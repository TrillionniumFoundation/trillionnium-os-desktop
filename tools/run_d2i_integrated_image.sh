#!/usr/bin/env bash
# Permanent read-only D2I qualification runner. It never mutates Git refs.
set -euo pipefail

step_identities() {
  local tested_sha tree_sha parent_count base_sha candidate_head_sha role authoritative
  tested_sha=$(git rev-parse HEAD)
  tree_sha=$(git rev-parse 'HEAD^{tree}')
  parent_count=$(git show -s --format='%P' HEAD | awk '{print NF}')
  git fetch --no-tags origin main
  case "$GITHUB_EVENT_NAME" in
    pull_request)
      [[ $parent_count -eq 2 ]] || {
        echo "D2I pull request evidence requires an exact two-parent synthetic merge" >&2
        exit 1
      }
      base_sha=$(git rev-parse HEAD^1)
      candidate_head_sha=$(git rev-parse HEAD^2)
      [[ $base_sha == "$(git rev-parse origin/main)" ]] || {
        echo "D2I synthetic merge is not based on current main" >&2
        exit 1
      }
      [[ -n ${EXPECTED_PR_HEAD:-} && $candidate_head_sha == "$EXPECTED_PR_HEAD" ]] || {
        echo "D2I synthetic merge second parent is not the live PR head" >&2
        exit 1
      }
      role=pr_synthetic_merge
      authoritative=false
      ;;
    push)
      [[ $GITHUB_REF == refs/heads/main ]] || {
        echo "D2I push evidence is accepted only on refs/heads/main" >&2
        exit 1
      }
      [[ $parent_count -ge 1 ]]
      base_sha=$(git rev-parse HEAD^1)
      candidate_head_sha=$tested_sha
      role=exact_main_push
      authoritative=true
      ;;
    workflow_dispatch)
      [[ $parent_count -ge 1 ]]
      base_sha=$(git rev-parse HEAD^1)
      candidate_head_sha=$tested_sha
      role=manual_non_authoritative
      authoritative=false
      ;;
    *)
      echo "unsupported D2I event: $GITHUB_EVENT_NAME" >&2
      exit 1
      ;;
  esac
  {
    printf 'TESTED_SHA=%s\n' "$tested_sha"
    printf 'TESTED_TREE_SHA=%s\n' "$tree_sha"
    printf 'BASE_SHA=%s\n' "$base_sha"
    printf 'CANDIDATE_HEAD_SHA=%s\n' "$candidate_head_sha"
    printf 'EVIDENCE_ROLE=%s\n' "$role"
    printf 'PROMOTION_AUTHORITATIVE=%s\n' "$authoritative"
  } >> "$GITHUB_ENV"
  printf 'role=%s\nauthoritative=%s\nbase=%s\ncandidate=%s\ntested=%s\ntree=%s\n' \
    "$role" "$authoritative" "$base_sha" "$candidate_head_sha" "$tested_sha" "$tree_sha"
}

