#!/usr/bin/env python3
"""Create-only matching compile request; never dispatch or run Cargo here."""
import ast
import copy
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD = ROOT / "producer08-projection-controller-freeze-01"
PAIR = ROOT / "cgroup-handoff-pair-freeze-01"
OUT = ROOT / "producer09-cgroup-controller-freeze-01"
ACTUAL = ROOT.parent / "root-recovery-20261104-02/evidence/producer08-compile01/compile-result.json"
REVISION = "producer09-cgroup-handoff01"
REMOTE = "/home/alex/work/pocket4-supervisor-lmkd-cgroup-r11-build-09-01"
PRIOR_REMOTE = "/home/alex/work/pocket4-supervisor-lmkd-projection-r11-build-08-01"
PRIOR_SHA = "0e77456cf7145dd3f81cbed8ccf0e17afe855963c712fc99171733541c932f87"
PRIOR_INVENTORY = "9719c2ec3f3b638e68d04ccec6e86952b8b9ffbc2421c96df97f55bd96b26118"
PAIR_SHA = "64200d271f96217fbdb8518960250661dff4211dc62fa94a575c165eedd88de5"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pretty(data):
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def write(name, data):
    data = data.encode() if isinstance(data, str) else data
    data.decode("utf-8")
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as target:
        target.write(data)


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    OUT.mkdir()
    raw = ACTUAL.read_bytes()
    assert sha(raw) == PRIOR_SHA
    actual = json.loads(raw)
    assert actual["success"] and actual["compile_only"] and actual["revision"] == "producer08-projection01"
    assert actual["candidate"] == PRIOR_REMOTE + "/candidate"
    assert actual["all_source_inventory_before_sha256"] == actual["all_source_inventory_after_sha256"] == PRIOR_INVENTORY
    preimage = actual["inputs_before"]
    assert preimage == actual["inputs_after"] and len(preimage) == 32
    manifest = (PAIR / "manifest.json").read_bytes()
    assert sha(manifest) == PAIR_SHA
    for row in json.loads(manifest)["files"]:
        body = (PAIR / row["path"]).read_bytes()
        assert len(body) == row["bytes"] and sha(body) == row["sha256"]
    overlays = {}
    for leaf in ["domain.rs", "entry.rs", "init_peer.rs"]:
        name = "runtime/droidloom-supervisor/src/relay_lifecycle/" + leaf
        old = (PAIR / "preimage/host" / name).read_bytes()
        assert {"bytes": len(old), "sha256": sha(old)} == preimage[name]
        body = (PAIR / "candidate/host" / name).read_bytes()
        overlays[name] = {"bytes": len(body), "sha256": sha(body), "text": body.decode()}
    old_cfg = json.loads((OLD / "payload.json").read_bytes())
    cfg = {"schema": 1, "revision": REVISION, "preimage": preimage, "overlays": overlays,
           "original_diff_sha256": sha((PAIR / "source.diff").read_bytes()),
           "source_manifest_sha256": PAIR_SHA}
    overlay_constant = "EXACT_OVERLAY = {\n" + "".join(
        f"    {path!r}: ({row['bytes']}, {row['sha256']!r}),\n" for path, row in sorted(overlays.items())
    ) + "}\nNEW_SOURCE_FILES = set()\n"
    programs = {}
    for name in ("compile.py", "run.py"):
        old = (OLD / name).read_text()
        text = replace_once(old, 'CONTROL_REVISION = "producer08-projection01"', f'CONTROL_REVISION = "{REVISION}"')
        text = replace_once(text, 'BASE = Path("/home/alex/work/pocket4-supervisor-lmkd-audit-r11-build-07-02")', f'BASE = Path("{PRIOR_REMOTE}")')
        text = replace_once(text, 'OUT = Path("/home/alex/work/pocket4-supervisor-lmkd-projection-r11-build-08-01")', f'OUT = Path("{REMOTE}")')
        for before, after in [
            ("d5ead1b1e83447a4037a07262830fc2b8ad807e004c3dbca95ec0051b3e0fbcf", PRIOR_SHA),
            ("2cc80213dd99a6b7ea4211f4bead6b9f6e15cfe4b7066636929435422bde958f", PRIOR_INVENTORY),
            (old_cfg["original_diff_sha256"], cfg["original_diff_sha256"]),
            (old_cfg["source_manifest_sha256"], cfg["source_manifest_sha256"]),
            ("producer07 audit02", "producer08 projection01"),
            ("producer07-audit02-actual-compile-result.json", "producer08-projection01-actual-compile-result.json"),
        ]:
            assert before in text, (name, before)
            text = text.replace(before, after)
        start = text.index("EXACT_OVERLAY = {"); end = text.index("BINARIES = ", start)
        text = text[:start] + overlay_constant + text[end:]
        if name == "compile.py":
            text = replace_once(text, 'prior["revision"] == "producer07-audit02"', 'prior["revision"] == "producer08-projection01"')
        else:
            text = replace_once(text, 'expected_count = 23 if key == ("droidloom_pressure_relay", "lib") else 120',
                                'expected_count = 23 if key == ("droidloom_pressure_relay", "lib") else 122')
            text = replace_once(text, 'rust_tests_passed={"droidloom-pressure-relay": 23, "droidloom-supervisor": 120},',
                                'rust_tests_passed={"droidloom-pressure-relay": 23, "droidloom-supervisor": 122},')
            text = replace_once(text, 'b"droidloom-relay-entry-v2\\n"', 'b"droidloom-relay-entry-v3\\n"')
        ast.parse(text)
        programs[name] = text
        write(name, text)
        write(name + ".diff", "".join(difflib.unified_diff(old.splitlines(True), text.splitlines(True), fromfile="producer08/" + name, tofile="producer09/" + name)))
    payload = pretty(cfg)
    assert "'''" not in payload and len(payload.encode()) < 512 * 1024
    write("payload.json", payload)
    stdin = programs["compile.py"] + "\ncompile_recovery(json.loads(r'''" + payload + "'''))\n"
    request = json.loads((OLD / "compile-request.json").read_bytes())
    request["stdin"] = stdin
    request["idempotency_key"] = "p4-producer09-cgroup01-compile01-" + sha(stdin.encode())[:16]
    write("compile-request.json", pretty(request)); write("compile-stdin.py", stdin)
    template = json.loads((OLD / "ordinary-run-request-template.json").read_bytes())
    assert template["execution_ready"] is False
    template["request_template"]["stdin"] = programs["run.py"]
    template["request_template"]["idempotency_key"] = "p4-producer09-cgroup01-ordinary01-REQUIRES_ACTUAL_SHA16"
    template["requires"] = "Actual successful producer09-cgroup-handoff01 compile-result external SHA and root dispatch"
    template["scope"] = "23 relay/122 supervisor library tests, 2 public retirement tests, 7 IPC, worker-context and entry ABI3; no actual Owner/Android"
    write("ordinary-run-request-template.json", pretty(template))
    write("resource_guard.py", (OLD / "resource_guard.py").read_bytes())
    write("evidence/prior-actual-compile-result.json", raw)
    write("make_rust_controller09.py", Path(__file__).read_bytes())
    controls = []
    unchanged = []
    for name, text in programs.items():
        ns = {"__name__": "local_config_only"}; exec(compile(text, name, "exec"), ns)
        assert ns["validate_config"](cfg) == cfg
        assert ns["candidate_input_pins"](cfg) == {**preimage, **{p: {"bytes": row["bytes"], "sha256": row["sha256"]} for p, row in overlays.items()}}
        for label, mutation in [
            ("old_revision", lambda v: v.update(revision="producer08-projection01")),
            ("wrong_pair_manifest", lambda v: v.update(source_manifest_sha256="0" * 64)),
            ("missing_overlay", lambda v: v["overlays"].pop(next(iter(overlays)))),
            ("wrong_overlay_bytes", lambda v: v["overlays"][next(iter(overlays))].update(text="old")),
        ]:
            bad = copy.deepcopy(cfg); mutation(bad)
            try: ns["validate_config"](bad)
            except RuntimeError: controls.append({"controller": name, "case": label, "rejected": True})
            else: raise AssertionError("bad config accepted")
        old_funcs = {n.name: ast.dump(n) for n in ast.parse((OLD / name).read_text()).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        new_funcs = {n.name: ast.dump(n) for n in ast.parse(text).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        assert old_funcs.keys() == new_funcs.keys()
        for key in old_funcs:
            if key not in {"validate_config", "compile_recovery", "ordinary_recovery"}:
                assert old_funcs[key] == new_funcs[key], (name, key)
                unchanged.append(name + ":" + key)
    parsed = ast.parse(stdin); call = parsed.body[-1].value
    assert call.func.id == "compile_recovery" and call.args[0].args[0].value == payload
    assert ast.dump(ast.Module(body=parsed.body[:-1], type_ignores=[])) == ast.dump(ast.parse(programs["compile.py"]))
    write("validation.json", pretty({"schema": 1, "execution_status": "NOT_SUBMITTED", "source_pair_manifest_sha256": PAIR_SHA,
        "prior_actual_receipt_sha256": PRIOR_SHA, "base_input_count": 32, "overlays": sorted(overlays),
        "negative_config_controls": controls, "unchanged_function_or_class_AST": unchanged,
        "request_bytes": len((OUT / "compile-request.json").read_bytes()), "request_sha256": sha((OUT / "compile-request.json").read_bytes()),
        "stdin_bytes": len(stdin.encode()), "stdin_sha256": sha(stdin.encode()),
        "actual_rust_tests_run": False, "actual_owner_qualified": False}))
    write("README.md", """# Producer09 cgroup holding/leaf matching request

Create-only candidate and target derived from exact actual producer08 source.
All 32 original inputs and full source inventory are fixed before/after copying.
Only domain.rs, entry.rs, init_peer.rs receive the separately frozen ABI3 pair.
CPU1/1GiB/600s compile, held own-resource gates, four bin targets and explicit
two-library --lib test selection are unchanged. The separate ordinary template
requires this revision's actual successful compile receipt: expected 23 relay
and 122 supervisor (120 old + two leaf controls), two public retirement cases,
seven IPC, worker-context and entry ABI3. Counts are expectations, not results.
No Android namespace, mount, Main deployment, pressure or real Owner executes.
""")
    members = []
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            data = p.read_bytes(); members.append({"path": str(p.relative_to(OUT)), "bytes": len(data), "sha256": sha(data)})
    write("manifest.json", pretty({"schema": 1, "kind": "producer09_cgroup_controller_freeze01", "files": members}))
    print(pretty({"root": str(OUT), "manifest_sha256": sha((OUT / "manifest.json").read_bytes()),
                  "request_sha256": sha((OUT / "compile-request.json").read_bytes()), "key": request["idempotency_key"]}))


if __name__ == "__main__":
    main()
