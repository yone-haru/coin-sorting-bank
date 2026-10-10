"""じょうご → 関門 の断面の試験（2026-10-01）  funnel_check.py の形状定義を使う軽い版

各高さ y（レール座標）で、空洞の厚み（z 方向のすき間）と幅（x 方向）を測り、
  ・許容の傾き φmax(y)：直径 d・厚み t の硬貨が、そのすき間に傾いて入れる最大の角度
        d*sin(φ) + t*cos(φ) <= 厚み   （x 軸まわりの傾き）
  ・下へ行くほど φmax が「減る」か（楔：上流で入れた傾きが下流の段で引っかかる）を見る
  ・段（厚みが急に狭くなる所）の有無
を出す。旧形状との比較、組立ずれ（④ とレールのねじ穴の遊び）の影響、重ね（2 枚）が入らないことも確認する。
"""
import sys
import numpy as np
import funnel_check as f

XC = 14.0            # 関門の中央
coins = [("1円", 20.0, 1.5), ("10円", 23.5, 1.5), ("500円", 26.5, 1.8)]
stacks = [("1円x2", 20.0, 3.0), ("500+1円", 26.5, 3.3), ("100+50円", 22.6, 3.4)]


def gap_at(HS, y, x=XC):
    """その (x,y) で、空洞の z の連続した区間のうち一番長いもの (z0, z1)。無ければ None"""
    zs = np.arange(-12.0, 14.0, 0.02)
    P = np.c_[np.full_like(zs, x), np.full_like(zs, y), zs]
    ins = f.inside(P, HS)
    best = None; start = None
    for z, v in zip(zs, ins):
        if v and start is None:
            start = z
        if (not v or z == zs[-1]) and start is not None:
            seg = (start, z)
            if best is None or seg[1] - seg[0] > best[1] - best[0]:
                best = seg
            start = None
    return best


def phimax(T, d, t):
    if T < t:
        return None
    for a in np.arange(0, 45, 0.1):
        r = np.radians(a)
        if d * np.sin(r) + t * np.cos(r) > T:
            return max(a - 0.1, 0.0)
    return 45.0


def analyse(name, design, sh=(0, 0, 0), ys=None):
    cav, ytop = design(*sh)
    HS = [f.half_spaces(p) for p in cav + f.fixed_cavities()]
    ys = ys if ys is not None else np.arange(f.gate_y0 - 6, 76.0, 2.0)
    rows = []
    for y in ys:
        g = gap_at(HS, y)
        rows.append((y, g))
    return rows


def report(name, design, sh=(0, 0, 0)):
    rows = analyse(name, design, sh)
    print(f"--- {name} ずれ(x,y,z)={sh} ---   y : 厚み [z0..z1]   許容傾き 500円/10円/1円")
    prev = {c[0]: None for c in coins}
    wedge = []
    for y, g in rows:
        if g is None:
            print(f"  y={y:5.1f}  空洞なし"); continue
        T = g[1] - g[0]
        ph = [phimax(T, d, t) for _, d, t in coins]
        print(f"  y={y:5.1f}  {T:4.2f} [{g[0]:5.2f}..{g[1]:5.2f}]  " + " / ".join("-" if p is None else f"{p:4.1f}°" for p in ph))
    return rows


if __name__ == "__main__":
    for nm, dsg in (("OLD", f.old_design), ("NEW", f.new_design)):
        report(nm, dsg)
    print()
    print("=== 組立ずれ（NEW）：出口の z と関門の z の重なり ===")
    for sh in [(0.4, 0.4, 0.2), (-0.4, -0.4, -0.2), (0.4, 0, -0.2), (-0.4, 0, 0.2)]:
        rows = analyse("NEW", f.new_design, sh, ys=np.array([f.gate_top + 0.2, f.gate_top - 2.0, f.gate_y0 + 1]))
        print("  ずれ", sh, [(round(y, 1), None if g is None else (round(g[0], 2), round(g[1], 2))) for y, g in rows])
    print()
    print("=== 重ね（2 枚）が通れる最小の厚みの場所：入口の絞りより下で、最も狭い厚み ===")
    rows = analyse("NEW", f.new_design)
    Ts = [(y, g[1] - g[0]) for y, g in rows if g]
    print("  最小厚み", min(Ts, key=lambda a: a[1]), " 最大（絞りより下）", max(T for y, T in Ts if y < 70))
    for nm, d, t in stacks:
        print(f"  {nm} t={t}: 絞り 2.8 に入る？ {'入る(NG)' if t <= 2.8 else '入らない(OK)'}")
