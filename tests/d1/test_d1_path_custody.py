from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class D1AgentPortPathCustodyTests(unittest.TestCase):
    def test_preflight_is_mandatory_and_fail_closed(self) -> None:
        dropin = (
            ROOT
            / "packaging/debian/image/rootfs-overlay/etc/systemd/system/"
            "trillionnium-d1-acceptance.service.d/05-agent-port-path-custody.conf"
        ).read_text(encoding="utf-8")
        script = (
            ROOT
            / "packaging/debian/image/rootfs-overlay/usr/local/libexec/"
            "trillionnium-d1-agent-port-path-custody"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "ExecStartPre=/usr/local/libexec/trillionnium-d1-agent-port-path-custody",
            dropin,
        )
        for marker in (
            "root:hepta-agent-socket:750",
            "hepta-browserd:hepta-agent:660",
            "browser_service_in_directory_custody_group",
            "agent_client_missing_directory_custody_group",
            "run_denied create",
            "run_denied chmod",
            "run_denied unlink",
            "run_denied rename",
            "TRILLIONNIUM_D1_PATH_CUSTODY_PASS",
        ):
            self.assertIn(marker, script)
        self.assertNotIn("|| true\n  fi", script)

    def test_product_package_contains_effective_custody_dropins(self) -> None:
        install = (ROOT / "packaging/debian/hepta-agent-portd.install").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "hepta-browserd-agent.socket.d/10-root-path-custody.conf",
            install,
        )
        self.assertIn(
            "hepta-browserd-agent@.service.d/10-root-path-custody.conf",
            install,
        )
        self.assertNotIn("hepta-browserd-agent-development.socket.d", install)


if __name__ == "__main__":
    unittest.main()
