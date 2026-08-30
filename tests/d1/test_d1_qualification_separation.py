from __future__ import annotations

from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[2]


class D1QualificationSeparationTests(unittest.TestCase):
    def test_product_and_d1_qualification_binaries_are_physically_separate(self) -> None:
        manifest_path = ROOT / "apps/hepta-agent-portd/Cargo.toml"
        manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
        features = manifest["features"]
        self.assertEqual(features["default"], [])
        self.assertIn("dep:hepta-agent-port", features["d1-qualification"])
        self.assertIn("dep:hepta-browser-codec", features["d1-qualification"])

        bins = {entry["name"]: entry for entry in manifest["bin"]}
        self.assertNotIn("required-features", bins["hepta-agent-portd"])
        self.assertEqual(
            bins["hepta-agent-d1-fixture"]["required-features"],
            ["d1-qualification"],
        )

        product = (ROOT / "apps/hepta-agent-portd/src/main.rs").read_text(
            encoding="utf-8"
        )
        qualification = (
            ROOT / "apps/hepta-agent-portd/src/bin/hepta-agent-d1-fixture.rs"
        ).read_text(encoding="utf-8")
        self.assertNotIn("D0FixtureHandler", product)
        self.assertNotIn("serve_one(", product)
        self.assertIn("ProductHandlerUnavailable", product)
        self.assertIn("D0FixtureHandler", qualification)
        self.assertIn('"server" => run_server()?', qualification)
        self.assertIn("qualification_only", qualification)
        self.assertIn("product_handler_connected", qualification)

        production_install = (
            ROOT / "packaging/debian/hepta-agent-portd.install"
        ).read_text(encoding="utf-8")
        self.assertNotIn("hepta-agent-d1-fixture", production_install)
        self.assertNotIn("image/rootfs-overlay", production_install)

        product_unit = (
            ROOT / "packaging/debian/systemd/hepta-browserd-agent@.service"
        ).read_text(encoding="utf-8")
        qualification_drop_in = (
            ROOT
            / "packaging/debian/image/rootfs-overlay/etc/systemd/system/"
            "hepta-browserd-agent@.service.d/10-d1-qualification-server.conf"
        ).read_text(encoding="utf-8")
        self.assertIn("ExecStart=/usr/libexec/hepta-agent-portd", product_unit)
        self.assertNotIn("hepta-agent-d1-fixture", product_unit)
        self.assertIn("ExecStart=", qualification_drop_in)
        self.assertIn(
            "ExecStart=/usr/libexec/hepta-agent-d1-fixture --mode server",
            qualification_drop_in,
        )

    def test_permanent_workflow_builds_and_audits_both_graphs_explicitly(self) -> None:
        workflow = (
            ROOT / ".github/workflows/d1-final-qualification.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("cargo tree --locked -p hepta-agent-portd --no-default-features", workflow)
        self.assertIn("--features d1-qualification", workflow)
        self.assertIn("--bin hepta-agent-d1-fixture", workflow)
        self.assertIn("product-daemon.strings", workflow)
        self.assertIn("qualification-fixture.strings", workflow)
        self.assertIn("product_handler_connected", workflow)
        self.assertIn("qualification_only", workflow)
        self.assertIn("git rev-parse HEAD^1", workflow)
        self.assertIn("git rev-parse HEAD^2", workflow)
        self.assertIn("- main", workflow)


if __name__ == "__main__":
    unittest.main()
