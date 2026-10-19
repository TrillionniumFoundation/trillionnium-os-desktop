#!/usr/bin/env python3
"""Bind delivered bytes and verify immutable evidence, history and edit scope."""

import argparse
import hashlib
import json
import re
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path


BASE = "0c2bf0fc1ba473325a0266c7bd476b1ddbf66383"
HISTORY_BASE = "e15ae6a63edb5d4e7c475a001be82111d451b653"
PREFIX = "results/integration/2026-10-19-g1-owner/"
ARCHIVES = {
    "g1-evidence": (10602828, "6a20eefe453be83e04ad74ac99e79206d20034025c30a743f9a95ce2e6b370fd"),
    "hepta-security": (2752828, "8f46f3080bd9645a57ed44c8910c616b9035d4ddaf84e6cd6fb3d4bd7e1311ac"),
    "hepta-bazel-followup": (969644, "d53aaa52bbf7a905ecfc83caa81a1a623bdfaccbed3fa3b7c2fa077588e96cdb"),
}
FROZEN_CI = {
    "g1-remote-ci-f744": ("f744-frozen-files.json", "fd7272ea240c83d695e6e11c2d2561ebcddf3dd6183535b6381085d806654cd8"),
    "g1-remote-ci-463f": ("463f-frozen-files.json", "8c76942b1be82321eb5cb3098b2139c83da48d2d9b32e57ad1cb42f30f15db3d"),
    "g1-remote-ci-107afb": ("107afb-frozen-files.json", "79bfaf1b4844242cc1f8becf0770ceed9d517650481dd8f23d6f85de0a3c7731"),
    "g1-remote-ci-1c054": ("1c054-frozen-files.json", "21b8d2f289502883cba16148d6876a74cf5d235428baa7a19e90e3963875bdc7"),
}
FROZEN_HEPTA_FINAL = {
    "hepta-fleet-main-remote-ci": "725dbd1dfb34d15dc09bec1074226a51891ec685f5653c8f7ee80add94b3c6c7",
    "hepta-scoped-ci-storage-fix": "56309b0d5e96c23540d4da7a5dd1d90937a1674d597993ac53e68ee01be64a46",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_record(repo, path):
    absolute = repo / path
    assert absolute.is_file() and not absolute.is_symlink(), path
    data = absolute.read_bytes()
    mode = "100755" if absolute.stat().st_mode & 0o111 else "100644"
    return {"path": path, "mode": mode, "bytes": len(data), "sha256": sha(data)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source-head", required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    root = repo / PREFIX

    def git(*argv):
        return subprocess.check_output(["git", *argv], cwd=repo)

    def read_object(path):
        return git("show", BASE + ":" + path)

    tracked_diff = git("diff", "--name-only", args.source_head, "--").decode().splitlines()
    allowed = {"docs/INDEX.md", "docs/STATUS.md"}
    assert all(path in allowed or path.startswith(PREFIX) for path in tracked_diff), tracked_diff
    preservation = json.loads((root / "review/whitespace-preservation.json").read_text())
    preserved_raw_paths = set()
    for entry in preservation["explicit_preserved_raw_paths"]:
        observed = file_record(repo, entry["path"])
        assert all(observed[key] == entry[key] for key in ["mode", "bytes", "sha256"])
        preserved_raw_paths.add(entry["path"])
    assert len(preserved_raw_paths) == 31 and preservation["original_diagnostic_path_count"] == 30
    extra_preservation = json.loads((root / "review/main-sync-whitespace-preservation.json").read_text())
    extra_manifest_path = root / extra_preservation["new_frozen_manifest"]
    extra_manifest_bytes = extra_manifest_path.read_bytes()
    assert sha(extra_manifest_bytes) == extra_preservation["new_frozen_manifest_sha256"] == "4aaf2c08953ba239bc071d04ea3877721965a6fd75eee7dc6c3d1af6776c9312"
    extra_entries = {PREFIX + extra_manifest_path.parent.relative_to(root).as_posix() + "/" + entry["path"]: entry for entry in json.loads(extra_manifest_bytes)["files"]}
    assert len(extra_preservation["explicit_preserved_raw_paths"]) == 8
    for entry in extra_preservation["explicit_preserved_raw_paths"]:
        observed = file_record(repo, entry["path"])
        assert all(observed[key] == entry[key] for key in ["mode", "bytes", "sha256"])
        assert all(extra_entries[entry["path"]][key] == entry[key] for key in ["bytes", "sha256"])
        assert entry["path"] not in preserved_raw_paths
        preserved_raw_paths.add(entry["path"])
    assert len(preserved_raw_paths) == 39
    format_paths = sorted(set(tracked_diff) - preserved_raw_paths)
    assert format_paths
    whitespace = subprocess.run(["git", "diff", "--check", args.source_head, "--", *format_paths], cwd=repo, capture_output=True, text=True)
    assert whitespace.returncode == 0, "Whitespace failed outside explicitly SHA-bound raw evidence paths"
    assert (repo / "README.md").read_bytes() == b"" == read_object("README.md")

    old_status = git("show", HISTORY_BASE + ":docs/STATUS.md")
    status = (repo / "docs/STATUS.md").read_bytes()
    title = "# 当前状态\n\n".encode()
    assert old_status.startswith(title)
    historical = old_status[len(title):]
    assert status.endswith(historical)
    old_index = git("show", HISTORY_BASE + ":docs/INDEX.md").decode()
    current_index = (repo / "docs/INDEX.md").read_text()
    index_targets = lambda value: set(re.findall(r"\[[^\]]*\]\(([^)]+)\)", value))
    incoming_targets = index_targets(old_index)
    current_targets = index_targets(current_index)
    assert not incoming_targets - current_targets, sorted(incoming_targets - current_targets)
    current_main_index = git("show", args.source_head + ":docs/INDEX.md").decode()
    current_main_targets = index_targets(current_main_index)
    assert not current_main_targets - current_targets, sorted(current_main_targets - current_targets)

    old_prefixes = ["results/integration/2026-10-18-objective-history", "results/integration/2026-10-18-objective-history-ci"]
    retained = []
    for entry in git("ls-tree", "-rz", BASE, "--", *old_prefixes).split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        path = name.decode()
        assert kind == "blob" and mode in {"100644", "100755"}, path
        record = file_record(repo, path)
        data = (repo / path).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        assert record["mode"] == mode and blob == oid, path
        retained.append({**record, "git_blob": oid})

    transport = json.loads((root / "publication-transport.json").read_text())
    g1_transport = transport["g1_archive"]
    assert g1_transport["body_in_published_Git_tree"] is False
    omitted_archive_paths = {g1_transport["path_after_restoration"]}
    assert omitted_archive_paths == {"g1-evidence/raw-evidence.tar.xz"}
    for item in transport["unchanged_internal_manifests"]:
        observed = file_record(repo, PREFIX + item["path"])
        assert observed["bytes"] == item["bytes"] and observed["sha256"] == item["sha256"]
    package_checks = []
    for package, expected in ARCHIVES.items():
        archive_path = PREFIX + package + "/raw-evidence.tar.xz"
        if package + "/raw-evidence.tar.xz" in omitted_archive_paths:
            assert g1_transport["bytes"] == expected[0] and g1_transport["sha256"] == expected[1]
            archive = {"path": archive_path, "mode": "100644", "bytes": expected[0], "sha256": expected[1], "resolution": "restore_from_verified_parts_body_not_in_Git"}
        else:
            archive = file_record(repo, archive_path)
        assert (archive["bytes"], archive["sha256"]) == expected
        artifact = json.loads((root / package / "artifact-manifest.json").read_text())
        assert artifact["archive"]["bytes"] == expected[0] and artifact["archive"]["sha256"] == expected[1]
        manifest = file_record(repo, PREFIX + package + "/files-manifest.json")
        assert manifest["bytes"] == artifact["files_manifest"]["bytes"]
        assert manifest["sha256"] == artifact["files_manifest"]["sha256"]
        primary = artifact["primary_copies"]
        for item in primary:
            observed = file_record(repo, PREFIX + package + "/" + item["path"])
            assert observed["bytes"] == item["bytes"] and observed["sha256"] == item["sha256"]
        package_checks.append({"package": package, "archive": archive, "files_manifest": manifest, "primary_copies_rechecked": len(primary), "previous_complete_member_verification_retained": True, "archive_recompressed": False})

    parts = json.loads((root / "archive-parts.json").read_text())
    archived_paths = set()
    for archive in parts["archives"]:
        expected = ARCHIVES[archive["path"].split("/", 1)[0]]
        assert (archive["bytes"], archive["sha256"]) == expected
        hasher = hashlib.sha256()
        length = 0
        assert [item["index"] for item in archive["parts"]] == list(range(len(archive["parts"])))
        for item in archive["parts"]:
            copied = (root / item["path"]).read_bytes()
            assert len(copied) == item["bytes"] <= parts["part_bytes"]
            assert sha(copied) == item["sha256"]
            hasher.update(copied)
            length += len(copied)
        assert (length, hasher.hexdigest()) == expected
        archived_paths.add(archive["path"])

    # Preserve every independently frozen CI file, representing only the
    # original large A06 ZIP with its byte-exact parts in the Git tree.
    ci_checks = []
    ci_part_count = 0
    observed_omitted_copies = []
    for package, (manifest_name, expected_manifest_sha) in FROZEN_CI.items():
        directory = root / package
        frozen_bytes = (directory / manifest_name).read_bytes()
        assert sha(frozen_bytes) == expected_manifest_sha
        frozen = json.loads(frozen_bytes)
        ci_transport = json.loads((directory / "publication-transport.json").read_text())
        original = ci_transport["original_archive"]
        original_name = package + "/" + original["path"]
        assert not ci_transport["original_archive_body_in_git_delivery"]
        assert ci_transport["original_frozen_manifest_unchanged"]
        assert ci_transport["original_restored_bytes_equal"]
        assert ci_transport["all_zip_members_independently_verified_before_and_after_restore"]["all_member_size_sha256_crc32_verified"]
        omitted_archive_paths.add(original_name)
        for entry in frozen["files"]:
            if entry["path"] == original["path"]:
                assert entry == original
            else:
                observed = file_record(repo, PREFIX + package + "/" + entry["path"])
                assert observed["bytes"] == entry["bytes"] and observed["sha256"] == entry["sha256"]
        ci_parts = json.loads((directory / "archive-parts.json").read_text())
        assert len(ci_parts["archives"]) == 1
        entry = ci_parts["archives"][0]
        assert all(entry[key] == original[key] for key in ["path", "bytes", "sha256"])
        hasher = hashlib.sha256()
        length = 0
        assert [item["index"] for item in entry["parts"]] == list(range(len(entry["parts"])))
        for item in entry["parts"]:
            data = (directory / item["path"]).read_bytes()
            assert len(data) == item["bytes"] <= ci_parts["part_bytes"]
            assert sha(data) == item["sha256"]
            hasher.update(data)
            length += len(data)
        assert length == original["bytes"] and hasher.hexdigest() == original["sha256"]
        ci_part_count += len(entry["parts"])
        ci_checks.append({"package": package, "original_frozen_manifest_sha256": expected_manifest_sha, "original_files_including_manifest": len(frozen["files"]) + 1, "original_archive": original, "parts_checked": len(entry["parts"]), "all_selected_original_bytes_preserved": True, "actual_restoration_receipt": package + "/publication-transport.json"})

    additional_packages = []
    for package, expected_sha in [("hepta-fleet-fixture-fix", "c42b3bc1774bd150d15ea563ce8fc088dd47c23cf0b1919350d912fa495c4232"), ("hepta-fleet-fixture-main-fix", "679cc06b07a26e9783ac5fde2d711383fe356763c4d6e1dac73390053d4ba868")]:
        data = (root / package / "files-manifest.json").read_bytes()
        assert sha(data) == expected_sha
        frozen = json.loads(data)
        for entry in frozen["files"]:
            observed = file_record(repo, PREFIX + package + "/" + entry["path"])
            assert observed["bytes"] == entry["bytes"] and observed["sha256"] == entry["sha256"]
        additional_packages.append({"package": package, "original_files": len(frozen["files"]) + 1, "manifest_sha256": expected_sha, "all_original_bytes_rechecked": True})
    host = root / "g1-ci-host-correction"
    assert sha((host / "artifact-manifest.json").read_bytes()) == "cc22d23e26c62986fc7b6067f029564a01602ce8669e8feb045e765c4abf2f25"
    host_artifact = json.loads((host / "artifact-manifest.json").read_text())
    for entry in [host_artifact["archive"], *host_artifact["primary_copies"]]:
        observed = file_record(repo, PREFIX + "g1-ci-host-correction/" + entry["path"])
        assert observed["bytes"] == entry["bytes"] and observed["sha256"] == entry["sha256"]
    additional_packages.append({"package": "g1-ci-host-correction", "all_primary_and_archive_bytes_rechecked": True, "raw_regular_members_verified_in_copy_receipt": 106})
    for package, expected_manifest_sha in FROZEN_HEPTA_FINAL.items():
        directory = root / package
        artifact_bytes = (directory / "artifact-manifest.json").read_bytes()
        assert sha(artifact_bytes) == expected_manifest_sha
        artifact = json.loads(artifact_bytes)
        for entry in artifact["files"]:
            observed = file_record(repo, PREFIX + package + "/" + entry["path"])
            assert observed["bytes"] == entry["bytes"] and observed["sha256"] == entry["sha256"]
        raw_bytes = (directory / "files-manifest.json").read_bytes()
        assert sha(raw_bytes) == artifact["raw_manifest"]["sha256"]
        raw_manifest = json.loads(raw_bytes)
        expected = {entry["path"]: entry for entry in raw_manifest["files"]}
        assert len(expected) == len(raw_manifest["files"])
        assert sum(entry["bytes"] for entry in expected.values()) == raw_manifest["bytes"]
        expected["files-manifest.json"] = {"path": "files-manifest.json", "bytes": len(raw_bytes), "sha256": sha(raw_bytes)}
        member_records = []
        with tarfile.open(directory / "raw-evidence.tar.xz", "r:xz") as archive:
            members = archive.getmembers()
            assert [entry.name for entry in members] == sorted(expected)
            assert len(members) == artifact["raw_member_count"]
            for member in members:
                assert member.isfile() and not member.issym() and not member.islnk()
                data = archive.extractfile(member).read()
                assert len(data) == expected[member.name]["bytes"] and sha(data) == expected[member.name]["sha256"]
                if member.name in artifact["primary_files"]:
                    assert data == (directory / member.name).read_bytes()
                member_records.append(expected[member.name])
        additional_packages.append({"package": package, "manifest_sha256": expected_manifest_sha, "original_files_including_manifest": len(artifact["files"]) + 1, "all_original_files_rechecked": True, "all_archive_members_verified_in_order_with_size_sha256": True, "primary_bytes_equal_archive_members": True, "raw_regular_members": member_records})

    for package, manifest_name, expected_manifest_sha in [
        ("hepta-final-status", "files-manifest.json", "95febb0d3b2ce57227c7b25bda0ff75e26f0a53a03ebbbc7af177fc9922bb448"),
        ("source-publication/report-main-sync/independent-pr198", "pr198-text-review-frozen-02.json", "4aaf2c08953ba239bc071d04ea3877721965a6fd75eee7dc6c3d1af6776c9312"),
    ]:
        directory = root / package
        original_bytes = (directory / manifest_name).read_bytes()
        assert sha(original_bytes) == expected_manifest_sha
        original = json.loads(original_bytes)
        for entry in original["files"]:
            actual = file_record(repo, PREFIX + package + "/" + entry["path"])
            assert actual["bytes"] == entry["bytes"] and actual["sha256"] == entry["sha256"]
        additional_packages.append({"package": package, "manifest": manifest_name, "manifest_sha256": expected_manifest_sha, "original_files_including_manifest": len(original["files"]) + 1, "all_original_selected_text_bytes_rechecked": True, "binary_archive_added": False})
    copies = json.loads((root / "review/report-main-sync-fixed-inputs-copy.json").read_text())
    for entry in copies["files"]:
        actual = file_record(repo, PREFIX + entry["path"])
        assert actual["bytes"] == entry["bytes"] and actual["sha256"] == entry["sha256"]
    inherited = json.loads((root / "review/main-sync-entry-preservation.json").read_text())
    assert inherited["old_entries"] == 405 and inherited["status"] == "passed_405_old_entries_preserved_or_explicitly_upgraded"
    for entry in inherited["records"]:
        actual = file_record(repo, entry["path"])
        if entry["path"] == PREFIX + "review/delivery-links.json":
            assert entry["after"]["byte_binding"] == "final_delivery_manifest_entry"
            assert actual["mode"] == entry["after"]["mode"] and actual["sha256"] != entry["before"]["sha256"]
            link_review = json.loads((repo / entry["path"]).read_text())
            assert link_review["fixed_product_source"] == args.source_head
            assert link_review["status"] == "passed_explicit_target_and_archive_resolution"
        else:
            assert all(actual[key] == entry["after"][key] for key in ["path", "mode", "bytes", "sha256"])

    # A later tool boundary may reveal a local copy again. It is explicitly
    # outside this publication selection; no ignore rule or repeated deletion
    # hides it, and the later index/tree gate must exclude all these paths.
    for name in sorted(omitted_archive_paths):
        path = root / name
        if path.exists():
            observed_omitted_copies.append(file_record(repo, PREFIX + name))

    excluded = {PREFIX + "delivery-manifest.json", PREFIX + "review/final-delivery-review.json"}
    paths = sorted(allowed | {path.relative_to(repo).as_posix() for path in root.rglob("*") if path.is_file()})
    entries = [file_record(repo, path) for path in paths if path not in excluded and path.removeprefix(PREFIX) not in omitted_archive_paths]
    oversized = [record for record in entries if record["bytes"] > parts["part_bytes"]]
    assert {record["path"].removeprefix(PREFIX) for record in oversized} == archived_paths - omitted_archive_paths
    source_tree = git("rev-parse", args.source_head + "^{tree}").decode().strip()
    manifest_data = {
        "schema": "r10.delivery-byte-manifest.v1",
        "base_commit": args.source_head,
        "initial_historical_base": BASE,
        "incoming_main_history_base": HISTORY_BASE,
        "fixed_local_product_source": args.source_head,
        "fixed_local_product_tree": source_tree,
        "scope": {"repository_relative_paths": True, "edited_tracked_documents": sorted(allowed), "new_results_prefix": PREFIX, "files_in_manifest": len(entries), "total_bytes_in_manifest": sum(entry["bytes"] for entry in entries)},
        "parts_only_archive_publication": {"manifest": "publication-transport.json", "ci_manifests": [package + "/publication-transport.json" for package in FROZEN_CI], "body_omitted_from_Git": sorted(omitted_archive_paths), "meaning": "G1 original tar and four original A06 ZIPs are restored byte-for-byte from the selected parts. Original producer manifests remain unchanged. Local physical reappearance of an excluded original copy does not alter the explicit Git index/tree selection."},
        "self_reference_rule": {"excluded": sorted(excluded), "meaning": "The manifest cannot hash itself; the final review hashes this manifest. Both terminal files are bound by the eventual Git commit. All other delivered results and the two edited documents are included."},
        "entries": entries,
        "remote_publication_scope": "Remote source/head, CI and merge observations are retained in separate evidence and described with their own timestamps. This manifest does not infer merge or runtime qualification from publication.",
    }
    manifest_path = root / "delivery-manifest.json"
    manifest_path.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2) + "\n")
    for entry in entries:
        assert file_record(repo, entry["path"]) == entry, entry["path"]
    receipt = {
        "schema": "r10.final-delivery-review.v1",
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_commit": args.source_head,
        "initial_historical_base": BASE,
        "incoming_main_history_base": HISTORY_BASE,
        "fixed_local_product_source": args.source_head,
        "fixed_local_product_tree": source_tree,
        "tracked_diff_paths_within_authorized_scope": True,
        "git_diff_check_returncode": whitespace.returncode,
        "git_diff_check_scope": "All changed tracked paths except the original31 and separately frozen8 exact SHA-bound raw/API files; every selected byte and mode remains checked. The current main is the diff baseline and no product gate is altered.",
        "whitespace_preservation_receipt": "review/whitespace-preservation.json",
        "initial_unfiltered_whitespace_failure_preserved": True,
        "additional_exact_whitespace_preservation_receipt": "review/main-sync-whitespace-preservation.json",
        "explicit_preserved_raw_format_paths": len(preserved_raw_paths),
        "root_README_bytes": 0,
        "historical_STATUS_suffix_bytes": len(historical),
        "historical_STATUS_suffix_sha256": sha(historical),
        "historical_STATUS_suffix_unchanged": True,
        "incoming_INDEX_distinct_link_targets": len(incoming_targets),
        "incoming_INDEX_all_targets_retained": True,
        "incoming_INDEX_targets": sorted(incoming_targets),
        "current_INDEX_distinct_link_targets": len(current_targets),
        "current_main_INDEX_distinct_link_targets": len(current_main_targets),
        "current_main_INDEX_all_targets_retained": True,
        "current_main_INDEX_targets": sorted(current_main_targets),
        "pre_sync_405_entries_preserved_or_explicitly_upgraded": {"receipt": "review/main-sync-entry-preservation.json", "unchanged_entries": inherited["unchanged_entries"], "explicitly_upgraded_entries": inherited["explicitly_upgraded_entries"], "old_QA_not_relabelled_for_this_tree": True},
        "R9_paths_checked": old_prefixes,
        "R9_retained_files_checked_against_original_Git_blob_and_mode": len(retained),
        "R9_retained_files": retained,
        "frozen_packages": package_checks,
        "additional_original_packages": additional_packages,
        "frozen_CI_packages": ci_checks,
        "later_visible_omitted_local_copies_not_selected": observed_omitted_copies,
        "archive_parts": {"archive_count": len(parts["archives"]) + len(FROZEN_CI), "part_count": sum(len(archive["parts"]) for archive in parts["archives"]) + ci_part_count, "all_part_and_original_identities_rechecked": True, "all_blobs_over_1_5_MiB_have_parts": True, "body_omitted_from_Git": sorted(omitted_archive_paths), "actual_roundtrip_receipt": "review/published-transport-roundtrip.json", "earlier_pre_publication_roundtrip": "review/archive-restoration-review.json", "ci_actual_roundtrips": [package + "/publication-transport.json" for package in FROZEN_CI]},
        "delivery_manifest": file_record(repo, PREFIX + "delivery-manifest.json"),
        "manifest_file_count": len(entries),
        "all_manifest_source_files_unchanged_during_review": True,
        "cargo_invocations": 0,
        "qemu_invocations": 0,
        "new_product_test_runs": 0,
        "status": "passed_byte_preservation_scope_and_transport_review",
    }
    (root / "review/final-delivery-review.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "files_in_manifest": len(entries), "R9_files_unchanged": len(retained), "packages": len(package_checks), "archive_parts": receipt["archive_parts"], "manifest": receipt["delivery_manifest"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
