#!/usr/bin/env python3
"""Keep generated integration workspaces within the fixed upstream lock set."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib

SEED_SHA256 = "6b5de5d78a8e794567e1b07f1e7c621079023ff7f03c6c618abb7d5c09d8e316"
TOOLCHAIN = "nightly-2026-07-21"
ALIASES = {"b": "build", "c": "check", "d": "doc", "r": "run", "t": "test"}
RESOLVING = {"metadata", "build", "check", "test", "run", "doc",
             "bench", "rustc", "rustdoc", "fetch", "tree", "pkgid"}
MANIFEST_ONLY = {"new", "init", "locate-project", "read-manifest", "verify-project",
                 "version", "help"}


def cargo_arguments(requested):
    """Recognize the fixed profile's commands before Cargo can expand aliases.

    Global value options cannot be mistaken for commands. This is deliberately
    a finite integration adapter, not a replacement Cargo CLI: custom commands,
    configuration overrides and directory/lock redirection fail closed.
    """
    args = list(requested)
    if args and args[0].startswith("+"):
        if args.pop(0) not in ("+" + TOOLCHAIN, "+" + TOOLCHAIN + "-x86_64-unknown-linux-gnu"):
            raise SystemExit("integration Cargo only permits the fixed " + TOOLCHAIN)
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--color":
            if index + 1 >= len(args) or args[index + 1] not in ("auto", "always", "never"):
                raise SystemExit("integration Cargo requires --color auto, always or never")
            index += 2
        elif arg.startswith("--color="):
            if arg.partition("=")[2] not in ("auto", "always", "never"):
                raise SystemExit("integration Cargo requires --color auto, always or never")
            index += 1
        elif arg in ("--quiet", "--verbose", "--locked", "--offline", "--frozen",
                     "--version", "--help", "--list") or \
                (arg.startswith("-") and len(arg) > 1 and set(arg[1:]) <= set("vqVh")):
            index += 1
        elif arg == "--explain":
            if index + 1 >= len(args):
                raise SystemExit("integration Cargo requires a rustc explanation code")
            index += 2
        elif arg == "-Z" and index + 1 < len(args):
            if args[index + 1] == "script" or args[index + 1].startswith("script="):
                raise SystemExit("integration Cargo does not permit script execution")
            index += 2
        elif arg.startswith("-Z") and len(arg) > 2 and not arg.startswith("-Zscript"):
            index += 1
        elif arg.startswith("-"):
            raise SystemExit(f"unsupported integration Cargo global option: {arg}")
        else:
            break
    command = ALIASES.get(args[index], args[index]) if index < len(args) else ""
    if command and command not in RESOLVING | MANIFEST_ONLY:
        raise SystemExit(f"unsupported integration Cargo command: {command}")
    if command:
        args[index] = command
    # Cargo accepts global options after the command too. Do not let a caller
    # redirect the lock, compiler or cwd after the workspace has been verified.
    cargo_side = args[:args.index("--")] if "--" in args else args
    for option_index, arg in enumerate(cargo_side):
        if arg in ("--config", "-C", "--lockfile-path", "-Zscript") or \
                arg.startswith(("--config=", "--lockfile-path=", "-Zscript")) or \
                (arg.startswith("-C") and len(arg) > 2) or \
                (arg == "-Z" and option_index + 1 < len(cargo_side) and
                 cargo_side[option_index + 1].partition("=")[0] == "script"):
            raise SystemExit(f"unsupported integration Cargo override: {arg}")
    if command == "help":
        topics = [arg for arg in args[index + 1:] if not arg.startswith("-")]
        if any(ALIASES.get(topic, topic) not in RESOLVING | MANIFEST_ONLY for topic in topics):
            raise SystemExit("integration Cargo help only permits known commands")
        args[index + 1:] = [ALIASES.get(arg, arg) for arg in args[index + 1:]]
    return args, command


def locked_arguments(args):
    # Flags after `--` belong to a test/program/rustc, not Cargo. Place the
    # enforced flags first, and avoid Cargo's duplicate-option rejection.
    boundary = args.index("--") if "--" in args else len(args)
    before = args[:boundary]
    forced = [flag for flag in ("--locked", "--offline") if flag not in before]
    return [*forced, *args]


def external(data):
    return {(p["name"], p["version"], p["source"], p.get("checksum", ""))
            for p in tomllib.loads(data.decode())["package"] if p.get("source")}


def atomic_write(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(data)
        name = temporary.name
    os.replace(name, path)


def main():
    real = os.environ["A01_REAL_CARGO"]
    # OSDK deliberately removes RUSTUP_TOOLCHAIN before Cargo build, and its
    # generated template says merely "nightly". Pin every real subprocess again
    # instead of allowing a Rust shim to install/select a different nightly.
    args, subcommand = cargo_arguments(sys.argv[1:])
    tool_bin = Path(real).resolve().parent
    os.environ["RUSTUP_TOOLCHAIN"] = TOOLCHAIN
    os.environ["RUSTUP_AUTO_INSTALL"] = "0"
    for name, variable in (("rustc", "RUSTC"), ("rustdoc", "RUSTDOC")):
        executable = tool_bin / name
        if not executable.is_file():
            raise SystemExit(f"fixed Cargo sibling is missing: {executable}")
        os.environ[variable] = str(executable)
    if subcommand not in RESOLVING:
        os.execv(real, [real, *args])
    record_dir = Path(os.environ["A01_OSDK_CASE_OUTPUT"]) / "cargo"
    record_dir.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix="request-", suffix=".json", dir=record_dir)
    os.close(descriptor)
    report = {"cwd": os.getcwd(), "requested_argv": [real, *sys.argv[1:]],
              "canonical_argv": [real, *args], "command": subcommand,
              "external_drift": None, "normalization_exit": None, "raw_exit_code": None,
              "cargo_path": real, "cargo_sha256": hashlib.sha256(Path(real).read_bytes()).hexdigest(),
              "cargo_version": subprocess.check_output([real, "-Vv"], text=True, timeout=10),
              "rustc_path": os.environ.get("RUSTC"),
              "rustc_version": subprocess.check_output([os.environ.get("RUSTC", "rustc"), "-Vv"], text=True, timeout=10)}
    if os.environ.get("RUSTC"):
        report["rustc_sha256"] = hashlib.sha256(Path(os.environ["RUSTC"]).read_bytes()).hexdigest()
    report_path = Path(name)
    def save():
        report_path.write_text(json.dumps(report, indent=2) + "\n")
    save()
    locate = [real, "locate-project", "--workspace", "--message-format", "plain"]
    cargo_side = args[:args.index("--")] if "--" in args else args
    for index, arg in enumerate(cargo_side):
        if arg == "--manifest-path":
            locate += cargo_side[index:index + 2]
        elif arg.startswith("--manifest-path="):
            locate.append(arg)
    root = subprocess.check_output(locate, text=True).strip()
    root = Path(root).resolve().parent
    allowed = [Path(value).resolve() for value in json.loads(os.environ["A01_OSDK_ALLOWED_ROOTS"])]
    if not any(root == path or root.is_relative_to(path) for path in allowed):
        raise SystemExit(f"refusing to alter a Cargo lock outside generated integration roots: {root}")
    seed_path = Path(os.environ["OSDK_CARGO_LOCK"])
    seed = seed_path.read_bytes()
    if hashlib.sha256(seed).hexdigest() != SEED_SHA256:
        raise SystemExit("fixed upstream seed lock hash mismatch")
    lock = root / "Cargo.lock"
    before = lock.read_bytes() if lock.exists() else seed
    if external(before) - external(seed):
        raise SystemExit("existing generated lock contains dependencies outside pinned upstream")
    # `osdk new` asks for --no-deps metadata before adding the local OSTD
    # dependency. This query identifies local manifests and never resolves or
    # builds their dependencies. A full resolution at this stage would resolve
    # the template's not-yet-replaced crates.io OSTD dependency.
    if subcommand == "metadata" and "--no-deps" in cargo_side:
        atomic_write(lock, seed)
        actual = [real, *locked_arguments(args)]
        report.update({"actual_argv": actual, "metadata_no_deps_only": True,
                       "external_drift": [], "seed_sha256": SEED_SHA256})
        save()
        result = subprocess.run(actual)
        report["raw_exit_code"] = result.returncode
        report["lock_after_sha256"] = hashlib.sha256(lock.read_bytes()).hexdigest()
        save()
        return result.returncode
    # Earlier metadata can precede manifest edits; always start real dependency
    # normalization from the complete fixed seed, not a previously pruned lock.
    atomic_write(lock, seed)
    # Cargo prunes the original seed and adds only locally generated packages.
    # An offline normalization can never fetch or select an unseen registry entry.
    normalize = [real, "metadata", "--offline", "--format-version", "1",
                 "--filter-platform", "x86_64-unknown-none"]
    report["normalization_argv"] = normalize
    report["workspace_root"] = str(root)
    report["seed_sha256"] = SEED_SHA256
    with report_path.with_suffix(".metadata.json").open("wb") as stdout, \
            report_path.with_suffix(".stderr.log").open("wb") as stderr:
        normalized = subprocess.run(normalize, cwd=root, stdout=stdout, stderr=stderr)
    report["normalization_exit"] = normalized.returncode
    if normalized.returncode:
        save()
        sys.stderr.write(report_path.with_suffix(".stderr.log").read_text())
        return normalized.returncode
    after = lock.read_bytes()
    drift = sorted(external(after) - external(seed))
    report["external_drift"] = drift
    report["normalized_sha256"] = hashlib.sha256(after).hexdigest()
    report_path.with_suffix(".Cargo.lock").write_bytes(after)
    if drift:
        save()
        raise SystemExit(f"generated lock drifted from pinned upstream identities: {drift}")
    actual = [real, *locked_arguments(args)]
    report["actual_argv"] = actual
    save()
    result = subprocess.run(actual)
    report["raw_exit_code"] = result.returncode
    report["lock_after_sha256"] = hashlib.sha256(lock.read_bytes()).hexdigest()
    if lock.read_bytes() != after:
        report["locked_command_changed_lock"] = True
        save()
        return 1
    save()
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
