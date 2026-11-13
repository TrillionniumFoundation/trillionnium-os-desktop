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

use crate::libc_wrappers::get_devnum;

use std::collections::HashMap;
use std::fs;
use std::io;
use std::os::unix::fs::FileTypeExt;
use std::path::{Path, PathBuf};

/// Represents a directory within sysfs that can be queried (by reading
/// files) for attributes of a device.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FilesystemAttributeMap {
    dir_path: PathBuf,
}

impl FilesystemAttributeMap {
    fn new<P: AsRef<Path>>(dir_path: P) -> Option<FilesystemAttributeMap> {
        if !dir_path.as_ref().is_dir() {
            return None;
        }

        Some(FilesystemAttributeMap { dir_path: dir_path.as_ref().to_path_buf() })
    }

    /// Checks whether or not the given sysattr exists.
    pub fn has(&self, key: &str) -> bool {
        self.dir_path.join(key).try_exists().unwrap_or(false)
    }

    /// Reads the sysfs attribute with the given `key`.
    pub fn get(&self, key: &str) -> io::Result<String> {
        fs::read_to_string(self.dir_path.join(key))
    }

    /// Writes the `value` to the sysfs attribute with the given `key`.
    pub fn set(&self, key: &str, value: &str) -> io::Result<()> {
        fs::write(self.dir_path.join(key), value)
    }

    fn attrs(&self) -> HashMap<String, String> {
        let Ok(entries) = fs::read_dir(&self.dir_path) else {
            return HashMap::new();
        };

        let mut attrs = HashMap::new();
        for entry in entries {
            let file_name = match entry {
                Ok(e) => e.file_name(),
                Err(_) => continue,
            };
            let Some(key) = file_name.to_str() else {
                continue;
            };
            let Ok(value) = self.get(key) else {
                continue;
            };
            attrs.insert(key.to_owned(), value);
        }
        attrs
    }
}

impl IntoIterator for FilesystemAttributeMap {
    type Item = (String, String);
    type IntoIter = std::collections::hash_map::IntoIter<String, String>;

    fn into_iter(self) -> Self::IntoIter {
        self.attrs().into_iter()
    }
}

/// Specifies a device number.
#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd)]
pub enum DeviceNumber {
    /// Device number for a block device.
    Block {
        /// Device major number.
        major: u32,
        /// Device minor number.
        minor: u32,
    },
    /// Device number for a character device.
    Char {
        /// Device major number.
        major: u32,
        /// Device minor number.
        minor: u32,
    },
}

/// Represents an actual device. This struct has methods allowing you
/// to create device objects through a variety of different identification
/// mechanisms, perform operations on the device tree, and work with device
/// attributes.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Device {
    /// Root directory of sysfs filesystem. Typically this is simply `/sys`
    /// but it may be something else in unit tests.
    sysfs_root: PathBuf,

    /// Path to sysfs directory representing this device.
    sysfs_path: PathBuf,

    /// Interface to allow getting and setting sysfs attributes.
    sysattrs: FilesystemAttributeMap,
}

impl Device {
    /// Creates a device object from the given syspath inside `sysfs_root`.
    pub fn with_root_and_syspath<P, Q>(sysfs_root: P, sysfs_path: Q) -> Option<Device>
    where
        P: AsRef<Path>,
        Q: AsRef<Path>,
    {
        if !sysfs_path.as_ref().starts_with(&sysfs_root) {
            return None;
        }

        let sysattrs = FilesystemAttributeMap::new(&sysfs_path)?;
        if !sysattrs.has("uevent") {
            // path does not describe a device, or we can't guarantee that it does
            return None;
        };

        Some(Device {
            sysfs_root: sysfs_root.as_ref().to_path_buf(),
            sysfs_path: sysfs_path.as_ref().to_path_buf(),
            sysattrs,
        })
    }

    /// Creates a device object from the given syspath inside `/sys`.
    pub fn with_syspath<P: AsRef<Path>>(sysfs_path: P) -> Option<Device> {
        Self::with_root_and_syspath("/sys", sysfs_path)
    }

