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

# Pin both agent CLIs to the versions currently known-good on the host.
RUN npm install --global \
    @openai/codex@0.154.0 \
    @github/copilot@1.0.83

WORKDIR /workspace

RUN mkdir -p /home/node/.codex /home/node/.copilot && \
    chown -R node:node /home/node

USER node

ENV HOME=/home/node
ENV CODEX_HOME=/home/node/.codex
ENV COPILOT_HOME=/home/node/.copilot

CMD ["/bin/bash"]
