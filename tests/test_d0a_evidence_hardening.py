from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


QUALIFIER = _load("qualify_servo_exact_pin", TOOLS / "qualify_servo_exact_pin.py")
EVIDENCE = _load(
    "qualify_servo_exact_pin_evidence",
    TOOLS / "qualify_servo_exact_pin_evidence.py",
)


class D0AEvidenceHardeningTests(unittest.TestCase):
    def test_qualifier_json_loader_rejects_duplicate_object_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"status":"PASS","status":"FORGED"}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
                QUALIFIER.load_json_file(path, "test manifest")

    def test_qualifier_required_inputs_reject_traversal_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "servo"
            root.mkdir()
            outside = Path(temporary) / "outside.txt"
            outside.write_text("outside\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "unsafe"):
                QUALIFIER.required_servo_inputs(root, {"required_inputs": ["../outside.txt"]})

            (root / "link.txt").symlink_to(outside)
            with self.assertRaisesRegex(RuntimeError, "symlink"):
                QUALIFIER.required_servo_inputs(root, {"required_inputs": ["link.txt"]})

    def test_evidence_hash_rejects_symlink_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.log"
            target.write_text("trusted\n", encoding="utf-8")
            alias = root / "alias.log"
            alias.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symlink"):
                EVIDENCE.sha256(alias)

    def test_d0a_json_consumers_use_strict_loader(self) -> None:
        workflow = (ROOT / ".github/workflows/servo-exact-pin.yml").read_text(
            encoding="utf-8"
        )
        headed = (TOOLS / "run_servo_headed_runtime_gate.sh").read_text(encoding="utf-8")
        self.assertIn("load_json_strict", workflow)
        self.assertIn("load_json_strict", headed)
        self.assertIn("_open_artifact", headed)
        for source in (workflow, headed):
            self.assertNotRegex(source, r"(?:lock|ledger|report|receipt|pre|terminated|recovered|selected_receipt|signal_receipt)\s*=\s*json\.loads\(")

    def test_headed_gate_guards_runtime_artifact_tree(self) -> None:
        headed = (TOOLS / "run_servo_headed_runtime_gate.sh").read_text(encoding="utf-8")
        self.assertIn('source "$script_dir/reject_symlink_path.sh"', headed)
        self.assertIn('reject_symlink_path "$PWD/artifacts/servo-headed-runtime/runtime"', headed)
        self.assertIn('examples_dir="$PWD/servo-source/ports/servoshell/examples"', headed)

    def test_headed_gate_creates_only_missing_servo_examples_leaf(self) -> None:
        headed = (TOOLS / "run_servo_headed_runtime_gate.sh").read_text(encoding="utf-8")
        # The pinned Servo tree may omit this optional directory.  The gate must
        # validate its tracked parent and create only the final leaf, retaining
        # the no-symlink boundary before installing ephemeral overlay files.
        self.assertIn('examples_parent=$(dirname -- "$examples_dir")', headed)
        self.assertIn('reject_symlink_path "$examples_parent"', headed)
        self.assertIn('mkdir -- "$examples_dir"', headed)
        self.assertIn('reject_symlink_path "$examples_dir"', headed)


if __name__ == "__main__":
    unittest.main()
