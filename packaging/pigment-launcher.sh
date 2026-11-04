#!/bin/sh
# Start Pigment (geïnstalleerd via pacman)
exec /usr/bin/python3 -c "import sys; sys.path.insert(0, '/usr/share/pigment'); from pigment.__main__ import main; main()" "$@"
