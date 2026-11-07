#!/usr/bin/env python3
"""Pinned preparation/checks for one isolated Pocket4 signal canary.

check-inputs and check-prepared are read-only. prepare creates only the new
owned stage/data/evidence paths and formats its freshly O_EXCL-created images.
No command in this module starts Android, a desktop service or an application.
There is no recovery/retry/delete-existing mode. Any partial attempt is retained.
"""
from pathlib import Path
import argparse
import datetime
import grp
import hashlib
import json
import os
import pwd
import re
import stat
import subprocess
import sys
import uuid

ORIGINAL_SHA = "895ecbfec6d04170adf0dbc16a0fd18d3de0b78317efec86de1846295dfcddb8"
BASE_MANIFEST_SHA = "31885dffa33fe30b0249d37acf437c00b348a0ac1020f8c56b427a8dac743183"
BASE_SPEC_SHA = "944110b00770d948de050b92efe46d510f7afc142cf2c5742d4d2a898fad00ce"
GUARD_SHA = "f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288"
ACTIVATION_SHA = "7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615"
CPU_INVENTORY_SHA = "590d32e10c5a86934afbd18eebd620d5a07f0e13a4c4af2e4094fac801dc5c62"
V5_MANIFEST_SHA = "72d3151d28485f536b9f28b9575b248da92c6b289998e28066a82a8a2f776f67"
PRESENTER_SHA = "47f34d5f68783a372283cb63a42034d5899e270524cca40122bf28fd5e903f24"
SIGNAL_PINS_SHA = "6a24ef53595e9d8da458a626effbfca4280a5de18c90ad1d5dd036ad3e936bf2"
R2_PINS_SHA = "b5d03eb02ad073180fd3a680518bfac3be42b7df292caa3ba74b4139581d458f"
R3_PINS_SHA = "1a17f89bf0ab6d03cc6d592528735c23012c3af38bc3b57cae008659631fc456"
MAIN_RESOURCE_KEYS = ("memory.high", "memory.max", "cpu.max", "memory.swap.max", "pids.max")
TOOL_PATHS = (
    "/usr/bin/systemd-run", "/usr/bin/systemctl", "/usr/bin/dbus-daemon",
    "/usr/bin/sway", "/usr/bin/nsenter", "/usr/bin/cp", "/usr/bin/env",
    "/usr/bin/timeout", "/usr/bin/journalctl", "/usr/sbin/mkfs.ext4",
)
PROBES = {
    "r2": ("org.droidloom.signalprobe", 1, "org.droidloom.signalprobe.SignalProbeInstrumentation", R2_PINS_SHA),
    "r3": ("org.droidloom.signalprobe.r3", 3, "org.droidloom.signalprobe.r3.SignalProbeInstrumentation", R3_PINS_SHA),
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def pinned_file(record, fixed=None, executable=False):
    require(isinstance(record, dict), "missing pinned file record")
    path = Path(record.get("path", ""))
    expected = record.get("sha256", "")
    require(path.is_absolute() and re.fullmatch(r"[0-9a-f]{64}", expected or ""), "explicit absolute path/hash required")
    require(not any(part in (".", "..") for part in path.parts), "noncanonical pinned path")
    metadata = path.stat()
    require(stat.S_ISREG(metadata.st_mode), "pinned input is not a regular file: " + str(path))
    require(not executable or metadata.st_mode & 0o111, "pinned tool is not executable")
    if fixed is not None:
        require(expected == fixed, "different frozen input selected: " + str(path))
    require(sha(path) == expected, "pinned input changed: " + str(path))
    return path


def read_json(record, fixed=None):
    return json.loads(pinned_file(record, fixed).read_text())


def new_path(value, parent, prefix):
    require(isinstance(value, str), "explicit new owned path required")
    path = Path(value)
    require(path.is_absolute() and path.parent == Path(parent) and path.name.startswith(prefix),
            "unexpected owned path: " + str(path))
    require(re.fullmatch(r"[A-Za-z0-9_-]+", path.name), "unsafe owned basename")
    for ancestor in path.parents:
        if ancestor.exists():
            require(not ancestor.is_symlink() and ancestor.is_dir(), "owned path has non-directory or symlink parent")
    return path


def paths(config):
    attempt = config["attempt"]
    name = attempt["name"]
    require(re.fullmatch(r"p4-signal-[a-z0-9_-]{8,64}", name), "new signal attempt name required")
    result = {
        "evidence": new_path(attempt["evidence"], "/home/alex/work", "pocket4-signal-canary-"),
        "stage": new_path(attempt["stage"], "/opt", "p4-signal-"),
        "data": new_path(attempt["data"], "/var/lib", "p4-signal-"),
        "runtime": new_path(attempt["runtime"], "/run", "p4-signal-"),
        "user_runtime": new_path(attempt["user_runtime"], "/run/user/1000", "p4-signal-"),
        "cell_runtime": Path("/run/droidloom/cells") / ("u" + str(attempt["host_uid"])),
    }
    require(all(result[k].name == name for k in ("stage", "data", "runtime", "user_runtime")),
            "stage/data/runtime names must equal attempt name")
    require(len(set(result.values())) == len(result), "owned paths overlap")
    return result


def call(argv, timeout=60):
    proc = subprocess.run(list(map(str, argv)), capture_output=True, timeout=timeout,
                          env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "LC_ALL": "C"})
    require(proc.returncode == 0, "read/preparation command failed: " + repr(argv[:3]) + " " + proc.stderr.decode(errors="replace")[-1200:])
    return proc.stdout


