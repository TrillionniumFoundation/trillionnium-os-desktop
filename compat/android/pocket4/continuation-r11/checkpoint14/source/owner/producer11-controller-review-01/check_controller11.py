#!/usr/bin/env python3
"""Local source/encoding checks only. Never calls Cargo, a remote tool or a controller entry."""
import ast
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD = ROOT / "producer10-broker-controller-freeze-01"
NEW = ROOT / "producer11-retirement-controller-freeze-01"
SOURCE = ROOT / "broker-retirement-cause-source-freeze-01"
OUT = ROOT / "producer11-controller-review-01"
EVIDENCE = ROOT.parent / "root-recovery-20261104-02/evidence"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pin(path):
    data = path.read_bytes()
    data.decode("utf-8")
    return {"path": str(path), "bytes": len(data), "sha256": sha(data)}


def once(text, before, after):
    assert text.count(before) == 1, (before, text.count(before))
    return text.replace(before, after)


def main():
    assert not OUT.exists(), "create-only review"
    checked = []
    for directory, digest in [
        (SOURCE, "259154ae622c5c7ae5d29ca11b3a971dfc7e194ae6c9760b3b3de52e0b41a190"),
        (NEW, "211d0c075033990b56d3f410ac0a168d03edb0a02d8d2b37d03b02c103a8c375"),
    ]:
        manifest = (directory / "manifest.json").read_bytes()
        assert sha(manifest) == digest
        checked.append(pin(directory / "manifest.json"))
        for row in json.loads(manifest)["files"]:
            actual = pin(directory / row["path"])
            assert (actual["bytes"], actual["sha256"]) == (row["bytes"], row["sha256"])
            checked.append(actual)
    prior_raw = (EVIDENCE / "producer10-broker-compile01/result.json").read_bytes()
    assert len(prior_raw) == 39853 and sha(prior_raw) == "879cbe2c95a98de1f2d8d820348059eb1656d1b82c59b272bc4c901b91013460"
    prior = json.loads(prior_raw)
    assert prior["success"] is True and prior["compile_only"] is True
    assert len(prior["commands"]) == 2 and all(x["returncode"] == 0 and not x["timed_out"] for x in prior["commands"])
    assert set(prior["artifacts"]) == {"droidloomd", "droidloom-supervisor", "droidloom-psi-owner", "owned-ipc-controls"}
    assert {(x["target_name"], x["target_kind"]) for x in prior["compiled_test_artifacts"]} == {
        ("droidloom_pressure_relay", "lib"), ("droidloom_supervisor", "lib")}
    assert prior_raw == (NEW / "evidence/prior-actual-compile-result.json").read_bytes()
    ordinary_raw = (EVIDENCE / "producer10-broker-ordinary01/result.json").read_bytes()
    assert len(ordinary_raw) == 35980 and sha(ordinary_raw) == "245ad655d64c12df5bbd19987b264e795247f78d7def701a082b344d5a14bfa5"
    ordinary = json.loads(ordinary_raw)
    assert ordinary["success"] is True and ordinary["external_compile_sha256"] == sha(prior_raw)
    assert ordinary["rust_tests_passed"] == {"droidloom-pressure-relay": 26, "droidloom-supervisor": 122}
    assert ordinary["ordinary_ipc_passed"] == 7
    assert len(ordinary["commands"]) == 7 and all(x["returncode"] == 0 and not x["timed_out"] for x in ordinary["commands"])
    for case in ordinary["targeted_public_retirement_controls"]:
        assert case["passed"] == 1 and case["filtered_out"] == 25 and case["failed"] == 0
    cfg_raw = (NEW / "payload.json").read_bytes()
    cfg = json.loads(cfg_raw)
    old_cfg = json.loads((OLD / "payload.json").read_bytes())
    assert len(cfg["preimage"]) == 32 and cfg["preimage"] == prior["inputs_before"] == prior["inputs_after"]
    assert set(cfg["overlays"]) == {"runtime/droidloom-pressure-relay/src/lifecycle_bootstrap.rs"}
    name = next(iter(cfg["overlays"]))
    preimage = (SOURCE / "preimage" / name).read_bytes()
    candidate = (SOURCE / "candidate" / name).read_bytes()
    assert cfg["preimage"][name] == {"bytes": len(preimage), "sha256": sha(preimage)}
    assert cfg["overlays"][name] == {"bytes": len(candidate), "sha256": sha(candidate), "text": candidate.decode()}
    assert candidate.count(b"#[test]") - preimage.count(b"#[test]") == 4
    programs = {}
    function_counts = {}
    for name in ("compile.py", "run.py"):
        before = (OLD / name).read_text()
        after = (NEW / name).read_text()
        tree = ast.parse(after)
        compile(after, name, "exec")
        programs[name] = after
        normalized = after
        changes = [
            ('CONTROL_REVISION = "producer11-retirement-cause01"', 'CONTROL_REVISION = "producer10-broker-holding01"'),
            ('BASE = Path("/home/alex/work/pocket4-supervisor-lmkd-broker-r11-build-10-01")', 'BASE = Path("/home/alex/work/pocket4-supervisor-lmkd-cgroup-r11-build-09-01")'),
            ('OUT = Path("/home/alex/work/pocket4-supervisor-lmkd-cause-r11-build-11-01")', 'OUT = Path("/home/alex/work/pocket4-supervisor-lmkd-broker-r11-build-10-01")'),
            (sha(prior_raw), "415c12d44b3f2c568c8914126f61c4844b6a1238a565eabc488b8145c64eaae1"),
            ("89122d0b725cac487b5912cec473fddf731f7b52eaa107aa355a40540b3514a0", "6c1abf6ede0fb5ffd5379c6491a20800705cb59a3da867dabafd71970c0d2e47"),
            (cfg["original_diff_sha256"], old_cfg["original_diff_sha256"]),
            (cfg["source_manifest_sha256"], old_cfg["source_manifest_sha256"]),
            ("producer10-broker-holding01-actual-compile-result.json", "producer09-cgroup-handoff01-actual-compile-result.json"),
        ]
        for new, old in changes:
            normalized = once(normalized, new, old)
        assert "producer10 broker holding01" in normalized
        normalized = normalized.replace("producer10 broker holding01", "producer09 cgroup handoff01")
        start, end = normalized.index("EXACT_OVERLAY = {"), normalized.index("BINARIES = ")
        old_start, old_end = before.index("EXACT_OVERLAY = {"), before.index("BINARIES = ")
        normalized = normalized[:start] + before[old_start:old_end] + normalized[end:]
        if name == "compile.py":
            normalized = once(normalized, 'prior["revision"] == "producer10-broker-holding01"', 'prior["revision"] == "producer09-cgroup-handoff01"')
        else:
            normalized = once(normalized, "test_summary(out, 1, 29)", "test_summary(out, 1, 25)")
            normalized = once(normalized, 'expected_count = 30 if key == ("droidloom_pressure_relay", "lib") else 122', 'expected_count = 26 if key == ("droidloom_pressure_relay", "lib") else 122')
            normalized = once(normalized, 'rust_tests_passed={"droidloom-pressure-relay": 30, "droidloom-supervisor": 122},', 'rust_tests_passed={"droidloom-pressure-relay": 26, "droidloom-supervisor": 122},')
        assert normalized == before, name + " has an unreviewed byte difference"
        function_counts[name] = len([n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))])
    assert (NEW / "resource_guard.py").read_bytes() == (OLD / "resource_guard.py").read_bytes()
    request = json.loads((NEW / "compile-request.json").read_bytes())
    old_request = json.loads((OLD / "compile-request.json").read_bytes())
    stdin = (NEW / "compile-stdin.py").read_text()
    assert request["stdin"] == stdin
    assert request["idempotency_key"] == "p4-producer11-cause01-compile01-" + sha(stdin.encode())[:16]
    normalized_request = copy.deepcopy(request)
    for k in ("stdin", "idempotency_key"):
        normalized_request[k] = old_request[k]
    assert normalized_request == old_request
    parsed = ast.parse(stdin)
    call = parsed.body[-1].value
    assert isinstance(call, ast.Call) and call.func.id == "compile_recovery"
    assert ast.dump(parsed.body[-1]) == ast.dump(ast.parse("compile_recovery(json.loads(" + repr(cfg_raw.decode()) + "))").body[0])
    assert ast.dump(ast.Module(body=parsed.body[:-1], type_ignores=[])) == ast.dump(ast.parse(programs["compile.py"]))
    template = json.loads((NEW / "ordinary-run-request-template.json").read_bytes())
    old_template = json.loads((OLD / "ordinary-run-request-template.json").read_bytes())
    assert template["execution_ready"] is False
    assert template["request_template"]["stdin"] == programs["run.py"]
    assert template["request_template"]["args"][-1] == "REQUIRES_ACTUAL_SUCCESSFUL_COMPILE_SHA256"
    for k in ("stdin", "idempotency_key"):
        template["request_template"][k] = old_template["request_template"][k]
    assert template["request_template"] == old_template["request_template"]
    validation = json.loads((NEW / "validation.json").read_bytes())
    assert len(validation["negative_config_controls"]) == 8 and all(x["rejected"] for x in validation["negative_config_controls"])
    report = {
        "schema": 1, "scope": "Independent local complete byte-delta, AST, actual prior receipt and request binding checks",
        "result": "PASS", "producer11_rust_compiled": False, "producer11_rust_tests_executed": False,
        "owner_runtime_qualified": False, "remote_call_performed": False,
        "all_frozen_pins_checked": checked,
        "actual_prior_compile": pin(EVIDENCE / "producer10-broker-compile01/result.json"),
        "actual_prior_ordinary": pin(EVIDENCE / "producer10-broker-ordinary01/result.json"),
        "actual_prior_inputs_equal": True, "input_count": 32, "overlay_count": 1,
        "complete_controller_inverse_transforms_equal_original_bytes": True,
        "controller_recursive_function_class_counts": function_counts,
        "resource_guard_unchanged": True, "compile_command_argv_and_child_cleanup_unchanged": True,
        "request_changed_fields_only": ["stdin", "idempotency_key"],
        "ordinary_template_requires_external_actual_compile_sha": True,
        "new_expected_tests": {"relay_lib": 30, "supervisor_lib": 122, "ipc": 7, "targeted_count": 2, "targeted_each_pass": 1, "targeted_each_filtered": 29},
        "new_rust_controls": "NOT_RUN: local cargo/rustc unavailable; actual matching build required",
        "resource_limit_scope": "Original own-job contract only; no assertion of hard swap.max=0 or whole-invocation qualification",
        "runtime_requirement": "Fresh Owner generation with matching new broker/daemon; observe original retirement cause, retain any real failure",
    }
    OUT.mkdir()
    for name, data in [
        ("report.json", (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()),
        ("check_controller11.py", Path(__file__).read_bytes()),
    ]:
        with (OUT / name).open("xb") as stream:
            stream.write(data)
    print(json.dumps({"report": pin(OUT / "report.json"), "request": pin(NEW / "compile-request.json"), "stdin": pin(NEW / "compile-stdin.py"), "key": request["idempotency_key"]}, indent=2))


if __name__ == "__main__":
    main()
