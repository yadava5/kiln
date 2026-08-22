# ~/.config/kitty/shell.zsh — kitty's shell-side furniture.
#
# Sourced from ~/.zshrc only when $TERM_HOST == kitty. This is kitty's half of
# the 2026-08-07 split: Ghostty's shell furniture lives in
# ~/.config/ghostty/completions.zsh and is sourced only under Ghostty, so
# neither terminal's aliases, completions or startup art leak into the other.
#
# Deliberately near-empty. Anything kitty-specific — a theme switcher alias, a
# welcome hook, kitty-only keybind helpers — belongs here, not in ~/.zshrc.

# Theme switching (script lives beside this file; `kt` is the daily driver).
#   kt          list themes, mark the active one
#   kt kiln     switch — applies live over the control socket when available
alias kitty-theme="$HOME/.config/kitty/kitty-theme"
alias kt="$HOME/.config/kitty/kitty-theme"

# hyperlinked-grep — ripgrep, but every hit is an OSC-8 hyperlink, so ctrl+click
# (or cmd+shift+y) opens the file at that line instead of you retyping the path.
# Same flags as rg; this only wraps the output.
alias hg="kitten hyperlinked-grep"

# check-art — shape terminal art against the live font before shipping it.
# JetBrains Mono turns a ligature into a BLANK spacer glyph plus a combined
# glyph, so cell counts stay right while a whisker silently vanishes. Nothing
# but a shaping run catches that.
#   art ' /\_/\ ' '( o.o )'
alias art="$HOME/.config/kitty/check-art"
