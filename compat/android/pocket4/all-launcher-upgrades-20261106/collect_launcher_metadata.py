#!/usr/bin/env python3
"""Bounded metadata inventory of every entry in the native launcher catalog.

Run as root: python3 -B -I collect_launcher_metadata.py. Place the exact pinned
collect_readonly.py beside this file. No arguments or scope overrides exist.
The original Reader, ABX parser, HeldAndroidRoot and guard are imported intact.
Two explicit read-only droidloomctl applications observations bracket metadata
collection; they are not retries. No Android namespace command is introduced.

No APK is opened or hashed. Package-manager certificates are stored evidence,
not fresh APK signature verification. Historical versionName is an unverified
reference even when its recorded versionCode equals the current stored value.
All effective grants remain UNKNOWN. The complete JSON artifact is capped at
512 KiB and emitted as a SHA256-addressed zlib/base64 stdout envelope.
"""
import sys
sys.dont_write_bytecode = True

import base64
import datetime
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


BASE_SHA = "04dcc9337aa61ed663e3ce3dea8ab13a963c4826588fcd1c25554466ed30acd1"
BASE_BYTES = 48526
CATALOG_ARGV = ("/usr/bin/sudo", "-n", "-u", "alex", "/usr/bin/droidloomctl", "--json", "applications")
CATALOG_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8",
               "XDG_RUNTIME_DIR": "/run/user/1000",
               "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus"}
CATALOG_SECONDS = 25
CATALOG_STDOUT = 256 * 1024
CATALOG_STDERR = 16 * 1024
MAX_CATALOG_ROWS = 512
MAX_ARTIFACT = 512 * 1024
MAX_PERMISSION_ENTRIES = 2048
MAX_HISTORY_FILES = 512
MAX_HISTORY_TOTAL = 16 * 1024 * 1024
PACKAGE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+\Z")
COMPONENT_CLASS_RE = re.compile(r"[A-Za-z0-9_.$]+\Z")
HISTORY_NAME_RE = re.compile(r"app-[0-9]{2,4}\.json\Z")
SCHEMA = "pocket4-native-launcher-metadata-inventory-v1"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("ascii")


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def load_base():
    path = Path(__file__).resolve().with_name("collect_readonly.py")
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size != BASE_BYTES:
            raise RuntimeError("PINNED_READER_FILE_METADATA_DIFFERS")
        chunks, count = [], 0
        while count <= BASE_BYTES:
            part = os.read(fd, BASE_BYTES + 1 - count)
            if not part:
                break
            chunks.append(part)
            count += len(part)
        after = os.fstat(fd)
        raw = b"".join(chunks)
        fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_uid", "st_gid",
                  "st_size", "st_mtime_ns", "st_ctime_ns")
        if count != BASE_BYTES or sha(raw) != BASE_SHA or any(
                getattr(before, k) != getattr(after, k) for k in fields):
            raise RuntimeError("PINNED_READER_SOURCE_CHANGED")
    finally:
        os.close(fd)
    module = types.ModuleType("pocket4_original_readonly_primitives")
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module, str(path)


