// =============================================================================
// CoinTracker — 自作ソータのビーム 5 本のエッジ → 金額（v3.0）
//
// 判別レールの上を硬貨が転がり、直径の小さい順に窓 W1〜W3 から落ちる。
//   穴 A・穴 B（HA/HB）：硬貨の中心の高さを横切るビーム。穴あき硬貨では遮光が 2 回に割れる
//   通過 P1〜P3        ：窓の後ろのビーム。ここを通った＝その窓では落ちなかった
// 穴 A と穴 B の両方を順に通ったと確かめられたものだけを硬貨として数え（10/10〜）、
// どこまで P を通ったか（段）と穴の有無で金額を決める。
// 穴 B だけ・穴 A だけ・P だけ・穴 B の長い遮光は硬貨にしない（鳴らさない。stats に数えるだけ）。
// 入口での見落としで鳴らないことより、余計な音が鳴らないことを優先した。
//   段 0（W1 で落ちた）：穴なし 1円 ／ 穴あり 50円
//   段 1（W2）         ：穴なし 100円 ／ 穴あり 5円
//   段 2（W3）         ：10円
//   段 3（P3 を通った）：500円
// 次の P が「来るはずの時間」（期限）を過ぎても来なければ、そこで落ちたと決める。
// 期限は穴 A→穴 B の時間差から出した速さで決める（SS_K_DEADLINE ほか）。
// 方式 S（10/10〜）：ビームの上で止まってから動き出した硬貨は、ビームから抜けた時刻から期限を数え直す。
// 硬貨が遮った P がまだ遮られている間は SS_STALL_CAP_MS まで待つ（止まっていない硬貨の判定は変わらない）
//
// 仕様の下書きは 3Dプリント/自作判別部/sim/system_test.py の decide()（hole_rule="or"）。
// decide() は記録全体を見てから判定するが、ここでは 1 本ずつ届くエッジで同じ結果になるよう
// 「まだ来るかもしれないもの」を待ってから決める（穴 B のかたまりが閉じるまで P1 を待つ など）。
// decide() との違い（10/10 時点）
//   ・穴 A の相方が無い穴 B は硬貨にしない（decide() は速さ不明のまま追う）
//   ・穴 B が SS_BEAM_JAM_MS 以上遮られていたら硬貨にしない（decide() は 1 枚として追う）
//   ・相方にする穴 A の条件を足した：時間差が SS_V_MIN_DT_MS より大きい・長さが SS_MIN_PASS_MS 以上
//     SS_BEAM_JAM_MS 未満・もう光が戻っている・穴 B より先に光が戻った（本物の硬貨なら必ず満たす）
//   ・入口で数えなかった硬貨を P で拾う（SS_ADOPT_ORPHAN）。既定は false（拾わない）。
//     拾う設定のときは P を SS_ADOPT_MIN_MS 以上遮ったときだけ（窓へ傾いた硬貨の短い再遮光で鳴らさない）
//
// Arduino API を使わない純粋クラス。時刻は micros() 相当の 32bit マイクロ秒で受け取り、
// 差は符号付き 32bit で取るので約 71 分ごとの巻き戻りをまたいでも正しく動く。
// =============================================================================
#pragma once
#include <cstdint>
#include "Config.h"

// ビームの変化 1 回（sim コマンドとテストで使う）
struct SsEdge {
  int beam;        // SS_BEAM_HA 〜 SS_BEAM_P3
  bool high;       // true = 遮られた
  uint32_t t_us;
};

// 決まった硬貨 1 枚
struct CoinResult {
  int value;              // 金額（円）
  int track;              // DFPlayer のトラック番号（LANE_TRACK の表）。見つからなければ 0
  int stage;              // どこで決まったか：0=W1 1=W2 2=W3 3=P3 を通った
  bool hole;              // 穴あり（穴 A か穴 B のどちらかで見えた）
  bool byTimeout;         // 次の P が来ないまま期限が切れて決まった
  bool adopted;           // 入口で数えていない硬貨を P で拾った
  bool forced;            // 追跡の枠があふれて途中で決めた
  uint32_t t_in_us;       // 穴 B に入った時刻（拾った硬貨は P を遮った時刻）
  uint32_t t_decided_us;  // 決まった時刻（期限切れなら期限の時刻）
  uint32_t speed_mm_s;    // 最後に測った速さ。0 = 不明
};

// 集計（stats コマンドで出す。判別率レポートの手がかり）
struct CoinTrackerStats {
  uint32_t coins;       // 穴 A と穴 B の両方で確かめて数えた硬貨
  uint32_t flicker;     // 穴 B の短すぎる遮光（数えなかった）
  uint32_t noA;         // 穴 B を通ったが相方の穴 A が無かった（硬貨にしない・鳴らさない）
  uint32_t aBad;        // noA のうち、時間の範囲には穴 A があったが相方にできなかったもの
                        // （時間差が短すぎ・穴 A が短すぎ/長すぎ/遮られたまま・穴 B より後に光が戻った）
  uint32_t pShort;      // P の短すぎる遮光（無視した）
  uint32_t orphan;      // どの硬貨にも当てはまらない P の通過
  uint32_t adopted;     // そのうち新しい硬貨として拾ったもの
  uint32_t adoptShort;  // そのうち遮光が SS_ADOPT_MIN_MS より短くて拾わなかったもの
  uint32_t overflow;    // 追跡の枠があふれて途中で決めた
  uint32_t evOverflow;  // P の処理待ちがあふれて、待たずに処理した
  uint32_t dropped;     // 結果の取り出しが間に合わず捨てた
  uint32_t longB;       // 穴 B が SS_BEAM_JAM_MS 以上遮られていた（硬貨にしない・鳴らさない）
};

