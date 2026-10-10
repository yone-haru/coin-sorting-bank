// =============================================================================
// CoinTracker の実装（v3.0・自作ソータ）
//
// decide()（system_test.py）との対応
//   group_pulses / hole_pairs     → holeEdge / closeGroup / holePair（1 本ずつ届くエッジで組み立てる）
//   穴 B のかたまり → 硬貨         → closeGroup → findPartner → createCoin（かたまりが閉じた時点で、
//                                   相方の穴 A が見つかったときだけ作る。10/10〜。decide() は相方が無くても作る）
//   P の通過を時刻順に処理         → 処理待ち ev_ に te の順で積み、先に決まるはずのものが残っていたら待つ
//   expire(te)                    → expireUpTo（「これより前はもう何も来ない」時刻までしか進めない）
// =============================================================================
#include "CoinTracker.h"

#include <climits>
#include <cmath>

namespace {

constexpr int32_t US_PER_MS = 1000;
constexpr int32_t GAP_US      = static_cast<int32_t>(SS_GROUP_GAP_MS) * US_PER_MS;
constexpr int32_t MIN_PASS_US = static_cast<int32_t>(SS_MIN_PASS_MS) * US_PER_MS;
constexpr int32_t P_MIN_US    = static_cast<int32_t>(SS_P_MIN_MS) * US_PER_MS;
constexpr int32_t V_MIN_DT_US = static_cast<int32_t>(SS_V_MIN_DT_MS) * US_PER_MS;
constexpr int32_t LOOKBACK_US = static_cast<int32_t>(SS_A_LOOKBACK_MS) * US_PER_MS;
constexpr int32_t JAM_US      = static_cast<int32_t>(SS_BEAM_JAM_MS) * US_PER_MS;
constexpr int32_t ADOPT_MIN_US = static_cast<int32_t>(SS_ADOPT_MIN_MS) * US_PER_MS;
constexpr int32_t STALL_CAP_US = static_cast<int32_t>(SS_STALL_CAP_MS) * US_PER_MS;
// 穴 A の記録を捨てる古さ（約 18 分）。調整値ではなく、32bit の時刻が 1 周して
// 古い記録が「さっきの穴 A」に見えるのを防ぐためのもの（半周の半分なら差の符号が正しい）
constexpr int32_t A_STALE_US  = INT32_MAX / 2;

inline int32_t d32(uint32_t a, uint32_t b) { return static_cast<int32_t>(a - b); }

// 段 s の距離（mm）：段 0＝穴 B→P1、段 1＝P1→P2、段 2＝P2→P3
double stageDist(int s) { return SS_BEAM_X_MM[SS_BEAM_HB + s + 1] - SS_BEAM_X_MM[SS_BEAM_HB + s]; }

// 速さ（不明なら既定値。下限つき）
double speedOr(double v) {
  if (v <= 0.0) v = SS_V_DEFAULT_MM_S;
  return v < SS_V_MIN_MM_S ? SS_V_MIN_MM_S : v;
}

// 隣り合う 2 回の遮光（a1,b1）（a2,b2）が穴の両側か（decide() の hole_pairs と同じ条件）
bool holePair(uint32_t a1, uint32_t b1, uint32_t a2, uint32_t b2) {
  const double span = d32(b2, a1);
  const double gap = d32(a2, b1);
  const double w1 = d32(b1, a1);
  const double w2 = d32(b2, a2);
  if (span <= 0.0 || w1 <= 0.0 || w2 <= 0.0) return false;
  const double g = gap / span;
  const double r = w1 / w2;
  return g > SS_HOLE_GAP_RATIO_MIN && g < SS_HOLE_GAP_RATIO_MAX &&
         r > SS_HOLE_PULSE_RATIO_MIN && r < SS_HOLE_PULSE_RATIO_MAX;
}

// 方式 S：ビームを start〜fall に遮った硬貨が「その段に入った時刻」。
// 遮光が長かった（止まっていた）ときだけ、抜けた時刻 − SS_STALL_BACK_MM を進む時間 に遅らせる
uint32_t stallRef(uint32_t start, uint32_t fall, double v) {
  const uint32_t back = static_cast<uint32_t>(SS_STALL_BACK_MM / speedOr(v) * 1e6);
  const uint32_t r = fall - back;
  return d32(r, start) > 0 ? r : start;
}

int trackOf(int value) {
  for (int i = 0; i < LANE_COUNT; i++) {
    if (LANE_VALUE[i] == value) return LANE_TRACK[i];
  }
  return 0;
}

}  // namespace