def catalog_command(c, budget):
    """One fixed existing CLI, bounded pipes and a separately owned process group."""
    budget.check()
    started = time.monotonic()
    receipt = {"argv": list(CATALOG_ARGV), "started_utc": now(), "automatic_retry": False,
               "timeout_seconds": CATALOG_SECONDS, "spawned": False, "joined": False,
               "timed_out": False, "group_termination_requested": False}
    proc, selector, failure = None, selectors.DefaultSelector(), None
    output = {"stdout": bytearray(), "stderr": bytearray()}
    streams = []
    try:
        proc = subprocess.Popen(CATALOG_ARGV, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=CATALOG_ENV, close_fds=True,
                                start_new_session=True)
        receipt["spawned"] = True
        streams = [proc.stdout, proc.stderr]
        for name, stream in zip(("stdout", "stderr"), streams):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        deadline = min(budget.deadline, started + CATALOG_SECONDS)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                receipt["timed_out"] = True
                raise c.Rejected("NATIVE_CATALOG_DEADLINE")
            for key, unused_mask in selector.select(min(0.2, remaining)):
                part = os.read(key.fileobj.fileno(), 65536)
                if not part:
                    selector.unregister(key.fileobj)
                    continue
                limit = CATALOG_STDOUT if key.data == "stdout" else CATALOG_STDERR
                c.need(len(output[key.data]) + len(part) <= limit, "NATIVE_CATALOG_PIPE_BOUND")
                output[key.data].extend(part)
        proc.wait(timeout=max(0.001, deadline - time.monotonic()))
    except BaseException as error:
        failure = error
        if isinstance(error, subprocess.TimeoutExpired):
            receipt["timed_out"] = True
        if proc is not None and proc.returncode is None:
            # This group was created by this invocation; the unreaped child PID
            # still pins its identity. Never signal the Main or an observed PID.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
                receipt["group_termination_requested"] = True
            except ProcessLookupError:
                pass
            except OSError as cleanup:
                receipt["termination_error"] = c.error_record(cleanup)
            try:
                proc.wait(timeout=5)
            except BaseException as cleanup:
                receipt["join_error"] = c.error_record(cleanup)
    finally:
        selector.close()
        for stream in streams:
            stream.close()
        receipt["joined"] = bool(proc is not None and proc.returncode is not None)
        receipt["returncode"] = proc.returncode if proc is not None else None
        receipt["seconds"] = round(time.monotonic() - started, 6)
        receipt["ended_utc"] = now()
        for name, data in output.items():
            receipt[name + "_bytes"] = len(data)
            receipt[name + "_sha256"] = sha(data)
    if failure is not None:
        receipt["error"] = c.error_record(failure)
    return bytes(output["stdout"]), receipt


def catalog_projection(c, raw, expected_host_pid):
    value = c.json_object(raw)
    c.need(value.get("ok") is True and value.get("state") == "running" and
           value.get("host_pid") == expected_host_pid, "NATIVE_CATALOG_MAIN_IDENTITY_DIFFERS")
    rows = value.get("applications")
    c.need(type(rows) is list and 0 < len(rows) <= MAX_CATALOG_ROWS, "NATIVE_CATALOG_ROW_BOUND")
    selected, seen = [], set()
    for row in rows:
        c.need(type(row) is dict, "NATIVE_CATALOG_ROW_TYPE")
        package = c.small_text(row.get("package"), "CATALOG_PACKAGE_BOUND", 256)
        component = c.small_text(row.get("component"), "CATALOG_COMPONENT_BOUND", 2048)
        name = c.small_text(row.get("name"), "CATALOG_LABEL_BOUND", 512)
        c.need(PACKAGE_RE.fullmatch(package) and component.startswith(package + "/") and
               COMPONENT_CLASS_RE.fullmatch(component[len(package) + 1:]), "CATALOG_COMPONENT_SCOPE")
        pair = (package, component)
        c.need(pair not in seen, "DUPLICATE_CATALOG_PACKAGE_COMPONENT")
        seen.add(pair)
        selected.append({"name": name, "package": package, "component": component})
    selected.sort(key=lambda row: (row["package"], row["component"]))
    pairs = [[row["package"], row["component"]] for row in selected]
    return {"applications": selected, "entry_count": len(selected),
            "package_count": len({row["package"] for row in selected}),
            "package_component_sha256": sha(canonical(pairs)),
            "labels_and_components_sha256": sha(canonical(selected)),
            "digest_encoding": "ASCII canonical JSON of sorted [package,component] pairs",
            "cache_freshness_proven": False, "current_android_launcher_resolution_proven": False}


