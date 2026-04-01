.PHONY: all fmt lint lock typecheck test check

fmt:
	uv run ruff format src

lint:
	uv run ruff check src

lock:
	uv lock --check

typecheck:
	uv run mypy src

test:
	uv run pytest

all: fmt lint lock typecheck test

check: all
