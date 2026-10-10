// =============================================================================
// ユニット箱（A1 mini 版）：天板A・天板B・継ぎ板・脚
// =============================================================================
// 判別部（④＋①〜③）・基板室・スピーカーを 1 つにまとめ、先方の蓋の裏に M4 ×6 で留める。
// 設計書：docs/superpowers/specs/2026-10-08-unit-box-design.md
// 寸法の正：unit_box_dims.scad（ここに数字を書かない）
//
// 座標は実物座標（X 右・Y = −蓋の Y・Z 上・先方の蓋の裏 = 0）。蓋の座標の値は L2P() で直す。
//
// 出力（export_unit_box.py が呼ぶ）
//   -D 'part="plateA"' / "plateB" / "splice" / "legs"
//   -D print_pose=true  … 印刷の向き（天板・継ぎ板は上面を下に、脚は座を下に。原点に寄せる）
// =============================================================================
include <unit_box_dims.scad>

part       = "plateA";
print_pose = false;

e = 0.01;   // 面がぴったり重ならないための逃げ（Volumes を確かめること）

// --- 共通の部品 -------------------------------------------------------------------

// 天板の下に立つ M4 タッピング用のボス（④・基板室を受ける）
module m4_boss(p) {
    translate(L2P(p) + [0, 0, -ub_plate_t - ub_boss_h])
        cylinder(d = ub_boss_d, h = ub_boss_h + e);
}

// 下から開けて上面の手前で止める下穴（d は径。上面から keep だけ残す）
module blind_pilot(p, d, keep = ub_pilot_top) {
    translate(L2P(p) + [0, 0, -ub_plate_t - ub_boss_h - 1])
        cylinder(d = d, h = ub_plate_t + ub_boss_h + 1 - keep);
}

// 先方の蓋へ留める M4：貫通穴と、下面の六角ナットのくぼみ
module lid_m4(p) {
    translate(L2P(p) + [0, 0, -ub_plate_t - 1]) cylinder(d = ub_m4_hole, h = ub_plate_t + 2);
    translate(L2P(p) + [0, 0, -ub_plate_t - 1])
        cylinder(d = ub_nut_af / cos(30), h = ub_nut_top + ub_plate_t + 1, $fn = 6);
}

// 天板の平らな板（y は蓋の座標の [奥, 手前]）
module slab(yr) {
    translate([ub_x[0], -yr[1], -ub_plate_t])
        cube([ub_x[1] - ub_x[0], yr[1] - yr[0], ub_plate_t]);
}

// その天板に入る点だけを選ぶ（継ぎ目より奥か手前か）
function on_plate(ps, yr) = [for (p = ps) if (p[1] > yr[0] && p[1] < yr[1]) p];

// --- 天板A ----------------------------------------------------------------------

// スリットのすり鉢：下面 ub_slot_bot から上面 ub_slot_top へ広げる
module slot_funnel() {
    c = L2P(ub_slot_c);
    hull() {
        translate(c + [-ub_slot_bot[0] / 2, -ub_slot_bot[1] / 2, -ub_plate_t - 1])
            cube([ub_slot_bot[0], ub_slot_bot[1], 1 + e]);
        translate(c + [-ub_slot_top[0] / 2, -ub_slot_top[1] / 2, -e])
            cube([ub_slot_top[0], ub_slot_top[1], 1]);
    }
}

function spk_holes() = [for (sx = [-1, 1], sy = [-1, 1])
    ub_spk_c + [sx * ub_spk_hole_half, sy * ub_spk_hole_half]];

module plateA() {
    difference() {
        union() {
            slab(ub_a_y);
            for (p = ub_hang_boss) m4_boss(p);
            for (p = spk_holes())
                translate(L2P(p) + [0, 0, -ub_plate_t - ub_spk_boss_h])
                    cylinder(d = ub_spk_boss_d, h = ub_spk_boss_h + e);
        }
        slot_funnel();
        for (p = ub_hang_boss) blind_pilot(p, ub_m4_pilot);
        for (p = spk_holes()) blind_pilot(p, ub_spk_pilot);
        for (p = ub_snd) translate(L2P(p) + [0, 0, -ub_plate_t - 1])
            cylinder(d = ub_snd_d, h = ub_plate_t + 2, $fn = 16);
        for (p = on_plate(ub_lid_m4, ub_a_y)) lid_m4(p);
        for (p = on_plate(ub_splice_screw, ub_a_y)) blind_pilot(p, ub_m3_pilot, ub_top_keep);
        for (p = on_plate(ub_leg_holes, ub_a_y)) blind_pilot(p, ub_m3_pilot, ub_top_keep);
    }
}

