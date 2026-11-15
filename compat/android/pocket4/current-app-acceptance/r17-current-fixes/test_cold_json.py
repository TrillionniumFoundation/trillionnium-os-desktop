#!/usr/bin/env python3
"""Pure JSON helper controls; no controller entrypoint or target inputs."""

import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "cold-controller-fragment.py"
UNCHANGED_SOURCE_SHA256 = "8117c24cf573ea6be04b91b7fddb3776eb9f647506e9abf8d0fe7dd29ca0b113"


def load_json_helper():
    tree = ast.parse(SOURCE.read_text())
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in {"need", "unique_json"}]
    if {node.name for node in functions} != {"need", "unique_json"}:
        raise RuntimeError("exact JSON helper pair required")
    namespace = {"json": json, "__builtins__": {
        "float": float, "ValueError": ValueError, "RuntimeError": RuntimeError}}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace["unique_json"]


class FiniteJsonControls(unittest.TestCase):
    def setUp(self):
        self.decode = load_json_helper()

    def test_ordinary_scalars_and_nested_values(self):
        for raw in ["0", "-7", "1.25", "true", "false", "null",
                    '{"values":[1,2.5,false,null,{"value":-3.75}]}']:
            with self.subTest(raw=raw):
                actual = self.decode(raw)
                expected = json.loads(raw)
                self.assertEqual(actual, expected)
                self.assertIs(type(actual), type(expected))

    def test_finite_float_boundaries_and_signed_zero(self):
        for raw in ["1.7976931348623157e308", "-1.7976931348623157e308",
                    "5e-324", "-5e-324", "0.0", "-0.0"]:
            with self.subTest(raw=raw):
                value = self.decode(raw)
                self.assertIs(type(value), float)
                self.assertTrue(math.isfinite(value))
                self.assertEqual(value, json.loads(raw))
                self.assertEqual(math.copysign(1.0, value), math.copysign(1.0, json.loads(raw)))

    def test_finite_underflow_preserves_default_float_semantics(self):
        for raw in ["1e-10000", "-1e-10000"]:
            with self.subTest(raw=raw):
                value = self.decode(raw)
                self.assertIs(type(value), float)
                self.assertEqual(value, 0.0)
                self.assertEqual(math.copysign(1.0, value), math.copysign(1.0, json.loads(raw)))

    def test_large_integers_remain_exact_integers(self):
        for raw in ["9007199254740993", "-9007199254740993", "123456789012345678901234567890"]:
            with self.subTest(raw=raw):
                value = self.decode(raw)
                self.assertIs(type(value), int)
                self.assertEqual(value, int(raw))

    def test_float_overflow_is_rejected_at_every_nesting_level(self):
        for token in ["1e400", "-1e400", "1.7976931348623159e308", "-1.7976931348623159e308"]:
            for raw in [token, "[" + token + "]", '{"value":[' + token + "]}"]:
                with self.subTest(raw=raw):
                    with self.assertRaisesRegex(ValueError, "nonfinite JSON"):
                        self.decode(raw)

    def test_existing_nonfinite_constants_stay_rejected(self):
        for token in ["NaN", "Infinity", "-Infinity"]:
            with self.subTest(token=token):
                with self.assertRaisesRegex(ValueError, "nonfinite JSON"):
                    self.decode('{"value":' + token + "}")

    def test_duplicate_fields_stay_rejected(self):
        for raw in ['{"value":1,"value":2}', '[{"value":1.0,"value":2.0}]',
                    '{"outer":{"value":null,"value":false}}']:
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(RuntimeError, "duplicate JSON field"):
                    self.decode(raw)

    def test_numeric_looking_strings_and_normal_json_errors(self):
        value = ["NaN", "Infinity", "1e400", "-1e400", "ordinary text"]
        self.assertEqual(self.decode(json.dumps(value)), value)
        for raw in ["[1,]", '{"value":}', "01", ""]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    self.decode(raw)

    def test_source_scope_and_followup_manifest(self):
        source = SOURCE.read_text()
        node = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.FunctionDef) and node.name == "unique_json")
        helper = "\n".join(source.splitlines()[node.lineno - 1:node.end_lineno]) + "\n"
        remaining = source.replace(helper, "", 1).encode()
        self.assertEqual(hashlib.sha256(remaining).hexdigest(), UNCHANGED_SOURCE_SHA256)
        manifest = json.loads((ROOT / "cold-CANDIDATE.json").read_text())
        followup = manifest["finite_json_followup"]
        self.assertEqual(followup["changed_controller_functions"], ["unique_json"])
        self.assertIs(followup["runtime_qualification_inherited"], False)
        self.assertEqual(followup["expected_public_json_tests"], 9)
        for name, pin in {**manifest["public_files"], **followup["public_files"]}.items():
            with self.subTest(file=name):
                data = (ROOT / name).read_bytes()
                self.assertEqual(len(data), pin["bytes"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), pin["sha256"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(FiniteJsonControls))
    report = {"schema": "p4-finite-json-public-controls-v1", "passed": result.wasSuccessful(),
              "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "only_controller_helpers_executed": ["need", "unique_json"],
              "input_scope": "short synthetic JSON only", "original_UART_read": False,
              "full_controller_or_cold_parser_executed": False,
              "VM_launches": 0, "runtime_qualified": False, "production_ready": False}
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        with args.report.open("x") as stream:
            stream.write(encoded)
    print(encoded, end="")
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