// -----------------------------------------------------------------------------
// sim 用のエッジ生成
// -----------------------------------------------------------------------------
int ssMakeCoinEdges(int value, double speed_mm_s, uint32_t tA_us, bool withA, SsEdge* out, int maxOut) {
  int k = -1;
  for (int i = 0; i < LANE_COUNT; i++) {
    if (LANE_VALUE[i] == value) k = i;
  }
  if (k < 0 || speed_mm_s <= 0.0 || out == nullptr) return 0;

  const double R = SS_SIM_DIAM_MM[k] / 2.0;
  const double r = SS_SIM_HOLE_MM[k] / 2.0;
  const int holeIdx = r > 0.0 ? 1 : 0;
  int lastStage = -1;   // どの段で落ちるか（3 = P3 を通る）
  for (int s = 0; s < 4; s++) {
    if (SS_STAGE_VALUE[s][holeIdx] == value) {
      lastStage = s;
      break;
    }
  }
  if (lastStage < 0) return 0;

  // まず穴 A 基準のずれ（µs・符号付き）で作り、あとで並べる
  int32_t off[14];
  int beam[14];
  bool lvl[14];
  int n = 0;
  auto add = [&](int b, double a_s, double b_s) {
    off[n] = static_cast<int32_t>(std::lround(a_s * 1e6)); beam[n] = b; lvl[n] = true;  n++;
    off[n] = static_cast<int32_t>(std::lround(b_s * 1e6)); beam[n] = b; lvl[n] = false; n++;
  };
  for (int b = SS_BEAM_HA; b <= SS_BEAM_HB; b++) {
    if (b == SS_BEAM_HA && !withA) continue;
    const double tc = (SS_BEAM_X_MM[b] - SS_BEAM_X_MM[SS_BEAM_HA]) / speed_mm_s;
    if (r > 0.0) {
      add(b, tc - R / speed_mm_s, tc - r / speed_mm_s);
      add(b, tc + r / speed_mm_s, tc + R / speed_mm_s);
    } else {
      add(b, tc - R / speed_mm_s, tc + R / speed_mm_s);
    }
  }
  for (int s = 1; s <= lastStage; s++) {   // P は穴を見ない高さなので 1 回
    const int b = SS_BEAM_HB + s;
    const double tc = (SS_BEAM_X_MM[b] - SS_BEAM_X_MM[SS_BEAM_HA]) / speed_mm_s;
    add(b, tc - R / speed_mm_s, tc + R / speed_mm_s);
  }
  if (n > maxOut) return 0;

  // 時刻順に並べる（挿入ソート。同じ時刻なら作った順）
  int order[14];
  for (int i = 0; i < n; i++) {
    int j = i;
    while (j > 0 && off[order[j - 1]] > off[i]) {
      order[j] = order[j - 1];
      j--;
    }
    order[j] = i;
  }
  for (int i = 0; i < n; i++) {
    const int s = order[i];
    out[i].beam = beam[s];
    out[i].high = lvl[s];
    out[i].t_us = tA_us + static_cast<uint32_t>(off[s]);
  }
  return n;
}

// -----------------------------------------------------------------------------
// CoinTracker
// -----------------------------------------------------------------------------
CoinTracker::CoinTracker(bool adoptOrphan, int maxCoins)
    : adoptOrphan_(adoptOrphan),
      maxCoins_(maxCoins < 1 ? 1 : (maxCoins > SS_MAX_COINS ? SS_MAX_COINS : maxCoins)) {
  reset();
}

