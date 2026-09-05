from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class D2IRendererPolicyTests(unittest.TestCase):
    def test_guest_runtime_uses_bounded_llvmpipe_cpu_features(self) -> None:
        service = (
            ROOT
            / "packaging/debian/image/d2i-overlay/etc/systemd/system/trillionnium-d2i-runtime.service"
        ).read_text()
        for line in (
            "Environment=LIBGL_ALWAYS_SOFTWARE=1",
            "Environment=GALLIUM_DRIVER=llvmpipe",
            "Environment=GALLIUM_OVERRIDE_CPU_CAPS=sse2",
            "Environment=LP_NATIVE_VECTOR_WIDTH=128",
            "Environment=LP_NUM_THREADS=1",
        ):
            self.assertIn(line, service)
        self.assertNotIn("Environment=GALLIUM_DRIVER=softpipe", service)
        self.assertNotIn("Environment=DRAW_USE_LLVM=0", service)

        contract = json.loads(
            (ROOT / "contracts/d2i-integrated-image.v1.json").read_text()
        )
        renderer = contract["runtime"]["software_renderer"]
        self.assertTrue(renderer["force_software"])
        self.assertEqual(renderer["gallium_driver"], "llvmpipe")
        self.assertEqual(renderer["cpu_capability_ceiling"], "sse2")
        self.assertEqual(renderer["native_vector_width_bits"], 128)
        self.assertEqual(renderer["worker_threads"], 1)
        self.assertTrue(renderer["llvm_execution_path_required"])
        self.assertEqual(
            renderer["environment"],
            [
                "LIBGL_ALWAYS_SOFTWARE=1",
                "GALLIUM_DRIVER=llvmpipe",
                "GALLIUM_OVERRIDE_CPU_CAPS=sse2",
                "LP_NATIVE_VECTOR_WIDTH=128",
                "LP_NUM_THREADS=1",
            ],
        )
        self.assertIn(
            "bounded_llvmpipe_sse2_single_worker",
            contract["promotion_requires"],
        )

    def test_d2i_input_source_is_explicitly_not_native_host_input(self) -> None:
        service = (
            ROOT
            / "packaging/debian/image/d2i-overlay/etc/systemd/system/trillionnium-d2i-runtime.service"
        ).read_text()
        runtime = (ROOT / "experiments/servo-headed-runtime/src/main.rs").read_text()
        acceptance = (
            ROOT
            / "packaging/debian/image/d2i-overlay/usr/local/libexec/trillionnium-d2i-acceptance"
        ).read_text()
        contract = json.loads(
            (ROOT / "contracts/d2i-integrated-image.v1.json").read_text()
        )
        self.assertIn("Environment=HEPTA_D2I_IMAGE_LOCAL_INPUT=1", service)
        self.assertIn("send_d2i_image_local_input", runtime)
        self.assertIn('"input_source": "d2i_image_local_servo_dispatch"', acceptance)
        input_contract = contract["runtime"]["input"]
        self.assertEqual(input_contract["source"], "d2i_image_local_servo_dispatch")
        self.assertFalse(input_contract["native_host_input_claimed"])
        self.assertFalse(input_contract["external_input_device_present"])
        self.assertTrue(input_contract["d0a02_native_host_input_remains_separate"])
        self.assertIn(
            "d2i_image_local_input_source_explicit",
            contract["promotion_requires"],
        )

    def test_recovery_screenshot_contract_matches_runtime_guest_and_host(self) -> None:
        runtime = (ROOT / "experiments/servo-headed-runtime/src/main.rs").read_text()
        acceptance = (
            ROOT
            / "packaging/debian/image/d2i-overlay/usr/local/libexec/trillionnium-d2i-acceptance"
        ).read_text()
        boot = (ROOT / "tests/qemu/run-d2i-boot-test.sh").read_text()
        workflow = (ROOT / ".github/workflows/d2i-integrated-image.yml").read_text()

        screenshot = "workspace-generation-2.png"
        self.assertIn(
            'save_workspace_image(&format!("workspace-generation-{generation}.png"))',
            runtime,
        )
        self.assertIn(f'screenshot="$out/{screenshot}"', acceptance)
        self.assertIn(f'screenshot="$output_dir/{screenshot}"', boot)
        self.assertIn(
            f"dump_guest_file /var/lib/trillionnium-d2i/{screenshot}",
            boot,
        )
        self.assertIn(f"root / 'qemu/{screenshot}'", workflow)
        for source in (acceptance, boot, workflow):
            self.assertNotIn("servo-content-recovered.png", source)


if __name__ == "__main__":
    unittest.main()
