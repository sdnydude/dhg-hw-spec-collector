# dhg-hw-spec-collector

**Cross-platform hardware specification collector for Linux, Windows, and macOS.**  
Collects complete system hardware data — CPU, GPU, RAM, storage, network, thermals, motherboard — and exports to a structured CSV file.

Developed by [Digital Harmony Group](https://digitalharmonygroup.com) · DHG Labs Division

---

## Features

- **Single command** — auto-detects OS, runs the right collector
- **Comprehensive** — 15+ hardware categories, 100+ data points per machine
- **GPU-aware** — NVIDIA via `nvidia-smi`, AMD via `rocm-smi`, Apple GPU via `ioreg`
- **Dual-GPU support** — captures mixed NVIDIA + AMD configs in the same CSV
- **Zero config** — installs its own Python dependencies on first run
- **Structured output** — `category / key / value / unit / source` schema, ready for import into any database or spreadsheet

---

## Quick Start

```bash
# Clone
git clone https://github.com/sdnydude/dhg-hw-spec-collector.git
cd dhg-hw-spec-collector

# Run (auto-detects OS)
python3 scripts/collect_all.py
```

Output: `hw_specs_<hostname>_<YYYYMMDD_HHMMSS>.csv`

---

## Platform Support

| Platform | Script | Notes |
|---|---|---|
| Linux | `scripts/collect_linux.py` | Full support. Requires `dmidecode`, `lspci`, `lm-sensors` for max data |
| Windows | `scripts/collect_windows.py` | Full support. WMI provides deep hardware detail |
| macOS | `scripts/collect_macos.py` | Full support. `system_profiler` + `ioreg` + `diskutil` |

---

## Output Schema

Every row in the CSV follows this structure:

| Column | Description | Example |
|---|---|---|
| `category` | Hardware subsystem | `GPU_NVIDIA` |
| `key` | Spec identifier | `gpu0_memory.total` |
| `value` | Measured value | `16376` |
| `unit` | Unit of measure | `MiB` |
| `source` | Tool that produced it | `nvidia-smi` |

---

## Data Collected

### All Platforms
- **OS** — hostname, distro, kernel/version, uptime
- **CPU** — model, architecture, cores/threads, clock speeds, cache sizes, per-core usage
- **RAM** — total/used/available, swap, per-slot detail (type, speed, manufacturer, part number)
- **Storage** — all mounted volumes + physical drive model, interface (NVMe/SATA/USB), size, type
- **GPU** — model, VRAM, driver version, utilization, temperature, clock speeds, PCIe link info
- **Network** — all interfaces, IP/MAC, link speed, duplex, MTU
- **Motherboard** — manufacturer, model, BIOS version, serial
- **Thermals** — per-sensor temperatures where available

### Linux Extras
- `lspci` full PCI device tree
- `dmidecode` memory slot detail (DDR type, speed, manufacturer, part number per DIMM)
- `nvidia-smi` full NVIDIA GPU stats
- `rocm-smi` full AMD GPU stats (ROCm required)
- `lm-sensors` thermal readings

### Windows Extras
- WMI full hardware inventory (Win32_Processor, Win32_PhysicalMemory, Win32_DiskDrive, Win32_VideoController, Win32_BaseBoard, Win32_BIOS)
- DirectX device info via WMI
- Per-disk serial numbers and partition counts

### macOS Extras
- `system_profiler` — SPHardwareDataType, SPMemoryDataType, SPStorageDataType, SPDisplaysDataType, SPNVMeDataType, SPPowerDataType, SPUSBDataType, SPThunderboltDataType, SPPCIDataType
- `ioreg` Apple Silicon GPU detail
- Airport WiFi link stats
- Battery/power detail (laptops)

---

## Dependencies

### Linux
```bash
# System tools (optional but recommended for full data)
sudo apt install -y dmidecode lm-sensors pciutils lshw

# Python
pip install psutil py-cpuinfo

# GPU tools (install with your driver)
# nvidia-smi  →  installed with NVIDIA driver
# rocm-smi   →  installed with ROCm
```

### Windows
```powershell
pip install psutil py-cpuinfo wmi pywin32
# nvidia-smi must be in PATH
```

### macOS
```bash
pip3 install psutil py-cpuinfo
# system_profiler, ioreg, diskutil — all built-in
```

> **Note:** The collector will attempt to auto-install `psutil` and `py-cpuinfo` on first run if they are missing.

---

## Use Cases

- **Hardware inventory** — document every machine in a fleet before deployment
- **GPU fleet management** — audit VRAM, driver versions, PCIe config across nodes
- **LLM server baseline** — capture pre/post hardware changes on inference machines
- **Support diagnostics** — one command, full system snapshot
- **Compliance documentation** — audit trail of hardware state at a point in time

---

## DHG AI Factory Integration

This tool is designed to feed into the DHG AI Factory observability stack:

```
collect_all.py → hw_specs_*.csv → PostgreSQL/pgvector → DHG Central Registry
```

Use the CSV as a hardware baseline record for each node in your GPU fleet.

---

## Project Structure

```
dhg-hw-spec-collector/
├── README.md
├── CHANGELOG.md
├── LICENSE
├── .gitignore
├── requirements.txt
├── scripts/
│   ├── collect_all.py        # Universal launcher (run this)
│   ├── collect_linux.py      # Linux collector
│   ├── collect_windows.py    # Windows collector
│   └── collect_macos.py      # macOS collector
├── docs/
│   ├── output-schema.md      # CSV column definitions
│   ├── linux-setup.md        # Linux dependency guide
│   ├── windows-setup.md      # Windows dependency guide
│   └── macos-setup.md        # macOS dependency guide
├── tests/
│   └── test_schema.py        # Output schema validation tests
└── .github/
    └── workflows/
        └── test.yml          # CI — runs schema tests on push
```

---

## License

MIT — see [LICENSE](LICENSE)

---

## Contributing

PRs welcome. Open an issue first for major changes.  
Maintained by DHG Labs · Digital Harmony Group
