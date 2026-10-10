// =============================================================================
// CoinTracker の単体テスト（v3.0・自作ソータ）
//
// 仕様：3Dプリント/自作判別部/sim/system_test.py の decide()（hole_rule="or"）／ Config.h の SS_*
// 実機なしで PC 上で走る（pio test -e native）。Arduino API は使わない。
// エッジは ssMakeCoinEdges（1 枚が一定の速さで通ったときの形）か手で並べて作り、
// 1ms ごとに「その時刻までのエッジを渡す → tick → 結果を取り出す」を回す（loop と同じ順）。
//
// 期待値の計算（速さ 250mm/s）
//   穴 B → P1 の距離 49mm → 196ms。段 0 の期限 1.8×49/250＋0.08 = 432.8ms
//   P1 → P2 の距離 36mm。段 1 の期限 1.8×36/250＋0.08 = 339.2ms
// =============================================================================
#include <unity.h>
#include "Config.h"
#include "CoinTracker.h"

static const uint32_t MS = 1000;
static const int CAP = 128;

struct Rec {
  CoinResult r[16];
  int n;
};

static uint32_t at(uint32_t base, double ms) { return base + static_cast<uint32_t>(ms * 1000.0 + 0.5); }

static int addPulse(SsEdge* e, int n, int beam, uint32_t a, uint32_t b) {
  e[n].beam = beam; e[n].high = true;  e[n].t_us = a; n++;
  e[n].beam = beam; e[n].high = false; e[n].t_us = b; n++;
  return n;
}

static int addCoin(SsEdge* e, int n, int value, double v, uint32_t base, double tA_ms, bool withA = true) {
  int k = ssMakeCoinEdges(value, v, at(base, tA_ms), withA, e + n, CAP - n);
  TEST_ASSERT_TRUE(k > 0);
  return n + k;
}

// 指定のビームの遮光を 1 回にまとめる（穴の割れ目を見落とした形）
static int mergeBeam(SsEdge* e, int n, int beam) {
  int first = -1, last = -1;
  for (int i = 0; i < n; i++) {
    if (e[i].beam == beam) {
      if (first < 0) first = i;
      last = i;
    }
  }
  int m = 0;
  for (int i = 0; i < n; i++) {
    if (e[i].beam == beam && i != first && i != last) continue;
    e[m++] = e[i];
  }
  return m;
}

static void sortEdges(SsEdge* e, int n, uint32_t base) {
  for (int i = 1; i < n; i++) {
    SsEdge x = e[i];
    int j = i - 1;
    while (j >= 0 && static_cast<int32_t>(e[j].t_us - base) > static_cast<int32_t>(x.t_us - base)) {
      e[j + 1] = e[j];
      j--;
    }
    e[j + 1] = x;
  }
}

static void run(CoinTracker& tr, SsEdge* e, int n, uint32_t base, uint32_t endMs, Rec* rec) {
  sortEdges(e, n, base);
  rec->n = 0;
  int k = 0;
  for (uint32_t ms = 0; ms <= endMs; ms++) {
    uint32_t now = base + ms * MS;
    while (k < n && static_cast<int32_t>(e[k].t_us - now) <= 0) {
      tr.onEdge(e[k].beam, e[k].high, e[k].t_us);
      k++;
    }
    tr.tick(now);
    CoinResult r;
    while (tr.poll(&r)) {
      if (rec->n < 16) rec->r[rec->n++] = r;
    }
  }
}

static uint32_t elapsed(const CoinResult& r) { return r.t_decided_us - r.t_in_us; }

void setUp(void) {}
void tearDown(void) {}

// 1. 6 金種を 1 枚ずつ（250mm/s）→ 金額・トラック・段・穴が正しい
void test_each_value_single(void) {
  const int stageOf[LANE_COUNT] = {3, 1, 0, 2, 1, 0};   // 500,100,50,10,5,1
  for (int k = 0; k < LANE_COUNT; k++) {
    CoinTracker tr;
    SsEdge e[CAP];
    int n = addCoin(e, 0, LANE_VALUE[k], 250.0, 0, 100);
    Rec rec;
    run(tr, e, n, 0, 1500, &rec);
    TEST_ASSERT_EQUAL_INT_MESSAGE(1, rec.n, "結果は 1 つ");
    TEST_ASSERT_EQUAL_INT(LANE_VALUE[k], rec.r[0].value);
    TEST_ASSERT_EQUAL_INT(LANE_TRACK[k], rec.r[0].track);
    TEST_ASSERT_EQUAL_INT(stageOf[k], rec.r[0].stage);
    TEST_ASSERT_EQUAL(LANE_VALUE[k] == 50 || LANE_VALUE[k] == 5, rec.r[0].hole);
    TEST_ASSERT_FALSE(rec.r[0].adopted);
    TEST_ASSERT_FALSE(rec.r[0].forced);
    TEST_ASSERT_UINT32_WITHIN(1, 250, rec.r[0].speed_mm_s);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().coins);
    TEST_ASSERT_EQUAL_UINT32(0, tr.stats().orphan);
    TEST_ASSERT_EQUAL_INT(0, tr.active());
  }
}

// 2. 穴 B の 5ms の遮光はちらつき → 数えない・鳴らさない
void test_flicker_on_B_is_ignored(void) {
  CoinTracker tr;
  SsEdge e[CAP];
  int n = addPulse(e, 0, SS_BEAM_HB, at(0, 100), at(0, 105));
  Rec rec;
  run(tr, e, n, 0, 2000, &rec);
  TEST_ASSERT_EQUAL_INT(0, rec.n);
  TEST_ASSERT_EQUAL_UINT32(1, tr.stats().flicker);
  TEST_ASSERT_EQUAL_UINT32(0, tr.stats().coins);
}

// 3. 穴が片方のビームでしか見えなくても 50円（hole_rule = "or"）
void test_hole_seen_on_one_beam_is_enough(void) {
  for (int beam = SS_BEAM_HA; beam <= SS_BEAM_HB; beam++) {
    CoinTracker tr;
    SsEdge e[CAP];
    int n = addCoin(e, 0, 50, 250.0, 0, 100);
    n = mergeBeam(e, n, beam == SS_BEAM_HA ? SS_BEAM_HB : SS_BEAM_HA);   // もう片方は割れ目を見落とす
    Rec rec;
    run(tr, e, n, 0, 1500, &rec);
    TEST_ASSERT_EQUAL_INT(1, rec.n);
    TEST_ASSERT_EQUAL_INT(50, rec.r[0].value);
    TEST_ASSERT_TRUE(rec.r[0].hole);
  }
}

