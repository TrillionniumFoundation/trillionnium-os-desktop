#!/usr/bin/env python3
"""Derive a fresh build-only request from the actual audit02 controller."""
import ast
import copy
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD = ROOT / "producer07-controller-freeze-02"
PAIR = ROOT / "socket-projection-pair-freeze-01"
OUT = ROOT / "producer08-projection-controller-freeze-01"
ACTUAL = ROOT.parent / "root-recovery-20261104-02/evidence/producer07-audit02/compile-result.json"
REVISION = "producer08-projection01"
REMOTE = "/home/alex/work/pocket4-supervisor-lmkd-projection-r11-build-08-01"
PRIOR_REMOTE = "/home/alex/work/pocket4-supervisor-lmkd-audit-r11-build-07-02"
PRIOR_SHA = "d5ead1b1e83447a4037a07262830fc2b8ad807e004c3dbca95ec0051b3e0fbcf"
PRIOR_INVENTORY = "2cc80213dd99a6b7ea4211f4bead6b9f6e15cfe4b7066636929435422bde958f"


def sha(body):
    return hashlib.sha256(body).hexdigest()


def pretty(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def write(name, body):
    if isinstance(body, str):
        body = body.encode()
    body.decode("utf-8")
    target = OUT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as file:
        file.write(body)


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    OUT.mkdir(exist_ok=False)
    before = ACTUAL.read_bytes()
    assert sha(before) == PRIOR_SHA
    actual = json.loads(before)
    assert actual["success"] is True and actual["compile_only"] is True and actual["revision"] == "producer07-audit02"
    assert actual["candidate"] == PRIOR_REMOTE + "/candidate"
    assert actual["all_source_inventory_before_sha256"] == actual["all_source_inventory_after_sha256"] == PRIOR_INVENTORY
    preimage = actual["inputs_before"]
    assert preimage == actual["inputs_after"] and len(preimage) == 32
    manifest = json.loads((PAIR / "manifest.json").read_bytes())
    for row in manifest["files"]:
        body = (PAIR / row["path"]).read_bytes()
        assert len(body) == row["bytes"] and sha(body) == row["sha256"]
    overlays = {}
    for leaf in ["init_peer.rs", "entry.rs"]:
        name = "runtime/droidloom-supervisor/src/relay_lifecycle/" + leaf
        old = (PAIR / "preimage/host" / name).read_bytes()
        assert {"bytes": len(old), "sha256": sha(old)} == preimage[name]
        body = (PAIR / "source/host" / name).read_bytes()
        overlays[name] = {"bytes": len(body), "sha256": sha(body), "text": body.decode()}
    diff_sha = sha((PAIR / "source.diff").read_bytes())
    manifest_sha = sha((PAIR / "source-manifest.json").read_bytes())
    cfg = {"schema": 1, "revision": REVISION, "preimage": preimage, "overlays": overlays,
           "original_diff_sha256": diff_sha, "source_manifest_sha256": manifest_sha}
    overlay_constant = "EXACT_OVERLAY = {\n" + "".join(
        f"    {path!r}: ({row['bytes']}, {row['sha256']!r}),\n" for path, row in sorted(overlays.items())
    ) + "}\nNEW_SOURCE_FILES = set()\n"
    programs = {}
    for name in ["compile.py", "run.py"]:
        old = (OLD / name).read_text()
        text = once(old, 'CONTROL_REVISION = "producer07-audit02"', f'CONTROL_REVISION = "{REVISION}"')
        text = once(text, 'BASE = Path("/home/alex/work/pocket4-supervisor-lmkd-deadline-r11-build-06-recovery04")',
                    f'BASE = Path("{PRIOR_REMOTE}")')
        text = once(text, 'OUT = Path("/home/alex/work/pocket4-supervisor-lmkd-audit-r11-build-07-02")', f'OUT = Path("{REMOTE}")')
        text = text.replace("2eb658308593cf760b7f99bbc9e3d7762295ef18c4628b050221838ffa274d4f", PRIOR_SHA)
        text = text.replace("731fcdae3856011a418e244b19b0568160f9316e94b31ba3aa6e75e423cab5eb", PRIOR_INVENTORY)
        text = text.replace("e4735859cde851b068d6f9697819e39c04bb20e93dfc4fc312a3e21681a9b5f3", diff_sha)
        text = text.replace("433b1e8e3cd97ba3b3fd7018ca7f899de3eae14ad84d011a5a54d05ba3f16b87", manifest_sha)
        start = text.index("EXACT_OVERLAY = {")
        end = text.index("BINARIES = ", start)
        text = text[:start] + overlay_constant + text[end:]
        text = once(text, 'need(len(cfg["preimage"]) == 31 and', 'need(len(cfg["preimage"]) == 32 and')
        text = text.replace("producer06 recovery04", "producer07 audit02")
        text = text.replace("producer06-recovery04-actual-compile-result.json", "producer07-audit02-actual-compile-result.json")
        text = text.replace("31 original source inputs differ", "32 original source inputs differ")
        if name == "compile.py":
            text = once(text, 'prior["revision"] == "producer06-deadline-recovery04"', 'prior["revision"] == "producer07-audit02"')
        else:
            text = once(text, 'expected_count = 23 if key == ("droidloom_pressure_relay", "lib") else 119',
                        'expected_count = 23 if key == ("droidloom_pressure_relay", "lib") else 120')
            text = once(text, 'rust_tests_passed={"droidloom-pressure-relay": 23, "droidloom-supervisor": 119},',
                        'rust_tests_passed={"droidloom-pressure-relay": 23, "droidloom-supervisor": 120},')
            text = once(text, 'b"droidloom-relay-entry-v1\\n"', 'b"droidloom-relay-entry-v2\\n"')
        ast.parse(text)
        programs[name] = text
        write(name, text)
        write(name + ".diff", "".join(difflib.unified_diff(old.splitlines(True), text.splitlines(True),
                                                        fromfile="producer07-audit02/" + name, tofile=REVISION + "/" + name)))
    payload = pretty(cfg)
    assert "'''" not in payload and len(payload.encode()) < 512 * 1024
    write("payload.json", payload)
    stdin = programs["compile.py"] + "\ncompile_recovery(json.loads(r'''" + payload + "'''))\n"
    request = json.loads((OLD / "compile-request.json").read_bytes())
    request["stdin"] = stdin
    request["idempotency_key"] = "p4-producer08-projection01-compile01-" + sha(stdin.encode())[:16]
    write("compile-request.json", pretty(request))
    write("compile-stdin.py", stdin)
    template = json.loads((OLD / "ordinary-run-request-template.json").read_bytes())
    assert template["execution_ready"] is False
    template["request_template"]["stdin"] = programs["run.py"]
    template["request_template"]["idempotency_key"] = "p4-producer08-projection01-ordinary01-REQUIRES_ACTUAL_SHA16"
    template["requires"] = "Actual successful producer08-projection01 compile-result.json external SHA-256 and root dispatch. No previous receipt substitution."
    template["scope"] = "23 relay + 120 supervisor library tests, two public retirement targets, 7 owned IPC, worker-context and entry ABI v2. No namespace, Android, actual mount or real Owner run."
    write("ordinary-run-request-template.json", pretty(template))
    write("resource_guard.py", (OLD / "resource_guard.py").read_bytes())
    write("evidence/prior-actual-compile-result.json", before)
    write("make_rust_controller01.py", Path(__file__).read_bytes())
    # Validate both exact public controller admission functions without calling
    # either compile/run entry or touching any remote path.
    tests = []
    for name, text in programs.items():
        namespace = {"__name__": "pair_local_validation"}
        exec(compile(text, name, "exec"), namespace)
        assert namespace["validate_config"](cfg) == cfg
        assert namespace["candidate_input_pins"](cfg) == {**preimage, **{
            p: {"bytes": r["bytes"], "sha256": r["sha256"]} for p, r in overlays.items()}}
        for label, mutate in [
            ("old_revision", lambda value: value.update(revision="producer07-audit02")),
            ("wrong_pair_manifest", lambda value: value.update(source_manifest_sha256="0" * 64)),
            ("missing_overlay", lambda value: value["overlays"].pop(next(iter(overlays)))),
            ("old_overlay_bytes", lambda value: value["overlays"][next(iter(overlays))].update(text="old")),
        ]:
            bad = copy.deepcopy(cfg); mutate(bad)
            try:
                namespace["validate_config"](bad)
            except RuntimeError:
                tests.append({"controller": name, "case": label, "rejected": True})
            else:
                raise AssertionError("invalid payload accepted: " + label)
    parsed = ast.parse(stdin)
    last = parsed.body[-1]
    assert isinstance(last, ast.Expr) and isinstance(last.value, ast.Call) and last.value.func.id == "compile_recovery"
    embedded = last.value.args[0].args[0].value
    assert embedded == payload and json.loads(embedded) == cfg
    assert ast.dump(ast.Module(body=parsed.body[:-1], type_ignores=[])) == ast.dump(ast.parse(programs["compile.py"]))
    assert request["stdin"] == stdin
    # The guard remains exactly inlined, and all nonconstant controls outside
    # validate_config/compile_recovery/ordinary_recovery remain byte-semantic.
    unchanged = []
    allowed_functions = {"validate_config", "compile_recovery", "ordinary_recovery"}
    for name, text in programs.items():
        old_ast = ast.parse((OLD / name).read_text())
        new_ast = ast.parse(text)
        old_functions = {n.name: ast.dump(n) for n in old_ast.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        new_functions = {n.name: ast.dump(n) for n in new_ast.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        assert set(old_functions) == set(new_functions)
        for key, value in old_functions.items():
            if key not in allowed_functions:
                assert value == new_functions[key], (name, key)
                unchanged.append(name + ":" + key)
    validation = {"kind": "producer08_controller_binding_01", "execution_status": "NOT_SUBMITTED",
                  "source_pair_manifest_sha256": sha((PAIR / "manifest.json").read_bytes()),
                  "prior_actual_receipt_sha256": PRIOR_SHA, "source_origin_inventory_sha256": PRIOR_INVENTORY,
                  "base_input_count": 32, "overlays": sorted(overlays), "negative_config_controls": tests,
                  "unchanged_function_or_class_AST": unchanged,
                  "compile_request": {"bytes": len((OUT / "compile-request.json").read_bytes()),
                                      "sha256": sha((OUT / "compile-request.json").read_bytes()), "idempotency_key": request["idempotency_key"]},
                  "compile_stdin": {"bytes": len(stdin.encode()), "sha256": sha(stdin.encode())},
                  "resources": {k: request[k] for k in ["cpu_quota_percent", "memory_max_bytes", "nice", "timeout_seconds"]},
                  "actual_rust_tests_run": False, "actual_owner_qualified": False}
    write("validation.json", pretty(validation))
    write("README.md", """# Producer08 paired projection matching build

Create-only source/candidate root; compile request only. The exact actual
producer07 audit02 source receipt and all 32 inputs are required. Two existing
Rust files are overlaid from the separately frozen ABI2 pair; no new source
module is introduced. The prior full source inventory is checked before copy
and again afterwards. The candidate inventory and held artifact hashes bind
the complete new build. Original CPU1/1GiB/600s compile and CPU1/512MiB/180s
ordinary resources, exact held cgroup health gates, and explicit --lib test
selection remain unchanged.

The separate ordinary template cannot execute until the actual successful new
compile receipt is pinned. Expected counts are 23 relay and 120 supervisor
tests (119 previous + one new non-O_PATH rejection case); two original public
retirement targets each pass 1/filter22; 7 IPC, worker-origin and entry ABI v2
also remain required. These are expectations, not actual results. There is no
Android namespace execution, Main deployment or actual Owner qualification in
this request. The actual constructor still requires the matching new Android
DSO and a fresh private CellSpec run.
""")
    members = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file():
            body = path.read_bytes()
            members.append({"path": str(path.relative_to(OUT)), "bytes": len(body), "sha256": sha(body)})
    write("manifest.json", pretty({"kind": "producer08_projection_controller_freeze_01", "files": members}))
    print(pretty({**validation, "root": str(OUT), "manifest_sha256": sha((OUT / "manifest.json").read_bytes())}))


if __name__ == "__main__":
    main()
