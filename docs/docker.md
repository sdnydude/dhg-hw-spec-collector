# Docker Guide

## Quick Run

```bash
# Build and run — CSV saved to ./output/
mkdir -p output
docker compose up --build
```

The container runs once, writes `hw_specs_<hostname>_<timestamp>.csv` to `./output/`, then exits.

---

## Manual docker run (no Compose)

```bash
docker build -t dhg-hw-spec-collector .

docker run --rm \
  --privileged \
  --pid=host \
  --network=host \
  -v /proc:/proc:ro \
  -v /sys:/sys:ro \
  -v /run/udev:/run/udev:ro \
  -v $(pwd)/output:/output \
  dhg-hw-spec-collector
```

---

## Why `--privileged`?

| Flag | Purpose |
|---|---|
| `--privileged` | Allows `dmidecode` (RAM slot/BIOS detail) and `lspci` (PCI tree) |
| `--pid=host` | Sees real host process table for accurate uptime/CPU stats |
| `--network=host` | Sees actual NICs, not just the Docker bridge |
| `/proc:/proc:ro` | CPU, memory, process stats |
| `/sys:/sys:ro` | Hardware topology, thermal sensors |
| `/run/udev:/run/udev:ro` | Device metadata (drive models, USB info) |

Without `--privileged`, the container still collects: OS, CPU, RAM totals, mounted
storage, network interfaces, and any NVIDIA GPU data. The dmidecode and lspci
categories simply won't appear.

---

## NVIDIA GPU inside Docker

Pass the GPU to the container:

```yaml
# docker-compose.yml addition
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: all
          capabilities: [gpu]
```

Or with docker run:

```bash
docker run --rm --privileged --pid=host --network=host \
  --gpus all \
  -v /proc:/proc:ro -v /sys:/sys:ro -v /run/udev:/run/udev:ro \
  -v $(pwd)/output:/output \
  dhg-hw-spec-collector
```

Requires `nvidia-container-toolkit` installed on the host.

---

## AMD GPU (ROCm) inside Docker

```bash
docker run --rm --privileged --pid=host --network=host \
  --device=/dev/kfd \
  --device=/dev/dri \
  -v /proc:/proc:ro -v /sys:/sys:ro -v /run/udev:/run/udev:ro \
  -v $(pwd)/output:/output \
  dhg-hw-spec-collector
```

`rocm-smi` requires `/dev/kfd` and `/dev/dri` device access.
The base image does not include ROCm — add it to the Dockerfile if needed:

```dockerfile
# Add after the apt-get install block:
RUN apt-get install -y rocm-smi-lib && \
    rm -rf /var/lib/apt/lists/*
```

---

## Dual GPU (RTX 5080 + RX 9700 AI Pro)

```yaml
services:
  hw-spec-collector:
    build: .
    privileged: true
    pid: host
    network_mode: host
    devices:
      - /dev/kfd           # AMD ROCm
      - /dev/dri           # AMD GPU render nodes
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    volumes:
      - /proc:/proc:ro
      - /sys:/sys:ro
      - /run/udev:/run/udev:ro
      - ./output:/output
    restart: "no"
```

---

## Scheduling with Cron (fleet inventory)

Run a hardware snapshot on a schedule:

```bash
# crontab -e
# Every day at 2am
0 2 * * * cd /opt/dhg-hw-spec-collector && docker compose up >> /var/log/hw-spec.log 2>&1
```

Output directory accumulates timestamped CSVs — one per run per machine.
