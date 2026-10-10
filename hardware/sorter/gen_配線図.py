# -*- coding: utf-8 -*-
"""
中継基板の配線図（PNG）を書き出す。  2026-09-27

  python gen_配線図.py   → 配線図_中継基板.png

基板室の CN1（端子台 8 極）⇄ 手持ちの耐熱ワイヤー 7 本 ⇄ 中継基板 ⇄ センサー 5 組（LED＋受光素子）
"""
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "配線図_中継基板.png")
F = r"C:\Windows\Fonts\YuGothM.ttc"
FB = r"C:\Windows\Fonts\YuGothB.ttc"

# CN1 の極・レーン名・GPIO・線の色・色の見本・つなぐ先
ROWS = [
    # 手持ちの「耐熱電子ワイヤー 7 色（AWG24）」を 1 色ずつ使う。予備（4 番）は線を引かない
    (1, "L0", "GPIO4",  "青",   ((30, 80, 220), None),   "P3 受光（W3 の後ろ）＝500円"),
    (2, "L1", "GPIO5",  "緑",   ((0, 150, 60), None),    "P2 受光（W2 の後ろ）"),
    (3, "L2", "GPIO3",  "黄",   ((230, 190, 0), None),   "P1 受光（W1 の後ろ）"),
    (4, "L3", "GPIO10", "（線なし）", ((200, 200, 200), None), "予備（CN1 で 8 番とつなぐ）"),
    (5, "L4", "GPIO20", "白",   ((235, 235, 235), (150, 150, 150)), "穴 A 受光（x=35・裏のホルダー）"),
    (6, "L5", "GPIO21", "残りの 1 色", ((150, 110, 200), None), "穴 B 受光（x=49・裏のホルダー）"),
    (7, "+5V", "—",     "赤",   ((210, 20, 20), None),   "LED 用 5V（中継基板で 5 本に分ける）"),
    (8, "GND", "—",     "黒",   ((20, 20, 20), None),    "GND（中継基板で 10 本に分ける）"),
]
SENS = [("P1", "x=98・床の下 LED ／ 上の受光"), ("P2", "x=134"), ("P3", "x=173.5"),
        ("穴 A", "x=35・橋の塔 LED ／ 裏の受光"), ("穴 B", "x=49")]


def wire(d, x0, y, x1, col, w=7):
    main, stripe = col
    d.line([x0, y, x1, y], fill=main, width=w)
    if stripe:
        for x in range(int(x0), int(x1), 18):
            d.line([x, y, min(x + 8, x1), y], fill=stripe, width=3)


