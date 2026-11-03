// SPDX-License-Identifier: MPL-2.0

//! Host entry point for the production partition decoder's own regressions.
//! This does not compile or replace BlockDevice, OSTD, DMA or guest execution.

extern crate alloc;

#[path = "../../kernel/asterinas/kernel/core/comps/block/src/partition/table.rs"]
mod table;
