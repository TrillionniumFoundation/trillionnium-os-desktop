"""Create one pinned normal plan and perform the existing read-only check only."""
import base64
import datetime
import hashlib
import json
import os
import stat
import subprocess
import traceback

CFG = __CFG__
ROOT = "/home/alex/work/pocket4-relay-prefix-r11-source-05-02"
PRIOR = "/home/alex/work/pocket4-relay-prefix-r11-source-05-01"
PRIOR_SHA = "1e70d9df93309ff5be991f0a20e4b5b4493e57a0b64fcc3881075e652a5ae712"
BASE = "/home/alex/work/pocket4-relay-prefix-r11-owned"
PLAN_NAME = "normal-plan-02.json"
REPORT_NAME = "normal-plan-02-preflight.json"
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1"}

def need(value, message):
    if not value:
        raise RuntimeError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def metadata(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns)

def read_file(directory, name, maximum):
    need(name and "/" not in name and name not in (".", ".."), "single filename required")
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == before.st_gid == 0
             and before.st_nlink == 1 and before.st_mode & 0o6022 == 0
             and 0 < before.st_size <= maximum, "source metadata differs: " + name)
        raw = bytearray()
        while True:
            part = os.read(fd, min(8192, maximum + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
            need(len(raw) <= maximum, "source grew: " + name)
        need(metadata(before) == metadata(os.fstat(fd)) and len(raw) == before.st_size,
             "source changed: " + name)
        return bytes(raw), before
    finally:
        os.close(fd)

def private_directory(path, parent=None):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                 dir_fd=parent)
    s = os.fstat(fd)
    if not (s.st_uid == s.st_gid == 0 and stat.S_ISDIR(s.st_mode)
            and stat.S_IMODE(s.st_mode) == 0o700):
        os.close(fd)
        raise RuntimeError("root-private directory differs: " + path)
    return fd

def create_bytes(directory, name, raw):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o600, dir_fd=directory)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.fsync(directory)

def verify_inputs(root, source, prior, binary, base):
    raw, _ = read_file(root, "build-result.json", 65536)
    need(sha(raw) == CFG["build_result_sha256"], "actual matching build receipt differs")
    receipt = json.loads(raw)
    need(receipt["success"] is True and receipt["inputs_before"] == receipt["inputs_after"]
         == CFG["inputs"] and receipt["source_freeze_manifest_sha256"] == CFG["freeze_manifest_sha256"],
         "matching source closure differs")
    need(receipt["python_tests_passed"] == {"test_prefix_control.py": 16, "test_prefix_coordinator.py": 27}
         and receipt["native_probe_reuse_verified"] is True
         and receipt["new_native_build_performed"] is False
         and receipt["new_native_controls_executed"] == 0
         and receipt["prior_native_ordinary_controls_referenced"] == 6
         and receipt["prior_build_result_sha256"] == PRIOR_SHA, "matching controls not complete")
    for key in ("namespace_actions", "network_actions", "systemd_unit_actions", "Android_operations", "Main_actions"):
        need(receipt[key] == 0, "matching build had unexpected actions")
    need(receipt["actual_Rust_Owner_executed"] is False and receipt["runtime_prefix_qualified"] is False
         and receipt["production_ready"] is False, "matching build scope differs")
    for name, expected in CFG["inputs"].items():
        data, _ = read_file(source, name, 65536)
        need({"bytes": len(data), "sha256": sha(data)} == expected, "frozen input differs: " + name)
    old_raw, _ = read_file(prior, "build-result.json", 65536)
    need(sha(old_raw) == PRIOR_SHA, "original native build receipt differs")
    previous_build = json.loads(old_raw)
    need(previous_build["success"] is True
         and previous_build["native_ordinary_controls_passed"] == 6, "original native controls incomplete")
    data, s = read_file(binary, "prefix-probe", 65536)
    pin = receipt["probe_before"]
    need(pin == receipt["probe_after"] == previous_build["probe"], "reused probe receipt differs")
    need(pin["path"] == PRIOR + "/bin/prefix-probe" and pin["sha256"] == CFG["probe_sha256"]
         and len(data) == pin["bytes"] and sha(data) == pin["sha256"]
         and [s.st_dev, s.st_ino] == [pin["device"], pin["inode"]]
         and stat.S_IMODE(s.st_mode) == pin["mode"] == 0o700, "actual compiled probe differs")
    held = os.fstat(base)
    previous = receipt["owned_attempt_base"]
    need(previous["path"] == BASE and [held.st_dev, held.st_ino] == [previous["device"], previous["inode"]],
         "original owned attempt base differs")
    for path, descriptor in ((ROOT, root), (PRIOR, prior), (BASE, base)):
        current = os.stat(path, follow_symlinks=False)
        held = os.fstat(descriptor)
        need([current.st_dev, current.st_ino] == [held.st_dev, held.st_ino], "held directory path was replaced")
    return {"all_six_inputs_exact": True, "probe_sha256": pin["sha256"],
            "original_native_build_result_sha256": PRIOR_SHA,
            "build_result_sha256": CFG["build_result_sha256"], "original_root_and_base_held": True}

