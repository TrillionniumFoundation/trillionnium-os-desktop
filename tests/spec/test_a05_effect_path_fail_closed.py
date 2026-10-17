"""A05 fail-closed source contract for the native effect seam.

This is a source contract only. It deliberately does not claim that any
resource effect is implemented or that an Asterinas guest has run.  The native
control device must remain QueryAbi-only until trusted CapSpace, the canonical
ResourceDomain owner, and the durable Hepta owner are connected.
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
    def test_device_advertises_only_queryabi(self):
        source = DEVICE.read_text()
        advertised = re.findall(r"supported_ops:\s*([^,]+),", source)
        self.assertEqual(
            advertised,
            ["1u64 << Opcode::QueryAbi.as_u16()"],
            "A05 must not advertise an effect opcode before its authority path exists",
        )
        self.assertIn("max_request_payload: 0", source)

    def test_all_non_query_opcodes_share_eopnotsupp_gate(self):
        source = DEVICE.read_text()
        abi = ABI.read_text()
        for opcode in ("ReadUsage", "InstallBudget", "QueryDelivery", "RetireThrough"):
            self.assertRegex(abi, rf"\b{opcode}\s*=\s*[2-5]\s*,")

        gate = (
            "if request.opcode != Opcode::QueryAbi || request.payload != RequestPayload::QueryAbi"
        )
        self.assertIn(gate, source)
        gate_start = source.index(gate)
        gate_body = source[gate_start : gate_start + 360]
        self.assertIn("Errno::EOPNOTSUPP", gate_body)
        self.assertIn("recognized HOS2 resource operation not implemented", gate_body)

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
        self.assertIn("No management authority is", source)
        self.assertIn("does not install a CPU budget", source)
        self.assertIn("cannot retire delivery", source)
        self.assertNotIn("execute_reserved", source)
        self.assertNotIn("install_budget", source)
        self.assertNotIn("retire_through", source)


if __name__ == "__main__":
    unittest.main()
