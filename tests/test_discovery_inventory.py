"""Prevent a green top-level unittest run from silently omitting subpackages."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"


def cases(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item


class DiscoveryInventoryTests(unittest.TestCase):
    def test_every_nested_test_directory_is_importable(self) -> None:
        for source in sorted(TESTS.rglob("test_*.py")):
            with self.subTest(source=str(source.relative_to(ROOT))):
                self.assertFalse(source.is_symlink())
                for parent in (source.parent, *source.parent.parents):
                    if parent == ROOT:
                        break
                    marker = parent / "__init__.py"
                    self.assertTrue(
                        marker.is_file(),
                        f"unittest silently skips {parent}: missing __init__.py",
                    )
                    self.assertFalse(marker.is_symlink())

    def test_top_level_discovery_contains_every_test_module_and_case(self) -> None:
        loader = unittest.TestLoader()
        suite = loader.discover(
            str(TESTS), pattern="test_*.py", top_level_dir=str(ROOT)
        )
        self.assertEqual(loader.errors, [])
        discovered = {case.id() for case in cases(suite)}
        for source in sorted(TESTS.rglob("test_*.py")):
            module_name = ".".join(
                source.relative_to(ROOT).with_suffix("").parts
            )
            with self.subTest(module=module_name):
                module = sys.modules.get(module_name)
                self.assertIsNotNone(module, f"not imported by discovery: {module_name}")
                self.assertEqual(Path(module.__file__).resolve(), source.resolve())
                expected = {
                    case.id()
                    for case in cases(loader.loadTestsFromModule(module))
                }
                self.assertTrue(expected, f"test file contributes no tests: {module_name}")
                self.assertTrue(
                    expected <= discovered,
                    f"omitted tests: {sorted(expected - discovered)}",
                )


if __name__ == "__main__":
    unittest.main()