def properties(unit):
    proc = subprocess.run(["/usr/bin/systemctl", "show", unit, "-p", "LoadState", "-p", "ActiveState",
                           "-p", "MainPID", "-p", "InvocationID", "-p", "ControlGroup", "-p", "Description",
                           "-p", "ExecStart"], capture_output=True, text=True, timeout=20)
    values = dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)
    require(proc.returncode == 0 or values.get("LoadState") == "not-found", "unit observation failed")
    return values


def load_guard(config):
    path = pinned_file(config["framework_guard"], GUARD_SHA)
    namespace = {"__name__": "pinned_signal_canary_epoch_guard", "__file__": str(path)}
    exec(compile(path.read_bytes(), str(path), "exec"), namespace)
    return namespace


def main_snapshot(config, guard=None):
    guard = guard or load_guard(config)
    activation = read_json(config["main_activation"], ACTIVATION_SHA)
    epoch = activation["framework_epoch"]
    guard["require_unchanged"](epoch, action_attempted=False)
    init = epoch["binding"]["processes"]["init"]["host_pid"]
    observed = guard["capture_android"](init)
    require(observed["binding"] == epoch["binding"], "Main framework epoch changed")
    daemon = properties("droidloomd.service")
    require(daemon.get("ActiveState") == "active" and int(daemon.get("MainPID", "0")) > 0, "Main daemon is not the retained live baseline")
    for key in ("ActiveState", "MainPID", "InvocationID", "ControlGroup"):
        require(daemon[key] == activation["daemon_unit"][key], "Main daemon activation changed: " + key)
    retained_processes = {}
    for key in ("daemon_process", "presenter_process", "launcher_process"):
        expected = activation[key]
        actual = guard["process_identity"](expected["host_pid"])
        require(actual == expected, "Main process generation changed: " + key)
        retained_processes[key] = actual
    group = daemon["ControlGroup"]
    require(group.startswith("/") and ".." not in Path(group).parts, "bad Main cgroup path")
    cgroup = Path("/sys/fs/cgroup") / group.lstrip("/")
    resources = {key: (cgroup / key).read_text().strip() for key in MAIN_RESOURCE_KEYS}
    expected_resources = config["main_resource_baseline"]
    require(expected_resources == activation["limits"], "Main resource baseline differs from activation")
    require(resources == expected_resources, "Main resource bounds changed")
    main_spec = json.loads(Path("/etc/droidloom/cell.json").read_text())
    data_stat = Path(main_spec["data_dir"]).stat()
    data_identity = {"device": data_stat.st_dev, "inode": data_stat.st_ino,
                     "uid": data_stat.st_uid, "gid": data_stat.st_gid}
    require(data_identity == activation["data_directory"], "Main data directory identity changed")
    engine_sha = sha(Path("/proc") / str(init) / "root/system/lib64/libberberis_arm64.so")
    require(engine_sha == activation["engine_sha256"], "Main mounted engine changed")
    guard["require_unchanged"](epoch, action_attempted=False)
    return {"framework_binding": observed["binding"], "framework_sha256": observed["sha256"],
            "daemon": daemon, "resources": resources, "config_sha256": sha("/etc/droidloom/cell.json"),
            "retained_processes": retained_processes, "data_directory": data_identity,
            "engine_sha256": engine_sha,
            "activation_sha256": config["main_activation"]["sha256"]}


