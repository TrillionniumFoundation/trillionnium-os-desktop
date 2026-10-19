#!/usr/bin/env python3
"""One unchanged legacy Python workload, isolated by the full-profile runner."""
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
CASES = ("sqlite_wal", "uds_path", "nss_tls")


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in CASES:
        print("A04_PYTHON_ERROR invalid case invocation", file=sys.stderr)
        return 2
    name, scratch = sys.argv[1], Path(sys.argv[2])
    if str(scratch) != "/tmp/a04/" + name or sys.executable != "/usr/bin/python3.12":
        print("A04_PYTHON_ERROR runtime or scratch path differs", file=sys.stderr)
        return 2
    spec = importlib.util.spec_from_file_location(
        "a04_legacy_python_workload", Path(__file__).with_name("run.py"))
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    functions = {"sqlite_wal": legacy.sqlite_test, "uds_path": legacy.unix_path_test,
                 "nss_tls": legacy.nss_tls_test}
    try:
        facts = functions[name](scratch)
    except Exception as error:
        print("A04_PYTHON_ERROR " + type(error).__name__ + ": " + str(error),
              file=sys.stderr)
        return 1
    print(json.dumps(facts, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0 if facts.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
