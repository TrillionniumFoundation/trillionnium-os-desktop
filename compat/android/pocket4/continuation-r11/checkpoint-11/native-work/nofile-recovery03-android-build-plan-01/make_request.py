#!/usr/bin/env python3
"""Create a fixed Android build-only request; never dispatch or install."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
SOURCES = HERE.parent / "nofile-recovery03-android-source-01"
ROOT = "/home/alex/work/pocket4-nofile-owner-recovery03-android-build-01-20261105"
KEY = "pocket4-nofile-owner-recovery03-matching-Android-build-01-20261105"
CONTROL_SHA = "27f88862a44becb691393680aab819258c7e54adda8832c78dff9d016b9f04b8"
ARM_PINS_SHA = "21a644c1fd29fcaa0ff4368a4c39926168db8adff5880290f86af9fe18baf98b"
BUILDER_SHA = "6f07583856f660eba100589f43114ff6b423659256363a9cf3883a334d6b4c81"

def pin(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

def write(path, raw):
    if isinstance(raw, str):
        raw = raw.encode()
    with path.open("xb") as stream:
        stream.write(raw)
    return pin(raw)

def freeze(output):
    raw = (HERE / "arm-source-pins.json").read_bytes()
    assert pin(raw)["sha256"] == ARM_PINS_SHA
    arms = json.loads(raw)
    files = {}
    for arm, rows in arms.items():
        for name, wanted in rows.items():
            data = (SOURCES / arm / name).read_bytes()
            assert pin(data) == wanted, (arm, name)
            files[arm + "/" + name] = data.decode()
    for name, path, expected in (
        ("build_android.py", HERE / "build_android.py", CONTROL_SHA),
        ("arm-source-pins.json", HERE / "arm-source-pins.json", ARM_PINS_SHA),
        ("build-r3.py", SOURCES / "references/build-r3.py", BUILDER_SHA),
    ):
        data = path.read_bytes()
        assert pin(data)["sha256"] == expected
        files["control-source/" + name] = data.decode()
    assert len(files) == 47
    pins = {name: pin(text.encode()) for name, text in files.items()}
    stage = '''import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
ROOT=Path(%r)
EXPECTED=%r
def main(packet):
    if os.getuid()!=1000 or os.geteuid()!=1000:raise RuntimeError('ordinary operator UID1000 required')
    if set(packet)!=set(EXPECTED):raise RuntimeError('source packet member set differs')
    for name,text in packet.items():
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or str(path)!=name:raise RuntimeError('source path escapes owned root')
        raw=text.encode()
        if len(raw)!=EXPECTED[name]['bytes'] or hashlib.sha256(raw).hexdigest()!=EXPECTED[name]['sha256']:
            raise RuntimeError('fixed source bytes differ: '+name)
    for parent in [ROOT.parent,*ROOT.parent.parents]:
        if not stat.S_ISDIR(parent.lstat().st_mode):raise RuntimeError('owned root parent alias')
    os.umask(0o077);ROOT.mkdir(mode=0o700)
    for name,text in packet.items():
        path=ROOT/name;path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
        with os.fdopen(fd,'wb') as stream:
            stream.write(text.encode());stream.flush();os.fsync(stream.fileno())
    os.execve('/usr/bin/python3',['/usr/bin/python3','-I','-B',str(ROOT/'control-source/build_android.py'),'--execute-once'],
              {'PATH':'/usr/bin:/bin','HOME':'/home/alex','LANG':'C','LC_ALL':'C'})
''' % (ROOT, pins)
    entry = stage + "\nPACKET=json.loads(" + repr(json.dumps(files, sort_keys=True)) + ")\nmain(PACKET)\n"
    ast.parse(entry)
    assert len(entry.encode()) <= 1024 * 1024
    request = {"host": "pocket4", "executable": "/usr/bin/python3", "args": ["-I", "-B", "-"],
               "stdin": entry, "cwd": "/", "cpu_quota_percent": 100,
               "memory_max_bytes": 1073741824, "nice": 15, "timeout_seconds": 600,
               "idempotency_key": KEY}
    output.mkdir()
    records = {}
    records["stage.py"] = write(output / "stage.py", stage)
    records["exact-request.json"] = write(output / "exact-request.json", json.dumps(request, indent=2) + "\n")
    records["packet-pins.json"] = write(output / "packet-pins.json", json.dumps(pins, indent=2) + "\n")
    result = subprocess.run(["/usr/bin/python3", "-I", "-B", str(HERE / "build_android.py")],
                            capture_output=True, text=True)
    assert result.returncode == 0 and not result.stderr and json.loads(result.stdout)["mode"] == "PLAN"
    records["LOCAL_VALIDATION.json"] = write(output / "LOCAL_VALIDATION.json", json.dumps({
        "AST_valid": True, "packet_files": len(files), "all_source_bytes_match": True,
        "default_PLAN": json.loads(result.stdout), "remote_actions": 0,
        "actual_NDK_compilation": False, "actual_Android_execution": False}, indent=2) + "\n")
    records["PLAN.json"] = write(output / "PLAN.json", json.dumps({
        "scope": "two matching owned APKs, no install or execution",
        "pinned_R3_builder_unchanged": True,
        "expected_source_files_per_arm": 22,
        "native_harness_SHA": "62c53acf7a58054a3ff4ea83e051a5630405955fe79cc59dcccc99b37e4264ef",
        "host_26_actual_receipt_SHA": "b0a03b1b95e3292131105dcb22fd59f4a767e63017197e29f4482036976a4ac2",
        "package": "local.pocket4.fdownerprobe.r11",
        "ABI": "x86_64",
        "same_package_two_APKs_require_separate_absent_install_run_remove_cycles": True,
        "case_assertions_unchanged": True,
        "actual_Bionic_raw_libc_and_worker_closure_pending": True,
        "root_manual_actual_entry_read_required_before_runtime": True,
        "Main_actions": 0, "all_apps_ready": False}, indent=2) + "\n")
    write(output / "SOURCE_PINS.json", json.dumps({
        "schema": 1, "files": records, "state": "FROZEN_NOT_DISPATCHED",
        "controller_sha256": CONTROL_SHA, "arm_source_pins_sha256": ARM_PINS_SHA,
        "builder_sha256": BUILDER_SHA}, indent=2) + "\n")
    print(json.dumps({"request": records["exact-request.json"], "stable_key": KEY,
                      "root": str(output)}, indent=2))

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is None:
        print(json.dumps({"mode": "PLAN", "remote_actions": 0, "Android_install_or_execution": False}))
    else:
        freeze(args.output)
