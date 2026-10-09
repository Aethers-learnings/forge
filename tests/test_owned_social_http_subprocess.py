"""Exercise both process modes without changing a running app's fixed mode."""
import os
import subprocess
import sys


def test_v2_contract_in_isolated_process():
    environment = {**os.environ, 'FORGE_SOCIAL_MODE': 'v2'}
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', 'tests/_v2_contract.py', 'tests/_v2_delivery.py'],
                            env=environment, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


def test_legacy_and_maintenance_modes_in_separate_processes():
    for mode in ('legacy', 'maintenance'):
        environment = {**os.environ, 'FORGE_SOCIAL_MODE': mode}
        result = subprocess.run([sys.executable, '-m', 'pytest', '-q', 'tests/_mode_contract.py'],
                                env=environment, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr


def test_mode_config_fail_closed():
    from forge_backend import build_app_config
    for invalid in ('', 'V2', ' v2', 'both', 'v2,legacy', 'automatic'):
        import pytest
        with pytest.raises(RuntimeError, match='FORGE_SOCIAL_MODE'):
            build_app_config({'FORGE_ENV': 'test', 'FORGE_SOCIAL_MODE': invalid})
    assert build_app_config({'FORGE_ENV': 'test'})['FORGE_SOCIAL_MODE'] == 'legacy'
