#!/usr/bin/env python3
"""Closed source correspondence for proposed GitHub required-check contexts.

This finite workflow inventory reads no credentials and applies no repository
settings. A source name or successful check can never establish execution,
independent approval, branch protection, installed qualification or G0 closure.
"""
from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import re
import sys

try:
    from .browser_codec_reference_security import load_json_strict, open_managed_regular_beneath
except ImportError:
    from browser_codec_reference_security import load_json_strict, open_managed_regular_beneath

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "contracts/ci-required-contexts.v1.json"
MAX_FILE_BYTES = 131072
WORKFLOWS = (
    "agent-port-custody", "agent-transport-reference", "approved-mechanism-policy",
    "authenticated-update-readback", "browser-codec-reference", "ci", "controlled-egress",
    "d1-final-qualification", "d2i-integrated-image", "g2-approved-native-startup",
    "g2-native-product-owner", "module-documentation", "receipt-journal", "s04-transport-custody",
    "s06-browser-actor", "s07-servo-retained-node", "s08-product-servo-runtime",
    "s08-servo-vertical-slice", "s09-linux-platform-adapters", "s10-production-debian-qemu",
    "s11-update-recovery", "s12-release-qualification", "self-hosted-desktop-availability",
    "self-hosted-fleet-availability", "servo-exact-pin", "servo-headed-runtime", "update-boot-observer",
)
MATRIX_WORKFLOWS = frozenset({"approved-mechanism-policy", "authenticated-update-readback",
                               "controlled-egress", "update-boot-observer"})
AVAILABILITY_WORKFLOWS = frozenset({"self-hosted-desktop-availability", "self-hosted-fleet-availability"})
MATRIX_EXPRESSION = "${{ github.event_name == 'pull_request' && fromJSON('[\"head\",\"prospective-merge\"]') || fromJSON('[\"head\"]') }}"
PROFILE = {
    "repository": "TrillionniumFoundation/trillionnium-os-desktop",
    "expected_application": {"slug": "github-actions", "app_id": 15368,
                             "binding": "required_status_checks.checks[].context+app_id"},
    "naming": "workflow_filename_stem / original_job_id / optional_original_matrix_object",
    "matrix_expression": MATRIX_EXPRESSION,
    "matrix_lanes": {"pull_request": ["head", "prospective-merge"], "push": ["head"],
                     "workflow_dispatch": ["head"]},
    "limits": {"files": 28, "file_bytes": MAX_FILE_BYTES, "jobs": 64, "context_utf8_bytes": 128},
    "administration": {"status": "PROPOSAL_REQUIRES_CURRENT_HOSTED_READBACK_AND_ADMIN_REVIEW",
                       "strict_up_to_date_proposed": True, "any_application_allowed": False,
                       "apply_entire_inventory_as_global_requirements": False,
                       "path_filtered_missing_check_policy_review_required": True,
                       "conditional_and_skipped_check_execution_review_required": True,
                       "manual_context_is_required_pr_execution": False},
    "claims": {"source_correspondence_only": True, "hosted_names_observed": False,
               "settings_applied": False, "independent_approval": False,
               "check_success_proves_actual_execution": False, "G0_closed": False,
               "installed_qualified": False, "production_ready": False},
}
INDEX = {"module": "hepta-browser-codec", "tool": "tools/verify_ci_required_contexts.py",
         "test": "tests/test_ci_required_contexts.py", "documentation": "docs/architecture/CI_REQUIRED_CONTEXTS.md"}


def exact(actual: object, expected: object, label: str) -> None:
    # JSON encoding preserves booleans vs integers; ordinary Python equality does not.
    if json.dumps(actual, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False):
        raise ValueError(label + " differs from its closed source profile")


