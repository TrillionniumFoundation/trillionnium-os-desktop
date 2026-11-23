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

pub const OBSERVER_ONLY_RC_SHA256: &str =
    "1e90d58b974d71ac12ddacaac43b59492bdea9bef442c9ee5da1286842ee599c";
pub const SHUTDOWN_RC_SHA256: &str =
    "57579b6cd84d16194480a4ea73c510d02fee2ddfef3ee26904246430b3efbb35";
pub const FACTORY_PROPERTY_CONTEXTS_SHA256: &str =
    "fae8632a118192c5dbb59c3a1096f575f410ae9eee80854355861e96a79eb0fd";
pub const SHUTDOWN_PROPERTY_CONTEXTS_SHA256: &str =
    "ca32c601b2debee94be7a5088f7050864e13e85e06e34598aef0b5925e154098";
pub const ORDERLY_CONTROL_RC_SHA256: &str =
    "ae320041a5d3f2d7c3f2a1689ffbdc17028f272cc81c5ee25757abe17e366b2c";
pub const ORDERLY_CONTROL_PROPERTY_SHA256: &str =
    "6c1a44f77bee433791a081c9f0175147df1438b39c0b64398830d7fbc50794cc";

pub fn shutdown_property_for_rc(rc: &str) -> Option<&'static str> {
    match rc {
        SHUTDOWN_RC_SHA256 => Some(SHUTDOWN_PROPERTY_CONTEXTS_SHA256),
        ORDERLY_CONTROL_RC_SHA256 => Some(ORDERLY_CONTROL_PROPERTY_SHA256),
        _ => None,
    }
}
pub const SHUTDOWN_PROPERTY_TARGET: &str =
    "/system/system_ext/etc/selinux/system_ext_property_contexts";

pub const READINESS_FILE: &str = "system_ext_readiness.img";
pub const READINESS_TARGETS: [&str; 2] = ["/system/system_ext/bin", "/system/system_ext/etc/init"];

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ReadinessDeclaration {
    pub file: String,
    pub bytes: u64,
    pub sha256: String,
    pub targets: [String; 2],
    pub source_system_sha256: String,
    pub source_vendor_sha256: String,
    pub source_system_ext_lib64_sha256: String,
    pub observer_sha256: String,
    pub init_rc_sha256: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub shutdown_property_contexts_sha256: Option<String>,
}

fn sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

/// Admit an exact two-, three-, or four-image raw release. The two readiness
/// subtrees always come from a single fourth filesystem.
pub fn accepts_base(
    schema: u32,
    scope: &str,
    library: Option<&Declaration>,
    readiness: Option<&ReadinessDeclaration>,
    system: &str,
    vendor: &str,
) -> bool {
    if schema != 3 {
        return readiness.is_none() && accepts(schema, scope, library, system, vendor);
    }
    let (Some(lib), Some(ready)) = (library, readiness) else {
        return false;
    };
    scope == "android_base_images_v3"
        && accepts(2, "android_base_images_v2", Some(lib), system, vendor)
        && ready.file == READINESS_FILE
        && ready.targets == READINESS_TARGETS
        && ready.shutdown_property_contexts_sha256.as_deref()
            == shutdown_property_for_rc(&ready.init_rc_sha256)
        && (4096..=16 * 1024 * 1024).contains(&ready.bytes)
        && ready.bytes % 512 == 0
        && ready.source_system_sha256 == system
        && ready.source_vendor_sha256 == vendor
        && ready.source_system_ext_lib64_sha256 == lib.sha256
        && [
            ready.sha256.as_str(),
            ready.observer_sha256.as_str(),
            ready.init_rc_sha256.as_str(),
        ]
        .iter()
        .all(|v| sha256(v))
        && ![system, vendor, &lib.sha256].contains(&ready.sha256.as_str())
        && ready.observer_sha256 != ready.init_rc_sha256
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
    fn fourth_image_binds_all_three_parents_and_both_install_paths() {
        let lib = candidate();
        let ready = ReadinessDeclaration {
            file: READINESS_FILE.into(),
            bytes: 8 * 1024 * 1024,
            sha256: "a".repeat(64),
            targets: READINESS_TARGETS.map(str::to_owned),
            source_system_sha256: SYSTEM_SHA256.into(),
            source_vendor_sha256: lib.source_vendor_sha256.clone(),
            source_system_ext_lib64_sha256: lib.sha256.clone(),
            observer_sha256: "c".repeat(64),
            init_rc_sha256: "d".repeat(64),
            shutdown_property_contexts_sha256: None,
        };
        let admit = |d: &ReadinessDeclaration| {
            accepts_base(
                3,
                "android_base_images_v3",
                Some(&lib),
                Some(d),
                SYSTEM_SHA256,
                &lib.source_vendor_sha256,
            )
        };
        assert!(admit(&ready));
        let mut shutdown = ready.clone();
        shutdown.init_rc_sha256 = SHUTDOWN_RC_SHA256.into();
        assert!(!admit(&shutdown));
        shutdown.shutdown_property_contexts_sha256 = Some(SHUTDOWN_PROPERTY_CONTEXTS_SHA256.into());
        assert!(admit(&shutdown));
        shutdown.init_rc_sha256 = ORDERLY_CONTROL_RC_SHA256.into();
        assert!(!admit(&shutdown));
        shutdown.shutdown_property_contexts_sha256 = Some(ORDERLY_CONTROL_PROPERTY_SHA256.into());
        assert!(admit(&shutdown));
        shutdown.init_rc_sha256 = OBSERVER_ONLY_RC_SHA256.into();
        assert!(!admit(&shutdown));
        shutdown.init_rc_sha256 = SHUTDOWN_RC_SHA256.into();
        shutdown.shutdown_property_contexts_sha256 = Some(FACTORY_PROPERTY_CONTEXTS_SHA256.into());
        assert!(!admit(&shutdown));
        for i in 0..5 {
            let mut other = ready.clone();
            match i {
                0 => other.source_system_sha256 = "0".repeat(64),
                1 => other.source_vendor_sha256 = "0".repeat(64),
                2 => other.source_system_ext_lib64_sha256 = "0".repeat(64),
                3 => other.targets.swap(0, 1),
                _ => other.init_rc_sha256 = other.observer_sha256.clone(),
            };
            assert!(!admit(&other));
        }
        assert!(!accepts_base(
            2,
            "android_base_images_v2",
            Some(&lib),
            Some(&ready),
            SYSTEM_SHA256,
            &lib.source_vendor_sha256
        ));
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
