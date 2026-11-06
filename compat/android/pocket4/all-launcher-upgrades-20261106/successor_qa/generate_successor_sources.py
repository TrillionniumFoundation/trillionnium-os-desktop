#!/usr/bin/env python3
"""Generate a new R5/R9 package closure from a real successor's pinned inputs.

No subprocess, namespace entry, install, launch, UI operation, permission grant,
or restart is performed. The only writes create the requested new source tree.
The resulting build program is a scoped adaptation of the original R9 builder.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OLD_EPOCH = "734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2"
OLD_BASELINE = "163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266"
OLD_QUALIFICATION = "f37b2eb00db80c398c9a4f9fd895628b6c7ecc827ccf9699c2242fa5ba862ed6"
REF = "df9465b6a899fbbd9f8e40294f14185f70880c4f"
NATIVE_CLI = {"path": "/usr/bin/droidloomctl", "bytes": 1705648,
              "sha256": "f81e0223f6b256584d07a5e8fbc72f3f4c764ab53a88469b45b587c101e12c79"}
PKG = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+")


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def read(path, maximum=4 * 1024 * 1024):
    path = str(path)
    parts = path[1:].split("/")
    need(path.startswith("/") and not any(x in ("", ".", "..") for x in parts), "CANONICAL_ABSOLUTE_PATH")
    fds = []
    try:
        d = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        fds.append(d)
        for component in parts[:-1]:
            d = os.open(component, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=d)
            fds.append(d)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=d)
        fds.append(fd)
        def metadata(f):
            s = os.fstat(f)
            return tuple(getattr(s, k) for k in ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns"))
        before, first = metadata(fd), os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and 0 < first.st_size <= maximum, "BOUNDED_SINGLE_FILE")
        raw, deadline = bytearray(), time.monotonic() + 10
        while len(raw) <= maximum:
            need(time.monotonic() < deadline, "READ_DEADLINE")
            block = os.read(fd, min(65536, maximum + 1 - len(raw)))
            if not block:
                break
            raw.extend(block)
        need(len(raw) == first.st_size and metadata(fd) == before, "READ_IDENTITY_CHANGED")
        check = os.open(parts[-1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=d)
        fds.append(check)
        need(metadata(check) == before, "READ_PATH_REPLACED")
        return bytes(raw)
    finally:
        errors = []
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError:
                errors.append(fd)
        need(not errors, "READ_FD_CLOSE")


def pinned(pin, maximum=4 * 1024 * 1024):
    need(type(pin) is dict and set(pin) == {"path", "bytes", "sha256"} and type(pin["bytes"]) is int and
         type(pin["sha256"]) is str and re.fullmatch("[0-9a-f]{64}", pin["sha256"]), "EXACT_INPUT_PIN")
    raw = read(pin["path"], maximum)
    need(len(raw) == pin["bytes"] and sha(raw) == pin["sha256"], "INPUT_PIN_CHANGED")
    return raw


def module(raw, path, name):
    value = types.ModuleType(name)
    value.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), value.__dict__)
    return value


def replace(text, old, new, count=1):
    need(text.count(old) == count, "SOURCE_EDIT_ANCHOR_COUNT:" + old[:80])
    return text.replace(old, new)


def function_text(source, name, class_name=None):
    nodes = ast.parse(source).body
    if class_name:
        classes = [x for x in nodes if isinstance(x, ast.ClassDef) and x.name == class_name]
        need(len(classes) == 1, "EXACT_SOURCE_CLASS")
        nodes = classes[0].body
    matches = [x for x in nodes if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == name]
    need(len(matches) == 1, "EXACT_SOURCE_FUNCTION:" + name)
    node = matches[0]
    return "".join(source.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])


def reference_closure(expected):
    raw = read(HERE / "GENERATOR_PINS.json", 65536)
    need(sha(raw) == expected, "EXTERNALLY_PINNED_GENERATOR_CLOSURE")
    manifest = json.loads(raw)
    need(manifest["schema"] == "pocket4-successor-qa-generator-source-v1" and
         manifest["reference_commit"] == REF and 20 <= len(manifest["files"]) <= 64, "GENERATOR_MANIFEST")
    sources = {}
    for name, row in manifest["files"].items():
        p = Path(name)
        need(not p.is_absolute() and ".." not in p.parts and str(p) == name, "GENERATOR_SOURCE_PATH")
        data = read(HERE / name, 1024 * 1024)
        need(row == {"bytes": len(data), "sha256": sha(data)}, "GENERATOR_SOURCE_CHANGED:" + name)
        sources[name] = data.decode("utf-8")
    need("generate_successor_sources.py" in sources and "templates/source_contract.py.in" in sources,
         "GENERATOR_EXECUTABLE_CLOSURE_INCOMPLETE")
    return sources


def validate_request(request):
    need(type(request) is dict and set(request) == {"schema", "qa_build_input", "launcher_catalog", "package",
         "component", "generation_nonce", "public_text", "allowed_operations", "output_root"}, "CLOSED_GENERATION_REQUEST")
    need(request["schema"] == "pocket4-successor-qa-source-request-v1", "SOURCE_REQUEST_SCHEMA")
    package = request["package"]
    need(type(package) is str and PKG.fullmatch(package) and len(package) <= 64, "PACKAGE_BOUND")
    need(type(request["component"]) is str and
         re.fullmatch(re.escape(package) + r"/[A-Za-z0-9_.$]+", request["component"]), "EXACT_COMPONENT")
    need(type(request["generation_nonce"]) is str and re.fullmatch("[0-9a-f]{32}", request["generation_nonce"]), "NEW_GENERATION_NONCE")
    text = request["public_text"]
    need(type(text) is str and 0 < len(text.encode("utf-8")) <= 64 and all(ord(x) >= 32 for x in text), "BOUNDED_REVIEWED_PUBLIC_TEXT")
    operations = request["allowed_operations"]
    need(type(operations) is list and len(set(operations)) == len(operations) and
         {"state", "inspect"} <= set(operations) <= {"state", "inspect", "click", "set_text", "reveal_controls", "player_button"},
         "CLOSED_OWNED_OPERATION_POLICY")
    need(package == "tv.danmaku.bili" or not set(operations) & {"reveal_controls", "player_button"}, "BILI_PLAYER_OPERATIONS_ARE_NOT_GENERIC")
    path = request["output_root"]
    need(type(path) is str and re.fullmatch(r"/home/alex/work/pocket4-successor-qa-source-[0-9a-f]{32}", path), "NEW_SOURCE_DESTINATION")
    need(path.endswith(request["generation_nonce"]), "SOURCE_NONCE_PATH_BINDING")
    return request


def acquire_binding(request):
    supplied = json.loads(pinned(request["qa_build_input"]))
    need(supplied.get("schema") == "pocket4-successor-qa-build-input-v1" and
         supplied.get("build_performed") is False and supplied.get("UI_or_install_runtime_admitted") is False and
         supplied.get("helper_source_binary_qualification_inherited") is False and supplied.get("production_ready") is False,
         "ACTUAL_UNQUALIFIED_QA_INPUT_REQUIRED")
    gp = supplied["runtime_guard"]
    raw = read(gp["path"], 65536)
    need(sha(raw) == gp["sha256"], "ACTUAL_GUARD_SOURCE_PIN")
    guard_pin = {"path": gp["path"], "bytes": len(raw), "sha256": sha(raw)}
    guard = module(raw, gp["path"], "source_generation_actual_successor_guard")
    before = guard.current_guard()
    need(before["schema"] == "pocket4-successor-main-guard-v1", "SUCCESSOR_GUARD_TYPE")
    baseline = guard.current_baseline()
    need(baseline["schema"] == "pocket4-successor-runtime-baseline-v1" and
         baseline["framework_epoch"]["sha256"] != OLD_EPOCH and
         baseline["framework_epoch"] == supplied["framework_epoch"] and
         baseline["runtime_epoch_sha256"] == supplied["runtime_epoch_sha256"], "REAL_NEW_FRAMEWORK_REQUIRED")
    qualification = json.loads(pinned(guard.PINS["qualification"], 65536))
    need(qualification["identity_qualified"] is True and qualification["old_native_pidfd_deaths_proved"] is True,
         "ACTUAL_SUCCESSOR_QUALIFICATION_REQUIRED")
    target = request["package"]
    selected = sorted({target, "local.pocket4.actions.v2"})
    scope_raw = pinned(supplied["app_scope"])
    scope = json.loads(scope_raw)
    need(scope["schema"] == "pocket4-versioned-app-scope-v1" and scope["runtime_epoch_sha256"] == supplied["runtime_epoch_sha256"], "SAME_RUNTIME_APP_SCOPE")
    need(set(selected) <= set(scope["apps"]) and set(selected) <= set(supplied["packages"]), "TARGET_AND_EXISTING_ACTION_RUNNER_SCOPE_REQUIRED")
    app_guard = guard.check_app_scope(supplied["app_scope"], selected)
    need(app_guard["app_scope_sha256"] == supplied["app_scope"]["sha256"], "CURRENT_TARGET_BYTES_REQUIRED")
    packages = {name: scope["apps"][name]["uid"] for name in selected}
    need(all(type(uid) is int and 0 <= uid < 100000 and supplied["packages"][name] == uid for name, uid in packages.items()), "ACTUAL_USER_ZERO_UIDS")
    runtime = baseline["runtime"]
    need(supplied["classpath_values"] == runtime["classpath"]["values"] and
         supplied["held_init_identity"] == runtime["held"]["extra"]["android_init"]["held_proc"] and
         supplied["status"] == {"host_pid": runtime["held"]["process_snapshot"]["binding"]["processes"]["launcher"]["host_pid"]},
         "BUILD_INPUT_PROCESS_OR_CLASSPATH_CHANGED")
    directories = {}
    for package in selected:
        for kind, entry in scope["apps"][package]["data_directories"].items():
            if entry["status"] == "PRESENT":
                key = kind + "/0/" + package
                identity = {name: entry[name] for name in ("device", "inode", "uid", "gid")}
                need(supplied["app_directories"].get(key) == identity, "DATA_DIRECTORY_INPUT_DIFFERS")
                directories["/data/" + key] = identity
    catalog = json.loads(pinned(request["launcher_catalog"]))
    # The reference's exact API envelope is retained. It is roster evidence;
    # native launch must still return its own current successful task receipt.
    catalog_value = catalog.get("catalog", catalog)
    applications = catalog_value.get("applications")
    need(type(applications) is list and 0 < len(applications) <= 128 and
         any(x.get("component") == request["component"] and x.get("package") == target for x in applications),
         "EXACT_OBSERVED_LAUNCHER_COMPONENT_REQUIRED")
    pinned(NATIVE_CLI, 32 * 1024 * 1024)
    binding = {"schema": "pocket4-successor-derived-recorder-binding-v1", "package": target,
        "component": request["component"], "uid": packages[target], "user": 0,
        "runtime_guard": guard_pin, "baseline": guard.PINS["baseline"], "qualification": guard.PINS["qualification"],
        "runtime_epoch_sha256": supplied["runtime_epoch_sha256"], "framework_epoch": supplied["framework_epoch"],
        "app_scope": supplied["app_scope"], "packages": packages, "app_directories": directories,
        "held_init_identity": supplied["held_init_identity"], "classpath_values": supplied["classpath_values"],
        "status": supplied["status"], "native_cli": NATIVE_CLI,
        "launcher_catalog_reference": request["launcher_catalog"], "qa_input_reference": request["qa_build_input"],
        "launcher_resolver_reenumerated_by_generator": False,
        "public_text": request["public_text"], "allowed_operations": request["allowed_operations"],
        "generation_nonce": request["generation_nonce"], "old_Bili_unknown_reconciled": False,
        "Bili_Accept_authorized_in_Main": False, "Meituan_location_grant_authorized": False,
        "security_bypass_authorized": False, "UI_admitted": False, "production_ready": False}
    need(guard.current_guard() == before, "GENERATION_INPUT_RUNTIME_CHANGED")
    return binding, guard, before


def render_host(sources, binding):
    root = "reference/r5/"
    originals = {p[len(root):]: s for p, s in sources.items() if p.startswith(root)}
    pins = {name: (len(s.encode()), sha(s.encode())) for name, s in originals.items() if name.startswith("references/")}
    source = sources["templates/source_contract.py.in"]
    original = originals["source_contract.py"]
    original_pins = [x for x in ast.parse(original).body if isinstance(x, ast.Assign) and
                     any(isinstance(t, ast.Name) and t.id == 'REFERENCE_PINS' for t in x.targets)]
    need(len(original_pins) == 1 and pins == ast.literal_eval(original_pins[0].value), 'UNCHANGED_ORIGINAL_R5_REFERENCES_REQUIRED')
    constants = original[original.index('HELPER_ROOT = '):original.index('\n\ndef require')]
    verifier = function_text(original, "verify_shared_helper")
    source = source.replace("__BINDING_LITERAL__", repr(binding)).replace("__REFERENCE_PINS_LITERAL__", repr(pins))
    source = source.replace("__ORIGINAL_HELPER_CONSTANTS_AND_VERIFIER__", constants + "\n\n" + verifier)
    files = {name: text for name, text in originals.items() if name.startswith("references/")}
    files["source_contract.py"] = source
    recorder = originals["recorder.py"]
    methods = sources["templates/flow_methods.py.in"]
    for name in ("__init__", "guard"):
        recorder = replace(recorder, function_text(recorder, name, "Flow"), function_text(methods, name, "Flow"))
    old_ui = function_text(recorder, "ui", "Flow")
    recorder = replace(recorder, old_ui, old_ui.replace("def ui(", "def _existing_ui_observation(") + "\n\n" + function_text(methods, "ui", "Flow"))
    recorder = replace(recorder, "        self.source.runtime_and_app_guard(self.current_guard, attempted)\n",
        "        self.source.runtime_and_app_guard(self.current_guard, attempted)\n        self.source.pinned(self.source.BINDING['native_cli'], 32 * 1024 * 1024)\n")
    recorder = recorder.replace("PREEXISTING_BILIBILI_TASK_PRESERVED_NO_LAUNCH", "PREEXISTING_TARGET_TASK_PRESERVED_NO_LAUNCH")
    files["recorder.py"] = recorder
    main = originals["main_binding.py"]
    prefix = main[:main.index("class MainBinding:")]
    # Use only the exact successor zygote's held environ, never a discovered
    # input-bridge PID or invented environment defaults.
    prefix = replace(prefix, "        values = held.selected_classpaths(raw)\n", "        values = held.selected_classpaths(raw)\n        environment = selected_environment(raw)\n")
    prefix = replace(prefix, "        again = held.selected_classpaths(held.read_at(view.proc_fd, \"environ\", held.ENV_LIMIT, deadline))\n",
        "        again_raw = held.read_at(view.proc_fd, 'environ', held.ENV_LIMIT, deadline)\n        again = held.selected_classpaths(again_raw)\n        require(selected_environment(again_raw) == environment, 'HELD_ENVIRONMENT_CHANGED')\n        del again_raw\n")
    prefix = replace(prefix, '            "main_classpath_read": True}', '            "main_classpath_read": True}, environment')
    env_function = '''\ndef selected_environment(raw):
    keys = {'PATH', 'BOOTCLASSPATH', 'DEX2OATBOOTCLASSPATH', 'ANDROID_ART_ROOT', 'ANDROID_ASSETS',
        'ANDROID_BOOTLOGO', 'ANDROID_DATA', 'ANDROID_I18N_ROOT', 'ANDROID_ROOT', 'ANDROID_STORAGE',
        'ANDROID_TZDATA_ROOT', 'ASEC_MOUNTPOINT', 'DOWNLOAD_CACHE', 'EXTERNAL_STORAGE',
        'LOOP_MOUNTPOINT', 'STANDALONE_SYSTEMSERVER_JARS', 'SYSTEMSERVERCLASSPATH', 'LANG'}
    found = {}
    for row in raw.split(b'\\0'):
        if b'=' not in row:
            continue
        key, value = row.split(b'=', 1)
        name = key.decode('utf-8', 'strict')
        if name not in keys:
            continue
        require(name not in found and len(value) <= 65536, 'ENV_DUPLICATE_OR_BOUND')
        found[name] = value.decode('utf-8', 'strict')
    return found
\n'''
    files["main_binding.py"] = prefix + env_function + sources["templates/main_binding_class.py.in"]
    transport = originals["bound_android_transport.py"]
    transport = replace(transport, 'FRAMEWORK_EPOCH_SHA256 = "' + OLD_EPOCH + '"', 'FRAMEWORK_EPOCH_SHA256 = ' + repr(binding["framework_epoch"]["sha256"]))
    transport = replace(transport, 'EXPECTED_PACKAGE = "tv.danmaku.bili"', 'EXPECTED_PACKAGE = ' + repr(binding["package"]))
    transport = replace(transport, "EXPECTED_UID = 10117", "EXPECTED_UID = " + str(binding["uid"]))
    files["bound_android_transport.py"] = transport
    child = originals["existing_ui_entry.py"]
    start = child.index("    current_guard = contract.load('current_baseline_guard.py'")
    end = child.index("    source.verify_scope(scope, activation, contract)", start)
    child = child[:start] + "    current_guard = source.load_guard()\n    source.verify_saved_baseline(root)\n    scope = json.loads(source.bounded_file(root / 'scope.json'))\n    activation = source.activation()\n" + child[end:]
    child = replace(child, "    mutation = operation in ('click', 'set-text')\n", "    mutation = operation in ('click', 'set-text')\n    require(not mutation, 'MUTATION_REQUIRES_NEW_OWNED_QA_HELPER')\n")
    files["existing_ui_entry.py"] = child
    coordinator = originals["current_coordinator.py"]
    start, end = coordinator.index("BASELINE=Path("), coordinator.index("ENV={'PATH'")
    coordinator = coordinator[:start] + "BINDING=" + repr(binding) + "\nSOURCE_CONTRACT_SHA=" + repr(sha(source.encode())) + "\n" + coordinator[end:]
    start = coordinator.index("def guard_module():")
    coordinator = coordinator[:start] + '''def guard_module():
    source=module(read(HERE/'source_contract.py',expected=SOURCE_CONTRACT_SHA),HERE/'source_contract.py','successor_coordinator_source')
    return source.load_guard()
def current_baseline():
    return guard_module().current_baseline()
def main_guard(baseline=None,epoch=None):
    return guard_module().current_guard(baseline,action_attempted=False)
'''
    files["current_coordinator.py"] = coordinator
    for name, text in files.items():
        if name.endswith(".py"):
            compile(text, name, "exec")
    manifest = {"schema": 3, "artifact": "pocket4-successor-recorder-r5-v1", "binding_sha256": sha(canonical(binding)),
                "files": {p: {"bytes": len(s.encode()), "sha256": sha(s.encode())} for p, s in sorted(files.items())},
                "UI_admitted": False, "production_ready": False}
    return files, canonical(manifest) + b"\n"


def render_helper(sources, binding, recorder_manifest_sha, output_name):
    old_self = "org.droidloom.qa.bili.r9"
    helper_id = sha(canonical(binding))[:16]
    helper_self = "org.droidloom.qa.successor.p" + helper_id + ".r1"
    root = "reference/bili/"
    source_names = ["ActionRunner.java", "AndroidManifest.xml", "build_candidate.py", "qa_contract.py", "qa_adapter.py",
        "check_current_baseline.py", "check_idle_contract.py", "tests/InspectionIdleGateChecks.java",
        "src/org/droidloom/qa/bili/r9/InspectionIdleGate.java", "src/org/droidloom/qa/bili/r9/PlayerButtonTransaction.java",
        "src/org/droidloom/qa/bili/r9/TouchTransaction.java"]
    files = {}
    literals = {old_self: helper_self, "org/droidloom/qa/bili/r9": helper_self.replace(".", "/"),
        "pocket4-owned-bili-qa-v9": "pocket4-owned-successor-qa-v1", OLD_EPOCH: binding["framework_epoch"]["sha256"],
        OLD_BASELINE: binding["baseline"]["sha256"], OLD_QUALIFICATION: binding["qualification"]["sha256"],
        "pocket4-main-current-baseline-v1": "pocket4-successor-runtime-baseline-v1",
        "tv.danmaku.bili": binding["package"], r"tv\.danmaku\.bili": re.escape(binding["package"]),
        r"tv\\.danmaku\\.bili": re.escape(binding["package"]).replace("\\", "\\\\"),
        "微积分": binding["public_text"], "Owned Bili QA": "Owned Scoped QA",
        "pocket4-owned-bili-qa-r9-build-01": output_name,
        "pocket4-bilibili-owned-qa-r4-flow-": "pocket4-successor-qa-flow-"}
    # Text is JSON-escaped at its language constant below. Avoid putting a
    # quote/newline supplied by a request into source literals via replacement.
    del literals["微积分"]
    for name in source_names:
        text = sources[root + name]
        for before, after in literals.items():
            text = text.replace(before, after)
        text = text.replace("UID = 10117", "UID = " + str(binding["uid"]))
        text = text.replace("TARGET_UID = 10117", "TARGET_UID = " + str(binding["uid"]))
        text = text.replace('PUBLIC_SEARCH_QUERY = "微积分"', 'PUBLIC_SEARCH_QUERY = ' + json.dumps(binding["public_text"], ensure_ascii=True))
        name = name.replace("org/droidloom/qa/bili/r9", helper_self.replace(".", "/"))
        if name == "ActionRunner.java":
            name = "src/" + helper_self.replace(".", "/") + "/ActionRunner.java"
        files[name] = text
    q = files["qa_contract.py"]
    q = replace(q, "SCOPE_KEYS = {", "RUNTIME_EPOCH = " + repr(binding["runtime_epoch_sha256"]) + "\nAPP_SCOPE_SHA = " + repr(binding["app_scope"]["sha256"]) + "\nALLOWED_OPERATIONS = " + repr(tuple(binding["allowed_operations"])) + "\nSCOPE_KEYS = {'runtime_epoch_sha256', 'app_scope_sha256', ")
    q = replace(q, "            'FIXED_MAIN_BILI_SCOPE_REQUIRED')", "            'FIXED_MAIN_BILI_SCOPE_REQUIRED')\n    require(value['runtime_epoch_sha256'] == RUNTIME_EPOCH and value['app_scope_sha256'] == APP_SCOPE_SHA, 'EXACT_RUNTIME_AND_APP_VERSION_SCOPE_REQUIRED')")
    q = replace(q, "    op = value.get('op')\n", "    op = value.get('op')\n    require(op in ALLOWED_OPERATIONS, 'COMPILED_OPERATION_POLICY')\n")
    files["qa_contract.py"] = q
    java_name = "src/" + helper_self.replace(".", "/") + "/ActionRunner.java"
    java = files[java_name]
    java = replace(java, '    static final int TARGET_UID = ', '    static final String RUNTIME_EPOCH = ' + json.dumps(binding["runtime_epoch_sha256"]) + ';\n    static final String APP_SCOPE_SHA = ' + json.dumps(binding["app_scope"]["sha256"]) + ';\n    static final int TARGET_UID = ')
    java = replace(java, '            String op = string(request, "op", 16);', '            String op = string(request, "op", 16);\n            need(Arrays.asList(' + ', '.join(json.dumps(x) for x in binding["allowed_operations"]) + ').contains(op), "COMPILED_OPERATION_POLICY");')
    java = replace(java, 'keys(scope, "package", "uid", "user", "display", "activity", "window_token", "main_epoch_sha256", "main_baseline_schema", "main_baseline_sha256", "main_baseline_qualification_sha256");',
        'keys(scope, "package", "uid", "user", "display", "activity", "window_token", "main_epoch_sha256", "main_baseline_schema", "main_baseline_sha256", "main_baseline_qualification_sha256", "runtime_epoch_sha256", "app_scope_sha256");\n        need(RUNTIME_EPOCH.equals(string(scope, "runtime_epoch_sha256", 64)) && APP_SCOPE_SHA.equals(string(scope, "app_scope_sha256", 64)), "EXACT_RUNTIME_AND_APP_VERSION_SCOPE_REQUIRED");')
    if binding["package"] == "tv.danmaku.bili":
        anchor = '            Capture finalWindow = inspect(null, "action_final_window");'
        guard = '''            if (!editing) {
                String label = (text(current.target.getText()) + " " + text(current.target.getContentDescription()) + " " + text(current.target.getViewIdResourceName())).toLowerCase(java.util.Locale.ROOT);
                need(!label.matches("(?s).*(accept|consent|agreement|privacy|user_agree|同意|接受|确认协议).*"), "BILI_ACCEPT_NOT_AUTHORIZED_IN_MAIN");
            }
'''
        java = replace(java, anchor, guard + anchor)
    files[java_name] = java
    adapter = files["qa_adapter.py"]
    adapter = replace(adapter, "RECORDER_MANIFEST_SHA = '52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1'", "RECORDER_MANIFEST_SHA = " + repr(recorder_manifest_sha))
    adapter = replace(adapter, "    op = plan['operation']; keys = {'schema','operation','nonces'}", "    op = plan['operation']; keys = {'schema','operation','nonces'}\n    require(op in qa.ALLOWED_OPERATIONS, 'COMPILED_OPERATION_POLICY')")
    adapter = replace(adapter, "            'main_baseline_qualification_sha256':self.qa.MAIN_BASELINE_QUALIFICATION_SHA})", "            'main_baseline_qualification_sha256':self.qa.MAIN_BASELINE_QUALIFICATION_SHA,\n            'runtime_epoch_sha256':self.qa.RUNTIME_EPOCH, 'app_scope_sha256':self.qa.APP_SCOPE_SHA})")
    # An actual installed UID must be distinct from this target, not only from
    # the old Bili target UID and historical helper UIDs.
    adapter = replace(adapter, "        self.flow, self.recorder, self.qa, self.proof, self.uid = flow, recorder, qa, proof, helper_uid", "        require(helper_uid != qa.UID, 'HELPER_CANNOT_SHARE_TARGET_UID')\n        self.flow, self.recorder, self.qa, self.proof, self.uid = flow, recorder, qa, proof, helper_uid")
    adapter = replace(adapter, "    artifact = receipt.get('APK')", "    scope_controls = receipt.get('current_baseline_scope_controls', {})\n    require(scope_controls.get('source_sha256') == manifest['files']['check_current_baseline.py']['sha256'] and\n            scope_controls.get('report', {}).get('schema') == 'pocket4-successor-app-scope-controls-v1' and\n            scope_controls['report'].get('count') == 16 and scope_controls['report'].get('all_passed') is True and\n            scope_controls['report'].get('production_contract_sha256') == manifest['files']['qa_contract.py']['sha256'] and\n            scope_controls['report'].get('main_epoch_sha256') == manifest['framework_epoch_sha256'],\n            'ACTUAL_NEW_RUNTIME_AND_APP_SCOPE_CONTROLS_REQUIRED')\n    artifact = receipt.get('APK')")
    adapter = replace(adapter, "    result['ended_utc'] = recorder.now()", "    result['ended_utc'] = recorder.now()\n    if flow is not None:\n        result['epoch_sha256'] = flow.scope['epoch_sha256']")
    files["qa_adapter.py"] = adapter
    checks = files["check_current_baseline.py"]
    checks = replace(checks, "          'main_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA}", "          'main_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA,\n          'runtime_epoch_sha256':qa.RUNTIME_EPOCH, 'app_scope_sha256':qa.APP_SCOPE_SHA}")
    checks = replace(checks, "    qa.require(len(rows)==12,'EXACT_CURRENT_BASELINE_SCOPE_CASES')", "    for key in ('runtime_epoch_sha256','app_scope_sha256'):\n        no('missing_'+key,lambda v,k=key:v.pop(k))\n        no('wrong_'+key,lambda v,k=key:v.update({k:'0'*64}))\n    qa.require(len(rows)==16,'EXACT_CURRENT_BASELINE_SCOPE_CASES')")
    checks = checks.replace("'count':12", "'count':16").replace("pocket4-current-baseline-scope-controls-v1", "pocket4-successor-app-scope-controls-v1")
    files["check_current_baseline.py"] = checks
    idle = files["check_idle_contract.py"]
    idle = replace(idle, "                      'main_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA}}", "                      'main_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA,\n                      'runtime_epoch_sha256':qa.RUNTIME_EPOCH,'app_scope_sha256':qa.APP_SCOPE_SHA}}")
    files["check_idle_contract.py"] = idle
    builder = files["build_candidate.py"].replace("baseline_controls['count']==12", "baseline_controls['count']==16").replace("len(baseline_controls['cases'])==12", "len(baseline_controls['cases'])==16")
    builder = builder.replace("'owned-bili-qa-r9'", "'owned-successor-qa'").replace("CN=Pocket4 Owned Bili QA R8", "CN=Pocket4 Owned Scoped QA")
    files["build_candidate.py"] = builder
    installer = sources['templates/install_owned_helper.py.in']
    installer = installer.replace('__HELPER_PACKAGE_LITERAL__', repr(helper_self)).replace('__RECORDER_MANIFEST_LITERAL__', repr(recorder_manifest_sha))
    files['install_owned_helper.py'] = installer
    files['run_case.py'] = sources['templates/run_case.py.in'].replace('__RECORDER_MANIFEST_LITERAL__', repr(recorder_manifest_sha))
    for name, text in files.items():
        if name.endswith(".py"):
            compile(text, name, "exec")
    manifest = {"schema": "pocket4-successor-owned-qa-source-v1", "helper_package": helper_self,
                "source_reference_commit": REF, "framework_epoch_sha256": binding["framework_epoch"]["sha256"],
                "runtime_epoch_sha256": binding["runtime_epoch_sha256"], "app_scope_sha256": binding["app_scope"]["sha256"],
                "target_package": binding["package"], "target_uid": binding["uid"], "recorder_manifest_sha256": recorder_manifest_sha,
                "files": {p: {"bytes": len(s.encode()), "sha256": sha(s.encode())} for p, s in sorted(files.items())},
                "build_performed": False, "UI_admitted": False, "old_helper_qualification_inherited": False, "production_ready": False}
    return files, canonical(manifest) + b"\n", helper_self


def write_new(path, raw, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, mode)
    try:
        left = memoryview(raw)
        while left:
            done = os.write(fd, left)
            need(done > 0, "SOURCE_WRITE_PROGRESS")
            left = left[done:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return {"path": str(path), "bytes": len(raw), "sha256": sha(raw)}


def generate(request, expected):
    need(os.getuid() == os.geteuid() == 0, "ROOT_READ_ONLY_IDENTITY_BINDING_REQUIRED")
    validate_request(request)
    sources = reference_closure(expected)
    binding, guard, initial = acquire_binding(request)
    host, host_manifest = render_host(sources, binding)
    output_name = "pocket4-successor-qa-build-" + request["generation_nonce"]
    helper, helper_manifest, helper_self = render_helper(sources, binding, sha(host_manifest), output_name)
    root = Path(request["output_root"])
    need(root.parent.resolve() == root.parent and not root.exists(), "NEW_CANONICAL_GENERATION_ROOT")
    os.umask(0o077)
    root.mkdir(mode=0o700)
    receipt = {"schema": "pocket4-successor-qa-source-result-v1", "ok": False,
               "generator_manifest_sha256": expected, "request_sha256": sha(canonical(request)),
               "build_performed": False, "install_performed": False, "UI_actions": 0,
               "source_identity_is_not_runtime_QA": True, "production_ready": False}
    try:
        for name, files in (("recorder", host), ("helper", helper)):
            directory = root / name
            directory.mkdir(mode=0o700)
            for relative, text in sorted(files.items()):
                path = directory / relative
                path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                write_new(path, text.encode())
        host_pin = write_new(root / "recorder/source-manifest.json", host_manifest)
        helper_pin = write_new(root / "helper/SOURCE_PINS.json", helper_manifest)
        # This source publication stays private. The separately reviewed staging
        # step copies this immutable helper closure to a new UID1000-owned source
        # root; the original R9 build remains unprivileged and installs nothing.
        build_plan = {"schema": "pocket4-successor-qa-build-plan-v1", "target_package": binding["package"],
            "helper_package": helper_self, "recorder_manifest": host_pin, "helper_manifest": helper_pin,
            "build_output": "/home/alex/work/" + output_name,
            "build_caller_uid": 1000, "source_staging_required": True,
            "stage_argv": ["/usr/bin/python3", "-I", str(HERE / 'stage_helper_source.py'), "--stage-once", "--source", str(root / 'helper'), "--source-manifest-sha256", helper_pin['sha256'], "--output", "/home/alex/work/pocket4-successor-qa-build-source-" + request['generation_nonce']],
            "build_argv_after_exact_source_staging": ["/usr/bin/python3", "-I", "/home/alex/work/pocket4-successor-qa-build-source-" + request['generation_nonce'] + "/build_candidate.py", "--build-once", "--source-manifest-sha256", helper_pin["sha256"]],
            "build_result_required_state": "BUILT_STATIC_VERIFIED_ANDROID_UNRUN",
            "next_install_prerequisites": ["fresh helper absent for all Android users", "actual new build/APK/signer receipt pins", "exact current runtime and target App scope guards", "original action lease acquired", "single durable install intent"],
            "install_argv_inside_existing_held_R5_transport": ["/system/bin/cmd", "package", "install", "-R", "-t", "--user", "0", "--pkg", helper_self, "ACTUAL_OWNED_GUEST_APK"],
            "QA_prerequisites": ["exact installed helper bytes and fresh UID read back", "fresh R5 admission evidence", "successful new native launch receipt and task scope", "state/inspect/state restoration evidence", "fresh explicit per-step policy and nonces"],
            "ADB_dependency": False, "runtime_QA_pass_inherited": False, "UI_admitted": False}
        plan_pin = write_new(root / "build-plan.json", canonical(build_plan) + b"\n")
        need(guard.current_guard() == initial, "POST_GENERATION_RUNTIME_CHANGED")
        guard.check_app_scope(binding["app_scope"], sorted(binding["packages"]))
        reference_closure(expected)
        receipt.update(ok=True, recorder_manifest=host_pin, helper_manifest=helper_pin, build_plan=plan_pin,
                       helper_package=helper_self, target_package=binding["package"],
                       runtime_epoch_sha256=binding["runtime_epoch_sha256"], app_scope_sha256=binding["app_scope"]["sha256"])
    except BaseException as error:
        receipt["error"] = {"type": type(error).__name__, "code": str(error)[:256]}
    receipt_pin = write_new(root / "generation-result.json", canonical(receipt) + b"\n")
    return {**receipt, "result": receipt_pin}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--request-sha256", required=True)
    parser.add_argument("--generator-manifest-sha256", required=True)
    args = parser.parse_args()
    try:
        raw = read(args.request, 65536)
        need(sha(raw) == args.request_sha256, "SOURCE_REQUEST_PIN")
        result = generate(json.loads(raw), args.generator_manifest_sha256)
    except BaseException as error:
        result = {"ok": False, "error": {"type": type(error).__name__, "code": str(error)[:256]},
                  "build_performed": False, "install_performed": False, "UI_actions": 0, "production_ready": False}
    text = canonical(result)
    need(len(text) <= 65536, "STDOUT_BOUND")
    print(text.decode(), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
