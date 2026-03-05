#!/usr/bin/env python3
"""
DHG Fleet Report — Combined side-by-side HTML comparison
Reads all CSVs from fleet_output/<hostname>/ and generates one report.

Usage:
    python3 fleet/fleet_report.py
    python3 fleet/fleet_report.py --out /path/to/output
"""

import argparse
import csv
import datetime
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT       = Path(__file__).parent.parent
FLEET_OUT  = ROOT / 'fleet_output'

DHG_BRAND = {
    'graphite': '#32374A', 'purple': '#663399', 'orange': '#F77E2D',
    'base': '#FAF7F2', 'surface': '#F4F0E8', 'card': '#EDE8DC',
    'border': '#DDD5C4', 'text': '#2E2C26', 'muted': '#4A4236', 'faint': '#6B6456',
}

# Keys to extract for each section
SUMMARY_KEYS = {
    'OS':       ['hostname', 'os', 'distro', 'kernel', 'uptime'],
    'CPU':      ['model', 'physical_cores', 'logical_cores', 'hz_advertised'],
    'CPU_HW':   ['chip_type', 'core_count', 'cpu_cores'],
    'RAM':      ['total', 'available', 'percent'],
    'GPU_NVIDIA': ['gpu0_name', 'gpu0_memory.total', 'gpu0_driver_version',
                   'gpu0_temperature.gpu', 'gpu0_utilization.gpu',
                   'gpu1_name', 'gpu1_memory.total'],
    'GPU_AMD':  ['GPU[0]_Card series', 'GPU[0]_Card model',
                 'GPU[0]_VRAM Total Memory (B)',
                 'GPU[0]_Temperature (Sensor edge) (C)'],
    'GPU':      ['gpu0_name', 'gpu0_vram', 'gpu0_driver'],
    'Storage':  ['disk0_device', 'disk0_total', 'disk0_fstype',
                 'disk1_device', 'disk1_total'],
    'Motherboard': ['manufacturer', 'product', 'version'],
    'MB_System':   ['manufacturer', 'product_name', 'version'],
    'System':      ['manufacturer', 'model'],
    'BIOS':        ['vendor', 'version', 'release_date'],
    'Network':     ['iface0_name', 'iface0_ipv4', 'iface0_speed'],
}


