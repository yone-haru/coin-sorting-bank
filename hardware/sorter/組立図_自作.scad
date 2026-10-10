// =============================================================================
// 組立図（自作判別部版・見るためだけ）  2026-09-27
// =============================================================================
// 蓋の裏（Z=0）にぶら下がる構成を 1 つにまとめた図。蓋の座標：X 右・Y 手前・Z 上（蓋の裏が 0）。
//   ・判別レール（rail.stl ＝ 判別レール.stl のコピー）は本物の形
//   ・じょうご（橙）／シュート＋レーンセンサー（水色）／吊り具（黄）は「試験で寸法が決まる前の案」
//   ・基板室（bay.stl）は今の設計のまま
// レールの姿勢（実物）：下り test_alpha で右（+X）へ下る。硬貨の面は手前を向き、壁は奥へ test_beta 傾く。
//   窓から倒れた硬貨は壁の奥側のシュートへ落ちる
// 画像：gen_組立図.py が視点ごとに書き出し、左右反転（蓋の座標が鏡の世界のため）と凡例を付ける
// =============================================================================
include <../chassis_dims.scad>
include <selfsort_params.scad>

explode = 0;
alpha = test_alpha;
beta  = test_beta;

// レール座標 → 蓋座標
function Rx(v) = [v[0], v[1] * sin(beta) - v[2] * cos(beta), v[1] * cos(beta) + v[2] * sin(beta)];
function Ry(v) = [v[0] * cos(alpha) + v[2] * sin(alpha), v[1], -v[0] * sin(alpha) + v[2] * cos(alpha)];
function Rot(v) = Ry(Rx(v));
gate_len   = 27.5;                                 // 関門の長さ（500円 26.5 が通る）
gate_gap   = 2.6;                                  // 1 枚ずつにする隙間
gate_top_y = plate_y1 + 10;                        // 関門の上端（レール座標の y）
gate_cx    = land_len / 2;                         // 関門の中心（着地場所の真上）
// 2026-09-27：スリットの右寄り（+8）だとシュートの端が X=356 で箱（内側 5〜345）からはみ出した。
//   関門をスリットの左端の真下（-20）へ寄せ、じょうごで斜めに送る → 右端 約 332
gate_world = [slot_c[0] - 20, slot_c[1] + 2, -48]; // 関門の上端の中心を置く蓋座標
P = gate_world - Rot([gate_cx, gate_top_y, plate_t + gate_gap / 2]);
// ★ 蓋の座標（X 右・Y 手前・Z 上）は右手系ではない（上から見た図の Y 下向きをそのまま使っているため）。
//   OpenSCAD の中では「鏡に映った世界」になる。本物のレール（判別レール.stl）をこの世界に置くには
//   鏡に映した形で置く必要がある → 関門を通る Y の面で鏡映しにする。
//   結果（実物）：硬貨の面が手前を向き、下りは右（+X）、窓から倒れた硬貨は壁の奥側へ落ちる。
//   画像は左右反転して実物の見え方に戻す（gen_組立図.py）
gy = gate_world[1];
function W(v) = let(p = P + Rot(v)) [p[0], 2 * gy - p[1], p[2]];
module pose() translate([0, 2 * gy, 0]) mirror([0, 1, 0]) translate(P) rotate([0, alpha, 0]) rotate([90 - beta, 0, 0]) children();

// ---------------------------------------------------------------------------
module lid() {
    color([0.9, 0.9, 0.9, 0.25]) difference() {
        cube([lid[0], lid[1], lid_t]);
        translate([slot_c[0] - slot_size[0] / 2, slot_c[1] - slot_size[1] / 2, -1]) cube([slot_size[0], slot_size[1], lid_t + 2]);
        translate([spk_c[0], spk_c[1], -1]) cylinder(d = spk_d, h = lid_t + 2);
        translate([pwr_c[0], pwr_c[1], -1]) cylinder(d = pwr_d, h = lid_t + 2);
    }
}

// 判別レール（本物）
module rail_part() { color([0.25, 0.25, 0.25]) pose() import("rail.stl"); }

