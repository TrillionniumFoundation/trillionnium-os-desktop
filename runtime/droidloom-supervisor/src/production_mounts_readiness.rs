use super::*;
use droidloom_contracts::system_ext::{self as contract, ReadinessDeclaration};
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
    extras: &[&str],
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
    for &new in extras {
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
        compare_original(&left, &right, level + 1, count, &[])?;
    }
    Ok(())
}

fn target(root: &File, index: usize) -> Result<File> {
    match index {
        0 => directory(root, "bin"),
        1 => directory(&directory(root, "etc")?, "init"),
        2 => regular(
            &directory(&directory(root, "etc")?, "selinux")?,
            "system_ext_property_contexts",
        ),
        _ => Err(MountError::Rejected("unknown readiness mount target")),
    }
}

pub(in crate::production_mounts) fn verify(
    original_ext: &File,
    carrier: &File,
    decl: &ReadinessDeclaration,
) -> Result<()> {
    let shutdown = decl.shutdown_property_contexts_sha256.is_some();
    fixed_children(carrier, &["bin", "etc"])?;
    let etc = directory(carrier, "etc")?;
    if shutdown {
        fixed_children(&etc, &["init", "selinux"])?;
        fixed_children(
            &directory(&etc, "selinux")?,
            &["system_ext_property_contexts"],
        )?;
        let original = target(original_ext, 2)?;
        let selected = target(carrier, 2)?;
        same_attributes(&original, &selected)?;
        let meta = original.metadata()?;
        let factory_owner = original_ext.metadata()?;
        let attrs = image_attrs(&selected)?;
        let label = attrs.get(std::ffi::OsStr::new("security.selinux"));
        require(
            (meta.uid(), meta.gid(), meta.mode() & 0o7777)
                == (factory_owner.uid(), factory_owner.gid(), 0o644)
                && label.is_some_and(|value| {
                    value.strip_suffix(&[0]).unwrap_or(value)
                        == b"u:object_r:property_contexts_file:s0"
                })
                && meta.len() == 181
                && selected.metadata()?.len() < 512
                && digest(&original)? == contract::FACTORY_PROPERTY_CONTEXTS_SHA256
                && digest(&selected)? == contract::SHUTDOWN_PROPERTY_CONTEXTS_SHA256,
            "unrecognized factory or selected Android property contexts",
        )?;
    } else {
        fixed_children(&etc, &["init"])?;
    }
    let bins = target(carrier, 0)?;
    let factory_bins = target(original_ext, 0)?;
    let init = target(carrier, 1)?;
    let factory_init = target(original_ext, 1)?;
    let additions: &[&str] = if shutdown {
        &["droidloom-readiness", "droidloom-shutdown"]
    } else {
        &["droidloom-readiness"]
    };
    compare_original(&factory_bins, &bins, 0, &mut 0, additions)?;
    compare_original(&factory_init, &init, 0, &mut 0, &["droidloom-readiness.rc"])?;
    let elf_reference = regular(&factory_bins, "hwservicemanager")?.metadata()?;
    let rc_reference = regular(&factory_init, "wificond.rc")?.metadata()?;
    let mut elf_inode = None;
    for (dir, name, reference, expected, mode, label) in [
        (
            &bins,
            "droidloom-readiness",
            &elf_reference,
            &decl.observer_sha256,
            0o755,
            b"u:object_r:droidloom_readiness_exec:s0".as_slice(),
        ),
        (
            &init,
            "droidloom-readiness.rc",
            &rc_reference,
            &decl.init_rc_sha256,
            0o644,
            b"u:object_r:system_file:s0".as_slice(),
        ),
        (
            &bins,
            "droidloom-shutdown",
            &elf_reference,
            &decl.observer_sha256,
            0o755,
            b"u:object_r:droidloom_shutdown_exec:s0".as_slice(),
        ),
    ]
    .into_iter()
    .take(if shutdown { 3 } else { 2 })
    {
        let added = regular(dir, name)?;
        let meta = added.metadata()?;
        let attrs = image_attrs(&added)?;
        let actual =
            attrs
                .get(std::ffi::OsStr::new("security.selinux"))
                .ok_or(MountError::Rejected(
                    "missing selected Android service file label",
                ))?;
        require(
            attrs.len() == 1
                && actual.strip_suffix(&[0]).unwrap_or(actual) == label
                && (meta.uid(), meta.gid(), meta.mode() & 0o7777)
                    == (reference.uid(), reference.gid(), mode)
                && meta.len() <= 8 * 1024 * 1024
                && digest(&added)? == *expected,
            "wrong selected Android service body, owner, label or mode",
        )?;
        if mode == 0o755 {
            require(
                elf_inode.replace((meta.dev(), meta.ino())) != Some((meta.dev(), meta.ino())),
                "Android service entrypoints must have independent inodes",
            )?;
        }
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
    for index in 0..(2 + usize::from(decl.shutdown_property_contexts_sha256.is_some())) {
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
        if index == 2 {
            let flags = MountAttr {
                attr_set: libc::MOUNT_ATTR_NOEXEC as u64,
                attr_clr: 0,
                propagation: 0,
                userns_fd: 0,
            };
            zero_rc(unsafe {
                libc::syscall(
                    libc::SYS_mount_setattr,
                    cloned.as_raw_fd(),
                    c"".as_ptr(),
                    AT_EMPTY_PATH,
                    &flags,
                    std::mem::size_of::<MountAttr>(),
                )
            } as i32)?;
        }
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
        let mut mounted_flags: libc::statvfs = unsafe { std::mem::zeroed() };
        zero_rc(unsafe { libc::fstatvfs(actual.as_raw_fd(), &mut mounted_flags) })?;
        let expected = READONLY_FLAGS
            | if index == 2 {
                libc::ST_NOEXEC as u64
            } else {
                0
            };
        require(
            mounted_flags.f_flag as u64 & (READONLY_FLAGS | libc::ST_NOEXEC as u64) == expected,
            "selected service mount is missing its exact kernel restrictions",
        )?;
        let (a, b) = (actual.metadata()?, source.metadata()?);
        require(
            (a.dev(), a.ino()) == (b.dev(), b.ino()) && mount_id(&actual)? == mount_id(&cloned)?,
            "readiness subtree did not land at the fixed original target",
        )?;
    }
    require_detached(system)?;
    Ok(())
}
