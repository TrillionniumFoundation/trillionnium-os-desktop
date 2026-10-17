"""Source-only A09/HOS2 ResourceDomain identity compatibility regression.

Not an A05 CapSpace grant test, a DMA access test or a Rust compile test.
"""
from pathlib import Path
import tempfile
import unittest


def compatibility_errors(host, a09):
    errors = []
    if "pub struct Id16([u8; 16]);" not in host or "id_type!(ResourceDomainId);" not in host:
        errors.append("canonical_hos2_domain_is_not_confirmed_16_bytes")
    if "pub struct ResourceDomainId([u8; 16]);" not in a09:
        errors.append("a09_domain_value_is_not_full_16_bytes")
    if "Self(value.to_be_bytes())" not in a09:
        errors.append("a09_domain_big_endian_encoding_missing")
    if "pub struct ResourceDomainId(pub u64);" in a09:
        errors.append("legacy_u64_domain_truncation_detected")
    for check in ("if !owner.is_nonzero()", "if !memory.owner.is_nonzero()"):
        if check not in a09:
            errors.append("zero_domain_validation_not_found:" + check)
    return errors


class DomainIdentityJoinTests(unittest.TestCase):
    def setUp(self):
        self.host = "pub struct Id16([u8; 16]);\nid_type!(ResourceDomainId);\n"
        self.a09 = ("pub struct ResourceDomainId([u8; 16]);\n"
                    "pub const fn from_u128(value: u128) -> Self { Self(value.to_be_bytes()) }\n"
                    "if !owner.is_nonzero() {}\nif !memory.owner.is_nonzero() {}\n")

    def test_current_checkout_uses_matching_16_byte_value_width(self):
        root = Path(__file__).resolve().parents[2]
        host = (root / "libs/os-control/src/lib.rs").read_text(encoding="utf-8")
        a09 = (root / "support/vmm/device_lifecycle/src/lib.rs").read_text(encoding="utf-8")
        self.assertEqual(compatibility_errors(host, a09), [])

    def test_matching_fixture_is_only_a_value_contract(self):
        self.assertEqual(compatibility_errors(self.host, self.a09), [])

    def test_old_u64_a09_model_is_rejected(self):
        bad = self.a09.replace("pub struct ResourceDomainId([u8; 16]);",
                               "pub struct ResourceDomainId(pub u64);")
        self.assertIn("a09_domain_value_is_not_full_16_bytes", compatibility_errors(self.host, bad))
        self.assertIn("legacy_u64_domain_truncation_detected", compatibility_errors(self.host, bad))

    def test_host_type_change_without_owner_agreement_is_rejected(self):
        self.assertIn("canonical_hos2_domain_is_not_confirmed_16_bytes",
                      compatibility_errors("pub struct Id16(u64);", self.a09))

    def test_lost_zero_identity_guard_is_rejected(self):
        self.assertTrue(compatibility_errors(self.host, self.a09.replace(
            "if !memory.owner.is_nonzero()", "if true")))


if __name__ == "__main__":
    unittest.main()
