#!/bin/sh
# Start Brushwork (geïnstalleerd via pacman)
exec /usr/bin/python3 -c "import sys; sys.path.insert(0, '/usr/share/brushwork'); from brushwork.__main__ import main; main()" "$@"
