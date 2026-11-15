//! One actual production business adapter: resolve and pin a Firefox HTTPS open.
//!
//! The same original Ready owner is borrowed for all package reads, resolver,
//! activity invocation and post-invocation reads. This does not qualify rendered
//! content, navigation, media, persistence, other applications, or all of Firefox.
use super::*;
use std::time::{Duration, Instant};

const WORKFLOW_LIMIT: Duration = Duration::from_secs(300);
const MAX_OPERATIONS: usize = 400;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Stage {
    BeforeResolve,
    Resolved,
    Started,
}

struct Binding {
    user: u32,
    url: String,
    paths: Vec<String>,
    stage: Stage,
    resolved_component: Option<String>,
}
impl Binding {
    fn new(expected: &ApplicationInspection, url: &str) -> Result<Self> {
        require(
            expected.package == "org.mozilla.firefox" && expected.user <= 21_474,
            "only the pinned Firefox HTTPS operation is implemented",
        )?;
        crate::control::application_probe::validate_https_url(url).map_err(external)?;
        require(
            !expected.apks.is_empty() && expected.apks.len() <= 64,
            "browser APK observation is empty or unbounded",
        )?;
        let paths = expected
            .apks
            .iter()
            .map(|a| a.path.clone())
            .collect::<Vec<_>>();
        require(
            paths.iter().all(|p| apk_valid(p)),
            "invalid browser APK observation path",
        )?;
        Ok(Self {
            user: expected.user,
            url: url.into(),
            paths,
            stage: Stage::BeforeResolve,
            resolved_component: None,
        })
    }

    fn read(&self, value: &ApplicationRead) -> Result<()> {
        require(
            match value {
                ApplicationRead::PackageIdentity { package, user }
                | ApplicationRead::PackagePaths { package, user } => {
                    package == "org.mozilla.firefox" && *user == self.user
                }
                ApplicationRead::ApkStat { path } | ApplicationRead::ApkSha256 { path } => {
                    self.paths.contains(path)
                }
            },
            "browser read is outside its bound package/user/APK set",
        )
    }

    fn browser(&self, args: &[String]) -> Result<BrowserCommand> {
        let command = BrowserCommand::from_command(args, self.user, &self.url)?;
        require(
            matches!(
                (&command, self.stage),
                (BrowserCommand::Resolve { .. }, Stage::BeforeResolve)
                    | (BrowserCommand::Start { .. }, Stage::Resolved)
            ),
            "browser command is repeated or out of order",
        )?;
        if let BrowserCommand::Start { component, .. } = &command {
            require(
                self.resolved_component.as_deref() == Some(component.as_str()),
                "browser start component differs from the actual completed resolver",
            )?;
        }
        Ok(command)
    }

    fn complete(&mut self, command: &BrowserCommand, output: &str) -> Result<()> {
        match (self.stage, command) {
            (Stage::BeforeResolve, BrowserCommand::Resolve { user, url })
                if *user == self.user && *url == self.url =>
            {
                // Parse before advancing the stage. This caller has already
                // checked the actual successful exit and complete retirement.
                let component = operation::resolved_firefox_component(output)?;
                self.resolved_component = Some(component);
                self.stage = Stage::Resolved;
            }
            (
                Stage::Resolved,
                BrowserCommand::Start {
                    user,
                    url,
                    component,
                },
            ) if *user == self.user
                && *url == self.url
                && self.resolved_component.as_deref() == Some(component.as_str()) =>
            {
                self.stage = Stage::Started;
            }
            _ => {
                return Err(reject(
                    "browser completion does not match the bound operation",
                ));
            }
        }
        Ok(())
    }
}

struct BrowserProbe<'a> {
    ready: ReadyTreeWitness<'a>,
    framework: FrameworkObservation,
    binding: Binding,
    receipts: Vec<ReadReceipt>,
    completed_browser_commands: usize,
    deadline: Instant,
}

