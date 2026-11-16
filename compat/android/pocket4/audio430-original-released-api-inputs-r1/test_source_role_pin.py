"""Portable controls for the actual provenance-path override defect and API originals."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from source_role_pin import local_source_pin

API_SHA = "39824f8c9fee1582598de5aa8cfa9653e84fbd69bd8aeb92c4a78c861faad552"
API_BLOB = "d802177e249b3f97128699222e65c35e57ba7540"
RELATIVE = "android/manifest/audio-bridge-source-lock.json"


class SourceRolePinControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "local-recipe"
        self.pin = {"bytes": 25, "sha256": API_SHA}

    def test_fixed_local_role_accepts_only_content_identity(self):
        self.assertEqual(local_source_pin(self.root, RELATIVE, self.pin),
            {"path": str(self.root / RELATIVE), **self.pin})

    def test_original_mapping_override_reproduced_and_rejected(self):
        origin = {"path": str(Path(self.temp.name) / "origin-host" / RELATIVE), **self.pin}
        old = {"path": str(self.root / RELATIVE), **origin}
        self.assertEqual(old["path"], origin["path"])
        self.assertNotEqual(old["path"], str(self.root / RELATIVE))
        with self.assertRaises(ValueError):
            local_source_pin(self.root, RELATIVE, origin)
        fixed = local_source_pin(self.root, RELATIVE,
                                 {key: origin[key] for key in ("bytes", "sha256")})
        self.assertEqual(fixed["path"], str(self.root / RELATIVE))
        self.assertEqual(origin["path"], old["path"])

    def test_sizes_reject_boolean_float_negative_and_missing(self):
        for value in (True, False, 25.0, -1, "25", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                local_source_pin(self.root, RELATIVE, {"bytes": value, "sha256": API_SHA})
        with self.assertRaises(ValueError):
            local_source_pin(self.root, RELATIVE, {"sha256": API_SHA})

    def test_digest_rejects_noncanonical_and_nonstring_values(self):
        for value in (API_SHA.upper(), API_SHA[:-1], "z" * 64, 0, True, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                local_source_pin(self.root, RELATIVE, {"bytes": 25, "sha256": value})

    def test_relative_roles_reject_escape_and_alias_spellings(self):
        for value in ("", ".", "..", "../lock", "/lock", "a//b", "a/./b",
                      "a/../b", "a\\b", "a\0b", Path("lock")):
            with self.subTest(value=str(value)), self.assertRaises(ValueError):
                local_source_pin(self.root, value, self.pin)

    def test_root_and_metadata_shape_are_strict(self):
        for root in ("relative", str(self.root), Path("relative")):
            with self.subTest(root=str(root)), self.assertRaises(ValueError):
                local_source_pin(root, RELATIVE, self.pin)
        for ref in ([], None, {"bytes": 25, "sha256": API_SHA, "identity": []}):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                local_source_pin(self.root, RELATIVE, ref)

    def test_four_api_fixtures_are_exact_upstream_git_blobs(self):
        fixtures = Path(__file__).parent / "fixtures" / "36"
        found = []
        for scope in ("public", "system-server"):
            for name in ("service-ondeviceintelligence.txt",
                         "service-ondeviceintelligence-removed.txt"):
                path = fixtures / scope / "api" / name
                raw = path.read_bytes()
                self.assertEqual(raw, b"// Signature format: 2.0\n")
                self.assertEqual(len(raw), 25)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), API_SHA)
                self.assertEqual(hashlib.sha1(b"blob 25\0" + raw).hexdigest(), API_BLOB)
                found.append(path)
        self.assertEqual(len(found), 4)


if __name__ == "__main__":
    unittest.main()
