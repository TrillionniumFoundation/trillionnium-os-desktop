//! Privileged single-cell Droidloom lifecycle daemon.

#![deny(unsafe_op_in_unsafe_fn)]

use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};

use clap::Parser;
use droidloom_supervisor::control::{
    DEFAULT_CONTROL_SOCKET, DEFAULT_SPEC_DIRECTORY, DEFAULT_SUPERVISOR, DaemonConfig, serve,
};

static SHUTDOWN: AtomicBool = AtomicBool::new(false);

#[derive(Debug, Parser)]
#[command(name = "droidloomd", version, about)]
struct Cli {
    /// Root-owned local lifecycle socket.
    #[arg(long, default_value = DEFAULT_CONTROL_SOCKET)]
    socket: PathBuf,
    /// Legacy option retained for protocol compatibility; production never executes it.
    #[arg(long, default_value = DEFAULT_SUPERVISOR)]
    supervisor: PathBuf,
    /// Root-owned cell-specification directory trusted for user requests.
    #[arg(long, default_value = DEFAULT_SPEC_DIRECTORY)]
    spec_directory: PathBuf,
}

extern "C" fn request_shutdown(_signal: libc::c_int) {
    SHUTDOWN.store(true, Ordering::Relaxed);
}

fn main() {
    if let Err(error) = run() {
        eprintln!("droidloomd: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    // These fixed private entry points run before ordinary CLI parsing, CPU
    // placement, signals or daemon setup. Extra input cannot be a capability.
    #[cfg(target_os = "linux")]
    {
        let mut arguments = std::env::args_os().skip(1);
        let action = arguments.next();
        if action.as_deref() == Some(std::ffi::OsStr::new("__production-nss-observe"))
            || action.as_deref() == Some(std::ffi::OsStr::new("__production-nss-observe-owned"))
        {
            if arguments.next().is_some() {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidInput,
                    "private NSS entry accepts no parameters",
                )
                .into());
            }
            if action.as_deref() == Some(std::ffi::OsStr::new("__production-nss-observe")) {
                droidloom_supervisor::production_host_admission::run_nss_observation_worker()?;
            } else {
                droidloom_supervisor::production_host_admission::run_nss_observation_probe()?;
            }
            return Ok(());
        }
    }
    // Preserve the actual production unit's CPU placement. Its owned cgroup
    // admission checks the inherited affinity; the old Background role would
    // overwrite the separately reviewed CPUs 2-23 policy.
    install_signal_handlers()?;
    let cli = Cli::parse();
    let config = DaemonConfig {
        socket: cli.socket,
        supervisor: cli.supervisor,
        spec_directory: cli.spec_directory,
    };
    serve(&config, &SHUTDOWN)?;
    Ok(())
}

fn install_signal_handlers() -> Result<(), std::io::Error> {
    for signal in [libc::SIGTERM, libc::SIGINT] {
        let previous =
            unsafe { libc::signal(signal, request_shutdown as *const () as libc::sighandler_t) };
        if previous == libc::SIG_ERR {
            return Err(std::io::Error::last_os_error());
        }
    }
    Ok(())
}