fn complete_retirement(receipt: &ReadReceipt) -> bool {
    receipt.cgroup_removed
        && receipt.worker_waitid_code == libc::CLD_EXITED
        && receipt.worker_waitid_status == 0
        && receipt.query_waitid_code == libc::CLD_EXITED
        && receipt.query_waitid_status == 0
}

impl AndroidProbe for BrowserProbe<'_> {
    fn epoch(&mut self) -> std::result::Result<RuntimeEpoch, String> {
        require(Instant::now() < self.deadline, "browser workflow deadline")
            .map_err(|e| e.to_string())?;
        let epoch = self
            .ready
            .application_epoch(&self.framework)
            .map_err(|e| e.to_string())?;
        require(Instant::now() < self.deadline, "browser workflow deadline")
            .map_err(|e| e.to_string())?;
        Ok(epoch)
    }

    fn command(&mut self, args: &[String]) -> std::result::Result<String, String> {
        let result = (|| -> Result<String> {
            require(
                Instant::now() < self.deadline && self.receipts.len() < MAX_OPERATIONS,
                "browser workflow deadline or command bound",
            )?;
            if let Ok(read) = ApplicationRead::from_command(args) {
                self.binding.read(&read)?;
                let result = self
                    .ready
                    .run_application_read_before(&read, self.deadline)
                    .map_err(external)?;
                require(
                    complete_retirement(&result.receipt),
                    "browser inspection child retirement incomplete",
                )?;
                self.receipts.push(result.receipt);
                require(Instant::now() < self.deadline, "browser workflow deadline")?;
                return Ok(result.output);
            }
            let command = self.binding.browser(args)?;
            let result = self
                .ready
                .run_application_browser(&command, self.deadline)
                .map_err(external)?;
            require(
                complete_retirement(&result.receipt),
                "browser operation child retirement incomplete",
            )?;
            self.receipts.push(result.receipt);
            require(Instant::now() < self.deadline, "browser workflow deadline")?;
            self.binding.complete(&command, &result.output)?;
            self.completed_browser_commands += 1;
            Ok(result.output)
        })();
        result.map_err(|e| e.to_string())
    }
}

