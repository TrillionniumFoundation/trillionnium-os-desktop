//! Exact ART inputs of the same original CP3A system used by the five query roles.
//! Derived from original protobuf fragments: ART, system, sorted non-ART APEX.
//! The 45 original APEX containers, including EROFS virt, were inspected.
//! Derivation SHA256: 9372d37ffbdb98c8fd76e88870e948345394b847a62d8b0a88fb6739b8b58b02
//! Original JAR pins SHA256: 49e32c683aa73fb614bcd1a98ef95dffb8ddc5b19e7209b296338bfce0a1d475
use std::ffi::CStr;

pub(super) const SOURCE_SYSTEM_SHA256: &str =
    "dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4";
pub(super) const TOTAL_BYTES: u64 = 85_745_138;
pub(super) const BOOTCLASSPATH: &CStr = c"BOOTCLASSPATH=/apex/com.android.art/javalib/core-oj.jar:/apex/com.android.art/javalib/core-libart.jar:/apex/com.android.art/javalib/okhttp.jar:/apex/com.android.art/javalib/bouncycastle.jar:/apex/com.android.art/javalib/apache-xml.jar:/system/framework/framework.jar:/system/framework/framework-graphics.jar:/system/framework/framework-location.jar:/system/framework/ext.jar:/system/framework/telephony-common.jar:/system/framework/voip-common.jar:/system/framework/ims-common.jar:/system/framework/framework-ondeviceintelligence-platform.jar:/apex/com.android.i18n/javalib/core-icu4j.jar:/apex/com.android.adservices/javalib/framework-adservices.jar:/apex/com.android.adservices/javalib/framework-sdksandbox.jar:/apex/com.android.appsearch/javalib/framework-appsearch.jar:/apex/com.android.bt/javalib/framework-bluetooth.jar:/apex/com.android.configinfrastructure/javalib/framework-configinfrastructure.jar:/apex/com.android.conscrypt/javalib/conscrypt.jar:/apex/com.android.conscrypt/javalib/framework-conscrypt-nsc.jar:/apex/com.android.crashrecovery/javalib/framework-crashrecovery.jar:/apex/com.android.devicelock/javalib/framework-devicelock.jar:/apex/com.android.healthfitness/javalib/framework-healthfitness.jar:/apex/com.android.ipsec/javalib/android.net.ipsec.ike.jar:/apex/com.android.media/javalib/updatable-media.jar:/apex/com.android.mediaprovider/javalib/framework-mediaprovider.jar:/apex/com.android.mediaprovider/javalib/framework-pdf.jar:/apex/com.android.mediaprovider/javalib/framework-pdf-v.jar:/apex/com.android.mediaprovider/javalib/framework-photopicker.jar:/apex/com.android.nfcservices/javalib/framework-nfc.jar:/apex/com.android.npumanager/javalib/framework-npumanager.jar:/apex/com.android.ondevicepersonalization/javalib/framework-ondevicepersonalization.jar:/apex/com.android.os.statsd/javalib/framework-statsd.jar:/apex/com.android.permission/javalib/framework-permission.jar:/apex/com.android.permission/javalib/framework-permission-s.jar:/apex/com.android.profiling/javalib/framework-anomaly-detector.jar:/apex/com.android.profiling/javalib/framework-profiling.jar:/apex/com.android.scheduling/javalib/framework-scheduling.jar:/apex/com.android.sdkext/javalib/framework-sdkextensions.jar:/apex/com.android.telephonycore/javalib/framework-telecom.jar:/apex/com.android.telephonycore/javalib/framework-telephony.jar:/apex/com.android.tethering/javalib/framework-connectivity.jar:/apex/com.android.tethering/javalib/framework-connectivity-b.jar:/apex/com.android.tethering/javalib/framework-connectivity-t.jar:/apex/com.android.tethering/javalib/framework-tethering.jar:/apex/com.android.uprobestats/javalib/framework-uprobestats.jar:/apex/com.android.uwb/javalib/framework-ranging.jar:/apex/com.android.uwb/javalib/framework-uwb.jar:/apex/com.android.virt/javalib/framework-virtualization.jar:/apex/com.android.webapp/javalib/framework-webapp.jar:/apex/com.android.wifi/javalib/framework-wifi.jar";
pub(super) const DEX2OATBOOTCLASSPATH: &CStr = c"DEX2OATBOOTCLASSPATH=/apex/com.android.art/javalib/core-oj.jar:/apex/com.android.art/javalib/core-libart.jar:/apex/com.android.art/javalib/okhttp.jar:/apex/com.android.art/javalib/bouncycastle.jar:/apex/com.android.art/javalib/apache-xml.jar:/system/framework/framework.jar:/system/framework/framework-graphics.jar:/system/framework/framework-location.jar:/system/framework/ext.jar:/system/framework/telephony-common.jar:/system/framework/voip-common.jar:/system/framework/ims-common.jar:/system/framework/framework-ondeviceintelligence-platform.jar:/apex/com.android.i18n/javalib/core-icu4j.jar";
pub(super) const ENVIRONMENT: [&CStr; 2] = [BOOTCLASSPATH, DEX2OATBOOTCLASSPATH];

