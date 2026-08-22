#!/usr/bin/env bash
# Claude Code statusline — instruments that fit the pane, and a cat that walks.
#
#  Opus 5 ▅high │  Portfolio-2.0 »  main* │  ctx 17% 172k/1M │  5h ▰▱▱▱▱ 23% · 4h39m │  wk ▰▰▰▱▱ 61% │ 22:31
#
#                        /\___/\
#                       (  o.o  )
#                        >  ^  <
#                        U     U
#
# ═══════════════════════════════════════════════════════════════════════════
# THE STATUSLINE CAN ANIMATE. Earlier versions of this file argued at length
# that it could not, and that error was load-bearing: it is the reason the
# moving cat was exiled to kitty's tab bar, where exactly one row exists.
#
# `statusLine.refreshInterval` (integer seconds) re-runs this command on a
# timer "in addition to event-driven updates". The key sits beside `padding`
# and `hideVimModeIndicator` in Claude Code 2.1.226's settings schema.
#
# MEASURED 2026-08-09 at refreshInterval=1, counting renders per session_id
# out of the payload log below:
#   * two genuinely idle sessions — nobody typing — rendered EXACTLY 20 times
#     in 20 s each. A clean 1 Hz timer, evenly spaced.
#   * this session, working, rendered 62 times in the same 20 s: event-driven
#     renders stack on top of the timer.
# So the cat idles at 1 fps and quickens to ~3 fps while Claude works, which
# is a feature — it is liveliest exactly when there is something to watch.
#
# SUB-SECOND IS REJECTED, and fails OPEN-LOOP. refreshInterval=0.5 does not
# give 2 Hz; it silently kills the timer. Measured: those same idle sessions
# fell from 20 renders per 20 s to 1. Integer seconds, floor of 1. Do not
# "optimise" this to 0.5.
#
# CONSEQUENCE: motion may now be a function of elapsed renders. The old rule
# still binds the INSTRUMENTS — a number can sit on screen for a full second,
# so it must be true, never a tick of a counter.
#
# ═══════════════════════════════════════════════════════════════════════════
# WHERE THE NUMBERS COME FROM — read this before changing anything.
#
# CONTEXT % IS THE SERVER'S OWN FIGURE: `.context_window.used_percentage`,
# pre-calculated, beside `.context_window_size` and `.total_input_tokens`.
# This file used to tail the transcript JSONL and take the last
# `message.usage` record. That was wrong three ways, and it is the "even after
# compacting, my context still shows the old context" bug:
#
#   1. STALE BY CONSTRUCTION — the last usage record is from the last
#      COMPLETED API call, so it lags everything since. Measured 2026-08-09:
#      the transcript said 129,781 (13%) while the server said 172,417 (17%).
#   2. DEAD WRONG AFTER /compact — compaction appends a
#      `system/compact_boundary` record (compactMetadata.preTokens 347,693 →
#      postTokens 21,052) to the SAME file, keeping the same sessionId and the
#      same transcript_path. Until the next assistant message lands, the last
#      usage record still reads 347k, so the statusline kept showing the
#      pre-compaction number long after the context had been emptied.
#   3. SIDECHAIN POLLUTION — subagent records carry their own `message.usage`,
#      so with an agent running, "the last usage record" could be the agent's
#      context rather than this session's.
#
# `exceeds_200k_tokens` is a HINT ONLY, never an override. The old line was
#   [ "$exceeds" = "true" ] && [ "$ctx_pct" -lt 20 ] && ctx_pct="200k+"
# which printed the malformed literal "ctx 200k+%" and, on a 1M model where
# 200k is a legitimate 20%, latched on permanently. It is now a small ▲ beside
# a percentage that stays true.
#
# RATE LIMITS are the server's own numbers too, from `.rate_limits` — the same
# ones `/usage` prints, free, no API call. NEVER estimate plan usage here: a
# previous version summed tokens across every transcript, divided by a GUESSED
# weekly denominator, read 62% when the truth was 80%, invented a Monday
# rollover the real window does not have, and burned a 32 s ccusage pass to do
# it. If `.rate_limits` is absent, print "—", not a number.
#
# REASONING EFFORT is `.effort.level`: low|medium|high|xhigh|max, and OPTIONAL
# — absent on models with no effort parameter. Absent prints nothing, never a
# default. It is also written to ~/.claude/cache/effort, because the SUBAGENT
# payload does not carry it and that file is the only honest source for the
# level an inheriting agent runs at.
#
# ═══════════════════════════════════════════════════════════════════════════
# WIDTH — why rows are packed, not printed.
#
# Claude Code renders each row as <Text dimColor wrap="truncate">. Two
# consequences, both verified in the binary (clv() -> jsx(y,{dimColor:!0,
# wrap:"truncate"})):
#
#   1. A row longer than the pane is CUT, not wrapped. This is the whole of
#      "when i open panes, some get cut and i don't see the end". A 211-column
#      window split three ways leaves ~68 columns; a fixed-width row of ~95
#      (or a single all-in-one row of ~120) loses its right-hand end. So the
#      instruments below are built as SEGMENTS and packed greedily into as
#      many rows as the measured width needs: one row on a wide window, two or
#      three in a narrow split, and low-value segments dropped entirely before
#      anything gets truncated.
#   2. Everything is wrapped in \033[2m, which is why this statusline used to
#      read washed out whatever colours it picked. Every row therefore OPENS
#      with \033[22m to cancel it, and asks for dim explicitly where dim is
#      wanted.
#
# The main payload carries no width (the SUBAGENT payload does — the schemas
# differ). `stty size < /dev/tty` is the reliable source inside a hook and
# gives the PANE, not the OS window; $COLUMNS is the fallback. The whole
# construct is wrapped, not just stty: a failing `< /dev/tty` redirection is
# reported by the SHELL before stty ever runs, so guarding stty alone still
# prints "Device not configured" on every render.
#
# PERF CONTRACT — this now runs on a 1 Hz timer in EVERY open session, so cost
# is no longer academic. An ancestor of this file took 16-17 s per render (132
# subprocesses); the transcript-tailing version took 110 ms. Budget: ONE jq
# over stdin, git behind a TTL cache, and builtins for everything else — no
# date fork (printf %(…)T), no awk fork, no subshells in the hot path.
# Measure after any change:
#   P=$(grep -v '^=== \|^--- env\|^COLUMNS=' ~/.claude/cache/statusline-payload.log | tail -1)
#   S=$(date +%s%N); for i in $(seq 20); do printf '%s' "$P" | \
#     ~/.claude/statusline.sh >/dev/null; done; E=$(date +%s%N)
#   echo $(( (E-S)/20000000 ))ms
#
# COLOURS are the TERMINAL'S OWN ANSI palette (SGR 33/34/36/90/91/95), never
# hardcoded RGB, so this inherits whatever kitty theme is running.
#
# Requires: jq, bash 5, JetBrainsMono Nerd Font.
set -uo pipefail

TOGGLES="$HOME/.claude/feature-toggles.json"
CACHE="$HOME/.claude/cache"
RL_DIR="$CACHE/ratelimits.d"   # one record per session; see the merge below
GIT_TTL=4          # seconds; git status on a big repo is the only slow call left

# ── stage geometry ───────────────────────────────────────────────────────────
# The one knob for how much screen the cat gets. The art is 4 rows tall, so 4
# is "cat only" and 5 lets it change its lie between rows. 0 removes the cat
# and leaves the instruments alone.
STAGE_ROWS=4          # exactly the cat; nothing else lives on the stage
CAT_H=4
CAT_W=9               # every sprite row below is exactly this many cells

input=$(cat)

# VERIFICATION HOOK, same pattern as tab_bar.py's draw log: with the marker
# present, every render appends the RAW payload and its environment to
# ~/.claude/cache/statusline-payload.log. The binary is compiled, so a capture
# is the only reliable source of truth for what Claude Code actually sends —
# it is how the refreshInterval cadence above was measured, and how the
# subagent schema was learned. Costs one [ -f ] when the marker is absent.
#   touch ~/.claude/cache/statusline-debug     → start
#   /bin/rm ~/.claude/cache/statusline-debug   → stop
if [ -f "$CACHE/statusline-debug" ]; then
  { printf '=== %(%H:%M:%S)T ===\n%s\n--- env ---\nCOLUMNS=%s LINES=%s TERM=%s\n' \
      -1 "$input" "${COLUMNS:-unset}" "${LINES:-unset}" "${TERM:-unset}"; \
  } >> "$CACHE/statusline-payload.log" 2>/dev/null || true