// じょうご＋関門：蓋のスリット(40×6) → 関門(27.5×2.6)。関門の奥の壁はレールの壁の延長
module funnel() {
    t = 2;
    module top(o = 0) translate([slot_c[0] - slot_size[0] / 2 - o, slot_c[1] - slot_size[1] / 2 - o, -3]) cube([slot_size[0] + 2 * o, slot_size[1] + 2 * o, 3]);
    module gate(o = 0, dy = 0) pose() translate([gate_cx - gate_len / 2 - o, gate_top_y - dy, plate_t - o]) cube([gate_len + 2 * o, 0.1 + dy, gate_gap + 2 * o]);
    color([1.0, 0.6, 0.2, 0.75]) difference() {
        hull() { top(t); gate(t); }
        hull() { translate([0, 0, 1]) top(0); gate(0, 0.5); }
    }
    // 関門：スリットから床の少し上まで（奥の壁＝レールの壁の延長、手前の板）
    color([1.0, 0.6, 0.2, 0.75]) pose() {
        translate([gate_cx - gate_len / 2 - t, plate_y1, 0]) cube([gate_len + 2 * t, gate_top_y - plate_y1, plate_t]);          // 奥の壁
        translate([gate_cx - gate_len / 2 - t, plate_y1 - 4, plate_t + gate_gap]) cube([gate_len + 2 * t, gate_top_y - plate_y1 + 4, t]); // 手前の板
    }
}

// シュート（窓の裏）とレーンセンサー。レール座標で作る。落ちる硬貨は裏(-z)へ離れながら下る
chute_d  = 26;          // 裏への深さ
chute_y0 = -48;         // シュートの下端（レール座標の y）
sens_y   = -30;         // レーンセンサーの高さ
lanes = [ [windows[0][1], windows[0][1] + windows[0][2] + jamb_bevel, "W1"],
          [windows[1][1], windows[1][1] + windows[1][2] + jamb_bevel, "W2"],
          [windows[2][1], windows[2][1] + windows[2][2] + jamb_bevel, "W3"],
          [plate_len - 4, plate_len + 16, "500"] ];   // 500円はレールの端から落ちる。端の壁で止める
module chutes() {
    t = 2;
    color([0.4, 0.8, 0.9, 0.4]) pose() difference() {
        union() {
            // 奥の壁と仕切り
            translate([lanes[0][0] - t, chute_y0, -chute_d - t]) cube([lanes[3][1] - lanes[0][0] + 2 * t, plate_y1 - chute_y0, t]);
            for (l = lanes) for (x = [l[0] - t, l[1]])
                translate([x, chute_y0, -chute_d]) cube([t, plate_y1 - chute_y0, chute_d]);
            // 板より下の手前の壁（センサーの受け側）
            translate([lanes[0][0] - t, chute_y0, -t]) cube([lanes[3][1] - lanes[0][0] + 2 * t, plate_y0 - chute_y0, t]);
            // 穴センサーの受光素子ホルダー（橋の裏）
            translate([bridge_x[0], plate_y0, -11]) cube([bridge_x[1] - bridge_x[0], plate_y1 - plate_y0, 11]);
        }
    }
    // レーンセンサー（赤＝LED、青＝受光素子）
    for (l = lanes) pose() translate([(l[0] + l[1]) / 2, sens_y, 0]) {
        color("red")  translate([0, 0, -chute_d - 2]) rotate([0, 0, 0]) cylinder(d = 5, h = 2);
        color("blue") translate([0, 0, -2]) cylinder(d = 5, h = 2);
        color([1, 0.3, 0.3, 0.6]) translate([0, 0, -chute_d]) cylinder(d = 1, h = chute_d);
    }
    // 穴センサーの受光素子（2 本・板の裏のホルダーに差す）
    for (bx = hole_beam_x) pose() translate([bx, hole_beam_y, 0])
        color("blue") translate([0, 0, -9]) cylinder(d = 5, h = 9);
}
// 穴センサーの LED（レールの橋の塔に上から差す。分解図ではレールと一緒に動く）
module hole_leds() {
    for (bx = hole_beam_x) pose() translate([bx, hole_beam_y, 0])
        color("red") translate([0, 0, plate_t + bridge_gap + 1]) cylinder(d = 5, h = elem_len);
}

