"""Guard the A06 workflow's path to the generated OSDK kernel ELF."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/a06-kernel.yml"


class A06KernelOutputContract(unittest.TestCase):
    def test_workflow_uses_generated_osdk_binary_name(self):
        source = WORKFLOW.read_text()
        expected = "osdk/asterinas/asterinas-osdk-bin.elf"
        self.assertEqual(
            source.count(expected),
            2,
            "the hash check and probe must consume the generated OSDK ELF",
        )
        self.assertNotIn("x86_64-unknown-none/release/asterinas-osdk-bin", source)
        self.assertIn("Machine:[[:space:]]+Intel 80386", source)

    def test_probe_scripts_keep_local_import_path(self):
        source = WORKFLOW.read_text()
        self.assertIn(
            "python3 tests/organ_backend/run_candidate_matrix.py",
            source,
        )
        self.assertIn(
            "python3 tests/organ_backend/smp2/run_parallel_candidate.py",
            source,
        )
        self.assertNotIn(
            "python3 -I tests/organ_backend/run_candidate_matrix.py",
            source,
        )
        self.assertNotIn(
            "python3 -I tests/organ_backend/smp2/run_parallel_candidate.py",
            source,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
