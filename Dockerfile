# OZON's antibot blocks headless Chromium, so the session bootstrap runs a real
# Chromium under Xvfb; thereafter requests go out over curl_cffi. Xvfb is started
# by entrypoint.sh before the server.
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PLAYWRIGHT_BROWSERS_PATH=/ms-browsers \
    DEBIAN_FRONTEND=noninteractive \
    OZON_STATE=/data/state.json

WORKDIR /app
# README.md comes along because pyproject declares it as the package readme —
# without it `uv sync` fails while reading project metadata.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project \
    && uv run playwright install --with-deps chromium \
    && apt-get update \
    && apt-get install -y --no-install-recommends xvfb fluxbox \
    && rm -rf /var/lib/apt/lists/*

COPY src ./src
COPY entrypoint.sh ./entrypoint.sh
RUN uv sync --frozen --no-dev && chmod +x entrypoint.sh

# /data holds the authenticated session (state.json) and the price history, so it
# must be bind-mounted to survive container recreation — the session rotates and
# is written back on every call.
VOLUME ["/data"]

# Only listened on when OZON_TRANSPORT=sse; serves both /sse and /metrics.
EXPOSE 8084

ENTRYPOINT ["./entrypoint.sh"]
