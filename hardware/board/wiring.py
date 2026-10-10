# -*- coding: utf-8 -*-
"""
配線の生成と検証
=============================================================================
netlist.py（どこを繋ぐか）と layout.py（どこに挿すか）から、
「どの穴とどの穴を、何で繋ぐか」を計算する。

方式：ネットごとに、全ピンを最小全域木（総配線長が最短になる木）で結ぶ。
      木なので必ず全部つながり、無駄な輪もできない。
      実際の道は、すでに引いた同じネットの線の「途中」から枝分かれしてよい
      （同じ穴を 2 本の線が通る二重配線を作らない）。

繋ぎ方の種類：
    ブリッジ … 隣り合う穴。はんだを盛って繋ぐ
    すずメッキ線 … はんだ面に這わせる裸線。縦横だけで曲げ、他のネットの足の穴・裸線を避けて通す
    ジャンパ線 … 裸線の道がどうしても無い（他の線をまたぐ）ところだけ、被覆線で渡す
=============================================================================
"""
import heapq
from netlist import NETS, PARTS
from layout import PINPOS, hole, rowname, rownum, COLS, ROWS

# 繋ぎ方の判定しきい値（穴の数）
BRIDGE_MAX = 1      # これ以下ならはんだブリッジ
BARE_MAX = 5        # 旧方式（kind_of）の名残。いまは使っていない

# 道選びの重み（小さいほど選ばれやすい）
COST_STEP = 1         # 1 穴進む
COST_BEND = 3         # 曲がり 1 回（曲がりが少ないほど作りやすい）
COST_NEAR_PIN = 1     # 他のネットの足の穴の隣を通る
COST_NEAR_TIN = 1     # 他のネットの裸線の隣を通る
COST_SOLDER_NEAR = 3  # はんだを盛る点（曲がり角・分かれ目）が他のネットの隣
COST_TAP = 1          # 線の途中から枝分かれする

# 実物にはんだ付け済みのすずメッキ線（2026-10-03 ユーザー申告。旧方式の 18 本）。
# この道は変えない。build() は最初にこれを置き、残りをその周りに通す。
DONE = [
    ("5-T", "7-T"), ("13-T", "11-T"), ("19-T", "21-T"), ("8-V", "6-V"),
    ("2-G", "2-I"), ("2-I", "2-K"), ("2-K", "2-M"), ("2-M", "2-O"), ("2-O", "2-Q"),
    ("18-T", "18-V"), ("13-V", "16-V"), ("23-V", "25-V"),
    ("6-G", "8-G"), ("6-I", "8-I"), ("6-K", "8-K"), ("8-M", "6-M"), ("8-O", "6-O"), ("8-Q", "6-Q"),
]

TAP = "途中"   # 線の途中から分かれるときのノード名：(TAP, ネット名, 列, 行)


def cell(h):
    """'5-T' → (5, 20)"""
    c, r = h.split("-")
    return (int(c), rownum(r))


DONE_SET = {frozenset((cell(p), cell(q))) for p, q in DONE}


def is_done(a, b):
    """ノード a-b の線が、はんだ付け済みの 18 本の 1 本か"""
    return frozenset((tuple(a[2:]), tuple(b[2:]))) in DONE_SET


def is_tap(n):
    return n[0] == TAP


def node_label(n):
    """表に出す名前（日本語可）"""
    return f"{n[1]}の線の途中" if is_tap(n) else f"{n[0]}-{n[1]}"


def node_ascii(n):
    """PDF の等幅フォント用（ASCII だけ）"""
    return "(wire)" if is_tap(n) else f"{n[0]}.{n[1]}"


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _blocked(p, q):
    """p-q の途中に、他の足の穴があるか（裸線がそのランドに触れてショートする）"""
    occupied = {pos for pins in PINPOS.values() for pos in pins.values()}
    for c in range(min(p[0], q[0]), max(p[0], q[0]) + 1):
        for r in range(min(p[1], q[1]), max(p[1], q[1]) + 1):
            if (c, r) not in (tuple(p), tuple(q)) and (c, r) in occupied:
                return True
    return False


