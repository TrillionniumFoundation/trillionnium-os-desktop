//! Read one original, still-borrowed composed frame for an owned-window request.
//!
//! The caller is the normal `present` path, after its task/buffer availability
//! checks and before returning that frame to Android. Neither a numeric buffer
//! name nor retained pixels grant permission to read a later buffer generation.
//! Layer streams need their own complete composition; their black root carrier
//! is deliberately not a composed application frame.

use super::{AcceptedWireFrame, RenderTarget};
use drm_fourcc::DrmFourcc;
use flate2::{Compression, write::ZlibEncoder};
use std::{
    io::{self, Write},
    mem::{MaybeUninit, size_of},
    os::fd::{AsFd, AsRawFd, BorrowedFd},
    ptr::NonNull,
    time::{Duration, Instant},
};
use thiserror::Error;

const MAX_DIMENSION: u32 = 4096;
const MAX_PIXELS: usize = 8 * 1024 * 1024;
const MAX_MAP_BYTES: usize = 128 * 1024 * 1024;
pub(super) const MAX_PNG_BYTES: usize = 36 * 1024 * 1024;
const FENCE_TIMEOUT: Duration = Duration::from_millis(200);
const SYNC_RETRY_TIMEOUT: Duration = Duration::from_millis(100);
// Linux UAPI: _IOW('b', 0, struct dma_buf_sync), containing exactly one u64.
const DMA_BUF_IOCTL_SYNC: libc::c_ulong = (1 << 30) | (8 << 16) | ((b'b' as libc::c_ulong) << 8);
const DMA_BUF_SYNC_READ: u64 = 1;
const DMA_BUF_SYNC_END: u64 = 4;

