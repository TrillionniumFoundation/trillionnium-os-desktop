//! Trusted host composition for the native Session.
//!
//! The standalone binary remains independently configured. Library features do
//! not install an issuer or original request owner. A configured standalone
//! Session may forward narrow typed intentions to an independently supplied host.

#![forbid(unsafe_code)]

#[cfg(all(target_os = "linux", feature = "objective-submission"))]
pub mod objective_submission;
