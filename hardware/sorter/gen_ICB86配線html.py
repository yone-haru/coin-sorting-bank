# -*- coding: utf-8 -*-
"""現物 ICB-86（中継基板）の配線図 HTML を生成する。  python gen_ICB86配線html.py
出力: ICB-86_配線図.html

制御基板の「基板設計/錫線だけ_配線図.html」（gen_錫線html.py）と同じ作りにしてある：
部品面から透かして見た図 → 半田面の図 → 注意 → 付ける物の表（☐・#・回路上の名前・from・to・道・はんだの注意）。
見た目（CSS・基板の描き方・橙の線・黒い足）は 基板設計/gen_手順html.py の CSS と board_svg を写したもの。
（あちらは layout.py / wiring.py を読むので import せず、ここに写している。あちらを変えたらこちらも合わせる）

穴の名前は「段-列」（例 05-G）。銅箔面を見て ICB-86 の文字を上にした向き（写真の向き）で、
段は上から 01～25、列は左から A～Q。I 列（+5V）と J 列（GND）は上から下まで 1 本ずつつながる。
A～B・F～H・K～M・P～Q は段ごとに横につながり、上下の段どうしは離れている。
センサー本体はレール側。この基板に載るのは 220Ω ×5 と、線の継ぎ目だけ。"""

import html
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "ICB-86_配線図.html"

# 穴の割り当て（Codex が 10/06 に決めたもの。変えない）
SENSORS = [
    # 名称、抵抗の段、LED－ の段、受光E の段、信号の段、CN1、線色、制御基板の回路名（netlist.py の LANE{i}_SENS）
    ("P3", 5, 1, 6, 12, 1, "青", "LANE0_SENS"),
    ("P2", 6, 2, 7, 13, 2, "緑", "LANE1_SENS"),
    ("P1", 7, 3, 8, 14, 3, "黄", "LANE2_SENS"),
    ("穴A", 8, 4, 9, 15, 5, "白", "LANE4_SENS"),
    ("穴B", 9, 5, 10, 16, 6, "残りの色", "LANE5_SENS"),
]
POWER = [  # 制御基板からの電源 2 本：CN1 番号、線色、段、列、回路名
    (7, "赤", 1, "I", "+5V"),
    (8, "黒", 11, "J", "GND"),
]

COLS = "ABCDEFGHIJKLMNOPQ"
NCOL, NROW = 17, 25
NO_HOLE = {(r, c) for r in (1, NROW) for c in "ABPQ"}   # 1 段と 25 段の A・B・P・Q は取付穴で、穴が無い
RES_ROWS = {s[1] for s in SENSORS}

# 図の寸法（px）。gen_手順html.py と同じ 1 穴 24px
PITCH = 24
BMX, BMY = 30, 52   # 端の穴から基板の縁まで（47×72mm の基板に 17×25 穴 → 横 3.2mm・縦 5.5mm）
SIDE = 170          # 基板の左右の、線の行き先を書く所
W = 2 * SIDE + 2 * BMX + (NCOL - 1) * PITCH
H = 8 + 2 * BMY + (NROW - 1) * PITCH
NEW_COLOR = "#d97706"   # これから付ける線（gen_手順html.py の すずメッキ線 の色）


def esc(s):
    return html.escape(str(s))


def hole(row, col):
    return f"{row:02d}-{col}"


