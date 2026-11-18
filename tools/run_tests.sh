#!/bin/sh
# Draait alle tests uit tests/ (zonder scherm) en geeft een overzicht. Stopt niet bij de eerste fout.
# Gebruik: tools/run_tests.sh [python]      (standaard: .venv/bin/python als die er is, anders python3)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${1:-}"
[ -n "$PY" ] || { [ -x "$ROOT/.venv/bin/python" ] && PY="$ROOT/.venv/bin/python" || PY=python3; }
export QT_QPA_PLATFORM=offscreen
LOG=$(mktemp -d)
failed=""
n=0
for t in "$ROOT"/tests/test_*.py "$ROOT"/tests/smoke.py; do
    name=$(basename "$t")
    n=$((n + 1))
    start=$(date +%s)
    if timeout 900 "$PY" -I "$t" > "$LOG/$name.log" 2>&1; then
        echo "ok    $name ($(( $(date +%s) - start ))s)"
    else
        echo "FOUT  $name ($(( $(date +%s) - start ))s)"
        failed="$failed $name"
        tail -25 "$LOG/$name.log" | sed 's/^/      /'
    fi
done
if [ -n "$failed" ]; then
    echo "Mislukt:$failed (van $n)"
    exit 1
fi
echo "Alle $n tests geslaagd"
