#!/usr/bin/env python3
"""Freeze eight-source ABI3 build with original exact Android link closure."""
import ast
import base64
import copy
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAIR = ROOT / "cgroup-handoff-pair-freeze-01"
OLD = ROOT / "init-socket-projection-build-freeze-01"
OUT = ROOT / "init-cgroup-handoff-build-freeze-01"
ACTUAL = ROOT.parent / "root-recovery-20261104-02/evidence/init-socket-projection-build01/build-result.json"
KIND = "p4-init-cgroup-handoff-build01"
REMOTE = "/opt/p4-init-cgroup-handoff-20261105-build-01"
PAIR_SHA = "64200d271f96217fbdb8518960250661dff4211dc62fa94a575c165eedd88de5"
ACTUAL_SHA = "b74dabc8c2cd8abcb4efe7de2cd35a95ec9ee5b29f364d33f055c0cd305972cd"


def sha(data): return hashlib.sha256(data).hexdigest()
def pretty(data): return json.dumps(data, sort_keys=True, indent=2) + "\n"


def write(name, data):
    data = data.encode() if isinstance(data, str) else data
    data.decode("utf-8")
    path = OUT / name; path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as target: target.write(data)


def main():
    OUT.mkdir()
    manifest = (PAIR / "manifest.json").read_bytes(); assert sha(manifest) == PAIR_SHA
    for row in json.loads(manifest)["files"]:
        body = (PAIR / row["path"]).read_bytes()
        assert len(body) == row["bytes"] and sha(body) == row["sha256"]
    raw = ACTUAL.read_bytes(); assert sha(raw) == ACTUAL_SHA
    actual = json.loads(raw)
    assert actual["success"] and actual["all_inputs_unchanged"] and len(actual["commands"]) == 13
    assert all(c["returncode"] == 0 and c["child_reaped"] and not c["timed_out"] for c in actual["commands"])
    old_cfg = json.loads((OLD / "config.json").read_bytes()); cfg = copy.deepcopy(old_cfg)
    cfg["kind"], cfg["root"], cfg["source_manifest_sha256"] = KIND, REMOTE, PAIR_SHA
    payload = {}
    for name in old_cfg["payload"]:
        preimage = (PAIR / "preimage/android" / name).read_bytes()
        assert sha(preimage) == actual["source_before"][name]["sha256"] and len(preimage) == actual["source_before"][name]["bytes"]
    for source in sorted((PAIR / "candidate/android").iterdir()):
        body = source.read_bytes()
        payload[source.name] = {"bytes": len(body), "sha256": sha(body), "base64": base64.b64encode(body).decode()}
    assert len(payload) == 8 and set(payload) == set(old_cfg["payload"]) | {"cgroup_view_controls.c"}
    cfg["payload"] = payload
    old = (OLD / "build-template.py").read_text()
    template = old.replace("p4-init-socket-projection-build01", KIND).replace("p4-init-socket-projection-20261105-build-01", Path(REMOTE).name)
    before = "            ('diagnostic', 'diagnostic_controls.c', False, 7, 'owned_diagnostic_controls_passed')]:"
    after = "            ('diagnostic', 'diagnostic_controls.c', False, 7, 'owned_diagnostic_controls_passed'),\n            ('cgroup-view', 'cgroup_view_controls.c', False, 8, 'cases')]:"
    assert template.count(before) == 1; template = template.replace(before, after)
    assert template.replace(after, before).replace(KIND, "p4-init-socket-projection-build01").replace(Path(REMOTE).name, "p4-init-socket-projection-20261105-build-01") == old
    marker = "CFG = None  # Filled once by the local frozen-request generator."
    assert template.count(marker) == 1
    body = template.replace(marker, "CFG = " + repr(cfg))
    parsed = ast.parse(body)
    assignment = next(n for n in parsed.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CFG" for t in n.targets))
    assert ast.literal_eval(assignment.value) == cfg
    assignment.value = ast.Constant(None)
    assert ast.dump(parsed) == ast.dump(ast.parse(template)); compile(body, "frozen_matching_build", "exec")
    request = json.loads((OLD / "request.json").read_bytes()); request["stdin"] = body
    request["idempotency_key"] = "p4-init-cgroup-handoff01-build01-" + sha(body.encode())[:16]
    assert {k: v for k, v in cfg.items() if k not in ("root", "kind", "source_manifest_sha256", "payload")} == {k: v for k, v in old_cfg.items() if k not in ("root", "kind", "source_manifest_sha256", "payload")}
    assert request["args"] == ["-n", "/usr/bin/python3", "-I", "-B", "-"]
    assert request["cpu_quota_percent"] == 100 and request["memory_max_bytes"] == 536870912 and request["timeout_seconds"] == 180
    write("request.json", pretty(request)); write("build.py", body); write("build-template.py", template)
    write("build-template.diff", "".join(difflib.unified_diff(old.splitlines(True), template.splitlines(True), fromfile="ABI2/build-template.py", tofile="ABI3/build-template.py")))
    write("config.json", pretty(cfg)); write("resource_guard.py", (OLD / "resource_guard.py").read_bytes())
    write("make_android_build09.py", Path(__file__).read_bytes())
    write("validation.json", pretty({"schema": 1, "execution_status": "NOT_SUBMITTED", "source_pair_manifest_sha256": PAIR_SHA,
        "prior_actual_report_sha256": ACTUAL_SHA, "prior_source_preimages_verified": 7, "payload_count": 8,
        "original_input_count": len(cfg["original_inputs"]), "expected_Android_MD_count": 140,
        "original_Android_argv_unchanged": True, "resource_guard_unchanged": True,
        "template_only_kind_root_and_new_control_tuple_changed": True, "CFG_and_packet_AST_exact": True,
        "request_bytes": len((OUT / "request.json").read_bytes()), "request_sha256": sha((OUT / "request.json").read_bytes()),
        "stdin_bytes": len(body.encode()), "stdin_sha256": sha(body.encode()),
        "expected_commands": 16, "expected_controls": {"protocol": 20, "protocol_close_errno": 20, "diagnostic": 7, "cgroup_view": 8},
        "actual_Android_constructor_qualified": False, "actual_Owner_qualified": False}))
    write("README.md", """# ABI3 cgroup holding-view matching build

This create-only CPU1/512MiB/180s request binds seven exact previous actual
source preimages and eight frozen candidate C inputs. The original 147-input
Android compiler/link closure, four argv and 140-header MD target/equality
checks are unchanged. The new DSO must retain the same libc-only ELF contract.

The original 20 transport, 20 close-errno and seven projection controls remain;
the eight holding-view/stock-target owned file controls are added with their
own preflight/actual MD closure. Total required commands: 16. These are
requirements, not previously executed results. The ordinary filesystem seam
is explicit and does not prove a namespace or mount. No Android constructor,
actual Owner, pressure, Main deployment or host network operation occurs.

Only this build's actual successful artifact may be paired with producer09
ABI3/entryv3 in a new private CellSpec. Earlier Owner08 failure remains intact.
""")
    rows = []
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            data = p.read_bytes(); rows.append({"path": str(p.relative_to(OUT)), "bytes": len(data), "sha256": sha(data)})
    write("manifest.json", pretty({"schema": 1, "kind": KIND, "files": rows}))
    print(pretty({"root": str(OUT), "manifest_sha256": sha((OUT / "manifest.json").read_bytes()),
                  "request_sha256": sha((OUT / "request.json").read_bytes()), "key": request["idempotency_key"]}))


if __name__ == "__main__":
    main()
