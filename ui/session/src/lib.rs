//! Trusted host composition for the native Session.
//!
//! The standalone binary remains independently configured. Library features do
//! not install an issuer, original request owner, or renderer submission path.

#![forbid(unsafe_code)]

#[cfg(all(target_os = "linux", feature = "objective-submission"))]
pub mod objective_submission;
