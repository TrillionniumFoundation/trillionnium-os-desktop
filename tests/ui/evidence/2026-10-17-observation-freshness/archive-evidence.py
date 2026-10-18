#!/usr/bin/env python3
"""Curate reproducible R6 freshness check evidence; never copy executable bytes."""
from pathlib import Path
import gzip
import hashlib
import json
import shutil
import subprocess

BASE = Path(__file__).resolve().parent
OUT = BASE / "archive"
SOURCE = BASE.parent.parent / "next-r6-ui-fix"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_object(commit, suffix):
    return subprocess.check_output(
        ["git", "-C", str(SOURCE), "rev-parse", commit + suffix], text=True
    ).strip()


OUT.mkdir(mode=0o700)
for name in ("copy-target.py", "run-checks.py", "post-check-r5-retention.json", "archive-evidence.py"):
    shutil.copy2(BASE / name, OUT / name)
with (OUT / "copy-receipt.json.gz").open("xb") as stream:
    with gzip.GzipFile(filename="copy-receipt.json", mode="wb", fileobj=stream, mtime=0) as zipped:
        zipped.write((BASE / "copy-receipt.json").read_bytes())

receipts = {}
for name in ("red-01", "green-01", "green-02", "green-03"):
    run = BASE / name
    destination = OUT / name
    destination.mkdir(mode=0o700)
    for path in sorted(run.iterdir()):
        if path.is_file() and path.suffix in (".json", ".log", ".py", ".d"):
            shutil.copy2(path, destination / path.name)
    receipts[name] = json.loads((run / "receipt.json").read_text())

binding = {}
for name, receipt in receipts.items():
    commit = receipt["source_commit"]
    paths = ("ui", "ui/Cargo.toml", "ui/Cargo.lock", "ui/shell/src",
             "services/hepta-os/src", "services/hepta-os/Cargo.toml", "services/hepta-os/Cargo.lock")
    binding[name] = {"source_commit": commit, "source_tree": git_object(commit, "^{tree}"),
                     "git_objects": {path: git_object(commit, ":" + path) for path in paths}}
    if binding[name]["source_tree"] != receipt["source_tree"]:
        raise RuntimeError("frozen source tree mismatch: " + name)
(OUT / "source-bindings.json").write_text(json.dumps(binding, indent=2) + "\n")

