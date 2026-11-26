//! User-facing control client for the one warm Droidloom Android cell.

#![forbid(unsafe_code)]

use std::{
    env, fs,
    io::{Read, Write},
    os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt, PermissionsExt},
    path::PathBuf,
    thread,
    time::{Duration, Instant},
};

#[path = "../container_services.rs"]
mod container_services;

use clap::{Parser, Subcommand, ValueEnum};
use droidloom_supervisor::control::{
    ControlRequest, DEFAULT_CELL_SPEC, DEFAULT_CONTROL_SOCKET, request, request_with_progress,
};
use droidloom_window_policy::{
    LogicalSize, SessionMode, WindowPolicyPaths, WindowPolicyStore, WindowPreference,
};

#[derive(Debug, Parser)]
#[command(name = "droidloomctl", version, about)]
struct Cli {
    /// Droidloom lifecycle socket.
    #[arg(long, global = true, default_value = DEFAULT_CONTROL_SOCKET)]
    socket: PathBuf,
    /// Control only the Android cell (internal service/recovery operation).
    #[arg(long, global = true, hide = true)]
    cell: bool,
    /// Emit the complete machine-readable response.
    #[arg(long, global = true)]
    json: bool,
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    /// Install a standalone APK, updating an existing app while retaining its data.
    Install {
        /// Host path to a standalone APK (split APK bundles are unsupported).
        apk: PathBuf,
        /// Android user identifier.
        #[arg(long, default_value_t = 0)]
        user: u32,
    },
    /// Atomically install original base and split APKs, preserving their signatures.
    InstallMultiple {
        /// Base APK and all required original splits (2 through 32 files).
        #[arg(required = true, num_args = 2..=32)]
        apks: Vec<PathBuf>,
        /// Android user identifier.
        #[arg(long, default_value_t = 0)]
        user: u32,
    },
    /// Update a source installation, or show pacman package-update instructions.
    Update {
        /// Discard updater-owned build outputs before rebuilding.
        #[arg(long)]
        clean: bool,
        /// Build and verify without activating the result.
        #[arg(long)]
        build_only: bool,
    },
    /// Start Droidloom, including Android, native windows, and the app catalog.
    Start {
        /// Return after starting the services, without waiting for Android readiness.
        #[arg(long)]
        no_wait: bool,
        /// Window mode: desktop (default) or mobile (fill available space).
        #[arg(long, default_value = "desktop")]
        mode: SessionMode,
        /// Cell specification.
        #[arg(long, default_value = DEFAULT_CELL_SPEC)]
        spec: PathBuf,
    },
    /// Stop Droidloom and release its runtime resources.
    Stop,
    /// Restart the complete Droidloom runtime.
    Restart {
        /// Return after restarting the services, without waiting for Android readiness.
        #[arg(long)]
        no_wait: bool,
        /// Window mode; omitted preserves the current session mode.
        #[arg(long)]
        mode: Option<SessionMode>,
        /// Cell specification.
        #[arg(long, default_value = DEFAULT_CELL_SPEC)]
        spec: PathBuf,
    },
    /// Report whether the cell is running, without checking Android readiness.
    Status,
    /// Check Android readiness once, without waiting for boot or restarting it.
    Readiness,
    /// Wait for Android boot, showing progress and a deadline without restarting it.
    Wait,
    /// Show recent Android logs, optionally filtered by an installed app's UID.
    Logs {
        /// Android package, including retained logs after its process exits.
        package: Option<String>,
        /// Number of recent logcat entries (output is also byte bounded).
        #[arg(short = 'n', long, default_value_t = 200, value_parser = clap::value_parser!(u32).range(1..=2000))]
        lines: u32,
        /// Android user whose package UID should be selected.
        #[arg(long, default_value_t = 0)]
        user: u32,
    },
    /// Show the global crash buffer and recorded exits for an optional package.
    Crashes {
        /// Select this package's exit history; crash traces still include all apps.
        package: Option<String>,
        /// Number of recent crash logcat entries (output is also byte bounded).
        #[arg(short = 'n', long, default_value_t = 1000, value_parser = clap::value_parser!(u32).range(1..=2000))]
        lines: u32,
    },
    /// Launch one Android application in the boot-managed runtime.
    Launch {
        /// Android package name.
        package: String,
        /// Optional flattened PACKAGE/ACTIVITY component.
        #[arg(long)]
        component: Option<String>,
        /// Restart this app with initial Android task size WIDTHxHEIGHT pixels.
        #[arg(long, value_parser = droidloom_supervisor::control::parse_launch_resolution)]
        resolution: Option<String>,
        /// Android user identifier.
        #[arg(long, default_value_t = 0)]
        user: u32,
        /// Expected cell specification.
        #[arg(long, default_value = DEFAULT_CELL_SPEC)]
        spec: PathBuf,
    },
    /// Inspect the installed package and verify its exact APK files.
    Inspect {
        /// Android package name.
        package: String,
        /// Android user identifier.
        #[arg(long, default_value_t = 0)]
        user: u32,
    },
    /// Observe package-scoped Android task metadata without changing tasks.
    Tasks {
        /// Android package name; task/object IDs are not accepted.
        package: String,
        /// Android user identifier.
        #[arg(long, default_value_t = 0)]
        user: u32,
    },
    /// Read the fixed public runtime VINTF inputs without checking compatibility.
    ObserveRuntimeVintf {
        /// Bounded RuntimeEpoch JSON from an actual prior owner observation.
        #[arg(long)]
        expected_epoch: PathBuf,
    },
    /// List Android applications exported to the native launcher.
    Applications {
        /// Android user identifier.
        #[arg(long, default_value_t = 0)]
        user: u32,
    },
    /// Persist Android's built-in-display density, warming the runtime if needed.
    Dpi {
        /// Android density in dots per inch.
        dpi: u32,
        /// Cell specification used when the runtime is cold.
        #[arg(long, default_value = DEFAULT_CELL_SPEC)]
        spec: PathBuf,
    },
    /// Persist how size-less initial Wayland configures are resolved.
    WindowMode {
        /// Mobile work-area or fixed windowed policy.
        mode: WindowMode,
        /// Logical width required by windowed mode.
        #[arg(long)]
        width: Option<u32>,
        /// Logical height required by windowed mode.
        #[arg(long)]
        height: Option<u32>,
        /// Apply only to this Android package instead of changing the default.
        #[arg(long)]
        package: Option<String>,
    },
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, ValueEnum)]
enum WindowMode {
    /// Fill the standard XDG bounds or logical output extent.
    FitOutput,
    /// Use an explicit logical size, constrained by XDG bounds.
    Windowed,
}

