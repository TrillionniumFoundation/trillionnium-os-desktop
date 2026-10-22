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
    if init::booted_from_rootfs() {
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

    init_console_file_table(ctx);
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
