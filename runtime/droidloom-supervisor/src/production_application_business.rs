//! One actual production business adapter: implicit public Firefox HTTPS open.
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
        Ok(command)
    }

    fn complete(&mut self, command: &BrowserCommand) -> Result<()> {
        self.stage = match (self.stage, command) {
            (Stage::BeforeResolve, BrowserCommand::Resolve { user, url })
                if *user == self.user && *url == self.url =>
            {
                Stage::Resolved
            }
            (Stage::Resolved, BrowserCommand::Start { user, url })
                if *user == self.user && *url == self.url =>
            {
                Stage::Started
            }
            _ => {
                return Err(reject(
                    "browser completion does not match the bound operation",
                ));
            }
        };
        Ok(())
    }
}

struct BrowserProbe<'borrow, 'owner> {
    ready: Workflow<'borrow, 'owner>,
    framework: WorkflowFramework,
    binding: Binding,
    receipts: Vec<ReadReceipt>,
    completed_browser_commands: usize,
    deadline: Instant,
}

fn complete_retirement(receipt: &ReadReceipt) -> bool {
    receipt.cgroup_removed
        && receipt.successful_retirement()
        && receipt.query_waitid_code == libc::CLD_EXITED
        && receipt.query_waitid_status == 0
}

impl AndroidProbe for BrowserProbe<'_, '_> {
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
            self.binding.complete(&command)?;
            self.completed_browser_commands += 1;
            Ok(result.output)
        })();
        result.map_err(|e| e.to_string())
    }
}

pub(super) fn open(
    mut ready: Workflow<'_, '_>,
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
    // output and unchanged post-start identity. No explicit-package fallback.
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
        };
        assert!(binding.browser(&strings(&start)).is_err());
        assert!(binding.complete(&start).is_err());
        assert_eq!(binding.stage, Stage::BeforeResolve);
        assert!(binding.browser(&strings(&resolve)).is_ok());
        binding.complete(&resolve).unwrap();
        assert!(binding.browser(&strings(&resolve)).is_err());
        assert!(binding.browser(&strings(&start)).is_ok());
        binding.complete(&start).unwrap();
        assert!(binding.browser(&strings(&start)).is_err());
        assert!(binding.complete(&resolve).is_err());
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
}
