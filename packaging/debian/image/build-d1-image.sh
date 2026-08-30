#!/bin/bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: build-d1-image.sh \
  --selection manifests/debian-d1.selection.json \
  --prepared-manifest /path/prepared-inputs.json \
  --sources-list /path/sources.list \
  --exact-packages /path/exact-packages.txt \
  --expected-package-lock /path/expected-package-lock.tsv \
  --agent-portd-binary /path/hepta-agent-portd \
  --agent-fixture-binary /path/hepta-agent-d1-fixture \
  --overlay packaging/debian/image/rootfs-overlay \
  --output-dir /path/output \
  --build-name build-a
EOF
}

selection=
prepared_manifest=
sources_list=
exact_packages=
expected_package_lock=
agent_portd_binary=
agent_fixture_binary=
overlay=
output_dir=
build_name=
while [[ $# -gt 0 ]]; do
  case "$1" in
    --selection) selection=$2; shift 2 ;;
    --prepared-manifest) prepared_manifest=$2; shift 2 ;;
    --sources-list) sources_list=$2; shift 2 ;;
    --exact-packages) exact_packages=$2; shift 2 ;;
    --expected-package-lock) expected_package_lock=$2; shift 2 ;;
    --agent-portd-binary) agent_portd_binary=$2; shift 2 ;;
    --agent-fixture-binary) agent_fixture_binary=$2; shift 2 ;;
    --overlay) overlay=$2; shift 2 ;;
    --output-dir) output_dir=$2; shift 2 ;;
    --build-name) build_name=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

required_values=(
  selection prepared_manifest sources_list exact_packages expected_package_lock
  agent_portd_binary agent_fixture_binary overlay output_dir build_name
)
for value in "${required_values[@]}"; do
  if [[ -z "${!value}" ]]; then
    echo "missing --${value//_/-}" >&2
    exit 2
  fi
done

if [[ $EUID -ne 0 ]]; then
  echo "build-d1-image.sh must run as root" >&2
  exit 1
fi

for command in mmdebstrap python3 jq tar chroot rsync sha256sum \
  systemd-sysusers systemd-tmpfiles cmp diff readlink stat awk locale; do
  command -v "$command" >/dev/null || {
    echo "required command is missing: $command" >&2
    exit 1
  }
done