pub(super) struct ArtJar {
    pub(super) path: &'static str,
    pub(super) components: &'static [&'static CStr],
    pub(super) bytes: u64,
    pub(super) sha256: [u8; 32],
    pub(super) original_uid: u32,
    pub(super) original_gid: u32,
    pub(super) original_label: &'static [u8],
    pub(super) original_filesystem: libc::c_long,
}
pub(super) const INPUTS: [ArtJar; 52] = [
    ArtJar {
        path: "/apex/com.android.art/javalib/core-oj.jar",
        original_filesystem: 0xef53,
        components: &[c"apex", c"com.android.art", c"javalib", c"core-oj.jar"],
        bytes: 6074840,
        sha256: [
            0xbe, 0x2f, 0x9f, 0xe7, 0x74, 0xfd, 0xd4, 0xbb, 0x5e, 0xca, 0xc4, 0xe3, 0x4b, 0xa3,
            0xfb, 0xe1, 0x0a, 0x93, 0x9f, 0x46, 0x16, 0x31, 0xc5, 0x20, 0xa5, 0x4b, 0x24, 0x06,
            0x39, 0x1b, 0xea, 0xb0,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.art/javalib/core-libart.jar",
        original_filesystem: 0xef53,
        components: &[c"apex", c"com.android.art", c"javalib", c"core-libart.jar"],
        bytes: 632525,
        sha256: [
            0x9d, 0xf7, 0xe3, 0x4f, 0x2e, 0x8e, 0xa7, 0x93, 0x1f, 0x2d, 0x03, 0x6c, 0xca, 0xb8,
            0xc0, 0x83, 0xe3, 0x94, 0x21, 0x94, 0x03, 0x0f, 0xa5, 0xe7, 0x50, 0x38, 0x25, 0xd0,
            0xa9, 0x33, 0x00, 0x71,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.art/javalib/okhttp.jar",
        original_filesystem: 0xef53,
        components: &[c"apex", c"com.android.art", c"javalib", c"okhttp.jar"],
        bytes: 368845,
        sha256: [
            0x7e, 0xa2, 0xa7, 0xee, 0x07, 0xdf, 0x14, 0xcc, 0x3f, 0xfe, 0x58, 0x75, 0x97, 0x0e,
            0x88, 0x58, 0x09, 0xc1, 0xf7, 0x3f, 0x84, 0x93, 0x87, 0x21, 0x1e, 0xe6, 0x02, 0xfd,
            0xe5, 0x62, 0x97, 0x67,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.art/javalib/bouncycastle.jar",
        original_filesystem: 0xef53,
        components: &[c"apex", c"com.android.art", c"javalib", c"bouncycastle.jar"],
        bytes: 1028929,
        sha256: [
            0x8d, 0x71, 0xf8, 0x10, 0x5b, 0xd4, 0x17, 0xc0, 0x1b, 0x6d, 0x9b, 0x00, 0x67, 0x8a,
            0xf4, 0xaf, 0x15, 0x06, 0x96, 0x96, 0xfa, 0x74, 0x1a, 0x8d, 0x1e, 0x80, 0x3b, 0xfc,
            0x10, 0x13, 0x33, 0x85,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.art/javalib/apache-xml.jar",
        original_filesystem: 0xef53,
        components: &[c"apex", c"com.android.art", c"javalib", c"apache-xml.jar"],
        bytes: 1055543,
        sha256: [
            0xda, 0xc4, 0x57, 0x6d, 0x84, 0xf9, 0xae, 0x1d, 0x15, 0x5a, 0xb0, 0xa9, 0x8a, 0x32,
            0x25, 0x19, 0xa5, 0x9d, 0x5b, 0xbb, 0xa7, 0xcd, 0x49, 0x21, 0xee, 0x59, 0xda, 0x62,
            0x53, 0x60, 0xf7, 0x0c,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/system/framework/framework.jar",
        original_filesystem: 0xef53,
        components: &[c"system", c"framework", c"framework.jar"],
        bytes: 49754098,
        sha256: [
            0xbc, 0x8a, 0x17, 0x5a, 0x95, 0xdc, 0xb5, 0x0b, 0x5a, 0xe6, 0x2a, 0x03, 0xa0, 0xec,
            0x2b, 0xa0, 0xfd, 0xea, 0x34, 0x16, 0x9f, 0x83, 0xb2, 0xaa, 0xb3, 0xc8, 0xbf, 0x27,
            0x90, 0x70, 0x75, 0x87,
        ],
        original_uid: 0,
        original_gid: 0,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/system/framework/framework-graphics.jar",
        original_filesystem: 0xef53,
        components: &[c"system", c"framework", c"framework-graphics.jar"],
        bytes: 4073,
        sha256: [
            0x8c, 0xcb, 0x3a, 0x4c, 0xe7, 0xaf, 0xff, 0x92, 0x76, 0x00, 0x69, 0x97, 0xcd, 0x03,
            0x75, 0x68, 0xbf, 0x91, 0xb6, 0xeb, 0x5a, 0x83, 0xe2, 0xd3, 0xf6, 0x62, 0x8f, 0xf4,
            0x1e, 0xdd, 0xfb, 0xe5,
        ],
        original_uid: 0,
        original_gid: 0,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/system/framework/framework-location.jar",
        original_filesystem: 0xef53,
        components: &[c"system", c"framework", c"framework-location.jar"],
        bytes: 537601,
        sha256: [
            0xc3, 0x72, 0x33, 0x6a, 0x63, 0x45, 0xf0, 0x29, 0xd7, 0x88, 0xf5, 0xfd, 0x54, 0xeb,
            0x0a, 0x0f, 0xdf, 0x62, 0x57, 0x23, 0x16, 0x66, 0x3f, 0x10, 0x13, 0xf9, 0x89, 0xdd,
            0xef, 0x6c, 0x45, 0x4d,
        ],
        original_uid: 0,
        original_gid: 0,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/system/framework/ext.jar",
        original_filesystem: 0xef53,
        components: &[c"system", c"framework", c"ext.jar"],
        bytes: 2308419,
        sha256: [
            0x6d, 0x6d, 0x86, 0x8b, 0xed, 0xee, 0xa4, 0x23, 0x7d, 0x51, 0xc8, 0x5f, 0x8a, 0xc2,
            0x21, 0x22, 0xa3, 0x4e, 0x4f, 0xa7, 0xd9, 0x6c, 0x71, 0x0a, 0xe9, 0xec, 0x4b, 0x83,
            0x65, 0x70, 0xbc, 0x33,
        ],
        original_uid: 0,
        original_gid: 0,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/system/framework/telephony-common.jar",
        original_filesystem: 0xef53,
        components: &[c"system", c"framework", c"telephony-common.jar"],
        bytes: 5733717,
        sha256: [
            0x4b, 0x9e, 0x09, 0x0b, 0xe1, 0x20, 0x62, 0x14, 0x96, 0xbc, 0xf1, 0x81, 0x8b, 0x25,
            0xc4, 0x4f, 0x8a, 0x3e, 0x31, 0x1d, 0x82, 0x5e, 0x38, 0xa3, 0x99, 0x1b, 0x1a, 0xb3,
            0x09, 0x33, 0x04, 0xac,
        ],
        original_uid: 0,
        original_gid: 0,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/system/framework/voip-common.jar",
        original_filesystem: 0xef53,
        components: &[c"system", c"framework", c"voip-common.jar"],
        bytes: 826005,
        sha256: [
            0x26, 0xbd, 0x8b, 0x43, 0xfc, 0x3d, 0x0e, 0xc6, 0x2d, 0x21, 0x27, 0xdb, 0x8f, 0xfa,
            0x68, 0x0c, 0x70, 0xcf, 0xf3, 0x16, 0xaf, 0x99, 0x55, 0x1a, 0x23, 0xc8, 0x7f, 0x68,
            0x0c, 0xbc, 0xa2, 0x5f,
        ],
        original_uid: 0,
        original_gid: 0,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/system/framework/ims-common.jar",
        original_filesystem: 0xef53,
        components: &[c"system", c"framework", c"ims-common.jar"],
        bytes: 548445,
        sha256: [
            0x32, 0x08, 0x42, 0x3a, 0xb0, 0x1d, 0x3e, 0xbc, 0x34, 0x15, 0x93, 0xbc, 0x1b, 0x39,
            0x7b, 0x00, 0x6a, 0xee, 0x56, 0xdf, 0x8f, 0x36, 0x06, 0x41, 0x83, 0x61, 0x17, 0xfc,
            0x50, 0x8c, 0xbe, 0x6c,
        ],
        original_uid: 0,
        original_gid: 0,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/system/framework/framework-ondeviceintelligence-platform.jar",
        original_filesystem: 0xef53,
        components: &[
            c"system",
            c"framework",
            c"framework-ondeviceintelligence-platform.jar",
        ],
        bytes: 225193,
        sha256: [
            0x4c, 0x1b, 0xd2, 0xde, 0xf9, 0x17, 0x30, 0x9e, 0x37, 0x27, 0xb5, 0x65, 0x8e, 0xb3,
            0x99, 0x2f, 0x2e, 0x37, 0xc9, 0x67, 0xf0, 0xdc, 0x6e, 0xc5, 0xd8, 0xa3, 0xd3, 0x7e,
            0x4e, 0x64, 0xbd, 0x26,
        ],
        original_uid: 0,
        original_gid: 0,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.i18n/javalib/core-icu4j.jar",
        original_filesystem: 0xef53,
        components: &[c"apex", c"com.android.i18n", c"javalib", c"core-icu4j.jar"],
        bytes: 3007385,
        sha256: [
            0x8b, 0x37, 0xb0, 0x33, 0x45, 0x4e, 0x13, 0xdc, 0xd9, 0xe4, 0x63, 0xe0, 0xb6, 0x5a,
            0x71, 0x95, 0x4b, 0x70, 0xba, 0xb5, 0x95, 0xb9, 0xad, 0xc5, 0xe3, 0xca, 0x17, 0xff,
            0x36, 0x1c, 0xbf, 0x13,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.adservices/javalib/framework-adservices.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.adservices",
            c"javalib",
            c"framework-adservices.jar",
        ],
        bytes: 564225,
        sha256: [
            0x8c, 0xba, 0xda, 0x71, 0x5e, 0x87, 0xd8, 0xc2, 0xb0, 0x6f, 0x18, 0x9d, 0x3e, 0x33,
            0x5b, 0x91, 0x26, 0xc1, 0x7f, 0x96, 0x94, 0xe7, 0xc7, 0x50, 0x56, 0x73, 0x1b, 0x3f,
            0xb1, 0x3d, 0x77, 0xa9,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.adservices/javalib/framework-sdksandbox.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.adservices",
            c"javalib",
            c"framework-sdksandbox.jar",
        ],
        bytes: 96861,
        sha256: [
            0x0d, 0xac, 0xdf, 0x7b, 0xa2, 0x7c, 0xc6, 0xc8, 0x1b, 0x8d, 0xd4, 0x24, 0x8b, 0x94,
            0x38, 0xb5, 0xf6, 0x83, 0x63, 0x2c, 0x76, 0xbf, 0xd5, 0x79, 0xe4, 0x44, 0x51, 0xd4,
            0xd1, 0x0e, 0x18, 0x4c,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.appsearch/javalib/framework-appsearch.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.appsearch",
            c"javalib",
            c"framework-appsearch.jar",
        ],
        bytes: 393601,
        sha256: [
            0xdd, 0xed, 0x3f, 0x2f, 0x8f, 0x46, 0x68, 0xbc, 0xed, 0x3e, 0x5a, 0xd8, 0x05, 0x30,
            0xcd, 0xd6, 0x95, 0x4a, 0xbe, 0x79, 0x7b, 0xcd, 0xb4, 0x6a, 0x89, 0x5a, 0x83, 0x74,
            0x33, 0xb7, 0x6e, 0x4d,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.bt/javalib/framework-bluetooth.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.bt",
            c"javalib",
            c"framework-bluetooth.jar",
        ],
        bytes: 1357002,
        sha256: [
            0xcb, 0xc9, 0xbb, 0xa7, 0x6b, 0x2a, 0x91, 0x54, 0x22, 0xc7, 0x83, 0x46, 0x90, 0x80,
            0x52, 0x0a, 0x0b, 0x22, 0xc8, 0x4b, 0xa9, 0xd7, 0xfe, 0xdc, 0x23, 0x62, 0x5f, 0xe0,
            0x0a, 0x81, 0x1c, 0xfb,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.configinfrastructure/javalib/framework-configinfrastructure.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.configinfrastructure",
            c"javalib",
            c"framework-configinfrastructure.jar",
        ],
        bytes: 170573,
        sha256: [
            0x46, 0x75, 0x53, 0xd2, 0xc6, 0x92, 0xea, 0xb6, 0x40, 0x1c, 0x67, 0x1a, 0x61, 0xc2,
            0x6a, 0x1c, 0xd9, 0x9d, 0x47, 0x8e, 0x7b, 0x71, 0x4e, 0x49, 0x2e, 0x94, 0x7c, 0x19,
            0xcd, 0xed, 0x81, 0xb1,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.conscrypt/javalib/conscrypt.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.conscrypt",
            c"javalib",
            c"conscrypt.jar",
        ],
        bytes: 609093,
        sha256: [
            0x05, 0x26, 0x00, 0x81, 0x3d, 0xbb, 0xdc, 0x9a, 0xc4, 0xad, 0xe1, 0x7a, 0xfe, 0x2e,
            0x85, 0x88, 0x36, 0x89, 0xc7, 0xc8, 0x8b, 0x8b, 0xdb, 0xc1, 0x78, 0x2c, 0xbb, 0xe4,
            0xab, 0x00, 0x0e, 0x06,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.conscrypt/javalib/framework-conscrypt-nsc.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.conscrypt",
            c"javalib",
            c"framework-conscrypt-nsc.jar",
        ],
        bytes: 87090,
        sha256: [
            0xf9, 0x73, 0x0a, 0x8b, 0xd5, 0x8e, 0x3f, 0x4b, 0x89, 0x33, 0xb4, 0xca, 0x3e, 0xc0,
            0xa9, 0x90, 0xdd, 0xac, 0x8e, 0x43, 0xf4, 0xb4, 0xec, 0x92, 0xe9, 0xb9, 0x8c, 0xc2,
            0x13, 0x40, 0x5d, 0x12,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.crashrecovery/javalib/framework-crashrecovery.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.crashrecovery",
            c"javalib",
            c"framework-crashrecovery.jar",
        ],
        bytes: 17293,
        sha256: [
            0x18, 0xd1, 0x02, 0x12, 0x6d, 0xe3, 0x12, 0x32, 0x6d, 0x3b, 0xcf, 0x07, 0x30, 0xa4,
            0xa2, 0x91, 0x1d, 0xb2, 0x6e, 0x80, 0xc0, 0x35, 0xbb, 0x69, 0x75, 0x2c, 0xfe, 0xa0,
            0x09, 0xa4, 0x59, 0xff,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.devicelock/javalib/framework-devicelock.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.devicelock",
            c"javalib",
            c"framework-devicelock.jar",
        ],
        bytes: 35785,
        sha256: [
            0xc1, 0x8d, 0x54, 0xc3, 0xd4, 0x6c, 0xa6, 0x2a, 0x0f, 0x34, 0x51, 0x11, 0x26, 0x4a,
            0xed, 0x57, 0x1b, 0x15, 0xb3, 0x9a, 0x3f, 0x19, 0x63, 0x7e, 0x6d, 0xc8, 0x72, 0xab,
            0xd1, 0xc2, 0xfc, 0x17,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.healthfitness/javalib/framework-healthfitness.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.healthfitness",
            c"javalib",
            c"framework-healthfitness.jar",
        ],
        bytes: 1003717,
        sha256: [
            0x60, 0x50, 0x48, 0x9d, 0xbc, 0xbe, 0x0e, 0x9d, 0x64, 0x96, 0x69, 0x5e, 0x3d, 0xfd,
            0x20, 0x3d, 0xcb, 0x80, 0x05, 0x3a, 0xad, 0x58, 0xc9, 0x4a, 0x3f, 0x1a, 0x8f, 0xa6,
            0x10, 0x19, 0xa8, 0x08,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.ipsec/javalib/android.net.ipsec.ike.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.ipsec",
            c"javalib",
            c"android.net.ipsec.ike.jar",
        ],
        bytes: 753217,
        sha256: [
            0xfa, 0xc6, 0x26, 0xae, 0x02, 0x75, 0x3a, 0x60, 0xdb, 0xc9, 0x31, 0x89, 0xa5, 0x5d,
            0xaf, 0x99, 0xda, 0xb8, 0x89, 0x60, 0xe4, 0xa8, 0x33, 0x1e, 0xc7, 0x8f, 0xb2, 0xdd,
            0xef, 0x9e, 0x82, 0x48,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.media/javalib/updatable-media.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.media",
            c"javalib",
            c"updatable-media.jar",
        ],
        bytes: 795377,
        sha256: [
            0x66, 0xfc, 0xa6, 0xab, 0x96, 0x51, 0x8c, 0xb7, 0xd0, 0x42, 0x96, 0x1a, 0x81, 0x30,
            0xc1, 0x14, 0xa8, 0xc0, 0x3b, 0x40, 0xd3, 0x1f, 0xe8, 0x90, 0x6f, 0x1c, 0x8c, 0x7c,
            0x4a, 0xdd, 0x08, 0xd0,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.mediaprovider/javalib/framework-mediaprovider.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.mediaprovider",
            c"javalib",
            c"framework-mediaprovider.jar",
        ],
        bytes: 216585,
        sha256: [
            0xfd, 0x46, 0xcf, 0xf5, 0x6f, 0x0f, 0x42, 0x08, 0x5e, 0x0a, 0xbf, 0xc7, 0x87, 0x93,
            0x55, 0x67, 0xc9, 0x7f, 0x44, 0x82, 0xfd, 0x6f, 0x9d, 0x87, 0x47, 0xb1, 0xcd, 0x66,
            0xde, 0x3e, 0x38, 0xc0,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.mediaprovider/javalib/framework-pdf.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.mediaprovider",
            c"javalib",
            c"framework-pdf.jar",
        ],
        bytes: 138001,
        sha256: [
            0xfa, 0xd2, 0xd1, 0xf2, 0x95, 0x6c, 0x76, 0xdb, 0x2f, 0x80, 0x65, 0x93, 0x16, 0xe1,
            0x53, 0xc1, 0xfb, 0xdd, 0xff, 0xfe, 0xc8, 0xb0, 0x39, 0x2a, 0x72, 0xca, 0x70, 0x16,
            0x32, 0x96, 0x06, 0xf4,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.mediaprovider/javalib/framework-pdf-v.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.mediaprovider",
            c"javalib",
            c"framework-pdf-v.jar",
        ],
        bytes: 14885,
        sha256: [
            0x43, 0x23, 0x02, 0x09, 0x38, 0xd3, 0x1e, 0x7e, 0x73, 0xd9, 0x44, 0x54, 0x70, 0x59,
            0x7a, 0xa5, 0xf2, 0x66, 0xd9, 0x79, 0x16, 0x97, 0x07, 0x0a, 0xa7, 0xd2, 0x05, 0xe5,
            0xd6, 0x57, 0xe4, 0x83,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.mediaprovider/javalib/framework-photopicker.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.mediaprovider",
            c"javalib",
            c"framework-photopicker.jar",
        ],
        bytes: 56861,
        sha256: [
            0x88, 0x2a, 0x99, 0x3c, 0x5f, 0xc4, 0x97, 0xef, 0x6e, 0x0f, 0xd0, 0x8d, 0xd3, 0x05,
            0x9f, 0x5b, 0x13, 0xa5, 0xeb, 0xc9, 0xf9, 0x31, 0x57, 0x25, 0x42, 0xad, 0x61, 0x79,
            0x8a, 0x72, 0xf7, 0xf1,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.nfcservices/javalib/framework-nfc.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.nfcservices",
            c"javalib",
            c"framework-nfc.jar",
        ],
        bytes: 425833,
        sha256: [
            0x95, 0xf3, 0x01, 0x5b, 0x69, 0x9d, 0x89, 0xde, 0xad, 0xfd, 0x38, 0xe2, 0xeb, 0x56,
            0x64, 0xdb, 0x93, 0x54, 0x31, 0xa8, 0x81, 0x17, 0xe0, 0xc6, 0xe1, 0x91, 0x38, 0xf2,
            0xe5, 0xe7, 0xa3, 0x66,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.npumanager/javalib/framework-npumanager.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.npumanager",
            c"javalib",
            c"framework-npumanager.jar",
        ],
        bytes: 35329,
        sha256: [
            0xe6, 0x63, 0x5f, 0x02, 0x88, 0x09, 0x30, 0x72, 0x0d, 0x63, 0x53, 0x1d, 0xef, 0xf5,
            0xdb, 0x92, 0x28, 0x7e, 0xf7, 0x9a, 0xd9, 0xa6, 0x5d, 0xbf, 0xf2, 0xb8, 0xd5, 0x94,
            0xb9, 0xbf, 0x86, 0xa6,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.ondevicepersonalization/javalib/framework-ondevicepersonalization.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.ondevicepersonalization",
            c"javalib",
            c"framework-ondevicepersonalization.jar",
        ],
        bytes: 294253,
        sha256: [
            0x24, 0x9a, 0x51, 0x40, 0x0a, 0x54, 0x4b, 0x2a, 0xf8, 0x08, 0x2c, 0x3f, 0xfe, 0xb6,
            0x20, 0x0f, 0xd3, 0x9f, 0x46, 0x80, 0x58, 0x5b, 0x3c, 0x9d, 0x06, 0x59, 0x47, 0xaf,
            0x38, 0x2f, 0x6a, 0xcb,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.os.statsd/javalib/framework-statsd.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.os.statsd",
            c"javalib",
            c"framework-statsd.jar",
        ],
        bytes: 107561,
        sha256: [
            0x56, 0xba, 0x1a, 0x80, 0xeb, 0x51, 0x1f, 0x45, 0xed, 0x18, 0x52, 0x88, 0x61, 0x12,
            0x61, 0x41, 0x70, 0x73, 0xa7, 0x17, 0x3a, 0x47, 0xde, 0x38, 0x7b, 0xad, 0x37, 0xb2,
            0x40, 0x69, 0x8a, 0x5e,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.permission/javalib/framework-permission.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.permission",
            c"javalib",
            c"framework-permission.jar",
        ],
        bytes: 1089,
        sha256: [
            0x1c, 0xec, 0xbd, 0xcb, 0x36, 0x6e, 0xd9, 0x75, 0x1d, 0x94, 0xf3, 0x3d, 0xce, 0xf3,
            0xc7, 0x58, 0x87, 0x85, 0x67, 0xfa, 0x7a, 0xe5, 0x68, 0xb4, 0x00, 0x8d, 0x26, 0xe2,
            0xf3, 0x00, 0x38, 0x74,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.permission/javalib/framework-permission-s.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.permission",
            c"javalib",
            c"framework-permission-s.jar",
        ],
        bytes: 307981,
        sha256: [
            0x5d, 0x06, 0x6b, 0xaf, 0x80, 0x10, 0x02, 0xa1, 0xdc, 0x9a, 0xba, 0x7f, 0xc9, 0x16,
            0xb1, 0x56, 0x6a, 0xe1, 0x26, 0x14, 0x7c, 0xa2, 0xaf, 0xa5, 0x32, 0xa0, 0xef, 0x4f,
            0xd6, 0x2e, 0x79, 0x02,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.profiling/javalib/framework-anomaly-detector.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.profiling",
            c"javalib",
            c"framework-anomaly-detector.jar",
        ],
        bytes: 23641,
        sha256: [
            0x2a, 0x99, 0x52, 0x25, 0xf2, 0xef, 0x62, 0x49, 0x68, 0x0f, 0x19, 0xed, 0x75, 0x7e,
            0x29, 0xfa, 0xb5, 0x09, 0xed, 0xa6, 0x8b, 0x00, 0xf6, 0x75, 0xb6, 0xc3, 0xc0, 0xf6,
            0x6d, 0x27, 0xf0, 0x96,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.profiling/javalib/framework-profiling.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.profiling",
            c"javalib",
            c"framework-profiling.jar",
        ],
        bytes: 58749,
        sha256: [
            0x46, 0xd9, 0x6f, 0x42, 0x77, 0x97, 0x4c, 0x36, 0x12, 0x97, 0x7d, 0x4d, 0x83, 0xf8,
            0x8f, 0xb9, 0x9c, 0x2c, 0x4e, 0xa2, 0xc7, 0x69, 0xbe, 0xd9, 0x24, 0x84, 0x46, 0x64,
            0x3b, 0x57, 0x02, 0xb4,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.scheduling/javalib/framework-scheduling.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.scheduling",
            c"javalib",
            c"framework-scheduling.jar",
        ],
        bytes: 45369,
        sha256: [
            0xff, 0xea, 0x50, 0xa7, 0xff, 0xe6, 0x52, 0x17, 0xe6, 0xaf, 0x48, 0x93, 0x2c, 0xef,
            0xc4, 0x06, 0xe7, 0xe1, 0xe3, 0xf2, 0x69, 0x56, 0x58, 0x92, 0x99, 0x44, 0xfd, 0x80,
            0x3a, 0x93, 0x0a, 0xad,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.sdkext/javalib/framework-sdkextensions.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.sdkext",
            c"javalib",
            c"framework-sdkextensions.jar",
        ],
        bytes: 8089,
        sha256: [
            0x4d, 0xee, 0x89, 0x87, 0x41, 0x1d, 0x81, 0x1e, 0x7b, 0x84, 0x9a, 0xbd, 0x7b, 0xe1,
            0xe7, 0x64, 0xf2, 0xb6, 0x9a, 0x62, 0xdb, 0x9e, 0x41, 0xd2, 0x9c, 0xcd, 0x21, 0x13,
            0x19, 0x19, 0x7a, 0xb5,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.telephonycore/javalib/framework-telecom.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.telephonycore",
            c"javalib",
            c"framework-telecom.jar",
        ],
        bytes: 775043,
        sha256: [
            0xfd, 0x8b, 0x20, 0xb9, 0x41, 0x4f, 0x96, 0xbb, 0xf6, 0x85, 0x5b, 0x05, 0x1f, 0x8e,
            0x3a, 0x33, 0xc9, 0x9f, 0x9c, 0xca, 0xf2, 0xa2, 0x19, 0x65, 0x83, 0x0b, 0x96, 0x3f,
            0xd4, 0xe0, 0x0b, 0x5d,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.telephonycore/javalib/framework-telephony.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.telephonycore",
            c"javalib",
            c"framework-telephony.jar",
        ],
        bytes: 541021,
        sha256: [
            0x68, 0x4b, 0x2e, 0x63, 0xb2, 0x17, 0x4d, 0xa6, 0x0a, 0xc1, 0xa7, 0x0f, 0x21, 0x2b,
            0x8b, 0x86, 0x79, 0x98, 0x50, 0x79, 0x09, 0x5b, 0xfe, 0xf6, 0x09, 0x5b, 0xef, 0x13,
            0x84, 0xb6, 0x4e, 0xf4,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.tethering/javalib/framework-connectivity.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.tethering",
            c"javalib",
            c"framework-connectivity.jar",
        ],
        bytes: 1564867,
        sha256: [
            0xd5, 0xc6, 0x45, 0x80, 0x5a, 0x0e, 0xdf, 0xc1, 0x6b, 0x10, 0x61, 0x21, 0xac, 0x6f,
            0xa0, 0x9e, 0xf0, 0xb2, 0x86, 0xc3, 0x8f, 0x9f, 0x62, 0xca, 0x1c, 0x96, 0xca, 0xca,
            0x8b, 0x31, 0x5f, 0x59,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.tethering/javalib/framework-connectivity-b.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.tethering",
            c"javalib",
            c"framework-connectivity-b.jar",
        ],
        bytes: 123041,
        sha256: [
            0x80, 0xf3, 0x37, 0x75, 0xcc, 0xc9, 0xe9, 0x84, 0xff, 0x0b, 0xbc, 0x3b, 0x0a, 0x3a,
            0xa4, 0x97, 0x94, 0xdd, 0x67, 0x50, 0x52, 0xed, 0x48, 0xab, 0x72, 0x3a, 0xb3, 0x2f,
            0x5f, 0x84, 0xb7, 0xe8,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.tethering/javalib/framework-connectivity-t.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.tethering",
            c"javalib",
            c"framework-connectivity-t.jar",
        ],
        bytes: 581125,
        sha256: [
            0x54, 0x12, 0xf8, 0x34, 0xf8, 0x6b, 0xe3, 0xed, 0x0c, 0x6d, 0x42, 0x22, 0x34, 0x26,
            0xb0, 0xa8, 0xa5, 0x74, 0xbe, 0xb0, 0xb5, 0x08, 0xda, 0xa3, 0x55, 0x40, 0x45, 0xda,
            0x47, 0xce, 0xad, 0xc8,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.tethering/javalib/framework-tethering.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.tethering",
            c"javalib",
            c"framework-tethering.jar",
        ],
        bytes: 85765,
        sha256: [
            0x1f, 0x17, 0xad, 0x2d, 0x4e, 0xb3, 0x3c, 0x57, 0x7d, 0x22, 0xc6, 0x01, 0x63, 0xab,
            0x15, 0xaa, 0x61, 0x2a, 0x22, 0x73, 0xa3, 0x04, 0xd6, 0xa6, 0x0a, 0x93, 0x75, 0x5b,
            0x46, 0x2b, 0xe9, 0x4b,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.uprobestats/javalib/framework-uprobestats.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.uprobestats",
            c"javalib",
            c"framework-uprobestats.jar",
        ],
        bytes: 24725,
        sha256: [
            0xa4, 0x79, 0x84, 0xc1, 0xa6, 0x40, 0xcc, 0x49, 0xff, 0x00, 0x99, 0xe1, 0xbf, 0x0c,
            0xd1, 0xe0, 0xd2, 0x1a, 0x11, 0x9f, 0x4a, 0xb7, 0xce, 0x31, 0x7b, 0x66, 0x81, 0xd4,
            0xa4, 0xb4, 0x84, 0xb3,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.uwb/javalib/framework-ranging.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.uwb",
            c"javalib",
            c"framework-ranging.jar",
        ],
        bytes: 222553,
        sha256: [
            0xce, 0xb4, 0x9d, 0x14, 0xcc, 0xe6, 0x9c, 0xad, 0x26, 0x99, 0x56, 0x7f, 0xd7, 0xad,
            0x04, 0x8a, 0xa2, 0xe2, 0x38, 0x8e, 0x09, 0xb5, 0xa2, 0xcf, 0x17, 0x1b, 0xb8, 0x74,
            0x01, 0x44, 0x93, 0x7b,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.uwb/javalib/framework-uwb.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.uwb",
            c"javalib",
            c"framework-uwb.jar",
        ],
        bytes: 208273,
        sha256: [
            0x1c, 0xdf, 0x7f, 0x4a, 0xa7, 0xf9, 0x10, 0x7b, 0x11, 0xfc, 0xcc, 0xb5, 0x09, 0x85,
            0x70, 0x11, 0x15, 0xeb, 0x26, 0xe0, 0xc5, 0xaf, 0x5a, 0xd9, 0x48, 0x05, 0x54, 0xbf,
            0x24, 0x6c, 0xae, 0xd1,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.virt/javalib/framework-virtualization.jar",
        original_filesystem: 0xe0f5_e1e2_u32 as libc::c_long,
        components: &[
            c"apex",
            c"com.android.virt",
            c"javalib",
            c"framework-virtualization.jar",
        ],
        bytes: 218809,
        sha256: [
            0xad, 0xd5, 0x4a, 0xe7, 0xda, 0x2a, 0x43, 0xc4, 0x34, 0xbf, 0x59, 0xc8, 0x6f, 0xd8,
            0x13, 0x40, 0x3c, 0x8b, 0x6a, 0x93, 0xa0, 0x5e, 0x9a, 0x09, 0x74, 0x15, 0x46, 0x0d,
            0x26, 0x2a, 0xf9, 0xc5,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.webapp/javalib/framework-webapp.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.webapp",
            c"javalib",
            c"framework-webapp.jar",
        ],
        bytes: 23485,
        sha256: [
            0x4a, 0x11, 0xc7, 0x51, 0xe9, 0x44, 0xed, 0x72, 0x6d, 0x9e, 0x15, 0xe5, 0x0b, 0x11,
            0xf1, 0x24, 0x7c, 0xb6, 0x83, 0xb1, 0x16, 0xa7, 0x6c, 0x0d, 0x82, 0xdb, 0x3f, 0x11,
            0xa4, 0x89, 0x03, 0xc0,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
    ArtJar {
        path: "/apex/com.android.wifi/javalib/framework-wifi.jar",
        original_filesystem: 0xef53,
        components: &[
            c"apex",
            c"com.android.wifi",
            c"javalib",
            c"framework-wifi.jar",
        ],
        bytes: 1652753,
        sha256: [
            0x43, 0x7a, 0xc7, 0xa7, 0x76, 0xb7, 0xe1, 0x93, 0x32, 0xec, 0xec, 0xaf, 0x4d, 0x6f,
            0xe4, 0x27, 0xf1, 0xf2, 0x74, 0x81, 0x30, 0x58, 0x75, 0xa5, 0x3d, 0x05, 0x73, 0xd7,
            0xd7, 0x40, 0x92, 0xac,
        ],
        original_uid: 1000,
        original_gid: 1000,
        original_label: b"u:object_r:system_file:s0\0",
    },
];

pub(super) fn consistent() -> bool {
    let boot = BOOTCLASSPATH.to_bytes().strip_prefix(b"BOOTCLASSPATH=");
    let dex = DEX2OATBOOTCLASSPATH
        .to_bytes()
        .strip_prefix(b"DEX2OATBOOTCLASSPATH=");
    SOURCE_SYSTEM_SHA256 == crate::production_execution_profile::query_inputs::SYSTEM_SHA256
        && INPUTS.iter().map(|i| i.bytes).sum::<u64>() == TOTAL_BYTES
        && boot.is_some_and(|b| {
            b.split(|c| *c == b':')
                .eq(INPUTS.iter().map(|i| i.path.as_bytes()))
        })
        && dex.is_some_and(|b| {
            b.split(|c| *c == b':')
                .eq(INPUTS[..14].iter().map(|i| i.path.as_bytes()))
        })
        && INPUTS.iter().all(|i| {
            let components: Vec<_> = i.path.as_bytes().split(|c| *c == b'/').skip(1).collect();
            components.len() == i.components.len()
                && components
                    .iter()
                    .zip(i.components)
                    .all(|(a, b)| *a == b.to_bytes())
                && (64..=128 * 1024 * 1024).contains(&i.bytes)
                && matches!(i.original_uid, 0 | 1000)
                && i.original_gid == i.original_uid
                && i.original_filesystem
                    == if i.path == "/apex/com.android.virt/javalib/framework-virtualization.jar" {
                        0xe0f5_e1e2_u32 as libc::c_long
                    } else {
                        0xef53
                    }
                && i.original_label == b"u:object_r:system_file:s0\0"
        })
}

#[cfg(test)]
mod tests {
    use super::*;
    use sha2::{Digest, Sha256};

    #[test]
    fn fixed_art_environment_matches_original_cp3a_fragments_and_full_input_order() {
        assert!(consistent());
        assert_eq!(INPUTS.len(), 52);
        assert_eq!(INPUTS.iter().filter(|i| i.original_uid == 0).count(), 8);
        assert_eq!(INPUTS.iter().filter(|i| i.original_uid == 1000).count(), 44);
        assert_eq!(
            format!("{:x}", Sha256::digest(BOOTCLASSPATH.to_bytes())),
            "b348d2eb8cf1075c065d47ed9bcb347bcfb9a249b694c27b5ad61a210b6ca01c"
        );
        assert_eq!(
            format!("{:x}", Sha256::digest(DEX2OATBOOTCLASSPATH.to_bytes())),
            "9d5fc10a18c2139ed987ea9503cf55df161275d9d65e1ce40d5c9fd28d0eaf3e"
        );
        assert!(
            INPUTS
                .iter()
                .any(|i| i.path == "/apex/com.android.virt/javalib/framework-virtualization.jar")
        );
        let unique: std::collections::BTreeSet<_> = INPUTS.iter().map(|i| i.path).collect();
        assert_eq!(unique.len(), INPUTS.len());
    }
}
