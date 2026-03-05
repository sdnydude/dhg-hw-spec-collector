# Output Schema

## File Naming

```
hw_specs_<hostname>_<YYYYMMDD_HHMMSS>.csv
```

Example: `hw_specs_PROART-Z890_20260305_154500.csv`

---

## CSV Columns

| Column | Type | Description | Example |
|---|---|---|---|
| `category` | string | Hardware subsystem group | `GPU_NVIDIA` |
| `key` | string | Spec identifier | `gpu0_memory.total` |
| `value` | string | Measured or reported value | `16376` |
| `unit` | string | Unit of measure (empty if N/A) | `MiB` |
| `source` | string | Tool or API that produced the value | `nvidia-smi` |

---

## Category Reference

| Category | Description | Primary Source |
|---|---|---|
| `OS` | Operating system, hostname, kernel | platform, uname |
| `CPU` | Processor model, cores, clocks, cache | psutil, cpuinfo |
| `CPU_HW` | macOS-specific CPU hardware detail | system_profiler |
| `RAM` | Memory totals, usage, swap | psutil |
| `RAM_DETAIL` | Per-DIMM slot info (type, speed, mfr) | dmidecode / WMI / system_profiler |
| `Storage` | Volume mounts, usage | psutil |
| `Storage_NVMe` | NVMe physical drive detail | lsblk / WMI / system_profiler |
| `Storage_Detail` | macOS volume metadata | system_profiler |
| `GPU_NVIDIA` | NVIDIA GPU stats | nvidia-smi |
| `GPU_AMD` | AMD GPU stats | rocm-smi |
| `GPU` | Generic GPU / video controller | WMI / lspci / system_profiler |
| `GPU_IOREG` | Apple GPU detail | ioreg |
| `Network` | Interface addresses, speed, MTU | psutil |
| `Network_WiFi` | WiFi link detail | airport (macOS) |
| `Motherboard` | Board model, serial | dmidecode / WMI |
| `MB_System` | System manufacturer, model | dmidecode |
| `MB_BIOS` | BIOS version, date | dmidecode |
| `BIOS` | BIOS detail | WMI |
| `System` | System-level WMI info | WMI |
| `Thermal` | Per-sensor temperatures | psutil / lm-sensors |
| `PCI` | Full PCI device list | lspci |
| `USB` | USB device inventory | system_profiler |
| `Thunderbolt` | Thunderbolt device inventory | system_profiler |
| `Power` | Battery / power detail | system_profiler |

---

## Importing to PostgreSQL

```sql
CREATE TABLE hw_specs (
    id          SERIAL PRIMARY KEY,
    collected_at TIMESTAMPTZ DEFAULT NOW(),
    hostname    TEXT,
    category    TEXT,
    key         TEXT,
    value       TEXT,
    unit        TEXT,
    source      TEXT
);

-- Then use COPY or pgloader to ingest the CSV
COPY hw_specs(category, key, value, unit, source)
FROM '/path/to/hw_specs_hostname_timestamp.csv'
CSV HEADER;
```

---

## Filtering Examples

```python
import pandas as pd
df = pd.read_csv('hw_specs_MYHOST_20260305_154500.csv')

# All GPU rows
df[df.category.str.startswith('GPU')]

# NVIDIA VRAM only
df[(df.category == 'GPU_NVIDIA') & (df.key.str.contains('memory.total'))]

# All thermals
df[df.category == 'Thermal']

# RAM slot detail
df[(df.category == 'RAM_DETAIL') & (df.key.str.contains('speed'))]
```
