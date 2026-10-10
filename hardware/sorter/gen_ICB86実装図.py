# -*- coding: utf-8 -*-
"""ICB-86 の無切断実装図を生成する。銅箔面から見た位置。"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
OUT = HERE / "ICB-86_実装図.png"
FONT = r"C:\Windows\Fonts\YuGothM.ttc"
BOLD = r"C:\Windows\Fonts\YuGothB.ttc"


def main():
    im = Image.new("RGB", (1900, 1320), "#ffffff")
    d = ImageDraw.Draw(im)
    title = ImageFont.truetype(BOLD, 38)
    head = ImageFont.truetype(BOLD, 27)
    body = ImageFont.truetype(FONT, 23)
    small = ImageFont.truetype(FONT, 20)
    d.rectangle((0, 0, 1900, 75), fill="#17324d")
    d.text((32, 14), "ICB-86 無切断実装図　銅箔面から見る／ICB-86 の文字を上", font=title, fill="white")
    d.text((35, 94), "電源を抜いて作業。部品は反対側に置き、足・線を図の穴へ通して銅箔面ではんだ付け。", font=body, fill="#273545")

    # 実物の銅箔パターンのうち使う部分を拡大。3穴帯は段ごとに独立、縦2列はそれぞれ全段で接続。
    left = (620, 675, 730)
    plus, ground = 830, 910
    right = (1010, 1065, 1120)
    first_y, step = 180, 43
    labels = {5: "P3", 6: "P2", 7: "P1", 8: "穴A", 9: "穴B"}
    signals = {12: ("P3", "CN1-1 青"), 13: ("P2", "CN1-2 緑"),
               14: ("P1", "CN1-3 黄"), 15: ("穴A", "CN1-5 白"),
               16: ("穴B", "CN1-6 残りの色")}
    d.rounded_rectangle((585, 145, 1155, 1040), radius=16, fill="#edd6ac", outline="#8b683c", width=4)
    d.line((plus, first_y, plus, first_y + step * 19), fill="#d72d36", width=22)
    d.line((ground, first_y, ground, first_y + step * 19), fill="#263645", width=22)
    for row in range(1, 21):
        y = first_y + step * (row - 1)
        d.text((550, y), f"{row:02}", font=small, fill="#243342", anchor="mm")
        d.rounded_rectangle((left[0] - 19, y - 15, left[2] + 19, y + 15), radius=13,
                            fill="#f7b969", outline="#b17a40", width=2)
        d.rounded_rectangle((right[0] - 19, y - 15, right[2] + 19, y + 15), radius=13,
                            fill="#f7b969", outline="#b17a40", width=2)
        for x in (*left, plus, ground, *right):
            d.ellipse((x - 9, y - 9, x + 9, y + 9), fill="#3d3940", outline="#e7c58a", width=2)

    d.text((600, 1070), "左3穴：LED＋", font=body, fill="#aa2530")
    d.text((600, 1110), "中央左：+5V", font=body, fill="#d72d36")
    d.text((920, 1070), "中央右：GND", font=body, fill="#263645")
    d.text((920, 1110), "右3穴：受光C", font=body, fill="#2860a6")

    d.text((35, 155), "左3穴帯　抵抗 → LED＋", font=head, fill="#a92b32")
    d.text((1200, 155), "右3穴帯　受光C → CN1", font=head, fill="#2860a6")
    for row, name in labels.items():
        y = first_y + step * (row - 1)
        d.line((left[0], y, plus, y), fill="#cf3538", width=5)
        d.rectangle((748, y - 13, 811, y + 13), fill="white", outline="#8f262b", width=3)
        d.text((780, y), "220", font=small, fill="#8f262b", anchor="mm")
        d.text((35, y), f"{row}段  {name} LED＋  ←  220Ω", font=body, fill="#8f262b", anchor="lm")
    for row, (name, cn) in signals.items():
        y = first_y + step * (row - 1)
        d.line((right[0], y, right[2], y), fill="#2860a6", width=5)
        for x in right:
            d.ellipse((x - 9, y - 9, x + 9, y + 9), fill="#3d3940", outline="#e7c58a", width=2)
        d.text((1200, y), f"{row}段  {name} 受光C ＋ {cn}", font=body, fill="#214f87", anchor="lm")

    d.text((35, 670), "+5V 縦列：1段に CN1-7 赤。", font=body, fill="#aa2530")
    d.text((35, 708), "5～9段に抵抗を1本ずつ。", font=body, fill="#aa2530")
    d.text((35, 785), "GND 縦列：", font=body, fill="#263645")
    d.text((35, 823), "1～5段＝各LEDの－", font=body, fill="#263645")
    d.text((35, 861), "6～10段＝各受光のE", font=body, fill="#263645")
    d.text((35, 899), "11段＝CN1-8 黒", font=body, fill="#263645")
    d.text((35, 1215), "同じ横3穴は1組。上下の段同士は離れている。中央の縦2列は別々の線。CN1-4↔CN1-8 は制御基板側で接続済み。", font=body, fill="#273545")
    d.text((35, 1255), "この図は穴の割当図。線は硬貨の通路を避けて既存の配線溝とクリップへ通し、はんだ部に引張力をかけない。", font=body, fill="#273545")
    im.save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
