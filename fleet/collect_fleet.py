#!/usr/bin/env python3
"""
DHG Fleet Collector
SSHes into every node in hosts.yml, uploads the right collector script,
runs it, and pulls the CSV back to fleet_output/<hostname>/

Usage:
    python3 fleet/collect_fleet.py
    python3 fleet/collect_fleet.py --host 10.0.0.54   # single node
    python3 fleet/collect_fleet.py --report            # also generate reports
"""

import argparse
import datetime
import os
import subprocess
import sys
import threading
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).parent.parent
SCRIPTS_DIR = ROOT / 'scripts'
REPORTS_DIR = ROOT / 'reports'
HOSTS_FILE  = ROOT / 'fleet' / 'hosts.yml'
OUTPUT_DIR  = ROOT / 'fleet_output'
KEY_PATH    = os.path.expanduser('~/.ssh/dhg_fleet')

COLLECTOR_MAP = {
    'linux':  'collect_linux.py',
    'macos':  'collect_macos.py',
    'windows':'collect_windows.py',
}

lock = threading.Lock()

# ── Helpers ───────────────────────────────────────────────────────────────────
def log(name, msg, icon='·'):
    with lock:
        print(f'  {icon}  {name:28s}  {msg}', flush=True)

def ssh(ip, user, cmd, key=KEY_PATH, timeout=60):
    """Run a command on a remote host via SSH."""
    try:
        return subprocess.run(
            ['ssh',
             '-i', key,
             '-o', 'StrictHostKeyChecking=no',
             '-o', 'BatchMode=yes',
             '-o', 'ConnectTimeout=10',
             '-o', 'IdentitiesOnly=yes',
             f'{user}@{ip}',
             cmd],
            capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        class _R:
            returncode = 1
            stdout = ''
            stderr = f'Connection timed out after {timeout}s'
        return _R()

def scp_put(local, remote_user, remote_ip, remote_path, key=KEY_PATH):
    """Upload a file to a remote host."""
    try:
        return subprocess.run(
            ['scp',
             '-i', key,
             '-o', 'StrictHostKeyChecking=no',
             '-o', 'BatchMode=yes',
             '-o', 'IdentitiesOnly=yes',
             local,
             f'{remote_user}@{remote_ip}:{remote_path}'],
            capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired:
        class _R:
            returncode = 1
            stdout = ''
            stderr = 'SCP upload timed out'
        return _R()

def scp_get(remote_user, remote_ip, remote_path, local_dir, key=KEY_PATH):
    """Download a file from a remote host."""
    return subprocess.run(
        ['scp',
         '-i', key,
         '-o', 'StrictHostKeyChecking=no',
         '-o', 'BatchMode=yes',
         f'{remote_user}@{remote_ip}:{remote_path}',
         str(local_dir)],
        capture_output=True, text=True, timeout=60
    )

# ── Per-node collection ───────────────────────────────────────────────────────
def collect_node(node, generate_report=False):
    ip        = node.get('ip') or node.get('host')
    name      = node.get('name', ip)
    os_type   = node.get('os', 'linux')
    if not ip:
        log(str(name), 'skipping — no IP in hosts.yml', '✗')
        return {'node': name, 'status': 'no_ip', 'ip': 'N/A'}
    user      = node.get('ssh_user', 'swebber64')
    key       = os.path.expanduser(node.get('key_path', KEY_PATH))
    collector = COLLECTOR_MAP.get(os_type, 'collect_linux.py')
    script    = SCRIPTS_DIR / collector

    out_dir   = OUTPUT_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)

    log(name, f'connecting ({ip})')

    # 1 — Test SSH
    test = ssh(ip, user, 'echo OK', key=key, timeout=10)
    if test.returncode != 0:
        log(name, f'SSH failed — skipping. ({test.stderr.strip()})', '✗')
        return {'node': name, 'status': 'ssh_failed', 'ip': ip}

    log(name, 'SSH OK — uploading collector')

    # 2 — Upload collector script
    # Windows uses a different temp path
    if os_type == 'windows':
        remote_script = 'C:\\Windows\\Temp\\' + collector
        remote_csv_glob = 'C:\\Windows\\Temp\\hw_specs_*.csv'
    else:
        remote_script = f'/tmp/{collector}'
        remote_csv_glob = '/tmp/hw_specs_*.csv'
    put = scp_put(str(script), user, ip, remote_script, key=key)
    if put.returncode != 0:
        log(name, f'Upload failed: {put.stderr.strip()}', '✗')
        return {'node': name, 'status': 'upload_failed', 'ip': ip}

    # 3 — Install deps if needed
    log(name, 'checking python deps')
    WINPY = 'C:\\Users\\Dunrs\\AppData\\Local\\Programs\\Python\\Python312\\python.exe'
    WINPIP = 'C:\\Users\\Dunrs\\AppData\\Local\\Programs\\Python\\Python312\\Scripts\\pip.exe'

    if os_type == 'windows':
        dep_cmd = f'{WINPY} -c "import psutil, cpuinfo" 2>nul || {WINPIP} install psutil py-cpuinfo -q 2>nul'
    elif os_type == 'macos':
        dep_cmd = 'python3 -c "import psutil, cpuinfo" 2>/dev/null || pip3 install psutil py-cpuinfo --user -q 2>/dev/null || pip3 install psutil py-cpuinfo -q 2>/dev/null'
    else:
        dep_cmd = 'python3 -c "import psutil, cpuinfo" 2>/dev/null || pip3 install psutil py-cpuinfo --break-system-packages -q 2>/dev/null || pip install psutil py-cpuinfo --break-system-packages -q 2>/dev/null'
    ssh(ip, user, dep_cmd, key=key, timeout=60)

    # 4 — Run collector
    log(name, 'running collector...')
    if os_type == 'windows':
        run_cmd = f'{WINPY} C:\\Windows\\Temp\\' + collector
    else:
        run_cmd = f'cd /tmp && python3 {remote_script}'
    result  = ssh(ip, user, run_cmd, key=key, timeout=120)
    if result.returncode != 0:
        log(name, f'Collector failed: {result.stderr.strip()[:80]}', '✗')
        return {'node': name, 'status': 'collect_failed', 'ip': ip}

    # 5 — Find the CSV on the remote
    if os_type == 'windows':
        find = ssh(ip, user, 'dir /b /od C:\\Windows\\Temp\\hw_specs_*.csv 2>nul', key=key)
        # Get last line (most recent)
        csv_lines = [l.strip() for l in find.stdout.strip().splitlines() if l.strip()]
        find_result = ('C:\\Windows\\Temp\\' + csv_lines[-1]) if csv_lines else ''
    else:
        find = ssh(ip, user, 'ls -t /tmp/hw_specs_*.csv 2>/dev/null | head -1', key=key)
        find_result = find.stdout.strip()
    csv_remote = find_result if os_type == 'windows' else find.stdout.strip()
    if not csv_remote:
        log(name, 'No CSV found on remote', '✗')
        return {'node': name, 'status': 'no_csv', 'ip': ip}

    # 6 — Pull CSV back
    log(name, f'pulling CSV → fleet_output/{name}/')
    get = scp_get(user, ip, csv_remote, str(out_dir), key=key)
    if get.returncode != 0:
        log(name, f'SCP pull failed: {get.stderr.strip()}', '✗')
        return {'node': name, 'status': 'pull_failed', 'ip': ip}

    # Find local CSV
    csvs = sorted(out_dir.glob('hw_specs_*.csv'), key=os.path.getmtime, reverse=True)
    if not csvs:
        log(name, 'CSV not found locally after pull', '✗')
        return {'node': name, 'status': 'local_missing', 'ip': ip}

    csv_local = csvs[0]
    log(name, f'✓ {csv_local.name}', '✓')

    # 7 — Generate reports (optional)
    if generate_report:
        log(name, 'generating reports...')
        subprocess.run(
            [sys.executable,
             str(REPORTS_DIR / 'generate_report.py'),
             str(csv_local),
             '--all',
             '--out', str(out_dir)],
            capture_output=True
        )
        reports = list(out_dir.glob('report_*.html')) + list(out_dir.glob('report_*.md'))
        log(name, f'{len(reports)} reports written')

    # 8 — Cleanup remote
    if os_type == 'windows':
        ssh(ip, user, f'del /f "{csv_remote}" "{remote_script}"', key=key)
    else:
        ssh(ip, user, f'rm -f {csv_remote} {remote_script}', key=key)

    return {
        'node':   name,
        'status': 'ok',
        'ip':     ip,
        'csv':    str(csv_local),
        'os':     os_type,
    }

# ── Load hosts ────────────────────────────────────────────────────────────────
def load_hosts(filter_host=None):
    if not HOSTS_FILE.exists():
        print(f'[ERROR] hosts.yml not found at {HOSTS_FILE}')
        sys.exit(1)
    with open(HOSTS_FILE) as f:
        data = yaml.safe_load(f)
    nodes = data.get('nodes', [])
    if filter_host:
        nodes = [n for n in nodes if n['ip'] == filter_host or n['name'] == filter_host]
    return nodes

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='DHG Fleet Collector')
    parser.add_argument('--host', '-H', default=None,
                        help='Collect from a single host (IP or name)')
    parser.add_argument('--report', '-r', action='store_true',
                        help='Generate all reports after collection')
    parser.add_argument('--workers', '-w', type=int, default=6,
                        help='Parallel workers (default: 6)')
    args = parser.parse_args()

    nodes = load_hosts(args.host)
    if not nodes:
        print('[ERROR] No nodes found. Check hosts.yml or --host value.')
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print(f'\n{"═"*60}')
    print(f'  DHG Fleet Collector — {ts}')
    print(f'  Nodes: {len(nodes)}   Workers: {args.workers}')
    print(f'  Reports: {"yes" if args.report else "no"}')
    print(f'{"═"*60}\n')

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(collect_node, n, args.report): n for n in nodes}
        for f in as_completed(futures):
            try:
                results.append(f.result())
            except Exception as e:
                node = futures[f]
                results.append({'node': node.get('name','unknown'), 'status': 'exception', 'ip': node.get('host','?'), 'error': str(e)})

    # Summary
    ok      = [r for r in results if r['status'] == 'ok']
    failed  = [r for r in results if r['status'] != 'ok']

    print(f'\n{"═"*60}')
    print(f'  FLEET COLLECTION COMPLETE')
    print(f'{"═"*60}')
    print(f'  Success : {len(ok)}/{len(nodes)}')
    print(f'  Failed  : {len(failed)}/{len(nodes)}')
    print()

    for r in ok:
        print(f'  ✓  {r["node"]:28s} {r["ip"]}')
    for r in failed:
        print(f'  ✗  {r["node"]:28s} {r["ip"]}  [{r["status"]}]')

    print(f'\n  Output → {OUTPUT_DIR}')
    print(f'{"═"*60}\n')

    if ok:
        print('  Next: python3 fleet/fleet_report.py  (combined fleet report)')

if __name__ == '__main__':
    # Check for pyyaml
    try:
        import yaml
    except ImportError:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install',
                               'pyyaml', '--break-system-packages', '-q'])
        import yaml
    main()
