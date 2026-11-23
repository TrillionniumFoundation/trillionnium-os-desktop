use super::super::{
    DEVELOPMENT_UNSHARE_ARGUMENTS, RenderNodeSysfsMetadata, arm_android_first_stage_umask,
    arm_development_parent_death, bind_mount, mount_first_stage_runtime_filesystems, mount_tmpfs,
    owned_process::OwnedNamespaceChild, project_cpu_sysfs_with, publish_render_node_sysfs_metadata,
};
use super::*;
use std::fs;
use std::os::unix::fs::{PermissionsExt, symlink};
use std::os::unix::net::{UnixListener, UnixStream};
use std::os::unix::process::CommandExt;
use std::process::{Child, Command, ExitStatus, Stdio};
use std::thread;
use std::time::{Duration, Instant};

const FIXTURE: &str = "development::guest_dirs::tests::private_namespace_fixture";
const CLIENT: &str = "development::guest_dirs::tests::unprivileged_socket_fixture";
const GUEST_EXEC: &str = "development::guest_dirs::tests::android_second_stage_umask_fixture";
const ENV: &str = "DROIDLOOM_GUEST_DIRECTORY_TEST_ROOT";

fn mode(path: &Path) -> u32 {
    fs::metadata(path).unwrap().permissions().mode() & 0o7777
}

#[test]
fn creates_explicit_modes_without_changing_existing_directories() {
    let directory = tempfile::tempdir().unwrap();
    fs::set_permissions(directory.path(), fs::Permissions::from_mode(0o700)).unwrap();
    create_under(directory.path(), Path::new("socket/droidloom")).unwrap();
    assert_eq!(mode(directory.path()), 0o700);
    assert_eq!(mode(&directory.path().join("socket")), 0o755);
    assert_eq!(mode(&directory.path().join("socket/droidloom")), 0o755);
    fs::set_permissions(
        directory.path().join("socket"),
        fs::Permissions::from_mode(0o700),
    )
    .unwrap();
    create_under(directory.path(), Path::new("socket/droidloom/new")).unwrap();
    assert_eq!(mode(&directory.path().join("socket")), 0o700);
    assert_eq!(mode(&directory.path().join("socket/droidloom/new")), 0o755);
}

#[test]
fn rejects_escape_symlink_and_non_directory_without_changing_targets() {
    let directory = tempfile::tempdir().unwrap();
    let outside = tempfile::tempdir().unwrap();
    fs::set_permissions(outside.path(), fs::Permissions::from_mode(0o700)).unwrap();
    symlink(outside.path(), directory.path().join("link")).unwrap();
    fs::write(directory.path().join("file"), b"unchanged").unwrap();
    for relative in ["../outside", "/absolute", "link/new", "file/new"] {
        assert!(create_under(directory.path(), Path::new(relative)).is_err());
    }
    assert_eq!(mode(outside.path()), 0o700);
    assert!(!outside.path().join("new").exists());
    assert_eq!(
        fs::read(directory.path().join("file")).unwrap(),
        b"unchanged"
    );
}

struct OwnedChild(Child);

