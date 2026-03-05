#!/usr/bin/env python3
"""
DHG SNMP Collector
Polls Netgear M4250/M4350 switches via SNMP and writes CSV.

Usage:
    python3 fleet/collect_snmp.py
    python3 fleet/collect_snmp.py --community public --out ./fleet_output

Requirements:
    pip3 install pysnmp --break-system-packages
"""

import argparse
import csv
import datetime
import ipaddress
import os
import sys
from pathlib import Path

ROOT      = Path(__file__).parent.parent
FLEET_OUT = ROOT / 'fleet_output'

# SNMP community string — change if you set a custom one on your switches
DEFAULT_COMMUNITY = 'public'

# Switches from hosts.yml
SWITCHES = [
    {'host': '10.0.0.4',   'name': 'Sidecar-4250-12port',   'model': 'M4250-12'},
    {'host': '10.0.0.7',   'name': 'LivingRoom-4250-12',    'model': 'M4250-12'},
    {'host': '10.0.0.134', 'name': 'StudioDesk-4250-24',    'model': 'M4250-24'},
]

# ── MIB OIDs ──────────────────────────────────────────────────────────────────
# Standard MIBs supported by Netgear M4250/M4350
OIDS = {
    # System
    'sysDescr':        '1.3.6.1.2.1.1.1.0',
    'sysName':         '1.3.6.1.2.1.1.5.0',
    'sysLocation':     '1.3.6.1.2.1.1.6.0',
    'sysContact':      '1.3.6.1.2.1.1.4.0',
    'sysUpTime':       '1.3.6.1.2.1.1.3.0',
    'sysObjectID':     '1.3.6.1.2.1.1.2.0',

    # Interfaces (ifTable) — walk these
    'ifNumber':        '1.3.6.1.2.1.2.1.0',

    # Entity MIB — hardware info
    'entPhysDescr':    '1.3.6.1.2.1.47.1.1.1.1.2.1',
    'entPhysMfgName':  '1.3.6.1.2.1.47.1.1.1.1.12.1',
    'entPhysModelName':'1.3.6.1.2.1.47.1.1.1.1.13.1',
    'entPhysSerialNum':'1.3.6.1.2.1.47.1.1.1.1.11.1',
    'entPhysFirmwareRev':'1.3.6.1.2.1.47.1.1.1.1.9.1',
    'entPhysSoftwareRev':'1.3.6.1.2.1.47.1.1.1.1.10.1',

    # NETGEAR enterprise OIDs (M4250/M4350)
    'ng_swVersion':    '1.3.6.1.4.1.4526.10.1.1.1.1.4.1',
    'ng_hwVersion':    '1.3.6.1.4.1.4526.10.1.1.1.1.5.1',
    'ng_serialNum':    '1.3.6.1.4.1.4526.10.1.1.1.1.6.1',
    'ng_model':        '1.3.6.1.4.1.4526.10.1.1.1.1.3.1',
}

# Interface walk OIDs
IF_TABLE_OIDS = {
    'ifDescr':         '1.3.6.1.2.1.2.2.1.2',
    'ifOperStatus':    '1.3.6.1.2.1.2.2.1.8',   # 1=up 2=down
    'ifSpeed':         '1.3.6.1.2.1.2.2.1.5',
    'ifInOctets':      '1.3.6.1.2.1.2.2.1.10',
    'ifOutOctets':     '1.3.6.1.2.1.2.2.1.16',
    'ifPhysAddress':   '1.3.6.1.2.1.2.2.1.6',
}

IF_STATUS = {1: 'up', 2: 'down', 3: 'testing', 4: 'unknown', 5: 'dormant'}


def ensure_pysnmp():
    try:
        from pysnmp.hlapi import getCmd, nextCmd, SnmpEngine, CommunityData, \
            UdpTransportTarget, ContextData, ObjectType, ObjectIdentity
        return True
    except ImportError:
        print('[SNMP] Installing pysnmp...')
        import subprocess
        subprocess.check_call([sys.executable, '-m', 'pip', 'install',
                               'pysnmp', '--break-system-packages', '-q'])
        return True


def snmp_get(host, community, oid, timeout=3, retries=1):
    from pysnmp.hlapi import getCmd, SnmpEngine, CommunityData, \
        UdpTransportTarget, ContextData, ObjectType, ObjectIdentity
    iterator = getCmd(
        SnmpEngine(),
        CommunityData(community, mpModel=0),
        UdpTransportTarget((host, 161), timeout=timeout, retries=retries),
        ContextData(),
        ObjectType(ObjectIdentity(oid))
    )
    errorIndication, errorStatus, errorIndex, varBinds = next(iterator)
    if errorIndication or errorStatus:
        return None
    for varBind in varBinds:
        return str(varBind[1])
    return None


def snmp_walk(host, community, oid, timeout=3, retries=1):
    from pysnmp.hlapi import nextCmd, SnmpEngine, CommunityData, \
        UdpTransportTarget, ContextData, ObjectType, ObjectIdentity
    results = {}
    for errorIndication, errorStatus, errorIndex, varBinds in nextCmd(
        SnmpEngine(),
        CommunityData(community, mpModel=0),
        UdpTransportTarget((host, 161), timeout=timeout, retries=retries),
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
        lexicographicMode=False
    ):
        if errorIndication or errorStatus:
            break
        for varBind in varBinds:
            oid_str = str(varBind[0])
            idx = oid_str.split('.')[-1]
            results[idx] = str(varBind[1])
    return results


