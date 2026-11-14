//! The exact delivered transport and environment modules are compiled directly.
//! No Android runtime, daemon handler or application acceptance is fabricated.
#![deny(unsafe_op_in_unsafe_fn)]

mod development {
    pub(crate) mod owned_process {
        pub(crate) use pocket4_process_fd::{open_pidfd, pidfd_exited};
    }
}

#[path = "../../source/runtime/droidloom-supervisor/src/application_command.rs"]
mod application_command;
