//! Actual trusted logind provider child and one held login-leader handoff.
use super::{
    Result, authority::RegistrationFiles, config::Inputs, fs, geometry::Product, packet, process,
    supervisor::InheritOnce,
};
use codex_hepta_agentd::HostAuthorityNativeProfile;
use serde::Deserialize;
use serde_json::json;
use std::os::fd::{AsFd, AsRawFd, OwnedFd};
use std::os::unix::fs::OpenOptionsExt;
use std::os::unix::net::UnixDatagram;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Receipt {
    schema: String,
    human_source: String,
    source_session_id: String,
    source_uid: u32,
    source_type: String,
    source_leader_start_ticks: u64,
    profile_sha256: String,
    original_daemon_pidfd_verified: bool,
    original_writer_lease_bound: bool,
    authority_initialized_or_renewed: bool,
    provider_credentials_read: bool,
    model_invoked: bool,
    production_ready: bool,
    scope: String,
}

pub(super) fn capture(
    inputs: &Inputs,
    fresh: &Product,
    files: &RegistrationFiles,
    owner_pidfd: &OwnedFd,
    environment: &std::collections::BTreeMap<String, String>,
) -> Result<(std::path::PathBuf, OwnedFd)> {
    process::alive(owner_pidfd)?;
    let config: codex_hepta_agentd::HostAuthorityServiceConfig = fs::read_root_json(&files.config)?;
    let writer_expiry = config
        .writer
        .as_ref()
        .ok_or("original registered writer absent")?
        .authority_lease
        .expires_at_unix_ms;
    let now = u64::try_from(
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_millis(),
    )?;
    let human_lifetime_ms = writer_expiry
        .checked_sub(now)
        .filter(|left| *left > 0)
        .ok_or("original writer expired before human capture")?
        .min(inputs.lifetime_ms);
    let template = fresh.admin.join("native-template.json");
    let profile = fresh.admin.join("native-human.json");
    fs::json_new(
        &template,
        &json!({
            "schema_version":1, "program":&inputs.programs.shell,
            "program_sha256":fs::digest(&inputs.programs.shell)?,
            "arguments":["--renderer","makepad","--notes-ui","original-thread"], "working_directory":&fresh.user,
            "environment": environment, "socket_path": fresh.prefix.join("r/root-text.sock"),
            "route":&files.route, "human_lifetime_ms": human_lifetime_ms,
            "can_interrupt":true, "can_resolve_approvals":false,
        }),
    )?;
    let (root, child) = UnixDatagram::pair()?;
    packet::passcred(&root)?;
    let program = fs::root_file(&inputs.programs.python, true)?;
    let script = fs::root_file(&inputs.programs.human_provider, false)?;
    let stdout = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(fresh.admin.join("human-provider.stdout"))?;
    let stderr = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(fresh.admin.join("human-provider.stderr"))?;
    let mut command = Command::new(format!("/proc/self/fd/{}", program.as_raw_fd()));
    command
        .arg(format!("/proc/self/fd/{}", script.as_raw_fd()))
        .args(["--config"])
        .arg(&files.config)
        .args(["--registration"])
        .arg(&files.registration)
        .args(["--template"])
        .arg(&template)
        .args(["--authority-host"])
        .arg(&inputs.programs.authority_host)
        .args([
            "--authority-host-sha256",
            &fs::digest(&inputs.programs.authority_host)?,
        ])
        .args(["--owner-pidfd", &owner_pidfd.as_raw_fd().to_string()])
        .args(["--lifetime-channel-fd", &child.as_raw_fd().to_string()])
        .args(["--output"])
        .arg(&profile)
        .current_dir(&fresh.admin)
        .env_clear()
        .env("PATH", "/usr/bin:/bin")
        .env("LANG", "C")
        .env("LC_ALL", "C")
        .stdin(Stdio::null())
        .stdout(stdout)
        .stderr(stderr);
    let inheritance = InheritOnce::new(&[owner_pidfd.as_fd(), child.as_fd(), script.as_fd()])?;
    let mut provider = process::ChildOwner::spawn(&mut command)?;
    drop(inheritance);
    drop(child);
    let end = Instant::now() + Duration::from_secs(15);
    let (raw, mut rights) = packet::metadata(
        &root,
        libc::ucred {
            pid: provider.pid() as i32,
            uid: 0,
            // SAFETY: observe the actual Root parent primary group inherited by its child.
            gid: unsafe { libc::getgid() },
        },
        packet::ReadMode::Consume,
        packet::Rights::One,
        end,
    )?;
    let receipt: Receipt = serde_json::from_slice(&raw)?;
    if receipt.schema != "trill.original-root-native-human-provider.v1"
        || receipt.human_source != "actual_local_systemd_logind_session"
        || receipt.source_uid != inputs.uid
        || !matches!(receipt.source_type.as_str(), "wayland" | "x11")
        || receipt.source_session_id.is_empty()
        || receipt.source_session_id.len() > 64
        || receipt.source_leader_start_ticks == 0
        || !receipt.original_daemon_pidfd_verified
        || !receipt.original_writer_lease_bound
        || receipt.authority_initialized_or_renewed
        || receipt.provider_credentials_read
        || receipt.model_invoked
        || receipt.production_ready
        || receipt.scope.len() > 4096
        || receipt.profile_sha256 != fs::digest(&profile)?
    {
        return Err("actual Root human provider receipt differs from the protected profile".into());
    }
    let leader = rights
        .pop()
        .ok_or("original provider did not transfer its held leader")?;
    process::alive(&leader)?;
    let fdinfo = std::fs::read_to_string(format!("/proc/self/fdinfo/{}", leader.as_raw_fd()))?;
    let pid = fdinfo
        .lines()
        .find_map(|s| s.strip_prefix("Pid:")?.trim().parse::<u32>().ok())
        .filter(|p| *p > 1)
        .ok_or("original login leader pidfd is invalid")?;
    let birth = packet::pinned_metadata(&leader, pid)?;
    if !birth.ends_with(&format!(":{pid}:{}", receipt.source_leader_start_ticks)) {
        return Err("actual held logind leader birth differs from its provider receipt".into());
    }
    if !provider.wait_before(end)?.success() {
        return Err("original human provider failed".into());
    }
    let actual: HostAuthorityNativeProfile = fs::read_root_json(&profile)?;
    if actual.route != files.route
        || actual.expires_at_ms <= now
        || actual.expires_at_ms > writer_expiry
    {
        return Err("Root human profile differs from the original seeded route".into());
    }
    fs::write_new(
        &fresh.admin.join("actual-human-provider-receipt.json"),
        &raw,
    )?;
    process::alive(owner_pidfd)?;
    process::alive(&leader)?;
    Ok((profile, leader))
}
