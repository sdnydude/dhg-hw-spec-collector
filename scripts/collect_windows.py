#!/usr/bin/env python3
"""
DHG Hardware Spec Collector — Windows
Collects full system hardware info via WMI, psutil, and nvidia-smi.
Requires: psutil, py-cpuinfo, wmi, pywin32
"""

import csv
import datetime
import os
import platform
import re
import shutil
import socket
import subprocess
import sys

# ── Install missing deps ──────────────────────────────────────────────────────
def ensure_deps():
    pkgs = {'psutil': 'psutil', 'cpuinfo': 'py-cpuinfo', 'wmi': 'wmi'}
    for mod, pkg in pkgs.items():
        try:
            __import__(mod)
        except ImportError:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install',
                                   pkg, '--quiet'])

ensure_deps()

import psutil
import cpuinfo
try:
    import wmi
    WMI_AVAILABLE = True
except ImportError:
    WMI_AVAILABLE = False

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

def run(cmd, source='shell'):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True,
                                text=True, timeout=20)
        return result.stdout.strip()
    except Exception:
        return ''

def cmd_exists(cmd):
    return shutil.which(cmd) is not None

def wmi_query(wmi_conn, cls):
    try:
        return getattr(wmi_conn, cls)()
    except Exception:
        return []

# ── OS / System ───────────────────────────────────────────────────────────────
def collect_os():
    add('OS', 'hostname',       socket.gethostname(),       source='socket')
    add('OS', 'os',             platform.system(),          source='platform')
    add('OS', 'os_release',     platform.release(),         source='platform')
    add('OS', 'os_version',     platform.version(),         source='platform')
    add('OS', 'machine',        platform.machine(),         source='platform')
    add('OS', 'python_version', platform.python_version(),  source='platform')
    add('OS', 'uptime_seconds', int((datetime.datetime.now().timestamp()
                                     - psutil.boot_time())), 's', source='psutil')

# ── CPU ───────────────────────────────────────────────────────────────────────
def collect_cpu(wmi_conn=None):
    info = cpuinfo.get_cpu_info()
    add('CPU', 'model',           info.get('brand_raw', 'N/A'),           source='cpuinfo')
    add('CPU', 'architecture',    info.get('arch', 'N/A'),                source='cpuinfo')
    add('CPU', 'hz_advertised',   info.get('hz_advertised_friendly','N/A'), source='cpuinfo')
    add('CPU', 'l2_cache',        info.get('l2_cache_size', 'N/A'),       source='cpuinfo')
    add('CPU', 'l3_cache',        info.get('l3_cache_size', 'N/A'),       source='cpuinfo')
    add('CPU', 'physical_cores',  psutil.cpu_count(logical=False),        source='psutil')
    add('CPU', 'logical_cores',   psutil.cpu_count(logical=True),         source='psutil')

    freq = psutil.cpu_freq()
    if freq:
        add('CPU', 'freq_current', round(freq.current, 1), 'MHz', source='psutil')
        add('CPU', 'freq_max',     round(freq.max, 1),     'MHz', source='psutil')

    for i, pct in enumerate(psutil.cpu_percent(percpu=True, interval=0.5)):
        add('CPU', f'core_{i}_usage', pct, '%', source='psutil')

    if wmi_conn:
        for proc in wmi_query(wmi_conn, 'Win32_Processor'):
            add('CPU', 'wmi_name',         getattr(proc, 'Name', 'N/A'),           source='WMI')
            add('CPU', 'wmi_socket',       getattr(proc, 'SocketDesignation','N/A'), source='WMI')
            add('CPU', 'wmi_max_clock',    getattr(proc, 'MaxClockSpeed', 'N/A'),  'MHz', source='WMI')
            add('CPU', 'wmi_current_clock',getattr(proc, 'CurrentClockSpeed','N/A'), 'MHz', source='WMI')
            add('CPU', 'wmi_cores',        getattr(proc, 'NumberOfCores', 'N/A'),  source='WMI')
            add('CPU', 'wmi_threads',      getattr(proc, 'ThreadCount', 'N/A'),    source='WMI')
            add('CPU', 'wmi_l2_cache',     getattr(proc, 'L2CacheSize', 'N/A'),    'KB', source='WMI')
            add('CPU', 'wmi_l3_cache',     getattr(proc, 'L3CacheSize', 'N/A'),    'KB', source='WMI')