void CoinTracker::reset() {
  for (int i = 0; i < 2; i++) {
    hole_[i] = HoleBeam{};
    hole_[i].slot = -1;
  }
  for (int i = 0; i < SS_A_GROUP_BUF; i++) aRing_[i] = AGroup{};
  aNext_ = 0;
  aSeq_ = 0;
  for (int j = 0; j < 3; j++) {
    p_[j] = PBeam{};
    pend_[j] = PendAdopt{};
  }
  evCount_ = 0;
  for (int i = 0; i < SS_MAX_COINS; i++) coins_[i] = Coin{};
  resHead_ = 0;
  resCount_ = 0;
  stats_ = CoinTrackerStats{};
}

void CoinTracker::resetStats() { stats_ = CoinTrackerStats{}; }

int CoinTracker::active() const {
  int n = 0;
  for (int i = 0; i < maxCoins_; i++) {
    if (coins_[i].active) n++;
  }
  return n;
}

void CoinTracker::onEdge(int beam, bool high, uint32_t t_us) {
  if (beam == SS_BEAM_HA || beam == SS_BEAM_HB) {
    holeEdge(beam - SS_BEAM_HA, high, t_us);
  } else if (beam >= SS_BEAM_P1 && beam <= SS_BEAM_P3) {
    pEdge(beam - SS_BEAM_P1, high, t_us);
  }
  // それ以外の番号は無視（呼び出し側の誤り。止めない）
}

bool CoinTracker::poll(CoinResult* out) {
  if (resCount_ == 0 || out == nullptr) return false;
  *out = res_[resHead_];
  resHead_ = (resHead_ + 1) % SS_RESULT_BUF;
  resCount_--;
  return true;
}

// ---- 穴ビーム ----------------------------------------------------------------

void CoinTracker::holeEdge(int idx, bool high, uint32_t t) {
  HoleBeam& h = hole_[idx];
  if (high == h.high) return;   // 同じ向きの変化が続いた（取りこぼし）→ 無視
  if (high) {
    h.high = true;
    h.rise = t;
    if (h.open && d32(t, h.lastFall) < GAP_US) {   // 同じかたまりの続き（穴の割れ目）
      if (idx == 0) noteA(true, t);
      return;
    }
    if (h.open) closeGroup(idx, t);                // tick より先に次の遮光が来た
    openGroup(idx, t);
  } else {
    h.high = false;
    if (!h.open) return;
    if (h.hasPrev && holePair(h.prevRise, h.prevFall, h.rise, t)) setHole(idx);
    h.hasPrev = true;
    h.prevRise = h.rise;
    h.prevFall = t;
    h.lastFall = t;
    if (idx == 0) noteA(false, t);
  }
}

// 今の穴 A のかたまりの記録に「遮られている／光が戻った時刻」を書く（相方の条件に使う）
void CoinTracker::noteA(bool blocked, uint32_t t) {
  const HoleBeam& h = hole_[0];
  if (h.slot < 0) return;
  AGroup& g = aRing_[h.slot];
  if (!g.valid || g.seq != h.seq) return;   // 記録はもう上書きされた
  g.blocked = blocked;
  if (!blocked) g.end = t;
}

void CoinTracker::openGroup(int idx, uint32_t t) {
  HoleBeam& h = hole_[idx];
  h.open = true;
  h.start = t;
  h.lastFall = t;
  h.hasPrev = false;
  h.hole = false;
  h.slot = -1;
  if (idx == 0) {   // 穴 A：相方探し用に記録しておく（古いものから上書き）
    h.slot = aNext_;
    h.seq = ++aSeq_;
    AGroup& g = aRing_[aNext_];
    g.valid = true;
    g.used = false;
    g.hole = false;
    g.blocked = true;
    g.start = t;
    g.end = t;
    g.seq = h.seq;
    aNext_ = (aNext_ + 1) % SS_A_GROUP_BUF;
  }
}

void CoinTracker::setHole(int idx) {
  HoleBeam& h = hole_[idx];
  h.hole = true;
  if (idx != 0 || h.slot < 0) return;
  AGroup& g = aRing_[h.slot];
  if (g.valid && g.seq == h.seq) g.hole = true;
  // もう相方として使われていたら、その硬貨にも伝える
  for (int i = 0; i < maxCoins_; i++) {
    Coin& c = coins_[i];
    if (c.active && c.aSlot == h.slot && c.aSeq == h.seq) c.holeA = true;
  }
}

