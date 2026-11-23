// Copyright (C) 2024 The Android Open Source Project
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

extern crate libc;

use std::fs::Metadata;
use std::os::unix::fs::MetadataExt;

#[cfg(target_os = "android")]
pub fn get_devnum(metadata: &Metadata) -> (u32, u32) {
    let devnum = metadata.rdev() as libc::dev_t;
    (libc::major(devnum).try_into().unwrap(), libc::minor(devnum).try_into().unwrap())
}

#[cfg(target_os = "linux")]
pub fn get_devnum(metadata: &Metadata) -> (u32, u32) {
    let devnum = metadata.rdev() as libc::dev_t;
    (libc::major(devnum), libc::minor(devnum))
}
