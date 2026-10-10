// =============================================================================
// main_lane.cpp — Arduino 層・とりだし君のレーン方式（Task 4・5・6・8／v2.1）
//
// 2026-09-27：自作ソータ版（main_selfsort.cpp・env:esp32c3）を既定にしたので、
// こちらは env:esp32c3_lane でだけビルドする。中身は v2.1 のまま（とりだし君に戻すとき用）。
//
// ここは薄く保つ。判定ロジックは lib/LaneDecoder と lib/PlaybackPolicy に置く。
// ピン・定数は include/Config.h（正は CLAUDE.md）。
//
// 流れ：
//   レーンセンサーの CHANGE 割込 → ISR がエッジ（レーン・レベル・時刻）をリングバッファへ
//   → loop() で立ち上がり〜立ち下がりを組にして「幅つきパルス」にする
//   → LaneDecoder（ノイズ除去・同一レーンの不感時間）→ PlaybackPolicy（連打ガード）
//   → DFPlayer 再生 → ログ（CLAUDE.md §3 の形式）＋ CSV（集計用）
//
// v2.1 の変更（2026-09-06・ユーザー承認済み）：
//   ・割込を RISING → CHANGE にし、幅の判定を loop の digitalRead から ISR の時刻差に変えた。
//     USB を挿したままターミナルを閉じていると HWCDC の送信待ちで loop が最大 100ms/回
//     止まるため、loop 側で 2ms 後に読み直す方式では取りこぼす可能性があった
//   ・ログを 1 回の書き込みにまとめ、Serial.setTxTimeoutMs() で待ち時間を詰めた
//   ・sim / play コマンド（センサー無しで音の経路を確認する）
//   ・ERROR 判定は「DFPlayer が応答しない」ときだけ（SD のファイル数 0 は警告に留める）
//   ・HIGH が続いたままなら詰まり警告（LANE_JAM_MS）
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
#include "LaneDecoder.h"
#include "PlaybackPolicy.h"

static_assert(LANE_COUNT == 6, "割込ハンドラの表は 6 レーン前提");

// -----------------------------------------------------------------------------
// 割込と共有するエッジのリングバッファ（ISR は記録だけ。Serial.print 禁止）
// -----------------------------------------------------------------------------
struct Edge {
  uint8_t  lane;
  uint8_t  level;   // HIGH（遮光）/ LOW（光あり）
  uint32_t us;      // micros()
  uint32_t ms;      // millis()
};
static volatile Edge     g_edges[LANE_EDGE_BUF];
static volatile uint8_t  g_edgeHead = 0;      // ISR が書く
static volatile uint8_t  g_edgeTail = 0;      // loop が読む
static volatile uint16_t g_edgeDropped = 0;   // バッファ満杯で捨てた数

template <int N>
static void IRAM_ATTR onLaneChangeISR() {
  const uint8_t next = static_cast<uint8_t>((g_edgeHead + 1) % LANE_EDGE_BUF);
  if (next == g_edgeTail) {   // 満杯：記録だけ諦める
    g_edgeDropped++;
    return;
  }
  g_edges[g_edgeHead].lane  = N;
  g_edges[g_edgeHead].level = static_cast<uint8_t>(digitalRead(PIN_LANE[N]));
  g_edges[g_edgeHead].us    = micros();
  g_edges[g_edgeHead].ms    = millis();
  g_edgeHead = next;
}

typedef void (*IsrFn)();
static const IsrFn kLaneISR[LANE_COUNT] = {
  onLaneChangeISR<0>, onLaneChangeISR<1>, onLaneChangeISR<2>,
  onLaneChangeISR<3>, onLaneChangeISR<4>, onLaneChangeISR<5>,
};

// リングバッファから 1 件取り出す（無ければ false）
static bool popEdge(Edge* out) {
  noInterrupts();
  if (g_edgeTail == g_edgeHead) {
    interrupts();
    return false;
  }
  out->lane  = g_edges[g_edgeTail].lane;
  out->level = g_edges[g_edgeTail].level;
  out->us    = g_edges[g_edgeTail].us;
  out->ms    = g_edges[g_edgeTail].ms;
  g_edgeTail = static_cast<uint8_t>((g_edgeTail + 1) % LANE_EDGE_BUF);
  interrupts();
  return true;
}

static void clearEdges() {
  noInterrupts();
  g_edgeHead = g_edgeTail = 0;
  g_edgeDropped = 0;
  interrupts();
}

