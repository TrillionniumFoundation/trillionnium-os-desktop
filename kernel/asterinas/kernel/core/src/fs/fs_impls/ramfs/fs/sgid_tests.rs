// SPDX-License-Identifier: MPL-2.0

use ostd::prelude::ktest;

use super::*;

fn create(parent: &Arc<Dentry>, name: &str, type_: InodeType, mode: u16) -> Arc<Dentry> {
    let dir = parent.as_dir_dentry_or_err().unwrap();
    dir.create_child(name, || {
        dir.inode()
            .create(&dir, name, type_, InodeMode::from_bits_truncate(mode))
    })
    .unwrap()
}

#[ktest]
fn setgid_parent_group_reaches_real_socket_file_directory_fifo_symlink_and_tmpfile() {
    crate::time::clocks::init_for_ktest();
    let fs = RamFs::new();
    let root = Dentry::new_root(fs.root_inode());
    root.inode().set_group(&root, Gid::new(60001)).unwrap();
    root.inode()
        .set_mode(&root, InodeMode::from_bits_truncate(0o2777))
        .unwrap();
    let uid = utils::current_fs_ids().0;
    for (name, type_) in [("stream", InodeType::Socket), ("file", InodeType::File)] {
        let child = create(&root, name, type_, 0o640);
        let attrs = child.inode().metadata().unwrap();
        assert_eq!(
            (attrs.uid, attrs.gid, attrs.mode.bits()),
            (uid, Gid::new(60001), 0o640)
        );
    }
    let directory = create(&root, "directory", InodeType::Dir, 0o750);
    assert_eq!(directory.inode().mode().unwrap().bits(), 0o2750);
    let nested = create(&directory, "nested", InodeType::File, 0o600);
    assert_eq!(nested.inode().group().unwrap(), Gid::new(60001));
    let dir = root.as_dir_dentry_or_err().unwrap();
    let fifo = dir
        .mknod(
            "fifo",
            InodeMode::from_bits_truncate(0o620),
            MknodType::NamedPipe,
        )
        .unwrap();
    assert_eq!(fifo.inode().group().unwrap(), Gid::new(60001));
    let link = dir
        .create_child("link", || {
            dir.inode()
                .create_symlink(&dir, "link", "file", InodeMode::from_bits_truncate(0o777))
        })
        .unwrap();
    assert_eq!(link.inode().group().unwrap(), Gid::new(60001));
    let temporary = dir
        .inode()
        .create_tmpfile(
            &root,
            InodeMode::from_bits_truncate(0o600),
            HardLinkability::Linkable,
        )
        .unwrap();
    assert_eq!(temporary.group().unwrap(), Gid::new(60001));
    assert_eq!(temporary.metadata().unwrap().nr_hard_links, 0);

    root.inode()
        .set_mode(&root, InodeMode::from_bits_truncate(0o777))
        .unwrap();
    let normal = create(&root, "normal", InodeType::File, 0o640);
    assert_eq!(normal.inode().group().unwrap(), utils::current_fs_ids().1);
    let plain_dir = create(&root, "plain-dir", InodeType::Dir, 0o750);
    assert_eq!(plain_dir.inode().mode().unwrap().bits(), 0o750);
}
