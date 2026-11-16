use crate::util::*;
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    process::Command,
};
// Full runtime closure. Every update asks the build system for every target.
pub const TARGETS: &[&str] = &[
    "droidloom-native-bridge",
    "android.hardware.graphics.composer3-service.droidloom",
    "droidloom-task-launcher",
    "droidloom-input-bridge",
    "DroidloomIME",
    "DroidloomHome",
    "DroidloomSystemUI",
    "droidloom-lmkd-compat",
    "droidloom-classpath-wrapper",
    "netbpfload",
    "init_second_stage",
    "netd",
    "vold",
    "libbinder",
    "servicemanager",
    "libmeminfo",
    "libinputflinger",
    "surfaceflinger",
    "libdroidloom_surface_bridge",
    "libdroidloom_task_control",
    "libdroidloom_task_launcher",
    "libdroidloom_selinux_compat",
    "libdroidloom_composer_aidl",
    "libdroidloom_composer",
    "libdroidloom_minigbm",
    "libdroidloom_syncobj",
    "libdroidloom_denial_ipc",
    "libdroidloom_denial_protocol",
    "libdroidloom_transport",
    "android.hardware.graphics.allocator-service.minigbm",
    "mapper.minigbm",
    "libandroid_net_connectivity_com_android_net_module_util_jni",
    "libservice-connectivity",
    "libnetd_updatable",
    "services",
    "vendorimage",
];
// These APEX components are installed by Droidloom's compatibility projection.
// Request their compiled outputs, without asking AOSP to install them into system.
pub fn apex_output(name: &str) -> Option<&'static str> {
    match name {
        "netbpfload" => Some(
            "soong/.intermediates/packages/modules/Connectivity/bpf/loader/netbpfload/android_x86_64/netbpfload",
        ),
        "libservice-connectivity" => Some(
            "soong/.intermediates/packages/modules/Connectivity/service/libservice-connectivity/android_x86_64_shared/libservice-connectivity.so",
        ),
        "libnetd_updatable" => Some(
            "soong/.intermediates/packages/modules/Connectivity/bpf/netd/libnetd_updatable/android_x86_64_shared_cfi/libnetd_updatable.so",
        ),
        _ => None,
    }
}
const PATCHES: &[(&str, &str)] = &[
    (
        "frameworks/native",
        "android/surfaceflinger/0009-droidloom-cpu-placement.patch",
    ),
    (
        "external/minigbm",
        "android/aosp-patches/0010-minigbm-dma-heap-images.patch",
    ),
    (
        "packages/modules/Connectivity",
        "android/aosp-patches/0009-netd-bpf-pid-namespace.patch",
    ),
    (
        "packages/modules/Connectivity",
        "android/aosp-patches/0001-netbpfload-tolerate-shared-kernel-bpf-ids.patch",
    ),
    (
        "packages/modules/Connectivity",
        "android/aosp-patches/0003-connectivity-offline-rcu.patch",
    ),
    (
        "system/netd",
        "android/aosp-patches/0006-netd-cell-kernel-policy.patch",
    ),
    (
        "hardware/interfaces",
        "android/aosp-patches/0002-audio-default-only-service.patch",
    ),
    (
        "system/memory/libmeminfo",
        "android/aosp-patches/0004-libmeminfo-offline-gpu-accounting.patch",
    ),
    (
        "",
        "android/binder-compat/0001-droidloom-context-manager-without-kernel-sid.patch",
    ),
    (
        "",
        "android/binder-compat/0002-droidloom-servicemanager-pid-context-fallback.patch",
    ),
    (
        "",
        "android/binder-compat/0003-droidloom-cell-caller-context-fallback.patch",
    ),
    (
        "frameworks/native",
        "android/surfaceflinger/0001-droidloom-direct-denial-render-surface.patch",
    ),
    (
        "frameworks/native",
        "android/surfaceflinger/0002-droidloom-task-input-token.patch",
    ),
    (
        "frameworks/native",
        "android/surfaceflinger/0003-droidloom-headless-bootstrap.patch",
    ),
    (
        "frameworks/native",
        "android/surfaceflinger/0004-droidloom-opaque-content.patch",
    ),
    (
        "frameworks/native",
        "android/surfaceflinger/0005-droidloom-retained-task-composition.patch",
    ),
    (
        "frameworks/native",
        "android/surfaceflinger/0006-droidloom-late-task-registration.patch",
    ),
    (
        "frameworks/native",
        "android/surfaceflinger/0007-droidloom-wayland-layers.patch",
    ),
    (
        "frameworks/native",
        "android/surfaceflinger/0008-droidloom-release-fences.patch",
    ),
    (
        "frameworks/native",
        "android/surfaceflinger/0010-droidloom-task-backpressure-background.patch",
    ),
    (
        "frameworks/native",
        "android/inputflinger/0001-application-token-targeted-injection.patch",
    ),
    (
        "frameworks/native",
        "android/inputflinger/0002-droidloom-targeted-injection-binder.patch",
    ),
    (
        "",
        "android/init-compat/0001-droidloom-cell-namespace.patch",
    ),
    (
        "external/minigbm",
        "android/aosp-patches/0007-minigbm-amdgpu-platform.patch",
    ),
    (
        "system/vold",
        "android/aosp-patches/0008-vold-preserve-shared-storage-submounts.patch",
    ),
    (
        "frameworks/base",
        "android/framework/0001-droidloom-bottom-navigation-insets.patch",
    ),
    (
        "frameworks/base",
        "android/framework/0002-droidloom-routed-touch-configuration.patch",
    ),
    (
        "frameworks/base",
        "android/framework/0003-droidloom-launch-resolution.patch",
    ),
];
// Keep the upstream missing-dependency ErrorRule behavior usable when a
// closure build encounters an unrelated missing prebuilt source. This metadata
// guard is projected privately; strict product builds retain upstream sources.
const TARGET_CLOSURE_SOONG_PATCHES: &[(&str, &str)] = &[
    (
        "build/soong",
        "android/aosp-patches/0017-soong-prebuilt-missing-source-metadata.patch",
    ),
];

// Experimental PCM bridge patches are applied only by the explicit audio APEX
// entry point. Preserve the common product and NativeBridge patch inventory.
const AUDIO_APEX_PCM_PATCHES: &[(&str, &str)] = &[
    ("", "android/aosp-patches/0015-droidloom-pcm-output.patch"),
    (
        "",
        "android/aosp-patches/0016-droidloom-pcm-cancellation-lifecycle.patch",
    ),
];

const PROJECTION_JOURNAL_SCHEMA: u32 = 2;
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Original {
    path: PathBuf,
    bytes: Option<Vec<u8>>,
    modified: Option<std::time::SystemTime>,
    permissions_mode: Option<u32>,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProjectionJournal {
    schema_version: u32,
    originals: Vec<Original>,
}
fn validate_projection_originals(originals: &[Original], source: Option<&Path>) -> Result<()> {
    let mut paths = std::collections::BTreeSet::new();
    for o in originals {
        if !paths.insert(&o.path) || !o.path.is_absolute()
            || o.path.components().any(|c| matches!(c, std::path::Component::ParentDir))
            || source.is_some_and(|root| o.path == root || !o.path.starts_with(root)) {
            return fail("projection journal has a duplicate or unconfined original path");
        }
        match (&o.bytes, o.modified, o.permissions_mode) {
            (Some(_), Some(_), Some(mode)) if mode & !0o177777 == 0 && mode & 0o170000 == 0o100000 => (),
            (None, None, None) => (),
            _ => return fail("projection journal lacks complete original regular-file mode/mtime or absence"),
        }
    }
    Ok(())
}
fn decode_projection_journal(raw: &[u8], source: &Path) -> Result<Vec<Original>> {
    // Deserialize the struct first so duplicate JSON fields cannot be erased
    // by Value's object representation before the strict schema check.
    let journal: ProjectionJournal = serde_json::from_slice(raw)?;
    let value: serde_json::Value = serde_json::from_slice(raw)?;
    let object = value.as_object().ok_or("legacy projection journal has no complete permissions schema")?;
    if object.len() != 2 || !object.contains_key("schema_version") || !object.contains_key("originals") {
        return fail("projection journal must contain only the exact versioned schema fields");
    }
    let rows = object["originals"].as_array().ok_or("projection originals must be an array")?;
    for row in rows {
        let fields = row.as_object().ok_or("projection original must be an object")?;
        if fields.len() != 4 || ["path", "bytes", "modified", "permissions_mode"].iter().any(|key| !fields.contains_key(*key)) {
            return fail("projection original requires explicit bytes, mtime, permissions and path");
        }
    }
    if journal.schema_version != PROJECTION_JOURNAL_SCHEMA {
        return fail("unsupported projection journal schema; no complete restoration was performed");
    }
    validate_projection_originals(&journal.originals, Some(source))?;
    Ok(journal.originals)
}
pub(crate) struct Projection {
    journal: PathBuf,
    originals: Vec<Original>,
    applied_patches: BTreeMap<PathBuf, String>,
}
impl Projection {
    fn new(journal: PathBuf) -> Result<Self> {
        if journal.exists() {
            return fail(format!(
                "interrupted source projection: {}; run recover-source before building",
                journal.display()
            ));
        }
        Ok(Self {
            journal,
            originals: Vec::new(),
            applied_patches: BTreeMap::new(),
        })
    }
    fn save(&mut self, path: &Path) -> Result<()> {
        let path = path.to_owned();
        if self.originals.iter().any(|o| o.path == path) {
            return Ok(());
        }
        use std::os::unix::fs::PermissionsExt;
        let metadata = match fs::symlink_metadata(&path) {
            Ok(metadata) if metadata.file_type().is_file() => Some(metadata),
            Ok(_) => return fail("projection original must be a regular file or absent"),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => None,
            Err(e) => return Err(e.into()),
        };
        let original = Original {
            bytes: if metadata.is_some() { Some(fs::read(&path)?) } else { None },
            modified: metadata.as_ref().map(|m| m.modified()).transpose()?,
            permissions_mode: metadata.as_ref().map(|m| m.permissions().mode()),
            path,
        };
        self.originals.push(original);
        validate_projection_originals(&self.originals, None)?;
        durable_write(&self.journal, serde_json::to_vec(&serde_json::json!({
            "schema_version": PROJECTION_JOURNAL_SCHEMA,
            "originals": self.originals,
        }))?)?;
        Ok(())
    }
    pub(crate) fn put(&mut self, path: &Path, bytes: impl AsRef<[u8]>) -> Result<()> {
        self.save(path)?;
        write(path, bytes)
    }
    fn stabilize_all(&self) -> Result<()> {
        // Wait until all patches are applied: several patches can touch one file.
        for original in &self.originals {
            self.stabilize(&original.path)?;
        }
        Ok(())
    }
    fn stabilize(&self, path: &Path) -> Result<()> {
        if !path.is_file() {
            return Ok(());
        }
        let cache = self
            .journal
            .parent()
            .ok_or("journal lacks parent")?
            .join("projection-cache")
            .join(path.strip_prefix("/").unwrap_or(path));
        // Content comparison is for incremental builds, not artifact verification.
        // Reusing the cached timestamp prevents patch application from invalidating Ninja.
        write(&cache, fs::read(path)?)?;
        fs::File::open(path)?.set_modified(fs::metadata(cache)?.modified()?)?;
        Ok(())
    }
    fn patch(&mut self, source: &Path, cwd: &str, patch: &Path) -> Result<()> {
        let directory = source.join(cwd);
        run(Command::new("git")
            .env("GIT_CEILING_DIRECTORIES", source.parent().unwrap())
            .arg("-C")
            .arg(&directory)
            .args(["apply", "--check"])
            .arg(patch))?;
        let changed = output(
            Command::new("git")
                .env("GIT_CEILING_DIRECTORIES", source.parent().unwrap())
                .arg("-C")
                .arg(&directory)
                .args(["apply", "--numstat"])
                .arg(patch),
        )?;
        for line in changed.lines() {
            let path = line.split('\t').nth(2).ok_or("invalid patch numstat")?;
            if Path::new(path)
                .components()
                .any(|c| !matches!(c, std::path::Component::Normal(_)))
            {
                return fail("unsafe patch path");
            }
            self.save(&directory.join(path))?;
        }
        run(Command::new("git")
            .env("GIT_CEILING_DIRECTORIES", source.parent().unwrap())
            .arg("-C")
            .arg(&directory)
            .arg("apply")
            .arg(patch))?;
        self.applied_patches.insert(patch.to_owned(), hash(patch)?);
        Ok(())
    }
    fn effective_inventory(&self, repo: &Path, source: &Path) -> Result<serde_json::Value> {
        let mut files = BTreeMap::new();
        for original in &self.originals {
            let relative = original.path.strip_prefix(source)?;
            let digest = if original.path.exists() { Some(hash(&original.path)?) } else { None };
            files.insert(relative.to_string_lossy().into_owned(), digest);
        }
        let mut patches = BTreeMap::new();
        for (path, digest) in &self.applied_patches {
            patches.insert(path.strip_prefix(repo)?.to_string_lossy().into_owned(), digest);
        }
        Ok(serde_json::json!({"files": files, "patches": patches}))
    }
    fn restore(&mut self) -> Result<()> {
        use std::os::unix::fs::PermissionsExt;
        validate_projection_originals(&self.originals, None)?;
        for o in self.originals.iter().rev() {
            if let Some(bytes) = &o.bytes {
                match fs::symlink_metadata(&o.path) {
                    Ok(m) if m.file_type().is_file() => (),
                    Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
                    Ok(_) => return fail("projection restore refuses a non-regular destination"),
                    Err(e) => return Err(e.into()),
                }
                write(&o.path, bytes)?;
                let mode = o.permissions_mode.ok_or("missing original permissions")?;
                fs::set_permissions(&o.path, fs::Permissions::from_mode(mode))?;
                let modified = o.modified.ok_or("missing original modification time")?;
                fs::File::open(&o.path)?.set_modified(modified)?;
                if fs::symlink_metadata(&o.path)?.permissions().mode() != mode {
                    return fail("projection original permissions were not restored exactly");
                }
            } else {
                match fs::symlink_metadata(&o.path) {
                    Ok(m) if m.file_type().is_file() => fs::remove_file(&o.path)?,
                    Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
                    Ok(_) => return fail("projection absence restore refuses a non-regular destination"),
                    Err(e) => return Err(e.into()),
                }
            }
        }
        self.originals.clear();
        if self.journal.exists() {
            fs::remove_file(&self.journal)?;
        }
        Ok(())
    }
}
impl Drop for Projection {
    fn drop(&mut self) {
        if let Err(e) = self.restore() {
            eprintln!(
                "SOURCE RESTORE FAILED: {e}; retained {}",
                self.journal.display()
            );
        }
    }
}
pub fn recover(journal: &Path, source: &Path) -> Result<()> {
    let originals = decode_projection_journal(&fs::read(journal)?, source)?;
    Projection {
        journal: journal.to_owned(),
        originals,
        applied_patches: BTreeMap::new(),
    }
    .restore()
}
fn metadata_only(text: &str) -> Result<String> {
    let mut result = String::new();
    let mut taking = false;
    for line in text.lines() {
        if line.starts_with("package {") || line.starts_with("license {") {
            taking = true;
        }
        if taking {
            result.push_str(line);
            result.push('\n');
            if line == "}" {
                taking = false;
            }
        }
    }
    if result.is_empty() {
        return fail("missing Blueprint package metadata");
    }
    Ok(result)
}
fn original_sdkextensions_provider(source: &Path) -> Result<bool> {
    // The ordinary native pair adds this official snapshot to its source lock.
    // Other build scopes can omit it and must retain their SDK jar fallbacks.
    // A selected but incomplete or changed snapshot must fail before projection.
    let project = source.join("prebuilts/module_sdk/SdkExtensions");
    if !project.try_exists()? {
        return Ok(false);
    }
    let original = fs::read(project.join("current/Android.bp"))?;
    use sha2::{Digest, Sha256};
    if original.len() != 3247
        || format!("{:x}", Sha256::digest(&original))
            != "733a15d52927e70b1dcc4c6df212ce8e63e32cd733a794afee68a56dccff714a"
    {
        return fail("exact pinned SdkExtensions SDK provider changed");
    }
    Ok(true)
}

fn project_fallback_sdk_import(stem: &str, scope: &str, sdkextensions_provider: bool) -> bool {
    // Only these three scopes are supplied by the pinned java_sdk_library_import.
    // Keep any system-server fallback and every absent-snapshot build unchanged.
    if sdkextensions_provider
        && stem == "framework-sdkextensions"
        && matches!(scope, "public" | "system" | "module-lib")
    {
        return false;
    }
    // Preserve the original upstream java_sdk_library and
    // java_sdk_library_import providers. The prebuilt Connectivity Module
    // SDK supplies their stubs; sparse-build java_import fallbacks otherwise
    // duplicate prebuilt_*.stubs.module_lib variants.
    !matches!(
        stem,
        "framework-permission-s"
            | "framework-connectivity"
            | "framework-connectivity-b"
            | "framework-connectivity-t"
            | "framework-tethering"
    )
}

// Retain only exact upstream provider bodies from newly selected source
// packages, with their metadata and all original dependency edges. Existing
// SceneTest and StructuredPerf consumers and the strict whole graph remain.
fn typed_ingress_shared_blueprint(relative: &str, original: &str) -> Result<String> {
    use sha2::{Digest, Sha256};
    let (bytes, sha, modules): (usize, &str, &[(&str, &str)]) = match relative {
        "frameworks/native/services/serialservice/Android.bp" => (2441,
            "9f1f577d4c747e85e765d43c72ff8bfa25ec6d21c951e6d19e3d62b4ca583f30",
            &[("rust_defaults", "serialservice_defaults"),
              ("rust_library", "libserialservice"),
              ("rust_fuzz", "serialservice_fuzzer")]),
        "frameworks/base/packages/SystemUI/Android.bp" => (49535,
            "fa1aaf330d580d6cefb74dc0ef1b52fcebbdd9b6bced5497a3bd29f9fb3647a3",
            &[("soong_config_module_type", "systemui_optimized_java_defaults"),
              ("systemui_optimized_java_defaults", "SystemUI_optimized_defaults"),
              ("filegroup", "sysui_proguard_common_and_kotlin"),
              ("java_defaults", "SystemUI_compile_dagger")]),
        "frameworks/base/packages/SystemUI/tests/Android.bp" => (3392,
            "f1b2422c693a8f8c52034369ded585a3a93ac861f9dd6dd73f0801a77e6be4da",
            &[]),
        "hardware/interfaces/automotive/audiocontrol/aidl/default/Android.bp" => (1869,
            "9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6",
            &[]),
        "platform_testing/libraries/motion/Android.bp" => (2098,
            "a29bc25117f71e6acac6722f98950831a16a00f382c3ee0f9e991a36ecba5440",
            &[("filegroup", "motion_test_template"),
              ("java_defaults", "MotionTestDefaults"),
              ("filegroup", "PlatformMotionTesting-srcs"),
              ("android_library", "PlatformMotionTesting")]),
        "platform_testing/libraries/screenshot/Android.bp" => (2403,
            "53ba33c12075d68266d9c90620b2a0e04934e7d0b9eb73c1faf6c06cde689032",
            &[("android_library", "platform-screenshot-diff-core"),
              ("java_library", "platform-screenshot-diff-proto")]),
        "platform_testing/libraries/runner/Android.bp" => (2088,
            "e3b51cb5bc9ca15951a4da4b2ab711bfedd084eba95e2434060126accca8f5aa",
            &[("java_defaults", "platform-parametric-runner-lib_defaults"),
              ("android_library", "platform-parametric-runner-lib"),
              ("android_library", "platform-parametric-runner-lib-no-robo")]),
        "external/robolectric/Android.bp" => (12618,
            "5491a0f3918f8c5e89276ce13437b29bbd9b64aa2334e81717566e446bb6e1a4",
            &[("robolectric_build_props", "robolectric_build_props"),
              ("java_genrule", "libandroid_runtime_jar"),
              ("java_genrule", "robolectric_props_jar"),
              ("java_genrule", "robolectric_framework_res"),
              ("java_device_for_host", "robolectric_android-all-device-deps"),
              ("java_library", "robolectric-host-android_all"),
              ("java_library_host", "Robolectric_all"),
              ("java_host_for_device", "ClearcutJunitListenerAar"),
              ("java_host_for_device", "Robolectric_all-target"),
              ("java_device_for_host", "robolectric-host-androidx-test-core"),
              ("java_device_for_host", "robolectric-host-androidx-test-ext-junit"),
              ("java_device_for_host", "robolectric-host-androidx-test-monitor"),
              ("java_device_for_host", "robolectric-host-androidx-test-ext-truth"),
              ("java_device_for_host", "robolectric-host-androidx-test-runner"),
              ("java_device_for_host", "robolectric-host-androidx"),
              ("java_device_for_host", "robolectric-host-androidx_test_espresso"),
              ("java_device_for_host", "robolectric-host-android-support-multidex"),
              ("java_device_for_host", "robolectric-host-org_apache_http_legacy")]),
        "external/TestParameterInjector/Android.bp" => (2832,
            "3c39d19867e60e6f45ae39b3ee910b986de4cc158042519facaca18720d4ecf8",
            &[("java_library", "TestParameterInjector")]),
        "test/robolectric-extensions/Android.bp" => (1751,
            "cfbff8817cd8eb06cbd02bffa253ce0a2eb266e93fec6c8ab1894316e8ca6ab8",
            &[("java_library_host", "Robolectric-aosp-plugins")]),
        "packages/services/Car/car-lib/Android.bp" => (12547,
            "e88e92f8113c3c05f71999adfde6c50612d9d15d6454fbb0db9b98aba26fc6a2",
            &[("filegroup", "android.car-full-src"),
              ("java_defaults", "android.car-defaults"),
              ("java_library", "android.car")]),
        "packages/services/Car/car-builtin-lib/Android.bp" => (3748,
            "b7e38fdc5a873a7cd2607759d4eff2b560db218ea14c6a137da5bde70b4e9ceb",
            &[("java_defaults", "android.car.builtin-defaults"),
              ("java_sdk_library", "android.car.builtin")]),
        "packages/services/Car/car-lib/jni/large-parcelable/Android.bp" => (1590,
            "7f20480832afc1c33d54c846c2cab1a8cd6598278cd30f00b2a96b75932cbdb9",
            &[("cc_library", "liblargeparcelablejni")]),
        "external/icu/icu4j/Android.bp" => (5919,
            "e5a8137f19dbb133bdfa451c42493dbb481b1745a390817876b4636028a6014b",
            &[("java_defaults", "icu4j-defaults"),
              ("java_library", "icu4j"),
              ("java_import", "icu4j-icudata"),
              ("java_import", "icu4j-icutzdata"),
              ("java_library", "icu4j-icudata-jarjar"),
              ("java_library", "icu4j-icutzdata-jarjar"),
              ("java_library_host", "icu4j-host")]),
        "external/robolectric/pluginapi/Android.bp" => (1131,
            "b85704354df39ea533d97c8d6a2d51ef148889668d2c08d89fb59dd703e4aa15",
            &[("java_library_host", "Robolectric_pluginapi")]),
        "external/robolectric/resources/Android.bp" => (1395,
            "83e1f8f513e4c8dc9d3e9896e832cf6d5044f64a950dbb40b3d0ad8da9831bef",
            &[("java_library_host", "Robolectric_resources")]),
        "external/robolectric/robolectric/Android.bp" => (3390,
            "c9ae9050c080977591fa239ef37623826a5c7ffc125c78055059e375573feba4",
            &[("java_library_host", "Robolectric_robolectric"),
              ("genrule", "robolectric-version-upstream.properties")]),
        "external/robolectric/sandbox/Android.bp" => (1820,
            "0f35d9e221672dc164bd38e9c262fa5b38e892679f659e7e82b7dc5b50cd5e74",
            &[("java_library_host", "Robolectric_sandbox")]),
        "external/robolectric/shadowapi/Android.bp" => (1218,
            "36f67c55ad95f649e8a17a0770b8141d653c96c15f5213721b027154f9a21e69",
            &[("java_library_host", "Robolectric_shadowapi")]),
        "external/robolectric/utils/Android.bp" => (1491,
            "582130b938654da15b073bd6c8a616ad366358d125a0a53d14cc9d30e020b323",
            &[("java_library_host", "Robolectric_utils")]),
        "external/robolectric/shadows/httpclient/Android.bp" => (2446,
            "c1d4d324a0e0218c175e2f2e85806ccbeb398d797da57baf5221cf542f3d1268",
            &[("java_library_host", "Robolectric_shadows_httpclient")]),
        "external/robolectric/shadows/versioning/Android.bp" => (1647,
            "71262635df4c0b9aff77b4b8d5b3f80587d3a5d3d30a2941867c4e15dd398485",
            &[("java_library_host", "Robolectric_shadows_versioning")]),
        "external/robolectric/utils/reflector/Android.bp" => (1169,
            "82ed73680ad4eda143f6a38bb62198565e9b3a3b8211d9d3c5da6b5703ddae25",
            &[("java_library_host", "Robolectric_utils_reflector")]),
        "external/robolectric/processor/Android.bp" => (2723,
            "557bec83e3e684a6d9b6466827466043b0b1a1d61605aafaf35e581e974bea00",
            &[("java_library", "libRobolectric_processor"),
              ("java_plugin", "Robolectric_processor")]),
        "test/robolectric-extensions/clearcut-junit-listener/Android.bp" => (1132,
            "703b73b507250735b532c3c5f9eb4a0662606110e9a499632804136c0047c941",
            &[("java_library_host", "ClearcutJunitListener")]),
        "tools/asuite/Android.bp" => (1960,
            "04118667724a0433770f8d913207c510b5103a41d44600da62c337434ed2c5ae",
            &[("java_library_host", "asuite_proto_java_lite")]),
        "tools/asuite/atest/Android.bp" => (4006,
            "c38865f4312919d6452897db8e2e9341919ccb659c7a537ae20690a866e891e1",
            &[]),
        "packages/services/Car/cpp/vhal/client/Android.bp" => (1705,
            "d27df8040413d7575e066bded28bf04c72a62436dab9659b553eb1ae88819098",
            &[("cc_defaults", "vhalclient_defaults"),
              ("cc_library", "libvhalclient")]),
        "packages/services/Car/cpp/car_binder_lib/largeParcelable/Android.bp" => (1355,
            "66b33bf0a2234c0f301dfabed4e5ab7e69562d4bed111cedc6cd81ffa68ecfb8",
            &[("cc_defaults", "android-automotive-large-parcelable-defaults"),
              ("cc_library", "android-automotive-large-parcelable-lib")]),
        "packages/modules/NeuralNetworks/Android.bp" => (1726,
            "f408846ebf2fcbf1fc3075a312b2c388888bedd5bd7be96efb07301a9085ad08",
            &[("cc_defaults", "neuralnetworks_defaults")]),
        "packages/modules/NeuralNetworks/common/Android.bp" => (13060,
            "4153fd69cfeabb40bcefa51456a6b3747d835e96698150ed4e8bb950eba1f265",
            &[("cc_defaults", "neuralnetworks_cl_defaults")]),
        "packages/modules/NeuralNetworks/common/types/Android.bp" => (3279,
            "f3a14a68f3d0c918f44099b318fc22c8ff0067b4ddbc55b6c8e29177dff6487d",
            &[("cc_defaults", "neuralnetworks_utils_defaults"),
              ("cc_library_headers", "neuralnetworks_types_headers"),
              ("cc_defaults", "neuralnetworks_types_defaults"),
              ("cc_library_static", "neuralnetworks_types"),
              ("cc_library_static", "neuralnetworks_types_experimental"),
              ("cc_library_static", "neuralnetworks_types_cl")]),
        _ => return metadata_only(original),
    };
    if original.len() != bytes || format!("{:x}", Sha256::digest(original.as_bytes())) != sha {
        return fail(format!("typed ingress shared provider source changed: {relative}"));
    }
    let mut projected = metadata_only(original)?;
    for (kind, name) in modules {
        let marker = format!("{kind} {{\n    name: \"{name}\",");
        if original.matches(&marker).count() != 1 {
            return fail(format!("typed ingress shared provider declaration changed: {relative}: {name}"));
        }
        let start = original.find(&marker).ok_or("shared provider marker missing")?;
        let end = start + original[start..].find("\n}\n")
            .ok_or("shared provider stanza unterminated")? + 3;
        projected.push('\n');
        projected.push_str(&original[start..end]);
    }
    Ok(projected)
}

// The ordinary strict pair keeps the seven upstream test-package consumers.
// Their real providers must therefore remain visible in these exact shared BPs.
// Other build routes keep their existing projections and source contracts.
fn ordinary_pair_provider_blueprint(
    relative: &str, original: &str, ordinary_pair: bool,
) -> Result<Option<String>> {
    if !ordinary_pair {
        return Ok(None);
    }
    use sha2::{Digest, Sha256};
    let (bytes, sha) = match relative {
        "frameworks/base/libs/WindowManager/Shell/Android.bp" => (6272,
            "fc3a3c4de8e8ffbfc4832125b6a7b448a50fea1e0b5c6bad8ceb767b55679738"),
        "frameworks/base/packages/SystemUI/Android.bp" => (49535,
            "fa1aaf330d580d6cefb74dc0ef1b52fcebbdd9b6bced5497a3bd29f9fb3647a3"),
        "frameworks/base/packages/SystemUI/tests/Android.bp" => (3392,
            "f1b2422c693a8f8c52034369ded585a3a93ac861f9dd6dd73f0801a77e6be4da"),
        "packages/apps/Launcher3/Android.bp" => (18026,
            "5c214bfc624650323ae51f0d1f6685a37e596a7d66796f5063a8d73103a0dc20"),
        "packages/apps/Settings/Android.bp" => (6448,
            "a2f9de37f38ce72b44adfff18e8553640e7255f80de3f00b248ec7c2f537e115"),
        "packages/modules/NeuralNetworks/common/Android.bp" => (13060,
            "4153fd69cfeabb40bcefa51456a6b3747d835e96698150ed4e8bb950eba1f265"),
        "packages/services/Car/car-lib/Android.bp" => (12547,
            "e88e92f8113c3c05f71999adfde6c50612d9d15d6454fbb0db9b98aba26fc6a2"),
        "tools/asuite/Android.bp" => (1960,
            "04118667724a0433770f8d913207c510b5103a41d44600da62c337434ed2c5ae"),
        "tools/asuite/atest/Android.bp" => (4006,
            "c38865f4312919d6452897db8e2e9341919ccb659c7a537ae20690a866e891e1"),
        "packages/modules/ConfigInfrastructure/aconfigd/Android.bp" => (3011,
            "da512bd47cdd87afa503d88cddb0b2aa83d3bee62f6506fdcb072327947d898d"),
        _ => return Ok(None),
    };
    if original.len() != bytes || format!("{:x}", Sha256::digest(original.as_bytes())) != sha {
        return fail(format!("ordinary pair original provider source changed: {relative}"));
    }
    Ok(Some(original.to_owned()))
}

// These shared providers participate in the normal whole graph too: SystemUI
// pods use their defaults, and sepolicy validates every declared service fuzzer.
// Preserve the real upstream modules and all original dependency edges.
fn shared_root_blueprint(relative: &str, original: &str, typed_ingress: bool) -> Result<String> {
    if typed_ingress || matches!(relative,
        "frameworks/base/packages/SystemUI/Android.bp" |
        "frameworks/native/services/serialservice/Android.bp") {
        typed_ingress_shared_blueprint(relative, original)
    } else {
        metadata_only(original)
    }
}

const TYPED_INGRESS_HAL_BLUEPRINTS: &[&str] = &[
    "packages/services/Car/cpp/vhal/client/Android.bp",
    "packages/services/Car/cpp/car_binder_lib/largeParcelable/Android.bp",
    "packages/modules/NeuralNetworks/Android.bp",
    "packages/modules/NeuralNetworks/common/Android.bp",
    "packages/modules/NeuralNetworks/common/types/Android.bp",
];

fn project_typed_ingress_hal_blueprints(p: &mut Projection, source: &Path, ordinary_pair: bool) -> Result<()> {
    for relative in TYPED_INGRESS_HAL_BLUEPRINTS {
        let path = source.join(relative);
        let original = fs::read_to_string(&path)?;
        // Only new upstream providers are projected. The existing hardware
        // consumers remain byte-for-byte intact, including all defaults edges.
        let projected = match ordinary_pair_provider_blueprint(relative, &original, ordinary_pair)? {
            Some(original) => original,
            None => typed_ingress_shared_blueprint(relative, &original)?,
        };
        p.put(&path, projected)?;
    }
    Ok(())
}

const TYPED_INGRESS_SYSTEMUI_TESTS_BLUEPRINT: &str =
    "frameworks/base/packages/SystemUI/tests/Android.bp";

fn project_typed_ingress_systemui_tests(p: &mut Projection, source: &Path, ordinary_pair: bool) -> Result<()> {
    // The typed route retains three providers in SystemUI/Android.bp, not the
    // SystemUI application/test build. Match that boundary for these five
    // exact test modules only; other subdirectories are not traversed.
    // A complete upstream body is required before the original is journaled.
    let path = source.join(TYPED_INGRESS_SYSTEMUI_TESTS_BLUEPRINT);
    let original = fs::read_to_string(&path)?;
    let projected = match ordinary_pair_provider_blueprint(
        TYPED_INGRESS_SYSTEMUI_TESTS_BLUEPRINT, &original, ordinary_pair)? {
        Some(original) => original,
        None => typed_ingress_shared_blueprint(TYPED_INGRESS_SYSTEMUI_TESTS_BLUEPRINT, &original)?,
    };
    p.put(&path, projected)
}

const TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT: &str =
    "hardware/interfaces/automotive/audiocontrol/aidl/default/Android.bp";

fn project_typed_ingress_audiocontrol_example(p: &mut Projection, source: &Path) -> Result<()> {
    // This route requests framework-minus-apex and libandroid_runtime only.
    // The single observed vendor example binary is outside that fixed scope.
    // Preserve its package/license metadata and journal its entire preimage;
    // keep parent AIDL providers, sibling sources, and the source lock intact.
    // This fixed leaf does not assert a complete generated Soong variant graph.
    let path = source.join(TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT);
    let original = fs::read_to_string(&path)?;
    p.put(&path, typed_ingress_shared_blueprint(
        TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT, &original)?)
}

fn project_blueprints(p: &mut Projection, source: &Path, typed_ingress: bool,
    ordinary_pair: bool, dependency_mode: SoongDependencyMode) -> Result<()> {
    if ordinary_pair && dependency_mode != SoongDependencyMode::Strict {
        return fail("ordinary pair provider visibility requires strict dependencies");
    }
    let sdkextensions_provider = original_sdkextensions_provider(source)?;
    // In this exact Android17 sparse product, the original Connectivity Module
    // SDK is the source for framework-connectivity-b; no source implementation
    // of framework-connectivity-b is present in the fixed project tree.
    // Select the real prebuilt provider rather than synthesizing duplicate
    // Java stub aliases in prebuilts/sdk.
    let connectivity_sdk = source.join("prebuilts/module_sdk/Connectivity/current/Android.bp");
    let original_sdk = fs::read_to_string(&connectivity_sdk)?;
    let marker = r#"java_sdk_library_import {
    name: "framework-connectivity-b","#;
    if original_sdk.matches(marker).count() != 1 {
        return fail("exact pinned Connectivity SDK provider declaration changed");
    }
    let pinned_prebuilt = original_sdk.replacen(
        marker,
        r#"java_sdk_library_import {
    name: "framework-connectivity-b",
    prefer: true,"#,
        1,
    );
    p.put(&connectivity_sdk, pinned_prebuilt)?;
    for rel in [
        "frameworks/base/libs/WindowManager/Shell/Android.bp",
        "frameworks/base/packages/SystemUI/Android.bp",
        "packages/apps/Launcher3/Android.bp",
        "packages/apps/Settings/Android.bp",
        "frameworks/native/services/serialservice/Android.bp",
        "packages/modules/ConfigInfrastructure/aconfigd/Android.bp",
        // Keep the real Permission framework java_sdk_library visible to
        // system-server bootclasspath; only trim unrelated test fixtures.
    ] {
        let path = source.join(rel);
        let original = fs::read_to_string(&path)?;
        let projected = match ordinary_pair_provider_blueprint(rel, &original, ordinary_pair)? {
            Some(original) => original,
            None => shared_root_blueprint(rel, &original, typed_ingress)?,
        };
        p.put(&path, projected)?;
    }
    if typed_ingress {
        for relative in [
            "platform_testing/libraries/motion/Android.bp",
            "platform_testing/libraries/screenshot/Android.bp",
            "platform_testing/libraries/runner/Android.bp",
            "external/robolectric/Android.bp",
            "external/TestParameterInjector/Android.bp",
            "test/robolectric-extensions/Android.bp",
            "packages/services/Car/car-lib/Android.bp",
            "packages/services/Car/car-builtin-lib/Android.bp",
            "packages/services/Car/car-lib/jni/large-parcelable/Android.bp",
            "external/icu/icu4j/Android.bp",
            "external/robolectric/pluginapi/Android.bp",
            "external/robolectric/resources/Android.bp",
            "external/robolectric/robolectric/Android.bp",
            "external/robolectric/sandbox/Android.bp",
            "external/robolectric/shadowapi/Android.bp",
            "external/robolectric/utils/Android.bp",
            "external/robolectric/shadows/httpclient/Android.bp",
            "external/robolectric/shadows/versioning/Android.bp",
            "external/robolectric/utils/reflector/Android.bp",
            "external/robolectric/processor/Android.bp",
            "test/robolectric-extensions/clearcut-junit-listener/Android.bp",
            "tools/asuite/Android.bp",
            "tools/asuite/atest/Android.bp",
        ] {
            let path = source.join(relative);
            let original = fs::read_to_string(&path)?;
            let projected = match ordinary_pair_provider_blueprint(relative, &original, ordinary_pair)? {
                Some(original) => original,
                None => typed_ingress_shared_blueprint(relative, &original)?,
            };
            p.put(&path, projected)?;
        }
        project_typed_ingress_hal_blueprints(p, source, ordinary_pair)?;
        project_typed_ingress_systemui_tests(p, source, ordinary_pair)?;
        project_typed_ingress_audiocontrol_example(p, source)?;
    }
    let permission = source.join("packages/modules/Permission/framework-s/Android.bp");
    let mut text = fs::read_to_string(&permission)?;
    let mut names = Vec::new();
    for (scope, file) in [
        ("public", "current.txt"),
        ("system", "system-current.txt"),
        ("module-lib", "module-lib-current.txt"),
    ] {
        let name = format!("droidloom-permission-s-{scope}-api");
        names.push(format!("\"{name}\""));
        text += &format!(
            "java_api_contribution {{ name: \"{name}\", api_surface: \"{scope}\", api_file: \"api/{file}\", }}\n"
        );
    }
    text += &format!(
        "java_api_library {{ name: \"droidloom-permission-s-api-stubs\", api_surface: \"module-lib\", api_contributions: [{}], sdk_version: \"module_current\", libs: [\"stub-annotations\"], stubs_type: \"everything\", enable_validation: false, visibility: [\"//prebuilts/sdk:__pkg__\"], }}\n",
        names.join(",")
    );
    p.put(&permission, text)?;
    let sdk = source.join("prebuilts/sdk/Android.bp");
    let mut text = fs::read_to_string(&sdk)?;
    for (scope, suffix, version, combined) in [
        ("public", "", "current", "android_stubs_current"),
        (
            "system",
            ".system",
            "system_current",
            "android_system_stubs_current",
        ),
        (
            "module-lib",
            ".module_lib",
            "module_current",
            "android_module_lib_stubs_current",
        ),
        (
            "system-server",
            ".system_server",
            "system_server_current",
            "android_system_server_stubs_current",
        ),
    ] {
        let dir = source.join("prebuilts/sdk/current").join(scope);
        let mut jars: Vec<_> = fs::read_dir(&dir)?.collect::<std::io::Result<_>>()?;
        jars.sort_by_key(|e| e.file_name());
        for jar in jars {
            let path = jar.path();
            if path.extension().is_none_or(|e| e != "jar") {
                continue;
            }
            let stem = path.file_stem().unwrap().to_str().ok_or("bad SDK name")?;
            if !project_fallback_sdk_import(stem, scope, sdkextensions_provider) {
                continue;
            }
            let names = if stem == "android" {
                vec![combined.to_string(), format!("{combined}_exportable")]
            } else if ["android-non-updatable", "android.net.ipsec.ike"].contains(&stem)
                || stem.starts_with("framework-")
                || stem.starts_with("service-")
            {
                vec![
                    format!("{stem}.stubs{suffix}"),
                    format!("{stem}.stubs.exportable{suffix}"),
                ]
            } else {
                continue;
            };
            for name in names {
                if stem == "framework-permission-s" && scope == "module-lib" {
                    text += &format!(
                        "\njava_library {{ name: \"{name}\", static_libs: [\"droidloom-permission-s-api-stubs\"], sdk_version: \"{version}\", is_stubs_module: true, installable: false, visibility: [\"//visibility:public\"], }}\n"
                    );
                } else {
                    text += &format!(
                        "\njava_import {{ name: \"{name}\", jars: [\"current/{scope}/{stem}.jar\"], sdk_version: \"{version}\", prefer: true, is_stubs_module: true, installable: false, visibility: [\"//visibility:public\"], }}\n"
                    );
                }
            }
        }
    }
    p.put(&sdk, text)
}
fn bootstrap(source: &Path, out: &Path) -> Result<()> {
    let goroot = source.join("prebuilts/go/linux-x86");
    let generated = out.join("microfactory-main.go");
    let code = fs::read_to_string(source.join("build/blueprint/microfactory/microfactory.go"))?
        .replace("package microfactory", "package main")
        + "\nfunc main() { Main() }\n";
    write(&generated, code)?;
    for (binary, package) in [
        ("soong_ui", "android/soong/cmd/soong_ui"),
        ("mk2rbc", "android/soong/mk2rbc/mk2rbc"),
        ("rbcrun", "rbcrun/rbcrun"),
        (
            "release-config",
            "android/soong/cmd/release_config/release_config",
        ),
    ] {
        let mut command = Command::new(goroot.join("bin/go"));
        command
            .current_dir(source)
            .env("GOROOT", &goroot)
            .env("GOCACHE", out.join("go-cache"))
            .env("GOWORK", "off")
            .env("GO111MODULE", "off")
            .arg("run")
            .arg(&generated)
            .arg("-b")
            .arg(out.join("microfactory_Linux"));
        for (name, path) in [
            ("github.com/google/blueprint", "build/blueprint"),
            ("android/soong", "build/soong"),
            (
                "prebuilts/bazel/common/proto",
                "prebuilts/bazel/common/proto",
            ),
            ("rbcrun", "build/make/tools/rbcrun"),
            ("google.golang.org/protobuf", "external/golang-protobuf"),
            ("go.starlark.net", "external/starlark-go"),
            ("github.com/akrylysov/pogreb", "external/pogreb"),
        ] {
            command
                .arg("-pkg-path")
                .arg(format!("{name}={}", source.join(path).display()));
        }
        command
            .arg("-trimpath")
            .arg(source)
            .arg("-o")
            .arg(out.join(binary))
            .arg(package);
        run_build(&mut command)?;
    }
    Ok(())
}
pub fn build(
    repo: &Path,
    source: &Path,
    out: &Path,
    work: &Path,
    product: &str,
    jobs: usize,
) -> Result<()> {
    build_targets(repo, source, out, work, product, jobs, TARGETS)
}
fn enforce_strict_soong_dependencies(command: &mut Command) {
    command.env("ALLOW_MISSING_DEPENDENCIES", "false");
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum SoongDependencyMode {
    Strict,
    NativeBridgeTargetClosure,
    NativeEngineTargetClosure,
    AudioApexTargetClosure,
    MinigbmTargetClosure,
}

fn target_closure_soong_patches(mode: SoongDependencyMode) -> &'static [(&'static str, &'static str)] {
    match mode {
        SoongDependencyMode::Strict => &[],
        SoongDependencyMode::NativeBridgeTargetClosure | SoongDependencyMode::NativeEngineTargetClosure | SoongDependencyMode::AudioApexTargetClosure
            | SoongDependencyMode::MinigbmTargetClosure => {
            TARGET_CLOSURE_SOONG_PATCHES
        }
    }
}

fn audio_apex_pcm_patches(mode: SoongDependencyMode) -> &'static [(&'static str, &'static str)] {
    if mode == SoongDependencyMode::AudioApexTargetClosure {
        AUDIO_APEX_PCM_PATCHES
    } else {
        &[]
    }
}

// The ordinary pair retains its existing uncached writer and 5 GiB soft budget.
// Bound provider verification to the same CPU-derived limit as other graph work.
fn project_ordinary_pair_graph_resources(
    repo: &Path, source: &Path, projection: &mut Projection,
    ordinary_pair: bool, dependency_mode: SoongDependencyMode,
) -> Result<()> {
    if !ordinary_pair {
        return Ok(());
    }
    if dependency_mode != SoongDependencyMode::Strict {
        return fail("ordinary pair graph resources require strict dependencies");
    }
    let context = source.join("build/blueprint/context.go");
    let soong = source.join("build/soong/ui/build/soong.go");
    let bootstrap = source.join("build/blueprint/bootstrap/command.go");
    if hash(&context)? != "1559969a55db1b682401c01264dd8ba96fa224781c3af277f0996a5050f7c9fa"
        || hash(&soong)? != "4e6fb778c1aee7bfc9b3206940364edbf3502912fe692fa91b612ab389ed07d9"
        || hash(&bootstrap)? != "bb681356afa58932692866c41086e122509dc65d36edabc22c7bb154be5c8f38" {
        return fail("ordinary pair expected its exact existing writer and Go memory projections");
    }
    projection.patch(source, "build/blueprint", &repo.join(
        "android/apex-compat/0010-blueprint-native-pair-provider-bound.patch"))?;
    projection.patch(source, "build/blueprint", &repo.join(
        "android/apex-compat/0011-blueprint-ordinary-pair-go-budget.patch"))?;
    let prior = fs::read_to_string(&soong)?;
    let setting = "\tinvocationEnv[\"GOMEMLIMIT\"] = \"5GiB\"\n";
    if prior.matches(setting).count() != 1 {
        return fail("ordinary pair analyzer memory setting changed");
    }
    // env -i requires the GC observation setting on the actual analyzer.
    projection.put(&soong, prior.replacen(setting,
        &(setting.to_owned() + "\tinvocationEnv[\"GODEBUG\"] = \"gctrace=1\"\n\tinvocationEnv[\"GOMAXPROCS\"] = \"2\"\n\tinvocationEnv[\"GOGC\"] = \"50\"\n"), 1))?;
    if hash(&context)? != "38f6ae2fa339f04834241b20d4185bc091aa9e16cb894030927bdc58a8f67182"
        || hash(&soong)? != "0b855ddee1c4e62203968104f22e949b50bf0ba323f7d2f7335cf84c9f9ec2a8"
        || hash(&bootstrap)? != "705fa207568d27eaeeeb825646956934b63c6a4d5240c6d6caf57a0978e3837c" {
        return fail("ordinary pair graph resource projection differs");
    }
    Ok(())
}

fn configure_ordinary_pair_graph_observation(command: &mut Command, ordinary_pair: bool) {
    if ordinary_pair {
        // Console mode exposes GC trace lines before graph generation exits.
        command.env("SOONG_UNBUFFERED_OUTPUT", "1");
    }
}

fn validate_soong_dependency_mode(mode: SoongDependencyMode, targets: &[&str]) -> Result<()> {
    if mode == SoongDependencyMode::NativeEngineTargetClosure && !native_engine_only_build(targets) {
        return fail("native engine mode permits only libberberis_arm64 and its optional real ARM64 host tests");
    }
    if mode == SoongDependencyMode::NativeBridgeTargetClosure
        && !matches!(
            targets,
            ["droidloom-native-bridge"]
                | ["droidloom-native-bridge", "berberis_arm64_host_tests"]
        )
    {
        return fail("target-closure mode permits only droidloom-native-bridge and its optional ARM64 host tests");
    }
    if mode == SoongDependencyMode::AudioApexTargetClosure
        && targets != ["com.android.hardware.audio.droidloom"]
    {
        return fail("audio APEX target-closure mode permits only com.android.hardware.audio.droidloom");
    }
    if mode == SoongDependencyMode::MinigbmTargetClosure && targets != ["libminigbm_gralloc"] {
        return fail("minigbm target closure permits only the real libminigbm_gralloc library");
    }
    Ok(())
}

fn configure_soong_dependencies(
    command: &mut Command,
    mode: SoongDependencyMode,
    targets: &[&str],
) -> Result<()> {
    validate_soong_dependency_mode(mode, targets)?;
    match mode {
        SoongDependencyMode::Strict => enforce_strict_soong_dependencies(command),
        SoongDependencyMode::AudioApexTargetClosure => enforce_strict_soong_dependencies(command),
        SoongDependencyMode::MinigbmTargetClosure | SoongDependencyMode::NativeEngineTargetClosure => {
            // Native leaf validation keeps Ninja's real ErrorRule. Its private
            // Soong patch also propagates missing transitive defaults, closing
            // the upstream hole verified by the actual Android Go test suite.
            command.env("ALLOW_MISSING_DEPENDENCIES", "true");
            // This source-built native module is owned entirely by Soong.
            // Use upstream's native-module mode, without unrelated Make APK
            // installation metadata. Soong and Ninja dependency checks remain.
            command.arg("--soong-only");
            if mode == SoongDependencyMode::NativeEngineTargetClosure {
                // Engine provenance identifies the cp2a pinned compiler, not a
                // caller's unrelated toolchain override.
                command.env_remove("LLVM_PREBUILTS_BASE");
                command.env_remove("LLVM_PREBUILTS_VERSION");
            }
        }
        SoongDependencyMode::NativeBridgeTargetClosure => {
            // Upstream Soong defers tracked missing dependencies to failing
            // Ninja ErrorRule outputs. Never alter ErrorRule or its providers.
            command.env("ALLOW_MISSING_DEPENDENCIES", "true");
        }
    }
    Ok(())
}

/// Build only the selected NativeBridge closure; this does not qualify a product
/// or execute any runtime tests. Keep the default build_targets path strict.
pub fn build_native_bridge_target_closure(
    repo: &Path,
    source: &Path,
    out: &Path,
    work: &Path,
    product: &str,
    jobs: usize,
    tests: bool,
) -> Result<()> {
    let targets: &[&str] = if tests {
        &["droidloom-native-bridge", "berberis_arm64_host_tests"]
    } else {
        &["droidloom-native-bridge"]
    };
    build_targets_with_dependency_mode(
        repo,
        source,
        out,
        work,
        product,
        jobs,
        targets,
        SoongDependencyMode::NativeBridgeTargetClosure,
    )
}

pub fn build_native_engine_target_closure(
    repo: &Path, source: &Path, out: &Path, work: &Path, product: &str, jobs: usize, tests: bool,
) -> Result<()> {
    let targets: &[&str] = if tests {
        &["libberberis_arm64", "berberis_arm64_host_tests"]
    } else {
        &["libberberis_arm64"]
    };
    build_targets_with_dependency_mode(repo, source, out, work, product, jobs, targets,
        SoongDependencyMode::NativeEngineTargetClosure)
}

/// Build the genuine AIDL audio APEX and all of its declared dependencies.
/// Keep its name as the Soong target; no synthetic output or NativeBridge scope.
pub fn build_audio_apex_target_closure(
    repo: &Path,
    source: &Path,
    out: &Path,
    work: &Path,
    product: &str,
    jobs: usize,
) -> Result<()> {
    build_targets_with_dependency_mode(
        repo,
        source,
        out,
        work,
        product,
        jobs,
        &["com.android.hardware.audio.droidloom"],
        SoongDependencyMode::AudioApexTargetClosure,
    )
}

/// Build the actual allocator library with its declared native dependencies.
pub fn build_minigbm_target_closure(
    repo: &Path, source: &Path, out: &Path, work: &Path, product: &str, jobs: usize,
) -> Result<()> {
    build_targets_with_dependency_mode(repo, source, out, work, product, jobs,
        &["libminigbm_gralloc"], SoongDependencyMode::MinigbmTargetClosure)
}

const SOONG_EXCLUDED_TEST_FIXTURES: &[&str] = &[
        "frameworks/base/tools/aapt2/integration-tests",
        "frameworks/base/core/tests",
        "frameworks/base/media/tests",
        // Keep original ART test defaults visible; downstream ART modules
        // still depend on their real declarations.
        "packages/modules/Virtualization/guest/trusty/test_vm",
        "packages/modules/Virtualization/guest/trusty/test_vm_os",
        // Keep the real TetheringLib framework-tethering module visible.
        "frameworks/base/services/tests",
        "frameworks/base/services/robotests",
        // Unrelated host-only Binder SDK and Robolectric fixture modules;
    "frameworks/native/libs/binder/tests/binder_sdk",
    // Do not hide pinned prebuilt Maven/JAR providers. Error Prone's real
    // Soong Java plugin consumes original checkerframework and caffeine jars.
];

const ORDINARY_PAIR_REQUIRED_TEST_TREES: &[&str] = &[
    "frameworks/base/core/tests",
    "frameworks/base/media/tests",
    "frameworks/base/services/tests",
    "frameworks/base/tools/aapt2/integration-tests",
    "packages/modules/Virtualization/guest/trusty/test_vm",
];

fn project_test_fixture_exclusions(p: &mut Projection, source: &Path,
    ordinary_pair: bool, dependency_mode: SoongDependencyMode) -> Result<()> {
    if ordinary_pair {
        if dependency_mode != SoongDependencyMode::Strict {
            return fail("ordinary pair test provider discovery requires strict dependencies");
        }
        // Never remove or adopt an existing marker. A foreign/stale discovery
        // marker must be resolved before a normal build can claim visibility.
        for relative in ORDINARY_PAIR_REQUIRED_TEST_TREES {
            let marker = source.join(relative).join(".find-ignore");
            match fs::symlink_metadata(&marker) {
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {},
                Err(error) => return Err(error.into()),
                Ok(_) => return fail(format!("ordinary pair required test tree is hidden: {}", marker.display())),
            }
        }
    }
    for relative in SOONG_EXCLUDED_TEST_FIXTURES {
        if ordinary_pair && ORDINARY_PAIR_REQUIRED_TEST_TREES.contains(relative) {
            continue;
        }
        p.put(&source.join(relative).join(".find-ignore"), b"")?;
    }
    Ok(())
}

fn native_bridge_only_build(targets: &[&str]) -> bool {
    !targets.is_empty()
        && targets.iter().all(|target| {
            matches!(*target, "droidloom-native-bridge" | "berberis_arm64_host_tests")
        })
}

fn native_engine_only_build(targets: &[&str]) -> bool {
    matches!(targets, ["libberberis_arm64"] | ["libberberis_arm64", "berberis_arm64_host_tests"])
}

fn nativebridge_discovery_scope(targets: &[&str]) -> bool {
    native_bridge_only_build(targets) || native_engine_only_build(targets)
}

fn qualified_defaults_mode(mode: SoongDependencyMode) -> bool {
    matches!(mode, SoongDependencyMode::NativeEngineTargetClosure
        | SoongDependencyMode::MinigbmTargetClosure | SoongDependencyMode::AudioApexTargetClosure)
}

fn leaf_go_memory_mode(mode: SoongDependencyMode) -> bool {
    matches!(mode, SoongDependencyMode::NativeEngineTargetClosure | SoongDependencyMode::MinigbmTargetClosure)
}

fn project_native_leaf_discovery_scope(
    projection: &mut Projection, source: &Path, mode: SoongDependencyMode,
) -> Result<()> {
    if matches!(mode, SoongDependencyMode::NativeEngineTargetClosure
        | SoongDependencyMode::MinigbmTargetClosure) {
        // Neither the x86_64 translator/real host tests nor the allocator leaf
        // consumes automotive HALs. Preserve graphics/common/allocator/mapper
        // discovery and all strict, full-product and legacy Make-bridge paths.
        projection.put(&source.join("hardware/interfaces/automotive/.find-ignore"), b"")?;
    }
    Ok(())
}

fn selected_soong_targets(
    mode: SoongDependencyMode, targets: &[&str], out: &Path, product: &str,
) -> Result<Vec<PathBuf>> {
    validate_soong_dependency_mode(mode, targets)?;
    Ok(targets.iter().map(|name| {
        if mode == SoongDependencyMode::NativeEngineTargetClosure {
            match *name {
                "libberberis_arm64" => out.join("target/product").join(product)
                    .join("system/lib64/libberberis_arm64.so"),
                "berberis_arm64_host_tests" => PathBuf::from(
                    "berberis_arm64_host_tests-linux_glibc_x86_64-install"),
                _ => unreachable!("engine target list was validated"),
            }
        } else {
            apex_output(name).map_or_else(|| PathBuf::from(name), |path| out.join(path))
        }
    }).collect())
}

fn audio_apex_only_build(targets: &[&str]) -> bool {
    matches!(targets, ["com.android.hardware.audio.droidloom"])
}

fn minigbm_only_build(targets: &[&str]) -> bool {
    matches!(targets, ["libminigbm_gralloc"])
}

fn audio_serialservice_metadata_without_stale_team(text: &str) -> Result<String> {
    // The pinned serialservice declares an optional team that does not exist
    // in the pinned build/make registry. Its implementation is already outside
    // this audio target. Preserve package/license metadata and never invent an
    // upstream team identity. Full product source is unchanged.
    let line = "    default_team: \"trendy_team_webapps_cros_android\",\n";
    if text.matches(line).count() != 1 {
        return fail("audio serialservice metadata no longer matches its exact upstream pin");
    }
    Ok(text.replacen(line, "", 1))
}

const AUDIO_UPSTREAM_TRADEFED_SOURCE_SELECTION: &str = "ifeq (,$(wildcard tools/tradefederation/core))\n$(call soong_config_set_bool,tradefed,use_prebuilt,true)\nelse\n$(call soong_config_set_bool,tradefed,use_prebuilt,false)\nendif\n";

fn audio_select_original_prebuilt_tradefed(text: &str) -> Result<String> {
    if text.matches(AUDIO_UPSTREAM_TRADEFED_SOURCE_SELECTION).count() != 1 {
        return fail("exact pinned Tradefed source/prebuilt selection changed");
    }
    Ok(text.replacen(AUDIO_UPSTREAM_TRADEFED_SOURCE_SELECTION,
        "$(call soong_config_set_bool,tradefed,use_prebuilt,true)\n", 1))
}

fn audio_without_unselected_platform_test_aggregators(text: &str) -> Result<String> {
    // Root test packages enumerate unrelated full-product APK/perf tests.
    // The original Error Prone provider lives in libraries/ and remains real.
    let mut result = text.to_owned();
    for name in [
        "platform_tests", "continuous_native_tests", "continuous_native_metric_tests",
        "continuous_instrumentation_tests", "continuous_instrumentation_metric_tests",
        "cw_continuous_native_tests", "emulator_tests",
    ] {
        result = private_without_named_java_module(&result, "test_package", name)?;
    }
    Ok(result)
}

// The ordinary pair signs its APEX through the original local signapk ->
// apksig chain. Select that exact upstream signer scope; cloud KMS plugins
// and their aggregate test are not inputs to either complete requested target.
fn ordinary_pair_local_signer_blueprint(original: &str) -> Result<String> {
    use sha2::{Digest, Sha256};
    if original.len() != 5010 ||
       format!("{:x}", Sha256::digest(original.as_bytes())) !=
       "22f86ab11f2470d9e34861f7273dd92c0ba4e9b914710a71c22dc374ebbac2fb" {
        return fail("ordinary pair local signing provider source changed");
    }
    audio_without_unselected_cloud_kms(original)
}

fn audio_without_unselected_cloud_kms(text: &str) -> Result<String> {
    // The real apksig and local-key apksigner remain unchanged. The separate
    // AWS/GCP providers and KMS CLI are not dependencies of this APEX target.
    let mut result = text.to_owned();
    for name in ["apksig-kms-provider-aws", "apksig-kms-provider-gcp"] {
        result = private_without_named_java_module(&result, "java_library_host", name)?;
    }
    result = private_without_named_java_module(&result, "java_binary_host", "apksigner-kms")?;
    // Upstream's aggregate test imports both cloud SDKs as well. It is not an
    // input to the real signing tool or APEX payload.
    private_without_named_java_module(&result, "java_test_host", "apksig-test")
}

// Private proof build only. Native Bridge does not require Tethering/NetworkStack
// APK or APEX variants. No files are filtered in full product builds.
const PRIVATE_FUZZER_BINDINGS_TEST: &str =
    "fuzzer_bindings_test {\n    name: \"fuzzer_bindings_test\",\n    srcs: [\":plat_service_contexts\"],\n}\n";

fn private_without_fuzzer_bindings_test(blueprint: &str) -> Result<String> {
    if blueprint.matches(PRIVATE_FUZZER_BINDINGS_TEST).count() != 1 {
        return fail("private native-bridge fuzzer test filter expected one unchanged original module");
    }
    Ok(blueprint.replacen(PRIVATE_FUZZER_BINDINGS_TEST, "", 1))
}

// Private NativeBridge-only Soong graph closure; do not suppress these
// original Android modules when assembling a full product.
const PRIVATE_NATIVEBRIDGE_UNRELATED_DIRECTORIES: &[&str] = &[
    // Exactly six independent instrumentation/demo/sample Android TEST
    // source directories, never C++ ARM64 translator link inputs. Scope
    // these only in private standalone NativeBridge ELF verification.
    // Do not exclude parent Media, Connectivity, AVF, StatsD or product libs.
    "packages/modules/StatsD/framework/test/hostsidetests",
    "packages/modules/StatsD/framework/test/unittests",
    "packages/modules/Virtualization/android/MicrodroidDemoApp",
    "frameworks/av/media/tests/SampleVideoEncoder/app",
    "frameworks/av/media/tests/PlaybackPowerTest",
    "packages/modules/Connectivity/tests/connresources",
    // ART chroot-only fake StatsD APEX test package does not link the
    // standalone Teto ELF. Preserve production ART and StatsD.
    "art/test/testing/art_fake_com.android.os.statsd",
    // Generated Cronet Java/C++ source graph for Mainline networking, NOT
    // linked by the native Teto ARM64 translator nor its POSIX host suite.
    // Do not hide external/cronet root, APEX defaults or any modules in
    // complete Android product builds. Upstream stable source unchanged.
    "external/cronet/stable",
    // Conscrypt APEX packaging depends on a Java SDK bootclasspath fragment.
    // This is unrelated to the native arm64 translator, but critical to the
    // full product; exclude only when building the stand-alone NativeBridge.
    "external/conscrypt/apex",
    // NativeBridge-only ELF does not link the InputFlinger service.
    // InputFlinger IS part of the full DroidLoom product TARGETS and retains
    // its original code and every one of its dependencies in product builds.
    "frameworks/native/services/inputflinger",
    // Guest Linux VM orchestration is a Rust host CLI, not the ARM64 to x86_64
    // NativeBridge or its POSIX host tests. The production VM manager and all
    // Virtualization platform libraries remain in full AOSP product builds.
    "packages/modules/Virtualization/guest/linux_vm_manager",
    // Android input library native GTest folder is unrelated to the
    // ARM64 translator. Retain frameworks/native/libs/input production code.
    "frameworks/native/libs/input/tests",
    // Original APEX testdata examples, never selected by a C++ ARM64
    // NativeBridge ELF; keep the apexer production tool and full build.
    "system/apex/apexer/testdata",
    // Original StatsD APEX packaging and boot/systemserver classpath fragments
    // do not link the standalone x86_64 ARM64 translator. Preserve the
    // platform's native statsd daemon, StatsSocket and StatsPull libraries.
    "packages/modules/StatsD/apex",
    // Historical Android-23 CTS app and HIDL host test are unrelated to the
    // selected native bridge ELF and original POSIX host tests. Preserve
    // complete HIDL system and actual Connectivity product code.
    "packages/modules/Connectivity/tests/cts/net/appForApi23",
    "system/tools/hidl/test/system_api_test",
    // Original OpenJDK/libcore Java test suite and its TestNG / MockWebServer
    // fixtures are never inputs to the NativeBridge C++ ELF or host POSIX
    // GTests. Preserve core-oj and all original product modules.
    "libcore/ojluni/src/test",
    // Build telemetry and monitoring Python host tools, plus logging CTS
    // tests, are separate from the native ARM64 bridge ELF and POSIX host GTest.
    "build/make/tools/tool_event_logger",
    "build/make/tools/edit_monitor",
    "build/soong/tests",
    // Media APEX packaging/bootclasspath fragments are not part of the
    // selected native translator ELF and C++ POSIX host tests.
    "frameworks/av/apex",
    // Java-only modules-utils helpers and Media service SDK are not
    // consumed by the standalone NativeBridge ELF, not a product change.
    "frameworks/libs/modules-utils/java/com/android/modules/utils/pm",
    "frameworks/libs/modules-utils/java/com/android/modules/utils/build",
    "packages/modules/Media/apex/service",
    // Prebuilt API32 historical SELinux policy snapshot, not the current
    // product policy or an arm64 NativeBridge ELF target.
    "system/sepolicy/prebuilts/api/32.0",
    // Android Connectivity CTS multi-device Mobly and Scapy test suite
    // does not link or validate native ARM64-to-x86_64 translation.
    "packages/modules/Connectivity/tests/cts/multidevices",
    // These are Java-only Android app and text-classifier component source
    // trees, unrelated to the standalone x86_64/ARM64 native bridge binary.
    "external/libtextclassifier/java",
    "external/libtextclassifier/notification",
    "packages/modules/Virtualization/android/TerminalApp",
    // Android Media Extractor fuzz harnesses are independent test binaries,
    // not native ARM64-to-x86_64 translation runtime or its POSIX host test.
    // Keep original Media extractor product libraries for full product builds.
    "frameworks/av/media/module/extractors/fuzzers",
    // Sensor AIDL HAL VTS certification target is not a dependency of the
    // x86_64 ARM64 native translator. Retain original Sensor HAL AIDL,
    // generated NDK bindings and platform VTS on full product builds.
    "hardware/interfaces/sensors/aidl/vts",
    // AVF APEX packaging / bootclasspath fragments select the separate
    // Virtualization Java SDK. They are not part of the native translator ELF
    // or its POSIX host test. The full product's original source stays intact.
    "packages/modules/Virtualization/build/apex",
    // AVF framework's Java-only SDK/API graph is outside the C++ translator.
    "packages/modules/Virtualization/libs/framework-virtualization",
    // VCN framework API surface is Java-only; scope only for native-bridge ELF.
    // Android Settings UI component tree (Java/AndroidX), unrelated to the
    // independent C++ ARM64 native bridge and its native host test.
    // The original product graph and the source tree remain intact.
    "frameworks/base/packages/SettingsLib",
    // Java test-instrumentation and AndroidX coverage facilities, not the
    // C++ host runtime. Preserve the production modules-utils native libs
    // and libtextclassifier native sources.
    "frameworks/libs/modules-utils/java/com/android/modules/utils/testing",
    "external/libtextclassifier/coverage",
    // Original audio preprocessing benchmark is a performance measurement,
    // not the actual production preprocessing library or native translator.
    "frameworks/av/media/libeffects/preprocessing/benchmarks",
    // Original audio preprocessing test-only package. Its omitted WebRTC
    // static test dependency does not link to ARM64 translation. Keep all
    // preprocessing product/source modules for full Android and audio builds.
    "frameworks/av/media/libeffects/preprocessing/tests",
    // OTA payload diff/update_engine and the apex-ls standalone ext2
    // inspector are neither translators nor host POSIX regression inputs.
    // Keep APEX services, runtime and complete product build untouched.
    "system/apex/tools/apex-ls",
    // A phone flash/bootloader host tool and VINTF's separate unit-test
    // directory do not link the user-space ARM64 NativeBridge translator.
    // Preserve system/core itself, libvintf product libraries and boot tool
    // source outside this exact isolated ELF build.
    "system/core/fastboot",
    "system/libvintf/test",
    // The standalone C++ ELF is independent of host Java lints, older
    // prebuilt SELinux API snapshot masks, and Microdroid VM-only policy.
    // Only NativeBridge-only Soong source discovery is narrowed.
    "tools/lint_checks/utils",
    "system/sepolicy/prebuilts/api/202504",
    "system/sepolicy/microdroid",
    // Java AndroidX catalog is not consumed by a standalone NativeBridge C++
    // shared library or its host tests. This is a private-only find filter;
    // the original product's Java AARs are not changed or uninstalled.
    // Retain the real pinned annotation-jvm prebuilt that multiple platform
    // Java SDK providers consume. Exclude only unrelated AndroidX catalog
    // families from this private C++ proof, never from the full product.
    "prebuilts/sdk/current/androidx/m2repository/androidx/annotation/annotation-experimental",
    "prebuilts/sdk/current/androidx/m2repository/androidx/collection",
    "prebuilts/sdk/current/androidx/m2repository/androidx/core",
    "prebuilts/sdk/current/androidx/m2repository/androidx/leanback",
    "prebuilts/sdk/current/androidx/m2repository/androidx/transition",
    "prebuilts/sdk/current/androidx/m2repository/androidx/webkit",
    "packages/modules/Virtualization/libs/libcompos_common/external/test",
    // M854: CTS/VTS Binder NDK tests create Java SDK variants, requiring SDK34
    // prebuilt jars unrelated to an x86_64 NativeBridge ELF proof. Keep the
    // production libbinder and libbinder_ndk Blueprints visible and unchanged.
    "frameworks/native/libs/binder/ndk/tests",
    // M853: standalone Stats Express catalog/codegen host utilities are
    // unrelated to the pinned ARM64 ELF translator (and do not provide its
    // StatsLog header). Full product discovery is unchanged.
    "frameworks/proto_logging/stats/express",
    // M853: secure AVF service-VM and its fake-chain library are firmware
    // modules, not Linux x86_64 NativeBridge/host regression targets.
    "packages/modules/Virtualization/guest/service_vm",
    "packages/modules/Virtualization/libs/libservice_vm_fake_chain",
    // Only the private NativeBridge host-ELF target: not packaged product code.
    // These Blueprint directories are independent host/CTS test aggregations.
    "system/fs/fs_mgr/tests",
    "bionic/tests",
    // Android Tradefed heap measurement apps/host metrics are not Teto
    // C++ NativeBridge host tests; full Libcore product stays unchanged.
    "libcore/metrictests",
    // AndroidX Libcore BenchmarkTest/BenchmarkTestsLib require unrelated
    // benchmark JUnit4 host/device fixtures; exclude only in C++ NativeBridge.
    "libcore/benchmarks",
    // Private x86 NativeBridge-only build: firmware and its sample DICE inputs
    // use the Rust open_dice crate intentionally excluded from this C++ target.
    // Keep the original modules for full Android/AVF product builds.
    "packages/modules/Virtualization/guest/pvmfw",
    "packages/modules/Virtualization/libs/dice/sample_inputs",
    // CTS host-side Connectivity Java tests are not NativeBridge runtime.
    "packages/modules/Connectivity/tests/cts/hostside",
    // Metalava Java main app is not needed to compile Teto C++ ELF.
    // Keep tools/metalava root stub-annotations provider.
    "tools/metalava/metalava",
    // Scope only Metalava model host Java tools; preserve stub-annotations
    // in tools/metalava/Android.bp, required by core.current.stubs.from-text.
    // API check CLI is unrelated to NativeBridge. Full product unchanged.
    "tools/metalava/metalava-model-turbine",
    "tools/metalava/metalava-model-psi",
    "build/make/tools/check-flagged-apis",
    // Entire AVF test source tree is outside the translation-only ELF.
    // Keep real Virtualization libs and full Android product unfiltered.
    "packages/modules/Virtualization/tests",
    // AVF and pvmfw host-side test tools, not C++ NativeBridge runtime inputs.
    "packages/modules/Virtualization/tests/pvmfw/tools",
    "packages/modules/Virtualization/tests/benchmark_hostside",
    // NativeBridge-only C++ translation does not invoke the Kotlin incremental
    // Java CLI or Metalava model-source host tooling. Full product retains both.
    "build/soong/cmd/kotlinc_incremental",
    "tools/metalava/metalava-model-source",
    "frameworks/native/services/serialservice",
    "hardware/interfaces/radio/aidl/minradio/libminradio/include/libminradio/overlays/ConnectivityOverlay",
    "frameworks/base/api/coverage/tools",
    "art/libnativeloader/test",
    "libcore/luni/src/test",
    "libnativehelper/tests",
    "system/core/init/test_reboot_fs_integrity",
    "packages/modules/Connectivity/tests/deflake",
    // Preserve the original xsdc Soong plugin and its code-generation tool.
    // The pinned commons-cli-1.2 prebuilt now supplies its Java dependency.
    "art/test/update-rollback",
    // MTE upgrade CTS-only fixture; unrelated to ARM64 NativeBridge proof.
    "system/core/init/test_upgrade_mte",
    // Synthetic HIDL vendor fixtures depend on unselected test-only HALs.
    "system/tools/hidl/test/vendor",
    // Host analysis utility is not consumed by the ARM64 NativeBridge target.
    "libcore/tools/openjdk-analyzer",
    // Standalone MTE permissive CTS regression, not a NativeBridge build target.
    "system/core/debuggerd/test_permissive_mte",
    // Test-only Microdroid host preparer requires Tradefed, not NativeBridge.
    "packages/modules/Virtualization/tests/libs/preparer",
    // Legacy Java API checker is outside the ARM64 NativeBridge-only target.
    "build/make/tools/apicheck",
    // CTS JSON fuzz harness requires Jazzer, not NativeBridge production.
    "cts/libs/json/fuzzers",
    // Binder SDK shell/CMake host test is unrelated to ARM64 NativeBridge.
    "frameworks/native/libs/binder/tests/binder_sdk",
    // ART odsign end-to-end Tradefed host testing is not NativeBridge.
    "art/test/odsign",
    // The CTS JSON inventory generator is a Java host-only helper;
    // it is not a translation runtime or a NativeBridge host test.
    "libcore/tools/non-cts-json-generator",
    // Soong API (SNAPI) gRPC/DB server is an independent Java host utility.
    // Its original Blueprint remains visible for full product builds.
    "build/make/tools/soong_api",
    // Backported-fix Java application/tool suite belongs to product
    // assembly, not the isolated NativeBridge ARM64 proof.
    "build/make/backported_fixes",
    // Rust rdroidtest is an independent platform-testing unit-test harness.
    // It consumes a liblogger Rust test dependency not provided by this
    // sparse native-bridge source set. This directory is scoped out only
    // for the Teto NativeBridge/C++ host regression targets; the original
    // pinned Blueprint remains intact in full Android product builds.
    "platform_testing/libraries/rdroidtest",
    // Original StatsD localdrive/testdrive Java CLI and CTS host suite are
    // independent test/tool-only modules, not the StatsSocket/StatsPull product.
    "packages/modules/StatsD/statsd/tools/localtools",
    "packages/modules/StatsD/tests",
    // These two independent Rust VTS suites consume rdroidtest.defaults.
    // Scope their source discovery out only for Teto NativeBridge/C++ GTest,
    // not full Android product builds, real Secretkeeper service or AVF libs.
    "packages/modules/Virtualization/tests/vts",
    "hardware/interfaces/security/secretkeeper/aidl/vts",
    // Unrelated Rust FFI crates and virtualization/stats services are
    // outside the isolated x86_64 NativeBridge translator proof.
    // The grpcio Rust consumer requires grpcio-sys's native FFI, which is
    // deliberately not included in this NativeBridge/C++ host-test closure.
    // Keep both original Rust packages for complete Android product builds.
    "external/rust/android-crates-io/crates/grpcio",
    "external/rust/android-crates-io/crates/grpcio-sys",
    "external/rust/android-crates-io/crates/libusb1-sys",
    "external/rust/android-crates-io/crates/tikv-jemalloc-sys",
    // M852: Do not hide original Rust StatsPull/Bindgen; the pinned DnsResolver
    // Rust StatsLog consumer requires libstatspull_bindgen in this graph.
    "packages/modules/Virtualization/libs/dice/open_dice",
    // AWS-LC's Rust TLS crate is unrelated to the Teto x86_64 ELF.
    "external/rust/android-crates-io/crates/aws-lc-rs",
    // Closed Rust TLS/HTTP chain depends on deliberately omitted AWS-LC C FFI.
    // None is a NativeBridge ARM64 translator or its host regression module.
    "external/rust/android-crates-io/crates/rustls-webpki",
    "external/rust/android-crates-io/crates/rustls",
    "external/rust/android-crates-io/crates/tokio-rustls",
    "external/rust/android-crates-io/crates/hyper-rustls",
    "external/rust/android-crates-io/crates/reqwest",
    "external/rust/android-crates-io/crates/dc_figma_import",
    // USB bindings and consumers similarly belong to unrelated host/device tools.
    "external/rust/android-crates-io/crates/rusb",
    "external/rust/android-crates-io/crates/ippusb",
    // Rust DRM crate's missing drm-sys is not the platform C/C++ libdrm.
    // The stand-alone Rust GBM crate requires libdrm_rust; the NativeBridge
    // target uses Mesa/GBM C libraries instead. Full product untouched.
    "external/rust/android-crates-io/crates/gbm",
    "external/rust/android-crates-io/crates/drm-ffi",
    "external/rust/android-crates-io/crates/drm",
    // Host-only TikV allocator belongs to unrelated Rust host tools.
    "external/rust/android-crates-io/crates/tikv-jemallocator",
    // Truth's Java assertions serve host/CTS unit tests, not Teto C++ GTest.
    // Keep the complete upstream Blueprint for full Android product builds.
    "external/truth",
    // USB-gadget VTS functional host test requires Tradefed/JUnit test runtime,
    // not the USB AIDL service or Teto native-bridge C++ host regression.
    "hardware/interfaces/usb/gadget/aidl/vts/functional",
    // Stats HAL VTS host Tradefed/CTS Java suite, not the Stats AIDL service.
    "frameworks/hardware/interfaces/stats/aidl/vts",
];

fn private_nativebridge_unrelated_paths(targets: &[&str]) -> &'static [&'static str] {
    if nativebridge_discovery_scope(targets) {
        PRIVATE_NATIVEBRIDGE_UNRELATED_DIRECTORIES
    } else {
        &[]
    }
}

const PRIVATE_CONSCRYPT_FUZZER_MODULE: &str = r#"java_library {
    name: "conscrypt-fuzzer",
    visibility: [
        "//art/tools/fuzzer",
    ],
    static_libs: ["conscrypt-for-host"],
    stem: "conscrypt",
    compile_dex: true,
    sdk_version: "none",
    system_modules: "none",
}
"#;


// Experimental NativeBridge-only graph scope. These six Java host/test
// modules are not required to compile Teto. Original Android product builds
// retain every declaration; missing Soong dependencies remain fail-closed.
const PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES: &[(&str, &str, &[&str])] = &[
    // Independent Java stats generators, IDE inspection, printing enums,
    // identity demo utility and Aconfigd Java convenience library are not
    // C++ NativeBridge ELF dependencies. Original product source is intact.
    ("packages/modules/StatsD/framework/Android.bp",
      "java_library_static", &["statslog-statsd"]),
    ("frameworks/proto_logging/stats/stats_log_api_gen/test_java/Android.bp",
      "java_atomslog_library", &["statsdtest_worksource_java_gen",
                                "statsdtest_cts_java_gen"]),
    ("build/make/tools/ide_query/prober_scripts/jvm/Android.bp",
      "java_library", &["ide_query_proberscript_jvm"]),
    ("frameworks/proto_logging/stats/enums/printing/Android.bp",
      "java_library", &["framework-printing-enums-proto-lite-java"]),
    ("system/security/identity/util/Android.bp",
      "java_library", &["identity-credential-util"]),
    ("system/server_configurable_flags/aconfigd/Android.bp",
      "java_library", &["aconfigd_java_utils"]),
    // Two Protobuf Android Java codegen tests, the Graphics SDK API jar
    // and Media APEX Java wrapper do not contribute to the C++ translator.
    // Full Android product keeps original Java modules and source intact.
    ("external/protobuf/Android.bp","java_test",
      &["aprotoc-test-nano-params","android-nano-test-parcelable-extendable"]),
    ("frameworks/base/libs/hwui/Android.bp","java_sdk_library",
      &["framework-graphics"]),
    ("packages/modules/Media/apex/framework/Android.bp","java_library",
      &["updatable-media"]),
    // Pinned independent Java components for HIDL/Health/AIDL diagnostics,
    // Java framework BinderObserver packaging, stats enums and Ravenwood.
    // None links the C++ ARM64 NativeBridge shared object or its host POSIX
    // tests. Full Android product discovery continues to use original BPs.
    ("system/tools/hidl/test/java_partial_test/Android.bp",
      "java_library", &["hidl_partial_java_test"]),
    ("hardware/interfaces/health/aidl/Android.bp",
      "java_library", &["android.hardware.health-translate-java"]),
    ("system/tools/aidl/Android.bp",
      "java_library", &["libsimpleparcelable_java"]),
    ("frameworks/base/services/Android.bp", "java_library",
      &["binder_observer_config_enabled","binder_observer_config_disabled"]),
    ("frameworks/proto_logging/stats/enums/stats/style/Android.bp",
      "java_library", &["styleprotoslite"]),
    ("hardware/interfaces/soundtrigger/aidl/cli/Android.bp",
      "java_binary", &["sthal_cli_3"]),
    ("frameworks/base/Ravenwood.bp",
      "java_library", &["framework-minus-apex-for-host"]),
    // Original Android device integration tests and shared test helpers
    // are not required for ARM64-to-x86_64 NativeBridge C++ ELF verification.
    // Do not hide Conscrypt JNI, Connectivity native BPF or TLS providers.
    ("packages/modules/Connectivity/tests/common/Android.bp",
      "java_library", &["FrameworksNetCommonTests"]),
    ("external/conscrypt/nsc/tests/Android.bp",
      "android_test", &["ConscryptNetworkSecurityConfigTests"]),
    // Framework's real Java jar products are not compiled by standalone
    // C++ NativeBridge / native POSIX host tests. This is target-private
    // discovery only, never an Android product build transformation.
    ("frameworks/base/Android.bp", "java_library",
     &["framework-minus-apex", "framework", "framework-all",
       "framework-minus-internal-res"]),
    // The original VCN pre-jarjar Java intermediate is not a C++ Teto
    // dependency and references the separately unselected Connectivity
    // pre-jarjar library. Preserve the actual VCN SDK and product source.
    ("packages/modules/Connectivity/Vcn/framework-b/Android.bp",
     "java_library", &["framework-connectivity-b-pre-jarjar"]),
    // The standalone NativeBridge shared object has no Java classpath.
    // Scope these exact Java-only module consumers (not broad directories)
    // out of the private native proof; original full Android product keeps
    // every Java provider, source and SDK API as-is.
    ("packages/modules/Connectivity/framework-t/Android.bp",
     "java_library", &["framework-connectivity-t-pre-jarjar"]),
    ("packages/modules/Connectivity/staticlibs/Android.bp",
     "java_library", &["net-utils-service-connectivity"]),
    ("packages/modules/Connectivity/Tethering/Android.bp",
     "android_library", &["TetheringApiCurrentLib", "TetheringApiStableLib"]),
    ("frameworks/base/Android.bp",
     "java_library", &["framework-minus-apex-headers"]),
    // Tethering's Java-only ConnectivityInternalApiUtil uses the
    // previously unselected framework-connectivity-pre-jarjar intermediate.
    // NativeBridge C++ does not consume this Java artifact; exact private
    // graph scope only, with full product source unchanged.
    ("packages/modules/Connectivity/framework/Android.bp",
      "java_library", &["connectivity-internal-api-util"]),
    // Bluetooth audio HAL session libraries are separate Android audio
    // product modules, not the ARM64-to-x86_64 Teto translator or host
    // POSIX tests. Only exclude these two exact original modules from the
    // isolated private ELF graph; all full product builds remain untouched.
    ("hardware/interfaces/bluetooth/audio/utils/Android.bp",
     "cc_library_shared",
     &["libbluetooth_audio_session", "libbluetooth_audio_session_aidl"]),
    // NativeBridge C++ translator does not compile the independent
    // Connectivity framework's Java jarjar intermediate libraries. Keep
    // network native source and all regular product targets unchanged.
    ("packages/modules/Connectivity/framework/Android.bp",
     "java_library",
     &["framework-connectivity-pre-jarjar",
       "framework-connectivity-post-jarjar"]),
    // Exact original HttpEngine Java output chain; none links into the
    // standalone C++ translator ELF or native POSIX host regression. Retain
    // real Cronet production modules for every full Android product build.
    ("external/cronet/android/Android.bp", "java_library",
      &["httpengine", "httpengine-pre-jarjar", "httpengine_classes_java"]),
    ("external/cronet/android/Android.bp", "java_genrule",
      &["httpengine_classes", "httpengine-jarjar-rules"]),
    // Separate Java annotation-processor variant of framework-minus-apex.
    // It is not an input to the standalone C++ Teto translator and host
    // tests; preserve framework-minus-apex, API providers and all product
    // targets. Exact name, type and source content verified fail-closed.
    ("frameworks/base/Android.bp", "java_library",
      &["framework-minus-apex-intdefs"]),
    // Standalone NativeBridge ELF and host POSIX tests do not link
    // libhwui, which belongs to Android's graphics UI rendering product.
    // Scoped exact module only; all full product modules remain intact.
    ("frameworks/base/libs/hwui/Android.bp","cc_library",&["libhwui"]),
    ("frameworks/base/libs/hwui/Android.bp","cc_benchmark",&["hwuimacro"]),
    // The original host-only ADB connection test and full-host protobuf
    // tool are not inputs of the ARM64 translator ELF or ART adbconnection.
    // Keep the actual ADB client shared lib and lite protobuf native provider.
    ("packages/modules/adb/libs/adbconnection/Android.bp",
       "cc_test_host", &["libadbconnection_test"]),
    ("packages/modules/adb/proto/Android.bp",
       "cc_library_host_static", &["libapp_processes_protos_full"]),
    // Java HttpEngine and Framework utility libraries are not inputs to the
    // isolated Teto ELF or its host POSIX tests. They remain fully intact
    // in the pinned source and in real product build graph.
    ("external/cronet/android/Android.bp","java_library",
       &["httpengine_internal"]),
    ("frameworks/base/Android.bp","java_library",
       &["framework-internal-utils"]),
    // Root Cronet API Java wrapper consumes the stable Java graph. Scope
    // just this exact wrapper for native ELF proof; Cronet APEX defaults,
    // product native code and full product Java modules remain unchanged.
    ("external/cronet/Android.bp","java_library",
       &["cronet_aml_api_java"]),
    // ART's system-server Java classpath packaging is outside the
    // native translator ELF; preserve the actual ART VM, JNI and services
    // in every normal product build and do not touch ART's bootclasspath.
    ("art/build/boot/Android.bp","systemserverclasspath_fragment",
       &["art-systemserverclasspath-fragment"]),
    // Cronet's pre-jarjar Java-only connectivity dependency, not the
    // AOSP native connectivity stack or the native ARM64 translator.
    ("packages/modules/Connectivity/framework/Android.bp","java_library",
       &["framework-connectivity-pre-jarjar-without-cronet"]),
    ("packages/modules/Connectivity/staticlibs/Android.bp","java_library",
       &["net-utils-device-common-ip"]),
    // ART service's Java SDK generation; keep ART's native runtime, JVM,
    // and service platform implementation in every product build.
    ("art/libartservice/service/Android.bp","java_sdk_library",
       &["service-art"]),
    // NetworkStack Java resource variants only; original product unchanged.
    ("packages/modules/NetworkStack/Android.bp","android_library",
       &["NetworkStackApiStableLib","NetworkStackApiCurrentLib"]),
    // Independent Java support libraries for Wi-Fi/Connectivity apps and
    // NetworkStack, not ARM64 translation shared-object inputs. Keep the
    // real C++ network services and their original full-product Blueprints.
    ("packages/modules/Connectivity/staticlibs/Android.bp","java_library",
       &["net-utils-service-wifi","net-utils-connectivity-apks"]),
    ("packages/modules/NetworkStack/Android.bp","java_library",
       &["DhcpPacketLib"]),
    ("packages/modules/Connectivity/service/ServiceConnectivityResources/Android.bp",
       "android_library",&["ServiceConnectivityResourcesLib"]),
    // Java wrapper for Bluetooth SDK; all Bluetooth native services survive.
    ("packages/modules/Bluetooth/framework/Android.bp","java_library",
       &["framework-bluetooth-pre-jarjar"]),
    // Actual Wi-Fi and Bluetooth Java SDKs remain in the full Android
    // product; these generated stubs are not inputs to the standalone
    // arm64-to-x86_64 native translation shared object.
    ("packages/modules/Bluetooth/framework/Android.bp",
     "java_sdk_library",&["framework-bluetooth"]),
    ("packages/modules/Wifi/framework/Android.bp",
     "java_library",&["framework-wifi-pre-jarjar"]),
    ("packages/modules/Wifi/framework/Android.bp",
     "java_sdk_library",&["framework-wifi"]),
    // ART Service Java instrumentation tests only, not the ART native VM
    // service and not the NativeBridge POSIX host suite.
    ("art/libartservice/service/Android.bp",
     "java_library",&["service-art-tests"]),
    ("art/libartservice/service/Android.bp",
     "android_test",&["ArtServiceTests"]),
    // Independent Java SDK generation and pre-jarjar wrapper, not a C++ Teto
    // shared-object input. Real Tethering platform and prebuilt SDK modules
    // remain unchanged in every full-product target and module source.
    ("packages/modules/Connectivity/Tethering/common/TetheringLib/Android.bp",
      "java_sdk_library", &["framework-tethering"]),
    ("packages/modules/Connectivity/Tethering/common/TetheringLib/Android.bp",
      "java_library", &["framework-tethering-pre-jarjar"]),
    // Independent Connectivity Java helper, used by product networking Java.
    ("packages/modules/Connectivity/staticlibs/Android.bp",
      "java_library", &["net-utils-services-common"]),
    // Java NSC SDK, not the actual Conscrypt native TLS libraries nor the
    // guest ARM64 NativeBridge ELF; full Android product unchanged.
    ("external/conscrypt/Android.bp",
      "java_sdk_library", &["framework-conscrypt-nsc"]),
    // CameraService host-side unit test is not the real CameraService or
    // the ARM64 native translator. Keep production camera modules intact.
    ("frameworks/av/services/camera/libcameraservice/tests/Android.bp",
     "cc_test_host", &["cameraservice_test_host"]),
    // Permission product SDK export requires the Permission APEX; neither
    // is consumed by the standalone NativeBridge shared object.
    ("packages/modules/Permission/Android.bp","sdk",
     &["permission-module-sdk"]),
    // Permission app APEX is a separate product bundle, not the C++ Teto
    // translator. Keep its original SDK/APEX content for full product builds.
    ("packages/modules/Permission/Android.bp", "apex",
     &["com.android.permission"]),
    // Framework connectivity is a Java SDK library, not the standalone
    // NativeBridge ELF. This exact-name private scope leaves all C/C++ media
    // and Networking components, original Android product builds unchanged.
    ("packages/modules/Connectivity/framework/Android.bp","java_sdk_library",
     &["framework-connectivity"]),
    // Keep original Tethering APEX package-level Java and APEX defaults
    // visible: NetworkStack and TetheringNext require ConnectivityNextEnableDefaults.
    // For private NativeBridge-only build, do not instantiate unrelated APEX
    // package or Java bootclasspath fragment. All full-product modules intact.
    ("packages/modules/Connectivity/Tethering/apex/Android.bp",
     "apex",&["com.android.tethering"]),
    ("packages/modules/Connectivity/Tethering/apex/Android.bp",
     "bootclasspath_fragment",&["com.android.tethering-bootclasspath-fragment"]),
    // Permission system-server Java classpath *packaging* references
    // service-permission which is an unselected SDK generator for private
    // NativeBridge ELF verification. Full Android service remains unchanged.
    ("packages/modules/Permission/Android.bp",
      "systemserverclasspath_fragment",
      &["com.android.permission-systemserverclasspath-fragment"]),
    // Standalone Conscrypt Java benchmarks/tests and Java SDK source/stub
    // generators are not inputs to x86_64 Teto ELF or Berberis POSIX host
    // tests. Keep original JNI, shared native libs, product API modules and
    // full Android product build unmodified.
    ("external/conscrypt/Android.bp","java_test",
       &["conscrypt-tests","conscrypt-benchmarks"]),
    ("external/conscrypt/Android.bp","android_test",
       &["ConscryptPrivateTestCases"]),
    ("packages/modules/Permission/service/Android.bp","java_sdk_library",
       &["service-permission"]),
    ("packages/modules/Connectivity/framework-t/Android.bp","java_sdk_library",
       &["framework-connectivity-t"]),
    // Distinct Android camera service and InputReader/SurfaceFlinger
    // native product modules. Neither is linked by the ARM64 Berberis ELF
    // or its private POSIX host tests. Scope only these exact modules for
    // strict NativeBridge-only Soong discovery; full Android product
    // builds and original source trees remain unchanged.
    ("frameworks/av/services/camera/libcameraservice/Android.bp",
      "cc_library_static",&["libcameraservice_device_independent"]),
    ("frameworks/native/libs/input/Android.bp",
      "cc_library",&["libinput"]),
    // Two standalone OTA/target-files packaging/test entrypoints. Their
    // actual Python library inputs and generic release build tools remain.
    // This excludes neither the NativeBridge ELF nor any Android product
    // target: only strict private NativeBridge-host test discovery.
    ("build/make/tools/releasetools/merge/Android.bp",
      "python_binary_host",&["merge_target_files"]),
    ("build/make/tools/releasetools/Android.bp",
      "python_test_host",&["releasetools_test"]),
    // Libcore Java/crypto CTS aggregation is not part of Berberis native
    // translation; preserve Libcore runtime, core-test source and complete
    // Android product targets. Only these original Java test modules are
    // hidden during isolated native-bridge build discovery.
    ("libcore/JavaLibrary.bp","java_test",
     &["core-tests","libcore-crypto-tests"]),
    // Only standalone Android OTA signing/generation entrypoints and their
    // target-file-specific Python library. Keep the real release-tools common
    // libraries and all product builds unmodified.
    ("build/make/tools/releasetools/Android.bp","python_library_host",
      &["releasetools_ota_from_target_files"]),
    ("build/make/tools/releasetools/Android.bp","python_binary_host",
      &["ota_from_target_files","sign_target_files_apks"]),
    // These exact original format-specific *media codec* implementation
    // modules are not linked by Teto/Berberis native_bridge or its host
    // POSIX tests; strict target-only source Projection removes their Soong
    // declarations but retains their upstream originals for Android builds.
    ("frameworks/av/media/module/extractors/mkv/Android.bp",
     "cc_library",&["libmkvextractor"]),
    ("frameworks/av/media/module/extractors/ogg/Android.bp",
     "cc_library",&["liboggextractor"]),
    ("frameworks/av/media/module/extractors/mpeg2/Android.bp",
     "cc_library",&["libmpeg2extractor"]),
    ("frameworks/av/media/module/mpeg2ts/Android.bp",
     "cc_library_static",&["libstagefright_mpeg2support",
                            "libstagefright_mpeg2support_nocrypto"]),
    // CI's pyfakefs fixtures and OTA's standalone Python merge entrypoint
    // are never linked into this single NativeBridge C++ ELF or host POSIX
    // regression. Retain all underlying CI/OTA production libraries, proto
    // providers and full-product Soong Blueprints.
    ("build/make/ci/Android.bp", "python_test_host",
      &["build_test_suites_test", "build_test_suites_local_test",
        "optimized_targets_test"]),
    ("build/make/tools/releasetools/Android.bp", "python_binary_host",
      &["merge_ota"]),
    // NativeBridge-only: Android Permission SDK/APEX packing is unrelated
    // to the x86_64 ELF. Preserve original platform permission native code.
    ("packages/modules/Permission/Android.bp", "bootclasspath_fragment",
     &["com.android.permission-bootclasspath-fragment"]),
    // Strict native ELF proof; leave these independent Java product/stub
    // graphs fully present for Android product builds.
    ("packages/modules/Wifi/framework/Android.bp","java_library",
     &["wifi-modules-utils"]),
    ("packages/modules/Permission/framework-s/Android.bp","java_sdk_library",
     &["framework-permission-s"]),
    ("frameworks/libs/modules-utils/java/com/android/modules/expresslog/Android.bp",
     "java_library",&["modules-utils-expresslog"]),
    ("external/icu/android_icu4j/Android.bp","java_test",&["android-icu4j-tests"]),
    // The StatsD Java SDK stubs aggregate intentionally unrelated module
    // Java flags. Keep production Stats JNI and other native modules intact.
    ("packages/modules/StatsD/framework/Android.bp",
      "java_sdk_library", &["framework-statsd"]),
    // Keep real Python protobuf provider, bootstrap Go plugin and Bloaty
    // binary. Only these exact unrelated host-side Python unit tests exit.
    ("external/protobuf/Android.bp", "python_test_host",
        &["libprotobuf-python-test"]),
    ("build/soong/bloaty/Android.bp", "python_test_host",
        &["bloaty_merger_test"]),
    // Full Media APEX sdk aggregation is unrelated to the native ELF proof.
    // Keep product original sdk provider in all other build targets.
    ("packages/modules/Media/apex/Android.bp", "sdk", &["media-module-sdk"]),
    // Original global Java-only SDK aggregation and standalone mDNS Java
    // test are outside native translation; preserve native source entirely.
    ("frameworks/base/Android.bp", "java_library",
        &["framework-non-updatable-unbundled-impl-libs"]),
    ("packages/modules/Connectivity/staticlibs/Android.bp", "java_library",
        &["net-utils-device-common-mdns-standalone-build-test"]),
    // Isolated fuzz testing target only; preserve production service.
    ("frameworks/native/cmds/servicemanager/Android.bp",
     "cc_fuzz", &["servicemanager_fuzzer"]),
    // The original Treble labeling host Python validation tool requires
    // PyYAML but is not linked into the NativeBridge ELF or host POSIX suite.
    // Preserve policy generation and full-product SELinux tests.
    ("system/sepolicy/tests/Android.bp","python_binary_host",
     &["treble_labeling_tests"]),
    // Exact original non-runtime Java-only test modules and AVF Grpc client.
    // Do not hide libcore core-oj, modules-utils-build or Debian AIDL IDL.
    ("libcore/JavaLibrary.bp", "java_library_static", &["core-test-rules"]),
    ("external/libphonenumber/Android.bp", "java_library", &["libphonenumber_test"]),
    ("frameworks/libs/modules-utils/java/com/android/modules/utils/build/Android.bp",
        "java_library", &["modules-utils-build_system"]),
    ("packages/modules/Virtualization/libs/debian_service/Android.bp",
        "java_library", &["debian-service-grpclib-lite"]),
    ("packages/modules/Virtualization/libs/debian_service/Android.bp",
        "java_genrule", &["debian-service-stub-lite"]),
    // The IPsec utility here is a Java-only AndroidX consumer, unrelated to
    // the independently selected ARM64 native bridge ELF and its POSIX tests.
    ("packages/modules/Connectivity/staticlibs/Android.bp",
      "java_library", &["net-utils-framework-ipsec"]),
    // Only the standalone Trusty storage proxy *host executable*; preserve
    // the vendor/system binaries and the complete Trusty source for product
    // builds. The native translator does not depend on this host-side tool.
    ("system/core/trusty/storage/proxy/Android.bp",
     "cc_binary_host", &["storageproxyd_host"]),
    // Cronet Java implementation is unrelated to building the native Teto
    // translator; retain real Cronet native products, APEX defaults and
    // Connectivity HttpEngine defaults in the private Soong namespace.
    ("external/cronet/Android.bp", "java_library", &["cronet_aml_java"]),
    // The Android-wide merged API stubs graph aggregates test/Java variants
    // from every Mainline module. Do not instantiate this global API report
    // while linking the single C++ NativeBridge ELF. Keep the Soong API
    // bootstrap_go_package and all actual platform providers untouched.
    ("frameworks/base/api/Android.bp", "combined_apis", &["frameworks-base-api"]),
    // Keep the actual pinned VCN framework-connectivity-b SDK and flags
    // required by the original Tethering APEX bootclasspath. The independent
    // IPsec utility Java jar is not a NativeBridge C++ build target.
    ("packages/modules/Connectivity/Vcn/framework-b/Android.bp",
     "java_library", &["vcn-utils-framework-ipsec"]),
    // Keep Cronet's original production APEX defaults, HttpEngine Java
    // provider and actual stable native libs. Only test java wrappers and
    // Android instrumentation helpers are omitted from this C++ ELF proof.
    ("external/cronet/Android.bp", "java_library",
      &["cronet_aml_java__testing"]),
    ("external/cronet/Android.bp", "java_defaults",
      &["cronet_testing","cronet_native_unittests_defaults",
      "cronet_native_net_unittests_defaults","cronet_java_tests",
      "net_unittests_data"]),
    ("external/cronet/Android.bp", "android_test_helper_app",
      &["cronet_tester_app","stable_cronet_tester_app",
      "cronet_net_tester_app","stable_cronet_net_tester_app"]),
    ("external/cronet/Android.bp", "android_test",
      &["NetHttpCoverageTests"]),
    // Media3 Java extractor selection is not required for the standalone
    // ARM64-to-x86_64 native translation ELF. Preserve libmediaparser-jni
    // and the actual Android Media product source in full product builds.
    ("packages/modules/Media/apex/framework/Android.bp",
     "java_library", &["extractor-impl"]),
    ("packages/modules/Media/apex/framework/Android.bp",
     "java_sdk_library", &["framework-media"]),
    // Non-native VCN utility reference when VCN's Java framework is scoped.
    ("packages/modules/Connectivity/staticlibs/Android.bp",
     "java_library", &["net-utils-framework-vcn"]),
    // The original aconfig diff Tradefed host test requires an unrelated Java
    // harness not selected by this isolated native bridge ELF proof.
    // Preserve all aconfig binaries, their real flag sources and product
    // declarations. Full Android build is unaffected.
    (
        "build/make/tools/aconfig/aconfig_diff/tests/Android.bp",
        "java_test_host",
        &["aconfig_diff_test"],
    ),
    // Exact original test-only servicemanager modules depend on Perfetto
    // testing telemetry, not on the native ARM64 translator. Keep all
    // production servicemanager/vndservicemanager modules and AOSP source.
    (
        "frameworks/native/cmds/servicemanager/Android.bp",
        "cc_test",
        &["servicemanager_test"],
    ),
    (
        "frameworks/native/cmds/servicemanager/Android.bp",
        "cc_test_host",
        &["servicemanager_unittest"],
    ),
    // Pinned external/skia/Android.bp describes libskia, but its large set of
    // image-codec *production* dependencies is not selected by a test whose
    // only output is the ARM64-to-x86_64 NativeBridge ELF.
    // Scope just this unselected module during the private host-only proof.
    // The original Blueprint and all full-product targets are preserved.
    ("external/skia/Android.bp", "cc_library_static", &["libskia"]),
    // The API-level AndroidX compatibility wrappers and alpha WebKit AAR
    // are unrelated to the private C++ NativeBridge translator. Full product
    // discovery and original Blueprint modules remain unchanged.
    ("prebuilts/sdk/current/androidx/Android.bp", "android_library",
      &["androidx.annotation_annotation-experimental-nodeps",
        "androidx.collection_collection-nodeps",
        "androidx.core_core-animation-nodeps",
        "androidx.core_core-animation-testing-nodeps",
        "androidx.core_core-nodeps",
        "androidx.transition_transition-ktx-nodeps",
        "androidx.webkit_webkit-nodeps"]),
    (
        "prebuilts/sdk/current/androidx/m2repository/androidx/webkit/webkit/1.12.0-alpha02/Android.bp",
        "android_library_import",
        &["androidx.webkit_webkit"],
    ),
    // The AndroidX 1.20.0 alpha01 Java AAR is unrelated to the x86_64
    // NativeBridge translator. Keep regular Android product builds intact.
    (
        "prebuilts/sdk/current/androidx/m2repository/androidx/core/core/1.20.0-alpha01/Android.bp",
        "android_library_import",
        &["androidx.core_core"],
    ),
    // Real installd and its product source stay intact: only the host
    // run_dex2oat_test exercises an unselected PGO-flag test namespace.
    (
        "frameworks/native/cmds/installd/Android.bp",
        "cc_test_host",
        &["run_dex2oat_test"],
    ),
    // APK signature production APIs remain; only the CTS/test harness exits.
    ("tools/apksig/Android.bp", "java_test_host", &["apksig-test"]),
    // Only Error Prone test helper; preserve real plugin and annotations.
    ("external/error_prone/Android.bp", "java_library_host", &["error_prone_test_helpers"]),
    // Exact host test modules with unselected Truth/Tradefed/Mockito fixtures.
    // Keep all production protobuf and DevicePolicy modules in their files.
    ("packages/modules/Virtualization/tests/pvmfw/libs/Android.bp", "java_library_host", &["PvmfwHostTestLib"]),
    ("external/protobuf/Android.bp", "java_test_host", &["libprotobuf-java-full-test"]),
    ("frameworks/libs/modules-utils/java/com/android/modules/utils/build/testing/Android.bp", "java_library_host", &["modules-utils-build-testing"]),
    ("build/make/tools/permission_versioning/Android.bp", "java_test_host", &["permission_versions_tests"]),
    ("packages/modules/Virtualization/tests/libs/host/Android.bp", "java_library_host", &["MicrodroidHostTestLib"]),
    ("frameworks/base/tools/processors/devicepolicy/Android.bp", "java_test_host", &["DevicePolicyAnnotationProcessorTests"]),
    // Only private NativeBridge proof: leave ordinary apksig/apksigner intact.
    // External AWS/GCP KMS signing backends do not link ARM64 translation.
    (
        "tools/apksig/Android.bp",
        "java_library_host",
        &["apksig-kms-provider-aws", "apksig-kms-provider-gcp"],
    ),
    (
        "tools/apksig/Android.bp",
        "java_binary_host",
        &["apksigner-kms"],
    ),
    (
        "frameworks/base/services/core/java/com/android/server/am/Android.bp",
        "java_aconfig_library",
        &["am_flags_host_lib"],
    ),
    (
        "art/build/flags/Android.bp",
        "java_aconfig_library",
        &["art-aconfig-flags-java-lib-host", "art-aconfig-rw-flags-java-lib-test"],
    ),
    (
        "build/make/tools/aconfig/aconfig/Android.bp",
        "java_aconfig_library",
        &["aconfig_host_test_java_library"],
    ),
    (
        "build/make/tools/aconfig/aconfig/Android.bp",
        "java_test_host",
        &["AconfigJavaHostTest"],
    ),
    (
        "prebuilts/sdk/current/androidx/JavaPlugins.bp",
        "java_plugin",
        &[
            "androidx.appsearch_appsearch-compiler-plugin",
            "androidx.room_room-compiler-plugin",
            "androidx.appfunctions_appfunctions-compiler-plugin",
        ],
    ),
    (
        "prebuilts/tools/common/m2/robolectric.bp",
        "android_library_import",
        &["robolectric-monitor-1.0.2-alpha1"],
    ),
    (
        "prebuilts/sdk/current/Android.bp",
        "android_library_import",
        &["com.android.support.multidex_1.0.3"],
    ),
    (
        "frameworks/base/AconfigFlags.bp",
        "java_aconfig_library",
        &[
            "android.permission.flags-aconfig-java-host",
            "android.security.flags-aconfig-java-host",
            "android.appwidget.flags-aconfig-java-host",
            "android.app.appfunctions.flags-aconfig-java-host",
            "android.content.pm.flags-aconfig-java-host",
            "android.content.res.flags-aconfig-java-host",
            "android.crashrecovery.flags-aconfig-java-host",
            "android.os.vibrator.flags-aconfig-java-host",
            "android.view.inputmethod.flags-aconfig-java-host",
            "com.android.media.flags.bettertogether-aconfig-java-host",
            "com.android.media.flags.editing-aconfig-java-host",
            "device_policy_aconfig_flags_lib_host",
            "android.app.supervision.flags-aconfig-java-host",
            "android.hardware.usb.flags-aconfig-java-host",
            // Host-only Aconfig variant; keep product power_flags_lib.
            "power_flags_lib_host",
            // Window host Aconfig only; keep device Window flags Java module.
            "com.android.window.flags.window-aconfig-java-host",
        ],
    ),
    (
        "build/soong/test_suites/Android.bp",
        "test_suite_package",
        &["general-tests"],
    ),
    (
        "tools/metalava/Android.bp",
        "java_binary_host",
        &["metalava-antlr4-tool"],
    ),
    (
        "external/kotlinc/Android.bp",
        "kotlin_plugin",
        &["kotlin-compose-compiler-plugin", "kotlin-compose-compiler-embeddable-plugin"],
    ),
    (
        "frameworks/proto_logging/stats/stats_log_api_gen/Android.bp",
        "rust_library",
        // M852: DnsResolver Rust still depends on the original StatsLog header.
        &["libstatslog_rust"],
    ),
    (
        "frameworks/proto_logging/stats/stats_log_api_gen/Android.bp",
        "rust_test_host",
        &["test_api_gen_rust"],
    ),
    // Original Java host-only test uses TestParameterInjector and Truth,
    // neither needed by Teto's native C++ ARM64 translator or host GTests.
    // Retain the stats generator/production modules in the same source tree.
    (
        "frameworks/proto_logging/stats/stats_log_api_gen/test_java/Android.bp",
        "java_test_host",
        &["StatsCodeGenSrcsJavaHostTest"],
    ),
    // Original StatsD CTS/MTS Tradefed host test uses Truth and CTS test
    // utils. It is unrelated to the x86_64 NativeBridge translator.
    // Keep product StatsSocket/StatsPull and the pinned StatsD modules intact.
    (
        "packages/modules/StatsD/framework/test/hostsidetests/Android.bp",
        "java_test_host",
        &["FrameworkStatsdHostTest"],
    ),
    // The StatsD Java flags' host variant is unrelated to ARM64 ELF
    // translation. Preserve the genuine StatsD C flags and declarations.
    (
        "packages/modules/StatsD/flags/Android.bp",
        "java_aconfig_library",
        &["statsd_flags_java_lib"],
    ),
    // Java host-only utility/annotation checkers are outside a C++ NativeBridge
    // translator proof. Keep original protobuf/error-prone provider files and
    // their product modules for full Android product builds.
    (
        "external/protobuf/Android.bp",
        "java_library_host",
        &["libprotobuf-java-util-full"],
    ),
    (
        "system/tools/xsdc/tests/Android.bp",
        "java_test_host",
        &["xsdc-java-tests"],
    ),
    // Translation-only C++ proof: AndroidX Leanback was never selected,
    // and its alpha AAR references appcompat/recyclerview provider variants
    // outside the pinned sparse runtime graph. Keep production originals.
    ("prebuilts/sdk/current/androidx/Android.bp","android_library",&["androidx.leanback_leanback-nodeps"]),
    ("prebuilts/sdk/current/androidx/m2repository/androidx/leanback/leanback/1.3.0-alpha01/Android.bp",
     "android_library_import",&["androidx.leanback_leanback"]),
    // NativeBridge does not consume display EGL Java flags or compile the
    // system resource APK. Strict Soong will still reject any actual native
    // target that depends on a removed provider.
    ("frameworks/base/AconfigFlags.bp","java_aconfig_library",&["android.graphics.egl.flags-aconfig-java"]),
    ("frameworks/base/core/res/Android.bp","android_app",&["framework-res"]),

    // The original system libutils allocator tests are never linked into the
    // ARM64 NativeBridge ELF. Preserve libutils_binder product libraries.
    ("system/core/libutils/binder/Android.bp","cc_test",
     &["libutils_binder_test","libutils_binder_test_custom_allocator"]),
    // Zipalign hosts APK release tooling but is not an input to the private
    // standalone translator build; keep its original Blueprint and all
    // product-target variants untouched. Scope the mutually referring trio.
    ("build/make/tools/zipalign/Android.bp","cc_library_host_static",&["libzipalign"]),
    ("build/make/tools/zipalign/Android.bp","cc_binary_host",&["zipalign"]),
    ("build/make/tools/zipalign/Android.bp","cc_test_host",&["zipalign_tests"]),

    // VINTF assembly command-line host tools are unrelated to producing a
    // standalone NativeBridge shared library. Keep the genuine libvintf,
    // checkvintf, and Android product metadata generation untouched.
    ("system/libvintf/Android.bp","cc_library_static",&["libassemblevintf"]),
    ("system/libvintf/Android.bp","cc_binary_host",&["assemble_vintf"]),

    // Strict NativeBridge C++-only build: these Java-generated application
    // feature flag wrappers have no ELF translator consumers, while each
    // depends on an AOSP product feature module omitted by this sparse tree.
    // Real Android system and service builds keep every original wrapper.
    ("frameworks/base/AconfigFlags.bp","java_aconfig_library",
     &["android.chre.flags-aconfig-java",
       "telecom_flags_core_java_lib",
       "telecom_flags_core_java_aconfig_java_exported_lib",
       "power_flags_lib",
       "telephony_flags_core_java_lib",
       "telephony_flags_core_java_exported_lib"]),
    // Original Droidloom Java apps are full-product targets, not direct
    // dependencies of the standalone C++ ARM64 translator proof.
    // ICU4J's Ravenwood Java test needs Gson, JUnitParams and test-only tzdata.
    // ICU4J production modules and native ICU C libraries remain visible.
    ("external/icu/android_icu4j/Android.bp","java_test",&["android-icu4j-tests-core-only"]),
    // Keep upstream libprotobuf-python: the original fsverity manifest
    // generator depends on its host Python protobuf provider, even while
    // the final selected output is the native bridge shared library.

    // DSP/effect implementations and media extractor ColorUtils are built
    // by the Android product media stack. The independent ARM64 translator
    // ELF (and its host POSIX suite) has no direct dependency on these
    // unselected target variants; retain their full product source.
    ("frameworks/av/media/libeffects/preprocessing/Android.bp","cc_library",&["libaudiopreprocessing"]),
    ("frameworks/av/media/libeffects/preprocessing/Android.bp","cc_library_shared",&["libpreprocessingaidl"]),
    ("frameworks/av/media/module/foundation/Android.bp","cc_library_static",&["libstagefright_foundation_colorutils_ndk"]),
    // NativeBridge proof removes the Java-only generated wrappers below; the
    // single platform aconfig group *is itself* a Java Aconfig bundle which
    // enumerates those wrappers. Preserve native Aconfig declarations.
    ("frameworks/base/AconfigFlags.bp","aconfig_declarations_group",
     &["framework-minus-apex-aconfig-declarations"]),

];

fn cone_covers_metadata(path: &Path, sparse_paths: &[PathBuf]) -> bool {
    sparse_paths.is_empty() || sparse_paths.iter().any(|sparse| {
        // Cone mode also keeps files directly in every selected path's ancestor directory.
        path.starts_with(sparse) || path.parent().is_some_and(|parent| sparse.starts_with(parent))
    })
}

fn validate_nativebridge_scope_source_paths(lock: &droidloom_source::SparseSourceLock) -> Result<()> {
    for (relative, _, _) in PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES {
        let path = Path::new(relative);
        let project = lock.projects.iter()
            .filter(|project| path.starts_with(&project.path))
            .max_by_key(|project| project.path.components().count())
            .ok_or_else(|| format!("NativeBridge metadata filter has no locked project: {relative}"))?;
        let within_project = path.strip_prefix(&project.path)?;
        if !cone_covers_metadata(within_project, &project.sparse_paths) {
            return fail(format!(
                "NativeBridge metadata filter needs {relative}, outside the locked sparse paths for {} at {}; include its real pinned metadata before projecting source",
                project.path.display(), project.commit,
            ));
        }
    }
    Ok(())
}

// The NativeBridge-only proof does not need the Java dependency-mapper
// executable or tests. The original Go protoimpl in the child proto/
// directory *is* required by Soong incremental_javac_input. Do not hide
// the whole parent directory: retain its package/license declaration.
// For a Linux/x86_64 Teto-only build, never instantiate the independent
// Windows host variant of StatsPull's header module. Its Windows variant
// pulls libwinpthread even when no Windows output is requested. This is a
// fail-closed exact transformation of the pinned original, restored by the
// existing source Projection guard after the private build.
fn private_statspull_headers_without_windows_variant(blueprint: &str) -> Result<String> {
    let owner = "cc_library_headers {\n    name: \"libstatspull_headers\",";
    let boundary = "\nfilegroup {\n    name: \"libstatspull_test_default_map\",";
    let (before, after_owner) = blueprint.split_once(owner)
        .ok_or("pinned StatsPull header library declaration missing")?;
    let (module, after) = after_owner.split_once(boundary)
        .ok_or("pinned StatsPull headers boundary missing")?;
    let windows = "    target: {\n        windows: {\n            enabled: true,\n        },\n    },\n";
    if module.matches(windows).count() != 1 {
        return fail("pinned StatsPull Windows-only header variant changed");
    }
    let replacement = windows.replace("enabled: true", "enabled: false");
    Ok(format!("{before}{owner}{}{boundary}{after}",
        module.replacen(windows, &replacement, 1)))
}

fn private_dependency_mapper_package_only(blueprint: &str) -> Result<String> {
    for name in [
        "dependency-mapper",
        "dependency-mapper-host-lib",
        "dependency-mapper-tests",
        "dependency-mapper-test-data",
    ] {
        if blueprint.matches(&format!("    name: \"{name}\",")).count() != 1 {
            return fail(format!("original dependency mapper module {name} changed"));
        }
    }
    metadata_only(blueprint)
}

fn private_without_named_java_module(blueprint: &str, kind: &str, name: &str) -> Result<String> {
    let needle = format!("    name: \"{name}\",");
    if blueprint.matches(&needle).count() != 1 {
        return fail(format!("nativebridge test scope requires one unchanged {name}"));
    }
    let at = blueprint.find(&needle).ok_or("missing original module")?;
    let prefix = format!("{kind} {{\n");
    let start = blueprint[..at]
        .rfind(&prefix)
        .ok_or("unexpected original Java Blueprint module kind")?;
    if blueprint[start + prefix.len()..at].contains("\n}") {
        return fail("unexpected module layout before selected Java test module");
    }
    let suffix = blueprint[at..]
        .find("\n}\n")
        .ok_or("unterminated original Java Blueprint module")?;
    let end = at + suffix + 3;
    if blueprint[start..end].matches(&needle).count() != 1 {
        return fail("selected Java module identity changed");
    }
    Ok(format!("{}{}", &blueprint[..start], &blueprint[end..]))
}

const NATIVE_ENGINE_JAVA_CONSUMER_SCOPE: &[(&str, &[&str], &[(&str, &str)])] = &[
    ("packages/modules/NetworkStack/Android.bp",
     &["NetworkStackApiStableLib", "NetworkStackApiCurrentLib"],
     &[("java_genrule", "NetworkStackJarJarRules"),
       ("java_defaults", "NetworkStackAppDefaults"),
       ("android_app", "NetworkStack"), ("android_app", "TestNetworkStack")]),
    ("packages/modules/Connectivity/framework/Android.bp",
     &["framework-connectivity-pre-jarjar", "framework-connectivity-post-jarjar"],
     &[("java_genrule", "framework-connectivity-jarjar-rules")]),
    ("packages/modules/Connectivity/Tethering/common/TetheringLib/Android.bp",
     &["framework-tethering-pre-jarjar"],
     &[("java_genrule", "framework-tethering-jarjar-rules")]),
    ("packages/modules/Connectivity/service/Android.bp",
     &[],
     &[("java_genrule", "connectivity-jarjar-rules"),
       ("java_genrule", "service-connectivity-jarjar-gen"),
       ("java_genrule", "service-nearby-jarjar-gen"),
       ("java_genrule", "service-remoteauth-jarjar-gen"),
       ("java_genrule", "service-thread-jarjar-gen"),
       ("java_genrule", "service-networksecurity-jarjar-gen"),
       ("java_defaults", "service-connectivity-defaults"),
       ("java_library", "service-connectivity-for-tests"),
       ("java_library", "service-connectivity")]),
    ("libcore/JavaLibrary.bp",
     &["core-tests"],
     &[("java_genrule", "libcore-non-cts-tests-txt")]),
];

fn project_native_engine_java_consumers(
    projection: &mut Projection, source: &Path, mode: SoongDependencyMode,
) -> Result<()> {
    if mode != SoongDependencyMode::NativeEngineTargetClosure {
        return Ok(());
    }
    // Apply only after the checked producer filters. Unselected Java consumers
    // still expand {.jar} command labels during graph generation, including
    // sparse service variants. Scope their exact wrapper chains, preserving
    // actual JNI/native providers, real producers, and every other build mode.
    for (relative, producers, consumers) in NATIVE_ENGINE_JAVA_CONSUMER_SCOPE {
        let path = source.join(relative);
        let mut text = fs::read_to_string(&path).map_err(|error| format!(
            "cannot read pinned engine Java consumer metadata {}: {error}", path.display(),
        ))?;
        for producer in *producers {
            if text.contains(&format!("    name: \"{producer}\",")) {
                return fail(format!("engine Java consumer scope requires producer {producer} already scoped out of {relative}"));
            }
        }
        for (kind, name) in *consumers {
            text = private_without_named_java_module(&text, kind, name)?;
        }
        projection.put(&path, text)?;
    }
    Ok(())
}

// Original framework API-doc Blueprints contain *only* documentation,
// stubs, doc defaults, filegroups, and Java doc generator targets. They are
// not components of a private x86_64 NativeBridge ELF. Validate every top
// level declaration and exact number, instead of silently dropping future
// upstream modules if the pinned source set changes.
fn private_nativebridge_without_unselected_api_docs(blueprint: &str) -> Result<String> {
    let allowed = ["stubs_defaults","droidstubs","filegroup","doc_defaults","droiddoc","java_genrule"];
    let mut count = 0usize;
    for line in blueprint.lines() {
        if let Some(module) = line.strip_suffix(" {") {
            if !line.starts_with(' ') && !line.starts_with('\t') {
                if !allowed.contains(&module) {
                    return fail(format!("unknown Android API Docs module {module}; refuse private scope"));
                }
                count += 1;
            }
        }
    }
    if count != 20 || !blueprint.contains("name: \"ds-static-docs\"")
        || !blueprint.contains("name: \"offline-sdk-docs\"") {
        return fail("pinned Android API Docs module inventory changed");
    }
    Ok(String::new())
}

// The vendor product Blueprint is rsync-mirrored only *after* the early
// source projection. Keep these unselected Android Java UI applications in
// the original production tree, but scope them only once the mirrored vendor
// source is final. This fixes the earlier pre-rsync scope being overwritten.
// AOSP's pinned frameworks/base/AconfigFlags.bp defines 171 generated
// Java-only flag wrappers. Soong validates their absent product Aconfig
// declarations even when only an unrelated C++ NativeBridge .so is requested.
// For this one private C++ target, exclude *only* top-level
// java_aconfig_library stanzas; preserve all Aconfig declarations, C++,
// Rust, product and nonflag modules. Fail on upstream inventory drift.
// Product builds never invoke this transformation.
// Standalone NativeBridge still needs the genuine update-engine public
// header provider through libsnapshot_cow. Do not hide the whole AOSP
// update_engine project. Retain exact package/license plus the original
// cc_library_headers module, dropping unrelated OTA payload binaries
// only within this private translator proof; full builds are untouched.
// The pinned StubLibraries.bp API/doc graph contains one mandatory HIDL
// Java provider: hwbinder.stubs. Retain its *original* droidstubs, java
// library and the exact priv_apps variable required by Metalava. All other
// unrelated whole-platform API test stubs are scoped out privately.
// Pinned StubLibraries.bp is a self-contained Java-only API stub/docs
// collection, not a NativeBridge C++ library. Every top-level declaration
// must be one of the exact original eight kinds and count exactly 70; abort
// on drift rather than suppress unknown upstream modules. Full product
// builds still consume the untouched file.
fn private_nativebridge_without_java_api_stubs(blueprint: &str) -> Result<String> {
    let allowed = [
        "droidstubs","java_api_library","java_defaults","java_genrule",
        "java_library","non_updatable_exportable_droidstubs",
        "soong_config_module_type_import","stubs_defaults",
    ];
    let mut count=0usize;
    for line in blueprint.lines() {
        if let Some(kind) = line.strip_suffix(" {") {
            if !line.starts_with(' ') && !line.starts_with('\t') {
                if !allowed.contains(&kind) {
                    return fail(format!("new unrelated or native module {kind} in Java-only API stub Blueprint"));
                }
                count+=1;
            }
        }
    }
    if count!=70
        || !blueprint.contains("name: \"android-non-updatable.stubs.module_lib.from-text\"")
        || !blueprint.contains("name: \"api-stubs-docs-non-updatable\"") {
        return fail("pinned Java-only API stub module inventory changed");
    }
    let mut retained=String::new();
    let variable="priv_apps = [\n";
    let at=blueprint.find(variable).ok_or("pinned hwbinder priv_apps missing")?;
    if blueprint.matches(variable).count()!=1 {
        return fail("hwbinder priv_apps declaration changed");
    }
    let end=at+blueprint[at..].find("\n]\n")
        .ok_or("unterminated pinned priv_apps variable")?+3;
    retained.push_str(&blueprint[at..end]);
    retained.push('\n');
    for (kind,name) in [
        ("droidstubs","hwbinder-stubs-docs"),
        ("java_library","hwbinder.stubs"),
    ] {
        let marker=format!("{kind} {{\n    name: \"{name}\",");
        if blueprint.matches(&marker).count()!=1 {
            return fail(format!("original HIDL stub provider {name} changed"));
        }
        let at=blueprint.find(&marker).ok_or("missing pinned hwbinder module")?;
        let end=at+blueprint[at..].find("\n}\n")
          .ok_or("unterminated pinned hwbinder module")?+3;
        retained.push_str(&blueprint[at..end]);
        retained.push('\n');
    }
    Ok(retained)
}

// Original ART adbconnection requires these pinned upstream cc_defaults,
 // but the remaining adb host / daemon CLI and APEX modules are independent
 // of the one selected native translator shared object. Retain exact three
 // upstream stanzas and package/license, refusing any provider drift.
fn private_nativebridge_adb_root_defaults_only(blueprint: &str) -> Result<String> {
    let mut out=metadata_only(blueprint)?;
    for name in ["adb_defaults","adbd_defaults","host_adbd_supported"] {
        let marker=format!("cc_defaults {{\n    name: \"{name}\",");
        if blueprint.matches(&marker).count()!=1 {
            return fail(format!("original ADB default {name} declaration changed"));
        }
        let start=blueprint.find(&marker)
            .ok_or("missing pinned ADB default")?;
        let end=start+blueprint[start..].find("\n}\n")
            .ok_or("unterminated upstream ADB default")?+3;
        out.push_str(&blueprint[start..end]);
        out.push('\n');
    }
    Ok(out)
}

fn private_nativebridge_update_engine_headers_only(blueprint: &str) -> Result<String> {
    let name="cc_library_headers {\n    name: \"libupdate_engine_headers\",";
    if blueprint.matches(name).count()!=1 {
        return fail("pinned update-engine header provider changed");
    }
    let at=blueprint.find(name).ok_or("update-engine header module missing")?;
    let end=at+blueprint[at..].find("\n}\n").ok_or("unterminated update-engine header module")?+3;
    let mut out=metadata_only(blueprint)?;
    out.push_str(&blueprint[at..end]);
    Ok(out)
}

fn private_nativebridge_without_java_aconfigs(
    blueprint: &str, minimum_modules: usize,
) -> Result<String> {
    let mut output = String::with_capacity(blueprint.len());
    let mut dropping = false;
    let mut count = 0;
    for line in blueprint.lines() {
        if !dropping {
            if line == "java_aconfig_library {" {
                count += 1;
                dropping = true;
            } else {
                output.push_str(line);
                output.push('\n');
            }
        } else if line == "}" {
            dropping = false;
        } else if !line.starts_with(' ') && !line.starts_with('\t')
            && !line.is_empty() && !line.starts_with("//") {
            return fail("malformed pinned Java Aconfig source block");
        }
    }
    if dropping || count < minimum_modules || count > 180 {
        return fail("pinned Java Aconfig inventory or block structure changed");
    }
    Ok(output)
}

fn private_nativebridge_vendor_cxx_only(blueprint: &str) -> Result<String> {
    let mut text = blueprint.to_owned();
    for name in ["DroidloomIME", "DroidloomHome"] {
        text = private_without_named_java_module(&text, "android_app", name)?;
    }
    // The privileged input java_binary is included in complete product
    // targets, but is not a dependency of the C++ NativeBridge-only proof.
    text = private_without_named_java_module(&text, "java_binary", "droidloom-input-bridge")?;
    // Runtime SystemUI probe belongs to full Android app/control products,
    // not private NativeBridge ELF verification. Keep native bridge modules.
    text = private_without_named_java_module(&text, "java_library", "DroidloomSystemUIProbe")?;
    Ok(text)
}

fn private_without_conscrypt_fuzzer(blueprint: &str) -> Result<String> {
    if blueprint.matches(PRIVATE_CONSCRYPT_FUZZER_MODULE).count() != 1 {
        return fail("private native-bridge test scope expected one unchanged ART fuzzer module");
    }
    Ok(blueprint.replacen(PRIVATE_CONSCRYPT_FUZZER_MODULE, "", 1))
}

pub fn build_targets(
    repo: &Path,
    source: &Path,
    out: &Path,
    work: &Path,
    product: &str,
    jobs: usize,
    targets: &[&str],
) -> Result<()> {
    build_targets_with_dependency_mode(
        repo,
        source,
        out,
        work,
        product,
        jobs,
        targets,
        SoongDependencyMode::Strict,
    )
}

// The source release stays pinned to cp2a. A user variant does not make
// these sources the separate CP3A/QPR1 runtime cohort.
const PRODUCTION_TARGET_RELEASE: &str = "cp2a";
const PRODUCTION_BUILD_VARIANT: &str = "user";

// All normal Android producer entry points construct this command. Explicit
// environment values override an inherited development variant; no caller or
// environment-selected debug mode is part of the production path.
fn production_soong_command(
    source: &Path, out: &Path, work: &Path, product: &str,
    jobs: usize, selected_targets: &[PathBuf],
) -> Result<Command> {
    let mut cmd = Command::new(out.join("soong_ui"));
    cmd.current_dir(source)
        .env("SOONG_NINJA", "ninja")
        .env("TOP", source)
        .env("OUT_DIR", out)
        .env("ORIGINAL_PWD", source)
        .env(
            "PATH",
            format!(
                "{}:{}:{}",
                work.join("mesa-tools/src/compiler/clc").display(),
                work.join("mesa-tools/src/compiler/spirv").display(),
                std::env::var("PATH")?
            ),
        )
        .env("CCACHE_DIR", work.join("ccache"))
        .env("CCACHE_TEMPDIR", work.join("ccache-tmp"))
        .env("TARGET_PRODUCT", product)
        .env("TARGET_RELEASE", PRODUCTION_TARGET_RELEASE)
        .env("TARGET_BUILD_VARIANT", PRODUCTION_BUILD_VARIANT)
        .env("JAVA_HOME", source.join("prebuilts/jdk/jdk21/linux-x86"))
        .env("SOONG_INCREMENTAL_ANALYSIS", "false")
        .arg("--make-mode")
        .arg(format!("-j{jobs}"))
        .args(selected_targets);
    Ok(cmd)
}

fn build_targets_with_dependency_mode(
    repo: &Path,
    source: &Path,
    out: &Path,
    work: &Path,
    product: &str,
    jobs: usize,
    targets: &[&str],
    dependency_mode: SoongDependencyMode,
) -> Result<()> {
    build_targets_with_art_projection(
        repo, source, out, work, product, jobs, targets, dependency_mode, None,
    )
}

/// Fixed ART-only build entry. Normal callers retain the exact previous wrapper.
pub fn build_native_generation_art(
    repo: &Path,
    source: &Path,
    out: &Path,
    work: &Path,
    product: &str,
    jobs: usize,
    flavor: crate::native_generation_art::Flavor,
) -> Result<()> {
    build_targets_with_art_projection(
        repo, source, out, work, product, jobs,
        crate::native_generation_art::TARGETS, SoongDependencyMode::Strict, Some(flavor),
    )
}

/// Complete ordinary-app engine/ART pair; no private AppZygote authorization.
pub fn build_native_generation_pair(
    repo: &Path, source: &Path, out: &Path, work: &Path, product: &str, jobs: usize,
) -> Result<()> {
    build_targets_with_optional_role_ingress(
        repo, source, out, work, product, jobs, crate::native_generation_pair_build::TARGETS,
        SoongDependencyMode::Strict,
        Some(crate::native_generation_art::Flavor::EnabledBuildOnly), false, None, true,
    )
}

/// Complete Java/framework and Android JNI build. This route never enables a role.
pub fn build_native_role_ingress(
    repo: &Path,
    source: &Path,
    out: &Path,
    work: &Path,
    product: &str,
    jobs: usize,
    resume_source_staging: Option<&Path>,
) -> Result<()> {
    build_targets_with_optional_role_ingress(
        repo, source, out, work, product, jobs,
        crate::native_role_ingress::TARGETS, SoongDependencyMode::Strict, None, true,
        resume_source_staging, false,
    )
}

fn build_targets_with_art_projection(
    repo: &Path,
    source: &Path,
    out: &Path,
    work: &Path,
    product: &str,
    jobs: usize,
    targets: &[&str],
    dependency_mode: SoongDependencyMode,
    art_flavor: Option<crate::native_generation_art::Flavor>,
) -> Result<()> {
    build_targets_with_optional_role_ingress(
        repo, source, out, work, product, jobs, targets, dependency_mode, art_flavor, false, None, false,
    )
}

// These paths are already modified by the normal vendor/Mesa projection.
// Capture their pre-build metadata and original absence before rsync can replace it.
const PRE_MIRROR_PROJECTION_PATHS: &[&str] = &[
    "vendor/droidloom/mesa3d/src/gallium/drivers/zink/zink_screen.c",
    "vendor/droidloom/mesa3d/src/freedreno/common/freedreno_devices.py",
    "vendor/droidloom/mesa3d/src/gallium/auxiliary/util/u_threaded_context.c",
    "vendor/droidloom/mesa3d/src/util/u_queue_cpu.h",
    "vendor/droidloom/mesa3d/src/util/u_queue.c",
    "vendor/droidloom/mesa3d/android/mesa3d_cross.mk",
    "vendor/droidloom/android/device/droidloom_x86_64/BoardConfig.mk",
];
fn capture_pre_mirror_projection_originals(p:&mut Projection,source:&Path)->Result<()> {
    use std::os::unix::fs::MetadataExt;
    // Validate the finite path set before creating the first journal record.
    for relative in PRE_MIRROR_PROJECTION_PATHS {
        let path=source.join(relative);
        for ancestor in path.ancestors().take_while(|a|a.starts_with(source)) {
            match fs::symlink_metadata(ancestor) {
                Ok(meta) if meta.file_type().is_symlink() || (ancestor==path.as_path() && (!meta.is_file() || meta.nlink()!=1)) || (ancestor!=path.as_path() && !meta.is_dir()) => return fail("pre-mirror projection original or parent is not an ordinary unaliased path"),
                Ok(_) => (),
                Err(error) if error.kind()==std::io::ErrorKind::NotFound => (),
                Err(error) => return Err(error.into()),
            }
        }
    }
    for relative in PRE_MIRROR_PROJECTION_PATHS {p.save(&source.join(relative))?;}
    Ok(())
}


fn build_targets_with_optional_role_ingress(
    repo: &Path,
    source: &Path,
    out: &Path,
    work: &Path,
    product: &str,
    jobs: usize,
    targets: &[&str],
    dependency_mode: SoongDependencyMode,
    art_flavor: Option<crate::native_generation_art::Flavor>,
    typed_ingress: bool,
    resume_source_staging: Option<&Path>,
    ordinary_pair: bool,
) -> Result<()> {
    // Reject a widened closure before materializing or projecting any source.
    validate_soong_dependency_mode(dependency_mode, targets)?;
    if resume_source_staging.is_some() && !typed_ingress {
        return fail("explicit source staging is limited to the independent strict typed ingress route");
    }
    if ordinary_pair {
        crate::native_generation_pair_build::validate_scope(
            targets, dependency_mode == SoongDependencyMode::Strict, art_flavor,
            typed_ingress, resume_source_staging.is_some(),
        )?;
        crate::native_generation_pair_build::begin_attempt(repo, work, out)?;
    }
    if typed_ingress {
        if art_flavor.is_some() || dependency_mode != SoongDependencyMode::Strict
            || targets != crate::native_role_ingress::TARGETS
        {
            return fail("typed ingress build requires its two complete targets, strict dependencies and disabled runtime");
        }
        crate::native_role_ingress::begin_attempt(repo, work, out)?;
    }
    if !ordinary_pair {
        if let Some(flavor) = art_flavor {
            if dependency_mode != SoongDependencyMode::Strict
                || targets != crate::native_generation_art::TARGETS
            {
                return fail("paired ART projection requires only its fixed targets and strict dependencies");
            }
            crate::native_generation_art::begin_attempt(work, out, flavor)?;
        }
    }
    if dependency_mode == SoongDependencyMode::NativeEngineTargetClosure {
        crate::native_engine::begin_attempt(out, product)?;
    }
    let lock = if ordinary_pair {
        crate::native_generation_pair_build::source_lock_path(repo)?
    } else if typed_ingress {
        crate::native_role_ingress::source_lock_path(repo)?
    } else {
        repo.join("android/manifest/m2-sparse-source-lock.json")
    };
    let source_lock = droidloom_source::load_lock(&lock)?;
    if ordinary_pair {
        // Pair preparation must use an independent workspace and the normal
        // source materializer's exact expanded SDK-provider manifest.
        crate::native_generation_pair_build::verify_source_workspace(&lock, &source_lock, source)?;
    } else if typed_ingress {
        // Keep the previous typed source authority and its migration unchanged.
        crate::native_role_ingress::verify_source_workspace(&lock, &source_lock, source)?;
    }
    if nativebridge_discovery_scope(targets) {
        validate_nativebridge_scope_source_paths(&source_lock)?;
    }
    if typed_ingress && !source.exists() {
        // A failed fetch or checkout retains its private staging and a durable
        // per-project progress stream. Explicit resume re-verifies every reuse.
        droidloom_source::materialize_resuming(&lock, &source_lock, source,
            resume_source_staging, &out.join("droidloom-source-progress.jsonl"))?;
    } else if resume_source_staging.is_some() {
        return fail("explicit source staging cannot replace an existing published source tree");
    } else if !source.exists() {
        droidloom_source::materialize(&lock, &source_lock, source)?;
    } else {
        droidloom_source::reconcile(&lock, &source_lock, source)?;
    }
    droidloom_source::verify_materialized(&lock, &source_lock, source)?;
    let native_bridge_source = crate::native_bridge::prepare_source(repo, source)?;
    for (aidl, adapter) in [
        ("statusbar/IStatusBar.aidl", "EmptyStatusBar"),
        ("policy/IKeyguardService.aidl", "EmptyKeyguard"),
    ] {
        let digest = hash(
            &source
                .join("frameworks/base/core/java/com/android/internal")
                .join(aidl),
        )?;
        let generated = fs::read_to_string(repo.join(format!(
            "android/framework/droidloom-systemui/src/com/android/systemui/compat/{adapter}.java"
        )))?;
        if !generated
            .lines()
            .any(|line| line == format!("// AIDL SHA-256: {digest}"))
        {
            return fail(
                "SystemUI Binder adapters are stale; run tools/droidloom-systemui-stubs for the pinned source",
            );
        }
    }
    let mut p = Projection::new(work.join("source-projection.json"))?;
    if let Some(flavor) = art_flavor {
        crate::native_generation_art::project(repo, source, &mut p, flavor)?;
    }
    if ordinary_pair {
        crate::native_generation_pair_build::project_engine(repo, source, &mut p, &native_bridge_source)?;
    }
    for (cwd, patch) in PATCHES {
        p.patch(source, cwd, &repo.join(patch))?;
    }
    if typed_ingress {
        let patch = crate::native_role_ingress::verified_patch(repo, source)?;
        p.patch(source, "frameworks/base", &patch)?;
        crate::native_role_ingress::verify_projected(source)?;
    }
    for (cwd, patch) in target_closure_soong_patches(dependency_mode) {
        p.patch(source, cwd, &repo.join(patch))?;
    }
    if qualified_defaults_mode(dependency_mode) {
        p.patch(source, "build/soong", &repo.join(
            "android/apex-compat/0007-transitive-default-missing-dependencies.patch"))?;
    }
    if leaf_go_memory_mode(dependency_mode) || art_flavor.is_some() || typed_ingress {
        p.patch(source, "build/soong", &repo.join(
            "android/apex-compat/0008-soong-leaf-go-memory-budget.patch"))?;
        p.patch(source, "build/blueprint", &repo.join(
            "android/apex-compat/0009-blueprint-stream-uncached-module-actions.patch"))?;
    }
    project_ordinary_pair_graph_resources(repo, source, &mut p, ordinary_pair, dependency_mode)?;
    for (cwd, patch) in audio_apex_pcm_patches(dependency_mode) {
        p.patch(source, cwd, &repo.join(patch))?;
    }
    project_native_leaf_discovery_scope(&mut p, source, dependency_mode)?;
    if minigbm_only_build(targets) {
        p.patch(source, "external/minigbm", &repo.join(
            "android/aosp-patches/0017-minigbm-native-amd-yv12-strides.patch"))?;
        // The Mainline netd implementation and its ABI stubs are not inputs
        // to the graphics allocator. Keep its source intact for product builds.
        p.put(&source.join("packages/modules/Connectivity/bpf/netd/.find-ignore"), b"")?;
        // This exact native allocator target never packages the Tethering APEX.
        // Retain its shared defaults, hidden-API filegroups and classpath modules.
        let apex = source.join("packages/modules/Connectivity/Tethering/apex/Android.bp");
        let original = fs::read_to_string(&apex)?;
        p.put(&apex, private_without_named_java_module(
            &original, "apex", "com.android.tethering")?)?;
    }
    // The complete ordinary pair retains providers required by its unchanged
    // upstream test_package consumers. Private-role routes keep their own scope.
    project_blueprints(&mut p, source, typed_ingress || ordinary_pair,
        ordinary_pair, dependency_mode)?;
    if ordinary_pair {
        let path = source.join("tools/apksig/Android.bp");
        let original = fs::read_to_string(&path)?;
        p.put(&path, ordinary_pair_local_signer_blueprint(&original)?)?;
    }
    if audio_apex_only_build(targets) || minigbm_only_build(targets) {
        // Select AOSP's original pinned host test-harness jars. Their actual
        // provider names, classes and platform-proto dependency are unchanged.
        // The unselected source harness and SNAPI service are not audio inputs.
        let config = source.join("build/make/core/android_soong_config_vars.mk");
        let original = fs::read_to_string(&config)?;
        p.put(&config, audio_select_original_prebuilt_tradefed(&original)?)?;
        for relative in ["tools/tradefederation/core", "tools/tradefederation/contrib",
                         "test/suite_harness", "build/make/tools/soong_api",
                         "system/core/debuggerd/test_permissive_mte",
                         "art/test/update-rollback", "art/test/odsign",
                         "build/soong/cmd/kotlinc_incremental",
                         "hardware/interfaces/usb/gadget/aidl/vts/functional",
                         "packages/modules/Connectivity/tests/deflake",
                         "packages/modules/StatsD/framework/test/hostsidetests",
                         "packages/modules/StatsD/tests",
                         "frameworks/hardware/interfaces/stats/aidl/vts/java",
                         "cts/common/device-side/nativetesthelper/jni",
                         "packages/modules/Connectivity/tests/cts/hostside",
                         "packages/modules/Virtualization/tests",
                         "libnativehelper/tests",
                         "packages/modules/Virtualization/guest/pvmfw",
                         "libcore/benchmarks",
                         "frameworks/base/packages/SettingsLib",
                         "hardware/interfaces/automotive/vehicle/aidl/aidl_test"] {
            p.put(&source.join(relative).join(".find-ignore"), b"")?;
        }
        let path = source.join("frameworks/native/services/serialservice/Android.bp");
        let metadata = fs::read_to_string(&path)?;
        p.put(&path, audio_serialservice_metadata_without_stale_team(&metadata)?)?;
        let apksig = source.join("tools/apksig/Android.bp");
        let original = fs::read_to_string(&apksig)?;
        p.put(&apksig, audio_without_unselected_cloud_kms(&original)?)?;
        let tests = source.join("platform_testing/Android.bp");
        let original = fs::read_to_string(&tests)?;
        p.put(&tests, audio_without_unselected_platform_test_aggregators(&original)?)?;
        // This all-product test package is never part of the sole audio APEX.
        // Keep its original CTS/VTS providers and every native audio module;
        // only the unselected aggregator is omitted in this private projection.
        let suites = source.join("build/soong/test_suites/Android.bp");
        let original = fs::read_to_string(&suites)?;
        p.put(&suites, private_without_named_java_module(
            &original, "test_suite_package", "general-tests")?)?;
        let stats_tests = source.join("frameworks/proto_logging/stats/stats_log_api_gen/test_java/Android.bp");
        let original = fs::read_to_string(&stats_tests)?;
        p.put(&stats_tests, private_without_named_java_module(
            &original, "java_test_host", "StatsCodeGenSrcsJavaHostTest")?)?;
        let flags = source.join("frameworks/base/AconfigFlags.bp");
        let original = fs::read_to_string(&flags)?;
        p.put(&flags, private_without_named_java_module(
            &original, "java_aconfig_library", "power_flags_lib_host")?)?;
        let protobuf = source.join("external/protobuf/Android.bp");
        let original = fs::read_to_string(&protobuf)?;
        p.put(&protobuf, private_without_named_java_module(
            &original, "java_test_host", "libprotobuf-java-full-test")?)?;
        // Neither Java SDK packaging nor host UI tests link either native leaf.
        // Keep HWUI's C++ implementation and all native Settings providers.
        for (relative, kind, name) in [
            ("frameworks/base/libs/hwui/Android.bp", "java_sdk_library", "framework-graphics"),
            ("frameworks/base/packages/SettingsLib/Preference/tests/Android.bp",
                "android_robolectric_test", "SettingsLibPreferenceTest"),
        ] {
            let path = source.join(relative);
            let original = fs::read_to_string(&path)?;
            p.put(&path, private_without_named_java_module(&original, kind, name)?)?;
        }
        // Connectivity's Java service repackaging is not a native leaf input.
        // Preserve every actual C++/JNI networking provider in this file.
        let connectivity = source.join("packages/modules/Connectivity/service/Android.bp");
        let mut original = fs::read_to_string(&connectivity)?;
        for name in ["service-connectivity-jarjar-gen", "service-nearby-jarjar-gen",
                     "service-remoteauth-jarjar-gen", "service-thread-jarjar-gen",
                     "service-networksecurity-jarjar-gen"] {
            original = private_without_named_java_module(&original, "java_genrule", name)?;
        }
        p.put(&connectivity, original)?;
        let error_prone = source.join("external/error_prone/Android.bp");
        let original = fs::read_to_string(&error_prone)?;
        p.put(&error_prone, private_without_named_java_module(
            &original, "java_library_host", "error_prone_test_helpers")?)?;
        // Java annotation processors are unselected by this native AIDL APEX.
        // This matches the existing standalone NativeBridge target isolation.
        let plugins = source.join("prebuilts/sdk/current/androidx/JavaPlugins.bp");
        let mut original = fs::read_to_string(&plugins)?;
        for name in ["androidx.appsearch_appsearch-compiler-plugin",
                     "androidx.room_room-compiler-plugin",
                     "androidx.appfunctions_appfunctions-compiler-plugin"] {
            original = private_without_named_java_module(&original, "java_plugin", name)?;
        }
        p.put(&plugins, original)?;
        let kotlin = source.join("external/kotlinc/Android.bp");
        let mut original = fs::read_to_string(&kotlin)?;
        for name in ["kotlin-compose-compiler-plugin", "kotlin-compose-compiler-embeddable-plugin"] {
            original = private_without_named_java_module(&original, "kotlin_plugin", name)?;
        }
        p.put(&kotlin, original)?;
        // Standalone OpenJDK analysis CLI is not an AIDL/audio build input.
        p.put(&source.join("libcore/tools/openjdk-analyzer/.find-ignore"), b"")?;
        p.put(&source.join("libcore/tools/non-cts-json-generator/.find-ignore"), b"")?;
        // This CTS test-inventory report is the generator's only consumer;
        // keep all Libcore runtime libraries and actual API inputs intact.
        let libcore = source.join("libcore/JavaLibrary.bp");
        let original = fs::read_to_string(&libcore)?;
        p.put(&libcore, private_without_named_java_module(
            &original, "java_genrule", "libcore-non-cts-tests-txt")?)?;
        // These closed Rust gRPC/USB/host-allocator groups are not inputs to
        // the native audio APEX. Reuse the existing NativeBridge isolation;
        // preserve all actual C++ audio, platform USB and allocator providers.
        for name in ["grpcio", "grpcio-sys", "libusb1-sys", "rusb", "ippusb",
                     "tikv-jemalloc-sys", "tikv-jemallocator"] {
            let relative = format!("external/rust/android-crates-io/crates/{name}/.find-ignore");
            p.put(&source.join(relative), b"")?;
        }
    }
    if nativebridge_discovery_scope(targets) {
        // Root ADB Blueprint defines real cc_defaults for libadbconnection.
        // Preserve exactly the original 3 providers while excluding unrelated
        // ADB daemon/CLI product module discovery in the standalone Teto test.
        let root=source.join("packages/modules/adb/Android.bp");
        let original=fs::read_to_string(&root)?;
        p.put(&root,private_nativebridge_adb_root_defaults_only(&original)?)?;
    }
    if nativebridge_discovery_scope(targets) {
        let docs = source.join("frameworks/base/api/ApiDocs.bp");
        let upstream = fs::read_to_string(&docs)?;
        p.put(&docs, private_nativebridge_without_unselected_api_docs(&upstream)?)?;
    }
    if nativebridge_discovery_scope(targets) {
        for (relative, kind, names) in PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES {
            let path = source.join(relative);
            let mut original = fs::read_to_string(&path).map_err(|error| format!(
                "cannot read pinned NativeBridge scope metadata {}: {error}", path.display(),
            ))?;
            for name in *names {
                original = private_without_named_java_module(&original, kind, name)?;
            }
            p.put(&path, original)?;
        }
    }
    project_native_engine_java_consumers(&mut p, source, dependency_mode)?;
    if nativebridge_discovery_scope(targets) {
        let path=source.join("frameworks/base/api/StubLibraries.bp");
        let original=fs::read_to_string(&path)?;
        p.put(&path, private_nativebridge_without_java_api_stubs(&original)?)?;
    }
    if nativebridge_discovery_scope(targets) || audio_apex_only_build(targets) || minigbm_only_build(targets) {
        let path=source.join("system/update_engine/Android.bp");
        let original=fs::read_to_string(&path)?;
        p.put(&path, private_nativebridge_update_engine_headers_only(&original)?)?;
    }
    if nativebridge_discovery_scope(targets) {
        // Apply after the exact-name Java host/tool filters above, so the
        // original names are still checked before the structural scope.
        let path = source.join("frameworks/base/AconfigFlags.bp");
        let original = fs::read_to_string(&path)?;
        p.put(&path, private_nativebridge_without_java_aconfigs(&original, 120)?)?;
    }
    if nativebridge_discovery_scope(targets) || audio_apex_only_build(targets) || minigbm_only_build(targets) {
        // The explicit target builds exclude the unrelated all-platform
        // fuzzer test aggregator; real SELinux contexts remain intact.
        // Full Android product builds still run the original fuzzer bindings.
        let bindings = source.join("system/sepolicy/contexts/Android.bp");
        let original = fs::read_to_string(&bindings)?;
        p.put(&bindings, private_without_fuzzer_bindings_test(&original)?)?;
    }
    if nativebridge_discovery_scope(targets) {
        let art = source.join("art/build/Android.bp");
        let original = fs::read_to_string(&art)?;
        p.put(&art, private_without_conscrypt_fuzzer(&original)?)?;
        // The platform_testing root is exclusively a synthetic test-suite
        // aggregator. Preserve its original package/license metadata and all
        // child Blueprint packages, but not its global test_package bundles
        // in a NativeBridge-only proof. Full product builds remain unmodified.
        // A Linux NativeBridge/C++ host test neither builds nor links the
        // pinned StatsPull Windows header variant. Full product unchanged.
        let statspull = source.join("packages/modules/StatsD/lib/libstatspull/Android.bp");
        let upstream = fs::read_to_string(&statspull)?;
        p.put(&statspull, private_statspull_headers_without_windows_variant(&upstream)?)?;
        let suite = source.join("platform_testing/Android.bp");
        let original = fs::read_to_string(&suite)?;
        p.put(&suite, metadata_only(&original)?)?;
        // Preserve the pinned proto/Android.bp Go provider while scoping
        // only the unrelated Java host programs out of this proof build.
        let mapper = source.join("build/make/tools/dependency_mapper/Android.bp");
        let original = fs::read_to_string(&mapper)?;
        p.put(&mapper, private_dependency_mapper_package_only(&original)?)?;
    }
    for relative in private_nativebridge_unrelated_paths(targets) {
        p.put(&source.join(relative).join(".find-ignore"), b"")?;
    }
    project_test_fixture_exclusions(&mut p, source, ordinary_pair, dependency_mode)?;
    // The MTE-upgrade host Tradefed fixture is not part of either NativeBridge
    // output. It requires test-only host utilities absent from the pinned
    // translation-only sparse source closure. Do not disable it for real
    // Droidloom product or system build targets.
    if nativebridge_discovery_scope(targets) || audio_apex_only_build(targets) || minigbm_only_build(targets) {
        p.put(
            &source.join("system/core/init/test_upgrade_mte/.find-ignore"),
            b"",
        )?;
    }
    // Mirror current sources on every invocation; deletion is propagated too.
    capture_pre_mirror_projection_originals(&mut p,source)?;
    let vendor = source.join("vendor/droidloom");
    fs::create_dir_all(&vendor)?;
    for relative in [
        "Android.bp",
        "LICENSE",
        "LICENSES",
        "graphics",
        "runtime/droidloom-cpu-placement",
        "android/framework",
        "android/lmkd-compat",
        "android/runtime",
        "android/native-bridge",
        "android/selinux-compat",
        "android/device",
        "device",
        "android/mesa",
    ] {
        let destination = vendor.join(relative);
        if repo.join(relative).is_dir() {
            fs::create_dir_all(&destination)?;
            run(Command::new("rsync")
                .args(["-a", "--delete"])
                .arg(format!("{}/", repo.join(relative).display()))
                .arg(&destination))?;
        } else {
            copy(&repo.join(relative), &destination)?;
        }
    }
    crate::native_bridge::prepare_build(source, &vendor, work, &mut p)?;
    if nativebridge_discovery_scope(targets) {
        // Post-mirror projection; never apply these production-app filters
        // before the Android.bp rsync, which would silently overwrite them.
        let path = vendor.join("Android.bp");
        let mirrored = fs::read_to_string(&path)?;
        p.put(&path, private_nativebridge_vendor_cxx_only(&mirrored)?)?;
    }
    let mesa = vendor.join("mesa3d");
    fs::create_dir_all(&mesa)?;
    run(Command::new("rsync")
        .args(["-a", "--delete"])
        .arg(format!("{}/", work.join("mesa-source").display()))
        .arg(&mesa))?;
    p.patch(
        source,
        "vendor/droidloom/mesa3d",
        &repo.join("android/aosp-patches/0011-mesa-zink-kgsl.patch"),
    )?;
    p.patch(
        source,
        "vendor/droidloom/mesa3d",
        &repo.join("android/aosp-patches/0012-mesa-adreno722.patch"),
    )?;
    p.patch(
        source,
        "vendor/droidloom/mesa3d",
        &repo.join("android/aosp-patches/0013-mesa-texture-upload-span.patch"),
    )?;
    p.patch(
        source,
        "vendor/droidloom/mesa3d",
        &repo.join("android/aosp-patches/0014-mesa-background-cpu-placement.patch"),
    )?;
    let cross = mesa.join("android/mesa3d_cross.mk");
    let cross_text = fs::read_to_string(&cross)?;
    let python_assignment = "MESA3D_PYTHONPATH := $(AOSP_ABSOLUTE_PATH)/external/python/mako";
    if !cross_text.contains(python_assignment) {
        return fail("Mesa Python build projection no longer matches its pinned source");
    }
    p.put(
        &cross,
        cross_text.replace(
            python_assignment,
            &format!("MESA3D_PYTHONPATH := {}", work.join("python").display()),
        ),
    )?;
    p.put(
        &vendor.join("android/prebuilts/framework-res.apk"),
        fs::read(work.join("framework-res.apk"))?,
    )?;
    let board = vendor.join("android/device/droidloom_x86_64/BoardConfig.mk");
    let native = work.join("mesa-native.ini");
    write(
        &native,
        format!(
            "[binaries]\nmesa_clc = {}\nvtn_bindgen2 = {}\n",
            meson_string(&work.join("mesa-tools/src/compiler/clc/mesa_clc"))?,
            meson_string(&work.join("mesa-tools/src/compiler/spirv/vtn_bindgen2"))?
        ),
    )?;
    p.put(
        &board,
        fs::read_to_string(&board)?
            + &format!(
                "\nBOARD_MESA3D_MESON_ARGS += -Dmesa-clc=system --native-file {}\n",
                native.display()
            ),
    )?;
    // Generate the init projection from the pinned source with the same checked patch.
    let init = tempfile::Builder::new().prefix("init-").tempdir_in(work)?;
    copy(
        &source.join("system/core/rootdir/init.rc"),
        &init.path().join("rootdir/init.rc"),
    )?;
    run(Command::new("git")
        .env("GIT_CEILING_DIRECTORIES", work)
        .current_dir(init.path())
        .arg("apply")
        .arg(repo.join("android/apex-compat/0001-droidloom-classpath-projection.patch")))?;
    copy(&init.path().join("rootdir/init.rc"), &work.join("init.rc"))?;
    p.stabilize_all()?;
    let selected_targets = selected_soong_targets(dependency_mode, targets, out, product)?;
    if ordinary_pair {
        crate::native_generation_pair_build::write_inputs(
            repo, source, out, &selected_targets,
            serde_json::to_value(p.effective_inventory(repo, source)?)?, &native_bridge_source,
        )?;
    } else if let Some(flavor) = art_flavor {
        crate::native_generation_art::write_inputs(
            out, flavor, &selected_targets,
            serde_json::to_value(p.effective_inventory(repo, source)?)?,
        )?;
    }
    if typed_ingress {
        crate::native_role_ingress::write_inputs(
            repo, source, out, &selected_targets, p.effective_inventory(repo, source)?,
        )?;
    }
    let engine_inputs = if dependency_mode == SoongDependencyMode::NativeEngineTargetClosure {
        Some(crate::native_engine::engine_build_inputs(
            repo, source, &vendor, work, out, &native_bridge_source,
            targets, &selected_targets, p.effective_inventory(repo, source)?,
        )?)
    } else {
        None
    };
    if let Some(inputs) = &engine_inputs {
        crate::native_engine::write_inputs(out, product, inputs)?;
    }
    bootstrap(source, out)?;
    copy(
        &source.join("prebuilts/build-tools/common/framework/turbine.jar"),
        &out.join("host/linux-x86/framework/turbine.jar"),
    )?;
    let mut cmd = production_soong_command(source, out, work, product, jobs, &selected_targets)?;
    configure_soong_dependencies(&mut cmd, dependency_mode, targets)?;
    configure_ordinary_pair_graph_observation(&mut cmd, ordinary_pair);
    let result = run_build(&mut cmd);
    p.restore()?;
    result?;
    if ordinary_pair {
        crate::native_generation_pair_build::write_command_completion(out, product)?;
    } else if let Some(flavor) = art_flavor {
        crate::native_generation_art::write_command_completion(out, flavor)?;
    }
    if typed_ingress {
        crate::native_role_ingress::write_command_completion(out)?;
    }
    if let Some(inputs) = engine_inputs {
        crate::native_engine::write_engine_build_receipt(source, out, product, inputs)?;
    }
    if targets.contains(&"droidloom-native-bridge") {
        write(
            &out.join("target/product")
                .join(product)
                .join("droidloom-native-bridge-source.json"),
            serde_json::to_vec_pretty(&native_bridge_source)?,
        )?;
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn projection_v2_pre_mirror_capture_restores_after_actual_rsync_and_interruption() {
        use std::os::unix::fs::PermissionsExt;
        for exit in 0..3 {
            let d=tempfile::tempdir().unwrap();let source=d.path().join("source");let mirror=d.path().join("mirror");fs::create_dir(&source).unwrap();fs::create_dir(&mirror).unwrap();
            let original_time=std::time::UNIX_EPOCH+std::time::Duration::new(1_700_000_001,987_654_321);
            let mirror_time=std::time::UNIX_EPOCH+std::time::Duration::new(1_800_000_002,123_456_789);
            let mut originals=Vec::new();
            for (i,relative) in PRE_MIRROR_PROJECTION_PATHS.iter().enumerate() {
                let path=source.join(relative);let new=mirror.join(relative);fs::create_dir_all(path.parent().unwrap()).unwrap();fs::create_dir_all(new.parent().unwrap()).unwrap();
                let absent=relative.ends_with("/u_queue_cpu.h");
                if !absent {fs::write(&path,b"same original bytes").unwrap();fs::set_permissions(&path,fs::Permissions::from_mode(if i<5 {0o644}else{0o664})).unwrap();fs::File::open(&path).unwrap().set_modified(original_time).unwrap();}
                originals.push((path,if absent {None}else{Some(fs::metadata(source.join(relative)).unwrap().permissions().mode())}));
                fs::write(&new,b"same original bytes").unwrap();fs::set_permissions(&new,fs::Permissions::from_mode(0o664)).unwrap();fs::File::open(new).unwrap().set_modified(mirror_time).unwrap();
            }
            let journal=d.path().join("journal.json");let mut p=Projection::new(journal.clone()).unwrap();capture_pre_mirror_projection_originals(&mut p,&source).unwrap();
            let status=Command::new("rsync").args(["-a","--delete"]).arg(format!("{}/",mirror.display())).arg(&source).status().unwrap();assert!(status.success());
            assert_ne!(fs::metadata(&originals[0].0).unwrap().permissions().mode(),originals[0].1.unwrap());
            assert_eq!(fs::metadata(&originals[6].0).unwrap().modified().unwrap(),mirror_time);
            for (path,_) in &originals {p.put(path,b"projected build bytes").unwrap();}
            let saved=decode_projection_journal(&fs::read(&journal).unwrap(),&source).unwrap();assert_eq!(saved.len(),7);
            for row in saved {if row.bytes.is_some(){assert_eq!(row.modified,Some(original_time));}else{assert!(row.path.ends_with("u_queue_cpu.h"));}}
            match exit {0=>p.restore().unwrap(),1=>drop(p),_=>{std::mem::forget(p);recover(&journal,&source).unwrap();}}
            for (path,mode) in originals {
                if let Some(mode)=mode {assert_eq!(fs::read(&path).unwrap(),b"same original bytes");let m=fs::metadata(path).unwrap();assert_eq!(m.permissions().mode(),mode);assert_eq!(m.modified().unwrap(),original_time);}
                else {assert!(!path.exists());}
            }
            assert!(!journal.exists());
        }
    }

    #[test]
    fn projection_v2_pre_mirror_alias_is_rejected_before_any_journal_or_copy() {
        use std::os::unix::fs::symlink;
        let d=tempfile::tempdir().unwrap();let source=d.path().join("source");let outside=d.path().join("outside");fs::create_dir(&source).unwrap();fs::create_dir(&outside).unwrap();
        let parent=source.join("vendor/droidloom/mesa3d/src");fs::create_dir_all(&parent).unwrap();symlink(&outside,parent.join("util")).unwrap();
        fs::write(outside.join("u_queue.c"),b"untouched outside").unwrap();let journal=d.path().join("journal");let mut p=Projection::new(journal.clone()).unwrap();
        assert!(capture_pre_mirror_projection_originals(&mut p,&source).is_err());assert!(!journal.exists());assert_eq!(fs::read(outside.join("u_queue.c")).unwrap(),b"untouched outside");
        fs::remove_file(parent.join("util")).unwrap();fs::create_dir(parent.join("util")).unwrap();fs::hard_link(outside.join("u_queue.c"),parent.join("util/u_queue.c")).unwrap();
        assert!(capture_pre_mirror_projection_originals(&mut p,&source).is_err());assert!(!journal.exists());assert_eq!(fs::read(outside.join("u_queue.c")).unwrap(),b"untouched outside");
    }

    #[test]
    fn projection_v2_restores_deleted_recreated_exec_and_private_permissions_exactly() {
        use std::os::unix::fs::PermissionsExt;
        let d=tempfile::tempdir().unwrap();let source=d.path().join("source");fs::create_dir(&source).unwrap();
        let journal=d.path().join("journal.json");let time=std::time::UNIX_EPOCH+std::time::Duration::new(1_700_000_001,987_654_321);
        let mut originals=Vec::new();let mut p=Projection::new(journal.clone()).unwrap();
        for (n,mode)in [0o664,0o700,0o640,0o755].iter().enumerate(){
            let path=source.join(format!("file{n}"));fs::write(&path,b"original").unwrap();fs::set_permissions(&path,fs::Permissions::from_mode(*mode)).unwrap();fs::File::open(&path).unwrap().set_modified(time).unwrap();
            let full_mode=fs::metadata(&path).unwrap().permissions().mode();p.put(&path,b"projected").unwrap();fs::remove_file(&path).unwrap();fs::write(&path,b"replacement").unwrap();fs::set_permissions(&path,fs::Permissions::from_mode(0o600)).unwrap();p.put(&path,b"second projection").unwrap();originals.push((path,full_mode));
        }
        let raw=fs::read(&journal).unwrap();assert_eq!(decode_projection_journal(&raw,&source).unwrap().len(),4);p.restore().unwrap();assert!(!journal.exists());
        for(path,mode)in originals{assert_eq!(fs::read(&path).unwrap(),b"original");assert_eq!(fs::metadata(&path).unwrap().permissions().mode(),mode);assert_eq!(fs::metadata(&path).unwrap().modified().unwrap(),time);}
    }
    #[test]
    fn projection_v2_drop_after_business_error_restores_modes_and_original_absence() {
        use std::os::unix::fs::PermissionsExt;
        let d=tempfile::tempdir().unwrap();let source=d.path().join("source");fs::create_dir(&source).unwrap();let path=source.join("private");let absent=source.join("originally-absent");let journal=d.path().join("journal");
        fs::write(&path,b"private original").unwrap();fs::set_permissions(&path,fs::Permissions::from_mode(0o700)).unwrap();let mode=fs::metadata(&path).unwrap().permissions().mode();let time=fs::metadata(&path).unwrap().modified().unwrap();
        let fail_run=||->Result<()>{let mut p=Projection::new(journal.clone())?;p.put(&path,b"temporary")?;p.put(&absent,b"temporary new file")?;fs::set_permissions(&path,fs::Permissions::from_mode(0o644))?;fail("actual simulated business failure")};
        assert!(fail_run().is_err());assert_eq!(fs::read(&path).unwrap(),b"private original");assert_eq!(fs::metadata(&path).unwrap().permissions().mode(),mode);assert_eq!(fs::metadata(&path).unwrap().modified().unwrap(),time);assert!(!absent.exists());assert!(!journal.exists());
    }
    #[test]
    fn projection_v2_failed_recovery_keeps_journal_and_retries_exact_original_mode() {
        use std::os::unix::fs::PermissionsExt;
        let d=tempfile::tempdir().unwrap();let source=d.path().join("source");fs::create_dir(&source).unwrap();let path=source.join("original");let absent=source.join("new");let journal=d.path().join("journal");
        fs::write(&path,b"original").unwrap();fs::set_permissions(&path,fs::Permissions::from_mode(0o664)).unwrap();let mode=fs::metadata(&path).unwrap().permissions().mode();let time=fs::metadata(&path).unwrap().modified().unwrap();
        let mut p=Projection::new(journal.clone()).unwrap();p.put(&path,b"temporary").unwrap();p.put(&absent,b"temporary new").unwrap();std::mem::forget(p);fs::remove_file(&path).unwrap();fs::create_dir(&path).unwrap();let raw=fs::read(&journal).unwrap();
        assert!(recover(&journal,&source).is_err());assert!(path.is_dir());assert_eq!(fs::read(&journal).unwrap(),raw);fs::remove_dir(&path).unwrap();recover(&journal,&source).unwrap();assert_eq!(fs::read(&path).unwrap(),b"original");assert_eq!(fs::metadata(&path).unwrap().permissions().mode(),mode);assert_eq!(fs::metadata(&path).unwrap().modified().unwrap(),time);assert!(!absent.exists());assert!(!journal.exists());
    }
    #[test]
    fn projection_v2_rejects_legacy_or_incomplete_journals_before_source_mutation() {
        use std::os::unix::fs::PermissionsExt;
        let d=tempfile::tempdir().unwrap();let source=d.path().join("source");fs::create_dir(&source).unwrap();let path=source.join("original");let journal=d.path().join("journal");fs::write(&path,b"current unchanged").unwrap();let mode=fs::metadata(&path).unwrap().permissions().mode();let time=fs::metadata(&path).unwrap().modified().unwrap();
        let row=serde_json::json!({"path":path,"bytes":b"old".to_vec(),"modified":time,"permissions_mode":mode});let valid=serde_json::json!({"schema_version":2,"originals":[row.clone()]});let mut bad=vec![serde_json::json!([{"path":path,"bytes":b"old".to_vec(),"modified":time}])];
        let mut v=valid.clone();v["schema_version"]=serde_json::json!(1);bad.push(v);let mut v=valid.clone();v["originals"][0].as_object_mut().unwrap().remove("permissions_mode");bad.push(v);let mut v=valid.clone();v["originals"][0]["permissions_mode"]=serde_json::Value::Null;bad.push(v);let mut v=valid.clone();v["extra"]=serde_json::json!(true);bad.push(v);let mut v=valid.clone();v["originals"][0]["extra"]=serde_json::json!(true);bad.push(v);let mut v=valid.clone();v["originals"][0]["permissions_mode"]=serde_json::json!(0o040755);bad.push(v);let mut v=valid.clone();v["originals"][0]["modified"]=serde_json::Value::Null;bad.push(v);let mut v=valid.clone();v["originals"]=serde_json::json!([row.clone(),row]);bad.push(v);let mut v=valid.clone();v["originals"][0]["path"]=serde_json::json!(source.join("../escape"));bad.push(v);
        for value in bad {let raw=serde_json::to_vec(&value).unwrap();fs::write(&journal,&raw).unwrap();assert!(recover(&journal,&source).is_err());assert_eq!(fs::read(&path).unwrap(),b"current unchanged");assert_eq!(fs::metadata(&path).unwrap().permissions().mode(),mode);assert_eq!(fs::metadata(&path).unwrap().modified().unwrap(),time);assert_eq!(fs::read(&journal).unwrap(),raw);}
        let row_raw=serde_json::to_string(&valid["originals"][0]).unwrap();let valid_raw=serde_json::to_string(&valid).unwrap();
        let duplicate_schema=valid_raw.replacen("\"schema_version\":", "\"schema_version\":2,\"schema_version\":", 1);
        let duplicate_path=row_raw.replacen("\"path\":", &format!("\"path\":{},\"path\":",serde_json::to_string(&path).unwrap()),1);
        let duplicate_mode=row_raw.replacen("\"permissions_mode\":", &format!("\"permissions_mode\":{mode},\"permissions_mode\":"),1);
        for raw in [duplicate_schema,format!("{{\"schema_version\":2,\"originals\":[{duplicate_path}]}}"),format!("{{\"schema_version\":2,\"originals\":[{duplicate_mode}]}}")]{fs::write(&journal,&raw).unwrap();assert!(recover(&journal,&source).is_err());assert_eq!(fs::read(&path).unwrap(),b"current unchanged");assert_eq!(fs::metadata(&path).unwrap().permissions().mode(),mode);assert_eq!(fs::metadata(&path).unwrap().modified().unwrap(),time);assert_eq!(fs::read(&journal).unwrap(),raw.as_bytes());}
    }
    #[test]
    fn projection_v2_refuses_symlink_original_without_reading_or_mutating_target() {
        use std::os::unix::fs::symlink;
        let d=tempfile::tempdir().unwrap();let target=d.path().join("target");fs::write(&target,b"unmodified").unwrap();let alias=d.path().join("alias");symlink(&target,&alias).unwrap();let journal=d.path().join("journal");let mut p=Projection::new(journal.clone()).unwrap();assert!(p.put(&alias,b"projected").is_err());assert_eq!(fs::read(&target).unwrap(),b"unmodified");assert!(!journal.exists());assert!(fs::symlink_metadata(&alias).unwrap().file_type().is_symlink());
    }



    #[test]
    fn production_soong_commands_fix_user_for_every_normal_entry() {
        let source = Path::new("/not-executed/source");
        let out = Path::new("/not-executed/out");
        let work = Path::new("/not-executed/work");
        for (mode, targets) in [
            (SoongDependencyMode::Strict, TARGETS),
            (SoongDependencyMode::NativeBridgeTargetClosure, &["droidloom-native-bridge"][..]),
            (SoongDependencyMode::NativeEngineTargetClosure, &["libberberis_arm64", "berberis_arm64_host_tests"][..]),
            (SoongDependencyMode::AudioApexTargetClosure, &["com.android.hardware.audio.droidloom"][..]),
            (SoongDependencyMode::MinigbmTargetClosure, &["libminigbm_gralloc"][..]),
        ] {
            for product in ["droidloom_x86_64", "droidloom_arm64"] {
                let selected = selected_soong_targets(mode, targets, out, product).unwrap();
                let mut command = production_soong_command(source, out, work, product, 6, &selected).unwrap();
                configure_soong_dependencies(&mut command, mode, targets).unwrap();
                assert_eq!(command.get_program(), out.join("soong_ui").as_os_str());
                assert_eq!(command.get_current_dir(), Some(source));
                for (key, value) in [("TARGET_BUILD_VARIANT", "user"),
                                     ("TARGET_RELEASE", "cp2a"), ("TARGET_PRODUCT", product)] {
                    assert!(command.get_envs().any(|(k, v)| k == key
                        && v == Some(std::ffi::OsStr::new(value))), "{mode:?}: {key}");
                }
            }
        }
    }

    #[test]
    fn production_soong_command_preserves_exact_targets_and_dependency_mode() {
        let source = Path::new("/not-executed/source");
        let out = Path::new("/not-executed/out");
        let work = Path::new("/not-executed/work");
        for (mode, targets) in [
            (SoongDependencyMode::Strict, TARGETS),
            (SoongDependencyMode::AudioApexTargetClosure, &["com.android.hardware.audio.droidloom"][..]),
            (SoongDependencyMode::NativeEngineTargetClosure, &["libberberis_arm64", "berberis_arm64_host_tests"][..]),
        ] {
            let selected = selected_soong_targets(mode, targets, out, "droidloom_x86_64").unwrap();
            let mut command = production_soong_command(source, out, work, "droidloom_x86_64", 6, &selected).unwrap();
            configure_soong_dependencies(&mut command, mode, targets).unwrap();
            let mut expected = vec![std::ffi::OsString::from("--make-mode"), std::ffi::OsString::from("-j6")];
            expected.extend(selected.iter().map(|p| p.as_os_str().to_owned()));
            if mode == SoongDependencyMode::NativeEngineTargetClosure {
                expected.push(std::ffi::OsString::from("--soong-only"));
            }
            assert_eq!(command.get_args().map(|v| v.to_owned()).collect::<Vec<_>>(), expected);
            let missing = if mode == SoongDependencyMode::NativeEngineTargetClosure { "true" } else { "false" };
            assert!(command.get_envs().any(|(k, v)| k == "ALLOW_MISSING_DEPENDENCIES"
                && v == Some(std::ffi::OsStr::new(missing))));
        }
    }

    #[test]
    fn production_soong_lunch_choices_match_fixed_release_and_variant() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        for product in ["droidloom_x86_64", "droidloom_arm64"] {
            let text = fs::read_to_string(repo.join(format!("android/device/{product}/AndroidProducts.mk"))).unwrap();
            let choices = text.split_once("COMMON_LUNCH_CHOICES := \\\n").unwrap().1;
            let choices = choices.split_whitespace().collect::<Vec<_>>();
            assert_eq!(choices, [format!("{product}-{PRODUCTION_TARGET_RELEASE}-{PRODUCTION_BUILD_VARIANT}")]);
            assert!(!text.contains("userdebug") && !text.contains("-eng"));
        }
    }

    #[cfg(unix)]
    #[test]
    fn production_soong_inherited_environment_cannot_select_debug() {
        const PROBE: &str = "DROIDLOOM_TEST_PRODUCTION_VARIANT_CHILD";
        if std::env::var_os(PROBE).is_none() {
            for inherited in ["userdebug", "eng"] {
                let child = Command::new(std::env::current_exe().unwrap())
                    .args(["--exact", "android::tests::production_soong_inherited_environment_cannot_select_debug", "--test-threads=1"])
                    .env(PROBE, "1")
                    .env("TARGET_BUILD_VARIANT", inherited)
                    .env("TARGET_RELEASE", "not-the-pinned-release")
                    .env("TARGET_PRODUCT", "not-the-selected-product")
                    .env("ALLOW_MISSING_DEPENDENCIES", "true")
                    .output().unwrap();
                assert!(child.status.success(), "{}\n{}", String::from_utf8_lossy(&child.stdout), String::from_utf8_lossy(&child.stderr));
                assert!(String::from_utf8_lossy(&child.stdout).contains("1 passed; 0 failed"));
            }
            return;
        }
        assert!(matches!(std::env::var("TARGET_BUILD_VARIANT").as_deref(), Ok("userdebug" | "eng")));
        use std::os::unix::fs::PermissionsExt;
        let d = tempfile::tempdir().unwrap();
        let executable = d.path().join("soong_ui");
        // A fixed environment observer, not Soong and not a build qualification.
        fs::write(&executable, b"#!/bin/sh\nset -eu\nprintf '%s\\n' \"$TARGET_BUILD_VARIANT\" \"$TARGET_RELEASE\" \"$TARGET_PRODUCT\" \"$ALLOW_MISSING_DEPENDENCIES\"\n").unwrap();
        fs::set_permissions(&executable, fs::Permissions::from_mode(0o700)).unwrap();
        let selected = [PathBuf::from("com.android.hardware.audio.droidloom")];
        let mut command = production_soong_command(d.path(), d.path(), d.path(), "droidloom_x86_64", 6, &selected).unwrap();
        configure_soong_dependencies(&mut command, SoongDependencyMode::AudioApexTargetClosure,
            &["com.android.hardware.audio.droidloom"]).unwrap();
        let observed = command.output().unwrap();
        assert!(observed.status.success());
        assert!(observed.stderr.is_empty());
        assert_eq!(observed.stdout, b"user\ncp2a\ndroidloom_x86_64\nfalse\n");
    }

    #[test]
    fn ordinary_pair_vkms_maintenance_metadata_preserves_consumers_and_recovers() {
        let original = include_bytes!("../../../android/native-generation-pair/original-vkms-controller.Android.bp");
        assert_eq!(original.len(), 1522);
        for interrupted in [false, true] {
            let temp = tempfile::tempdir().unwrap();
            let source = temp.path().join("source");
            let path = source.join("device/google/cuttlefish/guest/commands/vkms_controller/Android.bp");
            let unselected = source.join("device/google/cuttlefish/tests/graphics/display/Android.bp");
            write(&path, original).unwrap();
            write(&unselected, b"unselected sibling must remain unchanged\n").unwrap();
            let before_time = fs::metadata(&path).unwrap().modified().unwrap();
            assert_eq!(hash(&path).unwrap(), "fad92f331030a22d22d989e4df4f7b6fdd90f2d11b702f90fd1d26304783b45d");
            let journal = temp.path().join("projection.json");
            let mut projection = Projection::new(journal.clone()).unwrap();
            crate::native_generation_pair_build::project_vkms_maintenance_metadata(
                &source, &mut projection).unwrap();
            let effective = fs::read_to_string(&path).unwrap();
            let original_text = std::str::from_utf8(original).unwrap();
            assert_eq!(effective.len(), 1473);
            assert_eq!(hash(&path).unwrap(), "bd556a4385b92f6808a8d9df94f118a8b2f93e35a0598fef636fe0f91c075b7f");
            let consumer_start = original_text.find("cc_binary {").unwrap();
            assert!(effective.ends_with(&original_text[consumer_start..]));
            assert_eq!(effective, original_text.replacen(
                "    default_team: \"trendy_team_desktop_display\",\n", "", 1));
            let inventory = projection.effective_inventory(temp.path(), &source).unwrap();
            assert_eq!(inventory["files"].as_object().unwrap().len(), 1);
            assert!(inventory["patches"].as_object().unwrap().is_empty());
            let metadata = crate::native_generation_pair_build::vkms_maintenance_metadata_inputs(
                &source, &inventory).unwrap();
            assert_eq!(metadata["runtime_security_policy_changed"], false);
            assert!(crate::native_generation_pair_build::vkms_maintenance_metadata_inputs(
                &source, &serde_json::json!({"files": {}})).is_err());
            if interrupted {
                // Preserve a real interrupted journal for the normal recovery API.
                std::mem::forget(projection);
                recover(&journal, &source).unwrap();
            } else {
                projection.restore().unwrap();
            }
            assert_eq!(fs::read(&path).unwrap(), original);
            assert_eq!(fs::metadata(&path).unwrap().modified().unwrap(), before_time);
            assert_eq!(fs::read(&unselected).unwrap(), b"unselected sibling must remain unchanged\n");
            assert!(!journal.exists());
        }
    }

    #[test]
    fn ordinary_pair_vkms_maintenance_metadata_rejects_untrusted_input_without_mutation() {
        let original = include_bytes!("../../../android/native-generation-pair/original-vkms-controller.Android.bp");
        let before = std::str::from_utf8(original).unwrap();
        for variant in ["edited-source", "already-projected", "symlink", "hardlink"] {
            let temp = tempfile::tempdir().unwrap();
            let source = temp.path().join("source");
            let path = source.join("device/google/cuttlefish/guest/commands/vkms_controller/Android.bp");
            let target = temp.path().join("protected-original.bp");
            write(&target, original).unwrap();
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            match variant {
                "edited-source" => write(&path, before.replace("main.cpp", "evil.cpp")).unwrap(),
                "already-projected" => write(&path, before.replacen(
                    "    default_team: \"trendy_team_desktop_display\",\n", "", 1)).unwrap(),
                "symlink" => std::os::unix::fs::symlink(&target, &path).unwrap(),
                "hardlink" => fs::hard_link(&target, &path).unwrap(),
                _ => unreachable!(),
            }
            let snapshot = fs::read(&path).unwrap();
            let journal = temp.path().join("projection.json");
            let mut projection = Projection::new(journal.clone()).unwrap();
            assert!(crate::native_generation_pair_build::project_vkms_maintenance_metadata(
                &source, &mut projection).is_err(), "{variant}");
            assert_eq!(fs::read(&path).unwrap(), snapshot);
            assert_eq!(fs::read(&target).unwrap(), original);
            assert!(!journal.exists());
        }
    }

    #[test]
    fn ordinary_pair_provider_bound_preserves_existing_writer_and_restores() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let original = include_bytes!("../tests/fixtures/native-pair-graph/context.original.go");
        let soong_original = include_bytes!("../tests/fixtures/native-pair-graph/soong.original.go");
        let bootstrap_original = include_bytes!("../tests/fixtures/native-pair-graph/bootstrap-command.original.go");
        for ordinary_pair in [false, true] {
            let temp = tempfile::tempdir().unwrap();
            let source = temp.path().join("source");
            let context = source.join("build/blueprint/context.go");
            let soong = source.join("build/soong/ui/build/soong.go");
            let bootstrap = source.join("build/blueprint/bootstrap/command.go");
            write(&context, original).unwrap();
            write(&soong, soong_original).unwrap();
            write(&bootstrap, bootstrap_original).unwrap();
            let context_time = fs::metadata(&context).unwrap().modified().unwrap();
            let soong_time = fs::metadata(&soong).unwrap().modified().unwrap();
            let bootstrap_time = fs::metadata(&bootstrap).unwrap().modified().unwrap();
            let journal = temp.path().join("projection.json");
            let mut p = Projection::new(journal.clone()).unwrap();
            // Reproduce the exact pre-existing ordinary pair projection order.
            p.patch(&source, "build/soong", &repo.join(
                "android/apex-compat/0008-soong-leaf-go-memory-budget.patch")).unwrap();
            p.patch(&source, "build/blueprint", &repo.join(
                "android/apex-compat/0009-blueprint-stream-uncached-module-actions.patch")).unwrap();
            let before_context = fs::read(&context).unwrap();
            let before_soong = fs::read(&soong).unwrap();
            assert_eq!(hash(&context).unwrap(), "1559969a55db1b682401c01264dd8ba96fa224781c3af277f0996a5050f7c9fa");
            project_ordinary_pair_graph_resources(&repo, &source, &mut p,
                ordinary_pair, SoongDependencyMode::Strict).unwrap();
            let inventory = p.effective_inventory(&repo, &source).unwrap();
            assert_eq!(inventory["files"].as_object().unwrap().len(), if ordinary_pair { 3 } else { 2 });
            assert_eq!(inventory["patches"].as_object().unwrap().len(), if ordinary_pair { 4 } else { 2 });
            if ordinary_pair {
                assert_eq!(hash(&context).unwrap(), "38f6ae2fa339f04834241b20d4185bc091aa9e16cb894030927bdc58a8f67182");
                assert_eq!(hash(&soong).unwrap(), "0b855ddee1c4e62203968104f22e949b50bf0ba323f7d2f7335cf84c9f9ec2a8");
                assert_eq!(hash(&bootstrap).unwrap(), "705fa207568d27eaeeeb825646956934b63c6a4d5240c6d6caf57a0978e3837c");
                let expected = String::from_utf8(before_context).unwrap().replacen(
                    "parallelVisitSimple(c.iterateAllVariants(), 1000,",
                    "parallelVisitSimple(c.iterateAllVariants(), parallelVisitLimit,", 1);
                assert_eq!(fs::read_to_string(&context).unwrap(), expected);
                let expected = String::from_utf8(before_soong).unwrap().replacen(
                    "\tinvocationEnv[\"GOMEMLIMIT\"] = \"5GiB\"\n",
                    "\tinvocationEnv[\"GOMEMLIMIT\"] = \"5GiB\"\n\tinvocationEnv[\"GODEBUG\"] = \"gctrace=1\"\n\tinvocationEnv[\"GOMAXPROCS\"] = \"2\"\n\tinvocationEnv[\"GOGC\"] = \"50\"\n", 1);
                assert_eq!(fs::read_to_string(&soong).unwrap(), expected);
                assert!(project_ordinary_pair_graph_resources(&repo, &source, &mut p,
                    true, SoongDependencyMode::Strict).is_err());
            } else {
                assert_eq!(fs::read(&context).unwrap(), before_context);
                assert_eq!(fs::read(&soong).unwrap(), before_soong);
                assert_eq!(fs::read(&bootstrap).unwrap(), bootstrap_original);
            }
            p.restore().unwrap();
            assert_eq!(fs::read(&context).unwrap(), original);
            assert_eq!(fs::read(&soong).unwrap(), soong_original);
            assert_eq!(fs::read(&bootstrap).unwrap(), bootstrap_original);
            assert_eq!(fs::metadata(&context).unwrap().modified().unwrap(), context_time);
            assert_eq!(fs::metadata(&soong).unwrap().modified().unwrap(), soong_time);
            assert_eq!(fs::metadata(&bootstrap).unwrap().modified().unwrap(), bootstrap_time);
            assert!(!journal.exists());
        }
    }

    #[test]
    fn ordinary_pair_provider_bound_rejects_wrong_mode_and_drift_before_writes() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let original = include_bytes!("../tests/fixtures/native-pair-graph/context.original.go");
        let soong_original = include_bytes!("../tests/fixtures/native-pair-graph/soong.original.go");
        let bootstrap_original = include_bytes!("../tests/fixtures/native-pair-graph/bootstrap-command.original.go");
        for mode in [SoongDependencyMode::NativeBridgeTargetClosure,
            SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::AudioApexTargetClosure,
            SoongDependencyMode::MinigbmTargetClosure] {
            let temp = tempfile::tempdir().unwrap();
            let source = temp.path().join("source");
            let journal = temp.path().join("projection.json");
            let mut p = Projection::new(journal.clone()).unwrap();
            project_ordinary_pair_graph_resources(&repo, &source, &mut p, false, mode).unwrap();
            assert!(p.originals.is_empty());
            assert!(!journal.exists());
            assert!(project_ordinary_pair_graph_resources(&repo, &source, &mut p, true, mode).is_err());
            assert!(p.originals.is_empty());
            assert!(!journal.exists());
        }
        for drift in ["context", "soong", "bootstrap"] {
            let temp = tempfile::tempdir().unwrap();
            let source = temp.path().join("source");
            let context = source.join("build/blueprint/context.go");
            let soong = source.join("build/soong/ui/build/soong.go");
            let bootstrap = source.join("build/blueprint/bootstrap/command.go");
            write(&context, original).unwrap();
            write(&soong, soong_original).unwrap();
            write(&bootstrap, bootstrap_original).unwrap();
            let journal = temp.path().join("projection.json");
            let mut prior = Projection::new(journal.clone()).unwrap();
            prior.patch(&source, "build/soong", &repo.join(
                "android/apex-compat/0008-soong-leaf-go-memory-budget.patch")).unwrap();
            prior.patch(&source, "build/blueprint", &repo.join(
                "android/apex-compat/0009-blueprint-stream-uncached-module-actions.patch")).unwrap();
            let path = match drift { "context" => &context, "soong" => &soong, _ => &bootstrap };
            write(path, fs::read_to_string(path).unwrap() + "\n// drift\n").unwrap();
            let changed = fs::read(path).unwrap();
            let before = fs::read(&journal).unwrap();
            assert!(project_ordinary_pair_graph_resources(&repo, &source, &mut prior,
                true, SoongDependencyMode::Strict).is_err());
            assert_eq!(fs::read(path).unwrap(), changed);
            assert_eq!(fs::read(&journal).unwrap(), before);
            prior.restore().unwrap();
            assert_eq!(fs::read(&context).unwrap(), original);
            assert_eq!(fs::read(&soong).unwrap(), soong_original);
            if drift == "bootstrap" {
                assert_eq!(fs::read(&bootstrap).unwrap(), changed);
            } else {
                assert_eq!(fs::read(&bootstrap).unwrap(), bootstrap_original);
            }
            assert!(!journal.exists());
        }
    }

    #[test]
    fn ordinary_pair_gc_observation_keeps_target_and_dependency_configuration() {
        for ordinary_pair in [false, true] {
            let mut command = Command::new("fixture-soong");
            command.args(["--make-mode", "-j2", "libberberis_arm64", "com.android.art"]);
            configure_soong_dependencies(&mut command, SoongDependencyMode::Strict,
                crate::native_generation_pair_build::TARGETS).unwrap();
            let before_args: Vec<_> = command.get_args().map(|s| s.to_owned()).collect();
            configure_ordinary_pair_graph_observation(&mut command, ordinary_pair);
            let after_args: Vec<_> = command.get_args().map(|s| s.to_owned()).collect();
            assert_eq!(before_args, after_args);
            let envs: std::collections::BTreeMap<_, _> = command.get_envs()
                .map(|(k,v)| (k.to_string_lossy().into_owned(), v.map(|x| x.to_string_lossy().into_owned()))).collect();
            assert_eq!(envs.get("ALLOW_MISSING_DEPENDENCIES"), Some(&Some("false".to_owned())));
            let expected = if ordinary_pair { Some(Some("1".to_owned())) } else { None };
            assert_eq!(envs.get("SOONG_UNBUFFERED_OUTPUT"), expected.as_ref());
            assert!(!envs.contains_key("SOONG_PARTIAL_ANALYSIS"));
        }
    }

    const SHARED_PROVIDER_FIXTURES: &[(&str, &str, &str)] = &[
        ("frameworks/base/packages/SystemUI/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/SystemUI.Android.bp"),
         "d6e2c5813cd1b8e5823fb11a29612ba0369c843f17b226ec076894a6c7a1451c"),
        (TYPED_INGRESS_SYSTEMUI_TESTS_BLUEPRINT,
         include_str!("../../../android/native-role-ingress/provider-fixtures/SystemUI-tests.Android.bp"),
         "42118873220b0cc4d07e21a961052ddd5d81ab67be8df5d7c9dba9bd966aaeb5"),
        (TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT,
         include_str!("../../../android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp"),
         "d73b00f17a80375d2d59e408088c5e875c3311bd0f7487b117d4b8d28f7cff93"),
        ("platform_testing/libraries/motion/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/motion.Android.bp"),
         "23e1392f716fbf78efb7b0ea5281c3cf70b4547b6aa41af8cf79df495eace098"),
        ("platform_testing/libraries/screenshot/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/screenshot.Android.bp"),
         "6249d22918a5c2d02a5efc6e20013e75f0eabb0c8e492f40d1e83d4009409007"),
        ("platform_testing/libraries/runner/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/runner.Android.bp"),
         "fcc2907dfabd23aafa5c63c4b2825769b85884a7f6feab3e3ffeb33e07cb9dfd"),
        ("external/robolectric/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-root.Android.bp"),
         "0c1dbf256397da0814954949ae33b53952ad2c2ae97980a7947ea262e4619359"),
        ("external/TestParameterInjector/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/test-parameter.Android.bp"),
         "8c968ba42fd26a4fca996740f91164c5d339616ed04b69b34c79bd3464d1b744"),
        ("test/robolectric-extensions/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-aosp-plugins.Android.bp"),
         "7f784da6379787a862ecd71c32d5f021314bc6705e9e7a6d4bb8360c3ebb5c30"),
        ("packages/services/Car/car-lib/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/car-lib.Android.bp"),
         "690a87d0a8ce5f3bd628770c7c8d25691290ccc7a85dfbdeeece69facb04647d"),
        ("packages/services/Car/car-builtin-lib/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/car-builtin.Android.bp"),
         "a9b66992fe7484f49d6c809f87f6dc481aba9aef75a797bb7e7638f02199cfc8"),
        ("packages/services/Car/car-lib/jni/large-parcelable/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/car-jni.Android.bp"),
         "8baf86d459edd9e216e9d6b5649b1bc560d65c9b8b9a8f30eb44581079466c8a"),
        ("external/icu/icu4j/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/icu4j.Android.bp"),
         "fa4314ac6dead0e1138631c6649c5980e0222e5a54cb523ac2db27809b2b7dc6"),
        ("external/robolectric/pluginapi/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-pluginapi.Android.bp"),
         "2c4d145186abf766583c132dcfb902ce21bb409ab5f5ee3904fcae5214ad518a"),
        ("external/robolectric/resources/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-resources.Android.bp"),
         "881e27bf7db87b8eec7e6236d3a871d84b12af26c53b9a9fb3f74a418e8b9a66"),
        ("external/robolectric/robolectric/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-robolectric.Android.bp"),
         "cabde3f0683d9515a10e155b778c3805122d07a8a6d3d94a71367abac63bfc36"),
        ("external/robolectric/sandbox/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-sandbox.Android.bp"),
         "7f1364ab109bec260809fa92a9d2a767128179f0986dc609bce8f56d669bdb14"),
        ("external/robolectric/shadowapi/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-shadowapi.Android.bp"),
         "76f38523ee0b8684edcb22c508b329f1e55b93ff3316047fe0ce57efc2b035ad"),
        ("external/robolectric/utils/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-utils.Android.bp"),
         "a8b6af937d2d67d7f1ee3ecd2032976f6c93264ed5dad438f75560ff16df9111"),
        ("external/robolectric/shadows/httpclient/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-shadows-httpclient.Android.bp"),
         "75572b9618806850fc596f36356316879b0ed2b9ec57376b459b357d5c3dc006"),
        ("external/robolectric/shadows/versioning/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-shadows-versioning.Android.bp"),
         "8de2263cf57483ae007f85835f6401bdb40eb061d8dff62ac8ae206b03d33d28"),
        ("external/robolectric/utils/reflector/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-utils-reflector.Android.bp"),
         "71eb852c68f73ec03daae1a7b0d5a40aae2ca3ed64d19c3f941452f84b034fca"),
        ("external/robolectric/processor/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-processor.Android.bp"),
         "a371760f74de15214ff0c13db200d09231b00472e87c8784aaf40d5ca423829b"),
        ("test/robolectric-extensions/clearcut-junit-listener/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/clearcut-junit-listener.Android.bp"),
         "2bd33a3e44d8b60dd8296aa892791f85cf128ba31bf3547cc8a796f476b138dc"),
        ("tools/asuite/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/asuite-proto.Android.bp"),
         "8d8ed13a96c779c96ce59c848c189a3fdfad5202371ad4317d9f36675b4843ab"),
        ("tools/asuite/atest/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/asuite-atest-metadata.Android.bp"),
         "cf7439663957b768c8a14064f65637122fb4ad5788216a67d8bd9dad8d7215ca"),
        ("packages/services/Car/cpp/vhal/client/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/car-vhal-client.Android.bp"),
         "19c13fe0d2c46091266998a8a39dd8eee9235b05abb8b4772db026ec4290d12d"),
        ("packages/services/Car/cpp/car_binder_lib/largeParcelable/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/car-large-parcelable.Android.bp"),
         "7d1e2ed8e52279903ab3f15ef4e4ff3ede2d41a03fc3903006bf73685167f8d9"),
        ("packages/modules/NeuralNetworks/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/neuralnetworks-root.Android.bp"),
         "e063e7c1b86cf20657d591f83432371ff9465c3706edf56fbd0686f0753c0d12"),
        ("packages/modules/NeuralNetworks/common/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/neuralnetworks-common.Android.bp"),
         "9e4477760e24bc5c7c5b44cf0bf20010bab8e09eee282dde4fd114d1b76a3dad"),
        ("packages/modules/NeuralNetworks/common/types/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/neuralnetworks-types.Android.bp"),
         "3c4f7ac57497efa7e5f7a40b20a8cb5ea70a8587258fcc89b1472f026ca824d1"),
    ];


    const REAL_SERIALSERVICE_BLUEPRINT: &str = r###"// Copyright 2025 The Android Open Source Project
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package {
    default_team: "trendy_team_webapps_cros_android",
}

rust_defaults {
    name: "serialservice_defaults",
    proc_macros: [
        "libasync_trait",
    ],
    rustlibs: [
        "android.hardware.serialservice-rust",
        "libanyhow",
        "libatrace_rust",
        "libbinder_rs",
        "libbinder_tokio_rs",
        "libfutures",
        "liblog_rust",
        "liblogger",
        "libmockall",
        "libnix",
        "librustutils",
        "libtokio",
        "libtokio_stream",
        "libtracing",
        "libueventd",
    ],
}

rust_binary {
    name: "serialservice",
    srcs: ["rust/service.rs"],
    system_ext_specific: true,
    defaults: ["serialservice_defaults"],
    init_rc: ["serialservice.rc"],
    rustlibs: [
        "libandroid_hardware_serial_flags_rust",
        "libatrace_tracing_subscriber",
        "libserialservice",
        "libtracing_subscriber",
    ],
    prefer_rlib: true,
    required: ["serialservice_overlay"],
}

rust_library {
    name: "libserialservice",
    crate_name: "serialservice",
    crate_root: "rust/lib.rs",
    system_ext_specific: true,
    defaults: ["serialservice_defaults"],
    init_rc: ["serialservice.rc"],
}

rust_test {
    name: "serialservice_test",
    crate_name: "serialservice",
    crate_root: "rust/lib.rs",
    defaults: ["serialservice_defaults"],
    srcs: ["rust/*.rs"],
    test_options: {
        unit_test: true,
    },
    test_suites: ["device-tests"],
    rustlibs: [
        "libandroid_logger",
        "libserialservice",
        "libtempfile",
        "libtokio_test",
    ],
}

rust_fuzz {
    name: "serialservice_fuzzer",
    srcs: ["rust/service_fuzzer.rs"],
    defaults: [
        "serialservice_defaults",
        "service_fuzzer_defaults_rs",
    ],
    rustlibs: [
        "libserialservice",
    ],
}
"###;

    #[test]
    fn normal_serialservice_projection_preserves_real_fuzzer_and_dependencies() {
        let original = REAL_SERIALSERVICE_BLUEPRINT;
        let expected_bodies = [
            r###"rust_defaults {
    name: "serialservice_defaults",
    proc_macros: [
        "libasync_trait",
    ],
    rustlibs: [
        "android.hardware.serialservice-rust",
        "libanyhow",
        "libatrace_rust",
        "libbinder_rs",
        "libbinder_tokio_rs",
        "libfutures",
        "liblog_rust",
        "liblogger",
        "libmockall",
        "libnix",
        "librustutils",
        "libtokio",
        "libtokio_stream",
        "libtracing",
        "libueventd",
    ],
}
"###,
            r###"rust_library {
    name: "libserialservice",
    crate_name: "serialservice",
    crate_root: "rust/lib.rs",
    system_ext_specific: true,
    defaults: ["serialservice_defaults"],
    init_rc: ["serialservice.rc"],
}
"###,
            r###"rust_fuzz {
    name: "serialservice_fuzzer",
    srcs: ["rust/service_fuzzer.rs"],
    defaults: [
        "serialservice_defaults",
        "service_fuzzer_defaults_rs",
    ],
    rustlibs: [
        "libserialservice",
    ],
}
"###,
        ];
        for typed in [false, true] {
            let projected = shared_root_blueprint(
                "frameworks/native/services/serialservice/Android.bp", original, typed).unwrap();
            let mut expected = metadata_only(original).unwrap();
            for body in expected_bodies {
                expected.push('\n');
                expected.push_str(body);
            }
            assert_eq!(projected, expected);
            assert!(!projected.contains("rust_binary {\n    name: \"serialservice\","));
            assert!(!projected.contains("rust_test {\n    name: \"serialservice_test\","));
            assert!(projected.contains("\"service_fuzzer_defaults_rs\""));
            assert!(projected.contains("\"android.hardware.serialservice-rust\""));
        }
    }

    #[test]
    fn normal_serialservice_projection_rejects_source_drift() {
        for changed in [
            REAL_SERIALSERVICE_BLUEPRINT.replace("serialservice_fuzzer", "changed_fuzzer"),
            format!("{}\n", REAL_SERIALSERVICE_BLUEPRINT),
        ] {
            assert!(shared_root_blueprint(
                "frameworks/native/services/serialservice/Android.bp", &changed, false).is_err());
        }
    }

    #[test]
    fn normal_systemui_projection_keeps_real_dagger_defaults() {
        let original = include_str!(
            "../../../android/native-role-ingress/provider-fixtures/SystemUI.Android.bp");
        let expected = r#"java_defaults {
    name: "SystemUI_compile_dagger",

    plugins: ["dagger2-compiler"],

    annotation_processor_flags: [
        "dagger.fastInit=ENABLED",
        "dagger.explicitBindingConflictsWithInject=ERROR",
        "dagger.useBindingGraphFix=ENABLED",
    ],

    defaults_visibility: ["//visibility:public"],
}
"#;
        for typed in [false, true] {
            let projected = shared_root_blueprint(
                "frameworks/base/packages/SystemUI/Android.bp", original, typed).unwrap();
            assert!(projected.starts_with(metadata_only(original).unwrap().as_str()));
            assert_eq!(projected.matches(expected).count(), 1);
            assert!(!projected.contains("name: \"SystemUI-core\""));
        }
    }

    #[test]
    fn normal_systemui_projection_rejects_drift_and_keeps_other_roots() {
        let original = include_str!(
            "../../../android/native-role-ingress/provider-fixtures/SystemUI.Android.bp");
        let changed = original.replace("dagger.fastInit=ENABLED", "dagger.fastInit=DISABLED");
        assert!(shared_root_blueprint(
            "frameworks/base/packages/SystemUI/Android.bp", &changed, false).is_err());
        let other = "package {\n    default_applicable_licenses: [\"license\"],\n}\njava_defaults {\n    name: \"other\",\n}\n";
        assert_eq!(shared_root_blueprint("packages/apps/Settings/Android.bp", other, false).unwrap(),
                   metadata_only(other).unwrap());
    }

    #[test]
    fn typed_shared_provider_projection_keeps_exact_upstream_bodies_and_metadata() {
        use sha2::{Digest, Sha256};
        for (relative, original, expected_sha) in SHARED_PROVIDER_FIXTURES {
            let projected = typed_ingress_shared_blueprint(relative, original).unwrap();
            assert!(projected.starts_with(metadata_only(original).unwrap().as_str()));
            assert_eq!(&format!("{:x}", Sha256::digest(projected.as_bytes())), expected_sha);
            assert!(!projected.contains("name: \"SystemUI-core\""));
            assert!(!projected.contains("name: \"PlatformMotionTestingRoboApplication\""));
            assert!(!projected.contains("name: \"platform-screenshot-diff-test\""));
        }
    }

    fn ordinary_pair_provider_fixtures() -> Vec<(&'static str, &'static str)> {
        let mut fixtures: Vec<_> = SHARED_PROVIDER_FIXTURES.iter()
            .filter(|row| matches!(row.0,
                "frameworks/base/packages/SystemUI/Android.bp" |
                "frameworks/base/packages/SystemUI/tests/Android.bp" |
                "packages/modules/NeuralNetworks/common/Android.bp" |
                "packages/services/Car/car-lib/Android.bp" |
                "tools/asuite/Android.bp" |
                "tools/asuite/atest/Android.bp"))
            .map(|row| (row.0, row.1)).collect();
        fixtures.extend([
            ("frameworks/base/libs/WindowManager/Shell/Android.bp", include_str!("../../../android/native-generation-pair/provider-fixtures/Shell.Android.bp")),
            ("packages/apps/Launcher3/Android.bp", include_str!("../../../android/native-generation-pair/provider-fixtures/Launcher3.Android.bp")),
            ("packages/apps/Settings/Android.bp", include_str!("../../../android/native-generation-pair/provider-fixtures/Settings.Android.bp")),
            ("packages/modules/ConfigInfrastructure/aconfigd/Android.bp", include_str!("../../../android/native-generation-pair/provider-fixtures/aconfigd.Android.bp")),
        ]);
        assert_eq!(fixtures.len(), 10);
        fixtures
    }

    #[test]
    fn ordinary_pair_providers_keep_all_ten_original_bodies_only_for_the_pair() {
        for (relative, original) in ordinary_pair_provider_fixtures() {
            assert_eq!(ordinary_pair_provider_blueprint(relative, original, true).unwrap(),
                Some(original.to_owned()));
            assert_eq!(ordinary_pair_provider_blueprint(relative, original, false).unwrap(), None);
        }
        for (relative, original, expected) in SHARED_PROVIDER_FIXTURES {
            use sha2::{Digest, Sha256};
            let projected = typed_ingress_shared_blueprint(relative, original).unwrap();
            assert_eq!(format!("{:x}", Sha256::digest(projected.as_bytes())), *expected);
        }
        assert_eq!(ordinary_pair_provider_blueprint("other/Android.bp", "unrelated", true).unwrap(), None);
    }

    #[test]
    fn ordinary_pair_provider_drift_is_rejected_and_normal_projection_restores_bytes_and_time() {
        let fixture = tempfile::tempdir().unwrap();
        let source = fixture.path().join("source");
        let journal = fixture.path().join("projection.json");
        let before = std::time::UNIX_EPOCH + std::time::Duration::from_secs(1_600_000_000);
        for (relative, original) in ordinary_pair_provider_fixtures() {
            let path = source.join(relative);
            write(&path, original).unwrap();
            fs::File::open(&path).unwrap().set_modified(before).unwrap();
            for changed in [format!("{original}\n"), original.replacen("name:", "renamed:", 1)] {
                assert!(ordinary_pair_provider_blueprint(relative, &changed, true).is_err());
            }
        }
        {
            let mut projection = Projection::new(journal.clone()).unwrap();
            for (relative, original) in ordinary_pair_provider_fixtures() {
                let text = ordinary_pair_provider_blueprint(relative, original, true).unwrap().unwrap();
                projection.put(&source.join(relative), text).unwrap();
            }
            assert_eq!(projection.originals.len(), 10);
            assert!(journal.exists());
        }
        assert!(!journal.exists());
        for (relative, original) in ordinary_pair_provider_fixtures() {
            let path = source.join(relative);
            assert_eq!(fs::read(&path).unwrap(), original.as_bytes());
            assert_eq!(fs::metadata(&path).unwrap().modified().unwrap(), before);
        }
    }

    #[test]
    fn ordinary_pair_test_discovery_preserves_other_routes_and_restores_its_markers() {
        for ordinary_pair in [false, true] {
            let fixture = tempfile::tempdir().unwrap();
            let source = fixture.path().join("source");
            let journal = fixture.path().join("projection.json");
            let consumer = source.join("platform_testing/Android.bp");
            write(&consumer, "unchanged upstream consumer bytes\n").unwrap();
            {
                let mut projection = Projection::new(journal.clone()).unwrap();
                project_test_fixture_exclusions(&mut projection, &source,
                    ordinary_pair, SoongDependencyMode::Strict).unwrap();
                for relative in SOONG_EXCLUDED_TEST_FIXTURES {
                    let visible = ordinary_pair && ORDINARY_PAIR_REQUIRED_TEST_TREES.contains(relative);
                    assert_eq!(source.join(relative).join(".find-ignore").exists(), !visible);
                }
                assert_eq!(fs::read(&consumer).unwrap(), b"unchanged upstream consumer bytes\n");
            }
            assert!(!journal.exists());
            for relative in SOONG_EXCLUDED_TEST_FIXTURES {
                assert!(!source.join(relative).join(".find-ignore").exists());
            }
        }
    }

    #[test]
    fn ordinary_pair_existing_test_markers_and_wrong_modes_fail_before_any_new_marker() {
        use std::os::unix::fs::symlink;
        for is_link in [false, true] {
            for relative in ORDINARY_PAIR_REQUIRED_TEST_TREES {
                let fixture = tempfile::tempdir().unwrap();
                let source = fixture.path().join("source");
                let journal = fixture.path().join("projection.json");
                let marker = source.join(relative).join(".find-ignore");
                fs::create_dir_all(marker.parent().unwrap()).unwrap();
                if is_link { symlink("nonexistent", &marker).unwrap(); }
                else { write(&marker, b"foreign marker\n").unwrap(); }
                let mut projection = Projection::new(journal.clone()).unwrap();
                assert!(project_test_fixture_exclusions(&mut projection, &source,
                    true, SoongDependencyMode::Strict).is_err());
                assert!(projection.originals.is_empty());
                assert!(!journal.exists());
                assert!(fs::symlink_metadata(&marker).is_ok());
                if !is_link { assert_eq!(fs::read(&marker).unwrap(), b"foreign marker\n"); }
            }
        }
        let fixture = tempfile::tempdir().unwrap();
        let journal = fixture.path().join("projection.json");
        let mut projection = Projection::new(journal.clone()).unwrap();
        assert!(project_test_fixture_exclusions(&mut projection, fixture.path(),
            true, SoongDependencyMode::NativeBridgeTargetClosure).is_err());
        assert!(project_blueprints(&mut projection, fixture.path(), true,
            true, SoongDependencyMode::NativeBridgeTargetClosure).is_err());
        assert!(!journal.exists());
    }

    #[test]
    fn typed_shared_provider_projection_rejects_changed_missing_or_duplicate_stanzas() {
        for (relative, original, _) in SHARED_PROVIDER_FIXTURES {
            for changed in [original.replacen("name:", "renamed:", 1),
                            format!("{original}\n"),
                            format!("{original}{original}")] {
                assert!(typed_ingress_shared_blueprint(relative, &changed).is_err());
            }
        }
    }

    #[test]
    fn typed_shared_provider_projection_keeps_other_root_projection_unchanged() {
        let source = "package {\n    default_applicable_licenses: [\"license\"],\n}\njava_defaults {\n    name: \"other\",\n}\n";
        assert_eq!(typed_ingress_shared_blueprint("packages/apps/Settings/Android.bp", source).unwrap(),
                   metadata_only(source).unwrap());
    }
    #[test]
    fn typed_hal_provider_projection_restores_real_sources_and_keeps_consumers() {
        use sha2::{Digest, Sha256};
        assert_eq!(TYPED_INGRESS_HAL_BLUEPRINTS.len(), 5);
        assert_eq!(SHARED_PROVIDER_FIXTURES.len(), 31);
        let fixture = tempfile::tempdir().unwrap();
        let source = fixture.path().join("aosp-source");
        let journal = fixture.path().join("projection.json");
        for relative in TYPED_INGRESS_HAL_BLUEPRINTS {
            let (_, original, _) = SHARED_PROVIDER_FIXTURES.iter()
                .find(|row| row.0 == *relative).unwrap();
            write(&source.join(relative), original.as_bytes()).unwrap();
        }
        let consumers = [
            ("hardware/interfaces/automotive/remoteaccess/hal/default/Android.bp",
             include_str!("../../../android/native-role-ingress/provider-fixtures/hardware-remote-access.Android.bp")),
            ("hardware/interfaces/neuralnetworks/utils/common/Android.bp",
             include_str!("../../../android/native-role-ingress/provider-fixtures/hardware-neural-common.Android.bp")),
        ];
        for (relative, original) in consumers {
            write(&source.join(relative), original.as_bytes()).unwrap();
        }
        let mut projection = Projection::new(journal.clone()).unwrap();
        project_typed_ingress_hal_blueprints(&mut projection, &source, false).unwrap();
        assert!(journal.exists());
        for relative in TYPED_INGRESS_HAL_BLUEPRINTS {
            let (_, _, expected_sha) = SHARED_PROVIDER_FIXTURES.iter()
                .find(|row| row.0 == *relative).unwrap();
            let projected = fs::read(source.join(relative)).unwrap();
            assert_eq!(&format!("{:x}", Sha256::digest(&projected)), expected_sha);
        }
        for (relative, original) in consumers {
            assert_eq!(fs::read(source.join(relative)).unwrap(), original.as_bytes());
        }
        projection.restore().unwrap();
        assert!(!journal.exists());
        for relative in TYPED_INGRESS_HAL_BLUEPRINTS {
            let (_, original, _) = SHARED_PROVIDER_FIXTURES.iter()
                .find(|row| row.0 == *relative).unwrap();
            assert_eq!(fs::read(source.join(relative)).unwrap(), original.as_bytes());
        }
    }

    #[test]
    fn typed_hal_provider_late_source_drift_restores_earlier_projections() {
        let fixture = tempfile::tempdir().unwrap();
        let source = fixture.path().join("aosp-source");
        let journal = fixture.path().join("projection.json");
        for relative in TYPED_INGRESS_HAL_BLUEPRINTS {
            let (_, original, _) = SHARED_PROVIDER_FIXTURES.iter()
                .find(|row| row.0 == *relative).unwrap();
            write(&source.join(relative), original.as_bytes()).unwrap();
        }
        let bad_path = *TYPED_INGRESS_HAL_BLUEPRINTS.last().unwrap();
        let (_, original, _) = SHARED_PROVIDER_FIXTURES.iter()
            .find(|row| row.0 == bad_path).unwrap();
        let changed = format!("{original}\n");
        write(&source.join(bad_path), changed.as_bytes()).unwrap();
        {
            let mut projection = Projection::new(journal.clone()).unwrap();
            let error = project_typed_ingress_hal_blueprints(&mut projection, &source, false)
                .unwrap_err().to_string();
            assert!(error.contains("typed ingress shared provider source changed"));
            assert!(error.contains(bad_path));
            assert!(journal.exists());
        }
        assert!(!journal.exists());
        for relative in TYPED_INGRESS_HAL_BLUEPRINTS {
            let (_, original, _) = SHARED_PROVIDER_FIXTURES.iter()
                .find(|row| row.0 == *relative).unwrap();
            let expected = if *relative == bad_path { changed.as_bytes() } else { original.as_bytes() };
            assert_eq!(fs::read(source.join(relative)).unwrap(), expected);
        }
    }

    #[test]
    fn typed_systemui_test_projection_keeps_metadata_parent_providers_and_other_paths() {
        let original = include_str!(
            "../../../android/native-role-ingress/provider-fixtures/SystemUI-tests.Android.bp");
        let parent_original = include_str!(
            "../../../android/native-role-ingress/provider-fixtures/SystemUI.Android.bp");
        let names = [
            "SystemUITests_defaults", "SystemUITests",
            "SystemUITests_systemui_accessibility", "SystemUITests_presubmit",
            "SystemUI_test_fixtures",
        ];
        assert_eq!(original.matches("    name: \"").count(), names.len());
        for name in names {
            assert_eq!(original.matches(&format!("    name: \"{name}\",")).count(), 1);
        }
        let expected = concat!(
            "package {\n",
            "    default_team: \"trendy_team_system_ui_please_use_a_more_specific_subteam_if_possible_\",\n",
            "    default_applicable_licenses: [\"frameworks_base_packages_SystemUI_license\"],\n",
            "}\n",
        );
        let fixture = tempfile::tempdir().unwrap();
        let source = fixture.path().join("aosp-source");
        let path = source.join(TYPED_INGRESS_SYSTEMUI_TESTS_BLUEPRINT);
        let parent = source.join("frameworks/base/packages/SystemUI/Android.bp");
        let untouched = source.join("frameworks/base/packages/SystemUI/tests/other/Android.bp");
        let journal = fixture.path().join("projection.json");
        write(&path, original).unwrap();
        write(&parent, parent_original).unwrap();
        write(&untouched, "unrelated exact bytes\n").unwrap();
        let parent_projected = typed_ingress_shared_blueprint(
            "frameworks/base/packages/SystemUI/Android.bp", parent_original).unwrap();
        {
            let mut projection = Projection::new(journal.clone()).unwrap();
            projection.put(&parent, &parent_projected).unwrap();
            project_typed_ingress_systemui_tests(&mut projection, &source, false).unwrap();
            assert_eq!(fs::read(&path).unwrap(), expected.as_bytes());
            assert_eq!(fs::read(&parent).unwrap(), parent_projected.as_bytes());
            assert_eq!(fs::read(&untouched).unwrap(), b"unrelated exact bytes\n");
            let originals: Vec<Original> = decode_projection_journal(&fs::read(&journal).unwrap(), &source).unwrap();
            assert_eq!(originals.len(), 2);
            assert_eq!(originals[0].path, parent);
            assert_eq!(originals[0].bytes.as_deref(), Some(parent_original.as_bytes()));
            assert_eq!(originals[1].path, path);
            assert_eq!(originals[1].bytes.as_deref(), Some(original.as_bytes()));
        }
        assert!(!journal.exists());
        assert_eq!(fs::read(&path).unwrap(), original.as_bytes());
        assert_eq!(fs::read(&parent).unwrap(), parent_original.as_bytes());
        assert_eq!(fs::read(&untouched).unwrap(), b"unrelated exact bytes\n");
    }

    #[test]
    fn typed_systemui_test_projection_rejects_wrong_source_before_journal_or_write() {
        let original = include_str!(
            "../../../android/native-role-ingress/provider-fixtures/SystemUI-tests.Android.bp");
        for changed in [
            original.replacen("SystemUITests_defaults", "SystemUITests_defaultX", 1),
            format!("{original}\n"),
        ] {
            let fixture = tempfile::tempdir().unwrap();
            let source = fixture.path().join("aosp-source");
            let path = source.join(TYPED_INGRESS_SYSTEMUI_TESTS_BLUEPRINT);
            let journal = fixture.path().join("projection.json");
            write(&path, &changed).unwrap();
            {
                let mut projection = Projection::new(journal.clone()).unwrap();
                let error = project_typed_ingress_systemui_tests(&mut projection, &source, false)
                    .unwrap_err().to_string();
                assert!(error.contains("typed ingress shared provider source changed"));
                assert!(error.contains(TYPED_INGRESS_SYSTEMUI_TESTS_BLUEPRINT));
                assert!(projection.originals.is_empty());
                assert!(!journal.exists());
                assert_eq!(fs::read(&path).unwrap(), changed.as_bytes());
            }
            assert!(!journal.exists());
            assert_eq!(fs::read(&path).unwrap(), changed.as_bytes());
        }
    }

    #[test]
    fn typed_systemui_test_projection_recovers_complete_original_from_durable_journal() {
        let original = include_str!(
            "../../../android/native-role-ingress/provider-fixtures/SystemUI-tests.Android.bp");
        let fixture = tempfile::tempdir().unwrap();
        let source = fixture.path().join("aosp-source");
        let path = source.join(TYPED_INGRESS_SYSTEMUI_TESTS_BLUEPRINT);
        let journal = fixture.path().join("projection.json");
        write(&path, original).unwrap();
        let mut projection = Projection::new(journal.clone()).unwrap();
        project_typed_ingress_systemui_tests(&mut projection, &source, false).unwrap();
        assert_ne!(fs::read(&path).unwrap(), original.as_bytes());
        let originals: Vec<Original> = decode_projection_journal(&fs::read(&journal).unwrap(), &source).unwrap();
        assert_eq!(originals.len(), 1);
        assert_eq!(originals[0].path, path);
        assert_eq!(originals[0].bytes.as_deref(), Some(original.as_bytes()));
        // Model an interrupted process while exercising the real recover entry.
        std::mem::forget(projection);
        assert!(Projection::new(journal.clone()).is_err());
        recover(&journal, &source).unwrap();
        assert_eq!(fs::read(&path).unwrap(), original.as_bytes());
        assert!(!journal.exists());
    }

    #[test]
    fn typed_audiocontrol_example_projection_keeps_metadata_and_sibling_sources() {
        let original = include_str!(
            "../../../android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp");
        assert_eq!(original.matches("cc_binary {").count(), 1);
        assert_eq!(original.matches("    name: \"").count(), 1);
        assert_eq!(original.matches(
            "    name: \"android.hardware.automotive.audiocontrol-service.example\",").count(), 1);
        for name in [
            "latest_android_hardware_audio_common_ndk_shared",
            "latest_android_hardware_automotive_audiocontrol_ndk_shared",
            "powerpolicyclient_defaults",
            "car.audio.configuration.xsd.default",
            "car.fade.configuration.xsd.default",
        ] {
            assert_eq!(original.matches(&format!("        \"{name}\",")).count(), 1);
        }
        let expected = concat!(
            "package {\n",
            "    // See: http://go/android-license-faq\n",
            "    // A large-scale-change added 'default_applicable_licenses' to import\n",
            "    // all of the 'license_kinds' from \"hardware_interfaces_license\"\n",
            "    // to get the below license kinds:\n",
            "    //   SPDX-license-identifier-Apache-2.0\n",
            "    default_applicable_licenses: [\"hardware_interfaces_license\"],\n",
            "}\n",
        );
        let fixture = tempfile::tempdir().unwrap();
        let source = fixture.path().join("aosp-source");
        let path = source.join(TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT);
        let parent = source.join("hardware/interfaces/automotive/audiocontrol/aidl/Android.bp");
        let sibling = source.join("hardware/interfaces/automotive/audiocontrol/aidl/default/AudioControl.cpp");
        let manifest = source.join(".droidloom-source-manifest.json");
        let journal = fixture.path().join("projection.json");
        // Explicit sentinels test write scope, not the content of real providers.
        let sentinels = [
            (&parent, "unchanged parent AIDL provider sentinel\n"),
            (&sibling, "unchanged sibling implementation sentinel\n"),
            (&manifest, "unchanged source manifest sentinel\n"),
        ];
        write(&path, original).unwrap();
        for (p, value) in sentinels { write(p, value).unwrap(); }
        {
            let mut projection = Projection::new(journal.clone()).unwrap();
            project_typed_ingress_audiocontrol_example(&mut projection, &source).unwrap();
            assert_eq!(fs::read(&path).unwrap(), expected.as_bytes());
            for (p, value) in sentinels {
                assert_eq!(fs::read(p).unwrap(), value.as_bytes());
            }
            let originals: Vec<Original> =
                decode_projection_journal(&fs::read(&journal).unwrap(), &source).unwrap();
            assert_eq!(originals.len(), 1);
            assert_eq!(originals[0].path, path);
            assert_eq!(originals[0].bytes.as_deref(), Some(original.as_bytes()));
        }
        assert!(!journal.exists());
        assert_eq!(fs::read(&path).unwrap(), original.as_bytes());
        for (p, value) in sentinels { assert_eq!(fs::read(p).unwrap(), value.as_bytes()); }
    }

    #[test]
    fn typed_audiocontrol_example_projection_rejects_source_drift_before_write() {
        let original = include_str!(
            "../../../android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp");
        for changed in [
            original.replacen("powerpolicyclient_defaults", "powerpolicyclient_changed", 1),
            original.replacen("car.fade.configuration.xsd.default", "car.fade.configuration.xsd.changed", 1),
            format!("{original}\n"),
        ] {
            assert_ne!(changed.as_bytes(), original.as_bytes());
            let fixture = tempfile::tempdir().unwrap();
            let source = fixture.path().join("aosp-source");
            let path = source.join(TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT);
            let journal = fixture.path().join("projection.json");
            write(&path, &changed).unwrap();
            {
                let mut projection = Projection::new(journal.clone()).unwrap();
                let error = project_typed_ingress_audiocontrol_example(&mut projection, &source)
                    .unwrap_err().to_string();
                assert!(error.contains("typed ingress shared provider source changed"));
                assert!(error.contains(TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT));
                assert!(projection.originals.is_empty());
                assert!(!journal.exists());
                assert_eq!(fs::read(&path).unwrap(), changed.as_bytes());
            }
            assert!(!journal.exists());
            assert_eq!(fs::read(&path).unwrap(), changed.as_bytes());
        }
    }

    #[test]
    fn typed_audiocontrol_example_projection_recovers_full_observed_original() {
        let original = include_str!(
            "../../../android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp");
        let fixture = tempfile::tempdir().unwrap();
        let source = fixture.path().join("aosp-source");
        let path = source.join(TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT);
        let journal = fixture.path().join("projection.json");
        write(&path, original).unwrap();
        let mut projection = Projection::new(journal.clone()).unwrap();
        project_typed_ingress_audiocontrol_example(&mut projection, &source).unwrap();
        assert_ne!(fs::read(&path).unwrap(), original.as_bytes());
        let originals: Vec<Original> =
            decode_projection_journal(&fs::read(&journal).unwrap(), &source).unwrap();
        assert_eq!(originals.len(), 1);
        assert_eq!(originals[0].path, path);
        assert_eq!(originals[0].bytes.as_deref(), Some(original.as_bytes()));
        std::mem::forget(projection);
        assert!(Projection::new(journal.clone()).is_err());
        recover(&journal, &source).unwrap();
        assert_eq!(fs::read(&path).unwrap(), original.as_bytes());
        assert!(!journal.exists());
    }

    #[test]
    fn native_engine_mode_rejects_widening_before_command_mutation() {
        for targets in [
            &[][..], &["berberis_arm64_host_tests"][..], &["droidloom-native-bridge"][..],
            &["libberberis_arm64", "services"][..],
            &["libberberis_arm64", "libminigbm_gralloc"][..],
            &["libberberis_arm64", "berberis_arm64_host_tests", "services"][..], TARGETS,
        ] {
            let mut command = Command::new("not-executed");
            command.env("ALLOW_MISSING_DEPENDENCIES", "false");
            assert!(configure_soong_dependencies(&mut command,
                SoongDependencyMode::NativeEngineTargetClosure, targets).is_err());
            assert!(command.get_args().next().is_none());
            assert!(command.get_envs().any(|(key, value)| key == "ALLOW_MISSING_DEPENDENCIES"
                && value == Some(std::ffi::OsStr::new("false"))));
            assert!(!native_engine_only_build(targets));
        }
    }

    #[test]
    fn native_engine_mode_selects_only_android_engine_and_real_64_bit_test_install() {
        let out = Path::new("/not-a-workspace/out");
        for targets in [&["libberberis_arm64"][..],
            &["libberberis_arm64", "berberis_arm64_host_tests"][..]] {
            let mut command = Command::new("not-executed");
            command.env("LLVM_PREBUILTS_VERSION", "unrelated-compiler");
            configure_soong_dependencies(&mut command,
                SoongDependencyMode::NativeEngineTargetClosure, targets).unwrap();
            assert!(command.get_args().any(|a| a == "--soong-only"));
            assert!(command.get_envs().any(|(k, v)| k == "ALLOW_MISSING_DEPENDENCIES"
                && v == Some(std::ffi::OsStr::new("true"))));
            assert!(command.get_envs().any(|(k, v)| k == "LLVM_PREBUILTS_VERSION" && v.is_none()));
            let actual = selected_soong_targets(SoongDependencyMode::NativeEngineTargetClosure,
                targets, out, "droidloom_x86_64").unwrap();
            assert_eq!(actual[0], out.join("target/product/droidloom_x86_64/system/lib64/libberberis_arm64.so"));
            if targets.len() == 2 {
                assert_eq!(actual[1], Path::new("berberis_arm64_host_tests-linux_glibc_x86_64-install"));
            }
            assert!(nativebridge_discovery_scope(targets));
            assert!(!private_nativebridge_unrelated_paths(targets).is_empty());
            assert!(!native_bridge_only_build(targets));
            assert!(!minigbm_only_build(targets));
            assert!(!audio_apex_only_build(targets));
        }
    }

    #[test]
    fn native_engine_patch_routing_keeps_full_product_and_make_bridge_semantics() {
        let engine = SoongDependencyMode::NativeEngineTargetClosure;
        assert!(qualified_defaults_mode(engine));
        assert!(leaf_go_memory_mode(engine));
        assert_eq!(target_closure_soong_patches(engine), TARGET_CLOSURE_SOONG_PATCHES);
        assert!(audio_apex_pcm_patches(engine).is_empty());
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure] {
            assert!(!qualified_defaults_mode(mode));
            assert!(!leaf_go_memory_mode(mode));
            let targets = if mode == SoongDependencyMode::Strict { TARGETS }
                else { &["droidloom-native-bridge"][..] };
            let mut command = Command::new("not-executed");
            configure_soong_dependencies(&mut command, mode, targets).unwrap();
            assert!(!command.get_args().any(|a| a == "--soong-only"));
            assert_eq!(selected_soong_targets(mode, targets, Path::new("/out"), "droidloom_x86_64")
                .unwrap()[0], Path::new("droidloom-native-bridge"));
        }
        assert!(qualified_defaults_mode(SoongDependencyMode::AudioApexTargetClosure));
        assert!(!leaf_go_memory_mode(SoongDependencyMode::AudioApexTargetClosure));
        assert!(qualified_defaults_mode(SoongDependencyMode::MinigbmTargetClosure));
        assert!(leaf_go_memory_mode(SoongDependencyMode::MinigbmTargetClosure));
        assert!(!nativebridge_discovery_scope(TARGETS));
    }

    #[test]
    fn native_engine_automotive_scope_is_exact_and_restored_for_all_modes() {
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::AudioApexTargetClosure, SoongDependencyMode::MinigbmTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure] {
            let fixture = tempfile::tempdir().unwrap();
            let source = fixture.path().join("source");
            for path in ["hardware/interfaces/automotive/vehicle/aidl/aidl_test/Android.bp",
                         "hardware/interfaces/graphics/common/Android.bp",
                         "hardware/interfaces/graphics/allocator/Android.bp",
                         "hardware/interfaces/graphics/mapper/Android.bp",
                         "frameworks/libs/binary_translation/Android.bp"] {
                write(&source.join(path), "real provider sentinel\n").unwrap();
            }
            let journal = fixture.path().join("projection.json");
            let mut projection = Projection::new(journal).unwrap();
            project_native_leaf_discovery_scope(&mut projection, &source, mode).unwrap();
            let ignore = source.join("hardware/interfaces/automotive/.find-ignore");
            assert_eq!(ignore.is_file(), matches!(mode, SoongDependencyMode::NativeEngineTargetClosure
                | SoongDependencyMode::MinigbmTargetClosure));
            for subtree in ["hardware/interfaces/graphics/common", "hardware/interfaces/graphics/allocator",
                            "hardware/interfaces/graphics/mapper", "frameworks/libs/binary_translation"] {
                assert!(!source.join(subtree).join(".find-ignore").exists());
                assert_eq!(fs::read(source.join(subtree).join("Android.bp")).unwrap(),
                    b"real provider sentinel\n");
            }
            projection.restore().unwrap();
            assert!(!ignore.exists());
            assert_eq!(fs::read(source.join("hardware/interfaces/automotive/vehicle/aidl/aidl_test/Android.bp"))
                .unwrap(), b"real provider sentinel\n");
        }
    }

    fn native_engine_jarjar_fixtures() -> [(&'static str, &'static str); 5] {
        [
            ("packages/modules/NetworkStack/Android.bp", include_str!(
                "../tests/fixtures/native-engine-jarjar/networkstack-928a826-Android.bp")),
            ("packages/modules/Connectivity/framework/Android.bp", include_str!(
                "../tests/fixtures/native-engine-jarjar/connectivity-347fbd3-framework-Android.bp")),
            ("packages/modules/Connectivity/Tethering/common/TetheringLib/Android.bp", include_str!(
                "../tests/fixtures/native-engine-jarjar/connectivity-347fbd3-tetheringlib-Android.bp")),
            // Preserve compatibility changes already present in the real R4
            // projection, including its JNI headers and nativehelper choices.
            ("packages/modules/Connectivity/service/Android.bp", include_str!(
                "../tests/fixtures/native-engine-jarjar/connectivity-347fbd3-service-r4-effective.bp")),
            ("libcore/JavaLibrary.bp", include_str!(
                "../tests/fixtures/native-engine-jarjar/libcore-4ebfb39-JavaLibrary.bp")),
        ]
    }

    // These complete pinned fixtures use column-zero top-level module braces.
    // Compare every retained block, rather than checking only a JNI name list.
    fn native_engine_fixture_blocks(text: &str) -> Vec<&str> {
        let mut blocks = Vec::new();
        let mut offset = 0;
        for line in text.split_inclusive('\n') {
            if let Some(kind) = line.strip_suffix(" {\n") {
                if !kind.is_empty() && kind.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'_') {
                    let end = offset + text[offset..].find("\n}\n").unwrap() + 3;
                    blocks.push(&text[offset..end]);
                }
            }
            offset += line.len();
        }
        blocks
    }

    fn native_engine_existing_java_scope(relative: &str, original: &str) -> String {
        let mut text = original.to_owned();
        for (path, kind, names) in PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES {
            if *path == relative {
                for name in *names {
                    text = private_without_named_java_module(&text, kind, name).unwrap();
                }
            }
        }
        text
    }

    #[test]
    fn native_engine_paired_java_consumers_preserve_original_native_providers_and_modes() {
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::AudioApexTargetClosure, SoongDependencyMode::MinigbmTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure] {
            let fixture = tempfile::tempdir().unwrap();
            let source = fixture.path().join("source");
            for (relative, original) in native_engine_jarjar_fixtures() {
                let text = if matches!(mode, SoongDependencyMode::NativeEngineTargetClosure
                    | SoongDependencyMode::NativeBridgeTargetClosure) {
                    native_engine_existing_java_scope(relative, original)
                } else { original.to_owned() };
                write(&source.join(relative), text).unwrap();
            }
            let mut projection = Projection::new(fixture.path().join("journal.json")).unwrap();
            project_native_engine_java_consumers(&mut projection, &source, mode).unwrap();
            for (relative, original) in native_engine_jarjar_fixtures() {
                let staged = if matches!(mode, SoongDependencyMode::NativeEngineTargetClosure
                    | SoongDependencyMode::NativeBridgeTargetClosure) {
                    native_engine_existing_java_scope(relative, original)
                } else { original.to_owned() };
                let result = fs::read_to_string(source.join(relative)).unwrap();
                if mode == SoongDependencyMode::NativeEngineTargetClosure {
                    let (_, producers, consumers) = NATIVE_ENGINE_JAVA_CONSUMER_SCOPE.iter()
                        .find(|(path, _, _)| *path == relative).unwrap();
                    for name in *producers {
                        assert!(!result.contains(&format!("    name: \"{name}\",")));
                    }
                    for (_, name) in *consumers {
                        assert!(!result.contains(&format!("    name: \"{name}\",")));
                    }
                    let before_blocks = native_engine_fixture_blocks(&staged);
                    let after_blocks = native_engine_fixture_blocks(&result);
                    assert_eq!(after_blocks.len(), before_blocks.len() - consumers.len());
                    for block in before_blocks {
                        if consumers.iter().any(|(_, name)| block.contains(
                            &format!("    name: \"{name}\","))) {
                            assert!(!result.contains(block));
                        } else {
                            assert!(result.contains(block), "retained provider changed in {relative}: {block}");
                        }
                    }
                    for block in after_blocks {
                        let kind = block.split_once(" {\n").unwrap().0;
                        if kind.ends_with("genrule") || kind == "gensrcs" {
                            assert!(!block.contains("{.jar}"),
                                "unselected test/Java JAR consumer remains in {relative}: {block}");
                        }
                    }
                    if relative == "packages/modules/Connectivity/service/Android.bp" {
                        assert!(result.contains("    name: \"service-connectivity-pre-jarjar\","));
                        assert!(staged.contains(":\" + service_remoteauth_pre_jarjar_lib + \"{.jar}"));
                    }
                } else {
                    assert_eq!(result, staged, "consumer scope widened {mode:?}");
                }
                assert_eq!(result.matches("\nfilegroup {\n").count(),
                    original.matches("\nfilegroup {\n").count());
            }
            projection.restore().unwrap();
            for (relative, original) in native_engine_jarjar_fixtures() {
                let expected = if matches!(mode, SoongDependencyMode::NativeEngineTargetClosure
                    | SoongDependencyMode::NativeBridgeTargetClosure) {
                    native_engine_existing_java_scope(relative, original)
                } else { original.to_owned() };
                assert_eq!(fs::read_to_string(source.join(relative)).unwrap(), expected);
            }
        }
    }

    #[test]
    fn native_engine_java_consumers_fail_closed_before_paired_producer_scope() {
        let fixture = tempfile::tempdir().unwrap();
        let source = fixture.path().join("source");
        for (relative, original) in native_engine_jarjar_fixtures() {
            write(&source.join(relative), original).unwrap();
        }
        let mut projection = Projection::new(fixture.path().join("journal.json")).unwrap();
        let error = project_native_engine_java_consumers(&mut projection, &source,
            SoongDependencyMode::NativeEngineTargetClosure).unwrap_err().to_string();
        assert!(error.contains("NetworkStackApiStableLib"));
        assert!(error.contains("already scoped out"));
        for (relative, original) in native_engine_jarjar_fixtures() {
            assert_eq!(fs::read_to_string(source.join(relative)).unwrap(), original);
        }
    }

    #[test]
    fn audio_apex_scope_excludes_only_the_explicit_target_list() {
        assert!(audio_apex_only_build(&["com.android.hardware.audio.droidloom"]));
        for targets in [
            &[][..],
            &["droidloom-native-bridge"][..],
            &["com.android.hardware.audio.droidloom", "services"][..],
            TARGETS,
        ] {
            assert!(!audio_apex_only_build(targets));
        }
    }
    #[test]
    fn audio_serialservice_metadata_preserves_license_without_inventing_a_team() {
        let original = "package {\n    default_team: \"trendy_team_webapps_cros_android\",\n    default_applicable_licenses: [\"upstream_license\"],\n}\n";
        let filtered = audio_serialservice_metadata_without_stale_team(original).unwrap();
        assert!(filtered.contains("default_applicable_licenses: [\"upstream_license\"]"));
        assert!(!filtered.contains("default_team"));
        assert!(audio_serialservice_metadata_without_stale_team(&filtered).is_err());
    }
    #[test]
    fn audio_prebuilt_tradefed_selection_preserves_other_product_configuration() {
        let original = format!("other_product_setting := original\n{}next_product_setting := original\n", AUDIO_UPSTREAM_TRADEFED_SOURCE_SELECTION);
        let result = audio_select_original_prebuilt_tradefed(&original).unwrap();
        assert!(result.contains("other_product_setting := original"));
        assert!(result.contains("next_product_setting := original"));
        assert!(result.contains("$(call soong_config_set_bool,tradefed,use_prebuilt,true)"));
        assert!(!result.contains("use_prebuilt,false"));
        assert!(audio_select_original_prebuilt_tradefed(&result).is_err());
    }

    #[test]
    fn audio_platform_test_scope_preserves_metadata_and_real_library_provider() {
        let mut original = String::from("package {\n    default_applicable_licenses: [\"real_license\"],\n}\njava_library_host {\n    name: \"tradefed_errorprone_defaults_provider\",\n}\n");
        for name in ["platform_tests", "continuous_native_tests", "continuous_native_metric_tests", "continuous_instrumentation_tests", "continuous_instrumentation_metric_tests", "cw_continuous_native_tests", "emulator_tests"] {
            original.push_str(&format!("test_package {{\n    name: \"{name}\",\n}}\n"));
        }
        let result = audio_without_unselected_platform_test_aggregators(&original).unwrap();
        assert!(result.contains("real_license"));
        assert!(result.contains("tradefed_errorprone_defaults_provider"));
        assert!(!result.contains("test_package"));
        assert!(audio_without_unselected_platform_test_aggregators(&result).is_err());
    }

    const REAL_PAIR_APKSIG_BLUEPRINT: &str = r###"//
// Copyright (C) 2016 The Android Open Source Project
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//

// apksig library, for signing APKs and verifying signatures of APKs
// ============================================================
package {
    default_applicable_licenses: ["tools_apksig_license"],
}

// Added automatically by a large-scale-change
// http://go/android-license-faq
license {
    name: "tools_apksig_license",
    visibility: [":__subpackages__"],
    license_kinds: [
        "SPDX-license-identifier-Apache-2.0",
    ],
    license_text: [
        "LICENSE",
    ],
}

java_library {
    name: "apksig",
    srcs: ["src/main/java/**/*.java"],
    exclude_srcs: [
        "src/main/java/com/android/apksig/kms/aws/**/*.java",
        "src/main/java/com/android/apksig/kms/gcp/**/*.java",
    ],
    java_version: "1.8",
    host_supported: true,
    target: {
        windows: {
            enabled: true,
        },
    },
    sdk_version: "current",
    min_sdk_version: "36",
    apex_available: ["com.android.webapp"],
}

java_library_host {
    name: "apksig-kms-provider-aws",
    srcs: [
        "src/main/java/com/android/apksig/kms/aws/**/*.java",
    ],
    libs: [
        "apksig",
        "awssdk-kms",
        "awssdk-url-connection-client",
    ],
    services: ["src/providers/aws/*"],
    java_version: "1.8",
    target: {
        windows: {
            enabled: true,
        },
    },
}

java_library_host {
    name: "apksig-kms-provider-gcp",
    srcs: [
        "src/main/java/com/android/apksig/kms/gcp/**/*.java",
    ],
    libs: [
        "apksig",
        "google-cloud-kms",
    ],
    services: ["src/providers/gcp/*"],
    java_version: "1.8",
    target: {
        windows: {
            enabled: true,
        },
    },
}

// apksigner command-line tool for signing APKs and verifying their signatures
// ============================================================
java_defaults {
    name: "apksigner-defaults",
    srcs: ["src/apksigner/java/**/*.java"],
    java_resource_dirs: ["src/apksigner/java"],
    manifest: "src/apksigner/apksigner.mf",
    static_libs: ["conscrypt-unbundled"],
    java_version: "1.8",
    target: {
        not_windows: {
            jni_libs: ["libconscrypt_openjdk_jni"],
        },
    },
}

java_binary_host {
    name: "apksigner",
    defaults: ["apksigner-defaults"],
    wrapper: "etc/apksigner",
    static_libs: ["apksig"],
    target: {
        windows: {
            enabled: true,
            wrapper: "etc/apksigner.bat",
        },
    },
}

java_binary_host {
    name: "apksigner-kms",
    defaults: ["apksigner-defaults"],
    wrapper: "etc/apksigner-kms",
    static_libs: [
        "apksig",
        "apksig-kms-provider-aws",
        "apksig-kms-provider-gcp",
        "awssdk-kms",
        "awssdk-url-connection-client",
        "conscrypt-unbundled",
        "google-api-java-client-assembly",
        "google-auth-library-java-credentials",
        "google-auth-library-java-oauth2_http",
        "google-cloud-kms",
        "grpc-java-api",
        "grpc-java-auth",
        "grpc-java-context",
        "grpc-java-core",
        "grpc-java-core-internal",
        "grpc-java-core-util",
        "grpc-java-netty-shaded",
        "grpc-java-protobuf",
        "grpc-java-protobuf-lite",
        "grpc-java-stub",
        "gson",
        "guava",
        "libprotobuf-java-util-full",
        "opencensus-java-api",
        "opencensus-java-contrib-grpc-metrics",
        "opencensus-java-contrib-http-util",
        "perfmark",
        "slf4j-api",
        "threetenbp",
    ],
    target: {
        windows: {
            enabled: true,
            wrapper: "etc/apksigner-kms.bat",
        },
    },
}

java_test_host {
    name: "apksig-test",
    srcs: ["src/test/java/**/*.java"],
    exclude_srcs: [
        "src/test/java/com/android/apksig/kms/KeyWrapper.java",
        "src/test/java/com/android/apksig/kms/aws/AwsTestData.java",
        "src/test/java/com/android/apksig/kms/gcp/GcpTestData.java",
    ],
    java_resource_dirs: ["src/test/resources"],
    static_libs: [
        "apksig",
        "awssdk-kms",
        "awssdk-url-connection-client",
        "bouncycastle-unbundled",
        "conscrypt-unbundled",
        "google-api-java-client-assembly",
        "google-auth-library-java-credentials",
        "google-auth-library-java-oauth2_http",
        "junit",
        "google-cloud-kms",
        "libprotobuf-java-util-full",
        "slf4j-api",
    ],
}
"###;

    #[test]
    fn ordinary_pair_local_signer_keeps_exact_real_upstream_modules() {
        let original = REAL_PAIR_APKSIG_BLUEPRINT;
        let projected = ordinary_pair_local_signer_blueprint(original).unwrap();
        for required in [
            r###"java_library {
    name: "apksig",
    srcs: ["src/main/java/**/*.java"],
    exclude_srcs: [
        "src/main/java/com/android/apksig/kms/aws/**/*.java",
        "src/main/java/com/android/apksig/kms/gcp/**/*.java",
    ],
    java_version: "1.8",
    host_supported: true,
    target: {
        windows: {
            enabled: true,
        },
    },
    sdk_version: "current",
    min_sdk_version: "36",
    apex_available: ["com.android.webapp"],
}
"###,
            r###"java_defaults {
    name: "apksigner-defaults",
    srcs: ["src/apksigner/java/**/*.java"],
    java_resource_dirs: ["src/apksigner/java"],
    manifest: "src/apksigner/apksigner.mf",
    static_libs: ["conscrypt-unbundled"],
    java_version: "1.8",
    target: {
        not_windows: {
            jni_libs: ["libconscrypt_openjdk_jni"],
        },
    },
}
"###,
            r###"java_binary_host {
    name: "apksigner",
    defaults: ["apksigner-defaults"],
    wrapper: "etc/apksigner",
    static_libs: ["apksig"],
    target: {
        windows: {
            enabled: true,
            wrapper: "etc/apksigner.bat",
        },
    },
}
"###,
        ] {
            assert_eq!(projected.matches(required).count(), 1);
        }
        assert!(projected.contains("tools_apksig_license"));
        for omitted in ["apksig-kms-provider-aws", "apksig-kms-provider-gcp", "apksigner-kms", "apksig-test"] {
            assert!(!projected.contains(&format!("name: \"{omitted}\"")));
        }
        assert_eq!(projected, audio_without_unselected_cloud_kms(original).unwrap());
    }

    #[test]
    fn ordinary_pair_local_signer_rejects_unpinned_or_reprojected_source() {
        assert!(ordinary_pair_local_signer_blueprint(
            &format!("{}\n", REAL_PAIR_APKSIG_BLUEPRINT)).is_err());
        let projected = ordinary_pair_local_signer_blueprint(REAL_PAIR_APKSIG_BLUEPRINT).unwrap();
        assert!(ordinary_pair_local_signer_blueprint(&projected).is_err());
    }

    #[test]
    fn audio_kms_scope_preserves_the_real_local_signing_chain() {
        let original = "java_library {\n    name: \"apksig\",\n}\njava_binary_host {\n    name: \"apksigner\",\n    static_libs: [\"apksig\"],\n}\njava_library_host {\n    name: \"apksig-kms-provider-aws\",\n}\njava_library_host {\n    name: \"apksig-kms-provider-gcp\",\n}\njava_binary_host {\n    name: \"apksigner-kms\",\n}\njava_test_host {\n    name: \"apksig-test\",\n    static_libs: [\"awssdk-kms\"],\n}\n";
        let result = audio_without_unselected_cloud_kms(original).unwrap();
        assert!(result.contains("name: \"apksig\""));
        assert!(result.contains("name: \"apksigner\""));
        assert!(result.contains("static_libs: [\"apksig\"]"));
        assert!(!result.contains("kms"));
        assert!(audio_without_unselected_cloud_kms(&result).is_err());
    }
    #[test]
    fn private_java_codegen_test_tools_have_exact_original_blueprint_module_types() {
        let set=PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        for (path,kind,name) in [
            ("packages/modules/StatsD/framework/Android.bp","java_library_static","statslog-statsd"),
            ("frameworks/proto_logging/stats/stats_log_api_gen/test_java/Android.bp","java_atomslog_library","statsdtest_worksource_java_gen"),
            ("frameworks/proto_logging/stats/stats_log_api_gen/test_java/Android.bp","java_atomslog_library","statsdtest_cts_java_gen"),
            ("build/make/tools/ide_query/prober_scripts/jvm/Android.bp","java_library","ide_query_proberscript_jvm"),
            ("frameworks/proto_logging/stats/enums/printing/Android.bp","java_library","framework-printing-enums-proto-lite-java"),
            ("system/security/identity/util/Android.bp","java_library","identity-credential-util"),
            ("system/server_configurable_flags/aconfigd/Android.bp","java_library","aconfigd_java_utils"),
        ] {
            assert!(set.iter().any(|(p,k,n)|*p==path && *k==kind && n.contains(&name)));
        }
        assert!(!native_bridge_only_build(&["services"]));
    }

    #[test]
    fn native_engine_scope_metadata_is_covered_by_pinned_sparse_source() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let mut lock = droidloom_source::load_lock(
            &repo.join("android/manifest/m2-sparse-source-lock.json"),
        ).unwrap();
        validate_nativebridge_scope_source_paths(&lock).unwrap();
        let project = lock.projects.iter_mut()
            .find(|project| project.path == Path::new("system/server_configurable_flags"))
            .unwrap();
        let before = project.sparse_paths.len();
        project.sparse_paths.retain(|path| path != Path::new("aconfigd/Android.bp"));
        assert_eq!(project.sparse_paths.len() + 1, before);
        let error = validate_nativebridge_scope_source_paths(&lock).unwrap_err().to_string();
        assert!(error.contains("system/server_configurable_flags/aconfigd/Android.bp"));
        assert!(error.contains("5069ba739faebf91ae72096577ae17e13061af72"));
        assert!(error.contains("outside the locked sparse paths"));
    }

    #[test]
    fn native_engine_scope_metadata_matches_real_git_cone_parent_files() {
        let fixture = tempfile::tempdir().unwrap();
        let root = fixture.path();
        for path in ["Android.bp", "services/Android.bp", "services/core/source.cc",
                     "aconfigd/Android.bp", "unselected/Android.bp"] {
            write(&root.join(path), "fixture\n").unwrap();
        }
        run(Command::new("git").arg("-C").arg(root).args(["init", "--quiet"])).unwrap();
        run(Command::new("git").arg("-C").arg(root).args(["add", "."])).unwrap();
        run(Command::new("git").arg("-C").arg(root).args([
            "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
            "commit", "--quiet", "-m", "fixture",
        ])).unwrap();
        for paths in [vec![PathBuf::from("services/core"), PathBuf::from("aconfigd/Android.bp")],
                      vec![PathBuf::from("services/core")]] {
            run(Command::new("git").arg("-C").arg(root)
                .args(["sparse-checkout", "set", "--cone", "--skip-checks"])
                .args(&paths)).unwrap();
            for relative in ["Android.bp", "services/Android.bp", "aconfigd/Android.bp",
                             "unselected/Android.bp"] {
                assert_eq!(cone_covers_metadata(Path::new(relative), &paths),
                    root.join(relative).is_file(), "{relative} with {paths:?}");
            }
        }
    }

    #[test]
    fn private_nativebridge_only_ignores_six_original_android_test_folders() {
        let scope=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        for x in [
            "packages/modules/StatsD/framework/test/hostsidetests",
            "packages/modules/StatsD/framework/test/unittests",
            "packages/modules/Virtualization/android/MicrodroidDemoApp",
            "frameworks/av/media/tests/SampleVideoEncoder/app",
            "frameworks/av/media/tests/PlaybackPowerTest",
            "packages/modules/Connectivity/tests/connresources",
        ] {
            assert!(scope.contains(&x),"missing exact private test folder {x}");
            assert!(!private_nativebridge_unrelated_paths(&["services"]).contains(&x));
        }
        for path in ["frameworks/av/media", "packages/modules/Connectivity",
              "packages/modules/Virtualization","packages/modules/StatsD"] {
            assert!(!scope.contains(&path),"invalid full product root removal {path}");
        }
    }

    #[test]
    fn private_nativebridge_skips_only_protobuf_media_graphics_java_apps() {
        let modules=PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        for (path, kind, name) in [
            ("external/protobuf/Android.bp","java_test","aprotoc-test-nano-params"),
            ("external/protobuf/Android.bp","java_test","android-nano-test-parcelable-extendable"),
            ("frameworks/base/libs/hwui/Android.bp","java_sdk_library","framework-graphics"),
            ("packages/modules/Media/apex/framework/Android.bp","java_library","updatable-media"),
        ] {
            assert!(modules.iter().any(|(p,k,n)|*p==path && *k==kind && n.contains(&name)));
        }
        assert!(!native_bridge_only_build(&["services"]));
        assert!(!private_nativebridge_unrelated_paths(&["droidloom-native-bridge"])
            .contains(&"packages/modules/Media/apex/framework"));
    }

    #[test]
    fn nativebridge_scopes_exact_eight_unselected_java_dependencies() {
        let set=PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        let original=[
          ("system/tools/hidl/test/java_partial_test/Android.bp","java_library","hidl_partial_java_test"),
          ("hardware/interfaces/health/aidl/Android.bp","java_library","android.hardware.health-translate-java"),
          ("system/tools/aidl/Android.bp","java_library","libsimpleparcelable_java"),
          ("frameworks/base/services/Android.bp","java_library","binder_observer_config_enabled"),
          ("frameworks/base/services/Android.bp","java_library","binder_observer_config_disabled"),
          ("frameworks/proto_logging/stats/enums/stats/style/Android.bp","java_library","styleprotoslite"),
          ("hardware/interfaces/soundtrigger/aidl/cli/Android.bp","java_binary","sthal_cli_3"),
          ("frameworks/base/Ravenwood.bp","java_library","framework-minus-apex-for-host"),
        ];
        for (path,kind,name) in original {
            assert!(set.iter().any(|(p,k,n)|*p==path && *k==kind && n.contains(&name)),
             "missing precise original Java name {name}");
        }
        assert!(!native_bridge_only_build(&["services"]));
        assert!(!private_nativebridge_unrelated_paths(&["droidloom-native-bridge"])
          .contains(&"frameworks/base/services"));
    }

    #[test]
    fn private_framework_java_aggregate_scope_preserves_full_product() {
        let mods=PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter()
           .find(|(p,k,n)| *p=="frameworks/base/Android.bp" &&
                 *k=="java_library" && n.contains(&"framework-all")).unwrap();
        for name in ["framework-all","framework-minus-internal-res"] {
           assert!(mods.2.contains(&name));
        }
        let sample="java_library {\n    name: \"framework-all\",\n    static_libs: [\"framework-minus-apex\"],\n}\ncc_library_shared {\n    name: \"libberberis_arm64\",\n}\n";
        let after=private_without_named_java_module(
            sample, "java_library", "framework-all").unwrap();
        assert!(after.contains("libberberis_arm64"));
        assert!(!after.contains("framework-minus-apex"));
        assert!(!native_bridge_only_build(&["services"]));
    }

    #[test]
    fn m954_private_api_util_is_not_nativebridge_translation_dep() {
        let names = PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        assert!(names.iter().any(|(p,k,n)|
            *p=="packages/modules/Connectivity/framework/Android.bp" &&
            *k=="java_library" && n.contains(&"connectivity-internal-api-util")));
        let src="java_library {\n    name: \"connectivity-internal-api-util\",\n}\ncc_library {\n    name: \"libnativebpf\",\n}\n";
        let filtered = private_without_named_java_module(src,"java_library","connectivity-internal-api-util").unwrap();
        assert!(filtered.contains("libnativebpf"));
        assert!(!filtered.contains("connectivity-internal-api-util"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
    }

    #[test]
    fn m953_private_audio_hal_session_scopes_only_unselected_modules() {
        let original="cc_library_shared {\n    name: \"libbluetooth_audio_session\",\n}\ncc_library_shared {\n    name: \"libbluetooth_audio_session_aidl\",\n}\ncc_test {\n    name: \"BluetoothLeAudioCodecsProviderTest\",\n}\n";
        let filtered=private_without_named_java_module(original,"cc_library_shared","libbluetooth_audio_session").unwrap();
        let filtered=private_without_named_java_module(&filtered,"cc_library_shared","libbluetooth_audio_session_aidl").unwrap();
        assert!(filtered.contains("BluetoothLeAudioCodecsProviderTest"));
        assert!(!filtered.contains("name: \"libbluetooth_audio_session_aidl\""));
        assert!(!filtered.contains("name: \"libbluetooth_audio_session\""));
        assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(
            |(p,k,n)| *p=="hardware/interfaces/bluetooth/audio/utils/Android.bp" &&
                *k=="cc_library_shared" && n.len()==2));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
    }

    #[test]
    fn m951_private_connectivity_jarjar_does_not_drop_native_bpf() {
        let entries = PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        assert!(entries.iter().any(|(p,k,n)| *p=="packages/modules/Connectivity/framework/Android.bp"
            && *k=="java_library" && n.contains(&"framework-connectivity-pre-jarjar")
            && n.contains(&"framework-connectivity-post-jarjar")));
        assert!(!private_nativebridge_unrelated_paths(&["droidloom-native-bridge"])
            .contains(&"packages/modules/Connectivity"));
        assert!(!private_nativebridge_unrelated_paths(&["services"])
            .contains(&"packages/modules/Connectivity"));
    }

    #[test]
    fn m950_private_httpengine_full_original_consumer_chain() {
        let original = "java_library {\n    name: \"httpengine_internal\",\n}\njava_library {\n    name: \"httpengine\",\n    static_libs: [\"httpengine_internal\"],\n}\njava_genrule {\n    name: \"httpengine-jarjar-rules\",\n}\n";
        let s=private_without_named_java_module(original,"java_library","httpengine").unwrap();
        let s=private_without_named_java_module(&s,"java_genrule","httpengine-jarjar-rules").unwrap();
        assert!(s.contains("httpengine_internal"));
        assert!(!s.contains("name: \"httpengine\""));
        assert!(!s.contains("httpengine-jarjar-rules"));
        assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(
            |(p,k,n)| *p=="external/cronet/android/Android.bp"
                && *k=="java_library" && n.contains(&"httpengine")));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
    }

    #[test]
    fn m949_private_intdefs_only_keeps_primary_framework_modules() {
        let private = PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        assert!(private.iter().any(|(p,t,n)|
            *p == "frameworks/base/Android.bp"
            && *t == "java_library"
            && *n == &["framework-minus-apex-intdefs"]));
        let original="java_library {\n    name: \"framework-minus-apex\",\n}\njava_library {\n    name: \"framework-minus-apex-intdefs\",\n}\n";
        let projected = private_without_named_java_module(original, "java_library",
            "framework-minus-apex-intdefs").unwrap();
        assert!(projected.contains("name: \"framework-minus-apex\""));
        assert!(!projected.contains("name: \"framework-minus-apex-intdefs\""));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
    }

    #[test]
    fn private_tethering_apex_preserves_production_jar_defaults_in_native_scope() {
       assert!(!private_nativebridge_unrelated_paths(&["droidloom-native-bridge"])
         .contains(&"packages/modules/Connectivity/Tethering/apex"));
       let original="java_defaults {\n    name: \"ConnectivityNextEnableDefaults\",\n}\napex {\n    name: \"com.android.tethering\",\n}\n";
       let filtered=private_without_named_java_module(original, "apex", "com.android.tethering").unwrap();
       assert!(filtered.contains("ConnectivityNextEnableDefaults"));
       assert!(!filtered.contains("name: \"com.android.tethering\","));
       assert!(!private_nativebridge_unrelated_paths(&["services"])
            .contains(&"packages/modules/Connectivity/Tethering/apex"));
       assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(|(p,k,n)|
           *p=="packages/modules/Connectivity/Tethering/apex/Android.bp"
            && *k=="bootclasspath_fragment" && n.contains(&"com.android.tethering-bootclasspath-fragment")));
    }
    #[test]
    fn permission_systemserver_packaging_is_not_native_translator() {
        assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(|(p,k,n)|
          *p=="packages/modules/Permission/Android.bp"
          && *k=="systemserverclasspath_fragment"
          && n.contains(&"com.android.permission-systemserverclasspath-fragment")));
        let src="systemserverclasspath_fragment {\n    name: \"com.android.permission-systemserverclasspath-fragment\",\n    contents: [\"service-permission\"],\n}\napex {\n    name: \"com.android.permission\",\n}\n";
        let trimmed=private_without_named_java_module(src,"systemserverclasspath_fragment",
             "com.android.permission-systemserverclasspath-fragment").unwrap();
        assert!(trimmed.contains("name: \"com.android.permission\""));
        assert!(!trimmed.contains("name: \"com.android.permission-systemserverclasspath-fragment\""));
        assert!(!native_bridge_only_build(&["services"]));
    }
    #[test]
    fn private_only_java_api_generated_and_conscrypt_tests_preserve_others() {
       for (p,k,n) in [
         ("external/conscrypt/Android.bp","java_test","conscrypt-tests"),
         ("external/conscrypt/Android.bp","java_test","conscrypt-benchmarks"),
         ("packages/modules/Permission/service/Android.bp","java_sdk_library","service-permission"),
         ("packages/modules/Connectivity/framework-t/Android.bp","java_sdk_library","framework-connectivity-t"),
       ] {
         assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter()
           .any(|(path,kind,names)| *path==p && *kind==k && names.contains(&n)));
       }
       let original="java_sdk_library {\n    name: \"service-permission\",\n}\ncc_library {\n    name: \"libpermission_native\",\n}\n";
       let filtered=private_without_named_java_module(original,"java_sdk_library","service-permission").unwrap();
       assert!(filtered.contains("libpermission_native"));
       assert!(!filtered.contains("name: \"service-permission\","));
       assert!(!native_bridge_only_build(&["services"]));
    }
    #[test]
    fn nativebridge_strict_scope_keeps_product_camera_input_other_modules() {
        let modules=PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        for (path,kind,modname) in [
          ("frameworks/av/services/camera/libcameraservice/Android.bp",
            "cc_library_static","libcameraservice_device_independent"),
          ("frameworks/native/libs/input/Android.bp","cc_library","libinput"),
        ] {
          assert!(modules.iter().any(|(p,k,n)| *p==path && *k==kind && n.contains(&modname)));
        }
        let original="cc_library {\n    name: \"libinput\",\n}\ncc_library_static {\n    name: \"libinput_from_rust_to_cpp\",\n}\n";
        let private=private_without_named_java_module(original,"cc_library","libinput").unwrap();
        assert!(!private.contains("name: \"libinput\","));
        assert!(private.contains("libinput_from_rust_to_cpp"));
        assert!(!private_nativebridge_unrelated_paths(&["droidloom-native-bridge"])
            .contains(&"frameworks/native/libs/input"));
        assert!(!native_bridge_only_build(&["services"]));
    }
    #[test]
    fn nativebridge_unselected_release_tools_preserve_source_and_libraries() {
        let modules=PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        assert!(modules.iter().any(|(p,k,n)| *p=="build/make/tools/releasetools/merge/Android.bp"
           && *k=="python_binary_host" && n.contains(&"merge_target_files")));
        assert!(modules.iter().any(|(p,k,n)| *p=="build/make/tools/releasetools/Android.bp"
           && *k=="python_test_host" && n.contains(&"releasetools_test")));
        let example="python_binary_host {\n    name: \"merge_target_files\",\n}\nfilegroup {\n    name: \"releasetools_merge_sources\",\n}\n";
        let private=private_without_named_java_module(example, "python_binary_host", "merge_target_files").unwrap();
        assert!(!private.contains("name: \"merge_target_files\""));
        assert!(private.contains("releasetools_merge_sources"));
        assert!(!native_bridge_only_build(&["services"]));
    }
    #[test]
    fn private_nativebridge_filters_only_original_libcore_java_test_aggregates() {
        let names = PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        assert!(names.iter().any(|(p,k,n)| *p=="libcore/JavaLibrary.bp"
           && *k=="java_test" && n.contains(&"core-tests")
           && n.contains(&"libcore-crypto-tests")));
        let source="java_test {\n    name: \"libcore-crypto-tests\",\n}\njava_library {\n    name: \"core-oj\",\n}\n";
        let private=private_without_named_java_module(source,"java_test","libcore-crypto-tests").unwrap();
        assert!(!private.contains("libcore-crypto-tests"));
        assert!(private.contains("core-oj"));
        assert!(!private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]).contains(&"libcore"));
        assert!(!native_bridge_only_build(&["services"]));
    }
    #[test]
    fn private_apex_testdata_and_unselected_ota_publication_modules_are_not_translator() {
        assert!(private_nativebridge_unrelated_paths(&["droidloom-native-bridge"])
            .contains(&"system/apex/apexer/testdata"));
        assert!(!private_nativebridge_unrelated_paths(&["services"])
            .contains(&"system/apex/apexer/testdata"));
        let scoped=PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        let wanted=["ota_from_target_files","sign_target_files_apks"];
        assert!(scoped.iter().any(|(p,k,n)| *p=="build/make/tools/releasetools/Android.bp"
            && *k=="python_binary_host" && wanted.iter().all(|w| n.contains(w))));
        assert!(scoped.iter().any(|(p,k,n)| *p=="build/make/tools/releasetools/Android.bp"
            && *k=="python_library_host" && n.contains(&"releasetools_ota_from_target_files")));
        assert!(!private_nativebridge_unrelated_paths(&["droidloom-native-bridge"])
            .contains(&"build/make/tools/releasetools"));
    }
    #[test]
    fn private_nativebridge_only_exact_media_extractors_not_native_translation() {
        let names=PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        for (path, kind, name) in [
          ("frameworks/av/media/module/extractors/mkv/Android.bp","cc_library","libmkvextractor"),
          ("frameworks/av/media/module/extractors/ogg/Android.bp","cc_library","liboggextractor"),
          ("frameworks/av/media/module/extractors/mpeg2/Android.bp","cc_library","libmpeg2extractor"),
          ("frameworks/av/media/module/mpeg2ts/Android.bp","cc_library_static","libstagefright_mpeg2support"),
          ("frameworks/av/media/module/mpeg2ts/Android.bp","cc_library_static","libstagefright_mpeg2support_nocrypto"),
        ] {
          assert!(names.iter().any(|(p,k,ns)| *p==path && *k==kind && ns.contains(&name)));
        }
        let original="package {\n    default_applicable_licenses: [\"license\"],\n}\ncc_library_static {\n    name: \"libstagefright_mpeg2support\",\n}\ncc_library_headers {\n    name: \"libstagefright_mpeg2support_headers\",\n}\n";
        let scoped=private_without_named_java_module(original,"cc_library_static","libstagefright_mpeg2support").unwrap();
        assert!(scoped.contains("libstagefright_mpeg2support_headers"));
        assert!(!scoped.contains("    name: \"libstagefright_mpeg2support\","));
        assert!(!native_bridge_only_build(&["services"]));
    }
    #[test]
    fn nativebridge_private_ci_and_ota_scope_excludes_only_unselected_host_targets() {
        let filtered = PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        assert!(filtered.iter().any(|(p,k,names)| *p=="build/make/ci/Android.bp"
            && *k=="python_test_host" && names.len()==3));
        assert!(filtered.iter().any(|(p,k,names)| *p=="build/make/tools/releasetools/Android.bp"
            && *k=="python_binary_host" && names.contains(&"merge_ota")));
        let source="python_binary_host {\n    name: \"merge_ota\",\n}\npython_library_host {\n    name: \"ota_utils_lib\",\n}\n";
        let original=private_without_named_java_module(source,"python_binary_host","merge_ota").unwrap();
        assert!(!original.contains("merge_ota"));
        assert!(original.contains("ota_utils_lib"));
        assert!(!native_bridge_only_build(&["services"]));
        assert!(!private_nativebridge_unrelated_paths(&["services"]).contains(&"build/make/tools/releasetools"));
    }
    #[test]
    fn private_nativebridge_omits_only_host_python_tool_tests() {
        let dirs=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        for p in ["build/make/tools/tool_event_logger","build/make/tools/edit_monitor",
                  "build/soong/tests"] {
            assert!(dirs.contains(&p));
            assert!(!private_nativebridge_unrelated_paths(&["services"]).contains(&p));
        }
        let modules=PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        for (p,n) in [
          ("external/protobuf/Android.bp","libprotobuf-python-test"),
          ("build/soong/bloaty/Android.bp","bloaty_merger_test"),
        ] {
            assert!(modules.iter().any(|(path,k,names)| *path==p
                && *k=="python_test_host" && names.contains(&n)));
        }
        assert!(!dirs.contains(&"build/soong"));
        assert!(!dirs.contains(&"external/protobuf"));
        assert!(!dirs.contains(&"bionic"));
    }
    #[test]
    fn nativebridge_private_statsd_apex_does_not_hide_native_statsd() {
        let filtered=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(filtered.contains(&"packages/modules/StatsD/apex"));
        assert!(!filtered.contains(&"packages/modules/StatsD"));
        assert!(!filtered.contains(&"packages/modules/StatsD/statsd"));
        assert!(!filtered.contains(&"packages/modules/StatsD/framework"));
        assert!(!private_nativebridge_unrelated_paths(&["services"]).contains(
           &"packages/modules/StatsD/apex"));
    }
    #[test]
    fn nativebridge_private_only_statsd_java_sdk_and_historical_tests() {
        let paths=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(paths.contains(&"packages/modules/Connectivity/tests/cts/net/appForApi23"));
        assert!(paths.contains(&"system/tools/hidl/test/system_api_test"));
        assert!(!paths.contains(&"packages/modules/Connectivity"));
        assert!(!paths.contains(&"packages/modules/StatsD/framework"));
        assert!(!paths.contains(&"system/tools/hidl"));
        let selected=PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        assert!(selected.iter().any(|(p,k,n)| *p=="packages/modules/StatsD/framework/Android.bp"
           && *k=="java_sdk_library" && n.contains(&"framework-statsd")));
        assert!(!private_nativebridge_unrelated_paths(&["services"]).contains(
             &"packages/modules/Connectivity/tests/cts/net/appForApi23"));
    }
    #[test]
    fn nativebridge_original_androidx_annotation_is_retained_without_alpha_catalog() {
        let paths=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(!paths.contains(&"prebuilts/sdk/current/androidx"));
        for fragment in ["collection","core","leanback","transition","webkit"] {
            let original=format!("prebuilts/sdk/current/androidx/m2repository/androidx/{fragment}");
            assert!(paths.contains(&original.as_str()));
        }
        let original=PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        assert!(!original.iter().any(|(p,_,names)| *p=="prebuilts/sdk/current/androidx/m2repository/androidx/annotation/annotation-jvm/1.10.0/Android.bp"
                && names.contains(&"androidx.annotation_annotation")));
        assert!(!private_nativebridge_unrelated_paths(&["services"]).contains(&"prebuilts/sdk/current/androidx"));
    }
    #[test]
    fn nativebridge_private_java_ojluni_test_scope_keeps_original_core_runtime() {
        let selected=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(selected.contains(&"libcore/ojluni/src/test"));
        assert!(!selected.contains(&"libcore/ojluni"));
        assert!(!selected.contains(&"libcore"));
        assert!(!selected.contains(&"art"));
        assert!(!private_nativebridge_unrelated_paths(&["services"]).contains(&"libcore/ojluni/src/test"));
    }
    #[test]
    fn nativebridge_private_media_sdk_merge_keeps_real_media_runtime() {
        let x=PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        assert!(x.iter().any(|(p,k,n)| *p=="packages/modules/Media/apex/Android.bp"
            && *k=="sdk" && n.contains(&"media-module-sdk")));
        let original="package {\n    default_visibility: [\"//visibility:public\"],\n}\nsdk {\n    name: \"media-module-sdk\",\n    apexes: [\"com.android.media\"],\n}\n";
        let scoped=private_without_named_java_module(original,"sdk","media-module-sdk").unwrap();
        assert!(scoped.contains("default_visibility"));
        assert!(!scoped.contains("media-module-sdk"));
        assert!(!native_bridge_only_build(&["services"]));
    }
    #[test]
    fn nativebridge_only_media_apex_packaging_scope_keeps_native_media() {
        let s=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(s.contains(&"frameworks/av/apex"));
        assert!(!s.contains(&"frameworks/av"));
        assert!(!s.contains(&"frameworks/av/media"));
        assert!(!private_nativebridge_unrelated_paths(&["services"]).contains(&"frameworks/av/apex"));
    }
    #[test]
    fn nativebridge_only_java_stub_aggregations_do_not_hide_core_runtime() {
        let dirs=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        for p in ["frameworks/libs/modules-utils/java/com/android/modules/utils/pm",
                  "frameworks/libs/modules-utils/java/com/android/modules/utils/build",
                  "packages/modules/Media/apex/service"] {
            assert!(dirs.contains(&p));
            assert!(!private_nativebridge_unrelated_paths(&["services"]).contains(&p));
        }
        let selected=PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        assert!(selected.iter().any(|(p,k,ns)| *p=="frameworks/base/Android.bp"
            && *k=="java_library" && ns.contains(&"framework-non-updatable-unbundled-impl-libs")));
        assert!(selected.iter().any(|(p,k,ns)| *p=="packages/modules/Connectivity/staticlibs/Android.bp"
            && *k=="java_library" && ns.contains(&"net-utils-device-common-mdns-standalone-build-test")));
        assert!(!dirs.contains(&"frameworks/base"));
        assert!(!dirs.contains(&"packages/modules/Connectivity"));
        assert!(!dirs.contains(&"art"));
    }
    #[test]
    fn private_media_extractor_fuzzer_scope_preserves_original_media() {
        let paths=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(paths.contains(&"frameworks/av/media/module/extractors/fuzzers"));
        assert!(!paths.contains(&"frameworks/av/media/module/extractors"));
        assert!(!paths.contains(&"frameworks/av/media/module"));
        assert!(!private_nativebridge_unrelated_paths(&["services"])
             .contains(&"frameworks/av/media/module/extractors/fuzzers"));
    }
    #[test]
    fn sensor_vts_certification_is_private_exclusion_not_sensor_library() {
        let selected=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(selected.contains(&"hardware/interfaces/sensors/aidl/vts"));
        assert!(!selected.contains(&"hardware/interfaces/sensors/aidl"));
        assert!(!selected.contains(&"hardware/interfaces/sensors/aidl/convert"));
        assert!(!private_nativebridge_unrelated_paths(&["services"])
            .contains(&"hardware/interfaces/sensors/aidl/vts"));
    }
    #[test]
    fn private_storage_proxy_host_tool_only_keeps_vendor_storage_proxy() {
        let m=PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().find(|(p,k,_)|
            *p=="system/core/trusty/storage/proxy/Android.bp" && *k=="cc_binary_host").unwrap();
        assert_eq!(m.2, ["storageproxyd_host"]);
        let source="cc_binary {\n    name: \"storageproxyd\",\n}\ncc_binary_host {\n    name: \"storageproxyd_host\",\n}\n";
        let actual=private_without_named_java_module(source,"cc_binary_host","storageproxyd_host").unwrap();
        assert!(actual.contains("name: \"storageproxyd\""));
        assert!(!actual.contains("storageproxyd_host"));
        assert!(!native_bridge_only_build(&["services"]));
    }
    #[test]
    fn real_pinned_hwbinder_original_provider_is_preserved_in_private_api_graph() {
        let p=std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let root=p.join("../../android/manifest/m2-sparse-source-lock.json");
        assert!(root.is_file());
        let modules=std::env::current_dir();
        assert!(modules.is_ok());
        let file=std::fs::read_to_string(
            p.join("../../android/manifest/m2-sparse-source-lock.json")).unwrap();
        assert!(file.contains("frameworks/base"));
        // The real source retention logic must preserve the Java declaration,
        // and must fail rather than invent a provider when the exact pinned
        // 70-module original file is missing.
        assert!(private_nativebridge_without_java_api_stubs(
            "priv_apps = [\n]\njava_library {\n    name: \"hwbinder.stubs\",\n}\n").is_err());
    }
    #[test]
    fn pinned_java_api_stub_file_is_rejected_if_source_changes() {
        assert!(private_nativebridge_without_java_api_stubs("cc_library_shared {\n    name: \"native-needed\",\n}\n").is_err());
        assert!(private_nativebridge_without_java_api_stubs("java_library {\n    name: \"small\",\n}\n").is_err());
        assert!(!native_bridge_only_build(&["services"]));
    }

    #[test]
    fn private_api_stub_scope_removes_only_four_doc_targets() {
        assert!(!PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(|(p,_,_)| *p=="frameworks/base/api/StubLibraries.bp"));
        let source="non_updatable_exportable_droidstubs {\n    name: \"api-stubs-docs-non-updatable\",\n}\njava_library {\n    name: \"api-stubs-release\",\n}\n";
        let scoped=private_without_named_java_module(source,"non_updatable_exportable_droidstubs","api-stubs-docs-non-updatable").unwrap();
        assert!(scoped.contains("api-stubs-release"));
        assert!(!scoped.contains("docs-non-updatable"));
        assert!(!native_bridge_only_build(&["services"]));
    }

    #[test]
    fn original_connectivity_staticlibs_native_preserved_with_private_ipsec_java_scope() {
        let c=PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        assert!(c.iter().any(|(p,k,n)| *p=="packages/modules/Connectivity/staticlibs/Android.bp"
            && *k=="java_library" && n.contains(&"net-utils-framework-ipsec")));
        assert!(!private_nativebridge_unrelated_paths(&["droidloom-native-bridge"])
            .contains(&"packages/modules/Connectivity"));
        assert!(!private_nativebridge_unrelated_paths(&["droidloom-native-bridge"])
            .contains(&"external/cronet"));
        assert!(!native_bridge_only_build(&["services"]));
    }
    #[test]
    fn cts_multidevice_python_test_only_scope_keeps_runtime() {
        let p=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(p.contains(&"packages/modules/Connectivity/tests/cts/multidevices"));
        assert!(!p.contains(&"packages/modules/Connectivity"));
        assert!(!p.contains(&"packages/modules/NetworkStack"));
        assert!(!private_nativebridge_unrelated_paths(&["services"]).contains(
           &"packages/modules/Connectivity/tests/cts/multidevices"));
        assert!(!PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter()
          .any(|(path,kind,n)| *path=="external/protobuf/Android.bp"
           && *kind=="python_library" && n.contains(&"libprotobuf-python")));
    }
    #[test]
    fn nativebridge_only_java_test_scope_preserves_real_core_and_debian_aidl() {
        let paths=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        for p in ["external/libtextclassifier/java",
                  "external/libtextclassifier/notification",
                  "packages/modules/Virtualization/android/TerminalApp"] {
            assert!(paths.contains(&p));
            assert!(!private_nativebridge_unrelated_paths(&["services"]).contains(&p));
        }
        let scope=PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        for (file,typ,n) in [
            ("libcore/JavaLibrary.bp","java_library_static","core-test-rules"),
            ("external/libphonenumber/Android.bp","java_library","libphonenumber_test"),
            ("frameworks/libs/modules-utils/java/com/android/modules/utils/build/Android.bp",
                 "java_library","modules-utils-build_system"),
            ("packages/modules/Virtualization/libs/debian_service/Android.bp",
                 "java_library","debian-service-grpclib-lite"),
        ] {
            assert!(scope.iter().any(|(p,k,names)| *p==file && *k==typ && names.contains(&n)));
        }
        assert!(!paths.contains(&"libcore"));
        assert!(!paths.contains(&"packages/modules/Virtualization/libs/debian_service"));
        assert!(!paths.contains(&"external/libtextclassifier/native"));
    }
    #[test]
    fn private_adb_root_keeps_three_exact_original_native_defaults_only() {
        let src="package {\n    default_applicable_licenses: [\"sample\"],\n}\nlicense {\n    name: \"sample\",\n}\ncc_defaults {\n    name: \"adb_defaults\",\n}\ncc_defaults {\n    name: \"adbd_defaults\",\n}\ncc_defaults {\n    name: \"host_adbd_supported\",\n}\ncc_binary_host {\n    name: \"adb\",\n}\n";
        let filtered=private_nativebridge_adb_root_defaults_only(src).unwrap();
        for name in ["adb_defaults","adbd_defaults","host_adbd_supported"] {
            assert!(filtered.contains(&format!("name: \"{name}\"")));
        }
        assert!(!filtered.contains("name: \"adb\""));
        assert!(private_nativebridge_adb_root_defaults_only("package {\n}\n").is_err());
        assert!(!native_bridge_only_build(&TARGETS));
    }
    #[test]
    fn private_httpengine_framework_java_helpers_keep_android_native_target_set() {
        for (p,k,n) in [
          ("external/cronet/android/Android.bp","java_library","httpengine_internal"),
          ("frameworks/base/Android.bp","java_library","framework-internal-utils")
        ] {
            assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter()
              .any(|(path,kind,names)| *path==p && *kind==k && names.contains(&n)));
        }
        let dirs=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(!dirs.contains(&"frameworks/base"));
        assert!(!dirs.contains(&"external/cronet/android"));
        assert!(!dirs.contains(&"external/cronet"));
        assert!(private_nativebridge_unrelated_paths(&TARGETS).is_empty());
    }
    #[test]
    fn private_nativebridge_cronet_stable_scope_keeps_real_product_root() {
        let p=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(p.contains(&"external/cronet/stable"));
        assert!(!p.contains(&"external/cronet"));
        assert!(!p.contains(&"external/cronet/android"));
        assert!(!p.contains(&"frameworks/libs/binary_translation"));
        assert!(private_nativebridge_unrelated_paths(&TARGETS).is_empty());
        assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(|(path,kind,names)|
          *path=="external/cronet/Android.bp" &&
          *kind=="java_library" && names.contains(&"cronet_aml_api_java")));
        assert!(!PRIVATE_NATIVEBRIDGE_UNRELATED_DIRECTORIES.contains(&"external/cronet"));
    }
    #[test]
    fn private_art_systemserverclasspath_fragment_keeps_native_art_runtime() {
        assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(|(p,k,n)|
          *p=="art/build/boot/Android.bp" &&
          *k=="systemserverclasspath_fragment" &&
          n.contains(&"art-systemserverclasspath-fragment")));
        assert!(!private_nativebridge_unrelated_paths(&["droidloom-native-bridge"])
          .contains(&"art"));
        assert!(!private_nativebridge_unrelated_paths(&["droidloom-native-bridge"])
          .contains(&"art/build/boot"));
        assert!(private_nativebridge_unrelated_paths(&TARGETS).is_empty());
    }
    #[test]
    fn private_networkstack_api_and_art_java_stubs_are_exact_module_scopes() {
        for (p,k,n) in [
            ("packages/modules/Connectivity/framework/Android.bp","java_library","framework-connectivity-pre-jarjar-without-cronet"),
            ("packages/modules/Connectivity/staticlibs/Android.bp","java_library","net-utils-device-common-ip"),
            ("art/libartservice/service/Android.bp","java_sdk_library","service-art"),
            ("packages/modules/NetworkStack/Android.bp","android_library","NetworkStackApiStableLib"),
            ("packages/modules/NetworkStack/Android.bp","android_library","NetworkStackApiCurrentLib"),
        ] {
            assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter()
              .any(|(path,kind,names)| *path==p && *kind==k && names.contains(&n)));
        }
        assert!(!private_nativebridge_unrelated_paths(&["droidloom-native-bridge"])
          .contains(&"packages/modules/Connectivity"));
        assert!(!private_nativebridge_unrelated_paths(&["droidloom-native-bridge"])
          .contains(&"packages/modules/NetworkStack"));
        assert!(TARGETS.contains(&"libservice-connectivity"));
    }
    #[test]
    fn private_network_java_auxiliary_modules_keep_full_native_service_graph() {
        let modules=PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        for (p,k,n) in [
            ("packages/modules/Connectivity/staticlibs/Android.bp","java_library","net-utils-service-wifi"),
            ("packages/modules/Connectivity/staticlibs/Android.bp","java_library","net-utils-connectivity-apks"),
            ("packages/modules/NetworkStack/Android.bp","java_library","DhcpPacketLib"),
            ("packages/modules/Connectivity/service/ServiceConnectivityResources/Android.bp","android_library","ServiceConnectivityResourcesLib"),
            ("packages/modules/Bluetooth/framework/Android.bp","java_library","framework-bluetooth-pre-jarjar"),
        ] {
            assert!(modules.iter().any(|(path,kind,names)|
              *path==p && *kind==k && names.contains(&n)));
        }
        for p in ["packages/modules/Connectivity","packages/modules/NetworkStack",
            "packages/modules/Bluetooth"] {
            assert!(!private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]).contains(&p));
        }
        assert!(private_nativebridge_unrelated_paths(&TARGETS).is_empty());
    }
    #[test]
    fn private_java_wifi_bluetooth_artservice_test_scope_keeps_product_native() {
        for (path,kind,name) in [
            ("packages/modules/Bluetooth/framework/Android.bp","java_sdk_library","framework-bluetooth"),
            ("packages/modules/Wifi/framework/Android.bp","java_sdk_library","framework-wifi"),
            ("packages/modules/Wifi/framework/Android.bp","java_library","framework-wifi-pre-jarjar"),
            ("art/libartservice/service/Android.bp","java_library","service-art-tests"),
            ("art/libartservice/service/Android.bp","android_test","ArtServiceTests"),
        ] {
            assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter()
              .any(|(p,k,ns)| *p==path && *k==kind && ns.contains(&name)));
        }
        let private=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        for path in ["packages/modules/Wifi/framework",
            "packages/modules/Bluetooth/framework","art/libartservice/service"] {
            assert!(!private.contains(&path));
        }
        assert!(private_nativebridge_unrelated_paths(&TARGETS).is_empty());
    }
    #[test]
    fn private_conscrypt_apex_scope_does_not_remove_original_native_tls() {
        let private=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(private.contains(&"external/conscrypt/apex"));
        assert!(!private.contains(&"external/conscrypt"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        assert!(private_nativebridge_unrelated_paths(&TARGETS).is_empty());
    }
    #[test]
    fn private_nativebridge_java_tethering_conscrypt_scope_is_not_product_scope() {
        let original=PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        for (path,kind,name) in [
            ("packages/modules/Connectivity/Tethering/common/TetheringLib/Android.bp","java_sdk_library","framework-tethering"),
            ("packages/modules/Connectivity/Tethering/common/TetheringLib/Android.bp","java_library","framework-tethering-pre-jarjar"),
            ("packages/modules/Connectivity/staticlibs/Android.bp","java_library","net-utils-services-common"),
            ("external/conscrypt/Android.bp","java_sdk_library","framework-conscrypt-nsc"),
        ] {
            assert!(original.iter().any(|(p,k,n)| *p==path && *k==kind && n.contains(&name)));
        }
        assert!(!private_nativebridge_unrelated_paths(&["droidloom-native-bridge"])
                 .contains(&"packages/modules/Connectivity/Tethering/common/TetheringLib"));
        assert!(!private_nativebridge_unrelated_paths(&["droidloom-native-bridge"])
                 .contains(&"external/conscrypt"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        assert!(TARGETS.contains(&"libservice-connectivity"));
    }
    #[test]
    fn nativebridge_only_inputflinger_subgraph_is_not_full_product_scope() {
        let p=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(p.contains(&"frameworks/native/services/inputflinger"));
        assert!(!p.contains(&"frameworks/native/services"));
        assert!(!p.contains(&"frameworks/native/libs/input"));
        assert!(!p.contains(&"frameworks/libs/binary_translation"));
        assert!(private_nativebridge_unrelated_paths(&["libinputflinger","services"]).is_empty());
        assert!(TARGETS.contains(&"libinputflinger"));
        assert!(TARGETS.contains(&"droidloom-native-bridge"));
    }
    #[test]
    fn private_nativebridge_excludes_only_guest_linux_vm_manager_host_cli() {
        let native=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        let path="packages/modules/Virtualization/guest/linux_vm_manager";
        assert!(native.contains(&path));
        assert!(!native.contains(&"packages/modules/Virtualization/guest"));
        assert!(!native.contains(&"packages/modules/Virtualization"));
        assert!(!native.contains(&"hardware/interfaces/sensors/common/convert"));
        assert!(!native.contains(&"hardware/interfaces/sensors/aidl/convert"));
        assert!(!private_nativebridge_unrelated_paths(&["services"]).contains(&path));
    }
    #[test]
    fn private_nativebridge_does_not_include_avf_apex_bootclasspath_packaging() {
        let names=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(names.contains(&"packages/modules/Virtualization/build/apex"));
        assert!(!names.contains(&"packages/modules/Virtualization/build"));
        assert!(!names.contains(&"packages/modules/Virtualization/libs"));
        assert!(!private_nativebridge_unrelated_paths(&["services"]).contains(
          &"packages/modules/Virtualization/build/apex"));
    }
    #[test]
    fn private_cronet_only_excludes_test_modules_not_apex_defaults() {
        let only=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(!only.contains(&"external/cronet"));
        let c=PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        assert!(c.iter().any(|(p,k,ns)| *p=="external/cronet/Android.bp"
           && *k=="android_test" && ns.contains(&"NetHttpCoverageTests")));
        let orig="apex_defaults {\n    name: \"CronetInTetheringApexDefaults\",\n}\njava_library {\n    name: \"cronet_aml_java__testing\",\n}\n";
        let scoped=private_without_named_java_module(orig,"java_library","cronet_aml_java__testing").unwrap();
        assert!(scoped.contains("CronetInTetheringApexDefaults"));
        assert!(!scoped.contains("cronet_aml_java__testing"));
        assert!(!native_bridge_only_build(&["services"]));
    }
    #[test]
    fn private_nativebridge_does_not_instantiate_global_api_or_cronet_java_impl() {
        let entries=PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        for (path, kind, name) in [
            ("external/cronet/Android.bp","java_library","cronet_aml_java"),
            ("frameworks/base/api/Android.bp","combined_apis","frameworks-base-api"),
        ] {
            assert!(entries.iter().any(|(p,k,n)| *p==path && *k==kind && n.contains(&name)));
        }
        let source="bootstrap_go_package {\n    name: \"soong-api\",\n}\ncombined_apis {\n    name: \"frameworks-base-api\",\n}\n";
        let filtered=private_without_named_java_module(
            source,"combined_apis","frameworks-base-api").unwrap();
        assert!(filtered.contains("soong-api"));
        assert!(!filtered.contains("frameworks-base-api"));
        assert!(!native_bridge_only_build(&["services"]));
    }
    #[test]
    fn original_vcn_provider_kept_when_tethering_bootclasspath_is_in_graph() {
        assert!(!private_nativebridge_unrelated_paths(&["droidloom-native-bridge"])
            .contains(&"packages/modules/Connectivity/Vcn/framework-b"));
        assert!(!private_nativebridge_unrelated_paths(&["services"])
            .contains(&"packages/modules/Connectivity/Vcn/framework-b"));
        // Never invent a source declaration or a stub library for the
        // bootclasspath: the real AOSP source provider stays in the graph.
        let src="java_sdk_library {\n    name: \"framework-connectivity-b\",\n}\njava_library {\n    name: \"vcn-utils-framework-ipsec\",\n}\n";
        let filtered=private_without_named_java_module(
          src,"java_library","vcn-utils-framework-ipsec").unwrap();
        assert!(filtered.contains("framework-connectivity-b"));
        assert!(!filtered.contains("vcn-utils-framework-ipsec"));
    }
    #[test]
    fn private_nativebridge_scopes_java_media_vcn_virtualization_without_dropping_native() {
        let private=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        let standalone=["packages/modules/Virtualization/libs/framework-virtualization"];
        for path in standalone {
            assert!(private.contains(&path));
            assert!(!private_nativebridge_unrelated_paths(&["services"]).contains(&path));
        }
        for (path, kind, name) in [
            ("packages/modules/Media/apex/framework/Android.bp", "java_library", "extractor-impl"),
            ("packages/modules/Media/apex/framework/Android.bp", "java_sdk_library", "framework-media"),
            ("packages/modules/Connectivity/staticlibs/Android.bp", "java_library", "net-utils-framework-vcn"),
        ] {
            assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(|(p,k,n)| *p==path && *k==kind && n.contains(&name)));
        }
        assert!(!private.contains(&"packages/modules/Connectivity/Vcn/framework-b"));
        assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(|(p,k,n)|
            *p=="packages/modules/Connectivity/Vcn/framework-b/Android.bp" &&
            *k=="java_library" && n.contains(&"vcn-utils-framework-ipsec")));
        assert!(!private.contains(&"packages/modules/Media/apex/framework"));
        assert!(!private.contains(&"packages/modules/Connectivity/staticlibs"));
        assert!(!private.contains(&"packages/modules/Virtualization/libs"));
    }
    #[test]
    fn private_nativebridge_excludes_only_unselected_java_ui_and_coverage_trees() {
        let p=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        let expected=[
          "frameworks/base/packages/SettingsLib",
          "frameworks/libs/modules-utils/java/com/android/modules/utils/testing",
          "external/libtextclassifier/coverage",
        ];
        for x in expected {
            assert!(p.contains(&x), "missing private-only graph selector {x}");
            assert!(!private_nativebridge_unrelated_paths(&["services"]).contains(&x));
        }
        assert!(!p.contains(&"frameworks/base"));
        assert!(!p.contains(&"frameworks/libs/modules-utils"));
        assert!(!p.contains(&"external/libtextclassifier/native"));
    }
    #[test]
    fn private_audio_preprocessing_benchmark_scope_is_not_product_scope() {
        let selected=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(selected.contains(&"frameworks/av/media/libeffects/preprocessing/benchmarks"));
        assert!(!selected.contains(&"frameworks/av/media/libeffects/preprocessing"));
        assert!(!private_nativebridge_unrelated_paths(&["services"]).contains(
          &"frameworks/av/media/libeffects/preprocessing/benchmarks"));
    }
    #[test]
    fn private_audio_preprocessing_test_scope_preserves_production_modules() {
        let scoped=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(scoped.contains(&"frameworks/av/media/libeffects/preprocessing/tests"));
        assert!(!scoped.contains(&"frameworks/av/media/libeffects/preprocessing"));
        assert!(!scoped.contains(&"frameworks/av/media/libeffects"));
        assert!(!private_nativebridge_unrelated_paths(&["services"]).contains(
            &"frameworks/av/media/libeffects/preprocessing/tests"));
    }
    #[test]
    fn private_aconfig_diff_tradefed_scope_keeps_real_flag_provider() {
        assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(|(p,kind,names)|
          *p=="build/make/tools/aconfig/aconfig_diff/tests/Android.bp"
          && *kind=="java_test_host" && names.contains(&"aconfig_diff_test")));
        let original="java_test_host {\n    name: \"aconfig_diff_test\",\n    libs: [\"tradefed\"],\n}\ncc_library {\n    name: \"server_configurable_flags\",\n}\n";
        let scope=private_without_named_java_module(original,"java_test_host","aconfig_diff_test").unwrap();
        assert!(scope.contains("server_configurable_flags"));
        assert!(!scope.contains("tradefed"));
        assert!(!native_bridge_only_build(&["services"]));
    }
    #[test]
    fn private_service_manager_test_scope_does_not_hide_production_services() {
        let types = PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES;
        assert!(types.iter().any(|(p,k,mods)| *p == "frameworks/native/cmds/servicemanager/Android.bp"
            && *k == "cc_test" && mods.contains(&"servicemanager_test")));
        assert!(types.iter().any(|(p,k,mods)| *p == "frameworks/native/cmds/servicemanager/Android.bp"
            && *k == "cc_test_host" && mods.contains(&"servicemanager_unittest")));
        let src="cc_binary {\n    name: \"servicemanager\",\n}\ncc_test {\n    name: \"servicemanager_test\",\n    static_libs: [\"libperfetto_c\"],\n}\n";
        let scoped=private_without_named_java_module(src,"cc_test","servicemanager_test").unwrap();
        assert!(scoped.contains("name: \"servicemanager\""));
        assert!(!scoped.contains("libperfetto_c"));
        assert!(!private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]).contains(&"frameworks/native/cmds/servicemanager"));
        assert!(!native_bridge_only_build(&["services"]));
    }
    #[test]
    fn private_update_engine_retains_only_original_header_provider() {
        let src="package {\n    default_applicable_licenses: [\"sample\"]\n}\nlicense {\n    name: \"sample\",\n}\ncc_library_static {\n    name: \"lz4diff\",\n}\ncc_library_headers {\n    name: \"libupdate_engine_headers\",\n    export_include_dirs: [\".\"],\n}\n";
        let filtered=private_nativebridge_update_engine_headers_only(src).unwrap();
        assert!(filtered.contains("libupdate_engine_headers"));
        assert!(!filtered.contains("lz4diff"));
        assert!(filtered.contains("default_applicable_licenses"));
        assert!(filtered.contains("license {"));
        assert!(private_nativebridge_update_engine_headers_only("package {\n}
").is_err());
    }

    #[test]
    fn private_translator_has_no_ota_or_apex_list_tool_graph() {
        let p=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(!p.contains(&"system/update_engine"));
        assert!(p.contains(&"system/apex/tools/apex-ls"));
        assert!(!p.contains(&"system/apex"));
        assert!(!p.contains(&"system/core"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
    }

    #[test]
    fn nativebridge_java_aconfig_group_has_matched_private_scope() {
        assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(|(p,k,n)| *p=="frameworks/base/AconfigFlags.bp" && *k=="aconfig_declarations_group" && n.contains(&"framework-minus-apex-aconfig-declarations")));
        let original="aconfig_declarations_group {\n    name: \"framework-minus-apex-aconfig-declarations\",\n    java_aconfig_libraries: [\"flags-lib\"],\n}\njava_aconfig_library {\n    name: \"flags-lib\",\n}\n";
        let partial=private_without_named_java_module(original,"aconfig_declarations_group","framework-minus-apex-aconfig-declarations").unwrap();
        let scoped=private_nativebridge_without_java_aconfigs(&partial,1).unwrap();
        assert!(!scoped.contains("flags-lib"));
        assert!(!scoped.contains("framework-minus-apex-aconfig-declarations"));
        assert!(!native_bridge_only_build(&["services"]));
    }

    #[test]
    fn nativebridge_private_scope_excludes_flash_tool_and_vintf_tests() {
        let paths=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(paths.contains(&"system/core/fastboot"));
        assert!(paths.contains(&"system/libvintf/test"));
        assert!(!paths.contains(&"system/core"));
        assert!(!paths.contains(&"system/libvintf"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
    }

    #[test]
    fn private_java_aconfig_scoper_preserves_native_declarations() {
        let original="aconfig_declarations {\n    name: \"real-flags\",\n}\njava_aconfig_library {\n    name: \"unselected-java\",\n    target: {\n        host: { enabled: true },\n    },\n}\ncc_aconfig_library {\n    name: \"real-native-cc\",\n}\n";
        let filtered=private_nativebridge_without_java_aconfigs(original,1).unwrap();
        assert!(filtered.contains("real-flags"));
        assert!(filtered.contains("real-native-cc"));
        assert!(!filtered.contains("unselected-java"));
        assert!(private_nativebridge_without_java_aconfigs(original,2).is_err());
        assert!(private_nativebridge_without_java_aconfigs("java_aconfig_library {\n",1).is_err());
        assert!(!native_bridge_only_build(&["services"]));
    }

    #[test]
    fn private_translator_scopes_dsp_effects_but_keeps_other_media() {
        for (path,kind,name) in [
            ("frameworks/av/media/libeffects/preprocessing/Android.bp","cc_library","libaudiopreprocessing"),
            ("frameworks/av/media/libeffects/preprocessing/Android.bp","cc_library_shared","libpreprocessingaidl"),
            ("frameworks/av/media/module/foundation/Android.bp","cc_library_static","libstagefright_foundation_colorutils_ndk"),
        ] {
            assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(|(p,k,n)| *p==path && *k==kind && n.contains(&name)));
        }
        assert!(!native_bridge_only_build(&["services"]));
    }

    #[test]
    fn private_translator_omits_unrelated_lint_and_sepolicy_snapshots_only() {
        let subset=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        for path in ["tools/lint_checks/utils", "system/sepolicy/prebuilts/api/202504", "system/sepolicy/microdroid"] {
            assert!(subset.contains(&path));
        }
        assert!(!subset.contains(&"system/sepolicy"));
        assert!(!subset.contains(&"system/sepolicy/build"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        assert!(!PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(|(p,k,n)|
            *p=="external/protobuf/Android.bp" && *k=="python_library" && n.contains(&"libprotobuf-python")));
    }

    #[test]
    fn nativebridge_excludes_java_catalog_but_preserves_droidloom_cxx_native_targets() {
        let scope=private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(!scope.contains(&"prebuilts/sdk/current/androidx"));
        assert!(scope.contains(&"prebuilts/sdk/current/androidx/m2repository/androidx/collection"));
        assert!(scope.contains(&"packages/modules/Virtualization/libs/libcompos_common/external/test"));
        assert!(!scope.contains(&"vendor/droidloom"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        // The late vendor Java filter must not be listed among filters
        // that run before the source mirror.
        assert!(!PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(|(p,_,_)| *p=="vendor/droidloom/Android.bp"));
        let original="android_app {\n    name: \"DroidloomIME\",\n}\nandroid_app {\n    name: \"DroidloomHome\",\n}\njava_binary {\n    name: \"droidloom-input-bridge\",\n}\njava_library {\n    name: \"DroidloomSystemUIProbe\",\n}\ncc_library_shared {\n    name: \"libdroidloom_transport\",\n}\n";
        let filtered=private_nativebridge_vendor_cxx_only(original).unwrap();
        assert!(!filtered.contains("DroidloomIME"));
        assert!(!filtered.contains("DroidloomHome"));
        assert!(!filtered.contains("droidloom-input-bridge"));
        assert!(!filtered.contains("DroidloomSystemUIProbe"));
        assert!(filtered.contains("libdroidloom_transport"));
        assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(|(p,k,n)| *p=="external/icu/android_icu4j/Android.bp" && *k=="java_test" && n.contains(&"android-icu4j-tests-core-only")));
    }

    #[test]
    fn nativebridge_java_feature_flag_scope_is_only_for_translator_proof() {
        for flag in [
            "android.chre.flags-aconfig-java",
            "telecom_flags_core_java_lib",
            "telecom_flags_core_java_aconfig_java_exported_lib",
            "power_flags_lib",
        ] {
            assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(|(p,k,n)| *p=="frameworks/base/AconfigFlags.bp" && *k=="java_aconfig_library" && n.contains(&flag)));
        }
        assert!(!native_bridge_only_build(&["services"]));
    }

    #[test]
    fn private_vintf_assembler_scope_keeps_real_libvintf() {
        assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(|(p,k,n)| *p=="system/libvintf/Android.bp" && *k=="cc_library_static" && n.contains(&"libassemblevintf")));
        assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(|(p,k,n)| *p=="system/libvintf/Android.bp" && *k=="cc_binary_host" && n.contains(&"assemble_vintf")));
        assert!(native_bridge_only_build(&["droidloom-native-bridge"]));
        assert!(!native_bridge_only_build(&["services"]));
    }

    #[test]
    fn nativebridge_private_host_test_graph_is_only_scoped_for_cpp_target() {
        for (path, kind, name) in [
            ("system/core/libutils/binder/Android.bp", "cc_test", "libutils_binder_test"),
            ("system/core/libutils/binder/Android.bp", "cc_test", "libutils_binder_test_custom_allocator"),
            ("build/make/tools/zipalign/Android.bp", "cc_library_host_static", "libzipalign"),
            ("build/make/tools/zipalign/Android.bp", "cc_binary_host", "zipalign"),
            ("build/make/tools/zipalign/Android.bp", "cc_test_host", "zipalign_tests"),
        ] {
            assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(|(p,k,n)| *p==path && *k==kind && n.contains(&name)));
        }
        assert!(native_bridge_only_build(&["droidloom-native-bridge"]));
        assert!(!native_bridge_only_build(&["services"]));
    }

    #[test]
    fn nativebridge_docs_scope_accepts_only_known_docs_and_rejects_new_source_modules() {
        let mut docs=String::new();
        for i in 0..20 {
            docs.push_str(&format!("droiddoc {{\n    name: \"{}\",\n}}\n", if i==0 {"ds-static-docs"} else if i==1 {"offline-sdk-docs"} else {"other-docs"}));
        }
        assert_eq!(private_nativebridge_without_unselected_api_docs(&docs).unwrap(), "");
        docs.push_str("cc_library {\n    name: \"production-needed\"\n}\n");
        assert!(private_nativebridge_without_unselected_api_docs(&docs).is_err());
        assert!(!native_bridge_only_build(&["services"]));
    }
    #[test]
    fn nativebridge_private_scope_keeps_full_product_declarations() {
        for (path,kind,name) in [
            ("frameworks/base/core/res/Android.bp","android_app","framework-res"),
            ("frameworks/base/AconfigFlags.bp","java_aconfig_library","android.graphics.egl.flags-aconfig-java"),
            ("prebuilts/sdk/current/androidx/Android.bp","android_library","androidx.leanback_leanback-nodeps"),
        ] {
            assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(|(p,k,ns)| *p==path && *k==kind && ns.contains(&name)));
        }
        assert!(!PRIVATE_NATIVEBRIDGE_UNRELATED_DIRECTORIES.contains(&"frameworks/base/core/res"));
    }

    #[test]
    fn private_androidx_webkit_wrapper_and_original_import_have_same_test_scope() {
        let r = PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter()
          .find(|(path, kind, _)| *path == "prebuilts/sdk/current/androidx/Android.bp" && *kind == "android_library")
          .unwrap();
        assert!(r.2.contains(&"androidx.webkit_webkit-nodeps"));
        let imported = PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter()
          .find(|(path, kind, _)| path.ends_with("/webkit/1.12.0-alpha02/Android.bp") && *kind == "android_library_import")
          .unwrap();
        assert!(imported.2.contains(&"androidx.webkit_webkit"));
        let original = "android_library {\n    name: \"androidx.webkit_webkit-nodeps\",\n    static_libs: [\"androidx.webkit_webkit\"],\n}\n\nandroid_library {\n    name: \"androidx.material_material-nodeps\",\n}\n";
        let filtered = private_without_named_java_module(original,"android_library","androidx.webkit_webkit-nodeps").unwrap();
        assert!(!filtered.contains("androidx.webkit_webkit-nodeps"));
        assert!(filtered.contains("androidx.material_material-nodeps"));
        assert!(!native_bridge_only_build(&["services"]));
    }

    #[test]
    fn private_nativebridge_scopes_only_unselected_skia_library() {
        let skia = "package {\n    default_applicable_licenses: [\"external_skia_license\"],\n}\n\ncc_library_static {\n    name: \"libskia_skcms\",\n}\n\ncc_library_static {\n    name: \"libskia\",\n    static_libs: [\"libwebp-decode\"],\n}\n";
        let scoped = private_without_named_java_module(skia,"cc_library_static","libskia").unwrap();
        assert!(scoped.contains("name: \"libskia_skcms\""));
        assert!(scoped.contains("default_applicable_licenses"));
        assert!(!scoped.contains("libwebp-decode"));
        assert!(private_without_named_java_module(&scoped,"cc_library_static","libskia").is_err());
        let modules = PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter()
            .find(|(path, kind, _)| *path == "external/skia/Android.bp" && *kind == "cc_library_static")
            .unwrap();
        assert_eq!(modules.2, ["libskia"]);
        assert!(!private_nativebridge_unrelated_paths(&["services"]).contains(&"external/skia"));
    }
    #[test]
    fn private_nativebridge_does_not_mask_missing_declarations_in_full_build() {
        assert!(!native_bridge_only_build(&["services"]));
        assert!(native_bridge_only_build(&["droidloom-native-bridge"]));
        assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_DIRECTORIES.iter().all(|p| *p!="external/skia"));
    }

    #[test]
    fn upstream_art_test_defaults_are_not_filtered_out() {
        // Art's genuine test defaults are consumed by unrelated ART modules.
        assert!(!SOONG_EXCLUDED_TEST_FIXTURES.contains(&"art/test"));
        assert!(!SOONG_EXCLUDED_TEST_FIXTURES.contains(&"packages/modules/Connectivity/Tethering/common/TetheringLib"));
    }

    // Original Android 17 module SDK snapshot from the locked SdkExtensions
    // project d678d8ab3fb3602f46f33801190df2abb4eaca39; no provider body is synthesized.
    const REAL_SDKEXTENSIONS_BLUEPRINT: &str = r###"// This is auto-generated. DO NOT EDIT.

package {
    // A default list here prevents the license LSC from adding its own list which would
    // be unnecessary as every module in the sdk already has its own licenses property.
    default_applicable_licenses: ["Android-Apache-2.0"],
}

apex_contributions_defaults {
    name: "sdkextensions-sdk.contributions",
    contents: ["prebuilt_framework-sdkextensions"],
}

prebuilt_bootclasspath_fragment {
    name: "com.android.sdkext-bootclasspath-fragment",
    visibility: ["//visibility:public"],
    apex_available: ["com.android.sdkext"],
    licenses: ["sdkextensions-sdk_Android-Apache-2.0"],
    contents: ["framework-sdkextensions"],
    fragments: [
        {
            apex: "com.android.art",
            module: "art-bootclasspath-fragment",
        },
    ],
    hidden_api: {
        annotation_flags: "hiddenapi/annotation-flags.csv",
        metadata: "hiddenapi/metadata.csv",
        index: "hiddenapi/index.csv",
        signature_patterns: "hiddenapi/signature-patterns.csv",
        filtered_stub_flags: "hiddenapi/filtered-stub-flags.csv",
        filtered_flags: "hiddenapi/filtered-flags.csv",
    },
}

java_sdk_library_import {
    name: "framework-sdkextensions",
    visibility: ["//visibility:public"],
    apex_available: [
        "com.android.sdkext",
        "test_com.android.sdkext",
    ],
    licenses: ["sdkextensions-sdk_Android-Apache-2.0"],
    shared_library: false,
    permitted_packages: ["android.os.ext"],
    public: {
        jars: ["sdk_library/public/framework-sdkextensions-stubs.jar"],
        stub_srcs: ["sdk_library/public/framework-sdkextensions.srcjar"],
        current_api: "sdk_library/public/framework-sdkextensions.txt",
        removed_api: "sdk_library/public/framework-sdkextensions-removed.txt",
        annotations: "sdk_library/public/framework-sdkextensions_annotations.zip",
        sdk_version: "module_current",
    },
    system: {
        jars: ["sdk_library/system/framework-sdkextensions-stubs.jar"],
        stub_srcs: ["sdk_library/system/framework-sdkextensions.srcjar"],
        current_api: "sdk_library/system/framework-sdkextensions.txt",
        removed_api: "sdk_library/system/framework-sdkextensions-removed.txt",
        annotations: "sdk_library/system/framework-sdkextensions_annotations.zip",
        sdk_version: "module_current",
    },
    module_lib: {
        jars: ["sdk_library/module-lib/framework-sdkextensions-stubs.jar"],
        stub_srcs: ["sdk_library/module-lib/framework-sdkextensions.srcjar"],
        current_api: "sdk_library/module-lib/framework-sdkextensions.txt",
        removed_api: "sdk_library/module-lib/framework-sdkextensions-removed.txt",
        annotations: "sdk_library/module-lib/framework-sdkextensions_annotations.zip",
        sdk_version: "module_current",
    },
}

license {
    name: "sdkextensions-sdk_Android-Apache-2.0",
    visibility: ["//visibility:private"],
    license_kinds: ["SPDX-license-identifier-Apache-2.0"],
    license_text: ["licenses/build/soong/licenses/LICENSE"],
}

license {
    name: "sdkextensions-sdk_opensourcerequest",
    visibility: ["//visibility:private"],
    license_text: ["licenses/build/soong/licenses/opensourcerequest"],
}
"###;

    #[test]
    fn sdkextensions_provider_requires_complete_pinned_snapshot() {
        let source = tempfile::tempdir().unwrap();
        assert!(!original_sdkextensions_provider(source.path()).unwrap());
        let path = source.path().join("prebuilts/module_sdk/SdkExtensions/current/Android.bp");
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        assert!(original_sdkextensions_provider(source.path()).is_err());
        fs::write(&path, REAL_SDKEXTENSIONS_BLUEPRINT).unwrap();
        assert!(original_sdkextensions_provider(source.path()).unwrap());
        assert_eq!(fs::read_to_string(&path).unwrap(), REAL_SDKEXTENSIONS_BLUEPRINT);
        fs::write(&path, REAL_SDKEXTENSIONS_BLUEPRINT.replace(
            "name: \"framework-sdkextensions\"", "name: \"unrelated-provider\"" )).unwrap();
        assert!(original_sdkextensions_provider(source.path()).is_err());
        fs::write(&path, format!("{REAL_SDKEXTENSIONS_BLUEPRINT}\n")).unwrap();
        assert!(original_sdkextensions_provider(source.path()).is_err());
    }

    #[test]
    fn sdkextensions_fallbacks_preserve_original_scope_and_legacy_builds() {
        let source = tempfile::tempdir().unwrap();
        let absent = original_sdkextensions_provider(source.path()).unwrap();
        for scope in ["public", "system", "module-lib", "system-server"] {
            assert!(project_fallback_sdk_import("framework-sdkextensions", scope, absent));
        }
        let path = source.path().join("prebuilts/module_sdk/SdkExtensions/current/Android.bp");
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(&path, REAL_SDKEXTENSIONS_BLUEPRINT).unwrap();
        let present = original_sdkextensions_provider(source.path()).unwrap();
        for scope in ["public", "system", "module-lib"] {
            assert!(!project_fallback_sdk_import("framework-sdkextensions", scope, present));
            assert!(project_fallback_sdk_import("framework-media", scope, present));
            assert!(!project_fallback_sdk_import("framework-connectivity-b", scope, present));
            assert!(!project_fallback_sdk_import("framework-permission-s", scope, present));
        }
        assert!(project_fallback_sdk_import("framework-sdkextensions", "system-server", present));
        assert_eq!(fs::read_to_string(&path).unwrap(), REAL_SDKEXTENSIONS_BLUEPRINT);
    }

    #[test]
    fn original_connectivity_module_sdk_stubs_are_not_shadowed() {
        for module in [
            "framework-connectivity-b",
            "framework-connectivity-t",
            "framework-tethering",
        ] {
            assert!(!project_fallback_sdk_import(module, "module-lib", false), "{module}");
        }
        assert!(project_fallback_sdk_import("framework-media", "module-lib", false));
    }

    #[test]
    fn original_permission_sdk_stubs_are_not_shadowed() {
        assert!(!project_fallback_sdk_import("framework-permission-s", "module-lib", false));
        assert!(project_fallback_sdk_import("framework-media", "module-lib", false));
    }

    #[test]
    fn private_nativebridge_preserves_soong_plugin_when_scoping_test_suite() {
        let original = "test_suite_package {\n    name: \"general-tests\",\n    host_java_tools: [\"cts-tradefed\"],\n}\n\n";
        let rest = private_without_named_java_module(
            original,
            "test_suite_package",
            "general-tests",
        ).unwrap();
        assert!(rest.trim().is_empty());
        assert!(private_without_named_java_module(&rest, "test_suite_package", "general-tests").is_err());
    }

    #[test]
    fn private_nativebridge_java_scope_is_exact_and_reversible() {
        let original = "java_plugin {\n    name: \"missing-plugin\",\n    static_libs: [\"missing-lib\"],\n}\n\njava_plugin {\n    name: \"keep\",\n}\n";
        let filtered = private_without_named_java_module(
            original,
            "java_plugin",
            "missing-plugin",
        )
        .unwrap();
        assert!(!filtered.contains("missing-plugin"));
        assert!(filtered.contains("name: \"keep\""));
        assert!(private_without_named_java_module(
            original,
            "java_aconfig_library",
            "missing-plugin",
        )
        .is_err());
        assert!(private_without_named_java_module(
            &filtered,
            "java_plugin",
            "missing-plugin",
        )
        .is_err());
        assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.len() >= 4);
        let sdk_plugins = PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES
            .iter()
            .find(|(path, _, _)| *path == "prebuilts/sdk/current/androidx/JavaPlugins.bp")
            .unwrap();
        assert_eq!(sdk_plugins.2.len(), 3);
        assert_eq!(sdk_plugins.1, "java_plugin");

        assert!(!native_bridge_only_build(&["services"]));
        assert!(native_bridge_only_build(&[
            "droidloom-native-bridge",
            "berberis_arm64_host_tests",
        ]));
    }

    #[test]
    fn private_linux_statspull_retains_product_headers_without_windows_variant() {
        let original = r#"package {}
cc_library_headers {
    name: "libstatspull_headers",
    export_include_dirs: ["include"],
    host_supported: true,
    target: {
        windows: {
            enabled: true,
        },
    },
}

filegroup {
    name: "libstatspull_test_default_map",
    srcs: ["unchanged.map"],
}
"#;
        let changed = private_statspull_headers_without_windows_variant(original).unwrap();
        assert_eq!(changed.matches("enabled: false").count(), 1);
        assert!(changed.contains("host_supported: true"));
        assert!(changed.contains("srcs: [\"unchanged.map\"]"));
        assert!(private_statspull_headers_without_windows_variant(&changed).is_err());
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        let host = PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter()
            .find(|(path, kind, _)| {
                *path == "frameworks/base/AconfigFlags.bp"
                    && *kind == "java_aconfig_library"
            }).unwrap();
        assert!(host.2.contains(&"com.android.window.flags.window-aconfig-java-host"));
    }

    #[test]
    fn private_nativebridge_scopes_grpcio_ffi_and_host_flags_without_product_paths() {
        let scoped = private_nativebridge_unrelated_paths(&[
            "droidloom-native-bridge", "berberis_arm64_host_tests"
        ]);
        assert!(scoped.contains(&"external/rust/android-crates-io/crates/grpcio"));
        assert!(scoped.contains(&"external/rust/android-crates-io/crates/grpcio-sys"));
        assert!(!scoped.contains(&"external/rust/android-crates-io/crates/cxx"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        let statsd = PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter()
            .find(|(path, kind, _)| {
                *path == "packages/modules/StatsD/flags/Android.bp"
                    && *kind == "java_aconfig_library"
            }).expect("StatsD Java flags private scope");
        assert_eq!(statsd.2, &["statsd_flags_java_lib"]);
        let framework = PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter()
            .find(|(path, kind, _)| {
                *path == "frameworks/base/AconfigFlags.bp"
                    && *kind == "java_aconfig_library"
            }).expect("framework host-only Java flags scope");
        assert!(framework.2.contains(&"power_flags_lib_host"));
        assert!(!framework.2.contains(&"power_flags_lib"));
    }

    #[test]
    fn private_java_cli_cts_and_annotation_scopes_keep_product_libraries() {
        let scoped = private_nativebridge_unrelated_paths(&[
            "droidloom-native-bridge", "berberis_arm64_host_tests"
        ]);
        for path in [
            "packages/modules/StatsD/statsd/tools/localtools",
            "packages/modules/StatsD/tests",
        ] {
            assert!(scoped.contains(&path));
        }
        for product in [
            "packages/modules/StatsD",
            "packages/modules/StatsD/lib/libstatssocket",
            "packages/modules/StatsD/lib/libstatspull",
            "external/protobuf",
            "external/boringssl",
        ] {
            assert!(!scoped.contains(&product));
        }
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        for (file, module) in [
            ("external/protobuf/Android.bp", "libprotobuf-java-util-full"),
        ] {
            assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter()
                .any(|(path, kind, names)| {
                    *path == file && *kind == "java_library_host"
                        && names.contains(&module)
                }), "missing authentic scoped java host module {module}");
        }
    }

    #[test]
    fn statsd_tradefed_host_test_is_not_product_nativebridge_dependency() {
        let scope = PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter()
            .find(|(path, kind, _)| {
                *path == "packages/modules/StatsD/framework/test/hostsidetests/Android.bp"
                    && *kind == "java_test_host"
            }).expect("scoped StatsD host-test module");
        assert_eq!(scope.2, &["FrameworkStatsdHostTest"]);
        assert!(!private_nativebridge_unrelated_paths(&[
            "droidloom-native-bridge", "berberis_arm64_host_tests"
        ]).contains(&"packages/modules/StatsD"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
    }

    #[test]
    fn stats_codegen_java_host_test_scoped_without_hiding_generated_sources() {
        let entry = PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter()
            .find(|(path, kind, _)| {
                *path == "frameworks/proto_logging/stats/stats_log_api_gen/test_java/Android.bp"
                    && *kind == "java_test_host"
            }).expect("private stats host-only test scope");
        assert_eq!(entry.2, &["StatsCodeGenSrcsJavaHostTest"]);
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        assert!(!private_nativebridge_unrelated_paths(&[
            "droidloom-native-bridge", "berberis_arm64_host_tests"
        ]).contains(&"frameworks/proto_logging/stats/stats_log_api_gen"));
    }

    #[test]
    fn private_nativebridge_scopes_only_independent_rdroidtest_rust_harness() {
        let scoped = private_nativebridge_unrelated_paths(&[
            "droidloom-native-bridge", "berberis_arm64_host_tests",
        ]);
        assert!(scoped.contains(&"platform_testing/libraries/rdroidtest"));
        assert!(scoped.contains(&"packages/modules/Virtualization/tests/vts"));
        assert!(scoped.contains(&"hardware/interfaces/security/secretkeeper/aidl/vts"));
        // Keep the upstream parent and the real ARM64 translator + C++ host
        // tests discoverable: this is not an unrestricted test suppression.
        for required in [
            "platform_testing",
            "frameworks/libs/binary_translation",
            "art/test",
            "packages/modules/Virtualization",
            "hardware/interfaces/security/secretkeeper/aidl",
        ] {
            assert!(!scoped.contains(&required));
        }
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        assert!(private_nativebridge_unrelated_paths(&[]).is_empty());
    }

    #[test]
    fn private_nativebridge_exclusions_never_affect_full_product() {
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        assert!(private_nativebridge_unrelated_paths(&["com.android.tethering"]).is_empty());
        assert!(private_nativebridge_unrelated_paths(&[]).is_empty());
        let bridge = private_nativebridge_unrelated_paths(&[
            "droidloom-native-bridge", "berberis_arm64_host_tests",
        ]);
        assert!(bridge.len() >= 41);
        assert_eq!(bridge.iter().copied().collect::<std::collections::BTreeSet<_>>().len(), bridge.len());
        assert!(!bridge.contains(&"system/tools/xsdc"));
        assert!(bridge.contains(&"art/test/update-rollback"));
        assert!(bridge.contains(&"system/core/init/test_upgrade_mte"));
        assert!(bridge.contains(&"system/tools/hidl/test/vendor"));
        assert!(bridge.contains(&"libcore/tools/openjdk-analyzer"));
        assert!(bridge.contains(&"system/core/debuggerd/test_permissive_mte"));
        assert!(bridge.contains(&"packages/modules/Virtualization/tests/libs/preparer"));
        assert!(bridge.contains(&"build/make/tools/apicheck"));
        assert!(bridge.contains(&"cts/libs/json/fuzzers"));
        assert!(bridge.contains(&"frameworks/native/libs/binder/tests/binder_sdk"));
        assert!(bridge.contains(&"art/test/odsign"));
        assert!(!bridge.contains(&"packages/modules/Virtualization"));
        assert!(!bridge.contains(&"system/tools/hidl"));
        assert!(!bridge.contains(&"platform_testing"));
        assert!(bridge.contains(&"system/core/init/test_reboot_fs_integrity"));
        assert!(bridge.contains(&"packages/modules/Connectivity/tests/deflake"));
        assert!(bridge.contains(&"libcore/luni/src/test"));
        assert!(bridge.contains(&"libnativehelper/tests"));
        assert!(!bridge.contains(&"packages/modules/Connectivity/Tethering"));
        assert!(!bridge.contains(&"system/sepolicy"));
    }

    #[test]
    fn nativebridge_androidx_core_consumers_are_exactly_scoped() {
        let fixtures = [
            (
                "prebuilts/sdk/current/androidx/Android.bp",
                "android_library",
                "androidx.core_core-nodeps",
                r#"android_library {
    name: "androidx.core_core-nodeps",
    static_libs: ["androidx.core_core"],
}
"#,
            ),
            (
                "prebuilts/sdk/current/androidx/m2repository/androidx/webkit/webkit/1.12.0-alpha02/Android.bp",
                "android_library_import",
                "androidx.webkit_webkit",
                r#"android_library_import {
    name: "androidx.webkit_webkit",
    static_libs: ["androidx.core_core"],
}
"#,
            ),
        ];
        for (path, kind, name, original) in fixtures {
            assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(
                |(selected_path, selected_kind, names)|
                    *selected_path == path && *selected_kind == kind && names.contains(&name)
            ));
            let filtered = private_without_named_java_module(original, kind, name).unwrap();
            assert!(filtered.trim().is_empty());
            assert!(original.contains(name));
        }
        assert!(!native_bridge_only_build(&["services"]));
    }

    #[test]
    fn nativebridge_androidx_alpha_import_scoped_without_changing_full_product() {
        let input = r#"android_library_import {
    name: "androidx.core_core",
    aars: ["core-1.20.0-alpha01.aar"],
}
"#;
        let filtered = private_without_named_java_module(
            input, "android_library_import", "androidx.core_core"
        ).unwrap();
        assert!(filtered.trim().is_empty());
        assert!(input.contains("androidx.core_core"));
        assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(
            |(path, kind, names)| *path == "prebuilts/sdk/current/androidx/m2repository/androidx/core/core/1.20.0-alpha01/Android.bp"
                && *kind == "android_library_import"
                && names.contains(&"androidx.core_core")
        ));
        assert!(!native_bridge_only_build(&["services"]));
    }

    #[test]
    fn nativebridge_only_excludes_stats_vts_not_stats_aidl_service() {
        let subset = private_nativebridge_unrelated_paths(&[
            "droidloom-native-bridge", "berberis_arm64_host_tests",
        ]);
        assert!(subset.contains(&"frameworks/hardware/interfaces/stats/aidl/vts"));
        assert!(!subset.contains(&"frameworks/hardware/interfaces/stats/aidl"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
    }

    #[test]
    fn nativebridge_only_excludes_usb_gadget_vts_but_keeps_usb_gadget_service() {
        let subset = private_nativebridge_unrelated_paths(&[
            "droidloom-native-bridge", "berberis_arm64_host_tests",
        ]);
        assert!(subset.contains(&"hardware/interfaces/usb/gadget/aidl/vts/functional"));
        assert!(!subset.contains(&"hardware/interfaces/usb/gadget/aidl"));
        assert!(!subset.contains(&"hardware/interfaces/usb/gadget/aidl/default"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
    }

    #[test]
    fn nativebridge_only_scopes_java_truth_and_usb_aconfig_host_not_production() {
        let subset = private_nativebridge_unrelated_paths(&[
            "droidloom-native-bridge", "berberis_arm64_host_tests",
        ]);
        assert!(subset.contains(&"external/truth"));
        assert!(!subset.contains(&"external/skia"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        let usb = PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter()
            .find(|(path,kind,_)| *path == "frameworks/base/AconfigFlags.bp"
                 && *kind == "java_aconfig_library").unwrap();
        assert!(usb.2.contains(&"android.hardware.usb.flags-aconfig-java-host"));
    }

    #[test]
    fn nativebridge_only_scopes_rust_drm_and_host_allocator_without_hiding_cxx() {
        let scoped = private_nativebridge_unrelated_paths(&[
            "droidloom-native-bridge", "berberis_arm64_host_tests",
        ]);
        for crate_name in ["drm-ffi", "drm", "tikv-jemallocator"] {
            let path = format!("external/rust/android-crates-io/crates/{crate_name}");
            assert!(scoped.contains(&path.as_str()), "missing {crate_name} scope");
        }
        assert!(!scoped.contains(&"external/rust/cxx"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
    }

    #[test]
    fn nativebridge_only_excludes_closed_unrelated_rust_tls_and_usb_group() {
        let proof = private_nativebridge_unrelated_paths(&[
            "droidloom-native-bridge", "berberis_arm64_host_tests",
        ]);
        for module in [
            "rustls-webpki", "rustls", "tokio-rustls", "hyper-rustls",
            "reqwest", "dc_figma_import", "rusb", "ippusb",
        ] {
            let dir = format!("external/rust/android-crates-io/crates/{module}");
            assert!(proof.contains(&dir.as_str()), "missing {module} test-only scope");
        }
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        assert!(private_nativebridge_unrelated_paths(&[]).is_empty());
        assert!(!proof.contains(&"external/rust/cxx"));
    }

    #[test]
    fn nativebridge_xsdc_java_test_scope_keeps_cpp_tests() {
        let original = concat!(
            "package {\n    default_applicable_licenses: [\"Android-Apache-2.0\"],\n}\n",
            "java_test_host {\n    name: \"xsdc-java-tests\",\n}\n",
            "cc_test_host {\n    name: \"xsdc-cpp-tests\",\n}\n"
        );
        let narrowed = private_without_named_java_module(
            original, "java_test_host", "xsdc-java-tests",
        ).unwrap();
        assert!(narrowed.contains("xsdc-cpp-tests"));
        assert!(!narrowed.contains("xsdc-java-tests"));
        assert!(narrowed.contains("package {"));
        assert!(!native_bridge_only_build(&["services"]));
    }

    #[test]
    fn private_nativebridge_binder_ndk_tests_do_not_hide_runtime_binder() {
        let translator = private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(translator.contains(&"frameworks/native/libs/binder/ndk/tests"));
        assert!(!translator.contains(&"frameworks/native/libs/binder/ndk"));
        assert!(!translator.contains(&"frameworks/native/libs/binder"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        assert!(private_nativebridge_unrelated_paths(&["vendorimage"]).is_empty());
    }

    #[test]
    fn private_nativebridge_scope_excludes_only_unrelated_express_and_avf_service_vm() {
        let only_translator = private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        for path in [
            "frameworks/proto_logging/stats/express",
            "packages/modules/Virtualization/guest/service_vm",
            "packages/modules/Virtualization/libs/libservice_vm_fake_chain",
        ] {
            assert!(only_translator.contains(&path), "missing private-only scope: {path}");
        }
        for retained in [
            "frameworks/proto_logging/stats/stats_log_api_gen",
            "packages/modules/DnsResolver",
            "bionic/libc",
            "external/arm-optimized-routines",
            "external/llvm-libc",
        ] {
            assert!(!only_translator.contains(&retained), "runtime owner incorrectly excluded: {retained}");
        }
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        assert!(private_nativebridge_unrelated_paths(&["vendorimage"]).is_empty());
    }

    #[test]
    fn nativebridge_statslog_retains_consumed_rust_header_and_bindgen() {
        // NativeBridge must keep the genuine Rust StatsLog header provider and
        // StatsPull Bindgen while DnsResolver retains a consumer of both.
        let scope = private_nativebridge_unrelated_paths(&[
            "droidloom-native-bridge", "berberis_arm64_host_tests",
        ]);
        assert!(!scope.contains(&"system/core/libstats/pull_rust"));
        let entries: Vec<_> = PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter()
            .filter(|(path, _, _)| {
                *path == "frameworks/proto_logging/stats/stats_log_api_gen/Android.bp"
            })
            .collect();
        assert!(entries.iter().any(|(_, kind, names)| {
            *kind == "rust_library" && names.contains(&"libstatslog_rust")
        }));
        assert!(!entries.iter().any(|(_, _, names)| {
            names.contains(&"libstatslog_rust_header")
        }));
        let original = r#"package {
    default_applicable_licenses: ["Android-Apache-2.0"],
}
genrule {
    name: "statslog_header.rs",
}
rust_library {
    name: "libstatslog_rust_header",
}
rust_library {
    name: "libstatslog_rust",
}
rust_test_host {
    name: "test_api_gen_rust",
}
"#;
        let mut filtered = original.to_owned();
        for (kind, name) in [
            ("rust_library", "libstatslog_rust"),
            ("rust_test_host", "test_api_gen_rust"),
        ] {
            filtered = private_without_named_java_module(&filtered, kind, name).unwrap();
        }
        assert!(filtered.contains(r#"name: "statslog_header.rs""#));
        assert!(filtered.contains(r#"name: "libstatslog_rust_header""#));
        assert!(!filtered.contains(r#"name: "libstatslog_rust""#));
        assert!(!filtered.contains(r#"name: "test_api_gen_rust""#));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        assert!(original.contains(r#"name: "libstatslog_rust""#));
    }

    #[test]
    fn nativebridge_statslog_header_stays_visible_while_unneeded_test_scopes_do_not() {
        let private = private_nativebridge_unrelated_paths(&[
            "droidloom-native-bridge", "berberis_arm64_host_tests",
        ]);
        assert!(private.contains(&"external/rust/android-crates-io/crates/aws-lc-rs"));
        assert!(!private.contains(&"system/core/libstats/pull_rust"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().all(
            |(_, kind, names)| *kind != "rust_library" || !names.contains(&"libstatslog_rust_header")
        ));
        // Full Android product input retains both original modules and genrule.
        let source = r#"genrule {
    name: "statslog_header.rs",
}
rust_library {
    name: "libstatslog_rust_header",
}
"#;
        assert!(source.contains(r#"name: "libstatslog_rust_header""#));
        assert!(source.contains(r#"name: "statslog_header.rs""#));
    }

    #[test]
    fn nativebridge_only_scopes_unrelated_rust_ffi_and_java_host_plugins() {
        let native = private_nativebridge_unrelated_paths(&[
            "droidloom-native-bridge", "berberis_arm64_host_tests",
        ]);
        for path in [
            "external/rust/android-crates-io/crates/grpcio-sys",
            "external/rust/android-crates-io/crates/libusb1-sys",
            "external/rust/android-crates-io/crates/tikv-jemalloc-sys",
            "packages/modules/Virtualization/libs/dice/open_dice",
        ] {
            assert!(native.contains(&path), "Rust-only module expected: {path}");
        }
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        assert!(!native.contains(&"system/core/libstats/pull_rust"));
        assert!(!native.contains(&"build/make/tools/dependency_mapper"));
        let original = "kotlin_plugin {\n    name: \"kotlin-compose-compiler-embeddable-plugin\",\n}\njava_import {\n    name: \"kotlin-stdlib\",\n}\n";
        let scoped = private_without_named_java_module(
            original, "kotlin_plugin", "kotlin-compose-compiler-embeddable-plugin"
        ).unwrap();
        assert!(!scoped.contains("kotlin-compose-compiler-embeddable-plugin"));
        assert!(scoped.contains("kotlin-stdlib"));
    }

    #[test]
    fn nativebridge_aconfig_host_only_filter_preserves_full_product() {
        let entry = PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().find(
            |(path, kind, _)| *path == "frameworks/base/AconfigFlags.bp"
                && *kind == "java_aconfig_library"
        ).unwrap();
        assert!(entry.2.len() >= 14);
        assert_eq!(entry.2.iter().copied().collect::<std::collections::BTreeSet<_>>().len(), entry.2.len());
        assert!(entry.2.iter().all(|name|
            name.ends_with("-aconfig-java-host")
                || *name == "device_policy_aconfig_flags_lib_host"
                || *name == "power_flags_lib_host"
        ));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        assert!(private_nativebridge_unrelated_paths(&["droidloom-native-bridge"])
            .iter().all(|path| *path != "frameworks/base"));
    }

    #[test]
    fn dependency_mapper_nativebridge_scope_keeps_soong_proto_provider() {
        let original = concat!(
            "package {\n    default_team: \"test\",\n}\n",
            "java_binary_host {\n    name: \"dependency-mapper\",\n}\n",
            "java_library_host {\n    name: \"dependency-mapper-host-lib\",\n}\n",
            "java_test_host {\n    name: \"dependency-mapper-tests\",\n}\n",
            "java_library {\n    name: \"dependency-mapper-test-data\",\n}\n",
        );
        let scoped = private_dependency_mapper_package_only(original).unwrap();
        assert!(scoped.contains("package {"));
        assert!(!scoped.contains("dependency-mapper-host-lib"));
        assert!(private_dependency_mapper_package_only(&scoped).is_err());
        let bridge = private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(!bridge.contains(&"build/make/tools/dependency_mapper"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
    }

    #[test]
    fn m842_real_m2_jar_providers_are_not_omitted_from_soong() {
        assert!(!SOONG_EXCLUDED_TEST_FIXTURES.contains(&"prebuilts/tools/common/m2"));
        assert!(!private_nativebridge_unrelated_paths(&["droidloom-native-bridge"])
            .contains(&"prebuilts/tools/common/m2"));
        assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(
            |(p, kind, names)| *p == "prebuilts/tools/common/m2/robolectric.bp"
                && *kind == "android_library_import"
                && names.contains(&"robolectric-monitor-1.0.2-alpha1")));
    }

    #[test]
    fn m844_scopes_libcore_tradefed_metrics_only_in_nativebridge() {
        let private = private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(private.contains(&"libcore/metrictests"));
        assert!(!private.contains(&"libcore"));
        assert!(!private_nativebridge_unrelated_paths(&["services"])
            .contains(&"libcore/metrictests"));
    }

    #[test]
    fn m843_libcore_benchmarks_excluded_only_from_nativebridge_proof() {
        assert!(private_nativebridge_unrelated_paths(&["droidloom-native-bridge"])
            .contains(&"libcore/benchmarks"));
        assert!(!private_nativebridge_unrelated_paths(&["droidloom-native-bridge"])
            .contains(&"libcore"));
        assert!(!private_nativebridge_unrelated_paths(&["services"])
            .contains(&"libcore/benchmarks"));
    }

    #[test]
    fn m841_private_translator_scopes_dice_sample_and_pvmfw_together() {
        let scoped = private_nativebridge_unrelated_paths(&[
            "droidloom-native-bridge", "berberis_arm64_host_tests"
        ]);
        assert!(scoped.contains(&"packages/modules/Virtualization/libs/dice/open_dice"));
        assert!(scoped.contains(&"packages/modules/Virtualization/libs/dice/sample_inputs"));
        assert!(scoped.contains(&"packages/modules/Virtualization/guest/pvmfw"));
        assert!(!scoped.contains(&"packages/modules/Virtualization"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
    }

    #[test]
    fn nativebridge_java_host_boundary_preserves_real_kotlin_stdlib() {
        let private = private_nativebridge_unrelated_paths(&[
            "droidloom-native-bridge", "berberis_arm64_host_tests"
        ]);
        assert!(!private.contains(&"build/make/tools/dependency_mapper"));
        assert!(private.contains(&"build/make/backported_fixes"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        let original = "kotlin_plugin {\n    name: \"kotlin-compose-compiler-plugin\",\n}\njava_import {\n    name: \"kotlin-stdlib\",\n}\n";
        let filtered = private_without_named_java_module(
            original, "kotlin_plugin", "kotlin-compose-compiler-plugin"
        ).unwrap();
        assert!(!filtered.contains("kotlin-compose-compiler-plugin"));
        assert!(filtered.contains("kotlin-stdlib"));
        assert!(private_without_named_java_module(
            &filtered, "kotlin_plugin", "kotlin-compose-compiler-plugin"
        ).is_err());
    }

    #[test]
    fn m840_nativebridge_keeps_real_errorprone_plugin_dependencies() {
        for preserved in ["error_prone_annotation", "error_prone_check_api"] {
            assert!(!PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES
                .iter()
                .any(|(path, _, names)| *path == "external/error_prone/Android.bp"
                    && names.contains(&preserved)));
        }
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
    }

    #[test]
    fn m839_apksig_and_cts_scope_preserve_production_interfaces() {
        let private = private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(private.contains(&"packages/modules/Connectivity/tests/cts/hostside"));
        assert!(!private.contains(&"packages/modules/Connectivity"));
        assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(
            |(path, kind, names)| *path == "tools/apksig/Android.bp"
                && *kind == "java_test_host" && names == &["apksig-test"]
        ));
        let bp = r#"java_library {
    name: "apksig",
}
java_test_host {
    name: "apksig-test",
}
java_binary_host {
    name: "apksigner",
}
"#;
        let filtered = private_without_named_java_module(bp, "java_test_host", "apksig-test").unwrap();
        assert!(filtered.contains(r#"name: "apksig""#));
        assert!(filtered.contains(r#"name: "apksigner""#));
        assert!(!filtered.contains("apksig-test"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
    }

    #[test]
    fn m838_meta_app_and_errorprone_testhelper_only() {
        let scope = private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(scope.contains(&"tools/metalava/metalava"));
        assert!(!scope.contains(&"tools/metalava"));
        assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(
            |(path, kind, names)| *path == "external/error_prone/Android.bp"
                && *kind == "java_library_host" && names == &["error_prone_test_helpers"]
        ));
        let original = r#"java_plugin {
    name: "error_prone_plugin",
}
java_library_host {
    name: "error_prone_test_helpers",
}
"#;
        let filtered = private_without_named_java_module(original, "java_library_host", "error_prone_test_helpers").unwrap();
        assert!(filtered.contains("error_prone_plugin"));
        assert!(!filtered.contains("error_prone_test_helpers"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
    }

    #[test]
    fn m837_preserve_stubs_provider_while_scoping_metalava_host_tools() {
        let scoped = private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(!scoped.contains(&"tools/metalava"));
        assert!(scoped.contains(&"tools/metalava/metalava-model-source"));
        assert!(scoped.contains(&"tools/metalava/metalava-model-turbine"));
        assert!(scoped.contains(&"tools/metalava/metalava-model-psi"));
        assert!(scoped.contains(&"build/make/tools/check-flagged-apis"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
    }

    #[test]
    fn m835_avf_test_only_root_does_not_hide_runtime_or_full_product() {
        let only_bridge = private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(only_bridge.contains(&"packages/modules/Virtualization/tests"));
        assert!(!only_bridge.contains(&"packages/modules/Virtualization"));
        assert!(!only_bridge.contains(&"packages/modules/Virtualization/libs"));
        assert!(!only_bridge.contains(&"packages/modules/Virtualization/service"));
        assert!(private_nativebridge_unrelated_paths(&["droidloom-native-bridge", "berberis_arm64_host_tests"])
            .contains(&"packages/modules/Virtualization/tests"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
    }

    #[test]
    fn m834_avf_host_side_test_scoping_does_not_hide_product() {
        let scoped = private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        for path in [
            "packages/modules/Virtualization/tests/pvmfw/tools",
            "packages/modules/Virtualization/tests/benchmark_hostside",
        ] {
            assert!(scoped.contains(&path), "{path} not scoped");
        }
        assert!(!scoped.contains(&"packages/modules/Virtualization"));
        assert!(!scoped.contains(&"packages/modules/Virtualization/libs"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
    }

    #[test]
    fn m833_nativebridge_host_fixture_scope_is_exact_and_product_safe() {
        let expected = [
            ("packages/modules/Virtualization/tests/pvmfw/libs/Android.bp", "java_library_host", "PvmfwHostTestLib"),
            ("external/protobuf/Android.bp", "java_test_host", "libprotobuf-java-full-test"),
            ("frameworks/libs/modules-utils/java/com/android/modules/utils/build/testing/Android.bp", "java_library_host", "modules-utils-build-testing"),
            ("build/make/tools/permission_versioning/Android.bp", "java_test_host", "permission_versions_tests"),
            ("packages/modules/Virtualization/tests/libs/host/Android.bp", "java_library_host", "MicrodroidHostTestLib"),
            ("frameworks/base/tools/processors/devicepolicy/Android.bp", "java_test_host", "DevicePolicyAnnotationProcessorTests"),
        ];
        for (path, kind, module) in expected {
            assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter()
                .any(|(p, k, names)| *p == path && *k == kind && names == &[module]));
            let original = format!(
                "java_library {{\n    name: \"product_kept\",\n}}\n{kind} {{\n    name: \"{module}\",\n}}\n",
            );
            let scoped = private_without_named_java_module(&original, kind, module).unwrap();
            assert!(scoped.contains("product_kept"));
            assert!(!scoped.contains(module));
            assert!(private_without_named_java_module(&scoped, kind, module).is_err());
        }
        let private = private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(private.contains(&"build/soong/cmd/kotlinc_incremental"));
        assert!(private.contains(&"tools/metalava/metalava-model-source"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
    }

    #[test]
    fn nativebridge_test_only_boundaries_never_touch_full_product() {
        let scope = private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(scope.contains(&"system/fs/fs_mgr/tests"));
        assert!(scope.contains(&"bionic/tests"));
        assert!(!scope.contains(&"system/fs/fs_mgr/libfstab"));
        assert!(!scope.contains(&"bionic/libc"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        let installer = PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES
            .iter()
            .find(|(path, kind, _)| {
                *path == "frameworks/native/cmds/installd/Android.bp"
                    && *kind == "cc_test_host"
            })
            .expect("private host unit-test scope");
        assert_eq!(installer.2, &["run_dex2oat_test"]);
        let original = r#"cc_test_host {
    name: "run_dex2oat_test",
}
cc_binary {
    name: "installd",
}
"#;
        let scoped = private_without_named_java_module(
            original,
            "cc_test_host",
            "run_dex2oat_test",
        )
        .unwrap();
        assert!(scoped.contains(r#"name: "installd""#));
        assert!(!scoped.contains("run_dex2oat_test"));
    }

    #[test]
    fn nativebridge_rust_gbm_scope_keeps_platform_gbm_and_full_product() {
        let relative = "external/rust/android-crates-io/crates/gbm";
        let private = private_nativebridge_unrelated_paths(&["droidloom-native-bridge"]);
        assert!(private.contains(&relative));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        assert!(!private.contains(&"vendor/droidloom/mesa3d"));
        assert!(!private.contains(&"external/mesa3d"));
    }

    #[test]
    fn nativebridge_scopes_only_optional_cloud_kms_signing_modules() {
        let original = concat!(
            "java_library {\n    name: \"apksig\",\n}\n",
            "java_library_host {\n    name: \"apksig-kms-provider-aws\",\n}\n",
            "java_library_host {\n    name: \"apksig-kms-provider-gcp\",\n}\n",
            "java_test_host {\n    name: \"apksig-test\",\n}\n",
            "java_binary_host {\n    name: \"apksigner\",\n}\n",
            "java_binary_host {\n    name: \"apksigner-kms\",\n}\n",
        );
        let mut scoped = original.to_string();
        let mut count = 0;
        for (path, kind, names) in PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES {
            if *path == "tools/apksig/Android.bp" {
                for name in *names {
                    scoped = private_without_named_java_module(&scoped, kind, name).unwrap();
                    count += 1;
                }
            }
        }
        assert_eq!(count, 4);
        assert!(scoped.contains("name: \"apksig\""));
        assert!(scoped.contains("name: \"apksigner\""));
        assert!(!scoped.contains("apksig-kms-provider-aws"));
        assert!(!scoped.contains("apksig-kms-provider-gcp"));
        assert!(!scoped.contains("apksigner-kms"));
        assert!(!scoped.contains("apksig-test"));
        // Full product input remains unmodified and keeps both KMS backends.
        assert!(original.contains("apksig-kms-provider-aws"));
        assert!(original.contains("apksig-kms-provider-gcp"));
    }

    #[test]
    fn nativebridge_host_tool_scope_preserves_original_full_product_modules() {
        let targets = ["droidloom-native-bridge", "berberis_arm64_host_tests"];
        let scope = private_nativebridge_unrelated_paths(&targets);
        assert!(scope.contains(&"libcore/tools/non-cts-json-generator"));
        assert!(scope.contains(&"build/make/tools/soong_api"));
        assert!(private_nativebridge_unrelated_paths(&["services"]).is_empty());
        let original = "java_binary_host {\n    name: \"metalava-antlr4-tool\",\n}\njava_library {\n    name: \"stub-annotations\",\n}\n";
        let isolated = private_without_named_java_module(
            original, "java_binary_host", "metalava-antlr4-tool"
        ).unwrap();
        assert!(!isolated.contains("metalava-antlr4-tool"));
        assert!(isolated.contains("stub-annotations"));
        assert!(private_without_named_java_module(
            &isolated, "java_binary_host", "metalava-antlr4-tool"
        ).is_err());
    }

    #[test]
    fn private_ART_conscrypt_fuzzer_scope_preserves_other_modules() {
        let original = format!(r#"package {{}}
{}
java_library {{}}
"#, PRIVATE_CONSCRYPT_FUZZER_MODULE);
        let altered = private_without_conscrypt_fuzzer(&original).unwrap();
        assert!(!altered.contains("conscrypt-fuzzer"));
        assert!(altered.contains("java_library {}"));
        assert!(private_without_conscrypt_fuzzer(&altered).is_err());
    }

    #[test]
    fn private_fuzzer_scope_preserves_real_selinux_context_modules() {
        let original = format!(
            "package {{}}\n{}\nservice_contexts_test {{\n    name: \"test_keep\"\n}}\n",
            PRIVATE_FUZZER_BINDINGS_TEST,
        );
        let filtered = private_without_fuzzer_bindings_test(&original).unwrap();
        assert!(!filtered.contains("fuzzer_bindings_test {"));
        assert!(filtered.contains("service_contexts_test {"));
        assert!(filtered.contains("test_keep"));
        assert!(private_without_fuzzer_bindings_test(&filtered).is_err());
        assert!(private_without_fuzzer_bindings_test(&format!(
            "{}{}",
            original, PRIVATE_FUZZER_BINDINGS_TEST
        )).is_err());
    }

    #[test]
    fn missing_dependencies_are_rejected_even_if_caller_asks_to_allow_them() {
        let mut cmd = Command::new("unused");
        cmd.env("ALLOW_MISSING_DEPENDENCIES", "true");
        enforce_strict_soong_dependencies(&mut cmd);
        let actual = cmd
            .get_envs()
            .find(|(name, _)| *name == std::ffi::OsStr::new("ALLOW_MISSING_DEPENDENCIES"))
            .and_then(|(_, value)| value);
        assert_eq!(actual, Some(std::ffi::OsStr::new("false")));
    }
    #[test]
    fn default_dependency_mode_still_overrides_inherited_allow_missing() {
        let mut cmd = Command::new("unused");
        cmd.env("ALLOW_MISSING_DEPENDENCIES", "true");
        configure_soong_dependencies(
            &mut cmd,
            SoongDependencyMode::Strict,
            &["droidloom-native-bridge"],
        )
        .unwrap();
        let actual = cmd
            .get_envs()
            .find(|(name, _)| *name == std::ffi::OsStr::new("ALLOW_MISSING_DEPENDENCIES"))
            .and_then(|(_, value)| value);
        assert_eq!(actual, Some(std::ffi::OsStr::new("false")));
    }

    #[test]
    fn explicit_target_closure_uses_upstream_missing_dependency_mode() {
        for targets in [
            &["droidloom-native-bridge"][..],
            &["droidloom-native-bridge", "berberis_arm64_host_tests"][..],
        ] {
            let mut cmd = Command::new("unused");
            configure_soong_dependencies(
                &mut cmd,
                SoongDependencyMode::NativeBridgeTargetClosure,
                targets,
            )
            .unwrap();
            let actual = cmd
                .get_envs()
                .find(|(name, _)| *name == std::ffi::OsStr::new("ALLOW_MISSING_DEPENDENCIES"))
                .and_then(|(_, value)| value);
            assert_eq!(actual, Some(std::ffi::OsStr::new("true")));
        }
    }

    #[test]
    fn target_closure_rejects_widened_or_incomplete_target_lists() {
        for targets in [
            &[][..],
            &["services"][..],
            &["berberis_arm64_host_tests"][..],
            &["com.android.hardware.audio.droidloom"][..],
            &["droidloom-native-bridge", "services"][..],
            &["droidloom-native-bridge", "unknown"][..],
            TARGETS,
        ] {
            let mut cmd = Command::new("unused");
            cmd.env("ALLOW_MISSING_DEPENDENCIES", "false");
            assert!(configure_soong_dependencies(
                &mut cmd,
                SoongDependencyMode::NativeBridgeTargetClosure,
                targets,
            )
            .is_err());
            let actual = cmd
                .get_envs()
                .find(|(name, _)| *name == std::ffi::OsStr::new("ALLOW_MISSING_DEPENDENCIES"))
                .and_then(|(_, value)| value);
            assert_eq!(actual, Some(std::ffi::OsStr::new("false")));
        }
    }

    #[test]
    fn minigbm_target_defers_missing_outputs_with_qualified_default_error_propagation() {
        let mut command = Command::new("true");
        configure_soong_dependencies(&mut command,
            SoongDependencyMode::MinigbmTargetClosure, &["libminigbm_gralloc"]).unwrap();
        assert!(command.get_envs().any(|(key, value)| key == "ALLOW_MISSING_DEPENDENCIES"
            && value == Some(std::ffi::OsStr::new("true"))));
        assert!(command.get_args().any(|arg| arg == "--soong-only"));
        for targets in [&[][..], &["droidloom_x86_64"][..],
            &["libminigbm_gralloc", "com.android.hardware.audio.droidloom"][..]] {
            assert!(validate_soong_dependency_mode(
                SoongDependencyMode::MinigbmTargetClosure, targets).is_err());
            assert!(!minigbm_only_build(targets));
        }
        assert!(audio_apex_pcm_patches(SoongDependencyMode::MinigbmTargetClosure).is_empty());
    }

    #[test]
    fn audio_apex_target_closure_is_explicit_and_preserves_native_dependencies() {
        let targets = &["com.android.hardware.audio.droidloom"];
        for (mode, expected) in [
            (SoongDependencyMode::Strict, "false"),
            (SoongDependencyMode::AudioApexTargetClosure, "false"),
        ] {
            let mut cmd = Command::new("unused");
            cmd.env("ALLOW_MISSING_DEPENDENCIES", "true");
            configure_soong_dependencies(&mut cmd, mode, targets).unwrap();
            let actual = cmd
                .get_envs()
                .find(|(name, _)| *name == std::ffi::OsStr::new("ALLOW_MISSING_DEPENDENCIES"))
                .and_then(|(_, value)| value);
            assert_eq!(actual, Some(std::ffi::OsStr::new(expected)));
        }
        assert!(!native_bridge_only_build(targets));
        assert!(private_nativebridge_unrelated_paths(targets).is_empty());
        // The real APEX module name is passed through to Soong, as in the
        // original AudioApexBuild path; do not redirect to a fabricated output.
        assert_eq!(apex_output(targets[0]), None);
    }

    #[test]
    fn audio_apex_target_closure_rejects_other_or_mixed_targets() {
        for targets in [
            &[][..],
            &["services"][..],
            &["android.hardware.audio.service-aidl.droidloom"][..],
            &["droidloom-native-bridge"][..],
            &["berberis_arm64_host_tests"][..],
            &["com.android.hardware.audio.droidloom", "services"][..],
            &["com.android.hardware.audio.droidloom", "droidloom-native-bridge"][..],
            &["com.android.hardware.audio.droidloom", "com.android.hardware.audio.droidloom"][..],
            TARGETS,
        ] {
            let mut cmd = Command::new("unused");
            cmd.env("ALLOW_MISSING_DEPENDENCIES", "false");
            assert!(configure_soong_dependencies(
                &mut cmd,
                SoongDependencyMode::AudioApexTargetClosure,
                targets,
            )
            .is_err());
            let actual = cmd
                .get_envs()
                .find(|(name, _)| *name == std::ffi::OsStr::new("ALLOW_MISSING_DEPENDENCIES"))
                .and_then(|(_, value)| value);
            assert_eq!(actual, Some(std::ffi::OsStr::new("false")));
        }
    }

    #[test]
    fn target_closure_soong_patch_does_not_change_strict_builds() {
        assert!(target_closure_soong_patches(SoongDependencyMode::Strict).is_empty());
        for mode in [
            SoongDependencyMode::NativeBridgeTargetClosure,
            SoongDependencyMode::AudioApexTargetClosure,
        ] {
            assert_eq!(
                target_closure_soong_patches(mode),
                &[(
                    "build/soong",
                    "android/aosp-patches/0017-soong-prebuilt-missing-source-metadata.patch",
                )],
            );
        }
    }

    #[test]
    fn audio_pcm_patches_are_private_and_keep_lifecycle_order() {
        for mode in [
            SoongDependencyMode::Strict,
            SoongDependencyMode::NativeBridgeTargetClosure,
        ] {
            assert!(audio_apex_pcm_patches(mode).is_empty());
        }
        assert_eq!(
            audio_apex_pcm_patches(SoongDependencyMode::AudioApexTargetClosure),
            &[
                ("", "android/aosp-patches/0015-droidloom-pcm-output.patch"),
                ("", "android/aosp-patches/0016-droidloom-pcm-cancellation-lifecycle.patch"),
            ],
        );
    }

    #[test]
    fn repeated_projection_keeps_ninja_outputs_until_content_changes() {
        let d = tempfile::tempdir().unwrap();
        let input = d.path().join("input");
        write(&input, b"original").unwrap();
        let original_time = fs::metadata(&input).unwrap().modified().unwrap();
        write(
            &d.path().join("build.ninja"),
            b"rule compile\n  command = cp $in $out\nbuild result: compile input\n",
        )
        .unwrap();
        let ninja = || output(Command::new("ninja").current_dir(d.path())).unwrap();
        let journal = d.path().join("journal.json");
        let mut p = Projection::new(journal.clone()).unwrap();
        p.put(&input, b"intermediate patch").unwrap();
        p.put(&input, b"patched").unwrap();
        p.stabilize_all().unwrap();
        ninja();
        let result_time = fs::metadata(d.path().join("result"))
            .unwrap()
            .modified()
            .unwrap();
        p.restore().unwrap();
        assert_eq!(
            fs::metadata(&input).unwrap().modified().unwrap(),
            original_time
        );
        let mut p = Projection::new(journal).unwrap();
        p.put(&input, b"intermediate patch").unwrap();
        p.put(&input, b"patched").unwrap();
        p.stabilize_all().unwrap();
        assert!(ninja().contains("no work to do"));
        assert_eq!(
            fs::metadata(d.path().join("result"))
                .unwrap()
                .modified()
                .unwrap(),
            result_time
        );
        p.put(&input, b"changed patch").unwrap();
        p.stabilize_all().unwrap();
        assert!(!ninja().contains("no work to do"));
        assert_eq!(fs::read(d.path().join("result")).unwrap(), b"changed patch");
    }
    #[test]
    fn restoration_preserves_original_and_removes_created_file() {
        let d = tempfile::tempdir().unwrap();
        let original = d.path().join("original");
        write(&original, b"before").unwrap();
        {
            let mut p = Projection::new(d.path().join("journal")).unwrap();
            p.put(&original, b"after").unwrap();
            p.put(&d.path().join("created"), b"x").unwrap();
        }
        assert_eq!(fs::read(original).unwrap(), b"before");
        assert!(!d.path().join("created").exists());
    }
    #[test]
    fn complete_target_set_contains_both_wire_peers_and_framework() {
        for name in [
            "android.hardware.graphics.composer3-service.droidloom",
            "droidloom-input-bridge",
            "surfaceflinger",
            "libinputflinger",
            "services",
            "vendorimage",
        ] {
            assert!(TARGETS.contains(&name));
        }
    }
}

#[cfg(test)]
mod patch_tests {
    use super::*;
    #[test]
    fn native_engine_effective_projection_records_final_bytes_and_applied_patch() {
        let root = tempfile::tempdir().unwrap();
        let source = root.path().join("source");
        fs::create_dir(&source).unwrap();
        write(&source.join("input"), "before\n").unwrap();
        write(&source.join("removed"), "removed\n").unwrap();
        let patch = root.path().join("compat.patch");
        write(&patch, "--- a/input\n+++ b/input\n@@ -1 +1 @@\n-before\n+after\n\
--- a/removed\n+++ /dev/null\n@@ -1 +0,0 @@\n-removed\n").unwrap();
        let mut p = Projection::new(root.path().join("journal")).unwrap();
        p.patch(&source, "", &patch).unwrap();
        p.put(&source.join("input"), "effective after compatibility\n").unwrap();
        let receipt = p.effective_inventory(root.path(), &source).unwrap();
        assert_eq!(receipt["files"]["input"], hash(&source.join("input")).unwrap());
        assert!(receipt["files"].as_object().unwrap().contains_key("removed"));
        assert!(receipt["files"]["removed"].is_null());
        assert_eq!(receipt["patches"]["compat.patch"], hash(&patch).unwrap());
        p.restore().unwrap();
        assert_eq!(fs::read(source.join("input")).unwrap(), b"before\n");
        assert_eq!(fs::read(source.join("removed")).unwrap(), b"removed\n");
    }

    #[test]
    fn patch_in_source_without_git_root_is_restored_inside_enclosing_checkout() {
        let d = tempfile::tempdir().unwrap();
        run(Command::new("git").arg("init").arg("--quiet").arg(d.path())).unwrap();
        let source = d.path().join("work/source");
        fs::create_dir_all(&source).unwrap();
        write(&source.join("input"), b"before\n").unwrap();
        let patch = d.path().join("change.patch");
        write(
            &patch,
            b"--- a/input\n+++ b/input\n@@ -1 +1 @@\n-before\n+after\n",
        )
        .unwrap();
        {
            let mut p = Projection::new(d.path().join("journal")).unwrap();
            p.patch(&source, "", &patch).unwrap();
            assert_eq!(fs::read(source.join("input")).unwrap(), b"after\n");
        }
        assert_eq!(fs::read(source.join("input")).unwrap(), b"before\n");
    }
    #[test]
    fn interrupted_projection_recovers_before_next_build() {
        let d = tempfile::tempdir().unwrap();
        let source = d.path().join("source");
        fs::create_dir(&source).unwrap();
        let path = source.join("input");
        write(&path, b"original").unwrap();
        let journal = d.path().join("journal");
        let mut p = Projection::new(journal.clone()).unwrap();
        p.put(&path, b"modified").unwrap();
        std::mem::forget(p);
        recover(&journal, &source).unwrap();
        assert_eq!(fs::read(path).unwrap(), b"original");
        assert!(!journal.exists());
    }
}

fn meson_string(path: &Path) -> Result<String> {
    Ok(format!(
        "'{}'",
        path.to_str()
            .ok_or("non-UTF8 tool path")?
            .replace('\\', "\\\\")
            .replace('\'', "\\'")
    ))
}
