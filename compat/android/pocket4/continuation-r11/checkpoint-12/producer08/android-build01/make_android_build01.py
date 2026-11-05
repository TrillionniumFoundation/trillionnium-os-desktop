#!/usr/bin/env python3
"""Freeze the exact seven-source ABI2 Android build; never execute it here."""
import ast
import base64
import copy
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAIR = ROOT / "socket-projection-pair-freeze-01"
OLD = ROOT / "init-project-diagnostic-build-freeze-03"
OUT = ROOT / "init-socket-projection-build-freeze-01"
ACTUAL = ROOT.parent / "root-recovery-20261104-02/evidence/init-project-diagnostic-build03/build-result.json"
KIND = "p4-init-socket-projection-build01"
REMOTE = "/opt/p4-init-socket-projection-20261105-build-01"


def sha(body):
    return hashlib.sha256(body).hexdigest()


def pretty(value):
    return json.dumps(value, sort_keys=True, indent=2) + "\n"


def write(name, data):
    if isinstance(data, str):
        data = data.encode()
    data.decode("utf-8")
    target = OUT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as file:
        file.write(data)


def main():
    OUT.mkdir(exist_ok=False)
    pair_manifest = (PAIR / "manifest.json").read_bytes()
    assert sha(pair_manifest) == "c2cc6b709c503e7dc5d273e9e400665356e7c0654adf3b828838870eb8a06891"
    for row in json.loads(pair_manifest)["files"]:
        body = (PAIR / row["path"]).read_bytes()
        assert len(body) == row["bytes"] and sha(body) == row["sha256"]
    actual_raw = ACTUAL.read_bytes()
    assert sha(actual_raw) == "15c122a42f1c0d81ff4d473925184a8f7aedb6babc84d9fa4036ae6378b44d02"
    actual = json.loads(actual_raw)
    assert actual["success"] is True and actual["all_inputs_unchanged"] is True
    assert len(actual["commands"]) == 13 and all(c["returncode"] == 0 and c["child_reaped"] and not c["timed_out"] for c in actual["commands"])
    old_cfg = json.loads((OLD / "config.json").read_bytes())
    cfg = copy.deepcopy(old_cfg)
    cfg["kind"], cfg["root"], cfg["source_manifest_sha256"] = KIND, REMOTE, sha(pair_manifest)
    payload = {}
    for leaf in old_cfg["payload"]:
        preimage = (PAIR / "preimage/android" / leaf).read_bytes()
        assert sha(preimage) == actual["source_before"][leaf]["sha256"] and len(preimage) == actual["source_before"][leaf]["bytes"]
        body = (PAIR / "source/android" / leaf).read_bytes()
        payload[leaf] = {"bytes": len(body), "sha256": sha(body), "base64": base64.b64encode(body).decode()}
    assert len(payload) == 7
    cfg["payload"] = payload
    old_template = (OLD / "build-template.py").read_text()
    template = old_template.replace("p4-init-project-diagnostic-build03", KIND).replace(
        "p4-init-project-diagnostic-20261105-build-03", Path(REMOTE).name)
    # All compiler/link commands, dependency targets and resource/cleanup logic
    # are unchanged; only two fixed profile literals change in the template.
    assert template.replace(KIND, "p4-init-project-diagnostic-build03").replace(
        Path(REMOTE).name, "p4-init-project-diagnostic-20261105-build-03") == old_template
    marker = "CFG = None  # Filled once by the local frozen-request generator."
    assert template.count(marker) == 1
    body = template.replace(marker, "CFG = " + repr(cfg))
    parsed = ast.parse(body)
    assign = next(n for n in parsed.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CFG" for t in n.targets))
    assert ast.literal_eval(assign.value) == cfg
    assign.value = ast.Constant(value=None)
    assert ast.dump(parsed) == ast.dump(ast.parse(template))
    compile(body, "paired-build", "exec")
    request = json.loads((OLD / "request.json").read_bytes())
    request["stdin"] = body
    request["idempotency_key"] = "p4-init-socket-projection01-build01-" + sha(body.encode())[:16]
    assert {k: v for k, v in cfg.items() if k not in ["root", "kind", "source_manifest_sha256", "payload"]} == {
        k: v for k, v in old_cfg.items() if k not in ["root", "kind", "source_manifest_sha256", "payload"]}
    assert request["args"] == ["-n", "/usr/bin/python3", "-I", "-B", "-"]
    assert request["memory_max_bytes"] == 536870912 and request["cpu_quota_percent"] == 100 and request["timeout_seconds"] == 180
    write("request.json", pretty(request))
    write("build.py", body)
    write("build-template.py", template)
    write("build-template.diff", "".join(difflib.unified_diff(old_template.splitlines(True), template.splitlines(True),
                                                            fromfile="diagnostic03/build-template.py", tofile="projection01/build-template.py")))
    write("config.json", pretty(cfg))
    write("resource_guard.py", (OLD / "resource_guard.py").read_bytes())
    write("make_android_build01.py", Path(__file__).read_bytes())
    validation = {"kind": "paired_projection_android_build_binding_01", "execution_status": "NOT_SUBMITTED",
                  "source_pair_manifest_sha256": sha(pair_manifest), "prior_actual_report_sha256": sha(actual_raw),
                  "prior_actual_source_preimages_verified": 7, "source_payload_count": len(payload),
                  "original_input_count": len(cfg["original_inputs"]), "expected_Android_MD_count": 140,
                  "original_android_argv_unchanged": True, "resource_guard_unchanged": True,
                  "template_only_fixed_kind_root_changed": True, "AST_controller_equals_template_except_CFG": True,
                  "request": {"bytes": len((OUT / "request.json").read_bytes()), "sha256": sha((OUT / "request.json").read_bytes()),
                              "idempotency_key": request["idempotency_key"]},
                  "stdin": {"bytes": len(body.encode()), "sha256": sha(body.encode())},
                  "expected_controls": {"protocol": 20, "protocol_close_errno": 20, "diagnostic": 7},
                  "actual_constructor_qualified": False, "actual_owner_active_qualified": False}
    write("validation.json", pretty(validation))
    write("README.md", """# ABI2 Android projection matching build

This create-only request copies the exact seven frozen paired C inputs into a
new root and compiles against the original pinned 147-input Android tool/link
closure. The original four Android argv, the exact preflight/actual MD target
handling and equality checks, root-owned sealed files and CPU1/512MiB/180s
resource/cleanup gates are unchanged. Source preimages were independently
matched to all seven actual successful diagnostic-build03 inputs.

Required actual outcome: Android DSO link and fixed ELF contract, 20 owned
transport cases (including old numeric ABI1 refusal), the same 20 close-errno
variants, and seven owned directory/move-syscall seams. Local listener EPERM
was preserved in the source checkpoint and is not a device transport pass.
The ELF-export symbol version remains the original C query function signature;
the function's reported protocol ABI, wire magic and constructor opt-in version
are now 2. The paired Rust entry ABI is separately v2.

This request runs no Android constructor, namespace mount, pressure or Main
deployment. Only the newly built DSO's exact actual artifact hash may enter a
fresh private normal Owner CellSpec, together with the matching producer08
binary hashes. The whole lifecycle remains unqualified until that actual run.
""")
    rows = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file():
            data = path.read_bytes()
            rows.append({"path": str(path.relative_to(OUT)), "bytes": len(data), "sha256": sha(data)})
    write("manifest.json", pretty({"kind": KIND, "files": rows}))
    print(pretty({**validation, "root": str(OUT), "manifest_sha256": sha((OUT / "manifest.json").read_bytes())}))


if __name__ == "__main__":
    main()
