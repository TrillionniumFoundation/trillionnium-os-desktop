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
    Resolve {
        user: u32,
        url: String,
    },
    Start {
        user: u32,
        url: String,
        component: String,
    },
}

fn firefox_component_valid(component: &str) -> bool {
    let Some((owner, activity)) = component.split_once('/') else {
        return false;
    };
    let class = activity.strip_prefix('.').unwrap_or(activity);
    owner == "org.mozilla.firefox"
        && !class.is_empty()
        && class.split('.').all(|part| {
            !part.is_empty()
                && part
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'$'))
        })
}

/// Parse only the actual completed resolver's bounded stdout. The business
/// owner stores this value after successful command retirement; no serialized
/// resolution field or caller-supplied success record can advance its stage.
pub(super) fn resolved_firefox_component(output: &str) -> Result<String> {
    require(
        output.len() <= OUTPUT_LIMIT,
        "browser resolver output bound",
    )?;
    let mut components = output.lines().filter(|line| line.contains('/'));
    let component = components
        .next()
        .ok_or_else(|| reject("browser resolver returned no component"))?;
    require(
        components.next().is_none() && firefox_component_valid(component),
        "browser resolver did not select one valid Firefox component",
    )?;
    Ok(component.into())
}

impl BrowserCommand {
    pub(super) fn validate(&self) -> Result<()> {
        let (user, url) = match self {
            Self::Resolve { user, url } | Self::Start { user, url, .. } => (*user, url),
        };
        require(user <= 21_474, "invalid browser Android user")?;
        crate::control::application_probe::validate_https_url(url).map_err(external)?;
        if let Self::Start { component, .. } = self {
            require(
                firefox_component_valid(component),
                "invalid Firefox start component",
            )?;
        }
        Ok(())
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
                "-n",
                component,
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
                    component: (*component).into(),
                }
            }
            _ => return Err(reject("command is outside the fixed resolved browser flow")),
        };
        value.validate()?;
        Ok(value)
    }

    pub(super) fn arguments(&self) -> Result<Vec<CString>> {
        self.validate()?;
        let (user, url, service, action, option) = match self {
            Self::Resolve { user, url } => (*user, url, "package", "resolve-activity", "--brief"),
            Self::Start { user, url, .. } => (*user, url, "activity", "start-activity", "-W"),
        };
        let user = user.to_string();
        let mut arguments = vec!["/system/bin/cmd", service, action, option, "--user", &user];
        if let Self::Start { component, .. } = self {
            arguments.extend(["-n", component.as_str()]);
        }
        arguments.extend([
            "-a",
            "android.intent.action.VIEW",
            "-c",
            "android.intent.category.BROWSABLE",
            "-d",
            url,
        ]);
        arguments
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
                component: "org.mozilla.firefox/.LauncherAlias".into(),
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
                url: url.into(),
                component: "org.mozilla.firefox/.LauncherAlias".into(),
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
    fn production_browser_operation_rejects_cross_user_url_implicit_start_and_injected_role() {
        let url = "https://example.org/fixture";
        let start = BrowserCommand::Start {
            user: 10,
            url: url.into(),
            component: "org.mozilla.firefox/.LauncherAlias".into(),
        };
        let argv = strings(&start);
        assert!(BrowserCommand::from_command(&argv, 0, url).is_err());
        assert!(BrowserCommand::from_command(&argv, 10, "https://example.org/other").is_err());
        let mut implicit = argv.clone();
        implicit.drain(6..8);
        assert!(BrowserCommand::from_command(&implicit, 10, url).is_err());
        let mut repeated = argv.clone();
        repeated.extend(["-n".into(), "org.mozilla.firefox/.App".into()]);
        assert!(BrowserCommand::from_command(&repeated, 10, url).is_err());
        for invalid in [
            "file:///data/user/0/a",
            "https://example.org/\nsecret",
            "https://user:pass@example.org/",
        ] {
            assert!(
                BrowserCommand::Start {
                    user: 10,
                    url: invalid.into(),
                    component: "org.mozilla.firefox/.LauncherAlias".into(),
                }
                .arguments()
                .is_err()
            );
        }
        for message in [
            r#"{"operation":"Browser","value":{"browser":"Start","user":0,"url":"https://example.org/","component":"org.mozilla.firefox/.LauncherAlias","domain":"u:r:shell:s0"}}"#,
            r#"{"operation":"Browser","value":{"browser":"Start","user":0,"url":"https://example.org/","component":"org.mozilla.firefox/.LauncherAlias"},"pid":123}"#,
            r#"{"operation":"Command","argv":["/system/bin/sh","-c","true"]}"#,
        ] {
            assert!(serde_json::from_str::<ApplicationOperation>(message).is_err());
        }
    }

    #[test]
    fn production_browser_operation_requires_one_strict_resolved_firefox_component() {
        for component in [
            "org.mozilla.firefox/.LauncherAlias",
            "org.mozilla.firefox/org.mozilla.fenix.IntentReceiverActivity",
            "org.mozilla.firefox/.Outer$Inner",
        ] {
            let output = format!("priority=0 match=0x208000\n{component}\n");
            assert_eq!(resolved_firefox_component(&output).unwrap(), component);
            let start = BrowserCommand::Start {
                user: 10,
                url: "https://example.org/fixture".into(),
                component: component.into(),
            };
            assert_eq!(strings(&start)[7], component);
        }
        for output in [
            "No activity found",
            "org.other.browser/.Main",
            "org.mozilla.firefox/",
            "org.mozilla.firefox/.A\norg.mozilla.firefox/.B",
            "org.mozilla.firefox/.A\0",
            "org.mozilla.firefox/.A --user 0",
            "org.mozilla.firefox/../A",
        ] {
            assert!(resolved_firefox_component(output).is_err());
        }
    }

    #[test]
    fn production_browser_operation_wire_cannot_supply_a_resolution_witness() {
        let valid = serde_json::json!({
            "operation":"Browser",
            "value":{"browser":"Start","user":10,"url":"https://example.org/fixture",
                "component":"org.mozilla.firefox/.LauncherAlias"}
        });
        let decoded: ApplicationOperation = serde_json::from_value(valid.clone()).unwrap();
        decoded.validate().unwrap();
        let mut missing = valid.clone();
        missing["value"]
            .as_object_mut()
            .unwrap()
            .remove("component");
        assert!(serde_json::from_value::<ApplicationOperation>(missing).is_err());
        let mut claimed = valid.clone();
        claimed["value"]["resolved"] = serde_json::json!(true);
        assert!(serde_json::from_value::<ApplicationOperation>(claimed).is_err());
        for component in [
            "org.other.browser/.Main",
            "org.mozilla.firefox/.A\n",
            "org.mozilla.firefox/.A/extra",
        ] {
            let mut invalid = valid.clone();
            invalid["value"]["component"] = serde_json::json!(component);
            let decoded: ApplicationOperation = serde_json::from_value(invalid).unwrap();
            assert!(decoded.validate().is_err());
        }
    }
}

