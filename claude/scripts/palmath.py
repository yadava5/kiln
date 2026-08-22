"""Colour maths for the palette gates: WCAG 2.1, APCA, CIEDE2000, Machado CVD.

WHY THIS FILE EXISTS. `kitty-palcheck.py` imported all of its formulas from a
sibling `ghostty-palcheck.py`, so that there was exactly one implementation. That
sibling was deleted when Ghostty was removed from this machine on 2026-07-30, and
nothing noticed, because nothing runs the checker on a schedule. The result:
every "re-run palcheck after any edit" instruction in this setup — including the
one at the top of `themes/kiln.conf` — has been pointing at a script that dies
on import with FileNotFoundError. Found 2026-08-09 while trying to gate a palette
change; the traceback is the whole story.

This file restores the maths standalone. It has no imports beyond the standard
library and no dependency on any other terminal's tooling, so it cannot rot the
same way again.

Conventions: colours are (r, g, b) int tuples in 0..255, sRGB, non-linear.
"""

__all__ = ['hex2rgb', 'rgb2hex', 'relative_luminance', 'wcag_ratio', 'apca',
           'rgb2lab', 'ciede2000', 'cvd']

import math


# ── conversions ────────────────────────────────────────────────────────────
def hex2rgb(s):
    s = s.strip().lstrip('#')
    if len(s) == 3:
        s = ''.join(ch * 2 for ch in s)
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def rgb2hex(c):
    return '#%02x%02x%02x' % tuple(max(0, min(255, int(round(v)))) for v in c)


def _srgb_to_linear(v):
    v /= 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


