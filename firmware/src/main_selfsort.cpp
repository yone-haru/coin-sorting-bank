// =============================================================================
// main_selfsort.cpp — Arduino 層・自作ソータ版（v3.0。env:esp32c3）
//
// ここは薄く保つ。判定は lib/CoinTracker（ビーム 5 本のエッジ → 金額）、連打ガードは
// lib/PlaybackPolicy に置く。ピン・定数は include/Config.h の SS_*（表の正は
// 3Dプリント/自作判別部/設計メモ.md 第 7 章と 配線と固定.md）。
// とりだし君のレーン方式（v2.1）は main_lane.cpp（env:esp32c3_lane）に残してある。
//
// 流れ：
//   ビーム 5 本（HA/HB/P1/P2/P3）の CHANGE 割込 → ISR がエッジ（ビーム・レベル・時刻）をリングバッファへ
//   → loop() で時刻の順に CoinTracker へ渡す（sim コマンドの擬似エッジもここで時刻の順に混ぜる）
//   → tick() で「次の P が来るはずの期限」を進める → 決まった硬貨を poll()
//   → PlaybackPolicy（SS_RETRIG_MS）→ DFPlayer 再生 → ログ（COIN 行）＋ CSV（v2.1 と同じ形式）
//
// 判定は ISR が記録した時刻だけで行うので、USB の送信待ちで loop が遅れても結果は変わらない
// （音が遅れるだけ）。loop の先頭で時刻を取り、それより後に記録されたエッジは次の回に回す。
//
// ログ：
//   [12345] COIN value=50 stage=0 hole=1 v=250 dt=412ms timeout -> play(3) (interrupt)
//   CSV,12345,2,50,OK                        ← <millis>,<LANE_VALUE の並びの番号>,<金額>,<OK|DISCARD>
//   [12400] NOTE noA+1 aBad+1                ← 判定の途中で起きた「普通でないこと」（stats の増分）
//   10/10〜 穴 A と穴 B の両方で確かめた硬貨だけ鳴らす。noA（穴 A の相方なし）・longB（穴 B の長い遮光）・
//   orphan（硬貨に当てはまらない P）は鳴らさず NOTE に数えるだけ（SS_ADOPT_ORPHAN=false のとき）
//
// シリアルコマンド（ASCII・行末 LF）：help / stats / reset / sim / play / sensortest / exit
// =============================================================================
#include <Arduino.h>
#include <DFRobotDFPlayerMini.h>
#include <esp_task_wdt.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "Config.h"
#include "CoinTracker.h"
#include "PlaybackPolicy.h"

static_assert(SS_BEAM_COUNT == 5, "割込ハンドラの表はビーム 5 本前提");
static_assert(LANE_EDGE_BUF <= 255, "リングバッファの添字は uint8_t");

// -----------------------------------------------------------------------------
// 割込と共有するエッジのリングバッファ（ISR は記録だけ。Serial.print 禁止）
// 長さは v2.1 と同じ LANE_EDGE_BUF を使う（硬貨 1 枚で最大 14 本）
// -----------------------------------------------------------------------------
struct Edge {
  uint8_t  beam;    // SS_BEAM_HA 〜 SS_BEAM_P3
  uint8_t  level;   // HIGH（遮光）/ LOW（光あり）
  uint32_t us;      // micros()
};
static volatile Edge     g_edges[LANE_EDGE_BUF];
static volatile uint8_t  g_edgeHead = 0;      // ISR が書く
static volatile uint8_t  g_edgeTail = 0;      // loop が読む
static volatile uint16_t g_edgeDropped = 0;   // バッファ満杯で捨てた数

template <int N>
static void IRAM_ATTR onBeamChangeISR() {
  const uint8_t next = static_cast<uint8_t>((g_edgeHead + 1) % LANE_EDGE_BUF);
  if (next == g_edgeTail) {   // 満杯：記録だけ諦める
    g_edgeDropped++;
    return;
  }
  g_edges[g_edgeHead].beam  = N;
  g_edges[g_edgeHead].level = static_cast<uint8_t>(digitalRead(PIN_SS_BEAM[N]));
  g_edges[g_edgeHead].us    = micros();
  g_edgeHead = next;
}

typedef void (*IsrFn)();
static const IsrFn kBeamISR[SS_BEAM_COUNT] = {
  onBeamChangeISR<0>, onBeamChangeISR<1>, onBeamChangeISR<2>,
  onBeamChangeISR<3>, onBeamChangeISR<4>,
};

// リングバッファの先頭を見る（取り出さない）。無ければ false
static bool peekEdge(Edge* out) {
  noInterrupts();
  if (g_edgeTail == g_edgeHead) {
    interrupts();
    return false;
  }
  out->beam  = g_edges[g_edgeTail].beam;
  out->level = g_edges[g_edgeTail].level;
  out->us    = g_edges[g_edgeTail].us;
  interrupts();
  return true;
}