def candidate_binding(config):
    pins = read_json(config["signal_fix_pins"], SIGNAL_PINS_SHA)
    receipt = read_json(config["candidate_build_receipt"])
    inputs = read_json(config["candidate_build_inputs"])
    engine_path = pinned_file(config["engine"])
    require(inputs["status"] == "inputs_captured", "candidate inputs are not a pre-build receipt")
    require(receipt["status"] == "selected_artifacts_built" and receipt["scope"] == "native-engine-only", "candidate build not complete")
    require(receipt["tests_requested"] is True, "complete host suite was not built")
    require(receipt["logical_targets"] == ["libberberis_arm64", "berberis_arm64_host_tests"], "unexpected candidate target closure")
    require(receipt["installation_performed"] is False and receipt["full_runtime_rebuilt"] is False, "unexpected build scope")
    for key, value in inputs.items():
        if key != "status":
            require(receipt.get(key) == value, "candidate input/final receipt mismatch: " + key)
    require(receipt["engine"]["sha256"] == config["engine"]["sha256"], "engine hash not bound by build receipt")
    require(receipt["engine"]["path"] == str(engine_path), "engine path is not the exact build output")
    output = Path(receipt["output_directory"])
    require(output.is_absolute() and output.resolve(strict=True) == output, "noncanonical candidate output")
    require(engine_path == output / "target/product/droidloom_x86_64/system/lib64/libberberis_arm64.so",
            "engine is outside the selected output layout")
    require(engine_path.resolve(strict=True) == engine_path, "candidate engine path is aliased")
    require(Path(config["candidate_build_receipt"]["path"]) ==
            output / "target/product/droidloom_x86_64/droidloom-native-engine-source.json",
            "candidate final receipt path differs")
    require(Path(config["candidate_build_inputs"]["path"]) ==
            output / "target/product/droidloom_x86_64/droidloom-native-engine-inputs.json",
            "candidate input receipt path differs")
    require(receipt["engine"]["elf"]["machine"] == "EM_X86_64", "wrong host engine ABI")
    require(receipt["engine"]["metadata"]["soname"] == "libberberis_arm64.so", "engine SONAME mismatch")
    with engine_path.open("rb") as stream:
        header = stream.read(20)
    require(len(header) == 20 and header[:6] == b"\x7fELF\x02\x01" and
            int.from_bytes(header[18:20], "little") == 62, "candidate bytes are not x86_64 ELF64")
    for change in pins["changes"]:
        relative, digest = change["path"], change["sha256"]
        require(receipt["source_snapshot"]["files"].get(relative) == digest, "raw signal candidate differs: " + relative)
        require(receipt["effective_teto_files"].get(relative) == digest, "signal candidate projection differs: " + relative)
    return receipt


