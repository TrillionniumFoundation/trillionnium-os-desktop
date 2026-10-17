#!/usr/bin/env python3
"""Inventory an existing APK and optionally run a reviewable ADB scenario.

Inventory works without Android tools and never invents package metadata.  The
ADB scenario is opt-in (`--execute`) and its results are recorded as guest
evidence; an inventory or a Linux host probe is not an Android compatibility
pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCENARIOS = [
    "install",
    "launch",
    "main_surface",
    "input",
    "background",
    "foreground",
    "save_data",
    "exit",
    "restart",
]
PROFILE_PATH = Path(__file__).resolve().parents[3] / "compat" / "android" / "aosp-profile.json"

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run_tool(command: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        return 127, str(exc)
    return result.returncode, (result.stdout + result.stderr).strip()


def parse_badging(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {"permissions": [], "native_code": []}
    package = re.search(r"package: name='([^']+)' versionCode='([^']*)' versionName='([^']*)'", text)
    if package:
        result["package"] = package.group(1)
        result["version_code"] = package.group(2)
        result["version_name"] = package.group(3)
    activity = re.search(r"launchable-activity: name='([^']+)'", text)
    if activity:
        result["launchable_activity"] = activity.group(1)
    result["permissions"] = sorted(set(re.findall(r"uses-permission: name='([^']+)'", text)))
    native = re.search(r"native-code:(.*)", text)
    if native:
        result["native_code"] = re.findall(r"'([^']+)'", native.group(1))
    return result


def inventory(apk: Path, aapt2: str | None = None) -> dict[str, Any]:
    if not apk.is_file():
        raise FileNotFoundError(apk)
    with zipfile.ZipFile(apk) as archive:
        names = archive.namelist()
        native_libraries = sorted(
            name for name in names if name.startswith("lib/") and name.endswith(".so")
        )
        dex_files = sorted(
            name for name in names if name == "classes.dex" or re.fullmatch(r"classes\d+\.dex", name)
        )
    package: dict[str, Any] = {}
    tool = aapt2 or shutil.which("aapt2")
    if tool:
        code, output = run_tool([tool, "dump", "badging", str(apk)])
        if code == 0:
            package = parse_badging(output)
        else:
            package = {"metadata_status": "blocked_tool_error", "tool_output": output}
    else:
        package = {
            "metadata_status": "blocked_missing_aapt2",
            "package": None,
            "version_code": None,
            "version_name": None,
            "permissions": [],
            "native_code": [],
        }
    package["native_libraries"] = native_libraries
    package["dex_files"] = dex_files
    if native_libraries:
        package["abi_classes"] = sorted({name.split("/")[1] for name in native_libraries})
    else:
        package["abi_classes"] = []
    return package


def adb_call(adb: str, serial: str | None, args: list[str]) -> dict[str, Any]:
    command = [adb]
    if serial:
        command += ["-s", serial]
    command += args
    code, output = run_tool(command)
    return {"command": command, "returncode": code, "output": output[-4000:]}


def reference_target_check(adb: str, serial: str | None) -> dict[str, Any]:
    """Verify the pinned disposable reference target before APK writes."""
    if not serial:
        return {"status": "blocked_missing_serial", "checks": []}
    with PROFILE_PATH.open(encoding="utf-8") as stream:
        profile = json.load(stream)
    expected = {
        "transport": (["get-state"], "device"),
        "device": (["shell", "getprop", "ro.product.device"], profile["target"]["device"]),
        "abi": (["shell", "getprop", "ro.product.cpu.abi"], profile["target"]["architecture"]),
        "build_id": (["shell", "getprop", "ro.build.id"], profile["aosp"]["release_build"]),
        "page_size": (["shell", "getconf", "PAGE_SIZE"], str(profile["target"]["page_size_bytes"])),
    }
    checks = []
    for name, (args, wanted) in expected.items():
        result = adb_call(adb, serial, args)
        actual = result["output"].strip()
        ok = result["returncode"] == 0 and actual == wanted
        checks.append({"name": name, "expected": wanted, "actual": actual, "ok": ok, "command": result["command"]})
        if not ok:
            return {"status": "blocked_wrong_reference", "checks": checks}
    return {"status": "passed", "checks": checks}


def execute_scenario(apk: Path, metadata: dict[str, Any], adb: str, serial: str | None) -> list[dict[str, Any]]:
    package = metadata.get("package")
    activity = metadata.get("launchable_activity")
    if not package:
        return [{"scenario": "install", "status": "blocked_missing_package_metadata"}]
    results: list[dict[str, Any]] = []

    def step(name: str, command: list[str]) -> bool:
        result = adb_call(adb, serial, command)
        result.update({"scenario": name, "status": "passed" if result["returncode"] == 0 else "failed"})
        results.append(result)
        # A failed install or lifecycle operation must not be followed by
        # writes that could make a partial guest run look like a valid one.
        # The caller records the remaining scenarios as not_run.
        return result["returncode"] == 0

    if not step("install", ["install", "-r", str(apk)]):
        return results
    if activity:
        if not step("launch", ["shell", "am", "start", "-n", f"{package}/{activity}"]):
            return results
    else:
        if not step("launch", ["shell", "monkey", "-p", package, "1"]):
            return results
    if not step("main_surface", ["shell", "dumpsys", "activity", "activities"]):
        return results
    if not step("input", ["shell", "input", "text", "A08_test"]):
        return results
    if not step("background", ["shell", "input", "keyevent", "KEYCODE_HOME"]):
        return results
    if not step("foreground", ["shell", "monkey", "-p", package, "1"]):
        return results
    # The runner cannot assume an app-specific save protocol.  We record the
    # process/data observation and leave semantic verification to the workload.
    if not step("save_data", ["shell", "dumpsys", "package", package]):
        return results
    if not step("exit", ["shell", "am", "force-stop", package]):
        return results
    if activity:
        step("restart", ["shell", "am", "start", "-n", f"{package}/{activity}"])
    else:
        step("restart", ["shell", "monkey", "-p", package, "1"])
    return results


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--aapt2")
    parser.add_argument("--adb", help="adb binary; required only with --execute")
    parser.add_argument("--serial")
    parser.add_argument("--execute", action="store_true", help="run the opt-in ADB scenario")
    args = parser.parse_args(argv)
    if args.execute and not args.adb and not shutil.which("adb"):
        parser.error("--execute requires --adb or an adb binary on PATH")
    apk = args.apk.resolve()
    metadata = inventory(apk, args.aapt2)
    report: dict[str, Any] = {
        "schema_version": 1,
        "execution_class": "android-guest-reference" if args.execute else "apk-host-inventory",
        "native_android_claim": False,
        "apk": {
            "path": str(apk),
            "sha256": digest(apk),
            "size_bytes": apk.stat().st_size,
            "metadata": metadata,
        },
        "scenarios": [{"name": item, "status": "not_run"} for item in SCENARIOS],
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    if args.execute:
        adb = args.adb or shutil.which("adb")
        assert adb is not None
        identity = reference_target_check(adb, args.serial)
        if identity["status"] != "passed":
            report["scenarios"] = [{"name": SCENARIOS[0], "status": identity["status"]}]
            report["scenarios"] += [{"name": name, "status": "not_run"} for name in SCENARIOS[1:]]
            report["execution"] = {"adb": adb, "serial": args.serial, "status": "blocked", "identity": identity}
            encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(encoded, encoding="utf-8")
            else:
                print(encoded, end="")
            return 1
        executed = execute_scenario(apk, metadata, adb, args.serial)
        by_name = {item["scenario"]: item for item in executed}
        # Keep a stable complete schema even when a failed early step prevents
        # later guest writes. A not_run suffix is evidence of gating, not a
        # successful lifecycle step.
        scenario_records = []
        for name in SCENARIOS:
            item = by_name.get(name)
            if item is None:
                scenario_records.append({"name": name, "status": "not_run"})
            else:
                item = dict(item)
                item["name"] = item.pop("scenario")
                scenario_records.append(item)
        report["scenarios"] = scenario_records
        statuses = [item["status"] for item in executed]
        # Treat any status outside the explicit all-passed set as blocked or
        # failed. Unknown future statuses must never silently become success.
        if statuses and all(status == "passed" for status in statuses):
            execution_status = "passed"
        elif "failed" in statuses:
            execution_status = "failed"
        else:
            execution_status = "blocked"
        report["execution"] = {"adb": adb, "serial": args.serial, "status": execution_status, "identity": identity}
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 1 if args.execute and report["execution"]["status"] != "passed" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
