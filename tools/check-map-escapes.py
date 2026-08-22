#!/usr/bin/env python3
r"""A backslash in a kitty `map` action must be single-quoted, or kitty eats it.

WHY THIS GATE EXISTS. kitty's config parser stores a `map` line's action
verbatim — backslashes and all — so a config with `--regex \S+\.md` loads
without a single warning and `kitten @ ls` shows the definition looking exactly
as written. The backslashes are removed one layer later, when kitty splits that
definition into argv to run it. Measured on kitty 0.46.2, 2026-08-22:

    map ... --regex (?m)\\S+\\.(?:md|markdown|mdx)\\b     ->  (?m)S+.(?:md|markdown|mdx)b

which is a regex that compiles, matches nothing, and reports "No matches found"
against a directory full of the files it was written for. Two bindings shipped
this way — the markdown picker and `toggle_marker`, whose `\\berror\\b` became
`berrorb` and therefore marked nothing, which in turn left `scroll_to_mark` with
nothing to jump to. Both looked correct in every static reading of the config.

Single quotes survive. Double quotes do NOT: kitty's splitter treats backslash
as an escape inside them, unlike POSIX shells and unlike Python's `shlex`, so
`shlex.split` is not a valid model here and this file carries its own splitter
that reproduces kitty's behaviour on the four forms measured above.

`send_text` is exempt: it takes the rest of the line raw and does its own
escape processing, which is how `send_text all \\x1b\\x7f` sends ESC DEL.
"""
import sys

RAW_ACTIONS = {"send_text"}


def kitty_split(s):
    """kitty's argv splitter: backslash escapes anywhere except inside '...'."""
    out, cur, i, n = [], [], 0, len(s)
    quote = ""
    started = False
    while i < n:
        c = s[i]
        if quote == "'":
            if c == "'":
                quote = ""
            else:
                cur.append(c)
        elif c == "\\" and i + 1 < n:
            i += 1
            cur.append(s[i])
            started = True
        elif quote == '"':
            if c == '"':
                quote = ""
            else:
                cur.append(c)
        elif c in "'\"":
            quote = c
            started = True
        elif c.isspace():
            if cur or started:
                out.append("".join(cur))
                cur, started = [], False
        else:
            cur.append(c)
        i += 1
    if cur or started:
        out.append("".join(cur))
    return out


def check(path):
    bad = []
    for lineno, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.rstrip("\n")
        if not line.startswith("map "):
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        action = parts[2]
        if "\\" not in action:
            continue
        if action.split(None, 1)[0] in RAW_ACTIONS:
            continue
        before = action.count("\\")
        after = sum(t.count("\\") for t in kitty_split(action))
        if after < before:
            bad.append((lineno, before - after, line))
    return bad


def selftest():
    """The four forms, against what kitty 0.46.2 actually produced."""
    cases = [
        (r"a --regex (?m)\S+\.(?:md|mdx)\b b", r"(?m)S+.(?:md|mdx)b"),
        (r'''a --regex "(?m)\S+\.(?:md|mdx)\b" b''', r"(?m)S+.(?:md|mdx)b"),
        (r"""a --regex '(?m)\S+\.(?:md|mdx)\b' b""", r"(?m)\S+\.(?:md|mdx)\b"),
        (r"a --regex (?m)\\S+\\.(?:md|mdx)\\b b", r"(?m)\S+\.(?:md|mdx)\b"),
    ]
    for src, want in cases:
        got = kitty_split(src)[2]
        assert got == want, f"splitter disagrees with kitty: {src!r} -> {got!r} != {want!r}"
    return True


if __name__ == "__main__":
    selftest()
    files = sys.argv[1:] or ["kitty/kitty.conf"]
    failed = False
    for f in files:
        bad = check(f)
        for lineno, lost, line in bad:
            print(f"{f}:{lineno}: kitty will eat {lost} backslash(es) here")
            print(f"    {line}")
            print("    single-quote the argument: --regex '...'")
            failed = True
        if not bad:
            print(f"ok: {f} — every backslash in a map action survives argv splitting")
    sys.exit(1 if failed else 0)
