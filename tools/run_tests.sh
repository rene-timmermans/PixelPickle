#!/bin/sh
# Runs all tests in tests/ (without a screen) and prints an overview. Does not stop at the first failure.
# Usage: tools/run_tests.sh [python]      (default: .venv/bin/python if present, otherwise python3)
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
        echo "FAIL  $name ($(( $(date +%s) - start ))s)"
        failed="$failed $name"
        tail -25 "$LOG/$name.log" | sed 's/^/      /'
    fi
done
if [ -n "$failed" ]; then
    echo "Failed:$failed (of $n)"
    exit 1
fi
echo "All $n tests passed"
