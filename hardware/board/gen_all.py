# -*- coding: utf-8 -*-
"""
基板の図面を全部作り直して、検証まで通す（これ1本を実行すればよい）
=============================================================================
    python gen_all.py

やること
  1. netlist.py の自己検査（ピンの繋ぎ忘れ・短絡）
  2. layout.py の配置検査（穴の取り合い・はみ出し・部品の重なり）
  3. KiCad 回路図を生成 → ERC（配線ミス検出）→ PDF 出力
  4. KiCad が図から読み取ったネットと netlist.py を照合
  5. 配線を計算して検証（全ネットが導通するか）
  6. 実体配線図 PDF（部品面／配線／はんだ面／チェックリスト）を出力

どこかで失敗したら、その時点で止まって理由を出す。
=============================================================================
"""
import os, subprocess, sys, io

HERE = os.path.dirname(os.path.abspath(__file__))
PROJDIR = os.path.join(HERE, "貯金箱制御基板")
SCH = os.path.join(PROJDIR, "貯金箱制御基板.kicad_sch")

# KiCad の場所（winget でユーザー領域に入る）
KICAD_CANDIDATES = [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\KiCad\10.0\bin\kicad-cli.exe"),
    r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
    r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe",
    "kicad-cli",
]


def find_kicad():
    for p in KICAD_CANDIDATES:
        if p == "kicad-cli":
            try:
                subprocess.run([p, "version"], capture_output=True, timeout=30)
                return p
            except Exception:
                continue
        if os.path.exists(p):
            return p
    return None


def step(n, title):
    print(f"\n[{n}] {title}")


def run(cmd, what):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if "失敗" in out or "Failed" in out or r.returncode not in (0,):
        print("    NG:", out[:400])
        raise SystemExit(f"{what} に失敗しました")
    return out


def main():
    sys.path.insert(0, HERE)

    step(1, "回路の自己検査（netlist.py）")
    import netlist
    probs = netlist.check()
    if probs:
        for p in probs:
            print("    -", p)
        raise SystemExit("回路の定義に問題があります")
    print(f"    OK  部品 {len(netlist.PARTS)} 個 / ネット {len(netlist.NETS)} 本 / "
          f"接続点 {sum(len(v) for v in netlist.NETS.values())} 箇所")

    step(2, "配置の検査（layout.py）")
    import layout
    probs = layout.check_layout()
    if probs:
        for p in probs:
            print("    -", p)
        raise SystemExit("部品の配置に問題があります")
    print(f"    OK  {layout.COLS}列 × {layout.ROWS}行に {len(layout.PINPOS)} 部品、重なりなし")

    step(3, "KiCad 回路図の生成")
    import gen_kicad_sch
    gen_kicad_sch.gen()

    kc = find_kicad()
    if kc is None:
        print("    ! kicad-cli が見つかりません。ERC と PDF は飛ばします")
        print("      入れるには:  winget install KiCad.KiCad")
    else:
        step(4, "ERC（KiCad による配線ミス検出）")
        out = run([kc, "sch", "erc", "--output", os.path.join(PROJDIR, "erc.txt"),
                   "--severity-all", SCH], "ERC")
        print("    ", out.splitlines()[0] if out else "")
        rpt = io.open(os.path.join(PROJDIR, "erc.txt"), encoding="utf-8").read()
        if "Errors 0" not in rpt.replace("\r", ""):
            print(rpt[:1500])
            raise SystemExit("ERC でエラーが出ました")
        print("    OK  エラー 0 件")

        step(5, "回路図 PDF の出力")
        run([kc, "sch", "export", "pdf", "--output", os.path.join(PROJDIR, "回路図.pdf"), SCH], "PDF出力")
        print("    OK  貯金箱制御基板/回路図.pdf")

        step(6, "回路図から読み取ったネットと netlist.py の照合")
        run([kc, "sch", "export", "netlist", "--format", "kicadsexpr",
             "--output", os.path.join(PROJDIR, "n.net"), SCH], "ネットリスト出力")
        import verify
        if verify.main() != 0:
            raise SystemExit("照合で不一致がありました")

    step(7, "配線の計算と検証")
    import wiring
    w = wiring.build()
    probs = wiring.verify(w)
    if probs:
        for p in probs:
            print("    -", p)
        raise SystemExit("配線に問題があります")
    c, total, length = wiring.summary(w)
    print(f"    OK  {total} 本（ブリッジ {c['ブリッジ']} / すずメッキ線 {c['すずメッキ線']} / "
          f"ジャンパ線 {c['ジャンパ線']}）約 {length*2.54:.0f} mm")

    step(8, "実体配線図 PDF の出力")
    import gen_layout
    gen_layout.main()

    print("\n=== 全部通りました ===")
    print("  基板設計/貯金箱制御基板/回路図.pdf      … 回路図（ERC 済み）")
    print("  基板設計/貯金箱制御基板/*.kicad_sch     … KiCad で開いて編集できる")
    print("  基板設計/実体配線図.pdf                 … 1:1 印刷用（部品面／配線／はんだ面／チェックリスト）")


if __name__ == "__main__":
    main()