// -----------------------------------------------------------------------------
// 状態
// -----------------------------------------------------------------------------
enum class SysState { Run, Error };
static SysState g_state = SysState::Run;

static DFRobotDFPlayerMini g_df;
static LaneDecoder    g_decoder(LANE_HOLDOFF_MS, LANE_MIN_HIGH_US);
static PlaybackPolicy g_policy(RETRIG_MS);

// レーンごとの「いま HIGH 中」の記録（立ち下がりで幅が確定する）
struct LaneHigh {
  bool     active;
  uint32_t riseUs;
  uint32_t riseMs;
  bool     jamReported;
};
static LaneHigh g_high[LANE_COUNT] = {};

static bool     g_playing    = false;   // DFPlayer が再生中（PlayFinished 通知で解除）
static bool     g_sensorWarn = false;   // 起動時に遮光されたままのレーンがあった／詰まり検出
static uint32_t g_ledOffAt   = 0;       // 再生時の点灯を消す時刻（0 = 点灯要求なし）
static bool     g_sensorTest = false;   // sensortest モード中（Task 8）

// 判別率レポート用のカウンタ（stats / reset コマンド。Task 6）
static uint32_t g_countOk[LANE_COUNT] = {};
static uint32_t g_countIgnore  = 0;
static uint32_t g_countDiscard = 0;
static uint32_t g_countNoise   = 0;

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

// 集計用 CSV（Task 6）。PC 側でこの行だけ抜き出して判別率を出す。result：OK / IGNORE / DISCARD
static void logCsv(uint32_t t_ms, int lane, int value, const char* result) {
  char buf[64];
  snprintf(buf, sizeof(buf), "CSV,%lu,%d,%d,%s", static_cast<unsigned long>(t_ms), lane, value, result);
  Serial.println(buf);
}

// -----------------------------------------------------------------------------
// ステータス LED（アクティブ LOW。パターンは開発計画 Task 5）
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
// DFPlayer
// -----------------------------------------------------------------------------
// 応答があったかどうかで初期化の成否を決める。
// ライブラリの begin() は isACK=false だと常に true を返す実装なので戻り値は使えない。
// readFileCounts() は「-1＝応答なし（モジュール不在・配線ミス）」、
// 「0 以上＝応答あり」。クローン品は SD にファイルがあっても 0 を返す個体があるので、
// 0 のときは警告だけにして動かす（ERROR で止めない）。
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
// センサー自己診断（起動時。HIGH＝遮光のままのレーンは詰まりか LED 不良）
// -----------------------------------------------------------------------------
static void sensorSelfCheck() {
  delay(SENSOR_SETTLE_MS);   // setup() の中なので delay でよい
  g_sensorWarn = false;
  char buf[128];
  int n = snprintf(buf, sizeof(buf), "[%5lu] SENSOR CHECK:", static_cast<unsigned long>(millis()));
  for (int i = 0; i < LANE_COUNT; ++i) {
    const bool blocked = digitalRead(PIN_LANE[i]) == HIGH;
    n += snprintf(buf + n, sizeof(buf) - n, " L%d %s", i, blocked ? "BLOCKED" : "ok");
    if (blocked) g_sensorWarn = true;
  }
  Serial.println(buf);
  if (g_sensorWarn) {
    logLine(millis(), "SENSOR WARNING: blocked lane(s). Check for a stuck coin or a dead IR LED. Running anyway.");
  }
}