def signing_projection(c, node, certs, scope):
    rows = [x for x in node.children if x.tag == "sigs"]
    c.need(len(rows) <= 1, "MULTIPLE_SIGNING_RECORDS")
    out = {"scope": scope, "status": "UNKNOWN_NO_PACKAGE_MANAGER_RECORD",
           "certificate_sha256": [], "cryptographic_verification_performed": False}
    if not rows:
        return out
    items = [x for x in rows[0].children if x.tag == "cert"]
    count = c.integer(rows[0].attrs.get("count"), "SIGNATURE_COUNT_TYPE")
    c.need(0 <= count <= 32 and len(items) == count, "SIGNATURE_COUNT_MISMATCH")
    if count == 0:
        out["status"] = "UNKNOWN_EMPTY_PACKAGE_MANAGER_SIGNATURE_RECORD"
        return out
    indices = [c.integer(x.attrs.get("index"), "SIGNATURE_INDEX_TYPE") for x in items]
    c.need(len(indices) == len(set(indices)), "DUPLICATE_CERT_INDEX")
    if all(x in certs for x in indices):
        out.update(status="PACKAGE_MANAGER_CERTIFICATE_DIGESTS_ONLY",
                   certificate_sha256=sorted(certs[x] for x in indices))
    else:
        out["status"] = "UNKNOWN_UNRESOLVED_CERTIFICATE_INDEX"
    return out


def package_projection(c, root, packages):
    c.need(root.tag == "packages", "PACKAGES_ROOT_REQUIRED")
    certs, shared, nodes = c.cert_digests(root), {}, {}
    for node in root.children:
        if node.tag != "shared-user":
            continue
        uid = c.integer(node.attrs.get("userId"), "SHARED_USER_ID_TYPE")
        name = c.small_text(node.attrs.get("name"), "SHARED_USER_NAME_BOUND", 256)
        c.need(0 <= uid < 100000 and uid not in shared, "SHARED_USER_ID_BOUND_OR_DUPLICATE")
        shared[uid] = (name, node)
    result = {}
    for node in root.children:
        package = node.attrs.get("name")
        if node.tag != "package" or package not in packages:
            continue
        c.need(package not in result, "DUPLICATE_CATALOG_PACKAGE_METADATA")
        uid_keys = [k for k in ("userId", "sharedUserId") if k in node.attrs]
        c.need(len(uid_keys) == 1, "PACKAGE_UID_AMBIGUOUS_OR_MISSING")
        uid = c.integer(node.attrs[uid_keys[0]], "PACKAGE_UID_TYPE")
        c.need(0 <= uid < 100000, "USER_ZERO_UID_BOUND")
        versions = [c.integer(node.attrs[k], "PACKAGE_VERSION_TYPE")
                    for k in ("version", "versionCode") if k in node.attrs]
        c.need(versions and len(set(versions)) == 1 and 0 <= versions[0] < (1 << 63),
               "PACKAGE_VERSION_AMBIGUOUS_OR_MISSING")
        code_path = c.small_text(node.attrs.get("codePath"), "PACKAGE_CODE_PATH_BOUND", 2048)
        c.path_parts(code_path)  # Record a canonical path; do not open it.
        row = {"package": package, "metadata_present": True, "android_user": 0,
               "uid": uid, "uid_storage_attribute": uid_keys[0], "uid_below_10000": uid < 10000,
               "version_code": versions[0], "code_path": code_path, "code_path_opened": False,
               "version_name": {"value": None, "status": "UNKNOWN_CURRENT_MANIFEST_NOT_READ"},
               "package_manager_signing": signing_projection(c, node, certs, "package"),
               "package_manager_abi": {k: c.small_text(node.attrs[k], "ABI_BOUND", 64)
                   for k in ("primaryCpuAbi", "secondaryCpuAbi", "cpuAbiOverride") if k in node.attrs},
               "apk_set_hashed": False, "fresh_manifest_parser_executed": False,
               "effective_permission_state": "UNKNOWN_SAVED_SOURCES_NOT_LIVE_AUTHORITY",
               "App_runtime_or_business_qualification": "NOT_EXECUTED"}
        row["package_manager_saved_flags"] = {}
        for key in ("flags", "publicFlags", "privateFlags"):
            if key in node.attrs:
                value = node.attrs[key]
                c.need(type(value) is int or (type(value) is str and len(value) <= 32 and
                       re.fullmatch(r"[0-9a-fA-FxX+-]+", value)), "PACKAGE_SAVED_FLAGS_TYPE")
                row["package_manager_saved_flags"][key] = value
        if "versionName" in node.attrs:
            row["version_name"] = {"value": c.small_text(node.attrs["versionName"], "VERSION_NAME_BOUND", 256),
                                   "status": "PACKAGE_MANAGER_STORED_VALUE_NOT_FRESH_MANIFEST"}
        if uid_keys[0] == "sharedUserId":
            if uid in shared:
                name, shared_node = shared[uid]
                row["shared_user"] = {"name": name, "uid": uid,
                    "signing": signing_projection(c, shared_node, certs, "shared-user"),
                    "per_package_effective_grants_not_inferred": True}
            else:
                row["shared_user"] = {"uid": uid, "status": "UNKNOWN_SHARED_USER_RECORD_MISSING"}
        result[package], nodes[package] = row, node
    return result, nodes, shared


