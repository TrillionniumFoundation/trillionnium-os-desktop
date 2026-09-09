#!/usr/bin/env python3
"""Finish S06 current-stack error construction and incarnation contract repair."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_revision_error_fixture() -> None:
    path = ROOT / "crates/hepta-browser-actor-simulation/src/lib.rs"
    import_line = (
        "use trillionnium_contract_core::{RefFreshness, RevisionClock, "
        "classify_reference};\n"
    )
    replacement = import_line + (
        "#[cfg(test)]\n"
        "use trillionnium_contract_core::RevisionError;\n"
    )
    replace_once(path, import_line, replacement, "simulation RevisionError import")
    replace_once(
        path,
        "            TransitionError::RevisionExhausted,\n",
        "            TransitionError::RevisionExhausted(\n"
        "                RevisionError::SessionGenerationExhausted,\n"
        "            ),\n",
        "simulation revision-exhaustion test constructor",
    )


def patch_session_incarnation_contract() -> None:
    path = ROOT / "contracts/session-incarnation.v1.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["entropy_source"] = "actor_private_operating_system_entropy"
    value["entropy_owner"] = "hepta-browser-actor-simulation"
    value["transport_nonce_api_reused"] = False
    value["test_entropy_injection"] = "simulation_crate_unit_tests_only"
    value["document"] = "docs/architecture/SESSION_INCARNATION.md"
    value["required_workflow"] = ".github/workflows/s06-browser-actor.yml"
    value["required_sources"] = [
        "crates/hepta-browser-actor-simulation/src/incarnation.rs",
        "crates/hepta-browser-actor-simulation/src/incarnation_tests.rs",
    ]
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def write_session_incarnation_document() -> None:
    text = '''# Session incarnation boundary

Status: **S06 source/test candidate; no durable anti-rollback or installed runtime**

## Purpose

Each BrowserActor lazily acquires 32 bytes from an actor-private operating-system
entropy source on the first valid session creation. The entropy is domain-separated
and hashed before it participates in the opaque session and WebView identities.
A zero or failed read is latched: the actor cannot fall back to a predictable
namespace and must be reconstructed.

## Ownership and API separation

Incarnation entropy belongs to `hepta-browser-actor-simulation`, not the Agent
transport. The product Transport API does not export nonce-source injection,
fixed nonces, or session nonce material. Unit-test entropy injection is private
to the unpublished simulation crate and cannot be selected by a product caller,
environment variable, wire field, or configuration file.

## Ordering and failure

Counter exhaustion is checked before entropy or runtime work. Entropy acquisition
does not extend the original request deadline. A namespace is read at most once
per actor and is never automatically resurrected after an entropy failure.
Close/create cycles use checked ordinals inside the same namespace; actor
reconstruction creates a different namespace. Previous session, WebView, frame,
and semantic references therefore fail closed.

## Frame identity

A scoped frame identity hashes length-delimited session, WebView and local frame
keys under a separate domain. It is an opaque lookup identity, not proof that a
frame/node exists and not action authority. A concrete engine must still resolve
the current frame and retained node under current revisions.

## Claim ceiling

This mechanism does not prove absolute global uniqueness, durable rollback
resistance, product activation, Servo integration, installed-image behavior,
hardware identity, signing, publication or release readiness.
'''
    (ROOT / "docs/architecture/SESSION_INCARNATION.md").write_text(
        text, encoding="utf-8"
    )


def patch_contract_path_tests() -> None:
    path = ROOT / "tests/test_s06_contract_paths.py"
    old_contracts = '''CONTRACTS = (
    "contracts/engine-thread-dispatch.v1.json",
    "contracts/event-loop-completion.v1.json",
)
'''
    new_contracts = '''CONTRACTS = (
    "contracts/engine-thread-dispatch.v1.json",
    "contracts/event-loop-completion.v1.json",
    "contracts/session-incarnation.v1.json",
)
'''
    replace_once(path, old_contracts, new_contracts, "S06 contract list")

    old_binding = '''        engine = load_contract(CONTRACTS[0])
        event = load_contract(CONTRACTS[1])
        self.assertTrue(
            engine["implementation"].startswith(
                "crates/hepta-browser-actor-simulation/"
            )
        )
        for contract in (engine, event):
            for source in contract["required_sources"]:
                self.assertTrue(
                    source.startswith("crates/hepta-browser-actor-simulation/"),
                    source,
                )
'''
    new_binding = '''        engine = load_contract(CONTRACTS[0])
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
'''
    replace_once(path, old_binding, new_binding, "S06 source binding test")

    insertion = '''    def test_product_contract_closes_generic_runtime_injection(self) -> None:
'''
    method = '''    def test_incarnation_entropy_is_actor_private(self) -> None:
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
'''
    replace_once(path, insertion, method, "S06 incarnation contract test insertion")


def main() -> None:
    patch_revision_error_fixture()
    patch_session_incarnation_contract()
    write_session_incarnation_document()
    patch_contract_path_tests()


if __name__ == "__main__":
    main()