// peekEdge で見た先頭を捨てる
static void dropEdge() {
  noInterrupts();
  if (g_edgeTail != g_edgeHead) {
    g_edgeTail = static_cast<uint8_t>((g_edgeTail + 1) % LANE_EDGE_BUF);
  }
  interrupts();
}

static void clearEdges() {
  noInterrupts();
  g_edgeHead = g_edgeTail = 0;
  g_edgeDropped = 0;
  interrupts();
}

static uint16_t edgeDropped() {
  noInterrupts();
  const uint16_t n = g_edgeDropped;
  interrupts();
  return n;
}

// -----------------------------------------------------------------------------
// 状態
// -----------------------------------------------------------------------------
enum class SysState { Run, Error };
static SysState g_state = SysState::Run;

static DFRobotDFPlayerMini g_df;
static CoinTracker    g_tracker;
static PlaybackPolicy g_policy(SS_RETRIG_MS);

// ビームごとの「いま遮られているか」（詰まりの検出用。判定は CoinTracker が別に持つ）
struct BeamState {
  bool     high;
  uint32_t riseMs;        // 遮られ始めた時刻（loop で受け取った時刻。詰まり判定には十分）
  bool     jamReported;
};
static BeamState g_beam[SS_BEAM_COUNT] = {};

// sim コマンドの擬似エッジ（時刻の順）。1 枚ずつ（前の硬貨が転がり終わるまで次を受け付けない）
static SsEdge g_sim[SS_SIM_EDGE_BUF];
static int    g_simCount = 0;
static int    g_simNext  = 0;

static bool     g_playing    = false;   // DFPlayer が再生中（PlayFinished 通知で解除）
static bool     g_sensorWarn = false;   // 遮られたままのビームがある（起動時・詰まり）
static uint32_t g_ledOffAt   = 0;       // 再生時の点灯を消す時刻（0 = 点灯要求なし）
static bool     g_sensorTest = false;   // sensortest モード中

// 判別率レポート用のカウンタ（stats / reset コマンド）。並びは LANE_VALUE と同じ
static uint32_t g_countOk[LANE_COUNT] = {};
static uint32_t g_countDiscard = 0;
static uint32_t g_countNoTrack = 0;

// NOTE 行を出すための前回の値
static CoinTrackerStats g_prevStats = {};
static uint16_t         g_prevEdgeDropped = 0;

// -----------------------------------------------------------------------------
// ログ
//
// USB-CDC は 1 回の write ごとに送信待ちが入るので、1 行を 1 回の write にまとめる。
// -----------------------------------------------------------------------------
static void logLine(uint32_t t_ms, const char* fmt, ...) {
  char buf[192];
  const int n = snprintf(buf, sizeof(buf), "[%5lu] ", static_cast<unsigned long>(t_ms));
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf + n, sizeof(buf) - n, fmt, ap);
  va_end(ap);
  Serial.println(buf);
}

// 集計用 CSV（v2.1 と同じ形式）。lane は LANE_VALUE の並びの番号（0=500円 … 5=1円）
static void logCsv(uint32_t t_ms, int lane, int value, const char* result) {
  char buf[64];
  snprintf(buf, sizeof(buf), "CSV,%lu,%d,%d,%s", static_cast<unsigned long>(t_ms), lane, value, result);
  Serial.println(buf);
}

// snprintf の続きを書く（あふれたら何もしない）
static void appendf(char* buf, size_t size, int* n, const char* fmt, ...) {
  if (*n < 0 || static_cast<size_t>(*n) >= size) return;
  va_list ap;
  va_start(ap, fmt);
  const int k = vsnprintf(buf + *n, size - *n, fmt, ap);
  va_end(ap);
  if (k > 0) *n += k;
}

// -----------------------------------------------------------------------------
// ステータス LED（アクティブ LOW。パターンは v2.1 と同じ）
// -----------------------------------------------------------------------------
static inline void ledWrite(bool on) {
  digitalWrite(PIN_LED, on ? LED_ON_LEVEL : (LED_ON_LEVEL == LOW ? HIGH : LOW));
}

static void ledUpdate(uint32_t now) {
  bool on;
  if (g_state == SysState::Error) {
    on = ((now / LED_ERROR_MS) & 1) == 0;                       // 80ms 周期で点滅し続ける
  } else if (g_ledOffAt != 0 && static_cast<int32_t>(now - g_ledOffAt) < 0) {
    on = true;                                                  // 再生開始の 30ms 点灯
  } else {
    g_ledOffAt = 0;
    on = g_sensorWarn && (now % LED_WARN_PERIOD_MS) < LED_WARN_PERIOD_MS / 2;   // 警告はゆっくり点滅
  }
  ledWrite(on);
}

