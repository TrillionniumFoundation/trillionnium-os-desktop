// SPDX-License-Identifier: MPL-2.0

//! Test the `run` command

use crate::util::is_tdx_enabled;

mod basic {
    use std::path::PathBuf;

    use tempfile::tempdir;

    use crate::util::*;

    #[test]
    fn new_kernel_and_run() {
        const KERNEL_NAME: &str = "myos";

        // Use a per-test temporary directory to avoid cross-run collisions.
        let work_dir = tempdir().unwrap();

        // Run `cargo osdk new --kernel KERNEL_NAME` in the workspace directory
        let mut cmd_new = cargo_osdk(["new", "--kernel", KERNEL_NAME]);
        cmd_new.current_dir(&work_dir);
        cmd_new.ok().expect("create kernel fails");

        // Run `cargo osdk run` in the created kernel directory
        let os_dir = PathBuf::from(work_dir.path()).join(KERNEL_NAME);
        edit_config_files(&os_dir);
        let mut cmd_run = cargo_osdk(["run"]);
        cmd_run.current_dir(&os_dir);
        let output = cmd_run.ok().unwrap();
        assert_eq!(output.status.code().unwrap(), 0);
    }
}

const WORKSPACE: &str = "/tmp/kernel_test_workspace/run_command";

mod workspace {
    use crate::util::*;
    use std::{
        fs::{create_dir_all, remove_dir_all},
        path::Path,
    };

    fn create_kernel_in_workspace(workspace: &str, kernel_name: &str) {
        let os_dir = Path::new(workspace).join(kernel_name);
        if os_dir.exists() {
            remove_dir_all(&os_dir).unwrap();
        }
        let mut cargo_osdk_new = cargo_osdk(["new", "--kernel", kernel_name]);
        cargo_osdk_new.current_dir(workspace);
        cargo_osdk_new
            .ok()
            .expect("Failed to create kernel project");
        edit_config_files(&os_dir);
    }

    fn prepare_workspace(workspace: &str) {
        if !Path::new(workspace).exists() {
            create_dir_all(workspace).unwrap();
        }
    }
    #[derive(Debug)]
    pub struct WorkSpace {
        pub workspace: String,
        pub kernel_name: String,
    }
    impl WorkSpace {
        pub fn new(workspace: &str, kernel_name: &str) -> Self {
            prepare_workspace(workspace);
            create_kernel_in_workspace(workspace, kernel_name);
            Self {
                workspace: workspace.to_string(),
                kernel_name: kernel_name.to_string(),
            }
        }

        pub fn os_dir(&self) -> String {
            Path::new(&self.workspace)
                .join(self.kernel_name.clone())
                .to_string_lossy()
                .to_string()
        }
    }
    impl Drop for WorkSpace {
        fn drop(&mut self) {
            remove_dir_all(self.os_dir()).unwrap();
        }
    }
}

mod coverage_feature {
    use super::*;
    use crate::util::{cargo_osdk, depends_on_coverage};
    use std::path::Path;

    #[test]
    fn basic_coverage() {
        // Test skipped because TDX is enabled.
        if is_tdx_enabled() {
            return;
        }
        let workspace = workspace::WorkSpace::new(WORKSPACE, "basic_coverage");
        let manifest_path = Path::new(&workspace.os_dir()).join("Cargo.toml");
        let osdk_path = Path::new(&workspace.os_dir()).join("OSDK.toml");
        depends_on_coverage(&manifest_path, &osdk_path);
        let mut instance = cargo_osdk(["run", "--coverage"]);
        instance.current_dir(workspace.os_dir());

        let _output = instance
            .output()
            .expect("Failed to wait for QEMU coverage instance");
        let coverage_file = Path::new(&workspace.os_dir()).join("coverage.profraw");
        assert!(coverage_file.exists(), "Coverage file not found");
    }
}

mod qemu_gdb_feature {
    use super::*;
    use crate::util::cargo_osdk;
    use assert_cmd::Command;
    use std::{
        path::{Path, PathBuf},
        sync::{
            Arc,
            atomic::{AtomicBool, Ordering},
        },
        thread::sleep,
        time::{Duration, Instant},
    };

    const RUN_TIMEOUT: Duration = Duration::from_secs(300);
    const READY_TIMEOUT: Duration = Duration::from_secs(240);

    #[test]
    fn basic_debug() {
        // Test skipped because TDX is enabled.
        if is_tdx_enabled() {
            return;
        }
        let workspace = workspace::WorkSpace::new(WORKSPACE, "basic_debug");
        let unix_socket = {
            let path = Path::new(&workspace.os_dir()).join("qemu-gdb-sock");
            path.to_string_lossy().to_string()
        };

        let mut instance = cargo_osdk([
            "run",
            "--gdb-server",
            format!("addr={},wait-client", unix_socket.as_str()).as_str(),
        ]);
        instance.current_dir(workspace.os_dir());
        instance.timeout(RUN_TIMEOUT);

        let sock = unix_socket.clone();
        let cancelled = Arc::new(AtomicBool::new(false));
        let debugger_cancelled = cancelled.clone();
        let gdb = std::thread::spawn(move || {
            wait_for(&debugger_cancelled, || {
                Ok(Path::new(&sock).exists().then_some(()))
            })?;
            gdb_continue_via(&sock, None)
        });

        let output = instance.output();
        cancelled.store(true, Ordering::Relaxed);
        gdb.join()
            .expect("GDB worker panicked")
            .expect("GDB session failed");
        let output = output.expect("Failed to wait for QEMU GDB instance");
        assert!(output.status.success(), "OSDK failed: {output:?}");
        let stdout = String::from_utf8_lossy(&output.stdout).to_string();
        assert!(stdout.contains("Hello world from guest kernel!"));
    }

