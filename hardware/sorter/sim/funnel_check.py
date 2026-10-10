"""じょうご（④）〜 関門の「硬貨が詰まらずに通るか」の試験（2026-10-01）

10/1 実機で関門の手前で詰まった原因を形で再現し、作り直した形で通ることを確かめる。
  ・旧：出口 4.2mm・直線 0.5mm・関門の上端から 1.5mm 浮いていた（OLD）
  ・新：出口 2.2mm・直線 10mm・すき間 0.4mm（selfsort_params.scad の fun_*）

方法（配置空間の到達判定）
  硬貨＝円板（直径 d・厚み t）。姿勢 (中心 x,y,z ・ ピッチ φ（x 軸まわり）・ヨー ψ（y 軸まわり）) を格子にとり、
  「壁に当たらない姿勢」だけで、上（蓋のスリット）から下（関門の先の着地場所）まで、下向きにだけ進めるかを調べる。
  ・入口の姿勢は全部試す（スリットを斜めに入る硬貨も含む）。出口まで行けない姿勢＝その姿勢で入ると必ず詰まる
  ・硬貨の寸法・じょうごと関門の位置ずれ（④ とレールのねじ穴の遊び）を振って、通れる入口姿勢の割合を出す
  ・ピッチとヨーは別々に調べる（両方を同時にやると姿勢の数が多すぎるため）。硬貨は重力で壁（z 小さい側）に
    もたれるので、厳しめの見方になる
使い方: python funnel_check.py            （STL 不要。寸法は下の値＝selfsort_params.scad と同じ）
"""
import itertools, sys
import numpy as np
from scipy.spatial import ConvexHull

# ---- selfsort_params.scad / 判別ユニット_本番.scad と同じ値 -------------------------------------
alpha, beta = 10.0, 12.0
plate_t, guard_gap = 3.0, 4.5
land_len, gate_gap = 28.0, 2.6
gate_y0, gate_top, cham = 29.0, 43.0, 2.0
slot_c, slot_size = (175.0, 56.0), (40.0, 6.0)
gate_W = np.array([165.0, -56.0, -35.0])
plate_top_t = 10.0

ca, sa, cb, sb = (np.cos(np.radians(alpha)), np.sin(np.radians(alpha)),
                  np.cos(np.radians(beta)), np.sin(np.radians(beta)))
ex = np.array([ca, 0, -sa]); ey = np.array([cb * sa, sb, cb * ca]); ez = np.array([sb * sa, -cb, sb * ca])
R = np.stack([ex, ey, ez], axis=1)          # 列＝レールの軸（実物の座標で）
P0 = gate_W - R @ np.array([land_len / 2, gate_top, plate_t + gate_gap / 2])
to_real = lambda p: P0 + R @ np.asarray(p, float)
to_rail = lambda q: R.T @ (np.asarray(q, float) - P0)


def box(x, y, z):
    return np.array(list(itertools.product(x, y, z)), float)


def rail_box(x, y, z):
    return np.array([to_real(p) for p in box(x, y, z)])


def new_design(dx=0.0, dy=0.0, dz=0.0):
    """新しいじょうごの空洞（実物の座標の凸包の組）。dx,dy,dz = じょうごだけをレール座標でずらす"""
    out_x, out_z = (0.5, 27.5), (3.2, 5.4)
    y0 = gate_top + 0.4; y1 = y0 + 10
    in_w, in_t, in_depth, lip = 29.5, 2.8, 8.0, 1.5
    sh = np.array([dx, dy, dz])
    def orect(y):
        return np.array([to_real(np.array(p) + sh) for p in box(out_x, (y, y + 0.01), out_z)])
    c2 = to_real(np.array([land_len / 2, y1, sum(out_z) / 2]) + sh)
    c0 = np.array([slot_c[0], -slot_c[1], 0.0])
    c = c0 + (c2 - c0) * (-in_depth / c2[2])
    ir = np.array([c + R @ np.array(p) for p in box((-in_w / 2, in_w / 2), (-0.005, 0.005), (-in_t / 2, in_t / 2))])
    w, h = slot_size[0] + 0.6, slot_size[1] + 0.6
    x0, yc = slot_c[0] - w / 2, -slot_c[1]
    lipbox = box((x0, x0 + w), (yc - h / 2, yc + h / 2), (-lip, 0.02))
    lip_bot = box((x0, x0 + w), (yc - h / 2, yc + h / 2), (-lip, -lip + 0.01))
    return [lipbox, np.vstack([lip_bot, ir]), np.vstack([ir, orect(y1)]), np.vstack([orect(y1), orect(y0)])], y0


