#!/usr/bin/env bash
# Render the three statusline scenes to animated GIFs and open them.
#
#   ~/.claude/statusline-demo.sh              all three
#   ~/.claude/statusline-demo.sh terrain      just one
#
# WHY A GIF AND NOT A LIVE TERMINAL DEMO. The first version of this script
# animated in place with cursor-up escapes and it lost the stage entirely —
# only the info row survived on screen. Two different cursor strategies failed
# the same way, and the failure was silent: it looked like the SCENES were
# broken when the scenes were fine and the harness was not. A GIF is rendered
# from the bytes the real statusline emits, one frame at a time, so there is no
# cursor arithmetic left to get wrong and what you watch is what it does.
#
# It drives ~/.claude/statusline.sh under its own session ids, so your live
# session's history, cat position and threshold latch are untouched.
set -uo pipefail
OUT="$HOME/Downloads/stage-preview"
mkdir -p "$OUT"
cd "$OUT" || exit 1
/opt/homebrew/bin/python3 "$HOME/.claude/stage-preview.py" "${1:-all}" || exit 1
for f in "$OUT"/cat-*.gif; do [ -f "$f" ] && /usr/bin/open "$f"; done
