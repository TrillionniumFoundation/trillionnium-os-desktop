#!/usr/bin/env python3
"""Recover and recheck historical CI evidence. No product/test process is launched."""
from pathlib import Path, PurePosixPath
import datetime, gzip, hashlib, json, re, shutil, stat, zipfile, zlib

ROOT = Path(__file__).resolve().parent
MATERIALS = ROOT / "materials"
STAGE = ROOT / "archive-stage"
HEAD = "c4d4224c9daf1a5b22997930000f43001525d531"
TREE = "59e925797887187b902125ea2a162f71a5eabed4"
HEPTA = "f8c9419df6ddeb36ff8b522a50219981fb8d9345"
ZIP_SHA = "aaed616d85f52cd0c51672bd2bd22f43746bbf9c06c4c325002be3269594506c"
NOW = datetime.datetime.now(datetime.timezone.utc).isoformat()

def need(test, message):
    if not test:
        raise RuntimeError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

need(not STAGE.exists(), "Recovery archive directory must be new")
STAGE.mkdir()
sources = json.loads((ROOT / "source-materials.json").read_bytes())
run = json.loads((MATERIALS / "readback/run-api.json").read_bytes())
jobs = json.loads((MATERIALS / "readback/jobs-api.json").read_bytes())["jobs"]
artifacts = json.loads((MATERIALS / "readback/artifacts-api.json").read_bytes())["artifacts"]
by_id = {a["id"]: a for a in artifacts}
need(run["id"] == 39099387901 and run["head_sha"] == HEAD and run["head_commit"]["tree_id"] == TREE, "Run source")
need(run["run_attempt"] == 1 and run["status"] == "completed" and run["conclusion"] == "success", "Historical run result")
need(len(jobs) == 1 and jobs[0]["id"] == 117592347821 and jobs[0]["conclusion"] == "success", "Job identity/result")
need(all(x["conclusion"] == "success" for x in jobs[0]["steps"]), "Job steps")
zip_bytes = (MATERIALS / "evidence-12125674093.zip").read_bytes()
need(len(zip_bytes) == 1040029 and sha(zip_bytes) == ZIP_SHA, "Original ZIP bytes")
need(by_id[12125674093]["digest"] == "sha256:" + ZIP_SHA, "Official artifact digest")
patterns = {
    "github_classic_token_shape": rb"gh[pousr]_[A-Za-z0-9]{30,}",
    "github_fine_grained_token_shape": rb"github_pat_[A-Za-z0-9_]{40,}",
    "aws_access_key_shape": rb"(?:AKIA|ASIA)[A-Z0-9]{16}",
    "private_key_header": rb"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----",
    "signed_download_query": rb"(?:X-Amz-Signature|X-Goog-Signature)=[A-Za-z0-9%]+",
}
members = {}
inventory = []
with zipfile.ZipFile(MATERIALS / "evidence-12125674093.zip") as z:
    need(z.testzip() is None and len(z.infolist()) == 33, "Original ZIP CRC/count")
    for i in z.infolist():
        p = PurePosixPath(i.filename)
        need(not p.is_absolute() and ".." not in p.parts and i.filename not in members, "ZIP path")
        need(not i.is_dir() and not (i.flag_bits & 1), "ZIP type/encryption")
        need(stat.S_IFMT(i.external_attr >> 16) in (0, stat.S_IFREG), "ZIP regular file")
        need(p.suffix in {".json", ".toml", ".lock", ".log", ".txt", ".sha256", ".rs"}, "ZIP member kind")
        b = z.read(i)
        b.decode("utf-8")
        need(not b.startswith((b"\x7fELF", b"PK\x03\x04", b"\x1f\x8b", b"!<arch>\n")), "Executable or nested package")
        need(len(b) == i.file_size and zlib.crc32(b) == i.CRC, "ZIP member bytes/CRC")
        for name, pattern in patterns.items():
            need(not re.search(pattern, b), "Credential-shaped match: " + name + " in " + i.filename)
        members[i.filename] = b
        inventory.append({"path": i.filename, "bytes": len(b), "compressed_bytes": i.compress_size,
                          "crc32": f"{i.CRC:08x}", "sha256": sha(b), "utf8": True, "regular": True})
