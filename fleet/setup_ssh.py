#!/usr/bin/env python3
"""
DHG Fleet SSH Setup — One shot
Generates SSH key, pushes to all nodes, tests connections.
You enter each machine's password once. Never again after that.

Usage:
    python3 fleet/setup_ssh.py
"""

import os
import subprocess
import sys

KEY_PATH   = os.path.expanduser('~/.ssh/dhg_fleet')
KEY_PUB    = KEY_PATH + '.pub'
SSH_USER   = 'swebber64'

# All SSH-able nodes from hosts.yml
NODES = [
    {'ip': '10.0.0.54',  'name': 'DHG5090',              'os': 'linux'},
    {'ip': '10.0.0.80',  'name': 'JJ',                   'os': 'linux'},
    {'ip': '10.0.0.92',  'name': 'FAFaudiodesk',          'os': 'macos'},
    {'ip': '10.0.0.116', 'name': 'MacBook-Pro-2',         'os': 'macos'},
    {'ip': '10.0.0.169', 'name': 'MacBook-Pro-2b',        'os': 'macos'},
    {'ip': '10.0.0.179', 'name': 'dh40801',               'os': 'macos'},
    {'ip': '10.0.0.235', 'name': 'Stephens-MacBook-Pro',  'os': 'macos'},
    {'ip': '10.0.0.251', 'name': 'g700data1',             'os': 'linux'},
]

def banner(msg):
    print(f'\n{"─"*60}')
    print(f'  {msg}')
    print(f'{"─"*60}')

def run(cmd, capture=True):
    return subprocess.run(cmd, shell=True,
                          capture_output=capture,
                          text=True)

# ── Step 1: Generate key ──────────────────────────────────────────────────────
banner('STEP 1 — SSH Key')
if os.path.exists(KEY_PATH):
    print(f'  ✓ Key already exists: {KEY_PATH}')
else:
    print(f'  Generating ed25519 key → {KEY_PATH}')
    r = run(f'ssh-keygen -t ed25519 -C "swebber64@dhg" -f {KEY_PATH} -N ""')
    if r.returncode == 0:
        print(f'  ✓ Key generated')
    else:
        print(f'  ✗ Key generation failed: {r.stderr}')
        sys.exit(1)

with open(KEY_PUB) as f:
    pubkey = f.read().strip()
print(f'\n  Public key:\n  {pubkey}\n')

# ── Step 2: Enable SSH on macOS nodes ─────────────────────────────────────────
banner('STEP 2 — macOS SSH Note')
print('''  On each Mac, make sure Remote Login is enabled:
  System Settings → General → Sharing → Remote Login → ON
  (Only needs to be done once per machine)
  Press Enter when ready to continue...''')
input()

# ── Step 3: Push key to each node ─────────────────────────────────────────────
banner('STEP 3 — Push SSH Key to All Nodes')
print('  You will be prompted for each machine\'s password once.\n')

results = {}
for node in NODES:
    ip   = node['ip']
    name = node['name']
    print(f'  → {name} ({ip})')

    # First check if key already works
    test = run(
        f'ssh -i {KEY_PATH} -o ConnectTimeout=3 -o BatchMode=yes '
        f'-o StrictHostKeyChecking=no {SSH_USER}@{ip} "echo OK"'
    )
    if test.returncode == 0:
        print(f'    ✓ Already authorized — skipping')
        results[name] = 'already_ok'
        continue

    # Check if host is reachable at all
    ping = run(f'ping -c 1 -W 2 {ip}')
    if ping.returncode != 0:
        print(f'    ✗ Host unreachable — skipping')
        results[name] = 'unreachable'
        continue

    # ssh-copy-id — will prompt for password
    print(f'    Enter password for {SSH_USER}@{name}:')
    r = subprocess.run(
        f'ssh-copy-id -i {KEY_PUB} '
        f'-o ConnectTimeout=10 '
        f'-o StrictHostKeyChecking=no '
        f'{SSH_USER}@{ip}',
        shell=True
    )
    if r.returncode == 0:
        print(f'    ✓ Key pushed successfully')
        results[name] = 'pushed'
    else:
        print(f'    ✗ Failed — check SSH is enabled on this machine')
        results[name] = 'failed'

# ── Step 4: Test all connections ──────────────────────────────────────────────
banner('STEP 4 — Testing All Connections')
ready = []
for node in NODES:
    ip   = node['ip']
    name = node['name']
    test = run(
        f'ssh -i {KEY_PATH} -o ConnectTimeout=5 -o BatchMode=yes '
        f'-o StrictHostKeyChecking=no {SSH_USER}@{ip} '
        f'"uname -s && hostname"'
    )
    if test.returncode == 0:
        out = test.stdout.strip().replace('\n', ' / ')
        print(f'  ✓  {name:30s} {ip:16s}  {out}')
        ready.append(node)
        results[name] = 'ready'
    else:
        print(f'  ✗  {name:30s} {ip:16s}  NOT REACHABLE')

# ── Summary ───────────────────────────────────────────────────────────────────
banner('SUMMARY')
print(f'  Ready for fleet collection : {len(ready)}/{len(NODES)} nodes\n')
for node in NODES:
    status = results.get(node["name"], "unknown")
    icon   = '✓' if status == 'ready' else '✗'
    print(f'  {icon}  {node["name"]:30s} {node["ip"]}  [{status}]')

if len(ready) > 0:
    print(f'\n  Run the fleet collector next:')
    print(f'  python3 fleet/collect_fleet.py')
else:
    print(f'\n  No nodes ready. Check SSH is enabled on each machine.')
