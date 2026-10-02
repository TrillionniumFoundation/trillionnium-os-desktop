from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import json
import os
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import warnings
import zipfile
import zlib
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("g5_trusted_apps", ROOT / "platform/trusted_apps.py")
assert spec is not None and spec.loader is not None
apps = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = apps
spec.loader.exec_module(apps)

NOW = 1000
ASSETS = {"index.html": b"<!doctype html><script src='app.js'></script>",
          "app.js": b"document.title = 'local';", "other.html": b"<!doctype html>other"}
KEYS = None
PUBLIC = {}


def command(arguments):
    return subprocess.run(["/usr/bin/openssl", *arguments], capture_output=True, check=True,
                          env={"PATH": "/usr/bin:/bin", "OPENSSL_CONF": "/dev/null", "LC_ALL": "C"})


def setUpModule():
    global KEYS
    if not Path("/usr/bin/openssl").is_file():
        raise RuntimeError("real system OpenSSL is required; missing crypto is not a skipped success")
    KEYS = tempfile.TemporaryDirectory(prefix="g5-real-ed25519-")
    directory = Path(KEYS.name)
    for name in ("approved", "other"):
        command(["genpkey", "-algorithm", "ED25519", "-out", str(directory / f"{name}.key")])
        der = command(["pkey", "-in", str(directory / f"{name}.key"), "-pubout", "-outform", "DER"]).stdout
        if not der.startswith(bytes.fromhex("302a300506032b6570032100")) or len(der) != 44:
            raise RuntimeError("unexpected real Ed25519 public key encoding")
        PUBLIC[name] = der[12:]


def tearDownModule():
    if KEYS is not None:
        KEYS.cleanup()
    PUBLIC.clear()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def preimage(value):
    # Independent test producer: domain and exclusion rule are literal wire values.
    unsigned = {**value, "signature": {key: item for key, item in value["signature"].items() if key != "value"}}
    return b"trillionnium.desktop.app-manifest-signature.v1\0" + canonical(unsigned)


def sign(value, *, key="approved", domain=None):
    value = json.loads(canonical(value))
    directory = Path(KEYS.name)
    message = preimage(value) if domain is None else domain + preimage(value).split(b"\0", 1)[1]
    (directory / "message").write_bytes(message)
    signature = command(["pkeyutl", "-sign", "-rawin", "-inkey", str(directory / f"{key}.key"),
                         "-in", str(directory / "message")]).stdout
    if len(signature) != 64:
        raise RuntimeError("real Ed25519 signer returned a non-64-byte signature")
    value["signature"]["value"] = base64.b64encode(signature).decode("ascii")
    return canonical(value)


def manifest(assets=None, **overrides):
    assets = ASSETS if assets is None else assets
    value = {
        "schema": apps.MANIFEST_SCHEMA, "publisher": "example", "app_id": "notes",
        "version": "1.2.3", "entrypoint": "index.html",
        "origin_host": "notes.example.apps.hepta.invalid",
        "content_root_sha256": apps.content_root_sha256(assets), "capabilities": [],
        "csp": apps.RESTRICTIVE_CSP, "minimum_shell_version": "1.0.0", "data_schema_version": 1,
        "signature": {"algorithm": "ed25519", "key_id": "publisher:test",
                      "value": base64.b64encode(bytes(64)).decode("ascii")},
    }
    value.update(overrides)
    return value


def root(*, key="approved", publisher="example", key_id="publisher:test", start=500, end=1500):
    public = PUBLIC[key]
    return apps.PublisherTrustRoot(publisher, key_id, public, hashlib.sha256(public).hexdigest(), start, end)


def policy(*, roots=None, revoked=(), revision=1, start=100, end=2000):
    return apps.PublisherTrustPolicy(revision, start, end, (root(),) if roots is None else roots, revoked)


