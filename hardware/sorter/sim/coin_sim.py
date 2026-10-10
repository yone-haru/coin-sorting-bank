# -*- coding: utf-8 -*-
"""
判別レールの物理シミュレーション（MuJoCo）  2026-09-27

寸法は ../selfsort_params.scad（唯一の正）から読む。形は 判別レール.scad と同じ箱の組み合わせで作る。

  python coin_sim.py check              今の寸法で 6 金種を 1 回ずつ転がして結果を表示
  python coin_sim.py sweep [--quick]    勾配・傾き・摩擦・はね返り・印刷誤差を振って判別率を出す
  python coin_sim.py video [out.mp4]    6 金種を順に転がす動画

座標（レール座標・mm）：x = レールに沿う向き（下り）、y = 壁に沿って上、z = 壁の法線（硬貨側が +z）
  壁の板は z = 0..plate_t。床リブの面が y = 0。窓は板を貫通する穴。
世界座標（m）：Z が上。レールを「下り alpha・壁の傾き beta」で置き、重力は (0, 0, -9.81)
"""
import argparse
import json
import math
import os
import re
import sys
import time

import numpy as np
import mujoco

HERE = os.path.dirname(os.path.abspath(__file__))
PARAMS = os.path.join(HERE, "..", "selfsort_params.scad")

# 硬貨の質量 [g]（造幣局の公表値）
MASS_G = {"1": 1.0, "5": 3.75, "10": 4.5, "50": 4.0, "100": 4.8, "500": 7.1}
LANE_NAMES = ["W1", "W2", "W3", "END"]


# ---------------------------------------------------------------------------
# 寸法の読み込み
def load_params(path=PARAMS):
    s = open(path, encoding="utf-8").read()
    s = re.sub(r"//[^\n]*", "", s)
    P = {}
    for m in re.finditer(r"^\s*(\w+)\s*=\s*(-?[\d.]+)\s*;", s, re.M):
        P[m.group(1)] = float(m.group(2))
    cb = re.search(r"coins\s*=\s*\[(.*?)\];", s, re.S).group(1)
    P["coins"] = [(m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4)))
                  for m in re.finditer(r'\["(\w+)",\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)\]', cb)]
    wb = re.search(r"windows\s*=\s*\[(.*?)\];", s, re.S).group(1)
    P["windows"] = [[float(m.group(1)), float(m.group(2)), float(m.group(3))]
                    for m in re.finditer(r'\["[^"]*",\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)\]', wb)]
    hb = re.search(r"hole_beam_x\s*=\s*\[([^\]]*)\]", s).group(1)
    P["hole_beam_x"] = [float(v) for v in hb.split(",")]
    return P


def default_design(P):
    return dict(
        alpha=P.get("rail_alpha", P["test_alpha"]), beta=P.get("rail_beta", P["test_beta"]),
        windows=[list(w) for w in P["windows"]], win_comp=P["win_comp"], bevel=P.get("jamb_bevel", 0.0),
        plate_t=P["plate_t"], plate_y0=P["plate_y0"], plate_y1=P["plate_y1"], plate_len=P["plate_len"],
        rib_t=P["rib_t"], floor_w=P["floor_w"], land_len=P["land_len"],
        bridge=(P["land_len"], P["land_len"] + P["bridge_len"]), bridge_gap=P["bridge_gap"],
        bridge_t=P["bridge_t"], bridge_y1=P["bridge_y1"],
        gate_gap=P.get("gate_gap", 2.6), gate_y0=P["plate_y1"] - 4, gate_top=P["plate_y1"] + 10,
        land_front=True,        # 着地場所の手前にも板（橋と同じすき間）を付ける
        curb_h=P.get("curb_h", 0.0),   # 窓の下の縁石の高さ [mm]
        guard=True,             # 橋より下流の手前の板（前板）
        guard_y=(6.0, 14.0),    # （旧：柵の高さの範囲）
        guard_y1=P.get("guard_y1", 20.0),
        guard_gap=P.get("guard_gap", 4.5),
        pad=P.get("pad_t", 0.0) > 0,   # 着地場所の床のフェルト（pad_t > 0 のとき）
        mu=0.3,                 # 硬貨と PLA の摩擦係数
        damp=0.6,               # 接触の減衰比（小さいほど跳ねる）
        tol=0.0,                # 窓の高さの印刷誤差 [mm]（+ で大きく出る）
        hole_beam_x=P["hole_beam_x"], hole_beam_y=P["hole_beam_y"],
    )