def chamber_design(By=63.0, Bz=(3.1, 11.6), rs_depth=2.5, rs_t=2.8, out_z=(3.1, 5.5), straight=10.0, xr=(0.5, 27.5)):
    """案 D：出口の直線（薄い）→ 回転用の厚い部屋 B → 入口の絞り（薄い）→ スリット。曲がりは厚い部屋の中で回る"""
    def mk(dx=0.0, dy=0.0, dz=0.0):
        sh = np.array([dx, dy, dz])
        y0 = gate_top + 0.4; y1 = y0 + straight
        def rect(y, z):
            return np.array([to_real(np.array(p) + sh) for p in box(xr, (y, y + 0.01), z)])
        c2 = to_real(np.array([land_len / 2, y1, sum(out_z) / 2]) + sh)
        c0 = np.array([slot_c[0], -slot_c[1], 0.0])
        c = c0 + (c2 - c0) * (-rs_depth / c2[2])
        ir = np.array([c + R @ np.array(p) for p in box((-29.5 / 2, 29.5 / 2), (-0.005, 0.005), (-rs_t / 2, rs_t / 2))])
        w, h = slot_size[0] + 0.6, slot_size[1] + 0.6
        x0, yc = slot_c[0] - w / 2, -slot_c[1]
        lipbox = box((x0, x0 + w), (yc - h / 2, yc + h / 2), (-1.5, 0.02))
        lip_bot = box((x0, x0 + w), (yc - h / 2, yc + h / 2), (-1.5, -1.5 + 0.01))
        B = rect(By, Bz)
        return [lipbox, np.vstack([lip_bot, ir]), np.vstack([ir, B]), np.vstack([B, rect(y1, out_z)]), np.vstack([rect(y1, out_z), rect(y0, out_z)])], y0
    return mk


def old_design(dx=0.0, dy=0.0, dz=0.0):
    """旧（9/27〜9/30 に印刷したもの）：スリット 41×7 の柱 → 出口 27.4×4.2（関門の上端 +1.5 で終わる）"""
    sh = np.array([dx, dy, dz])
    t = plate_t
    w, h = slot_size[0] + 1, slot_size[1] + 1
    x0, yc = slot_c[0] - w / 2, -slot_c[1]
    colu = box((x0, x0 + w), (yc - h / 2, yc + h / 2), (-plate_top_t - 0.01, 0.01))
    outr = np.array([to_real(np.array(p) + sh) for p in box((0.3, land_len - 0.3), (gate_top + 1.5, gate_top + 2.0), (t + 0.4, t + 0.4 + gate_gap + 1.6))])
    return [colu, np.vstack([colu, outr])], gate_top + 1.5


def fixed_cavities():
    """関門・面取り・着地場所・蓋のスリット（じょうごと別の部品。ずらさない）"""
    t = plate_t
    gate = rail_box((0, land_len), (gate_y0, gate_top + 0.01), (t, t + gate_gap))
    gap = rail_box((0, land_len), (gate_top, gate_top + 0.9), (t, t + 3.0))              # 関門とじょうごの間のすき間（横は開いている）
    cham_ = np.array([to_real(p) for p in [(x, y, z) for x in (-1, land_len + 1)
                      for (y, z) in [(gate_top - cham, t + gate_gap), (gate_top, t + gate_gap), (gate_top, t + gate_gap + cham)]]])
    land = rail_box((0, land_len), (-3, gate_y0), (t, t + guard_gap))
    slot = box((slot_c[0] - slot_size[0] / 2, slot_c[0] + slot_size[0] / 2), (-slot_c[1] - slot_size[1] / 2, -slot_c[1] + slot_size[1] / 2), (0, 40))
    return [gate, gap, cham_, land, slot]


def half_spaces(pts):
    """凸包の不等式 A p + b <= 0（レール座標）"""
    q = np.array([to_rail(p) for p in pts])
    hu = ConvexHull(q)
    return hu.equations[:, :3], hu.equations[:, 3]


def inside(P, HS, tol=1e-6):
    ok = np.zeros(len(P), bool)
    for A, b in HS:
        ok |= np.all(P @ A.T + b <= tol, axis=1)
    return ok


def coin_points(d, t, n=32):
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    r = d / 2 / np.cos(np.pi / n)
    ring = np.stack([r * np.cos(th), r * np.sin(th)], 1)
    return np.vstack([np.c_[ring, np.full(n, s * t / 2)] for s in (-1, 1)])      # (u, v, w)


def pose_points(base, cx, cy, cz, phi, psi):
    """base=(u,v,w) 点群 → レール座標の点。φ=x 軸まわり（ピッチ）、ψ=y 軸まわり（ヨー）"""
    cph, sph, cps, sps = np.cos(phi), np.sin(phi), np.cos(psi), np.sin(psi)
    u = np.array([cps, 0, -sps]); v = np.array([0, cph, sph]); w = np.array([sps, -sph, cph * cps])
    return np.array([cx, cy, cz]) + base[:, 0:1] * u + base[:, 1:2] * v + base[:, 2:3] * w


