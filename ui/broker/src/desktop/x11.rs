//! A caller-selected, process-pinned X11 connection. No DISPLAY discovery,
//! shell, process launch, reconnect, or authority issuance lives here.
use std::io::{self, IoSlice};
use std::os::fd::AsRawFd;
use std::os::unix::net::UnixStream;
use std::sync::Mutex;
use std::time::{Duration, Instant};
use trill_ui_core::desktop::{InputEvent, NotInjectedReason, MAX_HEIGHT, MAX_WIDTH};
use x11rb::connection::Connection;
use x11rb::protocol::xproto::{self, ConnectionExt, EventMask, ImageFormat, ImageOrder, MapState};
use x11rb::protocol::{xtest::ConnectionExt as _, Event};
use x11rb::rust_connection::{DefaultStream, PollMode, RustConnection, Stream};
use x11rb::utils::RawFdContainer;

const NATIVE_DEADLINE: Duration = Duration::from_millis(500);
struct DeadlineStream {
    stream: DefaultStream,
    deadline: Mutex<Instant>,
}

impl DeadlineStream {
    fn remaining(&self) -> io::Result<Duration> {
        self.deadline
            .lock()
            .map_err(|_| io::Error::other("X11 deadline poisoned"))?
            .checked_duration_since(Instant::now())
            .filter(|d| !d.is_zero())
            .ok_or_else(|| io::Error::new(io::ErrorKind::TimedOut, "X11 total deadline"))
    }
    fn begin(&self) {
        *self.deadline.lock().expect("single X11 owner") = Instant::now() + NATIVE_DEADLINE;
    }
}
impl Stream for DeadlineStream {
    fn poll(&self, mode: PollMode) -> io::Result<()> {
        loop {
            let left = self.remaining()?;
            let mut fd = libc::pollfd {
                fd: self.stream.as_raw_fd(),
                events: (if mode.readable() { libc::POLLIN } else { 0 })
                    | (if mode.writable() { libc::POLLOUT } else { 0 }),
                revents: 0,
            };
            // fd is borrowed from the retained stream; poll writes this one stack entry.
            let n = unsafe {
                libc::poll(
                    &mut fd,
                    1,
                    left.as_millis().max(1).min(i32::MAX as u128) as i32,
                )
            };
            if n > 0 {
                self.remaining()?;
                return Ok(());
            }
            if n == 0 {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "X11 total deadline",
                ));
            }
            let e = io::Error::last_os_error();
            if e.kind() != io::ErrorKind::Interrupted {
                return Err(e);
            }
        }
    }
    fn read(&self, buf: &mut [u8], fds: &mut Vec<RawFdContainer>) -> io::Result<usize> {
        self.remaining()?;
        self.stream.read(buf, fds)
    }
    fn write(&self, buf: &[u8], fds: &mut Vec<RawFdContainer>) -> io::Result<usize> {
        self.remaining()?;
        self.stream.write(buf, fds)
    }
    fn write_vectored(
        &self,
        bufs: &[IoSlice<'_>],
        fds: &mut Vec<RawFdContainer>,
    ) -> io::Result<usize> {
        self.remaining()?;
        self.stream.write_vectored(bufs, fds)
    }
}

pub struct X11Pixels {
    pub width: u16,
    pub height: u16,
    pub rgb: Vec<u8>,
}
pub enum NativeInput {
    Injected,
    NotInjected(NotInjectedReason),
    Unknown,
}

pub struct NativeX11 {
    connection: Option<RustConnection<DeadlineStream>>,
    root: u32,
    window: u32,
    width: u16,
    height: u16,
    destroyed: bool,
}
fn io_error(e: impl std::fmt::Display) -> io::Error {
    io::Error::other(e.to_string())
}