def rail_rotation(alpha_deg, beta_deg):
    """レール座標 → 世界座標の回転行列（列がレールの x, y, z 軸）"""
    a, b = math.radians(alpha_deg), math.radians(beta_deg)
    x = [math.cos(a), 0.0, -math.sin(a)]
    y = [math.cos(b) * math.sin(a), math.sin(b), math.cos(b) * math.cos(a)]
    z = [math.sin(b) * math.sin(a), -math.cos(b), math.sin(b) * math.cos(a)]
    return np.array([x, y, z]).T


def mat2quat(M):
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, M.flatten())
    return q


# ---------------------------------------------------------------------------
# モデル（MJCF）を作る
def build_xml(D, coins, dt=0.0002, visual=False):
    """coins: [(name, dia, thick), ...]。硬貨は 1 枚ずつ自由物体。"""
    mm = 0.001
    t = D["plate_t"]
    y1 = D["plate_y1"]
    L = D["plate_len"]
    geoms, meshes = [], []
    dark = "0.18 0.18 0.2 1"
    tc = max(0.001, 5 * dt)      # 接触の時定数（床もフェルトも同じ硬さ。フェルトは減衰だけ大きい）

    def box(x0, x1, ya, yb, z0, z1, rgba=dark):
        c = [(x0 + x1) / 2 * mm, (ya + yb) / 2 * mm, (z0 + z1) / 2 * mm]
        h = [abs(x1 - x0) / 2 * mm, abs(yb - ya) / 2 * mm, abs(z1 - z0) / 2 * mm]
        geoms.append(f'<geom type="box" pos="{c[0]:.6f} {c[1]:.6f} {c[2]:.6f}" '
                     f'size="{h[0]:.6f} {h[1]:.6f} {h[2]:.6f}" rgba="{rgba}"/>')

    def wedge(a, bev, ya, yb):
        # 窓の下流の縁の面取り：z=t で x=a、z=0 で x=a+bev の斜面。三角柱
        n = f"w{len(meshes)}"
        pts = []
        for yy in (ya, yb):
            pts += [(a, yy, t), (a + bev, yy, t), (a + bev, yy, 0.0)]
        v = " ".join(f"{p[0]*mm:.6f} {p[1]*mm:.6f} {p[2]*mm:.6f}" for p in pts)
        meshes.append(f'<mesh name="{n}" vertex="{v}"/>')
        geoms.append(f'<geom type="mesh" mesh="{n}" rgba="{dark}"/>')

    # 床より下の板の帯
    box(0, L, D["plate_y0"], 0, 0, t)
    xs = 0.0
    for wx, wl, wh in D["windows"]:
        H = wh + D["win_comp"] + D["tol"]
        a = wx + wl                         # 窓の下流の縁（硬貨側の面での位置）
        bb = max(D["bevel"], 0.0)           # 裏側の面取り（落ちる硬貨を裏へ導く）
        cf = D.get("lead_in", 0.0)          # 硬貨側の角の面取り（入りかけた硬貨の前の縁を壁の面へ戻す）
        X = max(bb, cf) + 1.0
        ch = D["curb_h"]
        if wx > xs:
            box(xs, wx, 0, y1, 0, t)                      # 窓の手前の壁
        box(wx, a + X, H, y1, 0, t)                       # 窓の上（縁の上も）
        if ch > 0:
            cc = min(D.get("curb_ch", 0.0), ch - 0.2)     # 縁石の上の角（硬貨側）の面取り
            if cc > 0:
                # y-z 断面：(0,0)-(0,t)-(ch-cc,t)-(ch,t-cc)-(ch,0) を x 方向に押し出す
                n_ = f"w{len(meshes)}"
                sec = [(0.0, 0.0), (0.0, t), (ch - cc, t), (ch, t - cc), (ch, 0.0)]
                pts = [(xx, yy, zz) for xx in (wx, a + X) for (yy, zz) in sec]
                v_ = " ".join(f"{q[0]*mm:.6f} {q[1]*mm:.6f} {q[2]*mm:.6f}" for q in pts)
                meshes.append(f'<mesh name="{n_}" vertex="{v_}"/>')
                geoms.append(f'<geom type="mesh" mesh="{n_}" rgba="{dark}"/>')
            else:
                box(wx, a + X, 0, ch, 0, t)               # 窓の下の縁石（縁の下も）
        # 下流の縁：x-z 断面の多角形を y 方向に押し出す
        prof = [(a + cf, t)] + ([(a, t - cf)] if cf > 0 else []) + [(a + bb, 0.0), (a + X, 0.0), (a + X, t)]
        n_ = f"w{len(meshes)}"
        pts = [(px_, yy, pz_) for yy in (ch, H) for (px_, pz_) in prof]
        v_ = " ".join(f"{q[0]*mm:.6f} {q[1]*mm:.6f} {q[2]*mm:.6f}" for q in pts)
        meshes.append(f'<mesh name="{n_}" vertex="{v_}"/>')
        geoms.append(f'<geom type="mesh" mesh="{n_}" rgba="{dark}"/>')
        xs = a + X
    box(xs, L, 0, y1, 0, t)
    # 溝の幅（壁の面から手前の板まで）。chan_gap を指定すると着地・橋・柵を全部そろえる
    g = D.get("chan_gap") or D["bridge_gap"]
    gg = D.get("chan_gap") or D["guard_gap"]
    # 着地場所：壁を関門の上まで伸ばす（じょうごの奥の壁）
    box(0, D["land_len"], y1, D["gate_top"], 0, t)
    # 上流の端の壁
    box(-2, 0, -D["rib_t"], D["gate_top"], 0, t + max(g, D["floor_w"]) + 2)
    # 床リブ。pad=True なら着地場所の床だけ「跳ねない」材料（フェルト等）にする
    if D.get("pad"):
        c = [D["land_len"] / 2 * mm, -D["rib_t"] / 2 * mm, (t + D["floor_w"] / 2) * mm]
        geoms.append(f'<geom type="box" pos="{c[0]:.6f} {c[1]:.6f} {c[2]:.6f}" '
                     f'size="{D["land_len"]/2*mm:.6f} {D["rib_t"]/2*mm:.6f} {D["floor_w"]/2*mm:.6f}" '
                     f'rgba="0.3 0.5 0.3 1" solref="{tc} {D.get("pad_damp", 2.0)}" friction="0.6 0.001 0"/>')
        box(D["land_len"], L, -D["rib_t"], 0, t, t + D["floor_w"])
    else:
        box(0, L, -D["rib_t"], 0, t, t + D["floor_w"])
    # 橋（穴センサー）
    bx0, bx1 = D["bridge"]
    if g > D["floor_w"]:
        box(bx0, bx1, -D["rib_t"], 0, t + D["floor_w"], t + g)
    box(bx0, bx1, D["bridge_y1"] - 3, D["bridge_y1"], t, t + g)
    box(bx0, bx1, -D["rib_t"], D["bridge_y1"], t + g, t + g + D["bridge_t"])
    # 関門の手前の板（すき間 gate_gap）と、着地場所の手前の板（橋と同じすき間）
    box(0, D["land_len"], D["gate_y0"], D["gate_top"], t + D["gate_gap"], t + D["gate_gap"] + 2,
        rgba="0.95 0.6 0.2 0.5")
    if D["land_front"]:
        box(0, bx0, -D["rib_t"], D["gate_y0"], t + g, t + g + 2, rgba="0.95 0.6 0.2 0.2")
    if D["guard"]:
        gy1 = D.get("guard_y1") or D["guard_y"][1]
        gy0 = -D["rib_t"] if D.get("guard_y1") else D["guard_y"][0]
        box(bx1, L, gy0, gy1, t + gg, t + gg + 2, rgba="0.4 0.7 0.9 0.22")

    R = rail_rotation(D["alpha"], D["beta"])
    q = mat2quat(R)
    mu = D["mu"]
    tc = max(0.001, 5 * dt)
    colors = {"1": "0.85 0.85 0.88 1", "5": "0.85 0.7 0.3 1", "10": "0.72 0.42 0.25 1",
              "50": "0.88 0.88 0.9 1", "100": "0.8 0.8 0.82 1", "500": "0.9 0.78 0.4 1"}
    bodies = []
    for i, (nm, dia, th) in enumerate(coins):
        bodies.append(
            f'<body name="c{i}" pos="0 0 {1 + i*0.1}" quat="{q[0]} {q[1]} {q[2]} {q[3]}">'
            f'<freejoint/><geom name="coin{i}" type="cylinder" size="{dia/2*mm:.6f} {th/2*mm:.6f}" '
            f'mass="{MASS_G[nm]/1000:.6f}" rgba="{colors.get(nm, "0.8 0.8 0.8 1")}"/></body>')

    xml = f"""
<mujoco model="rail">
  <option timestep="{dt}" gravity="0 0 -9.81" cone="elliptic" impratio="10" integrator="implicitfast">
    <flag multiccd="enable"/>
  </option>
  <default>
    <geom friction="{mu} 0.0005 0" condim="4" solref="{tc} {D['damp']}" solimp="0.95 0.99 0.0001 0.5 2" margin="0"/>
  </default>
  <visual><global offwidth="1920" offheight="1080"/><quality shadowsize="4096"/>
    <headlight ambient="0.45 0.45 0.45" diffuse="0.6 0.6 0.6"/></visual>
  <asset>{''.join(meshes)}
    <texture type="skybox" builtin="gradient" rgb1="0.75 0.85 0.95" rgb2="1 1 1" width="256" height="256"/>
    <texture name="grid" type="2d" builtin="checker" rgb1="0.93 0.93 0.93" rgb2="0.86 0.86 0.86" width="256" height="256"/>
    <material name="grid" texture="grid" texrepeat="40 40"/>
  </asset>
  <worldbody>
    <light pos="0 -0.3 0.4" dir="0 0.5 -1" diffuse="0.5 0.5 0.5"/>
    {'<geom type="plane" pos="0 0 -0.08" size="0.4 0.4 0.01" material="grid" contype="0" conaffinity="0"/>' if visual else ''}
    <body name="rail" quat="{q[0]} {q[1]} {q[2]} {q[3]}">
      {''.join(geoms)}
    </body>
    {''.join(bodies)}
  </worldbody>
</mujoco>"""
    return xml, R


