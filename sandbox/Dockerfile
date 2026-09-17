FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y \
        bash \
        git \
        curl \
        wget \
        ca-certificates \
        build-essential \
        python3 \
        python3-pip \
        python3-venv \
        nodejs \
        npm \
        && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

CMD ["/bin/bash"]
