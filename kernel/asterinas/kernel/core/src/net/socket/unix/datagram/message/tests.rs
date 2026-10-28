// SPDX-License-Identifier: MPL-2.0

//! Regression tests for the Organ resource-isolation audit: real datagrams
//! must own fallible physical backing without changing packet publication.
//! The guest probe separately verifies current POSIX sender/cgroup ownership.

use ostd::{
    mm::{HasPaddr, HasSize, Infallible},
    prelude::ktest,
};

use super::*;

fn send(source: &MessageReceiver, target: &MessageReceiver, bytes: &[u8]) -> Result<usize> {
    target.queue.try_send(
        &mut VmReader::from(bytes).to_fallible(),
        &mut AuxiliaryData::default(),
        source,
    )
}

fn receive(target: &MessageReceiver, bytes: &mut [u8], flags: RecvFlags) -> RecvOutput {
    let (output, controls, _) = target
        .try_recv(&mut VmWriter::from(bytes).to_fallible(), flags)
        .unwrap();
    assert!(controls.is_empty());
    output
}

#[ktest]
fn datagram_peek_preserves_packet_and_never_exposes_physical_page_tail() {
    let source = MessageReceiver::new();
    let target = MessageReceiver::new();
    let input = vec![0x3b; PAGE_SIZE + 17];
    assert_eq!(send(&source, &target, &input).unwrap(), input.len());
    {
        let inner = target.queue.inner.lock();
        let message = inner.as_ref().unwrap().messages.front().unwrap();
        assert_eq!(message.bytes.size(), 2 * PAGE_SIZE);
        assert_eq!(message.len, input.len());
    }
    let mut output = vec![0xa7; 3 * PAGE_SIZE];
    let result = receive(&target, &mut output, RecvFlags::MSG_PEEK);
    assert_eq!(result.len(), input.len());
    assert!(result.flags().is_empty());
    assert_eq!(&output[..input.len()], input.as_slice());
    assert!(output[input.len()..].iter().all(|byte| *byte == 0xa7));
    assert_eq!(
        target.queue.inner.lock().as_ref().unwrap().messages.len(),
        1
    );
    assert_eq!(
        receive(&target, &mut output, RecvFlags::empty()).len(),
        input.len()
    );
    assert!(
        target
            .queue
            .inner
            .lock()
            .as_ref()
            .unwrap()
            .messages
            .is_empty()
    );
}

#[ktest]
fn empty_datagrams_retain_distinct_real_pages_and_consume_one_packet_each() {
    let source = MessageReceiver::new();
    let target = MessageReceiver::new();
    assert_eq!(send(&source, &target, &[]).unwrap(), 0);
    assert_eq!(send(&source, &target, &[]).unwrap(), 0);
    {
        let inner = target.queue.inner.lock();
        let inner = inner.as_ref().unwrap();
        assert_eq!(inner.messages.len(), 2);
        assert_eq!(inner.total_length, 0);
        assert!(
            inner
                .messages
                .iter()
                .all(|message| message.bytes.size() == PAGE_SIZE)
        );
        assert_ne!(
            inner.messages[0].bytes.paddr(),
            inner.messages[1].bytes.paddr()
        );
    }
    assert_eq!(receive(&target, &mut [], RecvFlags::MSG_PEEK).len(), 0);
    assert_eq!(
        target.queue.inner.lock().as_ref().unwrap().messages.len(),
        2
    );
    assert_eq!(receive(&target, &mut [], RecvFlags::empty()).len(), 0);
    assert_eq!(
        target.queue.inner.lock().as_ref().unwrap().messages.len(),
        1
    );
    assert_eq!(receive(&target, &mut [], RecvFlags::empty()).len(), 0);
    assert!(
        target
            .queue
            .inner
            .lock()
            .as_ref()
            .unwrap()
            .messages
            .is_empty()
    );
}

#[ktest]
fn full_datagram_preserves_original_byte_ceiling_and_truncated_receive_length() {
    let source = MessageReceiver::new();
    let target = MessageReceiver::new();
    let input = vec![0x62; UNIX_DATAGRAM_DEFAULT_BUF_SIZE];
    assert_eq!(send(&source, &target, &input).unwrap(), input.len());
    assert_eq!(
        send(&source, &target, b"x").unwrap_err().error(),
        Errno::EAGAIN
    );
    let mut output = [0; 13];
    let result = receive(&target, &mut output, RecvFlags::MSG_TRUNC);
    assert_eq!(result.len(), UNIX_DATAGRAM_DEFAULT_BUF_SIZE);
    assert_eq!(result.flags(), RecvFlags::MSG_TRUNC);
    assert_eq!(output, [0x62; 13]);
    assert_eq!(target.queue.inner.lock().as_ref().unwrap().total_length, 0);
    assert_eq!(send(&source, &target, b"retry").unwrap(), 5);
    assert_eq!(receive(&target, &mut output, RecvFlags::empty()).len(), 5);
    assert_eq!(&output[..5], b"retry");
}

struct FaultAfterPrefix;

impl ReadCString for FaultAfterPrefix {
    fn read_cstring_until_nul(&mut self, _: usize) -> Result<Option<CString>> {
        unreachable!("packet copy is binary")
    }

    fn read_cstring_until_end(&mut self, _: usize) -> Result<(CString, usize)> {
        unreachable!("packet copy is binary")
    }
}

