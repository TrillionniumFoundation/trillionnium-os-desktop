#!/usr/bin/python3
"""Actual installed root probe; no health, bootloader or release permission."""
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

root = Path("/state/g6a")
receipt = json.loads((root / "selected-root.json").read_bytes())
control = json.loads((root / "case-control.json").read_bytes())
mounts = Path("/proc/self/mountinfo").read_text().splitlines()
rows = [row.split() for row in mounts if row.split()[4] == "/"]
assert len(rows) == 1
row = rows[0]
device = os.stat("/dev/mapper/hepta-g6a-root").st_rdev
assert row[2] == f"{os.major(device)}:{os.minor(device)}" and "ro" in row[5].split(",")
assert row[row.index("-") + 1] == "ext4"
assert Path("/sys/dev/block/" + row[2] + "/ro").read_text().strip() == "1"
assert Path("/etc/g6a-slot").read_text().strip() == receipt["slot"]
assert Path("/proc/sys/kernel/random/boot_id").read_text().strip() == receipt["boot_id"]
try:
    os.open("/etc/g6a-slot", os.O_WRONLY | os.O_CLOEXEC)
except OSError as error:
    assert error.errno == errno.EROFS
else:
    raise RuntimeError("root_write_was_allowed")
receipt.update({"actual_root_device": row[2], "actual_root_mount_readonly": True, "actual_mapping_readonly": True, "root_write_refused": True, "measured_health_qualified": False, "commit_performed": False, "firmware_authenticated": False, "rollback_anchor_protected": False})
destination = root / ("boot-%02d.json" % receipt["boot_number"])
fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
try:
    payload = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    assert os.write(fd, payload) == len(payload)
    os.fsync(fd)
finally:
    os.close(fd)
print("G6A_ROOT_OBSERVED " + payload.decode(), flush=True)
if receipt["slot"] == "B" and control["target_failure"]:
    print("G6A_TARGET_FAILURE", flush=True)
    sys.exit(42)
