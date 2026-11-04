"""Negative fixtures for documentation coverage and navigation regressions."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location("check_modules", Path(__file__).with_name("check_modules.py"))
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "docs").mkdir()
        (self.root / "docs/target.md").write_text("# API & 权限\n## Same\n## Same\n<a id=\"explicit\"></a>\n")

    def test_unicode_punctuation_and_duplicate_heading(self):
        self.assertEqual(checker.heading_anchors((self.root / "docs/target.md").read_text()),
                         {"api--权限", "same", "same-1", "explicit"})

    def test_heading_inside_fenced_example_is_not_a_target(self):
        self.assertEqual(checker.heading_anchors("# Real\n~~~md\n# False\n~~~\n"), {"real"})

    def test_inline_angle_and_reference_destinations(self):
        links = checker.markdown_links('[a](target.md#same "title") [b](<space name.md>)\n[id]: target.md#explicit\n')
        self.assertEqual(links, ["target.md#same", "space name.md", "target.md#explicit"])

    def test_fenced_example_links_are_ignored(self):
        self.assertEqual(checker.markdown_links("```sh\n[a](missing.md)\n```\n[a](target.md)"), ["target.md"])

    def test_actual_relative_and_same_document_anchors(self):
        checker.check_reference(self.root, "docs/from.md", "target.md#same-1")
        checker.check_reference(self.root, "docs/target.md", "#api--权限")

    def test_external_destinations_are_not_fetched(self):
        self.assertIsNone(checker.check_reference(self.root, "docs/from.md", "https://example.invalid/missing#none"))

    def test_missing_file_and_missing_heading_fail(self):
        with self.assertRaisesRegex(ValueError, "missing target"):
            checker.check_reference(self.root, "docs/from.md", "missing.md")
        with self.assertRaisesRegex(ValueError, "missing heading"):
            checker.check_reference(self.root, "docs/from.md", "target.md#missing")

    def test_escaped_repository_target_fails(self):
        with self.assertRaisesRegex(ValueError, "escapes repository"):
            checker.check_reference(self.root, "docs/from.md", "../../outside.md")


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "libs/demo").mkdir(parents=True)
        (self.root / "libs/demo/Cargo.toml").write_text('[package]\nname="demo"\nversion="0.1.0"\n')
        (self.root / "libs/demo/lib.rs").write_text("//! Actual demo source entry\n")
        (self.root / "libs/demo/README.md").write_text("# Demo\n" + "Concrete module owner, errors, build and recovery behavior. " * 8)
        self.record = {
            "manifest": "libs/demo/Cargo.toml", "package": "demo", "entry": "libs/demo/README.md",
            "sources": ["libs/demo/lib.rs"],
            "technical": ["libs/demo/README.md"], "development": ["libs/demo/README.md"],
            "owner": "This fixture owns its exact demo state and never borrows authority from a title.",
            "failure_recovery": "An unknown operation must recover the original owner status before another effect is possible.",
            "current_scope": "This static fixture covers one local package and establishes no runtime execution proof.",
        }

    def check(self, records=None, manifests=None):
        return checker.check_catalogue(self.root, {"schema_version": 1, "packages": records or [self.record]},
                                       manifests or [self.record["manifest"]])[0]

    def test_concrete_package_contract_passes(self):
        self.assertEqual(self.check(), [])

    def test_added_manifest_requires_documented_mapping(self):
        errors = self.check(manifests=[self.record["manifest"], "libs/new/Cargo.toml"])
        self.assertIn("unmapped first-party Cargo manifest: libs/new/Cargo.toml", errors)

    def test_renamed_package_and_duplicate_mapping_fail(self):
        self.record["package"] = "old-name"
        errors = self.check(records=[self.record, self.record])
        self.assertTrue(any("package name differs" in error for error in errors))
        self.assertTrue(any("duplicate module manifest" in error for error in errors))

    def test_empty_template_or_missing_recovery_contract_fails(self):
        self.record["failure_recovery"] = "TODO"
        (self.root / "libs/demo/README.md").write_text("# TODO\n")
        errors = self.check()
        self.assertTrue(any("substantive failure_recovery" in error for error in errors))
        self.assertTrue(any("too short" in error for error in errors))

    def test_nonlocal_technical_contract_is_rejected(self):
        self.record["technical"] = ["https://example.invalid/only-external"]
        self.assertTrue(any("must be local Markdown" in error for error in self.check()))

    def test_missing_technical_document_fails(self):
        self.record["technical"] = []
        self.assertTrue(any("missing technical document" in error for error in self.check()))

    def test_missing_actual_source_fails(self):
        (self.root / "libs/demo/lib.rs").unlink()
        self.assertTrue(any("missing source" in error for error in self.check()))

    def test_existing_source_outside_repository_fails(self):
        with tempfile.NamedTemporaryFile() as outside:
            self.record["sources"] = [outside.name]
            self.assertTrue(any("missing source" in error for error in self.check()))

    def domains(self):
        return [{"id": identity, **self.record} for identity in (
            "A00", "A01", "A02", "A03", "A04", "A05", "A06", "A07", "A08", "A09", "A10",
        )]

    def test_complete_domain_set_and_duplicate_identity(self):
        domains = self.domains()
        self.assertEqual(checker.check_domains(self.root, {"domains": domains})[0], [])
        errors = checker.check_domains(self.root, {"domains": domains + [domains[0]]})[0]
        self.assertTrue(any("duplicate development domain" in error for error in errors))

    def test_each_required_domain_cannot_be_omitted(self):
        domains = self.domains()
        for omitted in domains:
            with self.subTest(omitted=omitted["id"]):
                remaining = [domain for domain in domains if domain is not omitted]
                errors = checker.check_domains(self.root, {"domains": remaining})[0]
                self.assertIn("missing development domains: " + omitted["id"], errors)

    def test_only_a00_cannot_stand_in_for_all_domains(self):
        errors = checker.check_domains(self.root, {"domains": [self.domains()[0]]})[0]
        self.assertTrue(any("missing development domains: A01, A02" in error for error in errors))

    def test_only_unknown_domain_fails(self):
        errors = checker.check_domains(self.root, {"domains": [{"id": "A99", **self.record}]})[0]
        self.assertIn("unexpected development domains: A99", errors)
        self.assertTrue(any("missing development domains: A00, A01" in error for error in errors))

    def test_extra_domain_fails_even_with_complete_required_set(self):
        domains = self.domains() + [{"id": "A99", **self.record}]
        errors = checker.check_domains(self.root, {"domains": domains})[0]
        self.assertIn("unexpected development domains: A99", errors)

    def test_unknown_domain_cannot_replace_a_required_domain(self):
        domains = self.domains()
        domains[-1] = {"id": "A99", **self.record}
        errors = checker.check_domains(self.root, {"domains": domains})[0]
        self.assertIn("missing development domains: A10", errors)
        self.assertIn("unexpected development domains: A99", errors)

    def test_invalid_domain_identity_is_reported_without_crashing(self):
        for identity in ("A0", "a00", "A000", None, 0, ["A00"]):
            with self.subTest(identity=identity):
                domains = self.domains() + [{"id": identity, **self.record}]
                errors = checker.check_domains(self.root, {"domains": domains})[0]
                self.assertTrue(any("invalid or duplicate development domain" in error for error in errors))

    def test_absent_cross_module_domain_map_fails(self):
        self.assertTrue(checker.check_domains(self.root, {})[0])

    def test_kernel_section_needs_unique_labels_and_own_sources(self):
        base = self.root / "kernel/asterinas"
        (base / "core/src").mkdir(parents=True)
        (base / "Cargo.toml").write_text('[workspace]\nmembers=["core"]\n')
        (base / "core/Cargo.toml").write_text('[package]\nname="kernel-demo"\nversion="0.1.0"\n')
        (base / "core/src/lib.rs").write_text("//! Kernel demo\n")
        book = self.root / "book.md"
        section = "## kernel-demo\n\n" + "\n".join(checker.HANDBOOK_LABELS)
        section += "\n[manifest](kernel/asterinas/core/Cargo.toml) [source](kernel/asterinas/core/src/lib.rs)\n"
        book.write_text(section)
        catalogue = {"kernel_workspace": "kernel/asterinas/Cargo.toml", "kernel_handbooks": ["book.md"]}
        self.assertEqual(checker.check_kernel(self.root, catalogue)[0], [])
        book.write_text(section.replace(checker.HANDBOOK_LABELS[1], ""))
        self.assertTrue(any("missing contract" in error for error in checker.check_kernel(self.root, catalogue)[0]))
        book.write_text(section + "\n" + section)
        # A duplicate same-name section in one book must not silently pass.
        errors = checker.check_kernel(self.root, catalogue)[0]
        self.assertTrue(any("exactly one" in error for error in errors))


class CurrentSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.commit = "1" * 40
        self.tree = "2" * 40
        self.previous = "3" * 40
        self.contract = self.root / "support/ui/HEPTA_SHARED_PRESENTER.json"
        self.contract.parent.mkdir(parents=True)
        self.contract.write_text(json.dumps({"commit": self.commit, "tree": self.tree}))
        self.current = (
            "<!-- current-hepta-source:start -->\n"
            "| Input | Identity |\n| --- | --- |\n"
            f"| Hepta commit | [`{self.commit}`](https://github.com/TrillionniumFoundation/"
            f"hepta-private-ci/commit/{self.commit}) |\n"
            f"| Hepta tree | `{self.tree}` |\n"
            f"[Owner](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/"
            f"{self.commit}/OWNER.md)\n"
            "<!-- current-hepta-source:end -->\n"
        )
        self.history = (
            "\n## Historical receipt\n"
            f"[Old source](https://github.com/TrillionniumFoundation/hepta-private-ci/commit/"
            f"{self.previous}) retained without successor qualification.\n"
        )
        for name in ("README.md", "docs/CURRENT_CAPABILITIES.md", "docs/SOURCES.md"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# Product\n\n" + self.current + self.history)

    def check(self):
        return checker.check_current_sources(self.root)

    def replace_current(self, current):
        (self.root / "README.md").write_text("# Product\n\n" + current + self.history)

    def test_current_source_matches_canonical_and_history_is_preserved(self):
        errors, documents = self.check()
        self.assertEqual(errors, [])
        self.assertEqual(documents, {"README.md", "docs/CURRENT_CAPABILITIES.md", "docs/SOURCES.md"})

    def test_stale_current_commit_fails(self):
        self.replace_current(self.current.replace(self.commit, self.previous))
        self.assertTrue(any("Hepta commit differs" in error for error in self.check()[0]))

    def test_stale_current_tree_fails(self):
        self.replace_current(self.current.replace(self.tree, self.previous))
        self.assertTrue(any("Hepta tree differs" in error for error in self.check()[0]))

    def test_stale_current_owner_link_fails_with_correct_declaration(self):
        self.replace_current(self.current.replace(f"/blob/{self.commit}/", f"/blob/{self.previous}/"))
        self.assertTrue(any("current Hepta link differs" in error for error in self.check()[0]))

    def test_moving_current_owner_link_fails(self):
        self.replace_current(self.current.replace(f"/blob/{self.commit}/", "/blob/main/"))
        self.assertTrue(any("current Hepta link differs" in error for error in self.check()[0]))

    def test_current_source_marker_must_be_unique_complete_and_ordered(self):
        start = "<!-- current-hepta-source:start -->"
        end = "<!-- current-hepta-source:end -->"
        for bad in (self.current.replace(start, ""), self.current.replace(end, ""),
                    self.current + self.current, end + self.current.replace(end, "")):
            with self.subTest(current=bad):
                self.replace_current(bad)
                self.assertTrue(any("current Hepta source block" in error for error in self.check()[0]))

    def test_identity_rows_must_be_unique_and_present(self):
        for field, value in (("commit", self.commit), ("tree", self.tree)):
            marker = f"| Hepta {field} |"
            row = next(line for line in self.current.splitlines() if line.startswith(marker))
            for bad in (self.current.replace(row + "\n", ""),
                        self.current.replace(row + "\n", row + "\n" + row + "\n")):
                with self.subTest(field=field, current=bad):
                    self.replace_current(bad)
                    self.assertTrue(any(f"Hepta {field} differs" in error for error in self.check()[0]))

    def test_overlong_current_identity_is_rejected(self):
        for field, value in (("commit", self.commit), ("tree", self.tree)):
            with self.subTest(field=field):
                self.replace_current(self.current.replace(f"`{value}`", f"`{value}0`"))
                self.assertTrue(any(f"Hepta {field} differs" in error for error in self.check()[0]))

    def test_canonical_source_change_requires_current_document_update(self):
        self.contract.write_text(json.dumps({"commit": self.previous, "tree": self.tree}))
        self.assertTrue(any("Hepta commit differs" in error for error in self.check()[0]))

    def test_invalid_canonical_identity_fails_closed(self):
        for contract in ({"commit": "main", "tree": self.tree},
                         {"commit": self.commit, "tree": ""}):
            with self.subTest(contract=contract):
                self.contract.write_text(json.dumps(contract))
                with self.assertRaisesRegex(ValueError, "canonical Hepta"):
                    self.check()


if __name__ == "__main__":
    unittest.main()
