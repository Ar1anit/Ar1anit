#!/usr/bin/env python3
"""Pixel-art asset generator for the profile README.

    python3 scripts/build_assets.py               # (re)draw everything in ./assets
    python3 scripts/build_assets.py sheet x.svg   # sprite review sheet, handy when tweaking poses

Everything (sprites, fonts, animation) is drawn from code with zero
dependencies, so the SVGs are self-contained and keep working inside GitHub's
<img> sandbox (no scripts, no external fonts or images). Animations are plain
CSS keyframes; with prefers-reduced-motion they freeze on a single frame.

The stats panels (high-scores.svg, combo-meter.svg) need a GitHub token from
$GITHUB_TOKEN / $GH_TOKEN or a logged-in `gh` CLI; without one they are left
as they are. .github/workflows/pixel-stats.yml refreshes them daily.
"""
from __future__ import annotations

import html
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'assets'

# ----------------------------------------------------------------------------
# Palette (built around the free "Sweetie 16" palette + a few extra tones)
# ----------------------------------------------------------------------------
INK = '#1a1c2c'
PURPLE = '#5d275d'
RED = '#b13e53'
ORANGE = '#ef7d57'
YELLOW = '#ffcd75'
LIME = '#a7f070'
GREEN = '#38b764'
TEAL = '#257179'
NAVY = '#29366f'
BLUE = '#3b5dc9'
SKY = '#41a6f6'
CYAN = '#73eff7'
WHITE = '#f4f4f4'
SILVER = '#94b0c2'
SLATE = '#566c86'
SHADOW = '#333c57'
# extras
CRIMSON = '#e43b44'
CRIMSON_D = '#9e2835'
SKIN = '#f2b48c'
SKIN_D = '#c98261'
HAIR = '#3d2b2e'
HAIR_L = '#6b4a4f'
BEIGE = '#e8d8b0'
BEIGE_D = '#b8a47e'
SCREEN = '#123b34'
PINK = '#ff77a8'


# ----------------------------------------------------------------------------
# Pixel sprites
# ----------------------------------------------------------------------------
class Sprite(dict):
    """A sparse pixel map: {(x, y): '#rrggbb'}. y grows downwards."""

    def blit(self, other, dx=0, dy=0):
        for (x, y), c in other.items():
            self[(x + dx, y + dy)] = c
        return self

    def moved(self, dx, dy):
        return Sprite({(x + dx, y + dy): c for (x, y), c in self.items()})

    def flipped(self):
        return Sprite({(-1 - x, y): c for (x, y), c in self.items()})

    def rot90(self, k=1, cx=0, cy=0):
        """Rotate clockwise by k quarter turns around pixel (cx, cy)."""
        out = dict(self)
        for _ in range(k % 4):
            out = {(cx - (y - cy), cy + (x - cx)): c for (x, y), c in out.items()}
        return Sprite(out)

    def recolor(self, mapping):
        return Sprite({p: mapping.get(c, c) for p, c in self.items()})

    def bbox(self):
        xs = [x for x, _ in self]
        ys = [y for _, y in self]
        return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def from_ascii(rows, cmap, ox=0, oy=0):
    spr = Sprite()
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in cmap and cmap[ch]:
                spr[(x + ox, y + oy)] = cmap[ch]
    return spr


# ------------------------------------------------------------- rasterising
def capsule(a, b, r):
    """Pixels whose centre lies within r of segment a-b (a, b = pixel coords)."""
    ax, ay = a[0] + .5, a[1] + .5
    bx, by = b[0] + .5, b[1] + .5
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    out = set()
    for x in range(math.floor(min(ax, bx) - r) - 1, math.ceil(max(ax, bx) + r) + 1):
        for y in range(math.floor(min(ay, by) - r) - 1, math.ceil(max(ay, by) + r) + 1):
            px, py = x + .5, y + .5
            t = 0 if l2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
            qx, qy = ax + t * dx, ay + t * dy
            if (px - qx) ** 2 + (py - qy) ** 2 <= r * r + 1e-6:
                out.add((x, y))
    return out


def polygon(pts):
    """Pixels whose centre is inside the polygon (pts in pixel-centre coords)."""
    pts = [(x + .5, y + .5) for x, y in pts]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    out = set()
    for y in range(math.floor(min(ys)) - 1, math.ceil(max(ys)) + 1):
        for x in range(math.floor(min(xs)) - 1, math.ceil(max(xs)) + 1):
            px, py, inside = x + .5, y + .5, False
            for i in range(len(pts)):
                (x1, y1), (x2, y2) = pts[i], pts[i - 1]
                if (y1 > py) != (y2 > py) and px < (x2 - x1) * (py - y1) / (y2 - y1) + x1:
                    inside = not inside
            if inside:
                out.add((x, y))
    return out


def rect(x, y, w, h):
    return {(i, j) for i in range(x, x + w) for j in range(y, y + h)}


def ellipse(cx, cy, rx, ry):
    return {(x, y) for x in range(math.floor(cx - rx) - 1, math.ceil(cx + rx) + 2)
            for y in range(math.floor(cy - ry) - 1, math.ceil(cy + ry) + 2)
            if ((x + .5 - cx) / rx) ** 2 + ((y + .5 - cy) / ry) ** 2 <= 1.0}


N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))


def dilate(mask, n=N4):
    return set(mask) | {(x + dx, y + dy) for x, y in mask for dx, dy in n}


def paint(spr, mask, base, shade=None, light=1, hi=None, ink=INK):
    """Outline the mask in ink, then fill it with simple directional shading.

    light=+1 means light comes from the right (front of a right-facing fighter),
    so the left and bottom edges get the shade colour.
    """
    for p in dilate(mask) - set(mask):
        spr[p] = ink
    for x, y in mask:
        c = base
        if shade and ((x, y + 1) not in mask or (x - light, y) not in mask):
            c = shade
        elif hi and ((x, y - 1) not in mask):
            c = hi
        spr[(x, y)] = c
    return spr


def paint_bitmap(spr, bmp, ink=INK):
    """Blit a hand-drawn bitmap with an automatic 1px outline."""
    for p in dilate(set(bmp)) - set(bmp):
        spr[p] = ink
    spr.blit(bmp)
    return spr


def unit(dx, dy):
    d = math.hypot(dx, dy) or 1
    return dx / d, dy / d


def ahead(p, q, n):
    """Point n pixels beyond q along the direction p->q."""
    ux, uy = unit(q[0] - p[0], q[1] - p[1])
    return round(q[0] + ux * n), round(q[1] + uy * n)


# ----------------------------------------------------------------------------
# SVG helpers
# ----------------------------------------------------------------------------
def rects_for(pixels):
    """Greedy merge of a pixel set into rectangles (x, y, w, h)."""
    rows = {}
    for x, y in pixels:
        rows.setdefault(y, []).append(x)
    runs = {}
    for y, xs in rows.items():
        xs.sort()
        start = prev = xs[0]
        for x in xs[1:] + [None]:
            if x is not None and x == prev + 1:
                prev = x
                continue
            runs.setdefault(y, []).append((start, prev + 1))
            if x is not None:
                start = prev = x
    out, active = [], {}
    for y in sorted(runs):
        nxt = {}
        for x0, x1 in runs[y]:
            if (x0, x1) in active and active[(x0, x1)][1] + active[(x0, x1)][2] == y:
                r = active.pop((x0, x1))
                nxt[(x0, x1)] = (r[0], r[1], r[2] + 1)
            else:
                nxt[(x0, x1)] = (x0, y, 1)
        for (x0, x1), r in active.items():
            out.append((x0, r[1], x1 - x0, r[2]))
        active = nxt
    for (x0, x1), r in active.items():
        out.append((x0, r[1], x1 - x0, r[2]))
    return out


def path_d(pixels):
    """Compact path data: one closed rect per run, chained with relative moves."""
    out, px, py = [], None, None
    for x, y, w, h in sorted(rects_for(pixels), key=lambda r: (r[1], r[0])):
        out.append(f'M{x} {y}' if px is None else f'm{x - px} {y - py}')
        out.append(f'h{w}v{h}h{-w}z')
        px, py = x, y
    return ''.join(out)


def _gap_filled(own, later):
    """Extend each row-run of `own` across gaps made only of `later` pixels."""
    rows = {}
    for x, y in own:
        rows.setdefault(y, []).append(x)
    out = set(own)
    for y, xs in rows.items():
        xs.sort()
        for a, b in zip(xs, xs[1:]):
            if b - a > 1 and all((x, y) in later for x in range(a + 1, b)):
                out.update((x, y) for x in range(a + 1, b))
    return out


def sprite_svg(spr, attrs=''):
    """Encode a sprite as one <path> per colour.

    Colours are painted from most to least common; a layer may run straight
    through pixels that a later layer paints over anyway, which merges many
    tiny runs (outlines!) into longer ones. Falls back to plain per-colour
    paths when that is smaller.
    """
    by_color = {}
    for p, c in spr.items():
        by_color.setdefault(c, set()).add(p)
    order = sorted(by_color, key=lambda c: (-len(by_color[c]), c))
    later = set(spr)
    layered = []
    for c in order:
        later -= by_color[c]
        layered.append((c, _gap_filled(by_color[c], later)))
    plain = [(c, by_color[c]) for c in order]
    best = min((layered, plain), key=lambda ls: sum(len(rects_for(px)) for _, px in ls))
    paths = ''.join(f'<path fill="{c}" d="{path_d(px)}"/>' for c, px in best)
    return f'<g{attrs}>{paths}</g>' if attrs else paths


def svg_doc(w, h, body, css='', title='', extra_defs=''):
    style = f'<style>{css}</style>' if css else ''
    t = f'<title>{html.escape(title, quote=False)}</title>' if title else ''
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w * 3}" height="{h * 3}" '
            f'shape-rendering="crispEdges">{t}{style}{extra_defs}{body}</svg>\n')


# ----------------------------------------------------------------------------
# Fighter 1: Arianit (faces right)
# ----------------------------------------------------------------------------
P1C = dict(skin=SKIN, skin_d=SKIN_D, hair=HAIR, hair_l=HAIR_L,
           hood=BLUE, hood_d=NAVY, hood_l=SKY, pants=SHADOW, pants_d='#232838',
           shoe=WHITE, shoe_d=SILVER, glove=CRIMSON, glove_d=CRIMSON_D,
           band=CRIMSON, band_d=CRIMSON_D)

HEAD_CMAP = {'h': HAIR, 'H': HAIR_L, 's': SKIN, 'S': SKIN_D, 'r': CRIMSON, 'R': CRIMSON_D,
             'e': INK, 'm': CRIMSON_D, 'w': WHITE, 'k': INK}

# Heads face right. Anchor (where the neck attaches) is marked by HEAD_ANCHOR.
P1_HEADS = {
    'normal': [
        "....h..h.h....",
        "...hhhhhhhhh..",
        "..hhHHhhhhhhh.",
        ".hhHhhhhhhhhhh",
        ".hhhhhhhhhhhhh",
        "rrrrrrrrrrrrrr",
        "RhhRRRRRRRRRRR",
        "hhhhhshhsshhsh",
        "hhhSsssskwsske",
        "hhSsSsssessske",
        ".hSSssssssssss",
        ".hSSssssssssm.",
        "..SSSssssssss.",
        "....SSSSSSs...",
    ],
    'angry': [
        "....h..h.h....",
        "...hhhhhhhhh..",
        "..hhHHhhhhhhh.",
        ".hhHhhhhhhhhhh",
        ".hhhhhhhhhhhhh",
        "rrrrrrrrrrrrrr",
        "RhhRRRRRRRRRRR",
        "hhhhhshhhsshhh",
        "hhhSsssskkssek",
        "hhSsSssseessse",
        ".hSSssssssssss",
        ".hSSsssssssmmm",
        "..SSSssssssss.",
        "....SSSSSSs...",
    ],
    'happy': [
        "....h..h.h....",
        "...hhhhhhhhh..",
        "..hhHHhhhhhhh.",
        ".hhHhhhhhhhhhh",
        ".hhhhhhhhhhhhh",
        "rrrrrrrrrrrrrr",
        "RhhRRRRRRRRRRR",
        "hhhhhshhsshhsh",
        "hhhSssssekesse",
        "hhSsSsssssssss",
        ".hSSsssssmmmms",
        ".hSSsssssmwwm.",
        "..SSSssssmms..",
        "....SSSSSSs...",
    ],
    'hurt': [
        "....h..h.h....",
        "...hhhhhhhhh..",
        "..hhHHhhhhhhh.",
        ".hhHhhhhhhhhhh",
        ".hhhhhhhhhhhhh",
        "rrrrrrrrrrrrrr",
        "RhhRRRRRRRRRRR",
        "hhhhhshhsshhsh",
        "hhhSssssessses",
        "hhSsSssssessse",
        ".hSSsssseessss",
        ".hSSssssssmmm.",
        "..SSSsssssmm..",
        "....SSSSSSs...",
    ],
}
HEAD_ANCHOR = (6, 13)  # bitmap pixel that sits on the neck joint


