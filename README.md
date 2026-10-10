# コイン別音声貯金箱（Coin-sorting talking piggy bank）

投入された日本の硬貨（1/5/10/50/100/500円）を**自作の機械式判別レール＋光センサー 5 本**で見分け、
金種ごとに違う音声を鳴らす貯金箱です。イベント展示で子供が使う前提で、
「壊れないこと」「必ず音が鳴ること」「余計な音を鳴らさないこと」を最優先に作りました。

> A piggy bank that identifies Japanese coins with a custom 3D-printed rolling rail and five IR beams,
> then plays a different sound per denomination. Firmware: ESP32-C3 (Arduino/PlatformIO) with a
> hardware-independent, unit-tested decision core. Hardware: OpenSCAD parts, a physics-simulated rail design,
> and a perfboard generated from a Python netlist.

受託案件として製作したものです。依頼元の名称・契約に関する資料は含めていません。

## しくみ

```
硬貨（1 枚ずつ）
   │
   ▼  レールの上を立って転がる（下り 10°・壁の傾き 12°）
 [HA][HB] 穴ビーム 2 本 … 硬貨が入った合図・速さ・穴の有無（遮光が 2 回に割れる＝穴あり）
   │
   ├─ 窓 W1 → P1 … 小さい硬貨はここで裏へ倒れて落ちる
   ├─ 窓 W2 → P2
   └─ 窓 W3 → P3 … 通過ビーム。どこまで来たかを見る
   │
 XIAO ESP32C3 ──UART──▶ DFPlayer Mini ──▶ TDA2030 アンプ ──▶ スピーカー
```

どの P まで来たか（段）と穴の有無で金額を決めます。

| 段 | 意味 | 穴なし | 穴あり |
|---|---|---|---|
| 0 | P1 に来なかった（W1 で落ちた） | 1円 | 50円 |
| 1 | P1 を通り、P2 に来なかった | 100円 | 5円 |
| 2 | P2 を通り、P3 に来なかった | 10円 | — |
| 3 | P3 を通った | 500円 | — |

「次の P に来なかった」は、HA→HB の時間差から出した速さで期限を計算して判断します。
ビームの上で止まった硬貨・詰まり・手をかざしたとき・ノイズでは**鳴らさない**側に倒しています。

### 工夫した点

- **判定ロジックをハードから切り離した。**`firmware/lib/CoinTracker` は Arduino API を使わない純粋な C++ クラスで、
  時刻つきのエッジ列だけを入力に取ります。PC 上の単体テスト（Unity・66 件）で、穴あき硬貨・連続投入・
  ビーム上での停止・`micros()` の巻き戻りなどの異常系を実機なしで検証しています
- **割込はエッジの記録だけ。**ISR は（ビーム・レベル・`micros()`）をリングバッファに積み、判定は loop で行います。
  判定は ISR の時刻だけで決まるので、USB-CDC の送信待ちで loop が止まっても結果は変わりません
- **寸法は物理シミュレーションで決めた。**`hardware/sorter/sim/` で約 3 万回の転がりを計算し、
  レールの傾き・窓の位置を決めました。判定アルゴリズムもシミュレーション結果（ストレステスト 5961 件）で調整しています
- **回路は Python のネットリストが唯一の正。**`hardware/board/netlist.py` から KiCad 回路図（ERC 済み）と
  1:1 の実体配線図 PDF を生成し、照合まで自動で走らせます

## ディレクトリ

```
firmware/                 PlatformIO プロジェクト
  include/Config.h        定数はすべてここ（ピン・時間・しきい値）
  lib/CoinTracker/        ビーム 5 本のエッジ → 金額（自作レール版の判定。ハード非依存）
  lib/LaneDecoder/        レーン → 金種（市販ソータ＋センサー 6 本の旧版）
  lib/PlaybackPolicy/     再生の可否（連打ガード・割り込み再生）
  src/main_selfsort.cpp   Arduino 層（自作レール版 v3.0・既定）
  src/main_lane.cpp       Arduino 層（旧版 v2.1）
  test/                   PC 上の単体テスト
hardware/
  chassis_dims.scad       筐体寸法
  sorter/                 判別レール・ユニット箱（OpenSCAD）、組立図、物理シミュレーション、印刷用 STL
  board/                  制御基板（netlist.py → KiCad 回路図・実体配線図）
tools/coin_monitor.py     判別結果をリアルタイム表示し、正解率を出す PC ツール（試験用 GUI）
```

## ビルドとテスト

```bash
cd firmware
pio test -e native            # PC で単体テスト（実機不要）
pio run -e esp32c3            # 自作レール版をビルド
pio run -e esp32c3 -t upload  # 書き込み
pio device monitor            # 115200bps。help / stats / sim <金額> / play <n> / sensortest
```

`sim <金額>` でセンサー無しでも、その硬貨が転がったときのエッジを流し込んで判定から音まで確認できます。

## ハードウェア

| 部品 | 型番など |
|---|---|
| MCU | Seeed Studio XIAO ESP32C3 |
| 音声 | DFPlayer Mini（microSD の `/mp3/0001〜0007.mp3`） |
| アンプ | TDA2030 10W モノラルアンプキット（12V） |
| センサー | 赤外 LED OSI5LA5113A（940nm）＋ フォトトランジスタ L-51ROPT1D1 × 5 組 |
| 電源 | 12V AC アダプタ → BP5293-50（5V） |
| 判別部・筐体 | 3D プリント（PETG・サポートなし） |

音声ファイルは含めていません。
