#!/usr/bin/env python3
"""Review retained CI bytes only; never execute a workload, compiler, or owner."""
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import gzip
import hashlib
import json
import re
import shutil
import zipfile

BASE = Path(__file__).resolve().parent
STAGE = BASE / "archive-stage"
HEAD = "46dcb2d691827f7aa3ad7903dae09d39fd338126"
TREE = "8d5de807c41090e3d987764daec9c235ebd022a1"
UPSTREAM = "2be5fc052ae7b2e9fb08c68a3ae7e5a218ad37d5"

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def read(path):
    return json.loads((BASE / path).read_text())

def emit(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

def copy(path):
    target = STAGE / path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BASE / path, target)

assert not STAGE.exists(), "fresh archive required"
report = read("owner/work/report.json")
records = report["runtime_records"]
run, jobs, checks = read("api/run.json"), read("api/jobs.json"), read("api/check-runs.json")
assert run["id"] == 39115155092 and run["head_sha"] == HEAD
assert run["conclusion"] == "success" and run["run_attempt"] == 1
assert {j["id"] for j in jobs["jobs"]} == {117639353718, 117655596136}
assert all(j["conclusion"] == "success" and j["head_sha"] == HEAD for j in jobs["jobs"])
assert len(checks["check_runs"]) == 7
assert all(c["head_sha"] == HEAD and c["conclusion"] == "success" for c in checks["check_runs"])
assert report["status"] == "passed" and report["runtime_executed"] is True
assert report["contract"]["desktop_commit"] == HEAD
assert report["upstream"]["commit"] == UPSTREAM
assert (BASE / "owner/runtime-exit-code.txt").read_text().strip() == "0"
raw_records = [json.loads(line) for line in (BASE / "owner/work/runtime.log").read_text().splitlines() if line.strip()]
assert raw_records == records
assert read("owner/logs/history-gate.log") == report
owner_log = (BASE / "logs/owner-job.log").read_text(encoding="utf-8-sig")
untimed = re.sub(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z ?", "", owner_log, flags=re.M)
assert (BASE / "owner/logs/history-gate.log").read_text().strip() in untimed
counts = Counter(record["event"] for record in records)
assert counts == {"owner_running": 4, "submission_observed": 4, "history_query_observed": 13,
                  "objective_history_check": 15, "objective_response_discarded": 1, "acceptance_pass": 1}
accepted = next(r for r in records if r["event"] == "acceptance_pass")
assert accepted["source_binding"] == report["compiled_source_binding"] == read("owner/work/probe/src/objective_history_source_binding.json")
assert accepted["objective_request_attempts"] == 5 and accepted["published_objective_requests"] == 4
assert accepted["recovery_resubmissions"] == 0 and accepted["isolated_test_issuer"] is True
for key in ["canonical_intelligence", "device_effect", "hepta_submit_cli_lost_reply_executed", "historical_run_resumed", "model_turn", "operations_dispatch", "operations_k_or_d_created", "production_issuer"]:
    assert accepted[key] is False

source = read("source-restoration.json")
assert source["desktop_commit"] == HEAD and source["tree"] == TREE
for row in source["files"]:
    raw = (BASE / "source" / row["path"]).read_bytes()
    assert len(raw) == row["bytes"] and digest(raw) == row["sha256"]
    assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == row["git_blob_sha1"]
owner_before, owner_after = read("owner/identity/desktop-before.json"), read("owner/identity/final-checkouts.json")
transport = read("transport/checks.json")
assert owner_before["commit"] == HEAD and owner_before["tree"] == TREE
assert owner_before["source_sha256"] == owner_after["source_sha256"] and owner_after["unchanged"] is True
assert transport["before"] == transport["after"] == read("transport/identity/before.json")
transport_final = read("transport/identity/final.json")
assert transport_final["expected_desktop_commit"] == HEAD
assert transport_final["checkout"]["identity"]["exit_code"] == 0
assert transport_final["checkout"]["identity"]["stdout"].splitlines() == [HEAD, TREE]
assert transport_final["checkout"]["status"]["exit_code"] == 0 and transport_final["checkout"]["status"]["stdout"] == ""
assert transport["before"]["commit"] == HEAD and transport["status"] == "passed"
assert all(step["exit_code"] == 0 for step in transport["steps"])
for manifest in [owner_before["source_sha256"], transport["before"]["source_sha256"]]:
    for path, expected in manifest.items():
        assert digest((BASE / "source" / path).read_bytes()) == expected
contract = read("owner/locks/OBJECTIVE_HISTORY_CONTRACT.json")
assert digest((BASE / "owner/locks/OBJECTIVE_HISTORY_CONTRACT.json").read_bytes()) == report["contract"]["sha256"]
assert digest((BASE / "owner/locks/hepta-Cargo.lock").read_bytes()) == contract["cargo_lock_sha256"] == report["upstream"]["cargo_lock_sha256"]
assert digest((BASE / "owner/work/probe/Cargo.lock").read_bytes()) == report["resolved_lock_sha256"]
assert (BASE / "owner/locks/desktop-Cargo.lock").read_bytes() == (BASE / "source/services/hepta-os/Cargo.lock").read_bytes()
contract_files = {f["path"]: f["sha256"] for f in contract["files"]}
assert digest((BASE / "owner/locks/hepta-Cargo.toml").read_bytes()) == contract_files["codex-rs/Cargo.toml"]
inputs = report["source_sha256"]
for name, expected in inputs.items():
    assert digest((BASE / "source/tests/integration/hepta" / name).read_bytes()) == expected
    target_name = "main.rs" if name == "objective_history_probe.rs" else name
    if target_name.endswith((".rs", ".json")):
        assert digest((BASE / "owner/work/probe/src" / target_name).read_bytes()) == expected
assert (BASE / "owner/work/runtime-evidence/admission-profile.json").read_bytes() == (BASE / "source/tests/integration/hepta/original_objective_profile.json").read_bytes()
builds = read("owner/identity/builds.json")
assert builds["upstream_before"] == builds["upstream_after"] == report["upstream"] == read("owner/identity/hepta-before.json")
assert builds["status"] == "passed" and all(step["exit_code"] == 0 for step in builds["steps"])

queries, submissions = [], []
for event in records:
    if event["event"] == "history_query_observed":
        label = event["label"]
        assert read("owner/work/runtime-evidence/" + label + "-query-output.json") == event["result"]
        assert event["journal_unchanged"] is True
        assert event["exit_code"] == {"historical_publication": 0, "unknown": 12}[event["result"]["status"]]
        identity = event["result"]["identity"]
        request = read("owner/work/runtime-evidence/" + label + "-query-input.json")
        assert request["message_id"] == identity["message_id"] and request["sequence"] == identity["message_sequence"]
        queries.append({"label": label, "status": event["result"]["status"], "exit_code": event["exit_code"], "identity": identity,
                        "journal_sha256": event["journal_sha256"], "journal_unchanged_ci_assertion": True})
    elif event["event"] == "submission_observed":
        assert read("owner/work/runtime-evidence/" + event["label"] + "-stdout.json") == event["result"]
        submissions.append({"label": event["label"], "status": event["result"]["status"], "exit_code": event["exit_code"]})

test_log = (BASE / "transport/logs/test.log").read_text()
totals = re.findall(r"test result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) ignored", test_log)
assert len(totals) == 9 and all(s == "ok" and f == i == "0" for s, p, f, i in totals)
assert sum(int(p) for s, p, f, i in totals) == 51
assert re.search(r"Ran 22 tests in [\d.]+s\n\nOK\n", (BASE / "transport/logs/history-contracts.log").read_text())
artifact_api = {a["name"]: a for a in read("api/artifacts.json")["artifacts"]}
zip_rows = []
for path in sorted(BASE.glob("*.zip")):
    raw = path.read_bytes()
    api = artifact_api[path.name.removesuffix(".zip")]
    assert len(raw) == api["size_in_bytes"] and "sha256:" + digest(raw) == api["digest"]
    prefix = "transport" if "transport" in path.name else "owner"
    with zipfile.ZipFile(path) as archive:
        files = [entry for entry in archive.infolist() if not entry.is_dir()]
        for entry in files:
            assert archive.read(entry) == (BASE / prefix / entry.filename).read_bytes()
    zip_rows.append({"file": path.name, "artifact_id": api["id"], "bytes": len(raw), "sha256": digest(raw), "members_verified_against_extracted_bytes": len(files)})

STAGE.mkdir()
selected = ["download-receipt.json", "transport-members.json", "owner-members.json", "source-restoration.json",
            "owner/work/report.json", "owner/runtime-exit-code.txt", "transport/checks.json", "seal_ci_review.py"]
selected += [str(p.relative_to(BASE)) for p in (BASE / "api").glob("*.json")]
selected += [str(p.relative_to(BASE)) for p in (BASE / "owner/identity").glob("*.json")]
selected += [str(p.relative_to(BASE)) for p in (BASE / "owner/locks").iterdir() if p.is_file()]
selected += [str(p.relative_to(BASE)) for p in (BASE / "source").rglob("*") if p.is_file()]
selected += [row["file"] for row in zip_rows]
for path in selected:
    copy(path)
storage = []
for path in [BASE / "logs/owner-job.log", BASE / "logs/transport-job.log", BASE / "owner/work/runtime.log"]:
    raw = path.read_bytes()
    relative = str(path.relative_to(BASE))
    stored = relative + ".gz"
    target = STAGE / stored
    target.parent.mkdir(parents=True, exist_ok=True)
    packed = gzip.compress(raw, compresslevel=9, mtime=0)
    target.write_bytes(packed)
    assert gzip.decompress(packed) == raw
    storage.append({"raw_path": relative, "raw_bytes": len(raw), "raw_sha256": digest(raw), "stored_path": stored,
                    "stored_bytes": len(packed), "stored_sha256": digest(packed), "encoding": "gzip", "mtime": 0, "roundtrip_exact": True})

review = {"schema": "r9.pr193.history-ci-independent-review.v1", "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    "status": "passed_with_explicit_scope", "reviewer": "A10", "new_workloads_compilations_or_owner_processes_executed": False,
    "execution_source": {"desktop_commit": HEAD, "desktop_tree": TREE, "owner_commit": UPSTREAM,
                         "owner_tree": report["upstream"]["tree"], "workflow_run": run["id"], "run_attempt": 1},
    "api": {"seven_checks_completed_success": True, "full_logs_and_artifacts_reviewed_jobs": [117639353718, 117655596136],
            "other_five_checks": "API status only; their workloads were not independently reviewed in this task"},
    "transport": {"rust_passed": 51, "rust_failed": 0, "rust_ignored": 0, "python_contract_passed": 22,
                  "strict_clippy_default_off_fmt": "passed", "compiler": "Rust 1.88.0", "steps": transport["steps"]},
    "original_runtime": {"records": dict(counts), "checks": accepted["checks"], "acceptance": accepted,
                         "owner_epochs": [r for r in records if r["event"] == "owner_running"], "queries": queries, "submissions": submissions,
                         "probe_and_agentd_compiler": "Rust 1.95.0", "desktop_cli_compiler": "Rust 1.88.0"},
    "independently_checked_retained_bytes": {"artifact_zip_digest_and_bytes": zip_rows,
        "artifact_members": 108, "complete_raw_runtime_equals_report": True, "gate_report_equals_embedded_full_job_log": True,
        "desktop_files_bound_to_fixed_git_commit": len(source["files"]), "owner_desktop_before_after_paths": 35,
        "transport_desktop_before_after_paths": 29, "probe_inputs_matched": 8, "profile_bytes_equal_compiled_fixture": True,
        "original_cargo_lock_sha256": contract["cargo_lock_sha256"], "generated_probe_lock_sha256": report["resolved_lock_sha256"],
        "original_root_manifest_sha256": contract_files["codex-rs/Cargo.toml"], "query_output_records_matched": 13,
        "submit_cli_output_records_matched": 4, "all_13_query_message_identity_pairs_matched": True},
    "ci_side_assertions_not_independent_local_elf_execution": {
        "owner_source": "CI verifies clean exact 2be commit/tree, f8 ancestry, all 36 contracted files and original Cargo.lock; prior sealed source audit independently reviewed 8 owner files, not all 36",
        "binaries": report["binaries"], "five_elf_guard": "Successful packaging step verifies regular executable paths, ELF64 little endian/AArch64 e_machine=183, recorded byte length and SHA256 after execution",
        "binary_manifest": "Stored only in the large ELF artifact; neither its raw manifest nor ELF bytes were downloaded in this review",
        "large_elf_artifact_downloaded": False,
        "journal_and_fault_assertions": "Raw before/injected/recovered journals and exact query/request outputs are preserved in the small owner ZIP; this seal does not claim independently decoding every journal frame",
        "cleanup": "Original controlled_stop record is active=false and CI job completed; no independent local process-tree observation of the remote runner"},
    "interpretation": [
        "ObjectiveAdmission queried an online original 2be owner across spawn generations 1,5,9,13; owner-stopped intervals are for storage fault injection, not the query API prerequisite.",
        "Compiled or explicit-abstain durable publication is admission history. RunStatus null neither disproves a publication nor resumes a run.",
        "The harness sent the lost-response request through the original protocol and read zero response bytes. It did not execute hepta-submit CLI reply-loss recovery.",
        "A separate actual hepta-submit returned submit_unknown/objective_owner_request_rejected after durable publication; history found publication 4. Capacity is a source-based inference, not an error detail returned in the wire response.",
        "Wrong/earlier anchor and altered signed request remain unknown. Restart history, expiry, retained-anchor rollback/truncation and revoked-issuer history were actually exercised under an isolated test issuer.",
        "No production issuer, model turn, device effect, Operations K/D or dispatch, kernel G1/G2, Session/Shell history integration, caller anchor+journal co-rollback, or historical run resumption was qualified."
    ],
    "source_nontransfer": "These runtime results belong only to desktop 46dcb2d + original 2be. They are not executions of main aab50f, R9 2bc/506, R9-sync, or the original f8 profile.",
    "prior_source_audit": {"path": "reviews/r9-main193-owner-history-review.json", "sha256": "fc8a409f93fa95c7d2fd5fbcbdf5734475975b00c02c6a69ac296ffe9e2e9c93", "unchanged": True},
    "storage": storage,
}
emit(STAGE / "review.json", review)
emit(STAGE / "STORAGE.json", {"schema": "lossless-log-storage.v1", "files": storage})
readme = """# PR193 actual original-owner Objective history CI

This is a read-only review of GitHub Actions run **39115155092**, attempt **1**, executed at desktop **46dcb2d691827f7aa3ad7903dae09d39fd338126** / tree **8d5de807c41090e3d987764daec9c235ebd022a1**, with original **hepta-private-ci@2be5fc052ae7b2e9fb08c68a3ae7e5a218ad37d5**. It is not a new execution at the later main merge, R9 source, or R9-sync candidate.

The two reviewed jobs completed successfully: [history-transport](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39115155092/job/117639353718) and [original-owner-history](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39115155092/job/117655596136). Seven checks at this head have successful API status; the other five jobs were not deeply reviewed here.

## Actual result

- Transport: **51 Rust tests**, **22 Python contract tests**, strict Clippy, default-off check and formatting passed, using Rust 1.88.0.
- Original runtime: **15 checks**, **13 online history queries**, **5 request attempts**, **4 published requests**, **0 recovery resubmissions**. Original Agentd and probe used Rust 1.95.0; three desktop CLIs used Rust 1.88.0.
- Original owner queried while running at spawn generations **1, 5, 9, 13**. Controlled owner-stopped intervals were used to inject rollback/truncation faults.
- Actual retained records cover compiled and explicit-abstain history, original-protocol harness response loss, a distinct actual submit-CLI `submit_unknown` after publication, anchors, signed-request mismatch, owner restart with RunStatus null, expiry, storage rollback/truncation, revocation, and controlled stop.

Historical publication does not establish a current run or completed device effect. The harness reply-loss case is not a `hepta-submit` CLI reply-loss qualification. Production issuer, caller request/anchor persistence and co-rollback handling, Session/Shell history integration, model turns, Operations K↔D, device effects and kernel G1/G2 remain outside this result.

## Preserved evidence and verification scope

The two original evidence ZIPs are preserved byte for byte and match their GitHub API SHA256 and byte length. They retain all **108 original members**, including complete compile/test logs, exact requests/query outputs, public test profile/trust records, fault journals, probe source/lock and runtime records. `owner/work/report.json` and `transport/checks.json` are convenient exact-byte copies. API JSON files preserve retrieved semantic payloads; full decoded job logs are retained separately.

`source/` is a read-only mirror of **36 fixed desktop Git files**, checked against the **35 owner-job** and **29 transport-job** before/after SHA bindings. Eight generated probe inputs, exact isolated profile bytes, original and generated lock digests, all 13 query output records and four CLI output records were independently matched. Full runtime JSON lines equal the report, which also equals the report embedded in the complete owner-job log.

All five ELF identities are recorded in `review.json` and the original runtime report. The successful CI packaging step verifies their AArch64 ELF headers, byte lengths and SHA256 after execution. **The 90.6 MB ELF artifact and its binary-manifest were not downloaded here.** The existing source audit independently reviewed eight original owner files; this follow-up does not claim a second independent download of all 36 contracted upstream files or independent decoding of every journal frame.

`STORAGE.json` records raw and stored hashes/lengths for the three losslessly gzip-wrapped logs (mtime 0). Original receipt bytes are unchanged. `SHA256SUMS` covers every published file except itself. The original ZIPs can be opened directly to inspect all raw logs and runtime evidence without any new workload execution. `seal_ci_review.py` records the local evidence-validation and packaging process; it requires the original unsealed review directory and is not a product or CI test.

The earlier fixed-source audit remains unchanged. Its pending-at-document-writing qualification statement is complemented by this independently retrieved actual CI result, not retroactively rewritten.
"""
(STAGE / "README.md").write_text(readme)
files = [{"path": str(p.relative_to(STAGE)), "bytes": p.stat().st_size, "sha256": digest(p.read_bytes())}
         for p in sorted(STAGE.rglob("*")) if p.is_file()]
emit(STAGE / "MANIFEST.json", {"schema": "published-ci-evidence.v1", "files": files})
sums = []
for p in sorted(STAGE.rglob("*")):
    if p.is_file():
        sums.append(digest(p.read_bytes()) + "  " + str(p.relative_to(STAGE)) + "\n")
(STAGE / "SHA256SUMS").write_text("".join(sums))
all_files = [p for p in STAGE.rglob("*") if p.is_file()]
seal = {"stage": str(STAGE), "files": len(all_files), "bytes": sum(p.stat().st_size for p in all_files),
        "sha256sums_sha256": digest((STAGE / "SHA256SUMS").read_bytes()), "review_sha256": digest((STAGE / "review.json").read_bytes()),
        "manifest_sha256": digest((STAGE / "MANIFEST.json").read_bytes())}
emit(BASE / "archive-seal.json", seal)
print(json.dumps(seal, indent=2))
