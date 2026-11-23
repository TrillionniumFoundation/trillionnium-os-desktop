//! Fixed CP3A capability policy, not an execution-admission constructor.
//!
//! The original official GSI's system and 38 APEX init scripts explicitly
//! request these 23 capabilities. Init also needs SETPCAP to set its child
//! services' inheritable/ambient sets. The namespace owner must separately
//! prove the original images and choose this profile through its typed wire
//! phase. No runtime configuration supplies a bitmask or arbitrary cap name.

#[path = "production_activation_input_profile.rs"]
pub(crate) mod activation_inputs;
#[path = "production_apex_input_profile.rs"]
pub(crate) mod apex_inputs;
#[path = "production_query_input_profile.rs"]
pub(crate) mod query_inputs;

pub(crate) const SCOPE: &str = "android_cp3a_scoped_capabilities_v1";
pub(crate) const SYSTEM_BYTES: u64 = 2_294_853_632;
pub(crate) const SYSTEM_SHA256: &str =
    "dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4";
pub(crate) const INIT_BYTES: u64 = 2_934_488;
pub(crate) const INIT_SHA256: &str =
    "9f69cc83a88db5f8533014cfea5ad9ea8e0454120335329aec27f8d65b2a9537";

// CHOWN, DAC_OVERRIDE, DAC_READ_SEARCH, FOWNER, FSETID, KILL, SETGID,
// SETUID, SETPCAP, NET_BIND_SERVICE, NET_ADMIN, NET_RAW, IPC_LOCK,
// SYS_CHROOT, SYS_PTRACE, SYS_ADMIN, SYS_NICE, SYS_RESOURCE, MKNOD,
// AUDIT_CONTROL, SYSLOG, WAKE_ALARM, BLOCK_SUSPEND, PERFMON.
pub(crate) const CAPABILITIES: u64 = 0x0000_005c_49ac_75ff;
pub(crate) const CAP_LAST: u32 = 40;

/// This rejects the initial namespace map as well as an identity-root map.
/// It is a raw-child defence in addition to the parent's actual lease/map
/// validation. Both complete UID and GID maps must have one subordinate range.
pub(crate) fn subordinate_map(bytes: &[u8]) -> bool {
    if bytes.is_empty() || bytes.len() > 256 || bytes.last() != Some(&b'\n') || bytes.contains(&0) {
        return false;
    }
    let Ok(text) = std::str::from_utf8(bytes) else {
        return false;
    };
    if text.lines().count() != 1 {
        return false;
    }
    let mut fields = text.split_ascii_whitespace();
    let mut values = [0_u64; 3];
    for value in &mut values {
        let Some(field) = fields.next() else {
            return false;
        };
        if field.is_empty() || !field.bytes().all(|byte| byte.is_ascii_digit()) {
            return false;
        }
        let Ok(number) = field.parse::<u64>() else {
            return false;
        };
        *value = number;
    }
    fields.next().is_none()
        && values[0] == 0
        && values[1] >= 65_536
        && values[2] >= 65_536
        && values[1]
            .checked_add(values[2])
            .is_some_and(|end| end <= u64::from(u32::MAX))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cp3a_profile_has_exact_service_union_without_unrequested_global_administration() {
        let selected = [
            0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 13, 14, 18, 19, 21, 23, 24, 27, 30, 34, 35, 36, 38,
        ];
        assert_eq!(CAPABILITIES.count_ones(), selected.len() as u32);
        assert_eq!(
            CAPABILITIES,
            selected
                .into_iter()
                .fold(0_u64, |mask, cap| mask | (1_u64 << cap))
        );
        // SYS_MODULE, SYS_RAWIO, SYS_PACCT, SYS_BOOT, SYS_TIME, SYS_TTY_CONFIG,
        // LEASE, AUDIT_WRITE, SETFCAP, MAC_OVERRIDE, MAC_ADMIN, AUDIT_READ,
        // BPF and CHECKPOINT_RESTORE have no place in this fixed profile.
        for cap in [16, 17, 20, 22, 25, 26, 28, 29, 31, 32, 33, 37, 39, 40] {
            assert_eq!(CAPABILITIES & (1_u64 << cap), 0);
        }
        assert_eq!(CAPABILITIES >> (CAP_LAST + 1), 0);
    }

    #[test]
    fn scoped_profile_rejects_initial_identity_partial_and_overflowing_id_maps() {
        for valid in [
            b"         0     200000     100000\n".as_slice(),
            b"0 65536 65536\n",
        ] {
            assert!(subordinate_map(valid));
        }
        for invalid in [
            b"0 0 4294967295\n".as_slice(),
            b"0 0 100000\n",
            b"1 200000 100000\n",
            b"0 200000 0\n",
            b"0 200000 65535\n",
            b"0 200000 100000",
            b"0 +200000 100000\n",
            b"0 4294901760 65536\n",
            b"0 18446744073709551615 65536\n",
            b"0 200000 100000 0\n",
            b"0 200000 100000\n100000 400000 1\n",
            b"0 200000 100000\0\n",
            b"\xff\n",
        ] {
            assert!(!subordinate_map(invalid), "accepted {invalid:?}");
        }
        assert!(!subordinate_map(&[b' '; 257]));
    }
}
