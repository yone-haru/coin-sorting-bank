# -*- coding: utf-8 -*-
"""すずメッキ線だけの配線図 HTML を生成する。  python gen_錫線html.py
出力: 錫線だけ_配線図.html（部品面から透かして見た図＋一覧表）"""
import os
import gen_手順html as G
import wiring as W

K = "すずメッキ線"


def table(rows, start, done):
    h = ['<table class="wires"><thead><tr><th></th><th>#</th><th>回路上の名前</th><th>from</th><th>to</th>'
         f'<th>道（出発 → 曲がる穴 → 到着）</th><th>長さ</th><th>{"ルーペで見る所" if done else "はんだの注意"}</th></tr></thead><tbody>']
    for i, (kind, net, a, b, n) in enumerate(rows, start):
        h.append(f'<tr{" class=done" if done else ""}><td><input type="checkbox"{" checked" if done else ""}></td><td>{i}</td><td>{G.esc(net)}</td>'
                 f'<td>{G.esc(G.pin_label(a))}</td><td>{G.esc(G.pin_label(b))}</td>'
                 f'<td class="mono">{G.esc(G.route_label(a, b))}</td><td>{n} 穴</td>'
                 f'<td class="cau">{G.caution_html(net, a, b)}</td></tr>')
    h.append('</tbody></table>')
    return "".join(h)


def route_example(rows):
    """「道」の読み方の例を、これから付ける線のうち曲がりが 1 回のものから作る"""
    for kind, net, a, b, n in rows:
        pts = G.route_label(a, b).split(" → ")
        if len(pts) == 3:
            return (f"例：{' → '.join(pts)} は、{pts[0]} から {pts[1]} までまっすぐ進み、"
                    f"{pts[1]} で直角に曲げて {pts[2]} まで")
    return "例：A → B → C は、A から B までまっすぐ進み、B で直角に曲げて C まで"


def mostly_bad(rows):
    """途中の穴の 7 割以上が「盛らない」（他の回路のすぐ隣）の線 → 「回路 出発→到着」の並び"""
    out = []
    for kind, net, a, b, n in rows:
        p = W.PATHS.get((tuple(a[2:]), tuple(b[2:])))
        if not p or len(p) < 5:
            continue
        mid = p[1:-1]
        bad = sum(1 for c in mid if G._near_other_net(c, net))
        if bad >= 0.7 * len(mid):
            out.append(f"{net} の {G.hole_label(a)} → {G.hole_label(b)}")
    return out


def main():
    rows = [r for r in G.wire_rows() if r[0] == K]
    new = [r for r in rows if not W.is_done(r[2], r[3])]
    done = [r for r in rows if W.is_done(r[2], r[3])]
    h = [f'<!doctype html><html lang="ja"><head><meta charset="utf-8">'
         f'<meta name="viewport" content="width=device-width,initial-scale=1">'
         f'<title>錫線だけの配線図</title><style>{G.CSS}</style></head><body><main>']
    h.append(f'<h1>すずメッキ線だけの配線図（{len(rows)} 本・うち付け済み {len(done)} 本）</h1>')
    h.append('<p class="note"><b>橙色の線がこれから付ける線</b>、灰色の線はもう付けてある線（そのまま残す）です。'
             '上の図は部品面から透かして見た向き、下の図は基板を裏返したはんだ面の向き（左右反転）です。<br>'
             '長い線も、すずメッキ線をはんだ面に這わせて渡します。図の道は縦横だけで、<b>他の回路の足の穴や線の上は通りません</b>。'
             '<b>曲がり角と、長い線の途中の空きランドにもはんだ付け</b>して固定すると、揺れても外れません。'
             'ただし表の「はんだの注意」で<b class="ng">盛らない</b>とある穴は、他の回路の足や線のすぐ隣です。'
             'そこには<b>はんだを付けず</b>、線を通すだけ（角なら曲げて押さえるだけ）にして、その前後の穴で留めます。'
             '<b class="few">端は少なめ</b>の穴は、はんだを少なめにしてルーペで隣とつながっていないか見ます。<br>'
             '<b>白い丸</b>は「分かれ目」です。すでに付けた同じ回路の線の上の穴に、新しい線の端をはんだ付けして分けます。<br>'
             '別の線と交差するものだけはジャンパ線（被覆線）にしてあります（別ページ）。</p>')
    h.append('<h2>部品面から透かして見た向き</h2>')
    h.append('<div class="wrap">' + G.board_svg(True, kinds=(K,)) + '</div>')
    h.append('<h2>半田面から見た向き（基板を裏返した図・左右反転）</h2>')
    h.append('<p class="note">はんだ付けするときに見える向きです。列番号は右が 1、左が 32。上下は同じで、XIAO の USB は上のままです。</p>')
    h.append('<div class="wrap">' + G.board_svg(True, kinds=(K,), mirror=True) + '</div>')
    h.append('<div class="card warn">裸線なので、隣の線や部品の足に触れるとショートします。'
             '付けるたびに、裏から見て隣とつながっていないか確認してください。<br>'
             f'途中のほとんどが「盛らない」の線（{G.esc("、".join(mostly_bad(new)))}）は、'
             'ジャンパ線の被覆を「盛らない」区間の長さぶん抜き取って筒にし、すずメッキ線に通してから付けると安心です'
             '（筒は曲がり角の手前で切って分ける）。</div>')
    h.append(f'<h2>これから付ける線（{len(new)} 本・付けたらチェック）</h2>')
    h.append(f'<p class="note">「道」の列は、線を曲げる穴の順番です（{G.esc(route_example(new))}）。'
             '「○○の線の途中」は分かれ目（白い丸）です。</p>')
    h.append(table(new, 1, False))
    h.append(f'<h2>付け済みの線（{len(done)} 本・そのまま）</h2>')
    h.append('<p class="note">付け直さなくてよいです。ただし右の列の穴は、隣の穴にこれから別の回路の線や足が来ます。'
             'もし途中にはんだを盛ってあったら、盛り上がりが隣に届いていないかルーペで見てください。</p>')
    h.append(table(done, len(new) + 1, True))
    h.append('</main></body></html>')
    out = os.path.join(G.HERE, "錫線だけ_配線図.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write("".join(h))
    print("wrote", out, len(rows), "new", len(new), "done", len(done))


if __name__ == "__main__":
    main()
