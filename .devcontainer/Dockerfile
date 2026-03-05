FROM python:3.14-slim

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    gh \
    curl \
    procps \
    jq \
    sqlite3 \
    lsof \
    iputils-ping \
    iproute2 \
    less \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONUNBUFFERED=1