#[cfg(test)]
mod r17_component_regressions {
    use super::*;

    fn explicit_arguments() -> Vec<String> {
        [
            "/system/bin/cmd",
            "activity",
            "start-activity",
            "-W",
            "--user",
            "10",
            "-n",
            "org.mozilla.firefox/.LauncherAlias",
            "-a",
            "android.intent.action.VIEW",
            "-c",
            "android.intent.category.BROWSABLE",
            "-d",
            "https://example.org/fixture",
        ]
        .into_iter()
        .map(str::to_owned)
        .collect()
    }

    #[test]
    fn r17_component_regression_explicit_start_roundtrips_exact_argv() {
        let argv = explicit_arguments();
        let result = BrowserCommand::from_command(&argv, 10, "https://example.org/fixture");
        assert!(
            result.is_ok(),
            "resolved explicit command was rejected: {result:?}"
        );
        let actual = result
            .unwrap()
            .arguments()
            .unwrap()
            .into_iter()
            .map(|value| value.into_string().unwrap())
            .collect::<Vec<_>>();
        assert_eq!(actual, argv);
    }

    #[test]
    fn r17_component_regression_implicit_start_is_rejected() {
        let mut argv = explicit_arguments();
        argv.drain(6..8);
        assert!(
            BrowserCommand::from_command(&argv, 10, "https://example.org/fixture").is_err(),
            "implicit second resolution remains executable"
        );
    }
}
