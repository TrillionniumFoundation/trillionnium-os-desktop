from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]


class D1ProductImageBindingTests(unittest.TestCase):
    def test_workflow_uses_audited_product_image_binding(self) -> None:
        workflow = (
            ROOT / ".github/workflows/d1-final-qualification.yml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "shellcheck tools/run_d1_product_image_qualification.sh",
            workflow,
        )
        self.assertIn(
            "tools/run_d1_product_image_qualification.sh",
            workflow,
        )
        self.assertNotIn(
            "run: tools/run_d1_final_qualification.sh run-pipeline",
            workflow,
        )

    def test_binding_adapter_is_valid_shell_and_restores_the_slot(self) -> None:
        path = ROOT / "tools/run_d1_product_image_qualification.sh"
        source = path.read_text(encoding="utf-8")

        completed = subprocess.run(
            ["bash", "-n", str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(
            'product_binary="$workspace/target/release/hepta-agent-portd"',
            source,
        )
        self.assertIn(
            "hepta-agent-port-qualificationd",
            source,
        )
        self.assertIn(
            'install -m 0755 -- "$product_binary" "$legacy_image_slot"',
            source,
        )
        self.assertIn("trap cleanup EXIT", source)
        self.assertIn(
            'install -m 0755 -- "$backup" "$legacy_image_slot"',
            source,
        )
        self.assertIn(
            '"$runner" run-pipeline',
            source,
        )

    def test_self_check_comparison_is_strict_but_pid_independent(self) -> None:
        source = (
            ROOT / "tools/run_d1_product_image_qualification.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("object_pairs_hook=reject_duplicates", source)
        self.assertIn('EXPECTED_KEYS - {"peer_pid"}', source)
        self.assertIn('type(item) is not int', source)
        self.assertNotIn('cmp --silent -- "$self_check"', source)

    def test_guest_product_claim_matches_effective_image_binary(self) -> None:
        pipeline = (ROOT / "tests/qemu/run-d1-pipeline.sh").read_text(
            encoding="utf-8"
        )
        builder = (
            ROOT / "packaging/debian/image/build-d1-image.sh"
        ).read_text(encoding="utf-8")
        acceptance = (
            ROOT
            / "packaging/debian/image/rootfs-overlay/usr/local/libexec/"
            "trillionnium-d1-acceptance"
        ).read_text(encoding="utf-8")
        adapter = (
            ROOT / "tools/run_d1_product_image_qualification.sh"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'agent_portd="$workspace/target/release/'
            'hepta-agent-port-qualificationd"',
            pipeline,
        )
        self.assertIn(
            '"$rootfs/usr/libexec/hepta-agent-portd"',
            builder,
        )
        self.assertIn(
            '/usr/libexec/hepta-agent-portd --self-check',
            acceptance,
        )
        self.assertIn(
            '"product_handler_connected":false',
            acceptance,
        )
        self.assertIn(
            'install -m 0755 -- "$product_binary" "$legacy_image_slot"',
            adapter,
        )


if __name__ == "__main__":
    unittest.main()
