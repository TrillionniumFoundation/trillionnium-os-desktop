//! Bounded, live package identity and implicit browser invocation.
//!
//! These observations do not qualify rendered content, media, or a whole app.
use std::collections::BTreeSet;

use serde::{Deserialize, Serialize};

/// Physical host/framework process generation, read by the lifecycle daemon.
#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct RuntimeEpoch {
    /// Host kernel boot UUID.
    pub boot_id: String,
    /// Daemon-owned namespace leader PID on the host.
    pub cell_host_pid: u32,
    /// Exact system_server PID on the host.
    pub framework_host_pid: u32,
    /// Kernel process start ticks, preventing transfer across generations.
    pub framework_start_ticks: u64,
}

/// The actual lifecycle implementation holding the observed Android runtime.
/// Production is deliberately absent until a production cell owner exists.
#[derive(Clone, Copy, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum RuntimeLifecycle {
    /// The existing daemon's owned DevelopmentCell implementation.
    Development,
}

/// Read-only readiness/identity observation, never a HostAdmission token.
#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct RuntimeObservation {
    /// Exact physical host/framework generation.
    pub epoch: RuntimeEpoch,
    /// Actual implementation which owns that cell; not a qualification label.
    pub lifecycle: RuntimeLifecycle,
}

/// A byte identity read from an APK path returned by Package Manager.
#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct InstalledApk {
    /// Normalized APK role: first PM source path is base.apk.
    pub name: String,
    /// Actual PM source path inside Android.
    pub path: String,
    /// Stable observed byte length.
    pub bytes: u64,
    /// SHA-256 of the actual installed APK bytes.
    pub sha256: String,
}

/// Fresh observed identity; its UID is never an input constant.
#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ApplicationInspection {
    /// Exact installed package name.
    pub package: String,
    /// Queried Android user.
    pub user: u32,
    /// Current UID read from Package Manager.
    pub uid: u32,
    /// Current numeric version read from Package Manager.
    pub version_code: u64,
    /// Live physical framework generation binding.
    pub epoch: RuntimeEpoch,
    /// Complete PM-returned base and split set.
    pub apks: Vec<InstalledApk>,
}

/// Existing daemon transport, after peer authorization and readiness admission.
pub trait AndroidProbe {
    /// Recheck the actual current framework identity.
    fn epoch(&mut self) -> Result<RuntimeEpoch, String>;
    /// Execute literal arguments, with a fixed deadline and bounded output.
    fn command(&mut self, args: &[String]) -> Result<String, String>;
}

fn argv(args: &[&str]) -> Vec<String> {
    args.iter().map(|s| (*s).to_owned()).collect()
}

fn package_valid(package: &str) -> bool {
    package.len() <= 255
        && package.contains('.')
        && package.split('.').all(|part| {
            !part.is_empty() && part.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_')
        })
}

/// Validate the only browser URL input accepted by the operation.
pub fn validate_https_url(url: &str) -> Result<(), String> {
    let Some(rest) = url.strip_prefix("https://") else {
        return Err("browser fixture URL must use HTTPS".into());
    };
    let authority = rest.split(['/', '?', '#']).next().unwrap_or("");
    if url.len() > 4096
        || !url.is_ascii()
        || url
            .bytes()
            .any(|b| b.is_ascii_control() || b.is_ascii_whitespace())
        || authority.is_empty()
        || authority.contains('@')
        || authority.contains('\\')
        || !authority
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b".-:[]".contains(&b))
    {
        return Err("browser fixture URL has an invalid or credential-bearing authority".into());
    }
    Ok(())
}

fn parse_package(output: &str, package: &str, user: u32) -> Result<(u32, u64), String> {
    let prefix = format!("package:{package}");
    let rows: Vec<_> = output
        .lines()
        .filter(|line| line.split_whitespace().next() == Some(prefix.as_str()))
        .collect();
    if rows.len() != 1 {
        return Err("exact installed package is absent or ambiguous".into());
    }
    let fields: Vec<_> = rows[0].split_whitespace().collect();
    let field = |prefix: &str| -> Result<&str, String> {
        let values: Vec<_> = fields
            .iter()
            .filter_map(|s| s.strip_prefix(prefix))
            .collect();
        if values.len() != 1 {
            return Err(format!("PM field {prefix} missing or repeated"));
        }
        Ok(values[0])
    };
    let uid: u32 = field("uid:")?.parse().map_err(|_| "invalid PM UID")?;
    let version: u64 = field("versionCode:")?
        .parse()
        .map_err(|_| "invalid PM version")?;
    if uid / 100_000 != user || version == 0 {
        return Err("PM UID is for another Android user or version is empty".into());
    }
    Ok((uid, version))
}