impl NativeX11 {
    /// `stream` has not sent its X11 setup packet. The launcher alone chooses
    /// and authenticates this display; cookie bytes never enter renderer IPC.
    pub fn from_stream(
        stream: UnixStream,
        expected_server_pid: u32,
        window: u32,
        cookie: Option<Vec<u8>>,
    ) -> io::Result<Self> {
        let peer = trill_ui_core::host_peer::linux_socket_peer_credentials(&stream)?;
        if expected_server_pid == 0
            || peer.pid != expected_server_pid as i32
            || peer.uid != trill_ui_core::host_peer::current_effective_uid()
            || window == 0
        {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "X11 exact server process mismatch",
            ));
        }
        if cookie.as_ref().is_some_and(|c| c.len() != 16) {
            return Err(io::Error::other("X11 cookie must be 16 bytes"));
        }
        let (stream, _) = DefaultStream::from_unix_stream(stream)?;
        let stream = DeadlineStream {
            stream,
            deadline: Mutex::new(Instant::now() + NATIVE_DEADLINE),
        };
        let (name, data) = cookie
            .map(|data| (b"MIT-MAGIC-COOKIE-1".to_vec(), data))
            .unwrap_or_default();
        let connection = RustConnection::connect_to_stream_with_auth_info(stream, 0, name, data)
            .map_err(io_error)?;
        connection
            .xtest_get_version(2, 2)
            .map_err(io_error)?
            .reply()
            .map_err(io_error)?;
        let screen = &connection.setup().roots[0];
        let (root, width, height) = (screen.root, screen.width_in_pixels, screen.height_in_pixels);
        if width == 0 || height == 0 || width > i16::MAX as u16 || height > i16::MAX as u16 {
            return Err(io::Error::other("X11 screen dimensions unsupported"));
        }
        connection
            .change_window_attributes(
                window,
                &xproto::ChangeWindowAttributesAux::new().event_mask(EventMask::STRUCTURE_NOTIFY),
            )
            .map_err(io_error)?
            .check()
            .map_err(io_error)?;
        let mut value = Self {
            connection: Some(connection),
            root,
            window,
            width,
            height,
            destroyed: false,
        };
        value
            .geometry()
            .map_err(|_| io::Error::other("selected X11 window unavailable"))?;
        Ok(value)
    }
    pub fn dimensions(&self) -> (u16, u16) {
        (self.width, self.height)
    }
    pub fn window(&self) -> u32 {
        self.window
    }
    fn geometry(&mut self) -> Result<xproto::GetGeometryReply, NotInjectedReason> {
        if self.destroyed {
            return Err(NotInjectedReason::WindowUnavailable);
        }
        let c = self
            .connection
            .as_ref()
            .ok_or(NotInjectedReason::WindowUnavailable)?;
        // Structure events permanently invalidate this identity on destruction;
        // a reused XID is not a continuation of the selected window.
        let mut drained = false;
        for _ in 0..256 {
            match c
                .poll_for_event()
                .map_err(|_| NotInjectedReason::WindowUnavailable)?
            {
                Some(Event::DestroyNotify(e)) if e.window == self.window => {
                    self.destroyed = true;
                    return Err(NotInjectedReason::WindowUnavailable);
                }
                Some(_) => {}
                None => {
                    drained = true;
                    break;
                }
            }
        }
        if !drained {
            // An event flood cannot hide a queued DestroyNotify behind the
            // per-call bound and thereby make a recycled XID look continuous.
            self.destroyed = true;
            return Err(NotInjectedReason::WindowUnavailable);
        }
        let attrs = c
            .get_window_attributes(self.window)
            .map_err(|_| NotInjectedReason::WindowUnavailable)?
            .reply()
            .map_err(|_| NotInjectedReason::WindowUnavailable)?;
        let g = c
            .get_geometry(self.window)
            .map_err(|_| NotInjectedReason::WindowUnavailable)?
            .reply()
            .map_err(|_| NotInjectedReason::WindowUnavailable)?;
        if attrs.map_state != MapState::VIEWABLE
            || g.root != self.root
            || g.width == 0
            || g.height == 0
        {
            return Err(NotInjectedReason::WindowUnavailable);
        }
        Ok(g)
    }
    pub fn inject(&mut self, events: &[InputEvent]) -> NativeInput {
        let Some(c) = self.connection.as_ref() else {
            return NativeInput::Unknown;
        };
        c.stream().begin();
        // Server grab serializes client-originated focus/window changes with
        // preflight+injection. It does not isolate physical input or other X11
        // clients; this capability is explicitly the whole trusted display.
        if c.grab_server()
            .and_then(|c| {
                c.check().map_err(|e| match e {
                    x11rb::errors::ReplyError::ConnectionError(e) => e,
                    _ => x11rb::errors::ConnectionError::UnknownError,
                })
            })
            .is_err()
        {
            self.connection.take();
            return NativeInput::Unknown;
        }
        let result = self.inject_grabbed(events);
        if let Some(c) = self.connection.as_ref() {
            if c.ungrab_server().is_err() || c.flush().is_err() {
                self.connection.take();
                return NativeInput::Unknown;
            }
        }
        if matches!(result, NativeInput::Unknown) {
            self.connection.take();
        }
        result
    }
    fn inject_grabbed(&mut self, events: &[InputEvent]) -> NativeInput {
        if let Err(reason) = self.geometry() {
            return NativeInput::NotInjected(reason);
        }
        let c = self.connection.as_ref().expect("connected X11");
        let preflight = (|| -> Result<(), NotInjectedReason> {
            let focus = c
                .get_input_focus()
                .map_err(|_| NotInjectedReason::FocusMismatch)?
                .reply()
                .map_err(|_| NotInjectedReason::FocusMismatch)?;
            if focus.focus != self.window {
                return Err(NotInjectedReason::FocusMismatch);
            }
            let keymap = c
                .query_keymap()
                .map_err(|_| NotInjectedReason::InputAlreadyHeld)?
                .reply()
                .map_err(|_| NotInjectedReason::InputAlreadyHeld)?;
            if keymap.keys.iter().any(|k| *k != 0) {
                return Err(NotInjectedReason::InputAlreadyHeld);
            }
            let pointer = c
                .query_pointer(self.window)
                .map_err(|_| NotInjectedReason::PointerOutside)?
                .reply()
                .map_err(|_| NotInjectedReason::PointerOutside)?;
            if u16::from(pointer.mask) & 0x1f00 != 0 {
                return Err(NotInjectedReason::InputAlreadyHeld);
            }
            let mut location = (pointer.root_x, pointer.root_y);
            for event in events {
                match *event {
                    InputEvent::PointerMove { x, y } => {
                        if x >= self.width || y >= self.height {
                            return Err(NotInjectedReason::PointerOutside);
                        }
                        location = (x as i16, y as i16);
                    }
                    InputEvent::PointerButton { .. } => {}
                    InputEvent::Key { .. } => continue,
                }
                // Root-child identity prevents injecting clicks into a window
                // covered by another top-level window at the selected point.
                let translated = c
                    .translate_coordinates(self.root, self.root, location.0, location.1)
                    .map_err(|_| NotInjectedReason::PointerOutside)?
                    .reply()
                    .map_err(|_| NotInjectedReason::PointerOutside)?;
                if translated.child != self.window {
                    return Err(NotInjectedReason::PointerOutside);
                }
            }
            Ok(())
        })();
        if let Err(reason) = preflight {
            return NativeInput::NotInjected(reason);
        }
        // No NotInjected return is permitted below this line: any prefix may
        // already be processed even when the next request/reply fails.
        for event in events {
            let (kind, detail, x, y) = match *event {
                InputEvent::Key { keycode, pressed } => {
                    (if pressed { 2 } else { 3 }, keycode, 0, 0)
                }
                InputEvent::PointerButton { button, pressed } => {
                    (if pressed { 4 } else { 5 }, button, 0, 0)
                }
                InputEvent::PointerMove { x, y } => (6, 0, x as i16, y as i16),
            };
            let sent = (|| -> Result<(), String> {
                c.xtest_fake_input(kind, detail, 0, self.root, x, y, 0)
                    .map_err(|e| e.to_string())?
                    .check()
                    .map_err(|e| e.to_string())
            })();
            if sent.is_err() {
                return NativeInput::Unknown;
            }
        }
        if c.get_input_focus()
            .ok()
            .and_then(|r| r.reply().ok())
            .is_none()
        {
            NativeInput::Unknown
        } else {
            NativeInput::Injected
        }
    }
    pub fn capture(&mut self) -> io::Result<X11Pixels> {
        let c = self
            .connection
            .as_ref()
            .ok_or_else(|| io::Error::other("X11 disconnected"))?;
        c.stream().begin();
        let grabbed = c
            .grab_server()
            .map_err(io_error)
            .and_then(|cookie| cookie.check().map_err(io_error));
        if let Err(error) = grabbed {
            self.connection.take();
            return Err(error);
        }
        // Capture uses the same lifecycle boundary as input. Otherwise a
        // destroyed/reused XID between geometry and GetImage could be labelled
        // with the previous window's identity.
        let mut result = self.capture_inner();
        if let Some(c) = self.connection.as_ref() {
            if c.ungrab_server().is_err() || c.flush().is_err() {
                result = Err(io::Error::other("X11 capture release failed"));
            }
        }
        if result.is_err() {
            self.connection.take();
        }
        result
    }
    fn capture_inner(&mut self) -> io::Result<X11Pixels> {
        let g = self
            .geometry()
            .map_err(|_| io::Error::other("selected window unavailable"))?;
        if g.width > MAX_WIDTH || g.height > MAX_HEIGHT {
            return Err(io::Error::other("capture exceeds bounded dimensions"));
        }
        let c = self.connection.as_ref().expect("connected X11");
        let image = c
            .get_image(
                ImageFormat::Z_PIXMAP,
                self.window,
                0,
                0,
                g.width,
                g.height,
                u32::MAX,
            )
            .map_err(io_error)?
            .reply()
            .map_err(io_error)?;
        let format = c
            .setup()
            .pixmap_formats
            .iter()
            .find(|f| f.depth == image.depth)
            .ok_or_else(|| io::Error::other("unknown pixel layout"))?;
        let visual = c.setup().roots[0]
            .allowed_depths
            .iter()
            .flat_map(|d| d.visuals.iter())
            .find(|v| v.visual_id == image.visual)
            .ok_or_else(|| io::Error::other("unknown visual"))?;
        if format.bits_per_pixel != 32
            || format.scanline_pad != 32
            || visual.red_mask != 0xff0000
            || visual.green_mask != 0xff00
            || visual.blue_mask != 0xff
            || image.data.len() != usize::from(g.width) * usize::from(g.height) * 4
        {
            return Err(io::Error::other("unsupported bounded X11 pixel layout"));
        }
        let mut rgb = Vec::with_capacity(usize::from(g.width) * usize::from(g.height) * 3);
        for pixel in image.data.chunks_exact(4) {
            let b: [u8; 4] = pixel.try_into().expect("pixel chunk");
            let p = if c.setup().image_byte_order == ImageOrder::LSB_FIRST {
                u32::from_le_bytes(b)
            } else {
                u32::from_be_bytes(b)
            };
            rgb.extend_from_slice(&[(p >> 16) as u8, (p >> 8) as u8, p as u8]);
        }
        Ok(X11Pixels {
            width: g.width,
            height: g.height,
            rgb,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn wrong_server_process_is_refused_before_x11_setup() {
        let (stream, mut peer) = UnixStream::pair().unwrap();
        assert!(
            NativeX11::from_stream(stream, std::process::id().saturating_add(1), 1, None).is_err()
        );
        peer.set_read_timeout(Some(Duration::from_millis(100)))
            .unwrap();
        use std::io::Read;
        assert_eq!(peer.read(&mut [0]).unwrap(), 0);
    }
    #[test]
    fn silent_x11_setup_cannot_exceed_native_total_deadline() {
        let (stream, _peer) = UnixStream::pair().unwrap();
        let start = Instant::now();
        assert!(NativeX11::from_stream(stream, std::process::id(), 1, None).is_err());
        assert!(start.elapsed() < Duration::from_millis(1200));
    }
}
