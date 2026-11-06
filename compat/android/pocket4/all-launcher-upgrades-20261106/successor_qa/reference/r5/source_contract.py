"""Exact local source and Main binding inputs for the existing recorder adapter."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import types

HERE = Path(__file__).resolve().parent
ARTIFACT = "pocket4-bilibili-current-recorder-held-r5"
MAIN_EPOCH = "734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2"
BASELINE_SCHEMA = "pocket4-main-current-baseline-v1"
BASELINE_SHA = "163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266"
BASELINE_QUALIFICATION_SHA = "f37b2eb00db80c398c9a4f9fd895628b6c7ecc827ccf9699c2242fa5ba862ed6"
CURRENT_GUARD_SHA = "0ee54ef97c073857609aedb4670395db084ceacc7d28558315647ab2ffbef679"
HISTORICAL_ACTIVATION_SHA = "7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615"
HISTORICAL_VERIFIED_SHA = "2d6f2ef7953b98109044f823da56694111bd9f8ff14fff5e746afb7bd42b0387"
PACKAGE = "tv.danmaku.bili"
COMPONENT = PACKAGE + "/tv.danmaku.bili.MainActivityV2"
UID = 10117
REFERENCE_PINS = {
    "references/original_recorder.py": (31945, "28103c8cb444d5963eac54ffef6aeda842337e33a892336c49a71cc5b82da20b"),
    "references/android_app.py": (37574, "eb24b1b0eefb275025d10647ccf218f9395b1f74cf6d912aaabf384210d1aa66"),
    "references/android_backend.py": (36401, "088be6d783e80006645a05b8c5b90cd100d3e38b6f3d4634dd499ab1de7898ae"),
    "references/framework_epoch.py": (8658, "f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288"),
    "references/task_scope_baseline.py": (17281, "a16e347abb0de2ccbff24f6d7990f6dab1be600675054b45203e907fa8eef528"),
    "references/held_runtime_r5.py": (22691, "72cf33399ca3c280fc0c9288669f7d6c13d387e41b5fb930cf477f2b940f16b4"),
    "references/bound_android_transport_r3.py": (13721, "def4e9af81bda71cc4125b61c8a15251e07e4866627b577650e77a4fb127ecae"),
}
PRODUCTION_FILES = {"recorder.py", "source_contract.py", "main_binding.py",
                    "existing_ui_entry.py", "bound_android_transport.py",
                    "current_baseline_guard.py", "current_coordinator.py"}
HELPER_ROOT = Path("/home/alex/work/pocket4-owned-held-ns-runner-r4-01")
HELPER_PATH = HELPER_ROOT / "held-namespace-entry"
HELPER_SOURCE = HELPER_ROOT / "held_namespace_entry.rs"
HELPER_SHA = "21ba02ff60ba07667c3b5601c1ff9cb9b2d9cce2fae9290a6f39e47c18126689"
# Exact original qualified ELF, independently hashed on Pocket4; not a generic bound.
HELPER_BYTES = 4_366_312
HELPER_SOURCE_SHA = "adf5b08f7854bec061ab8d2a208f3414339701c816218881e6550afde2e6c31c"
HELPER_QUALIFICATION = Path("/home/alex/work/pocket4-owned-held-ns-runner-r4-export-01/qualification.json")
HELPER_QUALIFICATION_SHA = "3e3dd5c9ae1b4e913d7a688bb338507162cbc211bb897658a539948ffb6f93e3"


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def bounded_file(path, limit=131072):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        first = os.fstat(fd)
        require(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and first.st_size <= limit,
                "INPUT_SHAPE_OR_BOUND_CHANGED: " + json.dumps({
                    "path": str(path), "is_regular": stat.S_ISREG(first.st_mode),
                    "mode": first.st_mode, "nlink": first.st_nlink,
                    "size_bytes": first.st_size, "maximum_bytes": limit}, sort_keys=True))
        chunks = []
        count = 0
        while count <= limit:
            part = os.read(fd, min(65536, limit + 1 - count))
            if not part:
                break
            count += len(part)
            require(count <= limit, "INPUT_BYTE_BOUND_EXCEEDED")
            chunks.append(part)
        last = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        require(all(getattr(first, key) == getattr(last, key) for key in fields)
                and count == first.st_size, "INPUT_CHANGED_DURING_READ")
        return b"".join(chunks)
    finally:
        os.close(fd)


class SourceContract:
    def __init__(self, path, expected_sha256):
        self.path = Path(path).resolve()
        self.root = self.path.parent
        require(self.path == HERE / "source-manifest.json", "ADAPTER_MANIFEST_LOCATION_CHANGED")
        require(isinstance(expected_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", expected_sha256),
                "EXTERNAL_MANIFEST_PIN_REQUIRED")
        self.sha256 = expected_sha256
        raw = bounded_file(self.path)
        require(sha(raw) == expected_sha256, "ADAPTER_MANIFEST_PIN_CHANGED")
        manifest = json.loads(raw)
        require(manifest.get("schema") == 2 and manifest.get("artifact") == ARTIFACT,
                "ADAPTER_MANIFEST_SCHEMA_CHANGED")
        binding = manifest.get("current_baseline", {})
        require(binding == {"schema": BASELINE_SCHEMA, "epoch_sha256": MAIN_EPOCH,
                "baseline_sha256": BASELINE_SHA, "qualification_sha256": BASELINE_QUALIFICATION_SHA,
                "guard_sha256": CURRENT_GUARD_SHA,
                "historical_activation_sha256": HISTORICAL_ACTIVATION_SHA,
                "historical_verified_sha256": HISTORICAL_VERIFIED_SHA},
                "ACTUAL_CURRENT_HOST_MANIFEST_BINDING_REQUIRED")
        self.files = manifest["files"]
        require(isinstance(self.files, dict) and len(self.files) <= 64 and
                PRODUCTION_FILES | set(REFERENCE_PINS) == set(self.files),
                "ADAPTER_SOURCE_CLOSURE_INCOMPLETE")
        for name, row in self.files.items():
            rel = PurePosixPath(name)
            require(not rel.is_absolute() and str(rel) == name and ".." not in rel.parts,
                    "ADAPTER_SOURCE_PATH_INVALID")
            require(type(row["bytes"]) is int and 0 < row["bytes"] <= 131072 and
                    re.fullmatch(r"[0-9a-f]{64}", row["sha256"]), "ADAPTER_SOURCE_PIN_INVALID")
        for name, (length, digest) in REFERENCE_PINS.items():
            require(self.files[name] == {"bytes": length, "sha256": digest},
                    "FROZEN_REFERENCE_PIN_CHANGED")
        require(self.files["current_baseline_guard.py"]["sha256"] == CURRENT_GUARD_SHA,
                "CURRENT_GUARD_SOURCE_PIN_CHANGED")
        self.verify()

    def verify(self):
        require(sha(bounded_file(self.path)) == self.sha256, "ADAPTER_MANIFEST_CHANGED_MID_FLOW")
        for name, row in self.files.items():
            raw = bounded_file(self.root / name)
            require(len(raw) == row["bytes"] and sha(raw) == row["sha256"],
                    "ADAPTER_SOURCE_CHANGED:" + name)

    def load(self, name, module_name):
        require(name in self.files, "UNPINNED_ADAPTER_MODULE")
        raw = bounded_file(self.root / name)
        row = self.files[name]
        require(len(raw) == row["bytes"] and sha(raw) == row["sha256"], "MODULE_PIN_CHANGED")
        module = types.ModuleType(module_name)
        module.__file__ = str(self.root / name)
        exec(compile(raw, module.__file__, "exec"), module.__dict__)
        return module


def verify_shared_helper():
    require(sha(bounded_file(HELPER_SOURCE)) == HELPER_SOURCE_SHA, "HELD_HELPER_SOURCE_CHANGED")
    helper = bounded_file(HELPER_PATH, HELPER_BYTES)
    require(len(helper) == HELPER_BYTES, "HELD_HELPER_BINARY_SIZE_CHANGED")
    require(sha(helper) == HELPER_SHA, "HELD_HELPER_BINARY_CHANGED")
    require(os.access(HELPER_PATH, os.X_OK), "HELD_HELPER_NOT_EXECUTABLE")
    for path in (HELPER_PATH, HELPER_SOURCE):
        require(path.lstat().st_mode & 0o022 == 0, "HELD_HELPER_WRITABLE_BY_OTHERS")
    raw = bounded_file(HELPER_QUALIFICATION)
    require(sha(raw) == HELPER_QUALIFICATION_SHA, "HELD_HELPER_QUALIFICATION_CHANGED")
    receipt = json.loads(raw)
    require(receipt.get("schema") == 1 and receipt.get("protocol") == "owned-held-namespace-entry-v1" and
            receipt.get("qualified_for_owned_namespace_entry") is True and
            receipt.get("helper_source_sha256") == HELPER_SOURCE_SHA and
            receipt.get("helper_binary_sha256") == HELPER_SHA and
            receipt.get("host_controls_passed") == 14 and
            receipt.get("six_namespace_host_entry_passed") is True and
            receipt.get("Main_readonly_entry_passed") is True and
            receipt.get("qualified_for_whole_process_tree_cleanup") is False and
            receipt.get("candidate_production_ready") is False,
            "HELD_HELPER_NOT_QUALIFIED_FOR_DECLARED_SCOPE")
    require(set(receipt.get("evidence", {})) == {"host14", "sixns", "main_readonly"},
            "HELD_HELPER_EVIDENCE_SET_CHANGED")
    for row in receipt["evidence"].values():
        require(sha(bounded_file(row["path"], 4 * 1024 * 1024)) == row["sha256"],
                "HELD_HELPER_ACTUAL_EVIDENCE_CHANGED")
        terminal = row["terminal"]
        require(terminal["state"] == "succeeded" and terminal["exit_code"] == 0 and
                terminal["cancelled"] is False and terminal["timed_out"] is False and
                terminal["output_complete"] is True and terminal["output_durable"] is True and
                terminal["terminal_publication_confirmed"] is True,
                "HELD_HELPER_EVIDENCE_TERMINAL_INCOMPLETE")
    return {"source_sha256": HELPER_SOURCE_SHA, "binary_sha256": HELPER_SHA,
            "qualification_sha256": HELPER_QUALIFICATION_SHA,
            "whole_process_tree_cleanup_qualified": False}


def verify_scope(scope, activation, contract):
    require(scope.get("schema") == "pocket4-current-recorder-scope-v1" and
            scope.get("current_baseline_schema") == BASELINE_SCHEMA and
            scope.get("package") == PACKAGE and scope.get("component") == COMPONENT and
            type(scope.get("uid")) is int and scope["uid"] == UID and
            type(scope.get("user")) is int and scope["user"] == 0 and
            scope.get("automatic_retry") is False,
            "CURRENT_BILIBILI_SCOPE_REQUIRED")
    require(activation.get("schema") == BASELINE_SCHEMA and
            activation.get("kind") == "current-framework-generation" and
            "main_deployed" not in activation and activation.get("deployment_performed") is False and
            scope.get("epoch_sha256") == MAIN_EPOCH and
            activation["framework_epoch"]["sha256"] == MAIN_EPOCH and
            scope.get("current_baseline_sha256") == BASELINE_SHA and
            scope.get("current_baseline_qualification_sha256") == BASELINE_QUALIFICATION_SHA and
            scope.get("historical_activation_sha256") == HISTORICAL_ACTIVATION_SHA and
            scope.get("historical_verified_sha256") == HISTORICAL_VERIFIED_SHA and
            "activation_sha256" not in scope and "verified_sha256" not in scope,
            "CURRENT_BASELINE_AND_SEPARATE_HISTORY_REQUIRED")
    history = activation.get("historical_deployment", {})
    require(history.get("activation_sha256") == HISTORICAL_ACTIVATION_SHA and
            history.get("verification_sha256") == HISTORICAL_VERIFIED_SHA and
            activation.get("framework_exit_cause_resolved") is False and
            activation.get("whole_app_production_ready") is False,
            "HISTORICAL_LINEAGE_OR_PRODUCTION_BOUNDARY_CHANGED")
    require(scope.get("adapter_manifest_sha256") == contract.sha256 and
            scope.get("recorder_sha256") == contract.files["recorder.py"]["sha256"],
            "RECORDER_ADAPTER_BINDING_CHANGED")
