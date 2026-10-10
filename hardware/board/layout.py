# -*- coding: utf-8 -*-
"""
ユニバーサル基板（秋月 103054 Bタイプ 95×72mm・2.54mmピッチ）の実体配置
=============================================================================
穴の呼び方：列 = 1〜32（左→右）、行 = A〜W（上→下）。例「12-F」
部品面（部品を挿す側）から見た座標で書く。

基板の実物：95×72mm、ランドピッチ 2.54mm、穴径 1.1mm、取付穴 φ3.2（88.9×66mm）
安全のため 32列×23行 の範囲だけを使う（実際のランド数が多少違っても収まる）。

ここは「どこに挿すか」だけを決める。どこを繋ぐかは netlist.py が正。
=============================================================================
"""
from netlist import PARTS, NETS, NO_CONNECT, LANES

COLS = 32          # 列 1..32
ROWS = 23          # 行 A..W
PITCH = 2.54       # mm

def rowname(r):    # 1 -> "A"
    return chr(ord("A") + r - 1)

def rownum(name):  # "A" -> 1
    return ord(name) - ord("A") + 1

def hole(col, row):
    return f"{col}-{rowname(row)}"


# =============================================================================
# 部品の足の位置  ref -> {ピン番号: (列, 行)}
# =============================================================================
PINPOS = {}
# 部品の占有範囲（本体が乗る範囲。ここには他の部品を置かない）
#   ref -> (col1, row1, col2, row2)
BODY = {}


def put_axial(ref, col, row, span, horizontal=True):
    """抵抗・ダイオードなど2本足を寝かせる。span = 端から端までの穴数"""
    if horizontal:
        PINPOS[ref] = {"1": (col, row), "2": (col + span - 1, row)}
        BODY[ref] = (col, row, col + span - 1, row)
    else:
        PINPOS[ref] = {"1": (col, row), "2": (col, row + span - 1)}
        BODY[ref] = (col, row, col, row + span - 1)


def put_radial(ref, col, row, span, horizontal=True, body=None):
    """電解コンデンサ・LEDなど。span = 足の間隔（穴数）。body=(w,h) 占有範囲を広げる"""
    if horizontal:
        PINPOS[ref] = {"1": (col, row), "2": (col + span - 1, row)}
        c1, r1, c2, r2 = col, row, col + span - 1, row
    else:
        PINPOS[ref] = {"1": (col, row), "2": (col, row + span - 1)}
        c1, r1, c2, r2 = col, row, col, row + span - 1
    if body:
        w, h = body
        cc = (c1 + c2) / 2
        rc = (r1 + r2) / 2
        c1, c2 = int(cc - w / 2), int(cc + w / 2)
        r1, r2 = int(rc - h / 2), int(rc + h / 2)
    BODY[ref] = (c1, r1, c2, r2)


def put_sip(ref, col, row, order, horizontal=True):
    """1列に並ぶピン。order = ピン番号の並び"""
    pos = {}
    for i, num in enumerate(order):
        pos[num] = (col + i, row) if horizontal else (col, row + i)
    PINPOS[ref] = pos
    cs = [p[0] for p in pos.values()]
    rs = [p[1] for p in pos.values()]
    BODY[ref] = (min(cs), min(rs), max(cs), max(rs))


def put_dip(ref, col_a, col_b, row, side_a, side_b):
    """2列のモジュール。side_a/side_b は上から順のピン番号"""
    pos = {}
    for i, num in enumerate(side_a):
        pos[num] = (col_a, row + i)
    for i, num in enumerate(side_b):
        pos[num] = (col_b, row + i)
    PINPOS[ref] = pos
    BODY[ref] = (min(col_a, col_b), row, max(col_a, col_b), row + max(len(side_a), len(side_b)) - 1)


def put_block(ref, col, row, poles, order):
    """端子台。極ピッチ 5.0mm ≒ 2穴。
    電線の差し込み口が基板の外（上）を向くように、本体は下（内側）へ約3行ぶん占める。"""
    pos = {}
    for i, num in enumerate(order):
        pos[num] = (col + i * 2, row)
    PINPOS[ref] = pos
    BODY[ref] = (col - 1, row - 1, col + (poles - 1) * 2 + 1, row + 3)


# -----------------------------------------------------------------------------
# ■ 上端（行B）：外部とつなぐ端子台
# -----------------------------------------------------------------------------
put_block("CN1", 2, 2, 8, ["1", "2", "3", "4", "5", "6", "7", "8"])   # 列 2,4,6,8,10,12,14,16
put_block("TB1", 20, 2, 2, ["1", "2"])                                # 列 20,22
put_block("TB2", 25, 2, 2, ["1", "2"])                                # 列 25,27
put_block("TB3", 30, 2, 2, ["1", "2"])                                # 列 30,32