def restrictions_projection(c, root, packages):
    c.need(root.tag == "package-restrictions", "RESTRICTIONS_ROOT_REQUIRED")
    result = {}
    for node in root.children:
        package = node.attrs.get("name")
        if node.tag != "pkg" or package not in packages:
            continue
        c.need(package not in result, "DUPLICATE_RESTRICTION_PACKAGE")
        values = {}
        for key in ("installed", "hidden", "suspended", "stopped", "enabled", "notLaunched"):
            if key in node.attrs:
                value = node.attrs[key]
                c.need(type(value) in (str, int, bool) and
                       (type(value) is not str or len(value) <= 64), "RESTRICTION_VALUE_TYPE")
                values[key] = value
        components = {}
        for section in node.children:
            if section.tag not in ("enabled-components", "disabled-components"):
                continue
            c.need(section.tag not in components, "DUPLICATE_COMPONENT_RESTRICTION_SECTION")
            names = [c.small_text(item.attrs.get("name"), "COMPONENT_RESTRICTION_BOUND", 2048)
                     for item in section.children if item.tag == "item"]
            c.need(len(names) <= 512 and len(names) == len(set(names)), "COMPONENT_RESTRICTION_COUNT")
            components[section.tag] = sorted(names)
        result[package] = {"coverage": True, "recorded_fields": values,
                           "recorded_components": components, "absent_fields_not_defaulted": True}
    return result


def permission_entries(c, node, item_tag):
    result, seen = [], set()
    for item in node.children:
        if item.tag != item_tag:
            continue
        name = c.small_text(item.attrs.get("name"), "PERMISSION_NAME_BOUND", 256)
        c.need(name not in seen and len(seen) < MAX_PERMISSION_ENTRIES, "PERMISSION_NAME_OR_COUNT")
        seen.add(name)
        row = {"name": name}
        if not c.NAME.fullmatch(name):
            row["noncanonical_name_preserved"] = True  # Never strip persisted names.
        if "flags" in item.attrs:
            flags = item.attrs["flags"]
            c.need(type(flags) is int or (type(flags) is str and len(flags) <= 32 and
                   re.fullmatch(r"[0-9a-fA-FxX+-]+", flags)), "PERMISSION_FLAG_TYPE")
            row["flags"] = flags
        if "granted" in item.attrs:
            value = item.attrs["granted"]
            c.need(type(value) is bool or value in ("true", "false"), "SAVED_PERMISSION_GRANT_TYPE")
            row["stored_granted"] = value if type(value) is bool else value == "true"
        result.append(row)
    return sorted(result, key=lambda row: row["name"])


