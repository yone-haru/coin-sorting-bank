# -*- coding: utf-8 -*-
"""
全体テスト（シミュレーション）：硬貨を入れてから「正しい音が鳴るか」まで。  2026-09-27

  硬貨の物理（MuJoCo）→ センサー 5 本の信号（穴 A/B は 5円・50円の穴を光が通るところまで計算、
  P1〜P3 は光線を実際に当てる）→ 判定ロジック（ファームに入れる予定のもの）→ 鳴らす音

  python system_test.py single [--seeds 6]     1 枚ずつ（全金種 × 摩擦・跳ね・印刷誤差）
  python system_test.py burst  [--n 12]        続けて入れる（間隔 0.35〜1.2 秒のランダムな列）

判定ロジック（firmware に移す予定。ここが仕様の下書き）
  ・穴ビーム A（x=35）の遮光のかたまり＝硬貨 1 枚の入口。LOW が GROUP_GAP_MS 続いたらかたまりの終わり
  ・かたまりの中で遮光が 2 回に割れ、割れ目が中ほど（30〜70%）にあり、長さの 4〜40% → 穴あり
  ・A と B（x=49）の立ち上がりの時間差 → 速さ
  ・通過ビーム P1/P2/P3 の立ち上がりは、その 1 つ手前まで来ている一番古い硬貨に割り当てる（追い越さない）
  ・期限（T_STAGE）までに次の P に来なければ、その段の窓で落ちたと判断して音を決める
      段 0（入口のあと P1 が来ない）→ 穴あり 50円 / なし 1円
      段 1（P1 のあと P2 が来ない）→ 穴あり 5円 / なし 100円
      段 2（P2 のあと P3 が来ない）→ 10円
      P3 が来た → 500円（すぐ鳴らす）
"""
import argparse
import itertools
import json
import math
import os
from collections import Counter
from multiprocessing import Pool

import numpy as np
import mujoco

import coin_sim as cs

GROUP_GAP_MS = 40          # 穴ビーム：これ以上光が戻ったらかたまりの終わり
P_MIN_MS = 8               # 通過ビーム：これより短い遮光は無視
T_STAGE = [0.90, 0.60, 0.50]   # 入口→P1、P1→P2、P2→P3 の期限 [s]
HOLE_RATIO = (0.04, 0.40)
HOLE_CENTER = (0.30, 0.70)
VALUE_OF = {("W1", True): "50", ("W1", False): "1", ("W2", True): "5", ("W2", False): "100",
            ("W3", True): "10", ("W3", False): "10", ("END", True): "500", ("END", False): "500"}


