// SPDX-License-Identifier: MPL-2.0

//! Regressions for the read-only writeback observed in the 2026-10-22
//! original-Agentd ordinary-ABI smoke. The backing device accepts writes;
//! these tests detect unwanted writes before a read-only backend can hide them.

use core::sync::atomic::{AtomicUsize, Ordering};

use aster_block::{
    BlockDeviceMeta,
    bio::{BioEnqueueError, BioType, SubmittedBio},
};
use ostd::prelude::ktest;

use super::*;
use crate::fs::{
    ext2::{
        Ext2,
        inode::test::read_raw_inode_from_disk,
        test_utils::{Ext2Fixture, Ext2MemoryDisk, create_file, default_fixture},
    },
    file::SyncMode,
    vfs::{
        file_system::{FileSystem as FileSystemTrait, FsFlags},
        inode::Inode as InodeTrait,
    },
};

const FILE_NAME: &str = "atime";
const PAYLOAD_BYTE: u8 = 0x5a;

/// Counts writes without rejecting them or changing read/flush behavior.
#[derive(Debug)]
struct CountingDisk {
    inner: Arc<Ext2MemoryDisk>,
    writes: AtomicUsize,
}

impl BlockDevice for CountingDisk {
    fn enqueue(&self, bio: SubmittedBio) -> core::result::Result<(), BioEnqueueError> {
        if bio.type_() == BioType::Write {
            self.writes.fetch_add(1, Ordering::Relaxed);
        }
        self.inner.enqueue(bio)
    }

    fn metadata(&self) -> BlockDeviceMeta {
        self.inner.metadata()
    }

    fn name(&self) -> &str {
        "ext2-atime-counting-disk"
    }

    fn id(&self) -> DeviceId {
        self.inner.id()
    }
}

#[derive(Clone, Copy)]
enum ReadPath {
    Buffered,
    Direct,
    Directory,
}

fn persisted_fixture() -> Ext2Fixture {
    let (fixture, root) = default_fixture();
    let file = create_file(&root, FILE_NAME);
    let data = vec![PAYLOAD_BYTE; BLOCK_SIZE];
    let mut reader = VmReader::from(data.as_slice()).to_fallible();
    assert_eq!(file.write_at(0, &mut reader).unwrap(), BLOCK_SIZE);
    file.set_atime(Duration::from_secs(7));
    root.set_atime(Duration::from_secs(11));
    FileSystemTrait::sync(fixture.ext2.as_ref()).unwrap();
    fixture
}

fn fresh_filesystem(fixture: &Ext2Fixture, flags: FsFlags) -> (Arc<Ext2>, Arc<CountingDisk>) {
    let disk = Arc::new(CountingDisk {
        inner: fixture.disk.clone(),
        writes: AtomicUsize::new(0),
    });
    // Opening the persisted bytes creates new inode and page caches. In
    // particular, the RO cases do not simulate initial RO with a flag change.
    let fs = Ext2::open(disk.clone(), flags, None).unwrap();
    (fs, disk)
}

fn read_target(fs: &Ext2, path: ReadPath) -> Arc<Inode> {
    let root = fs.root_inode().unwrap();
    match path {
        ReadPath::Directory => root,
        ReadPath::Buffered | ReadPath::Direct => root.lookup(FILE_NAME).unwrap(),
    }
}

fn exercise_read(inode: &Inode, path: ReadPath) {
    match path {
        ReadPath::Directory => {
            let mut names = Vec::<String>::new();
            assert!(inode.readdir_at(0, &mut names).unwrap() > 0);
            for name in [".", "..", FILE_NAME] {
                assert!(names.iter().any(|entry| entry == name));
            }
        }
        ReadPath::Buffered | ReadPath::Direct => {
            let mut data = vec![0u8; BLOCK_SIZE];
            let mut writer = VmWriter::from(data.as_mut_slice()).to_fallible();
            let read_len = match path {
                ReadPath::Buffered => inode.read_at(0, &mut writer).unwrap(),
                ReadPath::Direct => inode.read_direct_at(0, &mut writer).unwrap(),
                ReadPath::Directory => unreachable!(),
            };
            assert_eq!(read_len, BLOCK_SIZE);
            assert!(data.iter().all(|byte| *byte == PAYLOAD_BYTE));
        }
    }
}