impl Drop for OwnedChild {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

fn wait_owned(child: &mut Child) -> ExitStatus {
    let deadline = Instant::now() + Duration::from_secs(10);
    loop {
        if let Some(status) = child.try_wait().unwrap() {
            return status;
        }
        assert!(Instant::now() < deadline, "owned fixture deadline exceeded");
        thread::sleep(Duration::from_millis(5));
    }
}

fn fixture_arguments(command: &mut Command, test: &str, directory: &Path) {
    command
        .args([
            "--exact",
            test,
            "--ignored",
            "--nocapture",
            "--test-threads=1",
        ])
        .env(ENV, directory)
        .stdin(Stdio::null());
}

fn run_client(directory: &Path, expected: &str) {
    let mut command = Command::new(std::env::current_exe().unwrap());
    fixture_arguments(&mut command, CLIENT, directory);
    command.env("DROIDLOOM_GUEST_DIRECTORY_EXPECT", expected);
    // Only this owned fixture loses groups and credentials. No host account
    // or Android UID map is created or modified by the control.
    unsafe {
        command.pre_exec(|| {
            if libc::setgroups(0, std::ptr::null()) != 0
                || libc::setgid(1000) != 0
                || libc::setuid(1000) != 0
            {
                return Err(io::Error::last_os_error());
            }
            Ok(())
        });
    }
    let mut owned = OwnedChild(command.spawn().unwrap());
    assert!(wait_owned(&mut owned.0).success());
}

#[test]
#[ignore = "private UID1000 entry for the explicitly selected namespace control"]
fn unprivileged_socket_fixture() {
    assert_eq!(unsafe { libc::geteuid() }, 1000);
    assert_eq!(unsafe { libc::getegid() }, 1000);
    assert_eq!(unsafe { libc::getgroups(0, std::ptr::null_mut()) }, 0);
    let directory = PathBuf::from(std::env::var_os(ENV).unwrap());
    let expected = std::env::var("DROIDLOOM_GUEST_DIRECTORY_EXPECT").unwrap();
    let guest = directory.join("guest");
    if expected == "old-denied" {
        let error = UnixStream::connect(guest.join("old/socket/property_service")).unwrap_err();
        assert_eq!(error.raw_os_error(), Some(libc::EACCES));
        assert_eq!(
            fs::read(guest.join("old/__properties__/property_info"))
                .unwrap_err()
                .raw_os_error(),
            Some(libc::EACCES)
        );
        return;
    }
    if expected == "guest-properties-accessible" {
        assert_eq!(mode(&guest.join("dev/__properties__")), 0o711);
        assert_eq!(mode(&guest.join("dev/__properties__/property_info")), 0o444);
        assert_eq!(
            fs::read(guest.join("dev/__properties__/property_info")).unwrap(),
            b"property-info-fixture\n"
        );
        let _connection =
            UnixStream::connect(guest.join("dev/socket/property_service_after_exec")).unwrap();
        assert_eq!(
            fs::read(directory.join("control/private"))
                .unwrap_err()
                .raw_os_error(),
            Some(libc::EACCES)
        );
        return;
    }
    assert_eq!(expected, "new-accessible");
    let _connection = UnixStream::connect(guest.join("dev/socket/property_service")).unwrap();
    for relative in [
        "dev/pts",
        "dev/binderfs",
        "dev/block",
        "dev/dri",
        "dev/dma_heap",
        "dev/socket/droidloom",
        "sys/fs/cgroup",
        "sys/fs/bpf",
        "sys/fs/fuse/connections",
        "sys/dev/char/226:128/device/drm/renderD128",
        "sys/bus/platform",
        "mnt/vendor",
        "mnt/product",
    ] {
        assert_eq!(mode(&guest.join(relative)), 0o755, "{relative}");
        fs::read_dir(guest.join(relative)).unwrap();
    }
    for name in ["online", "possible", "present"] {
        assert!(
            !fs::read_to_string(guest.join("sys/devices/system/cpu").join(name))
                .unwrap()
                .trim()
                .is_empty()
        );
    }
    assert_eq!(
        fs::read_to_string(guest.join("sys/dev/char/226:128/device/uevent")).unwrap(),
        "DRIVER=directory-mode-fixture\n"
    );
    assert_eq!(
        fs::read(directory.join("control/private"))
            .unwrap_err()
            .raw_os_error(),
        Some(libc::EACCES)
    );
}

#[test]
#[ignore = "private PID1 entry for the explicitly selected namespace control"]
fn private_namespace_fixture() {
    assert_eq!(unsafe { libc::geteuid() }, 0);
    assert_eq!(unsafe { libc::getpid() }, 1);
    let directory = PathBuf::from(std::env::var_os(ENV).unwrap());
    // This process is already in new private namespaces. Do not change the
    // test runner's process-wide umask or mount anything in its namespace.
    unsafe { libc::umask(0o077) };
    let guest = directory.join("guest");
    mount_tmpfs(&guest, "mode=0755,nosuid,nodev,size=8m").unwrap();
    for name in [
        "dev",
        "sys",
        "mnt",
        "debug_ramdisk",
        "second_stage_resources",
    ] {
        create_under(&guest, Path::new(name)).unwrap();
    }
    device_directories(&guest.join("dev")).unwrap();
    create_under(&guest.join("dev"), Path::new("dma_heap")).unwrap();
    sysfs_mount_points(&guest.join("sys")).unwrap();
    project_cpu_sysfs_with(
        Path::new("/sys/devices/system/cpu"),
        &guest.join("sys"),
        bind_mount,
    )
    .unwrap();
    // Test the production metadata publisher with declared fixture data, not
    // a claim about an actual graphics device or Android graphics readiness.
    publish_render_node_sysfs_metadata(
        &guest.join("sys"),
        &RenderNodeSysfsMetadata {
            major: 226,
            minor: 128,
            node_name: "renderD128".into(),
            subsystem: "platform".into(),
            uevent: "DRIVER=directory-mode-fixture\n".into(),
            pci_identity: None,
        },
    )
    .unwrap();
    mount_first_stage_runtime_filesystems(&guest).unwrap();

    fs::create_dir_all(guest.join("old/socket")).unwrap();
    let _old = UnixListener::bind(guest.join("old/socket/property_service")).unwrap();
    fs::set_permissions(
        guest.join("old/socket/property_service"),
        fs::Permissions::from_mode(0o666),
    )
    .unwrap();
    assert_eq!(mode(&guest.join("old/socket")), 0o700);
    let old_properties =
        CString::new(guest.join("old/__properties__").as_os_str().as_bytes()).unwrap();
    assert_eq!(unsafe { libc::mkdir(old_properties.as_ptr(), 0o711) }, 0);
    fs::write(
        guest.join("old/__properties__/property_info"),
        b"property-info-fixture\n",
    )
    .unwrap();
    fs::set_permissions(
        guest.join("old/__properties__/property_info"),
        fs::Permissions::from_mode(0o444),
    )
    .unwrap();
    assert_eq!(mode(&guest.join("old/__properties__")), 0o700);
    run_client(&directory, "old-denied");

    let listener = UnixListener::bind(guest.join("dev/socket/property_service")).unwrap();
    fs::set_permissions(
        guest.join("dev/socket/property_service"),
        fs::Permissions::from_mode(0o666),
    )
    .unwrap();
    run_client(&directory, "new-accessible");
    listener.set_nonblocking(true).unwrap();
    let _accepted = listener.accept().unwrap();

    // An existing host bind must not be chmodded or traversed into by the
    // helper. The private tmpfs and original host filesystem differ here.
    let bound = create_under(&guest, Path::new("host-bind")).unwrap();
    bind_mount(&directory.join("host-source"), &bound, true).unwrap();
    assert_eq!(
        create_under(&guest, Path::new("host-bind/new"))
            .unwrap_err()
            .kind(),
        io::ErrorKind::PermissionDenied
    );
    assert_eq!(mode(&directory.join("host-source")), 0o700);
    assert!(!directory.join("host-source/new").exists());
    assert_eq!(unsafe { libc::umask(0o077) }, 0o077);
    fs::write(directory.join("control/after"), b"private\n").unwrap();
    assert_eq!(mode(&directory.join("control/after")), 0o600);
    fs::write(
        directory.join("ready"),
        b"old-EACCES;new-UID1000-connect;CPU-readable;host-bind-unchanged;umask-0077\n",
    )
    .unwrap();
    let deadline = Instant::now() + Duration::from_secs(10);
    while !directory.join("release").exists() {
        assert!(
            Instant::now() < deadline,
            "parent did not release owned fixture"
        );
        thread::sleep(Duration::from_millis(5));
    }
    let mut init = Command::new(std::env::current_exe().unwrap());
    fixture_arguments(&mut init, GUEST_EXEC, &directory);
    arm_android_first_stage_umask(&mut init);
    panic!("guest fixture exec failed: {}", init.exec());
}

#[test]
fn guest_umask_hook_rejects_non_pid1_children() {
    let before = fs::read_to_string("/proc/self/status").unwrap();
    let before = before
        .lines()
        .find(|line| line.starts_with("Umask:"))
        .unwrap();
    let mut command = Command::new("/usr/bin/true");
    arm_android_first_stage_umask(&mut command);
    assert_eq!(
        command.spawn().unwrap_err().kind(),
        io::ErrorKind::InvalidInput
    );
    let after = fs::read_to_string("/proc/self/status").unwrap();
    assert_eq!(
        after
            .lines()
            .find(|line| line.starts_with("Umask:"))
            .unwrap(),
        before
    );
}

#[test]
#[ignore = "private post-exec PID1 entry for the explicitly selected namespace control"]
fn android_second_stage_umask_fixture() {
    assert_eq!(unsafe { libc::getpid() }, 1);
    assert_eq!(
        unsafe { libc::umask(0) },
        0,
        "actual exec must inherit Android first-stage umask"
    );
    let directory = PathBuf::from(std::env::var_os(ENV).unwrap());
    let guest = directory.join("guest");
    let properties = CString::new(guest.join("dev/__properties__").as_os_str().as_bytes()).unwrap();
    // Same mkdir mode as bionic ContextsSerialized::Initialize. No chmod of
    // the directory may conceal a failure to restore the actual guest umask.
    assert_eq!(unsafe { libc::mkdir(properties.as_ptr(), 0o711) }, 0);
    assert_eq!(mode(&guest.join("dev/__properties__")), 0o711);
    fs::write(
        guest.join("dev/__properties__/property_info"),
        b"property-info-fixture\n",
    )
    .unwrap();
    fs::set_permissions(
        guest.join("dev/__properties__/property_info"),
        fs::Permissions::from_mode(0o444),
    )
    .unwrap();
    let listener =
        UnixListener::bind(guest.join("dev/socket/property_service_after_exec")).unwrap();
    fs::set_permissions(
        guest.join("dev/socket/property_service_after_exec"),
        fs::Permissions::from_mode(0o666),
    )
    .unwrap();
    run_client(&directory, "guest-properties-accessible");
    listener.set_nonblocking(true).unwrap();
    let _accepted = listener.accept().unwrap();
    println!(
        "{{\"actual_pid1_exec\":true,\"guest_umask_0000\":true,\"bionic_property_directory_mode\":\"0711\",\"uid1000_property_info_read\":true,\"uid1000_post_exec_socket_connect\":true}}"
    );
}

#[test]
#[ignore = "requires root and actual private Linux namespaces; no Android inputs"]
fn actual_restrictive_umask_namespace_directory_access() {
    assert_eq!(unsafe { libc::geteuid() }, 0);
    let host_status = fs::read_to_string("/proc/self/status").unwrap();
    let host_umask = host_status
        .lines()
        .find(|line| line.starts_with("Umask:"))
        .unwrap();
    let names = ["mnt", "pid", "cgroup", "ipc", "uts"];
    let before: Vec<_> = names
        .iter()
        .map(|name| fs::read_link(format!("/proc/self/ns/{name}")).unwrap())
        .collect();
    let directory = tempfile::tempdir().unwrap();
    fs::set_permissions(directory.path(), fs::Permissions::from_mode(0o755)).unwrap();
    fs::create_dir(directory.path().join("guest")).unwrap();
    for name in ["control", "host-source"] {
        fs::create_dir(directory.path().join(name)).unwrap();
        fs::set_permissions(
            directory.path().join(name),
            fs::Permissions::from_mode(0o700),
        )
        .unwrap();
    }
    fs::write(directory.path().join("control/private"), b"private\n").unwrap();
    fs::set_permissions(
        directory.path().join("control/private"),
        fs::Permissions::from_mode(0o600),
    )
    .unwrap();
    let host_before = fs::metadata(directory.path().join("host-source")).unwrap();
    let mut command = Command::new("/usr/bin/unshare");
    command
        .args(DEVELOPMENT_UNSHARE_ARGUMENTS)
        .arg(std::env::current_exe().unwrap());
    fixture_arguments(&mut command, FIXTURE, directory.path());
    arm_development_parent_death(&mut command);
    let mut owner = OwnedChild(command.spawn().unwrap());
    let init = OwnedNamespaceChild::capture(&mut owner.0, Duration::from_secs(5)).unwrap();
    let deadline = Instant::now() + Duration::from_secs(15);
    while !directory.path().join("ready").exists() {
        assert!(
            owner.0.try_wait().unwrap().is_none(),
            "namespace control failed"
        );
        assert!(Instant::now() < deadline, "namespace control timed out");
        thread::sleep(Duration::from_millis(5));
    }
    let child_list =
        fs::read_to_string(format!("/proc/{0}/task/{0}/children", owner.0.id())).unwrap();
    let children: Vec<_> = child_list.split_ascii_whitespace().collect();
    assert_eq!(children.len(), 1);
    for (name, original) in names.iter().zip(&before) {
        assert_ne!(
            fs::read_link(format!("/proc/{}/ns/{name}", children[0])).unwrap(),
            *original
        );
        assert_eq!(
            fs::read_link(format!("/proc/self/ns/{name}")).unwrap(),
            *original
        );
    }
    let outer_pid = owner.0.id();
    fs::write(directory.path().join("release"), b"release\n").unwrap();
    assert!(wait_owned(&mut owner.0).success());
    init.retire_after_owner_reaped().unwrap();
    assert!(init.exited().unwrap());
    assert!(!Path::new(&format!("/proc/{outer_pid}")).exists());
    assert!(
        fs::read_dir(directory.path().join("guest"))
            .unwrap()
            .next()
            .is_none()
    );
    let host_after = fs::metadata(directory.path().join("host-source")).unwrap();
    assert_eq!(
        (host_before.dev(), host_before.ino(), host_before.mode()),
        (host_after.dev(), host_after.ino(), host_after.mode())
    );
    assert!(!directory.path().join("host-source/new").exists());
    assert_eq!(mode(&directory.path().join("control")), 0o700);
    assert_eq!(mode(&directory.path().join("control/private")), 0o600);
    let host_after = fs::read_to_string("/proc/self/status").unwrap();
    assert_eq!(
        host_after
            .lines()
            .find(|line| line.starts_with("Umask:"))
            .unwrap(),
        host_umask
    );
    println!(
        "{{\"umask_0077\":true,\"old_parent_connect_errno\":13,\"uid1000_new_socket_connect\":true,\"cpu_files_readable\":3,\"host_control_private\":true,\"host_bind_unchanged\":true,\"private_namespaces\":5,\"owned_owner_reaped\":true,\"bound_init_exited\":true,\"android_inputs_used\":false}}"
    );
}
