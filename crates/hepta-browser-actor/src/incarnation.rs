//! Per-actor identity namespace. Not a capability or a durable rollback anchor.
use crate::{AgentPortError, RuntimeFailure, validate_token};
use hepta_agent_transport::{NONCE_BYTES, NonceSource, OsNonceSource};
use sha2::{Digest, Sha256};

const _: () = assert!(NONCE_BYTES == 32);

const ACTOR_DOMAIN: &[u8] = b"trillionnium.desktop.actor-incarnation.v1\0";
const FRAME_DOMAIN: &[u8] = b"trillionnium.desktop.scoped-frame.v1\0";

#[derive(Default)]
pub(super) struct ActorIncarnation {
    namespace: Option<String>,
    failed: bool,
    // Fault injection is private to the crate's unit-test build, never a
    // product argument, environment variable or caller-supplied namespace.
    #[cfg(test)]
    source: Option<Box<dyn NonceSource>>,
}

impl ActorIncarnation {
    pub(super) fn namespace(&mut self) -> Result<&str, AgentPortError> {
        if self.failed {
            return Err(identity_error());
        }
        if self.namespace.is_none() {
            let entropy = self.read_entropy();
            match entropy {
                Ok(bytes) if bytes != [0; NONCE_BYTES] => {
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

    fn read_entropy(&mut self) -> Result<[u8; NONCE_BYTES], hepta_agent_transport::TransportError> {
        #[cfg(test)]
        if let Some(source) = self.source.as_mut() {
            return source.next_nonce();
        }
        OsNonceSource.next_nonce()
    }

    #[cfg(test)]
    pub(super) fn with_source(source: impl NonceSource + 'static) -> Self {
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
