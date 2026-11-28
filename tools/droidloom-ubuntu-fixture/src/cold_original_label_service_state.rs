//! Fixed normal systemd state declarations. The source factory verifies each
//! exact unit from its admitted normal package before this contract is usable.
pub(super) struct UnitContract {
    pub name: &'static str,
    pub package: &'static str,
    pub bytes: u64,
    pub sha256: &'static str,
    pub state: &'static str,
}
pub(super) const UNITS: [UnitContract; 3] = [
    UnitContract {
        name: "systemd-random-seed.service",
        package: "systemd",
        bytes: 1187,
        sha256: "e4b935cc3c5aa680af2addebc0af1507d46c0f0f638bed3497a46b1db0ee51f6",
        state: "/var/lib/systemd/random-seed",
    },
    UnitContract {
        name: "systemd-timesyncd.service",
        package: "systemd-timesyncd",
        bytes: 1775,
        sha256: "a26f8693ba1a3c2af252bda0c24cda0679f85d3f1a327d1f3dffa919b8ca12e2",
        state: "/var/lib/systemd/timesync",
    },
    UnitContract {
        name: "systemd-logind.service",
        package: "systemd",
        bytes: 2088,
        sha256: "37563c6df1a510141bfd0777c20dfcc1c17087cdb56d3f71971a57d3cd380e64",
        state: "/var/lib/systemd/linger",
    },
];

// The actual gentmp2 source roundtrip confirms in-place seed writes/truncate,
// with only this additional absent/one-byte xattr. It does not atomically
// replace the inode. No seed contents are read by label preparation/recovery.
pub(super) const RANDOM_SEED_SOURCE: &str =
    "40f53a6f8387769fe48974be684018b002f1133bb66fde6800f617aaafce79b1";
pub(super) const TIMESYNC_SOURCE: &str =
    "6176f0d1c3a6ef03ad1cbd8e57c14f6e24a1369b598f251c3c6322f0f5d7137d";
pub(super) const CREDITABLE: &str = "user.random-seed-creditable";

pub(super) fn state_path(path: &std::path::Path) -> bool {
    let Some(path) = path.to_str() else {
        return false;
    };
    path == "/var/lib/systemd/timesync"
        || path == "/var/lib/systemd/timesync/clock"
        || path == "/var/lib/systemd/linger"
        || path
            .strip_prefix("/var/lib/systemd/linger/")
            .is_some_and(|name| {
                !name.is_empty()
                    && name.len() <= 256
                    && name
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b))
            })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn state_contract_never_opens_generic_var_lib_or_other_account_paths() {
        for path in [
            "/var/lib/systemd/timesync",
            "/var/lib/systemd/timesync/clock",
            "/var/lib/systemd/linger/alex",
        ] {
            assert!(state_path(std::path::Path::new(path)));
        }
        for path in [
            "/var/lib",
            "/var/lib/dpkg/status",
            "/var/lib/systemd/linger/../other",
            "/var/lib/systemd/timesync/arbitrary",
            "/var/lib/systemd/linger/alex/child",
            "/var/lib/NetworkManager",
        ] {
            assert!(!state_path(std::path::Path::new(path)));
        }
    }
}
