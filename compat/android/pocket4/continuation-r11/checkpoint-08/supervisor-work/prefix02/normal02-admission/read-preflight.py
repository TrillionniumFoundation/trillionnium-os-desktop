"""Read one fixed owned build receipt through root stdout, without mutation."""
import argparse
import hashlib
import json
import os
import re
import stat

PATH = "/home/alex/work/pocket4-relay-prefix-r11-source-05-02/normal-plan-02-preflight.json"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--expected-sha256", required=True)
args = parser.parse_args()
if os.getuid() != 0 or os.geteuid() != 0 or not re.fullmatch("[0-9a-f]{64}", args.expected_sha256):
    raise RuntimeError("exact root caller and observed receipt digest required")
fd = os.open(PATH, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
try:
    before = os.fstat(fd)
    if not (stat.S_ISREG(before.st_mode) and before.st_uid == before.st_gid == 0
            and before.st_nlink == 1 and stat.S_IMODE(before.st_mode) == 0o600
            and 0 < before.st_size <= 65536):
        raise RuntimeError("fixed receipt metadata/bound differs")
    raw = bytearray()
    while True:
        part = os.read(fd, min(8192, 65537 - len(raw)))
        if not part:
            break
        raw.extend(part)
        if len(raw) > 65536:
            raise RuntimeError("fixed receipt exceeded bound")
    after = os.fstat(fd)
    fields = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
                            value.st_size, value.st_mtime_ns, value.st_ctime_ns, value.st_nlink)
    digest = hashlib.sha256(raw).hexdigest()
    if fields(before) != fields(after) or len(raw) != before.st_size or digest != args.expected_sha256:
        raise RuntimeError("fixed receipt changed or observed digest differs")
finally:
    os.close(fd)
text = bytes(raw).decode("utf-8", "strict")
json.loads(text)
output = json.dumps({"schema": 1, "path": PATH, "sha256": digest, "bytes": len(raw), "text": text,
                     "root_artifact_read_only": True, "namespace_actions": 0}, ensure_ascii=True)
if len(output.encode()) > 131072:
    raise RuntimeError("receipt stdout envelope exceeded")
print(output, flush=True)