# ---------------------------------------------------------------------------
def expected_lane(D, dia):
    for i, (wx, wl, wh) in enumerate(D["windows"]):
        if dia < wh + D["win_comp"]:
            return i
    return len(D["windows"])


def lane_of_x(D, x):
    """壁の板を通り抜けた瞬間の硬貨の中心 x（レール座標）がどの窓か。
    （2026-09-27 修正：以前は下流へ 25mm の余裕を見ていたため、窓の間が 4mm しかないと
      W2 で落ちた硬貨を W1 と数えていた）"""
    for i, (wx, wl, wh) in enumerate(D["windows"]):
        if wx - 3 <= x <= wx + wl + max(D["bevel"], 0) + 3:
            return i
    return -1


def set_coin(model, data, i, R, p_rail, v_world, w_rail=(0, 0, 0), tilt=(0, 0)):
    """硬貨 i をレール座標 p_rail [mm] に置く。v_world [m/s]、w_rail は硬貨の角速度（レール座標 rad/s）"""
    jadr = model.jnt_qposadr[model.body_jntadr[model.body(f"c{i}").id]]
    vadr = model.jnt_dofadr[model.body_jntadr[model.body(f"c{i}").id]]
    pw = R @ (np.asarray(p_rail) * 0.001)
    # 硬貨の姿勢：レールの向き × 小さな傾き（x 軸まわり・y 軸まわり）
    ax, ay = math.radians(tilt[0]), math.radians(tilt[1])
    Rx = np.array([[1, 0, 0], [0, math.cos(ax), -math.sin(ax)], [0, math.sin(ax), math.cos(ax)]])
    Ry = np.array([[math.cos(ay), 0, math.sin(ay)], [0, 1, 0], [-math.sin(ay), 0, math.cos(ay)]])
    q = mat2quat(R @ Rx @ Ry)
    data.qpos[jadr:jadr + 3] = pw
    data.qpos[jadr + 3:jadr + 7] = q
    data.qvel[vadr:vadr + 3] = v_world
    # freejoint の角速度は物体座標
    data.qvel[vadr + 3:vadr + 6] = np.asarray(w_rail)


