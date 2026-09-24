"""Exercise the static profile export with the existing Node helper harness style."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_profile_export_frontend():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for frontend helper regressions")
    result = subprocess.run(
        [node, str(Path(__file__).with_name("profile_export_frontend.cjs"))],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