def kind_of(p, q):
    """旧方式の判定（まっすぐ 5 穴以内なら裸線）。はんだ付け済みの 18 本はこれで決めた"""
    d = manhattan(p, q)
    if d <= BRIDGE_MAX:
        return "ブリッジ"
    if (p[0] == q[0] or p[1] == q[1]) and d <= BARE_MAX and not _blocked(p, q):
        return "すずメッキ線"
    return "ジャンパ線"


def mst(nodes):
    """nodes = [(ref, pin, col, row)] を最小全域木で結ぶ。辺のリストを返す"""
    if len(nodes) < 2:
        return []
    inside = [0]
    outside = list(range(1, len(nodes)))
    edges = []
    while outside:
        best = None
        for i in inside:
            for j in outside:
                d = manhattan(nodes[i][2:], nodes[j][2:])
                if best is None or d < best[0]:
                    best = (d, i, j)
        _, i, j = best
        edges.append((nodes[i], nodes[j]))
        inside.append(j)
        outside.remove(j)
    return edges


PATHS = {}   # (始点の穴, 終点の穴) -> 通る穴の並び（直角に曲がる道）。build() が埋める
COLS_MAX, ROWS_MAX = COLS, ROWS
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _neighbors(p):
    for d in DIRS:
        n = (p[0] + d[0], p[1] + d[1])
        if 1 <= n[0] <= COLS_MAX and 1 <= n[1] <= ROWS_MAX:
            yield n


def owner_map():
    """穴 → その穴に挿さる足のネット名。どのネットにも入っていない足は 'NC:部品-足'（触れてはいけない）"""
    owner = {}
    for ref, pins in PINPOS.items():
        for pin, pos in pins.items():
            owner[tuple(pos)] = f"NC:{ref}-{pin}"
    for net, members in NETS.items():
        for ref, pin in members:
            owner[tuple(PINPOS[ref][pin])] = net
    return owner


def _near_other(p, net, owner, claimed):
    """p の上下左右に、他のネットの足の穴／裸線があるか → (足, 裸線)"""
    pin = tin = False
    for n in _neighbors(p):
        if owner.get(n, net) != net:
            pin = True
        if claimed.get(n, net) != net:
            tin = True
    return pin, tin


def _solder_cost(p, net, owner, claimed):
    pin, tin = _near_other(p, net, owner, claimed)
    return COST_SOLDER_NEAR if (pin or tin) else 0


def _route_tin(src, dst, net, owner, claimed, jitter=None):
    """裸線の道を探す。src / dst は {穴: そこを端にする追加の重み}。
    途中に通れるのは、足も裸線も無い空きの穴だけ。縦横にだけ進み、曲がりと他のネットの隣は重くする。
    jitter は {穴: 小さな重み}（探索用。同じ長さの道のどれを選ぶかを変える）。
    見つかれば穴の並び、無ければ None"""
    heap = []
    seq = 0
    for s, c0 in sorted(src.items()):
        heap.append((c0, seq, s, None, None))
        seq += 1
    heapq.heapify(heap)
    done = {}   # (穴, 向き) -> 一つ前の (穴, 向き)
    while heap:
        cost, _sq, cur, d, prev = heapq.heappop(heap)
        if (cur, d) in done:
            continue
        done[(cur, d)] = prev
        if cur in dst and d is not None:
            path, st = [], (cur, d)
            while st is not None:
                path.append(st[0])
                st = done[st]
            path.reverse()
            assert len(set(path)) == len(path), path
            return path
        for n in _neighbors(cur):
            nd = (n[0] - cur[0], n[1] - cur[1])
            if n in src or (n, nd) in done:
                continue
            if n not in dst and (n in owner or n in claimed):
                continue   # 足の穴・すでに線のある穴は、途中には通れない
            c = cost + COST_STEP
            if d is not None and nd != d:
                c += COST_BEND + _solder_cost(cur, net, owner, claimed)
            if n in dst:
                c += dst[n]
            else:
                pin, tin = _near_other(n, net, owner, claimed)
                c += (COST_NEAR_PIN if pin else 0) + (COST_NEAR_TIN if tin else 0)
                if jitter:
                    c += jitter.get(n, 0)
            seq += 1
            heapq.heappush(heap, (c, seq, n, nd, (cur, d)))
    return None


