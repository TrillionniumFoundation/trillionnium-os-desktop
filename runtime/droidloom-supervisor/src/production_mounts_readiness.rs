use super::*;
use droidloom_contracts::system_ext::ReadinessDeclaration;
use std::fs;

fn directory_names(fd: &File) -> Result<BTreeSet<String>> {
    fs::read_dir(format!("/proc/self/fd/{}", fd.as_raw_fd()))?
        .map(|row| {
            row?.file_name()
                .into_string()
                .map_err(|_| MountError::Rejected("invalid readiness tree filename"))
        })
        .collect()
}

fn compare_original(
    src: &File,
    dst: &File,
    level: usize,
    count: &mut usize,
    extra: Option<&str>,
) -> Result<()> {
    require(level < 8 && *count < 128, "bounded factory system_ext tree")?;
    *count += 1;
    same_attributes(src, dst)?;
    if src.metadata()?.is_file() {
        require(
            src.metadata()?.len() == dst.metadata()?.len()
                && src.metadata()?.len() <= 8 * 1024 * 1024
                && digest(src)? == digest(dst)?,
            "original system_ext file differs",
        )?;
        return Ok(());
    }
    require(
        src.metadata()?.is_dir() && dst.metadata()?.is_dir(),
        "original system_ext directory",
    )?;
    let original = directory_names(src)?;
    let mut selected = directory_names(dst)?;
    if let Some(new) = extra {
        require(
            !original.contains(new) && selected.remove(new),
            "new readiness member would shadow factory content",
        )?;
    }
    require(
        original == selected,
        "system_ext directory membership changed",
    )?;
    for name in original {
        let component = text_name(&name)?;
        let left = open_leaf(src, &component, libc::O_RDONLY | libc::O_NONBLOCK)?;
        let right = open_leaf(dst, &component, libc::O_RDONLY | libc::O_NONBLOCK)?;
        compare_original(&left, &right, level + 1, count, None)?;
    }
    Ok(())
}

fn target(root: &File, index: usize) -> Result<File> {
    match index {
        0 => directory(root, "bin"),
        1 => directory(&directory(root, "etc")?, "init"),
        _ => Err(MountError::Rejected("unknown readiness subtree")),
    }
}

pub(in crate::production_mounts) fn verify(
    original_ext: &File,
    carrier: &File,
    decl: &ReadinessDeclaration,
) -> Result<()> {
    fixed_children(carrier, &["bin", "etc"])?;
    fixed_children(&directory(carrier, "etc")?, &["init"])?;
    for (index, (name, sibling, expected, mode, label)) in [
        (
            "droidloom-readiness",
            "hwservicemanager",
            decl.observer_sha256.as_str(),
            0o755,
            b"u:object_r:droidloom_readiness_exec:s0".as_slice(),
        ),
        (
            "droidloom-readiness.rc",
            "wificond.rc",
            decl.init_rc_sha256.as_str(),
            0o644,
            b"u:object_r:system_file:s0".as_slice(),
        ),
    ]
    .into_iter()
    .enumerate()
    {
        let src = target(original_ext, index)?;
        let dst = target(carrier, index)?;
        compare_original(&src, &dst, 0, &mut 0, Some(name))?;
        let reference = regular(&src, sibling)?.metadata()?;
        let added = regular(&dst, name)?;
        let meta = added.metadata()?;
        let attrs = image_attrs(&added)?;
        let actual = attrs
            .get(std::ffi::OsStr::new("security.selinux"))
            .ok_or(MountError::Rejected("readiness inode has no SELinux label"))?;
        require(
            attrs.len() == 1
                && actual.strip_suffix(&[0]).unwrap_or(actual) == label
                && (meta.uid(), meta.gid(), meta.mode() & 0o7777)
                    == (reference.uid(), reference.gid(), mode)
                && meta.len() <= 8 * 1024 * 1024
                && digest(&added)? == expected,
            "wrong selected readiness service body, owner, label or mode",
        )?;
    }
    Ok(())
}

pub(in crate::production_mounts) fn compose(
    system: &File,
    carrier: &File,
    decl: &ReadinessDeclaration,
) -> Result<()> {
    let platform = directory(&directory(system, "system")?, "system_ext")?;
    verify(&platform, carrier, decl)?;
    for index in 0..2 {
        let original = target(&platform, index)?;
        require(
            mount_id(&original)? == mount_id(system)?,
            "readiness target was already mounted",
        )?;
        let source = target(carrier, index)?;
        let raw = unsafe {
            libc::syscall(
                libc::SYS_open_tree,
                source.as_raw_fd(),
                c"".as_ptr(),
                1u32 | libc::O_CLOEXEC as u32 | libc::AT_EMPTY_PATH as u32,
            )
        };
        if raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let cloned = unsafe { File::from_raw_fd(raw as i32) };
        require_detached(&cloned)?;
        let rc = unsafe {
            libc::syscall(
                libc::SYS_move_mount,
                cloned.as_raw_fd(),
                c"".as_ptr(),
                original.as_raw_fd(),
                c"".as_ptr(),
                libc::MOVE_MOUNT_F_EMPTY_PATH | libc::MOVE_MOUNT_T_EMPTY_PATH,
            )
        };
        if rc != 0 {
            return Err(io::Error::last_os_error().into());
        }
        let actual = target(&platform, index)?;
        let (a, b) = (actual.metadata()?, source.metadata()?);
        require(
            (a.dev(), a.ino()) == (b.dev(), b.ino()) && mount_id(&actual)? == mount_id(&cloned)?,
            "readiness subtree did not land at the fixed original target",
        )?;
    }
    require_detached(system)?;
    Ok(())
}
