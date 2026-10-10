# -*- coding: utf-8 -*-
"""
自作判別部の組立図（合体版）を視点ごとに PNG で書き出す。  2026-09-27

  python gen_組立図.py      → 組立図/01〜05_*.png

・組立図_自作.scad を OpenSCAD で描き、凡例（番号と部品名）とタイトルを付ける
・蓋の座標（X 右・Y 手前・Z 上）は OpenSCAD の中では鏡に映った世界になるので、
  斜めや横からの図は左右反転して実物の見え方に戻す（番号の数字は scad 側で鏡文字にしてある）。
  上から見た配置図は「下から写して反転しない」と、蓋レイアウト図と同じ向き（左上が奥の左角）になる
"""
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
SCAD = os.path.join(HERE, "組立図_自作.scad")
OUT = os.path.join(HERE, "組立図")
OPENSCAD = r"C:\openscad-2021.01\openscad.exe"
FONT = r"C:\Windows\Fonts\YuGothM.ttc"
FONT_B = r"C:\Windows\Fonts\YuGothB.ttc"

W, H = 1600, 1200          # 描画の大きさ
PANEL = 470                # 右の凡例の幅
TITLE_H = 86               # 上のタイトルの高さ

# 番号・名前・色（scad の色に合わせる）・ひとこと
LEGEND = [
    (1, "蓋（クライアント製作）", (225, 225, 225), "今の寸法図のまま（変えない）"),
    (2, "じょうご・関門", (255, 153, 51), "スリット 40×6 → 1 枚ずつ（すき間 2.6）"),
    (3, "判別レール ★印刷済みの形", (64, 64, 64), "窓 3 つで 4 レーンに分ける"),
    (4, "穴センサー 2 本", (230, 30, 30), "5円・50円の穴を光が一瞬通る"),
    (5, "シュート＋レーンセンサー", (102, 204, 230), "窓から落ちた硬貨を受けて光で数える"),
    (6, "吊り具", (242, 217, 77), "今のボス 4 本にそのまま留める"),
    (7, "基板室（今の設計のまま）", (89, 204, 128), ""),
    (8, "スピーカー", (51, 51, 64), "位置だけ"),
    (9, "硬貨の道", (255, 0, 0), "スリット→関門→レール→窓"),
]

# 視点：(ファイル名, タイトル, カメラ, 投影, 反転, -D の追加)
VIEWS = [
    ("01_全体_斜め手前下から", "① 全体（手前の左下から見上げた図）",
     "190,130,-80,100,0,215,930", "p", True, {}),
    ("02_手前から_硬貨の面", "② 手前から（硬貨がもたれる面・窓・穴センサー）※基板室とスピーカーは外して表示",
     "235,60,-95,92,0,180,560", "p", True, {"show_bay": 0}),
    ("03_奥から_シュート", "③ 奥から（窓の裏のシュートとレーンセンサー）",
     "235,60,-105,92,0,0,560", "p", True, {"tags_off": "[1,3,4,7,8,9]"}),
    ("04_上から_配置", "④ 上から見た配置（蓋は透明・左上が奥の左角＝蓋レイアウト図と同じ向き）",
     "175,175,-60,180,0,0,1000", "o", False, {}),
    ("05_分解図", "⑤ 分解図（部品を離して並べたもの）",
     "190,120,-60,100,0,215,1150", "p", True, {"explode": 1}),
]


def render(name, cam, proj, flip, extra):
    rx, ry, rz = [float(v) for v in cam.split(",")[3:6]]
    defs = {"vr": f"[{rx},{ry},{rz}]", "txt_mirror": 1 if flip else 0}
    defs.update(extra)
    tmp = os.path.join(tempfile.gettempdir(), f"asm_{name.split('_')[0]}.png")
    cmd = [OPENSCAD, "-o", tmp, f"--imgsize={W},{H}", "--colorscheme=Tomorrow",
           f"--projection={proj}", f"--camera={cam}"]
    for k, v in defs.items():
        cmd += ["-D", f"{k}={v}"]
    cmd.append(SCAD)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    bad = [l for l in (r.stdout + r.stderr).splitlines() if "WARNING" in l or "ERROR" in l]
    if r.returncode != 0 or not os.path.exists(tmp):
        sys.exit(f"OpenSCAD 失敗: {name}\n" + r.stderr)
    for l in bad:
        print("  ", l)
    img = Image.open(tmp).convert("RGB")
    if flip:
        img = ImageOps.mirror(img)
    return img


def compose(img, title, note):
    f_t = ImageFont.truetype(FONT_B, 34)
    f_n = ImageFont.truetype(FONT_B, 26)
    f_s = ImageFont.truetype(FONT, 19)
    f_num = ImageFont.truetype(FONT_B, 22)
    canvas = Image.new("RGB", (W + PANEL, H + TITLE_H), (255, 255, 255))
    canvas.paste(img, (0, TITLE_H))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, W + PANEL, TITLE_H], fill=(40, 60, 90))
    d.text((24, 22), title, font=f_t, fill=(255, 255, 255))
    # 凡例
    x0 = W + 24
    y = TITLE_H + 28
    d.text((x0, y), "番号と部品", font=f_n, fill=(40, 60, 90))
    y += 52
    for n, label, col, sub in LEGEND:
        d.ellipse([x0, y, x0 + 36, y + 36], fill=(255, 255, 255), outline=(0, 0, 0), width=2)
        d.text((x0 + 18, y + 18), str(n), font=f_num, fill=(0, 0, 0), anchor="mm")
        d.rectangle([x0 + 48, y + 6, x0 + 72, y + 30], fill=col, outline=(90, 90, 90))
        d.text((x0 + 84, y + 2), label, font=f_n, fill=(20, 20, 20))
        if sub:
            d.text((x0 + 84, y + 38), sub, font=f_s, fill=(90, 90, 90))
        y += 84
    # 注記
    y += 6
    d.line([x0, y, W + PANEL - 24, y], fill=(200, 200, 200), width=2)
    y += 14
    for line in note:
        d.text((x0, y), line, font=f_s, fill=(60, 60, 60))
        y += 28
    return canvas


NOTE = [
    "・黒のレールだけが印刷済みの形。",
    "  橙・水色・黄は試験の結果で寸法を",
    "  決める前の案",
    "・下りは右へ 6°、壁は奥へ 20°",
    "・蓋のスリット・ボス・スピーカー穴・",
    "  電源穴は今の図面のまま",
    "・一番右の端は X=329（箱の内側 345）",
]


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, title, cam, proj, flip, extra in VIEWS:
        print("描画中:", name)
        img = render(name, cam, proj, flip, extra)
        out = os.path.join(OUT, name + ".png")
        compose(img, title, NOTE).save(out)
        print("  →", out)


if __name__ == "__main__":
    main()
