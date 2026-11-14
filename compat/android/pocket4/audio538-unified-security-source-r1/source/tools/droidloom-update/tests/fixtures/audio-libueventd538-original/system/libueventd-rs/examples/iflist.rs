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

//! Example program which queries netlink for net interfaces and prints
//! their names, indices, and details about the underlying device if
//! it exists.

use std::boxed::Box;
use std::error::Error;

use log::warn;
use ueventd::net_interface::get_interface_list;

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn Error>> {
    let devices = get_interface_list().await?;

    for (index, netif_dev) in devices {
        let Some(name) = netif_dev.name() else {
            warn!("Net interface at {} had no name", netif_dev.syspath().display());
            continue;
        };

        let underlying_details = match netif_dev.device() {
            Some(underlying_dev) => {
                format!(
                    "underlying device {} (subsystem {}, driver {})",
                    underlying_dev.syspath().display(),
                    underlying_dev.subsystem().unwrap_or(String::from("<none>")),
                    underlying_dev.driver().unwrap_or(String::from("<none>"))
                )
            }
            None => String::from("no underlying device"),
        };
        println!("{index:>4} {name}: {underlying_details}");
    }

    Ok(())
}
