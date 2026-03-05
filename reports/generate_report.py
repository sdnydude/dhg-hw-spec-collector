#!/usr/bin/env python3
"""
DHG Hardware Spec Report Generator
Reads a hw_specs_*.csv and renders a chosen report template.

Usage:
    python3 generate_report.py <csv_file> [--type TYPE] [--format FORMAT] [--out DIR]

Types:   full | executive | gpu | storage | network  (default: full)
Formats: html | markdown                              (default: html)

Examples:
    python3 reports/generate_report.py output/hw_specs_MYHOST_20260305.csv
    python3 reports/generate_report.py output/hw_specs_MYHOST_20260305.csv --type gpu --format html
    python3 reports/generate_report.py output/hw_specs_MYHOST_20260305.csv --type executive --format markdown
"""

import argparse
import csv
import datetime
import os
import sys
from collections import defaultdict
from pathlib import Path

# ── Report category filters ───────────────────────────────────────────────────
REPORT_FILTERS = {
    'full': None,  # None = all categories
    'executive': {
        'OS':           ['hostname', 'os', 'distro', 'os_release', 'mac_version',
                         'sw_productversion', 'uptime', 'kernel'],
        'CPU':          ['model', 'architecture', 'physical_cores', 'logical_cores',
                         'hz_advertised', 'hz_actual', 'freq_max', 'l2_cache', 'l3_cache'],
        'CPU_HW':       None,
        'RAM':          ['total', 'available', 'used', 'percent'],
        'Storage':      None,
        'GPU_NVIDIA':   ['gpu0_name', 'gpu0_driver_version', 'gpu0_memory.total',
                         'gpu0_utilization.gpu', 'gpu0_temperature.gpu'],
        'GPU_AMD':      None,
        'GPU':          ['gpu0_name', 'gpu0_vram', 'gpu0_driver'],
        'Motherboard':  None,
        'MB_System':    None,
        'BIOS':         None,
        'System':       None,
    },
    'gpu': {
        'GPU_NVIDIA':   None,
        'GPU_AMD':      None,
        'GPU':          None,
        'GPU_IOREG':    None,
        'CPU':          ['model', 'physical_cores', 'logical_cores'],
        'RAM':          ['total'],
        'Thermal':      None,
        'OS':           ['hostname', 'os', 'distro', 'kernel'],
        'PCI':          None,
    },
    'storage': {
        'Storage':      None,
        'Storage_NVMe': None,
        'Storage_Detail': None,
        'OS':           ['hostname', 'os', 'distro'],
    },
    'network': {
        'Network':      None,
        'Network_WiFi': None,
        'OS':           ['hostname', 'os', 'distro'],
    },
}

REPORT_TITLES = {
    'full':      'Full Hardware Specification',
    'executive': 'Executive Summary',
    'gpu':       'GPU & Compute Report',
    'storage':   'Storage Audit',
    'network':   'Network Inventory',
}

# ── DHG Brand ─────────────────────────────────────────────────────────────────
DHG_BRAND = {
    'graphite':    '#32374A',
    'purple':      '#663399',
    'orange':      '#F77E2D',
    'base':        '#FAF7F2',
    'surface':     '#F4F0E8',
    'card':        '#EDE8DC',
    'border':      '#DDD5C4',
    'border2':     '#CCC2AE',
    'text':        '#2E2C26',
    'text_muted':  '#4A4236',
    'text_faint':  '#6B6456',
}

# ── Data loading ──────────────────────────────────────────────────────────────
def load_csv(path):
    rows = []
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows

def filter_rows(rows, report_type):
    filters = REPORT_FILTERS.get(report_type)
    if filters is None:
        return rows
    result = []
    for row in rows:
        cat = row.get('category', '')
        if cat not in filters:
            continue
        key_filter = filters[cat]
        if key_filter is None:
            result.append(row)
        elif row.get('key', '') in key_filter:
            result.append(row)
    return result

def group_by_category(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row['category']].append(row)
    return dict(groups)

def extract_hostname(rows):
    for row in rows:
        if row.get('category') == 'OS' and row.get('key') == 'hostname':
            return row.get('value', 'unknown')
    return 'unknown'

def extract_meta(rows):
    meta = {}
    for row in rows:
        if row.get('category') == 'OS':
            meta[row.get('key')] = row.get('value')
    return meta