// -----------------------------------------------------------------------------
// DFPlayer（v2.1 と同じ）
// -----------------------------------------------------------------------------
// 応答があったかどうかで初期化の成否を決める。
// ライブラリの begin() は isACK=false だと常に true を返す実装なので戻り値は使えない。
// readFileCounts() は「-1＝応答なし（モジュール不在・配線ミス）」、「0 以上＝応答あり」。
// クローン品は SD にファイルがあっても 0 を返す個体があるので、0 は警告だけにして動かす。
static bool dfInit() {
  for (int attempt = 1; attempt <= DF_INIT_RETRY; ++attempt) {
    g_df.begin(Serial1, /*isACK=*/false, /*doReset=*/true);
    const int files = g_df.readFileCounts(DFPLAYER_DEVICE_SD);
    if (files > 0) {
      logLine(millis(), "DFPlayer OK (attempt %d, %d files on SD)", attempt, files);
      return true;
    }
    if (files == 0) {
      logLine(millis(), "DFPlayer responded but reports 0 files (clone module or empty SD). Continuing.");
      return true;
    }
    logLine(millis(), "DFPlayer no response (attempt %d/%d)", attempt, DF_INIT_RETRY);
    delay(DF_RETRY_WAIT_MS);   // setup() の中なので delay でよい
  }
  return false;
}

static void playTrack(int track) {
  g_df.playMp3Folder(track);   // /mp3/000N.mp3。再生中なら DFPlayer 側で切り替わる（最新優先）
  g_playing = true;
  g_ledOffAt = millis() + LED_PLAY_MS;
  if (g_ledOffAt == 0) g_ledOffAt = 1;   // 0 は「要求なし」の意味に使っている
}

// DFPlayer からの非同期通知（再生終了・エラー）を読む
static void dfPoll() {
  while (g_df.available()) {
    const uint8_t type  = g_df.readType();
    const int     value = g_df.read();
    switch (type) {
      case DFPlayerPlayFinished:
        g_playing = false;
        break;
      case DFPlayerCardRemoved:
        logLine(millis(), "DFPlayer: SD card removed");
        break;
      case DFPlayerCardInserted:
        logLine(millis(), "DFPlayer: SD card inserted");
        break;
      case DFPlayerError:
        logLine(millis(), "DFPlayer ERROR code=%d", value);
        break;
      default:
        break;
    }
  }
}

// -----------------------------------------------------------------------------
// ビームの状態
// -----------------------------------------------------------------------------
// 起動時の自己診断。HIGH（遮光）のままのビームは、硬貨が止まっているか赤外 LED の不良
static void sensorSelfCheck() {
  delay(SENSOR_SETTLE_MS);   // setup() の中なので delay でよい
  g_sensorWarn = false;
  char buf[128];
  int n = snprintf(buf, sizeof(buf), "[%5lu] SENSOR CHECK:", static_cast<unsigned long>(millis()));
  for (int i = 0; i < SS_BEAM_COUNT; ++i) {
    const bool blocked = digitalRead(PIN_SS_BEAM[i]) == HIGH;
    appendf(buf, sizeof(buf), &n, " %s %s", SS_BEAM_NAME[i], blocked ? "BLOCKED" : "ok");
    if (blocked) g_sensorWarn = true;
  }
  Serial.println(buf);
  if (g_sensorWarn) {
    logLine(millis(), "SENSOR WARNING: blocked beam(s). Check for a stuck coin or a dead IR LED. Running anyway.");
  }
}

// 今のピンの状態を詰まり検出の起点にする（割込を付けた直後・sensortest から戻ったとき）。
// 遮られたままのビームは「もう詰まりとして報告済み」にして、すぐ警告の点滅にする。
// CoinTracker には渡さない（光が戻ったときの立ち下がりだけ届き、CoinTracker はそれを無視する）
static void syncBeamStates(uint32_t nowMs) {
  for (int i = 0; i < SS_BEAM_COUNT; ++i) {
    BeamState& b = g_beam[i];
    b.high = digitalRead(PIN_SS_BEAM[i]) == HIGH;
    b.riseMs = nowMs - SS_BEAM_JAM_MS;
    b.jamReported = b.high;
  }
}

// エッジを 1 本、詰まり検出と CoinTracker に渡す。
// nowMs は loop の先頭で取った時刻（checkJam と同じ時刻）。ここで millis() を読み直すと、
// 同じ loop の中でログの送信待ちなどで 1ms 以上進んだとき riseMs が checkJam の nowMs より
// 後になり、符号なしの引き算が巻き戻って「4294967295ms 遮られた」と誤って詰まりを出していた（10/10 修正）
static void applyEdge(int beam, bool high, uint32_t us, uint32_t nowMs) {
  BeamState& b = g_beam[beam];
  if (high != b.high) {
    if (high) {
      b.riseMs = nowMs;
      b.jamReported = false;
    } else if (b.jamReported) {
      const int32_t el = static_cast<int32_t>(nowMs - b.riseMs);
      logLine(nowMs, "BEAM %s -> clear (was blocked %lums)", SS_BEAM_NAME[beam],
              static_cast<unsigned long>(el < 0 ? 0 : el));
      b.jamReported = false;
    }
    b.high = high;
  }
  g_tracker.onEdge(beam, high, us);
}

