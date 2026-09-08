"""Mutation regressions for both real documentation validator entrypoints."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import unittest

from tests import test_component_documentation as component_tests
from tests import test_module_documentation as module_tests
from tools.documentation_claims import validate_claim_projection


@contextmanager
def fixture_for(kind: str):
    if kind == "module":
        fixture = module_tests.ModuleDocumentationValidatorTests()
        readme, registry, key = "crates/example/README.md", "manifests/modules.v1.json", "modules"
    else:
        fixture = component_tests.ComponentDocumentationValidatorTests()
        readme, registry, key = "tools/README.md", "manifests/components.v1.json", "components"
    fixture.setUp()
    try:
        yield fixture, fixture.root / readme, fixture.root / registry, key
    finally:
        fixture.tearDown()


class DocumentationClaimProjectionTests(unittest.TestCase):
    def mutate_readme(self, mutation) -> None:
        for kind in ("module", "component"):
            with self.subTest(kind=kind), fixture_for(kind) as (fixture, path, _, _):
                self.assertEqual(fixture.validate(), [])
                path.write_text(mutation(path.read_text(encoding="utf-8")), encoding="utf-8")
                self.assertTrue(fixture.validate(), "hostile README mutation was accepted")

    def test_readme_only_claim_expansion_fails(self) -> None:
        self.mutate_readme(lambda text: "\n".join(
            "**Claim ceiling:** production release ready; unrestricted effects."
            if line.startswith("**Claim ceiling:**") else line for line in text.split("\n")
        ))

    def test_readme_only_status_expansion_fails(self) -> None:
        self.mutate_readme(lambda text: text.replace("`source_candidate`", "`production_ready`")
                           .replace("`source_policy_active`", "`production_ready`"))

    def test_registry_only_status_and_claim_changes_fail(self) -> None:
        for kind in ("module", "component"):
            for field in ("status", "claim_ceiling"):
                with self.subTest(kind=kind, field=field), fixture_for(kind) as (fixture, _, path, key):
                    self.assertEqual(fixture.validate(), [])
                    registry = json.loads(path.read_text())
                    registry[key][0][field] = "production_ready"
                    path.write_text(json.dumps(registry))
                    self.assertTrue(fixture.validate())

    def test_missing_status_or_claim_fails(self) -> None:
        for label in ("Current status:", "Claim ceiling:"):
            with self.subTest(label=label):
                self.mutate_readme(lambda text: "\n".join(
                    line for line in text.split("\n") if label not in line
                ))

    def test_duplicate_identical_claims_fail(self) -> None:
        for label in ("Current status:", "Claim ceiling:"):
            with self.subTest(label=label):
                self.mutate_readme(lambda text: text + "\n" + next(
                    line for line in text.splitlines() if label in line
                ) + "\n")

    def test_disguised_conflicting_claims_fail(self) -> None:
        for declaration in (
            "**Claim ceiling:** production release ready.",
            "**cLaIm CeIlInG:** production release ready.",
            "**Claim   ceiling:** production release ready.",
            "**Claim\tceiling:** production release ready.",
            "**Claim\nceiling:** production release ready.",
            "**Ｃｌａｉｍ ｃｅｉｌｉｎｇ：** production release ready.",
            "**Claim\u200b ceiling:** production release ready.",
            "**Claim&#32;ceiling:** production release ready.",
            "**Current status:** `production_ready`",
            "current\nstatus = production_ready",
            "CURRENT STATUS: production_ready",
            "**Ｓｔａｔｕｓ：** production_ready",
            "Status: production_ready",
            "> **Claim ceiling:** production release ready.",
            "<!-- **Claim ceiling:** production release ready. -->",
            "```\n**Claim ceiling:** production release ready.\n```",
        ):
            with self.subTest(declaration=declaration):
                self.mutate_readme(lambda text: text + "\n" + declaration + "\n")

    def test_noncanonical_whitespace_and_case_fail(self) -> None:
        for transform in (
            lambda line: " " + line,
            lambda line: line + " ",
            lambda line: line.replace("Claim ceiling", "Claim  ceiling"),
            lambda line: line.replace("Claim ceiling", "CLAIM CEILING"),
            lambda line: line.replace(":** ", ":**\t"),
        ):
            self.mutate_readme(lambda text: "\n".join(
                transform(line) if line.startswith("**Claim ceiling:**") else line
                for line in text.split("\n")
            ))

    def test_declarations_in_fences_or_comments_fail(self) -> None:
        for before, after in (("```", "```"), ("~~~", "~~~"), ("<!--", "-->")):
            with self.subTest(before=before):
                self.mutate_readme(lambda text: "\n".join(
                    f"{before}\n{line}\n{after}" if line.startswith("**Claim ceiling:**") else line
                    for line in text.split("\n")
                ))

    def test_declaration_outside_claim_section_fails(self) -> None:
        def move(text):
            claim = next(line for line in text.splitlines() if line.startswith("**Claim ceiling:**"))
            return text.replace(claim, "", 1) + "\n" + claim + "\n"
        self.mutate_readme(move)

    def test_claim_section_in_comment_fails(self) -> None:
        self.mutate_readme(lambda text: text.replace(
            "## Status and claim ceiling",
            "<!--\n## Status and claim ceiling\n-->",
        ))

    def test_claim_moved_after_h1_fails(self) -> None:
        self.mutate_readme(lambda text: text.replace(
            "**Claim ceiling:**", "# Different scope\n**Claim ceiling:**", 1,
        ))

    def test_oversized_document_fails_before_parsing(self) -> None:
        self.assertTrue(validate_claim_projection(
            "x" * 1_048_577, "source_candidate", "source only", kind="module", label="x",
        ))

    def test_short_fences_and_html_cannot_hide_authority(self) -> None:
        for before, after in (
            ("````\n```", "````"), ("~~~~~\n~~~", "~~~~~"),
            ("<script>", "</script>"), ("<style>", "</style>"),
            ("<pre>", "</pre>"), ("<div>", "</div>"),
            ("<!--\n--><!--", "-->"), ("`", "`"),
        ):
            with self.subTest(before=before):
                self.mutate_readme(lambda text: "\n".join(
                    f"{before}\n{line}\n{after}" if line.startswith("**Claim ceiling:**") else line
                    for line in text.split("\n")
                ))

    def test_valid_fenced_examples_after_metadata_remain_allowed(self) -> None:
        for kind in ("module", "component"):
            with fixture_for(kind) as (fixture, path, _, _):
                path.write_text(path.read_text() + "\n```python\nprint('example')\n```\n")
                self.assertEqual(fixture.validate(), [])

    def test_component_duplicate_or_reordered_sections_fail(self) -> None:
        for mode in ("duplicate", "reorder", "suffix"):
            with self.subTest(mode=mode), fixture_for("component") as (fixture, path, _, _):
                text = path.read_text()
                if mode == "duplicate":
                    text += "\n## Security invariants\n"
                elif mode == "reorder":
                    text = text.replace("## Responsibilities", "## Non-responsibilities", 1)
                    offset = text.index("## Non-responsibilities", text.index("## Non-responsibilities") + 1)
                    text = text[:offset] + text[offset:].replace("## Non-responsibilities", "## Responsibilities", 1)
                else:
                    text = text.replace("## Security invariants\n", "## Security invariants extra\n")
                path.write_text(text)
                self.assertTrue(fixture.validate())

    def test_component_symlink_root_is_rejected(self) -> None:
        with fixture_for("component") as (fixture, _, _, _):
            alias = fixture.root.parent / (fixture.root.name + "-link")
            try:
                alias.symlink_to(fixture.root, target_is_directory=True)
                self.assertTrue(component_tests.VALIDATOR.validate(alias, expected_paths={"tools"}))
            finally:
                alias.unlink(missing_ok=True)

    def test_undecodable_direct_text_is_rejected(self) -> None:
        self.assertTrue(validate_claim_projection("\ud800", "valid", "source only", kind="module", label="x"))

    def test_bad_registry_values_fail_closed(self) -> None:
        for status, claim in ((None, "source only"), ("SOURCE", "source only"),
                              ("valid", "source\nonly"), ("valid", " source only"),
                              ("valid", "source\u200bonly"), ("valid", "<b>source</b>")):
            with self.subTest(status=status, claim=claim):
                self.assertTrue(validate_claim_projection("", status, claim, kind="module", label="x"))

    def test_committed_registry_projections_are_exact(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for kind, filename, key in (("module", "modules.v1.json", "modules"),
                                    ("component", "components.v1.json", "components")):
            registry = json.loads((root / "manifests" / filename).read_text())
            for entry in registry[key]:
                with self.subTest(kind=kind, entry=entry["id"]):
                    text = (root / entry["documentation"]).read_text()
                    self.assertEqual(validate_claim_projection(
                        text, entry["status"], entry["claim_ceiling"], kind=kind, label=entry["id"],
                    ), [])


if __name__ == "__main__":
    unittest.main()
