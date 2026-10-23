// SPDX-License-Identifier: MPL-2.0

#![no_std]
#![deny(unsafe_code)]
#![feature(negative_impls)]
#![allow(unfulfilled_lint_expectations)]
#![expect(dead_code, deprecated, unused_imports)]

// Set this crate's log prefix for `ostd::log`.
macro_rules! __log_prefix {
    () => {
        "mlsdisk: "
    };
}

mod error;
mod layers;
mod os;
mod prelude;
mod tx;
mod util;

extern crate alloc;
#[macro_use]
extern crate ostd_pod;

use alloc::{string::ToString, sync::Arc, vec};
use core::ops::Range;

use aster_block::{
    BlockDevice, SECTOR_SIZE,
    bio::{Bio, BioDirection, BioSegment, BioStatus, BioType},
    id::Sid,
};
use component::{ComponentInitError, init_component};
use device_id::{DeviceId, MajorId, MinorId};
use ostd::{
    mm::{VmIo, io::util::HasVmReaderWriter},
    prelude::*,
};

pub use self::{
    error::{Errno, Error},
    layers::{
        bio::{BLOCK_SIZE, BlockId, BlockSet, Buf, BufMut, BufRef},
        disk::MlsDisk,
    },
    os::{Aead, AeadIv, AeadKey, AeadMac, Rng},
    util::{Aead as _, RandomInit, Rng as _},
};

#[init_component]
fn init() -> Result<(), ComponentInitError> {
    // FIXME: how to find a valid device used to format mlsdisk.
    let id = DeviceId::new(MajorId::new(255), MinorId::new(0));
    let Some(device) = aster_block::lookup(id) else {
        return Err(ComponentInitError::Unknown);
    };
    let raw_disk = RawDisk::new(device);
    let root_key = AeadKey::random();
    let device =
        MlsDisk::create(raw_disk, root_key, None).map_err(|_| ComponentInitError::Unknown)?;
    let _ = aster_block::register(Arc::new(device));
    Ok(())
}

#[derive(Clone, Debug)]
struct RawDisk {
    inner: Arc<dyn BlockDevice>,
    region: Range<BlockId>,
}

impl RawDisk {
    fn new(host_disk: Arc<dyn BlockDevice>) -> Self {
        let end = host_disk.metadata().nr_sectors * SECTOR_SIZE / BLOCK_SIZE;
        Self {
            inner: host_disk,
            region: Range { start: 0, end },
        }
    }
}

impl BlockSet for RawDisk {
    fn read(&self, pos: BlockId, mut buf: BufMut) -> Result<(), Error> {
        if pos + buf.nblocks() > self.region.end {
            return_errno_with_msg!(Errno::InvalidArgs, "read position is out of range");
        }
        let sid = Sid::from_offset((self.region.start + pos) * BLOCK_SIZE);
        let bio_segment = BioSegment::alloc(buf.nblocks(), BioDirection::FromDevice);
        let bio = Bio::new(BioType::Read, sid, vec![bio_segment.clone()], None);

        let res = bio.submit_and_wait(&*self.inner);
        match res {
            Ok(BioStatus::Complete) => {
                bio_segment.read_bytes(0, buf.as_mut_slice()).unwrap();
                Ok(())
            }
            _ => return_errno_with_msg!(Errno::IoFailed, "read io failed"),
        }
    }

    fn write(&self, pos: BlockId, buf: BufRef) -> Result<(), Error> {
        if pos + buf.nblocks() > self.region.end {
            return_errno_with_msg!(Errno::InvalidArgs, "write position is out of range");
        }
        let sid = Sid::from_offset((self.region.start + pos) * BLOCK_SIZE);
        let bio_segment = BioSegment::alloc(buf.nblocks(), BioDirection::ToDevice);
        bio_segment.write_bytes(0, buf.as_slice()).unwrap();
        let bio = Bio::new(BioType::Write, sid, vec![bio_segment], None);

        let res = bio.submit_and_wait(&*self.inner);
        match res {
            Ok(BioStatus::Complete) => Ok(()),
            _ => return_errno_with_msg!(Errno::IoFailed, "write io failed"),
        }
    }

    fn subset(&self, range: Range<BlockId>) -> Result<Self, Error> {
        if self.region.start + range.end > self.region.end {
            return_errno_with_msg!(Errno::InvalidArgs, "subset is out of range");
        }

        Ok(RawDisk {
            inner: self.inner.clone(),
            region: Range {
                start: self.region.start + range.start,
                end: self.region.start + range.end,
            },
        })
    }

    fn flush(&self) -> Result<(), Error> {
        // Flush the underlying device's volatile cache, including when this
        // BlockSet is only a subregion of that device. There is no data payload.
        let bio = Bio::new(BioType::Flush, Sid::from_offset(0), vec![], None);
        match bio.submit_and_wait(&*self.inner) {
            Ok(BioStatus::Complete) => Ok(()),
            _ => return_errno_with_msg!(Errno::IoFailed, "flush io failed"),
        }
    }

    fn nblocks(&self) -> usize {
        self.region.len()
    }
}

#[cfg(ktest)]
mod test {
    use core::sync::atomic::{AtomicUsize, Ordering};

    use aster_block::{
        BlockDeviceMeta,
        bio::{BioEnqueueError, SubmittedBio},
    };
    use ostd::{
        mm::{FrameAllocOptions, Segment},
        prelude::*,
        sync::SpinLock,
    };

    use super::*;

    #[derive(Debug)]
    struct MemoryDisk {
        blocks: Segment<()>,
        flush_result: SpinLock<Result<BioStatus, BioEnqueueError>>,
        flush_count: AtomicUsize,
    }

