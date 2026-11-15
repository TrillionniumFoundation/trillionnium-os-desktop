//! Closed operations for the original broker's authenticated worker channel.
//! These values select literal argv and a fixed MAC role. They do not contain
//! an executable path, PID, namespace, descriptor number, or caller MAC label.
use super::*;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum OperationDomain {
    Query,
    Browser,
}
impl OperationDomain {
    pub(super) const fn context(self) -> &'static str {
        match self {
            Self::Query => "u:r:droidloom_query:s0",
            Self::Browser => "u:r:droidloom_browser:s0",
        }
    }

    pub(super) const fn terminated(self) -> &'static [u8] {
        match self {
            Self::Query => b"u:r:droidloom_query:s0\0",
            Self::Browser => b"u:r:droidloom_browser:s0\0",
        }
    }
}

/// This closed command can only be lent the original Ready owner. It carries
/// no package-success flag and cannot be converted to an application read.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(tag = "browser", deny_unknown_fields)]
pub(crate) enum BrowserCommand {
    Resolve { user: u32, url: String },
    Start { user: u32, url: String },
}

impl BrowserCommand {
    pub(super) fn validate(&self) -> Result<()> {
        let (user, url) = match self {
            Self::Resolve { user, url } | Self::Start { user, url } => (*user, url),
        };
        require(user <= 21_474, "invalid browser Android user")?;
        crate::control::application_probe::validate_https_url(url).map_err(external)
    }

    pub(super) fn from_command(args: &[String], user: u32, url: &str) -> Result<Self> {
        let text: Vec<&str> = args.iter().map(String::as_str).collect();
        let value = match text.as_slice() {
            [
                "/system/bin/cmd",
                "package",
                "resolve-activity",
                "--brief",
                "--user",
                observed_user,
                "-a",
                "android.intent.action.VIEW",
                "-c",
                "android.intent.category.BROWSABLE",
                "-d",
                observed_url,
            ] => {
                require(
                    canonical_user(observed_user)? == user && *observed_url == url,
                    "browser resolver input differs from this bound operation",
                )?;
                Self::Resolve {
                    user,
                    url: url.into(),
                }
            }
            [
                "/system/bin/cmd",
                "activity",
                "start-activity",
                "-W",
                "--user",
                observed_user,
                "-a",
                "android.intent.action.VIEW",
                "-c",
                "android.intent.category.BROWSABLE",
                "-d",
                observed_url,
            ] => {
                require(
                    canonical_user(observed_user)? == user && *observed_url == url,
                    "browser start input differs from this bound operation",
                )?;
                Self::Start {
                    user,
                    url: url.into(),
                }
            }
            _ => return Err(reject("command is outside the fixed implicit browser flow")),
        };
        value.validate()?;
        Ok(value)
    }

    pub(super) fn arguments(&self) -> Result<Vec<CString>> {
        self.validate()?;
        let (user, url, service, action, option) = match self {
            Self::Resolve { user, url } => (*user, url, "package", "resolve-activity", "--brief"),
            Self::Start { user, url } => (*user, url, "activity", "start-activity", "-W"),
        };
        let user = user.to_string();
        [
            "/system/bin/cmd",
            service,
            action,
            option,
            "--user",
            &user,
            "-a",
            "android.intent.action.VIEW",
            "-c",
            "android.intent.category.BROWSABLE",
            "-d",
            url,
        ]
        .into_iter()
        .map(|value| CString::new(value).map_err(|_| reject("NUL in fixed browser input")))
        .collect()
    }

    pub(super) fn domain(&self) -> OperationDomain {
        match self {
            Self::Resolve { .. } => OperationDomain::Query,
            Self::Start { .. } => OperationDomain::Browser,
        }
    }
}

/// This is only the private same-binary worker message. Public control clients
/// cannot send it directly or acquire its original-owner descriptor channel.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(tag = "operation", deny_unknown_fields)]
pub(super) enum ApplicationOperation {
    Read { value: ApplicationRead },
    Browser { value: BrowserCommand },
}

