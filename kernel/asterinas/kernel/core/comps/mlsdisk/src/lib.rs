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
    let root_key = AeadKey::random().map_err(|_| ComponentInitError::Unknown)?;
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
        mm::{Frame, FrameAllocOptions},
        prelude::*,
        sync::SpinLock,
    };

    use super::*;

    #[derive(Debug)]
    pub(crate) struct MemoryDisk {
        blocks: vec::Vec<Frame<()>>,
        flush_result: SpinLock<Result<BioStatus, BioEnqueueError>>,
        flush_count: AtomicUsize,
        write_count: AtomicUsize,
    }

    impl MemoryDisk {
        pub(crate) fn new(nblocks: usize) -> Self {
            // The block device promises logical capacity, not one physically
            // contiguous extent. Keep every page under the original Frame
            // allocator owner without requiring a 256-MiB contiguous region.
            let blocks = (0..nblocks)
                .map(|_| {
                    FrameAllocOptions::new()
                        .zeroed(false)
                        .alloc_frame()
                        .unwrap()
                })
                .collect();
            Self {
                blocks,
                flush_result: SpinLock::new(Ok(BioStatus::Complete)),
                flush_count: AtomicUsize::new(0),
                write_count: AtomicUsize::new(0),
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

            if bio_type == BioType::Write {
                self.write_count.fetch_add(1, Ordering::Relaxed);
            }
            let mut current_offset = bio.sid_range().start.to_offset();
            for segment in bio.segments() {
                let dma = segment.dma_slice();
                let mut transferred = 0;
                while transferred < segment.nbytes() {
                    let frame_index = current_offset / BLOCK_SIZE;
                    let frame_offset = current_offset % BLOCK_SIZE;
                    let count = (BLOCK_SIZE - frame_offset).min(segment.nbytes() - transferred);
                    let frame = &self.blocks[frame_index];
                    let copied = match bio_type {
                        BioType::Read => dma
                            .writer()
                            .unwrap()
                            .skip(transferred)
                            .limit(count)
                            .write(frame.reader().skip(frame_offset).limit(count)),
                        BioType::Write => frame
                            .writer()
                            .skip(frame_offset)
                            .limit(count)
                            .write(dma.reader().unwrap().skip(transferred).limit(count)),
                        _ => panic!("unsupported native MemoryDisk Bio type"),
                    };
                    assert_eq!(copied, count);
                    current_offset += copied;
                    transferred += copied;
                }
            }
            bio.complete(BioStatus::Complete);
            Ok(())
        }

        fn metadata(&self) -> BlockDeviceMeta {
            BlockDeviceMeta {
                max_nr_segments_per_bio: usize::MAX,
                nr_sectors: self.blocks.len() * BLOCK_SIZE / SECTOR_SIZE,
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
        let root_key = AeadKey::random().unwrap();
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
        let mlsdisk = MlsDisk::create(raw_disk, AeadKey::random().unwrap(), None).unwrap();
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

    #[ktest]
    fn entropy_failure_prevents_blob_and_chain_publication() {
        use crate::{
            layers::{
                bio::BlockRing,
                crypto::{CryptoBlob, CryptoChain},
            },
            os::entropy_test::EntropyCut,
        };

        let disk = Arc::new(MemoryDisk::new(16));
        let raw = RawDisk::new(disk.clone());
        for successful_words in [0, 1] {
            let cut = EntropyCut::after(successful_words);
            assert_eq!(
                CryptoBlob::create(raw.clone(), b"secret")
                    .err()
                    .unwrap()
                    .errno(),
                Errno::OsSpecUnknown
            );
            drop(cut);
            let cut = EntropyCut::after(successful_words);
            assert_eq!(
                CryptoChain::new(BlockRing::new(raw.clone()))
                    .err()
                    .unwrap()
                    .errno(),
                Errno::OsSpecUnknown
            );
            drop(cut);
        }
        assert_eq!(disk.write_count.load(Ordering::Relaxed), 0);

        let ring = BlockRing::new(raw);
        ring.set_cursor(0);
        let mut chain = CryptoChain::new(ring).unwrap();
        chain.append(b"first").unwrap();
        let before = disk.write_count.load(Ordering::Relaxed);
        for successful_words in [0, 1] {
            let cut = EntropyCut::after(successful_words);
            assert_eq!(
                chain.append(b"second").unwrap_err().errno(),
                Errno::OsSpecUnknown
            );
            assert_eq!(chain.block_range(), &(0..1));
            assert_eq!(disk.write_count.load(Ordering::Relaxed), before);
            drop(cut);
        }
        chain.append(b"second").unwrap();
        let mut output = [0; 6];
        assert_eq!(chain.read(1, &mut output).unwrap(), 6);
        assert_eq!(&output, b"second");
        assert_eq!(chain.block_range(), &(0..2));
    }

    #[ktest]
    fn entropy_failure_keeps_buffered_disk_data_for_retry() {
        use crate::os::entropy_test::EntropyCut;

        let (disk, mlsdisk) = disk_with_buffered_write();
        let mut buffer = Buf::alloc(1).unwrap();
        buffer.as_mut_slice().fill(0x6b);
        mlsdisk.write(1, buffer.as_ref()).unwrap();
        let before = disk.write_count.load(Ordering::Relaxed);
        // Fail before the first key, halfway through it, and after one whole
        // key. No HBA slots or device writes are consumed by these failures.
        for successful_words in [0, 1, 2, 3] {
            let cut = EntropyCut::after(successful_words);
            assert_eq!(mlsdisk.sync().unwrap_err().errno(), Errno::OsSpecUnknown);
            assert_eq!(disk.write_count.load(Ordering::Relaxed), before);
            mlsdisk.read(0, buffer.as_mut()).unwrap();
            assert!(buffer.as_slice().iter().all(|byte| *byte == 0x5a));
            mlsdisk.read(1, buffer.as_mut()).unwrap();
            assert!(buffer.as_slice().iter().all(|byte| *byte == 0x6b));
            drop(cut);
        }
        mlsdisk.sync().unwrap();
        assert!(disk.write_count.load(Ordering::Relaxed) > before);
        mlsdisk.read(0, buffer.as_mut()).unwrap();
        assert!(buffer.as_slice().iter().all(|byte| *byte == 0x5a));
        mlsdisk.read(1, buffer.as_mut()).unwrap();
        assert!(buffer.as_slice().iter().all(|byte| *byte == 0x6b));
    }

    #[ktest]
    fn entropy_failure_aborts_original_log_transaction() {
        use crate::{layers::log::TxLogStore, os::entropy_test::EntropyCut};

        let disk = Arc::new(MemoryDisk::new(64 * 1024));
        let store =
            TxLogStore::format(RawDisk::new(disk.clone()), AeadKey::random().unwrap()).unwrap();
        let tx = store.new_tx();
        let before = disk.write_count.load(Ordering::Relaxed);
        let cut = EntropyCut::after(0);
        assert_eq!(
            tx.context(|| store.create_log("denied"))
                .err()
                .unwrap()
                .errno(),
            Errno::OsSpecUnknown
        );
        drop(cut);
        tx.abort();
        assert_eq!(disk.write_count.load(Ordering::Relaxed), before);

        let tx = store.new_tx();
        let log = tx.context(|| store.create_log("denied")).unwrap();
        let mut buffer = Buf::alloc(1).unwrap();
        buffer.as_mut_slice().fill(0x39);
        tx.context(|| log.append(buffer.as_ref())).unwrap();
        let cut = EntropyCut::after(0);
        assert_eq!(tx.commit().unwrap_err().errno(), Errno::OsSpecUnknown);
        drop(cut);
        drop(log);
        assert_eq!(disk.write_count.load(Ordering::Relaxed), before);

        let tx = store.new_tx();
        assert_eq!(
            tx.context(|| store.list_logs_in("denied"))
                .unwrap_err()
                .errno(),
            Errno::NotFound
        );
        let log = tx.context(|| store.create_log("accepted")).unwrap();
        tx.context(|| log.append(buffer.as_ref())).unwrap();
        let id = log.id();
        tx.commit().unwrap();
        drop(log);
        store.sync().unwrap();
        let tx = store.new_tx();
        assert_eq!(
            tx.context(|| store.list_logs_in("accepted")).unwrap(),
            vec![id]
        );
        assert_eq!(
            tx.context(|| store.list_logs_in("denied"))
                .unwrap_err()
                .errno(),
            Errno::NotFound
        );
        tx.abort();
    }

    #[ktest]
    fn entropy_failure_does_not_apply_current_journal_edit() {
        use serde::{Deserialize, Serialize};

        use crate::{
            layers::edit::{Edit, EditJournal, NeverCompactPolicy},
            os::entropy_test::EntropyCut,
        };

        #[derive(Deserialize, Serialize)]
        struct PaddedEdit {
            increment: u64,
            padding: vec::Vec<u8>,
        }
        impl Edit<u64> for PaddedEdit {
            fn apply_to(&self, state: &mut u64) {
                *state += self.increment;
            }
        }
        let disk = Arc::new(MemoryDisk::new(16));
        let raw = RawDisk::new(disk.clone());
        let mut journal = EditJournal::format(raw.clone(), 0_u64, 64, NeverCompactPolicy).unwrap();
        journal.add(PaddedEdit {
            increment: 1,
            padding: vec![0x41; 3000],
        });
        journal.commit().unwrap();
        assert_eq!(*journal.state(), 1);
        let before = disk.write_count.load(Ordering::Relaxed);
        journal.add(PaddedEdit {
            increment: 100,
            padding: vec![0x42; 3000],
        });
        let cut = EntropyCut::after(0);
        // Each record fits alone; two do not. This reaches the original
        // full-buffer journal append, rather than a test replacement journal.
        assert_eq!(journal.commit().unwrap_err().errno(), Errno::OsSpecUnknown);
        assert_eq!(*journal.state(), 1);
        assert_eq!(disk.write_count.load(Ordering::Relaxed), before);
        drop(cut);
        journal.flush().unwrap();
        let meta = journal.meta();
        drop(journal);
        let mut recovered =
            EditJournal::<PaddedEdit, u64, _, _>::recover(raw, &meta, NeverCompactPolicy).unwrap();
        assert_eq!(*recovered.state(), 1);
        recovered.add(PaddedEdit {
            increment: 2,
            padding: vec![],
        });
        recovered.commit().unwrap();
        recovered.flush().unwrap();
        assert_eq!(*recovered.state(), 3);
    }

    #[derive(Debug)]
    struct DeferredDisk {
        disk: Arc<MemoryDisk>,
        parked: Arc<AtomicUsize>,
    }

    impl DeferredDisk {
        fn new(disk: Arc<MemoryDisk>) -> Self {
            Self {
                disk,
                parked: Arc::new(AtomicUsize::new(0)),
            }
        }
    }

    impl BlockDevice for DeferredDisk {
        fn enqueue(&self, bio: SubmittedBio) -> Result<(), BioEnqueueError> {
            use ostd::task::{Task, TaskOptions};

            let waiter = Task::current().unwrap().cloned();
            let disk = self.disk.clone();
            let parked = self.parked.clone();
            TaskOptions::new(move || {
                // This crate's fixed N0 test base uses OSTD's original FIFO
                // scheduler. It clears cpu only on dequeue/park, not yield.
                // Prove the submitting Task actually slept on its original
                // Bio completion before completing from this other Task.
                assert!(waiter.schedule_info().cpu.get().is_none());
                assert_eq!(bio.status(), BioStatus::Submit);
                parked.fetch_add(1, Ordering::Release);
                disk.enqueue(bio).unwrap();
            })
            .spawn()
            .unwrap();
            Ok(())
        }

        fn metadata(&self) -> BlockDeviceMeta {
            self.disk.metadata()
        }
        fn name(&self) -> &str {
            "mlsdisk-native-deferred"
        }
        fn id(&self) -> DeviceId {
            DeviceId::new(MajorId::new(255), MinorId::new(1))
        }
    }

    #[ktest]
    fn delayed_bio_completes_after_original_task_parks() {
        let memory = Arc::new(MemoryDisk::new(64 * 1024));
        let disk = Arc::new(DeferredDisk::new(memory));
        let raw = RawDisk::new(disk.clone());
        let key = AeadKey::random().unwrap();
        let mlsdisk = MlsDisk::create(raw.clone(), key, None).unwrap();
        let after_format = disk.parked.load(Ordering::Acquire);
        assert!(after_format > 0);
        let mut buffer = Buf::alloc(1).unwrap();
        buffer.as_mut_slice().fill(0x8d);
        mlsdisk.write(0, buffer.as_ref()).unwrap();
        mlsdisk.sync().unwrap();
        let after_sync = disk.parked.load(Ordering::Acquire);
        assert!(after_sync > after_format);
        buffer.as_mut_slice().fill(0);
        mlsdisk.read(0, buffer.as_mut()).unwrap();
        assert!(buffer.as_slice().iter().all(|byte| *byte == 0x8d));
        assert!(disk.parked.load(Ordering::Acquire) > after_sync);
        *disk.disk.flush_result.lock() = Ok(BioStatus::IoError);
        let before_error = disk.parked.load(Ordering::Acquire);
        assert_eq!(mlsdisk.sync().unwrap_err().errno(), Errno::IoFailed);
        assert!(disk.parked.load(Ordering::Acquire) > before_error);
        *disk.disk.flush_result.lock() = Ok(BioStatus::Complete);
        mlsdisk.sync().unwrap();
        drop(mlsdisk);
        // Exercise actual recovery reads and deeper LSM/MHT locks as well.
        let reopened = MlsDisk::open(raw, key, None).unwrap();
        buffer.as_mut_slice().fill(0);
        reopened.read(0, buffer.as_mut()).unwrap();
        assert!(buffer.as_slice().iter().all(|byte| *byte == 0x8d));
        reopened.sync().unwrap();
    }

    fn register_delayed_callback(
        provider: &Arc<tx::TxProvider>,
        stage: usize,
        raw: RawDisk,
        seen: Arc<ostd::sync::Mutex<vec::Vec<usize>>>,
        id: usize,
        add_next: bool,
    ) {
        use core::sync::atomic::AtomicBool;

        let owner = Arc::downgrade(provider);
        let first = AtomicBool::new(true);
        let invoke = move || {
            raw.flush().unwrap();
            seen.lock().push(id);
            if add_next && first.swap(false, Ordering::AcqRel) {
                register_delayed_callback(
                    &owner.upgrade().unwrap(),
                    stage,
                    raw.clone(),
                    seen.clone(),
                    id + 1,
                    false,
                );
            }
        };
        match stage {
            0 => provider.register_precommit_handler(move |_| {
                invoke();
                Ok(())
            }),
            1 => provider.register_commit_handler(move |_| invoke()),
            2 => provider.register_abort_handler(move |_| invoke()),
            _ => unreachable!(),
        }
    }

    #[ktest]
    fn transaction_callbacks_sleep_and_defer_reentrant_registration() {
        use ostd::sync::Mutex;

        use crate::tx::{TxData, TxProvider};

        struct Marker;
        impl TxData for Marker {}
        struct Later;
        impl TxData for Later {}

        let disk = Arc::new(DeferredDisk::new(Arc::new(MemoryDisk::new(1))));
        for stage in 0..3 {
            let provider = TxProvider::new();
            let raw = RawDisk::new(disk.clone());
            let seen = Arc::new(Mutex::new(vec![]));
            register_delayed_callback(&provider, stage, raw.clone(), seen.clone(), 1, false);
            register_delayed_callback(&provider, stage, raw.clone(), seen.clone(), 2, true);
            let owner = Arc::downgrade(&provider);
            provider.register_data_initializer(alloc::boxed::Box::new(move || {
                raw.flush().unwrap();
                owner
                    .upgrade()
                    .unwrap()
                    .register_data_initializer(alloc::boxed::Box::new(|| Later));
                Marker
            }));
            for round in 0..2 {
                let tx = provider.new_tx();
                tx.data_with(|_: &Marker| {});
                tx.data_with(|_: &Later| {});
                if stage == 2 {
                    tx.abort();
                } else {
                    tx.commit().unwrap();
                }
                if round == 0 {
                    assert_eq!(*seen.lock(), vec![2, 1]);
                }
            }
            assert_eq!(*seen.lock(), vec![2, 1, 3, 2, 1]);
        }
        // Five callbacks + two initializers in each of three dispatch stages.
        assert_eq!(disk.parked.load(Ordering::Acquire), 21);
    }

    #[ktest]
    fn final_store_owner_releases_real_disk_between_full_runs() {
        for _ in 0..2 {
            let memory = Arc::new(MemoryDisk::new(64 * 1024));
            let weak = Arc::downgrade(&memory);
            let raw = RawDisk::new(memory);
            let mlsdisk = MlsDisk::create(raw, AeadKey::random().unwrap(), None).unwrap();
            let mut buffer = Buf::alloc(1).unwrap();
            buffer.as_mut_slice().fill(0x51);
            mlsdisk.write(0, buffer.as_ref()).unwrap();
            mlsdisk.sync().unwrap();
            assert!(weak.upgrade().is_some());
            drop(mlsdisk);
            assert!(weak.upgrade().is_none());
            // The next iteration allocates another real 256-MiB frame-backed disk under
            // the unchanged 512-MiB N0 profile. No reset or smaller disk hides
            // a retained physical owner from the first iteration.
        }
    }

    #[ktest]
    fn frame_backed_disk_handles_noncontiguous_cross_page_bios() {
        use core::cmp::Reverse;

        use ostd::mm::HasPaddr;

        let mut memory = MemoryDisk::new(4);
        memory.blocks.sort_by_key(|frame| Reverse(frame.paddr()));
        assert!(memory.blocks[0].paddr() > memory.blocks[1].paddr());
        assert_eq!(memory.metadata().nr_sectors * SECTOR_SIZE, 4 * BLOCK_SIZE);
        for frame in &memory.blocks {
            frame.write_bytes(0, &[0xcc; BLOCK_SIZE]).unwrap();
        }
        let first = BioSegment::alloc(2, BioDirection::ToDevice);
        let second = BioSegment::alloc(1, BioDirection::ToDevice);
        first.write_bytes(0, &[0xa1; 2 * BLOCK_SIZE]).unwrap();
        second.write_bytes(0, &[0xb2; BLOCK_SIZE]).unwrap();
        let write = Bio::new(
            BioType::Write,
            Sid::from_offset(SECTOR_SIZE),
            vec![first, second],
            None,
        );
        assert_eq!(write.submit_and_wait(&memory), Ok(BioStatus::Complete));

        let first = BioSegment::alloc(1, BioDirection::FromDevice);
        let second = BioSegment::alloc(3, BioDirection::FromDevice);
        let read = Bio::new(
            BioType::Read,
            Sid::from_offset(0),
            vec![first.clone(), second.clone()],
            None,
        );
        assert_eq!(read.submit_and_wait(&memory), Ok(BioStatus::Complete));
        let mut bytes = vec![0; 4 * BLOCK_SIZE];
        first.read_bytes(0, &mut bytes[..BLOCK_SIZE]).unwrap();
        second.read_bytes(0, &mut bytes[BLOCK_SIZE..]).unwrap();
        assert!(bytes[..SECTOR_SIZE].iter().all(|b| *b == 0xcc));
        assert!(
            bytes[SECTOR_SIZE..SECTOR_SIZE + 2 * BLOCK_SIZE]
                .iter()
                .all(|b| *b == 0xa1)
        );
        assert!(
            bytes[SECTOR_SIZE + 2 * BLOCK_SIZE..SECTOR_SIZE + 3 * BLOCK_SIZE]
                .iter()
                .all(|b| *b == 0xb2)
        );
        assert!(
            bytes[SECTOR_SIZE + 3 * BLOCK_SIZE..]
                .iter()
                .all(|b| *b == 0xcc)
        );
    }
}
