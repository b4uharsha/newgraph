#!/bin/bash
# Graph OLAP Platform documentation — local server launcher (macOS / Linux).
#
# Double-click this file to start a tiny HTTP server rooted at this folder and
# open the docs in your default browser. The server runs until you close the
# Terminal window that opens.
#
# Why this exists: Chrome blocks ES module imports from file:// URLs by
# security policy, so opening index.html directly does not work in Chrome.
# Safari and Firefox are more permissive; if you use either, you can open
# index.html directly instead.

set -e
cd "$(dirname "$0")"

PORT=4321
URL="http://localhost:${PORT}/"

# Find a usable Python interpreter.
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "ERROR: Python 3 is required but not found on PATH."
  echo "Install Python from https://www.python.org/downloads/ and try again."
  read -p "Press Enter to close this window."
  exit 1
fi

echo "Starting docs server at ${URL}"
echo "Press Ctrl+C in this window to stop the server."
echo

# Open the browser in the background, then run the server in the foreground.
# A small delay gives the server a moment to bind the port before the browser
# requests the page.
( sleep 1 && { command -v open >/dev/null && open "${URL}"; } || { command -v xdg-open >/dev/null && xdg-open "${URL}"; } ) &

exec "${PY}" -m http.server "${PORT}" --bind 127.0.0.1