green = receipts["green-03"]
red_binding = json.loads((OUT / "red-01/executed-test-binding.json").read_text())
report = {
    "status": "passed_after_preserved_failures",
    "scope": "native Shell source regression and source-bound workspace build; no original runtime capture in this bundle",
    "green_attempt_count": 3,
    "green_failed_attempt_count": 2,
    "green_passed_attempt_count": 1,
    "source_commit": green["source_commit"],
    "source_tree": green["source_tree"],
    "runtime_freshness_tests_passed": 6,
    "layout_predicate_tests_passed": 2,
    "strict_shell_clippy_passed": True,
    "workspace_format_check_passed": True,
    "workspace_production_build_passed": True,
    "red_actual_test_binary_sha256": red_binding["actual_executed_test_sha256"],
    "green_actual_test_binary_sha256": green["test_binary"]["sha256"],
    "actual_status_text_in_red": "Hepta: OBSERVED · READ ONLY",
    "required_status_text_in_green": "STALE · CURRENT STATE UNKNOWN",
    "delayed_sample_unix_ms": 10000,
    "simulated_current_unix_ms": 18001,
    "synthetic_response_queue_test": True,
    "actual_egui_status_widget_test": True,
    "original_agentd_six_phase_capture_qualified_by_this_bundle": False,
    "physical_display_or_device_tested": False,
    "retained_R5_four_ELFs_rehashed_unchanged": True,
    "binaries": green["binaries"],
    "copy_manifest_uncompressed_sha256": sha(BASE / "copy-receipt.json"),
    "copy_manifest_compressed_sha256": sha(OUT / "copy-receipt.json.gz"),
    "executables_or_target_caches_in_archive": False,
}
(OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")

rows = "\n".join(
    "| `{}` | {:,} | `{}` |".format(name, value["bytes"], value["sha256"])
    for name, value in green["binaries"].items()
)
readme = f"""# R6 Shell observation freshness — actual RED/GREEN evidence

The final frozen source `{green['source_commit']}` passed the six targeted
freshness regressions, two existing layout-predicate tests, Shell Clippy with
`-D warnings`, workspace formatting and the native workspace binary build.
This bundle retains the successful result and all preceding attempts. There
were **three GREEN attempts: two failed, the third passed**.

## Defect and resulting behavior

A Session response can wait in the Shell queue while the UI is paused. The old
pre-draw path assigned a new local receipt time when it consumed that response,
then tested only receipt age. The RED test used sample time `10000` and current
time `18001` with a just-received response. The real `hepta_panel::status`
widget produced **`Hepta: OBSERVED · READ ONLY`** for this expired observation.
The exact text is retained in `red-01/freshness-tests.log`.

The fix evaluates both the original observation timestamp and the local
monotonic receipt before painting any page. Both ages may be at most 7000 ms;
7001 ms expires the observation. Future or missing timestamps cannot appear
current. Downgrading preserves the full previous observation, the Session's
attempt timestamp and existing unknown-state diagnostics. A later fresh
Session snapshot may restore Observed. The delayed-response regression now
requires the actual widget text `STALE · CURRENT STATE UNKNOWN`.

The queue in these deterministic tests is synthetic; the Desktop receive path,
pre-draw expiry path and egui status widget are the real production code. These
tests are not original Agentd, compositor-pixel, physical display, keyboard,
device-control or objective-submission evidence. The original six-phase Shell
captures are a separate gate and are not claimed by this bundle.

## Attempts and executed code identity

| Attempt | Frozen source | Actual result | Interpretation |
| --- | --- | --- | --- |
| RED-01 | `821841baf5c106b7fc5e4b849ac94636b1b724f7` | Cargo 101; 1 passed / 5 intended failed | Old production behavior was reproduced through the actual status widget. Helper success means the expected failure was observed, not that the product passed. |
| GREEN-01 | `f0f10dff564037fabc35809a8d8bb174dc5becb9` | Cargo reused RED's test ELF; 1 passed / 5 failed | Warm-target source binding failed. Cargo printed no Shell compile line and finished its test profile in 0.15 s. This is not a GREEN source regression. |
| GREEN-02 | `f0f10dff564037fabc35809a8d8bb174dc5becb9` | Actual Shell recompile; 6 freshness + 2 layout tests passed; Clippy 101 | Strict lint rejected only the new test helper's complex sender return type. Production behavior passed its targeted assertions; the complete gate still failed. |
| GREEN-03 | `{green['source_commit']}` | Actual Shell recompile; 6 + 2 passed; Clippy/fmt/workspace build all 0 | A named test sender type resolved the lint. This is the final passing source and build. |

RED extracted the real pre-draw entry while preserving its old receipt-only
semantics. Commit `f0f10dff564037fabc35809a8d8bb174dc5becb9` added the dual-clock
fix. Final commit `{green['source_commit']}` only names the test sender type.
The final source tree is `{green['source_tree']}`. `source-bindings.json` also
records the UI manifest/lockfile and the Session's external `hepta-os` source
and manifest objects.

The RED test ELF SHA-256 is
`{red_binding['actual_executed_test_sha256']}`. GREEN-02's genuinely recompiled
test ELF is `{receipts['green-02']['test_binary']['sha256']}`. GREEN-03's executed
test ELF is `{green['test_binary']['sha256']}`. The preserved cache diagnosis
records the older GREEN source mtime and workspace-relative dep-info: neither
absolute worktree appears in that dep-info. Assertions and source line numbers
in GREEN-01 match RED; a clean frozen HEAD alone was not sufficient proof.

## Cache, cleanup and resource limits

The R5 target was copied into a fresh task-owned disk directory, with all 2,754
regular files / 909,594,005 bytes verified by SHA-256 on source and destination.
`copy-receipt.json.gz` is the complete unchanged copy manifest, compressed with
a fixed gzip timestamp; its uncompressed SHA-256 is
`{report['copy_manifest_uncompressed_sha256']}`. `post-check-r5-retention.json`
rehashes the four retained R5 production ELFs after all UI tests/builds and
confirms their bytes remain unchanged. That second check is explicitly scoped
to those four ELFs, not a second full target-cache scan.

To resolve observed cross-worktree cache reuse, subsequent attempts run the
recorded command `cargo clean --manifest-path ui/Cargo.toml -p trill-shell
--locked --offline` with `CARGO_TARGET_DIR` set only to the new copied target.
Every accepted test run must then contain the actual Shell compile line for
the frozen source directory. No retained R5 target artifact was cleaned.

The helper uses Rust 1.88.0, offline locked Cargo, one build job, no incremental
or debug information, a 300-second per-command deadline, a 1-GiB disk reserve
and a 7-GiB nonreclaimable-memory stop threshold. Per-command logs, observed
exit codes, cwd, source pins, target directory, samples and timing remain in
each receipt. Each attempt includes the helper and process-group guard source
snapshot taken before execution. The guard retains and reaps its owned process
group; this build evidence does not claim arbitrary descendant-parent-death
qualification.

## Final four workspace binaries

| Binary | Bytes | SHA-256 |
| --- | ---: | --- |
{rows}

`green-03/production-build.log` records compilation of `hepta-os-observer`,
`trill-session`, `trill-shell` and `trill-app-window`. The final workspace
command also verifies `trill-ctl`; it has no separate compile line in that
command. The app-window build reproduced the same bytes as R5. All four paths,
ELF x86_64 checks, sizes and hashes are recorded; four changed hashes are not
claimed. These are Linux host binaries, not target-kernel or mobile-device
execution evidence.

## Review and archive checks

Run `sha256sum -c SHA256SUMS` in this directory to verify the curated bytes.
Use `gzip -dc copy-receipt.json.gz` to inspect the complete original copy
manifest. This archive contains no target cache, executable bytes, credentials,
Xauthority cookie, private runtime state, model calls or screenshots.
"""
(OUT / "README.md").write_text(readme)
files = sorted(path for path in OUT.rglob("*") if path.is_file())
for path in files:
    if path.read_bytes()[:4] == b"\x7fELF":
        raise RuntimeError("executable accidentally entered archive: " + str(path))
(OUT / "SHA256SUMS").write_text("".join(sha(path) + "  " + str(path.relative_to(OUT)) + "\n" for path in files))
print(json.dumps({"archive": str(OUT), "files": len(files) + 1,
                  "bytes": sum(path.stat().st_size for path in OUT.rglob("*") if path.is_file()),
                  "report_sha256": sha(OUT / "report.json")}, indent=2))
