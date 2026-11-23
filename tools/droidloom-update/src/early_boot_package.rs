//! Build and stage the board-parent custody archive and ordinary Ubuntu initramfs hooks.
use crate::util::*;
use std::{fs, path::Path, process::Command};

pub(super) fn stage(destination: &Path) -> Result<()> {
    let work = tempfile::tempdir()?;
    let src = work.path();
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
    for (source, object) in [("custody.c", "custody.o"), ("selected.c", "selected.o")] {
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
    let result = Command::new("ar")
        .current_dir(src)
        .args([
            "rcsD",
            "libdroidloom_early_custody.a",
            "custody.o",
            "selected.o",
        ])
        .status()?;
    if !result.success() {
        return fail("cannot archive verified first-stage custody objects");
    }
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
