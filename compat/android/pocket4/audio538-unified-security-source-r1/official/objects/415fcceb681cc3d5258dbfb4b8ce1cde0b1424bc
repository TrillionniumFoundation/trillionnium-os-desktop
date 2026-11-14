// Copyright (C) 2026 The Android Open Source Project
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

//! Example program which enumerates all device nodes and prints details
//! about their underlying devices.

use std::error::Error;
use std::path::{Path, PathBuf};

use log::error;

use ueventd::device::Device;
use ueventd::device_node::enumerator::EnumeratorDelegate;
use ueventd::errors;

struct Enumerator {
    // Vector containing pairs of device node path -> underlying device
    devices: Vec<(PathBuf, Device)>,
}

impl Enumerator {
    fn enumerate_devices<P: AsRef<Path>>(path: P) -> Vec<(PathBuf, Device)> {
        let mut enumerator = Self { devices: Vec::new() };
        enumerator.enumerate_devices(&path);
        enumerator.devices
    }
}

impl EnumeratorDelegate for Enumerator {
    fn on_directory<P: AsRef<Path>>(&mut self, _path: P) -> errors::Result<()> {
        Ok(())
    }

    fn on_device<P: AsRef<Path>>(&mut self, path: P) {
        let Some(device) = Device::with_devpath(&path) else {
            error!("Could not resolve device with device node {}", path.as_ref().display());
            return;
        };
        self.devices.push((path.as_ref().to_path_buf(), device));
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    for (device_node, device) in Enumerator::enumerate_devices("/dev") {
        println!("{} -> {}", device_node.display(), device.syspath().display());
    }
    Ok(())
}
