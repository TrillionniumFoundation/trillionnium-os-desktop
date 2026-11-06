#!/usr/bin/env python3
"""One real local filesystem fixture; never invokes observer.run or Main."""
import sys
sys.dont_write_bytecode = True
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import time
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent


def load(path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


def census():
    rows = {}
    for name in os.listdir("/proc/self/fd"):
        try:
            fd = int(name)
            info = os.fstat(fd)
            rows[name] = [info.st_dev, info.st_ino, info.st_mode, os.readlink("/proc/self/fd/" + name)]
        except FileNotFoundError:
            pass
        except OSError as error:
            if error.errno != 9:
                raise
    return rows


def main():
    worker_path = HERE / "observer-candidate-r1/observe_retention.py"
    worker = load(worker_path, "local_metadata_fixture_worker")
    core = load(PROJECT / "recovery/successor_runtime.py", "local_frozen_fd_primitives_only")
    before = census()
    pool = core.FDs()
    result = {"schema": "pocket4-retention-owned-local-filesystem-control-v1", "uid": os.getuid(),
              "Main_reads": 0, "native_commands": 0, "namespace_entries": 0, "remote_jobs": 0,
              "observer_run_invoked": False, "controls": [], "ok": False}
    try:
        with tempfile.TemporaryDirectory(prefix="pocket4-retention-local-control-") as tmp:
            base = Path(tmp)
            watched, output_dir = base / "watched", base / "evidence"
            watched.mkdir(mode=0o700); output_dir.mkdir(mode=0o700)
            outside = base / "outside"; outside.mkdir(mode=0o700)
            (outside / "sentinel").write_bytes(b"outside the reviewed walk scope\n")
            (watched / "data.bin").write_bytes(b"owned local fixture\n" * 512)
            os.link(watched / "data.bin", watched / "same-inode.bin")
            os.symlink(outside, watched / "external-link")
            host = pool.own(os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC))
            proc = pool.own(os.open("/proc/" + str(os.getpid()), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC))
            directory = pool.own(os.open(output_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC))
            output = worker.PrivateOutput(core, pool, str(output_dir), directory)
            output.start_entries()
            index = worker.AllocationIndex()
            full = worker.walk_tree(pool, host, proc, {"path": str(watched), "maximum_entries": 20, "maximum_depth": 4},
                                    time.monotonic() + 10, [0], index, output)
            assert full["status"] == "COMPLETE_METADATA_WALK" and full["entries"] == 3
            assert full["directory_iterators_opened"] == full["directory_iterators_closed"] == 1
            regular = [row for row in index.rows.values() if row["kinds"] == {stat.S_IFREG}]
            assert len(regular) == 1 and len(regular[0]["observed_aliases"]) == 2 and regular[0]["nlink_samples"] == {2}
            assert index.summary()["stable_regular_file_logical_bytes_unique_device_inode"] == (watched / "data.bin").stat().st_size
            assert index.summary()["reclaimable_bytes"] is None
            assert all(not path.startswith(str(outside)) for row in index.rows.values() for coordinate, path in row["observed_aliases"])
            assert any(row["kinds"] == {stat.S_IFLNK} for row in index.rows.values())
            result["controls"].append({"name": "real_hardlinks_deduplicated_and_external_symlink_not_traversed", "passed": True})
            limited = worker.walk_tree(pool, host, proc, {"path": str(watched), "maximum_entries": 2, "maximum_depth": 4},
                                       time.monotonic() + 10, [0], worker.AllocationIndex(), output)
            assert limited["status"] == "INCOMPLETE" and limited["entries"] == 2
            assert limited["gaps"] == [{"type": "RuntimeError", "code": "TREE_WALK_ENTRY_BOUND"}]
            assert limited["directory_iterators_opened"] == limited["directory_iterators_closed"] == 1
            result["controls"].append({"name": "real_entry_cap_preserves_incomplete_state_and_closes_iterator", "passed": True})
            receipt = output.finish_entries()
            raw = Path(receipt["path"]).read_bytes()
            assert len(raw) == receipt["bytes"] and hashlib.sha256(raw).hexdigest() == receipt["sha256"]
            assert len(raw.splitlines()) == 5 and stat.S_IMODE(Path(receipt["path"]).stat().st_mode) == 0o400
            result["controls"].append({"name": "new_private_stream_full_readback_and_no_cleanup_claim", "passed": True})
            result["entry_fixture_bytes"] = len(raw)
            result["entry_fixture_sha256"] = hashlib.sha256(raw).hexdigest()
        result["ok"] = True
    finally:
        pool.close_all()
        result["owned_FDs"] = pool.summary()
    after = census()
    assert before == after
    result.update(original_descriptor_identities_restored=True, FDs_before=len(before), FDs_after=len(after),
                  source_bytes=len(worker_path.read_bytes()), source_sha256=hashlib.sha256(worker_path.read_bytes()).hexdigest())
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