def archive(*, payload=None, assets=None, entries=None, compression=zipfile.ZIP_DEFLATED, comment=b""):
    assets = ASSETS if assets is None else assets
    payload = sign(manifest(assets)) if payload is None else payload
    stream = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(stream, "w") as writer:
            rows = [(apps.MANIFEST_PATH, payload), *assets.items()] if entries is None else entries
            for name, content in rows:
                info = name if isinstance(name, zipfile.ZipInfo) else zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
                if not isinstance(name, zipfile.ZipInfo):
                    info.create_system = 3
                    info.external_attr = (stat.S_IFREG | 0o644) << 16
                info.compress_type = compression
                writer.writestr(info, content)
            writer.comment = comment
    return stream.getvalue()


def with_deflate_tail(payload, assets):
    # Classic ZIP producer with structurally indexed trailing compressed bytes.
    local = bytearray()
    central = bytearray()
    entries = [("manifest.json", payload), *assets.items()]
    for name, content in entries:
        encoder = zlib.compressobj(wbits=-15)
        encoded = encoder.compress(content) + encoder.flush()
        if name == "app.js":
            encoded += b"unindexed-extra-stream-bytes"
        name = name.encode("ascii")
        offset = len(local)
        crc = zlib.crc32(content)
        local += struct.pack("<4s5H3L2H", b"PK\x03\x04", 20, 0, 8, 0, 0, crc, len(encoded), len(content), len(name), 0)
        local += name + encoded
        central += struct.pack("<4s6H3L5H2L", b"PK\x01\x02", 20 | 3 << 8, 20, 0, 8, 0, 0,
                               crc, len(encoded), len(content), len(name), 0, 0, 0, 0,
                               (stat.S_IFREG | 0o644) << 16, offset)
        central += name
    return bytes(local + central + struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, len(entries), len(entries), len(central), len(local), 0))


class TrustedAppsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="g5-app-corpus-")
        self.directory = Path(self.temp.name)
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o700)
        self.owner = apps.TrustedAppAdmission(shell_version="1.2.3", policy=policy())

    def tearDown(self):
        self.temp.cleanup()

    def write(self, value):
        path = self.directory / "app.zip"
        path.write_bytes(value)
        return path

    def admit(self, value=None, *, owner=None, now=NOW):
        return (self.owner if owner is None else owner).admit_bundle_file(
            self.write(archive() if value is None else value), now_unix=now)

    def refuse(self, value):
        with self.assertRaises(apps.AppAdmissionError):
            self.admit(value)

    def test_real_ed25519_bundle_and_local_response(self):
        raw = archive()
        bundle = self.admit(raw)
        self.assertEqual(bundle.archive_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(bundle.content_root_sha256, apps.content_root_sha256(ASSETS))
        self.assertEqual(bundle.asset_paths, tuple(sorted(ASSETS)))
        self.assertEqual(bundle.entrypoint_url, "https://notes.example.apps.hepta.invalid/index.html")
        self.assertEqual(bundle.capabilities, ())
        response = self.owner.asset_response(bundle, bundle.entrypoint_url, now_unix=NOW)
        self.assertEqual((response.status, response.asset_path, response.body), (200, "index.html", ASSETS["index.html"]))
        self.assertEqual(response.headers["Content-Security-Policy"], apps.RESTRICTIVE_CSP)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_index_complete_canonical_domain_and_no_self_reference(self):
        expected = {"schema": "trillionnium.desktop.trusted-app-content-index.v1", "files": [
            {"path": name, "size": len(ASSETS[name]), "sha256": hashlib.sha256(ASSETS[name]).hexdigest()}
            for name in sorted(ASSETS)]}
        self.assertEqual(apps.content_index_bytes(dict(reversed(list(ASSETS.items())))), canonical(expected))
        expected_root = hashlib.sha256(b"trillionnium.desktop.trusted-app-content-index.v1\0" + canonical(expected)).hexdigest()
        self.assertEqual(apps.content_root_sha256(ASSETS), expected_root)
        with self.assertRaises(apps.AppAdmissionError):
            apps.content_index_bytes({**ASSETS, "manifest.json": b"self reference"})

    def test_manifest_preimage_excludes_only_value(self):
        value = manifest()
        self.assertEqual(apps.manifest_signing_bytes(canonical(value)), preimage(value))
        value["signature"]["value"] = base64.b64encode(b"x" * 64).decode()
        self.assertEqual(apps.manifest_signing_bytes(canonical(value)), preimage(manifest()))
        value["signature"]["key_id"] = "publisher:alias"
        self.assertNotEqual(apps.manifest_signing_bytes(canonical(value)), preimage(manifest()))
        self.assertIn(b'"algorithm":"ed25519"', apps.manifest_signing_bytes(canonical(value)))

    def test_wrong_real_key_and_domain_are_refused(self):
        self.refuse(archive(payload=sign(manifest(), key="other")))
        self.refuse(archive(payload=sign(manifest(), domain=b"other-domain\0")))

    def test_valid_metadata_mutations_invalidate_real_signature(self):
        original = json.loads(sign(manifest()))
        mutations = [
            {"version": "2.0.0"}, {"entrypoint": "other.html"},
            {"capabilities": ["clipboard.read"]}, {"minimum_shell_version": "1.0.1"},
            {"data_schema_version": 2},
            {"app_id": "other", "origin_host": "other.example.apps.hepta.invalid"},
            {"publisher": "other", "origin_host": "notes.other.apps.hepta.invalid"},
        ]
        self.owner.replace_policy(policy(revision=2, roots=(root(), root(publisher="other"))))
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.refuse(archive(payload=canonical({**original, **mutation})))

    def test_key_id_is_signed_even_when_alias_pins_same_real_key(self):
        self.owner.replace_policy(policy(revision=2, roots=(root(), root(key_id="publisher:alias"))))
        value = json.loads(sign(manifest()))
        value["signature"]["key_id"] = "publisher:alias"
        self.refuse(archive(payload=canonical(value)))

    def test_corrupt_and_noncanonical_signature_are_refused(self):
        value = json.loads(sign(manifest()))
        signature = bytearray(base64.b64decode(value["signature"]["value"]))
        signature[0] ^= 1
        value["signature"]["value"] = base64.b64encode(signature).decode()
        self.refuse(archive(payload=canonical(value)))
        for signature in ("x" * 88, base64.b64encode(bytes(63)).decode(),
                          base64.b64encode(bytes(64)).decode().rstrip("="), " " + value["signature"]["value"]):
            with self.subTest(signature=signature):
                value["signature"]["value"] = signature
                self.refuse(archive(payload=canonical(value)))

    def test_default_and_explicit_empty_roots_refuse(self):
        for owner in (apps.TrustedAppAdmission(shell_version="1.2.3"),
                      apps.TrustedAppAdmission(shell_version="1.2.3", policy=policy(roots=()))):
            with self.assertRaises(apps.AppAdmissionError):
                self.admit(owner=owner)

    def test_root_scope_unknown_key_and_pin_are_enforced(self):
        for roots in ((root(publisher="different"),), (root(key_id="different:key"),), (root(key="other"),)):
            with self.subTest(roots=roots):
                owner = apps.TrustedAppAdmission(shell_version="1.2.3", policy=policy(roots=roots))
                with self.assertRaises(apps.AppAdmissionError):
                    self.admit(owner=owner)
        with self.assertRaises(apps.AppAdmissionError):
            replace(root(), public_key_sha256="0" * 64)
        with self.assertRaises(apps.AppAdmissionError):
            replace(root(), public_key=bytearray(PUBLIC["approved"]))

    def test_policy_and_key_validity_are_half_open(self):
        raw = archive()
        for now in (499, 1500, 2000, True, -1):
            with self.subTest(now=now), self.assertRaises(apps.AppAdmissionError):
                self.admit(raw, now=now)
        self.admit(raw, now=500)
        self.admit(raw, now=1499)
        owner = apps.TrustedAppAdmission(shell_version="1.2.3", policy=policy(start=1100))
        with self.assertRaises(apps.AppAdmissionError):
            self.admit(raw, owner=owner)

    def test_revocation_invalidates_already_admitted_asset_snapshot(self):
        bundle = self.admit()
        self.owner.replace_policy(policy(revision=2, revoked=(("example", "publisher:test"),)))
        with self.assertRaises(apps.AppAdmissionError):
            self.owner.asset_response(bundle, bundle.entrypoint_url, now_unix=NOW)
        with self.assertRaises(apps.AppAdmissionError):
            self.admit()

    def test_revoked_policy_replay_removal_and_key_rebinding_refuse(self):
        revoked = policy(revision=2, revoked=(("example", "publisher:test"),))
        self.owner.replace_policy(revoked)
        for candidate in (policy(), revoked, policy(revision=3),
                          policy(revision=3, roots=(root(key="other"),), revoked=revoked.revoked_keys)):
            with self.subTest(candidate=candidate), self.assertRaises(apps.AppAdmissionError):
                self.owner.replace_policy(candidate)
        with self.assertRaises(apps.AppAdmissionError):
            self.admit()

    def test_rotation_uses_new_key_id_and_current_policy_on_every_asset(self):
        old = self.admit()
        next_root = root(key="other", key_id="publisher:next")
        self.owner.replace_policy(policy(revision=2, roots=(next_root,)))
        with self.assertRaises(apps.AppAdmissionError):
            self.owner.asset_response(old, old.entrypoint_url, now_unix=NOW)
        value = manifest(signature={"algorithm": "ed25519", "key_id": "publisher:next",
                                    "value": base64.b64encode(bytes(64)).decode()})
        new = self.admit(archive(payload=sign(value, key="other")))
        self.assertEqual(self.owner.asset_response(new, new.entrypoint_url, now_unix=NOW).body, ASSETS["index.html"])
        with self.assertRaises(apps.AppAdmissionError):
            self.owner.asset_response(new, new.entrypoint_url, now_unix=1500)

    def test_ambiguous_and_invalid_trust_snapshots_refuse(self):
        for arguments in ({"roots": (root(), root())}, {"revoked_keys": (("example", "publisher:test"),) * 2},
                          {"revision": True}, {"valid_until_unix": 100}, {"roots": [root()]}):
            with self.subTest(arguments=arguments), self.assertRaises(apps.AppAdmissionError):
                replace(policy(), **arguments)

    def test_exact_origin_csp_and_minimum_shell_are_signed_admission_constraints(self):
        for mutation in ({"origin_host": "other.example.apps.hepta.invalid"},
                         {"origin_host": "shell.system.hepta.invalid"}, {"csp": "default-src * 'unsafe-inline'"},
                         {"minimum_shell_version": "2.0.0"}, {"entrypoint": "missing.html"},
                         {"version": "1.0.0-01"}, {"signature": {"algorithm": "rsa", "key_id": "publisher:test", "value": "x" * 88}}):
            with self.subTest(mutation=mutation):
                self.refuse(archive(payload=sign(manifest(**mutation))))

    def test_unknown_duplicate_noncanonical_and_noninteger_manifest_json(self):
        signed = sign(manifest())
        variants = [signed + b"\n", b' {"unexpected":true}',
                    b'{"schema":"first",' + signed[1:],
                    canonical({**json.loads(signed), "trust_roots": []}),
                    canonical({**json.loads(signed), "data_schema_version": True}),
                    signed.replace(b'"data_schema_version":1', b'"data_schema_version":1.0'),
                    signed.replace(b'"data_schema_version":1', b'"data_schema_version":NaN'),
                    signed.replace(b'"data_schema_version":1', b'"data_schema_version":' + b"9" * 100),
                    b"[" * 2000 + b"]" * 2000]
        for value in variants:
            with self.subTest(payload=value[:70]):
                self.refuse(archive(payload=value))

    def test_entire_signed_index_rejects_added_removed_and_modified_assets(self):
        signed = sign(manifest())
        for assets in ({**ASSETS, "extra.js": b"extra"},
                       {name: value for name, value in ASSETS.items() if name != "other.html"},
                       {**ASSETS, "app.js": b"document.title = 'changed';"}):
            with self.subTest(paths=list(assets)):
                self.refuse(archive(payload=signed, assets=assets))

    def test_portable_path_corpus(self):
        signed = sign(manifest())
        bad_paths = ("../x.js", "a/../x.js", "a//x.js", "/x.js", "C:/x.js", "a\\x.js", "a%2fx.js",
                     "a/./x.js", "a./x.js", "CON.html", "a/NUL.txt", "é.js", "dir/", ".hidden.js", "a space.js")
        for path in bad_paths:
            with self.subTest(path=path):
                self.refuse(archive(entries=[("manifest.json", signed), *ASSETS.items(), (path, b"bad")]))

    def test_duplicate_case_and_file_directory_collisions(self):
        signed = sign(manifest())
        for extra in (("manifest.json", signed), ("Manifest.json", signed), ("index.html", b"other"),
                      ("INDEX.html", b"other"), ("app.js/child.html", b"child")):
            with self.subTest(extra=extra[0]):
                self.refuse(archive(entries=[("manifest.json", signed), *ASSETS.items(), extra]))

    def test_symlink_device_fifo_setuid_and_directory_records_refuse(self):
        signed = sign(manifest())
        for mode in (stat.S_IFLNK | 0o777, stat.S_IFIFO | 0o600, stat.S_IFCHR | 0o600,
                     stat.S_IFREG | 0o4644, stat.S_IFDIR | 0o700):
            info = zipfile.ZipInfo("hostile.js", (2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = mode << 16
            with self.subTest(mode=mode):
                self.refuse(archive(entries=[("manifest.json", signed), *ASSETS.items(), (info, b"target")]))

    def test_no_unindexed_preamble_suffix_comment_or_deflate_tail(self):
        raw = archive()
        for value in (b"preamble" + raw, raw + b"trailing", archive(comment=b"comment"),
                      with_deflate_tail(sign(manifest()), ASSETS)):
            with self.subTest(size=len(value)):
                self.refuse(value)

    def test_local_central_crc_and_disk_mismatches_refuse(self):
        raw = archive(compression=zipfile.ZIP_STORED)
        variants = []
        value = bytearray(raw)
        struct.pack_into("<L", value, 14, struct.unpack_from("<L", value, 14)[0] ^ 1)
        variants.append(bytes(value))
        value = bytearray(raw)
        central = value.index(b"PK\x01\x02")
        crc = struct.unpack_from("<L", value, 14)[0] ^ 1
        struct.pack_into("<L", value, 14, crc)
        struct.pack_into("<L", value, central + 16, crc)
        variants.append(bytes(value))
        value = bytearray(raw)
        struct.pack_into("<H", value, len(value) - 18, 1)
        variants.append(bytes(value))
        value = bytearray(raw)
        struct.pack_into("<L", value, central + 42, 1)
        variants.append(bytes(value))
        for value in variants:
            self.refuse(value)

    def test_zip64_extra_data_descriptor_encryption_and_other_compression_refuse(self):
        signed = sign(manifest())
        info = zipfile.ZipInfo("extra.js", (2026, 1, 1, 0, 0, 0))
        info.extra = b"\x99\x99\x00\x00"
        self.refuse(archive(entries=[("manifest.json", signed), *ASSETS.items(), (info, b"extra")]))
        self.refuse(archive(compression=zipfile.ZIP_BZIP2))
        raw = bytearray(archive())
        struct.pack_into("<H", raw, 6, 1)
        struct.pack_into("<H", raw, raw.index(b"PK\x01\x02") + 8, 1)
        self.refuse(bytes(raw))
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as writer:
            with writer.open("manifest.json", "w", force_zip64=True) as member:
                member.write(signed)
            writer.writestr("index.html", ASSETS["index.html"])
        self.refuse(stream.getvalue())
        class NonSeeking(io.BytesIO):
            def seek(self, *args):
                raise OSError("streaming writer")
        stream = NonSeeking()
        with zipfile.ZipFile(stream, "w") as writer:
            writer.writestr("manifest.json", signed)
            writer.writestr("index.html", ASSETS["index.html"])
        self.refuse(stream.getvalue())

    def test_decompression_bomb_declared_size_and_entry_count_bound(self):
        signed = sign(manifest())
        self.refuse(archive(entries=[("manifest.json", signed), *ASSETS.items(), ("bomb.bin", b"0" * 1_000_000)]))
        raw = bytearray(archive())
        central = raw.index(b"PK\x01\x02")
        struct.pack_into("<L", raw, central + 24, 0xFFFFFFFF)
        self.refuse(bytes(raw))
        self.refuse(archive(entries=[("manifest.json", signed), *[(f"f{number}.js", b"x") for number in range(apps.MAX_ASSETS + 1)]]))

    def test_archive_and_manifest_byte_bound(self):
        path = self.directory / "large.zip"
        with path.open("wb") as stream:
            stream.truncate(apps.MAX_ARCHIVE_BYTES + 1)
        with self.assertRaises(apps.AppAdmissionError):
            self.owner.admit_bundle_file(path, now_unix=NOW)
        self.refuse(archive(payload=b" " * (apps.MAX_MANIFEST_BYTES + 1), compression=zipfile.ZIP_STORED))

    def test_nofollow_leaf_ancestor_hardlink_and_fifo_custody(self):
        actual = self.write(archive())
        leaf = self.directory / "leaf.zip"
        leaf.symlink_to(actual)
        ancestor = self.directory / "ancestor"
        ancestor.symlink_to(self.directory, target_is_directory=True)
        for path in (leaf, ancestor / "app.zip"):
            with self.subTest(path=path), self.assertRaises(apps.AppAdmissionError):
                self.owner.admit_bundle_file(path, now_unix=NOW)
        hard = self.directory / "hard.zip"
        os.link(actual, hard)
        with self.assertRaises(apps.AppAdmissionError):
            self.owner.admit_bundle_file(actual, now_unix=NOW)
        fifo = self.directory / "fifo"
        os.mkfifo(fifo)
        with self.assertRaises(apps.AppAdmissionError):
            self.owner.admit_bundle_file(fifo, now_unix=NOW)

    def test_noncanonical_filesystem_paths_refuse(self):
        path = self.write(archive())
        for candidate in (None, 123, b"/tmp/app.zip", "app.zip", "", str(path.parent) + "/../app.zip",
                          str(path.parent) + "//app.zip", str(path.parent) + "/./app.zip"):
            with self.subTest(candidate=candidate), self.assertRaises(apps.AppAdmissionError):
                self.owner.admit_bundle_file(candidate, now_unix=NOW)

    def test_owner_refuses_cross_thread_and_forked_copy(self):
        bundle = self.admit()
        errors = []
        def worker():
            for operation in (lambda: self.owner.replace_policy(policy(revision=2)),
                              lambda: self.owner.admit_bundle_file(self.directory / "app.zip", now_unix=NOW),
                              lambda: self.owner.asset_response(bundle, bundle.entrypoint_url, now_unix=NOW)):
                try:
                    operation()
                except apps.AppAdmissionError:
                    errors.append(True)
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [True, True, True])
        child = os.fork()
        if child == 0:
            try:
                self.owner.asset_response(bundle, bundle.entrypoint_url, now_unix=NOW)
            except apps.AppAdmissionError:
                os._exit(0)
            except BaseException:
                os._exit(2)
            os._exit(1)
        self.assertEqual(os.waitpid(child, 0)[1], 0)
        self.assertEqual(self.owner.asset_response(bundle, bundle.entrypoint_url, now_unix=NOW).body, ASSETS["index.html"])

    def test_stored_and_deflated_empty_nested_assets_are_served_exactly(self):
        assets = {"index.html": b"<!doctype html>", "nested/empty.bin": b"", "nested/A.JS": b"local();"}
        for compression in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            with self.subTest(compression=compression):
                bundle = self.admit(archive(assets=assets, compression=compression))
                url = f"https://{bundle.origin_host}/nested/empty.bin"
                response = self.owner.asset_response(bundle, url, now_unix=NOW)
                self.assertEqual((response.asset_path, response.body, response.headers["Content-Length"]),
                                 ("nested/empty.bin", b"", "0"))
                self.assertEqual(response.headers["Content-Type"], "application/octet-stream")
                url = f"https://{bundle.origin_host}/nested/A.JS"
                self.assertEqual(self.owner.asset_response(bundle, url, now_unix=NOW).body, b"local();")
                with self.assertRaises(apps.AppAdmissionError):
                    self.owner.asset_response(bundle, url.replace("A.JS", "a.js"), now_unix=NOW)

    def test_snapshot_refuses_same_size_mutation_and_path_replacement(self):
        raw = archive()
        actual_read = os.read
        for replacement in (False, True):
            path = self.write(raw)
            invoked = False
            def racing_read(fd, count):
                nonlocal invoked
                content = actual_read(fd, count)
                if not invoked:
                    invoked = True
                    if replacement:
                        other = self.directory / "replacement.zip"
                        other.write_bytes(raw)
                        os.replace(other, path)
                    else:
                        with path.open("r+b") as stream:
                            stream.write(b"XXXX")
                return content
            with self.subTest(replacement=replacement), patch.object(apps.os, "read", side_effect=racing_read):
                with self.assertRaises(apps.AppAdmissionError):
                    self.owner.admit_bundle_file(path, now_unix=NOW)
            self.assertTrue(invoked)

    def test_admitted_bytes_do_not_reopen_mutable_archive(self):
        bundle = self.admit()
        (self.directory / "app.zip").write_bytes(b"invalid replacement")
        response = self.owner.asset_response(bundle, bundle.entrypoint_url, now_unix=NOW)
        self.assertEqual(response.body, ASSETS["index.html"])
        with self.assertRaises(FrozenInstanceError):
            bundle.origin_host = "attacker.invalid"
        with self.assertRaises(TypeError):
            bundle._assets["index.html"] = b"mutated"
        with self.assertRaises(TypeError):
            response.headers["Content-Security-Policy"] = "unsafe"
        with self.assertRaises(apps.AppAdmissionError):
            apps.VerifiedAppBundle()

    def test_exact_local_url_and_method_corpus(self):
        bundle = self.admit()
        origin = "https://notes.example.apps.hepta.invalid/"
        urls = ["http://notes.example.apps.hepta.invalid/index.html", "HTTPS://notes.example.apps.hepta.invalid/index.html",
                "https://NOTES.example.apps.hepta.invalid/index.html", "https://notes.example.apps.hepta.invalid:443/index.html",
                "https://user@notes.example.apps.hepta.invalid/index.html", "https://notes.example.apps.hepta.invalid.evil/index.html",
                "https://other.example.apps.hepta.invalid/index.html", "https://shell.system.hepta.invalid/index.html",
                "https://example.com/index.html", origin + "../index.html", origin + "x/../index.html",
                origin + "%2e%2e/index.html", origin + "x%2findex.html", origin + "%69ndex.html",
                origin + "index.html?", origin + "index.html?x=1", origin + "index.html#", origin + "index.html#x",
                origin + "index.html\\x", origin + "index.html\n", origin + "missing.js", origin + "manifest.json", origin]
        for url in urls:
            with self.subTest(url=url), self.assertRaises(apps.AppAdmissionError):
                self.owner.asset_response(bundle, url, now_unix=NOW)
        for method in ("HEAD", "POST", "OPTIONS", "get"):
            with self.subTest(method=method), self.assertRaises(apps.AppAdmissionError):
                self.owner.asset_response(bundle, bundle.entrypoint_url, now_unix=NOW, method=method)
        foreign = apps.TrustedAppAdmission(shell_version="1.2.3", policy=policy())
        with self.assertRaises(apps.AppAdmissionError):
            foreign.asset_response(bundle, bundle.entrypoint_url, now_unix=NOW)

    def test_unknown_and_native_executable_extensions_have_no_asset_response(self):
        assets = {**ASSETS, "native.exe": b"MZ-executable", "server.cgi": b"#!/bin/sh", "unknown.xyz": b"unknown"}
        bundle = self.admit(archive(assets=assets))
        for path in ("native.exe", "server.cgi", "unknown.xyz"):
            with self.subTest(path=path), self.assertRaises(apps.AppAdmissionError):
                self.owner.asset_response(bundle, f"https://{bundle.origin_host}/{path}", now_unix=NOW)

    def test_offline_verifier_failure_is_refusal_not_fake_success(self):
        raw = archive()
        with patch.object(apps.subprocess, "run", side_effect=FileNotFoundError("OpenSSL missing")):
            with self.assertRaises(apps.AppAdmissionError):
                self.admit(raw)
        with patch.object(apps.subprocess, "run", side_effect=subprocess.TimeoutExpired("openssl", 5)):
            with self.assertRaises(apps.AppAdmissionError):
                self.admit(raw)

    def test_openssl_inputs_are_sealed_and_environment_is_fixed(self):
        raw = archive()
        actual_run = subprocess.run
        observed = []
        def inspecting_run(arguments, **kwargs):
            self.assertEqual(arguments[0], "/usr/bin/openssl")
            self.assertEqual(kwargs["env"], {"PATH": "/usr/bin:/bin", "OPENSSL_CONF": "/dev/null", "LC_ALL": "C"})
            self.assertEqual(len(kwargs["pass_fds"]), 3)
            for fd in kwargs["pass_fds"]:
                with self.assertRaises(OSError):
                    os.write(fd, b"mutable")
            observed.append(True)
            return actual_run(arguments, **kwargs)
        with patch.object(apps.subprocess, "run", side_effect=inspecting_run):
            self.admit(raw)
        self.assertEqual(observed, [True])

    def test_reentrant_revocation_refuses_without_corrupting_owner(self):
        raw = archive()
        actual_run = subprocess.run
        revoked = policy(revision=2, revoked=(("example", "publisher:test"),))
        def reenter(arguments, **kwargs):
            with self.assertRaises(apps.AppAdmissionError):
                self.owner.replace_policy(revoked)
            return actual_run(arguments, **kwargs)
        with patch.object(apps.subprocess, "run", side_effect=reenter):
            bundle = self.admit(raw)
        self.owner.replace_policy(revoked)
        with self.assertRaises(apps.AppAdmissionError):
            self.owner.asset_response(bundle, bundle.entrypoint_url, now_unix=NOW)
        # Failure also clears the guard: a newer cumulative policy remains possible.
        self.owner.replace_policy(replace(revoked, revision=3))

    def test_contract_matches_source_limits_and_signature_rules(self):
        contract = json.loads((ROOT / "contracts/trusted-app-bundle.v1.json").read_text())
        self.assertEqual(contract["manifest"]["signing_domain_utf8"].encode(), apps.MANIFEST_DOMAIN)
        self.assertEqual(contract["content_index"]["hash_domain_utf8"].encode(), apps.CONTENT_DOMAIN)
        self.assertEqual(contract["local_response"]["content_security_policy"], apps.RESTRICTIVE_CSP)
        self.assertEqual(set(contract["local_response"]["supported_extensions"]), set(apps._MIME))
        expected = {"archive_bytes": apps.MAX_ARCHIVE_BYTES, "content_bytes": apps.MAX_CONTENT_BYTES,
                    "asset_bytes": apps.MAX_ASSET_BYTES, "manifest_bytes": apps.MAX_MANIFEST_BYTES,
                    "asset_count": apps.MAX_ASSETS, "compression_ratio": apps.MAX_COMPRESSION_RATIO,
                    "path_characters": 512, "segment_characters": 128}
        self.assertEqual(contract["limits"], expected)
        schema = json.loads((ROOT / "contracts/app-manifest.v1.schema.json").read_text())
        self.assertEqual(set(schema["required"]), set(manifest()) - {"data_schema_version"})
        self.assertEqual(schema["properties"]["signature"]["properties"]["algorithm"]["enum"], ["ed25519"])


if __name__ == "__main__":
    unittest.main()
