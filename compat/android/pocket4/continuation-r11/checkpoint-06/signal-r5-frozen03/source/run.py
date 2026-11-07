#!/usr/bin/env python3
"""One-shot private-cell signal qualification; never targets Main for actions.

The --check phase is read-only. The --run phase requires externally pinned
preparation, full host-suite qualification and this separately frozen runner.
Only root's explicit device execution may invoke either phase on Pocket4.
"""
from pathlib import Path
import argparse
import ast
import datetime
import hashlib
import importlib.util
import json
import os
import re
import socket
import stat
import struct
import subprocess
import sys
import threading
import time
import traceback

sys.dont_write_bytecode = True
PREPARATION_MANIFEST_SHA = "3f12e8bcde951712a20208aaeed04f1125bac58993ce1a3f5a93e4f950a9b103"
ORIGINAL_SHA = "895ecbfec6d04170adf0dbc16a0fd18d3de0b78317efec86de1846295dfcddb8"
HOST_WRAPPER_MANIFEST_SHA = "ad47718c72d7fd8ecb3ce4147fd3e6dbc2ec6f662d079103bd7ecb5a55863bc5"
RETAINED_FUNCTIONS = (
    "now", "sha", "save", "event", "call", "props", "proc", "unit_launch", "owned", "endpoint",
    "ctl", "discover_init", "atext", "current_guest_epoch", "engine_loaded", "bootstrap_ready", "run", "cleanup",
)
CASES = (("r2", "svc"), ("r2", "smc-handler"), ("r2", "smc-default"), ("r3", "smc-mask-edit"))
HELPER_SOURCE_SHA = "adf5b08f7854bec061ab8d2a208f3414339701c816218881e6550afde2e6c31c"
HELPER_BINARY_SHA = "21ba02ff60ba07667c3b5601c1ff9cb9b2d9cce2fae9290a6f39e47c18126689"
HELPER_QUALIFICATION_SHA = "3e3dd5c9ae1b4e913d7a688bb338507162cbc211bb897658a539948ffb6f93e3"


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_manifest(path, expected):
    need(Path(path).is_absolute() and re.fullmatch(r"[0-9a-f]{64}", expected or ""), "explicit source manifest pin required")
    need(sha(path) == expected, "source manifest changed")
    value = json.loads(Path(path).read_text())
    for name, row in value["files"].items():
        relative = Path(name)
        need(not relative.is_absolute() and ".." not in relative.parts, "bad source manifest path")
        target = Path(path).parent / relative
        need(target.is_file() and sha(target) == row["sha256"], "source file changed: " + name)
    return value


def verify_prepared_sets(config, prepared, base, manifest, expected_probes, engine_size, layout):
    """Pure complete-set check, independent of prepared.json's self description."""
    need(prepared["schema"] == 1 and prepared["kind"] == "isolated-owned-signal-canary-r1" and
         prepared["arm"] == "signal-mask-r1" and prepared["production_ready"] is False,
         "unexpected preparation contract")
    need(prepared["name"] == config["attempt"]["name"] and
         prepared["engine_sha256"] == config["engine"]["sha256"] and
         prepared["presenter"] == config["presenter"]["path"] and
         prepared["presenter_sha256"] == config["presenter"]["sha256"] and
         prepared["framework_guard"] == config["framework_guard"]["path"] and
         prepared["framework_guard_sha256"] == config["framework_guard"]["sha256"],
         "prepared action targets differ from the reviewed input contract")
    # Do not rely on a self-described list or the neighboring self-reported
    # hash. Reconstruct every required set from the frozen input contract.
    engine_sources = [r["source"] for r in base["android_file_overrides"]
                      if r["target"] == "/system/lib64/libberberis_arm64.so"]
    need(len(engine_sources) == 1, "engine override is ambiguous")
    engine_relative = str(Path(engine_sources[0]).relative_to(config["base"]["root"]))
    expected_records = []
    for row in manifest["records"]:
        expected_records.append({"relative": row["relative"], "sha256": row["sha256"], "bytes": row["bytes"]})
        if row["relative"] == engine_relative:
            expected_records[-1].update(sha256=config["engine"]["sha256"], bytes=engine_size)
    need(len(expected_records) == 86 and prepared["copied_records"] == expected_records,
         "prepared runtime record set is incomplete or differs")
    expected_probes = {key: dict(value) for key, value in expected_probes.items()}
    for revision, row in expected_probes.items():
        row["path"] = str(layout["stage"] / "tests" / ("signal-" + revision + ".apk"))
    need(prepared["apks"] == expected_probes, "prepared r2/r3 APK set differs")
    images = prepared["data_images"]
    need(isinstance(images, list) and len(images) == 2 and
         [(r["name"], r["bytes"]) for r in images] == [("data.img", 8 * 1024**3), ("metadata.img", 128 * 1024**2)] and
         all(r["fresh_O_EXCL_created"] is True for r in images), "fresh image set incomplete")
    expected_cases = {revision + "-" + case for revision, case in CASES}
    need(set(prepared["nonces"]) == expected_cases, "owned case nonce set differs")
    nonces = [prepared["nonce"], *prepared["nonces"].values()]
    need(len(set(nonces)) == 5 and all(re.fullmatch(r"[0-9a-f]{32}", n or "") for n in nonces), "nonce uniqueness/format differs")


