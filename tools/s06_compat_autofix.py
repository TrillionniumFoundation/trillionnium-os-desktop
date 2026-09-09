#!/usr/bin/env python3
"""One-shot compatibility repair for S06 on the current S02-S05 stack."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_incarnation_source() -> None:
    source = r'''//! Per-actor identity namespace. Not a capability or a durable rollback anchor.
use crate::{AgentPortError, RuntimeFailure, validate_token};
use sha2::{Digest, Sha256};
use std::fs::File;
use std::io::{self, Read};

pub(super) const INCARNATION_ENTROPY_BYTES: usize = 32;

const ACTOR_DOMAIN: &[u8] = b"trillionnium.desktop.actor-incarnation.v1\0";
const FRAME_DOMAIN: &[u8] = b"trillionnium.desktop.scoped-frame.v1\0";

pub(super) trait IncarnationEntropySource {
    fn next_entropy(&mut self) -> io::Result<[u8; INCARNATION_ENTROPY_BYTES]>;
}

#[derive(Debug, Default)]
struct OsIncarnationEntropySource;

impl IncarnationEntropySource for OsIncarnationEntropySource {
    fn next_entropy(&mut self) -> io::Result<[u8; INCARNATION_ENTROPY_BYTES]> {
        let mut entropy = [0_u8; INCARNATION_ENTROPY_BYTES];
        let mut random = File::open("/dev/urandom")?;
        random.read_exact(&mut entropy)?;
        Ok(entropy)
    }
}

#[cfg(test)]
#[derive(Debug, Clone, Copy)]
pub(super) struct FixedEntropySource(pub [u8; INCARNATION_ENTROPY_BYTES]);

#[cfg(test)]
impl IncarnationEntropySource for FixedEntropySource {
    fn next_entropy(&mut self) -> io::Result<[u8; INCARNATION_ENTROPY_BYTES]> {
        Ok(self.0)
    }
}

#[derive(Default)]
pub(super) struct ActorIncarnation {
    namespace: Option<String>,
    failed: bool,
    // Fault injection is private to the simulation crate's unit-test build.
    // It is never a product argument, environment variable, transport API, or
    // caller-supplied namespace.
    #[cfg(test)]
    source: Option<Box<dyn IncarnationEntropySource>>,
}

impl ActorIncarnation {
    pub(super) fn namespace(&mut self) -> Result<&str, AgentPortError> {
        if self.failed {
            return Err(identity_error());
        }
        if self.namespace.is_none() {
            let entropy = self.read_entropy();
            match entropy {
                Ok(bytes) if bytes != [0; INCARNATION_ENTROPY_BYTES] => {
                    let mut digest = Sha256::new();
                    digest.update(ACTOR_DOMAIN);
                    digest.update(bytes);
                    self.namespace = Some(hex(digest.finalize().as_slice()));
                }
                _ => {
                    self.failed = true;
                    return Err(identity_error());
                }
            }
        }
        self.namespace.as_deref().ok_or_else(identity_error)
    }

    fn read_entropy(&mut self) -> io::Result<[u8; INCARNATION_ENTROPY_BYTES]> {
        #[cfg(test)]
        if let Some(source) = self.source.as_mut() {
            return source.next_entropy();
        }
        OsIncarnationEntropySource.next_entropy()
    }

    #[cfg(test)]
    pub(super) fn with_source(source: impl IncarnationEntropySource + 'static) -> Self {
        Self {
            source: Some(Box::new(source)),
            ..Self::default()
        }
    }
}

fn identity_error() -> AgentPortError {
    AgentPortError::Handler("session incarnation entropy unavailable; reconstruct actor".into())
}

fn hex(bytes: &[u8]) -> String {
    use std::fmt::Write;
    let mut result = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        let _ = write!(result, "{byte:02x}");
    }
    result
}

/// Namespace an adapter-owned local frame key by the PageOwner and WebView.
///
/// The result is an opaque, bounded identity, not an authorization token and
/// not proof that the frame or node exists. A real engine must resolve its
/// current frame, recheck revisions and retain the actual node before action.
/// This prevents a *previous* frame key from accidentally matching after
/// actor reconstruction or a close/create cycle with reset revision counters.
/// Identifiers are length-delimited to avoid concatenation aliases. No secret,
/// I/O, mutable state, caller target fields or engine dispatch is used here.
pub fn scoped_frame_id(
    session_id: &str,
    webview_token: &str,
    local_frame_key: &str,
) -> Result<String, RuntimeFailure> {
    let mut digest = Sha256::new();
    digest.update(FRAME_DOMAIN);
    for (field, value) in [
        ("session_id", session_id),
        ("webview_token", webview_token),
        ("local_frame_key", local_frame_key),
    ] {
        validate_token(field, value, 128)
            .map_err(|_| RuntimeFailure::PolicyDenied("invalid scoped frame identity input"))?;
        digest.update((value.len() as u32).to_be_bytes());
        digest.update(value.as_bytes());
    }
    Ok(hex(digest.finalize().as_slice()))
}
'''
    (ROOT / "crates/hepta-browser-actor-simulation/src/incarnation.rs").write_text(
        source, encoding="utf-8"
    )


def patch_incarnation_tests() -> None:
    path = ROOT / "crates/hepta-browser-actor-simulation/src/incarnation_tests.rs"
    text = path.read_text(encoding="utf-8")
    old_import = (
        "use hepta_agent_transport::{FixedNonceSource, NONCE_BYTES, NonceSource, "
        "TransportError};"
    )
    new_import = (
        "use crate::incarnation::{FixedEntropySource, INCARNATION_ENTROPY_BYTES, "
        "IncarnationEntropySource};"
    )
    if text.count(old_import) != 1:
        raise SystemExit("incarnation tests: old transport entropy import shape changed")
    text = text.replace(old_import, new_import, 1)
    old_impl = (
        "impl NonceSource for CountedEntropy {\n"
        "    fn next_nonce(&mut self) -> Result<[u8; NONCE_BYTES], TransportError> {"
    )
    new_impl = (
        "impl IncarnationEntropySource for CountedEntropy {\n"
        "    fn next_entropy(\n"
        "        &mut self,\n"
        "    ) -> std::io::Result<[u8; INCARNATION_ENTROPY_BYTES]> {"
    )
    if text.count(old_impl) != 1:
        raise SystemExit("incarnation tests: CountedEntropy implementation shape changed")
    text = text.replace(old_impl, new_impl, 1)
    old_error = (
        "Err(TransportError::Io(std::io::Error::other(\n"
        "                \"injected entropy failure\",\n"
        "            )))"
    )
    new_error = "Err(std::io::Error::other(\"injected entropy failure\"))"
    if text.count(old_error) != 1:
        raise SystemExit("incarnation tests: injected error shape changed")
    text = text.replace(old_error, new_error, 1)
    text = text.replace("FixedNonceSource", "FixedEntropySource")
    text = text.replace("NONCE_BYTES", "INCARNATION_ENTROPY_BYTES")
    path.write_text(text, encoding="utf-8")


def patch_simulation_state_model() -> None:
    path = ROOT / "crates/hepta-browser-actor-simulation/src/lib.rs"
    text = path.read_text(encoding="utf-8")
    old_pattern = "matches!(error, TransitionError::RevisionExhausted)"
    count = text.count(old_pattern)
    if count != 2:
        raise SystemExit(f"simulation lib: expected two revision patterns, found {count}")
    text = text.replace(
        old_pattern,
        "matches!(error, TransitionError::RevisionExhausted(_))",
    )
    obsolete_navigation = '''        TransitionError::ControlConflict(ControlState::AgentNavigating) => failure(
            BrowserErrorCode::NavigationInProgress,
            "Agent navigation is already in progress",
        ),
'''
    if text.count(obsolete_navigation) != 1:
        raise SystemExit("simulation lib: obsolete AgentNavigating arm shape changed")
    text = text.replace(obsolete_navigation, "", 1)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    write_incarnation_source()
    patch_incarnation_tests()
    patch_simulation_state_model()


if __name__ == "__main__":
    main()