// -----------------------------------------------------------------------------
// レーンのパルス → 判定 → 再生
// -----------------------------------------------------------------------------
static void handleCoin(const LanePulse& p) {
  CoinEvent coin;
  if (!g_decoder.onLanePulse(p, &coin)) {
    switch (g_decoder.lastReason()) {
      case LaneDecoder::Reason::Noise:
        logLine(p.t_ms, "LANE %d -> NOISE (%luus < %luus)", p.lane,
                static_cast<unsigned long>(p.width_us), static_cast<unsigned long>(LANE_MIN_HIGH_US));
        g_countNoise++;
        break;
      case LaneDecoder::Reason::Holdoff:
        logLine(p.t_ms, "LANE %d value=%d -> IGNORE (holdoff %lums)", p.lane, LANE_VALUE[p.lane],
                static_cast<unsigned long>(g_decoder.lastElapsedMs()));
        logCsv(p.t_ms, p.lane, LANE_VALUE[p.lane], "IGNORE");
        g_countIgnore++;
        break;
      default:
        logLine(p.t_ms, "LANE %d -> IGNORE (out of range)", p.lane);
        break;
    }
    return;
  }

  const uint32_t now = millis();
  if (!g_policy.shouldPlay(now)) {
    logLine(p.t_ms, "LANE %d value=%d -> DISCARD (retrig %lums)", coin.lane, coin.value,
            static_cast<unsigned long>(g_policy.sinceLastPlay(now)));
    logCsv(p.t_ms, coin.lane, coin.value, "DISCARD");
    g_countDiscard++;
    return;
  }

  const bool interrupted = g_playing;   // 再生中に上書きした（最新優先）
  playTrack(coin.track);
  logLine(p.t_ms, "LANE %d value=%d -> play(%d)%s", coin.lane, coin.value, coin.track,
          interrupted ? " (interrupt)" : "");
  logCsv(p.t_ms, coin.lane, coin.value, "OK");
  g_countOk[coin.lane]++;
}

// エッジを組にして幅つきパルスにする。立ち下がりで確定
static void processEdges() {
  Edge e;
  while (popEdge(&e)) {
    if (e.lane >= LANE_COUNT) continue;
    LaneHigh& h = g_high[e.lane];
    if (e.level == HIGH) {
      // 立ち上がり。前の HIGH が閉じていなければ（取りこぼし）上書きする
      h.active = true;
      h.riseUs = e.us;
      h.riseMs = e.ms;
      h.jamReported = false;
    } else if (h.active) {
      h.active = false;
      LanePulse p;
      p.lane = e.lane;
      p.t_ms = h.riseMs;
      p.width_us = static_cast<uint32_t>(e.us - h.riseUs);
      handleCoin(p);
    }
  }
}

// HIGH が LANE_JAM_MS 以上続いていたら詰まり（硬貨が筒で止まった／センサーが遮られたまま）
static void checkJam(uint32_t nowMs) {
  bool anyJam = false;
  for (int i = 0; i < LANE_COUNT; ++i) {
    LaneHigh& h = g_high[i];
    if (!h.active) continue;
    if (static_cast<uint32_t>(nowMs - h.riseMs) < LANE_JAM_MS) continue;
    anyJam = true;
    if (!h.jamReported) {
      h.jamReported = true;
      logLine(nowMs, "LANE %d value=%d -> JAM? blocked for %lums", i, LANE_VALUE[i],
              static_cast<unsigned long>(nowMs - h.riseMs));
    }
  }
  g_sensorWarn = anyJam;   // 詰まりが解消したら警告も消える
}

// -----------------------------------------------------------------------------
// センサー試験モード sensortest（Task 8）
//
// 通常動作（音）を止め、幅と間隔を実測する。
// LANE_HOLDOFF_MS・プルアップ値・取付位置を決めるために使う（製作手順書 追補 A-3）。
// 割込は通常動作と同じ CHANGE のまま。エッジの解釈だけを切り替える。
// -----------------------------------------------------------------------------
struct LaneTest {
  bool     high;
  uint32_t riseUs;
  bool     hasPrevRise;
  uint32_t prevRiseUs;
  uint32_t lastGapUs;
  uint32_t rises;
  uint32_t highs;
  uint32_t minHighUs, maxHighUs;
  uint64_t sumHighUs;
  uint32_t minGapUs;
};
static LaneTest g_lt[LANE_COUNT];
static uint32_t g_stLastPrintMs = 0;
static uint8_t  g_stLastLevels  = 0xFF;
static int      g_stPrintTick   = 0;

static void sensorTestResetStats() {
  for (int i = 0; i < LANE_COUNT; ++i) {
    g_lt[i] = LaneTest{};
    g_lt[i].minHighUs = 0xFFFFFFFFu;
    g_lt[i].minGapUs  = 0xFFFFFFFFu;
  }
  noInterrupts();
  g_edgeDropped = 0;
  interrupts();
}

