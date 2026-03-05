FROM python:3.12-slim

LABEL org.opencontainers.image.title="dhg-hw-spec-collector" \
      org.opencontainers.image.description="Cross-platform hardware spec collector — DHG Labs" \
      org.opencontainers.image.url="https://github.com/sdnydude/dhg-hw-spec-collector" \
      org.opencontainers.image.vendor="Digital Harmony Group" \
      org.opencontainers.image.licenses="MIT"

# System tools for full Linux hardware data
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        dmidecode \
        pciutils \
        lm-sensors \
        lshw \
        iproute2 \
        procps && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/ ./scripts/

# Output dir — mount a host volume here to retrieve the CSV
RUN mkdir -p /output

COPY docker-entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
