"""Run browser-helper regressions against the actual inline frontend source."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_frontend_csrf_behavior():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for frontend helper regressions")
    result = subprocess.run([node, str(Path(__file__).with_name("csrf_frontend.cjs"))],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