def permission_subjects(c, sources, projected, package_nodes, shared):
    """Deduplicate app-id/shared-user records; grants are never interpreted."""
    subjects, refs, seen = [], {package: [] for package in projected}, set()
    uids = {row["uid"] for row in projected.values()}
    shared_names = {row["shared_user"]["name"] for row in projected.values()
                    if "name" in row.get("shared_user", {})}

    def add(source, kind, subject, node, tag, packages):
        key = (source, kind, subject)
        c.need(key not in seen, "DUPLICATE_PERMISSION_SUBJECT")
        seen.add(key)
        identifier = "permission-subject-%03d" % len(subjects)
        subjects.append({"id": identifier, "source": source, "kind": kind, "subject": subject,
                         "effective_grant_state": "UNKNOWN", "absent_permissions_not_denied": True,
                         "entries": permission_entries(c, node, tag)})
        for package in packages:
            refs[package].append(identifier)

    for source in sources:
        root = source["document"]
        if root is None:
            continue
        path = source["path"]
        if root.tag == "access":
            for section in root.children:
                if section.tag != "app-id-permissions":
                    continue
                for node in section.children:
                    if node.tag != "app-id":
                        continue
                    uid = c.integer(node.attrs.get("id"), "PERMISSION_APPID_TYPE")
                    if uid in uids:
                        add(path, "access_app_id", uid, node, "permission",
                            [p for p, row in projected.items() if row["uid"] == uid])
        elif root.tag == "runtime-permissions":
            for node in root.children:
                name = node.attrs.get("name")
                if node.tag == "package" and name in projected:
                    add(path, "legacy_package", name, node, "item", [name])
                elif node.tag == "shared-user" and name in shared_names:
                    add(path, "legacy_shared_user", name, node, "item",
                        [p for p, row in projected.items() if row.get("shared_user", {}).get("name") == name])
    for package, node in package_nodes.items():
        sections = [x for x in node.children if x.tag == "perms"]
        c.need(len(sections) <= 1, "DUPLICATE_PACKAGE_INSTALL_PERMISSION_SECTION")
        if sections:
            add(c.PACKAGES_PATH, "package_manager_install_package", package, sections[0], "item", [package])
    for uid, (name, node) in shared.items():
        members = [p for p, row in projected.items() if row.get("shared_user", {}).get("name") == name]
        if not members:
            continue
        sections = [x for x in node.children if x.tag == "perms"]
        c.need(len(sections) <= 1, "DUPLICATE_SHARED_INSTALL_PERMISSION_SECTION")
        if sections:
            add(c.PACKAGES_PATH, "package_manager_install_shared_user", name, sections[0], "item", members)
    by_id = {row["id"]: row for row in subjects}
    for package, row in projected.items():
        row["permission_subject_refs"] = refs[package]
        row["saved_permission_record_present"] = bool(refs[package])
        row["location_permission_observations"] = [
            {"permission": permission, "effective_grant_state": "UNKNOWN",
             "stored_observations": [{"subject_ref": identifier, **entry}
                 for identifier in refs[package] for entry in by_id[identifier]["entries"]
                 if entry["name"] == permission]}
            for permission in c.LOCATION_PERMISSIONS]
    return subjects