r = json.loads(members["report.json"])
records = [json.loads(x) for x in members["work/original_agentd_process_probe.log"].splitlines() if x]
need(records == r["runtime_records"] and members["report.json"] == members["logs/gate.log"], "Original records/report")
need(members["gate-exit-code.txt"] == b"0\n", "Original exit code")
need(all(r[x] == "passed" for x in ["status", "live_agentd_acceptance", "persistent_session_acceptance"]), "Original qualifications")
need(r["large_build_attempted"] is True and r["runtime_probe_attempted"] is True, "Original actual execution")
need(all(x["status"] == "passed" for x in r["steps"]) and not r["blockers"], "Original steps")
need(all(x is False for x in r["profile"].values()), "Original bounded profile")
need(r["upstream"]["commit"] == HEPTA and r["upstream"]["clean_checkout"], "Original pin")
checks = ["original_starting", "original_running", "bounded_capabilities_events", "missing_run_read",
          "same_process_draining", "original_restart", "old_spawn_rejected", "controlled_stop"]
session_checks = ["persistent_session_starting", "persistent_session_running", "persistent_session_draining",
                  "same_worker_same_instance", "old_spawn_stale_ipc_responsive", "explicit_session_replacement",
                  "replacement_running", "stopped_stale_ipc_responsive"]
need(records[-1]["event"] == "acceptance_pass" and records[-1]["checks"] == checks, "Original eight")
passes = [x for x in records if x["event"] == "session_acceptance_pass"]
need(len(passes) == 1 and passes[0]["checks"] == session_checks, "Session eight")
for p in [records[-1], passes[0]]:
    need(all(p[x] is False for x in ["objective_submission", "model_turn", "device_effect"]), "No objective/model/device effect")
need(passes[0]["shell_capture_qualified_by_this_record"] is False, "No Shell pixels")
phases = [x for x in records if x["event"] == "session_phase_observed"]
need([x["phase"] for x in phases] == ["starting", "running", "draining", "old_spawn_stale", "recovered_running", "stopped_stale"], "Six phases")
need([x["sequence"] for x in phases] == list(range(1, 7)), "Phase order")
keys = ["session_instance", "session_pid", "worker_tid", "runtime_dir", "session_socket_path"]
for group in [phases[:4], phases[4:]]:
    need(all(all(p[k] == group[0][k] for k in keys) for p in group), "Continuous Session identity")
need(all(phases[0][k] != phases[4][k] for k in ["session_instance", "session_pid", "worker_tid"]), "Explicit replacement")
need(all(phases[0][k] == phases[4][k] for k in ["runtime_dir", "session_socket_path"]), "Same runtime path")
phase_summary = []
for i, p in enumerate(phases):
    s, h = p["snapshot"], p["snapshot"]["hepta"]
    o = h["last_observation"]
    need(s["session_instance"] == p["session_instance"] and s["tasks"] == [], "Snapshot identity/empty tasks")
    need(o["agent_id"] == "22222222-2222-4222-8222-222222222222" and o["health"]["fenced"] is False and o["source_changed"] is False, "Source fences")
    need(o["spawn_generation"] == (1 if i < 4 else 5) and o["health"]["process_id"] == (23471 if i < 4 else 23598), "Agentd identity")
    if i in (3, 5):
        first = p["stale_verification"]["first_stale_snapshot"]
        need(h["connection"] == first["hepta"]["connection"] == "stale", "Stale response")
        need(first["hepta"]["last_observation"] == o, "Frozen historical observation")
        need(h["last_attempt_unix_ms"] > first["hepta"]["last_attempt_unix_ms"] > o["sampled_unix_ms"], "Two failure samples")
        need(s["resources"]["sampled_unix_ms"] > first["resources"]["sampled_unix_ms"], "IPC responsiveness")
        need(first["tasks"] == [] and first["session_instance"] == s["session_instance"], "First stale identity")
        need(h["error_code"] == ("protocol_mismatch" if i == 3 else "unavailable"), "Stale reason")
    else:
        life, generation = {0: ("starting", 1), 1: ("running", 2), 2: ("draining", 3), 4: ("running", 6)}[i]
        need(h["connection"] == "observed" and h["error_code"] is None, "Observed state")
        need((o["health"]["lifecycle"], o["current_generation"]) == (life, generation), "Lifecycle")
    phase_summary.append({"phase": p["phase"], "sequence": p["sequence"], "session_instance": p["session_instance"],
                          "session_pid": p["session_pid"], "worker_tid": p["worker_tid"], "original": p["original"],
                          "connection": h["connection"], "error_code": h["error_code"], "last_observation": o,
                          "last_attempt_unix_ms": h["last_attempt_unix_ms"], "tasks_count": 0})
