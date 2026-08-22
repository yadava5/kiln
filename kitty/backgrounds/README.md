# Terminal wallpaper, from real places

`oxford-topo.png` is the live kitty background: elevation contours of Oxford,
Ohio, at roughly 1:24,000 — the Four Mile Creek valley, drawn as hairlines on a
near-black ground. This file is how it was made, and how to make another one.

    python3 oxford-topo-gen.py                              # the shipped one
    PLACE=zion LAT=37.298 LON=-113.026 python3 oxford-topo-gen.py

The generator fetches its own data and caches it, so a second run is instant.

---

## Why this one worked when four others did not

Five generated backgrounds were built and rejected before this: coffee-ring
poppies, a Penrose aperiodic tiling, and three kiln textures (crazing, firebox,
reduction). All five were *procedural* — a noise function or a tiling rule,
tuned until it looked plausible. Each was rejected within a minute of going on
screen.

This one is not generated at all. Every line is a measured contour of a real
hillside, so the image has the structure of a landscape: drainage that
branches, ridges that connect, spurs that taper. No noise function produces
that, and the eye picks up the difference long before it can say why.

**The reusable lesson: when a texture keeps reading as fake, stop tuning the
generator and go find real data.** Elevation, bathymetry, star catalogues,
river networks, street grids, isobars — all of it is free and none of it needs
an account.

---

## The method, step by step

### 1. Pick a place and a zoom

Tiles are the standard slippy-map scheme. For latitude/longitude at zoom `z`:

    x = (lon + 180) / 360 * 2**z
    y = (1 - asinh(tan(radians(lat))) / pi) / 2 * 2**z

Ground resolution is `156543.03 * cos(lat) / 2**z` metres per pixel. At Oxford's
latitude, zoom 14 gives **7.4 m/px**; the script then halves the grid, landing
at 14.7 m/px — finer than a hairline can show on a 3024px canvas, and coarse
enough that pure-Python marching squares finishes in seconds.

Lower zoom means more land and fewer wrinkles. Somewhere flat gives you almost
nothing; somewhere too steep gives you a solid mat of lines. A river valley is
the sweet spot, which is why this one works.

### 2. Fetch elevation

    https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png

USGS-lineage 3DEP data, no key, no account, 8×5 tiles for a 16:10 canvas.

### 3. Decode it

Terrarium packs metres into RGB:

    metres = r * 256 + g + b / 256 - 32768

So a plain PNG decoder gives a metre-accurate height field with no GIS stack.
Oxford comes out as 210–321 m over 2048×1280 samples.

### 4. Contour with marching squares

At a 5 m interval, with every 5th line drawn brighter as an index contour —
the convention on a real topographic sheet, and the thing that stops a field of
hairlines reading as noise.

The one optimisation that matters: for each cell, compute its min and max and
test **only the levels that actually cross it** — one or two, instead of all 22.
That is what keeps this tractable without numpy.

### 5. Draw at 2× and reduce

Hairlines drawn 1px wide on a double-size canvas and resized down with LANCZOS
become clean sub-pixel lines. Drawn at final size they crawl and alias.

Colours are the two dimmest steps of the terminal palette — `#4e3828` for
hairlines, `#724a30` for index contours, on the `#17120f` ground.

### 6. Ramp the density so text stays readable

**This is the step that makes it usable rather than pretty.** A uniform field of
contours competes with prose and code everywhere on screen. The canvas is
composited against flat ground through a gradient that runs from 22% at the top
left — where text actually lives — to full strength in the bottom-right corner.

Built as a 189×123 gradient and upscaled with LANCZOS, because a per-pixel
Python loop over 5.9M pixels takes half a minute and this takes none.

### 7. Measure the contrast — do not eyeball it

The gate this one passed, against the Kiln palette:

| | measured |
|---|---|
| worst foreground contrast over the whole canvas | 5.91:1 |
| canvas area below the 4.5:1 threshold | 0.000% |
| dim-tone area below threshold | 2.050% |

Three candidates were rendered and measured; this was the best of the three.
Use `~/.claude/scripts/palmath.py` (WCAG 2, APCA, CIEDE2000, Machado CVD) —
that is the same maths `kitty-palcheck.py` runs against the palette itself.

---

## Reproducing an exact framing

`oxford-topo.png` was framed by hand before the generator could fetch its own
tiles, so centring on the coordinates gives a slightly different window on the
same valley. `TX0` / `TY0` pin a tile origin exactly:

    TX0=4331 TY0=6229 python3 oxford-topo-gen.py

The shipped PNG is committed because that hand-picked framing is not recoverable
from the coordinates alone.

## Knobs

| variable | default | what it does |
|---|---|---|
| `PLACE` | `oxford-topo` | output filename stem |
| `LAT` / `LON` | Oxford, OH | centre of the canvas |
| `ZOOM` | 14 | detail; each step doubles the resolution and halves the land |
| `TX0` / `TY0` | from lat/lon | pin an exact framing |
| `INTERVAL` | 5.0 m | contour spacing — raise it for busy terrain |
| `INDEX_EVERY` | 5 | every Nth contour drawn brighter |
| `CW` / `CH` | 3024×1964 | canvas size |

## Files

- `oxford-topo-gen.py` — the generator; fetches, decodes, contours, draws
- `oxford-topo.png` — the live wallpaper, referenced by `kitty.conf`
- `tiles/` — cached elevation tiles, regenerable, not tracked
- `aperiodic.svg`, `coffee-poppies.svg`, `kiln-*.svg`, `aperiodic-gen.py` — the
  five rejected procedural attempts, kept as a record of what did not work

The rejects are tracked as **source only**. Their rendered 3024×1964 PNGs came
to 25 MB and were deleted on 2026-08-10; nothing referenced them. Bring one back
with:

    rsvg-convert -w 3024 -h 1964 -o NAME.png NAME.svg