def p1_head(face, at, tails=0):
    bmp = from_ascii(P1_HEADS[face], HEAD_CMAP, at[0] - HEAD_ANCHOR[0], at[1] - HEAD_ANCHOR[1])
    spr = Sprite()
    paint_bitmap(spr, bmp)
    # headband tails fluttering behind the head
    bx, by = at[0] - HEAD_ANCHOR[0], at[1] - HEAD_ANCHOR[1] + 5
    shapes = [
        [(-1, 0), (-2, 0), (-3, 1), (-4, 1), (-5, 2), (-2, 2), (-3, 3), (-4, 4)],
        [(-1, 0), (-2, -1), (-3, -1), (-4, -1), (-5, -2), (-2, 1), (-3, 2), (-4, 2), (-5, 2)],
        [(-1, 0), (-2, 1), (-3, 2), (-3, 3), (-4, 4), (-2, 2), (-1, 2)],
    ][tails]
    tail = Sprite({(bx + x, by + y): CRIMSON for x, y in shapes})
    out = Sprite()
    paint_bitmap(out, tail)
    out.blit(spr)
    return out


def p1_figure(p):
    """Render one pose of the hero from a dict of joints (pixel coords, y up = negative)."""
    c = P1C
    spr = Sprite()
    hip, neck = p['hip'], p['neck']

    def arm(sh, el, ha, far):
        base, sh_c = (c['hood_d'], INK) if far else (c['hood'], c['hood_d'])
        paint(spr, capsule(sh, el, 1.6) | capsule(el, ha, 1.4), base, sh_c)
        g, gd = (c['glove_d'], INK) if far else (c['glove'], c['glove_d'])
        paint(spr, capsule(ha, ahead(el, ha, 1), 2.1), g, gd)

    def leg(hp, kn, ft, far, toe=None):
        base, sh_c = (c['pants_d'], INK) if far else (c['pants'], c['pants_d'])
        paint(spr, capsule(hp, kn, 2.3) | capsule(kn, ft, 1.9), base, sh_c)
        tdir = toe or (1, 0)
        tip = (ft[0] + round(tdir[0] * 3), ft[1] + round(tdir[1] * 3))
        s, sd = (c['shoe_d'], SLATE) if far else (c['shoe'], c['shoe_d'])
        paint(spr, capsule(ft, tip, 1.5), s, sd)

    def torso():
        (hx, hy), (nx, ny) = hip, neck
        ux, uy = unit(nx - hx, ny - hy)
        px, py = -uy, ux  # perpendicular (points "back" for an upright body)
        cw, ww = 5.0, 4.2
        pts = [(nx + px * cw, ny + py * cw), (nx - px * cw, ny - py * cw),
               (hx - px * ww, hy - py * ww), (hx + px * ww, hy + py * ww)]
        m = polygon(pts)
        paint(spr, m, c['hood'], c['hood_d'])
        # hoodie details: zipper + pocket + hood bump
        for t in range(2, 10):
            zx = round(hx + (nx - hx) * t / 11 - px * 1.5)
            zy = round(hy + (ny - hy) * t / 11 - py * 1.5)
            if (zx, zy) in m:
                spr[(zx, zy)] = c['hood_d']
        hood = capsule((round(nx + px * 3), ny + 1), (round(nx + px * 4), ny + 3), 1.6)
        paint(spr, hood, c['hood'], c['hood_d'])
        for t in range(2, 6):  # hood string
            sx = round(nx - px * 2.5)
            spr[(sx, ny + t)] = WHITE if t < 5 else spr.get((sx, ny + t))

    def head():
        spr.blit(p1_head(p.get('face', 'normal'), p.get('head', neck), p.get('tails', 0)))

    nsh = p.get('nsh', (neck[0] + 1, neck[1] + 2))
    fsh = p.get('fsh', (neck[0] - 1, neck[1] + 2))
    nhp = p.get('nhp', (hip[0] + 1, hip[1]))
    fhp = p.get('fhp', (hip[0] - 1, hip[1]))
    parts = {
        'farm': lambda: arm(fsh, p['fel'], p['fha'], True),
        'fleg': lambda: leg(fhp, p['fkn'], p['fft'], True, p.get('ftoe')),
        'torso': torso,
        'nleg': lambda: leg(nhp, p['nkn'], p['nft'], False, p.get('ntoe')),
        'head': head,
        'narm': lambda: arm(nsh, p['nel'], p['nha'], False),
    }
    for name in p.get('order', ('farm', 'fleg', 'torso', 'nleg', 'head', 'narm')):
        parts[name]()
    return spr


def jitter(p, dx=0, dy=0, **over):
    """Copy a pose, shifting every joint (handy for bob frames)."""
    q = {}
    for k, v in p.items():
        q[k] = (v[0] + dx, v[1] + dy) if isinstance(v, tuple) and len(v) == 2 and all(isinstance(i, int) for i in v) else v
    q.update(over)
    return q


P1_IDLE = dict(hip=(0, -15), neck=(1, -26),
               nel=(6, -20), nha=(9, -25), fel=(3, -19), fha=(6, -23),
               nkn=(5, -8), nft=(7, -2), fkn=(-4, -8), fft=(-7, -2), ftoe=(1, 0))

P1_POSES = {
    'idle1': P1_IDLE,
    'idle2': jitter(P1_IDLE, 0, 1, nkn=(5, -7), fkn=(-4, -7), nft=(7, -2), fft=(-7, -2), tails=1),
    'walk1': dict(hip=(0, -15), neck=(2, -26), nel=(7, -20), nha=(10, -24), fel=(4, -19), fha=(7, -23),
                  nkn=(6, -8), nft=(9, -2), fkn=(-3, -7), fft=(-6, -3), tails=1),
    'walk2': dict(hip=(0, -16), neck=(2, -27), nel=(7, -21), nha=(10, -25), fel=(4, -20), fha=(7, -24),
                  nkn=(2, -8), nft=(1, -2), fkn=(0, -8), fft=(-2, -2), tails=2),
    'jab': dict(hip=(0, -15), neck=(3, -26), nsh=(4, -24), nel=(10, -24), nha=(15, -24),
                fel=(4, -19), fha=(7, -23), nkn=(6, -8), nft=(8, -2), fkn=(-4, -8), fft=(-7, -2),
                face='angry', tails=1),
    'cross': dict(hip=(1, -15), neck=(4, -26), fsh=(3, -24), fel=(9, -24), fha=(15, -25),
                  nel=(8, -20), nha=(9, -25), nkn=(6, -8), nft=(8, -2), fkn=(-3, -8), fft=(-6, -2),
                  face='angry', tails=2, order=('fleg', 'torso', 'farm', 'nleg', 'head', 'narm')),
    'kick': dict(hip=(-1, -16), neck=(-4, -26), nhp=(0, -16), nkn=(7, -21), nft=(14, -25), ntoe=(1, -0.3),
                 fkn=(-1, -8), fft=(-2, -2), nel=(-1, -20), nha=(2, -24), fel=(-6, -22), fha=(-9, -19),
                 face='angry', tails=1, order=('farm', 'fleg', 'torso', 'head', 'nleg', 'narm')),
    'crouch': dict(hip=(0, -9), neck=(3, -19), nel=(8, -13), nha=(10, -18), fel=(5, -12), fha=(8, -16),
                   nkn=(7, -6), nft=(6, -2), fkn=(-5, -5), fft=(-7, -2), face='angry', tails=0),
    'upper': dict(hip=(0, -17), neck=(2, -28), nsh=(3, -27), nel=(5, -34), nha=(6, -40),
                  fel=(-2, -21), fha=(1, -19), nkn=(5, -14), nft=(5, -7), ntoe=(1, 0.2),
                  fkn=(-1, -9), fft=(-3, -2), face='angry', tails=2,
                  order=('farm', 'fleg', 'torso', 'nleg', 'head', 'narm')),
    'airkick': dict(hip=(0, -17), neck=(-2, -28), nhp=(1, -17), nkn=(7, -21), nft=(12, -27), ntoe=(0.6, -0.8),
                    fkn=(3, -12), fft=(-2, -8), nel=(1, -22), nha=(4, -26), fel=(-5, -23), fha=(-8, -26),
                    face='angry', tails=1, order=('farm', 'fleg', 'torso', 'head', 'nleg', 'narm')),
    'airpunch': dict(hip=(0, -17), neck=(2, -28), nsh=(3, -27), nel=(8, -31), nha=(12, -35),
                     fel=(-1, -22), fha=(2, -25), nkn=(5, -14), nft=(3, -8), fkn=(-1, -12), fft=(-4, -6),
                     face='angry', tails=2),
    'block': dict(hip=(-1, -15), neck=(-2, -26), head=(-3, -26), nsh=(-1, -24), nel=(6, -22), nha=(7, -31),
                  fsh=(-3, -24), fel=(4, -21), fha=(5, -30), nkn=(4, -8), nft=(6, -2), fkn=(-5, -8), fft=(-8, -2),
                  face='angry', tails=2, order=('fleg', 'torso', 'nleg', 'head', 'farm', 'narm')),
    'win1': dict(hip=(0, -15), neck=(0, -26), nsh=(1, -24), nel=(4, -31), nha=(4, -38),
                 fel=(-5, -20), fha=(-2, -17), nkn=(3, -8), nft=(4, -2), fkn=(-3, -8), fft=(-4, -2),
                 face='happy', tails=1),
    'win2': dict(hip=(0, -16), neck=(0, -27), nsh=(1, -25), nel=(5, -31), nha=(4, -37),
                 fel=(-5, -21), fha=(-2, -18), nkn=(3, -8), nft=(4, -2), fkn=(-3, -8), fft=(-4, -2),
                 face='happy', tails=2, head=(0, -28)),
    'jump': dict(hip=(0, -17), neck=(1, -28), nel=(6, -23), nha=(8, -28), fel=(2, -22), fha=(5, -26),
                 nkn=(5, -13), nft=(2, -8), fkn=(-1, -11), fft=(-5, -7), tails=2),
    'deploy': dict(hip=(0, -15), neck=(2, -26), nsh=(3, -24), nel=(9, -25), nha=(14, -28),
                   fel=(3, -19), fha=(6, -23), nkn=(6, -8), nft=(8, -2), fkn=(-4, -8), fft=(-7, -2),
                   face='angry', tails=1),
}


# ----------------------------------------------------------------------------
# Fighter 2: the Hallucinator, a rogue LLM robot with a CRT head (faces left)
# ----------------------------------------------------------------------------
METAL, METAL_D, METAL_L = SILVER, SLATE, '#c9dbe6'
RGLOVE, RGLOVE_D = YELLOW, ORANGE

FACES = {  # 10x7 pixel faces drawn on the CRT screen (robot looks left)
    'normal': ["..........", ".##...##..", ".##...##..", "..........", "..........", "..####....", ".........."],
    'smug':   ["..........", ".#.#..#.#.", "#...##...#", "..........", "...####...", "......#...", ".........."],
    'hurt':   ["..........", "#.....#...", ".##....##.", "#.....#...", "..........", "..###.....", ".#...#...."],
    'dizzy':  ["..........", ".###..###.", ".#.#..#.#.", ".##...##..", "..........", "..#.#.#...", "...#.#...."],
    'ko':     ["..........", "#.#...#.#.", ".#.....#..", "#.#...#.#.", "..........", ".#.#.#.#..", "..#.#.#..."],
    'talk':   ["..........", ".##...##..", ".##...##..", "..........", "...##.....", "..#..#....", "...##....."],
    'wink':   ["..........", ".##.......", ".##...###.", "..........", "..........", "..####....", "...##....."],
    'huh':    ["...###....", "..#...#...", "......#...", ".....#....", "....#.....", "..........", "....#....."],
    'grin':   ["..........", ".#.#..#.#.", "#...##...#", "..........", "..####....", "..#..#....", "...##....."],
}


def crt_head(face='normal', glow=LIME):
    """CRT monitor head, ~18x16. Anchor = bottom centre of the stand (0, 0)."""
    spr = Sprite()
    body = {(x, y) for x in range(-9, 8) for y in range(-15, -2)} - {(-9, -15), (7, -15), (-9, -3), (7, -3)}
    back = {(x, y) for x in range(8, 11) for y in range(-13, -4)}  # tube depth (behind, to the right)
    paint(spr, back, BEIGE_D, '#8f7e5f', light=-1)
    paint(spr, body, BEIGE, BEIGE_D, light=-1)
    # screen
    scr = {(x, y) for x in range(-7, 5) for y in range(-13, -4)} - {(-7, -13), (4, -13), (-7, -5), (4, -5)}
    for p in dilate(scr) - scr:
        spr[p] = SHADOW
    for p in scr:
        spr[p] = SCREEN
    for x in range(-6, 4):  # scanline glint
        spr[(x, -12)] = '#1b5148'
    bmp = from_ascii(FACES[face], {'#': glow}, -7, -12)
    for p, col in bmp.items():
        if p in scr:
            spr[p] = col
    # knobs + stand
    spr[(5, -4)] = RED
    spr[(3, -4)] = LIME
    paint(spr, rect(-3, -2, 5, 2), METAL_D, SHADOW, light=-1)
    return spr


def antenna(spr, top, blink=True):
    x, y = top
    for i in range(4):
        spr[(x, y + i)] = SHADOW
    paint(spr, rect(x - 1, y - 2, 2, 2), CRIMSON if blink else CRIMSON_D)


