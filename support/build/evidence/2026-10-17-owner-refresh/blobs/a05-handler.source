// SPDX-License-Identifier: MPL-2.0

//! Read-only HOS2 bootstrap at /dev/hepta-control. No management authority is
//! granted by open, dup, fork, or this QueryAbi operation. The native resource
//! effects must be wired to a trusted CapSpace/ResourceDomain before enabling
//! any additional opcode. This is deliberately an experimental ioctl number.

use core::sync::atomic::{AtomicU64, Ordering};

use device_id::{DeviceId, MinorId};
use ostd::mm::VmIo;
use spin::Once;

use crate::{
    context::current_userspace,
    device::{Device, DeviceType, registry::char},
    events::IoEvents,
    fs::{
        devtmpfs::DevtmpfsNodeMeta,
        file::{PerOpenFileOps, StatusFlags},
        vfs::{inode::FileOps, path::Path},
    },
    hos2_os_abi::{
        self as wire, Opcode, QueryAbiResponse, RequestPayload, Response, ResponsePayload, Status,
        Transport,
    },
    prelude::*,
    process::signal::{PollHandle, Pollable},
    util::{ioctl::RawIoctl, random},
};

// _IOWR('H', 2, sizeof(Transport32)).  This number is test-only until A00
// assigns a public ioctl. It does not silently reuse the old HOS1 command.
const EXPERIMENTAL_HOS2_IOCTL: u32 = 0xC020_4802;
const QUERY_FRAME_BYTES: usize = wire::HEADER_LEN;
const QUERY_RESPONSE_BYTES: usize = wire::HEADER_LEN + 48;

static MAJOR: Once<char::MajorIdOwner> = Once::new();
static BOOT_ID: Once<[u8; 16]> = Once::new();
static NEXT_SESSION: AtomicU64 = AtomicU64::new(1);

fn nonzero_random_id() -> [u8; 16] {
    let mut id = [0u8; 16];
    random::getrandom(&mut id);
    // Even if an early emulator RNG were to return zeroes, never produce an
    // invalid HOS2 identity. No identity here is an authorization token.
    id[0] |= 1;
    id
}

// A monotonic per-boot nonce prevents collision and fails closed at the
// lifetime boundary. It is not a substitute for the real process CapSpace.
fn new_session_id() -> Result<[u8; 16]> {
    let counter = loop {
        let old = NEXT_SESSION.load(Ordering::Acquire);
        if old == u64::MAX {
            return_errno_with_message!(Errno::ENOSPC, "HOS2 session identity exhausted");
        }
        if NEXT_SESSION
            .compare_exchange(old, old + 1, Ordering::AcqRel, Ordering::Acquire)
            .is_ok()
        {
            break old;
        }
    };
    let mut id = [0u8; 16];
    id[..8].copy_from_slice(&BOOT_ID.get().unwrap()[..8]);
    id[8..].copy_from_slice(&counter.to_le_bytes());
    Ok(id)
}

#[derive(Debug)]
struct HeptaControlDevice {
    id: DeviceId,
}

impl Device for HeptaControlDevice {
    fn type_(&self) -> DeviceType {
        DeviceType::Char
    }

    fn id(&self) -> DeviceId {
        self.id
    }

    fn devtmpfs_meta(&self) -> Option<DevtmpfsNodeMeta> {
        // Default devtmpfs ownership is root:root and mode 0600; actual
        // kernel CapSpace grants must be verified separately for effects.
        Some(DevtmpfsNodeMeta::new("hepta-control").unwrap())
    }

    fn open(&self) -> Result<Box<dyn PerOpenFileOps>> {
        Ok(Box::new(HeptaControlFile {
            space_id: new_session_id()?,
        }))
    }
}

struct HeptaControlFile {
    space_id: [u8; 16],
}

impl Pollable for HeptaControlFile {
    fn poll(&self, mask: IoEvents, _poller: Option<&mut PollHandle>) -> IoEvents {
        mask & (IoEvents::IN | IoEvents::OUT)
    }
}

