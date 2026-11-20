#!/bin/sh
# Start PixelPickle from the source code (with the Python from .venv if present, otherwise python3)
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$DIR/.venv/bin/python"
[ -x "$PY" ] || PY=python3
PYTHONPATH="$DIR${PYTHONPATH:+:$PYTHONPATH}" exec "$PY" -m pixelpickle "$@"
