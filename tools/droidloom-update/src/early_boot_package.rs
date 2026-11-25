//! Build and stage the board-parent custody archive and ordinary Ubuntu initramfs hooks.
use crate::util::*;
#[path = "maintenance_package.rs"]
mod maintenance_package;
use std::{fs, path::Path, process::Command};

// Both the packaged bytes and the C PID 1 consumer are projected from this
// committed input. Never duplicate these pins in the C source or accept an
// uncommitted caller-supplied header.
const BOARD_INPUTS: &[u8] = include_bytes!(
    "../../../android/framework/droidloom-readiness/board-policy/pocket4-board-inputs.lock.json"
);

#[derive(serde::Deserialize)]
struct AppArmorProfileInput {
    size: u64,
    source_sha256: String,
    compiled_sha256: String,
    kernel_profile_sha256: String,
}

#[derive(serde::Deserialize)]
struct ReleaseInput {
    size: u64,
    sha256: String,
    #[serde(default)]
    active_sources: Option<u32>,
    #[serde(default)]
    board_profile_order: Vec<String>,
    #[serde(default)]
    board_profiles: std::collections::BTreeMap<String, AppArmorProfileInput>,
}

// Preserve the original first six roles and append only the selected hardware
// helper. The committed lock owns the serialized order; this is its closed set.
const APPARMOR_BOARD_ROLES: [&str; 8] = [
    "droidloom-ubuntu-journald",
    "droidloom-policy-loader",
    "droidloom-production-android",
    "droidloom-production-broker",
    "droidloom-instance-launcher",
    "droidloom-instance-factory",
    "droidloom-native-hardware-label",
    "droidloom-camera-capture",
];

