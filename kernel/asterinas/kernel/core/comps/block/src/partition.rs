// SPDX-License-Identifier: MPL-2.0

use alloc::format;

use device_id::{DeviceId, MinorId};
use ostd::{mm::VmIo, sync::Mutex};

use crate::{
    BlockDevice, BlockDeviceMeta, DEVICE_MINORS, SECTOR_SIZE,
    bio::{BioEnqueueError, SubmittedBio},
    device_id::EXTENDED_DEVICE_ID_ALLOCATOR,
    prelude::*,
    register, unregister,
};

mod table;
pub(super) use table::PartitionInfo;

pub(super) fn parse(device: &Arc<dyn BlockDevice>) -> Option<Vec<Option<PartitionInfo>>> {
    let nr_sectors = device.metadata().nr_sectors;
    // VmIo offsets and the block-device byte size are usize. Validate before
    // calling the original I/O adapter, including its capacity multiplication.
    if nr_sectors.checked_mul(SECTOR_SIZE).is_none() {
        ostd::warn!(
            "partition scan of {}: device byte size overflows",
            device.name()
        );
        return None;
    }
    let result = table::parse(nr_sectors as u64, |sector, bytes| {
        let offset = usize::try_from(sector)
            .ok()
            .and_then(|sector| sector.checked_mul(SECTOR_SIZE))
            .ok_or(ostd::Error::Overflow)?;
        device.read_bytes(offset, bytes)
    });
    let parsed = match result {
        Ok(Some(parsed)) => parsed,
        Ok(None) => return None,
        Err(error) => {
            ostd::warn!("partition scan of {} failed: {:?}", device.name(), error);
            return None;
        }
    };
    match parsed.source {
        table::TableSource::GptPrimaryOnly => ostd::warn!(
            "partition scan of {}: using primary GPT; backup is unavailable or invalid; no repair written",
            device.name()
        ),
        table::TableSource::GptBackupOnly => ostd::warn!(
            "partition scan of {}: using backup GPT; primary is unavailable or invalid; no repair written",
            device.name()
        ),
        table::TableSource::Mbr | table::TableSource::GptBoth => {}
    }
    parsed
        .partitions
        .iter()
        .any(Option::is_some)
        .then_some(parsed.partitions)
}

#[derive(Debug)]
struct PartitionNode {
    id: DeviceId,
    name: String,
    device: Arc<dyn BlockDevice>,
    info: PartitionInfo,
}

impl BlockDevice for PartitionNode {
    fn enqueue(&self, mut bio: SubmittedBio) -> Result<(), BioEnqueueError> {
        bio.set_sid_offset(self.info.start_sector());
        self.device.enqueue(bio)
    }

    fn metadata(&self) -> BlockDeviceMeta {
        let mut metadata = self.device.metadata();
        metadata.nr_sectors = self.info.total_sectors() as usize;
        metadata
    }

    fn name(&self) -> &str {
        &self.name
    }

    fn id(&self) -> DeviceId {
        self.id
    }

    fn is_partition(&self) -> bool {
        true
    }
}

impl PartitionNode {
    fn new(id: DeviceId, name: String, device: Arc<dyn BlockDevice>, info: PartitionInfo) -> Self {
        Self {
            id,
            name,
            device,
            info,
        }
    }
}

/// Manages the partitions of a whole-disk block device.
///
/// The manager owns the device's current partition list and the lock that
/// serializes partition replacement.
#[derive(Debug)]
pub struct PartitionManager {
    inner: Mutex<Option<Vec<Arc<PartitionNode>>>>,
}

impl Default for PartitionManager {
    fn default() -> Self {
        Self::new()
    }
}

impl PartitionManager {
    /// Creates an empty partition manager.
    pub const fn new() -> Self {
        Self {
            inner: Mutex::new(None),
        }
    }

    /// Replaces the managed partitions with the parsed partition information.
    pub(super) fn update(&self, device: &Arc<dyn BlockDevice>, infos: Vec<Option<PartitionInfo>>) {
        // Lock order: partition lock -> `DEVICE_REGISTRY`

        let mut partitions = self.inner.lock();

        if let Some(old_partitions) = partitions.take() {
            for partition in old_partitions {
                let _ = unregister(partition.id());
            }
        }

        let mut new_partitions = Vec::new();
        for (index, info_opt) in infos.iter().enumerate() {
            let Some(info) = info_opt else {
                continue;
            };

            let index = index as u32 + 1;
            let id = if index < DEVICE_MINORS {
                let device_id = device.id();
                DeviceId::new(
                    device_id.major(),
                    MinorId::new(device_id.minor().get() + index),
                )
            } else {
                EXTENDED_DEVICE_ID_ALLOCATOR.get().unwrap().allocate()
            };
            let name = partition_name(device.name(), index);
            let partition = Arc::new(PartitionNode::new(id, name, device.clone(), *info));
            new_partitions.push(partition);
        }

        for partition in new_partitions.iter() {
            let _ = register(partition.clone());
        }

        *partitions = Some(new_partitions);
    }
}

/// Formats the name of a partition.
///
/// We perform the naming similar to the Linux implementation: insert "p" between
/// the disk name and the partition number when the disk name ends with a digit
/// (`nvme0n1p1`), and append the number otherwise (`vda1`).
///
/// Reference: <https://elixir.bootlin.com/linux/v7.2.2/source/block/partitions/core.c#L337>
fn partition_name(disk_name: &str, partno: u32) -> String {
    if disk_name.ends_with(|c: char| c.is_ascii_digit()) {
        format!("{}p{}", disk_name, partno)
    } else {
        format!("{}{}", disk_name, partno)
    }
}
