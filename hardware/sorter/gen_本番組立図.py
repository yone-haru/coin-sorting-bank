# -*- coding: utf-8 -*-
"""
本番の判別ユニット（判別ユニット_本番.scad）の組立図を 5 視点の PNG に書き出す。  2026-09-27

  python gen_本番組立図.py   → 組立図_本番/01〜05_*.png

判別ユニット_本番.scad は実物の座標（右手系）で作ってあるので、画像はそのまま実物の見え方になる
（旧 gen_組立図.py のような左右反転は要らない）。
"""
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SCAD = os.path.join(HERE, "判別ユニット_本番.scad")
OUT = os.path.join(HERE, "組立図_本番")
OPENSCAD = r"C:\openscad-2021.01\openscad.exe"
FONT = r"C:\Windows\Fonts\YuGothM.ttc"
FONT_B = r"C:\Windows\Fonts\YuGothB.ttc"

W, H = 1600, 1200
PANEL = 500
TITLE_H = 86

LEGEND = [
    (1, "蓋（クライアント製作）", (225, 225, 225), "図面は変えない（スリット・ボス 4 本）"),
    (2, "④ 吊り板＋じょうご", (242, 217, 77), "ボス 4 本に M4 で留める。腕 2 本でレールを吊る"),
    (3, "① 判別レール", (56, 56, 61), "窓 3 つ＋縁石。センサーの穴も全部この部品"),
    (4, "② 前板", (102, 191, 242), "溝の手前。硬貨が手前へ倒れない"),
    (5, "③ 受光ホルダー", (77, 153, 77), "穴センサーの受光素子を裏から差す"),
    (6, "穴センサー 2 本（入口）", (230, 30, 30), "5円・50円の穴を見る・硬貨が入った合図"),
    (7, "通過センサー P1〜P3", (40, 60, 230), "溝を縦に貫く光。どの窓まで来たか"),
    (8, "着地場所", (38, 140, 64), "関門から落ちた硬貨が立つ所（フェルトなし・床は平ら）"),
    (9, "基板室（今の設計）", (89, 204, 128), ""),
    (10, "スピーカー", (51, 51, 64), "位置だけ"),
    (11, "硬貨の道", (255, 0, 0), "スリット→関門→レール→窓から奥へ"),
    (12, "線の束（耐熱ワイヤー 7 本）", (51, 89, 230), "中継基板 → 吊り板のクリップ → 基板室の CN1"),
    (13, "中継基板", (26, 128, 51), "LED の抵抗 220Ω ×5・5V と GND を分ける"),
    (14, "センサーの線（配線の溝）", (242, 153, 26), "上下の溝に押し込む。硬貨の通り道は通らない"),
    (15, "電源ジャック・スピーカーの線", (217, 26, 26), "吊り板のクリップで留めて基板室へ"),
]
NOTE = [
    "・寸法は物理シミュレーション（約 3 万回）で決めた",
    "  判別率 99.3%（普通の跳ね・フェルトなし）。",
    "  着地でよく跳ねると 88%（そのときはフェルト）",
    "・下り 10°・壁の傾き 12°・窓の下に縁石 2.5",
    "・印刷は 4 部品（灰色 PETG・サポートなし）",
    "・蓋のリブの無い範囲 X130〜275 に収まる",
]

