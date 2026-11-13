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

extern crate futures_channel;

use crate::device::Device;
use crate::errors::{Error, Result};
use crate::event::{DeviceEvent, DeviceType, EventType, ExtraData};

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use futures::stream::TryStreamExt;
use log::{error, warn};
use rtnetlink::packet_core::{NetlinkMessage, NetlinkPayload};
use rtnetlink::packet_route::address::{AddressAttribute, AddressMessage};
use rtnetlink::packet_route::link::{LinkAttribute, LinkMessage};
use rtnetlink::packet_route::RouteNetlinkMessage;
use rtnetlink::proto::Connection;
use rtnetlink::sys::SocketAddr;
use rtnetlink::{Handle as NetlinkHandle, MulticastGroup};
use tokio::sync::mpsc;
use tokio_stream::wrappers::UnboundedReceiverStream;
use tokio_stream::{Stream, StreamExt};

/// Actor which watches the list of net interfaces.
#[allow(dead_code)]
pub struct NetInterfaceWatcher {
    // Root directory for sysfs. Typically /sys, but may be different in
    // tests.
    root_sys_dir: PathBuf,

    // Objects encapsulating the netlink connection.
    connection: Connection<RouteNetlinkMessage>,
    handle: NetlinkHandle,
    netlink_events:
        futures_channel::mpsc::UnboundedReceiver<(NetlinkMessage<RouteNetlinkMessage>, SocketAddr)>,

    // This keeps track of interfaces that have been seen, so we don't e.g.
    // double-send events on object creation.
    tracked_interfaces: HashMap<u32, Device>,

    // Channel that events will be sent through.
    event_tx: mpsc::UnboundedSender<DeviceEvent>,
}

fn get_device<P: AsRef<Path>>(sysfs_root: P, link_message: &LinkMessage) -> Option<Device> {
    let name = link_message.attributes.iter().find_map(|attr| match attr {
        LinkAttribute::IfName(name) => Some(name),
        _ => None,
    })?;

    let sysfs_path = sysfs_root.as_ref().join(format!("class/net/{name}"));
    Device::with_root_and_syspath(sysfs_root, sysfs_path)
}

async fn get_interface_list_with_sysfs_root<P: AsRef<Path>>(
    sysfs_root: P,
    handle: &NetlinkHandle,
) -> Result<Vec<(u32, Device)>> {
    let mut responses = handle.link().get().execute();

    let mut devices = Vec::new();
    loop {
        match TryStreamExt::try_next(&mut responses).await {
            Ok(Some(msg)) => match get_device(&sysfs_root, &msg) {
                Some(device) => devices.push((msg.header.index, device)),
                None => return Err(Error::Other(String::from("could not resolve device"))),
            },
            Ok(None) => break,
            Err(e) => return Err(e.into()),
        }
    }
    Ok(devices)
}

impl NetInterfaceWatcher {
    async fn with_root_dir<P: AsRef<Path>>(
        root_sys_dir: P,
    ) -> Result<(NetInterfaceWatcher, impl Stream<Item = DeviceEvent>)> {
        let (event_tx, event_rx) = mpsc::unbounded_channel();

        let (connection, handle, netlink_events) = rtnetlink::new_multicast_connection(&[
            MulticastGroup::Link,
            MulticastGroup::Ipv4Ifaddr,
            MulticastGroup::Ipv6Ifaddr,
        ])?;

        let watcher = NetInterfaceWatcher {
            root_sys_dir: root_sys_dir.as_ref().to_path_buf(),
            connection,
            handle,
            netlink_events,
            tracked_interfaces: HashMap::new(),
            event_tx,
        };

        Ok((watcher, UnboundedReceiverStream::new(event_rx)))
    }

    /// Creates a new `NetInterfaceWatcher`.
    ///
    /// On success, this returns the `NetInterfaceWatcher`
    /// whose event loop can be run to watch the directory, and a stream of
    /// `DeviceEvent`s produced by the watcher.
    ///
    /// On error, propagates an `Err(_)` with more details.
    pub async fn new() -> Result<(NetInterfaceWatcher, impl Stream<Item = DeviceEvent>)> {
        Self::with_root_dir("/sys").await
    }

    async fn handle_new_link(&mut self, msg: LinkMessage) -> Result<()> {
        let index = msg.header.index;
        let device = get_device(&self.root_sys_dir, &msg)
            .ok_or(Error::Other(format!("Could not resolve device with index {index}")))?;

        if let Some(existing_device) = self.tracked_interfaces.get(&index) {
            if device == *existing_device {
                // this is a duplicate entry, just ignore it
                return Ok(());
            }
        }

        self.tracked_interfaces.insert(index, device.clone());
        let res = self.event_tx.send(DeviceEvent {
            event_type: EventType::Add,
            device_type: DeviceType::NetInterface { index },
            device,
            extra_data: None,
        });
        if let Err(err) = res {
            warn!("Failed to send device event: {err}");
        }
        Ok(())
    }

