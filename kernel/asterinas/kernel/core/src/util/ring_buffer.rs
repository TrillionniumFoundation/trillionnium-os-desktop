// SPDX-License-Identifier: MPL-2.0

use core::{
    num::Wrapping,
    ops::{Deref, Range},
};

use ostd::mm::{AnyUFrameMeta, io::util::HasVmReaderWriter};
pub(crate) use ring_buffer::{Consumer, Producer, RbConsumer, RbProducer, RingBuffer};

use super::{MultiRead, MultiWrite};
use crate::{
    prelude::*,
    vm::user_memory::{self, UserMemoryOwner, UserPageMeta},
};

/// IPC buffers retain their initiator's original per-frame charge.
pub(crate) type UserRingBuffer = RingBuffer<u8, UserPageMeta>;
pub(crate) type UserRbProducer = RbProducer<u8, UserPageMeta>;
pub(crate) type UserRbConsumer = RbConsumer<u8, UserPageMeta>;

pub(crate) fn new_user_ring_buffer(
    capacity: usize,
    owner: &UserMemoryOwner,
) -> Result<UserRingBuffer> {
    if !capacity.is_power_of_two() {
        return Err(Error::new(Errno::EINVAL));
    }
    let segment = user_memory::alloc_user_segment(owner, capacity.div_ceil(PAGE_SIZE))?;
    Ok(RingBuffer::from_segment(capacity, segment)?)
}

/// Extension methods for writing bytes to a [`Producer<u8, _>`].
pub(crate) trait ProducerU8Ext {
    /// Writes data from `reader` to the ring buffer.
    ///
    /// Returns the number of bytes written.
    fn write_fallible(&mut self, reader: &mut dyn MultiRead) -> Result<usize>;

    /// Writes up to `max_len` bytes from `reader` to the ring buffer.
    ///
    /// Returns the number of bytes written.
    fn write_fallible_with_max_len(
        &mut self,
        reader: &mut dyn MultiRead,
        max_len: usize,
    ) -> Result<usize>;
}

impl<R: Deref<Target = RingBuffer<u8, M>>, M: AnyUFrameMeta + ?Sized> ProducerU8Ext
    for Producer<u8, R, M>
{
    fn write_fallible(&mut self, reader: &mut dyn MultiRead) -> Result<usize> {
        self.write_fallible_with_max_len(reader, usize::MAX)
    }

    fn write_fallible_with_max_len(
        &mut self,
        reader: &mut dyn MultiRead,
        max_len: usize,
    ) -> Result<usize> {
        let free_len = self.free_len().min(max_len);

        let tail = self.tail();
        let offset = tail.0 & (self.capacity() - 1);

        let write_len = if offset + free_len > self.capacity() {
            // Write into two separate parts
            let mut write_len = 0;

            let mut writer = self.segment().writer();
            writer.skip(offset).limit(self.capacity() - offset);
            write_len += reader.read(&mut writer)?;

            let mut writer = self.segment().writer();
            writer.limit(free_len - (self.capacity() - offset));
            write_len += reader.read(&mut writer)?;

            write_len
        } else {
            let mut writer = self.segment().writer();
            writer.skip(offset).limit(free_len);
            reader.read(&mut writer)?
        };

        self.commit_write(write_len);
        Ok(write_len)
    }
}

/// Extension methods for byte ring buffers.
pub(crate) trait RingBufferU8Ext {
    /// Picks data from an absolute ring-counter range into `writer` without consuming it.
    ///
    /// Returns the number of bytes copied.
    fn pick_fallible(
        &self,
        range: Range<Wrapping<usize>>,
        writer: &mut dyn MultiWrite,
    ) -> Result<usize>;
}