VIEWS = [
    ("01_全体_手前の左下から", "① 全体（手前の左下から見上げた図）",
     "190,-170,-70,100,0,-30,900", "p", {"tags_off": "[12,13,14,15]"}),
    ("02_手前から_硬貨の面", "② 手前から（硬貨がもたれる面）※基板室とスピーカーは外して表示",
     "232,-62,-75,92,0,0,470", "p", {"show_bay": 0, "show_spk": 0, "tag_d": 10, "tags_off": "[1,9,10,12,13,14,15]"}),
    ("03_奥から", "③ 奥から（窓から倒れた硬貨はこちら側へ落ちる）",
     "232,-62,-75,92,0,180,470", "p", {"show_bay": 0, "show_spk": 0, "tag_d": 10, "tag_side": -1,
                                        "tags_off": "[1,4,6,7,8,9,10,11,12,13,14,15]"}),
    ("04_上から_配置", "④ 上から見た配置（蓋は透明・左上が奥の左角＝蓋レイアウト図と同じ向き）",
     "175,-175,-60,0,0,0,1000", "o", {"tags_off": "[4,5,6,7,8,11,13,14]"}),
    ("06_配線", "⑥ 配線の通し方（基板室は外して表示。青い束は手前の基板室の奥の壁へ）",
     "200,-85,-45,98,0,-28,430", "p", {"show_bay": 0, "show_spk": 0, "show_box": 0, "show_path": 0,
                                       "tag_d": 9, "tags_off": "[1,2,4,5,6,7,8,9,10,11]"}),
    ("05_分解図", "⑤ 分解図（蓋・吊り板を上へ、前板を手前へ、受光ホルダーを奥へ離した）",
     "215,-110,-40,100,0,-30,760", "p", {"explode": 1, "show_bay": 0, "show_spk": 0, "tag_d": 13,
                                          "tags_off": "[9,10,11]"}),
]


def render(name, cam, proj, extra):
    rx, ry, rz = [float(v) for v in cam.split(",")[3:6]]
    defs = {"vr": f"[{rx},{ry},{rz}]", "part": '"assembly"'}
    defs.update(extra)
    tmp = os.path.join(tempfile.gettempdir(), f"asm_hon_{name.split('_')[0]}.png")
    cmd = [OPENSCAD, "-o", tmp, f"--imgsize={W},{H}", "--colorscheme=Tomorrow",
           f"--projection={proj}", f"--camera={cam}"]
    for k, v in defs.items():
        cmd += ["-D", f"{k}={v}"]
    cmd.append(SCAD)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not os.path.exists(tmp):
        sys.exit(f"OpenSCAD 失敗: {name}\n" + r.stderr)
    for l in (r.stdout + r.stderr).splitlines():
        if "ERROR" in l:
            print("  ", l)
    return Image.open(tmp).convert("RGB")


def compose(img, title):
    f_t = ImageFont.truetype(FONT_B, 32)
    f_n = ImageFont.truetype(FONT_B, 24)
    f_s = ImageFont.truetype(FONT, 17)
    f_num = ImageFont.truetype(FONT_B, 20)
    canvas = Image.new("RGB", (W + PANEL, H + TITLE_H), (255, 255, 255))
    canvas.paste(img, (0, TITLE_H))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, W + PANEL, TITLE_H], fill=(40, 60, 90))
    d.text((24, 24), title, font=f_t, fill=(255, 255, 255))
    x0 = W + 20
    y = TITLE_H + 20
    d.text((x0, y), "番号と部品", font=f_n, fill=(40, 60, 90))
    y += 44
    for n, label, col, sub in LEGEND:
        d.ellipse([x0, y, x0 + 32, y + 32], fill=(255, 255, 255), outline=(0, 0, 0), width=2)
        d.text((x0 + 16, y + 16), str(n), font=f_num if n < 10 else f_s, fill=(0, 0, 0), anchor="mm")
        d.rectangle([x0 + 42, y + 6, x0 + 62, y + 26], fill=col, outline=(90, 90, 90))
        d.text((x0 + 72, y + 1), label, font=f_n, fill=(20, 20, 20))
        if sub:
            d.text((x0 + 72, y + 31), sub, font=f_s, fill=(90, 90, 90))
        y += 60
    y += 4
    d.line([x0, y, W + PANEL - 20, y], fill=(200, 200, 200), width=2)
    y += 12
    for line in NOTE:
        d.text((x0, y), line, font=f_s, fill=(60, 60, 60))
        y += 26
    return canvas


def main():
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[1:]
    for name, title, cam, proj, extra in VIEWS:
        if only and not any(name.startswith(o) for o in only):
            continue
        print("描画中:", name)
        img = compose(render(name, cam, proj, extra), title)
        dst = os.path.join(OUT, name + ".png")
        tmp = dst + ".tmp.png"
        img.save(tmp)
        try:
            os.replace(tmp, dst)
        except OSError:                      # 画像ビューアで開いたままだと置き換えられない
            alt = os.path.join(OUT, name + "_新.png")
            os.replace(tmp, alt)
            print("  ※開いたままのため別名で保存:", alt)


if __name__ == "__main__":
    main()
