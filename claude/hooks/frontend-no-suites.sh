#!/usr/bin/env bash
# PreToolUse(Bash) guard for the `picasso` agent ONLY — wired in
# ~/.claude/agents/picasso.md frontmatter, not settings.json, so it never
# fires for labrat/minion, whose whole job is running these.
#
# Frontend runs on the fable tier. Suites, e2e, benchmarks and coverage are
# long-running, token-hungry, and belong to `labrat`. The prompt already says so;
# this makes it mechanical. Exit 2 = block + stderr surfaced to the agent.
set -uo pipefail

payload=$(cat 2>/dev/null || true)
cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
[ -z "$cmd" ] && exit 0

block() {
  printf 'BLOCKED for frontend agent: %s Finish the frontend work and name exactly what should run in your report — labrat runs it and sends results back.\n' "$1" >&2
  exit 2
}

# Package-manager test/e2e/bench/coverage scripts: npm test, npm run test:unit,
# pnpm e2e, yarn coverage, bun test, npm run ci ...
if printf '%s' "$cmd" | grep -Eiq '(^|[^[:alnum:]_-])(npm|pnpm|yarn|bun)([[:space:]]+run)?[[:space:]]+(test|e2e|bench|benchmark|coverage|ci)([[:space:]:._-]|$)'; then
  block "package test/e2e/bench/coverage scripts are labrat's job."
fi

# Test/e2e/coverage runners invoked directly or via npx/bunx/pnpm dlx.
if printf '%s' "$cmd" | grep -Eiq '(^|[^[:alnum:]_-])(playwright|cypress|vitest|jest|mocha|ava|karma|stryker|nyc|c8)([[:space:]]|$)'; then
  block "test/e2e/coverage runners are labrat's job."
fi

# Other ecosystems and benchmark/load tools.
if printf '%s' "$cmd" | grep -Eiq '(^|[^[:alnum:]_-])(pytest|hyperfine|k6|artillery|autocannon|lighthouse)([[:space:]]|$)'; then
  block "test and benchmark tools are labrat's job."
fi
if printf '%s' "$cmd" | grep -Eiq '(^|[^[:alnum:]_-])(go|cargo|mvn|gradle|\./gradlew)[[:space:]]+(test|bench)([[:space:]]|$)'; then
  block "language-level test/bench commands are labrat's job."
fi

exit 0
