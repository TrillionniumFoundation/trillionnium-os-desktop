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

for command in git jq make sha256sum gcc msgfmt locale tar truncate python3; do
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
runtime_locale=$(jq -er '.build.runtime_locale' "$manifest")
mapfile -t configure_flags < <(jq -er '.build.configure_flags[]' "$manifest")
if (( ${#configure_flags[@]} != 1 )) || [[ ${configure_flags[0]} != --enable-nls ]]; then
  echo "pinned e2fsprogs must use the reviewed --enable-nls build contract" >&2
  exit 1
fi
if [[ $(LC_ALL="$runtime_locale" LANG="$runtime_locale" locale charmap) != UTF-8 ]]; then
  echo "pinned e2fsprogs runtime locale is not UTF-8: $runtime_locale" >&2
  exit 1
fi
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
build_fingerprint="$commit:${configure_flags[*]}:$runtime_locale"

valid_existing=false
if [[ -f "$stamp" && -x "$bin_dir/mke2fs" && -x "$bin_dir/e2fsck" && -x "$bin_dir/dumpe2fs" ]]; then
  installed_version=$("$bin_dir/mke2fs" -V 2>&1 | awk 'NR == 1 { print $2 }')
  if [[ "$installed_version" == "$version" && "$(cat "$stamp")" == "$build_fingerprint" ]]; then
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
      "${configure_flags[@]}"
    make -j2
    # Install only the three reviewed image-construction tools. A top-level
    # `make install` also writes udev/systemd/scrub assets to host paths that
    # are outside the isolated prefix and is therefore forbidden.
    make -C e2fsck install
    make -C misc install
  ) >&2
  test -x "$bin_dir/mke2fs"
  test -x "$bin_dir/e2fsck"
  test -x "$bin_dir/dumpe2fs"
  installed_version=$("$bin_dir/mke2fs" -V 2>&1 | awk 'NR == 1 { print $2 }')
  test "$installed_version" = "$version"
  printf '%s\n' "$build_fingerprint" > "$stamp"
fi

probe="$work_dir/utf8-probe"
rm -rf "$probe"
mkdir -p "$probe/root"
printf 'utf8-path-probe\n' > "$probe/root/路径.txt"
LC_ALL=C tar \
  --sort=name \
  --format=pax \
  --pax-option=delete=atime,delete=ctime,exthdr.name=%d/PaxHeaders/%f \
  --numeric-owner \
  --mtime='@1700000000' \
  -C "$probe/root" \
  -cf "$probe/rootfs.tar" .
truncate -s 64M "$probe/probe.ext4"
probe_uuid=7f453284-a1e5-4f17-9c30-7c5bde91ffff
E2FSPROGS_FAKE_TIME=1700000000 \
  LC_ALL="$runtime_locale" LANG="$runtime_locale" \
  "$bin_dir/mke2fs" \
  -F -q -t ext4 -b 4096 -I 256 -m 0 \
  -L TOSD1PROBE -U "$probe_uuid" \
  -E "root_owner=0:0,lazy_itable_init=0,lazy_journal_init=0,hash_seed=$probe_uuid" \
  -d "$probe/rootfs.tar" \
  "$probe/probe.ext4"
"$bin_dir/e2fsck" -fn "$probe/probe.ext4" >/dev/null
probe_image_sha256=$(sha256sum "$probe/probe.ext4" | awk '{print $1}')
rm -rf "$probe"

compiler=$(gcc --version | head -n1)
make_version=$(make --version | head -n1)
git_version=$(git --version)
python3 - "$evidence" "$repository" "$tag" "$tag_object" "$commit" "$version" \
  "$compiler" "$make_version" "$git_version" "$bin_dir" \
  "${configure_flags[*]}" "$runtime_locale" "$probe_image_sha256" <<'PY'
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
    configure_flag,
    runtime_locale,
    probe_image_sha256,
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
    "configure_flags": [configure_flag],
    "runtime_locale": runtime_locale,
    "utf8_tar_import_probe": {
        "status": "PASS",
        "image_sha256": probe_image_sha256,
    },
    "source_patch_count": 0,
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
