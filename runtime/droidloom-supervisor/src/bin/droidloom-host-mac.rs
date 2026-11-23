//! Fixed installation and board calibration helpers.
use droidloom_supervisor::production_mac_install::{export_kernel_first_release, seal_systemd_private};
use std::{ffi::OsStr, io::{self, Write}, process::ExitCode};

fn main() -> ExitCode {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let result = match args.as_slice() {
        [command] if command == OsStr::new("seal-systemd-private") => {
            seal_systemd_private().and_then(|record|
                writeln!(io::stdout().lock(), "{record}").map_err(|error|error.to_string()))
        }
        [command] if command == OsStr::new("export-kernel-first-release") => {
            export_kernel_first_release().and_then(|release| {
                let mut stdout=io::stdout().lock();
                serde_json::to_writer(&mut stdout,&release).map_err(|error|error.to_string())?;
                stdout.write_all(b"\n").and_then(|_|stdout.flush()).map_err(|error|error.to_string())?;
                if unsafe{libc::fsync(libc::STDOUT_FILENO)}!=0 {return Err(io::Error::last_os_error().to_string());}
                Ok(())
            })
        }
        _ => {
            eprintln!("usage: droidloom-host-mac {{seal-systemd-private|export-kernel-first-release}}");
            return ExitCode::from(2);
        }
    };
    match result {
        Ok(())=>ExitCode::SUCCESS,
        Err(error)=>{eprintln!("{error}");ExitCode::FAILURE}
    }
}
