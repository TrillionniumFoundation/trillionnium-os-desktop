//! The actual non-Root Session and metadata-only initial reservation peek.
use super::{Result, config::Inputs, fs, geometry::Product, packet, process};
use codex_hepta_memory::NotesTargetIdentity;
use std::collections::BTreeMap;
use std::fs::File;
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::OpenOptionsExt;
use std::os::unix::net::UnixDatagram;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

pub(super) struct Session {
    pub owner: process::ChildOwner,
    pub pair: UnixDatagram,
    pub end: Instant,
    pub target: NotesTargetIdentity,
    pub environment: BTreeMap<String, String>,
}

pub(super) fn environment(inputs: &Inputs, fresh: &Product) -> BTreeMap<String, String> {
    let mut environment = inputs.environment.clone();
    environment.insert("HOME".into(), fresh.user.join("home").display().to_string());
    environment.insert(
        "XDG_STATE_HOME".into(),
        fresh.user.join("state").display().to_string(),
    );
    environment.insert(
        "TRILL_UI_MAKEPAD_RESOURCES".into(),
        inputs.makepad_resources.display().to_string(),
    );
    environment.insert("TRILL_UI_DRAFT_RECOVERY".into(), "1".into());
    environment
}

impl Session {
    pub(super) fn spawn(inputs: &Inputs, fresh: &Product) -> Result<Self> {
        let (pair, child_pair) = UnixDatagram::pair()?;
        // Must precede spawn. Root remains the original anonymous pair creator.
        packet::passcred(&pair)?;
        let end = Instant::now() + Duration::from_secs(30);
        let program = fs::root_file(&inputs.programs.session, true)?;
        let environment = environment(inputs, fresh);
        let stdout = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(fresh.admin.join("session.stdout"))?;
        let stderr = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(fresh.admin.join("session.stderr"))?;
        let mut command = Command::new(format!("/proc/self/fd/{}", program.as_raw_fd()));
        command
            .arg("--notes-root-bootstrap-stdin")
            .current_dir(&fresh.user)
            .env_clear()
            .envs(&environment)
            .env("PATH", "/usr/bin:/bin")
            // The final Notes App must open its original durable store. Keep
            // this application setting out of the native human UI environment.
            .env("TRILL_NOTES_STATE_DIR", fresh.user.join("notes"))
            .env(
                "TRILL_NOTES_READBACK_HELPER_SHA256",
                fs::digest(
                    &inputs
                        .programs
                        .app_window
                        .with_file_name("trill-notes-recovery"),
                )?,
            )
            .stdin(Stdio::from(File::from(std::os::fd::OwnedFd::from(
                child_pair,
            ))))
            .stdout(stdout)
            .stderr(stderr);
        process::drop_to_owner(&mut command, inputs.uid, inputs.gid);
        let owner = process::ChildOwner::spawn(&mut command)?;
        // Verify real drop before reading, without inventing a serialized peer.
        loop {
            process::alive(&owner.pidfd)?;
            if process::actual_credentials(owner.pid(), inputs.uid, inputs.gid).is_ok() {
                break;
            }
            packet::remaining(end)?;
            std::thread::sleep(Duration::from_millis(5));
        }
        let birth = packet::pinned_metadata(&owner.pidfd, owner.pid())?;
        let (raw, _none) = packet::metadata(
            &pair,
            libc::ucred {
                pid: owner.pid() as i32,
                uid: inputs.uid,
                gid: inputs.gid,
            },
            packet::ReadMode::Peek,
            packet::Rights::None,
            end,
        )?;
        let reservation = trill_ui_core::notes_startup::NotesStartupReservation::parse_exact(&raw)
            .map_err(std::io::Error::other)?;
        let target: NotesTargetIdentity =
            serde_json::from_value(serde_json::to_value(&reservation.target)?)?;
        target.validate()?;
        if target.task_id != 1
            || birth != packet::pinned_metadata(&owner.pidfd, owner.pid())?
            || serde_json::to_value(&target)? != serde_json::to_value(&reservation.target)?
        {
            return Err(
                "actual initial Session target/birth or canonical Notes identity changed".into(),
            );
        }
        process::actual_credentials(owner.pid(), inputs.uid, inputs.gid)?;
        Ok(Self {
            owner,
            pair,
            end,
            target,
            environment,
        })
    }
}

pub(super) fn deployment() -> Result<(File, File)> {
    // SAFETY: static NUL-terminated name, returns a new private sealable FD.
    let raw = unsafe {
        libc::memfd_create(
            c"trill-original-notes-deployment".as_ptr(),
            libc::MFD_CLOEXEC | libc::MFD_ALLOW_SEALING,
        )
    };
    if raw < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    // SAFETY: takes ownership of exactly the new returned descriptor.
    let file = unsafe { File::from_raw_fd(raw) };
    if unsafe { libc::fchmod(file.as_raw_fd(), 0o600) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    // Independent O_RDONLY file description before sealing; never dup O_RDWR.
    let consumer = File::open(format!("/proc/self/fd/{}", file.as_raw_fd()))?;
    Ok((file, consumer))
}
