# -*- coding: utf-8 -*-
"""
ファーム（CoinTracker）と decide() の突き合わせ用に、シミュレーションのエッジ列を書き出す。  2026-09-27

  python eq_export.py OUT_DIR [--seeds 2] [--runs 24] [--n 12]

OUT_DIR/cases.txt に 1 ケースずつ：
  C <id> <kind> <truth values...>
  E <beam 0-4> <level 0/1> <t_us>        （HA,HB,P1,P2,P3 の順の番号）
  D <t_done_us> <value> <t_in_us>        （decide(hole_rule="or") の出力。t_in の順）
  X <t_end_us>
OUT_DIR は ASCII のパスにする（g++ でビルドした突き合わせ側が日本語パスを開けないため）。
"""
import argparse
import itertools
import json
import os
import re
from multiprocessing import Pool

import numpy as np

import coin_sim as cs
import system_test as st

BEAMS = ["HA", "HB", "P1", "P2", "P3"]


def to_case(t, sig, dec, meta):
    ev = []
    for bi, name in enumerate(BEAMS):
        for a, b in st.edges(t, sig[name]):
            ev.append((int(round(a * 1e6)), bi, 1))
            ev.append((int(round(b * 1e6)), bi, 0))
    ev.sort()
    lines = [meta]
    lines += [f"E {bi} {lv} {tu}" for tu, bi, lv in ev]
    lines += [f"D {int(round(d[0] * 1e6))} {d[1]} {int(round(d[2] * 1e6))}" for d in dec]
    lines.append(f"X {int(round(t[-1] * 1e6))}")
    return "\n".join(lines)


def job_single(job):
    cid, D, coin, seed = job
    t, sig, truth = st.simulate(D, [(0.05, coin)], seed=seed, t_tail=2.2)
    if truth[0]["vmax"] > 2.0:
        return None
    dec, _, _ = st.decide(t, sig, "or")
    return to_case(t, sig, dec, f"C {cid} single {coin[0]}")


def job_burst(job):
    cid, D, seq, seed = job
    t, sig, truth = st.simulate(D, seq, seed=seed, t_tail=2.5)
    if max(tr["vmax"] for tr in truth) > 2.0:
        return None
    dec, _, _ = st.decide(t, sig, "or")
    return to_case(t, sig, dec, f"C {cid} burst " + " ".join(c[0] for _, c in seq))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--runs", type=int, default=24)
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--gap", default="0.35,1.2")
    a = ap.parse_args()
    P = cs.load_params()
    base = cs.default_design(P)
    s = open(cs.PARAMS, encoding="utf-8").read()
    m = re.search(r"pass_beam_x\s*=\s*\[([^\]]*)\]", s)
    base["pass_beam_x"] = [float(v) for v in m.group(1).split(",")]
    coins = P["coins"]

    jobs_s = []
    cid = 0
    for mu, dp, tol in itertools.product([0.25, 0.35, 0.45], [0.5, 0.8], [-0.1, 0.1]):
        D = dict(base)
        D.update(mu=mu, damp=dp, tol=tol)
        for c in coins:
            for sd in range(a.seeds):
                jobs_s.append((cid, D, c, 30000 + sd))
                cid += 1
    lo, hi = [float(v) for v in a.gap.split(",")]
    rng = np.random.default_rng(7)
    jobs_b = []
    for run in range(a.runs):
        D = dict(base)
        D.update(mu=float(rng.choice([0.25, 0.35, 0.45])), damp=float(rng.choice([0.5, 0.8])))
        t = 0.05
        seq = []
        for i in range(a.n):
            c = coins[int(rng.integers(len(coins)))]
            seq.append((t, c))
            t += float(rng.uniform(lo, hi))
        jobs_b.append((cid, D, seq, 40000 + run))
        cid += 1

    with Pool(max(1, os.cpu_count() - 1)) as pool:
        rs = pool.map(job_single, jobs_s, chunksize=2)
        rb = pool.map(job_burst, jobs_b, chunksize=1)
    out = [r for r in rs + rb if r]
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "cases.txt"), "w", encoding="ascii") as f:
        f.write("\n".join(out) + "\n")
    print(f"cases: single {sum(1 for r in rs if r)}/{len(rs)}  burst {sum(1 for r in rb if r)}/{len(rb)}")


if __name__ == "__main__":
    main()
