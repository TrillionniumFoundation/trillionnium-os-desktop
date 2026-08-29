#!/usr/bin/env python3
from pathlib import Path

path = Path("packaging/debian/image/build-d1-image.sh")
text = path.read_text(encoding="utf-8")
old = 'chroot "$rootfs" /usr/bin/systemd-tmpfiles --create\n'
new = '''install -d -m 0555 "$rootfs/proc"
mount --types proc proc "$rootfs/proc"
set +e
chroot "$rootfs" /usr/bin/systemd-tmpfiles --create
tmpfiles_status=$?
set -e
umount "$rootfs/proc"
if (( tmpfiles_status != 0 )); then
  exit "$tmpfiles_status"
fi
'''
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected one target tmpfiles command, found {count}")
path.write_text(text.replace(old, new), encoding="utf-8")