// 4. 穴 A の相方が無い → 硬貨にしない・鳴らさない（10/10 の仕様変更。前は既定の速さで追っていた）
void test_no_A_is_not_a_coin(void) {
  CoinTracker tr;
  SsEdge e[CAP];
  int n = addCoin(e, 0, 1, 250.0, 0, 100, false);
  Rec rec;
  run(tr, e, n, 0, 1500, &rec);
  TEST_ASSERT_EQUAL_INT(0, rec.n);
  TEST_ASSERT_EQUAL_INT(0, tr.active());
  TEST_ASSERT_EQUAL_UINT32(1, tr.stats().noA);
  TEST_ASSERT_EQUAL_UINT32(0, tr.stats().aBad);   // 範囲内に穴 A が 1 つも無かった
  TEST_ASSERT_EQUAL_UINT32(0, tr.stats().coins);
}

// 5. 期限は速さで伸び縮みする（上限・下限つき）
void test_deadline_follows_speed(void) {
  // 遅い 100円（80mm/s）：P1 まで 612.5ms。段 1 の期限 1.8×36/80＋0.08 = 0.89s → 上限 700ms
  {
    CoinTracker tr;
    SsEdge e[CAP];
    int n = addCoin(e, 0, 100, 80.0, 0, 100);
    Rec rec;
    run(tr, e, n, 0, 3000, &rec);
    TEST_ASSERT_EQUAL_INT(1, rec.n);
    TEST_ASSERT_EQUAL_INT(100, rec.r[0].value);
    TEST_ASSERT_UINT32_WITHIN(2, 612500 + 700000, elapsed(rec.r[0]));
  }
  // 速い 1円（400mm/s）：段 0 の期限 1.8×49/400＋0.08 = 300.5ms
  {
    CoinTracker tr;
    SsEdge e[CAP];
    int n = addCoin(e, 0, 1, 400.0, 0, 100);
    Rec rec;
    run(tr, e, n, 0, 1500, &rec);
    TEST_ASSERT_EQUAL_INT(1, rec.n);
    TEST_ASSERT_EQUAL_INT(1, rec.r[0].value);
    TEST_ASSERT_UINT32_WITHIN(2, 300500, elapsed(rec.r[0]));
  }
}

// 6. 0.3 秒おきの 2 枚（500円 → 1円）がどちらも正しい
void test_two_coins_in_flight(void) {
  CoinTracker tr;
  SsEdge e[CAP];
  int n = addCoin(e, 0, 500, 250.0, 0, 100);
  n = addCoin(e, n, 1, 250.0, 0, 400);
  Rec rec;
  run(tr, e, n, 0, 2000, &rec);
  TEST_ASSERT_EQUAL_INT(2, rec.n);
  TEST_ASSERT_EQUAL_INT(500, rec.r[0].value);
  TEST_ASSERT_EQUAL_INT(1, rec.r[1].value);
  TEST_ASSERT_EQUAL_UINT32(2, tr.stats().coins);
  TEST_ASSERT_EQUAL_UINT32(0, tr.stats().orphan);
}

// 7. 速い 100円（400mm/s）は穴 B のかたまりが閉じる前に P1 を遮る → 閉じるまで待って正しく 100円
void test_fast_coin_P1_waits_for_B_group(void) {
  CoinTracker tr;
  SsEdge e[CAP];
  int n = addCoin(e, 0, 100, 400.0, 0, 100);
  Rec rec;
  run(tr, e, n, 0, 1500, &rec);
  TEST_ASSERT_EQUAL_INT(1, rec.n);
  TEST_ASSERT_EQUAL_INT(100, rec.r[0].value);
  TEST_ASSERT_FALSE(rec.r[0].adopted);
  TEST_ASSERT_EQUAL_UINT32(0, tr.stats().orphan);
}

// 8. P の 5ms の遮光は無視（数える）し、判定には影響しない
void test_short_P_glitch_is_ignored(void) {
  CoinTracker tr;
  SsEdge e[CAP];
  int n = addCoin(e, 0, 100, 250.0, 0, 100);
  n = addPulse(e, n, SS_BEAM_P2, at(0, 400), at(0, 405));
  Rec rec;
  run(tr, e, n, 0, 1500, &rec);
  TEST_ASSERT_EQUAL_INT(1, rec.n);
  TEST_ASSERT_EQUAL_INT(100, rec.r[0].value);
  TEST_ASSERT_EQUAL_UINT32(1, tr.stats().pShort);
}

// 9. 入口で数えていない硬貨が P3 を通った → 拾うなら 500円、拾わないなら鳴らさない
void test_orphan_P3(void) {
  {
    CoinTracker tr(true);
    SsEdge e[CAP];
    int n = addPulse(e, 0, SS_BEAM_P3, at(0, 100), at(0, 150));
    Rec rec;
    run(tr, e, n, 0, 1000, &rec);
    TEST_ASSERT_EQUAL_INT(1, rec.n);
    TEST_ASSERT_EQUAL_INT(500, rec.r[0].value);
    TEST_ASSERT_TRUE(rec.r[0].adopted);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().orphan);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().adopted);
  }
  {
    CoinTracker tr(false);
    SsEdge e[CAP];
    int n = addPulse(e, 0, SS_BEAM_P3, at(0, 100), at(0, 150));
    Rec rec;
    run(tr, e, n, 0, 1000, &rec);
    TEST_ASSERT_EQUAL_INT(0, rec.n);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().orphan);
    TEST_ASSERT_EQUAL_UINT32(0, tr.stats().adopted);
  }
}

// 10. 入口で数えていない硬貨が P1 を通った → 段 1 から追い、P2 が来なければ 339.2ms で 100円
void test_orphan_P1_is_adopted_and_expires(void) {
  CoinTracker tr(true);
  SsEdge e[CAP];
  int n = addPulse(e, 0, SS_BEAM_P1, at(0, 100), at(0, 150));
  Rec rec;
  run(tr, e, n, 0, 1000, &rec);
  TEST_ASSERT_EQUAL_INT(1, rec.n);
  TEST_ASSERT_EQUAL_INT(100, rec.r[0].value);
  TEST_ASSERT_TRUE(rec.r[0].adopted);
  TEST_ASSERT_TRUE(rec.r[0].byTimeout);
  TEST_ASSERT_UINT32_WITHIN(2, 339200, elapsed(rec.r[0]));
}

