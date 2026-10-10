// =============================================================================
// 自作判別部 ① 判別レール（＋試験用の受光素子ホルダーと台）  2026-09-26
// =============================================================================
// ★★ 旧案（2026-09-27 に置き換え）。本番は 判別ユニット_本番.scad。
//    この形（縁石なし・前板なし）はシミュレーションで硬貨が止まる／大きい硬貨も窓から落ちると分かった。
//    selfsort_params.scad は v2 になったので、ここを出力し直しても旧案の STL とは一致しない。印刷しないこと
// =============================================================================
// 寸法はすべて selfsort_params.scad（唯一の正）。ここは形だけ。
//
// 印刷：part = "rail"（既定）/ "holder" / "stand_up" / "stand_down" / "all"（1 枚のベッドに並べる）
//   ・判別レールは「硬貨がもたれる面を上」にして平置き。窓の高さ（しきい値）が XY になるので精度が出る
//   ・黒で印刷（赤外線を通さないため）。サポート不要（橋は 34mm のブリッジ）
//
// 使い方（試験）
//   1. 台（上流・下流）にレールを載せる：板の下端を台の段に、裏を斜面に当てる → 勾配 test_alpha・傾き test_beta
//   2. 上流端（x=0 側）の床リブの上に硬貨を立て、壁にもたれさせて手を離す
//   3. どの窓から落ちるかを見る（W1=1円/50円、W2=5円/100円、W3=10円、最後まで転がる=500円）
//   4. 穴センサー：橋の塔に LED、裏のホルダーに受光素子を差し、sensortest で遮光パルスを見る
//      （穴あき硬貨は 1 枚で HIGH が 2 回に割れる）
// =============================================================================

include <selfsort_params.scad>

part = "all";

// ---------------------------------------------------------------------------
module plate_body() {
    // 壁の板
    translate([0, plate_y0, 0]) cube([plate_len, plate_y1 - plate_y0, plate_t]);
    // 床リブ（硬貨が転がる床。y=0 の面が床）
    translate([0, -rib_t, plate_t]) cube([plate_len, rib_t, floor_w]);
}

// 窓：床の面(y=0)から高さ H まで板を貫通。下流側の縁は裏側で jamb_bevel 長く（45° 面取り）
module window_cut(x0, L, H) {
    hull() {
        translate([x0, 0, plate_t - 0.01]) cube([L, H, 0.02 + 1]);
        translate([x0, 0, -1])            cube([L + jamb_bevel + 1, H, 0.02]);
    }
    translate([x0, 0, -1]) cube([L, H, plate_t + 2]);
}

// 橋（穴センサーの LED を硬貨の手前に置く）と支え
module bridge() {
    x0 = bridge_x[0]; w = bridge_x[1] - bridge_x[0];
    zb = plate_t + bridge_gap;                       // 橋の下面
    // 下の支え：床リブを橋の下面まで伸ばす
    translate([x0, -rib_t, plate_t]) cube([w, rib_t, bridge_gap]);
    // 上の支え：500円より上の壁
    translate([x0, bridge_y1 - 3, plate_t]) cube([w, 3, bridge_gap]);
    // 橋の板
    translate([x0, -rib_t, zb]) cube([w, bridge_y1 + rib_t, bridge_t]);
    // LED の塔
    for (bx = hole_beam_x)
        translate([bx, hole_beam_y, zb]) cylinder(d = elem_d + 4, h = 1 + elem_len);
}

module bridge_holes() {
    zb = plate_t + bridge_gap;
    for (bx = hole_beam_x) {
        // LED を差す穴（上から。先端は 1mm の底で止まる）
        translate([bx, hole_beam_y, zb + 1]) cylinder(d = elem_d, h = elem_len + 1);
        // ビームを絞る穴（橋の下面）
        translate([bx, hole_beam_y, zb - 0.5]) cylinder(d = aperture_d, h = 2);
        // 板の側の絞り穴（裏の受光素子へ）
        translate([bx, hole_beam_y, -1]) cylinder(d = aperture_d, h = plate_t + 2);
    }
}

module labels() {
    // 床の下の帯（硬貨の通り道の外）に彫る。取付穴を避けて置く
    lbl = [["IN", 12], ["HOLE A/B", bridge_x[0] + 6], ["1/50", 64], ["21.5", 76],
           ["5/100", 97], ["23.05", 108], ["10", 134], ["25.0", 146], ["500>", 156]];
    for (l = lbl)
        translate([l[1], plate_y0 + 0.9, plate_t - 0.5])
            linear_extrude(1) text(l[0], size = 2.4, font = "Liberation Sans:style=Bold");
}

module rail() {
    difference() {
        union() { plate_body(); bridge(); }
        for (w = windows) window_cut(w[1], w[2], w[3] + win_comp);
        bridge_holes();
        for (x = mount_x) translate([x, mount_y, -1]) cylinder(d = m3_d, h = plate_t + 2);
        for (p = pin_xy)  translate([p[0], p[1], -1]) cylinder(d = pin_d + 0.2, h = plate_t + bridge_gap + 2);
        labels();
    }
}

