#!/usr/bin/env python3
"""Explicit Linux host compatibility gate; never native-guest evidence."""
import argparse
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prepare_inputs as build

require, sha, save = build.require, build.sha, build.save
AGENT = "33333333-3333-4333-8333-333333333333"
CHECKS = ["original_source_memory_kg_commit", "live_wal_before_sigkill", "sigkill_exit_observed",
          "legacy_reopen_exact_anchor_and_memory", "source_retry_idempotent_after_sigkill",
          "two_processes_ready_before_cas", "one_cas_commit_one_conflict",
          "losing_source_transaction_rolled_back", "winning_memory_and_projection_persisted",
          "graceful_close_reopen_exact_anchor"]
FALSE_FLAGS = ["production_authority", "production_writer_lock", "authenticated_recovery",
               "power_loss_durability", "f1_completed", "model_turn", "device_effect"]
LIMIT = 512 * 1024


def json_value(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("non-finite JSON constant")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def positive(value):
    return type(value) is int and 0 < value < 2**64


def digest(value):
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value) is not None


def validate_record(raw):
    require(0 < len(raw) <= LIMIT and raw.endswith(b"\n") and len(raw.splitlines()) == 1,
            "one bounded, complete original fixture record required")
    value = json_value(raw)
    require(isinstance(value, dict) and value.get("event") == "acceptance_pass"
            and value.get("schema") == "hepta.original-cognitive-store-process-crash.v1"
            and value.get("evidence_class") == "legacy_original_store_wal_process_crash_reopen"
            and value.get("agent_id") == AGENT and value.get("checks") == CHECKS, "incomplete original fixture acceptance")
    require(all(value.get(flag) is False for flag in FALSE_FLAGS), "fixture authority/effect scope changed")
    require(positive(value.get("wal_bytes_before_kill")) and type(value.get("killed_signal")) is int
            and value["killed_signal"] == 9, "real live-WAL SIGKILL observation missing")
    anchors = [value.get(key) for key in ("seed_anchor", "final_anchor")]
    for anchor in anchors:
        require(isinstance(anchor, dict) and set(anchor) == {"profile", "owner_agent_id", "schema_digest", "state_digest"}
                and anchor["profile"] == "hepta:cognitive:exact-current-cut:v1"
                and anchor["owner_agent_id"] == AGENT and digest(anchor["schema_digest"])
                and digest(anchor["state_digest"]), "original logical cut missing")
    require(anchors[0]["schema_digest"] == anchors[1]["schema_digest"]
            and anchors[0]["state_digest"] != anchors[1]["state_digest"], "logical cut did not advance")
    seed = value.get("seed_receipt")
    results = value.get("cas_results")
    require(isinstance(results, list) and len(results) == 2 and all(isinstance(item, dict) for item in results)
            and [item.get("variant") for item in results] == ["a", "b"]
            and all(item.get("event") == "cas_result" for item in results), "two independent CAS results missing")
    require(sorted(item.get("outcome", "") for item in results) == ["committed", "conflict"], "CAS was not one commit and one conflict")
    winner = next(item for item in results if item["outcome"] == "committed")
    loser = next(item for item in results if item["outcome"] == "conflict")
    require("receipt" not in loser, "loser unexpectedly returned a committed receipt")
    receipts = [(seed, "seed", 1), (winner.get("receipt"), winner["variant"], 2)]
    memory_ids = []
    for receipt, variant, revision in receipts:
        require(isinstance(receipt, dict) and set(receipt) == {"source", "memory", "projection"}, "original atomic receipt missing")
        memory, source, projection = (receipt[key] for key in ("memory", "source", "projection"))
        require(isinstance(source, dict) and source.get("revision") == 1 and type(source.get("revision")) is int
                and isinstance(source.get("source_id"), str)
                and re.fullmatch("source:v1:[0-9a-f]{64}", source["source_id"]), "source revision missing")
        require(isinstance(memory, dict) and memory.get("content") == f"Inert store compatibility fixture revision {variant}."
                and memory.get("scope") == {"scope": "agent_private"} and memory.get("verification") == "verified"
                and memory.get("lifecycle") == {"state": "active"} and memory.get("valid_from_unix_seconds") == 100
                and memory.get("valid_to_unix_seconds") is None and memory.get("supersedes_revision") == (None if revision == 1 else 1)
                and memory.get("citations") == [source]
                and memory.get("content_sha256") == hashlib.sha256(memory["content"].encode()).hexdigest(), "memory/source identity mismatch")
        identifier = memory.get("id", {})
        require(isinstance(identifier, dict) and type(identifier.get("revision")) is int and identifier["revision"] == revision
                and isinstance(identifier.get("memory_id"), str), "expected exact memory revision")
        memory_ids.append(identifier["memory_id"])
        require(isinstance(projection, dict) and positive(projection.get("generation"))
                and all(type(projection.get(key)) is int and projection[key] == count
                        for key, count in (("entity_count", 2), ("relation_count", 1), ("node_count", 2), ("edge_count", 1)))
                and all(digest(projection.get(key)) for key in ("fact_set_sha256", "input_heads_sha256", "output_sha256",
                                                               "generation_sha256", "publication_sha256")), "atomic original KG receipt missing")
    require(memory_ids[0] == memory_ids[1] and re.fullmatch("memory:v2:[0-9a-f]{64}", memory_ids[0]), "CAS changed stable memory identity")
    require(seed["projection"]["generation"] < winner["receipt"]["projection"]["generation"], "projection generation did not advance")
    return value


