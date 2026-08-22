#!/bin/bash
# Claude Code Notification hook.
#
# Replaces this, which was in settings.json from April and NEVER worked:
#
#   osascript -e 'display notification "$message" with title "Claude Code"'
#
# Three separate defects in one line:
#   1. SINGLE quotes, so "$message" never expanded - every notification since
#      April displayed the literal text `$message`.
#   2. Hooks receive their payload as JSON on STDIN, not as environment
#      variables, so even with double quotes $message would have been empty.
#   3. Had it expanded, it was unsanitised interpolation into `osascript -e`,
#      i.e. command injection via notification text. A message containing a
#      double quote plus AppleScript would have executed.
#
# This version reads stdin, and passes the text to osascript as an ARGUMENT
# (via `on run argv`) rather than splicing it into the script source, so the
# content can never be interpreted as code.
set -uo pipefail

payload=$(/bin/cat 2>/dev/null)

msg=$(printf '%s' "$payload" | /usr/bin/python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
m = d.get("message") or d.get("notification") or d.get("text") or ""
if isinstance(m, dict):
    m = m.get("text") or json.dumps(m)
print(str(m)[:300].replace("\n", " ").strip())
' 2>/dev/null)

[ -z "${msg:-}" ] && exit 0

/usr/bin/osascript - "$msg" <<'APPLESCRIPT' >/dev/null 2>&1 &
on run argv
    display notification (item 1 of argv) with title "Claude Code"
end run
APPLESCRIPT

exit 0
