// =============================================================================
// 自作判別ユニット（本番）  2026-09-27
// =============================================================================
// 寸法はすべて selfsort_params.scad（v2・シミュレーションで決めた値）。ここは形だけ。
// 蓋の図面（スリット・M4 ボス 4 本）は変えない。蓋の裏のリブが無い範囲（X 130〜275・奥から 12〜100）だけに付く。
//
// 部品（part = ...）
//   "rail"    ① 判別レール ……… 硬貨がもたれる面を上にして平置き。179 × 105。PETG（黒がよい）・壁 4・インフィル 30%・サポートなし
//   "guard"   ② 前板 ……………… 溝の手前の板。内面（硬貨側）を下にして平置き
//   "holder"  ③ 受光ホルダー …… 穴センサーの受光素子を裏から差す。平置き
//   "hanger"  ④ 吊り板 …………… 蓋のボス 4 本に留める板＋じょうご＋レールを吊る腕 2 本。蓋に当たる面を下にして印刷
//   "cap_pled" / "cap_prx" / "cap_hled" / "cap_hrx"  ⑤ 素子の押さえキャップ（2026-10-07）。通過 LED ×3・通過 受光 ×3・穴 LED ×2・穴 受光 ×1。
//             "cap_test" は 4 種類を 1 個ずつ、"cap_test3" は ⑤-1〜⑤-3、"cap_test23" は ⑤-2・⑤-3 を 1 個ずつ（試し刷り）。押さえる面を下にして平置き・サポートなし
//             "caps_all" は ⑤-1×2・⑤-2×2・⑤-3×1 を 1 枚に（2026-10-08・本番。足りない分だけ）
//   "assembly" 組立図（実物の向き・見るだけ）　"plate" 印刷の並べ方の確認
//
// 座標
//   レール座標（①②③）：x = 下り、y = 壁に沿って上（床の面が 0）、z = 壁の法線（硬貨側が +）
//   実物の座標（④・組立図）：X = 右、Y = 奥（蓋の「奥から」の値にマイナスを付けたもの）、Z = 上（蓋の裏が 0）
//   ★ 蓋の図面の座標（X 右・Y 手前）をそのまま 3D にすると鏡像になるので、Y の符号を反転して右手系にしてある
//
// レールの姿勢：右（+X）へ rail_alpha 下り、壁は奥へ rail_beta 傾く。硬貨の面は手前を向き、窓から倒れた硬貨は奥へ落ちる
// =============================================================================

include <../chassis_dims.scad>
include <selfsort_params.scad>

part = "assembly";
show_bay = 1;
show_lid = 1;

// ---- 姿勢と置き場所 -----------------------------------------------------------
ca = cos(rail_alpha); sa = sin(rail_alpha); cb = cos(rail_beta); sb = sin(rail_beta);
ex = [ca, 0, -sa];                 // レールの x 軸（実物の座標で）
ey = [cb * sa, sb, cb * ca];       // レールの y 軸
ez = [sb * sa, -cb, sb * ca];      // レールの z 軸（硬貨側の法線）
function Rv(v) = v[0] * ex + v[1] * ey + v[2] * ez;
function L2P(p) = [p[0], -p[1], len(p) > 2 ? p[2] : 0];     // 蓋の図面の座標 → 実物の座標

gate_pt  = [land_len / 2, gate_top, plate_t + gate_gap / 2];   // 関門の口の中心（レール座標）
gate_W   = [165, -slot_c[1], -35];   // 〃 を置く実物の位置（スリットの左寄りの真下・蓋の裏から 35）
P0 = gate_W - Rv(gate_pt);
function W(v) = P0 + Rv(v);                                     // レール座標 → 実物
function Wi(p) = let(d = p - P0) [d * ex, d * ey, d * ez];      // 実物 → レール座標
Mr = [[ex[0], ey[0], ez[0], P0[0]], [ex[1], ey[1], ez[1], P0[1]], [ex[2], ey[2], ez[2], P0[2]], [0, 0, 0, 1]];
module in_rail() multmatrix(Mr) children();

// ---- よく使う値 -----------------------------------------------------------------
t   = plate_t;
L   = plate_len;
zg  = t + guard_gap;                 // 前板・橋の内面（7.5）
x_e = -1.5;                          // 上流の端の壁の外側
bx0 = bridge_x[0]; bx1 = bridge_x[1];
el_blk = elem_d / 2 + 1.5;           // 素子ブロックの半幅（横の壁 1.5mm。灰色の PETG は赤外線を少し通すので厚めに）
blk_h  = pass_beam_z + elem_d / 2 + 1.8;   // 素子ブロックの高さ（上の壁 1.8mm）
cham = 2.0;                          // 関門の口の面取り

// 腕（マスト）：レールの上辺から立ち上がり、吊り板の腕にねじで留める
mast_top_Z = -14;                                   // マストの上端の高さ（実物の Z）
function mast_top_y(xc) = let(z0 = W([xc, 0, 0])[2]) (mast_top_Z - z0) / ey[2];
masts = [[44, 58], [102, 116]];                     // x の範囲（じょうごとセンサーを避ける）
mast_holes_dy = [8, 20];                            // マストの上端から下へ（ねじ穴 2 個。下の穴の頭が上の配線の溝の縁に当たらない位置）

// =============================================================================
// ① 判別レール
// =============================================================================
module window_cut(w) {
    x0 = w[1]; Lw = w[2]; H = w[3] + win_comp;
    translate([x0, curb_h, -1]) cube([Lw, H - curb_h, t + 2]);
}

module elem_bore_y(x, y0, y1) {       // y 方向の素子の穴（印刷では横向きの穴。φ5.7 ならブリッジで開く）
    translate([x, y0, pass_beam_z]) rotate([-90, 0, 0]) cylinder(d = elem_d, h = y1 - y0);
}