    fn wait_for<T>(
        cancelled: &AtomicBool,
        mut ready: impl FnMut() -> Result<Option<T>, String>,
    ) -> Result<T, String> {
        let deadline = Instant::now() + READY_TIMEOUT;
        loop {
            if let Some(value) = ready()? {
                return Ok(value);
            }
            if cancelled.load(Ordering::Relaxed) {
                return Err("OSDK exited before the debugger was ready".to_owned());
            }
            if Instant::now() >= deadline {
                return Err("timed out waiting for the debugger input".to_owned());
            }
            sleep(Duration::from_millis(20));
        }
    }

    fn gdb_continue_via(addr: &str, symbols: Option<&Path>) -> Result<(), String> {
        let mut gdb = Command::new("gdb");
        gdb.timeout(Duration::from_secs(30));
        gdb.args(["--batch", "-nx"]);
        if let Some(symbols) = symbols {
            gdb.arg("--se").arg(symbols);
        }
        gdb.args([
            "-ex",
            "set tcp auto-retry on",
            "-ex",
            "set tcp connect-timeout 20",
            "-ex",
            &format!("target remote {addr}"),
            "-ex",
            "info registers rip",
            "-ex",
            "detach",
        ]);
        let output = gdb.output().map_err(|error| error.to_string())?;
        if !output.status.success() {
            return Err(format!("GDB failed: {output:?}"));
        }
        if !String::from_utf8_lossy(&output.stdout).contains("rip") {
            return Err(format!(
                "GDB did not report the guest instruction pointer: {output:?}"
            ));
        }
        Ok(())
    }
    mod vsc {
        use super::*;

        #[test]
        fn vsc_launch_file() {
            // Test skipped because TDX is enabled.
            if is_tdx_enabled() {
                return;
            }
            let kernel_name = "vsc_launch_file";
            let workspace = workspace::WorkSpace::new(WORKSPACE, kernel_name);
            // Reserve an available TCP port instead of assuming a global fixed port.
            let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
            let addr = listener.local_addr().unwrap().to_string();
            drop(listener);

            let mut instance = cargo_osdk([
                "run",
                "--gdb-server",
                format!("wait-client,vscode,addr={}", addr).as_str(),
            ]);
            instance.current_dir(workspace.os_dir());
            instance.timeout(RUN_TIMEOUT);

            let dir = workspace.os_dir();
            let cancelled = Arc::new(AtomicBool::new(false));
            let debugger_cancelled = cancelled.clone();
            let gdb = std::thread::spawn(move || {
                let symbols = wait_for(&debugger_cancelled, || launch_symbol_file(&dir))?;
                gdb_continue_via(&addr, Some(&symbols))
            });

            let output = instance.output();
            cancelled.store(true, Ordering::Relaxed);
            gdb.join()
                .expect("GDB worker panicked")
                .expect("GDB session failed");
            let output = output.expect("Failed to wait for QEMU GDB instance");
            assert!(output.status.success(), "OSDK failed: {output:?}");
            let stdout = String::from_utf8_lossy(&output.stdout).to_string();
            assert!(stdout.contains("Hello world from guest kernel!"));
            assert!(
                !check_launch_file_existence(&workspace.os_dir()),
                "VSCode launch config file should be removed after debugging session"
            );
        }

        fn launch_symbol_file(workspace: &str) -> Result<Option<PathBuf>, String> {
            let launch_file = Path::new(workspace).join(".vscode/launch.json");
            let Ok(contents) = std::fs::read_to_string(launch_file) else {
                return Ok(None);
            };
            // The producer writes this concurrently; retry an incomplete JSON write.
            let Ok(launch) = serde_json::from_str::<serde_json::Value>(&contents) else {
                return Ok(None);
            };
            let command = launch["configurations"][0]["targetCreateCommands"][0]
                .as_str()
                .ok_or("missing VSCode target-create command")?;
            let words = shlex::split(command).ok_or("invalid VSCode target-create command")?;
            if words.len() != 3 || words[0] != "target" || words[1] != "create" {
                return Err(format!(
                    "unexpected VSCode target-create command: {command}"
                ));
            }
            let path = PathBuf::from(&words[2]);
            Ok(path.is_file().then_some(path))
        }

        fn check_launch_file_existence(workspace: &str) -> bool {
            let launch_file = Path::new(workspace).join(".vscode/launch.json");
            launch_file.exists()
        }
    }
}
