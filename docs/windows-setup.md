# Windows Setup Guide

## Install Python Dependencies

```powershell
pip install psutil py-cpuinfo wmi pywin32
```

## Run

```powershell
python scripts\collect_all.py
```

---

## NVIDIA GPU

`nvidia-smi.exe` must be in your PATH. It is installed automatically with the NVIDIA driver to:

```
C:\Windows\System32\DriverStore\FileRepository\nv...\nvidia-smi.exe
C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe
```

Verify:
```powershell
nvidia-smi --query-gpu=name,memory.total --format=csv
```

## AMD GPU

WMI captures basic AMD GPU info (name, driver, VRAM) via `Win32_VideoController`.
ROCm for Windows is available but still maturing — `rocm-smi` on Windows is not yet
included in the collector. WMI data is the fallback.

---

## WMI Provides

- `Win32_Processor` — CPU model, socket, cache, clocks
- `Win32_PhysicalMemory` — per-DIMM type, speed, manufacturer, part number, bank
- `Win32_DiskDrive` — physical drive model, interface, size, serial
- `Win32_VideoController` — GPU name, VRAM, driver version/date
- `Win32_BaseBoard` — motherboard manufacturer, model, serial
- `Win32_BIOS` — BIOS version, date, serial
- `Win32_ComputerSystem` — system model, total RAM, processor count

---

## Running as Administrator

Some WMI queries (especially BIOS serial, some hardware serials) return more complete
data when run as Administrator. Right-click PowerShell → "Run as administrator".