stops = [x for x in records if x["event"] == "session_stopped"]
need(len(stops) == 2 and all(x["signal"] == 9 for x in stops), "Original cleanup records")
for actual, expected in zip(stops, [phases[0], phases[4]]):
    need(all(actual[k] == expected[k] for k in ["session_pid", "session_instance", "worker_tid"]), "Cleanup identity")
need(phases[3]["original"]["process_id"] == 23598 and phases[3]["original"]["spawn_generation"] == 5, "Old Session rejects actual replacement")
need(phases[5]["original"]["active"] is False and phases[5]["original"]["process_id"] is None, "Original stopped")

tree = {x["path"]: x for x in sources["selected_tree_entries"]}
source_records = []
pairs = [(line.split("  ", 1)[1], line.split("  ", 1)[0], "identity/desktop-inputs.sha256")
         for line in members["identity/desktop-inputs.sha256"].decode().splitlines()]
pairs += [(p, digest, "report.observer_source_sha256") for p, digest in r["observer_source_sha256"].items()]
for path, digest, origin in pairs:
    b = sources["sources"][path].encode()
    blob = hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest()
    need(sha(b) == digest and blob == tree[path]["sha"], "Fixed source SHA/blob: " + path)
    source_records.append({"path": path, "sha256": digest, "git_blob": blob, "record": origin})
need(len(source_records) == 28 and len({x["path"] for x in source_records}) == 25, "Source binding count")
for member, source in [("work/probe/src/main.rs", "tests/integration/hepta/original_agentd_probe.rs"),
                       ("work/probe/src/original_session_probe.rs", "tests/integration/hepta/original_session_probe.rs")]:
    need(members[member] == sources["sources"][source].encode(), "Actual probe source copy")
need(members["identity/consumer-source-trees.txt"].decode().splitlines() ==
     [tree[p]["sha"] for p in ["ui", "services/hepta-os"]], "Consumer trees")
m1, m2 = [members[f"work/original_probe_locked_metadata_{i}.log"] for i in [1, 2]]
need(m1 == m2 and r["probe_lock_stability"]["locked_metadata_passes"] == 2, "Historical locked metadata")
need(sha(members["work/probe/Cargo.lock"]) == r["probe_resolved_lock_sha256"] == r["probe_lock_stability"]["sha256"], "Historical probe lock")
need(sha(members["locks/hepta-original-Cargo.lock"]) == r["upstream"]["cargo_lock_sha256"], "Historical original lock")
final = json.loads(members["identity/final-checkouts.json"])
for name, before in [("desktop", "identity/desktop-before.txt"), ("hepta", "identity/hepta-before.txt")]:
    x = final["checkouts"][name]
    need(x["identity"]["exit_code"] == 0 and x["identity"]["stdout"].encode() == members[before], "Historical source pre/post")
    need(x["status"] == {"exit_code": 0, "stdout": "", "stderr": ""}, "Historical clean source")

