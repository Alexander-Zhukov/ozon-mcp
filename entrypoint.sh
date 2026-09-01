#!/usr/bin/env bash
# Start a virtual display (OZON antibot needs headed Chromium), then the server.
set -euo pipefail
Xvfb :99 -screen 0 1366x900x24 >/tmp/xvfb.log 2>&1 &
export DISPLAY=:99
sleep 1
fluxbox >/tmp/fluxbox.log 2>&1 &
sleep 1
exec uv run --no-dev python -m ozon_mcp
