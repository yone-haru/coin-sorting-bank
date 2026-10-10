# -*- coding: utf-8 -*-
"""制御基板の製作手順 HTML を生成する。  python gen_手順html.py
layout.py / wiring.py / netlist.py から作るので、基板の設計を変えたら再実行すれば追従する。
出力: 製作手順_制御基板.html（SVG 図入り・1 ファイルで完結）"""
import html, os
import layout as L
import wiring as W

HERE = os.path.dirname(os.path.abspath(__file__))
PITCH = 24           # 図の 1 穴ぶん (px)
MX, MY = 34, 30      # 図の余白
COLS, ROWS = L.COLS, L.ROWS

PART_COLOR = {
    "CN1": "#fde68a", "TB1": "#fde68a", "TB2": "#fde68a", "TB3": "#fde68a",
    "U2": "#bfdbfe", "U3": "#c7d2fe", "U1": "#fecaca",
}
KIND_COLOR = {"ブリッジ": "#16a34a", "すずメッキ線": "#d97706", "ジャンパ線": "#2563eb"}
DONE_COLOR = "#94a3b8"   # はんだ付け済みのすずメッキ線（wiring.DONE の 18 本）


PCOLS, PROWS = 36, 27   # 実物の基板（秋月 g103054）の穴の数。写真で数えた（2026-10-02）
OFF = 2                 # 設計の 1-A は実物の左から 3 つ目・上から 3 つ目
CORNER_MOUNT = {(0, 0), (PCOLS - 1, 0), (0, PROWS - 1), (PCOLS - 1, PROWS - 1)}
CORNER_NOHOLE = set()
for _cx, _sx in ((0, 1), (PCOLS - 1, -1)):
    for _cy, _sy in ((0, 1), (PROWS - 1, -1)):
        CORNER_NOHOLE |= {(_cx + _sx, _cy), (_cx, _cy + _sy)}


MIRROR = False   # True＝半田面（基板を裏返した）向き。左右だけ反転する


def xy(col, row):
    c = col - 1 + OFF
    if MIRROR:
        c = PCOLS - 1 - c
    return MX + c * PITCH, MY + (row - 1 + OFF) * PITCH


def esc(s):
    return html.escape(str(s))


POLAR = {
    "D1": {"1": "A", "2": "K帯"}, "D2": {"1": "A", "2": "K帯"},
    "C1": {"1": "＋", "2": "－"}, "C2": {"1": "＋", "2": "－"}, "C3": {"1": "＋", "2": "－"},
    "LED1": {"1": "A長", "2": "K"},
    "U1": {"1": "IN", "2": "GND", "3": "OUT"},
    "VR1": {"1": "1", "2": "W", "3": "3"},
}


NET_COLOR = {}   # ネット名 → 色（番号つきの図で使う。呼び出し側が埋める）


def board_svg(show_wires, kinds=None, mirror=False, labels=None, extras=None):
    global MIRROR
    MIRROR = mirror
    try:
        return _board_svg(show_wires, kinds, labels, extras)
    finally:
        MIRROR = False


