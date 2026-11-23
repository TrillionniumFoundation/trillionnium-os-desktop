//! Immutable, release-bound system_ext library subtree for the CP3A GSI.
use serde::{Deserialize, Serialize};

pub const SYSTEM_SHA256: &str = "dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4";
pub const TARGET: &str = "/system/system_ext/lib64";
pub const FILE: &str = "system_ext_lib64.img";
pub const ENGINE: &str = "libberberis_arm64";
pub const ORIGINAL_HAL: &str = "android.hidl.memory@1.0-impl.so";
pub const ORIGINAL_HAL_SHA256: &str =
    "16d2b993998d519f533a7d95655dbcaaf37465c9cbbac8d5560c17f28f2817ec";

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Declaration {
    pub file: String,
    pub bytes: u64,
    pub sha256: String,
    pub target: String,
    pub source_system_sha256: String,
    pub source_vendor_sha256: String,
}

pub fn accepts(
    schema: u32,
    scope: &str,
    extension: Option<&Declaration>,
    system: &str,
    vendor: &str,
) -> bool {
    match (schema, scope, extension) {
        (1, "android_base_images_v1", None) => true,
        (2, "android_base_images_v2", Some(ext)) => {
            ext.file == FILE
                && ext.target == TARGET
                && system == SYSTEM_SHA256
                && ext.source_system_sha256 == system
                && ext.source_vendor_sha256 == vendor
                && (4096..=8 * 1024 * 1024 * 1024).contains(&ext.bytes)
                && ext.bytes % 512 == 0
                && ext.sha256.len() == 64
                && ext
                    .sha256
                    .bytes()
                    .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
        }
        _ => false,
    }
}

pub const HOST_MODULES: &[&str] = &[
    "libberberis_exec_region",
    "libberberis_proxy_libEGL",
    "libberberis_proxy_libGLESv1_CM",
    "libberberis_proxy_libGLESv2",
    "libberberis_proxy_libGLESv3",
    "libberberis_proxy_libOpenMAXAL",
    "libberberis_proxy_libOpenSLES",
    "libberberis_proxy_libaaudio",
    "libberberis_proxy_libamidi",
    "libberberis_proxy_libandroid",
    "libberberis_proxy_libandroid_runtime",
    "libberberis_proxy_libbinder_ndk",
    "libberberis_proxy_libc",
    "libberberis_proxy_libcamera2ndk",
    "libberberis_proxy_libjnigraphics",
    "libberberis_proxy_libm",
    "libberberis_proxy_libmediandk",
    "libberberis_proxy_libnativehelper",
    "libberberis_proxy_libnativewindow",
    "libberberis_proxy_libneuralnetworks",
    "libberberis_proxy_libvulkan",
    "libberberis_proxy_libwebviewchromium_plat_support",
    "libberberis_arm64",
];
#[cfg(test)]
mod tests {
    use super::*;

    fn candidate() -> Declaration {
        Declaration {
            file: FILE.into(),
            bytes: 24 * 1024 * 1024,
            sha256: "1".repeat(64),
            target: TARGET.into(),
            source_system_sha256: SYSTEM_SHA256.into(),
            source_vendor_sha256: "2".repeat(64),
        }
    }

    #[test]
    fn library_selection_preserves_v1_and_rejects_version_confusion() {
        let d = candidate();
        assert!(accepts(
            1,
            "android_base_images_v1",
            None,
            "system",
            "vendor"
        ));
        assert!(!accepts(
            1,
            "android_base_images_v1",
            Some(&d),
            SYSTEM_SHA256,
            &d.source_vendor_sha256
        ));
        assert!(!accepts(
            2,
            "android_base_images_v2",
            None,
            SYSTEM_SHA256,
            &d.source_vendor_sha256
        ));
        assert!(accepts(
            2,
            "android_base_images_v2",
            Some(&d),
            SYSTEM_SHA256,
            &d.source_vendor_sha256
        ));
    }

    #[test]
    fn library_selection_rejects_mismatched_generation_and_relocated_mount() {
        let mut d = candidate();
        assert!(!accepts(
            2,
            "android_base_images_v2",
            Some(&d),
            SYSTEM_SHA256,
            &"3".repeat(64)
        ));
        assert!(!accepts(
            2,
            "android_base_images_v2",
            Some(&d),
            &"4".repeat(64),
            &d.source_vendor_sha256
        ));
        d.target = "/system/lib64".into();
        assert!(!accepts(
            2,
            "android_base_images_v2",
            Some(&d),
            SYSTEM_SHA256,
            &d.source_vendor_sha256
        ));
        d.target = TARGET.into();
        d.file = "../system.img".into();
        assert!(!accepts(
            2,
            "android_base_images_v2",
            Some(&d),
            SYSTEM_SHA256,
            &d.source_vendor_sha256
        ));
    }
}
