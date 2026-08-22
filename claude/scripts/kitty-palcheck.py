#!/usr/bin/env python3
"""Per-slot contrast/CVD audit for KITTY theme files.

Parses kitty config syntax (`color1 #RRGGBB`, `background #RRGGBB`, ...).
All colour math (WCAG 2.1, APCA 0.98G-4g, CIEDE2000, Machado CVD) is imported
from ghostty-palcheck.py in this directory so there is exactly one
implementation of the formulas. Only the parser and the gates live here.

Gates (dark theme):
  foreground vs background      >= 4.5:1 WCAG (target 7+), APCA |Lc| >= 90
  color8 (dim/comment)          >= 4.5:1 WCAG, APCA |Lc| >= 60
  color0 (ANSI black)           >= 1.5:1 WCAG
  every content hue 1-6,9-14    >= 4.5:1 WCAG
  red/green (1 vs 2)            dE00 >= 20 normal, >= 12 under deut/prot
  blue/cyan (4 vs 6)            dE00 >= 10 (the Kanso Ink failure mode)
  fg on selection_background    >= 4.5:1 WCAG
  inactive_tab fg vs bg         >= 4.5:1 WCAG, APCA |Lc| >= 60
"""
import importlib.util
import os
import re
import sys

# palmath.py, NOT ghostty-palcheck.py. The original sibling was deleted with
# Ghostty on 2026-07-30 and this import has raised FileNotFoundError ever since,
# which meant every "re-run palcheck after any edit" instruction in this setup
# pointed at a script that could not start. Restored standalone 2026-08-09;
# `python3 palmath.py` self-checks the formulas against published values.
_spec = importlib.util.spec_from_file_location(
    'palmath', os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'palmath.py'))
_m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m)

hex2rgb, wcag_ratio, apca = _m.hex2rgb, _m.wcag_ratio, _m.apca
ciede2000, rgb2lab, cvd = _m.ciede2000, _m.rgb2lab, _m.cvd

KEY = re.compile(r'^(color\d+|background|foreground|cursor|cursor_text_color|'
                 r'selection_background|selection_foreground|url_color|'
                 r'active_border_color|inactive_border_color|bell_border_color|'
                 r'tab_bar_background|active_tab_foreground|active_tab_background|'
                 r'inactive_tab_foreground|inactive_tab_background)'
                 r'\s+(#[0-9a-fA-F]{6}|none)\s*$')


def parse(path):
    d = {}
    for line in open(path, encoding='utf-8'):
        m = KEY.match(line.strip())
        if m and m.group(2) != 'none':
            d[m.group(1)] = hex2rgb(m.group(2))
    return d


def gate(label, value, ok, fmt='{:.2f}'):
    status = 'PASS' if ok else 'FAIL'
    print(f'  {label:44} {fmt.format(value):>8}  {status}')
    return ok


def main(path):
    c = parse(path)
    bg, fg = c['background'], c['foreground']
    all_ok = True

    def g(*a, **k):
        nonlocal all_ok
        all_ok = gate(*a, **k) and all_ok

    print(f'{os.path.basename(path)}  (bg #{bg[0]:02x}{bg[1]:02x}{bg[2]:02x})')
    g('foreground WCAG (>=4.5)', wcag_ratio(fg, bg), wcag_ratio(fg, bg) >= 4.5)
    g('foreground APCA |Lc| (>=90)', abs(apca(fg, bg)), abs(apca(fg, bg)) >= 90, '{:.1f}')
    p8 = c['color8']
    g('color8 dim WCAG (>=4.5)', wcag_ratio(p8, bg), wcag_ratio(p8, bg) >= 4.5)
    g('color8 dim APCA |Lc| (>=60)', abs(apca(p8, bg)), abs(apca(p8, bg)) >= 60, '{:.1f}')
    g('color0 black WCAG (>=1.5)', wcag_ratio(c['color0'], bg),
      wcag_ratio(c['color0'], bg) >= 1.5)
    hues = {i: wcag_ratio(c[f'color{i}'], bg)
            for i in (*range(1, 8), *range(9, 16))}
    worst = min(hues, key=hues.get)
    g(f'min content hue WCAG (color{worst}) (>=4.5)', hues[worst],
      hues[worst] >= 4.5)
    red, grn = c['color1'], c['color2']
    de = ciede2000(rgb2lab(red), rgb2lab(grn))
    g('red/green dE00 (>=20)', de, de >= 20, '{:.1f}')
    for kind, tag in (('deuteranopia', 'deut'), ('protanopia', 'prot')):
        d = ciede2000(rgb2lab(cvd(red, kind)), rgb2lab(cvd(grn, kind)))
        g(f'red/green dE00 {tag} (>=12)', d, d >= 12, '{:.1f}')
    bc = ciede2000(rgb2lab(c['color4']), rgb2lab(c['color6']))
    g('blue/cyan dE00 (>=10)', bc, bc >= 10, '{:.1f}')
    g('cursor vs bg WCAG (>=3.0)', wcag_ratio(c['cursor'], bg),
      wcag_ratio(c['cursor'], bg) >= 3.0)
    if 'selection_background' in c:
        r = wcag_ratio(fg, c['selection_background'])
        g('fg on selection WCAG (>=4.5)', r, r >= 4.5)
    if 'inactive_tab_foreground' in c:
        tf, tb = c['inactive_tab_foreground'], c['inactive_tab_background']
        g('inactive tab WCAG (>=4.5)', wcag_ratio(tf, tb), wcag_ratio(tf, tb) >= 4.5)
        g('inactive tab APCA |Lc| (>=60)', abs(apca(tf, tb)),
          abs(apca(tf, tb)) >= 60, '{:.1f}')
        af, ab = c['active_tab_foreground'], c['active_tab_background']
        g('active tab WCAG (>=4.5)', wcag_ratio(af, ab), wcag_ratio(af, ab) >= 4.5)
    print('  --')
    for i in sorted(hues):
        print(f'  color{i:<2} WCAG {hues[i]:5.2f}  APCA {apca(c[f"color{i}"], bg):6.1f}')
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
