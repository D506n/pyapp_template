# Local checks only; bootstrap is explicit and may access the package index.
bootstrap:
    uv lock
    uv sync --locked

lint:
    bash -n ci/security.sh
    uv run --locked ruff check ci
    uv run --locked ruff format --check ci

format-ci:
    uv run --locked ruff format ci

test-contract:
    uv run --locked pytest --tb=no --show-capture=no -o log_cli=false

security:
    bash ci/security.sh

precommit-check-agent: lint test-contract security
