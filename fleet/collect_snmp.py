#!/usr/bin/env python3
"""
DHG SNMP Collector — puresnmp v2 async (SNMPv2c)
Usage:
    python3 fleet/collect_snmp.py
    python3 fleet/collect_snmp.py --host 10.0.0.4
    python3 fleet/collect_snmp.py --community public
"""
import argparse, asyncio, csv, datetime, subprocess, sys
from pathlib import Path

ROOT      = Path(__file__).parent.parent
FLEET_OUT = ROOT / 'fleet_output'
DEFAULT_COMMUNITY = 'public'

SWITCHES = [
    {'host': '10.0.0.4',   'name': 'Sidecar-4250-12port', 'model': 'M4250-12'},
    {'host': '10.0.0.7',   'name': 'LivingRoom-4250-12',  'model': 'M4250-12'},
    {'host': '10.0.0.134', 'name': 'StudioDesk-4250-24',  'model': 'M4250-24'},
]

# ──────────────────────────────────────────────
# MIB-II  RFC 1213 — system group
# ──────────────────────────────────────────────
OIDS = {
    'sysDescr':    '1.3.6.1.2.1.1.1.0',   # Full text description
    'sysObjectID': '1.3.6.1.2.1.1.2.0',   # Enterprise OID
    'sysUpTime':   '1.3.6.1.2.1.1.3.0',   # Centiseconds since last reinit
    'sysContact':  '1.3.6.1.2.1.1.4.0',
    'sysName':     '1.3.6.1.2.1.1.5.0',
    'sysLocation': '1.3.6.1.2.1.1.6.0',
    'sysServices': '1.3.6.1.2.1.1.7.0',   # Layer bitmap (e.g. 78 = L2+L3)
    # interfaces summary
    'ifNumber':    '1.3.6.1.2.1.2.1.0',   # Total interface count
    # dot1d bridge (STP)
    'dot1dBaseBridgeAddress': '1.3.6.1.2.1.17.1.1.0',  # Switch base MAC
    'dot1dBaseNumPorts':      '1.3.6.1.2.1.17.1.2.0',  # Physical port count
    'dot1dStpProtocolSpecification': '1.3.6.1.2.1.17.2.1.0',  # STP variant
    'dot1dStpRootCost':       '1.3.6.1.2.1.17.2.6.0',
    'dot1dStpRootPort':       '1.3.6.1.2.1.17.2.7.0',
    # IP MIB — routing / forwarding
    'ipForwarding':  '1.3.6.1.2.1.4.1.0',   # 1=forwarding, 2=not-forwarding
    'ipDefaultTTL':  '1.3.6.1.2.1.4.2.0',
    # ──────────────────────────────────────────
    # NETGEAR enterprise MIB  OID prefix: 1.3.6.1.4.1.4526
    # ng10  = NETGEAR-SWITCHING-MIB  (.10)
    # ──────────────────────────────────────────
    # agentInventory — unit table (.10.1.1.1.1.x)
    'ng_unitNum':     '1.3.6.1.4.1.4526.10.1.1.1.1.1.1',  # Unit number
    'ng_unitType':    '1.3.6.1.4.1.4526.10.1.1.1.1.2.1',  # Unit type code
    'ng_model':       '1.3.6.1.4.1.4526.10.1.1.1.1.3.1',  # Model string
    'ng_swVersion':   '1.3.6.1.4.1.4526.10.1.1.1.1.4.1',  # Software version
    'ng_hwVersion':   '1.3.6.1.4.1.4526.10.1.1.1.1.5.1',  # Hardware version
    'ng_serialNum':   '1.3.6.1.4.1.4526.10.1.1.1.1.6.1',  # Serial number
    'ng_mfgDate':     '1.3.6.1.4.1.4526.10.1.1.1.1.8.1',  # Manufacturing date
    # agentSwitchCpuProcessTotalUtilization
    'ng_cpuUtil1s':   '1.3.6.1.4.1.4526.10.1.36.1.0',     # CPU util 1-sec %
    'ng_cpuUtil5s':   '1.3.6.1.4.1.4526.10.1.36.2.0',     # CPU util 5-sec %
    'ng_cpuUtil1m':   '1.3.6.1.4.1.4526.10.1.36.3.0',     # CPU util 1-min %
    # agentSwitchMemory
    'ng_memTotal':    '1.3.6.1.4.1.4526.10.1.56.1.0',     # Total RAM (KB)
    'ng_memFree':     '1.3.6.1.4.1.4526.10.1.56.2.0',     # Free  RAM (KB)
    # agentSwitchTemperature
    'ng_tempSensor':  '1.3.6.1.4.1.4526.10.1.53.1.1.3.1', # Temp °C unit 1
    'ng_tempStatus':  '1.3.6.1.4.1.4526.10.1.53.1.1.4.1', # 1=normal,2=warning,3=critical
    # agentSwitchFan
    'ng_fanStatus1':  '1.3.6.1.4.1.4526.10.1.54.1.1.3.1', # Fan 1 status
    'ng_fanStatus2':  '1.3.6.1.4.1.4526.10.1.54.1.1.3.2', # Fan 2 status
    # agentPowerSupply
    'ng_psu1Status':  '1.3.6.1.4.1.4526.10.1.55.1.1.3.1', # PSU 1 status
    'ng_psu2Status':  '1.3.6.1.4.1.4526.10.1.55.1.1.3.2', # PSU 2 status
    # PoE — agentPethMainPseObjects (.10.15.2.x)
    'ng_poeMainPower':      '1.3.6.1.4.1.4526.10.15.2.1.1.2.1',  # Nominal power (W)
    'ng_poeConsumedPower':  '1.3.6.1.4.1.4526.10.15.2.1.1.3.1',  # Consumed power (W)
    'ng_poePowerStatus':    '1.3.6.1.4.1.4526.10.15.2.1.1.4.1',  # 1=on,2=off,3=faulty
    # LLDP local system  (IEEE 802.1AB  MIB)
    'lldpLocChassisIdSubtype': '1.0.8802.1.1.2.1.3.1.0',
    'lldpLocChassisId':        '1.0.8802.1.1.2.1.3.2.0',
    'lldpLocSysName':          '1.0.8802.1.1.2.1.3.3.0',
    'lldpLocSysDesc':          '1.0.8802.1.1.2.1.3.4.0',
}