def frozen_build(path, expected):
    require(digest(expected) and path.is_file() and not path.is_symlink()
            and 0 < path.stat().st_size <= LIMIT and sha(path) == expected, "pinned build receipt required")
    value = json_value(path.read_bytes())
    require(isinstance(value, dict) and value.get("schema") == "hepta.original-cognitive-store-build.v1"
            and value.get("built") is True and value.get("source_clean") is True
            and value.get("runtime_executed") is False, "successful original build receipt required")
    review = json_value((HERE / "source-review.json").read_bytes())
    require(value.get("source") == review and value.get("fixture_source_sha256") == sha(HERE / "store_probe.rs"),
            "fixture or original source revision differs")
    record = value.get("binary", {})
    require(record.get("path") == build.NAME, "unexpected frozen binary path")
    binary = path.parent / build.NAME
    require(binary.is_file() and not binary.is_symlink() and type(record.get("bytes")) is int
            and 0 < record["bytes"] <= 1024**3 and binary.stat().st_size == record["bytes"]
            and sha(binary) == record.get("sha256"), "frozen original fixture binary changed")
    require(isinstance(value.get("commands"), list) and len(value["commands"]) == 4
            and value.get("resolved_cargo_lock_sha256") == sha(path.parent / "runner/Cargo.lock"), "resolved original build evidence missing")
    return value, binary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--build-receipt", type=Path)
    parser.add_argument("--expected-build-receipt-sha256")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args(argv)
    report = {"schema": "hepta.original-cognitive-store-host-result.v1", "passed": False, "executed": False,
              "native_guest_verified": False, **dict.fromkeys(FALSE_FLAGS, False),
              "started_at_utc": datetime.now(timezone.utc).isoformat()}
    if not args.execute:
        report["status"] = "disabled; explicit --execute and frozen real fixture build required"
        print(json.dumps(report, sort_keys=True))
        return 0
    for name in ("build_receipt", "expected_build_receipt_sha256", "output"):
        if getattr(args, name) is None:
            parser.error("--execute requires --" + name.replace("_", "-"))
    out = args.output.absolute()
    try:
        require(sys.platform == "linux" and 30 <= args.timeout <= 600, "Linux and bounded host deadline required")
        receipt, binary = frozen_build(args.build_receipt, args.expected_build_receipt_sha256)
        require(not out.exists() and not out.is_symlink(), "output must be new")
        require(not out.resolve().is_relative_to(args.build_receipt.parent.resolve()), "output must be outside build inputs")
        out.mkdir(mode=0o700)
        report["output_created"] = True
        save(out / "frozen-build.json", receipt)
        command = [str(binary.absolute()), "probe", str(out / "store")]
        environment = {"PATH": "/usr/bin:/bin", "HOME": str(out), "TMPDIR": str(out), "LANG": "C", "LC_ALL": "C"}
        report.update(executed=True, command=command, environment=environment,
                      build_receipt_sha256=args.expected_build_receipt_sha256)
        build.HELPER.bounded_command(command, out, environment, out / "fixture.log", args.timeout)
        raw = (out / "fixture.log").read_bytes()
        observed = validate_record(raw)
        frozen_build(args.build_receipt, args.expected_build_receipt_sha256)
        report.update(passed=True, original_store_process_crash_reopen_verified=True,
                      fixture_output_sha256=sha(out / "fixture.log"), observation=observed)
    except (OSError, ValueError, KeyError, TypeError, build.HELPER.GateError, subprocess.SubprocessError) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    if report.get("output_created"):
        save(out / "result.json", report)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
