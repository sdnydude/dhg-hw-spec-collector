#!/usr/bin/env python3
"""
DHG SNMP Collector — uses snmpwalk/snmpget CLI (net-snmp)
SNMPv2c, community: public
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

# ── MIB-II system group ────────────────────────────────────────────────────────
SCALAR_OIDS = {
    # System
    'sysDescr':           ('System', '1.3.6.1.2.1.1.1.0',   ''),
    'sysName':            ('System', '1.3.6.1.2.1.1.5.0',   ''),
    'sysLocation':        ('System', '1.3.6.1.2.1.1.6.0',   ''),
    'sysContact':         ('System', '1.3.6.1.2.1.1.4.0',   ''),
    'sysUpTime':          ('System', '1.3.6.1.2.1.1.3.0',   ''),
    'sysObjectID':        ('System', '1.3.6.1.2.1.1.2.0',   ''),
    'sysServices':        ('System', '1.3.6.1.2.1.1.7.0',   ''),
    'ifNumber':           ('Interfaces', '1.3.6.1.2.1.2.1.0', ''),
    # Bridge / STP
    'dot1dBaseBridgeAddress':  ('STP', '1.3.6.1.2.1.17.1.1.0', ''),
    'dot1dBaseNumPorts':       ('STP', '1.3.6.1.2.1.17.1.2.0', ''),
    'dot1dStpRootCost':        ('STP', '1.3.6.1.2.1.17.2.6.0', ''),
    'dot1dStpRootPort':        ('STP', '1.3.6.1.2.1.17.2.7.0', ''),
    # IP
    'ipForwarding':       ('IP', '1.3.6.1.2.1.4.1.0',  ''),
    # LLDP
    'lldpLocChassisId':   ('LLDP', '1.0.8802.1.1.2.1.3.2.0', ''),
    'lldpLocSysName':     ('LLDP', '1.0.8802.1.1.2.1.3.3.0', ''),
    'lldpLocSysDesc':     ('LLDP', '1.0.8802.1.1.2.1.3.4.0', ''),
    # NETGEAR enterprise — hardware identity
    'ng_model':           ('Hardware', '1.3.6.1.4.1.4526.10.1.1.1.1.3.1',  ''),
    'ng_swVersion':       ('Hardware', '1.3.6.1.4.1.4526.10.1.1.1.1.4.1',  ''),
    'ng_hwVersion':       ('Hardware', '1.3.6.1.4.1.4526.10.1.1.1.1.5.1',  ''),
    'ng_serialNum':       ('Hardware', '1.3.6.1.4.1.4526.10.1.1.1.1.6.1',  ''),
    'ng_mfgDate':         ('Hardware', '1.3.6.1.4.1.4526.10.1.1.1.1.8.1',  ''),
    # NETGEAR — CPU utilization
    'ng_cpuUtil1s':       ('Health.CPU', '1.3.6.1.4.1.4526.10.1.36.1.0',   '%'),
    'ng_cpuUtil5s':       ('Health.CPU', '1.3.6.1.4.1.4526.10.1.36.2.0',   '%'),
    'ng_cpuUtil1m':       ('Health.CPU', '1.3.6.1.4.1.4526.10.1.36.3.0',   '%'),
    # NETGEAR — memory
    'ng_memTotal':        ('Health.Mem', '1.3.6.1.4.1.4526.10.1.56.1.0',   'KB'),
    'ng_memFree':         ('Health.Mem', '1.3.6.1.4.1.4526.10.1.56.2.0',   'KB'),
    # NETGEAR — temperature
    'ng_tempSensor':      ('Health.Temp', '1.3.6.1.4.1.4526.10.1.53.1.1.3.1', 'C'),
    'ng_tempStatus':      ('Health.Temp', '1.3.6.1.4.1.4526.10.1.53.1.1.4.1', ''),
    # NETGEAR — fans
    'ng_fanStatus1':      ('Health.Fan', '1.3.6.1.4.1.4526.10.1.54.1.1.3.1',  ''),
    'ng_fanStatus2':      ('Health.Fan', '1.3.6.1.4.1.4526.10.1.54.1.1.3.2',  ''),
    # NETGEAR — PSUs
    'ng_psu1Status':      ('Health.PSU', '1.3.6.1.4.1.4526.10.1.55.1.1.3.1',  ''),
    'ng_psu2Status':      ('Health.PSU', '1.3.6.1.4.1.4526.10.1.55.1.1.3.2',  ''),
    # NETGEAR — PoE
    'ng_poeNominalPower': ('PoE', '1.3.6.1.4.1.4526.10.15.2.1.1.2.1',  'W'),
    'ng_poeConsumedPwr':  ('PoE', '1.3.6.1.4.1.4526.10.15.2.1.1.3.1',  'W'),
    'ng_poePwrStatus':    ('PoE', '1.3.6.1.4.1.4526.10.15.2.1.1.4.1',  ''),
}

# ── Per-port walk OIDs (ifTable + ifXTable + dot3 + MAU) ─────────────────────
WALK_OIDS = {
    # RFC 2863 ifTable
    'ifDescr':            '1.3.6.1.2.1.2.2.1.2',
    'ifType':             '1.3.6.1.2.1.2.2.1.3',
    'ifMtu':              '1.3.6.1.2.1.2.2.1.4',
    'ifSpeed':            '1.3.6.1.2.1.2.2.1.5',
    'ifPhysAddress':      '1.3.6.1.2.1.2.2.1.6',
    'ifAdminStatus':      '1.3.6.1.2.1.2.2.1.7',
    'ifOperStatus':       '1.3.6.1.2.1.2.2.1.8',
    'ifLastChange':       '1.3.6.1.2.1.2.2.1.9',
    'ifInOctets':         '1.3.6.1.2.1.2.2.1.10',
    'ifInUcastPkts':      '1.3.6.1.2.1.2.2.1.11',
    'ifInDiscards':       '1.3.6.1.2.1.2.2.1.13',
    'ifInErrors':         '1.3.6.1.2.1.2.2.1.14',
    'ifOutOctets':        '1.3.6.1.2.1.2.2.1.16',
    'ifOutUcastPkts':     '1.3.6.1.2.1.2.2.1.17',
    'ifOutDiscards':      '1.3.6.1.2.1.2.2.1.19',
    'ifOutErrors':        '1.3.6.1.2.1.2.2.1.20',
    # RFC 2233 ifXTable — 64-bit counters
    'ifName':             '1.3.6.1.2.1.31.1.1.1.1',
    'ifHCInOctets':       '1.3.6.1.2.1.31.1.1.1.6',
    'ifHCOutOctets':      '1.3.6.1.2.1.31.1.1.1.10',
    'ifHighSpeed':        '1.3.6.1.2.1.31.1.1.1.15',
    'ifAlias':            '1.3.6.1.2.1.31.1.1.1.18',
    # RFC 3635 dot3 error counters
    'dot3StatsFCSErrors':          '1.3.6.1.2.1.10.7.2.1.3',
    'dot3StatsLateCollisions':     '1.3.6.1.2.1.10.7.2.1.8',
    'dot3StatsExcessiveCollisions':'1.3.6.1.2.1.10.7.2.1.9',
    'dot3StatsFrameTooLong':       '1.3.6.1.2.1.10.7.2.1.13',
    # MAU MIB — link type/speed negotiated
    'ifMauType':          '1.3.6.1.2.1.26.2.1.1.3',
    'ifMauStatus':        '1.3.6.1.2.1.26.2.1.1.4',
}

IF_STATUS = {1:'up',2:'down',3:'testing',4:'unknown',5:'dormant',6:'notPresent',7:'lowerLayerDown'}
IF_TYPE   = {6:'ethernet',161:'lag',24:'loopback',131:'tunnel',53:'propVirtual',1:'other'}


def snmpget(host, community, oid, timeout=3):
    """Run snmpget, return cleaned value string or None."""
    try:
        r = subprocess.run(
            ['snmpget', '-v2c', '-c', community, '-Oqv', '-t', str(timeout), host, oid],
            capture_output=True, text=True, timeout=timeout+2)
        val = r.stdout.strip()
        return val if val and 'No Such' not in val and 'Timeout' not in val else None
    except Exception:
        return None


def snmpwalk(host, community, base_oid, timeout=5):
    """Run snmpwalk, return {index: value} dict."""
    results = {}
    try:
        r = subprocess.run(
            ['snmpwalk', '-v2c', '-c', community, '-Oqn', '-t', str(timeout), host, base_oid],
            capture_output=True, text=True, timeout=timeout+5)
        for line in r.stdout.splitlines():
            line = line.strip()
            if not line or '=' not in line and ' ' not in line:
                continue
            # Output format with -Oqn: .1.3.6.1.2.1.2.2.1.2.1 "GigabitEthernet0/1"
            parts = line.split(None, 1)
            if len(parts) == 2:
                oid_str, val = parts
                idx = oid_str.rsplit('.', 1)[-1]
                results[idx] = val.strip('"')
    except Exception:
        pass
    return results


def clean(val):
    """Strip SNMP type prefixes like 'STRING:', 'INTEGER:', 'Hex-STRING:' etc."""
    if val is None:
        return ''
    for prefix in ('STRING:', 'INTEGER:', 'Hex-STRING:', 'OID:', 'Timeticks:', 'Counter32:',
                   'Counter64:', 'Gauge32:', 'IpAddress:', 'TimeTicks:'):
        if val.startswith(prefix):
            val = val[len(prefix):].strip()
    return val.strip('"').strip()


def collect_switch(switch, community):
    host = switch['host']
    name = switch['name']
    rows = []
    ts   = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

    def row(cat, key, val, unit=''):
        rows.append({'category': cat, 'key': key,
                     'value': clean(str(val)) if val is not None else '',
                     'unit': unit, 'source': 'snmp_v2c'})

    print(f'  . {name:36s} polling {host}...')

    # ── Scalar OIDs ───────────────────────────────────────────────────────────
    for key, (cat, oid, unit) in SCALAR_OIDS.items():
        val = snmpget(host, community, oid)
        if val:
            if key == 'sysUpTime':
                try:
                    # Timeticks: (12345678) 1:23:45.67  — extract human part
                    if '(' in val:
                        val = val.split(')',1)[-1].strip()
                except Exception:
                    pass
            row(cat, key.replace('ng_',''), val, unit)

    # ── Per-port walks ────────────────────────────────────────────────────────
    walks = {k: snmpwalk(host, community, oid) for k, oid in WALK_OIDS.items()}

    up = down = 0
    idxs = sorted(walks.get('ifDescr', {}).keys(),
                  key=lambda x: int(x) if x.isdigit() else 0)

    for idx in idxs:
        descr   = clean(walks['ifDescr'].get(idx, ''))
        if_name = clean(walks.get('ifName', {}).get(idx, descr))
        alias   = clean(walks.get('ifAlias', {}).get(idx, ''))
        mac     = clean(walks.get('ifPhysAddress', {}).get(idx, ''))

        try:
            if_type = IF_TYPE.get(int(clean(walks.get('ifType',{}).get(idx,'1'))), 'other')
        except Exception:
            if_type = 'other'

        try:
            status = IF_STATUS.get(int(clean(walks.get('ifOperStatus',{}).get(idx,'2'))), 'unknown')
        except Exception:
            status = 'unknown'

        try:
            admin = IF_STATUS.get(int(clean(walks.get('ifAdminStatus',{}).get(idx,'2'))), 'unknown')
        except Exception:
            admin = 'unknown'

        try:
            hs = int(clean(walks.get('ifHighSpeed',{}).get(idx,'0')))
            speed = f'{hs} Mbps' if hs else (
                f'{int(clean(walks.get("ifSpeed",{}).get(idx,"0")))//1_000_000} Mbps')
        except Exception:
            speed = ''

        in_oct  = clean(walks.get('ifHCInOctets',{}).get(idx) or walks.get('ifInOctets',{}).get(idx,''))
        out_oct = clean(walks.get('ifHCOutOctets',{}).get(idx) or walks.get('ifOutOctets',{}).get(idx,''))
        in_err  = clean(walks.get('ifInErrors',{}).get(idx,''))
        out_err = clean(walks.get('ifOutErrors',{}).get(idx,''))
        in_dis  = clean(walks.get('ifInDiscards',{}).get(idx,''))
        out_dis = clean(walks.get('ifOutDiscards',{}).get(idx,''))
        mtu     = clean(walks.get('ifMtu',{}).get(idx,''))
        fcs     = clean(walks.get('dot3StatsFCSErrors',{}).get(idx,''))
        late    = clean(walks.get('dot3StatsLateCollisions',{}).get(idx,''))
        mau_t   = clean(walks.get('ifMauType',{}).get(idx,''))
        mau_s   = clean(walks.get('ifMauStatus',{}).get(idx,''))

        p = f'port{idx}'
        row('Interfaces', f'{p}_name',         if_name)
        row('Interfaces', f'{p}_descr',         descr)
        row('Interfaces', f'{p}_alias',         alias)
        row('Interfaces', f'{p}_type',          if_type)
        row('Interfaces', f'{p}_mac',           mac)
        row('Interfaces', f'{p}_admin',         admin)
        row('Interfaces', f'{p}_status',        status)
        row('Interfaces', f'{p}_speed',         speed)
        row('Interfaces', f'{p}_mtu',           mtu)
        row('Interfaces', f'{p}_in_octets',     in_oct,  'bytes')
        row('Interfaces', f'{p}_out_octets',    out_oct, 'bytes')
        row('Interfaces', f'{p}_in_errors',     in_err)
        row('Interfaces', f'{p}_out_errors',    out_err)
        row('Interfaces', f'{p}_in_discards',   in_dis)
        row('Interfaces', f'{p}_out_discards',  out_dis)
        if fcs:   row('Interfaces', f'{p}_fcs_errors',  fcs)
        if late:  row('Interfaces', f'{p}_late_collisions', late)
        if mau_t: row('Interfaces', f'{p}_mau_type',    mau_t)
        if mau_s: row('Interfaces', f'{p}_mau_status',  mau_s)

        if status == 'up':   up += 1
        elif status == 'down': down += 1

    row('Interfaces', 'ports_up',   str(up))
    row('Interfaces', 'ports_down', str(down))

    out_dir  = FLEET_OUT / name
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f'hw_specs_{name}_{ts}.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['category','key','value','unit','source'])
        w.writeheader()
        w.writerows(rows)

    sym = 'ok' if rows else 'FAIL'
    print(f'  [{sym}] {name:36s} {len(rows)} rows  (up:{up} down:{down})  -> {csv_path.name}')
    return csv_path


def main():
    parser = argparse.ArgumentParser(description='DHG SNMP Collector (SNMPv2c via net-snmp CLI)')
    parser.add_argument('--community', '-c', default=DEFAULT_COMMUNITY)
    parser.add_argument('--host',      '-H', default=None)
    args = parser.parse_args()

    # Verify net-snmp is available
    if subprocess.run(['which','snmpwalk'], capture_output=True).returncode != 0:
        print('[SNMP] ERROR: snmpwalk not found. Install net-snmp:')
        print('  macOS:  brew install net-snmp')
        print('  Linux:  sudo apt install snmp')
        sys.exit(1)

    print(f'\n[DHG SNMP] SNMPv2c  community: {args.community}\n')
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
            print(f'  [FAIL] {sw["name"]:36s} {e}')

    print(f'\n[DHG SNMP] Done -- {ok}/{len(targets)} collected')
    if ok > 0:
        print('[DHG SNMP] Run fleet_report.py to include switches in fleet report')


if __name__ == '__main__':
    main()
