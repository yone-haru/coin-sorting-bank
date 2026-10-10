# -*- coding: utf-8 -*-
"""
実体配線図（1:1 で印刷できる PDF）と配線チェックリストを作る
=============================================================================
出力：実体配線図.pdf
  1ページ目 部品面：どの穴に何を挿すか
  2ページ目 配線図（部品面から透視）：配線の全体像
  3ページ目 はんだ面：基板を裏返した向き。実際にはんだ付けするときはこれを見る
  4ページ目〜 配線チェックリスト：1本ずつ消し込む

★ 印刷は「実際のサイズ（100%・倍率調整なし）」で。基板を紙に載せて穴を数えられます。
=============================================================================
"""
import io, os
import fitz
from netlist import PARTS
from layout import COLS, ROWS, PITCH, PINPOS, BODY, hole, rowname
import wiring

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "実体配線図.pdf")

MM = 72.0 / 25.4          # 1mm を PDF の単位(pt)に
BOARD_W, BOARD_H = 95.0, 72.0
OX = (BOARD_W - (COLS - 1) * PITCH) / 2      # 基板の左端から1列目の穴まで
OY = (BOARD_H - (ROWS - 1) * PITCH) / 2

PAGE_W, PAGE_H = 210.0, 297.0                # A4 縦
MARGIN_X, MARGIN_Y = 22.0, 52.0              # 基板の左上を置く位置

JP = "japan"                                  # PyMuPDF 内蔵の日本語フォント

C_BOARD = (0.87, 0.90, 0.83)
C_HOLE = (0.62, 0.62, 0.62)
C_USED = (0.10, 0.10, 0.10)
C_BODY = (0.20, 0.35, 0.65)
C_TEXT = (0.05, 0.05, 0.05)
C_GRID = (0.55, 0.55, 0.55)
KIND_COLOR = {
    "ブリッジ": (0.80, 0.10, 0.10),
    "すずメッキ線": (0.10, 0.35, 0.75),
    "ジャンパ線": (0.85, 0.45, 0.00),
}
C_DONE = (0.58, 0.64, 0.72)      # 付け済みのすずメッキ線（灰色）


def xy(col, row, mirror=False):
    """穴の中心をページ座標(pt)で返す。mirror=True で左右反転（はんだ面）"""
    c = (COLS + 1 - col) if mirror else col
    x = MARGIN_X + OX + (c - 1) * PITCH
    y = MARGIN_Y + OY + (row - 1) * PITCH
    return x * MM, y * MM


def board_rect():
    return fitz.Rect(MARGIN_X * MM, MARGIN_Y * MM,
                     (MARGIN_X + BOARD_W) * MM, (MARGIN_Y + BOARD_H) * MM)


def draw_board(page, mirror, title, subtitle):
    # 表題
    page.insert_text((MARGIN_X * MM, 22 * MM), title,
                     fontname=JP, fontsize=14, color=C_TEXT)
    ty = 30
    for line in subtitle:
        page.insert_text((MARGIN_X * MM, ty * MM), line,
                         fontname=JP, fontsize=8.5, color=(0.25, 0.25, 0.25))
        ty += 4.5

    # 基板
    page.draw_rect(board_rect(), color=(0.45, 0.5, 0.42), fill=C_BOARD, width=0.8)

    # 取付穴 φ3.2（間隔 88.9 × 66mm）
    for dx in (-88.9 / 2, 88.9 / 2):
        for dy in (-66 / 2, 66 / 2):
            cx = (MARGIN_X + BOARD_W / 2 + dx) * MM
            cy = (MARGIN_Y + BOARD_H / 2 + dy) * MM
            page.draw_circle((cx, cy), 1.6 * MM, color=(0.4, 0.4, 0.4),
                             fill=(1, 1, 1), width=0.6)

    # 穴
    for c in range(1, COLS + 1):
        for r in range(1, ROWS + 1):
            x, y = xy(c, r, mirror)
            page.draw_circle((x, y), 0.55 * MM, color=C_HOLE, width=0.3)

    # 目盛り（列番号・行記号）
    for c in range(1, COLS + 1):
        x, _ = xy(c, 1, mirror)
        page.insert_text((x - 1.1 * MM, (MARGIN_Y + OY - 3.2) * MM), str(c),
                         fontname="helv", fontsize=5, color=C_GRID)
        page.insert_text((x - 1.1 * MM, (MARGIN_Y + OY + (ROWS - 1) * PITCH + 5.0) * MM), str(c),
                         fontname="helv", fontsize=5, color=C_GRID)
    for r in range(1, ROWS + 1):
        _, y = xy(1, r, mirror)
        lx = MARGIN_X + OX - 5.0 if not mirror else MARGIN_X + OX - 5.0
        page.insert_text((lx * MM, y + 1.0 * MM), rowname(r),
                         fontname="helv", fontsize=5.5, color=C_GRID)
        page.insert_text(((MARGIN_X + OX + (COLS - 1) * PITCH + 2.6) * MM, y + 1.0 * MM), rowname(r),
                         fontname="helv", fontsize=5.5, color=C_GRID)


