"""Structural receipt/negotiation negative controls, never synthetic IME proof."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import preedit_gate as gate


class PreeditAcceptanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="trill-preedit-gate-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.log = self.root / "sdk.stderr"
        self.resources = self.root / "resources"
        self.resources.mkdir()
        self.sdk = {"sdk_profile": "preedit-callbacks", "patched_tree": "source-fixture-not-an-SDK"}
        (self.resources / "NATIVE-SDK-SOURCE.json").write_text(json.dumps(self.sdk))
        for number in range(60):
            (self.resources / f"file-{number}").write_text("structural resource fixture")
        self.build = {"profile": {"sdk_profile": "preedit-callbacks", "required_runtime_gate":
            "same-packaged-ELF-real-IBus-AT-SPI-callback-XID-and-owned-cleanup"},
            "sdk_source_profile": self.sdk,
            "resources": {path.name: gate.digest(path) for path in self.resources.iterdir()}}

    def verify(self, build):
        return gate.verify_resources(self.resources, build, packaged_binary=True, atomic_editable_text=True)

    def test_resources_must_match_the_explicit_source_and_full_build_inventory(self):
        self.assertEqual(self.verify(self.build)["name"], "preedit-callbacks")
        with self.assertRaisesRegex(RuntimeError, "explicit product build receipt"):
            self.verify(None)
        different = copy.deepcopy(self.build)
        different["sdk_source_profile"]["patched_tree"] = "another-source"
        with self.assertRaisesRegex(RuntimeError, "differs from the exact build"):
            self.verify(different)
        (self.resources / "file-0").write_text("changed structural resource")
        with self.assertRaisesRegex(RuntimeError, "differs from the compiled product"):
            self.verify(self.build)

    def test_preedit_product_requires_the_packaged_elf_and_atomic_editable_text_run(self):
        for packaged, editable in ((False, True), (True, False)):
            with self.subTest(packaged=packaged, editable=editable), self.assertRaisesRegex(RuntimeError, "acceptance requires"):
                gate.verify_resources(self.resources, self.build, packaged_binary=packaged, atomic_editable_text=editable)

    def test_a_callback_marker_for_another_window_or_a_later_downgrade_is_not_enough(self):
        prefix = "makepad-x11-ime profile=preedit-callbacks-v1 "
        self.log.write_text(prefix + "style=callback window=9\n")
        with self.assertRaisesRegex(RuntimeError, "exclusively negotiate"):
            gate.verify_negotiation(self.log, 10)
        self.log.write_text(prefix + "style=callback window=10\n" + prefix + "style=position window=10\n")
        with self.assertRaisesRegex(RuntimeError, "exclusively negotiate"):
            gate.verify_negotiation(self.log, 10)
        self.log.write_text(prefix + "style=callback window=10\n" + prefix + "style=position window=9\n")
        result = gate.verify_negotiation(self.log, 10)
        self.assertEqual(result["styles"], ["callback"])
        self.assertTrue(result["real_ibus_checks_required"])
