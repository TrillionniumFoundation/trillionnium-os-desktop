#!/usr/bin/env python3
"""Pure parser/admission controls using actual historical host output.

No host test binary, Android command, service or device operation is executed.
Mutated XML/registration values below are declared negative parser fixtures.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import importlib.util
import json
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).parent
    spec = importlib.util.spec_from_file_location("owned_host_wrapper_for_local_controls", here / "host_suite.py")
    wrapper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wrapper)
    reference = wrapper.contract()
    for name, row in reference["source_pins"].items():
        wrapper.need(wrapper.sha(args.reference / name) == row["sha256"], "historical reference changed")
    registration = (args.reference / "1-list.stdout").read_bytes()
    original_xml = (args.reference / "3-results.xml").read_bytes()
    controls = []

    def check(name, function, reject=False):
        error = None
        try:
            function()
        except (RuntimeError, KeyError, TypeError, ValueError, ET.ParseError) as failure:
            error = repr(failure)
        passed = (error is not None) == reject
        controls.append({"name": name, "passed": passed, "expected_rejection": reject, "error": error})
        wrapper.need(passed, "local control failed: " + name)

    check("historical-complete-registration", lambda: wrapper.need(wrapper.registration(registration) == reference["registered"], "registration mismatch"))
    check("historical-full-XML-contract", lambda: wrapper.assess_xml(original_xml, reference))
    check("duplicate-registration-rejected", lambda: wrapper.registration(registration + b"GetArm64CpuStateTest.\n  TestErrorArch\n"), True)
    check("partial-registration-rejected", lambda: wrapper.need(wrapper.registration(registration.rsplit(b"\n", 2)[0]) == reference["registered"], "registration incomplete"), True)
    check("unexpected-list-output-rejected", lambda: wrapper.registration(b"unexpected registration header\n" + registration), True)
    check("duplicate-JSON-key-rejected", lambda: wrapper.json_bytes(b'{"state":"failed","state":"PASS_FULL_HOST_SUITE"}'), True)

    def mutated(label, edit):
        root = ET.fromstring(original_xml)
        edit(root)
        check(label, lambda: wrapper.assess_xml(ET.tostring(root), reference), True)

    mutated("missing-test-with-unchanged-root-count-rejected", lambda root: root[0].remove(root[0].find("testcase")))
    mutated("duplicated-case-rejected", lambda root: root[0].append(copy.deepcopy(root[0].find("testcase"))))
    mutated("failure-leaf-with-false-zero-summary-rejected", lambda root: ET.SubElement(root[0].find("testcase"), "failure", {"message": "declared negative fixture"}))
    mutated("missing-whole-suite-rejected", lambda root: root.remove(root[0]))
    mutated("root-count-rejected", lambda root: root.set("tests", "3791"))
    mutated("suite-summary-count-rejected", lambda root: root[0].set("tests", "1089"))
    mutated("new-skipped-case-rejected", lambda root: root[0].find("testcase").set("result", "skipped"))
    mutated("uncompleted-case-rejected", lambda root: root[0].find("testcase").set("result", "unknown"))
    mutated("disabled-test-silently-dropped-rejected", lambda root: next(c for c in root.iter("testcase") if c.get("status") == "notrun").set("name", "different_disabled_test"))
    mutated("skip-reason-changed-rejected", lambda root: next(root.iter("skipped")).set("message", "file.cc:1\nnew unrelated skip"))
    check("truncated-XML-rejected", lambda: wrapper.assess_xml(original_xml[:-20], reference), True)
    check("XML-entity-declaration-rejected", lambda: wrapper.assess_xml(b'<!DOCTYPE testsuites [<!ENTITY x "x">]>' + original_xml, reference), True)
    baseline_layout = json.loads((here / "r16-host-layout.json").read_text())
    check("baseline-exact-layout-pin", lambda: wrapper.need(wrapper.sha(here / "r16-host-layout.json") == wrapper.R16_LAYOUT_SHA and
        len(baseline_layout["data"]) == 3 and len(baseline_layout["shared_libraries"]) == 3 and
        baseline_layout["binary"]["sha256"] == wrapper.R16_BINARY_SHA, "baseline layout differs"))
    print(json.dumps({"schema": 1, "state": "LOCAL_HOST_WRAPPER_PARSER_CONTROLS_PASS", "controls": controls,
        "historical_reference": reference["source_pins"], "device_operations": 0, "native_execution": False,
        "new_baseline_execution": "NOT_RUN", "candidate_execution": "NOT_RUN",
        "mutation_scope": "in-memory negative parser fixtures only"}, indent=2))


if __name__ == "__main__":
    main()