def load_fleet_csvs(fleet_dir):
    nodes = {}
    for node_dir in sorted(fleet_dir.iterdir()):
        if not node_dir.is_dir():
            continue
        csvs = sorted(node_dir.glob('hw_specs_*.csv'), key=os.path.getmtime, reverse=True)
        if not csvs:
            continue
        csv_path = csvs[0]
        rows = {}
        with open(csv_path, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                cat = row.get('category', '')
                key = row.get('key', '')
                rows[f"{cat}.{key}"] = row.get('value', '')
        nodes[node_dir.name] = {
            'data':     rows,
            'csv':      csv_path.name,
            'modified': datetime.datetime.fromtimestamp(
                os.path.getmtime(csv_path)).strftime('%Y-%m-%d %H:%M'),
        }
    return nodes


def get_val(data, cat, key):
    return data.get(f'{cat}.{key}', '')


def best_val(data, *cat_keys):
    """Try multiple category.key combos, return first non-empty."""
    for cat, key in cat_keys:
        v = get_val(data, cat, key)
        if v:
            return v
    return '—'


def build_summary_rows(nodes):
    """Build summary comparison table rows."""
    fields = [
        ('Hostname',     lambda d: best_val(d, ('OS','hostname'))),
        ('OS',           lambda d: best_val(d, ('OS','distro'), ('OS','os'))),
        ('Kernel',       lambda d: best_val(d, ('OS','kernel'))),
        ('CPU',          lambda d: best_val(d, ('CPU','model'), ('CPU_HW','chip_type'))),
        ('Cores (P/L)',  lambda d: '/'.join(filter(None, [
                             best_val(d, ('CPU','physical_cores'), ('CPU_HW','core_count')),
                             best_val(d, ('CPU','logical_cores'))]))),
        ('RAM Total',    lambda d: best_val(d, ('RAM','total'))),
        ('RAM Used %',   lambda d: best_val(d, ('RAM','percent'))),
        ('GPU',          lambda d: best_val(d,
                             ('GPU_NVIDIA','gpu0_name'),
                             ('GPU_AMD','GPU[0]_Card series'),
                             ('GPU','gpu0_name'))),
        ('GPU 2',        lambda d: best_val(d,
                             ('GPU_NVIDIA','gpu1_name'),
                             ('GPU_AMD','GPU[1]_Card series'))),
        ('VRAM',         lambda d: best_val(d,
                             ('GPU_NVIDIA','gpu0_memory.total'),
                             ('GPU_AMD','GPU[0]_VRAM Total Memory (B)'),
                             ('GPU','gpu0_vram'))),
        ('GPU Temp',     lambda d: best_val(d,
                             ('GPU_NVIDIA','gpu0_temperature.gpu'),
                             ('GPU_AMD','GPU[0]_Temperature (Sensor edge) (C)'))),
        ('Motherboard',  lambda d: best_val(d,
                             ('Motherboard','product'),
                             ('MB_System','product_name'),
                             ('System','model'))),
        ('Storage 0',    lambda d: ' '.join(filter(None, [
                             best_val(d, ('Storage','disk0_device')),
                             best_val(d, ('Storage','disk0_total'))]))),
    ]
    return fields


def temp_class(val):
    try:
        t = float(str(val).replace('°C','').strip())
        return 'warn' if t > 80 else 'good' if t < 60 else ''
    except Exception:
        return ''


def render_html(nodes, out_path):
    node_names = list(nodes.keys())
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    fields = build_summary_rows(nodes)

    # Build summary table
    header_cells = ''.join(f'<th>{n}</th>' for n in node_names)
    rows_html = ''
    for label, fn in fields:
        cells = ''
        for name in node_names:
            val = fn(nodes[name]['data'])
            cls = ''
            if 'Temp' in label:
                cls = temp_class(val)
            if val and val != '—' and any(x in val.lower() for x in ('nvidia','rtx','geforce','amd','radeon')):
                cls = 'gpu'
            cells += f'<td class="{cls}">{val if val else "—"}</td>'
        rows_html += f'<tr><td class="row-label">{label}</td>{cells}</tr>\n'

    # Collection metadata row
    meta_cells = ''.join(
        f'<td class="meta-cell">{nodes[n]["modified"]}<br><span class="csv-name">{nodes[n]["csv"]}</span></td>'
        for n in node_names
    )

    col_width = max(120, 600 // max(len(node_names), 1))

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DHG Fleet Report</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'IBM Plex Sans', sans-serif; background: {DHG_BRAND["base"]}; color: {DHG_BRAND["text"]}; }}

  .site-header {{
    background: {DHG_BRAND["graphite"]}; color: #fff;
    padding: 1.25rem 2rem; display: flex; align-items: center;
    justify-content: space-between; border-bottom: 3px solid {DHG_BRAND["orange"]};
  }}
  .site-header h1 {{ font-size: 1rem; font-weight: 600; }}
  .site-header .meta {{ font-size: 0.75rem; opacity: 0.6; text-align: right; }}

  .title-bar {{
    background: {DHG_BRAND["surface"]}; border-bottom: 1px solid {DHG_BRAND["border"]};
    padding: 1rem 2rem; display: flex; align-items: center; gap: 1rem;
  }}
  .title-bar h2 {{ font-size: 1.3rem; font-weight: 600; color: {DHG_BRAND["graphite"]}; }}
  .badge {{
    background: {DHG_BRAND["purple"]}; color: #fff;
    font-size: 0.68rem; font-weight: 600; padding: 0.2rem 0.55rem;
    border-radius: 3px; letter-spacing: 0.06em; text-transform: uppercase;
  }}
  .node-count {{ margin-left: auto; font-size: 0.8rem; color: {DHG_BRAND["faint"]}; }}

  .content {{ padding: 1.5rem 2rem 4rem; overflow-x: auto; }}

  table {{ border-collapse: collapse; min-width: 100%; font-size: 0.82rem; }}
  th, td {{ padding: 0.45rem 0.9rem; border: 1px solid {DHG_BRAND["border"]}; text-align: left; vertical-align: top; }}

  thead th {{
    background: {DHG_BRAND["graphite"]}; color: #fff;
    font-size: 0.75rem; font-weight: 600; white-space: nowrap;
    min-width: {col_width}px;
  }}
  thead th:first-child {{ background: {DHG_BRAND["surface"]}; color: {DHG_BRAND["faint"]}; min-width: 120px; }}

  .row-label {{
    background: {DHG_BRAND["surface"]}; font-weight: 600;
    font-size: 0.72rem; color: {DHG_BRAND["purple"]}; white-space: nowrap;
    letter-spacing: 0.04em; text-transform: uppercase;
  }}
  tr:nth-child(even) td:not(.row-label) {{ background: {DHG_BRAND["card"]}; }}
  tr:hover td {{ background: rgba(102,51,153,0.06); }}

  .gpu {{ color: {DHG_BRAND["purple"]}; font-weight: 500; }}
  .warn {{ color: {DHG_BRAND["orange"]}; font-weight: 500; }}
  .good {{ color: #2a7a3b; }}

  .meta-cell {{ font-size: 0.7rem; color: {DHG_BRAND["faint"]}; background: {DHG_BRAND["surface"]} !important; }}
  .csv-name {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.65rem; }}

  .section-divider td {{
    background: {DHG_BRAND["graphite"]}; color: #fff;
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.08em;
    text-transform: uppercase; padding: 0.35rem 0.9rem;
    border-color: {DHG_BRAND["graphite"]};
  }}

  .footer {{
    margin-top: 2rem; padding-top: 1rem;
    border-top: 1px solid {DHG_BRAND["border"]};
    font-size: 0.72rem; color: {DHG_BRAND["faint"]};
    display: flex; justify-content: space-between;
  }}
  .footer-brand {{ font-weight: 600; color: {DHG_BRAND["purple"]}; }}
</style>
</head>
<body>

<header class="site-header">
  <h1>Digital Harmony Group &mdash; DHG Labs</h1>
  <div class="meta">Generated {ts}<br>dhg-hw-spec-collector fleet report</div>
</header>

<div class="title-bar">
  <h2>Fleet Hardware Report</h2>
  <span class="badge">fleet</span>
  <span class="node-count">{len(node_names)} nodes</span>
</div>

<div class="content">
<table>
  <thead>
    <tr>
      <th>Spec</th>
      {header_cells}
    </tr>
  </thead>
  <tbody>
    <tr class="section-divider"><td colspan="{len(node_names)+1}">Collection Info</td></tr>
    <tr><td class="row-label">Collected</td>{meta_cells}</tr>
    <tr class="section-divider"><td colspan="{len(node_names)+1}">System</td></tr>
    {rows_html}
  </tbody>
</table>

<div class="footer">
  <span><span class="footer-brand">DHG Labs</span> &mdash; Digital Harmony Group</span>
  <span>{len(node_names)} nodes &bull; {ts}</span>
</div>
</div>

</body>
</html>'''

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'[DHG FLEET] Report written → {out_path}')


def main():
    parser = argparse.ArgumentParser(description='DHG Fleet Report Generator')
    parser.add_argument('--out', '-o', default=None,
                        help='Output directory (default: fleet_output/)')
    args = parser.parse_args()

    if not FLEET_OUT.exists():
        print(f'[ERROR] fleet_output/ not found at {FLEET_OUT}')
        print('        Run fleet/collect_fleet.py first.')
        sys.exit(1)

    nodes = load_fleet_csvs(FLEET_OUT)
    if not nodes:
        print('[ERROR] No CSVs found in fleet_output/')
        print('        Run fleet/collect_fleet.py first.')
        sys.exit(1)

    print(f'[DHG FLEET] {len(nodes)} nodes found: {", ".join(nodes.keys())}')

    out_dir = Path(args.out) if args.out else FLEET_OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    out_path = out_dir / f'fleet_report_{ts}.html'

    render_html(nodes, out_path)


if __name__ == '__main__':
    main()
