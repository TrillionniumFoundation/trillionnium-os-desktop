from __future__ import annotations

import copy
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_contract_foundation_under_test",
    ROOT / "tools/validate_contract_foundation.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def registry() -> dict[str, object]:
    return copy.deepcopy(VALIDATOR.EXPECTED_REGISTRY)


def replace_after(source: str, anchor: str, old: str, new: str) -> str:
    start = source.index(anchor)
    index = source.index(old, start)
    return source[:index] + new + source[index + len(old) :]


class ContractFoundationValidationTest(unittest.TestCase):
    def test_validator_passes_repository_state(self) -> None:
        completed = subprocess.run(
            [sys.executable, "tools/validate_contract_foundation.py"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_revision_policy_is_machine_readable(self) -> None:
        value = VALIDATOR.strict_json_loads(
            (ROOT / "contracts/contract-core-constraints.v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(VALIDATOR.validate_registry_data(value), [])
        self.assertEqual(value, VALIDATOR.EXPECTED_REGISTRY)


class StrictRegistryDecoderTest(unittest.TestCase):
    def test_duplicate_and_non_json_numbers_are_rejected(self) -> None:
        hostile = (
            '{"schema":"x","schema":"y"}',
            '{"value":NaN}',
            '{"value":Infinity}',
            '{"value":-Infinity}',
            '{"value":1e999}',
            '{"nested":{"value":NaN}}',
        )
        for encoded in hostile:
            with self.subTest(encoded=encoded), self.assertRaises(ValueError):
                VALIDATOR.strict_json_loads(encoded)

    def test_closed_schema_rejects_omitted_and_extra_fields_at_every_level(self) -> None:
        mutations = []

        value = registry()
        del value["unix_millis"]
        mutations.append(("missing root", value))

        value = registry()
        value["unexpected"] = {}
        mutations.append(("extra root", value))

        sections = {
            "bounded_identifiers": "allowed_ascii",
            "dns_label": "pattern",
            "revision_clock": "counter_type",
            "sha256_hex": "alphabet",
            "unix_millis": "rust_type",
        }
        for section, key in sections.items():
            value = registry()
            del value[section][key]  # type: ignore[index]
            mutations.append((f"missing {section}.{key}", value))

            value = registry()
            value[section]["unexpected"] = True  # type: ignore[index]
            mutations.append((f"extra {section}", value))

        value = registry()
        value["revision_clock"]["initial"] = {}  # type: ignore[index]
        mutations.append(("empty initial", value))

        value = registry()
        del value["revision_clock"]["initial"]["mutation_epoch"]  # type: ignore[index]
        mutations.append(("missing initial field", value))

        value = registry()
        value["revision_clock"]["initial"]["unexpected"] = 1  # type: ignore[index]
        mutations.append(("extra initial field", value))

        for label, value in mutations:
            with self.subTest(label=label):
                self.assertTrue(
                    VALIDATOR.validate_registry_data(value),
                    f"mutation unexpectedly accepted: {label}",
                )

    def test_every_declared_value_and_type_is_bound(self) -> None:
        mutations = {
            "allowed alphabet": (
                ("bounded_identifiers", "allowed_ascii"),
                "A-Z a-z 0-9",
            ),
            "request bound": (
                ("bounded_identifiers", "request_id_max_utf8_bytes"),
                129,
            ),
            "boolean is not integer": (
                ("bounded_identifiers", "lease_id_max_utf8_bytes"),
                True,
            ),
            "DNS maximum": (("dns_label", "max_ascii_bytes"), 64),
            "DNS pattern": (("dns_label", "pattern"), ".*"),
            "counter type": (("revision_clock", "counter_type"), "usize"),
            "overflow policy": (
                ("revision_clock", "overflow_policy"),
                "saturate",
            ),
            "initial session": (
                ("revision_clock", "initial", "session_generation"),
                0,
            ),
            "digest alphabet": (("sha256_hex", "alphabet"), "0123456789ABCDEF"),
            "digest length": (("sha256_hex", "length_ascii_bytes"), 63),
            "Unix milliseconds type": (("unix_millis", "rust_type"), "u64"),
        }
        for label, (path, replacement) in mutations.items():
            value = registry()
            cursor = value
            for component in path[:-1]:
                cursor = cursor[component]  # type: ignore[index,assignment]
            cursor[path[-1]] = replacement  # type: ignore[index]
            with self.subTest(label=label):
                self.assertTrue(VALIDATOR.validate_registry_data(value))


class SyntaxScopedSourceAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.core = (
            ROOT / "crates/trillionnium-contract-core/src/lib.rs"
        ).read_text(encoding="utf-8")
        cls.session = (
            ROOT / "crates/hepta-session-core/src/machine.rs"
        ).read_text(encoding="utf-8")

    def test_current_sources_pass_the_scoped_audits(self) -> None:
        self.assertEqual(VALIDATOR.audit_core_source(self.core), [])
        self.assertEqual(VALIDATOR.audit_session_source(self.session), [])

    def test_comment_or_out_of_scope_dead_code_cannot_replace_revision_propagation(self) -> None:
        cases = {
            "dom": ("SessionEvent::DomCommitted", ".on_dom_commit()"),
            "semantic": (
                "SessionEvent::SemanticSnapshotPublished",
                ".on_semantic_snapshot()",
            ),
            "navigation": (
                "SessionEvent::NavigationCommitted",
                ".on_navigation_commit()",
            ),
            "recovery": (
                "SessionEvent::BrowserCrashed",
                ".on_process_recovery()",
            ),
        }
        for label, (anchor, call) in cases.items():
            mutated = replace_after(
                self.session, anchor, call, call.replace("()", "_disabled()")
            )
            mutated += (
                "\n// decoy: self.revisions"
                + call
                + ".map_err(TransitionError::RevisionExhausted)?;\n"
                + "fn out_of_scope_decoy(machine: &mut SessionMachine) { "
                + "let _ = machine.revisions"
                + call
                + ".map_err(TransitionError::RevisionExhausted); }\n"
            )
            with self.subTest(label=label):
                errors = VALIDATOR.audit_session_source(mutated)
                self.assertTrue(errors)
                self.assertTrue(any(anchor in error for error in errors), errors)

    def test_each_lease_overflow_path_is_independently_required(self) -> None:
        for variant in (
            "SessionEvent::HumanFocusGained",
            "SessionEvent::HumanInput",
        ):
            mutated = replace_after(
                self.session,
                variant,
                ".checked_add(",
                ".checked_add_disabled(",
            )
            mutated += (
                "\n// now_ms.checked_add(extension)"
                ".ok_or(TransitionError::TimeOverflow)?;\n"
            )
            with self.subTest(variant=variant):
                errors = VALIDATOR.audit_session_source(mutated)
                self.assertTrue(any(variant in error for error in errors), errors)

    def test_every_multi_counter_preflight_is_independently_required(self) -> None:
        cases = {
            "on_navigation_commit": (
                "document_generation",
                "semantic_snapshot_revision",
                "mutation_epoch",
            ),
            "on_process_recovery": (
                "session_generation",
                "document_generation",
                "semantic_snapshot_revision",
                "mutation_epoch",
            ),
        }
        for method, fields in cases.items():
            for field in fields:
                old = f"self\n            .{field}\n            .checked_add(1)"
                if old not in self.core:
                    old = f"self.{field}.checked_add(1)"
                mutated = replace_after(
                    self.core,
                    f"pub fn {method}",
                    old,
                    old.replace("checked_add", "checked_add_disabled"),
                )
                mutated += f"\n// let {field} = self.{field}.checked_add(1);\n"
                with self.subTest(method=method, field=field):
                    errors = VALIDATOR.audit_core_source(mutated)
                    self.assertTrue(
                        any(method in error and field in error for error in errors),
                        errors,
                    )


if __name__ == "__main__":
    unittest.main()
