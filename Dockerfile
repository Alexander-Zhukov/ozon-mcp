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
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project \
    && uv run playwright install --with-deps chromium \
    && apt-get update \
    && apt-get install -y --no-install-recommends xvfb fluxbox \
    && rm -rf /var/lib/apt/lists/*

COPY src ./src
COPY entrypoint.sh ./entrypoint.sh
RUN uv sync --frozen --no-dev && chmod +x entrypoint.sh

VOLUME ["/data"]
ENTRYPOINT ["./entrypoint.sh"]
