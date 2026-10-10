// =============================================================================
// LaneDecoder の単体テスト（Task 2・v2.1：幅つきパルス）
//
// 仕様：開発計画_ClaudeCode用.md Task 2 ／ CLAUDE.md §3
// 実機なしで PC 上で走る（pio test -e native）。Arduino API は使わない。
// v2.1：割込を CHANGE にして ISR で HIGH の幅を測るようになったので、
//       LaneDecoder はパルス（レーン・立ち上がり時刻・HIGH 幅）を受け取り、
//       ノイズ（幅が短い）の除去もここで行う。
// =============================================================================
#include <unity.h>
#include "Config.h"
#include "LaneDecoder.h"

// テストでは値を固定する（Config.h の暫定値に依存しない）
static const uint32_t HOLDOFF  = 150;     // ms
static const uint32_t MIN_HIGH = 2000;    // us
static const uint32_t COIN     = 10000;   // 硬貨らしい幅（10ms）

static LanePulse pulse(int lane, uint32_t t_ms, uint32_t width_us = COIN) {
  LanePulse p;
  p.lane = lane;
  p.t_ms = t_ms;
  p.width_us = width_us;
  return p;
}

void setUp(void) {}
void tearDown(void) {}

// 1. レーン0 の1回のパルス → 500円・track 1 が返る
void test_lane0_single_pulse_is_500yen(void) {
  LaneDecoder d(HOLDOFF, MIN_HIGH);
  CoinEvent c{};
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(0, 1000), &c));
  TEST_ASSERT_EQUAL_INT(0, c.lane);
  TEST_ASSERT_EQUAL_INT(500, c.value);
  TEST_ASSERT_EQUAL_INT(1, c.track);
  TEST_ASSERT_EQUAL_UINT32(1000, c.t_ms);
  TEST_ASSERT_EQUAL(LaneDecoder::Reason::Accepted, d.lastReason());
}

// 2. 全レーンが Config.h の対応表（LANE_VALUE / LANE_TRACK）と一致。レーン5 → 1円・track 6
void test_all_lanes_match_config_table(void) {
  for (int lane = 0; lane < LANE_COUNT; ++lane) {
    LaneDecoder d(HOLDOFF, MIN_HIGH);
    CoinEvent c{};
    TEST_ASSERT_TRUE(d.onLanePulse(pulse(lane, 500), &c));
    TEST_ASSERT_EQUAL_INT(lane, c.lane);
    TEST_ASSERT_EQUAL_INT(LANE_VALUE[lane], c.value);
    TEST_ASSERT_EQUAL_INT(LANE_TRACK[lane], c.track);
  }
  LaneDecoder d(HOLDOFF, MIN_HIGH);
  CoinEvent c{};
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(5, 500), &c));
  TEST_ASSERT_EQUAL_INT(1, c.value);
  TEST_ASSERT_EQUAL_INT(6, c.track);
}

// 3. 同一レーンで holdoff 内（30ms 後）の2回目は無視する（穴あき硬貨・跳ねの二重検出）
void test_same_lane_within_holdoff_is_ignored(void) {
  LaneDecoder d(HOLDOFF, MIN_HIGH);
  CoinEvent c{};
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(2, 1000), &c));
  TEST_ASSERT_FALSE(d.onLanePulse(pulse(2, 1030), &c));
  TEST_ASSERT_EQUAL(LaneDecoder::Reason::Holdoff, d.lastReason());
  TEST_ASSERT_EQUAL_UINT32(30, d.lastElapsedMs());   // ログ IGNORE (holdoff 30ms) 用
}

// 3b. 無視したパルスは不感時間の起点にならない（起点は最後に「受理した」時刻）
void test_ignored_pulse_does_not_extend_holdoff(void) {
  LaneDecoder d(HOLDOFF, MIN_HIGH);
  CoinEvent c{};
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(2, 1000), &c));
  TEST_ASSERT_FALSE(d.onLanePulse(pulse(2, 1030), &c));
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(2, 1160), &c));
  TEST_ASSERT_EQUAL_UINT32(1160, c.t_ms);
}

// 4. 同一レーンで holdoff を超えた2回目（400ms 後）は受理する
void test_same_lane_after_holdoff_is_accepted(void) {
  LaneDecoder d(HOLDOFF, MIN_HIGH);
  CoinEvent c{};
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(3, 1000), &c));
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(3, 1400), &c));
  TEST_ASSERT_EQUAL_INT(10, c.value);
  TEST_ASSERT_EQUAL_UINT32(400, d.lastElapsedMs());
}

// 4b. 境界：holdoff-1 は無視、holdoff 丁度は受理
void test_holdoff_boundary(void) {
  LaneDecoder d(HOLDOFF, MIN_HIGH);
  CoinEvent c{};
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(1, 1000), &c));
  TEST_ASSERT_FALSE(d.onLanePulse(pulse(1, 1000 + HOLDOFF - 1), &c));
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(1, 1000 + HOLDOFF), &c));
}

// 5. 別レーンなら holdoff 内でも受理する（2枚目が別金種で連続投入）
void test_other_lane_within_holdoff_is_accepted(void) {
  LaneDecoder d(HOLDOFF, MIN_HIGH);
  CoinEvent c{};
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(0, 1000), &c));
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(4, 1050), &c));
  TEST_ASSERT_EQUAL_INT(5, c.value);
  TEST_ASSERT_EQUAL_INT(5, c.track);
}