    async fn handle_del_link(&mut self, msg: LinkMessage) -> Result<()> {
        let index = msg.header.index;
        let Some(device) = self.tracked_interfaces.remove(&index) else {
            return Err(Error::Other(format!(
                "Could not find tracked interface associated with index {index}"
            )));
        };

        let res = self.event_tx.send(DeviceEvent {
            event_type: EventType::Remove,
            device_type: DeviceType::NetInterface { index },
            device,
            extra_data: None,
        });
        if let Err(err) = res {
            warn!("Failed to send device event: {err}");
        }
        Ok(())
    }

    async fn handle_address_change(&mut self, msg: AddressMessage, added: bool) -> Result<()> {
        let index = msg.header.index;
        let Some(device) = self.tracked_interfaces.get(&index) else {
            return Err(Error::Other(format!(
                "Could not find tracked interface associated with index {index}"
            )));
        };

        let Some(addr) = msg.attributes.iter().find_map(|attr| match attr {
            AddressAttribute::Address(addr) => Some(*addr),
            _ => None,
        }) else {
            return Err(Error::Other(format!(
                "Address change message for interface at index {index} had no local address"
            )));
        };

        let extra_data = Some(if added {
            ExtraData::AddressAdded(addr)
        } else {
            ExtraData::AddressRemoved(addr)
        });

        let res = self.event_tx.send(DeviceEvent {
            event_type: EventType::Change,
            device_type: DeviceType::NetInterface { index },
            device: device.clone(),
            extra_data,
        });
        if let Err(err) = res {
            warn!("Failed to send device event: {err}");
        }
        Ok(())
    }

    async fn handle_message(&mut self, msg: RouteNetlinkMessage) -> Result<()> {
        match msg {
            RouteNetlinkMessage::NewLink(new_link_msg) => self.handle_new_link(new_link_msg).await,
            RouteNetlinkMessage::DelLink(del_link_msg) => self.handle_del_link(del_link_msg).await,
            RouteNetlinkMessage::NewAddress(new_addr_msg) => {
                self.handle_address_change(new_addr_msg, true).await
            }
            RouteNetlinkMessage::DelAddress(del_addr_msg) => {
                self.handle_address_change(del_addr_msg, false).await
            }
            // silently drop all other kinds of messages
            _ => Ok(()),
        }
    }

    /// Run the event loop associated with this `NetInterfaceWatcher`.
    ///
    /// You will need to do this for it to produce any events. To avoid blocking,
    /// you should spawn a separate task to run the event loop in.
    pub async fn run_event_loop(&mut self) {
        // phase 1: send the initial enumeration message and listen for responses
        // to that
        let mut initial_events = self.handle.link().get().execute();
        while !self.event_tx.is_closed() {
            tokio::select! {
                _ = &mut self.connection => return,
                event = TryStreamExt::try_next(&mut initial_events) => {
                    match event {
                        Ok(Some(msg)) => {
                            // This message represents a device. We can treat it like it was
                            // added in a notification.
                            let _ = self.handle_new_link(msg).await;
                        }
                        // responses are done, move to phase 2
                        Ok(None) => break,
                        // initialization error, exit early
                        Err(err) => {
                            error!("Failed to initialize net interface event stream: {err}");
                            return;
                        }
                    }
                }
            }
        }

        // phase 2: handle messages coming on the notification channel
        while !self.event_tx.is_closed() {
            tokio::select! {
                _ = &mut self.connection => return,
                event = self.netlink_events.next() => {
                    match event {
                        Some((msg, _)) => {
                            // we only care about RouteNetlinkMessage payloads, everything
                            // else is protocol stuff that shouldn't end up on the notification
                            // receiver and we can skip it
                            let NetlinkPayload::InnerMessage(rtnl_msg) = msg.payload else {
                                continue;
                            };
                            let _ = self.handle_message(rtnl_msg).await;
                        }
                        None => return,
                    }
                }
            }
        }
    }
}

/// Gets a list of devices representing net interfaces along with their associated interface
/// indices.
pub async fn get_interface_list() -> Result<Vec<(u32, Device)>> {
    let (connection, handle, _) = rtnetlink::new_connection()?;
    let join_handle = tokio::spawn(connection);

    let list = get_interface_list_with_sysfs_root("/sys", &handle).await;
    std::mem::drop(handle);
    join_handle
        .await
        .map_err(|err| Error::Other(format!("Failed to close netlink connection: {err}")))?;
    list
}