def draw_parts(page, mirror, faded=False):
    """部品の外形とラベル"""
    col = (0.6, 0.68, 0.8) if faded else C_BODY
    for ref, (c1, r1, c2, r2) in BODY.items():
        x1, y1 = xy(c1, r1, mirror)
        x2, y2 = xy(c2, r2, mirror)
        if mirror:
            x1, x2 = min(x1, x2), max(x1, x2)
        rect = fitz.Rect(min(x1, x2) - 1.1 * MM, min(y1, y2) - 1.1 * MM,
                         max(x1, x2) + 1.1 * MM, max(y1, y2) + 1.1 * MM)
        page.draw_rect(rect, color=col, width=0.7,
                       fill=(0.93, 0.95, 0.99) if not faded else None,
                       fill_opacity=0.55 if not faded else 0)
        page.insert_text((rect.x0 + 0.4 * MM, rect.y0 - 0.6 * MM), ref,
                         fontname="helv", fontsize=5.2, color=col)

    # ピンの穴を塗る
    for ref, pins in PINPOS.items():
        for pin, (c, r) in pins.items():
            x, y = xy(c, r, mirror)
            page.draw_circle((x, y), 0.62 * MM, color=C_USED, fill=C_USED, width=0)


def draw_wires(page, mirror, w):
    """配線を wiring.py が決めた道（縦横だけ・穴から穴へ）どおりに描く。
    付け済みのすずメッキ線は灰色。分かれ目（同じ回路の線の途中から分ける点）は白い丸。"""
    for net, conns in w.items():
        for a, b, kind, _d in conns:
            x1, y1 = xy(a[2], a[3], mirror)
            x2, y2 = xy(b[2], b[3], mirror)
            color = C_DONE if wiring.is_done(a, b) else KIND_COLOR[kind]
            width = 1.7 if kind == "ブリッジ" else 1.0
            path = wiring.PATHS.get((tuple(a[2:]), tuple(b[2:])), [tuple(a[2:]), tuple(b[2:])])
            pts = [xy(c, r, mirror) for c, r in path]
            for (px, py), (qx, qy) in zip(pts, pts[1:]):
                page.draw_line((px, py), (qx, qy), color=color, width=width)
            for n, (x, y) in ((a, (x1, y1)), (b, (x2, y2))):
                if wiring.is_tap(n):
                    page.draw_circle((x, y), 0.7 * MM, color=color, fill=(1, 1, 1), width=0.8)
                else:
                    page.draw_circle((x, y), 0.5 * MM, color=color, fill=color, width=0)


def legend(page, y0, items):
    y = y0
    for text, color in items:
        page.draw_line((MARGIN_X * MM, y * MM), ((MARGIN_X + 8) * MM, y * MM),
                       color=color, width=1.4)
        page.insert_text(((MARGIN_X + 10) * MM, (y + 1.0) * MM), text,
                         fontname=JP, fontsize=8, color=C_TEXT)
        y += 5.0
    return y


