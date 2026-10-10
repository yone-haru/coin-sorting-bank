# -*- coding: utf-8 -*-
"""フェルトの有無で、金種ごとの判別がどう変わるか（同じ条件・同じ落とし方で比べる）  2026-09-27"""
import itertools
from collections import defaultdict
from multiprocessing import Pool

import coin_sim as cs

P = cs.load_params()


def job(a):
    pad, c, mu, dp, tol, s = a
    D = cs.default_design(P)
    D.update(mu=mu, damp=dp, tol=tol, pad=pad)
    r = cs.run_one(D, c, seed=s)
    return (pad, c[0], r["ok"], r["out"], (r["vmax"] or 0) > 2)


def main():
    jobs = [(pad, c, mu, dp, tol, s) for pad in (True, False) for c in P["coins"]
            for mu, dp, tol in itertools.product([0.25, 0.35, 0.45], [0.5, 0.8], [-0.1, 0.1])
            for s in range(31000, 31012)]
    with Pool(7) as pool:
        res = pool.map(job, jobs, chunksize=4)
    agg = defaultdict(lambda: [0, 0])
    for pad, n, ok, out, art in res:
        if art:
            continue
        agg[(pad, n)][0] += ok
        agg[(pad, n)][1] += 1
        agg[(pad, "全体")][0] += ok
        agg[(pad, "全体")][1] += 1
    for pad in (True, False):
        print("フェルト" + ("あり" if pad else "なし") + "： " +
              "  ".join(f"{n}円 {agg[(pad, n)][0]}/{agg[(pad, n)][1]}" for n in ["1", "50", "5", "100", "10", "500"]) +
              f"  全体 {agg[(pad, '全体')][0]}/{agg[(pad, '全体')][1]} = {agg[(pad, '全体')][0] / agg[(pad, '全体')][1] * 100:.1f}%")


if __name__ == "__main__":
    main()
