#!/usr/bin/env python3
"""Freeze one fresh real Owner10 attempt from externally pinned actual builds."""
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
OLD = BASE / "owner09-normal01-freeze-01"
PAIR = BASE / "cgroup-handoff-pair-freeze-01"
HOST_PAIR = BASE / "broker-holding-bootstrap-source-freeze-01"
RUST = BASE / "producer10-broker-controller-freeze-01"
OUT = BASE / "owner10-normal01-freeze-01"
PREFIX = "p4-owner10-normal-20261105-01"
OLD_PREFIX = "p4-owner09-normal-20261105-01"


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
    assert rb["success"] is True and rb["compile_only"] is True and rb["revision"] == "producer10-broker-holding01"
    assert rb["candidate"] == "/home/alex/work/pocket4-supervisor-lmkd-broker-r11-build-10-01/candidate"
    assert rb["resource_health"]["held_own_cgroup_gate_passed"] is True
    assert len(rb["commands"]) == 2 and all(c["returncode"] == 0 and not c["timed_out"] for c in rb["commands"])
    host_manifest = (HOST_PAIR / "manifest.json").read_bytes()
    assert sha(host_manifest) == "019b34bc655bf76235339b533917d523fd2e5db3355214e5a5466e6a61ee3068"
    for row in json.loads(host_manifest)["files"]:
        body = (HOST_PAIR / row["path"]).read_bytes()
        assert len(body) == row["bytes"] and sha(body) == row["sha256"]
    cfg = json.loads((RUST / "payload.json").read_bytes())
    assert cfg["source_manifest_sha256"] == sha(host_manifest)
    assert cfg["original_diff_sha256"] == sha((HOST_PAIR / "source.diff").read_bytes())
    expected = dict(cfg["preimage"])
    expected.update({p: {"bytes": v["bytes"], "sha256": v["sha256"]} for p, v in cfg["overlays"].items()})
    assert rb["inputs_before"] == rb["inputs_after"] == expected
    assert rb["all_source_inventory_before_sha256"] == rb["all_source_inventory_after_sha256"]
    assert rr["success"] is True and rr["ordinary_controls_only"] is True and rr["revision"] == "producer10-broker-holding01"
    assert rr["external_compile_sha256"] == args.rust_build_sha256
    assert rr["inputs_before"] == rr["inputs_after"] == expected
    assert rr["all_source_inventory_before_sha256"] == rr["all_source_inventory_after_sha256"] == rb["all_source_inventory_before_sha256"]
    assert rr["rust_tests_passed"] == {"droidloom-pressure-relay": 26, "droidloom-supervisor": 122}
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
    assert sha(old_manifest) == "c3b70987189ac3621d819d3563b629510da69c9cbe780781ba3cbcd973bb871a"
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
    plan.update(kind="owned-real-producer10-normal01-broker-holding01",
                scope="REAL_OWNER_ABI3_BROKER_HOLDING_FIRST_ACTIVE_ORIGINAL_RETIREMENT",
                attempt_nonce=attempt, description="Pocket4 Owner10 ABI3 NORMAL01 " + attempt)
    plan["spec"]["host_uid"] = 61282
    plan["spec"]["subordinate_uids"]["start"] = 20500000
    plan["spec"]["subordinate_gids"]["start"] = 20500000
    plan["spec"]["runtime_dir"] = "/run/droidloom/cells/u61282"
    for role in ("droidloomd", "droidloom-supervisor", "droidloom-psi-owner"):
        row = copy.deepcopy(rb["artifacts"][role])
        assert row["path"] == "/home/alex/work/pocket4-supervisor-lmkd-broker-r11-build-10-01/target/debug/" + role
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
    predecessor_path = BASE.parent / "root-recovery-20261104-02/evidence/owner09-normal01-runtime-read01/runtime-result.json"
    predecessor_raw = predecessor_path.read_bytes()
    assert sha(predecessor_raw) == "20a20009beca9d9eb64b0973acfdd749f3b2a8cc8c6ef1c417d517378a518a05"
    assert json.loads(predecessor_raw)["success"] is False
    plan["predecessor_failure"] = {
        "runtime_sha256": sha(predecessor_raw),
        "attempt_nonce": old_plan["attempt_nonce"], "replayed": False,
        "observed_boundary": "actual InitHello followed by lifecycle packet framing/ancillary rejection; no BrokerReady or ACTIVE",
        "old_owner_original_retirement_passed": False,
        "outer_exact_cleanup_passed": True,
        "separate_source_defect": "legacy broker bootstrap still required directly projected root and direct-root init membership",
        "specific_old_transport_error_cause_not_inferred_from_source": True,
    }
    plan["broker_bootstrap_source_manifest_sha256"] = sha(host_manifest)
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
    controls_raw = (WORK / "new-profile-controls.json").read_bytes()
    controls = json.loads(controls_raw)
    assert controls["success"] is True and controls["passed"] == 19
    for row in controls["source_pins"]:
        body = (WORK / "source" / row["path"]).read_bytes()
        assert len(body) == row["bytes"] and sha(body) == row["sha256"]
    observer_raw = (WORK / "init-observation-controls.json").read_bytes()
    observer = json.loads(observer_raw)
    assert observer["success"] is True and observer["passed"] == 11
    for name, digest in observer["pins"].items():
        assert sha((WORK / "source" / name).read_bytes()) == digest
    source_freeze = BASE / "owner10-normal-source-freeze-01"
    assert sha((source_freeze / "manifest.json").read_bytes()) == "a99ce79b13d2ffdc71020783be6b0113938a392ce315b383c857a4b915d3fc50"
    for row in json.loads((source_freeze / "manifest.json").read_bytes())["files"]:
        raw = (source_freeze / row["path"]).read_bytes()
        assert len(raw) == row["bytes"] and sha(raw) == row["sha256"]
    payload = {}; source_diff = ""
    for path in sorted((WORK / "source").glob("*.py")):
        body = path.read_bytes(); old = (OLD / "source" / path.name).read_bytes()
        ast.parse(body.decode()); compile(body, path.name, "exec")
        assert body == (source_freeze / "source" / path.name).read_bytes()
        if path.name in ("owned.py", "pinned_support.py", "qualify.py"):
            assert body == old
        payload[path.name] = {"bytes": len(body), "sha256": sha(body), "content": body.decode()}
        source_diff += "".join(difflib.unified_diff(old.decode().splitlines(True), body.decode().splitlines(True),
                                                 fromfile="normal09-01/source/" + path.name, tofile="normal10-01/source/" + path.name))
    assert len(payload) == 6
    plan_raw = pretty(plan)
    packet = json.dumps({"plan_utf8": plan_raw.decode(), "sources": payload}, ensure_ascii=False, separators=(",", ":")).encode()
    prepare_template = (OLD / "requests/prepare-template.py").read_text()
    prepare_stdin = prepare_template.replace("__PACKET_SHA256__", repr(sha(packet))).replace("__PACKET_BASE64__", repr(base64.b64encode(packet).decode()))
    ast.parse(prepare_stdin)
    request = json.loads((OLD / "requests/prepare-request.json").read_bytes())
    request.update(stdin=prepare_stdin, idempotency_key="p4-owner10-normal01-prepare01-" + sha(prepare_stdin.encode())[:16])
    old_coordinator = (OLD / "source/coordinator.py").read_bytes()
    runtime = (OLD / "requests/runtime-stdin-template.py").read_text().replace(OLD_PREFIX, PREFIX)
    runtime = runtime.replace(sha(old_coordinator), payload["coordinator.py"]["sha256"])
    assert payload["coordinator.py"]["bytes"] == len(old_coordinator)
    ast.parse(runtime)
    runtime_request = json.loads((OLD / "requests/runtime-request-template.json").read_bytes())
    runtime_request.update(stdin=runtime, idempotency_key="p4-owner10-normal01-runtime01-__ACTUAL_PREPARED_SHA256_PREFIX16__")
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
                                                 fromfile="normal09-01/plan.json", tofile="normal10-01/plan.json")))
    write("requests/prepare-template.py", prepare_template)
    write("requests/prepare-stdin.py", prepare_stdin)
    write("requests/prepare-request.json", pretty(request))
    write("requests/runtime-stdin-template.py", runtime)
    write("requests/runtime-request-template.json", pretty(runtime_request))
    write("evidence/actual-rust-compile.json", rb_raw); write("evidence/actual-rust-ordinary.json", rr_raw)
    write("evidence/actual-android-build.json", cb_raw)
    write("evidence/actual-cgroup-mount-mechanism03.json", mm_raw)
    write("evidence/predecessor-normal09-runtime-failed.json", predecessor_raw)
    write("new-profile-controls.json", controls_raw)
    write("check_new_profile.py", (WORK / "check_new_profile.py").read_bytes())
    write("check_init_observation.py", (WORK / "check_init_observation.py").read_bytes())
    write("init-observation-controls.json", observer_raw)
    write("freeze_normal10.py", Path(__file__).read_bytes())
    validation = {"kind": "owner10_normal01_source_binding", "actual_device_execution": False,
                  "rust_compile_sha256": args.rust_build_sha256, "rust_run_sha256": args.rust_run_sha256,
                  "android_build_sha256": args.android_build_sha256,
                  "source_pair_manifest_sha256": sha(pair_manifest), "old_runtime_failure_preserved": True,
                  "new_profile_predicates_accept_completed_plan": True, "new_ABI_and_profile_controls_passed": 19,
                  "unchanged_runtime_sources": ["owned.py", "pinned_support.py", "qualify.py"],
                  "broker_bootstrap_source_manifest_sha256": sha(host_manifest),
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
    write("README.md", """# Fresh real Owner10 NORMAL01: explicit broker holding bootstrap

Only this revision's successful producer10 Rust compile and ordinary receipts,
unchanged actual ABI3 Android DSO, and actual cgroup mount mechanism are bound.
The new real Owner sends P4BOOT2/version2/layout3 to the matching broker. Legacy
P4BOOT1 remains an explicit old fixture contract; there is no runtime fallback.
The old NORMAL09 failed cell and its unsuccessful original Owner retirement
remain immutable; its later outer exact cleanup does not qualify that lifecycle.

The only runtime-script changes are fresh fixed profile/root/unit and labels.
qualify.py, owned.py and pinned_support.py are byte-identical to NORMAL09. The
required path remains actual init HELLO/PROJECTED/COMMIT/DONE, broker ACTIVE,
original public Stop, exact child deaths, joined retirement and domain removal.
The typed HELLO-matching init pidfd/procdir/birth/executable/ten namespaces and
three-clock observation remain; external kernel lines remain unattributed.

Outer5GiB/inner4GiB, zero swap, CPU1, original deadlines, native 70/700ms PSI
defaults, one-shot claims, private dbus/sway/presenter, Main fences, held resource
gates and exact cleanup remain required. Fresh UID61282 and subordinate range
20500000+100000 must pass live absence checks. Main, installed daemon, account
and subid tables, and host networking are not changed.

Prepare is not submitted by this generator. Runtime needs its new actual
prepared SHA and root dispatch. RC/reinit WIP is excluded; real pressure effects,
property reload, installed lifecycle and all App readiness remain open.
""")
    rows = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file():
            raw = path.read_bytes()
            rows.append({"path": str(path.relative_to(OUT)), "bytes": len(raw), "sha256": sha(raw)})
    write("manifest.json", pretty({"kind": "owner10_normal01_frozen", "runtime_executed": False, "files": rows}))
    print(json.dumps({"root": str(OUT), "manifest_sha256": sha((OUT / "manifest.json").read_bytes()),
                      "prepare_request_bytes": len((OUT / "requests/prepare-request.json").read_bytes()), **validation}, indent=2))


if __name__ == "__main__":
    main()
