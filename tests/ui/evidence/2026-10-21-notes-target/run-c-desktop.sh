#!/usr/bin/env bash
set -euo pipefail
umask 077
c_root="$(pwd -P)"
test -f "$c_root/SOURCE_HEAD.txt"
test -f "$c_root/ui/Cargo.toml"
mkdir -p "$c_root/evidence"
export CARGO_BUILD_JOBS=4 CARGO_INCREMENTAL=0
export CARGO_TARGET_DIR="$c_root/target"
export PYTHONOPTIMIZE=0 PYTHONDONTWRITEBYTECODE=1
unset DISPLAY WAYLAND_DISPLAY
{
  cat SOURCE_HEAD.txt
  cargo +1.95.0 --version
  rustc +1.95.0 --version
  uname -srmo
} > evidence/environment.txt
# Only C-owned workspace packages are formatted. Preserve the actual tested
# source for transfer back; formatting is not asserted to be an original-HEAD run.
nice -n 10 cargo +1.95.0 fmt --manifest-path ui/Cargo.toml \
  -p trill-ui-core -p trill-ui-broker -p trill-session -p trill-app-window -p trill-shell
nice -n 10 cargo +1.95.0 test --manifest-path ui/Cargo.toml \
  -p trill-ui-core -p trill-ui-broker 2>&1 | tee evidence/core-broker-test.log
cp ui/Cargo.lock evidence/Cargo.lock.updated
nice -n 10 cargo +1.95.0 test --manifest-path ui/Cargo.toml \
  --workspace --all-targets --locked 2>&1 | tee evidence/ui-workspace-test.log
nice -n 10 cargo +1.95.0 build --manifest-path ui/Cargo.toml \
  --workspace --bins --locked 2>&1 | tee evidence/ui-build.log
nice -n 10 cargo +1.95.0 build --manifest-path ui/Cargo.toml \
  -p trill-ui-broker --example notes_host_probe --locked 2>&1 | tee evidence/notes-probe-build.log
python3 tests/ui/test-strict-request-ipc.py "$CARGO_TARGET_DIR/debug" \
  2>&1 | tee evidence/strict-session-ipc.log
nice -n 10 cargo +1.95.0 fmt --manifest-path ui/Cargo.toml \
  -p trill-ui-core -p trill-ui-broker -p trill-session -p trill-app-window -p trill-shell -- --check
tar -czf evidence/ui-built-source.tgz ui
sha256sum evidence/ui-built-source.tgz > evidence/ui-built-source.tgz.sha256
python3 - <<'PY'
import hashlib,json
from pathlib import Path
prior=json.loads(Path('SOURCE_FILES_SHA256.json').read_text())
actual={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in prior if Path(p).is_file()}
Path('evidence/tested-source-sha256.json').write_text(json.dumps(actual,sort_keys=True,indent=2)+'\n')
changed=[p for p in prior if actual.get(p)!=prior[p]]
print(json.dumps({'source_head':Path('SOURCE_HEAD.txt').read_text().strip(),'modified_by_format_or_lock':changed,'rust_toolchain':'1.95.0','gui_run':False,'hepta_production_run':False}))
PY