fn parse_paths(output: &str) -> Result<Vec<String>, String> {
    let mut paths = Vec::new();
    let mut seen = BTreeSet::new();
    for line in output.lines().filter(|s| !s.trim().is_empty()) {
        let path = line
            .strip_prefix("package:")
            .ok_or("unexpected PM path output")?;
        let allowed = [
            "/data/app/",
            "/system/",
            "/system_ext/",
            "/product/",
            "/vendor/",
            "/odm/",
            "/oem/",
            "/apex/",
        ];
        if path.len() > 512
            || !path.ends_with(".apk")
            || !allowed.iter().any(|prefix| path.starts_with(prefix))
            || path
                .split('/')
                .skip(1)
                .any(|part| part.is_empty() || part == "." || part == "..")
            || path
                .bytes()
                .any(|b| b.is_ascii_control() || b.is_ascii_whitespace())
            || !seen.insert(path.to_owned())
        {
            return Err("invalid or duplicated installed APK path".into());
        }
        paths.push(path.to_owned());
    }
    if paths.is_empty() || paths.len() > 64 {
        return Err("installed APK set is empty or exceeds bound".into());
    }
    Ok(paths)
}

fn stat_bytes(raw: &str) -> Result<u64, String> {
    let raw = raw.trim();
    let fields: Vec<_> = raw.splitn(4, ':').collect();
    if fields.len() != 4 || fields[0].parse::<u64>().is_err() || fields[1].parse::<u64>().is_err() {
        return Err("invalid APK metadata".into());
    }
    let bytes: u64 = fields[2].parse().map_err(|_| "invalid APK byte count")?;
    if bytes == 0 || bytes > 1024 * 1024 * 1024 {
        return Err("APK exceeds the bounded inspection size".into());
    }
    Ok(bytes)
}

fn fence(probe: &mut impl AndroidProbe, epoch: &RuntimeEpoch) -> Result<(), String> {
    if probe.epoch()? != *epoch {
        return Err("Android framework generation changed".into());
    }
    Ok(())
}

/// Inspect the exact installed package and all PM-returned APK source paths.
pub fn inspect(
    probe: &mut impl AndroidProbe,
    package: &str,
    user: u32,
) -> Result<ApplicationInspection, String> {
    if !package_valid(package) || user > 21_474 {
        return Err("invalid package or Android user".into());
    }
    let epoch = probe.epoch()?;
    let user_string = user.to_string();
    let package_args = argv(&[
        "/system/bin/cmd",
        "package",
        "list",
        "packages",
        "--user",
        &user_string,
        "-U",
        "--show-versioncode",
        package,
    ]);
    let path_args = argv(&[
        "/system/bin/cmd",
        "package",
        "path",
        "--user",
        &user_string,
        package,
    ]);
    let first_package = probe.command(&package_args)?;
    let (uid, version_code) = parse_package(&first_package, package, user)?;
    let paths = parse_paths(&probe.command(&path_args)?)?;
    let mut apks = Vec::new();
    let mut names = BTreeSet::new();
    let mut total = 0_u64;
    for (index, path) in paths.iter().enumerate() {
        fence(probe, &epoch)?;
        let stat_args = argv(&["/system/bin/toybox", "stat", "-c", "%d:%i:%s:%y:%z", path]);
        let before = probe.command(&stat_args)?;
        let bytes = stat_bytes(&before)?;
        total = total.checked_add(bytes).ok_or("APK size overflow")?;
        if total > 4 * 1024 * 1024 * 1024 {
            return Err("installed APK set exceeds 4 GiB".into());
        }
        let checksum = probe.command(&argv(&["/system/bin/toybox", "sha256sum", path]))?;
        let (sha256, named) = checksum
            .trim()
            .split_once("  ")
            .ok_or("invalid APK checksum output")?;
        if named != path
            || sha256.len() != 64
            || !sha256
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        {
            return Err("APK checksum identity differs".into());
        }
        if probe.command(&stat_args)?.trim() != before.trim() {
            return Err("APK changed during hash read".into());
        }
        let name = if index == 0 {
            "base.apk"
        } else {
            path.rsplit('/').next().ok_or("missing split name")?
        };
        if !names.insert(name.to_owned()) {
            return Err("normalized APK role is duplicated".into());
        }
        apks.push(InstalledApk {
            name: name.into(),
            path: path.clone(),
            bytes,
            sha256: sha256.into(),
        });
    }
    if parse_package(&probe.command(&package_args)?, package, user)? != (uid, version_code)
        || parse_paths(&probe.command(&path_args)?)? != paths
    {
        return Err("Package Manager identity changed during inspection".into());
    }
    fence(probe, &epoch)?;
    apks.sort_by(|a, b| a.name.cmp(&b.name));
    Ok(ApplicationInspection {
        package: package.into(),
        user,
        uid,
        version_code,
        epoch,
        apks,
    })
}

