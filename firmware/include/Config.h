// =============================================================================
// Config.h — 全定数の定義（v2.0：機械式ソータ＋光センサー6レーン）
//
// マジックナンバーをコード中に直接書かないこと。必ずここを参照する。
// ピン番号と定数の正は プロジェクトルートの CLAUDE.md。
// 電子セレクタ版（v1.x）の定義は archive/電子セレクタ案_2026-09-05/ に保持。
// =============================================================================
#pragma once

// -----------------------------------------------------------------------------
// ピンアサイン（Seeed XIAO ESP32C3）
//
// 括弧内は基板のシルク印字（D番号）。基板を見るときはこちらで探す。
// 使用禁止：GPIO 2, 9（ブートストラップ。入力にも使わない）
//           11〜17（内蔵フラッシュ）
// GPIO 8 はストラップピンだが、LED をアクティブ LOW（アイドル HIGH）で繋ぐ限り安全。
// GPIO 21 は起動時にブートログを出す（UART0 TX）。センサー側に直列 1kΩ を入れて保護する。
// -----------------------------------------------------------------------------
constexpr int LANE_COUNT = 6;

// レーン i（0〜5）のセンサー入力。フォトトランジスタのコレクタ → 1kΩ → GPIO。
// 光が通っている（硬貨なし）= LOW、硬貨が遮った = HIGH。CHANGE で割込（v2.1〜）。
//   レーン0 = 500円 GPIO4  (D2)
//   レーン1 = 100円 GPIO5  (D3)
//   レーン2 =  50円 GPIO3  (D1)
//   レーン3 =  10円 GPIO10 (D10)
//   レーン4 =   5円 GPIO20 (D7)
//   レーン5 =   1円 GPIO21 (D6)
constexpr int PIN_LANE[LANE_COUNT] = {4, 5, 3, 10, 20, 21};

constexpr int PIN_DF_TX = 6;   // D4  → DFPlayer RX（UART1 TX）
constexpr int PIN_DF_RX = 7;   // D5  ← DFPlayer TX（UART1 RX）

// ステータス LED。3.3V → 470Ω → LED → GPIO8（アクティブ LOW）。GPIO8 は 10kΩ で 3.3V へプルアップ。
constexpr int PIN_LED = 8;     // D8
constexpr int LED_ON_LEVEL = 0;   // LOW で点灯

// -----------------------------------------------------------------------------
// レーン → 金種／トラック
//
// SD のファイル名は電子セレクタ版から変更なし（0001=500円 … 0006=1円、0007=起動音）。
// -----------------------------------------------------------------------------
constexpr int LANE_VALUE[LANE_COUNT] = {500, 100, 50, 10, 5, 1};
constexpr int LANE_TRACK[LANE_COUNT] = {1, 2, 3, 4, 5, 6};

// -----------------------------------------------------------------------------
// 判定
// -----------------------------------------------------------------------------
// 同一レーンで、直前のイベントからこの時間内の再検出は無視する（ms）。
// 穴あき硬貨（5円・50円）で光が一瞬戻って二重に立ち上がるのと、落下中の跳ねを吸収する。
// ★暫定値。センサー実測（Task 8 の sensortest モード）で確定する。
constexpr unsigned long LANE_HOLDOFF_MS = 150;

// 連打ガード（ms）。直前の再生開始からこの時間は新しい再生をしない。
constexpr unsigned long RETRIG_MS = 300;

// これより短い HIGH はノイズとみなす（µs）。硬貨の通過はヘッド直下で約 8ms、筒の下部でも約 4ms 続く。
// v2.1：割込を CHANGE にし、ISR で立ち上がり〜立ち下がりの幅を測って判定する（loop の遅延に依存しない）。
constexpr unsigned long LANE_MIN_HIGH_US = 2000;

// HIGH（遮光）がこれ以上続いたら硬貨が筒で止まっている（詰まり）とみなす（ms）。
// 音は鳴らして（硬貨は入っている）、警告ログと LED のゆっくり点滅で知らせる。★暫定値
constexpr unsigned long LANE_JAM_MS = 200;

