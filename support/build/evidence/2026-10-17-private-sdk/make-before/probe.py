#!/usr/bin/env python3
"""Host-only GNU make regression for a global SDK's compile-time source root.

No Rust compiler, real SDK, QEMU or system install is used. The upstream
Makefile and overlay bytes are fetched from an existing local Git object.
Only cargo is modeled: install records its cwd and osdk reads that binding.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

BASE = Path(__file__).resolve().parent
REPO = BASE.parent / "trillionnium-os-desktop"
COMMIT = "cdf308e751e561328c556ca2ece86056d15809a0"
ROOT = BASE / "results"
ROOT.mkdir()
source = {}
for name in ("kernel/asterinas/Makefile", "support/build/minimal.mk", "kernel/asterinas/osdk/src/util.rs"):
    raw = subprocess.check_output(["git", "-C", str(REPO), "show", COMMIT + ":" + name])
    (ROOT / name.replace("/", "__")).write_bytes(raw)
    source[name] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

FAKE_CARGO = '''#!/usr/bin/env python3
import json, os, pathlib, sys
root = pathlib.Path.cwd()
sdk = pathlib.Path(os.environ["SDK_FIXTURE_BINARY"])
log = pathlib.Path(os.environ["SDK_FIXTURE_LOG"])
args = sys.argv[1:]
if args[:1] == ["install"]:
    assert args == ["install", "--locked", "cargo-osdk", "--path", "osdk"]
    assert os.environ.get("OSDK_LOCAL_DEV") == "1"
    bound = str(root.resolve())
    sdk.write_text(bound)
    record = {"operation": "install", "cwd": str(root), "bound": bound, "argv": args}
    status = 0
elif args[:1] == ["osdk"]:
    bound = sdk.read_text()
    expected = str(root.parent.resolve())
    status = 0 if bound == expected else 73
    record = {"operation": "osdk", "cwd": str(root), "bound": bound, "expected": expected,
              "runtime_osdk_local_dev": os.environ.get("OSDK_LOCAL_DEV"), "argv": args,
              "returncode": status}
else:
    raise SystemExit("unexpected fixture cargo call")
with log.open("a") as output:
    output.write(json.dumps(record, sort_keys=True) + "\\n")
print(json.dumps(record, sort_keys=True))
raise SystemExit(status)
'''
tools = ROOT / "fake-bin"
tools.mkdir()
(tools / "cargo").write_text(FAKE_CARGO)
(tools / "cargo").chmod(0o755)
report = {"schema": "host-only-sdk-root-mtime-probe/1", "source_commit": COMMIT,
          "source_files": source, "make": subprocess.check_output(["make", "--version"]).decode(),
          "scope": "GNU make actual upstream+overlay recipes; cargo is an explicit host fixture; no Rust/SDK/QEMU build", "cases": []}
for variant in ("original", "phony_sdk_prerequisite"):
    for target in ("kernel", "run_kernel", "gdb_server"):
        case = ROOT / (variant + "-" + target)
        case.mkdir()
        old = case / "old-root"
        old.mkdir()
        new = case / "new-root"
        new.mkdir()
        (new / "kernel").mkdir()
        (new / "osdk/src").mkdir(parents=True)
        for name in ("Cargo.toml", "Cargo.lock", "src/lib.rs"):
            path = new / "osdk" / name
            path.write_text("host fixture only\n")
            os.utime(path, (1_600_000_000, 1_600_000_000))
        makefile = (ROOT / "kernel__asterinas__Makefile").read_bytes()
        overlay = (ROOT / "support__build__minimal.mk").read_bytes()
        (new / "Makefile").write_bytes(makefile)
        if variant == "phony_sdk_prerequisite":
            overlay += b"\n# Host experiment: force source-root SDK preparation at every action.\n.PHONY: $(CARGO_OSDK)\n"
        (new / "minimal.mk").write_bytes(overlay)
        initrd = case / "initramfs"
        initrd.write_bytes(b"host fixture")
        sdk = case / "cargo-osdk"
        sdk.write_text(str(old))
        os.utime(sdk, (1_600_000_100, 1_600_000_100))
        env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ["PATH"],
                   SDK_FIXTURE_BINARY=str(sdk), SDK_FIXTURE_LOG=str(case / "cargo.jsonl"),
                   OSDK_LOCAL_DEV="1")
        for key in ("MAKEFLAGS", "MFLAGS", "GNUMAKEFLAGS", "MAKEFILES", "MAKEOVERRIDES", "MAKELEVEL"):
            env.pop(key, None)
        command = ["make", "--no-print-directory", "-C", str(new), "-f", "Makefile", "-f", "minimal.mk", target,
                   "CARGO_OSDK=" + str(sdk), "A01_INITRAMFS=" + str(initrd), "VDSO_LIBRARY_DIR=host-fixture",
                   "A01_QEMU_WRAPPER=host-fixture", "A01_GDB_PORT=1234", "TARGET_ARCH=x86_64", "SMP=1", "MEM=512M",
                   "ENABLE_KVM=0", "BOOT_PROTOCOL=multiboot", "INITRAMFS=on", "AUTO_TEST=none"]
        result = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (case / "stdout.log").write_bytes(result.stdout)
        calls = [json.loads(line) for line in (case / "cargo.jsonl").read_text().splitlines()]
        expected = 2 if variant == "original" else 0
        assert result.returncode == expected, result.stdout.decode()
        assert [item["operation"] for item in calls] == (["osdk"] if variant == "original" else ["install", "osdk"])
        assert calls[-1]["returncode"] == (73 if variant == "original" else 0)
        report["cases"].append({"variant": variant, "target": target, "command": command,
                                "returncode": result.returncode, "cargo_calls": calls,
                                "overlay_sha256": hashlib.sha256(overlay).hexdigest()})
(ROOT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"cases": len(report["cases"]), "all_expectations_met": True, "scope": report["scope"]}))
