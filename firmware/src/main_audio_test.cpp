// 12V 単独で DFPlayer とアンプの 6 音声を確認する試験用ファーム。
// 書き込んだ後、USB を抜いて 12V を入れる。0007 起動音の後、
// 0001～0006 を番号順に 9.5 秒間隔で 1 回ずつ鳴らす。
// 試験が済んだら env:esp32c3 を書き戻すこと。

#include <Arduino.h>
#include <DFRobotDFPlayerMini.h>
#include "Config.h"

static DFRobotDFPlayerMini g_df;
static bool g_ready = false;
static int g_nextTrack = 1;
static unsigned long g_nextAt = 0;
constexpr unsigned long kFirstTrackDelayMs = 2000;
constexpr unsigned long kTrackIntervalMs = 9500;

void setup() {
  Serial.begin(SERIAL_BAUD);
  Serial.setTxTimeoutMs(SERIAL_TX_TIMEOUT_MS);
  Serial1.begin(DF_BAUD, SERIAL_8N1, PIN_DF_RX, PIN_DF_TX);

  for (int attempt = 1; attempt <= DF_INIT_RETRY; ++attempt) {
    g_df.begin(Serial1, /*isACK=*/false, /*doReset=*/true);
    const int files = g_df.readFileCounts(DFPLAYER_DEVICE_SD);
    if (files >= 0) {
      g_ready = true;
      break;
    }
    delay(DF_RETRY_WAIT_MS);
  }
  if (!g_ready) {
    Serial.println("audio test: DFPlayer not responding");
    return;
  }

  g_df.volume(DF_VOLUME);
  g_df.playMp3Folder(TRACK_BOOT);
  Serial.println("audio test: boot chime");
  g_nextAt = millis() + kFirstTrackDelayMs;
}

void loop() {
  if (!g_ready || g_nextTrack > 6) return;
  const unsigned long now = millis();
  if (static_cast<long>(now - g_nextAt) < 0) return;
  g_df.playMp3Folder(g_nextTrack);
  Serial.printf("audio test: track %d\n", g_nextTrack);
  ++g_nextTrack;
  g_nextAt = now + kTrackIntervalMs;
}