def items():
    """作業の順に並べた付ける物。# はこの順（前の版と同じ番号なので、ブラウザに保存したチェックがそのまま使える）。
    線は穴から半穴下へ曲げ、段と段のすき間を通って基板の外へ出す。side: a＝A 列の側へ／q＝Q 列の側へ"""
    it = []

    def add(**k):
        k["n"] = len(it) + 1
        it.append(k)

    for name, rr, lg, eg, sig, cn, wire, lane in SENSORS:
        add(kind="res", holes=[(rr, "I"), (rr, "F")], name=name,
            net=f"{name}用 220Ω（+5V → {name}_LED）", frm=hole(rr, "I"), to=hole(rr, "F"),
            route=f"{hole(rr, 'I')} → {hole(rr, 'F')}（胴は G・H の上）", length="3 穴")
    for cn, wire, row, col, net in POWER:
        spread = "05-I～09-I（抵抗 5 本の足）" if col == "I" else "01-J～10-J（LED－・受光E）"
        add(kind="wire", holes=[(row, col)], side="a", net=net,
            frm=f"CN1-{cn} {wire}", to=hole(row, col), route=f"{hole(row, col)} → {spread}",
            lab=f"CN1-{cn} {wire}（{net}）", pol="")
    for name, rr, lg, eg, sig, cn, wire, lane in SENSORS:
        add(kind="wire", holes=[(sig, "M")], side="q", net=f"{lane}（{name} 信号）",
            frm=f"CN1-{cn} {wire}", to=hole(sig, "M"), route=f"{hole(sig, 'M')} → {hole(sig, 'K')}（{name} 受光C）",
            lab=f"CN1-{cn} {wire}（{name} 信号）", pol="")
    for name, rr, lg, eg, sig, cn, wire, lane in SENSORS:
        add(kind="wire", holes=[(rr, "G")], side="a", net=f"{name}_LED",
            frm=f"{name} 赤外LED ＋（長い足）", to=hole(rr, "G"),
            route=f"{hole(rr, 'G')} → {hole(rr, 'F')}（{name}用 220Ω）", lab=f"{name} LED ", pol="＋ 長い足")
        add(kind="wire", holes=[(lg, "J")], side="q", net="GND",
            frm=f"{name} 赤外LED －（短い足）", to=hole(lg, "J"),
            route=f"{hole(lg, 'J')} → 11-J（CN1-8 黒）", lab=f"{name} LED ", pol="－ 短い足")
        add(kind="wire", holes=[(sig, "K")], side="a", net=f"{lane}（{name} 信号）",
            frm=f"{name} 受光 C（短い足）", to=hole(sig, "K"),
            route=f"{hole(sig, 'K')} → {hole(sig, 'M')}（CN1-{cn} {wire}）", lab=f"{name} 受光 ", pol="C 短い足")
        add(kind="wire", holes=[(eg, "J")], side="q", net="GND",
            frm=f"{name} 受光 E（長い足）", to=hole(eg, "J"),
            route=f"{hole(eg, 'J')} → 11-J（CN1-8 黒）", lab=f"{name} 受光 ", pol="E 長い足")
    return it


ITEMS = items()
RESISTORS = [i for i in ITEMS if i["kind"] == "res"]
WIRES = [i for i in ITEMS if i["kind"] == "wire"]
USED = {h for i in ITEMS for h in i["holes"]}


def check_layout():
    """穴の重なり・線どうしの重なりが無いことを確かめる（図を描く前に）"""
    holes = [h for i in ITEMS for h in i["holes"]]
    assert len(holes) == len(set(holes)), "同じ穴に 2 つ挿している"
    assert not (USED & NO_HOLE), "穴の無い所を使っている"
    gaps = {}
    for w in WIRES:
        (r, c), = w["holes"]
        key = (w["side"], r)
        assert key not in gaps, f"線が重なる：{w['lab']} と {gaps[key]['lab']}"
        gaps[key] = w
    # 同じすき間を A 側へ行く線と Q 側へ行く線が使うときは、A 側の線の穴が左にあること
    for (side, r), w in gaps.items():
        if side == "a" and ("q", r) in gaps:
            ca = COLS.index(w["holes"][0][1])
            cq = COLS.index(gaps[("q", r)]["holes"][0][1])
            assert ca < cq, f"{r} 段の下のすき間で線が重なる"


