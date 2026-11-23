//! Fixed linkerconfig trampoline ABI. This wire format is not an admission
//! capability: the broker must bind its actual peer PIDFD, MAC label, original
//! init generation, namespaces and exact executable before accepting AUTH.
//!
//! The only executed role is the held original linkerconfig ELF, with the
//! compile-time arguments `--target /linkerconfig`. No command, environment or
//! pathname can be selected by a packet. This ABI is independent of private
//! qualification probe protocols.

pub const MAGIC: u64 = 0x444c_4c4b_4346_4731;
pub const VERSION: u32 = 1;
pub const HELLO: u32 = 1;
pub const AUTH: u32 = 2;
pub const CHILD: u32 = 3;
pub const GO: u32 = 4;
pub const EXITED: u32 = 5;
pub const REAP: u32 = 6;
pub const REAPED: u32 = 7;
pub const DIAGNOSTIC: u32 = 8;
pub const ACK: u32 = 9;
pub const FAILED: u32 = 10;
pub const CANCEL: u32 = 11;
pub const PACKET_BYTES: usize = 128;
pub const DIAGNOSTIC_CHUNK: usize = 4096;
pub const OUTPUT_LIMIT: usize = 64 * 1024;
pub const MAX_COMMAND_NS: u64 = 30_000_000_000;
pub const HANDSHAKE_NS: u64 = 5_000_000_000;
pub const RETIREMENT_NS: u64 = 3_000_000_000;
pub const SOCKET_PATH: &[u8] = b"/dev/socket/droidloom-linkerconfig\0";

// Exact Linux 7.0.14 UAPI. EXIT becomes available from release_task(), not
// merely from a readable PIDFD or waitid(WNOWAIT). Always inspect the returned
// mask before interpreting exit_code; an unfilled zero is not success.
pub const PIDFD_INFO_EXIT: u64 = 1 << 3;
pub const PIDFD_INFO_SUPPORTED_MASK: u64 = 1 << 5;
pub const PIDFD_GET_INFO: u64 = 0xc050_ff0b;
#[repr(C)]
pub struct PidfdInfo {
    pub mask: u64,
    pub cgroupid: u64,
    pub pid: u32,
    pub tgid: u32,
    pub ppid: u32,
    pub ruid: u32,
    pub rgid: u32,
    pub euid: u32,
    pub egid: u32,
    pub suid: u32,
    pub sgid: u32,
    pub fsuid: u32,
    pub fsgid: u32,
    pub exit_code: i32,
    pub coredump_mask: u32,
    pub coredump_signal: u32,
    pub supported_mask: u64,
}
const _: () = assert!(core::mem::size_of::<PidfdInfo>() == 80);
const _: () = assert!(core::mem::offset_of!(PidfdInfo, exit_code) == 60);
const _: () = assert!(core::mem::offset_of!(PidfdInfo, supported_mask) == 72);
impl PidfdInfo {
    pub fn request_exit() -> Self {
        Self {
            mask: PIDFD_INFO_EXIT | PIDFD_INFO_SUPPORTED_MASK,
            cgroupid: 0,
            pid: 0,
            tgid: 0,
            ppid: 0,
            ruid: 0,
            rgid: 0,
            euid: 0,
            egid: 0,
            suid: 0,
            sgid: 0,
            fsuid: 0,
            fsgid: 0,
            exit_code: 0,
            coredump_mask: 0,
            coredump_signal: 0,
            supported_mask: 0,
        }
    }
}

pub fn raw_wait_status(code: i32, status: i32) -> Option<i32> {
    match code {
        1 if (0..=255).contains(&status) => Some(status << 8),
        2 if (1..=64).contains(&status) => Some(status),
        3 if (1..=64).contains(&status) => Some(status | 0x80),
        _ => None,
    }
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct Packet {
    pub magic: u64,
    pub version: u32,
    pub phase: u32,
    pub nonce: [u8; 32],
    pub owner_generation: [u8; 32],
    pub deadline_ns: u64,
    // Display/compare only. Kernel peer PIDFD/credentials create ownership;
    // this field must never be fed to pidfd_open, kill, waitpid or setns.
    pub child_pid: i32,
    pub exit_code: i32,
    pub exit_status: i32,
    pub error: i32,
    pub output_bytes: u64,
    pub data_length: u32,
    pub detail: u32,
    pub reserved: u64,
}

const _: () = assert!(core::mem::size_of::<Packet>() == PACKET_BYTES);
const _: () = assert!(core::mem::align_of::<Packet>() == 8);

impl Packet {
    pub const fn empty(phase: u32) -> Self {
        Self {
            magic: MAGIC,
            version: VERSION,
            phase,
            nonce: [0; 32],
            owner_generation: [0; 32],
            deadline_ns: 0,
            child_pid: 0,
            exit_code: 0,
            exit_status: 0,
            error: 0,
            output_bytes: 0,
            data_length: 0,
            detail: 0,
            reserved: 0,
        }
    }

    pub fn header_is_fixed(&self) -> bool {
        self.magic == MAGIC && self.version == VERSION && self.reserved == 0
    }

    pub fn session_matches(&self, session: &Self) -> bool {
        self.header_is_fixed()
            && self.nonce == session.nonce
            && self.owner_generation == session.owner_generation
            && self.deadline_ns == session.deadline_ns
            && self.child_pid == session.child_pid
    }

    pub fn nonempty_session(&self) -> bool {
        self.nonce.iter().any(|v| *v != 0) && self.owner_generation.iter().any(|v| *v != 0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn production_activation_protocol_binds_each_session_field_without_authority_from_packet() {
        let mut original = Packet::empty(AUTH);
        original.nonce = [7; 32];
        original.owner_generation = [9; 32];
        original.deadline_ns = 17;
        original.child_pid = 29;
        assert!(original.header_is_fixed() && original.nonempty_session());
        for kind in 0..7 {
            let mut bad = original;
            match kind {
                0 => bad.magic ^= 1,
                1 => bad.version += 1,
                2 => bad.nonce[31] ^= 1,
                3 => bad.owner_generation[0] ^= 1,
                4 => bad.deadline_ns += 1,
                5 => bad.child_pid += 1,
                6 => bad.reserved = 1,
                _ => unreachable!(),
            }
            assert!(!bad.session_matches(&original));
        }
        assert!(!Packet::empty(AUTH).nonempty_session());
        assert_eq!(PACKET_BYTES, 128);
        assert!(SOCKET_PATH.starts_with(b"/dev/socket/") && SOCKET_PATH.ends_with(b"\0"));
    }
}
