//! Narrow Android Java environment, read from the held framework process.
//!
//! Instrumentation starts app_process and needs the current boot classpath.
//! Host environment, loader overrides and caller-supplied classpaths are never
//! inherited. This is an execution prerequisite, not Android admission.

use std::collections::BTreeMap;
use std::io;
use std::process::Command;

pub(super) const ENVIRONMENT_LIMIT: u64 = 64 * 1024;
const VALUE_LIMIT: usize = 32 * 1024;
const REQUIRED: [&str; 6] = [
    "PATH",
    "BOOTCLASSPATH",
    "DEX2OATBOOTCLASSPATH",
    "ANDROID_ROOT",
    "ANDROID_DATA",
    "ANDROID_ART_ROOT",
];
const OPTIONAL: [&str; 5] = [
    "ANDROID_ASSETS",
    "ANDROID_I18N_ROOT",
    "ANDROID_TZDATA_ROOT",
    "SYSTEMSERVERCLASSPATH",
    "STANDALONE_SYSTEMSERVER_JARS",
];

fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

/// Only operations which start Android Java need this extra environment.
pub(super) fn needs_runtime_environment(args: &[String]) -> bool {
    matches!(
        args.first().map(String::as_str),
        Some("/system/bin/app_process" | "/system/bin/app_process32" | "/system/bin/app_process64")
    ) || (args.first().map(String::as_str) == Some("/system/bin/am")
        && args.get(1).map(String::as_str) == Some("instrument"))
}

fn android_path(value: &str) -> bool {
    value.len() <= 1024
        && value.starts_with('/')
        && !value.ends_with('/')
        && !value.contains("//")
        && value.split('/').all(|part| !matches!(part, "." | ".."))
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"/._-@+=".contains(&byte))
}

fn path_list(value: &str, classpath: bool, allow_empty: bool) -> bool {
    if value.is_empty() {
        return allow_empty;
    }
    let mut paths = std::collections::BTreeSet::new();
    for path in value.split(':') {
        if !android_path(path) || !paths.insert(path) || paths.len() > 256 {
            return false;
        }
        let rooted = [
            "/system/",
            "/system_ext/",
            "/product/",
            "/vendor/",
            "/odm/",
            "/apex/",
        ]
        .iter()
        .any(|prefix| path.starts_with(prefix));
        if !rooted
            || (classpath && !path.ends_with(".jar"))
            || (!classpath && !path.ends_with("/bin") && !path.ends_with("/xbin"))
        {
            return false;
        }
    }
    true
}

fn value_valid(name: &str, value: &str) -> bool {
    if value.len() > VALUE_LIMIT {
        return false;
    }
    match name {
        "PATH" => path_list(value, false, false),
        "BOOTCLASSPATH" | "DEX2OATBOOTCLASSPATH" | "SYSTEMSERVERCLASSPATH" => {
            path_list(value, true, false)
        }
        "STANDALONE_SYSTEMSERVER_JARS" => path_list(value, true, true),
        "ANDROID_ROOT" => value == "/system",
        "ANDROID_DATA" => value == "/data",
        "ANDROID_ART_ROOT" => value == "/apex/com.android.art",
        "ANDROID_I18N_ROOT" => value == "/apex/com.android.i18n",
        "ANDROID_TZDATA_ROOT" => value == "/apex/com.android.tzdata",
        "ANDROID_ASSETS" => value == "/system/app",
        _ => false,
    }
}

// Deliberately no Debug/Serialize: do not leak arbitrary process environment.
#[derive(Eq, PartialEq)]
pub(super) struct RuntimeEnvironment(BTreeMap<String, String>);

