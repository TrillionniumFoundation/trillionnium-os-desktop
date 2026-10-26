#!/usr/bin/env python3
"""Real isolated Git regressions for current native CI source selection."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

import current_source_review as source

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


class SourceFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.desktop, self.hepta = self.root / "desktop", self.root / "hepta"
        for path in (self.desktop, self.hepta):
            path.mkdir()
            self.git(path, "init", "--quiet")
        self.put(self.hepta, "codex-rs/rust-toolchain.toml", '[toolchain]\nchannel = "1.96.0"\n')
        self.put(self.hepta, "codex-rs/Cargo.toml", '[workspace]\nresolver = "2"\n')
        self.put(self.hepta, "codex-rs/Cargo.lock", "# Actual original lock\n")
        self.put(self.hepta, "codex-rs/hepta-agentd/src/old_owner.rs", "original owner\n")
        self.put(self.hepta, "codex-rs/hepta-agentd/src/new_authority.rs", "new actual authority module\n")
        self.put(self.hepta, "codex-rs/hepta-contracts/src/final_use.rs", "original FinalUse callee\n")
        self.put(self.hepta, "codex-rs/hepta-cognitive-store/src/lib.rs", "original cognitive store facade\n")
        self.commit(self.hepta)
        self.contract = {"schema": "trillionnium.original-shared-presenter.v1", "repository": source.REPOSITORY,
                         "commit": self.git(self.hepta, "rev-parse", "HEAD"),
                         "tree": self.git(self.hepta, "rev-parse", "HEAD^{tree}"),
                         "contract": "Source selection is not qualification", "desktop_base": {},
                         "initial_pull_request": 1, "files": []}
        name = "codex-rs/hepta-agentd/src/new_authority.rs"
        entry = source.record(self.hepta, name, "hepta")
        entry.pop("repository")
        entry["bytes"] = (self.hepta / name).stat().st_size
        self.contract["files"].append(entry)
        self.put(self.desktop, "original_fixture.rs", "unchanged original lifecycle fixture\n")
        for name in source.MANIFESTS:
            self.put(self.desktop, name, '[dependencies]\noriginal = { git = "https://github.com/'
                     + source.REPOSITORY + '", rev = "' + self.contract["commit"] + '" }\n')
        self.template = {"schema": source.SCHEMA,
                         "desktop": {"head": "1" * 40, "tree": "2" * 40},
                         "hepta": {"head": "3" * 40, "tree": "4" * 40},
                         "scope": "Historical fixture; not the current selected identity",
                         "source_files": [dict(repository=repo, path=name, git_blob="5" * 40, sha256="6" * 64)
                                          for repo, name in (("desktop", "original_fixture.rs"),
                                                             ("hepta", "codex-rs/hepta-agentd/src/old_owner.rs"))],
                         "userspace_toolchain": {"channel": "1.95.0", "manifest": "codex-rs/rust-toolchain.toml",
                                                 "sha256": "7" * 64}}
        self.put(self.desktop, source.TEMPLATE, json.dumps(self.template))
        self.save_contract()

    def git(self, directory, *arguments):
        return subprocess.check_output(["git", "-C", str(directory), *arguments], env=source.ENV,
                                       stderr=subprocess.PIPE, text=True).strip()

    def put(self, root, name, text):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, directory):
        self.git(directory, "add", "--all")
        self.git(directory, "-c", "user.name=Current source regression", "-c", "user.email=ci@invalid.example",
                 "commit", "--quiet", "-m", "Isolated exact source fixture")

    def save_contract(self):
        self.put(self.desktop, source.CONTRACT, json.dumps(self.contract))
        self.commit(self.desktop)

    def review(self):
        return source.derive(self.desktop, self.hepta)

    def external(self, value=None, raw=None):
        path = self.root / "review.json"
        path.write_bytes(raw if raw is not None else json.dumps(value).encode())
        return source.load_external(path, hashlib.sha256(path.read_bytes()).hexdigest(), self.desktop, self.hepta)


class CurrentSourceReviewTests(SourceFixture, unittest.TestCase):
    def test_current_checkout_and_one_authority_replace_both_stale_identities(self):
        before = (self.desktop / source.TEMPLATE).read_bytes()
        review = self.review()
        self.assertEqual(review["desktop"]["head"], self.git(self.desktop, "rev-parse", "HEAD"))
        self.assertEqual(review["hepta"]["head"], self.contract["commit"])
        self.assertNotEqual(review["desktop"], self.template["desktop"])
        self.assertNotEqual(review["hepta"], self.template["hepta"])
        self.assertEqual(review["userspace_toolchain"]["channel"], "1.96.0")
        selected = {(item["repository"], item["path"]) for item in review["source_files"]}
        self.assertTrue({(item["repository"], item["path"]) for item in self.template["source_files"]} <= selected)
        self.assertIn(("hepta", "codex-rs/hepta-agentd/src/new_authority.rs"), selected)
        self.assertIn(("hepta", "codex-rs/hepta-contracts/src/final_use.rs"), selected)
        self.assertIn(("hepta", "codex-rs/hepta-cognitive-store/src/lib.rs"), selected)
        self.assertIn(("hepta", "codex-rs/Cargo.toml"), selected)
        self.assertEqual(self.external(review), review)
        self.assertEqual((self.desktop / source.TEMPLATE).read_bytes(), before)
        self.assertEqual(self.git(self.desktop, "status", "--porcelain=v1", "--untracked-files=all"), "")

    def test_supplied_hash_cannot_authorize_another_pair_inventory_path_or_unknown_field(self):
        review = self.review()
        mutations = []
        for repository in ("desktop", "hepta"):
            changed = copy.deepcopy(review)
            changed[repository]["head"] = "0" * 40
            mutations.append(changed)
        for field in ("git_blob", "sha256", "path", "repository"):
            changed = copy.deepcopy(review)
            changed["source_files"][0][field] = "../outside" if field == "path" else "fake"
            mutations.append(changed)
        changed = copy.deepcopy(review)
        changed["source_files"].pop()
        mutations.append(changed)
        for name in ("original_fixture.rs", "codex-rs/hepta-agentd/src/new_authority.rs",
                     "codex-rs/hepta-contracts/src/final_use.rs", "codex-rs/hepta-cognitive-store/src/lib.rs"):
            changed = copy.deepcopy(review)
            changed["source_files"] = [item for item in changed["source_files"] if item["path"] != name]
            mutations.append(changed)
        changed = copy.deepcopy(review)
        changed["source_files"][0]["extra"] = True
        mutations.append(changed)
        changed = copy.deepcopy(review)
        changed["extra"] = True
        mutations.append(changed)
        changed = copy.deepcopy(review)
        changed["schema"] = "other.v1"
        mutations.append(changed)
        for changed in mutations:
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, "canonical tracked source reconstruction"):
                self.external(changed)

    def test_duplicate_fields_even_with_correct_supplied_hash_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate source JSON"):
            self.external(raw=b'{"schema":"one","schema":"two"}')

    def test_wrong_hash_oversized_or_symlink_review_is_rejected(self):
        path = self.root / "review.json"
        path.write_text(json.dumps(self.review()))
        with self.assertRaisesRegex(ValueError, "digest differs"):
            source.load_external(path, "0" * 64, self.desktop, self.hepta)
        link = self.root / "link.json"
        link.symlink_to(path)
        with self.assertRaisesRegex(ValueError, "canonical external review path"):
            source.load_external(link, source.digest(path.read_bytes()), self.desktop, self.hepta)
        path.write_bytes(b"x" * (source.LIMIT + 1))
        with self.assertRaisesRegex(ValueError, "bounded regular"):
            source.load_external(path, source.digest(path.read_bytes()), self.desktop, self.hepta)

    def test_dirty_working_bytes_or_new_untracked_input_reject_current_review(self):
        review = self.review()
        for root, name in ((self.desktop, "original_fixture.rs"), (self.hepta, "codex-rs/hepta-agentd/src/old_owner.rs")):
            path = root / name
            old = path.read_bytes()
            path.write_bytes(old + b"changed\n")
            with self.assertRaisesRegex(ValueError, "clean source required"):
                self.external(review)
            path.write_bytes(old)
        (self.desktop / "untracked").write_text("new input")
        with self.assertRaisesRegex(ValueError, "clean source required"):
            self.external(review)

    def test_other_canonical_hepta_identity_or_forged_closure_is_rejected(self):
        original = copy.deepcopy(self.contract)
        for field, value in (("commit", "0" * 40), ("tree", "0" * 40)):
            self.contract = dict(original, **{field: value})
            self.save_contract()
            with self.assertRaisesRegex(ValueError, "differs from canonical product"):
                self.review()
        self.contract = copy.deepcopy(original)
        self.contract["files"][0]["sha256"] = "0" * 64
        self.save_contract()
        with self.assertRaisesRegex(ValueError, "source closure differs"):
            self.review()

    def test_duplicate_or_escaping_canonical_source_item_is_rejected(self):
        original = copy.deepcopy(self.contract)
        self.contract["files"].append(copy.deepcopy(self.contract["files"][0]))
        self.save_contract()
        with self.assertRaisesRegex(ValueError, "duplicate canonical"):
            self.review()
        self.contract = original
        self.contract["files"][0]["path"] = "../outside"
        self.save_contract()
        with self.assertRaisesRegex(ValueError, "normalized source path"):
            self.review()

    def test_cargo_entry_disagreement_cannot_be_hidden_by_source_contract(self):
        path = self.desktop / source.MANIFESTS[0]
        path.write_text(path.read_text().replace(self.contract["commit"], "0" * 40))
        self.commit(self.desktop)
        with self.assertRaisesRegex(ValueError, "Cargo source differs"):
            self.review()

    def test_actual_workflow_fetches_unpublished_current_desktop_commit_locally(self):
        origin = self.root / "desktop-origin.git"
        self.git(self.desktop, "clone", "--quiet", "--bare", str(self.desktop), str(origin))
        self.put(self.desktop, "only-current-checkout.rs", "new unpublished source\n")
        self.commit(self.desktop)
        pin = self.git(self.desktop, "rev-parse", "HEAD")
        probe = self.root / "remote-probe"
        probe.mkdir()
        self.git(probe, "init", "--quiet")
        original = subprocess.run(["git", "-C", str(probe), "fetch", "--depth=1", str(origin), pin],
                                  env=source.ENV, capture_output=True, check=False)
        # A local upload-pack may serve a reachable loose commit by object path;
        # this origin was cloned before the new object and cannot possibly do so.
        self.assertNotEqual(original.returncode, 0)
        ci = self.root / "ci"
        (ci / "identity").mkdir(parents=True)
        (ci / "logs").mkdir()
        workflow = (ROOT / ".github/workflows/f1-original-runtime-native.yml").read_text()
        step = workflow.split("      - name: Fetch exact original Desktop and Hepta sources without credentials\n", 1)[1]
        script = textwrap.dedent(step.split("        run: |\n", 1)[1].split("      - name:", 1)[0])
        script = script.replace("https://github.com/TrillionniumFoundation/hepta-private-ci.git", self.hepta.as_uri())
        result = subprocess.run(["/bin/bash", "-c", script], env=dict(source.ENV, F1_CI_ROOT=str(ci),
                                GITHUB_WORKSPACE=str(self.desktop), DESKTOP_SOURCE_PIN=pin,
                                HEPTA_SOURCE_PIN=self.contract["commit"]), capture_output=True, text=True,
                                timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.git(ci / "desktop-source", "rev-parse", "HEAD"), pin)
        self.assertEqual(self.git(ci / "desktop-source", "rev-parse", "HEAD^{tree}"),
                         self.git(self.desktop, "rev-parse", "HEAD^{tree}"))
        self.assertEqual(self.git(ci / "hepta-source", "rev-parse", "HEAD"), self.contract["commit"])

    def test_partial_external_binding_fails_before_any_runtime_action(self):
        for name in ("F1_SOURCE_REVIEW_PATH", "F1_SOURCE_REVIEW_SHA256", "F1_HEPTA_SOURCE_ROOT"):
            result = subprocess.run([sys.executable, "-I", "-B", str(HERE / "run_agentd_runtime.py"), "--help"],
                                    env=dict(source.ENV, **{name: "partial"}), capture_output=True, text=True,
                                    timeout=10, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("complete explicit current source review binding", result.stderr)

    def test_actual_final_workflow_check_rejects_a_dirty_compiled_copy(self):
        self.put(self.desktop, "tests/workloads/hepta_agentd_runtime/current_source_review.py",
                 (HERE / "current_source_review.py").read_text())
        self.commit(self.desktop)
        review = self.review()
        external = self.root / "external.json"
        external.write_text(json.dumps(review))
        ci = self.root / "ci"
        ci.mkdir()
        for name, root in (("desktop", self.desktop), ("hepta", self.hepta)):
            subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", str(root), str(ci / (name + "-source"))],
                           env=source.ENV, capture_output=True, check=True)
        workflow = (ROOT / ".github/workflows/f1-original-runtime-native.yml").read_text()
        step = workflow.split("      - name: Verify the exact source pair after guest execution\n", 1)[1]
        step = step.split("      - name:", 1)[0]
        program = textwrap.dedent(step.split("          import importlib.util, os\n", 1)[1].split("          PYCODE", 1)[0])
        program = "import importlib.util, os\n" + program
        environment = dict(source.ENV, F1_SOURCE_REVIEW_PATH=str(external),
                           F1_SOURCE_REVIEW_SHA256=source.digest(external.read_bytes()),
                           GITHUB_WORKSPACE=str(self.desktop), F1_HEPTA_SOURCE_ROOT=str(self.hepta), F1_CI_ROOT=str(ci))
        def run():
            return subprocess.run([sys.executable, "-I", "-B", "-c", program], cwd=self.desktop,
                                  env=environment, capture_output=True, text=True, timeout=20, check=False)
        result = run()
        self.assertEqual(result.returncode, 0, result.stderr)
        (ci / "desktop-source/original_fixture.rs").write_text("unexpected post-build source change")
        result = run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("clean source required", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
