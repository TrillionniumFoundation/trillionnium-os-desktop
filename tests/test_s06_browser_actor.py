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
        dependents: list[str] = []
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

    def test_product_api_has_no_weak_constructor_or_ordinary_handler(self) -> None:
        source = (ROOT / "crates/hepta-browser-actor/src/lib.rs").read_text(
            encoding="utf-8"
        )
        for required in (
            "pub fn from_attested(",
            "pub fn handle_attested(",
            "attested.refresh_snapshot(attestor)",
            "simulation::PrincipalBinding::bind_attested",
            ".handle_attested(context, request, attestor, attested)",
        ):
            self.assertIn(required, source)

        for forbidden in (
            "pub fn new(",
            "impl<R: PageRuntime> BrowserRequestHandler",
            "pub use hepta_browser_actor_simulation::PrincipalBinding",
            "pub type PrincipalBinding",
            "pub use hepta_browser_actor_simulation::MechanismIdentity",
            "pub type MechanismIdentity",
        ):
            self.assertNotIn(forbidden, source)
        self.assertGreaterEqual(source.count("```compile_fail"), 2)

    def test_closed_contract_requires_attestation_and_custody(self) -> None:
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
        self.assertFalse(
            authority["caller_constructed_mechanism_identity_publicly_exported"]
        )
        self.assertFalse(authority["principal_binding_publicly_exported"])
        self.assertFalse(authority["ordinary_browser_request_handler_implemented"])
        self.assertFalse(authority["ordinary_handle_method_exported"])
        self.assertTrue(authority["construction_requires_attested_peer"])
        self.assertTrue(authority["every_dispatch_requires_attested_peer"])
        self.assertTrue(authority["request_scoped_custody_required"])
        self.assertFalse(authority["simulation_api_is_product_authority"])

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
        self.assertFalse(contract["receipts"]["journal_authorizes_execution"])
        self.assertFalse(
            contract["receipts"]["journal_automatically_replays_operations"]
        )
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
        self.assertIn("implementation-internal", simulation)
        self.assertIn("not a product entry point", simulation)


if __name__ == "__main__":
    unittest.main()
