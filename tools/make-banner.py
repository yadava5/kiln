"""Render the README banner and statusline GIFs from the REAL statusline.

    python3 tools/make-banner.py

Reuses ~/.claude/stage-preview.py for everything that matters — it runs
statusline.sh exactly as Claude Code does and paints the SGR the script itself
emitted, so if a GIF is wrong the statusline is wrong. Nothing in this file
draws a cat. The only things changed per job are the frame and the payload.

Four jobs:

  * 00-banner.gif — the live logo. The statusline run in a 45-column pane,
    which is a real geometry: the yard clamps to its minimum and the cat
    paces a short stretch instead of crossing a wide bar. The instrument row
    is stripped and the stage cropped to the 20 columns the yard occupies,
    so what remains reads as a mark, not a screenshot. Rendered at double
    cell size for a crisp half-scale display in the README.
  * statusline-live.gif — the whole strip at 128 columns, instrument row
    included: what Claude actually puts on screen, shown where the README
    explains the statusline.
  * 07-cat-idle.gif / 08-cat-busy.gif — the stage only, cropped to the left
    52 columns (the cat's yard at this width), so the idle/busy pair can sit
    side by side and still be legible.

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


def frames(sid, n, per_second, out_step, home, cols, stage_only=False):
    """Statusline lines per frame; optionally just the stage rows."""
    got, out = [], 1000
    for i in range(n):
        out += out_step
        env = dict(os.environ, HOME=home, COLUMNS=str(cols),
                   STATUSLINE_NOW=str(sp.BASE + i // per_second))
        p = subprocess.run([sp.SL], input=payload(sid, out).encode(),
                           capture_output=True, env=env)
        lines = p.stdout.decode("utf-8", "replace").split("\n")
        got.append(sp.stage(lines) if stage_only else lines)
    return got


# Key colour for transparency. Pure magenta appears nowhere in the kiln palette,
# so quantisation cannot confuse it with a cat pixel.
KEY = (255, 0, 255)


def render(fr, path, ms, cols, crop=None, size=None, pad=8, transparent=False):
    """Paint frames. crop=None trims to the widest painted column; an int is
    a fixed cell window (stable framing while the cat travels). size scales
    the cell grid; the default is stage-preview's own."""
    from PIL import Image, ImageDraw, ImageFont
    have = _covered(sp.FONT)
    if size is None:
        fnt_main, cw, ch, fsz = sp.font, sp.CW, sp.CH, sp.SIZE
    else:
        fnt_main = ImageFont.truetype(sp.FONT, size)
        cw, ch, fsz = fnt_main.getlength("M"), int(size * 1.42), size
    alt = ImageFont.truetype(FALLBACK, fsz)

    rows = max(len(f) for f in fr)
    if crop is None:
        crop = max((c + 1) for f in fr for r in f
                   for c, (chr_, _) in enumerate(sp.cells(r)[:cols])
                   if chr_ != " ")
    W = int(cw * crop) + 2 * pad
    H = ch * rows + 2 * pad
    ground = KEY if transparent else sp.GROUND
    imgs = []
    for f in fr:
        im = Image.new("RGB", (W, H), ground)
        d = ImageDraw.Draw(im)
        if transparent:
            # GIF alpha is 1-bit. An anti-aliased glyph edge is a BLEND of the
            # glyph colour and the key colour, which is neither fully keyed out
            # nor the right colour — it ships as a magenta halo around every
            # stroke. fontmode "1" renders without anti-aliasing, so every
            # pixel is either glyph or key and the 1-bit mask is exact.
            d.fontmode = "1"
        for r, line in enumerate(f):
            for c, (chr_, col) in enumerate(sp.cells(line)[:crop]):
                if chr_ == " ":
                    continue
                fnt = fnt_main if ord(chr_) in have else alt
                d.text((pad + c * cw, pad + r * ch), chr_, font=fnt, fill=col)
        imgs.append(im)
    if transparent:
        # The logo sits directly on the reader's page, not on a plate: a dark
        # rectangle behind it reads as a card floating on GitHub's background.
        # So it is painted on a key colour and that colour is made transparent.
        #
        # THE KEYING IS DONE BY IMAGEMAGICK, NOT PIL, and that is deliberate.
        # Two PIL routes were tried and both shipped a magenta block: per-frame
        # adaptive palettes make the transparency index stop meaning the key
        # after frame 1, and forcing one shared palette still did not set the
        # GIF transparency flag. `magick -transparent` does, and the result is
        # checked below rather than assumed.
        #
        # -dispose Background is REQUIRED: the cat travels, and without it each
        # frame composites over the last and the hop leaves a smear.
        import subprocess
        tmp = str(path) + ".opaque.gif"
        imgs[0].save(tmp, save_all=True, append_images=imgs[1:], duration=ms,
                     loop=0, optimize=False)
        subprocess.run(
            ["magick", tmp, "-coalesce",
             "-transparent", "#%02X%02X%02X" % KEY,
             "-set", "dispose", "Background",
             str(path)], check=True)
        pathlib.Path(tmp).unlink()
    else:
        imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=ms,
                     loop=0, optimize=True)
    return W, H, len(imgs)


if __name__ == "__main__":
    out = HERE / "docs" / "media"
    out.mkdir(parents=True, exist_ok=True)
    # (name, sid, frames, renders/s, out_step, ms, cols, stage_only, crop, size)
    jobs = [
        # the logo: a 45-column pane clamps the yard to its minimum
        ("00-banner", "bnrLogo", 90, 3, 420, 333, 45, True, 20, 52),   # transparent
        # the full strip, for the statusline section
        ("statusline-live", "bnrWork", 90, 3, 420, 333, 128, False, None, None),
        # the pair: stage only, half-strip crop, real tempos
        ("07-cat-idle", "bnrIdle", 60, 1, 0, 1000, 118, True, 52, None),
        ("08-cat-busy", "bnrBusy", 60, 3, 420, 333, 118, True, 52, None),
    ]
    for name, sid, n, per_s, step, ms, cols, st, crop, size in jobs:
        home = _sandbox_home()
        p = out / f"{name}.gif"
        fr = frames(sid, n, per_s, step, home, cols, stage_only=st)
        print(name, render(fr, p, ms, cols, crop=crop, size=size,
                           pad=24 if size else 8,
                           transparent=(name == "00-banner")), "->", p)