fi

# ── parse the payload in ONE jq call ─────────────────────────────────────────
# Joined on \x1f (unit separator), NOT @tsv: bash `read` treats tab as IFS
# *whitespace*, so adjacent tabs collapse and empty fields silently shift every
# later field — the real cause of an old "model shows ?" bug.
#
# Percentages are rounded HERE: a float reaching bash arithmetic is a hard
# error ("74.3: syntax error") that would blank the gauge.
# The feature-toggles file is folded into this SAME jq call rather than read by
# a second one. Two jq processes per render was the largest remaining cost
# after the transcript tail went: one fork is ~10 ms, and at 1 Hz in every open
# session that is real. --slurpfile is only passed when the file exists,
# because it is a hard error on a missing path; a missing file therefore
# degrades to `[]`, and the `// true` below turns that into ON (fail safe).
if [ -f "$TOGGLES" ]; then TOGARG=(--slurpfile tog "$TOGGLES")
else                       TOGARG=(--argjson tog '[]'); fi

IFS=$'\x1f' read -r cwd exceeds model_id model_name effort fastmode agent_name \
                    ctx_pct ctx_tok ctx_win \
                    blk_pct blk_end wk_pct wk_end sid toggle_plan \
                    out_tok <<<"$(
  printf '%s' "$input" | jq -r "${TOGARG[@]}" '
    [ (.workspace.current_dir // .cwd // "."),
      ((.exceeds_200k_tokens // false) | tostring),
      (.model.id // ""),
      (.model.display_name // ""),
      (.effort.level // ""),
      ((.fast_mode // false) | tostring),
      (.agent.name // ""),
      ((.context_window.used_percentage      // -1) | floor),
      ((.context_window.total_input_tokens   //  0) | floor),
      ((.context_window.context_window_size  //  0) | floor),
      ((.rate_limits.five_hour.used_percentage // -1) | round),
      ((.rate_limits.five_hour.resets_at        //  0) | floor),
      ((.rate_limits.seven_day.used_percentage  // -1) | round),
      ((.rate_limits.seven_day.resets_at        //  0) | floor),
      (.session_id // "default"),
      (($tog[0].ccusageInStatusline // true) | tostring),
      ((.context_window.total_output_tokens // 0) | floor)
    ] | map(tostring) | join("")
  ' 2>/dev/null
)"
cwd="${cwd:-.}"; sid="${sid:-default}"
# `// -1` does NOT fire for a key that is present-but-null, so every numeric
# field is re-validated before any arithmetic touches it.
case "$ctx_pct" in ''|*[!0-9-]*) ctx_pct=-1 ;; esac
case "$ctx_tok" in ''|*[!0-9]*)  ctx_tok=0  ;; esac
case "$ctx_win" in ''|*[!0-9]*)  ctx_win=0  ;; esac
case "$blk_pct" in ''|*[!0-9-]*) blk_pct=-1 ;; esac
case "$blk_end" in ''|*[!0-9]*)  blk_end=0  ;; esac
case "$wk_pct"  in ''|*[!0-9-]*) wk_pct=-1  ;; esac
case "$wk_end"  in ''|*[!0-9]*)  wk_end=0   ;; esac
case "$out_tok" in ''|*[!0-9]*) out_tok=0 ;; esac

# SCHEMA FALLBACK, added 2026-08-22 — the ctx instrument had gone dark.
# Claude Code stopped sending `.context_window.used_percentage`. Captured with
# the debug hook above, the object now carries only:
#   {"total_input_tokens":453184,"total_output_tokens":2186,
#    "context_window_size":1000000,"current_usage":{...}}
# With the key absent, ctx_pct stayed -1 and the instrument rendered "ctx —".
#
# This is NOT a return of the transcript-tailing bug the header warns about.
# That bug read the last usage record out of a DIFFERENT file, which was stale
# by construction and wrong after /compact. These two numbers are the server's
# own, in the SAME payload, for THIS render — the same pair already printed as
# "453k/1M" beside the percentage. Deriving one from the other cannot disagree
# with what is on screen.
#
# The server's own key still wins whenever it is present, so if it comes back
# this line silently stops firing.
if [ "$ctx_pct" -lt 0 ] && [ "$ctx_tok" -gt 0 ] && [ "$ctx_win" -gt 0 ]; then
  ctx_pct=$(( ctx_tok * 100 / ctx_win ))
fi

# printf's %()T is a bash 4.2+ builtin and saves a date fork per render — but
# macOS ships /bin/bash 3.2.57, where it fails with
#   printf: `(': invalid format character
# and BOTH time fields come out empty, which blanks the clock and makes every
# countdown read "now". The shebang here is `env bash`, so today this resolves
# to Homebrew's 5.3 and the builtin works; it would break the moment this file
# is run as `/bin/bash statusline.sh`, or on a machine without Homebrew bash.
# One fork a second is not worth that, so the builtin is used only where it
# exists. Reproduced 2026-08-09 by running the script under /bin/bash.
if [ "${BASH_VERSINFO[0]:-0}" -ge 5 ] 2>/dev/null || \
   { [ "${BASH_VERSINFO[0]:-0}" -eq 4 ] && [ "${BASH_VERSINFO[1]:-0}" -ge 2 ]; } 2>/dev/null; then
  printf -v now   '%(%s)T'    -1        # builtin, no fork
  printf -v clock '%(%H:%M)T' -1
else
  IFS=' ' read -r now clock <<<"$(date +'%s %H:%M')"
fi

# TEST SEAM. The cat's expressions are keyed to wall-clock seconds on purpose
# (see the two-clock note in the pose block), which makes them unwatchable from
# a harness: rendering sixty frames in a loop takes about a second of real time,
# so every blink cycle collapses and the preview shows a cat that never blinks
# while the live one blinks fine. With $STATUSLINE_NOW set, a test can hand this
# script the second it is pretending to be and step it forward one frame at a
# time. Unset in every real render, so the live path is untouched.
if [ -n "${STATUSLINE_NOW:-}" ]; then
  case "$STATUSLINE_NOW" in
    ''|*[!0-9]*) ;;
    *) now="$STATUSLINE_NOW"
       if [ "${BASH_VERSINFO[0]:-0}" -ge 5 ] 2>/dev/null; then
         printf -v clock '%(%H:%M)T' "$now"
       fi ;;
  esac
fi

# ── terminal width ───────────────────────────────────────────────────────────
cols=0
{ read -r _rows cols < <(stty size < /dev/tty); } 2>/dev/null || cols=0
case "$cols" in ''|*[!0-9]*) cols=0 ;; esac
[ "$cols" -lt 20 ] && cols="${COLUMNS:-120}"
case "$cols" in ''|*[!0-9]*) cols=120 ;; esac
[ "$cols" -lt 20 ] && cols=120

# ── rate-limit cache: one record per session, merged on read ─────────────────
# rate_limits is "only present for subscribers after first API response", so a
# brand-new session has none; this holds the last known pair so it shows real
# figures immediately instead of two dashes. Builtins only, no jq, no forks.
#
# ONE FILE PER SESSION. A single shared file meant last-writer-wins, and every
# open session rewrites this about once a second. Measured 2026-08-22 with six
# sessions open: the shared file alternated several times a second between
# "18 1787314200 61 …" and "17 1787400600 86 …", and the first of those was a
# day stale — its five-hour window had closed 23 hours earlier. Anything
# reading the file saw 61% weekly half the time when the truth was 86%.
#
# MERGE RULE, applied per field, in this order:
#   1. drop any record whose reset epoch has already passed; that window closed
#   2. newest reset epoch wins — a later window is strictly the fresher reading
#   3. same epoch, higher percentage wins — usage only climbs within a window
# The percentage alone is NOT the discriminator. In the sample above the stale
# record read 18% against the live record's 17%, so "take the highest" picks
# the wrong one.
#
# MERGED PER FIELD, not wholesale: five_hour and seven_day are INDEPENDENTLY
# optional, so a payload can carry one and not the other, and overwriting on
# either present would clobber a known-good value with -1. That is why this
# session's own previous record is folded in BEFORE the write.
now_s="${EPOCHSECONDS:-0}"
c1=-1; c2=0; c3=-1; c4=0
{ read -r c1 c2 c3 c4 _ < "$RL_DIR/${sid:-unknown}"; } 2>/dev/null || true
case "$c1$c2$c3$c4" in ''|*[!0-9\ -]*) c1=-1; c2=0; c3=-1; c4=0 ;; esac
[ "$blk_pct" -ge 0 ] 2>/dev/null || { blk_pct="$c1"; blk_end="$c2"; }
[ "$wk_pct"  -ge 0 ] 2>/dev/null || { wk_pct="$c3";  wk_end="$c4";  }
if [ "$blk_pct" -ge 0 ] 2>/dev/null || [ "$wk_pct" -ge 0 ] 2>/dev/null; then
  [ -d "$RL_DIR" ] || mkdir -p "$RL_DIR" 2>/dev/null
  { printf '%s %s %s %s %s\n' "$blk_pct" "$blk_end" "$wk_pct" "$wk_end" "$now_s" \
      > "$RL_DIR/${sid:-unknown}"; } 2>/dev/null || true
fi
# The merge. Every record, including the one just written, so a session whose
# own window has expired stops showing its own stale figure.
m1=-1; m2=0; m3=-1; m4=0
for _rl in "$RL_DIR"/*; do
  [ -f "$_rl" ] || continue
  r1=-1; r2=0; r3=-1; r4=0
  { read -r r1 r2 r3 r4 _ < "$_rl"; } 2>/dev/null || continue
  case "$r1$r2$r3$r4" in ''|*[!0-9\ -]*) continue ;; esac
  if [ "$r1" -ge 0 ] 2>/dev/null && [ "$r2" -gt "$now_s" ] 2>/dev/null; then
    if [ "$r2" -gt "$m2" ] 2>/dev/null ||
       { [ "$r2" -eq "$m2" ] && [ "$r1" -gt "$m1" ]; } 2>/dev/null; then
      m1="$r1"; m2="$r2"
    fi
  fi
  if [ "$r3" -ge 0 ] 2>/dev/null && [ "$r4" -gt "$now_s" ] 2>/dev/null; then
    if [ "$r4" -gt "$m4" ] 2>/dev/null ||
       { [ "$r4" -eq "$m4" ] && [ "$r3" -gt "$m3" ]; } 2>/dev/null; then
      m3="$r3"; m4="$r4"
    fi
  fi
done
[ "$m1" -ge 0 ] 2>/dev/null && { blk_pct="$m1"; blk_end="$m2"; }
[ "$m3" -ge 0 ] 2>/dev/null && { wk_pct="$m3";  wk_end="$m4";  }

# ── model short name ─────────────────────────────────────────────────────────
# Most-specific first; the generic *opus*/*sonnet* fallbacks LAST so a new
# minor version degrades to "Opus" rather than a bare "?", and a payload with
# no model at all degrades to "Claude".
model_short="${model_name:-}"
case "$model_id" in
  *fable-5*)     model_short="Fable 5"   ;;
  *opus-5*)      model_short="Opus 5"    ;;
  *opus-4-8*)    model_short="Opus 4.8"  ;;
  *opus-4-7*)    model_short="Opus 4.7"  ;;
  *opus-4-6*)    model_short="Opus 4.6"  ;;
  *opus-4-5*)    model_short="Opus 4.5"  ;;
  *opus*)        model_short="Opus"      ;;
  *sonnet-5*)    model_short="Sonnet 5"  ;;
  *sonnet-4-7*)  model_short="Sonnet 4.7";;
  *sonnet-4-6*)  model_short="Sonnet 4.6";;
  *sonnet-4-5*)  model_short="Sonnet 4.5";;
  *sonnet*)      model_short="Sonnet"    ;;
  *haiku-4-5*)   model_short="Haiku 4.5" ;;
  *haiku*)       model_short="Haiku"     ;;
