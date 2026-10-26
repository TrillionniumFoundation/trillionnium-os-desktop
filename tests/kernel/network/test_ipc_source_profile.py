#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Source-admission regressions only; synthetic dictionaries never prove a guest."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_unix_stream_guest as runner


class IpcSourceProfile(unittest.TestCase):
    def test_legacy_fingerprints_still_match_immutable_control_manifest(self):
        old = json.loads((HERE / "controls/manifest.json").read_text())["positive_source_sha256"]
        required = runner.required_sources("positive", "legacy")
        for name, sha in old.items():
            self.assertEqual(required[name], sha)

    def test_ipc_profile_matches_reviewed_actual_sources(self):
        root = HERE.parents[2]
        required = runner.required_sources("positive", "ipc-memory-v1")
        for name, sha in runner.IPC_SOURCE_SHA.items():
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), sha, name)
            self.assertEqual(required[name], sha)
        self.assertNotEqual(required[runner.CONNECTED], runner.CONNECTED_SHA["positive"])
        self.assertNotEqual(required[runner.SOCKET], runner.SOCKET_SHA)

    def test_historical_mutations_cannot_use_new_production_profile(self):
        for variant in ("race-fixed", "race-stale", "aux-zero-progress"):
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                runner.required_sources(variant, "ipc-memory-v1")
        with self.assertRaises(ValueError):
            runner.required_sources("positive", "invented")

    def test_missing_or_drifting_ipc_allocator_source_is_refused(self):
        required = runner.required_sources("positive", "ipc-memory-v1")
        synthetic = {"files": {name: {"sha256": sha} for name, sha in required.items()}}
        self.assertEqual(runner.check_sources(synthetic, "positive", "ipc-memory-v1"), required)
        for name in runner.IPC_SOURCE_SHA:
            with self.subTest(name=name):
                missing = {"files": {key: value for key, value in synthetic["files"].items() if key != name}}
                with self.assertRaises(ValueError):
                    runner.check_sources(missing, "positive", "ipc-memory-v1")
                drift = {"files": dict(synthetic["files"])}
                drift["files"][name] = {"sha256": "0" * 64}
                with self.assertRaises(ValueError):
                    runner.check_sources(drift, "positive", "ipc-memory-v1")


if __name__ == "__main__":
    unittest.main()