impl FileOps for HeptaControlFile {
    fn read_at(
        &self,
        _offset: usize,
        _writer: &mut VmWriter,
        _status_flags: StatusFlags,
    ) -> Result<usize> {
        return_errno_with_message!(Errno::EINVAL, "HOS2 requires the ioctl transport")
    }

    fn write_at(
        &self,
        _offset: usize,
        _reader: &mut VmReader,
        _status_flags: StatusFlags,
    ) -> Result<usize> {
        return_errno_with_message!(Errno::EINVAL, "HOS2 does not accept stream writes")
    }
}

impl PerOpenFileOps for HeptaControlFile {
    fn check_seekable(&self) -> Result<()> {
        return_errno_with_message!(Errno::ESPIPE, "HOS2 sessions are not seekable")
    }

    fn is_offset_aware(&self) -> bool {
        false
    }

    fn ioctl(&self, _path: &Path, raw_ioctl: RawIoctl) -> Result<i32> {
        if raw_ioctl.cmd() != EXPERIMENTAL_HOS2_IOCTL {
            return_errno_with_message!(Errno::ENOTTY, "not a recognized HOS2 ioctl")
        }

        // Copy the transport once. Every address and length is validated
        // before copying the nested request; no effect can occur on failure.
        let mut transport_bytes = [0u8; wire::TRANSPORT_LEN];
        current_userspace!().read_bytes(raw_ioctl.arg(), &mut transport_bytes)?;
        let transport = Transport::decode(&transport_bytes)
            .map_err(|_| Error::with_message(Errno::EINVAL, "malformed HOS2 transport"))?;
        if transport.request_bytes as usize != QUERY_FRAME_BYTES {
            return_errno_with_message!(Errno::ENOTTY, "only HOS2 QueryAbi is implemented")
        }
        let request_ptr = usize::try_from(transport.request_addr)
            .map_err(|_| Error::with_message(Errno::EINVAL, "invalid request address"))?;
        let response_ptr = usize::try_from(transport.response_addr)
            .map_err(|_| Error::with_message(Errno::EINVAL, "invalid response address"))?;
        let mut input = [0u8; QUERY_FRAME_BYTES];
        current_userspace!().read_bytes(request_ptr, &mut input)?;
        let request = transport
            .decode_request_snapshot(&input)
            .map_err(|_| Error::with_message(Errno::EINVAL, "invalid HOS2 request"))?;
        if request.opcode != Opcode::QueryAbi || request.payload != RequestPayload::QueryAbi {
            return_errno_with_message!(Errno::ENOTTY, "HOS2 resource operations not yet enabled")
        }

        // The advertised mask has *only* QueryAbi (bit 1). This creates no
        // grant, does not install a CPU budget and cannot retire delivery.
        let response = Response {
            opcode: Opcode::QueryAbi,
            status: Status::Ok,
            request_id: request.request_id,
            boot_id: *BOOT_ID.get().unwrap(),
            revision: 0,
            payload: ResponsePayload::QueryAbi(QueryAbiResponse {
                space_id: self.space_id,
                page_size: u32::try_from(PAGE_SIZE).unwrap(),
                max_request_payload: 0,
                max_response_payload: 48,
                supported_ops: 1u64 << Opcode::QueryAbi.as_u16(),
                features: 0,
            }),
        };
        let mut output = [0u8; QUERY_RESPONSE_BYTES];
        let bytes = wire::encode_response(&response, &mut output)
            .map_err(|_| Error::with_message(Errno::EINVAL, "invalid HOS2 response"))?;
        current_userspace!().write_bytes(response_ptr, &output[..bytes])?;
        Ok(0)
    }
}

pub(super) fn init_in_first_kthread() {
    BOOT_ID.call_once(nonzero_random_id);
    let major = MAJOR.call_once(|| char::allocate_major().unwrap()).get();
    char::register(Arc::new(HeptaControlDevice {
        id: DeviceId::new(major, MinorId::new(0)),
    }))
    .expect("register read-only HOS2 bootstrap");
}
