//! Exercise the real split-install CLI without host APK installation.
use std::io::{Read, Write};
use std::os::unix::net::UnixListener;
use std::process::Command;

#[test]
fn original_split_cli_preserves_success_and_failure_in_text_and_json() {
    for (ok, json) in [(true, false), (true, true), (false, false), (false, true)] {
        let directory = tempfile::tempdir().unwrap();
        let base = directory.path().join("base with spaces.apk");
        let split = directory.path().join("config.x86_64.apk");
        std::fs::write(&base, b"PK\x03\x04base").unwrap();
        std::fs::write(&split, b"PK\x03\x04split").unwrap();
        let socket = directory.path().join("control.sock");
        let listener = UnixListener::bind(&socket).unwrap();
        let server = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            // Real descriptor ownership and original segment bytes are tested
            // in control's socket tests. This mock checks CLI encoding/output.
            let mut bytes = Vec::new();
            stream.read_to_end(&mut bytes).unwrap();
            let request: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
            assert_eq!(
                request,
                serde_json::json!({"request": {
                    "command": "install_multiple", "user": 10, "lengths": [8, 9]
                }})
            );
            stream
                .write_all(b"{\"progress\":\"Installing original split APKs\"}\n")
                .unwrap();
            stream
                .write_all(
                    &serde_json::to_vec(&serde_json::json!({
                        "ok": ok, "state": "running",
                        "message": if ok { "Complete original APK set installed" }
                            else { "Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]" }
                    }))
                    .unwrap(),
                )
                .unwrap();
        });
        let mut command = Command::new(env!("CARGO_BIN_EXE_droidloomctl"));
        command
            .arg("--socket")
            .arg(socket)
            .arg("install-multiple")
            .arg(base)
            .arg(split)
            .args(["--user", "10"]);
        if json {
            command.arg("--json");
        }
        let output = command.output().unwrap();
        server.join().unwrap();
        assert_eq!(output.status.success(), ok, "{output:?}");
        if json {
            let response: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
            assert_eq!(response["ok"], ok);
            assert!(!String::from_utf8_lossy(&output.stdout).contains("progress"));
        } else if ok {
            assert!(String::from_utf8_lossy(&output.stdout).contains("original APK set installed"));
        } else {
            assert!(String::from_utf8_lossy(&output.stderr).contains("UPDATE_INCOMPATIBLE"));
        }
    }
}

#[test]
fn split_cli_rejects_missing_or_non_apk_before_connecting() {
    let directory = tempfile::tempdir().unwrap();
    let base = directory.path().join("base.apk");
    let split = directory.path().join("split.apk");
    std::fs::write(&base, b"PK\x03\x04base").unwrap();
    for content in [None, Some(b"not a signed APK".as_slice())] {
        if let Some(content) = content {
            std::fs::write(&split, content).unwrap();
        }
        let output = Command::new(env!("CARGO_BIN_EXE_droidloomctl"))
            .arg("--socket")
            .arg(directory.path().join("absent.sock"))
            .arg("install-multiple")
            .arg(&base)
            .arg(&split)
            .output()
            .unwrap();
        assert!(!output.status.success());
        let error = String::from_utf8_lossy(&output.stderr);
        assert!(error.contains("APK"), "{error}");
        assert!(!error.contains("connect to droidloomd"), "{error}");
    }
}

#[test]
fn split_cli_rejects_one_and_thirty_three_paths_without_contacting_daemon() {
    for count in [0, 1, 33] {
        let output = Command::new(env!("CARGO_BIN_EXE_droidloomctl"))
            .arg("--socket")
            .arg("/nonexistent-m552.sock")
            .arg("install-multiple")
            .args(vec!["absent.apk"; count])
            .output()
            .unwrap();
        assert!(!output.status.success(), "count={count}");
        let error = String::from_utf8_lossy(&output.stderr);
        assert!(!error.contains("connect to droidloomd"), "{error}");
        assert!(
            !error.contains("open split APK"),
            "argument count must fail before file open: {error}"
        );
    }
}

#[test]
fn split_cli_exposes_distinct_command_without_changing_single_apk_path() {
    let output = Command::new(env!("CARGO_BIN_EXE_droidloomctl"))
        .args(["install-multiple", "--help"])
        .output()
        .unwrap();
    assert!(output.status.success());
    let help = String::from_utf8_lossy(&output.stdout);
    assert!(help.contains("preserving their signatures"));
    assert!(help.contains("--user"));
    assert!(help.contains("--socket"));
}
