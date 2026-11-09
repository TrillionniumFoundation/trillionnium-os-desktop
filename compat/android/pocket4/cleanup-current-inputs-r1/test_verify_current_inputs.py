import hashlib
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

import verify_current_inputs as v


class CurrentInputsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def bind(self, path, content):
        raw = content if isinstance(content, bytes) else json.dumps(content, sort_keys=True).encode()
        path.write_bytes(raw)
        return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())

    def fixture(self):
        records = [self.bind(self.root / ("file%03d.py" % i), ("current %d" % i).encode()) for i in range(721)]
        manifest = dict(schema="gallery-qpr1-current-source-final-retained-files-v1", files=records)
        mb = self.bind(self.root / "retained.json", manifest)
        selector = dict(schema="current-application-preparation-selection-v1",
                        selected_preparations=records[:13], retained_manifest=mb)
        sb = self.bind(self.root / "selection.json", selector)
        current = dict(schema="pocket4-linux-android-current-continuation-v1",
                       application_qualification_preparations=sb,
                       application_current_QPR1_leaf_migration={"gallery": {"retained_manifest": mb}},
                       foreground_owner={"name": "test-owner", "active_until_utc": "2099-01-01T00:00:00+00:00"})
        self.current_path = self.root / "CURRENT.json"
        self.bind(self.current_path, current)
        return records, manifest, selector, current

    def test_real_schema_721_files_and_13_preparations_readonly(self):
        records, _, _, _ = self.fixture()
        before = {p.name: (p.stat().st_ino, p.stat().st_mtime_ns, p.read_bytes()) for p in self.root.iterdir()}
        result = v.verify(str(self.current_path))
        self.assertTrue(result["all_current_721_verified"])
        self.assertEqual(result["independently_verified_union"], 721)
        self.assertEqual(result["selected_preparation_count"], 13)
        self.assertFalse(result["deletion_authorized"])
        self.assertFalse(result["complete_current_dependency_census"])
        after = {p.name: (p.stat().st_ino, p.stat().st_mtime_ns, p.read_bytes()) for p in self.root.iterdir()}
        self.assertEqual(before, after)

    def test_changed_source_is_unknown_even_when_manifest_self_consistent(self):
        records, _, _, _ = self.fixture()
        pathlib.Path(records[700]["path"]).write_bytes(b"wrong bytes")
        result = v.verify(str(self.current_path))
        self.assertFalse(result["all_current_721_verified"])
        self.assertEqual(result["errors"][0]["path"], records[700]["path"])

    def test_symlink_parent_rejected(self):
        p = self.root / "real"; p.mkdir()
        bind = self.bind(p / "source.py", b"input")
        (self.root / "alias").symlink_to(p, target_is_directory=True)
        bind["path"] = str(self.root / "alias" / "source.py")
        with self.assertRaises(OSError):
            v.read_bound(bind)

    def test_hardlink_rejected(self):
        bind = self.bind(self.root / "source.py", b"input")
        os.link(bind["path"], self.root / "alias.py")
        with self.assertRaisesRegex(v.Refused, "SINGLE_LINK"):
            v.read_bound(bind)

    def test_secret_material_rejected_before_open(self):
        bind = dict(path=str(self.root / "private-signing" / "owned.p12"), bytes=10, sha256="a" * 64)
        with mock.patch.object(v, "open_exact", side_effect=AssertionError("body must not be opened")):
            with self.assertRaisesRegex(v.Refused, "BODY_REFUSED"):
                v.read_bound(bind)

    def test_duplicate_manifest_path_rejected(self):
        record = dict(path=str(self.root / "one.py"), bytes=0, sha256="a" * 64)
        with self.assertRaisesRegex(v.Refused, "DUPLICATE"):
            v.manifest_records(dict(schema="gallery-qpr1-current-source-final-retained-files-v1", files=[record] * 721))

    def test_wrong_count_and_path_traversal_rejected(self):
        with self.assertRaisesRegex(v.Refused, "721"):
            v.manifest_records(dict(schema="gallery-qpr1-current-source-final-retained-files-v1", files=[]))
        for bad in ("/a/../b", "/a/./b", "relative", "//host/a", "/a//b"):
            with self.subTest(path=bad), self.assertRaises(v.Refused):
                v.safe_path(bad)

    def test_current_selector_manifest_conflict(self):
        _, _, _, current = self.fixture()
        current["application_current_QPR1_leaf_migration"]["gallery"]["retained_manifest"]["sha256"] = "a" * 64
        self.bind(self.current_path, current)
        with self.assertRaisesRegex(v.Refused, "CONFLICT"):
            v.verify(str(self.current_path))

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(v.Refused, "DUPLICATE_JSON_KEY"):
            v.decode(b'{"files":[],"files":[1]}')

    def test_new_current_generation_during_readback_rejected(self):
        self.fixture()
        real = v.read_bound
        calls = 0
        def mutate(binding, *a, **kw):
            nonlocal calls
            calls += 1
            result = real(binding, *a, **kw)
            if calls == 20:
                self.current_path.write_bytes(self.current_path.read_bytes() + b"\n")
            return result
        with mock.patch.object(v, "read_bound", side_effect=mutate):
            result = v.verify(str(self.current_path))
        self.assertFalse(result["all_current_721_verified"])
        self.assertTrue(any(e["path"] == str(self.current_path) for e in result["errors"]))

    def test_changed_input_after_hash_is_detected_at_final_identity_check(self):
        records, _, _, _ = self.fixture()
        real = v.read_bound
        def mutate(binding, *a, **kw):
            result = real(binding, *a, **kw)
            if binding["path"] == records[5]["path"]:
                pathlib.Path(records[0]["path"]).write_bytes(b"subsequent mutation")
            return result
        with mock.patch.object(v, "read_bound", side_effect=mutate):
            result = v.verify(str(self.current_path))
        self.assertFalse(result["all_current_721_verified"])
        self.assertTrue(any("CHANGED_DURING" in e["error"] for e in result["errors"]))

    def test_union_byte_limit(self):
        self.fixture()
        with self.assertRaisesRegex(v.Refused, "BYTE_LIMIT"):
            v.verify(str(self.current_path), max_total_bytes=1)


if __name__ == "__main__":
    unittest.main()
