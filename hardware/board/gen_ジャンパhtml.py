# -*- coding: utf-8 -*-
"""ジャンパ線だけの配線図 HTML を生成する。  python gen_ジャンパhtml.py
出力: ジャンパだけ_配線図.html（番号つきの図 ×2＋短い順の一覧表＋つけ方）"""
import os
import gen_手順html as G

K = "ジャンパ線"
GROUPS = [("短いもの（〜6穴）", 0, 6), ("中くらい（7〜15穴）", 7, 15), ("長いもの（16穴〜）", 16, 999)]
COL = {"GND": "#111827", "+12V": "#dc2626", "+5V": "#ea580c", "XIAO_5V": "#ea580c", "VIN": "#dc2626",
       "+3V3": "#db2777", "DF_VCC": "#ea580c", "UART_TX": "#16a34a", "UART_RX": "#16a34a",
       "DAC_L": "#7c3aed", "AUDIO": "#7c3aed", "LED_K": "#0891b2"}
SUGGEST = {"GND": "黒", "+12V": "赤", "VIN": "赤", "+5V": "オレンジ", "XIAO_5V": "オレンジ", "DF_VCC": "オレンジ",
           "+3V3": "ピンク", "UART_TX": "緑", "UART_RX": "緑", "DAC_L": "紫", "AUDIO": "紫", "LED_K": "水色"}
EXTRA = ((8, 2), (16, 2), "★")   # CN1-4 ↔ CN1-8（被覆線・57本には入らない）


def star_caution():
    """★の両端（CN1-4＝GPIO10 の線、CN1-8＝GND）で、隣が別の回路の穴"""
    owner = G.W.owner_map()
    ends = [G.L.hole(*c) for c in EXTRA[:2] if G._near_other_net(c, owner[c])]
    return f'<span class="few">端は少なめ：{"・".join(ends)}</span>' if ends else '<span class="safe">—</span>'


