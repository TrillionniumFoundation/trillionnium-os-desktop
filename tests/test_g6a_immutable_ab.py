"""Real crypto/private-file/publication tests, separate from installed QEMU."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("g6a_guest_tests", ROOT / "packaging/debian/g6a/guest_selector.py")
g6a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g6a)
build_spec = importlib.util.spec_from_file_location("g6a_build_tests", ROOT / "tools/build_g6a_fixture.py")
builder = importlib.util.module_from_spec(build_spec)
build_spec.loader.exec_module(builder)


class ImmutableABHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys = tempfile.TemporaryDirectory(prefix="g6a-real-signatures-")
        cls.directory = Path(cls.keys.name)
        for name in ("approved", "other"):
            subprocess.run(["/usr/bin/openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(cls.directory / name)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        cls.public = subprocess.check_output(["/usr/bin/openssl", "pkey", "-in", str(cls.directory / "approved"), "-pubout"])

    @classmethod
    def tearDownClass(cls):
        cls.keys.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="g6a-files-")
        self.root = Path(self.temporary.name)
        self.root.chmod(0o700)
        self.value = {"schema": g6a.SCHEMA, "slot": "B", "generation": 2,
                      "data_sha256": "1" * 64, "data_bytes": 4096 * 256,
                      "hash_sha256": "2" * 64, "hash_bytes": 4096 * 3,
                      "verity": {"format": 1, "algorithm": "sha256", "data_block_size": 4096, "hash_block_size": 4096, "data_blocks": 256, "hash_start_block": 0, "root_hash": "3" * 64, "salt": "4" * 64},
                      "signature_sha256": "0" * 64, "fixture_only": True, "production_activation_enabled": False}
        self.state = {"schema": g6a.STATE_SCHEMA, "source_slot": "A", "pending_slot": "B", "attempts": 0, "boot_number": 0, "operation_id": "a" * 32, "fixture_only": True, "production_activation_enabled": False}

    def tearDown(self):
        self.temporary.cleanup()

    def sign(self, value=None, key="approved"):
        value = self.value if value is None else value
        preimage = self.root / "preimage"
        preimage.write_bytes(g6a.signing_bytes(value))
        signature = subprocess.check_output(["/usr/bin/openssl", "dgst", "-sha256", "-sign", str(self.directory / key), str(preimage)])
        value["signature_sha256"] = hashlib.sha256(signature).hexdigest()
        return signature

    def test_actual_openssl_accepts_exact_domain_and_descriptor(self):
        signature = self.sign()
        value = g6a.descriptor(json.dumps(self.value, indent=2).encode(), "B")
        g6a.verify_signature(value, signature, self.public)

    def test_rehashed_signature_envelope_does_not_create_crypto_authority(self):
        signature = bytearray(self.sign())
        signature[12] ^= 1
        self.value["signature_sha256"] = hashlib.sha256(signature).hexdigest()
        with self.assertRaisesRegex(g6a.Refused, "signature_invalid"):
            g6a.verify_signature(self.value, bytes(signature), self.public)

    def test_other_real_key_refused(self):
        signature = self.sign(key="other")
        with self.assertRaisesRegex(g6a.Refused, "signature_invalid"):
            g6a.verify_signature(self.value, signature, self.public)

    def test_all_geometry_and_slot_fields_are_signed(self):
        signature = self.sign()
        for field, replacement in (("data_sha256", "9" * 64), ("hash_sha256", "9" * 64), ("slot", "A"), ("generation", 3)):
            value = copy.deepcopy(self.value)
            value[field] = replacement
            with self.subTest(field=field), self.assertRaises(g6a.Refused):
                g6a.verify_signature(value, signature, self.public)
        for field in ("root_hash", "salt"):
            value = copy.deepcopy(self.value)
            value["verity"][field] = "9" * 64
            with self.subTest(field=field), self.assertRaises(g6a.Refused):
                g6a.verify_signature(value, signature, self.public)

    def test_duplicate_json_and_unknown_verity_options_refused(self):
        with self.assertRaises(g6a.Refused):
            g6a.document(b'{"slot":"A","slot":"B"}')
        for field in ("ignore-corruption", "check-at-most-once", "ignore-zero-blocks", "fec-device"):
            value = copy.deepcopy(self.value)
            value["verity"][field] = True
            with self.subTest(field=field), self.assertRaises(g6a.Refused):
                g6a.descriptor(g6a.canonical(value), "B")

    def test_bad_geometry_booleans_and_ceiling_refused(self):
        for field, replacement in (("data_bytes", True), ("data_bytes", 4097), ("fixture_only", False), ("production_activation_enabled", True)):
            value = copy.deepcopy(self.value)
            value[field] = replacement
            with self.subTest(field=field), self.assertRaises(g6a.Refused):
                g6a.descriptor(g6a.canonical(value), "B")

    def test_private_real_read_refuses_links_and_permissions(self):
        path = self.root / "record"
        path.write_bytes(b"exact")
        path.chmod(0o600)
        self.assertEqual(g6a.private_read(path), b"exact")
        path.chmod(0o644)
        with self.assertRaises(g6a.Refused):
            g6a.private_read(path)
        path.chmod(0o600)
        link = self.root / "hard"
        os.link(path, link)
        with self.assertRaises(g6a.Refused):
            g6a.private_read(path)
        link.unlink()
        link.symlink_to(path)
        with self.assertRaises(OSError):
            g6a.private_read(link)

    def test_actual_read_access_time_change_is_not_content_substitution(self):
        path = self.root / "record"
        path.write_bytes(b"stable")
        path.chmod(0o600)
        os.utime(path, ns=(1_000_000_000, 2_000_000_000))
        self.assertEqual(g6a.private_read(path), b"stable")

    def test_actual_publication_readback_and_six_boundaries(self):
        observed = []
        g6a.publish_state(self.root, self.state, observed.append)
        self.assertEqual(tuple(observed), g6a.CUTPOINTS)
        self.assertEqual(g6a.boot_state(g6a.private_read(self.root / "boot-state.json")), self.state)

    def test_actual_interruption_before_replace_retains_orphan(self):
        for stage in g6a.CUTPOINTS[:3]:
            with tempfile.TemporaryDirectory(dir=self.root) as directory:
                Path(directory).chmod(0o700)
                def cut(name):
                    if name == stage:
                        raise InterruptedError("actual callback boundary")
                with self.subTest(stage=stage), self.assertRaises(InterruptedError):
                    g6a.publish_state(directory, self.state, cut)
                self.assertTrue(any(path.name.startswith(".g6a-tmp-") for path in Path(directory).iterdir()))
                self.assertFalse((Path(directory) / "boot-state.json").exists())

    def test_actual_interruption_after_replace_preserves_exact_attempt(self):
        for stage in g6a.CUTPOINTS[3:]:
            with tempfile.TemporaryDirectory(dir=self.root) as directory:
                Path(directory).chmod(0o700)
                def cut(name):
                    if name == stage:
                        raise InterruptedError("actual callback boundary")
                self.state["attempts"] = 1
                with self.subTest(stage=stage), self.assertRaises(InterruptedError):
                    g6a.publish_state(directory, self.state, cut)
                self.assertEqual(g6a.boot_state(g6a.private_read(Path(directory) / "boot-state.json"))["attempts"], 1)
                self.assertFalse(any(path.name.startswith(".g6a-tmp-") for path in Path(directory).iterdir()))

    def test_real_regular_file_cannot_be_boot_block_fact(self):
        path = self.root / "pretend-block"
        path.write_bytes(bytes(4096))
        with self.assertRaisesRegex(g6a.Refused, "actual_block_device_required"):
            g6a.block_digest(path, 4096)

    def test_actual_temp_substitution_refused_before_state_replace(self):
        def replace(name):
            if name == "file_synced":
                temporary = next(self.root.glob(".g6a-tmp-*"))
                foreign = self.root / "foreign"
                foreign.write_bytes(b"foreign")
                foreign.chmod(0o600)
                os.replace(foreign, temporary)
        with self.assertRaisesRegex(g6a.Refused, "temporary_publication_changed"):
            g6a.publish_state(self.root, self.state, replace)
        self.assertFalse((self.root / "boot-state.json").exists())
        self.assertEqual(next(self.root.glob(".g6a-tmp-*")).read_bytes(), b"foreign")

    def test_state_never_accepts_caller_health_or_anchor_claim(self):
        for field in ("health_qualified", "stable_seconds", "protected_floor", "booted_image_verified", "root_hash"):
            state = dict(self.state)
            state[field] = True
            with self.subTest(field=field), self.assertRaises(g6a.Refused):
                g6a.boot_state(g6a.canonical(state))

    def test_attempt_bound_and_capacity_never_silently_extend(self):
        for field, value in (("attempts", True), ("attempts", 3), ("boot_number", g6a.MAX_BOOTS + 1), ("source_slot", "B")):
            state = dict(self.state)
            state[field] = value
            with self.subTest(field=field), self.assertRaises(g6a.Refused):
                g6a.boot_state(g6a.canonical(state))

    def test_host_process_cannot_execute_installed_selector(self):
        with self.assertRaisesRegex(g6a.Refused, "guest_pid1_required"):
            g6a.main()

    def package(self):
        tree = self.root / "deb-tree"
        (tree / "DEBIAN").mkdir(parents=True)
        (tree / "DEBIAN/control").write_text("Package: g6a-fixture-test\nVersion: 1\nArchitecture: all\nMaintainer: Fixture <fixture@example.invalid>\nDescription: disposable extraction test\n")
        (tree / "payload").write_bytes(b"exact approved fixture bytes")
        path = self.root / "input.deb"
        subprocess.run(["dpkg-deb", "--build", "--root-owner-group", str(tree), str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return path, {"size": path.stat().st_size, "sha256": builder.digest(path)}

    def test_actual_dpkg_extracts_exact_sealed_package_snapshot(self):
        path, entry = self.package()
        destination = self.root / "extracted"
        builder.extract_package(path, entry, destination)
        self.assertEqual((destination / "payload").read_bytes(), b"exact approved fixture bytes")

    def test_actual_mutated_package_refused_before_extractor(self):
        path, entry = self.package()
        changed = bytearray(path.read_bytes())
        changed[-1] ^= 1
        path.write_bytes(changed)
        destination = self.root / "extracted"
        with self.assertRaisesRegex(RuntimeError, "actual extracted bytes differ"):
            builder.extract_package(path, entry, destination)
        self.assertFalse(destination.exists())

    def test_actual_package_symlink_refused_before_extractor(self):
        path, entry = self.package()
        link = self.root / "linked.deb"
        link.symlink_to(path)
        destination = self.root / "extracted"
        with self.assertRaises(OSError):
            builder.extract_package(link, entry, destination)
        self.assertFalse(destination.exists())


G6_FIFO_CHILD_CODE = "\nimport errno, importlib.util, json, os, subprocess, sys\nfrom pathlib import Path\nfrom unittest import mock\nroot, mode, path = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])\nmodule_path = root / ('packaging/debian/g6a/guest_selector.py' if mode == 'private' else 'tools/build_g6a_fixture.py')\nspec = importlib.util.spec_from_file_location('bounded_g6_fifo_target', module_path)\nmodule = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(module)\noriginal_open, opened = os.open, []\ndef tracked_open(name, flags, *args, **kwargs):\n    descriptor = original_open(name, flags, *args, **kwargs)\n    if Path(name) == path:\n        opened.append(descriptor)\n        assert flags & os.O_NONBLOCK\n        assert flags & os.O_NOFOLLOW and flags & os.O_CLOEXEC\n        assert os.get_blocking(descriptor) is False\n    return descriptor\nexpected = 'private_file_custody' if mode == 'private' else 'bounded regular signed package required'\ndestination = path.parent / 'not-extracted'\nwith mock.patch.object(os, 'open', side_effect=tracked_open), \\\n        mock.patch.object(os, 'memfd_create', side_effect=AssertionError('FIFO reached memfd effect')), \\\n        mock.patch.object(subprocess, 'run', side_effect=AssertionError('FIFO reached crypto/extractor effect')):\n    try:\n        if mode == 'private':\n            module.private_read(path)\n        else:\n            module.extract_package(path, {'size': 1, 'sha256': '0' * 64}, destination)\n    except (RuntimeError, module.Refused if mode == 'private' else RuntimeError) as error:\n        assert str(error) == expected, str(error)\n    else:\n        raise AssertionError('FIFO accepted')\nassert len(opened) == 1 and not destination.exists()\nfor descriptor in opened:\n    try:\n        os.fstat(descriptor)\n    except OSError as error:\n        assert error.errno == errno.EBADF\n    else:\n        raise AssertionError('FIFO descriptor leaked')\nprint(json.dumps({'refused': expected, 'actual_fifo_opened': True,\n                  'actual_descriptor_closed': True, 'crypto_snapshot_extractor_effects': 0}, sort_keys=True))\n"


class BoundedLeafFifoHostTests(unittest.TestCase):
    """Real no-writer FIFO refusals; no signing/extraction prerequisite.

    This class sorts before ImmutableABHostTests, and uses an ordinary bounded
    child whose only target action is one leaf read. No installed selector runs.
    """
    def _actual_fifo_refusal(self, mode, expected):
        import sys
        with tempfile.TemporaryDirectory(prefix='g6a-real-fifo-') as directory:
            path = Path(directory) / 'no-writer-fifo'
            os.mkfifo(path, 0o600)
            environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
                           'TZ': 'UTC', 'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
            child = subprocess.run([sys.executable, '-B', '-c', G6_FIFO_CHILD_CODE,
                                    str(ROOT), mode, str(path)], cwd=ROOT, env=environment,
                                   stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                   timeout=5, check=False)
            self.assertEqual(child.returncode, 0, child.stderr)
            self.assertEqual(child.stderr, '')
            self.assertEqual(json.loads(child.stdout),
                             {'refused': expected, 'actual_fifo_opened': True,
                              'actual_descriptor_closed': True, 'crypto_snapshot_extractor_effects': 0})
            self.assertTrue(path.exists())

    def test_actual_private_FIFO_refuses_before_any_crypto_effect(self):
        self._actual_fifo_refusal('private', 'private_file_custody')

    def test_actual_package_FIFO_refuses_before_snapshot_or_extractor(self):
        self._actual_fifo_refusal('package', 'bounded regular signed package required')


if __name__ == "__main__":
    unittest.main()
