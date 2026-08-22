"""Render the README banner: the REAL statusline, animating, at its real tempo.

    python3 tools/make-banner.py

Reuses ~/.claude/stage-preview.py for everything that matters — it runs
statusline.sh exactly as Claude Code does and paints the SGR the script itself
emitted, so if the banner is wrong the statusline is wrong. The only things
changed here are the frame and the payload:

  * stage-preview crops to the left 52 columns because it is previewing the CAT.
    A banner has to show what Claude actually puts on screen, so nothing is
    cropped and the instrument row above the stage is kept.
  * the payload names this project rather than $HOME.

Tempo is not a taste. Idle is 1000 ms a frame (the measured refreshInterval=1
cadence) and working is 333 ms (the ~3 fps that event-driven renders stack up
to). The banner uses the working tempo: a banner that changes once a second
reads as broken rather than alive.
"""
import importlib.util
import os
import pathlib
import subprocess
import tempfile

HERE = pathlib.Path(__file__).resolve().parent.parent
SP = pathlib.Path(os.path.expanduser("~/.claude/stage-preview.py"))
if not SP.exists():
    SP = HERE / "claude" / "stage-preview.py"

_spec = importlib.util.spec_from_file_location("stage_preview", SP)
sp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sp)

COLS = 128

# kitty falls back to another face for codepoints JetBrainsMono does not carry —
# the gauge blocks U+25B0/U+25B1 are NOT in the Nerd Font (verified with
# fontTools against every JetBrainsMono*.ttf installed). PIL does no fallback of
# its own, so without this the gauges render as tofu and the banner would show a
# defect the terminal does not have.
FALLBACK = "/System/Library/Fonts/Menlo.ttc"


def _covered(path):
    from fontTools.ttLib import TTFont
    return set(TTFont(path, fontNumber=0).getBestCmap())


def _sandbox_home():
    """Every gauge synthetic: statusline.sh derives its cache from $HOME, so a
    temp HOME means the banner cannot pick up real account usage and cannot
    touch the live cat-position state."""
    home = tempfile.mkdtemp(prefix="kiln-banner-")
    os.makedirs(os.path.join(home, ".claude", "cache"), exist_ok=True)
    return home


def payload(sid, out):
    return (
        '{"workspace":{"current_dir":"%s"},'
        '"session_id":"%s","model":{"id":"claude-opus-5","display_name":"Opus 5"},'
        '"effort":{"level":"high"},"context_window":{"used_percentage":27,'
        '"total_input_tokens":269000,"total_output_tokens":%d,'
        '"context_window_size":1000000},"rate_limits":{"five_hour":'
        '{"used_percentage":23,"resets_at":0},"seven_day":'
        '{"used_percentage":61,"resets_at":0}}}' % (HERE, sid, out)
    )


def frames(sid, n, per_second, out_step, home):
    """Full statusline lines — instrument row included, nothing stripped."""
    got, out = [], 1000
    for i in range(n):
        out += out_step
        env = dict(os.environ, HOME=home, COLUMNS=str(COLS),
                   STATUSLINE_NOW=str(sp.BASE + i // per_second))
        p = subprocess.run([sp.SL], input=payload(sid, out).encode(),
                           capture_output=True, env=env)
        got.append(p.stdout.decode("utf-8", "replace").split("\n"))
    return got


def render(fr, path, ms):
    from PIL import Image, ImageDraw, ImageFont
    have = _covered(sp.FONT)
    alt = ImageFont.truetype(FALLBACK, sp.SIZE)

    rows = max(len(f) for f in fr)
    # Crop to the widest column any frame actually paints, so the banner has no
    # dead right-hand margin.
    used = max((c + 1) for f in fr for r in f
               for c, (ch, _) in enumerate(sp.cells(r)[:COLS]) if ch != " ")
    W = int(sp.CW * used) + 16
    H = sp.CH * rows + 16
    imgs = []
    for f in fr:
        im = Image.new("RGB", (W, H), sp.GROUND)
        d = ImageDraw.Draw(im)
        for r, line in enumerate(f):
            for c, (ch, col) in enumerate(sp.cells(line)[:COLS]):
                if ch == " ":
                    continue
                fnt = sp.font if ord(ch) in have else alt
                d.text((8 + c * sp.CW, 8 + r * sp.CH), ch, font=fnt, fill=col)
        imgs.append(im)
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=ms,
                 loop=0, optimize=True)
    return W, H, len(imgs)


if __name__ == "__main__":
    out = HERE / "docs" / "media"
    out.mkdir(parents=True, exist_ok=True)
    jobs = [
        ("00-banner",  "bnrWork", 90, 3, 420, 333),   # working: 3 renders a second
        ("07-cat-idle", "bnrIdle", 60, 1,   0, 1000),  # quiet: one render a second
        ("08-cat-busy", "bnrBusy", 60, 3, 420, 333),
    ]
    home = _sandbox_home()
    for name, sid, n, per_s, step, ms in jobs:
        p = out / f"{name}.gif"
        print(name, render(frames(sid, n, per_s, step, home), p, ms), "->", p)