// 時刻 nowUs までに起きたエッジを、実物と sim を混ぜて時刻の順に CoinTracker へ渡す。
// nowUs は loop の先頭で取った時刻なので、それより前に起きたエッジはもうリングバッファに入っている
static void feedEdges(uint32_t nowUs, uint32_t nowMs) {
  for (;;) {
    Edge hw = {};
    const bool hasHw  = peekEdge(&hw) && static_cast<int32_t>(hw.us - nowUs) <= 0;
    const bool hasSim = g_simNext < g_simCount &&
                        static_cast<int32_t>(g_sim[g_simNext].t_us - nowUs) <= 0;
    if (!hasHw && !hasSim) break;
    if (hasHw && (!hasSim || static_cast<int32_t>(hw.us - g_sim[g_simNext].t_us) <= 0)) {
      dropEdge();
      if (hw.beam < SS_BEAM_COUNT) applyEdge(hw.beam, hw.level == HIGH, hw.us, nowMs);
    } else {
      const SsEdge& s = g_sim[g_simNext++];
      applyEdge(s.beam, s.high, s.t_us, nowMs);
    }
  }
  if (g_simNext >= g_simCount) g_simCount = g_simNext = 0;
}

// ビームが SS_BEAM_JAM_MS 以上遮られ続けていたら詰まり（硬貨がレールで止まった／LED 不良）。
// 警告だけで、判定は止めない（CoinTracker は他のビームで判定を続ける）
static void checkJam(uint32_t nowMs) {
  bool anyJam = false;
  for (int i = 0; i < SS_BEAM_COUNT; ++i) {
    BeamState& b = g_beam[i];
    if (!b.high) continue;
    // 符号付きで比べる（riseMs が万一 nowMs より後でも、巻き戻って詰まりにしない）
    const int32_t el = static_cast<int32_t>(nowMs - b.riseMs);
    if (el < static_cast<int32_t>(SS_BEAM_JAM_MS)) continue;
    anyJam = true;
    if (!b.jamReported) {
      b.jamReported = true;
      logLine(nowMs, "BEAM %s -> JAM? blocked for %lums", SS_BEAM_NAME[i],
              static_cast<unsigned long>(el));
    }
  }
  g_sensorWarn = anyJam;   // 詰まりが解消したら警告も消える
}

// -----------------------------------------------------------------------------
// 決まった硬貨 → 再生
// -----------------------------------------------------------------------------
static int laneOfValue(int value) {
  for (int i = 0; i < LANE_COUNT; ++i) {
    if (LANE_VALUE[i] == value) return i;
  }
  return -1;
}

static void handleResult(const CoinResult& r) {
  const uint32_t nowMs = millis();
  const int lane = laneOfValue(r.value);

  // 判定の中身：段・穴・速さ・入口から決まるまでの時間・どう決まったか
  char info[96];
  int n = 0;
  info[0] = '\0';
  appendf(info, sizeof(info), &n, "value=%d stage=%d hole=%d v=%lu dt=%lums", r.value, r.stage,
          r.hole ? 1 : 0, static_cast<unsigned long>(r.speed_mm_s),
          static_cast<unsigned long>((r.t_decided_us - r.t_in_us) / 1000u));
  if (r.byTimeout) appendf(info, sizeof(info), &n, " timeout");
  if (r.adopted)   appendf(info, sizeof(info), &n, " adopted");
  if (r.forced)    appendf(info, sizeof(info), &n, " forced");

  if (lane < 0 || r.track <= 0) {   // 表に無い金額（起きないはず）。鳴らさずに記録だけ
    logLine(nowMs, "COIN %s -> NO TRACK", info);
    g_countNoTrack++;
    return;
  }
  if (!g_policy.shouldPlay(nowMs)) {
    logLine(nowMs, "COIN %s -> DISCARD (retrig %lums)", info,
            static_cast<unsigned long>(g_policy.sinceLastPlay(nowMs)));
    logCsv(nowMs, lane, r.value, "DISCARD");
    g_countDiscard++;
    return;
  }

  const bool interrupted = g_playing;   // 再生中に上書きした（最新優先）
  playTrack(r.track);                   // 先に鳴らしてからログを書く
  logLine(nowMs, "COIN %s -> play(%d)%s", info, r.track, interrupted ? " (interrupt)" : "");
  logCsv(nowMs, lane, r.value, "OK");
  g_countOk[lane]++;
}

