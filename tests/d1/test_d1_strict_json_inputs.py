from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location(
    "prepare_d1_inputs",
    ROOT / "tools/prepare_d1_inputs.py",
)
assert SPEC is not None and SPEC.loader is not None
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)


class D1StrictJsonInputTests(unittest.TestCase):
    def test_prepare_loader_rejects_duplicate_json_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"status":"PASS","status":"FORGED"}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
                PREPARE._load_json_file(path, "test input")

    def test_prepare_reader_rejects_symlink_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.json"
            target.write_text("{}\n", encoding="utf-8")
            alias = root / "alias.json"
            alias.symlink_to(target)
            with self.assertRaisesRegex(RuntimeError, "symlink"):
                PREPARE._load_json_file(alias, "test input")
            with self.assertRaisesRegex(RuntimeError, "symlink"):
                PREPARE.sha256_file(alias)

    def test_d1_json_consumers_use_strict_nofollow_loaders(self) -> None:
        prepare = (ROOT / "tools/prepare_d1_inputs.py").read_text(encoding="utf-8")
        boot = (ROOT / "tests/qemu/run-d1-boot-test.sh").read_text(encoding="utf-8")
        for source in (prepare, boot):
            self.assertIn("load_json_strict", source)
            self.assertIn("O_NOFOLLOW", source)
        self.assertNotIn("json.loads(selection_path.read_text", prepare)
        self.assertNotIn("json.loads(baseline_path.read_text", prepare)
        self.assertNotIn("json.loads(d1_lock_path.read_text", prepare)
        self.assertNotIn("json.loads(requirements_path.read_text", prepare)
        self.assertNotIn("data = json.loads(path.read_text())", boot)
        self.assertIn("_has_symlink_component(path)", boot)


if __name__ == "__main__":
    unittest.main()