def expected_cell_spec(base, config, layout):
    result = json.loads(json.dumps(base))
    stage = layout["stage"]
    root = Path(config["base"]["root"])
    for key in ("android_file_overrides", "android_runtime_directories"):
        for row in result[key]:
            row["source"] = str(stage / Path(row["source"]).relative_to(root))
    result["android_init"] = str(stage / Path(result["android_init"]).relative_to(root))
    result.update(host_uid=config["attempt"]["host_uid"],
                  subordinate_uids={"start": config["attempt"]["subid_start"], "count": 100000},
                  subordinate_gids={"start": config["attempt"]["subid_start"], "count": 100000},
                  runtime_dir=str(layout["cell_runtime"]), data_dir=str(layout["data"]), image_dir=str(stage),
                  vendor_image=str(stage / "images/vendor.raw.img"),
                  denial_socket=str(layout["user_runtime"] / "droidloom/native-bridge.sock"))
    return result


def qualified_host_wrapper(program_manifest, manifest_path):
    host_manifest = verify_manifest(manifest_path, HOST_WRAPPER_MANIFEST_SHA)
    need(host_manifest["artifact"] == "isolated-signal-canary-runtime-r1", "host qualification wrapper differs")
    for name in ("host_suite.py", "host-test-contract.json", "r16-host-layout.json"):
        need(program_manifest["files"][name] == host_manifest["files"][name], "host qualification code or contract changed")
    # verify_report checks HERE/source-manifest.json internally.  Its module
    # must be loaded from the externally verified original qualification
    # directory; an identical copied .py file does not preserve that context.
    return load_module(Path(manifest_path).parent / "host_suite.py", "pinned_signal_host_suite")


def verify_helper_qualification(path, expected):
    need(expected == HELPER_QUALIFICATION_SHA and sha(path) == expected,
         "external namespace-entry qualification pin differs")
    value = json.loads(Path(path).read_text())
    need(value.get("schema") == 1 and value.get("protocol") == "owned-held-namespace-entry-v1"
         and value.get("helper_source_sha256") == HELPER_SOURCE_SHA
         and value.get("helper_binary_sha256") == HELPER_BINARY_SHA
         and value.get("qualified_for_owned_namespace_entry") is True
         and value.get("host_controls_passed") == 14
         and value.get("six_namespace_host_entry_passed") is True
         and value.get("Main_readonly_entry_passed") is True
         and value.get("qualified_for_whole_process_tree_cleanup") is False
         and value.get("candidate_production_ready") is False,
         "namespace helper qualification scope or result differs")
    need(set(value.get("evidence", {})) == {"host14", "sixns", "main_readonly"},
         "namespace helper evidence set differs")
    for record in value["evidence"].values():
        need(sha(record["path"]) == record["sha256"], "actual helper control receipt changed")
        terminal = record["terminal"]
        need(terminal["state"] == "succeeded" and terminal["exit_code"] == 0
             and terminal["cancelled"] is False and terminal["timed_out"] is False
             and terminal["output_complete"] is True and terminal["output_durable"] is True
             and terminal["terminal_publication_confirmed"] is True,
             "helper control does not have a complete successful terminal")
    return {"path": str(path), "sha256": expected,
            "helper_source_sha256": HELPER_SOURCE_SHA, "helper_binary_sha256": HELPER_BINARY_SHA,
            "qualification_binding_module_sha256": value["binding_module_sha256"],
            "scope": "shared entry helper mechanism; this private runtime FD/classpath adapter is separately qualified",
            "whole_process_tree_cleanup_qualified": False}


