#!/usr/bin/env bash
# Permanent D1 qualification runner. It never mutates Git refs.
set -euo pipefail

step_identities() {
set -euo pipefail
tested_sha=$(git rev-parse HEAD)
tree_sha=$(git rev-parse 'HEAD^{tree}')
parent_line=$(git rev-list --parents -n 1 HEAD)
parent_count=$(awk '{print NF - 1}' <<<"$parent_line")
git fetch --no-tags origin main
case "$GITHUB_EVENT_NAME" in
  pull_request)
    [[ "$parent_count" -eq 2 ]] || {
      echo "pull-request qualification requires an exact two-parent merge object" >&2
      exit 1
    }
    base_sha=$(git rev-parse HEAD^1)
    candidate_head_sha=$(git rev-parse HEAD^2)
    current_main=$(git rev-parse origin/main)
    [[ "$base_sha" == "$current_main" ]] || {
      echo "tested pull-request base is not the current main object" >&2
      exit 1
    }
    [[ -n "${EXPECTED_PR_HEAD:-}" && "$candidate_head_sha" == "$EXPECTED_PR_HEAD" ]] || {
      echo "tested second parent does not equal the exact pull-request head" >&2
      exit 1
    }
    topology=pr_merge_commit
    evidence_role=pr_synthetic_merge
    promotion_authoritative=false
    ;;
  push)
    [[ "$GITHUB_REF" == refs/heads/main ]] || {
      echo "D1 push qualification is authoritative only on refs/heads/main" >&2
      exit 1
    }
    [[ "$parent_count" -ge 1 ]] || {
      echo "exact-main qualification requires a parent commit" >&2
      exit 1
    }
    base_sha=$(git rev-parse HEAD^1)
    candidate_head_sha=$tested_sha
    topology=exact_push_commit
    evidence_role=exact_main_push
    promotion_authoritative=true
    ;;
  workflow_dispatch)
    [[ "$parent_count" -ge 1 ]] || {
      echo "manual qualification requires a parent commit" >&2
      exit 1
    }
    base_sha=$(git rev-parse HEAD^1)
    candidate_head_sha=$tested_sha
    topology=manual_checkout
    evidence_role=manual_non_authoritative
    promotion_authoritative=false
    ;;
  *)
    echo "unsupported D1 qualification event: $GITHUB_EVENT_NAME" >&2
    exit 1
    ;;
esac
{
  printf 'TESTED_SHA=%s\n' "$tested_sha"
  printf 'TESTED_TREE_SHA=%s\n' "$tree_sha"
  printf 'BASE_SHA=%s\n' "$base_sha"
  printf 'CANDIDATE_HEAD_SHA=%s\n' "$candidate_head_sha"
  printf 'TESTED_TOPOLOGY=%s\n' "$topology"
  printf 'SOURCE_REF=%s\n' "$GITHUB_REF"
  printf 'SOURCE_REF_NAME=%s\n' "$GITHUB_REF_NAME"
  printf 'EVIDENCE_ROLE=%s\n' "$evidence_role"
  printf 'PROMOTION_AUTHORITATIVE=%s\n' "$promotion_authoritative"
} >> "$GITHUB_ENV"
printf 'role=%s\nauthoritative=%s\nref=%s\ntopology=%s\nbase=%s\ncandidate=%s\ntested=%s\ntree=%s\n' \
  "$evidence_role" "$promotion_authoritative" "$GITHUB_REF" "$topology" \
  "$base_sha" "$candidate_head_sha" "$tested_sha" "$tree_sha"
}