def _board_svg(show_wires, kinds=None, labels=None, extras=None):
    # 実物の基板：36 列 × 27 行。四隅は取り付け穴で、その隣 2 穴ずつ（角の三角）は穴が無い。
    # 設計の 1-A は、実物の左から 3 つ目・上から 3 つ目（OFF=2）に置く。
    w = MX * 2 + (PCOLS - 1) * PITCH
    h = MY * 2 + (PROWS - 1) * PITCH
    o = [f'<svg viewBox="0 0 {w} {h}" class="board" role="img">']
    o.append(f'<rect x="4" y="4" width="{w-8}" height="{h-8}" rx="8" fill="#a3b18a" opacity=".35" stroke="#14532d" stroke-width="2"/>')
    # 設計の範囲の枠
    ax1, ay1 = xy(1, 1)
    ax2, ay2 = xy(COLS, ROWS)
    ax1, ax2 = min(ax1, ax2), max(ax1, ax2)
    lx = ax2 + 18 if MIRROR else ax1 - 18
    o.append(f'<rect x="{ax1-12}" y="{ay1-12}" width="{ax2-ax1+24}" height="{ay2-ay1+24}" rx="6" fill="#fff" fill-opacity=".55" stroke="#dc2626" stroke-dasharray="6 4"/>')
    for pr in range(PROWS):
        for pc in range(PCOLS):
            px, py = MX + ((PCOLS - 1 - pc) if MIRROR else pc) * PITCH, MY + pr * PITCH
            if (pc, pr) in CORNER_MOUNT:
                o.append(f'<circle cx="{px}" cy="{py}" r="8" fill="#fff" stroke="#475569" stroke-width="2"/><text x="{px}" y="{py+3}" class="ax">取付</text>')
            elif (pc, pr) in CORNER_NOHOLE:
                o.append(f'<text x="{px}" y="{py+3}" class="ax" fill="#b91c1c">×</text>')
            else:
                o.append(f'<circle cx="{px}" cy="{py}" r="1.6" class="hole"/>')
    for c in range(1, COLS + 1):
        x, _ = xy(c, 1)
        o.append(f'<text x="{x}" y="{ay1-16}" class="ax">{c}</text>')
    for r in range(1, ROWS + 1):
        _, y = xy(1, r)
        o.append(f'<text x="{lx}" y="{y+4}" class="ax">{L.rowname(r)}</text>')
    # 部品の外形
    for ref, (c1, r1, c2, r2) in L.BODY.items():
        x1, y1 = xy(c1, r1)
        x2, y2 = xy(c2, r2)
        x1, x2 = min(x1, x2), max(x1, x2)
        fill = PART_COLOR.get(ref, "#e5e7eb")
        o.append(f'<rect x="{x1-9}" y="{y1-9}" width="{x2-x1+18}" height="{y2-y1+18}" rx="5" fill="{fill}" fill-opacity=".75" stroke="#475569"/>')
        if ref in ("U2", "U3", "CN1", "U1", "TB1", "TB2", "TB3"):
            o.append(f'<text x="{(x1+x2)/2}" y="{(y1+y2)/2+4}" class="pl">{ref}</text>')
        elif not show_wires or True:
            o.append(f'<text x="{(x1+x2)/2}" y="{y1-12 if r1==r2 else (y1+y2)/2}" class="pl s">{ref}</text>')
    # 足
    for ref, pins in L.PINPOS.items():
        for pn, (c, r) in pins.items():
            x, y = xy(c, r)
            o.append(f'<circle cx="{x}" cy="{y}" r="4.2" class="pin"><title>{ref}-{pn}</title></circle>')
    # 向きのある部品の印（赤）
    for ref, labels in POLAR.items():
        for pn, txt in labels.items():
            c, r = L.PINPOS[ref][pn]
            x, y = xy(c, r)
            o.append(f'<text x="{x}" y="{y+17}" class="pol">{txt}</text>')
    for ref, pn, txt in ((("U2", "1", "▲USB側（1番）")), ("U3", "1", "▲1番(VCC)")):
        c, r = L.PINPOS[ref][pn]
        x, y = xy(c, r)
        o.append(f'<text x="{x+30}" y="{y-12}" class="pol">{txt}</text>')
    for ref in ("D1", "D2"):  # 帯（カソード）側に太線
        c, r = L.PINPOS[ref]["2"]
        x, y = xy(c, r)
        o.append(f'<rect x="{x-8}" y="{y-8}" width="4" height="16" fill="#111"/>')
    if show_wires:
        for net, ws in W.build().items():
            for (a, b, kind, n) in ws:
                if kinds and kind not in kinds:
                    continue
                x1, y1 = xy(a[2], a[3])
                x2, y2 = xy(b[2], b[3])
                dash = ' stroke-dasharray="5 3"' if kind == "ジャンパ線" else ""
                col = KIND_COLOR[kind]
                key = (a[2], a[3], b[2], b[3])
                done = W.is_done(a, b)
                if labels is not None:
                    col = NET_COLOR.get(net, "#475569")
                elif done:
                    col = DONE_COLOR
                path = W.PATHS.get((tuple(a[2:]), tuple(b[2:])), [tuple(a[2:]), tuple(b[2:])])
                pts = [xy(c, r) for c, r in path]
                tip = f'{esc(net)}: {esc(pin_label(a))} → {esc(pin_label(b))} ({kind}{"・付け済み" if done else ""})'
                o.append(f'<polyline points="{" ".join(f"{px},{py}" for px, py in pts)}" fill="none" stroke-linejoin="round" stroke="{col}" stroke-width="2.4" opacity=".85"{dash}><title>{tip}</title></polyline>')
                # 線の途中から分かれる点（分かれ目）は白丸で示す
                for n in (a, b):
                    if W.is_tap(n) and labels is None:
                        tx, ty = xy(n[2], n[3])
                        o.append(f'<circle cx="{tx}" cy="{ty}" r="4" fill="#fff" stroke="{col}" stroke-width="2"><title>分かれ目（{esc(net)}の線の途中・はんだ付け）</title></circle>')
                if labels is not None and key in labels:
                    mx, my = pts[len(pts) // 2]
                    o.append(f'<circle cx="{mx}" cy="{my}" r="8.5" fill="#fff" stroke="{col}" stroke-width="1.5"/><text x="{mx}" y="{my+3.5}" class="ax" fill="#111" font-weight="700">{labels[key]}</text>')
        for (p1, p2, lab) in (extras or []):
            x1, y1 = xy(*p1)
            x2, y2 = xy(*p2)
            o.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#111" stroke-width="2.4" stroke-dasharray="2 3"/>')
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - 14
            o.append(f'<circle cx="{mx}" cy="{my}" r="9" fill="#fff" stroke="#111"/><text x="{mx}" y="{my+3.5}" class="ax" fill="#111" font-weight="700">{lab}</text>')
    o.append("</svg>")
    return "".join(o)


def pin_label(p):
    return W.node_label(p)


def hole_label(p):
    return L.hole(p[2], p[3])


def route_label(a, b):
    """線の道を「出発 → 曲がり角 … → 到着」の穴で書く（すずメッキ線を曲げる位置）"""
    p = W.PATHS.get((tuple(a[2:]), tuple(b[2:])))
    if not p:
        return f"{hole_label(a)} → {hole_label(b)}"
    pts = [p[0]]
    for i in range(1, len(p) - 1):
        if (p[i][0] - p[i-1][0], p[i][1] - p[i-1][1]) != (p[i+1][0] - p[i][0], p[i+1][1] - p[i][1]):
            pts.append(p[i])
    pts.append(p[-1])
    return " → ".join(L.hole(*c) for c in pts)


_TIN_OWNER = {}


def _tin_owner():
    """穴 → そこを通る裸線（すずメッキ線）の回路名。1 回だけ作って使い回す"""
    if not _TIN_OWNER:
        for net, ws in W.build().items():
            for a, b, kind, n in ws:
                if kind == "ジャンパ線":
                    continue
                for c in W.PATHS.get((tuple(a[2:]), tuple(b[2:])), ()):
                    _TIN_OWNER[c] = net
    return _TIN_OWNER


def _near_other_net(c, net):
    """穴 c の上下左右に、他の回路の足の穴か裸線があるか（はんだを盛るとつながる恐れ）"""
    owner, tin = W.owner_map(), _tin_owner()
    for n in W._neighbors(c):
        o = owner.get(n)
        if o is not None and o != net:
            return True
        if o is None and tin.get(n, net) != net:
            return True
    return False


def caution(net, a, b):
    """すずメッキ線の注意 → (はんだを盛らない穴, はんだ少なめにする端)。
    盛らない穴は、道の途中で他の回路の隣にある穴（続いている所は「A〜B」とまとめる）。
    端は足・分かれ目なので必ずはんだ付けするが、隣が他の回路なら少なめにしてルーペで見る"""
    p = W.PATHS.get((tuple(a[2:]), tuple(b[2:])))
    if not p:
        return "", ""
    bad = [i for i in range(1, len(p) - 1) if _near_other_net(p[i], net)]
    runs = []
    for i in bad:
        if runs and runs[-1][1] == i - 1:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    txt = []
    for s, e in runs:
        if s == e:
            txt.append(L.hole(*p[s]))
        elif e == s + 1:
            txt.append(f"{L.hole(*p[s])}・{L.hole(*p[e])}")
        else:
            txt.append(f"{L.hole(*p[s])}〜{L.hole(*p[e])}")
    return "、".join(txt), ends_near(net, a, b)


def ends_near(net, a, b):
    """線の両端の穴のうち、隣が他の回路のもの（はんだ少なめ・ルーペ確認）"""
    return "・".join(L.hole(*c) for c in (tuple(a[2:]), tuple(b[2:])) if _near_other_net(c, net))


def caution_html(net, a, b, kind="すずメッキ線"):
    if kind == "ジャンパ線":
        ends = ends_near(net, a, b)
        return f'<span class="few">端は少なめ：{esc(ends)}</span>' if ends else '<span class="safe">—</span>'
    bad, ends = caution(net, a, b)
    out = []
    if bad:
        out.append(f'<span class="ng">盛らない：{esc(bad)}</span>')
    if ends:
        out.append(f'<span class="few">端は少なめ：{esc(ends)}</span>')
    return "<br>".join(out) if out else '<span class="safe">どこで留めてもよい</span>'


def wire_rows():
    rows = []
    for net, ws in W.build().items():
        for (a, b, kind, n) in ws:
            rows.append((kind, net, a, b, n))
    order = {"ブリッジ": 0, "すずメッキ線": 1, "ジャンパ線": 2}
    rows.sort(key=lambda r: (order[r[0]], r[4], r[1]))
    return rows


def wire_table():
    out = []
    rows = wire_rows()
    cur = None
    i = 0
    for kind, net, a, b, n in rows:
        if kind != cur:
            if cur is not None:
                out.append("</tbody></table>")
            cur = kind
            msg = {"すずメッキ線": "すずメッキ線を半田面に這わせて渡す。「道」の列の穴で曲げ（縦横だけ）、角と途中をはんだで固定。"
                                    "ただし「注意」の列の<b>盛らない</b>穴は他の回路のすぐ隣なので、はんだを付けずに線を通すだけにする（角なら曲げるだけ）。"
                                    "<b>端は少なめ</b>の穴は、はんだを少なめにしてルーペで隣とつながっていないか見る。"
                                    "「○○の線の途中」は、すでに付けた同じ回路の線の上の穴にはんだ付けして分ける。灰色の行は付け済み。",
                   "ジャンパ線": "裸線では道が見つからない（他の線をまたぐ等）。被覆線で渡す。長さは穴の数＋余裕1cm。",
                   "ブリッジ": "隣り合う穴。半田を盛ってつなぐ。"}[kind]
            cnt = sum(1 for r in rows if r[0] == kind)
            out.append(f'<h3><span class="dot" style="background:{KIND_COLOR[kind]}"></span>{kind}（{cnt} 本）</h3><p class="note">{msg}</p>')
            out.append('<table class="wires"><thead><tr><th></th><th>#</th><th>回路上の名前</th><th>from（部品・足）</th><th>to（部品・足）</th><th>道（曲がる穴）</th><th>長さ</th><th>注意</th></tr></thead><tbody>')
        i += 1
        done = W.is_done(a, b)
        out.append(
            f'<tr{" class=done" if done else ""}><td><input type="checkbox" data-w="{i}"{" checked" if done else ""}></td><td>{i}{"（済）" if done else ""}</td><td>{esc(net)}</td>'
            f'<td>{esc(pin_label(a))}</td><td>{esc(pin_label(b))}</td>'
            f'<td class="mono">{esc(route_label(a, b) if kind != "ジャンパ線" else hole_label(a) + " → " + hole_label(b))}</td><td>{n} 穴</td>'
            f'<td class="cau">{caution_html(net, a, b, kind)}</td></tr>')
    out.append("</tbody></table>")
    return "".join(out)


CC = {"黒": "#111", "茶": "#7c4a1e", "赤": "#dc2626", "橙": "#f97316", "黄": "#facc15",
      "緑": "#16a34a", "青": "#2563eb", "紫": "#7e22ce", "灰": "#9ca3af", "白": "#fff",
      "金": "#c9a227", "銀": "#c0c0c0"}
# 値 -> (4本帯, 5本帯)。4本帯は 誤差 金(5%)、5本帯は 茶(1%)
BANDS = {
    "1R": ("茶黒金金", "茶黒黒銀茶"), "220R": ("赤赤茶金", "赤赤黒黒茶"),
    "470R": ("黄紫茶金", "黄紫黒黒茶"), "1k": ("茶黒赤金", "茶黒黒茶茶"),
    "10k": ("茶黒橙金", "茶黒黒赤茶"), "22k": ("赤赤橙金", "赤赤黒赤茶"),
}


def swatch(names):
    return "".join(f'<span class="band" style="background:{CC[n]}" title="{n}"></span>' for n in names) + \
        '<span class="bn">' + "・".join(names) + "</span>"


def color_table():
    out = ['<table class="parts"><thead><tr><th>抵抗</th><th>使う場所</th><th>4本帯（炭素皮膜）</th><th>5本帯（金属皮膜）</th></tr></thead><tbody>']
    use = {"1R": "R1（DFPlayer 電源）", "220R": "中継基板 ×5（赤外LED）", "470R": "R4（LED1）",
           "1k": "R21〜R26（GPIO 直列）", "10k": "R5（GPIO8 プルアップ）", "22k": "R11〜R16（プルアップ）"}
    for k in ("1R", "220R", "470R", "1k", "10k", "22k"):
        a, b = BANDS[k]
        out.append(f'<tr><td><b>{k.replace("R","Ω")}</b></td><td>{use[k]}</td><td>{swatch(a)}</td><td>{swatch(b)}</td></tr>')
    out.append("</tbody></table>")
    return "".join(out) + '<p class="note">帯は一方の端に寄っています（寄っている側が左＝1本目）。5本帯は最後の帯（茶）が少し離れています。迷ったらテスターで抵抗値を測って確認。</p>'


def parts_table():
    rows = []
    for ref, p in L.PARTS.items():
        if ref[:1] == "R" and len(ref) == 3 and ref not in ("R11",):
            continue  # レーンの抵抗は後でまとめる
        rows.append((ref, p["value"], p["desc"], p.get("polarity", p.get("note", ""))))
    out = ['<table class="parts"><thead><tr><th>記号</th><th>値</th><th>役目</th><th>向き・注意</th></tr></thead><tbody>']
    for ref, v, d, n in rows:
        if ref == "R11":
            v, d, n = "22k ×6（R11〜R16）／1k ×6（R21〜R26）", "各レーンのプルアップ 22k と GPIO 直列 1k", "向きなし"
            ref = "R11〜R16, R21〜R26"
        out.append(f"<tr><td>{esc(ref)}</td><td>{esc(v)}</td><td>{esc(d)}</td><td>{esc(n)}</td></tr>")
    out.append("</tbody></table>")
    return "".join(out)


POWER_SVG = """
<svg viewBox="0 0 760 250" class="diag" role="img">
 <defs><marker id="ar" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8z" fill="#475569"/></marker></defs>
 <g class="bx"><rect x="10" y="20" width="90" height="50" rx="6" fill="#fde68a"/><text x="55" y="42">12V AC</text><text x="55" y="58">アダプタ</text></g>
 <g class="bx"><rect x="140" y="20" width="60" height="50" rx="6" fill="#fde68a"/><text x="170" y="42">TB1</text><text x="170" y="58">12V入力</text></g>
 <g class="bx"><rect x="240" y="20" width="60" height="50" rx="6"/><text x="270" y="42">F1</text><text x="270" y="58">1.85A</text></g>
 <g class="bx"><rect x="340" y="20" width="60" height="50" rx="6"/><text x="370" y="42">D1</text><text x="370" y="58">逆接防止</text></g>
 <g class="bx"><rect x="440" y="20" width="90" height="50" rx="6" fill="#fecaca"/><text x="485" y="42">U1</text><text x="485" y="58">BP5293-50</text></g>
 <g class="bx"><rect x="440" y="130" width="90" height="50" rx="6" fill="#fde68a"/><text x="485" y="152">TB2</text><text x="485" y="168">→アンプ 12V</text></g>
 <g class="bx"><rect x="580" y="10" width="90" height="40" rx="6" fill="#bfdbfe"/><text x="625" y="35">D2→XIAO 5V</text></g>
 <g class="bx"><rect x="580" y="62" width="90" height="40" rx="6" fill="#c7d2fe"/><text x="625" y="80">R1 1Ω→DFPlayer</text><text x="625" y="94">+C3 100µF</text></g>
 <g class="bx"><rect x="580" y="114" width="90" height="40" rx="6" fill="#fef9c3"/><text x="625" y="139">CN1-7 → 赤外LED</text></g>
 <g stroke="#475569" stroke-width="2" fill="none" marker-end="url(#ar)">
  <line x1="100" y1="45" x2="138" y2="45"/><line x1="200" y1="45" x2="238" y2="45"/><line x1="300" y1="45" x2="338" y2="45"/><line x1="400" y1="45" x2="438" y2="45"/>
  <path d="M420,45 L420,155 L438,155"/>
  <path d="M530,45 L555,45 L555,30 L578,30"/><path d="M555,45 L555,82 L578,82"/><path d="M555,82 L555,134 L578,134"/>
 </g>
 <text x="35" y="110" class="lb">12V系</text><text x="440" y="105" class="lb">5V系 →</text>
 <text x="10" y="210" class="lb">C1 470µF（12V平滑）／C2 220µF（5V平滑）は U1 の前後。GND は全部つながる（TB1-2, C1-, U1-2, C2-, C3-, XIAO GND, DFPlayer GND, VR1-3, CN1-8, TB2-2, TB3-2）。</text>
</svg>
"""

SENSOR_SVG = """
<svg viewBox="0 0 760 330" class="diag" role="img">
 <g class="bx"><rect x="10" y="10" width="170" height="305" rx="8" fill="#fde68a"/><text x="95" y="32" class="tt">CN1（基板側）</text></g>
 <g class="bx lbl">
  <text x="30" y="62" text-anchor="start">1　L0 → P3 (GPIO4)　500円</text>
  <text x="30" y="96" text-anchor="start">2　L1 → P2 (GPIO5)</text>
  <text x="30" y="130" text-anchor="start">3　L2 → P1 (GPIO3)</text>
  <text x="30" y="164" text-anchor="start" fill="#b91c1c">4　L3 → 予備 GPIO10</text>
  <text x="30" y="198" text-anchor="start">5　L4 → HA (GPIO20)</text>
  <text x="30" y="232" text-anchor="start">6　L5 → HB (GPIO21)</text>
  <text x="30" y="266" text-anchor="start">7　+5V</text>
  <text x="30" y="300" text-anchor="start">8　GND</text>
 </g>
 <path d="M180,160 C230,160 230,300 180,300" stroke="#b91c1c" stroke-width="3" fill="none" stroke-dasharray="6 4"/>
 <text x="240" y="236" class="lb" fill="#b91c1c">4 と 8 を短い線でつなぐ！</text>
 <text x="240" y="254" class="lb" fill="#b91c1c">（GPIO10 を GND に落とす。基板では未使用）</text>
 <g stroke="#475569" stroke-width="2" fill="none">
  <line x1="180" y1="58" x2="440" y2="58"/><line x1="180" y1="92" x2="440" y2="92"/><line x1="180" y1="126" x2="440" y2="126"/>
  <line x1="180" y1="194" x2="440" y2="194"/><line x1="180" y1="228" x2="440" y2="228" stroke-opacity="0"/>
 </g>
 <g class="bx">
  <rect x="440" y="10" width="310" height="305" rx="8" fill="#f1f5f9"/><text x="595" y="32" class="tt">中継基板 ICB-86・切らない（220Ω×5）→ 7 芯 40cm → 各センサー</text>
  <text x="460" y="62" text-anchor="start">P3  受光（500円だけ通る）</text>
  <text x="460" y="96" text-anchor="start">P2  受光（5円/100円より大きい）</text>
  <text x="460" y="130" text-anchor="start">P1  受光（1円/50円より大きい）</text>
  <text x="460" y="198" text-anchor="start">HA  穴ビーム A（受光）</text>
  <text x="460" y="232" text-anchor="start">HB  穴ビーム B（受光）</text>
  <text x="460" y="266" text-anchor="start">赤外LED ×5 のアノード側へ 5V（220Ω 経由）</text>
  <text x="460" y="300" text-anchor="start">共通 GND（LED カソード・フォトトランジスタ E）</text>
 </g>
</svg>
"""

CSS = """
:root{--bg:#f8fafc;--fg:#0f172a;--mut:#475569;--card:#fff;--line:#cbd5e1;--ac:#2563eb;--warn:#b91c1c;--ok:#15803d}
@media (prefers-color-scheme:dark){:root{--bg:#0f172a;--fg:#e2e8f0;--mut:#94a3b8;--card:#1e293b;--line:#334155;--ac:#60a5fa;--warn:#f87171;--ok:#4ade80}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.7 system-ui,"Yu Gothic UI","Meiryo",sans-serif}
main{max-width:1000px;margin:0 auto;padding:16px}
h1{font-size:1.6rem;margin:.4em 0}h2{font-size:1.25rem;margin:2em 0 .5em;padding-bottom:.2em;border-bottom:2px solid var(--ac)}h3{font-size:1.05rem;margin:1.2em 0 .3em}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:12px 0}
.warn{border-left:5px solid var(--warn)}.ok{border-left:5px solid var(--ok)}.tip{border-left:5px solid var(--ac)}
.note{color:var(--mut);margin:.2em 0}.mono{font-family:Consolas,monospace}
tr.done td{color:var(--mut);background:rgba(148,163,184,.12)}
.ng{color:var(--warn);font-weight:600}.few{color:#c2410c}.safe{color:var(--ok)}
@media (prefers-color-scheme:dark){.few{color:#fb923c}}
td.cau{font-size:.85rem;line-height:1.45}
table{border-collapse:collapse;width:100%;font-size:.9rem;margin:.4em 0}th,td{border:1px solid var(--line);padding:4px 8px;text-align:left}th{background:var(--card)}
.wrap{overflow-x:auto}
svg{max-width:100%;height:auto}
svg.board{min-width:760px;background:var(--card);border-radius:8px}
svg text{fill:var(--fg);font:11px system-ui,"Yu Gothic UI",sans-serif}
.ax{text-anchor:middle;font-size:9px;fill:var(--mut)}.hole{fill:var(--line)}.pin{fill:#0f172a;stroke:#fff;stroke-width:1}
.band{display:inline-block;width:14px;height:22px;border:1px solid #64748b;margin-right:3px;vertical-align:middle;border-radius:2px}
.bn{margin-left:6px;font-size:.8rem;color:var(--mut)}
.pol{text-anchor:middle;font-weight:bold;font-size:9px;fill:#dc2626 !important}
.pl{text-anchor:middle;font-weight:bold;font-size:11px}.pl.s{font-size:9px}
.diag .bx rect{fill:var(--card);stroke:#475569}.diag .bx text{text-anchor:middle;font-size:12px}.diag .tt{font-weight:bold}.diag .lb{font-size:12px;fill:var(--mut)}
.dot{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:6px;vertical-align:middle}
ol.steps{padding-left:1.4em}ol.steps>li{margin:.5em 0}
label.chk{display:block;margin:.2em 0}
.legend span{margin-right:14px;white-space:nowrap}
.progress{position:sticky;top:0;background:var(--bg);padding:6px 0;z-index:5;border-bottom:1px solid var(--line);font-size:.9rem}
code{background:var(--card);border:1px solid var(--line);padding:0 4px;border-radius:4px}
"""

JS = """
const KEY='board-guide-v1';let st={};try{st=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
const boxes=[...document.querySelectorAll('input[type=checkbox]')];
function upd(){const w=boxes.filter(b=>b.dataset.w);const d=w.filter(b=>b.checked).length;
 document.getElementById('prog').textContent='配線 '+d+' / '+w.length+' 本 完了';}
boxes.forEach((b,i)=>{const k=b.dataset.w?'w'+b.dataset.w:'c'+i;b.checked=!!st[k];
 b.addEventListener('change',()=>{st[k]=b.checked;try{localStorage.setItem(KEY,JSON.stringify(st))}catch(e){};upd()})});
upd();
"""


def main():
    wires = W.build()
    total = sum(len(v) for v in wires.values())
    kinds = {}
    for ws in wires.values():
        for _, _, k, _ in ws:
            kinds[k] = kinds.get(k, 0) + 1

    h = []
    h.append(f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>制御基板の製作手順</title><style>{CSS}</style></head><body><main>')
    h.append('<h1>制御基板の製作手順（ユニバーサル基板 32×23）</h1>')
    h.append(f'<p class="note">配線は全部で <b>{total} 本</b>（' + "・".join(f"{k} {v}" for k, v in kinds.items()) + '）。この HTML は <code>基板設計/gen_手順html.py</code> が <code>netlist.py</code> から作っています。'
             '紙に印刷して使うときは <code>実体配線図.pdf</code>（1:1）を使ってください。</p>')
    h.append('<div class="progress" id="prog"></div>')

    h.append('<h2>0. 全体の流れ</h2><div class="card"><ol class="steps">'
             '<li><b>準備</b>：部品を並べ、テスターとはんだごてを用意</li>'
             '<li><b>部品を載せる</b>：低いもの（抵抗・ダイオード）→ ソケット → 背の高いもの（コンデンサ・端子台）の順</li>'
             f'<li><b>半田面で配線</b>：{total} 本（うちすずメッキ線 {len(W.DONE)} 本は付け済み）。残りのすずメッキ線 → ジャンパ線 → ★の順。1 本ごとにチェック</li>'
             '<li><b>電源を入れる前のテスター確認</b>（短絡チェック）</li>'
             '<li><b>段階通電</b>：12V だけ → 5V → XIAO → DFPlayer の順</li>'
             '<li><b>中継基板と 7 芯ケーブル</b>（センサー側）</li></ol></div>')

    h.append('<h2>1. 準備するもの</h2>')
    h.append('<div class="wrap">' + parts_table() + '</div>')
    h.append('<h3>抵抗のカラーコード</h3><div class="wrap">' + color_table() + '</div>')
    h.append('<div class="card tip">道具：はんだごて（30〜40W）／はんだ（0.8mm）／ニッパー／ピンセット／テスター／すずメッキ線／被覆線（AWG24 くらい）／マスキングテープ（部品の仮止め）。</div>')

    h.append('<h2>2. 基板の見取り図（部品面から見た配置）</h2>')
    h.append('<p class="note">横が列 1〜32、縦が行 A〜W（赤い点線の枠が設計の範囲）。黒い点が穴。マウスを乗せると部品名と足の番号が出ます。<br>'
             '<b>実物の基板は 36 × 27 穴。</b>四隅は「取付」穴で、その隣の 2 穴（図の赤い×）は<b>穴がありません</b>。'
             '設計の <b>1-A は、実物の左から 3 つ目・上から 3 つ目の穴</b>に置きます（四隅の穴なしの場所には何も載りません）。</p>')
    h.append('<div class="wrap">' + board_svg(False) + '</div>')
    h.append('<div class="card warn"><b>図の赤い文字が部品の向き</b>です。<br>'
             '・<b>D1・D2</b>：黒い太線と「K帯」の側に、部品の<b>帯</b>が来る向きで挿す。<br>'
             '・<b>C1・C2・C3</b>：「＋」の穴に<b>長い足</b>（本体の「−」印と反対側）。<br>'
             '・<b>LED1</b>：「A長」の穴に<b>長い足</b>。<br>'
             '・<b>U1</b>：左から IN・GND・OUT。印字面を見て合わせる。<br>'
             '・<b>XIAO</b>：USB の端子を図の上側（行 G 側、「▲USB側」）に向ける。<b>DFPlayer</b>：「▲1番(VCC)」の側が 1 番ピン。<br>'
             '・抵抗・F1・C6 は向きなし。</div>')
    h.append('<div class="card"><b>ゾーン分け</b>：上 A〜E ＝ コネクタ（CN1・TB1〜3）／ G〜Q 左 ＝ レーン入力の抵抗 ／ G〜N 中央〜右 ＝ XIAO（U2）と DFPlayer（U3）のソケット ／ 下 R〜W ＝ 電源回路・音声・LED。</div>')

    h.append('<h2>3. 部品を載せる順番</h2><ol class="steps">'
             '<li><label class="chk"><input type="checkbox"> 抵抗 R11〜R16（22k）・R21〜R26（1k）・R1（1Ω）・R4（470Ω）・R5（10k）。<b>値をテスターで確認</b>してから挿す（色が似ている）</label></li>'
             '<li><label class="chk"><input type="checkbox"> <b>SR54F は表面実装の小さなチップ</b>で穴に挿せない。先に D1・D2 の<b>両端へ細い線（すずメッキ線や抵抗の切り足、長さ約 15mm）を1本ずつはんだ付け</b>して足にする。帯のある端がカソード（K）＝足 2。その足を基板に挿す（足の間隔 5 穴）。向きを間違えると動かない</label></li>'
             '<li><label class="chk"><input type="checkbox"> ポリスイッチ F1</label></li>'
             '<li><label class="chk"><input type="checkbox"> C6（1µF）・LED1（<b>長い足がアノード＝足 1</b>）</label></li>'
             '<li><label class="chk"><input type="checkbox"> ソケット：U2（XIAO 用 7×2）、U3（DFPlayer 用 8×2）。<b>ソケットにだけはんだ付けし、モジュールは最後まで挿さない</b></label></li>'
             '<li><label class="chk"><input type="checkbox"> VR1（10k 半固定）・U1（BP5293-50。<b>印字面を見て IN・GND・OUT の向きを確認</b>）</label></li>'
             '<li><label class="chk"><input type="checkbox"> 電解コンデンサ C1（470µF）・C2（220µF）・C3（100µF）。<b>長い足が＋</b>、足 1</label></li>'
             '<li><label class="chk"><input type="checkbox"> 端子台 TB1〜TB3・CN1（最後。背が高く、はんだ付け中に基板が浮くため）</label></li></ol>')
    h.append('<div class="card warn"><b>やってはいけない</b>：XIAO の GPIO2 / GPIO9（D0・D9）には何も繋がない。電解コンデンサ・ダイオードの向き違いは破裂・発熱の原因。</div>')

    h.append('<h2>4. 電源まわりのつながり</h2><div class="wrap">' + POWER_SVG + '</div>')
    h.append('<div class="card tip">XIAO の 5V ピンには <b>D2 を直列</b>に入れます（USB と同時に挿したとき逆流しないため）。DFPlayer の VCC には <b>R1（1Ω）と C3（100µF）が必須</b>（起動時の電源ノイズ対策）。</div>')

    h.append('<h2>5. センサー側（CN1 と中継基板）</h2><div class="wrap">' + SENSOR_SVG + '</div>')
    h.append('<div class="card warn"><b>v3.0（自作判別部）では 5 本のビームしか使いません。</b>CN1-4（GPIO10）は未使用なので、<b>CN1-4 と CN1-8 を短い線でつなぎ GND に落とす</b>。GPIO10 を出力にしない・浮かせない。<br>フォトトランジスタの C と E を逆にすると「常に遮光」に見える。詳しい線の色は <code>3Dプリント/自作判別部/配線と固定.md</code>。</div>')

    h.append('<h2>6. 半田面の配線（全 ' + str(total) + ' 本）</h2>')
    h.append('<p class="note">基板を裏返して配線します。図は部品面から透かして見た配線です（鏡像ではなく部品面と同じ向き）。<span class="legend">' +
             "".join(f'<span><span class="dot" style="background:{c}"></span>{k}</span>' for k, c in KIND_COLOR.items()) +
             f'<span><span class="dot" style="background:{DONE_COLOR}"></span>付け済みのすずメッキ線</span>'
             '<span>○ 分かれ目（線の途中にはんだ付け）</span></span></p>')
    h.append('<div class="wrap">' + board_svg(True) + '</div>')
    h.append('<h3>半田面から見た向き（基板を裏返した図・左右反転）</h3><p class="note">はんだ付けするときに目に見える向きです。列番号は右が 1、左が 32 になります。XIAO の USB は上のままです。</p>')
    h.append('<div class="wrap">' + board_svg(True, mirror=True) + '</div>')
    h.append('<div class="card tip">コツ：①すずメッキ線は図の道どおりに（他の回路の足の穴は通らないようにしてある）。曲がり角・分かれ目・長い線の途中をはんだで留める。'
             'ただし表の「注意」で<b>盛らない</b>とある穴は他の回路のすぐ隣なので、はんだを付けずに通す（角なら曲げて押さえるだけ）。'
             '途中のほとんどが「盛らない」の線は、ジャンパ線の被覆を抜き取って筒にしたものを通しておくと安心 '
             '②1 本つけるごとに下の表にチェック ③ジャンパ線は被覆線なので交差してよいが、むき出しの芯線の先を隣の穴に触れさせない '
             '④「端は少なめ」の穴ははんだを少なめにし、半田面の穴にはんだが盛り上がって隣とつながっていないかルーペで見る。</div>')
    h.append(wire_table())
    h.append('<div class="card warn"><b>追加の 1 本</b>：上の表とは別に <b>CN1-4 ↔ CN1-8</b>（GPIO10 を GND へ）を忘れずに。<label class="chk"><input type="checkbox"> つないだ</label></div>')

    h.append('<h2>7. 通電前のテスター確認（電源は入れない）</h2><div class="card"><ol class="steps">'
             '<li><label class="chk"><input type="checkbox"> 導通ブザーで <b>+12V と GND</b>（TB1-1 と TB1-2）：<b>鳴らない</b>こと（ショートなし）</label></li>'
             '<li><label class="chk"><input type="checkbox"> <b>+5V と GND</b>（C2 の＋と−）：鳴らない</label></li>'
             '<li><label class="chk"><input type="checkbox"> <b>+3V3 と GND</b>（XIAO ソケットの 12 番と 13 番）：鳴らない</label></li>'
             '<li><label class="chk"><input type="checkbox"> GND がつながるべき所（TB1-2・C1−・U1-2・C2−・U2-13・U3-7・U3-10・VR1-3・CN1-8・TB2-2・TB3-2）が互いに <b>導通する</b></label></li>'
             '<li><label class="chk"><input type="checkbox"> 各レーン：CN1-n と 3V3 の間が約 <b>22kΩ</b>、CN1-n と XIAO の GPIO ピンの間が約 <b>1kΩ</b></label></li>'
             '<li><label class="chk"><input type="checkbox"> LED1：ダイオードモードで R4 側から順方向に電圧が出る（向き確認）</label></li></ol></div>')

    h.append('<h2>8. 段階通電</h2><div class="card"><p class="note">モジュールは 1 つずつ挿す。毎回、触ってみて熱くないか・においがしないか確認。</p><ol class="steps">'
             '<li><label class="chk"><input type="checkbox"> <b>XIAO・DFPlayer なし</b>で 12V を入れる → U1 出力（C2）が <b>5V±0.25V</b></label></li>'
             '<li><label class="chk"><input type="checkbox"> 電源を切り、<b>XIAO だけ</b>挿す → 入れる → XIAO の 3V3 が 3.3V、USB を挿して PC に認識される</label></li>'
             '<li><label class="chk"><input type="checkbox"> 電源を切り、<b>DFPlayer（microSD 入り）</b>を挿す → 入れる → ファーム書き込み後に起動音が鳴る</label></li>'
             '<li><label class="chk"><input type="checkbox"> アンプ接続：TB2 → アンプ 12V、TB3 → アンプ入力。音量は VR1 を中間から調整</label></li></ol></div>')

    h.append('<h2>9. この後</h2><div class="card ok"><ol class="steps">'
             '<li><code>cd firmware</code> → <code>pio run -e esp32c3 -t upload</code>（v3.0 を書き込み）</li>'
             '<li>起動音（0007）が鳴ること／シリアルに <code>SENSOR CHECK</code> が出ること</li>'
             '<li><code>play 1</code> 〜 <code>play 6</code> で全トラックが鳴ること</li>'
             '<li>センサーを繋いで <code>sensortest</code> で 5 本のビームを 1 本ずつ確認</li></ol></div>')
    h.append(f'<script>{JS}</script></main></body></html>')

    out = os.path.join(HERE, "製作手順_制御基板.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write("".join(h))
    print("wrote", out, "wires", total)


if __name__ == "__main__":
    main()
