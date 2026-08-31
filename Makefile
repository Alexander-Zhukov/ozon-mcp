.PHONY: install format lint typecheck test check-all

install:
	uv sync

format:
	uv run ruff format src tests

lint:
	uv run ruff check --no-fix src tests

typecheck:
	uv run ty check

test:
	uv run pytest

check-all:
	uv run ruff format --check src tests
	uv run ruff check --no-fix src tests
	uv run ty check
	uv run pytest
