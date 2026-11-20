#!/bin/sh
# Put the PixelPickle files in a system tree under $1 (shared by Arch, Debian and Fedora).
# Usage: packaging/stage.sh <target folder>     (run from the root of the source tree)
set -e
DEST="$1"
[ -n "$DEST" ] || { echo "usage: $0 <target dir>" >&2; exit 1; }
install -d "$DEST/usr/share/pixelpickle"
cp -r pixelpickle "$DEST/usr/share/pixelpickle/"
find "$DEST/usr/share/pixelpickle" -name '__pycache__' -prune -exec rm -rf {} +
install -Dm755 packaging/pixelpickle-launcher.sh "$DEST/usr/bin/pixelpickle"
install -Dm644 packaging/pixelpickle.desktop "$DEST/usr/share/applications/pixelpickle.desktop"
for s in 16 32 48 64 128 256; do
    install -Dm644 "pixelpickle/data/icons/pixelpickle-$s.png" "$DEST/usr/share/icons/hicolor/${s}x${s}/apps/pixelpickle.png"
done
install -Dm644 README.md "$DEST/usr/share/doc/pixelpickle/README.md"
install -Dm644 LICENSE "$DEST/usr/share/licenses/pixelpickle/LICENSE"