/// Open one reviewed public HTTPS fixture through actual implicit Android routing.
///
/// This never reports that content, media, persistence or permissions passed.
pub fn open_firefox(
    probe: &mut impl AndroidProbe,
    expected: &ApplicationInspection,
    url: &str,
) -> Result<(ApplicationInspection, String), String> {
    validate_https_url(url)?;
    if expected.package != "org.mozilla.firefox" {
        return Err("only the selected Firefox browser flow is implemented".into());
    }
    if inspect(probe, &expected.package, expected.user)? != *expected {
        return Err("installed browser or framework identity changed before invocation".into());
    }
    let user = expected.user.to_string();
    let resolve = probe.command(&argv(&[
        "/system/bin/cmd",
        "package",
        "resolve-activity",
        "--brief",
        "--user",
        &user,
        "-a",
        "android.intent.action.VIEW",
        "-c",
        "android.intent.category.BROWSABLE",
        "-d",
        url,
    ]))?;
    let components: Vec<_> = resolve.lines().filter(|line| line.contains('/')).collect();
    if components.len() != 1
        || components[0]
            .split_once('/')
            .is_none_or(|(owner, activity)| owner != expected.package || activity.is_empty())
    {
        return Err("implicit HTTPS resolver does not select the pinned Firefox package".into());
    }
    fence(probe, &expected.epoch)?;
    let output = probe.command(&argv(&[
        "/system/bin/cmd",
        "activity",
        "start-activity",
        "-W",
        "--user",
        &user,
        "-a",
        "android.intent.action.VIEW",
        "-c",
        "android.intent.category.BROWSABLE",
        "-d",
        url,
    ]))?;
    if !output.lines().any(|l| l.trim() == "Status: ok")
        || !output.lines().any(|l| {
            l.trim().strip_prefix("Activity: ").is_some_and(|c| {
                c.split_once('/')
                    .is_some_and(|(p, _)| p == expected.package)
            })
        })
    {
        return Err("Android did not confirm the actual Firefox activity start".into());
    }
    let after = inspect(probe, &expected.package, expected.user)?;
    if after != *expected {
        return Err("installed browser or framework identity changed after invocation".into());
    }
    Ok((after, output))
}

#[cfg(test)]
mod tests {
    #[test]
    fn runtime_observation_names_only_the_actual_lifecycle_without_production_authority() {
        let observed = super::RuntimeObservation {
            epoch: super::RuntimeEpoch {
                boot_id: "unit-test-boot".into(),
                cell_host_pid: 10,
                framework_host_pid: 20,
                framework_start_ticks: 30,
            },
            lifecycle: super::RuntimeLifecycle::Development,
        };
        let mut encoded = serde_json::to_value(&observed).unwrap();
        assert_eq!(encoded["lifecycle"], "development");
        assert_eq!(
            serde_json::from_value::<super::RuntimeObservation>(encoded.clone()).unwrap(),
            observed
        );
        encoded["lifecycle"] = serde_json::json!("production");
        assert!(serde_json::from_value::<super::RuntimeObservation>(encoded).is_err());
    }

