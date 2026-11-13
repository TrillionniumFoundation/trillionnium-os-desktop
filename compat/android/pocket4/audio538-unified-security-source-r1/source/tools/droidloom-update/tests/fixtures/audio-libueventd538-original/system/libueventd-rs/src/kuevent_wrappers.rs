use crate::errors::Error;
use futures::Stream;
use kobject_uevent::UEvent;
use netlink_sys::constants::NETLINK_KOBJECT_UEVENT;
use netlink_sys::Socket;
use netlink_sys::SocketAddr;
use tokio::io::unix::AsyncFd;

/// The netlink group for kernel uevents.
const KOBJ_NL_GROUP_UEVENT: u32 = 1;

/// Creates a stream of `UEvent` messages from the kernel.
///
/// This function sets up a `NETLINK_KOBJECT_UEVENT` netlink socket and
/// returns a `Stream` that yields parsed `UEvent`s as they are received.
/// # Returns
/// A `Result` containing a `Stream` that yields `Result<UEvent, Error>` for each event from the
/// kernel, or an `Error` if the socket could not be set up.
pub fn uevent_stream() -> Result<impl Stream<Item = Result<UEvent, Error>>, Error> {
    // 1. Create and bind the netlink socket
    let addr = SocketAddr::new(0, KOBJ_NL_GROUP_UEVENT);
    let mut socket = Socket::new(NETLINK_KOBJECT_UEVENT).map_err(Error::CreateSocket)?;
    socket.bind(&addr).map_err(Error::BindSocket)?;

    // 2. Wrap the socket in Tokio's AsyncFd for non-blocking I/O
    //
    // It must be manually set nonblocking, otherwise recv in the loop
    // will block waiting for data instead of returning back to the reactor.
    socket.set_non_blocking(true).map_err(Error::SetSocketNonBlocking)?;
    let async_fd = AsyncFd::new(socket).map_err(Error::CreateSocket)?;

    Ok(async_stream::try_stream! {
        loop {
            // Wait until the socket is readable
            let mut guard = async_fd.readable().await.map_err(Error::Recv)?;
            // Try to receive data from the socket
            match guard.try_io(|inner| {
                inner.get_ref().recv_from_full()
            }) {
                Ok(Ok((buf, _addr))) => {
                    let uevent = UEvent::from_netlink_packet(&buf)
                        .map_err(|e| Error::ParseFailure(e.to_string()))?;
                    yield uevent;
                },
                Ok(Err(_)) => { continue; }
                Err(_) => { continue; }
            }
        }
    })
}
