// SPDX-License-Identifier: MPL-2.0
//! Linux 64-bit Binder v8 wire layout. This does not imply all v8 operations exist.
use crate::prelude::*;

pub(super) const WRITE_READ: u32 = 0xc030_6201;
pub(super) const SET_MAX_THREADS: u32 = 0x4004_6205;
pub(super) const SET_CONTEXT_MGR: u32 = 0x4004_6207;
pub(super) const THREAD_EXIT: u32 = 0x4004_6208;
pub(super) const VERSION: u32 = 0xc004_6209;
pub(super) const SET_CONTEXT_MGR_EXT: u32 = 0x4018_620d;
pub(super) const TRANSACTION: u32 = 0x4040_6300;
pub(super) const REPLY: u32 = 0x4040_6301;
pub(super) const FREE_BUFFER: u32 = 0x4008_6303;
pub(super) const ENTER_LOOPER: u32 = 0x630c;
pub(super) const EXIT_LOOPER: u32 = 0x630d;
pub(super) const BR_TRANSACTION: u32 = 0x8040_7202;
pub(super) const BR_REPLY: u32 = 0x8040_7203;
pub(super) const BR_DEAD_REPLY: u32 = 0x7205;
pub(super) const BR_TRANSACTION_COMPLETE: u32 = 0x7206;

#[repr(C)]
#[derive(Clone, Copy, Debug, Default, Pod)]
pub(super) struct WriteRead {
    pub write_size: u64,
    pub write_consumed: u64,
    pub write_buffer: u64,
    pub read_size: u64,
    pub read_consumed: u64,
    pub read_buffer: u64,
}
#[repr(C)]
#[derive(Clone, Copy, Debug, Default, Pod)]
pub(super) struct Transaction {
    pub target: u64,
    pub cookie: u64,
    pub code: u32,
    pub flags: u32,
    pub sender_pid: i32,
    pub sender_euid: u32,
    pub data_size: u64,
    pub offsets_size: u64,
    pub buffer: u64,
    pub offsets: u64,
}
const _: () = assert!(size_of::<WriteRead>() == 48 && size_of::<Transaction>() == 64);

#[cfg(ktest)]
mod tests {
    use ostd::prelude::*;

    use super::*;
    #[ktest]
    fn native_layout() {
        assert_eq!(core::mem::offset_of!(WriteRead, read_buffer), 40);
        assert_eq!(core::mem::offset_of!(Transaction, sender_euid), 28);
        assert_eq!(core::mem::offset_of!(Transaction, buffer), 48);
    }
}
