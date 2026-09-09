#!/usr/bin/env bash
# Build imgdoc_<version>_amd64.deb from the PyInstaller output in dist/.
set -euo pipefail

VERSION="${1:-1.0.0}"
ARCH="$(dpkg --print-architecture)"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$ROOT/build/deb"
PKG="imgdoc_${VERSION}_${ARCH}"

[ -x "$ROOT/dist/imgdoc" ] || { echo "dist/imgdoc missing — run PyInstaller first"; exit 1; }

rm -rf "$STAGE"
mkdir -p "$STAGE/$PKG"/{DEBIAN,opt/imgdoc,usr/bin,usr/share/applications,usr/share/doc/imgdoc}

cp "$ROOT/dist/imgdoc" "$STAGE/$PKG/opt/imgdoc/imgdoc"
chmod 755 "$STAGE/$PKG/opt/imgdoc/imgdoc"
ln -s /opt/imgdoc/imgdoc "$STAGE/$PKG/usr/bin/imgdoc"
cp "$ROOT/README.md" "$STAGE/$PKG/usr/share/doc/imgdoc/"
cp "$ROOT/LICENSE" "$STAGE/$PKG/usr/share/doc/imgdoc/copyright" 2>/dev/null || true

INSTALLED_KB=$(du -sk "$STAGE/$PKG/opt" | cut -f1)

cat > "$STAGE/$PKG/DEBIAN/control" <<CTRL
Package: imgdoc
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: tesseract-ocr, tesseract-ocr-eng
Recommends: wl-clipboard | xclip, libnotify-bin
Installed-Size: $INSTALLED_KB
Maintainer: Muddasir Naveed <muddasir.naveed@gmail.com>
Description: Offline image to LLM-ready Markdown or JSON
 Converts scans, photos and screenshots into clean structured text that a
 language model can read directly, cutting tokens and removing per-call
 variance. Runs entirely on the local machine with no network access.
 .
 Includes a desktop window, a command line interface, and a clipboard
 hotkey that replaces a copied image with Markdown in place.
CTRL

cat > "$STAGE/$PKG/usr/share/applications/imgdoc.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=imgdoc
Comment=Convert document images to LLM-ready Markdown or JSON
Exec=/opt/imgdoc/imgdoc
Icon=accessories-text-editor
Terminal=false
Categories=Utility;Office;
Keywords=OCR;Markdown;JSON;screenshot;
DESK

dpkg-deb --root-owner-group --build "$STAGE/$PKG" "$ROOT/dist/$PKG.deb"
echo "built: dist/$PKG.deb"
