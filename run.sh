#!/usr/bin/env bash
# One-command run. Usage: bash run.sh [segment]
# If no segment given, runs all four. Assumes Swedish bulk files are in ./data/
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

SEG_ARGS=()
if [ $# -gt 0 ]; then
    SEG_ARGS=(--segment "$1")
fi

mkdir -p output data

se_ok=true
for f in data/scb_bulkfil.txt data/bolagsverket_bulkfil.txt; do
    if [ ! -f "$f" ]; then
        echo "WARNING: $f not found — Sweden will be skipped."
        echo "         Download from: https://bolagsverket.se/apierochoppnadata/nedladdningsbarafiler.2517.html"
        se_ok=false
    fi
done

echo "=== Norway ==="
python -m src.main --country NO "${SEG_ARGS[@]}" || true
echo "=== Finland ==="
python -m src.main --country FI "${SEG_ARGS[@]}" || true
if [ "$se_ok" = true ]; then
    echo "=== Sweden ==="
    python -m src.main --country SE "${SEG_ARGS[@]}" || true
fi
if [ -n "${CVR_USER:-}" ] && [ -n "${CVR_PASS:-}" ]; then
    echo "=== Denmark ==="
    python -m src.main --country DK "${SEG_ARGS[@]}" || true
else
    echo "DK skipped — CVR_USER / CVR_PASS not set in .env."
fi

echo
echo "=== Output ==="
ls -la output/ || true
echo
echo "Row counts:"
for f in output/*.csv; do
    [ -f "$f" ] || continue
    n=$(( $(wc -l < "$f") - 1 ))
    printf "  %-50s %6d rows\n" "$f" "$n"
done
