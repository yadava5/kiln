"""NOT CURRENTLY LOADED — kitty.conf sets `tab_bar_style separator`.

Kept on disk on purpose. The cat that used to live in this file moved to the
Claude Code statusline on 2026-08-09, because a horizontal kitty tab bar is
exactly ONE row (`Screen(None, 1, ...)`, `s.resize(1, ncells)`) and five cells
is not a stage. This file becomes useful again the moment kitty is upgraded to
0.48+, which added VERTICAL tab bars: with `tab_bar_edge left` the bar is a
real multi-row Screen — `s.resize(nlines, ncols)`, roughly 28 columns by the
full window height — and a custom draw_tab may paint any row of it.

Two porting notes recorded while the evidence was fresh, both from the 0.48.2
source, because they will silently break the code below:
  * in vertical mode draw_tab is called with is_last=True for EVERY tab, so the
    `if is_last:` gate at the bottom would draw the cat once per tab;
  * ExtraData is rebuilt per call, so prev_tab/next_tab/for_layout are always
    None/None/False, and there is no two-pass layout call.

Everything below is the horizontal implementation, unchanged and still correct
for `tab_bar_style custom`.
"""

"""Kitty tab bar: separator tabs plus a resident animated cat.

The Claude Code statusline cannot animate — its renders are event-driven,
measured 2026-08-08 arriving 1..34 s apart with 28-34 s freezes — so the
moving cat lives HERE: the tab bar is the one kitty surface with a real
repeating timer. The bar sits on the BOTTOM edge (kitty.conf) directly
under Claude Code's statusline, beside the text entry.

TIMER PAIRING — the fact this file exists to remember:
  mark_tab_bar_dirty() only sets a flag that the render loop reads when it
  next wakes; on its own the bar repaints only when something else happens
  to wake kitty. It MUST be paired with wakeup_main_loop() — see _dirty().
  Verified 2026-08-08 by logging: without the wakeup the on-screen sprite
  froze for 30 s while the dirty flag sat set.

SPRITES — ordinary characters that read as a cat: =o.o=~ and friends.
Every glyph pair below was shaped with HarfBuzz against the live font file
(hb-shape, ~/Library/Fonts/JetBrainsMonoNerdFontMono-Regular.ttf,
2026-08-08), because kitty shapes the bar with the same HarfBuzz + font
and JetBrains Mono ligates aggressively: `^=` IS a ligature
(asciicircum_equal.liga) — it kills the classic =^.^= face at the right
cheek — and `!=`, `~-`, `__`, `==` ligate too. Everything used here
shapes one glyph per cell at the mono advance (600), ω included: no
ligatures, no font fallback, no width drift. If you add art, hb-shape it
first — ligatures never change cell counts, so no width check catches one.
Standing junction rules encoded in the choreography: props keep a 1-cell
gap from the body unless the pair is verified (o= =o *= =* are), the two
cats never touch (== would ligate), `!` never sits immediately left of a
face, and speed-line trails keep a gap (~- would ligate).

BEHAVIOUR — a two-layer mind: a context chosen by terminal state, and
within each context a repertoire of weighted acts whose durations,
distances and directions are rolled fresh every time, so nothing loops.
Between acts the cat rests ~5 s (blinking, settling its tail) — that
pause is a stated user requirement, not slack.

  idle    blinks, tail-swishes, winks at you, makes faces, kneads
          contentedly, strolls out and sniffs, patrols to the tab strip
          and reads the titles, chases its tail until dizzy, bats a
          terracotta ball across the bar, checks the Claude rate-limit
          meter and recoils if it is high, catnaps; rarely an amber
          friend pads in from the right edge and they sit nose-to-nose
  work    a tab reports progress (OSC 9;4): an ember bar burns at the
          right end and the cat sits facing it, tail metronoming,
          glancing back at you; if progress stalls it turns grumpy
  bell    a finished run: dashes to the tab strip with speed lines and
          stares you down until you focus the tab, then ambles home
  doze    ~10 quiet minutes: slow tail-breathing, a drifting z
  sleep   ~15 quiet minutes: one static sprite, ZERO repaints; any tab
          activity startles it awake

Tab titles always win the row: the scene draws only right of the last
tab, drops the ember bar first and then the whole cat when the bar is
crowded, and can never push a title into truncation.

COST (2026-08-08, `/bin/ps -o cputime= -p <kitty pid>` deltas over wall
time; only measured claims below):
  * Unviewable window (user in another app): kitty stops calling draw_tab
    entirely — the draw log recorded ZERO passes over 25 min backgrounded.
    _tick() detects this (a requested repaint that stays undrawn for
    UNWATCHED_S) and stands down: no frame computation, a 0.5 Hz nudge so
    the bar catches up within ~2 s of becoming visible again.
  * Visible window: not measured for THIS sprite set — the OS window left
    focus mid-session and stealing it back was off-limits. The previous
    sextant cat on this exact timer machinery measured 0.50% of one core
    visible; this file does comparable per-tick work at FRAME_S 0.2.
    Measure with the window frontmost and the session quiet:
      t0=$(/bin/ps -o cputime= -p PID); /bin/sleep 60; \
      t1=$(/bin/ps -o cputime= -p PID)   # delta seconds / 60 = core share
  * The dirty-check in _tick() repaints only when the drawn frame would
    actually change: ~1-2 bar repaints/s while an act runs, a handful
    during the ~5 s rests, zero asleep.
One-line disable: ANIMATE = False below — the cat stays, static, and no
timer is ever armed.

RELOAD QUIRK (measured with version-tagged draws): kitty applies a
changed tab_bar.py one reload LATE. Boss.load_config_file clears the
run_once module cache only AFTER apply_new_options, and the
tab_title_template machinery repopulates the cache between reloads.
Always reload twice: `kitten @ load-config` && `kitten @ load-config`.

VERIFICATION HOOK: `touch ~/.config/kitty/.cat-drawlog` + reload twice →
every real draw pass (kitty's render loop calling draw_tab, not a script
loop) appends `monotonic x:text ...` to ~/.config/kitty/.cat-draw.log.
Remove the marker + reload twice to stop. The marker is checked once, at
module load.

Testing hook: KILN_CAT_QUIET_S in kitty's environment shrinks the
doze/sleep thresholds so the sleep path can be exercised quickly.
"""