def board_svg(copper):
    """基板の図。copper=False：部品面から透かして見た向き（A が右）／True：半田面（銅箔面・写真の向き。A が左）"""

    def x(col):
        c = COLS.index(col) if isinstance(col, str) else col
        if not copper:
            c = NCOL - 1 - c
        return SIDE + BMX + c * PITCH

    def y(row):
        return 4 + BMY + (row - 1) * PITCH

    o = [f'<svg viewBox="0 0 {W} {H}" class="board" role="img">']
    o.append(f'<rect x="{SIDE}" y="4" width="{2*BMX+(NCOL-1)*PITCH}" height="{2*BMY+(NROW-1)*PITCH}" rx="8" '
             'fill="#a3b18a" opacity=".35" stroke="#14532d" stroke-width="2"/>')
    # 銅箔（使うかどうかに関係なく全部）
    def strip(c1, r1, c2, r2):
        xa, xb = sorted((x(c1), x(c2)))
        o.append(f'<rect x="{xa-8}" y="{y(r1)-8}" width="{xb-xa+16}" height="{y(r2)-y(r1)+16}" rx="7" class="cu"/>')
    for col in "IJ":
        strip(col, 1, col, NROW)
    for r in range(1, NROW + 1):
        strip("F", r, "H", r)
        strip("K", r, "M", r)
        if r not in (1, NROW):
            strip("A", r, "B", r)
            strip("P", r, "Q", r)
    # 穴・取付穴
    for r in range(1, NROW + 1):
        for col in COLS:
            if (r, col) not in NO_HOLE:
                o.append(f'<circle cx="{x(col)}" cy="{y(r)}" r="1.6" class="hole"/>')
    for r in (1, NROW):
        for a, b in (("A", "B"), ("P", "Q")):
            cx = (x(a) + x(b)) / 2
            o.append(f'<circle cx="{cx}" cy="{y(r)}" r="8" fill="#fff" stroke="#475569" stroke-width="2"/>'
                     f'<text x="{cx}" y="{y(r)+3}" class="ax on">取付</text>')
    # 列の名前（上）・段の番号（A 列の側）
    for col in COLS:
        o.append(f'<text x="{x(col)}" y="{y(1)-16}" class="ax">{col}</text>')
    lx = x("A") - 18 if copper else x("A") + 18
    for r in range(1, NROW + 1):
        o.append(f'<text x="{lx}" y="{y(r)+4}" class="ax">{r:02d}</text>')
    o.append(f'<text x="{SIDE + BMX + (NCOL-1)*PITCH/2}" y="22" class="pol">▲上（ICB-86 の文字がある側）</text>')
    # +5V・GND の縦の銅箔の名前（下の余白。I は A 側・J は Q 側へ寄せる）
    for col, txt, toward_a in (("I", "+5V（I 列）", True), ("J", "GND（J 列）", False)):
        left = toward_a == copper
        anchor = "end" if left else "start"
        tx = x(col) - 10 if left else x(col) + 10
        o.append(f'<text x="{tx}" y="{y(NROW)+30}" class="pl s" style="text-anchor:{anchor}">{txt}</text>')
    # 抵抗（部品の外形・名前・足）
    for i in RESISTORS:
        (r, _), _ = i["holes"]
        xa, xb = sorted((x("F"), x("I")))
        g = [f'<g data-g="{i["n"]}">']
        g.append(f'<rect x="{xa-9}" y="{y(r)-9}" width="{xb-xa+18}" height="18" rx="5" fill="#e5e7eb" fill-opacity=".75" stroke="#475569"/>')
        g.append(f'<text x="{x("H")}" y="{y(r)+3}" class="pl s on">{esc(i["name"])}用</text>')
        for col in "FI":
            g.append(f'<circle cx="{x(col)}" cy="{y(r)}" r="4.2" class="pin"><title>{esc(i["name"])}用 220Ω の足（{hole(r, col)}）</title></circle>')
        g.append('</g>')
        o.append("".join(g))
    # 線（穴 → 半穴下のすき間 → 基板の外）。橙＝これから付ける線。チェックすると灰色になる
    for w in WIRES:
        (r, col), = w["holes"]
        hx, hy = x(col), y(r)
        gy = hy + PITCH // 2
        left = (w["side"] == "a") == copper
        ex = SIDE - 6 if left else W - SIDE + 6
        tx, anchor = (ex - 4, "end") if left else (ex + 4, "start")
        tip = f'{esc(w["net"])}: {esc(w["frm"])} → {hole(r, col)}'
        pol = f'<tspan class="p">{esc(w["pol"])}</tspan>' if w["pol"] else ""
        o.append(f'<g data-g="{w["n"]}">'
                 f'<polyline points="{hx},{hy} {hx},{gy} {ex},{gy}" fill="none" stroke-linejoin="round" '
                 f'stroke="{NEW_COLOR}" stroke-width="2.4" opacity=".85"><title>{tip}</title></polyline>'
                 f'<text x="{tx}" y="{gy+4}" class="wl" style="text-anchor:{anchor}">{esc(w["lab"])}{pol}</text>'
                 f'<circle cx="{hx}" cy="{hy}" r="4.2" class="pin"><title>{tip}</title></circle></g>')
    o.append("</svg>")
    return "".join(o)