def main():
    rows = [r for r in G.wire_rows() if r[0] == K]
    # 長さは図に描いた道（他の足を避けて回る）の穴の数に置きかえ、短い順に並べ直す
    def plen_of(r):
        path = G.W.PATHS.get((tuple(r[2][2:]), tuple(r[3][2:])))
        return len(path) - 1 if path else r[4]
    rows = sorted(((k, net, a, b, plen_of((k, net, a, b, n))) for k, net, a, b, n in rows), key=lambda r: (r[4], r[1]))
    for _, net, *_ in rows:
        G.NET_COLOR[net] = COL.get(net, "#2563eb") if not net.startswith("LANE") else "#2563eb"
    labels = {(a[2], a[3], b[2], b[3]): i for i, (_, net, a, b, n) in enumerate(rows, 1)}
    h = [f'<!doctype html><html lang="ja"><head><meta charset="utf-8">'
         f'<meta name="viewport" content="width=device-width,initial-scale=1">'
         f'<title>ジャンパ線だけの配線図</title><style>{G.CSS}'
         '.sw{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:middle;margin-right:4px}'
         '</style></head><body><main>']
    h.append(f'<h1>ジャンパ線だけの配線図（{len(rows)} 本＋★1 本）</h1>')
    h.append('<p class="note">丸の中の数字が、下の一覧の番号です。<b>番号の小さい（短い）ものから</b>付けていきます。'
             '線の色は回路の種類（黒＝GND、赤＝12V、橙＝5V、桃＝3.3V、緑＝UART、紫＝音、水色＝LED、青＝レーン信号）。'
             '<b>★</b>は被覆線で CN1-4（8-B）と CN1-8（16-B）をつなぐ 1 本で、最後に付けます。</p>')
    h.append('<h2>部品面から透かして見た向き</h2>')
    h.append('<div class="wrap">' + G.board_svg(True, kinds=(K,), labels=labels, extras=[EXTRA]) + '</div>')
    h.append('<h2>半田面から見た向き（基板を裏返した図・左右反転）</h2>')
    h.append('<p class="note">はんだ付けするときに見える向きです。列番号は右が 1、左が 32。上下は同じで、XIAO の USB は上のままです。</p>')
    h.append('<div class="wrap">' + G.board_svg(True, kinds=(K,), mirror=True, labels=labels, extras=[EXTRA]) + '</div>')

    h.append('<h2>つけ方</h2><div class="card"><ol>'
             '<li><b>線</b>：被覆つきの細い線（AWG24 前後）。色は何でもよいが、上の色分けにすると間違えにくい。</li>'
             '<li><b>長さ</b>：一覧の「線の長さ」の列のとおりに切る（図の道の穴の数×2.54mm＋余裕 1cm）。</li>'
             '<li><b>皮むき</b>：両端を 3mm ほど。先に予備はんだ（すずを薄くのせる）しておくと付けやすい。</li>'
             '<li><b>差す穴</b>：from と to の<b>足が出ている穴</b>（部品の足の穴）に、<b>はんだ面から</b>線の先を当てる。'
             '穴に通さず、足のランドに寝かせてはんだ付けしてよい。</li>'
             '<li><b>はんだ付け</b>：片方を付けたら、線を基板に沿わせて、もう片方を付ける。ピンと張らず、少したるませる。</li>'
             '<li><b>ほかの足に触れさせない</b>：線の被覆は他のランドに触れても平気だが、<b>むき出しの芯線の先</b>が隣の穴・ランドに触れるとショートする。'
             '特に <b>17-T（+12V）と 17-U（音）</b>、<b>18-V（GND）と 19-V（3.3V）</b>は隣り合っている。'
             '一覧の「注意」に<b>端は少なめ</b>とある穴は、隣が別の回路。はんだを足しすぎない。</li>'
             '<li><b>1本付けるたびに</b>、一覧のチェックを入れる。針金が長いときは、基板の縁や部品の間を通して交差させてよい（被覆があるので）。</li>'
             '<li><b>全部付けたら</b>、ルーペで隣どうしのブリッジを見て、テスターで確認（導通・ショートの有無）。</li>'
             '</ol></div>')

    h.append('<h2>一覧（短い順・付けたらチェック）</h2>')
    for title, lo, hi in GROUPS:
        sub = [(i, r) for i, r in enumerate(rows, 1) if lo <= r[4] <= hi]
        if not sub:
            continue
        h.append(f'<h3>{title}（{len(sub)} 本）</h3>')
        h.append('<table class="wires"><thead><tr><th></th><th>#</th><th>回路</th><th>色の目安</th><th>from</th><th>to</th><th>穴</th><th>線の長さ</th><th>注意</th></tr></thead><tbody>')
        for i, (kind, net, a, b, n) in sub:
            c = G.NET_COLOR[net]
            plen = n
            mm = round(plen * 2.54 + 10)
            sg = SUGGEST.get(net, "青系")
            h.append(f'<tr><td><input type="checkbox"></td><td><b>{i}</b></td><td><span class="sw" style="background:{c}"></span>{G.esc(net)}</td>'
                     f'<td>{sg}</td><td>{G.esc(G.pin_label(a))}<br><span class="mono">{G.esc(G.hole_label(a))}</span></td>'
                     f'<td>{G.esc(G.pin_label(b))}<br><span class="mono">{G.esc(G.hole_label(b))}</span></td>'
                     f'<td>{plen}</td><td>約 {mm} mm</td><td class="cau">{G.caution_html(net, a, b, kind)}</td></tr>')
        h.append('</tbody></table>')
    h.append('<h3>最後の 1 本（★）</h3><table class="wires"><tbody><tr><td><input type="checkbox"></td><td><b>★</b></td>'
             '<td>CN1-4 ↔ CN1-8</td><td>被覆線</td><td>CN1-4<br><span class="mono">8-B</span></td><td>CN1-8<br><span class="mono">16-B</span></td>'
             f'<td>8</td><td>約 30 mm</td><td class="cau">{star_caution()}</td></tr></tbody></table>'
             '<p class="note">レーン3（GPIO10）を GND に落とす線。間の CN1-5〜7 の穴の上を通るので、必ず被覆つきで。</p>')
    h.append('</main></body></html>')
    out = os.path.join(G.HERE, "ジャンパだけ_配線図.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write("".join(h))
    print("wrote", out, len(rows))


if __name__ == "__main__":
    main()