import os
import random
import time

from kitty.fast_data_types import Screen, add_timer, get_boss, wakeup_main_loop
from kitty.tab_bar import (
    DrawData,
    ExtraData,
    TabBarData,
    as_rgb,
    draw_tab_with_separator,
)
from kitty.utils import color_as_int

CAT = False           # ← THE CAT MOVED. See below.
ANIMATE = CAT         # False → no timers, no idle repaints at all

# ═══════════════════════════════════════════════════════════════════════════
# THE CAT LEFT THIS FILE ON 2026-08-09, and the premise that put it here was
# wrong. This module's header says the Claude Code statusline "cannot animate
# — its renders are event-driven". That is false: `statusLine.refreshInterval`
# (integer seconds) re-runs the statusline command on a real timer. Measured
# the same day: two idle Claude sessions rendered EXACTLY 20 times in 20 s at
# refreshInterval=1. The tab bar was never the only surface with a timer; it
# was only the only one anybody had tested.
#
# So the cat now lives in ~/.claude/statusline.sh, where it gets what one row
# could never give it: four rows of body instead of one, nine cells instead of
# five, a stage as wide as the pane, and somewhere to walk. Two cats on one
# screen read as a bug, so this one stands down.
#
# WHAT THIS FILE STILL DOES, and why it is still worth loading: the ember
# progress bar. A tab reporting OSC 9;4 progress gets ' NNN% ████▓░░░' at the
# right end of the bar, which the statusline cannot show because it does not
# know about other tabs. That is the part with no substitute.
#
# TO BRING THE CAT BACK: set CAT = True. Everything below is untouched and
# still works — the choreography, the acts, the bell dash, the doze/sleep
# ladder, the HarfBuzz-verified sprite set. Set STAGE_ROWS = 0 in
# ~/.claude/statusline.sh at the same time, or you will have two of them.
# ═══════════════════════════════════════════════════════════════════════════
FRAME_S = 0.2         # repeating-timer granularity; the shortest gesture beat
DASH_S = 0.8          # bell: dash duration …
DASH_FPS = 10.0       # … at 10 strip repaints/s, once per bell
AMBLE_S = 2.0         # bell cleared: walk home duration …
AMBLE_FPS = 3.0       # … at 3 strip repaints/s
EMBER_FRESH_S = 3.0   # embers shimmer only while progress moved this recently
UNWATCHED_S = 1.5     # a repaint request undrawn this long → window is
                      # unviewable, stand the timer down (kitty does not
                      # render unviewable windows, so draw_tab goes silent)
NUDGE_S = 2.0         # while stood down, re-request at this period so the
                      # bar catches up quickly when the window returns
STALL_S = 10.0        # no progress for this long → the cat turns grumpy
KILN_CELLS = 8        # width of the ember progress bar
KILN_W = 6 + KILN_CELLS   # ' NNN% ' + embers

RATELIMITS = '/Users/ayush/.claude/cache/ratelimits'
RATELIMITS_TTL = 60.0     # read the file at most this often, and only
                          # when the meter act actually rolls

_QUIET = float(os.environ.get('KILN_CAT_QUIET_S', 600.0))
DOZE_AFTER_S = _QUIET           # quiet this long → doze
SLEEP_AFTER_S = _QUIET + (90.0 if 'KILN_CAT_QUIET_S' in os.environ else 300.0)

# ── sprites ───────────────────────────────────────────────────────────────
# Faces are exactly 5 cells; a tail adds 1. All pairs HarfBuzz-clean (see
# header). No face may END in ^ — `^=` ligates — which is why happy eyes
# are u/ω here and ^ appears only at the left cheek (the wink).

