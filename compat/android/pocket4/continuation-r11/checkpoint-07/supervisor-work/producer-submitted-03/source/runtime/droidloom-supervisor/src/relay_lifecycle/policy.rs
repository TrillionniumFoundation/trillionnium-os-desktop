//! Explicit image and finite-resource contract for the opt-in relay path.
use serde::{Deserialize, Serialize};
use std::path::{Component, Path, PathBuf};

/// One prequalified package artifact; the digest is an authority input.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RelayArtifact {
    /// Normalized, root-owned immutable artifact path.
    pub path: PathBuf,
    /// Exact lowercase SHA-256.
    pub sha256: String,
}

/// No production budget or artifact can be inferred from the canary profile.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PressureRelaySpec {
    /// Existing delegated cgroup-v2 parent; controllers must already be enabled.
    pub cgroup_parent: PathBuf,
    /// Finite aggregate maximum, installed before any child joins.
    pub memory_max_bytes: u64,
    /// Finite pressure boundary below the maximum.
    pub memory_high_bytes: u64,
    /// The current contract requires zero swap.
    pub memory_swap_max_bytes: u64,
    /// CPU quota in microseconds.
    pub cpu_quota_us: u64,
    /// CPU period in microseconds.
    pub cpu_period_us: u64,
    /// Aggregate task maximum for the private generation.
    pub tasks_max: u32,
    /// Maximum time to receive the actual second-stage init HELLO.
    pub entry_timeout_ms: u32,
    /// Constructor's complete finite handshake timeout.
    pub bootstrap_timeout_ms: u32,
    /// Root caller's independently qualified native LMKD role.
    pub lmkd_uid: u32,
    /// Root caller's independently qualified native LMKD primary group.
    pub lmkd_gid: u32,
    /// Exact host broker executable.
    pub broker: RelayArtifact,
    /// Exact paired host entry executable, checked before namespace creation.
    pub entry_supervisor: RelayArtifact,
    /// Exact Android native relay-capable LMKD executable.
    pub lmkd: RelayArtifact,
    /// Exact Android init barrier library.
    pub init_barrier: RelayArtifact,
    /// Exact paired single-mount-namespace Android init digest.
    pub init_sha256: String,
    /// Exact Android bootstrap linker paired with that init.
    pub init_linker_sha256: String,
    /// Exact pre-overlay service file from the paired Android image.
    pub lmkd_rc_sha256: String,
    /// Exact pre-existing SELinux compatibility preload digest.
    pub compat_preload_sha256: String,
}

