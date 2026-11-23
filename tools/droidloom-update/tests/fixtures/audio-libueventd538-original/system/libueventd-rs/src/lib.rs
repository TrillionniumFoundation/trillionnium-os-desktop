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

//! libueventd is a library for working with devices on Android systems
//! in Rust. It allows users to enumerate and watch for devices,
//! receive notifications when they appear or disappear, and provides a
//! simple interface for interacting with them.

/// Module `device` provides an object representation of a device.
pub mod device;
/// Module `device_node` provides tools for working with devices identified
/// by device nodes, such as those under `/dev`.
pub mod device_node;
/// Module `errors` enumerates the different errors that may be returned
/// by functions in this library.
pub mod errors;
/// Module `event` specifies the types of events you can get from the various
/// watchers.
pub mod event;
/// Module `kuevent_wrappers` provides wrappers around the kuevent library.
pub mod kuevent_wrappers;
/// Module `net_interface` has functions and structs for working with net
/// interfaces and listening for changes in net interfaces.
pub mod net_interface;
/// Module `sysfs_watcher` has functions and structs for working with sysfs
/// devices and listening for changes in sysfs devices.
pub mod sysfs_watcher;

mod libc_wrappers;

/// Module `mock_sysfs` is used primarily to set up a file tree that looks
/// like sysfs for unit tests.
///
/// This is only used in tests in this crate but is exported to support
/// tests in packages that use this one.
pub mod mock_sysfs;
