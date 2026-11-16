//! Source-only regression tests for the application evidence completeness checker.
//! This crate does not execute Android acceptance or grant runtime qualification.
#![forbid(unsafe_code)]

#[path = "../../source/runtime/droidloom-applications/src/release.rs"]
pub mod release;
