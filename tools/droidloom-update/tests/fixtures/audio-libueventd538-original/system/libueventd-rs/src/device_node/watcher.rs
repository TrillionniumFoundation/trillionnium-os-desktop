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

use crate::device::Device;
use crate::device_node::enumerator::EnumeratorAsyncDelegate;
use crate::errors::{Error, Result};
use crate::event::{DeviceEvent, DeviceType, EventType};

use std::boxed::Box;
use std::collections::HashMap;
use std::path::{Path, PathBuf};

use async_trait::async_trait;
use inotify::{EventMask, EventStream, Inotify, WatchMask};
use log::{debug, error, info, warn};
use tokio::sync::mpsc;
use tokio_stream::wrappers::UnboundedReceiverStream;
use tokio_stream::{Stream, StreamExt, StreamMap};

fn event_mask_to_str(mask: EventMask) -> String {
    mask.iter_names().map(|v| v.0).collect::<Vec<_>>().join(", ")
}

/// Actor which watches the device node tree.
pub struct Watcher {
    // Root directory where we expect device nodes to be created. Typically
    // /dev, but may be different in tests.
    root_dev_dir: PathBuf,
    // Root directory for sysfs. Typically /sys, but may be different in
    // tests.
    root_sys_dir: PathBuf,

    // Stores the current inotify event streams for each directory under
    // the root.
    inotify_events: StreamMap<PathBuf, EventStream<Box<[u8]>>>,

    // This keeps track of devices that have been seen, so we don't e.g.
    // double-send events on object creation.
    tracked_devices: HashMap<PathBuf, Device>,

    // Channel that events will be sent through.
    event_tx: mpsc::UnboundedSender<DeviceEvent>,
}

impl Watcher {
    async fn with_root_dirs<P: AsRef<Path>, Q: AsRef<Path>>(
        root_dev_dir: P,
        root_sys_dir: Q,
    ) -> Result<(Watcher, impl Stream<Item = DeviceEvent>)> {
        let (event_tx, event_rx) = mpsc::unbounded_channel();

        let mut watcher = Watcher {
            root_dev_dir: root_dev_dir.as_ref().to_path_buf(),
            root_sys_dir: root_sys_dir.as_ref().to_path_buf(),
            inotify_events: StreamMap::new(),
            tracked_devices: HashMap::new(),
            event_tx,
        };

        watcher.setup_watch(root_dev_dir)?;

        // Check for existing devices and dirs.
        watcher.enumerate_root_dir().await;

        Ok((watcher, UnboundedReceiverStream::new(event_rx)))
    }

    /// Creates a new `Watcher` which watches `/dev`.
    ///
    /// On success, this returns the `Watcher`
    /// whose event loop can be run to watch the directory, and a stream of
    /// `DeviceEvent`s produced by the watcher.
    ///
    /// On error, propagates an `Err(_)` with more details.
    pub async fn new() -> Result<(Watcher, impl Stream<Item = DeviceEvent>)> {
        Self::with_root_dirs("/dev", "/sys").await
    }

    fn setup_watch<P: AsRef<Path>>(&mut self, path: P) -> Result<()> {
        if self.inotify_events.contains_key(path.as_ref()) {
            debug!("Already watching {}", path.as_ref().display());
            return Ok(());
        }

        debug!("Setting watch on {}", path.as_ref().display());
        let inotify = Inotify::init()?;

        inotify.watches().add(&path, WatchMask::CREATE | WatchMask::DELETE)?;

        self.inotify_events.insert(
            path.as_ref().to_path_buf(),
            inotify.into_event_stream(vec![0; 1024].into_boxed_slice())?,
        );
        Ok(())
    }

    fn teardown_watch<P: AsRef<Path>>(&mut self, path: P) {
        info!("Tearing down watch on {}", path.as_ref().display());
        self.inotify_events.remove(path.as_ref());
    }

