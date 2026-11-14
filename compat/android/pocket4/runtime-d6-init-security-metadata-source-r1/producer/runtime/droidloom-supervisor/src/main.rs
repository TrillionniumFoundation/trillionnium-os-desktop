//! Auditable Droidloom supervisor planning CLI.

#![forbid(unsafe_code)]

use std::fs;
use std::io::Read;
use std::os::unix::fs::OpenOptionsExt;
use std::path::PathBuf;

use clap::{Parser, Subcommand};
use droidloom_supervisor::CellSpec;
use droidloom_supervisor::development::{
    enter_development_cell, inspect_development_inputs, run_development_cell,
    validate_development_inputs,
};
use droidloom_supervisor::linux_plan::build_linux_plan;
#[cfg(target_os = "linux")]
use droidloom_supervisor::production_identity::IdentityAuthority;

const MAX_SPEC_BYTES: u64 = 1024 * 1024;

#[derive(Debug, Parser)]
#[command(name = "droidloom-supervisor", version, about)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    /// Inspect actual dedicated identity grants without reserving or starting a cell.
    #[cfg(target_os = "linux")]
    IdentityInspect {
        /// Root-owned cell specification JSON.
        #[arg(long)]
        spec: PathBuf,
    },
    /// Render the complete construction and reverse teardown plan as JSON.
    Plan {
        /// Cell specification JSON.
        #[arg(long)]
        spec: PathBuf,
    },
    /// Inspect readable boot inputs without root or any cell activation.
    DevelopmentInspect {
        /// Cell specification JSON; all referenced inputs must be readable.
        #[arg(long)]
        spec: PathBuf,
    },
    /// Validate the inputs for the minimal first-boot cell (requires root).
    DevelopmentValidate {
        /// Cell specification JSON.
        #[arg(long)]
        spec: PathBuf,
    },
    /// Start the minimal first-boot cell and attach to Android init logs.
    DevelopmentRun {
        /// Cell specification JSON.
        #[arg(long)]
        spec: PathBuf,
    },
    /// Private namespace re-entry used only by `development-run`.
    #[command(hide = true)]
    DevelopmentEnter {
        /// Cell specification JSON.
        #[arg(long)]
        spec: PathBuf,
    },
}

fn main() {
    if let Err(error) = run() {
        eprintln!("droidloom-supervisor: {error}");
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
    match Cli::parse().command {
        #[cfg(target_os = "linux")]
        Command::IdentityInspect { spec } => {
            let spec = load_spec(&spec)?;
            let authority = IdentityAuthority::inspect(&spec)?;
            println!("{}", serde_json::to_string_pretty(&authority.summary())?);
        }
        Command::Plan { spec } => {
            let spec = load_spec(&spec)?;
            let plan = build_linux_plan(&spec)?;
            println!("{}", serde_json::to_string_pretty(&plan)?);
        }
        Command::DevelopmentInspect { spec } => {
            let spec = load_spec(&spec)?;
            inspect_development_inputs(&spec)?;
            println!(
                "development boot inputs are readable and valid; cell activation was not attempted"
            );
        }
        Command::DevelopmentValidate { spec } => {
            let spec = load_spec(&spec)?;
            validate_development_inputs(&spec)?;
            println!("development boot inputs are valid");
        }
        Command::DevelopmentRun { spec } => {
            let cell = load_spec(&spec)?;
            run_development_cell(&spec, &cell)?;
        }
        Command::DevelopmentEnter { spec } => {
            let spec = load_spec(&spec)?;
            enter_development_cell(&spec)?;
        }
    }
    Ok(())
}

fn load_spec(path: &PathBuf) -> Result<CellSpec, Box<dyn std::error::Error>> {
    // Keep ordinary symlink paths compatible, but inspect and read the same
    // opened inode. Nonblocking open lets us reject a FIFO without a writer.
    let file = fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NONBLOCK)
        .open(path)?;
    let metadata = file.metadata()?;
    if !metadata.is_file() {
        return Err("cell specification must be a regular file".into());
    }
    if metadata.len() > MAX_SPEC_BYTES {
        return Err(format!(
            "cell specification is {} bytes; maximum is {MAX_SPEC_BYTES}",
            metadata.len()
        )
        .into());
    }
    read_spec(file)
}

