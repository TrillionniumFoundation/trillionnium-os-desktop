use crate::device::Device;
use crate::errors::Result;
use crate::event::{DeviceEvent, DeviceType, EventType, ExtraData};
use crate::kuevent_wrappers::uevent_stream;

use futures::{pin_mut, StreamExt};
use kobject_uevent::ActionType;
use kobject_uevent::UEvent;
use log::{error, info, warn};
use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use tokio::sync::mpsc;
use tokio_stream::wrappers::UnboundedReceiverStream;
use tokio_stream::Stream;

/// Actor which watches sysfs events through netlink socket.
pub struct SysfsWatcher {
    // Root directory for sysfs. Typically /sys, but may be different in
    // tests.
    root_sys_dir: PathBuf,

    // This keeps track of devices that have been seen, so we don't e.g.
    // double-send events on object creation.
    tracked_devices: HashMap<PathBuf, Device>,

    // Channel that events will be sent through.
    event_tx: mpsc::UnboundedSender<DeviceEvent>,
    // Subsystems to watch. If None, all subsystems are watched.
    watched_subsystems: Option<HashSet<String>>,
}

impl SysfsWatcher {
    async fn with_root_dir<P: AsRef<Path>>(
        root_sys_dir: P,
    ) -> Result<(SysfsWatcher, impl Stream<Item = DeviceEvent>)> {
        let (event_tx, event_rx) = mpsc::unbounded_channel();

        let watcher = SysfsWatcher {
            root_sys_dir: root_sys_dir.as_ref().to_path_buf(),

            tracked_devices: HashMap::new(),
            event_tx,
            watched_subsystems: None,
        };

        Ok((watcher, UnboundedReceiverStream::new(event_rx)))
    }

    /// Creates a new `SysfsWatcher`.
    ///
    /// On success, this returns the `SysfsWatcher`
    /// whose event loop can be run to watch the directory, and a stream of
    /// `DeviceEvent`s produced by the watcher.
    ///
    /// On error, propagates an `Err(_)` with more details.
    pub async fn new() -> Result<(SysfsWatcher, impl Stream<Item = DeviceEvent>)> {
        Self::with_root_dir("/sys").await
    }

    /// Adds a subsystem to the watch list. If the watch list is empty, it will be created.
    pub fn watch_for_subsystem(&mut self, subsystem: &str) {
        self.watched_subsystems.get_or_insert_with(HashSet::new).insert(subsystem.to_string());
    }

    async fn handle_uevent(&mut self, uevent: UEvent) -> Result<()> {
        info!("Handling uevent: {}", uevent.devpath.display());

        if let Some(watched) = &self.watched_subsystems {
            if !watched.contains(&uevent.subsystem) {
                return Ok(());
            }
        }

        let device_path =
            self.root_sys_dir.join(uevent.devpath.strip_prefix("/").unwrap_or(&uevent.devpath));
        let device_type = DeviceType::Raw;

        let Some(device) = Device::with_root_and_syspath(&self.root_sys_dir, device_path.clone())
        else {
            warn!("Failed to create device for path: {}", device_path.display());
            return Ok(());
        };

        let event_type = match uevent.action {
            ActionType::Add => EventType::Add,
            ActionType::Remove => EventType::Remove,
            ActionType::Change => EventType::Change,
            _ => return Ok(()),
        };

        match event_type {
            EventType::Add => {
                if self.tracked_devices.contains_key(&device_path.clone()) {
                    // this is a duplicate entry, just ignore it
                    return Ok(());
                }
                self.tracked_devices.insert(device_path.clone(), device.clone());
            }
            EventType::Remove => {
                if self.tracked_devices.remove(&device_path.clone()).is_none() {
                    return Ok(());
                }
            }
            EventType::Change => {
                // For change events, remove and then re-add the device to update its state
                // in the tracked_devices map.
                self.tracked_devices.remove(&device_path);
                self.tracked_devices.insert(device_path.clone(), device.clone());
            }
        }

        let extra_data = Some(ExtraData::Vars(uevent.env));

        let res = self.event_tx.send(DeviceEvent { event_type, device_type, device, extra_data });
        if let Err(err) = res {
            warn!("Failed to send device event: {}", err);
        }
        Ok(())
    }

