#!/usr/bin/env python3
"""One local filesystem boundary control; never call the host worker main."""
import errno
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace


def main():
    root = Path(__file__).resolve().parent
    source = (root / "prepare_official_aapt2.py").read_bytes()
    assert len(source) == 61830 and hashlib.sha256(source).hexdigest() == "bdae0316cd5423f60a6d1884e2131ba446c3554ee696c3c543ebf3634e743a63"
    namespace = {"__name__": "local_runpath_boundary_only", "__file__": str(root / "prepare_official_aapt2.py")}
    exec(compile(source, namespace["__file__"], "exec"), namespace)
    before = namespace["census"]()
    previous_raw = (root.parent / "google-maven-aapt2-host-proof-r2/actual/worker.stdout.original.json").read_bytes()
    assert len(previous_raw) == 5874 and hashlib.sha256(previous_raw).hexdigest() == "05648e1384125fcfd88044f1cea9937e03537be3decd0b10701c876e5bb30215"
    previous = json.loads(previous_raw)
    actual_elf = previous["static_dependency_graph"][0]["static_elf"]
    path = namespace["OUTPUT"] + "/toolchain/platform/bin/aapt2"
    candidate = SimpleNamespace(declared=path, resolved=path, observed=previous["candidate"])
    paths = namespace["exact_controlled_search_paths"](candidate, actual_elf)
    assert len(paths) == 5 and all(name.startswith(namespace["OUTPUT"] + "/") for name in paths)
    try:
        namespace["search_paths"](actual_elf["runpath"], str(Path(path).parent))
    except RuntimeError as error:
        assert str(error) == "SEARCH_PATH_OUTSIDE_REVIEWED_SYSTEM_LIBRARY_ROOTS"
    else:
        raise AssertionError("Original system-only policy was widened")
    changed = dict(actual_elf, runpath=actual_elf["runpath"] + ":/home/alex/lib")
    try:
        namespace["exact_controlled_search_paths"](candidate, changed)
    except RuntimeError as error:
        assert str(error) == "EXACT_OBSERVED_OFFICIAL_LOADER_INPUTS_REQUIRED"
    else:
        raise AssertionError("Changed loader inputs were admitted")

    # This local fixture is genuinely UID1000-owned. It demonstrates the
    # absence/presence/symlink boundary, not production root-owned admission.
    assert os.getuid() == os.geteuid() == 1000
    reader = namespace["frozen_module"](namespace["READER_SOURCE"], namespace["READER_SHA"], "local_original_reader")
    needed = namespace["EXACT_TOOL_NEEDED"]
    with tempfile.TemporaryDirectory(prefix="aapt2-controlled-library-boundary-") as temporary:
        directory = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            absent = namespace["observe_missing_sonames"](directory, needed)
            assert absent == [{"soname": name, "outcome": "ENOENT"} for name in needed]
            try:
                namespace["require_secure_directory"](reader, directory, True)
            except RuntimeError as error:
                assert str(error) == "ROOT_OWNED_NONWRITABLE_ANCESTOR_OR_PRIVATE_DIRECTORY_REQUIRED"
            else:
                raise AssertionError("Local UID1000 fixture masqueraded as production root")
            descriptor = os.open(needed[0], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                 0o600, dir_fd=directory)
            os.close(descriptor)
            try:
                namespace["observe_missing_sonames"](directory, needed)
            except RuntimeError as error:
                assert str(error) == "LIBRARY_CANDIDATE_EXISTS_IN_PRIVATE_RUNPATH"
            else:
                raise AssertionError("Present candidate was treated as absent")
            os.unlink(needed[0], dir_fd=directory)
            os.symlink("missing-target", needed[0], dir_fd=directory)
            try:
                namespace["observe_missing_sonames"](directory, needed)
            except OSError as error:
                assert error.errno == errno.ELOOP
            else:
                raise AssertionError("Dangling symlink was treated as absence")
            os.unlink(needed[0], dir_fd=directory)
            assert namespace["observe_missing_sonames"](directory, needed) == absent
        finally:
            os.close(directory)
    after = namespace["census"]()
    assert after == before
    result = {
        "schema": "pocket4-exact-controlled-runpath-local-boundary-v1", "ok": True,
        "source": {"bytes": len(source), "sha256": hashlib.sha256(source).hexdigest()},
        "original_failed_host_worker": {"bytes": len(previous_raw), "sha256": hashlib.sha256(previous_raw).hexdigest()},
        "actual_observed_ELF_has_exact_five_private_projections": paths,
        "unchanged_system_search_function_still_rejects_private_paths": True,
        "modified_RUNPATH_rejected": True,
        "actual_local_fixture_uid": os.getuid(),
        "UID1000_fixture_rejected_by_production_root_guard": True,
        "six_actual_missing_names_observed_as_ENOENT": True,
        "actual_regular_library_candidate_rejected": True,
        "actual_dangling_symlink_rejected_as_ELOOP_not_absence": True,
        "original_descriptor_identities_restored": after == before,
        "process_FDs_before": len(before), "process_FDs_after": len(after),
        "production_root_layout_created": False, "tool_executions": 0,
        "Main_reads": 0, "Android_commands": 0, "network_requests": 0,
        "qualification": "local control only; real root-owned layout and version remain unexecuted"
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