def coin_state(model, data, i, R):
    bid = model.body(f"c{i}").id
    p = R.T @ data.xpos[bid] * 1000.0            # レール座標 mm
    v = R.T @ data.cvel[bid][3:] if False else None
    jv = model.jnt_dofadr[model.body_jntadr[bid]]
    vw = data.qvel[jv:jv + 3]
    axis = R.T @ data.xmat[bid].reshape(3, 3)[:, 2]  # 硬貨の軸（レール座標）
    return p, np.linalg.norm(vw), axis


def probe_hits(model, data, R, probes):
    """probes: {名前: (p0, p1)}（レール座標 mm の線分）。硬貨が線分を遮っていれば True"""
    out = {}
    geomid = np.zeros(1, dtype=np.int32)
    for k, (p0, p1) in probes.items():
        a = R @ (np.asarray(p0) * 0.001)
        v = R @ ((np.asarray(p1) - np.asarray(p0)) * 0.001)
        x = mujoco.mj_ray(model, data, a, v, None, 0, -1, geomid)
        out[k] = (0 <= x <= 1)
    return out


def run_one(D, coin, seed=0, t_max=3.0, dt=0.0002, record=None, probes=None):
    """硬貨 1 枚を関門の下から落として、どこへ行ったかを返す"""
    nm, dia, th, hole = coin
    rng = np.random.default_rng(seed)
    xml, R = build_xml(D, [(nm, dia, th)], dt=dt)
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    r = dia / 2
    x0 = D["land_len"] / 2 + rng.uniform(-0.4, 0.4)
    p0 = [x0, D["gate_y0"] + r + rng.uniform(0, 3), D["plate_t"] + th / 2 + rng.uniform(0.1, 0.8)]
    v_down = rng.uniform(0.8, 1.3)                                   # 蓋のスリットからの落下
    v_world = np.array([0, 0, -v_down]) + R @ np.array([rng.uniform(-0.03, 0.12), 0, 0])
    w = rng.normal(0, 5, 3)
    set_coin(model, data, 0, R, p0, v_world, w_rail=w, tilt=(rng.normal(0, 2), rng.normal(0, 2)))
    mujoco.mj_forward(model, data)

    exp = expected_lane(D, dia)
    beams = {bx: None for bx in D["hole_beam_x"]}
    x_cross = None
    z_prev = 99.0
    blocked = {k: [] for k in (probes or {})}   # 遮られた区間 [(開始, 終了), ...]
    prev = {k: False for k in (probes or {})}
    slow_t = 0.0
    landed_t = None
    y_hist = []
    n_steps = int(t_max / dt)
    out = "TIMEOUT"
    x_exit = None
    t_exit = None
    vmax = 0.0
    for k in range(n_steps):
        mujoco.mj_step(model, data)
        if k % 5:
            continue
        tt = data.time
        p, sp, axis = coin_state(model, data, 0, R)
        vmax = max(vmax, sp)
        if probes:
            for kk, hit in probe_hits(model, data, R, probes).items():
                if hit and not prev[kk]:
                    blocked[kk].append([tt, tt])
                elif hit:
                    blocked[kk][-1][1] = tt
                prev[kk] = hit
        if record is not None and k % 50 == 0:
            record.append((tt, *p, sp))
        # 床に立ったか（中心の高さ ≒ 半径）
        if landed_t is None and abs(p[1] - r) < 0.6 and p[2] < D["plate_t"] + (D.get("chan_gap") or D["bridge_gap"]):
            landed_t = tt
        # 穴センサーのビームの位置を通ったときの中心の高さ（穴に光が通るか）
        for bx in beams:
            if beams[bx] is None and p[0] >= bx:
                beams[bx] = (p[1] - r, abs(axis[2]))
        # 板の厚みの真ん中を奥へ通り抜けた瞬間の x（どの窓を通ったか）
        if p[2] < D["plate_t"] / 2 <= z_prev:
            x_cross = p[0]
        z_prev = p[2]
        # 窓から抜けた（壁の裏へ倒れきった／板より下へ落ちた）
        if (p[2] < -0.5 * r and p[1] < D["plate_y1"]) or (p[2] < 0 and p[1] < D["plate_y0"]):
            out = "LANE"
            x_exit = x_cross if x_cross is not None else p[0]
            t_exit = tt
            break
        # どこかへ飛んだ
        if abs(p[2]) > 60 or p[1] < -80 or p[1] > 120 or p[0] < -30:
            out = "LOST"
            x_exit = p[0]
            break
        # 終端から出た（500円レーン）
        if p[0] > D["plate_len"] + 3:
            out = "END"
            x_exit = p[0]
            t_exit = tt
            break
        # 手前に落ちた
        if p[2] > D["plate_t"] + D["floor_w"] + r and p[1] < 0:
            out = "FRONT"
            x_exit = p[0]
            break
        # 止まった
        if tt > 0.25 and sp < 0.01:
            slow_t += dt * 5
            if slow_t > 0.4:
                out = "STALL"
                x_exit = p[0]
                break
        else:
            slow_t = 0.0
    # 抜けたあとも少し続けて、センサーの光を遮るかを記録する
    if probes and out in ("LANE", "END"):
        t_end = data.time + 0.3
        k = 0
        while data.time < t_end:
            mujoco.mj_step(model, data)
            k += 1
            if k % 5:
                continue
            tt = data.time
            for kk, hit in probe_hits(model, data, R, probes).items():
                if hit and not prev[kk]:
                    blocked[kk].append([tt, tt])
                elif hit:
                    blocked[kk][-1][1] = tt
                prev[kk] = hit
    if out == "LANE":
        lane = lane_of_x(D, x_exit)
    elif out == "END":
        lane = len(D["windows"])
    else:
        lane = -1
    ok = (lane == exp)
    # 穴センサー：中心の高さのずれ（床から浮いていると穴がビームから外れる）
    beam_dev = [None if v is None else round(float(v[0]), 3) for v in beams.values()]
    return dict(coin=nm, dia=dia, out=out, lane=lane, expected=exp, ok=bool(ok),
                x_exit=None if x_exit is None else round(float(x_exit), 1),
                t_exit=None if t_exit is None else round(float(t_exit), 3),
                vmax=round(float(vmax), 3), landed=None if landed_t is None else round(landed_t, 3),
                beam_dev=beam_dev,
                probes={k: [(round(a, 4), round(b, 4)) for a, b in v] for k, v in blocked.items()})


