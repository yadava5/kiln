# Change plan — 2026-08-22

**Outcome:** items 2, 4, 5, 6, 7 and 8 are APPLIED and verified. Item 1 stays
DEFERRED (needs a kitty quit). Item 3 is NOT DONE — the mechanism it assumed
does not work as written; see the note at the foot of this file.

Eight items were proposed. **#1 is deferred**: kitty 0.48.2 needs a full quit and
Ayush is working in a live tab. Everything below is edit-only. Nothing here
reloads kitty, restarts anything, or kills a process.

Every kitty file is mirrored in this repo, so each config edit is a TWO-PLACE
edit (live + repo) or `tools/check-sync.sh` goes red.

---

## 1. Upgrade kitty 0.46.2 → 0.48.2 — **DEFERRED, do not do**

Needs `brew upgrade --cask kitty` and a full quit. Live Claude sessions in
flight. Carried in memory note `kitty-046-cves`.

## 2. `frontend-no-suites.sh`: `qa` → `labrat`

File: `~/.claude/hooks/frontend-no-suites.sh` (NOT mirrored — hook is
deliberately unpublished? No: this one IS in the repo at `claude/hooks/`.)

Five occurrences, lines 16, 23, 28, 33, 36. All are inside the stderr text the
hook hands back to a blocked agent. `qa` is labrat's pre-2026-08-09 name and
resolves to nothing today.

```
-  ... — qa runs it and sends results back.
+  ... — labrat runs it and sends results back.
-  block "package test/e2e/bench/coverage scripts are qa's job."
+  block "package test/e2e/bench/coverage scripts are labrat's job."
```
…and the same for lines 28, 33, 36.

**Blast radius:** the hook's *matching logic* is untouched; only the message
text changes. A blocked command is still blocked, identically.

## 3. `stig`: name the mutating Supabase tools in `disallowedTools`

File: `~/.claude/agents/stig.md` frontmatter.

```
-disallowedTools: Write, Edit, NotebookEdit
+disallowedTools: Write, Edit, NotebookEdit, mcp__supabase__execute_sql, mcp__supabase__apply_migration, mcp__supabase-applied__execute_sql, mcp__supabase-applied__apply_migration
```

Explicit names, **no wildcards** — wildcard support in `disallowedTools` is
unverified, and `e97ae36` records that specifying `tools:` replaces the default
set, which was a real bug once. This stays in the `disallowedTools` idiom stig
already uses, and does not add a `tools:` key, so stig keeps inheriting the
deferred Claude-in-Chrome tools it loads via ToolSearch.

**Blast radius:** stig is the browser agent and has never needed to write to a
database. Five of six agents already carry a `tools:` allowlist; stig alone has
none, which is the oversight this closes.

## 4. `cursor_trail 3` → `30`

File: `kitty.conf:198` (+ repo copy).

The value is milliseconds — the time a cursor must have been stationary before a
jump earns a trail. At `3` the suppression never engages. Raising it keeps the
trail for deliberate jumps and drops it during Claude Code's stream repaints.

**Blast radius:** cosmetic, live-reloadable, no restart. Takes effect on his
next `ctrl+cmd+,` or new window. Nothing reads this value but kitty's renderer.

## 5. Move `mark1/2/3_*` into the theme file

From `kitty.conf:248-253` into `themes/kiln.conf` **and** `current-theme.conf`
(the two are byte-identical; `kitty-theme` copies one over the other).

Verified this works: `kitten @ get-colors` on the live socket returns
`mark1_background`, `mark1_foreground`, `mark2_*`, `mark3_*` among its keys, so
they are part of the window colour profile that `set-colors --all --configured`
patches. The comment at `kitty.conf:245` claiming otherwise is wrong.

**Ordering is safe:** `kitty.conf` includes `current-theme.conf` LAST, so values
defined there win. Moving a key from the file into the include cannot change the
effective value.

## 6. Theme the scrollbar

Add to `themes/kiln.conf` + `current-theme.conf`:

```
scrollbar_handle_color #7a5432
scrollbar_track_color  #241c17
```

`scrollbar scrolled` is the 0.46.2 default and is already active; both colours
currently default to `foreground` (`#f0e5d1`), i.e. parchment.

**Blast radius:** chrome only, not text. No contrast gate covers the scrollbar,
so no measured number moves.

## 7. `confirm_os_window_close 2` → `-1 count-background`

File: `kitty.conf:191` (+ repo copy).

With `shell_integration enabled`, negative values count only windows where a
command is actually running; `count-background` also counts backgrounded jobs.
That is precisely the case the setting was written for (a live Claude session),
and it stops prompting for two idle shells.

**Blast radius:** changes a confirmation prompt. Worst case is a prompt that
does or does not appear. It cannot close anything on its own.

## 8. Save a `kitty --session` layout

Read-only against the live instance: `kitten @ --to unix:/tmp/kitty-<pid> ls`
returns the tab/window tree as JSON. Writes a new file
`kitty/sessions/current.session`. Touches no running process and changes no
setting — `startup_session` is **not** being set, so nothing about launch
behaviour changes.

**Blast radius:** a new file. Needed before the deferred #1, since restoring the
layout is what makes that upgrade cheap.

---

## Not being done

- Anything requiring a kitty restart or quit (#1, and therefore `progress_bar`,
  vertical tab bars, and the 0.48 font-selection recheck).
- `startup_session` — that changes launch behaviour and deserves its own call.
- Adding a `tools:` key to stig — see #3.
- Any change to hook matching logic, agent routing, or model pins.


---

## Item 3 postscript — why it is not done

`disallowedTools` does **not** accept individual MCP tool names. The entry
`mcp__supabase__execute_sql` is valid YAML, looks correct, and is silently
ignored: with it in place a spawned stig discovered that tool and ran
`SELECT 1` against a live Postgres. A guard that cannot fail is the defect this
repo's own Decisions section warns about, so it was reverted rather than kept.

The documented form is server granularity — `mcp__supabase`,
`mcp__supabase__*`, `mcp__*` — and that form was observed working once: a
spawned stig reported its own tool access as
`All tools except Write, Edit, NotebookEdit, mcp__supabase, mcp__supabase-applied`
with every Supabase tool absent from its registry. A later spawn, after the
entry had been removed and re-added, saw them present again.

So the config in `claude/agents/stig.md` is the documented correct form, but
**propagation within a running session is unreliable**, and it must be
re-verified from a fresh Claude Code session before being treated as enforced.
Until then, assume stig can still reach both Supabase servers.

Two things learned that are worth more than the item itself:

* `disallowedTools` IS mechanical for built-in tool names, and the block
  propagates into nested agents — spawning `minion` from inside `stig` does not
  restore `Write`.
* A `PreToolUse` hook in agent frontmatter genuinely fires: `picasso` was
  blocked before `npm` ran, by `frontend-no-suites.sh`, at the PreToolUse stage.
  The README's claim that the suite gate is mechanical is therefore true, and
  now measured rather than asserted.
