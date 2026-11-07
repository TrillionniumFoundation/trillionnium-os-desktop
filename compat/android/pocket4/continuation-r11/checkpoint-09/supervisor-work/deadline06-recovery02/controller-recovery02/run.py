from pathlib import Path
import datetime
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import time
import traceback

CONTROL_REVISION = "producer06-deadline-recovery02"
BASE = Path("/home/alex/work/pocket4-supervisor-lmkd-lifecycle-r11-work-01")
SOURCE = BASE / "candidate"
OUT = Path("/home/alex/work/pocket4-supervisor-lmkd-deadline-r11-build-06-recovery02")
CANDIDATE = OUT / "candidate"
TARGET = OUT / "target"
CARGO = "/home/alex/.cargo/bin/cargo"
PRIOR_RECEIPT = BASE / "integration-producer-build-05/build-result.json"
PRIOR_RECEIPT_SHA = "1623811c108a7cac8af3460d828c063ed9e7064519d2d4e41d70bce4ab25e64c"
PRIOR_INVENTORY_SHA = "a603f4f2eeeb44ccf0063ddf44ee9be4986567b6befb9cc1799fd9f6664481a5"
ORIGINAL_DIFF_SHA = "0d9bd3796dee86faa1963791314d9be26cf0c55beaba57529a572a3bbd648f3a"
EXACT_OVERLAY = {
    "runtime/droidloom-pressure-relay/src/lib.rs":
        (44518, "ec0226b0025c6ffbff1b25aea61136437b061eaafa27d5b535dea288056338fa"),
    "runtime/droidloom-pressure-relay/src/lifecycle_bootstrap.rs":
        (53648, "5e96483abd45383f4e4cd233ee7d7441aa5259d0c6b0d7d1fc934f81e9a36732"),
    "runtime/droidloom-supervisor/src/relay_lifecycle/owner.rs":
        (37747, "5cceac40d2fff4f3a9234a0ecef9b04a2d0b6626f15e561f3f613472108fd715"),
}
BINARIES = ["droidloomd", "droidloom-supervisor", "droidloom-psi-owner", "owned-ipc-controls"]
EXPECTED_TEST_TARGETS = {
    ("droidloom_pressure_relay", "lib"),
    ("droidloom_supervisor", "lib"),
    ("droidloomd", "bin"),
    ("droidloom-supervisor", "bin"),
    ("droidloom-psi-owner", "bin"),
    ("owned-ipc-controls", "bin"),
}
SOURCE_LIMIT = 128 * 1024 * 1024
LOG_LIMIT = 8 * 1024 * 1024

def need(condition, reason):
    if not condition:
        raise RuntimeError(reason)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")

def stamp(st):
    return [st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns]

def read_regular(path, maximum):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_size <= maximum,
             "not a bounded regular file: " + str(path))
        parts = []
        length = 0
        while True:
            block = os.read(fd, min(65536, maximum + 1 - length))
            if not block:
                break
            parts.append(block)
            length += len(block)
            need(length <= maximum, "file exceeded read bound: " + str(path))
        after = os.fstat(fd)
        need(stamp(before) == stamp(after) and length == before.st_size,
             "file changed during held read: " + str(path))
        return b"".join(parts)
    finally:
        os.close(fd)

def file_pin(path, maximum=256 * 1024 * 1024, require_elf=False):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_size <= maximum,
             "artifact is not a bounded regular file: " + str(path))
        h = hashlib.sha256()
        size = 0
        first = b""
        while True:
            block = os.read(fd, 65536)
            if not block:
                break
            if not first:
                first = block[:4]
            size += len(block)
            need(size <= maximum, "artifact exceeded bound")
            h.update(block)
        need(stamp(before) == stamp(os.fstat(fd)) and size == before.st_size,
             "artifact changed during held hashing")
        if require_elf:
            need(first == b"\x7fELF" and before.st_mode & 0o111,
                 "compiled artifact is not an executable ELF")
        return {"path": str(path), "bytes": size, "sha256": h.hexdigest(),
                "device": before.st_dev, "inode": before.st_ino,
                "mode": stat.S_IMODE(before.st_mode)}
    finally:
        os.close(fd)