#[derive(Debug, Error)]
pub(super) enum CaptureError {
    #[error("owned frame capture refused: {0}")]
    Refused(&'static str),
    #[error("owned frame capture does not support {0}")]
    Unsupported(&'static str),
    #[error("original acquire fence did not signal within the capture bound")]
    FenceTimeout,
    #[error("owned frame capture {operation}: {source}")]
    Io {
        operation: &'static str,
        #[source]
        source: io::Error,
    },
}
fn io_error(operation: &'static str, source: io::Error) -> CaptureError {
    CaptureError::Io { operation, source }
}

/// Copied pixels are an observation of these original frame identities only.
/// They carry no descriptor and cannot authorize a subsequent input or close.
#[derive(Debug)]
pub(super) struct CapturedFrame {
    pub object: u64,
    pub frame: u64,
    pub buffer: u64,
    pub width: u32,
    pub height: u32,
    pub captured_monotonic_ns: u64,
    pub png: Vec<u8>,
}

#[derive(Clone, Copy, Debug)]
struct Layout {
    width: u32,
    height: u32,
    offset: usize,
    stride: usize,
    row_bytes: usize,
    map_bytes: usize,
    rgba_bytes: usize,
    has_alpha: bool,
}
impl Layout {
    fn checked(
        metadata: &droidloom_denial_protocol::BufferMetadata,
        planes: usize,
    ) -> Result<Self, CaptureError> {
        if !cfg!(target_endian = "little") {
            return Err(CaptureError::Unsupported("non-little-endian pixel storage"));
        }
        if metadata.format.modifier != 0 {
            return Err(CaptureError::Unsupported("a non-linear DMA-BUF modifier"));
        }
        let has_alpha = match metadata.format.fourcc {
            value if value == DrmFourcc::Argb8888 as u32 => true,
            value if value == DrmFourcc::Xrgb8888 as u32 => false,
            _ => {
                return Err(CaptureError::Unsupported(
                    "a format other than ARGB8888/XRGB8888",
                ));
            }
        };
        if planes != 1 || metadata.planes.len() != 1 || metadata.planes[0].index != 0 {
            return Err(CaptureError::Unsupported(
                "a multi-plane or noncanonical plane layout",
            ));
        }
        let (width, height) = (metadata.width, metadata.height);
        if width == 0 || height == 0 || width > MAX_DIMENSION || height > MAX_DIMENSION {
            return Err(CaptureError::Refused(
                "dimensions are outside the capture bound",
            ));
        }
        let pixels = (width as usize)
            .checked_mul(height as usize)
            .filter(|value| *value <= MAX_PIXELS)
            .ok_or(CaptureError::Refused(
                "pixel count is outside the capture bound",
            ))?;
        let row_bytes = (width as usize)
            .checked_mul(4)
            .ok_or(CaptureError::Refused("pixel row overflow"))?;
        let offset = metadata.planes[0].offset as usize;
        let stride = metadata.planes[0].stride as usize;
        if stride < row_bytes || stride % 4 != 0 || offset % 4 != 0 {
            return Err(CaptureError::Refused("unaligned or short DMA-BUF row"));
        }
        let map_bytes = (height as usize - 1)
            .checked_mul(stride)
            .and_then(|n| n.checked_add(offset))
            .and_then(|n| n.checked_add(row_bytes))
            .filter(|n| *n <= MAX_MAP_BYTES)
            .ok_or(CaptureError::Refused(
                "DMA-BUF span exceeds the capture bound",
            ))?;
        Ok(Self {
            width,
            height,
            offset,
            stride,
            row_bytes,
            map_bytes,
            rgba_bytes: pixels * 4,
            has_alpha,
        })
    }
}

// Linux sync_file.h. A zero component count requests the original sync-file's
// aggregate state without disclosing driver names or allocating a fence array.
#[repr(C)]
#[derive(Default)]
struct SyncFileInfo {
    name: [u8; 32],
    status: i32,
    flags: u32,
    num_fences: u32,
    pad: u32,
    sync_fence_info: u64,
}
fn fence_state(fd: BorrowedFd<'_>) -> Result<i32, CaptureError> {
    let mut info = SyncFileInfo::default();
    let request: libc::c_ulong = (3 << 30)
        | ((size_of::<SyncFileInfo>() as libc::c_ulong) << 16)
        | ((b'>' as libc::c_ulong) << 8)
        | 4;
    // SAFETY: this exact repr(C) UAPI object is writable for the whole ioctl;
    // num_fences and its pointer are zero, so no out-of-line buffer is supplied.
    let result = unsafe { libc::ioctl(fd.as_raw_fd(), request, &mut info) };
    if result != 0 {
        return Err(io_error("SYNC_IOC_FILE_INFO", io::Error::last_os_error()));
    }
    if info.status < 0 {
        return Err(CaptureError::Refused(
            "original acquire fence completed with an error",
        ));
    }
    Ok(info.status)
}
fn wait_acquire(fd: BorrowedFd<'_>) -> Result<(), CaptureError> {
    let deadline = Instant::now() + FENCE_TIMEOUT;
    loop {
        if fence_state(fd)? > 0 {
            return Ok(());
        }
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err(CaptureError::FenceTimeout);
        }
        let millis = i32::try_from(remaining.as_millis().max(1))
            .map_err(|_| CaptureError::Refused("fence wait duration overflow"))?;
        let mut entry = libc::pollfd {
            fd: fd.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        // SAFETY: one live pollfd is writable; the original fence stays borrowed.
        let result = unsafe { libc::poll(&mut entry, 1, millis) };
        if result < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(io_error("poll original acquire fence", error));
        }
        if result == 0 {
            return Err(CaptureError::FenceTimeout);
        }
        if entry.revents & (libc::POLLERR | libc::POLLHUP | libc::POLLNVAL) != 0 {
            return Err(CaptureError::Refused(
                "original acquire fence reported a poll error",
            ));
        }
        if entry.revents & libc::POLLIN == 0 {
            return Err(CaptureError::Refused(
                "original acquire fence did not report readable completion",
            ));
        }
        // A readable arbitrary fd is insufficient: repeat the actual sync-file
        // ioctl and require its own successful, permanently signalled state.
    }
}

fn dma_sync(fd: BorrowedFd<'_>, flags: u64) -> Result<(), CaptureError> {
    let deadline = Instant::now() + SYNC_RETRY_TIMEOUT;
    loop {
        let request_flags = flags;
        // SAFETY: dma_buf_sync is exactly one u64 and this kernel operation reads
        // it for the duration of this call. The caller retains the original fd.
        let result = unsafe { libc::ioctl(fd.as_raw_fd(), DMA_BUF_IOCTL_SYNC, &request_flags) };
        if result == 0 {
            return Ok(());
        }
        let error = io::Error::last_os_error();
        if matches!(error.raw_os_error(), Some(libc::EINTR | libc::EAGAIN))
            && Instant::now() < deadline
        {
            std::thread::yield_now();
            continue;
        }
        return Err(io_error(
            if flags & DMA_BUF_SYNC_END == 0 {
                "DMA_BUF_IOCTL_SYNC READ START"
            } else {
                "DMA_BUF_IOCTL_SYNC READ END"
            },
            error,
        ));
    }
}
struct CpuRead<'a> {
    fd: BorrowedFd<'a>,
    active: bool,
}
impl<'a> CpuRead<'a> {
    fn start(fd: BorrowedFd<'a>) -> Result<Self, CaptureError> {
        dma_sync(fd, DMA_BUF_SYNC_READ)?;
        Ok(Self { fd, active: true })
    }
    fn finish(mut self) -> Result<(), CaptureError> {
        dma_sync(self.fd, DMA_BUF_SYNC_READ | DMA_BUF_SYNC_END)?;
        self.active = false;
        Ok(())
    }
}
impl Drop for CpuRead<'_> {
    fn drop(&mut self) {
        if self.active {
            let _ = dma_sync(self.fd, DMA_BUF_SYNC_READ | DMA_BUF_SYNC_END);
        }
    }
}
struct Mapping {
    address: NonNull<libc::c_void>,
    length: usize,
}
impl Mapping {
    fn read_only(fd: BorrowedFd<'_>, length: usize) -> Result<Self, CaptureError> {
        // SAFETY: no requested address, bounded positive length, read-only shared
        // access to the original checked DMA-BUF. No byte is read before START.
        let address = unsafe {
            libc::mmap(
                std::ptr::null_mut(),
                length,
                libc::PROT_READ,
                libc::MAP_SHARED,
                fd.as_raw_fd(),
                0,
            )
        };
        if address == libc::MAP_FAILED {
            return Err(io_error(
                "mmap original DMA-BUF read-only",
                io::Error::last_os_error(),
            ));
        }
        let Some(address) = NonNull::new(address) else {
            // SAFETY: even a zero-address successful mapping must be released.
            unsafe {
                libc::munmap(address, length);
            }
            return Err(CaptureError::Refused(
                "DMA-BUF mapping returned a null address",
            ));
        };
        Ok(Self { address, length })
    }
    fn bytes(&self) -> &[u8] {
        // SAFETY: only this live bounded, read-only mapping is exposed; the
        // caller still owns the frame loan and active DMA-BUF CPU-read bracket.
        unsafe { std::slice::from_raw_parts(self.address.as_ptr().cast::<u8>(), self.length) }
    }
}
impl Drop for Mapping {
    fn drop(&mut self) {
        // SAFETY: this object uniquely owns this exact mmap interval.
        unsafe {
            libc::munmap(self.address.as_ptr(), self.length);
        }
    }
}
fn copied_rgba(bytes: &[u8], layout: Layout) -> Result<Vec<u8>, CaptureError> {
    if bytes.len() < layout.map_bytes {
        return Err(CaptureError::Refused(
            "mapped DMA-BUF is shorter than the validated span",
        ));
    }
    let mut rgba = Vec::new();
    rgba.try_reserve_exact(layout.rgba_bytes)
        .map_err(|_| CaptureError::Refused("pixel allocation could not be reserved"))?;
    for y in 0..layout.height as usize {
        let start = layout.offset + y * layout.stride;
        for pixel in bytes[start..start + layout.row_bytes].chunks_exact(4) {
            let alpha = if layout.has_alpha { pixel[3] } else { 255 };
            // Wayland ARGB pixels are premultiplied. PNG carries straight alpha;
            // recover that representation, never exposing hidden RGB at alpha 0.
            let straight = |component: u8| -> u8 {
                if alpha == 0 {
                    0
                } else {
                    ((u32::from(component) * 255 + u32::from(alpha) / 2) / u32::from(alpha))
                        .min(255) as u8
                }
            };
            rgba.extend_from_slice(&[
                straight(pixel[2]),
                straight(pixel[1]),
                straight(pixel[0]),
                alpha,
            ]);
        }
    }
    Ok(rgba)
}
fn read_pixels(fd: BorrowedFd<'_>, layout: Layout) -> Result<Vec<u8>, CaptureError> {
    let mut state = MaybeUninit::<libc::stat>::uninit();
    // SAFETY: a successful fstat fully initializes this writable stat object.
    if unsafe { libc::fstat(fd.as_raw_fd(), state.as_mut_ptr()) } != 0 {
        return Err(io_error(
            "fstat original DMA-BUF",
            io::Error::last_os_error(),
        ));
    }
    // SAFETY: the preceding fstat succeeded.
    let state = unsafe { state.assume_init() };
    if state.st_size <= 0
        || u64::try_from(layout.map_bytes).unwrap_or(u64::MAX) > state.st_size as u64
    {
        return Err(CaptureError::Refused(
            "original DMA-BUF allocation is smaller than its pixel span",
        ));
    }
    let cpu = CpuRead::start(fd)?;
    let mapping = Mapping::read_only(fd, layout.map_bytes)?;
    let pixels = copied_rgba(mapping.bytes(), layout);
    drop(mapping);
    cpu.finish()?;
    pixels
}

