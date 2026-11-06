"""Local deterministic seal from actual probe bytes and one preselected nonce.

Creates source and transport files only. Never executes the sealed stage or
worker and never calls a remote/Android tool.
"""
import hashlib
import json
from pathlib import Path
import re
import types

HERE = Path(__file__).resolve().parent
OUT = HERE / "candidate-r1"
ACTUAL = HERE.parent / "actual" / "ffi-bootstrap-probe-r1"


def pin(path, host_path=None):
    raw = path.read_bytes()
    return {"path": host_path or str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def main():
    assert not OUT.exists(), "Existing candidate is never overwritten or resumed"
    nonce = (HERE / "NEW_NONCE.txt").read_text().strip()
    assert re.fullmatch("[0-9a-f]{32}", nonce) and nonce != "77fe9d36efe51cf69813f3411099f049"
    raw = (ACTUAL / "stdout.raw.jsonl").read_bytes()
    terminal_raw = (ACTUAL / "terminal.raw.json").read_bytes()
    assert len(raw) == 14135 and hashlib.sha256(raw).hexdigest() == "c590487759f7a0e2e32dec8cdb16a7c42b7f932ed88154f760fdde477770ef94"
    assert len(terminal_raw) == 733 and hashlib.sha256(terminal_raw).hexdigest() == "86c28f1ff58512f7b8f3b42c59eb1a62e7bb20ce52edd0a043d54792e35d6762"
    template = (HERE / "prepare_beike_owned_lifetime.py.in").read_text()
    module = types.ModuleType("unsealed_candidate_validation")
    module.__file__ = str(HERE / "prepare_beike_owned_lifetime.py.in")
    exec(compile(template, module.__file__, "exec"), module.__dict__)
    module.validate_probe_proof(raw, json.loads(terminal_raw), "1a1b16bbf10-fc05-7891")
    worker = HERE.parent / "prepare_beike_bound_source.py"
    assert pin(worker)["sha256"] == "9db3af14e7f2903e3b94bc45ed43f202f2ceb243e95f904dcab3c363aa55cbde"
    request = json.loads((HERE.parent / "beike-final-request-r1.json").read_bytes())
    assert request["generation_nonce"] == "77fe9d36efe51cf69813f3411099f049"
    old_request = json.loads(json.dumps(request))
    request["generation_nonce"] = nonce
    request["output_root"] = "/home/alex/work/pocket4-beike-successor-qa-input-20261106-" + nonce
    assert {key: value for key, value in request.items() if key not in ("generation_nonce", "output_root")} == {
        key: value for key, value in old_request.items() if key not in ("generation_nonce", "output_root")}
    root = "/home/alex/work/pocket4-beike-owned-generation-20261106-" + nonce
    OUT.mkdir()
    (OUT / "actual-probe.stdout.raw.jsonl").write_bytes(raw)
    (OUT / "actual-probe.terminal.raw.json").write_bytes(terminal_raw)
    (OUT / "generation-request.json").write_bytes(module.canonical(request) + b"\n")
    config = {"schema": "pocket4-beike-library-owned-generation-config-v1",
              "probe_stdout": pin(OUT / "actual-probe.stdout.raw.jsonl", root + "/actual-probe.stdout.raw.jsonl"),
              "probe_terminal": pin(OUT / "actual-probe.terminal.raw.json", root + "/actual-probe.terminal.raw.json"),
              "probe_job_id": "1a1b16bbf10-fc05-7891", "new_nonce": nonce, "stage_root": root,
              "request": pin(OUT / "generation-request.json", root + "/generation-request.json")}
    marker = "CONFIG = None  # No unknown probe pin, terminal, version, or new nonce is invented."
    assert template.count(marker) == 1
    source = template.replace(marker, "CONFIG = " + repr(config))
    compile(source, root + "/prepare_beike_owned_lifetime.py", "exec")
    (OUT / "prepare_beike_owned_lifetime.py").write_text(source)
    names = ["actual-probe.stdout.raw.jsonl", "actual-probe.terminal.raw.json", "generation-request.json",
             "prepare_beike_owned_lifetime.py"]
    files = {name: {key: value for key, value in pin(OUT / name).items() if key != "path"} for name in names}
    stage = (HERE / "stage_owned_generation_once.py.in").read_text()
    assert stage.count("ROOT = None") == stage.count("FILES = None") == 1
    stage = stage.replace("ROOT = None", "ROOT = " + repr(root)).replace("FILES = None", "FILES = " + repr(files))
    compile(stage, "stage_owned_generation_once.py", "exec")
    (OUT / "stage_owned_generation_once.py").write_text(stage)
    payload = {"schema": "pocket4-beike-owned-generation-stage-input-v1",
               "files": [{"name": name, "text": (OUT / name).read_text()} for name in names]}
    stdin = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    assert len(stdin.encode()) <= 262144
    (OUT / "stage-input.json").write_text(stdin)
    process = {"host": "pocket4", "executable": "/usr/bin/sudo",
               "args": ["-n", "/usr/bin/python3", "-I", "-B", "-c", stage], "stdin": stdin,
               "cwd": "/home/alex/work", "timeout_seconds": 1200, "cpu_quota_percent": 100,
               "memory_max_bytes": 1073741824, "nice": 10,
               "idempotency_key": "pocket4-beike-owned-source-generation-r2-20261106-" + nonce}
    (OUT / "process-request.json").write_text(json.dumps(process, sort_keys=True, indent=2) + "\n")
    manifest = {"schema": "pocket4-beike-owned-source-candidate-v1", "sealed_but_not_executed": True,
                "new_nonce": nonce, "host_stage_root": root, "probe_job_id": config["probe_job_id"],
                "frozen_worker": module.FROZEN_WORKER, "original_failure_preserved": module.ORIGINAL_FAILURE,
                "runtime_scope_and_guard_changes": 0, "production_ready": False, "Main_actions": 0,
                "files": [pin(path, path.name) for path in sorted(OUT.iterdir()) if path.is_file()],
                "support_sources": [pin(HERE / name, "../" + name) for name in
                    ("prepare_beike_owned_lifetime.py.in", "stage_owned_generation_once.py.in",
                     "seal_candidate_r1.py", "test_template_controls.py", "local-controls-result.json", "README.md", "NEW_NONCE.txt")],
                "mandatory_followup_gate": "outer result + raw child + complete durable job success before build"}
    (OUT / "SOURCE_PINS.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"candidate": str(OUT), "nonce": nonce, "files": manifest["files"],
                      "manifest": pin(OUT / "SOURCE_PINS.json", "SOURCE_PINS.json")}, sort_keys=True))


if __name__ == "__main__":
    main()