def collect_switch(switch, community):
    host  = switch['host']
    name  = switch['name']
    model = switch['model']
    rows  = []
    ts    = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

    def row(cat, key, value, unit='', source='snmp'):
        rows.append({
            'category': cat, 'key': key,
            'value': str(value) if value is not None else '',
            'unit': unit, 'source': source
        })

    print(f'  · {name:30s} polling {host}...')

    # System info
    for key, oid in OIDS.items():
        if key.startswith('ng_') or key.startswith('entPhy') or key == 'ifNumber':
            continue
        val = snmp_get(host, community, oid)
        if val:
            # Convert sysUpTime from timeticks to human readable
            if key == 'sysUpTime':
                try:
                    ticks = int(val)
                    secs  = ticks // 100
                    days  = secs // 86400
                    hrs   = (secs % 86400) // 3600
                    mins  = (secs % 3600) // 60
                    val   = f'{days}d {hrs}h {mins}m'
                except Exception:
                    pass
            row('System', key, val, source='snmp_system')

    # NETGEAR enterprise OIDs
    for key, oid in OIDS.items():
        if not key.startswith('ng_'):
            continue
        val = snmp_get(host, community, oid)
        if val:
            row('Hardware', key.replace('ng_', ''), val, source='snmp_netgear')

    # Entity MIB
    for key, oid in OIDS.items():
        if not key.startswith('entPhy'):
            continue
        val = snmp_get(host, community, oid)
        if val:
            row('Entity', key, val, source='snmp_entity')

    # Interface count
    if_count_val = snmp_get(host, community, OIDS['ifNumber'])
    row('Interfaces', 'total_interfaces', if_count_val or '0', source='snmp_if')

    # Interface walk
    if_descr   = snmp_walk(host, community, IF_TABLE_OIDS['ifDescr'])
    if_status  = snmp_walk(host, community, IF_TABLE_OIDS['ifOperStatus'])
    if_speed   = snmp_walk(host, community, IF_TABLE_OIDS['ifSpeed'])
    if_in      = snmp_walk(host, community, IF_TABLE_OIDS['ifInOctets'])
    if_out     = snmp_walk(host, community, IF_TABLE_OIDS['ifOutOctets'])
    if_mac     = snmp_walk(host, community, IF_TABLE_OIDS['ifPhysAddress'])

    up_ports   = 0
    down_ports = 0
    for idx, descr in if_descr.items():
        status_code = if_status.get(idx, '2')
        try:
            status = IF_STATUS.get(int(status_code), status_code)
        except Exception:
            status = status_code
        speed_bps = if_speed.get(idx, '0')
        try:
            speed_mbps = int(speed_bps) // 1_000_000
            speed_str  = f'{speed_mbps} Mbps' if speed_mbps > 0 else '—'
        except Exception:
            speed_str = speed_bps
        mac = if_mac.get(idx, '')

        row('Interfaces', f'port{idx}_name',   descr,      source='snmp_if')
        row('Interfaces', f'port{idx}_status', status,     source='snmp_if')
        row('Interfaces', f'port{idx}_speed',  speed_str,  source='snmp_if')
        row('Interfaces', f'port{idx}_in_octets',  if_in.get(idx, '0'),  'bytes', 'snmp_if')
        row('Interfaces', f'port{idx}_out_octets', if_out.get(idx, '0'), 'bytes', 'snmp_if')
        if mac:
            row('Interfaces', f'port{idx}_mac', mac, source='snmp_if')

        if status == 'up':
            up_ports += 1
        elif status == 'down':
            down_ports += 1

    row('Interfaces', 'ports_up',   str(up_ports),   source='snmp_summary')
    row('Interfaces', 'ports_down', str(down_ports), source='snmp_summary')

    # Write CSV
    out_dir = FLEET_OUT / name
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f'hw_specs_{name}_{ts}.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['category','key','value','unit','source'])
        writer.writeheader()
        writer.writerows(rows)

    print(f'  ✓ {name:30s} {len(rows)} rows → {csv_path.name}  '
          f'(ports up: {up_ports}  down: {down_ports})')
    return csv_path


def main():
    parser = argparse.ArgumentParser(description='DHG SNMP Switch Collector')
    parser.add_argument('--community', '-c', default=DEFAULT_COMMUNITY,
                        help=f'SNMP community string (default: {DEFAULT_COMMUNITY})')
    parser.add_argument('--out', '-o', default=None,
                        help='Output directory (default: fleet_output/)')
    parser.add_argument('--host', '-H', default=None,
                        help='Poll a single switch by IP')
    args = parser.parse_args()

    ensure_pysnmp()

    global FLEET_OUT
    if args.out:
        FLEET_OUT = Path(args.out)
    FLEET_OUT.mkdir(parents=True, exist_ok=True)

    targets = SWITCHES
    if args.host:
        targets = [s for s in SWITCHES if s['host'] == args.host]
        if not targets:
            targets = [{'host': args.host, 'name': args.host, 'model': 'unknown'}]

    print(f'\n[DHG SNMP] Polling {len(targets)} switch(es) — community: {args.community}\n')

    results = []
    for switch in targets:
        try:
            csv_path = collect_switch(switch, args.community)
            results.append({'switch': switch['name'], 'status': 'ok', 'csv': str(csv_path)})
        except Exception as e:
            print(f'  ✗ {switch["name"]:30s} FAILED: {e}')
            results.append({'switch': switch['name'], 'status': 'failed', 'error': str(e)})

    ok = [r for r in results if r['status'] == 'ok']
    print(f'\n[DHG SNMP] Done — {len(ok)}/{len(targets)} switches collected')
    print(f'[DHG SNMP] Run fleet_report.py to include switches in fleet report')


if __name__ == '__main__':
    main()
