from __future__ import annotations

from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class D1AgentResultLifecycleTests(unittest.TestCase):
    def test_oneshot_runtime_result_survives_until_acceptance_reads_it(self) -> None:
        unit = (
            REPOSITORY_ROOT
            / "packaging/debian/image/rootfs-overlay/etc/systemd/system/hepta-agent.service"
        ).read_text(encoding="utf-8")
        acceptance = (
            REPOSITORY_ROOT
            / "packaging/debian/image/rootfs-overlay/usr/local/libexec/trillionnium-d1-acceptance"
        ).read_text(encoding="utf-8")

        self.assertIn("Type=oneshot", unit)
        self.assertIn("RuntimeDirectory=hepta-agent", unit)
        self.assertIn("RuntimeDirectoryPreserve=yes", unit)
        self.assertIn("agent_result=/run/hepta-agent/result.json", acceptance)
        self.assertIn('[[ -s "$agent_result" ]] || return 1', acceptance)
        self.assertIn(
            'cp "$agent_result" "$result_dir/authorized-health-initial.json"',
            acceptance,
        )
        self.assertIn(
            'cp "$agent_result" "$result_dir/authorized-health-recovery.json"',
            acceptance,
        )

    def test_acceptance_requires_strict_build_metadata(self) -> None:
        acceptance = (
            REPOSITORY_ROOT
            / "packaging/debian/image/rootfs-overlay/usr/local/libexec/trillionnium-d1-acceptance"
        ).read_text(encoding="utf-8")

        self.assertIn("read_required_metadata()", acceptance)
        self.assertIn('fail "${label}_missing"', acceptance)
        self.assertIn('fail "${label}_invalid"', acceptance)
        self.assertIn(
            "^trillionnium-desktop-d1-[0-9a-f]{12}-[0-9a-f]{12}$", acceptance
        )
        self.assertNotIn("|| echo unknown", acceptance)


if __name__ == "__main__":
    unittest.main()