# ── RAM ───────────────────────────────────────────────────────────────────────
def collect_ram(wmi_conn=None):
    vm = psutil.virtual_memory()
    add('RAM', 'total',     round(vm.total     / 1e9, 2), 'GB', source='psutil')
    add('RAM', 'available', round(vm.available / 1e9, 2), 'GB', source='psutil')
    add('RAM', 'used',      round(vm.used      / 1e9, 2), 'GB', source='psutil')
    add('RAM', 'percent',   vm.percent,                   '%',  source='psutil')

    sm = psutil.swap_memory()
    add('RAM', 'swap_total', round(sm.total / 1e9, 2), 'GB', source='psutil')

    if wmi_conn:
        for i, stick in enumerate(wmi_query(wmi_conn, 'Win32_PhysicalMemory')):
            cap_gb = int(getattr(stick, 'Capacity', 0) or 0) / 1e9
            add('RAM', f'slot_{i}_capacity',     round(cap_gb, 2),                  'GB', source='WMI')
            add('RAM', f'slot_{i}_speed',        getattr(stick, 'Speed', 'N/A'),   'MHz', source='WMI')
            add('RAM', f'slot_{i}_type',         getattr(stick, 'MemoryType', 'N/A'), source='WMI')
            add('RAM', f'slot_{i}_form_factor',  getattr(stick, 'FormFactor', 'N/A'), source='WMI')
            add('RAM', f'slot_{i}_manufacturer', getattr(stick, 'Manufacturer','N/A'), source='WMI')
            add('RAM', f'slot_{i}_part_number',  getattr(stick, 'PartNumber', 'N/A'), source='WMI')
            add('RAM', f'slot_{i}_bank_label',   getattr(stick, 'BankLabel', 'N/A'),  source='WMI')
            add('RAM', f'slot_{i}_device_locator', getattr(stick, 'DeviceLocator','N/A'), source='WMI')

# ── Storage ───────────────────────────────────────────────────────────────────
def collect_storage(wmi_conn=None):
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            mp = part.mountpoint.replace('\\', '_').replace(':', '').strip('_')
            add('Storage', f'{mp}_device',  part.device,                    source='psutil')
            add('Storage', f'{mp}_fstype',  part.fstype,                    source='psutil')
            add('Storage', f'{mp}_total',   round(usage.total / 1e9, 2),    'GB', source='psutil')
            add('Storage', f'{mp}_used',    round(usage.used  / 1e9, 2),    'GB', source='psutil')
            add('Storage', f'{mp}_free',    round(usage.free  / 1e9, 2),    'GB', source='psutil')
            add('Storage', f'{mp}_percent', usage.percent,                  '%',  source='psutil')
        except PermissionError:
            pass

    if wmi_conn:
        for disk in wmi_query(wmi_conn, 'Win32_DiskDrive'):
            idx  = getattr(disk, 'Index', '?')
            size = int(getattr(disk, 'Size', 0) or 0)
            add('Storage', f'disk{idx}_model',        getattr(disk, 'Model', 'N/A'),        source='WMI')
            add('Storage', f'disk{idx}_manufacturer', getattr(disk, 'Manufacturer', 'N/A'), source='WMI')
            add('Storage', f'disk{idx}_interface',    getattr(disk, 'InterfaceType','N/A'),  source='WMI')
            add('Storage', f'disk{idx}_size',         round(size / 1e9, 2),                 'GB', source='WMI')
            add('Storage', f'disk{idx}_partitions',   getattr(disk, 'Partitions', 'N/A'),   source='WMI')
            add('Storage', f'disk{idx}_serial',       getattr(disk, 'SerialNumber','N/A'),   source='WMI')
            add('Storage', f'disk{idx}_media_type',   getattr(disk, 'MediaType', 'N/A'),    source='WMI')

