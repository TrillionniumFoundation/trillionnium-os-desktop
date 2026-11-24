//! Finite Package Manager sessions. No request carries paths, flags, shell text,
//! executable names, domains or caller-chosen split names.
use super::*;
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(tag = "install", deny_unknown_fields)]
pub(crate) enum InstallCommand {
    Create {
        user: u32,
        bytes: u64,
    },
    Write {
        session: u32,
        index: u32,
        bytes: u64,
    },
    Commit {
        session: u32,
    },
    Abandon {
        session: u32,
    },
}
pub(crate) const MAX_INSTALL_BYTES: u64 = 2 * 1024 * 1024 * 1024;
impl InstallCommand {
    pub(super) fn validate(&self) -> Result<()> {
        match *self {
            Self::Create { user, bytes } => require(
                user <= 21_474 && (4..=MAX_INSTALL_BYTES).contains(&bytes),
                "install user or total size is outside the fixed session",
            ),
            Self::Write {
                session,
                index,
                bytes,
            } => require(
                valid_session(session) && index < 32 && (4..=MAX_INSTALL_BYTES).contains(&bytes),
                "install write is outside the fixed session or APK segment",
            ),
            Self::Commit { session } | Self::Abandon { session } => require(
                valid_session(session),
                "install session identity is not bounded and positive",
            ),
        }
    }
    pub(super) fn input_bytes(&self) -> Option<u64> {
        match *self {
            Self::Write { bytes, .. } => Some(bytes),
            _ => None,
        }
    }
    pub(super) fn arguments(&self) -> Result<Vec<CString>> {
        self.validate()?;
        let mut parts = vec!["/system/bin/cmd".to_string(), "package".to_string()];
        parts.extend(match *self {
            Self::Create { user, bytes } => vec![
                "install-create".into(),
                "-r".into(),
                "--user".into(),
                user.to_string(),
                "-S".into(),
                bytes.to_string(),
            ],
            Self::Write {
                session,
                index,
                bytes,
            } => vec![
                "install-write".into(),
                "-S".into(),
                bytes.to_string(),
                session.to_string(),
                format!("split-{index:04}.apk"),
            ],
            Self::Commit { session } => vec!["install-commit".into(), session.to_string()],
            Self::Abandon { session } => vec!["install-abandon".into(), session.to_string()],
        });
        parts
            .into_iter()
            .map(|part| CString::new(part).map_err(external))
            .collect()
    }
}
fn valid_session(value: u32) -> bool {
    value > 0 && value <= i32::MAX as u32
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn installation_commands_preserve_one_finite_atomic_session() {
        let write = InstallCommand::Write {
            session: 23,
            index: 1,
            bytes: 1234,
        };
        assert_eq!(
            write
                .arguments()
                .unwrap()
                .iter()
                .map(|s| s.to_str().unwrap())
                .collect::<Vec<_>>(),
            [
                "/system/bin/cmd",
                "package",
                "install-write",
                "-S",
                "1234",
                "23",
                "split-0001.apk"
            ]
        );
        assert_eq!(write.input_bytes(), Some(1234));
        assert_eq!(InstallCommand::Commit { session: 23 }.input_bytes(), None);
        for value in [
            InstallCommand::Create {
                user: u32::MAX,
                bytes: 8,
            },
            InstallCommand::Write {
                session: 0,
                index: 0,
                bytes: 8,
            },
            InstallCommand::Write {
                session: 1,
                index: 32,
                bytes: 8,
            },
            InstallCommand::Write {
                session: 1,
                index: 0,
                bytes: MAX_INSTALL_BYTES + 1,
            },
            InstallCommand::Commit { session: u32::MAX },
        ] {
            assert!(value.validate().is_err());
        }
        for raw in [
            r#"{"install":"Write","session":1,"index":0,"bytes":8,"path":"/data/other.apk"}"#,
            r#"{"install":"Create","user":0,"bytes":8,"flags":["-d"]}"#,
            r#"{"install":"Uninstall","package":"target"}"#,
        ] {
            assert!(serde_json::from_str::<InstallCommand>(raw).is_err());
        }
    }
}
