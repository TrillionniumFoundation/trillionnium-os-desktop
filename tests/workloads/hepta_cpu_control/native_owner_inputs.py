"""Bind actual original owner/kernel inputs before any native G2 execution."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import tomllib

from native_owner_evidence import digest as check_digest
from native_owner_evidence import json_value
from native_owner_evidence import obj
from native_owner_evidence import require

sys.dont_write_bytecode = True
MAX_OWNER_BYTES = 8 * 1024**2
MAX_KERNEL_BYTES = 64 * 1024**2
PROFILE = "g2-trusted-daemon"


def sha(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def read(path, limit, expected=None):
    require(path.is_absolute() and path.is_file() and not path.is_symlink()
            and path.resolve(strict=True) == path and 0 < path.stat().st_size <= limit,
            "canonical bounded regular input required: " + str(path))
    content = path.read_bytes()
    require(0 < len(content) <= limit, "input changed its bounded size: " + str(path))
    if expected is not None:
        require(hashlib.sha256(content).hexdigest() == check_digest(expected, "explicit input digest"),
                "input differs from its explicit frozen digest: " + str(path))
    return content


def document(path, limit, expected=None):
    value = json_value(read(path, limit, expected))
    require(type(value) is dict, "object document required: " + str(path))
    return value


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_identity(value):
    obj(value, ("head", "tree"), "exact source identity")
    require(all(type(value[key]) is str and re.fullmatch(r"[0-9a-f]{40}", value[key]) for key in value),
            "full source commit and tree required")
    return value


def review_inputs(path, expected):
    value = document(path, 1024**2, expected)
    obj(value, ("schema", "desktop", "hepta", "entry", "userspace_toolchain", "scope"), "original native owner source review")
    require(value["schema"] == "hepta.native-original-owner-source-review.v1", "original owner review schema differs")
    for key in ("desktop", "hepta"):
        source_identity(value[key])
    entry = obj(value["entry"], ("package", "name", "kind", "path", "sha256"), "reviewed original entry")
    require(entry["package"] == "codex-hepta-agentd" and entry["kind"] in ("bin", "example")
            and type(entry["name"]) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", entry["name"])
            and type(entry["path"]) is str and entry["path"].startswith("codex-rs/hepta-agentd/")
            and ".." not in Path(entry["path"]).parts, "review must select a tracked original Agentd executable")
    check_digest(entry["sha256"], "reviewed original entry")
    toolchain = obj(value["userspace_toolchain"], ("channel", "manifest", "sha256"), "reviewed userspace toolchain")
    require(type(toolchain["channel"]) is str and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", toolchain["channel"])
            and toolchain["manifest"] == "codex-rs/rust-toolchain.toml", "fixed original toolchain manifest required")
    check_digest(toolchain["sha256"], "reviewed toolchain manifest")
    require(type(value["scope"]) is str and 0 < len(value["scope"]) <= 8192, "review scope must be explicit")
    return value


def original_helpers(desktop):
    control = desktop / "tests/kernel/control"
    sys.path.insert(0, str(control))
    shape = load_module("g2_original_shape", control / "run_g1c_guest.py")
    ordinary = load_module("g2_original_snapshot", control / "run_queryabi_candidate_guest.py")
    replay = load_module("g2_original_archive", control / "run_queryabi_guest.py")
    return shape, ordinary, replay


def source_snapshots(roots, review, builder):
    snapshots = {name: builder.source_snapshot(root, review[name]["head"], review[name]["tree"])
                 for name, root in roots.items()}
    entry_path = roots["hepta"] / review["entry"]["path"]
    read(entry_path, 16 * 1024**2, review["entry"]["sha256"])
    file_map = {item["path"]: item for item in snapshots["hepta"]["files"]}
    require(file_map[review["entry"]["path"]]["sha256"] == review["entry"]["sha256"], "reviewed entry is not an original tracked source")
    toolchain = review["userspace_toolchain"]
    manifest = read(roots["hepta"] / toolchain["manifest"], 16 * 1024, toolchain["sha256"])
    require(tomllib.loads(manifest.decode())["toolchain"]["channel"] == toolchain["channel"], "original Rust toolchain drifted")
    return snapshots


def owner_build(receipt_path, expected, owner, review, snapshots, shape, hepta_source):
    value = document(receipt_path, 8 * 1024**2, expected)
    require(value.get("schema") == "hepta.original-native-entry-build.v1" and "error" not in value,
            "successful original tracked-entry build receipt required")
    for key in ("built", "packaged", "static_profile_passed", "source_inputs_unchanged"):
        require(value.get(key) is True, "original entry build did not complete: " + key)
    for key in ("features_disabled", "profile_overridden", "limits_changed", "fixture_created", "executed_binary",
                "native_role_verified", "persistent_cpu_verified", "recovery_verified", "g2_complete"):
        require(value.get(key) is False, "entry build cannot substitute profiles or execution claims: " + key)
    require(value.get("sources") == {name: review[name] for name in ("desktop", "hepta")}, "owner was built from another exact source pair")
    recorded = value.get("original_entry", {})
    for key in ("package", "name", "kind", "path"):
        require(recorded.get(key) == review["entry"][key], "owner build selected another original entry")
    require(recorded.get("entry_sha256") == review["entry"]["sha256"], "compiled original entry bytes differ from review")
    before = document(receipt_path.parent / "source-before.json", 64 * 1024**2)
    after = document(receipt_path.parent / "source-after.json", 64 * 1024**2)
    require(before == after == snapshots, "owner full tracked sources changed across its actual build")
    channel = review["userspace_toolchain"]["channel"]
    upstream = tomllib.loads(read(hepta_source / "codex-rs/Cargo.toml", 4 * 1024**2).decode())
    require(value.get("release_profile") == upstream["profile"]["release"]
            and value.get("original_lock_sha256") == sha(hepta_source / "codex-rs/Cargo.lock"),
            "original owner release profile or locked dependency graph differs")
    environment = value.get("environment", {})
    require(type(environment) is dict and environment.get("RUSTUP_TOOLCHAIN") == channel
            and environment.get("OPENSSL_STATIC") == "1" and environment.get("CARGO_NET_OFFLINE") == "true"
            and environment.get("CARGO_INCREMENTAL") == "0"
            and environment.get("CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_RUSTFLAGS")
                == "-C target-feature=+crt-static -C relocation-model=static -C link-arg=-no-pie"
            and not any(key in environment for key in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER")),
            "actual owner build changed the reviewed static compiler environment")
    for name in ("cargo", "rustc"):
        tool = value.get("toolchains", {}).get(name, {})
        require(type(tool.get("version")) is str and tool["version"].startswith(name + " " + channel + " "),
                "owner was built by a different actual fixed toolchain")
        check_digest(tool.get("sha256"), "actual owner build tool")
    commands = value.get("commands")
    require(type(commands) is list and len(commands) == 4, "original metadata/build/packaging/readelf commands required")
    require(all(type(command) is dict and command.get("completed") is True
                and type(command.get("exit_code")) is int and command["exit_code"] == 0
                and command.get("timed_out", False) is False for command in commands), "original owner command failed or timed out")
    require([command.get("log") for command in commands] == ["metadata.log", "build.log", "original-packaging.log", "original-readelf.log"],
            "original owner build command order differs")
    command = commands[1]["argv"]
    expected_tail = ["build", "--manifest-path", "codex-rs/Cargo.toml", "--locked", "--offline", "--release", "--target",
                     "x86_64-unknown-linux-gnu", "-p", "codex-hepta-agentd", "--" + recorded["kind"], recorded["name"]]
    require(type(command) is list and len(command) == len(expected_tail) + 2 and command[1:-1] == expected_tail
            and re.fullmatch(r"-j[1-8]", command[-1]), "owner build altered the original capabilities or release packaging")
    product = obj(value.get("product"), ("path", "bytes", "sha256"), "packaged original binary")
    check_digest(product["sha256"], "packaged original owner")
    require(product["path"] == "packaged/" + recorded["name"] and type(product["bytes"]) is int
            and 0 < product["bytes"] <= MAX_OWNER_BYTES, "original static owner exceeds the unchanged file bound")
    packaged = receipt_path.parent / product["path"]
    content = read(packaged, MAX_OWNER_BYTES, product["sha256"])
    require(read(owner, MAX_OWNER_BYTES, product["sha256"]) == content and len(content) == product["bytes"],
            "explicit owner ELF differs from the actual packaged original")
    info = shape.inspect_probe_elf(content)
    require(value.get("original_shape") == info, "original static ELF shape differs from its actual build receipt")
    retained = {receipt_path.name: receipt_path}
    for command in commands:
        path = receipt_path.parent / command["log"]
        read(path, 64 * 1024**2)
        retained[command["log"]] = path
    for name in ("source-before.json", "source-after.json"):
        retained[name] = receipt_path.parent / name
    return value, content, info, retained


def kernel_build(directory, expected, review, owner_bytes, ordinary):
    pipeline_path = directory / "pipeline.json"
    value = document(pipeline_path, 8 * 1024**2, expected)
    require(value.get("passed") is True and value.get("source_inputs_unchanged") is True
            and value.get("kernel_profile") == PROFILE
            and value.get("source_head") == review["desktop"]["head"]
            and value.get("source_tree") == review["desktop"]["tree"], "actual source-bound G2 product kernel pipeline required")
    desktop = Path(value.get("source_root", ""))
    require(desktop.is_absolute() and desktop.is_dir() and desktop.resolve(strict=True) == desktop,
            "actual kernel compiled-source root required")
    require(value.get("owner_sha256") == hashlib.sha256(owner_bytes).hexdigest(), "kernel embeds a different owner image")
    current = ordinary.source_snapshot(desktop, review["desktop"]["head"], review["desktop"]["tree"])
    before = document(directory / "source-before.json", 64 * 1024**2)
    after = document(directory / "source-after.json", 64 * 1024**2)
    require(before == after == current, "full original kernel source changed across its actual build")
    steps = value.get("steps")
    require(type(steps) is list and len(steps) == 2 and all(type(step) is dict for step in steps)
            and [step.get("label") for step in steps] == ["osdk-build", "g2-kernel"],
            "exact source OSDK and product G2 kernel build steps required")
    require(all(type(step.get("exit_code")) is int and step["exit_code"] == 0
                and step.get("timed_out", False) is False for step in steps), "actual G2 build command failed")
    osdk_source = desktop / "kernel/asterinas/osdk"
    require(value.get("osdk_source_root") == str(osdk_source), "OSDK was built with another embedded OSTD/source path")
    command = steps[0].get("argv", [])
    require(type(command) is list and len(command) >= 8 and command[1:3] == ["+nightly-2026-07-21", "install"]
            and command.count("--locked") == command.count("cargo-osdk") == command.count("--path") == 1
            and command[command.index("--path") + 1] == str(osdk_source), "OSDK did not execute the original locked local-source build")
    args = command[3:]
    while args:
        part, *args = args
        if part in ("--locked", "--offline", "--force", "cargo-osdk"):
            continue
        require(part in ("--path", "--target-dir") and args and Path(args[0]).is_absolute(), "unknown OSDK build option")
        args = args[1:]
    require(steps[0].get("cwd") in (str(desktop), str(desktop / "kernel/asterinas")), "OSDK command working directory differs")
    kernel_command = steps[1].get("argv")
    require(kernel_command in ([str(desktop / "support/build/kernel.sh"), "kernel"],
                               ["/bin/bash", str(desktop / "support/build/kernel.sh"), "kernel"])
            and steps[1].get("cwd") == str(desktop), "product kernel command differs from the original build script")
    osdk = directory / "source-built-cargo-osdk"
    check_digest(value.get("osdk_sha256"), "actual source-built OSDK")
    read(osdk, 512 * 1024**2, value.get("osdk_sha256"))
    build = directory / "kernel-build"
    for name in ("make-exit-code.txt", "log-exit-code.txt", "run-exit-code.txt"):
        require(read(build / name, 64).decode().strip() == "0", "original kernel build stage failed: " + name)
    require(read(build / "environment.log", 4 * 1024**2).decode().splitlines().count(review["desktop"]["head"]) == 1,
            "kernel environment did not record its actual source head")
    make = shlex.split(read(build / "command.sh", 64 * 1024).decode())
    prefix = ["make", "-C", str(desktop / "kernel/asterinas"), "-f", "Makefile", "-f",
              str(desktop / "support/build/minimal.mk"), "kernel"]
    required = {"TARGET_ARCH=x86_64", "SMP=1", "MEM=512M", "ENABLE_KVM=0", "BOOT_PROTOCOL=multiboot", "INITRAMFS=on", "AUTO_TEST=none",
                "HEPTA_G2_TRUSTED_DAEMON=1", "FEATURES=g2-trusted-daemon", f"A01_INITRAMFS={build / 'initramfs.cpio.gz'}",
                f"A01_QEMU_WRAPPER={desktop / 'support/build/record-qemu.py'}"}
    require(make[:8] == prefix and len(make) == 20 and make[8].startswith("CARGO_OSDK=") and set(make[9:]) == required,
            "actual product kernel profile differs from the fixed G2 N0 command")
    require("--features=g2-trusted-daemon" in read(build / "kernel.log", 64 * 1024**2).decode(),
            "actual OSDK invocation lacks the explicit G2 feature")
    verified = subprocess.run([sys.executable, "-I", "-B", str(desktop / "support/build/verify-source.py")], cwd=desktop,
                              env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
                              capture_output=True, timeout=60, check=False)
    require(verified.returncode == 0 and json_value(verified.stdout) == document(build / "source-inputs.json", 8 * 1024**2),
            "original kernel functional source gate differs from the actual build")
    locked = read(build / "generated.Cargo.lock", 4 * 1024**2)
    require(locked == read(desktop / "support/build/minimal/Cargo.lock", 4 * 1024**2)
            and len(tomllib.loads(locked.decode())["package"]) == 204,
            "G2 kernel must retain the original fixed 204-package product lock")
    manifest = document(build / "trusted-initial-manifest.json", 64 * 1024)
    expected_manifest = {"schema": "hepta-g2-trusted-initial-v1", "profile": PROFILE,
                         "embedded_input": str(build / "trusted-initial.elf"), "bytes": len(owner_bytes),
                         "sha256": hashlib.sha256(owner_bytes).hexdigest(), "supported_ops": 62, "features": 0,
                         "bootstrap_version": 3, "bootstrap_bytes": 200, "roles": ["root", "manager", "workload", "recovery"],
                         "cap_ns": 50_000_000, "period_ns": 100_000_000, "lease_ns": 300_000_000_000,
                         "recovery_grace_ns": 30_000_000_000, "workload_address_space_bytes": 256 * 1024**2,
                         "root_role": 4, "root_pid_offset": 192, "workload_uid": 60002, "workload_gid": 60002,
                         "manager_history_ack": True, "original_writer_durability_verified": False, "g2_complete": False}
    require(set(manifest) == set(expected_manifest) | {"source"}
            and all(type(manifest[key]) is type(item) and manifest[key] == item for key, item in expected_manifest.items()),
            "actual trusted initial manifest differs from the complete original G2 profile")
    require(Path(manifest["source"]).is_absolute(), "original embedded source provenance missing")
    require(read(build / "trusted-initial.elf", MAX_OWNER_BYTES, expected_manifest["sha256"]) == owner_bytes
            and stat.S_IMODE((build / "trusted-initial.elf").stat().st_mode) == 0o444,
            "original immutable embedded owner snapshot differs")
    check_digest(value.get("kernel_sha256"), "actual retained G2 kernel")
    kernel = read(directory / "product-kernel.elf", MAX_KERNEL_BYTES, value["kernel_sha256"])
    require(type(value.get("kernel_bytes")) is int and value["kernel_bytes"] == len(kernel)
            and kernel[:6] == b"\x7fELF\x02\x01" and kernel[18:20] == b"\x03\x00",
            "actual G2 kernel is not the retained original OSDK multiboot EM_386 conversion")
    image_manifest = document(build / "initramfs-manifest.json", 4 * 1024**2)
    base = read(build / "initramfs.cpio.gz", 8 * 1024**2, image_manifest["image_sha256"])
    retained = {"pipeline.json": pipeline_path, "source-before.json": directory / "source-before.json",
                "source-after.json": directory / "source-after.json", "source-built-cargo-osdk": osdk,
                "osdk-build.log": directory / "osdk-build.log", "g2-kernel.log": directory / "g2-kernel.log"}
    for name in ("command.sh", "environment.log", "source-inputs.json", "make-exit-code.txt", "log-exit-code.txt", "run-exit-code.txt",
                 "kernel.log", "generated.Cargo.lock", "trusted-initial-manifest.json", "trusted-initial.elf", "initramfs-manifest.json"):
        retained["kernel-build/" + name] = build / name
    for path in retained.values():
        read(path, 512 * 1024**2 if path == osdk else 64 * 1024**2)
    return value, kernel, base, retained
