//! Closed operations for the original broker's authenticated worker channel.
//! These values select literal argv and a fixed MAC role. They do not contain
//! an executable path, PID, namespace, descriptor number, or caller MAC label.
use super::*;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum OperationDomain {
    Query,
    Browser,
    ContactsRead,
    LaunchRead,
    LaunchStart,
    Install,
    CatalogRead,
    DisplayControl,
}
impl OperationDomain {
    pub(super) const fn context(self) -> &'static str {
        match self {
            Self::Query => "u:r:droidloom_query:s0",
            Self::Browser => "u:r:droidloom_browser:s0",
            Self::ContactsRead => "u:r:droidloom_contacts_read:s0",
            Self::LaunchRead => "u:r:droidloom_launch_read:s0",
            Self::LaunchStart => "u:r:droidloom_launch_start:s0",
            Self::Install => "u:r:droidloom_install:s0",
            Self::CatalogRead => "u:r:droidloom_catalog_read:s0",
            Self::DisplayControl => "u:r:droidloom_display_control:s0",
        }
    }

    pub(super) const fn terminated(self) -> &'static [u8] {
        match self {
            Self::Query => b"u:r:droidloom_query:s0\0",
            Self::Browser => b"u:r:droidloom_browser:s0\0",
            Self::ContactsRead => b"u:r:droidloom_contacts_read:s0\0",
            Self::LaunchRead => b"u:r:droidloom_launch_read:s0\0",
            Self::LaunchStart => b"u:r:droidloom_launch_start:s0\0",
            Self::Install => b"u:r:droidloom_install:s0\0",
            Self::CatalogRead => b"u:r:droidloom_catalog_read:s0\0",
            Self::DisplayControl => b"u:r:droidloom_display_control:s0\0",
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
    Vintf { value: super::vintf::VintfRead },
    RuntimeAbi { value: super::runtime_abi_query::RuntimeAbiRead },
    UserZeroPackageInventory { value: super::package_inventory_query::UserZeroPackageInventoryRead },
    Browser { value: BrowserCommand },
    ContactsRead { value: ContactsQuery },
    Launch { value: LaunchCommand },
    Install { value: InstallCommand },
    Catalog { value: CatalogRequest },
    Display { value: DisplayCommand },
}

impl ApplicationOperation {
    pub(super) fn validate(&self) -> Result<()> {
        match self {
            Self::Read { value } => value.validate(),
            Self::Vintf { value } => value.validate(),
            Self::RuntimeAbi { value } => value.validate(),
            Self::UserZeroPackageInventory { value } => value.validate(),
            Self::Browser { value } => value.validate(),
            Self::ContactsRead { value } => value.validate(),
            Self::Launch { value } => value.validate(),
            Self::Install { value } => value.validate(),
            Self::Catalog { value } => value.validate(),
            Self::Display { value } => value.validate(),
        }
    }

    pub(super) const fn uses_app_process(&self) -> bool {
        matches!(self, Self::ContactsRead { .. } | Self::Catalog { .. })
    }
    pub(super) fn catalog_jar_digest(&self) -> Option<&str> {
        match self {
            Self::Catalog { value } => Some(value.jar_digest()),
            _ => None,
        }
    }
    pub(super) const fn output_limit(&self) -> usize {
        match self {
            Self::Catalog { .. } => super::catalog::OUTPUT_BYTES,
            Self::Vintf { value } => value.output_limit(),
            Self::RuntimeAbi { .. } => super::runtime_abi::OUTPUT_BYTES,
            Self::UserZeroPackageInventory { .. } => super::package_inventory::OUTPUT_BYTES,
            _ => OUTPUT_LIMIT,
        }
    }

    pub(super) fn install_input_bytes(&self) -> Option<u64> {
        match self {
            Self::Install { value } => value.input_bytes(),
            _ => None,
        }
    }
    pub(super) const fn needs_content_jar(&self) -> bool {
        matches!(self, Self::ContactsRead { .. })
    }

    pub(super) const fn descriptor_count(&self) -> usize {
        if self.needs_content_jar() { 17 } else { 15 }
    }

