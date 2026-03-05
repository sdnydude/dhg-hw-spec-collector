#!/usr/bin/env python3
"""
DHG Hardware Spec Collector — Linux
Collects full system hardware info and writes to CSV.
Requires: psutil, py-cpuinfo
Optional: dmidecode, lshw, lm-sensors, nvidia-smi, rocm-smi
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
    for pkg in ['psutil', 'cpuinfo']:
        try:
            __import__(pkg)
        except ImportError:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install',
                                   'psutil', 'py-cpuinfo', '--break-system-packages',
                                   '--quiet'])
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

def run(cmd, source='shell'):
    """Run shell command, return stdout or empty string."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True,
                                text=True, timeout=15)
        return result.stdout.strip()
    except Exception:
        return ''

def cmd_exists(cmd):
    return shutil.which(cmd) is not None

# ── OS / System ───────────────────────────────────────────────────────────────
def collect_os():
    add('OS', 'hostname',       socket.gethostname(),         source='socket')
    add('OS', 'os',             platform.system(),            source='platform')
    add('OS', 'os_release',     platform.release(),           source='platform')
    add('OS', 'os_version',     platform.version(),           source='platform')
    add('OS', 'machine',        platform.machine(),           source='platform')
    add('OS', 'python_version', platform.python_version(),    source='platform')

    distro = run("cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'")
    if distro:
        add('OS', 'distro', distro, source='/etc/os-release')

    uptime = run("uptime -p")
    if uptime:
        add('OS', 'uptime', uptime, source='uptime')

    kernel = run("uname -r")
    if kernel:
        add('OS', 'kernel', kernel, source='uname')

# ── CPU ───────────────────────────────────────────────────────────────────────
def collect_cpu():
    info = cpuinfo.get_cpu_info()
    add('CPU', 'model',           info.get('brand_raw', 'N/A'),   source='cpuinfo')
    add('CPU', 'architecture',    info.get('arch', 'N/A'),        source='cpuinfo')
    add('CPU', 'bits',            info.get('bits', 'N/A'),        source='cpuinfo')
    add('CPU', 'hz_actual',       info.get('hz_actual_friendly', 'N/A'), source='cpuinfo')
    add('CPU', 'hz_advertised',   info.get('hz_advertised_friendly', 'N/A'), source='cpuinfo')
    add('CPU', 'l2_cache',        info.get('l2_cache_size', 'N/A'), source='cpuinfo')
    add('CPU', 'l3_cache',        info.get('l3_cache_size', 'N/A'), source='cpuinfo')
    add('CPU', 'flags',           ' '.join(info.get('flags', [])), source='cpuinfo')

    add('CPU', 'physical_cores',  psutil.cpu_count(logical=False), source='psutil')
    add('CPU', 'logical_cores',   psutil.cpu_count(logical=True),  source='psutil')

    freq = psutil.cpu_freq()
    if freq:
        add('CPU', 'freq_current', round(freq.current, 1), 'MHz', source='psutil')
        add('CPU', 'freq_min',     round(freq.min, 1),     'MHz', source='psutil')
        add('CPU', 'freq_max',     round(freq.max, 1),     'MHz', source='psutil')

    for i, pct in enumerate(psutil.cpu_percent(percpu=True, interval=0.5)):
        add('CPU', f'core_{i}_usage', pct, '%', source='psutil')

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

    # dmidecode for slot/speed detail
    if cmd_exists('dmidecode'):
        dmi = run('sudo dmidecode --type 17 2>/dev/null')
        slots = re.findall(
            r'Memory Device\n(.*?)(?=Memory Device|\Z)', dmi, re.DOTALL)
        for i, slot in enumerate(slots):
            def field(name):
                m = re.search(rf'{name}:\s*(.+)', slot)
                return m.group(1).strip() if m else 'N/A'
            add('RAM', f'slot_{i}_size',  field('Size'),         source='dmidecode')
            add('RAM', f'slot_{i}_type',  field('Type'),         source='dmidecode')
            add('RAM', f'slot_{i}_speed', field('Speed'),        source='dmidecode')
            add('RAM', f'slot_{i}_mfr',   field('Manufacturer'), source='dmidecode')
            add('RAM', f'slot_{i}_part',  field('Part Number'),  source='dmidecode')
            add('RAM', f'slot_{i}_loc',   field('Locator'),      source='dmidecode')

