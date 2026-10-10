// ユニット箱の寸法を echo で Python に渡す（形は作らない）。
// 出力：ECHO: "UBX <key> <JSON>"。読むのは unit_box_lib.read_data()
include <unit_box_dims.scad>

echo(str("UBX plate_t ", ub_plate_t));
echo(str("UBX x ", ub_x));
echo(str("UBX seam_y ", ub_seam_y));
echo(str("UBX a_y ", ub_a_y));
echo(str("UBX b_y ", ub_b_y));
echo(str("UBX boss_d ", ub_boss_d));
echo(str("UBX boss_h ", ub_boss_h));
echo(str("UBX hang_boss ", ub_hang_boss));
echo(str("UBX bay_place ", ub_bay_place));
echo(str("UBX bay_boss ", ub_bay_boss));
echo(str("UBX slot_c ", ub_slot_c));
echo(str("UBX slot_bot ", ub_slot_bot));
echo(str("UBX slot_top ", ub_slot_top));
echo(str("UBX spk_c ", ub_spk_c));
echo(str("UBX spk_sq ", ub_spk_sq));
echo(str("UBX spk_depth ", ub_spk_depth));
echo(str("UBX spk_boss_h ", ub_spk_boss_h));
echo(str("UBX spk_hole_half ", ub_spk_hole_half));
echo(str("UBX snd_d ", ub_snd_d));
echo(str("UBX snd_r ", ub_snd_r));
echo(str("UBX snd ", ub_snd));
echo(str("UBX lid_m4 ", ub_lid_m4));
echo(str("UBX m4_hole ", ub_m4_hole));
echo(str("UBX nut_af ", ub_nut_af));
echo(str("UBX nut_top ", ub_nut_top));
echo(str("UBX screw_tip ", ub_screw_tip));
echo(str("UBX splice ", ub_splice));
echo(str("UBX splice_t ", ub_splice_t));
echo(str("UBX splice_screw ", ub_splice_screw));
echo(str("UBX leg_h ", ub_leg_h));
echo(str("UBX legs ", ub_legs));
echo(str("UBX leg_holes ", ub_leg_holes));
echo(str("UBX lid ", lid));
echo(str("UBX recess ", recess));
echo(str("UBX slot_size ", slot_size));
