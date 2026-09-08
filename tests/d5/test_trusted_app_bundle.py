from __future__ import annotations

import base64
import copy
import json
import os
import sys
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from trusted_app_bundle import (  # noqa: E402
    VerificationError,
    build_fixture_manifest,
    canonical_json,
    content_root,
    ed25519_public_from_seed,
    ed25519_sign_fixture,
    ed25519_verify,
    signed_manifest_payload,
    transition_payload,
    verify_bundle,
)
from trusted_app_indicator import IndicatorError, verify_trust_indicator  # noqa: E402


SEED_1 = bytes.fromhex(
    "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
)
SEED_2 = bytes.fromhex(
    "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb"
)


class TrustedAppBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(
            (ROOT / "contracts/trusted-app-bundle.v1.json").read_text()
        )

    def base_content(self) -> dict[str, bytes]:
        return {
            "index.html": b"<!doctype html><meta charset=utf-8><script src=app.js></script>",
            "app.js": b"globalThis.trillionniumFixture = true;\n",
        }

    def write_content(self, root: Path, content: dict[str, bytes]) -> None:
        for relative, value in content.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)

    def trust_store(
        self,
        manifest: dict,
        key_records: dict[str, tuple[bytes, str]] | None = None,
        *,
        revocation_epoch: int = 1,
        revoked_bundles: list[str] | None = None,
    ) -> dict:
        if key_records is None:
            key_records = {
                manifest["publisher_key_id"]: (
                    ed25519_public_from_seed(SEED_1),
                    "active",
                )
            }
        return {
            "schema": "trillionnium.desktop.trust-store.v1",
            "revocation_epoch": revocation_epoch,
            "generated_at_epoch": 1,
            "expires_at_epoch": 1000,
            "publishers": {
                manifest["publisher_id"]: {
                    "keys": {
                        key_id: {
                            "status": status,
                            "public_key_base64": base64.b64encode(public_key).decode(),
                        }
                        for key_id, (public_key, status) in key_records.items()
                    }
                }
            },
            "revoked_bundle_digests": revoked_bundles or [],
        }

    def resign(self, manifest: dict, seed: bytes = SEED_1) -> None:
        manifest["signature"]["value_base64"] = base64.b64encode(
            ed25519_sign_fixture(seed, signed_manifest_payload(manifest))
        ).decode()

    def verify(
        self,
        manifest: dict,
        content: dict[str, bytes],
        trust: dict | None = None,
        install_state: dict | None = None,
    ) -> dict:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_content(root, content)
            return verify_bundle(
                manifest,
                root,
                trust or self.trust_store(manifest),
                self.contract,
                install_state=install_state,
                now_epoch=100,
            )

    def assert_rejected(self, reason: str, callback) -> None:
        with self.assertRaises(VerificationError) as captured:
            callback()
        self.assertEqual(captured.exception.reason, reason)

    def test_rfc8032_vector_1(self) -> None:
        public_key = bytes.fromhex(
            "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
        )
        signature = bytes.fromhex(
            "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
            "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
        )
        self.assertEqual(ed25519_public_from_seed(SEED_1), public_key)
        self.assertEqual(ed25519_sign_fixture(SEED_1, b""), signature)
        self.assertTrue(ed25519_verify(public_key, b"", signature))
        altered = bytearray(signature)
        altered[0] ^= 1
        self.assertFalse(ed25519_verify(public_key, b"", bytes(altered)))

    def test_valid_offline_bundle_and_indicator(self) -> None:
        content = self.base_content()
        manifest, _ = build_fixture_manifest(self.contract, content, seed=SEED_1)
        result = self.verify(manifest, content)
        self.assertEqual(result["status"], "PASS_OFFLINE_REFERENCE_VERIFICATION")
        self.assertFalse(result["network_used"])
        verify_trust_indicator(result["trust_indicator"])

    def test_content_byte_tamper_is_rejected(self) -> None:
        content = self.base_content()
        manifest, _ = build_fixture_manifest(self.contract, content, seed=SEED_1)
        tampered = dict(content)
        tampered["app.js"] += b"tamper"
        self.assert_rejected(
            "CONTENT_DIGEST_MISMATCH", lambda: self.verify(manifest, tampered)
        )

    def test_manifest_tamper_without_resigning_is_rejected(self) -> None:
        content = self.base_content()
        manifest, _ = build_fixture_manifest(self.contract, content, seed=SEED_1)
        manifest["version"] = 2
        self.assert_rejected(
            "MANIFEST_SIGNATURE_REJECTED", lambda: self.verify(manifest, content)
        )

    def test_signature_tamper_is_rejected(self) -> None:
        content = self.base_content()
        manifest, _ = build_fixture_manifest(self.contract, content, seed=SEED_1)
        signature = bytearray(base64.b64decode(manifest["signature"]["value_base64"]))
        signature[-1] ^= 1
        manifest["signature"]["value_base64"] = base64.b64encode(signature).decode()
        self.assert_rejected(
            "MANIFEST_SIGNATURE_REJECTED", lambda: self.verify(manifest, content)
        )

    def test_missing_and_extra_content_are_rejected(self) -> None:
        content = self.base_content()
        manifest, _ = build_fixture_manifest(self.contract, content, seed=SEED_1)
        missing = dict(content)
        missing.pop("app.js")
        self.assert_rejected(
            "CONTENT_SET_MISMATCH", lambda: self.verify(manifest, missing)
        )
        extra = dict(content)
        extra["extra.txt"] = b"not signed"
        self.assert_rejected(
            "CONTENT_SET_MISMATCH", lambda: self.verify(manifest, extra)
        )

    def test_path_traversal_is_rejected_even_when_signed(self) -> None:
        content = self.base_content()
        manifest, _ = build_fixture_manifest(self.contract, content, seed=SEED_1)
        manifest["content"][0]["path"] = "../index.html"
        manifest["content_root_sha256"] = content_root(manifest["content"])
        self.resign(manifest)
        self.assert_rejected(
            "CONTENT_PATH_TRAVERSAL", lambda: self.verify(manifest, content)
        )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_symlink_is_rejected(self) -> None:
        content = self.base_content()
        manifest, _ = build_fixture_manifest(self.contract, content, seed=SEED_1)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_content(root, content)
            (root / "app.js").unlink()
            os.symlink("index.html", root / "app.js")
            self.assert_rejected(
                "CONTENT_SYMLINK_REJECTED",
                lambda: verify_bundle(
                    manifest,
                    root,
                    self.trust_store(manifest),
                    self.contract,
                    now_epoch=100,
                ),
            )

    def test_content_root_is_order_independent(self) -> None:
        content = self.base_content()
        manifest, _ = build_fixture_manifest(self.contract, content, seed=SEED_1)
        self.assertEqual(
            content_root(manifest["content"]),
            content_root(list(reversed(manifest["content"]))),
        )

    def test_signed_unsafe_csp_is_rejected(self) -> None:
        content = self.base_content()
        manifest, _ = build_fixture_manifest(self.contract, content, seed=SEED_1)
        for value, reason in [
            (manifest["csp"].replace("script-src 'self'", "script-src 'self' 'unsafe-eval'"), "CSP_VALUE_MISMATCH"),
            (manifest["csp"].replace("connect-src 'none'", "connect-src https://example.com"), "CSP_VALUE_MISMATCH"),
            (manifest["csp"].replace("img-src 'self' data:", "img-src *"), "CSP_VALUE_MISMATCH"),
        ]:
            candidate = copy.deepcopy(manifest)
            candidate["csp"] = value
            self.resign(candidate)
            self.assert_rejected(reason, lambda candidate=candidate: self.verify(candidate, content))

    def test_synthetic_origin_mismatch_is_rejected(self) -> None:
        content = self.base_content()
        manifest, _ = build_fixture_manifest(self.contract, content, seed=SEED_1)
        manifest["synthetic_origin"] = "https://example.com/"
        self.resign(manifest)
        self.assert_rejected(
            "SYNTHETIC_ORIGIN_MISMATCH", lambda: self.verify(manifest, content)
        )

    def test_lower_version_and_same_version_content_change_are_rejected(self) -> None:
        content = self.base_content()
        first, _ = build_fixture_manifest(
            self.contract, content, seed=SEED_1, version=2
        )
        first_result = self.verify(first, content)
        lower, _ = build_fixture_manifest(
            self.contract, content, seed=SEED_1, version=1
        )
        self.assert_rejected(
            "VERSION_DOWNGRADE_REJECTED",
            lambda: self.verify(
                lower, content, install_state=first_result["install_state"]
            ),
        )
        changed_content = dict(content)
        changed_content["app.js"] = b"changed\n"
        changed, _ = build_fixture_manifest(
            self.contract, changed_content, seed=SEED_1, version=2
        )
        self.assert_rejected(
            "SAME_VERSION_CONTENT_OR_KEY_CHANGED",
            lambda: self.verify(
                changed,
                changed_content,
                install_state=first_result["install_state"],
            ),
        )

    def test_revoked_key_and_bundle_are_rejected(self) -> None:
        content = self.base_content()
        manifest, public = build_fixture_manifest(
            self.contract, content, seed=SEED_1
        )
        revoked_key = self.trust_store(
            manifest, {manifest["publisher_key_id"]: (public, "revoked")}
        )
        self.assert_rejected(
            "PUBLISHER_KEY_NOT_ACTIVE",
            lambda: self.verify(manifest, content, trust=revoked_key),
        )
        manifest_digest = __import__("hashlib").sha256(canonical_json(manifest)).hexdigest()
        revoked_bundle = self.trust_store(
            manifest, revoked_bundles=[manifest_digest]
        )
        self.assert_rejected(
            "BUNDLE_REVOKED",
            lambda: self.verify(manifest, content, trust=revoked_bundle),
        )

    def test_stale_revocation_snapshot_is_rejected(self) -> None:
        content = self.base_content()
        manifest, _ = build_fixture_manifest(self.contract, content, seed=SEED_1)
        result = self.verify(manifest, content)
        state = copy.deepcopy(result["install_state"])
        state["revocation_epoch"] = 2
        trust = self.trust_store(manifest, revocation_epoch=1)
        self.assert_rejected(
            "STALE_REVOCATION_SNAPSHOT",
            lambda: self.verify(manifest, content, trust=trust, install_state=state),
        )

    def test_valid_cross_signed_key_rotation(self) -> None:
        content = self.base_content()
        first, public_1 = build_fixture_manifest(
            self.contract, content, seed=SEED_1, key_id="fixture-key-1", version=1
        )
        first_result = self.verify(first, content)
        public_2 = ed25519_public_from_seed(SEED_2)
        transition = {
            "schema": "trillionnium.desktop.publisher-key-transition.v1",
            "from_key_id": "fixture-key-1",
            "to_key_id": "fixture-key-2",
            "to_public_key_sha256": __import__("hashlib").sha256(public_2).hexdigest(),
            "minimum_version": 2,
            "signature_by_from_key": "",
        }
        transition["signature_by_from_key"] = base64.b64encode(
            ed25519_sign_fixture(SEED_1, transition_payload(transition))
        ).decode()
        second, _ = build_fixture_manifest(
            self.contract,
            content,
            seed=SEED_2,
            key_id="fixture-key-2",
            version=2,
            key_transition=transition,
        )
        trust = self.trust_store(
            second,
            {
                "fixture-key-1": (public_1, "active"),
                "fixture-key-2": (public_2, "active"),
            },
            revocation_epoch=2,
        )
        result = self.verify(
            second,
            content,
            trust=trust,
            install_state=first_result["install_state"],
        )
        self.assertEqual(result["install_state"]["publisher_key_id"], "fixture-key-2")

    def test_unauthorized_or_revoked_predecessor_rotation_is_rejected(self) -> None:
        content = self.base_content()
        first, public_1 = build_fixture_manifest(
            self.contract, content, seed=SEED_1, key_id="fixture-key-1", version=1
        )
        first_result = self.verify(first, content)
        public_2 = ed25519_public_from_seed(SEED_2)
        transition = {
            "schema": "trillionnium.desktop.publisher-key-transition.v1",
            "from_key_id": "fixture-key-1",
            "to_key_id": "fixture-key-2",
            "to_public_key_sha256": __import__("hashlib").sha256(public_2).hexdigest(),
            "minimum_version": 2,
            "signature_by_from_key": "",
        }
        transition["signature_by_from_key"] = base64.b64encode(
            ed25519_sign_fixture(SEED_2, transition_payload(transition))
        ).decode()
        second, _ = build_fixture_manifest(
            self.contract,
            content,
            seed=SEED_2,
            key_id="fixture-key-2",
            version=2,
            key_transition=transition,
        )
        active_trust = self.trust_store(
            second,
            {
                "fixture-key-1": (public_1, "active"),
                "fixture-key-2": (public_2, "active"),
            },
            revocation_epoch=2,
        )
        self.assert_rejected(
            "KEY_TRANSITION_SIGNATURE_REJECTED",
            lambda: self.verify(
                second,
                content,
                trust=active_trust,
                install_state=first_result["install_state"],
            ),
        )
        transition["signature_by_from_key"] = base64.b64encode(
            ed25519_sign_fixture(SEED_1, transition_payload(transition))
        ).decode()
        second, _ = build_fixture_manifest(
            self.contract,
            content,
            seed=SEED_2,
            key_id="fixture-key-2",
            version=2,
            key_transition=transition,
        )
        revoked_trust = self.trust_store(
            second,
            {
                "fixture-key-1": (public_1, "revoked"),
                "fixture-key-2": (public_2, "active"),
            },
            revocation_epoch=2,
        )
        self.assert_rejected(
            "PUBLISHER_KEY_NOT_ACTIVE",
            lambda: self.verify(
                second,
                content,
                trust=revoked_trust,
                install_state=first_result["install_state"],
            ),
        )

    def test_service_worker_must_be_signed_and_scoped(self) -> None:
        content = self.base_content()
        manifest, _ = build_fixture_manifest(self.contract, content, seed=SEED_1)
        unsigned_script = copy.deepcopy(manifest)
        unsigned_script["service_worker"] = {
            "enabled": True,
            "script": "worker.js",
            "scope": "/",
            "network_fetch": False,
            "update_source": "signed_bundle_only",
        }
        self.resign(unsigned_script)
        self.assert_rejected(
            "SERVICE_WORKER_SCRIPT_NOT_SIGNED",
            lambda: self.verify(unsigned_script, content),
        )
        with_worker = dict(content)
        with_worker["worker.js"] = b"self.addEventListener('fetch',()=>{});\n"
        scoped, _ = build_fixture_manifest(
            self.contract, with_worker, seed=SEED_1
        )
        scoped["service_worker"] = {
            "enabled": True,
            "script": "worker.js",
            "scope": "/../escape",
            "network_fetch": False,
            "update_source": "signed_bundle_only",
        }
        self.resign(scoped)
        self.assert_rejected(
            "SERVICE_WORKER_SCOPE_REJECTED",
            lambda: self.verify(scoped, with_worker),
        )

    def test_trust_indicator_tamper_is_rejected(self) -> None:
        content = self.base_content()
        manifest, _ = build_fixture_manifest(self.contract, content, seed=SEED_1)
        result = self.verify(manifest, content)
        indicator = copy.deepcopy(result["trust_indicator"])
        indicator["version"] += 1
        with self.assertRaisesRegex(IndicatorError, "TRUST_INDICATOR_HASH_MISMATCH"):
            verify_trust_indicator(indicator)


if __name__ == "__main__":
    unittest.main()
