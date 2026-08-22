"""Contour wallpaper from real elevation — any place on Earth, drawn as hairlines.

    python3 oxford-topo-gen.py                 # Oxford, Ohio (the shipped one)
    PLACE=zion LAT=37.298 LON=-113.026 python3 oxford-topo-gen.py

NOT A GENERATED TEXTURE, and that is the whole point of it. The lines are
USGS-lineage 3DEP elevation, fetched as Terrarium-encoded tiles from AWS and
contoured with marching squares. Nothing on the canvas is invented: the shape
of the Four Mile Creek valley is the shape of the Four Mile Creek valley. That
is why it survived when four generated patterns before it did not — a real
place has structure that no noise function produces, and the eye can tell.

IT FETCHES ITS OWN DATA. The first version read 40 tiles from a `tiles/`
directory that a human had filled by hand, and when those tiles were later
cleaned up the script became unrunnable — a generator that cannot regenerate
is a comment, not a tool. Tiles are cached per place, so a re-run costs
nothing after the first.

WHY TERRARIUM: elevation is packed into RGB as
    metres = r * 256 + g + b / 256 - 32768
so a plain PNG decoder gets you a metre-accurate height field with no GIS
stack, no API key, and no account.

CHOOSING A ZOOM. Ground resolution is 156543.03 * cos(lat) / 2**z metres per
pixel. Zoom 14 at this latitude is 7.4 m/px, which after the 2x downsample
below lands at 14.7 m/px — finer than a hairline can show at 3024px wide, and
coarse enough that the marching squares stay tractable in pure Python. Lower
zoom = more land, fewer wrinkles.
"""
import math, os, sys, urllib.request
from PIL import Image, ImageDraw, ImageFilter

S = os.path.dirname(os.path.abspath(__file__))

# ── the place ──────────────────────────────────────────────────────────────
PLACE = os.environ.get("PLACE", "oxford-topo")
LAT   = float(os.environ.get("LAT", "39.5070"))     # Oxford, Ohio
LON   = float(os.environ.get("LON", "-84.7452"))
ZOOM  = int(os.environ.get("ZOOM", "14"))
TW, TH = 8, 5                                        # tiles across, down
GW, GH = TW * 256, TH * 256
TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"

# Slippy-map tile index for a latitude/longitude, then step back half the grid
# so the place ends up in the middle of the wallpaper rather than its corner.
n = 2 ** ZOOM
cx = (LON + 180.0) / 360.0 * n
cy = (1.0 - math.asinh(math.tan(math.radians(LAT))) / math.pi) / 2.0 * n
X0, Y0 = int(cx) - TW // 2, int(cy) - TH // 2
# The shipped oxford-topo.png was framed by hand before this script could fetch
# its own tiles, so centring on the coordinates gives a slightly different
# window on the same valley. TX0/TY0 pin an exact framing once you have found
# one you like — that is the only way to reproduce a specific render bit for bit.
X0 = int(os.environ.get("TX0", X0))
Y0 = int(os.environ.get("TY0", Y0))
CACHE = f"{S}/tiles/{ZOOM}"
os.makedirs(CACHE, exist_ok=True)
print(f"{PLACE}: z{ZOOM} tiles x{X0}..{X0+TW-1} y{Y0}..{Y0+TH-1} "
      f"({156543.03 * math.cos(math.radians(LAT)) / n:.1f} m/px)")

# ── assemble the elevation grid ────────────────────────────────────────────
el = [[0.0] * GW for _ in range(GH)]
for ty in range(TH):
    for tx in range(TW):
        path = f"{CACHE}/{X0+tx}_{Y0+ty}.png"
        if not os.path.exists(path):
            url = TILE_URL.format(z=ZOOM, x=X0 + tx, y=Y0 + ty)
            with urllib.request.urlopen(url, timeout=30) as r, open(path, "wb") as fh:
                fh.write(r.read())
            print(f"  fetched {os.path.basename(path)}")
        im = Image.open(path).convert("RGB")
        px = im.load()
        for j in range(256):
            row = el[ty * 256 + j]
            base = tx * 256
            for i in range(256):
                r, g, b = px[i, j]
                row[base + i] = (r * 256 + g + b / 256.0) - 32768.0

lo = min(min(r) for r in el); hi = max(max(r) for r in el)
print(f"elevation {lo:.0f}..{hi:.0f} m over {GW}x{GH} samples")

# Downsample 2x — 14.7 m/px is finer than a hairline can show at this canvas
# size, and halving the grid quarters the marching-squares work.
DW, DH = GW // 2, GH // 2
g = [[0.0] * DW for _ in range(DH)]
for j in range(DH):
    a, b = el[j*2], el[j*2+1]
    row = g[j]
    for i in range(DW):
        i2 = i*2
        row[i] = (a[i2] + a[i2+1] + b[i2] + b[i2+1]) * 0.25

