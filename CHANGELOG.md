# Changelog

All notable changes to `dhg-hw-spec-collector` will be documented here.

Format: [Semantic Versioning](https://semver.org/)

---

## [1.0.0] - 2026-03-05

### Added
- Initial release
- Linux collector: psutil, cpuinfo, dmidecode, lspci, lm-sensors, nvidia-smi, rocm-smi
- Windows collector: psutil, cpuinfo, WMI (Win32_* classes), nvidia-smi
- macOS collector: psutil, cpuinfo, system_profiler, ioreg, diskutil, airport
- Universal launcher `collect_all.py` with OS auto-detection
- CSV output schema: category / key / value / unit / source
- Dual-GPU support (mixed NVIDIA + AMD on same machine)
- Auto dependency installation on first run
- CI workflow for schema validation tests