def _route_soft(p, q, net, owner, claimed):
    """被覆線用の図の道。被覆線はどこを通ってもよいが、他の線・足の上を避けて見やすくする"""
    p, q = tuple(p), tuple(q)
    best = {}
    heap = [(0, 1, 0, p, None, (p,))]
    seq = 0
    while heap:
        cost, _ln, _sq, cur, d, path = heapq.heappop(heap)
        if cur == q:
            return list(path)
        if best.get((cur, d), 1e9) <= cost:
            continue
        best[(cur, d)] = cost
        for n in _neighbors(cur):
            nd = (n[0] - cur[0], n[1] - cur[1])
            if n in path:
                continue
            c = cost + COST_STEP + (COST_BEND if d is not None and nd != d else 0)
            if n != q:
                if owner.get(n, net) != net:
                    c += 4
                if claimed.get(n, net) != net:
                    c += 6
            seq += 1
            heapq.heappush(heap, (c, len(path) + 1, seq, n, nd, path + (n,)))
    return None


def _L_path(p, q):
    """被覆線用：横→縦のL字（道が見つからないときの予備）"""
    (c1, r1), (c2, r2) = p, q
    out = [(c, r1) for c in (range(c1, c2 + 1) if c2 >= c1 else range(c1, c2 - 1, -1))]
    out += [(c2, r) for r in (range(r1 + 1, r2 + 1) if r2 >= r1 else range(r1 - 1, r2 - 1, -1))]
    return out


def _straight(p, q):
    (c1, r1), (c2, r2) = p, q
    assert c1 == c2 or r1 == r2, (p, q)
    n = manhattan(p, q)
    dc, dr = (c2 > c1) - (c2 < c1), (r2 > r1) - (r2 < r1)
    return [(c1 + dc * i, r1 + dr * i) for i in range(n + 1)]


class _UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


# 線を通す順番の決め方。None なら短い順。数なら、その番号の乱数で順番と「同じ長さの道のどれを選ぶか」を
# ゆらす（python wiring.py search で、ジャンパ線がいちばん少なくなる番号を探して、ここに書く）
# 4312：0〜8999 の 9000 通りから選んだ（2026-10-03）。ジャンパ 14 本・危ない点 20。
#   13 本の案（1997・4693）は危ない点が 31〜33 に増え、すずメッキ線も 60 穴以上長くなるので採らない。
#   同じ 14 本の 242 より新しいすずメッキ線が短い（237 穴・最長 22 穴。242 は 47 穴の線がある）。
#   ★この下の道の決め方（コストなど）を変えると、同じ番号でも結果が変わる。変えたら探し直す
SEED = 4312
PRIO = []      # 先に通す線（ネット, 足の穴, 足の穴）。search が、前の回で道の無かった線を先頭に回して探す
JITTER = 0.9   # ゆらしの大きさ（1 穴ぶんより小さく）


def build(seed="default"):
    """戻り値: {ネット名: [(ノードA, ノードB, 種類, 距離), ...]}
    ノードは (部品, 足, 列, 行)。線の途中から分かれるときは (TAP, ネット名, 列, 行)。

    手順：
      1. はんだ付け済みの 18 本（DONE）をそのままの道で置く
      2. 隣の穴どうしはブリッジ
      3. 残りをすずメッキ線で通す（順番は SEED で決まる）。同じネットのすでにつながった部分
         （足・線の途中）のどこからでも出発し、相手側のどこに着いてもよい
      4. 道の無かったものは、他を全部通したあとにもう一度試す。それでも無いものだけジャンパ線
    距離は、すずメッキ線なら通る穴の数（曲がりを含む）、それ以外は直線の穴数。
    """
    if seed == "default":
        seed, prio = SEED, PRIO
    else:
        prio = None
    edges, paths, _score = _route_all(seed, draw_jumpers=True, prio=prio)
    PATHS.clear()
    PATHS.update(paths)
    result = {net: [] for net in NETS}
    for net, a, b, d, k, _name in edges:
        result[net].append((a, b, k, d))
    return result


