#!/usr/bin/env python3
"""Finite private constructor correspondence; actual identity tests are separate.

This reviewed profile follows the sole opaque approved caller through a pure
wrapper segment. It creates no public cheap API, runtime or report permission.
Token inventory is not a Rust parser or a substitute for native execution.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

try:
    from . import verify_approved_native_startup as composition
except ImportError:
    import verify_approved_native_startup as composition

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "contracts/approved-constructor-route.v1.json"
MAIN = "apps/hepta-browserd/src/product_dispatch.rs"
POLICY = "apps/hepta-browserd/src/product_dispatch/product_approved_policy.rs"

EXPECTED = {'schema': 'trillionnium.desktop.approved-constructor-route.v1',
 'default_activation': False,
 'status': 'SOURCE_CANDIDATE_NATIVE_BUDGET_REQUALIFICATION_PENDING',
 'authority': {'private_denial_only_gate': True,
               'caller_snapshot_or_boolean_authority': False,
               'original_binding_and_original_custodies_required': True,
               'public_full_readback_unchanged': True,
               'legacy_none_full_readback_unchanged': True,
               'scope_mints_runtime_or_report_permission': False,
               'cross_call_executable_cache': False},
 'lifetime': {'accepted_seconds_maximum': 20,
              'native_seconds_maximum': 5,
              'original_instant_extended': False},
 'full_boundaries': ['unchanged_public_approved_wrapper_before_private_constructor',
                     'actual_approved_actor_factory_identity_and_principal_equality',
                     'private_constructor_final_full_before_return',
                     'original_dispatch_completion_and_report_boundaries'],
 'private_helper_signature': 'fn ensure_approved_constructor_scope(&self, approved: '
                             '&hepta_peer_attestation::ApprovedAgentRequestBinding) -> Result<(), '
                             'ProductDispatchError>',
 'whole_source_sha256': {'apps/hepta-browserd/src/product_dispatch.rs': 'd6dab75c5b40260f1f53df2b9ccdbdf1d6c84f4a2b21150036c43a8c83934bd3',
                         'apps/hepta-browserd/src/product_dispatch/product_approved_policy.rs': '39c227ccba6bdf249402cf1f48cc8e2e09e7bc8e74067f619b1a134275c4aea5',
                         'apps/hepta-browserd/src/product_dispatch/product_approved_queue.rs': '818919238281bcb71c367a943f1b6fe7276d8f11c518b637a8cba602d5b1679a',
                         'apps/hepta-browserd/src/product_dispatch/product_control_wait.rs': 'd87efdb8cdd22e38cca90aae0f776f823478bf3b2045482c81ba608eb79a019f',
                         'apps/hepta-browserd/src/product_dispatch/configured_retained_bootstrap.rs': '13f5f364c22462065347e2f520bd9cd16ac68bc6ef32167727ff2d8a6a58588c',
                         'crates/hepta-peer-attestation/src/approved_policy.rs': '0a6a079336ad842bc55c34fe3930707ece098182bd976e78c2dfb21e18d87882',
                         'crates/hepta-peer-attestation/src/approved_policy/request_binding.rs': '604f35a1559901247341e51072207a7b31a768245324a82e35e3f31855421702',
                         'crates/hepta-peer-attestation/src/control_owner/control_request.rs': '4d4d6a80d2c6f93660b9ad09a1cefac43faa32177212d812c620315017a23eca',
                         'crates/hepta-peer-attestation/src/request_lease.rs': '54b80b2e94f4dc149d9af8f6e92815a2a8b88a9db987c34ec9a0b59d53850681',
                         'crates/hepta-browser-actor/src/servo_runtime/approved_binding.rs': '9141043f5ec964492a88a48ea57d3c2e82b71dc96dfd07d30419967f607fb754'},
 'function_token_sha256': {'apps/hepta-browserd/src/product_dispatch.rs': {'AcceptedProductConnection::ensure_approved_constructor_scope': 'b21691ccd7862af9b28578c49552b45dd48c51953d9a9cfdeb259f25a7dde8f1',
                                                                           'ProductRequestCoordinator::from_connection_with_approval': '8830bcc2e0950def13fa236eb03d81d0bb3054ed3471a105188d1515b7694182'},
                           'apps/hepta-browserd/src/product_dispatch/product_approved_policy.rs': {'ProductRequestCoordinator::from_approved_retained_connection': '1a5e124ec394f524f8c86176204cd4fbfdd58b57f4e9f2f05f2d3c202ea5f0ac',
                                                                                                   'ApprovedRetainedProductConnection::from_received': '714f4c25da8d16fabb64b8fb0d81496322594fb8a6bbde83277ba7edc4d0292f'}},
 'parent_public_api_token_bodies': {'ProductConnectionCancellation::cancel': '684f2d7d565c5863913de92c2e2e14a9275051e72ac3ce8702ad4c619230081c',
                                    'AcceptedProductConnection::attest': 'b16b0fa5a89cd4cbd2e584232d8bb25cd3a0ccf0a162c4a430f9136745563518',
                                    'AcceptedProductConnection::from_received': '37e398088329953ccd8289a2ca2de7c233d5772c7fec7518400f4da6c13b7107',
                                    'AcceptedProductConnection::from_control_received': 'f645636408c992edd75c19f55f8563873d84900c7f8a472752b682b5422303ad',
                                    'AcceptedProductConnection::deadline': '2a1cab133124f8851aece6bb6d4c31052f7c302725f639b2029cc084bc522d1f',
                                    'AcceptedProductConnection::cancellation': '2d6bc69b7ac3cb52517368fae6206aaebbdff2a12cf89682ed1a6713a64e3a47',
                                    'product_connection_queue': '02e4569a3b3a8a89939fb7c8ea75f5c7e72ab8f6e00fd36182027bda9c889a26',
                                    'ProductConnectionIngress::try_submit': 'f18ff7b179226f46a1db378cd0bb6995fa64b42f81e32039a44a2655779f1f20',
                                    'ProductConnectionQueue::try_next': '0864341e32fdcc27a164cdd7830e2e51d7e09d092afcc6ae0f0db6f0b32acf3d',
                                    'ProductRequestCoordinator::from_connection': '5d431916692c0904709f317fb6741478fabc8d0195d64dbc0b0e055d08a10885',
                                    'ProductRequestCoordinator::from_connection_after_reconciliation': 'b84a3b1a64dcfab2a982a54f1a8e4b552d7d6df367cc7a9f234989e4eddb974d',
                                    'ProductRequestCoordinator::serve_connection': '0cbcf0b6ca9e7047c394e382e646c6244e5f7097a591cf9cc8bb681b00a769df',
                                    'ProductRequestCoordinator::reconcile_request': 'b9e33199e0b617a5b36d882a9a53abd77b80c672c18bc8e18f764531fcb292a2',
                                    'ProductRequestCoordinator::content_process_crashed': 'edf071cff16509536c4d646a5d224fe9f1fd9b3101a72eba183630fe87a7a036',
                                    'ProductRequestCoordinator::acknowledge_stable_cycle': '0f9566c9862616df3c581b374e0cc5b9c25589a0814bdacaf76b7410e7f0b1c1',
                                    'ProductRequestCoordinator::reconstruct': '064672917c00fdcb15f3c2fefcc417f6e0de5276e9abb8546220ed4789a1ab7d'},
 'qualification': {'structural_source_correspondence_only': True,
                   'existing_actual_default_proc_kernel_groups_required': 13,
                   'existing_approved_startup_kernel_groups_required': 8,
                   'native_original_six_cases_and_budgets_preserved': True,
                   'actual_native_requalification_pending': True,
                   'measured_speedup_claim': False,
                   'installed_activation': False,
                   'production_ready': False}}


def digest(body):
    return hashlib.sha256(json.dumps(body, separators=(",", ":")).encode()).hexdigest()


def check(contract, texts):
    composition.typed_equal(contract, EXPECTED)
    for path, expected in EXPECTED["whole_source_sha256"].items():
        if hashlib.sha256(texts[path].encode("utf-8")).hexdigest() != expected:
            raise ValueError("private constructor or retained source differs: " + path)
    inventories = {path: composition.rust_inventory(texts[path])
                   for path in EXPECTED["function_token_sha256"]}
    for path, bindings in EXPECTED["function_token_sha256"].items():
        for name, expected in bindings.items():
            if digest(composition.function(inventories[path], name)) != expected:
                raise ValueError("finite constructor body differs: " + name)
    main, policy = inventories[MAIN], inventories[POLICY]
    if set(main["public_api"]) != set(EXPECTED["parent_public_api_token_bodies"]):
        raise ValueError("existing public constructor API changes")
    for name, expected in EXPECTED["parent_public_api_token_bodies"].items():
        if digest(composition.function(main, name)) != expected:
            raise ValueError("existing public constructor body changes: " + name)
    helper_name = "ensure_approved_constructor_scope"
    if main["tokens"].count(helper_name) != 2:
        raise ValueError("private constructor gate gains another call site")
    if any(name.endswith("::" + helper_name) for name in main["public_api"]):
        raise ValueError("private denial gate becomes public authority")
    position = main["tokens"].index(helper_name)
    if position < 2 or main["tokens"][position - 1] != "fn" or main["tokens"][position - 2] != "]":
        raise ValueError("private constructor gate visibility differs")
    opening = main["tokens"].index("{", position)
    actual = composition.signature(" ".join(main["tokens"][position - 1:opening]))
    if actual != composition.signature(EXPECTED["private_helper_signature"]):
        raise ValueError("private constructor gate arguments or result differ")
    combined = main["tokens"] + policy["tokens"]
    if combined.count("from_connection_with_approval") != 3:
        raise ValueError("finite approved/raw constructor callers differ")
    helper = composition.function(main, "AcceptedProductConnection::" + helper_name)
    composition.ordered(helper, [
        "self.control.owner_pid != std::process::id()", "let checked = (||",
        "let deadline = self.deadline()?", "self.attested.ensure_alive()",
        "self.control_verifier()?", "control.deadline()", "!= deadline",
        "approved.start_session()", ".verifier_for_session(&session)",
        ".with_original_pair(&session", "ceiling != deadline",
        "attested.snapshot() != self.attested.snapshot()", "custodian.ensure_alive()",
        "self.attested.ensure_alive()", "self.deadline()?", "control.ensure_alive()",
        "self.deadline()?", "checked.is_err()", "custody.revoke()", "checked",
    ], "private original-pair/root/creator/Instant/custody scope")
    constructor = composition.function(main, "ProductRequestCoordinator::from_connection_with_approval")
    composition.ordered(constructor, [
        "bootstrap.control.owner_pid != std::process::id()",
        "if let Some(approved) = admission.approved",
        "bootstrap.ensure_approved_constructor_scope(approved)?", "else",
        "bootstrap.ensure_control_current()?", "let ConnectionAdmissionScope",
        "journal.has_unresolved_receipts()", "ServoBrowserActor::from_approved_request(approved, endpoint)",
        "actor.principal() != &principal", "actor.receipt_observer(journal, image_id.clone())",
        "bootstrap.ensure_control_current()?", "Ok(Self",
    ], "legacy full and true actor/final full constructor boundaries")
    wrapper = composition.function(policy, "ProductRequestCoordinator::from_approved_retained_connection")
    composition.ordered(wrapper, [
        "bootstrap.deadline()?", "let connection = bootstrap.inner.connection.as_ref()",
        "Self::from_connection_with_approval", "bootstrap.principal.clone()", "connection",
        "ConnectionAdmissionScope", "approved: Some(&bootstrap.binding)",
    ], "sole approved caller after public full readback")


def validate(root=ROOT):
    texts = {path: composition.source(root, path) for path in EXPECTED["whole_source_sha256"]}
    check(composition.load(root / CONTRACT), texts)


def main():
    try:
        validate()
    except (ValueError, OSError) as error:
        print("approved private constructor validation failed: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps({"source_contract": "PASS", "public_cheap_api": False,
                      "actual_native_execution": "PENDING", "installed_activation": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