def historical_references(c, host, projected, budget):
    result = {package: [] for package in projected}
    try:
        names = host.directory(c.HISTORY_ROOT, lambda name: bool(HISTORY_NAME_RE.fullmatch(name)))
    except FileNotFoundError:
        return result, {"status": "ABSENT", "path": c.HISTORY_ROOT}
    c.need(len(names) <= MAX_HISTORY_FILES, "HISTORICAL_METADATA_FILE_COUNT")
    known_pins = {name: digest for name, digest in c.HISTORY.values()}
    total, observed = 0, 0
    for name in names:
        budget.check()
        raw, source = host.read(c.HISTORY_ROOT + "/" + name, 262144, pin=known_pins.get(name))
        total += len(raw)
        c.need(total <= MAX_HISTORY_TOTAL, "HISTORICAL_METADATA_TOTAL_BOUND")
        history = c.json_object(raw)
        package = history.get("package")
        if package not in projected:
            continue
        c.need(history.get("android_user") == 0, "HISTORICAL_USER_SCOPE")
        apks = history.get("apks")
        c.need(type(apks) is list and 0 < len(apks) <= 32, "HISTORICAL_APK_RECORD_COUNT")
        bases = [row.get("manifest", {}) for row in apks if type(row) is dict and
                 type(row.get("manifest")) is dict and row["manifest"].get("package") == package and
                 row["manifest"].get("split_name") is None]
        entry = {"source": {"path": source["path"], "bytes": source["bytes"], "sha256": source["sha256"]},
                 "source_externally_pinned": name in known_pins,
                 "status": "HISTORICAL_REFERENCE_CURRENT_APK_BYTES_UNCHECKED",
                 "current_apk_byte_match_proven": False, "current_version_name_verified": False}
        if len(bases) == 1:
            value = bases[0].get("version_name")
            c.need(value is None or (type(value) is str and len(value.encode("utf-8")) <= 256),
                   "HISTORICAL_VERSION_NAME_BOUND")
            version = c.integer(bases[0].get("version_code"), "HISTORICAL_VERSION_CODE_TYPE")
            c.need(0 <= version < (1 << 63), "HISTORICAL_VERSION_CODE_BOUND")
            entry.update(version_name=value, version_code=version,
                         current_stored_version_code_equal=version == projected[package]["version_code"])
        else:
            entry["status"] = "UNKNOWN_HISTORICAL_BASE_MANIFEST_AMBIGUOUS"
        if history.get("finished_utc") is not None:
            entry["finished_utc"] = c.small_text(history["finished_utc"], "HISTORICAL_TIME_BOUND", 128)
        result[package].append(entry)
        observed += 1
    return result, {"status": "READ", "path": c.HISTORY_ROOT, "files_read": len(names),
                    "matching_records": observed, "bytes_read": total,
                    "historical_data_not_current_manifest_authority": True}