// sim コマンドで注入する擬似パルスの幅（µs）。硬貨らしい値にする
constexpr unsigned long SIM_PULSE_US = 10000;

// -----------------------------------------------------------------------------
// センサー自己診断
// -----------------------------------------------------------------------------
// 起動時、この時間だけ待ってから全レーンを読む（ms）。
constexpr unsigned long SENSOR_SETTLE_MS = 200;
// 起動時に HIGH（遮光）のレーンがあれば「詰まり or LED 不良」として警告する。
// 動作は止めない（他のレーンは使える）。

// -----------------------------------------------------------------------------
// DFPlayer
// -----------------------------------------------------------------------------
constexpr int DF_VOLUME     = 25;    // 音量（0〜30）。起動時に1回だけ設定し、以後変更しない
constexpr int DF_INIT_RETRY = 3;     // 初期化のリトライ回数
constexpr int TRACK_BOOT    = 7;     // 起動音のトラック番号（0007.mp3・約0.4秒）
constexpr unsigned long DF_BAUD = 9600;
constexpr unsigned long DF_RETRY_WAIT_MS = 1000;   // 初期化失敗時、次のリトライまでの待ち

// -----------------------------------------------------------------------------
// ステータス LED の点灯パターン（アクティブ LOW。詳細は開発計画 Task 5）
// -----------------------------------------------------------------------------
constexpr unsigned long LED_PLAY_MS        = 30;    // 再生開始時に点灯する長さ
constexpr unsigned long LED_WARN_PERIOD_MS = 1000;  // センサー警告：この周期でゆっくり点滅
constexpr unsigned long LED_ERROR_MS       = 80;    // ERROR：この周期で点滅し続ける

// -----------------------------------------------------------------------------
// 監視・シリアルコマンド
// -----------------------------------------------------------------------------
constexpr int WDT_TIMEOUT_S = 8;                    // Task WDT のタイムアウト（秒）
constexpr int SERIAL_LINE_MAX = 32;                 // コマンド1行の最大文字数（ASCII）
constexpr unsigned long SENSORTEST_PRINT_MS = 100;  // sensortest モードでレーン現在値を出す周期
constexpr int SENSORTEST_FORCE_PRINT_EVERY = 10;    // 変化が無くてもこの回数に1回は現在値を出す（=1秒）
constexpr int LANE_EDGE_BUF = 64;                   // 割込が積むエッジ（立ち上がり／立ち下がり）のリングバッファ長。通常動作と sensortest で共用

// -----------------------------------------------------------------------------
// シリアル
// -----------------------------------------------------------------------------
constexpr unsigned long SERIAL_BAUD = 115200;
// USB-CDC の送信待ち上限（ms）。USB を PC に挿したままターミナルを閉じていると
// 既定の 100ms×書き込み回数だけ loop が止まるので短くする（未接続時は元から止まらない）
constexpr unsigned long SERIAL_TX_TIMEOUT_MS = 5;

// =============================================================================
// v3.0：自作ソータ（判別レール＋ビーム 5 本）モード。env:esp32c3（既定）で使う。
// とりだし君のレーン方式（v2.1）は env:esp32c3_lane に残してある（上の LANE_* を使う）。
//
// 判定の仕様の下書きは 3Dプリント/自作判別部/sim/system_test.py の decide()（hole_rule="or"）。
// ここの値はシミュレーション（1 枚ずつ 99.5%）で決めたもの。★実機の試験で見直す。
// =============================================================================
// ビームの番号（CoinTracker::onEdge の beam）
constexpr int SS_BEAM_COUNT = 5;
constexpr int SS_BEAM_HA = 0;   // 穴 A（x=35・橋）：入口と穴の有無
constexpr int SS_BEAM_HB = 1;   // 穴 B（x=49・橋）：硬貨を数える。穴の有無（A と冗長）
constexpr int SS_BEAM_P1 = 2;   // 通過 P1（x=98・W1 の後）：ここを通った＝1円/50円ではない
constexpr int SS_BEAM_P2 = 3;   // 通過 P2（x=134・W2 の後）：ここを通った＝5円/100円ではない
constexpr int SS_BEAM_P3 = 4;   // 通過 P3（x=173.5・W3 の後）：ここを通った＝500円

