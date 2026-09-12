"""Targeted projection/operations regressions, not product-qualification evidence."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("documentation_coherence", ROOT / "tools/validate_documentation_coherence.py")
assert SPEC is not None and SPEC.loader is not None
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class CoherenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.modules = [
            {"id": "sample-a", "package": "sample-a", "path": "crates/sample-a",
             "documentation": "crates/sample-a/README.md", "status": "source_candidate",
             "claim_ceiling": "source only; no runtime or release authority"},
            {"id": "sample-b", "package": "sample-b", "path": "apps/sample-b",
             "documentation": "apps/sample-b/README.md", "status": "fixture_only",
             "claim_ceiling": "fixture only; no production activation"},
        ]
        self.registry = {"schema": "trillionnium.desktop.modules.v1", "plan_revision": "2026-08-29-d6",
                         "policy": {}, "modules": self.modules}
        self.write(GATE.REGISTRY, json.dumps(self.registry))
        self.write("docs/MANIFEST.json", json.dumps({"active_plan_revision": "2026-08-29-d6"}))
        self.write("Cargo.toml", '[workspace]\nmembers = ["crates/sample-a", "apps/sample-b"]\n')
        for name in GATE.ANNEXES:
            self.write(f"docs/plan/{name}", "**Plan revision:** `2026-08-29-d6`\n\n## Plan inheritance and precedence\nThe active d6 executive lock wins.\n")
        self.write("crates/hepta-session-core/README.md", GATE.PERMISSIONS + "\n")
        self.regenerate()

    def write(self, path: str, text: str) -> None:
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")

    def save_registry(self) -> None:
        self.write(GATE.REGISTRY, json.dumps(self.registry))

    def regenerate(self) -> None:
        self.write(GATE.INDEX, GATE.render_index(self.root))

    def rejected(self, message: str) -> None:
        errors = GATE.validate(self.root)
        self.assertTrue(errors, message)
        self.assertTrue(any(message in error for error in errors), errors)

    def test_valid_fixture(self) -> None:
        self.assertEqual([], GATE.validate(self.root))

    def test_index_is_deterministic_and_does_not_promote(self) -> None:
        first = GATE.render_index(self.root)
        self.assertEqual(first, GATE.render_index(self.root))
        self.assertIn("Cargo workspace only", first)
        self.assertIn("fixture_only", first)
        self.assertIn("no production activation", first)
        self.assertNotIn("all_gaps_closed=true", first)

    def test_stale_status_is_rejected(self) -> None:
        self.modules[0]["status"] = "new_source_candidate"
        self.save_registry()
        self.rejected("index is stale")

    def test_stale_claim_is_rejected(self) -> None:
        self.modules[0]["claim_ceiling"] = "narrower source claim only"
        self.save_registry()
        self.rejected("index is stale")

    def test_added_prose_is_not_silently_accepted(self) -> None:
        self.write(GATE.INDEX, GATE.render_index(self.root) + "Production ready.\n")
        self.rejected("index is stale")

    def test_missing_index_fails(self) -> None:
        (self.root / GATE.INDEX).unlink()
        self.assertTrue(GATE.validate(self.root))

    def test_duplicate_json_key(self) -> None:
        self.write(GATE.REGISTRY, '{"schema":"x","schema":"y"}')
        self.rejected("duplicate JSON member")

    def test_nested_duplicate_json_key(self) -> None:
        self.write(GATE.REGISTRY, '{"policy":{"a":1,"a":2}}')
        self.rejected("duplicate JSON member")

    def test_non_json_numbers(self) -> None:
        for number in ("NaN", "Infinity", "-Infinity", "1.25"):
            with self.subTest(number=number):
                self.write(GATE.REGISTRY, '{"policy":' + number + '}')
                self.rejected("non-integer JSON number")

    def test_root_must_be_an_object(self) -> None:
        self.write(GATE.REGISTRY, "[]")
        self.rejected("expected JSON object")

    def test_utf8_bom_fails(self) -> None:
        self.write(GATE.REGISTRY, "\ufeff" + json.dumps(self.registry))
        self.assertTrue(GATE.validate(self.root))

    def test_deep_json_fails_without_uncaught_recursion(self) -> None:
        self.write(GATE.REGISTRY, '{"nested":' + '[' * 2000 + '0' + ']' * 2000 + '}')
        self.assertTrue(GATE.validate(self.root))

    def test_oversized_registry_fails(self) -> None:
        self.write(GATE.REGISTRY, " " * (GATE.MAX_BYTES + 1))
        self.rejected("bounded regular file")

    def test_inventory_cannot_be_empty(self) -> None:
        self.registry["modules"] = []
        self.save_registry()
        self.rejected("inventory size")

    def test_inventory_cardinality_is_bounded(self) -> None:
        self.registry["modules"] = [copy.deepcopy(self.modules[0])] * 257
        self.save_registry()
        self.rejected("inventory size")

    def test_duplicate_module_is_rejected(self) -> None:
        self.registry["modules"].append(copy.deepcopy(self.modules[0]))
        self.save_registry()
        self.rejected("duplicate module id")

    def test_workspace_order_must_match(self) -> None:
        self.modules.reverse()
        self.save_registry()
        self.rejected("Cargo workspace order")

    def test_unregistered_workspace_member_fails(self) -> None:
        self.write("Cargo.toml", '[workspace]\nmembers = ["crates/sample-a", "apps/sample-b", "crates/missing"]\n')
        self.rejected("Cargo workspace order")

    def test_documentation_path_cannot_escape(self) -> None:
        self.modules[0]["documentation"] = "../outside.md"
        self.save_registry()
        self.rejected("identity mismatch")

    def test_package_identity_must_match(self) -> None:
        self.modules[0]["package"] = "other-package"
        self.save_registry()
        self.rejected("identity mismatch")

    def test_markdown_and_control_injection_rejected(self) -> None:
        for character in ("|", "`", "<", ">", "\\", "\n", "\r", "\t", "\x7f"):
            with self.subTest(character=character):
                self.modules[0]["claim_ceiling"] = "source" + character + "only"
                self.save_registry()
                self.rejected("unsafe Markdown/control")

    def test_active_plan_drift_fails(self) -> None:
        self.registry["plan_revision"] = "2026-08-28-d5"
        self.save_registry()
        self.rejected("active plan")

    def test_annex_revision_drift_fails(self) -> None:
        self.write("docs/plan/PRODUCT_ARCHITECTURE.md", "**Plan revision:** `2026-08-28-d5`\n## Plan inheritance and precedence\n")
        self.rejected("active plan revision")

    def test_historical_authority_cannot_return(self) -> None:
        path = "docs/plan/CONTRACT_SECURITY_TESTING.md"
        self.write(path, GATE.read_text(self.root, path) + "normative component of the active canonical plan\n")
        self.rejected("ambiguous historical")

    def test_hidden_precedence_does_not_count(self) -> None:
        self.write("docs/plan/PRODUCT_ARCHITECTURE.md", "**Plan revision:** `2026-08-29-d6`\n<!-- ## Plan inheritance and precedence -->\n")
        self.rejected("precedence is missing")

    def test_directory_permission_regression(self) -> None:
        self.write("crates/hepta-session-core/README.md", "Use a private 0600 journal directory and one writer.\n")
        self.rejected("directory 0700")

    def test_permission_contradiction_is_rejected(self) -> None:
        self.write("crates/hepta-session-core/README.md", GATE.PERMISSIONS + "\nUse a 0600 directory.\n")
        self.rejected("incorrectly assigns 0600")

    def test_hidden_permission_rule_does_not_count(self) -> None:
        self.write("crates/hepta-session-core/README.md", "<!-- " + GATE.PERMISSIONS + " -->\n")
        self.rejected("directory 0700")

    def test_file_symlink_is_rejected(self) -> None:
        target = self.root / GATE.INDEX
        target.unlink()
        target.symlink_to(self.root / "docs/MANIFEST.json")
        self.assertTrue(GATE.validate(self.root))

    def test_directory_symlink_is_rejected(self) -> None:
        source = self.root / "docs/modules"
        moved = self.root / "moved-modules"
        source.rename(moved)
        source.symlink_to(moved, target_is_directory=True)
        self.assertTrue(GATE.validate(self.root))

    def test_fifo_is_rejected_without_waiting(self) -> None:
        target = self.root / GATE.INDEX
        target.unlink()
        os.mkfifo(target)
        self.rejected("bounded regular file")

    def test_path_traversal_is_rejected(self) -> None:
        for path in ("../x", "docs/../x", "/etc/passwd", "docs//x", "docs\\x"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                GATE.read_text(self.root, path)

    def test_checker_is_read_only(self) -> None:
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual([], GATE.validate(self.root))
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_render_cli_and_failure_exit(self) -> None:
        tool = self.root / "tools/validate_documentation_coherence.py"
        tool.parent.mkdir()
        shutil.copyfile(ROOT / "tools/validate_documentation_coherence.py", tool)
        result = subprocess.run([sys.executable, "-I", str(tool), "--render-index"], capture_output=True, text=True, timeout=5)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(GATE.render_index(self.root), result.stdout)
        self.write(GATE.INDEX, "stale\n")
        result = subprocess.run([sys.executable, "-I", str(tool)], capture_output=True, text=True, timeout=5)
        self.assertEqual(1, result.returncode)
        self.assertIn("index is stale", result.stderr)

    def test_documented_permission_bits_are_usable(self) -> None:
        directory = self.root / "private-store"
        directory.mkdir(mode=0o700)
        file = directory / "journal"
        fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        self.assertEqual(0o700, stat.S_IMODE(directory.stat().st_mode))
        self.assertEqual(0o600, stat.S_IMODE(file.stat().st_mode))


class RepositoryCoherenceTests(unittest.TestCase):
    def test_committed_projection_and_runbooks(self) -> None:
        self.assertEqual([], GATE.validate(ROOT))


if __name__ == "__main__":
    unittest.main()