# ---------------------------------------------------------------------------
def cmd_check(args):
    P = load_params()
    D = default_design(P)
    for k, v in (args.set or []):
        D[k] = float(v)
    print(f"alpha={D['alpha']} beta={D['beta']} mu={D['mu']} damp={D['damp']} tol={D['tol']}")
    for c in P["coins"]:
        for s in range(args.n):
            t0 = time.time()
            r = run_one(D, c, seed=s)
            print(f"  {c[0]:>3}円  → {r['out']:<7} lane={LANE_NAMES[r['lane']] if r['lane']>=0 else '-':<4} "
                  f"期待={LANE_NAMES[r['expected']]:<4} {'OK ' if r['ok'] else 'NG '} "
                  f"x={r['x_exit']} t={r['t_exit']} vmax={r['vmax']} 着地={r['landed']} 穴ビーム高さずれ={r['beam_dev']}"
                  f"  ({time.time()-t0:.1f}s)")


def cmd_video(D, out_path, coins, seed=1, fps=30, slow=0.5, size=(1280, 720), gap_s=1.4):
    """6 金種を順に関門から落とし、レールを転がる様子を動画にする（ffmpeg が必要）"""
    import subprocess
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(r"C:\Windows\Fonts\YuGothB.ttc", 30)
    font_s = ImageFont.truetype(r"C:\Windows\Fonts\YuGothM.ttc", 22)
    rng = np.random.default_rng(seed)
    specs = [(c[0], c[1], c[2]) for c in coins]
    xml, R = build_xml(D, specs, visual=True)
    xml = xml.replace("<freejoint/>", "<freejoint/>").replace('<body name="c', '<body gravcomp="1" name="c')
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    W_, H_ = size
    renderer = mujoco.Renderer(model, height=H_, width=W_)
    cam = mujoco.MjvCamera()
    n = R[:, 2]
    fwd = -n
    el = math.degrees(math.asin(fwd[2])) - 22
    az = math.degrees(math.atan2(fwd[1], fwd[0])) - 10
    cam.azimuth, cam.elevation, cam.distance = az, el, 0.21
    cam.lookat[:] = R @ (np.array([D["plate_len"] * 0.5, 14, 3]) * 0.001) + np.array([0, 0, -0.012])
    park = lambda i: np.array([2.0 + 0.2 * i, 2.0, 2.0])
    bids = [model.body(f"c{i}").id for i in range(len(specs))]
    for i in range(len(specs)):
        ja = model.jnt_qposadr[model.body_jntadr[bids[i]]]
        data.qpos[ja:ja + 3] = park(i)
    mujoco.mj_forward(model, data)
    state = ["wait"] * len(specs)
    result = [""] * len(specs)
    t_rel = [gap_s * i + 0.2 for i in range(len(specs))]
    T = t_rel[-1] + 2.2
    dt = model.opt.timestep
    frame_dt = slow / fps
    next_frame = 0.0
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{W_}x{H_}", "-r", str(fps), "-i", "-", "-pix_fmt", "yuv420p",
                           "-vcodec", "libx264", "-crf", "20", out_path], stdin=subprocess.PIPE)
    labels = ["W1", "W2", "W3", "終端"]
    while data.time < T:
        for i, (nm, dia, th) in enumerate(specs):
            if state[i] == "wait" and data.time >= t_rel[i]:
                r = dia / 2
                p0 = [D["land_len"] / 2, D["gate_y0"] + r + 1, D["plate_t"] + th / 2 + 0.3]
                v_world = np.array([0, 0, -rng.uniform(0.9, 1.2)])
                set_coin(model, data, i, R, p0, v_world, w_rail=rng.normal(0, 3, 3))
                model.body_gravcomp[bids[i]] = 0.0
                state[i] = "run"
            elif state[i] == "run":
                p = R.T @ data.xpos[bids[i]] * 1000
                r = dia / 2
                gone = None
                if (p[2] < -0.5 * r and p[1] < D["plate_y1"]) or p[1] < D["plate_y0"] - 10:
                    gone = lane_of_x(D, p[0])
                elif p[0] > D["plate_len"] + 3:
                    gone = len(D["windows"])
                if gone is not None:
                    exp = expected_lane(D, dia)
                    result[i] = f"{nm}円 → {labels[gone] if gone >= 0 else '?'}  {'○' if gone == exp else '×'}"
                    state[i] = "fall"
                    t_rel[i] = data.time
            elif state[i] == "fall" and data.time - t_rel[i] > 0.35:
                ja = model.jnt_qposadr[model.body_jntadr[bids[i]]]
                va = model.jnt_dofadr[model.body_jntadr[bids[i]]]
                data.qpos[ja:ja + 3] = park(i)
                data.qvel[va:va + 6] = 0
                model.body_gravcomp[bids[i]] = 1.0
                state[i] = "done"
        mujoco.mj_step(model, data)
        if data.time >= next_frame:
            next_frame += frame_dt
            renderer.update_scene(data, camera=cam)
            img = Image.fromarray(renderer.render())
            dr = ImageDraw.Draw(img)
            dr.rectangle([0, 0, W_, 48], fill=(30, 45, 70))
            dr.text((16, 8), f"判別レール シミュレーション（下り {D['alpha']}°・壁の傾き {D['beta']}°・"
                             f"摩擦 {D['mu']}）  {slow:g} 倍速", font=font_s, fill=(255, 255, 255))
            n_res = sum(1 for s in result if s)
            if n_res:
                dr.rectangle([8, 56, 330, 64 + 40 * n_res], fill=(255, 255, 255))
            y = 60
            for i, s in enumerate(result):
                if s:
                    dr.text((16, y), s, font=font, fill=(20, 20, 20) if "○" in s else (200, 0, 0))
                    y += 40
            ff.stdin.write(np.asarray(img).tobytes())
    ff.stdin.close()
    ff.wait()
    return result


