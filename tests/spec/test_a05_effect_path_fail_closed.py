"""A05 fail-closed source contract for the native effect seam.

This checks source boundaries, not Rust compilation or a successful guest.
Ordinary builds remain QueryAbi-only. G1-c adds the trusted initial image's
ReadUsage. G1-d separately connects all five opcodes to the original Process,
CPU owner and delivery core; this experimental slice does not certify Hepta
disk durability. Keep the default and G1-c disabled-operation gates intact.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
DEVICE = ROOT / "kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs"
ABI = ROOT / "libs/os-abi/src/lib.rs"
ARCHITECTURE = ROOT / "docs/ARCHITECTURE.md"
INDEX = ROOT / "docs/INDEX.md"


class A05EffectPathFailClosedContract(unittest.TestCase):
    def test_default_device_advertises_only_queryabi(self):
        source = DEVICE.read_text()
        self.assertRegex(
            source,
            r'#\[cfg\(not\(feature = "g1c-trusted-observe"\)\)\]\s*'
            r'let \(supported_ops, max_response_payload\) = '
            r'\(1u64 << Opcode::QueryAbi\.as_u16\(\), 48\);',
            "ordinary A05 must retain QueryAbi-only capabilities",
        )
        self.assertRegex(
            source,
            r'#\[cfg\(all\(feature = "g1c-trusted-observe", '
            r'not\(feature = "g1d-trusted-control"\)\)\)\]\s*'
            r'let \(supported_ops, max_response_payload\) = \(\s*'
            r'\(1u64 << Opcode::QueryAbi\.as_u16\(\)\) \| '
            r'\(1u64 << Opcode::ReadUsage\.as_u16\(\)\), 64,\s*\);',
            "G1-c must advertise exactly its two implemented reads",
        )
        bit_expression = r'\s*\|\s*'.join(
            rf'\(1u64 << Opcode::{name}\.as_u16\(\)\)'
            for name in ("QueryAbi", "ReadUsage", "InstallBudget", "QueryDelivery", "RetireThrough")
        )
        self.assertRegex(
            source,
            r'#\[cfg\(feature = "g1d-trusted-control"\)\]\s*'
            r'let \(supported_ops, max_response_payload\) = \(\s*'
            + bit_expression + r', 64,\s*\);',
            "G1-d must uniformly declare exactly its five operations",
        )
        self.assertRegex(
            source,
            r'#\[cfg\(not\(feature = "g1d-trusted-control"\)\)\]\s*'
            r'let max_request_payload = 0;',
        )
        self.assertRegex(
            source,
            r'#\[cfg\(feature = "g1d-trusted-control"\)\]\s*'
            r'let max_request_payload = 40;',
        )
        self.assertIn("features: 0", source)

    def test_all_disabled_opcodes_share_eopnotsupp_gate(self):
        source = DEVICE.read_text()
        abi = ABI.read_text()
        for opcode in ("ReadUsage", "InstallBudget", "QueryDelivery", "RetireThrough"):
            self.assertRegex(abi, rf"\b{opcode}\s*=\s*[2-5]\s*,")

        self.assertRegex(
            source,
            r'#\[cfg\(feature = "g1c-trusted-observe"\)\]\s*'
            r'RequestPayload::ReadUsage =>',
            "ordinary builds must not compile the ReadUsage arm",
        )
        self.assertRegex(
            source,
            r'#\[cfg\(not\(feature = "g1d-trusted-control"\)\)\]\s*'
            r'let result =\s*match process\.read_hepta_initial_usage\(',
            "G1-c must keep its independently qualified observe path",
        )
        self.assertRegex(
            source,
            r'#\[cfg\(feature = "g1d-trusted-control"\)\]\s*'
            r'RequestPayload::InstallBudget\(_\) \| RequestPayload::QueryDelivery\(_\)\s*'
            r'\| RequestPayload::RetireThrough\(_\) =>',
            "management and history arms require the separate G1-d profile",
        )
        self.assertEqual(source.count("process.dispatch_hepta_control(self.image_key, &request)"), 2)
        self.assertRegex(
            source,
            r'#\[cfg\(not\(feature = "g1d-trusted-control"\)\)\]\s*'
            r'_ => return_errno_with_message!\(\s*Errno::EOPNOTSUPP,\s*'
            r'"recognized HOS2 resource operation not implemented"\s*\),',
        )

    def test_control_device_does_not_import_ui_or_host_authority(self):
        source = DEVICE.read_text()
        forbidden = (
            "os-control",
            "os_control",
            "TrustedReadOnlyOrgan",
            "Agentd",
            "WebSocket",
            "websocket",
            "FinalUse",
            "Final-use",
        )
        for token in forbidden:
            self.assertNotIn(token, source)

        architecture = ARCHITECTURE.read_text()
        index = INDEX.read_text()
        self.assertIn("不冒充内核", architecture)
        self.assertIn("仍返回 `EOPNOTSUPP`", architecture)
        self.assertIn("libs/os-control/API_CONTRACT.md", index)
        self.assertIn("宿主模型", index)
        self.assertIn("内核 IRQ/SMP 接合仍需验证", index)

    def test_readonly_bootstrap_has_no_effectful_authority_signal(self):
        source = DEVICE.read_text()
        self.assertIn("//! Read-only HOS2 bootstrap", source)
        self.assertIn("Management and\n//! history operations remain disabled", source)
        self.assertIn("Open, dup, fork and descriptor transfer grant no authority", source)
        self.assertNotIn("execute_reserved", source)
        self.assertNotIn("install_budget", source)
        self.assertNotIn("retire_through", source)


if __name__ == "__main__":
    unittest.main()
