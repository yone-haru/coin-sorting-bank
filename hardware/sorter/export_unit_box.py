# -*- coding: utf-8 -*-
"""ユニット箱の印刷用 STL を 本番STL/ に書き出す。

・どれも A1 mini（180 × 180 × 180）に載ること
・浮いた部分が無いこと（1 つの塊なら OpenSCAD のログが Volumes: 2）
実行：3Dプリント/自作判別部/ で  python export_unit_box.py
"""
import re
import sys

import trimesh

import unit_box_lib as ub

OUT = ub.HERE / "本番STL"
BED = 180.0

# (part, 出力名, 期待する Volumes)
PARTS = [
    ("plateA", "⑥天板A.stl", 2),
    ("plateB", "⑥天板B.stl", 2),
    ("splice", "⑦継ぎ板（左右）.stl", 3),   # 2 枚が離れている
    ("legs",   "⑧脚×4.stl", 5),            # 4 本が離れている
    ("leg1",   None, 2),                    # 脚 1 本の浮きの確認だけ
]


def volumes(log):
    m = re.search(r"Volumes:\s*(\d+)", log)
    return int(m.group(1)) if m else None


def main():
    if "★" in (ub.HERE / "unit_box_dims.scad").read_text(encoding="utf-8"):
        print("！ ub_spk_hole_half がまだ実測値ではありません（★が残っています）。スピーカーのねじ穴を測ってください")
        return 1
    ng = 0
    for part, name, want in PARTS:
        out = (OUT / name) if name else (ub.BUILD / f"{part}_print.stl")
        ub.BUILD.mkdir(exist_ok=True)
        log = ub.run_openscad(ub.BOX_SCAD, out, {"part": f'"{part}"', "print_pose": "true"})
        vol = volumes(log)
        m = trimesh.load(str(out), force="mesh")
        lo, hi = m.bounds
        size = hi - lo
        ok_vol = vol == want
        ok_bed = all(s <= BED for s in size) and abs(lo[2]) < 0.01
        warn = "WARNING" in log or "ERROR" in log
        flag = "OK" if (ok_vol and ok_bed and not warn) else "NG"
        ng += flag == "NG"
        print(f"[{flag}] {name or part:22s} Volumes {vol}（期待 {want}）"
              f" 大きさ {size[0]:.1f} × {size[1]:.1f} × {size[2]:.1f}  下端 Z {lo[2]:.2f}"
              + ("  ！ログに WARNING/ERROR" if warn else ""))
    print("すべて OK" if ng == 0 else f"！ NG が {ng} 件")
    return 1 if ng else 0


if __name__ == "__main__":
    sys.exit(main())
