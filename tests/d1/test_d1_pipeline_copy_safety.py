from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "tests/qemu/run-d1-pipeline.sh"


class D1PipelineCopySafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = PIPELINE.read_text(encoding="utf-8")

    def test_copy_if_file_uses_descriptor_backed_helper(self) -> None:
        start = self.source.index("copy_if_file() {")
        end = self.source.index("\n}\n\ncopy_regular_tree", start)
        function = self.source[start:end]

        self.assertIn('safe_io="$workspace/tools/qemu_safe_io.py"', self.source)
        self.assertIn('python3 "$safe_io" copy', function)
        self.assertNotIn('cp -- "$source" "$destination"', function)

    def test_tail_truncation_uses_atomic_descriptor_helper(self) -> None:
        start = self.source.index("while IFS= read -r -d '' file; do")
        end = self.source.index("\n}\n\non_exit()", start)
        truncation = self.source[start:end]

        self.assertIn('python3 "$safe_io" tail', truncation)
        self.assertIn('--max-bytes 4194304', truncation)
        self.assertNotIn('tail -c 4194304 -- "$file" >', truncation)
        self.assertNotIn('mv -f -- "$temporary" "$file"', truncation)


if __name__ == "__main__":
    unittest.main()
