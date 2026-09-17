#!/usr/bin/env bash
set -euo pipefail
docker stop forge-agent 2>/dev/null || true
echo "Forge agent stopped."
