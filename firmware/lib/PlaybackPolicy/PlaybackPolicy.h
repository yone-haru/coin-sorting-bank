// =============================================================================
// PlaybackPolicy — 再生の可否判断（Task 3）
//
// 「今このトラックを再生してよいか」を判断する。連打ガード（RETRIG_MS）を担当する。
// 起動直後の1回目は必ず true（起動音のため）。true を返したときだけ起点を更新する。
//
// Arduino API を使わない純粋クラス。時刻は millis() 相当の 32bit ミリ秒で受け取り、
// 差を 32bit の unsigned で取るので約49日ごとの巻き戻りをまたいでも正しく動く。
// =============================================================================
#pragma once
#include <cstdint>

class PlaybackPolicy {
 public:
  // retrigger_ms：前回 true を返してからこの時間は false（RETRIG_MS）
  explicit PlaybackPolicy(uint32_t retrigger_ms);

  // 再生してよければ true。true を返したときは内部の「最後に再生した時刻」を now_ms に更新する
  bool shouldPlay(uint32_t now_ms);

  // 最後に再生してからの経過（ログ用）。まだ一度も再生していなければ 0xFFFFFFFF
  uint32_t sinceLastPlay(uint32_t now_ms) const;

  // 連打ガードを解除する（次の呼び出しは true）
  void reset();

 private:
  uint32_t retrigger_ms_;
  uint32_t last_play_ms_;
  bool has_played_;
};
