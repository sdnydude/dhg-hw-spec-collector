# macOS Setup Guide

## Install Python Dependencies

```bash
pip3 install psutil py-cpuinfo
```

## Run

```bash
python3 scripts/collect_all.py
```

---

## Built-in Tools Used (no install needed)

| Tool | Data |
|---|---|
| `system_profiler` | CPU, RAM, GPU, Storage, USB, Thunderbolt, Power |
| `ioreg` | Apple Silicon GPU internals, Metal info |
| `diskutil` | Volume metadata |
| `airport` | WiFi link stats, SSID, RSSI, channel |
| `sw_vers` | macOS version |

---

## Apple Silicon vs Intel

The collector handles both architectures automatically:

- **Apple Silicon (M-series):** GPU data comes from `ioreg` + `system_profiler SPDisplaysDataType`. The Unified Memory architecture means RAM/GPU share pool — this is reflected in the output.
- **Intel Mac:** Discrete GPU data from `system_profiler`, CPU detail from `cpuinfo`.

---

## Optional: Thermal Data

psutil's `sensors_temperatures()` may return limited data on macOS depending on
the version and hardware. For deeper thermal readings, install:

```bash
brew install osx-cpu-temp
```

The collector will use it automatically if present.

---

## sudo for powermetrics

If you want Apple's `powermetrics` thermal data (most detailed on Apple Silicon):

```bash
sudo python3 scripts/collect_all.py
```

Without sudo, all other data still collects normally.
