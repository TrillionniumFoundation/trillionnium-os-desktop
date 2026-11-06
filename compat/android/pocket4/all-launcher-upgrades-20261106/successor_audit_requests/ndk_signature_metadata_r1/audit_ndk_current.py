#!/usr/bin/env python3
"""One current NDK APK: ordinary signature and metadata tools, full48 identity protection; no UI or install."""
import sys
import argparse
import base64
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import time
import types
import zlib

sys.dont_write_bytecode = True

DEPS = {"path": "/home/alex/work/pocket4-app-identities-20261105-r12-01/dependencies.json",
        "sha256": "dfe1182d8e0da4d3d6e842736378539df33e03a87cf0ed9ab4bbe9ae1f26c041"}

ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "TZ": "UTC"}

STAT = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")

MAX_APK = 512 * 1024 * 1024

MAX_BATCH_BYTES = 4 * 1024 * 1024 * 1024

MAX_TOOL_OUTPUT = 4 * 1024 * 1024

MAX_RESULT = 512 * 1024

ACTUAL_GUARD = {"path": "/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/current_baseline_guard.py",
                "bytes": 3213, "sha256": "d84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3"}

ACTUAL_CANDIDATE = {'bytes': 54512, 'file': {'st_ctime_ns': 1791415705179294996, 'st_dev': 66306, 'st_gid': 0, 'st_ino': 108138273, 'st_mode': 33261, 'st_mtime_ns': 1757926427000000000, 'st_nlink': 1, 'st_size': 54512, 'st_uid': 0}, 'path': '/usr/lib/android-sdk/build-tools/debian/aapt2', 'sha256': '0e9ff92342040acdfd03e8708512f4e02353e3ca0a2b85ea2950da659110b009'}

ACTUAL_PROOF = {'path': '/home/alex/work/pocket4-calendar-official-aapt2-source-20261106-r1/inputs/aapt2-proof.outer.original.json', 'bytes': 54192, 'sha256': 'f9c289f7d28f836c51d845b4c851c1dbac0e8f326d658c7b98106b6ee327f192'}

ACTUAL_PROOF_TERMINAL = {'path': '/home/alex/work/pocket4-calendar-official-aapt2-source-20261106-r1/inputs/aapt2-proof.terminal.original.json', 'bytes': 730, 'sha256': 'f797f008a250a386ca905e9b7e9065ac2f85cad2168be702c3ad01209d341802'}

PROOF_JOB = "1a1b1cdd0e7-fc05-7ae1"

ANDROID_VERSION_DEFAULT_REFERENCE = {'origin': 'AOSP primary source, not an assertion of exact live ELF provenance', 'commit': '13f9d65c456ee75c488b5d5eccdaa277437528ef', 'blob': '73df5e8e7b1bbf943a03c852bb5fa1ff8b10fa89', 'url': 'https://android.googlesource.com/platform/frameworks/base.git/+/13f9d65c456ee75c488b5d5eccdaa277437528ef/core/java/com/android/internal/pm/parsing/pkg/PackageImpl.java', 'symbol': 'PackageImpl constructor', 'versionCode_default': 0, 'versionCodeMajor_default': 0, 'method': 'TypedArray.getInteger(attribute, defaultValue)', 'versionName_omission_is_null_reference': 'https://android.googlesource.com/platform/frameworks/base.git/+/main/core/java/android/content/pm/PackageInfo.java', 'typed_version_name': 'nullable; no invented display name'}

OFFICIAL_HOST_JOB = '1a1b257ba27-fc05-7da0'

OFFICIAL_HOST_SOURCE = {'bytes': 61830, 'path': '/home/alex/work/pocket4-official-aapt2-host-tool-source-20261106-r3/prepare_official_aapt2.py', 'sha256': 'bdae0316cd5423f60a6d1884e2131ba446c3554ee696c3c543ebf3634e743a63'}

OFFICIAL_HOST_STDOUT = {'path': '/home/alex/work/pocket4-calendar-official-aapt2-source-20261106-r1/inputs/official-host.stdout.original.jsonl', 'bytes': 7092, 'sha256': 'd7785fb80d8075267b99f1ccc5537cdd12dc014f38fd72c87eb575bd899dd343'}

OFFICIAL_HOST_TERMINAL = {'path': '/home/alex/work/pocket4-calendar-official-aapt2-source-20261106-r1/inputs/official-host.terminal.original.json', 'bytes': 731, 'sha256': 'f456a3ee2db689339d5d60db5106904b0d2bde640663eccc222311db39f62435'}

OFFICIAL_CANDIDATE = {'path': '/var/lib/pocket4-official-aapt2-host-tool-proof-20261106-r3/toolchain/platform/bin/aapt2', 'bytes': 6489808, 'sha256': 'd0c30c343c61bfdc837abd02e195741dba7407bcb61ca34e037bcc1dc26ea06c', 'file': {'st_ctime_ns': 1793993457351638049, 'st_dev': 66306, 'st_gid': 0, 'st_ino': 110244195, 'st_mode': 33088, 'st_mtime_ns': 1793993457351638049, 'st_nlink': 1, 'st_size': 6489808, 'st_uid': 0}}

OFFICIAL_TOOL_ROOT = '/var/lib/pocket4-official-aapt2-host-tool-proof-20261106-r3'

STAGE = '/home/alex/work/pocket4-ndk-current-apk-audit-source-20261106-r1'
OUTPUT_PREFIX = '/home/alex/work/pocket4-ndk-current-apk-audit-20261106-r1'
ACTUAL_SCOPE = {'bytes': 59957, 'path': '/home/alex/work/pocket4-current-explicit-48-app-observation-20261106-r1/app-scope.private.json', 'sha256': 'b184299ce0a39a998752ed980a43192b396099f780bcf60bcfe53d0edf92ffe4'}
PROTECTED_PACKAGES = ['com.Hyatt.hyt', 'com.MobileTicket', 'com.amazon.mShop.android.shopping', 'com.android.calendar', 'com.android.camera2', 'com.android.contacts', 'com.android.deskclock', 'com.android.dialer', 'com.android.documentsui', 'com.android.gallery3d', 'com.android.messaging', 'com.android.quicksearchbox', 'com.android.settings', 'com.android.threadnetwork.demoapp', 'com.bestbuy.android', 'com.ehi.national.mobile', 'com.enflick.android.TextNow', 'com.example.ndk_tests', 'com.google.android.gms', 'com.hertz.android.digital', 'com.hilton.android.hhonors', 'com.ihg.apps.android', 'com.jingdong.app.mall', 'com.lianjia.beike', 'com.marriott.mrt', 'com.pinger.textfree', 'com.rytong.airchina', 'com.rytong.ceair', 'com.sankuai.meituan.takeoutnew', 'com.sdu.didi.psnger', 'com.ss.android.ugc.aweme', 'com.szzc', 'com.taobao.taobao', 'com.tencent.mm', 'com.ubercab', 'com.united.mobile.android', 'com.xunmeng.pinduoduo', 'com.zhubajie.client', 'com.zillow.android.streeteasy', 'ctrip.android.view', 'jp.co.ana.android.tabidachi', 'local.pocket4.actions.v2', 'local.pocket4.fixture', 'org.chromium.webview_shell', 'org.droidloom.qa.editorcontract', 'org.droidloom.qa.successor.p8f89f253350ba2fa.r1', 'org.fcitx.fcitx5.android', 'tv.danmaku.bili']
NDK_EXPECTED = {'apks': [{'bytes': 1397258, 'file': {'st_ctime_ns': 1794002633656020265, 'st_dev': 1811, 'st_gid': 1000, 'st_ino': 656356, 'st_mode': 33188, 'st_mtime_ns': 1794002633656020265, 'st_nlink': 1, 'st_size': 1397258, 'st_uid': 1000}, 'path': '/data/app/~~8JR2GX_46psP21ozXayFmw==/com.example.ndk_tests-HmeuCBFzplykpELLMAOdPA==/base.apk', 'sha256': 'b3bf438dedbcdd5f3ac871733a273b3cece446db6be308df73f95b08cb46d164'}], 'code_path': '/data/app/~~8JR2GX_46psP21ozXayFmw==/com.example.ndk_tests-HmeuCBFzplykpELLMAOdPA==', 'data_directories': {'user': {'device': 1811, 'gid': 10162, 'inode': 161234, 'status': 'PRESENT', 'uid': 10162}, 'user_de': {'device': 1811, 'gid': 10162, 'inode': 163339, 'status': 'PRESENT', 'uid': 10162}}, 'fresh_signature_verification': False, 'package': 'com.example.ndk_tests', 'package_manager_certificate_sha256': ['a899ddfa8c4b57a962c2bb1ae885a44bd904d7b63f6fd301abf514edf70ad72c'], 'uid': 10162, 'version_code': 0}
ACTUAL_INVENTORY = {'bytes': 9876, 'path': '/home/alex/work/pocket4-calendar-official-aapt2-source-20261106-r1/inputs/inventory.original.json', 'sha256': '60ee9c47cb1719343a1667d306e26086d66f2376d62b8c5251f4e64446887341'}
SCOPE_JOB = '1a1b31300b9-fc05-8095'
SCOPE_STAGE = '/home/alex/work/pocket4-explicit-48-scope-source-20261106-r1'
SCOPE_VALIDATOR = {'path': '/home/alex/work/pocket4-explicit-48-scope-source-20261106-r1/owned_readonly_lifetime.py', 'bytes': 17291, 'sha256': 'f42eaeab2bea2f9a697b705e5903aac6257d7c94698ee85cbc97bbf78b25064e'}
SCOPE_STDOUT = {'path': '/home/alex/work/pocket4-ndk-current-apk-audit-source-20261106-r1/inputs/scope48.stdout.original.jsonl', 'bytes': 22547, 'sha256': 'ae494d741522c8ff5efcfe7c36b256790c1387e6ee62824b9538a7ec785494ae'}
SCOPE_TERMINAL = {'path': '/home/alex/work/pocket4-ndk-current-apk-audit-source-20261106-r1/inputs/scope48.terminal.original.json', 'bytes': 733, 'sha256': '76d9c72989ac5af982c25692bb06acb0c4e815742a24b19efbc7a3e836328ea1'}


