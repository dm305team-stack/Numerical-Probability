#!/bin/bash
# Build NumericalProbability.app from SPM output — no Xcode required.
# Usage: Scripts/bundle.sh [debug|release] [--run]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="NumericalProbability"
CONFIG="${1:-release}"

echo "==> swift build -c $CONFIG"
swift build -c "$CONFIG" --package-path "$ROOT"

BIN_DIR="$(swift build -c "$CONFIG" --package-path "$ROOT" --show-bin-path)"
APP="$ROOT/dist/$APP_NAME.app"

echo "==> Assembling $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cp "$BIN_DIR/$APP_NAME" "$APP/Contents/MacOS/$APP_NAME"

# SPM resource bundle (only exists if the target declares resources:).
SPM_BUNDLE="$BIN_DIR/${APP_NAME}_${APP_NAME}.bundle"
if [ -d "$SPM_BUNDLE" ]; then
    cp -R "$SPM_BUNDLE" "$APP/Contents/Resources/"
fi

cp "$ROOT/Support/Info.plist" "$APP/Contents/Info.plist"
printf 'APPL????' > "$APP/Contents/PkgInfo"

if [ -f "$ROOT/Support/AppIcon.icns" ]; then
    cp "$ROOT/Support/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
fi

echo "==> Ad-hoc signing"
# Sign the bundle directly; the main executable is the only Mach-O (--deep is deprecated).
codesign --force --sign - "$APP"
codesign --verify --verbose=2 "$APP"

echo "==> Done: $APP"
if [ "${2:-}" = "--run" ]; then
    pkill -x "$APP_NAME" || true
    open "$APP"
fi
