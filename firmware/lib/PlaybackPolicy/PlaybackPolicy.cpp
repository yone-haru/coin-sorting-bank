#include "PlaybackPolicy.h"

PlaybackPolicy::PlaybackPolicy(uint32_t retrigger_ms) : retrigger_ms_(retrigger_ms) {
  reset();
}

void PlaybackPolicy::reset() {
  last_play_ms_ = 0;
  has_played_ = false;
}

bool PlaybackPolicy::shouldPlay(uint32_t now_ms) {
  if (has_played_) {
    // 32bit の差なので millis() の巻き戻りをまたいでも正しい経過時間になる
    const uint32_t elapsed = static_cast<uint32_t>(now_ms - last_play_ms_);
    if (elapsed < retrigger_ms_) {
      return false;   // 起点は動かさない（連打しても最初の再生から retrigger_ms で解除）
    }
  }
  last_play_ms_ = now_ms;
  has_played_ = true;
  return true;
}

uint32_t PlaybackPolicy::sinceLastPlay(uint32_t now_ms) const {
  if (!has_played_) return 0xFFFFFFFFu;
  return static_cast<uint32_t>(now_ms - last_play_ms_);
}