if ! [[ "$build_name" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "unsafe D1 build name" >&2
  exit 2
fi

mke2fs_binary=${D1_MKE2FS_BINARY:-}
e2fsck_binary=${D1_E2FSCK_BINARY:-}
dumpe2fs_binary=${D1_DUMPE2FS_BINARY:-}
for binding in mke2fs_binary e2fsck_binary dumpe2fs_binary; do
  if [[ -z "${!binding}" ]]; then
    echo "missing explicit D1 filesystem-tool binding: $binding" >&2
    exit 1
  fi
done
mke2fs_binary=$(readlink -f "$mke2fs_binary")
e2fsck_binary=$(readlink -f "$e2fsck_binary")
dumpe2fs_binary=$(readlink -f "$dumpe2fs_binary")
for binary in "$mke2fs_binary" "$e2fsck_binary" "$dumpe2fs_binary"; do
  [[ -f "$binary" && -x "$binary" && ! -L "$binary" ]] || {
    echo "explicit D1 filesystem tool is missing or unsafe: $binary" >&2
    exit 1
  }
done
e2fsprogs_dir=$(dirname "$mke2fs_binary")
if [[ $(dirname "$e2fsck_binary") != "$e2fsprogs_dir" \
   || $(dirname "$dumpe2fs_binary") != "$e2fsprogs_dir" ]]; then
  echo "D1 filesystem tools do not share one exact reviewed prefix" >&2
  exit 1
fi
if [[ $(readlink -f "$(command -v mke2fs)") != "$mke2fs_binary" \
   || $(readlink -f "$(command -v e2fsck)") != "$e2fsck_binary" \
   || $(readlink -f "$(command -v dumpe2fs)") != "$dumpe2fs_binary" ]]; then
  echo "D1 filesystem tool PATH does not resolve to the explicit reviewed bindings" >&2
  exit 1
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(readlink -f "$script_dir/../../..")
# shellcheck source=../../../tools/reject_symlink_path.sh
source "$script_dir/../../../tools/reject_symlink_path.sh"
check_raw_path() {
  reject_symlink_path "$2" "$1" || exit 1
}
check_raw_path "D1 selection" "$selection"
check_raw_path "D1 prepared manifest" "$prepared_manifest"
check_raw_path "D1 sources list" "$sources_list"
check_raw_path "D1 exact package list" "$exact_packages"
check_raw_path "D1 expected package lock" "$expected_package_lock"
check_raw_path "D1 AgentPort binary" "$agent_portd_binary"
check_raw_path "D1 AgentPort fixture binary" "$agent_fixture_binary"
check_raw_path "D1 overlay" "$overlay"
check_raw_path "D1 output directory" "$output_dir"
selection=$(readlink -f -- "$selection")
prepared_manifest=$(readlink -f -- "$prepared_manifest")
sources_list=$(readlink -f -- "$sources_list")
exact_packages=$(readlink -f -- "$exact_packages")
expected_package_lock=$(readlink -f -- "$expected_package_lock")
agent_portd_binary=$(readlink -f -- "$agent_portd_binary")
agent_fixture_binary=$(readlink -f -- "$agent_fixture_binary")
overlay=$(readlink -f -- "$overlay")
mkdir -p -- "$output_dir"
reject_symlink_path "$output_dir" "D1 output directory" || exit 1
output_dir=$(readlink -f -- "$output_dir")
[[ -d "$output_dir" && ! -L "$output_dir" ]] || {
  echo "D1 output path is not a regular directory: $output_dir" >&2
  exit 1
}

for path in "$selection" "$prepared_manifest" "$sources_list" "$exact_packages" \
  "$expected_package_lock" "$agent_portd_binary" "$agent_fixture_binary"; do
  [[ -f "$path" && ! -L "$path" ]] || {
    echo "required regular input is missing or is a symlink: $path" >&2
    exit 1
  }
done
[[ -d "$overlay" && ! -L "$overlay" ]] || {
  echo "D1 overlay is missing or unsafe: $overlay" >&2
  exit 1
}

suite=$(jq -er '.suite' "$selection")
architecture=$(jq -er '.architecture' "$selection")
source_epoch=$(jq -er '.source_date_epoch' "$prepared_manifest")
image_size_mib=$(jq -er '.root_filesystem.size_mib' "$selection")
image_label=$(jq -er '.root_filesystem.label' "$selection")
image_uuid=$(jq -er '.root_filesystem.uuid' "$selection")
prepared_status=$(jq -er '.status' "$prepared_manifest")
expected_count=$(jq -er '.package_count' "$prepared_manifest")
expected_set_sha256=$(jq -er '.package_set_sha256' "$prepared_manifest")
host_keyring_raw=$(jq -er '.archive_keyring.path' "$prepared_manifest")
# The prepared manifest is an untrusted transport object at this boundary.
# Its keyring path must remain the exact file emitted beside the manifest; a
# free-form absolute path would otherwise let this root process read and
# install arbitrary host bytes into the image.  Check the raw spelling before
# canonicalization so a symlinked parent cannot be erased by readlink -f.
check_raw_path "Debian archive keyring" "$host_keyring_raw"
host_keyring=$(readlink -f -- "$host_keyring_raw")
expected_host_keyring=$(readlink -f -- \
  "$(dirname -- "$prepared_manifest")/trust/debian-13-archive-keyring.gpg")
if [[ "$host_keyring" != "$expected_host_keyring" ]]; then
  echo "prepared archive keyring is outside the generated trust workspace" >&2
  exit 1
fi
check_raw_path "Debian archive keyring" "$host_keyring"
expected_keyring_sha256=$(jq -er '.archive_keyring.sha256' "$prepared_manifest")
if ! [[ "$expected_keyring_sha256" =~ ^[0-9a-f]{64}$ ]] || \
   [[ "$expected_keyring_sha256" =~ ^0{64}$ ]]; then
  echo "prepared archive keyring digest is malformed" >&2
  exit 1
fi
if ! [[ "$suite" =~ ^[a-z0-9][a-z0-9+.-]*$ ]]; then
  echo "unsafe Debian suite" >&2
  exit 1
fi
if ! [[ "$image_label" =~ ^[A-Za-z0-9._-]{1,16}$ ]]; then
  echo "unsafe D1 filesystem label" >&2
  exit 1
fi
if ! [[ "$image_uuid" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]; then
  echo "unsafe D1 filesystem UUID" >&2
  exit 1
fi
if [[ "$prepared_status" != PASS_GENERATED_SIGNED_D1_PACKAGE_LOCK \
   && "$prepared_status" != PASS_COMMITTED_SIGNED_D1_PACKAGE_LOCK ]]; then
  echo "prepared D1 inputs have not passed signed package-lock validation" >&2
  exit 1
fi
if [[ "$architecture" != amd64 ]]; then
  echo "D1 supports amd64 only" >&2
  exit 1
fi
if ! [[ "$source_epoch" =~ ^[0-9]+$ ]] || (( source_epoch <= 0 )); then
  echo "invalid source epoch" >&2
  exit 1
fi
if ! [[ "$image_size_mib" =~ ^[0-9]+$ ]] || (( image_size_mib < 1024 )); then
  echo "invalid D1 image size" >&2
  exit 1
fi
if ! [[ "$expected_count" =~ ^[0-9]+$ ]] || (( expected_count < 319 )); then
  echo "invalid D1 package count" >&2
  exit 1
fi
reject_symlink_path "$host_keyring" "Debian archive keyring" || exit 1
[[ -f "$host_keyring" && ! -L "$host_keyring" ]] || {
  echo "prepared Debian archive keyring is missing or unsafe" >&2
  exit 1
}
if [[ "$(stat -c '%h' -- "$host_keyring")" != 1 ]]; then
  echo "prepared Debian archive keyring must not be hard-linked" >&2
  exit 1
fi
actual_keyring_sha256=$(sha256sum -- "$host_keyring" | awk '{print $1}')
if [[ "$actual_keyring_sha256" != "$expected_keyring_sha256" ]]; then
  echo "prepared Debian archive keyring digest does not match its manifest" >&2
  exit 1
fi

build_dir="$output_dir/$build_name"
rootfs="$build_dir/rootfs"
logs="$build_dir/logs"
artifacts="$build_dir/artifacts"
rm -rf "$build_dir"
mkdir -p "$rootfs" "$logs" "$artifacts"

mapfile -t package_specs < <(
  sed -e '/^[[:space:]]*$/d' "$exact_packages" | LC_ALL=C sort -u
)
if (( ${#package_specs[@]} != expected_count )); then
  echo "exact package specification count does not match prepared lock" >&2
  exit 1
fi
if printf '%s\n' "${package_specs[@]}" | grep -Evq '^[a-z0-9][a-z0-9+.-]+=[^[:space:]]+$'; then
  echo "exact package specification contains an unsafe entry" >&2
  exit 1
fi
include=$(IFS=,; echo "${package_specs[*]}")
mapfile -t mirrors < <(sed -e '/^[[:space:]]*$/d' "$sources_list")
if (( ${#mirrors[@]} == 0 )); then
  echo "prepared apt sources list is empty" >&2
  exit 1
fi

export SOURCE_DATE_EPOCH="$source_epoch"
export TZ=UTC
export LC_ALL=C.UTF-8

mmdebstrap_args=(
  --mode=root
  --variant=custom
  --architectures="$architecture"
  --components=main
  --include="$include"
  --aptopt='Acquire::Check-Valid-Until "false"'
  --aptopt='Acquire::Languages "none"'
  --aptopt='APT::Install-Recommends "false"'
  --aptopt='APT::Install-Suggests "false"'
  --dpkgopt='path-exclude=/usr/share/doc/*'
  --dpkgopt='path-include=/usr/share/doc/*/copyright'
  --dpkgopt='path-exclude=/usr/share/man/*'
  --dpkgopt='path-exclude=/usr/share/locale/*'
  "$suite"
  "$rootfs"
)
mmdebstrap_args+=("${mirrors[@]}")
mmdebstrap "${mmdebstrap_args[@]}" >"$logs/mmdebstrap.log" 2>&1

# Preserve the exact signed snapshot configuration using an in-image keyring
# path. QEMU acceptance itself has no network device.
image_keyring=/usr/share/keyrings/trillionnium-debian-13-archive.gpg
install -D -m 0644 "$host_keyring" "$rootfs$image_keyring"
sed "s#signed-by=$host_keyring#signed-by=$image_keyring#g" "$sources_list" \
  > "$rootfs/etc/apt/sources.list"
install -D -m 0644 /dev/null "$rootfs/etc/apt/sources.list.d/.keep"
cat > "$rootfs/etc/apt/apt.conf.d/99trillionnium-snapshot" <<'EOF'
Acquire::Check-Valid-Until "false";
Acquire::Languages "none";
APT::Install-Recommends "false";
APT::Install-Suggests "false";
EOF

rsync -aHAX --numeric-ids --chown=0:0 "$overlay/" "$rootfs/"
install -D -m 0755 "$agent_portd_binary" "$rootfs/usr/libexec/hepta-agent-portd"
install -D -m 0755 "$agent_fixture_binary" \
  "$rootfs/usr/libexec/hepta-agent-d1-fixture"
install -D -m 0644 \
  "$repo_root/packaging/debian/systemd/hepta-browserd-agent.socket" \
  "$rootfs/etc/systemd/system/hepta-browserd-agent.socket"
install -D -m 0644 \
  "$repo_root/packaging/debian/systemd/hepta-browserd-agent@.service" \
  "$rootfs/etc/systemd/system/hepta-browserd-agent@.service"
install -D -m 0644 \
  "$repo_root/packaging/debian/sysusers.d/trillionnium-desktop.conf" \
  "$rootfs/usr/lib/sysusers.d/trillionnium-desktop.conf"
install -D -m 0644 \
  "$repo_root/packaging/debian/tmpfiles.d/trillionnium-desktop.conf" \
  "$rootfs/usr/lib/tmpfiles.d/trillionnium-desktop.conf"
install -D -m 0644 \
  "$repo_root/packaging/debian/systemd-preset/90-trillionnium-desktop.preset" \
  "$rootfs/usr/lib/systemd/system-preset/90-trillionnium-desktop.preset"

chmod 0755 \
  "$rootfs/usr/local/libexec/trillionnium-d1-acceptance" \
  "$rootfs/usr/local/libexec/trillionnium-d1-agent-fixture-launcher"
find "$rootfs/etc/systemd/system" -type f \( -name '*.service' -o -name '*.socket' -o -name '*.target' \) \
  -exec chmod 0644 {} +

# A sudo-hosted mmdebstrap build may map rootfs metadata to the invoking
# runner UID/GID. Target systemd-tmpfiles correctly rejects trusted path
# parents that are not guest root. Overlay files are explicitly installed
# as 0:0 above; here we normalize only directory and symlink metadata left
# at the builder identity. Regular or special nodes fail closed so package
# ownership, setuid bits, and file capabilities are never silently rewritten.
builder_uid=${SUDO_UID:-0}
builder_gid=${SUDO_GID:-0}
if ! [[ "$builder_uid" =~ ^[0-9]+$ && "$builder_gid" =~ ^[0-9]+$ ]]; then
  echo "invalid sudo builder identity: uid=$builder_uid gid=$builder_gid" >&2
  exit 1
fi
if (( builder_uid != 0 )); then
  if awk -F: -v id="$builder_uid" '$3 == id { found = 1 } END { exit found ? 0 : 1 }' \
      "$rootfs/etc/passwd"; then
    echo "builder UID $builder_uid collides with a guest account" >&2
    exit 1
  fi
  unexpected_uid_node=$(find "$rootfs" -xdev -uid "$builder_uid" \
    ! -type d ! -type l -print -quit)
  if [[ -n "$unexpected_uid_node" ]]; then
    echo "refusing to rewrite builder-owned non-metadata node: $unexpected_uid_node" >&2
    exit 1
  fi
  find "$rootfs" -xdev -uid "$builder_uid" \( -type d -o -type l \) \
    -exec chown --no-dereference 0 {} +
fi
if (( builder_gid != 0 )); then
  if awk -F: -v id="$builder_gid" '$3 == id { found = 1 } END { exit found ? 0 : 1 }' \
      "$rootfs/etc/group"; then
    echo "builder GID $builder_gid collides with a guest group" >&2
    exit 1
  fi
  unexpected_gid_node=$(find "$rootfs" -xdev -gid "$builder_gid" \
    ! -type d ! -type l -print -quit)
  if [[ -n "$unexpected_gid_node" ]]; then
    echo "refusing to rewrite builder-group-owned non-metadata node: $unexpected_gid_node" >&2
    exit 1
  fi
  find "$rootfs" -xdev -gid "$builder_gid" \( -type d -o -type l \) \
    -exec chgrp --no-dereference 0 {} +
fi
for trusted_path in "$rootfs" "$rootfs/etc" "$rootfs/run" "$rootfs/usr" "$rootfs/var"; do
  [[ -d "$trusted_path" && ! -L "$trusted_path" ]] || {
    echo "required trusted rootfs directory is missing or unsafe: $trusted_path" >&2
    exit 1
  }
  [[ $(stat -c '%u:%g' "$trusted_path") == 0:0 ]] || {
    echo "trusted rootfs directory is not guest-root-owned: $trusted_path" >&2
    exit 1
  }
done

chroot "$rootfs" /usr/bin/systemd-sysusers

if ! chroot "$rootfs" getent passwd hepta-desktop >/dev/null; then
  chroot "$rootfs" /usr/sbin/useradd \
    --uid 1000 \
    --user-group \
    --create-home \
    --home-dir /var/lib/hepta-desktop \
    --shell /usr/sbin/nologin \
    hepta-desktop
fi
chroot "$rootfs" /usr/sbin/usermod --lock root
install -d -m 0555 "$rootfs/proc"
mount --types proc proc "$rootfs/proc"
set +e
chroot "$rootfs" /usr/bin/systemd-tmpfiles --create
tmpfiles_status=$?
set -e
umount "$rootfs/proc"
if (( tmpfiles_status != 0 )); then
  exit "$tmpfiles_status"
fi
install -d -o 1000 -g 1000 -m 0700 "$rootfs/run/hepta-desktop"
rm -f "$rootfs/etc/hepta/enable-agent-port"
rm -f "$rootfs/run/hepta/browserd/agent.sock"

cat > "$rootfs/etc/fstab" <<EOF
LABEL=$image_label / ext4 defaults 0 1
EOF
: > "$rootfs/etc/machine-id"
rm -f "$rootfs/var/lib/dbus/machine-id"
ln -s ../../../etc/machine-id "$rootfs/var/lib/dbus/machine-id"
rm -f "$rootfs/var/lib/systemd/random-seed"
rm -rf "$rootfs/var/log/journal" "$rootfs/var/tmp/"* "$rootfs/tmp/"*
install -d -m 1777 "$rootfs/tmp" "$rootfs/var/tmp"
install -d -m 0755 "$rootfs/usr/lib/trillionnium-d1" \
  "$rootfs/var/lib/trillionnium-d1"

# The final installed closure must match every package, version, and
# architecture in the signed D1 lock. No implicit mmdebstrap package is allowed.
chroot "$rootfs" dpkg-query -W \
  -f='${Package}\t${Version}\t${Architecture}\n' \
  | LC_ALL=C sort > "$artifacts/package-lock.tsv"
if ! cmp -s "$expected_package_lock" "$artifacts/package-lock.tsv"; then
  diff -u "$expected_package_lock" "$artifacts/package-lock.tsv" \
    > "$logs/package-lock.diff" || true
  echo "installed D1 package closure differs from the signed lock" >&2
  exit 1
fi
actual_count=$(wc -l < "$artifacts/package-lock.tsv")
if (( actual_count != expected_count )); then
  echo "installed D1 package count changed after exact comparison" >&2
  exit 1
fi
package_lock_sha256=$(sha256sum "$artifacts/package-lock.tsv" | awk '{print $1}')
printf '%s\n' "$package_lock_sha256" \
  > "$rootfs/usr/lib/trillionnium-d1/package-lock.sha256"
printf '%s\n' "$expected_set_sha256" \
  > "$rootfs/usr/lib/trillionnium-d1/package-set.sha256"

selection_sha256=$(sha256sum "$selection" | awk '{print $1}')
prepared_sha256=$(sha256sum "$prepared_manifest" | awk '{print $1}')
image_id="trillionnium-desktop-d1-${selection_sha256:0:12}-${package_lock_sha256:0:12}"
printf '%s\n' "$image_id" > "$rootfs/etc/trillionnium-d1-image-id"

cat > "$rootfs/etc/initramfs-tools/conf.d/trillionnium-reproducible" <<'EOF'
COMPRESS=gzip
EOF
chroot "$rootfs" /usr/bin/env \
  SOURCE_DATE_EPOCH="$source_epoch" TZ=UTC LC_ALL=C.UTF-8 \
  update-initramfs -u -k all >"$logs/update-initramfs.log" 2>&1

mapfile -t kernels < <(
  find "$rootfs/boot" -maxdepth 1 -type f -name 'vmlinuz-*' -printf '%f\n' \
    | LC_ALL=C sort
)
mapfile -t initrds < <(
  find "$rootfs/boot" -maxdepth 1 -type f -name 'initrd.img-*' -printf '%f\n' \
    | LC_ALL=C sort
)
if (( ${#kernels[@]} != 1 || ${#initrds[@]} != 1 )); then
  printf 'kernels=%s\ninitrds=%s\n' "${kernels[*]}" "${initrds[*]}" >&2
  echo "D1 requires exactly one kernel and one initrd" >&2
  exit 1
fi
kernel_name=${kernels[0]}
initrd_name=${initrds[0]}
cp --reflink=auto "$rootfs/boot/$kernel_name" "$artifacts/vmlinuz"
cp --reflink=auto "$rootfs/boot/$initrd_name" "$artifacts/initrd.img"

rm -rf "$rootfs/var/lib/apt/lists/"* "$rootfs/var/cache/apt/archives/"*
find "$rootfs/var/log" -type f -exec truncate -s 0 {} +
find "$rootfs" -xdev -print0 \
  | LC_ALL=C sort -z \
  | xargs -0r touch --no-dereference --date="@$source_epoch"

python3 "$repo_root/tools/d1_rootfs_manifest.py" \
  --root "$rootfs" \
  --output "$artifacts/rootfs-content-manifest.json"
rootfs_manifest_sha256=$(sha256sum \
  "$artifacts/rootfs-content-manifest.json" | awk '{print $1}')
rootfs_manifest_entries=$(jq -er '.entry_count' \
  "$artifacts/rootfs-content-manifest.json")
rootfs_manifest_entries_sha256=$(jq -er '.entries_sha256' \
  "$artifacts/rootfs-content-manifest.json")

tar \
  --sort=name \
  --format=pax \
  --pax-option=delete=atime,delete=ctime,exthdr.name=%d/PaxHeaders/%f \
  --numeric-owner \
  --xattrs --acls --selinux \
  --mtime="@$source_epoch" \
  -C "$rootfs" \
  -cf "$artifacts/rootfs.tar" .
rootfs_tar_sha256=$(sha256sum "$artifacts/rootfs.tar" | awk '{print $1}')

filesystem_locale=C.UTF-8
filesystem_charmap=$(LC_ALL="$filesystem_locale" LANG="$filesystem_locale" locale charmap)
if [[ $filesystem_charmap != UTF-8 ]]; then
  echo "D1 tar import requires the exact C.UTF-8 charmap; got $filesystem_charmap" >&2
  exit 1
fi

mke2fs_version=$("$mke2fs_binary" -V 2>&1 | awk 'NR == 1 { print $2 }')
python3 -c 'import re,sys; m=re.fullmatch(r"(\d+)\.(\d+)\.(\d+)",sys.argv[1]); raise SystemExit(0 if m and tuple(map(int,m.groups())) >= (1,47,1) else 1)' "$mke2fs_version" || {
  echo "D1 reproducible tar input requires e2fsprogs >= 1.47.1; got $mke2fs_version" >&2
  exit 1
}

image="$artifacts/trillionnium-d1.ext4"
truncate -s "${image_size_mib}M" "$image"
export E2FSPROGS_FAKE_TIME="$source_epoch"
LC_ALL="$filesystem_locale" LANG="$filesystem_locale" "$mke2fs_binary" \
  -F \
  -q \
  -t ext4 \
  -b 4096 \
  -I 256 \
  -m 0 \
  -L "$image_label" \
  -U "$image_uuid" \
  -E "root_owner=0:0,lazy_itable_init=0,lazy_journal_init=0,hash_seed=$image_uuid" \
  -d "$artifacts/rootfs.tar" \
  "$image" >"$logs/mke2fs.log" 2>&1
unset E2FSPROGS_FAKE_TIME
set +e
"$e2fsck_binary" -fn "$image" >"$logs/e2fsck-read-only.log" 2>&1
e2fsck_status=$?
set -e
if (( e2fsck_status != 0 )); then
  echo "generated ext4 image failed read-only e2fsck: status=$e2fsck_status" >&2
  cat "$logs/e2fsck-read-only.log" >&2
  exit "$e2fsck_status"
fi
"$dumpe2fs_binary" -h "$image" >"$logs/dumpe2fs-header.log" 2>&1

image_sha256=$(sha256sum "$image" | awk '{print $1}')
kernel_sha256=$(sha256sum "$artifacts/vmlinuz" | awk '{print $1}')
initrd_sha256=$(sha256sum "$artifacts/initrd.img" | awk '{print $1}')

python3 - "$artifacts/build-result.json" <<PY
import json, pathlib
result = {
  "schema": "trillionnium.desktop.d1-build-result.v2",
  "status": "PASS_BUILD_ONLY",
  "build_name": "$build_name",
  "image_id": "$image_id",
  "source_date_epoch": $source_epoch,
  "selection_sha256": "$selection_sha256",
  "prepared_manifest_sha256": "$prepared_sha256",
  "signed_package_set_sha256": "$expected_set_sha256",
  "package_lock": {
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
    "path": "rootfs.tar",
    "sha256": "$rootfs_tar_sha256"
  },
  "image": {
    "path": "trillionnium-d1.ext4",
    "bytes": pathlib.Path("$image").stat().st_size,
    "sha256": "$image_sha256",
    "format": "ext4",
    "label": "$image_label",
    "uuid": "$image_uuid"
  },
  "kernel": {
    "source_name": "$kernel_name",
    "path": "vmlinuz",
    "sha256": "$kernel_sha256"
  },
  "initrd": {
    "source_name": "$initrd_name",
    "path": "initrd.img",
    "sha256": "$initrd_sha256"
  },
  "release_marker_present": False,
  "qemu_booted": False,
  "network_during_acceptance": False
}
pathlib.Path("$artifacts/build-result.json").write_text(
  json.dumps(result, indent=2, sort_keys=True) + "\n"
)
PY

rm -rf "$rootfs"
printf '%s\n' "$artifacts"