    /// Creates a device object from the given device number and sysfs root.
    pub fn with_root_and_devnum<P: AsRef<Path>>(
        sysfs_root: P,
        devnum: DeviceNumber,
    ) -> Option<Device> {
        let syspath_link = match devnum {
            DeviceNumber::Block { major, minor } => format!("dev/block/{major}:{minor}"),
            DeviceNumber::Char { major, minor } => format!("dev/char/{major}:{minor}"),
        };
        Device::with_root_and_syspath(
            &sysfs_root,
            fs::canonicalize(sysfs_root.as_ref().join(syspath_link)).ok()?,
        )
    }

    /// Creates a device object from the given device number.
    pub fn with_devnum(devnum: DeviceNumber) -> Option<Device> {
        Device::with_root_and_devnum("/sys", devnum)
    }

    /// Creates a device object from the given device node path and sysfs root.
    pub fn with_root_and_devpath<P, Q>(sysfs_root: P, devfs_path: Q) -> Option<Device>
    where
        P: AsRef<Path>,
        Q: AsRef<Path>,
    {
        let metadata = if devfs_path.as_ref().to_str()?.starts_with("/dev/pts/") {
            // PTY ports /dev/pts/N don't have device info links /sys/dev/char/136:N,
            // so for them we use device info for PTY port /dev/ptmx.
            fs::metadata(Path::new("/dev/ptmx")).ok()?
        } else {
            fs::metadata(&devfs_path).ok()?
        };

        let chardev = if metadata.file_type().is_char_device() {
            true
        } else if metadata.file_type().is_block_device() {
            false
        } else {
            return None;
        };

        let (major, minor) = get_devnum(&metadata);
        let devnum = if chardev {
            DeviceNumber::Char { major, minor }
        } else {
            DeviceNumber::Block { major, minor }
        };
        Device::with_root_and_devnum(&sysfs_root, devnum)
    }

    /// Creates a device object from the given device node path.
    pub fn with_devpath<P: AsRef<Path>>(devfs_path: P) -> Option<Device> {
        Device::with_root_and_devpath("/sys", devfs_path)
    }

    /// Returns the parent `Device` of this device, if there is one.
    ///
    /// Returns `None` if there is no parent.
    pub fn parent(&self) -> Option<Device> {
        let mut parent_device = self.sysfs_path.clone();
        while parent_device != self.sysfs_root {
            if !parent_device.pop() {
                panic!(
                    "sysfs path {} was not under {}",
                    parent_device.display(),
                    self.sysfs_root.display()
                );
            }

            if let Some(dev) = Device::with_root_and_syspath(&self.sysfs_root, &parent_device) {
                return Some(dev);
            }
        }
        None
    }

    /// Returns the nearest parent `Device` of this device that has the given
    /// `subsystem`, if there is one.
    ///
    /// Returns `None` if no parent has the given `subsystem`, or if there is no
    /// parent `Device` at all.
    pub fn parent_with_subsystem(&self, subsystem: &str) -> Option<Device> {
        self.parent()?.walk_parents(|device| match device.get_link_target_filename("subsystem") {
            Some(target) if target == subsystem => Some(device.clone()),
            _ => None,
        })
    }

    /// Returns the syspath of this `Device`. It will point to a location in sysfs.
    pub fn syspath(&self) -> &Path {
        self.sysfs_path.as_path()
    }

    /// Returns the name of this `Device` as it is known in sysfs.
    pub fn name(&self) -> Option<&str> {
        self.sysfs_path.file_name()?.to_str()
    }

    /// Returns the name of the subsystem this `Device` belongs to.
    pub fn subsystem(&self) -> Option<String> {
        self.walk_parents(|device| device.get_link_target_filename("subsystem"))
    }

    /// Returns the name of the kernel driver managing this `Device`.
    pub fn driver(&self) -> Option<String> {
        self.walk_parents(|device| device.get_link_target_filename("driver"))
    }

    /// Returns the device pointed to by the device sysfs attribute. This may not
    /// always exist.
    pub fn device(&self) -> Option<Device> {
        match fs::canonicalize(self.sysfs_path.join("device")) {
            Ok(path) => Self::with_root_and_syspath(self.sysfs_root.clone(), path),
            Err(_) => None,
        }
    }