module rail_body() {
    // 壁の板（上流の端の壁の下まで）
    translate([x_e, plate_y0, 0]) cube([L - x_e, plate_y1 - plate_y0, t]);
    // 着地場所と関門の部分は壁を関門の上まで伸ばす
    translate([x_e, plate_y1 - 1, 0]) cube([land_len + 2 - x_e, gate_top - plate_y1 + 1, t]);
    // 床のブロック（溝の床。前板の受けも兼ねる）
    translate([0, -rib_t, t]) cube([L, rib_t, floor_w]);
    // 上流の端の壁
    translate([x_e, -rib_t, 0]) cube([-x_e, gate_top + rib_t, zg + bridge_t]);
    // 関門の下流側の壁（y が関門の範囲だけ。下は硬貨が転がり出る）
    translate([land_len, gate_y0, 0]) cube([2, gate_top - gate_y0, zg + bridge_t]);
    // 着地場所の前（すき間 4.5）と橋（穴センサーの LED）：x 0〜bx1 を一続きの天井で覆う
    translate([0, -rib_t, zg]) cube([bx1, gate_y0 + rib_t, bridge_t]);
    translate([bx0, -rib_t, zg]) cube([bx1 - bx0, bridge_y1 + rib_t, bridge_t]);
    translate([bx0, bridge_y1 - 3, t]) cube([bx1 - bx0, 3, zg - t]);          // 橋の上の支え
    // 関門の前（すき間 2.6）
    translate([0, gate_y0, t + gate_gap]) cube([land_len, gate_top - gate_y0, zg + bridge_t - t - gate_gap]);
    // 穴センサーの LED の塔
    for (bx = hole_beam_x) translate([bx, hole_beam_y, zg]) cylinder(d = elem_d + 4, h = bridge_t + 1 + elem_len);
    // 上辺の補強リブ（硬貨の上 26.5 より上）
    translate([bx1, plate_y1 - 3, t]) cube([L - bx1, 3, 3]);
    // 通過センサーのブロック：下（LED）と上（受光）
    for (px = pass_beam_x) {
        translate([px - el_blk, -rib_t - 1.5 - elem_len - 1, 0]) cube([2 * el_blk, 1.5 + elem_len + 1, blk_h]);
        translate([px - el_blk, pass_top_y, 0]) cube([2 * el_blk, 1 + elem_len + 2.5, blk_h]);
    }
    // マスト
    for (m = masts) {
        ytop = mast_top_y((m[0] + m[1]) / 2);
        translate([m[0], plate_y1 - 1, 0]) cube([m[1] - m[0], ytop - plate_y1 + 1, t]);
        translate([m[0], plate_y1 - 1, t]) cube([m[1] - m[0], 4, 3]);            // 付け根の補強
    }
    wire_gutters();
    // 中継基板の台（着地場所の前の面）
    for (b = rb_bosses) translate([b[0], b[1], zg + bridge_t - 0.01]) cylinder(d = 6.5, h = rb_boss_h);
}

// ---- 配線の溝 -------------------------------------------------------------------
// 硬貨の通り道（溝）と、窓から落ちた硬貨の通り道（板の裏）には配線を通さない。
// ・下の溝：床の下。通過センサーの LED（床の下）の足をここに入れ、上流の端まで運ぶ
// ・上の溝：硬貨の上。通過センサーの受光素子の足をここに入れ、上流（x=36）まで運ぶ
// どちらも硬貨側の面だけに付く（板の裏には何も出ない）。縁の上に 1mm の返しがあり、押し込むと外れない
gut_b  = [-22, plate_y0];            // 下の溝の範囲（y）：帯を -22 まで伸ばす
gut_t  = [pass_top_y + 1 + elem_len + 2.5, 48];   // 上の溝の範囲（y）：受光ブロックの上端〜48
gut_x0 = 36;                         // 上の溝の始まり（じょうごを避ける）
gut_h  = 9;                          // 縁の高さ（z）
lip_t  = 1.6;
rb_bosses = [[5, 20], [26, 40]];     // 中継基板を留める M3 タッピングの台（着地場所・関門の前の面）。基板に 2 穴開ける
rb_boss_h = 6;                       // M3×8 で留めてもねじの先が溝の天井（厚み 0.8）に届かない高さ
module wire_gutters() {
    // 下の溝
    translate([x_e, gut_b[0], 0]) cube([L - x_e, gut_b[1] - gut_b[0] + 0.01, t]);
    difference() {
        union() {
            translate([2, gut_b[0], t - 0.01]) cube([L - 2, lip_t, gut_h - t]);
            translate([2, gut_b[0] + lip_t - 0.01, gut_h - 1]) cube([L - 2, 1.0, 1]);           // 返し
        }
        for (px = pass_beam_x) translate([px - el_blk - 1, gut_b[0] - 1, 0]) cube([2 * el_blk + 2, 5, gut_h + 1]);  // LED を下から差す所は空ける
    }
    // 上の溝
    translate([gut_x0, plate_y1 - 1, 0]) cube([L - gut_x0, gut_t[1] - plate_y1 + 1, t]);
    difference() {
        union() {
            translate([gut_x0, gut_t[1] - lip_t, t - 0.01]) cube([L - gut_x0, lip_t, gut_h - t]);
            translate([gut_x0, gut_t[1] - lip_t - 1.0 + 0.01, gut_h - 1]) cube([L - gut_x0, 1.0, 1]);   // 返し
        }
        for (px = pass_beam_x) translate([px - el_blk - 1, gut_t[1] - 4, 0]) cube([2 * el_blk + 2, 5, gut_h + 1]);  // 受光素子を上から差す所は空ける
    }
}

