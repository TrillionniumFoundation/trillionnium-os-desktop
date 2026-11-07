#!/usr/bin/env python3
"""Exercise the unchanged real constructor with actual binding parameters.

Target is a metadata-only local fixture: no real process is opened, no transport
command is called, and no namespace/guard/record/runner callback may execute.
This checks the real constructor contract, not a mirror of its predicates.
"""
import sys
sys.dont_write_bytecode = True
import hashlib
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]


def load(path, name):
    value = types.ModuleType(name)
    value.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), "exec"), value.__dict__)
    return value


def main():
    support = load(HERE / "check_bound_controls.py", "local_fd_census_only")
    before = support.census()
    gate = load(HERE / "permission_capture_gate.py", "new46_source_gate")
    g, plan, loaded = gate.load_closure()
    raw = (PROJECT / "successor_audit_requests/native46_discovery_r1/actual/artifact.original.json").read_bytes()
    assert len(raw) == 112546 and hashlib.sha256(raw).hexdigest() == "69482778466e03dceff2defc85fb8f68880c360a3f112e129561a8fd5e6e5400"
    observation = json.loads(raw)
    target = types.SimpleNamespace(expected=observation["held_target"]["init"], helper_sha256=observation["held_target"]["helper_sha256"])
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("No callbacks or commands may run in a constructor-only control")
    old_scope = "44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f"
    checked = []
    for number, item in loaded.items():
        module = load(HERE / item["row"]["transport_file"], "batch_%02d_real_transport" % number)
        args = {"target": target, "environment": {key: "/constructor-fixture" for key in module.REQUIRED_ENV},
            "guard": forbidden, "record": forbidden, "runner": forbidden,
            "epoch_sha256": observation["guard_before"]["Main_epoch_sha256"],
            "init_pid": target.expected["pid"], "app_scope_sha256": item["request"]["app_scope"]["sha256"], "user": 0}
        assert module.EXPLICIT_SCOPE_SHA256 == plan["app_scope"]["sha256"] == args["app_scope_sha256"]
        assert module.FRAMEWORK_EPOCH_SHA256 == args["epoch_sha256"]
        assert module.HELD_HELPER_SHA256 == target.helper_sha256
        transport = module.BoundArun(**args)
        assert transport.target is target and transport._sequence == 0 and transport._poisoned is False
        try:
            module.BoundArun(**(args | {"app_scope_sha256": old_scope}))
        except module.TransportError as error:
            assert str(error) == "EXACT_NEW_READONLY_SERVICE_SCOPE_REQUIRED" and error.details["action_attempted"] is False
        else:
            raise AssertionError("Old47 scope must be rejected by unchanged constructor")
        checked.append({"batch": number, "actual49_constructor_accepted": True, "old47_scope_rejected": True,
                        "transport_methods_invoked": 0})
    for change, reason in (({"epoch_sha256": "0" * 64}, "EXACT_NEW_READONLY_SERVICE_SCOPE_REQUIRED"),
                           ({"target": types.SimpleNamespace(expected=target.expected, helper_sha256="0" * 64)}, "HELD_ENTRY_HELPER_PIN_DIFFERS")):
        try:
            module.BoundArun(**(args | change))
        except module.TransportError as error:
            assert str(error) == reason
        else:
            raise AssertionError("Original epoch/helper guard was weakened")
    original = load(HERE.parent / "bound-candidate-r1/batch-01/readonly_services_transport.py", "rejected_r1_original_transport")
    try:
        original.BoundArun(**args)
    except original.TransportError as error:
        assert str(error) == "EXACT_NEW_READONLY_SERVICE_SCOPE_REQUIRED"
    else:
        raise AssertionError("Original r1 rejection was not reproduced")
    assert not calls
    after = support.census()
    assert before == after
    print(json.dumps({"schema": "pocket4-fixed46-r2-real-constructor-controls-v1", "ok": True, "batches": checked,
        "actual_frozen_r1_constructor_rejection_reproduced": True, "wrong_epoch_rejected": True, "wrong_helper_rejected": True,
        "target_is_metadata_only_fixture": True, "target_values_from_actual_native46_observation": True,
        "environment_is_synthetic_constructor_fixture": True, "no_live_identity_qualification_claimed": True,
        "callback_invocations": len(calls), "Main_or_namespace_commands": 0, "remote_jobs": 0,
        "whole_process_FDs_before": before, "whole_process_FDs_after": after, "production_ready": False}, sort_keys=True))


if __name__ == "__main__":
    main()
