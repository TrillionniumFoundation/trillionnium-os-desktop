// SPDX-License-Identifier: MPL-2.0

use super::*;
use crate::{
    arch::{device::io_port::ReadWriteAccess, iommu::fault::test_fault_snapshot},
    io::{IoMem, IoPort},
    mm::VmIoOnce,
    prelude::ktest,
    task::Task,
};

struct Edu(IoMem);

impl Edu {
    fn open(device: u8) -> Self {
        // SAFETY: This feature's sole hardware test owns PCI configuration during
        // its OSTD-only guest. There are no upper-half PCI drivers. Only its fixed
        // EDU function's command register is written, after domain binding.
        let (address, data) = unsafe {
            (
                IoPort::<u32, ReadWriteAccess>::new(0xcf8),
                IoPort::<u32, ReadWriteAccess>::new(0xcfc),
            )
        };
        let select = |offset: u32| address.write(0x8000_0000 | (u32::from(device) << 11) | offset);
        select(0);
        assert_eq!(data.read(), 0x11e8_1234, "fixed EDU requester missing");
        select(0x10);
        let bar = data.read();
        assert_eq!(bar & 0xf, 0, "expected EDU 32-bit memory BAR");
        assert_ne!(bar, 0);
        select(4);
        let command = data.read();
        data.write((command & 0xffff) | 6);
        let memory = IoMem::acquire(bar as usize..bar as usize + 0x100000).unwrap();
        assert_eq!(memory.read_once::<u32>(0).unwrap() & 0xff, 0xed);
        Self(memory)
    }

    fn set_value(&self, scratch: &DeviceDmaBuffer, value: u32) {
        scratch.writer().write_val(&value).unwrap();
        self.transfer(scratch.daddr(), false);
    }

    fn value(&self, scratch: &DeviceDmaBuffer) -> u32 {
        scratch.writer().write_val(&0u32).unwrap();
        self.transfer(scratch.daddr(), true);
        scratch.reader().read_val().unwrap()
    }

    fn transfer(&self, address: Daddr, write_to_memory: bool) {
        let (source, destination) = if write_to_memory {
            (0x40000u64, address as u64)
        } else {
            (address as u64, 0x40000u64)
        };
        self.0.write_once(0x80, &source).unwrap();
        self.0.write_once(0x88, &destination).unwrap();
        self.0.write_once(0x90, &4u64).unwrap();
        self.0
            .write_once(0x98, &(if write_to_memory { 3u64 } else { 1u64 }))
            .unwrap();
        for _ in 0..2_000_000 {
            if self.0.read_once::<u64>(0x98).unwrap() & 1 == 0 {
                return;
            }
            Task::yield_now();
        }
        panic!("EDU DMA command did not complete");
    }
}

fn requester(device: u8) -> DmaRequester {
    DmaRequester {
        segment: 0,
        bus: 0,
        device,
        function: 0,
    }
}

fn denied_transfer(edu: &Edu, device: u8, address: Daddr, write: bool) {
    let before = test_fault_snapshot().0;
    edu.transfer(address, write);
    for _ in 0..100000 {
        let (count, last) = test_fault_snapshot();
        if count > before {
            assert_eq!(
                last & 0xffff,
                u64::from(device) << 3,
                "fault from another requester"
            );
            assert_ne!(last >> 16, 0, "missing hardware fault reason");
            return;
        }
        Task::yield_now();
    }
    panic!("denied DMA did not produce a requester-bound hardware fault");
}

#[ktest]
fn dma_domains_two_edu_devices_reject_cross_access_and_revoked_iova() {
    assert!(matches!(
        DeviceDmaDomain::bind(requester(0)),
        Err(DmaDomainError::UnsupportedRequester)
    ));
    if !super::super::has_dma_remapping() {
        assert!(matches!(
            DeviceDmaDomain::bind(requester(5)),
            Err(DmaDomainError::NoIommu)
        ));
        crate::early_println!("HEPTA_DMA_DOMAINS_NO_IOMMU_REJECTED");
        return;
    }
    let first = match DeviceDmaDomain::bind(requester(5)) {
        Ok(domain) => domain,
        Err(DmaDomainError::UnsupportedPlatform) => {
            crate::early_println!("HEPTA_DMA_DOMAINS_UNSUPPORTED_REJECTED");
            return;
        }
        other => panic!("unexpected binding result: {other:?}"),
    };
    let second = DeviceDmaDomain::bind(requester(6)).unwrap();
    assert!(matches!(
        DeviceDmaDomain::bind(requester(5)),
        Err(DmaDomainError::AlreadyBound)
    ));
    assert!(matches!(first.alloc(0), Err(DmaDomainError::InvalidSize)));
    let edu_a = Edu::open(5);
    let edu_b = Edu::open(6);
    let a = first.alloc(1).unwrap();
    let b = second.alloc(1).unwrap();
    let scratch_a = first.alloc(1).unwrap();
    let scratch_b = second.alloc(1).unwrap();
    a.writer().write_val(&0xaabb_1122u32).unwrap();
    b.writer().write_val(&0xccdd_3344u32).unwrap();
    edu_a.transfer(a.daddr(), false);
    edu_b.transfer(b.daddr(), false);
    assert_eq!(edu_a.value(&scratch_a), 0xaabb_1122);
    assert_eq!(edu_b.value(&scratch_b), 0xccdd_3344);
    edu_a.set_value(&scratch_a, 0xaaaa_5555);
    edu_a.transfer(a.daddr(), true);
    assert_eq!(a.reader().read_val::<u32>().unwrap(), 0xaaaa_5555);
    edu_b.set_value(&scratch_b, 0xbbbb_6666);
    edu_b.transfer(b.daddr(), true);
    assert_eq!(b.reader().read_val::<u32>().unwrap(), 0xbbbb_6666);

    denied_transfer(&edu_a, 5, b.daddr(), true);
    assert_eq!(b.reader().read_val::<u32>().unwrap(), 0xbbbb_6666);
    denied_transfer(&edu_b, 6, a.daddr(), true);
    assert_eq!(a.reader().read_val::<u32>().unwrap(), 0xaaaa_5555);
    denied_transfer(&edu_a, 5, b.daddr(), false);
    assert_ne!(edu_a.value(&scratch_a), 0xbbbb_6666);
    denied_transfer(&edu_b, 6, a.daddr(), false);
    assert_ne!(edu_b.value(&scratch_b), 0xaaaa_5555);

    let old = a.daddr();
    let revoked = a.revoke();
    edu_a.set_value(&scratch_a, 0xdead_beef);
    denied_transfer(&edu_a, 5, old, true);
    assert_eq!(revoked.reader().read_val::<u32>().unwrap(), 0xaaaa_5555);
    // Exercise real hardware queue wrap, not just descriptor encodings.
    for _ in 0..192 {
        drop(first.alloc(1).unwrap());
    }
    let held = first.alloc(1).unwrap();
    drop(scratch_a);
    drop(first);
    assert!(matches!(
        DeviceDmaDomain::bind(requester(5)),
        Err(DmaDomainError::AlreadyBound)
    ));
    drop(held);
    let rebound = DeviceDmaDomain::bind(requester(5)).unwrap();
    denied_transfer(&edu_a, 5, old, true);
    assert_eq!(revoked.reader().read_val::<u32>().unwrap(), 0xaaaa_5555);
    drop(rebound);
    drop((b, scratch_b, second));
    crate::early_println!(
        "HEPTA_DMA_DOMAINS_EDU_PASS cross-read cross-write revoke rebind queue-wrap"
    );
}
