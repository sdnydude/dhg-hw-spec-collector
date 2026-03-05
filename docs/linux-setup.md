# Linux Setup Guide

## Minimum (psutil + cpuinfo only)

```bash
pip install psutil py-cpuinfo --break-system-packages
python3 scripts/collect_all.py
```

Collects: OS, CPU, RAM totals, mounted storage, network interfaces.

---

## Full Setup (recommended)

### System tools

```bash
sudo apt install -y dmidecode lm-sensors pciutils lshw
```

| Tool | Adds |
|---|---|
| `dmidecode` | Per-DIMM RAM detail (type, speed, manufacturer, part number) |
| `lm-sensors` | Thermal readings from all hardware sensors |
| `pciutils` | Full PCI device tree |
| `lshw` | Comprehensive hardware list |

### Initialize lm-sensors

```bash
sudo sensors-detect --auto
```

### NVIDIA GPU

`nvidia-smi` is included with the NVIDIA driver. If the driver is installed correctly:

```bash
nvidia-smi --query-gpu=name,memory.total --format=csv
```

### AMD GPU (ROCm)

```bash
# ROCm installation — see https://rocm.docs.amd.com
# rocm-smi is included with ROCm
rocm-smi --showallinfo
```

> For RDNA 4 (RX 9700 AI Pro / gfx1201): ROCm 6.2+ required. Check
> https://github.com/ROCm/ROCm/issues for current RDNA 4 support status.

---

## Running with sudo (for dmidecode)

Some fields (BIOS serial, memory manufacturer) require root:

```bash
sudo python3 scripts/collect_all.py
```

Or run as your user and accept that dmidecode fields will be blank — everything else still collects.

---

## Dual GPU (NVIDIA + AMD)

Both are collected automatically in the same run:

```
GPU_NVIDIA  gpu0_name          NVIDIA GeForce RTX 5080    nvidia-smi
GPU_AMD     GPU[0]_Temperature  62                         rocm-smi
```
