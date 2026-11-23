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

use crate::device::Device;

use std::collections::HashMap;
use std::net::IpAddr;
use std::path::PathBuf;

/// Enum representing the type of event.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum EventType {
    /// A device is being added.
    Add,
    /// A device is being removed.
    Remove,
    /// A device is being changed.
    Change,
}

/// Enum representing the type of device an event concerns. It will also
/// contain any extra data for that specific type.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DeviceType {
    /// A device node (i.e. a character or block device in /dev).
    DeviceNode {
        /// Path to the device node itself.
        devnode_path: PathBuf,
    },
    /// A net interface.
    NetInterface {
        /// Index of the net interface.
        index: u32,
    },
    /// A raw device. It is identified entirely by the Device struct in the
    /// event.
    Raw,
}

/// This data may be included in device events, particularly change events.
#[derive(Clone, Debug)]
pub enum ExtraData {
    /// UEvent vars.
    Vars(HashMap<String, String>),
    /// Net interface added a new address.
    AddressAdded(IpAddr),
    /// Net interface removed an address.
    AddressRemoved(IpAddr),
}

/// Struct representing a device event. These are emitted by the watchers when
/// devices are added or removed, and contain information about the relevant
/// device as well as extra metadata that might be necessary for the device
/// type.
#[derive(Clone, Debug)]
pub struct DeviceEvent {
    /// Type of event (add, remove, etc.)
    pub event_type: EventType,
    /// Type of device (device node, net interface, etc.) along with extra information,
    /// if applicable.
    pub device_type: DeviceType,
    /// Device object representing the device this event concerns in sysfs.
    pub device: Device,
    /// Extra data that may be present in this event.
    pub extra_data: Option<ExtraData>,
}
