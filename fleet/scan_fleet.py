#!/usr/bin/env python3
"""
DHG Fleet Scanner — Pure Python, zero dependencies
Scans a subnet and identifies SSH/WinRM/SNMP targets.

Usage:
    python3 scan_fleet.py                    # scans 10.0.0.0/24
    python3 scan_fleet.py 192.168.1.0/24    # custom subnet
    python3 scan_fleet.py --out hosts.yml   # write inventory file
"""

import argparse
import ipaddress
import json
import os
import platform
import socket
import struct
import subprocess
import sys
import threading
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Config ────────────────────────────────────────────────────────────────────
DEFAULT_SUBNET   = '10.0.0.0/24'
PING_TIMEOUT     = 1.0      # seconds
PORT_TIMEOUT     = 0.5      # seconds
MAX_WORKERS      = 128      # parallel threads
PING_WORKERS     = 254      # parallel pings

# Ports to probe and what they indicate
PROBE_PORTS = {
    22:   ('SSH',    'linux/macos/windows'),
    5985: ('WinRM',  'windows'),
    5986: ('WinRM-S','windows'),
    3389: ('RDP',    'windows'),
    161:  ('SNMP',   'network-device'),
    443:  ('HTTPS',  'any'),
    80:   ('HTTP',   'any'),
    548:  ('AFP',    'macos'),
    445:  ('SMB',    'windows/linux'),
    9100: ('JetDirect', 'printer'),
}

# OS fingerprint hints from open ports
OS_HINTS = {
    frozenset([22, 548]):           'macos',
    frozenset([22, 445]):           'linux',
    frozenset([22, 445, 3389]):     'windows',
    frozenset([5985, 3389]):        'windows',
    frozenset([5985]):              'windows',
    frozenset([3389]):              'windows',
    frozenset([161]):               'network-device',
    frozenset([9100]):              'printer',
}

# ── Ping ──────────────────────────────────────────────────────────────────────
def ping(ip: str) -> bool:
    """OS-native ping — works everywhere without raw sockets."""
    system = platform.system()
    if system == 'Windows':
        cmd = ['ping', '-n', '1', '-w', '800', str(ip)]
    else:
        cmd = ['ping', '-c', '1', '-W', '1', str(ip)]
    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=2)
        return result.returncode == 0
    except Exception:
        return False


# ── Port probe ────────────────────────────────────────────────────────────────
def probe_port(ip: str, port: int) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=PORT_TIMEOUT):
            return True
    except Exception:
        return False


def probe_host(ip: str) -> dict | None:
    """Probe a single live host for open ports and grab hostname."""
    open_ports = {}
    with ThreadPoolExecutor(max_workers=len(PROBE_PORTS)) as ex:
        futures = {ex.submit(probe_port, ip, p): p for p in PROBE_PORTS}
        for f in as_completed(futures):
            port = futures[f]
            if f.result():
                open_ports[port] = PROBE_PORTS[port]

    if not open_ports and not ping(ip):
        return None

    # Hostname resolution
    try:
        hostname = socket.gethostbyaddr(ip)[0]
    except Exception:
        hostname = ''

    # OS guess from port fingerprint
    port_set = frozenset(open_ports.keys())
    os_guess = 'unknown'
    for hint_ports, hint_os in OS_HINTS.items():
        if hint_ports.issubset(port_set):
            os_guess = hint_os
            break

    # Refine: if SSH open and no Windows indicators → linux/macos
    if 22 in open_ports and os_guess == 'unknown':
        os_guess = 'linux'
    if 548 in open_ports:
        os_guess = 'macos'

    # Collector script mapping
    collector_map = {
        'linux':          'collect_linux.py',
        'macos':          'collect_macos.py',
        'windows':        'collect_windows.py',
        'network-device': 'snmp (no host collector)',
        'printer':        'n/a',
        'unknown':        'unknown — enable SSH first',
    }

    return {
        'ip':         ip,
        'hostname':   hostname,
        'os_guess':   os_guess,
        'open_ports': {str(p): v[0] for p, v in open_ports.items()},
        'ssh':        22 in open_ports,
        'winrm':      5985 in open_ports or 5986 in open_ports,
        'snmp':       161 in open_ports,
        'collectable': 22 in open_ports or 5985 in open_ports,
        'collector':  collector_map.get(os_guess, 'unknown'),
    }