def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())

def all_source(root):
    # Same serialized inventory as actual producer05 build-template.py.
    # The bounded regular-file reader adds held-open race rejection only.
    rows = []
    total = 0
    for path in sorted(root.rglob("*")):
        st = path.lstat()
        name = path.relative_to(root).as_posix()
        if stat.S_ISDIR(st.st_mode):
            continue
        if stat.S_ISREG(st.st_mode):
            data = read_regular(path, SOURCE_LIMIT)
            rows.append({"path": name, "bytes": st.st_size, "sha256": sha(data)})
            total += len(data)
        elif stat.S_ISLNK(st.st_mode):
            rows.append({"path": name, "symlink": os.readlink(path)})
        else:
            raise RuntimeError("unexpected non-source inode " + name)
        need(len(rows) <= 4096 and total <= 256 * 1024 * 1024,
             "complete source inventory bound exceeded")
    return json_bytes(rows)

def plain_input_path(root, name):
    need(not name.startswith("/") and ".." not in Path(name).parts,
         "invalid input relative path")
    need(root.resolve(strict=True) == root, "source root is not a plain absolute directory")
    current = root
    parts = Path(name).parts
    for part in parts[:-1]:
        current = current / part
        need(stat.S_ISDIR(current.lstat().st_mode), "source parent is not a real directory")
    need(stat.S_ISREG((root / name).lstat().st_mode),
         "source input is not a real regular file")
    return root / name

def inputs(root, expected):
    result = {}
    for name in sorted(expected):
        need(not name.startswith("/") and ".." not in Path(name).parts,
             "invalid input relative path")
        data = read_regular(plain_input_path(root, name), SOURCE_LIMIT)
        result[name] = {"bytes": len(data), "sha256": sha(data)}
    need(result == expected, "exact 31 input pins differ")
    return result

def command_env(target):
    env = dict(os.environ)
    for key in list(env):
        if key in {"RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTFLAGS",
                   "CARGO_ENCODED_RUSTFLAGS", "RUSTDOCFLAGS", "RUSTDOC",
                   "RUSTC", "CARGO_TARGET_DIR"}:
            env.pop(key, None)
    env.update(CARGO_BUILD_JOBS="1", CARGO_INCREMENTAL="0",
               CARGO_PROFILE_DEV_DEBUG="0", CARGO_PROFILE_TEST_DEBUG="0",
               RUST_TEST_THREADS="1", CARGO_TARGET_DIR=str(target),
               CARGO_HOME="/home/alex/.cargo", RUSTUP_HOME="/home/alex/.rustup")
    return env

def run_command(report, directory, argv, cwd, env, timeout, pass_fds=()):
    index = len(report["commands"])
    stdout_path = directory / ("command-%02d.stdout" % index)
    stderr_path = directory / ("command-%02d.stderr" % index)
    row = {"argv": argv, "cwd": str(cwd), "started_at": now(),
           "timeout_seconds": timeout, "timed_out": False,
           "returncode": None, "stdout_path": str(stdout_path),
           "stderr_path": str(stderr_path)}
    report["commands"].append(row)
    with open(stdout_path, "xb") as stdout, open(stderr_path, "xb") as stderr:
        process = subprocess.Popen(argv, cwd=cwd, env=env,
                                   stdin=subprocess.DEVNULL, stdout=stdout,
                                   stderr=stderr, start_new_session=True,
                                   pass_fds=pass_fds)
        row["exact_child_pid"] = process.pid
        try:
            row["returncode"] = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            row["timed_out"] = True
            # The direct child has not been reaped, so its numeric process
            # group cannot be recycled while these two group signals run.
            # Do not poll/wait between TERM and KILL.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            time.sleep(0.2)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            row["returncode"] = process.wait(timeout=5)
        finally:
            stdout.flush()
            stderr.flush()
    row["finished_at"] = now()
    row["stdout_pin"] = file_pin(stdout_path, maximum=64 * 1024 * 1024)
    row["stderr_pin"] = file_pin(stderr_path, maximum=64 * 1024 * 1024)
    out = read_regular(stdout_path, LOG_LIMIT)
    err = read_regular(stderr_path, LOG_LIMIT)
    row["stdout_excerpt"] = out[-4096:].decode("utf-8", errors="replace")
    row["stderr_excerpt"] = err[-4096:].decode("utf-8", errors="replace")
    need(not row["timed_out"] and row["returncode"] == 0,
         "command failed or timed out: " + str(index))
    return out, err