// 11. P は「来るはずの時刻に一番近い」硬貨に当て、それより前に入った硬貨はその場で決める
//   X：1円・入口 100ms・250mm/s  Y：10円・入口 300ms・250mm/s
//   Y の P1（496ms）は X には遅すぎ（誤差 1.02）、Y にはぴったり（0.0）→ Y に当てる。
//   X はそこで 1円と決まる（期限 532.8ms を待たない）
void test_nearest_prediction_and_older_resolved(void) {
  CoinTracker tr;
  SsEdge e[CAP];
  int n = addCoin(e, 0, 1, 250.0, 0, 84);          // 穴 B に 100ms に入る
  n = addCoin(e, n, 10, 250.0, 0, 291);            // 穴 B に 300ms に入る
  Rec rec;
  run(tr, e, n, 0, 2000, &rec);
  TEST_ASSERT_EQUAL_INT(2, rec.n);
  TEST_ASSERT_EQUAL_INT(1, rec.r[0].value);
  TEST_ASSERT_FALSE(rec.r[0].byTimeout);
  TEST_ASSERT_UINT32_WITHIN(2, at(0, 496), rec.r[0].t_decided_us);
  TEST_ASSERT_EQUAL_INT(10, rec.r[1].value);
  TEST_ASSERT_EQUAL_INT(2, rec.r[1].stage);
}

// 12. 追跡の枠（ここでは 2）があふれたら、一番古い硬貨をその場で決める
//   穴 A → 穴 B が 100ms（140mm/s）の 1円 3 枚。段 0 の期限 710ms なので 3 枚目が入るとき 1 枚目はまだ追跡中
void test_overflow_forces_oldest(void) {
  CoinTracker tr(true, 2);
  SsEdge e[CAP];
  int n = 0;
  for (int i = 0; i < 3; i++) {
    const double t0 = 100 + 115 * i;
    n = addPulse(e, n, SS_BEAM_HA, at(0, t0), at(0, t0 + 25));
    n = addPulse(e, n, SS_BEAM_HB, at(0, t0 + 100), at(0, t0 + 125));
  }
  Rec rec;
  run(tr, e, n, 0, 2000, &rec);
  TEST_ASSERT_EQUAL_INT(3, rec.n);
  TEST_ASSERT_TRUE(rec.r[0].forced);
  TEST_ASSERT_EQUAL_UINT32(at(0, 200), rec.r[0].t_in_us);
  for (int i = 0; i < 3; i++) TEST_ASSERT_EQUAL_INT(1, rec.r[i].value);
  TEST_ASSERT_FALSE(rec.r[1].forced);
  TEST_ASSERT_EQUAL_UINT32(1, tr.stats().overflow);
  TEST_ASSERT_EQUAL_UINT32(3, tr.stats().coins);
}

// 13. micros() の巻き戻り（0xFFFFFFFF → 0）をまたいでも正しい
void test_micros_wraparound(void) {
  CoinTracker tr;
  SsEdge e[CAP];
  const uint32_t base = 0xFFFFFFFFu - 150u * MS;
  int n = addCoin(e, 0, 100, 250.0, base, 100);
  Rec rec;
  run(tr, e, n, base, 1500, &rec);
  TEST_ASSERT_EQUAL_INT(1, rec.n);
  TEST_ASSERT_EQUAL_INT(100, rec.r[0].value);
  TEST_ASSERT_UINT32_WITHIN(2, 196000 + 339200, elapsed(rec.r[0]));
}

// 14. 100円 2 枚が接して穴 B を通り 1 枚に数えた → P1 の 2 回目を拾えば 2 回鳴る（拾わなければ 1 回）
void test_touching_coins_adoption(void) {
  for (int adopt = 0; adopt <= 1; adopt++) {
    CoinTracker tr(adopt == 1);
    SsEdge e[CAP];
    int n = addPulse(e, 0, SS_BEAM_HA, at(0, 0), at(0, 180.8));
    n = addPulse(e, n, SS_BEAM_HB, at(0, 56), at(0, 236.8));
    n = addPulse(e, n, SS_BEAM_P1, at(0, 252), at(0, 342.4));
    n = addPulse(e, n, SS_BEAM_P1, at(0, 400), at(0, 490.4));
    Rec rec;
    run(tr, e, n, 0, 1500, &rec);
    TEST_ASSERT_EQUAL_INT(adopt ? 2 : 1, rec.n);
    for (int i = 0; i < rec.n; i++) TEST_ASSERT_EQUAL_INT(100, rec.r[i].value);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().orphan);
  }
}

// 15. reset() で追跡中の硬貨も集計も消える
void test_reset_clears_state(void) {
  CoinTracker tr;
  SsEdge e[CAP];
  int n = addCoin(e, 0, 1, 250.0, 0, 100);
  Rec rec;
  run(tr, e, n, 0, 300, &rec);   // 穴 B のかたまりは閉じたが、まだ期限前
  TEST_ASSERT_EQUAL_INT(0, rec.n);
  TEST_ASSERT_EQUAL_INT(1, tr.active());
  tr.reset();
  TEST_ASSERT_EQUAL_INT(0, tr.active());
  TEST_ASSERT_EQUAL_UINT32(0, tr.stats().coins);
  CoinResult r;
  for (uint32_t ms = 300; ms < 2000; ms++) {
    tr.tick(ms * MS);
    TEST_ASSERT_FALSE(tr.poll(&r));
  }
}

// 16. 穴 B が詰まって遮られ続けても、1 秒を過ぎたら P1 を待たずに処理する（音が止まらない）
void test_B_jam_does_not_block_forever(void) {
  CoinTracker tr(true);
  SsEdge e[CAP];
  int n = 0;
  e[n].beam = SS_BEAM_HB; e[n].high = true; e[n].t_us = at(0, 100); n++;   // 落ちてこない
  n = addPulse(e, n, SS_BEAM_P1, at(0, 300), at(0, 350));
  Rec rec;
  run(tr, e, n, 0, 3000, &rec);
  TEST_ASSERT_EQUAL_INT(1, rec.n);
  TEST_ASSERT_EQUAL_INT(100, rec.r[0].value);
  TEST_ASSERT_TRUE(rec.r[0].adopted);
}