# ── Storage ───────────────────────────────────────────────────────────────────
def collect_storage():
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            safe_mp = part.mountpoint.replace('/', '_').strip('_') or 'root'
            add('Storage', f'{safe_mp}_device',     part.device,                    source='psutil')
            add('Storage', f'{safe_mp}_fstype',     part.fstype,                    source='psutil')
            add('Storage', f'{safe_mp}_total',      round(usage.total / 1e9, 2),    'GB', source='psutil')
            add('Storage', f'{safe_mp}_used',       round(usage.used  / 1e9, 2),    'GB', source='psutil')
            add('Storage', f'{safe_mp}_free',       round(usage.free  / 1e9, 2),    'GB', source='psutil')
            add('Storage', f'{safe_mp}_percent',    usage.percent,                  '%',  source='psutil')
        except PermissionError:
            pass

    # lsblk for physical drive detail
    lsblk = run("lsblk -d -o NAME,MODEL,SIZE,ROTA,TYPE,VENDOR,TRAN --json 2>/dev/null")
    if lsblk:
        import json
        try:
            data = json.loads(lsblk)
            for dev in data.get('blockdevices', []):
                name = dev.get('name', '?')
                add('Storage', f'{name}_model',  dev.get('model',  'N/A'), source='lsblk')
                add('Storage', f'{name}_size',   dev.get('size',   'N/A'), source='lsblk')
                add('Storage', f'{name}_type',   dev.get('type',   'N/A'), source='lsblk')
                add('Storage', f'{name}_vendor', dev.get('vendor', 'N/A'), source='lsblk')
                add('Storage', f'{name}_tran',   dev.get('tran',   'N/A'), source='lsblk')  # nvme/sata/usb
                is_ssd = dev.get('rota') == '0'
                add('Storage', f'{name}_is_ssd', is_ssd,                  source='lsblk')
        except Exception:
            pass

# ── GPU ───────────────────────────────────────────────────────────────────────
def collect_gpu():
    # NVIDIA
    if cmd_exists('nvidia-smi'):
        query = ('index,name,driver_version,memory.total,memory.used,memory.free,'
                 'utilization.gpu,utilization.memory,temperature.gpu,'
                 'clocks.current.graphics,clocks.current.memory,power.draw,'
                 'compute_cap,pcie.link.gen.current,pcie.link.width.current')
        raw = run(f'nvidia-smi --query-gpu={query} --format=csv,noheader,nounits')
        headers = [h.strip() for h in query.split(',')]
        for line in raw.splitlines():
            vals = [v.strip() for v in line.split(',')]
            idx = vals[0] if vals else '0'
            for h, v in zip(headers[1:], vals[1:]):
                add('GPU_NVIDIA', f'gpu{idx}_{h}', v, source='nvidia-smi')

    # AMD ROCm
    if cmd_exists('rocm-smi'):
        raw = run('rocm-smi --showallinfo 2>/dev/null')
        for line in raw.splitlines():
            if ':' in line:
                k, _, v = line.partition(':')
                add('GPU_AMD', k.strip(), v.strip(), source='rocm-smi')

    # lspci fallback for any GPU
    lspci = run("lspci | grep -Ei 'vga|3d|display|gpu'")
    if lspci:
        for i, line in enumerate(lspci.splitlines()):
            add('GPU', f'pci_device_{i}', line, source='lspci')

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
            add('Network', f'{iface}_speed',  s.speed,  'Mbps',  source='psutil')
            add('Network', f'{iface}_duplex', s.duplex,           source='psutil')
            add('Network', f'{iface}_mtu',    s.mtu,    'bytes',  source='psutil')
            add('Network', f'{iface}_isup',   s.isup,             source='psutil')

# ── Motherboard ───────────────────────────────────────────────────────────────
def collect_motherboard():
    if cmd_exists('dmidecode'):
        for dtype, cat in [('1', 'System'), ('2', 'Motherboard'), ('0', 'BIOS')]:
            raw = run(f'sudo dmidecode --type {dtype} 2>/dev/null')
            for line in raw.splitlines():
                if ':' in line and not line.strip().startswith('#'):
                    k, _, v = line.partition(':')
                    add(f'MB_{cat}', k.strip(), v.strip(), source='dmidecode')

# ── Thermals ──────────────────────────────────────────────────────────────────
def collect_thermals():
    if cmd_exists('sensors'):
        raw = run('sensors 2>/dev/null')
        current_chip = 'unknown'
        for line in raw.splitlines():
            if line and not line.startswith(' ') and ':' not in line:
                current_chip = line.strip()
            elif ':' in line:
                k, _, v = line.partition(':')
                temp = v.strip().split()[0] if v.strip() else ''
                add('Thermal', f'{current_chip}_{k.strip()}', temp, source='lm-sensors')

    temps = psutil.sensors_temperatures() if hasattr(psutil, 'sensors_temperatures') else {}
    for name, entries in temps.items():
        for entry in entries:
            add('Thermal', f'{name}_{entry.label or "temp"}',
                entry.current, '°C', source='psutil')

# ── PCI Devices ───────────────────────────────────────────────────────────────
def collect_pci():
    if cmd_exists('lspci'):
        raw = run('lspci -v 2>/dev/null')
        for line in raw.splitlines():
            if re.match(r'^[0-9a-f]{2}:', line):
                add('PCI', 'device', line.strip(), source='lspci')

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print("[HW-SPEC Linux] Starting collection...")
    collect_os()
    collect_cpu()
    collect_ram()
    collect_storage()
    collect_gpu()
    collect_network()
    collect_motherboard()
    collect_thermals()
    collect_pci()

    hostname  = socket.gethostname()
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename  = f'hw_specs_{hostname}_{timestamp}.csv'

    fieldnames = ['category', 'key', 'value', 'unit', 'source']
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[HW-SPEC Linux] Done. {len(rows)} rows written → {filename}")
    return filename

if __name__ == '__main__':
    main()
