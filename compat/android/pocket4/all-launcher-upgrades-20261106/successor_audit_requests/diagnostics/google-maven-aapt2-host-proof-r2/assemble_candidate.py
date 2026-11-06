#!/usr/bin/env python3
"""Assemble new host-only tool preparation from already reviewed definitions."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[2]


def source(path, size, digest):
    raw = (PROJECT / path).read_bytes()
    assert len(raw) == size and hashlib.sha256(raw).hexdigest() == digest, path
    return raw.decode("utf-8")


def definition(text, name):
    node = next(n for n in ast.parse(text).body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name)
    return ast.get_source_segment(text, node)


def main():
    prior = source("successor_audit_requests/diagnostics/aapt2-provenance-interface-r1/candidate-r2/worker_body.py", 19451,
                   "73b7a731d866dbea5f94c9e2b7ca6cce4477a364c75a49440eb1012b93e619c9")
    reader = source("successor_audit_requests/diagnostics/aapt2-candidate-inventory-r1/inventory_fixed_aapt2_candidates.py", 10557,
                    "5b56807f415bdce9be10f90952adfee063cc9f26bcd4deb91d8897bdd9b672f3")
    elf = source("successor_audit_requests/diagnostics/aapt2-provenance-interface-r1/elf_static.py", 11269,
                 "f829cd8664dc5f7172274b4917f70c60114c3bfb43694422c1a5412718b432dd")
    download = source("successor_audit_requests/diagnostics/google-maven-aapt2-artifact-r1/fetch_verified_artifact.py", 6476,
                      "3816e0c173fd14d9e615a40c1086f84af5e77458741a28365aaaab00e8445517")
    terminal = source("successor_audit_requests/diagnostics/google-maven-aapt2-artifact-r1/status-1.original.txt", 731,
                      "e7cec94c8f5a2b012e7bfecd40cef5065c7d23516ff1a81400673eadb959c458")
    jar = {"path": "/home/alex/work/pocket4-official-aapt2-9.5.1-16666295-20261106-r1/aapt2-9.5.1-16666295-linux.jar",
           "bytes": 2451278, "sha256": "fa1014cb1431622d292ef55ba870e75882ea19987bec541698b912f446a2d08f"}
    receipt = {"path": "/home/alex/work/pocket4-official-aapt2-9.5.1-16666295-20261106-r1/download-result.json",
               "bytes": 1429, "sha256": "e2cd6b1838f70e2052c01d0695602b74c3224b0dfc6fb8b4c4a70eccdcf18aa3"}
    readback = json.loads((PROJECT / "successor_audit_requests/diagnostics/google-maven-aapt2-artifact-r1/read-1.original.txt").read_bytes())
    receipt_raw = bytes.fromhex(readback["stdout"]["bytes_hex"])
    assert len(receipt_raw) == receipt["bytes"] and hashlib.sha256(receipt_raw).hexdigest() == receipt["sha256"]
    expected_members = json.loads(receipt_raw)["jar_members"]
    common = '''#!/usr/bin/env python3
"""Bind one exact official JAR, extract only aapt2, inspect ELF, run version once.

