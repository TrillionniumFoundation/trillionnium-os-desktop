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

use crate::errors::Result;

use std::fs;
use std::fs::FileType;
use std::os::unix::fs::FileTypeExt;
use std::path::{Path, PathBuf};

use async_trait::async_trait;
use log::{debug, trace, warn};

fn get_dir_entries<P: AsRef<Path>>(dir: P) -> Vec<(PathBuf, FileType)> {
    let entries = match fs::read_dir(&dir) {
        Ok(ents) => ents,
        Err(err) => {
            debug!("Error reading {}: {}", dir.as_ref().display(), err);
            return Vec::new();
        }
    };

    let mut res = Vec::new();
    for entry in entries {
        res.push(match entry {
            Ok(ent) => match ent.file_type() {
                Ok(ft) => (ent.path(), ft),
                Err(err) => {
                    debug!("Couldn't fetch file type for {}: {}", ent.path().display(), err);
                    continue;
                }
            },
            Err(err) => {
                debug!("Error reading directory entry in {}: {}", dir.as_ref().display(), err);
                return Vec::new();
            }
        });
    }

    res
}

/// Trait for synchronous enumeration of the device node directory.
///
/// Note that by implementing this trait you will also have a default implementation
/// of the asynchronous version.
pub trait EnumeratorDelegate {
    /// Visits the directory given by path.
    ///
    /// Returns Ok(()) if we should proceed with descending into this
    /// directory, or an Err if not.
    fn on_directory<P: AsRef<Path>>(&mut self, path: P) -> Result<()>;

    /// Visits a device.
    fn on_device<P: AsRef<Path>>(&mut self, path: P);

    /// Walks `dir` and calls the `on_directory` and `on_device` callbacks for each
    /// encountered directory and device, respectively.
    ///
    /// `dir` must refer to a directory.
    fn enumerate_dir<P: AsRef<Path>>(&mut self, dir: P) {
        for (path, file_type) in get_dir_entries(&dir) {
            if file_type.is_dir() {
                match self.on_directory(&path) {
                    Ok(()) => self.enumerate_dir(path),
                    Err(err) => {
                        debug!("Not walking {}, enumerator returned error: {}", path.display(), err)
                    }
                }
            } else if file_type.is_block_device() || file_type.is_char_device() {
                self.on_device(path);
            } else {
                trace!("Skipping file {} of unsupported type", path.display());
            }
        }
    }

    /// Walks `path` and calls the `on_directory` and `on_device` callbacks for each
    /// encountered directory and device, respectively.
    ///
    /// If `path` is not a directory, this does nothing.
    fn enumerate_devices<P: AsRef<Path>>(&mut self, path: P) {
        if !path.as_ref().is_dir() {
            warn!("Can't walk {} as it is not a directory", path.as_ref().display());
            return;
        }

        self.enumerate_dir(path);
    }
}

/// Trait for asynchronous enumeration of the device node tree.
#[async_trait]
pub trait EnumeratorAsyncDelegate {
    /// Visits the directory given by path.
    ///
    /// Returns Ok(()) if we should proceed with descending into this
    /// directory, or an Err if not.
    async fn on_directory<P: AsRef<Path> + Send>(&mut self, path: P) -> Result<()>;

    /// Visits a device.
    async fn on_device<P: AsRef<Path> + Send>(&mut self, path: P);

    /// Walks `dir` and calls the `on_directory` and `on_device` callbacks for each
    /// encountered directory and device, respectively.
    ///
    /// `dir` must refer to a directory.
    async fn enumerate_dir_async<P: AsRef<Path> + Send>(&mut self, dir: P) {
        for (path, file_type) in get_dir_entries(&dir) {
            if file_type.is_dir() {
                match self.on_directory(&path).await {
                    Ok(()) => Box::pin(self.enumerate_dir_async(path)).await,
                    Err(err) => {
                        debug!("Not walking {}, enumerator returned error: {}", path.display(), err)
                    }
                };
            } else if file_type.is_block_device() || file_type.is_char_device() {
                self.on_device(path).await;
            } else {
                trace!("Skipping file {} of unsupported type", path.display());
            }
        }
    }

    /// Walks `path` and calls the `on_directory` and `on_device` callbacks for each
    /// encountered directory and device, respectively.
    ///
    /// If `path` is not a directory, this does nothing.
    async fn enumerate_devices_async<P: AsRef<Path> + Send>(&mut self, path: P) {
        if !path.as_ref().is_dir() {
            warn!("Can't walk {} as it is not a directory", path.as_ref().display());
            return;
        }

        self.enumerate_dir_async(path).await;
    }
}

#[async_trait]
impl<T: EnumeratorDelegate + Send> EnumeratorAsyncDelegate for T {
    async fn on_directory<P: AsRef<Path> + Send>(&mut self, path: P) -> Result<()> {
        <T as EnumeratorDelegate>::on_directory(self, path)
    }

    async fn on_device<P: AsRef<Path> + Send>(&mut self, path: P) {
        <T as EnumeratorDelegate>::on_device(self, path)
    }
}
