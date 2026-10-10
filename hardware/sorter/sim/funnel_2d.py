"""じょうご → 関門 の 2D（y–z 面）到達試験（2026-10-01）

硬貨を「長さ d・厚み t の板」として、姿勢 (中心 y, 中心 z, 傾き φ) が空洞の中に収まるかを調べる。
  ・上（蓋のスリット）から入れる姿勢のうち、下向きにだけ動いて関門の先まで行ける割合を出す
  ・行けない姿勢で入ると必ず詰まる（＝曲がり角を回れない長い硬貨などが見つかる）
  ・印刷の誤差で空洞が細ることを見込み、硬貨を厚み +0.2（空洞が片側 0.1 細る）にした場合も見る
funnel_check.py の形（new_design / old_design）を使う。x は関門の中央 (14) で切る。
"""
import sys
import numpy as np
from scipy.ndimage import binary_dilation
import funnel_check as f

XC = 14.0
Z_GRID = np.arange(-2.0, 16.0, 0.15)
PHI_GRID = np.radians(np.arange(-30, 30.01, 1.5))
S = np.linspace(-0.5, 0.5, 9)
R3 = np.array([-0.5, 0.0, 0.5])


def feasible_layer(HS, yc, d, t):
    Zc, Ph = np.meshgrid(Z_GRID, PHI_GRID, indexing='ij')
    vy, vz = np.cos(Ph), np.sin(Ph)
    wy, wz = -np.sin(Ph), np.cos(Ph)
    ok = np.ones(Zc.shape, bool)
    pts_y = yc + d * S[None, None, :, None] * vy[:, :, None, None] + t * R3[None, None, None, :] * wy[:, :, None, None]
    pts_z = Zc[:, :, None, None] + d * S[None, None, :, None] * vz[:, :, None, None] + t * R3[None, None, None, :] * wz[:, :, None, None]
    n = pts_y.size
    P = np.stack([np.full(n, XC), pts_y.ravel(), pts_z.ravel()], 1)
    ins = f.inside(P, HS).reshape(pts_y.shape)
    return ins.all(axis=(2, 3))


def test(design, sh, d, t, infl=0.0, y_start=100.0, y_end=16.0, dy=1.0):
    cav, _ = design(*sh)
    HS = [f.half_spaces(p) for p in cav + f.fixed_cavities()]
    ys = np.arange(y_start, y_end - 1e-9, -dy)
    F = [feasible_layer(HS, y, d, t + infl) for y in ys]
    st = np.zeros((7, 5), bool)
    st[:] = True          # z ±0.45（3 マス）、φ ±3°（2 マス）
    # 上から：到達できる姿勢
    reach = [None] * len(ys)
    reach[0] = F[0]
    for k in range(1, len(ys)):
        reach[k] = F[k] & binary_dilation(reach[k - 1], structure=st)
    # 下から：出口まで行ける姿勢
    good = [None] * len(ys)
    good[-1] = F[-1]
    for k in range(len(ys) - 2, -1, -1):
        good[k] = F[k] & binary_dilation(good[k + 1], structure=st)
    n_in = F[0].sum()
    passed = bool(reach[-1].any())
    # 上から来て、下へ行けなくなる層（最後に到達できる y）
    last = max((k for k in range(len(ys)) if reach[k].any()), default=-1)
    stuck_y = None if passed else (ys[last] if last >= 0 else None)
    # 通れる入口姿勢の割合（入口で入れる姿勢のうち、出口まで行ける姿勢）
    frac = (good[0] & F[0]).sum() / max(n_in, 1)
    return dict(n_in=int(n_in), passed=passed, frac=frac, stuck_y=stuck_y)


if __name__ == "__main__":
    coins = [("1円", 20.0, 1.5), ("50円", 21.0, 1.7), ("100円", 22.6, 1.7), ("10円", 23.5, 1.5), ("500円", 26.5, 1.8)]
    shifts = [(0, 0, 0), (0.4, 0.4, 0.2), (-0.4, -0.4, -0.2)]
    which = sys.argv[1:] or ["old", "new"]
    for nm in which:
        dsg = {"old": f.old_design, "new": f.new_design}[nm]
        print(f"=== {nm.upper()} ===")
        for infl in (0.0, 0.2):
            for cn, d, t in coins:
                res = [test(dsg, sh, d, t, infl) for sh in shifts]
                worst = min(res, key=lambda r: (r['passed'], r['frac']))
                print(f"  厚み+{infl:.1f} {cn:5s} 通れる入口姿勢 {worst['frac'] * 100:5.1f}%  到達 {'OK' if all(r['passed'] for r in res) else 'NG(詰まる)'}"
                      f"  詰まる高さ y={worst['stuck_y']}", flush=True)