    /// Run the event loop associated with this `SysfsWatcher`.
    ///
    /// You will need to do this for it to produce any events. To avoid blocking,
    /// you should spawn a separate task to run the event loop in.
    pub async fn run_event_loop(&mut self) {
        info!("SysfsWatcher: Initialized, listening for events");
        let stream = match uevent_stream() {
            Ok(s) => s,
            Err(e) => {
                error!("Failed to create uevent stream: {}", e);
                return;
            }
        };
        pin_mut!(stream);

        loop {
            tokio::select! {
                uevent_result = stream.next() => {
                    match uevent_result {
                        Some(Ok(uevent)) => {
                            if let Err(e) = self.handle_uevent(uevent).await {
                                error!("Error handling uevent: {}", e);
                            }
                        }
                        Some(Err(e)) => {
                            error!("Got error from uevent stream: {}", e);
                        }
                        None => {
                            warn!("Uevent stream ended unexpectedly");
                            return;
                        }
                    }
                }
                _ = self.event_tx.closed() => {
                    info!("Event channel closed, shutting down event loop.");
                    return;
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::mock_sysfs::{MockSysfs, SysfsFile};
    use env_logger;
    use kobject_uevent::UEvent;
    use std::collections::HashMap;
    use tokio::time::{timeout, Duration};
    use tokio_stream::StreamExt;

    fn init_logging() {
        let _ = env_logger::try_init();
    }

    fn create_mock_uevent(action: &str, devpath: &str, subsystem: &str, seq: u64) -> UEvent {
        let mut env = HashMap::new();
        env.insert("ACTION".to_string(), action.to_string());
        env.insert("DEVPATH".to_string(), devpath.to_string());
        env.insert("SUBSYSTEM".to_string(), subsystem.to_string());
        env.insert("SEQNUM".to_string(), seq.to_string());
        UEvent {
            action: action.parse().unwrap(),
            devpath: devpath.into(),
            subsystem: subsystem.to_string(),
            env,
            seq,
        }
    }

    #[tokio::test]
    async fn test_handle_uevent_add_typec() {
        init_logging();
        let sysfs = SysfsFile::Dir(HashMap::from([(
            "class/typec/port0",
            SysfsFile::Dir(HashMap::from([("uevent", SysfsFile::RegularFile(""))])),
        )]));
        let sysfs_dir = match MockSysfs::new(sysfs) {
            Ok(ms) => ms,
            Err(e) => panic!("Could not create mock sysfs: {}", e),
        };
        let (mut watcher, mut stream) =
            SysfsWatcher::with_root_dir(sysfs_dir.path()).await.unwrap();

        let device_path = PathBuf::from("class/typec/port0");
        let sysfs_path = sysfs_dir.path().join(&device_path);
        info!("sysfs_path: {}", sysfs_path.display());
        info!("device_path: {}", device_path.display());
        let uevent = create_mock_uevent("add", device_path.to_str().unwrap(), "typec", 1);

        watcher.handle_uevent(uevent.clone()).await.unwrap();

        assert!(
            watcher.tracked_devices.contains_key(&sysfs_path),
            "Device not found in tracked devices"
        );

        let event = timeout(Duration::from_millis(100), stream.next())
            .await
            .expect("timed out waiting for event")
            .unwrap();
        assert_eq!(event.event_type, EventType::Add);
        assert_eq!(event.device_type, DeviceType::Raw);
        match event.extra_data {
            Some(ExtraData::Vars(vars)) => assert_eq!(vars, uevent.env),
            _ => panic!("extra data did not contain uevent vars"),
        }
    }

    #[tokio::test]
    async fn test_handle_uevent_add_usb_power_delivery() {
        init_logging();
        let sysfs = SysfsFile::Dir(HashMap::from([(
            "class/usb_power_delivery/port0",
            SysfsFile::Dir(HashMap::from([("uevent", SysfsFile::RegularFile(""))])),
        )]));
        let sysfs_dir = match MockSysfs::new(sysfs) {
            Ok(ms) => ms,
            Err(e) => panic!("Could not create mock sysfs: {}", e),
        };
        let (mut watcher, mut stream) =
            SysfsWatcher::with_root_dir(sysfs_dir.path()).await.unwrap();
        let device_path = PathBuf::from("class/usb_power_delivery/port0");
        let sysfs_path = sysfs_dir.path().join(&device_path);
        let uevent =
            create_mock_uevent("add", device_path.to_str().unwrap(), "usb_power_delivery", 1);

        watcher.handle_uevent(uevent.clone()).await.unwrap();

        assert!(
            watcher.tracked_devices.contains_key(&sysfs_path),
            "Device not found in tracked devices"
        );

        let event = timeout(Duration::from_millis(100), stream.next())
            .await
            .expect("timed out waiting for event")
            .unwrap();
        assert_eq!(event.event_type, EventType::Add);
        assert_eq!(event.device_type, DeviceType::Raw);
        match event.extra_data {
            Some(ExtraData::Vars(vars)) => assert_eq!(vars, uevent.env),
            _ => panic!("extra data did not contain uevent vars"),
        }
    }

    #[tokio::test]
    async fn test_handle_uevent_remove() {
        init_logging();
        let sysfs = SysfsFile::Dir(HashMap::from([(
            "class/typec/port0",
            SysfsFile::Dir(HashMap::from([("uevent", SysfsFile::RegularFile(""))])),
        )]));
        let sysfs_dir = match MockSysfs::new(sysfs) {
            Ok(ms) => ms,
            Err(e) => panic!("Could not create mock sysfs: {}", e),
        };
        let (mut watcher, mut stream) =
            SysfsWatcher::with_root_dir(sysfs_dir.path()).await.unwrap();
        let device_path = PathBuf::from("class/typec/port0");

        // Add the device first
        let add_uevent = create_mock_uevent("add", device_path.to_str().unwrap(), "typec", 3);
        watcher.handle_uevent(add_uevent).await.unwrap();
        assert_eq!(watcher.tracked_devices.len(), 1);
        let _ = stream.next().await; // consume add event

        // Now remove it
        let remove_uevent = create_mock_uevent("remove", device_path.to_str().unwrap(), "typec", 4);
        watcher.handle_uevent(remove_uevent).await.unwrap();

        assert!(watcher.tracked_devices.is_empty());
        let event = stream.next().await.unwrap();
        assert_eq!(event.event_type, EventType::Remove);
    }

    #[tokio::test]
    async fn test_handle_uevent_filtered() {
        init_logging();
        let sysfs = SysfsFile::Dir(HashMap::from([
            (
                "class/typec/port0",
                SysfsFile::Dir(HashMap::from([
                    ("uevent", SysfsFile::RegularFile("")),
                    ("subsystem", SysfsFile::Symlink("../../typec")),
                ])),
            ),
            (
                "class/other/dev0",
                SysfsFile::Dir(HashMap::from([
                    ("uevent", SysfsFile::RegularFile("")),
                    ("subsystem", SysfsFile::Symlink("../../other")),
                ])),
            ),
            ("class/typec", SysfsFile::Dir(HashMap::new())),
            ("class/other", SysfsFile::Dir(HashMap::new())),
        ]));
        let sysfs_dir = MockSysfs::new(sysfs).unwrap();
        let (mut watcher, mut stream) =
            SysfsWatcher::with_root_dir(sysfs_dir.path()).await.unwrap();

        watcher.watch_for_subsystem("typec");

        // Event for typec - should be received
        let uevent_typec = create_mock_uevent("add", "class/typec/port0", "typec", 1);
        watcher.handle_uevent(uevent_typec).await.unwrap();

        // Event for other - should be ignored
        let uevent_other = create_mock_uevent("add", "class/other/dev0", "other", 2);
        watcher.handle_uevent(uevent_other).await.unwrap();

        let event = timeout(Duration::from_millis(100), stream.next())
            .await
            .expect("timed out waiting for event")
            .unwrap();
        assert_eq!(event.device.subsystem().unwrap(), "typec");

        // There should be no more events
        let result = timeout(Duration::from_millis(100), stream.next()).await;
        assert!(result.is_err(), "Expected no more events");
    }
}
