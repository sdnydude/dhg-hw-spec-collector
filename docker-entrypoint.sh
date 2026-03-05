#!/bin/bash
# DHG HW Spec Collector — Docker Entrypoint
#
# Environment variables:
#   REPORT_TYPE    full | executive | gpu | storage | network | all  (default: full)
#   REPORT_FORMAT  html | markdown | both                             (default: html)
#   SKIP_REPORT    1 = collect only, skip report generation          (default: 0)
#
# Examples:
#   docker run ... -e REPORT_TYPE=gpu -e REPORT_FORMAT=html dhg-hw-spec-collector
#   docker run ... -e REPORT_TYPE=all dhg-hw-spec-collector

set -e

echo "========================================"
echo " DHG Hardware Spec Collector"
echo " Digital Harmony Group — DHG Labs"
echo "========================================"
echo ""

# Step 1: Collect hardware data
echo "[1/2] Collecting hardware specs..."
cd /output
python3 /app/scripts/collect_linux.py

# Find the CSV just written
CSV_FILE=$(ls -t /output/hw_specs_*.csv 2>/dev/null | head -1)
if [ -z "$CSV_FILE" ]; then
  echo "[ERROR] No CSV produced — check collector output above."
  exit 1
fi
echo "      CSV: $CSV_FILE"
echo ""

# Step 2: Generate reports (unless SKIP_REPORT=1)
if [ "${SKIP_REPORT}" = "1" ]; then
  echo "[2/2] Skipping report generation (SKIP_REPORT=1)"
else
  echo "[2/2] Generating reports..."
  RTYPE="${REPORT_TYPE:-full}"
  RFMT="${REPORT_FORMAT:-html}"

  if [ "$RFMT" = "both" ]; then
    python3 /app/reports/generate_report.py "$CSV_FILE" --type "$RTYPE" --format html    --out /output
    python3 /app/reports/generate_report.py "$CSV_FILE" --type "$RTYPE" --format markdown --out /output
  elif [ "$RTYPE" = "all" ]; then
    python3 /app/reports/generate_report.py "$CSV_FILE" --all --out /output
  else
    python3 /app/reports/generate_report.py "$CSV_FILE" --type "$RTYPE" --format "$RFMT" --out /output
  fi
fi

echo ""
echo "========================================"
echo " Output files in /output:"
ls -lh /output/ 2>/dev/null
echo "========================================"
