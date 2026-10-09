"""Actual shared web/WebView analytics consumer and account-generation guards."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_analytics_frontend():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for frontend helper regressions')
    result = subprocess.run([node, str(Path(__file__).with_name('analytics_frontend.cjs'))],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