# ── Subnet sweep ─────────────────────────────────────────────────────────────
def sweep(subnet: str, verbose: bool = True) -> list[dict]:
    network = ipaddress.IPv4Network(subnet, strict=False)
    hosts   = list(network.hosts())
    live    = []
    lock    = threading.Lock()

    if verbose:
        print(f'\n[DHG SCANNER] Scanning {subnet} ({len(hosts)} hosts)...\n')

    # Phase 1: ping sweep
    alive = []
    with ThreadPoolExecutor(max_workers=PING_WORKERS) as ex:
        futures = {ex.submit(ping, str(ip)): str(ip) for ip in hosts}
        done = 0
        for f in as_completed(futures):
            ip = futures[f]
            done += 1
            if f.result():
                alive.append(ip)
                if verbose:
                    print(f'  ● {ip} is up', flush=True)
            if verbose and done % 50 == 0:
                print(f'  … {done}/{len(hosts)} pinged, {len(alive)} alive', flush=True)

    if verbose:
        print(f'\n[DHG SCANNER] {len(alive)} hosts alive — probing ports...\n')

    # Phase 2: port probe live hosts
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(probe_host, ip): ip for ip in alive}
        for f in as_completed(futures):
            result = f.result()
            if result:
                with lock:
                    live.append(result)
                if verbose:
                    ports_str = ', '.join(
                        f'{p}({v})' for p, v in result['open_ports'].items()
                    )
                    flag = '✓' if result['collectable'] else '!'
                    print(f'  {flag} {result["ip"]:16s}  '
                          f'{result["os_guess"]:14s}  '
                          f'{result["hostname"][:30]:30s}  '
                          f'{ports_str}')

    live.sort(key=lambda x: socket.inet_aton(x['ip']))
    return live


# ── Report ────────────────────────────────────────────────────────────────────
def print_summary(results: list[dict]):
    collectable     = [r for r in results if r['collectable']]
    not_collectable = [r for r in results if not r['collectable']]
    network_devices = [r for r in results if r['snmp']]

    print('\n' + '═' * 70)
    print(' DHG FLEET SCAN SUMMARY')
    print('═' * 70)
    print(f'  Total live hosts   : {len(results)}')
    print(f'  Collectable (SSH)  : {len(collectable)}')
    print(f'  Network devices    : {len(network_devices)}')
    print(f'  Needs attention    : {len(not_collectable)}')
    print()

    if collectable:
        print('  COLLECTABLE HOSTS:')
        for r in collectable:
            print(f'    {r["ip"]:16s}  {r["os_guess"]:10s}  '
                  f'{r["hostname"] or "no-rdns":30s}  → {r["collector"]}')

    if network_devices:
        print()
        print('  NETWORK DEVICES (SNMP):')
        for r in network_devices:
            print(f'    {r["ip"]:16s}  {r["hostname"] or "no-rdns"}')

    if not_collectable:
        print()
        print('  NEEDS SSH ENABLED:')
        for r in not_collectable:
            ports = ', '.join(r['open_ports'].values()) or 'no ports open'
            print(f'    {r["ip"]:16s}  {r["os_guess"]:10s}  ports: {ports}')

    print('═' * 70 + '\n')


def write_hosts_yml(results: list[dict], path: str, ssh_user: str = 'stephen',
                    ssh_key: str = '~/.ssh/dhg_fleet'):
    """Write a hosts.yml ready for the fleet collector."""
    lines = [
        '# DHG Fleet Inventory',
        f'# Generated: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
        '# Edit ssh_user and key_path per node as needed',
        '',
        'defaults:',
        f'  ssh_user: {ssh_user}',
        f'  key_path: {ssh_key}',
        '',
        'nodes:',
    ]

    for r in results:
        if not r['collectable']:
            lines.append(f'  # SKIP {r["ip"]} — SSH not open ({r["os_guess"]})')
            continue
        lines += [
            f'  - host:      {r["ip"]}',
            f'    name:      {r["hostname"] or r["ip"].replace(".", "-")}',
            f'    os:        {r["os_guess"]}',
            f'    ssh_user:  {ssh_user}',
            f'    key_path:  {ssh_key}',
            f'    collector: {r["collector"]}',
            '',
        ]

    # Network devices as comments
    snmp_nodes = [r for r in results if r['snmp']]
    if snmp_nodes:
        lines += ['', '# SNMP network devices:', '# snmp_targets:']
        for r in snmp_nodes:
            lines.append(f'#   - host: {r["ip"]}  # {r["hostname"] or ""}')

    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'[DHG SCANNER] hosts.yml written → {path}')


def write_json(results: list[dict], path: str):
    with open(path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'[DHG SCANNER] JSON written → {path}')


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description='DHG Fleet Scanner — pure Python LAN discovery')
    parser.add_argument('subnet', nargs='?', default=DEFAULT_SUBNET,
                        help=f'Subnet to scan (default: {DEFAULT_SUBNET})')
    parser.add_argument('--out', '-o', default=None,
                        help='Write hosts.yml inventory to this path')
    parser.add_argument('--json', '-j', default=None,
                        help='Write raw JSON results to this path')
    parser.add_argument('--user', '-u', default='stephen',
                        help='SSH username for hosts.yml (default: stephen)')
    parser.add_argument('--key', '-k', default='~/.ssh/dhg_fleet',
                        help='SSH key path for hosts.yml')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Suppress per-host output')
    args = parser.parse_args()

    results = sweep(args.subnet, verbose=not args.quiet)
    print_summary(results)

    if args.out:
        write_hosts_yml(results, args.out, args.user, args.key)

    if args.json:
        write_json(results, args.json)

    # Always write both to cwd as well
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    write_hosts_yml(results, f'hosts_{ts}.yml', args.user, args.key)
    write_json(results, f'fleet_scan_{ts}.json')

    return results


if __name__ == '__main__':
    main()
