# -*- coding: utf-8 -*-
"""
netlist.py から KiCad の回路図（.kicad_sch）を生成する。
=============================================================================
方式：各ピンから短い線を出し、その先に「ネット名のラベル」を置く。
      同じ名前のラベル同士が KiCad の中で繋がる。
      線を引き回さないので生成が確実で、ERC（配線ミス検出）は同じように効く。

使い方：
    python gen_kicad_sch.py
    → 貯金箱制御基板/貯金箱制御基板.kicad_sch と .kicad_pro を作る

検証：
    kicad-cli sch erc 貯金箱制御基板/貯金箱制御基板.kicad_sch
    kicad-cli sch export pdf 貯金箱制御基板/貯金箱制御基板.kicad_sch
=============================================================================
"""
import io, os, uuid, hashlib
from netlist import PARTS, NETS, NO_CONNECT, LANES, check

OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "貯金箱制御基板")
PROJECT = "貯金箱制御基板"

# 再現性のある UUID（毎回同じファイルが出るように）
def uid(*parts):
    h = hashlib.md5(("::".join(str(p) for p in parts)).encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"

ROOT_UUID = uid("root")

# =============================================================================
# ピンの電気的タイプ（ERC がこれを見て「電源が供給されていない」等を判定する）
# =============================================================================
PIN_TYPE = {
    ("TB1", "1"): "power_out",   # 外から入ってくる 12V
    ("TB1", "2"): "power_out",   # 外から入ってくる GND
    ("U1", "1"):  "power_in",
    ("U1", "2"):  "power_in",
    ("U1", "3"):  "power_out",   # 5V を作る
    ("U2", "12"): "power_out",   # XIAO の内蔵レギュレータ 3V3 出力
    ("U2", "13"): "power_in",
    ("U2", "14"): "power_in",
    ("U3", "1"):  "power_in",
    ("U3", "7"):  "power_in",
    ("U3", "10"): "power_in",
    # XIAO の信号ピン
    ("U2", "5"):  "output",      # UART TX
    ("U2", "6"):  "input",       # UART RX
    ("U2", "9"):  "bidirectional",
    ("U3", "2"):  "input",       # DFPlayer RX
    ("U3", "3"):  "output",      # DFPlayer TX
    ("U3", "5"):  "output",      # DAC_L
}
for _i, _y, _p, _n in LANES:
    PIN_TYPE[("U2", _p)] = "input"


# =============================================================================
# シンボル定義（ライブラリを持っていなくても開けるよう、ファイルに埋め込む）
# =============================================================================
def eff(size=1.27, hide=False, justify=None):
    j = f" (justify {justify})" if justify else ""
    h = " (hide yes)" if hide else ""
    return f"(effects (font (size {size} {size})){j}{h})"


def sym_props(name, ref_prefix, ref_at, val_at):
    # (at ...) は「x y 角度」の3つ。余計な値を付けるとファイルが読めなくなる
    return f"""    (property "Reference" "{ref_prefix}" (at {ref_at}) {eff()})
    (property "Value" "{name}" (at {val_at}) {eff()})
    (property "Footprint" "" (at 0 0 0) {eff(hide=True)})
    (property "Datasheet" "~" (at 0 0 0) {eff(hide=True)})
    (property "Description" "" (at 0 0 0) {eff(hide=True)})"""


def two_pin_symbol(libname, ref_prefix, graphic, pin1_type="passive", pin2_type="passive",
                   pin1_name="~", pin2_name="~"):
    """縦置きの2ピン部品。ピン1が上(+3.81)、ピン2が下(-3.81)

    ※ 内側の (symbol "..._0_1") の名前は、親シンボル名と必ず一致させること。
       ここが違うと KiCad はファイルごと読み込めない（2026-09-06 に踏んだ）。
    """
    sym = libname.split(':')[1]
    return f"""  (symbol "{libname}"
    (pin_numbers (hide yes))
    (pin_names (offset 0) (hide yes))
    (exclude_from_sim no) (in_bom yes) (on_board yes)
{sym_props(sym, ref_prefix, "2.54 0 90", "-2.54 0 90")}
    (symbol "{sym}_0_1"
{graphic}
    )
    (symbol "{sym}_1_1"
      (pin {pin1_type} line (at 0 3.81 270) (length 1.27)
        (name "{pin1_name}" {eff()}) (number "1" {eff()}))
      (pin {pin2_type} line (at 0 -3.81 90) (length 1.27)
        (name "{pin2_name}" {eff()}) (number "2" {eff()}))
    )
  )"""


def box_symbol(libname, ref_prefix, pins, width=25.4):
    """左側にピンを縦に並べた箱。pins は [(番号, 名前, タイプ), ...]"""
    n = len(pins)
    h = max(n * 2.54 + 2.54, 7.62)
    top = h / 2
    lines = []
    for i, (num, pname, ptype) in enumerate(pins):
        y = top - 2.54 * (i + 1)
        lines.append(
            f'      (pin {ptype} line (at {-width/2 - 5.08:.2f} {y:.2f} 0) (length 5.08)\n'
            f'        (name "{pname}" {eff(1.016)}) (number "{num}" {eff(1.016)}))')
    body = "\n".join(lines)
    return f"""  (symbol "{libname}"
    (pin_names (offset 1.016))
    (exclude_from_sim no) (in_bom yes) (on_board yes)
{sym_props(libname.split(':')[1], ref_prefix, f"{-width/2:.2f} {top+2.54:.2f} 90", f"{-width/2:.2f} {top+5.08:.2f} 90")}
    (symbol "{ref_prefix}_0_1"
      (rectangle (start {-width/2:.2f} {top:.2f}) (end {width/2:.2f} {-top:.2f})
        (stroke (width 0.254) (type default)) (fill (type background)))
    )
    (symbol "{ref_prefix}_1_1"
{body}
    )
  )"""


# --- 図形 --------------------------------------------------------------------
G_R = """      (rectangle (start -1.016 -2.54) (end 1.016 2.54)
        (stroke (width 0.254) (type default)) (fill (type none)))"""

G_C = """      (polyline (pts (xy -2.032 -0.762) (xy 2.032 -0.762))
        (stroke (width 0.508) (type default)) (fill (type none)))
      (polyline (pts (xy -2.032 0.762) (xy 2.032 0.762))
        (stroke (width 0.508) (type default)) (fill (type none)))"""

G_CP = """      (rectangle (start -2.032 0.508) (end 2.032 1.016)
        (stroke (width 0.0) (type default)) (fill (type outline)))
      (rectangle (start -2.032 -1.016) (end 2.032 -0.508)
        (stroke (width 0.0) (type default)) (fill (type none)))
      (polyline (pts (xy -1.524 2.032) (xy -0.508 2.032))
        (stroke (width 0.254) (type default)) (fill (type none)))
      (polyline (pts (xy -1.016 1.524) (xy -1.016 2.54))
        (stroke (width 0.254) (type default)) (fill (type none)))"""

G_D = """      (polyline (pts (xy -1.27 -1.27) (xy 1.27 -1.27) (xy 0 1.27) (xy -1.27 -1.27))
        (stroke (width 0.254) (type default)) (fill (type none)))
      (polyline (pts (xy -1.27 1.27) (xy 1.27 1.27))
        (stroke (width 0.508) (type default)) (fill (type none)))
      (polyline (pts (xy 1.27 1.27) (xy 1.905 1.905))
        (stroke (width 0.254) (type default)) (fill (type none)))
      (polyline (pts (xy -1.27 1.27) (xy -1.905 0.635))
        (stroke (width 0.254) (type default)) (fill (type none)))"""

G_LED = """      (polyline (pts (xy -1.27 -1.27) (xy 1.27 -1.27) (xy 0 1.27) (xy -1.27 -1.27))
        (stroke (width 0.254) (type default)) (fill (type none)))
      (polyline (pts (xy -1.27 1.27) (xy 1.27 1.27))
        (stroke (width 0.508) (type default)) (fill (type none)))
      (polyline (pts (xy 1.778 -0.508) (xy 3.048 -1.778))
        (stroke (width 0.152) (type default)) (fill (type none)))
      (polyline (pts (xy 2.286 0.254) (xy 3.556 -1.016))
        (stroke (width 0.152) (type default)) (fill (type none)))"""

G_F = """      (rectangle (start -1.016 -2.54) (end 1.016 2.54)
        (stroke (width 0.254) (type default)) (fill (type none)))
      (polyline (pts (xy -1.016 1.27) (xy 1.016 -1.27))
        (stroke (width 0.254) (type default)) (fill (type none)))"""


G_PWR = """      (polyline (pts (xy 0 0) (xy 0 1.27) (xy -1.016 1.905) (xy 0 2.54) (xy 1.016 1.905) (xy 0 1.27))
        (stroke (width 0.0) (type default)) (fill (type outline)))"""

# 電源フラグ：ERC に「このネットは外から電源が供給されている」と教えるための印。
# 実部品ではない。ヒューズや抵抗の先の電源ネットに置かないと
# 「Input Power pin not driven」エラーになる。
PWR_FLAG_SYMBOL = f"""  (symbol "bank:PWR_FLAG"
    (power)
    (pin_numbers (hide yes))
    (pin_names (offset 0) (hide yes))
    (exclude_from_sim yes) (in_bom no) (on_board yes)
    (property "Reference" "#FLG" (at 0 5.08 0) {eff()})
    (property "Value" "PWR_FLAG" (at 0 6.35 0) {eff()})
    (property "Footprint" "" (at 0 0 0) {eff(hide=True)})
    (property "Datasheet" "~" (at 0 0 0) {eff(hide=True)})
    (symbol "PWR_FLAG_0_0"
      (pin power_out line (at 0 3.81 270) (length 1.27)
        (name "~" {eff()}) (number "1" {eff()}))
    )
    (symbol "PWR_FLAG_0_1"
{G_PWR}
    )
  )"""

# 電源フラグを置くネット（ヒューズ・ダイオード・抵抗の先で、ERC が供給元を見失う場所）
PWR_FLAG_NETS = ["+12V", "XIAO_5V", "DF_VCC"]


def build_lib_symbols():
    s = [PWR_FLAG_SYMBOL]
    s.append(two_pin_symbol("bank:R", "R", G_R))
    s.append(two_pin_symbol("bank:C", "C", G_C))
    s.append(two_pin_symbol("bank:CP", "CP", G_CP, pin1_name="+", pin2_name="-"))
    s.append(two_pin_symbol("bank:D_Schottky", "D", G_D, pin1_name="A", pin2_name="K"))
    s.append(two_pin_symbol("bank:LED", "LED", G_LED, pin1_name="A", pin2_name="K"))
    s.append(two_pin_symbol("bank:Polyfuse", "F", G_F))
    # 多ピン部品は箱
    for ref in ("U1", "U2", "U3", "VR1", "TB1", "TB2", "TB3", "CN1"):
        part = PARTS[ref]
        pins = []
        for num in sorted(part["pins"], key=lambda x: int(x)):
            ptype = PIN_TYPE.get((ref, num), "passive")
            pins.append((num, part["pins"][num], ptype))
        width = 33.02 if ref in ("U2", "U3") else 25.4
        s.append(box_symbol(f"bank:{ref}", ref, pins, width))
    return "\n".join(s)


# =============================================================================
# 部品の配置
# =============================================================================
TWO_PIN_LIB = {
    "F1": "bank:Polyfuse", "D1": "bank:D_Schottky", "D2": "bank:D_Schottky",
    "C1": "bank:CP", "C2": "bank:CP", "C3": "bank:CP", "C6": "bank:C",
    "R1": "bank:R", "R4": "bank:R", "R5": "bank:R", "LED1": "bank:LED",
}
for _i, _y, _p, _n in LANES:
    TWO_PIN_LIB[f"R1{_i+1}"] = "bank:R"
    TWO_PIN_LIB[f"R2{_i+1}"] = "bank:R"

# グループ（見出し, [部品...]）を左上から順に並べる
GROUPS = [
    ("1. 電源入力 12V", ["TB1", "F1", "D1", "C1"]),
    ("2. 5V 生成", ["U1", "C2"]),
    ("3. XIAO への 5V", ["D2"]),
    ("4. DFPlayer ノイズ対策", ["R1", "C3"]),
    ("5. レーン入力 ×6（22k プルアップ ＋ 1k 直列）",
     [f"R1{i+1}" for i in range(6)] + [f"R2{i+1}" for i in range(6)]),
    ("6. ステータス LED（LOWで点灯）", ["R4", "LED1", "R5"]),
    ("7. 音声出力", ["C6", "VR1"]),
    ("8. マイコン", ["U2"]),
    ("9. MP3 モジュール", ["U3"]),
    ("10. 外部接続（端子台）", ["CN1", "TB2", "TB3"]),
]

# ネット名を (部品, ピン) から引けるようにする
PIN_NET = {}
for net, nodes in NETS.items():
    for ref, pin in nodes:
        PIN_NET[(ref, pin)] = net


G = 1.27   # KiCad の配線グリッド。全部これの倍数に揃えないと ERC が「グリッド外」と怒る


def snap(v):
    return round(v / G) * G


COL_W   = 180.34   # 1段の幅（mm）= 71 グリッド
COL_TOP = 40.64
COL_BOT = 386.08   # A2（594×420mm）の下端手前まで
ITEM_W  = 20.32    # 2ピン部品1つぶんの横幅
ROW_H   = 33.02    # 2ピン部品1行ぶんの高さ


def group_size(refs):
    """その群が必要とする高さを先に見積もる（段の折り返し判断に使う）"""
    per_row = max(1, int((COL_W - 15.24) // ITEM_W))
    two_pin = [r for r in refs if r in TWO_PIN_LIB]
    boxes = [r for r in refs if r not in TWO_PIN_LIB]
    h = 0.0
    if two_pin:
        h += ROW_H * ((len(two_pin) + per_row - 1) // per_row)
    for ref in boxes:
        h += len(PARTS[ref]["pins"]) * 2.54 + 22.86
    return h + 12.7


def place():
    """部品の座標を決める。A2 用紙に段組みで並べ、全部 1.27mm グリッドに載せる"""
    pos, headers = {}, []
    per_row = max(1, int((COL_W - 15.24) // ITEM_W))
    x, y = 38.1, COL_TOP

    for title, refs in GROUPS:
        # この群が今の段に入らなければ次の段へ
        if y + group_size(refs) > COL_BOT and y > COL_TOP:
            x = snap(x + COL_W)
            y = COL_TOP

        headers.append((x, snap(y - 7.62), title))

        two_pin = [r for r in refs if r in TWO_PIN_LIB]
        boxes = [r for r in refs if r not in TWO_PIN_LIB]

        for i, ref in enumerate(two_pin):
            col, row = i % per_row, i // per_row
            pos[ref] = (snap(x + col * ITEM_W), snap(y + row * ROW_H + 12.7))
        if two_pin:
            y = snap(y + ROW_H * ((len(two_pin) + per_row - 1) // per_row))

        for ref in boxes:
            n = len(PARTS[ref]["pins"])
            h = n * 2.54 + 10.16
            pos[ref] = (snap(x + 38.1), snap(y + h / 2 + 6.35))
            y = snap(y + h + 22.86)

        y = snap(y + 10.16)

    return pos, headers


# =============================================================================
# 出力
# =============================================================================
def gen():
    probs = check()
    if probs:
        raise SystemExit("netlist.py に問題があります:\n  " + "\n  ".join(probs))

    pos, headers = place()
    out = []
    out.append('(kicad_sch')
    out.append('  (version 20231120)')
    out.append('  (generator "gen_kicad_sch.py")')
    out.append('  (generator_version "8.0")')
    out.append(f'  (uuid "{ROOT_UUID}")')
    out.append('  (paper "A2")')
    out.append('  (title_block')
    out.append('    (title "コイン別音声貯金箱 制御基板")')
    out.append('    (date "2026-09-06")')
    out.append('    (rev "v2.1")')
    out.append('    (comment 1 "netlist.py から自動生成。回路を変えるときは netlist.py を直す")')
    out.append('    (comment 2 "同じ名前のラベル同士がつながっている")')
    out.append('  )')
    out.append('  (lib_symbols')
    out.append(build_lib_symbols())
    out.append('  )')

    # --- 見出し ---
    for hx, hy, title in headers:
        out.append(f'  (text "{title}" (exclude_from_sim no) (at {hx:.2f} {hy:.2f} 0)\n'
                   f'    (effects (font (size 2.54 2.54) (bold yes)) (justify left bottom)) (uuid "{uid("h", title)}"))')

    # --- 部品 ---
    for ref, part in PARTS.items():
        x, y = pos[ref]
        lib = TWO_PIN_LIB.get(ref, f"bank:{ref}")
        pin_uuids = "\n".join(f'    (pin "{p}" (uuid "{uid(ref, "pin", p)}"))'
                              for p in sorted(part["pins"], key=lambda v: int(v)) if p.isdigit()) \
            if all(p.isdigit() for p in part["pins"]) else \
            "\n".join(f'    (pin "{p}" (uuid "{uid(ref, "pin", p)}"))' for p in part["pins"])
        if ref in TWO_PIN_LIB:
            rx, ry = x + 4.0, y - 5.0
            vx, vy = x + 4.0, y - 2.0
        else:
            n = len(part["pins"])
            rx, ry = x - 12.7, y - (n * 2.54 / 2 + 6.0)
            vx, vy = x - 12.7, y - (n * 2.54 / 2 + 3.0)
        out.append(f'''  (symbol (lib_id "{lib}") (at {x:.2f} {y:.2f} 0) (unit 1)
    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)
    (uuid "{uid(ref)}")
    (property "Reference" "{ref}" (at {rx:.2f} {ry:.2f} 0) {eff(1.27, justify="left")})
    (property "Value" "{part["value"]}" (at {vx:.2f} {vy:.2f} 0) {eff(1.27, justify="left")})
    (property "Footprint" "" (at {x:.2f} {y:.2f} 0) {eff(hide=True)})
    (property "Datasheet" "~" (at {x:.2f} {y:.2f} 0) {eff(hide=True)})
    (property "説明" "{part["desc"]}" (at {x:.2f} {y:.2f} 0) {eff(1.0, hide=True)})
    (property "秋月" "{part.get("akizuki","")}" (at {x:.2f} {y:.2f} 0) {eff(1.0, hide=True)})
{pin_uuids}
    (instances (project "{PROJECT}"
      (path "/{ROOT_UUID}" (reference "{ref}") (unit 1))))
  )''')

    # --- 各ピンから線とラベル ---
    nc_set = set(NO_CONNECT)
    for ref, part in PARTS.items():
        x, y = pos[ref]
        for num in part["pins"]:
            if ref in TWO_PIN_LIB:
                # ピン1は上、ピン2は下
                if num == "1":
                    px, py = x, y - 3.81      # KiCad は Y が下向きなので上＝マイナス
                    ex, ey = x, y - 8.89
                    rot, just = 90, "left bottom"
                else:
                    px, py = x, y + 3.81
                    ex, ey = x, y + 8.89
                    rot, just = 270, "left bottom"
            else:
                n = len(part["pins"])
                idx = sorted(part["pins"], key=lambda v: int(v)).index(num)
                top = (n * 2.54 + 2.54) / 2
                width = 33.02 if ref in ("U2", "U3") else 25.4
                py = y - (top - 2.54 * (idx + 1))
                px = x - width / 2 - 5.08
                ex, ey = px - 6.35, py
                rot, just = 180, "right"

            key = (ref, num)
            if key in nc_set:
                out.append(f'  (wire (pts (xy {px:.2f} {py:.2f}) (xy {ex:.2f} {ey:.2f}))\n'
                           f'    (stroke (width 0) (type default)) (uuid "{uid(ref,num,"w")}"))')
                out.append(f'  (no_connect (at {ex:.2f} {ey:.2f}) (uuid "{uid(ref,num,"nc")}"))')
                continue

            net = PIN_NET.get(key)
            if net is None:
                continue
            out.append(f'  (wire (pts (xy {px:.2f} {py:.2f}) (xy {ex:.2f} {ey:.2f}))\n'
                       f'    (stroke (width 0) (type default)) (uuid "{uid(ref,num,"w")}"))')
            out.append(f'  (label "{net}" (at {ex:.2f} {ey:.2f} {rot})\n'
                       f'    (effects (font (size 1.27 1.27)) (justify {just})) (uuid "{uid(ref,num,"l")}"))')

    # --- 電源フラグ（ERC 用の印。実部品ではない）---
    fx, fy = 38.1, 20.32
    for k, net in enumerate(PWR_FLAG_NETS):
        x = fx + k * 38.1
        out.append(f'''  (symbol (lib_id "bank:PWR_FLAG") (at {x:.2f} {fy:.2f} 0) (unit 1)
    (exclude_from_sim yes) (in_bom no) (on_board yes) (dnp no)
    (uuid "{uid("flg", net)}")
    (property "Reference" "#FLG{k+1}" (at {x:.2f} {fy - 6.35:.2f} 0) {eff(1.0, hide=True)})
    (property "Value" "PWR_FLAG" (at {x:.2f} {fy - 8.89:.2f} 0) {eff(1.0)})
    (property "Footprint" "" (at {x:.2f} {fy:.2f} 0) {eff(hide=True)})
    (property "Datasheet" "~" (at {x:.2f} {fy:.2f} 0) {eff(hide=True)})
    (pin "1" (uuid "{uid("flg", net, "p")}"))
    (instances (project "{PROJECT}"
      (path "/{ROOT_UUID}" (reference "#FLG{k+1}") (unit 1))))
  )''')
        py = fy - 3.81
        ey = py - 5.08
        out.append(f'  (wire (pts (xy {x:.2f} {py:.2f}) (xy {x:.2f} {ey:.2f}))\n'
                   f'    (stroke (width 0) (type default)) (uuid "{uid("flg",net,"w")}"))')
        out.append(f'  (label "{net}" (at {x:.2f} {ey:.2f} 90)\n'
                   f'    (effects (font (size 1.27 1.27)) (justify left bottom)) (uuid "{uid("flg",net,"l")}"))')

    out.append(f'''  (sheet_instances
    (path "/" (page "1"))
  )
)''')

    os.makedirs(OUTDIR, exist_ok=True)
    sch = os.path.join(OUTDIR, f"{PROJECT}.kicad_sch")
    io.open(sch, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")

    # lib_symbol_issues は「bank ライブラリが KiCad に登録されていない」という警告。
    # シンボル定義はファイル内に埋め込んであるので表示にも ERC にも影響しない。無視に設定する。
    pro = os.path.join(OUTDIR, f"{PROJECT}.kicad_pro")
    io.open(pro, "w", encoding="utf-8", newline="\n").write(
        '{\n'
        '  "board": {"design_settings": {}},\n'
        '  "erc": {\n'
        '    "erc_exclusions": [],\n'
        '    "meta": {"version": 0},\n'
        '    "rule_severities": {"lib_symbol_issues": "ignore"}\n'
        '  },\n'
        '  "meta": {"filename": "%s.kicad_pro", "version": 1},\n'
        '  "schematic": {\n'
        '    "meta": {"version": 1},\n'
        '    "erc": {\n'
        '      "erc_exclusions": [],\n'
        '      "meta": {"version": 0},\n'
        '      "rule_severities": {"lib_symbol_issues": "ignore"}\n'
        '    }\n'
        '  },\n'
        '  "sheets": [["%s", "Root"]],\n'
        '  "text_variables": {}\n}\n' % (PROJECT, ROOT_UUID))

    print("生成:", sch)
    print("生成:", pro)
    print(f"  部品 {len(PARTS)} 個／ネット {len(NETS)} 本／ラベル {sum(len(v) for v in NETS.values())} 個／"
          f"未接続印 {len(NO_CONNECT)} 個")
    return sch


if __name__ == "__main__":
    gen()