void CoinTracker::closeGroup(int idx, uint32_t t_now) {
  HoleBeam& h = hole_[idx];
  h.open = false;
  if (idx == 0) return;   // 穴 A は aRing_ に記録済み
  const int32_t span = d32(h.lastFall, h.start);
  if (span < MIN_PASS_US) {
    stats_.flicker++;
    return;
  }
  // 穴 B が詰まるほど長く遮られた（手・詰まった硬貨が抜けた）→ 硬貨にしない（10/10〜）
  if (span >= JAM_US) {
    stats_.longB++;
    return;
  }
  // 相方の穴 A が無ければ硬貨にしない（10/10〜。穴 B だけのノイズ・逆向きの通過で鳴らさない）
  bool holeA = false;
  const int a = findPartner(h.start, h.lastFall, &holeA);
  if (a < 0) {
    stats_.noA++;
    return;
  }
  stats_.coins++;
  createCoin(h.start, h.hole, a, holeA, t_now);
}

// 穴 B のかたまり（入口 t_in・最後に光が戻った bEnd）の相方の穴 A を探す。無ければ -1。
//   時間の範囲：入口の SS_A_LOOKBACK_MS 前から入口まで（穴 A が先に遮られる）に始まった未使用のかたまり
//   相方の条件：時間差が SS_V_MIN_DT_MS より大きい（14mm を 2.8m/s より速くは通らない）
//               長さが SS_MIN_PASS_MS 以上・SS_BEAM_JAM_MS 未満（ちらつき・手でない）
//               もう光が戻っていて、穴 B より先に戻った（硬貨は穴 A から先に抜ける）
//   条件を満たすもののうち一番新しいものを選ぶ。穴の有無はそのどれかに穴があれば「あり」（decide() と同じ考え）
int CoinTracker::findPartner(uint32_t t_in, uint32_t bEnd, bool* anyHole) {
  int best = -1;
  bool inWindow = false;
  bool hole = false;
  for (int i = 0; i < SS_A_GROUP_BUF; i++) {
    const AGroup& g = aRing_[i];
    if (!g.valid || g.used) continue;
    const int32_t d = d32(t_in, g.start);
    if (d < 0 || d >= LOOKBACK_US) continue;
    inWindow = true;
    if (d <= V_MIN_DT_US) continue;
    if (g.blocked) continue;
    const int32_t span = d32(g.end, g.start);
    if (span < MIN_PASS_US || span >= JAM_US) continue;
    if (d32(bEnd, g.end) <= 0) continue;
    hole = hole || g.hole;
    if (best < 0 || d32(g.start, aRing_[best].start) > 0) best = i;
  }
  if (best < 0 && inWindow) stats_.aBad++;
  *anyHole = hole;
  return best;
}

// 穴 A（aRing_[aIdx]）と穴 B の両方を通った硬貨を作って、段 0 から追い始める
void CoinTracker::createCoin(uint32_t t_in, bool holeB, int aIdx, bool holeA, uint32_t t_now) {
  const int ci = allocCoin(t_now);
  Coin& c = coins_[ci];
  AGroup& g = aRing_[aIdx];
  g.used = true;
  c = Coin{};
  c.active = true;
  c.t_in = t_in;
  c.t_stage = t_in;
  c.stage = 0;
  c.holeA = holeA;
  c.holeB = holeB;
  c.aSlot = aIdx;
  c.aSeq = g.seq;
  const int32_t dt = d32(t_in, g.start);   // findPartner で SS_V_MIN_DT_MS より大きいと確かめてある
  c.v = (SS_BEAM_X_MM[SS_BEAM_HB] - SS_BEAM_X_MM[SS_BEAM_HA]) / (dt * 1e-6);
  // 方式 S：穴 B の上で止まっていたら、段 0 の期限は穴 B から抜けた時刻から数える
  c.t_stage = stallRef(t_in, hole_[1].lastFall, c.v);
}

int CoinTracker::allocCoin(uint32_t t_now) {
  for (int i = 0; i < maxCoins_; i++) {
    if (!coins_[i].active) return i;
  }
  // 枠が無い：一番古い硬貨を今の段で決めてしまう（音を鳴らさないよりはよい）
  int old = 0;
  for (int i = 1; i < maxCoins_; i++) {
    if (d32(coins_[i].t_in, coins_[old].t_in) < 0) old = i;
  }
  stats_.overflow++;
  resolve(old, t_now, false, true);
  return old;
}