// CoinTracker の集計が増えていたら 1 行にまとめて出す（硬貨の数と「拾った」は COIN 行で分かるので出さない）
static void logNotes(uint32_t nowMs) {
  const CoinTrackerStats& s = g_tracker.stats();
  const uint16_t dropped = edgeDropped();
  char buf[224];
  int n = snprintf(buf, sizeof(buf), "[%5lu] NOTE", static_cast<unsigned long>(nowMs));
  const int base = n;
  const CoinTrackerStats& p = g_prevStats;
  if (s.flicker    != p.flicker)    appendf(buf, sizeof(buf), &n, " flicker+%lu",    static_cast<unsigned long>(s.flicker - p.flicker));
  if (s.noA        != p.noA)        appendf(buf, sizeof(buf), &n, " noA+%lu",        static_cast<unsigned long>(s.noA - p.noA));
  if (s.aBad       != p.aBad)       appendf(buf, sizeof(buf), &n, " aBad+%lu",       static_cast<unsigned long>(s.aBad - p.aBad));
  if (s.pShort     != p.pShort)     appendf(buf, sizeof(buf), &n, " pShort+%lu",     static_cast<unsigned long>(s.pShort - p.pShort));
  if (s.orphan     != p.orphan)     appendf(buf, sizeof(buf), &n, " orphan+%lu",     static_cast<unsigned long>(s.orphan - p.orphan));
  if (s.adoptShort != p.adoptShort) appendf(buf, sizeof(buf), &n, " adoptShort+%lu", static_cast<unsigned long>(s.adoptShort - p.adoptShort));
  if (s.overflow   != p.overflow)   appendf(buf, sizeof(buf), &n, " overflow+%lu",   static_cast<unsigned long>(s.overflow - p.overflow));
  if (s.evOverflow != p.evOverflow) appendf(buf, sizeof(buf), &n, " evOverflow+%lu", static_cast<unsigned long>(s.evOverflow - p.evOverflow));
  if (s.dropped    != p.dropped)    appendf(buf, sizeof(buf), &n, " resultDropped+%lu", static_cast<unsigned long>(s.dropped - p.dropped));
  if (s.longB      != p.longB)      appendf(buf, sizeof(buf), &n, " longB+%lu",      static_cast<unsigned long>(s.longB - p.longB));
  if (dropped != g_prevEdgeDropped) appendf(buf, sizeof(buf), &n, " edgeDropped+%u", static_cast<unsigned>(static_cast<uint16_t>(dropped - g_prevEdgeDropped)));
  if (n > base) Serial.println(buf);
  g_prevStats = s;
  g_prevEdgeDropped = dropped;
}

// CoinTracker を作り直す（sensortest から戻ったとき）。集計も消える
static void restartTracker(uint32_t nowMs) {
  clearEdges();
  g_simCount = g_simNext = 0;
  g_tracker.reset();
  g_prevStats = g_tracker.stats();
  g_prevEdgeDropped = 0;
  syncBeamStates(nowMs);
}

// -----------------------------------------------------------------------------
// センサー試験モード sensortest
//
// 通常動作（判定・音）を止め、ビームごとに遮光の長さと、直前に光が戻ってからの間隔を実測する。
// 穴あき硬貨では HA/HB の遮光が 2 回に割れ、間隔（gap）が穴を横切る時間になる。
// SS_P_MIN_MS・SS_ADOPT_MIN_MS・穴の判定（SS_HOLE_*）・プルアップ値・取付位置を決めるために使う。
// -----------------------------------------------------------------------------
struct BeamTest {
  bool     high;
  uint32_t riseUs;
  bool     hasFall;
  uint32_t lastFallUs;
  bool     hasGap;
  uint32_t gapUs;        // 今の遮光の直前に光が戻っていた時間
  uint32_t rises;
  uint32_t highs;
  uint32_t minHighUs, maxHighUs;
  uint64_t sumHighUs;
  uint32_t minGapUs;
};
static BeamTest g_bt[SS_BEAM_COUNT];
static uint32_t g_stLastPrintMs = 0;
static uint8_t  g_stLastLevels  = 0xFF;
static int      g_stPrintTick   = 0;

static void sensorTestResetStats() {
  for (int i = 0; i < SS_BEAM_COUNT; ++i) {
    g_bt[i] = BeamTest{};
    g_bt[i].minHighUs = 0xFFFFFFFFu;
    g_bt[i].minGapUs  = 0xFFFFFFFFu;
  }
  noInterrupts();
  g_edgeDropped = 0;
  interrupts();
}

// マイクロ秒を「ms（小数 1 桁）」で書く
static void appendMs(char* buf, size_t size, int* n, const char* label, uint32_t us) {
  appendf(buf, size, n, "%s%lu.%lums", label, static_cast<unsigned long>(us / 1000u),
          static_cast<unsigned long>((us % 1000u) / 100u));
}