    use super::*;
    use std::collections::VecDeque;
    #[derive(Clone)]
    struct Mock {
        epoch: RuntimeEpoch,
        output: VecDeque<String>,
        mutations: usize,
    }
    impl AndroidProbe for Mock {
        fn epoch(&mut self) -> Result<RuntimeEpoch, String> {
            Ok(self.epoch.clone())
        }
        fn command(&mut self, args: &[String]) -> Result<String, String> {
            if args.get(2).is_some_and(|s| s == "start-activity") {
                self.mutations += 1;
            }
            self.output.pop_front().ok_or("unexpected command".into())
        }
    }
    fn fixture(uid: u32) -> Mock {
        let package = format!("package:org.mozilla.firefox versionCode:2016193998 uid:{uid}");
        let path = "package:/data/app/browser/base.apk".to_owned();
        Mock {
            epoch: RuntimeEpoch {
                boot_id: "1".into(),
                cell_host_pid: 10,
                framework_host_pid: 20,
                framework_start_ticks: 30,
            },
            output: vec![
                package.clone(),
                path.clone(),
                "1:2:3:time:ctime".into(),
                format!("{}  /data/app/browser/base.apk", "a".repeat(64)),
                "1:2:3:time:ctime".into(),
                package,
                path,
            ]
            .into(),
            mutations: 0,
        }
    }
    #[test]
    fn uid_is_read_from_current_pm_and_not_fixed() {
        for uid in [10021, 10237] {
            assert_eq!(
                inspect(&mut fixture(uid), "org.mozilla.firefox", 0)
                    .unwrap()
                    .uid,
                uid
            );
        }
    }
    #[test]
    fn absent_and_wrong_user_packages_fail_before_apk_reads() {
        let mut m = fixture(10021);
        m.output[0] = "".into();
        assert!(inspect(&mut m, "org.mozilla.firefox", 0).is_err());
        assert!(inspect(&mut fixture(110021), "org.mozilla.firefox", 0).is_err());
    }
    #[test]
    fn private_traversal_and_duplicate_apk_paths_fail() {
        for path in [
            "package:/data/user/0/x/private.apk",
            "package:/data/app/../private.apk",
            "package:/system/a.apk\npackage:/system/a.apk",
        ] {
            assert!(parse_paths(path).is_err());
        }
    }
    #[test]
    fn package_update_and_byte_races_fail() {
        let mut m = fixture(10021);
        m.output[4] = "1:2:4:time:changed".into();
        assert!(inspect(&mut m, "org.mozilla.firefox", 0).is_err());
        let mut m = fixture(10021);
        m.output[5] = "package:org.mozilla.firefox versionCode:2016193999 uid:10021".into();
        assert!(inspect(&mut m, "org.mozilla.firefox", 0).is_err());
    }
    #[test]
    fn non_https_and_credential_urls_never_execute() {
        for url in [
            "http://example.com/",
            "https://u:p@example.com/",
            "https:///empty",
            "https://example.com/\n",
        ] {
            assert!(validate_https_url(url).is_err());
        }
    }
    #[test]
    fn other_default_browser_never_starts_firefox_explicitly() {
        let expected = inspect(&mut fixture(10021), "org.mozilla.firefox", 0).unwrap();
        let mut m = fixture(10021);
        m.output.push_back("org.example.browser/.Main".into());
        assert!(open_firefox(&mut m, &expected, "https://example.com/").is_err());
        assert_eq!(m.mutations, 0);
    }
    #[test]
    fn real_start_output_and_post_identity_are_required() {
        let expected = inspect(&mut fixture(10021), "org.mozilla.firefox", 0).unwrap();
        let mut m = fixture(10021);
        m.output.extend([
            "org.mozilla.firefox/.HomeActivity".into(),
            "Status: ok\nActivity: org.mozilla.firefox/.HomeActivity".into(),
        ]);
        m.output.extend(fixture(10021).output);
        assert!(open_firefox(&mut m, &expected, "https://example.com/").is_ok());
        assert_eq!(m.mutations, 1);
        let mut m = fixture(10021);
        m.output.extend([
            "org.mozilla.firefox/.HomeActivity".into(),
            "Status: timeout".into(),
        ]);
        assert!(open_firefox(&mut m, &expected, "https://example.com/").is_err());
    }
}
