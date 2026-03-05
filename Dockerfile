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

COPY scripts/  ./scripts/
COPY reports/  ./reports/

# Output dir — mount a host volume here to retrieve CSV + reports
RUN mkdir -p /output

COPY docker-entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Report config via env vars (see entrypoint for full docs)
ENV REPORT_TYPE=full
ENV REPORT_FORMAT=html
ENV SKIP_REPORT=0

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