esac
[ -z "$model_short" ] && model_short="Claude"

# ── project + branch, cached ─────────────────────────────────────────────────
# Two git calls were fine on the old event-driven schedule; at 1 Hz, `git
# status` on a large repo is the one thing here that can miss the beat. Cached
# for GIT_TTL seconds, keyed by cwd so switching projects refreshes at once.
GIT_CACHE="$CACHE/statusline.git.$sid"
git_root=""; project=""; branch=""; dirty=""; folder=""
g_at=0; g_cwd=""; g_root=""; g_branch=""; g_dirty=""
{ IFS=$'\x1f' read -r g_at g_cwd g_root g_branch g_dirty < "$GIT_CACHE"; } 2>/dev/null || true
case "$g_at" in ''|*[!0-9]*) g_at=0 ;; esac
if [ "$g_cwd" = "$cwd" ] && [ $(( now - g_at )) -lt "$GIT_TTL" ]; then
  git_root="$g_root"; branch="$g_branch"; dirty="$g_dirty"
else
  if git_info=$(git -C "$cwd" rev-parse --show-toplevel --abbrev-ref HEAD 2>/dev/null); then
    git_root="${git_info%%$'\n'*}"    # line 1 (pure bash, was two sed forks)
    branch="${git_info#*$'\n'}"       # line 2
  fi
  if [ -n "$git_root" ]; then
    [ "$branch" = "HEAD" ] && branch=$(git -C "$cwd" rev-parse --short HEAD 2>/dev/null)
    [ -n "$(git -C "$cwd" --no-optional-locks status --porcelain -uno 2>/dev/null | head -c 1)" ] && dirty="*"
  fi
  { printf '%s\x1f%s\x1f%s\x1f%s\x1f%s\n' \
      "$now" "$cwd" "$git_root" "$branch" "$dirty" > "$GIT_CACHE"; } 2>/dev/null || true
fi
if [ -n "$git_root" ]; then
  project="${git_root##*/}"
else
  folder="${cwd##*/}"
  [ -z "$folder" ] && folder="~"
fi

# ── colours ──────────────────────────────────────────────────────────────────
# NODIM leads every row — see the WIDTH section: Claude Code wraps each row in
# \033[2m, and without cancelling it the whole statusline renders washed out.
# Eighths ramp, shared by the bar sparkline and the equalizer stage.
BLK='▁▂▃▄▅▆▇█'

RST=$'\033[0m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; NODIM=$'\033[22m'
C_MODEL=$'\033[95m'   # bright magenta (color13) — model name
C_PROJ=$'\033[34m'    # blue          (color4)  — project / folder
C_BRANCH=$'\033[36m'  # cyan          (color6)  — git branch
C_HOT=$'\033[91m'     # bright red    (color9)  — dirty *, gauges >=80%
C_SEP=$'\033[90m'     # bright black  (color8)  — separators, dim text
C_CALM=$'\033[36m'    # cyan          (color6)  — gauges <50%
C_WARM=$'\033[33m'    # yellow        (color3)  — gauges 50-79%

pct_color() {
  if   [ "$1" -ge 80 ] 2>/dev/null; then PCOL="$C_HOT"
  elif [ "$1" -ge 50 ] 2>/dev/null; then PCOL="$C_WARM"
  else PCOL="$C_CALM"
  fi
}

# 5-cell gauge → $GAUGE. printf -v, NOT $(printf …): every $(…) is a fork and
# this runs twice per render. Width 3 keeps the two bars aligned.
gauge() {
  local pct=$1 fill i
  pct_color "$pct"
  fill=$(( (pct * 5 + 50) / 100 ))
  [ "$fill" -gt 5 ] && fill=5; [ "$fill" -lt 0 ] && fill=0
  GAUGE="$PCOL"
  for (( i = 0; i < fill; i++ ));  do GAUGE+="▰"; done
  GAUGE+="$C_SEP"
  for (( i = fill; i < 5; i++ ));  do GAUGE+="▱"; done
  printf -v p3 '%3d' "$pct"
  GAUGE+="$PCOL$p3%$RST"
}

# resets_at (epoch) → compact countdown, pure bash. No spaces: a segment that
# never contains a space cannot be split by the packer below.
countdown() {
  local end=$1 left
  CD=""
  [ "$end" -gt 0 ] 2>/dev/null || return
  left=$(( end - now ))
  if   [ "$left" -le 0 ];     then CD="now"
  elif [ "$left" -lt 3600 ];  then CD="$((left / 60))m"
  elif [ "$left" -lt 86400 ]; then CD="$((left / 3600))h$(((left % 3600) / 60))m"
  else                             CD="$((left / 86400))d$(((left % 86400) / 3600))h"
  fi
}

# integer → 172417:1000000 → "172k/1M". Pure bash; the old version forked awk.
human() {  # human <n> -> $H
  local n=$1
  if   [ "$n" -ge 1000000 ]; then
    local m=$(( n / 100000 ))            # tenths of a million
    if [ $(( m % 10 )) -eq 0 ]; then H="$(( m / 10 ))M"; else H="$(( m / 10 )).$(( m % 10 ))M"; fi
  elif [ "$n" -ge 1000 ];    then H="$(( n / 1000 ))k"
  else                            H="$n"
  fi
}

# ── effort ───────────────────────────────────────────────────────────────────
# THE WORD "effort", SPELLED OUT. This used to be a ramp glyph plus the level:
# ▁low ▃medium ▅high ▆xhigh █max. It read to Ayush, 2026-08-09, as "this yellow
# box just sitting there, idk for what" — and he was right. A block glyph in a
# bar full of block glyphs (the two ▰▱ gauges) does not say "reasoning effort",
# it says "some meter, presumably". The gauges earn their blocks because they
# are proportions; a five-value enum is not a proportion, and the ramp was
# encoding it twice — once in a shape nobody can decode, once in a word that was
# already there. The word carries it now, with the level in colour.
#
# Published to $CACHE/effort for ~/.claude/subagent-statusline.sh. The SUBAGENT
# payload does not carry the session effort (captured live: no such key on any
# task row), so an agent that inherits the session's level has no other honest
# source. One builtin redirect, no fork.
# KEYED BY SESSION, not one shared file. Several Claude sessions run at once
# here and each writes this every second; a single path is last-writer-wins, so
# an agent panel could report the effort of whichever OTHER session rendered
# most recently — wrong information on the one display whose entire job is
# saying what things run at. The subagent script reads effort.<session_id>.
{ printf '%s\n' "$effort" > "$CACHE/effort.$sid"; } 2>/dev/null || true
eff_render=""; eff_len=0
case "$effort" in
  low)    eff_render="${C_SEP}low effort${RST}";     eff_len=10 ;;
  medium) eff_render="${C_CALM}medium effort${RST}"; eff_len=13 ;;
  high)   eff_render="${C_WARM}high effort${RST}";   eff_len=11 ;;
  xhigh)  eff_render="${C_HOT}xhigh effort${RST}";   eff_len=12 ;;
  max)    eff_render="${C_HOT}max effort${RST}";     eff_len=10 ;;
