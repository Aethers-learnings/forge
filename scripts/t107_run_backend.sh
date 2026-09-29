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

export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"

# Every file below is owned by this temporary helper. The branch was clean when
# the helper started, and the user's earlier interrupted work is separately
# preserved in a git stash. Reset only these known helper targets so a failed
# run is safely rerunnable; do not touch any other working-tree path.
tracked_targets=(
  forge_backend.py
  forge_migrations.py
  forge_routes/owned_social.py
  forge_routes/owned_social_http.py
  tests/test_owned_social_models.py
  tests/test_migration_tooling.py
  tests/test_database_bootstrap.py
  tests/_v2_contract.py
)

echo "Resetting only prior helper-owned partial edits..."
git restore --source=HEAD --worktree -- "${tracked_targets[@]}"

for generated in \
  migrations/r20260929_03_blocking_core.py \
  migrations/20260929_03_blocking_core.json \
  tests/test_blocking_core_service.py \
  tests/test_blocking_core_migration.py
do
  if [[ -e "$generated" ]] && git status --porcelain -- "$generated" | grep -q '^?? '; then
    echo "Removing interrupted generated artifact: $generated"
    rm -f -- "$generated"
  fi
done

# Patch the temporary helper copy, not the tracked helper file. The old helper
# searched for a single identical assertion, but test_migration_tooling.py has
# two on purpose: the normal upgrade test should point at revision 03 while a
# rollback test must continue to expect revision 02. Match the surrounding
# normal-upgrade context so the rollback assertion remains unchanged.
TMP_HELPER="$(mktemp -t forge-t107-helper.XXXXXX.py)"
trap 'rm -f -- "$TMP_HELPER"' EXIT

"$PY" - "$TMP_HELPER" <<'PY'
from pathlib import Path
import sys

source = Path("scripts/t107_apply_backend.py").read_text()
old = '''src = replace_once(
    src,
    """    assert verified[\\"revision\\"] == owned_social.REVISION\\n""",
    """    assert verified[\\"revision\\"] == blocking.REVISION\\n""",
    "verified head assertion",
)
'''
new = '''src = replace_once(
    src,
    """    verified = verify_database(engine)\\n\\n    assert verified[\\"revision\\"] == owned_social.REVISION\\n    assert verified[\\"integrity\\"] == \\"ok\\"\\n    assert verified[\\"foreignKeyViolations\\"] == []\\n""",
    """    verified = verify_database(engine)\\n\\n    assert verified[\\"revision\\"] == blocking.REVISION\\n    assert verified[\\"integrity\\"] == \\"ok\\"\\n    assert verified[\\"foreignKeyViolations\\"] == []\\n""",
    "verified normal-upgrade head assertion",
)
'''
if source.count(old) != 1:
    raise SystemExit(
        f"temporary helper hotfix source mismatch: expected 1 block, found {source.count(old)}"
    )
Path(sys.argv[1]).write_text(source.replace(old, new, 1))
PY

echo "Using $PY"
echo "Applying T-107 blocking core..."
"$PY" "$TMP_HELPER"

# The bootstrap regression used the historical two-revision count as a literal.
# T-107 legitimately adds a third revision, so assert the migration registry
# length instead of hard-coding a number that must change with every revision.
"$PY" - <<'PY'
from pathlib import Path

path = Path("tests/test_database_bootstrap.py")
source = path.read_text()
old = '        assert conn.execute(f"SELECT count(*) FROM {migrations.LEDGER_TABLE}").fetchone()[0] == 2\n'
new = '        assert conn.execute(f"SELECT count(*) FROM {migrations.LEDGER_TABLE}").fetchone()[0] == len(migrations.REVISION_ORDER)\n'
if source.count(old) != 1:
    raise SystemExit(
        f"bootstrap ledger assertion mismatch: expected 1 source line, found {source.count(old)}"
    )
path.write_text(source.replace(old, new, 1))
PY

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
