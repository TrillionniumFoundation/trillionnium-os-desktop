// Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
use droidloom_pressure_relay::run_inherited_lifecycle;
use std::os::fd::{FromRawFd, OwnedFd};
fn main() {
    if std::env::args_os().skip(1).collect::<Vec<_>>() != ["--lifecycle-fd", "3"] {
        eprintln!("usage: droidloom-psi-owner --lifecycle-fd 3 (trusted supervisor inherited socket only)");
        std::process::exit(64);
    }
    // fd 3 is consumed once; entry validates socket kind/flags and authenticates
    // the exact kernel peer PIDFD before it accepts any lifecycle descriptors.
    if let Err(error) = run_inherited_lifecycle(unsafe { OwnedFd::from_raw_fd(3) }) {
        eprintln!("droidloom-psi-owner: {error}");
        std::process::exit(1);
    }
}