esac

# MOVED ABOVE THE SEGMENTS on 2026-08-10 so the info row can use the same
# numbers the stage does — the live sparkline in the bar is the same token
# history the equalizer draws. Nothing here depends on anything below it.

# ── activity: real tokens per second ─────────────────────────────────────────
# The equalizer is only worth having if it is an INSTRUMENT rather than a
# decoration, so it is driven by `.context_window.total_output_tokens`
# differenced against the previous render. That is genuine throughput: it
# spikes while Claude is writing and sits flat while it is thinking or waiting
# on a tool, which is exactly the distinction that is invisible in a spinner.
#
# State lives in one line beside the cat's: previous token count, the clock at
# that point, and a history string with ONE DIGIT PER COLUMN. A digit string is
# the whole trick — shifting a fixed-width window of samples is a single
# parameter expansion, where an array would need a loop and a rewrite every
# tick.
# Renamed from statusline.scene.* when the latch fields were added: a stale
# three-field file would have been read as a five-field one and mis-latched.
SCENE_STATE="$CACHE/statusline.stage.$sid"
p_tok=0; p_now=0; fired=0; train_until=0; hist=""
{ read -r p_tok p_now fired train_until hist < "$SCENE_STATE"; } 2>/dev/null || true
case "$fired"       in ''|*[!0-9]*) fired=0 ;; esac
case "$train_until" in ''|*[!0-9]*) train_until=0 ;; esac
case "$p_tok" in ''|*[!0-9]*) p_tok=0 ;; esac
case "$p_now" in ''|*[!0-9]*) p_now=0 ;; esac
case "$hist"  in *[!0-9]*)    hist=""  ;; esac

d_tok=$(( out_tok - p_tok )); [ "$d_tok" -lt 0 ] && d_tok=0
d_sec=$(( now - p_now ));     [ "$d_sec" -lt 1 ] && d_sec=1
[ "$p_now" -eq 0 ] && d_tok=0                 # first render has nothing to diff
rate=$(( d_tok / d_sec ))

# tok/s -> 0..8, coarsely logarithmic. Claude streams in the low hundreds when
# it is going, so a linear scale would peg or flatline; these breakpoints keep
# the bar readable across two orders of magnitude.
lvl=0
if   [ "$rate" -ge 400 ]; then lvl=8
elif [ "$rate" -ge 250 ]; then lvl=7
elif [ "$rate" -ge 150 ]; then lvl=6
elif [ "$rate" -ge  90 ]; then lvl=5
elif [ "$rate" -ge  50 ]; then lvl=4
elif [ "$rate" -ge  25 ]; then lvl=3
elif [ "$rate" -ge  10 ]; then lvl=2
elif [ "$rate" -ge   1 ]; then lvl=1
fi

# Idle = no output tokens for a while. Tracked in the history string itself
# rather than as another counter: if the last 30 samples are all 0, nothing has
# been generated for ~30 renders.
idle=1
case "${hist: -30}" in *[1-9]*) idle=0 ;; esac
[ "$lvl" -gt 0 ] && idle=0

# DECAY, NOT A CLIFF. The raw sample is 0 for every second Claude is not
# generating, so a burst dropped straight to the floor on the very next column
# and the ground came out as a flat line with occasional towers — which is
# exactly what it looked like on screen. Storing max(now, previous - 1) gives
# each burst a slope down instead of a wall. The value is still bounded by real
# throughput and nothing is invented; it just remembers for a few seconds,
# which is what turns genuine activity into terrain rather than a bar chart.
#
# NOTE this runs AFTER `idle` is computed above, deliberately: idle must judge
# the raw samples, or a decaying tail would keep the session looking busy for
# several seconds after it went quiet.
prev_lvl=0
[ "${#hist}" -gt 0 ] && prev_lvl="${hist: -1}"
case "$prev_lvl" in ''|*[!0-9]*) prev_lvl=0 ;; esac
decayed=$(( prev_lvl > 0 ? prev_lvl - 1 : 0 ))
[ "$lvl" -lt "$decayed" ] && lvl="$decayed"
hist+="$lvl"
# One history sample per terrain column, so `hist` and the stage are the same
# width — the ground has to reach the whole way under the cat.
SW=$(( cols - 2 )); [ "$SW" -lt 8 ] && SW=8; [ "$SW" -gt 200 ] && SW=200
# TRIM ONLY WHEN IT IS ACTUALLY TOO LONG. `${hist: -$SW}` is NOT Python
# slicing: when SW exceeds the string length bash returns the EMPTY STRING, not
# the whole string, so the history was being wiped on every render and the
# equalizer drew four blank rows for a session that was streaming 220 tok/s.
# Caught by printing the state file, which read `2760 1786334997 ` with nothing
# after the timestamp.
[ "${#hist}" -gt "$SW" ] && hist="${hist: -$SW}"
# The SAVE lives after scene selection, not here — see the note at the bottom
# of the selection block.

# ── segments ─────────────────────────────────────────────────────────────────
# Each segment is carried as (text, visible length, priority). Lengths are
# accumulated as the text is built rather than measured afterwards: stripping
# SGR to count cells needs either a fork or fragile pattern work, and we
# already know every piece we concatenate.
#
# priority 0 = never dropped · 1 = dropped only in a very narrow pane ·
# 2 = the first to go.
seg_txt=(); seg_len=(); seg_pri=()
add() { seg_txt+=("$1"); seg_len+=("$2"); seg_pri+=("$3"); }

