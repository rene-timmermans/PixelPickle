#!/bin/sh
# Start PixelPickle vanuit de broncode (met de Python uit .venv als die er is, anders python3)
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$DIR/.venv/bin/python"
[ -x "$PY" ] || PY=python3
PYTHONPATH="$DIR${PYTHONPATH:+:$PYTHONPATH}" exec "$PY" -m pixelpickle "$@"