uint32_t CoinTracker::deadline(const Coin& c) const {
  const int s = c.stage;
  double T = SS_K_DEADLINE * stageDist(s) / speedOr(c.v) + SS_T_MARGIN_MS / 1000.0;
  const double lo = SS_T_CLAMP_MS[s][0] / 1000.0;
  const double hi = SS_T_CLAMP_MS[s][1] / 1000.0;
  if (T < lo) T = lo;
  if (T > hi) T = hi;
  return c.t_stage + static_cast<uint32_t>(T * 1e6 + 0.5);
}

void CoinTracker::resolve(int ci, uint32_t t_decided, bool byTimeout, bool forced) {
  Coin& c = coins_[ci];
  const bool hole = c.holeA || c.holeB;
  CoinResult r{};
  r.value = SS_STAGE_VALUE[c.stage][hole ? 1 : 0];
  r.track = trackOf(r.value);
  r.stage = c.stage;
  r.hole = hole;
  r.byTimeout = byTimeout;
  r.adopted = c.adopted;
  r.forced = forced;
  r.t_in_us = c.t_in;
  r.t_decided_us = t_decided;
  r.speed_mm_s = c.v > 0.0 ? static_cast<uint32_t>(std::lround(c.v)) : 0;
  c.active = false;
  pushResult(r);
}

void CoinTracker::pushResult(const CoinResult& r) {
  if (resCount_ >= SS_RESULT_BUF) {
    stats_.dropped++;
    return;
  }
  res_[(resHead_ + resCount_) % SS_RESULT_BUF] = r;
  resCount_++;
}

// ---- 通過ビーム --------------------------------------------------------------

void CoinTracker::pEdge(int j, bool high, uint32_t t) {
  PBeam& p = p_[j];
  if (high == p.high) return;
  if (high) {
    p.high = true;
    p.rise = t;
    p.emitted = false;
  } else {
    p.high = false;
    const int32_t w = d32(t, p.rise);
    // 方式 S：この P を遮って次の段へ進んだ硬貨が上で止まっていたら、抜けた時刻から数え直す
    for (int i = 0; i < maxCoins_; i++) {
      Coin& c = coins_[i];
      if (c.active && c.stage == j + 1 && c.t_stage == p.rise) c.t_stage = stallRef(p.rise, t, c.v);
    }
    if (!p.emitted) {
      if (w >= P_MIN_US) {
        pushEvent(p.rise, j + 1, w);
      } else {
        stats_.pShort++;
      }
      p.emitted = true;
    } else {
      // 遮られている間に積んだ通過：まだ処理待ちなら長さを書き込む
      for (int i = 0; i < evCount_; i++) {
        if (ev_[i].pi == j + 1 && ev_[i].te == p.rise) ev_[i].w = w;
      }
      // もう処理して「拾うか」が長さ待ちだったなら、ここで決める
      if (pend_[j].valid && pend_[j].te == p.rise) {
        pend_[j].valid = false;
        adoptIfLong(p.rise, j + 1, w);
      }
    }
  }
}

void CoinTracker::pushEvent(uint32_t te, int pi, int32_t w) {
  if (evCount_ >= SS_EVENT_BUF) {
    // 処理待ちがあふれた：一番古いものを待たずに処理して空ける
    stats_.evOverflow++;
    const Event e = ev_[0];
    popEvent();
    expireUpTo(e.te);
    processEvent(e);
  }
  int i = evCount_;
  while (i > 0) {
    const Event& q = ev_[i - 1];
    const int32_t d = d32(q.te, te);
    if (d > 0 || (d == 0 && q.pi > pi)) {
      ev_[i] = ev_[i - 1];
      i--;
    } else {
      break;
    }
  }
  ev_[i].te = te;
  ev_[i].pi = pi;
  ev_[i].w = w;
  evCount_++;
}

void CoinTracker::popEvent() {
  for (int i = 1; i < evCount_; i++) ev_[i - 1] = ev_[i];
  if (evCount_ > 0) evCount_--;
}

