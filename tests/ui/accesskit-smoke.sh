#!/usr/bin/env bash
# Real AT-SPI discovery and actions on isolated X11/D-Bus surfaces only.
set -euo pipefail
cd "$(dirname "$0")/../.."
app="${A10_APP_WINDOW_BINARY:-${CARGO_TARGET_DIR:-ui/target}/debug/trill-app-window}"
test -x "$app"
app="$(realpath "$app")"
exec dbus-run-session -- xvfb-run -a -s '-screen 0 1280x800x24 -nolisten tcp' \
  python3 tests/ui/accesskit-smoke.py --app-window "$app"
