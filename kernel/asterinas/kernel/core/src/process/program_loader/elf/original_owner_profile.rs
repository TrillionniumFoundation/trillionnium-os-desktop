// SPDX-License-Identifier: MPL-2.0

//! One source-reviewed original owner image, not a caller-selected size budget.
//!
//! Measurements belong to the packaged a39/1.96 owner retained in
//! results/g2-original-owner-size-20261103. A different image requires a new
//! profile review. These constants do not reserve whole-guest/runtime memory.

pub const PROFILE: &str = "g2-original-owner-a39-v1";
pub const OWNER_SHA256: &str = "6ce96a0785b2cbb51bb71fabb2973c1e04d93e213d56694b42b4d717ed55a454";
pub const FILE_BYTES: usize = 20_138_584;
pub const MAPPED_BYTES: usize = 20_168_704;
pub const MAX_SEGMENT_BYTES: usize = 15_323_136;
pub const LOAD_SEGMENTS: usize = 4;
pub const INITIAL_ROLES: usize = 4;
