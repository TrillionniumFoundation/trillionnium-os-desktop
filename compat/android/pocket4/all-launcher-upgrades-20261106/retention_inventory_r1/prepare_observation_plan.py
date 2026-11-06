#!/usr/bin/env python3
"""Produce a review-only storage/dependency observation plan from local evidence.

This program never opens a Pocket4 path. It does not produce an executable
device packet, grant cleanup authority, or alter an existing receipt.
"""
import sys
sys.dont_write_bytecode = True
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
CATALOG_SHA = "6ba1391d24c056301612eb9d5fbc2ff5185c65a163dad79358d0fdcd402ac842"
GUARD = {
    "path": "/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/current_baseline_guard.py",
    "bytes": 3213,
    "sha256": "d84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3",
}
STAT_FIELDS = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
CGROUP_PATHS = {
    "/system.slice/droidloomd.service",
    "/user.slice/user-1000.slice/user@1000.service/app.slice/droidloom.service",
}
BUILDER_ROOTS = (
    "/home/alex/work/pocket4-native-typed-ingress-builder468-provider-closure-compile-03-20261106",
    "/home/alex/work/pocket4-native-typed-ingress-builder469-native-provider-compile-01-20261106",
    "/home/alex/work/pocket4-native-typed-ingress-builder470-systemui-provider-compile-02-20261106",
)
WORK = "/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-work-01-20261105"
BUILD08 = "/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-systemui-provider-build-08-20261106"
EXTRA_INPUTS = (
    "recovery/SOURCE_PINS.json",
    "recovery/successor_runtime.py",
    "recovery/independent_repair_r2/actual-execute-01/current_baseline_guard.py",
)


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def read_local(path):
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    need(all(getattr(before, k) == getattr(after, k) for k in STAT_FIELDS), "LOCAL_INPUT_CHANGED")
    need(len(raw) == before.st_size <= 2 * 1024 * 1024, "LOCAL_INPUT_SIZE_BOUND")
    return raw


def write_new(name, value):
    raw = canonical(value)
    with (HERE / name).open("xb") as stream:
        stream.write(raw)
    need((HERE / name).read_bytes() == raw, "NEW_LOCAL_PLAN_READBACK")
    return {"file": name, "bytes": len(raw), "sha256": sha(raw)}