module rail_cuts() {
    for (w = windows) window_cut(w);
    // フェルトのくぼみ（着地場所の床）
    if (pad_t > 0) translate([1, -pad_t, t - 0.01]) cube([land_len - 2, pad_t + 0.01, floor_w + 0.02]);   // pad_t=0 でフェルトなし（床は平ら）
    // 関門の口の面取り（前の板の上端・内側の角を 45° に落とす）
    translate([-1, 0, 0]) rotate([90, 0, 90]) linear_extrude(land_len + 2)
        polygon([[gate_top - cham, t + gate_gap - 0.01], [gate_top + 0.01, t + gate_gap - 0.01], [gate_top + 0.01, t + gate_gap + cham]]);
    // 穴センサー：LED の穴（上から）・絞り穴（橋の下面と板）
    for (bx = hole_beam_x) {
        translate([bx, hole_beam_y, zg + 1]) cylinder(d = elem_d, h = elem_len + bridge_t + 1);
        translate([bx, hole_beam_y, zg - 0.5]) cylinder(d = aperture_d, h = 2);
        translate([bx, hole_beam_y, -1]) cylinder(d = aperture_d, h = t + 2);
    }
    // 通過センサー：LED（床の下）と受光（上）。絞り穴は溝の床と天井に開く
    for (px = pass_beam_x) {
        elem_bore_y(px, -rib_t - 1.5 - elem_len - 1.01, -rib_t - 1.5);
        translate([px, 0.01, pass_beam_z]) rotate([90, 0, 0]) cylinder(d = pass_ap_d, h = rib_t + 1.6);
        elem_bore_y(px, pass_top_y + 1, pass_top_y + 1 + elem_len + 2.6);
        translate([px, pass_top_y - 0.01, pass_beam_z]) rotate([-90, 0, 0]) cylinder(d = pass_ap_d, h = 1.1);
    }
    // マストのねじ穴（M3 が通る）
    for (m = masts) for (dy = mast_holes_dy)
        translate([(m[0] + m[1]) / 2, mast_top_y((m[0] + m[1]) / 2) - dy, -1]) cylinder(d = m3_d, h = t + 5);
    // 前板を留めるねじの下穴（床のブロックの前面から）
    for (gx = guard_screw_x) translate([gx, -rib_t / 2, t - 1]) cylinder(d = m3_tap, h = floor_w + 2);
    // 受光ホルダーを裏から留めるねじの下穴（板と床のブロックへ。溝には抜けない）と位置決めピン
    for (hx = holder_screw_x) translate([hx, holder_screw_y, -0.01]) cylinder(d = m3_tap, h = 7);
    translate([42, 30, -1]) cylinder(d = pin_d + 0.2, h = t + 1.5);
    // 素子を差し込む通り道（溝の床が素子の胴に当たらないよう、穴の延長を溝の外まで空ける。底は 0.9mm 残す）
    for (px = pass_beam_x) {
        translate([px - 3.2, gut_b[0] - 1, 0.9]) cube([6.4, -rib_t - 1.5 - elem_len - 1 - gut_b[0] + 1.1, t]);
        translate([px - 3.2, gut_t[0] - 0.1, 0.9]) cube([6.4, gut_t[1] - gut_t[0] + 1.1, t]);
    }
    // 中継基板の台の下穴（溝には抜けない：天井の中で止める）
    for (b = rb_bosses) translate([b[0], b[1], zg + 0.8]) cylinder(d = m3_tap, h = bridge_t + rb_boss_h);
    // 目印（床の下の帯に彫る）
    for (l = [["IN", 6], ["1/50", 66], ["5/100", 100], ["10", 146]])
        translate([l[1], plate_y0 + 0.8, t - 0.5]) linear_extrude(1) text(l[0], size = 2.6, font = "Liberation Sans:style=Bold");
}
guard_screw_x  = [64, 116, 154];
holder_screw_x = [33, 51];
holder_screw_y = -rib_t / 2;

module rail() difference() { rail_body(); rail_cuts(); }

// =============================================================================
// ② 前板（溝の手前。橋の下流から終端まで）
// =============================================================================
module guard() {
    difference() {
        translate([bx1 + 0.3, -rib_t, zg]) cube([L - bx1 - 0.3, guard_y1 + rib_t, guard_t]);
        for (gx = guard_screw_x) translate([gx, -rib_t / 2, zg - 1]) cylinder(d = m3_d, h = guard_t + 2);
        // 通過センサーの絞り穴の真上は避ける必要なし（ビームは壁の面から 0.8、前板は 4.5 の位置）
    }
}

// =============================================================================
// ③ 受光ホルダー（穴センサー 2 本。板の裏に付ける）
// =============================================================================
holder_t = 11;
module holder() {
    x0 = bx0; w = bx1 - bx0;
    difference() {
        union() {
            translate([x0, plate_y0, -holder_t]) cube([w, 31 - plate_y0, holder_t]);
            translate([42, 30, -0.5]) cylinder(d = pin_d - 0.2, h = 1.7);
        }
        for (bx = hole_beam_x) translate([bx, hole_beam_y, -holder_t - 1]) cylinder(d = elem_d, h = holder_t + 2);
        for (bx = hole_beam_x) translate([bx - 1.5, hole_beam_y, -holder_t - 1]) cube([3, 14, 4]);   // 足を出す溝
        for (hx = holder_screw_x) {
            translate([hx, holder_screw_y, -holder_t - 1]) cylinder(d = m3_d, h = holder_t + 2);
            translate([hx, holder_screw_y, -holder_t - 1]) cylinder(d = 7, h = holder_t - 4 + 1);   // 頭の座ぐり（残り 4mm）。φ6 ではトラス 3×8 の頭が入らなかった（9/30）→ φ7
        }
    }
}

// =============================================================================
// ⑤ 素子の押さえキャップ（2026-10-07）。レール座標のまま、付ける位置に置いた形
// =============================================================================
// 素子のつば（φ5.8・厚み 1）を穴の入口の面へ押し付ける。くぼみ（⑤-1〜⑤-3 は φ5.8、⑤-4 は φ6.3）でつばの位置も決まる。
// ⑤-1 はすき間 0（fit_clr）。⑤-2・⑤-3 は片側 0.1 きつい（prx_clr・cup_clr = -0.1）。10/7 の試し刷り 2 回で合わせた。
// どれも素子の足の側からかぶせるだけ（ねじなし）。足の溝は縁まで開いているので、配線したまま付けられる。
// 外側は黒の油性ペンで塗る（灰色の PETG は赤外線を少し通す）
//   ⑤-1 通過 LED（床の下）×3 ：手前からブロックに押し込む。重さで下へ抜けようとするのを、耳が下の溝の返しで止める
//   ⑤-2 通過 受光（硬貨の上）×3：手前からブロックに押し込む。重さでつばの上に乗る
//   ⑤-3 穴 LED（橋の塔）×2   ：塔にかぶせる筒。重さで塔に乗る。筒は C 字（足の溝が下まで切れている）なので、はんだ付け後の線を横から入れてかぶせる
//   ⑤-4 穴 受光（③ の裏）×1  ：③ の裏を覆うふた。下の縁が ③ の下の面に乗り、突起が ③ のねじの座ぐりに入る
pled_face = -rib_t - 1.5 - elem_len - 1;          // 通過 LED のブロックの下の面（-16.1）
prx_face  = pass_top_y + 1 + elem_len + 2.5;      // 通過 受光のブロックの上の面（41.6）
tower_top = zg + bridge_t + 1 + elem_len;         // 橋の塔の上面（20.1）
cap_z1    = blk_h + cap_wall;                     // ⑤-1・⑤-2 の上の面
ret_face  = gut_b[0] + lip_t - 0.01 + 1.0;        // 下の溝の返しの内側の面（-19.41）

module ycyl(x, y0, y1, z, d) translate([x, min(y0, y1), z]) rotate([-90, 0, 0]) cylinder(d = d, h = abs(y1 - y0));