# ── WCAG 2.1 ───────────────────────────────────────────────────────────────
def relative_luminance(c):
    r, g, b = (_srgb_to_linear(v) for v in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def wcag_ratio(fg, bg):
    """Contrast ratio, 1.0 .. 21.0. Symmetric: order does not matter."""
    l1, l2 = relative_luminance(fg), relative_luminance(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


# ── APCA (SAPC-APCA 0.98G-4g constants) ────────────────────────────────────
# Lc is SIGNED and NOT symmetric: apca(text, background). Positive means dark
# text on a light background, negative means light text on dark. Callers here
# always take abs(); the sign is kept because throwing it away is how people end
# up comparing a dark-mode number against a light-mode threshold.
_S_TRC = 2.4
_R_CO, _G_CO, _B_CO = 0.2126729, 0.7151522, 0.0721750
_N_BG, _N_TX = 0.56, 0.57
_R_BG, _R_TX = 0.65, 0.62
_SCALE_BOW, _SCALE_WOB = 1.14, 1.14
_LO_CLIP, _LO_OFFSET = 0.1, 0.027
_DELTA_Y_MIN = 0.0005


def _apca_y(c):
    r, g, b = ((v / 255.0) ** _S_TRC for v in c)
    return _R_CO * r + _G_CO * g + _B_CO * b


def _soft_clamp(y):
    return y if y > 0.022 else y + (0.022 - y) ** 1.414


def apca(text, bg):
    """Lightness contrast Lc, roughly -108 .. +106."""
    ytxt, ybg = _soft_clamp(_apca_y(text)), _soft_clamp(_apca_y(bg))
    if abs(ybg - ytxt) < _DELTA_Y_MIN:
        return 0.0
    if ybg > ytxt:                                   # dark text on light bg
        sapc = (ybg ** _N_BG - ytxt ** _N_TX) * _SCALE_BOW
        out = 0.0 if sapc < _LO_CLIP else sapc - _LO_OFFSET
    else:                                            # light text on dark bg
        sapc = (ybg ** _R_BG - ytxt ** _R_TX) * _SCALE_WOB
        out = 0.0 if sapc > -_LO_CLIP else sapc + _LO_OFFSET
    return out * 100.0


# ── CIE Lab + CIEDE2000 ────────────────────────────────────────────────────
_WHITE = (0.95047, 1.00000, 1.08883)          # D65, 2 degree observer


def rgb2lab(c):
    r, g, b = (_srgb_to_linear(v) for v in c)
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / _WHITE[0]
    y = (0.2126729 * r + 0.7151522 * g + 0.0721750 * b) / _WHITE[1]
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / _WHITE[2]

    def f(t):
        return t ** (1.0 / 3.0) if t > 216.0 / 24389.0 else (841.0 / 108.0) * t + 4.0 / 29.0

    fx, fy, fz = f(x), f(y), f(z)
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def ciede2000(lab1, lab2):
    """Perceptual distance dE00. Roughly: <1 invisible, ~10 clearly different,
    >20 unmistakably different hues."""
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2
    kl = kc = kh = 1.0
    c1 = math.hypot(a1, b1)
    c2 = math.hypot(a2, b2)
    cbar = (c1 + c2) / 2.0
    g = 0.5 * (1.0 - math.sqrt(cbar ** 7 / (cbar ** 7 + 25.0 ** 7))) if cbar > 0 else 0.0
    a1p, a2p = (1.0 + g) * a1, (1.0 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360.0 if (a1p or b1) else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360.0 if (a2p or b2) else 0.0

    dlp = l2 - l1
    dcp = c2p - c1p
    if c1p * c2p == 0:
        dhp = 0.0
    else:
        dh = h2p - h1p
        if dh > 180.0:
            dh -= 360.0
        elif dh < -180.0:
            dh += 360.0
        dhp = 2.0 * math.sqrt(c1p * c2p) * math.sin(math.radians(dh / 2.0))

    lbarp = (l1 + l2) / 2.0
    cbarp = (c1p + c2p) / 2.0
    if c1p * c2p == 0:
        hbarp = h1p + h2p
    else:
        d = abs(h1p - h2p)
        if d <= 180.0:
            hbarp = (h1p + h2p) / 2.0
        elif h1p + h2p < 360.0:
            hbarp = (h1p + h2p + 360.0) / 2.0
        else:
            hbarp = (h1p + h2p - 360.0) / 2.0

    t = (1.0
         - 0.17 * math.cos(math.radians(hbarp - 30.0))
         + 0.24 * math.cos(math.radians(2.0 * hbarp))
         + 0.32 * math.cos(math.radians(3.0 * hbarp + 6.0))
         - 0.20 * math.cos(math.radians(4.0 * hbarp - 63.0)))
    dtheta = 30.0 * math.exp(-(((hbarp - 275.0) / 25.0) ** 2))
    rc = 2.0 * math.sqrt(cbarp ** 7 / (cbarp ** 7 + 25.0 ** 7)) if cbarp > 0 else 0.0
    sl = 1.0 + (0.015 * (lbarp - 50.0) ** 2) / math.sqrt(20.0 + (lbarp - 50.0) ** 2)
    sc = 1.0 + 0.045 * cbarp
    sh = 1.0 + 0.015 * cbarp * t
    rt = -math.sin(math.radians(2.0 * dtheta)) * rc

    return math.sqrt(
        (dlp / (kl * sl)) ** 2
        + (dcp / (kc * sc)) ** 2
        + (dhp / (kh * sh)) ** 2
        + rt * (dcp / (kc * sc)) * (dhp / (kh * sh)))


# ── Machado, Oliveira & Fernandes (2009) CVD simulation, severity 1.0 ──────
# These are the published severity-1.0 matrices; they operate on LINEAR RGB, and
# applying them to gamma-encoded values (the easy mistake) understates the
# collapse and would let a failing red/green pair through the gate.
_CVD_M = {
    'protanopia':   ((0.152286, 1.052583, -0.204868),
                     (0.114503, 0.786281,  0.099216),
                     (-0.003882, -0.048116, 1.051998)),
    'deuteranopia': ((0.367322, 0.860646, -0.227968),
                     (0.280085, 0.672501,  0.047413),
                     (-0.011820, 0.042940, 0.968881)),
    'tritanopia':   ((1.255528, -0.076749, -0.178779),
                     (-0.078411, 0.930809,  0.147602),
                     (0.004733,  0.691367,  0.303900)),
}


def _linear_to_srgb(v):
    v = max(0.0, min(1.0, v))
    v = v * 12.92 if v <= 0.0031308 else 1.055 * (v ** (1 / 2.4)) - 0.055
    return int(round(v * 255.0))


def cvd(c, kind):
    """Simulate how `c` appears under a colour-vision deficiency."""
    m = _CVD_M[kind]
    r, g, b = (_srgb_to_linear(v) for v in c)
    return tuple(_linear_to_srgb(row[0] * r + row[1] * g + row[2] * b) for row in m)


# ── self-check ─────────────────────────────────────────────────────────────
# Run this file directly to confirm the formulas against known-good values
# before trusting any gate that depends on them. A silently wrong colour
# formula is worse than a missing one: it produces confident numbers.
if __name__ == '__main__':
    fails = 0

    def check(label, got, want, tol):
        global fails
        ok = abs(got - want) <= tol
        fails += 0 if ok else 1
        print(f'  {label:38} got {got:8.3f}  want {want:8.3f}  '
              f'{"PASS" if ok else "FAIL"}')

    print('palmath self-check')
    # WCAG: black on white is exactly 21:1; identical colours are exactly 1:1.
    check('WCAG black/white', wcag_ratio((0, 0, 0), (255, 255, 255)), 21.0, 1e-6)
    check('WCAG same colour', wcag_ratio((18, 22, 19), (18, 22, 19)), 1.0, 1e-9)
    # APCA reference pairs from the published 0.98G-4g lookup.
    # The two polarity extremes are NOT mirror images, which is the whole point
    # of APCA over WCAG: black-on-white maxes at +106.04, white-on-black at
    # -107.88. Getting these the wrong way round was the first self-check
    # failure here, and it was the expectation that was wrong, not the formula.
    check('APCA #888 on #fff', apca((0x88, 0x88, 0x88), (255, 255, 255)), 63.056, 0.2)
    check('APCA #000 on #fff', apca((0, 0, 0), (255, 255, 255)), 106.041, 0.3)
    check('APCA #fff on #000', apca((255, 255, 255), (0, 0, 0)), -107.885, 0.3)
    check('APCA sign, dark on light',
          1.0 if apca((0, 0, 0), (255, 255, 255)) > 0 else -1.0, 1.0, 0)
    # CIEDE2000: identity is zero; Sharma et al. test pair 1 is 2.0425.
    check('dE00 identity', ciede2000(rgb2lab((100, 40, 60)), rgb2lab((100, 40, 60))),
          0.0, 1e-9)
    check('dE00 Sharma pair 1',
          ciede2000((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485)),
          2.0425, 0.001)
    check('dE00 Sharma pair 9',
          ciede2000((50.0000, 2.5000, 0.0000), (50.0000, 3.1736, 0.5854)),
          1.0000, 0.001)
    # Lab: pure white is L*=100, a*=b*=0.
    lw = rgb2lab((255, 255, 255))
    check('Lab white L*', lw[0], 100.0, 0.01)
    check('Lab white a*', lw[1], 0.0, 0.01)
    # CVD: a grey is unchanged by any deficiency (no chroma to lose).
    check('deut grey unchanged', cvd((128, 128, 128), 'deuteranopia')[0], 128, 1)
    # CVD: red and green must collapse toward each other, not stay apart.
    d_normal = ciede2000(rgb2lab((212, 96, 77)), rgb2lab((168, 191, 106)))
    d_deut = ciede2000(rgb2lab(cvd((212, 96, 77), 'deuteranopia')),
                       rgb2lab(cvd((168, 191, 106), 'deuteranopia')))
    check('deut collapses red/green', 1.0 if d_deut < d_normal else 0.0, 1.0, 0)
    print(f'  {"":38} {fails} failure(s)')
    raise SystemExit(1 if fails else 0)