def caution_html(row, col):
    """その穴のはんだの注意。隣が別の銅箔で、つながると困る所だけ「端は少なめ」"""
    h = hole(row, col)
    if col == "I":
        t = f"{h}（隣の J は GND" + ("。反対隣の H は抵抗のもう片方の足と同じ帯" if row in RES_ROWS else "") + "）"
        if (row, "J") in USED:
            t += "。この段は J にも線が来る"
        return f'<span class="few">端は少なめ：{esc(t)}</span>'
    if col == "J":
        t = f"{h}（隣の I は +5V）"
        if (row, "I") in USED:
            t += "。この段は I にも" + ("抵抗の足" if row in RES_ROWS else "線") + "が来る"
        return f'<span class="few">端は少なめ：{esc(t)}</span>'
    if col == "K":
        return f'<span class="few">端は少なめ：{esc(h)}（隣の J は GND）</span>'
    if col == "G":
        return '<span class="safe">普通でよい</span><br>抵抗の胴の下（胴を浮かせてから差す）'
    return '<span class="safe">普通でよい</span>'


def table(rows, res):
    h = ['<table class="wires"><thead><tr><th></th><th>#</th><th>回路上の名前</th><th>from</th><th>to</th>'
         f'<th>道（{"足の穴 → 足の穴" if res else "差す穴 → 銅箔でつながる穴"}）</th>'
         f'{"<th class=nw>長さ</th>" if res else ""}<th>はんだの注意</th></tr></thead><tbody>']
    for i in rows:
        cau = "<br>".join(dict.fromkeys(caution_html(r, c) for r, c in i["holes"] if not (res and c == "F")))
        h.append(f'<tr data-r="{i["n"]}"><td><input type="checkbox" data-w="{i["n"]}"></td><td>{i["n"]}</td>'
                 f'<td>{esc(i["net"])}</td><td>{esc(i["frm"])}</td><td class="nw">{esc(i["to"])}</td>'
                 f'<td class="mono">{esc(i["route"])}</td>{"<td class=nw>" + esc(i["length"]) + "</td>" if res else ""}'
                 f'<td class="cau">{cau}</td></tr>')
    h.append('</tbody></table>')
    return "".join(h)


def checks(prefix, lines):
    return "".join(f'<label class="chk"><input type="checkbox" data-c="{prefix}{k}"> {t}</label>'
                   for k, t in enumerate(lines))


# 基板設計/gen_手順html.py の CSS をそのまま写したもの（ここから）
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
# （ここまで）。以下は ICB-86 だけで足したもの：銅箔の帯・線の行き先の文字・付け済みの灰色・太字の Ω・折り返さない欄・明るい下地（抵抗・取付穴）の上の文字
CSS += """
.cu{fill:#c9a27e;fill-opacity:.45;stroke:#a16207;stroke-opacity:.35}
.wl{font-size:10px}.wl .p{fill:#dc2626;font-weight:bold}
g.dn polyline{stroke:#94a3b8}g.dn text{fill:var(--mut)}g.dn .p{fill:var(--mut)}g.dn rect{fill:#cbd5e1}
.ohm{font-family:"Segoe UI",Arial,sans-serif}
.nw{white-space:nowrap}
svg text.on{fill:#334155}
"""

