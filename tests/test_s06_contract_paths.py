from __future__ import annotations

import copy
import json
from pathlib import Path, PurePosixPath
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = (
    "contracts/engine-thread-dispatch.v1.json",
    "contracts/event-loop-completion.v1.json",
    "contracts/session-incarnation.v1.json",
)
PATH_FIELDS = (
    "implementation",
    "required_sources",
    "required_document",
    "document",
    "required_workflow",
)


def reject_duplicate(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def reject_constant(value):
    raise ValueError(f"non-JSON constant: {value}")


def load_contract(relative: str) -> dict:
    value = json.loads(
        (ROOT / relative).read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate,
        parse_constant=reject_constant,
    )
    if not isinstance(value, dict):
        raise ValueError(f"{relative} is not an object")
    return value


def required_paths(contract: dict) -> list[str]:
    output: list[str] = []
    for field in PATH_FIELDS:
        value = contract.get(field)
        if value is None:
            continue
        if isinstance(value, str):
            output.append(value)
        elif isinstance(value, list) and all(isinstance(item, str) for item in value):
            output.extend(value)
        else:
            raise ValueError(f"{field} must be a path or path list")
    return output


def path_errors(contract: dict) -> list[str]:
    errors: list[str] = []
    try:
        paths = required_paths(contract)
    except ValueError as error:
        return [str(error)]
    for value in paths:
        parsed = PurePosixPath(value)
        if (
            not value
            or value != value.strip()
            or parsed.is_absolute()
            or parsed.as_posix() != value
            or any(part in {"", ".", ".."} for part in parsed.parts)
            or "\\" in value
        ):
            errors.append(f"unsafe path: {value!r}")
            continue
        target = ROOT.joinpath(*parsed.parts)
        if not target.is_file():
            errors.append(f"missing required file: {value}")
    return errors


class S06ContractPathTests(unittest.TestCase):
    def test_every_declared_required_path_resolves(self) -> None:
        for relative in CONTRACTS:
            with self.subTest(contract=relative):
                contract = load_contract(relative)
                self.assertFalse(path_errors(contract), path_errors(contract))

    def test_paths_bind_the_internal_simulation_crate(self) -> None:
        engine = load_contract(CONTRACTS[0])
        event = load_contract(CONTRACTS[1])
        incarnation = load_contract(CONTRACTS[2])
        self.assertTrue(
            engine["implementation"].startswith(
                "crates/hepta-browser-actor-simulation/"
            )
        )
        for contract in (engine, event, incarnation):
            for source in contract["required_sources"]:
                self.assertTrue(
                    source.startswith("crates/hepta-browser-actor-simulation/"),
                    source,
                )

    def test_missing_traversal_absolute_and_wrong_type_mutations_fail(self) -> None:
        baseline = load_contract(CONTRACTS[0])
        mutations = []
        for value in (
            "does/not/exist.rs",
            "../outside.rs",
            "/tmp/outside.rs",
            "crates\\outside.rs",
        ):
            candidate = copy.deepcopy(baseline)
            candidate["implementation"] = value
            mutations.append(candidate)
        candidate = copy.deepcopy(baseline)
        candidate["required_sources"] = {"path": "not-a-list"}
        mutations.append(candidate)
        for candidate in mutations:
            with self.subTest(candidate=candidate.get("implementation")):
                self.assertTrue(path_errors(candidate))

    def test_incarnation_entropy_is_actor_private(self) -> None:
        contract = load_contract("contracts/session-incarnation.v1.json")
        self.assertEqual(
            contract["entropy_source"],
            "actor_private_operating_system_entropy",
        )
        self.assertEqual(
            contract["entropy_owner"],
            "hepta-browser-actor-simulation",
        )
        self.assertFalse(contract["transport_nonce_api_reused"])
        self.assertEqual(
            contract["test_entropy_injection"],
            "simulation_crate_unit_tests_only",
        )
        self.assertFalse(contract["caller_namespace_selection"])
        self.assertFalse(contract["production_fault_injection"])
        self.assertFalse(contract["automatic_session_resurrection"])

    def test_product_contract_closes_generic_runtime_injection(self) -> None:
        contract = load_contract("contracts/browser-actor.v1.json")
        authority = contract["authority_boundary"]
        actor = contract["browser_actor"]
        self.assertFalse(authority["product_actor_generic_over_runtime"])
        self.assertFalse(authority["caller_supplied_runtime_adapter"])
        self.assertFalse(authority["runtime_trait_publicly_exported"])
        self.assertFalse(authority["request_control_publicly_exported"])
        self.assertFalse(
            authority["deferred_work_after_terminal_success_representable"]
        )
        self.assertEqual(
            authority["product_runtime_type"],
            "actor_owned_deterministic_local_runtime",
        )
        self.assertFalse(actor["generic_runtime_injection"])
        self.assertTrue(
            actor["later_servo_adapter_requires_distinct_concrete_reviewed_type"]
        )


if __name__ == "__main__":
    unittest.main()
