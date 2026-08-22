#!/usr/bin/env python3
"""Generate the three candidate kitty backgrounds as SVG.

Everything here is computed rather than hand-drawn: a Voronoi craquelure, a
Penrose P3 deflation, and a bristle flow field. Shared vocabulary lives in
PALETTE and presence(); each candidate spends the same contrast budget in a
different way.

Gates the geometry is designed against (derived in measure.py, formulas
cross-checked against ghostty-palcheck):
  * no pixel above WCAG luminance 0.13704   -> fg #f0e5d1 stays >= 4.5:1
  * <= 1.2% of pixels above WCAG lum 0.06211 -> color8 #c0b29c stays >= 4.5:1
Paint at or below #55402e (lum 0.0562) is therefore free at any area; only
brighter paint spends budget, and the budget is one 244x244 square.

  gen.py            writes all three SVGs next to this file
"""
import math
import os
import cmath

import numpy as np
from scipy.spatial import Voronoi

W, H = 3024, 1964
OUT = os.path.dirname(os.path.abspath(__file__))

PALETTE = {
    'ground':  '#1c1613',   # Kiln background, exact — the image is seamless
    'ash':     '#241c17',
    'slip':    '#3b2c21',
    'clay':    '#4a3728',
    'sand':    '#55402e',   # ceiling of the free zone
    'glow':    '#6b4326',
    'ember':   '#9c3a22',   # brightest paint permitted; 5.5:1 for fg
    'amber':   '#8a5f24',
    'fissure': '#100c09',   # darker than ground — cracks read as depth
}

# Focus of the composition: right third, just below vertical centre. Prose and
# code run upper-left, the input box owns the bottom band; this is the gap.
FX, FY = 0.80, 0.72


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def presence(x, y):
    """0 where text lives (upper-left two thirds), 1 at the focus."""
    dx = (np.asarray(x) / W - FX) / 1.05
    dy = (np.asarray(y) / H - FY) / 0.95
    return 1.0 - smoothstep(0.10, 0.72, np.hypot(dx, dy))


def value_noise(shape, cells, rng, octaves=3):
    """Smooth 0..1 field — bilinear value noise, enough for glaze thickness."""
    out = np.zeros(shape)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        n = max(2, int(cells * 2 ** o))
        g = rng.random((n + 1, n + 1))
        yy = np.linspace(0, n, shape[0])
        xx = np.linspace(0, n, shape[1])
        y0 = np.clip(np.floor(yy).astype(int), 0, n - 1)
        x0 = np.clip(np.floor(xx).astype(int), 0, n - 1)
        fy, fx = (yy - y0)[:, None], (xx - x0)[None, :]
        fy, fx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)
        a = g[np.ix_(y0, x0)]
        b = g[np.ix_(y0, x0 + 1)]
        c = g[np.ix_(y0 + 1, x0)]
        d = g[np.ix_(y0 + 1, x0 + 1)]
        out += amp * ((a * (1 - fx) + b * fx) * (1 - fy)
                      + (c * (1 - fx) + d * fx) * fy)
        total += amp
        amp *= 0.5
    return out / total


def mix(c1, c2, t):
    """Blend two #rrggbb in sRGB space; t=0 -> c1."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return '#%02x%02x%02x' % tuple(
        int(round(a[i] + (b[i] - a[i]) * max(0.0, min(1.0, t)))) for i in range(3))


DEFS = """  <defs>
    <!-- kiln mouth: the one light source, off-canvas past the lower right -->
    <radialGradient id="mouth" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0"    stop-color="{glow}" stop-opacity="0.30"/>
      <stop offset="0.45" stop-color="{slip}" stop-opacity="0.11"/>
      <stop offset="1"    stop-color="{ash}"  stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="vig" cx="0.42" cy="0.38" r="0.78">
      <stop offset="0"    stop-color="#0e0a07" stop-opacity="0"/>
      <stop offset="0.55" stop-color="#0e0a07" stop-opacity="0"/>
      <stop offset="1"    stop-color="#0e0a07" stop-opacity="0.45"/>
    </radialGradient>
    <!-- warm kiln dust; alpha-only so it tints rather than washes out -->
    <filter id="grain">
      <feTurbulence type="fractalNoise" baseFrequency="0.85"
                    numOctaves="2" stitchTiles="stitch"/>
      <feColorMatrix values="0 0 0 0 0.82
                             0 0 0 0 0.62
                             0 0 0 0 0.34
                             0 0 0 0.045 0"/>
    </filter>
    <filter id="bloom" x="-40%" y="-40%" width="180%" height="180%">
      <feGaussianBlur stdDeviation="26"/>
    </filter>
  </defs>