FACES = {
    'look':  '=o.o=',   # open eyes — the resting face; the cat watches the room
    'shut':  '=-.-=',   # eyes closed: blink, doze, sleep
    'wide':  '=O.O=',   # startled / staring
    'calm':  '=u.u=',   # content, eyes closed soft
    'uwu':   '=uωu=',   # blissful
    'wink':  '=^.o=',   # left cheek only — the mirror-safe wink
    'grump': '=-_-=',
    'dizzy': '=@.@=',
}
# TAILS REMOVED 2026-08-08 at Ayush's request: "there are things like ~, ','
# and - maybe similar with the cat! can we remove that and clear those things,
# and just keep the cat!". At one row a detached tail glyph does not read as a
# tail — it reads as stray punctuation parked beside the cat. The choreography
# still passes a tail name in every step (it drives nothing now, and keeping
# the parameter means the acts, gaits and mirroring below are untouched), so
# restoring tails is a one-line revert of _compose plus CAT_W back to 6.
TAILS = {'mid': '~', 'low': ',', 'up': ')'}
_TAIL_MIRROR = {'~': '~', ',': ',', ')': '('}

CAT_W = 5             # the face alone, in cells


def _compose(face: str, tail: str | None = None, right: bool = False) -> str:
    """The drawn body: the face, and nothing else.

    Faces are visually symmetric, so facing right needs no mirroring now
    that the tail is gone — `right` is accepted and ignored so that every
    caller and every step tuple keeps working unchanged."""
    return FACES[face]


# ── state ─────────────────────────────────────────────────────────────────
# Accumulated over one draw pass (kitty draws a bar's tabs in order, index
# starts at 1, so index == 1 is the reset point).
_pass = {'bell': False, 'progress': -1, 'sig': [], 'active': -1}

_t0 = time.monotonic()
_state = {
    'mode': 'rest',      # rest | dash | watch | amble   (position, for bell)
    'since': _t0,        # when mode last changed
    'bell_prev': False,
    'pct_prev': -1,      # last progress value, for the ember-freshness gate
    'pct_since': _t0,    # when progress last changed
    'quiet_since': _t0,  # when the tab-state signature last changed
    'tabs_sig': None,    # that signature (titles, active, bell, progress)
    'geom': (0, 80),     # (left_x, columns) from the last draw, for _tick
    'drawn': None,       # canonical signature of the last drawn frame
    'req_at': 0.0,       # first repaint request not yet answered by a draw
    'drawn_at': 0.0,     # when a draw pass last ran
    'nudge_at': 0.0,     # last stood-down nudge
}
_timer_armed = False

_rng = random.Random()
# Current act: steps of (face, tail, seconds, dx, extra). dx is cells left
# of home; extra is None or a dict with any of
#   'f': 1                    cat faces right (tail flips side)
#   'ball': (bdx, glyph)      the ball at dx=bdx: 'o' rolling, '*' whap
#   'friend': (fdx, face, tail, right)   the visitor
#   'z': (glyph, gap)         a z drifting `gap` cells past the nose
#   'say': (text, colorkey)   short text one cell beyond the nose
#   'tr': 1                   speed lines behind a dashing cat
_act = {'ctx': None, 'steps': (), 'i': 0, 'until': 0.0, 'dx': 0, 'extra': None}

_BASE = {'idle': ('look', 'mid'), 'work': ('look', 'mid'),
         'bell': ('wide', 'up'), 'doze': ('shut', 'low'),
         'sleep': ('shut', 'low')}

_rl = {'at': 0.0, 'pcts': (0, 0)}

# Verification hook (see header): with the marker present at module load,
# every REAL draw pass — kitty's render loop calling draw_tab — appends
# its frame to the log. Costs one os.path.exists at load, zero otherwise.
try:
    from kitty.constants import config_dir as _config_dir
except Exception:
    _config_dir = os.path.expanduser('~/.config/kitty')
_LOG = (os.path.join(_config_dir, '.cat-draw.log')
        if os.path.exists(os.path.join(_config_dir, '.cat-drawlog'))
        else None)


def _ratelimits() -> tuple[int, int]:
    """(five_hour_pct, seven_day_pct), cached RATELIMITS_TTL. Called only
    from _plan when the meter act rolls, so the file is read at most once
    a minute and usually far less."""
    now = time.monotonic()
    if now - _rl['at'] > RATELIMITS_TTL:
        _rl['at'] = now
        try:
            with open(RATELIMITS, encoding='utf-8') as f:
                parts = f.read().split()
            _rl['pcts'] = (int(parts[0]), int(parts[2]))
        except Exception:
            pass  # keep the previous reading; the cat just stays calm
    return _rl['pcts']


def _hold(lo: float, hi: float) -> float:
    return _rng.uniform(lo, hi)


def _gait(frm: int, to: int, pace=(0.22, 0.32), face='look',
          extra=None) -> list:
    """Walk steps from dx=frm to dx=to, tail bouncing mid/low. Moving
    right (dx decreasing) flips the tail side so the cat faces where it
    is going."""
    steps = []
    ex = dict(extra) if extra else {}
    if to < frm:
        ex['f'] = 1
    rng = range(frm, to + 1) if to >= frm else range(frm, to - 1, -1)
    for n, dx in enumerate(rng):
        steps.append((face, ('mid', 'low')[n % 2], _hold(*pace), dx,
                      dict(ex) if ex else None))
    return steps