def admit(args):
    need(sys.flags.optimize == 0, "optimized Python is prohibited")
    source = Path(args.preparation_source).resolve(strict=True)
    original_manifest = source / "source-manifest.json"
    verify_manifest(original_manifest, PREPARATION_MANIFEST_SHA)
    program_manifest = verify_manifest(args.source_manifest, args.source_manifest_sha256)
    need(Path(args.source_manifest).parent.resolve() == Path(__file__).parent.resolve(), "runtime manifest directory differs")
    need(program_manifest["artifact"] == "isolated-signal-canary-runtime-r5" and
         {"run.py", "host_suite.py", "framework_census.py", "held_runtime.py",
          "failure_evidence.py", "held_namespace_entry.rs", "cleanup_owned.py"}.issubset(program_manifest["files"]), "incomplete runtime source contract")
    # The native binary and full 3793-registration suite already passed using
    # the exact frozen r1 host wrapper.  Bind that independent qualification;
    # a diagnostic-only Android runner revision must not relabel its source.
    host_suite = qualified_host_wrapper(program_manifest, args.host_wrapper_source_manifest)
    prep = load_module(source / "prepare.py", "pinned_signal_preparation")
    assess = load_module(source / "assess.py", "pinned_signal_assessment")
    need(args.namespace_helper_sha256 == HELPER_BINARY_SHA and
         args.namespace_helper_source_sha256 == HELPER_SOURCE_SHA, "unqualified namespace helper pin")
    need(program_manifest["files"]["held_namespace_entry.rs"]["sha256"] == HELPER_SOURCE_SHA,
         "namespace helper source differs from reviewed runtime source")
    for path, digest, executable in ((args.namespace_helper, args.namespace_helper_sha256, True),
                                    (args.namespace_helper_source, args.namespace_helper_source_sha256, False)):
        prep.pinned_file({"path": path, "sha256": digest}, executable=executable)
        info = Path(path).lstat()
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_mode & 0o022 == 0,
             "namespace helper source/binary is aliased or writable by others")
    verify_helper_qualification(args.namespace_helper_qualification, args.namespace_helper_qualification_sha256)
    config = prep.load_inputs(Path(args.inputs), args.inputs_sha256)
    need(Path(config["runner_manifest"]["path"]).resolve() == original_manifest and
         config["runner_manifest"]["sha256"] == PREPARATION_MANIFEST_SHA,
         "input contract selects another preparation revision")
    layout = prep.paths(config)
    prepared_path = layout["evidence"] / "prepared.json"
    need(sha(prepared_path) == args.prepared_sha256, "externally pinned preparation receipt changed")
    prepared = json.loads(prepared_path.read_text())
    base = prep.read_json(config["base"]["spec"], prep.BASE_SPEC_SHA)
    manifest = prep.read_json(config["base"]["manifest"], prep.BASE_MANIFEST_SHA)
    verify_prepared_sets(config, prepared, base, manifest, prep.probe_binding(config),
                         Path(config["engine"]["path"]).stat().st_size, layout)
    need(json.loads((layout["stage"] / "cell.json").read_text()) == expected_cell_spec(base, config, layout),
         "staged cell spec differs from exact fresh-data/private-socket transformation")
    prep.check_prepared(config, args.inputs_sha256)
    need(sha(prepared_path) == args.prepared_sha256, "preparation changed during checks")
    suite = host_suite.verify_report(Path(args.host_suite_receipt), args.host_suite_sha256,
                                    config["candidate_build_receipt"], config["engine"], HOST_WRAPPER_MANIFEST_SHA)
    # The original fixture depends on these actual host launch tools. Their
    # current exact input pins are a separate reviewed runtime contract.
    helpers = prep.read_json({"path": args.host_launch_inputs, "sha256": args.host_launch_inputs_sha256})
    need(helpers["schema"] == 1 and set(helpers["tools"]) == {
        "/usr/local/libexec/droidloom-compat/unshare", "/usr/bin/unshare", "/usr/bin/ip", "/usr/bin/python3"},
        "complete host launch input set required")
    for path, digest in helpers["tools"].items():
        prep.pinned_file({"path": path, "sha256": digest}, executable=True)
    need(helpers["tools"]["/usr/local/libexec/droidloom-compat/unshare"] == manifest["host_compat_wrapper_sha256"] and
         helpers["tools"]["/usr/bin/unshare"] == manifest["host_unshare_sha256"], "historical launch fixture changed")
    return prep, assess, config, prepared, suite, helpers


def original_runtime(prep, config, prepared, source):
    path = source / "v5_original.py"
    need(sha(path) == ORIGINAL_SHA, "original v5 bytes changed")
    tree = ast.parse(path.read_text())
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in RETAINED_FUNCTIONS]
    need({node.name for node in selected} == set(RETAINED_FUNCTIONS), "original v5 function set changed")
    # Retain the immutable v5 definitions for the reference/negative controls.
    # R5 installs its separately reviewed exact-retirement cleanup below.
    bootstrap = [node for node in tree.body if isinstance(node, ast.Assign) and
                 any(isinstance(t, ast.Name) and t.id == "BOOTSTRAP_ARTIFACTS" for t in node.targets)]
    need(len(bootstrap) == 1, "original bootstrap constant missing")
    stage, runtime, user = map(Path, (prepared["stage"], prepared["runtime"], prepared["user_runtime"]))
    scope = {"__name__": "pinned_v5_runtime_functions", "Path": Path, "datetime": datetime,
             "hashlib": hashlib, "json": json, "os": os, "re": re, "stat": stat, "subprocess": subprocess,
             "time": time, "traceback": traceback, "socket": socket, "struct": struct, "sys": sys,
             "P": prepared, "HERE": Path(prepared["evidence"]), "S": stage, "Q": runtime, "R": user,
             "SOCK": runtime / "control.sock", "SPEC": stage / "cell.json", "NAME": prepared["name"],
             "NONCE": prepared["nonce"], "NS": ("mnt", "pid", "uts", "ipc", "net", "cgroup"),
             "ENV": {"PATH": "/usr/local/libexec/droidloom-compat:/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
             "ROWS": [], "INIT": None, "LAUNCHER": None, "PRIVATE_EPOCH": None,
             "CPU_INVENTORY_PATH": Path(config["cpu_inventory"]["path"]),
             "CPU_INVENTORY": prep.read_json(config["cpu_inventory"], prep.CPU_INVENTORY_SHA),
             "EPOCH_GUARD": prep.load_guard(config),
             "BOOTSTRAP_ARTIFACTS": ast.literal_eval(bootstrap[0].value),
             "RESULT": {"schema": "isolated-owned-signal-runtime-r5", "arm": prepared["arm"],
                        "production_ready": False, "commercial_app_claim": False}}
    # Function definitions only. The old module's top-level source loaders,
    # hardcoded Main discovery and Activity/default-alarm flows never execute.
    exec(compile(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])), str(path), "exec"), scope)
    scope["main_snapshot"] = lambda: prep.main_snapshot(config, scope["EPOCH_GUARD"])
    scope["main_resources"] = lambda: prep.main_snapshot(config, scope["EPOCH_GUARD"])["resources"]
    cleanup = load_module(Path(__file__).with_name("cleanup_owned.py"), "pinned_owned_cleanup_r5")
    cleanup.install(scope)
    return scope