def inventory(path: str, text: str) -> tuple[str, dict[str, dict[str, object]], list[str], bool, list[str]]:
    """Recognize only the checked-in finite indentation profile, not general YAML.

    The digest retains every byte except job-level display-name lines. Therefore
    aliases, duplicate keys, different conditions/steps/matrices/flags and new
    YAML shapes require an explicit source review and a new recorded digest.
    """
    stem = Path(path).stem
    if text.count("\njobs:\n") != 1 or "\r" in text or "\t" in text:
        raise ValueError("workflow does not match the finite job inventory")
    lines = text.splitlines(keepends=True)
    start = lines.index("jobs:\n") + 1
    markers = [i for i in range(start, len(lines)) if re.fullmatch(r"  [A-Za-z_][A-Za-z0-9_-]*:\n", lines[i])]
    if not markers or markers[0] != start:
        raise ValueError("workflow requires explicit job mappings")
    jobs: dict[str, dict[str, object]] = {}
    names: set[int] = set()
    conditional: list[str] = []
    for n, marker in enumerate(markers):
        end = markers[n + 1] if n + 1 < len(markers) else len(lines)
        job_id = lines[marker].strip()[:-1]
        if job_id in jobs:
            raise ValueError("duplicate job ID")
        section = lines[marker + 1:end]
        found = [i for i in range(marker + 1, end) if lines[i].startswith("    name:")]
        if len(found) != 1 or found[0] != marker + 1:
            raise ValueError("one canonical display name must immediately follow its original job ID")
        name = lines[found[0]][len("    name: "):].removesuffix("\n")
        prefix = stem + " / " + job_id
        matrix = stem in MATRIX_WORKFLOWS
        expected_name = prefix + (" / ${{ matrix.object }}" if matrix else "")
        if name != expected_name:
            raise ValueError("job display name differs from canonical context")
        matrix_lines = [line for line in section if line.startswith("    strategy:") or line.startswith("        object:")]
        if matrix:
            if matrix_lines != ["    strategy:\n", "        object: " + MATRIX_EXPRESSION + "\n"]:
                raise ValueError("original finite matrix lanes differ")
        elif matrix_lines:
            raise ValueError("unreviewed matrix job")
        if any(line.startswith("    if:") for line in section):
            conditional.append(job_id)
        jobs[job_id] = {"display_name": name, "matrix_object": matrix,
                        "contexts": [prefix + " / " + lane for lane in ("head", "prospective-merge")] if matrix else [prefix],
                        "kind": "availability_diagnostic" if stem in AVAILABILITY_WORKFLOWS else "repository_source_check"}
        names.add(found[0])
    body = "".join(line for i, line in enumerate(lines) if i not in names)
    events = [line.strip()[:-1] for line in lines[:start - 1]
              if re.fullmatch(r"  (?:pull_request|push|workflow_dispatch):\n", line)]
    return hashlib.sha256(body.encode("utf-8")).hexdigest(), jobs, events, any(line == "    paths:\n" for line in lines[:start]), conditional


def check(catalog: object, texts: dict[str, str]) -> dict[str, object]:
    if type(catalog) is not dict or set(catalog) != {"schema", "profile", "source_index", "workflows"}:
        raise ValueError("required-context catalog fields differ")
    exact(catalog["schema"], "trillionnium.ci-required-contexts.v1", "schema")
    exact(catalog["profile"], PROFILE, "profile")
    exact(catalog["source_index"], INDEX, "source index")
    expected_paths = [".github/workflows/" + stem + ".yml" for stem in WORKFLOWS]
    if type(catalog["workflows"]) is not dict or set(catalog["workflows"]) != set(expected_paths) or set(texts) != set(expected_paths):
        raise ValueError("closed workflow catalog differs")
    contexts: set[str] = set()
    source_count = diagnostic_count = job_count = 0
    for path in expected_paths:
        if type(texts[path]) is not str:
            raise ValueError("workflow text must be UTF-8 source")
        body_sha, jobs, events, filtered, conditional = inventory(path, texts[path])
        expected = {"body_without_job_display_names_sha256": body_sha, "jobs": jobs,
                    "trigger_events": events, "path_filtered": filtered, "conditional_jobs": conditional}
        exact(catalog["workflows"][path], expected, path)
        for job in jobs.values():
            job_count += 1
            for context in job["contexts"]:
                if not context.isascii() or len(context.encode("utf-8")) > 128 or context in contexts:
                    raise ValueError("context is duplicated or outside its finite byte profile")
                contexts.add(context)
                if job["kind"] == "repository_source_check": source_count += 1
                else: diagnostic_count += 1
    if job_count > 64:
        raise ValueError("job inventory is over its bound")
    return {"status": "PASS_SOURCE_CONTEXT_CORRESPONDENCE_ONLY", "workflows": len(expected_paths),
            "jobs": job_count, "unique_contexts": len(contexts), "repository_source_contexts": source_count,
            "availability_diagnostic_contexts": diagnostic_count, "settings_applied": False,
            "hosted_names_observed": False, "G0_closed": False, "production_ready": False}


def validate(root: Path = ROOT) -> dict[str, object]:
    root = root.absolute()
    paths = [CONTRACT, *[".github/workflows/" + stem + ".yml" for stem in WORKFLOWS]]
    actual = sorted(str(p.relative_to(root)) for p in (root / ".github/workflows").iterdir()
                    if p.suffix in {".yml", ".yaml"})
    if actual != sorted(paths[1:]):
        raise ValueError("workflow files differ from the closed catalog")
    documents: dict[str, str] = {}
    with ExitStack() as stack:
        owners = []
        for relative in paths:
            path = root / relative
            reader = stack.enter_context(open_managed_regular_beneath(root, path, label="CI context source"))
            before = reader.stat()
            if before.st_size > MAX_FILE_BYTES or before.st_nlink != 1:
                raise ValueError("CI context source exceeds its regular single-link file profile")
            raw = reader.read(MAX_FILE_BYTES + 1)
            if len(raw) != before.st_size:
                raise ValueError("CI context source changed length while reading")
            documents[relative] = raw.decode("utf-8", "strict")
            owners.append((path, reader, before))
        catalog = load_json_strict(documents.pop(CONTRACT))
        result = check(catalog, documents)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        for path, reader, before in owners:
            if identity(before) != identity(reader.stat()) or identity(before) != identity(path.lstat()):
                raise ValueError("CI context source changed through final inventory validation")
        return result


if __name__ == "__main__":
    try:
        print(json.dumps(validate(), sort_keys=True))
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        print("CI context source refused: " + str(error), file=sys.stderr)
        raise SystemExit(1)