// 2026-10-08 実機の個別遮光で、物理 P1 は GPIO5、物理 P2 は GPIO3 と確認。
// 当初の配線図とは逆なので、現物を配線し直さず入力の対応をここで補正する。
constexpr int PIN_SS_BEAM[SS_BEAM_COUNT] = {20, 21, 5, 3, 4};   // HA, HB, P1, P2, P3
constexpr int PIN_SS_SPARE = 10;   // 予備。使わない（CN1 の 4 番と 8 番を短絡して GND に落としてある）
constexpr const char* SS_BEAM_NAME[SS_BEAM_COUNT] = {"HA", "HB", "P1", "P2", "P3"};

// ビームの位置（mm。レールの上流端から）。3Dプリント/自作判別部/selfsort_params.scad の
// hole_beam_x / pass_beam_x と同じ値にする（形を変えたらここも直す）
constexpr double SS_BEAM_X_MM[SS_BEAM_COUNT] = {35.0, 49.0, 98.0, 134.0, 173.5};

// 穴ビームの遮光のかたまり：光がこの時間以上戻ったら、かたまり（＝硬貨 1 枚）の終わり（ms）。
// 遅い硬貨（60mm/s）では穴の割れ目が 40ms を超えるので 80
constexpr unsigned long SS_GROUP_GAP_MS = 80;
// 穴 B のかたまりがこれより短ければ「ちらつき」として数えない（ms）
constexpr unsigned long SS_MIN_PASS_MS = 20;
// 通過ビーム P1〜P3：これより短い遮光は無視（ms）
constexpr unsigned long SS_P_MIN_MS = 8;

// 期限：次の P に来るはずの時間 ＝ K × 段の距離 ÷ 直前の速さ ＋ 余裕。段ごとに下限・上限で挟む
constexpr double SS_K_DEADLINE = 1.8;
constexpr unsigned long SS_T_MARGIN_MS = 80;
constexpr unsigned long SS_T_CLAMP_MS[3][2] = {{250, 900}, {200, 700}, {200, 800}};   // 段 0（入口→P1）・1（P1→P2）・2（P2→P3）
constexpr double SS_V_DEFAULT_MM_S = 250.0;   // 速さが分からないとき（穴 A の相方が無い）に使う
constexpr double SS_V_MIN_MM_S = 60.0;        // 速さの下限（期限が長くなりすぎないように）
constexpr unsigned long SS_V_MIN_DT_MS = 5;   // これより短い時間差からは速さを出さない
constexpr unsigned long SS_A_LOOKBACK_MS = 500;   // 穴 B の入口から、この時間前までの穴 A を相方として探す

// 穴の判定：かたまりの中の隣り合う 2 回の遮光（a1,b1）（a2,b2）が
//   割れ目 (a2-b1) ÷ 全体 (b2-a1) が MIN〜MAX、かつ 2 回の長さの比 (b1-a1)/(b2-a2) が MIN〜MAX → 穴あり
constexpr double SS_HOLE_GAP_RATIO_MIN   = 0.04;   // これ未満は「硬貨 2 枚が接して通った」
constexpr double SS_HOLE_GAP_RATIO_MAX   = 0.45;
constexpr double SS_HOLE_PULSE_RATIO_MIN = 0.4;    // 2 回の長さがほぼ同じ（穴の両側）
constexpr double SS_HOLE_PULSE_RATIO_MAX = 2.5;

// ビームがこれ以上遮られ続けたら詰まりとみなす（ms）。60mm/s の硬貨でも 1 本を 0.35 秒で抜ける。
// 警告ログと LED のゆっくり点滅。穴 B が詰まっている間も、ほかの硬貨の判定は止めない
constexpr unsigned long SS_BEAM_JAM_MS = 1000;

