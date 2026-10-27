#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Source-admission regressions only; synthetic dictionaries never prove a guest."""
import base64
import gzip
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

    def test_ipc_profile_accepts_bound_real_historical_source_bytes(self):
        # Exported from the original M5 Git blobs, not synthesized from the
        # profile dictionary. Portable CI needs no access to old branch refs.
        encoded = (HERE / "controls/ipc-memory-v1-source.json.gz").read_bytes()
        self.assertEqual(hashlib.sha256(encoded).hexdigest(),
                         "0745d146a7d0bb6c89c0d290bdc368eb296005e252bc27000fce833466f1a5a7")
        fixture = json.loads(gzip.decompress(encoded))
        self.assertEqual(fixture["schema"], "asterinas.ipc-memory-v1-historical-source.v1")
        self.assertEqual(fixture["source_head"], "fd66b01eae13c3e24d15f48e7ba15b5180ae310d")
        self.assertEqual(fixture["source_tree"], "1af95deec4d6b07475c56e21a0c71b6f87e94c9f")
        required = runner.required_sources("positive", "ipc-memory-v1")
        self.assertEqual(len(fixture["files"]), len(required))
        self.assertEqual({row["path"] for row in fixture["files"]}, set(required))
        historical = {"files": {}}
        for row in fixture["files"]:
            data = base64.b64decode(row["content_base64"], validate=True)
            self.assertIn(row["mode"], ("100644", "100755"))
            git_blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            self.assertEqual(git_blob, row["git_blob"], row["path"])
            sha = hashlib.sha256(data).hexdigest()
            self.assertEqual(sha, row["sha256"], row["path"])
            self.assertEqual(sha, required[row["path"]], row["path"])
            historical["files"][row["path"]] = {"sha256": sha}
        self.assertEqual(runner.check_sources(historical, "positive", "ipc-memory-v1"), required)
        self.assertNotEqual(required[runner.CONNECTED], runner.CONNECTED_SHA["positive"])
        self.assertNotEqual(required[runner.SOCKET], runner.SOCKET_SHA)

    def test_current_source_is_rejected_by_historical_profiles_and_accepted_by_post_profile(self):
        import run_unix_stream_receiving_guest as receiving
        import run_unix_stream_signal_guest as signal
        import run_unix_stream_oom_guest as post
        root = HERE.parents[2]
        current = {"files": {path: {"sha256": hashlib.sha256((root / path).read_bytes()).hexdigest()}
                             for _, path, _ in post.OWNERS}}
        first_changed_owner = (
            r"^reviewed variant input mismatch: "
            r"kernel/asterinas/kernel/core/src/net/socket/unix/stream/connected[.]rs$"
        )
        with self.assertRaisesRegex(ValueError, first_changed_owner):
            runner.check_sources(current, "positive", "ipc-memory-v1")
        # This profile checks its production cgroup owner before IPC owners.
        with self.assertRaisesRegex(
            ValueError,
            r"^reviewed variant input mismatch: "
            r"kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/mod[.]rs$",
        ):
            receiving.check_sources(current, "positive", receiving.PROFILE)
        # The frozen e7ed signal profile must refuse current OOM clone bytes.
        # Its authentic historical positive remains a separate fixture test.
        with self.assertRaisesRegex(
            ValueError,
            r"^reviewed variant input mismatch: "
            r"kernel/asterinas/kernel/core/src/process/clone[.]rs$",
        ):
            signal.check_sources(current, "positive", signal.PROFILE)
        expected = post.required_sources("positive", post.PROFILE)
        self.assertEqual(post.check_sources(current, "positive", post.PROFILE), expected)

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
