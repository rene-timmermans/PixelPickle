#!/bin/sh
# Maakt dist/pixelpickle-<versie>.tar.gz met alles wat de pakketten nodig hebben.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VER=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/pixelpickle/__init__.py")
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/pixelpickle-$VER" "$ROOT/dist"
cp -r "$ROOT/pixelpickle" "$ROOT/packaging" "$ROOT/README.md" "$ROOT/LICENSE" "$WORK/pixelpickle-$VER/"
tar -C "$WORK" --exclude='__pycache__' -czf "$ROOT/dist/pixelpickle-$VER.tar.gz" "pixelpickle-$VER"
echo "$ROOT/dist/pixelpickle-$VER.tar.gz"