// 通過センサーのキャップ。s = 足の向き（-1：下・LED、+1：上・受光）。y_far = 横の壁の終わり。c = 横の壁のすき間（片側）
module cap_pass(px, face_y, s, y_far, ears, c) {
    w  = el_blk + c;                              // 内側の半幅（⑤-1 はブロックとぴったり、⑤-2 は 0.1 細い）
    wo = w + cap_wall;                            // 外側の半幅
    y_in  = face_y + s * fit_clr;                 // つばを押す壁の内面
    y_out = y_in + s * (flange_t + cap_back);     // 〃 外面
    z0 = t + 0.2;                                 // 横の壁の下端（溝の床から浮かせる）
    difference() {
        union() {
            translate([px - wo, min(y_far, y_out), z0]) cube([2 * wo, abs(y_far - y_out), cap_z1 - z0]);
            // 耳：返しの内側の面に当たって、キャップが下へ抜けるのを止める（返しの切れ目 ±(el_blk+1) の外）
            if (ears) for (sx = [-1, 1]) {
                xa = px + sx * (el_blk + 1.1); xb = px + sx * (wo + 1.2);
                translate([min(xa, xb), ret_face + cap_ear_gap, gut_h - 2]) cube([abs(xb - xa), y_in - ret_face - cap_ear_gap, cap_z1 - gut_h + 2]);
            }
        }
        // ブロックが入る所（上の壁の内面がブロックの上面に乗る）
        translate([px - w, min(y_in, y_far - s), z0 - 1]) cube([2 * w, abs(y_far - s - y_in), blk_h - z0 + 1]);
        // つばのくぼみ（下が開いた U 字。押し込むとつばが下から入る）
        hull() for (z = [pass_beam_z, z0 - 1]) ycyl(px, y_in - s * 0.01, y_in + s * flange_t, z, flange_d);
        // 足の溝（下が開いている）
        hull() for (z = [pass_beam_z, z0 - 1]) ycyl(px, y_in - s * 0.01, y_out + s, z, cap_lead_w);
    }
}
module cap_pled(px) cap_pass(px, pled_face, -1, -rib_t - 0.5, true, fit_clr);     // 横の壁は床のブロック（y -5）の手前まで
module cap_prx(px)  cap_pass(px, prx_face, 1, plate_y1 + 3.2, false, prx_clr);    // 〃 マストの付け根の補強（y 32〜36）の上から

// 穴センサーの LED：塔にかぶせる筒
module cap_hled(bx) {
    r_in = (elem_d + 4) / 2 + cup_clr;
    difference() {
        translate([bx, hole_beam_y, tower_top - cup_depth]) cylinder(r = r_in + cap_wall, h = cup_depth + flange_t + cap_back);
        translate([bx, hole_beam_y, tower_top - cup_depth - 1]) cylinder(r = r_in, h = cup_depth + 1);
        translate([bx, hole_beam_y, tower_top - 0.01]) cylinder(d = flange_d, h = flange_t + 0.01);
        // 足の溝（真ん中から縁まで、筒の高さ全部を切る＝C 字）。線をはんだ付けした後でも横から線を入れられる（10/7）
        hull() for (dy = [0, r_in + cap_wall + 1]) translate([bx, hole_beam_y + dy, tower_top - cup_depth - 1]) cylinder(d = cap_lead_w, h = cup_depth + flange_t + cap_back + 2);
    }
}

// 穴センサーの受光：③ の裏ふた
module cap_hrx() {
    x0 = bx0 - cap_clr - cap_wall; x1 = bx1 + cap_clr + cap_wall;
    yb = plate_y0 - cap_clr - cap_wall; yt = 31;          // ③ は y -9〜31
    zi = -holder_t - 0.05;                                // ふたの内面（③ の裏の面 -11 から 0.05）
    zo = zi - flange_t - cap_back;                        // 〃 外面
    difference() {
        union() {
            translate([x0, yb, zo]) cube([x1 - x0, yt - yb, zi - zo]);
            // 縁（左・右・下）。③ の側面をつかむ。レールの板の裏（z=0）には当てない
            translate([x0, yb, zo]) cube([cap_wall, yt - yb, -0.5 - zo]);
            translate([x1 - cap_wall, yb, zo]) cube([cap_wall, yt - yb, -0.5 - zo]);
            translate([x0, yb, zo]) cube([x1 - x0, cap_wall, -0.5 - zo]);
            // 突起（③ のねじの座ぐり φ7 に入る。ねじの頭まで届かない長さ）
            for (hx = holder_screw_x) translate([hx, holder_screw_y, zi - 0.01]) cylinder(d = cap_peg_d, h = cap_peg_len);
        }
        for (bx = hole_beam_x) {
            translate([bx, hole_beam_y, zi - flange_t]) cylinder(d = cap_pocket_d, h = flange_t + 0.01);
            // 足の溝（素子の中心から上の縁まで。③ の足の溝の上に重なる）
            hull() for (y = [hole_beam_y, yt + 1]) translate([bx, y, zo - 1]) cylinder(d = cap_lead_w, h = zi - zo + 1.01);
        }
    }
}
hrx_zo = -holder_t - 0.05 - flange_t - cap_back;

module caps_placed() {
    for (px = pass_beam_x) { cap_pled(px); cap_prx(px); }
    for (bx = hole_beam_x) cap_hled(bx);
    cap_hrx();
}
// 印刷の向き（押さえる面を上。どれもサポートなし）。原点の近くに置く
module cap_print(k) {
    if (k == 0) translate([0, 0, cap_z1]) rotate([180, 0, 0]) translate([-pass_beam_x[0], -pled_face, 0]) cap_pled(pass_beam_x[0]);
    if (k == 1) translate([0, 0, cap_z1]) rotate([180, 0, 0]) translate([-pass_beam_x[0], -prx_face, 0]) cap_prx(pass_beam_x[0]);
    if (k == 2) translate([0, 0, tower_top + flange_t + cap_back]) rotate([180, 0, 0]) translate([-hole_beam_x[0], -hole_beam_y, 0]) cap_hled(hole_beam_x[0]);
    if (k == 3) translate([-bx0, -plate_y0, -hrx_zo]) cap_hrx();
}

