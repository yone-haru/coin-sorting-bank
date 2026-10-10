// =============================================================================
// LaneDecoder — レーンのパルス → 金種（Task 2・v2.1）
//
// 機械式ソータ（銭別銀行とりだし君）の筒6本それぞれに付けた光センサーが
// 「遮られた」パルス（立ち上がり時刻＋HIGH の幅）を受け取り、
//   ・幅が短すぎるもの＝ノイズ
//   ・同一レーンの不感時間内の再検出＝二重検出（跳ね・傾いた硬貨）
// を除いて金種を確定する。
//
// v2.1：割込を RISING → CHANGE に変え、ISR で幅を測ってから渡す形にした。
//       loop() の遅れ（USB シリアルの送信待ち等）に判定が影響されなくなる。
//
// Arduino API を使わない純粋クラス。時刻は引数で受け取る（PC 上でテストする）。
// 時刻は millis() 相当の 32bit ミリ秒。差は 32bit の unsigned で取るので
// 約49日ごとの巻き戻りをまたいでも正しく動く。
// レーン → 金種・トラックの対応は Config.h の LANE_VALUE / LANE_TRACK が正。
// =============================================================================
#pragma once
#include <cstdint>
#include "Config.h"

// 割込が測った「レーン n が t_ms に遮られ、width_us だけ続いた」
struct LanePulse {
  int lane;           // 0〜LANE_COUNT-1
  uint32_t t_ms;      // 立ち上がり時刻（millis 相当）
  uint32_t width_us;  // HIGH（遮光）が続いた長さ（micros 相当）
};

// 確定した硬貨イベント
struct CoinEvent {
  int lane;
  int value;        // 金種（円）
  int track;        // DFPlayer のトラック番号（/mp3/000N.mp3）
  uint32_t t_ms;    // 受理した時刻
};

class LaneDecoder {
 public:
  // 直前の判定の結果（ログ用）
  enum class Reason {
    None,         // まだ何も処理していない
    Accepted,     // 受理した
    Noise,        // 幅が短すぎる
    Holdoff,      // 同一レーンの不感時間内なので無視した
    OutOfRange    // レーン番号が範囲外
  };

  // holdoff_ms   ：同一レーンで、最後に受理してからこの時間内の再検出を無視する（LANE_HOLDOFF_MS）
  // min_high_us  ：この幅未満のパルスはノイズとして捨てる（LANE_MIN_HIGH_US）
  LaneDecoder(uint32_t holdoff_ms, uint32_t min_high_us);

  // パルスを処理する。受理したら true を返し、out（nullptr 可）に金種を書く。
  // ノイズ・無視・範囲外なら false。理由は lastReason()、
  // 同一レーンの最終受理からの経過は lastElapsedMs()。
  bool onLanePulse(const LanePulse& p, CoinEvent* out);

  // 全レーンの不感時間を解除する
  void reset();

  Reason lastReason() const { return last_reason_; }
  uint32_t lastElapsedMs() const { return last_elapsed_ms_; }

 private:
  uint32_t holdoff_ms_;
  uint32_t min_high_us_;
  uint32_t last_t_[LANE_COUNT];    // レーンごとの最終受理時刻
  bool has_last_[LANE_COUNT];      // 一度でも受理したか（0ms との区別のため）
  Reason last_reason_;
  uint32_t last_elapsed_ms_;
};
