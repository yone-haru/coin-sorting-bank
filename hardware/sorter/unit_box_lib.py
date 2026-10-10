# -*- coding: utf-8 -*-
"""ユニット箱の CAD 作業の共通部品。

座標は実物座標（X 右・Y = −蓋の Y・Z 上・先方の蓋の裏 = 0）。
寸法は unit_box_dims.scad が正。ここでは数を書き写さず、UBX 行から読む。
"""
import json
import os
import re
import subprocess
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree

OPENSCAD = os.environ.get("OPENSCAD", r"C:\openscad-2021.01\openscad.exe")
HERE = Path(__file__).resolve().parent            # 3Dプリント/自作判別部
ROOT3D = HERE.parent                              # 3Dプリント
BUILD = HERE / "unit_box_build"
BOX_SCAD = HERE / "ユニット箱.scad"
LID_SCAD = HERE / "lid.scad"
DEPS = [HERE / "unit_box_dims.scad", ROOT3D / "chassis_dims.scad"]


def run_openscad(scad, out, defines=None):
    """OpenSCAD で scad を out に書き出す。ログ（stdout + stderr）を返す"""
    cmd = [OPENSCAD, "-o", str(out)]
    for k, v in (defines or {}).items():
        cmd += ["-D", f"{k}={v}"]
    cmd.append(str(scad))
    r = subprocess.run(cmd, cwd=str(Path(scad).parent), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    log = r.stdout + r.stderr
    if r.returncode != 0:
        raise RuntimeError(f"OpenSCAD が失敗しました（{scad}）\n{log[-1500:]}")
    return log


def read_data():
    """unit_box_data.scad の UBX 行を {key: 値} にして返す"""
    BUILD.mkdir(exist_ok=True)
    log = run_openscad(HERE / "unit_box_data.scad", BUILD / "data.echo")
    text = (BUILD / "data.echo").read_text(encoding="utf-8", errors="replace") + log
    d = {}
    for line in text.splitlines():
        m = re.search(r'UBX (\S+) (.+?)"\s*$', line)
        if m:
            d[m.group(1)] = json.loads(m.group(2))
    if "x" not in d:
        raise RuntimeError("UBX 行が読めませんでした:\n" + text[-1500:])
    return d


def lid_to_real(p):
    p = list(p) + [0.0] * (3 - len(p))
    return np.array([p[0], -p[1], p[2]], dtype=float)


def _stale(out, deps):
    return (not out.exists()) or any(dp.stat().st_mtime > out.stat().st_mtime for dp in deps)


def load_sorter():
    """判別部（④＋①〜③の assembled）を、天板の厚さ 5mm だけ下げて返す"""
    BUILD.mkdir(exist_ok=True)
    out = BUILD / "sorter_assembled.stl"
    scad = HERE / "判別ユニット_本番.scad"
    if _stale(out, [scad, HERE / "selfsort_params.scad", ROOT3D / "chassis_dims.scad"]):
        run_openscad(scad, out, {"part": '"assembled"'})
    m = trimesh.load(str(out), force="mesh")
    m.apply_translation([0, 0, -read_data()["plate_t"]])
    return m


def load_bay():
    """基板室（筐体_基板室.scad の出力）を 90° 回して天板B の下に置く"""
    BUILD.mkdir(exist_ok=True)
    out = BUILD / "bay.stl"
    scad = ROOT3D / "筐体_基板室.scad"
    if _stale(out, [scad, ROOT3D / "chassis_dims.scad"]):
        run_openscad(scad, out)
    m = trimesh.load(str(out), force="mesh")
    m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 0, 1]))
    m.apply_translation(read_data()["bay_place"])
    return m


def speaker_dummy(d):
    """スピーカーの代わりの箱（前面が Z = −plate_t − spk_boss_h）"""
    top = -d["plate_t"] - d["spk_boss_h"]
    c = lid_to_real(d["spk_c"])
    c[2] = top - d["spk_depth"] / 2
    return trimesh.creation.box(extents=[d["spk_sq"], d["spk_sq"], d["spk_depth"]],
                                transform=trimesh.transformations.translation_matrix(c))


def load_part(part):
    """ユニット箱.scad の部品を実物座標で返す（ユニット箱.scad か寸法が新しければ出し直す）"""
    BUILD.mkdir(exist_ok=True)
    out = BUILD / f"{part}.stl"
    if _stale(out, [BOX_SCAD] + DEPS):
        run_openscad(BOX_SCAD, out, {"part": f'"{part}"', "print_pose": "false"})
    return trimesh.load(str(out), force="mesh")


def load_lid():
    """蓋（lid.scad。先方に渡す 3D データ）を実物座標で返す"""
    BUILD.mkdir(exist_ok=True)
    out = BUILD / "lid.stl"
    if _stale(out, [LID_SCAD] + DEPS):
        run_openscad(LID_SCAD, out, {"print_pose": "false"})
    return trimesh.load(str(out), force="mesh")


def overlap_volume(a, b):
    """a と b の重なりの体積（mm³）。面が接するだけなら 0 に近い"""
    try:
        inter = trimesh.boolean.intersection([a, b], engine="manifold")
    except Exception as e:  # 片方が閉じていないなど
        raise RuntimeError(f"重なりを計算できません: {e}")
    return float(inter.volume) if inter is not None and not inter.is_empty else 0.0


def min_gap(a, b, spacing=0.5):
    """a と b の面どうしの最短距離（mm）。点を撒いて近い候補を厳密に測り直す"""
    def one_way(p_mesh, q_mesh):
        n = int(min(400000, max(5000, p_mesh.area / spacing ** 2)))
        pts = np.vstack([p_mesh.vertices, p_mesh.sample(n)])
        qn = int(min(400000, max(5000, q_mesh.area / spacing ** 2)))
        qpts = np.vstack([q_mesh.vertices, q_mesh.sample(qn)])
        dist, _ = cKDTree(qpts).query(pts)
        idx = np.argsort(dist)[:300]
        _, exact, _ = q_mesh.nearest.on_surface(pts[idx])
        return float(exact.min())
    return min(one_way(a, b), one_way(b, a))
