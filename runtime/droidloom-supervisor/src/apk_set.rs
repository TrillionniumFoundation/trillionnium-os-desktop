//! Bounded, byte-preserving split APK transport and atomic Android sessions.
//!
//! Each original APK remains independently signed. This is an IPC payload, not
//! a merged/repacked APK. `PackageManager` validates package/version/certificates.
#![forbid(unsafe_code)]

use super::{ControlError, apk, diagnostics, io_error};
use std::fs::{File, OpenOptions};
use std::io::{self, Read, Seek, SeekFrom};
use std::os::unix::fs::{FileExt, OpenOptionsExt};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

const MAX_SPLITS: usize = 32;
const MAX_TOTAL_BYTES: u64 = 2 * 1024 * 1024 * 1024;
const SESSION_BUDGET: Duration = Duration::from_secs(110);

pub(super) fn prepare(paths: &[PathBuf]) -> Result<(File, Vec<u64>), ControlError> {
    if !(2..=MAX_SPLITS).contains(&paths.len()) {
        return Err(invalid("supply 2 through 32 original APK files"));
    }
    let mut inputs = Vec::with_capacity(paths.len());
    let mut lengths = Vec::with_capacity(paths.len());
    let mut total = 0_u64;
    for path in paths {
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NONBLOCK)
            .open(path)
            .map_err(|e| io_error("open split APK with caller permissions", e))?;
        let length = apk::validate(&file)?;
        total = total
            .checked_add(length)
            .filter(|v| *v <= MAX_TOTAL_BYTES)
            .ok_or_else(|| invalid("split APK set exceeds 2 GiB"))?;
        lengths.push(length);
        inputs.push(file);
    }
    // Unlinked, private disk-backed temporary file: no root-side pathname open,
    // archive extraction, path traversal, or 2-GiB in-memory allocation.
    let mut payload = tempfile::tempfile().map_err(|e| io_error("create split payload", e))?;
    for (file, length) in inputs.iter_mut().zip(&lengths) {
        let copied = io::copy(&mut (&mut *file).take(*length), &mut payload)
            .map_err(|e| io_error("copy original split bytes", e))?;
        if copied != *length
            || file
                .metadata()
                .map_err(|e| io_error("recheck split length", e))?
                .len()
                != *length
        {
            return Err(invalid("split APK length changed during preparation"));
        }
    }
    validate(&payload, &lengths)?;
    payload
        .rewind()
        .map_err(|e| io_error("rewind split payload", e))?;
    Ok((payload, lengths))
}

pub(super) fn validate(file: &File, lengths: &[u64]) -> Result<u64, ControlError> {
    if !(2..=MAX_SPLITS).contains(&lengths.len()) {
        return Err(invalid("split descriptor requires 2 through 32 lengths"));
    }
    let metadata = file
        .metadata()
        .map_err(|e| io_error("inspect split payload", e))?;
    if !metadata.is_file() {
        return Err(invalid("split payload must be a regular file"));
    }
    let mut total = 0_u64;
    for &length in lengths {
        if length < 4 {
            return Err(invalid("each split must contain an APK ZIP header"));
        }
        total = total
            .checked_add(length)
            .filter(|v| *v <= MAX_TOTAL_BYTES)
            .ok_or_else(|| invalid("split APK set exceeds 2 GiB"))?;
    }
    if metadata.len() != total {
        return Err(invalid(
            "split payload size does not match declared lengths",
        ));
    }
    let mut offset = 0;
    for &length in lengths {
        let mut magic = [0; 4];
        file.read_exact_at(&mut magic, offset)
            .map_err(|e| io_error("read split header", e))?;
        if magic != *b"PK\x03\x04" {
            return Err(invalid("a split is not an APK ZIP archive"));
        }
        offset += length;
    }
    Ok(total)
}

pub(super) fn install(
    pid: u32,
    user: u32,
    file: File,
    lengths: &[u64],
) -> Result<(), ControlError> {
    transact(file, lengths, user, |args, input, seconds| {
        let mut command = session_command(pid, args, seconds);
        diagnostics::capture_with_stdin(&mut command, input.map_or_else(Stdio::null, Stdio::from))
            .map_err(|e| invalid(&format!("Android split session command failed: {e}")))
    })
}

fn session_command(pid: u32, args: &[String], seconds: u64) -> Command {
    let mut command = droidloom_cpu_placement::command("/usr/bin/timeout");
    command
        .args([
            "--kill-after=5s",
            &format!("{seconds}s"),
            "/usr/bin/nsenter",
            "--target",
        ])
        .arg(pid.to_string())
        .args([
            "--mount",
            "--uts",
            "--ipc",
            "--net",
            "--pid",
            "--cgroup",
            "--root",
            "--wd",
            "--env",
            "--",
            "/system/bin/cmd",
            "package",
        ])
        .args(args);
    command
}

