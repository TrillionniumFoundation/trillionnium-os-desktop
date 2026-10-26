"""Cross-root source drift must fail before an expensive native build."""

import importlib.util
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("product_dependencies", Path(__file__).with_name("verify_product_dependencies.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class ProductDependencies(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for name in (*guard.MANIFESTS, *guard.LOCKS, guard.SOURCE,
                     "support/ui/linux-preedit-profile.json", "support/ui/linux-text-profile.json",
                     *guard.MIRRORED_FIXTURES.values()):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(guard.ROOT / name, target)

    def test_committed_pair_and_both_locks_agree(self):
        result = guard.verify(self.root, source_only=True)
        self.assertTrue(result["passed"])
        self.assertFalse(result["critical_graph_checked"])
        self.assertIsNone(result["critical_graph"])

    def test_full_verification_cannot_silently_become_source_only(self):
        with self.assertRaisesRegex(ValueError, "requires the original Hepta checkout"):
            guard.verify(self.root)

    def original_checkout(self):
        """Build an actual Git fixture; no external checkout/network is needed."""
        root = self.root / "original"
        root.mkdir()
        source_path = self.root / guard.SOURCE
        source = json.loads(source_path.read_text())
        old_commit = source["commit"]
        packages = guard.tomllib.loads((self.root / "ui/Cargo.lock").read_text())["package"]
        for package in packages:
            if guard.REPOSITORY in package.get("source", ""):
                del package["source"]
        reference = lock_bytes(packages)
        owner_manifests = {}
        for package in packages:
            dependencies = {d.split(" ", 1)[0] for d in package.get("dependencies", [])
                            if guard.is_critical(d.split(" ", 1)[0])}
            if package.get("source") is None and dependencies:
                name = f'codex-rs/reference-fixtures/{package["name"]}/Cargo.toml'
                owner_manifests[name] = ('[package]\nname = ' + json.dumps(package["name"])
                    + '\nversion = ' + json.dumps(package["version"]) + '\n[dependencies]\n'
                    + '\n'.join(f'{dep} = "*"' for dep in sorted(dependencies)) + '\n').encode()
                source["files"].append({"path": name})
        for entry in source["files"]:
            name = entry["path"]
            data = b"Original source fixture\n"
            if name in owner_manifests:
                data = owner_manifests[name]
            elif name == "codex-rs/Cargo.toml":
                data = b'[workspace]\nmembers = []\n[workspace.package]\nversion = "0.0.0"\n'
            elif name.endswith("/Cargo.toml"):
                data = ('[package]\nname = "fixture_' + hashlib.sha256(name.encode()).hexdigest()[:12]
                        + '"\nversion = "0.0.0"\n').encode()
            elif name in guard.MIRRORED_FIXTURES:
                data = (self.root / guard.MIRRORED_FIXTURES[name]).read_bytes()
            elif name == "codex-rs/Cargo.lock":
                data = reference
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            entry.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                         git_blob=hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest())
        def git(*args):
            return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL).decode().strip()
        git("init", "--quiet")
        git("add", ".")
        git("-c", "user.name=Dependency test", "-c", "user.email=test@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Original source fixture")
        source.update(commit=git("rev-parse", "HEAD"), tree=git("rev-parse", "HEAD^{tree}"))
        source_path.write_text(json.dumps(source))
        for name in (*guard.MANIFESTS, *guard.LOCKS):
            path = self.root / name
            path.write_text(path.read_text().replace(old_commit, source["commit"]))
        path = self.root / "support/ui/linux-preedit-profile.json"
        profile = json.loads(path.read_text())
        profile.update(hepta_commit=source["commit"], hepta_tree=source["tree"])
        path.write_text(json.dumps(profile))
        return root

    def test_full_public_entry_checks_all_six_locks_against_actual_git_reference(self):
        original = self.original_checkout()
        result = guard.verify(self.root, original)
        self.assertTrue(result["critical_graph_checked"])
        self.assertEqual(set(result["critical_graph"]["roots"]), set(guard.LOCKS))
        # Preserve every source revision, but break the current parser edge.
        path = self.root / "ui/Cargo.lock"
        text = path.read_text()
        graph = guard.LockedGraph(path.read_bytes(), "consumer mutation fixture")
        printer = graph.by_name["prettyplease"][0]
        parser = graph.edges(printer)["syn"]
        other = next(package for package in graph.by_name["syn"] if package["version"] != parser[1])
        marker = f'name = "prettyplease"\nversion = "{printer["version"]}"'
        start = text.index(marker)
        end = text.index("[[package]]", start)
        changed = text[start:end].replace(f'"syn {parser[1]}"', f'"syn {other["version"]}"')
        self.assertNotEqual(changed, text[start:end])
        path.write_text(text[:start] + changed + text[end:])
        with self.assertRaisesRegex(ValueError, "parser/printer type mismatch|Critical dependency edge differs"):
            guard.verify(self.root, original)

    def test_full_public_entry_rejects_reference_byte_drift(self):
        original = self.original_checkout()
        path = original / "codex-rs/Cargo.lock"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "Changed original source: codex-rs/Cargo.lock"):
            guard.verify(self.root, original)

    def test_whole_critical_family_removal_cannot_become_not_applicable(self):
        original = self.original_checkout()
        path = self.root / "ui/Cargo.lock"
        packages = guard.tomllib.loads(path.read_text())["package"]
        packages = [p for p in packages if not guard.is_critical(p["name"])]
        for package in packages:
            if "dependencies" in package:
                package["dependencies"] = [d for d in package["dependencies"]
                    if not guard.is_critical(d.split(" ", 1)[0])]
        path.write_bytes(lock_bytes(packages))
        with self.assertRaisesRegex(ValueError, "Missing mandatory original owner dependency"):
            guard.verify(self.root, original)

    def test_one_manifest_cannot_select_another_original_owner(self):
        path = self.root / "services/hepta-session-host/Cargo.toml"
        source = json.loads((self.root / guard.SOURCE).read_text())["commit"]
        path.write_text(path.read_text().replace(source, "a" * 40, 1))
        with self.assertRaisesRegex(ValueError, "Original owner dependency substituted|Mixed original Hepta dependency"):
            guard.verify(self.root, source_only=True)

    def test_original_owner_cannot_be_replaced_by_a_path_dependency(self):
        path = self.root / "services/hepta-session-host/Cargo.toml"
        lines = path.read_text().splitlines()
        lines = ['codex-hepta-memory = { path = "../substitute" }'
                 if line.startswith("codex-hepta-memory =") else line for line in lines]
        path.write_text("\n".join(lines) + "\n")
        with self.assertRaisesRegex(ValueError, "Original owner dependency substituted"):
            guard.verify(self.root, source_only=True)

    def test_each_lock_rejects_an_old_original_source(self):
        for name in guard.LOCKS:
            with self.subTest(lock=name):
                path = self.root / name
                original = path.read_text()
                source = json.loads((self.root / guard.SOURCE).read_text())["commit"]
                if source in original:
                    changed = original.replace(source, "a" * 40, 1)
                else:
                    # These independent contract roots have no original Hepta
                    # dependency. Introduce an actual foreign source rather
                    # than expecting a no-op string replacement to fail.
                    changed = original + '\n[[package]]\nname = "foreign-original-graph"\nversion = "0.0.0"\nsource = "git+' + guard.REPOSITORY + '?rev=' + "a" * 40 + '#' + "a" * 40 + '"\n'
                path.write_text(changed)
                with self.assertRaisesRegex(ValueError, "Mixed original Hepta sources"):
                    guard.verify(self.root, source_only=True)
                path.write_text(original)

    def test_missing_owner_is_not_an_empty_successful_lock(self):
        (self.root / "services/hepta-session-host/Cargo.lock").write_text("version = 4\n")
        with self.assertRaisesRegex(ValueError, "Original owner packages missing"):
            guard.verify(self.root, source_only=True)

    def test_missing_shared_compiler_is_refused(self):
        path = self.root / guard.SOURCE
        source = json.loads(path.read_text())
        source["files"] = [entry for entry in source["files"] if entry["path"] not in guard.REQUIRED_FILES]
        path.write_text(json.dumps(source))
        with self.assertRaisesRegex(ValueError, "shared literal Notes compiler"):
            guard.verify(self.root, source_only=True)

    def test_preedit_cannot_silently_use_another_companion(self):
        path = self.root / "support/ui/linux-preedit-profile.json"
        profile = json.loads(path.read_text())
        profile["hepta_commit"] = "b" * 40
        path.write_text(json.dumps(profile))
        with self.assertRaisesRegex(ValueError, "Preedit profile differs"):
            guard.verify(self.root, source_only=True)

    def test_composer_boundary_and_its_sdk_regression_cannot_be_omitted(self):
        path = self.root / guard.SOURCE
        original = json.loads(path.read_text())
        for name in ("composer_transaction.rs", "composer_transaction_tests.rs"):
            with self.subTest(source=name):
                source = dict(original, files=[entry for entry in original["files"]
                    if Path(entry["path"]).name != name])
                path.write_text(json.dumps(source))
                with self.assertRaisesRegex(ValueError, "original composer transaction"):
                    guard.verify(self.root, source_only=True)
        path.write_text(json.dumps(original))

    def test_readback_wire_cannot_drift_from_the_original_contract(self):
        name = guard.MIRRORED_FIXTURES["codex-rs/hepta-agentd/tests/fixtures/notes-document-observation-v1.json"]
        path = self.root / name
        path.write_text(path.read_text().replace('"revision": 5', '"revision": 6'))
        with self.assertRaisesRegex(ValueError, "readback wire fixtures differ"):
            guard.verify(self.root, source_only=True)

    def test_model_identity_fixture_cannot_drift(self):
        name = guard.MIRRORED_FIXTURES["codex-rs/hepta-agentd/tests/fixtures/notes-model-v1.json"]
        path = self.root / name
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "readback wire fixtures differ"):
            guard.verify(self.root, source_only=True)

    def test_root_dependency_cannot_be_replaced_by_a_path(self):
        path = self.root / "services/hepta-session-host/Cargo.toml"
        lines = path.read_text().splitlines()
        lines = ['codex-hepta-supervisor = { path = "../substitute", optional = true }'
                 if line.startswith("codex-hepta-supervisor =") else line for line in lines]
        path.write_text("\n".join(lines) + "\n")
        with self.assertRaisesRegex(ValueError, "Original owner dependency substituted"):
            guard.verify(self.root, source_only=True)

    def test_original_aws_security_patch_must_be_carried_by_both_roots(self):
        for name in ("ui/Cargo.toml", "services/hepta-session-host/Cargo.toml"):
            path = self.root / name
            original = path.read_text()
            path.write_text("\n".join(line for line in original.splitlines()
                                      if not line.startswith("aws-config =")) + "\n")
            with self.subTest(manifest=name), self.assertRaisesRegex(ValueError, "AWS security patch missing"):
                guard.verify(self.root, source_only=True)
            path.write_text(original)

    def test_common_package_version_cannot_drift_in_one_lock(self):
        path = self.root / "services/hepta-os/Cargo.lock"
        original = path.read_text()
        self.assertIn('name = "serde_json"\nversion = "1.0.154"', original)
        path.write_text(original.replace('name = "serde_json"\nversion = "1.0.154"',
                                         'name = "serde_json"\nversion = "1.0.151"'))
        with self.assertRaisesRegex(ValueError, "Shared package version differs"):
            guard.verify(self.root, source_only=True)

    def test_default_and_prepared_sdk_locks_cannot_be_interchanged(self):
        ordinary = self.root / "ui/Cargo.lock"
        prepared = self.root / "support/ui/preedit-sdk/Cargo.lock"
        ordinary_bytes, prepared_bytes = ordinary.read_bytes(), prepared.read_bytes()
        prepared.write_bytes(ordinary_bytes)
        with self.assertRaisesRegex(ValueError, "Prepared UI lock must resolve"):
            guard.verify(self.root, source_only=True)
        prepared.write_bytes(prepared_bytes)
        ordinary.write_bytes(prepared_bytes)
        with self.assertRaisesRegex(ValueError, "Default UI lock must retain"):
            guard.verify(self.root, source_only=True)