# ── GPU ───────────────────────────────────────────────────────────────────────
def collect_gpu(wmi_conn=None):
    # nvidia-smi
    if cmd_exists('nvidia-smi'):
        query = ('index,name,driver_version,memory.total,memory.used,memory.free,'
                 'utilization.gpu,temperature.gpu,clocks.current.graphics,'
                 'clocks.current.memory,power.draw,compute_cap,'
                 'pcie.link.gen.current,pcie.link.width.current')
        raw = run(f'nvidia-smi --query-gpu={query} --format=csv,noheader,nounits')
        headers = query.split(',')
        for line in raw.splitlines():
            vals = [v.strip() for v in line.split(',')]
            idx  = vals[0] if vals else '0'
            for h, v in zip(headers[1:], vals[1:]):
                add('GPU_NVIDIA', f'gpu{idx}_{h}', v, source='nvidia-smi')

    # WMI video controllers
    if wmi_conn:
        for i, gpu in enumerate(wmi_query(wmi_conn, 'Win32_VideoController')):
            ram = int(getattr(gpu, 'AdapterRAM', 0) or 0)
            add('GPU', f'gpu{i}_name',        getattr(gpu, 'Name', 'N/A'),          source='WMI')
            add('GPU', f'gpu{i}_driver',      getattr(gpu, 'DriverVersion', 'N/A'), source='WMI')
            add('GPU', f'gpu{i}_driver_date', getattr(gpu, 'DriverDate', 'N/A'),    source='WMI')
            add('GPU', f'gpu{i}_vram',        round(ram / 1e9, 2),                  'GB', source='WMI')
            add('GPU', f'gpu{i}_resolution',  getattr(gpu, 'CurrentHorizontalResolution','N/A'), source='WMI')
            add('GPU', f'gpu{i}_refresh_rate',getattr(gpu, 'CurrentRefreshRate','N/A'), 'Hz', source='WMI')
            add('GPU', f'gpu{i}_status',      getattr(gpu, 'Status', 'N/A'),        source='WMI')

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

# ── Motherboard / BIOS ────────────────────────────────────────────────────────
def collect_motherboard(wmi_conn=None):
    if not wmi_conn:
        return
    for board in wmi_query(wmi_conn, 'Win32_BaseBoard'):
        add('Motherboard', 'manufacturer', getattr(board, 'Manufacturer','N/A'), source='WMI')
        add('Motherboard', 'product',      getattr(board, 'Product',     'N/A'), source='WMI')
        add('Motherboard', 'version',      getattr(board, 'Version',     'N/A'), source='WMI')
        add('Motherboard', 'serial',       getattr(board, 'SerialNumber','N/A'), source='WMI')

    for bios in wmi_query(wmi_conn, 'Win32_BIOS'):
        add('BIOS', 'manufacturer', getattr(bios, 'Manufacturer', 'N/A'),  source='WMI')
        add('BIOS', 'version',      getattr(bios, 'SMBIOSBIOSVersion','N/A'), source='WMI')
        add('BIOS', 'release_date', getattr(bios, 'ReleaseDate',    'N/A'), source='WMI')
        add('BIOS', 'serial',       getattr(bios, 'SerialNumber',   'N/A'), source='WMI')

    for cs in wmi_query(wmi_conn, 'Win32_ComputerSystem'):
        add('System', 'manufacturer',   getattr(cs, 'Manufacturer',  'N/A'), source='WMI')
        add('System', 'model',          getattr(cs, 'Model',         'N/A'), source='WMI')
        add('System', 'total_ram',      getattr(cs, 'TotalPhysicalMemory','N/A'), source='WMI')
        add('System', 'num_processors', getattr(cs, 'NumberOfProcessors','N/A'), source='WMI')

# ── Thermals ──────────────────────────────────────────────────────────────────
def collect_thermals():
    temps = psutil.sensors_temperatures() if hasattr(psutil, 'sensors_temperatures') else {}
    for name, entries in temps.items():
        for entry in entries:
            add('Thermal', f'{name}_{entry.label or "temp"}',
                entry.current, '°C', source='psutil')

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print("[HW-SPEC Windows] Starting collection...")
    wmi_conn = None
    if WMI_AVAILABLE:
        try:
            import pythoncom
            pythoncom.CoInitialize()
            wmi_conn = wmi.WMI()
        except Exception as e:
            print(f"[HW-SPEC] WMI init warning: {e}")

    collect_os()
    collect_cpu(wmi_conn)
    collect_ram(wmi_conn)
    collect_storage(wmi_conn)
    collect_gpu(wmi_conn)
    collect_network()
    collect_motherboard(wmi_conn)
    collect_thermals()

    hostname  = socket.gethostname()
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename  = f'hw_specs_{hostname}_{timestamp}.csv'

    fieldnames = ['category', 'key', 'value', 'unit', 'source']
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[HW-SPEC Windows] Done. {len(rows)} rows written to {filename}")
    return filename

if __name__ == '__main__':
    main()
