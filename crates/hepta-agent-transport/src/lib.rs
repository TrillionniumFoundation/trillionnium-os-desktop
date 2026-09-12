//! Public fail-stop Agent transport API.
//!
//! The implementation is isolated behind a private facade and private wire
//! module. Production callers receive only OS-entropy-backed connected-stream
//! operations and redacted identity/error formatting. Raw frames, nonce values,
//! and deterministic nonce injection remain internal test mechanisms.

#![cfg_attr(not(any(target_os = "linux", target_os = "android")), allow(dead_code))]
#![deny(unsafe_op_in_unsafe_fn)]

use std::time::Duration;

mod facade;

pub use facade::{
    ClientConnection, PeerIdentity, PeerPolicy, ReceivedRequest, ServerConnection, TransportError,
    self_check,
};

pub const PROTOCOL_MAGIC: [u8; 8] = *b"HEPTA001";
pub const PROTOCOL_VERSION: u16 = 1;
pub const HEADER_BYTES: usize = 88;
pub const NONCE_BYTES: usize = 32;
pub const DIGEST_BYTES: usize = 32;
pub const MAX_PAYLOAD_BYTES: usize = 262_144;
pub const DEFAULT_OPERATION_TIMEOUT: Duration = Duration::from_secs(20);

// The reviewed kernel identity boundary lives in `facade/wire.rs`.
// SAFETY: it invokes `libc::getsockopt(..., SO_PEERCRED, ...)` with initialized
// output storage and a stream-owned descriptor, and retains no raw pointer.
