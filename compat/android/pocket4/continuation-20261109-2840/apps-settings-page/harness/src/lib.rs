//! Same-file Settings admission controls; no mirrored daemon or fake runtime.
#![deny(unsafe_op_in_unsafe_fn)]
#[path = "../../source/runtime/droidloom-supervisor/src/application_probe.rs"]
mod application_probe;
#[path = "../../source/runtime/droidloom-supervisor/src/application_settings.rs"]
mod application_settings;
