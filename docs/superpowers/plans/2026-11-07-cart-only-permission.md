# Cart-only Permission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Allow cart mutations without opening unrelated account changes or payments.

**Architecture:** Add a narrow cart flag alongside the existing broad write gate.
Expose the effective cart permission in session responses and enforce the existing
write gate on checkout configuration.

**Tech Stack:** Python >=3.13, pydantic-settings, FastMCP, pytest, Ruff, ty.

**Spec:** `docs/superpowers/specs/2026-11-07-cart-only-permission-design.md`

## Global Constraints

- All flags default off; no new dependencies or live-account mutations.
- Existing `OZON_ENABLE_WRITES=1` continues to permit cart changes.
- Cart-only permission cannot enable payment, cancellation, checkout configuration, favorites or lists.
- `OZON_ENABLE_ORDERS` remains independent; no merge or deployment.

## Review Focus

- Denied calls must reject before obtaining or using an upstream session.
- Login success, login failure and signed-out status must report effective cart permission.
- Legacy write permission must continue allowing cart writes with the new flag off.
- Order-placement permission alone must not enable cart or other writes.
- All externally exposed mutators must retain the intended permission boundary.

### Task 1: Separate cart permission and publish the contract

**Files:**
- Modify: `src/ozon_mcp/settings.py`, `src/ozon_mcp/errors.py`, `src/ozon_mcp/services/cart.py`, `src/ozon_mcp/services/checkout.py`
- Modify: `src/ozon_mcp/models/session.py`, `src/ozon_mcp/services/session.py`, `src/ozon_mcp/tools/cart.py`, `src/ozon_mcp/tools/checkout.py`, `src/ozon_mcp/tools/session.py`, `src/ozon_mcp/mcp_server.py`
- Modify: `env.example`, `README.md`, `README.ru.md`, `CHANGELOG.md`
- Create: `tests/services/test_cart_permission_is_independent.py`
- Modify: `tests/server/test_tools_are_self_describing.py`

**Interfaces:**
- Consumes: existing `get_settings()`, service entry points and `FakeSession` fixture.
- Produces: `OzonSettings.enable_cart: bool = False`, effective `OzonSettings.cart_enabled: bool`, `SessionStatus.cart_enabled: bool`, `CartDisabledError` with code `cart_disabled`.

- [x] Write parameterized regression tests: cart-only allows quantity/removal/selection, blocks every unrelated mutator with no upstream calls, legacy writes still permit cart, all-off and orders-only refuse cart, and all session/login outcomes report effective gates. Pin the documented MCP gates.
- [x] Run `.venv/bin/python -m pytest tests/services/test_cart_permission_is_independent.py tests/server/test_tools_are_self_describing.py --no-cov -q`; expect failures for missing cart permission and ungated checkout configuration.
- [x] Add the settings/error/status fields and service guards, update MCP descriptions and both README/env examples. Preserve broad-write compatibility and order-placement independence.
- [x] Run `make check-all` with the prepared environment; expect all tests, Ruff and ty to pass. Build a wheel with `uv build`; expect success.
- [x] Commit implementation and tests on `feat/cart-only-permission` without attribution trailers.

Controller step before Final Review: invoke spec-finish