def _work(job):
    D, coin, seed = job
    try:
        return run_one(D, coin, seed=seed)
    except Exception as e:  # 1 回の失敗で全体を止めない
        return dict(coin=coin[0], out="ERROR:" + str(e)[:60], ok=False, lane=-1, expected=-1)


def sweep(grid, seeds, base=None, coins=None, procs=None):
    """grid: {キー: [値, ...]}。全組み合わせ × 金種 × seeds を回し、組み合わせごとに集計して返す"""
    import itertools
    from multiprocessing import Pool
    P = load_params()
    base = dict(base or {})
    coins = coins or P["coins"]
    keys = list(grid)
    combos = list(itertools.product(*[grid[k] for k in keys]))
    jobs, meta = [], []
    for ci, combo in enumerate(combos):
        D = default_design(P)
        D.update(base)
        for k, v in zip(keys, combo):
            D[k] = v
        for c in coins:
            for s in range(seeds):
                jobs.append((D, c, 1000 * ci + s))
                meta.append(ci)
    with Pool(procs or max(1, os.cpu_count() - 1)) as pool:
        res = pool.map(_work, jobs, chunksize=4)
    table = []
    for ci, combo in enumerate(combos):
        rs = [r for r, m in zip(res, meta) if m == ci]
        per = {}
        for r in rs:
            per.setdefault(r["coin"], []).append(r)
        row = dict(zip(keys, combo))
        row["rate"] = sum(r["ok"] for r in rs) / len(rs)
        row["per"] = {k: sum(x["ok"] for x in v) / len(v) for k, v in per.items()}
        fails = {}
        for r in rs:
            if not r["ok"]:
                key = f'{r["coin"]}:{r["out"]}' + (f'->{LANE_NAMES[r["lane"]]}' if r.get("lane", -1) >= 0 else "")
                fails[key] = fails.get(key, 0) + 1
        row["fails"] = fails
        texit = [r["t_exit"] for r in rs if r.get("t_exit")]
        row["t_max"] = max(texit) if texit else None
        vm = [r["vmax"] for r in rs if r.get("vmax")]
        row["vmax"] = max(vm) if vm else None
        bd = [abs(b) for r in rs for b in (r.get("beam_dev") or []) if b is not None]
        row["beam_dev_max"] = round(max(bd), 2) if bd else None
        table.append(row)
    return table