fn transact<F>(mut file: File, lengths: &[u64], user: u32, mut call: F) -> Result<(), ControlError>
where
    F: FnMut(&[String], Option<File>, u64) -> Result<String, ControlError>,
{
    let total = validate(&file, lengths)?;
    let started = Instant::now();
    let budget = || {
        SESSION_BUDGET
            .checked_sub(started.elapsed())
            .filter(|d| !d.is_zero())
            .map(|d| d.as_secs().max(1))
            .ok_or_else(|| invalid("split session overall deadline expired"))
    };
    let create = vec![
        "install-create".into(),
        "-r".into(),
        "--user".into(),
        user.to_string(),
        "-S".into(),
        total.to_string(),
    ];
    let response = call(&create, None, budget()?)?;
    let session = parse_session(&response)?;
    let mut commit_attempted = false;
    let outcome = (|| {
        let mut offset = 0;
        for (index, &length) in lengths.iter().enumerate() {
            // Explicitly reset the shared open-file-description offset. Android
            // receives exactly -S bytes from each unchanged APK segment.
            file.seek(SeekFrom::Start(offset))
                .map_err(|e| io_error("seek split payload", e))?;
            let input = file
                .try_clone()
                .map_err(|e| io_error("duplicate split payload", e))?;
            let args = vec![
                "install-write".into(),
                "-S".into(),
                length.to_string(),
                session.to_string(),
                format!("split-{index:04}.apk"),
            ];
            let output = call(&args, Some(input), budget()?)?;
            confirm(&output, &format!("Success: streamed {length} bytes"))?;
            offset += length;
        }
        let args = vec!["install-commit".into(), session.to_string()];
        let seconds = budget()?;
        commit_attempted = true;
        confirm(&call(&args, None, seconds)?, "Success")
    })();
    if let Err(error) = outcome {
        let abandon = vec!["install-abandon".into(), session.to_string()];
        let cleanup = call(&abandon, None, 5).and_then(|output| confirm(&output, "Success"));
        return Err(invalid(&format!(
            "{error}; session {session} abandonment: {}; {}",
            match cleanup {
                Ok(()) => "confirmed".into(),
                Err(e) => format!("NOT confirmed ({e})"),
            },
            if commit_attempted {
                "commit was NOT confirmed: inspect installed version before any retry"
            } else {
                "commit was not attempted; existing installed app was not uninstalled"
            }
        )));
    }
    Ok(())
}

fn parse_session(output: &str) -> Result<u32, ControlError> {
    let sessions: Vec<_> = output
        .lines()
        .filter_map(|line| {
            line.trim()
                .strip_prefix("Success: created install session [")
                .and_then(|s| s.strip_suffix(']'))
                .filter(|s| !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit()))
                .and_then(|s| s.parse::<u32>().ok())
                .filter(|id| *id > 0 && i32::try_from(*id).is_ok())
        })
        .collect();
    if sessions.len() != 1 || output.contains("Failure") || output.contains("Error:") {
        return Err(invalid(
            "Android did not identify exactly one created session; inspect outstanding sessions before retry",
        ));
    }
    Ok(sessions[0])
}

fn confirm(output: &str, expected: &str) -> Result<(), ControlError> {
    if output.lines().any(|line| line.trim() == expected)
        && !output.contains("Failure")
        && !output.contains("Error:")
    {
        Ok(())
    } else {
        Err(invalid(&format!(
            "Android did not confirm {expected:?}: {}",
            output.trim()
        )))
    }
}