step_install_deps() {
  bash tools/run_d1_final_qualification.sh install-deps
  sudo apt-get update
  sudo apt-get install -y --no-install-recommends \
    autoconf automake ca-certificates clang cmake gperf imagemagick \
    libdbus-1-dev libegl1-mesa-dev libfontconfig1-dev libfreetype-dev \
    libgl1-mesa-dev libgles2-mesa-dev libgstreamer-plugins-base1.0-dev \
    libgstreamer1.0-dev libharfbuzz-dev liblzma-dev libssl-dev libunwind-dev \
    libwayland-dev libx11-dev libx11-xcb-dev libxcb-render0-dev \
    libxcb-shape0-dev libxcb-xfixes0-dev libxkbcommon-dev \
    libxkbcommon-x11-dev mesa-utils nasm ninja-build patch pkg-config \
    python3-pip x11-utils x11-xserver-utils xauth xserver-xorg-dev
  sudo rm -rf /var/lib/apt/lists/*
}

step_install_rust() {
  bash tools/run_d1_final_qualification.sh install-rust
}

step_build_e2fsprogs() {
  # The D1 helper publishes D1_E2FSPROGS_DIR and its bin directory through
  # GITHUB_ENV/GITHUB_PATH. GitHub applies those files to the next workflow
  # step, not to this parent shell, so same-step variable checks are invalid.
  bash tools/run_d1_final_qualification.sh build-e2fsprogs
}

step_validate_source() {
  export RUSTUP_TOOLCHAIN="$RUST_CHANNEL"
  bash tools/run_d1_final_qualification.sh validate-source
  python3 -m py_compile \
    tools/prepare_d2i_runtime.py \
    tools/prepare_d2i_boot_runner.py \
    tools/finalize_d2i_evidence.py \
    tools/verify_d2i_artifact.py
  python3 -m unittest tests.d1.test_d2i_contract -v
  shellcheck -e SC2016,SC2054 \
    tools/run_d2i_integrated_image.sh \
    tests/qemu/prepare-d2i-image.sh \
    tests/qemu/run-d2i-boot-test.base.sh \
    packaging/debian/image/d2i-overlay/usr/local/libexec/trillionnium-d2i-acceptance
  test -z "$(git status --porcelain=v1)"
  ! grep -RInE 'contents:[[:space:]]*write|git[[:space:]]+push' \
    .github/workflows/d2i-integrated-image.yml tools/run_d2i_integrated_image.sh
}

step_prove_d1_graphs() {
  bash tools/run_d1_final_qualification.sh prove-graphs
}

step_build_d1_binaries() {
  bash tools/run_d1_final_qualification.sh build-binaries
}

step_verify_servo() {
  test "$(git -C servo-source rev-parse HEAD)" = "$SERVO_COMMIT"
  test -z "$(git -C servo-source status --porcelain=v1)"
  python3 - <<'PY'
import json
from pathlib import Path
expected = '670ae8a70801b162e186f81cbb5bdd2d59c39108'
lock = json.loads(Path('manifests/servo.lock.json').read_text())
ledger = json.loads(Path('manifests/servo-patch-ledger.v1.json').read_text())
assert lock['commit'] == expected
assert ledger['servo_commit'] == expected
assert ledger['patch_count'] == 0 and ledger['patches'] == []
PY
}

step_install_servo_rust() {
  local channel
  channel=$(python3 - <<'PY'
from pathlib import Path
import tomllib
print(tomllib.loads(Path('servo-source/rust-toolchain.toml').read_text())['toolchain']['channel'])
PY
)
  printf 'SERVO_RUST_CHANNEL=%s\n' "$channel" >> "$GITHUB_ENV"
  rustup toolchain install "$channel" --profile minimal --component rustfmt
  RUSTUP_TOOLCHAIN="$channel" rustc --version --verbose
  RUSTUP_TOOLCHAIN="$channel" cargo --version --verbose
}

step_build_runtime() {
  local generated evidence
  generated=servo-source/components/servo/examples/hepta_workspace_runtime.rs
  evidence=/tmp/trillionnium-d2i/evidence/runtime-transformation.json
  mkdir -p /tmp/trillionnium-d2i/evidence
  python3 tools/prepare_d2i_runtime.py \
    --source runtime/servo/hepta_workspace_runtime.rs \
    --output "$generated" \
    --evidence "$evidence"
  export RUSTUP_TOOLCHAIN="$SERVO_RUST_CHANNEL"
  rustfmt --edition 2024 "$generated"
  rustfmt --edition 2024 --check "$generated"
  python3 - "$generated" "$evidence" <<'PY'
from pathlib import Path
import hashlib
import json
import sys
source = Path(sys.argv[1])
evidence = Path(sys.argv[2])
record = json.loads(evidence.read_text())
record['formatted_output_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
record['formatter'] = 'rustfmt from exact Servo Rust channel'
evidence.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
PY
  cargo build --release --locked --manifest-path servo-source/Cargo.toml \
    -p servo --example hepta_workspace_runtime
  install -D -m 0755 \
    servo-source/target/release/examples/hepta_workspace_runtime \
    /tmp/trillionnium-d2i/hepta-workspace-runtime
  sha256sum /tmp/trillionnium-d2i/hepta-workspace-runtime \
    > /tmp/trillionnium-d2i/headed-runtime.sha256
  rm -f "$generated"
  test -z "$(git -C servo-source status --porcelain=v1)"
}

step_run_d1() {
  export RUSTUP_TOOLCHAIN="$RUST_CHANNEL"
  bash tools/run_d1_final_qualification.sh run-pipeline
  bash tools/run_d1_final_qualification.sh enforce-evidence
}

step_prepare_images() {
  local base source_epoch
  base=/tmp/trillionnium-d1/build-a/candidate/artifacts/trillionnium-d1.ext4
  source_epoch=$(jq -er '.source_date_epoch' \
    /tmp/trillionnium-d1/prepared/prepared-inputs.json)
  mkdir -p /tmp/trillionnium-d2i/integrated
  for build in a b; do
    tests/qemu/prepare-d2i-image.sh \
      --base-image "$base" \
      --runtime-binary /tmp/trillionnium-d2i/hepta-workspace-runtime \
      --overlay packaging/debian/image/d2i-overlay \
      --source-epoch "$source_epoch" \
      --servo-revision "$SERVO_COMMIT" \
      --output-image "/tmp/trillionnium-d2i/integrated/d2i-$build.ext4" \
      --evidence "/tmp/trillionnium-d2i/integrated/preparation-$build.json"
  done
  cmp -s /tmp/trillionnium-d2i/integrated/d2i-a.ext4 \
    /tmp/trillionnium-d2i/integrated/d2i-b.ext4
  sha256sum /tmp/trillionnium-d2i/integrated/d2i-a.ext4 \
    /tmp/trillionnium-d2i/integrated/d2i-b.ext4 \
    > /tmp/trillionnium-d2i/integrated/image-sha256.txt
  test "$(jq -r '.integrated_image_sha256' /tmp/trillionnium-d2i/integrated/preparation-a.json)" = \
    "$(jq -r '.integrated_image_sha256' /tmp/trillionnium-d2i/integrated/preparation-b.json)"
}

step_boot_image() {
  python3 tools/prepare_d2i_boot_runner.py \
    --source tests/qemu/run-d2i-boot-test.base.sh \
    --output /tmp/trillionnium-d2i/run-d2i-boot-test.sh \
    --evidence /tmp/trillionnium-d2i/evidence/boot-runner-transformation.json
  /tmp/trillionnium-d2i/run-d2i-boot-test.sh \
    --selection manifests/debian-d1.selection.json \
    --artifacts /tmp/trillionnium-d1/build-a/candidate/artifacts \
    --image /tmp/trillionnium-d2i/integrated/d2i-a.ext4 \
    --preparation /tmp/trillionnium-d2i/integrated/preparation-a.json \
    --output-dir /tmp/trillionnium-d2i/qemu
}

step_finalize_evidence() {
  python3 tools/finalize_d2i_evidence.py \
    --repository "$GITHUB_WORKSPACE" \
    --d1-artifact /tmp/trillionnium-d1-artifact \
    --d2i-root /tmp/trillionnium-d2i \
    --artifact-root /tmp/trillionnium-d2i-artifact
  python3 tools/verify_d2i_artifact.py /tmp/trillionnium-d2i-artifact \
    | tee /tmp/trillionnium-d2i/evidence/offline-verification.json
  python3 tools/finalize_d2i_evidence.py \
    --repository "$GITHUB_WORKSPACE" \
    --d1-artifact /tmp/trillionnium-d1-artifact \
    --d2i-root /tmp/trillionnium-d2i \
    --artifact-root /tmp/trillionnium-d2i-artifact
  python3 tools/verify_d2i_artifact.py /tmp/trillionnium-d2i-artifact
}

case "${1:-}" in
  identities) step_identities ;;
  install-deps) step_install_deps ;;
  install-rust) step_install_rust ;;
  build-e2fsprogs) step_build_e2fsprogs ;;
  validate-source) step_validate_source ;;
  prove-d1-graphs) step_prove_d1_graphs ;;
  build-d1-binaries) step_build_d1_binaries ;;
  verify-servo) step_verify_servo ;;
  install-servo-rust) step_install_servo_rust ;;
  build-runtime) step_build_runtime ;;
  run-d1) step_run_d1 ;;
  prepare-images) step_prepare_images ;;
  boot-image) step_boot_image ;;
  finalize-evidence) step_finalize_evidence ;;
  *) echo "unknown D2I gate command: ${1:-}" >&2; exit 64 ;;
esac
