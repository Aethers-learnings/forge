FROM node:22-bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y \
        bash \
        ca-certificates \
        curl \
        git \
        jq \
        ripgrep \
        sqlite3 \
        ffmpeg \
        python3 \
        python3-pip \
        python3-venv \
        build-essential \
        && \
    rm -rf /var/lib/apt/lists/*

# Pin Codex to the version already installed and tested on the host.
RUN npm install --global @openai/codex@0.154.0

WORKDIR /workspace

# Prepare the isolated Codex home.
RUN mkdir -p /home/node/.codex && \
    chown -R node:node /home/node/.codex

USER node

ENV HOME=/home/node
ENV CODEX_HOME=/home/node/.codex

CMD ["/bin/bash"]