    impl MemoryDisk {
        fn new(nblocks: usize) -> Self {
            let blocks = FrameAllocOptions::new()
                .zeroed(false)
                .alloc_segment(nblocks)
                .unwrap();
            Self {
                blocks,
                flush_result: SpinLock::new(Ok(BioStatus::Complete)),
                flush_count: AtomicUsize::new(0),
            }
        }
    }

    impl BlockDevice for MemoryDisk {
        fn enqueue(&self, bio: SubmittedBio) -> Result<(), BioEnqueueError> {
            let bio_type = bio.type_();
            if bio_type == BioType::Flush {
                assert!(bio.segments().is_empty());
                assert!(bio.sid_range().is_empty());
                self.flush_count.fetch_add(1, Ordering::Relaxed);
                // Drop the fault-injection lock before invoking completion.
                let result = *self.flush_result.lock();
                bio.complete(result?);
                return Ok(());
            }

            let mut current_offset = bio.sid_range().start.to_offset();
            for segment in bio.segments() {
                let size = match bio_type {
                    BioType::Read => segment
                        .dma_slice()
                        .writer()
                        .unwrap()
                        .write(self.blocks.reader().skip(current_offset)),
                    BioType::Write => self
                        .blocks
                        .writer()
                        .skip(current_offset)
                        .write(&mut segment.dma_slice().reader().unwrap()),
                    _ => 0,
                };
                current_offset += size;
            }
            bio.complete(BioStatus::Complete);
            Ok(())
        }

        fn metadata(&self) -> BlockDeviceMeta {
            BlockDeviceMeta {
                max_nr_segments_per_bio: usize::MAX,
                nr_sectors: self.blocks.size() / SECTOR_SIZE,
            }
        }

        fn name(&self) -> &str {
            todo!()
        }

        fn id(&self) -> DeviceId {
            todo!()
        }
    }

    #[ktest]
    fn write_sync_read() {
        let nblocks = 64 * 1024;
        let memory_disk = Arc::new(MemoryDisk::new(nblocks));
        let raw_disk = RawDisk::new(memory_disk.clone());
        let root_key = AeadKey::random();
        let mlsdisk = MlsDisk::create(raw_disk.clone(), root_key, None).unwrap();

        let num_rw = 128;
        let mut rw_buf = Buf::alloc(1).unwrap();
        for i in 0..num_rw {
            rw_buf.as_mut_slice().fill(i as u8);
            mlsdisk.write(i, rw_buf.as_ref()).unwrap();
        }

        let before = memory_disk.flush_count.load(Ordering::Relaxed);
        mlsdisk.sync().unwrap();
        assert!(memory_disk.flush_count.load(Ordering::Relaxed) > before);

        for i in 0..num_rw {
            mlsdisk.read(i, rw_buf.as_mut()).unwrap();
            assert_eq!(rw_buf.as_slice()[0], i as u8);
        }
    }

    #[ktest]
    fn raw_disk_flush_submits_and_reports_terminal_failure() {
        let memory_disk = Arc::new(MemoryDisk::new(1));
        let raw_disk = RawDisk::new(memory_disk.clone());
        raw_disk.flush().unwrap();
        assert_eq!(memory_disk.flush_count.load(Ordering::Relaxed), 1);

        for (index, result) in [
            Ok(BioStatus::NotSupported),
            Ok(BioStatus::NoSpace),
            Ok(BioStatus::IoError),
            Err(BioEnqueueError::Refused),
            Err(BioEnqueueError::IsFull),
            Err(BioEnqueueError::TooBig),
        ]
        .into_iter()
        .enumerate()
        {
            *memory_disk.flush_result.lock() = result;
            assert_eq!(raw_disk.flush().unwrap_err().errno(), Errno::IoFailed);
            // No silent success or automatic retry on either submission or
            // completion failure.
            assert_eq!(memory_disk.flush_count.load(Ordering::Relaxed), index + 2);
        }
    }

    fn disk_with_buffered_write() -> (Arc<MemoryDisk>, MlsDisk<RawDisk>) {
        // Keep the original test disk geometry required by the journal's fixed
        // snapshot capacity. This is real Frame-backed storage, not a mock sync.
        let memory_disk = Arc::new(MemoryDisk::new(64 * 1024));
        let raw_disk = RawDisk::new(memory_disk.clone());
        let mlsdisk = MlsDisk::create(raw_disk, AeadKey::random(), None).unwrap();
        let mut buf = Buf::alloc(1).unwrap();
        buf.as_mut_slice().fill(0x5a);
        mlsdisk.write(0, buf.as_ref()).unwrap();
        (memory_disk, mlsdisk)
    }

    #[ktest]
    fn mlsdisk_sync_returns_device_flush_error() {
        let (memory_disk, mlsdisk) = disk_with_buffered_write();
        *memory_disk.flush_result.lock() = Ok(BioStatus::IoError);
        let before = memory_disk.flush_count.load(Ordering::Relaxed);
        assert_eq!(mlsdisk.sync().unwrap_err().errno(), Errno::IoFailed);
        assert_eq!(memory_disk.flush_count.load(Ordering::Relaxed), before + 1);
    }

    #[ktest]
    fn mlsdisk_flush_bio_completes_with_io_error() {
        let (memory_disk, mlsdisk) = disk_with_buffered_write();
        *memory_disk.flush_result.lock() = Err(BioEnqueueError::Refused);
        let before = memory_disk.flush_count.load(Ordering::Relaxed);
        let bio = Bio::new(BioType::Flush, Sid::from_offset(0), vec![], None);
        assert_eq!(bio.submit_and_wait(&mlsdisk), Ok(BioStatus::IoError));
        assert_eq!(memory_disk.flush_count.load(Ordering::Relaxed), before + 1);
    }
}