static void sensorTestPrintStats() {
  Serial.println("=== sensortest stats ===");
  char buf[160];
  for (int i = 0; i < SS_BEAM_COUNT; ++i) {
    const BeamTest& t = g_bt[i];
    int n = snprintf(buf, sizeof(buf), "%s: rises=%lu", SS_BEAM_NAME[i], static_cast<unsigned long>(t.rises));
    if (t.highs > 0) {
      appendMs(buf, sizeof(buf), &n, " high min=", t.minHighUs);
      appendMs(buf, sizeof(buf), &n, " avg=", static_cast<uint32_t>(t.sumHighUs / t.highs));
      appendMs(buf, sizeof(buf), &n, " max=", t.maxHighUs);
    }
    if (t.minGapUs != 0xFFFFFFFFu) appendMs(buf, sizeof(buf), &n, " mingap=", t.minGapUs);
    Serial.println(buf);
  }
  snprintf(buf, sizeof(buf), "dropped edges: %u  (SS_P_MIN_MS=%lu SS_ADOPT_MIN_MS=%lu SS_GROUP_GAP_MS=%lu)",
           static_cast<unsigned>(edgeDropped()), static_cast<unsigned long>(SS_P_MIN_MS),
           static_cast<unsigned long>(SS_ADOPT_MIN_MS), static_cast<unsigned long>(SS_GROUP_GAP_MS));
  Serial.println(buf);
}

static void sensorTestEnter() {
  clearEdges();
  g_simCount = g_simNext = 0;
  sensorTestResetStats();
  g_stLastLevels = 0xFF;
  g_stPrintTick  = 0;
  g_sensorTest = true;
  Serial.println("sensortest: ON (no sound). commands: stats | reset | exit");
  Serial.println("each pulse: <beam> high=<blocked time> gap=<light time before it>");
  Serial.println("levels: 0=light (ok) 1=blocked. printed when changed, at least once a second");
}

static void sensorTestExit() {
  g_sensorTest = false;
  restartTracker(millis());
  Serial.println("sensortest: OFF (normal operation. tracker stats were cleared)");
}

static void sensorTestLoop(uint32_t nowMs) {
  char buf[96];
  Edge e;
  while (peekEdge(&e)) {
    dropEdge();
    if (e.beam >= SS_BEAM_COUNT) continue;
    BeamTest& t = g_bt[e.beam];
    if (e.level == HIGH) {
      if (t.high) continue;   // 立ち下がりを取りこぼした：前の遮光は数えない
      t.rises++;
      t.hasGap = t.hasFall;
      if (t.hasGap) {
        t.gapUs = e.us - t.lastFallUs;
        if (t.gapUs < t.minGapUs) t.minGapUs = t.gapUs;
      }
      t.high   = true;
      t.riseUs = e.us;
    } else if (t.high) {
      const uint32_t highUs = e.us - t.riseUs;
      t.high = false;
      t.highs++;
      t.sumHighUs += highUs;
      if (highUs < t.minHighUs) t.minHighUs = highUs;
      if (highUs > t.maxHighUs) t.maxHighUs = highUs;
      t.hasFall = true;
      t.lastFallUs = e.us;
      int n = snprintf(buf, sizeof(buf), "%s", SS_BEAM_NAME[e.beam]);
      appendMs(buf, sizeof(buf), &n, " high=", highUs);
      if (t.hasGap) appendMs(buf, sizeof(buf), &n, " gap=", t.gapUs);
      Serial.println(buf);
    }
  }

  // 現在値。変化したとき、または SENSORTEST_FORCE_PRINT_EVERY 回に 1 回
  if (static_cast<uint32_t>(nowMs - g_stLastPrintMs) >= SENSORTEST_PRINT_MS) {
    g_stLastPrintMs = nowMs;
    uint8_t levels = 0;
    for (int i = 0; i < SS_BEAM_COUNT; ++i) {
      if (digitalRead(PIN_SS_BEAM[i]) == HIGH) levels |= static_cast<uint8_t>(1u << i);
    }
    g_stPrintTick++;
    if (levels != g_stLastLevels || g_stPrintTick >= SENSORTEST_FORCE_PRINT_EVERY) {
      g_stLastLevels = levels;
      g_stPrintTick  = 0;
      int n = snprintf(buf, sizeof(buf), "[%5lu]", static_cast<unsigned long>(nowMs));
      for (int i = 0; i < SS_BEAM_COUNT; ++i) {
        appendf(buf, sizeof(buf), &n, " %s=%d", SS_BEAM_NAME[i], (levels >> i) & 1);
      }
      Serial.println(buf);
    }
  }
}

// -----------------------------------------------------------------------------
// シリアルコマンド（ASCII・行末 LF。1 文字ずつ届くので \n まで溜める）
// -----------------------------------------------------------------------------
static char g_line[SERIAL_LINE_MAX + 1];
static int  g_lineLen = 0;