// =============================================================================
// ④ 吊り板（実物の座標）
// =============================================================================
plate_top_t = 10;                                        // 蓋の裏（Z=0）からボスの高さ 8 ＋ 2
hang_x = [cradle_ox - flange + 0.5, cradle_ox + cradle_w + flange - 0.5];      // リブの無い範囲の中
hang_y = [-(cradle_oy + cradle_d + flange - 0.5), -(cradle_oy - flange + 0.5)];
bosses = [for (p = boss_xy(cradle_w, cradle_d)) L2P([cradle_ox + p[0], cradle_oy + p[1]])];

// じょうご：蓋のスリット → 入口の絞り → 長い直線の出口 → 関門の上端
// ①②③ との間はレールの外形のすき間 0.4（rail_envelope）だけ。出口は関門の上端 +0.4 で終わる
fun_wall = 2.2;
fun_y0 = gate_top + 0.4;                     // 出口の下端（レール座標 y）
fun_y1 = fun_y0 + fun_straight;              // 直線部分の上端
fun_c2 = W([land_len / 2, fun_y1, (fun_out_z[0] + fun_out_z[1]) / 2]);   // 直線部分の上端の中心（実物）
fun_c0 = [slot_c[0], -slot_c[1], 0];
function fun_c(Zq) = fun_c0 + (fun_c2 - fun_c0) * (Zq / fun_c2[2]);     // 蓋の中心から出口までの線上の点
module fun_out_rect(y, o) {                  // 出口の断面（レール座標）
    in_rail() translate([fun_out_x[0] - o, y, fun_out_z[0] - o])
        cube([fun_out_x[1] - fun_out_x[0] + 2 * o, 0.01, fun_out_z[1] - fun_out_z[0] + 2 * o]);
}
module fun_ch_rect(o) {                      // 厚い部屋の断面（レール座標）
    in_rail() translate([fun_out_x[0] - o, fun_ch_y, fun_ch_z[0] - o])
        cube([fun_out_x[1] - fun_out_x[0] + 2 * o, 0.01, fun_ch_z[1] - fun_ch_z[0] + 2 * o]);
}
module fun_in_rect(o) {                      // 入口の絞り（レールと同じ向き。蓋の裏から fun_in_depth 下）
    c = fun_c(-fun_in_depth);
    multmatrix([[ex[0], ey[0], ez[0], c[0]], [ex[1], ey[1], ez[1], c[1]], [ex[2], ey[2], ez[2], c[2]], [0, 0, 0, 1]])
        translate([-fun_in_w / 2 - o, -0.005, -fun_in_t / 2 - o]) cube([fun_in_w + 2 * o, 0.01, fun_in_t + 2 * o]);
}
module funnel_cavity(o = 0) {
    // ① スリット直下：まっすぐ（蓋の穴 40×6 に 0.3 ずつ余裕）
    translate(L2P([slot_c[0] - slot_size[0] / 2 - 0.3 - o, slot_c[1] + slot_size[1] / 2 + 0.3 + o, -fun_lip]))
        cube([slot_size[0] + 0.6 + 2 * o, slot_size[1] + 0.6 + 2 * o, fun_lip + 0.02]);
    // ② 絞りまでゆるやかに
    hull() {
        translate(L2P([slot_c[0] - slot_size[0] / 2 - 0.3 - o, slot_c[1] + slot_size[1] / 2 + 0.3 + o, -fun_lip]))
            cube([slot_size[0] + 0.6 + 2 * o, slot_size[1] + 0.6 + 2 * o, 0.01]);
        fun_in_rect(o);
    }
    // ③ 絞り → 厚い部屋（ここで硬貨が回る）→ 出口の直線部分の上端
    hull() { fun_in_rect(o); fun_ch_rect(o); }
    hull() { fun_ch_rect(o); fun_out_rect(fun_y1, o); }
    // ④ 出口の直線部分
    hull() { fun_out_rect(fun_y1, o); fun_out_rect(fun_y0, o); }
}
module funnel() {
    difference() {
        funnel_cavity(fun_wall);
        funnel_cavity(0);
        in_rail() translate([-50, fun_y0 - 20, -50]) cube([200, 20, 100]);     // 口より下は無し
    }
}

// 腕：マストの裏（レール座標 z<0）に当たる台。台の前の面＝マストの裏の面
arm_d = 9;
function arm_y0(ytop) = max(ytop - 30, plate_y1 + 3);    // 腕の下端（板の上端より上＝落ちる硬貨の道に入らない）
module arm(m) {
    xc = (m[0] + m[1]) / 2;
    ytop = mast_top_y(xc);
    difference() {
        // 台（マストの裏に当たる）と、その真上の影を吊り板の下面まで伸ばした柱。
        // 印刷（上下逆）では側面が垂直になり、張り出しは台の面（約 12°）だけ
        hull() {
            in_rail() translate([m[0], arm_y0(ytop), -arm_d]) cube([m[1] - m[0], ytop - arm_y0(ytop), arm_d]);
            translate([0, 0, -plate_top_t - 1]) linear_extrude(1)
                projection() in_rail() translate([m[0], arm_y0(ytop), -arm_d]) cube([m[1] - m[0], ytop - arm_y0(ytop), arm_d]);
        }
        // ねじの下穴（M3 タッピング・深さ 8）
        for (dy = mast_holes_dy) in_rail() translate([xc, ytop - dy, -8]) cylinder(d = m3_tap, h = 8.1);
    }
}

