# -*- coding: utf-8 -*-
"""
1 つの形を、ばらつき（摩擦・跳ね・印刷誤差）の全組み合わせ × たくさんの落とし方で回し、
失敗を 1 件ずつ（どこで・どうなったか）表示する。

  python focus.py '{"alpha":10,"beta":12,"curb_h":2.5,"pad":true}' --seeds 20
"""
import argparse
import itertools
import json
import os
from collections import Counter
from multiprocessing import Pool

import coin_sim as cs


DT = 0.0002


def work(job):
    D, coin, seed, dt = job
    r = cs.run_one(D, coin, seed=seed, dt=dt)
    r["cond"] = {k: D[k] for k in ("mu", "damp", "tol")}
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("design")
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--robust", default='{"mu":[0.2,0.35,0.5],"damp":[0.3,0.8],"tol":[-0.15,0.15]}')
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--dt", type=float, default=0.0002)
    a = ap.parse_args()
    P = cs.load_params()
    base = cs.default_design(P)
    base.update(json.loads(a.design))
    rob = json.loads(a.robust)
    jobs = []
    for combo in itertools.product(*rob.values()):
        D = dict(base)
        D.update(dict(zip(rob.keys(), combo)))
        for c in P["coins"]:
            for s in range(a.seeds):
                jobs.append((D, c, 20000 + s, a.dt))
    with Pool(max(1, os.cpu_count() - 1)) as pool:
        res = pool.map(work, jobs, chunksize=2)
    art = [r for r in res if (r.get("vmax") or 0) > 2.0]     # 物理的にあり得ない速さ＝計算の破綻
    res = [r for r in res if (r.get("vmax") or 0) <= 2.0]
    ok = sum(r["ok"] for r in res)
    print(f"{json.dumps(json.loads(a.design), ensure_ascii=False)}")
    print(f"  判別 {ok}/{len(res)} = {ok/len(res)*100:.2f}%   （計算の破綻として除いた回 {len(art)}）")
    per = Counter()
    tot = Counter()
    for r in res:
        tot[r["coin"]] += 1
        per[r["coin"]] += r["ok"]
    print("  金種ごと " + " ".join(f"{c}:{per[c]}/{tot[c]}" for c in tot))
    kinds = Counter(f"{r['coin']}:{r['out']}" + (f"->{cs.LANE_NAMES[r['lane']]}" if r['lane'] >= 0 else "")
                    for r in res if not r["ok"])
    print("  失敗の種類", dict(kinds))
    if not a.quiet:
        for r in res:
            if not r["ok"]:
                print(f"    {r['coin']:>3}円 {r['out']:<7} lane={cs.LANE_NAMES[r['lane']] if r['lane']>=0 else '-':<4} "
                      f"x={r['x_exit']} t={r['t_exit']} vmax={r['vmax']} 着地={r['landed']} 条件={r['cond']}")
    tex = [r["t_exit"] for r in res if r.get("t_exit")]
    print(f"  通過時間 最長 {max(tex):.2f}s")


if __name__ == "__main__":
    main()
