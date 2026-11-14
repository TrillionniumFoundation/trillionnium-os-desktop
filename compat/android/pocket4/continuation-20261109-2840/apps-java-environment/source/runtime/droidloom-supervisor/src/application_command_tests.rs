use super::*;
use std::os::unix::net::UnixStream;
use std::os::unix::process::ExitStatusExt;

struct SleepFixture(Child);
impl SleepFixture {
    fn new() -> Self {
        Self(
            Command::new("/bin/sleep")
                .arg("30")
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .unwrap(),
        )
    }
}
impl Drop for SleepFixture {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

#[test]
fn held_process_rejects_exit_after_original_identity_was_bound() {
    let mut child = SleepFixture::new();
    let held = BoundProcess::capture(child.0.id()).unwrap();
    held.validate().unwrap();
    child.0.kill().unwrap();
    child.0.wait().unwrap();
    assert!(held.validate().is_err());
    assert!(pidfd_exited(&held.pidfd).unwrap());
}

#[test]
fn framework_start_identity_is_required_before_entry() {
    let me = BoundProcess::capture(std::process::id()).unwrap();
    assert!(
        NamespaceTarget::capture_named(
            std::process::id(),
            std::process::id(),
            me.identity.start_ticks + 1,
            None
        )
        .is_err()
    );
    assert!(
        NamespaceTarget::capture_named(
            std::process::id(),
            std::process::id(),
            me.identity.start_ticks,
            Some("a-different-process")
        )
        .is_err()
    );
}

#[test]
fn namespace_arguments_use_only_held_fds_and_explicit_environment() {
    let pid = std::process::id();
    let me = BoundProcess::capture(pid).unwrap();
    let target = NamespaceTarget::capture_named(pid, pid, me.identity.start_ticks, None).unwrap();
    let (command, inherited) = target
        .command(&["/system/bin/cmd".into(), "package".into()], None)
        .unwrap();
    let args: Vec<_> = command.get_args().map(|a| a.to_str().unwrap()).collect();
    assert_eq!(args.last(), Some(&"package"));
    assert!(
        !args
            .iter()
            .any(|a| a.starts_with("--target") || a.starts_with("--env"))
    );
    assert!(
        args.iter()
            .take_while(|a| **a != "--")
            .all(|a| a.contains("=/proc/self/fd/"))
    );
    assert!(!inherited.contains(&target.framework.directory.as_raw_fd()));
    assert!(!inherited.contains(&target.framework.pidfd.as_raw_fd()));
    let environment: Vec<_> = command
        .get_envs()
        .filter(|(_, v)| v.is_some())
        .map(|(k, _)| k.to_str().unwrap())
        .collect();
    assert_eq!(
        environment,
        ["ANDROID_DATA", "ANDROID_ROOT", "LANG", "PATH"]
    );
}

#[test]
fn current_java_environment_is_read_from_held_proc_and_stops_after_exit() {
    let mut child = SleepFixture(
        Command::new("/bin/sleep")
            .arg("30")
            .env_clear()
            .env("PATH", "/system/bin:/system/xbin")
            .env("BOOTCLASSPATH", "/system/framework/framework.jar")
            .env("DEX2OATBOOTCLASSPATH", "/system/framework/framework.jar")
            .env("ANDROID_ROOT", "/system")
            .env("ANDROID_DATA", "/data")
            .env("ANDROID_ART_ROOT", "/apex/com.android.art")
            .env("PRIVATE_TOKEN", "fixture-must-not-be-forwarded")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap(),
    );
    let held = BoundProcess::capture(child.0.id()).unwrap();
    let environment = held.runtime_environment().unwrap();
    let pid = std::process::id();
    let me = BoundProcess::capture(pid).unwrap();
    let target = NamespaceTarget::capture_named(pid, pid, me.identity.start_ticks, None).unwrap();
    let (command, _) = target
        .command(
            &["/system/bin/am".into(), "instrument".into()],
            Some(&environment),
        )
        .unwrap();
    let values: std::collections::BTreeMap<_, _> = command
        .get_envs()
        .filter_map(|(name, value)| {
            value.map(|value| (name.to_str().unwrap(), value.to_str().unwrap()))
        })
        .collect();
    assert_eq!(values["BOOTCLASSPATH"], "/system/framework/framework.jar");
    assert_eq!(values["ANDROID_ART_ROOT"], "/apex/com.android.art");
    assert_eq!(values["LANG"], "C");
    assert!(!values.contains_key("PRIVATE_TOKEN"));
    child.0.kill().unwrap();
    child.0.wait().unwrap();
    assert!(held.runtime_environment().is_err());
    assert!(pidfd_exited(&held.pidfd).unwrap());
}

#[test]
fn expired_java_invocation_does_not_enter_or_start_a_child() {
    let pid = std::process::id();
    let me = BoundProcess::capture(pid).unwrap();
    let target = NamespaceTarget::capture_named(pid, pid, me.identity.start_ticks, None).unwrap();
    let error = target
        .execute(
            &["/system/bin/am".into(), "instrument".into()],
            Instant::now() - Duration::from_millis(1),
        )
        .unwrap_err();
    assert!(error.contains("deadline exceeded before preparation"));
}

#[test]
fn nonblocking_reader_does_not_wait_for_a_held_writer() {
    let (mut reader, mut writer) = UnixStream::pair().unwrap();
    reader.set_nonblocking(true).unwrap();
    writer.write_all(b"still-open").unwrap();
    let mut bytes = Vec::new();
    let start = Instant::now();
    drain(&mut reader, &mut bytes).unwrap();
    assert_eq!(bytes, b"still-open");
    assert!(start.elapsed() < Duration::from_secs(1));
    // writer deliberately stays alive until after drain returns.
    writer.write_all(b"later").unwrap();
}

#[test]
fn successful_output_is_not_accepted_after_the_deadline() {
    let output = Output {
        status: ExitStatus::from_raw(0),
        stdout: b"late".to_vec(),
        stderr: Vec::new(),
    };
    assert!(success_before_deadline(output, Instant::now() - Duration::from_millis(1)).is_err());
}

fn require_owned_host_test() {
    // SAFETY: geteuid is a read-only syscall.
    assert_eq!(
        unsafe { libc::geteuid() },
        0,
        "explicit root-owned cgroup fixture required"
    );
    assert_eq!(
        std::env::var("DROIDLOOM_OWNED_COMMAND_TESTS").as_deref(),
        Ok("1")
    );
}

fn own_groups() -> Vec<PathBuf> {
    let prefix = format!("droidloom-app-probe-{}-", std::process::id());
    let mut paths: Vec<_> = fs::read_dir(current_cgroup_parent().unwrap())
        .unwrap()
        .map(Result::unwrap)
        .filter(|e| e.file_name().to_string_lossy().starts_with(&prefix))
        .map(|e| e.path())
        .collect();
    paths.sort();
    paths
}

fn shell(script: &str, argument: Option<&Path>) -> Command {
    let mut command = Command::new("/bin/sh");
    command
        .env_clear()
        .env("PATH", "/usr/bin:/bin")
        .arg("-c")
        .arg(script)
        .arg("owned-fixture");
    if let Some(path) = argument {
        command.arg(path);
    }
    command
}

fn assert_pid_dead_from(path: &Path) {
    let pid: u32 = fs::read_to_string(path).unwrap().trim().parse().unwrap();
    match open_pidfd(pid) {
        Err(error) => assert_eq!(error.raw_os_error(), Some(libc::ESRCH)),
        Ok(held) => assert!(
            pidfd_exited(&held).unwrap(),
            "owned escaped descendant remained live"
        ),
    }
}

#[test]
#[ignore = "requires explicit root test in a writable cgroup v2; creates only owned host fixtures"]
fn real_owned_group_retires_success_failure_overflow_and_escaped_pipe_holders() {
    require_owned_host_test();
    let before = own_groups();
    let mut normal = Command::new("/bin/echo");
    normal.arg("owned-output");
    let output = run_owned(normal, &[], &[], Instant::now() + Duration::from_secs(2)).unwrap();
    assert!(output.status.success());
    assert_eq!(output.stdout, b"owned-output\n");
    assert_eq!(own_groups(), before);

    let error = run_owned(
        shell("printf late; sleep 0.002", None),
        &[],
        &[],
        Instant::now() + Duration::from_millis(1),
    )
    .unwrap_err();
    assert!(error.contains("deadline exceeded"));
    assert!(error.contains("cgroup empty and direct child reaped"));
    assert_eq!(own_groups(), before);

    let output = run_owned(
        shell("printf bad >&2; exit 7", None),
        &[],
        &[],
        Instant::now() + Duration::from_secs(2),
    )
    .unwrap();
    assert_eq!(output.status.code(), Some(7));
    assert_eq!(output.stderr, b"bad");
    assert_eq!(own_groups(), before);

    let error = run_owned(
        shell("exec head -c 131072 /dev/zero", None),
        &[],
        &[],
        Instant::now() + Duration::from_secs(2),
    )
    .unwrap_err();
    assert!(error.contains("output bound exceeded"));
    assert!(error.contains("cgroup empty and direct child reaped"));
    assert_eq!(own_groups(), before);

    let temp = tempfile::tempdir().unwrap();
    let pidfile = temp.path().join("escaped.pid");
    // setsid escapes a process group while keeping stdout/stderr open. The
    // leader waits for its identity file, then exits before its descendant.
    let command = shell(
        "setsid sh -c 'echo $$ > \"$1\"; exec sleep 30' child \"$1\" & while ! test -s \"$1\"; do sleep 0.01; done; exit 0",
        Some(&pidfile),
    );
    let start = Instant::now();
    let error = run_owned(command, &[], &[], start + Duration::from_secs(2)).unwrap_err();
    assert!(start.elapsed() < Duration::from_secs(4));
    assert!(error.contains("leader exited with live invocation descendants"));
    assert!(error.contains("cgroup empty and direct child reaped"));
    assert_pid_dead_from(&pidfile);
    assert_eq!(own_groups(), before);

    let pidfile = temp.path().join("timeout.pid");
    let command = shell(
        "setsid sh -c 'echo $$ > \"$1\"; exec sleep 30' child \"$1\" & wait",
        Some(&pidfile),
    );
    let start = Instant::now();
    let error = run_owned(command, &[], &[], start + Duration::from_millis(300)).unwrap_err();
    assert!(start.elapsed() < Duration::from_secs(3));
    assert!(error.contains("deadline exceeded"));
    assert!(error.contains("cgroup empty and direct child reaped"));
    assert_pid_dead_from(&pidfile);
    assert_eq!(own_groups(), before);
}

#[test]
#[ignore = "requires explicit root test in a writable cgroup v2; enters only an owned host fixture"]
fn real_fd_namespace_entry_and_dead_pidfd_preexec_rejection() {
    require_owned_host_test();
    let before = own_groups();
    let mut child = SleepFixture::new();
    let held = BoundProcess::capture(child.0.id()).unwrap();
    let target = NamespaceTarget::capture_named(
        std::process::id(),
        child.0.id(),
        held.identity.start_ticks,
        Some("sleep"),
    )
    .unwrap();
    let output = target
        .execute(
            &["/bin/echo".into(), "fd-bound".into()],
            Instant::now() + Duration::from_secs(2),
        )
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(output.stdout, b"fd-bound\n");
    assert_eq!(own_groups(), before);
    child.0.kill().unwrap();
    child.0.wait().unwrap();
    assert!(
        target
            .execute(
                &["/bin/echo".into()],
                Instant::now() + Duration::from_secs(2)
            )
            .is_err()
    );
    let directory = tempfile::tempdir().unwrap();
    let marker = directory.path().join("must-not-exec");
    let command = shell("echo wrong > \"$1\"", Some(&marker));
    let error = run_owned(
        command,
        &[],
        &[held.pidfd.as_raw_fd()],
        Instant::now() + Duration::from_secs(2),
    )
    .unwrap_err();
    assert!(error.contains("spawn failed"));
    assert!(!marker.exists());
    assert_eq!(own_groups(), before);
}
