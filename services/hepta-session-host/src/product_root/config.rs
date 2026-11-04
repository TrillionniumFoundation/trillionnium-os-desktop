//! Explicit administrator inputs. No principal, PID, signature, grant or head is input.
use super::Result;
use super::fs;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Inputs {
    pub schema: String,
    #[serde(
        default,
        skip_serializing_if = "Option::is_none",
        deserialize_with = "profile_if_present"
    )]
    pub profile: Option<DesktopProfile>,
    pub prefix: PathBuf,
    pub uid: u32,
    pub gid: u32,
    pub programs: Programs,
    pub sources: Sources,
    pub makepad_resources: PathBuf,
    pub environment: BTreeMap<String, String>,
    pub locale: String,
    pub lifetime_ms: u64,
    pub grant_lifetime_ms: u64,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub(super) enum DesktopProfile {
    NotesCalculatorV1,
}

// A missing legacy field is accepted through serde's default. An explicitly
// supplied value must be the new named enum; null never selects the old profile.
fn profile_if_present<'de, D>(
    deserializer: D,
) -> std::result::Result<Option<DesktopProfile>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    DesktopProfile::deserialize(deserializer).map(Some)
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Programs {
    pub agentd: PathBuf,
    pub app_server: PathBuf,
    pub authority_host: PathBuf,
    pub session: PathBuf,
    pub shell: PathBuf,
    pub app_window: PathBuf,
    pub python: PathBuf,
    pub human_provider: PathBuf,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Sources {
    pub runtime_body: PathBuf,
    pub preferences: PathBuf,
    pub prompt_registry: PathBuf,
    pub sdk: PathBuf,
    pub source_freeze: PathBuf,
}

impl Inputs {
    pub(super) fn is_desktop(&self) -> bool {
        self.profile == Some(DesktopProfile::NotesCalculatorV1)
    }

    pub(super) fn objective_profile_name(&self) -> &'static str {
        if self.is_desktop() {
            "desktop-thread-profile.json"
        } else {
            "notes-thread-profile.json"
        }
    }

    pub(super) fn require_entry(&self, desktop: bool) -> Result<()> {
        if self.is_desktop() != desktop {
            return Err(
                "Root entry must match the explicit Notes or notes_calculator_v1 input".into(),
            );
        }
        Ok(())
    }

    pub(super) fn read(path: &Path) -> Result<Self> {
        let value: Self = fs::read_root_json(path)?;
        value.validate(/*fresh*/ true)?;
        Ok(value)
    }

    pub(super) fn read_recovery(path: &Path) -> Result<Self> {
        let value: Self = fs::read_root_json(path)?;
        value.validate(/*fresh*/ false)?;
        Ok(value)
    }

    fn validate(&self, fresh: bool) -> Result<()> {
        validate_selection(&self.schema, self.profile, fresh)?;
        if self.prefix.parent() != Some(Path::new("/var/lib/trill"))
            || !self
                .prefix
                .file_name()
                .and_then(|s| s.to_str())
                .is_some_and(|s| {
                    (1..=12).contains(&s.len())
                        && s.bytes()
                            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
                        && s.as_bytes()[0].is_ascii_alphanumeric()
                })
            || matches!(self.uid, 0 | u32::MAX)
            || matches!(self.gid, 0 | u32::MAX)
            || !(120_000..=300_000).contains(&self.lifetime_ms)
            || !(1..=30_000).contains(&self.grant_lifetime_ms)
            || self.grant_lifetime_ms > self.lifetime_ms
            || !matches!(self.locale.as_str(), "zh-CN" | "en-US")
        {
            return Err("invalid explicit fresh Root inputs".into());
        }
        let p = &self.programs;
        let notes_recovery = p.app_window.with_file_name("trill-notes-recovery");
        for program in [
            &p.agentd,
            &p.app_server,
            &p.authority_host,
            &p.session,
            &p.shell,
            &p.app_window,
            &notes_recovery,
            &p.python,
        ] {
            fs::root_file(program, true)?;
        }
        // Session resolves this exact sibling, never a PATH replacement.
        if p.session.with_file_name("trill-app-window") != p.app_window {
            return Err("Session requires the installed sibling trill-app-window".into());
        }
        fs::root_file(&p.human_provider, false)?;
        for input in [
            &self.sources.runtime_body,
            &self.sources.preferences,
            &self.sources.prompt_registry,
            &self.sources.sdk,
            &self.sources.source_freeze,
        ] {
            fs::root_file(input, false)?;
        }
        fs::root_directory(&self.makepad_resources)?;
        let allowed = [
            "DISPLAY",
            "WAYLAND_DISPLAY",
            "XDG_RUNTIME_DIR",
            "DBUS_SESSION_BUS_ADDRESS",
            "XAUTHORITY",
            "XMODIFIERS",
            "LANG",
            "LC_ALL",
        ];
        if self
            .environment
            .iter()
            .any(|(k, v)| !allowed.contains(&k.as_str()) || v.len() > 4096 || v.contains('\0'))
        {
            return Err("only bounded original display/session inputs are accepted".into());
        }
        if self
            .environment
            .get("XMODIFIERS")
            .is_some_and(|value| value != "@im=ibus")
        {
            return Err("the original IBus session is the only native XIM selector".into());
        }
        let runtime = self
            .environment
            .get("XDG_RUNTIME_DIR")
            .ok_or("the actual original XDG_RUNTIME_DIR is required")?;
        fs::user_directory(Path::new(runtime), self.uid)?;
        let session = Path::new(runtime).join("trillionnium-ui/session.sock");
        if fresh && std::fs::symlink_metadata(&session).is_ok() {
            return Err("an existing Session socket is never replaced".into());
        }
        if !self.environment.contains_key("WAYLAND_DISPLAY")
            && !self.environment.contains_key("DISPLAY")
        {
            return Err("an actual display selection is required".into());
        }
        Ok(())
    }
}

