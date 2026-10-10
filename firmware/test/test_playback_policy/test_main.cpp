// =============================================================================
// PlaybackPolicy の単体テスト（Task 3）
//
// 仕様：開発計画_ClaudeCode用.md Task 3 ／ CLAUDE.md §3「再生ポリシー」
// 実機なしで PC 上で走る（pio test -e native）。Arduino API は使わない。
// =============================================================================
#include <unity.h>
#include "PlaybackPolicy.h"

static const uint32_t RETRIG = 300;   // テストでは固定（Config.h の RETRIG_MS に依存しない）

void setUp(void) {}
void tearDown(void) {}

// 1. 起動直後の1回目は必ず true（起動音を鳴らすため）
void test_first_call_is_true(void) {
  PlaybackPolicy p(RETRIG);
  TEST_ASSERT_TRUE(p.shouldPlay(0));
}

// 1b. 起動直後の1回目は now が 0 でなくても true
void test_first_call_is_true_at_any_time(void) {
  PlaybackPolicy p(RETRIG);
  TEST_ASSERT_TRUE(p.shouldPlay(123456));
}

// 2. 直後（0ms 後）の2回目は false
void test_second_call_immediately_is_false(void) {
  PlaybackPolicy p(RETRIG);
  TEST_ASSERT_TRUE(p.shouldPlay(1000));
  TEST_ASSERT_FALSE(p.shouldPlay(1000));
}

// 3. retriggerMs-1 経過では false
void test_just_before_retrigger_is_false(void) {
  PlaybackPolicy p(RETRIG);
  TEST_ASSERT_TRUE(p.shouldPlay(1000));
  TEST_ASSERT_FALSE(p.shouldPlay(1000 + RETRIG - 1));
}

// 4. retriggerMs 丁度で true
void test_exactly_retrigger_is_true(void) {
  PlaybackPolicy p(RETRIG);
  TEST_ASSERT_TRUE(p.shouldPlay(1000));
  TEST_ASSERT_TRUE(p.shouldPlay(1000 + RETRIG));
}

// 5. retriggerMs 経過して true を返した後、また直後に呼ぶと false（起点が更新されている）
void test_after_replay_guard_restarts(void) {
  PlaybackPolicy p(RETRIG);
  TEST_ASSERT_TRUE(p.shouldPlay(1000));
  TEST_ASSERT_TRUE(p.shouldPlay(1000 + RETRIG));
  TEST_ASSERT_FALSE(p.shouldPlay(1000 + RETRIG + 10));
}

// 5b. false を返した呼び出しは起点を動かさない（連打しても最初の再生から retriggerMs で解除される）
void test_rejected_call_does_not_move_origin(void) {
  PlaybackPolicy p(RETRIG);
  TEST_ASSERT_TRUE(p.shouldPlay(1000));
  TEST_ASSERT_FALSE(p.shouldPlay(1200));
  TEST_ASSERT_TRUE(p.shouldPlay(1000 + RETRIG));
}

// 6. millis() の 32bit オーバーフローをまたいでも正しく判定する
void test_time_wraparound(void) {
  PlaybackPolicy p(RETRIG);
  TEST_ASSERT_TRUE(p.shouldPlay(0xFFFFFF00u));
  TEST_ASSERT_FALSE(p.shouldPlay(0x00000010u));                 // 巻き戻り後 272ms：ガード内
  TEST_ASSERT_EQUAL_UINT32(272, p.sinceLastPlay(0x00000010u));
  TEST_ASSERT_TRUE(p.shouldPlay(0x00000100u));                  // 巻き戻り後 512ms：再生
}

// 7. reset() 後は次の呼び出しが true
void test_reset_allows_immediate_play(void) {
  PlaybackPolicy p(RETRIG);
  TEST_ASSERT_TRUE(p.shouldPlay(1000));
  p.reset();
  TEST_ASSERT_TRUE(p.shouldPlay(1001));
}

// 8. sinceLastPlay：再生後の経過を返す。まだ一度も再生していなければ UINT32_MAX
void test_since_last_play(void) {
  PlaybackPolicy p(RETRIG);
  TEST_ASSERT_EQUAL_UINT32(0xFFFFFFFFu, p.sinceLastPlay(5000));
  TEST_ASSERT_TRUE(p.shouldPlay(1000));
  TEST_ASSERT_EQUAL_UINT32(0, p.sinceLastPlay(1000));
  TEST_ASSERT_EQUAL_UINT32(120, p.sinceLastPlay(1120));         // ログ "DISCARD (retrig 120ms)" 用
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_first_call_is_true);
  RUN_TEST(test_first_call_is_true_at_any_time);
  RUN_TEST(test_second_call_immediately_is_false);
  RUN_TEST(test_just_before_retrigger_is_false);
  RUN_TEST(test_exactly_retrigger_is_true);
  RUN_TEST(test_after_replay_guard_restarts);
  RUN_TEST(test_rejected_call_does_not_move_origin);
  RUN_TEST(test_time_wraparound);
  RUN_TEST(test_reset_allows_immediate_play);
  RUN_TEST(test_since_last_play);
  return UNITY_END();
}
