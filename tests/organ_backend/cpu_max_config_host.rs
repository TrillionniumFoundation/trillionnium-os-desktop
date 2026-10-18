// SPDX-License-Identifier: MPL-2.0

//! Runs the actual production CPU configuration parser on a Rust host.
//! The same regression functions also run as `aster-core` kernel tests.

#[path = "../../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/max_config.rs"]
mod max_config;
