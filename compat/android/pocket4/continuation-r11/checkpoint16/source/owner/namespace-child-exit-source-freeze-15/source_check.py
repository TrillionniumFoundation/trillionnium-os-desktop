"""Offline source binding/scope check. Does not compile Rust or run the tests."""
from pathlib import Path
from collections import Counter
import base64
import difflib
import hashlib
import json
import re
import shutil

ROOT = Path(__file__).resolve().parent

def pin(path):
    data = path.read_bytes()
    data.decode("utf-8", "strict")
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "git_blob_sha1": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()}

def functions(text):
    # Strip strings/comments while keeping byte positions for function-body
    # comparisons. This is a scope check, not a Rust parser or type checker.
    out = list(text); i = 0
    while i < len(text):
        start = i
        if text.startswith("//", i):
            i = text.find("\n", i)
            if i < 0: i = len(text)
        elif text.startswith("/*", i):
            depth = 1; i += 2
            while depth and i < len(text):
                if text.startswith("/*", i): depth += 1; i += 2
                elif text.startswith("*/", i): depth -= 1; i += 2
                else: i += 1
            assert depth == 0
        else:
            raw = re.match(r'r(#+)?"', text[i:])
            char = re.match(r"'(?:\\.|[^'\\])'", text[i:])
            if raw:
                end = '"' + (raw.group(1) or '')
                j = text.find(end, i + raw.end()); assert j >= 0
                i = j + len(end)
            elif text[i] == '"':
                i += 1
                while i < len(text):
                    if text[i] == "\\": i += 2
                    elif text[i] == '"': i += 1; break
                    else: i += 1
            elif char: i += char.end()
            else: i += 1; continue
        for j in range(start, i):
            if out[j] != "\n": out[j] = " "
    mask = "".join(out); result = []
    for m in re.finditer(r"(?m)^[ \t]*(?:pub(?:\([^)]*\))?[ \t]+)?(?:unsafe[ \t]+)?fn[ \t]+([A-Za-z_0-9]+)\b", mask):
        left = mask.find("{", m.end()); assert left >= 0
        depth = 1; right = left + 1
        while depth:
            assert right < len(mask)
            if mask[right] == "{": depth += 1
            elif mask[right] == "}": depth -= 1
            right += 1
        result.append((m.group(1), text[m.start():right]))
    return result

def get(text, name):
    values = [body for n, body in functions(text) if n == name]
    assert len(values) == 1, (name, len(values))
    return values[0]

