#!/usr/bin/env python3
"""Small local-only boundary controls; synthetic new rows are not observations."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent


def need(value, code):
    if not value:
        raise RuntimeError(code)


def load(name):
    spec = importlib.util.spec_from_file_location("local_" + name, ROOT / (name + ".py"))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def census():
    result = {}
    for item in sorted(os.listdir("/proc/self/fd"), key=int):
        try:
            st = os.fstat(int(item))
            result[item] = {"link": os.readlink("/proc/self/fd/" + item), "dev": st.st_dev,
                            "ino": st.st_ino, "mode": st.st_mode}
        except FileNotFoundError:
            continue
        except OSError as error:
            if error.errno != 9:
                raise
    return result


def main():
    before = census()
    worker, transport = load("observe_native46"), load("readonly_services_transport")
    raw = (ROOT / "inputs/previous_pm.json").read_bytes()
    need(len(raw) == 79176 and hashlib.sha256(raw).hexdigest() ==
         "185c6b0900aab78228e44788ea28b10d71c39cfeee8846fcb8c99c13a9f123fc", "ACTUAL_PRIOR_INPUT_PIN")
    previous = json.loads(raw)
    # The identity is deliberately arbitrary and is only a synthetic parser
    # control. No actual UID, version, source or signature is inferred from it.
    synthetic = {"package": worker.NEW_PACKAGE, "version_code": 0, "uids": [19001]}
    installed = sorted([*previous["installed_packages"], synthetic], key=lambda r: (r["package"], r["version_code"], r["uids"]))
    resolver = sorted([*previous["MAIN_LAUNCHER_components"], worker.component(worker.NEW_COMPONENT)], key=lambda r: r["component"])
    native = {"applications": [{"package": row["package"], "component": row["component"]} for row in resolver]}
    results = []
    compare = worker.discovery_comparison
    need(compare(installed, resolver, native, previous)["matches_only_the_observed_new_component"] is True,
         "CLOSED_SYNTHETIC_DISCOVERY_SHAPE")
    altered = copy.deepcopy(installed)
    old = next(row for row in altered if row["package"] != worker.NEW_PACKAGE)
    old["uids"][0] += 1
    need(compare(altered, resolver, native, previous)["matches_only_the_observed_new_component"] is False,
         "CHANGED_OLD_UID_MUST_REJECT")
    other = worker.component("org.example.unobserved/org.example.unobserved.Main")
    more_resolver = [*resolver, other]
    more_native = {"applications": [*native["applications"], {"package": other["package"], "component": other["component"]}]}
    need(compare(installed, more_resolver, more_native, previous)["matches_only_the_observed_new_component"] is False,
         "ADDITIONAL_COMPONENT_MUST_NOT_BE_OMITTED")
    need(compare(installed, resolver[:-1], native, previous)["matches_only_the_observed_new_component"] is False,
         "FRAMEWORK_NATIVE_DIVERGENCE_MUST_REJECT")
    results.append({"name": "full_sets_and_old_UID_cannot_be_relaxed", "ok": True,
                    "synthetic_new_row_only": True, "changed_old_UID_rejected": True,
                    "unexpected_component_rejected": True, "resolver_native_divergence_rejected": True})
    duplicate = {"applications": [*native["applications"], native["applications"][-1]]}
    try:
        compare(installed, resolver, duplicate, previous)
    except RuntimeError as error:
        need(str(error) == "DUPLICATE_NATIVE_DISCOVERY_COMPONENT", "PRECISE_DUPLICATE_REJECTION")
    else:
        raise RuntimeError("DUPLICATE_NATIVE_COMPONENT_ACCEPTED")
    results.append({"name": "duplicate_native_component_rejected", "ok": True})
    header = "  Package [" + worker.NEW_PACKAGE + "] (1234abcd):\n"
    dump = ("Packages:\n" + header + "    appId=19001\n    versionCode=0 minSdk=23 targetSdk=36\n" +
            "    codePath=/data/app/synthetic-control\n    User 10: installed=true\n" +
            "      firstInstallTime=SHOULD_NOT_BE_USER0\n").encode()
    parsed = worker.selected_dump_metadata(dump, worker.NEW_PACKAGE, 19001, 0)
    need(parsed["package_identity_matches_fresh_UID"] is True and parsed["fields"]["versionCode"]["integer"] == 0 and
         parsed["fields"]["versionName"]["status"] == "UNKNOWN" and
         parsed["fields"]["firstInstallTime"]["status"] == "UNKNOWN", "MISSING_OR_OTHER_USER_METADATA_UNKNOWN")
    ambiguous = dump + header.encode() + b"    appId=19001\n    versionName=untrusted-second-block\n"
    need(worker.selected_dump_metadata(ambiguous, worker.NEW_PACKAGE, 19001, 0)["status"] == "UNKNOWN",
         "DUPLICATE_PACKAGE_ATTRIBUTION_MUST_BE_UNKNOWN")
    need(worker.selected_dump_metadata(dump, worker.NEW_PACKAGE, 19002, 0)["status"] == "UNKNOWN",
         "WRONG_UID_MUST_NOT_BE_ATTRIBUTED")
    duplicate_name = dump + b"    versionName=A\n    versionName=B\n"
    need(worker.selected_dump_metadata(duplicate_name, worker.NEW_PACKAGE, 19001, 0)["fields"]["versionName"]["status"] == "UNKNOWN",
         "DUPLICATE_VERSION_FIELD_MUST_NOT_PICK_ONE")
    results.append({"name": "package_UID_user_and_missing_field_attribution", "ok": True,
                    "unknown_not_fabricated": True, "version_name_not_inferred_from_zero_code": True})
    bad_version = dump.replace(b"versionCode=0", b"versionCode=1")
    try:
        worker.selected_dump_metadata(bad_version, worker.NEW_PACKAGE, 19001, 0)
    except RuntimeError as error:
        need(str(error) == "DUMP_AND_FRESH_PM_VERSION_CODE_DIFFER", "PRECISE_PM_VERSION_REJECTION")
    else:
        raise RuntimeError("CONTRADICTING_PM_VERSION_ACCEPTED")
    results.append({"name": "contradictory_attributed_service_version_rejected", "ok": True})
    need(len(transport.READ_ONLY_COMMANDS) == 6 and transport.READ_ONLY_COMMANDS[-1] ==
         ("/system/bin/cmd", "package", "dump-package", worker.NEW_PACKAGE) and
         transport.READ_ONLY_COMMANDS[1] == transport.READ_ONLY_COMMANDS[3] and
         transport.READ_ONLY_COMMANDS[2] == transport.READ_ONLY_COMMANDS[4] and
         all(not ({"grant", "revoke", "install", "uninstall", "start", "stop", "clear", "set"} & set(argv))
             for argv in transport.READ_ONLY_COMMANDS), "CLOSED_READONLY_COMMANDS")
    results.append({"name": "exact_six_readonly_commands", "ok": True, "device_calls": 0})
    for file in (ROOT / "observe_native46.py", ROOT / "owned_readonly_lifetime.py", ROOT / "stage_discovery_once.py"):
        compile(file.read_bytes(), str(file), "exec")
    after = census()
    need(after == before, "LOCAL_FD_IDENTITIES_CHANGED")
    value = {"schema": "pocket4-native46-local-controls-v1", "ok": True, "cases": results,
             "uid": os.getuid(), "euid": os.geteuid(), "FDs_before": before, "FDs_after": after,
             "new_device_observation": False, "Main_or_remote_calls": 0,
             "synthetic_identity_is_not_new_package_evidence": True}
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
