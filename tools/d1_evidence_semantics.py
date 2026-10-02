"""Cross-check carried D1 bytes and producer records; never execute a payload.

The portable packet excludes disk, tar, kernel and initrd payloads. Their
recorded hashes are cross-bound, not recomputed by this reader. Carried JSON,
rootfs manifests and package locks are hashed from the same bytes we inspect.
"""
from __future__ import annotations

import hashlib
from contextlib import ExitStack
import json
import os
from pathlib import Path
import re
from typing import Any

try:
    from .artifact_evidence import open_file, safe_relative, SHA256, MAX_JSON_BYTES
    from .browser_codec_reference_security import load_json_strict
except ImportError:
    from artifact_evidence import open_file, safe_relative, SHA256, MAX_JSON_BYTES
    from browser_codec_reference_security import load_json_strict

STAGES = ("validate_committed_lock", "prepare_exact_inputs", "build_first", "build_second",
          "compare_builds", "qemu_acceptance", "pipeline")
ARTIFACTS = ("package-lock.tsv", "rootfs-content-manifest.json", "rootfs.tar",
             "trillionnium-d1.ext4", "vmlinuz", "initrd.img")
FIXTURE_SEPARATION = {
    "product_default_graph_fixture_free": True, "qualification_feature": "fixture",
    "qualification_binary": "hepta-agent-d1-fixture",
    "qualification_server_exec": "/usr/libexec/hepta-agent-d1-fixture --mode server",
    "product_handler_connected": False, "production_install_map_contains_qualification_binary": False,
}
REPRO_SCOPE = {"same_run_two_build_byte_identity": True, "cross_run_identity_claimed": False,
               "hermetic_host_environment_claimed": False}
ROOTFS_CONSISTENCY = {
    "root": "explicit '.' directory",
    "parents": "every nonroot path has an explicit immediate directory parent",
    "hardlink_head": "self-reference at the byte-lexicographic minimum carried group member",
    "hardlink_group": "all carried members name the same head and have matching inode metadata",
    "hardlink_member_count": "at most declared nlink; links outside the carried root may be absent",
    "symlink_target": "nonempty UTF-8/surrogateescape target bytes match recorded size",
    "actual_rootfs_payload_inspected": False,
    "complete_inode_link_inventory_claimed": False,
}
INVARIANTS = ("image_id", "source_date_epoch", "selection_sha256", "prepared_manifest_sha256",
    "signed_package_set_sha256", "package_lock", "rootfs_manifest", "rootfs_tar", "image", "kernel", "initrd",
    "release_marker_present", "network_during_acceptance")
REQUIRED_PAYLOADS = ("inputs/prepared-inputs.json", "inputs/expected-package-lock.tsv", "evidence/binary-digests.json",
    "evidence/product-cargo-tree.txt", "evidence/qualification-cargo-tree.txt", "raw-evidence/product-daemon.strings",
    "raw-evidence/qualification-fixture.strings", "evidence/product-daemon-self-check-host.json",
    "evidence/d1-qualification-self-check-host.json", "builds/build-a/build-result.json",
    "builds/build-a/rootfs-content-manifest.json", "builds/build-a/package-lock.tsv", "builds/build-b/build-result.json",
    "builds/build-b/rootfs-content-manifest.json", "builds/build-b/package-lock.tsv", "pipeline/pipeline-result.json",
    "reproducibility/reproducibility-result.json", "qemu/boot-result.json", "qemu/acceptance.json")


def same(actual: object, expected: object, label: str) -> None:
    if type(actual) is not type(expected):
        raise ValueError(f"D1 {label}: exact type mismatch")
    if type(expected) is dict:
        if set(actual) != set(expected):
            raise ValueError(f"D1 {label}: closed field set mismatch")
        for key, value in expected.items():
            same(actual[key], value, label + "." + key)
    elif type(expected) is list:
        if len(actual) != len(expected):
            raise ValueError(f"D1 {label}: list length mismatch")
        for left, right in zip(actual, expected):
            same(left, right, label)
    elif actual != expected:
        raise ValueError(f"D1 {label}: value mismatch")


def closed(value: object, keys: set[str], label: str) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise ValueError(f"D1 {label}: closed field set mismatch")
    return value