    /// Returns an object allowing you to query and set sysfs attributes for this
    /// `Device`.
    pub fn sysattrs(&self) -> FilesystemAttributeMap {
        self.sysattrs.clone()
    }

    /// Returns a map of all uevent vars associated with this `Device`.
    pub fn vars(&self) -> HashMap<String, String> {
        let Ok(uevent_vars) = self.sysattrs.get("uevent") else {
            return HashMap::new();
        };

        let mut vars = HashMap::new();
        for var in uevent_vars.lines() {
            if let Some((key, val)) = var.split_once('=') {
                vars.insert(key.to_owned(), val.to_owned());
            }
        }
        vars
    }

    fn walk_parents<T, F: Fn(&Device) -> Option<T>>(&self, f: F) -> Option<T> {
        let mut device = self.clone();
        loop {
            if let Some(val) = f(&device) {
                return Some(val);
            }

            device = device.parent()?;
        }
    }

    fn get_link_target_filename(&self, link: &str) -> Option<String> {
        match fs::canonicalize(self.sysfs_path.join(link)) {
            Ok(path) => Some(path.file_name()?.to_str()?.to_owned()),
            Err(_) => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use crate::device::{Device, DeviceNumber};
    use crate::mock_sysfs::{MockSysfs, SysfsFile};

    #[test]
    fn name() {
        let sysfs = SysfsFile::Dir(HashMap::from([(
            "squads/31a/kayamori_ruka",
            SysfsFile::Dir(HashMap::from([("uevent", SysfsFile::RegularFile(""))])),
        )]));

        let sysfs_dir = match MockSysfs::new(sysfs) {
            Ok(ms) => ms,
            Err(e) => panic!("Could not create mock sysfs: {e}"),
        };

        let sysfs_path = sysfs_dir.path().join("squads/31a/kayamori_ruka");

        let device = Device::with_root_and_syspath(sysfs_dir.path(), &sysfs_path)
            .expect("should create device");
        assert_eq!(device.name(), Some("kayamori_ruka"));
    }

    #[test]
    fn parent() {
        let sysfs = SysfsFile::Dir(HashMap::from([(
            "squads/31a",
            SysfsFile::Dir(HashMap::from([
                (
                    "kayamori_ruka",
                    SysfsFile::Dir(HashMap::from([("uevent", SysfsFile::RegularFile(""))])),
                ),
                ("uevent", SysfsFile::RegularFile("")),
            ])),
        )]));

        let sysfs_dir = match MockSysfs::new(sysfs) {
            Ok(ms) => ms,
            Err(e) => panic!("Could not create mock sysfs: {e}"),
        };

        let sysfs_path = sysfs_dir.path().join("squads/31a/kayamori_ruka");

        let device = Device::with_root_and_syspath(sysfs_dir.path(), &sysfs_path)
            .expect("should create device");
        let parent = device.parent().expect("should have parent");
        assert_eq!(parent.syspath(), sysfs_dir.path().join("squads/31a"));
    }

    #[test]
    fn get_attr() {
        let sysfs = SysfsFile::Dir(HashMap::from([(
            "squads/31a/kunimi_tama",
            SysfsFile::Dir(HashMap::from([
                ("nickname_en", SysfsFile::RegularFile("cappy")),
                ("nickname_jp", SysfsFile::RegularFile("otamasan")),
                ("uevent", SysfsFile::RegularFile("")),
            ])),
        )]));

        let sysfs_dir = match MockSysfs::new(sysfs) {
            Ok(ms) => ms,
            Err(e) => panic!("Could not create mock sysfs: {e}"),
        };

        let sysfs_path = sysfs_dir.path().join("squads/31a/kunimi_tama");

        let device = Device::with_root_and_syspath(sysfs_dir.path(), &sysfs_path)
            .expect("should create device");
        let sysattrs = device.sysattrs();
        assert_eq!(sysattrs.get("nickname_en").expect("should have nickname_en"), "cappy");
        assert_eq!(sysattrs.get("nickname_jp").expect("should have nickname_jp"), "otamasan");
        assert!(sysattrs.get("limit_breaks").is_err());
    }

    #[test]
    fn set_attr() {
        let sysfs = SysfsFile::Dir(HashMap::from([(
            "squads/31c/yamawaki_bon_ivar",
            SysfsFile::Dir(HashMap::from([("uevent", SysfsFile::RegularFile(""))])),
        )]));

        let sysfs_dir = match MockSysfs::new(sysfs) {
            Ok(ms) => ms,
            Err(e) => panic!("Could not create mock sysfs: {e}"),
        };

        let sysfs_path = sysfs_dir.path().join("squads/31c/yamawaki_bon_ivar");

        let device = Device::with_root_and_syspath(sysfs_dir.path(), &sysfs_path)
            .expect("should create device");
        let sysattrs = device.sysattrs();
        assert!(sysattrs.set("minions", "1").is_ok());
        assert_eq!(sysattrs.get("minions").expect("should have minions"), "1");
    }

    #[test]
    fn subsystem() {
        let sysfs = SysfsFile::Dir(HashMap::from([
            (
                "squads/31c/yamawaki_bon_ivar",
                SysfsFile::Dir(HashMap::from([
                    (
                        "memoria",
                        SysfsFile::Dir(HashMap::from([
                            (
                                "ebon_knight",
                                SysfsFile::Dir(HashMap::from([(
                                    "uevent",
                                    SysfsFile::RegularFile(""),
                                )])),
                            ),
                            (
                                "holy_knight",
                                SysfsFile::Dir(HashMap::from([
                                    (
                                        "subsystem",
                                        SysfsFile::Symlink("../../../../../roles/buffer"),
                                    ),
                                    ("uevent", SysfsFile::RegularFile("")),
                                ])),
                            ),
                        ])),
                    ),
                    ("subsystem", SysfsFile::Symlink("../../../roles/dps")),
                    ("uevent", SysfsFile::RegularFile("")),
                ])),
            ),
            ("roles/buffer", SysfsFile::Dir(HashMap::new())),
            ("roles/dps", SysfsFile::Dir(HashMap::new())),
        ]));

        let sysfs_dir = match MockSysfs::new(sysfs) {
            Ok(ms) => ms,
            Err(e) => panic!("Could not create mock sysfs: {e}"),
        };

        {
            let sysfs_path =
                sysfs_dir.path().join("squads/31c/yamawaki_bon_ivar/memoria/ebon_knight");

            let device = Device::with_root_and_syspath(sysfs_dir.path(), &sysfs_path)
                .expect("should create device");
            assert_eq!(device.subsystem().expect("should have subsystem"), "dps");
        }

        {
            let sysfs_path =
                sysfs_dir.path().join("squads/31c/yamawaki_bon_ivar/memoria/holy_knight");

            let device = Device::with_root_and_syspath(sysfs_dir.path(), &sysfs_path)
                .expect("should create device");
            assert_eq!(device.subsystem().expect("should have subsystem"), "buffer");
        }
    }

    #[test]
    fn parent_with_subsystem() {
        let sysfs = SysfsFile::Dir(HashMap::from([
            (
                "squads/31e",
                SysfsFile::Dir(HashMap::from([
                    (
                        "ohshima_isuzu",
                        SysfsFile::Dir(HashMap::from([
                            (
                                "memoria/key_to_victory",
                                SysfsFile::Dir(HashMap::from([(
                                    "uevent",
                                    SysfsFile::RegularFile(""),
                                )])),
                            ),
                            ("subsystem", SysfsFile::Symlink("../../../roles/debuffer")),
                            ("uevent", SysfsFile::RegularFile("")),
                        ])),
                    ),
                    ("subsystem", SysfsFile::Symlink("../../roles/squad")),
                    ("uevent", SysfsFile::RegularFile("")),
                ])),
            ),
            (
                "roles",
                SysfsFile::Dir(HashMap::from([
                    ("debuffer", SysfsFile::Dir(HashMap::new())),
                    ("squad", SysfsFile::Dir(HashMap::new())),
                ])),
            ),
        ]));

        let sysfs_dir = match MockSysfs::new(sysfs) {
            Ok(ms) => ms,
            Err(e) => panic!("Could not create mock sysfs: {e}"),
        };

        let sysfs_path = sysfs_dir.path().join("squads/31e/ohshima_isuzu/memoria/key_to_victory");

        let device = Device::with_root_and_syspath(sysfs_dir.path(), &sysfs_path)
            .expect("should create device");

        {
            let parent = device.parent_with_subsystem("debuffer");
            assert_eq!(
                parent.expect("parent device should exist").syspath(),
                sysfs_dir.path().join("squads/31e/ohshima_isuzu")
            );
        }

        {
            let parent = device.parent_with_subsystem("squad");
            assert_eq!(
                parent.expect("parent device should exist").syspath(),
                sysfs_dir.path().join("squads/31e")
            );
        }

        if device.parent_with_subsystem("something_else").is_some() {
            panic!("Found parent with subsystem that shouldn't exist");
        }
    }

    #[test]
    fn driver() {
        let sysfs = SysfsFile::Dir(HashMap::from([
            (
                "squads/31a",
                SysfsFile::Dir(HashMap::from([
                    ("driver", SysfsFile::Symlink("../../drivers/assault")),
                    (
                        "kayamori_ruka",
                        SysfsFile::Dir(HashMap::from([("uevent", SysfsFile::RegularFile(""))])),
                    ),
                    ("uevent", SysfsFile::RegularFile("")),
                ])),
            ),
            ("drivers/assault", SysfsFile::Dir(HashMap::new())),
        ]));

        let sysfs_dir = match MockSysfs::new(sysfs) {
            Ok(ms) => ms,
            Err(e) => panic!("Could not create mock sysfs: {e}"),
        };

        {
            let sysfs_path = sysfs_dir.path().join("squads/31a");

            let device = Device::with_root_and_syspath(sysfs_dir.path(), &sysfs_path)
                .expect("should create device");
            assert_eq!(device.driver().expect("should have driver"), "assault");
        }

        {
            let sysfs_path = sysfs_dir.path().join("squads/31a/kayamori_ruka");

            let device = Device::with_root_and_syspath(sysfs_dir.path(), &sysfs_path)
                .expect("should create device");
            assert_eq!(device.driver().expect("should have driver"), "assault");
        }
    }

    #[test]
    fn vars() {
        let sysfs = SysfsFile::Dir(HashMap::from([(
            "squads/30g/kura_satomi/memoria/goddess_of_harvest",
            SysfsFile::Dir(HashMap::from([(
                "uevent",
                SysfsFile::RegularFile("ELEMENT=light\nCLASS=blaster"),
            )])),
        )]));

        let sysfs_dir = match MockSysfs::new(sysfs) {
            Ok(ms) => ms,
            Err(e) => panic!("Could not create mock sysfs: {e}"),
        };

        let sysfs_path = sysfs_dir.path().join("squads/30g/kura_satomi/memoria/goddess_of_harvest");

        let device = Device::with_root_and_syspath(sysfs_dir.path(), &sysfs_path)
            .expect("should create device");
        let vars = device.vars();
        assert_eq!(vars["ELEMENT"], "light");
        assert_eq!(vars["CLASS"], "blaster");
    }

    #[test]
    fn from_devnum() {
        let sysfs = SysfsFile::Dir(HashMap::from([
            (
                "squads/31b/minase_ichigo",
                SysfsFile::Dir(HashMap::from([("uevent", SysfsFile::RegularFile(""))])),
            ),
            (
                "dev/char",
                SysfsFile::Dir(HashMap::from([(
                    "377:15",
                    SysfsFile::Symlink("../../squads/31b/minase_ichigo"),
                )])),
            ),
        ]));

        let sysfs_dir = match MockSysfs::new(sysfs) {
            Ok(ms) => ms,
            Err(e) => panic!("Could not create mock sysfs: {e}"),
        };

        let device = Device::with_root_and_devnum(
            sysfs_dir.path(),
            DeviceNumber::Char { major: 377, minor: 15 },
        )
        .expect("should create device");
        assert_eq!(device.name().expect("device should have name"), "minase_ichigo");
    }
}
