#!/usr/bin/env bash
# Permanent D1 qualification runner. It never mutates Git refs.
set -euo pipefail

step_identities() {
set -euo pipefail
tested_sha=$(git rev-parse HEAD)
tree_sha=$(git rev-parse 'HEAD^{tree}')
parent_line=$(git rev-list --parents -n 1 HEAD)
parent_count=$(awk '{print NF - 1}' <<<"$parent_line")
if [[ "$EVENT_NAME" == pull_request ]]; then
  [[ "$parent_count" -eq 2 ]] || {
    echo "pull-request qualification requires an exact two-parent merge object" >&2
    exit 1
  }
  base_sha=$(git rev-parse HEAD^1)
  candidate_head_sha=$(git rev-parse HEAD^2)
  [[ -n "$EXPECTED_PR_HEAD" && "$candidate_head_sha" == "$EXPECTED_PR_HEAD" ]] || {
    echo "tested second parent does not equal the exact pull-request head" >&2
    exit 1
  }
  topology=pr_merge_commit
else
  [[ "$parent_count" -ge 1 ]] || {
    echo "push qualification requires a parent commit" >&2
    exit 1
  }
  base_sha=$(git rev-parse HEAD^1)
  candidate_head_sha=$tested_sha
  topology=exact_push_commit
fi
{
  printf 'TESTED_SHA=%s\n' "$tested_sha"
  printf 'TESTED_TREE_SHA=%s\n' "$tree_sha"
  printf 'BASE_SHA=%s\n' "$base_sha"
  printf 'CANDIDATE_HEAD_SHA=%s\n' "$candidate_head_sha"
  printf 'TESTED_TOPOLOGY=%s\n' "$topology"
} >> "$GITHUB_ENV"
printf 'topology=%s\nbase=%s\ncandidate=%s\ntested=%s\ntree=%s\n' \
  "$topology" "$base_sha" "$candidate_head_sha" "$tested_sha" "$tree_sha"
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
  tools/prepare_d1_inputs.py \
  tools/resolve_debian_snapshot.py \
  tools/resolve_debian_snapshot_with_pinned_keys.py
shellcheck -e SC2016,SC2054 \
  packaging/debian/image/build-d1-image.sh \
  packaging/debian/image/rootfs-overlay/usr/local/libexec/trillionnium-d1-acceptance \
  packaging/debian/image/rootfs-overlay/usr/local/libexec/trillionnium-d1-agent-fixture-launcher \
  tests/qemu/run-d1-boot-test.sh \
  tests/qemu/run-d1-pipeline.sh \
  tools/build_pinned_e2fsprogs.sh
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
python3 - <<'PY'
from pathlib import Path
import hashlib
import json
import os

root = Path('/tmp/trillionnium-d1')
evidence = root / 'evidence'
pipeline = json.loads((root / 'pipeline-result.json').read_text())
repro = json.loads((root / 'reproducibility-result.json').read_text())
boot = json.loads((root / 'qemu/boot-result.json').read_text())
acceptance = json.loads((root / 'qemu/acceptance.json').read_text())
host_tool = json.loads((evidence / 'e2fsprogs-host-tool-result.json').read_text())
product_check = json.loads((evidence / 'product-daemon-self-check-host.json').read_text())
qualification_check = json.loads((evidence / 'd1-qualification-self-check-host.json').read_text())

assert pipeline['status'] == 'PASS', pipeline
assert repro['status'] == 'PASS_TWO_INDEPENDENT_BUILDS', repro
assert repro['reproducible'] is True, repro
assert boot['status'] == 'PASS_QEMU_PID1_WAYLAND_AND_AGENT_PORT', boot
assert acceptance['schema'] == 'trillionnium.desktop.d1-acceptance.v2', acceptance
assert acceptance['status'] == 'PASS', acceptance
assert host_tool['status'] == 'PASS_PINNED_ISOLATED_HOST_TOOL', host_tool
assert product_check['ok'] is True, product_check
assert product_check['product_handler_connected'] is False, product_check
assert product_check['fixture_handler_linked'] is False, product_check
assert qualification_check['status'] == 'PASS', qualification_check
assert qualification_check['qualification_only'] is True, qualification_check
assert qualification_check['product_handler_connected'] is False, qualification_check

claims = boot['claims']
for key in [
    'systemd_booted', 'udev_active', 'dbus_active', 'logind_active',
    'headless_wayland_active', 'agent_port_default_disabled',
    'agent_port_pid1_activation_validated', 'unauthorized_peer_denied',
    'authorized_fixture_request', 'per_connection_teardown',
    'connection_kill_recovered',
]:
    assert claims[key] is True, (key, claims.get(key))
assert claims['network_enabled'] is False
assert claims['servo_started'] is False
assert claims['visible_window_created'] is False
assert claims['secure_boot_qualified'] is False
assert boot['release_marker_absent'] is True
assert boot['clean_poweroff'] is True

agent = acceptance['agent_port']
for key in [
    'qualification_only_server', 'product_daemon_fixture_free',
    'marker_removed_before_poweroff', 'socket_removed_before_poweroff',
]:
    assert agent[key] is True, (key, agent.get(key))
assert agent['product_handler_connected'] is False, agent
assert agent['product_daemon_exercised_for_requests'] is False, agent
assert agent['qualification_server_exec'] == \
    '/usr/libexec/hepta-agent-d1-fixture --mode server', agent

workflow = Path('.github/workflows/d1-final-qualification.yml')
input_paths = [
    Path('Cargo.lock'),
    Path('rust-toolchain.toml'),
    Path('apps/hepta-agent-portd/Cargo.toml'),
    Path('apps/hepta-agent-portd/src/main.rs'),
    Path('apps/hepta-agent-portd/src/bin/hepta-agent-d1-fixture.rs'),
    Path('manifests/debian-d1.lock.v1.json'),
    Path('manifests/debian-d1.requirements.v1.json'),
    Path('manifests/debian-d1.selection.json'),
    Path('manifests/e2fsprogs-host-toolchain.v1.json'),
    Path('packaging/debian/image/build-d1-image.sh'),
    Path('packaging/debian/image/rootfs-overlay/etc/systemd/system/'
         'hepta-browserd-agent@.service.d/10-d1-qualification-server.conf'),
    Path('packaging/debian/image/rootfs-overlay/usr/local/libexec/'
         'trillionnium-d1-acceptance'),
    Path('packaging/debian/systemd/hepta-browserd-agent@.service'),
    Path('tests/qemu/run-d1-boot-test.sh'),
    Path('tests/qemu/run-d1-pipeline.sh'),
]
output_paths = [
    evidence / 'product-cargo-tree.txt',
    evidence / 'qualification-cargo-tree.txt',
    evidence / 'product-daemon-self-check-host.json',
    evidence / 'd1-qualification-self-check-host.json',
    root / 'pipeline-result.json',
    root / 'reproducibility-result.json',
    root / 'qemu/boot-result.json',
    root / 'qemu/acceptance.json',
]
summary = {
    'schema': 'trillionnium.desktop.d1-final-qualification.v2',
    'status': 'PASS',
    'repository': os.environ['GITHUB_REPOSITORY'],
    'event_name': os.environ['GITHUB_EVENT_NAME'],
    'tested_topology': os.environ['TESTED_TOPOLOGY'],
    'base_sha': os.environ['BASE_SHA'],
    'candidate_head_sha': os.environ['CANDIDATE_HEAD_SHA'],
    'tested_sha': os.environ['TESTED_SHA'],
    'tree_sha': os.environ['TESTED_TREE_SHA'],
    'workflow_sha256': hashlib.sha256(workflow.read_bytes()).hexdigest(),
    'workflow_run_id': os.environ['GITHUB_RUN_ID'],
    'workflow_run_attempt': int(os.environ['GITHUB_RUN_ATTEMPT']),
    'input_digests': {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in input_paths
    },
    'output_digests': {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in output_paths
    },
    'product_fixture_separation': {
        'product_default_graph_fixture_free': True,
        'qualification_feature': 'd1-qualification',
        'qualification_binary': 'hepta-agent-d1-fixture',
        'qualification_server_exec': agent['qualification_server_exec'],
        'product_handler_connected': False,
        'production_install_map_contains_qualification_binary': False,
    },
    'host_tool': host_tool,
    'pipeline': pipeline,
    'reproducibility': repro,
    'boot': boot,
    'acceptance': acceptance,
    'claim_ceiling': {
        'servo_started': False,
        'visible_window_created': False,
        'network_enabled_during_acceptance': False,
        'secure_boot_qualified': False,
        'product_agent_port_enabled': False,
        'product_release_authorized': False,
    },
}
(evidence / 'd1-final-qualification.json').write_text(
    json.dumps(summary, indent=2, sort_keys=True) + '\n'
)
PY
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