def main():
    raw = read_local(HERE / "PATH_CATALOG.json")
    need(sha(raw) == CATALOG_SHA, "EXACT_LOCAL_CATALOG")
    catalog = json.loads(raw)
    closure = {"PATH_CATALOG.json": {"bytes": len(raw), "sha256": sha(raw)}}
    for sid, item in catalog["source_files"].items():
        data = read_local(PROJECT / item["file"])
        need(len(data) == item["bytes"] and sha(data) == item["sha256"], "CATALOG_SOURCE_CHANGED_" + sid)
        closure[item["file"]] = {"bytes": len(data), "sha256": sha(data), "source_id": sid}
    for relative in EXTRA_INPUTS:
        data = read_local(PROJECT / relative)
        closure[relative] = {"bytes": len(data), "sha256": sha(data)}
    guard_raw = read_local(PROJECT / EXTRA_INPUTS[-1])
    need(len(guard_raw) == GUARD["bytes"] and sha(guard_raw) == GUARD["sha256"], "EXACT_GUARD_SOURCE_REFERENCE")
    core = read_local(PROJECT / "recovery/successor_runtime.py")
    need(b'ENGINE = "/system/lib64/libberberis_arm64.so"' in core, "ENGINE_PATH_MUST_BE_AN_EXISTING_SOURCE_LITERAL")

    references = []
    host, android, cgroup = [], [], []
    for entry in catalog["entries"]:
        item = {"catalog_id": entry["id"], "path": entry["path"], "categories": entry["categories"],
                "source_references": [{k: row[k] for k in ("source_id", "json_pointer")} for row in entry["evidence"]],
                "current_existence_observed": False, "deletion_eligible": False}
        if entry["path"] in CGROUP_PATHS:
            item.update(coordinate="cgroup_membership_reference_not_filesystem_path", observation="NO_FILESYSTEM_TRAVERSAL")
            cgroup.append(item)
        elif entry["path"] == "/init" or entry["coordinate"] == "android_init_root":
            item.update(coordinate="held_android_init_root", observation="EXACT_METADATA_ONLY_NO_DATA_TRAVERSAL")
            android.append(item)
        else:
            item.update(coordinate="host", observation="EXACT_METADATA_ONLY_NO_IMPLIED_PARENT_RECURSION")
            host.append(item)
        references.append(item)
    need(len(cgroup) == 2 and len(host) == 488 and len(android) == 305, "EXACT_TYPED_REFERENCE_COUNTS")
    typed_pin = write_new("TYPED_REFERENCES.json", {
        "schema": "pocket4-retention-typed-local-references-v1", "catalog": closure["PATH_CATALOG.json"],
        "entries": references, "host_filesystem_references": len(host), "Android_filesystem_references": len(android),
        "nonfilesystem_cgroup_references": len(cgroup), "literal_reference_count": len(references),
        "corrections": [
            "The two ControlGroup values are cgroup membership addresses, not host filesystem scan targets.",
            "/init is the Android init argv path in the held Android root, not host /init.",
            "Source literals and plan references do not establish present existence or absence.",
        ], "target_reads": 0, "deletions": 0})

    all_paths = {row["path"] for row in references}
    previous_parents = sorted({str(Path(item["path"]).parent) for item in catalog["retained_previous_APKs"]})
    roots = []
    def root(path, role, basis, budget, existence):
        need(any(p == path or p.startswith(path + "/") for p in all_paths), "ROOT_WITHOUT_LOCAL_PATH_EVIDENCE")
        need(not path.startswith("/home/alex/Documents/") and path != "/home/alex/work", "OTHER_PROJECT_OR_BROAD_ROOT_REJECTED")
        roots.append({"path": path, "role": role, "basis": basis, "maximum_entries": budget,
            "maximum_depth": 32, "nofollow": True, "cross_mounts": False, "file_content_reads": False,
            "historical_existence_basis": existence, "fresh_existence_required": True,
            "root_or_parent_ownership_does_not_prove_unused": True, "cleanup_eligible": False})
    for path in previous_parents:
        root(path, "retained_upgrade_transaction", "Parent of an exact retained previous APK in a successful original install receipt.",
             4096, "actual_retained_file_receipt; fresh parent identity still required")
    for path in BUILDER_ROOTS:
        root(path, "current_builder_or_inherited_qualification_dependencies", "Exact original authority/source/binary references in current470 qualification.",
             30000, "actual authority observations inside this root; whole tree is not proved")
    root(WORK, "shared_framework_source_and_inputs", "Exact work path in build08 plan plus retained actual preparation/contract references.",
         40000, "plan and preparation context; no blanket tree existence inference")
    root(BUILD08, "failed_build_resource_gate_evidence", "Exact build08 root from plan and actual failed outer fence; compiler was not called.",
         4096, "read-only existence probe; android-out is not assumed to exist")
    need(len(roots) == 16, "EXACT_REVIEWED_TREE_ROOT_COUNT")
    root_pin = write_new("TREE_SCOPES.review-only.json", {
        "schema": "pocket4-bounded-storage-tree-scopes-review-only-v1", "roots": roots,
        "runtime_admission": False, "recursive_deletion_authority": False,
        "all_roots_are_fixed_from_evidence_not_prefix_discovery": True,
        "sum_per_root_caps_is_not_global_budget": True, "global_entry_limit": 100000,
        "global_tree_walk_seconds": 90, "unknown_or_unstable_subtree_status": "INCOMPLETE_NO_RECLAIM_ESTIMATE"})

    protected = {
        "schema": "pocket4-retention-dependency-protection-v1",
        "current_reference_epoch": catalog["runtime_reference"]["runtime_epoch_sha256"],
        "scope47_is_an_explicit_historical_subset_not_current_exhaustive_scope": True,
        "current_observed_new_component_pending_identity": catalog["installed_protected_reference"]["new_component_identity_pending"],
        "protected_rule": "Any exact active, input, source, receipt, lock, data, layout or reproduction reference is retained until a newly qualified final closure removes its dependency.",
        "retained_previous_APKs": catalog["retained_previous_APKs"],
        "retained_previous_APK_recorded_logical_bytes": catalog["retained_previous_APK_recorded_logical_bytes"],
        "these_bytes_are_not_current_disk_usage_or_reclaimable_space": True,
        "external_JDK_exact_files": catalog["other_project_exact_JDK_dependencies"],
        "external_JDK_parent_recursion_or_cleanup_allowed": False,
        "current_builder_roots_and_inherited_roots": list(BUILDER_ROOTS),
        "source_contract_dependencies": [row["catalog_id"] for row in references if any(c in row["categories"] for c in (
            "CURRENT_QA_SOURCE_CONTRACT_REFERENCE", "PINNED_QA_EVIDENCE_DEPENDENCY"))],
        "official_aapt2_controlled_layout": "/var/lib/pocket4-official-aapt2-host-tool-proof-20261106-r3",
        "official_aapt2_layout_rule": "Keep the exact binary, all bound directories including empty lib64 directories, system dependency pins, original JAR and observed proof. Do not move, relink, patchelf, or rewrite LD paths.",
        "Android_PM_managed_paths_rule": "Installed and historical /data/app paths are not manual-delete targets. CE/DE data roots are protected without recursive content observation.",
        "production_regression_required_per_app": ["start", "login_or_authorized_guest", "core_operation", "network", "storage", "current_permissions_and_denial_recovery", "long_running", "normal_restart", "fault_recovery"],
        "qualification_does_not_follow_from_APK_or_install_audit": True,
        "deletion_eligible_entries": 0, "reclaimable_bytes": None,
    }
    protection_pin = write_new("DEPENDENCY_PROTECTION.json", protected)

    plan = {
        "schema": "pocket4-bounded-storage-dependency-observation-plan-v1",
        "state": "LOCAL_REVIEW_ONLY_NO_HOST_SOURCE_OR_PROCESS_PACKET_SUBMITTED",
        "target": "pocket4", "purpose": "Measure only the known task's metadata and dependency references before any later cleanup decision.",
        "catalog": {"file": "PATH_CATALOG.json", **closure["PATH_CATALOG.json"]},
        "typed_references": typed_pin, "tree_scopes": root_pin, "dependency_protection": protection_pin,
        "runtime_reference": {"guard": GUARD, "runtime_epoch_sha256": catalog["runtime_reference"]["runtime_epoch_sha256"],
            "framework_epoch_sha256": catalog["runtime_reference"]["framework_epoch_sha256"],
            "role_source": {"file": catalog["source_files"]["baseline"]["file"], "pointer": "/runtime/held/extra"},
            "initial_pid_reference": 3268779, "initial_start_reference": "99615082", "numeric_PID_is_not_authority": True,
            "old_scope47_may_not_be_admitted_as_complete_current_set": True},
        "before_remote_submission": [
            "Root reviews the exact new host-only source and process packet; this JSON itself is not executable authority.",
            "Root chooses a quiet observation window; existing Main, install, UI and lifecycle owners are not interrupted.",
            "Use the current typed guard and fixed original core/source pins with the already-proved owned FFI lifetime wrapper. Do not modify frozen code or a Beike two-package flow.",
            "Actual new component discovery remains separate. Its absence from reference47 never authorizes deletion or an exhaustive-scope claim.",
        ],
        "phases": [
            {"name": "fresh_identity", "operations": ["Acquire the existing action coordinator lease without creating or replacing its lock.",
                "Hold all eight current role proc handles and pidfds; compare start/boot/root/namespaces/executable identities to the typed baseline before and after.",
                "Open current runtime binaries and cell config by exact source-established paths; verify their existing expected stat/hash contracts. Read no process environment or business files."]},
            {"name": "mount_and_backing_relationships", "operations": [
                "Read bounded host and held-init mountinfo by held proc handles, and maps/fdinfo metadata for the eight held roles only. Namespace entries and Android commands remain zero.",
                "Record mount id, parent id, major:minor, root, mountpoint, filesystem type and source. Overlay lower/upper/work and loop backing paths are only literal observations, never automatically traversed.",
                "Associate exact allowed file dev/inode/mount-id with these maps. An external or unknown image path is reported as a protected unresolved dependency for separate review.",
                "Current rootfs/image backing paths and reDroid container IDs are not presently evidenced. No docker/podman/container runtime enumeration, socket use, or store traversal is included."]},
            {"name": "exact_metadata", "operations": [
                "For 488 host references and 305 Android-root references, only open/lstat the exact reviewed paths through held nofollow parents. Missing paths are recorded as ENOENT, not inferred to be deleted by this task.",
                "For the nine JDK dependencies in another project, inspect only those exact files and necessary parent identity components; no parent listing or recursive scan.",
                "For each allowed object record full stat, allocated blocks, mount id and stable before/after identity. Do not dereference an unreviewed symlink target.",
                "Inspect CE/DE top-level directory identity only. No account, credential, database, cache, external app storage or business-content walk."]},
            {"name": "bounded_known_tree_sizes", "operations": [
                "Walk only the 16 listed task roots, by directory FD, without following symlinks or crossing a mount boundary. No broad /home/alex/work, /opt or /var/lib discovery.",
                "Count entries and unique (device,inode) allocation observations; stable directory checks surround each traversal. Cap exhaustion, directory mutation, inaccessible entries or unexpected mounts mark that root INCOMPLETE.",
                "Only metadata is read. Do not hash arbitrary large build/APK content just to calculate space. Partial totals are lower bounds, never estimates of safely reclaimable bytes."]},
            {"name": "dependency_reconciliation", "operations": [
                "Match observed hardlink aliases by actual filesystem dev/inode and known mount correspondence. st_nlink greater than observed aliases means outside links are unresolved.",
                "Report st_size and st_blocks*512 separately. Reflinks, filesystem compression, snapshots and open deleted files prevent a simple sum from becoming a reclaim estimate.",
                "The eight-role FD/map sample is a positive-use proof only; it cannot prove absence of references in every app, other process or external project.",
                "Preserve every active-source/contract/tool dependency. No observation outcome in this plan sets deletion_eligible=true."]},
            {"name": "complete_close", "operations": [
                "Recheck original runtime, paths and directory identities; release every owned FD and existing action lease.",
                "Require original descriptor identity restoration, normal owned child/pidfd exit, full EOF capture and authoritative durable terminal for a complete observation.",
                "An unknown or failed observation is preserved without auto retry; it does not release any cleanup hold."]},
        ],
        "resource_bounds": {"outer_seconds": 240, "inner_seconds": 180, "tree_walk_seconds": 90,
            "tree_entries_total": 100000, "tree_depth": 32, "mountinfo_bytes_each": 2097152,
            "maps_bytes_each_of_eight_roles": 4194304, "FD_entries_each_of_eight_roles": 4096,
            "new_small_dependency_content_hash_bytes_total": 16777216,
            "existing_typed_guard_hash_limits_remain_unchanged": True,
            "raw_artifact_bytes": 33554432, "public_summary_bytes": 524288,
            "CPUQuota_percent": 25, "MemoryMax_bytes": 536870912, "nice": 10,
            "any_bound_exceeded": "INCOMPLETE_WITH_EXACT_REASON_NO_CLEANUP_QUALIFICATION"},
        "private_output": "New root-owned 0700 observation directory with O_EXCL/nofollow files; any unfiltered maps/mount records stay out of Git. Public output is fixed-path metadata, hashes, counts and explicit unknowns only.",
        "forbidden_actions": ["delete", "move", "chmod", "chown", "truncate", "unlink", "mount", "namespace_entry", "native_lifecycle", "signal_existing_process", "install", "uninstall", "permission_grant", "UI", "ADB", "container_prune", "write_existing_receipts"],
        "target_reads_already_performed_by_this_plan": 0, "cleanup_eligible_entries": 0,
        "final_portable_closure_prerequisites": [
            "Retain the complete working owned source, exact patches/source/provider locks, dependency manifests, build configuration and actual reproduction commands.",
            "Retain original signed APK sets, verified source/transport receipts and signer/version metadata for final versions; do not re-sign or alter integrity checks.",
            "Retain cell config, wrapper source and activation proof, current framework/engine/presenter/native tool identities, and actual image/mount backing mapping once observed.",
            "Generate and qualify a new final source/config path contract before deleting any directory still referenced by the current 468/469/470, JDK, UI helper or audit contract.",
            "Keep old failed/UNKNOWN records immutable and link later corrective outcomes. Private business/permission evidence remains protected outside the public reproducibility bundle.",
            "Each app must pass its own actual complete production regression; framework packaging/boot/runtime must be proven. Size or version-name evidence cannot substitute for this.",
        ],
    }
    plan_pin = write_new("OBSERVATION_PLAN.review-only.json", plan)
    closure_pin = write_new("INPUT_CLOSURE.json", {"schema": "pocket4-retention-local-input-closure-v1", "files": closure,
        "all_sources_read_from_local_project": True, "all_exact_hashes_revalidated": True,
        "numeric_values_preserved_by_Python": True, "target_reads": 0})
    summary = {"ok": True, "typed_reference_counts": {"host": len(host), "Android": len(android), "cgroup_nonfilesystem": len(cgroup)},
        "bounded_tree_roots_review_only": len(roots), "retained_previous_APKs": len(catalog["retained_previous_APKs"]),
        "recorded_previous_APK_logical_bytes": catalog["retained_previous_APK_recorded_logical_bytes"],
        "reclaimable_bytes": None, "cleanup_eligible": 0, "target_reads": 0,
        "outputs": [typed_pin, root_pin, protection_pin, plan_pin, closure_pin]}
    print(json.dumps(summary, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
