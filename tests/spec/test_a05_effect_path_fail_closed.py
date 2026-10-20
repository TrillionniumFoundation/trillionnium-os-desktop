"""A05 fail-closed source contract for the native effect seam.

This is a source contract only. It deliberately does not claim that any
resource effect is implemented or that an Asterinas guest has run. Ordinary
builds remain QueryAbi-only. The explicit G1-c profile may additionally read
its trusted initial image's existing CPU owner; management and history stay
disabled until their original owner paths are connected.
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
            r'#\[cfg\(feature = "g1c-trusted-observe"\)\]\s*'
            r'let \(supported_ops, max_response_payload\) = \(\s*'
            r'\(1u64 << Opcode::QueryAbi\.as_u16\(\)\) \| '
            r'\(1u64 << Opcode::ReadUsage\.as_u16\(\)\), 64,\s*\);',
            "the experimental profile must advertise exactly its two implemented reads",
        )
        self.assertIn("max_request_payload: 0", source)
        self.assertIn("features: 0", source)

    def test_all_disabled_opcodes_share_eopnotsupp_gate(self):
        source = DEVICE.read_text()
        abi = ABI.read_text()
        for opcode in ("ReadUsage", "InstallBudget", "QueryDelivery", "RetireThrough"):
            self.assertRegex(abi, rf"\b{opcode}\s*=\s*[2-5]\s*,")

        self.assertEqual(
            re.findall(r"RequestPayload::(\w+)(?:\([^)]*\))?\s*=>", source),
            ["QueryAbi", "ReadUsage"],
            "management and history must have no native match arm in this slice",
        )
        self.assertRegex(
            source,
            r'#\[cfg\(feature = "g1c-trusted-observe"\)\]\s*'
            r'RequestPayload::ReadUsage =>',
            "ordinary builds must not compile the ReadUsage arm",
        )
        self.assertIn("process.read_hepta_initial_usage(", source)
        self.assertRegex(
            source,
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
