#!/usr/bin/env bash
# Linux counterpart of overnight.bat — see DEBIAN_SYNC_2026-07-20.md.
# Run inside the cszero conda env:  conda activate cszero && scripts/overnight.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if { command -v ss >/dev/null && ss -ltn | grep -q ':8000 '; } \
   || { command -v netstat >/dev/null && netstat -ltn 2>/dev/null | grep -q ':8000 '; }; then
    echo "A backend is already listening on port 8000. Stop it first" \
         "(it may be running old code), then rerun this script."
    exit 1
fi

mkdir -p data/training

echo "Starting backend (log: data/training/backend_overnight.log)..."
nohup python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 \
    > data/training/backend_overnight.log 2>&1 &
echo $! > data/training/backend_overnight.pid
echo "Backend PID $(cat data/training/backend_overnight.pid)"

echo "Starting overnight runner (log: data/training/overnight_run.log)..."
echo "Report will land at data/training/overnight_report.md"
python scripts/overnight_run.py --games 693
