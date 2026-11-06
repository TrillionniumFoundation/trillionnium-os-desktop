#!/usr/bin/env python3
"""Local deterministic assembly from reviewed exact reference definitions."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]


def raw(path, size, digest):
    data = (PROJECT / path).read_bytes()
    assert len(data) == size and hashlib.sha256(data).hexdigest() == digest, path
    return data.decode()


def function(text, name):
    node = next(node for node in ast.parse(text).body if isinstance(node, ast.FunctionDef) and node.name == name)
    return ast.get_source_segment(text, node)


def assignments(text, names):
    nodes = [node for node in ast.parse(text).body if isinstance(node, ast.Assign) and
             any(isinstance(target, ast.Name) and target.id in names for target in node.targets)]
    assert len(nodes) == len(names)
    return "\n".join(ast.get_source_segment(text, node) for node in nodes)


def main():
    original47 = raw("successor_audit_requests/explicit47_scope_r2/observe_explicit_47.py", 18139,
                     "56922fbe372cf8cd2d0e39f75ddb69b16843f098d8090d65834b5737db04a656")
    binding = raw("successor_qa/reconstructed/source-generation-r2/recorder/main_binding.py", 9450,
                  "b7f7350f45e7c6764a6d101785dfda5febc43b679999a308718aa3534bd5eee4")
    shared = raw("successor_qa/reconstructed/source-generation-r2/recorder/source_contract.py", 20684,
                 "0cbb8c79b494a529e7cb7fe0ce99eec444103ae7207a02a768dbc76d3bb3cbc3")
    core = raw("recovery/successor_runtime.py", 65302,
               "53f79b2bdfc694a3006c0d33232a277a8729773407f301af6a07aa6a46f490d5")
    raw("successor_audit_requests/reference/install_successor_native.py", 31327,
        "ad4227b4c63033018bd1147c3c589b2632168766306791696aabc53583229c96")
    stage = "/home/alex/work/pocket4-current-readonly-services-source-20261106-r2"
    transport = (ROOT / "readonly_services_transport.py").read_bytes()
    transport_pin = {"path": stage+"/readonly_services_transport.py", "bytes": len(transport), "sha256": hashlib.sha256(transport).hexdigest()}
    common = '''#!/usr/bin/env python3
"""New explicit47-bound read-only user0 PM/resolver and three service help reads.

This standalone source does not import or extend an existing per-App Flow or
its source contract. Frozen R5 entry/classpath primitives remain unchanged.
"""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
import types
import zlib

sys.dont_write_bytecode = True
'''
    common += assignments(original47, {"EPOCH", "BASE", "GUARD", "LAUNCHERS", "ACTIONS", "HELPER", "STAT"}) + "\n"
    common += "PACKAGES = sorted((*LAUNCHERS, ACTIONS, HELPER))\n"
    common += "STAGE = " + repr(stage) + "\nOUTPUT = '/home/alex/work/pocket4-current-readonly-services-observation-20261106-r2'\n"
    common += "APP_SCOPE = " + repr({"path": "/home/alex/work/pocket4-current-explicit-47-app-observation-20261106-r2/app-scope.private.json", "bytes":58854,
                                  "sha256":"44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f"}) + "\n"
    common += "TRANSPORT = " + repr(transport_pin) + "\n"
    common += "NATIVE_HELPERS = " + repr({"path":"/home/alex/work/pocket4-successor-install-audit-source-20261106-r1/install_successor_native.py", "bytes":31327,
                                        "sha256":"ad4227b4c63033018bd1147c3c589b2632168766306791696aabc53583229c96"}) + "\n\n"
    common += "\n\n".join(function(original47, name) for name in ("need", "sha", "canonical", "parse", "read_root_pin", "load_source"))
    common += "\n\nrequire = need\ndigest = sha\n\n"
    common += assignments(shared, {"HELPER_ROOT", "HELPER_PATH", "HELPER_SOURCE", "HELPER_SHA", "HELPER_BYTES", "HELPER_SOURCE_SHA", "HELPER_QUALIFICATION", "HELPER_QUALIFICATION_SHA"}) + "\n\n"
    common += "\n\n".join(function(shared, name) for name in ("bounded_file", "verify_shared_helper")) + "\n\n"
    common += "\n\n".join(function(binding, name) for name in ("same_epoch_identity", "selected_environment", "main_classpaths")) + "\n\n"
    standalone_error = function(core, "safe_error").replace("isinstance(error, Rejected)", "isinstance(error, RuntimeError)")
    assert standalone_error != function(core, "safe_error")
    common += standalone_error + "\n\n"
    old_runner = function(core, "bounded_child")
    new_runner = old_runner.replace("def bounded_child(argv, seconds=5, limit=65536):", "def held_bounded_child(argv, seconds, limit, pass_fds, host_env):")
    new_runner = new_runner.replace('cwd="/", env=ENV, close_fds=True, start_new_session=True)',
                                    'cwd="/", env=host_env, pass_fds=pass_fds, close_fds=True, start_new_session=True)')
    assert old_runner != new_runner and "env=ENV" not in new_runner
    common += new_runner + "\n\n" + (ROOT / "worker_body.py").read_text()
    compile(common, "observe_current_services.py", "exec")
    with (ROOT / "observe_current_services.py").open("xb") as handle:
        handle.write(common.encode())
    diff = "".join(difflib.unified_diff(old_runner.splitlines(True), new_runner.splitlines(True), fromfile="original-frozen-core-bounded-child", tofile="seven-authority-fd-adapter"))
    with (ROOT / "runner-against-original.diff").open("xb") as handle:
        handle.write(diff.encode())
    pin = {"path": stage+"/observe_current_services.py", "bytes":len(common.encode()), "sha256":hashlib.sha256(common.encode()).hexdigest()}
    namespace = {"__name__":"candidate_definitions", "__file__":str(ROOT / "observe_current_services.py")}
    exec(compile(common, "observe_current_services.py", "exec"), namespace)
    request = {"schema":"pocket4-current-readonly-services-request-v1", "guard":namespace["GUARD"], "app_scope":namespace["APP_SCOPE"],
               "packages":namespace["PACKAGES"], "worker":pin, "transport":transport_pin, "output_root":namespace["OUTPUT"]}
    with (ROOT / "request.review-only.json").open("xb") as handle:
        handle.write((json.dumps(request,sort_keys=True,separators=(",", ":"),ensure_ascii=True)+"\n").encode())
    print(json.dumps({"worker":pin,"transport":transport_pin}))


if __name__ == "__main__":
    main()