""".format(**PALETTE)


def frame(body, header):
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n{header}\n'
            f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}"\n'
            f'     xmlns="http://www.w3.org/2000/svg">\n{DEFS}\n'
            f'  <rect width="{W}" height="{H}" fill="{PALETTE["ground"]}"/>\n'
            f'  <ellipse cx="{FX * W:.0f}" cy="{FY * H:.0f}" rx="{1.15 * W:.0f}"'
            f' ry="{1.05 * H:.0f}" fill="url(#mouth)"/>\n'
            f'{body}\n'
            f'  <rect width="{W}" height="{H}" fill="url(#vig)"/>\n'
            f'  <rect width="{W}" height="{H}" filter="url(#grain)"/>\n'
            f'</svg>\n')


# ── A · crackle ───────────────────────────────────────────────────────────
# Raku craquelure. An isotropic Voronoi over this canvas reads as leather, so
# the cells are grown in log-polar space around a point off the lower-right
# corner: crazing on a thrown pot follows the form, stretching tangentially
# around the axis it was turned on. The glaze is the surface, not the
# drawing — cells carry their own tint, and the fissures are darker than the
# ground so they read as depth rather than as damage.
CCX, CCY = 1.34 * W, 1.16 * H          # the axis the pot was thrown on


def _to_warp(x, y, k1, k2):
    dx, dy = x - CCX, y - CCY
    return k1 * np.log(np.hypot(dx, dy)), k2 * np.arctan2(dy, dx)


def _from_warp(u, v, k1, k2):
    # Voronoi circumcentres can land far outside the seeded box; exp() of an
    # unclamped u overflows and poisons the polygon with NaN
    r, th = np.exp(np.clip(u, -20, 20) / k1), v / k2
    return CCX + r * np.cos(th), CCY + r * np.sin(th)


def GUARD(u0, u1, v0, v1):
    """Four seeds just outside the box so every real cell comes back closed."""
    du, dv = (u1 - u0) * 0.6, (v1 - v0) * 0.6
    return [[u0 - du, v0 - dv], [u1 + du, v0 - dv],
            [u0 - du, v1 + dv], [u1 + du, v1 + dv]]


def crackle():
    rng = np.random.default_rng(20260809)
    # cells are isotropic in warp space, so k1/k2 comes out as the
    # tangential:radial aspect of the real cell — 2.5 is what crazing on a
    # thrown wall actually looks like
    k1, k2 = 1.0, 0.40
    corners = np.array([[0, 0], [W, 0], [0, H], [W, H], [W, 0.5 * H],
                        [0.5 * W, H], [0, 0.5 * H], [0.5 * W, 0]], float)
    cu, cv = _to_warp(corners[:, 0], corners[:, 1], k1, k2)
    u0, u1 = cu.min() - 0.05, cu.max() + 0.05
    v0, v1 = cv.min() - 0.03, cv.max() + 0.03

    seeds = []
    while len(seeds) < 1400:
        u = rng.uniform(u0, u1, 6000)
        v = rng.uniform(v0, v1, 6000)
        x, y = _from_warp(u, v, k1, k2)
        # crazing is finest where the fire was hottest; the cool corner where
        # the prose runs keeps a few broad plates and nothing else
        keep = rng.random(6000) < 0.22 + 0.78 * presence(x, y) ** 0.85
        seeds.extend(np.stack([u[keep], v[keep]], 1).tolist())
    wp = np.array(seeds[:1400])
    for _ in range(2):                  # Lloyd, in warp space: even crazing
        vor = Voronoi(np.vstack([wp, GUARD(u0, u1, v0, v1)]))
        moved = [vor.vertices[vor.regions[vor.point_region[i]]].mean(axis=0)
                 if vor.regions[vor.point_region[i]]
                 and -1 not in vor.regions[vor.point_region[i]] else wp[i]
                 for i in range(len(wp))]
        wp = np.array(moved)

    vor = Voronoi(np.vstack([wp, GUARD(u0, u1, v0, v1)]))
    thick = value_noise((260, 400), 3, rng, octaves=3)

    def unwarp(a):
        x, y = _from_warp(a[:, 0], a[:, 1], k1, k2)
        return np.stack([x, y], 1)

    facets, cracks, lit = [], [], []
    for i, c in enumerate(wp):
        reg = vor.regions[vor.point_region[i]]
        if not reg or -1 in reg:
            continue
        poly = unwarp(vor.vertices[reg])
        if not np.isfinite(poly).all():
            continue
        if poly[:, 0].max() < -20 or poly[:, 0].min() > W + 20:
            continue
        if poly[:, 1].max() < -20 or poly[:, 1].min() > H + 20:
            continue
        cx, cy = float(poly[:, 0].mean()), float(poly[:, 1].mean())
        m = float(presence(cx, cy))
        if m < 0.02:
            continue
        t = float(thick[int(np.clip(cy / H, 0, .999) * 260),
                        int(np.clip(cx / W, 0, .999) * 400)])
        # glaze pools where it ran thick and where the fire reached
        lvl = m ** 1.15 * (0.22 + 0.78 * t)
        fill = mix(PALETTE['ground'], PALETTE['sand'], lvl * 0.92)
        d = 'M' + 'L'.join(f'{x:.1f},{y:.1f}' for x, y in poly) + 'Z'
        facets.append(f'<path d="{d}" fill="{fill}"/>')

    seen = set()
    for v1i, v2i in vor.ridge_vertices:
        if v1i < 0 or v2i < 0:
            continue
        key = (min(v1i, v2i), max(v1i, v2i))
        if key in seen:
            continue
        seen.add(key)
        seg = unwarp(np.array([vor.vertices[v1i], vor.vertices[v2i]]))
        if not np.isfinite(seg).all():
            continue
        p, q = seg[0], seg[1]
        mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
        if not (-30 < mx < W + 30 and -30 < my < H + 30):
            continue
        if math.hypot(q[0] - p[0], q[1] - p[1]) > 460:
            continue                    # a warp-space artefact, not a crack
        m = float(presence(mx, my))
        if m < 0.03:
            continue
        # a crack wanders; one control point off the chord is the difference
        # between a fracture and a wireframe
        nx, ny = -(q[1] - p[1]), q[0] - p[0]
        nl = math.hypot(nx, ny) or 1
        bow = rng.normal(0, 0.06) * nl
        qx, qy = mx + nx / nl * bow, my + ny / nl * bow
        d = f'M{p[0]:.1f},{p[1]:.1f}Q{qx:.1f},{qy:.1f} {q[0]:.1f},{q[1]:.1f}'
        w = 1.3 + 2.8 * m
        cracks.append(f'<path d="{d}" stroke-width="{w:.1f}" '
                      f'opacity="{0.18 + 0.66 * m:.2f}"/>')
        # nearest the mouth the fissures light from underneath
        if m > 0.70 and rng.random() < 0.30:
            a = 0.22 + 0.62 * (m - 0.70) / 0.30
            lit.append(f'<path d="{d}" stroke-width="{w * 0.5:.1f}" '
                       f'opacity="{a:.2f}"/>')

    body = ('  <g>\n    ' + '\n    '.join(facets) + '\n  </g>\n'
            f'  <g fill="none" stroke="{PALETTE["fissure"]}" '
            f'stroke-linecap="round">\n    '
            + '\n    '.join(cracks) + '\n  </g>\n'
            f'  <g fill="none" stroke="{PALETTE["ember"]}" '
            f'stroke-linecap="round">\n    '
            + '\n    '.join(lit) + '\n  </g>\n')
    return frame(body, """<!-- Kiln · Crackle — craquelure in a cooling glaze.
     Computed: 1400 Lloyd-relaxed Voronoi cells grown in log-polar space
     around a point past the lower-right corner, so the crazing stretches
     tangentially the way it does on a thrown pot. Each cell is tinted by its
     own glaze thickness; boundaries are darker than the ground so they read
     as depth, and near the kiln mouth three fissures in ten are lit from
     underneath in ember. No words, no glyphs, no information.

     Emitted by gen.py (candidate set, 2026-08-09) — hand-edits to this file
     are fine, but re-running the generator will overwrite them. Regenerate
     the PNG after any edit:
       rsvg-convert -w 3024 -h 1964 -o cand-crackle.png cand-crackle.svg
     then reload kitty (ctrl+cmd+,).

     MEASURED on the real rendered pixels (PIL sweep + the WCAG 2.1 / APCA
     0.98G-4g formulas from ghostty-palcheck, diffed against the compiled
     reference over 4000 random pairs, max delta 0.0):
       foreground #f0e5d1  worst 5.35:1 WCAG / APCA Lc 71.1 — below
         4.5:1 on 0.000% of the canvas
       color8     #c0b29c  worst 3.21:1 WCAG — below 4.5:1 on 0.084% of
         the canvas (incumbent coffee-poppies: 1.187%)
     color8's APCA Lc60 ceiling is apcaY 0.0082 and the bare Kiln ground
     #1c1613 is already 0.00683, so ANY paint breaches it; that gate is
     unreachable by construction and is not tracked here. -->""")


# ── B · aperiodic ─────────────────────────────────────────────────────────
# Penrose P3 by Robinson deflation. Tilework is fired clay, and an aperiodic
# tiling never repeats — the structure earns its place instead of decorating.
# Movement comes from the glaze: it was poured from the lower right and only
# reached so far, so the same rigid lattice is wet at one end and dry at the
# other.
PHI = (1 + math.sqrt(5)) / 2


def _deflate(tris):
    out = []
    for kind, a, b, c in tris:
        if kind == 0:
            p = a + (b - a) / PHI
            out += [(0, c, p, b), (1, p, c, a)]
        else:
            q = b + (a - b) / PHI
            r = b + (c - b) / PHI
            out += [(1, r, c, a), (1, q, r, b), (0, r, q, a)]
    return out


def _rhombs(tris, cx, cy):
    """Glue each Robinson triangle to its mirror to recover the rhombs.

    Which of a triangle's three edges is the rhomb's internal diagonal
    depends on its kind, so rather than hard-coding it: an edge is a diagonal
    exactly when the two triangles sharing it close into a parallelogram.
    Everything left over is a real tile edge.
    """
    owners = {}
    tri_pts = []
    for idx, (kind, a, b, c) in enumerate(tris):
        p = [complex(a.real + cx, a.imag + cy), complex(b.real + cx, b.imag + cy),
             complex(c.real + cx, c.imag + cy)]
        tri_pts.append((kind, p))
        for i in range(3):
            u, v = p[i], p[(i + 1) % 3]
            key = tuple(sorted([(round(u.real, 2), round(u.imag, 2)),
                                (round(v.real, 2), round(v.imag, 2))]))
            owners.setdefault(key, []).append((idx, i))

    tiles, diagonals, paired = [], set(), set()
    for key, own in owners.items():
        if len(own) != 2:
            continue
        (i1, e1), (i2, e2) = own
        k1, p1 = tri_pts[i1]
        k2, p2 = tri_pts[i2]
        if k1 != k2 or i1 in paired or i2 in paired:
            continue
        shared = [complex(*key[0]), complex(*key[1])]
        r = next(z for z in p1 if abs(z - shared[0]) > 1 and abs(z - shared[1]) > 1)
        s = next(z for z in p2 if abs(z - shared[0]) > 1 and abs(z - shared[1]) > 1)
        if abs((r + s) - (shared[0] + shared[1])) > 1.0:
            continue                    # not a parallelogram: a real tile edge
        diagonals.add(key)
        paired.update((i1, i2))
        tiles.append((k1, [(shared[0].real, shared[0].imag), (r.real, r.imag),
                           (shared[1].real, shared[1].imag), (s.real, s.imag)]))
    edges = {k for k in owners if k not in diagonals}
    return tiles, edges


def aperiodic():
    rng = np.random.default_rng(31415)
    scale = 2350
    tris = []
    for i in range(10):
        b = cmath.exp((2 * i - 1) * cmath.pi * 1j / 10) * scale
        c = cmath.exp((2 * i + 1) * cmath.pi * 1j / 10) * scale
        tris.append((0, 0j, c, b) if i % 2 else (0, 0j, b, c))
    for _ in range(6):                      # rhomb edge lands near 320 px
        tris = _deflate(tris)

    cx, cy = 0.705 * W, 0.615 * H
    rhombs, edges = _rhombs(tris, cx, cy)

    strokes = []
    for u, v in edges:
        mx, my = (u[0] + v[0]) / 2, (u[1] + v[1]) / 2
        if not (-60 < mx < W + 60 and -60 < my < H + 60):
            continue
        m = float(presence(mx, my))
        if m < 0.035:
            continue
        # pressed by hand, not plotted: every edge bows a hair and the line
        # weight drifts, which is what stops a P3 reading as a CAD mesh
        nx, ny = -(v[1] - u[1]), v[0] - u[0]
        nl = math.hypot(nx, ny) or 1
        bow = rng.normal(0, 0.012) * nl
        qx, qy = mx + nx / nl * bow, my + ny / nl * bow
        w = (2.0 + 3.4 * m) * (0.8 + 0.4 * rng.random())
        strokes.append(
            f'<path d="M{u[0]:.1f},{u[1]:.1f}Q{qx:.1f},{qy:.1f} '
            f'{v[0]:.1f},{v[1]:.1f}" stroke-width="{w:.1f}" '
            f'opacity="{0.18 + 0.66 * m:.2f}"/>')

    # the pour: glaze was poured from the lower right and ran out before it
    # got across, so wetness is a smooth field — per-tile randomness here is
    # what makes a tiling read as a low-poly gradient mesh
    pour = value_noise((200, 300), 2, rng, octaves=2)
    fills, hot = [], None
    best = -1e9
    for kind, pts in rhombs:
        gx = sum(p[0] for p in pts) / 4
        gy = sum(p[1] for p in pts) / 4
        if not (-80 < gx < W + 80 and -80 < gy < H + 80):
            continue
        m = float(presence(gx, gy))
        pn = float(pour[int(np.clip(gy / H, 0, .999) * 200),
                        int(np.clip(gx / W, 0, .999) * 300)])
        wet = m ** 1.35 * (0.30 + 1.35 * pn)
        if wet > 0.30:
            d = 'M' + 'L'.join(f'{x:.1f},{y:.1f}' for x, y in pts) + 'Z'
            lvl = min(1.0, (wet - 0.30) / 0.72) ** 1.2
            fill = mix(PALETTE['ash'], PALETTE['sand'],
                       lvl * (0.62 if kind else 1.0))
            fills.append(f'<path d="{d}" fill="{fill}" opacity="0.90"/>')
        score = m + 0.25 * rng.random()
        if kind == 0 and score > best and 0.62 * W < gx < 0.88 * W \
                and 0.48 * H < gy < 0.78 * H:
            best, hot = score, (pts, gx, gy)

    # exactly one tile came out of the fire hot: the whole image's accent
    pts, gx, gy = hot
    d = 'M' + 'L'.join(f'{x:.1f},{y:.1f}' for x, y in pts) + 'Z'
    ember = (f'  <g>\n'
             f'    <path d="{d}" fill="{PALETTE["ember"]}" opacity="0.30" '
             f'filter="url(#bloom)"/>\n'
             f'    <path d="{d}" fill="{PALETTE["ember"]}"/>\n'
             f'  </g>\n')
    # its five-fold neighbours catch a little of it
    warm = []
    for kind, p2 in rhombs:
        hx = sum(p[0] for p in p2) / 4
        hy = sum(p[1] for p in p2) / 4
        r = math.hypot(hx - gx, hy - gy)
        if 1 < r < 620:
            d2 = 'M' + 'L'.join(f'{x:.1f},{y:.1f}' for x, y in p2) + 'Z'
            warm.append(f'<path d="{d2}" fill="{PALETTE["amber"]}" '
                        f'opacity="{0.30 * (1 - r / 620) ** 2:.3f}"/>')

    body = ('  <g>\n    ' + '\n    '.join(fills) + '\n  </g>\n'
            '  <g>\n    ' + '\n    '.join(warm) + '\n  </g>\n'
            + ember +
            f'  <g fill="none" stroke="{PALETTE["clay"]}" '
            f'stroke-linejoin="round" stroke-linecap="round">\n    '
            + '\n    '.join(strokes) + '\n  </g>\n')
    return frame(body, """<!-- Kiln · Aperiodic — a Penrose P3 in glazed clay.
     Computed: six Robinson deflations of a ten-triangle sun, rhomb edge ~320
     px, centred in the right third below the output. The lattice is rigid but
     the glaze is not — it was poured from the lower right, so tiles are wet
     at that end and bare line at the other, and exactly one rhomb came out of
     the fire hot. No words, no glyphs, no information.

     Emitted by gen.py (candidate set, 2026-08-09) — hand-edits to this file
     are fine, but re-running the generator will overwrite them. Regenerate
     the PNG after any edit:
       rsvg-convert -w 3024 -h 1964 -o cand-aperiodic.png cand-aperiodic.svg
     then reload kitty (ctrl+cmd+,).

     MEASURED on the real rendered pixels (PIL sweep + the WCAG 2.1 / APCA
     0.98G-4g formulas from ghostty-palcheck, diffed against the compiled
     reference over 4000 random pairs, max delta 0.0):
       foreground #f0e5d1  worst 6.23:1 WCAG / APCA Lc 74.9 — below
         4.5:1 on 0.000% of the canvas
       color8     #c0b29c  worst 3.73:1 WCAG — below 4.5:1 on 0.144% of
         the canvas (incumbent coffee-poppies: 1.187%)
     color8's APCA Lc60 ceiling is apcaY 0.0082 and the bare Kiln ground
     #1c1613 is already 0.00683, so ANY paint breaches it; that gate is
     unreachable by construction and is not tracked here. -->""")


# ── C · slip ──────────────────────────────────────────────────────────────
# The potter's decorating stroke: four loaded-brush sweeps off the lower
# right, drawn one bristle at a time so the tail breaks up the way a real dry
# brush does. Gesture, not depiction.
def _bezier(p0, p1, p2, p3, n):
    t = np.linspace(0, 1, n)[:, None]
    return ((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1
            + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3)


def slip():
    rng = np.random.default_rng(1618)
    # One committed stroke and two answers to it, all entering from the right
    # and turning back before the middle: a comma, not a swoosh across the
    # page. spine, half-width at head/tail, bristle count, ember share
    sweeps = [
        (((3140, 460), (2640, 1200), (2030, 1580), (1300, 1510)), 116, 20, 210, 0.045),
        (((3080, 1790), (2660, 1710), (2360, 1410), (2250, 950)), 64, 11, 118, 0.02),
        (((2980, 1000), (2820, 1210), (2760, 1430), (2800, 1680)), 34, 6, 58, 0.0),
    ]
    groups = []
    for spine, w0, w1, nb, hot in sweeps:
        p = _bezier(*[np.array(s, float) for s in spine], 320)
        tan = np.gradient(p, axis=0)
        nrm = np.stack([-tan[:, 1], tan[:, 0]], 1)
        nrm /= (np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-9)
        s = np.linspace(0, 1, len(p))
        half = w0 + (w1 - w0) * s ** 0.7
        body, blaze = [], []
        for k in range(nb):
            u = (k + 0.5) / nb * 2 - 1                     # -1..1 across brush
            # each hair carries a different load of slip; a uniform bank of
            # them reads as a light streak rather than as clay
            bristle_a = 0.45 + 1.15 * rng.random() ** 1.6
            wob = value_noise((1, len(p)), 5, rng, 2)[0] - 0.5
            off = u * half + wob * (10 + 34 * s)
            q = p + nrm * off[:, None]
            m = presence(q[:, 0], q[:, 1])
            # a bristle lifts off the clay in patches; more often at the tail
            alive = (value_noise((1, len(p)), 11, rng, 2)[0]
                     > 0.25 + 0.48 * s * (0.4 + 0.6 * abs(u)))
            alive &= m > 0.05
            runs, cur = [], []
            for i, ok in enumerate(alive):
                if ok:
                    cur.append(i)
                elif len(cur) > 3:
                    runs.append(cur)
                    cur = []
                else:
                    cur = []
            if len(cur) > 3:
                runs.append(cur)
            for run in runs:
                seg = q[run]
                if len(seg) < 4:
                    continue
                step = max(1, len(seg) // 14)
                d = 'M' + 'L'.join(f'{x:.1f},{y:.1f}'
                                   for x, y in seg[::step])
                mm = float(m[run].mean())
                a = ((0.10 + 0.30 * mm) * (1 - 0.42 * abs(u))
                     * (1 - 0.4 * s[run].mean()) * bristle_a)
                lw = 1.8 + 3.4 * mm * (1 - 0.5 * s[run].mean())
                tgt = (blaze if (rng.random() < hot and mm > 0.72
                                 and s[run].mean() < 0.34) else body)
                tgt.append(f'<path d="{d}" stroke-width="{lw:.1f}" '
                           f'opacity="{max(0.04, min(0.36, a)):.2f}"/>')
        groups.append((body, blaze))

    # flick: droplets thrown off the loaded end of the first stroke
    drops = []
    for _ in range(110):
        a = rng.uniform(-1.4, 0.9)
        r = rng.uniform(80, 1000)
        x = 2560 + math.cos(a) * r * 0.95
        y = 1180 - math.sin(a) * r * 0.8
        if not (0 < x < W and 0 < y < H):
            continue
        m = float(presence(x, y))
        if m < 0.25:
            continue
        rad = rng.uniform(2.0, 7.5) * (0.5 + m)
        # flecks, thrown along the direction of the flick, not round bubbles
        drops.append(f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="{rad * 1.9:.1f}" '
                     f'ry="{rad * 0.55:.1f}" '
                     f'transform="rotate({math.degrees(-a) - 20:.0f} {x:.0f} {y:.0f})" '
                     f'opacity="{0.10 + 0.22 * m:.2f}"/>')

    out = []
    for body, blaze in groups:
        out.append(f'  <g fill="none" stroke="{PALETTE["sand"]}" '
                   f'stroke-linecap="round" stroke-linejoin="round">\n    '
                   + '\n    '.join(body) + '\n  </g>')
        if blaze:
            out.append(f'  <g fill="none" stroke="{PALETTE["ember"]}" '
                       f'stroke-linecap="round">\n    '
                       + '\n    '.join(blaze) + '\n  </g>')
    out.append(f'  <g fill="{PALETTE["clay"]}">\n    '
               + '\n    '.join(drops) + '\n  </g>')
    return frame('\n'.join(out), """<!-- Kiln · Slip — the potter's stroke.
     Computed: three loaded-brush sweeps entering from the right, each drawn
     one bristle at a time (210 down to 58 of them) along a bezier spine, each
     hair carrying its own load, with lift-off noise so the stroke dries out
     into separate hairs. A handful of bristles at the loaded head run ember. No words, no glyphs, no
     information.

     Emitted by gen.py (candidate set, 2026-08-09) — hand-edits to this file
     are fine, but re-running the generator will overwrite them. Regenerate
     the PNG after any edit:
       rsvg-convert -w 3024 -h 1964 -o cand-slip.png cand-slip.svg
     then reload kitty (ctrl+cmd+,).

     MEASURED on the real rendered pixels (PIL sweep + the WCAG 2.1 / APCA
     0.98G-4g formulas from ghostty-palcheck, diffed against the compiled
     reference over 4000 random pairs, max delta 0.0):
       foreground #f0e5d1  worst 7.25:1 WCAG / APCA Lc 79.0 — below
         4.5:1 on 0.000% of the canvas
       color8     #c0b29c  worst 4.35:1 WCAG — below 4.5:1 on 0.009% of
         the canvas (incumbent coffee-poppies: 1.187%)
     color8's APCA Lc60 ceiling is apcaY 0.0082 and the bare Kiln ground
     #1c1613 is already 0.00683, so ANY paint breaches it; that gate is
     unreachable by construction and is not tracked here. -->""")


if __name__ == '__main__':
    for name, fn in (('crackle', crackle), ('aperiodic', aperiodic),
                     ('slip', slip)):
        path = os.path.join(OUT, f'cand-{name}.svg')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(fn())
        print(f'{path}  {os.path.getsize(path) / 1024:.0f} KB')
