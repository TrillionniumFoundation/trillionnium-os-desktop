//! Public fail-stop Agent transport API.
//!
//! The implementation is isolated behind a private facade and private wire
//! module. Production callers receive only OS-entropy-backed connected-stream
//! operations and redacted identity/error formatting. Raw frames, nonce values,
//! and deterministic nonce injection remain internal test mechanisms.

#![cfg_attr(not(any(target_os = "linux", target_os = "android")), allow(dead_code))]
#![deny(unsafe_op_in_unsafe_fn)]

mod facade;

pub use facade::{
    ClientConnection, DEFAULT_OPERATION_TIMEOUT, DIGEST_BYTES, HEADER_BYTES, MAX_PAYLOAD_BYTES,
    NONCE_BYTES, PROTOCOL_MAGIC, PROTOCOL_VERSION, PeerIdentity, PeerPolicy, ReceivedRequest,
    ServerConnection, TransportError, self_check,
};

// The reviewed kernel identity boundary lives in `facade/wire.rs`.
// SAFETY: it invokes `libc::getsockopt(..., SO_PEERCRED, ...)` with initialized
// output storage and a stream-owned descriptor, and retains no raw pointer.