def probe_binding(config):
    result = {}
    require(set(config["probes"]) == set(PROBES), "only frozen r2/r3 probes are allowed")
    for revision, (package, version, component, pins_sha) in PROBES.items():
        row = config["probes"][revision]
        pins = read_json(row["source_pins"], pins_sha)
        build = read_json(row["build_receipt"])
        apk = pinned_file(row["apk"])
        require(build["state"] == "BUILT_STATIC_VERIFIED_ANDROID_UNRUN", "probe build not qualified")
        require(build["package"] == package and build["ABI"] == "arm64-v8a", "probe package/ABI mismatch")
        require(build["APK"]["path"] == str(apk) and build["APK"]["sha256"] == row["apk"]["sha256"], "APK differs from build receipt")
        require(build["APK"]["bytes"] == apk.stat().st_size, "APK size differs from build receipt")
        require(build["no_activity"] is True and build["no_permissions"] is True, "probe component/permission scope differs")
        # The builder receipt binds all source bytes. Source pins bind the
        # immutable versions; compare their common files, including the pins.
        require(build["source_sha256"].get("SOURCE_PINS.json") == pins_sha, "probe build did not use frozen source pins")
        require(isinstance(pins.get("files"), list) and len(pins["files"]) == 6,
                "unexpected frozen probe source manifest")
        for identity in pins["files"]:
            relative, expected = identity["path"], identity["sha256"]
            require(build["source_sha256"].get(relative) == expected, "probe source/build mismatch: " + relative)
        result[revision] = {"package": package, "version": version, "instrumentation": component,
                            "path": str(apk), "sha256": row["apk"]["sha256"], "bytes": apk.stat().st_size}
    return result


def check_identity_allocation(config):
    attempt = config["attempt"]
    uid, start = attempt["host_uid"], attempt["subid_start"]
    require(type(uid) is int and 2000 <= uid < 60000, "explicit unused host UID required")
    require(type(start) is int and start >= 100000 and start + 100000 < 2**32, "invalid subordinate range")
    for lookup in (pwd.getpwuid, grp.getgrgid):
        try:
            lookup(uid)
            raise RuntimeError("host UID/GID already named")
        except KeyError:
            pass
    for path in [Path("/etc/droidloom/cell.json")] + list(Path("/opt").glob("*/cell.json")):
        cell = json.loads(path.read_text())
        # Its own already-created spec is checked against prepared.json later.
        if path == Path(attempt["stage"]) / "cell.json":
            continue
        require(cell.get("host_uid") != uid, "host UID already used by a cell")
        for key in ("subordinate_uids", "subordinate_gids"):
            interval = cell.get(key, {})
            if "start" in interval:
                require(interval["start"] + interval["count"] <= start or interval["start"] >= start + 100000,
                        "subordinate range overlaps an existing cell")
    for name in ("subuid", "subgid"):
        for line in Path("/etc", name).read_text().splitlines():
            _, begin, count = line.split(":")
            begin, count = int(begin), int(count)
            require(begin + count <= start or begin >= start + 100000, "subordinate range overlaps allocation")


