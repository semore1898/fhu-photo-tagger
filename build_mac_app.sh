#!/bin/bash
# Builds "FHU Photo Tagger.app" on a Mac.
# Run from the folder that holds photo_tagger.py:  bash build_mac_app.sh
#
# Before running, put ExifTool next to this script:
#   1. Download the "Image-ExifTool-XX.XX.tar.gz" file from https://exiftool.org
#   2. Double-click it to unpack it
#   3. Rename the unpacked folder to:  exiftool_bundle
#      (it should contain a file named "exiftool" and a folder named "lib")

set -e
HERE="$(cd "$(dirname "$0")" && pwd)"

if [ ! -f "$HERE/exiftool_bundle/exiftool" ] || [ ! -d "$HERE/exiftool_bundle/lib" ]; then
  echo "Missing exiftool_bundle/ (needs 'exiftool' and 'lib' inside)."
  echo "See the notes at the top of this script."
  exit 1
fi

if ! command -v python3 >/dev/null; then
  echo "Python 3 not found. Install it from python.org first."
  exit 1
fi

# Build in a temporary folder on the Mac's own disk (not Google Drive), and
# bundle ONLY the 'exiftool' program and its 'lib' folder. ExifTool's download
# also holds test files that confuse the packager.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cp "$HERE/photo_tagger.py" "$WORK/"
mkdir -p "$WORK/exiftool_bundle"
cp "$HERE/exiftool_bundle/exiftool" "$WORK/exiftool_bundle/"
cp -R "$HERE/exiftool_bundle/lib" "$WORK/exiftool_bundle/"
cd "$WORK"

python3 -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip pyinstaller pillow certifi

pyinstaller --noconfirm --clean --windowed \
  --name "FHU Photo Tagger" \
  --add-data "exiftool_bundle:exiftool_bundle" \
  photo_tagger.py

deactivate

mkdir -p "$HERE/dist"
rm -rf "$HERE/dist/FHU Photo Tagger.app"
cp -R "dist/FHU Photo Tagger.app" "$HERE/dist/"

echo
echo "Done. Your app is in:  $HERE/dist/FHU Photo Tagger.app"
echo "Drag it into Applications (or the Dock)."
