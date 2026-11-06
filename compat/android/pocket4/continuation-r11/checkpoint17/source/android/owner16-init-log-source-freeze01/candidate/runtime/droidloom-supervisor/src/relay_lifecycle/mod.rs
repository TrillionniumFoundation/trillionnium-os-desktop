//! Opt-in real cell relay lifecycle; integration in progress.
pub mod policy;
mod domain;
mod capability;
mod init_peer;
mod init_log;
pub mod entry;
pub(crate) mod owner;
mod worker;
mod audit;
pub use policy::{PressureRelaySpec, RelayArtifact};
pub use audit::RelayLifecycleAudit;
#[cfg(test)]
pub(crate) use audit::test_snapshot as audit_test_snapshot;
