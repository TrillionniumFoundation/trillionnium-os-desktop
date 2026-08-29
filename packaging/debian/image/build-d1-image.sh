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

for command in mmdebstrap python3 jq mke2fs tar chroot rsync sha256sum \
  systemd-sysusers systemd-tmpfiles cmp diff readlink; do
  command -v "$command" >/dev/null || {
    echo "required command is missing: $command" >&2
    exit 1
  }
done

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(readlink -f "$script_dir/../../..")
selection=$(readlink -f "$selection")
prepared_manifest=$(readlink -f "$prepared_manifest")
sources_list=$(readlink -f "$sources_list")
exact_packages=$(readlink -f "$exact_packages")
expected_package_lock=$(readlink -f "$expected_package_lock")
agent_portd_binary=$(readlink -f "$agent_portd_binary")
agent_fixture_binary=$(readlink -f "$agent_fixture_binary")
overlay=$(readlink -f "$overlay")
mkdir -p "$output_dir"
output_dir=$(readlink -f "$output_dir")

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
host_keyring=$(jq -er '.archive_keyring.path' "$prepared_manifest")
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
[[ -f "$host_keyring" && ! -L "$host_keyring" ]] || {
  echo "prepared Debian archive keyring is missing or unsafe" >&2
  exit 1
}

build_dir="$output_dir/$build_name"
rootfs="$build_dir/rootfs"
normalized_rootfs="$build_dir/normalized-rootfs"
logs="$build_dir/logs"
artifacts="$build_dir/artifacts"
rm -rf "$build_dir"
mkdir -p "$rootfs" "$normalized_rootfs" "$logs" "$artifacts"

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

rsync -aHAX --numeric-ids "$overlay/" "$rootfs/"
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

systemd-sysusers --root="$rootfs"
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
systemd-tmpfiles --root="$rootfs" --create
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

tar --numeric-owner --xattrs --acls --selinux \
  -xf "$artifacts/rootfs.tar" -C "$normalized_rootfs"
find "$normalized_rootfs" -xdev -print0 \
  | LC_ALL=C sort -z \
  | xargs -0r touch --no-dereference --date="@$source_epoch"

image="$artifacts/trillionnium-d1.ext4"
truncate -s "${image_size_mib}M" "$image"
export E2FSPROGS_FAKE_TIME="$source_epoch"
mke2fs \
  -F \
  -q \
  -t ext4 \
  -b 4096 \
  -I 256 \
  -m 0 \
  -L "$image_label" \
  -U "$image_uuid" \
  -E "root_owner=0:0,lazy_itable_init=0,lazy_journal_init=0,hash_seed=$image_uuid" \
  -d "$normalized_rootfs" \
  "$image" >"$logs/mke2fs.log" 2>&1
unset E2FSPROGS_FAKE_TIME

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

rm -rf "$rootfs" "$normalized_rootfs"
printf '%s\n' "$artifacts"