def _rest() -> list:
    """The ~5 s pause between acts the user asked for — with a blink and
    a tail settle partway through so it never reads as a freeze."""
    steps = [('look', 'mid', _hold(1.4, 2.2), 0, None)]
    if _rng.random() < 0.75:
        steps += [('shut', 'mid', 0.14, 0, None)]
    steps += [('look', 'mid', _hold(1.6, 2.6), 0, None)]
    if _rng.random() < 0.4:
        steps += [('look', 'low', _hold(0.6, 1.2), 0, None)]
    return steps


def _span() -> int:
    """How many cells of runway exist left of home, from the last draw."""
    left_x, columns = _state['geom']
    return max(0, columns - 1 - CAT_W - left_x)


def _plan(ctx: str) -> list:
    """One act plus the trailing rest. Weights, durations and directions
    are rolled fresh every time so nothing reads as a loop."""
    r, h = _rng, _hold
    if ctx == 'bell':
        # Sitting by the tabs, staring you down; the stare breaks only to
        # blink or glance.
        act = ([('shut', 'up', 0.15, 0, None)] if r.random() < 0.6 else
               [('look', 'up', h(0.8, 1.6), 0, None)])
        return act + [('wide', 'up', h(2.5, 4.5), 0, None)]
    if ctx == 'work':
        stalled = (time.monotonic() - _state['pct_since']) > STALL_S
        if stalled:
            # Sits back, tail flicking, grumpy: "it's stuck" reads from
            # across the room.
            act = r.choices((
                [('grump', ('mid', 'low')[n % 2], h(0.3, 0.5), 0, {'f': 1})
                 for n in range(r.randint(4, 8))],
                [('wide', 'mid', h(1.2, 2.2), 0, None)],   # turns to you
                [('grump', 'low', h(1.0, 1.8), 0, {'f': 1})],
            ), (3, 2, 2))[0]
            return act + [('look', 'low', h(1.5, 3.0), 0, {'f': 1})]
        act = r.choices((
            [('look', ('mid', 'low')[n % 2], h(0.6, 1.1), 0, {'f': 1})
             for n in range(r.randint(3, 6))],             # tail metronome
            [('look', 'mid', h(0.8, 1.4), 0, None)],       # glances at you
            [('shut', 'mid', 0.14, 0, {'f': 1})],          # blink
        ), (4, 2, 2))[0]
        return act + [('look', 'mid', h(1.0, 2.5), 0, {'f': 1})]
    if ctx == 'doze':
        # tail rises and falls slowly: breathing. A z now and then.
        act = []
        for n in range(r.randint(2, 3)):
            act += [('shut', 'low', h(2.4, 3.6), 0,
                     {'z': ('z', 1)} if r.random() < 0.5 else None),
                    ('shut', 'mid', h(2.4, 3.6), 0,
                     {'z': ('Z', 2)} if r.random() < 0.3 else None)]
        return act
    if ctx == 'sleep':
        return [('shut', 'low', 3600.0, 0, {'z': ('z', 1)})]  # 0 repaints

    # ── idle repertoire ──────────────────────────────────────────────────
    span = _span()
    blink = [('shut', 'mid', 0.14, 0, None)]
    if r.random() < 0.3:
        blink += [('look', 'mid', h(0.4, 0.8), 0, None),
                  ('shut', 'mid', 0.14, 0, None)]
    swish = [('look', r.choice(('mid', 'low', 'up')),
              h(0.3, 0.7), 0, None) for _ in range(r.randint(3, 6))]
    wink = [('wink', 'up', h(0.7, 1.2), 0, None)]
    faces = [(f, 'mid', h(0.5, 1.0), 0, None) for f in
             r.sample(('uwu', 'wide', 'wink', 'grump', 'dizzy', 'calm'),
                      r.randint(3, 5))]
    knead = [('calm', 'up', h(1.2, 2.0), 0, None),
             ('uwu', 'up', h(1.5, 2.5), 0, None)]
    catnap = [('calm', 'low', h(1.0, 1.6), 0, None),
              ('shut', 'low', h(4.0, 8.0), 0, {'z': ('z', 1)}),
              ('look', 'up', h(0.5, 0.9), 0, None)]
    startle = [('wide', 'up', h(0.4, 0.7), 0, None),   # was a floating '!'
               ('wide', 'up', 0.18, 1, None),
               ('wide', 'up', h(0.6, 1.0), 0, None),
               ('look', 'mid', h(0.8, 1.3), 0, None)]
    spin = [('look', 'up', h(0.15, 0.22), 0, {'f': n % 2})
            for n in range(r.randint(5, 9))] + \
           [('dizzy', 'mid', h(0.7, 1.1), 0, None)]

    far = r.randint(2, max(2, min(7, span)))
    stroll = (_gait(0, far)
              + [('look', 'mid', h(0.5, 0.9), far, None),  # was a floating '?'
                 ('look', 'mid', h(0.6, 1.0), far, None),
                 ('calm', 'mid', h(0.5, 0.9), far, None)]
              + _gait(far, 0))
    # all the way to the tab strip: sits and reads the titles
    pat = min(span, 24)
    patrol = (_gait(0, pat, pace=(0.2, 0.28))
              + [('look', 'up', h(1.6, 2.6), pat, None),
                 ('shut', 'up', 0.14, pat, None),
                 ('look', 'up', h(1.2, 2.2), pat, None)]
              + _gait(pat, 0, pace=(0.2, 0.28)))

    # the terracotta ball: spots it, stalks it, bats it across the bar
    if span >= 7:
        b0 = r.randint(5, min(10, span))
        bmax = span + CAT_W - 2
        ball = [('wide', 'up', h(0.4, 0.6), 0, {'ball': (b0, 'o')}),
                ('look', 'low', h(0.35, 0.6), 0, {'ball': (b0, 'o')})]
        ball += _gait(0, b0 - 1, pace=(0.16, 0.24),
                      extra={'ball': (b0, 'o')})
        at = b0 - 1
        for _hop in range(r.randint(2, 3)):
            nb = min(b0 + r.randint(2, 3), bmax)
            ball += [('look', 'up', 0.14, at, {'ball': (nb, '*')}),   # whap
                     ('look', 'up', 0.2, at, {'ball': (nb, 'o')})]
            if nb >= bmax:
                break
            ball += _gait(at, nb - 1, pace=(0.16, 0.24),
                          extra={'ball': (nb, 'o')})
            at, b0 = nb - 1, nb
        ball += [('look', 'mid', h(0.3, 0.5), at,
                  {'ball': (min(b0 + 4, bmax), 'o')}),   # it rolls…
                 ('look', 'mid', h(1.0, 1.6), at, None)]  # …and is gone
        ball += _gait(at, 0)
    else:
        ball = swish

    # checks the Claude rate-limit meter (the statusline sits directly
    # above this bar): reads it, and recoils if it is running hot
    p5, p7 = _ratelimits()
    pct = max(p5, p7)
    meter = _gait(0, 2) + [('look', 'mid', h(0.5, 0.8), 2, None),
                           ('wide', 'up', h(0.6, 0.9), 2, None)]
    if pct >= 80:
        say = (f'{pct}%!', 'warn')
        meter += [('wide', 'up', h(0.8, 1.2), 2, {'say': say}),
                  ('wide', 'up', 0.18, 3, {'say': say}),      # recoil hop
                  ('wide', 'up', 0.18, 2, {'say': say}),
                  ('grump', 'low', h(0.8, 1.4), 2, None)]
        meter += _gait(2, 0, pace=(0.15, 0.2))                # hurries home
        meter += [('grump', 'low', h(1.0, 1.8), 0, None)]
    elif pct >= 50:
        say = (f'{pct}%', 'ember')
        meter += [('look', 'mid', h(1.0, 1.6), 2, {'say': say}),
                  ('shut', 'mid', 0.14, 2, None),
                  ('look', 'mid', h(0.6, 1.0), 2, {'say': say})]
        meter += _gait(2, 0)
    else:
        meter += [('look', 'mid', h(1.0, 1.6), 2, {'say': (f'{pct}%', 'dim')}),
                  ('uwu', 'mid', h(0.8, 1.4), 2, None)]
        meter += _gait(2, 0)

    # the visitor: an amber friend pads in from the right edge; they sit
    # nose-to-nose (1-cell gap — two cats touching would shape == into a
    # ligature) and then it leaves
    if span >= 9:
        friend = _gait(0, 5) + [('look', 'mid', 0.3, 5, {'f': 1})]
        for n, fdx in enumerate(range(-6, -1)):
            friend += [('look', ('mid', 'low')[n % 2], h(0.25, 0.35), 5,
                        {'f': 1, 'friend': (fdx, 'look',
                                            ('mid', 'low')[n % 2], 0)})]
        friend += [('uwu', 'mid', h(1.5, 2.5), 5,
                    {'f': 1, 'friend': (-2, 'uwu', 'mid', 0)}),
                   ('look', 'mid', 0.3, 5,
                    {'f': 1, 'friend': (-2, 'look', 'mid', 0)}),
                   ('uwu', 'up', h(1.0, 1.8), 5,
                    {'f': 1, 'friend': (-2, 'uwu', 'up', 0)})]
        for n, fdx in enumerate(range(-2, -7, -1)):
            friend += [('look', 'mid', h(0.25, 0.35), 5,
                        {'f': 1, 'friend': (fdx, 'look',
                                            ('mid', 'low')[n % 2], 1)})]
        friend += [('look', 'mid', h(0.6, 1.0), 5, None)] + _gait(5, 0)
    else:
        friend = wink

    acts, weights = ([blink, swish, wink, faces, knead, catnap, startle,
                      spin, stroll, patrol, ball, meter, friend],
                     (3.0, 3.0, 1.5, 1.2, 2.0, 1.2, 0.4,
                      0.7, 2.0, 0.8, 0.9, 0.9, 0.35))
    return r.choices(acts, weights)[0] + _rest()


