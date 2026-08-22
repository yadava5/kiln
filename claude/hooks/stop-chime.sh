#!/bin/bash
# Claude Code Stop hook — the end-of-turn chime.
#
# Was an inline command in settings.json, ending in a bare
#   afplay /System/Library/Sounds/Glass.aiff
# which Claude Code runs SYNCHRONOUSLY and waits on before the turn can end.
#
# THE SOUND IS NOW BACKGROUNDED, and that is the whole change. Measured over the
# 737 Stop-hook runs recorded in the transcripts for the fourteen days to
# 2026-08-12:
#
#   * afplay blocks for the length of the sound. p50 2,467 ms — Glass.aiff is
#     about that long — so every turn ended with a two-and-a-half second wait
#     before the prompt came back. 37.4 minutes of wall clock in a fortnight,
#     spent listening to a ding finish.
#   * WHEN THE AUDIO DEVICE IS UNAVAILABLE IT DOES NOT FAIL FAST. It hangs on
#     its own AudioQueueStart timeout — 42 runs, every one of them between
#     10,203 and 12,941 ms — and then exits non-zero, which Claude Code reports
#     in the transcript as
#         Stop [...] Failed with non-blocking status code:
#         Error: AudioQueueStart failed ('stop')
#     That is the error that appears "every now and then": 42 of 737 runs, 5.7%.
#
# NO RETRY, DELIBERATELY. The failures are not per-call contention between
# concurrent sessions, which a retry would help. They arrive in one continuous
# window — 2026-08-11 08:15, then 19:52 through 2026-08-12 00:18 solid,
# interleaved across three sessions with gaps as short as 3 s — during which
# EVERY call hung the full ~10 s. The device was unavailable for hours, so a
# retry only queues a second doomed 10 s process behind the first. Backgrounded,
# a bad device costs a missed chime; nothing waits and nothing is reported.
set -uo pipefail

TOGGLES="$HOME/.claude/feature-toggles.json"
SOUND="/System/Library/Sounds/Glass.aiff"

# QUIET HOURS, unchanged from the inline version: gated on the toggle first, so
# with quietHours false the chime plays around the clock — which is how Ayush
# has it set, and is deliberate.
quiet=$(/usr/bin/jq -r '.quietHours // false' "$TOGGLES" 2>/dev/null)
if [ "${quiet:-false}" = "true" ]; then
  # 10# forces base ten. `date +%H` pads to two digits, so the 08 and 09 hours
  # arrive as strings a leading zero makes look octal; bash's own `test` reads
  # them as decimal, but the arithmetic context this now uses would not.
  h=$(/bin/date +%H)
  h=$(( 10#$h ))
  if [ "$h" -ge 23 ] || [ "$h" -lt 8 ]; then exit 0; fi
fi

[ -r "$SOUND" ] || exit 0
{ /usr/bin/afplay "$SOUND" </dev/null >/dev/null 2>&1 & } 2>/dev/null
disown 2>/dev/null || true
exit 0
