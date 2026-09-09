from __future__ import annotations

import json
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_MEMBERS = [
    "apps/hepta-browserd",
    "apps/hepta-agent-portd",
    "crates/hepta-agent-transport",
    "crates/hepta-browser-codec",
    "crates/hepta-agent-port",
    "crates/hepta-peer-attestation",
    "crates/trillionnium-contract-core",
    "crates/hepta-browser-contracts",
    "crates/hepta-session-core",
    "crates/hepta-workspace-composition",
    "crates/hepta-browser-actor",
    "crates/hepta-browser-actor-simulation",
]


def load_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def direct_dependency_names(manifest: dict) -> set[str]:
    names: set[str] = set()
    for section in ("dependencies", "dev-dependencies", "build-dependencies"):
        names.update(manifest.get(section, {}))
    for target in manifest.get("target", {}).values():
        for section in ("dependencies", "dev-dependencies", "build-dependencies"):
            names.update(target.get(section, {}))
    return names


class BrowserActorAuthorityBoundaryTests(unittest.TestCase):
    def test_workspace_and_machine_source_state_match_exactly(self) -> None:
        workspace = load_toml(ROOT / "Cargo.toml")["workspace"]
        self.assertEqual(workspace["members"], EXPECTED_MEMBERS)
        self.assertEqual(workspace["default-members"], EXPECTED_MEMBERS)
        source_state = json.loads(
            (ROOT / "docs/source-state.v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(source_state["schema"], "trillionnium.desktop.source-state.v1")
        self.assertEqual(source_state["workspace_members"], EXPECTED_MEMBERS)
        self.assertEqual(source_state["claim_ceiling"], "repository_source_tree_only")

    def test_only_product_wrapper_directly_depends_on_simulation_crate(self) -> None:
        dependents = []
        manifests = sorted((ROOT / "apps").glob("*/Cargo.toml")) + sorted(
            (ROOT / "crates").glob("*/Cargo.toml")
        )
        for path in manifests:
            if "hepta-browser-actor-simulation" in direct_dependency_names(load_toml(path)):
                dependents.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(dependents, ["crates/hepta-browser-actor/Cargo.toml"])
        simulation = load_toml(
            ROOT / "crates/hepta-browser-actor-simulation/Cargo.toml"
        )
        self.assertFalse(simulation["package"]["publish"])
        self.assertFalse(simulation["lib"]["doctest"])

    def test_product_api_has_no_generic_or_caller_supplied_runtime(self) -> None:
        source = (ROOT / "crates/hepta-browser-actor/src/lib.rs").read_text(
            encoding="utf-8"
        )
        for required in (
            "pub struct BrowserActor {",
            "pub fn from_attested(",
            "pub fn handle_attested(",
            "attested.refresh_snapshot(attestor)",
            "simulation::PrincipalBinding::bind_attested",
            "simulation::DeterministicLocalRuntime::default()",
            ".handle_attested(context, request, attestor, attested)",
        ):
            self.assertIn(required, source)
        for forbidden in (
            "pub struct BrowserActor<",
            "impl<R: PageRuntime>",
            "runtime: R",
            "PageRuntime,",
            "RequestControl,",
            "RuntimeReply,",
            "pub use hepta_session_core::{ReceiptJournal, SessionEvent",
            "pub fn apply_session_event(",
            ".apply_session_event(event, now_ms)",
            "pub fn new(",
            "BrowserRequestHandler for BrowserActor",
            "pub use hepta_browser_actor_simulation::PrincipalBinding",
            "pub type PrincipalBinding",
            "pub use hepta_browser_actor_simulation::MechanismIdentity",
            "pub type MechanismIdentity",
            "std::thread",
            "tokio::spawn",
        ):
            self.assertNotIn(forbidden, source)
        self.assertGreaterEqual(source.count("```compile_fail"), 4)

    def test_closed_contract_requires_attestation_custody_and_owned_runtime(self) -> None:
        contract = json.loads(
            (ROOT / "contracts/browser-actor.v1.json").read_text(encoding="utf-8")
        )
        authority = contract["authority_boundary"]
        self.assertEqual(authority["product_crate"], "hepta-browser-actor")
        self.assertEqual(
            authority["implementation_crate"], "hepta-browser-actor-simulation"
        )
        self.assertFalse(authority["implementation_crate_published"])
        self.assertTrue(
            authority["only_product_wrapper_may_depend_directly_on_implementation"]
        )
        self.assertFalse(authority["caller_constructed_mechanism_identity_publicly_exported"])
        self.assertFalse(authority["principal_binding_publicly_exported"])
        self.assertFalse(authority["ordinary_browser_request_handler_implemented"])
        self.assertFalse(authority["ordinary_handle_method_exported"])
        self.assertTrue(authority["construction_requires_attested_peer"])
        self.assertTrue(authority["every_dispatch_requires_attested_peer"])
        self.assertTrue(authority["request_scoped_custody_required"])
        self.assertFalse(authority["simulation_api_is_product_authority"])
        self.assertFalse(authority["product_actor_generic_over_runtime"])
        self.assertFalse(authority["caller_supplied_runtime_adapter"])
        self.assertFalse(authority["runtime_trait_publicly_exported"])
        self.assertFalse(authority["request_control_publicly_exported"])
        self.assertFalse(authority["deferred_work_after_terminal_success_representable"])
        self.assertFalse(authority["raw_session_event_type_publicly_exported"])
        self.assertFalse(
            authority["unauthenticated_session_event_mutation_publicly_exported"]
        )
        self.assertTrue(authority["authority_changing_state_requires_attested_request"])
        self.assertTrue(authority["cancellation_helpers_are_revocation_only"])
        self.assertEqual(
            contract["principal_binding"]["source"],
            "opaque_AttestedPeer_refresh_only",
        )
        self.assertTrue(
            contract["browser_actor"]["request_authority_carried_through_runtime_control"]
        )
        self.assertTrue(
            contract["browser_actor"]["final_success_released_after_peer_revalidation"]
        )
        self.assertFalse(contract["browser_actor"]["generic_runtime_injection"])
        self.assertFalse(contract["browser_actor"]["generic_session_event_ingress"])
        self.assertEqual(
            contract["browser_actor"]["product_state_transition_entry"],
            "handle_attested_request_only",
        )
        self.assertFalse(
            contract["browser_actor"]["caller_can_release_human_or_ime_control"]
        )
        self.assertFalse(
            contract["browser_actor"]["caller_can_resolve_capability_or_recovery"]
        )
        self.assertFalse(
            contract["browser_actor"]["caller_can_synthesize_navigation_completion"]
        )
        self.assertTrue(
            contract["browser_actor"][
                "unauthenticated_helpers_can_only_revoke_or_observe"
            ]
        )
        self.assertTrue(
            contract["browser_actor"][
                "agent_navigation_requires_idle_control_before_runtime"
            ]
        )
        self.assertTrue(
            contract["browser_actor"][
                "terminal_revision_reference_is_never_current"
            ]
        )
        self.assertFalse(
            contract["receipts"]["internal_error_text_exposed_by_display"]
        )
        self.assertFalse(contract["receipts"]["journal_authorizes_execution"])
        self.assertFalse(contract["receipts"]["journal_automatically_replays_operations"])
        self.assertFalse(contract["activation"]["product_agent_port_enabled"])
        self.assertFalse(contract["activation"]["production_release_authorized"])

    def test_actor_crates_create_no_listener_or_installable_binary(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for crate in (
                ROOT / "crates/hepta-browser-actor",
                ROOT / "crates/hepta-browser-actor-simulation",
            )
            for path in sorted((crate / "src").rglob("*.rs"))
        )
        self.assertNotIn("TcpListener", source)
        self.assertNotIn("UnixListener", source)
        for crate_name in ("hepta-browser-actor", "hepta-browser-actor-simulation"):
            manifest = load_toml(ROOT / f"crates/{crate_name}/Cargo.toml")
            self.assertFalse(manifest["package"]["autobins"])
            self.assertFalse(manifest["package"]["build"])
            self.assertFalse(manifest["package"]["publish"])

    def test_authority_boundary_is_documented(self) -> None:
        wrapper = (ROOT / "crates/hepta-browser-actor/README.md").read_text(
            encoding="utf-8"
        )
        simulation = (
            ROOT / "crates/hepta-browser-actor-simulation/README.md"
        ).read_text(encoding="utf-8")
        architecture = (
            ROOT / "docs/architecture/BROWSER_ACTOR_AUTHORITY_BOUNDARY.md"
        ).read_text(encoding="utf-8")
        for text in (wrapper, architecture):
            self.assertIn("AttestedPeer", text)
            self.assertIn("request", text.lower())
            self.assertIn("custody", text.lower())
            self.assertIn("BrowserRequestHandler", text)
        self.assertIn("actor-owned", wrapper)
        self.assertIn("no raw", wrapper.lower())
        self.assertIn("non-generic", architecture.lower())
        self.assertIn("handle_attested", architecture)
        self.assertNotIn("BrowserActor<R>", architecture)
        self.assertNotIn("a bounded `PageRuntime` adapter", architecture)
        self.assertIn("implementation-internal", simulation)
        self.assertIn("not a product entry point", simulation)


if __name__ == "__main__":
    unittest.main()
