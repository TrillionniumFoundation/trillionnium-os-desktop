//! Build and stage the board-parent custody archive and ordinary Ubuntu initramfs hooks.
use crate::util::*;
use std::{fs, path::Path, process::Command};

pub(super) fn stage_board_policy(inputs: &Path, destination: &Path) -> Result<()> {
    let release = destination.join("usr/lib/droidloom/production/current/board-policy");
    #[derive(serde::Deserialize)]
    struct ReleaseInput {
        size: u64,
        sha256: String,
    }
    #[derive(serde::Deserialize)]
    struct BoardInputs {
        files: std::collections::BTreeMap<String, ReleaseInput>,
    }
    let lock: BoardInputs = serde_json::from_slice(include_bytes!(
        "../../../android/framework/droidloom-readiness/board-policy/pocket4-board-inputs.lock.json"
    ))?;
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
                body.get(16..20).ok_or("truncated SELinux policy version")?.try_into()?,
            );
            let policy = destination.join(format!("etc/selinux/droidloom/policy/policy.{version}"));
            write(&policy, &body)?;
            mode(&policy, 0o444)?;
        }
    }
    let config = destination.join("etc/selinux/config");
    write(
        &config,
        include_bytes!("../../../android/framework/droidloom-readiness/board-policy/ubuntu-selinux-config"),
    )?;
    mode(&config, 0o444)?;
    Ok(())
}

pub(super) fn stage(destination: &Path) -> Result<()> {
    let work = tempfile::tempdir()?;
    let src = work.path();
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
        ("device_source.h", include_bytes!("../../../runtime/droidloom-early-boot/device_source.h").as_slice()),
        ("device_source.c", include_bytes!("../../../runtime/droidloom-early-boot/device_source.c").as_slice()),
        ("apparmor_epoch.c", include_bytes!("../../../runtime/droidloom-early-boot/apparmor_epoch.c").as_slice()),
        ("apparmor_epoch.h", include_bytes!("../../../runtime/droidloom-early-boot/apparmor_epoch.h").as_slice()),
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
        ("apparmor_epoch.c", "apparmor_epoch.o"),
        ("board_init.c", "board_init.o"),
        ("custody.c", "custody.o"),
        ("device_source.c", "device_source.o"),
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
            "board_policy.o",
            "apparmor_epoch.o",
            "linux_run_label.o",
            "selected.o",
            "custody.o",
            "device_source.o",
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
    Ok(())
}
