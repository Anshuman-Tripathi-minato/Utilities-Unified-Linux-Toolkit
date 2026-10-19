#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pip install --user -r requirements.txt >/dev/null 2>&1 || python3 -m pip install -r requirements.txt >/dev/null 2>&1 || true
LOG="${TMPDIR:-/tmp}/utilities-suite-$USER.log"
rm -f "$LOG"
python3 server.py >"$LOG" 2>&1 & SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
for _ in {1..50}; do
  if grep -q '^UTILITIES_PORT=' "$LOG"; then break; fi
  sleep 0.1
done
PORT="$(sed -n 's/^UTILITIES_PORT=//p' "$LOG" | head -1)"
if [[ -z "$PORT" ]]; then echo "Utilities backend failed to start. See $LOG"; cat "$LOG"; exit 1; fi
if command -v chromium >/dev/null 2>&1; then BROWSER=chromium
elif command -v chromium-browser >/dev/null 2>&1; then BROWSER=chromium-browser
else echo "Chromium is required. Install chromium."; exit 1; fi
"$BROWSER" --app="http://127.0.0.1:${PORT}" --start-maximized --disable-features=TranslateUI --disable-background-networking >/dev/null 2>&1 || true
wait "$SERVER_PID"
