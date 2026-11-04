#!/usr/bin/env python3
"""Local parser/binding controls only. Never calls prepare or any device tool."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True


def load(name):
    path = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location("signal_canary_control_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actual-evidence-dir", type=Path, required=True)
    parser.add_argument("--signal-fix-pins", type=Path, required=True)
    args = parser.parse_args()
    assess, prep = load("assess"), load("prepare")
    rows = []

    def control(name, operation, reject=False):
        error = None
        try:
            operation()
        except (ValueError, RuntimeError, KeyError) as failure:
            error = str(failure)
        success = (error is not None) == reject
        rows.append({"name": name, "expected_rejection": reject, "passed": success, "error": error})
        if not success:
            raise RuntimeError("local control failed: " + name)

    samples = {}
    for name, accepted in (("signal-svc-current-r16.json", True),
                           ("signal-smc-default-current-r16.json", True),
                           ("signal-smc-handler-current-r16-failure.json", False),
                           ("signal-r3-mask-edit-current-r16-failure.json", False)):
        record = json.loads((args.actual_evidence_dir / name).read_text())
        output = record["instrumentation_output"]
        document, _ = assess.instrumentation_document(output)
        # The durable files are not present in this local source cache. These
        # are parser controls constructed from measured stdout, not a claim
        # that disk readback has been independently performed here.
        claim = ("case=" + document["case"] + "\nnonce=" + document["nonce"] +
                 "\npid=" + str(document["java_pid"]) + "\n").encode()
        arguments = [output, json.dumps(document), claim, document["package"],
                     document["case"], document["nonce"], 0]
        samples[document["case"]] = arguments
        control("measured-" + document["case"], lambda a=arguments: assess.assess_case(*a), not accepted)
    svc = samples["svc"]
    wrong = copy.deepcopy(svc); wrong[5] = "different-owned-nonce"
    control("reject-another-nonce", lambda: assess.assess_case(*wrong), True)
    wrong = copy.deepcopy(svc); wrong[6] = 124
    control("reject-timeout-despite-pass-payload", lambda: assess.assess_case(*wrong), True)
    wrong = copy.deepcopy(svc); wrong[0] += "\nINSTRUMENTATION_CODE: -1\n"
    control("reject-multiple-completions", lambda: assess.assess_case(*wrong), True)
    control("reject-duplicate-json-key", lambda: assess.read_json('{"phase":"FAIL","phase":"PASS"}'), True)
    wrong = copy.deepcopy(samples["smc-default"])
    doc = json.loads(wrong[1]); doc["native"]["child"]["reaped"] = False
    wrong[0] = "INSTRUMENTATION_RESULT: evidence_json=" + json.dumps(doc) + "\nINSTRUMENTATION_CODE: -1\n"
    wrong[1] = json.dumps(doc)
    control("reject-unreaped-child-with-pass-bits", lambda: assess.assess_case(*wrong), True)
    control("reject-duplicate-package-identity", lambda: assess.package_identities(
        "package:owned.example versionCode:1 uid:10001\n" * 2), True)

    pins = json.loads(args.signal_fix_pins.read_text())
    if prep.sha(args.signal_fix_pins) != prep.SIGNAL_PINS_SHA:
        raise RuntimeError("local candidate pins differ")
    with tempfile.TemporaryDirectory(prefix="owned-signal-binding-") as temporary:
        out = Path(temporary) / "android-out"
        product = out / "target/product/droidloom_x86_64"
        engine = product / "system/lib64/libberberis_arm64.so"
        engine.parent.mkdir(parents=True)
        # Declared synthetic 20-byte ELF header fixture. Never executed or
        # described as a built translator; only exercises receipt admission.
        header = bytearray(20); header[:6] = b"\x7fELF\x02\x01"; header[18:20] = (62).to_bytes(2, "little")
        engine.write_bytes(header)
        raw_files = {row["path"]: row["sha256"] for row in pins["changes"]}
        inputs = {"status": "inputs_captured", "scope": "native-engine-only",
                  "tests_requested": True, "logical_targets": ["libberberis_arm64", "berberis_arm64_host_tests"],
                  "installation_performed": False, "full_runtime_rebuilt": False,
                  "output_directory": str(out), "source_snapshot": {"files": dict(raw_files)},
                  "effective_teto_files": dict(raw_files)}
        receipt = dict(inputs, status="selected_artifacts_built", engine={
            "path": str(engine), "sha256": prep.sha(engine), "elf": {"machine": "EM_X86_64"},
            "metadata": {"soname": "libberberis_arm64.so"}})
        ip, rp = product / "droidloom-native-engine-inputs.json", product / "droidloom-native-engine-source.json"

        def binding(changed_receipt=None, changed_inputs=None):
            ip.write_text(json.dumps(changed_inputs or inputs))
            rp.write_text(json.dumps(changed_receipt or receipt))
            config = {"signal_fix_pins": {"path": str(args.signal_fix_pins.resolve()), "sha256": prep.SIGNAL_PINS_SHA},
                      "candidate_build_inputs": {"path": str(ip), "sha256": prep.sha(ip)},
                      "candidate_build_receipt": {"path": str(rp), "sha256": prep.sha(rp)},
                      "engine": {"path": str(engine), "sha256": prep.sha(engine)}}
            return prep.candidate_binding(config)

        control("synthetic-binding-structure-only", binding)
        bad = copy.deepcopy(receipt); bad["status"] = "cancelled"
        control("reject-cancelled-build", lambda: binding(bad), True)
        bad = copy.deepcopy(receipt); bad["engine"]["sha256"] = "0" * 64
        control("reject-stale-engine-hash", lambda: binding(bad), True)
        bad = copy.deepcopy(receipt); bad["effective_teto_files"][pins["changes"][0]["path"]] = "0" * 64
        control("reject-projected-source-difference", lambda: binding(bad), True)
        bad_inputs = copy.deepcopy(inputs)
        bad_inputs["effective_teto_files"][pins["changes"][0]["path"]] = "0" * 64
        bad = copy.deepcopy(receipt); bad["effective_teto_files"] = bad_inputs["effective_teto_files"]
        control("reject-consistent-receipts-with-wrong-candidate", lambda: binding(bad, bad_inputs), True)
        bad = copy.deepcopy(inputs); bad["status"] = "selected_artifacts_built"
        control("reject-final-receipt-as-inputs", lambda: binding(changed_inputs=bad), True)
        bad = copy.deepcopy(receipt); bad["tests_requested"] = False
        control("reject-no-host-suite-build", lambda: binding(bad), True)

    print(json.dumps({"schema": 1, "state": "LOCAL_CONTROLS_PASS", "rows": rows,
                      "device_operations": 0, "services_started": 0,
                      "native_execution": False, "synthetic_fixture_scope": "receipt admission only",
                      "durable_probe_readback_qualified_here": False,
                      "actual_isolated_Android_qualification": "NOT_RUN"}, indent=2))


if __name__ == "__main__":
    main()
