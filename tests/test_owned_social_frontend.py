"""Executable Node tests use the actual static client's helper functions."""
import subprocess


def test_owned_social_client():
    result = subprocess.run(['node', '--test', 'tests/owned_social_frontend.cjs'],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
