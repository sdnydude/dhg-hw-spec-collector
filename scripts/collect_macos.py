#!/usr/bin/env python3
"""
DHG Hardware Spec Collector — macOS
Collects full system hardware info via system_profiler, ioreg, diskutil, psutil.
No extra sudo required for most data; powermetrics needs sudo for thermals.
"""

import csv
import datetime
import json
import os
import platform
import plistlib
import re
import shutil
import socket
import subprocess
import sys

# ── Install missing deps ──────────────────────────────────────────────────────
def ensure_deps():
    for pkg in ['psutil', 'cpuinfo']:
        try:
            __import__(pkg)
        except ImportError:
            subprocess.check_call([sys.executable, '-m', 'pip3', 'install',
                                   'psutil', 'py-cpuinfo', '--quiet'])
            break

ensure_deps()

import psutil
import cpuinfo

# ── Helpers ───────────────────────────────────────────────────────────────────
rows = []

def add(category, key, value, unit='', source=''):
    rows.append({
        'category': category,
        'key':      key,
        'value':    str(value).strip(),
        'unit':     unit,
        'source':   source,
    })

def run(cmd, timeout=20):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True,
                                text=True, timeout=timeout)
        return result.stdout.strip()
    except Exception:
        return ''

def run_plist(cmd):
    """Run command that returns XML plist and parse it."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, timeout=30)
        return plistlib.loads(result.stdout)
    except Exception:
        return {}

def cmd_exists(cmd):
    return shutil.which(cmd) is not None

# ── OS / System ───────────────────────────────────────────────────────────────
def collect_os():
    add('OS', 'hostname',       socket.gethostname(),       source='socket')
    add('OS', 'os',             platform.system(),          source='platform')
    add('OS', 'os_release',     platform.release(),         source='platform')
    add('OS', 'os_version',     platform.version(),         source='platform')
    add('OS', 'machine',        platform.machine(),         source='platform')  # arm64 or x86_64
    add('OS', 'python_version', platform.python_version(),  source='platform')
    add('OS', 'mac_version',    platform.mac_ver()[0],      source='platform')

    uptime = run("uptime")
    if uptime:
        add('OS', 'uptime', uptime, source='uptime')

    sw_vers = run("sw_vers")
    for line in sw_vers.splitlines():
        if ':' in line:
            k, _, v = line.partition(':')
            add('OS', f'sw_{k.strip().lower()}', v.strip(), source='sw_vers')

# ── CPU ───────────────────────────────────────────────────────────────────────
def collect_cpu():
    info = cpuinfo.get_cpu_info()
    add('CPU', 'model',         info.get('brand_raw', 'N/A'),             source='cpuinfo')
    add('CPU', 'architecture',  info.get('arch', 'N/A'),                  source='cpuinfo')
    add('CPU', 'hz_advertised', info.get('hz_advertised_friendly', 'N/A'), source='cpuinfo')
    add('CPU', 'l2_cache',      info.get('l2_cache_size', 'N/A'),         source='cpuinfo')
    add('CPU', 'l3_cache',      info.get('l3_cache_size', 'N/A'),         source='cpuinfo')
    add('CPU', 'physical_cores', psutil.cpu_count(logical=False),         source='psutil')
    add('CPU', 'logical_cores',  psutil.cpu_count(logical=True),          source='psutil')

    freq = psutil.cpu_freq()
    if freq:
        add('CPU', 'freq_current', round(freq.current, 1), 'MHz', source='psutil')
        add('CPU', 'freq_max',     round(freq.max, 1),     'MHz', source='psutil')

    for i, pct in enumerate(psutil.cpu_percent(percpu=True, interval=0.5)):
        add('CPU', f'core_{i}_usage', pct, '%', source='psutil')

    # system_profiler CPU detail (Apple Silicon especially)
    sp = run("system_profiler SPHardwareDataType")
    for line in sp.splitlines():
        if ':' in line:
            k, _, v = line.partition(':')
            k = k.strip().lower().replace(' ', '_')
            add('CPU_HW', k, v.strip(), source='system_profiler')

# ── RAM ───────────────────────────────────────────────────────────────────────
def collect_ram():
    vm = psutil.virtual_memory()
    add('RAM', 'total',     round(vm.total     / 1e9, 2), 'GB', source='psutil')
    add('RAM', 'available', round(vm.available / 1e9, 2), 'GB', source='psutil')
    add('RAM', 'used',      round(vm.used      / 1e9, 2), 'GB', source='psutil')
    add('RAM', 'percent',   vm.percent,                   '%',  source='psutil')

    sm = psutil.swap_memory()
    add('RAM', 'swap_total', round(sm.total / 1e9, 2), 'GB', source='psutil')
    add('RAM', 'swap_used',  round(sm.used  / 1e9, 2), 'GB', source='psutil')

    # system_profiler memory detail
    sp = run("system_profiler SPMemoryDataType")
    for line in sp.splitlines():
        if ':' in line:
            k, _, v = line.partition(':')
            add('RAM_DETAIL', k.strip().lower().replace(' ', '_'), v.strip(),
                source='system_profiler')

# ── Storage ───────────────────────────────────────────────────────────────────
def collect_storage():
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            safe = part.mountpoint.replace('/', '_').strip('_') or 'root'
            add('Storage', f'{safe}_device',  part.device,                    source='psutil')
            add('Storage', f'{safe}_fstype',  part.fstype,                    source='psutil')
            add('Storage', f'{safe}_total',   round(usage.total / 1e9, 2),    'GB', source='psutil')
            add('Storage', f'{safe}_used',    round(usage.used  / 1e9, 2),    'GB', source='psutil')
            add('Storage', f'{safe}_free',    round(usage.free  / 1e9, 2),    'GB', source='psutil')
            add('Storage', f'{safe}_percent', usage.percent,                  '%',  source='psutil')
        except PermissionError:
            pass

    # diskutil list for physical drive detail
    sp_storage_raw = run('system_profiler SPStorageDataType -json')
    try:
        sp_storage = json.loads(sp_storage_raw)
        volumes = sp_storage.get('SPStorageDataType', [])
        for i, vol in enumerate(volumes):
            for k, v in vol.items():
                add('Storage_Detail', f'vol{i}_{k}', str(v), source='system_profiler')
    except Exception:
        pass

    # NVMe/SSD detail
    sp_nvme = run('system_profiler SPNVMeDataType -json')
    try:
        nvme_data = json.loads(sp_nvme)
        drives = nvme_data.get('SPNVMeDataType', [])
        for i, d in enumerate(drives):
            for k, v in d.items():
                add('Storage_NVMe', f'nvme{i}_{k}', str(v), source='system_profiler')
    except Exception:
        pass

# ── GPU ───────────────────────────────────────────────────────────────────────
def collect_gpu():
    sp_gpu_raw = run('system_profiler SPDisplaysDataType -json')
    try:
        sp_gpu = json.loads(sp_gpu_raw)
        displays = sp_gpu.get('SPDisplaysDataType', [])
        for i, gpu in enumerate(displays):
            for k, v in gpu.items():
                if not isinstance(v, dict):
                    add('GPU', f'gpu{i}_{k}', str(v), source='system_profiler')
    except Exception:
        pass

    # ioreg for Apple GPU detail
    ioreg = run("ioreg -l | grep -i 'gpu\\|metal\\|vram' | head -40")
    for line in ioreg.splitlines():
        if '=' in line:
            k, _, v = line.partition('=')
            clean_k = re.sub(r'[^a-zA-Z0-9_]', '', k.strip())
            add('GPU_IOREG', clean_k, v.strip(), source='ioreg')

# ── Network ───────────────────────────────────────────────────────────────────
def collect_network():
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    for iface, addr_list in addrs.items():
        for addr in addr_list:
            fam = str(addr.family)
            add('Network', f'{iface}_{fam}_address', addr.address,  source='psutil')
            if addr.netmask:
                add('Network', f'{iface}_{fam}_netmask', addr.netmask, source='psutil')
        if iface in stats:
            s = stats[iface]
            add('Network', f'{iface}_speed',  s.speed,  'Mbps', source='psutil')
            add('Network', f'{iface}_isup',   s.isup,           source='psutil')
            add('Network', f'{iface}_mtu',    s.mtu,    'bytes', source='psutil')

    # WiFi detail
    airport = run('/System/Library/PrivateFrameworks/Apple80211.framework/'
                  'Versions/Current/Resources/airport -I 2>/dev/null')
    for line in airport.splitlines():
        if ':' in line:
            k, _, v = line.partition(':')
            add('Network_WiFi', k.strip().lower().replace(' ', '_'), v.strip(),
                source='airport')

# ── Motherboard / System ──────────────────────────────────────────────────────
def collect_motherboard():
    # Already covered largely by SPHardwareDataType in collect_cpu
    # Add battery if laptop
    sp_bat_raw = run('system_profiler SPPowerDataType -json')
    try:
        sp_bat = json.loads(sp_bat_raw)
        power = sp_bat.get('SPPowerDataType', [{}])[0]
        for k, v in power.items():
            if not isinstance(v, dict):
                add('Power', k, str(v), source='system_profiler')
    except Exception:
        pass

# ── Thermals ──────────────────────────────────────────────────────────────────
def collect_thermals():
    temps = psutil.sensors_temperatures() if hasattr(psutil, 'sensors_temperatures') else {}
    for name, entries in temps.items():
        for entry in entries:
            add('Thermal', f'{name}_{entry.label or "temp"}',
                entry.current, '°C', source='psutil')

    # osx-cpu-temp or iStats if installed
    if cmd_exists('osx-cpu-temp'):
        temp = run('osx-cpu-temp')
        if temp:
            add('Thermal', 'cpu_temp_tool', temp, source='osx-cpu-temp')

# ── USB / PCI / Thunderbolt ───────────────────────────────────────────────────
def collect_peripherals():
    for dtype, label in [('SPUSBDataType', 'USB'),
                         ('SPThunderboltDataType', 'Thunderbolt'),
                         ('SPPCIDataType', 'PCI')]:
        raw = run(f'system_profiler {dtype} -json')
        try:
            data = json.loads(raw).get(dtype, [])
            for i, item in enumerate(data):
                for k, v in item.items():
                    if not isinstance(v, (dict, list)):
                        add(label, f'{label.lower()}{i}_{k}', str(v),
                            source='system_profiler')
        except Exception:
            pass

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print("[HW-SPEC macOS] Starting collection...")
    collect_os()
    collect_cpu()
    collect_ram()
    collect_storage()
    collect_gpu()
    collect_network()
    collect_motherboard()
    collect_thermals()
    collect_peripherals()

    hostname  = socket.gethostname()
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename  = f'hw_specs_{hostname}_{timestamp}.csv'

    fieldnames = ['category', 'key', 'value', 'unit', 'source']
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[HW-SPEC macOS] Done. {len(rows)} rows written → {filename}")
    return filename

if __name__ == '__main__':
    main()