// 吊り具：蓋の裏のつば板（今の架台と同じ M4 ボス 4 本）から、シュートの両端へ
module hanger() {
    fx0 = cradle_ox - flange; fy0 = cradle_oy - flange;
    fw = cradle_w + 2 * flange; fd = cradle_d + 2 * flange;
    color([0.95, 0.85, 0.3, 0.85]) difference() {
        translate([fx0, fy0, -3]) cube([fw, fd, 3]);
        translate([slot_c[0] - slot_size[0] / 2 - 2, slot_c[1] - slot_size[1] / 2 - 2, -4]) cube([slot_size[0] + 4, slot_size[1] + 4, 5]);
        for (p = boss_xy(cradle_w, cradle_d)) translate([cradle_ox + p[0], cradle_oy + p[1], -4]) cylinder(d = m4_hole, h = 5);
    }
    // 柱 2 本（上流端と、右のボスの下）
    for (x = [W([lanes[0][0], 0, 0])[0] - 6, cradle_ox + cradle_w - 10])
        color([0.95, 0.85, 0.3, 0.85]) hull() {
            translate([x, W([0, plate_y1, -chute_d])[1] - 4, -3]) cube([8, 8, 1]);
            translate([x, W([0, plate_y1, -chute_d])[1] - 4, W([0, plate_y1, 0])[2] - 20]) cube([8, 8, 1]);
        }
}

// 硬貨の道（赤）
module coin_path() {
    color("red") {
        hull() { translate([slot_c[0], slot_c[1], 20]) sphere(1.2); translate(W([gate_cx, gate_top_y, plate_t + 1.3])) sphere(1.2); }
        hull() { translate(W([gate_cx, gate_top_y, plate_t + 1.3])) sphere(1.2); translate(W([gate_cx, 11, plate_t + 1.3])) sphere(1.2); }
        hull() { translate(W([gate_cx, 11, plate_t + 1.3])) sphere(1.2); translate(W([plate_len + 6, 13, plate_t + 1.3])) sphere(1.2); }
        for (l = lanes) hull() {
            translate(W([(l[0] + l[1]) / 2 - 6, 11, plate_t + 1])) sphere(1.2);
            translate(W([(l[0] + l[1]) / 2, chute_y0 + 4, -chute_d / 2])) sphere(1.2);
        }
    }
}

module bay_part() {
    // bay.stl は 9/27 から実物どおりの向き（Y=0 が手前）。この図は蓋の図面の座標（Y が手前）なので前後を戻して置く
    translate([bay_ox, bay_oy + bay_d, -bay_h]) mirror([0, 1, 0]) color([0.35, 0.8, 0.5, 0.9]) import("bay.stl");
}

// スピーカー（位置だけ。蓋の音抜きの真下に蓋から吊る）
module speaker() {
    color([0.2, 0.2, 0.25]) translate([spk_c[0], spk_c[1], -32]) {
        cylinder(d = 66, h = 6);
        translate([0, 0, 6]) cylinder(d1 = 66, d2 = 40, h = 20);
        translate([0, 0, 26]) cylinder(d = 40, h = 6);
    }
}

// 箱（アクリル・内寸 344 角）の上の縁と四隅だけ線で描く
module box(h = 200) {
    w = recess[0] + 4; d = recess[1] + 4; x0 = (lid[0] - w) / 2; y0 = (lid[1] - d) / 2;
    color([0.5, 0.7, 1.0]) {
        for (x = [x0, x0 + w], y = [y0, y0 + d]) translate([x - 1, y - 1, -h]) cube([2, 2, h]);
        for (y = [y0, y0 + d]) translate([x0 - 1, y - 1, -1]) cube([w + 2, 2, 2]);
        for (x = [x0, x0 + w]) translate([x - 1, y0 - 1, -1]) cube([2, d + 2, 2]);
    }
}

// 番号札（カメラの方を向く）。p = 札の位置、q = 指す点
//   vr = カメラの回転（--camera と同じ値を -D で渡す）。txt_mirror = 1 なら数字を鏡文字にする
//   （画像を左右反転したあとで正しく読めるように）
vr = [55, 0, 25];
txt_mirror = 0;
tag_d = 16;
module tag(n, p, q) {
    color("black") hull() { translate(p) sphere(0.7); translate(q) sphere(0.7); }
    translate(p) rotate(vr) {
        color("white") translate([0, 0, 0.5]) cylinder(d = tag_d, h = 0.2, center = true);
        color("black") translate([0, 0, 0.8]) mirror([txt_mirror, 0, 0]) linear_extrude(0.2)
            text(str(n), size = tag_d * 0.55, halign = "center", valign = "center", font = "Liberation Sans:style=Bold");
        color("black") translate([0, 0, 0.5]) difference() { cylinder(d = tag_d + 1.4, h = 0.3, center = true); cylinder(d = tag_d, h = 1, center = true); }
    }
}

