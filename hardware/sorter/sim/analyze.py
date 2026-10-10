# -*- coding: utf-8 -*-
"""
sweep の結果（JSON）を「形の組み合わせごと」にまとめ、ばらつき（摩擦・跳ね・印刷誤差）の中で
一番悪い判別率が高い順に並べる。

  python analyze.py sweep1.json [--robust mu,damp,tol] [--top 20]
"""
import argparse
import json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--robust", default="mu,damp,tol", help="ばらつきとして扱うキー")
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args()
    rows = json.load(open(a.file, encoding="utf-8"))
    rob = set(a.robust.split(","))
    skip = {"rate", "per", "fails", "t_max", "vmax", "beam_dev_max"}
    groups = {}
    for r in rows:
        key = tuple((k, r[k]) for k in r if k not in skip and k not in rob)
        groups.setdefault(key, []).append(r)
    out = []
    for key, rs in groups.items():
        worst = min(r["rate"] for r in rs)
        mean = sum(r["rate"] for r in rs) / len(rs)
        coins = {}
        for r in rs:
            for c, v in r["per"].items():
                coins[c] = min(coins.get(c, 1), v)
        fails = {}
        for r in rs:
            for f, n in r["fails"].items():
                fails[f] = fails.get(f, 0) + n
        tmax = max((r["t_max"] or 0) for r in rs)
        beam = max((r["beam_dev_max"] or 0) for r in rs)
        worst_cond = min(rs, key=lambda r: r["rate"])
        wc = " ".join(f"{k}={worst_cond[k]}" for k in worst_cond if k in rob)
        out.append((worst, mean, key, coins, fails, tmax, beam, wc))
    out.sort(key=lambda o: (-o[0], -o[1]))
    for worst, mean, key, coins, fails, tmax, beam, wc in out[:a.top]:
        k = " ".join(f"{k}={v}" for k, v in key)
        cs = " ".join(f"{c}:{v*100:.0f}" for c, v in coins.items())
        fs = ", ".join(f"{f}×{n}" for f, n in sorted(fails.items(), key=lambda x: -x[1])[:5])
        print(f"最悪 {worst*100:5.1f}% 平均 {mean*100:5.1f}%  {k}\n"
              f"      金種ごとの最悪 {cs} | 通過 最長 {tmax}s | 穴ビームでの浮き 最大 {beam}mm | 最悪条件 {wc}\n"
              f"      失敗 {fs}")
    print(f"（形の組み合わせ {len(out)} 通り）")


if __name__ == "__main__":
    main()
