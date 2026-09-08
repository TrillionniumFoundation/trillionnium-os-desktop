from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "tests/qemu/run-d1-pipeline.sh"


def selection_parser() -> str:
    source = PIPELINE.read_text(encoding="utf-8")
    start_marker = "selection_status=$(D1_TOOLS_DIR=\"$workspace/tools\" python3 - \"$selection\" <<'PY'\n"
    end_marker = "\nPY\n) || {"
    start = source.index(start_marker) + len(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


class D1PipelineJsonSafetyTests(unittest.TestCase):
    def run_parser(self, path: Path) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["D1_TOOLS_DIR"] = str(ROOT / "tools")
        return subprocess.run(
            ["python3", "-", str(path)],
            input=selection_parser(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            check=False,
        )

    def test_selection_parser_rejects_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "selection.json"
            path.write_text('{"status":"PASS","status":"FORGED"}\n', encoding="utf-8")
            result = self.run_parser(path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate JSON object key", result.stderr)

    def test_selection_parser_rejects_symlink_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "selection-target.json"
            target.write_text('{"status":"PASS"}\n', encoding="utf-8")
            alias = root / "selection.json"
            alias.symlink_to(target)
            result = self.run_parser(alias)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("symlink", result.stderr)

    def test_pipeline_status_read_is_fail_closed_and_nofollow(self) -> None:
        source = PIPELINE.read_text(encoding="utf-8")
        self.assertIn("load_json_strict", source)
        self.assertIn("O_NOFOLLOW", source)
        self.assertIn("selection_status=$(D1_TOOLS_DIR=", source)
        self.assertIn("\n) || {", source)
        self.assertNotIn("json.load(open(sys.argv[1]))", source)


if __name__ == "__main__":
    unittest.main()
