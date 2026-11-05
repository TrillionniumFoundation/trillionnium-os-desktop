// SPDX-License-Identifier: MPL-2.0

pub mod file;
mod fs_impls;
pub(crate) mod initramfs;
pub(crate) mod pipe;
pub(crate) mod rootfs;
pub(crate) mod thread_info;
pub mod utils;
pub mod vfs;

pub use fs_impls::devtmpfs;
pub(crate) use fs_impls::{
    cgroupfs, configfs, devpts, exfat, ext2, procfs, pseudofs, ramfs, sysfs, tmpfs,
};

use crate::{
    fs::{
        file::{
            AccessMode, InodeType, OpenArgs,
            file_table::{FdFlags, FileTable},
            mkmod,
        },
        vfs::{
            path::{FsPath, Path, PathResolver, PerMountFlags},
            registry::FsAndRoot,
        },
    },
    init,
    prelude::*,
};

pub(crate) fn init() {
    vfs::init();
    fs_impls::init();
}

pub(crate) fn init_on_each_cpu() {
    fs_impls::init_on_each_cpu();
}

pub(crate) fn init_in_first_kthread(path_resolver: &PathResolver) {
    fs_impls::init_in_first_kthread();
    initramfs::init_in_first_kthread(path_resolver).unwrap();
}

pub(crate) fn init_in_first_process(ctx: &Context) {
    // The exact image runs directly as rdinit, without the base /init mounts.
    if init::booted_from_rootfs() || cfg!(feature = "g2-original-owner-a39-v1") {
        let fs = ctx.thread_local.borrow_fs();
        let path_resolver = fs.resolver().read();
        let dev_path = lookup_or_create_dev(&path_resolver).unwrap();
        dev_path
            .mount(
                FsAndRoot::new(devtmpfs::singleton().clone()),
                PerMountFlags::default(),
                Some("devtmpfs".to_string()),
                ctx,
            )
            .unwrap();
    }

    #[cfg(feature = "g2-original-owner-a39-v1")]
    mount_original_owner_runtime_fs(ctx).expect("mount original owner runtime filesystems");

    init_console_file_table(ctx);
}

/// Supplies the skipped fixed initramfs mounts for the exact original image.
/// PID 1 runs this before its startup hook releases the prepared children.
/// All roles retain the original shared namespace and registered filesystems.
#[cfg(feature = "g2-original-owner-a39-v1")]
fn mount_original_owner_runtime_fs(ctx: &Context) -> Result<()> {
    use crate::fs::vfs::{file_system::FsFlags, registry::FsCreationCtx};

    // The fixed base has no /run. The original owner requires a physical,
    // root-owned runtime ancestor without group/other write access.
    {
        let fs = ctx.thread_local.borrow_fs();
        let resolver = fs.resolver().read();
        match resolver.lookup(&FsPath::try_from("/run")?) {
            Err(error) if error.error() == Errno::ENOENT => {
                resolver
                    .root()
                    .new_child("run", InodeType::Dir, mkmod!(a+rx, u+w))?;
            }
            Ok(path) if path.type_() == InodeType::Dir => {}
            Ok(_) => {
                return_errno_with_message!(
                    Errno::ENOTDIR,
                    "original owner runtime is not a directory"
                );
            }
            Err(error) => return Err(error),
        }
    }

    for (target, type_name) in [("/proc", "proc"), ("/sys", "sysfs")] {
        let mountpoint = {
            let fs = ctx.thread_local.borrow_fs();
            let resolver = fs.resolver().read();
            resolver.lookup(&FsPath::try_from(target)?)?
        };
        if mountpoint.type_() != InodeType::Dir {
            return_errno_with_message!(
                Errno::ENOTDIR,
                "original owner mountpoint is not a directory"
            );
        }
        let fs_type = vfs::registry::look_up(type_name).ok_or_else(|| Error::new(Errno::ENODEV))?;
        let mut creation = FsCreationCtx::new(Some(type_name), FsFlags::empty(), None, ctx);
        mountpoint.mount(
            fs_type.get_or_create(&mut creation)?,
            PerMountFlags::default(),
            Some(type_name.to_string()),
            ctx,
        )?;
    }
    Ok(())
}

/// Installs the standard console descriptors in an empty initial file table.
/// Device initialization must already have completed in the first process.
pub(crate) fn init_console_file_table(ctx: &Context) {
    let fs = ctx.thread_local.borrow_fs();
    let path_resolver = fs.resolver().read();

    let tty_path = FsPath::try_from("/dev/console").unwrap();
    let stdin = {
        let open_args = OpenArgs::from_modes(AccessMode::O_RDONLY, mkmod!(u+r));
        path_resolver
            .lookup(&tty_path)
            .unwrap()
            .open(open_args)
            .unwrap()
    };
    let stdout = {
        let open_args = OpenArgs::from_modes(AccessMode::O_WRONLY, mkmod!(u+w));
        path_resolver
            .lookup(&tty_path)
            .unwrap()
            .open(open_args)
            .unwrap()
    };
    let stderr = {
        let open_args = OpenArgs::from_modes(AccessMode::O_WRONLY, mkmod!(u+w));
        path_resolver
            .lookup(&tty_path)
            .unwrap()
            .open(open_args)
            .unwrap()
    };

    // Each initial process has an empty table and a soft limit of at least three.
    for file in [stdin, stdout, stderr] {
        FileTable::reserve_fd(ctx, FdFlags::empty())
            .unwrap()
            .install(Arc::new(file));
    }
}

fn lookup_or_create_dev(path_resolver: &PathResolver) -> Result<Path> {
    match path_resolver.lookup(&FsPath::try_from("/dev")?) {
        Err(error) if error.error() == Errno::ENOENT => {
            path_resolver
                .root()
                .new_child("dev", InodeType::Dir, mkmod!(a+rx, u+w))
        }
        result => result,
    }
}