def robot_figure(p):
    spr = Sprite()
    hip, neck = p['hip'], p['neck']

    def arm(sh, el, ha, far):
        base, sh_c = (METAL_D, SHADOW) if far else (METAL, METAL_D)
        paint(spr, capsule(sh, el, 1.5) | capsule(el, ha, 1.5), base, sh_c, light=-1)
        g, gd = (RGLOVE_D, CRIMSON_D) if far else (RGLOVE, RGLOVE_D)
        paint(spr, capsule(ha, ahead(el, ha, 2), 2.4), g, gd, light=-1)

    def leg(hp, kn, ft, far, toe=None):
        base, sh_c = (METAL_D, SHADOW) if far else (METAL, METAL_D)
        paint(spr, capsule(hp, kn, 2.0) | capsule(kn, ft, 2.0), base, sh_c, light=-1)
        tdir = toe or (-1, 0)
        tip = (ft[0] + round(tdir[0] * 3), ft[1] + round(tdir[1] * 3))
        back = (ft[0] - round(tdir[0] * 1), ft[1] - round(tdir[1] * 1))
        paint(spr, capsule(back, tip, 1.8), SHADOW if not far else INK, INK, light=-1)

    def torso():
        (hx, hy), (nx, ny) = hip, neck
        ux, uy = unit(nx - hx, ny - hy)
        px, py = -uy, ux
        w1, w2 = 8.0, 6.0
        pts = [(nx + px * w1, ny + py * w1), (nx - px * w1, ny - py * w1),
               (hx - px * w2, hy - py * w2), (hx + px * w2, hy + py * w2)]
        m = polygon(pts)
        paint(spr, m, PURPLE, '#3e1a3f', light=-1, hi='#7b3b7b')
        # chest plate with "LLM" + belt
        cx, cy = round(hx + (nx - hx) * .55), round(hy + (ny - hy) * .55)
        plate = {(x, y) for x in range(cx - 7, cx + 8) for y in range(cy - 3, cy + 4)}
        plate &= m
        for q in plate:
            spr[q] = INK
        for q, col in text_sprite('LLM', FONT_S, LIME).moved(cx - 6, cy - 2).items():
            if q in plate:
                spr[q] = col
        for q in m:
            if q[1] in (round(hy - 1), round(hy - 2)):
                spr[q] = YELLOW if (q[0] + q[1]) % 3 else ORANGE

    def head():
        h = crt_head(p.get('face', 'normal'))
        rot = p.get('head_rot', 0)
        hx, hy = p.get('head', neck)
        if rot:
            h = h.rot90(rot)
        h = h.moved(hx, hy)
        if not rot:
            antenna(h, (hx - 1, hy - 19), p.get('blink', True))
        spr.blit(h)

    nsh = p.get('nsh', (neck[0] - 1, neck[1] + 2))
    fsh = p.get('fsh', (neck[0] + 2, neck[1] + 2))
    nhp = p.get('nhp', (hip[0] - 2, hip[1]))
    fhp = p.get('fhp', (hip[0] + 2, hip[1]))
    parts = {
        'farm': lambda: arm(fsh, p['fel'], p['fha'], True),
        'fleg': lambda: leg(fhp, p['fkn'], p['fft'], True, p.get('ftoe')),
        'torso': torso,
        'nleg': lambda: leg(nhp, p['nkn'], p['nft'], False, p.get('ntoe')),
        'head': head,
        'narm': lambda: arm(nsh, p['nel'], p['nha'], False),
    }
    for name in p.get('order', ('farm', 'fleg', 'torso', 'nleg', 'head', 'narm')):
        parts[name]()
    return spr


R_IDLE = dict(hip=(0, -17), neck=(0, -30), head=(0, -30),
              nel=(-6, -24), nha=(-9, -30), fel=(5, -23), fha=(1, -28),
              nkn=(-5, -9), nft=(-7, -2), fkn=(5, -9), fft=(7, -2), ftoe=(-1, 0))

R_POSES = {
    'idle1': R_IDLE,
    'idle2': jitter(R_IDLE, 0, 1, nkn=(-5, -8), fkn=(5, -8), nft=(-7, -2), fft=(7, -2), blink=False),
    'smug': dict(R_IDLE, face='smug', nel=(-6, -23), nha=(-3, -18), fel=(6, -23), fha=(3, -18)),
    'huh1': dict(R_IDLE, face='huh'),
    'huh2': jitter(R_IDLE, 0, 1, nkn=(-5, -8), fkn=(5, -8), nft=(-7, -2), fft=(7, -2), blink=False, face='huh'),
    'throw': dict(hip=(0, -17), neck=(-2, -30), head=(-2, -30), nsh=(-3, -28), nel=(-10, -28), nha=(-16, -29),
                  fel=(5, -23), fha=(2, -28), nkn=(-6, -9), nft=(-9, -2), fkn=(5, -9), fft=(7, -2),
                  face='smug'),
    'hurt1': dict(hip=(1, -17), neck=(4, -29), head=(5, -29), nel=(-2, -26), nha=(-5, -31),
                  fel=(9, -25), fha=(12, -30), nkn=(-4, -9), nft=(-6, -2), fkn=(6, -9), fft=(8, -2),
                  face='hurt'),
    'hurt2': dict(hip=(2, -17), neck=(6, -28), head=(7, -28), nel=(1, -31), nha=(-2, -36),
                  fel=(11, -26), fha=(14, -22), nkn=(-3, -9), nft=(-6, -2), fkn=(7, -9), fft=(10, -2),
                  face='hurt', blink=False),
    'launch': dict(hip=(0, -17), neck=(3, -30), head=(3, -30), nel=(-3, -36), nha=(-6, -41),
                   fel=(8, -35), fha=(10, -40), nkn=(-3, -10), nft=(-1, -3), fkn=(5, -11), fft=(4, -4),
                   face='dizzy'),
    'splat': dict(hip=(0, -17), neck=(0, -30), head=(0, -30), nsh=(-3, -28), nel=(-9, -31), nha=(-12, -36),
                  fsh=(3, -28), fel=(9, -31), fha=(12, -36), nhp=(-2, -17), nkn=(-6, -10), nft=(-9, -3),
                  fhp=(2, -17), fkn=(6, -10), fft=(9, -3), ntoe=(0, 1), ftoe=(0, 1), face='dizzy',
                  order=('fleg', 'nleg', 'torso', 'farm', 'narm', 'head')),
    'tumble': dict(hip=(0, -20), neck=(0, -31), head=(0, -31), nel=(-7, -27), nha=(-5, -21),
                   fel=(7, -27), fha=(5, -21), nkn=(-6, -26), nft=(-8, -18), fkn=(6, -26), fft=(8, -18),
                   ntoe=(-1, 1), ftoe=(1, 1), face='dizzy', order=('farm', 'fleg', 'torso', 'head', 'nleg', 'narm')),
    'slide': dict(hip=(0, -12), neck=(1, -25), head=(1, -25), nsh=(-3, -23), nel=(-8, -19), nha=(-10, -14),
                  fsh=(4, -23), fel=(9, -19), fha=(11, -14), nhp=(-2, -12), nkn=(-6, -8), nft=(-10, -3),
                  fhp=(2, -12), fkn=(5, -7), fft=(3, -2), face='dizzy', blink=False,
                  order=('fleg', 'nleg', 'torso', 'farm', 'narm', 'head')),
    'down': dict(hip=(2, -6), neck=(5, -19), head=(5, -19), nsh=(1, -17), nel=(-3, -11), nha=(-6, -6),
                 fsh=(8, -17), fel=(11, -11), fha=(12, -6), nhp=(0, -6), nkn=(-7, -9), nft=(-13, -3),
                 fhp=(4, -6), fkn=(-3, -5), fft=(-9, -2), face='ko', blink=False,
                 order=('fleg', 'farm', 'torso', 'nleg', 'head', 'narm')),
    'sorry': dict(hip=(2, -6), neck=(5, -19), head=(5, -19), nsh=(1, -17), nel=(-3, -11), nha=(-6, -6),
                  fsh=(8, -17), fel=(11, -11), fha=(12, -6), nhp=(0, -6), nkn=(-7, -9), nft=(-13, -3),
                  fhp=(4, -6), fkn=(-3, -5), fft=(-9, -2), face='grin',
                  order=('fleg', 'farm', 'torso', 'nleg', 'head', 'narm')),
}


# ----------------------------------------------------------------------------
# Pixel fonts (hand-made 5x7 and 3x5)
# ----------------------------------------------------------------------------
def _font(src):
    out = {}
    for ch, rows in src.items():
        out[ch] = rows.split('/')
    return out


FONT_L = _font({
    'A': '.###./#...#/#...#/#####/#...#/#...#/#...#', 'B': '####./#...#/#...#/####./#...#/#...#/####.',
    'C': '.###./#...#/#..../#..../#..../#...#/.###.', 'D': '####./#...#/#...#/#...#/#...#/#...#/####.',
    'E': '#####/#..../#..../####./#..../#..../#####', 'F': '#####/#..../#..../####./#..../#..../#....',
    'G': '.###./#...#/#..../#.###/#...#/#...#/.####', 'H': '#...#/#...#/#...#/#####/#...#/#...#/#...#',
    'I': '###/.#./.#./.#./.#./.#./###', 'J': '..###/...#./...#./...#./...#./#..#./.##..',
    'K': '#...#/#..#./#.#../##.../#.#../#..#./#...#', 'L': '#..../#..../#..../#..../#..../#..../#####',
    'M': '#...#/##.##/#.#.#/#.#.#/#...#/#...#/#...#', 'N': '#...#/#...#/##..#/#.#.#/#..##/#...#/#...#',
    'O': '.###./#...#/#...#/#...#/#...#/#...#/.###.', 'P': '####./#...#/#...#/####./#..../#..../#....',
    'Q': '.###./#...#/#...#/#...#/#.#.#/#..#./.##.#', 'R': '####./#...#/#...#/####./#.#../#..#./#...#',
    'S': '.####/#..../#..../.###./....#/....#/####.', 'T': '#####/..#../..#../..#../..#../..#../..#..',
    'U': '#...#/#...#/#...#/#...#/#...#/#...#/.###.', 'V': '#...#/#...#/#...#/#...#/#...#/.#.#./..#..',
    'W': '#...#/#...#/#...#/#.#.#/#.#.#/#.#.#/.#.#.', 'X': '#...#/#...#/.#.#./..#../.#.#./#...#/#...#',
    'Y': '#...#/#...#/.#.#./..#../..#../..#../..#..', 'Z': '#####/....#/...#./..#../.#.../#..../#####',
    '0': '.###./#...#/#..##/#.#.#/##..#/#...#/.###.', '1': '..#../.##../..#../..#../..#../..#../.###.',
    '2': '.###./#...#/....#/...#./..#../.#.../#####', '3': '#####/...#./..#../...#./....#/#...#/.###.',
    '4': '...#./..##./.#.#./#..#./#####/...#./...#.', '5': '#####/#..../####./....#/....#/#...#/.###.',
    '6': '..##./.#.../#..../####./#...#/#...#/.###.', '7': '#####/....#/...#./..#../.#.../.#.../.#...',
    '8': '.###./#...#/#...#/.###./#...#/#...#/.###.', '9': '.###./#...#/#...#/.####/....#/...#./.##..',
    ' ': '.../.../.../.../.../.../...', '!': '#/#/#/#/#/./#', '?': '.###./#...#/....#/...#./..#../...../..#..',
    '.': './././././././#', ',': '../../../../../.#/#.', ':': './././#/./#/.', "'": '#/#/./././././.',
    '-': '..../..../..../####/..../..../....', '+': '...../..#../..#../#####/..#../..#../.....',
    '=': '...../...../#####/...../#####/...../.....', '/': '....#/....#/...#./..#../.#.../#..../#....',
    '@': '.###./#...#/#.###/#.#.#/#.###/#..../.####', '&': '.##../#..#./#.#../.#.../#.#.#/#..#./.##.#',
    'x': '...../...../#...#/.#.#./..#../.#.#./#...#', '%': '##..#/##..#/...#./..#../.#.../#..##/#..##',
    '(': '.#/#./#./#./#./#./.#', ')': '#./.#/.#/.#/.#/.#/#.', '>': '#.../.#../..#./...#/..#./.#../#...',
    '<': '...#/..#./.#../#.../.#../..#./...#', '#': '.#.#./.#.#./#####/.#.#./#####/.#.#./.#.#.',
    '_': '...../...../...../...../...../...../#####', '*': '...../#.#.#/.###./#####/.###./#.#.#/.....',
    '|': '#/#/#/#/#/#/#',
})

FONT_S = _font({
    'A': '.#./#.#/###/#.#/#.#', 'B': '##./#.#/##./#.#/##.', 'C': '.##/#../#../#../.##', 'D': '##./#.#/#.#/#.#/##.',
    'E': '###/#../##./#../###', 'F': '###/#../##./#../#..', 'G': '.##/#../#.#/#.#/.##', 'H': '#.#/#.#/###/#.#/#.#',
    'I': '###/.#./.#./.#./###', 'J': '..#/..#/..#/#.#/.#.', 'K': '#.#/#.#/##./#.#/#.#', 'L': '#../#../#../#../###',
    'M': '#...#/##.##/#.#.#/#...#/#...#', 'N': '#..#/##.#/#.##/#..#/#..#', 'O': '.#./#.#/#.#/#.#/.#.',
    'P': '##./#.#/##./#../#..', 'Q': '.#./#.#/#.#/##./.##', 'R': '##./#.#/##./#.#/#.#', 'S': '.##/#../.#./..#/##.',
    'T': '###/.#./.#./.#./.#.', 'U': '#.#/#.#/#.#/#.#/###', 'V': '#.#/#.#/#.#/#.#/.#.', 'W': '#...#/#...#/#.#.#/##.##/#...#',
    'X': '#.#/#.#/.#./#.#/#.#', 'Y': '#.#/#.#/.#./.#./.#.', 'Z': '###/..#/.#./#../###',
    '0': '###/#.#/#.#/#.#/###', '1': '.#./##./.#./.#./###', '2': '##./..#/.#./#../###', '3': '##./..#/.#./..#/##.',
    '4': '#.#/#.#/###/..#/..#', '5': '###/#../##./..#/##.', '6': '.##/#../###/#.#/###', '7': '###/..#/.#./.#./.#.',
    '8': '###/#.#/###/#.#/###', '9': '###/#.#/###/..#/##.', ' ': '../../../../..', '!': '#/#/#/./#',
    '?': '##./..#/.#./.../.#.', '.': '././././#', ',': './././#/#', ':': './#/./#/.', "'": '#/#/./././',
    '-': '.../.../###/.../...', '+': '.../.#./###/.#./...', '=': '.../###/.../###/...', '/': '..#/..#/.#./#../#..',
    '%': '#.#/..#/.#./#../#.#', '>': '#../.#./..#/.#./#..', '<': '..#/.#./#../.#./..#', '(': '.#/#./#./#./.#',
    ')': '#./.#/.#/.#/#.', '@': '###/#.#/#.#/#../.##', '&': '.#./#.#/.#./#.#/.##', '_': '.../.../.../.../###',
    'x': '.../#.#/.#./#.#/...', '#': '#.#/###/#.#/###/#.#', '*': '#.#/.#./#.#/.../...',
})