// stats：金額ごとの再生回数と、判定の途中で起きたことの回数。
// 正解率は「金額ごとに 50 枚まとめて入れ、その区間のカウントを見る」運用で出す
static void printStats() {
  Serial.println("=== stats (selfsort) ===");
  char buf[160];
  for (int i = 0; i < LANE_COUNT; ++i) {
    snprintf(buf, sizeof(buf), "%3dyen : %lu", LANE_VALUE[i], static_cast<unsigned long>(g_countOk[i]));
    Serial.println(buf);
  }
  snprintf(buf, sizeof(buf), "DISCARD: %lu  NO TRACK: %lu", static_cast<unsigned long>(g_countDiscard),
           static_cast<unsigned long>(g_countNoTrack));
  Serial.println(buf);
  const CoinTrackerStats& s = g_tracker.stats();
  // noA（うち aBad）・longB は硬貨にしなかった数（鳴らしていない）
  snprintf(buf, sizeof(buf), "coins=%lu flicker=%lu noA=%lu (aBad=%lu) pShort=%lu",
           static_cast<unsigned long>(s.coins), static_cast<unsigned long>(s.flicker),
           static_cast<unsigned long>(s.noA), static_cast<unsigned long>(s.aBad),
           static_cast<unsigned long>(s.pShort));
  Serial.println(buf);
  snprintf(buf, sizeof(buf), "orphan=%lu adopted=%lu adoptShort=%lu",
           static_cast<unsigned long>(s.orphan), static_cast<unsigned long>(s.adopted),
           static_cast<unsigned long>(s.adoptShort));
  Serial.println(buf);
  snprintf(buf, sizeof(buf), "overflow=%lu evOverflow=%lu resultDropped=%lu longB=%lu",
           static_cast<unsigned long>(s.overflow), static_cast<unsigned long>(s.evOverflow),
           static_cast<unsigned long>(s.dropped), static_cast<unsigned long>(s.longB));
  Serial.println(buf);
  snprintf(buf, sizeof(buf), "edgeDropped=%u tracking=%d", static_cast<unsigned>(edgeDropped()),
           g_tracker.active());
  Serial.println(buf);
}

static void resetStats() {
  for (int i = 0; i < LANE_COUNT; ++i) g_countOk[i] = 0;
  g_countDiscard = g_countNoTrack = 0;
  g_tracker.resetStats();
  g_prevStats = g_tracker.stats();
  noInterrupts();
  g_edgeDropped = 0;
  interrupts();
  g_prevEdgeDropped = 0;
  Serial.println("stats reset");
}

// sim <金額> [速さ mm/s]：センサー無しで、その硬貨がレールを転がったことにする。
// 擬似エッジを CoinTracker に通すので、判定から音まで全部確かめられる（配線前の動作確認用）
static void cmdSim(const char* arg) {
  char* end = nullptr;
  const long value = strtol(arg, &end, 10);
  bool ok = end != arg && (*end == '\0' || *end == ' ');
  double speed = SS_SIM_SPEED_MM_S;
  if (ok && *end == ' ') {   // 速さを指定した
    char* end2 = nullptr;
    speed = strtod(end, &end2);
    ok = end2 != end && *end2 == '\0';
  }
  if (!ok || laneOfValue(static_cast<int>(value)) < 0 ||
      !(speed >= SS_V_MIN_MM_S && speed <= SS_SIM_SPEED_MAX_MM_S)) {
    char buf[96];
    snprintf(buf, sizeof(buf), "usage: sim <1|5|10|50|100|500> [speed %lu-%lu mm/s, default %lu]",
             static_cast<unsigned long>(SS_V_MIN_MM_S), static_cast<unsigned long>(SS_SIM_SPEED_MAX_MM_S),
             static_cast<unsigned long>(SS_SIM_SPEED_MM_S));
    Serial.println(buf);
    return;
  }
  if (g_simCount > 0) {
    Serial.println("sim: previous coin is still rolling. try again in a second");
    return;
  }
  for (int i = 0; i < SS_BEAM_COUNT; ++i) {
    if (g_beam[i].high) {
      Serial.println("sim: a beam is blocked now. clear the rail first");
      return;
    }
  }
  const uint32_t tA = micros() + SS_SIM_START_DELAY_MS * 1000u;
  const int n = ssMakeCoinEdges(static_cast<int>(value), speed, tA, /*withA=*/true, g_sim, SS_SIM_EDGE_BUF);
  if (n <= 0) {
    Serial.println("sim: could not make edges");
    return;
  }
  g_simCount = n;
  g_simNext  = 0;
  logLine(millis(), "sim value=%ld v=%lu (%d edges)", value, static_cast<unsigned long>(speed), n);
}

// play <track>：トラックを直接鳴らす（スピーカー・アンプの確認用）
static void cmdPlay(const char* arg) {
  const int track = atoi(arg);
  if (track < 1 || track > TRACK_BOOT) {
    Serial.println("usage: play <1-7>   (1=500yen ... 6=1yen 7=boot chime)");
    return;
  }
  playTrack(track);
  logLine(millis(), "manual -> play(%d)", track);
}

