#!/usr/bin/env bash
set -euo pipefail
mkdir -p data
rm -f data/bandit-report.json data/bandit-report-short.json
paths=(ci)

bandit_code=0
uv run --locked bandit -r "${paths[@]}" -f json -o data/bandit-report.json || bandit_code=$?
uv run --locked python ci/summarize_bandit.py
audit_code=0
uv run --locked pip-audit --cache-dir data/pip-audit-cache || audit_code=$?
if (( bandit_code != 0 )); then
    exit "$bandit_code"
fi
exit "$audit_code"
