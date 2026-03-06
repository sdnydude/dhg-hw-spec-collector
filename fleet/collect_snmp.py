#!/usr/bin/env python3
"""
DHG SNMP Collector — uses puresnmp (synchronous, no legacy deps)
Usage:
    python3 fleet/collect_snmp.py
    python3 fleet/collect_snmp.py --host 10.0.0.4
    python3 fleet/collect_snmp.py --community public
"""
import argparse, csv, datetime, subprocess, sys
from pathlib import Path

ROOT      = Path(__file__).parent.parent
FLEET_OUT = ROOT / 'fleet_output'
DEFAULT_COMMUNITY = 'public'

SWITCHES = [
    {'host': '10.0.0.4',   'name': 'Sidecar-4250-12port', 'model': 'M4250-12'},
    {'host': '10.0.0.7',   'name': 'LivingRoom-4250-12',  'model': 'M4250-12'},
    {'host': '10.0.0.134', 'name': 'StudioDesk-4250-24',  'model': 'M4250-24'},
]

OIDS = {
    'sysDescr':    '1.3.6.1.2.1.1.1.0',
    'sysName':     '1.3.6.1.2.1.1.5.0',
    'sysLocation': '1.3.6.1.2.1.1.6.0',
    'sysUpTime':   '1.3.6.1.2.1.1.3.0',
    'ifNumber':    '1.3.6.1.2.1.2.1.0',
    'ng_model':     '1.3.6.1.4.1.4526.10.1.1.1.1.3.1',
    'ng_swVersion': '1.3.6.1.4.1.4526.10.1.1.1.1.4.1',
    'ng_hwVersion': '1.3.6.1.4.1.4526.10.1.1.1.1.5.1',
    'ng_serialNum': '1.3.6.1.4.1.4526.10.1.1.1.1.6.1',
}

IF_OIDS = {
    'ifDescr':      '1.3.6.1.2.1.2.2.1.2',
    'ifOperStatus': '1.3.6.1.2.1.2.2.1.8',
    'ifSpeed':      '1.3.6.1.2.1.2.2.1.5',
    'ifInOctets':   '1.3.6.1.2.1.2.2.1.10',
    'ifOutOctets':  '1.3.6.1.2.1.2.2.1.16',
}
IF_STATUS = {1:'up', 2:'down', 3:'testing', 4:'unknown', 5:'dormant'}


def ensure_puresnmp():
    try:
        import puresnmp  # noqa
        return True
    except ImportError:
        print('[SNMP] Installing puresnmp...')
        for flag in ['--user', '--break-system-packages']:
            r = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', 'puresnmp', flag, '-q'],
                capture_output=True)
            if r.returncode == 0:
                return True
        return False


def snmp_get(host, community, oid, timeout=3):
    try:
        from puresnmp import Client, V2C
        with Client(host, V2C(community), timeout=timeout) as client:
            val = client.get(oid)
        return str(val) if val is not None else None
    except Exception:
        return None


def snmp_walk(host, community, oid, timeout=3):
    results = {}
    try:
        from puresnmp import Client, V2C
        with Client(host, V2C(community), timeout=timeout) as client:
            for item in client.walk(oid):
                idx = str(item.oid).split('.')[-1]
                results[idx] = str(item.value)
    except Exception:
        pass
    return results


def collect_switch(switch, community):
    host = switch['host']
    name = switch['name']
    rows = []
    ts   = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

    def row(cat, key, val, unit=''):
        rows.append({'category': cat, 'key': key,
                     'value': str(val) if val else '', 'unit': unit, 'source': 'snmp'})

    print(f'  · {name:36s} polling {host}...')

    # System OIDs
    for key, oid in OIDS.items():
        if key.startswith('ng_') or key == 'ifNumber':
            continue
        val = snmp_get(host, community, oid)
        if val:
            if key == 'sysUpTime':
                try:
                    s = int(val) // 100
                    val = f'{s//86400}d {(s%86400)//3600}h {(s%3600)//60}m'
                except Exception:
                    pass
            row('System', key, val)

    # NETGEAR OIDs
    for key, oid in OIDS.items():
        if not key.startswith('ng_'):
            continue
        val = snmp_get(host, community, oid)
        if val:
            row('Hardware', key.replace('ng_', ''), val)

    row('Interfaces', 'total_interfaces',
        snmp_get(host, community, OIDS['ifNumber']) or '0')

    # Interface walk
    if_data = {k: snmp_walk(host, community, v) for k, v in IF_OIDS.items()}
    up = down = 0
    for idx, descr in if_data['ifDescr'].items():
        try:
            status = IF_STATUS.get(int(if_data['ifOperStatus'].get(idx, '2')), 'unknown')
        except Exception:
            status = 'unknown'
        try:
            mbps = int(if_data['ifSpeed'].get(idx, '0')) // 1_000_000
            speed = f'{mbps} Mbps' if mbps else '—'
        except Exception:
            speed = '—'
        row('Interfaces', f'port{idx}_name',       descr)
        row('Interfaces', f'port{idx}_status',     status)
        row('Interfaces', f'port{idx}_speed',      speed)
        row('Interfaces', f'port{idx}_in_octets',  if_data['ifInOctets'].get(idx,'0'),  'bytes')
        row('Interfaces', f'port{idx}_out_octets', if_data['ifOutOctets'].get(idx,'0'), 'bytes')
        if status == 'up':    up += 1
        elif status == 'down': down += 1

    row('Interfaces', 'ports_up',   str(up))
    row('Interfaces', 'ports_down', str(down))

    out_dir = FLEET_OUT / name
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f'hw_specs_{name}_{ts}.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['category','key','value','unit','source'])
        writer.writeheader()
        writer.writerows(rows)

    print(f'  {"✓" if rows else "✗"} {name:36s} {len(rows)} rows  (up:{up} down:{down})  '
          f'→ {csv_path.name}')
    return csv_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--community', '-c', default=DEFAULT_COMMUNITY)
    parser.add_argument('--host',      '-H', default=None)
    args = parser.parse_args()

    if not ensure_puresnmp():
        print('[SNMP] ERROR: could not install puresnmp'); sys.exit(1)

    print(f'\n[DHG SNMP] community: {args.community}\n')
    FLEET_OUT.mkdir(parents=True, exist_ok=True)

    targets = SWITCHES
    if args.host:
        targets = [s for s in SWITCHES if s['host'] == args.host] or \
                  [{'host': args.host, 'name': args.host, 'model': 'unknown'}]

    ok = 0
    for sw in targets:
        try:
            collect_switch(sw, args.community)
            ok += 1
        except Exception as e:
            print(f'  ✗ {sw["name"]:36s} FAILED: {e}')

    print(f'\n[DHG SNMP] Done — {ok}/{len(targets)} collected')
    if ok > 0:
        print('[DHG SNMP] Run fleet_report.py to include switches in fleet report')


if __name__ == '__main__':
    main()
