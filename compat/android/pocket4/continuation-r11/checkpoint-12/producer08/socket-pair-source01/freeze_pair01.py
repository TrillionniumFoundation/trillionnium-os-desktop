#!/usr/bin/env python3
"""Create-only paired source checkpoint; does not build or dispatch anything."""
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "socket-projection-pair-freeze-01"
EVIDENCE = ROOT.parent.parent / "root-recovery-20261104-02/evidence"


def sha(body):
    return hashlib.sha256(body).hexdigest()


def write(relative, body):
    if isinstance(body, str):
        body = body.encode()
    body.decode("utf-8")
    path = OUT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as file:
        file.write(body)


def pretty(value):
    return json.dumps(value, sort_keys=True, indent=2) + "\n"


def main():
    OUT.mkdir(exist_ok=False)
    original = json.loads((ROOT / "preimage-pins.json").read_text())
    changed = []
    diff = ""
    source = []
    for item in original["files"]:
        relative = item["path"]
        before = (ROOT / "preimage" / relative).read_bytes()
        after = (ROOT / "candidate" / relative).read_bytes()
        assert len(before) == item["bytes"] and sha(before) == item["sha256"]
        assert before == Path(item["preimage_source"]).read_bytes()
        write("preimage/" + relative, before)
        write("source/" + relative, after)
        source.append({"path": relative, "bytes": len(after), "sha256": sha(after)})
        if before != after:
            changed.append(relative)
            diff += "".join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                                               fromfile="a/" + relative, tofile="b/" + relative))
    assert changed == [
        "host/runtime/droidloom-supervisor/src/relay_lifecycle/init_peer.rs",
        "host/runtime/droidloom-supervisor/src/relay_lifecycle/entry.rs",
        "android/diagnostic_controls.c", "android/init_relay_barrier.c",
        "android/init_relay_protocol.h", "android/protocol_controls.c",
    ], changed
    write("source.diff", diff)
    write("preimage-pins.json", (ROOT / "preimage-pins.json").read_bytes())
    write("source-manifest.json", pretty({"kind": "paired_detached_socket_projection_v2_source_01", "files": source}))
    for relative in ["run_local_controls.py", "run_local_controls02.py", "freeze_pair01.py",
                     "local-controls-01/result.json", "local-controls-02/result.json"]:
        write(relative, (ROOT / relative).read_bytes())
    mechanism = (EVIDENCE / "socket-projection-mechanism01/result.json").read_bytes()
    assert len(mechanism) == 177936 and sha(mechanism) == "4a6f12bac1b20679596f7e6b2484662adaa90299c823bd957e24e2919051b4a6"
    write("evidence/pocket4-projection-mechanism-result.json", mechanism)
    local = json.loads((ROOT / "local-controls-02/result.json").read_text())
    assert local["success"] is True and local["owned_projection_seam_cases_passed"] == 7
    assert local["transport_controls_passed"] is False
    write("validation.json", pretty({
        "kind": "paired_socket_projection_source_validation_01", "changed_files": changed,
        "source_diff": {"bytes": len(diff.encode()), "sha256": sha(diff.encode())},
        "actual_pocket4_mechanism_source_is_separate_from_production_pair": True,
        "actual_pocket4_mechanism_report_sha256": sha(mechanism),
        "local_projection_seam_cases_passed": 7,
        "local_c_strict_compilation_passed": True,
        "local_transport_controls_passed": False,
        "local_transport_failure_preserved": True,
        "rust_compiled": False, "android_matching_built": False,
        "actual_constructor_v2_executed": False, "owner_active_qualified": False,
        "main_modified": False, "installed_producer_qualified": False,
    }))
    write("README.md", """# Paired detached socket projection, ABI 2

NORMAL03 reached authenticated init HELLO and broker READY, then failed at
`project-bind-mount` with errno 22. Its original failure and exact retirement
remain unchanged. A separate actual Pocket4 owned namespace probe confirmed:
raw foreign O_PATH bind fails EINVAL; reopening the same inode in the child
namespace binds successfully; a source-owner detached clone transfers through
SCM_RIGHTS and attaches with move_mount. The two processes shared the same
initial user namespace and had distinct mount namespaces. Its exact result is
included, but it does not qualify this new producer or Android constructor.

## Paired production change

The supervisor still validates the exact READY endpoint inode, socket type,
UID/GID, mode and O_PATH descriptor. It revalidates the original HostContext
through the existing broker gate before cloning that locally opened endpoint
with `open_tree(CLONE|CLOEXEC|AT_EMPTY_PATH)`. The clone must retain the exact
inode, type, owner, mode and descriptor sealing. Only that new detached mount FD
is sent. The original endpoint proof remains retained for audit and cleanup;
the temporary clone is closed after send or on every error. The broker is a
direct exec with no namespace transition, and the worker's captured namespaces
must remain the leader's. An init-received foreign raw FD is never cloned here.

The real init constructor keeps its own newly O_EXCL-created target FD open and
uses `move_mount(F_EMPTY_PATH|T_EMPTY_PATH)` exactly once. It retains root/dev/
socket-directory owner/mode checks, socket post-stat identity checks, all
credentials, nonces, phase/rights counts, finite deadlines and first-errno
preservation. No raw bind fallback or path-based target reopening is added.

The descriptor semantics are explicitly versioned: init wire magic P4IBV2!!,
numeric ABI 2, constructor environment ABI 2 and CLI entry ABI
`droidloom-relay-entry-v2`. Old init headers are rejected before projection;
old entry binaries are refused by the existing exact ABI query. The deployment
pair must additionally bind both resulting executable/DSO SHA-256 values in the
original explicit CellSpec. No current artifact or installed service changed.

## Actual validation and limits

Local strict C compilation succeeded. Seven owned directory/projection syscall
seam controls passed, including exact empty-path move flags, a still-open target
FD with CLOEXEC, O_EXCL refusal, directory policy checks, target closure and
first errno preservation. Their move syscall is explicitly replaced and they
do not claim actual mount execution. The first local transport case failed;
the original result is preserved, and a direct local capability check records
EPERM when creating an AF_UNIX SOCK_SEQPACKET listener. The Pocket4 matching
build must still run both original 20-case transport suites and all seven
diagnostic controls. The added Rust ordinary control refuses non-O_PATH input
before mount creation; no Rust execution is claimed in this checkpoint.

Next required evidence: fresh matching Rust build and ordinary controls,
matching Android DSO build and owned C controls, then a new exact private
CellSpec/nonce/unit run showing the actual constructor PROJECTED/COMMIT/DONE,
broker ACTIVE and complete original Stop/retirement. RC critical/property
reload semantics, actual pressure and installed lifecycle qualification remain
separate open gates. No old failed cell is replayed.
""")
    members = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file():
            body = path.read_bytes()
            members.append({"path": str(path.relative_to(OUT)), "bytes": len(body), "sha256": sha(body)})
    write("manifest.json", pretty({"kind": "paired_projection_source_freeze_01", "files": members}))
    print(pretty({"root": str(OUT), "files": len(members), "manifest_sha256": sha((OUT / "manifest.json").read_bytes()),
                  "diff_bytes": len(diff.encode()), "diff_sha256": sha(diff.encode())}))


if __name__ == "__main__":
    main()
