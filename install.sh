#!/usr/bin/env bash
# Install kiln into ~/.config/kitty and ~/.claude.
#
# Backs up anything it would overwrite to <file>.pre-kiln-<date>, then rewrites
# the absolute paths baked into kitty.conf, kitty-keys, check-art and
# tab_bar.py so they point at YOUR home directory rather than the author's.
#
#   ./install.sh --dry-run    print every action, change nothing
#   ./install.sh              do it
#
# It never removes anything and never touches a running kitty. Reload the
# config afterwards with ctrl+cmd+, — except for the background image path,
# allow_remote_control and listen_on, which need a full kitty restart.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KITTY="$HOME/.config/kitty"
CLAUDE="$HOME/.claude"
STAMP="$(/bin/date +%Y%m%d-%H%M%S)"
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

say()  { printf '  %s\n' "$*"; }
head_() { printf '\n%s\n' "$*"; }
run()  { if [ "$DRY" = 1 ]; then say "would: $*"; else "$@"; fi; }

# Copy one file, backing up an existing different copy first.
place() {
  local from=$1 to=$2
  if [ -e "$to" ] && ! /usr/bin/diff -q "$from" "$to" >/dev/null 2>&1; then
    say "backup  $to -> $(basename "$to").pre-kiln-$STAMP"
    run /bin/cp -p "$to" "$to.pre-kiln-$STAMP"
  fi
  say "install $to"
  run /bin/mkdir -p "$(dirname "$to")"
  run /bin/cp -p "$from" "$to"
}

head_ "kiln -> $KITTY and $CLAUDE"
[ "$DRY" = 1 ] && say "(dry run: nothing will be written)"

head_ "checking dependencies"
miss=0
need() { command -v "$1" >/dev/null 2>&1 && say "ok      $1" || { say "MISSING $1  ($2)"; miss=1; }; }
need kitty   "the terminal itself"
need jq      "required by statusline.sh"
need python3 "required by tab_bar.py, check-art, kitty-palcheck.py"
need hb-shape "required by check-art only (brew install harfbuzz)"
if ! /usr/bin/fc-list 2>/dev/null | /usr/bin/grep -qi "JetBrainsMonoNFM" \
   && ! /bin/ls "$HOME/Library/Fonts" 2>/dev/null | /usr/bin/grep -qi "JetBrainsMonoNerdFontMono"; then
  say "MISSING JetBrainsMono Nerd Font MONO  (the plain family silently falls back to Menlo)"
  miss=1
else
  say "ok      JetBrainsMono Nerd Font Mono"
fi
[ "$miss" = 1 ] && say "continuing anyway; the missing pieces degrade individually"

head_ "kitty"
for f in kitty.conf current-theme.conf shell.zsh tab_bar.py check-art kitty-cats kitty-keys kitty-theme kiln-top; do
  place "$SRC/kitty/$f" "$KITTY/$f"
done
for f in "$SRC"/kitty/themes/*; do place "$f" "$KITTY/themes/$(basename "$f")"; done
for f in "$SRC"/kitty/backgrounds/*; do
  [ -f "$f" ] && place "$f" "$KITTY/backgrounds/$(basename "$f")"
done
for f in check-art kitty-cats kitty-keys kitty-theme kiln-top; do run /bin/chmod +x "$KITTY/$f"; done

head_ "claude code"
place "$SRC/claude/statusline.sh"      "$CLAUDE/statusline.sh"
place "$SRC/claude/statusline-demo.sh" "$CLAUDE/statusline-demo.sh"
place "$SRC/claude/stage-preview.py"    "$CLAUDE/stage-preview.py"
run /bin/chmod +x "$CLAUDE/statusline.sh" "$CLAUDE/statusline-demo.sh"
for f in "$SRC"/claude/agents/*.md;  do place "$f" "$CLAUDE/agents/$(basename "$f")"; done
for f in "$SRC"/claude/hooks/*.sh;   do place "$f" "$CLAUDE/hooks/$(basename "$f")"; run /bin/chmod +x "$CLAUDE/hooks/$(basename "$f")"; done
for f in "$SRC"/claude/scripts/*.py; do place "$f" "$CLAUDE/scripts/$(basename "$f")"; done

head_ "rewriting absolute paths to $HOME"
# These four files hard-code the author's home. Everything else uses ~ or $HOME.
for t in "$KITTY/kitty.conf" "$KITTY/kitty-keys" "$KITTY/check-art" "$KITTY/tab_bar.py"; do
  if [ "$DRY" = 1 ]; then
    n=$(/usr/bin/grep -c "/Users/ayush" "$SRC/kitty/$(basename "$t")" 2>/dev/null || echo 0)
    say "would rewrite $n path(s) in $t"
  else
    n=$(/usr/bin/grep -c "/Users/ayush" "$t" 2>/dev/null || true)
    /usr/bin/sed -i '' "s|/Users/ayush|$HOME|g" "$t"
    say "rewrote ${n:-0} path(s) in $t"
  fi
done

head_ "statusline settings"
say "Add this to $CLAUDE/settings.json (padding 0 matters; the stage is sized in cells):"
cat <<'JSON'
    "statusLine": {
      "type": "command",
      "command": "$HOME/.claude/statusline.sh",
      "padding": 0,
      "refreshInterval": 1
    }
JSON

head_ "done"
say "Reload kitty:  ctrl+cmd+,"
say "The background image path needs a FULL kitty restart, not a reload."
say "Check the palette still passes:  python3 $CLAUDE/scripts/kitty-palcheck.py $KITTY/themes/kiln.conf"
