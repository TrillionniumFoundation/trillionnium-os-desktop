"""Reject a successful metadata command that resolved a different product."""
import copy
import json
from pathlib import Path
import unittest

import build_text_product as product


class TextProductProfileTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads(Path(__file__).with_name("linux-text-profile.json").read_text())
        self.hepta = "7ea3df4e2ebaaa1052f8e01169ef0b5763beeda9"
        source = "git+https://github.com/TrillionniumFoundation/hepta-private-ci?rev=" + self.hepta + "#" + self.hepta
        sdk = "git+" + self.profile["makepad_repository"] + "?rev=" + self.profile["makepad_commit"] + "#" + self.profile["makepad_commit"]
        entries = (("trill-shell", None, ["hepta-native-makepad"]),
                   ("hepta-session-host", None, ["native-text"]),
                   ("hepta-robrix-ui", source, ["native-presentation"]),
                   ("hepta-control-core", source, []),
                   ("codex-hepta-agentd", source, []),
                   ("codex-hepta-memory", source, []),
                   ("makepad-widgets", sdk, []))
        self.metadata = {"packages": [{"name": name, "id": name, "source": origin}
                                      for name, origin, _ in entries],
                         "resolve": {"nodes": [{"id": name, "features": features}
                                                for name, _, features in entries]}}

    def test_exact_original_graph_is_accepted(self):
        result = product.validate_graph(self.metadata, self.hepta, self.profile)
        self.assertEqual(result["hepta-session-host"]["features"], ["native-text"])

    def test_egui_or_disconnected_text_feature_is_not_a_text_build(self):
        for name in ("trill-shell", "hepta-session-host", "hepta-robrix-ui"):
            metadata = copy.deepcopy(self.metadata)
            next(node for node in metadata["resolve"]["nodes"] if node["id"] == name)["features"] = []
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Missing native feature"):
                product.validate_graph(metadata, self.hepta, self.profile)

    def test_mixed_original_sources_and_local_runtime_substitution_are_refused(self):
        for value in (None, "git+https://github.com/TrillionniumFoundation/hepta-private-ci?rev=" + "a" * 40 + "#" + "a" * 40):
            metadata = copy.deepcopy(self.metadata)
            next(package for package in metadata["packages"] if package["name"] == "codex-hepta-agentd")["source"] = value
            with self.subTest(source=value), self.assertRaises(ValueError):
                product.validate_graph(metadata, self.hepta, self.profile)

    def test_clipboard_candidate_and_sdk_source_override_are_separate(self):
        metadata = copy.deepcopy(self.metadata)
        metadata["resolve"]["nodes"][0]["features"].append("hepta-native-clipboard-sdk")
        with self.assertRaisesRegex(ValueError, "independent patched SDK"):
            product.validate_graph(metadata, self.hepta, self.profile)
        metadata = copy.deepcopy(self.metadata)
        metadata["packages"][-1]["source"] = None
        with self.assertRaisesRegex(ValueError, "Original Makepad SDK differs"):
            product.validate_graph(metadata, self.hepta, self.profile)

    def test_unresolved_and_duplicate_original_owner_are_refused(self):
        metadata = copy.deepcopy(self.metadata)
        metadata["resolve"]["nodes"] = [node for node in metadata["resolve"]["nodes"] if node["id"] != "codex-hepta-agentd"]
        with self.assertRaisesRegex(ValueError, "one resolved package"):
            product.validate_graph(metadata, self.hepta, self.profile)
        metadata = copy.deepcopy(self.metadata)
        metadata["packages"].append(dict(metadata["packages"][4], id="other-agentd"))
        metadata["resolve"]["nodes"].append({"id": "other-agentd", "features": []})
        with self.assertRaisesRegex(ValueError, "one resolved package"):
            product.validate_graph(metadata, self.hepta, self.profile)


if __name__ == "__main__":
    unittest.main()