def text_mask(s, font, scale=1, spacing=1):
    pixels, x = set(), 0
    for ch in s:
        g = font.get(ch) or font.get(ch.upper()) or font['?']
        w = len(g[0])
        for gy, row in enumerate(g):
            for gx, v in enumerate(row):
                if v == '#':
                    for sx in range(scale):
                        for sy in range(scale):
                            pixels.add((x + gx * scale + sx, gy * scale + sy))
        x += (w + spacing) * scale
    return pixels


def text_width(s, font, scale=1, spacing=1):
    w = sum((len((font.get(c) or font.get(c.upper()) or font['?'])[0]) + spacing) for c in s)
    return (w - spacing) * scale


def text_sprite(s, font, color, scale=1, spacing=1):
    return Sprite({p: color for p in text_mask(s, font, scale, spacing)})


def fancy_text(s, font, scale, bands, outline=INK, shadow=None, spacing=1, thick=1):
    """Arcade-style title text: banded vertical gradient + outline + drop shadow."""
    m = text_mask(s, font, scale, spacing)
    h = len(next(iter(font.values()))) * scale
    spr = Sprite()
    ring = set(m)
    for _ in range(thick):
        ring = dilate(ring, N4 + ((1, 1), (-1, -1), (1, -1), (-1, 1)))
    if shadow:
        for x, y in ring:
            spr[(x + 1, y + 1)] = shadow
            spr[(x + 1, y + 2)] = shadow
    for p in ring:
        spr[p] = outline
    for x, y in m:
        spr[(x, y)] = bands[min(len(bands) - 1, y * len(bands) // h)]
    return spr


# ----------------------------------------------------------------------------
# Animation plumbing. Every moving thing is an Actor: a list of keys
# (time, pose, x, y). Poses are toggled with stepped opacity keyframes and
# positions with stepped translate keyframes. All animations share one loop
# length, so the whole scene stays in sync forever.
# ----------------------------------------------------------------------------
class Clock:
    def __init__(self, loop, prefix='k'):
        self.loop, self.prefix, self.css, self.n = loop, prefix, [], 0

    def pct(self, t):
        v = max(0.0, min(100.0, t * 100.0 / self.loop))
        return f'{v:.3f}'.rstrip('0').rstrip('.') + '%'

    def track(self, keys, decl, timing=None):
        """keys: [(t, value)]. Returns a CSS class name, or None if nothing changes."""
        merged = []
        for t, v in sorted(keys, key=lambda k: k[0]):
            if merged and abs(merged[-1][0] - t) < 1e-6:
                merged[-1] = (t, v)
            else:
                merged.append((t, v))
        if timing is None:  # stepped: drop keys that change nothing
            merged = [k for i, k in enumerate(merged) if i == 0 or k[1] != merged[i - 1][1]]
        if len({repr(v) for _, v in merged}) <= 1:
            return None
        if merged[0][0] > 1e-6:
            merged.insert(0, (0.0, merged[-1][1]))
        name = f'{self.prefix}{self.n:x}'
        self.n += 1
        body = ''.join(f'{self.pct(t)}{{{decl(v)}}}' for t, v in merged)
        body += f'100%{{{decl(merged[-1][1])}}}'
        self.css.append(f'@keyframes {name}{{{body}}}')
        tf = f';animation-timing-function:{timing}' if timing else ''
        self.css.append(f'.{name}{{animation-name:{name}{tf}}}')
        return name

    def style(self):
        return (f'.a{{animation-duration:{self.loop}s;animation-iteration-count:infinite;'
                f'animation-timing-function:step-end}}' + ''.join(self.css) +
                '@media (prefers-reduced-motion:reduce){.a{animation:none!important}}')


def cls_attr(name):
    return f' class="a {name}"' if name else ''


def value_at(keys, t):
    keys = sorted(keys, key=lambda k: k[0])
    cur = keys[0][1]
    for kt, v in keys:
        if kt <= t + 1e-9:
            cur = v
    return cur


def opacity_el(clock, keys, markup, poster, timing=None):
    """Wrap markup in a <g> whose opacity follows keys [(t, 0..1)]."""
    cls = clock.track(keys, lambda v: f'opacity:{v}', timing)
    v = value_at(keys, poster)
    op = '' if v == 1 else f' opacity="{v}"'
    return f'<g{cls_attr(cls)}{op}>{markup}</g>'


class Actor:
    def __init__(self, clock):
        self.clock, self.keys, self.poses = clock, [], {}

    def pose(self, name, markup):
        self.poses[name] = markup
        return self

    def at(self, t, pose=..., x=None, y=None):
        lp, lx, ly = self.keys[-1][1:] if self.keys else (None, 0, 0)
        self.keys.append((t, lp if pose is ... else pose, lx if x is None else x, ly if y is None else y))
        return self

    def hide(self, t):
        return self.at(t, None)

    def last(self):
        return self.keys[-1]

    def svg(self, poster):
        keys = sorted(self.keys, key=lambda k: k[0])
        p0, x0, y0 = value_at([(t, (p, x, y)) for t, p, x, y in keys], poster)
        mv = self.clock.track([(t, (x, y)) for t, _, x, y in keys],
                              lambda v: f'transform:translate({v[0]}px,{v[1]}px)')
        kids = []
        for name, markup in self.poses.items():
            vis = [(t, int(p == name)) for t, p, _, _ in keys]
            if any(v for _, v in vis):
                kids.append(opacity_el(self.clock, vis, markup, poster))
        return f'<g{cls_attr(mv)} transform="translate({x0} {y0})">{"".join(kids)}</g>'


def sample(t0, t1, fps=30):
    n = max(1, round((t1 - t0) * fps))
    return [(t0 + (t1 - t0) * i / n, i / n) for i in range(n)]


# ----------------------------------------------------------------------------
# Effects & props
# ----------------------------------------------------------------------------
def spark_frames(kind='hit'):
    hot, main, edge = {'hit': (WHITE, YELLOW, ORANGE), 'big': (WHITE, YELLOW, CRIMSON),
                       'block': (WHITE, CYAN, SKY)}[kind]
    s = 1.45 if kind == 'big' else 1.0
    f0 = Sprite()
    paint(f0, capsule((-3, 0), (3, 0), 1.0) | capsule((0, -3), (0, 3), 1.0), main, ink=edge)
    for p in capsule((0, 0), (0, 0), 1.0):
        f0[p] = hot
    f1, rays, big_r = Sprite(), set(), round(7 * s)
    for i in range(8):
        a = i * math.pi / 4 + math.pi / 8 * (kind == 'block')
        ln = big_r if i % 2 == 0 else round(big_r * .6)
        rays |= capsule((0, 0), (round(math.cos(a) * ln), round(math.sin(a) * ln)), 1.2 if i % 2 == 0 else .8)
    paint(f1, rays, main, ink=edge)
    for p in ellipse(.5, .5, 2.6 * s, 2.6 * s):
        f1[p] = hot
    f2 = Sprite()
    for i in range(8):
        a = i * math.pi / 4 + math.pi / 8
        cx, cy = round(math.cos(a) * (big_r + 2)), round(math.sin(a) * (big_r + 2))
        for p in rect(cx, cy, 2, 2):
            f2[p] = main if i % 2 else edge
    return [f0, f1, f2]


def dust_frames():
    lt, dk = '#d9c7e6', '#8d7aa0'
    out = []
    for spread, r in ((3, 2.2), (6, 2.8), (9, 1.6)):
        f = Sprite()
        m = ellipse(-spread + .5, -2, r, r * .8) | ellipse(spread + .5, -2, r, r * .8)
        paint(f, m, lt, dk, ink=dk)
        out.append(f)
    return out


def bubble(lines, tail=None, font=FONT_S, fg=INK, bg=WHITE):
    """Speech bubble sprite; tail = ('down', x) or ('right', y)."""
    lh = len(font['A']) + 2
    w = max(text_width(ln, font) for ln in lines) + 6
    h = lh * len(lines) + 2
    body = rect(0, 0, w, h) - {(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)}
    if tail and tail[0] == 'down':
        tx = tail[1]
        body |= {(tx, h), (tx + 1, h), (tx + 2, h), (tx + 1, h + 1), (tx + 2, h + 1), (tx + 2, h + 2)}
    if tail and tail[0] == 'right':
        ty = tail[1]
        body |= {(w, ty), (w, ty + 1), (w, ty + 2), (w + 1, ty + 1), (w + 1, ty + 2), (w + 2, ty + 2)}
    spr = Sprite()
    paint(spr, body, bg)
    for i, ln in enumerate(lines):
        spr.blit(text_sprite(ln, font, fg), (w - text_width(ln, font)) // 2, 2 + i * lh)
    return spr


def guardrail():
    """A highway guardrail: the most literal LLM guardrail there is."""
    spr = Sprite()
    for px in (3, 17, 31):  # posts
        paint(spr, rect(px, 3, 3, 17), SLATE, SHADOW, light=-1)
        spr[(px + 1, 14)] = CRIMSON  # reflector
    beam = rect(1, 2, 35, 10) | rect(0, 3, 1, 8) | rect(36, 3, 1, 8)
    paint(spr, beam, METAL, METAL_D, hi=METAL_L)
    for x in range(1, 36):  # the W-profile: two ridges + grooves
        spr[(x, 4)] = METAL_L
        spr[(x, 6)] = METAL_D
        spr[(x, 7)] = METAL_D
        spr[(x, 9)] = METAL_L
    for px in (4, 18, 32):  # bolts
        spr[(px, 5)] = INK
        spr[(px, 8)] = INK
    for x in range(8, 15):  # hazard stripes
        for y in (10, 11):
            spr[(x, y)] = YELLOW if ((x + y) // 2) % 2 else INK
    for x in range(22, 29):
        for y in (10, 11):
            spr[(x, y)] = YELLOW if ((x + y) // 2) % 2 else INK
    return spr


def flame_frames(big=False):
    """Pixel flames for the top of the FIREWALL (28px wide)."""
    out = []
    for f in range(3):
        spr = Sprite()
        for x in range(28):
            hgt = (5 + 3 * math.sin(x * .9 + f * 2.1) + 2 * math.sin(x * 2.3 + f)) * (1.8 if big else 1)
            hgt = max(2, round(hgt))
            for y in range(hgt):
                c = YELLOW if y < hgt * .35 else ORANGE if y < hgt * .7 else CRIMSON
                spr[(x, -1 - y)] = c
        # flicker holes / embers
        for i in range(4):
            ex = (i * 7 + f * 3) % 28
            spr[(ex, -round(10 * (1.8 if big else 1)) - (i + f) % 3)] = ORANGE
        out.append(spr)
    return out


# ----------------------------------------------------------------------------
# Stage: synthwave sunset over a pixel skyline, neon grid floor, a server rack
# on the left and a literal FIREWALL on the right.
# ----------------------------------------------------------------------------
W, H = 320, 160
HORIZON = 112
GROUND = 144
SKY_BANDS = [(0, INK), (30, '#211d3a'), (46, '#32204b'), (60, PURPLE), (72, '#86305c'),
             (84, RED), (95, '#d65a57'), (104, ORANGE)]
WALL_X = 292


class Rng:  # tiny deterministic LCG so the art never changes between builds
    def __init__(self, seed):
        self.s = seed

    def __call__(self, n):
        self.s = (self.s * 1103515245 + 12345) & 0x7fffffff
        return self.s % n


def stage(clock, poster, defs):
    out = []
    for i, (y, c) in enumerate(SKY_BANDS):
        y2 = SKY_BANDS[i + 1][0] if i + 1 < len(SKY_BANDS) else HORIZON
        out.append(f'<rect y="{y}" width="{W}" height="{y2 - y}" fill="{c}"/>')
    for i in range(1, len(SKY_BANDS)):
        y, c = SKY_BANDS[i]
        defs.append(f'<pattern id="d{i}" width="2" height="2" patternUnits="userSpaceOnUse">'
                    f'<rect width="1" height="1" fill="{c}"/><rect x="1" y="1" width="1" height="1" fill="{c}"/></pattern>')
        out.append(f'<rect y="{y - 2}" width="{W}" height="2" fill="url(#d{i})"/>')

    # stars (a few twinkle)
    rng = Rng(7)
    stars = Sprite()
    twinkles = []
    for i in range(46):
        x, y = rng(W), 22 + rng(40)
        if i % 6 == 0:
            twinkles.append((x, y))
        else:
            stars[(x, y)] = WHITE if rng(3) == 0 else SILVER
    out.append(sprite_svg(stars))
    for i, (x, y) in enumerate(twinkles):
        star = Sprite({(x, y): WHITE, (x - 1, y): SILVER, (x + 1, y): SILVER, (x, y - 1): SILVER, (x, y + 1): SILVER})
        ph = (i * .37) % 1.0
        keys = [(0, 1)] + [(t, 0 if int((t / .45) + ph * 3) % 3 == 0 else 1) for t in [k * .45 for k in range(int(clock.loop / .45))]]
        out.append(opacity_el(clock, keys, sprite_svg(star), poster))

    # synthwave sun with slits
    sun = Sprite()
    cx, cy, r = 160, 92, 30
    sun_cols = [YELLOW, '#ffb86b', '#ffa45e', ORANGE, '#e8606b', '#d94d70']
    slits = {96: 1, 101: 2, 106: 2, 110: 3}
    for y in range(cy - r, HORIZON):
        if any(sy <= y < sy + n for sy, n in slits.items()):
            continue
        for x in range(cx - r, cx + r):
            if (x + .5 - cx) ** 2 + (y + .5 - cy) ** 2 <= r * r:
                sun[(x, y)] = sun_cols[min(len(sun_cols) - 1, (y - (cy - r)) * len(sun_cols) // (HORIZON - cy + r))]
    out.append(sprite_svg(sun))

    # clouds drifting by (the cloud architect's natural habitat)
    def cloud(w):
        c = Sprite()
        m = ellipse(w * .5, 4, w * .5, 3) | ellipse(w * .32, 2.5, w * .2, 3) | ellipse(w * .62, 1.5, w * .22, 3.5)
        m = {p for p in m if p[1] < 7}
        paint(c, m, '#f6c1d9', '#d987b3', ink='#a75a92', hi=WHITE)
        return c
    for (x0, y0, w, dx) in ((96, 72, 26, 12), (190, 32, 32, -10), (262, 58, 20, 8)):
        a = Actor(clock).pose('c', sprite_svg(cloud(w)))
        for t, u in sample(0, clock.loop, 4):
            a.at(t, 'c', round(x0 + dx * u), y0)
        out.append(a.svg(poster))

    # skyline (far + near) with windows
    far, near, far_win, near_win = Sprite(), Sprite(), Sprite(), Sprite()
    rng = Rng(42)
    x = -4
    while x < W:
        w = 10 + rng(14)
        h = 18 + rng(26)
        if 118 < x < 196:
            h = 8 + rng(10)
        for p in rect(x, HORIZON - h, w, h):
            far[p] = '#4b2350'
        for wy in range(HORIZON - h + 3, HORIZON - 2, 4):
            for wx in range(x + 2, x + w - 2, 3):
                if rng(5) == 0:
                    far_win[(wx, wy)] = '#a8506d'
        x += w + rng(3)
    x = -6
    lit = []
    while x < W:
        w = 12 + rng(16)
        h = 10 + rng(18)
        if 126 < x < 190:
            h = 4 + rng(6)
        for p in rect(x, HORIZON - h, w, h):
            near[p] = '#2a1838'
        if rng(3) == 0 and h > 14:  # rooftop antenna
            for yy in range(HORIZON - h - 5, HORIZON - h):
                near[(x + w // 2, yy)] = '#2a1838'
            near[(x + w // 2, HORIZON - h - 6)] = CRIMSON
        for wy in range(HORIZON - h + 3, HORIZON - 2, 4):
            for wx in range(x + 2, x + w - 2, 3):
                if rng(4) == 0:
                    near_win[(wx, wy)] = YELLOW if rng(3) else ORANGE
                    if rng(9) == 0:
                        lit.append((wx, wy))
        x += w + 1 + rng(4)
    out.append(sprite_svg(far) + sprite_svg(far_win))
    out.append(sprite_svg(near) + sprite_svg(near_win))
    for i, (wx, wy) in enumerate(lit[:6]):  # a few windows switching on/off
        keys = [(0, 1)] + [(1.1 + i * 1.7 + k * 5.3, (k + 1) % 2) for k in range(3) if 1.1 + i * 1.7 + k * 5.3 < clock.loop]
        out.append(opacity_el(clock, keys, f'<rect x="{wx}" y="{wy}" width="1" height="1" fill="#2a1838"/>', poster))

    # neon grid floor
    out.append(f'<rect y="{HORIZON}" width="{W}" height="{H - HORIZON}" fill="#1d1129"/>')
    floor = Sprite()
    for y in (114, 117, 121, 126, 132, 139, 147, 156):
        for x in range(W):
            floor[(x, y)] = '#5b2763'
    for k in range(-14, 15):
        xt, xb = 160 + k * 9, 160 + k * 46
        for y in range(HORIZON, H):
            u = (y - HORIZON) / (H - HORIZON)
            floor[(round(xt + (xb - xt) * u), y)] = '#5b2763'
    for x in range(W):
        floor[(x, HORIZON)] = PINK
        floor[(x, HORIZON + 1)] = '#a33b7a'
    out.append(sprite_svg(floor))

    # server rack (left)
    rack = Sprite()
    paint(rack, rect(2, 96, 18, 50), SHADOW, '#262b40', hi=SLATE)
    for y in range(100, 142, 6):
        for p in rect(4, y, 14, 4):
            rack[p] = '#202436'
        rack[(5, y + 1)] = INK
        for x in range(9, 17, 2):
            rack[(x, y + 2)] = '#3a4466'
    out.append(sprite_svg(rack))
    leds = [Sprite(), Sprite()]
    for i, y in enumerate(range(100, 142, 6)):
        for f in range(2):
            leds[f][(6, y + 1)] = LIME if (i + f) % 2 else GREEN
            leds[f][(16, y + 1)] = CYAN if (i * 3 + f) % 4 else SKY
    a = Actor(clock).pose('0', sprite_svg(leds[0])).pose('1', sprite_svg(leds[1]))
    for t, _ in sample(0, clock.loop, 3):
        a.at(t, str(round(t * 3) % 2), 0, 0)
    out.append(a.svg(poster))

    # FIREWALL (right)
    out.append(f'<rect x="{WALL_X}" y="88" width="{W - WALL_X}" height="60" fill="{RED}"/>')
    wall = Sprite()
    for y in range(88, 148):
        for x in range(WALL_X, W):
            row, col = (y - 88) // 5, x - WALL_X
            mortar = (y - 88) % 5 == 4 or (col + (4 if row % 2 else 0)) % 9 == 8
            if mortar or (y - 88) % 5 == 0:
                wall[(x, y)] = '#4a1730' if mortar else '#d0586a'
    for y in range(88, 148):
        wall[(WALL_X, y)] = INK
        wall[(WALL_X + 1, y)] = '#7a2341'
    for p in rect(WALL_X + 3, 100, 24, 15):
        wall[p] = INK
    for x in range(WALL_X + 2, WALL_X + 28):
        wall[(x, 99)] = SLATE
        wall[(x, 115)] = SLATE
    wall.blit(text_sprite('FIRE', FONT_S, YELLOW), WALL_X + 7, 102)
    wall.blit(text_sprite('WALL', FONT_S, YELLOW), WALL_X + 6, 108)
    out.append(sprite_svg(wall))
    return ''.join(out)


# ----------------------------------------------------------------------------
# The fight. Arianit vs. a hallucinating LLM. Every beat of the choreography
# is scripted below in seconds.
# ----------------------------------------------------------------------------
LOOP = 13.4
POSTER = 6.62  # the frame shown when animations are disabled


def build_fight():
    clk = Clock(LOOP)
    defs, layers, hud = [], [], []
    shake_keys = [(0, (0, 0))]

    def shake(t, amp):
        for i, (dx, dy) in enumerate(((amp, 0), (-amp, 1), (amp - 1, -1), (0, 0))):
            shake_keys.append((t + i * .04, (dx, dy)))

    shared = {}

    def ref(key, markup):
        """Define a sprite once in <defs> and reuse it with <use>."""
        if key not in shared:
            shared[key] = f'u{len(shared):x}'
            defs.append(f'<g id="{shared[key]}">{markup}</g>')
        return f'<use href="#{shared[key]}"/>'

    # ---------------- actors
    p1 = Actor(clk)
    for n, pz in P1_POSES.items():
        p1.pose(n, sprite_svg(p1_figure(pz)))
    rb = Actor(clk)
    for n, pz in R_POSES.items():
        rb.pose(n, sprite_svg(robot_figure(pz)))
    tumble = robot_figure(R_POSES['tumble'])
    for k in range(1, 4):
        rb.pose(f'tumble{k}', sprite_svg(tumble.rot90(k, 0, -22)))
    R_TUMBLE = ['tumble', 'tumble1', 'tumble2', 'tumble3']

    def idle(actor, t0, t1, x, a='idle1', b='idle2', period=.24, y=GROUND):
        t, i = t0, 0
        while t < t1 - 1e-6:
            actor.at(t, (a, b)[i % 2], x, y)
            t, i = t + period, i + 1

    sparks = [Actor(clk) for _ in range(3)]
    for sp in sparks:
        for kind in ('hit', 'big', 'block'):
            for i, f in enumerate(spark_frames(kind)):
                sp.pose(f'{kind}{i}', ref(f'spark-{kind}{i}', sprite_svg(f)))
        sp.at(0, None, 0, 0)
    spark_n = [0]

    def spark(t, x, y, kind='hit'):
        sp = sparks[spark_n[0] % len(sparks)]
        spark_n[0] += 1
        sp.at(t, f'{kind}0', x, y).at(t + .035, f'{kind}1').at(t + .1, f'{kind}2').hide(t + .16)

    dusts = [Actor(clk) for _ in range(2)]
    for d in dusts:
        for i, f in enumerate(dust_frames()):
            d.pose(f'd{i}', ref(f'dust{i}', sprite_svg(f)))
        d.at(0, None, 0, 0)
    dust_n = [0]

    def dust(t, x, y=GROUND):
        d = dusts[dust_n[0] % len(dusts)]
        dust_n[0] += 1
        d.at(t, 'd0', x, y).at(t + .06, 'd1').at(t + .14, 'd2').hide(t + .24)

    # ---------------- HP + combo bookkeeping
    hp = [(0, 126)]
    combo = [(0, 0)]

    def hit(t, x, y, dmg, kind='hit', n=None):
        spark(t, x, y, kind)
        hp.append((t, max(0, hp[-1][1] - dmg)))
        combo.append((t, n if n is not None else combo[-1][1] + 1))

    # ---------------- 0.0 - 2.1: intro
    idle(p1, 0, 3.1, 92)
    idle(rb, 0, 2.1, 228, period=.3)

    # 2.1: the robot brags
    rb.at(2.1, 'smug', 228, GROUND)
    # 3.08: ...and lobs a hallucination
    rb.at(3.08, 'throw')
    idle(rb, 3.45, 3.62, 228, period=.3)
    idle(rb, 3.62, 4.38, 228, 'huh1', 'huh2', .3)  # "?" on its screen once it bounces

    proj = Actor(clk).pose('b', sprite_svg(bubble(['2+2=5'], tail=('right', 3))))
    proj.at(0, None, 0, 0)
    for t, u in sample(3.1, 3.58):
        proj.at(t, 'b', round(182 - 39 * u), round(110 + 15 * u - 18 * u * (1 - u)))
    proj.hide(3.58)
    shards = []
    for vx, vy in ((-40, -70), (-10, -95), (30, -80), (55, -40), (-60, -30), (15, -55)):
        s_ = Actor(clk).pose('s', ref('shard', sprite_svg(paint(Sprite(), rect(0, 0, 2, 2), WHITE))))
        s_.at(0, None, 0, 0)
        for t, _ in sample(3.58, 3.95, 24):
            dt = t - 3.58
            s_.at(t, 's', round(146 + vx * dt), round(127 - vy * dt + 260 * dt * dt))
        s_.hide(3.95)
        shards.append(s_)

    # 3.1: Arianit deploys a guardrail. A literal one.
    p1.at(3.1, 'deploy', 92, GROUND)
    p1.at(3.45, 'block')
    p1.at(3.92, 'idle1')
    rail = Actor(clk).pose('g', sprite_svg(guardrail()))
    rail.at(0, None, 106, 0)
    for t, u in sample(3.18, 3.32):
        rail.at(t, 'g', 106, round(30 + (GROUND - 20 - 30) * u * u))
    rail.at(3.32, 'g', 106, GROUND - 20)
    dust(3.32, 112)
    shake(3.32, 1)
    spark(3.58, 144, 130, 'block')
    for i in range(4):
        rail.at(3.72 + i * .07, None if i % 2 == 0 else 'g')
    rail.hide(4.0)

    # 4.0: dash in
    for t, u in sample(4.02, 4.34):
        p1.at(t, ('walk1', 'walk2')[int(u * 5) % 2], round(92 + (204 - 92) * u), GROUND)
    dust(4.02, 88)

    # 4.36 - 5.1: four-hit string
    seq = [(4.36, 'jab', 204, 230), (4.56, 'cross', 206, 232), (4.76, 'jab', 208, 234), (4.96, 'kick', 210, 239)]
    for i, (t, pz, px, rx) in enumerate(seq):
        p1.at(t, pz, px, GROUND)
        p1.at(t + .14, 'idle1')
        rb.at(t + .02, 'hurt2' if pz == 'kick' else ('hurt1', 'hurt2')[i % 2], rx, GROUND)
        hit(t + .02, px + 17, GROUND - 25 + (pz == 'kick'), 10 if pz != 'kick' else 12,
            'big' if pz == 'kick' else 'hit')
    shake(4.98, 2)
    rb.at(5.2, 'hurt1', 239, GROUND)

    # 5.18: crouch, 5.32: launcher!
    p1.at(5.18, 'crouch', 218, GROUND)
    p1.at(5.32, 'upper', 220, GROUND - 4)
    p1.at(5.4, 'upper', 220, GROUND - 8)
    p1.at(5.5, 'upper', 220, GROUND - 6)
    p1.at(5.58, 'jump', 220, GROUND - 3)
    p1.at(5.64, 'crouch', 220, GROUND)
    hit(5.33, 230, GROUND - 30, 12, 'big')
    shake(5.33, 3)
    launch_t, lx0, vx, vy, g = 5.33, 239, 14, 200, 450
    for t, _ in sample(launch_t, 5.88):
        dt = t - launch_t
        pose = 'launch' if dt < .16 else R_TUMBLE[int(dt / .07) % 4]
        rb.at(t, pose, round(lx0 + vx * dt), round(GROUND - vy * dt + .5 * g * dt * dt))

    # 5.72: jump after it; 5.88 first air hit
    for t, u in sample(5.72, 5.88):
        p1.at(t, 'jump', round(220 + 8 * u), round(GROUND - 30 * (1 - (1 - u) ** 2)))
    p1.at(5.88, 'airpunch', 228, GROUND - 30)
    hit(5.9, 243, 80, 6)

    # 5.92 - 7.2: the "infinite" air juggle; physics takes a coffee break
    t, i = 5.94, 0
    while t < 7.2:
        u = (t - 5.94) / (7.2 - 5.94)
        rx = round(246 + 16 * u)
        px = rx - 23
        p1.at(t, ('airkick', 'airpunch')[i % 2], px, GROUND - 31 + (i % 2))
        rb.at(t, R_TUMBLE[i % 4], rx + (i % 2), 100 + (1 if i % 3 == 0 else 0))
        sx = rx - 6 + (i * 5) % 9
        sy = 74 + (i * 7) % 11
        spark(t + .01, sx, sy, 'big' if i % 4 == 0 else 'hit')
        hp.append((t, max(14, hp[-1][1] - 3)))
        t, i = t + .085, i + 1
    # combo counter spins like a slot machine
    for t, u in sample(5.94, 7.2, 34):
        combo.append((t, 6 + round(92 * u ** 1.4)))

    # 7.22: finisher into the FIREWALL
    p1.at(7.22, 'airkick', 247, GROUND - 32)
    hit(7.24, 266, 76, 8, 'big', n=99)
    for t, u in sample(7.24, 7.34):
        rb.at(t, 'launch', round(264 + 15 * u), round(100 + 6 * u))
    rb.at(7.34, 'splat', 279, 106)
    shake(7.34, 3)
    spark(7.36, 286, 84, 'big')
    for t, u in sample(7.3, 7.62):
        p1.at(t, 'jump', round(247 + 3 * u), round(GROUND - 32 + 32 * u * u))
    p1.at(7.62, 'crouch', 250, GROUND)
    dust(7.62, 252)
    idle(p1, 7.76, 8.86, 250)

    # 7.84: slide down the wall, 8.2 crumple
    for t, u in sample(7.84, 8.2):
        rb.at(t, 'slide', 280, round(106 + (GROUND - 106) * u * u))
    rb.at(8.2, 'down', 281, GROUND)
    dust(8.2, 276)
    hp.append((8.2, 0))
    shake(8.24, 2)
    KO = 8.3

    # 8.9: hero walks back to centre stage and celebrates
    for t, u in sample(8.86, 9.4):
        p1.at(t, ('walk1', 'walk2')[int(u * 6) % 2], round(250 - 52 * u), GROUND)
    idle(p1, 9.4, LOOP + .1, 198, 'win1', 'win2', .26)

    # 9.9: the punchline
    rb.at(9.9, 'sorry', 281, GROUND)
    rb.at(LOOP - .4, 'down')

    # ---------------- speech bubbles
    brag = Actor(clk).pose('b', sprite_svg(bubble(["I'M ALWAYS RIGHT."], tail=('down', 52))))
    brag.at(0, None, 168, 70).at(2.14, 'b').hide(3.04)
    sorry = Actor(clk).pose('b', sprite_svg(bubble(["YOU'RE ABSOLUTELY", 'RIGHT!'], tail=('down', 58))))
    sorry.at(0, None, 214, 78).at(9.94, 'b').hide(12.6)

    # ---------------- shadows under the fighters (stay on the ground when airborne)
    def shadow_for(actor, dx=0, wide=12):
        sh = Actor(clk)
        for name, rx in (('L', wide), ('M', wide - 3), ('S', wide - 6)):
            m = ellipse(.5, .5, rx, 2.2 if name == 'L' else 1.8)
            sh.pose(name, f'<path fill="#0e0816" d="{path_d(m)}"/>')
        for t, pz, x, y in sorted(actor.keys, key=lambda k: k[0]):
            hgt = GROUND - y
            sh.at(t, None if pz is None else ('L' if hgt < 12 else 'M' if hgt < 40 else 'S'), x + dx, GROUND - 1)
        return sh

    # ---------------- stage layers (inside the shake group)
    flames = Actor(clk)
    for i, f in enumerate(flame_frames()):
        flames.pose(f'f{i}', sprite_svg(f))
    for i, f in enumerate(flame_frames(True)):
        flames.pose(f'F{i}', sprite_svg(f))
    for t, _ in sample(0, LOOP, 8):
        big = 7.34 <= t < 8.3
        flames.at(t, ('F' if big else 'f') + str(round(t * 8) % 3), WALL_X, 88)

    layers.append(stage(clk, POSTER, defs))
    layers.append(flames.svg(POSTER))
    layers.append(shadow_for(rb, 0, 13).svg(POSTER))
    layers.append(shadow_for(p1, 0, 11).svg(POSTER))
    layers.append(rail.svg(POSTER))
    layers.append(rb.svg(POSTER))
    layers.append(p1.svg(POSTER))
    layers.append(proj.svg(POSTER))
    layers += [s_.svg(POSTER) for s_ in shards]
    layers += [d.svg(POSTER) for d in dusts]
    layers += [sp.svg(POSTER) for sp in sparks]
    layers.append(brag.svg(POSTER))
    layers.append(sorry.svg(POSTER))

    # ---------------- HUD
    def bar(x0, keys, side):
        inner_x, iw = x0 + 1, 126
        frame = (f'<rect x="{x0 - 1}" y="6" width="130" height="11" fill="{SLATE}"/>'
                 f'<rect x="{x0}" y="7" width="128" height="9" fill="{INK}"/>'
                 f'<rect x="{inner_x}" y="8" width="{iw}" height="7" fill="#3b1f2b"/>')
        defs.append(f'<clipPath id="bar{side}"><rect x="{inner_x}" y="8" width="{iw}" height="7"/></clipPath>')
        fill = (f'<rect x="{inner_x}" y="8" width="{iw}" height="7" fill="{YELLOW}"/>'
                f'<rect x="{inner_x}" y="8" width="{iw}" height="1" fill="#fff1bd"/>'
                f'<rect x="{inner_x}" y="14" width="{iw}" height="1" fill="{ORANGE}"/>')
        trail = f'<rect x="{inner_x}" y="8" width="{iw}" height="7" fill="{CRIMSON}"/>'
        sign = 1 if side == 'R' else -1

        def mover(ks, markup, timing=None):
            cls = clk.track([(t, (126 - v) * sign) for t, v in ks], lambda v: f'transform:translateX({v}px)', timing)
            v0 = (126 - value_at(ks, POSTER)) * sign
            return f'<g{cls_attr(cls)} transform="translate({v0} 0)">{markup}</g>'
        trail_keys = []
        for t, _ in sample(0, LOOP, 12):
            trail_keys.append((t, value_at(keys, t - .32)))
        return frame + f'<g clip-path="url(#bar{side})">{mover(trail_keys, trail, "linear")}{mover(keys, fill)}</g>'

    hud.append(bar(12, [(0, 126)], 'L'))
    hud.append(bar(180, hp, 'R'))
    hud.append(sprite_svg(fancy_text('ARIANIT', FONT_L, 1, [WHITE], shadow=None), ' transform="translate(12 19)"'))
    nm = 'HALLUCINATOR'
    hud.append(sprite_svg(fancy_text(nm, FONT_L, 1, [WHITE]), f' transform="translate({308 - text_width(nm, FONT_L)} 19)"'))

    def pip(on):
        s_ = Sprite()
        paint(s_, {(1, 0), (0, 1), (1, 1), (2, 1), (1, 2)} | rect(0, 0, 3, 3) - {(0, 0), (2, 0), (0, 2), (2, 2)},
              YELLOW if on else SHADOW)
        return sprite_svg(s_)
    for x in (126, 132):
        hud.append(f'<g transform="translate({x} 20)">{pip(False)}</g>')
    hud.append(f'<g transform="translate(132 20)">{opacity_el(clk, [(0, 0), (KO + 1.4, 1), (LOOP - .2, 0)], pip(True), POSTER)}</g>')
    for x in (182, 188):
        hud.append(f'<g transform="translate({x} 20)">{pip(False)}</g>')

    def digits(x, y, scale, bands, keys, lead_blank=False):
        tens, ones = Actor(clk), Actor(clk)
        for d in '0123456789':
            spr = ref(f'digit-{scale}-{bands}-{d}', sprite_svg(fancy_text(d, FONT_L, scale, bands)))
            tens.pose(d, spr)
            ones.pose(d, spr)
        dw = (5 + 1) * scale + 1
        for t, v in keys:
            if v is None:
                tens.at(t, None, x, y)
                ones.at(t, None, x + dw, y)
                continue
            tens.at(t, None if (lead_blank and v < 10) else str(v // 10), x, y)
            ones.at(t, str(v % 10), x + dw, y)
        return tens.svg(POSTER) + ones.svg(POSTER)

    # round timer: ticks once per second from FIGHT! until the K.O.
    tkeys = [(0, 60)] + [(2.0 + s, 59 - s) for s in range(0, 7) if 2.0 + s < KO]
    hud.append(digits(147, 6, 2, [WHITE, WHITE, SILVER], tkeys))

    # combo counter
    ckeys = []
    for t, n in combo:
        ckeys.append((t, n if n >= 2 else None))
    ckeys.append((KO + 1.6, None))
    hud.append(digits(10, 32, 2, ['#fff6d5', YELLOW, YELLOW, ORANGE], ckeys, lead_blank=True))
    hits = Actor(clk).pose('h', sprite_svg(fancy_text('HITS', FONT_L, 1, [WHITE, CYAN])))
    hits.at(0, None, 37, 39)
    shown = None
    for t, n in sorted(ckeys, key=lambda k: k[0]):
        vis = n is not None
        if vis != shown:
            hits.at(t, 'h' if vis else None)
            shown = vis
    hud.append(hits.svg(POSTER))

    # move-name callouts under the combo counter
    call = Actor(clk)
    for txt in ('GUARDRAIL!', 'RAG UPPERCUT!', 'INFINITE JUGGLE?!', 'FIREWALL SPLAT!'):
        call.pose(txt, sprite_svg(fancy_text(txt, FONT_L, 1, [WHITE, YELLOW])))
    call.at(0, None, 11, 52)
    call.at(3.32, 'GUARDRAIL!').hide(4.3)
    call.at(5.33, 'RAG UPPERCUT!').at(6.3, 'INFINITE JUGGLE?!').at(7.34, 'FIREWALL SPLAT!').hide(8.3)
    hud.append(call.svg(POSTER))

    # announcer
    def announce(txt, scale, bands, t0, t1, cy, blink=True):
        a = Actor(clk)
        big = fancy_text(txt, FONT_L, scale + 1, bands, shadow=PURPLE)
        nrm = fancy_text(txt, FONT_L, scale, bands, shadow=PURPLE)
        a.pose('B', sprite_svg(big)).pose('N', sprite_svg(nrm))
        bw, nw = text_width(txt, FONT_L, scale + 1), text_width(txt, FONT_L, scale)
        bh, nh = 7 * (scale + 1), 7 * scale
        a.at(0, None, 0, 0)
        a.at(t0, 'B', 160 - bw // 2, cy - bh // 2)
        a.at(t0 + .07, 'N', 160 - nw // 2, cy - nh // 2)
        if blink:
            for k in range(3):
                a.at(t1 - .3 + k * .1, None if k % 2 == 0 else 'N')
        a.hide(t1)
        return a.svg(POSTER)

    hud.append(announce('ROUND 1', 3, ['#fff6d5', YELLOW, YELLOW, '#ffa94d', ORANGE], .3, 1.3, 58))
    hud.append(announce('FIGHT!', 4, [YELLOW, '#ffa94d', ORANGE, CRIMSON, CRIMSON], 1.4, 2.05, 58, blink=False))
    hud.append(announce('K.O.', 6, [WHITE, '#ffd0d0', '#ff6b6b', CRIMSON, CRIMSON_D], KO, KO + 1.45, 60))
    hud.append(announce('PERFECT', 3, [WHITE, CYAN, CYAN, SKY, BLUE], KO + 1.5, KO + 2.7, 52))
    hud.append(announce('ARIANIT WINS', 2, ['#fff6d5', YELLOW, YELLOW, ORANGE], KO + 2.8, LOOP - .55, 52, blink=False))

    # ---------------- flashes + fade in/out (stepped, like an old arcade board)
    flash = opacity_el(clk, [(0, 0), (KO, .85), (KO + .05, .45), (KO + .1, 0)],
                       f'<rect width="{W}" height="{H}" fill="{WHITE}"/>', POSTER)
    fade = opacity_el(clk, [(0, 1), (.1, .66), (.2, .33), (.3, 0),
                            (LOOP - .5, .33), (LOOP - .4, .66), (LOOP - .3, 1)],
                      f'<rect width="{W}" height="{H}" fill="{INK}"/>', POSTER)

    shake_cls = clk.track(shake_keys, lambda v: f'transform:translate({v[0]}px,{v[1]}px)')
    body = (f'<defs>{"".join(defs)}</defs>'
            f'<g{cls_attr(shake_cls)}>{"".join(layers)}</g>'
            f'{"".join(hud)}{flash}{fade}'
            f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" fill="none" stroke="{INK}"/>')
    title = 'Pixel-art fighting game: Arianit vs. a hallucinating LLM robot'
    return svg_doc(W, H, body, css=clk.style(), title=title)


# ----------------------------------------------------------------------------
# Shared bits for the smaller panels (title screen + footer)
# ----------------------------------------------------------------------------
def night_sky(clock, w, h, horizon, poster, pid, seed=3, stars=40, star_top=0):
    """Dithered night sky, twinkling stars and a neon grid floor below `horizon`."""
    out, defs = [], []
    bands = [(0, INK), (round(horizon * .55), '#211d3a'), (round(horizon * .78), '#32204b'),
             (round(horizon * .92), PURPLE)]
    for i, (y, c) in enumerate(bands):
        y2 = bands[i + 1][0] if i + 1 < len(bands) else horizon
        out.append(f'<rect y="{y}" width="{w}" height="{y2 - y}" fill="{c}"/>')
        if i:
            defs.append(f'<pattern id="{pid}{i}" width="2" height="2" patternUnits="userSpaceOnUse">'
                        f'<rect width="1" height="1" fill="{c}"/><rect x="1" y="1" width="1" height="1" fill="{c}"/></pattern>')
            out.append(f'<rect y="{y - 2}" width="{w}" height="2" fill="url(#{pid}{i})"/>')
    rng = Rng(seed)
    still = Sprite()
    for i in range(stars):
        x, y = rng(w), star_top + rng(max(1, horizon - 8 - star_top))
        if i % 5 == 0:
            star = Sprite({(x, y): WHITE, (x - 1, y): SILVER, (x + 1, y): SILVER, (x, y - 1): SILVER, (x, y + 1): SILVER})
            ph = i % 3
            keys = [(t * .4, 0 if (k + ph) % 3 == 0 else 1) for k, t in enumerate(range(int(clock.loop / .4)))]
            out.append(opacity_el(clock, keys, sprite_svg(star), poster))
        else:
            still[(x, y)] = WHITE if rng(3) == 0 else SILVER
    out.insert(len(bands) * 2 - 1, sprite_svg(still))
    out.append(f'<rect y="{horizon}" width="{w}" height="{h - horizon}" fill="#1d1129"/>')
    grid, y, step = Sprite(), horizon + 2, 2
    while y < h:
        for x in range(w):
            grid[(x, y)] = '#5b2763'
        y, step = y + step, step + 1
    for k in range(-30, 31):
        xt, xb = w / 2 + k * 9, w / 2 + k * (9 + .77 * (h - horizon))
        for y in range(horizon, h):
            u = (y - horizon) / max(1, h - horizon)
            x = round(xt + (xb - xt) * u)
            if 0 <= x < w:
                grid[(x, y)] = '#5b2763'
    for x in range(w):
        grid[(x, horizon)] = PINK
    out.append(sprite_svg(grid))
    return ''.join(out), ''.join(defs)


def triangle(color, flip=False):
    s_ = Sprite()
    for y in range(7):
        for x in range(4 - abs(3 - y)):
            s_[((3 - x) if flip else x, y)] = color
    return paint(Sprite(), set(s_), color)


# ----------------------------------------------------------------------------
# Title screen header
# ----------------------------------------------------------------------------
ROLE_LINES = [  # typed out, one after another, in the title screen's dialog box
    ('CLOUD SOLUTION ARCHITECT @ MICROSOFT', YELLOW),
    ('BUILDING WITH LLMS & GENERATIVE AI', CYAN),
    ('MLOPS | LLM GUARDRAILS | RAG', LIME),
    ('GITHUB COPILOT & MCP ENTHUSIAST', PINK),
]


def build_header():
    type_dt, erase_dt, hold, gap = .05, .015, 1.9, .3
    windows, t = [], .3
    for line, _ in ROLE_LINES:
        n = len(line)
        windows.append((t, t + n * type_dt, t + n * type_dt + hold, t + n * type_dt + hold + n * erase_dt))
        t = windows[-1][3] + gap
    loop = round(t, 2)
    clk = Clock(loop, 'h')
    w, h, horizon = 320, 90, 78
    poster = windows[0][1] + 1.15  # first line typed, cursor + 1UP + PRESS START all lit
    sky, defs = night_sky(clk, w, h, horizon, poster, 'hd', seed=11, star_top=12)
    parts = [sky]

    # shooting stars
    shoot = Actor(clk)
    streak = Sprite({(0, 0): WHITE, (1, 0): WHITE, (2, -1): SILVER, (3, -1): SILVER, (4, -1): SLATE,
                     (5, -2): SLATE, (6, -2): '#3a4466'})
    shoot.pose('s', sprite_svg(streak.flipped()))
    shoot.at(0, None, 0, 0)
    for t0, x0, y0 in ((2.6, 230, 10), (loop * .6, 120, 6)):
        for t, u in sample(t0, t0 + .5, 24):
            shoot.at(t, 's', round(x0 - 70 * u), round(y0 + 18 * u))
        shoot.hide(t0 + .5)
    parts.append(shoot.svg(poster))

    # little clouds drifting
    for (x0, y0, cw, dx) in ((14, 56, 22, 6), (284, 54, 24, -6)):
        cl = Sprite()
        m = ellipse(cw * .5, 4, cw * .5, 3) | ellipse(cw * .32, 2.5, cw * .2, 3) | ellipse(cw * .62, 1.5, cw * .22, 3.5)
        paint(cl, {p for p in m if p[1] < 7}, '#c9a3d6', '#9a74b3', ink='#5d3d7a', hi='#e8d0f0')
        a = Actor(clk).pose('c', sprite_svg(cl))
        for t, u in sample(0, loop, 2):
            a.at(t, 'c', round(x0 + dx * math.sin(u * math.tau * 2)), y0)
        parts.append(a.svg(poster))

    # arcade score line
    top = Sprite()
    hs, score = 'HI-SCORE', '999999'
    hx = 160 - (text_width(hs, FONT_S) + 4 + text_width(score, FONT_S)) // 2
    top.blit(text_sprite('001337', FONT_S, WHITE), 24, 4)
    top.blit(text_sprite(hs, FONT_S, CRIMSON), hx, 4).blit(text_sprite(score, FONT_S, WHITE), hx + text_width(hs, FONT_S) + 4, 4)
    cr = 'CREDIT 99'
    top.blit(text_sprite(cr, FONT_S, WHITE), 312 - text_width(cr, FONT_S), 4)
    parts.append(sprite_svg(top))
    blink = [(k * .4, int(k % 2 == 0)) for k in range(int(loop / .4))]
    parts.append(opacity_el(clk, blink, sprite_svg(text_sprite('1UP', FONT_S, CRIMSON), ' transform="translate(8 4)"'), poster))

    # title + shine sweep
    title = "HEY, I'M ARIANIT"
    tw = text_width(title, FONT_L, 3)
    tx, ty = 160 - tw // 2, 17
    bands = ['#fff6d5', YELLOW, YELLOW, '#ffa94d', ORANGE, '#e8606b']
    parts.append(sprite_svg(fancy_text(title, FONT_L, 3, bands, shadow=PURPLE), f' transform="translate({tx} {ty})"'))
    glyphs = text_mask(title, FONT_L, 3)
    defs += f'<clipPath id="tclip"><path transform="translate({tx} {ty})" d="{path_d(glyphs)}"/></clipPath>'
    band = Sprite()
    for y in range(-2, 24):
        for x in range(0, 5):
            band[(x - y // 2, y)] = WHITE
    shine = Actor(clk).pose('s', sprite_svg(band))
    shine.at(0, None, 0, ty)
    for t0 in (.6, loop / 2):
        for t, u in sample(t0, t0 + .7, 20):
            shine.at(t, 's', round(tx - 10 + (tw + 24) * u), ty)
        shine.hide(t0 + .7)
    parts.append(f'<g clip-path="url(#tclip)" opacity=".75">{shine.svg(poster)}</g>')

    # RPG-style dialog box that types out the role lines
    widest = max(text_width(line, FONT_L) for line, _ in ROLE_LINES)
    bw, by, bh = widest + 18, 45, 15
    bx = 160 - bw // 2
    parts.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" fill="{SLATE}"/>'
                 f'<rect x="{bx + 1}" y="{by + 1}" width="{bw - 2}" height="{bh - 2}" fill="{INK}"/>')
    defs += f'<clipPath id="dclip"><rect x="{bx + 2}" y="{by + 2}" width="{bw - 4}" height="{bh - 4}"/></clipPath>'
    text_y = by + 4
    lines = Actor(clk)
    curtain = Actor(clk).pose('c', f'<rect width="{bw}" height="9" fill="{INK}"/>')
    cursor = Actor(clk).pose('c', f'<rect width="4" height="7" fill="{WHITE}"/>')
    lines.at(0, None, 0, text_y)
    curtain.at(0, 'c', bx, text_y - 1)
    cursor.at(0, None, bx, text_y)
    for i, ((line, col), (t0, t1, t2, t3)) in enumerate(zip(ROLE_LINES, windows)):
        lx = 160 - text_width(line, FONT_L) // 2
        lines.pose(str(i), sprite_svg(text_sprite(line, FONT_L, col)))
        lines.at(t0, str(i), lx, text_y)
        edges = [lx] + [lx + text_width(line[:k], FONT_L) + 1 for k in range(1, len(line) + 1)]
        for k, ex in enumerate(edges):
            curtain.at(t0 + k * type_dt, 'c', ex, text_y - 1)
            cursor.at(t0 + k * type_dt, 'c', ex, text_y)
        b = 0
        while t1 + b * .27 < t2:
            cursor.at(t1 + b * .27, None if b % 2 else 'c')
            b += 1
        for k, ex in enumerate(reversed(edges)):
            curtain.at(t2 + k * erase_dt, 'c', ex, text_y - 1)
            cursor.at(t2 + k * erase_dt, 'c', ex, text_y)
        lines.hide(t3)
        cursor.at(t3, 'c', lx, text_y)
    parts.append(f'<g clip-path="url(#dclip)">{lines.svg(poster)}{curtain.svg(poster)}{cursor.svg(poster)}</g>')

    ps = 'PRESS START'
    pw = text_width(ps, FONT_L)
    press = sprite_svg(fancy_text(ps, FONT_L, 1, [WHITE, WHITE, SILVER]), f' transform="translate({160 - pw // 2} 65)"')
    arrows = (sprite_svg(triangle(YELLOW), f' transform="translate({160 - pw // 2 - 10} 65)"') +
              sprite_svg(triangle(YELLOW, True), f' transform="translate({160 + pw // 2 + 6} 65)"'))
    parts.append(opacity_el(clk, [(k * .5, int(k % 2 == 0)) for k in range(int(loop / .5))], press + arrows, poster))

    body = (f'<defs>{defs}</defs>{"".join(parts)}'
            f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" fill="none" stroke="{INK}"/>')
    return svg_doc(w, h, body, css=clk.style(),
                   title="Hey, I'm Arianit! Cloud Solution Architect @ Microsoft, building with LLMs & generative AI")


# ----------------------------------------------------------------------------
# Section headings: pixel icon + chunky outlined text, transparent background
# so they work in GitHub's light and dark themes.
# ----------------------------------------------------------------------------
ICONS = {
    'player': (["..hh..", ".hssh.", ".hssh.", "..ss..", "bbbbbb", "b.bb.b", "..bb..", ".p..p."],
               {'h': HAIR, 's': SKIN, 'b': BLUE, 'p': SHADOW}),
    'joystick': ([".rrr...", "rrRrr..", ".rrr...", "..s....", "..s....", "kkkkkkk", "kYkkkGk", "kkkkkkk"],
                 {'r': CRIMSON, 'R': WHITE, 's': SILVER, 'k': SHADOW, 'Y': YELLOW, 'G': LIME}),
    'flag': (["pfff....", "pffffff.", "pfFffff.", "pffffff.", "p...fff.", "p.......", "p.......", "pp......"],
             {'p': SILVER, 'f': CRIMSON, 'F': WHITE}),
    'trophy': (["y.yyyy.y", "y.yWyy.y", ".yyyyyy.", "..yyyy..", "...oo...", "...oo...", "..oooo..", ".bbbbbb."],
               {'y': YELLOW, 'W': WHITE, 'o': ORANGE, 'b': SHADOW}),
    'bolt': (["....yy.", "...yy..", "..yy...", ".yyyyy.", "...yy..", "..yy...", ".yy....", "yy....."],
             {'y': YELLOW}),
    'coin': (["..yyyy..", ".yYYYYy.", "yYYoYYYy", "yYYoYYYy", "yYYoYYYy", "yYYoYYYy", ".yYYYYy.", "..yyyy.."],
             {'y': ORANGE, 'Y': YELLOW, 'o': '#d98c3b'}),
}


def build_section(label, icon):
    rows, cmap = ICONS[icon]
    ico = Sprite()
    paint_bitmap(ico, from_ascii(rows, cmap))
    txt = fancy_text(label, FONT_L, 1, ['#fff6d5', YELLOW, YELLOW, '#ffa94d', ORANGE], shadow=PURPLE)
    iw = len(rows[0])
    spr = Sprite().blit(ico, 1, 1).blit(txt, iw + 6, 1)
    x0, y0, x1, y1 = spr.bbox()
    w, h = x1 + 1, max(y1 + 1, 11)
    return svg_doc(w, h, sprite_svg(spr), title=label)


# ----------------------------------------------------------------------------
# Footer: CONTINUE? countdown, then a thank-you.
# ----------------------------------------------------------------------------
def build_footer():
    loop = 14.0
    clk = Clock(loop, 'f')
    w, h, horizon = 320, 56, 44
    poster = 1.0
    sky, defs = night_sky(clk, w, h, horizon, poster, 'fd', seed=5, stars=26)
    parts = [sky]
    cont = 'CONTINUE?'
    cw = text_width(cont, FONT_L, 2)
    dw = text_width('9', FONT_L, 3)
    x0 = 160 - (cw + 8 + dw) // 2
    word = sprite_svg(fancy_text(cont, FONT_L, 2, [WHITE, '#ffd0d0', '#ff6b6b', CRIMSON], shadow=PURPLE),
                      f' transform="translate({x0} 13)"')
    num = Actor(clk)
    for d in '0123456789':
        num.pose(d, sprite_svg(fancy_text(d, FONT_L, 3, ['#fff6d5', YELLOW, ORANGE], shadow=PURPLE)))
    num.at(0, '9', x0 + cw + 8, 9)
    for i in range(10):
        num.at(i, str(9 - i))
    num.hide(10)
    parts.append(opacity_el(clk, [(0, 1), (10, 0)], word, poster))
    parts.append(num.svg(poster))
    ins = 'INSERT COIN'
    blink = [(t * .5, int(k % 2 == 0)) for k, t in enumerate(range(20))] + [(10, 0)]
    parts.append(opacity_el(clk, blink, sprite_svg(fancy_text(ins, FONT_L, 1, [CYAN, CYAN, WHITE]),
                                                   f' transform="translate({160 - text_width(ins, FONT_L) // 2} 34)"'), poster))
    thx = 'THANKS FOR PLAYING!'
    see = 'SEE YOU NEXT ROUND'
    end = (sprite_svg(fancy_text(thx, FONT_L, 2, ['#fff6d5', YELLOW, YELLOW, ORANGE], shadow=PURPLE),
                      f' transform="translate({160 - text_width(thx, FONT_L, 2) // 2} 12)"') +
           sprite_svg(fancy_text(see, FONT_L, 1, [CYAN, CYAN, WHITE]),
                      f' transform="translate({160 - text_width(see, FONT_L) // 2} 33)"'))
    parts.append(opacity_el(clk, [(0, 0), (10, 1)], end, poster))
    body = (f'<defs>{defs}</defs>{"".join(parts)}'
            f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" fill="none" stroke="{INK}"/>')
    return svg_doc(w, h, body, css=clk.style(), title='Continue? Thanks for playing!')


SECTIONS = {
    'player-1': ('PLAYER 1', 'player'),
    'move-list': ('MOVE LIST', 'joystick'),
    'stage-select': ('STAGE SELECT', 'flag'),
    'high-scores': ('HIGH SCORES', 'trophy'),
    'combo-meter': ('COMBO METER', 'bolt'),
    'continue': ('CONTINUE?', 'coin'),
}


# ----------------------------------------------------------------------------
# Live GitHub stats, drawn as an arcade high-score table and a "combo meter"
# heatmap. Needs a token: $GITHUB_TOKEN / $GH_TOKEN, or a logged-in `gh` CLI.
# Without one, the existing stats SVGs are simply left untouched.
# ----------------------------------------------------------------------------
USER = 'Ar1anit'


def fetch_stats(login=USER):
    import json
    import os
    import subprocess
    import urllib.request
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if not token:
        try:
            token = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True, timeout=15).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            token = ''
    if not token:
        print('stats: no GitHub token found, keeping the existing stats SVGs')
        return None
    query = '''query($login: String!) { user(login: $login) {
      followers { totalCount }
      repositories(ownerAffiliations: OWNER, isFork: false, first: 100, privacy: PUBLIC) {
        totalCount nodes { stargazerCount
          languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name } } } } }
      contributionsCollection { totalPullRequestContributions
        contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } } } } }'''
    req = urllib.request.Request(
        'https://api.github.com/graphql',
        data=json.dumps({'query': query, 'variables': {'login': login}}).encode(),
        headers={'Authorization': f'bearer {token}', 'User-Agent': 'pixel-profile-builder'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            user = json.load(r)['data']['user']
    except Exception as e:  # network, auth or schema trouble: never break the build
        print(f'stats: GitHub API request failed ({e}), keeping the existing stats SVGs')
        return None
    cc = user['contributionsCollection']
    days = [(d['date'], d['contributionCount'])
            for w in cc['contributionCalendar']['weeks'] for d in w['contributionDays']]
    longest = run = 0
    for _, n in days:
        run = run + 1 if n else 0
        longest = max(longest, run)
    current, tail = 0, list(reversed(days))
    if tail and tail[0][1] == 0:  # today is not over yet
        tail = tail[1:]
    for _, n in tail:
        if not n:
            break
        current += 1
    langs = {}
    for repo in user['repositories']['nodes']:
        for e in repo['languages']['edges']:
            langs[e['node']['name']] = langs.get(e['node']['name'], 0) + e['size']
    return dict(
        total=cc['contributionCalendar']['totalContributions'],
        prs=cc['totalPullRequestContributions'],
        followers=user['followers']['totalCount'],
        stars=sum(r['stargazerCount'] for r in user['repositories']['nodes']),
        repos=user['repositories']['totalCount'],
        days=days, longest=longest, current=current,
        active=sum(1 for _, n in days if n), best=max((n for _, n in days), default=0),
        langs=sorted(langs.items(), key=lambda kv: -kv[1]),
    )


RANK_COLORS = [CRIMSON, ORANGE, YELLOW, LIME, CYAN, SKY]


def panel(w, h):
    return (f'<rect width="{w}" height="{h}" fill="{INK}"/>'
            f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" fill="none" stroke="{SLATE}" stroke-width="1"/>'
            f'<rect x="3" y="3" width="{w - 6}" height="{h - 6}" fill="none" stroke="{SHADOW}" stroke-width="1"/>')


def build_scores(st):
    clk = Clock(2.0, 's')
    w, h = 320, 96
    rows = [('CONTRIBUTIONS', st['total']), ('ACTIVE DAYS', st['active']), ('BEST DAY', st['best']),
            ('PULL REQUESTS', st['prs']), ('LONGEST COMBO', st['longest']), ('FOLLOWERS', st['followers'])]
    rows.sort(key=lambda r: -r[1])
    spr = Sprite()
    spr.blit(text_sprite('RANK', FONT_L, CYAN), 12, 10).blit(text_sprite('NAME', FONT_L, CYAN), 42, 10)
    spr.blit(text_sprite('SCORE', FONT_L, CYAN), 178 - text_width('SCORE', FONT_L), 10)
    first = Sprite()
    for i, (name, val) in enumerate(rows):
        col, y = RANK_COLORS[i], 23 + i * 11
        rank = ('1ST', '2ND', '3RD', '4TH', '5TH', '6TH')[i]
        (first if i == 0 else spr).blit(text_sprite(rank, FONT_L, col), 12, y)
        spr.blit(text_sprite(name, FONT_L, col), 42, y)
        score = f'{min(val, 999999):06d}'
        spr.blit(text_sprite(score, FONT_L, col), 178 - text_width(score, FONT_L), y)
    # most played languages
    spr.blit(text_sprite('MOST PLAYED', FONT_L, CYAN), 198, 10)
    total = sum(v for _, v in st['langs']) or 1
    for i, (lang, size) in enumerate(st['langs'][:4]):
        col, y = RANK_COLORS[i], 23 + i * 17
        pct = size * 100 / total
        label = lang.upper()[:10]
        spr.blit(text_sprite(label, FONT_L, WHITE), 198, y)
        p = f'{pct:.0f}%' if pct >= 1 else '<1%'
        spr.blit(text_sprite(p, FONT_L, col), 308 - text_width(p, FONT_L), y)
        cells = max(1, round(pct / 100 * 22))
        for c in range(22):
            for p_ in rect(198 + c * 5, y + 9, 4, 3):
                spr[p_] = col if c < cells else SHADOW
    body = panel(w, h) + sprite_svg(spr) + opacity_el(clk, [(0, 1), (1.0, 0)], sprite_svg(first), 0)
    return svg_doc(w, h, body, css=clk.style(), title='High scores: GitHub stats')


def build_combo(st):
    loop = 8.0
    clk = Clock(loop, 'c')
    w, h = 320, 70
    days = st['days']
    nz = sorted(n for _, n in days if n)
    q = [nz[min(len(nz) - 1, int(len(nz) * f))] for f in (.25, .5, .75)] if nz else [1, 2, 3]
    levels = ['#2a2440', PURPLE, RED, ORANGE, YELLOW]
    weeks = (len(days) + 6) // 7
    x0 = (w - (weeks * 5 - 1)) // 2
    y0 = 15
    import datetime
    first = datetime.date.fromisoformat(days[0][0])
    pad = (first.weekday() + 1) % 7  # GitHub weeks start on Sunday
    cells, months, last_month = Sprite(), Sprite(), None
    for i, (date, n) in enumerate(days):
        k = i + pad
        wk, dow = k // 7, k % 7
        lvl = 0 if n == 0 else 1 + sum(n > t for t in q)
        for p_ in rect(x0 + wk * 5, y0 + dow * 5, 4, 4):
            cells[p_] = levels[min(lvl, 4)]
        d = datetime.date.fromisoformat(date)
        if d.day <= 7 and dow == 0 and d.month != last_month and wk < weeks - 2:
            months.blit(text_sprite(d.strftime('%b').upper(), FONT_S, SILVER), x0 + wk * 5, y0 - 8)
            last_month = d.month
    stats = Sprite()
    left = f"{st['total']} HITS IN THE LAST YEAR"
    right = f"LONGEST COMBO {st['longest']}  CURRENT {st['current']}"
    stats.blit(text_sprite(left, FONT_S, YELLOW), x0, 56)
    stats.blit(text_sprite(right, FONT_S, CYAN), x0 + weeks * 5 - 1 - text_width(right, FONT_S), 56)
    legend = Sprite()
    lx = 160 - (5 * 5) // 2
    for i, c in enumerate(levels):
        for p_ in rect(lx + i * 5, 56, 4, 4):
            legend[p_] = c
    sweep = Actor(clk).pose('s', f'<rect width="3" height="{7 * 5 - 1}" fill="{WHITE}" opacity=".35"/>')
    sweep.at(0, None, x0, y0)
    for t, u in sample(.4, 2.4, 30):
        sweep.at(t, 's', x0 + round((weeks * 5 - 3) * u), y0)
    sweep.hide(2.4)
    body = (panel(w, h) + sprite_svg(cells) + sprite_svg(months) + sprite_svg(stats) + sprite_svg(legend)
            + sweep.svg(3.0))
    return svg_doc(w, h, body, css=clk.style(), title='Combo meter: contributions in the last year')


# ----------------------------------------------------------------------------
# Review sheet (static) — handy while tweaking sprites
# ----------------------------------------------------------------------------
def build_sheet():
    cells = []
    x = 14
    for name, pose in P1_POSES.items():
        cells.append(sprite_svg(p1_figure(pose), f' transform="translate({x} 56)"'))
        cells.append(sprite_svg(text_sprite(name.upper(), FONT_S, WHITE), f' transform="translate({x - 10} 60)"'))
        x += 30
    x = 18
    for name, pose in R_POSES.items():
        cells.append(sprite_svg(robot_figure(pose), f' transform="translate({x} 126)"'))
        cells.append(sprite_svg(text_sprite(name.upper(), FONT_S, WHITE), f' transform="translate({x - 10} 130)"'))
        x += 40
    w = max(30 * len(P1_POSES), 40 * len(R_POSES)) + 20
    body = f'<rect width="{w}" height="140" fill="#3a4466"/>' + ''.join(cells)
    return svg_doc(w, 140, body)


def main():
    import sys
    if 'sheet' in sys.argv:
        pathlib.Path(sys.argv[-1]).write_text(build_sheet())
        return
    OUT.mkdir(exist_ok=True)
    files = {'fight.svg': build_fight(), 'header.svg': build_header(), 'footer.svg': build_footer()}
    for name, (label, icon) in SECTIONS.items():
        files[f'sections/{name}.svg'] = build_section(label, icon)
    (OUT / 'sections').mkdir(exist_ok=True)
    st = fetch_stats()
    if st:
        files['high-scores.svg'] = build_scores(st)
        files['combo-meter.svg'] = build_combo(st)
    for name, svg in files.items():
        (OUT / name).write_text(svg)
        print(f'assets/{name}: {len(svg) / 1024:.1f} KB')


if __name__ == '__main__':
    main()
