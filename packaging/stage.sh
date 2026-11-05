#!/bin/sh
# Zet de PixelPickle bestanden in een systeemboom onder $1 (gedeeld door Arch, Debian en Fedora).
# Gebruik: packaging/stage.sh <doelmap>     (uitvoeren vanuit de hoofdmap van de broncode)
set -e
DEST="$1"
[ -n "$DEST" ] || { echo "gebruik: $0 <doelmap>" >&2; exit 1; }
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