def lock_bytes(packages):
    rows = ["version = 4"]
    for package in packages:
        rows.append("\n[[package]]")
        rows.extend(f"{key} = {json.dumps(value)}" for key, value in package.items())
    return ("\n".join(rows) + "\n").encode()


class CriticalLockedGraph(unittest.TestCase):
    def setUp(self):
        def package(name, version, dependencies=()):
            return {"name": name, "version": version,
                    "source": "registry+https://github.com/rust-lang/crates.io-index",
                    "checksum": hashlib.sha256((name + version).encode()).hexdigest(),
                    "dependencies": list(dependencies)}
        self.packages = [
            package("bindgen", "0.73.2", ("prettyplease", "syn 2.0.119")),
            package("prettyplease", "0.2.37", ("syn 2.0.119",)),
            package("syn", "2.0.119"), package("syn", "3.0.9"),
            package("zstd", "0.14.3", ("zstd-safe",)),
            package("zstd-safe", "8.2.0", ("zstd-sys",)),
            package("zstd-sys", "2.1.2+zstd.1.5.7"),
            package("independent-macro", "1.0.0", ("syn 3.0.9",)),
        ]
        self.reference = guard.LockedGraph(lock_bytes(self.packages), "reference")

    def check(self, packages=None):
        return guard.verify_critical_graph(lock_bytes(self.packages if packages is None else packages),
                                           self.reference, "consumer")

    def aws_graph(self):
        def package(name, version, dependencies=()):
            return {"name": name, "version": version,
                    "source": "registry+https://github.com/rust-lang/crates.io-index",
                    "checksum": hashlib.sha256((name + version).encode()).hexdigest(),
                    "dependencies": list(dependencies)}
        config = {"name": "aws-config", "version": "1.12.0", "dependencies": ["aws-types"]}
        types = package("aws-types", "1.6.0", ("aws-smithy-schema",))
        schema = package("aws-smithy-schema", "0.2.1")
        reference = guard.LockedGraph(lock_bytes(self.packages + [config, types, schema]), "AWS reference")
        consumer = copy.deepcopy(self.packages + [config, types, schema])
        consumer[-3]["source"] = "git+original"
        consumer.append({"name": "original-owner", "version": "0.0.0", "source": "git+original",
                         "dependencies": ["aws-config"]})
        mandatory = {("original-owner", "0.0.0"): {"aws-config": guard.package_identity(config)},
                     ("aws-config", "1.12.0"): {"aws-types": guard.package_identity(types)}}
        return reference, consumer, mandatory

    def test_aws_vendor_path_maps_only_to_selected_original_git_source(self):
        reference, packages, mandatory = self.aws_graph()
        result = guard.verify_critical_graph(lock_bytes(packages), reference, "consumer", mandatory, "git+original")
        self.assertEqual(len(result["original_owner_edges"]), 2)
        self.assertIn("aws-config", {node["name"] for node in result["nodes"]})
        for replacement in ("registry+https://github.com/rust-lang/crates.io-index", "git+foreign"):
            changed = copy.deepcopy(packages)
            next(p for p in changed if p["name"] == "aws-config")["source"] = replacement
            with self.subTest(source=replacement), self.assertRaisesRegex(ValueError, "Critical package differs"):
                guard.verify_critical_graph(lock_bytes(changed), reference, "consumer", mandatory, "git+original")

    def test_newer_aws_config_cannot_bypass_carried_patch(self):
        reference, packages, mandatory = self.aws_graph()
        config = next(p for p in packages if p["name"] == "aws-config")
        config.update(version="1.13.0", source="registry+https://github.com/rust-lang/crates.io-index", checksum="0" * 64)
        with self.assertRaisesRegex(ValueError, "Critical package differs"):
            guard.verify_critical_graph(lock_bytes(packages), reference, "consumer", mandatory, "git+original")

    def test_aws_types_and_schema_drift_are_not_version_compatibility_assumptions(self):
        reference, original, mandatory = self.aws_graph()
        for family, version in (("aws-types", "1.7.0"), ("aws-smithy-schema", "1.1.0")):
            packages = copy.deepcopy(original)
            next(p for p in packages if p["name"] == family)["version"] = version
            with self.subTest(family=family), self.assertRaisesRegex(ValueError, "Critical dependency edge differs|Critical package differs"):
                guard.verify_critical_graph(lock_bytes(packages), reference, "consumer", mandatory, "git+original")

    def test_aws_edge_cannot_switch_between_two_allowed_schema_nodes(self):
        reference, packages, mandatory = self.aws_graph()
        extra = dict(next(p for p in packages if p["name"] == "aws-smithy-schema"), version="1.1.0", checksum="1" * 64)
        upstream = copy.deepcopy(reference.packages) + [extra]
        next(p for p in upstream if p["name"] == "aws-types")["dependencies"] = ["aws-smithy-schema 0.2.1"]
        reference = guard.LockedGraph(lock_bytes(upstream), "two schema nodes")
        packages.append(extra)
        next(p for p in packages if p["name"] == "aws-types")["dependencies"] = ["aws-smithy-schema 1.1.0"]
        with self.assertRaisesRegex(ValueError, "Critical dependency edge differs"):
            guard.verify_critical_graph(lock_bytes(packages), reference, "consumer", mandatory, "git+original")

    def test_whole_aws_family_removal_does_not_erase_original_required_patch(self):
        reference, packages, mandatory = self.aws_graph()
        packages = [p for p in packages if not p["name"].startswith("aws-")]
        packages[-1]["dependencies"] = []
        with self.assertRaisesRegex(ValueError, "Missing mandatory original owner dependency"):
            guard.verify_critical_graph(lock_bytes(packages), reference, "consumer", mandatory, "git+original")

    def test_exact_edges_allow_independent_syn3(self):
        result = self.check()
        self.assertTrue(result["applicable"])
        self.assertEqual(len(result["nodes"]), 5)
        self.assertEqual(len(result["edges"]), 5)

    def test_root_without_critical_packages_is_not_applicable(self):
        self.assertEqual(self.check(self.packages[2:4]),
                         {"applicable": False, "checked": True, "nodes": [], "edges": []})

    def test_bindgen_without_optional_printer_does_not_invent_one(self):
        self.packages[0]["dependencies"] = ["syn 2.0.119"]
        del self.packages[1]
        self.assertTrue(self.check()["checked"])

    def test_same_source_revision_does_not_allow_mixed_parser_printer(self):
        self.packages[0]["dependencies"] = ["prettyplease", "syn 3.0.9"]
        with self.assertRaisesRegex(ValueError, "Critical dependency edge differs"):
            self.check()

    def test_printer_must_keep_its_exact_parser_edge(self):
        for dependencies in ([], ["syn 3.0.9"]):
            with self.subTest(dependencies=dependencies):
                self.packages[1]["dependencies"] = dependencies
                with self.assertRaisesRegex(ValueError, "Missing critical edge|Critical dependency edge differs|parser/printer type mismatch"):
                    self.check()

    def test_old_zstd_cannot_hide_beside_the_current_one(self):
        old = copy.deepcopy(self.packages[4])
        old["version"] = "0.13.3"
        self.packages.append(old)
        with self.assertRaisesRegex(ValueError, "Critical package differs"):
            self.check()

    def test_original_owner_cannot_switch_between_two_allowed_critical_nodes(self):
        # A wider reference can allow two versions while a particular original
        # owner still requires one exact incoming edge.
        old = copy.deepcopy(self.packages[4])
        old["version"] = "0.13.3"
        old["checksum"] = "1" * 64
        self.packages.append(old)
        reference = guard.LockedGraph(lock_bytes(self.packages), "two allowed versions")
        expected = {("original-owner", "0.0.0"): {"zstd": guard.package_identity(old)}}
        owner = {"name": "original-owner", "version": "0.0.0", "source": "git+original",
                 "dependencies": ["zstd 0.14.3"]}
        with self.assertRaisesRegex(ValueError, "Mandatory original owner edge differs"):
            guard.verify_critical_graph(lock_bytes(self.packages + [owner]), reference,
                                        "consumer", expected, "git+original")

    def test_same_version_source_or_checksum_substitution_is_refused(self):
        for key, value in (("source", "registry+https://foreign.invalid/index"),
                           ("checksum", "0" * 64)):
            with self.subTest(key=key):
                packages = copy.deepcopy(self.packages)
                packages[1][key] = value
                with self.assertRaisesRegex(ValueError, "Critical dependency edge differs|Critical package differs"):
                    self.check(packages)

    def test_ambiguous_dependency_name_is_not_first_match(self):
        self.packages[0]["dependencies"] = ["prettyplease", "syn"]
        with self.assertRaisesRegex(ValueError, "ambiguous lock dependency"):
            self.check()

    def test_deleted_critical_package_is_not_not_applicable(self):
        packages = [copy.deepcopy(self.packages[7])]
        packages[0]["dependencies"] = ["bindgen"]
        with self.assertRaisesRegex(ValueError, "Missing or ambiguous lock dependency"):
            self.check(packages)

    def test_duplicate_package_id_with_different_checksum_is_refused(self):
        duplicate = copy.deepcopy(self.packages[1])
        duplicate["checksum"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Duplicate locked package"):
            self.check(self.packages + [duplicate])

    def test_reference_must_match_actual_recorded_git_blob(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            name = "codex-rs/Cargo.lock"
            path = root / name
            path.parent.mkdir()
            data = lock_bytes(self.packages)
            path.write_bytes(data)
            def git(*args):
                return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL)
            git("init", "--quiet")
            git("add", name)
            git("-c", "user.name=Dependency test", "-c", "user.email=test@example.invalid",
                "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Reference lock")
            blob = git("rev-parse", "HEAD:" + name).decode().strip()
            self.assertEqual(guard.reference_lock(root, {name: {"git_blob": blob}}), data)
            with patch.dict(os.environ, {"GIT_DIR": str(root / "foreign-missing.git"),
                    "GIT_WORK_TREE": str(root / "foreign-worktree"), "GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "core.bare", "GIT_CONFIG_VALUE_0": "true"}):
                self.assertEqual(guard.reference_lock(root, {name: {"git_blob": blob}}), data)
            # Even a caller-updated digest cannot authorize uncommitted bytes.
            path.write_bytes(data + b"\n")
            altered = hashlib.sha1(b"blob " + str(len(data) + 1).encode() + b"\0" + data + b"\n").hexdigest()
            with self.assertRaisesRegex(ValueError, "recorded tracked regular blob"):
                guard.reference_lock(root, {name: {"git_blob": altered}})
            path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "recorded tracked regular blob"):
                guard.reference_lock(root, {name: {"git_blob": "0" * 40}})


if __name__ == "__main__":
    unittest.main()