def validate_config(cfg):
    need(set(cfg) == {"schema", "revision", "preimage", "overlays",
                     "original_diff_sha256", "source_manifest_sha256"},
         "unexpected recovery payload fields")
    need(cfg["schema"] == 1 and cfg["revision"] == CONTROL_REVISION,
         "wrong recovery payload revision")
    need(cfg["original_diff_sha256"] == ORIGINAL_DIFF_SHA and
         cfg["source_manifest_sha256"] ==
         "ad66ab3800fecbfc75bf10a5dcefbd46fad1a7fb642ff205b2d26cd10a010bf3",
         "wrong recovered source lineage")
    need(len(cfg["preimage"]) == 31 and
         set(cfg["overlays"]) == set(EXACT_OVERLAY), "wrong input/overlay set")
    for name, (size, digest) in EXACT_OVERLAY.items():
        row = cfg["overlays"][name]
        data = row["text"].encode("utf-8")
        need(set(row) == {"text", "bytes", "sha256"} and
             row["bytes"] == size and len(data) == size and
             row["sha256"] == digest and sha(data) == digest,
             "overlay does not match original frozen source: " + name)
    return cfg

def candidate_input_pins(cfg):
    result = dict(cfg["preimage"])
    for name, row in cfg["overlays"].items():
        result[name] = {"bytes": row["bytes"], "sha256": row["sha256"]}
    return result

import sys

TARGETED_TESTS = [
    "lifecycle_bootstrap::tests::producer05_three_second_retirement_is_rejected_before_transport",
    "lifecycle_bootstrap::tests::shared_retirement_bound_sends_exact_request_and_receives_terminal_ack",
]

def fd_digest(fd, expected):
    before = os.fstat(fd)
    need(stat.S_ISREG(before.st_mode) and
         before.st_dev == expected["device"] and
         before.st_ino == expected["inode"] and
         before.st_size == expected["bytes"] and
         stat.S_IMODE(before.st_mode) == expected["mode"] and
         before.st_mode & 0o111,
         "held ELF identity differs from actual compile receipt")
    need(before.st_size <= 256 * 1024 * 1024, "ELF bound exceeded")
    offset = 0
    h = hashlib.sha256()
    while offset < before.st_size:
        block = os.pread(fd, min(65536, before.st_size - offset), offset)
        need(bool(block), "short held ELF read")
        if offset == 0:
            need(block.startswith(b"\x7fELF"), "held input is not ELF")
        offset += len(block)
        h.update(block)
    need(stamp(before) == stamp(os.fstat(fd)) and h.hexdigest() == expected["sha256"],
         "held ELF bytes changed or differ from actual compile receipt")
    return stamp(before)

def test_summary(out, expected_passed, expected_filtered):
    text = out.decode("utf-8")
    found = re.findall(
        r"^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored; "
        r"(\d+) measured; (\d+) filtered out;", text, re.M)
    need(len(found) == 1, "exact test binary summary missing or repeated")
    state, passed, failed, ignored, measured, filtered = found[0]
    need(state == "ok" and int(passed) == expected_passed and
         int(failed) == 0 and int(ignored) == 0 and int(measured) == 0 and
         int(filtered) == expected_filtered, "test count/status mismatch")
    return {"passed": int(passed), "failed": 0, "ignored": 0,
            "measured": 0, "filtered_out": int(filtered)}