struct BoundedBytes(Vec<u8>);
impl Write for BoundedBytes {
    fn write(&mut self, value: &[u8]) -> io::Result<usize> {
        if self
            .0
            .len()
            .checked_add(value.len())
            .is_none_or(|n| n > MAX_PNG_BYTES - 128)
        {
            return Err(io::Error::other("encoded PNG exceeds the capture bound"));
        }
        self.0
            .try_reserve(value.len())
            .map_err(|_| io::Error::other("PNG allocation failed"))?;
        self.0.extend_from_slice(value);
        Ok(value.len())
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}
const fn crc_table() -> [u32; 256] {
    let mut table = [0; 256];
    let mut i = 0;
    while i < 256 {
        let mut value = i as u32;
        let mut bit = 0;
        while bit < 8 {
            value = if value & 1 != 0 {
                0xedb8_8320 ^ (value >> 1)
            } else {
                value >> 1
            };
            bit += 1;
        }
        table[i] = value;
        i += 1;
    }
    table
}
const CRC: [u32; 256] = crc_table();
fn crc32(parts: &[&[u8]]) -> u32 {
    let mut state = u32::MAX;
    for part in parts {
        for &byte in *part {
            state = CRC[((state ^ u32::from(byte)) & 255) as usize] ^ (state >> 8);
        }
    }
    !state
}
fn png_chunk(output: &mut Vec<u8>, kind: &[u8; 4], data: &[u8]) -> Result<(), CaptureError> {
    let length =
        u32::try_from(data.len()).map_err(|_| CaptureError::Refused("PNG chunk overflow"))?;
    if output
        .len()
        .checked_add(data.len())
        .and_then(|n| n.checked_add(12))
        .is_none_or(|n| n > MAX_PNG_BYTES)
    {
        return Err(CaptureError::Refused("PNG exceeds its complete byte bound"));
    }
    output
        .try_reserve(data.len() + 12)
        .map_err(|_| CaptureError::Refused("PNG allocation failed"))?;
    output.extend_from_slice(&length.to_be_bytes());
    output.extend_from_slice(kind);
    output.extend_from_slice(data);
    output.extend_from_slice(&crc32(&[kind, data]).to_be_bytes());
    Ok(())
}
fn encode_png(layout: Layout, rgba: &[u8]) -> Result<Vec<u8>, CaptureError> {
    if rgba.len() != layout.rgba_bytes {
        return Err(CaptureError::Refused("incomplete captured pixels"));
    }
    let mut encoder = ZlibEncoder::new(BoundedBytes(Vec::new()), Compression::fast());
    for row in rgba.chunks_exact(layout.width as usize * 4) {
        encoder
            .write_all(&[0])
            .map_err(|e| io_error("PNG row filter", e))?;
        encoder
            .write_all(row)
            .map_err(|e| io_error("PNG row compression", e))?;
    }
    let compressed = encoder
        .finish()
        .map_err(|e| io_error("PNG compression finish", e))?
        .0;
    let mut output = Vec::new();
    output.extend_from_slice(b"\x89PNG\r\n\x1a\n");
    let mut header = [0u8; 13];
    header[..4].copy_from_slice(&layout.width.to_be_bytes());
    header[4..8].copy_from_slice(&layout.height.to_be_bytes());
    header[8] = 8;
    header[9] = 6; // Eight-bit RGBA, ordinary zlib, no interlace.
    png_chunk(&mut output, b"IHDR", &header)?;
    png_chunk(&mut output, b"IDAT", &compressed)?;
    png_chunk(&mut output, b"IEND", &[])?;
    Ok(output)
}
fn monotonic_ns() -> Result<u64, CaptureError> {
    let mut time = libc::timespec {
        tv_sec: 0,
        tv_nsec: 0,
    };
    // SAFETY: the writable timespec remains alive for this clock query.
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut time) } != 0 {
        return Err(io_error(
            "capture monotonic timestamp",
            io::Error::last_os_error(),
        ));
    }
    u64::try_from(time.tv_sec)
        .ok()
        .and_then(|s| s.checked_mul(1_000_000_000))
        .and_then(|s| {
            u64::try_from(time.tv_nsec)
                .ok()
                .and_then(|n| s.checked_add(n))
        })
        .ok_or(CaptureError::Refused("invalid capture monotonic timestamp"))
}

