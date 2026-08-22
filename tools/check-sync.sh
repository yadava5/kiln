#!/usr/bin/env bash
# Drift gate: does this repo still match what is actually installed?
#
# This repo is a MIRROR of ~/.config/kitty and parts of ~/.claude. A mirror
# nobody diffs goes stale silently, which is how a manual copy of a PDF in
# another repo here sat wrong for weeks.
#
#   tools/check-sync.sh          report drift, exit 1 if any
#   tools/check-sync.sh --pull   copy the INSTALLED version over the repo
#
# /usr/bin/diff explicitly: a `diff` aliased to difftastic has already
# reported two differing directories as identical on this machine.
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KITTY="$HOME/.config/kitty"
CLAUDE="$HOME/.claude"
PULL=0
[ "${1:-}" = "--pull" ] && PULL=1

drift=0 checked=0 missing=0

cmp_one() {
  local repo=$1 live=$2
  checked=$((checked + 1))
  if [ ! -e "$live" ]; then
    printf '  absent   %s\n' "${live/#$HOME/\~}"
    missing=$((missing + 1))
    return
  fi
  if /usr/bin/diff -q "$repo" "$live" >/dev/null 2>&1; then
    return
  fi
  drift=$((drift + 1))
  if [ "$PULL" = 1 ]; then
    /bin/cp -p "$live" "$repo"
    printf '  pulled   %s\n' "${repo/#$SRC\//}"
  else
    printf '  DRIFT    %s\n' "${repo/#$SRC\//}"
    /usr/bin/diff -u "$repo" "$live" | /usr/bin/head -12 | /usr/bin/sed 's/^/           /'
  fi
}

printf '\nkiln sync check\n'
printf '  repo %s\n  live %s, %s\n\n' "$SRC" "${KITTY/#$HOME/\~}" "${CLAUDE/#$HOME/\~}"

for f in "$SRC"/kitty/*; do
  [ -f "$f" ] && cmp_one "$f" "$KITTY/$(basename "$f")"
done
for f in "$SRC"/kitty/themes/* "$SRC"/kitty/backgrounds/*; do
  [ -f "$f" ] || continue
  sub=$(basename "$(dirname "$f")")
  cmp_one "$f" "$KITTY/$sub/$(basename "$f")"
done
cmp_one "$SRC/claude/statusline.sh"      "$CLAUDE/statusline.sh"
cmp_one "$SRC/claude/statusline-demo.sh" "$CLAUDE/statusline-demo.sh"
cmp_one "$SRC/claude/stage-preview.py"    "$CLAUDE/stage-preview.py"
for f in "$SRC"/claude/agents/*.md;  do cmp_one "$f" "$CLAUDE/agents/$(basename "$f")"; done
for f in "$SRC"/claude/hooks/*.sh;   do cmp_one "$f" "$CLAUDE/hooks/$(basename "$f")"; done
for f in "$SRC"/claude/scripts/*.py; do cmp_one "$f" "$CLAUDE/scripts/$(basename "$f")"; done

printf '\n  %d file(s) checked, %d drifted, %d absent locally\n\n' "$checked" "$drift" "$missing"
[ "$drift" -eq 0 ] || { [ "$PULL" = 1 ] && exit 0; exit 1; }
exit 0
