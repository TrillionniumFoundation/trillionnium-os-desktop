#!/usr/bin/env python3
import fcntl
import hashlib
import json
import os
from pathlib import Path

scratch = Path(__file__).resolve().parent
work = scratch / "a01-next6-build"
archive = scratch / "trillionnium-os-desktop/support/build/evidence/2026-10-16-ktest-lifecycle/kernel-public"
manifest = work / "kernel/asterinas/kernel/OSDK.toml"
fields = lambda value: {key: getattr(value, key) for key in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")}
record = {"kind": "read_only_followup_of_post_cleanup_public_path", "path": str(manifest),
          "writer_identified": False,
          "prior_observation_note": "The first observation compared whole stat_result values and reported false; its original record and bytes remain unchanged. This separate read explicitly compares content identity fields and retains both values."}
with (work / "support/build/out-kernel.lock").open("a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with manifest.open("rb") as source:
            before = fields(os.fstat(source.fileno()))
            data = source.read()
            after = fields(os.fstat(source.fileno()))
        record.update(present=True, before=before, after=after, content_identity_fields_stable=before == after,
                      sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
                      snapshot="post-boot-followup-manifest.toml")
        (archive / "post-boot-followup-manifest.toml").write_bytes(data)
        current = manifest.lstat()
        record["public_path_still_names_read_inode"] = (current.st_dev, current.st_ino) == (before["st_dev"], before["st_ino"])
    except OSError as error:
        record.update(error=str(error), errno=error.errno)
(archive / "post-boot-followup.json").write_text(json.dumps(record, indent=2) + "\n")
(archive / "post-boot-followup-controller.py").write_bytes(Path(__file__).read_bytes())
print(json.dumps(record, indent=2))