fn validate_selection(schema: &str, profile: Option<DesktopProfile>, fresh: bool) -> Result<()> {
    match (schema, profile, fresh) {
        ("trill.original-desktop-root.initialize.v1", None, _) => Ok(()),
        (
            "trill.original-desktop-root.initialize.v2",
            Some(DesktopProfile::NotesCalculatorV1),
            true,
        ) => Ok(()),
        (
            "trill.original-desktop-root.initialize.v2",
            Some(DesktopProfile::NotesCalculatorV1),
            false,
        ) => Err("joint Desktop recovery requires its own reviewed profile; old Notes recovery cannot migrate it".into()),
        _ => Err("Root schema and explicit target profile do not match".into()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn real_input_json_distinguishes_absence_from_null_and_explicit_joint_selection() {
        // Parsing only: none of these fixture paths is opened or provisioned.
        let mut value = serde_json::json!({
            "schema": "trill.original-desktop-root.initialize.v1",
            "prefix": "/var/lib/trill/fixture",
            "uid": 1000,
            "gid": 1000,
            "programs": {
                "agentd": "/fixture/agentd",
                "app_server": "/fixture/app-server",
                "authority_host": "/fixture/authority-host",
                "session": "/fixture/trill-session",
                "shell": "/fixture/trill-shell",
                "app_window": "/fixture/trill-app-window",
                "python": "/fixture/python",
                "human_provider": "/fixture/human-provider.py",
            },
            "sources": {
                "runtime_body": "/fixture/agentd",
                "preferences": "/fixture/preferences.json",
                "prompt_registry": "/fixture/prompts.json",
                "sdk": "/fixture/sdk.json",
                "source_freeze": "/fixture/source-freeze.json",
            },
            "makepad_resources": "/fixture/resources",
            "environment": {},
            "locale": "en-US",
            "lifetime_ms": 120000,
            "grant_lifetime_ms": 30000,
        });
        let legacy: Inputs = serde_json::from_value(value.clone()).unwrap();
        assert!(!legacy.is_desktop());
        assert!(legacy.require_entry(false).is_ok());
        assert!(legacy.require_entry(true).is_err());
        assert!(
            serde_json::to_value(legacy)
                .unwrap()
                .get("profile")
                .is_none()
        );

        value["profile"] = serde_json::Value::Null;
        assert!(serde_json::from_value::<Inputs>(value.clone()).is_err());
        value["schema"] = "trill.original-desktop-root.initialize.v2".into();
        value["profile"] = "notes_calculator_v1".into();
        let joint: Inputs = serde_json::from_value(value.clone()).unwrap();
        assert!(joint.is_desktop());
        assert!(joint.require_entry(true).is_ok());
        assert!(joint.require_entry(false).is_err());
        value["profile"] = "unknown".into();
        assert!(serde_json::from_value::<Inputs>(value).is_err());
    }

    #[test]
    fn joint_profile_requires_new_schema_and_fresh_entry() {
        let legacy = "trill.original-desktop-root.initialize.v1";
        let joint = "trill.original-desktop-root.initialize.v2";
        let both = Some(DesktopProfile::NotesCalculatorV1);
        assert!(validate_selection(legacy, None, true).is_ok());
        assert!(validate_selection(legacy, None, false).is_ok());
        assert!(validate_selection(joint, both, true).is_ok());
        assert!(validate_selection(legacy, both, true).is_err());
        assert!(validate_selection(joint, None, true).is_err());
        assert!(validate_selection(joint, both, false).is_err());
        assert!(
            validate_selection("trill.original-desktop-root.initialize.v3", both, true).is_err()
        );
    }
}
