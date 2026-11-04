#!/bin/sh
# Bouwt dist/pigment-<versie>-1-any.pkg.tar.zst (pacman pakket). Gebruik: tools/build_package.sh
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VER=$(sed -n 's/^pkgver=//p' "$ROOT/packaging/PKGBUILD")
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/pigment-$VER/icons" "$ROOT/dist"
cp -r "$ROOT/pigment" "$ROOT/packaging" "$ROOT/README.md" "$WORK/pigment-$VER/"
QT_QPA_PLATFORM=offscreen "$ROOT/.venv/bin/python" -I "$ROOT/packaging/make_icon.py" "$WORK/pigment-$VER/icons"
tar -C "$WORK" --exclude='__pycache__' -czf "$WORK/pigment-$VER.tar.gz" "pigment-$VER"
cp "$ROOT/packaging/PKGBUILD" "$WORK/"
cd "$WORK" && makepkg -f --nodeps --noconfirm >/dev/null
cp "$WORK"/pigment-*.pkg.tar.zst "$ROOT/dist/"
ls -la "$ROOT/dist/"
