#![forbid(unsafe_code)]

//! Deterministic session ownership, revision, bounded queueing, and
//! Agent/human arbitration core. No Servo object, socket, clock source, or
//! operating-system authority is owned by this crate; adapters inject events
//! and monotonic timestamps.

mod machine;
mod queue;
mod types;

pub use machine::{SessionMachine, SessionSnapshot};
pub use queue::{ArbiterQueue, QueueError};
pub use types::{
    ControlSource, ControlState, DEFAULT_HUMAN_LEASE_TTL_MS, HumanLease,
    MAX_HUMAN_LEASE_TTL_MS, SessionEffect, SessionEvent, SessionPhase, TransitionError,
};

#[cfg(test)]
mod tests;