// この P の通過を今処理してよいか。まだ決まっていない「より前のもの」があれば待つ
bool CoinTracker::eventBlocked(const Event& e, uint32_t now) const {
  // より早く遮られ始めた P で、まだ長さ（SS_P_MIN_MS 以上か）が決まっていないもの
  for (int j = 0; j < 3; j++) {
    const PBeam& p = p_[j];
    if (!p.high || p.emitted) continue;
    const int32_t d = d32(p.rise, e.te);
    if (d < 0 || (d == 0 && j + 1 < e.pi)) return true;
  }
  // P1：この時刻より前に入った硬貨が、まだ穴 B のかたまりの途中（数えていない）。
  // 速い硬貨はかたまりが閉じる前に P1 を遮る。ただし詰まり（SS_BEAM_JAM_MS）なら待たない
  if (e.pi == 1) {
    const HoleBeam& b = hole_[1];
    if (b.open && d32(e.te, b.start) > 0 && d32(now, b.start) < JAM_US) return true;
  }
  return false;
}

void CoinTracker::processEvent(const Event& e) {
  const uint32_t te = e.te;
  const int pi = e.pi;
  const int s = pi - 1;
  const double dx = stageDist(s);

  // 候補：段 s で待っていて、te より前に入った硬貨。来るはずの時刻に一番近いもの（同じくらいなら古い方）
  int best = -1;
  double bestKey = 0.0;
  for (int i = 0; i < maxCoins_; i++) {
    const Coin& c = coins_[i];
    if (!c.active || c.stage != s || d32(c.t_in, te) >= 0) continue;
    const double expect = dx / speedOr(c.v);
    const double err = std::fabs(d32(te, c.t_stage) * 1e-6 - expect) / expect;
    const double key = std::floor(err * 10.0 + 0.5);   // 0.1 刻みに丸める
    if (best < 0 || key < bestKey || (key == bestKey && d32(c.t_in, coins_[best].t_in) < 0)) {
      best = i;
      bestKey = key;
    }
  }

  if (best < 0) {
    stats_.orphan++;
    if (!adoptOrphan_) return;
    if (e.w >= 0) {
      adoptIfLong(te, pi, e.w);
    } else {
      // まだ遮られていて長さが分からない：SS_ADOPT_MIN_MS に達したら tick で、
      // その前に光が戻ったら pEdge で決める
      pend_[s].valid = true;
      pend_[s].te = te;
    }
    return;
  }

  // 追い越しは無いので、選んだ硬貨より前に入って同じ段で待っている硬貨は、この段の窓で落ちている
  for (;;) {
    int older = -1;
    for (int i = 0; i < maxCoins_; i++) {
      const Coin& c = coins_[i];
      if (i == best || !c.active || c.stage != s || d32(c.t_in, coins_[best].t_in) >= 0) continue;
      if (older < 0 || d32(c.t_in, coins_[older].t_in) < 0) older = i;
    }
    if (older < 0) break;
    resolve(older, te, false, false);
  }

  Coin& c = coins_[best];
  const int32_t dt = d32(te, c.t_stage);
  if (dt > V_MIN_DT_US) c.v = dx / (dt * 1e-6);
  c.stage = pi;
  // 方式 S：処理を待っている間にもう光が戻っていた P は、ここで止まっていたかを見る（pEdge では間に合わない）
  c.t_stage = e.w >= 0 ? stallRef(te, te + static_cast<uint32_t>(e.w), c.v) : te;
  if (pi == 3) resolve(best, te, false, false);
}

// どの硬貨にも当てはまらない P の通過：SS_ADOPT_MIN_MS 以上遮っていたら拾う
void CoinTracker::adoptIfLong(uint32_t te, int pi, int32_t w) {
  if (w >= ADOPT_MIN_US) {
    adopt(te, pi);
  } else {
    stats_.adoptShort++;
  }
}

