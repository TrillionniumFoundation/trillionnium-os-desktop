"""Keep the independent edge fixtures checked by the normal ABI test suite."""

import json
from pathlib import Path
import subprocess
import sys
import unittest

from test_golden_contract import read_frame


GOLDEN = Path(__file__).resolve().parents[1] / "golden"


class SemanticEdgeContract(unittest.TestCase):
    def test_independent_generator_matches_committed_edge_bytes(self):
        result = subprocess.run(
            [sys.executable, str(GOLDEN / "generate_hos2_edges.py"), "--check"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_independent_payload_oracle_accepts_all_edge_vectors(self):
        vectors = json.loads((GOLDEN / "hos2_edges.json").read_text())["vectors"]
        self.assertEqual(len(vectors), 24)
        for vector in vectors:
            with self.subTest(name=vector["name"]):
                frame = bytes.fromhex(vector["hex"])
                self.assertEqual(len(frame), vector["bytes"])
                self.assertEqual(read_frame(frame, vector["kind"])[0], vector["opcode"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
