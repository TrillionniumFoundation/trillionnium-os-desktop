"""New per-package R5 source binding to an actual qualified successor.

Generated only after the successor guard and this versioned App scope pass.
This is source identity, not UI qualification or application readiness.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import time
import types

HERE = Path(__file__).resolve().parent
ARTIFACT = "pocket4-successor-recorder-r5-v1"
BINDING = {'schema': 'pocket4-successor-derived-recorder-binding-v1', 'package': 'com.lianjia.beike', 'component': 'com.lianjia.beike/com.lianjia.activity.MainActivity', 'uid': 10143, 'user': 0, 'runtime_guard': {'path': '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/current_baseline_guard.py', 'bytes': 3213, 'sha256': 'd84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3'}, 'baseline': {'path': '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/baseline.private.json', 'sha256': '7c52723c372b9f486067456e720709ef401bcebe1a7aad158f6b8c099f67fcc8', 'bytes': 44041}, 'qualification': {'path': '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/qualification.private.json', 'sha256': '4bdfe7dd1e275bc4727f37c630dc2498b3dc31c528b03a4028e42c1cf8fc4fc6', 'bytes': 1587}, 'runtime_epoch_sha256': 'a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9', 'framework_epoch': {'binding': {'boot_id': '981ff371-cd72-4f81-9be3-a862111afdb1', 'processes': {'init': {'cgroup': ['0::/system.slice/droidloomd.service'], 'cmdline': ['/init', 'second_stage'], 'executable': '/system/bin/init', 'host_pid': 3268779, 'namespace_pids': [3268779, 1], 'namespaces': {'mnt': 'mnt:[4026533280]', 'pid': 'pid:[4026533285]'}, 'parent_host_pid': 3268775, 'start_ticks': 99615082, 'uids': [0, 0, 0, 0]}, 'surfaceflinger': {'cgroup': ['0::/system.slice/droidloomd.service/system/uid_1000/pid_661'], 'cmdline': ['/system/bin/surfaceflinger'], 'executable': '/system/bin/surfaceflinger', 'host_pid': 3270350, 'namespace_pids': [3270350, 661], 'namespaces': {'mnt': 'mnt:[4026533280]', 'pid': 'pid:[4026533285]'}, 'parent_host_pid': 3268779, 'start_ticks': 99615245, 'uids': [1000, 1000, 1000, 1000]}, 'system_server': {'cgroup': ['0::/system.slice/droidloomd.service/system/uid_1000/pid_808'], 'cmdline': ['system_server'], 'executable': '/system/bin/app_process64', 'host_pid': 3270611, 'namespace_pids': [3270611, 808], 'namespaces': {'mnt': 'mnt:[4026533719]', 'pid': 'pid:[4026533285]'}, 'parent_host_pid': 3270325, 'start_ticks': 99615342, 'uids': [1000, 1000, 1000, 1000]}, 'zygote64': {'cgroup': ['0::/system.slice/droidloomd.service/system/uid_0/pid_638'], 'cmdline': ['zygote64'], 'executable': '/system/bin/app_process64', 'host_pid': 3270325, 'namespace_pids': [3270325, 638], 'namespaces': {'mnt': 'mnt:[4026533718]', 'pid': 'pid:[4026533285]'}, 'parent_host_pid': 3268779, 'start_ticks': 99615242, 'uids': [0, 0, 0, 0]}}}, 'collected_monotonic_ns': 996169557306983, 'schema': 'pocket4-framework-epoch-v1', 'sha256': '7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c'}, 'app_scope': {'bytes': 2779, 'path': '/home/alex/work/pocket4-beike-successor-qa-input-20261106-b34f158f88bbebf112840fd88df25d03/beike-and-existing-actions.private.json', 'sha256': '2f3ed55a035e64401189cd2afbaded2414c7b0b9a3c641a82308a1c68b96a8eb'}, 'packages': {'com.lianjia.beike': 10143, 'local.pocket4.actions.v2': 10125}, 'app_directories': {'/data/user/0/com.lianjia.beike': {'device': 1811, 'inode': 152786, 'uid': 10143, 'gid': 10143}, '/data/user_de/0/com.lianjia.beike': {'device': 1811, 'inode': 152789, 'uid': 10143, 'gid': 10143}, '/data/user/0/local.pocket4.actions.v2': {'device': 1811, 'inode': 142156, 'uid': 10125, 'gid': 10125}, '/data/user_de/0/local.pocket4.actions.v2': {'device': 1811, 'inode': 142227, 'uid': 10125, 'gid': 10125}}, 'held_init_identity': {'cgroup': '0::/system.slice/droidloomd.service\n', 'exe': '/system/bin/init', 'ns': {'cgroup': 'cgroup:[4026533387]', 'ipc': 'ipc:[4026533284]', 'mnt': 'mnt:[4026533280]', 'net': 'net:[4026533041]', 'pid': 'pid:[4026533285]', 'uts': 'uts:[4026533281]'}, 'nspid': ['3268779', '1'], 'pid': 3268779, 'ppid': 3268775, 'start': '99615082', 'uid': ['0', '0', '0', '0']}, 'classpath_values': {'BOOTCLASSPATH': '/apex/com.android.art/javalib/core-oj.jar:/apex/com.android.art/javalib/core-libart.jar:/apex/com.android.art/javalib/okhttp.jar:/apex/com.android.art/javalib/bouncycastle.jar:/apex/com.android.art/javalib/apache-xml.jar:/system/framework/framework.jar:/system/framework/framework-graphics.jar:/system/framework/framework-location.jar:/system/framework/ext.jar:/system/framework/telephony-common.jar:/system/framework/voip-common.jar:/system/framework/ims-common.jar:/system/framework/framework-ondeviceintelligence-platform.jar:/apex/com.android.i18n/javalib/core-icu4j.jar:/apex/com.android.adservices/javalib/framework-adservices.jar:/apex/com.android.adservices/javalib/framework-sdksandbox.jar:/apex/com.android.appsearch/javalib/framework-appsearch.jar:/apex/com.android.bt/javalib/framework-bluetooth.jar:/apex/com.android.configinfrastructure/javalib/framework-configinfrastructure.jar:/apex/com.android.conscrypt/javalib/conscrypt.jar:/apex/com.android.conscrypt/javalib/framework-conscrypt-nsc.jar:/apex/com.android.crashrecovery/javalib/framework-crashrecovery.jar:/apex/com.android.devicelock/javalib/framework-devicelock.jar:/apex/com.android.healthfitness/javalib/framework-healthfitness.jar:/apex/com.android.ipsec/javalib/android.net.ipsec.ike.jar:/apex/com.android.media/javalib/updatable-media.jar:/apex/com.android.mediaprovider/javalib/framework-mediaprovider.jar:/apex/com.android.mediaprovider/javalib/framework-pdf.jar:/apex/com.android.mediaprovider/javalib/framework-pdf-v.jar:/apex/com.android.mediaprovider/javalib/framework-photopicker.jar:/apex/com.android.nfcservices/javalib/framework-nfc.jar:/apex/com.android.npumanager/javalib/framework-npumanager.jar:/apex/com.android.ondevicepersonalization/javalib/framework-ondevicepersonalization.jar:/apex/com.android.os.statsd/javalib/framework-statsd.jar:/apex/com.android.permission/javalib/framework-permission.jar:/apex/com.android.permission/javalib/framework-permission-s.jar:/apex/com.android.profiling/javalib/framework-anomaly-detector.jar:/apex/com.android.profiling/javalib/framework-profiling.jar:/apex/com.android.scheduling/javalib/framework-scheduling.jar:/apex/com.android.sdkext/javalib/framework-sdkextensions.jar:/apex/com.android.telephonycore/javalib/framework-telecom.jar:/apex/com.android.telephonycore/javalib/framework-telephony.jar:/apex/com.android.tethering/javalib/framework-connectivity.jar:/apex/com.android.tethering/javalib/framework-connectivity-b.jar:/apex/com.android.tethering/javalib/framework-connectivity-t.jar:/apex/com.android.tethering/javalib/framework-tethering.jar:/apex/com.android.uprobestats/javalib/framework-uprobestats.jar:/apex/com.android.uwb/javalib/framework-ranging.jar:/apex/com.android.uwb/javalib/framework-uwb.jar:/apex/com.android.virt/javalib/framework-virtualization.jar:/apex/com.android.webapp/javalib/framework-webapp.jar:/apex/com.android.wifi/javalib/framework-wifi.jar', 'DEX2OATBOOTCLASSPATH': '/apex/com.android.art/javalib/core-oj.jar:/apex/com.android.art/javalib/core-libart.jar:/apex/com.android.art/javalib/okhttp.jar:/apex/com.android.art/javalib/bouncycastle.jar:/apex/com.android.art/javalib/apache-xml.jar:/system/framework/framework.jar:/system/framework/framework-graphics.jar:/system/framework/framework-location.jar:/system/framework/ext.jar:/system/framework/telephony-common.jar:/system/framework/voip-common.jar:/system/framework/ims-common.jar:/system/framework/framework-ondeviceintelligence-platform.jar:/apex/com.android.i18n/javalib/core-icu4j.jar'}, 'status': {'host_pid': 3268774}, 'native_cli': {'path': '/usr/bin/droidloomctl', 'bytes': 1705648, 'sha256': 'f81e0223f6b256584d07a5e8fbc72f3f4c764ab53a88469b45b587c101e12c79'}, 'launcher_catalog_reference': {'path': '/home/alex/work/pocket4-beike-successor-qa-input-20261106-b34f158f88bbebf112840fd88df25d03/native-catalog.stdout.raw.json', 'sha256': '1352cb70367b09af255283dcbaecd8680c4d6bad662cf6432d01e2f2d6cabf54', 'bytes': 10114}, 'qa_input_reference': {'path': '/home/alex/work/pocket4-beike-successor-qa-input-20261106-b34f158f88bbebf112840fd88df25d03/qa-build-input.private.json', 'sha256': 'c393a18171684b84e4fc15588bcddfea1f14e96f1a5bb9bb2802377c598f2184', 'bytes': 6718}, 'launcher_resolver_reenumerated_by_generator': False, 'public_text': '北京', 'allowed_operations': ['state', 'inspect', 'click', 'set_text'], 'generation_nonce': 'b34f158f88bbebf112840fd88df25d03', 'old_Bili_unknown_reconciled': False, 'Bili_Accept_authorized_in_Main': False, 'Meituan_location_grant_authorized': False, 'security_bypass_authorized': False, 'UI_admitted': False, 'production_ready': False}
PACKAGE = BINDING["package"]
COMPONENT = BINDING["component"]
UID = BINDING["uid"]
MAIN_EPOCH = BINDING["framework_epoch"]["sha256"]
BASELINE_SCHEMA = "pocket4-successor-runtime-baseline-v1"
BASELINE_SHA = BINDING["baseline"]["sha256"]
BASELINE_QUALIFICATION_SHA = BINDING["qualification"]["sha256"]
CURRENT_GUARD_SHA = BINDING["runtime_guard"]["sha256"]
REFERENCE_PINS = {'references/android_app.py': (37574, 'eb24b1b0eefb275025d10647ccf218f9395b1f74cf6d912aaabf384210d1aa66'), 'references/android_backend.py': (36401, '088be6d783e80006645a05b8c5b90cd100d3e38b6f3d4634dd499ab1de7898ae'), 'references/bound_android_transport_r3.py': (13721, 'def4e9af81bda71cc4125b61c8a15251e07e4866627b577650e77a4fb127ecae'), 'references/framework_epoch.py': (8658, 'f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288'), 'references/held_runtime_r5.py': (22691, '72cf33399ca3c280fc0c9288669f7d6c13d387e41b5fb930cf477f2b940f16b4'), 'references/original_recorder.py': (31945, '28103c8cb444d5963eac54ffef6aeda842337e33a892336c49a71cc5b82da20b'), 'references/task_scope_baseline.py': (17281, 'a16e347abb0de2ccbff24f6d7990f6dab1be600675054b45203e907fa8eef528')}
PRODUCTION_FILES = {"recorder.py", "source_contract.py", "main_binding.py",
                    "existing_ui_entry.py", "bound_android_transport.py", "current_coordinator.py"}


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def bounded_file(path, limit=131072):
    path = str(path)
    parts = path[1:].split("/")
    require(path.startswith("/") and not any(x in ("", ".", "..") for x in parts), "CANONICAL_SOURCE_PATH")
    fds = []
    try:
        d = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        fds.append(d)
        for part in parts[:-1]:
            d = os.open(part, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=d)
            fds.append(d)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=d)
        fds.append(fd)
        def meta(f):
            s = os.fstat(f)
            return tuple(getattr(s, k) for k in ("st_dev", "st_ino", "st_size", "st_mode", "st_uid", "st_gid", "st_nlink", "st_mtime_ns", "st_ctime_ns"))
        first = os.fstat(fd)
        before = meta(fd)
        require(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and 0 <= first.st_size <= limit, "BOUNDED_SINGLE_REGULAR_FILE")
        data, deadline = bytearray(), time.monotonic() + 10
        while len(data) <= limit:
            require(time.monotonic() < deadline, "SOURCE_READ_DEADLINE")
            chunk = os.read(fd, min(65536, limit + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        require(len(data) == first.st_size and meta(fd) == before, "SOURCE_CHANGED_DURING_READ")
        check = os.open(parts[-1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=d)
        fds.append(check)
        require(meta(check) == before, "SOURCE_PATH_REPLACED")
        return bytes(data)
    finally:
        failures = []
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError:
                failures.append(fd)
        require(not failures, "SOURCE_FD_CLOSE_FAILED")


def pinned(reference, limit=4 * 1024 * 1024):
    raw = bounded_file(reference["path"], limit)
    require(len(raw) == reference["bytes"] and sha(raw) == reference["sha256"], "EXACT_PINNED_INPUT_CHANGED")
    return raw


class SourceContract:
    def __init__(self, path, expected_sha256):
        self.path = Path(path)
        self.root = self.path.parent
        require(self.path == HERE / "source-manifest.json", "EXACT_MANIFEST_LOCATION")
        require(isinstance(expected_sha256, str) and re.fullmatch("[0-9a-f]{64}", expected_sha256), "EXTERNAL_MANIFEST_PIN")
        self.sha256 = expected_sha256
        raw = bounded_file(self.path)
        require(sha(raw) == expected_sha256, "SOURCE_MANIFEST_CHANGED")
        manifest = json.loads(raw)
        require(set(manifest) == {"schema", "artifact", "binding_sha256", "files", "UI_admitted", "production_ready"}
                and manifest["schema"] == 3 and manifest["artifact"] == ARTIFACT
                and manifest["binding_sha256"] == sha(json.dumps(BINDING, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode())
                and manifest["UI_admitted"] is False and manifest["production_ready"] is False, "NEW_SOURCE_IDENTITY_REQUIRED")
        self.files = manifest["files"]
        require(set(self.files) == PRODUCTION_FILES | set(REFERENCE_PINS), "EXACT_SOURCE_CLOSURE")
        for name, row in self.files.items():
            rel = PurePosixPath(name)
            require(not rel.is_absolute() and str(rel) == name and ".." not in rel.parts and
                    set(row) == {"bytes", "sha256"} and type(row["bytes"]) is int and 0 < row["bytes"] <= 131072
                    and re.fullmatch("[0-9a-f]{64}", row["sha256"]), "SOURCE_ROW_INVALID")
        for name, (length, digest) in REFERENCE_PINS.items():
            require(self.files[name] == {"bytes": length, "sha256": digest}, "FROZEN_REFERENCE_CHANGED")
        self.verify()

    def verify(self):
        require(sha(bounded_file(self.path)) == self.sha256, "MANIFEST_CHANGED_DURING_FLOW")
        for name, row in self.files.items():
            raw = bounded_file(self.root / name)
            require(len(raw) == row["bytes"] and sha(raw) == row["sha256"], "SOURCE_CHANGED:" + name)

    def load(self, name, module_name):
        require(name in self.files, "UNPINNED_MODULE")
        raw = bounded_file(self.root / name)
        row = self.files[name]
        require(len(raw) == row["bytes"] and sha(raw) == row["sha256"], "MODULE_CHANGED")
        module = types.ModuleType(module_name)
        module.__file__ = str(self.root / name)
        exec(compile(raw, module.__file__, "exec"), module.__dict__)
        return module


def load_guard():
    raw = pinned(BINDING["runtime_guard"], 65536)
    module = types.ModuleType("actual_successor_guard")
    module.__file__ = BINDING["runtime_guard"]["path"]
    exec(compile(raw, module.__file__, "exec"), module.__dict__)
    require(module.PINS["baseline"] == BINDING["baseline"] and
            module.PINS["qualification"] == BINDING["qualification"], "ACTUAL_GUARD_DOCUMENT_PINS_CHANGED")
    return module


def activation():
    """Explicit derived binding view. It never claims to be a runtime baseline."""
    return json.loads(json.dumps(BINDING, sort_keys=True))


def actual_documents():
    return pinned(BINDING["baseline"]), pinned(BINDING["qualification"], 65536)


def verify_saved_baseline(root):
    for name, pin in (("baseline.json", BINDING["baseline"]), ("baseline-qualification.json", BINDING["qualification"])):
        data = bounded_file(root / name, 4 * 1024 * 1024)
        require(len(data) == pin["bytes"] and sha(data) == pin["sha256"], "SAVED_ACTUAL_BASELINE_CHANGED")


def runtime_and_app_guard(guard, attempted=False):
    result = guard.current_guard(action_attempted=attempted)
    require(result["schema"] == "pocket4-successor-main-guard-v1" and
            result["Main_epoch_sha256"] == MAIN_EPOCH and
            result["runtime_epoch_sha256"] == BINDING["runtime_epoch_sha256"], "EXACT_SUCCESSOR_RUNTIME_REQUIRED")
    try:
        app = guard.check_app_scope(BINDING["app_scope"], sorted(BINDING["packages"]))
        require(app["app_scope_sha256"] == BINDING["app_scope"]["sha256"], "EXACT_APP_VERSION_SCOPE_REQUIRED")
        return result
    except BaseException as error:
        error.action_attempted = attempted
        error.outcome_unknown = attempted
        error.automatic_retry = False
        raise


def verify_scope(scope, observed_activation, contract):
    require(observed_activation == activation(), "DERIVED_BINDING_VIEW_CHANGED")
    expected = {"schema": "pocket4-successor-recorder-scope-v1", "current_baseline_schema": BASELINE_SCHEMA,
                "package": PACKAGE, "component": COMPONENT, "uid": UID, "user": 0,
                "current_baseline_sha256": BASELINE_SHA,
                "current_baseline_qualification_sha256": BASELINE_QUALIFICATION_SHA,
                "epoch_sha256": MAIN_EPOCH, "runtime_epoch_sha256": BINDING["runtime_epoch_sha256"],
                "app_scope_sha256": BINDING["app_scope"]["sha256"],
                "adapter_manifest_sha256": contract.sha256,
                "recorder_sha256": contract.files["recorder.py"]["sha256"], "automatic_retry": False}
    require(set(scope) == set(expected) | {"created_utc"} and
            all(scope[k] == v for k, v in expected.items()) and isinstance(scope["created_utc"], str),
            "EXACT_SUCCESSOR_PACKAGE_SCOPE_REQUIRED")


HELPER_ROOT = Path("/home/alex/work/pocket4-owned-held-ns-runner-r4-01")
HELPER_PATH = HELPER_ROOT / "held-namespace-entry"
HELPER_SOURCE = HELPER_ROOT / "held_namespace_entry.rs"
HELPER_SHA = "21ba02ff60ba07667c3b5601c1ff9cb9b2d9cce2fae9290a6f39e47c18126689"
# Exact original qualified ELF, independently hashed on Pocket4; not a generic bound.
HELPER_BYTES = 4_366_312
HELPER_SOURCE_SHA = "adf5b08f7854bec061ab8d2a208f3414339701c816218881e6550afde2e6c31c"
HELPER_QUALIFICATION = Path("/home/alex/work/pocket4-owned-held-ns-runner-r4-export-01/qualification.json")
HELPER_QUALIFICATION_SHA = "3e3dd5c9ae1b4e913d7a688bb338507162cbc211bb897658a539948ffb6f93e3"


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

