#!/usr/bin/python3
"""Private-tree regressions. No host GDM, user manager or /run is changed."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location("proof", Path(__file__).with_name("gdm_greeter_proof.py"))
proof = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proof)


class NamedGroupIdentity(unittest.TestCase):
    def test_primary_gid_comes_from_fixed_named_group_and_matches_credentials(self):
        name, uid = "gdm-greeter", 60578
        home = "/run/gdm3/home/" + name
        invocation = "1234567890abcdef1234567890abcdef"
        for gid in (121, 981):
            account = SimpleNamespace(pw_name=name, pw_uid=uid, pw_gid=gid, pw_dir=home)
            with mock.patch.object(proof.os, "getresuid", return_value=(uid, uid, uid)), \
                 mock.patch.object(proof.os, "getresgid", return_value=(gid, gid, gid)), \
                 mock.patch.object(proof.grp, "getgrnam", return_value=SimpleNamespace(gr_gid=gid)) as group, \
                 mock.patch.object(proof.pwd, "getpwuid", return_value=account), \
                 mock.patch.dict(proof.os.environ, {"HOME": home, "INVOCATION_ID": invocation}):
                self.assertEqual(proof.identity(), (uid, gid, name, home, invocation))
                group.assert_called_with("gdm")
                with mock.patch.object(proof.os, "getresgid", return_value=(1000, 1000, 1000)):
                    with self.assertRaises(proof.Rejected):
                        proof.identity()
                account.pw_gid = 65534
                with self.assertRaises(proof.Rejected):
                    proof.identity()


@unittest.skipUnless(os.geteuid() == 0, "requires actual disposable child UID/GID transitions")
class ActualCredentialTree(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="p4-greeter-proof-test-"))
        self.base.chmod(0o755)
        self.name, self.uid = "gdm-greeter", 60578
        self.home = "/run/gdm3/home/" + self.name
        private = self.base / self.home.lstrip("/")
        for part in (self.base / "run", self.base / "run/gdm3", self.base / "run/gdm3/home"):
            part.mkdir(mode=0o755)
            part.chmod(0o755)
        for part in (private, private / ".config", private / ".config/environment.d"):
            part.mkdir(mode=0o700)
            os.chown(part, self.uid, 65534)
        self.leaf = private / ".config/environment.d/gdm.conf"
        self.body = ("USER=gdm-greeter\nLOGNAME=gdm-greeter\nHOME=" + self.home
                     + "\nGDM_SEAT_ID=seat0\nUNRELATED=never-print-this-body\n").encode()
        self.leaf.write_bytes(self.body)
        os.chown(self.leaf, self.uid, 65534)
        self.leaf.chmod(0o600)

    def tearDown(self):
        shutil.rmtree(self.base)

    def child(self, uid=60578, gid=121, identity_only=False, mutate=False):
        read_end, write_end = os.pipe()
        root = os.open(self.base, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW)
        pid = os.fork()
        if pid == 0:
            os.close(read_end)
            try:
                os.setgroups([])
                os.setresgid(gid, gid, gid)
                os.setresuid(uid, uid, uid)
                if mutate:
                    original_read = os.read
                    did_change = False
                    def change_after_read(fd, count):
                        nonlocal did_change
                        data = original_read(fd, count)
                        if data and not did_change:
                            did_change = True
                            with self.leaf.open("ab") as changed:
                                changed.write(b"CHANGED=yes\n")
                        return data
                    proof.os.read = change_after_read
                result = proof.identity() if identity_only else proof.observe(root, uid, self.name, self.home)
                output = {"accepted": True, "result": result, "actual_uid": os.geteuid(), "actual_gid": os.getegid()}
            except Exception as error:
                output = {"accepted": False, "error_type": type(error).__name__,
                          "errno": error.errno if isinstance(error, OSError) else None,
                          "reason": str(error) if isinstance(error, proof.Rejected) else "os-or-identity-error"}
            os.write(write_end, json.dumps(output).encode())
            os._exit(0)
        os.close(write_end)
        os.close(root)
        data = bytearray()
        while part := os.read(read_end, 8192):
            data.extend(part)
        os.close(read_end)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(status, 0)
        return json.loads(data)

    def test_actual_dynamic_uid_reads_private_file_without_body_disclosure(self):
        result = self.child()
        self.assertTrue(result["accepted"], result)
        self.assertEqual((result["actual_uid"], result["actual_gid"]), (60578, 121))
        self.assertEqual(result["result"]["file_sha256"], proof.hashlib.sha256(self.body).hexdigest())
        self.assertNotIn("never-print-this-body", json.dumps(result))

    def test_actual_normal_group_reads_private_file_without_body_disclosure(self):
        result = self.child(gid=981)
        self.assertTrue(result["accepted"], result)
        self.assertEqual((result["actual_uid"], result["actual_gid"]), (60578, 981))
        self.assertEqual(result["result"]["file_sha256"], proof.hashlib.sha256(self.body).hexdigest())
        self.assertNotIn("never-print-this-body", json.dumps(result))

    def test_actual_alex_and_wrong_group_cannot_pass_identity(self):
        for uid, gid in [(1000, 1000), (0, 0), (60577, 65534), (60706, 65534), (60578, 1000), (60578, 65534)]:
            self.assertFalse(self.child(uid=uid, gid=gid, identity_only=True)["accepted"])

    def test_leaf_alias_and_hard_link_are_rejected(self):
        real = self.leaf.with_name("actual")
        self.leaf.rename(real)
        self.leaf.symlink_to(real.name)
        self.assertFalse(self.child()["accepted"])
        self.leaf.unlink()
        os.link(real, self.leaf)
        self.assertFalse(self.child()["accepted"])

    def test_parent_alias_is_rejected(self):
        parent = self.leaf.parent
        moved = parent.with_name("renamed")
        parent.rename(moved)
        parent.symlink_to(moved.name, target_is_directory=True)
        self.assertFalse(self.child()["accepted"])

    def test_wrong_mode_owner_and_fifo_are_rejected(self):
        self.leaf.chmod(0o644)
        self.assertFalse(self.child()["accepted"])
        self.leaf.chmod(0o600)
        os.chown(self.leaf, 1000, 65534)
        self.assertFalse(self.child()["accepted"])
        self.leaf.unlink()
        os.mkfifo(self.leaf, 0o600)
        os.chown(self.leaf, 60578, 65534)
        self.assertFalse(self.child()["accepted"])

    def test_duplicate_or_wrong_required_values_and_oversize_are_rejected(self):
        for data in [self.body + b"USER=alex\n", self.body.replace(b"seat0", b"seat1"),
                     self.body.replace(b"LOGNAME=gdm-greeter", b"LOGNAME=alex"), b"X=" + b"z" * 65536 + b"\n"]:
            self.leaf.write_bytes(data)
            self.assertFalse(self.child()["accepted"])

    def test_actual_content_change_during_read_is_rejected(self):
        self.assertFalse(self.child(mutate=True)["accepted"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