// 17. ssMakeCoinEdges：本数と並び
void test_make_edges(void) {
  SsEdge e[CAP];
  TEST_ASSERT_EQUAL_INT(2 + 2 + 6, ssMakeCoinEdges(500, 250.0, 0, true, e, CAP));
  TEST_ASSERT_EQUAL_INT(4 + 4 + 2, ssMakeCoinEdges(5, 250.0, 0, true, e, CAP));
  TEST_ASSERT_EQUAL_INT(4, ssMakeCoinEdges(50, 250.0, 0, false, e, CAP));
  TEST_ASSERT_EQUAL_INT(0, ssMakeCoinEdges(7, 250.0, 0, true, e, CAP));   // 無い金額
  TEST_ASSERT_EQUAL_INT(0, ssMakeCoinEdges(500, 250.0, 0, true, e, 4));  // 入りきらない
  int n = ssMakeCoinEdges(10, 250.0, 1000000, true, e, CAP);
  for (int i = 1; i < n; i++) TEST_ASSERT_TRUE(static_cast<int32_t>(e[i].t_us - e[i - 1].t_us) >= 0);
  // 1円の穴 A：中心 1.0s、半径 10mm ÷ 250mm/s = 40ms
  n = ssMakeCoinEdges(1, 250.0, 1000000, true, e, CAP);
  TEST_ASSERT_EQUAL_INT(SS_BEAM_HA, e[0].beam);
  TEST_ASSERT_TRUE(e[0].high);
  TEST_ASSERT_EQUAL_UINT32(960000, e[0].t_us);
}

// 18. 相方の無いまま残った穴 A のかたまりが、micros() の 1 周（約 71.6 分）後に相方と間違われない
void test_stale_A_group_after_wrap(void) {
  CoinTracker tr(true);
  tr.onEdge(SS_BEAM_HA, true, 0);         // 穴 A だけの遮光（硬貨にならない。相方の条件は満たす長さ）
  tr.onEdge(SS_BEAM_HA, false, 20 * MS);
  for (uint64_t t = 0; t < (1ull << 32); t += 1000 * MS) tr.tick(static_cast<uint32_t>(t));   // 1 周、何も来ない
  SsEdge e[CAP];
  int n = addCoin(e, 0, 1, 250.0, 0, 150, false);   // 1 周後の同じ時刻の近くに、穴 A を見落とした 1円
  Rec rec;
  run(tr, e, n, 0, 1500, &rec);
  TEST_ASSERT_EQUAL_INT(0, rec.n);                  // 古い穴 A を相方にしていない → 鳴らない
  TEST_ASSERT_EQUAL_UINT32(1, tr.stats().noA);
  TEST_ASSERT_EQUAL_UINT32(0, tr.stats().coins);
}

// 19. P1 を通った 5円が W2 へ傾いて P1 をもう一度 18ms 遮った → 拾わない（余計な 100円を鳴らさない）
//   シミュレーションで実際に出た形（落ちた後 39ms で 18ms の遮光）
void test_short_reblock_is_not_adopted(void) {
  CoinTracker tr(true);
  SsEdge e[CAP];
  int n = addCoin(e, 0, 5, 250.0, 0, 100);
  uint32_t p1Fall = 0;
  for (int i = 0; i < n; i++) {
    if (e[i].beam == SS_BEAM_P1 && !e[i].high) p1Fall = e[i].t_us;
  }
  TEST_ASSERT_TRUE(p1Fall > 0);
  n = addPulse(e, n, SS_BEAM_P1, p1Fall + 39 * MS, p1Fall + 57 * MS);
  Rec rec;
  run(tr, e, n, 0, 2000, &rec);
  TEST_ASSERT_EQUAL_INT(1, rec.n);
  TEST_ASSERT_EQUAL_INT(5, rec.r[0].value);
  TEST_ASSERT_FALSE(rec.r[0].adopted);
  TEST_ASSERT_EQUAL_UINT32(1, tr.stats().orphan);
  TEST_ASSERT_EQUAL_UINT32(0, tr.stats().adopted);
  TEST_ASSERT_EQUAL_UINT32(1, tr.stats().adoptShort);
}

// 20. 拾うかどうかは P の遮光の長さ（SS_ADOPT_MIN_MS = 40ms）で決める
//   (a) 45ms：遮られている途中で 40ms に達した時点で拾う → 段 1 から追って 100円（期限は遮り始めから）
//   (b) 30ms：光が戻った時点で短いと分かる → 拾わない
//   (c) 穴 B の詰まりで P1 の処理が遅れ、処理した時点で光が戻っていた 20ms → 拾わない
void test_adopt_needs_min_width(void) {
  {
    CoinTracker tr(true);
    SsEdge e[CAP];
    int n = addPulse(e, 0, SS_BEAM_P1, at(0, 100), at(0, 145));
    Rec rec;
    run(tr, e, n, 0, 1000, &rec);
    TEST_ASSERT_EQUAL_INT(1, rec.n);
    TEST_ASSERT_EQUAL_INT(100, rec.r[0].value);
    TEST_ASSERT_TRUE(rec.r[0].adopted);
    TEST_ASSERT_EQUAL_UINT32(at(0, 100), rec.r[0].t_in_us);
    TEST_ASSERT_UINT32_WITHIN(2, 339200, elapsed(rec.r[0]));
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().adopted);
  }
  {
    CoinTracker tr(true);
    SsEdge e[CAP];
    int n = addPulse(e, 0, SS_BEAM_P1, at(0, 100), at(0, 130));
    Rec rec;
    run(tr, e, n, 0, 1000, &rec);
    TEST_ASSERT_EQUAL_INT(0, rec.n);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().orphan);
    TEST_ASSERT_EQUAL_UINT32(0, tr.stats().adopted);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().adoptShort);
    TEST_ASSERT_EQUAL_INT(0, tr.active());
  }
  {
    CoinTracker tr(true);
    SsEdge e[CAP];
    int n = 0;
    e[n].beam = SS_BEAM_HB; e[n].high = true; e[n].t_us = at(0, 100); n++;   // 落ちてこない
    n = addPulse(e, n, SS_BEAM_P1, at(0, 300), at(0, 320));
    Rec rec;
    run(tr, e, n, 0, 3000, &rec);
    TEST_ASSERT_EQUAL_INT(0, rec.n);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().orphan);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().adoptShort);
  }
}

// =============================================================================
// 10/10 の仕様変更：穴 A と穴 B の両方を通ったと確かめられた硬貨だけを判定する
//   正常な硬貨の結果は変わらないこと（21〜23）と、それ以外では鳴らないこと（24〜35）
// =============================================================================

// 指定のビームのエッジを全部消す（そのビームの見落とし）
static int dropBeam(SsEdge* e, int n, int beam) {
  int m = 0;
  for (int i = 0; i < n; i++) {
    if (e[i].beam != beam) e[m++] = e[i];
  }
  return m;
}