static void handleCommand(char* cmd) {
  // 先頭の語と引数に割る
  char* arg = strchr(cmd, ' ');
  if (arg) {
    *arg = '\0';
    ++arg;
  }

  if (strcmp(cmd, "help") == 0) {
    Serial.println("commands: help | stats | reset | sim <yen> [mm/s] | play <1-7> | sensortest | exit");
  } else if (strcmp(cmd, "stats") == 0) {
    if (g_sensorTest) sensorTestPrintStats(); else printStats();
  } else if (strcmp(cmd, "reset") == 0) {
    if (g_sensorTest) { sensorTestResetStats(); Serial.println("sensortest stats reset"); }
    else resetStats();
  } else if (strcmp(cmd, "sim") == 0) {
    if (g_state == SysState::Error) Serial.println("sim: not available in ERROR state");
    else if (g_sensorTest) Serial.println("sim: exit sensortest first");
    else cmdSim(arg ? arg : "");
  } else if (strcmp(cmd, "play") == 0) {
    if (g_state == SysState::Error) Serial.println("play: not available in ERROR state");
    else cmdPlay(arg ? arg : "");
  } else if (strcmp(cmd, "sensortest") == 0) {
    if (g_state == SysState::Error) Serial.println("sensortest: not available in ERROR state");
    else if (g_sensorTest) Serial.println("sensortest: already ON");
    else sensorTestEnter();
  } else if (strcmp(cmd, "exit") == 0) {
    if (g_sensorTest) sensorTestExit(); else Serial.println("exit: not in sensortest");
  } else {
    char buf[64];
    snprintf(buf, sizeof(buf), "unknown command: %s (try 'help')", cmd);
    Serial.println(buf);
  }
}

static void pollSerial() {
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\n' || c == '\r') {
      if (g_lineLen > 0) {
        g_line[g_lineLen] = '\0';
        handleCommand(g_line);
        g_lineLen = 0;
      }
    } else if (g_lineLen < SERIAL_LINE_MAX) {
      g_line[g_lineLen++] = c;
    }
    // 長すぎる行は末尾を捨てる
  }
}

// -----------------------------------------------------------------------------
// setup / loop
// -----------------------------------------------------------------------------
void setup() {
  Serial.begin(SERIAL_BAUD);   // USB-CDC。PC が繋がっていなくても止まらない
  Serial.setTxTimeoutMs(SERIAL_TX_TIMEOUT_MS);   // 既定 100ms。挿しっぱなしでターミナルを閉じたときの停止を短くする

  pinMode(PIN_LED, OUTPUT);
  ledWrite(false);
  for (int i = 0; i < SS_BEAM_COUNT; ++i) {
    pinMode(PIN_SS_BEAM[i], INPUT);   // 外部 22kΩ プルアップ＋1kΩ 直列。内蔵プルアップは使わない
  }
  pinMode(PIN_SS_SPARE, INPUT);       // 予備（基板で GND に落としてある）。出力にしない

  Serial.println("# coin-bank log v1 / boot");   // 集計スクリプトが起動を見つけるためのヘッダ
  logLine(millis(), "coin-bank v3.0 boot (selfsort)");

  Serial1.begin(DF_BAUD, SERIAL_8N1, PIN_DF_RX, PIN_DF_TX);
  if (!dfInit()) {
    g_state = SysState::Error;
    logLine(millis(), "ERROR: DFPlayer not responding. Check wiring (TX=GPIO6/RX=GPIO7, 5V, GND). Halted.");
    return;   // 以後 loop() は LED 点滅とコマンドだけ
  }
  g_df.volume(DF_VOLUME);   // 1 回だけ。以後触らない（音量は VR1 で調整）

  sensorSelfCheck();

  g_policy.shouldPlay(millis());   // 起動直後の 1 回目は必ず true（起動音）
  playTrack(TRACK_BOOT);
  logLine(millis(), "boot sound -> play(%d)", TRACK_BOOT);

  // 割込は起動音の後に有効化する（起動直後の GPIO21＝穴 B のブートログで誤検出しないため）
  for (int i = 0; i < SS_BEAM_COUNT; ++i) {
    attachInterrupt(digitalPinToInterrupt(PIN_SS_BEAM[i]), kBeamISR[i], CHANGE);
  }
  restartTracker(millis());
  logLine(millis(), "IDLE");

  // Task WDT。Arduino core 2.x では loopTask が既定で未登録なので自分で登録する。
  // DFPlayer の初期化（リトライで 10 秒を超える）が終わってから有効にする
  esp_task_wdt_init(WDT_TIMEOUT_S, true);
  esp_task_wdt_add(NULL);
}

void loop() {
  esp_task_wdt_reset();   // ERROR 状態では未登録なので何もしない（戻り値は無視でよい）
  const uint32_t nowUs = micros();   // 先に取る。これより前に起きたエッジはもうリングバッファに入っている
  const uint32_t nowMs = millis();
  ledUpdate(nowMs);
  pollSerial();
  if (g_state == SysState::Error) return;   // ERROR：LED 点滅とコマンド以外は何もしない
  dfPoll();
  if (g_sensorTest) {
    sensorTestLoop(nowMs);   // 試験モード中は判定・再生をしない
    return;
  }
  feedEdges(nowUs, nowMs);
  g_tracker.tick(nowUs);
  CoinResult r;
  while (g_tracker.poll(&r)) handleResult(r);
  checkJam(nowMs);
  logNotes(nowMs);
  // delay() は使わない（エッジは ISR が時刻つきで記録するが、音が遅れる）
}
