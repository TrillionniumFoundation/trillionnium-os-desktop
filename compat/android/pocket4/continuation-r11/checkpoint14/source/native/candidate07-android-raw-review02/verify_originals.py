#!/usr/bin/env python3
"""Reassess existing, pinned case originals offline; never execute an Android case."""
import argparse
import hashlib
import json
from pathlib import Path
import stat

HERE = Path(__file__).resolve().parent
RUNTIME_SHA = "4e1899db8d0f82a3d80df231f10b09fed644028440a1d77e820e50413c3378d1"
PREVIOUS_REVIEW_SHA = "f149d0c08d6d5fe68981096e84223f2213cff67f5059125cf4500d2eca7f59cc"
ASSESSOR_SHA = "125547744b86686f80278bb7730fdb4352b4f3378376f03ea10f7553f879ec97"
READER_SOURCE_SHA = "688fa8c589fd4c79bbb03ebbc00df7a0384f97c329bee5f81713ab1e1bee22ea"
ENGINE_SHA = "3aa9b479a9b66f56ae827477cf9f957fdeb6dcb21f1f8f981e34a1089f80048a"
REMOTE_ROOT = "/home/alex/work/pocket4-signal-canary-combined07-9b4f271386ac6d2d"
CASES = (
    ("r2-svc", "svc", "org.droidloom.signalprobe", "5a7517935f9d49e183b8b4647d5bbd94", 5588),
    ("r2-smc-handler", "smc-handler", "org.droidloom.signalprobe", "c2ca535cfa9545c29f3f7e935ffba5fb", 5647),
    ("r2-smc-default", "smc-default", "org.droidloom.signalprobe", "a350a2487c2c471b805bfe7287cb9688", 5709),
    ("r3-smc-mask-edit", "smc-mask-edit", "org.droidloom.signalprobe.r3", "ebdddcaf8b4e4d46abff14c3575e3f68", 5827),
)
SUFFIXES = (("-durable.json", 262144), ("-durable.claim", 16384),
            ("-instrument.stdout", 262144), ("-instrument-terminal.json", 16384))


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unique(pairs):
    value = {}
    for key, item in pairs:
        need(key not in value, "duplicate JSON key: " + key)
        value[key] = item
    return value


def document(raw):
    return json.loads(raw, object_pairs_hook=unique)


def pinned(path, expected, length=None):
    raw = Path(path).read_bytes()
    need(sha(raw) == expected, "local artifact SHA differs: " + str(path))
    if length is not None:
        need(len(raw) == length, "local artifact length differs: " + str(path))
    return raw