fn read_expected_epoch(
    path: &std::path::Path,
) -> Result<
    droidloom_supervisor::control::application_probe::RuntimeEpoch,
    Box<dyn std::error::Error>,
> {
    let file = fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)?;
    let before = file.metadata()?;
    if !before.is_file() || before.len() == 0 || before.len() > 4096 {
        return Err("expected epoch must be one bounded regular JSON file".into());
    }
    let mut bytes = Vec::new();
    (&file).take(4097).read_to_end(&mut bytes)?;
    let after = file.metadata()?;
    let identity = |m: &fs::Metadata| {
        (
            m.dev(),
            m.ino(),
            m.mode(),
            m.uid(),
            m.gid(),
            m.nlink(),
            m.len(),
            m.mtime(),
            m.mtime_nsec(),
            m.ctime(),
            m.ctime_nsec(),
        )
    };
    if identity(&before) != identity(&after) || bytes.len() as u64 != before.len() {
        return Err("expected epoch file changed while reading".into());
    }
    Ok(serde_json::from_slice(&bytes)?)
}

fn main() {
    if let Err(error) = run() {
        eprintln!("droidloomctl: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let cli = Cli::parse();
    let managed = match &cli.command {
        Command::Start { spec, mode, no_wait } if spec == &PathBuf::from(DEFAULT_CELL_SPEC) =>
            Some(("start", Some(*mode), !cli.cell && !no_wait)),
        Command::Restart { spec, mode, no_wait } if spec == &PathBuf::from(DEFAULT_CELL_SPEC) =>
            Some(("restart", *mode, !cli.cell && !no_wait)),
        Command::Stop => Some(("stop", None, false)),
        Command::Status => Some(("status", None, false)),
        Command::Wait | Command::Readiness => Some(("status", None, matches!(cli.command, Command::Wait))),
        _ => None,
    };
    if let Some((operation, mode, wait)) = managed {
        if cli.socket == PathBuf::from(DEFAULT_CONTROL_SOCKET)
            && let Some(choice) = droidloom_supervisor::control::SharedKernelLauncher::read()? {
            choice.revalidate()?;
            if mode.is_some_and(|selected| selected != SessionMode::Desktop) {
                return Err("the shared-kernel production service currently supports desktop mode".into());
            }
            let program = (operation != "stop").then(|| choice.entry_program()).transpose()?;
            let generation = if choice.early_kernel_boot() {container_services::early_lifecycle(operation)?} else {container_services::lifecycle(operation)?};
            let probe = matches!(cli.command, Command::Status | Command::Readiness | Command::Wait) || wait;
            let (state, message, original) = if let Some(owner) = generation.filter(|_| probe) {
                let response = droidloom_supervisor::control::container_entry_readiness(
                    std::path::Path::new("/run/droidloom-container/readiness.sock"), owner.pid, wait, &mut |message| {
                        if !cli.json { eprintln!("{message}"); }
                    },
                )?;
                owner.verify_current()?;
                if !response.ok { return Err(response.message.into()); }
                if wait && response.state != droidloom_supervisor::control::CellState::Running {
                    return Err("container entry replied before Android reached Running".into());
                }
                (response.state, response.message.clone(), Some(response))
            } else if operation == "start" || operation == "restart" {
                (droidloom_supervisor::control::CellState::Starting,
                 "Container services are running. Android readiness is pending.".into(), None)
            } else if wait {
                return Err("container entry is not running".into());
            } else {
                (droidloom_supervisor::control::CellState::Stopped, "Container services are stopped".into(), None)
            };
            if let Some(program) = program { program.revalidate()?; }
            choice.revalidate()?;
            if cli.json {
                let json = if let Some(response) = original {
                    serde_json::to_value(response)?
                } else {
                    serde_json::json!({"ok":true, "state":state, "message":message})
                };
                println!("{}", serde_json::to_string_pretty(&json)?);
            } else {
                println!("{message}");
            }
            return Ok(());
        }
    }
    if !cli.cell && cli.socket == PathBuf::from(DEFAULT_CONTROL_SOCKET)
        && !container_services::requires_production_control()? {
        let operation = match &cli.command {
            Command::Start {
                spec,
                mode,
                no_wait,
            } if spec == &PathBuf::from(DEFAULT_CELL_SPEC) => {
                Some(("start", Some(*mode), *no_wait))
            }
            Command::Stop => Some(("stop", None, true)),
            Command::Restart {
                spec,
                mode,
                no_wait,
            } if spec == &PathBuf::from(DEFAULT_CELL_SPEC) => Some(("restart", *mode, *no_wait)),
            _ => None,
        };
        if let Some((operation, mode, no_wait)) = operation {
            return session_lifecycle(operation, cli.json, mode, no_wait);
        }
        if matches!(cli.command, Command::Status) && !cli.socket.exists() {
            if cli.json {
                println!(
                    "{}",
                    serde_json::json!({"ok": true, "message": "Droidloom is stopped", "state": "stopped"})
                );
            } else {
                println!("Droidloom is stopped");
            }
            return Ok(());
        }
    }
    let mut report = |message: &str| {
        if !cli.json {
            eprintln!("{message}");
        }
    };
    let wait_after_start = !cli.cell
        && matches!(
            cli.command,
            Command::Start { no_wait: false, .. } | Command::Restart { no_wait: false, .. }
        );
    let mut response = if let Command::Install { apk, user } = &cli.command {
        droidloom_supervisor::control::install_apk_with_progress(
            &cli.socket,
            apk,
            *user,
            &mut report,
        )?
    } else if let Command::InstallMultiple { apks, user } = &cli.command {
        droidloom_supervisor::control::install_multiple_apks_with_progress(
            &cli.socket,
            apks,
            *user,
            &mut report,
        )?
    } else if let Command::Tasks { package, user } = &cli.command {
        let inspected = request_with_progress(
            &cli.socket,
            &ControlRequest::InspectApplication { package: package.clone(), user: *user },
            &mut report,
        )?;
        if !inspected.ok || inspected.state != droidloom_supervisor::control::CellState::Running {
            return Err(inspected.message.into());
        }
        let expected = inspected.inspection.ok_or("current package inspection is missing")?;
        if expected.package != *package || expected.user != *user
            || inspected.host_pid != Some(expected.epoch.cell_host_pid) {
            return Err("current package inspection owner differs".into());
        }
        let response = request_with_progress(
            &cli.socket,
            &ControlRequest::ObserveApplicationTasks { expected: expected.clone() },
            &mut report,
        )?;
        if response.ok {
            let observed: droidloom_supervisor::control::application_tasks::ApplicationTaskSnapshot =
                serde_json::from_str(response.diagnostics.as_deref().ok_or("task snapshot is missing")?)?;
            observed.validate(&expected)?;
            if response.state != droidloom_supervisor::control::CellState::Running
                || response.host_pid != Some(expected.epoch.cell_host_pid)
                || response.inspection.as_ref() != Some(&expected) {
                return Err("task snapshot response lost the actual inspected owner".into());
            }
        }
        response
    } else {
        let control_request = match cli.command {
            Command::Tasks { .. } => unreachable!("handled by the current inspected owner"),
            Command::Install { .. } | Command::InstallMultiple { .. } => {
                unreachable!("handled with its APK file descriptor")
            }
            Command::Update { clean, build_only } => {
                if PathBuf::from("/usr/share/droidloom/package.json").is_file() {
                    return Err("Droidloom is managed by pacman. Install the new package pair with sudo pacman -U, or build it with cargo run --locked -j 1 -p droidloom-package -- build. Sudo is needed only to replace package-owned system files and update pacman's database.".into());
                }
                let mut command = droidloom_cpu_placement::command("/usr/bin/droidloom-update");
                if clean {
                    command.arg("--clean");
                }
                if build_only {
                    command.arg("--build-only");
                }
                let status = command.status()?;
                if !status.success() {
                    return Err(format!("update failed: {status}").into());
                }
                return Ok(());
            }
            Command::Start { spec, .. } => ControlRequest::Start { spec },
            Command::Stop => ControlRequest::Stop,
            Command::Restart { spec, .. } => ControlRequest::Restart { spec },
            Command::Status => ControlRequest::Status,
            Command::Readiness => ControlRequest::Readiness,
            Command::Wait => ControlRequest::WaitReady,
            Command::Logs {
                package,
                lines,
                user,
            } => ControlRequest::Diagnostics {
                package,
                lines,
                user,
                crashes: false,
            },
            Command::Crashes { package, lines } => ControlRequest::Diagnostics {
                package,
                lines,
                user: 0,
                crashes: true,
            },
            Command::Launch {
                package,
                component,
                resolution,
                user,
                spec,
            } => ControlRequest::Launch {
                spec,
                package,
                component,
                resolution,
                user,
            },
            Command::Inspect { package, user } => {
                ControlRequest::InspectApplication { package, user }
            }
            Command::ObserveRuntimeVintf { expected_epoch } => ControlRequest::ObserveRuntimeVintf {
                expected_epoch: read_expected_epoch(&expected_epoch)?,
            },
            Command::Applications { user } => ControlRequest::ListApplications { user },
            Command::Dpi { dpi, spec } => ControlRequest::SetDpi { spec, dpi },
            Command::WindowMode {
                mode,
                width,
                height,
                package,
            } => {
                let preference = match (mode, width, height) {
                    (WindowMode::FitOutput, None, None) => WindowPreference::fit_output(),
                    (WindowMode::Windowed, Some(width), Some(height)) => {
                        WindowPreference::windowed(LogicalSize::new(width, height)?)
                    }
                    (WindowMode::FitOutput, _, _) => {
                        return Err("fit-output mode does not accept --width or --height".into());
                    }
                    (WindowMode::Windowed, _, _) => {
                        return Err("windowed mode requires both --width and --height".into());
                    }
                };
                let paths = WindowPolicyPaths::from_environment(
                    env::var_os("XDG_CONFIG_HOME"),
                    env::var_os("XDG_STATE_HOME"),
                    env::var_os("HOME"),
                )?;
                let mut store = WindowPolicyStore::load(paths)?;
                store.set_preference(package.as_deref(), preference)?;
                if cli.json {
                    println!(
                        "{}",
                        serde_json::to_string_pretty(&serde_json::json!({
                            "ok": true,
                            "mode": match mode {
                                WindowMode::FitOutput => "fit_output",
                                WindowMode::Windowed => "windowed",
                            },
                            "width": width,
                            "height": height,
                            "package": package,
                        }))?
                    );
                } else if let Some(package) = package {
                    println!("set persistent Droidloom window policy for {package}");
                } else {
                    println!("set persistent default Droidloom window policy");
                }
                return Ok(());
            }
        };
        if cli.cell {
            request(&cli.socket, &control_request)?
        } else {
            request_with_progress(&cli.socket, &control_request, &mut report)?
        }
    };
    if response.ok && wait_after_start {
        response = request_with_progress(&cli.socket, &ControlRequest::WaitReady, &mut report)?;
    }
    if cli.json {
        println!("{}", serde_json::to_string_pretty(&response)?);
    } else if response.ok {
        if let Some(diagnostics) = &response.diagnostics {
            print!("{diagnostics}");
            if !diagnostics.ends_with('\n') {
                println!();
            }
        } else {
            println!("{}", response.message);
        }
        if let Some(launch) = &response.launch
            && !launch.is_empty()
        {
            println!("{launch}");
        }
        if let Some(applications) = &response.applications {
            for application in applications {
                println!("{}\t{}", application.name, application.component);
            }
        }
    }
    if response.ok {
        Ok(())
    } else {
        Err(response.message.into())
    }
}

fn session_lifecycle(
    operation: &str,
    json: bool,
    requested_mode: Option<SessionMode>,
    no_wait: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    if operation != "stop" && PathBuf::from("/usr/share/droidloom/package.json").is_file() {
        let status =
            droidloom_cpu_placement::command("/usr/lib/droidloom/droidloom-package-helper")
                .arg("prepare")
                .status()?;
        if !status.success() {
            return Err("Droidloom setup did not complete; the runtime was not started".into());
        }
        let status = droidloom_cpu_placement::command("systemctl")
            .args(["--user", "daemon-reload"])
            .status()?;
        if !status.success() {
            return Err("could not reload the installed Droidloom user service".into());
        }
    }
    let mut operation = operation;
    if operation != "stop" {
        let runtime =
            PathBuf::from(env::var_os("XDG_RUNTIME_DIR").ok_or("XDG_RUNTIME_DIR is missing")?);
        if !runtime.is_absolute() {
            return Err("XDG_RUNTIME_DIR must be absolute".into());
        }
        let directory = runtime.join("droidloom");
        match fs::DirBuilder::new().mode(0o700).create(&directory) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
            Err(error) => return Err(error.into()),
        }
        let metadata = fs::symlink_metadata(&directory)?;
        if !metadata.is_dir() || metadata.uid() != fs::metadata(&runtime)?.uid() {
            return Err("Droidloom runtime directory must be a session-owned directory".into());
        }
        // Older clients created this directory with the default 0755 mode.
        // Keep the presenter's private-socket directory invariant on every start.
        fs::set_permissions(&directory, fs::Permissions::from_mode(0o700))?;
        let path = directory.join("session.env");
        let previous = match fs::read_to_string(&path) {
            Ok(value) => value
                .trim()
                .strip_prefix("DROIDLOOM_MODE=")
                .ok_or("invalid session mode file")?
                .parse::<SessionMode>()?,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => SessionMode::Desktop,
            Err(error) => return Err(error.into()),
        };
        let mode = requested_mode.unwrap_or(previous);
        // A start with a different mode must actually change the running service.
        if operation == "start"
            && mode != previous
            && droidloom_cpu_placement::command("systemctl")
                .args(["--user", "is-active", "--quiet", "droidloom.service"])
                .status()?
                .success()
        {
            operation = "restart";
        }
        let temporary = directory.join(format!(".session-{}.env", std::process::id()));
        let mut file = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&temporary)?;
        writeln!(file, "DROIDLOOM_MODE={mode}")?;
        file.sync_all()?;
        fs::rename(&temporary, path)?;
    }
    // Import the caller's live session without requiring a logout after install.
    if operation != "stop" {
        let variables: Vec<_> = ["WAYLAND_DISPLAY", "DISPLAY", "XDG_CURRENT_DESKTOP"]
            .into_iter()
            .filter(|name| env::var_os(name).is_some())
            .collect();
        if !variables.is_empty() {
            let status = droidloom_cpu_placement::command("systemctl")
                .args(["--user", "import-environment"])
                .args(variables)
                .status()?;
            if !status.success() {
                return Err("could not import the graphical session environment".into());
            }
        }
    }
    if !json {
        eprintln!("Waiting for Droidloom services to {operation} (up to 160 seconds)...");
    }
    let mut child = droidloom_cpu_placement::command("systemctl")
        .args(["--user", operation, "droidloom.service"])
        .spawn()?;
    let started = Instant::now();
    let mut next_update = Duration::from_secs(10);
    let status = loop {
        if let Some(status) = child.try_wait()? {
            break status;
        }
        if started.elapsed() >= Duration::from_secs(160) {
            let _ = child.kill();
            let _ = child.wait();
            return Err(format!("Droidloom services did not {operation} within 160 seconds. The systemd job may still be running. Check the logs with:\n  journalctl --user -b -u droidloom.service -n 100 --no-pager\n  journalctl -b -u droidloomd.service -n 200 --no-pager").into());
        }
        if started.elapsed() >= next_update {
            if !json {
                eprintln!(
                    "Waiting for Droidloom services to {operation} ({} seconds elapsed; {} seconds remaining)...",
                    started.elapsed().as_secs(),
                    160 - started.elapsed().as_secs()
                );
            }
            next_update += Duration::from_secs(10);
        }
        thread::sleep(Duration::from_millis(100));
    };
    if !status.success() {
        return Err(
            format!("{operation} failed; see journalctl --user -u droidloom.service").into(),
        );
    }
    let message = if operation == "stop" {
        "Droidloom is stopped"
    } else if no_wait {
        "Droidloom services are running; Android readiness has not been checked. Use `droidloomctl wait` to follow boot progress."
    } else {
        let response = request_with_progress(
            &PathBuf::from(DEFAULT_CONTROL_SOCKET),
            &ControlRequest::WaitReady,
            &mut |message| {
                if !json {
                    eprintln!("{message}");
                }
            },
        )?;
        if !response.ok {
            return Err(response.message.into());
        }
        "Droidloom is running; Android is ready"
    };
    if json {
        println!(
            "{}",
            serde_json::json!({"ok": true, "message": message, "state": if operation == "stop" { "stopped" } else { "running" }})
        );
    } else {
        println!("{message}");
    }
    Ok(())
}

#[cfg(test)]
mod task_metadata_cli_tests {
    use super::*;

    #[test]
    fn task_metadata_cli_accepts_only_package_and_user() {
        let parsed = Cli::try_parse_from(["droidloomctl", "--json", "tasks", "org.example.app", "--user", "0"]).unwrap();
        assert!(matches!(parsed.command, Command::Tasks { package, user: 0 } if package == "org.example.app"));
        for flag in ["--task", "--object", "--close", "--resolution", "--component", "--spec"] {
            assert!(Cli::try_parse_from(["droidloomctl", "tasks", "org.example.app", flag, "9"]).is_err(), "{flag}");
        }
    }
}
