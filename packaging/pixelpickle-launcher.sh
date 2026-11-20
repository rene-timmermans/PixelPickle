#!/bin/sh
# Start PixelPickle (installed via pacman)
exec /usr/bin/python3 -c "import sys; sys.path.insert(0, '/usr/share/pixelpickle'); from pixelpickle.__main__ import main; main()" "$@"
