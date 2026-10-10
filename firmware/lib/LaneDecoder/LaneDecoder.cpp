#include "LaneDecoder.h"

LaneDecoder::LaneDecoder(uint32_t holdoff_ms, uint32_t min_high_us)
    : holdoff_ms_(holdoff_ms), min_high_us_(min_high_us) {
  reset();
}

void LaneDecoder::reset() {
  for (int i = 0; i < LANE_COUNT; ++i) {
    last_t_[i] = 0;
    has_last_[i] = false;
  }
  last_reason_ = Reason::None;
  last_elapsed_ms_ = 0;
}

bool LaneDecoder::onLanePulse(const LanePulse& p, CoinEvent* out) {
  if (p.lane < 0 || p.lane >= LANE_COUNT) {
    last_reason_ = Reason::OutOfRange;
    last_elapsed_ms_ = 0;
    return false;
  }

  // 幅が短いものはノイズ。不感時間の起点にもしない（本物の硬貨が直後に来ても取りこぼさない）
  if (p.width_us < min_high_us_) {
    last_reason_ = Reason::Noise;
    last_elapsed_ms_ = 0;
    return false;
  }

  if (has_last_[p.lane]) {
    // 32bit の差なので millis() の巻き戻りをまたいでも正しい経過時間になる
    const uint32_t elapsed = static_cast<uint32_t>(p.t_ms - last_t_[p.lane]);
    last_elapsed_ms_ = elapsed;
    if (elapsed < holdoff_ms_) {
      // 不感時間の起点は「最後に受理した時刻」のまま。無視したパルスで延長しない
      last_reason_ = Reason::Holdoff;
      return false;
    }
  } else {
    last_elapsed_ms_ = 0;
  }

  last_t_[p.lane] = p.t_ms;
  has_last_[p.lane] = true;
  last_reason_ = Reason::Accepted;

  if (out) {
    out->lane = p.lane;
    out->value = LANE_VALUE[p.lane];
    out->track = LANE_TRACK[p.lane];
    out->t_ms = p.t_ms;
  }
  return true;
}
