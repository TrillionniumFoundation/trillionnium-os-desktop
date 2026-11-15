#!/usr/bin/env python3
"""Public, data-only controls for the three cold-observer source changes.

Fixtures are synthetic. Parser functions are AST-loaded: no entrypoint, socket,
QMP, manager, VM or Rust executable runs. The private native17+11 test receipt
is separate and is not reproduced or inferred by these public tests.
"""
import argparse
import ast
import configparser
import copy
import errno
import hashlib
import json
import re
import stat
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "cold-controller-base.py"
CANDIDATE = ROOT / "cold-controller-fragment.py"
DCS = bytes.fromhex("1b502b7136453631364436351b5c")


def load_functions(path):
    tree = ast.parse(path.read_text())
    names = {"need", "unique_json", "parse_component_serial", "validate_fixed_nsfs_records",
             "validate_original_server_metadata"}
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    namespace = {"json": json, "errno": errno, "stat": stat, "re": re, "REPORT": {}}
    exec(compile(ast.Module(body=functions, type_ignores=[]), path.name, "exec"), namespace)
    return namespace


def synthetic_nsfs():
    """Shape-valid data only; no namespace handle or runtime authority exists."""
    before = []
    denied = [{"command": c, "return": -1, "errno": errno.EACCES}
              for c in (0xb701, 0xb702, 0xb704, 0xb603)]
    for path, kind, ident, inode in (("/proc/self/ns/user", 0x10000000, 3, 101),
                                    ("/proc/self/ns/pid", 0x20000000, 4, 102)):
        before.append({"path": path, "actual_type": kind, "actual_id": ident,
                       "context": "u:object_r:droidloom_nsfs:s0\0",
                       "inode": [5, inode, stat.S_IFREG | 0o444, 0, 0, 1, 0, 10, 10],
                       "denied": copy.deepcopy(denied), "production_ready": False})
    after = copy.deepcopy(before)
    for row in after:
        row["inode"][7:] = [20, 20]
    return before + after


def socket_metadata():
    return {"node": [5, 23, stat.S_IFSOCK | 0o700, 0, 0, 1, 0, 100, 100],
            "expected_mode": 0o700, "peer_authenticated": False, "label_mutations": 0}


