#!/usr/bin/env python3
"""Verify immutable original blobs and extract a small wire-only Rust check.

The input may be an authorized checkout or an exact source-file snapshot; no
claim of a complete/clean original checkout is made. Fourteen original blobs
are hash checked. Only original serde declarations, AgentId and the original
expired/all-zero wire fixture are compiled. No owner, signer, socket or runtime
is constructed. The existing lightweight lock is reused with one explicit
root-package rename, never the 733-package original daemon graph.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from check_upstream_contract import braced_block, declaration, selected_enum


ROOT = Path(__file__).resolve().parents[3]
CRATE = ROOT / "services/hepta-os"
MANIFEST = CRATE / "OBJECTIVE_UPSTREAM_CONTRACT.json"
PACKAGE = "hepta-objective-wire-conformance"


def verified_files(source):
    manifest = json.loads(MANIFEST.read_text())
    texts = {}
    for item in manifest["files"]:
        data = (source / item["path"]).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if (len(data) != item["bytes"] or blob != item["git_blob"]
                or hashlib.sha256(data).hexdigest() != item["sha256"]):
            raise ValueError(f"pinned source bytes differ: {item['path']}")
        texts[item["path"]] = data.decode("utf-8")
    return manifest, texts


def emit_reference(manifest, texts, destination):
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "src").mkdir()
    protocol_path = "codex-rs/hepta-agent-protocol/src/lib.rs"
    authbus_path = "codex-rs/hepta-agent-protocol/src/authbus.rs"
    fixture_path = "codex-rs/hepta-agent-protocol/src/objective_tests.rs"
    protocol, authbus, original_tests = (texts[path] for path in [protocol_path, authbus_path, fixture_path])
    blocks = ["use serde::{Deserialize, Serialize};\nmod agent_id;\nuse agent_id::AgentId;"]
    extractions = []

    def append(path, name, original, emitted=None, selected=None):
        if emitted is None:
            emitted = original
        start = texts[path].index(original)
        extractions.append({
            "path": path, "name": name,
            "first_line": texts[path].count("\n", 0, start) + 1,
            "last_line": texts[path].count("\n", 0, start + len(original)) + 1,
            "original_block_sha256": hashlib.sha256(original.encode()).hexdigest(),
            "emitted_block_sha256": hashlib.sha256(emitted.encode()).hexdigest(),
            "selected_enum_variants": selected,
        })
        blocks.append(emitted)

    for name in ["AuthBusObjectiveBody", "AuthBusObjectiveIngress", "ObjectiveRunAdmission"]:
        append(authbus_path, name, declaration(authbus, name, "struct"))
    append(authbus_path, "ObjectiveStartOutcome", declaration(authbus, "ObjectiveStartOutcome", "enum"))
    for name in ["AgentdRequest", "AgentdResponse"]:
        append(protocol_path, name, declaration(protocol, name, "struct"))
    for name, selected in [("AgentdMethod", ["ObjectiveStart"]),
                           ("AgentdPayload", ["ObjectiveRun", "ObjectiveConflict", "Error"])]:
        append(protocol_path, name, declaration(protocol, name, "enum"),
               selected_enum(protocol, name, selected), selected)
    for name in ["digest", "ingress"]:
        append(fixture_path, name, braced_block(original_tests, original_tests.index(f"fn {name}(")))
    blocks.append(REFERENCE_MAIN)
    (destination / "src/main.rs").write_text("\n\n".join(blocks) + "\n")
    # Use the already-verified bytes; do not reread a possibly replaced file.
    (destination / "src/agent_id.rs").write_text(texts["codex-rs/hepta-contracts/src/agent_id.rs"])
    shutil.copyfile(CRATE / "tests/fixtures/objective_ingress_original_wire_only.json", destination / "fixture.json")
    cargo = (CRATE / "Cargo.toml").read_text()
    lock = (CRATE / "Cargo.lock").read_text()
    for value in [cargo, lock]:
        if value.count('name = "hepta-os-observer"') != 1:
            raise ValueError("lightweight root package is no longer unique")
    cargo = cargo.replace('name = "hepta-os-observer"', f'name = "{PACKAGE}"')
    cargo = cargo.replace('name = "hepta-observe"', f'name = "{PACKAGE}"')
    cargo = cargo.replace('path = "src/bin/hepta-observe.rs"', 'path = "src/main.rs"')
    (destination / "Cargo.toml").write_text(cargo + "\n[workspace]\n")
    (destination / "Cargo.lock").write_text(lock.replace('name = "hepta-os-observer"', f'name = "{PACKAGE}"'))
    binding = {
        "directory": str(destination),
        "original_commit": manifest["commit"],
        "verified_original_files": manifest["files"],
        "extractions": extractions,
        "whole_file_copy": "codex-rs/hepta-contracts/src/agent_id.rs",
        "local_assertion_harness_sha256": hashlib.sha256(REFERENCE_MAIN.encode()).hexdigest(),
        "lock_derivation": "existing lightweight lock; only unique root-package name changed",
        "input_lock_sha256": hashlib.sha256((CRATE / "Cargo.lock").read_bytes()).hexdigest(),
        "emitted_lock_sha256": hashlib.sha256((destination / "Cargo.lock").read_bytes()).hexdigest(),
        "generated_files": {
            path: hashlib.sha256((destination / path).read_bytes()).hexdigest()
            for path in ["src/main.rs", "src/agent_id.rs", "fixture.json", "Cargo.toml", "Cargo.lock"]
        },
        "qualification": "original declarations and original wire-only fixture with local assertions; no Agentd crate, authentication or original runtime",
    }
    (destination / "SOURCE_BINDING.json").write_text(json.dumps(binding, indent=2) + "\n")
    return {"directory": str(destination), "source_binding": str(destination / "SOURCE_BINDING.json"),
            "source_binding_sha256": hashlib.sha256((destination / "SOURCE_BINDING.json").read_bytes()).hexdigest()}


REFERENCE_MAIN = r'''
fn main() {
    let raw = include_str!("../fixture.json");
    let provided: AuthBusObjectiveIngress = serde_json::from_str(raw).unwrap();
    assert_eq!(provided, ingress(), "fixture must equal the unchanged original wire-only factory");
    let supplied: serde_json::Value = serde_json::from_str(raw).unwrap();
    let request_json = serde_json::json!({
        "schema_version":2, "request_id":41, "spawn_generation":3,
        "method":{"type":"objective_start", "request":supplied}
    });
    let request: AgentdRequest = serde_json::from_value(request_json.clone()).unwrap();
    assert_eq!(request.method, AgentdMethod::ObjectiveStart { request: provided });
    assert_eq!(serde_json::to_value(&request).unwrap(), request_json);
    let mut frame = serde_json::to_vec(&request).unwrap();
    frame.push(b'\n');
    assert!(frame.len() <= 65_536);

    let admission = ObjectiveRunAdmission {
        run_id:"run.objective.1".to_owned(), objective_digest:digest('1'),
        hard_constraint_digest:digest('2'), publication_digest:digest('3'),
        chain_digest:digest('4'), disposition:"compiled".to_owned(), idempotent:false
    };
    let payload = serde_json::to_value(AgentdPayload::ObjectiveRun(admission.clone())).unwrap();
    let expected = serde_json::json!({
        "type":"objective_run", "run_id":"run.objective.1", "objective_digest":digest('1'),
        "hard_constraint_digest":digest('2'), "publication_digest":digest('3'),
        "chain_digest":digest('4'), "disposition":"compiled", "idempotent":false
    });
    assert_eq!(payload, expected);
    let _: AgentdPayload = serde_json::from_value(payload.clone()).unwrap();
    let outcome = serde_json::to_value(ObjectiveStartOutcome::Admitted { receipt:admission }).unwrap();
    assert_eq!(outcome["type"], "admitted");
    assert!(outcome.get("receipt").is_some());
    assert!(serde_json::from_value::<AgentdPayload>(outcome).is_err());

    let response = AgentdResponse {
        schema_version:2, request_id:41,
        agent_id:AgentId::parse("11111111-1111-4111-8111-111111111111").unwrap(),
        spawn_generation:3, current_generation:4,
        payload:serde_json::from_value(payload.clone()).unwrap()
    };
    let response_json = serde_json::json!({
        "schema_version":2, "request_id":41, "agent_id":"11111111-1111-4111-8111-111111111111",
        "spawn_generation":3, "current_generation":4, "payload":payload
    });
    assert_eq!(serde_json::to_value(&response).unwrap(), response_json);
    assert_eq!(serde_json::from_value::<AgentdResponse>(response_json).unwrap(), response);
    for value in [
        serde_json::json!({"type":"objective_conflict", "run_id":"run.objective.1", "conflict_digest":digest('6')}),
        serde_json::json!({"type":"error", "code":"request_rejected", "message":"wire-only fixture"})
    ] {
        let payload: AgentdPayload = serde_json::from_value(value.clone()).unwrap();
        assert_eq!(serde_json::to_value(payload).unwrap(), value);
    }
    let duplicate = raw.replacen("\"issuer_id\":", "\"issuer_id\":\"duplicate\",\"issuer_id\":", 1);
    assert!(serde_json::from_str::<AuthBusObjectiveIngress>(&duplicate).is_err());
    let mut unknown: serde_json::Value = serde_json::from_str(raw).unwrap();
    unknown["body"]["unexpected"] = serde_json::json!(true);
    assert!(serde_json::from_value::<AuthBusObjectiveIngress>(unknown).is_err());
    println!("{}", serde_json::json!({
        "status":"passed", "qualification":"original serde declarations and wire-only fixture; no original runtime/authentication",
        "checks":["original_fixture", "objective_start_request", "flat_objective_run_payload", "client_outcome_is_distinct", "response_envelope", "conflict_and_error_payloads", "strict_fields"],
        "original_agentd_started":false, "signature_created":false, "objective_submitted":false
    }));
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-files", type=Path, required=True)
    parser.add_argument("--emit-reference", type=Path)
    args = parser.parse_args()
    manifest, texts = verified_files(args.source_files.resolve(strict=True))
    report = {
        "status": "source_verified", "original_commit": manifest["commit"],
        "git_blob_and_sha256_files": len(texts),
        "qualification": "fixed source-file subset, not original checkout/build/run/admission",
    }
    if args.emit_reference:
        report["reference"] = emit_reference(manifest, texts, args.emit_reference.resolve())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
