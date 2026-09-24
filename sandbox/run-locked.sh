#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-develop}"
shift || true

HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

case "$MODE" in
    discover)
        WORKSPACE_MOUNT="type=bind,src=${ROOT},dst=/workspace,readonly"
        ;;
    develop)
        WORKSPACE_MOUNT="type=bind,src=${ROOT},dst=/workspace"
        ;;
    *)
        echo "Usage:"
        echo "  $0 discover"
        echo "  $0 develop"
        exit 2
        ;;
esac

if [ "$HOST_UID" != "1000" ] || [ "$HOST_GID" != "1000" ]; then
    echo "Expected host UID/GID 1000:1000."
    echo "Detected: ${HOST_UID}:${HOST_GID}"
    exit 1
fi

DOCKER_TTY=()
if [ -t 0 ] && [ -t 1 ]; then
    DOCKER_TTY=(-it)
fi

exec docker run --rm "${DOCKER_TTY[@]}" \
    --name forge-codex \
    --network=bridge \
    --cap-drop=ALL \
    --security-opt=no-new-privileges:true \
    --read-only \
    --pids-limit=512 \
    --memory=8g \
    --cpus=4 \
    --tmpfs /tmp:rw,noexec,nosuid,nodev,size=1g \
    --tmpfs /run:rw,noexec,nosuid,nodev,size=64m \
    --tmpfs /home/node:rw,nosuid,nodev,size=512m \
    --mount "$WORKSPACE_MOUNT" \
    --mount type=volume,src=forge-codex-home,dst=/home/node/.codex \
    --workdir=/workspace \
    --user "$HOST_UID:$HOST_GID" \
    --env HOME=/home/node \
    --env CODEX_HOME=/home/node/.codex \
    forge-agent \
    codex \
        --sandbox danger-full-access \
        --ask-for-approval on-request \
        "$@"