# model · effort · fast · agent
s="${C_MODEL} ${BOLD}${model_short}${RST}"; n=$(( ${#model_short} + 3 ))
if [ -n "$eff_render" ]; then s+=" $eff_render"; n=$(( n + 1 + eff_len )); fi
[ "$fastmode" = "true" ] && { s+=" ${C_WARM}fast${RST}"; n=$(( n + 5 )); }
[ -n "$agent_name" ] && { s+=" ${C_MODEL}${agent_name}${RST}"; n=$(( n + 1 + ${#agent_name} )); }
add "$s" "$n" 0

# project » branch
if [ -n "$git_root" ]; then
  add "${C_PROJ} ${project}${RST}${C_SEP} » ${RST}${C_BRANCH} ${branch}${RST}${C_HOT}${dirty}${RST}" \
      $(( ${#project} + ${#branch} + ${#dirty} + 7 )) 1
else
  add "${C_PROJ} ${folder}${RST}" $(( ${#folder} + 2 )) 1
fi

# context
if [ "$ctx_pct" -ge 0 ] 2>/dev/null; then
  pct_color "$ctx_pct"
  s="${PCOL} ctx ${ctx_pct}%${RST}"; n=$(( ${#ctx_pct} + 7 ))
  if [ "$ctx_tok" -gt 0 ] && [ "$ctx_win" -gt 0 ]; then
    human "$ctx_tok"; t="$H"; human "$ctx_win"; w="$H"
    s+=" ${DIM}${t}/${w}${RST}"; n=$(( n + 2 + ${#t} + ${#w} ))
  fi
  # exceeds_200k_tokens is a fact about pricing, not about the window — a hint
  # beside a percentage that stays true. Never an override; see the header.
  [ "$exceeds" = "true" ] && { s+=" ${C_SEP}▲${RST}"; n=$(( n + 2 )); }
  add "$s" "$n" 0
else
  add "${C_SEP} ctx —${RST}" 7 0
fi

# plan gauges
[ "$toggle_plan" = "false" ] || toggle_plan=true    # parsed above, in the one jq
if [ "$toggle_plan" = "true" ]; then
  if [ "$blk_pct" -ge 0 ] 2>/dev/null; then
    gauge "$blk_pct"; countdown "$blk_end"
    s="${C_SEP} 5h${RST} ${GAUGE}"; n=15
    [ -n "$CD" ] && { s+=" ${C_SEP}· ${CD}${RST}"; n=$(( n + 3 + ${#CD} )); }
    add "$s" "$n" 1
  else
    add "${C_SEP} 5h —${RST}" 6 2
  fi
  if [ "$wk_pct" -ge 0 ] 2>/dev/null; then
    gauge "$wk_pct"; countdown "$wk_end"
    s="${C_SEP} wk${RST} ${GAUGE}"; n=15
    [ -n "$CD" ] && { s+=" ${C_SEP}· ${CD}${RST}"; n=$(( n + 3 + ${#CD} )); }
    add "$s" "$n" 1
  else
    add "${C_SEP} wk —${RST}" 6 2
  fi

  # ── the per-model weekly cap (the Fable one) ───────────────────────────────
  # NOT IN THE PAYLOAD, and not where the obvious lookup puts it either. The
  # statusline payload carries exactly `.rate_limits.five_hour` and
  # `.rate_limits.seven_day`. ~/.claude.json has a `seven_day_opus` key and it
  # is genuinely null — I read it, reported "your plan has no such limit", and
  # was wrong, because the figure /usage shows lives in a differently shaped
  # place: the usage endpoint returns a `limits` ARRAY whose per-model entry is
  # identified by kind + scope, not by key name:
  #     {"kind":"weekly_scoped","percent":5,
  #      "scope":{"model":{"display_name":"Fable"}}}
  # Checking one named field and concluding the data does not exist is the
  # mistake this comment is here to stop being repeated.
  #
  # ~/.claude/usage-refresh.sh fetches it and writes one line to $FABLE_CACHE.
  # This reads that line with a builtin, and when it goes stale it re-launches
  # the fetcher DETACHED — the statusline's own contract is that nothing in it
  # ever blocks on the network, and a background spawn honours that literally.
  #
  # THE FETCHER WAS NEVER ONCE LAUNCHED. From the day this gauge shipped until
  # 2026-08-12 it showed 5%, frozen, because the spawn was written as
  #
  #     { setsid "$HOME/.claude/usage-refresh.sh" >/dev/null 2>&1 & } 2>/dev/null \
  #       || { "$HOME/.claude/usage-refresh.sh" >/dev/null 2>&1 & } 2>/dev/null
  #
  # and BOTH halves of that are wrong at once:
  #   1. macOS HAS NO setsid. It is a util-linux command; there is no such
  #      binary in /usr/bin or in Homebrew's prefix here.
  #   2. THE FALLBACK CANNOT FIRE. `{ cmd & }` reports the success of *starting*
  #      a background job, never the exit status of the job, so the list is 0
  #      whatever happens inside it. Verified directly:
  #        bash -c '{ setsid /bin/echo hi & } || { echo FALLBACK; }; wait; echo $?'
  #      prints only `0` — no FALLBACK line. The 127 died in the child.
  # So every render since has silently forked a `setsid: command not found` and
  # the cache kept whatever number was in it from the last hand-run — 5%, dated
  # 2026-08-10 01:47, still on screen two days later.
  #
  # No setsid is needed to detach on macOS. Backgrounding plus a `disown`
  # already reparents the child when this process exits a few milliseconds
  # later, and the three redirections are what actually matter: stdout is the
  # statusline's own pipe to Claude Code and must not be inherited or the pipe
  # stays open, and </dev/null keeps the child off the payload pipe on stdin.
  #
  # THE TTL GATE IS ON THE ATTEMPT, NOT ON THE RESULT. $FABLE_CACHE is written
  # only on SUCCESS, so gating the spawn on its timestamp alone means a fetch
  # that fails — offline, expired token, API 500 — never advances the clock and
  # every subsequent render spawns another. At 1 Hz in each of up to ten open
  # sessions, with curl's max-time at 10 s, that is a permanent standing herd of
  # ~100 curls for as long as the failure lasts. The stamp is written BEFORE the
  # spawn, so a failing fetch is retried on FABLE_RETRY, not on every tick.
  FABLE_CACHE="$CACHE/fablelimit"
  FABLE_STAMP="$CACHE/fablelimit.attempt"
  FABLE_TTL=300      # seconds a good figure is considered fresh
  FABLE_RETRY=60     # floor between two fetch attempts, successful or not
  f_at=0; f_pct=-1; f_end=0; f_name=""
  { IFS=$'\t' read -r f_at f_pct f_end f_name < "$FABLE_CACHE"; } 2>/dev/null || true
  case "$f_at"  in ''|*[!0-9]*) f_at=0  ;; esac
  case "$f_pct" in ''|*[!0-9]*) f_pct=-1 ;; esac
  case "$f_end" in ''|*[!0-9]*) f_end=0 ;; esac
  a_at=0
  { read -r a_at < "$FABLE_STAMP"; } 2>/dev/null || true
  case "$a_at" in ''|*[!0-9]*) a_at=0 ;; esac
  if [ $(( now - f_at )) -ge "$FABLE_TTL" ] && [ $(( now - a_at )) -ge "$FABLE_RETRY" ]; then
    { printf '%s\n' "$now" > "$FABLE_STAMP"; } 2>/dev/null || true
    { "$HOME/.claude/usage-refresh.sh" </dev/null >/dev/null 2>&1 & } 2>/dev/null
    disown 2>/dev/null || true
  fi
  if [ "$f_pct" -ge 0 ] 2>/dev/null; then
    [ -z "$f_name" ] && f_name="model"
    gauge "$f_pct"; countdown "$f_end"
    s="${C_SEP} ${f_name}${RST} ${GAUGE}"; n=$(( 13 + ${#f_name} ))
    [ -n "$CD" ] && { s+=" ${C_SEP}· ${CD}${RST}"; n=$(( n + 3 + ${#CD} )); }
    add "$s" "$n" 1
  fi
fi

# ── the bar animates too ─────────────────────────────────────────────────────
# Ayush, 2026-08-10: the info row "looks plane itself with no animation or
# something similar within itself. put some small kind of something always
# doing animation".
#
# Two things move, and NEITHER is a mystery glyph — that was the lesson of the
# effort ramp, which he read as "this yellow box just sitting there, idk for
# what". An ornament that has to be explained is worse than a still bar.
#
#   the colon blinks   a digital clock blinking its colon is the most
#                      universally understood always-on animation there is,
#                      and it is honest: it is a clock, and it is ticking.
#
#   a live sparkline   the last eight samples of the SAME token-rate history
#                      the equalizer draws, five cells wide. It moves whenever
#                      Claude is doing anything, and it says something while
#                      it moves. Hidden entirely when idle rather than sitting
#                      there flat, so it never becomes furniture.
#
# Both are functions of the wall clock, not of a render counter, which is
# deliberate: renders arrive irregularly (1 Hz idle, ~3 Hz busy) and a counter
# would make the colon stutter. The header rule — a frame must still be TRUE
# after sitting for thirty seconds — is untouched, because neither of these
# asserts anything that can go stale.
spark=""; spark_n=0
if [ "${#hist}" -gt 0 ]; then
  tail8="${hist: -8}"
  [ "${#hist}" -lt 8 ] && tail8="$hist"
  for (( i = 0; i < ${#tail8}; i++ )); do
    v="${tail8:$i:1}"
    [ "$v" -gt 0 ] 2>/dev/null && spark+="${BLK:$(( v * 8 / 10 )):1}" || spark+="${DIM}·${C_CALM}"
    spark_n=$(( spark_n + 1 ))
  done
fi
if [ "$rate" -gt 0 ] && [ "$spark_n" -gt 0 ]; then
  human "$rate"
  add "${C_CALM}${spark}${RST} ${DIM}${H}/s${RST}" $(( spark_n + 2 + ${#H} )) 2
fi

# The colon is the animation; ${clock} already holds HH:MM.
if [ $(( now % 2 )) -eq 0 ]; then
  add "${C_SEP} ${clock}${RST}" 7 2
else
  add "${C_SEP} ${clock/:/ }${RST}" 7 2
fi

# ── pack segments into rows ──────────────────────────────────────────────────
# Greedy, order-preserving, separator-aware. Wide window → one row. Narrow
# split → two or three. Very narrow → low-priority segments dropped outright,
# because a dropped clock is honest and a truncated gauge is not.
SEPW=3
sep="${C_SEP} │ ${RST}"
# A PULSE TRAVELS ALONG THE BAR. Ayush asked twice for "some kind of animation
# within this line itself", and the blinking colon alone was too quiet to
# register. One separator at a time is lit while the rest stay dim, and the lit
# one advances every second — a highlight walking the length of the bar. It
# reads as a pulse rather than as a glyph that needs explaining, which was the
# whole lesson of the effort ramp he called "this yellow box".
#
# Driven by the wall clock, not a render counter: renders arrive irregularly
# and a counter would make the pulse stutter. It asserts nothing, so it cannot
# go stale in the way a number can.
sep_hot="${C_WARM} │ ${RST}"
sep_i=0
budget=$(( cols - 1 ))
maxrows=3
[ "$cols" -lt 60 ] && maxrows=4

rows=(); row=""; rowlen=0; nrows=1
for i in "${!seg_txt[@]}"; do
  t="${seg_txt[$i]}"; l="${seg_len[$i]}"; p="${seg_pri[$i]}"
  # A segment that cannot fit a row on its own is dropped, never truncated.
  [ "$l" -gt "$budget" ] && continue
  if [ -z "$row" ]; then
    row="$t"; rowlen="$l"; continue
  fi
  if [ $(( rowlen + SEPW + l )) -le "$budget" ]; then
    if [ $(( sep_i % 7 )) -eq $(( now % 7 )) ]; then
      row+="${sep_hot}${t}"
    else
      row+="${sep}${t}"
    fi
    sep_i=$(( sep_i + 1 ))
    rowlen=$(( rowlen + SEPW + l ))
  elif [ "$nrows" -lt "$maxrows" ]; then
    rows+=("$row"); row="$t"; rowlen="$l"; nrows=$(( nrows + 1 ))
  elif [ "$p" -eq 0 ]; then
    # A must-keep segment with nowhere to go takes one more row anyway.
    rows+=("$row"); row="$t"; rowlen="$l"; nrows=$(( nrows + 1 ))
  fi
  # anything else: dropped
done
[ -n "$row" ] && rows+=("$row")
for r in "${rows[@]}"; do printf '%s%s\n' "$NODIM" "$r"; done

# ── the cat ──────────────────────────────────────────────────────────────────
# Nine cells wide, four rows tall, walking a stage as wide as the pane — twice
# the footprint of the old three-row, seven-cell cat, and it actually travels.
#
# EVERY LINE OF ART HERE WAS SHAPED against the live font with
# ~/.config/kitty/check-art before it shipped. That is not optional and a width
# check cannot replace it: JetBrains Mono renders a ligature as one glyph PER
# CELL, replacing the first character with a BLANK spacer glyph (`SPC`) and the
# second with the combined `*.liga` glyph. Cell counts therefore survive
# intact, and the only symptom is that a whisker silently becomes whitespace —
# which is exactly how `=^.^=` loses its right cheek to `asciicircum_equal`.
#
# One rule in the older files is too strict, and check-art proves it: `__`
# ligates BETWEEN LETTERS (a__b → SPC + underscore_underscore.liga) but NOT
# beside slashes. `/\___/\` shapes to seven clean glyphs, which is what lets
# this cat be wider than the old one.
#
# ── THE CAT ─────────────────────────────────────────────────────────────────
#
# THE CAMERA NEVER LEAVES THE FRONT, and that is the central decision here.
#
# Rebuilt 2026-08-10 after Ayush split his verdict cleanly: "i like the cat
# expressions though" against "i'm still not satisfied with the walking". The
# expressions are all the front sprite. The walking was dominated by a side
# profile — and the profile was on screen for roughly 40% of renders, so the
# face he liked was absent nearly half the time, replaced by a long, low,
# one-eared shape whose `(o>` muzzle read as a beak. Deleting the profile
# doubles the screen time of the one asset that has been approved at every
# iteration, which is a better answer than any redraw of it.
#
# What replaces walking is HOPPING, and the reason is the medium rather than
# taste. At one render per second there is no apparent motion: a walk cycle is
# a high-frequency signal sampled at 1 Hz, and what comes back is aliasing. The
# old walk made that concrete — rows 0-2 were pixel-identical for eight
# consecutive renders while the leg row changed 100% of its marks every render,
# so the loud signal was a flicker and the quiet one was a body sliding 1/9th
# of its own length. It read as vibrating, not walking.
#
# A hop has one channel and it is the motion channel: between the two poses
# every element translates rigidly by (+3, -1) — ears, eyes and paws all move
# together — and the body covers a third of its own length per frame. Nothing
# alternates except the thing that is moving.
#
# THE VERTICAL GRAMMAR, which is what makes this fit in four rows:
#     row 0 blank  =  standing on the ground
#     row 3 blank  =  in the air
# The shipped loaf already proved the body can re-lie inside the fixed stage.
# No fifth row is needed, and picasso explicitly declined one when offered.
#
# DIRECTION IS CARRIED BY THE SIGN OF dx AND NOTHING ELSE. At 1 fps no drawing
# communicates heading between frames anyway — the viewer reads "the cat is
# elsewhere now" — so the profile was only ever pretending to encode it.
#
# STATE, one line, all integers, builtins only, keyed by session_id.
#   x      left cell of the cat
#   dirn   +1 or -1, the direction of the current traversal
#   mode   0 rest · 1 hop · 2 scamper · 3 pounce · 4 stretch · 5 yawn
#          6 sleep · 7 moth
#   step   frame index inside the current motion
#   until  wall-clock second a held mode ends
#   tgt    the column a traversal is heading for
#   f      render counter
#   seed   carried PRNG state
CAT_STATE="$CACHE/statusline.cat.$sid"

YARD_L=2
_yw=$(( cols / 3 ))
[ "$_yw" -gt 40 ] && _yw=40
[ "$_yw" -lt $(( CAT_W + 6 )) ] && _yw=$(( CAT_W + 6 ))
YARD_R=$(( YARD_L + _yw - CAT_W ))
[ "$YARD_R" -lt "$YARD_L" ] && YARD_R="$YARD_L"

x=-1; dirn=1; mode=9; step=0; until_s=0; tgt=-1; f=0; seed=0
{ read -r x dirn mode step until_s tgt f seed < "$CAT_STATE"; } 2>/dev/null || true
case "$x"       in ''|*[!0-9-]*) x=-1 ;; esac
case "$dirn"    in 1|-1) ;; *) dirn=1 ;; esac
case "$mode"    in 0|1|2|3|4|5|6|7) ;; *) mode=9 ;; esac
case "$step"    in ''|*[!0-9]*) step=0 ;; esac
case "$until_s" in ''|*[!0-9]*) until_s=0 ;; esac
case "$tgt"     in ''|*[!0-9-]*) tgt=-1 ;; esac
case "$f"       in ''|*[!0-9]*) f=0 ;; esac
case "$seed"    in ''|*[!0-9]*) seed=0 ;; esac
[ "$x" -lt "$YARD_L" ] && x="$YARD_L"
[ "$x" -gt "$YARD_R" ] && x="$YARD_R"

rnd() {  # rnd <mod> -> $R   — carried PRNG; $RANDOM reseeds per process
  seed=$(( (seed * 1103515245 + 12345 + now) & 0x7fffffff ))
  R=$(( (seed >> 8) % $1 ))
}

f=$(( f + 1 ))
x_before="$x"

# ── the sequencer ────────────────────────────────────────────────────────────
# MOTIONS ARE ATOMIC. Once one begins it runs to completion; nothing may
# interrupt it. This is not tidiness — the previous cat had no such rule and its
# groom oscillated paw-at-muzzle / paw-over-ear on a two-second loop with 50/50
# duty, a stationary body flipping A-B-A-B forever. That is the strobe the whole
# design forbids, and it shipped, because a scheduler that re-rolls every few
# seconds turns any two-frame gesture into a loop.
new_target() {
  local span=$(( YARD_R - YARD_L )) mid d mind
  if [ "$span" -lt 3 ]; then tgt="$x"; return; fi
  # Draw from the half of the yard the cat is NOT in: one draw, always valid,
  # self-scaling. A rejection loop looked equivalent and collapsed on narrow
  # panes, where the minimum equalled the span and the fallback fired every
  # time — a metronome ping-ponging end to end in exactly the split panes in use.
  mid=$(( YARD_L + span / 2 ))
  if [ "$x" -le "$mid" ]; then
    rnd $(( YARD_R - mid + 1 )); tgt=$(( mid + R ))
  else
    rnd $(( mid - YARD_L + 1 )); tgt=$(( YARD_L + R ))
  fi
  mind=$(( span / 4 )); [ "$mind" -lt 3 ] && mind=3
  d=$(( tgt - x )); [ "$d" -lt 0 ] && d=$(( -d ))
  if [ "$d" -lt "$mind" ]; then
    if [ "$x" -le "$mid" ]; then tgt="$YARD_R"; else tgt="$YARD_L"; fi
  fi
}

start_traverse() {   # start_traverse <mode 1 hop | 2 scamper>
  new_target
  [ "$tgt" -lt "$x" ] && dirn=-1 || dirn=1
  mode="$1"; step=0
}

rest_for() { mode=0; step=0; rnd "$1"; until_s=$(( now + $2 + R )); }

choose_motion() {
  rnd 100
  if [ "$lvl" -ge 5 ]; then
    # BUSY. Never settle, short rests, locomotion dominant — at ~3 fps the
    # scamper actually fuses into motion, and this is the cadence Ayush is
    # watching. The old cat was at its stillest exactly here.
    if [ "$R" -lt 78 ]; then start_traverse 2
    else mode=3; step=0                      # pounce
    fi
  else
    # WEIGHTS. The pounce and the moth are the memorable acts and they are the
    # ones that spoil fastest if they are common — a surprise that happens every
    # thirty seconds is furniture. The moth at 2% of choices works out to roughly
    # once every few minutes, which is where picasso wanted it; the pounce is
    # rare enough to still be a punchline.
    if   [ "$R" -lt 50 ]; then start_traverse 1                # hop somewhere
    elif [ "$R" -lt 62 ]; then mode=4; step=0                  # stretch
    elif [ "$R" -lt 74 ]; then mode=5; step=0                  # yawn
    elif [ "$R" -lt 79 ]; then mode=3; step=0                  # pounce
    elif [ "$R" -lt 81 ] && [ "$MOTH_OK" -eq 1 ]; then mode=7; step=0
    elif [ "$R" -lt 87 ]; then mode=6; rnd 6; until_s=$(( now + 8 + R ))
    else rest_for 3 2
    fi
  fi
}

# The moth needs 26 clear cells to the right of the cat or it flies off the
# pane and the chase has nothing in it to chase.
MOTH_OK=0
[ $(( cols - YARD_R - CAT_W )) -ge 26 ] && MOTH_OK=1

land=0
case "$mode" in
  0)  [ "$now" -ge "$until_s" ] && choose_motion ;;
  1|2)
    _sp=3; [ "$mode" -eq 2 ] && _sp=2
    x=$(( x + dirn * _sp ))
    step=$(( step + 1 ))
    if { [ "$dirn" -gt 0 ] && [ "$x" -ge "$tgt" ]; } || \
       { [ "$dirn" -lt 0 ] && [ "$x" -le "$tgt" ]; }; then
      # ALWAYS LAND ON A GROUNDED FRAME. Ending a hop on the airborne pose
      # leaves the cat hanging in the air for the whole of the following rest.
      x="$tgt"; land=1; rest_for 3 2
    fi
    ;;
  3)  # pounce: spot, hold, launch, land — the anticipation beat is a HELD
      # frame, so it costs nothing in change budget and buys the whole read
      case "$step" in
        2|3) x=$(( x + dirn * 3 )) ;;
      esac
      step=$(( step + 1 ))
      [ "$step" -ge 4 ] && rest_for 3 2
      ;;
  4|5)  step=$(( step + 1 ))
        [ "$step" -ge 3 ] && rest_for 3 2 ;;
  6)  [ "$now" -ge "$until_s" ] && rest_for 2 2 ;;
  7)  step=$(( step + 1 ))
      case "$step" in 7|8) x=$(( x + 3 )) ;; esac
      [ "$step" -ge 10 ] && rest_for 2 2
      ;;
  *)  choose_motion ;;
esac
[ "$x" -lt "$YARD_L" ] && x="$YARD_L"
[ "$x" -gt "$YARD_R" ] && x="$YARD_R"
dx=$(( x - x_before ))

{ printf '%s %s %s %s %s %s %s %s\n' "$x" "$dirn" "$mode" "$step" "$until_s" \
    "$tgt" "$f" "$seed" > "$CAT_STATE"; } 2>/dev/null || true

# ── the sprites ──────────────────────────────────────────────────────────────
# Every row is EXACTLY CAT_W cells, and a blank row is nine spaces rather than
# the empty string. All 28 unique lines are check-art CLEAN; re-run
# `~/.config/kitty/check-art --file` after ANY edit here, with its positive
# control, because a ligature preserves the cell count and a width check can
# never see one. Known traps in this alphabet: a bare `/\` between spaces
# (slash_backslash.liga), exactly two `_`, and the `^`/`=` family.
#
# Expressions are applied ONLY to the rest pose. The gestures are authored
# frame by frame and must not be overwritten mid-sequence — that is requirement
# one of the sequencer, and the reason the old groom oscillated.
ov=""; ov_row=0; ov_dx=0          # the one-cell overlay: z, moth, dust

blink=0;    [ $(( now % 7 ))  -eq 0 ] && blink=1
earflick=0; [ $(( now % 11 )) -eq 0 ] && earflick=1

set_rest() {
  a1=' /\___/\ '; a2='(  o.o  )'; a3=' >  ^  < '; a4=' U     U '
  [ "$blink" -eq 1 ] && a2='(  -.-  )'
  [ "$earflick" -eq 1 ] && a1=' /\_ _/\ '
  case $(( (now / 3) % 5 )) in
    1) [ "$blink" -eq 0 ] && a2='(    o.o)' ;;
    3) [ "$blink" -eq 0 ] && a2='(o.o    )' ;;
  esac
}

case "$mode" in
  1)  # HOP. Ground doubles as the landing and as the coil for the next bound,
      # so the cycle contains no stationary change at all.
      if [ "$land" -eq 1 ] || [ $(( step % 2 )) -eq 0 ]; then
        a1='         '; a2=' /\___/\ '; a3='(  o.o  )'; a4='\_U   U_/'
      else
        a1=' /\___/\ '; a2='(  ^.^  )'; a3=' \u   u/ '; a4='         '
      fi ;;
  2)  # SCAMPER, busy only. The head is pixel-identical across all three frames
      # and only the leg row changes — which is what the old walk was trying to
      # do, and it works here because at ~3 fps the displacement actually fuses.
      a1=' /\___/\ '; a2='(  >.<  )'; a3=' >  ^  < '
      if [ "$land" -eq 1 ]; then a4=' u_   _u '
      else
        case $(( step % 3 )) in
          0) a4=' u_   _u ' ;;
          1) a4='  \_ _/  ' ;;
          *) a4=' _u   u_ ' ;;
        esac
      fi ;;
  3)  case "$step" in
        1|2) a1='         '; a2=' /\___/\ '; a3='(  O.O  )'; a4='U_______U' ;;
        3)   a1=' /\___/\ '; a2='(  O.O  )'; a3='\_U   U_/'; a4='         ' ;;
        *)   a1='         '; a2=' /\___/\ '; a3='(  -.-  )'; a4='/U     U\' ;;
      esac ;;
  4)  case "$step" in
        1) a1='         '; a2=' /\___/\ '; a3='(  -.-  )'; a4='\_______/' ;;
        2) a1=' /\___/\ '; a2='(  >.<  )'; a3=' > (U) < '; a4=' \_U U_/ ' ;;
        *) a1=' /\___/\ '; a2='(  ^.^  )'; a3=' >  ^  < '; a4='U_______U' ;;
      esac ;;
  5)  case "$step" in
        1) a1=' /\___/\ '; a2='(  -.-  )'; a3=' >  ^  < '; a4=' U     U ' ;;
        2) a1=' /\___/\ '; a2='(  -.-  )'; a3=' > (U) < '; a4=' U     U ' ;;
        *) a1=' /\___/\ '; a2='(  ^.^  )'; a3=' >  ^  < '; a4=' U     U ' ;;
      esac ;;
  6)  # SLEEP. The body never changes; the z is the only moving thing, and it
      # displaces every render, which is what licenses its animation.
      a1='         '; a2=' /\___/\ '; a3='(  -.-  )'; a4='(_______)'
      case $(( f % 3 )) in
        0) ov='z'; ov_row=2; ov_dx=$(( CAT_W )) ;;
        1) ov='z'; ov_row=1; ov_dx=$(( CAT_W + 1 )) ;;
        *) ov='Z'; ov_row=0; ov_dx=$(( CAT_W + 2 )) ;;
      esac ;;
  7)  # THE MOTH. The cat does not travel; the world travels past it. A single
      # cell moving three cells is unambiguous at any cadence — the only thing
      # on this surface that reads as motion without needing frame fusion. It
      # is also the reason the eye-shift sprites exist: until now they looked
      # at nothing.
      set_rest
      case "$step" in
        1) ov='v'; ov_row=0; ov_dx=24 ;;
        2) a2='(    o.o)'; ov='^'; ov_row=0; ov_dx=20 ;;
        3) a2='(    o.o)'; ov='v'; ov_row=1; ov_dx=17 ;;
        4) a2='(    o.o)'; ov='^'; ov_row=0; ov_dx=14 ;;
        5) a1='         '; a2=' /\___/\ '; a3='(  O.O  )'; a4='U_______U'
           ov='v'; ov_row=1; ov_dx=12 ;;
        6) a1='         '; a2=' /\___/\ '; a3='(  O.O  )'; a4='U_______U'
           ov='^'; ov_row=2; ov_dx=11 ;;
        7) a1=' /\___/\ '; a2='(  O.O  )'; a3='\_U   U_/'; a4='         '
           ov='v'; ov_row=0; ov_dx=13 ;;
        8) a1='         '; a2=' /\___/\ '; a3='(  -.-  )'; a4='/U     U\'
           ov='^'; ov_row=0; ov_dx=16 ;;
        9) a2='(    o.o)'; ov='v'; ov_row=0; ov_dx=22 ;;
        *) a2='(  -.-  )' ;;
      esac ;;
  *)  set_rest ;;