def _route_all(seed, draw_jumpers=False, prio=None):
    """1 回ぶんの配線。(辺のリスト, 道, 点数) を返す。点数は小さいほどよい"""
    import random
    rng = random.Random(seed) if seed is not None else None
    PATHS = {}
    owner = owner_map()
    jitter = None
    if rng:
        jitter = {(c, r): rng.random() * JITTER for c in range(1, COLS_MAX + 1) for r in range(1, ROWS_MAX + 1)}
    pin_node = {}
    for ref, pins in PINPOS.items():
        for pin, pos in pins.items():
            pin_node[tuple(pos)] = (ref, pin, pos[0], pos[1])

    edges = []
    for net, members in NETS.items():
        nodes = []
        for ref, pin in members:
            c, r = PINPOS[ref][pin]
            nodes.append((ref, pin, c, r))
        # 左上から順に並べておくと、同じ結果が毎回出る
        nodes.sort(key=lambda n: (n[3], n[2], n[0], n[1]))
        for a, b in mst(nodes):
            # e[5] は線の名前（ネット, 足の穴, 足の穴）。PRIO で順番を指定するときに使う
            edges.append([net, a, b, manhattan(a[2:], b[2:]), None,
                          (net,) + tuple(sorted((hole(*a[2:]), hole(*b[2:]))))])

    claimed = {}      # 穴 → その穴を通る裸線のネット
    uf = _UF()        # 電気的につながった穴のまとまり（足・裸線・ブリッジ・ジャンパ）
    for pos in pin_node:
        uf.find(pos)

    def lay_tin(e, path):
        net = e[0]
        a = pin_node.get(path[0]) or (TAP, net, *path[0])
        b = pin_node.get(path[-1]) or (TAP, net, *path[-1])
        e[1], e[2] = a, b
        e[3] = len(path) - 1
        e[4] = "ブリッジ" if e[3] <= BRIDGE_MAX else "すずメッキ線"
        PATHS[(path[0], path[-1])] = list(path)
        for c in path:
            claimed[c] = net
            uf.union(path[0], c)

    # 1. はんだ付け済み
    done_left = set(DONE_SET)
    for e in edges:
        key = frozenset((tuple(e[1][2:]), tuple(e[2][2:])))
        if key in done_left:
            path = _straight(tuple(e[1][2:]), tuple(e[2][2:]))
            for c in path[1:-1]:
                if c in owner or claimed.get(c, e[0]) != e[0]:
                    raise SystemExit(f"はんだ付け済みの線 {hole(*path[0])}→{hole(*path[-1])} が {hole(*c)} で他の足・線に触れる")
            lay_tin(e, path)
            done_left.discard(key)
    if done_left:
        raise SystemExit("はんだ付け済みの線が回路の木に無い: " +
                         ", ".join(f"{hole(*sorted(k)[0])}-{hole(*sorted(k)[1])}" for k in done_left))

    def group(net, pos):
        """pos とつながっている穴（足・同じネットの裸線）"""
        root = uf.find(pos)
        cells = set(p for p in pin_node if owner.get(p) == net and uf.find(p) == root)
        cells |= set(p for p, n in claimed.items() if n == net and uf.find(p) == root)
        return cells

    def ends(cells, net):
        """出発点・到着点の候補と、その追加の重み（足ならそのまま、線の途中なら分かれ目のはんだ）"""
        out = {}
        for p in cells:
            out[p] = 0 if p in pin_node else COST_TAP + _solder_cost(p, net, owner, claimed)
        return out

    def try_tin(e):
        net, a, b = e[0], e[1], e[2]
        ga, gb = group(net, tuple(a[2:])), group(net, tuple(b[2:]))
        if ga & gb:
            raise SystemExit(f"{net}: {node_label(a)} と {node_label(b)} がすでにつながっている（輪になる）")
        path = _route_tin(ends(ga, net), ends(gb, net), net, owner, claimed, jitter)
        if path is None:
            return False
        lay_tin(e, path)
        return True

    rest = [e for e in edges if e[4] is None]
    # 2. ブリッジ（隣の穴）
    for e in rest:
        if e[3] <= BRIDGE_MAX:
            lay_tin(e, [tuple(e[1][2:]), tuple(e[2][2:])])
    rest = [e for e in rest if e[4] is None]
    # 3. すずメッキ線（SEED が無ければ短い順）。prio に挙げた線は先に通す
    if rng:
        order = sorted(rest, key=lambda e: e[3] * rng.uniform(0.3, 3.0) + rng.random() * 4)
    else:
        order = sorted(rest, key=lambda e: e[3])
    if prio:
        rank = {k: i for i, k in enumerate(prio)}
        order.sort(key=lambda e: rank.get(e[5], len(rank)))
    failed = [e for e in order if not try_tin(e)]
    # 4. 道の無かったものをもう一度（他の線が伸びて、近くから分かれられるようになっていることがある）
    while True:
        again = [e for e in failed if not try_tin(e)]
        if len(again) == len(failed):
            break
        failed = again
    # 残りはジャンパ線。両側のまとまりの足どうしで、いちばん近い組を選ぶ
    jclaim = {}
    for e in failed:
        net = e[0]
        ga = [p for p in group(net, tuple(e[1][2:])) if p in pin_node]
        gb = [p for p in group(net, tuple(e[2][2:])) if p in pin_node]
        pa, pb = min(((p, q) for p in ga for q in gb), key=lambda t: (manhattan(*t), t))
        e[1], e[2] = pin_node[pa], pin_node[pb]
        e[3] = manhattan(pa, pb)
        e[4] = "ジャンパ線"
        uf.union(pa, pb)
        if not draw_jumpers:
            continue
        both = dict(claimed)
        both.update(jclaim)
        path = _route_soft(pa, pb, net, owner, both) or _L_path(pa, pb)
        PATHS[(pa, pb)] = path
        for c in path:
            jclaim.setdefault(c, net)

    # 点数：①ジャンパ線の本数 ②はんだを盛る点（曲がり角・分かれ目）が他のネットの隣にある数
    #       ③ジャンパ線ののべ長さ ④すずメッキ線ののべ長さ
    risky = 0
    for e in edges:
        if e[4] != "すずメッキ線":
            continue
        p = PATHS[(tuple(e[1][2:]), tuple(e[2][2:]))]
        pts = [p[i] for i in range(1, len(p) - 1)
               if (p[i][0] - p[i-1][0], p[i][1] - p[i-1][1]) != (p[i+1][0] - p[i][0], p[i+1][1] - p[i][1])]
        pts += [x for x in (p[0], p[-1]) if x not in pin_node]
        risky += sum(1 for x in pts if any(_near_other(x, e[0], owner, claimed)))
    jumpers = [e for e in edges if e[4] == "ジャンパ線"]
    score = (len(jumpers), risky, sum(e[3] for e in jumpers),
             sum(e[3] for e in edges if e[4] != "ジャンパ線"))
    return edges, PATHS, score