# ──────────────────────────────────────────────
# RFC 2863 ifTable (1.3.6.1.2.1.2.2.1.x) — per-port walk
# ──────────────────────────────────────────────
IF_OIDS = {
    'ifDescr':       '1.3.6.1.2.1.2.2.1.2',   # Interface name (e.g. "0/1")
    'ifType':        '1.3.6.1.2.1.2.2.1.3',   # 6=ethernetCsmacd, 161=ieee8023adLag
    'ifMtu':         '1.3.6.1.2.1.2.2.1.4',
    'ifSpeed':       '1.3.6.1.2.1.2.2.1.5',   # bps (32-bit; use ifHighSpeed for 1G+)
    'ifPhysAddress': '1.3.6.1.2.1.2.2.1.6',   # MAC address
    'ifAdminStatus': '1.3.6.1.2.1.2.2.1.7',   # 1=up 2=down 3=testing
    'ifOperStatus':  '1.3.6.1.2.1.2.2.1.8',   # 1=up 2=down 3=testing …
    'ifLastChange':  '1.3.6.1.2.1.2.2.1.9',   # Timeticks of last status change
    'ifInOctets':    '1.3.6.1.2.1.2.2.1.10',
    'ifInUcastPkts': '1.3.6.1.2.1.2.2.1.11',
    'ifInDiscards':  '1.3.6.1.2.1.2.2.1.13',
    'ifInErrors':    '1.3.6.1.2.1.2.2.1.14',
    'ifOutOctets':   '1.3.6.1.2.1.2.2.1.16',
    'ifOutUcastPkts':'1.3.6.1.2.1.2.2.1.17',
    'ifOutDiscards': '1.3.6.1.2.1.2.2.1.19',
    'ifOutErrors':   '1.3.6.1.2.1.2.2.1.20',
}

