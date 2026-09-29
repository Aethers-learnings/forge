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

# The apply helper is executed as scripts/t107_apply_backend.py, so Python would
# otherwise put scripts/ (not the repository root) at sys.path[0]. Exporting the
# root lets it import forge_migrations and the migrations package reliably.
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"

# A previous interrupted run may have stopped immediately after creating these
# generated, untracked migration artifacts. Remove only those exact helper-owned
# files if Git still reports them as untracked; never delete tracked project data.
for generated in \
  migrations/r20260929_03_blocking_core.py \
  migrations/20260929_03_blocking_core.json
do
  if git status --porcelain -- "$generated" | grep -q '^?? '; then
    echo "Removing interrupted generated artifact: $generated"
    rm -f -- "$generated"
  fi
done

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
