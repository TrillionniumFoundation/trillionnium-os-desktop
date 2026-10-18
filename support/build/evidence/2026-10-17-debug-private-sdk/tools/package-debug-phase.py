#!/usr/bin/env python3
"""Archive actual host-only debug SDK regression fixtures and source bindings."""
import argparse
import datetime
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

BASE = Path(__file__).resolve().parent
REPO = BASE.parent / "trillionnium-os-desktop"
REVIEW = BASE.parent / "sdk-debug-independent-review"
parser = argparse.ArgumentParser()
parser.add_argument("--code-commit", required=True)
args = parser.parse_args()
code = subprocess.check_output(["git", "-C", str(REPO), "rev-parse", args.code_commit + "^{commit}"]).decode().strip()
ready = json.loads((BASE / "source-validation-ready.json").read_text())
for name, sha in ready["source_sha256"].items():
    content = subprocess.check_output(["git", "-C", str(REPO), "show", code + ":" + name])
    if hashlib.sha256(content).hexdigest() != sha:
        raise ValueError("published source differs from tested bytes: " + name)
phase = REPO / "support/build/evidence/2026-10-17-debug-private-sdk"
phase.mkdir()

def put(name, content):
    path = phase / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(content)

for name in ready["source_sha256"]:
    put(Path("source/final") / name, subprocess.check_output(["git", "-C", str(REPO), "show", code + ":" + name]))
put("source/baseline/run.py", (BASE / "baseline/run.py").read_bytes())
for name in ("source-validation-ready.json", "before-I.log", "after-I.log", "after-I-O.log"):
    put(Path("logs") / name, (BASE / name).read_bytes())
for name in ("review.json", "result.json", "old-I.log", "old-IO.log", "new-I.log", "new-IO.log"):
    put(Path("independent-review") / name, (REVIEW / "final" / name).read_bytes())
index = []
symlinks = []
tarbuffer = io.BytesIO()
with gzip.GzipFile(fileobj=tarbuffer, mode="wb", filename="", mtime=0) as compressed:
    with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
        inputs = []
        for source, prefix in ((BASE / "baseline", "owner/baseline"), (BASE / "before-I", "owner/before-I"),
                               (BASE / "after-I", "owner/after-I"), (BASE / "after-I-O", "owner/after-I-O"),
                               (REVIEW / "baseline", "independent/baseline"), (REVIEW / "final", "independent/final")):
            for here, directories, filenames in os.walk(source, followlinks=False):
                here = Path(here)
                directories[:] = [name for name in sorted(directories) if name != "__pycache__"]
                for name in list(directories):
                    path = here / name
                    if path.is_symlink():
                        symlinks.append({"source": str(path), "target": os.readlink(path)})
                        directories.remove(name)
                for name in sorted(filenames):
                    path = here / name
                    if path.is_symlink():
                        symlinks.append({"source": str(path), "target": os.readlink(path)})
                    else:
                        inputs.append((path, str(Path(prefix) / path.relative_to(source))))
        for path, name in sorted(inputs, key=lambda pair: pair[1]):
            raw = path.read_bytes()
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            member.mode = 0o644
            member.mtime = 0
            archive.addfile(member, io.BytesIO(raw))
            index.append({"name": name, "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
raw = tarbuffer.getvalue()
put("host-fixtures.tar.gz", raw)
put("host-fixtures.index.json", (json.dumps({"schema": "a01-debug-sdk-host-fixtures/1", "regular_files": index,
                                            "symlinks_indexed_not_archived": symlinks}, indent=2) + "\n").encode())
put("verify.py", (BASE / "verify-debug-phase.py").read_bytes())
put("tools/package-debug-phase.py", Path(__file__).read_bytes())
report = f"""# Debug runner records its own private SDK

Support code `{code}` fixes a downstream regression after the ordinary build
entry moved OSDK installation to each run's private prefix. The previous debug
runner still observed CARGO_HOME/bin/cargo-osdk after readiness. A missing global
SDK incorrectly failed the debug run; an unrelated global SDK was recorded as
the current build. With a foreign global SDK present it also ignored a missing
private SDK or a bad private installation receipt.

The actual public debug CLI, with explicitly substituted host-only build/GDB/boot
work, reproduced all four pre-fix failures. The new helper observes only
boot/osdk/bin/cargo-osdk, reads the regular executable through one descriptor
with NOFOLLOW/NONBLOCK, checks unchanged descriptor and pathname identities,
and verifies the exact SHA256/path against boot/osdk/cargo-osdk.sha256.
The record includes installation root, source directory, Cargo.toml and
Cargo.lock hashes. Shared Cargo home contents are never a fallback.

The complete debug host suite passed 16/16 under -I and 16/16 under -I -O,
including existing cancellation/session ownership and encoded-flag entry tests.
The independent reviewer separately ran the same four focused public-CLI
fixtures in both modes: four expected failures with the old source and
four passes with the corrected source in each mode. These focused checks repeat
a subset of the complete suite and are reported separately.

This phase executes no real SDK installation, Rust compilation, GDB session,
or QEMU guest. Fixture result.json files deliberately contain host substitutes;
their passed fields do not establish a guest or entry breakpoint result.
The SDK observation describes bytes at observation time, not immutable custody
of bytes already executed. Earlier genuine kernel/debug evidence retains its
own original source and binary identities. Neither kernel.sh, minimal.mk,
kernel runtime code, nor the prior private-sdk evidence phase was changed.

Complete fixture projects, source snapshots, command records, raw observations
and intermediate failures are in host-fixtures.tar.gz. The index binds each
regular member; the offline verifier reads the archive in memory without
extracting or executing its contents. Baseline and final source bytes and raw
test/review logs are also retained in readable form.

```sh
python3 -I support/build/evidence/2026-10-17-debug-private-sdk/verify.py --repo .
python3 -I -O support/build/evidence/2026-10-17-debug-private-sdk/verify.py --repo .
```
"""
put("REPORT.md", report.encode())
manifest = {"schema": "a01-debug-private-sdk-evidence/1", "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "published_code_commit": code, "scope": ready["scope"], "source_sha256": ready["source_sha256"],
            "host_complete_suite": {"isolated": 16, "isolated_optimized": 16},
            "independent_focused_subset_repeats": {"new_each_mode_passed": 4, "old_each_mode_expected_failures": 4},
            "archive": {"name": "host-fixtures.tar.gz", "sha256": hashlib.sha256(raw).hexdigest(),
                        "size": len(raw), "regular_members": len(index)},
            "actual_sdk_compilation": False, "actual_kernel_compilation": False, "actual_gdb_or_qemu_execution": False,
            "immutable_executed_sdk_custody_claimed": False}
put("manifest.json", (json.dumps(manifest, indent=2) + "\n").encode())
payload = sorted(path for path in phase.rglob("*") if path.is_file())
put("SHA256SUMS", "".join(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + str(path.relative_to(phase)) + "\n"
                          for path in payload).encode())
print(json.dumps({"phase": str(phase), "payload_files": len(payload), "regular_archive_members": len(index),
                  "total_files": len(payload) + 1, "total_bytes": sum(path.stat().st_size for path in phase.rglob("*") if path.is_file()),
                  "sha256sums_sha256": hashlib.sha256((phase / "SHA256SUMS").read_bytes()).hexdigest()}))
