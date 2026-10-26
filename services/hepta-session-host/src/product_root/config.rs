//! Explicit administrator inputs. No principal, PID, signature, grant or head is input.
use super::Result;
use super::fs;
use serde::Deserialize;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Inputs {
    pub schema: String,
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

#[derive(Deserialize)]
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

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Sources {
    pub runtime_body: PathBuf,
    pub preferences: PathBuf,
    pub prompt_registry: PathBuf,
    pub sdk: PathBuf,
    pub source_freeze: PathBuf,
}

impl Inputs {
    pub(super) fn read(path: &Path) -> Result<Self> {
        let value: Self = fs::read_root_json(path)?;
        value.validate()?;
        Ok(value)
    }

    fn validate(&self) -> Result<()> {
        if self.schema != "trill.original-desktop-root.initialize.v1"
            || self.prefix.parent() != Some(Path::new("/var/lib/trill"))
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
            || !(1..=300_000).contains(&self.lifetime_ms)
            || !(1..=30_000).contains(&self.grant_lifetime_ms)
            || self.grant_lifetime_ms > self.lifetime_ms
            || !matches!(self.locale.as_str(), "zh-CN" | "en-US")
        {
            return Err("invalid explicit fresh Root inputs".into());
        }
        let p = &self.programs;
        for program in [
            &p.agentd,
            &p.app_server,
            &p.authority_host,
            &p.session,
            &p.shell,
            &p.app_window,
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
        let runtime = self
            .environment
            .get("XDG_RUNTIME_DIR")
            .ok_or("the actual original XDG_RUNTIME_DIR is required")?;
        fs::user_directory(Path::new(runtime), self.uid)?;
        let session = Path::new(runtime).join("trillionnium-ui/session.sock");
        if std::fs::symlink_metadata(&session).is_ok() {
            return Err("an existing Session socket is never replaced".into());
        }
        if self.environment.get("WAYLAND_DISPLAY").is_none()
            && self.environment.get("DISPLAY").is_none()
        {
            return Err("an actual display selection is required".into());
        }
        Ok(())
    }
}