// 6. 範囲外のレーン（-1, 6）は無視して false。out は書き換えない
void test_out_of_range_lane_is_rejected(void) {
  LaneDecoder d(HOLDOFF, MIN_HIGH);
  CoinEvent c{};
  c.value = -1;
  TEST_ASSERT_FALSE(d.onLanePulse(pulse(-1, 1000), &c));
  TEST_ASSERT_EQUAL(LaneDecoder::Reason::OutOfRange, d.lastReason());
  TEST_ASSERT_FALSE(d.onLanePulse(pulse(LANE_COUNT, 1000), &c));
  TEST_ASSERT_EQUAL(LaneDecoder::Reason::OutOfRange, d.lastReason());
  TEST_ASSERT_EQUAL_INT(-1, c.value);
}

// 7. 時刻が巻き戻っても落ちない（millis() の 32bit オーバーフロー相当）
void test_time_wraparound(void) {
  LaneDecoder d(HOLDOFF, MIN_HIGH);
  CoinEvent c{};
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(2, 0xFFFFFFF0u), &c));
  TEST_ASSERT_FALSE(d.onLanePulse(pulse(2, 0x00000010u), &c));   // 巻き戻り後 32ms：不感時間内
  TEST_ASSERT_EQUAL_UINT32(32, d.lastElapsedMs());
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(2, 0x00000200u), &c));    // 巻き戻り後 528ms：受理
}

// 8. reset() 後は holdoff が解除される
void test_reset_clears_holdoff(void) {
  LaneDecoder d(HOLDOFF, MIN_HIGH);
  CoinEvent c{};
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(5, 1000), &c));
  d.reset();
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(5, 1010), &c));
}

// 9. holdoff = 0 なら同一レーンの連続でも全部受理する（設定で無効化できる）
void test_zero_holdoff_accepts_everything(void) {
  LaneDecoder d(0, MIN_HIGH);
  CoinEvent c{};
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(0, 1000), &c));
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(0, 1000), &c));
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(0, 1001), &c));
}

// 10. out が nullptr でも判定だけは行う（落ちない）
void test_null_out_pointer_is_safe(void) {
  LaneDecoder d(HOLDOFF, MIN_HIGH);
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(1, 1000), nullptr));
  TEST_ASSERT_FALSE(d.onLanePulse(pulse(1, 1010), nullptr));
}

// 11. 幅が min_high_us 未満のパルスはノイズとして捨てる。ノイズは不感時間の起点にもならない
void test_short_pulse_is_noise_and_does_not_start_holdoff(void) {
  LaneDecoder d(HOLDOFF, MIN_HIGH);
  CoinEvent c{};
  c.value = -1;
  TEST_ASSERT_FALSE(d.onLanePulse(pulse(3, 1000, 300), &c));       // 0.3ms
  TEST_ASSERT_EQUAL(LaneDecoder::Reason::Noise, d.lastReason());
  TEST_ASSERT_EQUAL_INT(-1, c.value);
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(3, 1010, COIN), &c));       // 10ms 後の本物は受理
  TEST_ASSERT_EQUAL_INT(10, c.value);
}

// 12. 幅の境界：min_high_us 丁度は受理、min_high_us-1 はノイズ
void test_min_high_boundary(void) {
  LaneDecoder d(HOLDOFF, MIN_HIGH);
  CoinEvent c{};
  TEST_ASSERT_FALSE(d.onLanePulse(pulse(0, 1000, MIN_HIGH - 1), &c));
  TEST_ASSERT_EQUAL(LaneDecoder::Reason::Noise, d.lastReason());
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(0, 1000, MIN_HIGH), &c));
}

// 13. min_high_us = 0 なら幅 0 でも受理する（設定で無効化できる）
void test_zero_min_high_accepts_any_width(void) {
  LaneDecoder d(HOLDOFF, 0);
  CoinEvent c{};
  TEST_ASSERT_TRUE(d.onLanePulse(pulse(0, 1000, 0), &c));
}

// 14. 範囲外レーンの判定はノイズ判定より先（レーン -1 で幅が短くても OutOfRange）
void test_out_of_range_checked_before_noise(void) {
  LaneDecoder d(HOLDOFF, MIN_HIGH);
  TEST_ASSERT_FALSE(d.onLanePulse(pulse(-1, 1000, 1), nullptr));
  TEST_ASSERT_EQUAL(LaneDecoder::Reason::OutOfRange, d.lastReason());
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_lane0_single_pulse_is_500yen);
  RUN_TEST(test_all_lanes_match_config_table);
  RUN_TEST(test_same_lane_within_holdoff_is_ignored);
  RUN_TEST(test_ignored_pulse_does_not_extend_holdoff);
  RUN_TEST(test_same_lane_after_holdoff_is_accepted);
  RUN_TEST(test_holdoff_boundary);
  RUN_TEST(test_other_lane_within_holdoff_is_accepted);
  RUN_TEST(test_out_of_range_lane_is_rejected);
  RUN_TEST(test_time_wraparound);
  RUN_TEST(test_reset_clears_holdoff);
  RUN_TEST(test_zero_holdoff_accepts_everything);
  RUN_TEST(test_null_out_pointer_is_safe);
  RUN_TEST(test_short_pulse_is_noise_and_does_not_start_holdoff);
  RUN_TEST(test_min_high_boundary);
  RUN_TEST(test_zero_min_high_accepts_any_width);
  RUN_TEST(test_out_of_range_checked_before_noise);
  return UNITY_END();
}