def check_identity(row, relative, maximum):
    need(row["path"] == REMOTE_ROOT + "/" + relative and row["relative"] == relative,
         "remote case path differs")
    need(row["state"] == "ORIGINAL_READ" and row["original_file_modified"] is False,
         "original case reader failed or modified source")
    identities = [row[key] for key in ("named_before", "held_before", "held_after", "named_after")]
    need(all(value == identities[0] for value in identities), "held/named original identities differ")
    identity = identities[0]
    need(stat.S_ISREG(identity["mode"]) and identity["mode"] & 0o022 == 0 and
         identity["uid"] == identity["gid"] == 0 and identity["nlink"] == 1 and
         0 < identity["bytes"] <= maximum and identity["bytes"] == row["bytes"],
         "original type/ownership/mode/bound differs")
    need(row["maximum"] == maximum, "fixed original observation bound differs")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reader", required=True)
    parser.add_argument("--reader-sha256", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--previous-review", required=True)
    args = parser.parse_args()
    need(len(args.reader_sha256) == 64 and all(c in "0123456789abcdef" for c in args.reader_sha256),
         "the actual root-provided reader digest is required")
    assessor_raw = pinned(HERE / "references/assess.py", ASSESSOR_SHA, 6240)
    assessor = {"__name__": "frozen_pure_assessment", "__file__": str(HERE / "references/assess.py")}
    exec(compile(assessor_raw, assessor["__file__"], "exec"), assessor, assessor)
    reader_source = pinned(HERE.parent / "candidate07-android-cases-read02/read_cases.py", READER_SOURCE_SHA, 5767)
    del reader_source
    runtime = document(pinned(args.runtime, RUNTIME_SHA, 30990))
    previous = document(pinned(args.previous_review, PREVIOUS_REVIEW_SHA, 4423))
    need(previous["state"] == "OFFLINE_RECEIPT_CROSSCHECK_PASSED" and
         previous["runtime_sha256"] == RUNTIME_SHA, "previous actual source/cleanup review differs")
    need(runtime["state"] == "OWNED_SYNC_SIGNAL_CANARY_PASS" and len(runtime["cases"]) == 4,
         "actual runtime is not the exact four-case result")
    reader_raw = pinned(args.reader, args.reader_sha256)
    reader = document(reader_raw)
    need(reader["state"] == "ORIGINAL_ANDROID_CASE_FILES_READ" and reader["root"] == REMOTE_ROOT,
         "originals reader did not complete the fixed scope")
    need(reader["writes"] == reader["children_created"] == reader["Main_actions"] == 0 and
         reader["new_test_execution"] is False and reader["runtime_admitted"] is False,
         "read-only observation boundary differs")
    authority = reader["runtime_result_authority"]
    check_identity(authority, "runtime-result.json", 4 * 1024 * 1024)
    need(authority["bytes"] == 30990 and authority["sha256"] == RUNTIME_SHA,
         "runtime authority differs from the prior actual original")
    expected_files = {label + suffix: maximum for label, *_ in CASES for suffix, maximum in SUFFIXES}
    need(len(reader["files"]) == 16 and reader["maximum_original_bytes"] == sum(expected_files.values()),
         "original observation count/bound differs")
    originals, pins = {}, {}
    for row in reader["files"]:
        relative = row["relative"]
        need(relative in expected_files and relative not in originals, "duplicate or unexpected original")
        check_identity(row, relative, expected_files[relative])
        raw = row["text"].encode("utf-8")
        need(len(raw) == row["bytes"] and sha(raw) == row["sha256"], "original body length/SHA differs")
        originals[relative] = raw
        pins[relative] = {"bytes": len(raw), "sha256": sha(raw), "held_identity": row["held_before"]}
    need(set(originals) == set(expected_files), "one or more original case files are missing")
    evaluations = []
    for (label, case, package, nonce, pid), recorded in zip(CASES, runtime["cases"]):
        terminal = document(originals[label + "-instrument-terminal.json"])
        need(set(terminal) == {"returncode", "timed_out", "mutation_attempted", "automatic_retry"} and
             type(terminal["returncode"]) is int and terminal["returncode"] == 0 and
             terminal["timed_out"] is False and terminal["mutation_attempted"] is True and
             terminal["automatic_retry"] is False, "instrumentation terminal was not exact completed once")
        assessed = assessor["assess_case"](originals[label + "-instrument.stdout"],
                    originals[label + "-durable.json"], originals[label + "-durable.claim"],
                    package, case, nonce, terminal["returncode"])
        need(assessed == {k: v for k, v in recorded.items() if k != "actual_mapped_engine"},
             "recomputed frozen assessment differs from runtime result")
        need(assessed["guest_pid"] == pid, "fixed actual PID differs")
        mapping = recorded["actual_mapped_engine"]
        need(mapping["binding"]["engine_sha256"] == ENGINE_SHA and
             mapping["binding"]["mapped_device"] == 66306 and
             mapping["binding"]["mapped_inode"] == 44182354 and
             mapping["binding"]["hash_bound_by_held_file_before_and_after_case"] is True and
             mapping["process"]["namespace_pids"][-1] == pid,
             "observed exact native engine/PID binding differs")
        final = assessor["read_json"](originals[label + "-durable.json"])
        evaluations.append({**assessed, "instrument_terminal": terminal,
                            "instruction": final["native"]["instruction"],
                            "signal": final["native"]["signal"],
                            "mask_edit": final["native"].get("mask_edit"),
                            "child": final["native"].get("child"),
                            "mapped_engine_sha256": ENGINE_SHA})
    result = {"schema": 1, "state": "FOUR_ORIGINAL_CASES_REASSESSED_OFFLINE_PASS",
              "reader_report": {"path": args.reader, "bytes": len(reader_raw), "sha256": args.reader_sha256},
              "runtime_sha256": RUNTIME_SHA, "previous_review_sha256": PREVIOUS_REVIEW_SHA,
              "frozen_assessor_sha256": ASSESSOR_SHA, "reader_source_sha256": READER_SOURCE_SHA,
              "originals": pins, "cases": evaluations,
              "instrumentation_and_durable_documents_equal": True,
              "exact_claims_and_instrumentation_terminals_verified": True,
              "native_assertions_reassessed_by_unchanged_frozen_assessor": True,
              "new_Android_execution": False, "Hepta_calls": 0, "Main_actions": 0,
              "metadata_generation_enabled": False, "whole_app_qualification": False,
              "production_ready": False,
              "limits": ["No new tests or actual process/namespace observations occurred in this offline reassessment.",
                         "Source, host-suite, package cleanup and four service hierarchy review remain bound to the prior receipt.",
                         "Controller actor memory.max events were nonzero; Main memory.events deltas are absent from this runtime result.",
                         "The smc-default case proves owned child SIGILL termination/reaping, not precise default-fault siginfo.",
                         "Native register/check assertions retain the frozen probe and assessor meaning; this adds no new independent emulator oracle."]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
