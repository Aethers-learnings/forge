#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

docker run --rm -it \
    --name forge-agent \
    --network=none \
    --cap-drop=ALL \
    --security-opt=no-new-privileges:true \
    --read-only \
    --tmpfs /tmp:rw,noexec,nosuid,size=512m \
    --tmpfs /run:rw,noexec,nosuid,size=64m \
    --tmpfs /home/agent:rw,nosuid,size=256m \
    --pids-limit=512 \
    --memory=8g \
    --cpus=4 \
    --user "${HOST_UID}:${HOST_GID}" \
    --mount "type=bind,src=${PROJECT_ROOT},dst=/workspace" \
    --workdir=/workspace \
    forge-agent