// --- 天板B ----------------------------------------------------------------------
// 基板室を 90° 回して吊る。配線はボスの高さ（8mm）のすき間から基板室の奥の配線穴へ
module plateB() {
    difference() {
        union() {
            slab(ub_b_y);
            for (p = ub_bay_boss) m4_boss(p);
        }
        for (p = ub_bay_boss) blind_pilot(p, ub_m4_pilot);
        for (p = on_plate(ub_lid_m4, ub_b_y)) lid_m4(p);
        for (p = on_plate(ub_splice_screw, ub_b_y)) blind_pilot(p, ub_m3_pilot, ub_top_keep);
        for (p = on_plate(ub_leg_holes, ub_b_y)) blind_pilot(p, ub_m3_pilot, ub_top_keep);
    }
}

// --- 継ぎ板 ---------------------------------------------------------------------
// 天板A・B の継ぎ目の下に当て、M3×8 タッピングで両方に留める（左右 2 枚）。
// スピーカー・基板室のつばとボスを避けた位置（設計書第 6 章）
module splice_one(r) {
    difference() {
        translate([r[0], -r[3], -ub_plate_t - ub_splice_t])
            cube([r[2] - r[0], r[3] - r[1], ub_splice_t]);
        for (p = ub_splice_screw)
            if (p[0] > r[0] && p[0] < r[2])
                translate(L2P(p) + [0, 0, -ub_plate_t - ub_splice_t - 1])
                    cylinder(d = ub_m3_clear, h = ub_splice_t + 2);
    }
}

module splice() { for (r = ub_splice) splice_one(r); }

// --- 脚（同じ形 ×4） -----------------------------------------------------------
// 柱 14 角 × 135、上に座 14 × 40 × 4（天板の下面に当てる）、座の両わきに三角の補強。
// 座の穴 2 つから M3×8 タッピングで天板に留める。外せる
// ローカル座標：柱の角が原点、上面 z = 0、座は +y へのびる
module leg_local() {
    s = ub_leg_sq;
    difference() {
        union() {
            translate([0, 0, -ub_leg_h]) cube([s, s, ub_leg_h]);
            translate([0, 0, -ub_leg_pad[2]]) cube([ub_leg_pad[0], ub_leg_pad[1], ub_leg_pad[2]]);
            for (gx = [0, s - ub_leg_gus_t])
                translate([gx, 0, 0]) rotate([90, 0, 90])
                    linear_extrude(ub_leg_gus_t) polygon(ub_leg_gus);
        }
        for (hs = ub_leg_hole_s)
            translate([s / 2, s / 2 + hs, -ub_leg_pad[2] - 1])
                cylinder(d = ub_m3_clear, h = ub_leg_pad[2] + 2);
    }
}

// c：柱の中心（蓋の座標）、dir：座の向き（蓋の座標）
module leg_place(c, dir) {
    dr  = [dir[0], -dir[1]];
    ang = atan2(dr[1], dr[0]) - 90;
    translate([c[0], -c[1], -ub_plate_t]) rotate([0, 0, ang])
        translate([-ub_leg_sq / 2, -ub_leg_sq / 2, 0]) leg_local();
}

module legs() { for (l = ub_legs) leg_place(l[0], l[1]); }

// --- 出力 -------------------------------------------------------------------------
module place_print(yr) {
    // 上面（Z 0）を下にして、左奥の角を原点へ
    translate([-ub_x[0], -yr[0], 0]) rotate([180, 0, 0]) children();
}

if (part == "plateA") {
    if (print_pose) place_print(ub_a_y) plateA(); else plateA();
}
if (part == "plateB") {
    if (print_pose) place_print(ub_b_y) plateB(); else plateB();
}
if (part == "splice") {
    if (print_pose) {
        // 天板に当たる面（Z −5）を下にして、左右を X に 10mm あけて並べる
        for (i = [0 : len(ub_splice) - 1]) {
            r = ub_splice[i];
            translate([i * (ub_splice[0][2] - ub_splice[0][0] + 10), 0, 0])
                translate([-r[0], -r[1], -ub_plate_t]) rotate([180, 0, 0]) splice_one(r);
        }
    } else splice();
}
if (part == "legs") {
    if (print_pose) {
        // 座（z = 0 の面）を下にする。4 本を X に 25mm おきに並べる（全体 89 × 40 × 135）
        for (i = [0 : 3])
            translate([i * 25, ub_leg_pad[1], 0]) rotate([180, 0, 0]) leg_local();
    } else legs();
}
if (part == "leg1") translate([0, ub_leg_pad[1], 0]) rotate([180, 0, 0]) leg_local();