pub(crate) fn digest(text: &str) -> Result<[u8; 32], &'static str> {
    if text.len() != 64 { return Err("SHA-256 must contain 64 lowercase hex characters"); }
    let mut value = [0; 32];
    for (index, pair) in text.as_bytes().chunks_exact(2).enumerate() {
        let digit = |byte: u8| match byte {
            b'0'..=b'9' => Ok(byte - b'0'),
            b'a'..=b'f' => Ok(byte - b'a' + 10),
            _ => Err("SHA-256 must be lowercase hexadecimal"),
        };
        value[index] = digit(pair[0])? * 16 + digit(pair[1])?;
    }
    if value == [0; 32] { return Err("zero SHA-256 is not an artifact identity"); }
    Ok(value)
}
fn absolute(path: &Path) -> bool {
    path.is_absolute() && path.components().skip(1).all(|part| matches!(part, Component::Normal(_)))
}
impl PressureRelaySpec {
    pub(crate) fn validate(&self, data: &Path, runtime: &Path) -> Vec<String> {
        let mut errors = Vec::new();
        if !absolute(&self.cgroup_parent)
            || !self.cgroup_parent.starts_with("/sys/fs/cgroup")
            || self.cgroup_parent == Path::new("/sys/fs/cgroup") {
            errors.push("pressure_relay.cgroup_parent must name an explicit delegated child below /sys/fs/cgroup".into());
        }
        if self.memory_max_bytes > i64::MAX as u64 || self.memory_high_bytes == 0 || self.memory_high_bytes >= self.memory_max_bytes
            || self.memory_swap_max_bytes != 0 {
            errors.push("pressure_relay requires 0 < memory.high < finite memory.max and memory.swap.max=0".into());
        }
        if !(1_000..=1_000_000).contains(&self.cpu_period_us)
            || self.cpu_quota_us < 1_000 || self.tasks_max < 2 {
            errors.push("pressure_relay requires explicit finite CPU and task limits".into());
        }
        if !(10..=20_000).contains(&self.bootstrap_timeout_ms)
            || !(10..=120_000).contains(&self.entry_timeout_ms)
            || self.entry_timeout_ms < self.bootstrap_timeout_ms {
            errors.push("pressure_relay timeouts must be finite and include the constructor interval".into());
        }
        if [self.lmkd_uid, self.lmkd_gid].iter().any(|id| *id == 0 || *id == u32::MAX) {
            errors.push("pressure_relay LMKD role must be an explicit non-root UID/GID".into());
        }
        for (name, artifact) in [("broker", &self.broker), ("entry_supervisor", &self.entry_supervisor), ("lmkd", &self.lmkd), ("init_barrier", &self.init_barrier)] {
            if !absolute(&artifact.path) || artifact.path.starts_with(data) || artifact.path.starts_with(runtime) {
                errors.push(format!("pressure_relay.{name} must be a normalized package path outside cell-writable data/runtime"));
            }
            if let Err(error) = digest(&artifact.sha256) { errors.push(format!("pressure_relay.{name}: {error}")); }
        }
        for (name, value) in [("init_sha256", &self.init_sha256), ("init_linker_sha256", &self.init_linker_sha256), ("lmkd_rc_sha256", &self.lmkd_rc_sha256), ("compat_preload_sha256", &self.compat_preload_sha256)] {
            if let Err(error) = digest(value) { errors.push(format!("pressure_relay.{name}: {error}")); }
        }
        errors
    }
    pub(crate) fn nonce() -> std::io::Result<[u8; 32]> {
        let mut result = [0u8; 32];
        let mut filled = 0;
        while filled < result.len() {
            // SAFETY: the remaining output slice is live and writable.
            let n = unsafe { libc::getrandom(result[filled..].as_mut_ptr().cast(), result.len() - filled, 0) };
            if n < 0 {
                let error = std::io::Error::last_os_error();
                if error.kind() == std::io::ErrorKind::Interrupted { continue; }
                return Err(error);
            }
            if n == 0 { return Err(std::io::Error::other("getrandom returned no entropy")); }
            filled += n as usize;
        }
        if result == [0; 32] { return Err(std::io::Error::other("zero generation nonce")); }
        Ok(result)
    }
}
pub(crate) fn hex(value: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut result = String::with_capacity(value.len() * 2);
    for byte in value {
        result.push(DIGITS[(byte >> 4) as usize] as char);
        result.push(DIGITS[(byte & 15) as usize] as char);
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    pub(super) fn policy() -> PressureRelaySpec {
        let artifact = |name| RelayArtifact { path: PathBuf::from(format!("/usr/lib/droidloom/test/{name}")), sha256: "1".repeat(64) };
        PressureRelaySpec { cgroup_parent: "/sys/fs/cgroup/owned-test-parent".into(),
            memory_max_bytes: 1024 * 1024 * 1024, memory_high_bytes: 768 * 1024 * 1024,
            memory_swap_max_bytes: 0, cpu_quota_us: 100_000, cpu_period_us: 100_000, tasks_max: 64,
            entry_timeout_ms: 20_000, bootstrap_timeout_ms: 10_000, lmkd_uid: 1069, lmkd_gid: 1069,
            broker: artifact("broker"), entry_supervisor: artifact("supervisor"), lmkd: artifact("lmkd"), init_barrier: artifact("barrier.so"),
            init_sha256: "2".repeat(64), init_linker_sha256: "4".repeat(64), lmkd_rc_sha256: "6".repeat(64), compat_preload_sha256: "3".repeat(64) }
    }
    fn valid(p: &PressureRelaySpec) -> bool { p.validate(Path::new("/data"), Path::new("/run/cell")).is_empty() }
    #[test]
    fn finite_budget_and_authority_have_no_implicit_defaults() {
        let p = policy(); assert!(valid(&p));
        let mut value = serde_json::to_value(&p).unwrap();
        for required in ["memory_max_bytes", "memory_high_bytes", "cpu_quota_us", "tasks_max", "init_sha256", "init_linker_sha256", "lmkd_rc_sha256", "entry_supervisor", "broker"] {
            let saved = value.as_object_mut().unwrap().remove(required).unwrap();
            assert!(serde_json::from_value::<PressureRelaySpec>(value.clone()).is_err());
            value.as_object_mut().unwrap().insert(required.into(), saved);
        }
        value["unknown_override"] = true.into();
        assert!(serde_json::from_value::<PressureRelaySpec>(value).is_err());
    }
    #[test]
    fn unlimited_or_guest_writable_authorities_are_rejected() {
        let p = policy();
        let mut q = p.clone(); q.memory_high_bytes = 0; assert!(!valid(&q));
        q = p.clone(); q.memory_high_bytes = q.memory_max_bytes; assert!(!valid(&q));
        q = p.clone(); q.memory_swap_max_bytes = 1; assert!(!valid(&q));
        q = p.clone(); q.cgroup_parent = "/sys/fs/cgroup".into(); assert!(!valid(&q));
        q = p.clone(); q.broker.path = "/data/broker".into(); assert!(!valid(&q));
        q = p.clone(); q.lmkd_uid = 0; assert!(!valid(&q));
        q = p.clone(); q.init_sha256 = "0".repeat(64); assert!(!valid(&q));
        q = p; q.bootstrap_timeout_ms = 20_001; assert!(!valid(&q));
    }
    #[test]
    fn nonce_and_digest_roundtrip_are_strict() {
        let nonce = PressureRelaySpec::nonce().unwrap();
        assert_eq!(digest(&hex(&nonce)).unwrap(), nonce);
        assert!(digest(&"A".repeat(64)).is_err());
        assert!(digest(&"0".repeat(64)).is_err());
        assert!(digest("1234").is_err());
    }
}