def reach(HS, d, t, mode, y_top, y_end, dy=2.0, zs=None, angs=None, cxs=None, w_infl=0.0):
    """mode='pitch' か 'yaw'。入口の姿勢のうち出口まで下向きに進める割合と、通れる姿勢の範囲を返す"""
    base = coin_points(d, t + w_infl)
    zs = np.arange(1.0, 9.01, 0.4) if zs is None else zs
    angs = np.radians(np.arange(-14, 14.01, 1.0 if mode == 'pitch' else 0.5)) if angs is None else angs
    cxs = np.arange(3.0, 26.01, 3.0) if cxs is None else cxs
    ys = np.arange(y_top, y_end - 1e-9, -dy)
    shape = (len(cxs), len(zs), len(angs))

    def feasible(y):
        g = np.stack(np.meshgrid(cxs, zs, angs, indexing='ij'), -1).reshape(-1, 3)
        cx, cz, a = g[:, 0], g[:, 1], g[:, 2]
        ph = a if mode == 'pitch' else np.zeros_like(a)
        ps = a if mode == 'yaw' else np.zeros_like(a)
        cph, sph, cps, sps = np.cos(ph), np.sin(ph), np.cos(ps), np.sin(ps)
        u = np.stack([cps, 0 * a, -sps], 1); v = np.stack([0 * a, cph, sph], 1); w = np.stack([sps, -sph, cph * cps], 1)
        C = np.stack([cx, np.full_like(cx, y), cz], 1)
        P = (C[:, None, :] + base[None, :, 0:1] * u[:, None, :] + base[None, :, 1:2] * v[:, None, :]
             + base[None, :, 2:3] * w[:, None, :])                      # (姿勢, 点, 3)
        ok = np.zeros(len(g), bool)
        for A, b in HS:
            ok |= np.all(np.all(P @ A.T + b <= 1e-6, axis=2), axis=1)   # 全点が 1 つの凸包の中
        return ok.reshape(shape)

    from scipy.ndimage import binary_dilation
    st = np.ones((3, 3, 3), bool)
    F = [feasible(y) for y in ys]
    # 下から逆にたどる：ある層の姿勢が「出口まで行ける」か
    good = [None] * len(ys)
    good[-1] = F[-1]
    for k in range(len(ys) - 2, -1, -1):
        good[k] = F[k] & binary_dilation(good[k + 1], structure=st)
    return F[0], good[0], angs


def run(label, design, y_top, y_end, d, t, mode, tol_dz=(0.0,), infl=0.0):
    res = []
    for dxyz in tol_dz:
        dx_, dy_, dz_ = dxyz
        cav, _ = design(dx_, dy_, dz_)
        HS = [half_spaces(p) for p in cav + fixed_cavities()]
        f0, g0, angs = reach(HS, d, t, mode, y_top, y_end, w_infl=infl)
        # 入口（上の層）の姿勢で「入れる」もののうち、出口まで行けるもの
        ent = f0.any(axis=(0, 1))                     # 角度ごとに、入口で入れる姿勢があるか
        ok = g0.any(axis=(0, 1))
        res.append((dxyz, ent.sum(), ok.sum(), np.degrees(angs[ok]) if ok.any() else None, np.degrees(angs[ent])))
    return res


if __name__ == "__main__":
    # 蓋の中心（x=175）の真上から、着地場所までの y 範囲
    y_lid = to_rail(np.array([slot_c[0], -slot_c[1], -1.0]))[1]
    y_end = 16.0
    coins = [("1円", 20.0, 1.5), ("10円", 23.5, 1.5), ("500円", 26.5, 1.8), ("1円x2(重ね)", 20.0, 3.0), ("500+1円(重ね)", 26.5, 3.3)]
    shifts = [(0, 0, 0), (0.4, 0.4, 0.2), (-0.4, -0.4, -0.2)]
    for name, design in (("OLD", old_design), ("NEW", new_design)):
        print(f"=== {name} ===  (入口の層 y={y_lid:.1f} → 出口 y={y_end})")
        for mode in ("pitch", "yaw"):
            for cn, d, t in coins:
                worst = None
                for dxyz, nent, nok, okang, entang in run(name, design, y_lid, y_end, d, t, mode, shifts):
                    frac = nok / max(nent, 1)
                    if worst is None or frac < worst[0]:
                        worst = (frac, dxyz, nent, nok, okang)
                print(f"  {mode:5s} {cn:5s}  最悪のずれ {worst[1]}  入口で入れる角度 {worst[2]} 通れる角度 {worst[3]}  "
                      f"通れる割合 {worst[0] * 100:.0f}%  通れる角 {None if worst[4] is None else (worst[4].min(), worst[4].max())}")
            sys.stdout.flush()
