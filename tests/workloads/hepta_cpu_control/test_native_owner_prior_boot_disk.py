"""Actual temporary ext2/SQLite I/O with inert rows, never native evidence."""
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest

import native_owner_inputs as inputs
import native_owner_prior_boot_disk as physical
import native_owner_prior_boot_store as store
import native_owner_prior_boot_types as t
import run_native_owner as original
from test_native_owner_prior_boot_store import fixture, KEY


class ActualPriorBootDiskTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="inert-prior-disk-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.image = self.root / "inert.raw"
        with self.image.open("xb") as stream:
            stream.truncate(original.STATE_BYTES)
        mkfs = shutil.which("mkfs.ext2")
        debugfs = shutil.which("debugfs")
        self.assertIsNotNone(mkfs, "actual temporary ext2 formatter required")
        self.assertIsNotNone(debugfs, "actual read-only ext2 observer required")
        self.tool = Path(debugfs).resolve()
        self.tool_identity = {"path": str(self.tool), "bytes": self.tool.stat().st_size, "sha256": inputs.sha(self.tool)}
        subprocess.run([mkfs, "-F", "-q", "-b", "4096", "-I", "256", "-m", "0", "-O", "none,filetype", str(self.image)],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        self.created = set()

    def mutate(self, command):
        self.assertTrue(self.image.is_relative_to(self.root))
        result = subprocess.run([str(self.tool), "-w", "-R", command, str(self.image)], check=True,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(len(result.stderr.splitlines()), 1, result.stderr)

    def directory(self, path, uid=0):
        physical_path = physical.Disk.physical(path)
        for count in range(1, len(Path(physical_path).parts)):
            name = "/" + "/".join(Path(physical_path).parts[1:count + 1])
            if name in self.created:
                continue
            self.mutate("mkdir " + name)
            self.mutate("set_inode_field " + name + " mode 040700")
            self.created.add(name)
        if uid:
            for field in ("uid", "gid"):
                self.mutate("set_inode_field " + physical_path + " " + field + " " + str(uid))

    def install(self, source, path, uid=0):
        physical_path = physical.Disk.physical(path)
        self.mutate("write " + str(source) + " " + physical_path)
        self.mutate("set_inode_field " + physical_path + " mode 0100600")
        for field in ("uid", "gid"):
            self.mutate("set_inode_field " + physical_path + " " + field + " " + str(uid))

    def disk(self, label):
        return physical.Disk(self.image, inputs.sha(self.image), self.tool, self.tool_identity, self.root / label)

    def test_actual_readonly_descriptor_and_root_physical_alias_retain_identical_bytes(self):
        path = t.AUTHORITY + "/inert-observation.json"
        self.directory(t.AUTHORITY)
        source = self.root / "inert-observation.json"
        source.write_bytes(b'{"inert_host_test_only":true}')
        self.install(source, path)
        before = inputs.sha(self.image)
        with self.disk("extract") as disk:
            result = disk.read(path, 0, 0o600, 1024)
            self.assertEqual(result["raw"], source.read_bytes())
            self.assertEqual(result["physical_path"], "/hepta-native/protected-source/authority/inert-observation.json")
            self.assertNotIn("passed", result)
            self.assertNotIn("native_execution_verified", result)
            for record in disk.commands:
                self.assertNotIn("-w", record["argv"])
                self.assertEqual(record["pass_fds"], [disk.fd])
                self.assertEqual(record["argv"][-1], "/proc/self/fd/" + str(disk.fd))
        self.assertEqual(inputs.sha(self.image), before)

    def test_actual_protected_ancestor_ownership_fails_even_when_leaf_is_private(self):
        self.directory(t.AUTHORITY)
        self.mutate("set_inode_field /hepta-native/protected-source uid 60001")
        with self.disk("refused") as disk, self.assertRaisesRegex(ValueError, "Root ownership or write boundary"):
            disk.directory(t.AUTHORITY, 0, 0o700)

    def test_ext2_directory_discovery_passes_actual_wal_to_sqlite_and_rejects_late_terminal(self):
        database = self.root / "host-inert.sqlite3"
        connection = sqlite3.connect(database)
        raw, events, insert = fixture(connection)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_autocheckpoint=0")
        terminal = {**events[-1], "event_sequence": 3, "event_id": "inert-late-terminal",
                    "event_kind": "reconcile_committed", "payload_json": "inert terminal only in WAL",
                    "previous_sha256": events[-1]["event_sha256"]}
        import hashlib
        terminal["payload_sha256"] = hashlib.sha256(terminal["payload_json"].encode()).hexdigest()
        terminal["event_sha256"] = store.row_digest(terminal, "event")
        insert("cognitive_local_events", terminal)
        connection.commit()
        directory = t.BASE + "/fleet/agents/" + t.AGENT + "/cognitive"
        path = directory + "/cognitive_1.sqlite3"
        try:
            self.directory(directory, 60001)
            self.install(database, path, 60001)
            self.install(database.with_name(database.name + "-wal"), path + "-wal", 60001)
        finally:
            connection.close()
        before = inputs.sha(self.image)
        with self.disk("wal-extract") as disk:
            with self.assertRaisesRegex(ValueError, "terminal, rollback"):
                physical.database(disk, path, 60001, None, None, {"occurrence_key": KEY, "payload_json": raw},
                                  self.root / "sqlite-read", True)
            self.assertIn("cognitive_1.sqlite3-wal", disk.entries(directory))
        self.assertEqual(inputs.sha(self.image), before)


if __name__ == "__main__":
    unittest.main()