# ──────────────────────────────────────────────
# IF-MIB ifXTable — 64-bit counters + names (RFC 2233)
# ──────────────────────────────────────────────
IFX_OIDS = {
    'ifName':           '1.3.6.1.2.1.31.1.1.1.1',   # Short name (e.g. "1/0/1")
    'ifInMulticastPkts':'1.3.6.1.2.1.31.1.1.1.2',
    'ifInBroadcastPkts':'1.3.6.1.2.1.31.1.1.1.3',
    'ifOutMulticastPkts':'1.3.6.1.2.1.31.1.1.1.4',
    'ifOutBroadcastPkts':'1.3.6.1.2.1.31.1.1.1.5',
    'ifHCInOctets':     '1.3.6.1.2.1.31.1.1.1.6',   # 64-bit in bytes
    'ifHCInUcastPkts':  '1.3.6.1.2.1.31.1.1.1.7',
    'ifHCOutOctets':    '1.3.6.1.2.1.31.1.1.1.10',  # 64-bit out bytes
    'ifHCOutUcastPkts': '1.3.6.1.2.1.31.1.1.1.11',
    'ifHighSpeed':      '1.3.6.1.2.1.31.1.1.1.15',  # Mbps (use this for 1G/2.5G/10G)
    'ifPromiscuousMode':'1.3.6.1.2.1.31.1.1.1.16',
    'ifAlias':          '1.3.6.1.2.1.31.1.1.1.18',  # Admin-assigned description
    'ifCounterDiscontinuityTime': '1.3.6.1.2.1.31.1.1.1.19',
}

# ──────────────────────────────────────────────
# dot3 Ethernet-like MIB (RFC 3635) — per-port walk
# ──────────────────────────────────────────────
DOT3_OIDS = {
    'dot3StatsFCSErrors':          '1.3.6.1.2.1.10.7.2.1.3',
    'dot3StatsSingleCollisionFrames':'1.3.6.1.2.1.10.7.2.1.4',
    'dot3StatsMultipleCollisionFrames':'1.3.6.1.2.1.10.7.2.1.5',
    'dot3StatsDeferredTransmissions':'1.3.6.1.2.1.10.7.2.1.7',
    'dot3StatsLateCollisions':     '1.3.6.1.2.1.10.7.2.1.8',
    'dot3StatsExcessiveCollisions':'1.3.6.1.2.1.10.7.2.1.9',
    'dot3StatsInternalMacTransmitErrors':'1.3.6.1.2.1.10.7.2.1.10',
    'dot3StatsFrameTooLong':       '1.3.6.1.2.1.10.7.2.1.13',
}

# ──────────────────────────────────────────────
# IEEE 802.3az EEE / MAU MIB — link speed negotiated
# ──────────────────────────────────────────────
MAU_OIDS = {
    'ifMauType':     '1.3.6.1.2.1.26.2.1.1.3',  # MAU type OID (speed+duplex)
    'ifMauStatus':   '1.3.6.1.2.1.26.2.1.1.4',  # 1=other,2=unknown,3=operational
    'ifMauMediaAvailable': '1.3.6.1.2.1.26.2.1.1.5',
}

IF_STATUS = {1:'up', 2:'down', 3:'testing', 4:'unknown', 5:'dormant', 6:'notPresent', 7:'lowerLayerDown'}
IF_TYPE   = {6:'ethernet', 161:'lag', 24:'loopback', 131:'tunnel', 1:'other'}


def ensure_puresnmp():
    try:
        import puresnmp; return True  # noqa
    except ImportError:
        print('[SNMP] Installing puresnmp...')
        for flag in ['--user', '--break-system-packages']:
            r = subprocess.run([sys.executable, '-m', 'pip', 'install', 'puresnmp', flag, '-q'],
                               capture_output=True)
            if r.returncode == 0: return True
        return False


async def _aget(host, community, oid):
    from puresnmp import Client, V2C
    from x690.types import ObjectIdentifier
    client = Client(host, V2C(community))
    try:
        return await client.get(ObjectIdentifier(oid))
    except Exception:
        return None


async def _awalk(host, community, base_oid):
    from puresnmp import Client, V2C
    from x690.types import ObjectIdentifier
    results = {}
    client = Client(host, V2C(community))
    try:
        async for oid, val in client.walk(ObjectIdentifier(base_oid)):
            idx = str(oid).split('.')[-1]
            results[idx] = val
    except Exception:
        pass
    return results


