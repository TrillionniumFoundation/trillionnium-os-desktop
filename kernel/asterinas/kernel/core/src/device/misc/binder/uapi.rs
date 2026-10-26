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
pub(super) const INCREFS: u32 = 0x4004_6304;
pub(super) const ACQUIRE: u32 = 0x4004_6305;
pub(super) const RELEASE: u32 = 0x4004_6306;
pub(super) const DECREFS: u32 = 0x4004_6307;
pub(super) const INCREFS_DONE: u32 = 0x4010_6308;
pub(super) const ACQUIRE_DONE: u32 = 0x4010_6309;
pub(super) const REQUEST_DEATH_NOTIFICATION: u32 = 0x400c_630e;
pub(super) const CLEAR_DEATH_NOTIFICATION: u32 = 0x400c_630f;
pub(super) const DEAD_BINDER_DONE: u32 = 0x4008_6310;
pub(super) const BR_DEAD_BINDER: u32 = 0x8008_720f;
pub(super) const BR_CLEAR_DEATH_NOTIFICATION_DONE: u32 = 0x8008_7210;
pub(super) const ENTER_LOOPER: u32 = 0x630c;
pub(super) const EXIT_LOOPER: u32 = 0x630d;
pub(super) const BR_TRANSACTION: u32 = 0x8040_7202;
pub(super) const BR_REPLY: u32 = 0x8040_7203;
pub(super) const BR_DEAD_REPLY: u32 = 0x7205;
pub(super) const BR_TRANSACTION_COMPLETE: u32 = 0x7206;
pub(super) const BR_INCREFS: u32 = 0x8010_7207;
pub(super) const BR_ACQUIRE: u32 = 0x8010_7208;
pub(super) const BR_RELEASE: u32 = 0x8010_7209;
pub(super) const BR_DECREFS: u32 = 0x8010_720a;
pub(super) const ACCEPTS_FDS: u32 = 0x100;
pub(super) const TF_ACCEPT_FDS: u32 = 0x10;
pub(super) const TYPE_FD: u32 = 0x6664_2a85;
pub(super) const TYPE_BINDER: u32 = 0x7362_2a85;
pub(super) const TYPE_WEAK_BINDER: u32 = 0x7762_2a85;
pub(super) const TYPE_HANDLE: u32 = 0x7368_2a85;
pub(super) const TYPE_WEAK_HANDLE: u32 = 0x7768_2a85;

#[repr(C)]
#[derive(Clone, Copy, Debug, Default, Pod)]
pub(super) struct FlatObject {
    pub kind: u32,
    pub flags: u32,
    pub value: u64,
    pub cookie: u64,
}
#[repr(C)]
#[derive(Clone, Copy, Debug, Default, Pod)]
pub(super) struct PtrCookie {
    pub pointer: u64,
    pub cookie: u64,
}

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
