"""Hostile and repository regressions for documentation semantic projections."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "documentation_integrity", ROOT / "tools/validate_documentation_integrity.py"
)
assert SPEC is not None and SPEC.loader is not None
DOCS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DOCS)

EXAMPLE = '''from pathlib import Path
import os
import stat

# Run only in an empty development directory, never over a live journal.
root = Path("journal-state")
root.mkdir(mode=0o700, exist_ok=False)
fd = os.open(root / "example.journal", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
os.close(fd)
assert stat.S_IMODE(root.stat().st_mode) == 0o700
assert stat.S_IMODE((root / "example.journal").stat().st_mode) == 0o600
'''


class ProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.registry = {
            "schema": "trillionnium.desktop.modules.v1",
            "plan_revision": DOCS.PLAN,
            "modules": [{"id": "example", "path": "crates/example",
                         "documentation": "crates/example/README.md",
                         "status": "source_candidate",
                         "claim_ceiling": "source only; no release authority"}],
        }
        self.write(DOCS.REGISTRY, json.dumps(self.registry))
        self.write(DOCS.INDEX, DOCS.render_index(self.registry))
        for path in DOCS.ANNEXES:
            self.write(path, f"# Inherited design\n\n{DOCS.ANNEX_STATUS}\n{DOCS.ACTIVE_LINK}\n")
        self.permission_doc = (DOCS.PERMISSION_LINE + "\n\n" + DOCS.EXAMPLE_START
                               + "\n```python\n" + EXAMPLE + "```\n" + DOCS.EXAMPLE_END)
        self.write("crates/hepta-session-core/README.md", self.permission_doc)
        self.write("docs/plan/D6_ANNEX_PRECEDENCE.md", "# Precedence\n")
        self.write("docs/modules/PRODUCT_SUBSYSTEM_COVERAGE.md", "# Scope\n")

    def write(self, path: str, text: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def test_consistent_fixture_passes(self) -> None:
        self.assertEqual(DOCS.validate(self.root), [])

    def test_output_is_deterministic(self) -> None:
        self.assertEqual(DOCS.render_index(self.registry), DOCS.render_index(copy.deepcopy(self.registry)))

    def test_changed_status_invalidates_index(self) -> None:
        self.registry["modules"][0]["status"] = "new_source_candidate"
        self.write(DOCS.REGISTRY, json.dumps(self.registry))
        self.assertTrue(any("index is stale" in error for error in DOCS.validate(self.root)))

    def test_changed_claim_invalidates_index(self) -> None:
        self.registry["modules"][0]["claim_ceiling"] = "narrower source only"
        self.write(DOCS.REGISTRY, json.dumps(self.registry))
        self.assertTrue(any("index is stale" in error for error in DOCS.validate(self.root)))

    def test_hand_edited_index_fails(self) -> None:
        self.write(DOCS.INDEX, DOCS.render_index(self.registry) + "all gaps closed\n")
        self.assertTrue(DOCS.validate(self.root))

    def test_duplicate_json_member_fails(self) -> None:
        self.write(DOCS.REGISTRY, '{"schema":"one","schema":"two"}')
        self.assertTrue(DOCS.validate(self.root))

    def test_non_json_numbers_fail(self) -> None:
        for value in ("NaN", "Infinity", "-Infinity", "1.25"):
            with self.subTest(value=value):
                text = json.dumps(self.registry)[:-1] + ', "untrusted":' + value + '}'
                self.write(DOCS.REGISTRY, text)
                self.assertTrue(DOCS.validate(self.root))

    def test_utf8_bom_fails(self) -> None:
        self.write(DOCS.REGISTRY, "\ufeff" + json.dumps(self.registry))
        self.assertTrue(DOCS.validate(self.root))

    def test_empty_inventory_fails(self) -> None:
        self.registry["modules"] = []
        self.write(DOCS.REGISTRY, json.dumps(self.registry))
        self.assertTrue(DOCS.validate(self.root))

    def test_duplicate_module_fails(self) -> None:
        self.registry["modules"].append(copy.deepcopy(self.registry["modules"][0]))
        self.write(DOCS.REGISTRY, json.dumps(self.registry))
        self.assertTrue(DOCS.validate(self.root))

    def test_markdown_injection_fails(self) -> None:
        for value in ("| forged row", "\n# hidden state", "<script>bad</script>", "`complete`"):
            with self.subTest(value=value):
                self.registry["modules"][0]["claim_ceiling"] = value
                self.write(DOCS.REGISTRY, json.dumps(self.registry))
                self.assertTrue(DOCS.validate(self.root))

    def test_traversal_documentation_fails(self) -> None:
        self.registry["modules"][0]["documentation"] = "../outside.md"
        self.write(DOCS.REGISTRY, json.dumps(self.registry))
        self.assertTrue(DOCS.validate(self.root))

    def test_symlinked_index_fails(self) -> None:
        original = self.root / DOCS.INDEX
        original.rename(original.with_suffix(".real"))
        original.symlink_to(original.with_suffix(".real").name)
        self.assertTrue(DOCS.validate(self.root))

    def test_symlinked_registry_parent_fails(self) -> None:
        (self.root / "manifests").rename(self.root / "real-manifests")
        (self.root / "manifests").symlink_to("real-manifests", target_is_directory=True)
        self.assertTrue(DOCS.validate(self.root))

    def test_oversized_registry_fails_before_parsing(self) -> None:
        self.write(DOCS.REGISTRY, " " * (DOCS.MAX_BYTES + 1))
        self.assertTrue(DOCS.validate(self.root))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO regression requires POSIX")
    def test_fifo_read_is_refused_without_a_writer(self) -> None:
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        with self.assertRaises(DOCS.InvalidDocumentation):
            DOCS.read_text(self.root, "fifo")

    def test_annex_cannot_claim_current_authority(self) -> None:
        for path in DOCS.ANNEXES:
            with self.subTest(path=path):
                self.write(path, "# d5\n**Status:** normative component of the active canonical plan\n")
                self.assertTrue(DOCS.validate(self.root))

    def test_annex_active_plan_link_is_required(self) -> None:
        self.write(DOCS.ANNEXES[0], DOCS.ANNEX_STATUS + "\n")
        self.assertTrue(DOCS.validate(self.root))

    def test_directory_file_mode_confusion_fails(self) -> None:
        self.write("crates/hepta-session-core/README.md", self.permission_doc
                   + "\nUse a private 0600 journal directory.\n")
        self.assertTrue(DOCS.validate(self.root))

    def test_duplicate_permission_contract_fails(self) -> None:
        self.write("crates/hepta-session-core/README.md", self.permission_doc + DOCS.PERMISSION_LINE)
        self.assertTrue(DOCS.validate(self.root))

    def test_missing_example_fails(self) -> None:
        self.write("crates/hepta-session-core/README.md", DOCS.PERMISSION_LINE)
        self.assertTrue(DOCS.validate(self.root))

    def test_permission_example_executes_on_host_filesystem(self) -> None:
        source = DOCS.permission_example(self.permission_doc)
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-I", "-c", source], cwd=directory,
                                    capture_output=True, text=True, timeout=5, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)


class RepositoryProjectionTests(unittest.TestCase):
    def test_committed_repository_documentation_is_consistent(self) -> None:
        self.assertEqual(DOCS.validate(ROOT), [])

    def test_documented_permission_example_executes(self) -> None:
        text = DOCS.read_text(ROOT, "crates/hepta-session-core/README.md")
        source = DOCS.permission_example(text)
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-I", "-c", source], cwd=directory,
                                    capture_output=True, text=True, timeout=5, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