def validate_inputs(config, prepared=False):
    require(sys.flags.optimize == 0, "optimized Python disables the retained v5 assertions")
    require(os.geteuid() == 0 and os.getegid() == 0, "checks/preparation require root for the owned fixture and read-only Main epoch")
    require(config.get("schema") == 1, "unsupported input contract")
    layout = paths(config)
    source_manifest = read_json(config["runner_manifest"])
    source_root = Path(__file__).parent
    require(source_manifest["schema"] == 1 and source_manifest["deployed"] is False,
            "unexpected runner source manifest")
    for relative, identity in source_manifest["files"].items():
        relative = Path(relative)
        require(not relative.is_absolute() and ".." not in relative.parts, "bad runner manifest path")
        require(sha(source_root / relative) == identity["sha256"], "runner source changed")
    original = Path(__file__).with_name("v5_original.py")
    require(sha(original) == ORIGINAL_SHA, "original successful v5 source changed")
    require(set(config["tools"]) == set(TOOL_PATHS), "complete exact tool pins required")
    for tool in TOOL_PATHS:
        pinned_file({"path": tool, "sha256": config["tools"][tool]}, executable=True)
    base = config["base"]
    base_root = Path(base["root"])
    require(base_root == Path("/opt/p4-media-composer-diagnostic-20261102-chat2-r5"), "unexpected historical fixture selected")
    base_spec = read_json(base["spec"], BASE_SPEC_SHA)
    manifest = read_json(base["manifest"], BASE_MANIFEST_SHA)
    require(manifest["spec_sha256"] == BASE_SPEC_SHA, "frozen fixture manifest/spec differ")
    require(Path(base["spec"]["path"]) == base_root / "cell.json" and
            Path(base["manifest"]["path"]) == base_root / "media-canary-manifest.json", "fixture metadata path mismatch")
    records = manifest["records"]
    require(len(records) == 86 and len({r["relative"] for r in records}) == 86, "fixture record set changed")
    require(base_spec["host_uid"] == 2191 and base_spec["shared_storage_directories"] == [], "base fixture contract changed")
    for row in records:
        relative = Path(row["relative"])
        require(not relative.is_absolute() and ".." not in relative.parts, "bad fixture relative path")
        source = Path(row["frozen"])
        require(source == base_root / relative, "fixture record escapes frozen root")
        metadata = source.lstat()
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_uid == 0 and metadata.st_nlink == 1 and
                metadata.st_mode & 0o022 == 0 and metadata.st_size == row["bytes"], "unsafe frozen record: " + str(source))
        require(sha(source) == row["sha256"], "frozen runtime record changed: " + str(source))
    pinned_file(config["presenter"], PRESENTER_SHA, executable=True)
    pinned_file(config["framework_guard"], GUARD_SHA)
    pinned_file(config["cpu_inventory"], CPU_INVENTORY_SHA)
    original_manifest = read_json(config["original_runner_manifest"], V5_MANIFEST_SHA)
    require(original_manifest["files"]["run_arm-v5-once.py"] == ORIGINAL_SHA and
            original_manifest["inventory_sha256"] == CPU_INVENTORY_SHA, "original v5 reference differs")
    build = candidate_binding(config)
    probes = probe_binding(config)
    check_identity_allocation(config)
    for key, path in layout.items():
        if prepared and key in ("evidence", "stage", "data"):
            require(path.is_dir() and not path.is_symlink(), "prepared directory missing or aliased")
        else:
            require(not path.exists() and not path.is_symlink(), "new owned path already exists: " + str(path))
    for role in ("bus", "sway", "presenter", "daemon"):
        require(properties(config["attempt"]["name"] + "-" + role + ".service").get("LoadState") == "not-found",
                "owned unit name already exists")
    main = main_snapshot(config)
    return {"layout": layout, "base_spec": base_spec, "records": records,
            "build": build, "probes": probes, "main": main}