# ── marching squares ───────────────────────────────────────────────────────
# Only the levels that actually cross a cell are tested, which is what keeps
# this tractable in pure Python: ~1-2 levels per cell instead of all of them.
INTERVAL = 5.0                      # metres between contours
INDEX_EVERY = 5                     # every 5th line is an index contour
levels = []
L = math.ceil(lo / INTERVAL) * INTERVAL
while L < hi:
    levels.append(L); L += INTERVAL

segs, idx_segs = [], []
def interp(p, q, va, vb, t):
    d = vb - va
    f = 0.5 if d == 0 else (t - va) / d
    return (p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f)

for j in range(DH - 1):
    gj, gj1 = g[j], g[j + 1]
    for i in range(DW - 1):
        a, b, c, d = gj[i], gj[i+1], gj1[i+1], gj1[i]
        cmin = a if a < b else b
        if c < cmin: cmin = c
        if d < cmin: cmin = d
        cmax = a if a > b else b
        if c > cmax: cmax = c
        if d > cmax: cmax = d
        k0 = int(math.ceil(cmin / INTERVAL))
        k1 = int(math.floor(cmax / INTERVAL))
        for k in range(k0, k1 + 1):
            t = k * INTERVAL
            if t <= cmin or t > cmax:
                continue
            idxc = (1 if a > t else 0) | (2 if b > t else 0) | (4 if c > t else 0) | (8 if d > t else 0)
            if idxc == 0 or idxc == 15:
                continue
            P = (i, j); Q = (i+1, j); R = (i+1, j+1); T = (i, j+1)
            top    = interp(P, Q, a, b, t)
            right  = interp(Q, R, b, c, t)
            bottom = interp(T, R, d, c, t)
            left   = interp(P, T, a, d, t)
            pairs = {
                1:  (left, top),    2:  (top, right),   3:  (left, right),
                4:  (right, bottom),5:  None,           6:  (top, bottom),
                7:  (left, bottom), 8:  (bottom, left), 9:  (top, bottom),
                10: None,           11: (bottom, right),12: (right, left),
                13: (right, top),   14: (top, left),
            }[idxc]
            if pairs is None:      # saddle: draw both, orientation is cosmetic
                out = [(left, top), (right, bottom)] if idxc == 5 else [(top, right), (bottom, left)]
            else:
                out = [pairs]
            dest = idx_segs if (k % INDEX_EVERY == 0) else segs
            dest.extend(out)

print(f"{len(levels)} levels -> {len(segs)} hairline + {len(idx_segs)} index segments")

# ── draw ───────────────────────────────────────────────────────────────────
CW, CH = 3024, 1964
GROUND = (0x17, 0x12, 0x0f)
sx, sy = CW / (DW - 1), CH / (DH - 1)

# Supersample 2x then reduce: hairlines drawn at 1px on a 2x canvas come out as
# clean sub-pixel lines, which is what keeps them from crawling.
SS = 2
canvas = Image.new("RGB", (CW * SS, CH * SS), GROUND)
dr = ImageDraw.Draw(canvas)
for (p, q) in segs:
    dr.line([p[0]*sx*SS, p[1]*sy*SS, q[0]*sx*SS, q[1]*sy*SS], fill=(0x4e, 0x38, 0x28), width=SS)
for (p, q) in idx_segs:
    dr.line([p[0]*sx*SS, p[1]*sy*SS, q[0]*sx*SS, q[1]*sy*SS], fill=(0x72, 0x4a, 0x30), width=SS)
canvas = canvas.resize((CW, CH), Image.LANCZOS)

# A single ember: the one index contour nearest the university, lit. This is
# the only invented mark on the whole canvas, and it is one line.
# Density ramp: quiet where prose and code run (upper left two thirds), full
# strength in the dead corner. Built small and upsampled — a per-pixel Python
# loop over 5.9M pixels takes half a minute, a 189x123 gradient resized with
# LANCZOS and handed to Image.composite is instant.
ground_img = Image.new("RGB", (CW, CH), GROUND)
gw, gh = 189, 123
ramp = Image.new("L", (gw, gh)); pr = ramp.load()
for y in range(gh):
    for x in range(gw):
        t = 0.55 * (x / (gw - 1)) + 0.45 * (y / (gh - 1))
        a = 0.22 + 0.78 * (t ** 1.35)
        pr[x, y] = int(max(0.0, min(1.0, a)) * 255)
canvas = Image.composite(canvas, ground_img, ramp.resize((CW, CH), Image.LANCZOS))

out = f"{S}/{PLACE}.png"
canvas.save(out)
print(f"wrote {out}  ({os.path.getsize(out)//1024} KB)")
