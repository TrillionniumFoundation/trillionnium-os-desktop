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

//! Example program which watches for sysfs changes for typec and usb_power_delivery.

use std::boxed::Box;
use std::error::Error;

use futures::StreamExt;
use ueventd::sysfs_watcher::SysfsWatcher;

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn Error>> {
    env_logger::init();

    let (mut watcher, mut stream) = SysfsWatcher::new().await?;

    watcher.watch_for_subsystem("typec");
    watcher.watch_for_subsystem("usb_power_delivery");

    // The event loop must be run in a separate task for the watcher to produce events.
    tokio::spawn(async move {
        watcher.run_event_loop().await;
    });

    println!("Watching for typec and usb_power_delivery device events...");

    while let Some(event) = stream.next().await {
        println!(
            "Received event: {:?} for device type: {:?}, device: {:?}",
            event.event_type, event.device_type, event.device
        );
    }

    Ok(())
}