esac

# THE CAT IS NOT A GAUGE. Its colour used to follow the worst rate-limit bar, so
# an ordinary late-week session turned the whole animal red with permanently
# bugged eyes and collapsed the repertoire into one pose. The bar carries the
# numbers; the pet only has to be good at being a pet.
CATC="$C_WARM"

# ── scene selection ──────────────────────────────────────────────────────────
# ONE SCENE. The stage is the pet and nothing else.
#
# It had three. `agents` gave every live subagent its own walker; `train` was a
# context warning that crossed the screen at 400k and again at 500k. Both were
# built, both worked, and Ayush cut them on 2026-08-10 — "remove the B and C as
# well". The scene switch went with them.
#
# They are DELETED, not disabled behind a toggle. Everything that has gone
# wrong on this stage went wrong in a branch nobody was looking at: the cat that
# "only animated some time" was a live branch with a dead timer, and the terrain
# survived four rebuilds partly because the failure only showed under conditions
# no one reproduced on purpose. Code that renders is code that gets seen. If the
# train is wanted back it comes back from git, working, not from an `if` that
# has been rotting behind a false.
#
# The history push above and the state save below are the same record; the
# latch fields (`fired`, `train_until`) stay in the format as zeroes so an old
# state file still parses on the first render after this change rather than
# reading a token count out of the wrong field.
{ printf '%s %s %s %s %s\n' "$out_tok" "$now" 0 0 "$hist" \
    > "$SCENE_STATE"; } 2>/dev/null || true