fn invalid(message: &str) -> ControlError {
    ControlError::Invalid(message.into())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    fn payload() -> File {
        let mut file = tempfile::tempfile().unwrap();
        file.write_all(b"PK\x03\x04basePK\x03\x04split").unwrap();
        file
    }
    #[test]
    fn validates_original_segment_headers_and_exact_total() {
        let file = payload();
        assert_eq!(validate(&file, &[8, 9]).unwrap(), 17);
        for sizes in [
            vec![],
            vec![17],
            vec![8, 8],
            vec![9, 8],
            vec![3, 14],
            vec![4; 33],
            vec![u64::MAX, 8],
        ] {
            assert!(validate(&file, &sizes).is_err(), "{sizes:?}");
        }
        assert!(validate(&File::open("/dev/null").unwrap(), &[8, 9]).is_err());
    }
    #[test]
    fn requires_unambiguous_bounded_positive_session_identity() {
        assert_eq!(
            parse_session("Success: created install session [12]\n").unwrap(),
            12
        );
        for value in [
            "Success",
            "Success: created install session [-1]",
            "Success: created install session [0]",
            "Success: created install session [2147483648]",
            "Success: created install session [1]\nFailure [bad]",
            "Success: created install session [1]\nSuccess: created install session [2]",
        ] {
            assert!(parse_session(value).is_err(), "{value}");
        }
    }
    #[test]
    fn success_is_exact_and_failure_cannot_be_hidden() {
        assert!(confirm("Success: streamed 8 bytes\n", "Success: streamed 8 bytes").is_ok());
        for s in [
            "Success",
            "Success: streamed 9 bytes",
            "Success: streamed 8 bytes\nFailure [bad]",
            "Success: streamed 8 bytes\nError: bad",
        ] {
            assert!(confirm(s, "Success: streamed 8 bytes").is_err());
        }
    }
    #[test]
    fn preserves_bytes_then_commits_once_without_uninstall_or_downgrade() {
        let mut seen = Vec::new();
        let mut bodies = Vec::new();
        transact(payload(), &[8, 9], 10, |args, input, seconds| {
            assert!((1..=110).contains(&seconds));
            seen.push(args.to_vec());
            match args[0].as_str() {
                "install-create" => Ok("Success: created install session [23]".into()),
                "install-write" => {
                    let length = args[2].parse::<u64>().unwrap();
                    let mut body = Vec::new();
                    input.unwrap().take(length).read_to_end(&mut body).unwrap();
                    bodies.push(body);
                    Ok(format!("Success: streamed {length} bytes"))
                }
                "install-commit" => Ok("Success".into()),
                _ => panic!("unexpected operation"),
            }
        })
        .unwrap();
        assert_eq!(
            bodies,
            vec![b"PK\x03\x04base".to_vec(), b"PK\x03\x04split".to_vec()]
        );
        assert_eq!(seen.len(), 4);
        assert_eq!(
            seen[0],
            vec!["install-create", "-r", "--user", "10", "-S", "17"]
        );
        assert_eq!(
            seen[1],
            vec!["install-write", "-S", "8", "23", "split-0000.apk"]
        );
        assert_eq!(seen[3], vec!["install-commit", "23"]);
        assert!(
            !seen
                .iter()
                .flatten()
                .any(|s| s == "uninstall" || s == "-d" || s == "-g")
        );
    }
    #[test]
    fn failed_write_abandons_and_never_commits() {
        let mut calls = Vec::new();
        let error = transact(payload(), &[8, 9], 0, |args, _, _| {
            calls.push(args[0].clone());
            Ok(match args[0].as_str() {
                "install-create" => "Success: created install session [7]",
                "install-abandon" => "Success",
                _ => "Failure [INSTALL_FAILED_INVALID_APK]",
            }
            .into())
        })
        .unwrap_err()
        .to_string();
        assert_eq!(
            calls,
            vec!["install-create", "install-write", "install-abandon"]
        );
        assert!(error.contains("abandonment: confirmed"));
        assert!(error.contains("commit was not attempted"));
    }
    #[test]
    fn failed_commit_and_failed_cleanup_are_not_reported_as_success() {
        let mut calls = Vec::new();
        let error = transact(payload(), &[8, 9], 0, |args, _, _| {
            calls.push(args[0].clone());
            match args[0].as_str() {
                "install-create" => Ok("Success: created install session [4]".into()),
                "install-write" => Ok(format!("Success: streamed {} bytes", args[2])),
                _ => Err(invalid("timeout")),
            }
        })
        .unwrap_err()
        .to_string();
        assert_eq!(
            calls
                .iter()
                .filter(|v| v.as_str() == "install-commit")
                .count(),
            1
        );
        assert_eq!(calls.last().unwrap(), "install-abandon");
        assert!(error.contains("NOT confirmed"));
        assert!(error.contains("before any retry"));
    }
    #[test]
    fn invalid_payload_never_creates_a_session() {
        assert!(
            transact(payload(), &[8, 8], 0, |_, _, _| panic!(
                "must not contact Android"
            ))
            .is_err()
        );
    }
    #[test]
    fn invalid_create_response_never_guesses_session_to_abandon() {
        let mut count = 0;
        assert!(
            transact(payload(), &[8, 9], 0, |_, _, _| {
                count += 1;
                Ok("Failure [bad]".into())
            })
            .is_err()
        );
        assert_eq!(count, 1);
    }
    #[test]
    fn preparation_is_byte_identical_and_fails_before_any_socket() {
        let dir = tempfile::tempdir().unwrap();
        let a = dir.path().join("base with spaces.apk");
        let b = dir.path().join("config.apk");
        std::fs::write(&a, b"PK\x03\x04base").unwrap();
        std::fs::write(&b, b"PK\x03\x04split").unwrap();
        let (mut file, lengths) = prepare(&[a.clone(), b.clone()]).unwrap();
        assert_eq!(lengths, vec![8, 9]);
        let mut bytes = Vec::new();
        file.read_to_end(&mut bytes).unwrap();
        assert_eq!(bytes, b"PK\x03\x04basePK\x03\x04split");
        assert!(prepare(std::slice::from_ref(&a)).is_err());
        assert!(prepare(&[a.clone(), dir.path().join("absent.apk")]).is_err());
        assert!(prepare(&[a.clone(), PathBuf::from("/dev/null")]).is_err());
        assert!(prepare(&vec![a; 33]).is_err());
    }
    #[test]
    fn namespace_command_has_fixed_argv_and_bounded_timeout() {
        let command = session_command(1234, &["install-commit".into(), "23".into()], 17);
        let args: Vec<_> = command.get_args().map(|a| a.to_str().unwrap()).collect();
        assert_eq!(
            &args[..5],
            &[
                "--kill-after=5s",
                "17s",
                "/usr/bin/nsenter",
                "--target",
                "1234"
            ]
        );
        assert_eq!(
            &args[args.len() - 4..],
            &["/system/bin/cmd", "package", "install-commit", "23"]
        );
        assert!(!args.contains(&"sh"));
    }
}
