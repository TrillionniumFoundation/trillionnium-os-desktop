// SPDX-License-Identifier: MPL-2.0

mod addr;
mod cred;
mod ctrl_msg;
mod datagram;
mod ns;
mod ownership;
mod stream;

pub(crate) use addr::UnixSocketAddr;
pub(crate) use cred::CUserCred;
pub(super) use ctrl_msg::UnixControlMessage;
pub(super) use datagram::UNIX_DATAGRAM_DEFAULT_BUF_SIZE;
pub(crate) use datagram::UnixDatagramSocket;
pub(super) use stream::UNIX_STREAM_DEFAULT_BUF_SIZE;
pub(crate) use stream::UnixStreamSocket;

#[cfg(ktest)]
pub(crate) fn rights_message_for_test(
    files: alloc::vec::Vec<alloc::sync::Arc<dyn crate::fs::file::FileLike>>,
) -> crate::net::socket::util::ControlMessage {
    crate::net::socket::util::ControlMessage::Unix(UnixControlMessage::from_files_for_test(files))
}
