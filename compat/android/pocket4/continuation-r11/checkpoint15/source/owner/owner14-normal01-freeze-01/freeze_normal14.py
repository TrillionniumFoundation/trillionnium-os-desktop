#!/usr/bin/env python3
"""Freeze one fresh real Owner14 attempt from externally pinned actual builds."""
import argparse
import ast
import base64
import copy
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import stat

WORK = Path(__file__).resolve().parent
BASE = WORK.parent
OLD = BASE / "owner11-normal01-freeze-01"
PAIR = BASE / "cgroup-handoff-pair-freeze-01"
HOST_PAIR = BASE / "retirement-terminal-drain-source-freeze-13"
FIXTURE = BASE / "retirement-fixture-repair-source-freeze-14"
DIAGNOSTIC = BASE / "pinned-io-cause-source-freeze-12"
RUST = BASE / "producer14-fixture-controller-freeze-01"
OUT = BASE / "owner14-normal01-freeze-01"
PREFIX = "p4-owner14-normal-20261105-01"
OLD_PREFIX = "p4-owner11-normal-20261105-01"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pretty(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def actual_file(path, expected):
    assert re.fullmatch("[0-9a-f]{64}", expected)
    raw = path.read_bytes()
    assert sha(raw) == expected
    return raw, json.loads(raw)


def write(name, raw):
    if isinstance(raw, str):
        raw = raw.encode()
    raw.decode("utf-8")
    target = OUT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as file:
        file.write(raw)


def main():
    parser = argparse.ArgumentParser()
    for name in ("rust_build", "rust_run", "android_build", "mount_mechanism"):
        parser.add_argument("--" + name.replace("_", "-") + "-receipt", type=Path, required=True)
        parser.add_argument("--" + name.replace("_", "-") + "-sha256", required=True)
    args = parser.parse_args()
    rb_raw, rb = actual_file(args.rust_build_receipt, args.rust_build_sha256)
    rr_raw, rr = actual_file(args.rust_run_receipt, args.rust_run_sha256)
    cb_raw, cb = actual_file(args.android_build_receipt, args.android_build_sha256)
    mm_raw, mm = actual_file(args.mount_mechanism_receipt, args.mount_mechanism_sha256)
    mechanism = BASE / "cgroup-mount-mechanism-freeze-03"
    assert sha((mechanism / "manifest.json").read_bytes()) == "ef9b8e0255c01fc7ae235acb6cbd2295653bba93af66999f82028a6a65ddc851"
    mp = json.loads((mechanism / "profile.json").read_bytes())
    assert mm["kind"] == "owned-cgroup-repeat-mount-mechanism03" and mm["success"] is True and mm["errors"] == []
    assert mm["production_qualified"] is False and mm["Android_executed"] is False and mm["host_network_modified"] is False
    assert mm["probe_nonce"] == mp["nonce"] and mm["actual_MD_equals_preflight"] is True
    assert len(mm["commands"]) == 4 and all(c["returncode"] == 0 and c["child_reaped"] and not c["timed_out"] for c in mm["commands"])
    assert mm["dependencies_before"] == mm["dependencies_after"] and mm["resource_health"]["held_own_cgroup_gate_passed"] is True
    source_dep = mm["dependencies_before"][mp["root"] + "/source/probe.c"]
    assert source_dep["sha256"] == sha((mechanism / "source/probe.c").read_bytes())
    mc = mm["kernel_control"]
    assert mc["success"] is True and mc["peer_eof"] is True and mc["child_reaped"] is True and mc["forced_kill"] is False
    assert mc["parent_errno"] == mc["child_errno"] == mc["child_wait_status"] == 0
    assert mc["all_private_mounts_unmounted"] is True and mc["inherited_domain_closed"] is True and mc["cgroup_controls_written"] is False
    assert mc["first_a"] == mc["fresh_b"] == {"rc":0,"errno":0}
    assert mc["repeat_a_recursiveprot"] == mc["repeat_a_plain"] == {"rc":-1,"errno":16}
    assert rb["success"] is True and rb["compile_only"] is True and rb["revision"] == "producer14-retirement-fixture-repair01"
    assert rb["candidate"] == "/home/alex/work/pocket4-supervisor-lmkd-fixture-r11-build-14-01/candidate"
    assert rb["resource_health"]["held_own_cgroup_gate_passed"] is True
    assert len(rb["commands"]) == 2 and all(c["returncode"] == 0 and not c["timed_out"] for c in rb["commands"])
    host_manifest = (HOST_PAIR / "manifest.json").read_bytes()
    assert sha(host_manifest) == "fab7226afa93d372a7ba7d025cd704ae4aba878f9fa5336490af72eca98e6593"
    for row in json.loads(host_manifest)["files"]:
        body = (HOST_PAIR / row["path"]).read_bytes()
        assert len(body) == row["bytes"] and sha(body) == row["sha256"]
    fixture_manifest = (FIXTURE / "manifest.json").read_bytes()
    assert sha(fixture_manifest) == "6ae91802b992dba1d48c725e99e51a7daade464f4c5006f78575050f759bcccb"
    for row in json.loads(fixture_manifest)["files"]:
        body = (FIXTURE / row["path"]).read_bytes()
        assert len(body) == row["bytes"] and sha(body) == row["sha256"]
    fixture_paths = {"runtime/droidloom-pressure-relay/src/lib.rs",
                     "runtime/droidloom-pressure-relay/src/lifecycle_bootstrap.rs"}
    for relative in fixture_paths:
        before = (FIXTURE / "preimage" / relative).read_bytes()
        after = (FIXTURE / "candidate" / relative).read_bytes()
        assert before == (HOST_PAIR / "candidate" / relative).read_bytes()
        marker = b"#[cfg(test)]\nmod tests {"
        assert before.count(marker) == after.count(marker) == 1
        assert before.split(marker, 1)[0] == after.split(marker, 1)[0]
    cfg = json.loads((RUST / "payload.json").read_bytes())
    assert cfg["source_manifest_sha256"] == sha(fixture_manifest)
    assert cfg["original_diff_sha256"] == sha((FIXTURE / "source.diff").read_bytes())
    assert set(cfg["overlays"]) == fixture_paths
    for relative, row in cfg["overlays"].items():
        assert row["text"].encode() == (FIXTURE / "candidate" / relative).read_bytes()
    expected = dict(cfg["preimage"])
    expected.update({p: {"bytes": v["bytes"], "sha256": v["sha256"]} for p, v in cfg["overlays"].items()})
    assert rb["inputs_before"] == rb["inputs_after"] == expected
    assert rb["all_source_inventory_before_sha256"] == rb["all_source_inventory_after_sha256"]
    assert rr["success"] is True and rr["ordinary_controls_only"] is True and rr["revision"] == "producer14-retirement-fixture-repair01"
    assert rr["external_compile_sha256"] == args.rust_build_sha256
    assert rr["inputs_before"] == rr["inputs_after"] == expected
    assert rr["all_source_inventory_before_sha256"] == rr["all_source_inventory_after_sha256"] == rb["all_source_inventory_before_sha256"]
    assert rr["rust_tests_passed"] == {"droidloom-pressure-relay": 37, "droidloom-supervisor": 122}
    assert rr["ordinary_ipc_passed"] == 7 and rr["worker_context_passed"] is True and rr["actual_compiled_entry_abi_passed"] is True
    assert len(rr["commands"]) == 7 and all(c["returncode"] == 0 and not c["timed_out"] for c in rr["commands"])
    assert rr["resource_health"]["held_own_cgroup_gate_passed"] is True
    assert not rb["full_owner_runtime_qualified"] and not rr["full_owner_runtime_qualified"]
    assert cb["kind"] == "p4-init-cgroup-handoff-build01" and cb["success"] is True and cb["errors"] == []
    assert cb["all_inputs_unchanged"] is True and cb["Android_actual_MD_equals_preflight"] is True
    assert cb["Android_input_count"] == 140 and cb["Android_needed"] == ["libc.so"]
    assert [(v["name"], v["passed"]) for v in cb["host_control_results"]] == [
        ("protocol", 20), ("protocol-close-errno", 20), ("diagnostic", 7), ("cgroup-view", 8)]
    assert len(cb["commands"]) == 16 and all(c["returncode"] == 0 and not c["timed_out"] and c["child_reaped"] for c in cb["commands"])
    assert cb["resource_health"]["held_own_cgroup_gate_passed"] is True
    assert not cb["Android_constructor_executed"] and not cb["installed_files_changed"]
    pair_manifest = (PAIR / "manifest.json").read_bytes()
    assert sha(pair_manifest) == cb["source_manifest_sha256"] == "64200d271f96217fbdb8518960250661dff4211dc62fa94a575c165eedd88de5"
    for name, row in cb["source_before"].items():
        raw = (PAIR / "candidate/android" / name).read_bytes()
        assert row["bytes"] == len(raw) and row["sha256"] == sha(raw)
    assert len(cb["source_before"]) == 8
    barrier = cb["Android_artifact"]
    assert barrier["path"] == "/opt/p4-init-cgroup-handoff-20261105-build-01/libdroidloom_init_relay.so"
    assert barrier["uid"] == barrier["gid"] == 0 and not barrier["mode"] & 0o6022
    assert barrier["inode"] > 0 and barrier["bytes"] > 0
    old_manifest = (OLD / "manifest.json").read_bytes()
    assert sha(old_manifest) == "1cc0ff739afbe642255103e035d1379ac686b77c8b8ac3d1849f56ff984ecb3e"
    for row in json.loads(old_manifest)["files"]:
        body = (OLD / row["path"]).read_bytes()
        assert len(body) == row["bytes"] and sha(body) == row["sha256"]
    old_plan = json.loads((OLD / "plan.json").read_bytes())
    def remap(value):
        if isinstance(value, str):
            return value.replace(OLD_PREFIX, PREFIX)
        if isinstance(value, list):
            return [remap(x) for x in value]
        if isinstance(value, dict):
            return {k: remap(v) for k, v in value.items()}
        return value
    plan = remap(old_plan)
    attempt = os.urandom(32).hex()
    assert attempt != old_plan["attempt_nonce"] and attempt != "0" * 64
    plan.update(kind="owned-real-producer14-normal01-fixture-repair01",
                scope="REAL_OWNER_ABI3_PINNED_CAUSE_TERMINAL_DRAIN_FIRST_ACTIVE_ORIGINAL_RETIREMENT",
                attempt_nonce=attempt, description="Pocket4 Owner14 ABI3 NORMAL01 " + attempt)
    plan["spec"]["host_uid"] = 61286
    plan["spec"]["subordinate_uids"]["start"] = 20900000
    plan["spec"]["subordinate_gids"]["start"] = 20900000
    plan["spec"]["runtime_dir"] = "/run/droidloom/cells/u61286"
    for role in ("droidloomd", "droidloom-supervisor", "droidloom-psi-owner"):
        row = copy.deepcopy(rb["artifacts"][role])
        assert row["path"] == "/home/alex/work/pocket4-supervisor-lmkd-fixture-r11-build-14-01/target/debug/" + role
        assert row["mode"] & 0o111 and not row["mode"] & 0o6022 and row["inode"] > 0 and row["bytes"] > 0
        row["destination"] = "bin/" + role
        plan["artifacts"][role] = row
    plan["artifacts"]["init-barrier"] = {key: barrier[key] for key in ("path", "bytes", "sha256", "device", "inode")}
    plan["artifacts"]["init-barrier"].update(mode=stat.S_IMODE(barrier["mode"]), destination="lib/libdroidloom_init_relay.so")
    relay = plan["spec"]["pressure_relay"]
    for name, role in (("broker", "droidloom-psi-owner"), ("entry_supervisor", "droidloom-supervisor"), ("init_barrier", "init-barrier")):
        relay[name]["sha256"] = plan["artifacts"][role]["sha256"]
    plan["actual_compile_receipt"] = {"path": str(args.rust_build_receipt), "bytes": len(rb_raw), "sha256": args.rust_build_sha256}
    plan["actual_ordinary_receipt_sha256"] = args.rust_run_sha256
    plan["projection_build_receipt_sha256"] = args.android_build_sha256
    plan["paired_projection_source_manifest_sha256"] = sha(pair_manifest)
    plan["init_protocol_abi"] = 3
    plan["entry_abi"] = "droidloom-relay-entry-v3"
    # All preceding failed generation receipts remain in immutable predecessor plans.
    plan["earlier_failure_chain"] = {"earlier": old_plan["earlier_failure_chain"], "previous": old_plan["predecessor_failure"]}
    predecessor_path = BASE.parent / "root-recovery-20261104-02/evidence/owner11-normal01-runtime-read01/runtime-result.json"
    predecessor_raw = predecessor_path.read_bytes()
    assert sha(predecessor_raw) == "a04dbc0f1073c5ffb5f7fdbd549618af4b316a98688d3ecfe0622d05ef98303d"
    assert json.loads(predecessor_raw)["success"] is False
    previous_runtime = json.loads(predecessor_raw)
    previous_cleanup = previous_runtime["exact_unit_cleanup"]
    assert all(previous_cleanup[key] is True for key in ("cgroup_absent", "original_actor_dead", "unit_not_found"))
    assert previous_runtime["main_before"] == previous_runtime["main_before_gate"] == previous_runtime["main_after"]
    previous_audit = previous_runtime["actor_result"]["latest_status"]["relay_lifecycle"]
    assert previous_audit["recording_incomplete"] is False and previous_audit["recording_error"] is None
    assert previous_audit["retirement_failure"]["message"] == "rejected: lifecycle bootstrap disconnected"
    assert previous_audit["cleanup_failure"] is not None
    assert previous_audit["first_failure"]["message"] == "owned process generation is dead or changed"
    previous_details = {row["detail"]["event"]: row["detail"] for row in previous_audit["records"]}
    assert len(previous_details) == len(previous_audit["records"]) == 9
    assert list(previous_details) == ["prepared", "owner_attached", "init_hello", "broker_ready",
        "init_project_sent", "init_projected_accepted", "init_commit_sent", "init_done_accepted", "retiring"]
    assert previous_runtime["actor_result"]["latest_status"]["state"] == "cleanup_failed"
    cause_review_path = BASE / "owner11-retirement-cause-actual-review-01/report.json"
    cause_review_raw = cause_review_path.read_bytes()
    assert sha(cause_review_raw) == "79b248d4313baab3843a92e87fa06b61a47f9f7381947b80ea6979c1e96a747d"
    cause_review = json.loads(cause_review_raw)
    assert cause_review["original_runtime"]["sha256"] == sha(predecessor_raw)
    assert cause_review["original_Owner_retirement_completed"] is False
    assert cause_review["specific_relative_name_base_or_role_observed"] is False
    assert cause_review["missing_public_projection_proved"] is False
    assert cause_review["decoded_original_causes"] == {
        "relay_reason": "open relative pinned directory: No such file or directory (os error 2)",
        "lifecycle_error": "rejected: relay service retired; exact old cell requires lifecycle recovery"}
    previous_stderr = (BASE.parent / "root-recovery-20261104-02/evidence/owner11-normal01-logs01/files/evidence/daemon.stderr").read_bytes()
    assert len(previous_stderr) == 2017 and sha(previous_stderr) == "ba0e15b7b1b8992f9fd77169e3f4d17b2687a0aafca9b6d28d2344cfa39dd6c6"
    cause_lines = [line for line in previous_stderr.decode().splitlines()
                   if line.startswith("droidloom-psi-owner: retirement-cause-v1 ")]
    assert len(cause_lines) == 1
    actual_cause = json.loads(cause_lines[0].split("retirement-cause-v1 ", 1)[1])
    assert actual_cause == cause_review["retirement_cause_v1"]
    assert actual_cause["nonce"] == previous_audit["nonce"]
    assert actual_cause["granted"] is False and actual_cause["faulted"] is True
    plan["predecessor_failure"] = {
        "runtime_sha256": sha(predecessor_raw),
        "attempt_nonce": old_plan["attempt_nonce"], "replayed": False,
        "observed_boundary": "actual InitHello, BrokerReady, PROJECTED, COMMIT and DONE; failed before ACTIVE; original retirement incomplete",
        "old_owner_original_resource_retirement_passed": False,
        "old_owner_retirement_error": previous_audit["retirement_failure"]["message"],
        "outer_exact_cleanup_passed": True,
        "generic_pinned_openat_ENOENT_observed": True,
        "specific_relative_name_base_or_role_observed": False,
        "missing_public_projection_proved": False,
        "retirement_cause_review_sha256": sha(cause_review_raw),
        "original_daemon_stderr_sha256": sha(previous_stderr),
        "diagnostic_gap": "exact relative name, held base and validated caller role were omitted; error/process-death ordering is not proved",
        "old_failure_cause_not_inferred_from_blkio_cpuset_or_SIGHUP": True,
    }
    assert plan["broker_bootstrap_source_manifest_sha256"] == "019b34bc655bf76235339b533917d523fd2e5db3355214e5a5466e6a61ee3068"
    # Preserve the existing Producer11 diagnostic's own historical contract.
    assert plan["broker_retirement_diagnostic_source_manifest_sha256"] == "259154ae622c5c7ae5d29ca11b3a971dfc7e194ae6c9760b3b3de52e0b41a190"
    assert plan["retirement_diagnostic_contract"] == old_plan["retirement_diagnostic_contract"]
    diagnostic_manifest = (DIAGNOSTIC / "manifest.json").read_bytes()
    assert sha(diagnostic_manifest) == "963f7055854ba25ebc4fb9a9cd2dbf1e59d5a4200363d2fa1222003c341b6bfb"
    for row in json.loads(diagnostic_manifest)["files"]:
        body = (DIAGNOSTIC / row["path"]).read_bytes()
        assert len(body) == row["bytes"] and sha(body) == row["sha256"]
    for relative in ("runtime/droidloom-pressure-relay/src/lib.rs", "runtime/droidloom-pressure-relay/src/lifecycle_relay.rs"):
        assert (HOST_PAIR / "candidate" / relative).read_bytes() == (DIAGNOSTIC / "candidate" / relative).read_bytes()
    plan["pinned_io_diagnostic_source_manifest_sha256"] = sha(diagnostic_manifest)
    plan["pinned_io_diagnostic_contract"] = {
        "scope": "failure-only relative open name/flags/optional held base and validated caller context",
        "original_errno_preserved_before_optional_fstat": True,
        "retry_fallback_or_authority_change": False,
        "diagnostic_itself_qualifies_ACTIVE_or_enrollment": False}
    plan["terminal_drain_source_manifest_sha256"] = sha(host_manifest)
    plan["terminal_drain_contract"] = {
        "scope": "public LifecycleBroker.retire transaction",
        "existing_nonce_scope_AUDIT_status_and_exact_child_exit_required": True,
        "predrain_itself_qualifies_nothing": True,
        "one_request_only_and_original_maximum_two_seconds": True,
        "retirement_error_poison_is_sticky": True,
        "public_receive_progress_independent_error_global_poison_changed": False,
        "old_Owner11_failure_reclassified": False,
        "local_fixture_deterministic_send_race_branch_coverage_claimed": False}
    prior_ordinary_raw = (FIXTURE / "evidence/actual-producer13-ordinary-failed.json").read_bytes()
    assert sha(prior_ordinary_raw) == "cc26182f01c5241d6766dfb356263fa6efc7b6499a05684e0447895935ad523e"
    prior_ordinary = json.loads(prior_ordinary_raw)
    assert prior_ordinary["success"] is False and len(prior_ordinary["commands"]) == 3
    assert [row["returncode"] for row in prior_ordinary["commands"]] == [0, 0, 101]
    assert prior_ordinary["external_compile_sha256"] == "9a2cf0087ff99b6834fc2b3a963e03629a14acc21af1a8d67f2b5081bbb22e8e"
    prior_stdout = (FIXTURE / "evidence/actual-producer13-relay-command.stdout").read_bytes()
    assert len(prior_stdout) == 4483 and sha(prior_stdout) == "8a8537257b6bea7e1ca04031cf7d5f40143812cd71e6f7d1fdfd5082e911d528"
    assert prior_ordinary["commands"][2]["stdout_pin"]["sha256"] == sha(prior_stdout)
    assert "test result: FAILED. 35 passed; 2 failed;" in prior_stdout.decode()
    plan["fixture_repair_source_manifest_sha256"] = sha(fixture_manifest)
    plan["fixture_repair_contract"] = {
        "production_prefixes_unchanged_from13": True,
        "only_two_test_fixtures_changed": True,
        "faulted_requires_incomplete_codec_not_changed": True,
        "dead_held_proc_errno_compared_with_raw_syscall": True,
        "prior_ordinary_failure_preserved": True,
        "prior_ordinary_receipt_sha256": sha(prior_ordinary_raw),
        "prior_relay_stdout_sha256": sha(prior_stdout),
        "prior_relay_passed": 35, "prior_relay_failed": 2,
        "prior_supervisor_IPC_executed": False,
        "NORMAL13_never_prepared_or_executed": True}
    plan["broker_bootstrap_source_contract"] = {"magic": "P4BOOT2!", "version": 2, "layout": 3,
                                                "fallback_allowed": False, "wire_execution_observed_by_this_generator": False}
    plan["mechanism_evidence"] = {"report_sha256": "4a6f12bac1b20679596f7e6b2484662adaa90299c823bd957e24e2919051b4a6",
                                  "scope": "owned host shared-initial-userns distinct-mntns socket projection; not production constructor"}
    plan["cgroup_mount_mechanism_evidence"] = {"report_sha256":args.mount_mechanism_sha256,
        "scope":"owned shared-initial-userns/new-cgroup-mntns first/repeated/fresh mount with exact cleanup; not old Owner08 sender attribution"}
    canonical = json.dumps(plan["spec"], ensure_ascii=False, separators=(",", ":")).encode()
    plan["canonical_spec_sha256"] = sha(canonical)
    plan["status"] = "SOURCE_FROZEN_PREPARE_AND_RUNTIME_NOT_SUBMITTED"
    assert plan["main"] == old_plan["main"] and plan["base"] == old_plan["base"] and plan["outer_limits"] == old_plan["outer_limits"]
    assert plan["artifacts"]["lmkd"] == old_plan["artifacts"]["lmkd"]
    assert plan["presenter"] == old_plan["presenter"] and plan["tools_sha256"] == old_plan["tools_sha256"]
    # These are private namespace-local helper paths, created anew by the
    # unchanged actor. Their legacy label is not a reused host path or process.
    assert plan["spec"]["denial_socket"] == old_plan["spec"]["denial_socket"]
    assert plan["control_socket"] == old_plan["control_socket"]
    rust = BASE / "producer07-audit-freeze-02/source/runtime/droidloom-supervisor/src"
    def fields(text, name):
        return re.findall(r"^\s*pub\s+(\w+)\s*:", re.search(r"pub struct " + name + r"\s*\{(.*?)^\}", text, re.S | re.M)[1], re.M)
    lib = (rust / "lib.rs").read_text(); policy = (rust / "relay_lifecycle/policy.rs").read_text()
    assert list(plan["spec"]) == [name for name in fields(lib, "CellSpec") if name in plan["spec"]]
    assert list(relay) == fields(policy, "PressureRelaySpec")
    for name in ("broker", "entry_supervisor", "lmkd", "init_barrier"):
        assert list(relay[name]) == fields(policy, "RelayArtifact")
    source_freeze = BASE / "owner14-normal-source-freeze-01"
    assert sha((source_freeze / "manifest.json").read_bytes()) == "e2ae7182ce3d2bcd8c8aae249efd536999a9082c65d84ff8cf23cecb68e8b81b"
    for row in json.loads((source_freeze / "manifest.json").read_bytes())["files"]:
        raw = (source_freeze / row["path"]).read_bytes()
        assert len(raw) == row["bytes"] and sha(raw) == row["sha256"]
    controls_raw = (source_freeze / "source-review.json").read_bytes()
    controls = json.loads(controls_raw)
    assert controls["actual_runtime_executed"] is False and controls["plan_generated"] is False
    assert controls["fixed_profile_controls"] == [
        {"case": "new_profile", "accepted": True}, {"case": "new_paths", "accepted": True},
        {"case": "old_kind_rejected", "accepted": False}, {"case": "short_nonce_rejected", "accepted": False},
        {"case": "old_scope_rejected", "accepted": False}, {"case": "old_unit_rejected", "accepted": False},
        {"case": "old_package_rejected", "accepted": False}, {"case": "old_state_rejected", "accepted": False}]
    # Only profile literals changed. Retain the earlier source-level init
    # observation controls without claiming an additional execution of them.
    observer_base = BASE / "owner13-normal-source-freeze-01"
    observer_raw = (observer_base / "init-observation-controls.json").read_bytes()
    observer = json.loads(observer_raw)
    assert observer["success"] is True and observer["passed"] == 11
    for name, digest in observer["pins"].items():
        assert sha((observer_base / "source" / name).read_bytes()) == digest
    def function_ast(path, name):
        return ast.dump(next(n for n in ast.parse(path.read_text()).body
                             if isinstance(n, ast.FunctionDef) and n.name == name))
    assert function_ast(observer_base / "source/actor.py", "observe_init_hello") == function_ast(source_freeze / "source/actor.py", "observe_init_hello")
    assert (observer_base / "source/qualify.py").read_bytes() == (source_freeze / "source/qualify.py").read_bytes()
    payload = {}; source_diff = ""
    for path in sorted((source_freeze / "source").glob("*.py")):
        body = path.read_bytes(); old = (OLD / "source" / path.name).read_bytes()
        ast.parse(body.decode()); compile(body, path.name, "exec")
        assert body == (source_freeze / "source" / path.name).read_bytes()
        if path.name in ("owned.py", "pinned_support.py", "qualify.py"):
            assert body == old
        payload[path.name] = {"bytes": len(body), "sha256": sha(body), "content": body.decode()}
        source_diff += "".join(difflib.unified_diff(old.decode().splitlines(True), body.decode().splitlines(True),
                                                 fromfile="normal11-01/source/" + path.name, tofile="normal14-01/source/" + path.name))
    assert len(payload) == 6
    plan_raw = pretty(plan)
    packet = json.dumps({"plan_utf8": plan_raw.decode(), "sources": payload}, ensure_ascii=False, separators=(",", ":")).encode()
    prepare_template = (OLD / "requests/prepare-template.py").read_text()
    prepare_stdin = prepare_template.replace("__PACKET_SHA256__", repr(sha(packet))).replace("__PACKET_BASE64__", repr(base64.b64encode(packet).decode()))
    ast.parse(prepare_stdin)
    request = json.loads((OLD / "requests/prepare-request.json").read_bytes())
    request.update(stdin=prepare_stdin, idempotency_key="p4-owner14-normal01-prepare01-" + sha(prepare_stdin.encode())[:16])
    old_coordinator = (OLD / "source/coordinator.py").read_bytes()
    runtime = (OLD / "requests/runtime-stdin-template.py").read_text().replace(OLD_PREFIX, PREFIX)
    runtime = runtime.replace(sha(old_coordinator), payload["coordinator.py"]["sha256"])
    assert payload["coordinator.py"]["bytes"] == len(old_coordinator)
    ast.parse(runtime)
    runtime_request = json.loads((OLD / "requests/runtime-request-template.json").read_bytes())
    runtime_request.update(stdin=runtime, idempotency_key="p4-owner14-normal01-runtime01-__ACTUAL_PREPARED_SHA256_PREFIX16__")
    assert "__ACTUAL_PREPARED_SHA256__" in runtime
    # Actual source admission predicates, against the completed plan.
    for name, message in [("prepare.py", "wrong fixed profile"),
                          ("coordinator.py", "this controller accepts only its fixed fresh unit/package/state")]:
        tree = ast.parse(payload[name]["content"])
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and
                 n.func.attr == "need" and len(n.args) >= 2 and isinstance(n.args[1], ast.Constant) and n.args[1].value == message]
        assert len(calls) == 1
        assert eval(compile(ast.fix_missing_locations(ast.Expression(calls[0].args[0])), "actual-fixed-guard", "eval"),
                    {"__builtins__": {}, "len": len}, {"plan": plan}) is True
    OUT.mkdir(exist_ok=False)
    write("plan.json", plan_raw); write("cell.json", canonical)
    for name, row in payload.items():
        write("source/" + name, row["content"])
    write("source.diff", source_diff)
    write("plan.diff", "".join(difflib.unified_diff((OLD / "plan.json").read_text().splitlines(True), plan_raw.decode().splitlines(True),
                                                 fromfile="normal11-01/plan.json", tofile="normal14-01/plan.json")))
    write("requests/prepare-template.py", prepare_template)
    write("requests/prepare-stdin.py", prepare_stdin)
    write("requests/prepare-request.json", pretty(request))
    write("requests/runtime-stdin-template.py", runtime)
    write("requests/runtime-request-template.json", pretty(runtime_request))
    write("evidence/actual-rust-compile.json", rb_raw); write("evidence/actual-rust-ordinary.json", rr_raw)
    write("evidence/actual-android-build.json", cb_raw)
    write("evidence/actual-cgroup-mount-mechanism03.json", mm_raw)
    write("evidence/predecessor-normal11-runtime-failed.json", predecessor_raw)
    write("evidence/predecessor-normal11-cause-review.json", cause_review_raw)
    write("evidence/predecessor-normal11-daemon.stderr", previous_stderr)
    write("source-profile-review.json", controls_raw)
    write("derive_sources14.py", (source_freeze / "derive_sources14.py").read_bytes())
    write("evidence/prior-init-observation-controls.json", observer_raw)
    write("evidence/producer13-ordinary-failed.json", prior_ordinary_raw)
    write("evidence/producer13-relay-command.stdout", prior_stdout)
    write("freeze_normal14.py", Path(__file__).read_bytes())
    validation = {"kind": "owner14_normal01_source_binding", "actual_device_execution": False,
                  "rust_compile_sha256": args.rust_build_sha256, "rust_run_sha256": args.rust_run_sha256,
                  "android_build_sha256": args.android_build_sha256,
                  "source_pair_manifest_sha256": sha(pair_manifest), "old_runtime_failure_preserved": True,
                  "new_profile_predicates_accept_completed_plan": True, "new_profile_controls_passed": 8, "init_observation_controls_retained_not_rerun": 11,
                  "unchanged_runtime_sources": ["owned.py", "pinned_support.py", "qualify.py"],
                  "pinned_io_diagnostic_source_manifest_sha256": sha(diagnostic_manifest),
                  "terminal_drain_source_manifest_sha256": sha(host_manifest),
                  "fixture_repair_source_manifest_sha256": sha(fixture_manifest),
                  "producer13_ordinary_failure_still_preserved": True,
                  "old_owner_original_retirement_still_failed": True,
                  "old_external_exact_cleanup_passed": True,
                  "original_Rust_field_order_verified": True, "canonical_spec_sha256": sha(canonical),
                  "published_plan_sha256": sha(plan_raw),
                  "expected_prepared_serialized_plan_sha256": sha((json.dumps(plan, sort_keys=True, indent=2) + "\n").encode()),
                  "prepare_packet_sha256": sha(packet), "prepare_stdin_sha256": sha(prepare_stdin.encode()),
                  "prepare_request_sha256": sha((OUT / "requests/prepare-request.json").read_bytes()),
                  "idempotency_key": request["idempotency_key"], "prepare_submitted": False,
                  "runtime_template_requires_actual_prepared_pin": True,
                  "synthetic_uid_subid_live_absence_still_required": True,
                  "Main_host_network_or_installed_service_modified": False}
    write("source-binding-result.json", pretty(validation))
    write("README.md", """# Fresh real Owner14 NORMAL01: pinned I/O cause and strict terminal drain

This plan requires the actual successful Producer14 matching compile and ordinary
receipts, including 37 relay / 122 supervisor library tests, two targeted public
retirement controls, seven IPC controls, worker-context and entry ABI3. The original
ABI3 Android DSO, LMKD r6, P4BOOT2/layout3 and cgroup mount mechanism remain fixed.

Diagnostic12 records the original failed relative open name/flags/held base and
validated caller role without retry or relaxed authorization. Combined13 adds
terminal-aware retirement: predrain only feeds the unchanged strict receiver;
a closed send can be discharged only by the complete validated AUDIT/status and
exact child exit. Bare HUP/death cannot qualify, retirement errors stay poisoned,
and the original two-second deadline and one-request contract remain.

Producer14 changes only two test fixtures after the original producer13 ordinary
run failed 35/37 relay tests. That failure remains fixed evidence; its supervisor
and IPC stages did not run. Production13 diagnostics and retirement remain
unchanged. No NORMAL13 prepare or runtime was executed. The new expected suite
must actually pass before this plan can be created.

Owner11 remains failed before ACTIVE. Its generic pinned-openat ENOENT is retained;
the precise relative path/role and error-versus-death order are not proved. Its
original resource retirement failed; later outer exact cleanup completed. The new
patch does not retroactively mark either the original run or its retirement green.
Blkio/cpuset/SIGHUP and external kernel lines are not used as causal evidence.

The runtime-script changes are only fresh profile/root/unit and labels.
qualify.py, owned.py and pinned_support.py are byte-identical to NORMAL11.
Required scope is actual init HELLO/PROJECTED/COMMIT/DONE, broker ACTIVE, original
public Stop, exact child deaths, joined retirement and domain removal. The typed
HELLO-matching init identity and three clocks remain mandatory.

Outer5GiB/inner4GiB, zero swap, CPU1, original deadlines, native 70/700ms PSI
defaults, one-shot claims, private dbus/sway/presenter, Main fences and exact cleanup
remain unchanged. Fresh UID61286 and subordinate range20900000+100000 must pass
live absence checks. No installed service, account/subid table or host network is
changed. Runtime requires the actual prepared SHA and Root dispatch.

RC/reinit WIP is excluded. Real pressure effects, property reload, installed
lifecycle and all-App readiness remain open. Ordinary controls are not actual
Owner qualification or deterministic coverage of every send-close scheduling race.
""")
    rows = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file():
            raw = path.read_bytes()
            rows.append({"path": str(path.relative_to(OUT)), "bytes": len(raw), "sha256": sha(raw)})
    write("manifest.json", pretty({"kind": "owner14_normal01_frozen", "runtime_executed": False, "files": rows}))
    print(json.dumps({"root": str(OUT), "manifest_sha256": sha((OUT / "manifest.json").read_bytes()),
                      "prepare_request_bytes": len((OUT / "requests/prepare-request.json").read_bytes()), **validation}, indent=2))


if __name__ == "__main__":
    main()