def validate_candidate(candidate):
    need(type(candidate) is dict and set(candidate) == {"path", "bytes", "sha256", "file"}, "EXACT_CANDIDATE_PIN_SCHEMA")
    need(candidate == ACTUAL_CANDIDATE, "EXACT_ACTUAL_CANDIDATE_BYTES_AND_INTEGER_STAT_REQUIRED")
    need(type(candidate["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", candidate["sha256"]), "CANDIDATE_SHA_REQUIRED")
    value = candidate["file"]
    need(type(value) is dict and set(value) == set(STAT) and all(type(value[key]) is int for key in STAT), "EXACT_INTEGER_FILE_STAT_REQUIRED")
    need(stat.S_ISREG(value["st_mode"]) and value["st_nlink"] == 1 and value["st_size"] == candidate["bytes"] and value["st_mode"] & 0o111, "REGULAR_EXECUTABLE_CANDIDATE_REQUIRED")


def verify_candidate_inventory(candidate, inventory):
    validate_candidate(candidate)
    need(inventory.get("schema") == "pocket4-two-proposed-aapt2-host-candidates-v1" and inventory.get("ok") is True and inventory.get("errors") == [], "ACTUAL_COMPLETE_CANDIDATE_INVENTORY_REQUIRED")
    need(inventory.get("process_FDs_before") == inventory.get("process_FDs_after") and type(inventory.get("process_FDs_before")) is int, "INVENTORY_FDS_NOT_RETIRED")
    need(all(type(inventory.get(key)) is int and inventory[key] == 0 for key in ("candidate_executions", "Main_reads", "Android_commands", "native_commands", "namespace_entries", "installs", "UI_actions", "permission_changes")), "INVENTORY_BOUNDARY_CHANGED")
    rows = [row for row in inventory["candidates"] if row.get("path") == candidate["path"]]
    need(len(rows) == 1, "UNIQUE_OBSERVED_CANDIDATE_REQUIRED")
    row = rows[0]
    need(row.get("status") == "OBSERVED_REGULAR_FILE" and row.get("held_file_and_path_full_stat_rechecked") is True and row.get("parent_identity_rechecked") is True, "CANDIDATE_OBSERVATION_INCOMPLETE")
    need(row.get("bytes") == candidate["bytes"] and row.get("sha256") == candidate["sha256"] and row.get("stat") == candidate["file"], "CANDIDATE_DIFFERS_FROM_ACTUAL_INVENTORY")
    need(row.get("elf_header", {}).get("host_x86_64_header") is True and row.get("elf_header", {}).get("execution_performed") is False, "OBSERVED_HOST_ELF_HEADER_REQUIRED")
    return row


def verify_actual_proof(proof, terminal, candidate):
    """Use exact observed facts; the old exit-1 help job remains failed."""
    validate_candidate(candidate)
    need(proof.get("schema") == "pocket4-existing-dpkg-aapt2-host-proof-and-interface-v1", "ACTUAL_PROOF_SCHEMA")
    need(proof.get("candidate") == candidate, "PROOF_CANDIDATE_DIFFERS")
    need(terminal.get("job_id") == PROOF_JOB and terminal.get("state") == "failed" and terminal.get("exit_code") == 1,
         "PRESERVE_ACTUAL_FAILED_HELP_JOB")
    need(all(terminal.get(key) is True for key in ("output_complete", "output_durable", "terminal_publication_confirmed")),
         "PROOF_AUTHORITATIVE_TERMINAL_REQUIRED")
    need(all(terminal.get(key) is False for key in ("automatic_retry", "timed_out", "cancelled")), "PROOF_TERMINAL_NOT_SETTLED")
    need(terminal.get("log_truncated") == {"stdout": False, "stderr": False} and
         terminal.get("log_errors") == {"stdout": None, "stderr": None} and
         terminal.get("log_synced") == {"stdout": True, "stderr": True}, "PROOF_LOG_COMPLETENESS")
    need(proof.get("ok") is False and proof.get("status") == "HOST_PROOF_OR_INTERFACE_INCOMPLETE_NO_RETRY" and
         proof.get("errors") == [], "ORIGINAL_PROOF_FAILURE_MUST_REMAIN")
    need(proof.get("process_FDs_before") == proof.get("process_FDs_after") == 4 and
         proof.get("all_owned_tool_children_joined") is True and proof.get("all_bound_host_files_unchanged") is True,
         "PROOF_IDENTITY_OR_RETIREMENT_INCOMPLETE")
    need(proof.get("installed_dpkg_candidate_membership_and_checksum_match") is True,
         "ACTUAL_DPKG_MEMBERSHIP_CHECKSUM_REQUIRED")
    need(all(type(proof.get(key)) is int and proof[key] == 0 for key in
         ("APK_reads", "APK_tool_inputs", "Android_commands", "App_launches", "Main_reads", "UI_actions", "installs",
          "namespace_entries", "native_commands", "permission_changes")) and proof.get("action_lock_acquired") is False,
         "PROOF_ACTION_BOUNDARY_CHANGED")
    commands = proof.get("commands")
    need(type(commands) is list and len(commands) == 2 and proof.get("candidate_executions") == 2, "EXACT_TWO_HOST_COMMANDS")
    for command, tail, code in zip(commands, (["version"], ["dump", "badging", "--help"]), (0, 1)):
        need(command.get("argv") == [candidate["path"], *tail] and command.get("returncode") == code,
             "ACTUAL_INTERFACE_COMMAND_DIFFERS")
        need(command.get("joined") is True and command.get("pipes_closed") is True and
             command.get("output_capture_complete") is True and command.get("timed_out") is False and
             not command.get("error") and not command.get("retirement_error"), "PROOF_CHILD_NOT_SETTLED")
        for stream in ("stdout", "stderr"):
            raw = bytes.fromhex(command[stream + "_original_hex"])
            need(len(raw) == command[stream]["bytes"] and sha(raw) == command[stream]["sha256"], "PROOF_LOG_PIN_CHANGED")
    need(commands[1]["stderr"]["bytes"] == 199 and commands[1]["stderr"]["sha256"] ==
         "c5fb01d0065654135344c1ba9a082c3524363d154fec18f114e0dfef5caa711b", "EXACT_ACTUAL_BADGING_USAGE_REQUIRED")
    graph = proof.get("static_dependency_graph")
    need(type(graph) is list and len(graph) == proof.get("static_dependency_file_count") == 19,
         "ACTUAL_NINETEEN_FILE_STATIC_GRAPH_REQUIRED")
    need(len({row["file"]["resolved_path"] for row in graph}) == len(graph), "STATIC_FILE_PATH_NOT_UNIQUE")
    need(all(row["static_elf"]["additional_loader_directives"] == [] for row in graph), "UNREVIEWED_LOADER_DIRECTIVE")
    return {"job_id": PROOF_JOB, "prior_job_state": "failed", "prior_job_exit_code": 1,
            "prior_job_reclassified": False, "version_returncode": 0, "help_returncode": 1,
            "actual_usage_observed": True, "dpkg_membership_and_checksum_observed": True,
            "distribution_signature_reverified": False, "static_graph_is_runtime_loader_proof": False}


def bind_static_dependencies(core, pool, rows, end, proof):
    aliases = []
    for index, item in enumerate(proof["static_dependency_graph"]):
        need(time.monotonic() < end, "DIAGNOSTIC_DEADLINE_BEFORE_DEPENDENCY_BIND")
        pin = item["file"]
        need(str(Path(pin["declared_path"]).resolve()) == pin["resolved_path"], "ACTUAL_STATIC_DEPENDENCY_RESOLUTION_CHANGED")
        fd = core.open_host(pool, pin["resolved_path"])
        value = core.hash_fd(fd, 512 * 1024 * 1024, min(end, time.monotonic() + 45))
        need(value == {key: pin[key] for key in ("bytes", "sha256", "file")}, "ACTUAL_STATIC_DEPENDENCY_BYTES_OR_STAT_CHANGED")
        rows["aapt2-static-" + str(index)] = {"pin": pin, "fd": fd, "observed": value}
        aliases.extend(item.get("resolved_needed", []))
        if item.get("resolved_interpreter") is not None:
            aliases.append(item["resolved_interpreter"])
    recheck_static_aliases(aliases, end)
    return aliases


def recheck_static_aliases(aliases, end):
    for pin in aliases:
        need(time.monotonic() < end, "DIAGNOSTIC_DEADLINE_BEFORE_ALIAS_RECHECK")
        need(str(Path(pin["declared_path"]).resolve()) == pin["resolved_path"], "ACTUAL_LOADER_ALIAS_CHANGED")


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def read_bootstrap(pin, limit):
    """Read a root-owned, no-symlink request/guard before loading its typed API."""
    need(type(pin) is dict and set(pin) <= {"path", "sha256", "bytes"} and {"path", "sha256"} <= set(pin), "PIN_SCHEMA")
    path = pin["path"]
    need(type(path) is str and path.startswith("/") and all(x not in ("", ".", "..") for x in path[1:].split("/")), "ABSOLUTE_CANONICAL_PATH")
    need(re.fullmatch(r"[0-9a-f]{64}", pin["sha256"]) is not None, "SHA256_REQUIRED")
    fds = []
    try:
        d = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC); fds.append(d)
        parts = path[1:].split("/")
        for part in parts[:-1]:
            d = os.open(part, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=d); fds.append(d)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=d); fds.append(fd)
        a = os.fstat(fd)
        need(stat.S_ISREG(a.st_mode) and a.st_uid == 0 and a.st_nlink == 1 and 0 < a.st_size <= limit, "PINNED_ROOT_FILE_BOUND")
        raw, end = bytearray(), time.monotonic() + 10
        while len(raw) <= limit:
            need(time.monotonic() < end, "BOOTSTRAP_READ_DEADLINE")
            part = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        again = os.open(parts[-1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=d); fds.append(again)
        need(len(raw) == a.st_size and all(getattr(a, k) == getattr(os.fstat(fd), k) == getattr(os.fstat(again), k) for k in STAT), "BOOTSTRAP_FILE_CHANGED")
        need(sha(raw) == pin["sha256"] and ("bytes" not in pin or len(raw) == pin["bytes"]), "BOOTSTRAP_PIN_CHANGED")
        return bytes(raw)
    finally:
        errors = []
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError:
                errors.append(fd)
        need(not errors, "BOOTSTRAP_FD_CLOSE_FAILED")


class Store:
    def __init__(self, core, pool, path):
        core.path_parts(path)
        need(path.startswith(OUTPUT_PREFIX) and path.count("/") == 4, "NEW_AUDIT_OUTPUT_REQUIRED")
        self.core, self.pool, self.path = core, pool, path
        parent = core.open_host(pool, str(Path(path).parent), os.O_PATH | os.O_DIRECTORY)
        try:
            os.mkdir(Path(path).name, 0o700, dir_fd=parent)
            self.fd = pool.own(os.open(Path(path).name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent))
        finally:
            pool.close(parent)
        self.identity = core.metadata(self.fd)
        need(self.identity["st_uid"] == 0 and stat.S_IMODE(self.identity["st_mode"]) == 0o700, "ROOT_PRIVATE_OUTPUT_REQUIRED")

    def write(self, name, raw):
        need(re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", name) and name not in (".", ".."), "OUTPUT_NAME")
        fd = self.pool.own(os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400, dir_fd=self.fd))
        try:
            view = memoryview(raw)
            while view:
                count = os.write(fd, view); need(count > 0, "OUTPUT_WRITE_PROGRESS"); view = view[count:]
            os.fsync(fd)
        finally:
            self.pool.close(fd)
        os.fsync(self.fd)
        pin = {"path": self.path + "/" + name, "bytes": len(raw), "sha256": sha(raw)}
        need(self.core.pinned_record(pin, max(1, len(raw))) == raw, "DURABLE_OUTPUT_READBACK")
        return pin


def bind_tools(core, pool, end, candidate):
    deps = core.parse(core.pinned_record(DEPS, 262144))
    files = deps["files"]
    need(type(files) is dict and {"java", "apksigner_jar", "aapt"} <= set(files) and 3 <= len(files) <= 32, "FIXED_EXISTING_TOOL_CLOSURE")
    rows = {}
    for name, pin in files.items():
        need(type(name) is str and re.fullmatch(r"[A-Za-z0-9_.-]+", name), "DEPENDENCY_NAME")
        need(str(Path(pin["declared_path"]).resolve()) == pin["resolved_path"], "DEPENDENCY_RESOLUTION_CHANGED")
        fd = core.open_host(pool, pin["resolved_path"])
        value = core.hash_fd(fd, 512 * 1024 * 1024, min(end, time.monotonic() + 45))
        need(value["bytes"] == pin["bytes"] and value["sha256"] == pin["sha256"], "DEPENDENCY_BYTES_CHANGED")
        rows[name] = {"pin": pin, "fd": fd, "observed": value}
    need("aapt2" not in rows, "FIXED_DEPENDENCIES_ALREADY_DECLARE_AAPT2")
    fd = core.open_host(pool, candidate["path"])
    observed = core.hash_fd(fd, 64 * 1024 * 1024, min(end, time.monotonic() + 45))
    need(observed == {key: candidate[key] for key in ("bytes", "sha256", "file")}, "ACTUAL_CANDIDATE_BYTES_OR_IDENTITY_CHANGED")
    rows["aapt2"] = {"pin": {"declared_path": candidate["path"], "resolved_path": candidate["path"],
                              "bytes": candidate["bytes"], "sha256": candidate["sha256"]},
                     "fd": fd, "observed": observed}
    return rows


def recheck_tools(core, pool, rows, end, full):
    core.pinned_record(DEPS, 262144)
    for row in rows.values():
        need(time.monotonic() < end, "DIAGNOSTIC_DEADLINE_BEFORE_TOOL_RECHECK")
        pin, expected, fd = row["pin"], row["observed"], row["fd"]
        need(str(Path(pin["declared_path"]).resolve()) == pin["resolved_path"] and core.metadata(fd) == expected["file"], "HELD_TOOL_OR_RESOLUTION_CHANGED")
        current = core.open_host(pool, pin["resolved_path"])
        try:
            need(core.metadata(current) == expected["file"], "TOOL_PATH_CHANGED")
        finally:
            pool.close(current)
        if full:
            need(core.hash_fd(fd, 512 * 1024 * 1024, min(end, time.monotonic() + 45)) == expected, "TOOL_BYTES_CHANGED_AFTER_AUDIT")


def run_tool(argv, pass_fds, receipt, end):
    """Bounded host child; retire only its own process group and keep raw output."""
    receipt.update(argv=argv, started_utc=now(), spawned=False, joined=False, timed_out=False,
                   output_capture_complete=False, automatic_retry=False, pipes_closed=False)
    proc, sel = None, selectors.DefaultSelector()
    streams, output = [], {"stdout": bytearray(), "stderr": bytearray()}
    deadline, killed = min(end, time.monotonic() + 90), False
    failure = None
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                pass_fds=tuple(pass_fds), close_fds=True, start_new_session=True, env=ENV)
        receipt.update(spawned=True, pid=proc.pid)
        streams = [proc.stdout, proc.stderr]
        for name, stream in zip(("stdout", "stderr"), streams):
            os.set_blocking(stream.fileno(), False); sel.register(stream, selectors.EVENT_READ, name)
        while sel.get_map():
            if time.monotonic() >= deadline:
                receipt["timed_out"] = True
                break
            for key, unused in sel.select(min(.2, max(0, deadline - time.monotonic()))):
                part = os.read(key.fileobj.fileno(), 65536)
                if not part:
                    sel.unregister(key.fileobj)
                    continue
                room = MAX_TOOL_OUTPUT - len(output[key.data])
                output[key.data].extend(part[:room])
                if len(part) > room:
                    receipt["output_truncated"] = True
                    raise RuntimeError("TOOL_OUTPUT_BOUND")
        if receipt["timed_out"]:
            os.killpg(proc.pid, signal.SIGKILL); killed = True
        proc.wait(timeout=5)
        receipt.update(joined=True, returncode=proc.returncode, output_capture_complete=not bool(sel.get_map()))
    except BaseException as error:
        failure = error
        receipt["error"] = {"type": type(error).__name__, "reason": str(error)[:160]}
    finally:
        try:
            if proc is not None and (proc.poll() is None or failure is not None):
                try:
                    os.killpg(proc.pid, signal.SIGKILL); killed = True
                except ProcessLookupError:
                    pass
                proc.wait(timeout=5)
            if proc is not None:
                receipt.update(joined=proc.poll() is not None, returncode=proc.returncode)
        except BaseException as error:
            receipt["retirement_error"] = {"type": type(error).__name__, "reason": str(error)[:160]}
        finally:
            for stream in streams:
                stream.close()
            sel.close()
            receipt.update(ended_utc=now(), own_group_kill_requested=killed, pipes_closed=all(x.closed for x in streams))
    return {key: bytes(value) for key, value in output.items()}