# ── HTML renderer ─────────────────────────────────────────────────────────────
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{report_title} — {hostname}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --graphite: {graphite};
    --purple:   {purple};
    --orange:   {orange};
    --base:     {base};
    --surface:  {surface};
    --card:     {card};
    --border:   {border};
    --border2:  {border2};
    --text:     {text};
    --muted:    {text_muted};
    --faint:    {text_faint};
  }}

  html {{ font-size: 15px; }}
  body {{
    font-family: 'IBM Plex Sans', system-ui, sans-serif;
    background: var(--base);
    color: var(--text);
    line-height: 1.6;
    padding: 0;
  }}

  /* ── Header ── */
  .site-header {{
    background: var(--graphite);
    color: #fff;
    padding: 1.5rem 2.5rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 3px solid var(--orange);
  }}
  .site-header .brand {{ display: flex; align-items: center; gap: 0.75rem; }}
  .site-header .brand-dot {{
    width: 10px; height: 10px; border-radius: 50%;
    background: var(--orange); flex-shrink: 0;
  }}
  .site-header h1 {{ font-size: 1.1rem; font-weight: 600; letter-spacing: 0.02em; }}
  .site-header .meta {{ font-size: 0.78rem; opacity: 0.65; text-align: right; line-height: 1.4; }}

  /* ── Report title bar ── */
  .report-title-bar {{
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 1.25rem 2.5rem;
    display: flex;
    align-items: baseline;
    gap: 1rem;
  }}
  .report-title-bar h2 {{
    font-size: 1.4rem; font-weight: 600;
    color: var(--graphite);
  }}
  .report-badge {{
    background: var(--purple);
    color: #fff;
    font-size: 0.7rem;
    font-weight: 600;
    padding: 0.2rem 0.6rem;
    border-radius: 3px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }}
  .hostname-badge {{
    margin-left: auto;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.8rem;
    color: var(--muted);
    background: var(--card);
    border: 1px solid var(--border);
    padding: 0.2rem 0.6rem;
    border-radius: 3px;
  }}

  /* ── Layout ── */
  .content {{ max-width: 1200px; margin: 0 auto; padding: 2rem 2.5rem 4rem; }}

  /* ── Category sections ── */
  .category-section {{
    margin-bottom: 2rem;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 6px;
    overflow: hidden;
  }}
  .category-header {{
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 0.65rem 1.25rem;
    display: flex;
    align-items: center;
    gap: 0.6rem;
  }}
  .category-header h3 {{
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--purple);
  }}
  .category-header .row-count {{
    margin-left: auto;
    font-size: 0.7rem;
    color: var(--faint);
    font-family: 'IBM Plex Mono', monospace;
  }}
  .category-accent {{
    width: 3px; height: 14px; border-radius: 2px;
    background: var(--orange); flex-shrink: 0;
  }}

  /* ── Table ── */
  .spec-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.83rem;
  }}
  .spec-table th {{
    text-align: left;
    padding: 0.5rem 1.25rem;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--faint);
    background: var(--surface);
    border-bottom: 1px solid var(--border2);
  }}
  .spec-table td {{
    padding: 0.45rem 1.25rem;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }}
  .spec-table tr:last-child td {{ border-bottom: none; }}
  .spec-table tr:hover td {{ background: rgba(102,51,153,0.04); }}

  .key-cell {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    color: var(--graphite);
    white-space: nowrap;
    width: 30%;
    min-width: 180px;
  }}
  .value-cell {{
    color: var(--text);
    word-break: break-word;
    max-width: 500px;
  }}
  .value-cell.long {{ font-size: 0.72rem; color: var(--muted); }}
  .unit-cell {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    color: var(--faint);
    white-space: nowrap;
    text-align: right;
    padding-right: 0.5rem;
  }}
  .source-cell {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    color: var(--faint);
    white-space: nowrap;
    text-align: right;
  }}

  /* ── Value highlights ── */
  .val-gpu    {{ color: var(--purple); font-weight: 500; }}
  .val-warn   {{ color: var(--orange); font-weight: 500; }}
  .val-good   {{ color: #2a7a3b; font-weight: 500; }}

  /* ── Footer ── */
  .report-footer {{
    margin-top: 3rem;
    padding-top: 1.5rem;
    border-top: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.72rem;
    color: var(--faint);
  }}
  .footer-brand {{ font-weight: 600; color: var(--purple); }}

  /* ── Summary cards (executive) ── */
  .summary-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
  }}
  .summary-card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 1rem 1.25rem;
    border-left: 3px solid var(--purple);
  }}
  .summary-card .label {{
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--faint);
    margin-bottom: 0.3rem;
  }}
  .summary-card .val {{
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--graphite);
    font-family: 'IBM Plex Mono', monospace;
  }}
  .summary-card .sub {{
    font-size: 0.72rem;
    color: var(--muted);
    margin-top: 0.15rem;
  }}
</style>
</head>
<body>

<header class="site-header">
  <div class="brand">
    <div class="brand-dot"></div>
    <h1>Digital Harmony Group &mdash; DHG Labs</h1>
  </div>
  <div class="meta">
    Generated {generated_at}<br>
    dhg-hw-spec-collector v1.0
  </div>
