# -*- coding: utf-8 -*-
"""
センサーの位置をシミュレーションで確かめる。  2026-09-27

考え方（すべてのセンサーを「硬貨の通り道（溝）」の中に置く）
  ・穴ビーム A/B：壁の法線方向（z）。入口の直後。硬貨 1 枚ごとの「入った」合図と穴の有無
  ・通過ビーム P1/P2/P3：溝を縦（y 方向）に貫く光。LED は床の下、受光は硬貨の上（500円より上）。
      P1 は W1 の後ろ、P2 は W2 の後ろ、P3 は W3 の後ろ（＝500円だけが通る）
  ・レーンの決め方：入口を通ったあと P1 を通らなければ W1（1円/50円）、P1 を通って P2 を通らなければ W2（5円/100円）、
      P2 を通って P3 を通らなければ W3（10円）、P3 を通れば 500円
  ・「通らなければ」は入口での速さから予想した時刻 × 余裕 で待つ（タイムアウト）

調べること
  1. 窓から落ちる硬貨が、次の通過ビームを一瞬でも遮らないか（遮ると誤判定）
  2. 通る硬貨が必ず遮るか・遮る長さ
  3. 入口 → 各ビームの時間の最大（タイムアウトの決め方）＝音が鳴るまでの遅れ

  python sensor_eval.py '{"alpha":12,...}' [--seeds 6]
"""
import argparse
import json
import os
import sys
from multiprocessing import Pool

import numpy as np

import coin_sim as cs


def probes_for(D, px):
    z_beam = D["plate_t"] + 0.8          # 壁の面から 0.8mm（寄りかかった硬貨の厚みの中）
    pr = {}
    for bx in D["hole_beam_x"]:
        pr[f"H{int(bx)}"] = ((bx, D["hole_beam_y"], D["plate_t"] + 8), (bx, D["hole_beam_y"], -2))
    for i, x in enumerate(px):
        pr[f"P{i+1}"] = ((x, -1.0, z_beam), (x, 29.5, z_beam))
    return pr


def work(job):
    D, coin, seed, px = job
    return cs.run_one(D, coin, seed=seed, probes=probes_for(D, px))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("design", help="寸法の上書き（JSON）")
    ap.add_argument("--px", default="", help="通過ビームの x（カンマ区切り）。省略時は各窓の下流端＋8")
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--robust", default='{"mu":[0.2,0.35,0.5],"damp":[0.3,0.8]}')
    a = ap.parse_args()
    P = cs.load_params()
    base = cs.default_design(P)
    base.update(json.loads(a.design))
    px = [float(v) for v in a.px.split(",")] if a.px else \
         [w[0] + w[1] + max(base["bevel"], 0) + 8 for w in base["windows"]]
    rob = json.loads(a.robust)
    import itertools
    jobs = []
    for combo in itertools.product(*rob.values()):
        D = dict(base)
        D.update(dict(zip(rob.keys(), combo)))
        for c in P["coins"]:
            for s in range(a.seeds):
                jobs.append((D, c, 5000 + s, px))
    with Pool(max(1, os.cpu_count() - 1)) as pool:
        res = pool.map(work, jobs, chunksize=2)

    names = [f"P{i+1}" for i in range(len(px))]
    print(f"通過ビームの x = {px}")
    bad = 0
    lat = {}
    blk = {}
    for r in res:
        exp = r["expected"]
        pr = r.get("probes", {})
        hA = pr.get(f"H{int(base['hole_beam_x'][0])}", [])
        t0 = hA[0][0] if hA else None
        # 期待：exp より前の P は遮る、exp 以降の P は遮らない（exp=3 の 500 円は P1〜P3 すべて遮る）
        for i, n in enumerate(names):
            iv = pr.get(n, [])
            should = i < exp
            if should and not iv:
                bad += 1
                print(f"  × {r['coin']}円 が {n} を遮らなかった（結果 {r['out']} {cs.LANE_NAMES[r['lane']] if r['lane']>=0 else '-'}）")
            if (not should) and iv:
                dur = max(b - a_ for a_, b in iv)
                print(f"  △ {r['coin']}円（期待 {cs.LANE_NAMES[exp]}）が {n} を {dur*1000:.0f}ms 遮った（結果 {r['out']}）")
                bad += 1
            if should and iv and t0 is not None:
                lat.setdefault(n, []).append(iv[0][0] - t0)
                blk.setdefault(n, []).append(max(b - a_ for a_, b in iv))
        if t0 is None:
            print(f"  × {r['coin']}円 が穴ビームを遮らなかった（{r['out']}）")
            bad += 1
    print(f"不具合 {bad} / {len(res)} 回")
    for n in names:
        if n in lat:
            print(f"  {n}: 入口→到着 最短 {min(lat[n])*1000:.0f}ms 最長 {max(lat[n])*1000:.0f}ms ／ "
                  f"遮る長さ 最短 {min(blk[n])*1000:.0f}ms")
    oks = sum(r["ok"] for r in res)
    print(f"機械の判別（どの窓で落ちたか）: {oks}/{len(res)}")
    fails = {}
    for r in res:
        if not r["ok"]:
            k = f"{r['coin']}:{r['out']}"
            fails[k] = fails.get(k, 0) + 1
    if fails:
        print("  失敗", fails)


if __name__ == "__main__":
    main()
