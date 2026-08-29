#!/bin/bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: build-d1-image.sh \
  --selection manifests/debian-d1.selection.json \
  --resolved-manifest /path/debian-d1.resolved.json \
  --sources-list /path/sources.list \
  --packages packaging/debian/image/d1-packages.txt \
  --overlay packaging/debian/image/rootfs-overlay \
  --output-dir /path/output \
  --build-name build-a
EOF
}

selection=
resolved_manifest=
sources_list=
packages_file=
overlay=
output_dir=
build_name=
while [[ $# -gt 0 ]]; do
  case "$1" in
    --selection) selection=$2; shift 2 ;;
    --resolved-manifest) resolved_manifest=$2; shift 2 ;;
    --sources-list) sources_list=$2; shift 2 ;;
    --packages) packages_file=$2; shift 2 ;;
    --overlay) overlay=$2; shift 2 ;;
    --output-dir) output_dir=$2; shift 2 ;;
    --build-name) build_name=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

for value in selection resolved_manifest sources_list packages_file overlay output_dir build_name; do
  if [[ -z "${!value}" ]]; then
    echo "missing --${value//_/-}" >&2
    exit 2
  fi
done

if [[ $EUID -ne 0 ]]; then
  echo "build-d1-image.sh must run as root" >&2
  exit 1
fi

for command in mmdebstrap python3 jq mke2fs tar chroot rsync sha256sum findmnt; do
  command -v "$command" >/dev/null || {
    echo "required command is missing: $command" >&2
    exit 1
  }
done

selection=$(readlink -f "$selection")
resolved_manifest=$(readlink -f "$resolved_manifest")
sources_list=$(readlink -f "$sources_list")
packages_file=$(readlink -f "$packages_file")
overlay=$(readlink -f "$overlay")
mkdir -p "$output_dir"
output_dir=$(readlink -f "$output_dir")

suite=$(jq -er '.suite' "$selection")
architecture=$(jq -er '.architecture' "$selection")
source_epoch=$(jq -er '.source_date_epoch' "$resolved_manifest")
image_size_mib=$(jq -er '.root_filesystem.size_mib' "$selection")
image_label=$(jq -er '.root_filesystem.label' "$selection")
image_uuid=$(jq -er '.root_filesystem.uuid' "$selection")
resolved_status=$(jq -er '.status' "$resolved_manifest")
if [[ "$resolved_status" != PASS_SIGNED_INRELEASE ]]; then
  echo "resolved manifest has not passed signed InRelease verification" >&2
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

build_dir="$output_dir/$build_name"
rootfs="$build_dir/rootfs"
normalized_rootfs="$build_dir/normalized-rootfs"
logs="$build_dir/logs"
artifacts="$build_dir/artifacts"
rm -rf "$build_dir"
mkdir -p "$rootfs" "$normalized_rootfs" "$logs" "$artifacts"

mapfile -t package_names < <(
  sed -e 's/#.*$//' -e '/^[[:space:]]*$/d' "$packages_file" | LC_ALL=C sort -u
)
required_packages=(passwd)
for package in "${required_packages[@]}"; do
  if ! printf '%s\n' "${package_names[@]}" | grep -qxF "$package"; then
    package_names+=("$package")
  fi