def badging_manifest(raw):
    text = raw.decode("utf-8", "strict")
    lines = [line for line in text.splitlines() if line.startswith("package: ")]
    need(len(lines) == 1, "UNIQUE_AAPT_PACKAGE_LINE")
    attrs, at = {}, len("package:")
    while at < len(lines[0]):
        match = re.match(r"\s+([A-Za-z][A-Za-z0-9_-]*)='([^']*)'", lines[0][at:])
        need(match is not None and match[1] not in attrs, "BADGING_ATTRIBUTE_UNPARSED_OR_DUPLICATE")
        attrs[match[1]] = match[2]
        at += match.end()
    need("name" in attrs and attrs.get("versionCode", "").isdigit(), "AAPT_PACKAGE_VERSION_REQUIRED")
    value = {"package": attrs["name"], "version_code": int(attrs["versionCode"]), "version_name": attrs.get("versionName"),
             "split_name": attrs.get("split"), "package_line_raw": lines[0]}
    for name, prefixes in (("min_sdk", ("sdkVersion:", "minSdkVersion:")),
                           ("target_sdk", ("targetSdkVersion:",)), ("max_sdk", ("maxSdkVersion:",))):
        found = [line for line in text.splitlines() if line.startswith(prefixes)]
        need(len(found) <= 1, "AMBIGUOUS_AAPT_SDK")
        if found:
            parsed = re.fullmatch(r"(?:sdkVersion|minSdkVersion|targetSdkVersion|maxSdkVersion):'([^']+)'", found[0])
            need(parsed is not None, "MALFORMED_AAPT_SDK_LINE")
            value[name] = parsed[1]
        else:
            value[name] = None
    native = [line for line in text.splitlines() if line.startswith("native-code:")]
    need(len(native) <= 1, "AMBIGUOUS_AAPT_ABI")
    value["native_abis"] = re.findall(r"'([^']*)'", native[0]) if native else []
    value["native_abi_source"] = "aapt2_dump_badging_current_APK"
    value["version_code_major"] = int(attrs.get("versionCodeMajor", "0"))
    value["long_version_code"] = value["version_code"] | (value["version_code_major"] << 32)
    return value