def _ctx(now: float) -> str:
    """Pure function of state + now, so _tick and the draw agree."""
    if _pass['bell'] or _state['mode'] in ('dash', 'watch'):
        return 'bell'
    if _pass['progress'] >= 0:
        return 'work'
    quiet = now - _state['quiet_since']
    if quiet >= SLEEP_AFTER_S:
        return 'sleep'
    if quiet >= DOZE_AFTER_S:
        return 'doze'
    return 'idle'


def _repertoire(now: float, ctx: str) -> tuple:
    """Advance the repertoire to `now`; returns (face, tail, extra) and
    leaves the current dx in _act['dx']. Monotone in `now`, so _tick and
    the draw always agree on the frame."""
    a = _act
    if a['ctx'] != ctx:
        waking = a['ctx'] in ('doze', 'sleep') and ctx in ('idle', 'work')
        a['ctx'] = ctx
        if waking:   # startled awake, a beat of bliss, then composure
            a['steps'] = [('wide', 'up', 0.6, 0, None),
                          ('uwu', 'mid', 1.0, 0, None),
                          ('look', 'mid', _hold(0.75, 1.5), 0, None)]
        else:        # settle beat on the context's base face first
            face, tail = _BASE[ctx]
            a['steps'] = [(face, tail, _hold(0.75, 1.75), 0, None)]
        a['i'] = 0
        a['until'] = now + a['steps'][0][2]
    while now >= a['until']:
        a['i'] += 1
        if a['i'] >= len(a['steps']):
            a['steps'] = _plan(ctx)
            a['i'] = 0
        a['until'] = now + a['steps'][a['i']][2]
    face, tail, _, a['dx'], extra = a['steps'][a['i']]
    return face, tail, extra