impl<M: AnyUFrameMeta + ?Sized> RingBufferU8Ext for RingBuffer<u8, M> {
    fn pick_fallible(
        &self,
        range: Range<Wrapping<usize>>,
        writer: &mut dyn MultiWrite,
    ) -> Result<usize> {
        let len = (range.end - range.start).0;
        let offset = range.start.0 & (self.capacity() - 1);

        if offset + len > self.capacity() {
            // Read from two separate parts
            let mut read_len = 0;

            let mut reader = self.segment().reader();
            reader.skip(offset).limit(self.capacity() - offset);
            read_len += writer.write(&mut reader)?;

            let mut reader = self.segment().reader();
            reader.limit(len - (self.capacity() - offset));
            read_len += writer.write(&mut reader)?;

            Ok(read_len)
        } else {
            let mut reader = self.segment().reader();
            reader.skip(offset).limit(len);
            Ok(writer.write(&mut reader)?)
        }
    }
}

/// Extension methods for reading bytes from a [`Consumer<u8, _>`].
pub(crate) trait ConsumerU8Ext {
    /// Reads data from the ring buffer into `writer`.
    ///
    /// Returns the number of bytes read.
    fn read_fallible(&mut self, writer: &mut dyn MultiWrite) -> Result<usize>;

    /// Reads up to `max_len` bytes from the ring buffer into `writer`.
    ///
    /// Returns the number of bytes read.
    fn read_fallible_with_max_len(
        &mut self,
        writer: &mut dyn MultiWrite,
        max_len: usize,
    ) -> Result<usize>;
}

impl<R: Deref<Target = RingBuffer<u8, M>>, M: AnyUFrameMeta + ?Sized> ConsumerU8Ext
    for Consumer<u8, R, M>
{
    fn read_fallible(&mut self, writer: &mut dyn MultiWrite) -> Result<usize> {
        self.read_fallible_with_max_len(writer, usize::MAX)
    }

    fn read_fallible_with_max_len(
        &mut self,
        writer: &mut dyn MultiWrite,
        max_len: usize,
    ) -> Result<usize> {
        let len = self.len().min(max_len);
        let head = self.head();
        let read_len = self
            .ring_buffer()
            .pick_fallible(head..head + Wrapping(len), writer)?;
        self.commit_read(read_len);
        Ok(read_len)
    }
}

#[cfg(ktest)]
mod test {
    use alloc::vec;

    use ostd::prelude::*;

    use super::*;

    #[ktest]
    fn rb_write_read_one_with_ext() {
        let rb = RingBuffer::<u8>::new(1);

        let (mut prod, mut cons) = rb.split();

        let input = [u8::MAX];
        assert_eq!(
            prod.write_fallible(&mut reader_from(input.as_slice()))
                .unwrap(),
            1
        );
        assert_eq!(
            prod.write_fallible(&mut reader_from(input.as_slice()))
                .unwrap(),
            0
        );
        assert_eq!(prod.len(), 1);

        let mut output = [0u8];
        assert_eq!(
            cons.read_fallible(&mut writer_from(output.as_mut_slice()))
                .unwrap(),
            1
        );
        assert_eq!(
            cons.read_fallible(&mut writer_from(output.as_mut_slice()))
                .unwrap(),
            0
        );
        assert_eq!(cons.free_len(), 1);

        assert_eq!(output, input);
    }

    #[ktest]
    fn rb_write_read_all_with_ext() {
        let rb = RingBuffer::<u8>::new(4 * PAGE_SIZE);
        assert_eq!(rb.capacity(), 4 * PAGE_SIZE);

        let (mut prod, mut cons) = rb.split();

        let step = 128;
        let mut input = vec![0u8; step];
        for i in (0..4 * PAGE_SIZE).step_by(step) {
            input.fill(i as _);
            let write_len = prod
                .write_fallible(&mut reader_from(input.as_slice()))
                .unwrap();
            assert_eq!(write_len, step);
        }
        assert!(cons.is_full());

        let mut output = vec![0u8; step];
        for i in (0..4 * PAGE_SIZE).step_by(step) {
            let read_len = cons
                .read_fallible(&mut writer_from(output.as_mut_slice()))
                .unwrap();
            assert_eq!(read_len, step);
            assert_eq!(output[0], i as u8);
            assert_eq!(output[step - 1], i as u8);
        }
        assert!(prod.is_empty());
    }

