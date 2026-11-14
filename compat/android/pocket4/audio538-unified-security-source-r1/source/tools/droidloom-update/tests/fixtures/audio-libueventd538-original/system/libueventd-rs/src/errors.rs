// Copyright (C) 2025 The Android Open Source Project
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

extern crate rtnetlink;

use std::io;

/// Represents an error that may be returned by functions in this library.
#[derive(Debug, thiserror::Error)]
pub enum Error {
    /// Underlying IO error.
    #[error("IO error: {0}")]
    IOError(#[from] io::Error),

    /// Underlying netlink error.
    #[error("Netlink error: {0}")]
    NetlinkError(#[from] rtnetlink::Error),

    /// Failed to create netlink socket.
    #[error("Failed to create netlink socket")]
    CreateSocket(#[source] io::Error),
    /// Failed to bind netlink socket.
    #[error("Failed to bind netlink socket")]
    BindSocket(#[source] io::Error),
    /// Failed to set netlink socket non-blocking.
    #[error("Failed to set netlink socket non-blocking")]
    SetSocketNonBlocking(#[source] io::Error),
    /// Failed to receive from netlink socket.
    #[error("Failed to receive from netlink socket")]
    Recv(#[source] io::Error),
    /// Failed to parse uevent message.
    #[error("Failed to parse uevent message: {0}")]
    ParseFailure(String),

    /// Catch-all for other errors.
    #[error("Other error: {0}")]
    Other(String),
}

/// Result type including the Error type for this crate.
pub type Result<T> = std::result::Result<T, Error>;