// 結果が 1 つも出ず、追跡中の硬貨も残っていない
static void expectSilent(CoinTracker& tr, SsEdge* e, int n, uint32_t endMs) {
  Rec rec;
  run(tr, e, n, 0, endMs, &rec);
  TEST_ASSERT_EQUAL_INT_MESSAGE(0, rec.n, "鳴ってはいけない");
  TEST_ASSERT_EQUAL_INT(0, tr.active());
}

static int stageOfValue(int value) {
  for (int s = 0; s < 4; s++) {
    for (int h = 0; h < 2; h++) {
      if (SS_STAGE_VALUE[s][h] == value) return s;
    }
  }
  return -1;
}

// 21. 6 金種 × 速さ 7 通り（100〜600mm/s）→ 金額・段・穴・速さが正しく、異常の集計が 0
void test_normal_coins_all_speeds(void) {
  const double speeds[] = {100, 150, 200, 250, 300, 400, 600};
  for (double v : speeds) {
    for (int k = 0; k < LANE_COUNT; k++) {
      CoinTracker tr;
      SsEdge e[CAP];
      int n = addCoin(e, 0, LANE_VALUE[k], v, 0, 200);
      Rec rec;
      run(tr, e, n, 0, 3000, &rec);
      TEST_ASSERT_EQUAL_INT_MESSAGE(1, rec.n, "結果は 1 つ");
      TEST_ASSERT_EQUAL_INT(LANE_VALUE[k], rec.r[0].value);
      TEST_ASSERT_EQUAL_INT(stageOfValue(LANE_VALUE[k]), rec.r[0].stage);
      TEST_ASSERT_EQUAL(LANE_VALUE[k] == 50 || LANE_VALUE[k] == 5, rec.r[0].hole);
      TEST_ASSERT_FALSE(rec.r[0].adopted);
      TEST_ASSERT_FALSE(rec.r[0].forced);
      TEST_ASSERT_UINT32_WITHIN(static_cast<uint32_t>(v / 100) + 1, static_cast<uint32_t>(v), rec.r[0].speed_mm_s);
      TEST_ASSERT_EQUAL_UINT32(1, tr.stats().coins);
      TEST_ASSERT_EQUAL_UINT32(0, tr.stats().noA);
      TEST_ASSERT_EQUAL_UINT32(0, tr.stats().aBad);
      TEST_ASSERT_EQUAL_UINT32(0, tr.stats().orphan);
      TEST_ASSERT_EQUAL_UINT32(0, tr.stats().longB);
      TEST_ASSERT_EQUAL_INT(0, tr.active());
    }
  }
}

// 22. 12 枚を 0.4 秒おきに続けて（金種を順に 2 周）→ 全部正しい順で正しい金額
void test_consecutive_coins(void) {
  CoinTracker tr;
  SsEdge e[CAP];
  int n = 0;
  const int N = 12;
  for (int i = 0; i < N; i++) n = addCoin(e, n, LANE_VALUE[i % LANE_COUNT], 250.0, 0, 100 + 400 * i);
  Rec rec;
  run(tr, e, n, 0, 100 + 400 * N + 1500, &rec);
  TEST_ASSERT_EQUAL_INT(N, rec.n);
  for (int i = 0; i < N; i++) TEST_ASSERT_EQUAL_INT(LANE_VALUE[i % LANE_COUNT], rec.r[i].value);
  TEST_ASSERT_EQUAL_UINT32(N, tr.stats().coins);
  TEST_ASSERT_EQUAL_UINT32(0, tr.stats().noA);
  TEST_ASSERT_EQUAL_UINT32(0, tr.stats().orphan);
}

// 23. 2 枚を 270ms の間隔で（36 通りの組み合わせ・250mm/s）→ 2 枚とも正しい
void test_two_coins_270ms_all_pairs(void) {
  for (int a = 0; a < LANE_COUNT; a++) {
    for (int b = 0; b < LANE_COUNT; b++) {
      CoinTracker tr;
      SsEdge e[CAP];
      int n = addCoin(e, 0, LANE_VALUE[a], 250.0, 0, 100);
      n = addCoin(e, n, LANE_VALUE[b], 250.0, 0, 370);
      Rec rec;
      run(tr, e, n, 0, 2500, &rec);
      TEST_ASSERT_EQUAL_INT_MESSAGE(2, rec.n, "2 枚とも鳴る");
      TEST_ASSERT_EQUAL_INT(LANE_VALUE[a], rec.r[0].value);
      TEST_ASSERT_EQUAL_INT(LANE_VALUE[b], rec.r[1].value);
    }
  }
}

// 24. P だけが遮られた（P1 ／ P1→P2 ／ P1→P2→P3）→ 鳴らない。既定では拾わない（SS_ADOPT_ORPHAN=false）
//   遮光は 60ms（拾う下限 SS_ADOPT_MIN_MS より長い。拾う設定なら鳴る長さ）
void test_P_only_is_silent(void) {
  TEST_ASSERT_FALSE(SS_ADOPT_ORPHAN);
  for (int last = SS_BEAM_P1; last <= SS_BEAM_P3; last++) {
    CoinTracker tr;
    SsEdge e[CAP];
    int n = 0;
    for (int b = SS_BEAM_P1; b <= last; b++) {
      const double t0 = 100 + 150 * (b - SS_BEAM_P1);
      n = addPulse(e, n, b, at(0, t0), at(0, t0 + 60));
    }
    expectSilent(tr, e, n, 2000);
    TEST_ASSERT_EQUAL_UINT32(static_cast<uint32_t>(last - SS_BEAM_P1 + 1), tr.stats().orphan);
    TEST_ASSERT_EQUAL_UINT32(0, tr.stats().adopted);
    TEST_ASSERT_EQUAL_UINT32(0, tr.stats().coins);
  }
}

// 25. 穴 B から先だけ（穴 A を見落とした硬貨）→ 鳴らない。P は誰にも当たらない
void test_B_without_A_is_silent(void) {
  const int values[] = {500, 50, 10};
  const uint32_t pCount[] = {3, 0, 2};
  for (int i = 0; i < 3; i++) {
    CoinTracker tr;
    SsEdge e[CAP];
    int n = addCoin(e, 0, values[i], 250.0, 0, 100, false);
    expectSilent(tr, e, n, 2000);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().noA);
    TEST_ASSERT_EQUAL_UINT32(0, tr.stats().coins);
    TEST_ASSERT_EQUAL_UINT32(pCount[i], tr.stats().orphan);
  }
}

