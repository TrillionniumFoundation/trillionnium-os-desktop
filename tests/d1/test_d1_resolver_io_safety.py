from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(ROOT / "tools"))

import resolve_debian_snapshot  # noqa: E402
import resolve_debian_snapshot_with_pinned_keys  # noqa: E402


class D1ResolverIOSafetyTests(unittest.TestCase):
    def test_requirements_loaders_reject_duplicate_keys(self) -> None:
        payload = '{"archives": [], "archives": [{"id":"forged"}]}\n'
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "requirements.json"
            path.write_text(payload, encoding="utf-8")
            for module in (
                resolve_debian_snapshot,
                resolve_debian_snapshot_with_pinned_keys,
            ):
                with self.subTest(module=module.__name__):
                    with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
                        module._load_json_file(path, "requirements")

    def test_resolver_readers_reject_symlink_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.json"
            target.write_text("{}\n", encoding="utf-8")
            alias = root / "alias.json"
            alias.symlink_to(target)
            for module in (
                resolve_debian_snapshot,
                resolve_debian_snapshot_with_pinned_keys,
            ):
                with self.subTest(module=module.__name__):
                    with self.assertRaisesRegex(RuntimeError, "symlink"):
                        module._load_json_file(alias, "requirements")
                    with self.assertRaisesRegex(RuntimeError, "symlink"):
                        module.sha256(alias)

    def test_resolver_sources_use_strict_nofollow_io(self) -> None:
        for relative in (
            "tools/resolve_debian_snapshot.py",
            "tools/resolve_debian_snapshot_with_pinned_keys.py",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(source=relative):
                self.assertIn("load_json_strict", source)
                self.assertIn("O_NOFOLLOW", source)
                self.assertNotIn("json.loads(args.requirements.read_text", source)
                self.assertNotIn("json.loads(intermediate.read_text", source)

    def test_resolver_writers_reject_symlink_destinations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.txt"
            target.write_text("sentinel", encoding="utf-8")
            alias = root / "alias.txt"
            alias.symlink_to(target)
            for module in (
                resolve_debian_snapshot,
                resolve_debian_snapshot_with_pinned_keys,
            ):
                with self.subTest(module=module.__name__):
                    with self.assertRaisesRegex(RuntimeError, "symlink"):
                        module._write_text_file(alias, "replacement", "output")
            self.assertEqual(target.read_text(encoding="utf-8"), "sentinel")

    def test_base_resolver_rejects_symlinked_cli_input_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "requirements.json"
            target.write_text("{}\n", encoding="utf-8")
            alias = root / "requirements-alias.json"
            alias.symlink_to(target)
            original = sys.argv
            sys.argv = [
                "resolve_debian_snapshot.py",
                "--requirements",
                str(alias),
                "--output",
                str(root / "out.json"),
                "--work-dir",
                str(root / "work"),
                "--logs",
                str(root / "logs"),
            ]
            try:
                with self.assertRaises(RuntimeError):
                    resolve_debian_snapshot.main()
            finally:
                sys.argv = original


if __name__ == "__main__":
    unittest.main()
