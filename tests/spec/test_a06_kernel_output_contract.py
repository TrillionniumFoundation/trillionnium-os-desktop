"""Guard the A06 workflow's path to the generated OSDK kernel ELF."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/a06-kernel.yml"


class A06KernelOutputContract(unittest.TestCase):
    def test_workflow_uses_generated_osdk_binary_name(self):
        source = WORKFLOW.read_text()
        expected = "x86_64-unknown-none/release/asterinas-osdk-bin"
        self.assertEqual(
            source.count(expected),
            2,
            "the hash check and probe must consume the generated OSDK ELF",
        )
        self.assertNotIn("release/asterinas\\\"", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
