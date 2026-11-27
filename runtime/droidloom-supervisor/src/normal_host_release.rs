//! Source-shared comparison pins for the two normal host programs.
//! These serializable values are selected configuration, never process,
//! namespace, execution, installation, or business-acceptance authority.
//! The normal publishers derive them from two actual members of one admitted
//! host manifest. Only an authenticated opaque Main observation carries them
//! into an application baseline.
use serde::{Deserialize, Serialize};

pub const SCHEMA: &str = "droidloom.normal-host-release.v1";
pub const MANAGER: &str = "/usr/lib/droidloom/production/current/droidloomd";
pub const PRESENTER: &str = "/usr/bin/droidloom-wayland";
pub const MAX_PROGRAM_BYTES: u64 = 128 * 1024 * 1024;

#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NormalHostProgramPin {
    pub path: String,
    pub bytes: u64,
    pub sha256: String,
}
#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NormalHostRelease {
    pub schema: String,
    pub manager: NormalHostProgramPin,
    pub presenter: NormalHostProgramPin,
}
impl NormalHostRelease {
    /// Shape only. A parsed or caller-constructed value cannot authenticate
    /// the selected source, a live executable, or an application observation.
    pub fn validate(&self) -> Result<(), &'static str> {
        if self.schema != SCHEMA {
            return Err("normal host release schema differs");
        }
        for (pin, path) in [(&self.manager, MANAGER), (&self.presenter, PRESENTER)] {
            if pin.path != path
                || !(64..=MAX_PROGRAM_BYTES).contains(&pin.bytes)
                || pin.sha256.len() != 64
                || !pin.sha256.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            {
                return Err("normal host release requires two bounded fixed program pins");
            }
        }
        if self.manager.sha256 == self.presenter.sha256 {
            return Err("normal manager and presenter cannot be the same program");
        }
        Ok(())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn sample() -> NormalHostRelease {
        NormalHostRelease {
            schema: SCHEMA.into(),
            manager: NormalHostProgramPin { path: MANAGER.into(), bytes: 1024, sha256: "a".repeat(64) },
            presenter: NormalHostProgramPin { path: PRESENTER.into(), bytes: 2048, sha256: "b".repeat(64) },
        }
    }
    #[test]
    fn normal_host_release_rejects_path_aliases_unbounded_programs_and_same_program() {
        assert!(sample().validate().is_ok());
        for bad in ["/tmp/presenter", "/usr/bin/../bin/droidloom-wayland", "/proc/self/exe"] {
            let mut value = sample();
            value.presenter.path = bad.into();
            assert!(value.validate().is_err());
        }
        for size in [0, 63, MAX_PROGRAM_BYTES + 1] {
            let mut value = sample();
            value.presenter.bytes = size;
            assert!(value.validate().is_err());
        }
        let mut value = sample();
        value.presenter.sha256 = value.manager.sha256.clone();
        assert!(value.validate().is_err());
        value = sample();
        value.manager.sha256 = "A".repeat(64);
        assert!(value.validate().is_err());
    }
    #[test]
    fn normal_host_release_json_cannot_add_process_or_qualification_claims() {
        let value = sample();
        let mut raw = serde_json::to_value(&value).unwrap();
        raw["production_ready"] = true.into();
        assert!(serde_json::from_value::<NormalHostRelease>(raw).is_err());
        let mut raw = serde_json::to_value(&value).unwrap();
        raw["presenter"]["pid"] = 1234.into();
        assert!(serde_json::from_value::<NormalHostRelease>(raw).is_err());
    }
}