// 方式 S（2026-10-10）：ビームの上で止まってから動き出した硬貨の扱い
//   期限を「ビームから抜けた時刻 − SS_STALL_BACK_MM を進む時間」から数え直す（止まっていた時間を数えない）。
//   止まらずに通った硬貨は遮光の長さが直径ぶん（最大 26.5mm）なので、直径 2 枚ぶん（53mm）なら数え直しは起きない
//   硬貨が遮った P がまだ遮られている間は、次の段の期限が切れても待つ。ただし遮られ始めてから
//   SS_STALL_CAP_MS を過ぎたら待たずに決める（詰まった硬貨をいつまでも待たない）
//   5961 ケースの試験で P の上で止まる 52.8%→100%、穴 B の上で止まる 29.2%→47.2%。ほかの結果は同じ
constexpr double SS_STALL_BACK_MM = 53.0;
constexpr unsigned long SS_STALL_CAP_MS = 3000;

// 入口で数えていない硬貨が P を通ったとき（2 枚が接して 1 枚に数えた等）、その段から追い始めて音を鳴らすか。
// 2026-10-10 に false（拾わない）へ変更：穴 A と穴 B の両方を通ったと確かめた硬貨だけを鳴らす仕様にした。
// 入口での見落としで鳴らないことより、P だけのノイズ・P の遮り直しで余計な音が鳴る方を重く見た。
// true に戻すと、穴は分からないので「なし」として扱う（5円→100円と言う可能性がある）
constexpr bool SS_ADOPT_ORPHAN = false;
// （SS_ADOPT_ORPHAN = true のときだけ使う）
// 拾うのは P を SS_ADOPT_MIN_MS 以上遮ったときだけ（ms）。P を通った硬貨が次の窓へ傾くとき、
// 同じ P をもう一度 15〜31ms 遮ることがあり、拾うと余計な音が 1 回鳴る。本物の通過は 54ms 以上
// （シミュレーション 472 件で確認。2026-09-27）。実物の硬貨がもっと速くて細い遮光になっても、
// 拾わないだけで decide() と同じ動きに戻る（安全側）
constexpr unsigned long SS_ADOPT_MIN_MS = 40;

// 連打ガード（ms）。この方式では 1 枚につき必ず 1 回だけ決まるので使わない（0）。
// 300 にすると、続けて入れた硬貨の正しい音を捨ててしまう（シミュレーションで確認）
constexpr unsigned long SS_RETRIG_MS = 0;

// どこで落ちたか → 金額。[段][穴なし=0 / 穴あり=1]
//   段 0：P1 に来なかった（W1 で落ちた） 段 1：P2 に来なかった（W2） 段 2：P3 に来なかった（W3） 段 3：P3 を通った
// 金額 → トラック番号は LANE_VALUE / LANE_TRACK の表をそのまま使う（音声ファイルは変えない）
constexpr int SS_STAGE_VALUE[4][2] = {{1, 50}, {100, 5}, {10, 10}, {500, 500}};

// sim コマンド（センサー無しで判定から音まで通す）で使う硬貨の形。並びは LANE_VALUE と同じ（500,100,50,10,5,1）
constexpr double SS_SIM_DIAM_MM[LANE_COUNT] = {26.5, 22.6, 21.0, 23.5, 22.0, 20.0};
constexpr double SS_SIM_HOLE_MM[LANE_COUNT] = {0.0, 0.0, 4.0, 0.0, 5.0, 0.0};
constexpr double SS_SIM_SPEED_MM_S = 250.0;       // sim の硬貨の速さ（速さを省いたとき）
constexpr double SS_SIM_SPEED_MAX_MM_S = 1000.0;  // sim で指定できる速さの上限（下限は SS_V_MIN_MM_S）
constexpr unsigned long SS_SIM_START_DELAY_MS = 20;   // sim コマンドから硬貨が穴 A に来るまで

// 追跡の上限など（バッファの大きさ）
constexpr int SS_MAX_COINS    = 8;    // レール上で同時に追う硬貨。物理的には 3〜4 枚まで。あふれたら一番古いものを決めてしまう
constexpr int SS_A_GROUP_BUF  = 16;   // 穴 A のかたまりの記録
constexpr int SS_EVENT_BUF    = 16;   // 処理待ちの P の通過
constexpr int SS_RESULT_BUF   = 8;    // 決まった結果（loop が毎回取り出す）
constexpr int SS_SIM_EDGE_BUF = 32;   // sim コマンドが積む擬似エッジ（1 枚で最大 14 本）