def xml_permissions(raw):
    """Preserve raw typed attributes; undecodable names are never normalized."""
    entries, stack, current, manifest_seen = [], [], None, False
    tags = {"uses-permission", "uses-permission-sdk-23", "uses-permission-sdk-m", "permission", "permission-group", "permission-tree"}
    for line in raw.decode("utf-8", "strict").splitlines():
        event = re.match(r"^(\s*)E: ([A-Za-z0-9_.:-]+)(?:\s|$)", line)
        if event:
            indent, tag = len(event[1]), event[2]
            while stack and stack[-1][0] >= indent:
                stack.pop()
            parent = stack[-1][1] if stack else None
            stack.append((indent, tag))
            manifest_seen |= tag == "manifest" and parent is None
            current = None
            if tag in tags and parent == "manifest":
                current = {"tag": tag, "attributes": {}, "name": None, "raw_name_preserved": True}
                entries.append(current)
                need(len(entries) <= 2048, "MANIFEST_PERMISSION_COUNT_BOUND")
            continue
        attr = re.match(r"^\s+A: ([A-Za-z0-9_.:-]+)(?:\(0x[0-9a-fA-F]+\))?=(.*)$", line)
        if attr and current is not None:
            key, value = attr[1], attr[2]
            need(key not in current["attributes"], "DUPLICATE_PERMISSION_ATTRIBUTE")
            current["attributes"][key] = value
            if key == "android:name":
                literal = re.match(r'^("(?:[^"\\]|\\.)*")(?:\s|$)', value)
                if literal:
                    try:
                        current["name"] = json.loads(literal[1])
                    except (ValueError, TypeError):
                        pass
    need(manifest_seen, "AAPT_XML_MANIFEST_ROOT_REQUIRED")
    return {"entries": entries, "all_names_decoded": all(x["name"] is not None for x in entries),
            "effective_permission_grants": "UNKNOWN_NOT_QUERIED", "declared_manifest_only": True}


def parse_signature(raw, command):
    text = raw.decode("utf-8", "strict")
    certs = re.findall(r"^Signer #\d+ certificate SHA-256 digest: ([0-9a-fA-F]{64})$", text, re.M)
    certs = sorted(value.lower() for value in certs)
    verified = bool(command.get("returncode") == 0 and command.get("joined") and command.get("output_capture_complete") and not command.get("timed_out") and certs and len(certs) == len(set(certs)))
    schemes = {match[1]: match[2] == "true" for match in re.finditer(r"^Verified using (.*): (true|false)$", text, re.M)}
    return {"cryptographic_verification_performed": True, "verified": verified,
            "signer_certificate_sha256": certs, "schemes": schemes,
            "API_minimum_override_used": False, "integrity_check_bypassed": False}


def verify_official_host_proof(raw_stdout, terminal_raw):
    """Require final original stdout and its actual durable successful job."""
    terminal = json.loads(terminal_raw)
    need(terminal.get("job_id") == OFFICIAL_HOST_JOB and terminal.get("state") == "succeeded" and
         terminal.get("exit_code") == 0 and
         all(terminal.get(key) is True for key in ("output_complete", "output_durable", "terminal_publication_confirmed")) and
         all(terminal.get(key) is False for key in ("automatic_retry", "timed_out", "cancelled")) and
         terminal.get("log_truncated") == {"stdout": False, "stderr": False} and
         terminal.get("log_errors") == {"stdout": None, "stderr": None} and
         terminal.get("log_synced") == {"stdout": True, "stderr": True}, "ACTUAL_OFFICIAL_HOST_DURABLE_SUCCESS_REQUIRED")
    lines = raw_stdout.splitlines()
    need(len(lines) == 2, "EXACT_ORIGINAL_OFFICIAL_HOST_STDOUT")
    stage, envelope = (json.loads(line) for line in lines)
    need(stage.get("schema") == "pocket4-official-aapt2-host-source-stage-result-v1" and
         stage.get("source_stage_ok") is True and stage.get("worker_about_to_exec_once") is True and
         stage.get("source_root") == str(Path(OFFICIAL_HOST_SOURCE["path"]).parent) and
         stage.get("files") == [{"name": "prepare_official_aapt2.py", "bytes": OFFICIAL_HOST_SOURCE["bytes"],
                                 "sha256": OFFICIAL_HOST_SOURCE["sha256"]}], "ACTUAL_OFFICIAL_SOURCE_STAGE_CHANGED")
    need(set(envelope) == {"encoding", "artifact_bytes", "artifact_sha256", "data"} and
         envelope["encoding"] == "zlib-base64" and envelope["artifact_bytes"] == 34091 and
         envelope["artifact_sha256"] == "b827c080d7af767cab60fbd9a682eafd8dfe06d6f4375b23f62988212a4b908e",
         "EXACT_OFFICIAL_FINAL_WORKER_ENVELOPE_REQUIRED")
    compressed = base64.b64decode(envelope["data"], validate=True)
    need(len(compressed) <= 131072, "OFFICIAL_HOST_COMPRESSED_BOUND")
    inflater = zlib.decompressobj()
    raw = inflater.decompress(compressed, 131073)
    need(inflater.eof and not inflater.unused_data and not inflater.unconsumed_tail and
         len(raw) == envelope["artifact_bytes"] and sha(raw) == envelope["artifact_sha256"],
         "OFFICIAL_FINAL_WORKER_BYTES_CHANGED")
    proof = json.loads(raw)
    need(proof.get("schema") == "pocket4-official-aapt2-extraction-elf-version-v1" and proof.get("ok") is True and
         proof.get("errors") == [] and proof.get("status") == "OFFICIAL_HOST_TOOL_EXTRACTED_BOUND_AND_VERSION_OBSERVED" and
         proof.get("source") == OFFICIAL_HOST_SOURCE and proof.get("official_version") == "9.5.1-16666295" and
         all(proof.get(key) is True for key in ("official_jar_and_extracted_tool_unchanged", "all_bound_host_files_unchanged",
             "all_owned_tool_children_joined", "original_descriptor_identities_restored")) and
         proof.get("process_FDs_before") == proof.get("process_FDs_after") == 3, "OFFICIAL_HOST_FINAL_RETIREMENT_OR_IDENTITY_REQUIRED")
    candidate = proof.get("candidate", {})
    need(candidate.get("declared_path") == candidate.get("resolved_path") == OFFICIAL_CANDIDATE["path"] and
         all(candidate.get(key) == OFFICIAL_CANDIDATE[key] for key in ("bytes", "sha256", "file")),
         "EXACT_OFFICIAL_CANDIDATE_FILE_AND_STAT_REQUIRED")
    need(all(type(proof.get(key)) is int and proof[key] == 0 for key in
         ("APK_reads", "APK_tool_inputs", "Android_commands", "App_launches", "Main_reads", "UI_actions", "installs",
          "namespace_entries", "native_commands", "permission_changes", "new_network_requests")) and
         proof.get("action_lock_acquired") is False and proof.get("existing_files_modified") is False and
         proof.get("original_failed_audits_reclassified") is False, "OFFICIAL_HOST_ACTION_BOUNDARY_CHANGED")
    need(proof["extraction"]["source_jar_sha256"] == "fa1014cb1431622d292ef55ba870e75882ea19987bec541698b912f446a2d08f" and
         proof["extraction"]["member_crc_checked_by_complete_ZipExtFile_read"] is True and
         proof["extraction"]["other_members_extracted"] is False, "OFFICIAL_JAR_EXTRACTION_EVIDENCE_REQUIRED")
    commands = proof.get("commands")
    need(type(commands) is list and len(commands) == proof.get("candidate_executions") == 1, "EXACT_ORIGINAL_VERSION_ONCE")
    command = commands[0]
    need(command.get("argv") == [OFFICIAL_CANDIDATE["path"], "version"] and command.get("returncode") == 0 and
         all(command.get(key) is True for key in ("joined", "pipes_closed", "output_capture_complete")) and
         all(command.get(key) is False for key in ("timed_out", "own_group_kill_requested")) and
         not command.get("error") and not command.get("retirement_error"), "OFFICIAL_VERSION_CHILD_DID_NOT_SETTLE_NORMALLY")
    for stream in ("stdout", "stderr"):
        original = bytes.fromhex(command[stream + "_original_hex"])
        need(len(original) == command[stream]["bytes"] and sha(original) == command[stream]["sha256"], "OFFICIAL_VERSION_RAW_STREAM_PIN")
    need(proof.get("version_original") == "Android Asset Packaging Tool (aapt) 2.20-16666295\n", "ACTUAL_OFFICIAL_VERSION_OUTPUT")
    graph = proof.get("static_dependency_graph")
    need(type(graph) is list and len(graph) == proof.get("static_dependency_file_count") == 7 and
         len({row["file"]["resolved_path"] for row in graph}) == 7 and
         all(row["static_elf"]["additional_loader_directives"] == [] for row in graph), "EXACT_OFFICIAL_SEVEN_FILE_STATIC_GRAPH")
    layout = proof["controlled_runpath_layout"]
    need(layout["output_root"] == OFFICIAL_TOOL_ROOT and
         layout["owned_directory_descriptors"] == {"acquired": 11, "closed": 11, "errors": [],
             "evidence_store_descriptor_borrowed_not_closed_here": True} and
         [row["stage"] for row in layout["observations"]] == ["before_system_dependency_resolution", "immediately_before_version",
             "after_version_and_final_file_recheck"] and
         all(row["complete"] is True and row["all_five_search_directories_and_thirty_candidates_proved"] is True
             for row in layout["observations"]), "OFFICIAL_CONTROLLED_LAYOUT_PROOF_INCOMPLETE")
    need(all(row["directories"] == layout["observations"][0]["directories"] for row in layout["observations"]),
         "OFFICIAL_PRIVATE_DIRECTORY_PROOF_CHANGED")
    return proof