impl RuntimeEnvironment {
    pub(super) fn parse(raw: &[u8]) -> io::Result<Self> {
        if raw.is_empty() || raw.len() as u64 > ENVIRONMENT_LIMIT || raw.last() != Some(&0) {
            return Err(invalid(
                "framework environment is absent, unbounded or incomplete",
            ));
        }
        let mut selected = BTreeMap::new();
        for record in raw[..raw.len() - 1].split(|byte| *byte == 0) {
            let separator = record
                .iter()
                .position(|byte| *byte == b'=')
                .ok_or_else(|| invalid("framework environment has a malformed record"))?;
            let name = std::str::from_utf8(&record[..separator])
                .map_err(|_| invalid("framework environment has an invalid name"))?;
            if name.is_empty()
                || !name
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
            {
                return Err(invalid("framework environment has an invalid name"));
            }
            if !REQUIRED.contains(&name) && !OPTIONAL.contains(&name) {
                continue;
            }
            let value = std::str::from_utf8(&record[separator + 1..])
                .map_err(|_| invalid("selected framework environment is not UTF-8"))?;
            if !value_valid(name, value) {
                return Err(invalid(
                    "selected framework environment has an invalid Android path",
                ));
            }
            if selected.insert(name.to_owned(), value.to_owned()).is_some() {
                return Err(invalid(
                    "selected framework environment has a duplicate name",
                ));
            }
        }
        if REQUIRED.iter().any(|name| !selected.contains_key(*name)) {
            return Err(invalid("framework Java environment is incomplete"));
        }
        Ok(Self(selected))
    }