def _kiln(now: float, canonical: bool = False) -> str:
    """' NNN% ████▓░░░' while a tab reports progress, else ''.

    canonical=True pins the shimmer so _tick's dirty-comparison never sees
    it change. The shimmer also requires a progress update within the last
    EMBER_FRESH_S: freshness — not incidental redraws — is what keeps
    "stalled" readable as still embers.
    """
    pct = _pass['progress']
    if pct < 0:
        return ''
    filled = round(KILN_CELLS * min(100, pct) / 100)
    cells = ['█'] * filled + ['░'] * (KILN_CELLS - filled)
    if (filled and ANIMATE and not canonical
            and now - _state['pct_since'] < EMBER_FRESH_S and int(now * 4) % 2):
        cells[filled - 1] = '▓'
    return f' {pct:>3}% ' + ''.join(cells)


def _scene(now: float, canonical: bool = False):
    """Everything right of the tabs, as draw items (x, text, colorkey).
    Returns (items, alerted) or None when the bar is too crowded — tabs
    always win. Pure in `now` given the state, so _tick can compare."""
    left_x, columns = _state['geom']
    ctx = _ctx(now)
    kiln = _kiln(now, canonical)
    # right-to-left budget: [cat][kiln], then degrade. With CAT off the cat
    # reserves nothing, so a crowded bar keeps the ember bar for longer.
    cat_w = (CAT_W + 1) if CAT else 0
    need = cat_w + (KILN_W if kiln else 0)
    if need == 0:
        return None
    if columns - left_x < need:
        kiln = ''
        need = cat_w
        if need == 0 or columns - left_x < need:
            return None
    home_x = columns - need

    m = _state['mode']
    alerted = _pass['bell'] or m in ('dash', 'watch')
    items = []
    if kiln:
        kx = columns - KILN_W
        items.append((kx, kiln[:6], 'dim'))
        items.append((kx + 6, kiln[6:], 'ember'))

    if not CAT:
        # Ember bar only. Returning the items list (not None) keeps the row's
        # own erase path running, which is what stops a stale title lingering
        # between the tabs and the right edge.
        return items, alerted

    if not ANIMATE:
        face = 'wide' if alerted else 'look'
        items.append((home_x, _compose(face, 'mid'),
                      'hot' if alerted else 'body'))
        return items, alerted

    # position: bell movement interpolates, everything else follows the act
    if m == 'dash':
        face, tail = 'wide', ('mid', 'low')[int(now * DASH_FPS) % 2]
        extra = {'tr': 1}
        t = min(1.0, (now - _state['since']) / DASH_S)
        t = 1.0 - (1.0 - t) ** 3       # ease-out: launch hard, skid to stop
        x, right = home_x - round((home_x - left_x) * t), False
    elif m == 'amble':
        face, tail = 'look', ('mid', 'low')[int(now * AMBLE_FPS) % 2]
        extra = {}
        t = min(1.0, (now - _state['since']) / AMBLE_S)
        t = t * t * (3.0 - 2.0 * t)    # smoothstep: unhurried at both ends
        x, right = left_x + round((home_x - left_x) * t), True
    else:
        face, tail, extra = _repertoire(now, ctx)
        extra = extra or {}
        right = bool(extra.get('f'))
        x = left_x if m == 'watch' else max(left_x, home_x - _act['dx'])
    body = _compose(face, tail, right)

    if 'ball' in extra:
        bdx, glyph = extra['ball']
        items.append((home_x - bdx, glyph, 'ball'))
    if 'friend' in extra:
        fdx, fface, ftail, fright = extra['friend']
        items.append((home_x - fdx, _compose(fface, ftail, bool(fright)),
                      'friend'))
    if 'z' in extra:
        glyph, gap = extra['z']
        items.append((x - gap - 1, glyph, 'dim'))
    if 'say' in extra:
        txt, key = extra['say']
        sx = x + len(body) + 1 if right else x - len(txt) - 1
        items.append((sx, txt, key))
    items.append((x, body, 'hot' if alerted else 'body'))
    if extra.get('tr') and x + len(body) + 1 < home_x:
        items.append((x + len(body) + 1,
                      '-~'[int((now - _state['since']) * DASH_FPS) % 2],
                      'dim'))
    return items, alerted


