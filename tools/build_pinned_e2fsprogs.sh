#!/bin/bash
set -euo pipefail

usage() {
  echo "Usage: build_pinned_e2fsprogs.sh --manifest PATH --work-dir PATH --evidence PATH" >&2
}

manifest=
work_dir=
evidence=
while [[ $# -gt 0 ]]; do
  case "$1" in
    --manifest) manifest=$2; shift 2 ;;
    --work-dir) work_dir=$2; shift 2 ;;
    --evidence) evidence=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done
if [[ -z "$manifest" || -z "$work_dir" || -z "$evidence" ]]; then
  usage
  exit 2
fi
manifest=$(readlink -f "$manifest")
mkdir -p "$work_dir" "$(dirname "$evidence")"
work_dir=$(readlink -f "$work_dir")
evidence=$(readlink -m "$evidence")

for command in git jq make sha256sum gcc; do
  command -v "$command" >/dev/null || {
    echo "required pinned e2fsprogs build command missing: $command" >&2
    exit 1
  }
done

repository=$(jq -er '.repository' "$manifest")
commit=$(jq -er '.commit' "$manifest")
version=$(jq -er '.version' "$manifest")
tag=$(jq -er '.tag' "$manifest")
tag_object=$(jq -er '.tag_object' "$manifest")
if ! [[ "$commit" =~ ^[0-9a-f]{40}$ && "$tag_object" =~ ^[0-9a-f]{40}$ ]]; then
  echo "invalid pinned e2fsprogs Git object IDs" >&2
  exit 1
fi
if [[ "$version" != 1.47.2 || "$tag" != v1.47.2 ]]; then
  echo "unexpected pinned e2fsprogs version contract" >&2
  exit 1
fi

source_dir="$work_dir/source"
build_dir="$work_dir/build"
prefix="$work_dir/prefix"
bin_dir="$prefix/sbin"
stamp="$work_dir/PASS"

valid_existing=false
if [[ -f "$stamp" && -x "$bin_dir/mke2fs" && -x "$bin_dir/e2fsck" && -x "$bin_dir/dumpe2fs" ]]; then
  installed_version=$($bin_dir/mke2fs -V 2>&1 | awk 'NR == 1 { print $2 }')
  if [[ "$installed_version" == "$version" && "$(cat "$stamp")" == "$commit" ]]; then
    valid_existing=true
  fi
fi

if [[ "$valid_existing" != true ]]; then
  rm -rf "$source_dir" "$build_dir" "$prefix" "$stamp"
  mkdir -p "$source_dir" "$build_dir" "$prefix"
  git -C "$source_dir" init -q
  git -C "$source_dir" remote add origin "$repository"
  git -C "$source_dir" fetch --no-tags --depth=1 origin "$commit"
  git -C "$source_dir" checkout -q --detach FETCH_HEAD
  test "$(git -C "$source_dir" rev-parse HEAD)" = "$commit"
  test -z "$(git -C "$source_dir" status --porcelain=v1)"
  git -C "$source_dir" fsck --strict --no-dangling

  (
    cd "$build_dir"
    "$source_dir/configure" \
      --prefix="$prefix" \
      --disable-nls
    make -j2
    make install
  ) >&2
  test -x "$bin_dir/mke2fs"
  test -x "$bin_dir/e2fsck"
  test -x "$bin_dir/dumpe2fs"
  installed_version=$($bin_dir/mke2fs -V 2>&1 | awk 'NR == 1 { print $2 }')
  test "$installed_version" = "$version"
  printf '%s\n' "$commit" > "$stamp"
fi

compiler=$(gcc --version | head -n1)
make_version=$(make --version | head -n1)
git_version=$(git --version)
python3 - "$evidence" "$repository" "$tag" "$tag_object" "$commit" "$version" \
  "$compiler" "$make_version" "$git_version" "$bin_dir" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

(
    output,
    repository,
    tag,
    tag_object,
    commit,
    version,
    compiler,
    make_version,
    git_version,
    bin_dir,
) = sys.argv[1:]
root = Path(bin_dir)
binaries = {}
for name in ("mke2fs", "e2fsck", "dumpe2fs"):
    path = root / name
    data = path.read_bytes()
    binaries[name] = {
        "path": str(path),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
report = {
    "schema": "trillionnium.desktop.e2fsprogs-host-tool-result.v1",
    "status": "PASS_PINNED_ISOLATED_HOST_TOOL",
    "repository": repository,
    "tag": tag,
    "tag_object": tag_object,
    "commit": commit,
    "version": version,
    "compiler": compiler,
    "make": make_version,
    "git": git_version,
    "binaries": binaries,
    "system_install_modified": False,
    "claim_ceiling": "host_image_construction_tool_only",
}
Path(output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
PY

printf '%s\n' "$bin_dir"