# ---------------------------------------------------------------------------
# 物理：複数の硬貨を順に落とし、1ms ごとのセンサーの状態を記録する
def simulate(D, seq, seed=0, dt=0.0002, t_tail=2.0):
    """seq: [(t_release, coin), ...]。戻り値：(times, sensors{name: bool[]}, truth[])"""
    rng = np.random.default_rng(seed)
    specs = [(c[0], c[1], c[2]) for _, c in seq]
    xml, R = cs.build_xml(D, specs, dt=dt)
    xml = xml.replace('<body name="c', '<body gravcomp="1" name="c')
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    bids = [model.body(f"c{i}").id for i in range(len(specs))]
    qadr = [model.jnt_qposadr[model.body_jntadr[b]] for b in bids]
    vadr = [model.jnt_dofadr[model.body_jntadr[b]] for b in bids]
    for i in range(len(specs)):
        data.qpos[qadr[i]:qadr[i] + 3] = [3.0 + 0.2 * i, 3.0, 3.0]
    mujoco.mj_forward(model, data)
    px = D["pass_beam_x"]
    zb = D["plate_t"] + 0.8
    probes = {f"P{i+1}": ((x, -1.0, zb), (x, 29.5, zb)) for i, x in enumerate(px)}
    hb = D["hole_beam_x"]
    hy = D["hole_beam_y"]
    state = ["wait"] * len(specs)
    t_rel = [t for t, _ in seq]
    truth = [dict(coin=c[0], lane=None, x_cross=None, z_prev=99.0, t_out=None, vmax=0.0) for _, c in seq]
    T = t_rel[-1] + t_tail
    times, sig = [], {k: [] for k in ["HA", "HB"] + list(probes)}
    k = 0
    while data.time < T:
        for i, (_, c) in enumerate(seq):
            nm, dia, th, hole = c
            if state[i] == "wait" and data.time >= t_rel[i]:
                r = dia / 2
                x0 = D["land_len"] / 2 + rng.uniform(-0.4, 0.4)
                p0 = [x0, D["gate_y0"] + r + rng.uniform(0, 3), D["plate_t"] + th / 2 + rng.uniform(0.1, 0.8)]
                vw = np.array([0, 0, -rng.uniform(0.8, 1.3)]) + R @ np.array([rng.uniform(-0.03, 0.12), 0, 0])
                cs.set_coin(model, data, i, R, p0, vw, w_rail=rng.normal(0, 5, 3),
                            tilt=(rng.normal(0, 2), rng.normal(0, 2)))
                model.body_gravcomp[bids[i]] = 0.0
                state[i] = "run"
            elif state[i] == "run":
                p = R.T @ data.xpos[bids[i]] * 1000
                tr = truth[i]
                r = dia / 2
                tr["vmax"] = max(tr["vmax"], float(np.linalg.norm(data.qvel[vadr[i]:vadr[i] + 3])))
                if p[2] < D["plate_t"] / 2 <= tr["z_prev"]:
                    tr["x_cross"] = p[0]
                tr["z_prev"] = p[2]
                out = None
                if (p[2] < -0.5 * r and p[1] < D["plate_y1"]) or (p[2] < 0 and p[1] < D["plate_y0"]):
                    li = cs.lane_of_x(D, tr["x_cross"] if tr["x_cross"] is not None else p[0])
                    out = cs.LANE_NAMES[li] if li >= 0 else "?"
                elif p[0] > D["plate_len"] + 3:
                    out = "END"
                elif abs(p[2]) > 60 or p[1] < -80 or p[1] > 120:
                    out = "LOST"
                if out:
                    tr["lane"] = out
                    tr["t_out"] = data.time
                    state[i] = "fall"
            elif state[i] == "fall" and data.time - truth[i]["t_out"] > 0.4:
                data.qpos[qadr[i]:qadr[i] + 3] = [3.0 + 0.2 * i, 3.0, 3.0]
                data.qvel[vadr[i]:vadr[i] + 6] = 0
                model.body_gravcomp[bids[i]] = 1.0
                state[i] = "done"
        mujoco.mj_step(model, data)
        k += 1
        if k % 5:
            continue
        times.append(data.time)
        for kk, hit in cs.probe_hits(model, data, R, probes).items():
            sig[kk].append(hit)
        # 穴ビーム：光線（z 方向）と硬貨の円板（穴つき）が交わるか
        hA = hB = False
        for i, (_, c) in enumerate(seq):
            if state[i] not in ("run", "fall"):
                continue
            nm, dia, th, hole = c
            cpos = R.T @ data.xpos[bids[i]] * 1000
            M = R.T @ data.xmat[bids[i]].reshape(3, 3)
            n = M[:, 2]
            if abs(n[2]) < 0.2:
                continue
            for j, bx in enumerate(hb):
                zs = cpos[2] - (n[0] * (bx - cpos[0]) + n[1] * (hy - cpos[1])) / n[2]
                dvec = np.array([bx, hy, zs]) - cpos
                d = float(np.linalg.norm(dvec))
                blocked = (d <= dia / 2) and (d >= hole / 2) and (-5 < zs < D["plate_t"] + 8)
                if blocked:
                    if j == 0:
                        hA = True
                    else:
                        hB = True
        sig["HA"].append(hA)
        sig["HB"].append(hB)
    for i, tr in enumerate(truth):
        if tr["lane"] is None:
            tr["lane"] = "STALL"
            p = R.T @ data.xpos[bids[i]] * 1000
            tr["stall_at"] = (round(float(p[0]), 1), round(float(p[1]), 1), round(float(p[2]), 1))
    return np.array(times), {k: np.array(v) for k, v in sig.items()}, truth


