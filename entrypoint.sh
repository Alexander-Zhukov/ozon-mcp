#!/usr/bin/env bash
# Start a virtual display (OZON antibot needs headed Chromium), then the server.
set -euo pipefail

# A container that is stopped and started again — rather than recreated — keeps
# its /tmp, and Xvfb refuses to take a display whose lock file is still there.
# It then dies while the server starts perfectly well: /metrics answers, the
# healthcheck passes, and every tool fails with "launched a headed browser
# without having a XServer running". Clearing the lock is what makes a restart
# equal to a fresh start.
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99

Xvfb :99 -screen 0 1366x900x24 >/tmp/xvfb.log 2>&1 &
export DISPLAY=:99

# Fail loudly instead of serving a process that cannot open a browser.
for _ in $(seq 1 30); do
    [ -e /tmp/.X11-unix/X99 ] && break
    sleep 0.5
done
if [ ! -e /tmp/.X11-unix/X99 ]; then
    echo "Xvfb did not come up on :99; see /tmp/xvfb.log" >&2
    cat /tmp/xvfb.log >&2 || true
    exit 1
fi

fluxbox >/tmp/fluxbox.log 2>&1 &
sleep 1
exec uv run --no-dev python -m ozon_mcp
