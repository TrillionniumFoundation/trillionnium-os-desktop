// SPDX-License-Identifier: MPL-2.0

#![expect(dead_code)]

//! Remapping structures of DMAR table.
//!
//! This file defines these structures and provides a `Debug` implementation to see the value
//! inside these structures.
//!
//! Most of the introduction are copied from Intel vt-directed-io-specification.

use alloc::{borrow::ToOwned, string::String, vec::Vec};
use core::fmt::Debug;

use ostd_pod::Pod;

/// DMA-remapping hardware unit definition (DRHD).
///
/// A DRHD structure uniquely represents a remapping hardware unit present in the platform.
/// There must be at least one instance of this structure for each PCI segment in the platform.
#[derive(Clone, Debug)]
pub(in crate::arch) struct Drhd {
    header: DrhdHeader,
    device_scopes: Vec<DeviceScope>,
}

impl Drhd {
    pub(in crate::arch) fn register_base_addr(&self) -> u64 {
        self.header.register_base_addr
    }

    /// Root-bus, function-zero requesters explicitly covered by this unit.
    /// Bridge paths and other segments are deliberately not inferred.
    pub(in crate::arch) fn root_function_zero_coverage(&self) -> u32 {
        if self.header.segment_num != 0 {
            return 0;
        }
        if self.header.flags & 1 != 0 {
            return u32::MAX;
        }
        self.device_scopes.iter().fold(0, |mask, scope| {
            if scope.header.typ == 1
                && scope.header.start_bus_number == 0
                && scope.path.len() == 1
                && scope.path[0].0 < 32
                && scope.path[0].1 == 0
            {
                mask | (1 << scope.path[0].0)
            } else {
                mask
            }
        })
    }
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Pod)]
struct DrhdHeader {
    typ: u16,
    length: u16,
    flags: u8,
    size: u8,
    segment_num: u16,
    register_base_addr: u64,
}

/// Reserved Memory Region Reporting (RMRR).
///
/// BIOS allocated reserved memory ranges that may be DMA targets.
/// It may report each such reserved memory region through the RMRR structures, along
/// with the devices that requires access to the specified reserved memory region.
#[derive(Clone, Debug)]
pub(in crate::arch) struct Rmrr {
    header: RmrrHeader,
    device_scopes: Vec<DeviceScope>,
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Pod)]
struct RmrrHeader {
    typ: u16,
    length: u16,
    reserved: u16,
    segment_num: u16,
    reserved_memory_region_base_addr: u64,
    reserved_memory_region_limit_addr: u64,
}

/// Root Port ATS Capability Reporting (ATSR).
///
/// This structure is applicable only for platforms supporting Device-TLBs as reported through the
/// Extended Capability Register.
#[derive(Clone, Debug)]
pub(in crate::arch) struct Atsr {
    header: AtsrHeader,
    device_scopes: Vec<DeviceScope>,
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Pod)]
struct AtsrHeader {
    typ: u16,
    length: u16,
    flags: u8,
    reserved: u8,
    segment_num: u16,
}

/// Remapping Hardware Status Affinity (RHSA).
///
/// It is applicable for platforms supporting non-uniform memory (NUMA),
/// where Remapping hardware units spans across nodes.
/// This optional structure provides the association between each Remapping hardware unit (identified
/// by its respective Base Address) and the proximity domain to which that hardware unit belongs.
#[padding_struct]
#[repr(C)]
#[derive(Clone, Copy, Debug, Pod)]
pub(in crate::arch) struct Rhsa {
    typ: u16,
    length: u16,
    flags: u32,
    register_base_addr: u64,
    proximity_domain: u32,
}

/// ACPI Name-space Device Declaration (ANDD).
///
/// An ANDD structure uniquely represents an ACPI name-space
/// enumerated device capable of issuing DMA requests in the platform.
#[derive(Clone, Debug)]
pub(in crate::arch) struct Andd {
    header: AnddHeader,
    acpi_object_name: String,
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Pod)]
struct AnddHeader {
    typ: u16,
    length: u16,
    reserved: [u8; 3],
    acpi_device_num: u8,
}

/// SoC Integrated Address Translation Cache (SATC).
///
/// The SATC reporting structure identifies devices that have address translation cache (ATC),
/// as defined by the PCI Express Base Specification.
#[derive(Clone, Debug)]
pub(in crate::arch) struct Satc {
    header: SatcHeader,
    device_scopes: Vec<DeviceScope>,
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Pod)]
struct SatcHeader {
    typ: u16,
    length: u16,
    flags: u8,
    reserved: u8,
    segment_num: u16,
}

/// SoC Integrated Device Property Reporting (SIDP).
///
/// The (SIDP) reporting structure identifies devices that have special
/// properties and that may put restrictions on how system software must configure remapping
/// structures that govern such devices in a platform where remapping hardware is enabled.
#[derive(Clone, Debug)]
pub(in crate::arch) struct Sidp {
    header: SidpHeader,
    device_scopes: Vec<DeviceScope>,
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Pod)]
struct SidpHeader {
    typ: u16,
    length: u16,
    reserved: u16,
    segment_num: u16,
}

