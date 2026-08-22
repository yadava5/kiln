#!/bin/bash
# SessionStart hook: emit the minimum orientation Claude Code cannot derive
# for itself, and nothing else.
#
# Replaces ~/.agent-memory-hooks/memory_context.py (≈800 lines) on 2026-07-30,
# when basic-memory was removed. That file had already been reduced to
# emitting only <workspace>; everything else in it - FTS queries, recent
# activity, handoff loading, the Codex mirror - was dead code on this path.
#
# History worth keeping in mind if anyone is tempted to grow this again:
# the version that injected "relevant memory" on every prompt cost ~406 tokens
# and up to 7 seconds per prompt, and what it surfaced was a truncated
# fragment of the previous reply plus unrelated months-old notes. Injecting
# loosely-related context is worse than injecting none - it competes with the
# actual request for attention. If something is worth knowing, put it in
# CLAUDE.md; if it is worth looking up, let the model search for it.
#
# Contract: JSON on stdin, one JSON object on stdout with
# hookSpecificOutput.additionalContext. Must stay well under ~50ms.
set -uo pipefail

payload=$(/bin/cat 2>/dev/null)

cwd=$(printf '%s' "$payload" | /usr/bin/sed -n 's/.*"cwd"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | /usr/bin/head -1)
[ -z "${cwd:-}" ] && cwd="$PWD"
[ -d "$cwd" ] || cwd="$HOME"

repo=$(/usr/bin/git -C "$cwd" rev-parse --show-toplevel 2>/dev/null || true)
branch=""
dirty=""
if [ -n "$repo" ]; then
  branch=$(/usr/bin/git -C "$repo" rev-parse --abbrev-ref HEAD 2>/dev/null || true)
  n=$(/usr/bin/git -C "$repo" status --porcelain 2>/dev/null | /usr/bin/wc -l | /usr/bin/tr -d ' ')
  [ "${n:-0}" -gt 0 ] 2>/dev/null && dirty=" dirty=\"$n\""
fi

# Build the context string with JSON escaping already applied, so the output
# is a plain printf and no interpreter has to start. Spawning python purely to
# encode one flat object cost 124ms of the 128ms total - the whole hook was
# interpreter startup. Paths here are filesystem paths and branch names; the
# only JSON metacharacter that can appear is the double quote, which is
# stripped rather than escaped so the output cannot be malformed.
strip() { printf '%s' "${1//\"/}"; }

if [ -n "$repo" ]; then
  ctx="<workspace repo=\\\"$(strip "$(/usr/bin/basename "$repo")")\\\" branch=\\\"$(strip "${branch:-?}")\\\"${dirty//\"/\\\"} path=\\\"$(strip "$repo")\\\" />"
else
  ctx="<workspace path=\\\"$(strip "$cwd")\\\" vcs=\\\"none\\\" />"
fi

printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$ctx"