// ---------------------------------------------------------------------------
// 試験用：板の裏に付ける受光素子ホルダー（ピンで位置決め、テープかホットボンドで留める）
holder_t = 11;
module holder() {
    x0 = bridge_x[0]; w = bridge_x[1] - bridge_x[0];
    difference() {
        union() {
            translate([x0, plate_y0 + 1, 0]) cube([w, 31 - plate_y0 - 1 + 1, holder_t]);
            for (p = pin_xy) translate([p[0], p[1], holder_t]) cylinder(d = pin_d - 0.2, h = 2.5);
        }
        // 受光素子の穴（裏から差し、先端を板に当てる）
        for (bx = hole_beam_x) translate([bx, hole_beam_y, -1]) cylinder(d = elem_d, h = holder_t + 2);
        // 足を出す溝
        for (bx = hole_beam_x) translate([bx - 1.5, hole_beam_y, -1]) cube([3, 12, 4]);
    }
}

// ---------------------------------------------------------------------------
// 試験台：板の下端を段で受け、裏を斜面で受ける。上流と下流で高さを変えて勾配を作る
// 断面（台の幅方向に押し出す）：原点＝段の角。板の裏の面は後ろへ test_beta 傾く
stand_w  = 12;
stand_H  = 32;          // 斜面の長さ（板に沿って）
stand_h0 = 8;           // 下流側：段の角の高さ
stand_dx = (plate_len - stand_w);   // 上流と下流の台の中心間（板の端に置く）
module stand_section(h) {
    b = test_beta;
    polygon([
        [ (plate_t + 1) * cos(b), (plate_t + 1) * sin(b)],             // 段の先
        [ (plate_t + 1) * cos(b) - 2 * sin(b), (plate_t + 1) * sin(b) + 2 * cos(b)], // 段の先の小さな返し
        [ (plate_t + 1) * cos(b) - 2 * sin(b) - 1.2 * cos(b), (plate_t + 1) * sin(b) + 2 * cos(b) - 1.2 * sin(b)],
        [ 0, 0 ],                                                       // 段の角（板の下端の裏）
        [ -stand_H * sin(b), stand_H * cos(b) ],                        // 斜面の上端
        [ -stand_H * sin(b) - 6, stand_H * cos(b) ],
        [ -stand_H * sin(b) - 6, -h ],
        [ (plate_t + 1) * cos(b) + 4, -h ],
    ]);
}
// 印刷用：断面を床に寝かせて stand_w の厚みで押し出す
module stand(h) { linear_extrude(stand_w) stand_section(h); }
module stand_up()   { stand(stand_h0 + stand_dx * sin(test_alpha)); }
module stand_down() { stand(stand_h0); }

// 試験の姿勢（確認用の組立図）：レールを傾けて台に載せる。前＝+Y、下りは -X
module rail_on_stand() { rotate([0, 0, 180]) rotate([0, test_alpha, 0]) rotate([90 - test_beta, 0, 0]) translate([0, -plate_y0, 0]) rail(); }
module assembly_test() {
    color("dimgray") rail_on_stand();
    // 台の角 = 板の裏・下端の線。上流端（x=0）と下流端（x=plate_len）の位置へ
    for (s = [[0, stand_up_h()], [plate_len - stand_w, stand_h0]]) {
        xw = -(s[0] + stand_w / 2) * cos(test_alpha);
        zw = (s[0] + stand_w / 2) * sin(test_alpha);
        color("orange") translate([xw - stand_w / 2, 0, -zw]) rotate([90, 0, 90]) stand(s[1]);
    }
}
function stand_up_h() = stand_h0 + stand_dx * sin(test_alpha);

// ---------------------------------------------------------------------------
if (part == "rail")       rail();
if (part == "holder")     holder();
if (part == "stand_up")   stand_up();
if (part == "stand_down") stand_down();
if (part == "all") {                      // A1 mini のベッド 1 枚に並べる（180 角）
    translate([0, 9, 0]) rail();                                   // y 0〜42
    translate([126, 60, 0]) holder();                              // x 140〜168, y 52〜92（レールから 10mm 離す）
    translate([28, 72, 0]) stand_up();                             // x 11〜36, y 20〜80 付近
    translate([90, 72, 0]) stand_down();
}
if (part == "assembly") assembly_test();

// ---------------------------------------------------------------------------
echo(str("=== 判別レール === 板 ", plate_len, " x ", plate_y1 - plate_y0, " x ", plate_t, "（橋・塔込みの高さ ",
         plate_t + bridge_gap + 1 + elem_len, "）"));
for (w = windows) echo(str("  ", w[0], "  x ", w[1], "〜", w[1] + w[2], "  高さ ", w[3], " (+補正 ", win_comp, ")"));
for (c = coins) {
    // どの窓で落ちるか（直径 < 窓の高さ の最初の窓）
    idx = [for (i = [0:len(windows)-1]) if (c[1] < windows[i][3]) i];
    echo(str("  ", c[0], "円 φ", c[1], " → ", len(idx) ? windows[idx[0]][0] : "終端(500円レーン)",
             len(idx) ? str("  余裕 ", windows[idx[0]][3] - c[1], " / 手前の窓との差 ",
                            idx[0] > 0 ? c[1] - windows[idx[0]-1][3] : 99) : "",
             c[3] > 0 ? "  穴あり" : ""));
}