# チェックはこのブラウザに保存する（キーは前の版と同じ。# が同じなので付けたチェックが残る）
JS = """
const KEY='icb86-guide-v2';let st={};try{st=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
const boxes=[...document.querySelectorAll('input[type=checkbox]')];
function mark(n,on){document.querySelectorAll('tr[data-r="'+n+'"]').forEach(e=>e.classList.toggle('done',on));
 document.querySelectorAll('g[data-g="'+n+'"]').forEach(e=>e.classList.toggle('dn',on))}
function upd(){const w=boxes.filter(b=>b.dataset.w);const d=w.filter(b=>b.checked).length;
 document.getElementById('prog').textContent='抵抗と線 '+d+' / '+w.length+' 本 完了（チェックはこのブラウザに保存）';}
boxes.forEach(b=>{const k=b.dataset.w?'w'+b.dataset.w:'c'+b.dataset.c;b.checked=!!st[k];if(b.dataset.w)mark(b.dataset.w,b.checked);
 b.addEventListener('change',()=>{st[k]=b.checked;try{localStorage.setItem(KEY,JSON.stringify(st))}catch(e){};
  if(b.dataset.w)mark(b.dataset.w,b.checked);upd()})});
upd();
"""


def main():
    check_layout()
    ohm = '<span class="ohm">Ω</span>'
    gl = "・".join(hole(r, "G") for r in sorted(RES_ROWS))
    h = ['<!doctype html><html lang="ja"><head><meta charset="utf-8">'
         '<meta name="viewport" content="width=device-width,initial-scale=1">'
         f'<title>ICB-86 中継基板配線図</title><style>{CSS}</style></head><body><main>']
    h.append(f'<h1>ICB-86 中継基板の配線図（抵抗 {len(RESISTORS)} 本・線 {len(WIRES)} 本）</h1>')
    h.append('<div class="progress" id="prog"></div>')
    h.append('<p class="note"><b>橙色の線がこれから付ける線</b>です。どの線も基板の外（レールのセンサーと、制御基板の CN1）から来て、'
             '<b>黒い丸の穴</b>に 1 本ずつ差してはんだ付けします。図の端の文字が、その線の元です'
             '（線は被覆線なので、図で銅箔の上を横切っていても問題ありません。図の線は「どの穴へ行くか」の案内です）。'
             '上の図は部品面から透かして見た向き、下の図は基板を裏返したはんだ面の向き（左右反転）です。<br>'
             '<b>茶色の帯が銅箔</b>です。I 列（+5V）と J 列（GND）は上から下まで 1 本、F～H と K～M は<b>その段の 3 穴だけ</b>がつながります。'
             'だから 05-G に差した線は、同じ段の 05-F の抵抗とつながります。<br>'
             f'<b>灰色の四角が抵抗 220{ohm}</b>（5 本。「P3用」はセンサー P3 の LED 用）。部品面に置き、<b>胴を 3mm ほど浮かせます</b>（胴の下の G に線を差すため）。<br>'
             '表の「はんだの注意」で<b class="few">端は少なめ</b>の穴は、隣が別の銅箔（+5V と GND など）です。'
             'はんだを少なめにして、ルーペで隣とつながっていないか見ます。<br>'
             'センサー本体はこの基板に載りません。CN1-4 は線を引きません（制御基板の側で CN1-8 とつないであります）。'
             '表のチェックを付けると、図のその線が灰色（付け済み）になります。</p>')
    h.append('<h2>部品面から透かして見た向き</h2>')
    h.append('<p class="note">抵抗を置き、線を差す面です。列は右が A、左が Q。</p>')
    h.append('<div class="wrap">' + board_svg(False) + '</div>')
    h.append('<h2>半田面から見た向き（基板を裏返した図・左右反転）</h2>')
    h.append('<p class="note">はんだ付けするときに見える向きで、写真と同じ向きです。列は左が A、右が Q。上下は同じで、ICB-86 の文字は上のままです。'
             '穴の名前（段-列）はこの向きで数えます。</p>')
    h.append('<div class="wrap">' + board_svg(True) + '</div>')
    h.append('<div class="card warn">はんだが隣の穴に触れるとショートします。とくに I 列（+5V）と J 列（GND）は隣どうしで、'
             '<b>01 段と 05～09 段は I と J の両方に足や線が来ます</b>。05～09 段は I と H がつながると抵抗が効かなくなり、LED が壊れます。'
             '付けるたびに、裏から見て隣とつながっていないか確認してください。<br>'
             '<b>足の見分け方：</b>赤外LED <code>OSI5LA5113A</code> は長い足＝＋、短い足＝－。'
             '受光素子 <code>L-51ROPT1D1</code> は<b>短い足＝C</b>、長い足＝E（<b>LED と長短が逆</b>）。足を切る前に線に印を付けておきます。</div>')
    h.append(f'<h2>先に付ける抵抗 220{ohm}（{len(RESISTORS)} 本・付けたらチェック）</h2>')
    h.append('<p class="note">5 本とも別々の段で、1 本にまとめません。胴は G・H の上に来るので、3mm ほど浮かせて付けます'
             f'（あとで胴の下の {gl} に LED＋ の線を差すため）。胴をぴったり付けてしまったときは、LED＋ の線を F の抵抗の足に'
             '部品面で巻いてはんだ付けしても同じです（F・G・H は同じ帯）。</p>')
    h.append(table(RESISTORS, True))
    h.append(f'<h2>これから付ける線（{len(WIRES)} 本・付けたらチェック）</h2>')
    h.append('<p class="note">「道」の列は、差した穴から銅箔でどこにつながるかです（例：05-G → 05-F（P3用 220Ω）は、'
             '05-G に差した線が同じ段の帯を通って 05-F の抵抗の足とつながる）。'
             'LED－ と 受光E はどちらも J 列（GND）ですが、穴は 1 本ずつ別にします。'
             '継ぎ目は熱収縮チューブで覆い、線はレールの溝と吊り板のクリップに収めて、はんだの所が引っ張られないようにします。</p>')
    h.append(table(WIRES, False))
    h.append('<div class="card ok"><b>付け終わったら、電源を入れる前に測る：</b>'
             + checks("m", [
                 "導通ブザーで、I 列と J 列の間が鳴らない（束を制御基板につないであると、最初に一瞬鳴ってすぐ止まることがある。"
                 "制御基板のコンデンサの充電なので問題ない）",
                 f"テスターの抵抗レンジで、I 列と {gl} の間がどれも約 220{ohm}（線を付ける前に測るのがいちばん正確）",
                 "12～16 段の K と J 列の間が、どの段も鳴らない",
                 "隣り合う段どうし（05-G と 06-G、12-K と 13-K など）が鳴らない",
                 "12V を入れて <code>sensortest</code> を打ち、5 本のビームを 1 本ずつ指でさえぎると、"
                 "HA・HB・P1・P2・P3 の表示がそれぞれ変わる"]) + '</div>')
    h.append('<p class="note"><small>中継基板は ICB-86 を切らずに使います（10/06 に決定。32×28mm に切る前の案はやめました）。'
             '穴の割り当ては Codex が 10/06 に決めたもののままで、現物ではまだ確かめていません。</small></p>')
    h.append(f'</main><script>{JS}</script></body></html>')

    OUT.write_text("".join(h), encoding="utf-8", newline="\n")
    print("wrote", OUT, "resistors", len(RESISTORS), "wires", len(WIRES), "total", len(ITEMS))


if __name__ == "__main__":
    main()