def print_table(table, top=None):
    table = sorted(table, key=lambda r: -r["rate"])
    for r in table[:top]:
        head = " ".join(f"{k}={r[k]}" for k in r if k not in ("rate", "per", "fails", "t_max", "vmax", "beam_dev_max"))
        per = " ".join(f"{k}:{v*100:.0f}" for k, v in r["per"].items())
        print(f"{r['rate']*100:5.1f}%  {head}  | {per} | tmax={r['t_max']} vmax={r['vmax']} beam={r['beam_dev_max']}"
              + (f"  NG {r['fails']}" if r["fails"] else ""))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("check")
    c.add_argument("-n", type=int, default=1)
    c.add_argument("--set", nargs=2, action="append", metavar=("KEY", "VALUE"))
    s = sub.add_parser("sweep")
    s.add_argument("grid", help='JSON 例: {"alpha":[8,10],"beta":[12,15]}')
    s.add_argument("--base", default="{}", help="全部に共通で上書きする値（JSON）")
    s.add_argument("--seeds", type=int, default=3)
    s.add_argument("--top", type=int, default=30)
    s.add_argument("--out", default=None, help="結果を JSON で保存")
    v = sub.add_parser("video")
    v.add_argument("out", nargs="?", default="rail_sim.mp4")
    v.add_argument("--design", default="{}", help="寸法の上書き（JSON）")
    v.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    if args.cmd == "video":
        P = load_params()
        D = default_design(P)
        D.update(json.loads(args.design))
        res = cmd_video(D, args.out, P["coins"], seed=args.seed)
        print("\n".join(res))
        return
    if args.cmd == "check":
        cmd_check(args)
    elif args.cmd == "sweep":
        t0 = time.time()
        table = sweep(json.loads(args.grid), args.seeds, base=json.loads(args.base))
        print_table(table, args.top)
        print(f"({len(table)} 通り・{time.time()-t0:.0f} 秒)")
        if args.out:
            json.dump(table, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
