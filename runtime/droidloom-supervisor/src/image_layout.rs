//! Explicit Android partition layout and bounded paths inside one cell.

use std::ffi::OsStr;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

/// Physical organization of the verified Android image set.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AndroidImageLayout {
    /// Separate system, system_ext and product images, the existing default.
    #[default]
    SplitPartitions,
    /// One system-as-root GSI containing product and system_ext below /system.
    GsiSystemAsRoot,
}

impl AndroidImageLayout {
    pub(crate) const fn is_split(&self) -> bool {
        matches!(self, Self::SplitPartitions)
    }

    pub(crate) const fn image_roles(self) -> &'static [&'static str] {
        match self {
            Self::SplitPartitions => &["system", "system_ext", "product"],
            Self::GsiSystemAsRoot => &["system"],
        }
    }

    // Normalize only the two declared GSI aliases. Other image symlinks are
    // still rejected by the existing real-directory override-parent checks.
    pub(crate) fn partition_target(self, target: &Path) -> PathBuf {
        if self == Self::GsiSystemAsRoot {
            for (alias, actual) in [
                ("/product", "/system/product"),
                ("/system_ext", "/system/system_ext"),
            ] {
                if let Ok(suffix) = target.strip_prefix(alias) {
                    return Path::new(actual).join(suffix);
                }
            }
        }
        target.to_path_buf()
    }

    pub(crate) fn root_link(self, name: &OsStr, original: &Path) -> Result<PathBuf, String> {
        if self == Self::GsiSystemAsRoot {
            let expected = if name == "product" {
                Some("/system/product")
            } else if name == "system_ext" {
                Some("/system/system_ext")
            } else {
                None
            };
            if let Some(expected) = expected {
                if original != Path::new(expected) {
                    return Err(format!(
                        "GSI root alias {} must point to {expected}",
                        name.to_string_lossy()
                    ));
                }
                // Before chroot, an absolute link would resolve in the host.
                // A root-relative equivalent in private tmpfs has identical
                // guest semantics and stays inside the cell during setup.
                return Ok(PathBuf::from(expected.trim_start_matches('/')));
            }
        }
        Ok(original.to_path_buf())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn gsi_partition_paths_use_only_declared_aliases() {
        let layout = AndroidImageLayout::GsiSystemAsRoot;
        assert_eq!(
            layout.partition_target(Path::new("/product/app/Calendar/Calendar.apk")),
            PathBuf::from("/system/product/app/Calendar/Calendar.apk")
        );
        assert_eq!(
            layout.partition_target(Path::new("/system_ext/priv-app/SystemUI/SystemUI.apk")),
            PathBuf::from("/system/system_ext/priv-app/SystemUI/SystemUI.apk")
        );
        for path in ["/system/bin/init", "/vendor/etc/fstab", "/production/file"] {
            assert_eq!(layout.partition_target(Path::new(path)), Path::new(path));
        }
        assert_eq!(
            AndroidImageLayout::SplitPartitions.partition_target(Path::new("/product/app/a.apk")),
            Path::new("/product/app/a.apk")
        );
    }

    #[test]
    fn gsi_root_aliases_never_resolve_in_the_host() {
        let layout = AndroidImageLayout::GsiSystemAsRoot;
        assert_eq!(
            layout
                .root_link(OsStr::new("product"), Path::new("/system/product"))
                .unwrap(),
            Path::new("system/product")
        );
        assert_eq!(
            layout
                .root_link(OsStr::new("system_ext"), Path::new("/system/system_ext"))
                .unwrap(),
            Path::new("system/system_ext")
        );
        for wrong in [
            "/etc",
            "../../outside",
            "/system/../product",
            "system/product",
        ] {
            assert!(
                layout
                    .root_link(OsStr::new("product"), Path::new(wrong))
                    .is_err()
            );
        }
        assert_eq!(
            AndroidImageLayout::SplitPartitions
                .root_link(OsStr::new("product"), Path::new("/system/product"))
                .unwrap(),
            Path::new("/system/product")
        );
    }
}