# ── draw the stage ───────────────────────────────────────────────────────────
# ALWAYS exactly 1 + STAGE_ROWS lines, whatever the scene and wherever the cat
# is sitting: a block whose height changes between ticks makes Claude Code
# reflow its whole TUI, and at 1 Hz that is a permanent judder.
#
# The leading blank line is not padding for its own sake. Ayush, 2026-08-09:
# "the cat currently is cutting over the bar" — with the stage starting on the
# very next row, the cat's ears sat directly under the instruments and its `z`
# landed beside the project name. One empty row separates the two and the
# collision goes away.
#
# COST DISCIPLINE, because this runs at 1 Hz in every open session: each scene
# below walks the columns ONCE and appends into per-row accumulators. The
# obvious shape — a loop per row — costs rows x cols iterations instead of
# cols, and at 200 columns that is the difference between ~2 ms and ~10 ms.
# Colour is emitted PER ROW, never per cell: a colour per cell would multiply
# the string length by six and hand Ink far more to parse than it draws.
#
# The two full-width scenes (`eq`, `fire`) are UNROLLED into five named row
# accumulators instead of looping over a rows array. Not premature: with a
# generic inner loop the fire measured 35 ms per render at 211 columns against
# 23 ms for the cat — 3.5% of a core per session, and Ayush runs up to ten.
# Inlining the PRNG bought almost nothing (35 -> 33 ms); it was the 200 x 5
# inner iterations. The unroll is why STAGE_ROWS is effectively pinned at 5 for
# those two scenes: change it and the case tables have to change with it.

