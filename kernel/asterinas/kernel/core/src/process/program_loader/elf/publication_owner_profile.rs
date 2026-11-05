// SPDX-License-Identifier: MPL-2.0

//! Exact eac original-owner image measured on the original GNU toolchain.
//!
//! These values bind the complete packaged image; they do not establish
//! a native boot, whole-guest peak, reserve, or the legacy 8/16 MiB gate.

pub const PROFILE: &str = "g2-original-owner-publish-v1";
pub const OWNER_SHA256: &str = "0c11e60e56e22116b82b4188c3a3b4986fd3f22fce42db9d4f85281af7faffaf";
pub const FILE_BYTES: usize = 19_631_544;
pub const MAPPED_BYTES: usize = 19_660_800;
pub const MAX_SEGMENT_BYTES: usize = 14_876_672;
pub const LOAD_SEGMENTS: usize = 4;
pub const INITIAL_ROLES: usize = 4;
