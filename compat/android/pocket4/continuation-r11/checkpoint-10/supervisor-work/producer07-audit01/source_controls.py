#!/usr/bin/env python3
"""Local exact-source controls; no Rust, device, namespace or runtime work."""
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
BEFORE = ROOT / "baseline-deadline06" / "source"
AFTER = ROOT / "source"
RESULT = ROOT / "source-control-result.json"
DIFF = ROOT / "producer06-to07-audit.patch"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(root, rel):
    return (root / rel).read_text(encoding="utf-8")


def inventory(root):
    result = []
    for path in sorted(root.rglob("*")):
        assert not path.is_symlink(), f"unexpected symlink: {path}"
        if path.is_file():
            data = path.read_bytes()
            data.decode("utf-8")
            result.append({"path": str(path.relative_to(root)), "bytes": len(data), "sha256": sha(data)})
    return result


def strip_region(text, first, following):
    assert text.count(first) == 1
    start = text.index(first)
    end = text.index(following, start)
    return text[:start] + text[end:]


def run():
    assert not RESULT.exists(), "source-control receipt is create-only"
    checks = []

    def check(name, condition):
        assert condition, name
        checks.append(name)

    old = inventory(BEFORE)
    new = inventory(AFTER)
    expected = json.loads((ROOT / "baseline-deadline06" / "manifest.json").read_text())["files"]
    check("exact_31_file_deadline06_basis", old == expected and len(old) == 31)
    old_by_path = {row["path"]: row for row in old}
    new_by_path = {row["path"]: row for row in new}
    check("32_inputs_one_explicit_new_module", len(new) == 32 and set(new_by_path) - set(old_by_path) == {
        "runtime/droidloom-supervisor/src/relay_lifecycle/audit.rs"
    } and not set(old_by_path) - set(new_by_path))
    changed = [path for path in new_by_path if path not in old_by_path or new_by_path[path] != old_by_path[path]]
    check("ten_changed_inputs", len(changed) == 10)

    relay = "runtime/droidloom-pressure-relay/src/"
    supervisor = "runtime/droidloom-supervisor/src/"
    unchanged = [row for row in old if row["path"] not in changed]
    check("22_unchanged_inputs", len(unchanged) == 22)
    for path in [
        relay + "psi.rs", relay + "pressure_audit.rs", relay + "enrollment.rs",
        relay + "lifecycle_relay.rs", relay + "ancestry.rs",
        supervisor + "generation_claim.rs", supervisor + "development_network.rs",
        supervisor + "relay_lifecycle/domain.rs", supervisor + "relay_lifecycle/policy.rs",
        supervisor + "relay_lifecycle/entry.rs", supervisor + "relay_lifecycle/worker.rs",
    ]:
        check("unchanged:" + path, old_by_path[path] == new_by_path[path])

    core = read(AFTER, relay + "lib.rs")
    check("entire_core_authority_implementation_unchanged", core.replace(
        "LifecycleBroker, LifecycleProcessObservation, MAX_LIFECYCLE_IO_TIMEOUT",
        "LifecycleBroker, MAX_LIFECYCLE_IO_TIMEOUT",
    ) == read(BEFORE, relay + "lib.rs"))
    bootstrap = read(AFTER, relay + "lifecycle_bootstrap.rs")
    bootstrap = strip_region(bootstrap,
        "/// Read-only kernel identities from an existing authenticated broker pin.\n",
        "/// Supervisor-side ownership adapter.")
    bootstrap = strip_region(bootstrap,
        "    /// Data-only identity of the existing authenticated, live broker pin.\n",
        "    /// Close only this exact owned broker's authority channel")
    check("all_original_broker_methods_unchanged", bootstrap == read(BEFORE, relay + "lifecycle_bootstrap.rs"))

    peer_before = read(BEFORE, supervisor + "relay_lifecycle/init_peer.rs")
    peer_after = read(AFTER, supervisor + "relay_lifecycle/init_peer.rs")
    start = "struct Wait<'a>"
    end = "#[derive(Clone, Copy, Eq, PartialEq)]"
    check("entire_final_wait_gate_send_receive_unchanged",
          peer_before[peer_before.index(start):peer_before.index(end)] ==
          peer_after[peer_after.index(start):peer_after.index(end)])
    end = "fn require_exact_peer_packet("
    check("exact_peer_validation_and_original_transport_controls_unchanged",
          peer_before[peer_before.index(end):] == peer_after[peer_after.index(end):])

    dev_before = read(BEFORE, supervisor + "development.rs")
    dev_after = read(AFTER, supervisor + "development.rs")
    old_start = dev_before.index("    fn cleanup(&mut self) -> Result<(), DevelopmentError> {")
    new_start = dev_after.index("    fn cleanup_inner(&mut self) -> Result<(), DevelopmentError> {")
    marker = "    #[cfg(test)]\n    pub(crate) fn from_owned_child_for_test"
    old_body = dev_before[old_start:dev_before.index(marker, old_start)]
    new_body = dev_after[new_start:dev_after.index(marker, new_start)]
    check("original_cleanup_body_and_operation_order_unchanged",
          old_body.replace("fn cleanup(", "fn cleanup_inner(", 1) == new_body)

    control = read(AFTER, supervisor + "control.rs")
    check("seven_response_literals_explicitly_omit_none",
          control.count("relay_lifecycle: None,") == 7)
    check("only_status_stop_request_audit",
          control.count("let include_audit = matches!(&request, ControlRequest::Status | ControlRequest::Stop);") == 1)

    old_tests = set()
    new_tests = set()
    for path in changed:
        if path in old_by_path:
            old_tests.update(re.findall(r"#\[test\]\s*fn\s+(\w+)", read(BEFORE, path)))
        new_tests.update(re.findall(r"#\[test\]\s*fn\s+(\w+)", read(AFTER, path)))
    check("seven_new_test_definitions_no_removed_tests", len(new_tests - old_tests) == 7 and not old_tests - new_tests)

    patch = "".join(
        "".join(difflib.unified_diff(
            (read(BEFORE, path) if path in old_by_path else "").splitlines(True),
            read(AFTER, path).splitlines(True),
            fromfile="a/" + path if path in old_by_path else "/dev/null",
            tofile="b/" + path,
        )) for path in sorted(changed)
    )
    with DIFF.open("x", encoding="utf-8") as handle:
        handle.write(patch)
    patch_binary = shutil.which("patch")
    check("local_patch_tool_available", patch_binary is not None)
    with tempfile.TemporaryDirectory(prefix="audit-apply-", dir=ROOT) as temporary:
        target = Path(temporary) / "source"
        shutil.copytree(BEFORE, target)
        result = subprocess.run([patch_binary, "-p1", "--batch", "--forward", "--input", str(DIFF)],
                                cwd=target, capture_output=True, text=True, timeout=20)
        check("exact_patch_apply_exit0", result.returncode == 0)
        check("exact_patch_reconstructs_all_32_inputs", inventory(target) == new)
    report = {
        "schema": 1, "scope": "local exact-source and patch controls only",
        "status": "pass", "checks": checks, "check_count": len(checks),
        "new_rust_test_definitions": sorted(new_tests - old_tests),
        "new_rust_tests_executed": False, "rust_syntax_or_typecheck_performed": False,
        "device_or_namespace_execution": False, "owner_lifecycle_qualified": False,
        "android_or_main_deployed": False,
        "diff": {"path": DIFF.name, "bytes": len(patch.encode()), "sha256": sha(patch.encode())},
        "basis_inputs": old, "candidate_inputs": new, "changed_inputs": changed,
    }
    with RESULT.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({"status": "pass", "check_count": len(checks),
                      "diff": report["diff"], "report_sha256": sha(RESULT.read_bytes())}))


if __name__ == "__main__":
    run()