# ---------------------------------------------------------------------------
# 判定ロジック（ファームの下書き）
def edges(t, s):
    """立ち上がり・立ち下がりの時刻の組 [(on, off), ...]"""
    out = []
    on = None
    for ti, v in zip(t, s):
        if v and on is None:
            on = ti
        elif not v and on is not None:
            out.append((on, ti))
            on = None
    if on is not None:
        out.append((on, t[-1]))
    return out


def group_pulses(iv, gap):
    groups = []
    for a, b in iv:
        if groups and a - groups[-1][-1][1] < gap:
            groups[-1].append((a, b))
        else:
            groups.append([(a, b)])
    return groups


def has_hole(g):
    if len(g) < 2:
        return False
    total = g[-1][1] - g[0][0]
    if total <= 0:
        return False
    for (a1, b1), (a2, b2) in zip(g, g[1:]):
        gap = a2 - b1
        center = ((b1 + a2) / 2 - g[0][0]) / total
        if HOLE_RATIO[0] < gap / total < HOLE_RATIO[1] and HOLE_CENTER[0] < center < HOLE_CENTER[1]:
            return True
    return False


GROUP_GAP2_MS = 80         # v2：穴ビームのかたまりの切れ目（遅い硬貨の穴の割れ目は 40ms を超える）
MIN_PASS_MS = 20           # v2：これより短いかたまりは「ちらつき」
K_DEADLINE = 1.8           # v2：期限 ＝ K × 距離 ÷ 直前の速さ ＋ 余裕
T_MARGIN = 0.08
T_CLAMP = [(0.25, 0.9), (0.20, 0.7), (0.20, 0.8)]
def _beam_x():
    import re as _re
    P_ = cs.load_params()
    txt = open(cs.PARAMS, encoding="utf-8").read()
    m_ = _re.search(r"pass_beam_x\s*=\s*\[([^\]]*)\]", txt)
    px_ = [float(v) for v in m_.group(1).split(",")]
    return [P_["hole_beam_x"][0], P_["hole_beam_x"][1]] + px_


BEAM_X = _beam_x()         # [穴A, 穴B, P1, P2, P3]（selfsort_params.scad から）


def hole_pairs(g):
    """隣り合う 2 回の遮光が「ほぼ同じ長さ」で、割れ目が短い → 穴（中心の穴の両側）"""
    for (a1, b1), (a2, b2) in zip(g, g[1:]):
        span = b2 - a1
        gap = a2 - b1
        d1, d2 = b1 - a1, b2 - a2
        if span <= 0 or d1 <= 0 or d2 <= 0:
            continue
        if 0.04 < gap / span < 0.45 and 0.4 < d1 / d2 < 2.5:
            return True
    return False