def collect(c, base_path):
    fds, budget = c.Descriptors(), c.Budget()
    result = {"schema": SCHEMA, "started_utc": now(), "base_reader_sha256": BASE_SHA,
              "scope": {"name": "all-current-native-launcher-catalog-entries",
                        "system_and_shared_uid_packages_included": True,
                        "catalog_cache_freshness_proven": False,
                        "current_android_launcher_resolver_proven": False},
              "epoch_sha256": c.EPOCH, "guard_source_sha256": c.GUARD_SHA,
              "identity_qualification_only": True, "UI_or_install_runtime_admitted": False,
              "production_ready": False, "new_signature_verification_performed": False,
              "catalog_cli_calls": [], "Android_namespace_commands": 0, "namespace_entries": 0,
              "App_launches": 0, "UI_actions": 0, "installs": 0, "permission_changes": 0,
              "collector_file_writes": 0, "automatic_retry": False, "apk_bytes_read": 0,
              "APK_scope": "NOT_OPENED_METADATA_ONLY", "permission_subjects": [],
              "apps": [], "errors": [], "reference_warnings": [], "snapshot_consistent": False,
              "read_limits": {"seconds": c.READ_SECONDS, "metadata_file_bytes": c.MAX_METADATA,
                              "artifact_bytes": MAX_ARTIFACT, "catalog_rows": MAX_CATALOG_ROWS}}
    guard, host, android, held = None, None, None, None
    old_handler, alarm_set = None, False
    try:
        c.need(os.getuid() == os.geteuid() == 0 and sys.platform.startswith("linux"), "ROOT_LINUX_REQUIRED")
        c.need(len(sys.argv) == 1, "NO_RUNTIME_OVERRIDES")
        root = fds.own(os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC))
        host = c.Reader(root, fds, budget)
        host.read(base_path, 65536, pin=BASE_SHA)
        raw, unused = host.read(c.GUARD_PATH, 65536, pin=c.GUARD_SHA)
        guard = types.ModuleType("pocket4_unchanged_current_guard")
        guard.__file__ = c.GUARD_PATH
        exec(compile(raw, c.GUARD_PATH, "exec"), guard.__dict__)
        result["guard_before"] = c.validate_guard_result(guard.current_guard())
        baseline = guard.current_baseline()
        expected_host_pid = baseline["status"]["host_pid"]
        held = c.HeldAndroidRoot(baseline, fds, budget)
        del baseline
        android = c.Reader(held.root_fd, fds, budget)
        c.need(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), "PREEXISTING_PROCESS_ALARM")
        def expired(unused_signum, unused_frame):
            raise c.Rejected("READ_DEADLINE_EXCEEDED")
        old_handler = signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, max(0.001, budget.deadline - time.monotonic()))
        alarm_set = True
        catalog_raw, receipt = catalog_command(c, budget)
        result["catalog_cli_calls"].append(receipt)
        c.need(receipt.get("error") is None and receipt["joined"] and receipt["returncode"] == 0,
               "NATIVE_CATALOG_COMMAND_FAILED")
        catalog = catalog_projection(c, catalog_raw, expected_host_pid)
        result["catalog"] = catalog
        packages = {row["package"] for row in catalog["applications"]}
        result["scope"]["package_component_sha256"] = catalog["package_component_sha256"]
        result["scope"]["packages"] = sorted(packages)
        held.verify()
        metadata_sources = {}
        raw, metadata_sources["packages"] = android.read(c.PACKAGES_PATH, c.MAX_METADATA)
        package_root = c.parse_xml(raw, budget.check)
        projected, package_nodes, shared = package_projection(c, package_root, packages)
        raw, metadata_sources["restrictions"] = android.read(c.RESTRICTIONS_PATH, c.MAX_METADATA)
        restrictions = restrictions_projection(c, c.parse_xml(raw, budget.check), packages)
        permission_sources = []
        for path in c.PERMISSION_PATHS:
            observed = android.optional(path, c.MAX_METADATA)
            if observed is None:
                permission_sources.append({"path": path, "status": "ABSENT", "document": None})
                continue
            raw, source = observed
            source.update(status="READ", format="ABX0" if raw.startswith(b"ABX\0") else "XML")
            document = c.parse_xml(raw, budget.check)
            source.update(root_tag=document.tag, scoped_schema_supported=document.tag in ("access", "runtime-permissions"))
            permission_sources.append({**source, "document": document})
        result["metadata_sources"] = metadata_sources
        result["permission_sources"] = [{k: v for k, v in source.items() if k != "document"}
                                        for source in permission_sources]
        result["permission_subjects"] = permission_subjects(c, permission_sources, projected, package_nodes, shared)
        for package in sorted(packages):
            budget.check()
            if package not in projected:
                result["apps"].append({"package": package, "metadata_present": False,
                                       "status": "UNKNOWN_CATALOG_PACKAGE_NOT_IN_CURRENT_PM_METADATA",
                                       "effective_permission_state": "UNKNOWN"})
                continue
            row = projected[package]
            row["launcher_entries"] = [x for x in catalog["applications"] if x["package"] == package]
            row["user_restrictions"] = restrictions.get(package, {"coverage": False, "recorded_fields": {},
                                                                  "absent_fields_not_defaulted": True})
            row["historical_version_name_references"] = []
            result["apps"].append(row)
        try:
            history, result["historical_sources"] = historical_references(c, host, projected, budget)
            for row in result["apps"]:
                row["historical_version_name_references"] = history.get(row["package"], [])
        except (c.Rejected, OSError, ValueError, TypeError) as error:
            # Optional historical references cannot replace or erase current
            # metadata. File-identity changes still fail the final recheck.
            result["historical_sources"] = {"status": "UNAVAILABLE_OR_UNQUALIFIED"}
            result["reference_warnings"].append({"stage": "historical_reference", **c.error_record(error)})
        held.verify()
        android.recheck()
        host.recheck()
        held.verify()
        result["all_observed_paths_rechecked"] = True
        catalog_raw, receipt = catalog_command(c, budget)
        result["catalog_cli_calls"].append(receipt)
        c.need(receipt.get("error") is None and receipt["joined"] and receipt["returncode"] == 0,
               "FINAL_NATIVE_CATALOG_COMMAND_FAILED")
        after = catalog_projection(c, catalog_raw, expected_host_pid)
        c.need(after == catalog, "NATIVE_CATALOG_CHANGED_DURING_METADATA_READ")
        result["catalog_bracket_equal"] = True
        # The final catalog call may take time: recheck metadata after it too.
        held.verify()
        android.recheck()
        host.recheck()
        held.verify()
    except BaseException as error:
        result["errors"].append(c.error_record(error))
    finally:
        if old_handler is not None:
            if alarm_set:
                signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)
        if guard is not None:
            try:
                result["guard_after"] = c.validate_guard_result(guard.current_guard())
                c.need(result.get("guard_before") == result["guard_after"], "GUARD_RESULTS_CHANGED")
            except BaseException as error:
                result["errors"].append({"stage": "final_guard", **c.error_record(error)})
        fds.close_remaining()
        result["observation_fds"] = fds.report()
        if fds.close_errors or fds.live or fds.acquired != fds.closed:
            result["errors"].append({"code": "OWNED_DESCRIPTORS_NOT_ALL_CLOSED"})
    result["all_catalog_packages_observed"] = bool(result.get("catalog") and
        len(result["apps"]) == result["catalog"]["package_count"] and
        all(row.get("metadata_present") is True for row in result["apps"]))
    result["snapshot_consistent"] = bool(not result["errors"] and result.get("all_observed_paths_rechecked")
        and result.get("catalog_bracket_equal") and result.get("guard_after"))
    result["status"] = ("READONLY_LAUNCHER_METADATA_COMPLETE" if result["snapshot_consistent"] and
                        result["all_catalog_packages_observed"] else "FAILED_OR_INCOMPLETE_METADATA_SNAPSHOT")
    result["finished_utc"] = now()
    result["elapsed_seconds"] = round(time.monotonic() - budget.started, 6)
    return result