step_install_deps() {
set -euo pipefail
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  build-essential \
  curl \
  debian-archive-keyring \
  e2fsprogs \
  gettext \
  git \
  gnupg \
  jq \
  mmdebstrap \
  qemu-system-x86 \
  rsync \
  shellcheck \
  systemd
sudo rm -rf /var/lib/apt/lists/*
mkdir -p /tmp/trillionnium-d1/evidence
python3 - <<'PY'
from pathlib import Path
import hashlib
import json
import os
import platform
import shutil
import subprocess

commands = [
    'apt-get', 'chroot', 'cpio', 'dpkg', 'dpkg-query', 'gzip', 'locale',
    'mmdebstrap', 'qemu-system-x86_64', 'rsync', 'sha256sum',
    'systemd-sysusers', 'systemd-tmpfiles', 'tar', 'touch',
]

def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()

binaries = {}
for command in commands:
    resolved = shutil.which(command)
    if resolved is None:
        raise SystemExit(f'missing image-producing host command: {command}')
    path = Path(resolved).resolve()
    binaries[command] = {
        'path': str(path),
        'sha256': digest(path),
        'bytes': path.stat().st_size,
    }
packages = subprocess.check_output(
    ['dpkg-query', '-W', '-f=${binary:Package}\t${Version}\n'], text=True
).splitlines()
packages = sorted(line for line in packages if line.strip())
canonical_packages = ('\n'.join(packages) + '\n').encode()
os_release = {}
for line in Path('/etc/os-release').read_text(encoding='utf-8').splitlines():
    if '=' in line:
        key, value = line.split('=', 1)
        os_release[key] = value.strip('"')
record = {
    'schema': 'trillionnium.desktop.d1-host-toolchain.v1',
    'runner': {
        'os': os.environ.get('RUNNER_OS'),
        'arch': os.environ.get('RUNNER_ARCH'),
        'environment': os.environ.get('RUNNER_ENVIRONMENT'),
        'image_os': os.environ.get('ImageOS'),
        'image_version': os.environ.get('ImageVersion'),
        'python': platform.python_version(),
        'kernel': platform.release(),
        'machine': platform.machine(),
    },
    'os_release': os_release,
    'installed_package_count': len(packages),
    'installed_packages_sha256': hashlib.sha256(canonical_packages).hexdigest(),
    'installed_packages': packages,
    'binaries': binaries,
}
Path('/tmp/trillionnium-d1/evidence/host-toolchain.json').write_text(
    json.dumps(record, indent=2, sort_keys=True) + '\n', encoding='utf-8'
)
PY
}

step_install_rust() {
set -euo pipefail
channel="$(python3 - <<'PY'
from pathlib import Path
import tomllib
print(tomllib.loads(Path('rust-toolchain.toml').read_text())['toolchain']['channel'])
PY
)"
components="$(python3 - <<'PY'
from pathlib import Path
import tomllib
print(' '.join(tomllib.loads(Path('rust-toolchain.toml').read_text())['toolchain']['components']))
PY
)"
printf 'RUST_CHANNEL=%s\n' "$channel" >> "$GITHUB_ENV"
rustup toolchain install "$channel" --profile minimal
for component in $components; do
  rustup component add "$component" --toolchain "$channel"
done
export RUSTUP_TOOLCHAIN="$channel"
rustc --version --verbose
cargo --version --verbose
}

step_build_e2fsprogs() {
set -euo pipefail
tool_dir=$(bash tools/build_pinned_e2fsprogs.sh \
  --manifest manifests/e2fsprogs-host-toolchain.v1.json \
  --work-dir "$RUNNER_TEMP/d1-e2fsprogs" \
  --evidence /tmp/trillionnium-d1/evidence/e2fsprogs-host-tool-result.json)
[[ -x "$tool_dir/mke2fs" && -x "$tool_dir/e2fsck" && -x "$tool_dir/dumpe2fs" ]]
printf '%s\n' "$tool_dir" >> "$GITHUB_PATH"
printf 'D1_E2FSPROGS_DIR=%s\n' "$tool_dir" >> "$GITHUB_ENV"
}

step_validate_source() {
set -euo pipefail
export RUSTUP_TOOLCHAIN="$RUST_CHANNEL"
test -z "$(git status --porcelain=v1)"
python3 tools/validate_repository.py
python3 tools/validate_project_truth.py
python3 -m unittest discover -s tests/d1 -p 'test_*.py' -v
python3 -m py_compile \
  tools/compare_d1_builds.py \
  tools/d1_rootfs_manifest.py \
  tools/finalize_d1_evidence.py \
  tools/prepare_d1_inputs.py \
  tools/resolve_debian_snapshot.py \
  tools/resolve_debian_snapshot_with_pinned_keys.py \
  tools/verify_d1_artifact.py
shellcheck -e SC2016,SC2054 \
  packaging/debian/image/build-d1-image.sh \
  packaging/debian/image/rootfs-overlay/usr/local/libexec/trillionnium-d1-acceptance \
  packaging/debian/image/rootfs-overlay/usr/local/libexec/trillionnium-d1-agent-fixture-launcher \
  tests/qemu/run-d1-boot-test.sh \
  tests/qemu/run-d1-pipeline.sh \
  tools/build_pinned_e2fsprogs.sh \
  tools/run_d1_final_qualification.sh
cargo fmt --all --check
cargo check --workspace --all-targets --locked
cargo clippy --workspace --all-targets --all-features --locked -- -D warnings
cargo test --workspace --all-targets --all-features --locked
}

step_prove_graphs() {
set -euo pipefail
export RUSTUP_TOOLCHAIN="$RUST_CHANNEL"
mkdir -p /tmp/trillionnium-d1/evidence
cargo tree --locked -p hepta-agent-portd --no-default-features -e normal \
  > /tmp/trillionnium-d1/evidence/product-cargo-tree.txt
if grep -Eq 'hepta-agent-port v|hepta-browser-codec v' \
  /tmp/trillionnium-d1/evidence/product-cargo-tree.txt; then
  echo "product daemon graph contains qualification dependencies" >&2
  exit 1
fi
cargo tree --locked -p hepta-agent-portd --no-default-features \
  --features d1-qualification -e normal \
  > /tmp/trillionnium-d1/evidence/qualification-cargo-tree.txt
grep -q 'hepta-agent-port v' \
  /tmp/trillionnium-d1/evidence/qualification-cargo-tree.txt
grep -q 'hepta-browser-codec v' \
  /tmp/trillionnium-d1/evidence/qualification-cargo-tree.txt
! grep -q 'hepta-agent-d1-fixture' packaging/debian/hepta-agent-portd.install
! grep -q 'image/rootfs-overlay' packaging/debian/hepta-agent-portd.install
}

step_build_binaries() {
set -euo pipefail
export RUSTUP_TOOLCHAIN="$RUST_CHANNEL"
cargo build --release --locked \
  -p hepta-agent-portd \
  --no-default-features \
  --bin hepta-agent-portd
install -D -m 0755 target/release/hepta-agent-portd \
  "$RUNNER_TEMP/hepta-agent-portd-product"
cargo build --release --locked \
  -p hepta-agent-portd \
  --no-default-features \
  --features d1-qualification \
  --bin hepta-agent-d1-fixture
install -m 0755 "$RUNNER_TEMP/hepta-agent-portd-product" \
  target/release/hepta-agent-portd
test -x target/release/hepta-agent-portd
test -x target/release/hepta-agent-d1-fixture
target/release/hepta-agent-portd --self-check \
  > /tmp/trillionnium-d1/evidence/product-daemon-self-check-host.json
target/release/hepta-agent-d1-fixture --mode self-check \
  > /tmp/trillionnium-d1/evidence/d1-qualification-self-check-host.json
strings target/release/hepta-agent-portd \
  > /tmp/trillionnium-d1/evidence/product-daemon.strings
strings target/release/hepta-agent-d1-fixture \
  > /tmp/trillionnium-d1/evidence/qualification-fixture.strings
! grep -q 'agent_port_ready' \
  /tmp/trillionnium-d1/evidence/product-daemon.strings
! grep -q 'browser_runtime_available' \
  /tmp/trillionnium-d1/evidence/product-daemon.strings
grep -q 'qualification_only' \
  /tmp/trillionnium-d1/evidence/qualification-fixture.strings
grep -q 'product_handler_connected' \
  /tmp/trillionnium-d1/evidence/qualification-fixture.strings
grep -q '"product_handler_connected":false' \
  /tmp/trillionnium-d1/evidence/product-daemon-self-check-host.json
grep -q '"fixture_handler_linked":false' \
  /tmp/trillionnium-d1/evidence/product-daemon-self-check-host.json
}

step_run_pipeline() {
set -euo pipefail
export RUSTUP_TOOLCHAIN="$RUST_CHANNEL"
test "$(readlink -f "$(command -v mke2fs)")" = "$D1_E2FSPROGS_DIR/mke2fs"
tests/qemu/run-d1-pipeline.sh \
  --workspace "$GITHUB_WORKSPACE" \
  --output-dir /tmp/trillionnium-d1
}

step_enforce_evidence() {
set -euo pipefail
python3 tools/finalize_d1_evidence.py \
  --repository "$GITHUB_WORKSPACE" \
  --root /tmp/trillionnium-d1 \
  --artifact-root /tmp/trillionnium-d1-artifact
python3 tools/verify_d1_artifact.py /tmp/trillionnium-d1-artifact \
  | tee /tmp/trillionnium-d1/evidence/offline-verification.json
# Re-finalize so the independent verifier report is itself digest-bound.
python3 tools/finalize_d1_evidence.py \
  --repository "$GITHUB_WORKSPACE" \
  --root /tmp/trillionnium-d1 \
  --artifact-root /tmp/trillionnium-d1-artifact
python3 tools/verify_d1_artifact.py /tmp/trillionnium-d1-artifact
}

case "${1:-}" in
  identities)
    step_identities
    ;;
  install-deps)
    step_install_deps
    ;;
  install-rust)
    step_install_rust
    ;;
  build-e2fsprogs)
    step_build_e2fsprogs
    ;;
  validate-source)
    step_validate_source
    ;;
  prove-graphs)
    step_prove_graphs
    ;;
  build-binaries)
    step_build_binaries
    ;;
  run-pipeline)
    step_run_pipeline
    ;;
  enforce-evidence)
    step_enforce_evidence
    ;;
  *)
    printf 'unknown D1 gate command: %s\n' "${1:-}" >&2
    exit 64
    ;;
esac
