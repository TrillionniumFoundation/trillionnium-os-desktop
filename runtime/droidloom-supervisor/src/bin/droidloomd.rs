//! Privileged single-cell Droidloom lifecycle daemon.

#![deny(unsafe_op_in_unsafe_fn)]

use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};

use clap::Parser;
use droidloom_supervisor::control::{
    DEFAULT_CONTROL_SOCKET, DEFAULT_SPEC_DIRECTORY, DEFAULT_SUPERVISOR, DaemonConfig, serve,
};

#[cfg(target_os = "linux")]
#[path = "../container_oci_owner.rs"]
mod container_oci_owner;

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
    #[cfg(target_os = "linux")]
    if droidloom_supervisor::native_once_return::dispatch(
        &std::env::args_os().skip(1).collect::<Vec<_>>(),
    )? {
        return Ok(());
    }

    #[cfg(target_os = "linux")]
    if droidloom_supervisor::native_uevent_label::dispatch(
        &std::env::args_os().skip(1).collect::<Vec<_>>(),
    )? {
        return Ok(());
    }

    #[cfg(target_os = "linux")]
    if droidloom_supervisor::native_hardware_label::dispatch(
        &std::env::args_os().skip(1).collect::<Vec<_>>(),
    )? {
        return Ok(());
    }

    #[cfg(target_os = "linux")]
    if droidloom_supervisor::production_application::dispatch_camera(
        &std::env::args_os().skip(1).collect::<Vec<_>>(),
    )? {
        return Ok(());
    }

    // These fixed private entry points run before ordinary CLI parsing, CPU
    // placement, signals or daemon setup. Extra input cannot be a capability.
    #[cfg(target_os = "linux")]
    {
        let mut arguments = std::env::args_os().skip(1);
        let action = arguments.next();
        if action.as_deref() == Some(std::ffi::OsStr::new("--inspect-container-service-elf")) {
            use std::io::Read;
            if arguments.next().is_some() {
                return Err("service ELF inspection reads only standard input".into());
            }
            let mut bytes = Vec::new();
            std::io::stdin()
                .lock()
                .take(64 * 1024 * 1024 + 1)
                .read_to_end(&mut bytes)?;
            droidloom_supervisor::control::inspect_container_service_elf(&bytes)?;
            println!(
                "Service ELF structure verified; publication and runtime policy are separate checks"
            );
            return Ok(());
        }
        if action.as_deref() == Some(std::ffi::OsStr::new("--serve-early-instances")) {
            if arguments.next().is_some() { return Err("the boot instance factory accepts no parameters".into()); }
            install_signal_handlers()?;
            droidloom_supervisor::control::run_instance_factory(&SHUTDOWN)?;
            return Ok(());
        }
        if action.as_deref() == Some(std::ffi::OsStr::new("--launch-early-instance")) {
            if arguments.next().is_some() { return Err("the original instance launcher accepts no parameters".into()); }
            install_signal_handlers()?;
            droidloom_supervisor::control::run_instance_launcher(&SHUTDOWN)?;
            return Ok(());
        }
        if action.as_deref() == Some(std::ffi::OsStr::new("--adopt-early-factory")) {
            if arguments.next().is_some() {
                return Err("the original factory adopter accepts no parameters".into());
            }
            droidloom_supervisor::control::run_instance_adopter()?;
            return Ok(());
        }
        if action.as_deref() == Some(std::ffi::OsStr::new("--complete-early-boot")) {
            if arguments.next().is_some() {
                return Err("the selected early resource owner accepts no parameters".into());
            }
            if !droidloom_supervisor::control::SharedKernelLauncher::early_service_selected()? {
                return Err("kernel-first Android is not the selected system service".into());
            }
            droidloom_supervisor::control::complete_early_resources()?;
            return Ok(());
        }
        if action.as_deref() == Some(std::ffi::OsStr::new("--manage-container")) {
            if arguments.next().is_some() {
                return Err("container management accepts no arguments".into());
            }
            install_signal_handlers()?;
            container_oci_owner::run(&SHUTDOWN)?;
            return Ok(());
        }
        if action.as_deref() == Some(std::ffi::OsStr::new("--observe-early-container")) {
            if arguments.next().is_some() {
                return Err("early Android observation accepts no arguments".into());
            }
            install_signal_handlers()?;
            container_oci_owner::early::run(&SHUTDOWN)?;
            return Ok(());
        }
        if action.as_deref() == Some(std::ffi::OsStr::new("--post-switch-board-plan")) {
            if arguments.next().is_some() {
                return Err("post-switch board verification accepts no arguments".into());
            }
            if let Some(plan) = droidloom_supervisor::control::verify_post_switch_board_plan()? {
                println!("{plan}");
            }
            return Ok(());
        }
        if let Some(action) = action.as_ref().and_then(|arg| arg.to_str()).filter(|name| {
            matches!(
                *name,
                "--initramfs-selected-generation"
                    | "--initramfs-pre-switch-root"
                    | "--initramfs-board-plan"
            )
        }) {
            if arguments.next().is_some() {
                return Err("early boot release verification accepts no arguments".into());
            }
            let switch_root = action == "--initramfs-pre-switch-root";
            if let Some(digest) = droidloom_supervisor::control::verify_initramfs_release(
                switch_root,
                action == "--initramfs-board-plan",
            )? {
                println!("{digest}");
            }
            return Ok(());
        }
        if action.as_deref() == Some(std::ffi::OsStr::new("--initramfs-verify-stock-init")) {
            use std::os::fd::AsFd;
            if arguments.next().is_some() {
                return Err("the original init is supplied only on a held descriptor".into());
            }
            let descriptor = std::io::stdin().as_fd().try_clone_to_owned()?;
            droidloom_supervisor::control::verify_original_init_for_boot(&std::fs::File::from(
                descriptor,
            ))?;
            return Ok(());
        }
        if action.as_deref() == Some(std::ffi::OsStr::new("--inspect-early-generation")) {
            if arguments.next().is_some() {
                return Err("early generation inspection accepts no arguments".into());
            }
            let mac = droidloom_supervisor::control::ContainerManagerMac::acquire()?;
            let generation = droidloom_supervisor::control::EarlyAndroidGeneration::acquire()?;
            generation.revalidate()?;
            mac.revalidate()?;
            println!("Selected Android namespace PID 1 is live");
            return Ok(());
        }
        if action.as_deref() == Some(std::ffi::OsStr::new("--check-container-platform")) {
            if arguments.next().is_some() {
                return Err("platform check accepts no arguments".into());
            }
            droidloom_supervisor::control::check_installed_mac_platform()?;
            println!("Current host MAC backend kernel interfaces verified");
            return Ok(());
        }
        if action.as_deref() == Some(std::ffi::OsStr::new("--inspect-container-runtime-entry")) {
            if arguments.next().is_some() {
                return Err("runtime entry inspection accepts no arguments".into());
            }
            let selected = droidloom_supervisor::control::PreparedContainerSelection::acquire()?;
            println!("{}", selected.runtime_entry_description()?);
            return Ok(());
        }
        if action.as_deref() == Some(std::ffi::OsStr::new("--check-container-selection")) {
            if arguments.next().is_some() {
                return Err("container selection check accepts no arguments".into());
            }
            let selected = droidloom_supervisor::control::PreparedContainerSelection::acquire()?;
            selected.revalidate()?;
            println!("Shared-kernel launch selection verified");
            return Ok(());
        }
        if action.as_deref() == Some(std::ffi::OsStr::new("__production-engine-observer")) {
            if arguments.next().is_some() {
                return Err("private engine observer accepts no parameters".into());
            }
            droidloom_supervisor::production_application::run_engine_observer()?;
            return Ok(());
        }
        if action.as_deref() == Some(std::ffi::OsStr::new("__production-metadata-observer")) {
            if arguments.next().is_some() {
                return Err("private metadata observer accepts no parameters".into());
            }
            droidloom_supervisor::production_application::run_metadata_observer()?;
            return Ok(());
        }
        if action.as_deref() == Some(std::ffi::OsStr::new("__production-query-io")) {
            if arguments.next().is_some() {
                return Err("private query I/O creator accepts no parameters".into());
            }
            droidloom_supervisor::production_application::run_query_io_creator()?;
            return Ok(());
        }
        if action.as_deref() == Some(std::ffi::OsStr::new("__production-application-read")) {
            if arguments.next().is_some() {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidInput,
                    "private application worker accepts no parameters",
                )
                .into());
            }
            droidloom_supervisor::production_application::run_application_read_worker()?;
            return Ok(());
        }
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
    let cli = Cli::parse();
    #[cfg(target_os = "linux")]
    if droidloom_supervisor::control::SharedKernelLauncher::early_service_selected()? {
        if cli.socket != std::path::Path::new(DEFAULT_CONTROL_SOCKET)
            || cli.supervisor != std::path::Path::new(DEFAULT_SUPERVISOR)
            || cli.spec_directory != std::path::Path::new(DEFAULT_SPEC_DIRECTORY)
        {
            return Err("the kernel-first system service requires its installed paths".into());
        }
        droidloom_supervisor::control::complete_early_resources()?;
        return Ok(());
    }
    install_signal_handlers()?;
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
