//! Finite Linux first-product Root composition. Existing/partial state is an
//! error. The original libraries own authority, lifecycle, queues and effects.
mod authority;
mod config;
mod fs;
mod geometry;
mod human;
mod packet;
mod process;
mod recovery;
mod recovery_authority;
mod recovery_sockets;
mod replay;
mod seed;
mod session;
mod supervisor;

use codex_hepta_agentd::{
    PreparedHostAuthoritySession, bind_root_agentd_socket, send_root_production_handoff,
};
use codex_hepta_supervisor::AgentCommand;
use std::ffi::OsString;
use std::os::fd::{AsFd, AsRawFd};
use std::os::unix::net::UnixDatagram;
use std::path::Path;

pub(super) type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

pub(super) fn initialize(path: &Path) -> Result<()> {
    root_environment()?;
    let inputs = config::Inputs::read(path)?;
    let fresh = geometry::Product::create(&inputs)?;
    fs::json_new(&fresh.admin.join("original-inputs.json"), &inputs)?;
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()?;
    let seed = runtime.block_on(seed::create(&inputs, &fresh))?;
    let replay = runtime.block_on(replay::initialize(&inputs, &fresh))?;
    run(inputs, fresh, seed, replay, runtime, /*previous*/ None)
}

pub(super) fn recover(path: &Path, operation: &str) -> Result<()> {
    root_environment()?;
    let inputs = config::Inputs::read_recovery(path)?;
    let (old, fresh) = recovery::Existing::open(&inputs, operation)?;
    let issuer_expiry = recovery_authority::wait_retirement(&old)?;
    recovery_sockets::retire(&inputs, &fresh, &old)?;
    let replay = replay::existing(&inputs, &fresh)?;
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()?;
    run(
        inputs,
        fresh,
        old.seed.clone(),
        replay,
        runtime,
        Some((old, issuer_expiry)),
    )
}

fn root_environment() -> Result<()> {
    if unsafe { libc::getuid() } != 0 || unsafe { libc::geteuid() } != 0 {
        return Err("explicit actual Root required".into());
    }
    // Only before runtime/worker threads exist. No provider credentials enter.
    unsafe {
        libc::umask(0o077);
        if libc::clearenv() != 0
            || libc::setenv(c"PATH".as_ptr(), c"/usr/bin:/bin".as_ptr(), 1) != 0
            || libc::setenv(c"LANG".as_ptr(), c"C.UTF-8".as_ptr(), 1) != 0
        {
            return Err(std::io::Error::last_os_error().into());
        }
    }
    Ok(())
}