need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0, "exact root caller required")
os.umask(0o077)
handles = []
report = {"schema": 1, "scope": "CREATE_ONE_PLAN_AND_READ_ONLY_CHECK_NO_RUNTIME",
          "success": False, "plan_sha256": CFG["plan_sha256"], "runtime_started": False,
          "namespace_actions": 0, "Android_operations": 0, "Main_actions": 0,
          "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
try:
    root = private_directory(ROOT); handles.append(root)
    source = private_directory("source", root); handles.append(source)
    prior = private_directory(PRIOR); handles.append(prior)
    binary = private_directory("bin", prior); handles.append(binary)
    base = private_directory(BASE); handles.append(base)
    try:
        report["inputs_before"] = verify_inputs(root, source, prior, binary, base)
        plan = base64.b64decode(CFG["plan_base64"], validate=True)
        need(sha(plan) == CFG["plan_sha256"], "embedded external plan differs")
        value = json.loads(plan)
        need(value["mode"] == "normal" and value["nonce"] == CFG["nonce"] and value["predecessor"] is None
             and value["sources"]["probe"]["sha256"] == CFG["probe_sha256"], "not this new normal plan")
        create_bytes(root, PLAN_NAME, plan)
        report["plan_created_once"] = True
        argv = ["/usr/bin/python3", "-I", "-B", ROOT + "/source/prefix_coordinator.py", "--check",
                "--plan", ROOT + "/" + PLAN_NAME, "--plan-sha256", CFG["plan_sha256"]]
        report["argv"] = argv
        result = subprocess.run(argv, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
        need(len(result.stdout) <= 16384 and len(result.stderr) <= 16384, "read-only check output exceeded")
        report.update(returncode=result.returncode, stdout=result.stdout.decode("utf-8", "strict"),
                      stderr=result.stderr.decode("utf-8", "strict"))
        need(result.returncode == 0, "read-only normal plan check failed")
        checked = json.loads(report["stdout"])
        need(checked["read_only_plan_checked"] is True and checked["nonce"] == CFG["nonce"]
             and checked["runtime_started"] is False and checked["Android_operations"] == 0,
             "read-only check result differs")
        report["inputs_after"] = verify_inputs(root, source, prior, binary, base)
        need(read_file(root, PLAN_NAME, 65536)[0] == plan, "external plan changed during check")
        report["success"] = True
    except BaseException as error:
        report["error"] = repr(error)
        report["traceback"] = traceback.format_exc()
    report["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    raw = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    need(len(raw) <= 65536, "read-only preflight receipt exceeded")
    create_bytes(root, REPORT_NAME, raw)
    print(json.dumps({"success": report["success"], "path": ROOT + "/" + REPORT_NAME,
                      "sha256": sha(raw), "bytes": len(raw), "plan_sha256": CFG["plan_sha256"],
                      "runtime_started": False, "namespace_actions": 0, "Android_operations": 0}), flush=True)
finally:
    for fd in reversed(handles):
        os.close(fd)
raise SystemExit(0 if report["success"] else 1)
