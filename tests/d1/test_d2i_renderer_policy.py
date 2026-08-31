from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class D2IRendererPolicyTests(unittest.TestCase):
    def test_guest_runtime_forces_non_jit_software_renderer(self) -> None:
        service = (
            ROOT
            / "packaging/debian/image/d2i-overlay/etc/systemd/system/trillionnium-d2i-runtime.service"
        ).read_text()
        self.assertIn("Environment=LIBGL_ALWAYS_SOFTWARE=1", service)
        self.assertIn("Environment=GALLIUM_DRIVER=softpipe", service)
        self.assertIn("Environment=DRAW_USE_LLVM=0", service)
        self.assertNotIn("Environment=GALLIUM_DRIVER=llvmpipe", service)

        contract = json.loads(
            (ROOT / "contracts/d2i-integrated-image.v1.json").read_text()
        )
        renderer = contract["runtime"]["software_renderer"]
        self.assertTrue(renderer["force_software"])
        self.assertEqual(renderer["gallium_driver"], "softpipe")
        self.assertTrue(renderer["llvm_jit_disabled"])
        self.assertEqual(
            renderer["environment"],
            [
                "LIBGL_ALWAYS_SOFTWARE=1",
                "GALLIUM_DRIVER=softpipe",
                "DRAW_USE_LLVM=0",
            ],
        )
        self.assertIn(
            "softpipe_renderer_without_llvm_jit",
            contract["promotion_requires"],
        )


if __name__ == "__main__":
    unittest.main()