fn assert_readonly_read(path: ReadPath) {
    let fixture = persisted_fixture();
    let (fs, disk) = fresh_filesystem(&fixture, FsFlags::RDONLY);
    let inode = read_target(&fs, path);
    let before = inode.atime();
    assert!(!inode.inner.read().is_dirty());
    assert_eq!(disk.writes.load(Ordering::Relaxed), 0);

    exercise_read(&inode, path);
    assert_eq!(inode.atime(), before);
    assert!(!inode.inner.read().is_dirty());
    for mode in [SyncMode::Full, SyncMode::Data] {
        InodeTrait::sync(inode.as_ref(), mode).unwrap();
        assert_eq!(disk.writes.load(Ordering::Relaxed), 0);
    }
    FileSystemTrait::sync(fs.as_ref()).unwrap();
    assert_eq!(disk.writes.load(Ordering::Relaxed), 0);
    assert_eq!(
        read_raw_inode_from_disk(&fixture, inode.ino()).atime,
        utils::duration_to_ext2_secs(before)
    );
}

#[ktest]
fn readonly_buffered_read_keeps_atime_without_writes() {
    assert_readonly_read(ReadPath::Buffered);
}

#[ktest]
fn readonly_direct_read_keeps_atime_without_writes() {
    assert_readonly_read(ReadPath::Direct);
}

#[ktest]
fn readonly_readdir_keeps_atime_without_writes() {
    assert_readonly_read(ReadPath::Directory);
}

#[ktest]
fn writable_reads_persist_atime() {
    for path in [ReadPath::Buffered, ReadPath::Direct, ReadPath::Directory] {
        let fixture = persisted_fixture();
        let (fs, disk) = fresh_filesystem(&fixture, FsFlags::empty());
        let inode = read_target(&fs, path);
        assert!(!inode.inner.read().is_dirty());
        assert_eq!(disk.writes.load(Ordering::Relaxed), 0);

        exercise_read(&inode, path);
        let observed_atime = inode.atime();
        assert!(inode.inner.read().is_dirty());
        FileSystemTrait::sync(fs.as_ref()).unwrap();
        assert!(disk.writes.load(Ordering::Relaxed) > 0);
        assert!(!inode.inner.read().is_dirty());
        // No assumption about clock advancement: even an unchanged timestamp
        // must retain the original RW dirtying and persistence behavior.
        assert_eq!(
            read_raw_inode_from_disk(&fixture, inode.ino()).atime,
            utils::duration_to_ext2_secs(observed_atime)
        );
    }
}

#[ktest]
fn readonly_flag_does_not_discard_preexisting_dirty_data() {
    let fixture = persisted_fixture();
    let (fs, disk) = fresh_filesystem(&fixture, FsFlags::empty());
    let inode = read_target(&fs, ReadPath::Buffered);
    let replacement = vec![0xc3u8; BLOCK_SIZE];
    let mut reader = VmReader::from(replacement.as_slice()).to_fallible();
    assert_eq!(inode.write_at(0, &mut reader).unwrap(), BLOCK_SIZE);
    assert!(inode.inner.read().is_dirty());
    let writes_before_sync = disk.writes.load(Ordering::Relaxed);

    // This preserves the existing flag setter's behavior; it does not claim
    // an atomic RW-to-RO remount. Sync must still flush the earlier RW data.
    fs.set_fs_flags(FsFlags::RDONLY);
    FileSystemTrait::sync(fs.as_ref()).unwrap();
    assert!(disk.writes.load(Ordering::Relaxed) > writes_before_sync);

    let reopened = Ext2::open(fixture.disk.clone(), FsFlags::RDONLY, None).unwrap();
    let fresh_inode = read_target(&reopened, ReadPath::Buffered);
    let mut data = vec![0u8; BLOCK_SIZE];
    let mut writer = VmWriter::from(data.as_mut_slice()).to_fallible();
    assert_eq!(fresh_inode.read_at(0, &mut writer).unwrap(), BLOCK_SIZE);
    assert_eq!(data, replacement);
}
