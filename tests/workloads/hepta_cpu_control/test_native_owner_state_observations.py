"""Real private ext2/debugfs tests with inert payloads, never guest evidence."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import native_owner_state_observations as observed
from native_owner_continuity_test_records import ContinuityRecords
from native_owner_root_observation import ROOT_OBSERVATION_DIRECTORY, launch_observation_filename


class RootObservationDiskTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="inert-root-observation-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.debugfs = Path(shutil.which("debugfs") or "/missing-debugfs").resolve()
        self.mkfs = shutil.which("mkfs.ext2")
        self.assertTrue(self.debugfs.is_file(), "real read-only ext2 tool is required")
        self.assertIsNotNone(self.mkfs, "real ext2 formatter is required")
        self.identity = {"path": str(self.debugfs), "sha256": observed.sha(self.debugfs), "bytes": self.debugfs.stat().st_size}
        self.image = self.root / "inert-state.raw"
        with self.image.open("xb") as stream:
            stream.truncate(8 * 1024**2)
        subprocess.run([self.mkfs, "-F", "-q", "-b", "4096", "-I", "256", "-m", "0", "-O", "none,filetype", str(self.image)],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.expected = list(ContinuityRecords("history-only-after-both-owner-exit-v1").saved.values())
        self.guest = ROOT_OBSERVATION_DIRECTORY.removeprefix("/state")
        parts = Path(self.guest).parts[1:]
        for count in range(1, len(parts) + 1):
            path = "/" + "/".join(parts[:count])
            self.write_command("mkdir " + path)
            self.write_command("set_inode_field " + path + " mode 040700")
        empty = self.root / "empty-inert-lock"
        empty.write_bytes(b"")
        for value in self.expected:
            name = launch_observation_filename(value["observation_id"])
            payload = {"schema_version": 1, "observation_id": value["observation_id"],
                       "payload": list(value["durable_payload_json"].encode())}
            source = self.root / name
            source.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
            for suffix, input_path in (("", source), (".lock", empty)):
                path = self.guest + "/" + name + suffix
                self.write_command("write " + str(input_path) + " " + path)
                self.write_command("set_inode_field " + path + " mode 0100600")

    def write_command(self, command, image=None):
        # Only setup/mutations of this class's private inert input use -w.
        image = self.image if image is None else image
        self.assertTrue(image.is_relative_to(self.root))
        result = subprocess.run([str(self.debugfs), "-w", "-R", command, str(image)], check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(len(result.stderr.splitlines()), 1, result.stderr)

    def verify(self, image=None, expected=None, label="extract"):
        image = self.image if image is None else image
        return observed.verify(image, self.debugfs, self.identity, observed.sha(image),
                               self.expected if expected is None else expected, self.root / label)

    def test_actual_readonly_bytes_inode_modes_locks_and_hashes_are_retained(self):
        before = observed.sha(self.image)
        checked = self.verify()
        self.assertTrue(checked["passed"])
        self.assertEqual(observed.sha(self.image), before)
        self.assertEqual(len(checked["actual_files"]), 2)
        self.assertEqual(len(checked["original_lock_inodes"]), 2)
        self.assertFalse(checked["cross_boot_verified"])
        self.assertFalse(checked["power_loss_verified"])
        for path in sorted((self.root / "extract").glob("[0-9][0-9][0-9].json")):
            record = json.loads(path.read_bytes())
            self.assertNotIn("-w", record["argv"])
            for name in ("stdout", "stderr"):
                self.assertEqual(observed.sha(Path(record[name]["path"])), record[name]["sha256"])
        self.assertEqual({item["payload_sha256"] for item in checked["actual_files"]},
                         {item["durable_payload_sha256"] for item in self.expected})

    def test_actual_inode_owner_permissions_links_and_ancestor_boundaries_fail_closed(self):
        name = launch_observation_filename(self.expected[0]["observation_id"])
        commands = [f"set_inode_field {self.guest}/{name} mode 0100644",
                    f"set_inode_field {self.guest}/{name} uid 60001",
                    f"set_inode_field {self.guest}/{name} links_count 2",
                    f"set_inode_field {self.guest} mode 040755",
                    "set_inode_field /hepta-native mode 040777"]
        for index, command in enumerate(commands):
            image = self.root / f"inert-mutated-{index}.raw"
            shutil.copyfile(self.image, image)
            self.write_command(command, image)
            before = observed.sha(image)
            with self.subTest(command=command), self.assertRaises(ValueError):
                self.verify(image, label=f"refused-{index}")
            self.assertEqual(observed.sha(image), before)

    def test_actual_missing_extra_and_replaced_record_bytes_are_refused(self):
        name = launch_observation_filename(self.expected[0]["observation_id"])
        cases = [f"rm {self.guest}/{name}", f"rm {self.guest}/{name}.lock",
                 "write " + str(self.root / "empty-inert-lock") + " " + self.guest + "/unexpected",
                 f"set_inode_field {self.guest}/{name} size 1"]
        for index, command in enumerate(cases):
            image = self.root / f"inert-content-{index}.raw"
            shutil.copyfile(self.image, image)
            self.write_command(command, image)
            with self.subTest(command=command), self.assertRaises((ValueError, UnicodeError)):
                self.verify(image, label=f"content-refused-{index}")
        changed = copy.deepcopy(self.expected)
        changed[0]["durable_payload_json"] += " "
        with self.assertRaises(ValueError):
            self.verify(expected=changed, label="payload-refused")

    def test_state_identity_and_exit_zero_missing_path_cannot_pass(self):
        with self.assertRaises(ValueError):
            observed.verify(self.image, self.debugfs, self.identity, "0" * 64, self.expected, self.root / "wrong-hash")
        self.write_command("set_inode_field /hepta-native mode 0100600")
        with self.assertRaises(ValueError):
            self.verify(label="wrong-ancestor")


if __name__ == "__main__":
    unittest.main()