module hanger() {
    difference() {
        union() {
            translate([hang_x[0], hang_y[0], -plate_top_t]) cube([hang_x[1] - hang_x[0], hang_y[1] - hang_y[0], plate_top_t]);
            funnel();
            for (m = masts) arm(m);
            for (i = [0 : len(anchors) - 1]) snap_clip(anchors[i], anchor_w[i]);
        }
        funnel_cavity(0);
        // ボスの逃げ（蓋のボス φ9・高さ 8）と M4 の長穴（±1.5）
        for (b = bosses) {
            translate([b[0], b[1], -8.01]) cylinder(d = boss_d + 1.5, h = 8.1);
            hull() for (d = [-1.5, 1.5]) translate([b[0] + d, b[1], -plate_top_t - 1]) cylinder(d = m4_hole, h = plate_top_t);
        }
        // 肉抜き（板の中の空洞は作らず、上面から浅く）
        // レールとぶつかる所を逃がす（安全のため 0.3mm すき間）
        in_rail() rail_envelope(0.4);
        // 蓋の上面より上は無し
        translate([0, -400, 0]) cube([400, 400, 50]);
    }
}
// レールの外形（腕との干渉を逃がすための粗い形）
module rail_envelope(g = 0) {      // g = すき間
    translate([x_e - g, plate_y0 - g, -g]) cube([L - x_e + 2 * g, plate_y1 - plate_y0 + 2 * g, zg + bridge_t + 1 + elem_len + 2 * g]);
    // マストの裏の面（z=0）は腕がぴったり当たる面なので、すき間を付けない
    for (m = masts) translate([m[0] - g, plate_y1 - 1, 0]) cube([m[1] - m[0] + 2 * g, mast_top_y((m[0] + m[1]) / 2) - plate_y1 + 1 + g, 6 + g]);
    translate([x_e - g, plate_y1 - 1, -g]) cube([land_len + 2 - x_e + 2 * g, gate_top - plate_y1 + 1 + g, zg + bridge_t + 2 * g]);
    for (px = pass_beam_x) translate([px - el_blk - g, pass_top_y - g, -g]) cube([2 * el_blk + 2 * g, 1 + elem_len + 2.5 + 2 * g, blk_h + 2 * g]);
    // 配線の溝（下・上）
    translate([x_e - g, gut_b[0] - g, -g]) cube([L - x_e + 2 * g, plate_y0 - gut_b[0] + 2 * g, gut_h + 2 * g]);
    translate([gut_x0 - g, plate_y1 - 1, -g]) cube([L - gut_x0 + 2 * g, gut_t[1] - plate_y1 + 1 + g, gut_h + 2 * g]);
    // 中継基板と部品の高さ（着地場所の前の面の上）
    translate([rb_xy[0] - g, rb_xy[1] - g, zg + bridge_t]) cube([rb_size[0] + 2 * g, rb_size[1] + 2 * g, rb_boss_h + rb_height + g]);
}
// 中継基板（ユニバーサル基板を切って使う）の置き場所：レール座標で左下の角と大きさ
rb_xy   = [1, 16];
rb_size = [32, 28];
rb_height = 12;                      // 基板＋部品の高さ（抵抗は寝かせる。端子台は使わない）

// ---- 吊り板の線の留め具（印刷のクリップ。結束バンドは要らない）---------------------------
// 板の下にぶら下がる U 字。線の束を下から押し込むと、先の返し（0.5mm）で外れない。
// 板の上面は蓋にぴったり当たるので、板に穴を開けて留める方式は使えない
anchors  = [[157, -74], [157, -89],   // 配線 7 本の束（中継基板 → 基板室）。板の前の縁（Y -96.3）から出ない
            [140, -42], [140, -74]];  // 電源ジャックの線 2 本（蓋の奥 → 基板室）
anchor_w = [4.5, 4.5, 3.0, 3.0];      // U の内側の幅＝束の太さ（AWG24 7 本で約 4mm、2 本で約 2.5mm）
clip_len = 8;                         // 線の向きの長さ
prong_t  = 1.4;                       // 爪の厚み（PETG が割れずにしなう厚み）
barb     = 0.5;                       // 返し
anchor_h = 3.5;                       // （組立図で線を描く高さに使う）
module snap_clip(p, w) {
    dp = w + 3;                       // 爪の長さ（板の下面から）
    for (s = [-1, 1]) {
        translate([p[0] + s * (w / 2 + prong_t / 2) - prong_t / 2, p[1] - clip_len / 2, -plate_top_t - dp])
            cube([prong_t, clip_len, dp + 0.01]);
        // 返し：先端で内側へ barb、1.2mm 上で 0 になる斜面（下から押し込むと爪が開く）
        hull() {
            translate([p[0] + s * w / 2 - (s > 0 ? barb : 0), p[1] - clip_len / 2, -plate_top_t - dp]) cube([barb, clip_len, 0.01]);
            translate([p[0] + s * w / 2 - (s > 0 ? 0.01 : 0), p[1] - clip_len / 2, -plate_top_t - dp + 1.2]) cube([0.01, clip_len, 0.01]);
        }
    }
}

// =============================================================================
// 組立図（実物の向き）
// =============================================================================
module lid_view() {
    color([0.92, 0.92, 0.92, 0.3]) difference() {
        translate([0, -lid[1], 0]) cube([lid[0], lid[1], lid_t]);
        translate(L2P([slot_c[0] - slot_size[0] / 2, slot_c[1] + slot_size[1] / 2, -1])) cube([slot_size[0], slot_size[1], lid_t + 2]);
        translate(L2P([spk_c[0], spk_c[1], -1])) cylinder(d = spk_d, h = lid_t + 2);
        translate(L2P([pwr_c[0], pwr_c[1], -1])) cylinder(d = pwr_d, h = lid_t + 2);
    }
    for (b = bosses) color([0.8, 0.8, 0.8]) translate([b[0], b[1], -8]) cylinder(d = boss_d, h = 8);
}
module speaker_view() {
    color([0.2, 0.2, 0.25]) translate(L2P([spk_c[0], spk_c[1], -32])) {
        cylinder(d = 66, h = 6);
        translate([0, 0, 6]) cylinder(d1 = 66, d2 = 40, h = 20);
        translate([0, 0, 26]) cylinder(d = 40, h = 6);
    }
}
module box_view(h = 200) {            // アクリル箱（内寸 344 角）の縁だけ
    w = 344; x0 = (lid[0] - w) / 2;
    color([0.5, 0.7, 1.0]) {
        for (x = [x0, x0 + w], y = [-x0, -x0 - w]) translate([x - 1, y - 1, -h]) cube([2, 2, h]);
        for (y = [-x0, -x0 - w]) translate([x0 - 1, y - 1, -1]) cube([w + 2, 2, 2]);
        for (x = [x0, x0 + w]) translate([x - 1, -x0 - w - 1, -1]) cube([2, w + 2, 2]);
    }
}
module coin_path() {                  // 硬貨の道（赤）
    pts = [L2P([slot_c[0] + 8, slot_c[1], 20]), L2P([slot_c[0] + 8, slot_c[1], 0]),
           W([land_len / 2, gate_top + 3, t + 1.3]), W([land_len / 2, 11, t + 1.3]),
           W([plate_len + 3, 12.5, t + 1.3])];
    color("red") for (i = [0 : len(pts) - 2]) hull() { translate(pts[i]) sphere(1.1); translate(pts[i + 1]) sphere(1.1); }
    color("red") for (w = windows) hull() {
        translate(W([w[1] + w[2] * 0.6, 10.5, t + 1])) sphere(1.1);
        translate(W([w[1] + w[2] * 0.9, -25, -14])) sphere(1.1);
    }
}
// 番号札（カメラの方を向く）。vr = カメラの回転を -D で渡す
vr = [55, 0, 25];
tag_d = 15;
module tag(n, p, q) {
    color("black") hull() { translate(p) sphere(0.6); translate(q) sphere(0.6); }
    translate(p) rotate(vr) {
        color("white") translate([0, 0, 0.5]) cylinder(d = tag_d, h = 0.2, center = true);
        color("black") translate([0, 0, 0.8]) linear_extrude(0.2)
            text(str(n), size = tag_d * (n >= 10 ? 0.42 : 0.55), halign = "center", valign = "center", font = "Liberation Sans:style=Bold");
        color("black") translate([0, 0, 0.5]) difference() { cylinder(d = tag_d + 1.4, h = 0.3, center = true); cylinder(d = tag_d, h = 1, center = true); }
    }
}
show_tags = 1;
show_path = 1;
show_wire = 1;       // 配線を描く
show_box  = 1;