def ordinary_recovery(external_sha):
    need(re.fullmatch(r"[0-9a-f]{64}", external_sha) is not None,
         "a complete externally verified actual compile SHA is required")
    need(os.geteuid() != 0, "ordinary controls must run as the configured non-root operator")
    os.umask(0o077)
    run_dir = OUT / "ordinary-run-01"
    run_dir.mkdir(mode=0o700)
    report = {
        "schema": 1, "revision": CONTROL_REVISION, "started_at": now(),
        "success": False, "commands": [], "external_compile_sha256": external_sha,
        "cargo_invoked": False, "ordinary_controls_only": True,
        "full_owner_runtime_qualified": False, "real_broker_generation_qualified": False,
        "android_runtime_started": False, "barrier_constructor_executed": False,
        "pressure_or_namespace_effects_requested": False,
        "installed_files_changed": False, "main_fence_claimed": False,
        "targeted_public_retirement_controls": [],
    }
    cfg = None
    try:
        raw = read_regular(OUT / "compile-result.json", 256 * 1024)
        need(sha(raw) == external_sha, "compile receipt differs from external SHA")
        actual = json.loads(raw)
        need(actual["schema"] == 1 and actual["revision"] == CONTROL_REVISION and
             actual["success"] is True and actual["compile_only"] is True and
             actual["test_binaries_executed"] is False and
             actual["candidate"] == str(CANDIDATE) and
             actual["target"] == str(TARGET) and
             actual["prior_build_receipt_sha256"] == PRIOR_RECEIPT_SHA and
             actual["original_source_diff_sha256"] == ORIGINAL_DIFF_SHA and
             actual["original_source_inventory_after_sha256"] == PRIOR_INVENTORY_SHA and
             actual["all_source_inventory_before_sha256"] ==
             actual["all_source_inventory_after_sha256"],
             "actual matching compile admission failed")
        put(run_dir / "admitted-compile-result.json", raw)
        payload = read_regular(OUT / "payload.json", 512 * 1024)
        need(sha(payload) == actual["payload_sha256"], "compiled payload digest differs")
        cfg = validate_config(json.loads(payload))
        prior_raw = read_regular(OUT / "producer05-actual-build-result.json", 128 * 1024)
        need(sha(prior_raw) == PRIOR_RECEIPT_SHA, "producer05 lineage receipt differs")
        prior = json.loads(prior_raw)
        need(prior["inputs_before"] == cfg["preimage"] == prior["inputs_after"],
             "31 original source inputs differ")
        expected = candidate_input_pins(cfg)
        report["inputs_before"] = inputs(CANDIDATE, expected)
        need(actual["inputs_before"] == expected == actual["inputs_after"],
             "actual compile source inputs differ")
        before = all_source(CANDIDATE)
        need(sha(before) == actual["all_source_inventory_before_sha256"],
             "full compiled source tree changed before ordinary controls")
        report["all_source_inventory_before_sha256"] = sha(before)
        put(run_dir / "source-inventory-before.json", before)
        tests = {}
        for row in actual["compiled_test_artifacts"]:
            key = (row["target_name"], row["target_kind"])
            need(key in EXPECTED_TEST_TARGETS and key not in tests,
                 "unexpected or repeated compiled test identity")
            path = Path(row["path"])
            need(path.is_relative_to(TARGET / "debug" / "deps") and
                 Path(row["cargo_target_source"]).is_relative_to(CANDIDATE / "runtime"),
                 "compiled test escaped candidate/target")
            tests[key] = row
        need(set(tests) == EXPECTED_TEST_TARGETS and
             set(actual["artifacts"]) == set(BINARIES), "compiled artifact set incomplete")
        for name in BINARIES:
            need(actual["artifacts"][name]["path"] == str(TARGET / "debug" / name),
                 "binary path does not match isolated output")
        env = command_env(TARGET)
        deadline = time.monotonic() + 165

        def execute(row, args, limit):
            remaining = deadline - time.monotonic()
            need(remaining >= 1, "ordinary invocation envelope exhausted")
            path = Path(row["path"])
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                first = fd_digest(fd, row)
                need(stamp(path.lstat()) == first, "named ELF no longer names the held object")
                index = len(report["commands"])
                try:
                    out, err = run_command(
                        report, run_dir, ["/proc/self/fd/" + str(fd)] + list(args),
                        CANDIDATE, env, min(limit, remaining), (fd,))
                finally:
                    if len(report["commands"]) > index:
                        report["commands"][index]["actual_held_elf"] = {
                            "path": row["path"], "sha256": row["sha256"],
                            "bytes": row["bytes"], "device": row["device"],
                            "inode": row["inode"], "mode": row["mode"]}
                        # This is additional validation only; it cannot replace
                        # the command return code or an original test error.
                need(fd_digest(fd, row) == first and stamp(path.lstat()) == first,
                     "executed ELF changed during ordinary control")
                return out, err
            finally:
                os.close(fd)

        relay = tests[("droidloom_pressure_relay", "lib")]
        for name in TARGETED_TESTS:
            out, _ = execute(relay, ["--exact", name, "--test-threads=1", "--nocapture"], 8)
            result = test_summary(out, 1, 24)
            result["name"] = name
            report["targeted_public_retirement_controls"].append(result)
        counts = {}
        for key in sorted(tests):
            expected_count = (25 if key == ("droidloom_pressure_relay", "lib") else
                              122 if key == ("droidloom_supervisor", "lib") else 0)
            limit = 30 if key[0] == "droidloom_pressure_relay" else 45 if key[0] == "droidloom_supervisor" else 5
            out, _ = execute(tests[key], ["--test-threads=1"], limit)
            result = test_summary(out, expected_count, 0)
            counts[key[0] + ":" + key[1]] = result["passed"]
        ordinary, _ = execute(actual["artifacts"]["owned-ipc-controls"], [], 30)
        need(len(re.findall(rb"^PASS ", ordinary, re.M)) == 7 and
             ordinary.endswith(b"RESULT PASS mode=host-negative-controls\n"),
             "ordinary seven-control result missing")
        context, _ = execute(actual["artifacts"]["owned-ipc-controls"],
                             ["--worker-context-control"], 10)
        need(len(re.findall(rb"^PASS ", context, re.M)) == 1 and
             context.endswith(b"RESULT PASS mode=worker-context-without-namespace-or-pressure-effects\n"),
             "real leader-token ordinary control missing")
        abi, _ = execute(actual["artifacts"]["droidloom-supervisor"],
                         ["relay-entry-abi"], 5)
        need(abi == b"droidloom-relay-entry-v1\n", "compiled entry ABI differs")
        report["inputs_after"] = inputs(CANDIDATE, expected)
        after = all_source(CANDIDATE)
        put(run_dir / "source-inventory-after.json", after)
        need(after == before and report["inputs_before"] == report["inputs_after"],
             "compiled source changed during ordinary controls")
        report.update(
            success=True, all_source_inventory_after_sha256=sha(after),
            rust_test_binary_counts=counts,
            rust_tests_passed={"droidloom-pressure-relay": 25, "droidloom-supervisor": 122},
            ordinary_ipc_passed=7, worker_context_passed=True,
            actual_compiled_entry_abi_passed=True,
            scope="ordinary host controls only; actual public request/status uses the compiled relay crate")
    except Exception as failure:
        report["error"] = type(failure).__name__ + ": " + str(failure)
        report["traceback"] = traceback.format_exc()
    report["finished_at"] = now()
    raw = json_bytes(report)
    put(run_dir / "run-result.json", raw)
    print(json.dumps({
        "success": report["success"], "report": str(run_dir / "run-result.json"),
        "bytes": len(raw), "sha256": sha(raw),
        "rust_tests_passed": report.get("rust_tests_passed"),
        "ordinary_ipc_passed": report.get("ordinary_ipc_passed"),
        "full_owner_runtime_qualified": False, "error": report.get("error")
    }), flush=True)
    raise SystemExit(0 if report["success"] else 1)

def run_from_args():
    need(len(sys.argv) == 3 and sys.argv[1] == "--compile-sha256",
         "usage: python3 -I -B - --compile-sha256 <externally-verified-actual-sha>")
    ordinary_recovery(sys.argv[2])

if __name__ == "__main__":
    run_from_args()