def decide(t, sig, hole_rule="or"):
    """v2：入口は穴ビーム B で数える。期限は直前の速さから決める"""
    xA, xB, x1, x2, x3 = BEAM_X
    gA = group_pulses(edges(t, sig["HA"]), GROUP_GAP2_MS / 1000)
    gB = group_pulses(edges(t, sig["HB"]), GROUP_GAP2_MS / 1000)
    usedA = set()
    coins = []
    for g in gB:
        if g[-1][1] - g[0][0] < MIN_PASS_MS / 1000:
            continue
        c = dict(t_in=g[0][0], holeB=hole_pairs(g), holeA=False, v=None, stage=0, t_stage=g[0][0], done=None)
        cand = [i for i, ga in enumerate(gA) if i not in usedA and c["t_in"] - 0.5 < ga[0][0] < c["t_in"]]
        if cand:
            i = cand[-1]
            usedA.add(i)
            c["holeA"] = any(hole_pairs(gA[j]) for j in cand)
            dt_ = c["t_in"] - gA[i][0][0]
            if dt_ > 0.005:
                c["v"] = (xB - xA) / dt_
        c["hole"] = (c["holeA"] or c["holeB"]) if hole_rule == "or" else (c["holeA"] and c["holeB"])
        coins.append(c)
    dist = [x1 - xB, x2 - x1, x3 - x2]

    def deadline(c):
        s_ = c["stage"]
        v = c["v"] or 250.0                                   # mm/s（分からなければ遅めに見る）
        T = K_DEADLINE * dist[s_] / max(v, 60.0) + T_MARGIN
        lo, hi = T_CLAMP[s_]
        return c["t_stage"] + min(max(T, lo), hi)

    ev = []
    for i in range(3):
        for a, b in edges(t, sig[f"P{i+1}"]):
            if b - a >= P_MIN_MS / 1000:
                ev.append((a, i + 1))
    ev.sort()
    stage_lane = {0: "W1", 1: "W2", 2: "W3"}
    out = []
    orphans = 0

    def expire(now):
        for c in coins:
            if c["done"] is None and c["t_in"] <= now and c["stage"] < 3 and now > deadline(c):
                c["done"] = deadline(c)
                out.append((c["done"], VALUE_OF[(stage_lane[c["stage"]], c["hole"])], c["t_in"]))

    for te, pi in ev:
        expire(te)
        cand = [c for c in coins if c["done"] is None and c["stage"] == pi - 1 and c["t_in"] < te]
        if not cand:
            orphans += 1
            continue
        dx = dist[pi - 1]

        def pred_err(cc):
            v_ = cc["v"] or 250.0
            exp_ = dx / max(v_, 60.0)
            return abs((te - cc["t_stage"]) - exp_) / exp_
        # 予想到着時刻に一番近い硬貨に割り当てる（同じくらいなら古い方）
        c = min(cand, key=lambda cc: (round(pred_err(cc), 1), cc["t_in"]))
        # 追い越しは無いので、c より古くて同じ段で待っている硬貨は、この段の窓で落ちている → すぐ決める
        for older in cand:
            if older is not c and older["t_in"] < c["t_in"]:
                older["done"] = te
                out.append((te, VALUE_OF[(stage_lane[older["stage"]], older["hole"])], older["t_in"]))
        if te - c["t_stage"] > 0.005:
            c["v"] = dx / (te - c["t_stage"])
        c["stage"] = pi
        c["t_stage"] = te
        if pi == 3:
            c["done"] = te
            out.append((te, "500", c["t_in"]))
    expire(t[-1] + 10)
    out.sort(key=lambda o: o[2])
    return out, orphans, coins


# ---------------------------------------------------------------------------
def run_single(job):
    D, coin, seed = job
    t, sig, truth = simulate(D, [(0.05, coin)], seed=seed, t_tail=2.2)
    res = {}
    for rule in ("or", "and"):
        dec, orphans, coins = decide(t, sig, rule)
        played = [d[1] for d in dec]
        res[rule] = dict(played=played, orphans=orphans,
                         latency=(dec[0][0] - 0.05) if dec else None)
    iv = {k: [(round(a, 3), round(b, 3)) for a, b in edges(t, v)] for k, v in sig.items()}
    return dict(coin=coin[0], truth=truth[0]["lane"], vmax=truth[0]["vmax"], res=res,
                hole_true=coin[3] > 0, cond=(D["mu"], D["damp"], D["tol"]), seed=seed, iv=iv)