// 26. 穴 A（と P）だけ（穴 B を見落とした硬貨・穴 A のノイズ）→ 鳴らない
void test_A_without_B_is_silent(void) {
  const int values[] = {500, 1, 5};
  for (int i = 0; i < 3; i++) {
    CoinTracker tr;
    SsEdge e[CAP];
    int n = addCoin(e, 0, values[i], 250.0, 0, 100);
    n = dropBeam(e, n, SS_BEAM_HB);
    expectSilent(tr, e, n, 2000);
    TEST_ASSERT_EQUAL_UINT32(0, tr.stats().coins);
  }
  {   // 穴 A だけの 30ms のノイズ
    CoinTracker tr;
    SsEdge e[CAP];
    int n = addPulse(e, 0, SS_BEAM_HA, at(0, 100), at(0, 130));
    expectSilent(tr, e, n, 2000);
  }
}

// 27. 穴 B → 穴 A の逆順（逆向きに転がった・別々のノイズ）→ 鳴らない
void test_B_then_A_is_silent(void) {
  {   // 離れて逆順
    CoinTracker tr;
    SsEdge e[CAP];
    int n = addPulse(e, 0, SS_BEAM_HB, at(0, 100), at(0, 190));
    n = addPulse(e, n, SS_BEAM_HA, at(0, 214), at(0, 304));
    expectSilent(tr, e, n, 2000);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().noA);
  }
  {   // 重なって逆順（穴 A が後から始まる）
    CoinTracker tr;
    SsEdge e[CAP];
    int n = addPulse(e, 0, SS_BEAM_HB, at(0, 100), at(0, 200));
    n = addPulse(e, n, SS_BEAM_HA, at(0, 150), at(0, 250));
    expectSilent(tr, e, n, 2000);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().noA);
  }
}

// 28. ちらつき：穴 B の 15ms を 400ms おきに 20 回 ／ 穴 A と穴 B が同時に ／ 穴 A が 10ms 先 → 鳴らない
void test_flicker_trains_are_silent(void) {
  for (int mode = 0; mode < 3; mode++) {
    CoinTracker tr;
    SsEdge e[CAP];
    int n = 0;
    for (int i = 0; i < 20; i++) {
      const double t0 = 100 + 400 * i;
      n = addPulse(e, n, SS_BEAM_HB, at(0, t0), at(0, t0 + 15));
      if (mode == 1) n = addPulse(e, n, SS_BEAM_HA, at(0, t0), at(0, t0 + 15));
      if (mode == 2) n = addPulse(e, n, SS_BEAM_HA, at(0, t0 - 10), at(0, t0 + 5));
    }
    expectSilent(tr, e, n, 100 + 400 * 20 + 1000);
    TEST_ASSERT_EQUAL_UINT32(20, tr.stats().flicker);
    TEST_ASSERT_EQUAL_UINT32(0, tr.stats().coins);
  }
}

// 29. 穴 A と穴 B がほぼ同時に 25ms 遮られた（電気的なノイズ・同時に横切る影）→ 鳴らない
//   時間差 0ms と 3ms（SS_V_MIN_DT_MS = 5ms 以下＝14mm を 2.8m/s 以上で通ったことになる）
void test_A_and_B_simultaneous_is_silent(void) {
  const double lags[] = {0, 3};
  for (double lag : lags) {
    CoinTracker tr;
    SsEdge e[CAP];
    int n = addPulse(e, 0, SS_BEAM_HA, at(0, 100), at(0, 125));
    n = addPulse(e, n, SS_BEAM_HB, at(0, 100 + lag), at(0, 125 + lag));
    expectSilent(tr, e, n, 2000);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().noA);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().aBad);
  }
}

// 30. 穴 A の 10ms のちらつき＋穴 A を見落とした硬貨 → ちらつきは相方にしない → 鳴らない
void test_A_flicker_is_not_partner(void) {
  CoinTracker tr;
  SsEdge e[CAP];
  int n = addCoin(e, 0, 100, 250.0, 0, 100, false);   // 穴 B は 109ms から
  n = addPulse(e, n, SS_BEAM_HA, at(0, 60), at(0, 70));
  expectSilent(tr, e, n, 2000);
  TEST_ASSERT_EQUAL_UINT32(1, tr.stats().noA);
  TEST_ASSERT_EQUAL_UINT32(1, tr.stats().aBad);
}

// 31. 穴 A の長い遮光・終わり方のおかしい穴 A は相方にしない → 鳴らない
//   (a) 穴 A が遮られたまま、穴 B を 50ms の影が通った
//   (b) 穴 A が 1.1 秒（SS_BEAM_JAM_MS 以上）遮られてから戻った
//   (c) 穴 A の光が戻ったのが穴 B より後（硬貨なら穴 A の方が先に抜ける）
void test_bad_A_is_not_partner(void) {
  {
    CoinTracker tr;
    SsEdge e[CAP];
    int n = 0;
    e[n].beam = SS_BEAM_HA; e[n].high = true; e[n].t_us = at(0, 0); n++;
    n = addPulse(e, n, SS_BEAM_HB, at(0, 100), at(0, 150));
    expectSilent(tr, e, n, 2000);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().aBad);
  }
  {
    CoinTracker tr;
    SsEdge e[CAP];
    int n = addPulse(e, 0, SS_BEAM_HA, at(0, 0), at(0, 1100));
    n = addPulse(e, n, SS_BEAM_HB, at(0, 400), at(0, 1150));
    expectSilent(tr, e, n, 3000);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().aBad);
  }
  {
    CoinTracker tr;
    SsEdge e[CAP];
    int n = addPulse(e, 0, SS_BEAM_HA, at(0, 0), at(0, 200));
    n = addPulse(e, n, SS_BEAM_HB, at(0, 50), at(0, 150));
    expectSilent(tr, e, n, 2000);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().aBad);
  }
}

// 32. 穴 B が 1.5 秒遮られた → 硬貨にしない（穴 A があっても）。そのあとの硬貨は正しく鳴る
void test_long_B_is_silent(void) {
  {
    CoinTracker tr;
    SsEdge e[CAP];
    int n = addPulse(e, 0, SS_BEAM_HB, at(0, 100), at(0, 1600));
    expectSilent(tr, e, n, 3000);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().longB);
    TEST_ASSERT_EQUAL_UINT32(0, tr.stats().coins);
  }
  {
    CoinTracker tr;
    SsEdge e[CAP];
    int n = addPulse(e, 0, SS_BEAM_HA, at(0, 0), at(0, 90));
    n = addPulse(e, n, SS_BEAM_HB, at(0, 50), at(0, 1550));
    n = addCoin(e, n, 100, 250.0, 0, 2500);
    Rec rec;
    run(tr, e, n, 0, 4000, &rec);
    TEST_ASSERT_EQUAL_INT(1, rec.n);
    TEST_ASSERT_EQUAL_INT(100, rec.r[0].value);
    TEST_ASSERT_FALSE(rec.r[0].adopted);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().longB);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().coins);
  }
}

