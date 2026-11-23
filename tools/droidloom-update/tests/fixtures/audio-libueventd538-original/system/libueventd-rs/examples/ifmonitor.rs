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

//! Example program which watches for net interfaces coming up and down.

use std::boxed::Box;
use std::error::Error;

use log::{info, warn};
use tokio_stream::StreamExt;
use ueventd::event::{DeviceType, EventType, ExtraData};
use ueventd::net_interface::NetInterfaceWatcher;

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn Error>> {
    let (mut watcher, mut events) = NetInterfaceWatcher::new().await?;

    tokio::spawn(async move {
        watcher.run_event_loop().await;
    });

    loop {
        let Some(event) = events.next().await else {
            info!("exiting...");
            return Ok(());
        };

        let DeviceType::NetInterface { index } = event.device_type else {
            warn!("got non-net interface event {event:?}");
            continue;
        };

        let Some(name) = event.device.name() else {
            warn!(
                "Net interface at {} (index {}) had no name",
                event.device.syspath().display(),
                index
            );
            continue;
        };

        let event_type = match event.event_type {
            EventType::Add => "+",
            EventType::Remove => "-",
            EventType::Change => "c",
        };

        let extra_data = match event.extra_data {
            Some(ExtraData::AddressAdded(addr)) => format!(" added address {}", addr),
            Some(ExtraData::AddressRemoved(addr)) => format!(" removed address {}", addr),
            Some(_) => " <unexpected extra data>".to_owned(),
            None => String::new(),
        };

        println!("{event_type} {index:>4} {name}{extra_data}");
    }
}
