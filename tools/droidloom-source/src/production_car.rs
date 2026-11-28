//! Exact original Android 17 dependencies for the strict vendor build.
//! Historical 652-project profiles remain independent recovery contracts.
use super::*;

/// Read a bounded lock; this profile validates its complete exact scope next.
pub use super::load_lock;

pub(super) const MAX_PROJECTS: usize = 661;
const CAR660_PROJECTS: usize = 660;
/// Exact selected JarJar project path.
pub const JARJAR_PATH: &str = "external/jarjar";
/// Exact selected JarJar project name.
pub const JARJAR_NAME: &str = "platform/external/jarjar";
/// Exact selected JarJar project commit.
pub const JARJAR_COMMIT: &str = "384ed55d6afe79ec6a143118c2cdd422e68c8e42";
/// Exact selected JarJar project purpose.
pub const JARJAR_PURPOSE: &str = "Same-release host JarJar provider required by normal libcore bootstrap relocation";
/// Complete source and resource scopes for the ordinary Java host target and its tests.
pub const JARJAR_CONES: &[&str] = &[
    "Android.bp",
    "COPYING",
    "LICENSE.txt",
    "NOTICE",
    "lib/apache-ant-1.9.4.jar",
    "lib/maven-plugin-api.jar",
    "manifest.txt",
    "res",
    "src/android",
    "src/main",
    "src/test",
];

/// Existing Clang checkout consumed by normal Soong Rust Bindgen.
pub const BINDGEN_CLANG_PROJECT: &str = "prebuilts/clang/host/linux-x86";
/// Exact ordinary Clang driver and real executable absent from the prior scope.
pub const BINDGEN_CLANG_TOOLS: &[&str] = &["clang-r584948/bin/clang", "clang-r584948/bin/clang-22", "clang-r584948/bin/clang-real"];

fn jarjar_project() -> PlannedProject {
    PlannedProject {
        path: JARJAR_PATH.into(),
        url: format!("{OFFICIAL_REMOTE}{JARJAR_NAME}"),
        commit: JARJAR_COMMIT.to_owned(),
        purpose: JARJAR_PURPOSE.to_owned(),
        sparse_paths: JARJAR_CONES.iter().map(PathBuf::from).collect(),
    }
}

pub(super) const MAX_SPARSE_PATHS: usize = 534;
const BASE_SHA: &str = "14fd227541b01876c7e34d7e6a1ffcb2a202d97d94c6a8f6e14be369e4b79505";
const BASE_LOCK: &[u8] =
    include_bytes!("../../../android/manifest/production-full-apex-tests-source-lock.json");

/// Original project, unchanged superproject Gitlink and complete required cone.
/// Ancestor Android.bp files are retained by the normal Git cone materializer.
pub const PROVIDERS: &[(&str, &str, &str)] = &[
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "apex_car_framework"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "car-lib-module"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "car-lib/generated-prop-config"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "service/proto"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "service/res"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "service/src"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "packages/ScriptExecutor/res"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "packages/ScriptExecutor/src"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "cpp/power/aidl"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "cpp/telemetry/cartelemetryd/aidl"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "cpp/telemetry/cartelemetryd/src"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "cpp/telemetry/cartelemetryd/tests"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "cpp/telemetry/proto"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "libs/car-watchdog-lib"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "libs/procfs-inspector/client"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "data/etc"),
    ("frameworks/hardware/interfaces", "9de6d032a248523c22d0bd86e224d1762355c41e", "automotive/telemetry/aidl/aidl_api"),
    ("frameworks/hardware/interfaces", "9de6d032a248523c22d0bd86e224d1762355c41e", "automotive/telemetry/aidl/android"),
    ("packages/providers/MediaProvider", "773ea53100eeb1e97c223826ca59054a58cd74ff", "apex/testing"),
    ("packages/providers/MediaProvider", "773ea53100eeb1e97c223826ca59054a58cd74ff", "apex/hiddenapi"),
    ("external/robolectric", "87aa52b08f0a6bc65f373e0f542a33d8cfb3cfc1", "processor/src/test/resources"),
    ("external/robolectric", "87aa52b08f0a6bc65f373e0f542a33d8cfb3cfc1", "resources/src/test/resources"),
    ("external/robolectric", "87aa52b08f0a6bc65f373e0f542a33d8cfb3cfc1", "robolectric/src/test/resources"),
    ("external/robolectric", "87aa52b08f0a6bc65f373e0f542a33d8cfb3cfc1", "shadows/httpclient/src/test/resources"),
    ("packages/modules/Uwb", "7c9e03046ff41cc28cf794cc2eda306fbc40279e", "ranging/tests/multidevices/CtsMultiDeviceGenericRangingAccuracyTests/AndroidTest.xml"),
    ("packages/modules/Uwb", "7c9e03046ff41cc28cf794cc2eda306fbc40279e", "ranging/tests/multidevices/RangingManagerTests/AndroidTest.xml"),
    ("packages/modules/Uwb", "7c9e03046ff41cc28cf794cc2eda306fbc40279e", "ranging/tests/multidevices/RangingManagerTests/AndroidTestV2.xml"),
    ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/motion/compose/tests/goldens"),
    ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/screenshot/src/androidTest/assets"),
    ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/screenshot/src/androidTest/manifest/AndroidManifest.xml"),
    ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/os/src/android/os/cts"),
    ("external/hyphenation-patterns", "487eaf7776fa0733d9835747032288ab0b549a70", "LibreOffice"),
    ("external/hyphenation-patterns", "487eaf7776fa0733d9835747032288ab0b549a70", "OpenTaal"),
    ("external/hyphenation-patterns", "487eaf7776fa0733d9835747032288ab0b549a70", "TeX"),
    ("external/hyphenation-patterns", "487eaf7776fa0733d9835747032288ab0b549a70", "laboratory50"),
    ("external/hyphenation-patterns", "487eaf7776fa0733d9835747032288ab0b549a70", "rekenaar"),
    ("external/hyphenation-patterns", "487eaf7776fa0733d9835747032288ab0b549a70", "tensojka"),
    ("frameworks/minikin", "915f1232cff2f38be1ed2273769c5ffd00928dff", "tools"),
    ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/os/src/android/os/connectivity/cts"),
    ("system/chre", "17b4a35a8c2b9f27e7f1b382b7d714aced928ce4", "chpp/common"),
    ("system/chre", "17b4a35a8c2b9f27e7f1b382b7d714aced928ce4", "chpp/services"),
    ("system/chre", "17b4a35a8c2b9f27e7f1b382b7d714aced928ce4", "chpp"),
];

