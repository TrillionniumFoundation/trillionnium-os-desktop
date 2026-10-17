#!/usr/bin/env python3
"""Verify a fixed Hepta checkout; optionally emit source-derived wire checks.

The optional Rust program uses exact declaration blocks, EventBuffer source,
fleet lifecycle transition methods and Agentd's accepted lifecycle expression
from the hash-verified checkout. Only Method/Payload enum variants are narrowed
to the client's allowlist. It does not construct Agentd or any authority owner.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "services/hepta-os/UPSTREAM_CONTRACT.json"
PROTOCOL = "codex-rs/hepta-agent-protocol/src/lib.rs"
CAPABILITIES = "codex-rs/hepta-agent-protocol/src/capabilities.rs"
FLEET = "codex-rs/hepta-fleet/src/model.rs"
STATE = "codex-rs/hepta-agentd/src/state.rs"


def braced_block(text, start):
    opening = text.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def declaration(text, name, kind):
    match = re.search(rf"^pub {kind} {name}\b", text, re.MULTILINE)
    if match is None:
        raise ValueError(f"pinned declaration absent: {name}")
    start = text.rfind("#[derive(", 0, match.start())
    return braced_block(text, start)


def selected_enum(text, name, selected):
    item = declaration(text, name, "enum")
    opening = item.index("{")
    variants = []
    for selected_name in selected:
        match = re.search(rf"^    {selected_name}(?=[,\s({{])", item, re.MULTILINE)
        if match is None:
            raise ValueError(f"pinned variant absent: {name}::{selected_name}")
        end, depth = match.end(), 0
        while end < len(item):
            char = item[end]
            if char in "({":
                depth += 1
            elif char in ")}":
                depth -= 1
            elif char == "," and depth == 0:
                break
            end += 1
        variants.append(item[match.start():end + 1])
    return item[:opening + 1] + "\n" + "\n".join(variants) + "\n}"


def emit_reference(source, destination):
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "src").mkdir()
    protocol = (source / PROTOCOL).read_text(encoding="utf-8")
    capabilities = (source / CAPABILITIES).read_text(encoding="utf-8")
    fleet = (source / FLEET).read_text(encoding="utf-8")
    state = (source / STATE).read_text(encoding="utf-8")
    generation_start = state.index("        let distance = record\n")
    generation_end = state.index("        if !accepted {", generation_start)
    accepted_expression = state[generation_start:generation_end]
    blocks = [
        "use serde::{Deserialize, Serialize};\nuse std::path::PathBuf;\nmod agent_id;\nuse agent_id::AgentId;",
        declaration(fleet, "AgentLifecycle", "enum"),
        braced_block(fleet, fleet.index("impl AgentLifecycle {")),
        re.search(r"^pub const AGENT_STATE_SCHEMA_VERSION:.*;$", fleet, re.MULTILINE).group(),
        declaration(fleet, "AgentLifecycleState", "struct"),
        braced_block(fleet, fleet.index("impl AgentLifecycleState {")),
        GENERATION_SHIMS.replace("// ORIGINAL_ACCEPTED_EXPRESSION", accepted_expression),
        declaration(capabilities, "AgentdCapability", "struct"),
        declaration(capabilities, "AgentdCapabilitySet", "struct"),
    ]
    for name, kind in [
        ("AgentRunPhase", "enum"), ("AgentRunReceipt", "struct"),
        ("HealthSnapshot", "struct"), ("AgentdEventKind", "enum"),
        ("AgentdEvent", "struct"), ("EventBatch", "struct"),
        ("AgentdRequest", "struct"), ("AgentdResponse", "struct"),
    ]:
        blocks.append(declaration(protocol, name, kind))
    blocks.append(selected_enum(protocol, "AgentdMethod", ["Health", "Capabilities", "Events", "RunStatus"]))
    blocks.append(selected_enum(protocol, "AgentdPayload", ["Health", "Capabilities", "Events", "RunStatus", "Error"]))
    blocks.append(REFERENCE_MAIN)
    (destination / "src/main.rs").write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    shutil.copyfile(source / "codex-rs/hepta-contracts/src/agent_id.rs", destination / "src/agent_id.rs")
    shutil.copyfile(source / "codex-rs/hepta-agentd/src/event_buffer.rs", destination / "src/event_buffer.rs")
    shutil.copyfile(ROOT / "services/hepta-os/tests/fixtures/agentd_v2_payloads.json", destination / "fixtures.json")
    (destination / "Cargo.toml").write_text(
        '[package]\nname="hepta-pinned-wire-conformance"\nversion="0.0.0"\nedition="2021"\npublish=false\n'
        '[workspace]\n[dependencies]\nserde={version="=1.0.219",features=["derive"]}\nserde_json="=1.0.140"\n',
        encoding="utf-8",
    )


GENERATION_SHIMS = r'''
// Only the surrounding error/record/identity shapes are local shims. The fleet
// initial/successor/can_transition_to methods and accepted statements above
// are copied verbatim from the verified source. This is not an AgentdState.
#[derive(Debug)]
pub enum FleetRegistryError {
    InvalidTransition { agent_id: AgentId, current: AgentLifecycle, requested: AgentLifecycle },
    Corrupt(String),
}
struct Identity { spawn_generation: u64 }
struct Record { lifecycle: AgentLifecycleState }
struct AcceptedExpression { identity: Identity }
impl AcceptedExpression {
    fn accepts(&self, record: &Record) -> bool {
        // ORIGINAL_ACCEPTED_EXPRESSION
        accepted
    }
}
fn verify_original_generation_semantics() {
    let id = AgentId::parse("11111111-1111-4111-8111-111111111111").unwrap();
    let mut record = Record { lifecycle: AgentLifecycleState::initial(id.clone()) };
    let verifier = AcceptedExpression { identity: Identity { spawn_generation: 1 } };
    assert!(!verifier.accepts(&record));
    for (phase, generation) in [(AgentLifecycle::Starting,1), (AgentLifecycle::Running,2), (AgentLifecycle::Draining,3)] {
        record.lifecycle = record.lifecycle.successor(phase).unwrap();
        assert_eq!(record.lifecycle.generation, generation);
        assert!(verifier.accepts(&record));
    }
    assert!(record.lifecycle.successor(AgentLifecycle::Running).is_err());
    record.lifecycle = record.lifecycle.successor(AgentLifecycle::Stopped).unwrap();
    assert!(!verifier.accepts(&record));
    record.lifecycle = record.lifecycle.successor(AgentLifecycle::Starting).unwrap();
    assert!(!verifier.accepts(&record), "old spawn must be fenced after restart");
    let restarted = AcceptedExpression { identity: Identity { spawn_generation: 5 } };
    assert!(restarted.accepts(&record));
    let fixed = AcceptedExpression { identity: Identity { spawn_generation: 7 } };
    for phase in [AgentLifecycle::Stopped, AgentLifecycle::Starting, AgentLifecycle::Running, AgentLifecycle::Draining, AgentLifecycle::Failed] {
        for generation in [6,7,8,9,10] {
            let record = Record { lifecycle: AgentLifecycleState { schema_version: AGENT_STATE_SCHEMA_VERSION, agent_id: id.clone(), generation, lifecycle: phase } };
            assert_eq!(fixed.accepts(&record), matches!((phase,generation),
                (AgentLifecycle::Starting,7) | (AgentLifecycle::Running,8) | (AgentLifecycle::Draining,9)));
        }
    }
    let mut overflow = AgentLifecycleState::initial(id);
    overflow.generation = u64::MAX;
    assert!(overflow.successor(AgentLifecycle::Starting).is_err());
}
'''


REFERENCE_MAIN = r'''
// EventBuffer needs only this error-reporting shape; no owner is reconstructed.
#[derive(Debug)]
pub enum AgentdError { Invalid(String) }
mod event_buffer;

fn main() {
    verify_original_generation_semantics();
    let fixtures: serde_json::Value = serde_json::from_str(include_str!("../fixtures.json")).unwrap();
    for name in ["health", "capabilities", "events", "run_status"] {
        let payload: AgentdPayload = serde_json::from_value(fixtures[name].clone()).unwrap();
        assert_eq!(serde_json::to_value(payload).unwrap(), fixtures[name]);
    }
    for method in [
        serde_json::json!({"type":"health"}),
        serde_json::json!({"type":"capabilities"}),
        serde_json::json!({"type":"events","after_cursor":0,"limit":16}),
        serde_json::json!({"type":"run_status","run_id":"fixture:run-1"}),
    ] {
        let json = serde_json::json!({"schema_version":2,"request_id":1,"spawn_generation":7,"method":method});
        let request: AgentdRequest = serde_json::from_value(json.clone()).unwrap();
        assert_eq!(serde_json::to_value(request).unwrap(), json);
    }
    let mut ring = event_buffer::EventBuffer::new(2).unwrap();
    ring.push(AgentdEventKind::Bootstrapped);
    ring.push(AgentdEventKind::Lifecycle { lifecycle: AgentLifecycle::Running, generation: 8 });
    ring.push(AgentdEventKind::AppServerReady);
    let first = ring.batch(0, 1);
    assert!(first.gap);
    assert_eq!((first.events.len(), first.next_cursor, first.latest_cursor), (1, 2, 3));
    let next = ring.batch(first.next_cursor, 16);
    assert!(!next.gap);
    assert_eq!((next.events.len(), next.next_cursor, next.latest_cursor), (1, 3, 3));
    let ahead = ring.batch(9, 16);
    assert_eq!((ahead.events.len(), ahead.next_cursor, ahead.latest_cursor), (0, 9, 3));
    let id = AgentId::parse("11111111-1111-4111-8111-111111111111").unwrap();
    let response = AgentdResponse { schema_version: 2, request_id: 1, agent_id: id,
        spawn_generation: 7, current_generation: 8,
        payload: serde_json::from_value(fixtures["health"].clone()).unwrap() };
    let json = serde_json::to_value(response).unwrap();
    assert_eq!(json["agent_id"], "11111111-1111-4111-8111-111111111111");
    assert_eq!(json["payload"], fixtures["health"]);
    println!("PASS: source-derived lifecycle successor and exact Starting/+0 Running/+1 Draining/+2 acceptance, restart fencing, overflow; 4 payload and 4 request roundtrips; identity/envelope; exact EventBuffer gap/resume/ahead behavior");
    println!("Evidence class: source-derived protocol conformance; no live Hepta daemon or device effect");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hepta-source", required=True, type=Path)
    parser.add_argument("--emit-reference", type=Path, help="New directory for the small source-derived Rust verifier")
    args = parser.parse_args()
    source = args.hepta_source.resolve(strict=True)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if commit != manifest["commit"]:
        raise SystemExit("FAIL: Hepta checkout does not match the reviewed commit")
    for item in manifest["files"]:
        data = (source / item["path"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise SystemExit(f"FAIL: reviewed source content changed: {item['path']}")
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if blob != item["git_blob"]:
            raise SystemExit(f"FAIL: source blob mismatch: {item['path']}")
    print(f"PASS: {len(manifest['files'])} source files at Hepta {commit}")
    if args.emit_reference:
        emit_reference(source, args.emit_reference)
        print(f"Generated source-derived Rust verifier: {args.emit_reference}")
        print("Run cargo run --offline --manifest-path <generated-directory>/Cargo.toml")
    print("This verifies a pinned source contract, not a live daemon or Hepta-to-device effect.")


if __name__ == "__main__":
    main()