</header>

<div class="report-title-bar">
  <h2>{report_title}</h2>
  <span class="report-badge">{report_type}</span>
  <span class="hostname-badge">{hostname}</span>
</div>

<div class="content">
{summary_cards}
{sections}
  <div class="report-footer">
    <span><span class="footer-brand">DHG Labs</span> &mdash; Digital Harmony Group</span>
    <span>{total_rows} data points &bull; Source: hw_specs_{hostname}_{timestamp}.csv</span>
  </div>
</div>

</body>
</html>'''

def build_summary_cards(rows, report_type):
    """Build summary stat cards for executive/gpu reports."""
    if report_type not in ('executive', 'gpu'):
        return ''

    kv = {}
    for row in rows:
        kv[f"{row['category']}.{row['key']}"] = row.get('value', '')

    cards = []

    def card(label, val, sub=''):
        return (f'<div class="summary-card">'
                f'<div class="label">{label}</div>'
                f'<div class="val">{val}</div>'
                f'{"<div class=sub>" + sub + "</div>" if sub else ""}'
                f'</div>')

    if report_type == 'executive':
        cpu   = kv.get('CPU.model', kv.get('CPU_HW.chip_type', '—'))
        cores = kv.get('CPU.physical_cores', '—')
        ram   = kv.get('RAM.total', '—')
        gpu   = (kv.get('GPU_NVIDIA.gpu0_name') or
                 kv.get('GPU.gpu0_name') or
                 kv.get('GPU_AMD.GPU[0]_Card series', '—'))
        vram  = kv.get('GPU_NVIDIA.gpu0_memory.total', kv.get('GPU.gpu0_vram', '—'))
        os_   = kv.get('OS.distro', kv.get('OS.os', '—'))

        cards = [
            card('CPU', cpu[:28] + ('…' if len(cpu) > 28 else ''),
                 f'{cores} physical cores'),
            card('RAM', f'{ram} GB'),
            card('GPU', gpu[:28] + ('…' if len(gpu) > 28 else ''),
                 f'{vram} MiB VRAM' if vram != '—' else ''),
            card('OS', os_[:28] + ('…' if len(os_) > 28 else '')),
        ]

    elif report_type == 'gpu':
        nvidia = kv.get('GPU_NVIDIA.gpu0_name', '')
        amd    = kv.get('GPU_AMD.GPU[0]_Card series', kv.get('GPU.gpu0_name', ''))
        nvram  = kv.get('GPU_NVIDIA.gpu0_memory.total', '—')
        nvtemp = kv.get('GPU_NVIDIA.gpu0_temperature.gpu', '—')
        nvutil = kv.get('GPU_NVIDIA.gpu0_utilization.gpu', '—')
        amdtemp = kv.get('GPU_AMD.GPU[0]_Temperature (Sensor edge) (C)', '—')

        if nvidia:
            cards.append(card('NVIDIA GPU', nvidia[:28] + ('…' if len(nvidia)>28 else ''),
                               f'VRAM: {nvram} MiB'))
            cards.append(card('NVIDIA Temp', f'{nvtemp}°C', f'Utilization: {nvutil}%'))
        if amd:
            cards.append(card('AMD GPU', amd[:28] + ('…' if len(amd)>28 else ''),
                               f'Temp: {amdtemp}°C' if amdtemp != '—' else ''))

    if not cards:
        return ''
    return '<div class="summary-grid">' + ''.join(cards) + '</div>\n'


def value_class(key, value):
    """Apply highlight classes to notable values."""
    key_l = key.lower()
    if any(x in key_l for x in ('name', 'model')) and any(
            x in value.lower() for x in ('nvidia', 'rtx', 'geforce', 'quadro')):
        return 'val-gpu'
    if any(x in key_l for x in ('name', 'model')) and any(
            x in value.lower() for x in ('amd', 'radeon', 'rx ')):
        return 'val-gpu'
    if 'temperature' in key_l or 'temp' in key_l:
        try:
            t = float(value.replace('°C', '').strip())
            return 'val-warn' if t > 80 else 'val-good' if t < 60 else ''
        except Exception:
            pass
    if 'percent' in key_l or 'usage' in key_l:
        try:
            p = float(value.replace('%', '').strip())
            return 'val-warn' if p > 85 else ''
        except Exception:
            pass
    return 'long' if len(value) > 80 else ''


def render_html(rows, report_type, csv_path):
    hostname  = extract_hostname(rows)
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ts_file   = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filtered  = filter_rows(rows, report_type)
    groups    = group_by_category(filtered)

    summary_cards = build_summary_cards(filtered, report_type)

    sections_html = ''
    for cat, cat_rows in groups.items():
        rows_html = ''
        for row in cat_rows:
            vc = value_class(row['key'], row['value'])
            val_td = f'<td class="value-cell {vc}">{row["value"]}</td>'
            rows_html += (
                f'<tr>'
                f'<td class="key-cell">{row["key"]}</td>'
                f'{val_td}'
                f'<td class="unit-cell">{row.get("unit","")}</td>'
                f'<td class="source-cell">{row.get("source","")}</td>'
                f'</tr>\n'
            )
        sections_html += f'''
  <div class="category-section">
    <div class="category-header">
      <div class="category-accent"></div>
      <h3>{cat}</h3>
      <span class="row-count">{len(cat_rows)} rows</span>
    </div>
    <table class="spec-table">
      <thead>
        <tr>
          <th>Key</th><th>Value</th><th>Unit</th><th>Source</th>
        </tr>
      </thead>
      <tbody>
{rows_html}      </tbody>
    </table>
  </div>