class ProbeFlow:
    def __init__(self, scope, assess):
        self.s = scope
        self.a = assess
        self.installed = {}
        self.before = None
        self.mutation_attempted = False
        self.target = None
        self.classpath_env = None
        self.sampler = None
        self.failure_labels = set()

    def discover_init(self):
        need(self.target is None, "private init binding cannot be replaced")
        value = self.s["discover_init_original"]()
        self.target = self.s["HELD_API"].HeldTarget(value, self.s["NAMESPACE_HELPER"],
                                                   self.s["NAMESPACE_HELPER_SHA"])
        self.s["save"]("private-held-entry.json", self.target.record)
        return value

    def release_bindings(self, failures):
        report = {"before_private_cell_stop": True, "all_commands_joined": False,
                  "all_samplers_joined": self.sampler is None or not self.sampler.is_alive()}
        try:
            if self.target is not None:
                if not report["all_samplers_joined"]:
                    self.target.seal_admission()
                    raise RuntimeError("sampler still active; authority FDs retained until controller exit")
                self.target.close()
                report["all_commands_joined"] = True
                report["released"] = True
            else:
                report["released"] = True
                report["never_acquired"] = True
        except BaseException as error:
            failures.append("held-entry-release: " + repr(error))
            report["error"] = repr(error)
            report["released"] = False
        try:
            self.s["save"]("private-held-entry-release.json", report)
        except BaseException as error:
            failures.append("held-entry-release-receipt: " + repr(error))

    def bind_environment(self):
        need(self.classpath_env is None, "private classpath cannot be replaced")
        values, receipt = self.s["HELD_API"].bind_classpaths(self.target, self.s["PRIVATE_EPOCH"],
            self.s["EPOCH_GUARD"]["process_identity"], self.guard)
        self.classpath_env = values
        self.s["save"]("private-classpath-admission.json", receipt)

    def guard(self, attempted=False):
        s = self.s
        s["EPOCH_GUARD"]["require_unchanged"]({"schema": "pocket4-framework-epoch-v1",
            "binding": s["P"]["main_before"]["framework_binding"],
            "sha256": s["P"]["main_before"]["framework_sha256"]}, action_attempted=attempted)
        if s["PRIVATE_EPOCH"] is not None:
            s["EPOCH_GUARD"]["require_unchanged"](s["PRIVATE_EPOCH"], action_attempted=attempted)
        need(s["INIT"] is not None and s["proc"](s["INIT"]["pid"]) == s["INIT"], "private init generation changed")
        s["owned"](next(row for row in s["ROWS"] if row["role"] == "daemon"))
        if self.target is not None:
            self.target.verify()

    def guest_command(self, args, uid, timeout):
        env = ["PATH=/system/bin:/system/xbin:/apex/com.android.art/bin", "ANDROID_ROOT=/system", "ANDROID_DATA=/data",
               "ANDROID_ART_ROOT=/apex/com.android.art", "ANDROID_I18N_ROOT=/apex/com.android.i18n",
               "ANDROID_TZDATA_ROOT=/apex/com.android.tzdata", "EXTERNAL_STORAGE=/sdcard"]
        if list(args[:2]) == ["/system/bin/am", "instrument"]:
            need(self.classpath_env is not None and
                 set(self.classpath_env) == set(self.s["HELD_API"].REQUIRED_CLASSPATHS) and
                 all(self.classpath_env.values()), "private classpath admission required before instrumentation")
        if self.classpath_env is not None:
            env += [key + "=" + self.classpath_env[key] for key in self.s["HELD_API"].REQUIRED_CLASSPATHS]
        return ["/system/bin/env", "-i", *env, "/system/bin/timeout", "-k", "2",
                str(max(1, timeout - 5)), "/system/xbin/su", str(uid), *map(str, args)]

    def argv(self, args, uid, timeout):
        need(self.target is not None, "held private namespace/root binding is required")
        return self.target.entry(self.guest_command(args, uid, timeout))

    def android(self, args, uid=2000, timeout=35, check=True):
        self.guard()
        with self.argv(args, uid, timeout) as (argv, authorities):
            p = subprocess.run(argv, capture_output=True, timeout=timeout, env=self.s["ENV"],
                               close_fds=True, pass_fds=authorities)
        self.guard()
        if check:
            need(p.returncode == 0, "private read command failed: " + repr(args[:3]))
        return p

    def command(self, label, args, *, data=None, mutation=False, timeout=35, check=True):
        self.guard(self.mutation_attempted)
        if mutation:
            self.s["save"](label + "-attempt.json", {"argv": args, "utc": self.s["now"](),
                "init": self.s["INIT"], "private_epoch_sha256": self.s["PRIVATE_EPOCH"]["sha256"],
                "automatic_retry": False})
            self.mutation_attempted = True
        try:
            with self.argv(args, 2000, timeout) as (argv, authorities):
                p = subprocess.run(argv, input=data, capture_output=True, timeout=timeout,
                                   env=self.s["ENV"], close_fds=True, pass_fds=authorities)
        except subprocess.TimeoutExpired as error:
            self.s["save"](label + ".stdout", error.stdout or b"")
            self.s["save"](label + ".stderr", error.stderr or b"")
            self.s["save"](label + "-terminal.json", {"returncode": None, "timed_out": True,
                "outcome_unknown": True, "automatic_retry": False})
            if mutation:
                self.s["RESULT"].setdefault("primary_command_failure", {"label": label, "returncode": None,
                    "timed_out": True, "outcome_unknown": True, "automatic_retry": False})
            raise
        self.s["save"](label + ".stdout", p.stdout)
        self.s["save"](label + ".stderr", p.stderr)
        self.s["save"](label + "-terminal.json", {"returncode": p.returncode, "timed_out": False,
            "mutation_attempted": mutation, "automatic_retry": False})
        if mutation and p.returncode != 0:
            self.s["RESULT"].setdefault("primary_command_failure", {"label": label, "returncode": p.returncode,
                "timed_out": False, "automatic_retry": False})
        self.guard(self.mutation_attempted)
        if check:
            need(p.returncode == 0, "private command failed: " + label + " status=" + str(p.returncode))
        return p

    def packages(self, label):
        result = self.command(label, ["/system/bin/cmd", "package", "list", "packages", "-U", "--show-versioncode", "--user", "0"])
        return self.a.package_identities(result.stdout)

    def package_binding(self, revision, label):
        row = self.s["P"]["apks"][revision]
        all_packages = self.packages(label + "-identities")
        identity = all_packages.get(row["package"])
        need(identity is not None and identity["version_code"] == row["version"] and
             10000 <= identity["uid"] < 100000, "owned package version/UID differs")
        need(sum(value["uid"] == identity["uid"] for value in all_packages.values()) == 1, "owned probe UID is shared")
        result = self.command(label + "-path", ["/system/bin/cmd", "package", "path", row["package"]])
        lines = result.stdout.decode("utf-8", "strict").splitlines()
        need(len(lines) == 1 and lines[0].startswith("package:/data/app/"), "owned APK path is ambiguous")
        path = Path(lines[0].removeprefix("package:"))
        need(".." not in path.parts and row["package"] in path.parent.name, "owned APK path differs")
        fd = self.target.open_root(str(path), os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as actual:
            before = os.fstat(actual.fileno())
            need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size == row["bytes"],
                 "installed owned APK metadata differs")
            need(hashlib.file_digest(actual, "sha256").hexdigest() == row["sha256"],
                 "installed owned APK hash differs")
            after = os.fstat(actual.fileno())
            need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                 (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
                 "installed APK changed during held-root read")
        binding = {"package": row["package"], **identity, "apk_path": str(path), "apk_sha256": row["sha256"]}
        if revision in self.installed:
            need(binding == self.installed[revision], "installed owned package identity changed")
        self.guard(self.mutation_attempted)
        return binding

    def install(self, revision):
        row = self.s["P"]["apks"][revision]
        before = self.packages(revision + "-before-install")
        need(row["package"] not in before, "owned package already present; no replacement")
        raw = Path(row["path"]).read_bytes()
        need(hashlib.sha256(raw).hexdigest() == row["sha256"], "staged APK changed")
        result = self.command(revision + "-install", ["/system/bin/cmd", "package", "install", "-t", "--user", "0",
            "--abi", "arm64-v8a", "-S", str(len(raw))], data=raw, mutation=True, timeout=45)
        need(result.stdout.strip() == b"Success", "owned install success not confirmed")
        after = self.packages(revision + "-after-install")
        need({k: v for k, v in after.items() if k != row["package"]} == before, "preexisting private packages changed")
        self.installed[revision] = self.package_binding(revision, revision + "-installed")
        self.s["save"](revision + "-install-binding.json", self.installed[revision])

    def sample_engine(self, package, uid, pin, stop, records, errors):
        s = self.s
        zygote = s["PRIVATE_EPOCH"]["binding"]["processes"]["zygote64"]
        seen = set()
        try:
            while not stop.is_set():
                need(s["EPOCH_GUARD"]["process_identity"](zygote["host_pid"]) == zygote, "private zygote changed while sampling")
                children = (Path("/proc") / str(zygote["host_pid"]) / "task" / str(zygote["host_pid"]) / "children").read_text().split()
                for value in children:
                    try:
                        pid = int(value)
                        if (Path("/proc") / value / "cmdline").read_bytes().split(b"\0")[0] != package.encode():
                            continue
                        identity = s["EPOCH_GUARD"]["process_identity"](pid)
                        key = (pid, identity["start_ticks"])
                        if key in seen:
                            continue
                        need(identity["uids"] == [uid] * 4 and identity["namespaces"]["pid"] == s["INIT"]["ns"]["pid"], "probe sampler scope differs")
                        maps = (Path("/proc") / value / "maps").read_text()
                        if not any("libberberis_arm64.so" in line and "r-xp" in line for line in maps.splitlines()):
                            continue
                        actual = Path("/proc") / value / "root/system/lib64/libberberis_arm64.so"
                        metadata = actual.stat()
                        need((metadata.st_dev, metadata.st_ino, metadata.st_size) ==
                             (pin["device"], pin["inode"], pin["bytes"]), "probe mounted another engine inode")
                        mapped = []
                        for line in maps.splitlines():
                            if "libberberis_arm64.so" not in line:
                                continue
                            fields = line.split(None, 5)
                            major, minor = fields[3].split(":")
                            need(int(fields[4]) == pin["inode"] and
                                 os.makedev(int(major, 16), int(minor, 16)) == pin["device"], "probe mapped another engine inode")
                            mapped.append(line)
                        need(mapped and any("r-xp" in line for line in mapped), "engine executable mapping absent")
                        evidence = {"engine_sha256": pin["sha256"], "mapped_inode": pin["inode"],
                                    "mapped_device": pin["device"], "actual_host_maps": mapped,
                                    "hash_bound_by_held_file_before_and_after_case": True}
                        need(s["EPOCH_GUARD"]["process_identity"](pid) == identity, "probe changed during mapping read")
                        records.append({"process": identity, "binding": evidence, "observed_utc": s["now"]()})
                        seen.add(key)
                    except (FileNotFoundError, ProcessLookupError):
                        continue
                    except s["EPOCH_GUARD"]["EpochError"] as error:
                        if error.code not in ("PROCESS_IDENTITY_UNAVAILABLE", "PROCESS_IDENTITY_UNSTABLE"):
                            raise
                        # The app can finish while an observation is in flight.
                        # Never count this as a stable mapping; a matching
                        # complete observation remains mandatory after return.
                        continue
                stop.wait(.01)
        except BaseException as error:
            errors.append(repr(error))

    def instrument_with_mapping(self, label, row, binding, case, nonce):
        s = self.s
        engine_path = "/system/lib64/libberberis_arm64.so"
        with os.fdopen(self.target.open_root(engine_path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as held:
            metadata = os.fstat(held.fileno())
            pin = {"device": metadata.st_dev, "inode": metadata.st_ino, "bytes": metadata.st_size,
                   "sha256": hashlib.file_digest(held, "sha256").hexdigest()}
            need(stat.S_ISREG(metadata.st_mode) and pin["sha256"] == s["P"]["engine_sha256"], "private mounted engine differs")
            stop, mappings, errors = threading.Event(), [], []
            sampler = threading.Thread(target=self.sample_engine,
                args=(row["package"], binding["uid"], pin, stop, mappings, errors), daemon=True)
            self.sampler = sampler
            sampler.start()
            try:
                result = self.command(label + "-instrument", ["/system/bin/am", "instrument", "-w", "-r", "-e", "case", case,
                    "-e", "nonce", nonce, row["package"] + "/" + row["instrumentation"]], mutation=True, timeout=35, check=False)
            finally:
                stop.set(); sampler.join(timeout=5)
                s["save"](label + "-engine-observations.json", {"observations": mappings, "errors": errors,
                    "sampler_stopped": not sampler.is_alive(), "held_engine_before": pin})
            need(not sampler.is_alive() and not errors, "probe engine sampler did not complete cleanly")
            held.seek(0)
            need(hashlib.file_digest(held, "sha256").hexdigest() == pin["sha256"], "held candidate engine changed during case")
            after_fd = self.target.open_root(engine_path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                after = os.fstat(after_fd)
            finally:
                os.close(after_fd)
            need((after.st_dev, after.st_ino, after.st_size) == (pin["device"], pin["inode"], pin["bytes"]),
                 "private engine mount changed during case")
            s["save"](label + "-engine-pin-after.json", pin)
            return result, mappings

    def case(self, revision, case):
        s = self.s
        label = revision + "-" + case
        row = s["P"]["apks"][revision]
        nonce = s["P"]["nonces"][label]
        binding = self.package_binding(revision, label + "-before")
        self.command(label + "-force-stop", ["/system/bin/am", "force-stop", "--user", "0", row["package"]], mutation=True)
        deadline = time.monotonic() + 5
        while True:
            remaining = self.android(["/system/bin/pidof", row["package"]], 0, check=False)
            need(remaining.returncode in (0, 1) and not remaining.stderr.strip(), "owned process absence query failed")
            if remaining.returncode == 1 and not remaining.stdout.strip():
                break
            need(time.monotonic() < deadline, "previous owned probe process did not stop")
            time.sleep(.05)
        directory = "/data/user/0/" + row["package"] + "/files/signal-probe/"
        claim, final = directory + nonce + ".claim", directory + nonce + ".json"
        need(not self.target.exists(claim) and not self.target.exists(final), "nonce was already claimed")
        s["save"](label + "-case-claim.json", {"nonce": nonce, "case": case, "binding": binding,
            "engine_sha256": s["P"]["engine_sha256"], "invocations_allowed": 1})
        try:
            result, mappings = self.instrument_with_mapping(label, row, binding, case, nonce)
            self.guard(True)
            need(result.returncode == 0, "owned instrumentation command failed: " + label + " status=" + str(result.returncode))
            claim_bytes, claim_meta = self.target.read_file(claim, 16384, single_link=True)
            final_bytes, final_meta = self.target.read_file(final, 256 * 1024, single_link=True)
            need(claim_meta["uid"] == binding["uid"] and final_meta["uid"] == binding["uid"],
                 "owned durable result UID differs")
            s["save"](label + "-durable.claim", claim_bytes)
            s["save"](label + "-durable.json", final_bytes)
            outcome = self.a.assess_case(result.stdout, final_bytes, claim_bytes, row["package"], case, nonce, result.returncode)
            bound = [m for m in mappings if m["process"]["namespace_pids"][-1] == outcome["guest_pid"]]
            need(len(bound) == 1, "exact probe process candidate engine mapping was not observed")
            need(len(mappings) == 1, "multiple probe process generations observed for one invocation")
            outcome["actual_mapped_engine"] = bound[0]
            s["save"](label + "-assessment.json", outcome)
            self.package_binding(revision, label + "-after")
            s["RESULT"].setdefault("cases", []).append(outcome)
        except BaseException as error:
            if label not in self.failure_labels:
                self.failure_labels.add(label)
                try:
                    self.s["FAILURE_EVIDENCE"].capture(self, label, row, binding, nonce, error)
                except BaseException as capture_error:
                    s["RESULT"].setdefault("failure_evidence_errors", []).append(repr(capture_error))
            raise

    def cleanup_packages(self):
        if self.before is None:
            return
        failures = []
        for revision in ("r3", "r2"):
            row = self.s["P"]["apks"][revision]
            try:
                current = self.packages(revision + "-cleanup-inventory")
                if row["package"] not in current:
                    continue
                need(row["package"] not in self.before, "refusing to remove a preexisting package")
                binding = self.package_binding(revision, revision + "-cleanup-binding")
                self.s["save"](revision + "-cleanup-exact-identity.json", binding)
                result = self.command(revision + "-uninstall", ["/system/bin/cmd", "package", "uninstall", "--user", "0", row["package"]], mutation=True, timeout=45)
                need(result.stdout.strip() == b"Success", "owned package removal not confirmed")
                targets = [str(Path(binding["apk_path"]).parent), "/data/data/" + row["package"],
                           "/data/user/0/" + row["package"], "/data/user_de/0/" + row["package"]]
                deadline = time.monotonic() + 10
                while True:
                    self.guard(True)
                    remaining = [p for p in targets if self.target.exists(p)]
                    if not remaining or time.monotonic() >= deadline:
                        break
                    time.sleep(.2)
                self.s["save"](revision + "-owned-path-removal.json", {"paths": targets, "remaining": remaining})
                need(not remaining, "owned code/data remains after uninstall")
            except BaseException as error:
                failures.append(revision + ": " + repr(error))
        try:
            after = self.packages("private-packages-final")
            need(after == self.before, "private baseline package identities were not restored")
            self.s["RESULT"]["private_package_baseline_restored"] = True
        except BaseException as error:
            failures.append("package-baseline: " + repr(error))
        self.s["RESULT"]["package_cleanup_errors"] = failures
        self.s["RESULT"]["own_packages_removed"] = not failures

    def run(self):
        s = self.s
        need(self.before is None and not self.installed and not self.mutation_attempted,
             "initial framework capture is prohibited after any probe action")
        s["FRAMEWORK_CENSUS"].capture_initial(s, self.guard)
        self.bind_environment()
        s["bootstrap_ready"]()
        self.before = self.packages("private-packages-baseline")
        need(set(s["BOOTSTRAP_ARTIFACTS"]).issubset(self.before), "private bootstrap is incomplete")
        need(not any(row["package"] in self.before for row in s["P"]["apks"].values()), "probe package preexists fresh fixture")
        try:
            self.install("r2")
            for case in ("svc", "smc-handler", "smc-default"):
                self.case("r2", case)
            self.install("r3")
            self.case("r3", "smc-mask-edit")
            s["RESULT"]["all_owned_contracts_complete"] = True
        finally:
            self.cleanup_packages()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("check", "run"))
    for name in ("inputs", "inputs-sha256", "prepared-sha256", "preparation-source", "source-manifest",
                 "source-manifest-sha256", "host-suite-receipt", "host-suite-sha256", "host-launch-inputs", "host-launch-inputs-sha256",
                 "host-wrapper-source-manifest", "namespace-helper", "namespace-helper-sha256",
                 "namespace-helper-source", "namespace-helper-source-sha256",
                 "namespace-helper-qualification", "namespace-helper-qualification-sha256"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        prep, assess, config, prepared, suite, helpers = admit(args)
    except Exception as error:
        print(json.dumps({"state": "ADMISSION_FAILED_NO_ACTIONS_NO_RETRY", "error": repr(error)}))
        return 1
    if args.phase == "check":
        print(json.dumps({"state": "RUNTIME_INPUTS_CHECKED_NO_ACTIONS", "prepared_sha256": args.prepared_sha256,
                          "host_suite_sha256": args.host_suite_sha256, "services_started": False}))
        return 0
    scope = original_runtime(prep, config, prepared, Path(args.preparation_source))
    scope["FRAMEWORK_CENSUS"] = load_module(Path(__file__).with_name("framework_census.py"), "pinned_signal_framework_census_r2")
    scope["HELD_API"] = load_module(Path(__file__).with_name("held_runtime.py"), "pinned_signal_held_runtime_r5")
    scope["FAILURE_EVIDENCE"] = load_module(Path(__file__).with_name("failure_evidence.py"), "pinned_signal_failure_evidence_r5")
    scope["NAMESPACE_HELPER"] = args.namespace_helper
    scope["NAMESPACE_HELPER_SHA"] = args.namespace_helper_sha256
    flow = ProbeFlow(scope, assess)
    scope["discover_init_original"] = scope["discover_init"]
    scope["discover_init"] = flow.discover_init
    scope["release_held_binding"] = flow.release_bindings
    scope["android"] = flow.android
    scope["run_probes"] = flow.run

    def source_contract():
        verify_manifest(args.source_manifest, args.source_manifest_sha256)
        verify_manifest(Path(args.preparation_source) / "source-manifest.json", PREPARATION_MANIFEST_SHA)
        verify_manifest(args.host_wrapper_source_manifest, HOST_WRAPPER_MANIFEST_SHA)
        need(sha(args.inputs) == args.inputs_sha256 and sha(Path(prepared["evidence"]) / "prepared.json") == args.prepared_sha256,
             "runtime input/receipt changed")
        need(sha(args.host_launch_inputs) == args.host_launch_inputs_sha256, "host launch input receipt changed")
        for tool, digest in {**config["tools"], **helpers["tools"]}.items():
            need(sha(tool) == digest, "host tool changed")
        need(sha(args.host_suite_receipt) == args.host_suite_sha256, "host suite receipt changed")
        verify_helper_qualification(args.namespace_helper_qualification, args.namespace_helper_qualification_sha256)
        need(sha(args.namespace_helper) == HELPER_BINARY_SHA and
             sha(args.namespace_helper_source) == HELPER_SOURCE_SHA, "namespace helper source/binary changed")
        return {"runtime_manifest_sha256": args.source_manifest_sha256, "preparation_manifest_sha256": PREPARATION_MANIFEST_SHA,
                "host_qualification_wrapper_manifest_sha256": HOST_WRAPPER_MANIFEST_SHA,
                "input_sha256": args.inputs_sha256, "prepared_sha256": args.prepared_sha256,
                "host_suite_sha256": args.host_suite_sha256, "host_launch_inputs_sha256": args.host_launch_inputs_sha256,
                "namespace_helper_sha256": HELPER_BINARY_SHA, "namespace_helper_source_sha256": HELPER_SOURCE_SHA,
                "namespace_helper_qualification_sha256": HELPER_QUALIFICATION_SHA}

    scope["source_contract"] = source_contract
    prep.write_new(Path(prepared["evidence"]) / "run.claim.json", {"started_utc": scope["now"](),
        **source_contract(), "nonces": prepared["nonces"], "automatic_retry": False})
    result = scope["RESULT"]
    result["host_suite"] = suite
    result["namespace_entry_qualification"] = verify_helper_qualification(
        args.namespace_helper_qualification, args.namespace_helper_qualification_sha256)
    try:
        scope["run"]()
        result["run_returned"] = True
    except BaseException as error:
        result["error"] = repr(error)
        result["traceback"] = traceback.format_exc()
        try:
            scope["event"]("failed", error=repr(error))
        except BaseException as write_error:
            result.setdefault("evidence_errors", []).append("failed-event: " + repr(write_error))
    finally:
        # The R5 cleanup owns exact late reconciliation and independent
        # retirement attempts. Recording failure must not suppress cleanup.
        try:
            scope["cleanup"]()
        except BaseException as error:
            result.setdefault("cleanup", {}).setdefault("errors", []).append(repr(error))
            result.setdefault("first_cleanup_error", repr(error))
        result["finished_utc"] = scope["now"]()
        complete = (result.get("run_returned") and not result.get("error") and
                    not result.get("cleanup", {}).get("errors") and result.get("main_preserved") and
                    result.get("all_owned_contracts_complete") and result.get("own_packages_removed") and
                    result.get("owned_memory_events_zero") and result.get("adbd_before_cleanup") == "stopped" and
                    result.get("source_contract_preserved"))
        result["state"] = "OWNED_SYNC_SIGNAL_CANARY_PASS" if complete else "INCOMPLETE_OR_FAILED_NO_RETRY"
        try:
            scope["save"]("runtime-result.json", result)
        except BaseException as write_error:
            message = "runtime-result-write: " + repr(write_error)
            result.setdefault("cleanup", {}).setdefault("errors", []).append(message)
            result.setdefault("first_cleanup_error", message)
            result["state"] = "INCOMPLETE_OR_FAILED_NO_RETRY"
    print(json.dumps({key: result.get(key) for key in ("state", "error", "primary_command_failure",
        "first_cleanup_error", "main_preserved", "own_packages_removed", "cleanup", "finished_utc")}))
    return 0 if result["state"] == "OWNED_SYNC_SIGNAL_CANARY_PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"state": "RUNNER_ERROR_RECONCILIATION_REQUIRED", "error": repr(error),
                          "action_outcome": "UNKNOWN_CHECK_DURABLE_CLAIM_AND_RECEIPTS", "automatic_retry": False}))
        raise SystemExit(1)
