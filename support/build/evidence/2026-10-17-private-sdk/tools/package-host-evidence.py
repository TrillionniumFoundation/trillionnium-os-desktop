#!/usr/bin/env python3
"""Package original and final host receipts; this does not run a Rust build."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

BASE = Path(__file__).resolve().parent
REPO = BASE.parent / "trillionnium-os-desktop"
REVIEW = BASE.parent / "sdk-root-independent-review"
parser = argparse.ArgumentParser()
parser.add_argument("--code-commit", required=True)
args = parser.parse_args()
code = subprocess.check_output(["git", "-C", str(REPO), "rev-parse", args.code_commit + "^{commit}"]).decode().strip()
ready = json.loads((BASE / "private-sdk-validation-ready-v2.json").read_text())
for name, sha in ready["source_sha256"].items():
    data = subprocess.check_output(["git", "-C", str(REPO), "show", code + ":" + name])
    if hashlib.sha256(data).hexdigest() != sha:
        raise ValueError("published code does not match tested bytes: " + name)
dest = REPO / "support/build/evidence/2026-10-17-private-sdk"
dest.mkdir()
copied = []
symlinks = []

def put(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(raw)
    path.chmod(0o644)
    copied.append({"path": str(path.relative_to(dest)), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})

def copy(path, relative):
    if path.is_symlink() or not path.is_file():
        raise ValueError("expected regular input: " + str(path))
    put(dest / relative, path.read_bytes())

def tree(source, relative):
    for here, directories, files in os.walk(source, followlinks=False):
        here = Path(here)
        directories[:] = [name for name in sorted(directories) if name != "__pycache__"]
        for name in list(directories):
            path = here / name
            if path.is_symlink():
                symlinks.append({"source": str(path), "target": os.readlink(path), "archived": False})
                directories.remove(name)
        for name in sorted(files):
            path = here / name
            if path.is_symlink():
                symlinks.append({"source": str(path), "target": os.readlink(path), "archived": False})
            else:
                copy(path, relative / path.relative_to(source))

for name in ready["source_sha256"]:
    for commit, group in (("09aea79c71dc9f48ba519757078dd8a20f5c8fb3", "baseline"), (code, "final")):
        put(dest / "source" / group / name,
            subprocess.check_output(["git", "-C", str(REPO), "show", commit + ":" + name]))
for name in ("kernel/asterinas/Makefile", "kernel/asterinas/osdk/src/util.rs", "support/build/repro/profile.py"):
    put(dest / "source/upstream-and-profile" / name,
        subprocess.check_output(["git", "-C", str(REPO), "show", "cdf308e751e561328c556ca2ece86056d15809a0:" + name]))
for name in ("private-sdk-validation-ready.json", "private-sdk-validation-ready-v2.json", "private-sdk-optimized-validation.json",
             "baseline-kernel-runner.log", "private-sdk-kernel-runner-isolated.log",
             "private-sdk-kernel-runner-ordinary.log", "private-sdk-kernel-runner-final-isolated.log",
             "private-sdk-kernel-supervisor-isolated.log", "private-sdk-repro-profile-isolated.log",
             "private-sdk-kernel-runner-v2-ordinary.log", "private-sdk-kernel-runner-v2-isolated.log",
             "private-sdk-kernel-runner-v2-isolated-optimized.log", "private-sdk-kernel-supervisor-v2-isolated.log",
             "private-sdk-repro-profile-v2-isolated.log"):
    copy(BASE / name, Path("host-validation") / name)
tree(BASE / "results", Path("make-before/results"))
copy(BASE / "probe.py", Path("make-before/probe.py"))
tree(BASE / "cargo-lookup-results", Path("real-cargo-lookup/cargo-lookup-results"))
tree(BASE / "cargo-relative-lookup-results", Path("real-cargo-lookup/cargo-relative-lookup-results"))
for name in ("probe-cargo-lookup.py", "probe-cargo-relative-home.py"):
    copy(BASE / name, Path("real-cargo-lookup") / name)
tree(BASE / "profile-host-path-results", Path("profile-path-inputs/profile-host-path-results"))
copy(BASE / "profile-host-path-probe.py", Path("profile-path-inputs/profile-host-path-probe.py"))
tree(REVIEW, Path("independent-review"))
copy(BASE / "verify-host-phase.py", Path("verify.py"))
for name in ("package-host-evidence.py", "finalize-host-receipt.py"):
    copy(BASE / name, Path("tools") / name)
report = f"""# Per-invocation SDK isolation: host evidence

Published support code: `{code}`. These four published files match the exact
host-tested source hashes in `host-validation/private-sdk-validation-ready-v2.json`.
The pre-change code is archived at baseline `09aea79c71dc9f48ba519757078dd8a20f5c8fb3`.
The original GNU make probe read `cdf308e751e561328c556ca2ece86056d15809a0`;
its exact upstream Makefile and minimal overlay bytes remain in the bundle.

The prior ordinary path used a global cargo-osdk binary governed by mtime.
OSDK_LOCAL_DEV fixes OSTD's absolute source dependency at SDK compilation.
Actual GNU make with the original upstream Makefile and overlay skipped the
installation for a newer, foreign-root SDK in all three developer actions:
kernel, run_kernel, gdb_server. Each observed make status is 2 and the explicit
fake SDK's mismatch status is 73. The diagnostic phony-only experiment passes
all three host actions, without claiming concurrent global SDK safety.