    async fn handle_dir_event<P: AsRef<Path> + Send>(
        &mut self,
        mask: EventMask,
        path: P,
    ) -> Result<()> {
        if mask.contains(EventMask::CREATE) {
            let _ = self.setup_watch(&path);
            // It's possible that we missed some events from before we set up the watch,
            // so explicitly enumerate the directory now.
            Box::pin(self.enumerate_dir_async(path)).await;
        } else if mask.contains(EventMask::DELETE) {
            self.teardown_watch(path);
        } else {
            debug!("Got unexpected event type [{}], ignoring", event_mask_to_str(mask));
        }
        Ok(())
    }

    async fn handle_device_event<P: AsRef<Path>>(&mut self, mask: EventMask, path: P) {
        if mask.contains(EventMask::DELETE) {
            if let Some(device) = self.tracked_devices.remove(path.as_ref()) {
                let res = self.event_tx.send(DeviceEvent {
                    event_type: EventType::Remove,
                    device_type: DeviceType::DeviceNode {
                        devnode_path: path.as_ref().to_path_buf(),
                    },
                    device,
                    extra_data: None,
                });
                if let Err(err) = res {
                    warn!("Failed to send device event: {err}");
                }
            }
            return;
        }

        if !mask.contains(EventMask::CREATE) {
            warn!("Got unexpected event type [{}], ignoring", event_mask_to_str(mask));
            return;
        }

        if self.tracked_devices.contains_key(path.as_ref()) {
            debug!("Duplicate event for device {}, ignoring", path.as_ref().display());
            return;
        }

        let Some(device) = Device::with_root_and_devpath(&self.root_sys_dir, &path) else {
            debug!("Could not fetch device info for {}", path.as_ref().display());
            return;
        };

        self.tracked_devices.insert(path.as_ref().to_path_buf(), device.clone());

        let res = self.event_tx.send(DeviceEvent {
            event_type: EventType::Add,
            device_type: DeviceType::DeviceNode { devnode_path: path.as_ref().to_path_buf() },
            device,
            extra_data: None,
        });
        if let Err(err) = res {
            warn!("Failed to send device event: {err}");
        }
    }

    async fn handle_single_event(&mut self) -> Result<()> {
        let (dir, event) = match self.inotify_events.next().await {
            Some(e) => (e.0, e.1?),
            None => {
                return Err(Error::Other(String::from("inotify streams closed")));
            }
        };

        let Some(name) = event.name else {
            warn!("No name on uevent");
            return Ok(());
        };
        let Some(name_str) = name.to_str() else {
            return Err(Error::Other(String::from("Failed to copy name from uevent")));
        };
        let full_path = dir.join(name_str);

        if event.mask.contains(EventMask::ISDIR) {
            self.handle_dir_event(event.mask, full_path).await
        } else {
            self.handle_device_event(event.mask, full_path).await;
            Ok(())
        }
    }

    async fn enumerate_root_dir(&mut self) {
        debug!("Searching {} for existing devices", self.root_dev_dir.display());
        self.enumerate_devices_async(self.root_dev_dir.clone()).await;
    }

    /// Run the event loop associated with this `Watcher`.
    ///
    /// You will need to do this for it to produce any events. To avoid blocking,
    /// you should spawn a separate task to run the event loop in.
    pub async fn run_event_loop(&mut self) {
        info!("Watching for devices");
        while !self.event_tx.is_closed() {
            if let Err(err) = self.handle_single_event().await {
                error!("Got error handling event: {err}");
                continue;
            }
        }
        info!("Device watch stopping");
    }
}

#[async_trait]
impl EnumeratorAsyncDelegate for Watcher {
    async fn on_directory<P: AsRef<Path> + Send>(&mut self, path: P) -> Result<()> {
        let _ = self.setup_watch(path);
        Ok(())
    }

    async fn on_device<P: AsRef<Path> + Send>(&mut self, path: P) {
        self.handle_device_event(EventMask::CREATE, path).await;
    }
}