Host-only. This is neither an Android installer nor an APK/resource audit.
The original read-only reader, static ELF parser and owned child runner remain
the implementation references. No Main, UI, namespace, permission or ADB work.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import time
import types
import zipfile
import zlib
sys.dont_write_bytecode = True
'''
    constants = {
        "READER_SOURCE": reader, "READER_SHA": hashlib.sha256(reader.encode()).hexdigest(),
        "ELF_SOURCE": elf, "ELF_SHA": hashlib.sha256(elf.encode()).hexdigest(),
        "JAR": jar, "DOWNLOAD": receipt, "USER_INPUTS": {jar["path"]: jar, receipt["path"]: receipt},
        "USER_INPUT_MODES": {jar["path"]: 0o400, receipt["path"]: 0o600},
        "EXPECTED_MEMBERS": expected_members, "DOWNLOAD_TERMINAL_RAW": terminal,
        "OFFICIAL_URL": "https://dl.google.com/dl/android/maven2/com/android/tools/build/aapt2/9.5.1-16666295/aapt2-9.5.1-16666295-linux.jar",
        "SOURCE_ROOT": "/home/alex/work/pocket4-official-aapt2-host-tool-source-20261106-r2",
        "OUTPUT": "/home/alex/work/pocket4-official-aapt2-host-tool-proof-20261106-r2",
        "COLLECTOR": {"path": "/home/alex/work/pocket4-successor-install-audit-source-20261106-r1/audit_successor_apks.py",
                      "bytes": 29242, "sha256": "faff199c1f6218b3c01d87e44be610d6fa211de396b5e8c862c188dec59d284a"},
        "SYSTEM_LIBRARY_ROOTS": ("/usr/lib", "/lib", "/lib64"),
        "SEARCH_DIRS": ("/usr/lib/x86_64-linux-gnu/android", "/usr/lib/x86_64-linux-gnu", "/lib/x86_64-linux-gnu", "/usr/lib64", "/lib64"),
        "MAX_FILE": 64 * 1024 * 1024, "MAX_TOTAL": 512 * 1024 * 1024, "MAX_RESULT": 262144,
    }
    common += "\n".join(key + " = " + repr(value) for key, value in constants.items()) + "\n\n"
    common += "\n\n".join(definition(prior, name) for name in ("required", "sha", "canonical", "frozen_module")) + "\n\n"
    original_bound = definition(prior, "BoundFile")
    bound = original_bound.replace('"""Hold one root-owned host file and retain the original reader\'s guards."""',
                                   '"""Root-owned tools/dependencies; only two exact pinned UID1000 download inputs."""')
    bound = bound.replace('self.held = None\n        observed, unused = reader.read_regular(self.resolved, limit, True, expected)',
                          'self.held = None\n        self.user_input = path in USER_INPUTS\n'
                          '        required(not self.user_input or (not resolve and expected == USER_INPUTS[path]), "ONLY_TWO_PINNED_OPERATOR_INPUTS")\n'
                          '        observed, unused = reader.read_regular(self.resolved, limit, not self.user_input, expected)')
    bound = bound.replace('self.observed = observed\n        try:',
                          'required(observed["stat"]["st_uid"] == (1000 if self.user_input else 0), "EXACT_HOST_FILE_OWNER_REQUIRED")\n'
                          '        required(not self.user_input or stat.S_IMODE(observed["stat"]["st_mode"]) == USER_INPUT_MODES[path], "EXACT_DOWNLOAD_INPUT_MODE")\n'
                          '        self.observed = observed\n        try:')
    bound = bound.replace('self.reader.read_regular(self.resolved, self.limit, True)',
                          'self.reader.read_regular(self.resolved, self.limit, not self.user_input)')
    assert bound != original_bound and 'self.user_input = path in USER_INPUTS' in bound
    common += bound + "\n\n"
    common += "\n\n".join(definition(prior, name) for name in
                            ("EvidenceStore", "in_system_library_root", "search_paths", "resolve_dependency")) + "\n\n"
    common += definition(download, "census") + "\n\n" + (ROOT / "worker_body.py").read_text()
    compile(common, "prepare_official_aapt2.py", "exec")
    with (ROOT / "prepare_official_aapt2.py").open("xb") as handle:
        handle.write(common.encode("utf-8"))
    difference = "".join(difflib.unified_diff(original_bound.splitlines(True), bound.splitlines(True),
                        fromfile="original-reviewed-root-owned-BoundFile", tofile="root-files-plus-two-exact-official-download-inputs"))
    with (ROOT / "host-file-binding-against-original.diff").open("xb") as handle:
        handle.write(difference.encode("utf-8"))
    print(json.dumps({"source_bytes": len(common.encode()), "source_sha256": hashlib.sha256(common.encode()).hexdigest(),
                      "runtime_executed": False, "root_dependencies_not_widened": True}))


if __name__ == "__main__":
    main()
