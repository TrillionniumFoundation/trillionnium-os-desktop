from __future__ import annotations

import base64
import fcntl
import gc
import hashlib
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
import weakref
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("g5_app_storage", ROOT / "platform/app_storage.py")
storage = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = storage
spec.loader.exec_module(storage)
apps = storage.trusted_apps
NOW = 1000
ORIGIN = "https://notes.example.apps.hepta.invalid"
KEYS = None
PUBLIC = {}


def command(arguments):
    return subprocess.run(["/usr/bin/openssl", *arguments], capture_output=True, check=True,
        env={"PATH": "/usr/bin:/bin", "OPENSSL_CONF": "/dev/null", "LC_ALL": "C"})


def setUpModule():
    global KEYS
    if not Path("/usr/bin/openssl").is_file():
        raise RuntimeError("real system Ed25519 verification is required; no crypto skip")
    KEYS = tempfile.TemporaryDirectory(prefix="app-storage-real-ed25519-")
    for name in ("approved", "other"):
        key = Path(KEYS.name) / f"{name}.key"
        command(["genpkey", "-algorithm", "ED25519", "-out", str(key)])
        public = command(["pkey", "-in", str(key), "-pubout", "-outform", "DER"]).stdout
        if len(public) != 44 or public[:12] != bytes.fromhex("302a300506032b6570032100"):
            raise RuntimeError("unexpected system Ed25519 public key encoding")
        PUBLIC[name] = public[12:]


def tearDownModule():
    KEYS.cleanup()
    PUBLIC.clear()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def root(*, key="approved", publisher="example", key_id="publisher:test"):
    public = PUBLIC[key]
    return apps.PublisherTrustRoot(publisher, key_id, public, hashlib.sha256(public).hexdigest(), 500, 1500)


def policy(*, revision=1, roots=None, revoked=()):
    return apps.PublisherTrustPolicy(revision, 100, 2000, (root(),) if roots is None else roots, revoked)


def owner(**kwargs):
    return apps.TrustedAppAdmission(shell_version="1.0.0", policy=policy(**kwargs))


def signed_archive(*, version="1.2.3", app_id="notes", publisher="example", schema=1,
                   assets=None, key="approved", key_id="publisher:test", entries=None, trailing=b""):
    assets = {"index.html": b"<!doctype html>signed", "app.js": b"document.title='signed';"} if assets is None else assets
    value = {"schema": apps.MANIFEST_SCHEMA, "publisher": publisher, "app_id": app_id,
        "version": version, "entrypoint": "index.html", "origin_host": f"{app_id}.{publisher}.apps.hepta.invalid",
        "content_root_sha256": apps.content_root_sha256(assets), "capabilities": [],
        "csp": apps.RESTRICTIVE_CSP, "minimum_shell_version": "1.0.0",
        "signature": {"algorithm": "ed25519", "key_id": key_id,
                      "value": base64.b64encode(bytes(64)).decode("ascii")}}
    if schema is not None:
        value["data_schema_version"] = schema
    unsigned = {**value, "signature": {"algorithm": "ed25519", "key_id": key_id}}
    message = Path(KEYS.name) / "message"
    message.write_bytes(b"trillionnium.desktop.app-manifest-signature.v1\0" + canonical(unsigned))
    signature = command(["pkeyutl", "-sign", "-rawin", "-inkey", str(Path(KEYS.name) / f"{key}.key"), "-in", str(message)]).stdout
    value["signature"]["value"] = base64.b64encode(signature).decode("ascii")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as writer:
        for name, payload in [("manifest.json", canonical(value)), *(assets.items() if entries is None else entries)]:
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            writer.writestr(info, payload)
    return stream.getvalue() + trailing


class AppStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="g5-storage-")
        self.base = Path(self.temp.name)
        self.directory = self.base / "private"
        self.directory.mkdir(mode=0o700)
        self.admission = owner()
        self.stores = []
        self.counter = 0

    def tearDown(self):
        for instance in reversed(self.stores):
            try:
                instance.close()
            except (OSError, storage.AppStorageError):
                pass  # Fault/custody tests intentionally preserve refusal artifacts.
        self.temp.cleanup()

    def store(self, **kwargs):
        instance = storage.AppStorage(self.directory, admission=kwargs.pop("admission", self.admission), **kwargs)
        self.stores.append(instance)
        return instance

    def bundle(self, admission=None, **kwargs):
        self.counter += 1
        path = self.base / f"bundle-{self.counter}.zip"
        path.write_bytes(signed_archive(**kwargs))
        return (self.admission if admission is None else admission).admit_bundle_file(path, now_unix=NOW)

    def install(self, instance, *, principal="principal:a", operation="install:1", bundle=None, **kwargs):
        bundle = self.bundle(**kwargs) if bundle is None else bundle
        plan = instance.prepare_install(principal, bundle, now_unix=NOW)
        return instance.commit_install(plan, operation_id=operation, now_unix=NOW)

    def reopen(self, instance, admission=None):
        instance.close()
        return self.store(admission=owner() if admission is None else admission)

    def test_real_signed_install_read_and_restart(self):
        instance = self.store()
        handle = self.install(instance)
        self.assertEqual(instance.asset_response(handle, ORIGIN + "/index.html", now_unix=NOW).body, b"<!doctype html>signed")
        instance.put_data(handle, "settings", b"private", operation_id="data:1", now_unix=NOW)
        restarted = self.reopen(instance)
        handle = restarted.open_app("principal:a", ORIGIN, now_unix=NOW)
        self.assertEqual(restarted.read_data(handle, "settings", now_unix=NOW), b"private")
        self.assertEqual(handle.version, "1.2.3")

    def test_no_default_roots(self):
        instance = storage.AppStorage(self.directory)
        self.stores.append(instance)
        with self.assertRaises(storage.AppStorageError):
            instance.prepare_install("principal:a", self.bundle(), now_unix=NOW)
        with self.assertRaises(storage.AppStorageError):
            instance.synchronize_policy(now_unix=NOW)
        self.assertFalse(list(self.directory.glob("package-*.zip")))

    def test_no_boolean_or_digest_admission_owner(self):
        for admission in (True, {"approved": True}, object()):
            with self.subTest(admission=type(admission)), self.assertRaises(storage.AppStorageError):
                storage.AppStorage(self.directory, admission=admission)

    def test_foreign_admission_bundle_refused(self):
        instance = self.store()
        foreign = self.bundle(admission=owner())
        with self.assertRaises(storage.AppStorageError):
            instance.prepare_install("principal:a", foreign, now_unix=NOW)
        self.assertFalse(list(self.directory.glob("event-*.json")))

    def test_public_handle_and_plan_construction_refused(self):
        for cls in (storage.InstalledApp, storage.InstallTransaction):
            with self.subTest(cls=cls), self.assertRaises(storage.AppStorageError):
                cls(approved=True, digest="0" * 64)

    def test_forged_bundle_issuer_refused(self):
        instance = self.store()
        forged = object.__new__(apps.VerifiedAppBundle)
        object.__setattr__(forged, "origin_host", "notes.example.apps.hepta.invalid")
        object.__setattr__(forged, "entrypoint", "index.html")
        object.__setattr__(forged, "_issuer", object())
        with self.assertRaises(storage.AppStorageError):
            instance.prepare_install("principal:a", forged, now_unix=NOW)

    def test_cross_principal_and_cross_app_data_isolation(self):
        instance = self.store()
        first = self.install(instance)
        second = self.install(instance, principal="principal:b", operation="install:2")
        third = self.install(instance, operation="install:3", app_id="other")
        instance.put_data(first, "settings", b"a", operation_id="data:1", now_unix=NOW)
        for handle in (second, third):
            with self.subTest(origin=handle.origin, principal=handle.principal), self.assertRaises(storage.AppStorageError):
                instance.read_data(handle, "settings", now_unix=NOW)
        self.assertEqual(instance.read_data(first, "settings", now_unix=NOW), b"a")

    def test_only_exact_synthetic_https_origins(self):
        instance = self.store()
        self.install(instance)
        for origin in (ORIGIN + "/", ORIGIN + "?", ORIGIN + "#", ORIGIN + ":443", ORIGIN.upper(),
                       "hepta-app://notes.example/", "http://notes.example.apps.hepta.invalid", "https://example.com",
                       "https://user@notes.example.apps.hepta.invalid", "https://notes.example.apps.hepta.invalid%2f"):
            with self.subTest(origin=origin), self.assertRaises((storage.AppStorageError, apps.AppAdmissionError)):
                instance.open_app("principal:a", origin, now_unix=NOW)

    def test_local_response_cross_origin_and_traversal_refused(self):
        instance = self.store()
        handle = self.install(instance)
        for path in ("https://other.example.apps.hepta.invalid/index.html", ORIGIN + "/../index.html",
                     ORIGIN + "/index.html?x=1", ORIGIN + "/manifest.json", ORIGIN + "/%69ndex.html"):
            with self.subTest(path=path), self.assertRaises(storage.AppStorageError):
                instance.asset_response(handle, path, now_unix=NOW)

    def test_data_keys_never_become_filesystem_paths(self):
        instance = self.store()
        handle = self.install(instance)
        for key in ("../secret", "/root", "foo/bar", "foo\\bar", "%2f", ".hidden", "NUL.txt", "a.", "a\x00", "é"):
            with self.subTest(key=key), self.assertRaises((storage.AppStorageError, apps.AppAdmissionError)):
                instance.put_data(handle, key, b"x", operation_id="invalid", now_unix=NOW)
        self.assertFalse(list(self.directory.glob("data-*.bin")))

    def test_data_bytes_are_immutable_and_bounded(self):
        instance = self.store()
        handle = self.install(instance)
        for payload in (bytearray(b"x"), memoryview(b"x"), b"x" * (storage.MAX_DATA_BYTES + 1)):
            with self.subTest(type=type(payload)), self.assertRaises(storage.AppStorageError):
                instance.put_data(handle, "settings", payload, operation_id="invalid", now_unix=NOW)
        instance.put_data(handle, "empty", b"", operation_id="empty", now_unix=NOW)
        self.assertEqual(instance.read_data(handle, "empty", now_unix=NOW), b"")

    def test_upgrade_keeps_schema_data_and_invalidates_old_handle(self):
        instance = self.store()
        first = self.install(instance)
        instance.put_data(first, "settings", b"same-schema", operation_id="data:1", now_unix=NOW)
        second = self.install(instance, operation="install:2", version="1.3.0")
        with self.assertRaises(storage.AppStorageError):
            instance.read_data(first, "settings", now_unix=NOW)
        self.assertEqual(instance.read_data(second, "settings", now_unix=NOW), b"same-schema")

    def test_numeric_version_order_and_downgrade_refusal(self):
        instance = self.store()
        self.install(instance, version="1.9.0")
        self.install(instance, operation="install:2", version="1.10.0")
        for version in ("1.9.99", "1.10.0", "0.999.999"):
            with self.subTest(version=version), self.assertRaises(storage.AppStorageError):
                instance.prepare_install("principal:a", self.bundle(version=version), now_unix=NOW)

    def test_same_version_changed_signed_content_refused(self):
        instance = self.store()
        self.install(instance)
        bundle = self.bundle(assets={"index.html": b"<!doctype html>replacement"})
        with self.assertRaises(storage.AppStorageError):
            instance.prepare_install("principal:a", bundle, now_unix=NOW)

    def test_prerelease_storage_profile_explicitly_refused(self):
        instance = self.store()
        with self.assertRaises(storage.AppStorageError):
            instance.prepare_install("principal:a", self.bundle(version="2.0.0-rc.1"), now_unix=NOW)

    def test_migration_and_schema_removal_explicitly_refused(self):
        instance = self.store()
        self.install(instance)
        for schema in (2, None):
            with self.subTest(schema=schema), self.assertRaises(storage.AppStorageError):
                instance.prepare_install("principal:a", self.bundle(version="2.0.0", schema=schema), now_unix=NOW)

    def test_uninstall_preserves_floor_and_data_tombstones(self):
        instance = self.store()
        handle = self.install(instance)
        instance.put_data(handle, "settings", b"history", operation_id="data:1", now_unix=NOW)
        before = set(self.directory.iterdir())
        instance.uninstall(handle, operation_id="uninstall:1", now_unix=NOW)
        self.assertTrue(before <= set(self.directory.iterdir()))
        with self.assertRaises(storage.AppStorageError):
            instance.open_app("principal:a", ORIGIN, now_unix=NOW)
        restarted = self.reopen(instance)
        with self.assertRaises(storage.AppStorageError):
            restarted.prepare_install("principal:a", self.bundle(admission=restarted._admission), now_unix=NOW)
        newer = self.install(restarted, bundle=self.bundle(admission=restarted._admission, version="2.0.0"), operation="reinstall")
        self.assertEqual(restarted.read_data(newer, "settings", now_unix=NOW), b"history")

    def test_data_delete_is_durable_and_never_erases_history(self):
        instance = self.store()
        handle = self.install(instance)
        instance.put_data(handle, "settings", b"first", operation_id="data:1", now_unix=NOW)
        paths = list(self.directory.glob("data-*.bin"))
        instance.put_data(handle, "settings", b"second", operation_id="data:2", now_unix=NOW)
        instance.delete_data(handle, "settings", operation_id="delete:1", now_unix=NOW)
        self.assertEqual(paths[0].read_bytes(), b"first")
        restarted = self.reopen(instance)
        handle = restarted.open_app("principal:a", ORIGIN, now_unix=NOW)
        with self.assertRaises(storage.AppStorageError):
            restarted.read_data(handle, "settings", now_unix=NOW)

    def test_operation_replay_refused_after_restart(self):
        instance = self.store()
        self.install(instance, operation="used")
        restarted = self.reopen(instance)
        plan = restarted.prepare_install("principal:a", self.bundle(admission=restarted._admission, version="2.0.0"), now_unix=NOW)
        with self.assertRaises(storage.AppStorageError):
            restarted.commit_install(plan, operation_id="used", now_unix=NOW)
        self.assertEqual(len(list(self.directory.glob("package-*.zip"))), 1)

    def test_transactions_are_single_use_and_owner_bound(self):
        instance = self.store()
        plan = instance.prepare_install("principal:a", self.bundle(), now_unix=NOW)
        instance.commit_install(plan, operation_id="install:1", now_unix=NOW)
        with self.assertRaises(storage.AppStorageError):
            instance.commit_install(plan, operation_id="install:2", now_unix=NOW)
        restarted = self.reopen(instance)
        with self.assertRaises(storage.AppStorageError):
            restarted.commit_install(plan, operation_id="install:3", now_unix=NOW)

    def test_intervening_data_mutation_invalidates_update_plan(self):
        instance = self.store()
        handle = self.install(instance)
        plan = instance.prepare_install("principal:a", self.bundle(version="2.0.0"), now_unix=NOW)
        instance.put_data(handle, "settings", b"changed", operation_id="data:1", now_unix=NOW)
        with self.assertRaises(storage.AppStorageError):
            instance.commit_install(plan, operation_id="install:2", now_unix=NOW)

    def test_current_revocation_refuses_assets_data_and_update(self):
        instance = self.store()
        handle = self.install(instance)
        instance.put_data(handle, "settings", b"private", operation_id="data:1", now_unix=NOW)
        plan = instance.prepare_install("principal:a", self.bundle(version="2.0.0"), now_unix=NOW)
        self.admission.replace_policy(policy(revision=2, revoked=(("example", "publisher:test"),)))
        instance.synchronize_policy(now_unix=NOW)
        for call in (lambda: instance.asset_response(handle, ORIGIN + "/index.html", now_unix=NOW),
                     lambda: instance.read_data(handle, "settings", now_unix=NOW),
                     lambda: instance.commit_install(plan, operation_id="install:2", now_unix=NOW)):
            with self.assertRaises(storage.AppStorageError):
                call()

    def test_durable_policy_revision_and_revocation_cannot_restart_rollback(self):
        instance = self.store()
        self.install(instance)
        self.admission.replace_policy(policy(revision=2, revoked=(("example", "publisher:test"),)))
        instance.synchronize_policy(now_unix=NOW)
        restarted = self.reopen(instance, admission=owner())
        with self.assertRaises(storage.AppStorageError):
            restarted.open_app("principal:a", ORIGIN, now_unix=NOW)
        self.assertFalse(list(self.directory.glob("event-000004.intent.json")))

    def test_refused_revoked_read_persists_observed_policy_before_key_refusal(self):
        instance = self.store()
        handle = self.install(instance)
        self.admission.replace_policy(policy(revision=2, revoked=(("example", "publisher:test"),)))
        with self.assertRaises(storage.AppStorageError):
            instance.asset_response(handle, ORIGIN + "/index.html", now_unix=NOW)
        self.assertEqual(instance._policy["revision"], 2)
        restarted = self.reopen(instance, admission=owner())
        with self.assertRaises(storage.AppStorageError):
            restarted.open_app("principal:a", ORIGIN, now_unix=NOW)

    def test_new_revocation_policy_capacity_failure_cannot_clean_restart_old_floor(self):
        instance = self.store()
        handle = self.install(instance)
        self.admission.replace_policy(policy(revision=2, revoked=(("example", "publisher:test"),)))
        with patch.object(storage, "MAX_EVENTS", instance._sequence), self.assertRaises(storage.AppStorageError):
            instance.asset_response(handle, ORIGIN + "/index.html", now_unix=NOW)
        self.assertTrue(instance._poisoned)
        instance.close()
        with self.assertRaises(storage.RecoveryRequired):
            self.store(admission=owner())

    def test_durable_policy_same_revision_different_roots_refused(self):
        instance = self.store()
        self.install(instance)
        restarted = self.reopen(instance, admission=owner(roots=(root(key="other"),)))
        with self.assertRaises(storage.AppStorageError):
            restarted.synchronize_policy(now_unix=NOW)

    def test_durable_pin_rebinding_at_new_revision_refused(self):
        instance = self.store()
        self.install(instance)
        restarted = self.reopen(instance, admission=owner(revision=2, roots=(root(key="other"),)))
        with self.assertRaises(storage.AppStorageError):
            restarted.synchronize_policy(now_unix=NOW)

    def test_legitimate_rotated_key_with_removed_old_root_survives_restart(self):
        instance = self.store()
        self.install(instance)
        rotated = policy(revision=2, roots=(root(key="other", key_id="publisher:new"),),
                         revoked=(("example", "publisher:test"),))
        self.admission.replace_policy(rotated)
        self.install(instance, operation="install:2", version="2.0.0", key="other", key_id="publisher:new")
        new_owner = apps.TrustedAppAdmission(shell_version="1.0.0", policy=rotated)
        restarted = self.reopen(instance, admission=new_owner)
        handle = restarted.open_app("principal:a", ORIGIN, now_unix=NOW)
        self.assertEqual(handle.version, "2.0.0")
        self.assertEqual(len(restarted._policy["pins"]), 2)

    def test_canonical_policy_record_overflow_refuses_before_intent(self):
        instance = self.store()
        # The two wire records add overhead beyond the concrete owner's policy
        # snapshot. A smaller configured profile tests the actual byte boundary.
        snapshot = canonical(instance._policy_snapshot(NOW))
        before = set(self.directory.iterdir())
        with patch.object(storage, "MAX_RECORD_BYTES", len(snapshot)), self.assertRaises(storage.AppStorageError):
            instance.synchronize_policy(now_unix=NOW)
        self.assertEqual(set(self.directory.iterdir()), before)

    def test_current_expired_policy_and_key_refuse(self):
        instance = self.store()
        handle = self.install(instance)
        for now in (499, 1500, 2000, True):
            with self.subTest(now=now), self.assertRaises(storage.AppStorageError):
                instance.asset_response(handle, ORIGIN + "/index.html", now_unix=now)

    def test_actual_signature_failure_never_becomes_storage_authority(self):
        path = self.base / "bad-signature.zip"
        path.write_bytes(signed_archive(key="other"))
        with self.assertRaises(apps.AppAdmissionError):
            self.admission.admit_bundle_file(path, now_unix=NOW)
        self.assertFalse(list(self.directory.glob("package-*.zip")))

    def test_malformed_zip_and_traversal_never_become_storage_authority(self):
        for number, payload in enumerate((signed_archive(trailing=b"tail"), signed_archive(entries=[("../outside", b"x")]),
                                         signed_archive(entries=[("index.html", b"substituted")]), b"not a ZIP")):
            path = self.base / f"bad-{number}.zip"
            path.write_bytes(payload)
            with self.subTest(number=number), self.assertRaises(apps.AppAdmissionError):
                self.admission.admit_bundle_file(path, now_unix=NOW)

    def test_symlink_and_hardlink_archive_input_refused(self):
        path = self.base / "input.zip"
        path.write_bytes(signed_archive())
        linked = self.base / "linked.zip"
        linked.symlink_to(path)
        with self.assertRaises(apps.AppAdmissionError):
            self.admission.admit_bundle_file(linked, now_unix=NOW)
        linked.unlink()
        os.link(path, linked)
        with self.assertRaises(apps.AppAdmissionError):
            self.admission.admit_bundle_file(path, now_unix=NOW)

    def test_unknown_signed_asset_extension_install_refused(self):
        instance = self.store()
        bundle = self.bundle(assets={"index.html": b"<!doctype html>", "native.exe": b"MZ"})
        with self.assertRaises(storage.AppStorageError):
            instance.prepare_install("principal:a", bundle, now_unix=NOW)
        self.assertFalse(list(self.directory.glob("package-*.zip")))

    def test_root_and_lease_must_be_private(self):
        os.chmod(self.directory, 0o750)
        with self.assertRaises(storage.AppStorageError):
            self.store()
        os.chmod(self.directory, 0o700)
        lease = self.directory / storage.LEASE
        lease.write_bytes(b"")
        os.chmod(lease, 0o660)
        with self.assertRaises(storage.AppStorageError):
            self.store()

    def test_lease_symlink_hardlink_and_nonempty_refused(self):
        outside = self.base / "lease"
        outside.write_bytes(b"")
        os.chmod(outside, 0o600)
        lease = self.directory / storage.LEASE
        lease.symlink_to(outside)
        with self.assertRaises((storage.AppStorageError, OSError)):
            self.store()
        lease.unlink()
        os.link(outside, lease)
        with self.assertRaises(storage.AppStorageError):
            self.store()
        lease.unlink()
        lease.write_bytes(b"foreign")
        os.chmod(lease, 0o600)
        with self.assertRaises(storage.AppStorageError):
            self.store()

    def test_other_coordinator_cannot_acquire_live_lease(self):
        instance = self.store()
        with self.assertRaises(storage.AppStorageError):
            self.store()
        self.install(instance)

    def test_garbage_collection_releases_descriptors_without_clean_receipt(self):
        instance = storage.AppStorage(self.directory, admission=self.admission)
        descriptors = [instance._lease, *(fd for _, fd, _ in instance._chain)]
        reference = weakref.ref(instance)
        del instance
        gc.collect()
        self.assertIsNone(reference())
        for fd in descriptors:
            with self.subTest(fd=fd), self.assertRaises(OSError):
                os.fstat(fd)
        lease = os.open(self.directory / storage.LEASE, os.O_RDWR | os.O_NOFOLLOW)
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(lease)
        self.assertTrue((self.directory / "owner-000001.open.json").exists())
        self.assertFalse((self.directory / "owner-000001.clean.json").exists())
        with self.assertRaises(storage.RecoveryRequired):
            self.store()

    def test_interrupted_close_never_retries_reused_lease_or_chain_descriptors(self):
        for boundary in ("lease", "chain"):
            with self.subTest(boundary=boundary):
                directory = self.base / f"close-{boundary}"
                directory.mkdir(mode=0o700)
                instance = storage.AppStorage(directory, admission=self.admission)
                descriptors = [instance._lease, *(fd for _, fd, _ in instance._chain)]
                target = instance._lease if boundary == "lease" else instance._chain[-1][1]
                reference = weakref.ref(instance)
                real_close = os.close
                attempted = []
                def close_then_interrupt(fd):
                    attempted.append(fd)
                    real_close(fd)
                    if fd == target:
                        raise KeyboardInterrupt("injected after actual kernel close")
                # Leave a real durable unresolved session and interrupt cleanup
                # after actual close, not before the kernel effect.
                instance._poisoned = True
                with patch.object(storage.os, "close", side_effect=close_then_interrupt), self.assertRaises(KeyboardInterrupt):
                    instance.close()
                self.assertEqual(set(attempted), set(descriptors))
                self.assertEqual(len(attempted), len(descriptors))
                self.assertEqual(instance._lease, -1)
                self.assertEqual(instance._chain, [])
                self.assertEqual(instance._root_fd, -1)
                for fd in descriptors:
                    with self.assertRaises(OSError):
                        os.fstat(fd)
                unrelated = os.open("/dev/null", os.O_RDONLY)
                if unrelated != target:
                    os.dup2(unrelated, target)
                    os.close(unrelated)
                try:
                    del instance
                    gc.collect()
                    self.assertIsNone(reference())
                    self.assertTrue(stat.S_ISCHR(os.fstat(target).st_mode))
                    self.assertEqual(os.read(target, 1), b"")
                finally:
                    os.close(target)
                lease = os.open(directory / storage.LEASE, os.O_RDWR | os.O_NOFOLLOW)
                try:
                    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    os.close(lease)
                with self.assertRaises(storage.RecoveryRequired):
                    storage.AppStorage(directory, admission=self.admission)

    def test_cleanup_attempts_all_descriptors_after_multiple_close_errors(self):
        instance = storage.AppStorage(self.directory, admission=self.admission)
        descriptors = [instance._lease, *(fd for _, fd, _ in reversed(instance._chain))]
        real_close = os.close
        attempted = []
        first_error = OSError("first close return failure")
        def close_then_fail(fd):
            attempted.append(fd)
            real_close(fd)
            raise first_error if len(attempted) == 1 else KeyboardInterrupt("subsequent close return failure")
        instance._poisoned = True
        with patch.object(storage.os, "close", side_effect=close_then_fail):
            with self.assertRaises(OSError) as error:
                instance.close()
        self.assertIs(error.exception, first_error)
        self.assertEqual(attempted, descriptors)
        self.assertEqual(instance._chain, [])
        self.assertEqual(instance._lease, -1)
        del instance
        gc.collect()
        for fd in descriptors:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_ancestor_symlink_and_noncanonical_root_refused(self):
        linked = self.base / "alias"
        linked.symlink_to(self.directory, target_is_directory=True)
        for path in (linked, str(self.directory) + "/", self.directory.parent / ".." / self.directory.name):
            with self.subTest(path=path), self.assertRaises((storage.AppStorageError, OSError)):
                storage.AppStorage(path, admission=self.admission)

    def test_root_replacement_and_ancestor_replacement_latch(self):
        instance = self.store()
        handle = self.install(instance)
        detached = self.base / "detached"
        self.directory.rename(detached)
        self.directory.mkdir(mode=0o700)
        with self.assertRaises(storage.RecoveryRequired):
            instance.asset_response(handle, ORIGIN + "/index.html", now_unix=NOW)
        with self.assertRaises(storage.RecoveryRequired):
            instance.prepare_install("principal:b", self.bundle(), now_unix=NOW)
        instance.close()
        with self.assertRaises(storage.RecoveryRequired):
            storage.AppStorage(detached, admission=self.admission)

    def test_lease_replacement_latches_without_reclaiming_lock(self):
        instance = self.store()
        handle = self.install(instance)
        lease = self.directory / storage.LEASE
        lease.rename(self.directory / "stolen-lock")
        lease.write_bytes(b"")
        os.chmod(lease, 0o600)
        with self.assertRaises(storage.RecoveryRequired):
            instance.asset_response(handle, ORIGIN + "/index.html", now_unix=NOW)

    def test_package_symlink_hardlink_mode_and_bytes_refused(self):
        for attack in ("symlink", "hardlink", "mode", "bytes"):
            with self.subTest(attack=attack):
                location = self.base / attack
                location.mkdir(mode=0o700)
                instance = storage.AppStorage(location, admission=self.admission)
                self.stores.append(instance)
                handle = self.install(instance)
                package = next(location.glob("package-*.zip"))
                if attack == "symlink":
                    copy = self.base / "package-copy"
                    copy.write_bytes(package.read_bytes())
                    package.unlink()
                    package.symlink_to(copy)
                elif attack == "hardlink":
                    os.link(package, self.base / "package-hardlink")
                elif attack == "mode":
                    os.chmod(package, 0o640)
                else:
                    package.write_bytes(b"substituted")
                with self.assertRaises(storage.RecoveryRequired):
                    instance.asset_response(handle, ORIGIN + "/index.html", now_unix=NOW)
                instance.close()
                with self.assertRaises(storage.RecoveryRequired):
                    storage.AppStorage(location, admission=self.admission)

    def test_data_tampering_latches_and_restart_refuses(self):
        instance = self.store()
        handle = self.install(instance)
        instance.put_data(handle, "settings", b"original", operation_id="data:1", now_unix=NOW)
        path = next(self.directory.glob("data-*.bin"))
        path.write_bytes(b"replaced")
        with self.assertRaises(storage.RecoveryRequired):
            instance.read_data(handle, "settings", now_unix=NOW)
        instance.close()
        with self.assertRaises(storage.RecoveryRequired):
            self.store()

    def test_fsync_failure_persists_refusal_even_when_commit_candidate_exists(self):
        instance = self.store()
        handle = self.install(instance)
        real = os.fsync
        def fail_commit(fd):
            if os.readlink(f"/proc/self/fd/{fd}").endswith("event-000003.commit.json"):
                raise OSError("injected commit barrier failure")
            return real(fd)
        with patch.object(storage.os, "fsync", side_effect=fail_commit), self.assertRaises(storage.RecoveryRequired):
            instance.put_data(handle, "settings", b"candidate", operation_id="data:1", now_unix=NOW)
        self.assertTrue((self.directory / "event-000003.commit.json").exists())
        instance.close()
        self.assertFalse((self.directory / "owner-000001.clean.json").exists())
        with self.assertRaises(storage.RecoveryRequired):
            self.store()

    def test_partial_write_disk_full_preserves_intent_and_refuses_restart(self):
        instance = self.store()
        handle = self.install(instance)
        real = os.write
        count = 0
        def partial(fd, payload):
            nonlocal count
            if os.readlink(f"/proc/self/fd/{fd}").endswith("data-000003.bin"):
                count += 1
                if count > 1:
                    raise OSError(28, "injected disk full")
                return real(fd, payload[:2])
            return real(fd, payload)
        with patch.object(storage.os, "write", side_effect=partial), self.assertRaises(storage.RecoveryRequired):
            instance.put_data(handle, "settings", b"partial", operation_id="data:1", now_unix=NOW)
        self.assertEqual((self.directory / "data-000003.bin").read_bytes(), b"pa")
        self.assertTrue((self.directory / "event-000003.intent.json").exists())
        instance.close()
        with self.assertRaises(storage.RecoveryRequired):
            self.store()

    def test_return_window_interruption_is_not_silent_success_after_restart(self):
        instance = self.store()
        handle = self.install(instance)
        with patch.object(instance, "_return_commit", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            instance.put_data(handle, "settings", b"durable-but-unreturned", operation_id="data:1", now_unix=NOW)
        self.assertTrue((self.directory / "event-000003.commit.json").exists())
        instance.close()
        with self.assertRaises(storage.RecoveryRequired):
            self.store()

    def test_process_exit_without_clean_close_is_persistent_refusal(self):
        child = os.fork()
        if child == 0:
            try:
                instance = storage.AppStorage(self.directory, admission=owner())
                os._exit(0)  # Deliberately leave the fsynced open record unresolved.
            except BaseException:
                os._exit(3)
        _, status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 0)
        with self.assertRaises(storage.RecoveryRequired):
            self.store()

    def test_install_result_window_interrupt_does_not_write_clean_receipt(self):
        instance = self.store()
        plan = instance.prepare_install("principal:a", self.bundle(), now_unix=NOW)
        with patch.object(instance, "_handle", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            instance.commit_install(plan, operation_id="install:1", now_unix=NOW)
        self.assertTrue((self.directory / "event-000002.commit.json").exists())
        instance.close()
        self.assertFalse((self.directory / "owner-000001.clean.json").exists())
        with self.assertRaises(storage.RecoveryRequired):
            self.store()

    def test_lost_wrapper_return_keeps_durable_commit_single_use(self):
        instance = self.store()
        plan = instance.prepare_install("principal:a", self.bundle(), now_unix=NOW)
        hit = []
        def trace(frame, event, result):
            if (event == "return" and frame.f_code is storage.AppStorage.commit_install.__code__
                    and type(result) is storage.InstalledApp):
                hit.append(True)
                sys.settrace(None)
                raise KeyboardInterrupt("injected final wrapper return interrupt")
            return trace
        sys.settrace(trace)
        try:
            with self.assertRaises(KeyboardInterrupt):
                instance.commit_install(plan, operation_id="install:1", now_unix=NOW)
        finally:
            sys.settrace(None)
        self.assertEqual(hit, [True])
        # CPython emits this callback after the callee's protected region. The
        # known durable local commit is terminal, even though the caller lost
        # its result. It cannot be replayed or broadened by a new owner.
        restarted = self.reopen(instance)
        handle = restarted.open_app("principal:a", ORIGIN, now_unix=NOW)
        self.assertEqual(handle.version, "1.2.3")
        with self.assertRaises(storage.AppStorageError):
            restarted.commit_install(plan, operation_id="install:1", now_unix=NOW)
        with self.assertRaises(storage.AppStorageError):
            restarted.prepare_install("principal:a", self.bundle(admission=restarted._admission), now_unix=NOW)
        newer = restarted.prepare_install("principal:a", self.bundle(admission=restarted._admission, version="2.0.0"), now_unix=NOW)
        with self.assertRaises(storage.AppStorageError):
            restarted.commit_install(newer, operation_id="install:1", now_unix=NOW)

    def test_busy_cleanup_interrupt_preserves_unresolved_session(self):
        import inspect
        instance = self.store()
        plan = instance.prepare_install("principal:a", self.bundle(), now_unix=NOW)
        lines, start = inspect.getsourcelines(storage._owned)
        boundary = next(start + number for number, line in enumerate(lines)
                        if "self._busy = False" in line)
        hit = []
        def trace(frame, event, result):
            if (event == "line" and frame.f_code is storage.AppStorage.commit_install.__code__
                    and frame.f_lineno == boundary):
                hit.append(True)
                sys.settrace(None)
                raise KeyboardInterrupt("injected busy cleanup interrupt")
            return trace
        sys.settrace(trace)
        try:
            with self.assertRaises(KeyboardInterrupt):
                instance.commit_install(plan, operation_id="install:1", now_unix=NOW)
        finally:
            sys.settrace(None)
        self.assertEqual(hit, [True])
        self.assertTrue(instance._poisoned)
        self.assertFalse(instance._busy)
        instance.close()
        with self.assertRaises(storage.RecoveryRequired):
            self.store()

    def test_clean_close_barrier_failure_preserves_explicit_refusal(self):
        instance = self.store()
        self.install(instance)
        with patch.object(storage.os, "fsync", side_effect=OSError("injected close barrier failure")), self.assertRaises(OSError):
            instance.close()
        self.assertTrue((self.directory / "owner-000001.refused.json").exists())
        with self.assertRaises(storage.RecoveryRequired):
            self.store()

    def test_revocation_during_publication_leaves_unresolved_intent(self):
        instance = self.store()
        handle = self.install(instance)
        real = os.fsync
        changed = False
        def revoke(fd):
            nonlocal changed
            result = real(fd)
            if not changed and os.readlink(f"/proc/self/fd/{fd}").endswith("data-000003.bin"):
                changed = True
                self.admission.replace_policy(policy(revision=2, revoked=(("example", "publisher:test"),)))
            return result
        with patch.object(storage.os, "fsync", side_effect=revoke), self.assertRaises(storage.AppStorageError):
            instance.put_data(handle, "settings", b"never-authorized-completion", operation_id="data:1", now_unix=NOW)
        self.assertTrue(changed)
        self.assertFalse((self.directory / "event-000003.commit.json").exists())
        instance.close()
        with self.assertRaises(storage.RecoveryRequired):
            self.store()

    def test_staged_file_substitution_preserves_foreign_inode_and_refuses(self):
        instance = self.store()
        handle = self.install(instance)
        real = os.fsync
        replaced = False
        def replace(fd):
            nonlocal replaced
            result = real(fd)
            if not replaced and os.readlink(f"/proc/self/fd/{fd}").endswith("data-000003.bin"):
                replaced = True
                path = self.directory / "data-000003.bin"
                path.rename(self.base / "owned-candidate")
                path.write_bytes(b"foreign")
                os.chmod(path, 0o600)
            return result
        with patch.object(storage.os, "fsync", side_effect=replace), self.assertRaises(storage.RecoveryRequired):
            instance.put_data(handle, "settings", b"intended", operation_id="data:1", now_unix=NOW)
        self.assertEqual((self.directory / "data-000003.bin").read_bytes(), b"foreign")
        self.assertEqual((self.base / "owned-candidate").read_bytes(), b"intended")

    def test_reentrant_publication_call_refused(self):
        instance = self.store()
        handle = self.install(instance)
        real = os.fsync
        observed = []
        def reenter(fd):
            if not observed:
                try:
                    instance.read_data(handle, "settings", now_unix=NOW)
                except storage.AppStorageError as error:
                    observed.append(str(error))
            return real(fd)
        with patch.object(storage.os, "fsync", side_effect=reenter):
            instance.put_data(handle, "settings", b"safe", operation_id="data:1", now_unix=NOW)
        self.assertEqual(observed, ["storage owner is not reentrant"])

    def test_cross_thread_use_and_forked_copy_refused(self):
        instance = self.store()
        handle = self.install(instance)
        errors = []
        def run():
            try:
                instance.asset_response(handle, ORIGIN + "/index.html", now_unix=NOW)
            except storage.AppStorageError:
                errors.append(True)
        thread = threading.Thread(target=run)
        thread.start()
        thread.join(5)
        self.assertEqual(errors, [True])
        child = os.fork()
        if child == 0:
            try:
                run()
                instance.close()  # Must not unlock the parent's shared flock.
                os._exit(0 if len(errors) == 2 else 2)
            except BaseException:
                os._exit(3)
        _, status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 0)
        with self.assertRaises(storage.AppStorageError):
            self.store()
        self.assertEqual(instance.asset_response(handle, ORIGIN + "/index.html", now_unix=NOW).body, b"<!doctype html>signed")

    def test_event_capacity_refuses_before_intent_and_keeps_close_possible(self):
        instance = self.store()
        handle = self.install(instance)
        before = set(self.directory.iterdir())
        with patch.object(storage, "MAX_EVENTS", instance._sequence), self.assertRaises(storage.AppStorageError):
            instance.put_data(handle, "settings", b"no", operation_id="data:1", now_unix=NOW)
        self.assertEqual(set(self.directory.iterdir()), before)
        self.reopen(instance).open_app("principal:a", ORIGIN, now_unix=NOW)

    def test_partition_data_quota_and_tombstone_key_capacity(self):
        instance = self.store()
        handle = self.install(instance)
        instance.put_data(handle, "first", b"1234", operation_id="data:1", now_unix=NOW)
        with patch.object(storage, "MAX_PARTITION_DATA_BYTES", 4), self.assertRaises(storage.AppStorageError):
            instance.put_data(handle, "second", b"x", operation_id="data:2", now_unix=NOW)
        instance.delete_data(handle, "first", operation_id="delete:1", now_unix=NOW)
        with patch.object(storage, "MAX_DATA_KEYS", 1), self.assertRaises(storage.AppStorageError):
            instance.put_data(handle, "second", b"x", operation_id="data:2", now_unix=NOW)

    def test_unknown_or_orphan_history_never_auto_repaired(self):
        instance = self.store()
        self.install(instance)
        instance.close()
        extra = self.directory / "data-000255.bin"
        extra.write_bytes(b"orphan")
        os.chmod(extra, 0o600)
        with self.assertRaises(storage.RecoveryRequired):
            self.store()
        self.assertEqual(extra.read_bytes(), b"orphan")

    def test_duplicate_json_and_historical_manifest_floor_mismatch_refuse(self):
        for attack in ("duplicate", "floor"):
            with self.subTest(attack=attack):
                location = self.base / attack
                location.mkdir(mode=0o700)
                instance = storage.AppStorage(location, admission=self.admission)
                self.stores.append(instance)
                self.install(instance)
                instance.close()
                intent = location / "event-000002.intent.json"
                commit = location / "event-000002.commit.json"
                if attack == "duplicate":
                    intent.write_bytes(b'{"schema":"x","schema":"y"}')
                else:
                    value = json.loads(intent.read_bytes())
                    value["event"]["app"]["version"] = "0.0.1"
                    payload = canonical(value)
                    intent.write_bytes(payload)
                    commit.write_bytes(canonical({"schema": storage.SCHEMA, "event": value["event"],
                        "intent_sha256": hashlib.sha256(payload).hexdigest()}))
                with self.assertRaises((storage.AppStorageError, apps.AppAdmissionError)):
                    storage.AppStorage(location, admission=self.admission)

    def test_contract_and_documentation_match_source_limits(self):
        contract = json.loads((ROOT / "contracts/app-storage.v1.json").read_text())
        self.assertEqual(contract["status"], "SOURCE_CANDIDATE")
        self.assertEqual(contract["limits"]["events"], storage.MAX_EVENTS)
        self.assertEqual(contract["limits"]["retained_store_bytes"], storage.MAX_STORE_BYTES)
        self.assertEqual(contract["limits"]["data_value_bytes"], storage.MAX_DATA_BYTES)
        self.assertFalse(contract["installed_engine_storage_enforcement"])
        self.assertFalse(contract["whole_directory_rollback_protection"])


if __name__ == "__main__":
    unittest.main()
