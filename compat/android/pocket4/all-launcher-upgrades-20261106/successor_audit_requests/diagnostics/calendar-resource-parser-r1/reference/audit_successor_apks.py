#!/usr/bin/env python3
"""Audit installed APK bytes, manifests and signatures on one typed successor.

No old guard, install, Android namespace, UI, grant, reset, or discovery path.
One immutable request selects at most four of the reviewed 45 Launcher apps.
The actual successor guard and versioned App scope must already exist and be
passed by content pin. Every APK is opened through the held Android root and
kept open across existing host tools. Business-data content is never read.
"""
import sys
sys.dont_write_bytecode = True
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

DEPS = {"path": "/home/alex/work/pocket4-app-identities-20261105-r12-01/dependencies.json",
        "sha256": "dfe1182d8e0da4d3d6e842736378539df33e03a87cf0ed9ab4bbe9ae1f26c041"}
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "TZ": "UTC"}
STAT = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
OUTPUT_PREFIX = "/home/alex/work/pocket4-successor-apk-audit-20261106-"
MAX_APK = 512 * 1024 * 1024
MAX_BATCH_BYTES = 4 * 1024 * 1024 * 1024
MAX_TOOL_OUTPUT = 4 * 1024 * 1024
MAX_RESULT = 512 * 1024
PACKAGES = (
    "com.Hyatt.hyt", "com.MobileTicket", "com.amazon.mShop.android.shopping",
    "com.android.calendar", "com.android.camera2", "com.android.contacts", "com.android.deskclock",
    "com.android.dialer", "com.android.documentsui", "com.android.gallery3d", "com.android.messaging",
    "com.android.quicksearchbox", "com.android.settings", "com.android.threadnetwork.demoapp",
    "com.bestbuy.android", "com.ehi.national.mobile", "com.enflick.android.TextNow", "com.google.android.gms",
    "com.hertz.android.digital", "com.hilton.android.hhonors", "com.ihg.apps.android", "com.jingdong.app.mall",
    "com.lianjia.beike", "com.marriott.mrt", "com.pinger.textfree", "com.rytong.airchina", "com.rytong.ceair",
    "com.sankuai.meituan.takeoutnew", "com.sdu.didi.psnger", "com.ss.android.ugc.aweme", "com.szzc",
    "com.taobao.taobao", "com.tencent.mm", "com.ubercab", "com.united.mobile.android", "com.xunmeng.pinduoduo",
    "com.zhubajie.client", "com.zillow.android.streeteasy", "ctrip.android.view", "jp.co.ana.android.tabidachi",
    "local.pocket4.fixture", "org.chromium.webview_shell", "org.droidloom.qa.editorcontract",
    "org.fcitx.fcitx5.android", "tv.danmaku.bili")
ROSTER_REFERENCE_SHA = "9c457f72522dc199ffc32e5d821c60c011662bb4e4e98651ea1cfe9a06e48eba"


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


def bind_tools(core, pool, end):
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
    return rows


def recheck_tools(core, pool, rows, end, full):
    core.pinned_record(DEPS, 262144)
    for row in rows.values():
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
    for name, prefix in (("min_sdk", "sdkVersion:"), ("target_sdk", "targetSdkVersion:"), ("max_sdk", "maxSdkVersion:")):
        found = [line for line in text.splitlines() if line.startswith(prefix)]
        need(len(found) <= 1, "AMBIGUOUS_AAPT_SDK")
        value[name] = re.findall(r"'([^']*)'", found[0])[0] if found and re.findall(r"'([^']*)'", found[0]) else None
    native = [line for line in text.splitlines() if line.startswith("native-code:")]
    need(len(native) <= 1, "AMBIGUOUS_AAPT_ABI")
    value["native_abis"] = re.findall(r"'([^']*)'", native[0]) if native else []
    value["native_abi_source"] = "aapt_dump_badging_current_APK"
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


def validate_request(request):
    need(set(request) == {"schema", "guard", "app_scope", "packages", "output_root", "official_release_assets"}, "CLOSED_REQUEST_SCHEMA")
    need(request["schema"] == "pocket4-successor-apk-audit-request-v1", "REQUEST_SCHEMA")
    packages = request["packages"]
    need(type(packages) is list and 0 < len(packages) <= 4 and len(packages) == len(set(packages)) and set(packages) <= set(PACKAGES), "EXPLICIT_REVIEWED_LAUNCHER_BATCH")
    need(request["official_release_assets"] is None or type(request["official_release_assets"]) is dict, "OPTIONAL_RELEASE_PIN")


def all_apk_evidence_verified(result, packages):
    """Complete evidence includes each current signer matching the actual PM record."""
    fields = ("complete_APK_set_observed", "one_base_manifest_observed",
              "all_APKs_signature_verified", "all_current_signers_equal_PM_records",
              "all_manifests_match_PM_identity", "all_permission_names_decoded")
    return bool(result.get("snapshot_consistent") is True and result.get("all_commands_succeeded") is True
                and len(result.get("apps", [])) == len(packages) > 0 and not result.get("errors")
                and all(all(row.get(field) is True for field in fields) for row in result["apps"]))