// ============================================================================
// explode = 1 で分解図（部品を離して並べる）
e = explode;
show_lid  = 1;
show_bay  = 1;      // 手前から見る図では基板室とスピーカーがレールを隠すので 0 にする
show_tags = 1;
translate([0, 0, 90 * e]) { if (show_lid) %lid(); }
if (e == 0) %box();
translate([0, 0, 40 * e]) hanger();
translate([0, 0, 25 * e]) funnel();
rail_part();
hole_leds();
translate([0, -40 * e, -35 * e]) chutes();
if (show_bay) translate([0, 40 * e, 0]) { bay_part(); speaker(); }
if (e == 0) coin_path();

// 番号札（凡例は画像側で付ける）
//  1 蓋  2 じょうご・関門  3 判別レール  4 穴センサー  5 シュート＋レーンセンサー
//  6 吊り具  7 基板室  8 スピーカー  9 硬貨の道
q2 = W([gate_cx - gate_len / 2, gate_top_y, plate_t]);
q3 = W([112, 22, plate_t]);
q4 = W([hole_beam_x[0], hole_beam_y, plate_t + bridge_gap + bridge_t + elem_len]);
q5 = W([150, chute_y0 + 4, -chute_d - 2]);
q6 = [cradle_ox - flange, cradle_oy + cradle_d / 2, -3];
q7 = [bay_ox + bay_w, bay_oy + 110, -30];
q8 = [spk_c[0] + 33, spk_c[1], -20];
q9 = W([plate_len + 4, 13, plate_t + 1.3]);
ex = [0, 40 * e, 0];   // 分解図のとき部品と一緒に動かす量（基板室）
tags_off = [];      // 視点によって裏に隠れる札を消す（例：-D "tags_off=[4,9]"）
module tag_if(n, p, q) if (len(search(n, tags_off)) == 0) tag(n, p, q);
if (show_tags) {
    tag_if(1, [20, 250, 90 * e - 30], [20, 250, 90 * e]);
    tag_if(2, q2 + [-20, 45, 25 * e + 25], q2 + [0, 0, 25 * e]);
    tag_if(3, q3 + [10, 55, -40], q3);
    tag_if(4, q4 + [-45, 40, -5], q4);
    tag_if(5, q5 + [25, -40 * e, -35 - 35 * e], q5 + [0, -40 * e, -35 * e]);
    tag_if(6, q6 + [-35, 0, 40 * e - 20], q6 + [0, 0, 40 * e]);
    if (show_bay) {
        tag_if(7, q7 + ex + [35, 0, -30], q7 + ex);
        tag_if(8, q8 + ex + [30, 0, -40], q8 + ex);
    }
    if (e == 0) tag_if(9, q9 + [25, 40, -30], q9);
}

// 位置の確認用（箱の内側は X・Y とも 5〜345）
echo(str("レール上流端（床）", W([0, 0, plate_t]), " 下流端（床）", W([plate_len, 0, plate_t])));
echo(str("シュートの右端 ", W([lanes[3][1] + 2, chute_y0, -chute_d - 2]), " ", W([lanes[3][1] + 2, plate_y1, 0])));
echo(str("シュートの左端 ", W([lanes[0][0] - 2, chute_y0, -chute_d - 2])));
echo(str("レール左端の上 ", W([0, plate_y1, 0]), " じょうごの関門 ", W([gate_cx, gate_top_y, plate_t])));
echo(str("一番低い所 ", W([plate_len, chute_y0, -chute_d - 2])));
echo(str("一番奥（シュートの裏）Y ", min([for (v = [[0, plate_y1, -chute_d - 2], [0, chute_y0, -chute_d - 2], [0, plate_y1, 0]]) W(v)[1]]),
         " ／一番手前（LED の塔）Y ", W([0, hole_beam_y + 5, plate_t + bridge_gap + bridge_t + elem_len + 1])[1]));