// 配線の通り道（見るだけ）。点を順に太い線でつなぐ
module wire_path(pts, d, col) {
    color(col) for (i = [0 : len(pts) - 2]) hull() { translate(pts[i]) sphere(d / 2); translate(pts[i + 1]) sphere(d / 2); }
}
bay_entry = [157, -140, -4];         // 基板室の奥の壁の上（蓋とのすき間 8mm）から入る
module harness_view() {
    // 中継基板
    color([0.1, 0.5, 0.2]) in_rail() translate([rb_xy[0], rb_xy[1], zg + bridge_t + rb_boss_h]) cube([rb_size[0], rb_size[1], 1.6]);
    // 下の溝：通過センサーの LED 3 本 → 上流の端 → 中継基板
    wire_path([for (v = [[175, -19, 5], [4, -19, 5], [4, -4, 11], [8, 18, 16.5]]) W(v)], 2.4, [0.95, 0.6, 0.1]);
    // 上の溝：通過センサーの受光 3 本 → x=36 → 中継基板
    wire_path([for (v = [[176, 44.5, 5], [37, 44.5, 5], [31, 42, 16.5]]) W(v)], 2.4, [0.95, 0.6, 0.1]);
    // 穴センサーの LED 2 本（橋の塔の上）→ 中継基板
    for (bx = hole_beam_x) wire_path([for (v = [[bx, hole_beam_y, zg + bridge_t + 1 + elem_len], [bx - 4, 16, 18], [30, 22, 16.5]]) W(v)], 1.6, [0.95, 0.6, 0.1]);
    // 穴センサーの受光 2 本（裏のホルダー）→ 板の裏を上へ → 上の辺を越えて上の溝へ
    for (bx = hole_beam_x) wire_path([for (v = [[bx, 24, -holder_t + 2], [40, 40, -2], [40, 48.5, 1.5], [38, 45, 5]]) W(v)], 1.6, [0.95, 0.6, 0.1]);
    // LAN ケーブル（8 本）：中継基板 → 吊り板の門 2 つ → 基板室
    wire_path(concat([W([16, rb_xy[1] + rb_size[1], zg + bridge_t + rb_boss_h + 4])],
                     [[anchors[0][0], anchors[0][1], -plate_top_t - 3],
                      [anchors[1][0], anchors[1][1], -plate_top_t - 3], bay_entry]), 5, [0.2, 0.35, 0.9]);
    // 電源ジャックの線：蓋の奥 → 門 2 つ → 基板室
    wire_path([L2P([pwr_c[0], pwr_c[1], -2]), [anchors[2][0], anchors[2][1], -plate_top_t - 3],
               [anchors[3][0], anchors[3][1], -plate_top_t - 3], [138, -140, -4]], 3.5, [0.85, 0.1, 0.1]);
    // スピーカーの線
    wire_path([L2P([spk_c[0] + 20, spk_c[1], -25]), L2P([bay_ox - 4, bay_oy + bay_d - 40, -4])], 3, [0.5, 0.5, 0.5]);
}
show_spk  = 1;
tags_off  = [];
explode   = 0;
tag_side  = 1;       // 札を出す向き：1 = 手前（-Y）、-1 = 奥（+Y）
module tag_if(n, p, q) if (len(search(n, tags_off)) == 0) tag(n, q + [p[0] - q[0], (p[1] - q[1]) * tag_side, p[2] - q[2]], q);

module assembly() {
    e = explode;
    dL = [0, 0, 90 * e]; dH = [0, 0, 45 * e]; dG = 30 * e * ez; dO = -30 * e * ez;   // 分解図の移動量（前板は手前・ホルダーは奥）
    if (show_lid) translate(dL) %lid_view();
    if (e == 0 && show_box) %box_view();
    translate(dH) color([0.95, 0.85, 0.3]) hanger();
    color([0.22, 0.22, 0.24]) in_rail() rail();
    translate(dG) color([0.4, 0.75, 0.95, 0.85]) in_rail() guard();
    translate(dO) color([0.3, 0.6, 0.3]) in_rail() holder();
    if (pad_t > 0) color([0.15, 0.55, 0.25]) in_rail() translate([1.2, -pad_t, t]) cube([land_len - 2.4, pad_t, floor_w - 0.2]);  // フェルト
    // センサー（赤＝LED、青＝受光）
    for (bx = hole_beam_x) in_rail() {
        color("red")  translate([bx, hole_beam_y, zg + bridge_t + 1]) cylinder(d = 5, h = elem_len);
        translate(-30 * e * [0, 0, 1]) color("blue") translate([bx, hole_beam_y, -holder_t + 1]) cylinder(d = 5, h = elem_len);
    }
    for (px = pass_beam_x) in_rail() {
        color("red")  translate([px, -rib_t - 1.5 - elem_len, pass_beam_z]) rotate([-90, 0, 0]) cylinder(d = 5, h = elem_len);
        color("blue") translate([px, pass_top_y + 1, pass_beam_z]) rotate([-90, 0, 0]) cylinder(d = 5, h = elem_len);
    }
    // 基板室。bay.stl は 9/27 から実物どおりの向き（Y=0 が手前）で出しているので鏡映しは要らない。
    // 蓋の図面の奥の端（bay_oy）が、この図では Y = -bay_oy に来る
    if (show_bay) translate([bay_ox, -(bay_oy + bay_d), -bay_h]) color([0.35, 0.8, 0.5, 0.6]) import("bay.stl");
    if (show_spk) speaker_view();
    if (show_path && e == 0) coin_path();
    if (show_wire && e == 0) harness_view();
    if (show_tags) {
        q1 = [322, -335, 0];
        q2 = [hang_x[1], hang_y[0] + 10, -10] + dH;
        q3 = W([150, 28, t]);
        q4 = W([118, 12, zg + guard_t]) + dG;
        q5 = W([42, 24, -holder_t]) + dO;
        q6 = W([hole_beam_x[0], hole_beam_y, zg + bridge_t + elem_len]);
        q7 = W([pass_beam_x[1], -rib_t - 6, 5]);
        q8 = W([10, -1, t + 2]);
        q9 = L2P([bay_ox + bay_w, bay_oy + 110, -30]);
        q10 = L2P([spk_c[0] + 33, spk_c[1], -20]);
        q11 = W([plate_len - 8, 12.5, t + 1.3]);
        tag_if(1, q1 + [0, 0, -30] + dL, q1 + dL);
        tag_if(2, q2 + [25, -25, -18], q2);
        tag_if(3, q3 + [0, -40, 30], q3);
        tag_if(4, q4 + [40, -45, -5], q4);
        tag_if(5, q5 + [-5, 40, -45], q5);
        tag_if(6, q6 + [-40, -30, 5], q6);
        tag_if(7, q7 + [-15, -40, -35], q7);
        tag_if(8, q8 + [-20, -35, -35], q8);
        if (show_bay) tag_if(9, q9 + [35, 0, -30], q9);
        if (show_spk) tag_if(10, q10 + [30, 0, -40], q10);
        if (show_path && e == 0) tag_if(11, q11 + [10, -35, -35], q11);
        if (show_wire && e == 0) {
            q12 = [anchors[1][0], anchors[1][1] - 20, -14];
            q13 = W([rb_xy[0] + rb_size[0] / 2, rb_xy[1] + 4, zg + bridge_t + rb_boss_h + 1.6]);
            q14 = W([120, -19, 5]);
            q15 = [anchors[3][0], anchors[3][1], -16];
            tag_if(12, q12 + [-10, -30, -25], q12);
            tag_if(13, q13 + [-35, -35, -10], q13);
            tag_if(14, q14 + [45, -30, 5], q14);
            tag_if(15, q15 + [-35, -20, -20], q15);
        }
    }
}

