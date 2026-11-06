"""Local parsing/admission controls; no Main read, fake root stat, or generation."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types

HERE = Path(__file__).resolve().parent
source = HERE / "prepare_beike_owned_lifetime.py.in"
module = types.ModuleType("unsealed_owned_template")
module.__file__ = str(source)
exec(compile(source.read_bytes(), str(source), "exec"), module.__dict__)
actual = HERE.parent / "actual" / "ffi-bootstrap-probe-r1"
raw = (actual / "stdout.raw.jsonl").read_bytes()
terminal_raw = (actual / "terminal.raw.json").read_bytes()
terminal = json.loads(terminal_raw)
observed = module.validate_probe_proof(raw, terminal, "1a1b16bbf10-fc05-7891")
assert observed["library"]["sha256"] == "1a0dc86f787f73e025a6e521056360afcbe70f2a82cd808132fefc2b4ee95daa"
negative = []
for label, key, value in (("durability_missing", "output_durable", False),
                          ("child_timeout", "timed_out", True),
                          ("job_identity_wrong", "job_id", "different")):
    bad = copy.deepcopy(terminal)
    bad[key] = value
    try:
        module.validate_probe_proof(raw, bad, "1a1b16bbf10-fc05-7891")
    except RuntimeError as exc:
        negative.append({"name": label, "rejected": str(exc)})
    else:
        raise AssertionError(label)
parts = [json.loads(line) for line in raw.splitlines()]
parts[1]["child_lifecycle"]["pidfd_exit_observed"] = False
bad_raw = b"\n".join(module.canonical(value) for value in parts) + b"\n"
bad_terminal = copy.deepcopy(terminal)
bad_terminal["log_bytes"]["stdout"] = {"seen": len(bad_raw), "stored": len(bad_raw)}
try:
    module.validate_probe_proof(bad_raw, bad_terminal, "1a1b16bbf10-fc05-7891")
except RuntimeError as exc:
    negative.append({"name": "inner_probe_success_without_held_pidfd_death", "rejected": str(exc)})
else:
    raise AssertionError("pidfd gate")
control = subprocess.run([sys.executable, "-B", "-I", str(source), "--execute-new-source-preparation"],
                         capture_output=True, timeout=5)
rejected = json.loads(control.stdout)
assert control.returncode == 1 and rejected["errors"][0]["code"] == "UNSEALED_NO_EXECUTION"
assert "child_lifecycle" not in rejected and "final_receipt" not in rejected
(HERE / "unsealed-control.stdout.raw.json").write_bytes(control.stdout)
(HERE / "unsealed-control.stderr.raw.txt").write_bytes(control.stderr)
result = {"schema": "pocket4-owned-generation-template-local-controls-v1",
          "actual_probe_raw_parsed": {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
          "actual_probe_terminal": {"bytes": len(terminal_raw), "sha256": hashlib.sha256(terminal_raw).hexdigest()},
          "actual_probe_proof_parser_pass": True, "negative_controls": negative,
          "unsealed_process_exit": control.returncode, "unsealed_no_child_or_Main": True,
          "Main_actions": 0, "root_stat_not_mocked": True,
          "sealed_worker_executed": False, "source_worker_executed": False}
(HERE / "local-controls-result.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
print(json.dumps(result, sort_keys=True))