def integer(value: object, label: str, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= 2**64 - 1:
        raise ValueError(f"D1 {label}: invalid integer")
    return value


def sha(value: object, label: str) -> str:
    if type(value) is not str or SHA256.fullmatch(value) is None:
        raise ValueError(f"D1 {label}: invalid SHA-256")
    return value


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()


def metadata(info: os.stat_result) -> tuple:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


class _Snapshot:
    """Same-FD parse/hash, pinned absolute-path opener, final full readback."""
    def __init__(self, root: Path, outputs: dict):
        self.root, self.outputs = root, outputs
        self.cached: dict[str, tuple[bytes, tuple]] = {}

    def read(self, name: str) -> bytes:
        safe_relative(name)
        path = self.root / name
        with os.fdopen(open_file(path), "rb") as stream:
            before = os.fstat(stream.fileno())
            if before.st_size > MAX_JSON_BYTES:
                raise ValueError("D1 semantic payload exceeds bound")
            data = stream.read(MAX_JSON_BYTES + 1)
            after = os.fstat(stream.fileno())
            named = path.stat(follow_symlinks=False)
            if (len(data) != before.st_size or len(data) > MAX_JSON_BYTES
                    or metadata(before) != metadata(after) or metadata(before) != metadata(named)):
                raise ValueError("D1 semantic payload changed during retained read")
        same(hashlib.sha256(data).hexdigest(), self.outputs.get(name), "semantic output digest " + name)
        snapshot = (data, metadata(before))
        if name in self.cached and self.cached[name] != snapshot:
            raise ValueError("D1 semantic payload changed after its first read")
        self.cached[name] = snapshot
        return data

    def document(self, name: str) -> dict:
        value = load_json_strict(self.read(name).decode("utf-8", "strict"))
        if type(value) is not dict:
            raise ValueError("D1 semantic payload is not an object")
        return value

    def digest(self, name: str) -> str:
        return hashlib.sha256(self.read(name)).hexdigest()

    def finish(self) -> None:
        # Retain every readback FD through the final cross-check. A predecessor
        # changed while a later record is read cannot escape as a stale cache.
        with ExitStack() as stack:
            retained = []
            for name, (expected, identity) in tuple(self.cached.items()):
                path = self.root / name
                stream = stack.enter_context(os.fdopen(open_file(path), "rb"))
                if metadata(os.fstat(stream.fileno())) != identity:
                    raise ValueError("D1 semantic readback identity drift")
                data = stream.read(MAX_JSON_BYTES + 1)
                same(data, expected, "complete semantic payload readback")
                retained.append((path, stream, identity))
            for path, stream, identity in retained:
                if (metadata(os.fstat(stream.fileno())) != identity
                        or metadata(path.stat(follow_symlinks=False)) != identity):
                    raise ValueError("D1 semantic complete readback changed during scan")


def pipeline(document: dict) -> None:
    same(document.get("schema"), "trillionnium.desktop.d1-pipeline-result.v2", "pipeline schema")
    same(document.get("status"), "PASS", "pipeline status")
    same(document.get("failed_stage"), None, "pipeline failed_stage")
    stages = closed(document.get("stages"), set(STAGES), "pipeline stages")
    for name in STAGES:
        same(stages[name], {"exit_code": 0, "status": "PASS"}, "pipeline stage " + name)
    same(document.get("authority"), {key: False for key in (
        "qemu_network_enabled", "release_qualified", "secure_boot_qualified", "servo_started", "visible_window_created")},
        "pipeline authority")
    started = integer(document.get("started_unix"), "pipeline started_unix")
    finished = integer(document.get("finished_unix"), "pipeline finished_unix")
    if finished < started:
        raise ValueError("D1 pipeline finish precedes start")


def rootfs(document: dict) -> dict[str, dict]:
    closed(document, {"schema", "entries", "entry_count", "entries_sha256"}, "rootfs manifest")
    same(document["schema"], "trillionnium.desktop.d1-rootfs-manifest.v1", "rootfs schema")
    entries = document["entries"]
    if type(entries) is not list or not 0 < len(entries) <= 200000:
        raise ValueError("D1 rootfs entries exceed bound or are absent")
    same(document["entry_count"], len(entries), "rootfs entry_count")
    same(document["entries_sha256"], hashlib.sha256(canonical(entries)).hexdigest(), "rootfs entries digest")
    by_path = {}
    base = {"path", "type", "mode", "uid", "gid", "size", "nlink", "mtime_ns", "xattrs"}
    for item in entries:
        if type(item) is not dict or type(item.get("path")) is not str:
            raise ValueError("D1 rootfs entry path is invalid")
        name, kind = item["path"], item.get("type")
        if name != ".":
            if not name.startswith("./"):
                raise ValueError("D1 rootfs path is not canonical")
            safe_relative(name[2:])
        if name in by_path:
            raise ValueError("D1 rootfs repeats a path")
        if kind not in {"file", "directory", "symlink", "character_device", "block_device", "fifo", "socket"}:
            raise ValueError("D1 rootfs object type is unsupported")
        extra = {"sha256"} if kind == "file" else {"target"} if kind == "symlink" else (
            {"device_major", "device_minor"} if kind in {"character_device", "block_device"} else set())
        if kind == "file" and integer(item.get("nlink"), "rootfs nlink", 1) > 1:
            extra.add("hardlink_head")
        closed(item, base | extra, "rootfs entry")
        for field in ("uid", "gid", "size", "mtime_ns", "nlink"):
            integer(item[field], "rootfs " + field, 1 if field == "nlink" else 0)
        if type(item["mode"]) is not str or re.fullmatch(r"[0-7]{4}", item["mode"]) is None:
            raise ValueError("D1 rootfs mode is invalid")
        if type(item["xattrs"]) is not dict or not all(type(k) is str and type(v) is str for k, v in item["xattrs"].items()):
            raise ValueError("D1 rootfs xattrs are malformed")
        if kind == "file":
            sha(item["sha256"], "rootfs file SHA")
        elif kind == "symlink":
            if type(item["target"]) is not str or "\x00" in item["target"]:
                raise ValueError("D1 rootfs symlink target is invalid")
        elif kind in {"character_device", "block_device"}:
            integer(item["device_major"], "rootfs device major")
            integer(item["device_minor"], "rootfs device minor")
        by_path[name] = item
    root = by_path.get(".")
    if root is None or root["type"] != "directory":
        raise ValueError("D1 rootfs requires an explicit root directory")
    for name in by_path:
        if name == ".":
            continue
        parent = name.rpartition("/")[0]
        directory = by_path.get(parent)
        if directory is None or directory["type"] != "directory":
            raise ValueError("D1 rootfs path has no explicit directory parent")
    for item in by_path.values():
        if item["type"] == "symlink":
            try:
                target_bytes = item["target"].encode("utf-8", "surrogateescape")
            except UnicodeEncodeError as error:
                raise ValueError("D1 rootfs symlink target is not filesystem-representable") from error
            if not target_bytes or item["size"] != len(target_bytes):
                raise ValueError("D1 rootfs symlink target byte length differs from recorded size")
    hardlink_groups: dict[str, list[str]] = {}
    for item in by_path.values():
        if "hardlink_head" in item:
            if type(item["hardlink_head"]) is not str:
                raise ValueError("D1 rootfs hardlink head is not a path")
            head = by_path.get(item["hardlink_head"])
            if head is None or head["type"] != "file":
                raise ValueError("D1 rootfs hardlink head is absent")
            same(head.get("hardlink_head"), head["path"], "rootfs hardlink head self-reference")
            for field in ("sha256", "size", "nlink", "mode", "uid", "gid", "mtime_ns", "xattrs"):
                same(item[field], head[field], "rootfs hardlink " + field)
            hardlink_groups.setdefault(head["path"], []).append(item["path"])
    for head, members in hardlink_groups.items():
        try:
            minimum = min(members, key=os.fsencode)
        except UnicodeEncodeError as error:
            raise ValueError("D1 rootfs hardlink paths are not filesystem-representable") from error
        same(head, minimum, "rootfs canonical hardlink head")
        if len(members) > by_path[head]["nlink"]:
            raise ValueError("D1 rootfs carried hardlink group exceeds nlink")
    return by_path


def verify_semantics(root: Path, receipt: dict, documents: dict[str, Any]) -> None:
    validate_contract()
    same(receipt.get("product_fixture_separation"), FIXTURE_SEPARATION, "product_fixture_separation")
    same(receipt.get("reproducibility_scope"), REPRO_SCOPE, "reproducibility_scope")
    pipeline(documents["pipeline"])
    snapshot = _Snapshot(root, receipt["output_digests"])
    product_graph = snapshot.read("evidence/product-cargo-tree.txt").decode("utf-8", "strict")
    qualification_graph = snapshot.read("evidence/qualification-cargo-tree.txt").decode("utf-8", "strict")
    for graph in (product_graph, qualification_graph):
        if not graph.startswith("hepta-agent-portd v"):
            raise ValueError("D1 exported dependency graph has the wrong owner")
    for crate in ("hepta-agent-port v", "hepta-browser-codec v"):
        if crate in product_graph or crate not in qualification_graph:
            raise ValueError("D1 exported dependency graphs violate fixture separation")
    product_strings = snapshot.read("raw-evidence/product-daemon.strings")
    qualification_strings = snapshot.read("raw-evidence/qualification-fixture.strings")
    if any(marker in product_strings for marker in (b"agent_port_ready", b"browser_runtime_available")):
        raise ValueError("D1 exported product strings contain qualification handlers")
    if not all(marker in qualification_strings for marker in (b"qualification_only", b"product_handler_connected")):
        raise ValueError("D1 exported qualification strings lack fixed handler markers")
    prepared = snapshot.document("inputs/prepared-inputs.json")
    same(prepared.get("schema"), "trillionnium.desktop.d1-prepared-inputs.v2", "prepared schema")
    if prepared.get("status") not in {"PASS_COMMITTED_SIGNED_D1_PACKAGE_LOCK", "PASS_GENERATED_SIGNED_D1_PACKAGE_LOCK"}:
        raise ValueError("D1 prepared status has not passed")
    same(prepared.get("claims"), {key: False for key in ("agent_port_activated", "disk_image_created", "product_ready",
        "qemu_booted", "rootfs_created", "servo_started", "wayland_started")}, "prepared claims")
    expected_lock = snapshot.read("inputs/expected-package-lock.tsv")
    lines = [line for line in expected_lock.decode("utf-8", "strict").splitlines() if line.strip()]
    if not lines or not all(len(line.split("\t")) == 3 and all(line.split("\t")) for line in lines):
        raise ValueError("D1 package lock is malformed")
    same(prepared.get("package_count"), len(lines), "prepared package count")
    same(prepared.get("expected_package_lock_sha256"), hashlib.sha256(expected_lock).hexdigest(), "prepared package lock digest")
    binary = snapshot.document("evidence/binary-digests.json")
    closed(binary, {"schema", "product", "qualification"}, "binary digests")
    same(binary["schema"], "trillionnium.desktop.d1-binary-digests.v1", "binary schema")
    for key, path in (("product", "target/release/hepta-agent-portd"),
                      ("qualification", "target/release/examples/hepta-agent-d1-fixture")):
        value = closed(binary[key], {"path", "sha256", "bytes"}, "binary " + key)
        same(value["path"], path, "binary path")
        sha(value["sha256"], "binary digest")
        integer(value["bytes"], "binary bytes", 1)
    builds, manifests = [], []
    for build in ("build-a", "build-b"):
        prefix = f"builds/{build}/"
        result = snapshot.document(prefix + "build-result.json")
        same(result.get("schema"), "trillionnium.desktop.d1-build-result.v2", "build schema")
        same(result.get("status"), "PASS_BUILD_ONLY", "build status")
        for field in ("release_marker_present", "network_during_acceptance", "qemu_booted"):
            same(result.get(field), False, "build " + field)
        same(result.get("prepared_manifest_sha256"), snapshot.digest("inputs/prepared-inputs.json"), "build prepared manifest")
        for field in ("source_date_epoch", "selection_sha256"):
            same(result.get(field), prepared.get(field), "build prepared " + field)
        integer(result["source_date_epoch"], "build source epoch")
        sha(result["selection_sha256"], "build selection")
        same(result.get("signed_package_set_sha256"), prepared.get("package_set_sha256"), "build signed package set")
        sha(result["signed_package_set_sha256"], "build signed package set")
        lock = closed(result.get("package_lock"), {"path", "sha256", "entries"}, "build package lock")
        same(lock, {"path": "package-lock.tsv", "sha256": hashlib.sha256(expected_lock).hexdigest(), "entries": len(lines)}, "build package lock")
        same(snapshot.read(prefix + "package-lock.tsv"), expected_lock, "actual build package bytes")
        manifest = snapshot.document(prefix + "rootfs-content-manifest.json")
        entries = rootfs(manifest)
        same(result.get("rootfs_manifest"), {"path": "rootfs-content-manifest.json", "entries": len(entries),
             "entries_sha256": manifest["entries_sha256"], "sha256": snapshot.digest(prefix + "rootfs-content-manifest.json")}, "build rootfs manifest")
        for key, path in (("product", "./usr/libexec/hepta-agent-portd"), ("qualification", "./usr/libexec/hepta-agent-d1-fixture")):
            entry = entries.get(path)
            if entry is None:
                raise ValueError("D1 rootfs binary is absent")
            for field, expected in (("type", "file"), ("uid", 0), ("gid", 0), ("mode", "0755"),
                ("nlink", 1), ("sha256", binary[key]["sha256"]), ("size", binary[key]["bytes"])):
                same(entry[field], expected, "rootfs binary " + key + "." + field)
        builds.append(result); manifests.append(manifest)
    for field in INVARIANTS:
        if field not in builds[0] or field not in builds[1]:
            raise ValueError("D1 build invariant is absent: " + field)
        same(builds[0][field], builds[1][field], "two-build invariant " + field)
    same(manifests[0], manifests[1], "two-build actual rootfs manifests")
    reproducibility(documents["reproducibility"], snapshot, builds, manifests, len(lines))
    boot = documents["boot"]
    same(boot.get("schema"), "trillionnium.desktop.d1-qemu-boot-result.v2", "boot schema")
    same(boot.get("qemu_exit_status"), 0, "boot exit")
    same(boot.get("network"), "none", "boot network")
    claims = {key: True for key in ("systemd_booted", "udev_active", "dbus_active", "logind_active", "headless_wayland_active",
        "agent_port_default_disabled", "agent_port_pid1_activation_validated", "unauthorized_peer_denied", "authorized_fixture_request",
        "per_connection_teardown", "connection_kill_recovered")}
    claims.update({key: False for key in ("network_enabled", "servo_started", "visible_window_created", "secure_boot_qualified")})
    same(boot.get("claims"), claims, "boot claims")
    same(boot.get("pre_boot_image_sha256"), builds[0]["image"]["sha256"], "boot tested image digest")
    same(boot.get("package_lock_sha256"), hashlib.sha256(expected_lock).hexdigest(), "boot package lock")
    same(boot.get("guest_acceptance_sha256"), snapshot.digest("qemu/acceptance.json"), "boot guest acceptance payload digest")
    acceptance = snapshot.document("qemu/acceptance.json")
    same(acceptance, documents["acceptance"], "inspected acceptance readback")
    same(acceptance.get("package_lock_sha256"), hashlib.sha256(expected_lock).hexdigest(), "acceptance package lock")
    same(acceptance.get("package_set_sha256"), prepared["package_set_sha256"], "acceptance signed package set")
    same(acceptance.get("image_id"), builds[0]["image_id"], "acceptance image identity")
    same(acceptance.get("network_enabled"), False, "acceptance network")
    same(acceptance.get("pid1"), "systemd", "acceptance pid1")
    for field in ("systemd", "udev", "dbus", "logind", "wayland_compositor"):
        same(acceptance.get(field), "active", "acceptance service " + field)
    agent = acceptance["agent_port"]
    same(agent.get("qualification_server_exec"), FIXTURE_SEPARATION["qualification_server_exec"], "actual qualification command")
    for field in ("qualification_only_server", "product_daemon_fixture_free", "marker_removed_before_poweroff",
        "socket_removed_before_poweroff", "default_disabled", "unauthorized_peer_denied", "authorized_request_completed",
        "per_connection_teardown", "connection_kill_recovered", "marker_created_at_runtime_only"):
        same(agent.get(field), True, "acceptance agent_port " + field)
    for field in ("product_handler_connected", "product_daemon_exercised_for_requests"):
        same(agent.get(field), False, "acceptance agent_port " + field)
    same(agent.get("product_self_check_sha256"), snapshot.digest("evidence/product-daemon-self-check-host.json"), "acceptance product self-check digest")
    for field, name in (("pipeline", "pipeline/pipeline-result.json"), ("reproducibility", "reproducibility/reproducibility-result.json"),
                        ("boot", "qemu/boot-result.json"), ("product_check", "evidence/product-daemon-self-check-host.json"),
                        ("qualification_check", "evidence/d1-qualification-self-check-host.json")):
        same(snapshot.document(name), documents[field], "inspected " + field + " readback")
    same(set(snapshot.cached), set(REQUIRED_PAYLOADS), "complete semantic payload inventory")
    snapshot.finish()


def reproducibility(document: dict, snapshot: _Snapshot, builds: list[dict], manifests: list[dict], package_count: int) -> None:
    same(document.get("schema"), "trillionnium.desktop.d1-reproducibility-result.v3", "reproducibility schema")
    same(document.get("invariant_mismatches"), [], "reproducibility invariant mismatches")
    same(document.get("package_count"), package_count, "reproducibility package count")
    same(document.get("prepared_inputs_sha256"), snapshot.digest("inputs/prepared-inputs.json"), "reproducibility prepared digest")
    same(document.get("signed_package_set_sha256"), builds[0]["signed_package_set_sha256"], "reproducibility signed package set")
    claims = {key: True for key in ("two_build_rootfs_manifest_match", "two_build_rootfs_match", "two_build_ext4_match", "two_build_kernel_match", "two_build_initrd_match")}
    claims.update({"qemu_booted": False, "servo_started": False, "product_ready": False})
    same(document.get("claims"), claims, "reproducibility claims")
    same(document.get("rootfs_manifest_diff"), {"equal": True, "first_entry_count": manifests[0]["entry_count"],
        "second_entry_count": manifests[1]["entry_count"], "missing_from_second_count": 0, "missing_from_first_count": 0,
        "changed_count": 0, "difference_count": 0, "report_truncated": False, "missing_from_second": [],
        "missing_from_first": [], "changed": []}, "reproducibility rootfs manifest diff")
    comparisons = closed(document.get("artifact_comparisons"), set(ARTIFACTS), "reproducibility comparisons")
    mapping = {"package-lock.tsv": "package_lock", "rootfs-content-manifest.json": "rootfs_manifest", "rootfs.tar": "rootfs_tar",
               "trillionnium-d1.ext4": "image", "vmlinuz": "kernel", "initrd.img": "initrd"}
    for name in ARTIFACTS:
        comparison = closed(comparisons[name], {"equal", "first_sha256", "second_sha256", "first_bytes", "second_bytes"}, "artifact comparison")
        same(comparison["equal"], True, "artifact equal")
        for side, build in zip(("first", "second"), builds):
            value = build[mapping[name]]
            if type(value) is not dict:
                raise ValueError("D1 artifact metadata is absent")
            same(value.get("path"), name, "build artifact path")
            same(sha(comparison[side + "_sha256"], "comparison digest"), sha(value.get("sha256"), "build artifact digest"), "artifact build digest")
            size = integer(comparison[side + "_bytes"], "comparison bytes", 1)
            if name == "trillionnium-d1.ext4":
                same(size, integer(value.get("bytes"), "build image bytes", 1), "artifact image bytes")
            if name in {"package-lock.tsv", "rootfs-content-manifest.json"}:
                same(comparison[side + "_sha256"], snapshot.digest(f"builds/build-{'a' if side == 'first' else 'b'}/{name}"), "actual carried artifact digest")
                same(size, len(snapshot.read(f"builds/build-{'a' if side == 'first' else 'b'}/{name}")), "actual carried artifact bytes")
        same(comparison["first_sha256"], comparison["second_sha256"], "two-build artifact SHA")
        same(comparison["first_bytes"], comparison["second_bytes"], "two-build artifact bytes")


def validate_contract(value: object | None = None) -> None:
    if value is None:
        path = Path(__file__).absolute().parents[1] / "contracts/d1-portable-evidence.v1.json"
        with os.fdopen(open_file(path), "rb") as stream:
            data = stream.read(65537)
        if len(data) > 65536:
            raise ValueError("D1 evidence contract exceeds bound")
        value = load_json_strict(data.decode("utf-8", "strict"))
    same(value, {"schema": "trillionnium.desktop.d1-portable-evidence-contract.v1",
        "status": "SOURCE_ONLY_READER_SEMANTICS", "default_product_activation": False,
        "product_fixture_separation": FIXTURE_SEPARATION, "reproducibility_scope": REPRO_SCOPE,
        "rootfs_manifest_consistency": ROOTFS_CONSISTENCY,
        "pipeline_stages": list(STAGES), "comparison_artifacts": list(ARTIFACTS),
        "carried_payloads_rehashed": list(REQUIRED_PAYLOADS),
        "absent_payloads_metadata_bound_only": ["rootfs.tar", "trillionnium-d1.ext4", "vmlinuz", "initrd.img"],
        "execute_artifact_payloads": False, "full_disk_rehash_claimed": False, "cross_run_identity_claimed": False,
        "hermetic_build_claimed": False, "installed_qualification_created_by_reader": False,
        "production_ready": False}, "portable evidence contract")