def audit(request):
    validate_request(request)
    need(os.getuid() == os.geteuid() == 0, "EXISTING_ROOT_AUTHORITY_REQUIRED")
    end = time.monotonic() + 840
    result = {"schema": "pocket4-successor-installed-apk-audit-v1", "started_utc": now(),
        "packages": request["packages"], "request": request, "roster_reference_sha256": ROSTER_REFERENCE_SHA,
        "UI_actions": 0, "App_launches": 0, "permission_changes": 0, "installs": 0,
        "Android_namespace_commands": 0, "ADB_commands": 0, "business_data_content_reads": 0,
        "automatic_retry": False, "production_ready": False, "snapshot_consistent": False,
        "effective_permission_grants": "UNKNOWN_NOT_QUERIED", "apps": [], "commands": [], "errors": []}
    raw = read_bootstrap(request["guard"], 65536)
    guard = types.ModuleType("pinned_successor_apk_audit_guard"); guard.__file__ = request["guard"]["path"]
    exec(compile(raw, guard.__file__, "exec"), guard.__dict__)
    core = guard._core()
    pool, store, lock = core.FDs(), None, None
    try:
        lock, result["action_lock_identity"] = core.acquire_lock(pool, core.ACTION_LOCK)
        result["guard_before"] = guard.current_guard()
        need(result["guard_before"].get("schema") == "pocket4-successor-main-guard-v1", "ACTUAL_NEW_TYPED_GUARD_REQUIRED")
        baseline = guard.current_baseline()
        scope = core.parse(core.pinned_record(request["app_scope"]))
        need(scope.get("schema") == "pocket4-versioned-app-scope-v1" and scope.get("runtime_epoch_sha256") == baseline["runtime_epoch_sha256"] and set(request["packages"]) <= set(scope["apps"]), "SAME_SUCCESSOR_APP_SCOPE_REQUIRED")
        expected = {name: scope["apps"][name] for name in request["packages"]}
        total = sum(apk["bytes"] for row in expected.values() for apk in row["apks"])
        need(0 < total <= MAX_BATCH_BYTES and all(0 < len(row["apks"]) <= 32 for row in expected.values()), "SCOPED_APK_SET_BOUND")
        runtime = baseline["runtime"]
        binding = runtime["held"]["process_snapshot"]["binding"]
        held = core.HeldProcesses(pool, {name: row["host_pid"] for name, row in binding["processes"].items()})
        need(held.before["binding"] == binding, "SUCCESSOR_HELD_BINDING_CHANGED")
        core.verify_runtime(pool, held, runtime)
        core.app_scope(pool, held, request["packages"], expected, False)
        store = Store(core, pool, request["output_root"])
        result["request_artifact"] = store.write("request.json", canonical(request) + b"\n")
        result["collector_source"] = store.write("collector-source.py", core.host_read(str(Path(__file__).resolve()), 131072)[0])
        tools = bind_tools(core, pool, end)
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
                        ("badging", [tools["aapt"]["pin"]["resolved_path"], "dump", "badging", source]),
                        ("manifest", [tools["aapt"]["pin"]["resolved_path"], "dump", "xmltree", source, "AndroidManifest.xml"])]
                    outputs = {}
                    for name, argv in definitions:
                        recheck_tools(core, pool, tools, end, False)
                        command = {"package": package, "apk_path": apk["path"], "name": name}
                        result["commands"].append(command); item["commands"].append(command)
                        streams = run_tool(argv, (fd, tools["apksigner_jar"]["fd"]), command, end)
                        for kind, content in streams.items():
                            command[kind] = store.write(f"p{pi:02d}-a{ai:02d}-{name}.{kind}", content)
                        need(command.get("joined") is True and command.get("pipes_closed") is True, "TOOL_CHILD_RETIREMENT_NOT_PROVED")
                        outputs[name] = streams["stdout"]
                        recheck_tools(core, pool, tools, end, False)
                    for name, fn in (("signature", lambda: parse_signature(outputs["apksigner"], item["commands"][0])),
                                     ("manifest", lambda: badging_manifest(outputs["badging"])),
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
        recheck_tools(core, pool, tools, end, True)
        core.app_scope(pool, held, request["packages"], expected, False)
        core.verify_runtime(pool, held, runtime)
        result["guard_after"] = guard.current_guard()
        need(result["guard_after"] == result["guard_before"], "TYPED_SUCCESSOR_GUARD_CHANGED")
        core.pinned_record(request["app_scope"])
        read_bootstrap(request["guard"], 65536)
        result["snapshot_consistent"] = True
    except BaseException as error:
        result["errors"].append({"type": type(error).__name__, "reason": str(error)[:256]})
    finally:
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
        result["all_manifests_and_signatures_verified"] = all_apk_evidence_verified(result, request["packages"])
        result["ended_utc"] = now()
        result["owned_descriptors_before_final_receipt"] = pool.summary()
        result["status"] = "ACTUAL_APK_AUDIT_VERIFIED" if result["all_manifests_and_signatures_verified"] else "APK_AUDIT_INCOMPLETE_REVIEW_RAW_EVIDENCE"
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
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--request-sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        request = json.loads(read_bootstrap({"path": args.request, "sha256": args.request_sha256}, 262144))
        result = audit(request)
    except BaseException as error:
        result = {"schema": "pocket4-successor-apk-audit-entry-rejection-v1", "status": "ENTRY_OR_RECEIPT_REJECTED", "type": type(error).__name__,
                  "reason": str(error)[:256], "installs": 0, "UI_actions": 0, "automatic_retry": False, "production_ready": False}
    raw = canonical(result)
    need(len(raw) <= MAX_RESULT, "STDOUT_ARTIFACT_BOUND")
    print(json.dumps({"encoding": "zlib-base64", "artifact_bytes": len(raw), "artifact_sha256": sha(raw), "data": base64.b64encode(zlib.compress(raw, 9)).decode("ascii")}, separators=(",", ":")), flush=True)
    return 0 if result.get("all_manifests_and_signatures_verified") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