packed = (MATERIALS / "readback/job-117592347821.log.gz").read_bytes()
log_bytes = gzip.decompress(packed)
need(len(log_bytes) == 145349 and sha(log_bytes) == "b2580573da0adea34417cc2b2cc0210dcdc79295c1e1af28426286d07c94cd69", "Original job bytes")
need(len(packed) == 25995 and sha(packed) == "563751ef8be61cb1f1639ae0634e6f5849a1ccd036eecf286554dda7a557b9e7", "Original gzip bytes")
for name, pattern in patterns.items():
    need(not re.search(pattern, log_bytes), "Job credential-shaped match: " + name)
log = "\n".join(re.sub(r"\x1b\[[0-9;]*m", "", re.sub(r"^\d{4}-\d\d-\d\dT[0-9:.]+Z ", "", line))
                  for line in log_bytes.decode().splitlines())
workflow = sources["sources"][".github/workflows/hepta-original-agentd.yml"]
script = workflow.split("      - name: Bind both successful runtime qualifications to five actual ARM64 ELF files\n", 1)[1]
script = script.split("        run: |\n", 1)[1].split("\n      - name:", 1)[0]
script = "\n".join(line[10:] if line.startswith("          ") else line for line in script.splitlines()).rstrip()
need(script in log and "header[18:20])[0] != 183" in script and "if executed_hash != actual:" in script, "Original five-ELF binding step")
for a in artifacts:
    need(a["digest"].split(":", 1)[1] in log and f"Artifact ID {a['id']}" in log, "Official upload declaration")
for p in ["evidence-12125674093.zip", "readback/run-api.json", "readback/jobs-api.json", "readback/artifacts-api.json",
          "readback/job-117592347821.log.gz", "source/.github/workflows/hepta-original-agentd.yml",
          "source/tests/integration/hepta/run_original_agentd.py"]:
    target = STAGE / p
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(MATERIALS / p, target)
for p in sorted((MATERIALS / "selected").rglob("*")):
    if p.is_file():
        target = STAGE / p.relative_to(MATERIALS)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(p.read_bytes())
shutil.copyfile(__file__, STAGE / "verify_readback.py")
new_record = {"recorded_at_utc": NOW, "record_kind": "new_recovery_record_not_original_05xx_curation",
              "historical_run_id": 39099387901, "historical_job_id": 117592347821}
save(STAGE / "readback/readback-receipt.json", {**new_record,
    "retained_stores": ["r7_arm_run_full", "r7_arm_jobs", "r7_arm_artifacts", "r7_arm_job_logs", "r7_arm_evidence_download"],
    "source": "Previous connector response values retained in functions stores; same artifact downloaded again",
    "run_head": HEAD, "file_references": {"original": "file_00000000c72c82309af87c8898fb47e5",
                                       "recovery": "file_0000000033348230b36d78c77a86d2ac"},
    "zip_recovery_receipt": json.loads((ROOT / "zip-recovery-receipt.json").read_bytes()),
    "job_log": {"original_bytes": len(log_bytes), "original_sha256": sha(log_bytes),
                "stored_bytes": len(packed), "stored_sha256": sha(packed), "gzip_mtime": 0},
    "signed_download_url_saved": False, "no_product_or_test_execution": True})
save(STAGE / "review/zip-members.json", {**new_record, "zip_bytes": len(zip_bytes), "zip_sha256": ZIP_SHA,
    "member_count": len(inventory), "members": inventory, "all_crc_passed": True,
    "all_regular_utf8": True, "elf_or_nested_package_payloads": False,
    "credential_shape_scan_matches": [], "scan_patterns": list(patterns), "scope": "Pattern scan and content inspection; not a universal secret detector"})