class ColdSourceControls(unittest.TestCase):
    def setUp(self):
        self.original = load_functions(BASE)
        self.candidate = load_functions(CANDIDATE)

    def test_public_manifest_matches_complete_flat_inputs(self):
        manifest = json.loads((ROOT / "cold-CANDIDATE.json").read_text())
        self.assertIs(manifest["source_fix_candidate_only"], True)
        self.assertIs(manifest["runtime_qualified"], False)
        self.assertIs(manifest["production_ready"], False)
        expected = {"cold-BASE.json", "cold-README.md", "cold-source.patch",
                    "cold-controller-base.py", "cold-controller-fragment.py", "cold-base-observe.service",
                    "p4-systemd-observe.service", "systemd_cold.rs", "test_cold_source_fixes.py"}
        self.assertEqual(set(manifest["public_files"]), expected)
        for name, pin in manifest["public_files"].items():
            with self.subTest(file=name):
                data = (ROOT / name).read_bytes()
                self.assertEqual(len(data), pin["bytes"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), pin["sha256"])

    def test_synthetic_dcs_stays_rejected_by_both_parsers(self):
        raw = DCS + b'P4_SYSTEMD_OBSERVER_STARTED {"synthetic":true}\n'
        for name, namespace in (("base", self.original), ("candidate", self.candidate)):
            with self.subTest(source=name), self.assertRaisesRegex(RuntimeError, "^known bounded original-systemd record$"):
                namespace["parse_component_serial"](raw.decode(), {}, {})
            self.assertNotIn("original_systemd_cold_observation_passed", namespace["REPORT"])

    def test_synthetic_nsfs_timestamp_change_and_stable_identity(self):
        rows = synthetic_nsfs()
        function = next(n for n in ast.parse(BASE.read_text()).body
                        if isinstance(n, ast.FunctionDef) and n.name == "parse_component_serial")
        gate = next(n for n in function.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                    and any(isinstance(a, ast.Constant) and a.value ==
                            "same held initial namespaces across original manager exec" for a in n.value.args))
        with self.assertRaisesRegex(RuntimeError, "same held initial namespaces"):
            exec(compile(ast.Module(body=[gate], type_ignores=[]), "original-nsfs-gate", "exec"),
                 {"need": self.original["need"], "nsfs_rows": rows})
        before = copy.deepcopy(rows)
        self.candidate["validate_fixed_nsfs_records"](rows)
        self.assertEqual(rows, before)
        self.assertEqual(self.candidate["REPORT"], {})

    def test_nsfs_rejects_every_changed_stable_inode_field(self):
        for index in range(7):
            with self.subTest(index=index):
                rows = synthetic_nsfs()
                rows[2]["inode"][index] += 1
                with self.assertRaises(RuntimeError):
                    self.candidate["validate_fixed_nsfs_records"](rows)

    def test_nsfs_rejects_changed_type_id_label_path_or_negative_control(self):
        changes = [("actual_type", 0x20000000), ("actual_id", 4), ("path", "/proc/1/ns/user"),
                   ("context", "u:object_r:other:s0"), ("production_ready", True)]
        for key, value in changes:
            with self.subTest(field=key):
                rows = synthetic_nsfs()
                rows[2][key] = value
                with self.assertRaises(RuntimeError):
                    self.candidate["validate_fixed_nsfs_records"](rows)
        rows = synthetic_nsfs()
        rows[2]["denied"][0]["errno"] = errno.EPERM
        with self.assertRaises(RuntimeError):
            self.candidate["validate_fixed_nsfs_records"](rows)

    def test_nsfs_retains_uint64_timestamps_and_complete_record_types(self):
        for value in (True, -1, 1 << 64, "100", 1.0):
            with self.subTest(value=value):
                rows = synthetic_nsfs()
                rows[2]["inode"][7] = value
                with self.assertRaises(RuntimeError):
                    self.candidate["validate_fixed_nsfs_records"](rows)
        original = synthetic_nsfs()
        for rows in (original[:3], original + [original[0]], {}, None):
            with self.subTest(rows=type(rows).__name__), self.assertRaises(RuntimeError):
                self.candidate["validate_fixed_nsfs_records"](rows)

    def test_server_metadata_accepts_only_exact_mode_and_owner(self):
        self.candidate["validate_original_server_metadata"](socket_metadata())
        for mode in (0, 0o500, 0o600, 0o710, 0o701, 0o770, 0o777, 0o4700, 0o2700, 0o1700, (1 << 32) | 0o700):
            with self.subTest(mode=oct(mode)):
                value = socket_metadata()
                value["node"][2] = stat.S_IFSOCK | mode
                with self.assertRaises(RuntimeError):
                    self.candidate["validate_original_server_metadata"](value)
        for index, item in ((3, 1000), (4, 1000), (5, 0), (5, 2)):
            with self.subTest(index=index, value=item):
                value = socket_metadata()
                value["node"][index] = item
                with self.assertRaises(RuntimeError):
                    self.candidate["validate_original_server_metadata"](value)

    def test_server_metadata_rejects_non_socket_and_untyped_nodes(self):
        for kind in (stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR, stat.S_IFBLK):
            value = socket_metadata()
            value["node"][2] = kind | 0o700
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                self.candidate["validate_original_server_metadata"](value)
        for item in (True, -1, 1 << 64, "100", 1.0):
            value = socket_metadata()
            value["node"][0] = item
            with self.subTest(item=item), self.assertRaises(RuntimeError):
                self.candidate["validate_original_server_metadata"](value)

    def test_server_metadata_cannot_claim_authentication_or_extra_fields(self):
        for key, item in (("peer_authenticated", True), ("peer_authenticated", 0),
                          ("label_mutations", False), ("label_mutations", 1),
                          ("expected_mode", 0o600), ("expected_mode", 448.0),
                          ("runtime_qualified", True)):
            value = socket_metadata()
            value[key] = item
            with self.subTest(key=key, item=item), self.assertRaises(RuntimeError):
                self.candidate["validate_original_server_metadata"](value)
        self.assertLess(len(json.dumps(socket_metadata())), 512)

    def test_metadata_record_alone_is_not_protocol_acceptance(self):
        line = "P4_SYSTEMD_SERVER_METADATA " + json.dumps(socket_metadata()) + "\n"
        with self.assertRaisesRegex(RuntimeError, "exactly one actual first-policy precondition"):
            self.candidate["parse_component_serial"](line, {}, {})
        for key in ("original_systemd_cold_observation_passed", "actual_original_systemd_execs_observed", "runtime_qualified"):
            self.assertNotIn(key, self.candidate["REPORT"])

    def test_new_metadata_keeps_strict_framing_json_and_size_rejection(self):
        body = json.dumps(socket_metadata())
        cases = [("P4_SYSTEMD_SERVER_METADATA " + body, "complete raw"),
                 ("P4_SYSTEMD_SERVER_METADATA " + body + "\r\n", "complete raw"),
                 ('P4_SYSTEMD_SERVER_METADATA {"node":[],"node":[]}\n', "duplicate"),
                 ("P4_SYSTEMD_SERVER_METADATA " + " " * 65537 + "{}\n", "bounded complete"),
                 (DCS.decode() + "P4_SYSTEMD_SERVER_METADATA " + body + "\n", "known bounded"),
                 ("P4_SYSTEMD_SERVER_METADATA_X " + body + "\n", "known bounded")]
        for value, reason in cases:
            with self.subTest(prefix=repr(value[:35])), self.assertRaisesRegex((RuntimeError, ValueError), reason):
                self.candidate["parse_component_serial"](value, {}, {})
        self.assertNotIn("original_systemd_cold_observation_passed", self.candidate["REPORT"])

    def test_raw_parser_loop_and_non_json_helpers_are_unchanged(self):
        a = {n.name: n for n in ast.parse(BASE.read_text()).body if isinstance(n, ast.FunctionDef)}
        b = {n.name: n for n in ast.parse(CANDIDATE.read_text()).body if isinstance(n, ast.FunctionDef)}
        self.assertEqual(set(b) - set(a), {"validate_fixed_nsfs_records", "validate_original_server_metadata"})
        for name in ("need",):
            self.assertEqual(ast.dump(a[name]), ast.dump(b[name]))
        for pick in (lambda f: f.body[0], lambda f: next(n for n in f.body if isinstance(n, ast.For))):
            self.assertEqual(ast.dump(pick(a["parse_component_serial"])), ast.dump(pick(b["parse_component_serial"])))

    def test_producer_unit_disables_terminal_inputs_preserving_lifetime(self):
        original, changed = [configparser.ConfigParser(interpolation=None, strict=True) for _ in range(2)]
        original.optionxform = changed.optionxform = str
        original.read_string((ROOT / "cold-base-observe.service").read_text())
        changed.read_string((ROOT / "p4-systemd-observe.service").read_text())
        self.assertEqual(original["Service"]["TTYPath"], "/dev/ttyS1")
        self.assertEqual(original["Service"]["TTYReset"], "no")
        for key in ("StandardInput", "StandardOutput", "StandardError"):
            self.assertEqual(changed["Service"][key], "null")
        self.assertFalse(any(key.startswith("TTY") for key in changed["Service"]))
        allowed = {"StandardOutput", "StandardError", "TTYPath", "TTYReset", "TTYVHangup", "TTYVTDisallocate"}
        for section in original.sections():
            self.assertEqual({k: v for k, v in original[section].items() if k not in allowed},
                             {k: v for k, v in changed[section].items() if k not in allowed})

    def test_guest_owns_com2_only_after_authentication_and_nnp(self):
        source = (ROOT / "systemd_cold.rs").read_text()
        body = source[source.index("pub(super) fn observe() -> R<()> {"):source.index("#[cfg(test)]")]
        self.assertLess(body.index("auth(false)?;"), body.index("component_channel()?;"))
        self.assertLess(body.index("actual original manager applied observer NNP1"), body.index("component_channel()?;"))
        self.assertLess(body.index("component_channel()?;"), body.index('"P4_SYSTEMD_OBSERVER_STARTED"'))

    def test_guest_emits_metadata_before_mode_refusal_and_peer_connection(self):
        source = (ROOT / "systemd_cold.rs").read_text()
        body = source[source.index("fn observe_inner() -> R<Value> {"):source.index("pub(super) fn observe() -> R<()> {")]
        positions = [body.index(s) for s in ("let server_node = node(&server)?;",
                     'emit("P4_SYSTEMD_SERVER_METADATA", server_metadata(&server_node));',
                     "validate_original_server_node(&server_node)?;", '"P4_SYSTEMD_SERVER_INODE"',
                     "let connection = connect(")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('"peer_authenticated":false', source)
        self.assertIn('"actual root0700 original server sock_file"', source)
        self.assertIn("server_node[2] == (libc::S_IFSOCK as u64 | 0o700)", source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ColdSourceControls))
    report = {"schema": "p4-r9-public-source-controls-v1", "passed": result.wasSuccessful(),
              "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "fixture_scope": "synthetic data only", "native_Rust_tests_run": False,
              "real_socket_tests_run": False, "original_R9_raw_tested": False,
              "VM_launches": 0, "live_QMP_calls": 0, "runtime_qualified": False, "production_ready": False}
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        with args.report.open("x") as stream:
            stream.write(encoded)
    print(encoded, end="")
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