/// The Device Scope Structure is made up of Device Scope Entries. Each Device Scope Entry may be
/// used to indicate a PCI endpoint device
#[derive(Clone, Debug)]
struct DeviceScope {
    header: DeviceScopeHeader,
    path: Vec<(u8, u8)>,
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Pod)]
struct DeviceScopeHeader {
    typ: u8,
    length: u8,
    flags: u8,
    reserved: u8,
    enum_id: u8,
    start_bus_number: u8,
}

macro_rules! impl_from_bytes {
    ($(($struct:tt, $header_struct:tt),)*) => {
        $(impl $struct {
            #[doc = concat!("Parses a [`", stringify!($struct), "`] from bytes.")]
            ///
            /// # Panics
            ///
            #[doc = concat!(
                "This method may panic if the bytes do not represent a valid [`",
                stringify!($struct),
                "`].",
            )]
            pub(super) fn from_bytes(bytes: &[u8]) -> Self {
                let header = $header_struct::from_first_bytes(bytes);
                debug_assert_eq!(header.length as usize, bytes.len());

                let mut index = size_of::<$header_struct>();
                let mut device_scopes = Vec::new();
                while index != (header.length as usize) {
                    let val = DeviceScope::from_bytes_prefix(&bytes[index..]);
                    index += val.header.length as usize;
                    device_scopes.push(val);
                }

                Self{
                    header,
                    device_scopes,
                }
            }
        })*
    };
}

impl_from_bytes!(
    (Drhd, DrhdHeader),
    (Rmrr, RmrrHeader),
    (Atsr, AtsrHeader),
    (Satc, SatcHeader),
    (Sidp, SidpHeader),
);

impl DeviceScope {
    /// Parses a [`DeviceScope`] from a prefix of the bytes.
    ///
    /// # Panics
    ///
    /// This method may panic if the byte prefix does not represent a valid [`DeviceScope`].
    fn from_bytes_prefix(bytes: &[u8]) -> Self {
        let header = DeviceScopeHeader::from_first_bytes(bytes);
        debug_assert!((header.length as usize) <= bytes.len());

        let mut index = size_of::<DeviceScopeHeader>();
        debug_assert!((header.length as usize) >= index);

        let mut path = Vec::new();
        while index != (header.length as usize) {
            let val = (bytes[index], bytes[index + 1]);
            path.push(val);
            index += 2;
        }

        Self { header, path }
    }
}

impl Rhsa {
    /// Parses an [`Rhsa`] from the bytes.
    ///
    /// # Panics
    ///
    /// This method may panic if the bytes do not represent a valid [`Rhsa`].
    pub(super) fn from_bytes(bytes: &[u8]) -> Self {
        let val = <Self as Pod>::from_first_bytes(bytes);
        debug_assert_eq!(val.length as usize, bytes.len());

        val
    }
}

impl Andd {
    /// Parses an [`Andd`] from the bytes.
    ///
    /// # Panics
    ///
    /// This method may panic if the bytes do not represent a valid [`Andd`].
    pub(super) fn from_bytes(bytes: &[u8]) -> Self {
        let header = AnddHeader::from_first_bytes(bytes);
        debug_assert_eq!(header.length as usize, bytes.len());

        let header_len = size_of::<AnddHeader>();
        let acpi_object_name = core::str::from_utf8(&bytes[header_len..])
            .unwrap()
            .to_owned();

        Self {
            header,
            acpi_object_name,
        }
    }
}

#[cfg(ktest)]
mod tests {
    use super::*;
    use crate::prelude::ktest;

    #[ktest]
    fn domain_coverage_does_not_infer_bridges_other_functions_or_segments() {
        let mut drhd = Drhd {
            header: DrhdHeader {
                typ: 0,
                length: 16,
                flags: 0,
                size: 0,
                segment_num: 0,
                register_base_addr: 0xfed90000,
            },
            device_scopes: Vec::new(),
        };
        assert_eq!(drhd.root_function_zero_coverage(), 0);
        let scope = |typ, bus, path| DeviceScope {
            header: DeviceScopeHeader {
                typ,
                length: 8,
                flags: 0,
                reserved: 0,
                enum_id: 0,
                start_bus_number: bus,
            },
            path,
        };
        drhd.device_scopes.push(scope(1, 0, alloc::vec![(5, 0)]));
        drhd.device_scopes.push(scope(1, 0, alloc::vec![(6, 1)]));
        drhd.device_scopes.push(scope(1, 1, alloc::vec![(7, 0)]));
        drhd.device_scopes
            .push(scope(1, 0, alloc::vec![(8, 0), (0, 0)]));
        drhd.device_scopes.push(scope(2, 0, alloc::vec![(9, 0)]));
        drhd.device_scopes.push(scope(1, 0, alloc::vec![(32, 0)]));
        assert_eq!(drhd.root_function_zero_coverage(), 1 << 5);
        drhd.header.flags = 1;
        assert_eq!(drhd.root_function_zero_coverage(), u32::MAX);
        drhd.header.segment_num = 1;
        assert_eq!(drhd.root_function_zero_coverage(), 0);
    }
}