The final support implementation instead creates a mode700 SDK prefix within
every new evidence directory, executes locked cargo install with --root,
and points both make's binary prerequisite and Cargo's external-command lookup
at that private binary. Shared CARGO_HOME/RUSTUP_HOME keep their values.
The installed binary hash is recorded. The selected Cargo home must be
absolute and contain no parent components; an unset CARGO_HOME uses an
absolute HOME default. No Cargo shim or upstream runtime change was added.

Fixed real Cargo 1.99.0-nightly, commit 3efb1f477e99b42974b982d939fd100303cdf7db,
was invoked with tiny fake external SDK commands in a private Cargo home.
Without an explicit home/bin PATH entry, Cargo selects the global command.
With private/bin followed by the literal home/bin entry, it selects private.
Independent real-Cargo checks found a counterexample for absolute paths
containing '..', including the default HOME path. The final entry rejects
those before a lock, output allocation, or SDK action. Normal, dot, symlink,
trailing slash, repeated slash, and double-leading slash forms select private.
A private command failing 47 propagates 47 without falling back to global.

Final host execution totals are separate: ordinary Python 40/40, Python -I
40/40, Python -I -O 40/40, supervisor -I 9/9 and repro profile -I 32/32.
That is 161 host test executions; only the first three modes rerun the kernel
runner suite. Its full upstream Makefile/overlay fixture checks all three
developer targets, fresh-prefix selection, a global replacement after private
installation, cache identity, ignored inherited SDK prefixes, installation
failure and owned-manifest cleanup. No-guest run/GDB fixture commands remain
rejected as boot evidence. The original lifecycle helpers are unchanged.
The independent final review approves the corrected source and includes
eight actual entry guard checks and seven focused host runner checks.

The first 38-test READY receipt and its exact bytes are retained as superseded,
along with the independent '..' counterexample. Earlier 37-test and baseline
30-test logs are intermediate observations, not final source acceptance.
The independent guard checker's first diagnostic-substring typo and the first
default-home probe's harmless printf newline typo are retained beside the
corrected raw reruns. Expected red reports are not rewritten as passes.

The schema4 descriptor-only probe also shows why identical virtual prefixes
alone do not establish independent-host reproduction: registry absolute paths
contribute to nonlocal producer identities, and then local consumer metadata.
Use the same literal registry/toolchain layout for a future cross-host attempt;
this phase does not claim that reproducing those paths is sufficient.

There is no SDK compilation, kernel compilation, or QEMU execution in this
phase. New full-build/boot acceptance must refer to its own actual producer
commit and logs. Historical first wrong-root SDK binary bytes were not retained;
its existing static path diagnosis cannot be upgraded into binary custody.
Mode700 private directories isolate normal installations between checkouts;
they are not an immutable sandbox against an unrelated same-user writer.
KVM/VMX, default AF_UNIX, independent-host/immutable environment validation,
and A05/A06/A07 native owner functionality remain outside this host fix.

To verify archived integrity without invoking the fixtures:

```sh
python3 -I support/build/evidence/2026-10-17-private-sdk/verify.py
# Also compare the four source files in the local published Git object:
python3 -I support/build/evidence/2026-10-17-private-sdk/verify.py --repo .
```

Fresh host regression commands from the repository root:

```sh
python3 -m unittest discover -s support/build/tests -p test_kernel_runner.py -v
python3 -I -m unittest discover -s support/build/tests -p test_kernel_runner.py -v
python3 -I -O -m unittest discover -s support/build/tests -p test_kernel_runner.py -v
python3 -I -m unittest discover -s support/build/tests -p test_kernel_supervisor.py -v
python3 -I -m unittest discover -s support/build/repro -p test_profile.py -v
```

The raw diagnostic scripts preserve their original absolute scratch paths;
they are provenance records, not path-independent launchers. Symlink fixture
targets are indexed in manifest.json rather than reproduced as archive links.
"""
put(dest / "REPORT.md", report.encode())
manifest = {"schema": "a01-private-sdk-host-evidence/1", "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "published_code_commit": code, "base_commit": ready["base_commit"],
            "scope": "host-only SDK source-root isolation; no actual SDK/kernel/QEMU build",
            "source_sha256": ready["source_sha256"], "final_host_execution_count": 161,
            "final_modes": {"ordinary": 40, "isolated": 40, "isolated_optimized": 40, "supervisor_isolated": 9, "repro_profile_isolated": 32},
            "superseded_receipt": ready["supersedes"], "symlink_fixture_index": symlinks,
            "files_copied_before_manifest": copied}
put(dest / "manifest.json", (json.dumps(manifest, indent=2) + "\n").encode())
payload = sorted(path for path in dest.rglob("*") if path.is_file())
with (dest / "SHA256SUMS").open("x") as output:
    for path in payload:
        output.write(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + str(path.relative_to(dest)) + "\n")
print(json.dumps({"phase": str(dest), "files": len(payload), "bytes": sum(path.stat().st_size for path in payload),
                  "sha256sums": hashlib.sha256((dest / "SHA256SUMS").read_bytes()).hexdigest()}))
