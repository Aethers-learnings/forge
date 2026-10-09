"""Analytics chooses its social graph only at process startup."""
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize('mode', ['legacy', 'maintenance', 'v2'])
def test_analytics_contract_in_isolated_process(mode):
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '--disable-warnings',
                             'tests/_analytics_contract.py'],
                            env={**os.environ, 'FORGE_SOCIAL_MODE': mode},
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


def test_unknown_social_mode_fails_actual_startup():
    result = subprocess.run([sys.executable, '-c', 'import forge_backend'],
                            env={**os.environ, 'FORGE_SOCIAL_MODE': 'unknown'},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert 'FORGE_SOCIAL_MODE must be exactly legacy, maintenance, or v2' in result.stderr