def main():
    w = wiring.build()
    probs = wiring.verify(w)
    if probs:
        raise SystemExit("配線に問題があります:\n  " + "\n  ".join(probs))

    doc = fitz.open()

    # ---------- 1ページ目：部品面 ----------
    p = doc.new_page(width=PAGE_W * MM, height=PAGE_H * MM)
    draw_board(p, False, "実体配線図 ①  部品面（部品を挿す側）",
               ["ユニバーサル基板 秋月 103054 Bタイプ 95×72mm／2.54mmピッチ",
                "この面から部品を挿し、裏側ではんだ付けします。",
                "★ 印刷は「実際のサイズ（100%）」で。基板を紙に載せて穴を数えられます。"])
    draw_parts(p, False)
    y = MARGIN_Y + BOARD_H + 8
    p.insert_text((MARGIN_X * MM, y * MM), "部品の一覧（記号 ＝ 部品 ／ 挿す穴）",
                  fontname=JP, fontsize=9, color=C_TEXT)
    y += 5
    col2 = MARGIN_X + 88
    n = 0
    for ref in sorted(PINPOS, key=lambda r: (BODY[r][1], BODY[r][0])):
        pins = PINPOS[ref]
        hs = " ".join(hole(*pins[k]) for k in sorted(pins, key=lambda v: int(v)))
        if len(hs) > 44:
            hs = hs[:41] + "…"
        tx = MARGIN_X if n < 16 else col2
        ty = y + (n if n < 16 else n - 16) * 3.9
        p.insert_text((tx * MM, ty * MM), f"{ref:5s} {PARTS[ref]['value'][:13]:14s} {hs}",
                      fontname="cour", fontsize=5.6, color=C_TEXT)
        n += 1

    # ---------- 2ページ目：配線（部品面から透視）----------
    p = doc.new_page(width=PAGE_W * MM, height=PAGE_H * MM)
    draw_board(p, False, "実体配線図 ②  配線（部品面から透かして見た図）",
               ["配線は実際には裏（はんだ面）で行います。この図は向きを分かりやすくするため部品面から見ています。",
                "実際にはんだ付けするときは ③ はんだ面 を見てください。"])
    draw_parts(p, False, faded=True)
    draw_wires(p, False, w)
    c, total, length = wiring.summary(w)
    y = MARGIN_Y + BOARD_H + 10
    y = legend(p, y, [(f"はんだブリッジ（隣の穴を盛って繋ぐ） {c['ブリッジ']} 箇所", KIND_COLOR["ブリッジ"]),
                      (f"すずメッキ線（裸線をまっすぐ渡す） {c['すずメッキ線']} 本", KIND_COLOR["すずメッキ線"]),
                      (f"ジャンパ線（被覆付きの線を引き回す） {c['ジャンパ線']} 本", KIND_COLOR["ジャンパ線"]),
                      (f"付け済みのすずメッキ線 {len(wiring.DONE)} 本（そのまま残す）・白い丸＝分かれ目", C_DONE)])
    p.insert_text((MARGIN_X * MM, (y + 3) * MM),
                  f"合計 {total} 本 ／ のべ長さ 約 {length*PITCH:.0f} mm（耐熱ワイヤー 2m×7色 で足ります）",
                  fontname=JP, fontsize=8, color=C_TEXT)

    # ---------- 3ページ目：はんだ面 ----------
    p = doc.new_page(width=PAGE_W * MM, height=PAGE_H * MM)
    draw_board(p, True, "実体配線図 ③  はんだ面（基板を裏返した向き）",
               ["基板を左右にひっくり返した図です。実際にはんだ付けするときはこの図を見てください。",
                "列番号が右から左に増えていることに注意（部品面と左右が逆）。"])
    draw_parts(p, True, faded=True)
    draw_wires(p, True, w)
    y = MARGIN_Y + BOARD_H + 10
    legend(p, y, [("はんだブリッジ", KIND_COLOR["ブリッジ"]),
                  ("すずメッキ線", KIND_COLOR["すずメッキ線"]),
                  ("ジャンパ線", KIND_COLOR["ジャンパ線"]),
                  ("付け済みのすずメッキ線・白い丸＝分かれ目", C_DONE)])

    # ---------- 4ページ目〜：チェックリスト ----------
    rows = []
    for net in sorted(w, key=lambda n: (-len(w[n]), n)):
        for a, b, kind, d in w[net]:
            # 等幅フォントは日本語を出せないので、分かれ目は "(wire)" と書く
            rows.append((net, wiring.node_ascii(a), hole(a[2], a[3]),
                         wiring.node_ascii(b), hole(b[2], b[3]),
                         kind + ("（済）" if wiring.is_done(a, b) else ""), f"{d*PITCH:.0f}mm"))

    per_page = 56
    for pageno in range(0, len(rows), per_page):
        p = doc.new_page(width=PAGE_W * MM, height=PAGE_H * MM)
        p.insert_text((MARGIN_X * MM, 20 * MM),
                      f"配線チェックリスト（{pageno//per_page + 1}/{(len(rows)-1)//per_page + 1}）",
                      fontname=JP, fontsize=13, color=C_TEXT)
        p.insert_text((MARGIN_X * MM, 26 * MM),
                      "1本つなぐごとに □ を塗りつぶしてください。テスターの導通で確かめると確実です。",
                      fontname=JP, fontsize=8, color=(0.3, 0.3, 0.3))
        # 見出し（等幅フォントは日本語を出せないので、日本語フォントで別に置く）
        yy = 34
        for label, dx in (("ネット", 4), ("つなぐ穴（部品.ピン）", 32),
                          ("つなぎ方", 116), ("長さ", 150)):
            p.insert_text(((MARGIN_X + dx) * MM, yy * MM), label,
                          fontname=JP, fontsize=6.4, color=(0.35, 0.35, 0.35))
        p.draw_line((MARGIN_X * MM, (yy + 1.4) * MM),
                    ((MARGIN_X + 165) * MM, (yy + 1.4) * MM),
                    color=(0.6, 0.6, 0.6), width=0.4)
        yy += 5
        for net, an, ah, bn, bh, kind, dist in rows[pageno:pageno + per_page]:
            p.draw_rect(fitz.Rect(MARGIN_X * MM, (yy - 2.2) * MM,
                                  (MARGIN_X + 2.6) * MM, (yy + 0.4) * MM),
                        color=(0.3, 0.3, 0.3), width=0.5)
            p.insert_text(((MARGIN_X + 4) * MM, yy * MM),
                          f"{net:14s} {an:8s} {ah:6s} -> {bn:8s} {bh:6s}",
                          fontname="cour", fontsize=6.4, color=C_TEXT)
            p.insert_text(((MARGIN_X + 116) * MM, yy * MM), kind,
                          fontname=JP, fontsize=6.4,
                          color=C_DONE if kind.endswith("（済）") else KIND_COLOR[kind])
            p.insert_text(((MARGIN_X + 150) * MM, yy * MM), dist,
                          fontname="cour", fontsize=6.4, color=(0.35, 0.35, 0.35))
            yy += 4.3

    doc.set_metadata({"title": "コイン別音声貯金箱 制御基板 実体配線図",
                      "author": "netlist.py / layout.py から自動生成"})
    doc.save(OUT)
    doc.close()
    print("生成:", OUT)
    print(f"  {len(doc) if False else ''}ページ構成：部品面／配線／はんだ面／チェックリスト {(len(rows)-1)//per_page + 1} 枚")
    print(f"  配線 {total} 本、のべ約 {length*PITCH:.0f} mm")


if __name__ == "__main__":
    main()
