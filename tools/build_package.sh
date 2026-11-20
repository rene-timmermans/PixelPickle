#!/bin/sh
# Builds the Arch package locally: dist/pixelpickle-<version>-1-any.pkg.tar.zst
# (Debian and Fedora packages are built by GitHub Actions on every release; see .github/workflows/release.yml)
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARBALL=$("$ROOT/tools/make_source_tarball.sh")
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cp "$TARBALL" "$ROOT/packaging/PKGBUILD" "$WORK/"
VER=$(basename "$TARBALL" .tar.gz | sed 's/^pixelpickle-//')
sed -i "s/^pkgver=.*/pkgver=$VER/" "$WORK/PKGBUILD"
cd "$WORK" && makepkg -f --nodeps --noconfirm >/dev/null
cp "$WORK"/pixelpickle-*.pkg.tar.zst "$ROOT/dist/"
ls -la "$ROOT"/dist/*.pkg.tar.zst