pub(super) fn open(
    mut ready: ReadyTreeWitness<'_>,
    expected: &ApplicationInspection,
    url: &str,
) -> Result<(ApplicationInspection, String)> {
    let deadline = Instant::now() + WORKFLOW_LIMIT;
    let binding = Binding::new(expected, url)?;
    let framework = ready.observe_application_framework().map_err(external)?;
    require(Instant::now() < deadline, "browser workflow deadline")?;
    let mut probe = BrowserProbe {
        ready,
        framework,
        binding,
        receipts: Vec::new(),
        completed_browser_commands: 0,
        deadline,
    };
    // This existing workflow checks complete before/after APK bytes+version+UID
    // and physical epoch, the actual default resolver, actual Status/Activity
    // output and unchanged post-start identity. The start is explicitly bound
    // to that completed resolver, without an implicit re-resolution window.
    let result = crate::control::application_probe::open_firefox(&mut probe, expected, url)
        .map_err(external)?;
    require(
        probe.binding.stage == Stage::Started
            && probe.completed_browser_commands == 2
            && !probe.receipts.is_empty()
            && probe.receipts.iter().all(complete_retirement),
        "browser operation did not complete its actual owned sequence",
    )?;
    require(
        probe.epoch().map_err(external)? == expected.epoch,
        "original browser framework changed after operation",
    )?;
    require(Instant::now() < deadline, "browser workflow deadline")?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::control::application_probe::InstalledApk;

    fn expected() -> ApplicationInspection {
        ApplicationInspection {
            package: "org.mozilla.firefox".into(),
            user: 10,
            uid: 1_010_123,
            version_code: 1,
            epoch: RuntimeEpoch {
                boot_id: "fixture-not-runtime-proof".into(),
                cell_host_pid: 2,
                framework_host_pid: 3,
                framework_start_ticks: 4,
            },
            apks: vec![InstalledApk {
                name: "base.apk".into(),
                path: "/data/app/firefox/base.apk".into(),
                bytes: 64,
                sha256: "a".repeat(64),
            }],
        }
    }

    fn strings(command: &BrowserCommand) -> Vec<String> {
        command
            .arguments()
            .unwrap()
            .into_iter()
            .map(|s| s.into_string().unwrap())
            .collect()
    }

    #[test]
    fn production_browser_binding_rejects_launch_before_resolve_and_replay() {
        let url = "https://example.org/fixture";
        let mut binding = Binding::new(&expected(), url).unwrap();
        let resolve = BrowserCommand::Resolve {
            user: 10,
            url: url.into(),
        };
        let start = BrowserCommand::Start {
            user: 10,
            url: url.into(),
            component: "org.mozilla.firefox/.LauncherAlias".into(),
        };
        assert!(binding.browser(&strings(&start)).is_err());
        assert!(binding.complete(&start, "Status: ok").is_err());
        assert_eq!(binding.stage, Stage::BeforeResolve);
        assert!(binding.browser(&strings(&resolve)).is_ok());
        binding
            .complete(&resolve, "org.mozilla.firefox/.LauncherAlias\n")
            .unwrap();
        assert!(binding.browser(&strings(&resolve)).is_err());
        assert!(binding.browser(&strings(&start)).is_ok());
        binding.complete(&start, "Status: ok").unwrap();
        assert!(binding.browser(&strings(&start)).is_err());
        assert!(
            binding
                .complete(&resolve, "org.mozilla.firefox/.LauncherAlias\n")
                .is_err()
        );
        assert_eq!(binding.stage, Stage::Started);
    }

    #[test]
    fn production_browser_binding_keeps_expected_package_user_and_complete_apk_set() {
        let binding = Binding::new(&expected(), "https://example.org/fixture").unwrap();
        assert!(
            binding
                .read(&ApplicationRead::PackagePaths {
                    package: "org.mozilla.firefox".into(),
                    user: 10
                })
                .is_ok()
        );
        assert!(
            binding
                .read(&ApplicationRead::PackagePaths {
                    package: "org.mozilla.firefox".into(),
                    user: 0
                })
                .is_err()
        );
        assert!(
            binding
                .read(&ApplicationRead::PackageIdentity {
                    package: "org.other.app".into(),
                    user: 10
                })
                .is_err()
        );
        assert!(
            binding
                .read(&ApplicationRead::ApkSha256 {
                    path: "/data/app/firefox/base.apk".into()
                })
                .is_ok()
        );
        assert!(
            binding
                .read(&ApplicationRead::ApkSha256 {
                    path: "/data/app/firefox/new-split.apk".into()
                })
                .is_err()
        );
        let mut other = expected();
        other.package = "org.other.app".into();
        assert!(Binding::new(&other, "https://example.org/fixture").is_err());
    }

    #[test]
    fn production_browser_binding_pins_actual_resolver_component_and_rejects_substitution() {
        let url = "https://example.org/fixture";
        let mut binding = Binding::new(&expected(), url).unwrap();
        let resolve = BrowserCommand::Resolve {
            user: 10,
            url: url.into(),
        };
        binding
            .complete(&resolve, "priority=0\norg.mozilla.firefox/.LauncherAlias\n")
            .unwrap();
        let different = BrowserCommand::Start {
            user: 10,
            url: url.into(),
            component: "org.mozilla.firefox/.DifferentAlias".into(),
        };
        assert!(binding.browser(&strings(&different)).is_err());
        assert!(binding.complete(&different, "Status: ok").is_err());
        assert_eq!(binding.stage, Stage::Resolved);
        assert_eq!(
            binding.resolved_component.as_deref(),
            Some("org.mozilla.firefox/.LauncherAlias")
        );
        let start = BrowserCommand::Start {
            user: 10,
            url: url.into(),
            component: "org.mozilla.firefox/.LauncherAlias".into(),
        };
        assert!(binding.browser(&strings(&start)).is_ok());
        // Android may report a concrete same-package activity for an alias.
        // The existing probe checks that result; this state binds sent -n data.
        binding
            .complete(
                &start,
                "Status: ok\nActivity: org.mozilla.firefox/org.mozilla.fenix.HomeActivity\n",
            )
            .unwrap();
        assert_eq!(binding.stage, Stage::Started);
        assert!(binding.browser(&strings(&start)).is_err());
    }

    #[test]
    fn production_browser_binding_invalid_resolver_does_not_advance_or_store_component() {
        let url = "https://example.org/fixture";
        let resolve = BrowserCommand::Resolve {
            user: 10,
            url: url.into(),
        };
        for output in [
            "No activity found",
            "org.other.browser/.Main",
            "org.mozilla.firefox/.A\norg.mozilla.firefox/.B",
            "org.mozilla.firefox/.A\0",
        ] {
            let mut binding = Binding::new(&expected(), url).unwrap();
            assert!(binding.complete(&resolve, output).is_err());
            assert_eq!(binding.stage, Stage::BeforeResolve);
            assert!(binding.resolved_component.is_none());
        }
    }

    #[test]
    fn production_browser_probe_uses_actual_binding_and_parser_for_the_published_explicit_plan() {
        // Ordinary grammar/workflow fixture only. It cannot construct Ready,
        // ExecutionAdmission or a retirement receipt, and executes no process.
        struct Fixture {
            expected: ApplicationInspection,
            binding: Binding,
            starts: Vec<Vec<String>>,
        }
        impl AndroidProbe for Fixture {
            fn epoch(&mut self) -> std::result::Result<RuntimeEpoch, String> {
                Ok(self.expected.epoch.clone())
            }
            fn command(&mut self, args: &[String]) -> std::result::Result<String, String> {
                if let Ok(read) = ApplicationRead::from_command(args) {
                    self.binding.read(&read).map_err(|e| e.to_string())?;
                    return Ok(match read {
                        ApplicationRead::PackageIdentity { .. } => {
                            "package:org.mozilla.firefox versionCode:1 uid:1010123".into()
                        }
                        ApplicationRead::PackagePaths { .. } => {
                            "package:/data/app/firefox/base.apk".into()
                        }
                        ApplicationRead::ApkStat { .. } => "1:2:64:time:ctime".into(),
                        ApplicationRead::ApkSha256 { .. } => {
                            format!("{}  /data/app/firefox/base.apk", "a".repeat(64))
                        }
                    });
                }
                let command = self.binding.browser(args).map_err(|e| e.to_string())?;
                let output = match &command {
                    BrowserCommand::Resolve { .. } => {
                        "priority=0\norg.mozilla.firefox/.LauncherAlias\n".to_owned()
                    }
                    BrowserCommand::Start { .. } => {
                        self.starts.push(args.to_vec());
                        "Status: ok\nActivity: org.mozilla.firefox/org.mozilla.fenix.HomeActivity\n"
                            .into()
                    }
                };
                self.binding
                    .complete(&command, &output)
                    .map_err(|e| e.to_string())?;
                Ok(output)
            }
        }
        let expected = expected();
        let url = "https://example.org/fixture";
        let mut probe = Fixture {
            expected: expected.clone(),
            binding: Binding::new(&expected, url).unwrap(),
            starts: Vec::new(),
        };
        let (after, _) =
            crate::control::application_probe::open_firefox(&mut probe, &expected, url).unwrap();
        assert_eq!(after, expected);
        assert_eq!(probe.binding.stage, Stage::Started);
        assert_eq!(probe.starts.len(), 1);
        assert_eq!(
            &probe.starts[0][6..8],
            ["-n", "org.mozilla.firefox/.LauncherAlias"]
        );
    }
}
