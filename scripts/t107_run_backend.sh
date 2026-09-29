#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

if [[ "$(git branch --show-current)" != "manual/t107-blocking-core" ]]; then
  echo "ERROR: expected manual/t107-blocking-core" >&2
  exit 1
fi

PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
  PY=python3
fi

echo "Using $PY"
echo "Applying T-107 blocking core..."
"$PY" scripts/t107_apply_backend.py

echo
echo "Running focused T-107 / owned-social / migration tests..."
"$PY" -m pytest -q --disable-warnings \
  tests/test_blocking_core_migration.py \
  tests/test_blocking_core_service.py \
  tests/test_owned_social_models.py \
  tests/test_owned_social_service.py \
  tests/test_owned_social_http_subprocess.py \
  tests/test_migration_tooling.py \
  tests/test_database_bootstrap.py

echo
echo "Running diff check..."
git diff --check

echo
echo "Working tree:"
git status --short

echo
echo "Diff summary:"
git diff --stat

echo
echo "T-107 backend/core focused verification completed successfully."