def run_burst(job):
    D, seq_spec, seed = job
    t, sig, truth = simulate(D, seq_spec, seed=seed, t_tail=2.5)
    dec, orphans, coins = decide(t, sig, "or")
    # 硬貨ごとに判定を対応させる：入口の数が硬貨の数と同じなら順番どおり、違えば時刻の近いもの
    rel = [t_ for t_, _ in seq_spec]
    per = []
    used = set()
    if len(dec) == len(rel):
        per = [d[1] for d in dec]
        used = set(range(len(dec)))
    else:
        for i, tr_ in enumerate(rel):
            best = None
            for j, d in enumerate(dec):
                if j in used:
                    continue
                lag = d[2] - tr_
                if 0.05 < lag < 2.0 and (best is None or lag < dec[best][2] - tr_):
                    best = j
            if best is not None:
                used.add(best)
                per.append(dec[best][1])
            else:
                per.append("（無音）")
    return dict(seq=[c[0] for _, c in seq_spec], truth=[tr["lane"] for tr in truth],
                stall=[tr.get("stall_at") for tr in truth], times=[round(t_, 2) for t_ in rel],
                vmax=max(tr["vmax"] for tr in truth), played=[d[1] for d in dec], per=per,
                extra=len(dec) - len(used), n_entry=len(coins), orphans=orphans,
                close_pairs=sum(1 for a_, b_ in zip(sorted(d[0] for d in dec), sorted(d[0] for d in dec)[1:]) if b_ - a_ < 0.3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["single", "burst"])
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--runs", type=int, default=24)
    ap.add_argument("--gap", default="0.35,1.2")
    ap.add_argument("--dump", action="store_true")
    ap.add_argument("--design", default="{}", help="寸法の上書き（JSON）")
    a = ap.parse_args()
    P = cs.load_params()
    base = cs.default_design(P)
    base.update(json.loads(a.design))
    base["pass_beam_x"] = [98.0, 134.0, 173.5]
    import re
    s = open(cs.PARAMS, encoding="utf-8").read()
    m = re.search(r"pass_beam_x\s*=\s*\[([^\]]*)\]", s)
    if m:
        base["pass_beam_x"] = [float(v) for v in m.group(1).split(",")]
    coins = P["coins"]
    if a.mode == "single":
        jobs = []
        for mu, dp, tol in itertools.product([0.25, 0.35, 0.45], [0.5, 0.8], [-0.1, 0.1]):
            D = dict(base)
            D.update(mu=mu, damp=dp, tol=tol)
            for c in coins:
                for sd in range(a.seeds):
                    jobs.append((D, c, 30000 + sd))
        with Pool(max(1, os.cpu_count() - 1)) as pool:
            res = pool.map(run_single, jobs, chunksize=2)
        art = [r for r in res if r["vmax"] > 2.0]
        res = [r for r in res if r["vmax"] <= 2.0]
        print(f"1 枚ずつ：{len(res)} 回（計算の破綻 {len(art)} 回を除く）")
        for rule in ("or", "and"):
            ok = sum(1 for r in res if r["res"][rule]["played"] == [r["coin"]])
            print(f"  穴の判定={rule}: 正しい音 {ok}/{len(res)} = {ok/len(res)*100:.2f}%")
        rule = "or"
        per = Counter()
        tot = Counter()
        kinds = Counter()
        lat = {}
        for r in res:
            tot[r["coin"]] += 1
            pl = r["res"][rule]["played"]
            if pl == [r["coin"]]:
                per[r["coin"]] += 1
                lat.setdefault(r["coin"], []).append(r["res"][rule]["latency"])
            else:
                mech_ok = r["truth"] == {"1": "W1", "50": "W1", "5": "W2", "100": "W2", "10": "W3", "500": "END"}[r["coin"]]
                kinds[f"{r['coin']}→{pl}（機械 {'正' if mech_ok else '誤:' + str(r['truth'])}）"] += 1
        print("  金種ごと " + " ".join(f"{c}:{per[c]}/{tot[c]}" for c in tot))
        print("  音が鳴るまで（投入から）: " + " ".join(f"{c}円 最長 {max(v):.2f}s" for c, v in lat.items()))
        if kinds:
            print("  間違い：")
            for k, v in kinds.most_common():
                print(f"    {k} ×{v}")
        # 段ごとの所要時間（期限を決めるため）
        st = {"入口→P1": [], "P1→P2": [], "P2→P3": []}
        for r in res:
            iv = r["iv"]
            if not iv["HA"]:
                continue
            t0 = iv["HA"][0][0]
            p = [iv[f"P{i}"][0][0] if iv[f"P{i}"] else None for i in (1, 2, 3)]
            if p[0]: st["入口→P1"].append(p[0] - t0)
            if p[0] and p[1]: st["P1→P2"].append(p[1] - p[0])
            if p[1] and p[2]: st["P2→P3"].append(p[2] - p[1])
        print("  段ごとの所要時間: " + " ".join(f"{k} 最短 {min(v):.3f} 最長 {max(v):.3f}" for k, v in st.items() if v))
        if a.dump:
            for r in res:
                if r["res"]["or"]["played"] != [r["coin"]]:
                    print(f"--- {r['coin']}円 条件{r['cond']} seed{r['seed']} 機械 {r['truth']} 音 {r['res']['or']['played']}")
                    for k, v in r["iv"].items():
                        print(f"     {k}: {v}")
    else:
        lo, hi = [float(v) for v in a.gap.split(",")]
        jobs = []
        rng = np.random.default_rng(7)
        for run in range(a.runs):
            D = dict(base)
            D.update(mu=float(rng.choice([0.25, 0.35, 0.45])), damp=float(rng.choice([0.5, 0.8])))
            t = 0.05
            seq = []
            for i in range(a.n):
                c = coins[int(rng.integers(len(coins)))]
                seq.append((t, c))
                t += float(rng.uniform(lo, hi))
            jobs.append((D, seq, 40000 + run))
        with Pool(max(1, os.cpu_count() - 1)) as pool:
            res = pool.map(run_burst, jobs, chunksize=1)
        tot = ok = mech = 0
        art = 0
        for r in res:
            if r["vmax"] > 2.0:
                art += 1
                continue
            n = len(r["seq"])
            tot += n
            m = sum(1 for a_, b_ in zip(r["seq"], r["per"]) if a_ == b_)
            ok += m
            want = {"1": "W1", "50": "W1", "5": "W2", "100": "W2", "10": "W3", "500": "END"}
            mech += sum(1 for c, l in zip(r["seq"], r["truth"]) if want[c] == l)
            extra_total = r["extra"]
            if m != n or extra_total:
                print(f"  列：{' '.join(r['seq'])}\n    投入：{r['times']}\n    機械：{' '.join(str(x) for x in r['truth'])}"
                      f"\n    音　：{' '.join(r['per'])}（余分な音 {r['extra']}・入口 {r['n_entry']} 枚・宙に浮いた通過信号 {r['orphans']}）")
                st_ = [x for x in r["stall"] if x]
                if st_:
                    print(f"    止まった位置（レール座標 x,y,z）：{st_}")
        print(f"続けて入れる（間隔 {lo}〜{hi} 秒・{a.n} 枚 × {a.runs} 回、破綻 {art} 回を除く）：")
        print(f"  機械の判別 {mech}/{tot}、正しい音 {ok}/{tot} = {ok/max(tot,1)*100:.2f}%")
        cp = sum(r.get("close_pairs", 0) for r in res if r["vmax"] <= 2.0)
        print(f"  判定どうしが 0.3 秒以内に続いた回数 {cp}（今のファームの RETRIG_MS=300 だと後の音が消える）")


if __name__ == "__main__":
    main()