def _frame_sig(now: float):
    return _scene(now, canonical=True)


def _dirty() -> None:
    boss = get_boss()
    if boss is None:
        return
    tm = boss.active_tab_manager
    if tm is not None:
        # Track the first request a draw pass has not yet answered — the
        # gap between the two is how _tick detects an unviewable window.
        if _state['req_at'] <= _state['drawn_at']:
            _state['req_at'] = time.monotonic()
        tm.mark_tab_bar_dirty()
        # Marking alone is NOT enough: it sets a flag the render loop reads,
        # and the render loop sleeps until an event. Without this wakeup the
        # cat only moved when something else happened to redraw the bar —
        # verified 2026-08-08 by logging _tick (sig_eq stayed False for 30 s
        # while the on-screen sprite never changed).
        wakeup_main_loop()


def _tick(timer_id=None) -> None:
    """Repeating timer: repaint only when the drawn frame would change."""
    if _state['mode'] in ('dash', 'amble'):
        return  # movement repaints belong to _burst
    now = time.monotonic()
    # Stand down while the window is unviewable: kitty does not render it,
    # so draw_tab is never called and a repaint we requested stays undrawn
    # (measured 2026-08-08: zero draw passes over 25 min backgrounded).
    # Skip all frame work; nudge at NUDGE_S so the first frames after the
    # window returns are at most ~2 s stale.
    pending = _state['req_at'] > _state['drawn_at']
    if pending and now - _state['req_at'] > UNWATCHED_S:
        if now - _state['nudge_at'] > NUDGE_S:
            _state['nudge_at'] = now
            _dirty()
        return
    if _state['drawn'] == 'yield':
        return  # crowded bar: the cat is hidden, nothing to animate
    if _frame_sig(now) == _state['drawn']:
        return
    _dirty()


def _burst(timer_id=None) -> None:
    """One-shot chain at DASH/AMBLE_FPS while the cat is moving."""
    m = _state['mode']
    if m not in ('dash', 'amble'):
        return  # movement over; the chain dies here
    _dirty()
    add_timer(_burst, 1.0 / (DASH_FPS if m == 'dash' else AMBLE_FPS), False)


def _arm_timer() -> None:
    global _timer_armed
    if ANIMATE and not _timer_armed:
        _timer_armed = True
        add_timer(_tick, FRAME_S, True)


def _set_mode(mode: str, now: float) -> None:
    _state['mode'] = mode
    _state['since'] = now


def _advance(now: float) -> None:
    """State transitions, run once per draw pass (event-driven)."""
    if _pass['progress'] != _state['pct_prev']:
        _state['pct_prev'] = _pass['progress']
        _state['pct_since'] = now
    # Activity = the tab strip itself changed (titles, count, focus, bells,
    # progress) — the thing the bar can actually see. Typing into a running
    # program does not repaint the bar, so the cat may doze beside deep
    # focus; that is a feature. It wakes the instant anything happens.
    sig = tuple(_pass['sig'])
    if sig != _state['tabs_sig']:
        prev = _state['tabs_sig']
        _state['tabs_sig'] = sig
        _state['quiet_since'] = now
        # A tab SWITCH (or bell landing, or tab opened/closed) while the
        # cat idles at home earns a pointed look toward the tab strip.
        # The trigger must be STRUCTURAL — never the title text: a busy
        # Claude session puts a spinner in its title that flickers several
        # times a second, and keying off it re-armed this look on every
        # flicker, freezing the cat at =o.o=) exactly when the session was
        # busiest (reproduced headless 2026-08-08: 300 flickering draw
        # passes → 2 distinct frames; live log showed 738/744).
        struct = tuple((s[1], s[2]) for s in sig)
        pstruct = None if prev is None else tuple((s[1], s[2]) for s in prev)
        if (pstruct is not None and struct != pstruct and ANIMATE
                and _act['ctx'] == 'idle' and _state['mode'] == 'rest'
                and _act['dx'] == 0):
            _act['steps'] = [('look', 'up', _hold(1.2, 2.2), 0, None),
                             ('look', 'mid', _hold(0.5, 1.0), 0, None)]
            _act['i'] = 0
            _act['until'] = now + _act['steps'][0][2]
    bell = _pass['bell']
    if bell and not _state['bell_prev'] and ANIMATE:
        _set_mode('dash', now)
        add_timer(_burst, 1.0 / DASH_FPS, False)
    elif not bell and _state['bell_prev'] and _state['mode'] in ('dash', 'watch'):
        _set_mode('amble', now)
        add_timer(_burst, 1.0 / AMBLE_FPS, False)
    _state['bell_prev'] = bell
    m = _state['mode']
    if m == 'dash' and now - _state['since'] >= DASH_S:
        _set_mode('watch', now)
    elif m == 'amble' and now - _state['since'] >= AMBLE_S:
        _set_mode('rest', now)