def main():
    compile_path = ROOT / "evidence/actual-producer14-compile.json"
    assert pin(compile_path)["sha256"] == "a916592cc708dc76411b482a371214410bca4662f6ff72dccd5083d88872b6a6"
    actual = json.loads(compile_path.read_bytes())
    assert actual["success"] is True
    bindings = json.loads((ROOT / "actual-input-bindings.json").read_bytes())
    assert bindings["input_count"] == len(bindings["inputs"]) == 32
    for row in bindings["inputs"]:
        p = pin(Path(row["local_path"]))
        assert {k: p[k] for k in ("bytes", "sha256")} == actual["inputs_after"][row["path"]]
    changes = []; fragments = []; child = []; diagnostic = []
    texts = {}
    for pre in sorted((ROOT / "preimage").rglob("*.rs")):
        relative = pre.relative_to(ROOT / "preimage").as_posix()
        old = pre.read_text(); new = (ROOT / "candidate" / relative).read_text()
        assert {k: pin(pre)[k] for k in ("bytes", "sha256")} == actual["inputs_after"][relative]
        delta = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile="a/"+relative, tofile="b/"+relative))
        assert delta
        fragments.append(delta)
        (diagnostic if "droidloom-pressure-relay" in relative else child).append(delta)
        old_fn = functions(old); new_fn = functions(new)
        exact_new = Counter(body for _, body in new_fn)
        changed = []; unchanged = 0
        for name, body in old_fn:
            if exact_new[body]: exact_new[body] -= 1; unchanged += 1
            else: changed.append(name)
        changes.append({"path": relative, "preimage": pin(pre), "candidate": pin(ROOT/"candidate"/relative),
                        "old_functions_exact_in_new": unchanged, "changed_existing_functions": changed,
                        "tests_before": old.count("#[test]"), "tests_after": new.count("#[test]")})
        texts[pre.name] = (old, new)
    assert len(changes) == 4
    for name, value in (("source.diff", fragments), ("child-exit-only.diff", child), ("post-error-observation-only.diff", diagnostic)):
        assert (ROOT/name).read_text() == "".join(value)
    lib_old, lib_new = texts["lib.rs"]
    old_capture = lib_old.split("impl LifecycleSnapshot {", 1)[1].split("    fn matches", 1)[0].strip()
    new_inner = lib_new.split("    fn capture_inner(pin: &ProcessPin)", 1)[1].split("    fn matches", 1)[0].strip()
    assert old_capture.split("fn capture(pin: &ProcessPin)", 1)[1].strip() == new_inner
    for name in ("live", "namespace_pins", "open_at", "authenticate", "revalidate"):
        assert get(lib_old, name) == get(lib_new, name), name
    owner_old, owner_new = texts["owner.rs"]
    for name in ("run", "run_inner", "run_generation", "retire_generation", "stop_exact_processes", "prove_retired", "finish_after_runtime", "poll", "enrolled"):
        assert get(owner_old, name) == get(owner_new, name), name
    retire = get(owner_new, "retire_before_network")
    assert retire.index("child.try_wait()") < retire.index("self.observe_child_exit") < retire.index("self.cancel.request()") < retire.index("status?.is_none()")
    dev_old, dev_new = texts["development.rs"]
    stop = get(dev_new, "stop")
    assert stop.index("self.child.try_wait()") < stop.index("relay.observe_child_exit") < stop.index("relay.request_stop()") < stop.index("if let Err(source) = before_stop")
    assert get(dev_new, "try_wait").index("relay.observe_child_exit") < get(dev_new, "try_wait").index("self.cleanup()")
    assert "if self.termination_reason.is_none()" in get(dev_new, "cleanup_inner")
    assert get(dev_new, "cleanup_inner").index("self.termination_reason =") < get(dev_new, "cleanup_inner").index("retired.map_err")
    audit_old, audit_new = texts["audit.rs"]
    assert "#[serde(default, skip_serializing_if = \"Option::is_none\")]\n    namespace_owner_exit: Option<NamespaceOwnerExit>" in audit_new
    assert "if !status.success() && !explicit_stop_requested && !worker_retirement_started" in audit_new
    assert "const MAX_RECORDS: usize = 16;" in audit_old and "const MAX_RECORDS: usize = 16;" in audit_new
    added_supervisor = sum(row["tests_after"]-row["tests_before"] for row in changes if "supervisor" in row["path"])
    added_relay = sum(row["tests_after"]-row["tests_before"] for row in changes if "pressure-relay" in row["path"])
    assert (added_supervisor, added_relay) == (6, 2)
    return {"schema": 1, "scope": "offline source/provenance/order check only", "passed": True,
            "actual_preimage_inputs_verified": 32, "changes": changes,
            "original_lifecycle_capture_body_exact": True,
            "declared_new_rust_tests": {"supervisor": added_supervisor, "relay": added_relay},
            "expected_matching_suite_counts_not_executed": {"supervisor": 128, "relay": 39, "ordinary_ipc": 7},
            "rustc_available": shutil.which("rustc") is not None, "cargo_available": shutil.which("cargo") is not None,
            "rust_compiled": False, "rust_tests_executed": False, "android_or_namespace_executed": False,
            "full_owner_runtime_qualified": False, "original_owner14_failure_preserved": True,
            "main_current_budget_change_resolved": False, "new_owner_runtime_admitted": False}

if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, sort_keys=True, indent=2))
