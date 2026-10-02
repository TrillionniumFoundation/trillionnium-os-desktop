#!/usr/bin/env python3
"""Closed exact-pin source/patch and actual semantic-corpus result verifier.

Default verification is read-only. Upstream verification applies all patches only in a
temporary copied source set, preserving the original pristine checkout on every outcome.
The standalone Rust check compiles the actual new module, not Servo or a product runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

try:
    from .artifact_evidence import load, open_file, safe_relative, load_json_strict
except ImportError:
    from artifact_evidence import load, open_file, safe_relative, load_json_strict

PIN = "670ae8a70801b162e186f81cbb5bdd2d59c39108"
MANIFEST = "manifests/lab-s08-semantic-custody.v1.json"
PATCH = "manifests/servo-patches/s08-semantic-custody-v1/000.patch"
PREREQUISITE = "manifests/lab-d3-servo-retained-node-action.v1.json"
ADAPTER = "experiments/servo-s08-runtime/accessibility_server.rs"
WORKFLOW = ".github/workflows/s08-servo-vertical-slice.yml"
RETAINED_TESTS = [
    "test_retained_accessibility_click_dispatches_exactly_once",
    "test_retained_accessibility_rejects_unadvertised_and_unsupported_requests",
    "test_retained_accessibility_rejects_replaced_node_identity",
    "test_retained_accessibility_rejects_inactive_and_stale_tree",
    "test_retained_accessibility_rejects_disabled_hidden_and_non_element_targets",
    "test_retained_accessibility_dropped_callback_does_not_duplicate_dispatch",
]
SEMANTIC_TEST = "test_trillionnium_s08_semantic_custody"
ORIGINAL_MAILBOX_BODY_SHA256 = "4500fb1c3d5b47ab3ff056c92e319842e2bd481afebcb39fdcb3a098e9d3a990"
RUNTIME_CORPUS = {
    "retained_test_names": RETAINED_TESTS, "fresh_process_per_retained_test": True,
    "exact_filter_from_actual_list": True, "expected_tests_per_retained_process": 1,
    "semantic_servo_owners": 1, "semantic_webviews": 7,
}
SEMANTIC_MUTATIONS = [
    ("same_node_label", "target.textContent='Changed target'", "TargetSemanticMismatch"),
    ("same_node_role", "target.setAttribute('role','heading')", "TargetSemanticMismatch"),
    ("same_node_ancestry", "document.getElementById('other').appendChild(target)", "TargetSemanticMismatch"),
    ("replacement", "target.replaceWith(target.cloneNode(true))", "StaleNode"),
    ("disabled", "target.disabled=true", "TargetDisabled"),
    ("hidden", "target.style.display='none'", "TargetNotRendered"),
]
FINAL_SEMANTIC_REFRESH = {
    "source": "current_dom_properties_during_checked_script_layout_reflow",
    "ordinary_damage_is_final_authority": False,
    "retained_tree_node_epoch_identity_preserved": True,
    "snapshot_requires_completed_checked_reflow": True,
    "stimulus_same_task_dom_boolean_required": True,
    "unfiltered_upstream_layout_unit_tests_required": True,
}
DOM_CONDITIONS = {
    "same_node_label": "target.textContent === 'Changed target'",
    "same_node_role": "target.getAttribute('role') === 'heading'",
    "same_node_ancestry": "target.parentElement === document.getElementById('other')",
    "replacement": "!target.isConnected && document.getElementById('target') !== target",
    "disabled": "target.disabled === true",
    "hidden": "target.style.display === 'none'",
}
ALLOWED_PATHS = [
    "Cargo.lock", "components/constellation/constellation.rs", "components/constellation/tracing.rs",
    "components/layout/accessibility_tree.rs", "components/layout/layout_impl.rs",
    "components/script/event_loop/script_thread.rs", "components/script/messaging.rs", "components/servo/lib.rs",
    "components/servo/webview.rs", "components/shared/base/Cargo.toml",
    "components/shared/base/accessibility_semantics.rs", "components/shared/base/lib.rs",
    "components/shared/constellation/lib.rs", "components/shared/layout/lib.rs",
    "components/shared/script/lib.rs",
]
SEMANTIC_SCHEMA = {
    "version": 1, "name_encoding": "raw_utf8_without_normalization",
    "maximum_name_bytes": 1024, "maximum_ancestry_nodes": 16,
    "maximum_name_preimage_bytes": 1057, "maximum_structural_preimage_bytes": 16647,
    "maximum_result_bytes": 4096,
    "ancestry_order": "retained_leaf_to_document_root_no_graft",
    "hash": "sha2_0.11.0_sha256", "name_domain": "trillionnium.accesskit.name\\0",
    "structural_domain": "trillionnium.accesskit.semantic\\0",
    "ipc_shape": "fixed_size_serde_closed_fields",
}
NEGATIVES = {
    "same_node_label": "TargetSemanticMismatch",
    "same_node_role": "TargetSemanticMismatch",
    "same_node_ancestry": "TargetSemanticMismatch",
    "replacement": "StaleNode", "disabled": "TargetDisabled",
    "hidden": "TargetNotRendered", "stale_epoch_expectation": "TargetSemanticMismatch",
}
ORIGINAL_STIMULUS = {
    "agentport_requests": 10, "servo_commands": 9, "durable_receipt_facts": 30,
    "positive_dom_clicks": 1, "s07_patch_and_test_bodies_unchanged": True,
}
CLAIMS = {
    "actual_servo_execution_requires_exact_pin_ci": True,
    "source_fixtures_are_servo_proof": False, "installed_product_activation": False,
    "final_script_peer_control_custody": False, "external_effect_authority": False,
    "release": False,
}
MAX_SOURCE_BYTES = 1024 * 1024
MAX_PATCH_BYTES = 256 * 1024
MAX_RESULT_BYTES = 4096
HUNK = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:[^\n]*)\n\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SHA1 = re.compile(r"[0-9a-f]{40}\Z")
TEST_NAME = r"[A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z_][A-Za-z0-9_]*)*"


def read(path: Path, maximum: int = MAX_SOURCE_BYTES) -> bytes:
    with os.fdopen(open_file(path.absolute()), "rb") as stream:
        before = os.fstat(stream.fileno())
        if before.st_size > maximum:
            raise ValueError("source input exceeds byte bound")
        data = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
        fields = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if len(data) > maximum or len(data) != before.st_size or fields(before) != fields(after):
            raise ValueError("source input changed during retained read")
    return data


def exact(value: object, expected: object, label: str) -> None:
    # Canonical JSON distinguishes integer/bool/float aliases in source profiles and results.
    import json
    if isinstance(value, set) and isinstance(expected, set):
        if value != expected:
            raise ValueError(f"{label} differs from closed schema")
        return
    if json.dumps(value, sort_keys=True, separators=(",", ":")) != json.dumps(expected, sort_keys=True, separators=(",", ":")):
        raise ValueError(f"{label} differs from closed schema")


def fields(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    exact(set(value), expected, label)
    return value


def function_source(text: str, name: str) -> str:
    # These pinned, formatted top-level Rust functions end at a column-zero brace.
    matches = re.findall(r"(?ms)^fn " + re.escape(name) + r"\(.*?^}\n", text)
    if len(matches) != 1:
        raise ValueError("runtime function is absent or repeated")
    return matches[0]


def verify_runtime_corpus(root: Path, profile: object, prerequisite: dict[str, Any]) -> None:
    section = fields(profile, set(RUNTIME_CORPUS) | {"adapter_path", "adapter_sha256", "workflow_path", "workflow_sha256"}, "runtime corpus fields")
    exact({key: section[key] for key in RUNTIME_CORPUS}, RUNTIME_CORPUS, "runtime owner/process profile")
    for key, path in (("adapter", ADAPTER), ("workflow", WORKFLOW)):
        exact(section[key + "_path"], path, "runtime source path")
        exact(hashlib.sha256(read(root / path)).hexdigest(), section[key + "_sha256"], "runtime source digest")
    original_names = []
    for original in (prerequisite["patch"], prerequisite["hardening"]):
        for row in original["parts"]:
            data = read(root / safe_relative(row["path"]), MAX_PATCH_BYTES)
            exact(hashlib.sha256(data).hexdigest(), row["sha256"], "unchanged original S07 part")
            original_names += re.findall(r"(?m)^\+fn (test_retained_accessibility\w+)\(", data.decode("utf-8", "strict"))
    exact(original_names, RETAINED_TESTS, "original retained test inventory")
    source = read(root / ADAPTER).decode("utf-8", "strict")
    exact(hashlib.sha256(function_source(source, "test_trillionnium_s08_mailbox_server").encode()).hexdigest(), ORIGINAL_MAILBOX_BODY_SHA256, "unchanged original product/Servo test body")
    helper = function_source(source, "s08_build_webview_and_tree")
    body = function_source(source, SEMANTIC_TEST)
    if re.search(r"build_test\(|ServoTest::|ServoBuilder", helper):
        raise ValueError("per-case helper constructs a second Servo owner")
    for marker in ("servo_test: &ServoTest", "Rc::new(WebViewDelegateImpl::default())", "WebViewBuilder::new(servo_test.servo(), servo_test.rendering_context.clone())", "webview.set_accessibility_active(true)", "LoadStatus::Complete", "wait_for_min_updates(servo_test, delegate.clone(), 2)", "let tree = build_tree(updates)", "(delegate, webview, tree)"):
        if marker not in helper:
            raise ValueError("same-owner fresh WebView helper differs")
    if body.count("let servo_test = build_test();") != 1 or body.count("build_test(") != 1:
        raise ValueError("semantic corpus must construct exactly one Servo owner")
    if re.search(r"(?<!s08_)build_webview_and_tree\(|ServoTest::|ServoBuilder", body):
        raise ValueError("semantic case reconstructs the process-local Servo owner")
    if body.count("s08_build_webview_and_tree(") != 2 or body.index("let servo_test = build_test();") > body.index("let cases = ["):
        raise ValueError("semantic owner is not shared by both case paths")
    if body.count("std::env::") != 1:
        raise ValueError("semantic corpus adds a per-case environment selector")
    cases = re.search(r"(?s)let cases = \[(.*?)\n    \];", body)
    if cases is None:
        raise ValueError("semantic mutation inventory missing")
    tuple_pattern = r'\(\s*"([a-z_]+)",\s*"([^"\n]+)",\s*AccessibilityActionResult::([A-Za-z]+),\s*\)'
    exact(re.findall(tuple_pattern, cases[1]), SEMANTIC_MUTATIONS, "complete semantic mutation inventory")
    if re.sub(tuple_pattern, "", cases[1]).strip(" \n\t,"):
        raise ValueError("semantic mutation inventory contains another expression")
    for marker in ('for (name, mutation, expected_result) in cases {', 'assert_eq!(result, expected_result, "typed semantic refusal")', '"real refused target DOM click counter must be zero"', '"real DOM must retain zero epoch clicks"', '.checked_sub(1)', 'completed.push("{\\"case\\":\\"stale_epoch_expectation\\"'):
        if marker not in body:
            raise ValueError("complete semantic corpus gate missing")
    conditions = re.search(r'(?s)let dom_condition = match name \{(.*?)\n        \};', body)
    if conditions is None:
        raise ValueError("same-task DOM mutation observations missing")
    pairs = re.findall(r'"([a-z_]+)" => "([^"\n]+)"', conditions[1])
    exact(pairs, list(DOM_CONDITIONS.items()), "same-task actual DOM mutation conditions")
    for marker in ('let mutation_result = evaluate_javascript(&servo_test, webview.clone(), &stimulus);',
                   'matches!(mutation_result, Ok(servo::JSValue::Boolean(true)))',
                   "return ({dom_condition}) && document.getElementById('marker').textContent === 'Mutation done';",
                   'actual same-task DOM semantic mutation must complete'):
        if marker not in body:
            raise ValueError("same-task DOM mutation must return an observed Boolean")
    if body.index('matches!(mutation_result,') > body.index('let result = s08_perform_checked_action('):
        raise ValueError("DOM mutation observation must precede checked dispatch")
    mutation_to_dispatch = body[body.index('let stimulus = format!('):body.index('let result = s08_perform_checked_action(')]
    if body.count('evaluate_javascript(&servo_test, webview.clone(), &stimulus)') != 1 or mutation_to_dispatch.count('evaluate_javascript(') != 1:
        raise ValueError("mutation adds another pre-action evaluation")
    if re.search(r"\bspin\s*\(|s08_semantic_expectation\s*\(|wait_for_|sleep\s*\(", mutation_to_dispatch):
        raise ValueError("mutation observation adds a pre-action wait or refresh")
    workflow = read(root / WORKFLOW).decode("utf-8", "strict")
    layout_command = "            cargo test --locked -p servo-layout --lib"
    if re.findall(r"(?m)^            cargo test --locked -p servo-layout[^\n]*$", workflow) != [layout_command]:
        raise ValueError("exact-pin layout cfg(test) corpus must run unfiltered")
    if workflow.index(layout_command) > workflow.index('cargo test --locked -p servo --test accessibility -- --list'):
        raise ValueError("layout unit compilation must precede retained runtime inventory")
    for marker in ('cargo test --locked -p servo --test accessibility -- --list', '--retained-list "$retained/list.txt" --print-retained-names', 'mapfile -t retained_tests < "$retained/names.txt"', 'test "${#retained_tests[@]}" -eq 6', 'for index in "${!retained_tests[@]}"; do', '"${retained_tests[$index]}" -- --exact --nocapture', '--retained-log-dir "$retained"', 'test_trillionnium_s08_semantic_custody -- --exact --nocapture'):
        if marker not in workflow:
            raise ValueError("fresh exact retained-process workflow gate missing")
    if re.search(r"\s+test_retained_accessibility --", workflow):
        raise ValueError("workflow groups original Servo owners into one process")
    for marker in ('if set(value) != set(expected):', 'if type(value[key]) is not type(expected_value):'):
        if marker not in workflow:
            raise ValueError("CI result validation lacks closed scalar types")
    for call, comparison in [('require_scalar_types(product, expected_product, "product")', 'if product != expected_product:'),
                             ('require_scalar_types(servo, required_servo, "Servo")', 'if servo != required_servo:')]:
        if workflow.count(call) != 1 or workflow.index(call) > workflow.index(comparison):
            raise ValueError("CI result types must be checked before original equality")


def retained_inventory(path: Path) -> tuple[list[str], int]:
    text = read(path).decode("utf-8", "strict")
    names = []
    summaries = []
    for line in text.splitlines():
        if not line:
            continue
        match = re.fullmatch(r"(" + TEST_NAME + r"): test", line)
        if match:
            names.append(match[1])
            continue
        summary = re.fullmatch(r"(\d+) tests, 0 benchmarks", line)
        if summary:
            summaries.append(int(summary[1]))
            continue
        raise ValueError("unexpected actual test inventory line")
    if len(set(names)) != len(names) or summaries != [len(names)]:
        raise ValueError("actual test inventory count or identity differs")
    retained = [name for name in names if name.split("::")[-1].startswith("test_retained_accessibility")]
    leaves = [name.split("::")[-1] for name in retained]
    if len(leaves) != len(RETAINED_TESTS) or set(leaves) != set(RETAINED_TESTS):
        raise ValueError("actual retained test inventory is incomplete or duplicated")
    if sum(name.split("::")[-1] == SEMANTIC_TEST for name in names) != 1:
        raise ValueError("complete semantic test is absent or ambiguous")
    # Use the full names from the actual listing, including any module prefix.
    return [retained[leaves.index(leaf)] for leaf in RETAINED_TESTS], len(names)


def verify_retained_results(list_path: Path, directory: Path) -> None:
    names, total = retained_inventory(list_path)
    for index, name in enumerate(names):
        text = read(directory / f"case-{index}.log").decode("utf-8", "strict")
        starts = re.findall(r"(?m)^running (\d+) tests?$", text)
        outcomes = re.findall(r"(?m)^test (" + TEST_NAME + r") \.\.\. (ok|FAILED|ignored)$", text)
        summaries = re.findall(r"(?m)^test result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out; finished in [0-9.]+s$", text)
        if starts != ["1"] or outcomes != [(name, "ok")] or summaries != [("ok", "1", "0", "0", "0", str(total - 1))]:
            raise ValueError("retained subprocess did not run exactly its one listed original test")


def parse_patch(data: bytes) -> dict[str, list[str]]:
    text = data.decode("utf-8", "strict")
    chunks = text.split("diff --git ")
    if chunks[0] or len(chunks) != len(ALLOWED_PATHS) + 1:
        raise ValueError("semantic patch has unexpected section count")
    output: dict[str, list[str]] = {}
    for chunk in chunks[1:]:
        lines = chunk.splitlines(keepends=True)
        header = lines.pop(0).removesuffix("\n")
        match = re.fullmatch(r"a/(\S+) b/(\S+)", header)
        if match is None or match[1] != match[2]:
            raise ValueError("semantic patch redirects a source path")
        path = safe_relative(match[1]).as_posix()
        if path not in ALLOWED_PATHS or path in output:
            raise ValueError("semantic patch path is undeclared or repeated")
        new_file = path == "components/shared/base/accessibility_semantics.rs"
        if new_file:
            exact(lines.pop(0), "new file mode 100644\n", "semantic new-file mode")
        exact(lines.pop(0), "--- /dev/null\n" if new_file else f"--- a/{path}\n", "semantic old path")
        exact(lines.pop(0), f"+++ b/{path}\n", "semantic new path")
        if not lines or HUNK.fullmatch(lines[0]) is None:
            raise ValueError("semantic patch has no exact hunk")
        for record in lines:
            if record[:1] in {" ", "+", "-"} and record.endswith("\n"):
                body = record[1:-1]
                if body and body.rstrip(" \t") != body:
                    raise ValueError("semantic patch source body has trailing whitespace")
        output[path] = lines
    exact(list(output), ALLOWED_PATHS, "semantic patch order")
    return output


def apply_exact(before: bytes | None, lines: list[str]) -> bytes:
    source = [] if before is None else before.decode("utf-8", "strict").splitlines(keepends=True)
    output: list[str] = []
    cursor = 0
    index = 0
    while index < len(lines):
        header = HUNK.fullmatch(lines[index])
        if header is None:
            raise ValueError("unexpected semantic hunk syntax")
        old_start, old_count, new_start, new_count = [int(header[group] or "1") for group in range(1, 5)]
        position = old_start - 1 if old_count else old_start
        if position < cursor or position > len(source):
            raise ValueError("semantic hunk range escapes original file")
        output += source[cursor:position]
        if new_start != len(output) + (1 if new_count else 0):
            raise ValueError("semantic new hunk range differs")
        cursor = position
        index += 1
        consumed = produced = 0
        while index < len(lines) and HUNK.fullmatch(lines[index]) is None:
            line = lines[index]
            if not line or line[0] not in " +-" or not line.endswith("\n"):
                raise ValueError("unsupported semantic hunk record")
            kind, body = line[0], line[1:]
            if kind in " -":
                if cursor >= len(source) or source[cursor] != body:
                    raise ValueError("semantic patch does not exactly match post-S07 source")
                cursor += 1
                consumed += 1
            if kind in " +":
                output.append(body)
                produced += 1
            index += 1
        if (consumed, produced) != (old_count, new_count):
            raise ValueError("semantic hunk counts differ")
    output += source[cursor:]
    return "".join(output).encode("utf-8")


def apply_gnu_patch(stage: Path, data: bytes) -> None:
    """Require the same complete patch the CI applies, without fuzz or offset.

    An exact line transformer alone does not check GNU unified-hunk boundary
    interpretation. This temporary source tree grants no runtime authority.
    """
    result = subprocess.run(
        ["patch", "--batch", "--forward", "--fuzz=0", "-p1", "-d", str(stage)],
        input=data, capture_output=True, timeout=30, check=False,
    )
    diagnostic = (result.stdout + result.stderr).decode("utf-8", "strict")
    if result.returncode or re.search(r"\b(?:offset|fuzz)\b", diagnostic):
        raise ValueError("complete semantic patch did not apply with GNU zero fuzz/offset")


def verify(root: Path) -> tuple[dict[str, Any], dict[str, list[str]]]:
    manifest = load(root / MANIFEST)
    exact(set(manifest), {"schema", "status", "servo_commit", "prerequisite_manifest", "prerequisite_manifest_sha256", "patch", "semantic_schema", "original_stimulus", "required_negative_cases", "claim_ceiling", "standalone_source_check", "runtime_corpus", "final_semantic_refresh"}, "semantic manifest fields")
    exact(manifest["schema"], "trillionnium.lab.s08-semantic-custody.v1", "semantic schema")
    exact(manifest["status"], "SOURCE_CANDIDATE_EXACT_PIN_RUNTIME_REQUIRED", "semantic status")
    exact(manifest["servo_commit"], PIN, "semantic Servo pin")
    exact(manifest["prerequisite_manifest"], PREREQUISITE, "prerequisite manifest path")
    exact(hashlib.sha256(read(root / PREREQUISITE)).hexdigest(), manifest["prerequisite_manifest_sha256"], "original S07 manifest digest")
    verify_runtime_corpus(root, manifest["runtime_corpus"], load(root / PREREQUISITE))
    exact(manifest["semantic_schema"], SEMANTIC_SCHEMA, "bounded semantic profile")
    exact(manifest["final_semantic_refresh"], FINAL_SEMANTIC_REFRESH, "final current DOM semantic refresh profile")
    exact(manifest["original_stimulus"], ORIGINAL_STIMULUS, "original stimulus")
    exact(manifest["required_negative_cases"], list(NEGATIVES), "semantic negative corpus")
    exact(manifest["claim_ceiling"], CLAIMS, "semantic claim ceiling")
    standalone = fields(manifest["standalone_source_check"], {"manifest_path", "manifest_sha256", "lock_path", "lock_sha256", "fixture_only", "expected_tests"}, "standalone source profile fields")
    for key, leaf in (("manifest", "Cargo.toml"), ("lock", "Cargo.lock")):
        path = "experiments/servo-s08-runtime/semantic-source-check/" + leaf
        exact(standalone[key + "_path"], path, "standalone source path")
        exact(hashlib.sha256(read(root / path)).hexdigest(), standalone[key + "_sha256"], "standalone pinned source digest")
    exact(standalone["fixture_only"], True, "standalone evidence scope")
    exact(standalone["expected_tests"], 6, "standalone Rust corpus count")
    exact(tomllib.loads(read(root / standalone["manifest_path"]).decode()), {
        "package": {"name": "s08-semantic-standalone-source-check", "version": "0.0.0", "edition": "2024"},
        "lib": {"path": "semantic_source.rs"},
        "dependencies": {"accesskit": {"version": "=0.24.0", "features": ["serde"]},
                         "sha2": "=0.11.0", "serde": {"version": "=1.0.228", "features": ["derive"]},
                         "serde_json": "=1.0.151"},
    }, "standalone exact pinned dependency profile")
    section = fields(manifest["patch"], {"path", "sha256", "allowed_paths", "source_pins"}, "semantic patch fields")
    exact(section["path"], PATCH, "semantic patch path")
    exact(section["allowed_paths"], ALLOWED_PATHS, "semantic declared paths")
    data = read(root / PATCH, MAX_PATCH_BYTES)
    exact(hashlib.sha256(data).hexdigest(), section["sha256"], "semantic patch digest")
    parsed = parse_patch(data)
    rows = section["source_pins"]
    if not isinstance(rows, list) or len(rows) != len(ALLOWED_PATHS):
        raise ValueError("semantic source pin count differs")
    for path, row in zip(ALLOWED_PATHS, rows, strict=True):
        fields(row, {"path", "original_blob_sha1", "original_sha256", "post_s07_sha256", "semantic_sha256"}, "source pin fields")
        exact(row["path"], path, "source pin path")
        for key in ("original_blob_sha1", "original_sha256", "post_s07_sha256", "semantic_sha256"):
            value = row[key]
            if path.endswith("/accessibility_semantics.rs") and key != "semantic_sha256":
                exact(value, None, "new source absence")
            elif not isinstance(value, str) or (SHA1 if key == "original_blob_sha1" else SHA256).fullmatch(value) is None:
                raise ValueError("invalid pinned source digest")
    module = apply_exact(None, parsed["components/shared/base/accessibility_semantics.rs"])
    exact(hashlib.sha256(module).hexdigest(), rows[ALLOWED_PATHS.index("components/shared/base/accessibility_semantics.rs")]["semantic_sha256"], "semantic module source digest")
    for marker in (b"MAX_ACCESSIBILITY_NAME_BYTES: usize = 1024", b"MAX_ACCESSIBILITY_ANCESTRY: usize = 16", b"ACCESSIBILITY_SEMANTIC_VERSION: u16 = 1", b"#[serde(deny_unknown_fields)]", b"use sha2::{Digest, Sha256};", b"self.ids[..depth].contains(&id)"):
        if marker not in module:
            raise ValueError("semantic source boundary marker missing")
    script = "".join(parsed["components/script/event_loop/script_thread.rs"])
    for marker in ("if current != expected", "expected.is_well_formed()", "expected.tree_id() != request.target_tree", "expected.node_id() != request.target_node", "accessibility_semantic_expectation(", "ObserveAccessibilitySemantics"):
        if marker not in script:
            raise ValueError("final same-task semantic comparison missing")
    refresh_sources = {
        path: "".join(line[1:] for line in parsed[path] if line.startswith(("+", " ")))
        for path in ("components/script/event_loop/script_thread.rs", "components/layout/layout_impl.rs",
                     "components/layout/accessibility_tree.rs", "components/shared/layout/lib.rs")
    }
    verify_semantic_refresh(refresh_sources)
    additions = "\n".join(line[1:] for lines in parsed.values() for line in lines if line.startswith("+"))
    for pattern in (r"evaluate_javascript|EvaluateJavaScript|WebDriver", r"query_selector|element_from_point|hit_test", r"fire_synthetic_pointer_event_not_trusted"):
        if re.search(pattern, additions):
            raise ValueError("semantic production patch adds an action fallback or extra dispatch")
    return manifest, parsed



def verify_semantic_refresh(sources: dict[str, str]) -> None:
    script = sources["components/script/event_loop/script_thread.rs"]
    layout = sources["components/layout/layout_impl.rs"]
    tree = sources["components/layout/accessibility_tree.rs"]
    shared = sources["components/shared/layout/lib.rs"]
    prepare = "window.layout().prepare_accessibility_semantic_reflow();"
    if script.count(prepare) != 2 or (prepare + "\n        window.reflow(cx, ReflowGoal::UpdateTheRendering);") not in script:
        raise ValueError("semantic observation must prepare before final reflow")
    if "if expectation.is_some() {\n            " + prepare + "\n        }\n        window.reflow(cx, ReflowGoal::UpdateTheRendering);" not in script:
        raise ValueError("checked dispatch must prepare its own current DOM reflow")
    for marker in ("self.accessibility_semantics_ready.set(false);\n        self.refresh_accessibility_semantics.set(true);\n        self.set_force_accessibility_update();",
                   "!self.accessibility_semantics_ready.get() { return None; }",
                   "refresh_accessibility_semantics: Cell::new(false)", "accessibility_semantics_ready: Cell::new(false)",
                   "let refresh_semantics = self.refresh_accessibility_semantics.get();",
                   "            rooted_nodes,\n            refresh_semantics,\n        );",
                   "if refresh_semantics {\n            self.refresh_accessibility_semantics.set(false);\n            self.accessibility_semantics_ready.set(true);\n        }"):
        if marker not in layout:
            raise ValueError("semantic snapshot requires an actual completed checked layout update")
    if layout.index("let (tree_update, counters) = accessibility_tree.update_tree(") > layout.index("self.accessibility_semantics_ready.set(true);"):
        raise ValueError("semantic readiness precedes current DOM update")
    for marker in ("refresh_semantics: bool", "AccessibilityUpdate::new(damage_from_dom, rooted_nodes, self);\n        update.refresh_semantics = refresh_semantics;",
                   "let mut damage = if update.refresh_semantics {\n            AccessibilityDamage::Node\n        } else {\n            AccessibilityDamage::empty()\n        };",
                   "            refresh_semantics: false,\n            changed_nodes:"):
        if marker not in tree:
            raise ValueError("checked update must read current DOM properties independently of damage")
    if "fn prepare_accessibility_semantic_reflow(&self);" not in shared:
        raise ValueError("current DOM semantic reflow interface is absent")

def verify_upstream_sources(root: Path, upstream: Path, manifest: dict[str, Any], parsed: dict[str, list[str]]) -> None:
    prerequisite = load(root / PREREQUISITE)
    paths = sorted(set(prerequisite["patch"]["allowed_paths"]) | set(ALLOWED_PATHS))
    originals: dict[str, bytes | None] = {}
    for path in paths:
        originals[path] = None if path.endswith("/accessibility_semantics.rs") else read(upstream / path)
    for row in manifest["patch"]["source_pins"]:
        data = originals[row["path"]]
        if data is None:
            if (upstream / row["path"]).exists() or (upstream / row["path"]).is_symlink():
                raise ValueError("new semantic source already exists")
            continue
        exact(hashlib.sha256(data).hexdigest(), row["original_sha256"], "original exact-pin bytes")
        exact(hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest(), row["original_blob_sha1"], "original exact-pin Git blob")
    with tempfile.TemporaryDirectory(prefix="s08-semantic-pristine-") as temporary:
        stage = Path(temporary)
        for path, data in originals.items():
            if data is not None:
                destination = stage / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
        for section in (prerequisite["patch"], prerequisite["hardening"]):
            for entry in section["parts"]:
                data = read(root / safe_relative(entry["path"]), MAX_PATCH_BYTES)
                exact(hashlib.sha256(data).hexdigest(), entry["sha256"], "unchanged S07 part")
                # Original S07 part 006 has its already-qualified one-line context fuzz.
                # The new complete semantic patch must satisfy both applicators below.
                result = subprocess.run(["patch", "--batch", "--forward", "-p1", "-d", str(stage)], input=data, capture_output=True, timeout=30, check=False)
                if result.returncode:
                    raise ValueError("original S07 prerequisite did not apply")
        after_sources: dict[str, bytes] = {}
        for row in manifest["patch"]["source_pins"]:
            path = row["path"]
            before = None if originals[path] is None else read(stage / path)
            exact(None if before is None else hashlib.sha256(before).hexdigest(), row["post_s07_sha256"], "post-S07 source bytes")
            after = apply_exact(before, parsed[path])
            exact(hashlib.sha256(after).hexdigest(), row["semantic_sha256"], "semantic after-source bytes")
            after_sources[path] = after
        verify_semantic_refresh({path: after_sources[path].decode("utf-8", "strict") for path in (
            "components/script/event_loop/script_thread.rs", "components/layout/layout_impl.rs",
            "components/layout/accessibility_tree.rs", "components/shared/layout/lib.rs")})
        # The checked refresh passes current ServoLayoutNode values to the existing property reader.
        tree_source = after_sources["components/layout/accessibility_tree.rs"].decode("utf-8", "strict")
        for marker in ("self.set_role(role_from_dom_node(dom_node))", "click_action_supported(dom_node)",
                       "let text_content = dom_node.text_content();", "self.update_children_from_dom_node(",
                       "child.parent_node = Some(weak_self.clone());"):
            if marker not in tree_source:
                raise ValueError("checked semantic refresh lost its current DOM measurement source")
        before_lock = tomllib.loads(read(stage / "Cargo.lock").decode())
        after_lock = tomllib.loads(after_sources["Cargo.lock"].decode())
        exact(len(after_lock["package"]), len(before_lock["package"]), "upstream locked package count")
        for before, after in zip(before_lock["package"], after_lock["package"], strict=True):
            expected = dict(before)
            if before["name"] == "servo-base":
                expected["dependencies"] = sorted(before["dependencies"] + ["sha2 0.11.0"])
            exact(after, expected, "unchanged pinned package or minimal sha2 edge")
        pinned_registry = {(item["name"], item["version"], item.get("source"), item.get("checksum")) for item in before_lock["package"] if "source" in item}
        standalone_lock = tomllib.loads(read(root / manifest["standalone_source_check"]["lock_path"]).decode())
        for item in standalone_lock["package"]:
            if "source" in item and (item["name"], item["version"], item.get("source"), item.get("checksum")) not in pinned_registry:
                raise ValueError("standalone dependency drifted from exact pin registry bytes")
        apply_gnu_patch(stage, read(root / PATCH, MAX_PATCH_BYTES))
        for path, expected in after_sources.items():
            if read(stage / path) != expected:
                raise ValueError("GNU and exact semantic after-source bytes differ")
        # No write has been made to upstream: failures and success discard only this private copy.
    for path, original in originals.items():
        if original is not None and read(upstream / path) != original:
            raise ValueError("pristine upstream source changed during verification")


def verify_result(path: Path) -> None:
    actual = load_json_strict(read(path, MAX_RESULT_BYTES).decode("utf-8", "strict"))
    expected = {"schema": "trillionnium.desktop.s08-semantic-result.v1", "servo_commit": PIN, "case_count": len(NEGATIVES), "cases": [{"case": case, "refusal": refusal, "dom_click_count": 0} for case, refusal in NEGATIVES.items()], "final_same_script_task_check": True, "installed_image_proven": False, "final_peer_control_custody_proven": False}
    exact(actual, expected, "real semantic corpus result")


def source_check(root: Path, parsed: dict[str, list[str]]) -> None:
    toolchain = subprocess.check_output(["rustc", "--version"], text=True, timeout=15).strip()
    if toolchain != "rustc 1.93.0 (254b59607 2026-01-19)":
        raise ValueError("standalone semantic source check requires locked Rust 1.93.0")
    with tempfile.TemporaryDirectory(prefix="s08-semantic-rust-") as temporary:
        project = Path(temporary)
        for name in ("Cargo.toml", "Cargo.lock"):
            (project / name).write_bytes(read(root / "experiments/servo-s08-runtime/semantic-source-check" / name))
        (project / "semantic_source.rs").write_bytes(apply_exact(None, parsed["components/shared/base/accessibility_semantics.rs"]))
        subprocess.run(["cargo", "test", "--locked", "--manifest-path", str(project / "Cargo.toml")], stdout=sys.stderr, check=True, timeout=180)


def main(argv: list[str] | None = None) -> int:
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check-upstream", type=Path)
    parser.add_argument("--source-check", action="store_true")
    parser.add_argument("--result", type=Path)
    parser.add_argument("--retained-list", type=Path)
    parser.add_argument("--retained-log-dir", type=Path)
    parser.add_argument("--print-retained-names", action="store_true")
    args = parser.parse_args(argv)
    manifest, parsed = verify(args.root)
    if (args.retained_log_dir or args.print_retained_names) and not args.retained_list:
        raise ValueError("retained logs/names require the actual inventory")
    if args.print_retained_names and (args.check_upstream or args.source_check or args.result or args.retained_log_dir):
        raise ValueError("retained names mode only emits verified inventory names")
    if args.retained_list:
        names, _ = retained_inventory(args.retained_list)
        if args.print_retained_names:
            print("\n".join(names))
            return 0
    if args.retained_log_dir:
        verify_retained_results(args.retained_list, args.retained_log_dir)
    if args.check_upstream:
        pin = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=args.check_upstream, text=True, timeout=15).strip()
        if pin != PIN or subprocess.check_output(["git", "status", "--porcelain=v1"], cwd=args.check_upstream, text=True, timeout=15):
            raise ValueError("upstream checkout must be pristine exact pin")
        verify_upstream_sources(args.root, args.check_upstream, manifest, parsed)
    if args.source_check:
        source_check(args.root, parsed)
    if args.result:
        verify_result(args.result)
    print(json.dumps({"schema": "trillionnium.desktop.s08-semantic-source-verification.v1", "source_verified": True, "upstream_bytes_checked": bool(args.check_upstream), "standalone_source_checked": args.source_check, "semantic_result_shape_checked": bool(args.result), "retained_inventory_shape_checked": bool(args.retained_list), "retained_subprocess_shapes_checked": bool(args.retained_log_dir), "actual_servo_execution_proven": False, "patch_sha256": manifest["patch"]["sha256"], "servo_commit": PIN, "installed_product_proven": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, UnicodeError, TypeError, KeyError, IndexError, subprocess.SubprocessError) as error:
        print(f"S08 semantic verification refused: {type(error).__name__}", file=sys.stderr)
        raise SystemExit(1)