def write_new(path, value, mode=0o444):
    path = Path(path)
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(path, mode)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def prepare(config, input_path, input_sha):
    checked = validate_inputs(config)
    layout = checked["layout"]
    available = os.statvfs("/opt")
    require(available.f_bavail * available.f_frsize >= 12 * 1024**3, "private staging free-space guard failed")
    evidence = layout["evidence"]
    evidence.mkdir(mode=0o700)
    write_new(evidence / "prepare.claim.json", {"started_utc": now(), "input_sha256": input_sha,
              "main_before": checked["main"], "services_started": False})
    status = {"status": "PREPARING", "services_started": False, "input_sha256": input_sha}
    try:
        stage, data = layout["stage"], layout["data"]
        stage.mkdir(mode=0o755)
        data.mkdir(mode=0o700)
        copied = []
        for row in checked["records"]:
            target = stage / row["relative"]
            target.parent.mkdir(parents=True, exist_ok=True)
            call(["/usr/bin/cp", "--reflink=auto", "--sparse=always", "--no-clobber", row["frozen"], target], 180)
            os.chown(target, 0, 0)
            mode = row["mode"]
            os.chmod(target, int(mode, 0) if isinstance(mode, str) else mode)
            require(sha(target) == row["sha256"], "staged runtime copy differs")
            copied.append({"relative": row["relative"], "sha256": row["sha256"], "bytes": row["bytes"]})
        cfg = json.loads(json.dumps(checked["base_spec"]))
        overrides = [row for row in cfg["android_file_overrides"] if row["target"] == "/system/lib64/libberberis_arm64.so"]
        require(len(overrides) == 1, "expected one private engine override")
        base_root = Path(config["base"]["root"])
        relative = Path(overrides[0]["source"]).relative_to(base_root)
        engine = stage / relative
        require(any(row["relative"] == str(relative) for row in copied), "engine not in frozen record set")
        engine.unlink()  # only the verified copy in this just-created owned stage
        call(["/usr/bin/cp", "--reflink=auto", "--no-clobber", config["engine"]["path"], engine])
        os.chown(engine, 0, 0)
        os.chmod(engine, 0o444)
        require(sha(engine) == config["engine"]["sha256"], "staged new engine differs")
        for row in copied:
            if row["relative"] == str(relative):
                row.update(sha256=config["engine"]["sha256"], bytes=engine.stat().st_size)
        for key in ("android_file_overrides", "android_runtime_directories"):
            for row in cfg[key]:
                row["source"] = str(stage / Path(row["source"]).relative_to(base_root))
        cfg["android_init"] = str(stage / Path(cfg["android_init"]).relative_to(base_root))
        attempt = config["attempt"]
        cfg.update(host_uid=attempt["host_uid"], subordinate_uids={"start": attempt["subid_start"], "count": 100000},
                   subordinate_gids={"start": attempt["subid_start"], "count": 100000},
                   runtime_dir=str(layout["cell_runtime"]), data_dir=str(data), image_dir=str(stage),
                   vendor_image=str(stage / "images/vendor.raw.img"),
                   denial_socket=str(layout["user_runtime"] / "droidloom/native-bridge.sock"))
        write_new(stage / "cell.json", cfg)
        images = []
        for name, size, label in (("data.img", 8 * 1024**3, "userdata"), ("metadata.img", 128 * 1024**2, "metadata")):
            image = data / name
            fd = os.open(image, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.truncate(size)
                stream.flush()
                os.fsync(stream.fileno())
            call(["/usr/sbin/mkfs.ext4", "-F", "-m", "0", "-L", label, "-O", "verity,^orphan_file",
                  "-E", "lazy_itable_init=1,lazy_journal_init=1", image], 180)
            metadata = image.stat()
            images.append({"name": name, "bytes": size, "device": metadata.st_dev, "inode": metadata.st_ino,
                           "sha256_before_first_boot": sha(image), "fresh_O_EXCL_created": True})
        (stage / "tests").mkdir()
        apks = {}
        for revision, row in checked["probes"].items():
            target = stage / "tests" / ("signal-" + revision + ".apk")
            call(["/usr/bin/cp", "--no-clobber", row["path"], target])
            os.chown(target, 0, 0)
            os.chmod(target, 0o444)
            require(sha(target) == row["sha256"], "staged probe APK differs")
            apks[revision] = dict(row, path=str(target))
        after = main_snapshot(config)
        require(after == checked["main"], "Main changed during private preparation")
        prepared = {"schema": 1, "kind": "isolated-owned-signal-canary-r1", "created_utc": now(),
                    "name": attempt["name"], "nonce": uuid.uuid4().hex,
                    "nonces": {key: uuid.uuid4().hex for key in ("r2-svc", "r2-smc-handler", "r2-smc-default", "r3-smc-mask-edit")},
                    "arm": "signal-mask-r1", **{key: str(value) for key, value in layout.items()},
                    "input_path": str(input_path), "input_sha256": input_sha,
                    "spec_sha256": sha(stage / "cell.json"), "engine_sha256": config["engine"]["sha256"],
                    "presenter": config["presenter"]["path"], "presenter_sha256": PRESENTER_SHA,
                    "framework_guard": config["framework_guard"]["path"], "framework_guard_sha256": GUARD_SHA,
                    "main_before": checked["main"], "copied_records": copied, "data_images": images,
                    "apks": apks, "fresh_empty_data_images": True, "old_userdata_read": False,
                    "services_started": False, "production_ready": False}
        write_new(evidence / "prepared.json", prepared)
        status.update(status="PREPARED_NOT_STARTED", prepared_sha256=sha(evidence / "prepared.json"))
    except BaseException as error:
        status.update(status="FAILED_PREPARATION_RETAINED_NO_RETRY", error=repr(error))
        raise
    finally:
        status["finished_utc"] = now()
        write_new(evidence / "prepare-result.json", status)
    return status


def check_prepared(config, input_sha):
    checked = validate_inputs(config, prepared=True)
    layout = checked["layout"]
    result = json.loads((layout["evidence"] / "prepare-result.json").read_text())
    require(result["status"] == "PREPARED_NOT_STARTED" and result["services_started"] is False and
            result["input_sha256"] == input_sha, "preparation did not complete")
    prepared_path = layout["evidence"] / "prepared.json"
    require(sha(prepared_path) == result["prepared_sha256"], "prepared receipt changed")
    prepared = json.loads(prepared_path.read_text())
    require(prepared["input_sha256"] == input_sha, "prepared input contract differs")
    require(all(prepared[key] == str(value) for key, value in layout.items()), "prepared owned layout differs")
    require(prepared["services_started"] is False and prepared["fresh_empty_data_images"] is True and
            prepared["old_userdata_read"] is False, "prepared isolation contract differs")
    require(prepared["main_before"] == checked["main"], "Main differs from prepared baseline")
    require(sha(layout["stage"] / "cell.json") == prepared["spec_sha256"], "prepared spec changed")
    require(prepared["engine_sha256"] == config["engine"]["sha256"], "prepared engine differs")
    for row in prepared["copied_records"]:
        path = layout["stage"] / row["relative"]
        require(path.is_file() and not path.is_symlink() and path.stat().st_size == row["bytes"] and sha(path) == row["sha256"], "prepared runtime changed")
    for row in prepared["apks"].values():
        require(sha(row["path"]) == row["sha256"], "prepared APK changed")
    for row in prepared["data_images"]:
        path = layout["data"] / row["name"]
        metadata = path.lstat()
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1 and metadata.st_uid == 0 and
                metadata.st_mode & 0o077 == 0 and metadata.st_size == row["bytes"] and
                (metadata.st_dev, metadata.st_ino) == (row["device"], row["inode"]) and
                sha(path) == row["sha256_before_first_boot"], "fresh private data image changed before first boot")
    require(not (layout["evidence"] / "run.claim.json").exists(), "run was already claimed; no automatic replay")
    return {"status": "PREPARED_CHECKED_NO_SERVICES_STARTED", "prepared_sha256": sha(layout["evidence"] / "prepared.json")}


def load_inputs(path, expected):
    path = pinned_file({"path": str(path), "sha256": expected})
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("check-inputs", "prepare", "check-prepared"))
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--inputs-sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    config = load_inputs(args.inputs, args.inputs_sha256)
    if args.phase == "prepare":
        result = prepare(config, args.inputs, args.inputs_sha256)
    elif args.phase == "check-prepared":
        result = check_prepared(config, args.inputs_sha256)
    else:
        checked = validate_inputs(config)
        result = {"status": "INPUTS_VERIFIED_NOT_STAGED_NOT_STARTED", "engine_sha256": config["engine"]["sha256"],
                  "input_sha256": args.inputs_sha256, "main_epoch_sha256": checked["main"]["framework_sha256"]}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as failure:
        print(json.dumps({"status": "FAILED_NO_RETRY", "error": repr(failure)}))
        sys.exit(1)