fn read_spec(reader: impl Read) -> Result<CellSpec, Box<dyn std::error::Error>> {
    // Metadata is only an early rejection: a regular file can grow after
    // fstat. Read at most one byte beyond the accepted size to detect that.
    let mut bytes = Vec::new();
    reader.take(MAX_SPEC_BYTES + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > MAX_SPEC_BYTES {
        return Err(format!("cell specification exceeds maximum of {MAX_SPEC_BYTES} bytes").into());
    }
    Ok(serde_json::from_slice(&bytes)?)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;

    fn spec_bytes() -> Vec<u8> {
        serde_json::to_vec(&serde_json::json!({
            "host_uid": 1000,
            "subordinate_uids": {"start": 200_000, "count": 100_000},
            "subordinate_gids": {"start": 200_000, "count": 100_000},
            "image_dir": "/usr/lib/droidloom/images/base",
            "vendor_image": "/usr/lib/droidloom/images/vendor.img",
            "data_dir": "/var/lib/droidloom/cells/u1000",
            "runtime_dir": "/run/droidloom/cells/u1000",
            "render_node": "/dev/dri/renderD128",
            "denial_socket": "/run/user/1000/denial/native-bridge.sock"
        }))
        .unwrap()
    }

    #[test]
    fn spec_reads_exact_limit_regular_file_and_ordinary_symlink() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("cell.json");
        let mut bytes = spec_bytes();
        bytes.resize(MAX_SPEC_BYTES as usize, b' ');
        fs::write(&path, &bytes).unwrap();
        let loaded = load_spec(&path).unwrap();
        loaded.validate().unwrap();
        let link = root.path().join("current.json");
        symlink(&path, &link).unwrap();
        assert_eq!(load_spec(&link).unwrap(), loaded);
    }

    #[test]
    fn spec_rejects_oversized_regular_file() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("cell.json");
        let mut bytes = spec_bytes();
        bytes.resize(MAX_SPEC_BYTES as usize + 1, b' ');
        fs::write(&path, &bytes).unwrap();
        assert!(
            load_spec(&path)
                .unwrap_err()
                .to_string()
                .contains("maximum")
        );
    }

    #[test]
    fn spec_reader_bounds_unending_input() {
        struct Unending {
            bytes_read: u64,
        }
        impl Read for Unending {
            fn read(&mut self, buffer: &mut [u8]) -> std::io::Result<usize> {
                // Fail the regression deterministically instead of exhausting
                // memory if the production reader loses its hard limit.
                assert!(self.bytes_read + buffer.len() as u64 <= MAX_SPEC_BYTES + 1);
                buffer.fill(b' ');
                self.bytes_read += buffer.len() as u64;
                Ok(buffer.len())
            }
        }
        let mut reader = Unending { bytes_read: 0 };
        let error = read_spec(&mut reader).unwrap_err();
        assert!(error.to_string().contains("maximum"));
        assert_eq!(reader.bytes_read, MAX_SPEC_BYTES + 1);
    }

    #[test]
    fn spec_rejects_directory() {
        let root = tempfile::tempdir().unwrap();
        assert!(
            load_spec(&root.path().to_path_buf())
                .unwrap_err()
                .to_string()
                .contains("regular file")
        );
    }

    #[test]
    fn spec_fifo_is_rejected_without_waiting_for_a_writer() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("cell.fifo");
        assert!(
            std::process::Command::new("mkfifo")
                .arg(&path)
                .status()
                .unwrap()
                .success()
        );
        let reader_path = path.clone();
        let (sender, receiver) = std::sync::mpsc::sync_channel(1);
        let worker = std::thread::spawn(move || {
            let result = load_spec(&reader_path).map_err(|error| error.to_string());
            sender.send(result).unwrap();
        });
        match receiver.recv_timeout(std::time::Duration::from_secs(1)) {
            Ok(result) => {
                worker.join().unwrap();
                assert!(result.unwrap_err().contains("regular file"));
            }
            Err(std::sync::mpsc::RecvTimeoutError::Timeout) => {
                // A regressed blocking open must be released before joining.
                // Closing the writer also gives an unbounded old reader EOF.
                let writer = fs::OpenOptions::new()
                    .write(true)
                    .custom_flags(libc::O_NONBLOCK)
                    .open(&path)
                    .unwrap();
                drop(writer);
                worker.join().unwrap();
                panic!("cell specification waited for a FIFO writer");
            }
            Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => {
                worker.join().unwrap();
                panic!("cell specification reader exited without a result");
            }
        }
    }
}