emit_stage() {
  printf '\n%s' "$1"
}

if [ "$STAGE_ROWS" -gt 0 ] && [ "$cols" -ge 24 ]; then
  # Row helpers. `poke` writes into a row string at a column and clips at both
  # edges, so a subject can walk off the side one cell at a time rather than
  # vanishing at the boundary.
  W=$(( cols - 2 )); [ "$W" -lt 20 ] && W=20
  printf -v blankrow '%*s' "$W" ''
  poke() {   # poke <rowvar> <x> <text>
    local -n _r=$1
    local px=$2 t=$3
    if [ "$px" -lt 0 ]; then
      t="${t:$(( -px ))}"; px=0
    fi
    [ "$px" -ge "$W" ] && return
    local avail=$(( W - px ))
    [ "${#t}" -gt "$avail" ] && t="${t:0:$avail}"
    [ -z "$t" ] && return
    _r="${_r:0:$px}${t}${_r:$(( px + ${#t} ))}"
  }
  poke_n() {  # poke_n <row index> <x> <text>
    case "$1" in
      0) poke r0 "$2" "$3" ;; 1) poke r1 "$2" "$3" ;; 2) poke r2 "$2" "$3" ;;
      3) poke r3 "$2" "$3" ;; *) poke r4 "$2" "$3" ;;
    esac
  }

  # THE PET, IN ITS YARD AT THE LEFT. Nothing else is on this stage.
  #
  # It once tried to be an instrument as well — a cat walking on terrain built
  # from token history, rebuilt four times and wrong every time: spikes, then a
  # city skyline, then a floor that stopped two thirds across the monitor, then
  # rolling hills that were, in Ayush's words, "trash". The lesson stands even
  # though the cat now travels again: the bar carries the numbers, the yard
  # carries an animal, and the animal only has to be good at being an animal.
  #
  # (This paragraph said "animated in place, no travel" for a while after the
  # cat had started walking, which is the sediment problem in miniature — every
  # rebuild of this thing begins by reading these comments, so a stale one costs
  # more here than almost anywhere else in the file.)
  art=("$a1" "$a2" "$a3" "$a4")
  for (( i = 0; i < 4; i++ )); do
    row="$blankrow"
    poke row "$x" "${art[$i]}"
    [ -n "$ov" ] && [ "$i" -eq "$ov_row" ] && poke row $(( x + ov_dx )) "$ov"
    out+="${NODIM}${CATC} ${row}${RST}"
    [ "$i" -lt 3 ] && out+=$'\n'
  done

  emit_stage "$out"
fi