/// Actual provider path and name in the same original AOSP superproject.
pub const SERVICES_PATH: &str = "frameworks/opt/car/services";
/// Official repository name of the original system-server provider.
pub const SERVICES_NAME: &str = "platform/frameworks/opt/car/services";
/// Exact original 28f0bbdd superproject Gitlink, not a moving release ref.
pub const SERVICES_COMMIT: &str = "2bb3349c1a84b9b15c5ef05ef9c2e3dc6dde427a";
/// Inclusion reason shared by the exact new lock and compiled validator.
pub const SERVICES_PURPOSE: &str = "Original superproject Car framework system-server module, builtin API and protobuf source required by com.android.car.framework";
/// Complete original Java, API and protobuf providers; no unrelated test tree.
pub const SERVICES_CONES: &[&str] = &[
    "builtInServices/api",
    "builtInServices/proto",
    "builtInServices/src",
    "updatableServices/src",
];

/// Official host bootclasspath provider in the original AOSP superproject.
pub const BOOTCLASSPATH_PATH: &str = "prebuilts/jdk/jdk8";
/// Canonical repository rather than a host-installed Java runtime.
pub const BOOTCLASSPATH_NAME: &str = "platform/prebuilts/jdk/jdk8";
/// Exact immutable superproject Gitlink.
pub const BOOTCLASSPATH_COMMIT: &str = "6cd518be7a7147ed5b1053edfbf66379bf5a45f9";
/// Inclusion reason shared by the lock and validator.
pub const BOOTCLASSPATH_PURPOSE: &str = "Original superproject Java 8 host bootclasspath inputs for dx and Apache Commons Lang";
/// Legacy platform classes used by the two host compilation modules.
pub const BOOTCLASSPATH_CONES: &[&str] = &[
    "linux-x86/jre/lib/jce.jar",
    "linux-x86/jre/lib/rt.jar",
];


const WEBRTC_ASSET_CONE: &str = "host/frontend/webrtc/html_client";

/// Exact additional official CTS provider cones for the WebRTC plan.
pub const CTS_RAVENWOOD_CONES: &[&str] = &["common/device-side/preconditions", "libs/display"];

/// Exact CTS biometric provider required by CtsSecurityTestCases.
pub const CTS_BIOMETRIC_CONE: &str = "tests/framework/base/biometrics";

/// Exact CTS kernel information provider.
pub const CTS_KERNELINFO_CONE: &str = "libs/kernelinfo";

/// Exact CTS utilities used by the released host test.
pub const CTS_MAINLINE_HOTSPOT_CONES: &[&str] = &["libraries/sts-common-util/apps/MainlineModuleDetector", "apps/hotspot"];
pub const CTS_DEVICEINFO_BACKUP_CONES: &[&str] = &["tools/cts-device-info", "hostsidetests/backup"];
pub const CTS_MANIFEST_GENERATOR_CONES: &[&str] = &["tools/manifest-generator"];

