#!/usr/bin/env python3
"""Freeze exact matching requests only; never dispatch or run Cargo locally."""
import ast
import copy
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD = ROOT / "producer09-cgroup-controller-freeze-01"
PAIR = ROOT / "broker-holding-bootstrap-source-freeze-01"
OUT = ROOT / "producer10-broker-controller-freeze-01"
ACTUAL = ROOT.parent / "root-recovery-20261104-02/evidence/producer09-cgroup-compile01/result.json"
REVISION = "producer10-broker-holding01"
REMOTE = "/home/alex/work/pocket4-supervisor-lmkd-broker-r11-build-10-01"
PRIOR_REMOTE = "/home/alex/work/pocket4-supervisor-lmkd-cgroup-r11-build-09-01"
PRIOR_SHA = "415c12d44b3f2c568c8914126f61c4844b6a1238a565eabc488b8145c64eaae1"
PRIOR_INVENTORY = "6c1abf6ede0fb5ffd5379c6491a20800705cb59a3da867dabafd71970c0d2e47"
PAIR_SHA = "019b34bc655bf76235339b533917d523fd2e5db3355214e5a5466e6a61ee3068"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pretty(value):
    return json.dumps(value, sort_keys=True, indent=2) + "\n"


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not OUT.exists(), "create-only freeze already exists"
    files = {}

    def put(name, data):
        data = data.encode() if isinstance(data, str) else data
        data.decode("utf-8")
        assert name not in files
        files[name] = data

    raw = ACTUAL.read_bytes()
    assert sha(raw) == PRIOR_SHA
    actual = json.loads(raw)
    assert actual["success"] and actual["compile_only"]
    assert actual["revision"] == "producer09-cgroup-handoff01"
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
    for name in ["runtime/droidloom-pressure-relay/src/lifecycle_bootstrap.rs",
                 "runtime/droidloom-supervisor/src/relay_lifecycle/owner.rs"]:
        old = (PAIR / "preimage" / name).read_bytes()
        assert {"bytes": len(old), "sha256": sha(old)} == preimage[name]
        body = (PAIR / "candidate" / name).read_bytes()
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
        text = once(old, 'CONTROL_REVISION = "producer09-cgroup-handoff01"', f'CONTROL_REVISION = "{REVISION}"')
        text = once(text, 'BASE = Path("/home/alex/work/pocket4-supervisor-lmkd-projection-r11-build-08-01")', f'BASE = Path("{PRIOR_REMOTE}")')
        text = once(text, 'OUT = Path("/home/alex/work/pocket4-supervisor-lmkd-cgroup-r11-build-09-01")', f'OUT = Path("{REMOTE}")')
        for before, after in [
            ("0e77456cf7145dd3f81cbed8ccf0e17afe855963c712fc99171733541c932f87", PRIOR_SHA),
            ("9719c2ec3f3b638e68d04ccec6e86952b8b9ffbc2421c96df97f55bd96b26118", PRIOR_INVENTORY),
            (old_cfg["original_diff_sha256"], cfg["original_diff_sha256"]),
            (old_cfg["source_manifest_sha256"], cfg["source_manifest_sha256"]),
            ("producer08 projection01", "producer09 cgroup handoff01"),
            ("producer08-projection01-actual-compile-result.json", "producer09-cgroup-handoff01-actual-compile-result.json"),
        ]:
            assert before in text, (name, before)
            text = text.replace(before, after)
        start = text.index("EXACT_OVERLAY = {")
        end = text.index("BINARIES = ", start)
        text = text[:start] + overlay_constant + text[end:]
        if name == "compile.py":
            text = once(text, 'prior["revision"] == "producer08-projection01"', 'prior["revision"] == "producer09-cgroup-handoff01"')
        else:
            text = once(text, 'test_summary(out, 1, 22)', 'test_summary(out, 1, 25)')
            text = once(text, 'expected_count = 23 if key == ("droidloom_pressure_relay", "lib") else 122',
                        'expected_count = 26 if key == ("droidloom_pressure_relay", "lib") else 122')
            text = once(text, 'rust_tests_passed={"droidloom-pressure-relay": 23, "droidloom-supervisor": 122},',
                        'rust_tests_passed={"droidloom-pressure-relay": 26, "droidloom-supervisor": 122},')
        ast.parse(text)
        programs[name] = text
        put(name, text)
        put(name + ".diff", "".join(difflib.unified_diff(old.splitlines(True), text.splitlines(True),
                                                       fromfile="producer09/" + name, tofile="producer10/" + name)))
    payload = pretty(cfg)
    assert "'''" not in payload and len(payload.encode()) < 512 * 1024
    put("payload.json", payload)
    stdin = programs["compile.py"] + "\ncompile_recovery(json.loads(r'''" + payload + "'''))\n"
    request = json.loads((OLD / "compile-request.json").read_bytes())
    request["stdin"] = stdin
    request["idempotency_key"] = "p4-producer10-broker01-compile01-" + sha(stdin.encode())[:16]
    put("compile-request.json", pretty(request))
    put("compile-stdin.py", stdin)
    template = json.loads((OLD / "ordinary-run-request-template.json").read_bytes())
    assert template["execution_ready"] is False
    template["request_template"]["stdin"] = programs["run.py"]
    template["request_template"]["idempotency_key"] = "p4-producer10-broker01-ordinary01-REQUIRES_ACTUAL_SHA16"
    template["requires"] = "Actual successful producer10-broker-holding01 compile-result external SHA and root dispatch"
    template["scope"] = "26 relay/122 supervisor library tests, 2 public retirement tests, 7 IPC, worker-context and entry ABI3; no actual Owner/Android"
    put("ordinary-run-request-template.json", pretty(template))
    put("resource_guard.py", (OLD / "resource_guard.py").read_bytes())
    put("evidence/prior-actual-compile-result.json", raw)
    put("make_rust_controller10.py", Path(__file__).read_bytes())
    negative = []
    unchanged = []
    for name, text in programs.items():
        ns = {"__name__": "local_config_only"}
        exec(compile(text, name, "exec"), ns)
        assert ns["validate_config"](cfg) == cfg
        assert ns["candidate_input_pins"](cfg) == {
            **preimage, **{p: {"bytes": row["bytes"], "sha256": row["sha256"]} for p, row in overlays.items()}}
        for label, mutate in [
            ("old_revision", lambda v: v.update(revision="producer09-cgroup-handoff01")),
            ("wrong_pair_manifest", lambda v: v.update(source_manifest_sha256="0" * 64)),
            ("missing_overlay", lambda v: v["overlays"].pop(next(iter(overlays)))),
            ("wrong_overlay_bytes", lambda v: v["overlays"][next(iter(overlays))].update(text="old")),
        ]:
            bad = copy.deepcopy(cfg)
            mutate(bad)
            try:
                ns["validate_config"](bad)
            except RuntimeError:
                negative.append({"controller": name, "case": label, "rejected": True})
            else:
                raise AssertionError("bad config accepted")
        old_functions = {n.name: ast.dump(n) for n in ast.parse((OLD / name).read_text()).body
                         if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        new_functions = {n.name: ast.dump(n) for n in ast.parse(text).body
                         if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        assert old_functions.keys() == new_functions.keys()
        for key in old_functions:
            if key not in {"validate_config", "compile_recovery", "ordinary_recovery"}:
                assert old_functions[key] == new_functions[key], (name, key)
                unchanged.append(name + ":" + key)
    parsed = ast.parse(stdin)
    call = parsed.body[-1].value
    assert call.func.id == "compile_recovery" and call.args[0].args[0].value == payload
    assert ast.dump(ast.Module(body=parsed.body[:-1], type_ignores=[])) == ast.dump(ast.parse(programs["compile.py"]))
    put("validation.json", pretty({"schema": 1, "execution_status": "NOT_SUBMITTED",
        "source_pair_manifest_sha256": PAIR_SHA, "prior_actual_receipt_sha256": PRIOR_SHA,
        "base_input_count": 32, "overlays": sorted(overlays), "negative_config_controls": negative,
        "unchanged_function_or_class_AST": unchanged,
        "request_bytes": len(files["compile-request.json"]), "request_sha256": sha(files["compile-request.json"]),
        "stdin_bytes": len(stdin.encode()), "stdin_sha256": sha(stdin.encode()),
        "actual_rust_tests_run": False, "actual_owner_qualified": False}))
    put("README.md", """# Producer10 explicit broker holding bootstrap matching request

Create-only candidate and target derived from exact actual producer09 source.
All 32 original inputs and the complete source inventory are fixed before and
after copying. Only lifecycle_bootstrap.rs and the real Owner's one spawn call
receive the separately frozen P4BOOT2/layout3 source. The Android ABI3 DSO and
the steady-state authentication/retirement library remain unchanged.

CPU1/1GiB/600s compile, held own-cgroup resource gates, four binary targets and
explicit two-library --lib test selection are unchanged. The separate ordinary
template requires this revision's actual successful compile receipt: expected
26 relay (23 old + three new) and 122 supervisor tests, two public retirement
cases (one pass/25 filtered each), seven IPC, worker context and entry ABI3.
Counts are strict expectations, not results. No Android namespace, mount,
Main deployment, host network, pressure or actual Owner is executed here.
""")
    members = [{"path": name, "bytes": len(data), "sha256": sha(data)} for name, data in sorted(files.items())]
    put("manifest.json", pretty({"schema": 1, "kind": "producer10_broker_controller_freeze01", "files": members}))
    OUT.mkdir()
    for name, data in files.items():
        path = OUT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as target:
            target.write(data)
    print(pretty({"root": str(OUT), "manifest_sha256": sha(files["manifest.json"]),
                  "request_bytes": len(files["compile-request.json"]),
                  "request_sha256": sha(files["compile-request.json"]),
                  "stdin_bytes": len(stdin.encode()), "stdin_sha256": sha(stdin.encode()),
                  "key": request["idempotency_key"]}))


if __name__ == "__main__":
    main()