def envelope(result):
    raw = canonical(result)
    if len(raw) > MAX_ARTIFACT:
        result = {"schema": SCHEMA, "status": "FAILED_OUTPUT_BOUND", "snapshot_consistent": False,
                  "production_ready": False, "UI_or_install_runtime_admitted": False,
                  "suppressed_artifact_bytes": len(raw), "suppressed_artifact_sha256": sha(raw),
                  "errors": [{"code": "ARTIFACT_512KIB_BOUND"}],
                  "observation_fds": result.get("observation_fds")}
        raw = canonical(result)
    packed = zlib.compress(raw, 9)
    return {"schema": "pocket4-zlib-json-artifact-v1", "artifact_schema": SCHEMA,
            "status": result["status"], "encoding": "zlib+base64", "artifact_bytes": len(raw),
            "artifact_sha256": sha(raw), "compressed_bytes": len(packed), "compressed_sha256": sha(packed),
            "data_base64": base64.b64encode(packed).decode("ascii")}


def main():
    try:
        c, path = load_base()
        result = collect(c, path)
    except BaseException as error:
        result = {"schema": SCHEMA, "status": "FAILED_BASE_READER_ADMISSION", "snapshot_consistent": False,
                  "production_ready": False, "UI_or_install_runtime_admitted": False,
                  "errors": [{"code": type(error).__name__}]}
    wrapped = envelope(result)
    sys.stdout.buffer.write(canonical(wrapped) + b"\n")
    sys.stdout.buffer.flush()
    return 0 if wrapped["status"] == "READONLY_LAUNCHER_METADATA_COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