done
include=$(IFS=,; echo "${package_names[*]}")
mapfile -t mirrors < <(sed -e '/^[[:space:]]*$/d' "$sources_list")
if (( ${#mirrors[@]} == 0 )); then
  echo "resolved apt sources list is empty" >&2
  exit 1
fi

export SOURCE_DATE_EPOCH="$source_epoch"
export TZ=UTC
export LC_ALL=C.UTF-8

mmdebstrap_args=(
  --mode=root
  --variant=minbase
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

# The package manager resolved only signed metadata from the snapshot. Keep the
# exact source list in the image for provenance, but QEMU qualification has no
# network device.
install -D -m 0644 "$sources_list" "$rootfs/etc/apt/sources.list"
install -D -m 0644 /dev/null "$rootfs/etc/apt/sources.list.d/.keep"
cat > "$rootfs/etc/apt/apt.conf.d/99trillionnium-snapshot" <<'EOF'
Acquire::Check-Valid-Until "false";
Acquire::Languages "none";
APT::Install-Recommends "false";
APT::Install-Suggests "false";
EOF

# Create the one local D1 desktop identity without a password or login shell.
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

rsync -aHAX --numeric-ids "$overlay/" "$rootfs/"
chmod 0755 "$rootfs/usr/local/libexec/trillionnium-d1-acceptance"
chmod 0644 "$rootfs/etc/systemd/system/"*.service "$rootfs/etc/systemd/system/"*.target
install -d -m 0755 "$rootfs/etc/systemd/system/trillionnium-d1-acceptance.target.wants"
ln -sfn ../trillionnium-d1-wayland.service \
  "$rootfs/etc/systemd/system/trillionnium-d1-acceptance.target.wants/trillionnium-d1-wayland.service"
ln -sfn ../trillionnium-d1-acceptance.service \
  "$rootfs/etc/systemd/system/trillionnium-d1-acceptance.target.wants/trillionnium-d1-acceptance.service"

cat > "$rootfs/etc/fstab" <<EOF
LABEL=$image_label / ext4 defaults 0 1
EOF
: > "$rootfs/etc/machine-id"
rm -f "$rootfs/var/lib/dbus/machine-id"
ln -s ../../../etc/machine-id "$rootfs/var/lib/dbus/machine-id"
rm -f "$rootfs/var/lib/systemd/random-seed"
rm -rf "$rootfs/var/log/journal" "$rootfs/var/tmp/"* "$rootfs/tmp/"*
install -d -m 1777 "$rootfs/tmp" "$rootfs/var/tmp"
install -d -m 0755 "$rootfs/usr/lib/trillionnium-d1" "$rootfs/var/lib/trillionnium-d1"

# Resolve the exact installed package closure before deleting apt metadata.
chroot "$rootfs" dpkg-query -W \
  -f='${binary:Package}\t${Version}\t${Architecture}\n' \
  | LC_ALL=C sort > "$artifacts/package-lock.tsv"
package_lock_sha256=$(sha256sum "$artifacts/package-lock.tsv" | awk '{print $1}')
printf '%s\n' "$package_lock_sha256" > "$rootfs/usr/lib/trillionnium-d1/package-lock.sha256"

selection_sha256=$(sha256sum "$selection" | awk '{print $1}')
resolved_sha256=$(sha256sum "$resolved_manifest" | awk '{print $1}')
image_id="trillionnium-desktop-d1-${build_name}-${selection_sha256:0:12}-${package_lock_sha256:0:12}"
printf '%s\n' "$image_id" > "$rootfs/etc/trillionnium-d1-image-id"

# Force a reproducible initramfs compression mode and rebuild all installed
# initramfs artifacts with SOURCE_DATE_EPOCH in the environment.
cat > "$rootfs/etc/initramfs-tools/conf.d/trillionnium-reproducible" <<'EOF'
COMPRESS=gzip
EOF
chroot "$rootfs" /usr/bin/env \
  SOURCE_DATE_EPOCH="$source_epoch" TZ=UTC LC_ALL=C.UTF-8 \
  update-initramfs -u -k all >"$logs/update-initramfs.log" 2>&1

mapfile -t kernels < <(find "$rootfs/boot" -maxdepth 1 -type f -name 'vmlinuz-*' -printf '%f\n' | LC_ALL=C sort)
mapfile -t initrds < <(find "$rootfs/boot" -maxdepth 1 -type f -name 'initrd.img-*' -printf '%f\n' | LC_ALL=C sort)
if (( ${#kernels[@]} != 1 || ${#initrds[@]} != 1 )); then
  printf 'kernels=%s\ninitrds=%s\n' "${kernels[*]}" "${initrds[*]}" >&2
  echo "D1 requires exactly one kernel and one initrd" >&2
  exit 1
fi
kernel_name=${kernels[0]}
initrd_name=${initrds[0]}
cp --reflink=auto "$rootfs/boot/$kernel_name" "$artifacts/vmlinuz"
cp --reflink=auto "$rootfs/boot/$initrd_name" "$artifacts/initrd.img"

# Remove mutable package caches and normalize every timestamp before creating a
# sorted rootfs archive. The archive is also an independent reproducibility
# checkpoint before ext4 construction.
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
  "schema": "trillionnium.desktop.d1-build-result.v1",
  "status": "PASS_BUILD_ONLY",
  "build_name": "$build_name",
  "image_id": "$image_id",
  "source_date_epoch": $source_epoch,
  "selection_sha256": "$selection_sha256",
  "resolved_manifest_sha256": "$resolved_sha256",
  "package_lock": {
    "path": "package-lock.tsv",
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
  "qemu_booted": False,
  "network_during_acceptance": False
}
pathlib.Path("$artifacts/build-result.json").write_text(
  json.dumps(result, indent=2, sort_keys=True) + "\n"
)
PY

printf '%s\n' "$artifacts"
