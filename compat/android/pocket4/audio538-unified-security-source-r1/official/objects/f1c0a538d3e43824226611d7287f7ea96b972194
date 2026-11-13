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

//! Example program which watches for all kernel uevents.

use futures::{pin_mut, StreamExt};
use log::{error, info};
use std::boxed::Box;
use std::error::Error;
use ueventd::kuevent_wrappers::uevent_stream;

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn Error>> {
    env_logger::init();
    let stream = match uevent_stream() {
        Ok(s) => s,
        Err(e) => {
            error!("Failed to create uevent stream: {}", e);
            return Err(e.into());
        }
    };
    pin_mut!(stream);
    info!("Listening for kernel uevents...");

    while let Some(event_result) = stream.next().await {
        let event = match event_result {
            Ok(event) => event,
            Err(e) => {
                error!("Error receiving uevent: {}", e);
                continue;
            }
        };

        let seqnum = event.env.get("SEQNUM").map_or("", |s| s.as_str());
        println!(
            "{:?} {} {} (seq: {})",
            event.action,
            event.subsystem,
            event.devpath.display(),
            seqnum
        );
        for (key, value) in event.env {
            println!("    {}={}", key, value);
        }
    }
    Ok(())
}