def search(n, start=0, rounds=6):
    """SEED の候補を n 個ためす。1 つの SEED につき rounds 回、道の無かった線を先頭に回して通し直す
    （引きはがして通し直す、の簡単な版）。点数のよい順に表示する"""
    rows = []
    for s in [None] + list(range(start, start + n)):
        prio = []
        for _ in range(rounds):
            try:
                edges, _p, score = _route_all(s, prio=prio)
            except (SystemExit, AssertionError) as ex:
                print("seed", s, "失敗:", ex)
                break
            rows.append((score, s if s is not None else -1, list(prio)))
            failed = [e[5] for e in edges if e[4] == "ジャンパ線"]
            prio = failed + [k for k in prio if k not in failed]
    rows.sort()
    for score, s, prio in rows[:10]:
        print(f"seed {s:5d}  ジャンパ {score[0]:2d}  危ない点 {score[1]:2d}  ジャンパ長 {score[2]:3d}  すず長 {score[3]:3d}  PRIO {len(prio)}")
    if rows:
        print("いちばん良い PRIO =", rows[0][2])
    return rows


# =============================================================================
# 検証：実物の穴の上で、配線した結果が netlist.py のネットと完全に一致するか
# （裸線は通る穴すべてのランドに触れる、として数える）
# =============================================================================
def verify(wiring):
    problems = []
    owner = owner_map()
    uf = _UF()
    for pos in owner:
        uf.find(pos)
    tin_owner = {}
    for net, conns in wiring.items():
        for a, b, k, _d in conns:
            pa, pb = tuple(a[2:]), tuple(b[2:])
            for n in (a, b):
                if not is_tap(n) and tuple(PINPOS[n[0]][n[1]]) != tuple(n[2:]):
                    problems.append(f"{net}: {node_label(n)} の穴が layout と違う")
                if not is_tap(n) and owner.get(tuple(n[2:])) != net:
                    problems.append(f"{net}: {node_label(n)} はこのネットの足ではない")
            if k == "ジャンパ線":
                if is_tap(a) or is_tap(b):
                    problems.append(f"{net}: ジャンパ線の端が足でない")
                uf.union(pa, pb)
                continue
            path = PATHS.get((pa, pb))
            if not path or path[0] != pa or path[-1] != pb:
                problems.append(f"{net}: {hole(*pa)}→{hole(*pb)} の道が無い")
                continue
            for p, q in zip(path, path[1:]):
                if manhattan(p, q) != 1:
                    problems.append(f"{net}: {hole(*p)}→{hole(*q)} が 1 穴ずつ進んでいない（斜め・飛び）")
            for c in path:
                if tin_owner.get(c, net) != net:
                    problems.append(f"穴 {hole(*c)} を {tin_owner[c]} と {net} の裸線が両方通る（短絡）")
                tin_owner[c] = net
                uf.union(pa, c)
            for c in path[1:-1]:
                if c in owner:
                    problems.append(f"{net}: 裸線が途中で足の穴 {hole(*c)}（{owner[c]}）を通る")

    # 1. 各ネットの足が、全部ひとつにつながっているか
    for net, members in NETS.items():
        roots = {uf.find(tuple(PINPOS[r][p])) for r, p in members}
        if len(roots) > 1:
            problems.append(f"{net}: 配線をたどっても全部つながらない（{len(roots)} 組に分かれている）")

    # 2. 違うネットの足が、同じまとまりに入っていないか（＝短絡）。未接続の足に触れていないか
    seen = {}
    for pos, net in owner.items():
        r = uf.find(pos)
        if r in seen and seen[r] != net:
            problems.append(f"{seen[r]} と {net} がつながっている（短絡）。{hole(*pos)} 付近")
        seen.setdefault(r, net)

    # 3. 裸線の途中の分かれ目が、同じネットの線の上にあるか
    for net, conns in wiring.items():
        for a, b, k, _d in conns:
            for n in (a, b):
                if is_tap(n) and tin_owner.get(tuple(n[2:])) != net:
                    problems.append(f"{net}: 分かれ目 {hole(*n[2:])} が線の上に無い")

    return problems


def summary(wiring):
    from collections import Counter
    c = Counter(k for conns in wiring.values() for _a, _b, k, _d in conns)
    total = sum(c.values())
    length = sum(d for conns in wiring.values() for _a, _b, _k, d in conns)
    return c, total, length


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        # python wiring.py search 回数 [開始番号]
        search(int(sys.argv[2]) if len(sys.argv) > 2 else 200, int(sys.argv[3]) if len(sys.argv) > 3 else 0)
        raise SystemExit
    w = build()
    probs = verify(w)
    c, total, length = summary(w)
    print(f"配線 {total} 本（ブリッジ {c['ブリッジ']} / すずメッキ線 {c['すずメッキ線']} / ジャンパ線 {c['ジャンパ線']}）")
    print(f"のべ長さ {length} 穴ぶん ＝ 約 {length*2.54:.0f} mm")
    if probs:
        print(f"\n【問題 {len(probs)} 件】")
        for p in probs:
            print("  -", p)
    else:
        print("\n配線検証：全ネットが配線だけで完全につながり、短絡もありません")