// 33. 手で全ビームを 2 秒遮った（同時に ／ 10ms ずつずれて）→ 鳴らない
void test_hand_over_all_beams_is_silent(void) {
  for (int stagger = 0; stagger <= 10; stagger += 10) {
    CoinTracker tr;
    SsEdge e[CAP];
    int n = 0;
    for (int b = 0; b < SS_BEAM_COUNT; b++) {
      n = addPulse(e, n, b, at(0, 100 + stagger * b), at(0, 2100 + stagger * b));
    }
    expectSilent(tr, e, n, 4000);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().longB);
    TEST_ASSERT_EQUAL_UINT32(0, tr.stats().coins);
  }
}

// 34. 正常な硬貨の後に P だけのノイズ（P1・P2・P3 を 60ms ずつ）→ 鳴るのは硬貨の 1 回だけ
void test_coin_then_P_noise(void) {
  CoinTracker tr;
  SsEdge e[CAP];
  int n = addCoin(e, 0, 100, 250.0, 0, 100);
  n = addPulse(e, n, SS_BEAM_P1, at(0, 1800), at(0, 1860));
  n = addPulse(e, n, SS_BEAM_P2, at(0, 1950), at(0, 2010));
  n = addPulse(e, n, SS_BEAM_P3, at(0, 2100), at(0, 2160));
  Rec rec;
  run(tr, e, n, 0, 3500, &rec);
  TEST_ASSERT_EQUAL_INT(1, rec.n);
  TEST_ASSERT_EQUAL_INT(100, rec.r[0].value);
  TEST_ASSERT_EQUAL_UINT32(3, tr.stats().orphan);
  TEST_ASSERT_EQUAL_INT(0, tr.active());
}

// 35. 硬貨の後ろで P が遮り直した（既定の設定）→ 余計な音は出ない
//   P1 を通った 5円が W2 へ傾いて P1 を 50ms 遮り直す（拾う下限 40ms より長い）／ 500円の後ろで P3 を 50ms
void test_reblock_behind_coin_default(void) {
  const int values[] = {5, 500};
  const int beams[] = {SS_BEAM_P1, SS_BEAM_P3};
  for (int i = 0; i < 2; i++) {
    CoinTracker tr;
    SsEdge e[CAP];
    int n = addCoin(e, 0, values[i], 250.0, 0, 100);
    uint32_t fall = 0;
    for (int k = 0; k < n; k++) {
      if (e[k].beam == beams[i] && !e[k].high) fall = e[k].t_us;
    }
    TEST_ASSERT_TRUE(fall > 0);
    n = addPulse(e, n, beams[i], fall + 39 * MS, fall + 89 * MS);
    Rec rec;
    run(tr, e, n, 0, 2500, &rec);
    TEST_ASSERT_EQUAL_INT(1, rec.n);
    TEST_ASSERT_EQUAL_INT(values[i], rec.r[0].value);
    TEST_ASSERT_EQUAL_UINT32(1, tr.stats().orphan);
    TEST_ASSERT_EQUAL_UINT32(0, tr.stats().adopted);
  }
}

// 36. 穴 A を見落とした硬貨は、前の硬貨の（使用済みの）穴 A を相方にしない → 1 枚目だけ鳴る
void test_missed_A_does_not_reuse_previous_A(void) {
  CoinTracker tr;
  SsEdge e[CAP];
  int n = addCoin(e, 0, 10, 250.0, 0, 100);
  n = addCoin(e, n, 100, 250.0, 0, 400, false);
  Rec rec;
  run(tr, e, n, 0, 2500, &rec);
  TEST_ASSERT_EQUAL_INT(1, rec.n);
  TEST_ASSERT_EQUAL_INT(10, rec.r[0].value);
  TEST_ASSERT_EQUAL_UINT32(1, tr.stats().noA);
}

// =============================================================================
// 10/10 方式 S：ビームの上で止まってから動き出した硬貨
//   期限は「ビームから抜けた時刻」から数え直す。P を遮っている間は SS_STALL_CAP_MS まで待つ
// =============================================================================

// 硬貨が beam の上で stallMs 止まった形にする（beam の最後の光が戻るエッジ以降を、全部 stallMs 遅らせる）
static int stallOn(SsEdge* e, int n, int beam, uint32_t stallMs) {
  uint32_t tf = 0;
  bool found = false;
  for (int i = 0; i < n; i++) {
    if (e[i].beam == beam && !e[i].high && (!found || static_cast<int32_t>(e[i].t_us - tf) > 0)) {
      tf = e[i].t_us;
      found = true;
    }
  }
  TEST_ASSERT_TRUE(found);
  for (int i = 0; i < n; i++) {
    if (static_cast<int32_t>(e[i].t_us - tf) >= 0) e[i].t_us += stallMs * MS;
  }
  return n;
}

// 37. P の上で止まってから動く（P1・P2 の上で 0.3〜2.5 秒）→ 金額は止まらなかったときと同じ
void test_stall_on_P_then_go(void) {
  const int values[] = {100, 5, 10, 500};
  const int beams[] = {SS_BEAM_P1, SS_BEAM_P2};
  const uint32_t stalls[] = {300, 600, 1500, 2500};
  for (int b : beams) {
    for (int value : values) {
      if (stageOfValue(value) < b - SS_BEAM_HB) continue;   // その P まで行かない硬貨
      for (uint32_t s : stalls) {
        CoinTracker tr;
        SsEdge e[CAP];
        int n = addCoin(e, 0, value, 250.0, 0, 100);
        n = stallOn(e, n, b, s);
        Rec rec;
        run(tr, e, n, 0, 5000, &rec);
        TEST_ASSERT_EQUAL_INT_MESSAGE(1, rec.n, "結果は 1 つ");
        TEST_ASSERT_EQUAL_INT(value, rec.r[0].value);
        TEST_ASSERT_EQUAL_UINT32(0, tr.stats().orphan);
        TEST_ASSERT_EQUAL_INT(0, tr.active());
      }
    }
  }
}