static void sensorTestPrintStats() {
  Serial.println("=== sensortest stats ===");
  char buf[160];
  for (int i = 0; i < LANE_COUNT; ++i) {
    const LaneTest& t = g_lt[i];
    int n = snprintf(buf, sizeof(buf), "L%d %3dyen: rises=%lu", i, LANE_VALUE[i],
                     static_cast<unsigned long>(t.rises));
    if (t.highs > 0) {
      n += snprintf(buf + n, sizeof(buf) - n, " high min/avg/max=%lu/%lu/%lums",
                    static_cast<unsigned long>(t.minHighUs / 1000),
                    static_cast<unsigned long>(t.sumHighUs / t.highs / 1000),
                    static_cast<unsigned long>(t.maxHighUs / 1000));
    }
    if (t.minGapUs != 0xFFFFFFFFu) {
      snprintf(buf + n, sizeof(buf) - n, " mingap=%lums", static_cast<unsigned long>(t.minGapUs / 1000));
    }
    Serial.println(buf);
  }
  snprintf(buf, sizeof(buf), "dropped edges: %u  (LANE_HOLDOFF_MS=%lu LANE_MIN_HIGH_US=%lu)",
           static_cast<unsigned>(g_edgeDropped),
           static_cast<unsigned long>(LANE_HOLDOFF_MS), static_cast<unsigned long>(LANE_MIN_HIGH_US));
  Serial.println(buf);
}

static void sensorTestEnter() {
  clearEdges();
  for (int i = 0; i < LANE_COUNT; ++i) g_high[i].active = false;
  sensorTestResetStats();
  g_stLastLevels = 0xFF;
  g_stPrintTick  = 0;
  g_sensorTest = true;
  Serial.println("sensortest: ON (no sound). commands: stats | reset | exit");
  Serial.println("levels: 0=light (ok) 1=blocked. printed when changed, at least once a second");
}

static void sensorTestExit() {
  clearEdges();
  for (int i = 0; i < LANE_COUNT; ++i) g_high[i].active = false;
  g_decoder.reset();
  g_sensorTest = false;
  Serial.println("sensortest: OFF (normal operation)");
}

static void sensorTestLoop(uint32_t nowMs) {
  char buf[96];
  Edge e;
  while (popEdge(&e)) {
    if (e.lane >= LANE_COUNT) continue;
    LaneTest& t = g_lt[e.lane];
    if (e.level == HIGH) {
      t.rises++;
      t.lastGapUs = 0;
      if (t.hasPrevRise) {
        t.lastGapUs = e.us - t.prevRiseUs;
        if (t.lastGapUs < t.minGapUs) t.minGapUs = t.lastGapUs;
      }
      t.hasPrevRise = true;
      t.prevRiseUs  = e.us;
      t.high   = true;
      t.riseUs = e.us;
    } else if (t.high) {
      const uint32_t highUs = e.us - t.riseUs;
      t.high = false;
      t.highs++;
      t.sumHighUs += highUs;
      if (highUs < t.minHighUs) t.minHighUs = highUs;
      if (highUs > t.maxHighUs) t.maxHighUs = highUs;
      int n = snprintf(buf, sizeof(buf), "L%d high=%luus (%lums)", e.lane,
                       static_cast<unsigned long>(highUs), static_cast<unsigned long>(highUs / 1000));
      if (t.lastGapUs != 0) {
        snprintf(buf + n, sizeof(buf) - n, " gap=%lums", static_cast<unsigned long>(t.lastGapUs / 1000));
      }
      Serial.println(buf);
    }
  }

  // 現在値。変化したとき、または SENSORTEST_FORCE_PRINT_EVERY 回に1回
  if (static_cast<uint32_t>(nowMs - g_stLastPrintMs) >= SENSORTEST_PRINT_MS) {
    g_stLastPrintMs = nowMs;
    uint8_t levels = 0;
    for (int i = 0; i < LANE_COUNT; ++i) {
      if (digitalRead(PIN_LANE[i]) == HIGH) levels |= static_cast<uint8_t>(1u << i);
    }
    g_stPrintTick++;
    if (levels != g_stLastLevels || g_stPrintTick >= SENSORTEST_FORCE_PRINT_EVERY) {
      g_stLastLevels = levels;
      g_stPrintTick  = 0;
      int n = snprintf(buf, sizeof(buf), "[%5lu]", static_cast<unsigned long>(nowMs));
      for (int i = 0; i < LANE_COUNT; ++i) {
        n += snprintf(buf + n, sizeof(buf) - n, " L%d=%d", i, (levels >> i) & 1);
      }
      Serial.println(buf);
    }
  }
}

// -----------------------------------------------------------------------------
// シリアルコマンド（ASCII・行末 LF。1文字ずつ届くので \n まで溜める）
// -----------------------------------------------------------------------------
static char g_line[SERIAL_LINE_MAX + 1];
static int  g_lineLen = 0;