// 入口で数えていない硬貨として拾う。遮られ始めた時刻（te）にその段へ入ったことにする
void CoinTracker::adopt(uint32_t te, int pi) {
  stats_.adopted++;
  if (pi == 3) {   // P3 を通った＝500円
    CoinResult r{};
    r.value = SS_STAGE_VALUE[3][0];
    r.track = trackOf(r.value);
    r.stage = 3;
    r.adopted = true;
    r.t_in_us = te;
    r.t_decided_us = te;
    pushResult(r);
    return;
  }
  // その段から追い始める。穴は分からないので「なし」
  const int ci = allocCoin(te);
  Coin& c = coins_[ci];
  c = Coin{};
  c.active = true;
  c.t_in = te;
  c.t_stage = te;
  c.stage = pi;
  c.aSlot = -1;
  c.adopted = true;
}

// 方式 S：硬貨 c が今の段に入るときに遮った P が、まだ遮られている（硬貨がその上で止まっている）。
// 遮られ始めてから SS_STALL_CAP_MS を過ぎたら待たない
bool CoinTracker::stallWaiting(const Coin& c, uint32_t w) const {
  if (c.stage < 1) return false;
  const PBeam& p = p_[c.stage - 1];
  return p.high && p.rise == c.t_stage && d32(w, p.rise) < STALL_CAP_US;
}

// 期限が w より前に切れた硬貨を、切れた時刻で決める（入った順）
void CoinTracker::expireUpTo(uint32_t w) {
  for (;;) {
    int pick = -1;
    for (int i = 0; i < maxCoins_; i++) {
      const Coin& c = coins_[i];
      if (!c.active || c.stage >= 3) continue;
      if (d32(deadline(c), w) >= 0) continue;
      // 方式 S：この硬貨が遮った P がまだ遮られている（上で止まっている）間は、SS_STALL_CAP_MS まで待つ
      if (stallWaiting(c, w)) continue;
      if (pick < 0 || d32(c.t_in, coins_[pick].t_in) < 0) pick = i;
    }
    if (pick < 0) return;
    resolve(pick, deadline(coins_[pick]), true, false);
  }
}

void CoinTracker::tick(uint32_t now) {
  // 1. 光が SS_GROUP_GAP_MS 戻ったままの穴ビーム → かたまりを閉じる（穴 B なら硬貨を 1 枚作る）
  for (int idx = 0; idx < 2; idx++) {
    const HoleBeam& h = hole_[idx];
    if (h.open && !h.high && d32(now, h.lastFall) >= GAP_US) closeGroup(idx, now);
  }
  for (int i = 0; i < SS_A_GROUP_BUF; i++) {
    if (aRing_[i].valid && d32(now, aRing_[i].start) >= A_STALE_US) aRing_[i].valid = false;
  }
  // 2. SS_P_MIN_MS 以上遮られている P → 通過として積む（抜けるのを待たない）
  for (int j = 0; j < 3; j++) {
    PBeam& p = p_[j];
    if (p.high && !p.emitted && d32(now, p.rise) >= P_MIN_US) {
      pushEvent(p.rise, j + 1, -1);
      p.emitted = true;
    }
  }
  // 3. 待たなくてよくなった P の通過を、古い順に処理する
  while (evCount_ > 0 && !eventBlocked(ev_[0], now)) {
    const Event e = ev_[0];
    popEvent();
    expireUpTo(e.te);
    processEvent(e);
  }
  // 3b. 拾うか長さ待ちの P：遮られたまま SS_ADOPT_MIN_MS に達したら、光が戻るのを待たずに拾う
  for (int j = 0; j < 3; j++) {
    if (!pend_[j].valid) continue;
    const PBeam& p = p_[j];
    if (!p.high || p.rise != pend_[j].te) {
      pend_[j].valid = false;   // 光が戻ったのに pEdge で決まらなかった（起きないはず。残さない）
    } else if (d32(now, p.rise) >= ADOPT_MIN_US) {
      pend_[j].valid = false;
      adopt(p.rise, j + 1);
    }
  }
  // 4. 期限切れ。まだ処理していない P の通過（遮られ始めた時刻）より前の分だけ
  uint32_t w = now;
  if (evCount_ > 0 && d32(ev_[0].te, w) < 0) w = ev_[0].te;
  for (int j = 0; j < 3; j++) {
    const PBeam& p = p_[j];
    if (p.high && !p.emitted && d32(p.rise, w) < 0) w = p.rise;
  }
  expireUpTo(w);
}
