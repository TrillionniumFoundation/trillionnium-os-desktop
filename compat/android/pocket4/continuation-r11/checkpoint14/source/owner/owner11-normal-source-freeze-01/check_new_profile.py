#!/usr/bin/env python3
"""Run exact source predicates only; no lifecycle/namespace execution."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "source"
sys.path.insert(0, str(SOURCE))
import qualify


def sha(body):
    return hashlib.sha256(body).hexdigest()


def main():
    records = []
    nonce = "12" * 32
    def wire(kind):
        out = bytearray(128)
        out[:8] = b"P4IBV3!!"
        for offset, size, value in [(8, 4, 3), (12, 4, kind), (48, 8, 7), (56, 8, 11),
                                     (64, 4, 1069), (68, 4, 1069), (72, 4, 0o600)]:
            out[offset:offset + size] = value.to_bytes(size, "little")
        out[16:48] = bytes.fromhex(nonce)
        return out.hex()
    detail = {"init_hello": {"init": {"hello_wire_hex": wire(1)}},
              "broker_ready": {"status": {"endpoint": {"device": 7, "inode": 11}}}}
    for kind, event in [(2, "init_project_sent"), (3, "init_projected_accepted"),
                        (4, "init_commit_sent"), (5, "init_done_accepted")]:
        detail[event] = {"wire_hex": wire(kind)}
    assert qualify.qualify_init_v3(detail, nonce) is True
    records.append({"case": "exact_ABI3_nonce_phase_projection_echo", "accepted": True})
    def mutate_hex(value, event, offset, data):
        if event == "init_hello":
            row, key = value[event]["init"], "hello_wire_hex"
        else:
            row, key = value[event], "wire_hex"
        body = bytearray.fromhex(row[key]); body[offset:offset + len(data)] = data
        row[key] = body.hex()
    mutations = [
        ("old_numeric_abi2", lambda v: mutate_hex(v, "init_hello", 8, (2).to_bytes(4, "little"))),
        ("old_magic_v2", lambda v: mutate_hex(v, "init_project_sent", 0, b"P4IBV2!!")),
        ("old_numeric_abi1", lambda v: mutate_hex(v, "init_hello", 8, (1).to_bytes(4, "little"))),
        ("old_magic_v1", lambda v: mutate_hex(v, "init_project_sent", 0, b"P4IBV1!!")),
        ("wrong_actual_nonce", lambda v: mutate_hex(v, "init_done_accepted", 16, bytes.fromhex("34" * 32))),
        ("wrong_phase", lambda v: mutate_hex(v, "init_commit_sent", 12, (3).to_bytes(4, "little"))),
        ("changed_echo_payload", lambda v: mutate_hex(v, "init_projected_accepted", 56, (12).to_bytes(8, "little"))),
        ("unexpected_reserved_project_fields", lambda v: [mutate_hex(v, event, 127, b"\x01") for event in
            ("init_project_sent", "init_projected_accepted", "init_commit_sent", "init_done_accepted")]),
        ("different_ready_inode", lambda v: v["broker_ready"]["status"]["endpoint"].update(inode=12)),
        ("nonhex_wire", lambda v: v["init_hello"]["init"].update(hello_wire_hex="g" * 256)),
    ]
    for name, change in mutations:
        value = copy.deepcopy(detail); change(value)
        try:
            qualify.qualify_init_v3(value, nonce)
        except RuntimeError:
            records.append({"case": name, "accepted": False})
        else:
            raise AssertionError(name + " accepted")
    def expression(name, message):
        source = (SOURCE / name).read_text()
        calls = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call) and
                 isinstance(n.func, ast.Attribute) and n.func.attr == "need" and len(n.args) >= 2 and
                 isinstance(n.args[1], ast.Constant) and n.args[1].value == message]
        assert len(calls) == 1
        return compile(ast.fix_missing_locations(ast.Expression(calls[0].args[0])), "actual-profile-guard", "eval")
    scope = "REAL_OWNER_ABI3_RETAINED_CAUSE_FIRST_ACTIVE_ORIGINAL_RETIREMENT"
    plan = {"attempt_nonce": nonce, "kind": "owned-real-producer11-normal01-retirement-cause01", "scope": scope,
            "unit": "p4-owner11-normal-20261105-01.service", "package": "/opt/p4-owner11-normal-20261105-01",
            "state": "/opt/p4-owner11-normal-20261105-01-state"}
    profile = expression("prepare.py", "wrong fixed profile")
    paths = expression("coordinator.py", "this controller accepts only its fixed fresh unit/package/state")
    for label, code, value, expected in [
        ("new_profile", profile, plan, True), ("new_paths", paths, plan, True),
        ("old_profile", profile, {**plan, "kind": "owned-real-producer10-normal01-broker-holding01"}, False),
        ("old_scope", profile, {**plan, "scope": "REAL_OWNER_ABI3_BROKER_HOLDING_FIRST_ACTIVE_ORIGINAL_RETIREMENT"}, False),
        ("short_nonce", profile, {**plan, "attempt_nonce": nonce[:-1]}, False),
    ] + [("old_" + key, paths, {**plan, key: value}, False) for key, value in [
        ("unit", "p4-owner10-normal-20261105-01.service"),
        ("package", "/opt/p4-owner10-normal-20261105-01"),
        ("state", "/opt/p4-owner10-normal-20261105-01-state"),
    ]]:
        got = eval(code, {"__builtins__": {}, "len": len}, {"plan": value})
        assert got is expected
        records.append({"case": label, "accepted": got})
    pins = [{"path": p.name, "bytes": len(b), "sha256": sha(b)}
            for p in sorted(SOURCE.glob("*.py")) for b in [p.read_bytes()]]
    report = {"kind": "owner11_exact_qualifier_and_profile_controls_01", "success": True,
              "scope": "Pure exact source ABI/echo/phase/profile controls; no full Owner qualification or device execution.",
              "source_pins": pins, "cases": records, "passed": len(records), "actual_runtime_executed": False}
    body = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    with (ROOT / "new-profile-controls.json").open("xb") as file:
        file.write(body)
    print(json.dumps({"path": str(ROOT / "new-profile-controls.json"), "bytes": len(body), "sha256": sha(body), "passed": len(records)}))


if __name__ == "__main__":
    main()
