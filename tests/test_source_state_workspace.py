from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "structured_status_repository.py"
SPEC = importlib.util.spec_from_file_location("structured_status_repository_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SourceStateWorkspaceTests(unittest.TestCase):
    def make_root(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        paths = [
            "README.md",
            "Cargo.toml",
            "manifests/project-state.v1.json",
            "docs/status-documents.v1.json",
            "docs/source-state.v1.json",
            "docs/CURRENT_STATE.md",
            "docs/CANDIDATE_STATUS.md",
            "docs/NON_CLAIMS.md",
            "docs/plan/PR73_DECOMPOSITION.md",
        ]
        for relative in paths:
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        return root

    @staticmethod
    def write_workspace(root: Path, members: list[str]) -> None:
        quoted = ",\n".join(f'    "{member}"' for member in members)
        (root / "Cargo.toml").write_text(
            f"[workspace]\nmembers = [\n{quoted}\n]\nresolver = \"3\"\n",
            encoding="utf-8",
        )

    @staticmethod
    def source_state(root: Path) -> dict[str, object]:
        return json.loads((root / "docs/source-state.v1.json").read_text())

    @staticmethod
    def write_source_state(root: Path, record: dict[str, object]) -> None:
        (root / "docs/source-state.v1.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )

    def test_candidate_module_can_exist_in_source_without_integrated_promotion(self) -> None:
        root = self.make_root()
        record = self.source_state(root)
        members = record["workspace_members"]
        members.append("crates/hepta-browser-actor")
        self.write_source_state(root, record)
        self.write_workspace(root, members)

        self.assertEqual(MODULE.validate_repository(root), [])
        registry = json.loads((root / "docs/status-documents.v1.json").read_text())
        self.assertNotIn(
            "crates/hepta-browser-actor",
            registry["integrated_state"]["workspace_members"],
        )

    def test_unregistered_cargo_member_fails_closed(self) -> None:
        root = self.make_root()
        record = self.source_state(root)
        cargo_members = list(record["workspace_members"])
        cargo_members.append("crates/unregistered-candidate")
        self.write_workspace(root, cargo_members)
        self.assertIn(
            "source_state workspace_members differ from Cargo.toml",
            MODULE.validate_repository(root),
        )

    def test_source_record_without_cargo_member_fails_closed(self) -> None:
        root = self.make_root()
        record = self.source_state(root)
        source_members = record["workspace_members"]
        source_members.append("crates/unmaterialized-candidate")
        self.write_source_state(root, record)
        self.write_workspace(root, source_members[:-1])
        self.assertIn(
            "source_state workspace_members differ from Cargo.toml",
            MODULE.validate_repository(root),
        )

    def test_source_state_cannot_drop_integrated_member(self) -> None:
        root = self.make_root()
        record = self.source_state(root)
        del record["workspace_members"][0]
        self.write_source_state(root, record)
        self.write_workspace(root, record["workspace_members"])
        self.assertTrue(
            any("every integrated member" in error for error in MODULE.validate_repository(root))
        )

    def test_source_state_claim_ceiling_is_closed(self) -> None:
        root = self.make_root()
        record = self.source_state(root)
        record["claim_ceiling"] = "integrated_runtime"
        self.write_source_state(root, record)
        self.assertTrue(
            any("repository_source_tree_only" in error for error in MODULE.validate_repository(root))
        )


if __name__ == "__main__":
    unittest.main()