// stats：金種ごとの再生回数と IGNORE / DISCARD / NOISE の回数。
// 正解率は「金種ごとに 50 枚まとめて入れ、その区間のカウントを見る」運用で出す（Task 6）
static void printStats() {
  Serial.println("=== stats ===");
  char buf[64];
  for (int i = 0; i < LANE_COUNT; ++i) {
    snprintf(buf, sizeof(buf), "L%d %3dyen : %lu", i, LANE_VALUE[i],
             static_cast<unsigned long>(g_countOk[i]));
    Serial.println(buf);
  }
  snprintf(buf, sizeof(buf), "IGNORE   : %lu", static_cast<unsigned long>(g_countIgnore));
  Serial.println(buf);
  snprintf(buf, sizeof(buf), "DISCARD  : %lu", static_cast<unsigned long>(g_countDiscard));
  Serial.println(buf);
  snprintf(buf, sizeof(buf), "NOISE    : %lu", static_cast<unsigned long>(g_countNoise));
  Serial.println(buf);
}

static void resetStats() {
  for (int i = 0; i < LANE_COUNT; ++i) g_countOk[i] = 0;
  g_countIgnore = g_countDiscard = g_countNoise = 0;
  Serial.println("stats reset");
}

// sim <lane>：センサー無しで、そのレーンに硬貨が来たことにする（配線前の動作確認用）
static void cmdSim(const char* arg) {
  const int lane = atoi(arg);
  if (lane < 0 || lane >= LANE_COUNT) {
    Serial.println("usage: sim <0-5>   (0=500yen 1=100yen 2=50yen 3=10yen 4=5yen 5=1yen)");
    return;
  }
  LanePulse p;
  p.lane = lane;
  p.t_ms = millis();
  p.width_us = SIM_PULSE_US;
  handleCoin(p);
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
    Serial.println("commands: help | stats | reset | sim <0-5> | play <1-7> | sensortest | exit");
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
  for (int i = 0; i < LANE_COUNT; ++i) {
    pinMode(PIN_LANE[i], INPUT);   // 外部 22kΩ プルアップ＋1kΩ 直列。内蔵プルアップは使わない
  }

  Serial.println("# coin-bank log v1 / boot");   // 集計スクリプトが起動を見つけるためのヘッダ（Task 6）
  logLine(millis(), "coin-bank v2.1 boot");

  Serial1.begin(DF_BAUD, SERIAL_8N1, PIN_DF_RX, PIN_DF_TX);
  if (!dfInit()) {
    g_state = SysState::Error;
    logLine(millis(), "ERROR: DFPlayer not responding. Check wiring (TX=GPIO6/RX=GPIO7, 5V, GND). Halted.");
    return;   // 以後 loop() は LED 点滅とコマンドだけ
  }
  g_df.volume(DF_VOLUME);   // 1回だけ。以後触らない（音量は VR1 で調整）

  sensorSelfCheck();

  g_policy.shouldPlay(millis());   // 起動直後の1回目は必ず true（起動音）
  playTrack(TRACK_BOOT);
  logLine(millis(), "boot sound -> play(%d)", TRACK_BOOT);

  // 割込は起動音の後に有効化する（起動直後の GPIO21 のブートログで誤検出しないため）
  for (int i = 0; i < LANE_COUNT; ++i) {
    attachInterrupt(digitalPinToInterrupt(PIN_LANE[i]), kLaneISR[i], CHANGE);
  }
  clearEdges();
  logLine(millis(), "IDLE");

  // Task WDT（Task 5）。Arduino core 2.x では loopTask が既定で未登録なので自分で登録する。
  // DFPlayer の初期化（リトライで 10 秒を超える）が終わってから有効にする
  esp_task_wdt_init(WDT_TIMEOUT_S, true);
  esp_task_wdt_add(NULL);
}

void loop() {
  esp_task_wdt_reset();   // ERROR 状態では未登録なので何もしない（戻り値は無視でよい）
  const uint32_t now = millis();
  ledUpdate(now);
  pollSerial();
  if (g_state == SysState::Error) return;   // ERROR：LED 点滅とコマンド以外は何もしない
  dfPoll();
  if (g_sensorTest) {
    sensorTestLoop(now);   // 試験モード中は判定・再生をしない
  } else {
    processEdges();
    checkJam(now);
  }
  // delay() は使わない（レーンのエッジを取りこぼす）
}