fn run(
    inputs: config::Inputs,
    fresh: geometry::Product,
    seed: codex_hepta_agentd::NotesThreadSeedReceipt,
    replay: std::path::PathBuf,
    runtime: tokio::runtime::Runtime,
    previous: Option<(recovery::Existing, u64)>,
) -> Result<()> {
    // Only now begins the one 30-second Session/Root bootstrap episode.
    let staged = session::Session::spawn(&inputs, &fresh)?;
    let (deployment, consumer) = session::deployment()?;
    let (root_handoff, child_handoff) = UnixDatagram::pair()?;
    let control = bind_root_agentd_socket(
        fresh.record.layout.agentd_control_socket(),
        inputs.uid,
        inputs.gid,
    )?;
    let app_server = bind_root_agentd_socket(
        fresh.record.layout.app_server_socket(),
        inputs.uid,
        inputs.gid,
    )?;
    let notes_listener = bind_root_agentd_socket(
        &fresh.record.layout.run_root().join("notes-objective.sock"),
        inputs.uid,
        inputs.gid,
    )?;
    let app_pair = staged.pair.try_clone()?;
    let inherited_session = staged.owner.pidfd.try_clone()?;
    let mut args = Vec::<OsString>::new();
    let mut pair = |name: &str, value: OsString| {
        args.push(name.into());
        args.push(value);
    };
    pair("--root-production-profile", "notes".into());
    pair(
        "--root-production-handoff-fd",
        child_handoff.as_raw_fd().to_string().into(),
    );
    pair("--root-production-uid", inputs.uid.to_string().into());
    pair("--root-production-gid", inputs.gid.to_string().into());
    pair(
        "--root-production-control-fd",
        control.as_raw_fd().to_string().into(),
    );
    pair(
        "--root-production-app-server-fd",
        app_server.as_raw_fd().to_string().into(),
    );
    pair(
        "--root-production-lifetime-ms",
        inputs.lifetime_ms.to_string().into(),
    );
    pair(
        "--notes-production-handoff-fd",
        app_pair.as_raw_fd().to_string().into(),
    );
    pair(
        "--notes-literal-deployment-fd",
        consumer.as_raw_fd().to_string().into(),
    );
    pair(
        "--notes-literal-ui-fd",
        notes_listener.as_raw_fd().to_string().into(),
    );
    pair(
        "--notes-session-pidfd",
        inherited_session.as_raw_fd().to_string().into(),
    );
    pair(
        "--authbus-trust-file",
        fresh
            .record
            .layout
            .home_root()
            .join("authbus-root-trust.json")
            .into_os_string(),
    );
    pair("--authbus-checkpoint-file", replay.into_os_string());
    pair(
        "--objective-profile-file",
        fresh
            .record
            .layout
            .home_root()
            .join("notes-thread-profile.json")
            .into_os_string(),
    );
    let start_owner = if previous.is_some() {
        supervisor::start_successor
    } else {
        supervisor::start_original
    };
    let mut owner = start_owner(
        fresh.registry.clone(),
        &fresh.agent,
        AgentCommand::new(&inputs.programs.agentd, args)?,
        &[
            child_handoff.as_fd(),
            control.as_fd(),
            app_server.as_fd(),
            app_pair.as_fd(),
            consumer.as_fd(),
            notes_listener.as_fd(),
            inherited_session.as_fd(),
        ],
        inputs.uid,
        inputs.gid,
    )?;
    // Root keeps no unneeded inherited endpoint aliases.
    drop((
        child_handoff,
        control,
        app_server,
        app_pair,
        consumer,
        notes_listener,
        inherited_session,
    ));
    packet::remaining(staged.end)?;
    let files = match &previous {
        None => authority::initialize(&inputs, &fresh, &owner.registration, &seed, &staged.target)?,
        Some((old, expiry)) => {
            recovery_authority::rotate(&inputs, &fresh, old, &owner.registration, *expiry)?
        }
    };
    if previous.is_none() {
        replay::trust(&fresh, &files)?;
    }
    owner.registration = fs::read_root_json(&files.registration)?;
    // Monitor/reap always remains owned by the original Supervisor/driver.
    let (registration, owner_pidfd, monitor) = owner.monitor();
    let human_owner = owner_pidfd.try_clone()?;
    let prepared = if previous.is_some() {
        PreparedHostAuthoritySession::recover_with_physical_material(
            &files.config,
            &files.registration,
            owner_pidfd,
        )?
    } else {
        runtime.block_on(
            PreparedHostAuthoritySession::prepare_fresh_with_physical_material(
                &files.config,
                &files.registration,
                owner_pidfd,
            ),
        )?
    };
    if let Some((old, _)) = &previous {
        old.stage(
            &fresh,
            "20-material-current",
            &prepared.observe_physical_current()?,
        )?;
    }
    packet::remaining(staged.end)?;
    let (prepared, consumer_root) = if previous.is_some() {
        (prepared, replay::consumer_root(&inputs, &fresh)?)
    } else {
        prepared.handoff_fresh_agent_filesystem()?
    };
    let session::Session {
        owner: session_owner,
        pair: application_pair,
        end,
        target,
        environment,
    } = staged;
    let prepared = match &previous {
        None => prepared.with_notes_startup_from_session_before(
            &files.profile,
            application_pair,
            session_owner.pidfd.try_clone()?,
            deployment,
            end,
        )?,
        Some((old, _)) => prepared.with_notes_recovery_startup_from_session_before(
            &files.profile,
            application_pair,
            session_owner.pidfd.try_clone()?,
            deployment,
            end,
            codex_hepta_agentd::RootNotesPolicyPredecessor {
                target: &old.target,
                grant_lifetime_ms: inputs.grant_lifetime_ms,
            },
        )?,
    };
    let bootstrap = prepared.seal_bootstrap(&consumer_root)?;
    let self_pidfd = process::pin(std::process::id())?;
    send_root_production_handoff(
        root_handoff,
        &bootstrap,
        &self_pidfd,
        packet::remaining(end)?,
    )?;
    if let Some((old, _)) = &previous {
        old.stage(&fresh, "30-bootstrap-sent", &serde_json::json!({"original_operation_id":old.operation,"old_target":old.target,"new_target_for_future_operations_only":target,"thread":seed,"scope":"same-identity old outcome remains unasserted until original writer/helper readback; no old dispatch"}))?;
    }
    fs::json_new(
        &fresh.admin.join("actual-composition.json"),
        &serde_json::json!({
            "schema":"trill.original-desktop-root.composition.v1",
            "scope":if previous.is_some() {"existing same-boot composition; original outcome still requires original thread/receipt readback"} else {"fresh Root bootstrap and original process composition; model/Notes effect acceptance requires original runtime receipts"},
            "registration":registration, "original_thread_seed":seed,
            "objective_profile":&files.objective,
            "notes_state_dir":fresh.user.join("notes"),
            "notes_target":target,
            "session_pid":session_owner.pid(), "session_birth":packet::pinned_metadata(&session_owner.pidfd, session_owner.pid())?,
            "bootstrap_model_turn_sent":false,
        }),
    )?;
    let (profile, leader) = human::capture(&inputs, &fresh, &files, &human_owner, &environment)?;
    let prepared = prepared.with_original_logind_session(&profile, leader)?;
    // Same retained issuer/clock/Root instance. No open-only CLI child replaces it.
    let result = prepared.launch_native(&files.config, &files.registration, &profile);
    drop(monitor); // Original Supervisor stop/kill/reap only its actual child.
    drop(session_owner);
    drop(runtime);
    drop(fresh); // No forced/lazy unmount, no recursive deletion of product data.
    result.map_err(Into::into)
}