impl ApplicationOperation {
    pub(super) fn validate(&self) -> Result<()> {
        match self {
            Self::Read { value } => value.validate(),
            Self::Browser { value } => value.validate(),
        }
    }

    pub(super) fn binary(&self) -> &'static CStr {
        match self {
            Self::Read { value } => value.binary(),
            Self::Browser { .. } => c"cmd",
        }
    }

    pub(super) fn arguments(&self) -> Result<Vec<CString>> {
        match self {
            Self::Read { value } => value.arguments(),
            Self::Browser { value } => value.arguments(),
        }
    }

    pub(super) fn domain(&self) -> OperationDomain {
        match self {
            Self::Read { .. } => OperationDomain::Query,
            Self::Browser { value } => value.domain(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn strings(command: &BrowserCommand) -> Vec<String> {
        command
            .arguments()
            .unwrap()
            .into_iter()
            .map(|v| v.into_string().unwrap())
            .collect()
    }

    #[test]
    fn production_browser_operation_keeps_read_role_separate_from_activity_start() {
        let url = "https://example.org/firefox-fixture?mode=public";
        for command in [
            BrowserCommand::Resolve {
                user: 0,
                url: url.into(),
            },
            BrowserCommand::Start {
                user: 0,
                url: url.into(),
            },
        ] {
            let argv = strings(&command);
            assert_eq!(
                BrowserCommand::from_command(&argv, 0, url).unwrap(),
                command
            );
            assert!(ApplicationRead::from_command(&argv).is_err());
        }
        let read = ApplicationOperation::Read {
            value: ApplicationRead::PackagePaths {
                package: "org.mozilla.firefox".into(),
                user: 0,
            },
        };
        assert_eq!(read.domain(), OperationDomain::Query);
        assert_eq!(
            BrowserCommand::Resolve {
                user: 0,
                url: url.into()
            }
            .domain(),
            OperationDomain::Query
        );
        assert_eq!(
            BrowserCommand::Start {
                user: 0,
                url: url.into()
            }
            .domain(),
            OperationDomain::Browser
        );
        assert_ne!(
            OperationDomain::Query.context(),
            OperationDomain::Browser.context()
        );
        assert_eq!(
            OperationDomain::Query.terminated(),
            b"u:r:droidloom_query:s0\0"
        );
        assert_eq!(
            OperationDomain::Browser.terminated(),
            b"u:r:droidloom_browser:s0\0"
        );
    }

    #[test]
    fn production_browser_operation_rejects_cross_user_url_explicit_component_and_injected_role() {
        let url = "https://example.org/fixture";
        let start = BrowserCommand::Start {
            user: 10,
            url: url.into(),
        };
        let argv = strings(&start);
        assert!(BrowserCommand::from_command(&argv, 0, url).is_err());
        assert!(BrowserCommand::from_command(&argv, 10, "https://example.org/other").is_err());
        let mut explicit = argv.clone();
        explicit.extend(["-n".into(), "org.mozilla.firefox/.App".into()]);
        assert!(BrowserCommand::from_command(&explicit, 10, url).is_err());
        for invalid in [
            "file:///data/user/0/a",
            "https://example.org/\nsecret",
            "https://user:pass@example.org/",
        ] {
            assert!(
                BrowserCommand::Start {
                    user: 10,
                    url: invalid.into()
                }
                .arguments()
                .is_err()
            );
        }
        for message in [
            r#"{"operation":"Browser","value":{"browser":"Start","user":0,"url":"https://example.org/","domain":"u:r:shell:s0"}}"#,
            r#"{"operation":"Browser","value":{"browser":"Start","user":0,"url":"https://example.org/"},"pid":123}"#,
            r#"{"operation":"Command","argv":["/system/bin/sh","-c","true"]}"#,
        ] {
            assert!(serde_json::from_str::<ApplicationOperation>(message).is_err());
        }
    }
}