def bind_existing_official_layout(core, pool, end, result, proof):
    """Read-only adapter for the already proved exact host layout verifier."""
    raw = core.pinned_record(OFFICIAL_HOST_SOURCE, 131072)
    host = types.ModuleType("pinned_official_aapt2_host_layout_definitions")
    host.__file__ = OFFICIAL_HOST_SOURCE["path"]
    exec(compile(raw, host.__file__, "exec"), host.__dict__)
    reader = host.frozen_module(host.READER_SOURCE, host.READER_SHA, "original_readonly_layout_reader")
    record = {"host_source": OFFICIAL_HOST_SOURCE, "prior_host_job": OFFICIAL_HOST_JOB,
              "existing_directories_only": True, "new_directories_created": False,
              "root_identity_source": "fresh read-only binding; seven child directory full stats equal prior actual host proof"}
    result["official_private_layout"] = record
    layout = host.ControlledRunpathLayout(reader, record)
    try:
        need(host.OUTPUT == OFFICIAL_TOOL_ROOT, "EXACT_OFFICIAL_LAYOUT_SOURCE_ROOT")
        # The original class borrows this descriptor. Its own anchor/children
        # close through the original class; this one closes through core.pool.
        root_fd = core.open_host(pool, OFFICIAL_TOOL_ROOT, os.O_RDONLY | os.O_DIRECTORY)
        layout.store = types.SimpleNamespace(fd=root_fd, written=proof["new_evidence_files"] + [proof["inner_receipt"]])
        layout.anchor = reader.HeldPath(OFFICIAL_TOOL_ROOT)
        layout.anchor.open()
        need(layout.anchor.fd is not None and reader.metadata(layout.anchor.fd) == reader.metadata(root_fd),
             "EXISTING_OFFICIAL_ROOT_FULL_PATH_REQUIRED")
        previous_parents = proof["controlled_runpath_layout"]["ancestors_after_new_output"]
        need([row["path"] for row in layout.anchor.parents] == [row["path"] for row in previous_parents], "OFFICIAL_ANCESTOR_PATHS_CHANGED")
        for current, previous in zip(layout.anchor.parents, previous_parents):
            value = host.require_secure_directory(reader, current["fd"])
            need(all(value[key] == previous["stat"][key] for key in ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode")),
                 "OFFICIAL_ANCESTOR_IDENTITY_OR_OWNER_CHANGED")
        layout.root_stat = host.require_secure_directory(reader, root_fd, True)
        record["fresh_held_root_stat"] = layout.root_stat
        previous = proof["controlled_runpath_layout"]["observations"][-1]["directories"]
        need([row["path"] for row in previous] == [OFFICIAL_TOOL_ROOT + "/" + name for name in host.ControlledRunpathLayout.CONTENTS],
             "EXACT_SEVEN_PREVIOUS_DIRECTORY_PATHS")
        for row in previous:
            need(time.monotonic() < end, "OFFICIAL_DIRECTORY_REBIND_DEADLINE")
            relative = row["path"][len(OFFICIAL_TOOL_ROOT) + 1:]
            prefix, unused, leaf = relative.rpartition("/")
            parent = root_fd if not prefix else layout.directories[prefix]
            descriptor = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            layout.directories[relative] = descriptor
            need(host.require_secure_directory(reader, descriptor, True) == row["stat"], "OFFICIAL_PRIVATE_DIRECTORY_FULL_STAT_CHANGED")
            layout.directory_stats[relative] = row["stat"]
        layout.verify("fresh_readonly_rebind_before_APK_tools", end)
        return layout
    except BaseException:
        layout.close()
        raise


def add_official_tool_binding(core, pool, tools, end, proof):
    need("aapt2" in tools and "legacy-aapt2" not in tools, "LEGACY_BINDING_MUST_REMAIN")
    tools["legacy-aapt2"] = tools.pop("aapt2")
    candidate = OFFICIAL_CANDIDATE
    fd = core.open_host(pool, candidate["path"])
    value = core.hash_fd(fd, 64 * 1024 * 1024, min(end, time.monotonic() + 45))
    need(value == {key: candidate[key] for key in ("bytes", "sha256", "file")}, "OFFICIAL_TOOL_FULL_BYTES_OR_IDENTITY_CHANGED")
    tools["aapt2"] = {"pin": {"declared_path": candidate["path"], "resolved_path": candidate["path"],
                               "bytes": candidate["bytes"], "sha256": candidate["sha256"]}, "fd": fd, "observed": value}
    additional = {}
    aliases = bind_static_dependencies(core, pool, additional, end, proof)
    for name, row in additional.items():
        key = "official-" + name
        need(key not in tools, "OFFICIAL_STATIC_BINDINGS_MUST_NOT_REPLACE_LEGACY")
        tools[key] = row
    return aliases


def all_apk_evidence_verified(result, packages):
    """Complete evidence includes each current signer matching the actual PM record."""
    fields = ("complete_APK_set_observed", "one_base_manifest_observed",
              "all_APKs_signature_verified", "all_current_signers_equal_PM_records",
              "all_manifests_match_PM_identity", "all_permission_names_decoded")
    return bool(result.get("snapshot_consistent") is True and result.get("all_commands_succeeded") is True
                and len(result.get("apps", [])) == len(packages) > 0 and not result.get("errors")
                and all(all(row.get(field) is True for field in fields) for row in result["apps"]))


def validate_scope_qualification(outer_raw, terminal_raw, validator):
    """Require the actual identity-only 48-scope joint; it is not APK signature evidence."""
    need(len(outer_raw.splitlines()) == 2, "EXACT_SCOPE_STAGE_AND_OUTER_STREAM")
    stage, outer = [json.loads(line) for line in outer_raw.splitlines()]
    terminal = json.loads(terminal_raw)
    need(terminal.get("job_id") == SCOPE_JOB and terminal.get("state") == "succeeded" and
         type(terminal.get("exit_code")) is int and terminal["exit_code"] == 0 and
         all(terminal.get(key) is True for key in ("output_complete", "output_durable", "terminal_publication_confirmed")) and
         all(terminal.get(key) is False for key in ("automatic_retry", "timed_out", "cancelled")),
         "ACTUAL_SCOPE_DURABLE_NORMAL_SUCCESS_REQUIRED")
    need(terminal.get("log_bytes") == {"stdout": {"seen": len(outer_raw), "stored": len(outer_raw)},
                                      "stderr": {"seen": 0, "stored": 0}} and
         terminal.get("log_truncated") == {"stdout": False, "stderr": False} and
         terminal.get("log_errors") == {"stdout": None, "stderr": None} and
         terminal.get("log_synced") == {"stdout": True, "stderr": True}, "ACTUAL_SCOPE_COMPLETE_ORIGINAL_STREAMS")
    need(stage.get("schema") == "pocket4-explicit48-owned-scope-source-stage-result-v1" and stage.get("source_stage_ok") is True and
         stage.get("source_root") == SCOPE_STAGE and stage.get("bootstrap_FDs_before") == stage.get("bootstrap_FDs_after") and
         all(type(stage.get(key)) is int and stage[key] == 0 for key in
             ("stage_Main_reads", "stage_UI_actions", "stage_installs", "stage_namespace_entries")), "ACTUAL_SCOPE_SOURCE_STAGE")
    need(validator.CONFIG["kind"] == "explicit48" and validator.CONFIG["stage_root"] == SCOPE_STAGE,
         "PINNED_ACTUAL_SCOPE_VALIDATOR")
    need(outer.get("schema") == "pocket4-owned-readonly-observation-result-v1" and outer.get("ok") is True and
         outer.get("status") == "READONLY_OBSERVATION_AND_OWNED_LIFETIME_VERIFIED" and outer.get("kind") == "explicit48" and
         outer.get("errors") == [] and outer.get("automatic_retry") is False and outer.get("production_ready") is False and
         outer.get("inner_result_alone_qualifies") is False and outer.get("old_results_reclassified") is False and
         outer.get("library_FD_retired_by_original_held_owned_child_exit") is True and
         all(type(outer.get(key)) is int and outer[key] == 0 for key in ("UI_actions", "installs", "permission_changes")),
         "ACTUAL_SCOPE_OWNED_OUTER_GATE")
    child = outer["child_result"]
    need(validator.combined(outer["child_lifecycle"], child, b"") and outer["child_stderr"]["bytes"] == 0 and
         outer["child_stderr"]["sha256"] == sha(b"") and child.get("worker_invoked") is True and
         child.get("manual_library_FD_close") is False and child.get("unknown_FDs_closed") == 0 and
         child["frozen_descriptors_before_worker"] == child["frozen_descriptors_after_worker"] == child["final_descriptors"],
         "ACTUAL_SCOPE_OWNED_NORMAL_EXIT_AND_FDS")
    worker_raw = child["worker_stdout_original"].encode("utf-8")
    need(len(worker_raw) == child["worker_stdout_bytes"] == outer["worker_stdout"]["bytes"] and
         sha(worker_raw) == child["worker_stdout_sha256"] == outer["worker_stdout"]["sha256"], "ACTUAL_SCOPE_WORKER_STREAM_PIN")
    observed = validator.decode_worker(worker_raw)
    validator.worker_gate(observed, child["worker_returncode"])
    need(observed["observation"]["app_scope"] == ACTUAL_SCOPE and observed["packages"] == PROTECTED_PACKAGES and
         observed["package_count"] == 48 and observed["new_signature_verification_performed"] is False and
         observed["UI_or_install_admitted"] is False and observed["original_47_unchanged"] is True and
         observed["new_package_matches_actual_discovery"] is True, "EXACT_IDENTITY_ONLY_SCOPE_48")
    return {"job_id": SCOPE_JOB, "scope": ACTUAL_SCOPE, "outer": SCOPE_STDOUT, "terminal": SCOPE_TERMINAL,
            "validator": SCOPE_VALIDATOR, "normal_owned_joint_validated": True,
            "scope_is_signature_evidence": False, "scope_is_UI_or_install_admission": False}


def ndk_xml_root(raw, expected):
    """Read the current signed APK's actual XML root, preserving all typed attributes."""
    text = raw.decode("utf-8", "strict")
    lines = text.splitlines()
    need(lines and lines[0] == "N: android=http://schemas.android.com/apk/res/android",
         "NDK_XML_ANDROID_NAMESPACE_REQUIRED")
    roots = [i for i, line in enumerate(lines) if re.fullmatch(r"  E: manifest \(line=[0-9]+\)", line)]
    need(roots == [1], "ONE_COMPLETE_NDK_XML_MANIFEST_ROOT_REQUIRED")
    attributes = {}
    child_seen = False
    for line in lines[2:]:
        if re.fullmatch(r"    E: [A-Za-z0-9_.:-]+ \(line=[0-9]+\)", line):
            child_seen = True
            break
        match = re.fullmatch(r"    A: ([A-Za-z0-9_.:-]+)(?:\(0x[0-9a-fA-F]+\))?=(.*)", line)
        need(match is not None and match[1] not in attributes, "NDK_XML_ROOT_ATTRIBUTE_UNPARSED_OR_DUPLICATE")
        attributes[match[1]] = match[2]
    need(child_seen, "COMPLETE_ROOT_ATTRIBUTE_BLOCK_MUST_END_AT_OBSERVED_CHILD")
    value = attributes.get("package")
    literal = re.fullmatch(r'("(?:[^"\\]|\\.)*") \(Raw: ("(?:[^"\\]|\\.)*")\)', value or "")
    need(literal is not None and json.loads(literal[1]) == json.loads(literal[2]) == expected["package"],
         "CURRENT_XML_PACKAGE_MUST_MATCH_FIXED_SCOPE")
    names = ("android:versionCode", "android:versionCodeMajor", "android:versionName")
    return {"stream": {"bytes": len(raw), "sha256": sha(raw)}, "root_package": expected["package"],
            "root_attributes_original": attributes,
            "version_attribute_declarations": {key: attributes.get(key) for key in names},
            "all_three_version_attributes_absent": all(key not in attributes for key in names),
            "missing_or_partial_XML_accepted": False}


def ndk_manifest_with_observed_absence(raw, xml_raw, expected, apk, signature):
    """Use actual XML absence, normal cryptographic verification and the exact scoped APK.

    No manifest field is fabricated from PackageManager. Empty badging strings
    and absent declarations remain distinct from Android's effective default.
    The previous fixture package exception and its observed stream pins are not
    transferred to NDK. This new contract accepts only the frozen NDK identity.
    """
    need(expected == NDK_EXPECTED and expected["package"] == "com.example.ndk_tests" and
         type(expected["uid"]) is int and expected["uid"] == 10162 and expected["apks"] == [apk],
         "ONLY_EXACT_FRESH_SCOPED_NDK_IDENTITY")
    need(signature is not None and signature.get("verified") is True and
         signature.get("cryptographic_verification_performed") is True and
         signature.get("API_minimum_override_used") is False and signature.get("integrity_check_bypassed") is False and
         signature.get("signer_certificate_sha256") == expected["package_manager_certificate_sha256"],
         "NORMAL_CURRENT_SIGNATURE_MATCHING_PM_REQUIRED")
    root = ndk_xml_root(xml_raw, expected)
    text = raw.decode("utf-8", "strict")
    lines = [line for line in text.splitlines() if line.startswith("package: ")]
    need(len(lines) == 1, "UNIQUE_AAPT_PACKAGE_LINE")
    attrs, at = {}, len("package:")
    while at < len(lines[0]):
        match = re.match(r"\s+([A-Za-z][A-Za-z0-9_-]*)='([^']*)'", lines[0][at:])
        need(match is not None and match[1] not in attrs, "BADGING_ATTRIBUTE_UNPARSED_OR_DUPLICATE")
        attrs[match[1]] = match[2]
        at += match.end()
    need(attrs.get("name") == expected["package"] and "split" not in attrs, "FIXED_NDK_BASE_PACKAGE_REQUIRED")
    if attrs.get("versionCode", "").isdigit():
        value = badging_manifest(raw)
        value["xml_root_observation"] = root
        value["version_default_applied_by_this_adapter"] = False
        return value
    need(type(expected["version_code"]) is int and expected["version_code"] == 0 and
         attrs.get("versionCode") == "" and attrs.get("versionName") == "" and "versionCodeMajor" not in attrs and
         root["all_three_version_attributes_absent"] is True,
         "ACTUAL_EMPTY_BADGING_AND_COMPLETE_XML_ABSENCE_REQUIRED_FOR_DEFAULT_ZERO")
    value = {"package": expected["package"], "version_code": None, "version_code_major": None, "version_name": None,
             "version_code_raw": attrs["versionCode"], "version_name_raw": attrs["versionName"],
             "split_name": None, "package_line_raw": lines[0], "long_version_code": 0,
             "effective_version_code_source": "ANDROID_ABSENT_ATTRIBUTE_DEFAULT_CONFIRMED_BY_CURRENT_XML_AND_PM_ZERO",
             "version_default_applied_by_this_adapter": True, "xml_root_observation": root,
             "version_default_evidence": {"schema": "pocket4-current-signed-ndk-absent-version-evidence-v1",
                 "badging_stream": {"bytes": len(raw), "sha256": sha(raw)}, "xml_root": root,
                 "fixed_APK_sha256": apk["sha256"], "fixed_PM_version_code": 0,
                 "fresh_normal_signature_matches_fixed_PM": True, "declared_version_name_invented": False,
                 "historical_fixture_exception_inherited": False,
                 "Android_parser_reference": ANDROID_VERSION_DEFAULT_REFERENCE}}
    # Identical SDK/ABI extraction to the already proven generic parser.
    for name, prefixes in (("min_sdk", ("sdkVersion:", "minSdkVersion:")),
                           ("target_sdk", ("targetSdkVersion:",)), ("max_sdk", ("maxSdkVersion:",))):
        found = [line for line in text.splitlines() if line.startswith(prefixes)]
        need(len(found) <= 1, "AMBIGUOUS_AAPT_SDK")
        if found:
            parsed = re.fullmatch(r"(?:sdkVersion|minSdkVersion|targetSdkVersion|maxSdkVersion):'([^']+)'", found[0])
            need(parsed is not None, "MALFORMED_AAPT_SDK_LINE")
            value[name] = parsed[1]
        else:
            value[name] = None
    native = [line for line in text.splitlines() if line.startswith("native-code:")]
    need(len(native) <= 1, "AMBIGUOUS_AAPT_ABI")
    value["native_abis"] = re.findall(r"'([^']*)'", native[0]) if native else []
    value["native_abi_source"] = "aapt2_dump_badging_current_APK"
    return value


def clean_official_badging_observations(result):
    badging = [row for row in result["commands"] if row.get("name") == "badging"]
    expected = [(app["package"], apk["path"]) for app in result["apps"] for apk in app["apks"]]
    return bool(len(expected) == 1 and [(row.get("package"), row.get("apk_path")) for row in badging] == expected and
                all(row.get("returncode") == 0 and row.get("output_capture_complete") is True and
                    row.get("stderr", {}).get("bytes") == 0 and row.get("stderr", {}).get("sha256") ==
                    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" for row in badging))


def validate_request(request):
    need(set(request) == {"schema", "guard", "app_scope", "packages", "protected_packages", "output_root", "official_release_assets",
                          "legacy_candidate_aapt2", "legacy_candidate_inventory", "legacy_candidate_proof", "legacy_candidate_terminal",
                          "official_candidate_aapt2", "official_host_stdout", "official_host_terminal",
                          "scope_joint_stdout", "scope_terminal", "scope_validator"}, "CLOSED_INDEPENDENT_NDK_AUDIT_REQUEST")
    need(request["schema"] == "pocket4-ndk-current-apk-signature-metadata-request-v1" and
         request["guard"] == ACTUAL_GUARD and request["app_scope"] == ACTUAL_SCOPE and
         request["packages"] == [NDK_EXPECTED["package"]] and request["protected_packages"] == PROTECTED_PACKAGES and
         len(PROTECTED_PACKAGES) == len(set(PROTECTED_PACKAGES)) == 48 and
         request["output_root"] == OUTPUT_PREFIX and request["official_release_assets"] is None and
         request["scope_joint_stdout"] == SCOPE_STDOUT and request["scope_terminal"] == SCOPE_TERMINAL and
         request["scope_validator"] == SCOPE_VALIDATOR, "EXACT_CURRENT_48_PROTECTION_AND_ONE_NDK_AUDIT")
    validate_candidate(request["legacy_candidate_aapt2"])
    need(request["official_candidate_aapt2"] == OFFICIAL_CANDIDATE and request["official_host_stdout"] == OFFICIAL_HOST_STDOUT and
         request["official_host_terminal"] == OFFICIAL_HOST_TERMINAL, "EXACT_ACTUAL_OFFICIAL_TOOL_PROOF_REQUEST")
    need(request["legacy_candidate_proof"] == ACTUAL_PROOF and request["legacy_candidate_terminal"] == ACTUAL_PROOF_TERMINAL and
         request["legacy_candidate_inventory"] == ACTUAL_INVENTORY, "EXACT_ACTUAL_PRIOR_TOOL_PROVENANCE")


def audit(request):
    validate_request(request)
    batch = {"APK_count": 1, "logical_APK_bytes": 1397258}
    need(os.getuid() == os.geteuid() == 0, "EXISTING_ROOT_AUTHORITY_REQUIRED")
    end = time.monotonic() + 840
    result = {"schema": "pocket4-independent-ndk-apk-signature-metadata-v1", "started_utc": now(),
        "packages": request["packages"], "protected_packages": PROTECTED_PACKAGES, "request": request,
        "original_failures_reclassified": False, "old_ledger_modified": False,
        "scope_claimed_as_signature_evidence": False, "vendor_artifact_source_trust": "UNKNOWN",
        "UI_or_install_admitted": False, "all_current_launcher_APKs_reaudited": False,
        "UI_actions": 0, "App_launches": 0, "permission_changes": 0, "installs": 0,
        "Android_namespace_commands": 0, "ADB_commands": 0, "business_data_content_reads": 0,
        "native_commands": 0, "new_scopes_published": 0,
        "automatic_retry": False, "production_ready": False, "snapshot_consistent": False,
        "effective_permission_grants": "UNKNOWN_NOT_QUERIED", "apps": [], "commands": [], "errors": []}
    raw = read_bootstrap(request["guard"], 65536)
    guard = types.ModuleType("pinned_successor_apk_audit_guard"); guard.__file__ = request["guard"]["path"]
    exec(compile(raw, guard.__file__, "exec"), guard.__dict__)
    core = guard._core()
    pool, store, lock, official_layout = core.FDs(), None, None, None
    try:
        lock, result["action_lock_identity"] = core.acquire_lock(pool, core.ACTION_LOCK)
        result["guard_before"] = guard.current_guard()
        need(result["guard_before"].get("schema") == "pocket4-successor-main-guard-v1", "ACTUAL_NEW_TYPED_GUARD_REQUIRED")
        baseline = guard.current_baseline()
        scope = core.parse(core.pinned_record(request["app_scope"]))
        need(scope.get("schema") == "pocket4-versioned-app-scope-v1" and
             scope.get("runtime_epoch_sha256") == baseline["runtime_epoch_sha256"] and
             sorted(scope["apps"]) == PROTECTED_PACKAGES and scope["apps"][NDK_EXPECTED["package"]] == NDK_EXPECTED,
             "EXACT_CURRENT_48_SCOPE_AND_DISCOVERED_NDK_ROW")
        result["scope_guard_before"] = guard.check_app_scope(request["app_scope"], PROTECTED_PACKAGES)
        scope_validator_raw = core.pinned_record(SCOPE_VALIDATOR)
        scope_validator = types.ModuleType("actual48_pure_qualification_validator"); scope_validator.__file__ = SCOPE_VALIDATOR["path"]
        exec(compile(scope_validator_raw, scope_validator.__file__, "exec"), scope_validator.__dict__)
        scope_stdout_raw = core.pinned_record(SCOPE_STDOUT)
        scope_terminal_raw = core.pinned_record(SCOPE_TERMINAL)
        result["scope_qualification"] = validate_scope_qualification(scope_stdout_raw, scope_terminal_raw, scope_validator)
        expected = {name: scope["apps"][name] for name in request["packages"]}
        proof_raw = core.pinned_record(request["legacy_candidate_proof"], 131072)
        terminal_raw = core.pinned_record(request["legacy_candidate_terminal"], 65536)
        proof = core.parse(proof_raw)
        result["actual_prior_host_proof"] = verify_actual_proof(proof, core.parse(terminal_raw), request["legacy_candidate_aapt2"])
        official_stdout_raw = core.pinned_record(request["official_host_stdout"], 131072)
        official_terminal_raw = core.pinned_record(request["official_host_terminal"], 65536)
        official_proof = verify_official_host_proof(official_stdout_raw, official_terminal_raw)
        result["official_host_qualification"] = {"job_id": OFFICIAL_HOST_JOB, "source": OFFICIAL_HOST_SOURCE,
            "candidate": OFFICIAL_CANDIDATE, "version": official_proof["version_original"],
            "static_graph_is_actual_loader_mapping_proof": False}
        inventory_raw = core.pinned_record(request["legacy_candidate_inventory"], 65536)
        result["actual_candidate_observation"] = verify_candidate_inventory(request["legacy_candidate_aapt2"], core.parse(inventory_raw))
        need(sum(len(row["apks"]) for row in expected.values()) == 1, "EXACT_ONE_CURRENT_NDK_APK")
        total = sum(apk["bytes"] for row in expected.values() for apk in row["apks"])
        need(total == 1397258 and 0 < total <= MAX_BATCH_BYTES, "FIXED_COMPLETE_NDK_APK_BYTE_COUNT")
        runtime = baseline["runtime"]
        binding = runtime["held"]["process_snapshot"]["binding"]
        held = core.HeldProcesses(pool, {name: row["host_pid"] for name, row in binding["processes"].items()})
        need(held.before["binding"] == binding, "SUCCESSOR_HELD_BINDING_CHANGED")
        core.verify_runtime(pool, held, runtime)
        core.app_scope(pool, held, request["packages"], expected, False)
        store = Store(core, pool, request["output_root"])
        result["request_artifact"] = store.write("request.json", canonical(request) + b"\n")
        result["collector_source"] = store.write("collector-source.py", core.host_read(str(Path(__file__).resolve()), 131072)[0])
        result["candidate_inventory_artifact"] = store.write("candidate-inventory.original.json", inventory_raw)
        result["scope_joint_artifact"] = store.write("scope48.stdout.original.jsonl", scope_stdout_raw)
        result["scope_terminal_artifact"] = store.write("scope48.terminal.original.json", scope_terminal_raw)
        result["candidate_proof_artifact"] = store.write("prior-host-proof.outer.original.json", proof_raw)
        result["candidate_terminal_artifact"] = store.write("prior-host-proof.terminal.original.json", terminal_raw)
        result["official_host_stdout_artifact"] = store.write("official-host.stdout.original.jsonl", official_stdout_raw)
        result["official_host_terminal_artifact"] = store.write("official-host.terminal.original.json", official_terminal_raw)
        tools = bind_tools(core, pool, end, request["legacy_candidate_aapt2"])
        aliases = bind_static_dependencies(core, pool, tools, end, proof)
        aliases += add_official_tool_binding(core, pool, tools, end, official_proof)
        official_layout = bind_existing_official_layout(core, pool, end, result, official_proof)
        result["legacy_static_dependency_file_count"] = len(proof["static_dependency_graph"])
        result["official_static_dependency_file_count"] = len(official_proof["static_dependency_graph"])
        result["tool_dependencies"] = DEPS
        result["tool_binding"] = {name: {"pin": row["pin"], "observed": row["observed"]} for name, row in tools.items()}
        releases = None
        if request["official_release_assets"] is not None:
            releases = core.parse(core.pinned_record(request["official_release_assets"], 262144))
            need(releases.get("schema") == "pocket4-published-release-apk-digests-v1", "RELEASE_ASSET_REFERENCE_SCHEMA")
        for pi, package in enumerate(request["packages"]):
            need(time.monotonic() < end, "BATCH_DEADLINE")
            row = expected[package]
            app = {"package": package, "uid": row["uid"], "PM_version_code": row["version_code"], "code_path": row["code_path"],
                   "PM_certificate_sha256": row["package_manager_certificate_sha256"], "data_directories": row["data_directories"], "apks": []}
            result["apps"].append(app)
            core.app_scope(pool, held, [package], {package: row}, False)
            for ai, apk in enumerate(row["apks"]):
                fd = pool.own(core.H.open_in_root(held.roots["android_init"], apk["path"], os.O_RDONLY | os.O_NOFOLLOW))
                try:
                    before = core.hash_fd(fd, MAX_APK, min(end, time.monotonic() + 60))
                    need(before == {key: apk[key] for key in ("bytes", "sha256", "file")}, "EXACT_SCOPED_APK_BYTES_OR_STAT_CHANGED")
                    core.check_path(pool, held.roots["android_init"], apk["path"], before["file"])
                    item = {"path": apk["path"], **before, "commands": [], "parse_errors": []}; app["apks"].append(item)
                    source = "/proc/self/fd/" + str(fd)
                    definitions = [
                        ("apksigner", [tools["java"]["pin"]["resolved_path"], "-Xmx256m", "-jar", tools["apksigner_jar"]["pin"]["resolved_path"], "verify", "--verbose", "--print-certs", source]),
                        ("badging", [tools["aapt2"]["pin"]["resolved_path"], "dump", "badging", source]),
                        ("manifest", [tools["aapt"]["pin"]["resolved_path"], "dump", "xmltree", source, "AndroidManifest.xml"])]
                    outputs = {}
                    for name, argv in definitions:
                        recheck_tools(core, pool, tools, end, False)
                        command = {"package": package, "apk_path": apk["path"], "name": name}
                        result["commands"].append(command); item["commands"].append(command)
                        recheck_static_aliases(aliases, end)
                        need(time.monotonic() + 5 < end, "DIAGNOSTIC_DEADLINE_BEFORE_CHILD_SPAWN")
                        official_layout.verify(f"before-p{pi:02d}-a{ai:02d}-{name}", end)
                        need(time.monotonic() + 5 < end, "OFFICIAL_LAYOUT_POSTCHECK_DEADLINE_BEFORE_SPAWN")
                        streams = run_tool(argv, (fd, tools["apksigner_jar"]["fd"]), command, end)
                        for kind, content in streams.items():
                            command[kind] = store.write(f"p{pi:02d}-a{ai:02d}-{name}.{kind}", content)
                        need(command.get("joined") is True and command.get("pipes_closed") is True, "TOOL_CHILD_RETIREMENT_NOT_PROVED")
                        need(command.get("output_capture_complete") is True and not command.get("timed_out") and not command.get("error") and not command.get("retirement_error"), "TOOL_OBSERVATION_INCOMPLETE")
                        recheck_static_aliases(aliases, end)
                        official_layout.verify(f"after-p{pi:02d}-a{ai:02d}-{name}", end)
                        outputs[name] = streams["stdout"]
                        recheck_tools(core, pool, tools, end, False)
                    for name, fn in (("signature", lambda: parse_signature(outputs["apksigner"], item["commands"][0])),
                                     ("manifest", lambda: ndk_manifest_with_observed_absence(outputs["badging"], outputs["manifest"], row, apk, item.get("signature"))),
                                     ("declared_permissions", lambda: xml_permissions(outputs["manifest"]))):
                        try:
                            item[name] = fn()
                        except (RuntimeError, UnicodeError, ValueError) as error:
                            item["parse_errors"].append({"field": name, "type": type(error).__name__, "reason": str(error)[:160]})
                    if "manifest" in item:
                        item["manifest_matches_PM_package_and_version"] = item["manifest"]["package"] == package and item["manifest"]["long_version_code"] == row["version_code"]
                    if "signature" in item:
                        item["signature"]["current_signers_equal_PM_certificate_record"] = item["signature"]["signer_certificate_sha256"] == sorted(row["package_manager_certificate_sha256"])
                    need(core.hash_fd(fd, MAX_APK, min(end, time.monotonic() + 60)) == before, "APK_BYTES_CHANGED_DURING_TOOLS")
                    core.check_path(pool, held.roots["android_init"], apk["path"], before["file"])
                    item["held_bytes_and_full_stat_and_path_unchanged"] = True
                    if releases is not None and package in ("com.google.android.gms", "org.fcitx.fcitx5.android"):
                        matches = [asset for asset in releases["assets"] if asset["package"] == package and asset["bytes"] == apk["bytes"] and asset["sha256"] == apk["sha256"]]
                        item["published_official_asset_matches"] = matches
                        item["official_release_reference"] = request["official_release_assets"]
                finally:
                    pool.close(fd)
            core.app_scope(pool, held, [package], {package: row}, False)
            manifests = [a.get("manifest") for a in app["apks"]]
            base = [m for m in manifests if m and not m["split_name"]]
            app["one_base_manifest_observed"] = len(base) == 1
            app["base_manifest"] = base[0] if len(base) == 1 else None
            app["complete_APK_set_observed"] = len(app["apks"]) == len(row["apks"])
            app["all_APKs_signature_verified"] = all(a.get("signature", {}).get("verified") is True for a in app["apks"])
            app["all_current_signers_equal_PM_records"] = all(a.get("signature", {}).get("current_signers_equal_PM_certificate_record") is True for a in app["apks"])
            app["all_manifests_match_PM_identity"] = all(a.get("manifest_matches_PM_package_and_version") is True for a in app["apks"])
            app["all_permission_names_decoded"] = all(a.get("declared_permissions", {}).get("all_names_decoded") is True for a in app["apks"])
        recheck_static_aliases(aliases, end)
        recheck_tools(core, pool, tools, end, True)
        core.app_scope(pool, held, request["packages"], expected, False)
        core.verify_runtime(pool, held, runtime)
        result["scope_guard_after"] = guard.check_app_scope(request["app_scope"], PROTECTED_PACKAGES)
        need(result["scope_guard_after"] == result["scope_guard_before"], "COMPLETE_48_PROTECTION_CHANGED")
        result["guard_after"] = guard.current_guard()
        need(result["guard_after"] == result["guard_before"], "TYPED_SUCCESSOR_GUARD_CHANGED")
        core.pinned_record(request["app_scope"])
        read_bootstrap(request["guard"], 65536)
        core.pinned_record(request["legacy_candidate_inventory"], 65536)
        core.pinned_record(request["legacy_candidate_proof"], 131072)
        core.pinned_record(request["legacy_candidate_terminal"], 65536)
        core.pinned_record(request["official_host_stdout"], 131072)
        core.pinned_record(request["official_host_terminal"], 65536)
        core.pinned_record(OFFICIAL_HOST_SOURCE, 131072)
        core.pinned_record(SCOPE_STDOUT)
        core.pinned_record(SCOPE_TERMINAL)
        core.pinned_record(SCOPE_VALIDATOR)
        official_layout.verify("after_all_APK_tools_and_file_checks", end)
        result["snapshot_consistent"] = True
    except BaseException as error:
        result["errors"].append({"type": type(error).__name__, "reason": str(error)[:256]})
    finally:
        if official_layout is not None:
            try:
                official_layout.close()
                closure = result["official_private_layout"]["owned_directory_descriptors"]
                result["official_layout_descriptors_closed"] = closure["acquired"] == closure["closed"] == 11 and closure["errors"] == []
                need(result["official_layout_descriptors_closed"], "OFFICIAL_LAYOUT_FDS_NOT_CLOSED")
            except BaseException as error:
                result["errors"].append({"stage": "official_layout_close", "type": type(error).__name__, "reason": str(error)[:160]})
        if lock is not None:
            try:
                fcntl.flock(lock, fcntl.LOCK_UN); result["action_lock_released"] = True
            except BaseException as error:
                result["errors"].append({"stage": "unlock", "type": type(error).__name__})
        keep = store.fd if store is not None else None
        for fd in tuple(pool.active):
            if fd != keep:
                try:
                    pool.close(fd)
                except BaseException as error:
                    result["errors"].append({"stage": "close", "type": type(error).__name__})
        result["all_tool_children_joined"] = all(x.get("joined") and x.get("pipes_closed") for x in result["commands"])
        result["unjoined_tool_pids"] = [x.get("pid") for x in result["commands"] if x.get("spawned") and not x.get("joined")]
        result["all_commands_succeeded"] = all(x.get("returncode") == 0 and not x.get("timed_out") and x.get("output_capture_complete") and not x.get("error") for x in result["commands"])
        result["all_primary_commands_succeeded"] = len(result["commands"]) == 3 * batch["APK_count"] and result["all_commands_succeeded"]
        result["all_manifests_and_signatures_verified"] = all_apk_evidence_verified(result, request["packages"])
        result["official_badging_stderr_empty"] = clean_official_badging_observations(result)
        observations = result.get("official_private_layout", {}).get("observations", [])
        result["official_layout_before_and_after_all_commands"] = len(observations) == 2 + 6 * batch["APK_count"] and all(
            row.get("complete") is True and row.get("all_five_search_directories_and_thirty_candidates_proved") is True for row in observations)
        result["ndk_audit_complete"] = (result["all_manifests_and_signatures_verified"] and
            result["all_primary_commands_succeeded"] and result["official_badging_stderr_empty"] and
            result.get("official_layout_descriptors_closed") is True and result["official_layout_before_and_after_all_commands"] and
            result.get("scope_guard_before") == result.get("scope_guard_after") and
            result.get("scope_qualification", {}).get("normal_owned_joint_validated") is True)
        # Preserve every full observation losslessly, under the same private store.
        # At 16 APKs the duplicate directory records otherwise exceed MAX_RESULT.
        try:
            if store is not None and "official_private_layout" in result:
                layout = result["official_private_layout"]
                layout_raw = canonical(layout) + b"\n"
                need(len(layout_raw) <= MAX_RESULT, "FULL_LAYOUT_EVIDENCE_BYTE_BOUND")
                layout_pin = store.write("official-layout-observations.private.json", layout_raw)
                result["official_private_layout"] = {"artifact": layout_pin,
                    "encoding": "zlib-base64", "data": base64.b64encode(zlib.compress(layout_raw, 9)).decode("ascii"),
                    "observation_count": len(observations),
                    "all_observations_complete": all(row.get("complete") is True and
                        row.get("all_five_search_directories_and_thirty_candidates_proved") is True for row in observations),
                    "owned_directory_descriptors": layout["owned_directory_descriptors"],
                    "full_original_observations_persisted_and_read_back": True}
            else:
                result["ndk_audit_complete"] = False
        except BaseException as error:
            result["errors"].append({"stage": "full_layout_evidence_publication", "type": type(error).__name__, "reason": str(error)[:160]})
            result["all_manifests_and_signatures_verified"] = False
            result["ndk_audit_complete"] = False
        result["resource_table_integrity_fully_proved"] = False
        result["inference_limit"] = "Current exact NDK APK normal cryptographic verification and manifest metadata only. PM signer equality does not authenticate package origin or authorize an upgrade. The 48-package identity scope, original FAILED/STOP/UNKNOWN records, permissions, UI and production gates remain unchanged. Resources are not fully validated by badging."
        result["ended_utc"] = now()
        result["owned_descriptors_before_final_receipt"] = pool.summary()
        result["status"] = "NDK_CURRENT_APK_SIGNATURE_AND_METADATA_VERIFIED" if result["ndk_audit_complete"] else "NDK_CURRENT_APK_AUDIT_INCOMPLETE_NO_RETRY"
        try:
            if store is not None:
                raw = canonical(result) + b"\n"; need(len(raw) <= MAX_RESULT, "RESULT_BYTE_BOUND")
                result["final_receipt"] = store.write("result.json", raw)
        except BaseException as error:
            result["errors"].append({"stage": "final_receipt", "type": type(error).__name__, "reason": str(error)[:160]})
            result["all_manifests_and_signatures_verified"] = False
            result["status"] = "FINAL_RECEIPT_FAILED"
        finally:
            try:
                pool.close_all()
            except BaseException as error:
                result["errors"].append({"stage": "FD_retirement", "type": type(error).__name__})
                result["all_manifests_and_signatures_verified"] = False
                result["status"] = "FD_RETIREMENT_FAILED"
        result["owned_descriptors_final"] = pool.summary()
        if not result["all_manifests_and_signatures_verified"]:
            result["ndk_audit_complete"] = False
    return result



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--request-sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    process_fds_before = len(os.listdir("/proc/self/fd"))
    try:
        request = json.loads(read_bootstrap({"path": args.request, "sha256": args.request_sha256}, 262144))
        result = audit(request)
    except BaseException as error:
        result = {"schema": "pocket4-ndk-apk-audit-entry-rejection-v1", "status": "ENTRY_OR_RECEIPT_REJECTED", "type": type(error).__name__,
                  "reason": str(error)[:256], "installs": 0, "UI_actions": 0, "automatic_retry": False, "production_ready": False}
    result["process_FDs_before"] = process_fds_before
    result["process_FDs_after"] = len(os.listdir("/proc/self/fd"))
    if result["process_FDs_before"] != result["process_FDs_after"]:
        result.setdefault("errors", []).append({"reason": "FINAL_PROCESS_FD_DIFFERENCE"})
        result["all_manifests_and_signatures_verified"] = False
        result["ndk_audit_complete"] = False
        result["status"] = "FINAL_PROCESS_FD_DIFFERENCE"
    result["success_gate_requires_outer_final_stdout_and_authoritative_terminal"] = True
    raw = canonical(result)
    need(len(raw) <= MAX_RESULT, "STDOUT_ARTIFACT_BOUND")
    print(json.dumps({"encoding": "zlib-base64", "artifact_bytes": len(raw), "artifact_sha256": sha(raw), "data": base64.b64encode(zlib.compress(raw, 9)).decode("ascii")}, separators=(",", ":")), flush=True)
    return 0 if result.get("ndk_audit_complete") is True else 1



if __name__ == "__main__":
    raise SystemExit(main())