save(STAGE / "review/source-binding.json", {**new_record, "remote_head": HEAD, "remote_tree": TREE,
    "frozen_source_retrieval": sources["tree_api_url"], "tree_api_truncated": False,
    "source_records": source_records, "distinct_files": 25, "source_binding_records": 28,
    "all_sha256_and_git_blob_ids_match": True, "upstream_pin": HEPTA,
    "source_pre_post_clean_in_original_ci": True, "locked_metadata_raw_bytes_equal": True,
    "probe_lock_sha256": r["probe_resolved_lock_sha256"], "original_lock_sha256": r["upstream"]["cargo_lock_sha256"],
    "copied_probe_bytes_match_fixed_source": True, "new_compile_or_original_source_checkout": False})
save(STAGE / "review/phase-summary.json", {**new_record, "raw_jsonl_equals_report_records": True,
    "original_checks": checks, "session_checks": session_checks, "phases": phase_summary,
    "cleanup_records": stops, "original_effect_flags": {"objective_submission": False, "model_turn": False, "device_effect": False},
    "shell_pixel_qualification": "not_run", "analysis_only_no_new_runtime": True})
hashes = dict(r["binary_sha256"])
hashes.update({p: r["session_input_binaries"][p]["sha256"] for p in ["session", "ctl"]})
save(STAGE / "review/five-elf-binding-review.json", {**new_record,
    "evidence_kind": "Original report hashes plus exact successful CI command and official upload metadata",
    "reported_binary_sha256": hashes, "step_number": 10, "step_conclusion": "success",
    "script_matches_fixed_workflow_and_original_job_log": True, "ci_asserted_format": "ELF64 little endian AArch64 e_machine=183",
    "large_artifact_metadata": by_id[12126585987], "elf_zip_downloaded": False,
    "local_elf_rehash": False, "large_artifact_binary_manifest_directly_read": False})
(STAGE / "review/binding-step-as-logged.txt").write_text(script + "\n")
save(STAGE / "review/independent-review.json", {**new_record, "schema": "r7-arm-evidence-recovery-independent-review-v1",
    "status": "historical_readonly_ci_evidence_recovered_and_rechecked",
    "reviewer": "/root/r6_original_session", "head": HEAD, "tree": TREE, "upstream": HEPTA,
    "original_run_started_at": run["run_started_at"], "original_run_updated_at": run["updated_at"],
    "original_run_conclusion": "success", "original_check_count": 8, "persistent_session_check_count": 8,
    "original_runtime_record_count": len(records), "original_session_phase_count": 6,
    "source_binding_records": 28, "distinct_source_files": 25,
    "original_zip_sha_and_crc": "passed", "original_job_raw_and_gzip_sha": "passed",
    "stale_history_and_responsive_ipc_records": "passed", "original_cleanup_records": "passed",
    "historical_five_elf_binding_evidence": "passed_without_local_elf_read",
    "missing_prior_curation": {"original_independent_review_sha256": "9916620950b891a0e027b5c3e2429caa3e9eb44eb6cc094d9823d8e9d8f60fdb",
       "original_manifest_sha256": "cd93d719d0f291ddbeaabca8ff9d07e39102c7a5e9aff7e57f2c7b79337f03d3",
       "original_sha256sums_sha256": "15a07378222714e9b6349fa37bb8d8ba24b2599172a8eb479523a96740c3ea34",
       "original_final_verification_sha256": "f6de3938f624432db11d82e6e37b83be3aceffe411b37344edc00e5330ec9748",
       "original_full_curation_bytes_recovered": False, "original_generation_timestamps_not_invented": True},
    "scope": {"historical_qualification": "original_agentd_and_persistent_session_readonly_acceptance_passed",
              "new_test_or_product_execution": False, "objective_submission": False, "model_turn": False,
              "device_effect": False, "shell_pixels": "not_run", "objective_transport_admission": "not_qualified"}})
print(json.dumps({"status": "recovery_material_checks_passed", "stage": str(STAGE),
                  "files_before_index": len([p for p in STAGE.rglob("*") if p.is_file()]),
                  "recovery_recorded_at_utc": NOW, "zip_sha256": ZIP_SHA}, indent=2))