def _draw_right_status(draw_data: DrawData, screen: Screen, end: int) -> None:
    now = time.monotonic()
    _state['drawn_at'] = now   # a draw pass ran: the window is viewable
    _advance(now)
    left_x = end + 2
    _state['geom'] = (left_x, screen.columns)
    # Erase the rest of the row ourselves before drawing: for the LAST tab
    # draw_tab_with_separator stops at `end` without covering it, kitty only
    # erases from wherever the cursor finishes, and our items move around —
    # so text a previous frame drew would otherwise linger. (Seen live
    # 2026-08-08: a stale title sat between the tabs and the cat, plus one
    # orphan glyph exactly at `end` until the erase started there.)
    screen.cursor.bold = screen.cursor.italic = False
    screen.cursor.bg = as_rgb(color_as_int(draw_data.default_bg))
    cx = min(end, screen.columns)
    screen.cursor.x = cx
    screen.draw(' ' * (screen.columns - cx))
    scene = _scene(now)
    if scene is None:
        _state['drawn'] = 'yield'
        return
    items, alerted = scene
    inactive = as_rgb(color_as_int(draw_data.inactive_fg))
    active = as_rgb(color_as_int(draw_data.active_fg))

    def pal(n: int, fallback: int) -> int:
        # live palette via the bar screen's colour profile — a theme switch
        # through `kitten @ set-colors` recolours the cat with everything else
        try:
            return as_rgb(color_as_int(screen.color_profile.as_color(
                (n << 8) | 1)))
        except Exception:
            return fallback
    colors = {
        'body': inactive,          # quiet parchment: furniture until it moves
        'hot': active,             # bell: full-contrast stare
        'dim': inactive,
        'ember': pal(3, active),   # kiln amber
        'ball': pal(1, active),    # terracotta ball
        'friend': pal(3, active),  # the visitor arrives in amber
        'warn': pal(1, active),    # the rate-limit shock
    }
    # Ascending x, and the LAST draw must be the rightmost item: kitty
    # erases the bar from wherever the cursor ends up, so anything drawn
    # to the right of the final cursor position vanishes. (Found by
    # screenshot: an item in the list, at the right columns, was blank on
    # screen while another — drawn after it, further left — showed fine.)
    for x, text, key in sorted(items, key=lambda it: it[0]):
        if x < left_x:             # clip against the tab strip
            text = text[left_x - x:]
            x = left_x
        if x >= screen.columns or not text:
            continue
        text = text[:screen.columns - x]
        screen.cursor.x = x
        screen.cursor.fg = colors[key]
        screen.draw(text)
    # With tab_bar_style custom kitty calls draw_tab on EVERY window frame
    # (measured 46 passes/s while the pty streamed), so this path must stay
    # cheap: without a kiln the scene we just drew IS the canonical frame —
    # skip recomputing it. The kiln's shimmer is the one non-canonical bit.
    _state['drawn'] = scene if _pass['progress'] < 0 else _frame_sig(now)
    if _LOG:  # verification hook, see header
        try:
            with open(_LOG, 'a', encoding='utf-8') as f:
                frame = ' '.join(f'{x}:{t}' for x, t, _k in sorted(items))
                f.write(f'{now:.3f} end={end} cols={screen.columns} '
                        f'{frame}\n')
        except Exception:
            pass


def draw_tab(
    draw_data: DrawData,
    screen: Screen,
    tab: TabBarData,
    before: int,
    max_tab_length: int,
    index: int,
    is_last: bool,
    extra_data: ExtraData,
) -> int:
    if index == 1:
        _pass['bell'] = False
        _pass['progress'] = -1
        _pass['sig'] = []
    if tab.needs_attention:
        _pass['bell'] = True
    if tab.num_of_windows_with_progress > 0:
        pct = tab.total_progress // tab.num_of_windows_with_progress
        _pass['progress'] = max(_pass['progress'], pct)
    _pass['sig'].append((tab.title, tab.is_active, tab.needs_attention,
                         tab.num_of_windows_with_progress))
    _arm_timer()
    end = draw_tab_with_separator(
        draw_data, screen, tab, before, max_tab_length, index, is_last,
        extra_data)
    if is_last:
        _draw_right_status(draw_data, screen, end)
    return end