def snmp_get(host, community, oid):
    return asyncio.run(_aget(host, community, oid))


def snmp_walk(host, community, base_oid):
    return asyncio.run(_awalk(host, community, base_oid))


def fmt(val):
    if val is None: return ''
    if isinstance(val, (bytes, bytearray)):
        try: return val.decode('utf-8', errors='replace').strip('\x00')
        except Exception: return val.hex(':')
    return str(val)


def fmt_mac(val):
    if isinstance(val, (bytes, bytearray)) and len(val) == 6:
        return ':'.join(f'{b:02x}' for b in val)
    return fmt(val)


def collect_switch(switch, community):
    host = switch['host']
    name = switch['name']
    rows = []
    ts   = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

    def row(cat, key, val, unit=''):
        rows.append({'category': cat, 'key': key, 'value': fmt(val), 'unit': unit, 'source': 'snmp_v2c'})

    print(f'  . {name:36s} polling {host}...')

    # System group
    for key, oid in OIDS.items():
        if key.startswith('ng_') or key == 'ifNumber': continue
        val = snmp_get(host, community, oid)
        if val is not None:
            if key == 'sysUpTime':
                try:
                    s = int(str(val)) // 100
                    val = f'{s//86400}d {(s%86400)//3600}h {(s%3600)//60}m {s%60}s'
                except Exception: pass
            row('System', key, val)

    # NETGEAR OIDs
    for key, oid in OIDS.items():
        if not key.startswith('ng_'): continue
        val = snmp_get(host, community, oid)
        if val is not None:
            row('Hardware', key.replace('ng_',''), val)

    row('Interfaces', 'total_interfaces', snmp_get(host, community, OIDS['ifNumber']) or '0')

    # NETGEAR health — CPU, memory, temperature, fans, PSUs, PoE
    health_keys = ['ng_cpuUtil1s','ng_cpuUtil5s','ng_cpuUtil1m',
                   'ng_memTotal','ng_memFree',
                   'ng_tempSensor','ng_tempStatus',
                   'ng_fanStatus1','ng_fanStatus2',
                   'ng_psu1Status','ng_psu2Status',
                   'ng_poeMainPower','ng_poeConsumedPower','ng_poePowerStatus']
    for key in health_keys:
        if key in OIDS:
            val = snmp_get(host, community, OIDS[key])
            if val is not None:
                cat = ('PoE'        if 'poe'  in key else
                       'Health.Temp' if 'temp' in key else
                       'Health.Fan'  if 'fan'  in key else
                       'Health.PSU'  if 'psu'  in key else
                       'Health.CPU'  if 'cpu'  in key else
                       'Health.Mem')
                unit = ('%' if 'Util' in key else
                        'KB' if key in ('ng_memTotal','ng_memFree') else
                        'C'  if key == 'ng_tempSensor' else
                        'W'  if 'Power' in key else '')
                row(cat, key.replace('ng_',''), val, unit)

    # LLDP local info
    for key in ('lldpLocChassisId','lldpLocSysName','lldpLocSysDesc'):
        if key in OIDS:
            val = snmp_get(host, community, OIDS[key])
            if val is not None:
                row('LLDP', key, val)

    # Interface tables
    if_data   = {k: snmp_walk(host, community, v) for k, v in IF_OIDS.items()}
    ifx_data  = {k: snmp_walk(host, community, v) for k, v in IFX_OIDS.items()}
    dot3_data = {k: snmp_walk(host, community, v) for k, v in DOT3_OIDS.items()}
    mau_data  = {k: snmp_walk(host, community, v) for k, v in MAU_OIDS.items()}

    up = down = 0
    idxs = sorted(if_data.get('ifDescr', {}).keys(),
                  key=lambda x: int(x) if x.isdigit() else 0)

    for idx in idxs:
        descr   = fmt(if_data['ifDescr'].get(idx, ''))
        if_name = fmt(ifx_data['ifName'].get(idx, descr))
        alias   = fmt(ifx_data['ifAlias'].get(idx, ''))
        mac     = fmt_mac(if_data['ifPhysAddress'].get(idx, b''))

        try:
            if_type = IF_TYPE.get(int(str(if_data['ifType'].get(idx,1))), 'other')
        except Exception:
            if_type = 'other'

        try:
            status = IF_STATUS.get(int(str(if_data['ifOperStatus'].get(idx,'2'))), 'unknown')
        except Exception:
            status = 'unknown'

        try:
            admin = IF_STATUS.get(int(str(if_data['ifAdminStatus'].get(idx,'2'))), 'unknown')
        except Exception:
            admin = 'unknown'

        try:
            hs = int(str(ifx_data['ifHighSpeed'].get(idx,'0')))
            speed = f'{hs} Mbps' if hs else '—'
        except Exception:
            try:
                speed = f'{int(str(if_data["ifSpeed"].get(idx,"0")))//1_000_000} Mbps'
            except Exception:
                speed = '—'

        in_oct  = fmt(ifx_data['ifHCInOctets'].get(idx) or if_data['ifInOctets'].get(idx,'0'))
        out_oct = fmt(ifx_data['ifHCOutOctets'].get(idx) or if_data['ifOutOctets'].get(idx,'0'))
        in_err  = fmt(if_data['ifInErrors'].get(idx,'0'))
        out_err = fmt(if_data['ifOutErrors'].get(idx,'0'))
        mtu     = fmt(if_data['ifMtu'].get(idx,''))

        p = f'port{idx}'
        row('Interfaces', f'{p}_name',       if_name)
        row('Interfaces', f'{p}_descr',      descr)
        row('Interfaces', f'{p}_alias',      alias)
        row('Interfaces', f'{p}_type',       if_type)
        row('Interfaces', f'{p}_mac',        mac)
        row('Interfaces', f'{p}_admin',      admin)
        row('Interfaces', f'{p}_status',     status)
        row('Interfaces', f'{p}_speed',      speed)
        row('Interfaces', f'{p}_mtu',        mtu)
        row('Interfaces', f'{p}_in_octets',  in_oct,  'bytes')
        row('Interfaces', f'{p}_out_octets', out_oct, 'bytes')
        row('Interfaces', f'{p}_in_errors',  in_err)
        row('Interfaces', f'{p}_out_errors', out_err)

        # dot3 error counters
        fcs = fmt(dot3_data.get('dot3StatsFCSErrors',{}).get(idx,''))
        late = fmt(dot3_data.get('dot3StatsLateCollisions',{}).get(idx,''))
        exc  = fmt(dot3_data.get('dot3StatsExcessiveCollisions',{}).get(idx,''))
        frame_long = fmt(dot3_data.get('dot3StatsFrameTooLong',{}).get(idx,''))
        if fcs:       row('Interfaces', f'{p}_fcs_errors',  fcs)
        if late:      row('Interfaces', f'{p}_late_collisions', late)
        if exc:       row('Interfaces', f'{p}_excess_collisions', exc)
        if frame_long:row('Interfaces', f'{p}_frame_too_long', frame_long)

        # MAU (negotiated link type)
        mau_type = fmt(mau_data.get('ifMauType',{}).get(idx,''))
        mau_stat = fmt(mau_data.get('ifMauStatus',{}).get(idx,''))
        if mau_type: row('Interfaces', f'{p}_mau_type',   mau_type)
        if mau_stat: row('Interfaces', f'{p}_mau_status', mau_stat)

        if status == 'up':    up += 1
        elif status == 'down': down += 1

    row('Interfaces', 'ports_up',   str(up))
    row('Interfaces', 'ports_down', str(down))

    out_dir  = FLEET_OUT / name
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f'hw_specs_{name}_{ts}.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['category','key','value','unit','source'])
        w.writeheader(); w.writerows(rows)

    status_sym = 'ok' if rows else 'FAIL'
    print(f'  [{status_sym}] {name:36s} {len(rows)} rows  (up:{up} down:{down})  -> {csv_path.name}')
    return csv_path


def main():
    parser = argparse.ArgumentParser(description='DHG SNMP Collector (SNMPv2c)')
    parser.add_argument('--community', '-c', default=DEFAULT_COMMUNITY)
    parser.add_argument('--host',      '-H', default=None)
    args = parser.parse_args()

    if not ensure_puresnmp():
        print('[SNMP] ERROR: could not install puresnmp'); sys.exit(1)

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
