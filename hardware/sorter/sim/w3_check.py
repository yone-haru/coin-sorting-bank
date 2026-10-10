# -*- coding: utf-8 -*-
"""W3 の高さを変えたときの 500円（通るべき）と 10円（落ちるべき）の結果  2026-09-27
  python w3_check.py 25.0 24.7 24.4
"""
import itertools
import sys
from collections import defaultdict
from multiprocessing import Pool

import coin_sim as cs

P = cs.load_params()
COINS = {c[0]: c for c in P["coins"]}


def job(a):
    H3, name, mu, dp, tol, s = a
    D = cs.default_design(P)
    D.update(mu=mu, damp=dp, tol=tol)
    D["windows"] = [list(w) for w in D["windows"]]
    D["windows"][2][2] = H3
    r = cs.run_one(D, COINS[name], seed=s)
    return (H3, name, r["ok"], r["out"], (r["vmax"] or 0) > 2)


def main():
    hs = [float(v) for v in sys.argv[1:]] or [25.0, 24.7, 24.4]
    jobs = [(H3, n, mu, dp, tol, s) for H3 in hs for n in ("500", "10", "100")
            for mu, dp, tol in itertools.product([0.25, 0.35, 0.45], [0.5, 0.8], [-0.1, 0.1])
            for s in range(30000, 30008)]
    with Pool(7) as pool:
        res = pool.map(job, jobs, chunksize=4)
    agg = defaultdict(lambda: [0, 0])
    fails = defaultdict(list)
    for H3, n, ok, out, art in res:
        if art:
            continue
        agg[(H3, n)][0] += ok
        agg[(H3, n)][1] += 1
        if not ok:
            fails[(H3, n)].append(out)
    for k in sorted(agg):
        print(f"W3 の高さ {k[0]}  {k[1]}円: {agg[k][0]}/{agg[k][1]}  外れ {fails.get(k, [])}")


if __name__ == "__main__":
    main()
