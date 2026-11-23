//! Fixed host-MAC installation helper; no general command interface.
use std::ffi::OsStr;

fn main() -> std::process::ExitCode {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() != 1 || args[0] != OsStr::new("seal-systemd-private") {
        eprintln!("usage: droidloom-host-mac seal-systemd-private");
        return std::process::ExitCode::from(2);
    }
    match droidloom_supervisor::production_mac_install::seal_systemd_private() {
        Ok(observed) => {
            println!("{observed}");
            std::process::ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("{error}");
            std::process::ExitCode::FAILURE
        }
    }
}