'''

    return HTML_TEMPLATE.format(
        report_title=REPORT_TITLES[report_type],
        report_type=report_type.upper(),
        hostname=hostname,
        generated_at=timestamp,
        timestamp=ts_file,
        summary_cards=summary_cards,
        sections=sections_html,
        total_rows=len(filtered),
        **DHG_BRAND,
    )


# ── Markdown renderer ─────────────────────────────────────────────────────────
def render_markdown(rows, report_type, csv_path):
    hostname  = extract_hostname(rows)
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    filtered  = filter_rows(rows, report_type)
    groups    = group_by_category(filtered)
    csv_name  = Path(csv_path).name

    lines = [
        f'# {REPORT_TITLES[report_type]}',
        f'',
        f'**Host:** `{hostname}`  ',
        f'**Report type:** `{report_type}`  ',
        f'**Generated:** {timestamp}  ',
        f'**Source:** `{csv_name}`  ',
        f'**Total data points:** {len(filtered)}',
        f'',
        f'---',
        f'',
    ]

    for cat, cat_rows in groups.items():
        lines.append(f'## {cat}')
        lines.append(f'')
        lines.append(f'| Key | Value | Unit | Source |')
        lines.append(f'|-----|-------|------|--------|')
        for row in cat_rows:
            key   = row.get('key', '').replace('|', '\\|')
            value = row.get('value', '').replace('|', '\\|')
            unit  = row.get('unit', '').replace('|', '\\|')
            src   = row.get('source', '').replace('|', '\\|')
            # Truncate very long values in markdown
            if len(value) > 120:
                value = value[:117] + '…'
            lines.append(f'| `{key}` | {value} | {unit} | `{src}` |')
        lines.append('')

    lines += [
        '---',
        '',
        '*Generated by [dhg-hw-spec-collector](https://github.com/sdnydude/dhg-hw-spec-collector) '
        '— DHG Labs / Digital Harmony Group*',
    ]

    return '\n'.join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description='DHG Hardware Spec Report Generator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('csv', help='Path to hw_specs_*.csv')
    parser.add_argument('--type', '-t',
                        choices=['full', 'executive', 'gpu', 'storage', 'network'],
                        default='full',
                        help='Report type (default: full)')
    parser.add_argument('--format', '-f',
                        choices=['html', 'markdown'],
                        default='html',
                        help='Output format (default: html)')
    parser.add_argument('--out', '-o',
                        default=None,
                        help='Output directory (default: same dir as CSV)')
    parser.add_argument('--all', '-a',
                        action='store_true',
                        help='Generate all report types in both formats')
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f'[ERROR] CSV not found: {args.csv}')
        sys.exit(1)

    rows = load_csv(args.csv)
    hostname  = extract_hostname(rows)
    ts        = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir   = args.out or os.path.dirname(os.path.abspath(args.csv))
    os.makedirs(out_dir, exist_ok=True)

    combos = (
        [(t, f) for t in REPORT_FILTERS for f in ['html', 'markdown']]
        if args.all
        else [(args.type, args.format)]
    )

    generated = []
    for rtype, rfmt in combos:
        if rfmt == 'html':
            content = render_html(rows, rtype, args.csv)
            ext = 'html'
        else:
            content = render_markdown(rows, rtype, args.csv)
            ext = 'md'

        fname = f'report_{rtype}_{hostname}_{ts}.{ext}'
        fpath = os.path.join(out_dir, fname)
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(content)

        generated.append(fpath)
        print(f'[DHG REPORT] {rtype:12s} {rfmt:8s} → {fpath}')

    print(f'\n[DHG REPORT] Done. {len(generated)} report(s) written.')
    return generated

if __name__ == '__main__':
    main()