/// Call synchronously for the just-accepted normal composed frame only. The
/// normal caller must retain its original task and frame loan through return.
pub(super) fn capture(
    target: &RenderTarget,
    frame: &AcceptedWireFrame,
    acquire_fence: BorrowedFd<'_>,
) -> Result<CapturedFrame, CaptureError> {
    if target.busy || target.retired || frame.buffer != target.metadata.id {
        return Err(CaptureError::Refused(
            "original target is busy, retired or belongs to another frame",
        ));
    }
    let layout = Layout::checked(&target.metadata, target.planes.len())?;
    wait_acquire(acquire_fence)?;
    let rgba = read_pixels(target.planes[0].as_fd(), layout)?;
    let captured_monotonic_ns = monotonic_ns()?;
    let png = encode_png(layout, &rgba)?;
    Ok(CapturedFrame {
        object: frame.object.0,
        frame: frame.frame.0,
        buffer: frame.buffer.0,
        width: layout.width,
        height: layout.height,
        captured_monotonic_ns,
        png,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use droidloom_denial_protocol::{BufferId, BufferMetadata, FormatModifier, PlaneMetadata};
    use std::io::Read;
    fn metadata() -> BufferMetadata {
        BufferMetadata {
            id: BufferId(1),
            width: 2,
            height: 2,
            format: FormatModifier {
                fourcc: DrmFourcc::Argb8888 as u32,
                modifier: 0,
            },
            planes: vec![PlaneMetadata {
                index: 0,
                offset: 4,
                stride: 12,
            }],
        }
    }
    #[test]
    fn capture_respects_padding_offset_and_premultiplied_alpha() {
        let layout = Layout::checked(&metadata(), 1).unwrap();
        let pixels = [
            9, 9, 9, 9, 0, 0, 128, 128, 255, 0, 0, 255, 9, 9, 9, 9, 0, 255, 0, 255, 77, 99, 111, 0,
        ];
        assert_eq!(
            copied_rgba(&pixels, layout).unwrap(),
            [255, 0, 0, 128, 0, 0, 255, 255, 0, 255, 0, 255, 0, 0, 0, 0]
        );
        assert!(copied_rgba(&pixels[..pixels.len() - 1], layout).is_err());
        let mut xrgb = metadata();
        xrgb.format.fourcc = DrmFourcc::Xrgb8888 as u32;
        assert_eq!(
            &copied_rgba(&pixels, Layout::checked(&xrgb, 1).unwrap()).unwrap()[12..],
            &[111, 99, 77, 255]
        );
    }
    #[test]
    fn capture_refuses_unbounded_unsupported_and_inconsistent_layouts() {
        let base = metadata();
        let mut zero = base.clone();
        zero.width = 0;
        let mut wide = base.clone();
        wide.width = MAX_DIMENSION + 1;
        let mut stride = base.clone();
        stride.planes[0].stride = 4;
        let mut offset = base.clone();
        offset.planes[0].offset = u32::MAX - 3;
        let mut tiled = base.clone();
        tiled.format.modifier = 1;
        let mut plane = base.clone();
        plane.planes[0].index = 1;
        let mut pixels = base.clone();
        pixels.width = 4096;
        pixels.height = 4096;
        for invalid in [zero, wide, stride, offset, tiled, plane, pixels] {
            assert!(Layout::checked(&invalid, 1).is_err());
        }
        assert!(Layout::checked(&base, 0).is_err());
        assert!(Layout::checked(&base, 2).is_err());
    }
    #[test]
    fn an_ordinary_real_file_is_neither_a_sync_file_nor_a_dma_buf() {
        let file = tempfile::tempfile().unwrap();
        file.set_len(4096).unwrap();
        assert!(fence_state(file.as_fd()).is_err());
        assert!(wait_acquire(file.as_fd()).is_err());
        assert!(read_pixels(file.as_fd(), Layout::checked(&metadata(), 1).unwrap()).is_err());
    }
    #[test]
    fn bounded_png_has_standard_checksums_and_decodable_exact_pixels() {
        assert_eq!(crc32(&[b"123456789"]), 0xcbf4_3926);
        assert_eq!(crc32(&[b"IEND"]), 0xae42_6082);
        let layout = Layout::checked(&metadata(), 1).unwrap();
        let pixels = [255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 1, 2, 3, 128];
        let png = encode_png(layout, &pixels).unwrap();
        assert_eq!(&png[..8], b"\x89PNG\r\n\x1a\n");
        assert_eq!(&png[12..16], b"IHDR");
        assert_eq!(&png[16..24], &[0, 0, 0, 2, 0, 0, 0, 2]);
        assert_eq!(&png[24..29], &[8, 6, 0, 0, 0]);
        assert_eq!(&png[37..41], b"IDAT");
        let compressed_len = u32::from_be_bytes(png[33..37].try_into().unwrap()) as usize;
        let mut decoded = Vec::new();
        flate2::read::ZlibDecoder::new(&png[41..41 + compressed_len])
            .read_to_end(&mut decoded)
            .unwrap();
        let expected = [&[0][..], &pixels[..8], &[0][..], &pixels[8..]].concat();
        assert_eq!(decoded, expected);
        assert_eq!(
            &png[png.len() - 12..],
            &[0, 0, 0, 0, b'I', b'E', b'N', b'D', 0xae, 0x42, 0x60, 0x82]
        );
        let mut bounded = BoundedBytes(Vec::new());
        assert!(bounded.write_all(&vec![0; MAX_PNG_BYTES]).is_err());
    }
}
