"""Render the REAL statusline cat to GIFs, AT THE SPEED IT ACTUALLY RUNS.

    ~/.claude/statusline-demo.sh            both scenes
    ~/.claude/statusline-demo.sh idle       just one

TEMPO IS THE POINT OF THIS FILE, and the previous version got it wrong in a way
that quietly invalidated every design judgement made from it: frames were saved
at duration=500 ms, exactly twice the real idle rate. A cat reviewed at 2 fps
and shipped at 1 fps looks lively in the preview and dead on the screen, which
is precisely what kept happening. Idle is 1000 ms a frame — the measured
refreshInterval=1 cadence — and busy is 333 ms, the ~3 fps that event-driven
renders stack up to while Claude is working.

The second half of the same mistake was simulated time. Rendering sixty frames
in a loop takes about a second of wall clock, so everything keyed to the clock —
blinks, ear flicks, the groom cycle — collapsed into a single instant and the
preview showed a cat that never blinked. Frames are stepped through
$STATUSLINE_NOW instead, one pretend second at a time, so the GIF shows the
cycles a person would actually see.

Nothing here draws a cat. It runs ~/.claude/statusline.sh exactly as Claude Code
does, captures the bytes, parses the SGR the script itself emitted, and paints
that with the font kitty uses. If the GIF is wrong, the statusline is wrong.
"""
import os
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

SL = os.path.expanduser("~/.claude/statusline.sh")
CACHE = os.path.expanduser("~/.claude/cache")
FONT = os.path.expanduser("~/Library/Fonts/JetBrainsMonoNerdFontMono-Regular.ttf")
COLS = 118          # what the script is told the pane is
CROP = 52           # what the GIF shows — the cat lives in the left yard
SIZE = 26
BASE = 1786400000   # fixed epoch, so a rerun produces the same cat

font = ImageFont.truetype(FONT, SIZE)
CW = font.getlength("M")
CH = int(SIZE * 1.42)

GROUND = (0x17, 0x12, 0x0F)
FG = (0xF0, 0xE5, 0xD1)
PAL = {
    30: (0x53, 0x44, 0x39), 31: (0xD8, 0x62, 0x4E), 32: (0xA4, 0xCB, 0x6F),
    33: (0xEF, 0xA8, 0x4E), 34: (0x7D, 0xA6, 0xD9), 35: (0xC7, 0x82, 0xBA),
    36: (0x68, 0xBD, 0xAB), 37: (0xD3, 0xC5, 0xAE),
    90: (0x9A, 0x8F, 0x84), 91: (0xF3, 0x7F, 0x6F), 92: (0xC1, 0xE2, 0x91),
    93: (0xFE, 0xC5, 0x77), 94: (0x99, 0xC2, 0xF1), 95: (0xE4, 0xA1, 0xD3),
    96: (0x84, 0xD9, 0xC6), 97: (0xFF, 0xFF, 0xFF),
}
SGR = re.compile(r"\x1b\[([0-9;]*)m")


def cells(line):
    """[(char, colour)] for one line, honouring the SGR the script emitted."""
    out, col, dim, i = [], FG, False, 0
    for m in SGR.finditer(line):
        for ch in line[i:m.start()]:
            out.append((ch, tuple(int(v * 0.55) for v in col) if dim else col))
        for p in (m.group(1) or "0").split(";"):
            p = int(p or 0)
            if p == 0:
                col, dim = FG, False
            elif p == 2:
                dim = True
            elif p == 22:
                dim = False
            elif p in PAL:
                col = PAL[p]
        i = m.end()
    for ch in line[i:]:
        out.append((ch, tuple(int(v * 0.55) for v in col) if dim else col))
    return out


def payload(sid, out):
    return (
        '{"cwd":"%s","session_id":"%s","model":{"id":"claude-opus-5[1m]"},'
        '"effort":{"level":"high"},"context_window":{"used_percentage":34,'
        '"total_input_tokens":340000,"total_output_tokens":%d,'
        '"context_window_size":1000000},"rate_limits":{"five_hour":'
        '{"used_percentage":31,"resets_at":0},"seven_day":'
        '{"used_percentage":7,"resets_at":0}}}' % (os.path.expanduser("~"), sid, out)
    )


def run(sid, second, out):
    env = dict(os.environ, COLUMNS=str(COLS), STATUSLINE_NOW=str(second))
    p = subprocess.run([SL], input=payload(sid, out).encode(),
                       capture_output=True, env=env)
    return p.stdout.decode("utf-8", "replace").split("\n")


def fresh(sid):
    for f in (f"statusline.stage.{sid}", f"statusline.cat.{sid}"):
        try:
            os.remove(os.path.join(CACHE, f))
        except OSError:
            pass


def stage(frame_lines):
    """Just the stage rows — everything after the blank separator."""
    for i, line in enumerate(frame_lines):
        if not SGR.sub("", line).strip():
            return frame_lines[i + 1:]
    return []


def scene_idle(n=70):
    """A quiet minute: one render a second, nothing being generated."""
    sid = "gifIdle"
    fresh(sid)
    return [stage(run(sid, BASE + i, 1000)) for i in range(n)]


def scene_busy(n=60):
    """Claude working: three renders inside each second, tokens flowing."""
    sid = "gifBusy"
    fresh(sid)
    frames, out = [], 1000
    for i in range(n):
        out += 420                       # keeps the activity level up, so it trots
        frames.append(stage(run(sid, BASE + i // 3, out)))
    return frames


def render(frames, path, ms):
    rows = max(len(f) for f in frames)
    W, H = int(CW * CROP) + 16, CH * rows + 16
    imgs = []
    for f in frames:
        im = Image.new("RGB", (W, H), GROUND)
        d = ImageDraw.Draw(im)
        for r, line in enumerate(f):
            for c, (ch, col) in enumerate(cells(line)[:CROP]):
                if ch != " ":
                    d.text((8 + c * CW, 8 + r * CH), ch, font=font, fill=col)
        imgs.append(im)
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=ms,
                 loop=0, optimize=True)
    return W, H, len(imgs), ms


if __name__ == "__main__":
    OUT = os.path.expanduser("~/Downloads/stage-preview")
    os.makedirs(OUT, exist_ok=True)
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    # (name, builder, ms per frame) — the ms is the real cadence, not a taste.
    jobs = [("idle", scene_idle, 1000), ("busy", scene_busy, 333)]
    for name, fn, ms in jobs:
        if which not in ("all", name):
            continue
        p = f"{OUT}/cat-{name}.gif"
        print(f"{name}: {render(fn(), p, ms)}  -> {p}")
