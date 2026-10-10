# -*- coding: utf-8 -*-
"""
照合：netlist.py（正）と、KiCad が回路図から読み取ったネットが一致するか
=============================================================================
KiCad は「線とラベルの位置」から接続を計算し直す。
つまりこの照合が通れば、
  ・回路図の絵が netlist.py どおりに描けている
  ・ラベルの置き場所ズレなどで繋がり損ねていない
の両方が保証される。

使い方：
    python verify.py
    （事前に kicad-cli で n.net を書き出しておく。gen_all.py が自動でやる）
=============================================================================
"""
import io, os, re, sys
from netlist import NETS, PARTS, NO_CONNECT

NETFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "貯金箱制御基板", "n.net")


def parse_kicad_net(path):
    """KiCad の .net から {ネット名: {(部品, ピン), ...}} を作る

    括弧を数えて (net ...) の塊を正確に切り出す。
    正規表現の後読みだけだと最後の1本を取りこぼす（2026-09-06 に踏んだ）。
    """
    s = io.open(path, encoding="utf-8").read()
    nets = {}
    for m in re.finditer(r'\(net\s', s):
        start = m.start()
        depth, i = 0, start
        while i < len(s):
            if s[i] == "(":
                depth += 1
            elif s[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        block = s[start:i + 1]
        nm = re.search(r'\(name "([^"]*)"\)', block)
        if not nm:
            continue
        name = nm.group(1).lstrip("/")
        nodes = {(a, b) for a, b in
                 re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', block)}
        if nodes:
            nets[name] = nodes
    return nets


def main():
    if not os.path.exists(NETFILE):
        print("n.net がありません。先に gen_all.py を実行してください")
        return 1

    kicad_all = parse_kicad_net(NETFILE)
    # 電源フラグ（#FLG）は ERC 用の印なので比較から外す
    kicad_all = {n: {(r, p) for (r, p) in v if not r.startswith("#")}
                 for n, v in kicad_all.items()}
    kicad_all = {n: v for n, v in kicad_all.items() if v}

    # KiCad は未接続ピンに unconnected-(...) という仮のネットを付ける。
    # これは netlist.py の NO_CONNECT と一致すべきもの
    kicad = {n: v for n, v in kicad_all.items() if not n.startswith("unconnected-")}
    kicad_nc = set()
    for n, v in kicad_all.items():
        if n.startswith("unconnected-"):
            kicad_nc |= v

    mine = {n: set(v) for n, v in NETS.items()}

    problems = []

    # --- 未接続の照合 ---
    mine_nc = set(NO_CONNECT)
    for x in sorted(mine_nc - kicad_nc):
        problems.append(f"未接続宣言なのに回路図では未接続になっていない: {x[0]}.{x[1]}")
    for x in sorted(kicad_nc - mine_nc):
        problems.append(f"回路図で未接続だが netlist.py に宣言が無い: {x[0]}.{x[1]}")

    only_mine = set(mine) - set(kicad)
    only_kicad = set(kicad) - set(mine)
    for n in sorted(only_mine):
        problems.append(f"netlist.py にあるが回路図に無いネット: {n}")
    for n in sorted(only_kicad):
        problems.append(f"回路図にあるが netlist.py に無いネット: {n}  {sorted(kicad[n])}")

    for n in sorted(set(mine) & set(kicad)):
        a, b = mine[n], kicad[n]
        if a != b:
            miss = sorted(a - b)
            extra = sorted(b - a)
            problems.append(f"ネット {n} の中身が違う")
            if miss:
                problems.append(f"    回路図で繋がっていない: {miss}")
            if extra:
                problems.append(f"    回路図で余計に繋がっている: {extra}")

    total = sum(len(v) for v in mine.values())
    print(f"netlist.py : ネット {len(mine)} 本 / 接続点 {total} 箇所 / 未接続 {len(mine_nc)} 箇所")
    print(f"回路図から  : ネット {len(kicad)} 本 / 接続点 {sum(len(v) for v in kicad.values())} 箇所 / 未接続 {len(kicad_nc)} 箇所")

    if problems:
        print(f"\n【不一致 {len(problems)} 件】")
        for p in problems:
            print("  -", p)
        return 1

    print("\n照合：完全一致。回路図は netlist.py どおりに描けています")
    return 0


if __name__ == "__main__":
    sys.exit(main())