fn sha256_text(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

#[derive(serde::Deserialize)]
struct KernelInput {
    release: String,
}

#[derive(serde::Deserialize)]
struct BoardInputs {
    native_init: droidloom_contracts::native_init::NativeInit,
    kernel: KernelInput,
    files: std::collections::BTreeMap<String, ReleaseInput>,
}

fn committed_board_inputs() -> Result<BoardInputs> {
    parse_board_inputs(BOARD_INPUTS)
}

fn parse_board_inputs(bytes: &[u8]) -> Result<BoardInputs> {
    let lock: BoardInputs = serde_json::from_slice(bytes)?;
    lock.native_init.validate()?;
    let release = lock.kernel.release.as_bytes();
    if release.is_empty()
        || release.len() > 64
        || !release
            .iter()
            .all(|b| b.is_ascii_alphanumeric() || b"._+-".contains(b))
    {
        return fail("board lock has an unsafe or unsupported kernel release");
    }
    for name in ["joint.policy", "ubuntu-apparmor.profiles"] {
        let input = lock
            .files
            .get(name)
            .ok_or("board input absent from release lock")?;
        if input.size == 0
            || input.size > 64 * 1024 * 1024
            || input.sha256.len() != 64
            || !input
                .sha256
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        {
            return fail(format!("invalid bounded board input pin for {name}"));
        }
    }
    let aa = &lock.files["ubuntu-apparmor.profiles"];
    let ubuntu = aa
        .active_sources
        .ok_or("AppArmor Ubuntu source count is absent")?;
    if ubuntu == 0
        || ubuntu > 4096
        || !aa
            .board_profile_order
            .iter()
            .map(String::as_str)
            .eq(APPARMOR_BOARD_ROLES.iter().copied())
        || aa.board_profiles.len() != APPARMOR_BOARD_ROLES.len()
    {
        return fail(
            "AppArmor lock must preserve the bounded Ubuntu prefix and eight ordered board roles",
        );
    }
    for name in &aa.board_profile_order {
        let role = aa
            .board_profiles
            .get(name)
            .ok_or("ordered AppArmor role is absent")?;
        if role.size == 0
            || role.size > 64 * 1024 * 1024
            || !sha256_text(&role.source_sha256)
            || !sha256_text(&role.compiled_sha256)
            || !sha256_text(&role.kernel_profile_sha256)
        {
            return fail(format!("invalid bounded AppArmor role pin for {name}"));
        }
    }
    Ok(lock)
}

fn board_policy_header(lock: &BoardInputs) -> String {
    let policy = &lock.files["joint.policy"];
    let aa = &lock.files["ubuntu-apparmor.profiles"];
    let ubuntu = aa.active_sources.expect("validated AppArmor prefix");
    let mut header = format!(
        concat!(
            "/* Generated from the committed pocket4-board-inputs.lock.json. */\n",
            "#ifndef DROIDLOOM_BOARD_POLICY_INPUTS_H\n",
            "#define DROIDLOOM_BOARD_POLICY_INPUTS_H\n",
            "#define DROIDLOOM_BOARD_KERNEL_RELEASE \"{}\"\n",
            "#define DROIDLOOM_BOARD_SELINUX_SIZE {}ULL\n",
            "#define DROIDLOOM_BOARD_SELINUX_SHA256 \"{}\"\n",
            "#define DROIDLOOM_BOARD_APPARMOR_SIZE {}ULL\n",
            "#define DROIDLOOM_BOARD_APPARMOR_SHA256 \"{}\"\n",
            "#define DROIDLOOM_BOARD_APPARMOR_UBUNTU_ENTRIES {}U\n",
            "#define DROIDLOOM_BOARD_APPARMOR_BOARD_ENTRIES {}U\n",
            "#define DROIDLOOM_BOARD_APPARMOR_PROFILE_ENTRIES {}U\n",
        ),
        lock.kernel.release,
        policy.size,
        policy.sha256,
        aa.size,
        aa.sha256,
        ubuntu,
        aa.board_profile_order.len(),
        ubuntu as usize + aa.board_profile_order.len(),
    );
    header.push_str(&format!(
        "#define DROIDLOOM_BOARD_NATIVE_INIT_PATH \"{}\"\n#define DROIDLOOM_BOARD_NATIVE_INIT_SIZE {}ULL\n#define DROIDLOOM_BOARD_NATIVE_INIT_SHA256 {}\n",
        lock.native_init.path, lock.native_init.size,
        lock.native_init.sha256_c_initializer().expect("validated native manager digest"),
    ));
    for (symbol, name) in [
        ("LOADER", "droidloom-policy-loader"),
        ("ANDROID", "droidloom-production-android"),
        ("BROKER", "droidloom-production-broker"),
        ("CAMERA", "droidloom-camera-capture"),
    ] {
        let index = aa
            .board_profile_order
            .iter()
            .position(|role| role == name)
            .expect("validated epoch role");
        header.push_str(&format!(
            "#define DROIDLOOM_BOARD_APPARMOR_EPOCH_{symbol}_INDEX {}U\n",
            ubuntu as usize + index,
        ));
    }
    let loader = aa.board_profile_order.iter().position(|r| r == "droidloom-policy-loader").unwrap();
    let camera = aa.board_profile_order.iter().position(|r| r == "droidloom-camera-capture").unwrap();
    // Original independently admitted loader birth 164 anchors the same ordered
    // raw loads. The camera generation is derived rather than another index list.
    let birth = 164usize.checked_sub(loader).and_then(|v| v.checked_add(camera)).unwrap();
    header.push_str(&format!("#define DROIDLOOM_BOARD_APPARMOR_CAMERA_RAW_BIRTH {birth}U\n"));
    header.push_str(concat!(
        "struct droidloom_board_apparmor_profile {\n",
        "    const char *name; unsigned long long size;\n",
        "    const char *compiled_sha256; const char *kernel_sha256;\n",
        "};\n",
        "static const struct droidloom_board_apparmor_profile ",
        "droidloom_board_apparmor_profiles[DROIDLOOM_BOARD_APPARMOR_BOARD_ENTRIES] = {\n",
    ));
    for name in &aa.board_profile_order {
        let role = &aa.board_profiles[name];
        header.push_str(&format!(
            "    {{\"{}\", {}ULL, \"{}\", \"{}\"}},\n",
            name, role.size, role.compiled_sha256, role.kernel_profile_sha256,
        ));
    }
    header.push_str("};\n#endif\n");
    header
}

pub(super) fn stage_board_policy(inputs: &Path, destination: &Path) -> Result<()> {
    let release = destination.join("usr/lib/droidloom/production/current/board-policy");
    let lock = committed_board_inputs()?;
    for name in ["joint.policy", "ubuntu-apparmor.profiles"] {
        let input = lock
            .files
            .get(name)
            .ok_or("board input absent from release lock")?;
        let body = crate::coherent_images::read_release_input(
            &inputs.join(name),
            input.size,
            &input.sha256,
        )?;
        let path = release.join(name);
        write(&path, &body)?;
        mode(&path, 0o444)?;
        if name == "joint.policy" {
            // The verified binary policy header carries the version used by libselinux.
            if body.get(..16) != Some(&b"\x8c\xff\x7c\xf9\x08\0\0\0SE Linux"[..]) {
                return fail("selected joint policy has an unsupported binary header");
            }
            let version = u32::from_le_bytes(
                body.get(16..20)
                    .ok_or("truncated SELinux policy version")?
                    .try_into()?,
            );
            let policy = destination.join(format!("etc/selinux/droidloom/policy/policy.{version}"));
            write(&policy, &body)?;
            mode(&policy, 0o444)?;
        }
    }
    stage_native_configuration(destination)
}

// Shared by the normal board-policy publisher and its package contract check.
pub(super) fn stage_native_configuration(destination: &Path) -> Result<()> {
    let config = destination.join("etc/selinux/config");
    write(
        &config,
        include_bytes!(
            "../../../android/framework/droidloom-readiness/board-policy/ubuntu-selinux-config"
        ),
    )?;
    mode(&config, 0o444)?;
    // Stock D-Bus requires its include, and stock pam_selinux resolves the
    // admitted login accounts and caller domains through these public files.
    // Unexpected users/callers have no generic or failsafe context mapping.
    for (relative, body) in [
        (
            "etc/selinux/droidloom/contexts/dbus_contexts",
            include_bytes!("../../../android/framework/droidloom-readiness/board-policy/ubuntu-dbus_contexts").as_slice(),
        ),
        (
            "etc/selinux/droidloom/seusers",
            include_bytes!("../../../android/framework/droidloom-readiness/board-policy/ubuntu-seusers").as_slice(),
        ),
        (
            "etc/selinux/droidloom/contexts/default_contexts",
            include_bytes!("../../../android/framework/droidloom-readiness/board-policy/ubuntu-default_contexts").as_slice(),
        ),
        (
            "etc/systemd/system/user-runtime-dir@.service.d/50-droidloom-native-session.conf",
            include_bytes!("../../../android/framework/droidloom-readiness/board-policy/ubuntu-user-runtime-dir.conf").as_slice(),
        ),
        (
            "usr/lib/udev/rules.d/00-droidloom-native-hardware.rules",
            include_bytes!("../../../android/framework/droidloom-readiness/board-policy/00-droidloom-native-hardware.rules").as_slice(),
        ),
        (
            "usr/lib/systemd/system/systemd-udevd.service.d/50-droidloom-hardware-label.conf",
            include_bytes!("../../../android/framework/droidloom-readiness/board-policy/ubuntu-udev-hardware-label.conf").as_slice(),
        ),
    ] {
        let path = destination.join(relative);
        write(&path, body)?;
        mode(&path, 0o444)?;
    }
    let contexts = destination.join("etc/selinux/droidloom/contexts/files/file_contexts");
    let rules = [
        include_bytes!("../../../android/framework/droidloom-readiness/board-policy/ubuntu-native-file_contexts").as_slice(),
        include_bytes!("../../../android/framework/droidloom-readiness/board-policy/ubuntu-real-root-file_contexts").as_slice(),
        include_bytes!("../../../android/framework/droidloom-readiness/board-policy/linux-service-file_contexts").as_slice(),
        include_bytes!("../../../android/framework/droidloom-readiness/board-policy/linux-initial-calibration-file_contexts").as_slice(),
    ].concat();
    write(&contexts, rules)?;
    mode(&contexts, 0o444)?;
    Ok(())
}

pub(super) fn stage(destination: &Path) -> Result<()> {
    let work = tempfile::tempdir()?;
    let src = work.path();
    let lock = committed_board_inputs()?;
    fs::write(
        src.join("board_policy_inputs.h"),
        board_policy_header(&lock),
    )?;
    fs::write(
        src.join("board.h"),
        include_bytes!("../../../runtime/droidloom-early-boot/board.h"),
    )?;
    fs::write(
        src.join("custody.h"),
        include_bytes!("../../../runtime/droidloom-early-boot/custody.h"),
    )?;
    fs::write(
        src.join("custody.c"),
        include_bytes!("../../../runtime/droidloom-early-boot/custody.c"),
    )?;
    fs::write(
        src.join("selected.c"),
        include_bytes!("../../../runtime/droidloom-early-boot/selected.c"),
    )?;
    for (name, content) in [
        (
            "boot_diagnostics.h",
            include_bytes!("../../../runtime/droidloom-early-boot/boot_diagnostics.h").as_slice(),
        ),
        (
            "boot_diagnostics.c",
            include_bytes!("../../../runtime/droidloom-early-boot/boot_diagnostics.c").as_slice(),
        ),
        (
            "device_source.h",
            include_bytes!("../../../runtime/droidloom-early-boot/device_source.h").as_slice(),
        ),
        (
            "device_template.h",
            include_bytes!("../../../runtime/droidloom-early-boot/device_template.h").as_slice(),
        ),
        (
            "device_template.c",
            include_bytes!("../../../runtime/droidloom-early-boot/device_template.c").as_slice(),
        ),
        (
            "device_source.c",
            include_bytes!("../../../runtime/droidloom-early-boot/device_source.c").as_slice(),
        ),
        (
            "apparmor_epoch.c",
            include_bytes!("../../../runtime/droidloom-early-boot/apparmor_epoch.c").as_slice(),
        ),
        (
            "apparmor_epoch.h",
            include_bytes!("../../../runtime/droidloom-early-boot/apparmor_epoch.h").as_slice(),
        ),
        (
            "board_policy.c",
            include_bytes!("../../../runtime/droidloom-early-boot/board_policy.c").as_slice(),
        ),
        (
            "board_policy.h",
            include_bytes!("../../../runtime/droidloom-early-boot/board_policy.h").as_slice(),
        ),
        (
            "board_init.c",
            include_bytes!("../../../runtime/droidloom-early-boot/board_init.c").as_slice(),
        ),
        (
            "board_resources.h",
            include_bytes!("../../../runtime/droidloom-early-boot/board_resources.h").as_slice(),
        ),
        (
            "board_cgroup.h",
            include_bytes!("../../../runtime/droidloom-early-boot/board_cgroup.h").as_slice(),
        ),
        (
            "board_binder.h",
            include_bytes!("../../../runtime/droidloom-early-boot/board_binder.h").as_slice(),
        ),
        (
            "board_resources.c",
            include_bytes!("../../../runtime/droidloom-early-boot/board_resources.c").as_slice(),
        ),
        (
            "firststage.c",
            include_bytes!("../../../runtime/droidloom-early-boot/firststage.c").as_slice(),
        ),
    ] {
        fs::write(src.join(name), content)?;
    }
    fs::write(
        src.join("linux_run_label.c"),
        include_bytes!("../../../runtime/droidloom-early-boot/linux_run_label.c"),
    )?;
    fs::write(
        src.join("linux_run_label.h"),
        include_bytes!("../../../runtime/droidloom-early-boot/linux_run_label.h"),
    )?;
    for (source, object) in [
        ("board_policy.c", "board_policy.o"),
        ("boot_diagnostics.c", "boot_diagnostics.o"),
        ("apparmor_epoch.c", "apparmor_epoch.o"),
        ("board_init.c", "board_init.o"),
        ("custody.c", "custody.o"),
        ("device_source.c", "device_source.o"),
        ("device_template.c", "device_template.o"),
        ("selected.c", "selected.o"),
        ("board_resources.c", "board_resources.o"),
        ("firststage.c", "firststage.o"),
        ("linux_run_label.c", "linux_run_label.o"),
    ] {
        let result = Command::new("cc")
            .current_dir(src)
            .args([
                "-std=c11", "-Os", "-fPIC", "-Wall", "-Wextra", "-Werror", "-c", source, "-o",
                object,
            ])
            .status()?;
        if !result.success() {
            return fail("cannot compile the board first-stage custody archive");
        }
    }
    let boot = "droidloom-early-firststage";
    let result = Command::new("cc")
        .current_dir(src)
        .args([
            "-Wl,-z,relro,-z,now",
            "firststage.o",
            "custody.o",
            "device_source.o",
            "device_template.o",
            "selected.o",
            "board_resources.o",
            "-lcrypto",
            "-o",
            boot,
        ])
        .status()?;
    if !result.success() {
        return fail("cannot link the original shared-kernel first-stage executable");
    }
    let binary = destination
        .join("usr/lib/droidloom/production/current")
        .join(boot);
    copy(&src.join(boot), &binary)?;
    mode(&binary, 0o755)?;
    let board_init = "droidloom-board-init";
    let linked = Command::new("cc")
        .current_dir(src)
        .args([
            "-Wl,-z,relro,-z,now",
            "board_init.o",
            "boot_diagnostics.o",
            "board_policy.o",
            "apparmor_epoch.o",
            "linux_run_label.o",
            "selected.o",
            "custody.o",
            "device_source.o",
            "device_template.o",
            "-lcrypto",
            "-o",
            board_init,
        ])
        .status()?;
    if !linked.success() {
        return fail("cannot link the selected shared-kernel board PID 1");
    }
    let path = destination
        .join("usr/lib/droidloom/production/current")
        .join(board_init);
    copy(&src.join(board_init), &path)?;
    mode(&path, 0o755)?;
    let result = Command::new("ar")
        .current_dir(src)
        .args([
            "rcsD",
            "libdroidloom_early_custody.a",
            "custody.o",
            "device_source.o",
            "device_template.o",
            "selected.o",
            "linux_run_label.o",
        ])
        .status()?;
    if !result.success() {
        return fail("cannot archive verified first-stage custody objects");
    }
    // The same resource handoff object is linkable by the late systemd broker.
    let archive = destination.join("usr/lib/droidloom/production/libdroidloom_early_custody.a");
    copy(&src.join("libdroidloom_early_custody.a"), &archive)?;
    mode(&archive, 0o644)?;
    for (name, bytes, permissions) in [
        (
            "usr/include/droidloom/early-custody.h",
            include_bytes!("../../../runtime/droidloom-early-boot/custody.h").as_slice(),
            0o644,
        ),
        (
            "usr/share/droidloom/board/ubuntu-real-root-devices",
            include_bytes!("../../../android/framework/droidloom-readiness/board-policy/ubuntu-real-root-devices").as_slice(),
            0o444,
        ),
        (
            "usr/share/droidloom/board/ubuntu-real-root-file_contexts",
            include_bytes!("../../../android/framework/droidloom-readiness/board-policy/ubuntu-real-root-file_contexts").as_slice(),
            0o444,
        ),
        (
            "usr/share/droidloom/board/ubuntu-native-file_contexts",
            include_bytes!("../../../android/framework/droidloom-readiness/board-policy/ubuntu-native-file_contexts").as_slice(),
            0o444,
        ),
        (
            "usr/share/initramfs-tools/hooks/droidloom-early-release",
            include_bytes!("../../../runtime/droidloom-early-boot/initramfs-hook").as_slice(),
            0o755,
        ),
        (
            "usr/share/initramfs-tools/scripts/init-bottom/droidloom-early-custody",
            include_bytes!("../../../runtime/droidloom-early-boot/init-bottom").as_slice(),
            0o755,
        ),
    ] {
        let path = destination.join(name);
        write(&path, bytes)?;
        mode(&path, permissions)?;
    }
    maintenance_package::stage(destination)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn committed_board_pins_reach_the_normally_compiled_pid_one() {
        let destination = tempfile::tempdir().unwrap();
        stage(destination.path()).unwrap();
        let elf = fs::read(
            destination
                .path()
                .join("usr/lib/droidloom/production/current/droidloom-board-init"),
        )
        .unwrap();
        assert_eq!(&elf[..4], b"\x7fELF");
        let lock = committed_board_inputs().unwrap();
        let native_digest = hex::decode(&lock.native_init.sha256).unwrap();
        assert!(elf.windows(32).any(|bytes| bytes == native_digest));
        for value in [
            lock.kernel.release.as_str(),
            lock.native_init.path.as_str(),
            lock.files["joint.policy"].sha256.as_str(),
            lock.files["ubuntu-apparmor.profiles"].sha256.as_str(),
        ] {
            let mut nul_terminated = value.as_bytes().to_vec();
            nul_terminated.push(0);
            assert!(
                elf.windows(nul_terminated.len())
                    .any(|bytes| bytes == nul_terminated),
                "compiled PID 1 omitted committed board input {value}"
            );
        }
    }

    #[test]
    fn malformed_board_locks_are_rejected_before_generating_c() {
        let original: serde_json::Value = serde_json::from_slice(BOARD_INPUTS).unwrap();
        for release in [
            "",
            "../kernel",
            "kernel\"\n#error injected",
            "kernel\\x00",
            &"k".repeat(65),
        ] {
            let mut value = original.clone();
            value["kernel"]["release"] = serde_json::json!(release);
            assert!(parse_board_inputs(&serde_json::to_vec(&value).unwrap()).is_err());
        }
        for name in ["joint.policy", "ubuntu-apparmor.profiles"] {
            for size in [0, 64 * 1024 * 1024 + 1, u64::MAX] {
                let mut value = original.clone();
                value["files"][name]["size"] = serde_json::json!(size);
                assert!(parse_board_inputs(&serde_json::to_vec(&value).unwrap()).is_err());
            }
            for hash in [
                "",
                "00",
                &"A".repeat(64),
                &"g".repeat(64),
                &format!("{}\"", "a".repeat(63)),
            ] {
                let mut value = original.clone();
                value["files"][name]["sha256"] = serde_json::json!(hash);
                assert!(parse_board_inputs(&serde_json::to_vec(&value).unwrap()).is_err());
            }
            let mut value = original.clone();
            value["files"].as_object_mut().unwrap().remove(name);
            assert!(parse_board_inputs(&serde_json::to_vec(&value).unwrap()).is_err());
        }
    }
    #[test]
    fn malformed_apparmor_role_layouts_are_rejected_before_generating_c() {
        let original: serde_json::Value = serde_json::from_slice(BOARD_INPUTS).unwrap();
        for count in [0_u64, 4097, u64::MAX] {
            let mut value = original.clone();
            value["files"]["ubuntu-apparmor.profiles"]["active_sources"] = serde_json::json!(count);
            assert!(parse_board_inputs(&serde_json::to_vec(&value).unwrap()).is_err());
        }
        for field in ["active_sources", "board_profile_order", "board_profiles"] {
            let mut value = original.clone();
            value["files"]["ubuntu-apparmor.profiles"]
                .as_object_mut()
                .unwrap()
                .remove(field);
            assert!(parse_board_inputs(&serde_json::to_vec(&value).unwrap()).is_err());
        }
        for mutation in 0..4 {
            let mut value = original.clone();
            let aa = &mut value["files"]["ubuntu-apparmor.profiles"];
            match mutation {
                0 => {
                    aa["board_profile_order"].as_array_mut().unwrap().pop();
                }
                1 => {
                    aa["board_profile_order"].as_array_mut().unwrap().swap(1, 2);
                }
                2 => {
                    aa["board_profile_order"][6] = serde_json::json!("droidloom-instance-factory");
                }
                _ => {
                    aa["board_profiles"]
                        .as_object_mut()
                        .unwrap()
                        .remove("droidloom-native-hardware-label");
                }
            }
            assert!(parse_board_inputs(&serde_json::to_vec(&value).unwrap()).is_err());
        }
        for field in ["source_sha256", "compiled_sha256", "kernel_profile_sha256"] {
            let mut value = original.clone();
            value["files"]["ubuntu-apparmor.profiles"]["board_profiles"]
                ["droidloom-native-hardware-label"][field] = serde_json::json!("bad");
            assert!(parse_board_inputs(&serde_json::to_vec(&value).unwrap()).is_err());
        }
    }

    #[test]
    #[ignore = "requires the exact admitted normal AppArmor archive in DROIDLOOM_TEST_APPARMOR_ARCHIVE"]
    fn admitted_apparmor_archive_reaches_original_epoch_roles() {
        let lock = committed_board_inputs().unwrap();
        let aa = &lock.files["ubuntu-apparmor.profiles"];
        let path = std::env::var_os("DROIDLOOM_TEST_APPARMOR_ARCHIVE")
            .expect("exact normal AppArmor archive path");
        let archive =
            crate::coherent_images::read_release_input(Path::new(&path), aa.size, &aa.sha256)
                .unwrap();
        let work = tempfile::tempdir().unwrap();
        let dir = work.path();
        fs::write(
            dir.join("board_policy_inputs.h"),
            board_policy_header(&lock),
        )
        .unwrap();
        fs::write(dir.join("archive"), archive).unwrap();
        for (name, source) in [
            (
                "board_policy.c",
                include_bytes!("../../../runtime/droidloom-early-boot/board_policy.c").as_slice(),
            ),
            (
                "board_policy.h",
                include_bytes!("../../../runtime/droidloom-early-boot/board_policy.h").as_slice(),
            ),
            (
                "apparmor_epoch.c",
                include_bytes!("../../../runtime/droidloom-early-boot/apparmor_epoch.c").as_slice(),
            ),
            (
                "apparmor_epoch.h",
                include_bytes!("../../../runtime/droidloom-early-boot/apparmor_epoch.h").as_slice(),
            ),
            (
                "boot_diagnostics.h",
                include_bytes!("../../../runtime/droidloom-early-boot/boot_diagnostics.h")
                    .as_slice(),
            ),
            (
                "linux_run_label.h",
                include_bytes!("../../../runtime/droidloom-early-boot/linux_run_label.h")
                    .as_slice(),
            ),
            (
                "device_source.h",
                include_bytes!("../../../runtime/droidloom-early-boot/device_source.h").as_slice(),
            ),
            (
                "device_template.h",
                include_bytes!("../../../runtime/droidloom-early-boot/device_template.h")
                    .as_slice(),
            ),
            (
                "board.h",
                include_bytes!("../../../runtime/droidloom-early-boot/board.h").as_slice(),
            ),
            (
                "custody.h",
                include_bytes!("../../../runtime/droidloom-early-boot/custody.h").as_slice(),
            ),
            (
                "apparmor_pack_test.c",
                include_bytes!("../../../runtime/droidloom-early-boot/tests/apparmor_pack_test.c")
                    .as_slice(),
            ),
            (
                "apparmor_role_fields_test.c",
                include_bytes!(
                    "../../../runtime/droidloom-early-boot/tests/apparmor_role_fields_test.c"
                )
                .as_slice(),
            ),
        ] {
            fs::write(dir.join(name), source).unwrap();
        }
        for source in ["apparmor_pack_test.c", "apparmor_role_fields_test.c"] {
            let elf = dir.join(source.trim_end_matches(".c"));
            let compile = Command::new("cc")
                .current_dir(dir)
                .args([
                    "-std=c11",
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-ffunction-sections",
                    "-fdata-sections",
                    source,
                    "-Wl,--gc-sections",
                    "-lcrypto",
                    "-o",
                ])
                .arg(&elf)
                .output()
                .unwrap();
            assert!(
                compile.status.success(),
                "{}",
                String::from_utf8_lossy(&compile.stderr)
            );
            let output = Command::new(&elf)
                .arg(dir.join("archive"))
                .output()
                .unwrap();
            assert!(
                output.status.success(),
                "stdout={} stderr={}",
                String::from_utf8_lossy(&output.stdout),
                String::from_utf8_lossy(&output.stderr)
            );
            println!("{}", String::from_utf8_lossy(&output.stdout));
        }
    }
}
