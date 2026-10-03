#!/usr/bin/env python3
"""Finite source correspondence for denial-only private composition scope.

Token digests pin this reviewed source profile; they do not prove live /proc,
execute Servo or qualify the unchanged native budget. Actual tests are separate.
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
CONTRACT = "contracts/approved-composition-scope.v1.json"
POLICY = "apps/hepta-browserd/src/product_dispatch/product_approved_policy.rs"
QUEUE = composition.QUEUE
EXPECTED = {
    "schema": "trillionnium.desktop.approved-composition-scope.v1",
    "default_activation": False,
    "status": "SOURCE_CANDIDATE_NATIVE_BUDGET_REQUALIFICATION_PENDING",
    "authority": {
        "public_cheap_api": False,
        "caller_snapshot_or_principal": False,
        "action_or_report_permission_from_scope": False,
        "original_pair_root_policy_pidfds_and_creator_required": True,
        "full_executable_readback_in_scope": False,
        "cross_transaction_executable_cache": False
    },
    "lifetime": {
        "accepted_seconds_maximum": 20,
        "native_seconds_maximum": 5,
        "original_instant_extended": False
    },
    "full_boundaries": [
        "queue_admission_before_and_after_local_assignment",
        "approved_constructor_and_return",
        "serve_entry_before_allocation",
        "before_monitor_spawn",
        "after_monitor_spawn_before_coordinator",
        "coordinator_actor_dispatch_and_report_existing_boundaries"
    ],
    "function_token_sha256": {
        "apps/hepta-browserd/src/product_dispatch/product_approved_policy.rs": {
            "ApprovedRetainedProductConnection::original_scope": "7a096a3b0c3b94553d277f0b7470e274de328cda20a25df601db0af1f61cb34f",
            "ApprovedRetainedProductConnection::original_cancellation": "bbf43ee8b770a155e1d246bb79a9c97d15ced6b18b78350ae8c0c3df46092cb2",
            "ApprovedRetainedProductConnection::deadline": "fcfa944becd8ed71e7bd450cc43e5c0cf7d03893a367e67c2e4ec32aad4075e0",
            "ApprovedRetainedProductConnection::cancellation": "6b4a833d4ef359c86ba0bfb29b78f89e754924cff1d3186bc89fb024c37261e3",
            "ProductRequestCoordinator::from_approved_retained_connection": "1a5e124ec394f524f8c86176204cd4fbfdd58b57f4e9f2f05f2d3c202ea5f0ac",
            "ProductRequestCoordinator::serve_approved_retained_connection": "394a035a1777d124a884b390186459fc940dbea97f6deaac37958d9916bf5755",
            "ApprovedRetainedProductConnection::from_received": "714f4c25da8d16fabb64b8fb0d81496322594fb8a6bbde83277ba7edc4d0292f"
        },
        "apps/hepta-browserd/src/product_dispatch/product_approved_queue.rs": {
            "ApprovedRetainedAdmission::original_scope": "2ad97b0b5098ec4c6d4a60ef52ff5cd195d59828845b179f63b0726081d3710f",
            "ApprovedRetainedAdmission::original_cancellation": "8b2d665a6850b1073f65a261ef975e374c434b52640d7d54149c940675184dbd",
            "ApprovedRetainedAdmission::deadline": "30e6d4f0ac0622449e1975a16d0fbf45e7da2e2048cdf726985cb112a0f30ee4",
            "ApprovedRetainedAdmission::cancellation": "331d9a74826ec9dbf687b76cf87ae25226a3679933d7242098891b1b4d6187ab",
            "ApprovedRetainedAdmission::coordinator": "5c73281318ade5f32769ba59e3ceafaab9381a6fa02874c7e685aeac917aba64",
            "ApprovedRetainedAdmission::serve": "15b1b8a88771bc663bdb3cb8a860e0199e64abeba4f835291129eac6600763e6",
            "ApprovedRetainedIngress::try_submit": "d7843ec1642ffe6da65fd2e6c61f3ce0292839b09f3c3d6af59ed62253c2926e",
            "ApprovedRetainedAdmission::from_received": "58afaa35c1bfca2c9990a28f91350e9f7746de24f36ba2dd72afcbaf1f8549a6"
        }
    },
    "retained_source_sha256": {
        "crates/hepta-peer-attestation/src/approved_policy.rs": "0a6a079336ad842bc55c34fe3930707ece098182bd976e78c2dfb21e18d87882",
        "crates/hepta-peer-attestation/src/approved_policy/request_binding.rs": "604f35a1559901247341e51072207a7b31a768245324a82e35e3f31855421702",
        "crates/hepta-peer-attestation/src/control_owner/control_request.rs": "4d4d6a80d2c6f93660b9ad09a1cefac43faa32177212d812c620315017a23eca",
        "crates/hepta-peer-attestation/src/request_lease.rs": "54b80b2e94f4dc149d9af8f6e92815a2a8b88a9db987c34ec9a0b59d53850681",
        "crates/hepta-peer-attestation/src/control_owner/retained_request.rs": "f6f70998cf1b2b1e20857263a07d3101cf5f67ca4fcaa930b88a527445bdf754",
        "apps/hepta-browserd/src/product_dispatch/product_control_wait.rs": "d87efdb8cdd22e38cca90aae0f776f823478bf3b2045482c81ba608eb79a019f"
    },
    "qualification": {
        "structural_source_correspondence_only": True,
        "actual_kernel_tests": "existing_13_binding_plus_8_approved_startup_default_proc",
        "original_native_six_case_bodies_and_budgets_preserved": True,
        "actual_native_execution_pending": True,
        "installed_activation": False,
        "production_ready": False
    },
    "private_helper_signatures": {
        "apps/hepta-browserd/src/product_dispatch/product_approved_policy.rs": {
            "original_scope": "pub(super) fn original_scope(&self) -> Result<Instant, ProductDispatchError>",
            "original_cancellation": "pub(super) fn original_cancellation(&self) -> Result<ProductConnectionCancellation, ProductDispatchError>"
        },
        "apps/hepta-browserd/src/product_dispatch/product_approved_queue.rs": {
            "original_scope": "fn original_scope(&self) -> Result<Instant, ProductDispatchError>",
            "original_cancellation": "fn original_cancellation(&self) -> Result<ProductConnectionCancellation, ProductDispatchError>"
        }
    }
}


def digest(body):
    return hashlib.sha256(json.dumps(body, separators=(",", ":")).encode()).hexdigest()


def check(contract, texts):
    # Explicit finite successor inverse; original EXPECTED and rules are kept.
    try:
        from .verify_retained_control_readiness import legacy_texts
    except ImportError:
        from verify_retained_control_readiness import legacy_texts
    texts = legacy_texts(texts)
    try:
        from .verify_approved_service_owner import legacy_source
    except ImportError:
        from verify_approved_service_owner import legacy_source
    composition.typed_equal(contract, EXPECTED)
    inventories = {}
    for path, bindings in EXPECTED["function_token_sha256"].items():
        inventory = composition.rust_inventory(texts[path])
        inventories[path] = inventory
        for name, wanted in bindings.items():
            if digest(composition.function(inventory, name)) != wanted:
                raise ValueError("private scope or complete effect boundary differs: " + name)
    for path, wanted in EXPECTED["retained_source_sha256"].items():
        if hashlib.sha256(legacy_source(path, texts[path]).encode("utf-8")).hexdigest() != wanted:
            raise ValueError("original root/pidfd/full retained source differs: " + path)
    policy, queue = inventories[POLICY], inventories[QUEUE]
    for inventory in [policy, queue]:
        for name in inventory["public_api"]:
            if name.endswith(("::original_scope", "::original_cancellation")):
                raise ValueError("private denial scope becomes public authority")
    # The token inventory also strips literal/comment decoys. Exact visibility
    # limits these helpers to the parent product module or their own impl.
    for path, headers in EXPECTED["private_helper_signatures"].items():
        items = inventories[path]["tokens"]
        for method, header in headers.items():
            prefix = composition.tokens(("pub(super) fn " if path == POLICY else "fn ") + method)
            starts = [i for i in range(len(items) - len(prefix) + 1)
                      if items[i:i + len(prefix)] == prefix]
            if len(starts) != 1:
                raise ValueError("finite private helper visibility differs")
            start = starts[0]
            opening = items.index("{", start + len(prefix))
            actual = composition.signature(" ".join(items[start:opening]))
            if actual != composition.signature(header):
                raise ValueError("finite private helper signature differs")
            if path == QUEUE and start and items[start - 1] in {"pub", ")"}:
                raise ValueError("admission scope gains external visibility")
    composition.ordered(composition.function(policy, "ApprovedRetainedProductConnection::original_scope"),
                        ["self.owner_pid != std::process::id()", "self.inner.deadline()?",
                         "self.binding.start_session()", "product_time_remaining(deadline)?", "Ok(deadline)"],
                        "original creator/root/path/pair scope")
    composition.ordered(composition.function(queue, "ApprovedRetainedAdmission::original_scope"),
                        ["creating(self.owner_pid)?", "queue.current()?", ".original_scope()?",
                         "current != self.original_deadline", "product_time_remaining(self.original_deadline)?",
                         "Ok(self.original_deadline)"], "same captured queue scope")
    composition.check_queue(texts[QUEUE])


def validate(root=ROOT):
    paths = set(EXPECTED["function_token_sha256"]) | set(EXPECTED["retained_source_sha256"])
    texts = {path: composition.source(root, path) for path in paths}
    check(composition.load(root / CONTRACT), texts)


def main():
    try:
        validate()
    except (ValueError, OSError) as error:
        print("approved private composition scope validation failed: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps({"source_contract": "PASS", "public_cheap_api": False,
                      "actual_native_execution": "PENDING", "installed_activation": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