# -----------------------------------------------------------------------------
# ■ 左側（行G〜Q の奇数行）：レーン入力回路 ×6
#     [+3V3]--22k--(レーン節点)--1k--[GPIO]
#     22k は 列2〜5、1k は 列7〜10。列5と列6ではなく、節点は列5＝列7を配線でつなぐ
# -----------------------------------------------------------------------------
LANE_ROWS = [7, 9, 11, 13, 15, 17]     # G, I, K, M, O, Q
for i, r in enumerate(LANE_ROWS):
    put_axial(f"R1{i+1}", 2, r, 5)     # 22k  列2-6   （1/4W 抵抗は本体 6.3mm。足の間隔 10.16mm＝5穴）
    put_axial(f"R2{i+1}", 8, r, 5)     # 1k   列8-12  （列13 の XIAO と隣り合わないよう 1 列あける）

# -----------------------------------------------------------------------------
# ■ 中央：XIAO ESP32C3（ピンソケットに挿す。2×7・列間 15.24mm ＝ 6ピッチ）
#     USB端子は上（行G側）を向く
# -----------------------------------------------------------------------------
put_dip("U2", 14, 20, 7,
        side_a=["1", "2", "3", "4", "5", "6", "7"],       # D0,D1,D2,D3,D4,D5,D6
        side_b=["14", "13", "12", "11", "10", "9", "8"])  # 5V,GND,3V3,D10,D9,D8,D7

# -----------------------------------------------------------------------------
# ■ 右：DFPlayer Mini（2×8・列間 17.78mm ＝ 7ピッチ）
# -----------------------------------------------------------------------------
put_dip("U3", 22, 29, 7,
        side_a=["1", "2", "3", "4", "5", "6", "7", "8"],
        side_b=["16", "15", "14", "13", "12", "11", "10", "9"])

# -----------------------------------------------------------------------------
# ■ 下段①（行T）：12V → 5V の電源部
# -----------------------------------------------------------------------------
put_radial("F1", 3, 20, 3, body=(5, 1))        # ポリスイッチ MF-R185  足の間隔 5.1mm＝列3,5（本体は幅 12mm で列2〜6 にまたがる）
put_axial("D1", 7, 20, 5)                       # SR54F        列7-11
put_radial("C1", 13, 20, 3, body=(3, 3))        # 470µF/25V Φ8・足 3.5mm → 列13,15（足を少し開く）
put_sip("U1", 17, 20, ["1", "2", "3"])          # BP5293-50    列17,18,19
put_radial("C2", 21, 20, 2, body=(3, 3))        # 220µF/16V Φ6.3・足 2.5mm → 列21,22
put_axial("D2", 25, 20, 5)                      # SR54F        列25-29

# -----------------------------------------------------------------------------
# ■ 下段②（行V）：DFPlayer 電源・音声・ステータスLED
# -----------------------------------------------------------------------------
put_axial("R1", 2, 22, 5)                       # 1Ω          列2-6
put_radial("C3", 8, 22, 2, body=(2, 2))         # 100µF/16V Φ5・足 2mm → 列8,9
put_axial("C6", 11, 22, 3)                      # 1µF（足 5mm） 列11-13
# 半固定10k 3362P：足は三角。両端の 1・3 は 2 穴あけて同じ行、真ん中の 2（ワイパー）だけ 1 行上
PINPOS["VR1"] = {"1": (16, 22), "2": (17, 21), "3": (18, 22)}
BODY["VR1"] = (16, 21, 18, 22)
put_axial("R4", 19, 22, 5)                      # 470Ω        列19-23
put_radial("LED1", 25, 22, 2)                   # LED         列25,26
put_axial("R5", 28, 22, 5)                      # 10kΩ        列28-32


# =============================================================================
# 検査
# =============================================================================
def check_layout():
    problems = []

    # 1. 全部品・全ピンに位置があるか
    for ref, part in PARTS.items():
        if ref not in PINPOS:
            problems.append(f"{ref} の配置が未定義")
            continue
        for pin in part["pins"]:
            if pin not in PINPOS[ref]:
                problems.append(f"{ref}.{pin} の位置が未定義")

    # 2. 盤面からはみ出していないか
    for ref, pins in PINPOS.items():
        for pin, (c, r) in pins.items():
            if not (1 <= c <= COLS and 1 <= r <= ROWS):
                problems.append(f"{ref}.{pin} が基板の外 ({hole(c,r)})")

    # 3. 同じ穴を2つの部品が使っていないか
    used = {}
    for ref, pins in PINPOS.items():
        for pin, pos in pins.items():
            if pos in used:
                problems.append(f"穴 {hole(*pos)} を {used[pos]} と {ref}.{pin} が奪い合っている")
            used[pos] = f"{ref}.{pin}"

    # 4. 本体（占有範囲）が重なっていないか
    refs = list(BODY)
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            a, b = BODY[refs[i]], BODY[refs[j]]
            if a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]:
                problems.append(f"本体が重なる：{refs[i]} {a} と {refs[j]} {b}")

    return problems


def pin_hole(ref, pin):
    return PINPOS[ref][pin]


if __name__ == "__main__":
    probs = check_layout()
    used = sum(len(p) for p in PINPOS.values())
    print(f"基板 {COLS}列 × {ROWS}行（{COLS*PITCH:.1f} × {ROWS*PITCH:.1f} mm 相当）")
    print(f"部品 {len(PINPOS)} 個 ／ 使用する穴 {used} 個")
    if probs:
        print(f"\n【問題 {len(probs)} 件】")
        for p in probs:
            print("  -", p)
    else:
        print("\n配置検査：問題なし")