/// Exact released AOSP project, repository, Gitlink and input directory needed by the Kati closure.
pub const KATI_REQUIRED_CONES: &[(&str, &str, &str, &str)] = &[
    ("device/google/cuttlefish", "device/google/cuttlefish", "283645aacf6cdb56cc31a9362f54d412dbc132a1", "build"),
    ("device/google/cuttlefish", "device/google/cuttlefish", "283645aacf6cdb56cc31a9362f54d412dbc132a1", "shared/phone"),
    ("device/google/cuttlefish", "device/google/cuttlefish", "283645aacf6cdb56cc31a9362f54d412dbc132a1", "host/commands/mkenvimage_slim"),
    ("device/google/cuttlefish", "device/google/cuttlefish", "283645aacf6cdb56cc31a9362f54d412dbc132a1", "host/commands/console_forwarder"),
    ("device/google/cuttlefish", "device/google/cuttlefish", "283645aacf6cdb56cc31a9362f54d412dbc132a1", "host/commands/log_tee"),
    ("device/google/cuttlefish", "device/google/cuttlefish", "283645aacf6cdb56cc31a9362f54d412dbc132a1", "host/commands/logcat_receiver"),
    ("device/google/cuttlefish", "device/google/cuttlefish", "283645aacf6cdb56cc31a9362f54d412dbc132a1", "host/commands/tcp_connector"),
    ("system/extras", "platform/system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "vbmeta_tools"),
    ("system/extras", "platform/system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "simpleperf/simpleperf_app_runner"),
    ("system/memory/libmeminfo", "platform/system/memory/libmeminfo", "d59c960b1fb93377bf68664918031ea5fe709f89", "tools"),
    ("system/zygote", "platform/system/zygote", "c24023080df0bdb5988c1e0c641d494574a97c40", "memmark"),
    ("cts", "platform/cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/hardware"),
    ("cts", "platform/cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/input"),
    ("cts", "platform/cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/security"),
    ("cts", "platform/cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/view"),
    ("cts", "platform/cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/widget"),
    ("cts", "platform/cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/securitybulletin"),
    ("device/google/cuttlefish", "device/google/cuttlefish", "283645aacf6cdb56cc31a9362f54d412dbc132a1", WEBRTC_ASSET_CONE),
    ("cts", "platform/cts", CTS_PCC_COMMIT, CTS_RAVENWOOD_CONES[0]),
    ("cts", "platform/cts", CTS_PCC_COMMIT, CTS_RAVENWOOD_CONES[1]),
    ("cts", "platform/cts", CTS_PCC_COMMIT, CTS_BIOMETRIC_CONE),
    ("cts", "platform/cts", CTS_PCC_COMMIT, CTS_KERNELINFO_CONE),
    ("platform_testing", "platform/platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", CTS_MAINLINE_HOTSPOT_CONES[0]),
    ("cts", "platform/cts", CTS_PCC_COMMIT, CTS_MAINLINE_HOTSPOT_CONES[1]),
    ("cts", "platform/cts", CTS_PCC_COMMIT, CTS_DEVICEINFO_BACKUP_CONES[0]),
    ("cts", "platform/cts", CTS_PCC_COMMIT, CTS_DEVICEINFO_BACKUP_CONES[1]),
    ("cts", "platform/cts", CTS_PCC_COMMIT, CTS_MANIFEST_GENERATOR_CONES[0]),
];

/// Exact additional Gitlinks from the already selected Android 17 superproject.
pub const KATI_REQUIRED_PROJECTS: &[(&str, &str, &str, &str, &[&str])] = &[
    ("external/bc", "platform/external/bc", "683fc6fd48adab655b30f96ffdb931ba192047cb", "Official Android shell bc utility required by shell_and_utilities_system.", &[]),
    ("external/exfatprogs", "platform/external/exfatprogs", "02af625a7b521040c883aa91910a8278e22a21ff", "Official Android exFAT format and repair tools required by shell_and_utilities_system.", &[]),
    ("external/newfs_msdos", "platform/external/newfs_msdos", "c5ec86d6f3515fad6481e01c1798457ca0ec40d1", "Official Android FAT format utility required by shell_and_utilities_system.", &[]),
    ("external/one-true-awk", "platform/external/one-true-awk", "dd362b6ae0e8b3e7742edaf45dcee7fe4f25a422", "Official awk system and vendor binaries required by Android shell utilities.", &[]),
    ("external/tcpdump", "platform/external/tcpdump", "435ac48f51456ba3e57b4131fb7667b38e5ab142", "Official Android network diagnostic utility required by shell_and_utilities_system.", &[]),
    ("device/google/cuttlefish_prebuilts", "device/google/cuttlefish_prebuilts", "36f427b7c46682cfcdb2e61eee6893acbfb2a606", "Official Cuttlefish bootloader and kernel inspection inputs required by assemble_cvd.", &["bootloader", "scripts/extract-ikconfig"]),
];

fn invalid(message: &str) -> SourceError {
    SourceError::Invalid(vec![message.to_owned()])
}

fn original() -> Result<SparseSourceLock, SourceError> {
    if format!("{:x}", Sha256::digest(BASE_LOCK)) != BASE_SHA {
        return Err(invalid("original Production652 APEX-test lock bytes changed"));
    }
    serde_json::from_slice(BASE_LOCK)
        .map_err(|_| invalid("original Production652 APEX-test lock is malformed"))
}

// Only the reviewed exact CTS tails may extend the original 534 paths.
const CTS_PCC_CONE: &str = "tests/tests/os/src/android/os/cts";
const CTS_CONNECTIVITY_CONE: &str = "tests/tests/os/src/android/os/connectivity/cts";
const CTS_PCC_COMMIT: &str = "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd";

pub(super) fn permits_cts_pcc_sparse_extension(project: &SparseProject) -> bool {
    if project.path != Path::new("cts")
        || project.name != "platform/cts"
        || project.commit != CTS_PCC_COMMIT
    {
        return false;
    }
    let exact_tail = match project.sparse_paths.get(MAX_SPARSE_PATHS..) {
        Some([pcc]) => pcc == Path::new(CTS_PCC_CONE),
        Some([pcc, connectivity, rest @ ..]) => {
            pcc == Path::new(CTS_PCC_CONE)
                && connectivity == Path::new(CTS_CONNECTIVITY_CONE)
                && (rest.is_empty() || {
                    let kati = KATI_REQUIRED_CONES.iter().filter_map(|&(path, _, _, cone)| {
                        (path == "cts" && !CTS_RAVENWOOD_CONES.contains(&cone) && cone != CTS_BIOMETRIC_CONE && cone != CTS_KERNELINFO_CONE && cone != CTS_MAINLINE_HOTSPOT_CONES[1] && !CTS_DEVICEINFO_BACKUP_CONES.contains(&cone) && !CTS_MANIFEST_GENERATOR_CONES.contains(&cone)).then_some(Path::new(cone))
                    });
                    let paths = rest.iter().map(PathBuf::as_path);
                    let ravenwood = kati.clone().chain(CTS_RAVENWOOD_CONES.iter().map(|&cone| Path::new(cone)));
                    let biometric = ravenwood.clone().chain(std::iter::once(Path::new(CTS_BIOMETRIC_CONE)));
                    let kernelinfo = biometric.clone().chain(std::iter::once(Path::new(CTS_KERNELINFO_CONE)));
                    let mainline = kernelinfo.clone().chain(std::iter::once(Path::new(CTS_MAINLINE_HOTSPOT_CONES[1])));
                    paths.clone().eq(kati) || paths.clone().eq(ravenwood) || paths.clone().eq(biometric)
                        || paths.clone().eq(kernelinfo) || paths.clone().eq(mainline.clone())
                        || paths.clone().eq(mainline.clone().chain(CTS_DEVICEINFO_BACKUP_CONES.iter().map(|cone| Path::new(cone))))
                        || paths.eq(mainline.chain(CTS_DEVICEINFO_BACKUP_CONES.iter().map(|cone| Path::new(cone)))
                            .chain(CTS_MANIFEST_GENERATOR_CONES.iter().map(|cone| Path::new(cone))))
                })
        }
        _ => false,
    };
    if !exact_tail {
        return false;
    }
    original().ok().and_then(|lock| {
        lock.projects.into_iter().find(|old| old.path == Path::new("cts"))
    }).is_some_and(|old| {
        old.name == project.name
            && old.commit == project.commit
            && old.purpose == project.purpose
            && old.sparse_paths.as_slice() == &project.sparse_paths[..MAX_SPARSE_PATHS]
    })
}

/// Retain all original projects and add only the authenticated Car dependency closure.
///
/// # Errors
/// Rejects every changed old identity, missing source cone, unrelated extension,
/// altered policy and existing path, URL or duplicate validation failure.
pub fn build_plan(lock: &SparseSourceLock) -> Result<MaterializationPlan, SourceError> {
    let mut plan = super::build_plan_with_profile(lock, SourceProfile::Production654)?;
    let with_jarjar = plan.projects.len() == MAX_PROJECTS;
    if with_jarjar && plan.projects.pop().as_ref() != Some(&jarjar_project()) {
        return Err(invalid("only the exact same-release JarJar project may extend the complete Car660 plan"));
    }
    let bindgen_paths: Vec<PathBuf> = BINDGEN_CLANG_TOOLS.iter().map(PathBuf::from).collect();
    let mut with_bindgen_tools = false;
    if with_jarjar {
        let clang = plan.projects.iter_mut().find(|entry| entry.path == Path::new(BINDGEN_CLANG_PROJECT))
            .ok_or_else(|| invalid("complete Car661 plan must retain the original Clang project"))?;
        if clang.sparse_paths.ends_with(&bindgen_paths) {
            clang.sparse_paths.truncate(clang.sparse_paths.len() - bindgen_paths.len());
            with_bindgen_tools = true;
        }
    }
    let base = original()?;
    let mut expected = super::production_apex_tests::build_plan(&base)?;
    for &(path, commit, cone) in PROVIDERS {
        let project = expected.projects.iter_mut()
            .find(|project| project.path == Path::new(path))
            .ok_or_else(|| invalid("original provider dependency project is absent"))?;
        if project.commit != commit
            || project.url != format!("{OFFICIAL_REMOTE}platform/{path}")
            || project.sparse_paths.is_empty()
            || project.sparse_paths.iter().any(|item| item == Path::new(cone))
        {
            return Err(invalid("original provider dependency identity or scope changed"));
        }
        project.sparse_paths.push(cone.into());
    }
    expected.projects.push(PlannedProject {
        path: SERVICES_PATH.into(),
        url: format!("{OFFICIAL_REMOTE}{SERVICES_NAME}"),
        commit: SERVICES_COMMIT.to_owned(),
        purpose: SERVICES_PURPOSE.to_owned(),
        sparse_paths: SERVICES_CONES.iter().map(PathBuf::from).collect(),
    });
    expected.projects.push(PlannedProject {
        path: BOOTCLASSPATH_PATH.into(),
        url: format!("{OFFICIAL_REMOTE}{BOOTCLASSPATH_NAME}"),
        commit: BOOTCLASSPATH_COMMIT.to_owned(),
        purpose: BOOTCLASSPATH_PURPOSE.to_owned(),
        sparse_paths: BOOTCLASSPATH_CONES.iter().map(PathBuf::from).collect(),
    });
    if plan.projects.len() == CAR660_PROJECTS {
        for &(path, name, commit, cone) in KATI_REQUIRED_CONES {
            if cone == WEBRTC_ASSET_CONE || (path == "cts" && (CTS_RAVENWOOD_CONES.contains(&cone) || cone == CTS_BIOMETRIC_CONE || cone == CTS_KERNELINFO_CONE || cone == CTS_MAINLINE_HOTSPOT_CONES[1]
                    || CTS_DEVICEINFO_BACKUP_CONES.contains(&cone) || CTS_MANIFEST_GENERATOR_CONES.contains(&cone)))
                || (path == "platform_testing" && cone == CTS_MAINLINE_HOTSPOT_CONES[0])
            {
                continue;
            }
            let project = expected.projects.iter_mut().find(|row| row.path == Path::new(path))
                .ok_or_else(|| invalid("original Kati provider project is absent"))?;
            if project.commit != commit || project.url != format!("{OFFICIAL_REMOTE}{name}")
                || project.sparse_paths.is_empty()
                || project.sparse_paths.iter().any(|item| item == Path::new(cone))
            {
                return Err(invalid("original Kati provider identity or scope changed"));
            }
            project.sparse_paths.push(cone.into());
        }
        for &(path, name, commit, purpose, cones) in KATI_REQUIRED_PROJECTS {
            expected.projects.push(PlannedProject {
                path: path.into(), url: format!("{OFFICIAL_REMOTE}{name}"),
                commit: commit.to_owned(), purpose: purpose.to_owned(),
                sparse_paths: cones.iter().map(PathBuf::from).collect(),
            });
        }
    }
    if (with_jarjar || plan != expected) && plan.projects.len() == CAR660_PROJECTS {
        let provider = expected.projects.iter_mut().find(|row| row.path == Path::new("device/google/cuttlefish"))
            .ok_or_else(|| invalid("original Cuttlefish provider project is absent"))?;
        if provider.commit != "283645aacf6cdb56cc31a9362f54d412dbc132a1" || provider.sparse_paths.is_empty() {
            return Err(invalid("original Cuttlefish provider identity or scope changed"));
        }
        provider.sparse_paths.push(WEBRTC_ASSET_CONE.into());
    }
    if (with_jarjar || plan != expected) && plan.projects.len() == CAR660_PROJECTS {
        let cts = expected.projects.iter_mut().find(|row| row.path == Path::new("cts"))
            .ok_or_else(|| invalid("original CTS provider project is absent"))?;
        if cts.commit != CTS_PCC_COMMIT || cts.url != format!("{OFFICIAL_REMOTE}platform/cts")
            || cts.sparse_paths.len() != 542
        {
            return Err(invalid("original WebRTC CTS provider identity or scope changed"));
        }
        cts.sparse_paths.extend(CTS_RAVENWOOD_CONES.iter().map(|&cone| PathBuf::from(cone)));
    }
    if (with_jarjar || plan != expected) && plan.projects.len() == CAR660_PROJECTS {
        let cts = expected.projects.iter_mut().find(|row| row.path == Path::new("cts"))
            .ok_or_else(|| invalid("original CTS biometric provider project is absent"))?;
        if cts.commit != CTS_PCC_COMMIT || cts.url != format!("{OFFICIAL_REMOTE}platform/cts")
            || cts.sparse_paths.len() != 544
        {
            return Err(invalid("original biometric predecessor CTS identity or scope changed"));
        }
        cts.sparse_paths.push(CTS_BIOMETRIC_CONE.into());
    }
    if (with_jarjar || plan != expected) && plan.projects.len() == CAR660_PROJECTS {
        let cts = expected.projects.iter_mut().find(|row| row.path == Path::new("cts"))
            .ok_or_else(|| invalid("original CTS kernelinfo provider project is absent"))?;
        if cts.commit != CTS_PCC_COMMIT || cts.url != format!("{OFFICIAL_REMOTE}platform/cts")
            || cts.sparse_paths.len() != 545
        {
            return Err(invalid("original kernelinfo predecessor CTS identity or scope changed"));
        }
        cts.sparse_paths.push(CTS_KERNELINFO_CONE.into());
    }
    if (with_jarjar || plan != expected) && plan.projects.len() == CAR660_PROJECTS {
        let cts = expected.projects.iter_mut().find(|row| row.path == Path::new("cts"))
            .ok_or_else(|| invalid("original CTS provider project is absent"))?;
        if cts.commit != CTS_PCC_COMMIT || cts.url != format!("{OFFICIAL_REMOTE}platform/cts")
            || cts.sparse_paths.len() != 546
        {
            return Err(invalid("original Mainline and hotspot predecessor CTS identity or scope changed"));
        }
        cts.sparse_paths.push(CTS_MAINLINE_HOTSPOT_CONES[1].into());
        let platform = expected.projects.iter_mut().find(|row| row.path == Path::new("platform_testing"))
            .ok_or_else(|| invalid("original platform testing project is absent"))?;
        if platform.commit != "6abefd291d50dee240ed2b22572d273175f070da"
            || platform.url != format!("{OFFICIAL_REMOTE}platform/platform_testing")
            || platform.sparse_paths.len() != 163
        {
            return Err(invalid("original Mainline module detector platform testing identity or scope changed"));
        }
        platform.sparse_paths.push(CTS_MAINLINE_HOTSPOT_CONES[0].into());
    }
    if (with_jarjar || plan != expected) && plan.projects.len() == CAR660_PROJECTS {
        let cts = expected.projects.iter_mut().find(|row| row.path == Path::new("cts"))
            .ok_or_else(|| invalid("original CTS project is absent"))?;
        if cts.commit != CTS_PCC_COMMIT || cts.url != format!("{OFFICIAL_REMOTE}platform/cts")
            || cts.sparse_paths.len() != 547
        {
            return Err(invalid("original CTS release path scope changed"));
        }
        cts.sparse_paths.extend(CTS_DEVICEINFO_BACKUP_CONES.iter().map(std::path::PathBuf::from));
    }
    if (with_jarjar || plan != expected) && plan.projects.len() == CAR660_PROJECTS {
        let cts = expected.projects.iter_mut().find(|row| row.path == Path::new("cts"))
            .ok_or_else(|| invalid("original CTS manifest generator predecessor is absent"))?;
        if cts.commit != CTS_PCC_COMMIT || cts.url != format!("{OFFICIAL_REMOTE}platform/cts")
            || cts.sparse_paths.len() != 549
        {
            return Err(invalid("original manifest generator predecessor CTS identity or scope changed"));
        }
        cts.sparse_paths.extend(CTS_MANIFEST_GENERATOR_CONES.iter().map(std::path::PathBuf::from));
    }
    if plan != expected
        || lock.selected_at != base.selected_at
        || lock.status != base.status
        || lock.superproject.source_ref != base.superproject.source_ref
    {
        return Err(invalid(
            "production-full-car requires unchanged Production652 plus exactly the original Android 17 vendor build dependency closure",
        ));
    }
    if with_bindgen_tools {
        let clang = plan.projects.iter_mut().find(|entry| entry.path == Path::new(BINDGEN_CLANG_PROJECT))
            .ok_or_else(|| invalid("verified Car661 Clang project missing"))?;
        clang.sparse_paths.extend(bindgen_paths);
    }
    if with_jarjar {
        plan.projects.push(jarjar_project());
    }
    Ok(plan)
}

/// Materialize the named profile through the unchanged normal atomic writer.
///
/// # Errors
/// Preserves the original exact Git provenance, path validation and writer failures.
pub fn materialize(
    lock_path: &Path,
    lock: &SparseSourceLock,
    destination: &Path,
) -> Result<MaterializedManifest, SourceError> {
    build_plan(lock)?;
    super::materialize_with_profile(lock_path, lock, destination, SourceProfile::Production654)
}

/// Add only this fixed closure using the unchanged monotonic source reconciler.
///
/// # Errors
/// Rejects dirty trees, missing old inputs, changed Gitlinks and root-link aliases.
pub fn reconcile(
    lock_path: &Path,
    lock: &SparseSourceLock,
    destination: &Path,
) -> Result<MaterializedManifest, SourceError> {
    build_plan(lock)?;
    super::reconcile_with_profile(lock_path, lock, destination, SourceProfile::Production654)
}

/// Verify the exact new manifest and every real original materialized Git input.
///
/// # Errors
/// Rejects an unreconciled 652 manifest, partial source, wrong Git identity or dirt.
pub fn verify_materialized(
    lock_path: &Path,
    lock: &SparseSourceLock,
    destination: &Path,
) -> Result<MaterializedManifest, SourceError> {
    build_plan(lock)?;
    super::verify_materialized_with_profile(
        lock_path, lock, destination, SourceProfile::Production654,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn latest_lock_with_jarjar() -> SparseSourceLock {
        serde_json::from_slice(include_bytes!(
            "../../../android/manifest/production-full-car-source-lock.json"
        )).unwrap()
    }

    fn car661_before_bindgen_tools() -> SparseSourceLock {
        let mut lock = latest_lock_with_jarjar();
        let paths = &mut project(&mut lock, BINDGEN_CLANG_PROJECT).sparse_paths;
        for path in BINDGEN_CLANG_TOOLS.iter().rev() {
            assert_eq!(paths.pop().unwrap(), Path::new(path));
        }
        lock
    }

    // The existing history tests operate on the Car660 predecessor.
    fn latest_lock() -> SparseSourceLock {
        let mut lock = car661_before_bindgen_tools();
        assert_eq!(lock.projects.len(), MAX_PROJECTS);
        assert_eq!(lock.projects.pop().unwrap().path, Path::new(JARJAR_PATH));
        lock
    }

    #[test]
    fn car661_requires_exact_jarjar_on_the_complete_prior_plan() {
        let current = car661_before_bindgen_tools();
        let plan = build_plan(&current).unwrap();
        let legacy = build_plan(&latest_lock()).unwrap();
        assert_eq!(plan.projects.len(), MAX_PROJECTS);
        assert_eq!(&plan.projects[..CAR660_PROJECTS], legacy.projects.as_slice());
        assert_eq!(plan.projects.last(), Some(&jarjar_project()));
        super::super::validate_plan_extension(&legacy, &plan).unwrap();
        assert!(super::super::validate_plan_extension(&plan, &legacy).is_err());
        let mut wrong = current.clone();
        wrong.projects.last_mut().unwrap().commit = "0".repeat(40);
        assert!(build_plan(&wrong).is_err());
        let mut wrong = current.clone();
        wrong.projects.last_mut().unwrap().sparse_paths.pop();
        assert!(build_plan(&wrong).is_err());
        let mut wrong = current;
        project(&mut wrong, "cts").sparse_paths.pop();
        assert!(build_plan(&wrong).is_err());
    }

    #[test]
    fn car661_adds_only_the_exact_bindgen_clang_drivers() {
        let current = latest_lock_with_jarjar();
        let old = build_plan(&car661_before_bindgen_tools()).unwrap();
        let new = build_plan(&current).unwrap();
        let mut expected = old.clone();
        let clang = expected.projects.iter_mut().find(|entry| entry.path == Path::new(BINDGEN_CLANG_PROJECT)).unwrap();
        clang.sparse_paths.extend(BINDGEN_CLANG_TOOLS.iter().map(PathBuf::from));
        assert_eq!(new, expected);
        super::super::validate_plan_extension(&old, &new).unwrap();
        assert!(super::super::validate_plan_extension(&new, &old).is_err());
        let mut incomplete = current.clone();
        project(&mut incomplete, BINDGEN_CLANG_PROJECT).sparse_paths.pop();
        assert!(build_plan(&incomplete).is_err());
        let mut unrelated = current;
        project(&mut unrelated, BINDGEN_CLANG_PROJECT).sparse_paths.push(PathBuf::from("unrelated"));
        assert!(build_plan(&unrelated).is_err());
    }

    fn lock() -> SparseSourceLock {
        let mut previous = latest_lock();
        assert_eq!(previous.projects.len(), CAR660_PROJECTS);
        previous.projects.truncate(654);
        for &(path, _, _, cone) in KATI_REQUIRED_CONES.iter().rev() {
            let row = project(&mut previous, path);
            assert_eq!(row.sparse_paths.pop().as_deref(), Some(Path::new(cone)));
        }
        previous
    }

    fn project<'a>(lock: &'a mut SparseSourceLock, path: &str) -> &'a mut SparseProject {
        lock.projects.iter_mut().find(|project| project.path == Path::new(path)).unwrap()
    }

    #[test]
    fn car_profile_retains_original_652_and_adds_only_authenticated_provider_sources() {
        let base = original().unwrap();
        let prior = crate::production_apex_tests::build_plan(&base).unwrap();
        let current = lock();
        let plan = build_plan(&current).unwrap();
        assert_eq!(prior.projects.len(), 652);
        assert_eq!(plan.projects.len(), 654);
        let latest = latest_lock();
        let latest_plan = build_plan(&latest).unwrap();
        assert_eq!(latest_plan.projects.len(), CAR660_PROJECTS);
        let mut deviceinfo = latest.clone();
        assert_eq!(project(&mut deviceinfo, "cts").sparse_paths.pop().as_deref(), Some(Path::new(CTS_MANIFEST_GENERATOR_CONES[0])));
        let deviceinfo_plan = build_plan(&deviceinfo).unwrap();
        super::super::validate_plan_extension(&deviceinfo_plan, &latest_plan).unwrap();
        assert!(super::super::validate_plan_extension(&latest_plan, &deviceinfo_plan).is_err());
        let mut wrong_manifest_generator = latest.clone();
        *project(&mut wrong_manifest_generator, "cts").sparse_paths.last_mut().unwrap() = "tools/manifest-generator/unapproved".into();
        assert!(build_plan(&wrong_manifest_generator).is_err());
        let mut broad_manifest_generator = latest.clone();
        *project(&mut broad_manifest_generator, "cts").sparse_paths.last_mut().unwrap() = "tools".into();
        assert!(build_plan(&broad_manifest_generator).is_err());
        let mut mainline = deviceinfo;
        for expected in CTS_DEVICEINFO_BACKUP_CONES.iter().rev() {
            assert_eq!(project(&mut mainline, "cts").sparse_paths.pop().as_deref(), Some(Path::new(expected)));
        }
        let mainline_plan = build_plan(&mainline).unwrap();
        super::super::validate_plan_extension(&mainline_plan, &latest_plan).unwrap();
        assert!(super::super::validate_plan_extension(&latest_plan, &mainline_plan).is_err());
        for keep in CTS_DEVICEINFO_BACKUP_CONES {
            let mut partial_pair = mainline.clone();
            project(&mut partial_pair, "cts").sparse_paths.push(keep.into());
            assert!(build_plan(&partial_pair).is_err());
        }
        let mut ancestor = latest.clone();
        *project(&mut ancestor, "cts").sparse_paths.last_mut().unwrap() = "hostsidetests".into();
        assert!(build_plan(&ancestor).is_err());
        let mut kernelinfo = mainline;
        assert_eq!(project(&mut kernelinfo, "cts").sparse_paths.pop().as_deref(), Some(Path::new(CTS_MAINLINE_HOTSPOT_CONES[1])));
        assert_eq!(project(&mut kernelinfo, "platform_testing").sparse_paths.pop().as_deref(), Some(Path::new(CTS_MAINLINE_HOTSPOT_CONES[0])));
        let kernelinfo_plan = build_plan(&kernelinfo).unwrap();
        super::super::validate_plan_extension(&kernelinfo_plan, &latest_plan).unwrap();
        assert!(super::super::validate_plan_extension(&latest_plan, &kernelinfo_plan).is_err());
        let mut partial_utilities = latest.clone();
        assert_eq!(project(&mut partial_utilities, "cts").sparse_paths.pop().as_deref(),
                   Some(Path::new(CTS_MANIFEST_GENERATOR_CONES[0])));
        assert!(build_plan(&partial_utilities).is_ok());
        project(&mut partial_utilities, "cts").sparse_paths.pop();
        assert!(build_plan(&partial_utilities).is_err());
        let mut partial_platform = latest.clone();
        project(&mut partial_platform, "platform_testing").sparse_paths.pop();
        assert!(build_plan(&partial_platform).is_err());
        let mut relocated = latest.clone();
        *project(&mut relocated, "platform_testing").sparse_paths.last_mut().unwrap() = "libraries/sts-common-util/apps".into();
        assert!(build_plan(&relocated).is_err());
        let mut biometric = kernelinfo;
        assert_eq!(project(&mut biometric, "cts").sparse_paths.pop().as_deref(), Some(Path::new(CTS_KERNELINFO_CONE)));
        let biometric_plan = build_plan(&biometric).unwrap();
        super::super::validate_plan_extension(&biometric_plan, &latest_plan).unwrap();
        assert!(super::super::validate_plan_extension(&latest_plan, &biometric_plan).is_err());
        let mut wrong_kernelinfo = latest.clone();
        *project(&mut wrong_kernelinfo, "cts").sparse_paths.last_mut().unwrap() = "libs/kernelinfo/unapproved".into();
        assert!(build_plan(&wrong_kernelinfo).is_err());
        let mut ravenwood = biometric;
        assert_eq!(project(&mut ravenwood, "cts").sparse_paths.pop().as_deref(), Some(Path::new(CTS_BIOMETRIC_CONE)));
        let ravenwood_plan = build_plan(&ravenwood).unwrap();
        super::super::validate_plan_extension(&ravenwood_plan, &latest_plan).unwrap();
        assert!(super::super::validate_plan_extension(&latest_plan, &ravenwood_plan).is_err());
        let mut wrong_biometric = latest.clone();
        *project(&mut wrong_biometric, "cts").sparse_paths.last_mut().unwrap() = "tests/framework/base".into();
        assert!(build_plan(&wrong_biometric).is_err());
        let mut previous = ravenwood.clone();
        for &cone in CTS_RAVENWOOD_CONES.iter().rev() {
            let cts = project(&mut previous, "cts");
            assert_eq!(cts.sparse_paths.pop().as_deref(), Some(Path::new(cone)));
        }
        let web_plan = build_plan(&previous).unwrap();
        super::super::validate_plan_extension(&web_plan, &latest_plan).unwrap();
        assert!(super::super::validate_plan_extension(&latest_plan, &web_plan).is_err());
        let mut partial = ravenwood;
        project(&mut partial, "cts").sparse_paths.pop();
        assert!(build_plan(&partial).is_err());
        let mut changed_tail = latest.clone();
        project(&mut changed_tail, "cts").sparse_paths.swap(542, 543);
        assert!(build_plan(&changed_tail).is_err());
        let mut no_web = latest.clone();
        project(&mut no_web, "device/google/cuttlefish").sparse_paths.pop();
        assert!(build_plan(&no_web).is_err());
        let provider = project(&mut previous, "device/google/cuttlefish");
        assert_eq!(provider.sparse_paths.pop().as_deref(), Some(Path::new(WEBRTC_ASSET_CONE)));
        let previous_plan = build_plan(&previous).unwrap();
        super::super::validate_plan_extension(&previous_plan, &latest_plan).unwrap();
        assert!(super::super::validate_plan_extension(&latest_plan, &previous_plan).is_err());
        project(&mut previous, "device/google/cuttlefish").sparse_paths.push("host/frontend/unreviewed".into());
        assert!(build_plan(&previous).is_err());
        super::super::validate_plan_extension(&plan, &latest_plan).unwrap();
        assert!(super::super::validate_plan_extension(&latest_plan, &plan).is_err());
        let mut incomplete = latest.clone();
        incomplete.projects.pop();
        assert!(build_plan(&incomplete).is_err());
        let mut changed = latest;
        changed.projects.last_mut().unwrap().commit = "0".repeat(40);
        assert!(build_plan(&changed).is_err());
        for (old, new) in prior.projects.iter().zip(&plan.projects) {
            let mut expected = old.clone();
            for &(path, commit, cone) in PROVIDERS {
                if old.path == Path::new(path) {
                    assert_eq!(old.commit, commit);
                    expected.sparse_paths.push(cone.into());
                }
            }
            assert_eq!(&expected, new);
        }
        let service = &plan.projects[prior.projects.len()];
        assert_eq!(service.path, Path::new(SERVICES_PATH));
        assert_eq!(service.url, format!("{OFFICIAL_REMOTE}{SERVICES_NAME}"));
        assert_eq!(service.commit, SERVICES_COMMIT);
        assert_eq!(service.purpose, SERVICES_PURPOSE);
        assert_eq!(service.sparse_paths, SERVICES_CONES.iter().map(PathBuf::from).collect::<Vec<_>>());
        let bootclasspath = plan.projects.last().unwrap();
        assert_eq!(bootclasspath.path, Path::new(BOOTCLASSPATH_PATH));
        assert_eq!(bootclasspath.commit, BOOTCLASSPATH_COMMIT);
        assert_eq!(bootclasspath.sparse_paths, BOOTCLASSPATH_CONES.iter().map(PathBuf::from).collect::<Vec<_>>());
        assert_eq!(plan.links, prior.links);
        assert_eq!(plan.superproject_commit, prior.superproject_commit);
        assert!(!plan.unrestricted_repo_sync);
        super::super::validate_plan_extension(&prior, &plan).unwrap();
        assert!(super::super::validate_plan_extension(&plan, &prior).is_err());
        assert!(crate::production_apex_tests::build_plan(&current).is_err());
        assert!(crate::production_lint::build_plan(&current).is_err());
        assert!(crate::production_cmake::build_plan(&current).is_err());
        assert!(crate::production_full::build_plan(&current).is_err());
        assert!(crate::native_pair::build_plan(&current).is_err());
        assert!(crate::build_plan(&current).is_err());
        assert!(build_plan(&base).is_err());

        let mut exact = lock();
        assert!(permits_cts_pcc_sparse_extension(project(&mut exact, "cts")));
        let mut prior = lock();
        let row = project(&mut prior, "cts");
        assert_eq!(row.sparse_paths.pop().as_deref(), Some(Path::new(CTS_CONNECTIVITY_CONE)));
        assert!(permits_cts_pcc_sparse_extension(row));
        let mut old_profile = Vec::new();
        super::super::validate_projects(&exact, SourceProfile::Production652, &mut old_profile);
        assert!(old_profile.iter().any(|problem| problem.starts_with("project cts has more than ")));

        for change in 0..5 {
            let mut candidate = lock();
            let row = project(&mut candidate, "cts");
            match change {
                0 => row.sparse_paths[0] = "unreviewed-old-prefix".into(),
                1 => row.sparse_paths[MAX_SPARSE_PATHS] = "unreviewed-cts-extension".into(),
                2 => row.sparse_paths.push("unreviewed-extra-scope".into()),
                4 => row.sparse_paths[MAX_SPARSE_PATHS + 1] = "unreviewed-connectivity-extension".into(),
                3 => {
                    row.path = "external/unreviewed".into();
                    row.name = "platform/external/unreviewed".into();
                }
                _ => unreachable!(),
            }
            assert!(!permits_cts_pcc_sparse_extension(row));
            let diagnostic = format!(
                "project {} has more than {MAX_SPARSE_PATHS} sparse paths", row.path.display()
            );
            let mut problems = Vec::new();
            super::super::validate_projects(&candidate, SourceProfile::Production654, &mut problems);
            assert!(problems.contains(&diagnostic), "unapproved cap exception {change}");
        }
    }

    #[test]
    fn car_profile_rejects_each_missing_partial_duplicate_or_repinned_source_cone() {
        for &(path, _, cone) in PROVIDERS {
            for mutation in 0..7 {
                let mut bad = lock();
                let selected = project(&mut bad, path);
                let index = selected.sparse_paths.iter().position(|p| p == Path::new(cone)).unwrap();
                match mutation {
                    0 => { selected.sparse_paths.remove(index); }
                    1 => selected.sparse_paths[index] = format!("{cone}/Android.bp").into(),
                    2 => selected.sparse_paths.clear(),
                    3 => selected.commit = "0".repeat(40),
                    4 => selected.sparse_paths.push(cone.into()),
                    5 => selected.purpose = "unreviewed source".into(),
                    6 => selected.sparse_paths[index] = "../outside".into(),
                    _ => unreachable!(),
                }
                assert!(build_plan(&bad).is_err(), "{path}/{cone} mutation {mutation}");
            }
        }
    }

    #[test]
    fn car_profile_rejects_foreign_service_gitlink_and_incomplete_api_or_proto() {
        for mutation in 0..10 {
            let mut bad = lock();
            let service = project(&mut bad, SERVICES_PATH);
            match mutation {
                0 => service.commit = "0".repeat(40),
                1 => service.name = "platform/frameworks/opt/other".into(),
                2 => service.path = "frameworks/opt/other".into(),
                3 => service.purpose = "unreviewed service".into(),
                4 => service.sparse_paths.clear(),
                5 => service.sparse_paths = vec!["updatableServices/Android.bp".into()],
                6 => { service.sparse_paths.remove(0); }
                7 => { service.sparse_paths.remove(1); }
                8 => service.sparse_paths.push("unreviewed".into()),
                9 => service.sparse_paths.swap(0, 1),
                _ => unreachable!(),
            }
            assert!(build_plan(&bad).is_err(), "service mutation {mutation}");
        }
    }

    #[test]
    fn car_profile_rejects_unrelated_metadata_scope_and_source_policy_changes() {
        for mutation in 0..11 {
            let mut bad = lock();
            match mutation {
                0 => bad.projects[0].commit = "0".repeat(40),
                1 => bad.projects.swap(0, 1),
                2 => bad.projects[0].sparse_paths = vec!["unreviewed".into()],
                3 => bad.superproject.commit = "0".repeat(40),
                4 => bad.superproject.source_ref = "refs/heads/android-other".into(),
                5 => bad.selected_at = "unreviewed".into(),
                6 => bad.status = "build_proven".into(),
                7 => bad.policy.allow_unrestricted_repo_sync = true,
                8 => bad.links.pop().map(drop).unwrap(),
                9 => bad.projects.push(bad.projects[0].clone()),
                10 => { bad.projects.remove(0); }
                _ => unreachable!(),
            }
            assert!(build_plan(&bad).is_err(), "mutation {mutation}");
        }
    }

    #[test]
    fn car_operations_reject_old_or_partial_scope_before_source_io() {
        let directory = tempfile::tempdir().unwrap();
        let absent = directory.path().join("must-not-exist");
        let missing_lock = directory.path().join("missing-lock.json");
        let old = original().unwrap();
        let mut partial = lock();
        partial.projects.pop();
        for bad in [&old, &partial] {
            assert!(materialize(&missing_lock, bad, &absent).is_err());
            assert!(reconcile(&missing_lock, bad, &absent).is_err());
            assert!(verify_materialized(&missing_lock, bad, &absent).is_err());
        }
        assert_eq!(fs::read_dir(directory.path()).unwrap().count(), 0);
    }

    #[test]
    fn car_verification_never_rewrites_original_652_manifest() {
        let directory = tempfile::tempdir().unwrap();
        let source = directory.path().join("source");
        fs::create_dir(&source).unwrap();
        let prior = MaterializedManifest {
            schema_version: 1,
            source_lock_sha256: BASE_SHA.into(),
            plan: crate::production_apex_tests::build_plan(&original().unwrap()).unwrap(),
        };
        let bytes = serde_json::to_vec_pretty(&prior).unwrap();
        let manifest = source.join(".droidloom-source-manifest.json");
        fs::write(&manifest, &bytes).unwrap();
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let current = repo.join("android/manifest/production-full-car-source-lock.json");
        assert!(verify_materialized(&current, &lock(), &source).is_err());
        assert_eq!(fs::read(manifest).unwrap(), bytes);
        assert_eq!(fs::read_dir(source).unwrap().count(), 1);
    }
}


/// Resume verified disjoint source checkouts under the exact production lock.
pub fn materialize_resuming(
    lock_path: &Path, lock: &SparseSourceLock, destination: &Path,
    resume: Option<&Path>, progress: &Path,
) -> Result<MaterializedManifest, SourceError> {
    materialize_resuming_with_jobs(lock_path, lock, destination, resume, progress, 1)
}

/// Limit parallel official Git requests when restoring a verified source tree.
pub fn materialize_resuming_with_jobs(
    lock_path: &Path, lock: &SparseSourceLock, destination: &Path,
    resume: Option<&Path>, progress: &Path, jobs: usize,
) -> Result<MaterializedManifest, SourceError> {
    super::resume::materialize_for_profile(lock_path, lock, destination, resume, progress, true, jobs)
}