// 38. 穴 B の上で 0.5 秒止まってから動く（6 金種）→ 金額は止まらなかったときと同じ
void test_stall_on_B_then_go(void) {
  for (int k = 0; k < LANE_COUNT; k++) {
    CoinTracker tr;
    SsEdge e[CAP];
    int n = addCoin(e, 0, LANE_VALUE[k], 250.0, 0, 100);
    n = stallOn(e, n, SS_BEAM_HB, 500);
    Rec rec;
    run(tr, e, n, 0, 4000, &rec);
    TEST_ASSERT_EQUAL_INT_MESSAGE(1, rec.n, "結果は 1 つ");
    TEST_ASSERT_EQUAL_INT(LANE_VALUE[k], rec.r[0].value);
    TEST_ASSERT_EQUAL_UINT32(0, tr.stats().orphan);
    TEST_ASSERT_EQUAL_INT(0, tr.active());
  }
}

// 39. P1 を遮ったまま動かない（10円が P1 の上で 5 秒）→ SS_STALL_CAP_MS までは待ち、過ぎたら決める（1 回だけ）
void test_stall_cap(void) {
  SsEdge base[CAP];
  int n0 = addCoin(base, 0, 10, 250.0, 0, 100);
  n0 = stallOn(base, n0, SS_BEAM_P1, 5000);
  uint32_t p1Rise = 0;
  for (int i = 0; i < n0; i++) {
    if (base[i].beam == SS_BEAM_P1 && base[i].high) p1Rise = base[i].t_us;
  }
  TEST_ASSERT_TRUE(p1Rise > 0);
  const uint32_t riseMs = p1Rise / MS;
  {   // 上限の少し前：まだ決めていない
    CoinTracker tr;
    SsEdge e[CAP];
    for (int i = 0; i < n0; i++) e[i] = base[i];
    Rec rec;
    run(tr, e, n0, 0, riseMs + SS_STALL_CAP_MS - 50, &rec);
    TEST_ASSERT_EQUAL_INT(0, rec.n);
    TEST_ASSERT_EQUAL_INT(1, tr.active());
  }
  {   // 上限を過ぎた（P1 はまだ遮られている）：段 1 で決まる
    CoinTracker tr;
    SsEdge e[CAP];
    for (int i = 0; i < n0; i++) e[i] = base[i];
    Rec rec;
    run(tr, e, n0, 0, riseMs + SS_STALL_CAP_MS + 50, &rec);
    TEST_ASSERT_EQUAL_INT(1, rec.n);
    TEST_ASSERT_EQUAL_INT(1, rec.r[0].stage);
    TEST_ASSERT_TRUE(rec.r[0].byTimeout);
    TEST_ASSERT_EQUAL_INT(0, tr.active());
  }
  {   // 最後まで：鳴るのは 1 回だけ（あとの P2・P3 は拾わない）
    CoinTracker tr;
    SsEdge e[CAP];
    for (int i = 0; i < n0; i++) e[i] = base[i];
    Rec rec;
    run(tr, e, n0, 0, 8000, &rec);
    TEST_ASSERT_EQUAL_INT(1, rec.n);
    TEST_ASSERT_EQUAL_INT(0, tr.active());
  }
}

// 40. 止まらない硬貨の判定の時刻は変わらない（100円：P1 から段 1 の期限 339.2ms ちょうどで決まる）
void test_no_stall_timing_unchanged(void) {
  CoinTracker tr;
  SsEdge e[CAP];
  int n = addCoin(e, 0, 100, 250.0, 0, 100);
  uint32_t p1Rise = 0;
  for (int i = 0; i < n; i++) {
    if (e[i].beam == SS_BEAM_P1 && e[i].high) p1Rise = e[i].t_us;
  }
  Rec rec;
  run(tr, e, n, 0, 2000, &rec);
  TEST_ASSERT_EQUAL_INT(1, rec.n);
  TEST_ASSERT_EQUAL_INT(100, rec.r[0].value);
  TEST_ASSERT_UINT32_WITHIN(2 * MS, p1Rise + 339 * MS, rec.r[0].t_decided_us);
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_each_value_single);
  RUN_TEST(test_flicker_on_B_is_ignored);
  RUN_TEST(test_hole_seen_on_one_beam_is_enough);
  RUN_TEST(test_no_A_is_not_a_coin);
  RUN_TEST(test_deadline_follows_speed);
  RUN_TEST(test_two_coins_in_flight);
  RUN_TEST(test_fast_coin_P1_waits_for_B_group);
  RUN_TEST(test_short_P_glitch_is_ignored);
  RUN_TEST(test_orphan_P3);
  RUN_TEST(test_orphan_P1_is_adopted_and_expires);
  RUN_TEST(test_nearest_prediction_and_older_resolved);
  RUN_TEST(test_overflow_forces_oldest);
  RUN_TEST(test_micros_wraparound);
  RUN_TEST(test_touching_coins_adoption);
  RUN_TEST(test_reset_clears_state);
  RUN_TEST(test_B_jam_does_not_block_forever);
  RUN_TEST(test_make_edges);
  RUN_TEST(test_stale_A_group_after_wrap);
  RUN_TEST(test_short_reblock_is_not_adopted);
  RUN_TEST(test_adopt_needs_min_width);
  RUN_TEST(test_normal_coins_all_speeds);
  RUN_TEST(test_consecutive_coins);
  RUN_TEST(test_two_coins_270ms_all_pairs);
  RUN_TEST(test_P_only_is_silent);
  RUN_TEST(test_B_without_A_is_silent);
  RUN_TEST(test_A_without_B_is_silent);
  RUN_TEST(test_B_then_A_is_silent);
  RUN_TEST(test_flicker_trains_are_silent);
  RUN_TEST(test_A_and_B_simultaneous_is_silent);
  RUN_TEST(test_A_flicker_is_not_partner);
  RUN_TEST(test_bad_A_is_not_partner);
  RUN_TEST(test_long_B_is_silent);
  RUN_TEST(test_hand_over_all_beams_is_silent);
  RUN_TEST(test_coin_then_P_noise);
  RUN_TEST(test_reblock_behind_coin_default);
  RUN_TEST(test_missed_A_does_not_reuse_previous_A);
  RUN_TEST(test_stall_on_P_then_go);
  RUN_TEST(test_stall_on_B_then_go);
  RUN_TEST(test_stall_cap);
  RUN_TEST(test_no_stall_timing_unchanged);
  return UNITY_END();
}
