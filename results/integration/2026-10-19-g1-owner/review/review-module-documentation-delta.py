#!/usr/bin/env python3
"""Compare a retained R9 documentation review with explicit R10 source/overlay bytes."""

import argparse
import hashlib
import json
import posixpath
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--main-base", default="e15ae6a63edb5d4e7c475a001be82111d451b653")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    historical_base = "0c2bf0fc1ba473325a0266c7bd476b1ddbf66383"
    base = args.main_base
    source = args.source_head
    assert re.fullmatch(r"[0-9a-f]{40}", source)

    def git(*argv):
        return subprocess.check_output(["git", *argv], cwd=repo)

    def immutable(path, commit=source):
        result = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=repo, capture_output=True)
        return result.stdout if result.returncode == 0 else None

    new_prefix = "results/integration/2026-10-19-g1-owner/"
    overlays = {"docs/INDEX.md", "docs/STATUS.md"}

    def read(path):
        if path in overlays or path.startswith(new_prefix):
            item = repo / path
            return (item.read_bytes(), "uncommitted_delivery_overlay") if item.is_file() else (None, "missing_delivery_overlay")
        data = immutable(path)
        return data, "fixed_source_commit" if data is not None else "absent_fixed_source"

    def target(path):
        data, origin = read(path)
        return {"path": path, "exists": data is not None, "origin": origin, "bytes": len(data) if data is not None else None, "sha256": sha(data) if data is not None else None}

    baseline_path = "results/integration/2026-10-18-objective-history/module-documentation-review.json"
    baseline_bytes = immutable(baseline_path, historical_base)
    assert baseline_bytes is not None
    assert (repo / baseline_path).read_bytes() == baseline_bytes
    old = json.loads(baseline_bytes)

    baseline_comparison = []
    for entry in old["local_document_manifest"]:
        current = target(entry["path"])
        current["historical_bytes"] = entry["bytes"]
        current["historical_sha256"] = entry["sha256"]
        current["byte_status"] = "missing" if not current["exists"] else "unchanged" if current["sha256"] == entry["sha256"] else "changed"
        baseline_comparison.append(current)

    def links_from(document, content):
        result = []
        for label, raw in re.findall(r"\[([^\]]+)\]\(([^\s)]+)\)", content):
            parsed = urlsplit(raw)
            if parsed.scheme or parsed.netloc:
                result.append({"from": document, "label": label, "href": raw, "scope": "external_reference_not_refetched"})
                continue
            relative = unquote(parsed.path)
            path = posixpath.normpath(posixpath.join(posixpath.dirname(document), relative)) if relative else document
            assert not path.startswith("../") and not path.startswith("/")
            info = {"from": document, "label": label, "href": raw, "scope": "local", **target(path)}
            if parsed.fragment:
                # File presence is the gate here; archive and heading anchors are separately reviewed.
                info["fragment"] = parsed.fragment
                info["fragment_check"] = "not_part_of_this_target_presence_gate"
            result.append(info)
        return result

    index = (repo / "docs/INDEX.md").read_text()
    rows = [line for line in index.splitlines() if re.match(r"\| A\d\d ", line)]
    assert len(rows) == 11
    module_rows = []
    for row in rows:
        module = re.match(r"\| (A\d\d) ", row).group(1)
        module_rows.append({"id": module, "links": links_from("docs/INDEX.md", row)})
    local_index = [link for module in module_rows for link in module["links"] if link["scope"] == "local"]

    substantive_documents = [
        {"path": "docs/ASTERINAS_CPU_OWNER_G1A.md", "review": "New detailed developer/technical manual read in full: source/dependencies, same real budget/revision, private binding/errors, detached lifecycle, lock order, fixed seed/working lock, ten ktests and qualification limits."},
        {"path": "support/build/README.md", "review": "Actual R10 diff read: original Git seed versus exact working derivative, unchanged external package records, complete component metadata with --locked, run-base and OSDK provenance."},
        {"path": "support/build/ktest/README.md", "review": "Actual R10 diff read: verified locked fetch before offline normalization, immutable seed, 200/97 derived test locks, explicit features, source stability and soft-skip treatment."},
        {"path": "docs/ASTERINAS_CPU_BANDWIDTH_N0.md", "review": "Actual G1 and incoming e15 diffs read, then combined source checked: G1-a manual and e15 malformed cpu.max input-contract sections are both retained; original N0 execution identities remain separate."},
        {"path": "tests/kernel/control/README.md", "review": "New candidate manual read in full: source/head/tree gate, ordinary non-ktest boot first, same ELF QueryAbi guest, valid-shaped four disabled operations, markers, timeouts, original replay preservation and separate host-fixture scope."},
        {"path": "docs/agents/handoffs/A04_LINUX_HEPTA_ELF.md", "review": "Incoming e15 164-line handoff read in full: actual candidate source owners, toolchain and binary pins, independent checkout/build/reference/rootfs/QEMU commands, full input/output/error semantics, same-ELF limits and current-main integration sequence. This is a concrete main developer/technical entry; the three original implementation directories and complete candidate manuals remain external."},
        {"path": "docs/DESKTOP_UX.md", "review": "Incoming e15 delta read: complete Runtime monotonic total age, independent known-run source clock, 7000/7001 ms boundary, matched Session/Shell/ctl deployment, CLI process-loss uncertainty, and separate identities for old pixels, original-owner history and new source integration."},
        {"path": "docs/agents/PLAN.md", "review": "Incoming e15 delta read: A06 ownership includes the actual cgroup CPU controller and its cpu subtree, keeps one budget owner and coordinates shared OSTD changes."},
        {"path": "docs/agents/R8_NEXT_SLICE.md", "review": "Incoming e15 delta read: distinguish original protocol lost-reply qualification from actual CLI SIGKILL handshakes; retain missing receipt as uncertainty and leave durable request/anchor storage and S1/S2 product assembly open."},
        {"path": "docs/agents/R9_G1_OWNER_SEAM.md", "review": "Incoming e15 delta read: retain the fixed historical audit while identifying #195 parser rejection as already integrated; later G1-a owner implementation is evidenced by its own new manual and tests, not silently inserted into this historical source audit."},
        {"path": "services/hepta-os/OBJECTIVE_TRANSPORT.md", "review": "Incoming e15 delta read: real CLI EOF-before-send and full-frame-before-reply kill boundaries, handshake/peer evidence, no receipt or retry, exact caller-owned request preservation and remaining durable reconciliation work."},
        {"path": "support/ui/CHAT_WORKSPACE.md", "review": "Incoming e15 delta read: Runtime and known-run total monotonic age with wall-time checks, preserved repeated-source age, visible/layout agreement, independent host-task rule and matched version deployment."},
        {"path": "support/ui/HEPTA_OBSERVER.md", "review": "Incoming e15 delta read: complete poll start and successful sequence ownership, failed-read and historical sample retention, separate Runtime/known-run clocks, source identity, stale dispatch and old/new strict decoder compatibility."},
        {"path": "tests/integration/hepta/ORIGINAL_AGENTD.md", "review": "Incoming e15 delta read: successful exit does not prove same-group descendants stopped; WNOWAIT identity anchor and bounded TERM/grace/KILL precede unique reap. Real RED/GREEN process-guard receipts and local skipped fixed-original manifest checks remain distinct."},
        {"path": "ui/shell/OBSERVATION_FRESHNESS.md", "review": "Incoming e15 replacement/delta read: three-term total bound, source and sequence rules, monotonic/wall failures, same-sample no rejuvenation/no duplicated RTT, matching wire builds, real queue/egui and scripted UDS regression scope."},
    ]
    substantive = []
    one_hop = []
    for item in substantive_documents:
        current = target(item["path"])
        assert current["exists"], item["path"]
        previous = immutable(item["path"], base)
        initial = immutable(item["path"], historical_base)
        current.update({"review": item["review"], "main_base_status": "new" if previous is None else "modified" if sha(previous) != current["sha256"] else "unchanged", "main_base_sha256": sha(previous) if previous is not None else None, "initial_0c_status": "new" if initial is None else "modified" if sha(initial) != current["sha256"] else "unchanged"})
        substantive.append(current)
        one_hop += links_from(item["path"], read(item["path"])[0].decode())

    a04 = []
    for item in old["external_A04_documents"]:
        entry = {"path": item["path"], "external_commit": item["commit"], "external_url": item["url"], "exists_at_main_base": immutable(item["path"], base) is not None, "exists_at_r10_source": immutable(item["path"]) is not None, "external_document_refetched_by_this_delta": False}
        assert not entry["exists_at_main_base"] and not entry["exists_at_r10_source"]
        a04.append(entry)

    api_path = new_prefix + "source-publication/upstream-and-a04-current-api.json"
    api_bytes = read(api_path)[0]
    api = json.loads(api_bytes)
    pr8 = json.loads(api["a04"]["value"]["structuredContent"]["content"])
    assert pr8["head"]["sha"] == "25c681d944e4efa92f2772cf773e03ae811bc345"
    assert pr8["state"] == "open" and pr8["draft"] and not pr8["merged"]

    missing = [link for link in local_index + [entry for entry in one_hop if entry["scope"] == "local"] if not link["exists"]]
    result = {
        "schema": "r10.module-documentation-delta.v1",
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source,
        "source_tree": git("rev-parse", source + "^{tree}").decode().strip(),
        "main_base": base,
        "initial_historical_base": historical_base,
        "documentation_overlay": {"tracked_paths": sorted(overlays), "new_results_prefix": new_prefix, "meaning": "Explicit local delivery files over the immutable product source; a later docs commit/publication receipt binds these same bytes. This does not claim all overlays already exist in main."},
        "historical_baseline": {"path": baseline_path, "bytes": len(baseline_bytes), "sha256": sha(baseline_bytes), "reviewed_commit": old["reviewed_commit"], "reviewed_tree": old["reviewed_tree"], "recorded_at_utc": old["recorded_at_utc"], "historical_summary": old["summary"], "historical_review_rerun": False, "full_manual_content_review_repeated": False},
        "current_scope": {"module_rows_checked": len(module_rows), "index_local_targets_checked": len(local_index), "index_missing": sum(not link["exists"] for link in local_index), "new_or_modified_manuals_substantively_read": len(substantive), "their_one_hop_local_targets_checked": sum(link["scope"] == "local" for link in one_hop), "one_hop_missing": sum(not link["exists"] for link in one_hop if link["scope"] == "local"), "historical_materials_byte_compared": len(baseline_comparison), "historical_material_status_counts": {label: sum(entry["byte_status"] == label for entry in baseline_comparison) for label in ["unchanged", "changed", "missing"]}, "root_README_bytes": len(read("README.md")[0]), "cargo_invocations": 0, "qemu_invocations": 0, "module_runtime_tests": 0, "new_runtime_qualification": False},
        "module_rows": module_rows,
        "substantively_reviewed_manual_deltas": substantive,
        "new_manual_one_hop_targets": one_hop,
        "historical_local_material_byte_comparison": baseline_comparison,
        "A04_exception": a04,
        "A04_concrete_main_handoff": target("docs/agents/handoffs/A04_LINUX_HEPTA_ELF.md"),
        "A04_current_PR_observation": {"source": api_path, "bytes": len(api_bytes), "sha256": sha(api_bytes), "observed_at_utc": api["at_utc"], "performed_by_root_API_read": True, "head": pr8["head"]["sha"], "state": pr8["state"], "draft": pr8["draft"], "merged": pr8["merged"], "meaning": "A new root API observation was read from its immutable receipt; this documentation helper did not refetch remote candidate document contents."},
        "incoming_main_document_delta": {"main": base, "changed_Markdown_from_0c": 13, "INDEX_STATUS_three_way_merged": True, "manual_overlap_with_G1": "docs/ASTERINAS_CPU_BANDWIDTH_N0.md", "substantive_manuals_count_excludes_INDEX_STATUS": True},
        "findings": ["A01 and A06 now link the concrete G1-a owner manual. A05 links the independent ordinary-candidate QueryAbi manual.", "Shared contracts remain legitimate module documentation; this check does not create independent handbooks for every module.", "Incoming e15 adds a concrete 164-line A04 main handoff, read substantively here. The three original complete manuals/implementation directories remain external and absent locally; it is no longer correct to call A04 wholly without a main handoff.", "The 53 INDEX targets and 225 nested targets belong to the original R9 review; only counts in current_scope were executed by this new delta review.", "Product tests, hardware support, security remediation and PR merge state are not established by target existence or documentation bytes."],
        "blocking_missing_targets": missing,
        "status": "passed_explicit_source_plus_overlay_target_and_manual_delta_review" if not missing else "failed_missing_targets",
    }
    assert result["current_scope"]["root_README_bytes"] == 0
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "current_scope": result["current_scope"], "output": str(args.output)}, ensure_ascii=False))
    if missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