impl MultiRead for FaultAfterPrefix {
    fn read(
        &mut self,
        writer: &mut VmWriter<'_, Infallible>,
    ) -> Result<usize, (ostd::Error, usize)> {
        assert_eq!(VmReader::from(b"prefix".as_slice()).read(writer), 6);
        Err((ostd::Error::PageFault, 6))
    }

    fn sum_lens(&self) -> usize {
        7
    }

    fn skip_some(&mut self, _: usize) {
        unreachable!("packet copy must not skip source bytes")
    }
}

#[ktest]
fn failed_datagram_copy_does_not_publish_prefix_or_change_existing_packet() {
    let source = MessageReceiver::new();
    let target = MessageReceiver::new();
    send(&source, &target, b"original").unwrap();
    let error = target.queue.try_send(
        &mut FaultAfterPrefix,
        &mut AuxiliaryData::default(),
        &source,
    );
    assert_eq!(error.unwrap_err().error(), Errno::EFAULT);
    {
        let inner = target.queue.inner.lock();
        let inner = inner.as_ref().unwrap();
        assert_eq!(inner.messages.len(), 1);
        assert_eq!(inner.total_length, 8);
    }
    let mut output = [0; 16];
    assert_eq!(receive(&target, &mut output, RecvFlags::empty()).len(), 8);
    assert_eq!(&output[..8], b"original");
}

struct FaultingWriter;

struct ShortSource;

impl ReadCString for ShortSource {
    fn read_cstring_until_nul(&mut self, _: usize) -> Result<Option<CString>> {
        unreachable!("packet copy is binary")
    }

    fn read_cstring_until_end(&mut self, _: usize) -> Result<(CString, usize)> {
        unreachable!("packet copy is binary")
    }
}

impl MultiRead for ShortSource {
    fn read(&mut self, _: &mut VmWriter<'_, Infallible>) -> Result<usize, (ostd::Error, usize)> {
        Ok(0)
    }

    fn sum_lens(&self) -> usize {
        1
    }

    fn skip_some(&mut self, _: usize) {
        unreachable!("packet copy must not skip source bytes")
    }
}

#[ktest]
fn incomplete_internal_source_never_publishes_uninitialized_payload() {
    let source = MessageReceiver::new();
    let target = MessageReceiver::new();
    assert_eq!(
        target
            .queue
            .try_send(&mut ShortSource, &mut AuxiliaryData::default(), &source)
            .unwrap_err()
            .error(),
        Errno::EFAULT
    );
    assert!(
        target
            .queue
            .inner
            .lock()
            .as_ref()
            .unwrap()
            .messages
            .is_empty()
    );
    assert_eq!(target.queue.inner.lock().as_ref().unwrap().total_length, 0);
}

impl MultiWrite for FaultingWriter {
    fn write(
        &mut self,
        reader: &mut VmReader<'_, Infallible>,
    ) -> Result<usize, (ostd::Error, usize)> {
        let mut prefix = [0; 2];
        assert_eq!(reader.read(&mut VmWriter::from(prefix.as_mut_slice())), 2);
        Err((ostd::Error::PageFault, 2))
    }

    fn sum_lens(&self) -> usize {
        8
    }

    fn skip_some(&mut self, _: usize) {
        unreachable!("packet copy must not skip destination bytes")
    }
}

#[ktest]
fn failed_datagram_receive_retains_whole_packet_for_actual_retry() {
    let source = MessageReceiver::new();
    let target = MessageReceiver::new();
    send(&source, &target, b"original").unwrap();
    assert_eq!(
        target
            .try_recv(&mut FaultingWriter, RecvFlags::empty())
            .err()
            .unwrap()
            .error(),
        Errno::EFAULT
    );
    assert_eq!(
        target.queue.inner.lock().as_ref().unwrap().messages.len(),
        1
    );
    let mut output = [0; 8];
    assert_eq!(receive(&target, &mut output, RecvFlags::empty()).len(), 8);
    assert_eq!(&output, b"original");
}

#[ktest]
fn dropping_receiver_clears_queue_but_extra_physical_reference_keeps_bytes() {
    let source = MessageReceiver::new();
    let target = MessageReceiver::new();
    send(&source, &target, b"held").unwrap();
    let queue = target.queue.clone();
    let held = queue
        .inner
        .lock()
        .as_ref()
        .unwrap()
        .messages
        .front()
        .unwrap()
        .bytes
        .clone();
    drop(target);
    assert!(queue.inner.lock().is_none());
    assert_eq!(
        queue
            .try_send(
                &mut VmReader::from(b"x".as_slice()).to_fallible(),
                &mut AuxiliaryData::default(),
                &source
            )
            .unwrap_err()
            .error(),
        Errno::ECONNREFUSED
    );
    let mut output = [0; 4];
    assert_eq!(
        held.reader()
            .read(&mut VmWriter::from(output.as_mut_slice())),
        4
    );
    assert_eq!(&output, b"held");
}

#[ktest]
fn oversized_datagram_leaves_no_message_or_physical_backing_published() {
    let source = MessageReceiver::new();
    let target = MessageReceiver::new();
    let input = vec![0; UNIX_DATAGRAM_DEFAULT_BUF_SIZE + 1];
    assert_eq!(
        send(&source, &target, &input).unwrap_err().error(),
        Errno::EMSGSIZE
    );
    let inner = target.queue.inner.lock();
    let inner = inner.as_ref().unwrap();
    assert!(inner.messages.is_empty());
    assert_eq!(inner.total_length, 0);
}