// =============================================================================
if (part == "rail")   rail();
if (part == "guard")  translate([0, 0, zg + guard_t]) rotate([180, 0, 0]) guard();      // 内面を下（鏡映しにしない）
if (part == "holder") translate([0, 0, holder_t]) holder();
if (part == "hanger") rotate([180, 0, 0]) hanger();                                       // 蓋に当たる面を下（鏡映しにしない）
if (part == "assembly") assembly();
if (part == "funnel_cavity") funnel_cavity(0);                                            // じょうごの空洞（試験用。sim/funnel_check.py）
if (part == "gate_cavity") in_rail() translate([0, gate_y0, t]) cube([land_len, gate_top - gate_y0 + 0.01, gate_gap]);   // 関門の空洞（実物の向き）
// 干渉の確認：吊り板とレール一式が重なる所だけ残す（空なら OK）
if (part == "check_hanger") intersection() { hanger(); in_rail() union() { rail(); guard(); holder(); } }
if (part == "check_guard")  intersection() { rail(); guard(); }
if (part == "assembled") { hanger(); in_rail() { rail(); guard(); holder(); } }       // 実物の座標で一式（寸法の確認用）
if (part == "check_holder") intersection() { rail(); holder(); }
// ⑤ 押さえキャップ（印刷の向き）。cap_test は 4 種類を 1 個ずつ（試し刷り）
if (part == "cap_pled") for (i = [0:2]) translate([i * 18, 0, 0]) cap_print(0);
if (part == "cap_prx")  for (i = [0:2]) translate([i * 18, 0, 0]) cap_print(1);
if (part == "cap_hled") for (i = [0:1]) translate([i * 16, 0, 0]) cap_print(2);
if (part == "cap_hrx")  cap_print(3);
if (part == "cap_test") { cap_print(0); translate([18, 0, 0]) cap_print(1); translate([40, 8, 0]) cap_print(2); translate([0, 25, 0]) cap_print(3); }
if (part == "cap_test3") { cap_print(0); translate([18, 0, 0]) cap_print(1); translate([40, 8, 0]) cap_print(2); }   // ⑤-4 なし（10/7：⑤-4 は合格済み）
if (part == "cap_test23") { cap_print(1); translate([22, 8, 0]) cap_print(2); }   // ⑤-2・⑤-3 だけ（10/7 2 回目：⑤-1 も合格）
if (part == "caps_all") {   // 本番：⑤-1×2・⑤-2×2・⑤-3×1（10/8：試し刷り 3 回で合格。⑤-4 と残りは試し刷りの分を使う）
    for (i = [0:1]) translate([i * 18, 0, 0]) cap_print(0);
    for (i = [0:1]) translate([36 + i * 18, 0, 0]) cap_print(1);
    translate([76, 8, 0]) cap_print(2);
}
if (part == "caps_placed") caps_placed();
if (part == "caps_view") { color("silver") { rail(); guard(); holder(); } color("black") caps_placed(); }   // 付けた所の絵（レール座標）
// キャップがレール・前板・③・吊り板に食い込まないか（空なら OK）
if (part == "check_caps") intersection() { caps_placed(); union() { rail(); guard(); holder(); } }
if (part == "check_caps_hanger") intersection() { hanger(); in_rail() caps_placed(); }
if (part == "plate") {                                                                    // 部品の確認用
    translate([0, 0, 0]) rail();
    translate([0, 120, 0]) translate([0, 0, zg + guard_t]) rotate([180, 0, 0]) guard();
}

// ---- 確認 ------------------------------------------------------------------------
echo(str("関門の口（実物）", gate_W, "  レール上流の床 ", W([0, 0, t]), "  下流の床 ", W([L, 0, t])));
echo(str("レールの X 範囲 ", W([x_e, 0, 0])[0], " 〜 ", W([L, 0, 0])[0], "（箱の内側 3〜347・蓋のリブの無い範囲 X 130〜275）"));
echo(str("一番低い所 Z ", W([L, -rib_t - 1.5 - elem_len - 1, 0])[2]));
for (m = masts) echo(str("マスト x ", m, " 上端 y ", mast_top_y((m[0] + m[1]) / 2), " 実物 ", W([(m[0] + m[1]) / 2, mast_top_y((m[0] + m[1]) / 2), 0])));
echo(str("吊り板 X ", hang_x, " Y ", hang_y));
