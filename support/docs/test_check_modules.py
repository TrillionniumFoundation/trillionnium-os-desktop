"""Negative fixtures for documentation coverage and navigation regressions."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location("check_modules", Path(__file__).with_name("check_modules.py"))
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)

DOMAIN_IDS = ("A00", "A01", "A02", "A03", "A04", "A05", "A06", "A07", "A08", "A09", "A10")


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

    def test_domain_contract_and_duplicate_identity(self):
        domains = [{"id": identity, **self.record} for identity in DOMAIN_IDS]
        self.assertEqual(checker.check_domains(self.root, {"domains": domains})[0], [])
        self.assertEqual(checker.check_domains(self.root, {"domains": domains[::-1]})[0], [])
        errors = checker.check_domains(self.root, {"domains": domains + [domains[0]]})[0]
        self.assertTrue(any("duplicate development domain" in error for error in errors))

    def test_absent_cross_module_domain_map_fails(self):
        errors = checker.check_domains(self.root, {})[0]
        self.assertEqual(set(errors), {"missing development domain: " + identity for identity in DOMAIN_IDS})

    def test_each_required_domain_cannot_be_removed(self):
        for missing in DOMAIN_IDS:
            with self.subTest(missing=missing):
                domains = [{"id": identity, **self.record} for identity in DOMAIN_IDS if identity != missing]
                errors = checker.check_domains(self.root, {"domains": domains})[0]
                self.assertEqual(errors, ["missing development domain: " + missing])

    def test_unexpected_domain_cannot_extend_documented_scope(self):
        domains = [{"id": identity, **self.record} for identity in DOMAIN_IDS]
        for extra in ("A11", "A99"):
            with self.subTest(extra=extra):
                records = domains + [{"id": extra, **self.record}]
                errors = checker.check_domains(self.root, {"domains": records})[0]
                self.assertEqual(errors, ["unexpected development domain: " + extra])

    def test_replacement_cannot_hide_missing_domain_at_same_count(self):
        domains = [{"id": identity, **self.record} for identity in DOMAIN_IDS if identity != "A10"]
        domains.append({"id": "A11", **self.record})
        self.assertEqual(len(domains), 11)
        errors = checker.check_domains(self.root, {"domains": domains})[0]
        self.assertEqual(set(errors), {"missing development domain: A10", "unexpected development domain: A11"})

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


if __name__ == "__main__":
    unittest.main()
