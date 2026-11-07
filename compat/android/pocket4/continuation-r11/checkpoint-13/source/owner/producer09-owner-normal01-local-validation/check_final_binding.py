#!/usr/bin/env python3
"""Read-only local byte/AST binding check; no device or frozen module execution."""
from pathlib import Path
import ast
import base64
import hashlib
import json

BASE = Path(__file__).resolve().parent.parent
FROZEN = BASE / "owner09-normal01-freeze-01"
OLD = BASE / "owner08-normal01-freeze-01"
SOURCE = BASE / "owner09-normal-source-freeze-01"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    manifest_raw = (FROZEN / "manifest.json").read_bytes()
    assert sha(manifest_raw) == "c3b70987189ac3621d819d3563b629510da69c9cbe780781ba3cbcd973bb871a"
    rows = json.loads(manifest_raw)["files"]
    for row in rows:
        raw = (FROZEN / row["path"]).read_bytes()
        raw.decode("utf-8")
        assert len(raw) == row["bytes"] and sha(raw) == row["sha256"]
    for path in FROZEN.rglob("*.py"):
        ast.parse(path.read_bytes())
    request_raw = (FROZEN / "requests/prepare-request.json").read_bytes()
    request = json.loads(request_raw)
    old_request = json.loads((OLD / "requests/prepare-request.json").read_bytes())
    stdin = (FROZEN / "requests/prepare-stdin.py").read_text()
    assert request["stdin"] == stdin
    assert {k: v for k, v in request.items() if k not in ("stdin", "idempotency_key")} == {
        k: v for k, v in old_request.items() if k not in ("stdin", "idempotency_key")}
    values = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in ast.parse(stdin).body
        if isinstance(node, ast.Assign) and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in ("PACKET_SHA256", "PACKET_BASE64")
    }
    packet_raw = base64.b64decode(values["PACKET_BASE64"], validate=True)
    assert sha(packet_raw) == values["PACKET_SHA256"]
    packet = json.loads(packet_raw)
    plan_raw = (FROZEN / "plan.json").read_bytes()
    assert packet["plan_utf8"].encode() == plan_raw
    assert sorted(packet["sources"]) == sorted(p.name for p in (FROZEN / "source").glob("*.py"))
    for name, row in packet["sources"].items():
        raw = (FROZEN / "source" / name).read_bytes()
        assert row["content"].encode() == raw and len(raw) == row["bytes"] and sha(raw) == row["sha256"]
        assert raw == (SOURCE / "source" / name).read_bytes()
    expected_stdin = (FROZEN / "requests/prepare-template.py").read_text().replace(
        "__PACKET_SHA256__", repr(values["PACKET_SHA256"])).replace(
        "__PACKET_BASE64__", repr(values["PACKET_BASE64"]))
    assert stdin == expected_stdin
    plan = json.loads(plan_raw)
    old_plan = json.loads((OLD / "plan.json").read_bytes())
    assert all(plan[k] == old_plan[k] for k in ("base", "main", "outer_limits", "presenter", "tools_sha256"))
    assert plan["artifacts"]["lmkd"] == old_plan["artifacts"]["lmkd"]
    assert sha(json.dumps(plan["spec"], ensure_ascii=False, separators=(",", ":")).encode()) == plan["canonical_spec_sha256"]
    assert plan["spec"]["host_uid"] == 61281
    assert plan["spec"]["subordinate_uids"]["start"] == plan["spec"]["subordinate_gids"]["start"] == 20400000
    assert len(bytes.fromhex(plan["attempt_nonce"])) == 32 and plan["attempt_nonce"] != old_plan["attempt_nonce"]
    # The generator reused old diff display labels only. Validate the exact
    # four header pairs; do not alter either immutable source snapshot.
    old_diff = (SOURCE / "source.diff").read_bytes()
    new_diff = (FROZEN / "source.diff").read_bytes()
    assert old_diff.count(b"--- normal08/source/") == new_diff.count(b"--- normal07-03/source/") == 4
    assert old_diff.count(b"+++ normal09/source/") == new_diff.count(b"+++ normal09-01/source/") == 4
    assert new_diff.replace(b"--- normal07-03/source/", b"--- normal08/source/").replace(
        b"+++ normal09-01/source/", b"+++ normal09/source/") == old_diff
    print(json.dumps({
        "kind": "owner09_normal01_local_final_binding",
        "verified": True, "payload_count": len(rows),
        "manifest_sha256": sha(manifest_raw),
        "prepare_request_sha256": sha(request_raw),
        "prepare_stdin_bytes": len(stdin.encode()), "prepare_stdin_sha256": sha(stdin.encode()),
        "prepare_packet_sha256": values["PACKET_SHA256"],
        "source_diff_sha256": sha(new_diff), "source_only_diff_sha256": sha(old_diff),
        "diff_header_only_relabeling_exact": True,
        "plan_sha256": sha(plan_raw), "canonical_spec_sha256": plan["canonical_spec_sha256"],
        "source_count": len(packet["sources"]), "AST_and_packet_binding": True,
        "same_Main_base_presenter_resource_contract": True,
        "prepare_submitted_by_this_check": False, "runtime_executed": False,
        "previous_inline_check_failure": "Strict complete diff equality rejected four display-header pairs; all earlier byte, AST, packet, plan, resource and nonce assertions passed. Frozen sources were unchanged.",
        "request_controls": {k: v for k, v in request.items() if k != "stdin"},
    }, indent=2))


if __name__ == "__main__":
    main()
