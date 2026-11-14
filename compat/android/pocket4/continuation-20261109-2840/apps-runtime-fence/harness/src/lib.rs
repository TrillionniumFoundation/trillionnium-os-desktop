//! CI compiles the delivered source files directly. No Android runtime is started.
#![deny(unsafe_op_in_unsafe_fn)]

// Type-path compatibility only: the actual production observation module is
// re-exported below. No control request handler or transport is fabricated.
extern crate self as droidloom_supervisor;
pub mod control { pub use crate::application_probe; }

mod development {
    pub(crate) mod owned_process {
        pub(crate) use pocket4_process_fd::{open_pidfd, pidfd_exited};
    }
}

#[path = "../../source/runtime/droidloom-supervisor/src/application_probe.rs"]
pub mod application_probe;
#[path = "../../source/runtime/droidloom-supervisor/src/application_command.rs"]
mod application_command;
#[path = "../../source/runtime/droidloom-applications/src/release.rs"]
pub mod release;
#[path = "../../source/runtime/droidloom-applications/src/runtime_fence.rs"]
mod runtime_fence;
