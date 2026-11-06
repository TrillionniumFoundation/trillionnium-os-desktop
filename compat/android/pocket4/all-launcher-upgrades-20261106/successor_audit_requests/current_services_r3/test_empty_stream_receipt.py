#!/usr/bin/env python3
"""One local owned child, exact empty streams, and a real exclusive-write failure."""
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    core_path = PROJECT / "recovery/successor_runtime.py"
    core_raw = core_path.read_bytes()
    assert len(core_raw) == 65302 and hashlib.sha256(core_raw).hexdigest() == \
        "53f79b2bdfc694a3006c0d33232a277a8729773407f301af6a07aa6a46f490d5"
    core = load(core_path, "frozen_core_definitions_only")
    worker_path = ROOT / "observe_current_services.py"
    worker = load(worker_path, "services_r3_definitions_only")
    before = len(os.listdir("/proc/self/fd"))
    raw, stderr, command = worker.held_bounded_child(
        [sys.executable, "-I", "-B", "-c", "pass"], 3, 65536, (),
        {"PATH": "/usr/bin:/bin", "LANG": "C"})
    assert raw == stderr == b"" and command["returncode"] == 0
    assert command["complete"] and command["joined"] and not command["termination_attempted"]
    assert command["errors"] == []
    try:
        os.waitpid(command["host_pid"], os.WNOHANG)
    except ChildProcessError:
        reaped = True
    else:
        raise AssertionError("Owned child was not reaped")
    pool = core.FDs()
    with tempfile.TemporaryDirectory(prefix="p4-services-empty-stream-local-") as temporary:
        directory = pool.own(os.open(temporary, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC))
        identity = core.metadata(directory)

        def write(name, data):
            pin = worker.write_empty_raw_stream(core, pool, directory, identity, temporary + "/" + name, data)
            assert core.pinned_record(pin, 1) == data
            item = os.stat(temporary + "/" + name, follow_symlinks=False)
            assert item.st_uid == os.getuid() and item.st_size == 0 and item.st_nlink == 1
            assert stat.S_ISREG(item.st_mode) and stat.S_IMODE(item.st_mode) == 0o400
            return pin

        rows = []
        worker.remember_child_streams(rows, {"command": command}, write, "native-01", raw, stderr)
        assert len(rows) == 1 and rows[0]["stream_artifacts_complete"] is True
        assert rows[0]["stdout"]["bytes"] == rows[0]["stderr"]["bytes"] == 0
        assert rows[0]["stdout"]["sha256"] == rows[0]["stderr"]["sha256"] == hashlib.sha256(b"").hexdigest()
        # A second save of this already captured child record must fail, not overwrite.
        # No command is executed a second time.
        failed_rows = []
        try:
            worker.remember_child_streams(failed_rows, {"command": command}, write, "native-01", raw, stderr)
        except FileExistsError as error:
            assert error.errno == errno.EEXIST
        else:
            raise AssertionError("Existing raw stream was overwritten")
        assert len(failed_rows) == 1 and failed_rows[0]["command"] is command
        assert failed_rows[0]["stream_artifacts_complete"] is False
        assert failed_rows[0]["stream_artifact_error"] == {"type": "FileExistsError", "errno": errno.EEXIST}
        assert failed_rows[0]["command"]["complete"] and failed_rows[0]["command"]["joined"]
        assert core.pinned_record(rows[0]["stdout"], 1) == core.pinned_record(rows[0]["stderr"], 1) == b""
        pool.close_all()
    after = len(os.listdir("/proc/self/fd"))
    assert before == after and pool.summary()["remaining"] == 0
    output = {
        "schema": "pocket4-services-r3-real-empty-stream-and-receipt-failure-control-v1",
        "ok": True, "control_count": 1, "real_owned_children": 1,
        "command": command, "owned_child_reaped": reaped,
        "empty_stdout_and_stderr_saved_exactly": True,
        "raw_files_mode": "0400", "actual_fixture_uid": os.getuid(),
        "production_root_authority_not_simulated": True,
        "existing_stream_overwrite_rejected": True,
        "command_retained_before_actual_write_failure": True,
        "write_failure": failed_rows[0]["stream_artifact_error"],
        "observation_FDs": pool.summary(),
        "process_FDs_before": before, "process_FDs_after": after,
        "Pocket4_operations": 0, "Main_operations": 0, "namespace_entries": 0,
        "source_sha256": hashlib.sha256(worker_path.read_bytes()).hexdigest(),
        "frozen_core_unchanged": True,
    }
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
