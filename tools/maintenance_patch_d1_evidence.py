#!/usr/bin/env python3
"""One-shot source patch for D1 evidence and reproducibility soundness."""

from __future__ import annotations

import json
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def replace_function(text: str, name: str, next_name: str, body: str) -> str:
    start = text.index(f"{name}() {{")
    if next_name == "case":
        end = text.index('\ncase "${1:-}" in', start)
    else:
        end = text.index(f"\n{next_name}() {{", start)
    return text[:start] + body.rstrip() + "\n" + text[end:]


def patch_builder() -> None:
    path = Path("packaging/debian/image/build-d1-image.sh")
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''find "$rootfs" -xdev -print0 \\
  | LC_ALL=C sort -z \\
  | xargs -0r touch --no-dereference --date="@$source_epoch"

tar \\
''',
        '''find "$rootfs" -xdev -print0 \\
  | LC_ALL=C sort -z \\
  | xargs -0r touch --no-dereference --date="@$source_epoch"

python3 "$repo_root/tools/d1_rootfs_manifest.py" \\
  --root "$rootfs" \\
  --output "$artifacts/rootfs-content-manifest.json"
rootfs_manifest_sha256=$(sha256sum \\
  "$artifacts/rootfs-content-manifest.json" | awk '{print $1}')
rootfs_manifest_entries=$(jq -er '.entry_count' \\
  "$artifacts/rootfs-content-manifest.json")
rootfs_manifest_entries_sha256=$(jq -er '.entries_sha256' \\
  "$artifacts/rootfs-content-manifest.json")

tar \\
''',
        "rootfs manifest generation",
    )
    text = replace_once(
        text,
        '''  "package_lock": {
    "path": "package-lock.tsv",
    "entries": $actual_count,
    "sha256": "$package_lock_sha256"
  },
  "rootfs_tar": {
''',
        '''  "package_lock": {
    "path": "package-lock.tsv",
    "entries": $actual_count,
    "sha256": "$package_lock_sha256"
  },
  "rootfs_manifest": {
    "path": "rootfs-content-manifest.json",
    "entries": $rootfs_manifest_entries,
    "entries_sha256": "$rootfs_manifest_entries_sha256",
    "sha256": "$rootfs_manifest_sha256"
  },
  "rootfs_tar": {
''',
        "build result rootfs manifest",
    )
    path.write_text(text, encoding="utf-8")


def patch_runner() -> None:
    path = Path("tools/run_d1_final_qualification.sh")
    text = path.read_text(encoding="utf-8")
    identities = r'''step_identities() {
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
}'''
    text = replace_function(text, "step_identities", "step_install_deps", identities)

    install_deps = r'''step_install_deps() {
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
}'''
    text = replace_function(text, "step_install_deps", "step_install_rust", install_deps)

    text = replace_once(
        text,
        '''python3 -m py_compile \\
  tools/compare_d1_builds.py \\
  tools/prepare_d1_inputs.py \\
  tools/resolve_debian_snapshot.py \\
  tools/resolve_debian_snapshot_with_pinned_keys.py
''',
        '''python3 -m py_compile \\
  tools/compare_d1_builds.py \\
  tools/d1_rootfs_manifest.py \\
  tools/finalize_d1_evidence.py \\
  tools/prepare_d1_inputs.py \\
  tools/resolve_debian_snapshot.py \\
  tools/resolve_debian_snapshot_with_pinned_keys.py \\
  tools/verify_d1_artifact.py
''',
        "D1 Python validation corpus",
    )
    text = replace_once(
        text,
        '''  tests/qemu/run-d1-pipeline.sh \\
  tools/build_pinned_e2fsprogs.sh
''',
        '''  tests/qemu/run-d1-pipeline.sh \\
  tools/build_pinned_e2fsprogs.sh \\
  tools/run_d1_final_qualification.sh
''',
        "D1 shell validation corpus",
    )

    enforce = r'''step_enforce_evidence() {
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
}'''
    text = replace_function(text, "step_enforce_evidence", "case", enforce)
    path.write_text(text, encoding="utf-8")


def patch_gate_registry() -> None:
    path = Path("manifests/gates.v1.json")
    document = json.loads(path.read_text(encoding="utf-8"))
    matches = [gate for gate in document["gates"] if gate.get("id") == "D1-01"]
    if len(matches) != 1:
        raise SystemExit("gate registry must contain exactly one D1-01 gate")
    matches[0]["invalidation_paths"] = [
        ".github/workflows/d1-final-qualification.yml",
        "Cargo.toml",
        "Cargo.lock",
        "rust-toolchain.toml",
        "apps/**",
        "crates/**",
        "contracts/**",
        "manifests/debian-*.json",
        "manifests/e2fsprogs-host-toolchain.v1.json",
        "manifests/d1-host-toolchain.lock.v1.json",
        "manifests/project-state.v1.json",
        "manifests/gates.v1.json",
        "packaging/debian/**",
        "tests/d1/**",
        "tests/qemu/**",
        "tests/fixtures/**",
        "tools/**",
    ]
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_tests() -> None:
    path = Path("tests/d1/test_d1_evidence_soundness.py")
    path.write_text(
        '''from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class D1EvidenceSoundnessTests(unittest.TestCase):
    def test_permanent_gate_is_unconditional_read_only_and_non_mutating(self) -> None:
        workflow = (ROOT / ".github/workflows/d1-final-qualification.yml").read_text(
            encoding="utf-8"
        )
        trigger = workflow.split("\\npermissions:\\n", 1)[0]
        self.assertNotIn("paths:", trigger)
        self.assertNotIn("paths-ignore:", trigger)
        self.assertIn("pull_request:", trigger)
        self.assertIn("push:", trigger)
        self.assertIn("branches: [main]", trigger)
        self.assertIn("permissions:\\n  contents: read", workflow)
        self.assertNotIn("git push", workflow)
        self.assertNotIn("gh workflow run", workflow)

    def test_gate_registry_covers_actual_build_dependency_domains(self) -> None:
        registry = json.loads(
            (ROOT / "manifests/gates.v1.json").read_text(encoding="utf-8")
        )
        gate = next(item for item in registry["gates"] if item["id"] == "D1-01")
        paths = set(gate["invalidation_paths"])
        for required in {
            "Cargo.toml",
            "Cargo.lock",
            "rust-toolchain.toml",
            "apps/**",
            "crates/**",
            "contracts/**",
            "packaging/debian/**",
            "tests/d1/**",
            "tests/qemu/**",
            "tests/fixtures/**",
            "tools/**",
        }:
            self.assertIn(required, paths)

    def test_rootfs_manifest_and_portable_verifier_are_bound(self) -> None:
        builder = (ROOT / "packaging/debian/image/build-d1-image.sh").read_text(
            encoding="utf-8"
        )
        comparer = (ROOT / "tools/compare_d1_builds.py").read_text(encoding="utf-8")
        runner = (ROOT / "tools/run_d1_final_qualification.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("tools/d1_rootfs_manifest.py", builder)
        self.assertIn("rootfs-content-manifest.json", builder)
        self.assertIn("rootfs-content-manifest.json", comparer)
        self.assertIn("rootfs_manifest_diff", comparer)
        self.assertIn("tools/finalize_d1_evidence.py", runner)
        self.assertIn("tools/verify_d1_artifact.py", runner)
        self.assertNotIn("git push", runner)
        self.assertNotIn("gh workflow run", runner)


if __name__ == "__main__":
    unittest.main()
''',
        encoding="utf-8",
    )


def main() -> None:
    patch_builder()
    patch_runner()
    patch_gate_registry()
    write_tests()


if __name__ == "__main__":
    main()