    pub(super) fn environment(&self, projection: QueryProjection) -> Vec<&'static CStr> {
        let mut values = vec![
            c"PATH=/system/bin:/system/xbin",
            c"LC_ALL=C",
            c"ANDROID_ROOT=/system",
            c"ANDROID_DATA=/data",
            c"ANDROID_ART_ROOT=/apex/com.android.art",
            c"ANDROID_RUNTIME_ROOT=/apex/com.android.runtime",
            c"ANDROID_I18N_ROOT=/apex/com.android.i18n",
            c"ANDROID_TZDATA_ROOT=/apex/com.android.tzdata",
        ];
        if self.uses_app_process() {
            values.extend(super::art_profile::ENVIRONMENT);
        }
        if self.needs_content_jar() {
            values.push(projection.content_classpath());
        } else if matches!(self, Self::Catalog { .. }) {
            values.push(c"CLASSPATH=/system/system_ext/framework/droidloom-input-bridge.jar");
        }
        values
    }

    pub(super) fn binary(&self) -> &'static CStr {
        match self {
            Self::Read { value } => value.binary(),
            Self::Vintf { value } => value.binary(),
            Self::Browser { .. } | Self::RuntimeAbi { .. } | Self::UserZeroPackageInventory { .. } => c"cmd",
            Self::ContactsRead { .. } | Self::Catalog { .. } => c"app_process64",
            Self::Launch { .. } | Self::Install { .. } | Self::Display { .. } => c"cmd",
        }
    }

    pub(super) fn arguments(&self) -> Result<Vec<CString>> {
        match self {
            Self::Read { value } => value.arguments(),
            Self::Vintf { value } => value.arguments(),
            Self::RuntimeAbi { value } => value.arguments(),
            Self::UserZeroPackageInventory { value } => value.arguments(),
            Self::Browser { value } => value.arguments(),
            Self::ContactsRead { value } => value.arguments(),
            Self::Launch { value } => value.arguments(),
            Self::Install { value } => value.arguments(),
            Self::Catalog { value } => value.arguments(),
            Self::Display { value } => value.arguments(),
        }
    }

    pub(super) fn domain(&self) -> OperationDomain {
        match self {
            Self::Read { .. } | Self::Vintf { .. } | Self::UserZeroPackageInventory { .. } => OperationDomain::Query,
            Self::RuntimeAbi { .. } => OperationDomain::LaunchRead,
            Self::Browser { value } => value.domain(),
            Self::ContactsRead { .. } => OperationDomain::ContactsRead,
            Self::Launch { value } => value.domain(),
            Self::Install { .. } => OperationDomain::Install,
            Self::Catalog { .. } => OperationDomain::CatalogRead,
            Self::Display { .. } => OperationDomain::DisplayControl,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn contacts_read_operation_keeps_classpath_and_domain_out_of_existing_read_and_browser_roles() {
        let operation = ApplicationOperation::ContactsRead {
            value: ContactsQuery::RawRows,
        };
        let environment = operation.environment(QueryProjection::LegacyRoot);
        assert_eq!(operation.domain(), OperationDomain::ContactsRead);
        assert_eq!(operation.binary(), c"app_process64");
        assert_eq!(operation.descriptor_count(), 17);
        assert!(environment.contains(&c"CLASSPATH=/.droidloom-query/content.jar"));
        assert_eq!(
            OperationDomain::ContactsRead.terminated(),
            b"u:r:droidloom_contacts_read:s0\0"
        );
        for other in [
            ApplicationOperation::Read {
                value: ApplicationRead::PackagePaths {
                    package: "com.android.contacts".into(),
                    user: 0,
                },
            },
            ApplicationOperation::Browser {
                value: BrowserCommand::Start {
                    user: 0,
                    url: "https://example.org/fixture".into(),
                },
            },
        ] {
            assert_eq!(other.descriptor_count(), 15);
            assert!(!other.needs_content_jar());
            assert!(
                !other
                    .environment(QueryProjection::LegacyRoot)
                    .iter()
                    .any(|x| x.to_bytes().starts_with(b"CLASSPATH="))
            );
            assert_ne!(other.domain(), OperationDomain::ContactsRead);
        }
        for message in [
            r#"{"operation":"ContactsRead","value":{"contacts_read":"RawRows"},"domain":"u:r:shell:s0"}"#,
            r#"{"operation":"ContactsRead","value":{"contacts_read":"RawRows","classpath":"/data/other.jar"}}"#,
            r#"{"operation":"ContactsRead","value":{"contacts_read":"Delete","raw_contact_id":"1"}}"#,
        ] {
            assert!(serde_json::from_str::<ApplicationOperation>(message).is_err());
        }
    }
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
    #[test]
    fn only_fixed_app_process_roles_receive_the_complete_original_art_environment() {
        let catalog = serde_json::from_value(serde_json::json!({
            "command":{"catalog":"List","user":0},
            "selected_jar_sha256":"a".repeat(64)
        }))
        .unwrap();
        for operation in [
            ApplicationOperation::ContactsRead {
                value: ContactsQuery::RawRows,
            },
            ApplicationOperation::Catalog { value: catalog },
        ] {
            for projection in [QueryProjection::LegacyRoot, QueryProjection::EarlyDev] {
                let environment = operation.environment(projection);
                for fixed in super::super::art_profile::ENVIRONMENT {
                    assert_eq!(environment.iter().filter(|e| **e == fixed).count(), 1);
                }
                assert_eq!(
                    environment
                        .iter()
                        .filter(|e| e.to_bytes().starts_with(b"CLASSPATH="))
                        .count(),
                    1
                );
            }
        }
        let native = ApplicationOperation::Read {
            value: ApplicationRead::PackagePaths {
                package: "com.android.contacts".into(),
                user: 0,
            },
        };
        assert!(
            !native
                .environment(QueryProjection::EarlyDev)
                .iter()
                .any(|e| e.to_bytes().starts_with(b"BOOTCLASSPATH=")
                    || e.to_bytes().starts_with(b"DEX2OATBOOTCLASSPATH="))
        );
    }
}
