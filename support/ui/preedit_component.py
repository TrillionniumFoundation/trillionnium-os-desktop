#!/usr/bin/env python3
"""Run the pinned prepared-SDK regressions in disposable, isolated sources.

This is a compile/unit regression component. It does not launch a desktop,
exercise an IME daemon or grant any production authority.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import tomllib

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
REGRESSIONS = (("sdk-window-tests", "window::focus_tests", 4),
               ("sdk-text-input-tests", "text_input::", 35))
SUMMARY = re.compile(r"^test result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) ignored;", re.MULTILINE)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def sdk_test_commands(profile, common):
    require(profile.get("sdk_profile") == "preedit-callbacks", "SDK regressions require the explicit preedit profile")
    return [(name, ["cargo", "test", "--manifest-path", "ui/Cargo.toml", *common,
        "-p", "trill-shell", "-p", "makepad-widgets", "--features", profile["cargo_feature"],
        "--lib", test_filter, "--", "--test-threads=1"], test_filter, expected)
        for name, test_filter, expected in REGRESSIONS]


def require_test_results(text, expected, test_filter):
    """Cargo exit zero alone permits zero tests; require actual pinned passes."""
    summaries = SUMMARY.findall(text)
    require(bool(summaries), "SDK regression log has no libtest result")
    require(all(state == "ok" and failed == "0" and ignored == "0"
                for state, _passed, failed, ignored in summaries), "SDK regression failed or ignored tests")
    passed = sum(int(item[1]) for item in summaries)
    require(passed == expected and expected > 0,
            f"SDK regression must execute exactly {expected} tests, observed {passed}")
    named = re.findall(r"^test (\S+) \.\.\. ok$", text, re.MULTILINE)
    require(len(named) == expected and len(set(named)) == expected
            and all(name.startswith(test_filter.rstrip(":") + "::") for name in named),
            "SDK regression must execute the named widgets scope: " + test_filter)
    return {"passed": passed, "failed": 0, "ignored": 0, "libtest_summaries": len(summaries)}


@contextmanager
def restored_lock(repo):
    """Only the disposable UI lock may change, and restoration also runs on failure."""
    path = Path(repo) / "ui/Cargo.lock"
    require(path.is_file() and not path.is_symlink(), "Expected a regular committed UI lock")
    before, mode = path.read_bytes(), path.stat().st_mode & 0o777
    try:
        yield before
    finally:
        # Replace an unexpected link rather than following it while restoring.
        temporary = path.with_name(".Cargo.lock.preedit-restore")
        with temporary.open("xb") as stream:
            stream.write(before)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
        require(path.read_bytes() == before, "Failed to restore the original UI lock bytes")


def run_component(args):
    import build_text_product as product
    import preedit_source
    import verify_product_dependencies as dependencies

    require(product.platform.system() == "Linux" and product.platform.machine() == "x86_64",
            "The prepared SDK CI component requires x86_64 Linux")
    profile = preedit_source.settings()
    baseline = json.loads((HERE / "linux-text-profile.json").read_bytes())
    source = json.loads((HERE / "HEPTA_SHARED_PRESENTER.json").read_bytes())
    require((source["commit"], source["tree"]) == (profile["hepta_commit"], profile["hepta_tree"]),
            "Prepared regression helper and runtime must be the same Hepta source")
    original = product.source_profile.Repository(REPO, "desktop")
    commit = original.git("rev-parse", "HEAD").decode().strip()
    tree = original.git("rev-parse", "HEAD^{tree}").decode().strip()
    original.check(commit, tree)
    discovery = Path(args.metadata).resolve(strict=True)
    recorded = json.loads(Path(args.source_receipt).read_bytes())
    metadata = json.loads(discovery.read_bytes())
    caches = product.verify_source_caches(metadata, source["commit"], source["tree"], baseline)
    require(recorded["source_caches"] == caches
            and recorded["resolved_packages"] == product.validate_graph(metadata, source["commit"], baseline)
            and recorded["profile"] == baseline
            and recorded["profile_sha256"] == product.digest(HERE / "linux-text-profile.json"),
            "Default metadata/source receipt differs from actual verified sources")
    require(recorded["product_dependencies"] == dependencies.verify(REPO, Path(caches["hepta"]["root"])),
            "Original source-byte contract differs from the discovery receipt")
    work, output = Path(args.work_dir).absolute(), Path(args.output).absolute()
    roots = [REPO, *(Path(entry["root"]) for entry in caches.values())]
    require(work == work.resolve() and output == output.resolve(), "Use canonical absolute component paths")
    require(not any(path.is_relative_to(root) for path in (work, output) for root in roots),
            "Component outputs must be outside original source checkouts")
    require(not work.is_relative_to(output) and not output.is_relative_to(work),
            "Evidence and disposable source directories must be separate")
    work.mkdir(mode=0o700, parents=False, exist_ok=False)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    logs = output / "logs"
    logs.mkdir(mode=0o700)
    scratch = work / "desktop"
    helper = work / "hepta"
    sdk = work / "sdk"
    config = work / "sdk-overrides.toml"
    original_metadata = work / "original-metadata.json"
    tools = {name: str(Path(subprocess.check_output(
        ["rustup", "which", "--toolchain", profile["toolchain"], name], text=True).strip()).resolve(strict=True))
        for name in ("cargo", "rustc", "rustdoc")}
    target = Path(os.environ.get("CARGO_TARGET_DIR", work / "target")).absolute()
    require(target == target.resolve() and not any(target.is_relative_to(root) for root in roots),
            "Cargo target must be a canonical directory outside original source checkouts")
    env, removed = product.controlled_environment(profile, target, args.jobs, tools)
    for key in list(env):
        if key.startswith(("TRILL_", "HEPTA_", "GIT_", "CARGO_REGISTRIES_", "CARGO_ALIAS_")) or key in {
                "DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "IBUS_ADDRESS", "LD_PRELOAD"}:
            removed.append(key)
            del env[key]
    env.update(CARGO_INCREMENTAL="0", CARGO_PROFILE_TEST_DEBUG="0", CARGO_TERM_COLOR="never",
               PYTHONDONTWRITEBYTECODE="1", GIT_NO_REPLACE_OBJECTS="1", GIT_OPTIONAL_LOCKS="0",
               GIT_TERMINAL_PROMPT="0")
    receipt = {"schema": "trill.preedit-sdk-ci-component.v1", "status": "running", "exit_code": None,
        "desktop_commit": commit, "desktop_tree": tree, "hepta": source,
        "discovery_inputs": {str(path): sha(path) for path in (discovery, Path(args.source_receipt))},
        "profile_sha256": sha(HERE / "linux-preedit-profile.json"), "commands": [],
        "ambient_overrides_removed": sorted(set(removed)), "tests": {}, "default_source_caches": caches,
        "cargo_target": str(target), "cargo_target_reused": "CARGO_TARGET_DIR" in os.environ,
        "toolchain_executables": {name: {"path": path, "sha256": sha(path)} for name, path in tools.items()},
        "default_product_binaries_qualified": False,
        "runtime_executed": False, "window_qualified": False, "production_authority_qualified": False,
        "scope": "isolated prepared-SDK compile and actual widget-event unit regressions only"}

    def save():
        product.desktop.atomic_write(output / "component-receipt.json", product.source_profile.canonical(receipt))

    def run(name, command, cwd=scratch, machine=False):
        if command[0] in tools:
            command = [tools[command[0]], *command[1:]]
        stdout = work / (name + ".json") if machine else logs / (name + ".log")
        stderr = logs / (name + ".stderr.log")
        entry = {"name": name, "command": command, "cwd": str(cwd)}
        receipt["commands"].append(entry)
        save()
        started = time.monotonic()
        with stdout.open("xb") as out, stderr.open("xb") as err:
            process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                stdout=out, stderr=err, start_new_session=True)
            try:
                code = process.wait()
            except BaseException:
                if process.returncode is None:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        process.wait(timeout=5)
                raise
        entry.update(exit_code=code, seconds=round(time.monotonic() - started, 3),
                     stdout={"path": str(stdout), "sha256": sha(stdout)},
                     stderr={"path": str(stderr), "sha256": sha(stderr)})
        save()
        require(code == 0, f"{name} failed with exit {code}")
        return stdout

    handlers = {}

    def interrupted(number, _frame):
        raise InterruptedError("Component interrupted by signal " + str(number))

    try:
        for number in (signal.SIGTERM, signal.SIGINT):
            handlers[number] = signal.signal(number, interrupted)
        save()
        for name, origin, destination, revision in (
                ("clone-desktop", REPO, scratch, commit),
                ("clone-hepta", Path(caches["hepta"]["root"]), helper, source["commit"])):
            run(name, ["git", "-c", "core.hooksPath=/dev/null", "clone", "--shared", "--no-checkout",
                str(origin), str(destination)], cwd=work)
            run(name + "-checkout", ["git", "-c", "core.hooksPath=/dev/null", "checkout", "--detach", revision], cwd=destination)
        scratch_repo = product.source_profile.Repository(scratch, "scratch desktop")
        scratch_repo.check(commit, tree)
        preedit_source.verified_helper(helper)
        dependencies.verify(scratch, helper)
        with restored_lock(scratch) as lock_before:
            receipt["original_ui_lock_sha256"] = hashlib.sha256(lock_before).hexdigest()
            # This complete graph deliberately contains the original Git SDK.
            path = run("original-metadata", ["cargo", "metadata", "--manifest-path", "ui/Cargo.toml",
                "--locked", "--format-version", "1", "--features", profile["cargo_feature"]], machine=True)
            original_metadata.write_bytes(path.read_bytes())
            helper_script = helper / "apps/hepta-control-ui/test/prepare-native-clipboard-sdk.py"
            run("prepare-sdk", [sys.executable, "-I", "-B", str(helper_script), "--profile", "preedit-callbacks",
                "--upstream-repo", caches["makepad"]["root"], "--destination", str(sdk),
                "--hepta-root", str(helper), "--metadata", str(original_metadata),
                "--cargo-config-output", str(config)])
            overrides = tomllib.loads(config.read_text())["patch"][profile["makepad_repository"]]
            require(len(overrides) == 102, "Canonical metadata must prepare all 102 SDK crate overrides")
            # Cargo alone generates the path lock, in the disposable checkout.
            prepared = run("prepared-metadata", ["cargo", "--config", str(config), "metadata", "--manifest-path",
                "ui/Cargo.toml", "--offline", "--format-version", "1", "--features", profile["cargo_feature"]], machine=True)
            changed = scratch_repo.git("diff", "--name-only", "HEAD").decode().splitlines()
            require(changed == ["ui/Cargo.lock"], "Preparation changed source outside the isolated UI lock")
            receipt["temporary_ui_lock_sha256"] = sha(scratch / "ui/Cargo.lock")
            sdk_profile = preedit_source.verify(prepared.read_bytes(), sdk, None, original_metadata, config, helper)
            graph = json.loads(prepared.read_bytes())
            receipt["resolved_packages"] = product.validate_graph(graph, source["commit"], profile, sdk_profile)
            prepared_caches = product.verify_source_caches(graph, source["commit"], source["tree"], profile, sdk_profile)
            receipt["sdk_source_profile"] = sdk_profile
            receipt["sdk_cargo_override_count"] = len(overrides)
            for name, command, test_filter, expected in sdk_test_commands(profile, ["--locked", "--offline"]):
                command = [command[0], "--config", str(config), *command[1:]]
                path = run(name, command)
                receipt["tests"][name] = require_test_results(path.read_text(), expected, test_filter)
                save()
            after = run("prepared-metadata-after", ["cargo", "--config", str(config), "metadata", "--manifest-path",
                "ui/Cargo.toml", "--locked", "--offline", "--format-version", "1", "--features", profile["cargo_feature"]], machine=True)
            require(preedit_source.verify(after.read_bytes(), sdk, None, original_metadata, config, helper) == sdk_profile,
                    "Prepared SDK/helper/config/full graph changed during regression tests")
            after_graph = json.loads(after.read_bytes())
            require(product.validate_graph(after_graph, source["commit"], profile, sdk_profile) == receipt["resolved_packages"]
                    and product.verify_source_caches(after_graph, source["commit"], source["tree"], profile, sdk_profile) == prepared_caches,
                    "Resolved prepared source caches changed during tests")
        receipt["restored_ui_lock_sha256"] = sha(scratch / "ui/Cargo.lock")
        scratch_repo.check(commit, tree)
        original.check(commit, tree)
        require(product.verify_source_caches(metadata, source["commit"], source["tree"], baseline) == caches,
                "Original dependency source caches changed during component tests")
        receipt.update(status="passed", exit_code=0, scratch_source_restored=True)
        save()
        return 0
    except BaseException as error:
        receipt.update(status="failed", exit_code=1, error=str(error))
        if (scratch / "ui/Cargo.lock").is_file():
            receipt["restored_ui_lock_sha256"] = sha(scratch / "ui/Cargo.lock")
        save()
        raise
    finally:
        for number, handler in handlers.items():
            signal.signal(number, handler)
        post_errors = []
        for name, check in (
                ("original_checkout", lambda: original.check(commit, tree)),
                ("original_source_caches", lambda: require(
                    product.verify_source_caches(metadata, source["commit"], source["tree"], baseline) == caches,
                    "Original dependency source caches changed")),
                ("toolchain_executables", lambda: require(all(sha(entry["path"]) == entry["sha256"]
                    for entry in receipt["toolchain_executables"].values()), "Toolchain executable changed")),
                ("scratch_checkout", lambda: product.source_profile.Repository(scratch, "scratch desktop").check(commit, tree))):
            try:
                check()
            except (OSError, ValueError, subprocess.SubprocessError, product.source_profile.ProfileError) as error:
                post_errors.append(name + ": " + str(error))
        receipt["postchecks"] = {"passed": not post_errors, "errors": post_errors}
        if post_errors:
            receipt.update(status="failed", exit_code=1)
        save()
        if post_errors and sys.exc_info()[0] is None:
            raise ValueError("Component source/lock postcheck failed: " + "; ".join(post_errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("metadata", "source-receipt", "work-dir", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=1)
    try:
        # Ignored bytecode is not part of source identity; import checked local
        # tools with a fresh, non-writing cache prefix instead.
        with tempfile.TemporaryDirectory(prefix="trill-preedit-component-tools-") as cache:
            sys.pycache_prefix, sys.dont_write_bytecode = cache, True
            return run_component(parser.parse_args())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print("Prepared SDK component: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