    fn reader_from(buf: &[u8]) -> VmReader<'_> {
        VmReader::from(buf).to_fallible()
    }

    fn writer_from(buf: &mut [u8]) -> VmWriter<'_> {
        VmWriter::from(buf).to_fallible()
    }

    #[ktest]
    fn ipc_buffer_charges_original_pages_until_last_segment_alias() {
        use crate::vm::user_memory::UserMemoryAccount;
        let account = UserMemoryAccount::new(16);
        let owner = Some(account.clone());
        let buffer = new_user_ring_buffer(65536, &owner).unwrap();
        assert_eq!(account.current_pages(), 16);
        let last_page = buffer.segment().slice(&(15 * PAGE_SIZE..16 * PAGE_SIZE));
        let (mut producer, mut consumer) = buffer.split();
        let bytes = [7u8; 37];
        assert_eq!(
            producer
                .write_fallible(&mut VmReader::from(&bytes[..]).to_fallible())
                .unwrap(),
            bytes.len()
        );
        let mut read = [0u8; 37];
        assert_eq!(
            consumer
                .read_fallible(&mut VmWriter::from(&mut read[..]).to_fallible())
                .unwrap(),
            bytes.len()
        );
        assert_eq!(read, bytes);
        assert_eq!(account.current_pages(), 16);
        assert!(
            new_user_ring_buffer(1, &owner)
                .err()
                .unwrap()
                .is_user_frame_limit()
        );
        drop(producer);
        assert_eq!(account.current_pages(), 16);
        drop(consumer);
        assert_eq!(account.current_pages(), 1);
        drop(last_page);
        assert_eq!(account.current_pages(), 0);
        drop(new_user_ring_buffer(65536, &owner).unwrap());
        assert_eq!(account.current_pages(), 0);
        // Ordinary/unowned paths remain uncharged; they cannot change this owner.
        drop(RingBuffer::<u8>::new(65536));
        drop(new_user_ring_buffer(65536, &None).unwrap());
        assert_eq!(account.current_pages(), 0);
    }

    #[ktest]
    fn ipc_buffer_rejected_layout_and_allocator_failure_refund_owner() {
        use crate::vm::user_memory::{UserMemoryAccount, alloc_user_segment};
        let account = UserMemoryAccount::new(1);
        let owner = Some(account.clone());
        for capacity in [0, 3, 2 * PAGE_SIZE] {
            let segment = alloc_user_segment(&owner, 1).unwrap();
            assert_eq!(account.current_pages(), 1);
            assert!(RingBuffer::<u8, _>::from_segment(capacity, segment).is_err());
            assert_eq!(account.current_pages(), 0);
        }
        assert!(new_user_ring_buffer(3, &owner).is_err());
        assert!(alloc_user_segment(&owner, 0).is_err());
        assert_eq!(account.current_pages(), 0);

        // A valid 16-TiB layout exceeds the original allocator's maximum
        // order (8 TiB), independently of available RAM. This reaches the
        // actual physical-allocation error after admission; no frame is
        // fabricated and no global exhaustion/fault flag is installed.
        let pages = 1usize << 32;
        let large = UserMemoryAccount::new(pages);
        let error = new_user_ring_buffer(pages * PAGE_SIZE, &Some(large.clone()))
            .err()
            .unwrap();
        assert_eq!(error.error(), Errno::ENOMEM);
        assert!(!error.is_user_frame_limit());
        assert_eq!(large.current_pages(), 0);
        drop(new_user_ring_buffer(PAGE_SIZE, &Some(large.clone())).unwrap());
        assert_eq!(large.current_pages(), 0);
    }
}