def main():
    W, H = 2000, 1250
    im = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(im)
    ft = ImageFont.truetype(FB, 34)
    fh = ImageFont.truetype(FB, 24)
    f = ImageFont.truetype(F, 21)
    fs = ImageFont.truetype(F, 18)
    d.rectangle([0, 0, W, 70], fill=(40, 60, 90))
    d.text((24, 16), "中継基板の配線図（自作判別部）  CN1 ⇄ 耐熱ワイヤー 7 本の束 ⇄ 中継基板 ⇄ センサー 5 組", font=ft, fill=(255, 255, 255))

    # 左：CN1 と線の束
    x_cn, x_lan1 = 60, 430
    d.text((x_cn, 95), "基板室の CN1（端子台 8 極）", font=fh, fill=(20, 20, 20))
    d.text((x_cn + 330, 95), "手持ちの耐熱ワイヤー（7 色・40cm）", font=fh, fill=(20, 20, 20))
    y0 = 185
    ys = {}
    for i, (pin, lane, gpio, cname, col, dest) in enumerate(ROWS):
        y = y0 + i * 62
        ys[pin] = y
        d.rectangle([x_cn, y - 22, x_cn + 60, y + 22], outline=(0, 0, 0), width=2)
        d.text((x_cn + 30, y), str(pin), font=fh, fill=(0, 0, 0), anchor="mm")
        d.text((x_cn + 75, y - 12), f"{lane}  {gpio}", font=f, fill=(20, 20, 20))
        if pin != 4:
            wire(d, x_cn + 250, y, x_lan1 + 320, col)
        d.text((x_cn + 260, y - 36), cname, font=fs, fill=(80, 80, 80))
    # 予備レーン
    for yy in (ys[4], ys[8]):
        d.line([x_cn - 20, yy, x_cn, yy], fill=(200, 0, 0), width=3)
    d.line([x_cn - 20, ys[4], x_cn - 20, ys[8]], fill=(200, 0, 0), width=3)
    d.text((x_cn - 20, ys[8] + 32), "↑ 4 番と 8 番を短い線でつなぐ（予備の入力を GND に）", font=fs, fill=(200, 0, 0))

    # 中：中継基板
    bx0, bx1 = 800, 1250
    d.rectangle([bx0, 120, bx1, 1060], outline=(20, 110, 40), width=4)
    d.text((bx0 + 150, 1030), "中継基板（ICB-86 を切らずに使う）", font=fs, fill=(20, 110, 40))
    # 5V バス と GND バス
    y5 = ys[7]
    yg = ys[8]
    d.line([bx0 + 40, y5, bx0 + 40, 1020], fill=(200, 0, 0), width=5)
    d.text((bx0 + 14, 1025), "5V", font=f, fill=(200, 0, 0))
    d.line([bx0 + 110, y0 - 20, bx0 + 110, 1020], fill=(0, 0, 0), width=5)
    d.text((bx0 + 90, 1025), "GND", font=f, fill=(0, 0, 0))
    wire(d, x_lan1 + 320, y5, bx0 + 40, ROWS[6][4])
    wire(d, x_lan1 + 320, yg, bx0 + 110, ROWS[7][4])
    # 信号線はそのまま右へ
    sig = {"P3": 1, "P2": 2, "P1": 3, "穴 A": 5, "穴 B": 6}
    # 右：センサー 5 組
    x_s = 1330
    d.text((x_s, 95), "センサー（レールに差す）", font=fh, fill=(20, 20, 20))
    order = ["P1", "P2", "P3", "穴 A", "穴 B"]
    loc = dict(SENS)
    for k, name in enumerate(order):
        yb = 640 + k * 80
        # LED：5V → 220Ω → アノード、カソード → GND
        d.line([bx0 + 40, yb, bx0 + 170, yb], fill=(200, 0, 0), width=3)
        d.rectangle([bx0 + 170, yb - 12, bx0 + 250, yb + 12], outline=(0, 0, 0), width=2)
        d.text((bx0 + 210, yb), "220Ω", font=fs, fill=(0, 0, 0), anchor="mm")
        d.line([bx0 + 250, yb, x_s + 10, yb], fill=(200, 0, 0), width=3)
        d.line([bx0 + 110, yb + 22, x_s + 10, yb + 22], fill=(0, 0, 0), width=3)
        d.text((x_s + 20, yb - 14), f"{name} LED：＋（長い足）", font=f, fill=(200, 0, 0))
        d.text((x_s + 20, yb + 12), f"{name} LED：−", font=f, fill=(0, 0, 0))
        # 受光素子：信号 → C、E → GND
        ys_sig = ys[sig[name]]
        wire(d, x_lan1 + 320, ys_sig, x_s + 10, ROWS[sig[name] - 1][4], w=5)
        d.text((x_s + 20, ys_sig - 14), f"{name} 受光：C（信号）", font=f, fill=(20, 20, 20))
        d.line([bx0 + 110, ys_sig + 22, x_s + 10, ys_sig + 22], fill=(0, 0, 0), width=2)
        d.text((x_s + 20, ys_sig + 10), f"{name} 受光：E", font=fs, fill=(0, 0, 0))
        d.text((x_s + 360, yb - 14), loc[name], font=fs, fill=(90, 90, 90))

    notes = [
        "・LED の＋は長い足。受光素子の C と E を逆に付けると、その光はいつも「遮られている」と出る → sensortest で確かめ、おかしければ入れ替える",
        "・7 本はねじって 1 本の束にし、10cm おきに手持ちの熱収縮チューブ φ6 を 1cm に切って通して縮める（結束バンドの代わり）",
        "・束は ICB-86 の空いている穴（17〜24 段）2 つに余りの線を通してねじって留める（引っ張り止め）。レールの溝と吊り板の印刷クリップに押し込む",
        "・予備の CN1-4（GPIO10）は線を引かず、CN1 で 8 番（GND）とつなぐ（つながないと「いつも遮られている」と読まれる）",
    ]
    for i, n in enumerate(notes):
        d.text((60, 1090 + i * 36), n, font=f, fill=(40, 40, 40))
    tmp = OUT + ".tmp.png"
    im.save(tmp)
    try:
        os.replace(tmp, OUT)
        print(OUT)
    except OSError:                         # 画像ビューアで開いたままだと置き換えられない
        alt = OUT.replace(".png", "_新.png")
        os.replace(tmp, alt)
        print("開いたままのため別名で保存:", alt)


if __name__ == "__main__":
    main()
