#!/bin/bash
# DHG HW Spec Collector — Docker Entrypoint
# Runs the collector, writes CSV to /output, then exits.
set -e

echo "========================================"
echo " DHG Hardware Spec Collector"
echo " Digital Harmony Group — DHG Labs"
echo "========================================"
echo ""

# Run the collector from /output so the CSV lands there
cd /output
python3 /app/scripts/collect_linux.py

echo ""
echo "CSV written to /output:"
ls -lh /output/*.csv 2>/dev/null || echo "(no CSV found — check for errors above)"