    pub(super) fn apply(&self, command: &mut Command) {
        command.envs(&self.0);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    pub(super) fn fixture() -> Vec<u8> {
        b"PATH=/product/bin:/apex/com.android.art/bin:/system/bin:/system/xbin:/vendor/bin\0BOOTCLASSPATH=/apex/com.android.art/javalib/core-oj.jar:/system/framework/framework.jar\0DEX2OATBOOTCLASSPATH=/apex/com.android.art/javalib/core-oj.jar:/system/framework/framework.jar\0ANDROID_ROOT=/system\0ANDROID_DATA=/data\0ANDROID_ART_ROOT=/apex/com.android.art\0".to_vec()
    }

    #[test]
    fn android_java_operations_are_selected_without_changing_pm_or_browser_start() {
        let args = |values: &[&str]| values.iter().map(|s| (*s).to_owned()).collect::<Vec<_>>();
        assert!(needs_runtime_environment(&args(&[
            "/system/bin/am",
            "instrument",
            "-w"
        ])));
        assert!(needs_runtime_environment(&args(&[
            "/system/bin/app_process",
            "/system/bin"
        ])));
        for values in [
            vec!["/system/bin/cmd", "package"],
            vec!["/system/bin/am", "start"],
            vec![],
            vec!["am", "instrument"],
        ] {
            assert!(!needs_runtime_environment(&args(&values)));
        }
    }

    #[test]
    fn only_current_android_runtime_keys_reach_the_child() {
        let mut raw = fixture();
        raw.extend_from_slice(b"LD_PRELOAD=/data/untrusted.so\0CLASSPATH=/data/wrong.jar\0JAVA_TOOL_OPTIONS=wrong\0PRIVATE_TOKEN=do-not-forward\0");
        let environment = RuntimeEnvironment::parse(&raw).unwrap();
        let mut command = Command::new("/not-executed");
        command.env_clear();
        environment.apply(&mut command);
        let observed: BTreeMap<_, _> = command
            .get_envs()
            .map(|(k, v)| (k.to_str().unwrap(), v.unwrap().to_str().unwrap()))
            .collect();
        assert_eq!(observed.len(), REQUIRED.len());
        assert_eq!(
            observed["BOOTCLASSPATH"],
            "/apex/com.android.art/javalib/core-oj.jar:/system/framework/framework.jar"
        );
        assert!(!observed.contains_key("LD_PRELOAD"));
        assert!(!observed.contains_key("CLASSPATH"));
        assert!(!observed.contains_key("PRIVATE_TOKEN"));
    }

    #[test]
    fn missing_duplicate_truncated_and_unbounded_environments_fail() {
        let full = fixture();
        assert!(RuntimeEnvironment::parse(&[]).is_err());
        assert!(RuntimeEnvironment::parse(&full[..full.len() - 1]).is_err());
        let missing: Vec<_> = full
            .split_inclusive(|v| *v == 0)
            .filter(|v| !v.starts_with(b"BOOTCLASSPATH="))
            .flatten()
            .copied()
            .collect();
        assert!(RuntimeEnvironment::parse(&missing).is_err());
        let mut duplicate = full.clone();
        duplicate.extend_from_slice(b"ANDROID_DATA=/data\0");
        assert!(RuntimeEnvironment::parse(&duplicate).is_err());
        assert!(RuntimeEnvironment::parse(&vec![0; ENVIRONMENT_LIMIT as usize + 1]).is_err());
    }

    #[test]
    fn malformed_records_and_selected_non_utf8_values_fail() {
        for extra in [
            b"broken\0".as_slice(),
            b"=empty\0",
            b"BAD-NAME=x\0",
            b"ANDROID_ASSETS=\xff\0",
            b"\0",
        ] {
            let mut raw = fixture();
            raw.extend_from_slice(extra);
            assert!(RuntimeEnvironment::parse(&raw).is_err());
        }
        let mut ignored = fixture();
        ignored.extend_from_slice(b"IGNORED_BINARY=\xff\0");
        assert!(RuntimeEnvironment::parse(&ignored).is_ok());
    }

    #[test]
    fn classpaths_cannot_escape_android_or_admit_ambiguous_segments() {
        for value in [
            "",
            "relative.jar",
            "/data/evil.jar",
            "/system/framework/../evil.jar",
            "/system//framework/a.jar",
            "/system/framework/a.jar:",
            "/system/framework/a.jar:/system/framework/a.jar",
            "/system/framework/a.jar;evil",
            "/system/framework/a.apk",
            "/system/framework/a.jar\n",
        ] {
            assert!(!value_valid("BOOTCLASSPATH", value), "{value:?}");
        }
        assert!(!value_valid("PATH", "/data/local/bin"));
        assert!(!value_valid("PATH", "/system/framework"));
        assert!(!value_valid("ANDROID_DATA", "/data/elsewhere"));
        assert!(!value_valid(
            "ANDROID_ART_ROOT",
            "/apex/com.android.art/../other"
        ));
        assert!(value_valid("PATH", "/system_ext/bin:/vendor/xbin"));
    }

    #[test]
    fn optional_runtime_roots_and_an_empty_standalone_list_are_explicit() {
        let mut raw = fixture();
        raw.extend_from_slice(b"ANDROID_I18N_ROOT=/apex/com.android.i18n\0ANDROID_TZDATA_ROOT=/apex/com.android.tzdata\0ANDROID_ASSETS=/system/app\0SYSTEMSERVERCLASSPATH=/system/framework/services.jar\0STANDALONE_SYSTEMSERVER_JARS=\0");
        let parsed = RuntimeEnvironment::parse(&raw).unwrap();
        assert_eq!(parsed.0.len(), REQUIRED.len() + OPTIONAL.len());
        assert_eq!(parsed.0["STANDALONE_SYSTEMSERVER_JARS"], "");
    }

    #[test]
    fn selected_environment_change_cannot_match_the_frozen_invocation() {
        let before = RuntimeEnvironment::parse(&fixture()).unwrap();
        let different = String::from_utf8(fixture())
            .unwrap()
            .replace("framework.jar", "framework-new.jar");
        let after = RuntimeEnvironment::parse(different.as_bytes()).unwrap();
        assert!(before != after);
        let mut same = fixture();
        same.extend_from_slice(b"IGNORED_SESSION=changed\0");
        assert!(before == RuntimeEnvironment::parse(&same).unwrap());
    }
}
