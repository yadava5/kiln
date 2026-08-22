# kitty themes

kitty's own themes — written in kitty's config syntax, designed for kitty.
Currently: `kiln.conf` (fired clay + ember amber; every contrast gate
measured with `~/.claude/scripts/kitty-palcheck.py`, run it after any edit).

**Do not copy `~/.config/ghostty/themes/*.conf` in here.** They are Ghostty
syntax (`palette = 1=#RRGGBB`, `background-opacity`, `background-image`), kitty
uses different keys (`color1 #RRGGBB`, `background_opacity`,
`background_image`), and a hand-translated duplicate of a palette that already
exists one directory over can only drift. The separation on 2026-08-07 exists
specifically to stop that copying.

## Convention

Each theme is one self-contained `<name>.conf` holding **only colour keys** —
the switcher live-applies it with `kitten @ set-colors`, which reads colours
and nothing else. Behaviour (fonts, padding, keybinds) stays in
`../kitty.conf`.

A theme must define **`mark1/2/3_foreground` and `mark1/2/3_background`**
(the `cmd+shift+m` scrollback highlighter) as well as the ANSI palette. They
moved here from `../kitty.conf` on 2026-08-22, once `kitten @ get-colors` was
checked and shown to return all six — so they live-apply with everything else.
A theme that omits them will keep the previous theme's mark colours until the
next reload, then fall back to kitty's stock blue/beige/violet.

**`scrollbar_handle_color` is the one exception: it is reload-only.** It is a
colour key and belongs here, but `get-colors` does not report it, so
`set-colors` cannot carry it and a live switch will not move it until
`ctrl+cmd+,`. `scrollbar_track_color` is deliberately unset — the track's
opacity defaults to 0, so colouring it would change nothing.

Switch with `../kitty-theme <name>` (alias `kt` under kitty). It copies the
chosen theme over `../current-theme.conf`, which `../kitty.conf` includes
last so the theme's values override the base config, then applies live over
the control socket when one is available. Fallback: `ctrl+cmd+,` reloads
open windows without a restart.