// 自作ソータを 1 枚が一定の速さで通ったときのエッジを作る（sim コマンドとテスト用）。
//   value   ：金額（LANE_VALUE にある値）。形は SS_SIM_DIAM_MM / SS_SIM_HOLE_MM
//   tA_us   ：硬貨の中心が穴 A の位置に来る時刻
//   withA   ：false なら穴 A のエッジを出さない（穴 A の見落とし）
// 時刻順に並べて out に書き、本数を返す（最大 14 本）。金額が表に無い・入りきらないときは 0
int ssMakeCoinEdges(int value, double speed_mm_s, uint32_t tA_us, bool withA,
                    SsEdge* out, int maxOut);

class CoinTracker {
 public:
  // adoptOrphan：入口で数えていない硬貨を P で拾うか（SS_ADOPT_ORPHAN）
  // maxCoins   ：同時に追う硬貨の上限（1〜SS_MAX_COINS。テストで小さくする）
  explicit CoinTracker(bool adoptOrphan = SS_ADOPT_ORPHAN, int maxCoins = SS_MAX_COINS);

  // 追跡中の硬貨・待ち行列・集計をすべて消す
  void reset();

  // ビームの変化を渡す。時刻の順に渡すこと（ISR のリングバッファから取り出した順）
  void onEdge(int beam, bool high, uint32_t t_us);

  // 今の時刻を渡して、期限切れ・待っていた P の処理を進める。loop で毎回呼ぶ
  void tick(uint32_t now_us);

  // 決まった結果を 1 つ取り出す。無ければ false
  bool poll(CoinResult* out);

  // 追跡中（まだ決まっていない）の硬貨の数
  int active() const;

  const CoinTrackerStats& stats() const { return stats_; }
  void resetStats();

 private:
  // 穴ビーム（HA/HB）の遮光のかたまり
  struct HoleBeam {
    bool high;
    uint32_t rise;          // 今の遮光の始まり
    bool open;              // かたまりの途中
    uint32_t start;         // かたまりの始まり
    uint32_t lastFall;      // かたまりの最後の遮光の終わり
    bool hasPrev;           // かたまりの中に確定した遮光がある
    uint32_t prevRise, prevFall;
    bool hole;              // かたまりの中に穴の割れ目があった
    int slot;               // 穴 A だけ：aRing_ の位置
    uint32_t seq;           // 穴 A だけ：aRing_ の通し番号
  };
  // 穴 A のかたまりの記録（穴 B で数えた硬貨の相方を探す）
  struct AGroup {
    bool valid;
    bool used;
    bool hole;
    bool blocked;           // 今も遮られている
    uint32_t start;
    uint32_t end;           // 最後に光が戻った時刻（まだ戻っていなければ start）
    uint32_t seq;
  };
  // 通過ビーム（P1〜P3）
  struct PBeam {
    bool high;
    bool emitted;           // この遮光はもう処理待ちに積んだ（または短すぎて捨てた）
    uint32_t rise;
  };
  // 処理待ちの P の通過
  struct Event {
    uint32_t te;            // 遮られた時刻
    int pi;                 // 1〜3（P1〜P3）
    int32_t w;              // 遮光の長さ（us）。-1 = まだ遮られている
  };
  // 拾うかどうか、遮光の長さが決まるのを待っている P の通過（P ごとに 1 つ）
  struct PendAdopt {
    bool valid;
    uint32_t te;
  };
  // 追跡中の硬貨
  struct Coin {
    bool active;
    uint32_t t_in;          // 穴 B に入った時刻
    uint32_t t_stage;       // 今の段に入った時刻
    int stage;              // 0〜2（3 になったら決まり）
    bool holeA, holeB;
    double v;               // mm/s。0 = 不明
    int aSlot;              // 相方の穴 A（-1 = 無し）
    uint32_t aSeq;
    bool adopted;
  };

  static int32_t diff(uint32_t a, uint32_t b) { return static_cast<int32_t>(a - b); }

  void holeEdge(int idx, bool high, uint32_t t);
  void openGroup(int idx, uint32_t t);
  void closeGroup(int idx, uint32_t t_now);
  void setHole(int idx);
  void noteA(bool blocked, uint32_t t);
  void pEdge(int j, bool high, uint32_t t);

  int findPartner(uint32_t t_in, uint32_t bEnd, bool* anyHole);
  void createCoin(uint32_t t_in, bool holeB, int aIdx, bool holeA, uint32_t t_now);
  int allocCoin(uint32_t t_now);
  uint32_t deadline(const Coin& c) const;
  void resolve(int ci, uint32_t t_decided, bool byTimeout, bool forced);
  void pushResult(const CoinResult& r);

  void pushEvent(uint32_t te, int pi, int32_t w);
  bool eventBlocked(const Event& e, uint32_t now) const;
  void popEvent();
  void processEvent(const Event& e);
  bool stallWaiting(const Coin& c, uint32_t w) const;
  void expireUpTo(uint32_t w);
  void adoptIfLong(uint32_t te, int pi, int32_t w);
  void adopt(uint32_t te, int pi);

  bool adoptOrphan_;
  int maxCoins_;

  HoleBeam hole_[2];                  // [0]=HA [1]=HB
  AGroup aRing_[SS_A_GROUP_BUF];
  int aNext_;
  uint32_t aSeq_;
  PBeam p_[3];
  PendAdopt pend_[3];
  Event ev_[SS_EVENT_BUF];           // te の順（同じ時刻なら pi の順）に並べておく
  int evCount_;
  Coin coins_[SS_MAX_COINS];
  CoinResult res_[SS_RESULT_BUF];
  int resHead_, resCount_;
  CoinTrackerStats stats_;
};
