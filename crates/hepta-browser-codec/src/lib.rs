#![forbid(unsafe_code)]

//! Strict canonical Browser API codec for TrillionniumOS Desktop.
//!
//! The product carrier treats every payload as opaque bytes. This crate is the
//! first semantic boundary: it rejects malformed, duplicate-member,
//! non-canonical, over-bounded, or contract-invalid JSON before any
//! BrowserActor handler can observe a request. It does not open a listener,
//! dispatch Servo, grant a capability, or authorize an external effect.

mod json;
mod model;

pub use json::{JsonError, JsonObject, JsonValue};
pub use model::{
    BrowserErrorCode, BrowserOperation, BrowserRequest, BrowserResponse, BrowserWireError,
    CodecError, DecodedMessage, EffectClass, ElementReference, NavigationTarget,
    ObservationField, PageAction, ProfilePersistence, ProfileSpec, WaitCondition,
};

pub const BROWSER_API_PROTOCOL: &str = "trillionnium.desktop.browser-api.v1";
pub const MAX_MESSAGE_BYTES: usize = 262_144;
pub const MAX_JSON_DEPTH: usize = 32;
pub const MAX_CONTAINER_ITEMS: usize = 20_000;

pub use model::{decode_request, decode_response, encode_request, encode_response, self_check};

#[cfg(test)]
mod tests;
