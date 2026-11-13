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
    ("", "android/aosp-patches/0017-droidloom-real-pcm-input.patch"),
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
fn project_fallback_sdk_import(stem: &str) -> bool {
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

fn project_fallback_sdk_import_for_mode(stem: &str, scope: &str, mode: SoongDependencyMode) -> bool {
    project_fallback_sdk_import(stem) && !(mode == SoongDependencyMode::AudioApexTargetClosure
        && matches!(stem, "framework-sdkextensions" | "framework-npumanager")
        && matches!(scope, "public" | "system" | "module-lib"))
}

// The retained libandroid NPU shim requires its original Rust AIDL. The
// same upstream BP also defines the real SDK library; its public/system/module
// scopes must not be duplicated by sparse prebuilt aliases. Check both the
// original provider and the defaults that enable exactly those three scopes.
fn validate_audio_npumanager_sdk_provider(source: &Path, mode: SoongDependencyMode) -> Result<()> {
    if mode != SoongDependencyMode::AudioApexTargetClosure {
        return Ok(());
    }
    for (relative, expected) in [
        ("packages/modules/NpuManager/framework/Android.bp",
         "199f86c7e2f5b7ccb49f4903e9adbd45039ac4966234e6184fecb0b7620fc081"),
        ("packages/modules/common/sdk/Android.bp",
         "f68716de589c8ab13e4aa46b00416144728ed61d488450659cb97265eae88e17"),
    ] {
        if hash(&source.join(relative))? != expected {
            return fail("audio NPU SDK fallback requires its original three-scope provider and defaults");
        }
    }
    Ok(())
}

fn validate_audio_sdk_import_provider(source: &Path, mode: SoongDependencyMode) -> Result<()> {
    if mode == SoongDependencyMode::AudioApexTargetClosure && hash(&source.join(
        "prebuilts/module_sdk/SdkExtensions/current/Android.bp"))?
        != "733a15d52927e70b1dcc4c6df212ce8e63e32cd733a794afee68a56dccff714a" {
        return fail("audio SDK fallback requires the exact original three-scope SdkExtensions provider");
    }
    Ok(())
}

// The audio projection keeps SystemUI's existing downstream consumers. In
// particular SystemUITests_defaults links SystemUI-tests, its fixtures link
// SystemUI-application, and StructuredConcurrencyPerfTests uses both the
// optimized defaults and the original proguard filegroup. Keeping only three
// defaults would still sever those real dependency edges. Preserve these two
// complete, pinned provider files, including all of their original dependencies.
// These original providers have incoming edges from Audio's retained
// framework/fastboot/Connectivity/aconfigd graph. Keep their complete source
// declarations and all dependencies; other target routes keep their old scope.
fn audio_original_graph_provider(
    relative: &str, original: &str, mode: SoongDependencyMode,
) -> Result<Option<String>> {
    if mode != SoongDependencyMode::AudioApexTargetClosure {
        return Ok(None);
    }
    use sha2::{Digest, Sha256};
    let (bytes, expected) = match relative {
        "system/update_engine/Android.bp" => (41318,
            "58a7115ce497d3cbfe7479d15f3ab056fcc93ed9d950aebdc9685f6f54fde308"),
        "packages/modules/Connectivity/service/Android.bp" => (16884,
            "f118cc0ac04460b290d84248c511539ec245999be73901fd6d59df1b3eae888f"),
        "frameworks/base/libs/hwui/Android.bp" => (24900,
            "37633298fdd6e1cf8a3d0acf59e715d8581dd0ba214384f480213d178a7f40c6"),
        "packages/modules/ConfigInfrastructure/aconfigd/Android.bp" => (3011,
            "da512bd47cdd87afa503d88cddb0b2aa83d3bee62f6506fdcb072327947d898d"),
        "prebuilts/sdk/current/androidx/JavaPlugins.bp" => (1315,
            "ecb2b148861c341c50fa9c223117a1d918a8641cebcef7c07e143c3806d77102"),
        _ => return Ok(None),
    };
    if original.len() != bytes || format!("{:x}", Sha256::digest(original.as_bytes())) != expected {
        return fail(format!("audio retained original graph provider changed: {relative}"));
    }
    Ok(Some(original.to_owned()))
}


// Connectivity's normal platform patches run before provider scoping. Verify
// their captured original preimage and both exact patches, then preserve the
// independently reproduced complete postimage. An arbitrary current hash or an
// unpatched original cannot satisfy this post-patch boundary.
const AUDIO_CONNECTIVITY_BP: &str = "packages/modules/Connectivity/service/Android.bp";
const AUDIO_CONNECTIVITY_PATCHES: &[(&str, &str)] = &[
    ("android/aosp-patches/0001-netbpfload-tolerate-shared-kernel-bpf-ids.patch",
     "eae002e9858dc976f494f9d29783b42f8cad8ed0fd3326a26d28d7906b7a9b78"),
    ("android/aosp-patches/0003-connectivity-offline-rcu.patch",
     "3a09e7169467b08774495e36ba1775f76bbada5ddc1c2771ec8736cc75bc588b"),
];

fn audio_connectivity_provider_after_patch(
    projection: &Projection, repo: &Path, source: &Path, current: &str,
    mode: SoongDependencyMode,
) -> Result<Option<String>> {
    if mode != SoongDependencyMode::AudioApexTargetClosure {
        return Ok(None);
    }
    let path = source.join(AUDIO_CONNECTIVITY_BP);
    let originals: Vec<_> = projection.originals.iter()
        .filter(|original| original.path == path).collect();
    if originals.len() != 1 {
        return fail("audio Connectivity requires its unique normal projection preimage");
    }
    let preimage = originals[0].bytes.as_ref()
        .ok_or("audio Connectivity original provider was absent")?;
    audio_original_graph_provider(AUDIO_CONNECTIVITY_BP,
        std::str::from_utf8(preimage)?, mode)?
        .ok_or("audio Connectivity original provider was not validated")?;
    for (relative, expected) in AUDIO_CONNECTIVITY_PATCHES {
        let patch = repo.join(relative);
        if projection.applied_patches.get(&patch).map(String::as_str) != Some(*expected)
            || hash(&patch)? != *expected
        {
            return fail("audio Connectivity requires both exact normal applied patches");
        }
    }
    use sha2::{Digest, Sha256};
    if current.len() != 17018 || format!("{:x}", Sha256::digest(current.as_bytes()))
        != "e5b482317718cea8ce2a8dbe5c339daaf7837e92b1fa58c735dd4f3f48c58c44"
    {
        return fail("audio Connectivity complete normal projected provider changed");
    }
    Ok(Some(current.to_owned()))
}

fn audio_original_shared_provider(
    relative: &str, original: &str, mode: SoongDependencyMode,
) -> Result<Option<String>> {
    if mode != SoongDependencyMode::AudioApexTargetClosure {
        return Ok(None);
    }
    if let Some(complete) = audio_original_graph_provider(relative, original, mode)? {
        return Ok(Some(complete));
    }
    if relative == "packages/apps/Launcher3/Android.bp" {
        return audio_original_launcher_tapl_provider(original).map(Some);
    }
    use sha2::{Digest, Sha256};
    let (bytes, sha) = match relative {
        "frameworks/base/libs/WindowManager/Shell/Android.bp" => (6272,
            "fc3a3c4de8e8ffbfc4832125b6a7b448a50fea1e0b5c6bad8ceb767b55679738"),
        "frameworks/base/packages/SystemUI/Android.bp" => (49535,
            "fa1aaf330d580d6cefb74dc0ef1b52fcebbdd9b6bced5497a3bd29f9fb3647a3"),
        _ => return Ok(None),
    };
    if original.len() != bytes || format!("{:x}", Sha256::digest(original.as_bytes())) != sha {
        return fail(format!("audio original shared provider changed: {relative}"));
    }
    Ok(Some(original.to_owned()))
}

// SystemFeatures' retained Error Prone tests require this original helper.
// Keep its complete implementation and every transitive dependency in Audio;
// the allocator's prior private scope and NativeBridge route stay unchanged.
fn native_leaf_error_prone(original: &str, mode: SoongDependencyMode) -> Result<String> {
    if mode == SoongDependencyMode::AudioApexTargetClosure {
        use sha2::{Digest, Sha256};
        if original.len() != 5736 || format!("{:x}", Sha256::digest(original.as_bytes()))
            != "a8647e651304f9b1a6ff3740aade8723cd0628e711fdc9c18b17ec01790f959f" {
            return fail("audio original Error Prone provider changed");
        }
        return Ok(original.to_owned());
    }
    private_without_named_java_module(original, "java_library_host", "error_prone_test_helpers")
}

fn audio_original_launcher_tapl_provider(original: &str) -> Result<String> {
    use sha2::{Digest, Sha256};
    if original.len() != 18026 || format!("{:x}", Sha256::digest(original.as_bytes()))
        != "5c214bfc624650323ae51f0d1f6685a37e596a7d66796f5063a8d73103a0dc20"
    {
        return fail("audio original Launcher TAPL providers changed");
    }
    // The retained health rules require TAPL, whose original root-file chain
    // is exactly the library, its generated BuildConfig, and that generator's
    // shell tool. Keep every original dependency and all package/license data.
    // The other Launcher app modules retain the existing unselected scope.
    let mut result = metadata_only(original)?;
    // shared/Android.bp inherits this original parent-scope assignment. Keep
    // its source bytes rather than rewriting the child consumer's property.
    let variable = "min_launcher3_sdk_version = ";
    if original.matches(variable).count() != 1 {
        return fail("audio original Launcher shared minimum SDK variable changed");
    }
    let start = original.find(variable).ok_or("missing pinned Launcher minimum SDK variable")?;
    let end = start + original[start..].find('\n')
        .ok_or("unterminated pinned Launcher minimum SDK variable")? + 1;
    result.push_str(&original[start..end]);
    result.push('\n');
    for (kind, name) in [
        ("android_library", "launcher-aosp-tapl"),
        ("genrule", "launcher-tapl-build-config"),
        ("sh_binary_host", "launcher-build-config-tool"),
    ] {
        let marker = format!("{kind} {{\n    name: \"{name}\",");
        if original.matches(&marker).count() != 1 {
            return fail(format!("audio original Launcher provider declaration changed: {name}"));
        }
        let start = original.find(&marker).ok_or("missing pinned Launcher provider")?;
        let end = start + original[start..].find("\n}\n")
            .ok_or("unterminated pinned Launcher provider")? + 3;
        result.push_str(&original[start..end]);
        result.push('\n');
    }
    Ok(result)
}

fn audio_new_source_root_scope(
    relative: &str, original: &str, mode: SoongDependencyMode,
) -> Result<Option<String>> {
    if mode != SoongDependencyMode::AudioApexTargetClosure {
        return Ok(None);
    }
    use sha2::{Digest, Sha256};
    let (bytes, sha) = match relative {
        "packages/apps/Launcher3/tests/Android.bp" => (5776,
            "437663c4bed6a611728126dd588ace92111f27cb27c9a232dbe7595668c49eec"),
        "packages/services/CrossDeviceSync/Android.bp" => (3278,
            "29eacd3b289de1892582bbf4fe1cfbc5661472b1d7a6b91d24c4a2f86f75dea4"),
        "packages/services/CrossDeviceSync/lib/Android.bp" => (1742,
            "6204b0f4a99f592f7a59a696bfeb03864c61a5d00167bd01e594e23ffa00730f"),
        _ => return Ok(None),
    };
    if original.len() != bytes || format!("{:x}", Sha256::digest(original.as_bytes())) != sha {
        return fail(format!("audio newly discovered unselected source roots changed: {relative}"));
    }
    // Selecting the required original tests/tapl source cone also discovers
    // its ancestor Blueprint. These nine app/e2e test roots were absent from
    // the prior audio graph, and no retained provider depends on them. Keep
    // their package metadata under the existing unselected Launcher scope.
    // TAPL itself is the original root-file library, not a module in this file.
    // Likewise, adding the real CrossDeviceSync flag provider discovers new
    // app/test roots that have no incoming edge from the retained graph. Its
    // license remains original, and its independent flags BP stays untouched.
    metadata_only(original).map(Some)
}

// The retained service-ondeviceintelligence SDK library needs original released
// API inputs for both public and system-server scopes. Soong's prebuilt_apis
// load hook creates latest/combined modules only for scopes with real API files.
// Verify upstream bytes before projection; do not manufacture empty providers.
const AUDIO_ONDEVICEINTELLIGENCE_API_INPUTS: &[(&str, u64, &str)] = &[
    ("prebuilts/sdk/36/public/api/service-ondeviceintelligence.txt", 25,
        "39824f8c9fee1582598de5aa8cfa9653e84fbd69bd8aeb92c4a78c861faad552"),
    ("prebuilts/sdk/36/public/api/service-ondeviceintelligence-removed.txt", 25,
        "39824f8c9fee1582598de5aa8cfa9653e84fbd69bd8aeb92c4a78c861faad552"),
    ("prebuilts/sdk/36/system-server/api/service-ondeviceintelligence.txt", 25,
        "39824f8c9fee1582598de5aa8cfa9653e84fbd69bd8aeb92c4a78c861faad552"),
    ("prebuilts/sdk/36/system-server/api/service-ondeviceintelligence-removed.txt", 25,
        "39824f8c9fee1582598de5aa8cfa9653e84fbd69bd8aeb92c4a78c861faad552"),
];

fn validate_audio_ondeviceintelligence_api_inputs(
    source: &Path, mode: SoongDependencyMode,
) -> Result<()> {
    if mode != SoongDependencyMode::AudioApexTargetClosure {
        return Ok(());
    }
    for (relative, bytes, expected) in AUDIO_ONDEVICEINTELLIGENCE_API_INPUTS {
        let path = source.join(relative);
        let metadata = fs::symlink_metadata(&path)?;
        if !metadata.file_type().is_file() || metadata.len() != *bytes
            || hash(&path)? != *expected
        {
            return fail(format!("audio SDK consumer requires its original API input: {relative}"));
        }
    }
    Ok(())
}

// The retained DesktopTestLibTestsMobly consumer needs PASIT-defaults and its
// original Python, protobuf, JNI and Android snippet providers. Check upstream
// bytes immediately after normal source verification, before any projection.
// These inputs are not replacements, stubs or a relaxed Soong dependency mode.
const AUDIO_PASIT_ORIGINAL_PROVIDERS: &[(&str, u64, &str)] = &[
    ("tools/test/desktop/mobly/lib/pasit/Android.bp", 9623,
        "71cb178dbf79d5ce2974350a93f35fb82f3093b6ee46fca0d12d24ea6cc7c4fc"),
    ("tools/test/desktop/mobly/lib/pasit/passport/Android.bp", 1172,
        "6c46367958ae1a9a320c8925ad0f4a4ba5b1748ad3571a7344a5fb5ab3cb47d8"),
    ("tools/test/desktop/mobly/lib/pasit/snippets/hid/Android.bp", 1163,
        "f4425a2efa943566afeaf2aad3ad1754c8bd26053cf60429982b54ba7bd0e6f2"),
    ("tools/test/desktop/mobly/lib/utils/Android.bp", 2030,
        "95063ab7533dd67a4204cbb807323313675a340864321bb42642ba5c080f8d62"),
    ("tools/test/desktop/mobly/tests/pasit/Android.bp", 1107,
        "01b4a9495646aa94358153832915925f15c3b35752013e9810c7b2bed4d045e2"),
    ("external/grpc-grpc/Android.bp", 43866,
        "bf2fe1aa1e59fca322faed17fbeb0b9138d744fc51141674202a4060fcc3300f"),
    ("external/grpc-grpc/src/python/grpcio/Android.bp", 2162,
        "ca1565e658d47d0e0b65306fe30bcfdcb0d25b9df06ca1757e8e00953ec48c60"),
    ("external/grpc-grpc/third_party/address_sorting/Android.bp", 858,
        "6ad38a10c02683141584baf81774fbcb57aa60d5203bf9fbace6562d3592afce"),
    ("external/grpc-grpc/third_party/upb/Android.bp", 3225,
        "0848aa90ea027cb92124d031f6567bba6488a675f7e88722e0a67b41a576b631"),
    ("external/grpc-grpc/third_party/utf8_range/Android.bp", 729,
        "319e6b70c575b5b24713d3584b71393d23ff78ccf768ced8f5cb9e2d7c1bfd4a"),
    ("external/grpc-grpc/third_party/xxhash/Android.bp", 601,
        "bdc907cccd9e933a3539e122bf087eda7f46f578a8eeff14da27fb5bcf5d588b"),
    ("external/chromiumos-config/Android.bp", 3859,
        "5e3abe55cb6d81eb65cd78acb0f75c5386687b491159a919c71abb7e6ce67402"),
    ("external/chromiumos-config/python/Android.bp", 1460,
        "922664a63c44e569c6a2656590f243bccf95fbb1971348164ff1ca57433be85b"),
    ("external/python/snippet-uiautomator/Android.bp", 936,
        "069ba8f528d4c1312043e964cdcf7e7aaae7bb13a0e82a7df3679c8c95afa125"),
    ("external/python/snippet-uiautomator/snippet_uiautomator/Android.bp", 1429,
        "b4de85cd296a35c2ad4f0569b9cc6f0c05a240627f75c463b64aa1157b78a0b1"),
    ("external/mobly-snippet-lib/Android.bp", 972,
        "dd6f572562993de221a3efa2c874d5a080c47795dec3b3c8ac0fd9c6c5771ca6"),
];

fn validate_audio_pasit_original_providers(source: &Path, mode: SoongDependencyMode) -> Result<()> {
    if mode != SoongDependencyMode::AudioApexTargetClosure {
        return Ok(());
    }
    for (relative, bytes, expected) in AUDIO_PASIT_ORIGINAL_PROVIDERS {
        let path = source.join(relative);
        let metadata = fs::symlink_metadata(&path)?;
        if !metadata.file_type().is_file() || metadata.len() != *bytes
            || hash(&path)? != *expected
        {
            return fail(format!("audio PASIT requires its complete original provider: {relative}"));
        }
    }
    Ok(())
}

// Original edit_monitor Python dependency and its parent license declaration.
const AUDIO_WATCHDOG_ORIGINAL_INPUTS: &[(&str, u64, &str)] = &[
    ("external/python/watchdog/Android.bp", 917,
        "7ff3bf308b3e792abe06f463677b96bf75449662ca7544fed911e4677d09e1ac"),
    ("external/python/watchdog/src/watchdog/Android.bp", 871,
        "8580071e5cd98620834a301cacd66dfd70444fcf9de6db5ff80e7ceb8cb1f772"),
];

fn validate_audio_watchdog_original_inputs(source: &Path, mode: SoongDependencyMode) -> Result<()> {
    if mode != SoongDependencyMode::AudioApexTargetClosure { return Ok(()); }
    for (relative, bytes, expected) in AUDIO_WATCHDOG_ORIGINAL_INPUTS {
        let path = source.join(relative);
        let metadata = fs::symlink_metadata(&path)?;
        if !metadata.file_type().is_file() || metadata.len() != *bytes || hash(&path)? != *expected {
            return fail(format!("audio edit_monitor requires the original watchdog provider: {relative}"));
        }
    }
    Ok(())
}

// Complete original host-tool suppliers and every newly exposed ancestor BP.
const AUDIO_HOST_TOOLS_ORIGINAL_INPUTS: &[(&str, u64, &str)] = &[
    ("dalvik/tools/hprof-conv/Android.bp", 1117,
        "269a6745e536a5370fa2b509623a003e1f6b194a681b6364f1189a86560fc0fb"),
    ("development/tools/Android.bp", 1092,
        "a6f071651ca38f9f6bbd2fe6c2a9bc22288a69c8662c20c28e2e7b9ce9cd5655"),
    ("development/tools/etc1tool/Android.bp", 462,
        "a19ad99745b88cb0e8334c21cbcc1b8688153b511d98e2f47d284573e9888780"),
    ("external/e2fsprogs/contrib/Android.bp", 775,
        "19c341127f6aa3d58f59e0d5bd7fd51e49a8010e6cfcf8e0adc3ab94e95a4fd4"),
    ("external/e2fsprogs/contrib/android/Android.bp", 2148,
        "cbfe8e11a12a072d6708c2a3e34bd69cf67b6bb758a9c531440e4e50b087f124"),
    ("external/f2fs-tools/Android.bp", 9489,
        "ad9c356b284fd10a4d6700e721aeb77c831495d9efaa6ab33572455d16a3902b"),
    ("external/f2fs-tools/tools/f2fs_io/Android.bp", 802,
        "00094d01539246db80ef64cd2077dd7db66d406d3f805e2a135f3c5d65e3c8eb"),
    ("system/extras/partition_tools/Android.bp", 3648,
        "db1e21844d8771bb314781cddde8f05a043b5766db7691b85f5b9cf68dfc9d1a"),
    ("system/extras/partition_tools/aidl/Android.bp", 949,
        "5ea87b0a71f80afe8eee837c6c71ee3f7759ab3d3a6e728eefde1e262256968d"),
];

fn validate_audio_host_tools_original_inputs(source: &Path, mode: SoongDependencyMode) -> Result<()> {
    if mode != SoongDependencyMode::AudioApexTargetClosure { return Ok(()); }
    for (relative, bytes, expected) in AUDIO_HOST_TOOLS_ORIGINAL_INPUTS {
        let path = source.join(relative);
        let metadata = fs::symlink_metadata(&path)?;
        if !metadata.file_type().is_file() || metadata.len() != *bytes || hash(&path)? != *expected {
            return fail(format!("audio host tools require their complete original provider: {relative}"));
        }
    }
    Ok(())
}


// Original Trusty storage provider, including the complete parent header closure.
fn validate_audio_trusty_source_paths(lock: &droidloom_source::SparseSourceLock, mode: SoongDependencyMode) -> Result<()> {
    if mode != SoongDependencyMode::AudioApexTargetClosure { return Ok(()); }
    for (path,name,commit,cone) in [
        ("external/trusty/lk", "trusty/lk/common", "88b0dd09802a19f07869d45dcd9a87a291803201", "include/shared"),
        ("external/trusty/lk", "trusty/lk/common", "88b0dd09802a19f07869d45dcd9a87a291803201", "include/uapi"),
        ("trusty/kernel", "trusty/lk/trusty", "837ece72a3c50f454dfaf3bb86d5ac2e843c142b", "include/shared"),
        ("trusty/kernel", "trusty/lk/trusty", "837ece72a3c50f454dfaf3bb86d5ac2e843c142b", "include/uapi"),
        ("trusty/user/base", "trusty/lib", "165d46c463bd22524a7d33d177bf7f35dad46bf5", "interface/storage"),
        ("trusty/user/base", "trusty/lib", "165d46c463bd22524a7d33d177bf7f35dad46bf5", "include/user"),
    ] {
        let p = lock.projects.iter().find(|p| p.path == Path::new(path)).ok_or("audio Trusty original provider project is missing")?;
        if p.name != name || p.commit != commit || !p.sparse_paths.iter().any(|c| Path::new(cone).starts_with(c)) {
            return fail(format!("audio Trusty requires its exact original complete provider: {path}/{cone}"));
        }
    }
    Ok(())
}
const AUDIO_TRUSTY_STORAGE_ORIGINAL_INPUTS: &[(&str,u64,&str)] = &[
    ("external/trusty/lk/Android.bp", 747, "2f65b4f30d8a8709dffe8ef270703eaa656f8a780169d11380be38a3ea5c715e"),
    ("trusty/kernel/Android.bp", 674, "c1c3d549adf62f7f9380af63218d4a489dbe1693ef439fe6cb7cc12cf612ada8"),
    ("trusty/user/base/Android.bp", 1286, "421fff468ba8fff3fbf71ba5b64fb94110bd6b814437d2235b0ac8b83e819599"),
    ("trusty/user/base/interface/storage/Android.bp", 1018, "58f3a3c8e30084891c9aa417dd506d9d1825fdd7b4603a4422f0f56d6136d284"),
    ("trusty/user/base/interface/storage/LICENSE", 11358, "c95bae1d1ce0235ecccd3560b772ec1efb97f348a79f0fbe0a634f0c2ccefe2c"),
    ("trusty/user/base/interface/storage/include/interface/storage/storage.h", 22815, "4ee66aa7ea280344154f40dcdc97ddd8edc5fc84a61e6653f14db782f8fb11cc"),
    ("trusty/user/base/interface/storage/rules.mk", 730, "5e436ed64f6900c068314b8ef1122c284fc4228f6c76d9d0e556404bfa4e6fa1"),
    ("system/core/trusty/storage/proxy/Android.bp", 2035, "9a5a408efa8dc5bc2d1e62c526f79b7b66305ac972dd2867ffd8512dbd91d02b"),
];
fn validate_audio_trusty_original_inputs(source: &Path, mode: SoongDependencyMode) -> Result<()> {
    if mode != SoongDependencyMode::AudioApexTargetClosure { return Ok(()); }
    for (relative,bytes,expected) in AUDIO_TRUSTY_STORAGE_ORIGINAL_INPUTS {
        let path = source.join(relative); let metadata = fs::symlink_metadata(&path)?;
        if !metadata.file_type().is_file() || metadata.len() != *bytes || hash(&path)? != *expected {
            return fail(format!("audio Trusty requires its complete original provider: {relative}"));
        }
    }
    Ok(())
}

// Original ADB/WebRTC providers, transitive libraries, parent metadata and consumer contracts.
const AUDIO_ADB_WEBRTC_ORIGINAL_INPUTS: &[(&str, u64, &str)] = &[
    ("build/soong/cc/fuzz.go", 22465,
        "5a784754990ffe297fcdfd832ec6279754220648b061583c56f6b0571a9dc115"),
    ("external/libevent/Android.bp", 3364,
        "998ca72d3151814ba2af8736171325cb372bcfba8a2cd77cca2a32d18e7af0e6"),
    ("external/libsrtp2/Android.bp", 3018,
        "348434ba864251d76528ce0f850d767d632244be163563a965d7d754647a2331"),
    ("external/libusb/Android.bp", 4545,
        "3001992a167843dcedb0fe1411d25b11bff6289aba054ace8872fee56b64fca6"),
    ("external/openscreen/Android.bp", 6519,
        "d081703fe3c8c2c13dc87074c7d348694eb6122b9948c6d63b1816bb28069c0a"),
    ("external/openscreen/third_party/abseil/Android.bp", 2079,
        "464b1cf29838623f7354f3db433c2a8cab6a216dc618fc4975111ed5dd1cda79"),
    ("external/pffft/Android.bp", 1939,
        "ee7a1baa29a10223bf091cbf1e82e065a1520adf1a415dfd08bb80eae4606193"),
    ("external/rnnoise/Android.bp", 666,
        "5a8e68158c697ed8ceb9d95407142818a3ff5138b90f39188bfa4c8119897b4c"),
    ("external/webrtc/Android.bp", 186479,
        "3deab91c64d1f5bcf50fcb3ba2801e5ab230daa5e4e2a28ef4c3d4869e61135d"),
    ("external/webrtc/sdk/objc/base/RTCMacros.h", 1965,
        "44d6203968801af27a7e92620c9f021cf1e6d3b177bf378ec02d2ae057f66c7a"),
    ("external/webrtc/sdk/objc/native/src/audio/audio_device_ios.h", 13346,
        "0347a89ed338d2799838e994b220782775eae728661ca8755e5abd8715eea0b6"),
    ("external/webrtc/sdk/objc/native/src/audio/audio_session_observer.h", 1259,
        "f72e0a9d4d1f78133a401ac2340b3464cdb7c81921a743c29566f7ab992f7671"),
    ("external/webrtc/sdk/objc/native/src/audio/voice_processing_audio_unit.h", 5979,
        "5cbaf39de22823fd3ede5309f0516b6ae188eab8ced6ec9fa230c5863ec6fa9b"),
    ("external/webrtc/third_party/crc32c/Android.bp", 366,
        "606966a55944866a8d173d658b24043e7f3bcd3add9dc055741213f2b0471cc6"),
    ("frameworks/av/media/libeffects/preprocessing/Android.bp", 2064,
        "bc76ee824a0f504accf731d6524df84e758eb47bfab2386b4f42ae3c7085665a"),
    ("packages/modules/adb/Android.bp", 27549,
        "485922ab5a3742db71c9da7819b2b87821acdbc56c423f0feb244b3d21315be7"),
    ("packages/modules/adb/client/adbmdns/Android.bp", 1154,
        "893d912872bf7f92447527e0aec2bd15c79206356460f3a82537b4d7118717a7"),
    ("packages/modules/adb/crypto/Android.bp", 2195,
        "785e311f34cb1113e3156d94ccfc6d103f5d648510941b4ca48c7a8a15936f32"),
    ("packages/modules/adb/crypto/tests/Android.bp", 1262,
        "6b6e8aa0206253d6920838c891158ac93f845aa862f31d7ce1118eee9a01d5da"),
    ("packages/modules/adb/fastdeploy/Android.bp", 2666,
        "e0e9911181a2c8d5648044b1ba1b7e8bd974eedff7052d26d2143b031d552de3"),
    ("packages/modules/adb/libs/adbconnection/Android.bp", 2735,
        "27f64796bf1c17e7524a7f6fe709e594e02b21998cfcea9c9f1a907630cae554"),
    ("packages/modules/adb/libs/libadbd_fs/Android.bp", 1025,
        "b40d89e420601e465220495fff965a1dc7d4a485b6961b27ace8b76a9d346a40"),
    ("packages/modules/adb/pairing_auth/Android.bp", 2353,
        "50e328864936955cdf54715be49fef2c651f307ad58047fe35a0fc21c6dc4eb0"),
    ("packages/modules/adb/pairing_auth/tests/Android.bp", 1154,
        "a529c42ca2902f3fd8b0fee033caa85816ffda5bdfbbeff8e8a067f17e540219"),
    ("packages/modules/adb/pairing_connection/Android.bp", 4914,
        "dfac1357dc2381f45ccff5c6bba99e72259c9bd9ed84a02b2ea4f07537da28d6"),
    ("packages/modules/adb/pairing_connection/tests/Android.bp", 1517,
        "56aac62791510c102c00067fe8a3e793449bb17531b80e7c9f066defc6143e0f"),
    ("packages/modules/adb/proto/Android.bp", 4238,
        "09c3b00c40e2d3ac52fdb3fc888873d5b141e34c0a2799a4efeb0d2ba6cc70ff"),
    ("packages/modules/adb/tls/Android.bp", 2068,
        "a432e3e7408032be9dba76c077622f1e808737eb58c1ea24bc5561ed39d597f1"),
    ("packages/modules/adb/tls/tests/Android.bp", 1269,
        "acacd6e8e4921057fa0d575a99c46734d4852af7b301e2cefe1e48696b43aa56"),
    ("prebuilts/clang/host/linux-x86/Android.bp", 17607,
        "d6c17476ae87bdd901e07bb2cc5ddbaeff4ce70569aa476ea40c7e119d521e1b"),
    ("tools/security/fuzzing/libFuzzer_mte_crash_handler/Android.bp", 836,
        "1a7fc157fdb0e65ac2dd53fecab46e7917f6b7e4b6d6c0abf89d7794ef15924c"),
    ("tools/security/fuzzing/libFuzzer_mte_crash_handler/crash_handler.cpp", 3424,
        "e06ce2812001d86bfccb118540cf27037e3a8e108c4f13a076224f15a96d6e00"),
];

fn validate_audio_adb_webrtc_original_inputs(source: &Path, mode: SoongDependencyMode) -> Result<()> {
    if mode != SoongDependencyMode::AudioApexTargetClosure { return Ok(()); }
    for (relative, bytes, expected) in AUDIO_ADB_WEBRTC_ORIGINAL_INPUTS {
        let path = source.join(relative);
        let metadata = fs::symlink_metadata(&path)?;
        if !metadata.file_type().is_file() || metadata.len() != *bytes || hash(&path)? != *expected {
            return fail(format!("audio ADB/WebRTC requires the original provider or consumer: {relative}"));
        }
    }
    Ok(())
}

// Original VINTF consumer and complete VTS provider cone, parent Blueprint and AIDL inputs.
const AUDIO_VINTF_VTS_ORIGINAL_PROVIDERS: &[(&str, u64, &str)] = &[
    ("system/libbase/Android.bp", 6804,
        "2e3f7e52769a44e4b0f7d3c6557776e9d939da2733118574f2b350e63cd3894d"),
    ("system/libvintf/Android.bp", 6296,
        "e9a91645f7a13b096242acd1e511ef07cf42845a51d62010cde99d8568702853"),
    ("test/vts-testcase/hal/treble/Android.bp", 717,
        "2690e6d734b18fba5fff3238e8266736d50fb17f9d2e630e82348f1521ab945a"),
    ("test/vts-testcase/hal/treble/vintf/Android.bp", 4324,
        "69291d2ef340ad2a3776a1be2b18222a3f941b2628f9cc797a48e02ce9e671ea"),
    ("test/vts-testcase/hal/treble/vintf/DeviceManifestTest.cpp", 20018,
        "430b85f25368733499b7b4770ed3ae760ebb7fd797c046a88b9ae7929fa1ccfa"),
    ("test/vts-testcase/hal/treble/vintf/DeviceManifestTest.h", 1300,
        "efba10687463c874e58e8c25e11b30328d50c41dbf95eff180ffd05a5f60bd99"),
    ("test/vts-testcase/hal/treble/vintf/DeviceMatrixTest.cpp", 3216,
        "461c6cbd783b885026c265ad9b4ae7d8c6237bc177cea9295f8e64fb1c20dbc8"),
    ("test/vts-testcase/hal/treble/vintf/DeviceMatrixTest.h", 1172,
        "32d20a54c7b129182a1c7e538e99948b01ffda3b385aa43cce8242a6d7ddf551"),
    ("test/vts-testcase/hal/treble/vintf/OWNERS", 62,
        "c718c10861fc554276f518d5a6fc199bf57070372ae68ce59377f9577dfaa58d"),
    ("test/vts-testcase/hal/treble/vintf/SingleManifestTest.cpp", 44443,
        "340642cfbec3ea07f876457273b5bebdafd6880efe770b003dbfcdf888c33ba4"),
    ("test/vts-testcase/hal/treble/vintf/SingleManifestTest.h", 2483,
        "8b0801e0bbfd6675d201e0ac9421f8fecd6b52bc3d0c3277e99ee58a3a1a569a"),
    ("test/vts-testcase/hal/treble/vintf/SystemVendorTest.cpp", 7734,
        "e4592f2a23caf8c8df1a1a6115fa2126f12de0131e22cd31739f033a675519ad"),
    ("test/vts-testcase/hal/treble/vintf/SystemVendorTest.h", 1655,
        "0485d6c24fc6f6ab6a4d8420baaaf4ba80485b7b883483d59b446ccbfa6a46d9"),
    ("test/vts-testcase/hal/treble/vintf/TEST_MAPPING", 387,
        "59c2308f450acdc62584cea91ce61067e6c5f1c130cb0170adecaaeac6799e6d"),
    ("test/vts-testcase/hal/treble/vintf/VtsNoHidl.cpp", 3949,
        "b0d2d09d2c7bc9454e716b667559d41113a13d9262a193d2b687d5ae23128ee7"),
    ("test/vts-testcase/hal/treble/vintf/VtsTrebleVintfTestBase.cpp", 9194,
        "6c1fcdc1f518bed92e863cabc94892afeb83424c7764a84779c5ebbf4ee4df7e"),
    ("test/vts-testcase/hal/treble/vintf/VtsTrebleVintfTestBase.h", 2739,
        "ef87f7c3b71c245637297d0fac1f521ebb1c975ef24f4e6fd3070ea82c18aee1"),
    ("test/vts-testcase/hal/treble/vintf/aidl/Android.bp", 156,
        "0c8b470e7fff2671818d442f2e372864ff26c6a9118baff37da7c436a3b4ba42"),
    ("test/vts-testcase/hal/treble/vintf/aidl/android/vintf/IServiceInfoFetcher.aidl", 1279,
        "b9cbc95820fddbe27f8d412c6de511eff8d65077151f62eb98fe7c63dd812a4b"),
    ("test/vts-testcase/hal/treble/vintf/aidl/android/vintf/ServiceInfo.aidl", 1719,
        "12d11d6597f3f135aa86f9ea2e61a42a53b58d494292a6b33de753eeda6f968a"),
    ("test/vts-testcase/hal/treble/vintf/aidl/android/vintf/StabilityLevel.aidl", 783,
        "a10a5b3024308ff962f46bc18ab5d38b80947e37d6013dcfb7b3b85beebff9cf"),
    ("test/vts-testcase/hal/treble/vintf/libvts_vintf_test_common/Android.bp", 930,
        "d0ec7e7a9a493a455c3203ba2971b4f0bf59c7dfe4b253b863fa78e9278d1ef5"),
    ("test/vts-testcase/hal/treble/vintf/libvts_vintf_test_common/common.cpp", 4141,
        "87f575934f7cb356209ea7c0f5b27fd62bd88b889236d7e39b0d92060450a003"),
    ("test/vts-testcase/hal/treble/vintf/libvts_vintf_test_common/include/libvts_vintf_test_common/common.h", 1309,
        "61fa7188204d51a52b16b6bf38939ded618cd5aff6e39ce6507f780ee8af8e2c"),
    ("test/vts-testcase/hal/treble/vintf/main.cpp", 915,
        "fabd1a6ed2e71e774971295f37e7224b721f3af761e9d57e5677134b6824563b"),
    ("test/vts-testcase/hal/treble/vintf/utils.cpp", 5773,
        "08b9ab60c326b6d1b7e56aa89cde51a8478b3d2262369df2f37a6fbccf42eb0b"),
    ("test/vts-testcase/hal/treble/vintf/utils.h", 7510,
        "46d5e8ec53bd02b53c5f0ad3fe3ecb4a5d59879785c621789a757b56d6ac4e51"),
    ("test/vts-testcase/hal/treble/vintf/vts_treble_vintf_framework_test.xml", 2124,
        "891b054c65909e7e12f56923f555843bb71c963645777a2ffa9660ea26e664b4"),
    ("test/vts-testcase/hal/treble/vintf/vts_treble_vintf_trusted_hal_test.xml", 3841,
        "c42d9336d6b8300d4ed97d20040536109b6495f89d16474f3a2fd4b7906156a5"),
    ("test/vts-testcase/hal/treble/vintf/vts_treble_vintf_vendor_test.xml", 2112,
        "38a00f6a812adfaa3edd9c28b2a520017c21cf62608b5824ffd853879ab812ea"),
];

fn validate_audio_vintf_vts_original_providers(source: &Path, mode: SoongDependencyMode) -> Result<()> {
    if mode != SoongDependencyMode::AudioApexTargetClosure { return Ok(()); }
    for (relative, bytes, expected) in AUDIO_VINTF_VTS_ORIGINAL_PROVIDERS {
        let path = source.join(relative);
        let metadata = fs::symlink_metadata(&path)?;
        if !metadata.file_type().is_file() || metadata.len() != *bytes || hash(&path)? != *expected {
            return fail(format!("audio VINTF/VTS requires its complete original provider: {relative}"));
        }
    }
    Ok(())
}

// Original CHRE Pigweed providers, generator inputs, defaults and consumer.
const AUDIO_CHRE_ORIGINAL_PROVIDERS: &[(&str, u64, &str)] = &[
    ("external/emboss/Android.bp", 2450,
        "69b8a9b99837807626b0da843e2b69b530a04d91b835d8792ac075edbc10fb98"),
    ("external/emboss/compiler/back_end/cpp/generated_code_templates", 34201,
        "6a4c007a26fa26af617253c700cb27c947ea42281b97711307a60dc8c0843881"),
    ("external/emboss/compiler/front_end/error_examples", 20637,
        "b616743b86a42723cbd4a1e0d3d5f0fa2d56e42a444b9f15e8370454e4999abd"),
    ("external/emboss/compiler/front_end/prelude.emb", 2670,
        "8968a6e7fc91960391bb224905b45a342498e5f95d27d1658c8b417bf58e7d6a"),
    ("external/emboss/compiler/front_end/reserved_words", 11161,
        "4f7cfd4d60e12b40fe0b289697c2119f7a586e2211562247cd73150d3a949adb"),
    ("external/emboss/embossc", 3372,
        "ddbe2cb82ec4ba191e49e010978525830ac94531ed1f655eaa0e03cd36925c99"),
    ("external/emboss/runtime/cpp/emboss_prelude.h", 32172,
        "ef937b8d364dc2004e70012450abde15ac45c5277eb7954346eb30eeafc1ba92"),
    ("external/pigweed/Android.bp", 852,
        "0237ce95d4e6ac1e0bf2d6b8dc26840d7e625687609de067cb7099819ce61252"),
    ("external/pigweed/pw_allocator/Android.bp", 1898,
        "222c200206cbdf9106c5ed4d786cef3b6982e32356f07e0453701e1611decc6e"),
    ("external/pigweed/pw_assert/Android.bp", 944,
        "2d3fbac5926bec5d39bdfde09120f463307b256ec6b56b88ddfa4741bc6a2047"),
    ("external/pigweed/pw_assert_log/Android.bp", 1390,
        "c8c1bc779fb7dc92091ab7818e2a397ee27f52cc867a2f8b959c6b974e418cc4"),
    ("external/pigweed/pw_async2/Android.bp", 1571,
        "2088c174111dbd045feea45faaf7d41599cef099ba55e55ce943fccb8e32423e"),
    ("external/pigweed/pw_base64/Android.bp", 1139,
        "805e554c646f42a94bf9c32077e1454a0b0452460f9d369b4b9e85d0c37f5c6a"),
    ("external/pigweed/pw_bluetooth/Android.bp", 6581,
        "a995bbf09b9514423cadde6cfa7e1e021b6320c51111ee2d018091b4ee1f6a78"),
    ("external/pigweed/pw_bluetooth_proxy/Android.bp", 3454,
        "c66541195c390eab55bd2fe3fe4a8a4224da353c9e277a27482570b415321904"),
    ("external/pigweed/pw_bluetooth_proxy/gatt/Android.bp", 1601,
        "68fcbb256c8c88c1ec93f40c02ca4d1af22633f6bd30d5ac192e1e5fa9c92cb5"),
    ("external/pigweed/pw_bluetooth_proxy/hci/Android.bp", 3691,
        "77375db679fc31e8baf6869da8aa71a224da313559e426f0d318bd9854dcbc06"),
    ("external/pigweed/pw_bluetooth_proxy/rfcomm/Android.bp", 1828,
        "4608e089d91a2d1031a3899949279af9b87842800f6c3726b73bf47a7660dab7"),
    ("external/pigweed/pw_build_android/Android.bp", 2786,
        "b5f2354c666827c900816435ff3c295704b79a9c9058fcb7aa3c6e4f4b48e6c5"),
    ("external/pigweed/pw_bytes/Android.bp", 1386,
        "1d99d60689ef8f86729db3887c82487f07f347e4d8e31f38acfe9c6371dfb780"),
    ("external/pigweed/pw_checksum/Android.bp", 948,
        "8522ee979feb57360c164f550d96a8e36abd70871043b36e517992724bb8031a"),
    ("external/pigweed/pw_chrono/Android.bp", 1814,
        "1be7d8b9053c9f20237488beff24929bfc926a260f235fd4edc8fb5d9061744e"),
    ("external/pigweed/pw_chrono_stl/Android.bp", 1523,
        "ae074ddb7fa0871df1c3d195b36779fca74eec987f43c952320669c55ef0d553"),
    ("external/pigweed/pw_containers/Android.bp", 1474,
        "e23d29aaa4610ce0706e8c1e24e78c08171cddfe43c7e02a5d95d5fef8bf37ee"),
    ("external/pigweed/pw_elf/Android.bp", 1319,
        "3fe24f7942081440aa872cf520480ffefafbad65cd845f7b0cdd9aa9893b753e"),
    ("external/pigweed/pw_function/Android.bp", 968,
        "5117051b7d05dbb9029cd0ebcea6024b95ff92610efd050d4795c4d70702b3f5"),
    ("external/pigweed/pw_intrusive_ptr/Android.bp", 933,
        "9f7e0e934b51193c07dda771378244638fa79159d4e1f721ba5dba662d082bf5"),
    ("external/pigweed/pw_log/Android.bp", 6786,
        "759ad255c7b2955d2e8d5d4a79d43e12faa3235694b1f7a52ecb23b6885b4a5d"),
    ("external/pigweed/pw_log_android/Android.bp", 1601,
        "a23d4dd3e9a50496c6d959bf6e0f7ebdb1f902cc19774a6cfda545f4399f0b1e"),
    ("external/pigweed/pw_log_tokenized/Android.bp", 830,
        "d90286454cb7ae02dd1449a78b7983b74cb4f449e04906dabcaa6212ec6409d3"),
    ("external/pigweed/pw_memory/Android.bp", 823,
        "fa41cfd61e001b7c71464b83e0f887a7bc9131994b21deb726385759db00f0b5"),
    ("external/pigweed/pw_metric/Android.bp", 2883,
        "afba03c4578ae11b852ea981457e71809d51827d1425e675976254ae851f442f"),
    ("external/pigweed/pw_multibuf/Android.bp", 4767,
        "c3bbd313e3cf93625307a1d9abc7310d0147918f329a9f214b82da310ac45500"),
    ("external/pigweed/pw_numeric/Android.bp", 944,
        "9a78571fbb3e555409e598386ba5e0a15fd6de01abe6cb7b2fb2c96445dcdc5a"),
    ("external/pigweed/pw_polyfill/Android.bp", 825,
        "9115c242ec848d004b8a19bb5ce46f9e2e9d53415db3d136e99daa1036dca7ec"),
    ("external/pigweed/pw_preprocessor/Android.bp", 941,
        "812cbdfcdc3821cd5400e2750fc6f04e2397c47936b4d326559c748f14ee76d2"),
    ("external/pigweed/pw_protobuf/Android.bp", 7072,
        "baa4b79f24bb6913d63d16dd8932542737bfb317d245737a14de4bb66ab90341"),
    ("external/pigweed/pw_protobuf/py/Android.bp", 1207,
        "3d32e35a379ee3402df520ac847be73f2ed461e35a8a30e1e6556526d11855f9"),
    ("external/pigweed/pw_protobuf_compiler/py/Android.bp", 979,
        "6858535d8fc21d24994ddc632e763c03c87693a1e81cc9a8ccd616bb2a156671"),
    ("external/pigweed/pw_result/Android.bp", 1212,
        "5adbf3fb697873dea93afa7795108f3e6e34e1d71078a10e500b4d53ce9c5bdb"),
    ("external/pigweed/pw_rpc/Android.bp", 24280,
        "9694fa240b3d74426f3258dd120c79f63a58a367bf7d6b244ffb5e5da6e5de67"),
    ("external/pigweed/pw_rpc/nanopb/Android.bp", 2265,
        "ffd5cd022e84e60e4fc3d89bf08111121b7b5e7538d12f2fb4516ca3fad939a9"),
    ("external/pigweed/pw_rpc/pwpb/Android.bp", 1301,
        "a6e3606b0c018aaea41eec764149904510b3358bc9db7c3ce48b47a84b7fc249"),
    ("external/pigweed/pw_rpc/py/Android.bp", 1676,
        "d046ed2b4f44e1b1ba5311554a273b65cf2b3bbb9d9c068d87a0fe8e8644017a"),
    ("external/pigweed/pw_rpc/raw/Android.bp", 1950,
        "31d7b4395d970a71ab25b770f1f420922599ce58f14bb0937679b3e31aa40d32"),
    ("external/pigweed/pw_span/Android.bp", 1433,
        "2be142386fa754f4570abd59a6065bfcbe9a58f01a3ac373c48375654fba690d"),
    ("external/pigweed/pw_status/Android.bp", 863,
        "77eb7619ee75e4423f53a537f23b10e74d75d24963143d705b504f366f828a75"),
    ("external/pigweed/pw_status/py/Android.bp", 773,
        "8ad777ef5a04da14298ddb180170e647e3ad634c3bb84490a39b8c427a0b346f"),
    ("external/pigweed/pw_stream/Android.bp", 2503,
        "22e5fd0198c748647fea5109938a9900b9a1dd4be1517386ececb6af799c8a4b"),
    ("external/pigweed/pw_string/Android.bp", 1485,
        "db5e9e2736f4c8b0f5539b7639e7ea56b67d870a2dc42e437e747552fc82d58e"),
    ("external/pigweed/pw_sync/Android.bp", 1470,
        "e7d97d50ae68b303f645ff67d447e9142f886cf5a3baaed52a23b8d8345f1623"),
    ("external/pigweed/pw_sync_baremetal/Android.bp", 1083,
        "6fab65f7398b018d175f43e867dca6a604fe72dca52766e54dd7da8541acbb49"),
    ("external/pigweed/pw_sync_stl/Android.bp", 1595,
        "0443f99048912431361438ad8d8d04ba16801c174c1bfa23e2c8135c1aa7330b"),
    ("external/pigweed/pw_thread/Android.bp", 2870,
        "965f4c215ee60975420a82368ad93d5c8b27f9c016465b020c920e250a20564c"),
    ("external/pigweed/pw_thread_stl/Android.bp", 1522,
        "f2257de2a41867f9fbada785a379f9f80e2994177764ff7f02aeee9530870d44"),
    ("external/pigweed/pw_tokenizer/Android.bp", 4608,
        "e45f2bb773424ea2e2d29f048d622ae7c9487f7706819c063eb0e73acd1a7d46"),
    ("external/pigweed/pw_toolchain/Android.bp", 949,
        "39422efc23b8f37142b0898b7151db6946a7a7cbdcc076fada321a8dfd9f1ad7"),
    ("external/pigweed/pw_varint/Android.bp", 1348,
        "dbed35383358b8c77be100c627beb93c2955890350f91857f96a8f504bb8b46e"),
    ("external/pigweed/third_party/Android.bp", 1580,
        "0a4f52a496995a38e7cffb81c5ae319b777c23529f50890464fcffcccf43a6a5"),
    ("external/pigweed/third_party/emboss/Android.bp", 853,
        "029abd1f68d1c936bfdb5ecd7993a4e449facd8bc9e93d554827bb012bc3a404"),
    ("external/pigweed/third_party/emboss/embossc_runner.py", 1010,
        "828222c28cdbd23a4837b47af947b2e99a431ddfb58ce1b485c9ee466d8ff3e9"),
    ("system/chre/Android.bp", 49456,
        "64ceaec43e29dea5f875d7ca33cef33baae7b097e40b3a60a59f18f0d27e6783"),
];

fn validate_audio_chre_original_providers(source: &Path, mode: SoongDependencyMode) -> Result<()> {
    if mode != SoongDependencyMode::AudioApexTargetClosure { return Ok(()); }
    for (relative, bytes, expected) in AUDIO_CHRE_ORIGINAL_PROVIDERS {
        let path = source.join(relative);
        let metadata = fs::symlink_metadata(&path)?;
        if !metadata.file_type().is_file() || metadata.len() != *bytes || hash(&path)? != *expected {
            return fail(format!("audio CHRE requires its complete original provider: {relative}"));
        }
    }
    Ok(())
}

// Original bcc_compat source, its inherited defaults and existing dependency providers.
const AUDIO_BCC_ORIGINAL_PROVIDERS: &[(&str, u64, &str)] = &[
    ("frameworks/compile/libbcc/Android.bp", 4058,
        "4ca16abde50edf9a354b07d4d5be2d777f0f5c4d3ea17c3aafb9d1c981403174"),
    ("frameworks/compile/libbcc/tools/Android.bp", 424,
        "c01fb11463a73c3a123c5df71bd731206d1743379e75946b4524731004f2a47a"),
    ("frameworks/compile/libbcc/tools/bcc_compat/Android.bp", 1523,
        "ea4c4f94e63227e29e886ed6d7df7a51ca94b9a3e8c743f8d569d1db8f40086a"),
    ("frameworks/compile/libbcc/tools/bcc_compat/Main.cpp", 9427,
        "d7b8aef5a94119dd93620baf3fff0f260f277092a6113e6c0f8fed67643f7bad"),
    ("frameworks/compile/libbcc/lib/Android.bp", 2708,
        "9c11eefede1e7a47e5d11ca416156687f490523e57480ad033f0638a6b95e0a8"),
    ("frameworks/compile/libbcc/bcinfo/Android.bp", 3254,
        "5de036d60938ea6fd8f5ec0ece88427a76a5e1539de6b8e13f6ad9c92577632d"),
    ("frameworks/compile/slang/Android.bp", 6132,
        "d35d89aff4360900e8d539bc5fd60c3fde59d3d9157f2f7c8c7fa556590822d2"),
    ("external/llvm/Android.bp", 9862,
        "0bda6d7cb9cd6e6d315faaf38738fe2ec170eeb03412a89868b217f49145a1a0"),
    ("external/llvm/lib/Android.bp", 1122,
        "ff9db387ee3a98367725ded74243b4b9171d260ee6c4ae2fd38f6c3055ffb6a1"),
    ("development/build/Android.bp", 15422,
        "7ddfd0a4b3df0d09e6e57a69c659971ea243fcbaf6bf8e68732edf75699e3045"),
];

fn validate_audio_bcc_original_providers(source: &Path, mode: SoongDependencyMode) -> Result<()> {
    if mode != SoongDependencyMode::AudioApexTargetClosure { return Ok(()); }
    for (relative, bytes, expected) in AUDIO_BCC_ORIGINAL_PROVIDERS {
        let path = source.join(relative);
        let metadata = fs::symlink_metadata(&path)?;
        if !metadata.file_type().is_file() || metadata.len() != *bytes || hash(&path)? != *expected {
            return fail(format!("audio bcc tools require their complete original provider: {relative}"));
        }
    }
    Ok(())
}

// Exact original test-tool providers from the same pinned Android superproject.
const AUDIO_TEST_TOOLS_ORIGINAL_PROVIDERS: &[(&str, u64, &str)] = &[
    ("dalvik/Android.bp", 397,
        "f7b9402fa49017530daffcf9988d0ceca373882fad92325aaa7388b51ad5a9d2"),
    ("dalvik/tools/dexdeps/Android.bp", 1083,
        "cc8dce9ef5443652d09c3f11c459bd7b21b4eea2caa7855378cc814afd0900bf"),
    ("external/python/absl-py/Android.bp", 1045,
        "c6f20cd28b53137cb6c6639f01ebc22e098f7a156483ebf8408cc3bdc0445014"),
    ("external/python/cachetools/Android.bp", 992,
        "306e8188f17b0781496816a018307b549c13d57271e0f102aec41e25cfef9277"),
    ("external/python/cachetools/src/Android.bp", 814,
        "c873763d666b64f0344e017ee580595fb0eb8eb02de0e63c70827c443c033879"),
    ("external/python/google-api-python-client/Android.bp", 2207,
        "0e4d4b22a368c48994797102ce19c37516c893c10644adcda92ea295ba073bc8"),
    ("external/python/google-auth-library-python/Android.bp", 1327,
        "ce8e59e8652c27f97e9d8fef7c11d1a373c5f85ce5ca881069bea12cf4fdd26b"),
    ("external/python/httplib2/Android.bp", 2479,
        "aa348e8e1ce63899a1bf344f5d0b4ecbfe140894381bc1ee11d0dbad5b644c8f"),
    ("external/python/oauth2client/Android.bp", 1010,
        "b6afdaa29170260505790633553d1b3199d5db174dda3ac96b9fe85e4305db39"),
    ("external/python/oauth2client/oauth2client/Android.bp", 1301,
        "34fab3eee6cf54e57440c89dc063d2310e6b26c41ca03acb561d00f076e360c0"),
    ("external/python/pyasn1-modules/Android.bp", 1011,
        "6b8b7f35696b65daf204bb7df81a8a588317e8df19dfd43002879918ee0dc159"),
    ("external/python/pyasn1-modules/pyasn1_modules/Android.bp", 1154,
        "193c203c70fad21899d8984522dfe85350c709b5628f5bcebfda6e2c7295eeae"),
    ("external/python/pyasn1/Android.bp", 1004,
        "a90b962dfccb85871b953c7351d898af180e170d408d14c080b4f252b9f24ee2"),
    ("external/python/pyasn1/pyasn1/Android.bp", 1265,
        "e6c4e49f554edf8cd8e0e613c84fa258d4691a4ce71be17c0a1d19733becada5"),
    ("external/python/python-api-core/Android.bp", 1321,
        "feaab5b32ff8e2d8b94f3e2c9a25bd74eb54cfa7dc9176c79a25009e609d7084"),
    ("external/python/rsa/Android.bp", 992,
        "9c9d9890258837bba57bdd8a480177f531994a67f66604b1f039b991604b4dbd"),
    ("external/python/rsa/rsa/Android.bp", 1117,
        "dfa5ef469aab81bf3bcda6b46c0ad6d07b3637652e90b02adf45c47bb591335b"),
    ("external/python/uritemplates/Android.bp", 1304,
        "70a43368834d111e5d69feca3befb7776c2b633bb65b84cbb3b3add4d26b9589"),
    ("external/python/uritemplates/uritemplate/Android.bp", 1111,
        "9aadaa186800f26e78ac49ce9930fde768c6502face003fa719dc9c6a330fe18"),
    ("external/scapy/Android.bp", 1302,
        "116fe925311c6568aab026a7e8eca453bb9830f1d07f8aee7d4ce2c839ad1c44"),
    ("tools/asuite/Android.bp", 1960,
        "04118667724a0433770f8d913207c510b5103a41d44600da62c337434ed2c5ae"),
    ("tools/asuite/atest/Android.bp", 4006,
        "c38865f4312919d6452897db8e2e9341919ccb659c7a537ae20690a866e891e1"),
    ("tools/asuite/atest/asuite_lib_test/Android.bp", 1273,
        "be125e24659129d2cb7b0245c34460e7d9b7f982a55f6c17aa6ce7eb1dcbde0e"),
    ("tools/asuite/atest/coverage/Android.bp", 379,
        "a356301928e786a091235572f5dc6978b77fd70b9eed10192d2fd08bbf16e26f"),
    ("tools/asuite/atest/integration_tests/Android.bp", 4243,
        "8a0d5c242ddcc8deb2302cfaf6412bf7c10fd63fc1510ceecd44feeeaab21f01"),
    ("tools/asuite/atest/integration_tests/device_android_test/Android.bp", 1360,
        "98df10d5baacf237a0da1eaee8d58e0eae65c66e139ef0093c98c8305378ec25"),
    ("tools/asuite/atest/integration_tests/device_cc_test/Android.bp", 894,
        "fe3001f67ca6ac2573280a2e6aeb2449116f01266400a34b14de7679fd313832"),
    ("tools/asuite/atest/integration_tests/deviceless_cc_test/Android.bp", 803,
        "d834c16f6ae480ba4f57aa4c54c86b5decf756265f9151e716e10425435e4ff5"),
    ("tools/asuite/atest/integration_tests/deviceless_cc_test_host/Android.bp", 813,
        "2cad241fa005ee164c194df1d46849b611fcf9ea9fdb5cfcbe116cb91afce5f0"),
    ("tools/asuite/atest/integration_tests/deviceless_java_test_host/Android.bp", 895,
        "21c4dd61c0b0d54eb307386b1452988c1820a73f9b15c6c2079b15e123b84584"),
    ("tools/asuite/atest/integration_tests/deviceless_python_test_host/Android.bp", 845,
        "83de8bf2e4bfd6164ce9539918402252ffc84261556123ba435fcf8a64475849"),
    ("tools/asuite/atest/integration_tests/deviceless_python_test_host_multiclass/Android.bp", 342,
        "6da15ee0704ec1d7ad83b26ee97d8343cad005b7493ca0392035c07124601527"),
    ("tools/asuite/atest/java/Android.bp", 1270,
        "38cfd994929ae5ad354f0e0ab9d7bf3c954ebad4f49cd985f34920e44c8cfdb8"),
    ("tools/asuite/atest/logstorage/httplib2/Android.bp", 1472,
        "6736f0ddd353a82abf7623001a921255145815044b943125fd61ebca1a760575"),
    ("tools/test/mobly_extensions/Android.bp", 1865,
        "c11e7f8cdb31646042b5ebb8e325ad74de87eabb86a6eb0014e4f84713a4f3bc"),
    ("tools/test/mobly_extensions/mobly_sponge_converter/Android.bp", 1551,
        "f013df6b3e00c0ff5dddf96548018f42caef08f65c452dd360ad6466fc58e69e"),
    ("tools/test/mobly_extensions/resultdb_uploader/Android.bp", 1161,
        "edffabaa4dc8ee0ca58e17fb6a90a0c09526bb77d0f42aaa1dc84f0f25ee646f"),
];

fn validate_audio_test_tools_original_providers(source: &Path, mode: SoongDependencyMode) -> Result<()> {
    if mode != SoongDependencyMode::AudioApexTargetClosure { return Ok(()); }
    for (relative, bytes, expected) in AUDIO_TEST_TOOLS_ORIGINAL_PROVIDERS {
        let path = source.join(relative);
        let metadata = fs::symlink_metadata(&path)?;
        if !metadata.file_type().is_file() || metadata.len() != *bytes || hash(&path)? != *expected {
            return fail(format!("audio test tools require their complete original provider: {relative}"));
        }
    }
    Ok(())
}

// Original Python providers required by retained lint and framework font consumers.
const AUDIO_LINT_FONTTOOLS_ORIGINAL_PROVIDERS: &[(&str, u64, &str)] = &[
    ("tools/lint_checks/fix/Android.bp", 929,
        "a8279c01827b6235a82b1eacc72f4b4200b262a975cd7b17c868ae2836a0e549"),
    ("external/fonttools/Android.bp", 2329,
        "681d39f7b34162823973ff1ac3d38007e1dd9404e0d19451c4d8b7e4fca7f116"),
    ("external/fonttools/Lib/fontTools/Android.bp", 1446,
        "6cf8554fe39a60a3be025fdfaff7762944a6c05ebfd4a79c84b49c9649a6c7c4"),
];

fn validate_audio_lint_fonttools_original_providers(source: &Path, mode: SoongDependencyMode) -> Result<()> {
    if mode != SoongDependencyMode::AudioApexTargetClosure {
        return Ok(());
    }
    for (relative, bytes, expected) in AUDIO_LINT_FONTTOOLS_ORIGINAL_PROVIDERS {
        let path = source.join(relative);
        let metadata = fs::symlink_metadata(&path)?;
        if !metadata.file_type().is_file() || metadata.len() != *bytes || hash(&path)? != *expected {
            return fail(format!("audio lint/font tools require their complete original provider: {relative}"));
        }
    }
    Ok(())
}

// Original Rust providers required by retained libzygote_messages consumers.
const AUDIO_ZYGOTE_ORIGINAL_PROVIDERS: &[(&str, u64, &str)] = &[
    ("system/zygote/zygote-proc-macros/Android.bp", 1031,
        "2aeb034aeb2a268ce6712eb06dfc6c4f597c26a2d7c3df97c3a8f6419cc42194"),
    ("system/zygote/zygote-sys/Android.bp", 1360,
        "a5ea31a5be9e34b80eb0cecd8575b165a3b10d3bf3b546d5311b70902afae6bd"),
];

fn validate_audio_zygote_original_providers(source: &Path, mode: SoongDependencyMode) -> Result<()> {
    if mode != SoongDependencyMode::AudioApexTargetClosure {
        return Ok(());
    }
    for (relative, bytes, expected) in AUDIO_ZYGOTE_ORIGINAL_PROVIDERS {
        let path = source.join(relative);
        let metadata = fs::symlink_metadata(&path)?;
        if !metadata.file_type().is_file() || metadata.len() != *bytes || hash(&path)? != *expected {
            return fail(format!("audio zygote requires its complete original provider: {relative}"));
        }
    }
    Ok(())
}

// Released Java SDK inputs used by the retained Audio discovery graph.
// Keep the original consumer API levels and the pinned SDK revision. A jar,
// public framework AIDL, and (API 30+) system module jar form one SDK input.
const AUDIO_RELEASED_SDK_INPUTS: &[&str] = &[
    "4/public/android.jar",
    "4/public/framework.aidl",
    "7/public/android.jar",
    "7/public/framework.aidl",
    "8/public/android.jar",
    "8/public/framework.aidl",
    "9/public/android.jar",
    "9/public/framework.aidl",
    "15/public/android.jar",
    "15/public/framework.aidl",
    "16/public/android.jar",
    "16/public/framework.aidl",
    "18/public/android.jar",
    "18/public/framework.aidl",
    "19/public/android.jar",
    "19/public/framework.aidl",
    "21/public/android.jar",
    "21/public/framework.aidl",
    "22/public/android.jar",
    "22/public/framework.aidl",
    "23/public/android.jar",
    "23/public/framework.aidl",
    "24/public/android.jar",
    "24/public/framework.aidl",
    "25/public/android.jar",
    "25/public/framework.aidl",
    "26/public/android.jar",
    "26/public/framework.aidl",
    "27/public/android.jar",
    "27/public/framework.aidl",
    "28/public/android.jar",
    "28/public/framework.aidl",
    "29/public/android.jar",
    "29/public/framework.aidl",
    "30/public/android.jar",
    "30/public/framework.aidl",
    "30/public/core-for-system-modules.jar",
    "31/public/android.jar",
    "31/public/framework.aidl",
    "31/public/core-for-system-modules.jar",
    "33/public/android.jar",
    "33/public/framework.aidl",
    "33/public/core-for-system-modules.jar",
    "34/public/android.jar",
    "34/public/framework.aidl",
    "34/public/core-for-system-modules.jar",
    "35/public/android.jar",
    "35/public/framework.aidl",
    "35/public/core-for-system-modules.jar",
    "37.0/public/android.jar",
    "37.0/public/framework.aidl",
    "37.0/public/core-for-system-modules.jar",
    "29/system/android.jar",
    "31/system/android.jar",
    "35/system/android.jar",
    "36/public/android.jar",
    "36/public/framework.aidl",
    "36/public/core-for-system-modules.jar",
    "33/module-lib/README.md",
    "33/module-lib/android-non-updatable.jar",
    "33/module-lib/android-plus-updatable.jar",
    "33/module-lib/android.jar",
    "33/module-lib/android.net.ipsec.ike.jar",
    "33/module-lib/api/android-non-updatable-incompatibilities.txt",
    "33/module-lib/api/android-non-updatable-removed.txt",
    "33/module-lib/api/android-non-updatable.txt",
    "33/module-lib/api/android-removed.txt",
    "33/module-lib/api/android.net.ipsec.ike-removed.txt",
    "33/module-lib/api/android.net.ipsec.ike.txt",
    "33/module-lib/api/android.txt",
    "33/module-lib/api/art-removed.txt",
    "33/module-lib/api/art.txt",
    "33/module-lib/api/conscrypt-removed.txt",
    "33/module-lib/api/conscrypt.txt",
    "33/module-lib/api/framework-adservices-removed.txt",
    "33/module-lib/api/framework-adservices.txt",
    "33/module-lib/api/framework-appsearch-removed.txt",
    "33/module-lib/api/framework-appsearch.txt",
    "33/module-lib/api/framework-bluetooth-removed.txt",
    "33/module-lib/api/framework-bluetooth.txt",
    "33/module-lib/api/framework-configinfrastructure-removed.txt",
    "33/module-lib/api/framework-configinfrastructure.txt",
    "33/module-lib/api/framework-connectivity-removed.txt",
    "33/module-lib/api/framework-connectivity-t-removed.txt",
    "33/module-lib/api/framework-connectivity-t.txt",
    "33/module-lib/api/framework-connectivity.txt",
    "33/module-lib/api/framework-federatedcompute-removed.txt",
    "33/module-lib/api/framework-federatedcompute.txt",
    "33/module-lib/api/framework-graphics-removed.txt",
    "33/module-lib/api/framework-graphics.txt",
    "33/module-lib/api/framework-healthfitness-removed.txt",
    "33/module-lib/api/framework-healthfitness.txt",
    "33/module-lib/api/framework-media-removed.txt",
    "33/module-lib/api/framework-media.txt",
    "33/module-lib/api/framework-mediaprovider-removed.txt",
    "33/module-lib/api/framework-mediaprovider.txt",
    "33/module-lib/api/framework-ondevicepersonalization-removed.txt",
    "33/module-lib/api/framework-ondevicepersonalization.txt",
    "33/module-lib/api/framework-pdf-removed.txt",
    "33/module-lib/api/framework-pdf-v-removed.txt",
    "33/module-lib/api/framework-pdf-v.txt",
    "33/module-lib/api/framework-pdf.txt",
    "33/module-lib/api/framework-permission-removed.txt",
    "33/module-lib/api/framework-permission-s-removed.txt",
    "33/module-lib/api/framework-permission-s.txt",
    "33/module-lib/api/framework-permission.txt",
    "33/module-lib/api/framework-scheduling-removed.txt",
    "33/module-lib/api/framework-scheduling.txt",
    "33/module-lib/api/framework-sdkextensions-removed.txt",
    "33/module-lib/api/framework-sdkextensions.txt",
    "33/module-lib/api/framework-sdksandbox-removed.txt",
    "33/module-lib/api/framework-sdksandbox.txt",
    "33/module-lib/api/framework-statsd-removed.txt",
    "33/module-lib/api/framework-statsd.txt",
    "33/module-lib/api/framework-supplementalapi-removed.txt",
    "33/module-lib/api/framework-supplementalapi.txt",
    "33/module-lib/api/framework-tethering-removed.txt",
    "33/module-lib/api/framework-tethering.txt",
    "33/module-lib/api/framework-uwb-removed.txt",
    "33/module-lib/api/framework-uwb.txt",
    "33/module-lib/api/framework-virtualization-removed.txt",
    "33/module-lib/api/framework-virtualization.txt",
    "33/module-lib/api/framework-wifi-removed.txt",
    "33/module-lib/api/framework-wifi.txt",
    "33/module-lib/api/runtime-i18n-removed.txt",
    "33/module-lib/api/runtime-i18n.txt",
    "33/module-lib/api/service-configinfrastructure-removed.txt",
    "33/module-lib/api/service-configinfrastructure.txt",
    "33/module-lib/art.jar",
    "33/module-lib/conscrypt.jar",
    "33/module-lib/core-for-system-modules.jar",
    "33/module-lib/framework-adservices.jar",
    "33/module-lib/framework-appsearch.jar",
    "33/module-lib/framework-bluetooth.jar",
    "33/module-lib/framework-connectivity-t.jar",
    "33/module-lib/framework-connectivity.jar",
    "33/module-lib/framework-graphics.jar",
    "33/module-lib/framework-media.jar",
    "33/module-lib/framework-mediaprovider.jar",
    "33/module-lib/framework-ondevicepersonalization.jar",
    "33/module-lib/framework-permission-s.jar",
    "33/module-lib/framework-permission.jar",
    "33/module-lib/framework-scheduling.jar",
    "33/module-lib/framework-sdkextensions.jar",
    "33/module-lib/framework-sdksandbox.jar",
    "33/module-lib/framework-statsd.jar",
    "33/module-lib/framework-supplementalapi.jar",
    "33/module-lib/framework-tethering.jar",
    "33/module-lib/framework-uwb.jar",
    "33/module-lib/framework-wifi.jar",
    "33/module-lib/runtime-i18n.jar",
];

fn validate_audio_provider_source_paths(
    lock: &droidloom_source::SparseSourceLock, mode: SoongDependencyMode,
) -> Result<()> {
    if mode != SoongDependencyMode::AudioApexTargetClosure {
        return Ok(());
    }
    let sdk = lock.projects.iter().find(|project| project.path == Path::new("prebuilts/sdk"))
        .ok_or("audio consumers require the original released SDK provider")?;
    if sdk.name != "platform/prebuilts/sdk"
        || sdk.commit != "0f07e8d60ab0aba46129e427101f96ba459a95c1"
    {
        return fail("audio released SDK provider must retain its pinned upstream revision");
    }
    for required in AUDIO_RELEASED_SDK_INPUTS {
        if !sdk.sparse_paths.is_empty()
            && !sdk.sparse_paths.iter().any(|cone| Path::new(required).starts_with(cone))
        {
            return fail(format!("audio released SDK input is not selected: prebuilts/sdk/{required}"));
        }
    }
    for (relative, commit, required) in [
        ("development", "4dafd114fab3c3d9543a5aff0ad097f479915176", "tools/etc1tool"),
        ("development", "4dafd114fab3c3d9543a5aff0ad097f479915176", "tools/emulator/skins"),
        ("development", "4dafd114fab3c3d9543a5aff0ad097f479915176", "tools/templates"),
        ("dalvik", "5013071e756f89aa2cea97b437af12aacb8d4485", "tools/hprof-conv"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "partition_tools"),
        ("external/f2fs-tools", "c64468cb6397fb63bded0f549438b472f7e7cf88", "fsck"),
        ("external/f2fs-tools", "c64468cb6397fb63bded0f549438b472f7e7cf88", "include"),
        ("external/f2fs-tools", "c64468cb6397fb63bded0f549438b472f7e7cf88", "lib"),
        ("external/f2fs-tools", "c64468cb6397fb63bded0f549438b472f7e7cf88", "mkfs"),
        ("external/f2fs-tools", "c64468cb6397fb63bded0f549438b472f7e7cf88", "tools"),
        ("external/e2fsprogs", "3eb17241db7cd4408cc1bce9d25b602465ace8ff", "contrib/android"),
        ("external/python/watchdog", "0b66557116f53002852d98db711d5488e838c966", "src"),
        ("external/openscreen", "3f982cf4871df8771c9d4abe6e9a6f8d829b2736", "discovery"),
        ("external/openscreen", "3f982cf4871df8771c9d4abe6e9a6f8d829b2736", "platform"),
        ("external/openscreen", "3f982cf4871df8771c9d4abe6e9a6f8d829b2736", "third_party/abseil"),
        ("external/openscreen", "3f982cf4871df8771c9d4abe6e9a6f8d829b2736", "util"),
        ("external/libusb", "70460fc2b43c3948f9caae1fd4eacd2d666a872b", "android/config.h"),
        ("external/libusb", "70460fc2b43c3948f9caae1fd4eacd2d666a872b", "darwin"),
        ("external/libusb", "70460fc2b43c3948f9caae1fd4eacd2d666a872b", "include"),
        ("external/libusb", "70460fc2b43c3948f9caae1fd4eacd2d666a872b", "libusb"),
        ("external/libusb", "70460fc2b43c3948f9caae1fd4eacd2d666a872b", "linux"),
        ("external/libusb", "70460fc2b43c3948f9caae1fd4eacd2d666a872b", "windows"),
        ("external/webrtc", "1895dc1134c158561e0ef668734d86d6bb20d993", "api"),
        ("external/webrtc", "1895dc1134c158561e0ef668734d86d6bb20d993", "audio"),
        ("external/webrtc", "1895dc1134c158561e0ef668734d86d6bb20d993", "call"),
        ("external/webrtc", "1895dc1134c158561e0ef668734d86d6bb20d993", "common_audio"),
        ("external/webrtc", "1895dc1134c158561e0ef668734d86d6bb20d993", "common_video"),
        ("external/webrtc", "1895dc1134c158561e0ef668734d86d6bb20d993", "logging"),
        ("external/webrtc", "1895dc1134c158561e0ef668734d86d6bb20d993", "media"),
        ("external/webrtc", "1895dc1134c158561e0ef668734d86d6bb20d993", "modules"),
        ("external/webrtc", "1895dc1134c158561e0ef668734d86d6bb20d993", "net"),
        ("external/webrtc", "1895dc1134c158561e0ef668734d86d6bb20d993", "p2p"),
        ("external/webrtc", "1895dc1134c158561e0ef668734d86d6bb20d993", "pc"),
        ("external/webrtc", "1895dc1134c158561e0ef668734d86d6bb20d993", "rtc_base"),
        ("external/webrtc", "1895dc1134c158561e0ef668734d86d6bb20d993", "stats"),
        ("external/webrtc", "1895dc1134c158561e0ef668734d86d6bb20d993", "system_wrappers"),
        ("external/webrtc", "1895dc1134c158561e0ef668734d86d6bb20d993", "test"),
        ("external/webrtc", "1895dc1134c158561e0ef668734d86d6bb20d993", "third_party"),
        ("external/webrtc", "1895dc1134c158561e0ef668734d86d6bb20d993", "video"),
        ("external/webrtc", "1895dc1134c158561e0ef668734d86d6bb20d993", "webrtc"),
        ("external/webrtc", "1895dc1134c158561e0ef668734d86d6bb20d993", "sdk"),
        ("external/pffft", "9bc003aef1c0c120735aeeb1098ef830c265c98c", "simd"),
        ("external/rnnoise", "1295d6828459cc82c3c29cc5d7d297215250a74b", "include"),
        ("external/rnnoise", "1295d6828459cc82c3c29cc5d7d297215250a74b", "src"),
        ("external/libsrtp2", "f50e3237d9f6d20e95293ffce692aaa60b7c81be", "crypto"),
        ("external/libsrtp2", "f50e3237d9f6d20e95293ffce692aaa60b7c81be", "exported_include"),
        ("external/libsrtp2", "f50e3237d9f6d20e95293ffce692aaa60b7c81be", "fuzzer"),
        ("external/libsrtp2", "f50e3237d9f6d20e95293ffce692aaa60b7c81be", "include"),
        ("external/libsrtp2", "f50e3237d9f6d20e95293ffce692aaa60b7c81be", "srtp"),
        ("tools/security", "e4e7ba1dabe64f33b9894624e43763bd8a3cbca5", "fuzzing/libFuzzer_mte_crash_handler"),
        ("external/libevent", "44754c0dfee5dc81723013498398034176e6d81e", "compat"),
        ("external/libevent", "44754c0dfee5dc81723013498398034176e6d81e", "include"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "client"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "fdevent"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "sysdeps"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "daemon"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "fastdeploy"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "test_utils"),
        ("test/vts-testcase/hal", "61df1bdbc6b596dafeee213c04f5d2c8d7131b98", "treble/vintf"),
        ("external/pigweed", "db5cb0db8513b2598ae7c1fa8a6441ff7f8808b5", "pw_async2"),
        ("external/pigweed", "db5cb0db8513b2598ae7c1fa8a6441ff7f8808b5", "pw_bluetooth"),
        ("external/pigweed", "db5cb0db8513b2598ae7c1fa8a6441ff7f8808b5", "pw_bluetooth_proxy"),
        ("external/pigweed", "db5cb0db8513b2598ae7c1fa8a6441ff7f8808b5", "pw_checksum"),
        ("external/pigweed", "db5cb0db8513b2598ae7c1fa8a6441ff7f8808b5", "pw_intrusive_ptr"),
        ("external/pigweed", "db5cb0db8513b2598ae7c1fa8a6441ff7f8808b5", "pw_multibuf"),
        ("external/pigweed", "db5cb0db8513b2598ae7c1fa8a6441ff7f8808b5", "third_party/emboss"),
        ("external/emboss", "e06f586857f7f7a814a4621deba91a9f586d930c", "compiler"),
        ("external/emboss", "e06f586857f7f7a814a4621deba91a9f586d930c", "runtime"),
        ("frameworks/compile/libbcc", "943016fade3dbbb725c363d0dc60a6e962bd88e5", "tools/bcc_compat"),
        ("dalvik", "5013071e756f89aa2cea97b437af12aacb8d4485", "tools/dexdeps"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest"),
        ("external/python/absl-py", "0bd198a006d34d3d0a49eebd6c9edbfc0476c973", "absl"),
        ("external/scapy", "825c73720a094ed76d5416e44bd387f6f4dd67fd", "scapy"),
        ("external/python/google-api-python-client", "9bb5d18c9e8dcc25f8be6359e2dcffba23851acb", "apiclient"),
        ("external/python/google-api-python-client", "9bb5d18c9e8dcc25f8be6359e2dcffba23851acb", "googleapiclient"),
        ("external/python/oauth2client", "7055ce09e3ed196a6da5365a86317046473a3374", "oauth2client"),
        ("external/python/httplib2", "d9d5963848fc2f3e6abf5c115166ebecdcd69484", "python3"),
        ("tools/test/mobly_extensions", "fc6621351d8d17286870813678c96bf81555c1ad", "coverage"),
        ("tools/test/mobly_extensions", "fc6621351d8d17286870813678c96bf81555c1ad", "mobly_sponge_converter"),
        ("tools/test/mobly_extensions", "fc6621351d8d17286870813678c96bf81555c1ad", "resultdb_uploader"),
        ("tools/test/mobly_extensions", "fc6621351d8d17286870813678c96bf81555c1ad", "tools"),
        ("external/python/uritemplates", "3936369be2a971ef0b37742e8f9cf93cd10bcc41", "uritemplate"),
        ("external/python/python-api-core", "57ebd58f04b400e908b44ff532db2c2cfc366e3a", "google"),
        ("external/python/google-auth-library-python", "46e96844758592ebba0935bbc7757a4d460b9920", "google"),
        ("external/python/cachetools", "e7fc0ce906fa64166504aba2bd2b5ef96087f96d", "src"),
        ("external/python/rsa", "b7be4df622ff5b8902da876cc39a379e569406ef", "rsa"),
        ("external/python/pyasn1", "0071cbf57b52336b8261f3903612a2d4d81669af", "pyasn1"),
        ("external/python/pyasn1-modules", "98f5febb5f61c53f8d3831eafdbe0ec23cb97e32", "pyasn1_modules"),
        ("tools/lint_checks", "d260e8254709bb2884c072dd595f63c9c8d22527", "fix"),
        ("external/fonttools", "97cf2c42d30e48e1e6f7432079544dcd8b0af23c", "Lib"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "33/module-lib"),
        ("system/zygote", "c24023080df0bdb5988c1e0c641d494574a97c40", "zygote-proc-macros"),
        ("system/zygote", "c24023080df0bdb5988c1e0c641d494574a97c40", "zygote-sys"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "36/public/api/service-ondeviceintelligence.txt"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "36/public/api/service-ondeviceintelligence-removed.txt"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "36/system-server/api/service-ondeviceintelligence.txt"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "36/system-server/api/service-ondeviceintelligence-removed.txt"),
        ("tools/test/desktop/mobly", "b77d8987bdd1d44645a015042130c8b7cba05b4b", "lib/pasit"),
        ("tools/test/desktop/mobly", "b77d8987bdd1d44645a015042130c8b7cba05b4b", "lib/utils"),
        ("tools/test/desktop/mobly", "b77d8987bdd1d44645a015042130c8b7cba05b4b", "tests/pasit/Android.bp"),
        ("external/grpc-grpc", "a7112f326a9df61597d1bfdbdad7ad9ef3f764b7", "etc"),
        ("external/grpc-grpc", "a7112f326a9df61597d1bfdbdad7ad9ef3f764b7", "examples"),
        ("external/grpc-grpc", "a7112f326a9df61597d1bfdbdad7ad9ef3f764b7", "include"),
        ("external/grpc-grpc", "a7112f326a9df61597d1bfdbdad7ad9ef3f764b7", "src"),
        ("external/grpc-grpc", "a7112f326a9df61597d1bfdbdad7ad9ef3f764b7", "third_party"),
        ("external/grpc-grpc", "a7112f326a9df61597d1bfdbdad7ad9ef3f764b7", "tools"),
        ("external/grpc-grpc", "a7112f326a9df61597d1bfdbdad7ad9ef3f764b7", "test/core/address_utils"),
        ("external/grpc-grpc", "a7112f326a9df61597d1bfdbdad7ad9ef3f764b7", "test/core/event_engine"),
        ("external/grpc-grpc", "a7112f326a9df61597d1bfdbdad7ad9ef3f764b7", "test/core/test_util"),
        ("external/grpc-grpc", "a7112f326a9df61597d1bfdbdad7ad9ef3f764b7", "test/cpp/common"),
        ("external/grpc-grpc", "a7112f326a9df61597d1bfdbdad7ad9ef3f764b7", "test/cpp/util"),
        ("external/chromiumos-config", "0f9ee62b2480d7ffa81c1584407813e7a6d930ca", "proto"),
        ("external/chromiumos-config", "0f9ee62b2480d7ffa81c1584407813e7a6d930ca", "python"),
        ("external/python/snippet-uiautomator", "5dbbc2e9f543b88b6353b6d66f23dcb071f565a7", "snippet_uiautomator"),
        ("external/mobly-snippet-lib", "fcbe611cef61ea47d55107c6d70ac1b4706a6217", "third_party/sl4a"),
        ("packages/modules/RemoteKeyProvisioning", "d88e2305f9186661fe75ee2f00c8b250a76fdabe", "apex"),
        ("external/gemmlowp", "9304d9b673e827202f9526913d161e3cb49a1560", "eight_bit_int_gemm"),
        ("external/gemmlowp", "9304d9b673e827202f9526913d161e3cb49a1560", "fixedpoint"),
        ("external/gemmlowp", "9304d9b673e827202f9526913d161e3cb49a1560", "internal"),
        ("external/gemmlowp", "9304d9b673e827202f9526913d161e3cb49a1560", "meta"),
        ("external/gemmlowp", "9304d9b673e827202f9526913d161e3cb49a1560", "profiling"),
        ("external/gemmlowp", "9304d9b673e827202f9526913d161e3cb49a1560", "public"),
        ("external/gemmlowp", "9304d9b673e827202f9526913d161e3cb49a1560", "test"),
        ("external/llvm", "429d6c6097aea3326e49fc8e87cc7658b750c5d7", "soong"),
        ("external/clang", "bdc4d062dc4550869e0825da19fe8fa720db860a", "soong"),
        ("system/update_engine", "4591637f51644f5429f9e2fe589ab22b92f61842", "flags"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/nativetesthelper/jni"),
        ("frameworks/base", "94b4c163b7dfe5ce3607f7bb8456f9573f7de57d", "core/tests"),
        ("frameworks/base", "94b4c163b7dfe5ce3607f7bb8456f9573f7de57d", "services/tests"),
        ("external/deqp", "eae519aaa6980b2a34ec07141bb19de3f6ddf69e", "android/cts/main"),
        ("external/deqp", "eae519aaa6980b2a34ec07141bb19de3f6ddf69e", "android/openglcts/AndroidManifest.xml"),
        ("external/deqp", "eae519aaa6980b2a34ec07141bb19de3f6ddf69e", "android/openglcts/src"),
        ("external/deqp", "eae519aaa6980b2a34ec07141bb19de3f6ddf69e", "android/package"),
        ("external/deqp", "eae519aaa6980b2a34ec07141bb19de3f6ddf69e", "data"),
        ("external/deqp", "eae519aaa6980b2a34ec07141bb19de3f6ddf69e", "execserver"),
        ("external/deqp", "eae519aaa6980b2a34ec07141bb19de3f6ddf69e", "executor"),
        ("external/deqp", "eae519aaa6980b2a34ec07141bb19de3f6ddf69e", "external"),
        ("external/deqp", "eae519aaa6980b2a34ec07141bb19de3f6ddf69e", "framework"),
        ("external/deqp", "eae519aaa6980b2a34ec07141bb19de3f6ddf69e", "modules"),
        ("external/deqp", "eae519aaa6980b2a34ec07141bb19de3f6ddf69e", "android/cts/runner"),
        ("external/deqp", "eae519aaa6980b2a34ec07141bb19de3f6ddf69e", "android/cts/angle"),
        ("external/deqp-deps/SPIRV-Headers", "d425c460bde47239483e36ccbec5674cf39eb431", "include"),
        ("external/deqp-deps/SPIRV-Tools", "4e0aa7940f17b47e67f7be80442d526b4fc54142", "include"),
        ("external/deqp-deps/SPIRV-Tools", "4e0aa7940f17b47e67f7be80442d526b4fc54142", "source"),
        ("external/deqp-deps/SPIRV-Tools", "4e0aa7940f17b47e67f7be80442d526b4fc54142", "test"),
        ("external/deqp-deps/SPIRV-Tools", "4e0aa7940f17b47e67f7be80442d526b4fc54142", "tools"),
        ("external/deqp-deps/SPIRV-Tools", "4e0aa7940f17b47e67f7be80442d526b4fc54142", "utils"),
        ("external/deqp-deps/amber", "e2217d1616b410dc65f72d0cdd0b73f0b72a860d", "android_sample"),
        ("external/deqp-deps/amber", "e2217d1616b410dc65f72d0cdd0b73f0b72a860d", "include"),
        ("external/deqp-deps/amber", "e2217d1616b410dc65f72d0cdd0b73f0b72a860d", "samples/config_helper.h"),
        ("external/deqp-deps/amber", "e2217d1616b410dc65f72d0cdd0b73f0b72a860d", "samples/config_helper_dawn.h"),
        ("external/deqp-deps/amber", "e2217d1616b410dc65f72d0cdd0b73f0b72a860d", "samples/config_helper_vulkan.h"),
        ("external/deqp-deps/amber", "e2217d1616b410dc65f72d0cdd0b73f0b72a860d", "samples/log.h"),
        ("external/deqp-deps/amber", "e2217d1616b410dc65f72d0cdd0b73f0b72a860d", "samples/png.h"),
        ("external/deqp-deps/amber", "e2217d1616b410dc65f72d0cdd0b73f0b72a860d", "samples/ppm.h"),
        ("external/deqp-deps/amber", "e2217d1616b410dc65f72d0cdd0b73f0b72a860d", "samples/timestamp.h"),
        ("external/deqp-deps/amber", "e2217d1616b410dc65f72d0cdd0b73f0b72a860d", "src"),
        ("external/deqp-deps/amber", "e2217d1616b410dc65f72d0cdd0b73f0b72a860d", "tools"),
        ("external/deqp-deps/glslang", "14422bdc57fb93221192a0c542dde144980dfb69", "SPIRV"),
        ("external/deqp-deps/glslang", "14422bdc57fb93221192a0c542dde144980dfb69", "StandAlone"),
        ("external/deqp-deps/glslang", "14422bdc57fb93221192a0c542dde144980dfb69", "Test"),
        ("external/deqp-deps/glslang", "14422bdc57fb93221192a0c542dde144980dfb69", "glslang"),
        ("external/deqp-deps/glslang", "14422bdc57fb93221192a0c542dde144980dfb69", "gtests"),
        ("external/easymock", "06a9728c3609f856e87db38a6602196cec3ab727", "src"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "9/public"),
        ("prebuilts/clang/host/linux-x86", "29182889399818f97baa65ea238c80e8117981eb", "clang-r584948b"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "35/public/android.jar"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "35/public/framework.aidl"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "35/public/core-for-system-modules.jar"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "libs/shim"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "libs/install"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/stagedinstall"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/PrivilegedUpdateApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tools/cts-tradefed"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "libs/runner"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/core/runner-axt"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "libs/vogar-expect"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/compilation"),
        ("external/jimfs", "cd18acbf0036a7c6a3443e7e58b5091cacf327cf", "jimfs"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appcompat/host/lib"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/certs"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/res"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/AppAccessData"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/AppDataIsolationTestApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/AppWithData"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/DeclarePermissionsWithSpacesApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/DeviceIdentifiers"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/DuplicatePermissionDeclareApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/DuplicatePermissionSameGroup"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/InstrumentationAppDiffCert"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/KeyRotationTest"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/KeyStoreManagerTest"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/ListeningPortsApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/MalformedDuplicatePermission"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/PackageInstallerPermissionRequestApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/PackageInstallerWhitelistApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/PermissionDeclareApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/PermissionDeclareAppCompat"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/ReadSettingsFieldsApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/RoleSecurityTestApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/SimpleAppInstall"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/SimpleAppInstallDiffCert"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/StatsdSecurityApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/TargetInstrumentationApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/UsePermissionDiffCert"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/UseProcessFailActivity"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/V32HybridSigningScheme"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/V3SigningSchemeRotation"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/keysets/malBadKey"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/keysets/malNoDef"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/keysets/malOneDef"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/keysets/permDef"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/keysets/permUse"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/keysets/testApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/keysets/uA"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/keysets/uAuB"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/keysets/uB"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/keysets/uBsharedUser"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/keysets/uEcA"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/keysets/uNone"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/tinyapp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/statsdatom/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/statsdatom/apps/adpfapp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/statsdatom/apps/expressloghelperapp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/statsdatom/apps/statsdapp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/statsdatom/configs/AndroidTestTelecom.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/statsdatom/express/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/statsdatom/lib/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/statsdatom/statsd/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/statsdatom/telecom/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/utils"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/telecom"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/telecom-apps/ConnectionServiceVoipAppClone"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/telecom-apps/ConnectionServiceVoipAppMain"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/telecom-apps/ManagedConnectionService"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/telecom-apps/ManagedConnectionServiceClone"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/telecom-apps/TransactionalVoipAppClone"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/telecom-apps/TransactionalVoipAppMain"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/telecom-apps/Utils"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/telecom-cuj"),
        ("external/bouncycastle", "c404048739e9a35cd51ad82906aadf910cca09dd", "bcpkix/src/main/java"),
        ("external/bouncycastle", "c404048739e9a35cd51ad82906aadf910cca09dd", "bcprov/src/main/java"),
        ("external/bouncycastle", "c404048739e9a35cd51ad82906aadf910cca09dd", "repackaged_platform/bcpkix/src/main/java"),
        ("external/bouncycastle", "c404048739e9a35cd51ad82906aadf910cca09dd", "repackaged_platform/bcprov/src/main/java"),
        ("external/caliper", "d7bb09dccd464969498584337b0e68a9347b4d40", "caliper"),
        ("external/caliper", "d7bb09dccd464969498584337b0e68a9347b4d40", "examples"),
        ("external/caliper", "d7bb09dccd464969498584337b0e68a9347b4d40", "lib"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/comparedf2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/mulodi4.c"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/BidirectionalStream.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/BidirectionalStreamBuilderWrapper.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/BidirectionalStreamCallbackWrapper.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/BidirectionalStreamWrapper.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/CallbackException.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/CallbackExceptionWrapper.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/ConnectionMigrationOptions.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/CronetEngineWrapper.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/CronetExceptionTranslationUtils.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/CronetExceptionWrapper.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/DnsOptions.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/HeaderBlock.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/HeaderBlockImpl.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/HeaderBlockWrapper.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/HttpEngine.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/HttpEngineJavaClasses.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/HttpException.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/InlineExecutionProhibitedException.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/NetworkException.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/NetworkExceptionWrapper.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/Proxy.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/ProxyOptions.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/QuicException.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/QuicExceptionWrapper.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/QuicOptions.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/UploadDataProvider.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/UploadDataProviderWrapper.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/UploadDataSink.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/UploadDataSinkWrapper.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/UrlRequest.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/UrlRequestBuilderWrapper.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/UrlRequestCallbackWrapper.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/UrlRequestStatusListenerWrapper.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/UrlRequestWrapper.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/UrlResponseInfo.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src/android/net/http/UrlResponseInfoWrapper.java"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/build/Android.bp"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/build/util/LASTCHANGE"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/build/util/android_chrome_version.py"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/build/util/version.py"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/chrome/VERSION"),
        ("external/escapevelocity", "03b11f293548ad5fd65b5164b46aca08a96968f5", "src/main"),
        ("external/libbpf", "9723b4de6459ab48b361aed3bae5df3c1bd20cb8", "android/bpf_stub.c"),
        ("external/mime-support", "9d71d482603aac054815958c9834ae1cd036f024", "mime.types"),
        ("external/mime-support", "9d71d482603aac054815958c9834ae1cd036f024", "mime.types-alt"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "java/lite/proguard.pgcfg"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "javanano/src/device/main/java/com/google/protobuf/nano"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "javanano/src/main/java/com/google/protobuf/nano"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "framework/tests/util"),
        ("packages/modules/ConfigInfrastructure", "333bc8067efc529ef4d197fec2f4f2cae1ad2ece", "aconfigd/proto"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "Tethering/apex/hiddenapi"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "staticlibs/device"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "staticlibs/framework"),
        ("packages/modules/NpuManager", "d194f8ada2cab31b8487fb3aaac6fd383fc7e07f", "flags"),
        ("packages/modules/NpuManager", "d194f8ada2cab31b8487fb3aaac6fd383fc7e07f", "framework"),
        ("packages/modules/NpuManager", "d194f8ada2cab31b8487fb3aaac6fd383fc7e07f", "ndk"),
        ("packages/modules/Telephony", "d83f23a96fbe6d68942d8d7245dbd3db91e9c711", "tests/mcts/Android.bp"),
        ("packages/modules/Telephony", "d83f23a96fbe6d68942d8d7245dbd3db91e9c711", "tests/mcts/AndroidTest.xml"),
        ("packages/modules/Telephony", "d83f23a96fbe6d68942d8d7245dbd3db91e9c711", "tests/mcts/telecom-cuj"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "framework/aidl-export"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "framework/java"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/sts-common-util/host-side/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/sts-common-util/host-side/res"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/sts-common-util/host-side/src"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/sts-common-util/util/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/sts-common-util/util/src"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "tools/darwin/bin/aapt2"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "tools/linux/bin/aapt2"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "tools/windows/bin/aapt2.exe"),
        ("system/gsid", "35a92d40f529b605fad8ff622691e76901044cc8", "aidl/android/gsi/AvbPublicKey.aidl"),
        ("system/gsid", "35a92d40f529b605fad8ff622691e76901044cc8", "aidl/android/gsi/GsiProgress.aidl"),
        ("system/gsid", "35a92d40f529b605fad8ff622691e76901044cc8", "aidl/android/gsi/IGsiService.aidl"),
        ("system/gsid", "35a92d40f529b605fad8ff622691e76901044cc8", "aidl/android/gsi/IGsiServiceCallback.aidl"),
        ("system/gsid", "35a92d40f529b605fad8ff622691e76901044cc8", "aidl/android/gsi/IImageService.aidl"),
        ("system/gsid", "35a92d40f529b605fad8ff622691e76901044cc8", "aidl/android/gsi/IProgressCallback.aidl"),
        ("system/gsid", "35a92d40f529b605fad8ff622691e76901044cc8", "aidl/android/gsi/MappedImage.aidl"),
        ("system/liburingutils", "3d6286bdd07ec68ee6a411381e56c1aaa6e11247", "include"),
        ("system/liburingutils", "3d6286bdd07ec68ee6a411381e56c1aaa6e11247", "src"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/Android.bp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/CommandListener.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/CompressionEngine.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogAudit.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogBufferElement.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogBufferTest.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogKlog.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogListener.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogPermissions.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogReader.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogReaderList.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogReaderThread.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogSize.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogStatistics.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogTags.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogdLock.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogdNativeService.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/PkgIds.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/PruneList.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/ReplayMessages.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/SerializedFlushToState.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/SerializedFlushToStateTest.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/SerializedLogBuffer.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/SerializedLogBufferTest.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/SerializedLogChunk.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/SerializedLogChunkTest.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/SimpleLogBuffer.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/TrustyLog.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/auditctl.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/binder"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/device_test_config.xml"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/flags"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/libaudit"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/logd_test.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/logtagd.rc"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/main.cpp"),
        ("system/update_engine", "4591637f51644f5429f9e2fe589ab22b92f61842", "binder_bindings/android/os/IUpdateEngine.aidl"),
        ("system/update_engine", "4591637f51644f5429f9e2fe589ab22b92f61842", "binder_bindings/android/os/IUpdateEngineCallback.aidl"),
        ("system/update_engine", "4591637f51644f5429f9e2fe589ab22b92f61842", "stable"),
        ("system/vold", "6d20a0078c2bcaa2499dc5d032f337bfe1182d9e", "binder/android/os/IVold.aidl"),
        ("system/vold", "6d20a0078c2bcaa2499dc5d032f337bfe1182d9e", "binder/android/os/IVoldListener.aidl"),
        ("system/vold", "6d20a0078c2bcaa2499dc5d032f337bfe1182d9e", "binder/android/os/IVoldMountCallback.aidl"),
        ("system/vold", "6d20a0078c2bcaa2499dc5d032f337bfe1182d9e", "binder/android/os/IVoldTaskListener.aidl"),
        ("external/e2fsprogs", "3eb17241db7cd4408cc1bce9d25b602465ace8ff", "debugfs"),
        ("external/e2fsprogs", "3eb17241db7cd4408cc1bce9d25b602465ace8ff", "lib"),
        ("external/e2fsprogs", "3eb17241db7cd4408cc1bce9d25b602465ace8ff", "misc"),
        ("external/e2fsprogs", "3eb17241db7cd4408cc1bce9d25b602465ace8ff", "e2fsck"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "scripts"),
        ("tools/deviceinfra/prebuilts", "bb2d5f519bd0bf57641d74f40c12bab281423781", "Android.bp"),
        ("tools/deviceinfra/prebuilts", "bb2d5f519bd0bf57641d74f40c12bab281423781", "ats_console_deploy.jar"),
        ("tools/deviceinfra/prebuilts", "bb2d5f519bd0bf57641d74f40c12bab281423781", "ats_olc_server_local_mode_deploy.jar"),
        ("tools/deviceinfra/prebuilts", "bb2d5f519bd0bf57641d74f40c12bab281423781", "ats_olc_server_deploy.jar"),
        ("external/junit-params", "1a5f3f8b0c829e257386c56cfda5e5a442377282", "lib"),
        ("external/junit-params", "1a5f3f8b0c829e257386c56cfda5e5a442377282", "src"),
        ("system/gatekeeper", "5b5e75b5bda9fccbc3132e9624cb25286babdaac", "include"),
        ("system/gatekeeper", "5b5e75b5bda9fccbc3132e9624cb25286babdaac", "rust"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "hals/Android.bp"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "hals/derive"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "hals/wire"),
        ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "cpp/power/client"),
        ("frameworks/hardware/interfaces", "9de6d032a248523c22d0bd86e224d1762355c41e", "automotive/power/aidl"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "aconfig"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "shared"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "tests/tapl"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "tools/buildconfig.sh"),
        ("packages/apps/Settings", "213829fb67f5e070029e0513a088f31bc8f5c1ed", "aconfig"),
        ("packages/services/CrossDeviceSync", "e11258b65bdf0091dfc440c2b2e2c782778688c3", "src/com/android/crossdevicesync/flags"),
    ] {
        let project = lock.projects.iter().find(|project| project.path == Path::new(relative))
            .ok_or_else(|| format!("audio consumer requires the original locked provider project {relative}"))?;
        if project.name != format!("platform/{relative}") || project.commit != commit
            || (!project.sparse_paths.is_empty() && !project.sparse_paths.iter().any(|cone|
                Path::new(required).starts_with(cone)))
        {
            return fail(format!("audio consumer requires the complete original {relative}/{required} cone at its pinned commit"));
        }
    }
    validate_audio_trusty_source_paths(lock, mode)?;
    Ok(())
}

fn audio_keep_required_discovery(
    source: &Path, relative: &str, mode: SoongDependencyMode,
) -> Result<bool> {
    if mode != SoongDependencyMode::AudioApexTargetClosure {
        return Ok(false);
    }
    // Original retained consumers require these real provider trees. Preserve
    // all their original Blueprint siblings and source dependencies. Reject an
    // existing marker rather than deleting or adopting a foreign exclusion.
    let (probe, expected) = match relative {
        "frameworks/base/packages/SettingsLib" => (
            "frameworks/base/packages/SettingsLib/Android.bp",
            "a3190e923698e7e0b3847916b38fd85a23cb82491e4fae622a2e9286f45559fd"),
        "cts/common/device-side/nativetesthelper/jni" => (
            "cts/common/device-side/nativetesthelper/jni/Android.bp",
            "ff53810c94a598d1c1f39617e8d580bbcba9d6ce8a67e8f84bf610079086e327"),
        "frameworks/base/core/tests" => (
            "frameworks/base/core/tests/coretests/Android.bp",
            "0da6ab7feda048ecd9b700d814ba0fcf9f7eecd594fedc13c060db1c3efc9007"),
        "frameworks/base/services/tests" => (
            "frameworks/base/services/tests/servicestests/Android.bp",
            "051e4d6be23025177ff185a189f58d93839cce47986fe409328aec2a322b2dae"),
        "external/rust/android-crates-io/crates/grpcio-sys" => (
            "external/rust/android-crates-io/crates/grpcio-sys/Android.bp",
            "5222a36700372ec7fd1a584a96d1da025d1daafd56d6cacadfff923cfcd90c28"),
        "packages/modules/StatsD/tests" => (
            "packages/modules/StatsD/tests/utils/Android.bp",
            "51fd5290837c4903eb7298e81fb95983842b88cea5daf35b3475604f613acc9d"),
        "packages/modules/Virtualization/tests" => (
            "packages/modules/Virtualization/tests/testapk/Android.bp",
            "4d8b81e1ff5f831ac60ff0a1e372256104086e0a4faee5c108d4229f56bf791d"),
        "packages/modules/Virtualization/guest/pvmfw" => (
            "packages/modules/Virtualization/guest/pvmfw/Android.bp",
            "998e3f4858d3e0adaf6e95c01bef7fe5ff6dcc07c166ec7db1849311f947ae76"),
        "packages/modules/Virtualization/guest/trusty/test_vm" => (
            "packages/modules/Virtualization/guest/trusty/test_vm/vm/Android.bp",
            "35ea190e9dbc2b45c2fb97eaaae207ddf78e6459fe3e717a031a089f557a5d10"),
        _ => return Ok(false),
    };
    if hash(&source.join(probe))? != expected {
        return fail(format!("audio original required discovery provider changed: {probe}"));
    }
    match fs::symlink_metadata(source.join(relative).join(".find-ignore")) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(true),
        Ok(_) => fail(format!("audio required provider is hidden by an existing discovery marker: {relative}")),
        Err(error) => Err(error.into()),
    }
}

fn project_discovery_exclusion(
    p: &mut Projection, source: &Path, relative: &str, mode: SoongDependencyMode,
) -> Result<()> {
    if !audio_keep_required_discovery(source, relative, mode)? {
        p.put(&source.join(relative).join(".find-ignore"), b"")?;
    }
    Ok(())
}

fn native_leaf_java_plugins(original: &str, mode: SoongDependencyMode) -> Result<String> {
    if let Some(complete) = audio_original_graph_provider(
        "prebuilts/sdk/current/androidx/JavaPlugins.bp", original, mode,
    )? {
        return Ok(complete);
    }
    if mode == SoongDependencyMode::AudioApexTargetClosure {
        use sha2::{Digest, Sha256};
        if original.len() != 1315 || format!("{:x}", Sha256::digest(original.as_bytes()))
            != "ecb2b148861c341c50fa9c223117a1d918a8641cebcef7c07e143c3806d77102"
        {
            return fail("audio original AndroidX Java plugin providers changed");
        }
    }
    let mut result = original.to_owned();
    for name in ["androidx.appsearch_appsearch-compiler-plugin",
                 "androidx.room_room-compiler-plugin",
                 "androidx.appfunctions_appfunctions-compiler-plugin"] {
        if mode == SoongDependencyMode::AudioApexTargetClosure
            && name == "androidx.room_room-compiler-plugin"
        {
            // SystemUI-tests directly uses this real processor, including its
            // original room compiler and kotlin-reflect dependencies.
            continue;
        }
        result = private_without_named_java_module(&result, "java_plugin", name)?;
    }
    Ok(result)
}

fn project_blueprints(p: &mut Projection, source: &Path, mode: SoongDependencyMode) -> Result<()> {
    // This existing provider generates exactly these three prebuilt stubs.
    // No system-server provider is declared: retain its original fallback.
    validate_audio_sdk_import_provider(source, mode)?;
    validate_audio_npumanager_sdk_provider(source, mode)?;
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
        let projected = match audio_original_shared_provider(rel, &original, mode)? {
            Some(original) => original,
            None => metadata_only(&original)?,
        };
        p.put(&path, projected)?;
    }
    if mode == SoongDependencyMode::AudioApexTargetClosure {
        for relative in ["packages/apps/Launcher3/tests/Android.bp",
                         "packages/services/CrossDeviceSync/Android.bp",
                         "packages/services/CrossDeviceSync/lib/Android.bp"] {
            let path = source.join(relative);
            let original = fs::read_to_string(&path)?;
            let projected = audio_new_source_root_scope(relative, &original, mode)?
                .ok_or("missing audio unselected source root scope")?;
            p.put(&path, projected)?;
        }
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
            if !project_fallback_sdk_import_for_mode(stem, scope, mode) {
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


// A requested build target is separate from the already qualified source and
// projection scope. This additional purpose never widens AudioApexBuild.
#[derive(Clone, Copy, Debug)]
enum FixedProductionRequest<'a> {
    Existing(SoongDependencyMode, &'a [&'a str]),
    VendorPolicyOnAudioSource,
    VendorPolicyBundleOnAudioSource,
}

impl FixedProductionRequest<'_> {
    fn source_mode(&self) -> SoongDependencyMode {
        match self {
            Self::Existing(mode, _) => *mode,
            Self::VendorPolicyOnAudioSource | Self::VendorPolicyBundleOnAudioSource => SoongDependencyMode::AudioApexTargetClosure,
        }
    }
    fn projection_targets(&self) -> &[&str] {
        match self {
            Self::Existing(_, targets) => targets,
            Self::VendorPolicyOnAudioSource | Self::VendorPolicyBundleOnAudioSource => &["com.android.hardware.audio.droidloom"],
        }
    }
    fn requested_targets(&self) -> &[&str] {
        match self {
            Self::Existing(_, targets) => targets,
            Self::VendorPolicyOnAudioSource => &["vendor_sepolicy.cil"],
            Self::VendorPolicyBundleOnAudioSource => VENDOR_POLICY_BUNDLE_TARGETS,
        }
    }
    fn validate(&self, product: &str) -> Result<()> {
        match self {
            Self::Existing(mode, targets) => validate_soong_dependency_mode(*mode, targets),
            Self::VendorPolicyOnAudioSource | Self::VendorPolicyBundleOnAudioSource if product == "droidloom_x86_64" => Ok(()),
            Self::VendorPolicyOnAudioSource | Self::VendorPolicyBundleOnAudioSource => fail("fixed Audio-source vendor policy requires droidloom_x86_64"),
        }
    }
    fn soong_targets(&self, out: &Path, product: &str) -> Result<Vec<PathBuf>> {
        self.validate(product)?;
        match self {
            Self::Existing(mode, targets) => selected_soong_targets(*mode, targets, out, product),
            Self::VendorPolicyOnAudioSource => Ok(vec![PathBuf::from("vendor_sepolicy.cil")]),
            Self::VendorPolicyBundleOnAudioSource => Ok(VENDOR_POLICY_BUNDLE_TARGETS.iter().map(|target|PathBuf::from(*target)).collect()),
        }
    }
    fn configure_dependencies(&self, command: &mut Command, product: &str) -> Result<()> {
        self.validate(product)?;
        match self {
            Self::Existing(mode, targets) => configure_soong_dependencies(command, *mode, targets),
            Self::VendorPolicyOnAudioSource | Self::VendorPolicyBundleOnAudioSource => {
                enforce_strict_soong_dependencies(command);
                command.env("SELINUX_IGNORE_NEVERALLOWS", "false");
                Ok(())
            }
        }
    }
    fn policy_receipt_names(&self) -> Option<(&'static str, &'static str, &'static str, &'static str)> {
        match self {
            Self::VendorPolicyOnAudioSource => Some(("droidloom-vendor-policy-build-inputs.json", "droidloom-fixed-user-vendor-policy-inputs-v1", "droidloom-vendor-policy-normal-result.json", "droidloom-fixed-user-vendor-policy-normal-result-v1")),
            Self::VendorPolicyBundleOnAudioSource => Some(("droidloom-vendor-policy-bundle-build-inputs.json", "droidloom-fixed-user-vendor-policy-bundle-inputs-v1", "droidloom-vendor-policy-bundle-normal-result.json", "droidloom-fixed-user-vendor-policy-bundle-normal-result-v1")),
            Self::Existing(_, _) => None,
        }
    }
    fn description(&self, product: &str) -> Result<serde_json::Value> {
        self.validate(product)?;
        Ok(serde_json::json!({
            "requested_targets": self.requested_targets(),
            "projection_scope_targets": self.projection_targets(),
            "source_profile": match self {
                Self::VendorPolicyOnAudioSource => "exact-audio537-original-libexif-source-policy-target",
                Self::VendorPolicyBundleOnAudioSource => "exact-audio537-libexif-source-vendor-policy-bundle",
                Self::Existing(_, _) => "existing-normal-entry",
            },
            "product": product,
            "source_release": PRODUCTION_TARGET_RELEASE,
            "build_variant": PRODUCTION_BUILD_VARIANT,
            "QPR1_source_identity_claim": false,
            "Audio_APEX_qualified": false,
            "selected_cohort_policy_qualified": false,
            "runtime_qualified": false,
        }))
    }
}

const VENDOR_POLICY_BUNDLE_TARGETS: &[&str] = &[
    "selinux_policy_vendor", "vendor_manifest.xml", "vendor_compatibility_matrix.xml", "checkvintf",
];
// Pin the native aggregate and its VINTF producer, including their real required tests.
const VENDOR_POLICY_BUNDLE_ORIGINALS: &[(&str,u64,&str)] = &[
    ("build/soong/android/vintf_data.go",6016,"af3a6ecd77510ea5190401eaec9b85cb042a5e54c25ddd6f0dc53e76cee84c4d"),
    ("system/libhidl/vintfdata/Android.bp",1510,"fa9e0b07f4e9588b9fc1221f95b4017ccdc07677a4f6ff3d089eb464f7d01f66"),
    ("system/libvintf/Android.bp",6296,"e9a91645f7a13b096242acd1e511ef07cf42845a51d62010cde99d8568702853"),
    ("system/sepolicy/Android.bp",43207,"037ba970d4bae28865245366b4f4f9a0e828197c43843f7950a9e18e754aa42b"),
    ("system/sepolicy/contexts/Android.bp",19165,"823c37013ebe64615d435aef41e8ff4828aaabaeb12552b70713f3d1f6bdf202"),
];
fn validate_vendor_policy_bundle_originals(source:&Path)->Result<()> {
    use std::os::unix::fs::MetadataExt;
    for (relative,bytes,digest) in VENDOR_POLICY_BUNDLE_ORIGINALS {
        let mut path=source.to_path_buf();
        for part in Path::new(relative).components() {
            path.push(part.as_os_str());
            if fs::symlink_metadata(&path)?.file_type().is_symlink() {return fail("vendor policy bundle original path is an alias");}
        }
        let metadata=fs::symlink_metadata(&path)?;
        if !metadata.is_file() || metadata.nlink()!=1 || metadata.len()!=*bytes || hash(&path)?!=*digest {
            return fail(format!("vendor policy bundle original aggregate or producer changed: {relative}"));
        }
    }
    Ok(())
}
pub fn build_vendor_policy_bundle_on_audio_source(
    repo:&Path, source:&Path, out:&Path, work:&Path, product:&str, jobs:usize,
)->Result<()> {
    build_targets_with_fixed_request(repo,source,out,work,product,jobs,FixedProductionRequest::VendorPolicyBundleOnAudioSource)
}

fn validate_vendor_policy_original(source: &Path) -> Result<()> {
    if hash(&source.join("system/sepolicy/Android.bp"))?
        != "037ba970d4bae28865245366b4f4f9a0e828197c43843f7950a9e18e754aa42b" {
        return fail("vendor policy requires the original pinned final se_versioned_policy target");
    }
    Ok(())
}

/// Build the original final vendor policy on the exact Audio source profile.
/// It neither builds an Audio APEX nor installs or loads a SELinux policy.
pub fn build_vendor_policy_on_audio_source(
    repo: &Path, source: &Path, out: &Path, work: &Path, product: &str, jobs: usize,
) -> Result<()> {
    build_targets_with_fixed_request(repo, source, out, work, product, jobs,
        FixedProductionRequest::VendorPolicyOnAudioSource)
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

const AUDIO_GENERIC535_ORIGINAL_BPS: &[(&str,u64,&str)] = &[
    ("development/cmds/monkey/Android.bp",1153,"a3219a5696ecae7ca713ca85219835e8fe6c233a6b35949e26adf73bc3d41e34"),
    ("development/cmds/monkey/libmonkey_jni/Android.bp",1174,"b10ddca96d3f265b37decfe1f75381f641713e24e6d82f0e2c82c6056d1a3903"),
    ("external/angle/Android.bp",345490,"193db8af085f83b1788b0e7d69d26a0ed23a97f2c2c6cd7c695e46184f8cadf2"),
    ("external/angle/android/cts/Android.bp",1838,"a583dab9b15dff4fdb87caf290046d9d6ce899828d5e62e1bfa988dc9db3b41e"),
    ("external/bazelbuild-remote-apis/build/bazel/remote/execution/v2/Android.bp",1915,"15e078a61aa18cc4404d22552f9d48355d90e6bec6f1d9a44c55758047a7a19f"),
    ("external/bazelbuild-remote-apis/build/bazel/semver/Android.bp",1080,"5422798a2de5759afe08beb111e71ffad2e7e14c2ca9b8a5edd237502e49be59"),
    ("external/crosvm/Android.bp",7853,"e6a7db97c6e72093a27a99e067b6a3878881503d32f55cd0bcc8c18c50bffd49"),
    ("external/crosvm/aarch64/Android.bp",1948,"bc7d741c24597efcc75112ea67c1d841a7b16e95f6aef7cd405a1678bd7cbaa1"),
    ("external/crosvm/aarch64/cargo2android_arch.bp",395,"8f1a8fd518a789aced6b25da8029b2b47bd9aa8a5ba00c70db489afe5c494f9a"),
    ("external/crosvm/aarch64_sys_reg/Android.bp",1385,"c94a0b8c7b68391e7b8d264d7f44e289d7ffea71f855aeadb6da78b865582ab0"),
    ("external/crosvm/acpi_tables/Android.bp",1335,"799e21b9ab720b91def21de4f038e4111c617a3f6826ac8783d855301d386024"),
    ("external/crosvm/android_audio/Android.bp",1224,"87e309f481951b92cfc6cecb7f3316733ceabfa89317b4cd618b05ef84c9ecb4"),
    ("external/crosvm/arch/Android.bp",2734,"053ee3fc7bff3a5f9e63379e622c4e9fe7a357c99759f46419b87d720d263057"),
    ("external/crosvm/argh_helpers/Android.bp",930,"6351c01673a792d275358f57f893bdb53a9f528fdd89575c6bc3af80d8902151"),
    ("external/crosvm/audio_util/Android.bp",741,"959baec55e77920d8c67f03d2174195226c479aacf9438debf886dca33496322"),
    ("external/crosvm/base/Android.bp",7206,"fb128a2d484a284fb227f2537e5de00168840ae0cd3dac5d4c20737e8db1585f"),
    ("external/crosvm/base/base_event_token_derive/Android.bp",1404,"2904e2ae94495dc4b147fa9562915427af31d92e7ffbd88def3ba1d8c4fab8d8"),
    ("external/crosvm/bit_field/Android.bp",1861,"469560c3e0a4b3e95587711069058f5cac41ca3bea4fd9ac9bee5821461dd62e"),
    ("external/crosvm/bit_field/bit_field_derive/Android.bp",1415,"aca78233e1f96a668bbf01aff6e2b4503f0a244e33421da886bfadc3ed3bffc8"),
    ("external/crosvm/cargo2android_defaults.bp",628,"3ddee2ffa6a5cd3268d0ceaa9ed080131ef9d94705886a3ad8822bc2633bcd36"),
    ("external/crosvm/common/audio_streams/Android.bp",1597,"a71ccffe2ee1ac1266a566ad8c4a95331e8e9772ee3d3859f24a3f793eaf3a7f"),
    ("external/crosvm/common/balloon_control/Android.bp",900,"b6b5fbc449a37c99130834e6eb00243b6b6705d8a6921b6d330d79cb9909f580"),
    ("external/crosvm/common/data_model/Android.bp",1379,"b3926de8d561d53a531e0df20d0252a0f824109042aaa41b51b8ed8790e2b234"),
    ("external/crosvm/common/sync/Android.bp",856,"bdd4f1cb11ef8a44e3a61fc3e98b25229312b61787b21173f2f2c39fc359c797"),
    ("external/crosvm/cros_async/Android.bp",3322,"4e61baa6c4fad417021e43a932bed91c12b09f5fc91d306b7c74a31bd2b27154"),
    ("external/crosvm/cros_fdt/Android.bp",2099,"489ad4bf49a460764d5fa904a2e042858539f453f5740935fccbcf6c13e75509"),
    ("external/crosvm/cros_tracing/Android.bp",1012,"25ca6c96b469c48711acc2bc7007f17ad87987136b50a22a43f54baec9bc4841"),
    ("external/crosvm/cros_tracing_types/Android.bp",946,"ef03ed3a17fcdd20fd588cfae20a35540aa0b80d0ef6483b09e6a9a7ad561f9f"),
    ("external/crosvm/crosvm_cli/Android.bp",927,"8daf9a1404abcafc61b91914b2d95652e2606516b57c0837fdfd7751ea823b17"),
    ("external/crosvm/crosvm_control/Android.bp",2178,"1daa776e9bb856866b09550ff88b3301a09fe3e12d8b8074f922ef4f4211f534"),
    ("external/crosvm/devices/Android.bp",8149,"98102fa39c1a8385354d20581b9cf5b8c7ee6afcb17b4ac4d9f2139b89488c0a"),
    ("external/crosvm/disk/Android.bp",2576,"27691c4e2fa07ed327aec766ea5efb535bbb7933526cfcb700eecac8a2f73a22"),
    ("external/crosvm/ext2/Android.bp",1591,"57d7da6441f1ac27e6d4b8548d4197ae61b3025dcbf058b68c83eabc4ddfbe5a"),
    ("external/crosvm/fuse/Android.bp",1932,"ee71554db814a9a6c484c74391b68e73770c9e2add964e29ee3f44d4c3239f5e"),
    ("external/crosvm/gpu_display/Android.bp",4277,"366bde32ee6c10cbbe6c958b643c835eae6b2a8ed40f1aee016b35321372b6fe"),
    ("external/crosvm/gpu_display/cargo2android.bp",2290,"3c745a0f833989a0677c968bdd8419a60376a11011d3528038699c425175ea00"),
    ("external/crosvm/hypervisor/Android.bp",11355,"18a7d29c9499085ab7c2f0a35ac62b5c9c104712b002a89886c58e22ab804e6a"),
    ("external/crosvm/hypervisor/hypervisor_test_macro/Android.bp",774,"0f3e4f42feb4cf53ed7227158b0d2b6397055581b39598e2fb8f19203a990765"),
    ("external/crosvm/io_uring/Android.bp",1004,"39df433b84c7d78a3dc70ccb597b0d7f513fbc9ea118b203f3ddafdd1d92583a"),
    ("external/crosvm/jail/Android.bp",1740,"97919827fff1e31d5c45ef9bc929ba7d1141e8141525bb9348d761c8e9ab4f7e"),
    ("external/crosvm/kernel_cmdline/Android.bp",1476,"4049dddc68d89870e7ddd3bd1eafeee74b00fc2afd03821eb4bb52a8268e91ad"),
    ("external/crosvm/kernel_loader/Android.bp",2030,"2f40a7afe7f6506e8c57bf9cabfb23ff80503e5b620165af7d5faf2844279dbd"),
    ("external/crosvm/kvm_sys/Android.bp",1476,"19326f2551ca81a49d2fcd9b22eef96510167290e40f155bdf3546e1f5e41037"),
    ("external/crosvm/libcras_stub/Android.bp",931,"23646c2caa81daf2db7de4be484a34c5d3c7e97f601273cd08545a52e8d24da0"),
    ("external/crosvm/linux_input_sys/Android.bp",986,"bbefa1ea4b2ecd50fcf1aadfb49df4e2445c0761d03eb524594449d04a68daf0"),
    ("external/crosvm/metrics/Android.bp",1703,"796a9681850e4f86ed0cd31ced1f615f32cc2de9cc4f3a8d5c9c4f16ad7651ba"),
    ("external/crosvm/metrics_events/Android.bp",799,"2abc71672e6ba4bcddb86b58207e94cacc643483613fb1a13ac3894361f6e427"),
    ("external/crosvm/net_sys/Android.bp",922,"d4c1e01b41ca1e095e4cce3ea48b252e960149c6292a6c30931376508806131b"),
    ("external/crosvm/net_util/Android.bp",2520,"5aed5268993119fa97ebb79be7b8d7b4e5c0363ac0baecf1523f5c5ac1985fb1"),
    ("external/crosvm/power_monitor/Android.bp",1173,"5599b3102632a4fb981e4ac5404fb7186646b3c8c2dc6825ca61563465561c37"),
    ("external/crosvm/proc_init/Android.bp",1002,"01870ec44466fb12ea02915629d47d5701d1d6d0e48f69b81d6890f8b5b6f30c"),
    ("external/crosvm/protos/Android.bp",1555,"a9ff2093cecfb389638c837920b8f551c25cd9173859f0d8e0b9e53f04078041"),
    ("external/crosvm/protos/cargo2android_protobuf.bp",507,"9d0fd338dbb3fadb9871bcc1af54641fcfec122c7492e0153d265ecaa5ed8325"),
    ("external/crosvm/resources/Android.bp",1536,"b6127c4236d4bec690d88b98f36ad2c44517235423e1e9ffc5dfc208cf94560c"),
    ("external/crosvm/riscv64/Android.bp",1132,"18e9ecf3454846909f7dd510c3b5e0579b5aff90bacb6cd3e1270475c7452b4c"),
    ("external/crosvm/serde_keyvalue/Android.bp",1861,"bdb9fbe6f596c492eaa588c6c2b54723ca42c6206e85bdfcf59879900b16f917"),
    ("external/crosvm/serde_keyvalue/serde_keyvalue_derive/Android.bp",967,"ef3c693a05b4441473af2baae59103bb8bb0b2ebb8b0804e284a4a8d76033cd7"),
    ("external/crosvm/snapshot/Android.bp",813,"84111a122342d13ebfd057265d00ac1173228972c41f3ed159fbd046669c532d"),
    ("external/crosvm/swap/Android.bp",1198,"81007ea96f73ab9ad7f1962c624b32942249fe011ce743b8b2a0592eaefa5d17"),
    ("external/crosvm/third_party/vmm_vhost/Android.bp",1734,"286de816cf16e1e3c459bab7c6e06e1565162f7fef86ec6abc5e37c1fa4f399f"),
    ("external/crosvm/usb_sys/Android.bp",888,"5d8245f16dad82d88e749a848cb9ea4c2cc6bcdb44e30ff0a7f8f60ff52fb88c"),
    ("external/crosvm/usb_util/Android.bp",1719,"c09d9bf4d276dd47384348a4540138a9459151d0ea940d53ed8b2f94a282b924"),
    ("external/crosvm/vendor/generic/crypto/Android.bp",1005,"ce930c5946e9192a8a319e43f69ccbc6573c6cc46230d6b534cbaba8b6084cb2"),
    ("external/crosvm/vendor/generic/metrics/Android.bp",996,"bba13fae0dc0ac346a7e5304fb2daa707b2bf69ccd5be86f48c888139401930e"),
    ("external/crosvm/vendor/generic/metrics_events/Android.bp",657,"0c176d950e09ee9f6629e1315d59a35d925b9ce21d5d2aadd3063edc1f502dae"),
    ("external/crosvm/vendor/generic/proc_init/Android.bp",940,"cdd17fe5d7f1f6c4bb68f5e213eb8a6dd6364a70e7c285275b0e0b67e4a964f6"),
    ("external/crosvm/vendor/generic/vm_control/Android.bp",906,"417353be76bf21b61b7292e0265cc54cc42f46d49355e234543ffc4374d6821c"),
    ("external/crosvm/vfio_sys/Android.bp",928,"1180ebd4e8666cec1488fcea91fc75b5c6bac26129018ae9de7f1bd84ce3de06"),
    ("external/crosvm/vhost/Android.bp",1692,"832e22f471df6f408623151bd605d578717d8a8604888c66a64d5d4fc70ad476"),
    ("external/crosvm/virtio_sys/Android.bp",957,"a6107cfc9f772ab093ff3cc212d850392e5da6308e6fec565d0c96cb94bb419b"),
    ("external/crosvm/vm_control/Android.bp",2707,"98448ac6902544e3263011c73957915662dec41b78f77b078d0f853c530e46c5"),
    ("external/crosvm/vm_memory/Android.bp",2024,"29c4404d827b325211c793f47f4c11b27e1c5364345e6cfd90c78eebc9f9cd55"),
    ("external/crosvm/x86_64/Android.bp",2891,"96b69bb1968a8cc852ebe2210cb0c7576430c05b68642f49275ccd533a860242"),
    ("external/dnsmasq/src/Android.bp",2216,"13a4adbee368aecd47cbc418fa3ece205f9dbc889f41e8d296b55ed20c326b43"),
    ("external/ethtool/Android.bp",2223,"36377966a8399520f9e921950d09b67c60e290f703b24a5c53f40c938e0a6dbf"),
    ("external/fsck_msdos/Android.bp",913,"fc85cfbf8b93d688a0c2274a3554a1fd31fd9bc837d22a1af19768c5f5d8f13f"),
    ("external/googleapis/google/bytestream/Android.bp",1404,"7fc84964b97785827cd30f68ef1ac9f05f424110fc51335a9c3a95da3b7b48b8"),
    ("external/googleapis/google/longrunning/Android.bp",1237,"948c4def340b93e3a1c1f3330c6e0a8758e6596c57bccfe7a2ddda6bf7104fcb"),
    ("external/iproute2/Android.bp",2961,"74d4273ee46566fedd6c19f9b9a1055a629b20268accf326eeb64b9a97fc197b"),
    ("external/iproute2/ip/Android.bp",3114,"d3433407ebf459262bc1fcac182c1a5f2e59ce64c29c6bec12a89af835fe36ab"),
    ("external/iproute2/lib/Android.bp",2128,"e82d5ab64ec5afd943300fc3941048c176688127d51a759fe350302ccc49c6be"),
    ("external/iproute2/misc/Android.bp",776,"dc4a6ae51eba570a8004c309ad03dec48060a55de869bf3ecaf8218ea0570b19"),
    ("external/iproute2/tc/Android.bp",4002,"85dc15186983c582602f1f686245d770b72b430d282aba81b145eb1462aa9117"),
    ("external/iptables/Android.bp",1946,"d6d1f5feb6a2f76812e4f7e42e7dad1d41821a68ca648cbb1ee0f5ad79b521b2"),
    ("external/iptables/extensions/Android.bp",3415,"eca53adecb15f2241588e4dedf101275041aae3dafccad69defa3072594136b8"),
    ("external/iptables/iptables/Android.bp",1864,"eaeb74787a2d3f8c10e0b9bda77a4c58f8c13b2dcad39336d0f41e5e09178ab5"),
    ("external/iptables/libiptc/Android.bp",710,"e6d5e3bbd0d5b599b44f85c52e69c24c8dae733da3999674b0d1c85acb104374"),
    ("external/iptables/libxtables/Android.bp",940,"7471df48b73b2c3fa5cde6c8b93b39c3e518eebd4f0c0519585873abd0380c2f"),
    ("external/iputils/Android.bp",2246,"89c2ecc2fb3da3d7b666a142157fa7b72b070c832ab8fe7d59bcbfc8e1fc87b8"),
    ("external/jackson-core/Android.bp",1681,"c456c3ff3cc79f16e090ba331ca45ce7e51e9c64beef6c55970a20123ee555b7"),
    ("external/jline/Android.bp",1364,"947ab3501292b5449853f5756b4dafc1ca93fd1772269926b42df92b7c0fbcad"),
    ("external/ksoap2/Android.bp",1240,"208708fcfe92f90c42117cb958e6196a0c47b0988322e3991fa8ff2a5da5da10"),
    ("external/libcups/Android.bp",4221,"085a86eb5e18e34bada661d920cbdc89fea0f354fd26ea84d67f52f0eba8c686"),
    ("external/libcxx/Android.bp",345,"62aebe1aef2385ce1b233c3675bb570f328fa1c2feb5ad266d2087a8699f1c50"),
    ("external/libcxxabi/Android.bp",135,"d60ef961e80750242eb88799a2ce750187377e9db06b6a0163fef9e8d2fc3912"),
    ("external/libffi/Android.bp",4570,"067fd97cbeeb58de8952cbd5edbd141e9bd3dea5f4033890ec4407d7292cc408"),
    ("external/liblc3/Android.bp",1541,"00ce9b8a1b010ae5b9a66008bc794d58ba0de5d99ec8ab25bcbb3d3d390688f3"),
    ("external/libldac/Android.bp",2127,"cd584173071a6375a317a56a7900942c894b27f987c513a75a768acc76993056"),
    ("external/lua/Android.bp",1257,"a7062441770fcbd0fd21ce9f02e381e78e0072fe24bfaddbb7b444374e9b703f"),
    ("external/marisa-trie/Android.bp",3081,"348f8fc8cfdc57e4e11a9686a5f2f0c5ec3bf3fe430b0f8087823f039beb9a0d"),
    ("external/mbedtls/Android.bp",2432,"16b6efaf436905e06555ff14a3528a3b14d895ba7ce56bf3e21983678fc6d225"),
    ("external/mesa3d/Android.bp",18486,"43fc74c16a3ff4c54d1c2becab88a442d78eed5362b4365aaf93f37531b3771d"),
    ("external/mesa3d/bin/Android.bp",932,"76a2bbe578d428b5f640b657b5537bd40a46b9175e5ee43d87240d25a7888f05"),
    ("external/mesa3d/include/Android.bp",865,"be42485be4948e493567c4059a1bbc1d1add37d85a65d5bf1823e4a0b211837e"),
    ("external/mesa3d/include/vulkan/Android.bp",495,"438d83cd2185e3d90ccb48408e1958c646f3b27c7e16ce5f96fb50bd193472dc"),
    ("external/mesa3d/src/Android.bp",964,"3ddb9b1333bbe64ecebfac60b11b615c348c4f9588656a9a8ac5fc72e92ae473"),
    ("external/mesa3d/src/android_stub/Android.bp",4285,"f6294ad8e44baf5805718c8afcc3c0b0d3af27979c88dbbd4b1bb35b3929ae41"),
    ("external/mesa3d/src/c11/impl/Android.bp",1052,"c4fb09a14477585e323e683fb88829aa46614b6015dcfd9c56253cab3b09a637"),
    ("external/mesa3d/src/compiler/Android.bp",2272,"8da5cfd357cf53ec2b54b76ad898b5bfdab9b2b26bb564068fac8049cd44f762"),
    ("external/mesa3d/src/compiler/glsl/Android.bp",781,"4fea257ed72ed42ef03a67cccdcda29c6463f97fddd1b40fb4ccda239ba97c2f"),
    ("external/mesa3d/src/compiler/isaspec/Android.bp",2234,"976c4afde530caf43f8e497ce3a3e35c7922750958e8ff6b2dba33ad8f15a6ef"),
    ("external/mesa3d/src/compiler/nir/Android.bp",14618,"8b5b9f0fafff13bda79db76ec5173a7ea8562a5d7f1db08fb1480efe99377d2d"),
    ("external/mesa3d/src/compiler/spirv/Android.bp",5212,"090adb6c0b91b3af5bb19ee58c795b7ad362921ef981dfeb8d8f92b177fa711d"),
    ("external/mesa3d/src/gallium/auxiliary/Android.bp",23924,"9cf5fd8ff2a5e255add11b9de5759b30b672ca1e47ba6fdc47f5454b08c86cd4"),
    ("external/mesa3d/src/gallium/auxiliary/cso_cache/Android.bp",1056,"d8c0d67c7fc5c55c8f0634690e27967a2ac89a7c7dec48749edc3801ca72ad6a"),
    ("external/mesa3d/src/gallium/auxiliary/draw/Android.bp",8056,"feb1b635f37451e6dc7c241d1a4a8eadfd81561033186f6cf3c0ee5615fd8410"),
    ("external/mesa3d/src/gallium/auxiliary/driver_ddebug/Android.bp",1047,"3296f43e3184e1c54ded4620c227433fb76827efff0ddb25336f69bef7cb7c18"),
    ("external/mesa3d/src/gallium/auxiliary/driver_noop/Android.bp",674,"accb4433a69d84246bbf2abfd383b5d2fcb9826b70673a154f3e3d014ca0c003"),
    ("external/mesa3d/src/gallium/auxiliary/driver_trace/Android.bp",2347,"1c33491d99f7eb2c41031871329171b5158eb6ea03e1505350714e76ba761c9a"),
    ("external/mesa3d/src/gallium/auxiliary/gallivm/Android.bp",9253,"2a2da657dc66ad9d6992dc2c9bac4645094f7855d3339f9b48b3d1b38db6b302"),
    ("external/mesa3d/src/gallium/auxiliary/hud/Android.bp",1594,"a01f4f5102dd7e31febc63cf1acd6e2cf616eef355fdee998a78635c4a9f208d"),
    ("external/mesa3d/src/gallium/auxiliary/indices/Android.bp",1461,"dcf3cb424b30978a1455cb8b00f802240f33a4d56d24f8ef3526b2c1e7ba13a3"),
    ("external/mesa3d/src/gallium/auxiliary/nir/Android.bp",1342,"3aefaa322cc5088bcd3c33f66d15c60149c51ffbcbbed99598df2be52fdbed3b"),
    ("external/mesa3d/src/gallium/auxiliary/pipe-loader/Android.bp",2541,"d72496e98cb3b5d606d4063546e429e1515d5376832a7e3686feda967f5f5310"),
    ("external/mesa3d/src/gallium/auxiliary/pipebuffer/Android.bp",1761,"afb3e6283d41882308ca7eaa8a5261a66a2961570ee3809aa7093f228d245a4e"),
    ("external/mesa3d/src/gallium/auxiliary/postprocess/Android.bp",2054,"947ed1e805edbf11c2b49c8d3215d4e71cc74a38be2cdbb9c81b0766b5289138"),
    ("external/mesa3d/src/gallium/auxiliary/renderonly/Android.bp",586,"924ac6f6f918f80b4280177dc991138b976273b2079a1fffa18d26c5690a7836"),
    ("external/mesa3d/src/gallium/auxiliary/rtasm/Android.bp",839,"6d9ef368fa2fb0722b5523e9465d012bf920d97b138bbdb52caef628f8eb953e"),
    ("external/mesa3d/src/gallium/auxiliary/tessellator/Android.bp",846,"6e1cbb556ca06edcfde429fbff9899f8f6adedd3f2acfe6a6f7bf55946013dc1"),
    ("external/mesa3d/src/gallium/auxiliary/tgsi/Android.bp",5206,"c2ce0beefcaa5c84c6d23b78176fcd90d5d3631391521503c66283f4ba2a417d"),
    ("external/mesa3d/src/gallium/auxiliary/translate/Android.bp",1034,"be6b26cd8054ac15ee62789709d63acd97ce05fb96aa95bc40c15b59c973fe8b"),
    ("external/mesa3d/src/gallium/auxiliary/util/Android.bp",12307,"1f8405541664b27f382b354e58d91624226f66aeb0091474d29ed1b327732550"),
    ("external/mesa3d/src/gallium/auxiliary/vl/Android.bp",3484,"ff39eb69bca147227234f692087ebcb088ece1c6cd66920554d08a852e49deb9"),
    ("external/mesa3d/src/gallium/drivers/Android.bp",496,"e9bf1bedc63f2fd53fde957e55a76a9fad635b4b958773fe034e646d5aa0dfee"),
    ("external/mesa3d/src/gallium/drivers/llvmpipe/Android.bp",4304,"07efaaa0bd6ada29c1a59c0db3c86cc69f5df375c77e19159f571d0e3145cc28"),
    ("external/mesa3d/src/gallium/drivers/zink/Android.bp",505,"df0e0631c2ee2d715fa6891d354e46dd4b4739edf1af271491ed59b58473d5e0"),
    ("external/mesa3d/src/gallium/frontends/lavapipe/Android.bp",5487,"908b244812aa0819c102c54757d0817d94e8c6ab1d624821485acb6801e0d909"),
    ("external/mesa3d/src/gallium/frontends/lavapipe/nir/Android.bp",1324,"2ecd657bc6ad27efb821010158da2ca811318bf253cf185328d17f296f4de3ca"),
    ("external/mesa3d/src/gallium/include/Android.bp",488,"c4d3db556a0e9a3fefa527c3b89478ed2d29038eb9789eb3d85cd4c69848ccd2"),
    ("external/mesa3d/src/gallium/include/pipe/Android.bp",520,"e6482502ebeb168443072066925dc78971c7e96a051a74c996bb447549489b88"),
    ("external/mesa3d/src/gallium/winsys/Android.bp",495,"2976e6a400bb08252ff01ef22a453166afa76065b5b49e7d32c6ee47553cb3ac"),
    ("external/mesa3d/src/gallium/winsys/sw/null/Android.bp",2310,"540db9fca7b7f892f9f7292e68e7fb7c50f00a0f76bbaaaba9df48c8be81d675"),
    ("external/mesa3d/src/gallium/winsys/sw/wrapper/Android.bp",2293,"a02a0289f90f5fbc37da4eb78a7938a84ea123006d390415f29adffc36c7765a"),
    ("external/mesa3d/src/gfxstream/aemu/Android.bp",669,"9433d775ce09750af7847dfe1b9a4c11c8b23095eff7b921891c6590b43575fe"),
    ("external/mesa3d/src/gfxstream/aemu/include/Android.bp",485,"f06c713e10448d217936bbcd7dc7e339d7871c1f6153bf4a0fa500eaef01e13d"),
    ("external/mesa3d/src/gfxstream/codegen/scripts/Android.bp",1570,"c86123f68fa24ef9aabf6e9305a8d04749d1d4106fd678f7823949b725e9c0e9"),
    ("external/mesa3d/src/gfxstream/codegen/xml/Android.bp",440,"8c3010d34021043e96cbc3240f35935edf18343d97033c76ff2f40da8a432820"),
    ("external/mesa3d/src/gfxstream/guest/Android.bp",1627,"a38dc3a09ce5114d841c5995c07fd444ccb3025b8d326bbf50bbf58245834faf"),
    ("external/mesa3d/src/gfxstream/guest/GoldfishAddressSpace/Android.bp",1787,"934d6f555796d6d331c9555eaf105a907c0f18d5573fa27236a79851cddc0bb3"),
    ("external/mesa3d/src/gfxstream/guest/GoldfishAddressSpace/include/Android.bp",503,"6eb3f525c628de4bbd8ac15873194fdcfe09b03ee809a96f760309f7ec1051e3"),
    ("external/mesa3d/src/gfxstream/guest/android/Android.bp",3270,"d15509259461f3d6491b594c3b488a1de14eaaf57db57272d9102aadafd7e9e8"),
    ("external/mesa3d/src/gfxstream/guest/android/include/Android.bp",498,"9e4c0a166bec45c53bce9b6e74a4a3535cf12d357c657b64356a39d80d63a3df"),
    ("external/mesa3d/src/gfxstream/guest/connection-manager/Android.bp",3072,"ad3bd500f431659bfee1c0b254530e960b42ee8a29888b2b3c7288c99336902f"),
    ("external/mesa3d/src/gfxstream/guest/iostream/include/Android.bp",495,"6a9370764b2f7655b9f96055d0f7bd3f5dfc098ce3fa5ba17a2493bcc220aebd"),
    ("external/mesa3d/src/gfxstream/guest/platform/Android.bp",1379,"9be34af040d26ee0011c6b4e2ae1ee8bb87392c6c06bad94bb6d1f908501822b"),
    ("external/mesa3d/src/gfxstream/guest/platform/drm/Android.bp",2533,"a56438941b2161f9f82a32ec9cac6d98c13f0951c8b68423068306e31b4137c4"),
    ("external/mesa3d/src/gfxstream/guest/platform/include/Android.bp",497,"f2d9ed658dd50f05715508b4b6fc5da9352faa3a0f9fd31ca4e3ce9055abef54"),
    ("external/mesa3d/src/gfxstream/guest/platform/kumquat/Android.bp",2935,"0cbdc91fc16682e15d49c741e5c75be2e6460b4b7afdc3c226c81d58a99896e6"),
    ("external/mesa3d/src/gfxstream/guest/platform/kumquat/vulkan-mapper/Android.bp",2911,"ba7c522d077c65990b1b7b648a75b5be63b2fa956beb9ee8f86dc041abfcda72"),
    ("external/mesa3d/src/gfxstream/guest/vulkan/Android.bp",5236,"091e254008cc3032c6a4b549b403fba424e1dfb8b8ff8880ed2d116fad81edd8"),
    ("external/mesa3d/src/gfxstream/guest/vulkan/stubs/Android.bp",1000,"5b2bb3f4e6d5a9d251f2f689e8d3877b8a6a82fc6c7fd62e5831dccd1056ecdb"),
    ("external/mesa3d/src/gfxstream/guest/vulkan_enc/Android.bp",3979,"3e941d9f393da9199f11c15d48c0df5405180fa3f24e88d37e2dec1dfc3f94bd"),
    ("external/mesa3d/src/gtest/Android.bp",695,"cd88d6c9eb9b4b7cbb2ae9a3b084cd54df197ff0e9f8f433fcfcb8f6ac9d362f"),
    ("external/mesa3d/src/gtest/include/Android.bp",498,"279ad9c84fe8a6e050b216eb957c213894a9d6aaa59b8dedac3ee9e67a6d87c6"),
    ("external/mesa3d/src/gtest/src/Android.bp",528,"39db6acbd62c7b767c003246d50a35a93b5c45aa42d83ac420d349a071b52b18"),
    ("external/mesa3d/src/loader/Android.bp",2621,"33b3ae02eb68d73bf8adfbdfdae94b070f63fd763b1d95701138c0d9c1054d28"),
    ("external/mesa3d/src/tool/Android.bp",606,"57cf61f580cc2ddccfc50d25c6fc3df3a94d92d0cbd9d994ac28854192639577"),
    ("external/mesa3d/src/tool/pps/Android.bp",4647,"66ac630fb7cfc8cdf076959cf93130de6de6df9fa353bbc7a28a6463394f3f1e"),
    ("external/mesa3d/src/util/Android.bp",10763,"8b8f48c57359b3f337eb53c9468d36d93fc266584ab4747d904e67685aedc84d"),
    ("external/mesa3d/src/util/blake3/Android.bp",1618,"9fcc8092a5dd00dd8b9617b956ebb2da7b40c3522eb816d3ddb4a25b12c019d4"),
    ("external/mesa3d/src/util/format/Android.bp",2201,"41a0ceb647b10e25c45445d614d4356f246138a0ae6808d4ae4467f633d6a9c9"),
    ("external/mesa3d/src/util/perf/Android.bp",1166,"376c27bb7374e127752a15371cd52bf6ac6baef3acf454181fc60df7b2f63260"),
    ("external/mesa3d/src/util/rust/Android.bp",726,"b930ac14d976d6ff31c59020a08a2321f65834ce7e6843e913eff0cdc22b1830"),
    ("external/mesa3d/src/util/sha1/Android.bp",491,"aa84b9988de09567ee0d3e8e143fe8dfded6c1a205dcf1b88a712d6cd44885a7"),
    ("external/mesa3d/src/util/u_gralloc/Android.bp",1216,"3c0b638ef263d0e0b665f64fc85d438dd9c6a85c1eea8b4999845233ecffd476"),
    ("external/mesa3d/src/virtio/protocols/Android.bp",762,"e24032570a051e9dae1f9a372e34e1fee600a3e9cc4266bc2d6a77bbb63cf3eb"),
    ("external/mesa3d/src/virtio/virtgpu_kumquat/Android.bp",791,"a8cf4fe7ffa281fad70ef8a62a1f5fd4c9b61f6f8af9cbafc816ce2f4712a8dd"),
    ("external/mesa3d/src/virtio/virtgpu_kumquat_ffi/Android.bp",905,"7e9a2c925d2ae3e3322cc6838d15c83196bf11f4af892e271ec46685234ea9b9"),
    ("external/mesa3d/src/virtio/virtgpu_kumquat_ffi/include/Android.bp",500,"b9a9226ed66a775bbd29019a47df9aa5667ecb0d77f79d60c7b87f822c853edb"),
    ("external/mesa3d/src/vulkan/Android.bp",1175,"299ba66a5e06f9e3997c11fb1f2d1e733d8fc5541fa454486be4c430d0e29780"),
    ("external/mesa3d/src/vulkan/registry/Android.bp",424,"1a5c84770b80c76dee3f87fa2c5aa7e2875679236010a0aa90e1202692de9971"),
    ("external/mesa3d/src/vulkan/runtime/Android.bp",22351,"7636c69225bfaa0c192cc08cb664e9ccfe3d4db939c061e1a11576b2689e0949"),
    ("external/mesa3d/src/vulkan/runtime/bvh/Android.bp",12258,"44469bafe6953b7af1e431218686c86b77e8f9ed0c12ddfaa69135b9876467bb"),
    ("external/mesa3d/src/vulkan/runtime/radix_sort/Android.bp",625,"1dff03d912566b09c152f998b9f8cf76560fb0d66b09bcc354c9cffd01fed953"),
    ("external/mesa3d/src/vulkan/runtime/radix_sort/common/Android.bp",713,"f594ced5edf2ad544fa561fad450bde6e1cd672343f0b6e84d8884318f0694b6"),
    ("external/mesa3d/src/vulkan/runtime/radix_sort/common/vk/Android.bp",577,"0cc86f6d30adaf231e4b6d567d14bf5a2a9b478c5df771aff2b1b77cc324ff20"),
    ("external/mesa3d/src/vulkan/runtime/radix_sort/shaders/Android.bp",6700,"8cfac7078cdc9dc5abdc2a66e14d50e607fc3a4a583b78cad6f182cc83ab62dd"),
    ("external/mesa3d/src/vulkan/runtime/rmv/Android.bp",542,"2a95536e466219d2530e6e30ad990fc6de92b8e6b52acc9a765cb3abe18cda6f"),
    ("external/mesa3d/src/vulkan/util/Android.bp",10032,"7871c5de84122cf082069a99b794c86d83ee2d4dbf6e3083e76f8e3be452fe33"),
    ("external/mesa3d/src/vulkan/wsi/Android.bp",4379,"77f90b64ce7dc7fd02350d554d2c06a8b47f10ce892b756d3af8b2b60e633a58"),
    ("external/musl/Android.bp",22353,"1549385ed6509cbcf2243509878d792b6278e10a1e8b1be0b00a1ef7071c1b3f"),
    ("external/musl/sources.bp",69236,"10183770b7a1e2312f82a2caedccfa2d3db67463379fe3ebbb96d2f6bbcf793c"),
    ("external/neven/Android.bp",6521,"65d1a77097d67df01a45273c623769da9a36a23029959f53c2bb159d90ed0fcc"),
    ("external/obex/Android.bp",6381,"12533095611ad6eb8636edc799697573bbd29fc478bdf176ee2b028ccd5b884a"),
    ("external/openthread/Android.bp",33555,"d0c8578b4f2478e5ec80b5ca749285cf0c0f4080a03eca8d3fcf3d453678c048"),
    ("external/python/jinja/Android.bp",515,"2c570b88c0eb27fdc4ca3935529e9e6b5216b1354fcec3a539f8a60ba7577fcc"),
    ("external/python/jinja/src/Android.bp",219,"f2703d92dac477df285848020a1de9e6d6a43012df447fb11c0dff451dd65084"),
    ("external/python/mako/Android.bp",1157,"fad5d6f84333e71201ee35872999c012d41acd910608bec23e9b09735ca17f72"),
    ("external/python/markupsafe/Android.bp",530,"a1c17ec5bf968163d0cc003572c895ed5c30e621d6fc68b1abfd21011361040b"),
    ("external/python/markupsafe/src/Android.bp",244,"697d850582ef48b29a6f8865112b9f32eaac201d3efee13530ba97d541592726"),
    ("external/rust/android-crates-io/crates/grpcio-sys/Android.bp",2972,"5222a36700372ec7fd1a584a96d1da025d1daafd56d6cacadfff923cfcd90c28"),
    ("external/rust/crates/v4l2r/Android.bp",181,"eb17a27be986cbbb22f54f11da7297df2c07ac4fc4ea949c080f876bfd8f976e"),
    ("external/rust/crates/v4l2r/android/Android.bp",1080,"c8962af2a8c60f20e1db75e92d8837ab196121b1307aec31c5d28ae036e04993"),
    ("external/rust/crates/v4l2r/android/srcs.bp",84,"409bd45287a014a8a904be56f84a2d18975807bd457b5697925f4cb7018ddc65"),
    ("external/rust/crates/v4l2r/lib/Android.bp",1781,"32c7474e7e72a3ab55017051ffd44a15a72a2dc7d5b9b47dd2b6c3e5566c1b81"),
    ("external/rust/crates/v4l2r/utils/Android.bp",1175,"e2230dea773fd9381698b6829175a83662928584a74b8832bf1824dc0be78c73"),
    ("external/rust/rutabaga_gfx/Android.bp",2136,"3df27dd9906af1bfbac3969382b01232a9f721b7626ecdd2c06f2b2a29a537aa"),
    ("external/rust/rutabaga_gfx/kumquat/server/Android.bp",1180,"15e809794b23059e8886a9bee5ef0794f264aef6bf30228114b16d29b9ec86d6"),
    ("external/rust/rutabaga_gfx/third_party/mesa3d/src/magma/Android.bp",4659,"4da15a8ec7423820e11a245ff388ab622482159eb2b47fa642afe79ea5f13b65"),
    ("external/rust/rutabaga_gfx/third_party/mesa3d/src/util/rust/Android.bp",1199,"f905741221901ab007e32b5e55515f644a09d89bb3535d67dd159e2220cae131"),
    ("external/rust/rutabaga_gfx/third_party/mesa3d/src/virtio/protocols/Android.bp",1123,"1ad3243a70b53ea86bc248973f8529ee02e5af0e5346f3713c3681fb07d1dd50"),
    ("external/rust/rutabaga_gfx/third_party/mesa3d/src/virtio/virtgpu_kumquat/Android.bp",1138,"67df5efef1e7cb5683e04bba5dab5e533e49d88f7a407f45264e355c7baf2901"),
    ("external/swiftshader/Android.bp",3553,"6413c986f1be8a05d32b4834ec59ecbe3cd53ca10d102993909e502daa5c15c6"),
    ("external/swiftshader/src/Android.bp",8092,"9e9bb27ab39199e794b294815ae83d0fcdb1badb05548ceae2353f09fa9eed0e"),
    ("external/swiftshader/third_party/SPIRV-Headers/Android.bp",4103,"93b5bfd4e8cc76fca0e958cbf56d29244610ababfe0544d920ca1d39690ec6eb"),
    ("external/swiftshader/third_party/SPIRV-Tools/Android.bp",14954,"e41a44858659377175cec598e2160f3d46fc9f12b6fc26daf7e5948bd9fda582"),
    ("external/swiftshader/third_party/astc-encoder/Android.bp",1432,"d1450f97c687fdbeed45efa42c949a38e299d943f40def216b704de9a7044755"),
    ("external/swiftshader/third_party/llvm-10.0/Android.bp",55008,"9a574f8e473adcb38e57261bf8ac3f7771f440a89f856f27f15a4c2b9395fd5b"),
    ("external/swiftshader/third_party/llvm-16.0/Android.bp",83081,"4a752963cafc9df53da4c60270007f5d8b89a1776462339a0d64d229580fb27a"),
    ("external/swiftshader/third_party/llvm-16.0/scripts/template_Android.bp",2430,"7bc7acf93a383a15cc28dba26f55d7c4b89846cfde45f329c280342c59caa44b"),
    ("external/swiftshader/third_party/llvm-subzero/Android.bp",3715,"dd9621dffabde6d7fb5f0ca90ef246589b7ce9dd935db78f574e3ed79a279a75"),
    ("external/swiftshader/third_party/marl/Android.bp",2016,"caa3d02d76f50c96bd9ceb8d88c240c2d99016264f8f868f6f28df614b513f65"),
    ("external/virtio-media/device/Android.bp",1710,"daf7aa261deaaa785fb00b85bbdf36318b25c80395cf294ccdb89a4387125f7f"),
    ("external/wayland-protocols/Android.bp",10885,"3c32ef578b3239a598f1294dd39edfa7552633896db8d522b78fdec1022c3fc6"),
    ("external/wayland/Android.bp",5317,"a416e5ecff5ef8bef72c54d1cbb59ef064f37bcbc85d468871780b104bee64d6"),
    ("external/wpa_supplicant_8/wpa_supplicant/aidl/config/Android.bp",938,"c3033e0959d5c254d50f1ee5972012c053b572bdbdd2c1ea0387cf6d873c9bba"),
    ("frameworks/compile/libbcc/tools/bcc/Android.bp",1882,"791c784cb915158a6779646ae10e34a54571b2ea662d28c2c4112353c4933f83"),
    ("frameworks/compile/mclinker/Android.bp",1659,"c45099571b10ec525156d66f4300570377c3c4d5b63d0230dbfefbce6d18e089"),
    ("frameworks/compile/mclinker/lib/ADT/Android.bp",493,"4e848eed6842f88320fa825b2ea37bb9ac61f94e3460ffa487077619db341b9c"),
    ("frameworks/compile/mclinker/lib/Android.bp",373,"e8730b5974317bc228d69b3bbb9fd4467f5c98a530e17fb16bae48a17a5743d1"),
    ("frameworks/compile/mclinker/lib/Core/Android.bp",749,"3155680bbf1ffb45eb1fd3dd52c433f28758990b6ae9e91cbcd6e8904cc8dc86"),
    ("frameworks/compile/mclinker/lib/Fragment/Android.bp",698,"c9b7df3563e1fd6d83cbfbfe73169d7834a87a812b3169f87bab08078dafa8de"),
    ("frameworks/compile/mclinker/lib/LD/Android.bp",2413,"e14b08191d01844dfc2b6a5303b1d7aeb45c0be32f65b6c8b22a4396243766b0"),
    ("frameworks/compile/mclinker/lib/MC/Android.bp",830,"e753fec94169909dac33b6b11da05c151b816859ec6f5c434af001d253a79c6b"),
    ("frameworks/compile/mclinker/lib/Object/Android.bp",567,"f4a84e81e0b1f89b17808dd2f3e7e9bb72f056cdb30c650565401d41fb95fa15"),
    ("frameworks/compile/mclinker/lib/Script/Android.bp",1479,"d0abff108358e52c536b231575f23a2f8bc16845c66cf5de719add1069a48e2c"),
    ("frameworks/compile/mclinker/lib/Support/Android.bp",876,"987a0e0afa43fe4260eb37d34d6e9c0d5572045fb4b054bc7de8a0b3072783e3"),
    ("frameworks/compile/mclinker/lib/Target/AArch64/Android.bp",939,"f6cc8ef0ef94615757e7ce8f593db9db371fb020a78ef7650c4dfed861e6b817"),
    ("frameworks/compile/mclinker/lib/Target/AArch64/TargetInfo/Android.bp",507,"af2e830c180ba6cc71d856addfcc43cbc2a1cdd6b8dcbd483d54c3cf48b2d478"),
    ("frameworks/compile/mclinker/lib/Target/ARM/Android.bp",874,"2b2dee4cc45faed2ce23ba2a86aca4552b24ea291908a4f7f742652b7a72932c"),
    ("frameworks/compile/mclinker/lib/Target/ARM/TargetInfo/Android.bp",499,"9f96dca6f04adb1e5c317410b9a6b25cdf65a236837d42de77c05f65d55964ff"),
    ("frameworks/compile/mclinker/lib/Target/Android.bp",849,"4f7cea881eed6537494dc20bdc1843713bc457c504ced48cb31af501e7e12a85"),
    ("frameworks/compile/mclinker/lib/Target/Mips/Android.bp",816,"dc43a30dbad1304037c54d55a4df36668e0221c54da0dd9e59410e47a498026c"),
    ("frameworks/compile/mclinker/lib/Target/Mips/TargetInfo/Android.bp",501,"c08408bf6ad080793cb281a384f820ef5070487fcf545ec110669baf56d68bd6"),
    ("frameworks/compile/mclinker/lib/Target/X86/Android.bp",724,"942f66e2ab4594c74d67d42a979141378f71867519449037e933dfdfe0af01ef"),
    ("frameworks/compile/mclinker/lib/Target/X86/TargetInfo/Android.bp",499,"8eda76bb6d0daaee444dd89092514a508773997e21712dcdff2fed6f6d9103a7"),
    ("frameworks/compile/mclinker/tools/mcld/Android.bp",2367,"6c3cbe0e703be032f6d8f8d8a6a8df23a9546b73d26b5a4fd614fee652fb0707"),
    ("frameworks/opt/vcard/Android.bp",6210,"d5623cf1b5e21e119ac84f4ce50ccb00fd16e083529d1b97684ff534ff9c3b28"),
    ("frameworks/opt/vcard/tests/Android.bp",1360,"235769c932037d6bef27a1c1d5e9601250c7642b59ecdf907e3eecb660e730e9"),
    ("hardware/google/gfxstream/Android.bp",4924,"7ce5fa482d696b74ecec5bec95fc7a5d200f399565510f0a3635e0b01fc2c8b7"),
    ("hardware/google/gfxstream/common/base/Android.bp",1116,"c53fbca301d91545d229aaf89ec668c5611696b5bfeee60e850d6cb247bad780"),
    ("hardware/google/gfxstream/common/detector/Android.bp",1404,"ee91a5531d63c36002b5870e69f614c6bede86783982d4d9f65cb05c2a7a66ca"),
    ("hardware/google/gfxstream/common/detector/shaders/Android.bp",187,"21f5e35d345536ad6a2bf9c218cb936e49e92d355bc11df6a2f6854c3d491800"),
    ("hardware/google/gfxstream/common/etc/Android.bp",1330,"058abd9556a6354df77b485a8c4fcab9f8ef22339405b72d2826a6b714e301c1"),
    ("hardware/google/gfxstream/common/image/Android.bp",962,"fdbed18dc5fd061f0236720d62fb67a6c034212e1fc1ad110719010874e4300d"),
    ("hardware/google/gfxstream/common/logging/Android.bp",1172,"78da4058393f04e0795f153be6b2bc60ece2f0b6bf836adc8b245a424d7d551e"),
    ("hardware/google/gfxstream/common/testenv/Android.bp",1014,"f8689c5a0f3517cc15eb5e812903070fc8a1bad8a3eab9eb283a75bd6856924b"),
    ("hardware/google/gfxstream/common/utils/Android.bp",885,"1312d0d174637f8986f3485d80ce4e5fba109054d71ed0d3b045ff914cc914b4"),
    ("hardware/google/gfxstream/guest/Android.bp",690,"622d8ed433aa9ef22b4c6e3620389baf05e36e5bf696775366e6e5d25355a1b7"),
    ("hardware/google/gfxstream/guest/GLESv1/Android.bp",1308,"2ff2c41e11030a2a56a4cce962ccfd11711da2a3da32125066bab101ca6b549c"),
    ("hardware/google/gfxstream/guest/GLESv1_enc/Android.bp",1495,"37fd21570f14be4bbefe9dbe99465afa1cbf582cc1bc50b6c982ca053488be4a"),
    ("hardware/google/gfxstream/guest/GLESv2/Android.bp",1339,"e129d63335bf2ff9dd26aa1bc9a7e80d0773c074c9a91a6e80f74a07a4f0241c"),
    ("hardware/google/gfxstream/guest/GLESv2_enc/Android.bp",2115,"3e275ef67b55695fc058c7fafe67bef3997ee8d824e4fa55ce5d5870c3fef376"),
    ("hardware/google/gfxstream/guest/OpenglCodecCommon/Android.bp",3152,"360b463be239dfeb4dd69fe5ec14f8f96fddd6858d5dd04d468a1c1570caca14"),
    ("hardware/google/gfxstream/guest/OpenglSystemCommon/Android.bp",4040,"a6c4acb1f017ae95a8f77bf6cde021179da3a7160096195fb55ed9f7313aa048"),
    ("hardware/google/gfxstream/guest/android-emu/Android.bp",3026,"1bf6873b916af1af05e3c9e1be6a4dffa074d5572cb1ecc4344930de081c1419"),
    ("hardware/google/gfxstream/guest/egl/Android.bp",2149,"50d64f825cdb0202ba1e367b00bfc89a23a8090029338a6c90701b8dc7144861"),
    ("hardware/google/gfxstream/guest/gralloc_cb/Android.bp",964,"40224d31e088f64cf493751436f0778562f4b6129859a5894d8b6075c6bba21d"),
    ("hardware/google/gfxstream/guest/include/Android.bp",872,"47c33eb2a6c4aee01d5dce1e1b9d2c03b38772b7a61adb40fc92ce2997e05ca3"),
    ("hardware/google/gfxstream/guest/qemupipe/Android.bp",1699,"558befae2e7e3b12dd7f55dcf78fb49f470aa61dfff233f616fc5caca29c0264"),
    ("hardware/google/gfxstream/guest/renderControl_enc/Android.bp",2851,"35133d0b04a4dcbea12816a27ec4aa7171dcc1c9d98db3591053431a78439abd"),
    ("hardware/google/gfxstream/guest/rendercontrol/Android.bp",1664,"78afa3ce3ab9d223535536463a728f6c03f257a59f841071660a2c5984e486fa"),
    ("hardware/google/gfxstream/host/Android.bp",6843,"11086623debc5d7e5bd1bdbe2a86af3cc40489b9c234b78d6bd90f6489f75180"),
    ("hardware/google/gfxstream/host/address_space/Android.bp",1329,"8cb1205e13a367df09680d27033b71c4e8852e6640cff31d999c6dc07fa43416"),
    ("hardware/google/gfxstream/host/common/Android.bp",1717,"e29f26accc8ea26816ee9772fc3df86df224cf3bf89a84d43328b52cfa52163c"),
    ("hardware/google/gfxstream/host/compressed_textures/Android.bp",1045,"ac0a15fe744ee1c2d80e343d16f2bcf998531d05cba41c24fca665a477b90160"),
    ("hardware/google/gfxstream/host/decoder_common/Android.bp",1517,"858edea11eafe336c178b1c09ff2df22e2aa08b514182b00d1383fe3508e6319"),
    ("hardware/google/gfxstream/host/features/Android.bp",997,"940535fa6681c81d861cd08c126604f9f4d828eadbd630af36096765c74299fd"),
    ("hardware/google/gfxstream/host/gl/Android.bp",2062,"b92f34b6d68ab60a68a4966fa32b5bd4474844ece02533f4a1c8fbcf480927db"),
    ("hardware/google/gfxstream/host/gl/OpenGLESDispatch/Android.bp",2007,"416884172ef0c20151da13e22947c3f50acb86f7ca9c56df738bbab2af6ff1fe"),
    ("hardware/google/gfxstream/host/gl/gles1_dec/Android.bp",1438,"f24629b4a547db3631479c8905e0e39015c7132f8d8781a5873069e2cc7f2132"),
    ("hardware/google/gfxstream/host/gl/gles2_dec/Android.bp",1431,"e4a3d626ebaeb2e75bc7d1471d351b3814383e806c8c00faba0242df7ddde902"),
    ("hardware/google/gfxstream/host/gl/glestranslator/common/Android.bp",2247,"7ed06eb0ea0c02c55b4d2e5aa9d8d9ee8cb4b32cba710424d67b975b9ee00922"),
    ("hardware/google/gfxstream/host/gl/glestranslator/egl/Android.bp",2042,"c5c2bc8b55e18c7caca9f08bb32b8e3eff5c3db508717ce1b83675b6cf367bc7"),
    ("hardware/google/gfxstream/host/gl/glestranslator/gles_cm/Android.bp",1427,"f786eb1b69ba8a018cf9233f0a443c9cf348a7797467af78081e3548d9c41a85"),
    ("hardware/google/gfxstream/host/gl/glestranslator/gles_v2/Android.bp",1515,"8d82456f3bd64eebfe38449c8edc59b3ed3433927b0cd5f134f0b441b28eb44b"),
    ("hardware/google/gfxstream/host/gl/glsnapshot/Android.bp",1022,"5dfe6b4ec82fde4995f05ff26512e5ef06150a1c79b47f2c8e8d26f61ec09635"),
    ("hardware/google/gfxstream/host/iostream/Android.bp",852,"b727bf5c084ac4bb24ebf54d088ed420720b8d0fc07824d39503eb9cb15b49eb"),
    ("hardware/google/gfxstream/host/library/Android.bp",1038,"5a10f1220c855366960927cf16a60e6c6c53cac35cb8479a4210abc90fe8e795"),
    ("hardware/google/gfxstream/host/renderControl_dec/Android.bp",1253,"9adb12beb5aeb7c0dc956d4c1aaed45516d4411353e7924bd21f0d6e144cc3f8"),
    ("hardware/google/gfxstream/host/renderdoc/Android.bp",1290,"267e3a46ea9298aad89451da1dbd79701a21023496574ca38ce98add1a734a67"),
    ("hardware/google/gfxstream/host/snapshot/Android.bp",983,"43b7d34148563eb2a547e34dfe7d2077b0beab12cb37b713488fdb3a8b2e1d8f"),
    ("hardware/google/gfxstream/host/testlibs/oswindow/Android.bp",1200,"2908bfa72a0b67a0651760d20a26f2199f01de4fa82b336dc4182c50164eec71"),
    ("hardware/google/gfxstream/host/testlibs/support/Android.bp",1760,"211463eb57f81bb3355b9d2d621f0572f5619c151ac003406e5cb3da65c16320"),
    ("hardware/google/gfxstream/host/tracing/Android.bp",1204,"5c933a16c5b7b7fb33984a86578d5e5ec18a77def4d91217ee1153310300b79e"),
    ("hardware/google/gfxstream/host/vulkan/Android.bp",8770,"ab11b4b4e9d329d60e449f13dce0dfae9352069d5b8b8e0e334f0ea9addd0d92"),
    ("hardware/google/gfxstream/host/vulkan/cereal/Android.bp",1714,"0288be5b39b629fc3e0fc5f41b763fb1479860557d4b2bd3ac211727d7c5006d"),
    ("hardware/google/gfxstream/host/vulkan/cereal/common/Android.bp",859,"bc368bbc34ef0760c008666a6c63f2bceb95663e867895c0c2c5d8521506b63f"),
    ("hardware/google/gfxstream/host/vulkan/emulated_textures/Android.bp",1321,"1e2fe2f2e387ebef0813cdfa4fa571b4a11659fb676281a4988cdb47dc3c7c82"),
    ("hardware/google/gfxstream/tests/end2end/Android.bp",2979,"96c3eb8a04223e81c24343054749cebba969599f712cc526ad120956f55ce0f2"),
    ("hardware/google/gfxstream/third_party/astc-encoder/Android.bp",987,"1ee206b2a61e579937ed7400a9a6a53863e807ab99b21769e94a9766c87617dd"),
    ("hardware/google/gfxstream/third_party/drm/Android.bp",854,"dacd0573a2950bded62dd76325e7308127f71623cdd824feffa1b8e37ed42b7e"),
    ("hardware/google/gfxstream/third_party/glm/Android.bp",831,"8b8bd1d3e8a34267cdbc0381c2e22d9f026b7cc8acc4b1a579e3ce216f8c7daf"),
    ("hardware/google/gfxstream/third_party/opengl/Android.bp",967,"a0f7ebdecc48f29f54269c21b6930f5f54fac5170b0a2d89a8f2a4c4db9a9e7d"),
    ("hardware/google/gfxstream/third_party/renderdoc/Android.bp",1253,"227071a68df2c9afd9a0305ead0bad4d1641b3a01b2e5b348a3cebc9aa6d3e6e"),
    ("hardware/google/gfxstream/third_party/stb/Android.bp",1253,"436f6b348b4ae51e3123cb4c520924d4913b5694624c30626fb81df6ba47d751"),
    ("hardware/google/gfxstream/third_party/vulkan/Android.bp",1175,"7545d68e7a7735472e3dc275a39b070936d0e8879f67c2e1773572d5c6ec04b1"),
    ("hardware/google/gfxstream/third_party/x11/Android.bp",843,"35da2676fc7d7bf0189eea2582e50296ebb544ebb311873db85a0b183aa8af5a"),
    ("hardware/google/gfxstream/third_party/xcb/Android.bp",1235,"6084c205abf85ac5309694aab9c28e63bbcb9cc4eb27a60a318bb0bb7a5e9ef1"),
    ("hardware/ril/Android.bp",488,"86bce79076e432f4067428a83aa2844d371579ee6ebd891809af008fabd88014"),
    ("hardware/ril/libril/Android.bp",2115,"185a370c3e4c02596145e86258a29c23a8f152368a50a90dd04ba14264c91f09"),
    ("hardware/ril/librilutils/Android.bp",1142,"7c18b12f903e3ccf6c7821b0fca75835b68bc9794f3b9f4949fc2dfdcc343be7"),
    ("hardware/ril/reference-ril/Android.bp",1511,"d78ffb55c84d011081ef707a2b6616b4ba421637cc5f672d56280423baa1c079"),
    ("kernel/prebuilts/6.12/x86_64/Android.bp",921,"c6f2116476ce6627d034bc978d778e55d897d1c16bfce09ae2778ba20020241d"),
    ("kernel/prebuilts/6.6/x86_64/Android.bp",917,"f8da48548401481a52d6ae30cc6a2eb9011baeb1ded6c11a0153d9b6ee35c5a2"),
    ("packages/apps/CellBroadcastReceiver/Android.bp",3901,"1bd490b2bb67e337cbe9297d4c419527858bdc78a181398bde5766e591365b6c"),
    ("packages/apps/CellBroadcastReceiver/apex/Android.bp",1184,"b5182de0ae1b44018e4d452dd65ddecff2057e38097fb5e213ca72fb8f4acda0"),
    ("packages/apps/CellBroadcastReceiver/apex/permissions/Android.bp",1382,"2095635a9342b6ecd140aeca0d79ef983111f27b27d344b98f5e59051609e0e4"),
    ("packages/apps/CellBroadcastReceiver/apex/testing/Android.bp",1121,"a376b53fb4098bdd249cd63781845ae7ea3148286f19e59bbefabba98d9778d9"),
    ("packages/apps/CellBroadcastReceiver/flags/Android.bp",1735,"77c5aede61323ecd9b3ef5f4d2f3b7b7afd1a0221772a4b0e928f2d9d4579099"),
    ("packages/apps/CellBroadcastReceiver/legacy/Android.bp",964,"effff2da7d1db3fd04ec55e22101158a52c8131438d3b83e2d39e5c2b89bacb2"),
    ("packages/apps/CellBroadcastReceiver/tests/testapp/Android.bp",2040,"772f933db7c4d2692bb7a661d78c0c3bc2f1233c3f9d1aa6e956e4dc591ec1f1"),
    ("packages/apps/CellBroadcastReceiver/tests/unit/Android.bp",3838,"de12838ee2de28bfa5451466abb17f843ebe7f3184fc57c1d03d87249e5894a6"),
    ("packages/apps/CertInstaller/Android.bp",293,"e4adf85e4ae7e723d34cb4402130ff00513980afc41e6ef6d44be9f8a12c6646"),
    ("packages/apps/CertInstaller/robotests/Android.bp",541,"245781083f81f2ef238149d27ff88c1541c5e431e762c45597899b41ed97f694"),
    ("packages/apps/ContactsPicker/Android.bp",2380,"206cefdd8f69cf5e218bfcbc0b63380f5b864d443a753a76c000be74fbe6003a"),
    ("packages/apps/ContactsPicker/tests/componenttests/Android.bp",2026,"4e9956085f3ea03d3a4d2c01e3fd17f00f2dd34ea84de6617487fce4e4e7f3f6"),
    ("packages/apps/ContactsPicker/tests/democlientapps/lib/Android.bp",1235,"767a9718380794559f65bac59b35810e07236c84e952c686bcf283bc964649ef"),
    ("packages/apps/ContactsPicker/tests/democlientapps/sdk36/Android.bp",1415,"bfa700c71966b618214dca0949bce15043b68b36b52bfd728ef682fb85c9daa0"),
    ("packages/apps/ContactsPicker/tests/democlientapps/sdk37/Android.bp",1439,"279cf80623b646ff584afb2b77ee33de1e78e573bb214fc530ba2f2cf24b7f50"),
    ("packages/apps/ContactsPicker/tests/integration/Android.bp",1630,"f685d9041f672fdf4c07ab476d4370389e7ef3420f796e2ed3781e1ba4a26b64"),
    ("packages/apps/DeviceDiagnostics/DeviceDiagnosticsLib/src/androidTest/Android.bp",1449,"452ed2b44aa93981755bb79961903386a94cd23a24bb4ea11ce2b097382abe82"),
    ("packages/apps/DeviceDiagnostics/DeviceDiagnosticsLib/src/main/Android.bp",825,"16e1eb718d2f07edac8850b19f7a29137087602e983eafd0513b39072403866b"),
    ("packages/apps/DeviceDiagnostics/app/src/main/Android.bp",381,"a7a0d6b5731f6ac0293f6ddbaa110db3d3693acd34b21e1c2338a0e66ea8752d"),
    ("packages/apps/DeviceDiagnostics/tradeinmode/Android.bp",1562,"4e0d309440c7b87cacf6f9f84e2d2437aaa644a719a983ce8b55c5912701ee80"),
    ("packages/apps/DeviceDiagnostics/tradeinmode/tests/Android.bp",1438,"94a510d6b4bc63be63a5b69c42e76687bce14bd48044ef2426b1073e8b2335ad"),
    ("packages/apps/HTMLViewer/Android.bp",640,"74b6d43d9b9da5abfdf021cfbe2de0850c21fecdd19cd668f196b93a5501660a"),
    ("packages/apps/KeyChain/Android.bp",909,"9200024ae517b5a3992d3d9965dbe9c19764277af40e35013e91165bb8d041af"),
    ("packages/apps/KeyChain/robotests/Android.bp",494,"0678a8b4013be212be2ef9040480522705170237f9922abaa4458c109d817fd8"),
    ("packages/apps/KeyChain/support/Android.bp",1067,"6ec1b0b707217d79dac7f647661c0bff40ec02adb4f594d59ae49ea89932501d"),
    ("packages/apps/KeyChain/tests/Android.bp",1390,"fe63b0f9d3d0ef1eb46781d9514f4b4bb9431ee4c6a8512d2b9faa0f1034c515"),
    ("packages/apps/MusicFX/Android.bp",354,"76acb13563f15272086e4a9f4fbc09aa95a9ab0acba27848416fb8b3ab29089a"),
    ("packages/apps/PrivateSpace/Android.bp",1572,"04d044a372b7585f93ccad02622acdf5bf8f81e8fd16945216a0c2dfb3833bf5"),
    ("packages/apps/PrivateSpace/tests/integration/Android.bp",692,"7509d3ae2a217fc88f9c59f561f1c8f032f02f26ed4c2a507494eef4768b943b"),
    ("packages/apps/PrivateSpace/tests/unit/Android.bp",1182,"8cb1934d9c1aee43fa1c56c6631af46e6197893ce88a05e7e4486246956ec57b"),
    ("packages/apps/SecureElement/Android.bp",1176,"18d7002d78af73bdaacbb1a9beeb360aeb1aee7336b7ef284b6aa25856801fdb"),
    ("packages/apps/SecureElement/tests/unit/Android.bp",705,"1f8eec15c6f9cac229d49b00e4313c295d77d92ac2c6f96b78ed69949d289783"),
    ("packages/apps/Stk/Android.bp",434,"a5febf2490f7e1422ffc0075dd3e36ee4b9bcb0b5cec27b7d2ec0afe53d9829b"),
    ("packages/apps/Tag/Android.bp",350,"6f322545fec16c0792ac1b2decac99df01e28f1626e5d293b3e2c5bcc395d5dd"),
    ("packages/modules/AppSearch/AppSearchAiSealConfig/Android.bp",3821,"3a2e46b369387d3ec9fd6346f06857d250536d23dd7066fce4bee496088f5fc2"),
    ("packages/modules/AppSearch/AppSearchAiSealConfig/assets/Android.bp",871,"3e0d7e03dd5ee5cef81552df0885c2a050b8121aaef34c519e00f5c00ba0afe0"),
    ("packages/modules/Bluetooth/android/app/change-ids/Android.bp",1074,"df6aadc48c695adfeb32651d3a5f353cc924c1038e16e270f92b2c772d8d79e4"),
    ("packages/modules/Bluetooth/apex/Android.bp",4415,"626cbcb83fd9ae547290de376964d86ddba01b24a1a0ea909eec221fdb52cc27"),
    ("packages/modules/Bluetooth/apex/key/Android.bp",412,"f5e7abb928373a4543ad427fa44da6b53a9f4fbb39cbd7564c69f7b9e2d67422"),
    ("packages/modules/Bluetooth/apex/permissions/Android.bp",182,"118a9b52303140b7f03ed1692beaa25c6c23390ee63f3b4efe5b18d0c82898e3"),
    ("packages/modules/Bluetooth/common/kotlin_utils/Android.bp",935,"1d5e94fcf8172f1e64413fc3c1b1bc47c664a58533abf18e1c426ff3af7f518a"),
    ("packages/modules/Bluetooth/sysprop/Android.bp",1055,"1a7c43a3039cd2d9a137efe5749d21de25b9824a52bc6ab599bffe470313649f"),
    ("packages/modules/Bluetooth/system/audio/Android.bp",2758,"56e8c8db92af48ef4f9fdb7d8a778b365793164bfaf7eb51d74bde11e952d61d"),
    ("packages/modules/Bluetooth/system/audio/codecs/lhdcv5/Android.bp",1180,"08bccb5b4f2c71eea9416fb99f767cab24c14b2953c3507c8dfb7a3c42da91a3"),
    ("packages/modules/Bluetooth/system/audio_hal_interface/Android.bp",10784,"0a4165644aab567cf94f30b7f9d9a17c2c599d77e4072bb5fa68ea29df5546cb"),
    ("packages/modules/Bluetooth/system/audio_hal_interface/fuzzer/Android.bp",4222,"a81f1092b9bce9071af9345b1eddccdf389ae2c6ab5cff670072f773dd5dc53f"),
    ("packages/modules/Bluetooth/system/bta/Android.bp",52240,"3349d02afa34e13d165d50836c71771eb243dec68344e4308d2b12ed234182ac"),
    ("packages/modules/Bluetooth/system/bta/aics/Android.bp",833,"d81bffd58a69b590366c60e5f81d711a39e269b2bbcb1a458ee8ee569225f3d9"),
    ("packages/modules/Bluetooth/system/btcore/Android.bp",1342,"9c540ba75a68999da642b954991f23b3f2cebb0738c393f87db80f6c7c6e8b2d"),
    ("packages/modules/Bluetooth/system/btif/Android.bp",16279,"b0c80df5edd73c6465ce2644b942dcf9ba8360ce2e69c1db3c4b045854ffecc1"),
    ("packages/modules/Bluetooth/system/common/Android.bp",4245,"2ddb489b4b21ee926591adbdfb1780c566d358b138aef773d24a2001d79acd9b"),
    ("packages/modules/Bluetooth/system/conf/Android.bp",752,"53f8adb6b001fefaab9f6d2d7e960e1d51011391a139afb941f42b9750c8a1d2"),
    ("packages/modules/Bluetooth/system/device/Android.bp",2748,"7ddebfe650b3bd9ce1aef7c0d6d98e26e89cc0222cf4c04d592fa0cd6c5d1f35"),
    ("packages/modules/Bluetooth/system/device/fuzzer/Android.bp",1897,"334f20ea30d8ec87d9e77c5cdb924256b3584b339032b518bf5f71331dab1304"),
    ("packages/modules/Bluetooth/system/embdrv/encoder_for_aptx/Android.bp",1340,"19aaad38c6e5987461f0f8723d23580a31a7c355e4fc02313cd5877bcf37a4e0"),
    ("packages/modules/Bluetooth/system/embdrv/encoder_for_aptxhd/Android.bp",1344,"d89815161fbcd5f6f10f93049a7ccc3bcf381a1ce75f44ca09846e9bdcf424fe"),
    ("packages/modules/Bluetooth/system/embdrv/g722/Android.bp",729,"cee81e2a9c6574a05df4a7500271d08199b348fa0727745935952510da05ff68"),
    ("packages/modules/Bluetooth/system/embdrv/g722/fuzzer/Android.bp",526,"ecfc78bc2e67f25fba71f6ae2375aa1c439c2bf7e6d550dc10d054a9aafbe8aa"),
    ("packages/modules/Bluetooth/system/embdrv/sbc/Android.bp",371,"14f51fcf479364a96179e359b409128d57521e2cb40d9f5aa67f87beb6155087"),
    ("packages/modules/Bluetooth/system/embdrv/sbc/decoder/Android.bp",1365,"3b2e0aeb000cd5189054eaf28ed56d7bb8da2ac7be23d848add13798f524c2da"),
    ("packages/modules/Bluetooth/system/embdrv/sbc/encoder/Android.bp",1631,"772a6b54a7c32928df9ff1d36c02a01355d377c1648d2ea035206569b24377f2"),
    ("packages/modules/Bluetooth/system/gd/Android.bp",20158,"6795389b802cfb194dd776a9dcda8de66480298ef91282c51226625213940036"),
    ("packages/modules/Bluetooth/system/gd/crypto_toolbox/Android.bp",908,"a9074bde40169a6abecb323f3fb6d4ffc65725baf6c614855785272f6f8208e8"),
    ("packages/modules/Bluetooth/system/gd/packet/Android.bp",982,"bebf4a0fc50162d46cfc99d1911ac777234f9f5fb2eaf9ca022983691f83e317"),
    ("packages/modules/Bluetooth/system/gd/packet/parser/Android.bp",1469,"b15c36754826adf3c56c8e55438d85d0769dc7e1d671baabbad501be47d589fe"),
    ("packages/modules/Bluetooth/system/gd/packet/parser/test/Android.bp",849,"82d3f61b7d802bd76cd3a3d7cc5b26138bbd4026f89b06186d35426db1619bf1"),
    ("packages/modules/Bluetooth/system/gd/proto/Android.bp",613,"eef8955c5ed3152841580981161a424d420c185e164185fe92783bc5e33f9dba"),
    ("packages/modules/Bluetooth/system/hci/Android.bp",1983,"4ea4d782255f24481307a8e36f120e1266a10628285886e1aac9cb6bcb7362d4"),
    ("packages/modules/Bluetooth/system/include/Android.bp",1480,"584f794760846ea50b7c8c434605faefc9cc658e381443acdf0962bf2dae6403"),
    ("packages/modules/Bluetooth/system/internal_include/Android.bp",594,"2983f7f1bf915da2b29eb269e7ba69abaaedf843cce542fc03b6907190c353bd"),
    ("packages/modules/Bluetooth/system/log/Android.bp",1318,"a442c5e84ce7747fae5f5b5cf0aa7b7796827262fcf9bf0df659f375ebbdb0cf"),
    ("packages/modules/Bluetooth/system/main/Android.bp",4527,"9e52e3e6fd2e261044bd9532cbc3855456c6e4983ba771d558737ad1c813a833"),
    ("packages/modules/Bluetooth/system/metrics/Android.bp",4402,"b938b5723b2aebfb553ed10f7911ebdf5aa3cb1cf54d5265533ae5fc3b99700f"),
    ("packages/modules/Bluetooth/system/osi/Android.bp",4397,"9e56022bf515565eb5c95e508ce959952ab843427118ceb943ab3f493af3ed47"),
    ("packages/modules/Bluetooth/system/osi/test/fuzzers/Android.bp",592,"a344387713de68a0592b7e43871b64acf6da963c949d6d75078a78346837cd27"),
    ("packages/modules/Bluetooth/system/osi/test/fuzzers/alarm/Android.bp",1022,"c5accb02afbbef32193db6757bf7a2b4df4dd0ba4b0b56b0960d375d0df0f801"),
    ("packages/modules/Bluetooth/system/osi/test/fuzzers/allocator/Android.bp",670,"217942e6eba6521090035701c985aeef6d2d68e226de09850c14f35daad38a23"),
    ("packages/modules/Bluetooth/system/osi/test/fuzzers/compat/Android.bp",638,"5354a3b1c548c9dbe486531e353994ffa65263315b006b288169b5b02a245d30"),
    ("packages/modules/Bluetooth/system/osi/test/fuzzers/fixed_queue/Android.bp",721,"f9ded103945605a6f665cd7987f94858b7356da4a6440808c211b0a0cb5c4b7b"),
    ("packages/modules/Bluetooth/system/osi/test/fuzzers/future/Android.bp",711,"b66d4fedc8b68cbb54a69d374dbb5339d3bdf7e3c67786f5d1ce19bc88a49c5d"),
    ("packages/modules/Bluetooth/system/osi/test/fuzzers/list/Android.bp",660,"fef382780ee3b3ce8f26a3d114bae8409b2d87e60759f926a0d9f4bd9b7f9c89"),
    ("packages/modules/Bluetooth/system/packet/Android.bp",3001,"3a42968efa7a16efa8105bd2344c70c719f82feadfbfa4b93c2450522e083633"),
    ("packages/modules/Bluetooth/system/packet/avrcp/Android.bp",1798,"464920cb5f2cea5b5a8acf2f683fd43e915ff135ea3b8354a448e84ffe19a23a"),
    ("packages/modules/Bluetooth/system/packet/base/Android.bp",841,"915ab80d98ff905a146e89509a5cddf45d4cc80d934139a6b08a2c842a4369a7"),
    ("packages/modules/Bluetooth/system/packet/tests/fuzzers/Android.bp",6266,"61a446fae926fba2ea4e5a52d808c2465358af6fe93847392b7d2279462bd809"),
    ("packages/modules/Bluetooth/system/pdl/Android.bp",285,"504a95afe9bcb99d499a1cca23347e761e07f2bcf41612da9c4a53c9a12c9007"),
    ("packages/modules/Bluetooth/system/pdl/ascs/Android.bp",831,"9ce356e23a22426beddde793a4581e45e06c9d25322cf16cca309c944b6b6e18"),
    ("packages/modules/Bluetooth/system/pdl/hci/Android.bp",1890,"77455b5c0289c705415aeb8728c2aa0f16bc0730cfedb33238864bd35f6fc385"),
    ("packages/modules/Bluetooth/system/pdl/l2cap/Android.bp",841,"e8a28361b9cfe5898c5d5b501c899a19af394351718b67ef84593aa0db9ed789"),
    ("packages/modules/Bluetooth/system/pdl/pacs/Android.bp",831,"cf9caf743e18e78d5f8830d190b4bd094e83192d095506653fdef6b8c7743d9f"),
    ("packages/modules/Bluetooth/system/pdl/ras/Android.bp",821,"5ae3f7263787f29e6b39eb616df5b0e9526360716eb7affa78d8245e2dcac33d"),
    ("packages/modules/Bluetooth/system/pdl/security/Android.bp",826,"15d1d37abdfd69145a075f9c1a334b3dea1e7e1badca06047abb036a478eccf4"),
    ("packages/modules/Bluetooth/system/profile/avrcp/Android.bp",3546,"7cfe9293d48d86384563192e93f9f89ad2b5857873345c384376ab941fa40531"),
    ("packages/modules/Bluetooth/system/rust/Android.bp",2185,"d96c7f521540c7c3de883cd4c97391c99d09b49f15527764b46e4eb33199642a"),
    ("packages/modules/Bluetooth/system/rust/macros/Android.bp",822,"b8db6bacbf064a24dc9e75ea4001dc7ddd2bcf79863b53ad623c4352f94728ba"),
    ("packages/modules/Bluetooth/system/rust/private_gatt/Android.bp",5452,"4e69b0772576315789440f3f706eae9a3da35013692da4363c5a3331658927c7"),
    ("packages/modules/Bluetooth/system/rust/src/le_audio/Android.bp",2692,"aae49a2407794ad31cebe2b2134a43e14a1e4cdb3b3238a24451249cb86e4842"),
    ("packages/modules/Bluetooth/system/stack/Android.bp",62532,"d9135f0290d56d7bd5b00f8575c2bf5e5f49ffd99553cbcafbb1ada54c1b7c22"),
    ("packages/modules/Bluetooth/system/stack/fuzzers/test/Android.bp",3572,"423a1c29d0cc30eea9b65fdd51b655c78eba5a1431700b3645b0c9ca7b67f339"),
    ("packages/modules/Bluetooth/system/stack/test/fuzzers/Android.bp",3643,"89e623196dd253767e3aba3c3521ea234f05aa6604239e18ea464d5e6ff1998f"),
    ("packages/modules/Bluetooth/system/types/Android.bp",1555,"2cf3372c2c4ba57ec7ea041445f3518683e318f7ea4250c79f3ed88cf6486127"),
    ("packages/modules/Bluetooth/system/udrv/Android.bp",871,"910c2c609b0860ecd5d9c1aa4318b56a4bb0760fed4e0fb3b544dd5e0fab05a3"),
    ("packages/modules/CaptivePortalLogin/Android.bp",4062,"54660bc603b16321cd64306e0f1d12aa030646c7bfe895590ee44088019fd668"),
    ("packages/modules/CaptivePortalLogin/tests/Android.bp",2818,"c88c5451a6faae47f14a230e3dc17a6a4b90fdcc6ceab4af48b630428bad44ff"),
    ("packages/modules/ConfigInfrastructure/aflags/Android.bp",1227,"c259bef41099cb002295d1de2293ed1d8eda121a5fa099d29bbad7a6452b6efb"),
    ("packages/modules/ConfigInfrastructure/aflags/proto/Android.bp",1626,"5584c4f7b001a99b96d8ad761db857a27a771a35394f4ace9a7bfc2985d7e9b5"),
    ("packages/modules/ConfigInfrastructure/apex/Android.bp",4713,"614c3bda1c8e0fb1d4234e4efacbd9d3af8179c12289a6ea7c5e1835541db4a2"),
    ("packages/modules/Connectivity/clatd/Android.bp",2831,"6d80870a3709dea8fb1d17d1751f7277968f6d429f0328ecafd2268dd230e045"),
    ("packages/modules/Connectivity/staticlibs/native/nettestutils/Android.bp",1222,"2b18cff82a006f26105b92153b83e9f2dcb82f2f54df9450dc3780c7c85b4fa6"),
    ("packages/modules/Connectivity/thread/apex/Android.bp",1110,"d51fc08095b5cc8cc7e142d544e4b777cfea2bbdee2467a05f12bb072d690b16"),
    ("packages/modules/DnsResolver/apex/Android.bp",2309,"620c4fc222727039bf81497e60d0ba07be4634bf12de691b4ec99e5011bc9ee0"),
    ("packages/modules/DnsResolver/tests/dns_responder/Android.bp",1233,"13d0404010463a5c4d4879a4a2af442601b1ecefe96cc8919bc7020dc542d769"),
    ("packages/modules/ExtServices/Android.bp",4953,"9dd21818df4aef2254da28e127d6ebbf6f22aab3bd9f1a3c1edc7d4a96454cd1"),
    ("packages/modules/ExtServices/apex/Android.bp",2540,"4da492d9f66c11a7d960c5105136a8cfd7e71b02c9862c32bf1c785852ac23a8"),
    ("packages/modules/ExtServices/apex/permissions/Android.bp",1134,"84f4ebfc904217e0e85b7267e925ba7739e8cc523acbf4b23dd75fe2745d31df"),
    ("packages/modules/ExtServices/apex/testing/Android.bp",1357,"8353b6e7b2c5c614d067f6fcc5a815e7a27405bbe20b9dc740c4eaddc49cf8b6"),
    ("packages/modules/ExtServices/flags/Android.bp",1293,"6c59d76e29b83ed780c9181024f03acc2601766dbc28c4b1fd769dc7dbb742a4"),
    ("packages/modules/ExtServices/java/tests/Android.bp",2270,"57dd1398975c4d46fea8ed396795602e8b7ce169ae1f6b8259f9979dd16bf84f"),
    ("packages/modules/ExtServices/jni/Android.bp",1653,"9c4db0b16f0b94b40c9f1645e3f624cf672f907c0f3b777a000f11f852e89364"),
    ("packages/modules/ExtServices/native/Android.bp",1598,"800bfb2ae797f436d4ae1adb26b7cd625ff393b403b0501f72a6a165eb5117b6"),
    ("packages/modules/IntentResolver/Android.bp",3507,"b85d86e1516b93d7d5f7181e2f2437086947b923f5223802d53a1cf417ddfd5a"),
    ("packages/modules/IntentResolver/aconfig/Android.bp",963,"bf2ffd458b62f4a4ca8e7d78a7d2c22d11fe0cd7d3d1a6cffcf15b95ff15844f"),
    ("packages/modules/IntentResolver/tests/activity/Android.bp",2187,"2942fe1890d84525440a388cf7aa555f36b556638c103eeb85318bae9bed5519"),
    ("packages/modules/IntentResolver/tests/integration/Android.bp",1260,"32f50d89c7e9f15c99c6188e1ba4ffd376d2565a65f9ea9dca8e1287d5241201"),
    ("packages/modules/IntentResolver/tests/shared/Android.bp",1081,"d05c41dacf000b0a55736ad418556e952597084ae3dadcfb890982220642ced3"),
    ("packages/modules/IntentResolver/tests/unit/Android.bp",2060,"0aa64da3942f4f5458620855e2a83471dc9ddd5f4c37b052459c3ffe3dec36c6"),
    ("packages/modules/NetworkStack/common/captiveportal/Android.bp",1018,"80299ec2eafd1224cb7360339f95b017593b319f949ccbbc6d1a3a86da4b1410"),
    ("packages/modules/NeuralNetworks/apex/Android.bp",4051,"a06695b68504c4b5db444c71b06ee1f4657e9e042b1ddff699373667e6159456"),
    ("packages/modules/NeuralNetworks/apex/testing/Android.bp",1193,"a6faaaf928f231e43bde444756eff70db1ea2a68423eddf8a9886a0e13caae47"),
    ("packages/modules/Permission/SafetyCenter/Resources/Android.bp",1897,"4e64f5c836d293edff53b007c118ecf0faac0b17976b703217a5dd1dc248ec32"),
    ("packages/modules/RuntimeI18n/apex/Android.bp",4768,"749c5fbe355c0568e8cf55471cd1604fe68513b87123db06f9335817711a38ef"),
    ("packages/modules/StatsD/tests/Android.bp",1516,"da11d7656867a364b0ac649ee23acc64bd0192f70869973ee4b23588a1dcdc32"),
    ("packages/modules/StatsD/tests/apps/atomstormapp/Android.bp",1290,"cdadb57121cd6b94840ba2ab410e9d36b1d4354947d5bd92ea56399a1b274b96"),
    ("packages/modules/StatsD/tests/apps/statsdapp/Android.bp",2058,"8a6be26ea583ae681625f442578155642698871afec262b5f1af613af5e47c1f"),
    ("packages/modules/StatsD/tests/utils/Android.bp",938,"51fd5290837c4903eb7298e81fb95983842b88cea5daf35b3475604f613acc9d"),
    ("packages/modules/StatsD/tests/utils/tests/Android.bp",1651,"705bc92ff84cec927558f37e5cf45bad74b1289a71a3b606e560230c1d7a9366"),
    ("packages/modules/Uwb/apex/Android.bp",5352,"aa5b34160144fce5039037d9a122d2cdbecd000755c57a037723f8d72acfdacd"),
    ("packages/modules/Uwb/libuwb-uci/Android.bp",128,"e9b99ff32f1f630e0897286c758434a27f0f0cf1bb760e5176d7cbf71f7f3f67"),
    ("packages/modules/Uwb/libuwb-uci/src/Android.bp",10959,"0cbcac2270947f549fc7fb89f4925034c473fedc88bf1d16c8673d3545aa9840"),
    ("packages/modules/Uwb/ranging/rtt_backend/Android.bp",1352,"9b98f92f7164a9384e84d2b83adc57ebb9cc353ad890b9822e775b44f47611a0"),
    ("packages/modules/Uwb/ranging/rtt_backend/tests/Android.bp",1799,"c83c659f257ef375fc7ddb4a74ad2e9f5fcf31e05c023a10acd6d14add40c35a"),
    ("packages/modules/Uwb/ranging/service/Android.bp",4930,"34a3b6d12fcd40ded115a9fcc9f80fa811652c2db4a79451839f3a7ed7a678d8"),
    ("packages/modules/Uwb/ranging/service/tests/Android.bp",1560,"27e2b3d038ccd7260c93c5f4a9cffa54edeb4988ecf5716124472f51f3da7d76"),
    ("packages/modules/Uwb/ranging/uwb_backend/Android.bp",1607,"cde6d5b3f82cfd3c671554e6fecdc8a56ee45bcf4b08cd1b78568b799d39b237"),
    ("packages/modules/Uwb/ranging/uwb_backend/tests/Android.bp",1867,"c84b91139ee30160e820d8e667a306828473c80eadd53668ac516ca245e8eb07"),
    ("packages/modules/Uwb/service/uci/Android.bp",134,"7083bbdaadfe179c0f32c0efc10459738976561ffd4a75cb6817f4bf72ef14ce"),
    ("packages/modules/Uwb/service/uci/jni/Android.bp",1873,"a46484a095bfd94cca8149eae9f7b08b70430e8f983cae8aaa8580684af3c6f8"),
    ("packages/modules/Virtualization/guest/pvmfw/Android.bp",19471,"998e3f4858d3e0adaf6e95c01bef7fe5ff6dcc07c166ec7db1849311f947ae76"),
    ("packages/modules/Virtualization/guest/pvmfw/avb/Android.bp",8531,"7d88f449782cbc6a3fc53ed454b46efe8ec76360b3fe27ab3f563b423c57692a"),
    ("packages/modules/Virtualization/guest/pvmfw/avb/fuzz/Android.bp",1359,"0f801ebe467c90b6ee689a1a4547310689714da5445f3d4d756f48bf7194aad9"),
    ("packages/modules/Virtualization/guest/trusty/test_vm/Android.bp",3888,"9875e1b5610b8d11477ebd567c1b9c57e579c1f7ee8e5f911c1251e3ff9cb45e"),
    ("packages/modules/Virtualization/guest/trusty/test_vm/vm/Android.bp",3424,"35ea190e9dbc2b45c2fb97eaaae207ddf78e6459fe3e717a031a089f557a5d10"),
    ("packages/modules/Virtualization/tests/ComposBenchmarkApp/Android.bp",580,"207abfc076066fc8bd6480c814267ce26528bb2c8b5d9487ba2849a326a0fd51"),
    ("packages/modules/Virtualization/tests/ComposHostTestCases/Android.bp",664,"4de8e48c1aaa2e2d51db8b5acb5460adb53661cd71d1c3f06872690a51197c44"),
    ("packages/modules/Virtualization/tests/Terminal/Android.bp",677,"2ed99a233a2e54a876e8c337c0f963d0ec29f7e43326885ccc6bb621d2ca5831"),
    ("packages/modules/Virtualization/tests/TrustyVmBenchmarks/Android.bp",1533,"7f1b74716e2efdd224bd686ffd959bb1d2618c45e90785f573526895daf0a2ec"),
    ("packages/modules/Virtualization/tests/aidl/Android.bp",487,"ee2135ed5a56f770606ad980756de54023c838f3fbdf150f694433572d353e5c"),
    ("packages/modules/Virtualization/tests/authfs/Android.bp",1493,"226bec1468a82c4fff3bad47071ac7a4b050ce929ebb89478e9221eb4b5ea970"),
    ("packages/modules/Virtualization/tests/authfs/benchmarks/Android.bp",1385,"37688956063faa3ee1fa51c9cd98f625da6c8d56ca4d810586ff9b23c04c369c"),
    ("packages/modules/Virtualization/tests/authfs/common/Android.bp",1093,"d9b6cf40d5d20c93b2522502d2b3fce675c9aa443d22494846dedaf275019571"),
    ("packages/modules/Virtualization/tests/authfs/hosttests/Android.bp",563,"dd3f63ea074e6839121b8f9640430c015d58e2753d1cc87a3804acd4be012c0f"),
    ("packages/modules/Virtualization/tests/backcompat_test/Android.bp",786,"1fdd23a34da2cbadb44ae8d2f9be94147da4eb05c1097cf5033f306435e2982e"),
    ("packages/modules/Virtualization/tests/benchmark/Android.bp",1347,"9759ec28629fb56abed782d6a449a87ed56c89e4ab3c00684a019de24290f53a"),
    ("packages/modules/Virtualization/tests/benchmark/src/jni/Android.bp",264,"5e1728ae68e371c02e1d0e05574ff2ba0642ccb54a9d27f39558b9489c9d5cd7"),
    ("packages/modules/Virtualization/tests/benchmark_hostside/Android.bp",505,"88722b0249f7c7d3fe1d89979c32898ef17270399bc4d6eb5cfa07c61003d2ed"),
    ("packages/modules/Virtualization/tests/com.android.microdroid.test.tenant0/Android.bp",1653,"5f02dec434d368db2c2cd3f2843e3a0a440a26d6261b0898aaed13c34441cecc"),
    ("packages/modules/Virtualization/tests/dtcompare/Android.bp",407,"d4413879918b6718277524b7327ffc74bf2d79f241299f90807a650cf73c6ed0"),
    ("packages/modules/Virtualization/tests/early_vm_test/Android.bp",1329,"d10624b3642a2db19b80f754050a1d21a0ce2a4302c702ca0ac99a1faee17192"),
    ("packages/modules/Virtualization/tests/encrypted_assets/Android.bp",1711,"44c12a50a6811cbda89d66da93cc9163f4f3ba5bc379dae4827c4f54807ba96d"),
    ("packages/modules/Virtualization/tests/hostside/Android.bp",3564,"95d6fbe9b1b0dfd9b3f6b0d86137e2794fe199d7c03f9581a3ca586748e5c61d"),
    ("packages/modules/Virtualization/tests/hypervisor_neverallow_test/Android.bp",309,"4fdf55ee362f354d487383c9fc1bb253302d76dc777455582777849f21d3cde7"),
    ("packages/modules/Virtualization/tests/libs/common/Android.bp",300,"47e659304ca4540984968723f4554c0a3969d979405e2ab8316b27577cd79393"),
    ("packages/modules/Virtualization/tests/libs/device/Android.bp",553,"ebc5a02f96eacb70d1d0efd5b19d931bcf0bffbad2c327a19a1e10d7ece73588"),
    ("packages/modules/Virtualization/tests/libs/host/Android.bp",350,"393cbb41b7b25b35a06b582142bee92c65bb6096f654504ab05884afeda02ef7"),
    ("packages/modules/Virtualization/tests/libs/libdts/Android.bp",378,"7f9b69be070cde0c23922c1942522962770d362f4e94789d52067bacc8b683da"),
    ("packages/modules/Virtualization/tests/libs/preparer/Android.bp",381,"eb44d6a46adb31117c8c56828fa5fd04d4a8ac27b557a8bd6e92c17833ce2ea9"),
    ("packages/modules/Virtualization/tests/no_avf/Android.bp",522,"613b2d560072bd3395f95d452cf4d44c0cd7c9028ac6f39ac6468a4aa61fcc51"),
    ("packages/modules/Virtualization/tests/old_images_avf_test/Android.bp",1236,"2ed87b8520b434d91fcaa7a6b03b9fb3c7acac089f107a8830858627a825e0d5"),
    ("packages/modules/Virtualization/tests/pvmfw/Android.bp",947,"c3d0dc5ec98c27265e9afe103bf3e845cdd53dc4de0577fd4f6c598bebaea6c9"),
    ("packages/modules/Virtualization/tests/pvmfw/assets/Android.bp",1251,"234c68d14bcf09796f01a63e9c577b7cbcc10e188587656aece1f25c9fd50582"),
    ("packages/modules/Virtualization/tests/pvmfw/libs/Android.bp",237,"52c1d8e354a1177d70c2281a5dc66d5fb9f8b084e91c2625e85f7252f303f588"),
    ("packages/modules/Virtualization/tests/pvmfw/tools/Android.bp",225,"7ff4ad0658d4903e58e7c89c5ec2c3dc51f0a96241ec1923aa71f2ed56e46971"),
    ("packages/modules/Virtualization/tests/testapk/Android.bp",12292,"4d8b81e1ff5f831ac60ff0a1e372256104086e0a4faee5c108d4229f56bf791d"),
    ("packages/modules/Virtualization/tests/testapk_no_perm/Android.bp",652,"b46e693c788ea9a5178c7362500331f350946959de1740ceb2f4a28f16861f26"),
    ("packages/modules/Virtualization/tests/vendor_images/Android.bp",867,"7620abea13cc0d91670900aaf7ad1d1cded6cb0f60b3a310e7182c1ae58afb17"),
    ("packages/modules/Virtualization/tests/vm_accessor/accessor/Android.bp",763,"8a1c4fdd2ab058f3da68c2f640c2434f7bb561fdd0d8f4bea12ca9a564d168e5"),
    ("packages/modules/Virtualization/tests/vm_accessor/accessor_vm/Android.bp",831,"59934fedd6b05521c759e1d4e8d8e32d1f505e747fda69120f121ced19749dee"),
    ("packages/modules/Virtualization/tests/vm_accessor/aidl/Android.bp",414,"cccaf8c4d5aac7b4b656661d0599a278c2918a207c8184edb0a737bcd1190d80"),
    ("packages/modules/Virtualization/tests/vm_accessor/apex/Android.bp",1531,"8726ff3ebefbcfc8b6602d673a77e1df7ea9a0f48efdfd347a747b10c0a3eaed"),
    ("packages/modules/Virtualization/tests/vm_accessor/test/Android.bp",1139,"5732d999e51a7584e603a7a8ebef029d3c8436807b6c62058b724de9f7675e46"),
    ("packages/modules/Virtualization/tests/vm_attestation/Android.bp",2029,"7cc8802b94399090dea2e71fff0df1599556ff5a12eb8b8eebf28af4c5cd34c7"),
    ("packages/modules/Virtualization/tests/vm_attestation/aidl/Android.bp",413,"d7a948437b89b2804f838a925cc3fa3392b913d2181e934b48ee11abfd8c98c2"),
    ("packages/modules/Virtualization/tests/vm_multitenancy/Android.bp",2751,"605a2bd84d27d11277760145587b325333d96670fd8783c40931af706bd30693"),
    ("packages/modules/Virtualization/tests/vmbase_example/Android.bp",681,"f188f9ac2eff825cb6351573ec5566fb3a2a0c3cf37a931b05be72987930237e"),
    ("packages/modules/Virtualization/tests/vmbase_test_vm/Android.bp",1797,"3807f3ce492353e11cca3a3143baa74df370b95daf1d0d861333920049564297"),
    ("packages/modules/Virtualization/tests/vmbase_test_vm/messages/Android.bp",442,"26c12177938d5d1666a014f19876e0811bee916eb5adbce0c18f523413769ee6"),
    ("packages/modules/Virtualization/tests/vmshareapp/Android.bp",728,"735643c6588cc927b8b0be22f666a5a8b2f1b2b6046b89523aeea58552cd397a"),
    ("packages/modules/Virtualization/tests/vmshareapp/aidl/Android.bp",537,"02c85b967ccc6fb8bcdb48509ad3ab1001ee89c63762d28e740fdca5beb625a0"),
    ("packages/modules/Virtualization/tests/vts/Android.bp",1600,"9d1efb1166d1b3e5df9927b0ad175ab48769f6003f80ca02c9f1f5aa15536ef5"),
    ("packages/modules/Wifi/OsuLogin/Android.bp",1051,"0925563347794a6ef8147fc0096ee35626c13d0be1bbb8ae96f3b32798e483ce"),
    ("packages/modules/Wifi/WifiDialog/Android.bp",1772,"19a37f405d0432afa10a702ac69d32153d2bf58ae5b83f63b2c8cfb58a2e0ec8"),
    ("packages/modules/Wifi/aidl/mainline_supplicant/Android.bp",1721,"ee11a59275785d4e3002ec9a9b8196ff41e32dcc20dc621390c26bf44377a0b9"),
    ("packages/modules/Wifi/apex/Android.bp",5872,"8fafaab04b947aa863f5ed1789123ccc70c116aa37b856137b44780eaaaa2528"),
    ("packages/modules/Wifi/jni/Android.bp",322,"f77fcf3f05834ba1391db179e63eb31daac5ea5dfe96c59acecf5533f4c341a1"),
    ("packages/modules/Wifi/service/Android.bp",6803,"98cf577988126ce03ac9c87cca319ddb952fa9850ed235dec3b802a8e13745d5"),
    ("packages/modules/Wifi/service/ServiceWifiResources/Android.bp",1622,"5f27887fe78cdd31c7af5d9675adda6b1ea757e494474cc085e23b25c61de6a7"),
    ("packages/modules/Wifi/service/coex-table-parser/Android.bp",891,"9f6209eae52ed78c2f962ec0dc3fbe18cf31f53735c2cb3b12b4ce11cf3a3d15"),
    ("packages/modules/Wifi/service/proto/Android.bp",1536,"f7e974f19c94b1a7fb1fd2aa882d84fd690b528f4205ddc94e063e14706f43cc"),
    ("packages/modules/Wifi/service/tests/mts/Android.bp",1911,"a05080f909c0a6af000b9eb646acdac16eb0b96989d665b85ddb134ce7971be7"),
    ("packages/modules/Wifi/service/tests/wifitests/Android.bp",90207,"ed879edb68b75244d0386801ac6ae79900a000d3dfee444a103a98241ada0d1b"),
    ("packages/modules/Wifi/service/tests/wifitests/apex/Android.bp",1216,"9eeb638ddc5dc4e5fa6f7987221ddade657feaa9ed03d82560bc85225e44673c"),
    ("packages/modules/adb/apex/Android.bp",1871,"3e421fe53d9cbce1b072b005577b530dc858adb1366999b8e20573ad07ab6c20"),
    ("packages/modules/common/build/Android.bp",2230,"e75d395b889514a0d2a76a9693037171b8367661e60c4c34472dfc70aefcfb81"),
    ("packages/modules/common/build/mainline_modules_sdks_test_data/google_wifi_for_r_Android.bp",1594,"ea33b8aa8a27977380d4b66de0ecfb1238f80d42f0ce66e17b4734d79db7f865"),
    ("packages/modules/common/build/mainline_modules_sdks_test_data/ipsec_for_r_Android.bp",1665,"c16e04495d91af37e43243f6053459bd9a95b90c1b8086c20e18bcec5de02f54"),
    ("packages/modules/common/build/mainline_modules_sdks_test_data/tethering_for_r_Android.bp",1616,"36c87711cc2455a48b0af6a86de06968a6ffe1976f0045cb7c6b8bd8ebeb6631"),
    ("packages/providers/BookmarkProvider/Android.bp",784,"855f4a8b47692a1331b792821ec30c7cb12f0aab245e99dbf2194cd80e06fa23"),
    ("packages/providers/CallLogProvider/Android.bp",1196,"58d011c716f1ffe49b462973c502cbc776b466ed78148209dc30bcdb20d5d6a3"),
    ("packages/providers/CallLogProvider/tests/Android.bp",715,"69596b0cb952fb5d289b13c1bc0b526139b15743324da39cc5685ff457407bd3"),
    ("packages/providers/ContactsKeysProvider/Android.bp",1390,"7003019895854cefe7af159aaf3ab745d06f14af62b4789905590d7a45aba885"),
    ("packages/providers/ContactsKeysProvider/tests/Android.bp",848,"5a05104809d85d06f3486cddc7d392b9c34b20b7e86c8bae2bef1334462d71de"),
    ("packages/providers/ContactsProvider/Android.bp",2592,"837db07050a2b077fea6baacc5b52fc982daa8c48770e0f584abc846b29da7cc"),
    ("packages/providers/ContactsProvider/test_common/Android.bp",944,"3b0d98bce3cfe8e87efa5112da691b4ba9107013c21443807475bd3f5160fb0b"),
    ("packages/providers/ContactsProvider/tests/Android.bp",3119,"f2c2c8c95553d37351911a3c77ffb239e5cd0bf188dd76fcff9aa2edb41f9c67"),
    ("packages/providers/DownloadProvider/Android.bp",1850,"857b7757e5af9c91ca5611959b3a868d58dcf7f41c5206293602408d19c70511"),
    ("packages/providers/DownloadProvider/flags/Android.bp",994,"9fc36e4ade240cf8b7343c472fbc92430d25687a6491db6f27674b2e1e978eeb"),
    ("packages/providers/DownloadProvider/tests/Android.bp",1384,"270dd28e1050fb9d9652e4a1354ce972529d62793ef3fbbf31d8b0f16b6e4a75"),
    ("packages/providers/DownloadProvider/ui/Android.bp",1016,"03fefc161b9209b464a30ef1a877c33ac5402f00320bae2ce87e1ce434da4971"),
    ("packages/providers/PartnerBookmarksProvider/Android.bp",911,"55a0c3f3f43e32897eae34d3697955bf603d05edc4c5519ee2dce15d6e3cfd63"),
    ("packages/providers/PartnerBookmarksProvider/tests/Android.bp",1046,"34a1535cbac4ff058077554fd6eb3f56412207e73d6689894df52e596f21b06b"),
    ("packages/providers/UserDictionaryProvider/Android.bp",282,"bb5ad931abe223ed938a0664fa2c05402b5b6de094f826dd2a1987ac34ea14a9"),
    ("packages/screensavers/Basic/Android.bp",219,"5370b6debef4473bba8283317827a84aa5c33945e297caa8b6280d771bceab44"),
    ("packages/services/AlternativeNetworkAccess/Android.bp",1355,"d4f79c44b4c9ee2679059e30220fedbc7bffdd88638d2c30b34668c424e57b58"),
    ("packages/services/AlternativeNetworkAccess/tests/Android.bp",1333,"05e29c7853a97c85427eafb7494fb5fc26872e4aaf190f1c926666db826fa084"),
    ("packages/services/BuiltInPrintService/Android.bp",3290,"825acd4b757071a143436c16e582d9ccb7843ba20284eb72891fb32b02293768"),
    ("packages/services/BuiltInPrintService/flags/Android.bp",1081,"b0d6049941cf202d47f3e384ba1f8eaa8426e944830f7f90b2569ec99d165585"),
    ("packages/services/BuiltInPrintService/jni/Android.bp",2244,"6a19250f42fb20ca8ee107aa60cba712e4b5519e7b5aff4146d2731d40c2aa88"),
    ("packages/services/DeviceAsWebcam/impl/Android.bp",705,"a46cc43717347e53e9a3291cc9dfd5fcdebb497697524612d3ad088ad99eb393"),
    ("packages/services/DeviceAsWebcam/interface/Android.bp",488,"e1cb78a8fff2c0a78873134ba050dcc396940cb6e2a592031481ee31f7fa0b56"),
    ("packages/services/DeviceAsWebcam/interface/jni/Android.bp",756,"29fe565c73fa668e7fe070ed93b240f93167ae1ce15f15851c4e9eb612e5c922"),
    ("packages/services/Mms/Android.bp",1612,"124a899d0adf8b9b8ad1cc3591723b8657d2e4a9044b626eb18f389032dd778d"),
    ("packages/services/Mms/proto/Android.bp",902,"c3a1abfab6019d1f741fc7b96e413cdd1623a79d110e685bebbdb24a391f44d7"),
    ("packages/services/Mms/tests/robotests/Android.bp",576,"c422e1261773136ca0a8ae2ae6145e9f7b7291dab2b0eeaa320eeb86eea13b1e"),
    ("packages/services/Mms/tests/unittests/Android.bp",811,"3150555abcba28407556ad21110a8d6b43fccaa191e698d60bf0c0930daaf218"),
    ("packages/wallpapers/LivePicker/Android.bp",1858,"a578af91176e86e6f1d151f254edb81e11ebcfaea8299ff94f5d2613857b1a40"),
    ("platform_testing/libraries/androidbuildinternal/Android.bp",856,"06c2638f4fe5f51ea2c9bd82e7c82c90ab4a97d9e219e5b037bc11010af62db6"),
    ("prebuilts/android-emulator/Android.bp",818,"2a244fdf59510a43ed80de87e150c1b45325aa4ca8a2048fb3edcad8daf15d37"),
    ("prebuilts/android-emulator/trusty-x86_64/Android.bp",1051,"d80230f95c23265844ac5f3f3dd2b724a508a2c84ae19cc3fb86a0dfaeaaff60"),
    ("prebuilts/misc/common/devtools-annotations/Android.bp",183,"33bf1b2d852ab172db637e58d345e103d290f5d6289fa8819b7235d241f29039"),
    ("prebuilts/tools/common/google-api-services-compute/Android.bp",1336,"d3ec2b6773d95d48e52dc145537ac4b05445764f0dc6adcf225e1c3fd7565453"),
    ("prebuilts/tools/common/google-api-services-storage/1.24.1/Android.bp",1467,"dede9d88e7ee744e9d1d7a1b8c8aeb8ddad857cd23d684be035e70f1d4431d27"),
    ("system/apex/patchlevel/Android.bp",791,"c4fc1821a78ce290e1db63d1c9018f21187175350dc867591bdbb9bd7202f02b"),
    ("system/ca-certificates/Android.bp",1205,"ca558680ec36413b642bfa264d75c9a1ef028cb2606e999c428cf250c2eef54a"),
    ("system/ca-certificates/wfa_certs/Android.bp",1352,"375c9d0aa2b760f2ed9e1fb61f1cb5073029f33d698e1a32916c576a8bbc51f9"),
    ("system/dmesgd/Android.bp",1467,"22576b9cf0458cb7b7a9b6a3b9b3b304a3710bd48c9afe21d37c12e954a7c50a"),
    ("system/extras/cppreopts/Android.bp",1049,"1bd48a1e331edf5f6d65b4c9f2b89f3d4198c5917e832565b5d6563690c380bf"),
    ("system/extras/kcmdlinectrl/Android.bp",1248,"5154ddef53692ab22cea4c07ec7c7a28e03eb6a05cb4164cf4f04bb827614dd7"),
    ("system/extras/kcmdlinemodprobe/Android.bp",1812,"95b8a71757525aa1fefccb281543758c873a7ff9c1b84255a719156378ea8063"),
    ("system/extras/mtectrl/Android.bp",1361,"fd08b3e4b7cd6df85c5b7844669e45276a5067f312ece7ec322176a20046f953"),
    ("system/extras/pinner/Android.bp",1296,"48fda564fa07e542c5baa61c09bc031745b31ac7863d466dfe8625ef772fbe9c"),
    ("system/extras/pinner/tests/Android.bp",1967,"35f2d86d741f3c1e3859f4cc60f98be45f70d97852cd9e996d75689d746351be"),
    ("system/extras/preopt2cachename/Android.bp",927,"4eefe1b8730a33250adc8c8782b5cd04bdd591242a9350188000e726fc74014f"),
    ("system/extras/tests/Android.bp",991,"b7de3b1362c9ebcf0229faf821510433e67079901c2a49b28284fbe5e85cda08"),
    ("system/extras/tests/binder/benchmarks/Android.bp",1319,"2fa446b0fc6f301bccc8decc9178ec138d2e8e0be87c07484741d84a28f970e7"),
    ("system/extras/tests/cpueater/Android.bp",1407,"dffb633c084aa6ad249e4cc2d3f56d4d29c38cf9c56dcd5023795747a067bf7b"),
    ("system/extras/tests/crypto/Android.bp",564,"6ee1fbb65abc16671c4efd6ef758a5927840cba1c4e1dd4df025ae9cafb584ec"),
    ("system/extras/tests/directiotest/Android.bp",474,"56ae099207404af24d1ad4be49bb0c22d3ed4474df73cf460ddedd60f896ac40"),
    ("system/extras/tests/ext4/Android.bp",1205,"2a66252989df11ad186b45c584e6bcd5732a414ac222bf8db457fee4caede87c"),
    ("system/extras/tests/framebuffer/Android.bp",751,"cf02a5c02d85a68cf1cb752630c4e0595cc29efc8d52417db0705f268e2113c6"),
    ("system/extras/tests/fstest/Android.bp",1359,"288af4d8d2a952e846d70adcb7f795c23c6c47c5b1a30a5c2178f56ffaac0235"),
    ("system/extras/tests/icachetest/Android.bp",674,"a6f58e110766d8a24fcbd96dd9169c3452b22ffe52547f247d0e69b5a59c725c"),
    ("system/extras/tests/kernel.config/Android.bp",2052,"f440e6a02fa063481a505e7f8c693f2e813dbe8a98272eac7c21e55639618eb1"),
    ("system/extras/tests/lib/Android.bp",363,"3cf712225bfa4813ff886f3253ca0f8196b4d75a75e8f53d061e68f2c08ca22c"),
    ("system/extras/tests/lib/testUtil/Android.bp",1202,"abf76a4619148c8e9b82b3538791a7d96544446420fe24d872de969ab9c6818b"),
    ("system/extras/tests/pagingtest/Android.bp",1183,"3f911483338e86aced42edd2db004d3f2587017a090fd3cbd932060fcefd5a1f"),
    ("system/extras/tests/pftest/Android.bp",629,"2cd576f02002fecf1acd307a3f20fc7e77eddc2f1b210a8d68f5e455f17af071"),
    ("system/extras/tests/schedtest/Android.bp",501,"8e117cb3b6585874876b120f3d2c47d6f74b4454fdc678f948d8b372df763c51"),
    ("system/extras/tests/storage/Android.bp",643,"e2def42e9569b1804cc3ab253feba0929762d0808409db1a52f2373e21d08d5e"),
    ("system/extras/tests/suspend_stress/Android.bp",591,"962fb1eecc838f70c271c2c86f2ae65cbe1423b6b4d2bdf2476be202c03584dd"),
    ("system/extras/tests/tcp_nuke_addr/Android.bp",541,"44f195c17984627a3e37f8804b07fcbc847d05115105f0b882406091e5db39cb"),
    ("system/extras/tests/timetest/Android.bp",857,"837270af5dad403e05c462148431897cf37cf713eeca2ca49b307d4312992399"),
    ("system/extras/tests/uevents/Android.bp",529,"1208adb50af02cb11bab6a5566f60a721e3ab55c25549b0ab8215d3e65c50535"),
    ("system/hwservicemanager/Android.bp",3467,"30c544744e49332c150755c32669656138eca93169cdd5e4f80aa493f44a1ed2"),
    ("system/memory/guardian/Android.bp",2041,"c239de4098a9252767ad9600139817fbdb25c5b2dd6a1c7b46d5a3043e3d0fc6"),
    ("system/netd/tests/Android.bp",3588,"c59dddf32997b3612c6ed8d33d38fef60e1890bb92f9604c9ef39481ba9c1e86"),
    ("system/netd/tests/benchmarks/Android.bp",1557,"03956b689b323f84ebb664daf2c8f597b11048a5899eb7d1ef97c79fcdacee15"),
    ("system/security/keystore-engine/Android.bp",2462,"f4162419bac7def60fe28925f970a9b15347ef0c3b27d6e7d6e9e196cdc90793"),
    ("system/server_configurable_flags/disaster_recovery/Android.bp",474,"e7ce694c9400cdf8f60d5cab78e85949f371eef8ad6a8f61ef16bb10edd4a5c5"),
    ("system/zygote/zygote-core/Android.bp",1842,"fea50c0fc6255f69e124b60d3bdb7483b0fd17d85db920e8e22adbcc8ddb95cd"),
    ("system/zygote/zygote/Android.bp",4244,"545655e86f4ce1259e6c67f9a9f5dbe741043ea18ac66edb47a5f28f72e1e6ef"),
    ("system/zygote/zygote/libs/statslog/Android.bp",1399,"0409f4789964d1d8005703effe0d55dd3010f76b3deb6fb9a5821f4ff4ecf43d"),
    ("tools/security/remote_provisioning/hwtrust/Android.bp",2692,"993f6320e25a8a4bfb875d3fa6d4ca8055df2670169d11fd5c3815092074c786"),
    ("tools/security/remote_provisioning/hwtrust/cxxbridge/Android.bp",1206,"a8483f181ff56715191e5ffe95f2fa1f437428a767fb91cdd44da570973f17d0"),
    ("trusty/device/desktop/Android.bp",3013,"7bbe1759b3bebc7caae410569f863c2022bcf06adcd83c971087d6b720feaec7"),
    ("trusty/host/common/scripts/metrics_atoms_protoc_plugin/Android.bp",1049,"8b86aa5c9847c307f6b05352bc51c31e179e8d8e8328bcb895027c712de79b33"),
    ("trusty/host/common/scripts/replace_ramdisk_modules/Android.bp",865,"7388f7531b51df27a2511bba2d0560cd97e1bc1f0e3799f893ac897a96f24041"),
    ("trusty/user/desktop/Android.bp",136,"faceec5b43e6982e47df2898070560f28e9f12290307b58414d263186fdfd20d"),
    ("trusty/user/desktop/lib/desktop_trusty_build_params/Android.bp",1296,"eeb97b41b9bfe1cd72654add69c7f81738e505f248961c844de7b2477af1c9fa"),
    ("trusty/vendor/google/aosp/Android.bp",142,"7b700365e43af21e111cdb8f4709498dd5e2ebbd3f7c3df0f0fd4ac1e7ff3224"),
    ("trusty/vendor/google/aosp/scripts/Android.bp",23969,"731c6b6360ce6944b99e8fa5eafa15e9ea5c091a899001a1fa15f3d40016c6da"),
];

fn validate_audio_generic535_original_inputs(source:&Path,mode:SoongDependencyMode)->Result<()> {
    if mode!=SoongDependencyMode::AudioApexTargetClosure {return Ok(());}
    for (relative,bytes,digest)in AUDIO_GENERIC535_ORIGINAL_BPS {
        let mut path=source.to_path_buf();
        for component in Path::new(relative).components() {
            path.push(component.as_os_str());let metadata=fs::symlink_metadata(&path)?;
            if metadata.file_type().is_symlink(){return fail(format!("audio generic original input alias: {relative}"));}
        }
        let metadata=fs::symlink_metadata(&path)?;
        if !metadata.file_type().is_file()||metadata.len()!=*bytes||hash(&path)?!=*digest {
            return fail(format!("audio generic complete original Blueprint changed: {relative}"));
        }
    }
    Ok(())
}

const AUDIO_DEPMOD536_ORIGINAL_INPUTS: &[(&str,u64,&str)] = &[
    ("build/blueprint/bootstrap/bootstrap.go",30476,"fa24dd004bc67346f43d6f9291e5f1f9d5462e8ef1fd39f73f76b0c6d629f4c2"),
    ("build/blueprint/deptools/Android.bp",288,"c5357ec394729caedffbe7cdd0f5a6135afeb277bfa77d133811d487cd612ba1"),
    ("build/blueprint/pathtools/Android.bp",537,"4fb6d6e9a51c7570eeaa1a3a4a41eb935aa62b77ac8da2424ca83e2fa716df79"),
    ("build/soong/Android.bp",8949,"ba2b7cf0320706b039268d5866eaeb1570d4c9f59f111969d7a3006e9fda4dd7"),
    ("build/soong/android/base_module_context.go",23635,"465df61dd2ea0071700eeae0ddb756853de5badcc781ad003375e1e611906b81"),
    ("build/soong/android/config.go",90413,"275ec92b707f44fe9c1173b9bf434821a50782841ed80e527d256feddb7c809c"),
    ("build/soong/android/module.go",141225,"97da5c233519c471ed974a6d24d9dee55f2da3cf80be9083d8b6d7ba28417280"),
    ("build/soong/android/module_context.go",42658,"dcef5da43b8efd17e49ffc041b83b818413e87ec078bc285be63c6d4cf1bf29a"),
    ("build/soong/android/mutator.go",25131,"46aa785dec9f2e09536b0d6bf4f6ae30185409dd0edfdbc467303fd075a24588"),
    ("build/soong/android/prebuilt_build_tool.go",4118,"3d04e2ae838be029b05f6cecf889fb7a78e852b7118504903f753756f67fe9ef"),
    ("build/soong/android/register.go",10855,"cd9e190e1eeb25dcd9ac4ee1877dd6bbb972a41aeb641d5db99731f81ca62bea"),
    ("build/soong/android/visibility.go",22053,"1d0a29735cc0a7fce16d739392685507594adbf2e06589c87b02ad55bec51d71"),
    ("build/soong/cmd/merge_zips/Android.bp",953,"f3449989d527b133df7aa793626596822d122609b4394579d2ae5c763a24d18f"),
    ("build/soong/cmd/merge_zips/merge_zips.go",20876,"b8d6c9b19766ab39c8c18e80ecf0d8a473cfbfa07a4a12bccdc34119f1dcd175"),
    ("build/soong/cmd/zipsync/Android.bp",847,"3923b75e33c0b1bc506de86dfab5d9f0fca0dbcb436284042b30f4c10c865dcf"),
    ("build/soong/cmd/zipsync/zipsync.go",4360,"875b610391689ebc9d4aabe00e4224585f1c2146648c64adc309be09c50cbb01"),
    ("build/soong/golang/golang.go",5809,"77135fe3097bda4ed06be6b99f379835ec41e8a0c8065dfb2f3d001714fd8a27"),
    ("build/soong/jar/Android.bp",918,"193b9b81eee10d52d07fa63414b97080c1aa83f8bec38d43f6aeda543b50f5ce"),
    ("build/soong/kernel/Android.bp",1114,"e1eb2b7f8010c7327ad88cae2395435f21508ae951428bfdc4c5ef9d71f2e368"),
    ("build/soong/kernel/common/Android.bp",865,"b951bc82efac3cafc0e631f48d9b71cc5ebb68fe94952520a43a2c922b54d58a"),
    ("build/soong/kernel/common/prebuilt_kernel_modules_common.go",3173,"06c5753c64d081742f3f56e2a17fa894a055c193430f5541d363a29b0e77033e"),
    ("build/soong/kernel/kernel_modules_builder/Android.bp",846,"ee945e1e75c347efa63494ab3607ea210e91380b56eec3e7c5bcde3a050960a8"),
    ("build/soong/kernel/kernel_modules_builder/kernel_modules_builder.go",13394,"dc0f6ba23d8d2f96b26536cd92ac850dc19f3ceb1d40441ab7240257d799300a"),
    ("build/soong/kernel/prebuilt_kernel_modules.go",11373,"b4b964f547a6276afb45ba1eb01856a4c6eab7d5cb1b7bbc827cbb565c05c17e"),
    ("build/soong/kernel/prebuilt_kernel_modules_test.go",2171,"dfc99268718001488411a2c8ca754a3e634035749ed1de8947c2dcc5333744aa"),
    ("build/soong/response/Android.bp",330,"cd0f46ce4dd4b1224c87902f77a5616b23e4165b390b9492da29eb5427eaed27"),
    ("build/soong/root.bp",225,"faaf34f6e465d8a792f73023f73283182842c63934d4b865ad0bc4eb1957cc06"),
    ("build/soong/third_party/zip/Android.bp",1259,"9ab17410618bbd0db22b4cf17bdfd0a61835a280de0e1c3efe6f58fba7365fcc"),
    ("build/soong/zip/Android.bp",1017,"bd5c80505c1ebe20ced309f572524f46a6408077a6fcf82111a14c29023370b6"),
    ("build/soong/zip/cmd/Android.bp",896,"29bf22bee379d24e83ac9f6943a8d950cf3ea63ff16d1454bfd48d463a359b1d"),
    ("build/soong/zip/cmd/main.go",7044,"1022385814486dd014e76de6b1cc7a15a304e1e584206816cc4edfbfd3094df1"),
    ("external/kmod/.gitignore",285,"f45163635aff80989d9fde27de0a029bab6f69db3bdfa4e9babd6c36d96c018e"),
    ("external/kmod/Android.bp",3297,"d9a16f20f17f040c22ae0e2d66b95a8a96fd86f111b6969df51cd4a2626694f4"),
    ("external/kmod/BUILD.bazel",2571,"76d925e2115e7d2683f30e34a15be5684015f6184166273208f5908ff7c55546"),
    ("external/kmod/CODING-STYLE",2386,"1b67c96f8e9cff02f75d63686e4134f2944dcd9fd5d861b609f684bb60ef5439"),
    ("external/kmod/COPYING",26432,"6095e9ffa777dd22839f7801aa845b31c9ed07f3d6bf8a26dc5d2dec8ccc0ef3"),
    ("external/kmod/METADATA",587,"ba5a4bcdb4268599582de0f1fbcf19ca9a452eb31f699bd14b037476f6391675"),
    ("external/kmod/MODULE_LICENSE_LGPL",0,"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    ("external/kmod/Makefile.am",13885,"2ee8d1159fd753ae36ef13e712091d46ad5e6752579969f02fce8e816d4b9239"),
    ("external/kmod/NEWS",32194,"8da6ec00df9181a5ae8ce29bda919ff8a5633838cb8106716ca1c9d2f9505628"),
    ("external/kmod/NOTICE",26432,"6095e9ffa777dd22839f7801aa845b31c9ed07f3d6bf8a26dc5d2dec8ccc0ef3"),
    ("external/kmod/OWNERS",46,"a8a956399e1ed1f7b7cd77d8312e19bb9a8d8dc39d77651894b67e1659073acc"),
    ("external/kmod/README.md",3784,"ac98e1abe2b727590233094637973b53e5e51a45248f1ec413c2daff4ac9fc07"),
    ("external/kmod/TODO",2185,"ea74f6acb490e40087250604f0d64989570a897b497d9b0365bf682a3833e6f7"),
    ("external/kmod/android/port.h",2336,"d6f1f9c0f770fc301de4051c17ab9db2245da9832b06db865a1cbaa2d0747a8e"),
    ("external/kmod/autogen.sh",1794,"e8fe709a45ddd593ee8fe6290c891e327ccb535d9dbc942f46f6053584f7451f"),
    ("external/kmod/config.h",6962,"012ffd1885c7f8a4249b81fb27c81147f507aecf210d8ecd7c3dc28ddcea29ca"),
    ("external/kmod/config.h.in",6515,"aeb3787e95a0f6b3d6463310a9102742513c801e366f3e3fe36d8f9cd65aa287"),
    ("external/kmod/configure.ac",11562,"268d38075beac96d8c0e8413cef91c78d2847b6212512c6c962aa0a8bbc5e662"),
    ("external/kmod/libkmod/.gitignore",45,"640f6f672fedb18adcc80c1aba487341076b1cfc5566366dc11244af76859868"),
    ("external/kmod/libkmod/COPYING",26432,"6095e9ffa777dd22839f7801aa845b31c9ed07f3d6bf8a26dc5d2dec8ccc0ef3"),
    ("external/kmod/libkmod/Makefile",332,"85eb6a17cfb939aa991dbb06d906d62095966b9775be2e774d08df62b34ed2f1"),
    ("external/kmod/libkmod/README",1313,"dc724f4aedb591d8d75fa7821fb8572c3b52b9d457540c2b3bbeeb33c6c6f5d2"),
    ("external/kmod/libkmod/docs/.gitignore",154,"4c8cfb08055659b69db3fc980e19b8fc7bb5d596b3f7d480e16b47caef4c33b6"),
    ("external/kmod/libkmod/docs/Makefile.am",796,"e597dcaf97f0df69162e4b2e0465d2a4850ae6cf1feb8f95aa80bdae77b2fd34"),
    ("external/kmod/libkmod/docs/libkmod-docs.xml",881,"b967290286dd437e45e4f6072e70ec61643f9c0f052577341d1c0245df0ff2e5"),
    ("external/kmod/libkmod/docs/libkmod-sections.txt",2183,"8612046173af0db9f178837452259685b09cf749b526f1bb3414bc70777123a3"),
    ("external/kmod/libkmod/docs/version.xml.in",10,"e17c0158b831d506641b48f47a1617a2910163f0c19c952c816a68c457bc61d0"),
    ("external/kmod/libkmod/libkmod-builtin.c",6373,"6c2ee11fdd9c3d9983ed0393e878970049980b7fe605b256a481150e5ff59fcf"),
    ("external/kmod/libkmod/libkmod-config.c",29967,"08ecadfc231d16c648e82888c29e6f544bb3d18713973213910eb4464d6b717e"),
    ("external/kmod/libkmod/libkmod-elf.c",28576,"a732fd415ceeac961f570860fb1bb5cf8580b1873a968c00c0075fd43046be4f"),
    ("external/kmod/libkmod/libkmod-file.c",11307,"38a1d98d68a345bdd5b95d6e6739812893d22178b8c20bdcd7227060e4edb9cc"),
    ("external/kmod/libkmod/libkmod-index.c",23624,"09aebc94e7131a1b6999896e1f03be50dc634642d5c911351df789aeabfb863e"),
    ("external/kmod/libkmod/libkmod-index.h",1788,"de8d07f823627c62e235570ec3566ce46f4657f46f6d14147b35b55b2c6eaffd"),
    ("external/kmod/libkmod/libkmod-internal.h",10589,"314e2fdce9b9607747959e33b8fb5b143987abcee26f6dd0df7a9c235b293a44"),
    ("external/kmod/libkmod/libkmod-list.c",6992,"4c5f39c0a4893027f7f6d47308e084e7986b438c3104dae610dbe206827c0816"),
    ("external/kmod/libkmod/libkmod-module.c",74132,"8504eacb0e82e71c05d42ed354d9f3dd0ee8834f3ddaef739db6db53f0d92139"),
    ("external/kmod/libkmod/libkmod-signature.c",8520,"4dd6d4090b7531531bb4189c4d3459a00e7dd0d6b35c7920af08627ccf2f3fce"),
    ("external/kmod/libkmod/libkmod.c",24456,"80bc9443ce4efdbe72608d07355559d13b2b631d928797092e0a34595f38c5b4"),
    ("external/kmod/libkmod/libkmod.h",9667,"bfcf51c09a03cbe92913fe6a3c889e72a21a0a0bc794578998ebadf63be99c25"),
    ("external/kmod/libkmod/libkmod.pc.in",270,"d9f93397a1a5d7d941b8ceda7d6f1294d759e914c8aaa9836a6bcec0de540bd8"),
    ("external/kmod/libkmod/libkmod.sym",2105,"842d36540a4b85695b682b779db843ccf81b9db2592ca6c4d0a8e37e8847c625"),
    ("external/kmod/rules.mk",1903,"5f8b508f975da42222bda3950c7e3f2bda32650cb439d6ea4db3a020e127f576"),
    ("external/kmod/shared/.gitignore",34,"3a2a7ba08d5b63ccec247944f75160722ea2c26933a5d8fa004d5d40074aa593"),
    ("external/kmod/shared/array.c",2731,"094fdac342bce7caa26acac4e02217e7d9959741f426f3cf01a88835c426c5ab"),
    ("external/kmod/shared/array.h",651,"a3a322caac9448d995080863308606ae317c57e04d12d016d616b592cac6275e"),
    ("external/kmod/shared/hash.c",8194,"228ea0edaa5b9ac2dace32b2febc639e632bd7bec477070181b7ee786e152928"),
    ("external/kmod/shared/hash.h",725,"2592c9a8dce090f796884e53807cda6f050e8173966eca75b301638667188efd"),
    ("external/kmod/shared/macro.h",2432,"ad250f0ab3839d1d01f9f0e4c137b8aeeb0fd6c2661bcdb55a4e11215274bdbc"),
    ("external/kmod/shared/missing.h",1123,"a25b12e69a37e8215cbfab1863b85c1267ae4ad2032af434c375e0ca028bb5f0"),
    ("external/kmod/shared/scratchbuf.c",1492,"aff341a5f724f400fd18c49b875a8b1f38288fbf51e48799a17878c90519dfe6"),
    ("external/kmod/shared/scratchbuf.h",620,"a129413daf4a77f7d00c61538d29dcfcfd3472886a126f6e7cf1566ae5bc4ecd"),
    ("external/kmod/shared/strbuf.c",2542,"a98b2f6e34cf2f9c5b44b0a94ed13b459863bd97a0cda24c1c4c439c2176baa2"),
    ("external/kmod/shared/strbuf.h",696,"5687ce1c87e7141d47abe1396fb0e44fdf54017dc7a9c88fde146bd3e45249c0"),
    ("external/kmod/shared/util.c",10106,"bfb38225fb1dca19c5fcc241214f0e789b2a67bedb3589327ee51a733aab5a63"),
    ("external/kmod/shared/util.h",4045,"a933298b5b25b4f3e4717c4743cb049ecae42a9c1a19fc803cc929d3c0397511"),
    ("external/kmod/tools/.gitignore",151,"c83a2f8c8863159242534f7f3a8d17cb7d884724fac986a337725301ace0c936"),
    ("external/kmod/tools/COPYING",17987,"ab15fd526bd8dd18a9e77ebc139656bf4d33e97fc7238cd11bf60e2b9b8666c6"),
    ("external/kmod/tools/Makefile",332,"85eb6a17cfb939aa991dbb06d906d62095966b9775be2e774d08df62b34ed2f1"),
    ("external/kmod/tools/depmod.c",71605,"7691e48be33ba4a1f4bc49f373b63edad8891dd2f014594269dd45ff621d22c4"),
    ("external/kmod/tools/insmod.c",3719,"68c526b5ac81070abe8b532b39d7f0f0029fff91380df0745a6ab7f62827c7f5"),
    ("external/kmod/tools/kmod.c",3815,"e03b283c0650a5f398a428aa8bc8e966ccc95ae5ea8d423a60e0836c379aa78a"),
    ("external/kmod/tools/kmod.h",1415,"30cb77bc7049e20e240f81f0aa640c5d3bca2eaf223ccb69cdb8505308cbf8a9"),
    ("external/kmod/tools/kmod.pc.in",260,"bba1599353e0abfd6a390b1a424c97ee2234c9eb0529cd89e46ce0a4305e97c6"),
    ("external/kmod/tools/log.c",3149,"d7253f98265a6f0a879ab35b3668f39586d010f8474d89d43e4328d435714781"),
    ("external/kmod/tools/log.h",1307,"ab345f6545ec75a1ff08d427c2de0893249c3d5b48ddf251bd6450f11daf0044"),
    ("external/kmod/tools/lsmod.c",2577,"441aa51f39964b71e443d63e368f879f869d4c7d3d9b31c9fd52edafcab0e969"),
    ("external/kmod/tools/modinfo.c",11202,"7baea25aedacfe7aef032e502d952f8947700ea14ffd6a0b0db4baa6e7fc60d5"),
    ("external/kmod/tools/modprobe.c",25088,"f0e1a4cd3bedd98ef0796706cdac781d8b3a8568c670dac54b2b3b655c88d01e"),
    ("external/kmod/tools/port.c",175,"0749f7f83fc1722512328f03f99901a947ea579a5fe16e365fa3037ff25c4201"),
    ("external/kmod/tools/rmmod.c",4699,"1cfdde39bdbf85742750d8af2c850ef6812a928bb6c619f1ec5e61163b05ba91"),
    ("external/kmod/tools/static-nodes.c",7009,"f16dfd9b0a833ae7ee71d2eff37fbd851469e6606fd9f86e5cdd25480efceced"),
    ("prebuilts/clang/host/linux-x86/Android.bp",17607,"d6c17476ae87bdd901e07bb2cc5ddbaeff4ce70569aa476ea40c7e119d521e1b"),
];

fn validate_audio_depmod536_source_paths(lock:&droidloom_source::SparseSourceLock,mode:SoongDependencyMode)->Result<()> {
    if mode!=SoongDependencyMode::AudioApexTargetClosure {return Ok(());}
    let p=lock.projects.iter().find(|p|p.path==Path::new("external/kmod")).ok_or("missing original same-SP kmod host provider")?;
    let cones=vec!["android","libkmod","shared","tools"].into_iter().map(PathBuf::from).collect::<Vec<_>>();
    if p.name!="platform/external/kmod"||p.commit!="41034538d81a8ee44e98dfaf6bd9d46f1f45adac"||p.sparse_paths!=cones {return fail("depmod requires exact original kmod project pin and four cones");}
    Ok(())
}
fn validate_audio_depmod536_original_inputs(source:&Path,mode:SoongDependencyMode)->Result<()> {
    if mode!=SoongDependencyMode::AudioApexTargetClosure {return Ok(());}
    for(relative,bytes,digest)in AUDIO_DEPMOD536_ORIGINAL_INPUTS {
        let mut path=source.to_path_buf();
        for part in Path::new(relative).components(){path.push(part.as_os_str());if fs::symlink_metadata(&path)?.file_type().is_symlink(){return fail(format!("depmod original source alias: {relative}"));}}
        let metadata=fs::symlink_metadata(&path)?;
        if !metadata.is_file()||metadata.len()!=*bytes||hash(&path)?!=*digest {return fail(format!("depmod original producer/factory source changed: {relative}"));}
    }
    Ok(())
}

// The original shared libexif provider for the real camera dependency.
// The existing camera module and all of its direct native providers remain intact.
const AUDIO_LIBEXIF537_ORIGINALS: &[(&str,u64,&str,bool)] = &[
    ("external/dynamic_depth/Android.bp",1986,"3e4fdba538c06b65e2a37c4a0e83730e3bf6b2c5fd950fc142bf49588b4b0bbf",false),
    ("external/libexif/ABOUT-NLS",53838,"7cdde3110b8642b4ff7a76a870b006c0db599f9b9429059f765986418d049155",false),
    ("external/libexif/AUTHORS",162,"fe4e264840222918a17b78014fa5aa4c438b9a7e81639fb9b2ff6d9a0c4d61cc",false),
    ("external/libexif/Android.bp",3545,"341ccf904de372b9c5b5a8eefcf3f5c9b8e4de09729bd7631a63ebcc367fb1a2",false),
    ("external/libexif/COPYING",26434,"36b6d3fa47916943fd5fec313c584784946047ec1337a78b440e5992cb595f89",false),
    ("external/libexif/ChangeLog",67816,"ac473d6f80080dfa64e21b6a90267f4b8b6873383045b468598a0dd9e881b669",false),
    ("external/libexif/INSTALL",15578,"91826b889739b720e0da7055b74a5a579dd31ad2f3b683b15302039df676e34f",false),
    ("external/libexif/METADATA",577,"7b1f086a9e9296973ab2389df5c89fdccb302c3cc5652675522172b788231ea6",false),
    ("external/libexif/MODULE_LICENSE_LGPL",0,"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",false),
    ("external/libexif/Makefile.am",1533,"36c40ef62b625cc98d588091ddb9008f4559f77e4cd1eed6d0bd3ddadf575374",false),
    ("external/libexif/Makefile.in",29398,"009c4af1241176f4804926b9ed087cfd53e4f7b69a455eb040a0a06bc550dbc3",false),
    ("external/libexif/NEWS",6173,"4b10f762e6ce468f6b5feb73a57a7c62938b707d22d1a6bc562a1fddfbc78f8e",false),
    ("external/libexif/NOTICE",26434,"36b6d3fa47916943fd5fec313c584784946047ec1337a78b440e5992cb595f89",false),
    ("external/libexif/OWNERS",212,"c2e5b2410bf0689e3c63c39b753772b6cbc9456a6276d4ef1f196115f1aa64a3",false),
    ("external/libexif/README",6142,"b6883a3ee10ee2c6aa3fc7ee5627e4543360564cec3303e8a65592ef658dd9d6",false),
    ("external/libexif/README-Win32.txt",946,"38303da59b042bf99d5508832483cc1d1518a3d3d0526771ab68dfe9b4f7d99b",false),
    ("external/libexif/README.android",153,"becf72cf3772dc8f76d8f6b25534d532d4a7465146266e2546f5482a4be9e8ce",false),
    ("external/libexif/README.version",132,"68d12b5e05653c99cea1bd7850ee681b4fbfb931edd5a60927976c522e81734f",false),
    ("external/libexif/aclocal.m4",37911,"1b6af4ead408eb9bccff44485c71cc493eda499167f98d520bce10b2e48a5d00",false),
    ("external/libexif/config.guess",44941,"8486189f55971e6bde5ace26d97a2a51470fe49222160647d258be15d1e693b2",true),
    ("external/libexif/config.h",2809,"6c572c9a3509e24830fe0cf2874de5847ca70e894522544398f606c90421f675",false),
    ("external/libexif/config.h.in",2440,"c5bd3eb491f27ae85580e7f336d5080cad9ead38fc96a903807f3ac2e3381aef",false),
    ("external/libexif/config.rpath",14987,"e0380c868ff060c190b3f56d7f30dde939b8a529f5a980f355f3080a56c1594d",true),
    ("external/libexif/config.sub",34423,"4b046cb76957a1a683f30014263c0672b02d8425086a721e6ef25aede80ff861",true),
    ("external/libexif/configure",490200,"7aedbde73fbae06cf90bbf1a669b8ca51b234a20dbaa96354d521e43452d1471",true),
    ("external/libexif/configure.ac",7619,"997208f03149c83264f799b75e03f686db1eb65e20aa44a62589015af09b7feb",false),
    ("external/libexif/depcomp",18615,"20efdbd4f295e6b759a024fe045671de5db6066e2a210be3296eeb9c38a1b238",true),
    ("external/libexif/install-sh",13663,"a42cce53f5b376a4b1251e8d06e96dead9e858396d07333ed0cc83aa4b510023",true),
    ("external/libexif/libexif-uninstalled.pc.in",168,"dc0c30f39c1ba2346263a5ea144c686b361f6bb72d54ea5518c2aefd3bae832a",false),
    ("external/libexif/libexif.pc.in",243,"e0e9a5d0e7ebbcdd72140935668b381d192e92612ee7d5ed8f82df0f94fbe0a4",false),
    ("external/libexif/libexif.spec",1323,"a5ee6dda2f1ec9d4f7308c832ce5d117cd9f2ef7bf9fab3c4ad6cbb5623a9369",false),
    ("external/libexif/libexif.spec.in",1328,"c9016206c771dbff7b8199c7cfe6623daebed67d16945b811d1900709fea9907",false),
    ("external/libexif/libexif/Makefile.am",1481,"f496001ddfc67351049d212ffbfa1104a6f92488f3e571c024605679509fa026",false),
    ("external/libexif/libexif/Makefile.in",40273,"2d2c6ece425cc4c9b5c815c5c1e654b655747453f5262cf951ad7e28226bc02d",false),
    ("external/libexif/libexif/_stdint.h",76,"4f0de7785dd7e001a7d6f6d949d756d42727dab4cb80cb10a376ac8c64fd8982",false),
    ("external/libexif/libexif/exif-byte-order.c",1168,"8f823138d75d1c0a7e14ce164513483b2f3d1e25c590d4af60040faaa880d3ec",false),
    ("external/libexif/libexif/exif-byte-order.h",1521,"4fbdd09da28c99a4cd50f85387efd8f4a4bd5ea1f6fea68d66ce440109aa8ddf",false),
    ("external/libexif/libexif/exif-content.c",7865,"6be7b4ec9fec61a652891566ae50dc2a566ea6f162c5df12f0e35bf8b05e7b8d",false),
    ("external/libexif/libexif/exif-content.h",4721,"1f10cb036f01ee9374c03e934134bd6ad649e2c1c622172a3089094429aa675c",false),
    ("external/libexif/libexif/exif-data-type.h",1433,"52d0c29b9fceb770460de5162851e280cd3040d0a7a47f16900445f4a1ec5fff",false),
    ("external/libexif/libexif/exif-data.c",31713,"f5b7d988d67dce3f8bc1be2ab200b09fbb00c2a0b2b78de1e1c5840f7833ade9",false),
    ("external/libexif/libexif/exif-data.h",8876,"eb29be3d7e90e99b033e288efcd04d40646715b2c55b378415e2c653778ecb20",false),
    ("external/libexif/libexif/exif-entry.c",52859,"3d426db5af95f9d541f97a4002087abb8c81f924d7e2cec645ec4fcfbaa7ba38",false),
    ("external/libexif/libexif/exif-entry.h",6215,"7e5a4c26fe20072612532ce26c4ea600bd55baba4ccbf1eb7161caf73b1de367",false),
    ("external/libexif/libexif/exif-format.c",2623,"395c2076ea49b4db81eac43616b84a436fc58818867228ba71235189885b3019",false),
    ("external/libexif/libexif/exif-format.h",1939,"604ad147d03605f92a7846dac98d3acbf5eccf3ce5120c3db9307329b28487c3",false),
    ("external/libexif/libexif/exif-ifd.c",1325,"843a2f2a204d53cb53f03d8554ddab2920bfa1dcdf49c151f94e4c6381dba646",false),
    ("external/libexif/libexif/exif-ifd.h",1528,"9fdf3cd24b787b2bd343309ac8efe61f0e6807a6a5123d1e1300988d5bc898cf",false),
    ("external/libexif/libexif/exif-loader.c",9858,"5149ef0f7a051956a16f54efddeb0cc0934b44ae585d8cff96eaf04a5e7144a2",false),
    ("external/libexif/libexif/exif-loader.h",4279,"a0ac25eddc4aae52b71e0bec560e8f2b6908f7c12bbdf13c3e399a4859eb1191",false),
    ("external/libexif/libexif/exif-log.c",3239,"6e8aa7dabc3af18aeec55e3ff07ab9c40c5d37a6fd1964a3a575132238d733f8",false),
    ("external/libexif/libexif/exif-log.h",3390,"2ebaf52339822e89804c8b42b0f39eae4a388b257df466ace326dd158ea5df68",false),
    ("external/libexif/libexif/exif-mem.c",1821,"41c643ffbf3f59014110bb0686d5278e9c334007d3e91b1b1b50a047392f874e",false),
    ("external/libexif/libexif/exif-mem.h",2584,"febf0e90c69b30837b7c69b98cee1e83f23e8813470cf0bbe5ef9018fab285e1",false),
    ("external/libexif/libexif/exif-mnote-data-priv.h",2572,"feec6183a731192f4f00a630ff5e000b0184f4d581233101bedc60c16a4a8094",false),
    ("external/libexif/libexif/exif-mnote-data.c",3670,"68cc3e375898220c95cee6f6b54bc248dcf46ec9cc060144f2a9e794807f3210",false),
    ("external/libexif/libexif/exif-mnote-data.h",4256,"5e1a011964bf50d5ce07316c5e02508a4d7a730df33f0a011c60b0b79f056741",false),
    ("external/libexif/libexif/exif-system.h",1147,"115c607051faf5d050616dc617bdf9de3a677831d42186ece5fec5d4d6bc1baf",false),
    ("external/libexif/libexif/exif-tag.c",58433,"4552558b9c83cde7e208b0b4b886c4c4324956dad71fb6715bcc82b6d275d34b",false),
    ("external/libexif/libexif/exif-tag.h",10470,"95d71967c1c413e31e615697f00f32e230a7b1c11c07c3fb53b33116d4538b38",false),
    ("external/libexif/libexif/exif-utils.c",5997,"a79e512890e7d33f9aabcbd7748c570b4f3e4510352714377e121c7f830583a4",false),
    ("external/libexif/libexif/exif-utils.h",5930,"1676c9d6e61f56c3ba5b55588d19c8fa127204568f355bb054001653e616192f",false),
    ("external/libexif/libexif/exif.h",3403,"603f05b7e647fdf3fece47a64de85516bb25f5502512b581012d1f6e7ac5e25b",false),
    ("external/libexif/libexif/i18n.h",1694,"84e68a1fe5cb99864f86fa8ff62ac134b7ebc0abf6bcef2117a286c0601f575a",false),
    ("external/libexif/libexif/libexif.sym",2690,"bf260817bbdcfdda0db76443bc7fd8a8ba4237e597594ca22972cdbc811dc88f",false),
    ("external/libexif/libexif_blocklist.txt",989,"356c96ecc730fdb9f8fc156dbe034ba053ad040a7567c6c8111f5ffca5df2ab1",false),
    ("external/libexif/ltmain.sh",283503,"b76ab504b03b76dff3efc3693fc036b3174a39ff70c5abfee009206d032d2171",true),
    ("external/libexif/missing",11419,"fd08cdce99a06aeb2308dd3b78499edc15c29ebc2da23b059a931b38cc5b90f3",true),
    ("external/libexif/mkinstalldirs",3538,"e99c53f339aae38b0b2320d2e15d8a92ffe6028da0ab485b17bf57fda149110a",true),
    ("external/libjpeg-turbo/Android.bp",10518,"a1c573b0948772b666021a83000688ec9f92ff8c316a3eac294559b97660b7a6",false),
    ("external/libxml2/Android.bp",39154,"23118f1d9f88e910e92bc5d3bfc329b8b489a1ed9d8b90d79de1c127c76bbcfe",false),
    ("frameworks/av/camera/Android.bp",6764,"99fdf64377ab08f959d5263ff3803c622ffb68b84f9a0aaa7d766a4839ae916c",false),
    ("frameworks/av/services/camera/libcameraservice/Android.bp",10592,"0cefe30c4a76dfd0e9a24092908ad22c4520b20281e8d6992149072309c9721a",false),
    ("frameworks/native/libs/binder/Android.bp",29180,"f984bc90258c3b343a48033c9dcd450814c804af67ddd0152b6bfa5307127e87",false),
    ("packages/modules/StatsD/lib/libstatspull/Android.bp",5167,"fde52e11594a382862d4b3d11e9a38f3655a877c78c9629d2f5aa4bdc37e7682",false),
    ("system/core/libutils/Android.bp",8090,"dd6de537de330cb420b63883da38c739aa1ab7f9256fa22c2bb630e28909a3bb",false),
    ("system/libbase/Android.bp",6804,"2e3f7e52769a44e4b0f7d3c6557776e9d939da2733118574f2b350e63cd3894d",false),
    ("system/logging/liblog/Android.bp",6450,"6d338a6006e1b7aff334cca19930f45c6c5d7fcd67823591ad0636e29be7c1b4",false),
    ("system/media/camera/Android.bp",2029,"b3347c3ec5dab27f6fa84d6c41690d121a5d04a4b1c14be25c8649aad509821b",false),
 ];
fn validate_audio_libexif537_source_paths(lock:&droidloom_source::SparseSourceLock,mode:SoongDependencyMode)->Result<()> {
    if mode!=SoongDependencyMode::AudioApexTargetClosure {return Ok(());}
    let p=lock.projects.iter().find(|p|p.path==Path::new("external/libexif")).ok_or("missing original same-SP libexif shared provider")?;
    if p.name!="platform/external/libexif"||p.commit!="e180c53a25cc0f26e6e0caf4a2708c41b8ec5214"||p.sparse_paths!=vec![PathBuf::from("libexif")] {
        return fail("libexif requires its fixed original project and one complete native cone");
    }
    Ok(())
}
fn validate_audio_libexif537_original_inputs(source:&Path,mode:SoongDependencyMode)->Result<()> {
    use std::os::unix::fs::MetadataExt;
    if mode!=SoongDependencyMode::AudioApexTargetClosure {return Ok(());}
    for(relative,bytes,digest,executable)in AUDIO_LIBEXIF537_ORIGINALS {
        let mut path=source.to_path_buf();
        for part in Path::new(relative).components() {
            path.push(part.as_os_str());let metadata=fs::symlink_metadata(&path)?;
            if metadata.file_type().is_symlink() {return fail(format!("libexif original path aliases another input: {relative}"));}
        }
        let metadata=fs::symlink_metadata(&path)?;
        if !metadata.is_file()||metadata.nlink()!=1||metadata.len()!=*bytes||
            (metadata.mode()&0o111!=0)!=*executable||hash(&path)?!=*digest {
            return fail(format!("libexif/camera original source or native producer changed: {relative}"));
        }
    }
    Ok(())
}

fn validate_audio_sdk14_source_paths(lock:&droidloom_source::SparseSourceLock, mode:SoongDependencyMode)->Result<()> {
    if mode!=SoongDependencyMode::AudioApexTargetClosure {return Ok(());}
    let sdk=lock.projects.iter().find(|p|p.path==Path::new("prebuilts/sdk")).ok_or("missing original SDK14 provider")?;
    if sdk.name!="platform/prebuilts/sdk" || sdk.commit!="0f07e8d60ab0aba46129e427101f96ba459a95c1" || !sdk.sparse_paths.contains(&PathBuf::from("14/public")) || sdk.sparse_paths.contains(&PathBuf::from("14")) {
        return fail("SDK14 requires the fixed original public cone without repinning or whole-API widening");
    }
    Ok(())
}
const AUDIO_SOURCE_LOCK_SHA256: &str = "84bdef58aa934bcaa1926f9ea901186017c5f53118db1683fec1283489e0f31b";
fn selected_source_lock(repo: &Path, mode: SoongDependencyMode) -> Result<PathBuf> {
    if mode == SoongDependencyMode::AudioApexTargetClosure {
        let lock = repo.join("android/manifest/audio-bridge-source-lock.json");
        if hash(&lock)? != AUDIO_SOURCE_LOCK_SHA256 {
            return fail("audio build requires its exact independent 537-project source lock");
        }
        Ok(lock)
    } else {
        Ok(repo.join("android/manifest/m2-sparse-source-lock.json"))
    }
}

fn project_audio_resources(p: &mut Projection, repo: &Path, source: &Path,
                           mode: SoongDependencyMode) -> Result<()> {
    if mode != SoongDependencyMode::AudioApexTargetClosure { return Ok(()); }
    // Only scheduling and retained output buffers change. Every provider,
    // selected target, dependency error, and incremental branch is preserved.
    for (relative, expected) in [
        ("build/blueprint/context.go", "e2b7bf50848ba9f9ac7078dae87c6b2e13ce7019ba997c71f90a04e602f1a9d4"),
        ("build/soong/ui/build/soong.go", "ab745182f4fba6ab4fbd1cea6fc4943b78e588b4187dfc735cd28826bbaa7027"),
        ("build/blueprint/bootstrap/command.go", "bb681356afa58932692866c41086e122509dc65d36edabc22c7bb154be5c8f38"),
    ] {
        if hash(&source.join(relative))? != expected {
            return fail(format!("audio resource projection requires exact locked original {relative}"));
        }
    }
    for (cwd, patch) in [
        ("build/soong", "android/audio-bridge/0001-soong-resource-budget.patch"),
        ("build/blueprint", "android/audio-bridge/0002-blueprint-stream-uncached-actions.patch"),
        ("build/blueprint", "android/audio-bridge/0003-blueprint-provider-concurrency.patch"),
        ("build/blueprint", "android/audio-bridge/0004-blueprint-explicit-go-budget.patch"),
    ] { p.patch(source, cwd, &repo.join(patch))?; }
    Ok(())
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
    build_targets_with_fixed_request(repo, source, out, work, product, jobs,
        FixedProductionRequest::Existing(dependency_mode, targets))
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

fn build_targets_with_fixed_request(
    repo: &Path, source: &Path, out: &Path, work: &Path, product: &str, jobs: usize,
    request: FixedProductionRequest<'_>,
) -> Result<()> {
    // Reject the request before materializing or projecting any source. The
    // existing profile targets below control projection only, never final argv.
    request.validate(product)?;
    let dependency_mode = request.source_mode();
    let targets = request.projection_targets();
    if dependency_mode == SoongDependencyMode::NativeEngineTargetClosure {
        crate::native_engine::begin_attempt(out, product)?;
    }
    let lock = selected_source_lock(repo, dependency_mode)?;
    let source_lock = droidloom_source::load_lock(&lock)?;
    validate_audio_provider_source_paths(&source_lock, dependency_mode)?;
    validate_audio_depmod536_source_paths(&source_lock, dependency_mode)?;
    validate_audio_libexif537_source_paths(&source_lock, dependency_mode)?;
    validate_audio_sdk14_source_paths(&source_lock, dependency_mode)?;
    if nativebridge_discovery_scope(targets) {
        validate_nativebridge_scope_source_paths(&source_lock)?;
    }
    if !source.exists() {
        droidloom_source::materialize(&lock, &source_lock, source)?;
    } else {
        droidloom_source::reconcile(&lock, &source_lock, source)?;
    }
    droidloom_source::verify_materialized(&lock, &source_lock, source)?;
    match request {
        FixedProductionRequest::VendorPolicyOnAudioSource => validate_vendor_policy_original(source)?,
        FixedProductionRequest::VendorPolicyBundleOnAudioSource => validate_vendor_policy_bundle_originals(source)?,
        FixedProductionRequest::Existing(_, _) => (),
    }
    validate_audio_pasit_original_providers(source, dependency_mode)?;
    validate_audio_zygote_original_providers(source, dependency_mode)?;
    validate_audio_lint_fonttools_original_providers(source, dependency_mode)?;
    validate_audio_test_tools_original_providers(source, dependency_mode)?;
    validate_audio_bcc_original_providers(source, dependency_mode)?;
    validate_audio_chre_original_providers(source, dependency_mode)?;
    validate_audio_vintf_vts_original_providers(source, dependency_mode)?;
    validate_audio_adb_webrtc_original_inputs(source, dependency_mode)?;
    validate_audio_watchdog_original_inputs(source, dependency_mode)?;
    validate_audio_host_tools_original_inputs(source, dependency_mode)?;
    validate_audio_trusty_original_inputs(source, dependency_mode)?;
    validate_audio_generic535_original_inputs(source, dependency_mode)?;
    validate_audio_depmod536_original_inputs(source, dependency_mode)?;
    validate_audio_libexif537_original_inputs(source, dependency_mode)?;
    validate_audio_ondeviceintelligence_api_inputs(source, dependency_mode)?;
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
    for (cwd, patch) in PATCHES {
        p.patch(source, cwd, &repo.join(patch))?;
    }
    for (cwd, patch) in target_closure_soong_patches(dependency_mode) {
        p.patch(source, cwd, &repo.join(patch))?;
    }
    if qualified_defaults_mode(dependency_mode) {
        p.patch(source, "build/soong", &repo.join(
            "android/apex-compat/0007-transitive-default-missing-dependencies.patch"))?;
    }
    if leaf_go_memory_mode(dependency_mode) {
        p.patch(source, "build/soong", &repo.join(
            "android/apex-compat/0008-soong-leaf-go-memory-budget.patch"))?;
    }
    project_audio_resources(&mut p, repo, source, dependency_mode)?;
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
    project_blueprints(&mut p, source, dependency_mode)?;
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
            project_discovery_exclusion(&mut p, source, relative, dependency_mode)?;
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
            let projected = match audio_original_graph_provider(relative, &original, dependency_mode)? {
                Some(complete) => complete,
                None => private_without_named_java_module(&original, kind, name)?,
            };
            p.put(&path, projected)?;
        }
        // Audio's retained Java services still consume these original generators.
        // Other native leaf routes keep their existing private scope.
        // Preserve every actual C++/JNI networking provider in this file.
        let connectivity = source.join("packages/modules/Connectivity/service/Android.bp");
        let original = fs::read_to_string(&connectivity)?;
        let projected = match audio_connectivity_provider_after_patch(
            &p, repo, source, &original, dependency_mode,
        )? {
            Some(complete) => complete,
            None => {
                let mut scoped = original;
                for name in ["service-connectivity-jarjar-gen", "service-nearby-jarjar-gen",
                             "service-remoteauth-jarjar-gen", "service-thread-jarjar-gen",
                             "service-networksecurity-jarjar-gen"] {
                    scoped = private_without_named_java_module(&scoped, "java_genrule", name)?;
                }
                scoped
            }
        };
        p.put(&connectivity, projected)?;
        let error_prone = source.join("external/error_prone/Android.bp");
        let original = fs::read_to_string(&error_prone)?;
        p.put(&error_prone, native_leaf_error_prone(&original, dependency_mode)?)?;
        // Retain the real Room processor required by the visible SystemUI
        // providers in audio mode. Other leaf routes retain their old scope.
        let plugins = source.join("prebuilts/sdk/current/androidx/JavaPlugins.bp");
        let original = fs::read_to_string(&plugins)?;
        p.put(&plugins, native_leaf_java_plugins(&original, dependency_mode)?)?;
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
            let directory=format!("external/rust/android-crates-io/crates/{name}");
            project_discovery_exclusion(&mut p,source,&directory,dependency_mode)?;
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
        let projected = match audio_original_graph_provider(
            "system/update_engine/Android.bp", &original, dependency_mode,
        )? {
            Some(complete) => complete,
            None => private_nativebridge_update_engine_headers_only(&original)?,
        };
        p.put(&path, projected)?;
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
    for relative in SOONG_EXCLUDED_TEST_FIXTURES {
        project_discovery_exclusion(&mut p, source, relative, dependency_mode)?;
    }
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
    let selected_targets = request.soong_targets(out, product)?;
    let policy_names = request.policy_receipt_names();
    let policy_input_path = policy_names.map(|names| out.join(names.0));
    if let Some((_,input_schema,_,_)) = policy_names {
        let mut inputs = request.description(product)?;
        inputs["schema"] = input_schema.into();
        inputs["source_lock"] = serde_json::json!({"path": lock, "sha256": hash(&lock)?});
        inputs["source_directory"] = serde_json::json!(source);
        inputs["output_directory"] = serde_json::json!(out);
        inputs["selected_soong_targets"] = serde_json::json!(selected_targets);
        inputs["strict_allow_missing_dependencies"] = "false".into();
        inputs["selinux_ignore_neverallows"] = "false".into();
        write(policy_input_path.as_ref().ok_or("fixed policy input path missing")?, serde_json::to_vec_pretty(&inputs)?)?;
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
    request.configure_dependencies(&mut cmd, product)?;
    let result = run_build(&mut cmd);
    p.restore()?;
    result?;
    if let Some((_,_,result_name,result_schema)) = policy_names {
        let policy_input_path=policy_input_path.as_ref().ok_or("fixed policy input path missing")?;
        write(&out.join(result_name),
            serde_json::to_vec_pretty(&serde_json::json!({
                "schema": result_schema,
                "inputs": {"path": policy_input_path, "sha256": hash(policy_input_path)?},
                "requested_targets": request.requested_targets(),
                "normal_command_returned_success": true,
                "source_projection_restored": true,
                "artifact_identity_qualified": false,
                "selected_cohort_policy_qualified": false,
                "Audio_APEX_qualified": false,
                "runtime_qualified": false,
            }))?)?;
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

    fn write_libexif537_original_fixtures(root:&Path) {
        use std::os::unix::fs::PermissionsExt;
        let bodies:&[(&str,&[u8])]=&[
            ("external/dynamic_depth/Android.bp",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/dynamic_depth/Android.bp")[..]),
            ("external/libexif/ABOUT-NLS",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/ABOUT-NLS")[..]),
            ("external/libexif/AUTHORS",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/AUTHORS")[..]),
            ("external/libexif/Android.bp",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/Android.bp")[..]),
            ("external/libexif/COPYING",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/COPYING")[..]),
            ("external/libexif/ChangeLog",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/ChangeLog")[..]),
            ("external/libexif/INSTALL",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/INSTALL")[..]),
            ("external/libexif/METADATA",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/METADATA")[..]),
            ("external/libexif/MODULE_LICENSE_LGPL",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/MODULE_LICENSE_LGPL")[..]),
            ("external/libexif/Makefile.am",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/Makefile.am")[..]),
            ("external/libexif/Makefile.in",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/Makefile.in")[..]),
            ("external/libexif/NEWS",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/NEWS")[..]),
            ("external/libexif/NOTICE",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/NOTICE")[..]),
            ("external/libexif/OWNERS",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/OWNERS")[..]),
            ("external/libexif/README",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/README")[..]),
            ("external/libexif/README-Win32.txt",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/README-Win32.txt")[..]),
            ("external/libexif/README.android",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/README.android")[..]),
            ("external/libexif/README.version",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/README.version")[..]),
            ("external/libexif/aclocal.m4",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/aclocal.m4")[..]),
            ("external/libexif/config.guess",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/config.guess")[..]),
            ("external/libexif/config.h",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/config.h")[..]),
            ("external/libexif/config.h.in",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/config.h.in")[..]),
            ("external/libexif/config.rpath",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/config.rpath")[..]),
            ("external/libexif/config.sub",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/config.sub")[..]),
            ("external/libexif/configure",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/configure")[..]),
            ("external/libexif/configure.ac",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/configure.ac")[..]),
            ("external/libexif/depcomp",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/depcomp")[..]),
            ("external/libexif/install-sh",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/install-sh")[..]),
            ("external/libexif/libexif-uninstalled.pc.in",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif-uninstalled.pc.in")[..]),
            ("external/libexif/libexif.pc.in",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif.pc.in")[..]),
            ("external/libexif/libexif.spec",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif.spec")[..]),
            ("external/libexif/libexif.spec.in",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif.spec.in")[..]),
            ("external/libexif/libexif/Makefile.am",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/Makefile.am")[..]),
            ("external/libexif/libexif/Makefile.in",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/Makefile.in")[..]),
            ("external/libexif/libexif/_stdint.h",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/_stdint.h")[..]),
            ("external/libexif/libexif/exif-byte-order.c",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-byte-order.c")[..]),
            ("external/libexif/libexif/exif-byte-order.h",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-byte-order.h")[..]),
            ("external/libexif/libexif/exif-content.c",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-content.c")[..]),
            ("external/libexif/libexif/exif-content.h",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-content.h")[..]),
            ("external/libexif/libexif/exif-data-type.h",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-data-type.h")[..]),
            ("external/libexif/libexif/exif-data.c",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-data.c")[..]),
            ("external/libexif/libexif/exif-data.h",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-data.h")[..]),
            ("external/libexif/libexif/exif-entry.c",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-entry.c")[..]),
            ("external/libexif/libexif/exif-entry.h",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-entry.h")[..]),
            ("external/libexif/libexif/exif-format.c",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-format.c")[..]),
            ("external/libexif/libexif/exif-format.h",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-format.h")[..]),
            ("external/libexif/libexif/exif-ifd.c",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-ifd.c")[..]),
            ("external/libexif/libexif/exif-ifd.h",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-ifd.h")[..]),
            ("external/libexif/libexif/exif-loader.c",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-loader.c")[..]),
            ("external/libexif/libexif/exif-loader.h",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-loader.h")[..]),
            ("external/libexif/libexif/exif-log.c",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-log.c")[..]),
            ("external/libexif/libexif/exif-log.h",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-log.h")[..]),
            ("external/libexif/libexif/exif-mem.c",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-mem.c")[..]),
            ("external/libexif/libexif/exif-mem.h",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-mem.h")[..]),
            ("external/libexif/libexif/exif-mnote-data-priv.h",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-mnote-data-priv.h")[..]),
            ("external/libexif/libexif/exif-mnote-data.c",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-mnote-data.c")[..]),
            ("external/libexif/libexif/exif-mnote-data.h",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-mnote-data.h")[..]),
            ("external/libexif/libexif/exif-system.h",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-system.h")[..]),
            ("external/libexif/libexif/exif-tag.c",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-tag.c")[..]),
            ("external/libexif/libexif/exif-tag.h",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-tag.h")[..]),
            ("external/libexif/libexif/exif-utils.c",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-utils.c")[..]),
            ("external/libexif/libexif/exif-utils.h",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif-utils.h")[..]),
            ("external/libexif/libexif/exif.h",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/exif.h")[..]),
            ("external/libexif/libexif/i18n.h",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/i18n.h")[..]),
            ("external/libexif/libexif/libexif.sym",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif/libexif.sym")[..]),
            ("external/libexif/libexif_blocklist.txt",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/libexif_blocklist.txt")[..]),
            ("external/libexif/ltmain.sh",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/ltmain.sh")[..]),
            ("external/libexif/missing",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/missing")[..]),
            ("external/libexif/mkinstalldirs",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libexif/mkinstalldirs")[..]),
            ("external/libjpeg-turbo/Android.bp",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libjpeg-turbo/Android.bp")[..]),
            ("external/libxml2/Android.bp",&include_bytes!("../tests/fixtures/audio-libexif537-original/external/libxml2/Android.bp")[..]),
            ("frameworks/av/camera/Android.bp",&include_bytes!("../tests/fixtures/audio-libexif537-original/frameworks/av/camera/Android.bp")[..]),
            ("frameworks/av/services/camera/libcameraservice/Android.bp",&include_bytes!("../tests/fixtures/audio-libexif537-original/frameworks/av/services/camera/libcameraservice/Android.bp")[..]),
            ("frameworks/native/libs/binder/Android.bp",&include_bytes!("../tests/fixtures/audio-libexif537-original/frameworks/native/libs/binder/Android.bp")[..]),
            ("packages/modules/StatsD/lib/libstatspull/Android.bp",&include_bytes!("../tests/fixtures/audio-libexif537-original/packages/modules/StatsD/lib/libstatspull/Android.bp")[..]),
            ("system/core/libutils/Android.bp",&include_bytes!("../tests/fixtures/audio-libexif537-original/system/core/libutils/Android.bp")[..]),
            ("system/libbase/Android.bp",&include_bytes!("../tests/fixtures/audio-libexif537-original/system/libbase/Android.bp")[..]),
            ("system/logging/liblog/Android.bp",&include_bytes!("../tests/fixtures/audio-libexif537-original/system/logging/liblog/Android.bp")[..]),
            ("system/media/camera/Android.bp",&include_bytes!("../tests/fixtures/audio-libexif537-original/system/media/camera/Android.bp")[..]),
        ];
        for (relative,raw)in bodies {let p=root.join(relative);fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(&p,raw).unwrap();let executable=AUDIO_LIBEXIF537_ORIGINALS.iter().find(|r|r.0==*relative).unwrap().3;fs::set_permissions(&p,fs::Permissions::from_mode(if executable{0o700}else{0o600})).unwrap();}
    }
    #[test]
    fn audio_libexif537_exact_original_project_and_cone_reject_pin_or_scope_drift() {
        let repo=Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let lock=droidloom_source::load_lock(&repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();let audio=SoongDependencyMode::AudioApexTargetClosure;
        validate_audio_libexif537_source_paths(&lock,audio).unwrap();
        let old:droidloom_source::SparseSourceLock=serde_json::from_str(include_str!("../../droidloom-source/tests/fixtures/audio-source536-before-libexif.json")).unwrap();
        assert!(validate_audio_libexif537_source_paths(&old,audio).is_err());
        for case in 0..4 {let mut bad=lock.clone();let p=bad.projects.iter_mut().find(|p|p.path==Path::new("external/libexif")).unwrap();match case {0=>p.commit="0000000000000000000000000000000000000000".into(),1=>p.name="platform/other".into(),2=>p.sparse_paths.clear(),_=>p.sparse_paths.push(PathBuf::from("contrib"))};assert!(validate_audio_libexif537_source_paths(&bad,audio).is_err());}
        for mode in [SoongDependencyMode::Strict,SoongDependencyMode::NativeBridgeTargetClosure,SoongDependencyMode::NativeEngineTargetClosure,SoongDependencyMode::MinigbmTargetClosure] {validate_audio_libexif537_source_paths(&old,mode).unwrap();}
    }
    #[test]
    fn audio_libexif537_whole_original_closure_rejects_changed_missing_aliased_or_wrong_mode_inputs() {
        use std::os::unix::fs::{symlink,PermissionsExt};
        let d=tempfile::tempdir().unwrap();write_libexif537_original_fixtures(d.path());let audio=SoongDependencyMode::AudioApexTargetClosure;
        validate_audio_libexif537_original_inputs(d.path(),audio).unwrap();
        for relative in ["external/libexif/Android.bp","external/libexif/config.h","external/libexif/libexif/exif-data.c","frameworks/av/services/camera/libcameraservice/Android.bp","system/logging/liblog/Android.bp"] {
            let p=d.path().join(relative);let raw=fs::read(&p).unwrap();let mode=fs::metadata(&p).unwrap().permissions().mode();
            fs::write(&p,b"changed original").unwrap();assert!(validate_audio_libexif537_original_inputs(d.path(),audio).is_err());
            fs::remove_file(&p).unwrap();assert!(validate_audio_libexif537_original_inputs(d.path(),audio).is_err());
            let same=d.path().join("same-original");fs::write(&same,&raw).unwrap();symlink(&same,&p).unwrap();assert!(validate_audio_libexif537_original_inputs(d.path(),audio).is_err());fs::remove_file(&p).unwrap();
            fs::hard_link(&same,&p).unwrap();assert!(validate_audio_libexif537_original_inputs(d.path(),audio).is_err());fs::remove_file(&p).unwrap();
            fs::write(&p,&raw).unwrap();fs::set_permissions(&p,fs::Permissions::from_mode(mode^0o100)).unwrap();assert!(validate_audio_libexif537_original_inputs(d.path(),audio).is_err());
            fs::set_permissions(&p,fs::Permissions::from_mode(mode)).unwrap();fs::remove_file(same).unwrap();validate_audio_libexif537_original_inputs(d.path(),audio).unwrap();
        }
        let original=d.path().join("external/libexif/libexif");let moved=d.path().join("original-libexif");fs::rename(&original,&moved).unwrap();symlink(&moved,&original).unwrap();assert!(validate_audio_libexif537_original_inputs(d.path(),audio).is_err());
        validate_audio_libexif537_original_inputs(Path::new("/not-present"),SoongDependencyMode::Strict).unwrap();
    }
    #[test]
    fn audio_libexif537_real_shared_provider_keeps_camera_and_all_direct_native_definitions() {
        let d=tempfile::tempdir().unwrap();write_libexif537_original_fixtures(d.path());
        let exif=fs::read_to_string(d.path().join("external/libexif/Android.bp")).unwrap();
        assert!(exif.contains("cc_library_shared {\n    name: \"libexif\","));assert!(exif.contains("host_supported: true"));assert!(exif.contains("vendor_available: true"));
        assert!(exif.contains("shared_libs: [\n        \"liblog\","));
        let camera=fs::read_to_string(d.path().join("frameworks/av/services/camera/libcameraservice/Android.bp")).unwrap();
        assert!(camera.contains("cc_library_static {\n    name: \"libcameraservice_device_independent\","));assert!(camera.contains("\"libexif\","));
        let consumer=camera.split("cc_library_static {\n    name: \"libcameraservice_device_independent\",").nth(1).unwrap().split("cc_library_static {").next().unwrap();
        for (relative,kind,name)in [
            ("frameworks/av/camera/Android.bp","cc_aconfig_library","camera_platform_flags_c_lib"),
            ("frameworks/av/camera/Android.bp","cc_aconfig_library","camera_platform_flags_c_lib_for_test"),
            ("system/libbase/Android.bp","cc_library","libbase"),
            ("frameworks/native/libs/binder/Android.bp","cc_library","libbinder"),
            ("system/media/camera/Android.bp","cc_library","libcamera_metadata"),
            ("external/dynamic_depth/Android.bp","cc_library","libdynamic_depth"),
            ("external/dynamic_depth/Android.bp","cc_library_headers","libdynamic_depth-internal_headers"),
            ("external/dynamic_depth/Android.bp","cc_library_headers","libdynamic_depth-public_headers"),
            ("external/libexif/Android.bp","cc_library_shared","libexif"),
            ("external/libjpeg-turbo/Android.bp","cc_library","libjpeg"),
            ("system/logging/liblog/Android.bp","cc_library","liblog"),
            ("packages/modules/StatsD/lib/libstatspull/Android.bp","cc_library_shared","libstatspull"),
            ("system/core/libutils/Android.bp","cc_library","libutils"),
            ("external/libxml2/Android.bp","cc_library","libxml2"),
        ] {assert!(consumer.contains(&format!("\"{name}\",")));let text=fs::read_to_string(d.path().join(relative)).unwrap();let compact:String=text.chars().filter(|c|!c.is_whitespace()).collect();assert!(compact.contains(&format!("{kind}{{name:\"{name}\",")),"real original native provider missing: {name}");}
        assert!(!nativebridge_discovery_scope(&["com.android.hardware.audio.droidloom"]));
        for (relative,_,_,_)in AUDIO_LIBEXIF537_ORIGINALS {
            if relative.starts_with("external/libexif/libexif/")&&(relative.ends_with(".c")||relative.ends_with(".h")) {
                let text=fs::read_to_string(d.path().join(relative)).unwrap();
                for line in text.lines().map(str::trim).filter(|line|line.starts_with("#include")) {
                    let target=line.trim_start_matches("#include").trim().trim_matches(&['<','>','"'][..]);
                    if target.starts_with("libexif/"){assert!(d.path().join("external/libexif").join(target).is_file(),"missing original selected include {target}");}
                }
            }
        }
        validate_audio_libexif537_original_inputs(d.path(),SoongDependencyMode::AudioApexTargetClosure).unwrap();
    }
    fn write_vendor_policy_bundle_original_fixtures(root:&Path) {
        for (relative,raw) in [
            ("system/sepolicy/Android.bp",&include_bytes!("../tests/fixtures/vendor-policy-bundle-original/system/sepolicy/Android.bp")[..]),
            ("system/sepolicy/contexts/Android.bp",&include_bytes!("../tests/fixtures/vendor-policy-bundle-original/system/sepolicy/contexts/Android.bp")[..]),
            ("system/libhidl/vintfdata/Android.bp",&include_bytes!("../tests/fixtures/vendor-policy-bundle-original/system/libhidl/vintfdata/Android.bp")[..]),
            ("system/libvintf/Android.bp",&include_bytes!("../tests/fixtures/vendor-policy-bundle-original/system/libvintf/Android.bp")[..]),
            ("build/soong/android/vintf_data.go",&include_bytes!("../tests/fixtures/vendor-policy-bundle-original/build/soong/android/vintf_data.go")[..]),
        ] {let p=root.join(relative);fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,raw).unwrap();}
    }

    #[test]
    fn audio_sdk14_source_paths_keep_fixed_provider_and_only_public_cone() {
        let repo=Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let lock=droidloom_source::load_lock(&repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        let audio=SoongDependencyMode::AudioApexTargetClosure;
        validate_audio_sdk14_source_paths(&lock,audio).unwrap();
        let old:droidloom_source::SparseSourceLock=serde_json::from_str(include_str!("../../droidloom-source/tests/fixtures/audio-source536-before-sdk14.json")).unwrap();
        assert!(validate_audio_sdk14_source_paths(&old,audio).is_err());
        for case in 0..4 {
            let mut bad=lock.clone();let sdk=bad.projects.iter_mut().find(|p|p.path==Path::new("prebuilts/sdk")).unwrap();
            match case {0=>sdk.commit="0000000000000000000000000000000000000000".into(),1=>sdk.name="platform/other".into(),2=>sdk.sparse_paths.retain(|p|p!=Path::new("14/public")),_=>sdk.sparse_paths.push(PathBuf::from("14"))}
            assert!(validate_audio_sdk14_source_paths(&bad,audio).is_err());
        }
        for mode in [SoongDependencyMode::Strict,SoongDependencyMode::NativeBridgeTargetClosure,SoongDependencyMode::NativeEngineTargetClosure,SoongDependencyMode::MinigbmTargetClosure] {validate_audio_sdk14_source_paths(&old,mode).unwrap();}
    }

    #[test]
    fn vendor_policy_bundle_typed_request_keeps_audio_scope_and_distinct_receipt() {
        let request=FixedProductionRequest::VendorPolicyBundleOnAudioSource;
        let repo=Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        assert_eq!(selected_source_lock(repo,request.source_mode()).unwrap(),repo.join("android/manifest/audio-bridge-source-lock.json"));
        assert_eq!(request.source_mode(),SoongDependencyMode::AudioApexTargetClosure);
        assert_eq!(request.projection_targets(),["com.android.hardware.audio.droidloom"]);
        assert_eq!(request.requested_targets(),["selinux_policy_vendor","vendor_manifest.xml","vendor_compatibility_matrix.xml","checkvintf"]);
        assert!(request.validate("droidloom_arm64").is_err());
        assert!(FixedProductionRequest::Existing(SoongDependencyMode::AudioApexTargetClosure,VENDOR_POLICY_BUNDLE_TARGETS).validate("droidloom_x86_64").is_err());
        let names=request.policy_receipt_names().unwrap();
        assert_ne!(names,FixedProductionRequest::VendorPolicyOnAudioSource.policy_receipt_names().unwrap());
        assert_eq!(names.0,"droidloom-vendor-policy-bundle-build-inputs.json");
        assert_eq!(names.2,"droidloom-vendor-policy-bundle-normal-result.json");
        let value=request.description("droidloom_x86_64").unwrap();
        assert_eq!(value["source_release"],"cp2a");assert_eq!(value["build_variant"],"user");
        for key in ["QPR1_source_identity_claim","Audio_APEX_qualified","selected_cohort_policy_qualified","runtime_qualified"] {assert_eq!(value[key],false);}
    }

    #[test]
    fn vendor_policy_bundle_original_producers_reject_drift_missing_and_aliases() {
        use std::os::unix::fs::symlink;
        let d=tempfile::tempdir().unwrap();write_vendor_policy_bundle_original_fixtures(d.path());
        validate_vendor_policy_bundle_originals(d.path()).unwrap();
        for (relative,_,_) in VENDOR_POLICY_BUNDLE_ORIGINALS {
            let p=d.path().join(relative);let original=fs::read(&p).unwrap();
            fs::write(&p,b"changed native producer").unwrap();assert!(validate_vendor_policy_bundle_originals(d.path()).is_err());
            fs::remove_file(&p).unwrap();assert!(validate_vendor_policy_bundle_originals(d.path()).is_err());
            let same=d.path().join("same-original");fs::write(&same,&original).unwrap();
            symlink(&same,&p).unwrap();assert!(validate_vendor_policy_bundle_originals(d.path()).is_err());fs::remove_file(&p).unwrap();
            fs::hard_link(&same,&p).unwrap();assert!(validate_vendor_policy_bundle_originals(d.path()).is_err());fs::remove_file(&p).unwrap();
            fs::write(&p,original).unwrap();fs::remove_file(same).unwrap();validate_vendor_policy_bundle_originals(d.path()).unwrap();
        }
        let dir=d.path().join("system/libhidl/vintfdata");let moved=d.path().join("original-vintfdata");fs::rename(&dir,&moved).unwrap();symlink(&moved,&dir).unwrap();
        assert!(validate_vendor_policy_bundle_originals(d.path()).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn vendor_policy_bundle_real_command_overrides_inherited_debug_environment() {
        const PROBE:&str="DROIDLOOM_TEST_VENDOR_POLICY_BUNDLE_ENV_CHILD";
        if std::env::var_os(PROBE).is_none() {
            for inherited in ["userdebug","eng"] {
                let child=Command::new(std::env::current_exe().unwrap())
                    .args(["--exact","android::tests::vendor_policy_bundle_real_command_overrides_inherited_debug_environment","--test-threads=1"])
                    .env(PROBE,"1").env("TARGET_BUILD_VARIANT",inherited).env("TARGET_RELEASE","cp3a").env("TARGET_PRODUCT","wrong-product")
                    .env("ALLOW_MISSING_DEPENDENCIES","true").env("SELINUX_IGNORE_NEVERALLOWS","true").output().unwrap();
                assert!(child.status.success(),"{}",String::from_utf8_lossy(&child.stderr));
                assert!(String::from_utf8_lossy(&child.stdout).contains("1 passed; 0 failed"));
            }
            return;
        }
        use std::os::unix::fs::PermissionsExt;
        let d=tempfile::tempdir().unwrap();let executable=d.path().join("soong_ui");
        // This is an actual child argv/environment probe, never a Soong substitute.
        fs::write(&executable,b"#!/bin/sh\nset -eu\nprintf '%s\\n' \"$TARGET_BUILD_VARIANT\" \"$TARGET_RELEASE\" \"$TARGET_PRODUCT\" \"$ALLOW_MISSING_DEPENDENCIES\" \"$SELINUX_IGNORE_NEVERALLOWS\" \"$@\"\n").unwrap();
        fs::set_permissions(&executable,fs::Permissions::from_mode(0o700)).unwrap();
        let request=FixedProductionRequest::VendorPolicyBundleOnAudioSource;
        let selected=request.soong_targets(d.path(),"droidloom_x86_64").unwrap();
        let mut command=production_soong_command(d.path(),d.path(),d.path(),"droidloom_x86_64",6,&selected).unwrap();
        request.configure_dependencies(&mut command,"droidloom_x86_64").unwrap();
        let observed=command.output().unwrap();assert!(observed.status.success());assert!(observed.stderr.is_empty());
        assert_eq!(observed.stdout,b"user\ncp2a\ndroidloom_x86_64\nfalse\nfalse\n--make-mode\n-j6\nselinux_policy_vendor\nvendor_manifest.xml\nvendor_compatibility_matrix.xml\ncheckvintf\n");
    }

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


    fn write_depmod536_original_fixtures(root:&Path){
        let p=root.join("build/blueprint/bootstrap/bootstrap.go");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/blueprint/bootstrap/bootstrap.go")).unwrap();
        let p=root.join("build/blueprint/deptools/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/blueprint/deptools/Android.bp")).unwrap();
        let p=root.join("build/blueprint/pathtools/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/blueprint/pathtools/Android.bp")).unwrap();
        let p=root.join("build/soong/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/Android.bp")).unwrap();
        let p=root.join("build/soong/android/base_module_context.go");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/android/base_module_context.go")).unwrap();
        let p=root.join("build/soong/android/config.go");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/android/config.go")).unwrap();
        let p=root.join("build/soong/android/module.go");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/android/module.go")).unwrap();
        let p=root.join("build/soong/android/module_context.go");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/android/module_context.go")).unwrap();
        let p=root.join("build/soong/android/mutator.go");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/android/mutator.go")).unwrap();
        let p=root.join("build/soong/android/prebuilt_build_tool.go");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/android/prebuilt_build_tool.go")).unwrap();
        let p=root.join("build/soong/android/register.go");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/android/register.go")).unwrap();
        let p=root.join("build/soong/android/visibility.go");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/android/visibility.go")).unwrap();
        let p=root.join("build/soong/cmd/merge_zips/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/cmd/merge_zips/Android.bp")).unwrap();
        let p=root.join("build/soong/cmd/merge_zips/merge_zips.go");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/cmd/merge_zips/merge_zips.go")).unwrap();
        let p=root.join("build/soong/cmd/zipsync/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/cmd/zipsync/Android.bp")).unwrap();
        let p=root.join("build/soong/cmd/zipsync/zipsync.go");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/cmd/zipsync/zipsync.go")).unwrap();
        let p=root.join("build/soong/golang/golang.go");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/golang/golang.go")).unwrap();
        let p=root.join("build/soong/jar/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/jar/Android.bp")).unwrap();
        let p=root.join("build/soong/kernel/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/kernel/Android.bp")).unwrap();
        let p=root.join("build/soong/kernel/common/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/kernel/common/Android.bp")).unwrap();
        let p=root.join("build/soong/kernel/common/prebuilt_kernel_modules_common.go");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/kernel/common/prebuilt_kernel_modules_common.go")).unwrap();
        let p=root.join("build/soong/kernel/kernel_modules_builder/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/kernel/kernel_modules_builder/Android.bp")).unwrap();
        let p=root.join("build/soong/kernel/kernel_modules_builder/kernel_modules_builder.go");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/kernel/kernel_modules_builder/kernel_modules_builder.go")).unwrap();
        let p=root.join("build/soong/kernel/prebuilt_kernel_modules.go");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/kernel/prebuilt_kernel_modules.go")).unwrap();
        let p=root.join("build/soong/kernel/prebuilt_kernel_modules_test.go");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/kernel/prebuilt_kernel_modules_test.go")).unwrap();
        let p=root.join("build/soong/response/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/response/Android.bp")).unwrap();
        let p=root.join("build/soong/root.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/root.bp")).unwrap();
        let p=root.join("build/soong/third_party/zip/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/third_party/zip/Android.bp")).unwrap();
        let p=root.join("build/soong/zip/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/zip/Android.bp")).unwrap();
        let p=root.join("build/soong/zip/cmd/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/zip/cmd/Android.bp")).unwrap();
        let p=root.join("build/soong/zip/cmd/main.go");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/build/soong/zip/cmd/main.go")).unwrap();
        let p=root.join("external/kmod/.gitignore");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/.gitignore")).unwrap();
        let p=root.join("external/kmod/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/Android.bp")).unwrap();
        let p=root.join("external/kmod/BUILD.bazel");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/BUILD.bazel")).unwrap();
        let p=root.join("external/kmod/CODING-STYLE");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/CODING-STYLE")).unwrap();
        let p=root.join("external/kmod/COPYING");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/COPYING")).unwrap();
        let p=root.join("external/kmod/METADATA");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/METADATA")).unwrap();
        let p=root.join("external/kmod/MODULE_LICENSE_LGPL");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/MODULE_LICENSE_LGPL")).unwrap();
        let p=root.join("external/kmod/Makefile.am");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/Makefile.am")).unwrap();
        let p=root.join("external/kmod/NEWS");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/NEWS")).unwrap();
        let p=root.join("external/kmod/NOTICE");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/NOTICE")).unwrap();
        let p=root.join("external/kmod/OWNERS");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/OWNERS")).unwrap();
        let p=root.join("external/kmod/README.md");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/README.md")).unwrap();
        let p=root.join("external/kmod/TODO");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/TODO")).unwrap();
        let p=root.join("external/kmod/android/port.h");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/android/port.h")).unwrap();
        let p=root.join("external/kmod/autogen.sh");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/autogen.sh")).unwrap();
        let p=root.join("external/kmod/config.h");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/config.h")).unwrap();
        let p=root.join("external/kmod/config.h.in");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/config.h.in")).unwrap();
        let p=root.join("external/kmod/configure.ac");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/configure.ac")).unwrap();
        let p=root.join("external/kmod/libkmod/.gitignore");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/.gitignore")).unwrap();
        let p=root.join("external/kmod/libkmod/COPYING");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/COPYING")).unwrap();
        let p=root.join("external/kmod/libkmod/Makefile");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/Makefile")).unwrap();
        let p=root.join("external/kmod/libkmod/README");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/README")).unwrap();
        let p=root.join("external/kmod/libkmod/docs/.gitignore");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/docs/.gitignore")).unwrap();
        let p=root.join("external/kmod/libkmod/docs/Makefile.am");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/docs/Makefile.am")).unwrap();
        let p=root.join("external/kmod/libkmod/docs/libkmod-docs.xml");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/docs/libkmod-docs.xml")).unwrap();
        let p=root.join("external/kmod/libkmod/docs/libkmod-sections.txt");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/docs/libkmod-sections.txt")).unwrap();
        let p=root.join("external/kmod/libkmod/docs/version.xml.in");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/docs/version.xml.in")).unwrap();
        let p=root.join("external/kmod/libkmod/libkmod-builtin.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/libkmod-builtin.c")).unwrap();
        let p=root.join("external/kmod/libkmod/libkmod-config.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/libkmod-config.c")).unwrap();
        let p=root.join("external/kmod/libkmod/libkmod-elf.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/libkmod-elf.c")).unwrap();
        let p=root.join("external/kmod/libkmod/libkmod-file.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/libkmod-file.c")).unwrap();
        let p=root.join("external/kmod/libkmod/libkmod-index.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/libkmod-index.c")).unwrap();
        let p=root.join("external/kmod/libkmod/libkmod-index.h");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/libkmod-index.h")).unwrap();
        let p=root.join("external/kmod/libkmod/libkmod-internal.h");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/libkmod-internal.h")).unwrap();
        let p=root.join("external/kmod/libkmod/libkmod-list.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/libkmod-list.c")).unwrap();
        let p=root.join("external/kmod/libkmod/libkmod-module.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/libkmod-module.c")).unwrap();
        let p=root.join("external/kmod/libkmod/libkmod-signature.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/libkmod-signature.c")).unwrap();
        let p=root.join("external/kmod/libkmod/libkmod.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/libkmod.c")).unwrap();
        let p=root.join("external/kmod/libkmod/libkmod.h");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/libkmod.h")).unwrap();
        let p=root.join("external/kmod/libkmod/libkmod.pc.in");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/libkmod.pc.in")).unwrap();
        let p=root.join("external/kmod/libkmod/libkmod.sym");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/libkmod/libkmod.sym")).unwrap();
        let p=root.join("external/kmod/rules.mk");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/rules.mk")).unwrap();
        let p=root.join("external/kmod/shared/.gitignore");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/shared/.gitignore")).unwrap();
        let p=root.join("external/kmod/shared/array.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/shared/array.c")).unwrap();
        let p=root.join("external/kmod/shared/array.h");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/shared/array.h")).unwrap();
        let p=root.join("external/kmod/shared/hash.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/shared/hash.c")).unwrap();
        let p=root.join("external/kmod/shared/hash.h");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/shared/hash.h")).unwrap();
        let p=root.join("external/kmod/shared/macro.h");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/shared/macro.h")).unwrap();
        let p=root.join("external/kmod/shared/missing.h");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/shared/missing.h")).unwrap();
        let p=root.join("external/kmod/shared/scratchbuf.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/shared/scratchbuf.c")).unwrap();
        let p=root.join("external/kmod/shared/scratchbuf.h");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/shared/scratchbuf.h")).unwrap();
        let p=root.join("external/kmod/shared/strbuf.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/shared/strbuf.c")).unwrap();
        let p=root.join("external/kmod/shared/strbuf.h");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/shared/strbuf.h")).unwrap();
        let p=root.join("external/kmod/shared/util.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/shared/util.c")).unwrap();
        let p=root.join("external/kmod/shared/util.h");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/shared/util.h")).unwrap();
        let p=root.join("external/kmod/tools/.gitignore");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/tools/.gitignore")).unwrap();
        let p=root.join("external/kmod/tools/COPYING");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/tools/COPYING")).unwrap();
        let p=root.join("external/kmod/tools/Makefile");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/tools/Makefile")).unwrap();
        let p=root.join("external/kmod/tools/depmod.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/tools/depmod.c")).unwrap();
        let p=root.join("external/kmod/tools/insmod.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/tools/insmod.c")).unwrap();
        let p=root.join("external/kmod/tools/kmod.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/tools/kmod.c")).unwrap();
        let p=root.join("external/kmod/tools/kmod.h");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/tools/kmod.h")).unwrap();
        let p=root.join("external/kmod/tools/kmod.pc.in");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/tools/kmod.pc.in")).unwrap();
        let p=root.join("external/kmod/tools/log.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/tools/log.c")).unwrap();
        let p=root.join("external/kmod/tools/log.h");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/tools/log.h")).unwrap();
        let p=root.join("external/kmod/tools/lsmod.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/tools/lsmod.c")).unwrap();
        let p=root.join("external/kmod/tools/modinfo.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/tools/modinfo.c")).unwrap();
        let p=root.join("external/kmod/tools/modprobe.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/tools/modprobe.c")).unwrap();
        let p=root.join("external/kmod/tools/port.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/tools/port.c")).unwrap();
        let p=root.join("external/kmod/tools/rmmod.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/tools/rmmod.c")).unwrap();
        let p=root.join("external/kmod/tools/static-nodes.c");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/external/kmod/tools/static-nodes.c")).unwrap();
        let p=root.join("prebuilts/clang/host/linux-x86/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-depmod536-original/prebuilts/clang/host/linux-x86/Android.bp")).unwrap();
    }
    #[test]
    fn audio_depmod536_requires_the_actual_same_sp_host_provider_and_exact_cones() {
        let repo=Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();let lock=droidloom_source::load_lock(&repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();let audio=SoongDependencyMode::AudioApexTargetClosure;validate_audio_depmod536_source_paths(&lock,audio).unwrap();
        let old:droidloom_source::SparseSourceLock=serde_json::from_str(include_str!("../../droidloom-source/tests/fixtures/audio-source535-before-depmod.json")).unwrap();assert_eq!(old.projects.len(),535);assert!(validate_audio_depmod536_source_paths(&old,audio).is_err());
        let mut wrong=lock.clone();wrong.projects.iter_mut().find(|p|p.path==Path::new("external/kmod")).unwrap().commit="0000000000000000000000000000000000000000".into();assert!(validate_audio_depmod536_source_paths(&wrong,audio).is_err());
        for cone in ["android","libkmod","shared","tools"]{let mut narrow=lock.clone();narrow.projects.iter_mut().find(|p|p.path==Path::new("external/kmod")).unwrap().sparse_paths.retain(|p|p!=Path::new(cone));assert!(validate_audio_depmod536_source_paths(&narrow,audio).is_err());}
        for mode in [SoongDependencyMode::Strict,SoongDependencyMode::NativeBridgeTargetClosure,SoongDependencyMode::NativeEngineTargetClosure,SoongDependencyMode::MinigbmTargetClosure]{validate_audio_depmod536_source_paths(&old,mode).unwrap();}
    }
    #[test]
    fn audio_depmod536_whole_original_factory_tools_and_package_reject_drift_missing_or_alias() {
        use std::os::unix::fs::symlink;
        let d=tempfile::tempdir().unwrap();write_depmod536_original_fixtures(d.path());let mode=SoongDependencyMode::AudioApexTargetClosure;validate_audio_depmod536_original_inputs(d.path(),mode).unwrap();
        for relative in ["external/kmod/Android.bp","external/kmod/tools/depmod.c","build/soong/kernel/prebuilt_kernel_modules.go","build/soong/cmd/merge_zips/Android.bp","prebuilts/clang/host/linux-x86/Android.bp"]{
            let p=d.path().join(relative);let raw=fs::read(&p).unwrap();fs::write(&p,b"changed original").unwrap();assert!(validate_audio_depmod536_original_inputs(d.path(),mode).is_err());fs::remove_file(&p).unwrap();assert!(validate_audio_depmod536_original_inputs(d.path(),mode).is_err());let target=d.path().join("same-original");fs::write(&target,&raw).unwrap();symlink(&target,&p).unwrap();assert!(validate_audio_depmod536_original_inputs(d.path(),mode).is_err());fs::remove_file(&p).unwrap();fs::write(&p,raw).unwrap();}
        validate_audio_depmod536_original_inputs(d.path(),mode).unwrap();validate_audio_depmod536_original_inputs(Path::new("/not-present"),SoongDependencyMode::Strict).unwrap();
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

    fn write_generic535_original_fixtures(root:&Path) {
        let p=root.join("development/cmds/monkey/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/development/cmds/monkey/Android.bp")).unwrap();
        let p=root.join("development/cmds/monkey/libmonkey_jni/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/development/cmds/monkey/libmonkey_jni/Android.bp")).unwrap();
        let p=root.join("external/angle/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/angle/Android.bp")).unwrap();
        let p=root.join("external/angle/android/cts/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/angle/android/cts/Android.bp")).unwrap();
        let p=root.join("external/bazelbuild-remote-apis/build/bazel/remote/execution/v2/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/bazelbuild-remote-apis/build/bazel/remote/execution/v2/Android.bp")).unwrap();
        let p=root.join("external/bazelbuild-remote-apis/build/bazel/semver/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/bazelbuild-remote-apis/build/bazel/semver/Android.bp")).unwrap();
        let p=root.join("external/crosvm/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/Android.bp")).unwrap();
        let p=root.join("external/crosvm/aarch64/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/aarch64/Android.bp")).unwrap();
        let p=root.join("external/crosvm/aarch64/cargo2android_arch.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/aarch64/cargo2android_arch.bp")).unwrap();
        let p=root.join("external/crosvm/aarch64_sys_reg/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/aarch64_sys_reg/Android.bp")).unwrap();
        let p=root.join("external/crosvm/acpi_tables/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/acpi_tables/Android.bp")).unwrap();
        let p=root.join("external/crosvm/android_audio/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/android_audio/Android.bp")).unwrap();
        let p=root.join("external/crosvm/arch/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/arch/Android.bp")).unwrap();
        let p=root.join("external/crosvm/argh_helpers/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/argh_helpers/Android.bp")).unwrap();
        let p=root.join("external/crosvm/audio_util/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/audio_util/Android.bp")).unwrap();
        let p=root.join("external/crosvm/base/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/base/Android.bp")).unwrap();
        let p=root.join("external/crosvm/base/base_event_token_derive/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/base/base_event_token_derive/Android.bp")).unwrap();
        let p=root.join("external/crosvm/bit_field/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/bit_field/Android.bp")).unwrap();
        let p=root.join("external/crosvm/bit_field/bit_field_derive/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/bit_field/bit_field_derive/Android.bp")).unwrap();
        let p=root.join("external/crosvm/cargo2android_defaults.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/cargo2android_defaults.bp")).unwrap();
        let p=root.join("external/crosvm/common/audio_streams/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/common/audio_streams/Android.bp")).unwrap();
        let p=root.join("external/crosvm/common/balloon_control/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/common/balloon_control/Android.bp")).unwrap();
        let p=root.join("external/crosvm/common/data_model/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/common/data_model/Android.bp")).unwrap();
        let p=root.join("external/crosvm/common/sync/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/common/sync/Android.bp")).unwrap();
        let p=root.join("external/crosvm/cros_async/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/cros_async/Android.bp")).unwrap();
        let p=root.join("external/crosvm/cros_fdt/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/cros_fdt/Android.bp")).unwrap();
        let p=root.join("external/crosvm/cros_tracing/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/cros_tracing/Android.bp")).unwrap();
        let p=root.join("external/crosvm/cros_tracing_types/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/cros_tracing_types/Android.bp")).unwrap();
        let p=root.join("external/crosvm/crosvm_cli/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/crosvm_cli/Android.bp")).unwrap();
        let p=root.join("external/crosvm/crosvm_control/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/crosvm_control/Android.bp")).unwrap();
        let p=root.join("external/crosvm/devices/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/devices/Android.bp")).unwrap();
        let p=root.join("external/crosvm/disk/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/disk/Android.bp")).unwrap();
        let p=root.join("external/crosvm/ext2/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/ext2/Android.bp")).unwrap();
        let p=root.join("external/crosvm/fuse/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/fuse/Android.bp")).unwrap();
        let p=root.join("external/crosvm/gpu_display/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/gpu_display/Android.bp")).unwrap();
        let p=root.join("external/crosvm/gpu_display/cargo2android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/gpu_display/cargo2android.bp")).unwrap();
        let p=root.join("external/crosvm/hypervisor/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/hypervisor/Android.bp")).unwrap();
        let p=root.join("external/crosvm/hypervisor/hypervisor_test_macro/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/hypervisor/hypervisor_test_macro/Android.bp")).unwrap();
        let p=root.join("external/crosvm/io_uring/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/io_uring/Android.bp")).unwrap();
        let p=root.join("external/crosvm/jail/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/jail/Android.bp")).unwrap();
        let p=root.join("external/crosvm/kernel_cmdline/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/kernel_cmdline/Android.bp")).unwrap();
        let p=root.join("external/crosvm/kernel_loader/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/kernel_loader/Android.bp")).unwrap();
        let p=root.join("external/crosvm/kvm_sys/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/kvm_sys/Android.bp")).unwrap();
        let p=root.join("external/crosvm/libcras_stub/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/libcras_stub/Android.bp")).unwrap();
        let p=root.join("external/crosvm/linux_input_sys/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/linux_input_sys/Android.bp")).unwrap();
        let p=root.join("external/crosvm/metrics/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/metrics/Android.bp")).unwrap();
        let p=root.join("external/crosvm/metrics_events/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/metrics_events/Android.bp")).unwrap();
        let p=root.join("external/crosvm/net_sys/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/net_sys/Android.bp")).unwrap();
        let p=root.join("external/crosvm/net_util/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/net_util/Android.bp")).unwrap();
        let p=root.join("external/crosvm/power_monitor/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/power_monitor/Android.bp")).unwrap();
        let p=root.join("external/crosvm/proc_init/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/proc_init/Android.bp")).unwrap();
        let p=root.join("external/crosvm/protos/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/protos/Android.bp")).unwrap();
        let p=root.join("external/crosvm/protos/cargo2android_protobuf.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/protos/cargo2android_protobuf.bp")).unwrap();
        let p=root.join("external/crosvm/resources/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/resources/Android.bp")).unwrap();
        let p=root.join("external/crosvm/riscv64/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/riscv64/Android.bp")).unwrap();
        let p=root.join("external/crosvm/serde_keyvalue/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/serde_keyvalue/Android.bp")).unwrap();
        let p=root.join("external/crosvm/serde_keyvalue/serde_keyvalue_derive/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/serde_keyvalue/serde_keyvalue_derive/Android.bp")).unwrap();
        let p=root.join("external/crosvm/snapshot/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/snapshot/Android.bp")).unwrap();
        let p=root.join("external/crosvm/swap/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/swap/Android.bp")).unwrap();
        let p=root.join("external/crosvm/third_party/vmm_vhost/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/third_party/vmm_vhost/Android.bp")).unwrap();
        let p=root.join("external/crosvm/usb_sys/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/usb_sys/Android.bp")).unwrap();
        let p=root.join("external/crosvm/usb_util/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/usb_util/Android.bp")).unwrap();
        let p=root.join("external/crosvm/vendor/generic/crypto/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/vendor/generic/crypto/Android.bp")).unwrap();
        let p=root.join("external/crosvm/vendor/generic/metrics/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/vendor/generic/metrics/Android.bp")).unwrap();
        let p=root.join("external/crosvm/vendor/generic/metrics_events/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/vendor/generic/metrics_events/Android.bp")).unwrap();
        let p=root.join("external/crosvm/vendor/generic/proc_init/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/vendor/generic/proc_init/Android.bp")).unwrap();
        let p=root.join("external/crosvm/vendor/generic/vm_control/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/vendor/generic/vm_control/Android.bp")).unwrap();
        let p=root.join("external/crosvm/vfio_sys/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/vfio_sys/Android.bp")).unwrap();
        let p=root.join("external/crosvm/vhost/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/vhost/Android.bp")).unwrap();
        let p=root.join("external/crosvm/virtio_sys/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/virtio_sys/Android.bp")).unwrap();
        let p=root.join("external/crosvm/vm_control/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/vm_control/Android.bp")).unwrap();
        let p=root.join("external/crosvm/vm_memory/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/vm_memory/Android.bp")).unwrap();
        let p=root.join("external/crosvm/x86_64/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/crosvm/x86_64/Android.bp")).unwrap();
        let p=root.join("external/dnsmasq/src/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/dnsmasq/src/Android.bp")).unwrap();
        let p=root.join("external/ethtool/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/ethtool/Android.bp")).unwrap();
        let p=root.join("external/fsck_msdos/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/fsck_msdos/Android.bp")).unwrap();
        let p=root.join("external/googleapis/google/bytestream/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/googleapis/google/bytestream/Android.bp")).unwrap();
        let p=root.join("external/googleapis/google/longrunning/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/googleapis/google/longrunning/Android.bp")).unwrap();
        let p=root.join("external/iproute2/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/iproute2/Android.bp")).unwrap();
        let p=root.join("external/iproute2/ip/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/iproute2/ip/Android.bp")).unwrap();
        let p=root.join("external/iproute2/lib/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/iproute2/lib/Android.bp")).unwrap();
        let p=root.join("external/iproute2/misc/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/iproute2/misc/Android.bp")).unwrap();
        let p=root.join("external/iproute2/tc/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/iproute2/tc/Android.bp")).unwrap();
        let p=root.join("external/iptables/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/iptables/Android.bp")).unwrap();
        let p=root.join("external/iptables/extensions/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/iptables/extensions/Android.bp")).unwrap();
        let p=root.join("external/iptables/iptables/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/iptables/iptables/Android.bp")).unwrap();
        let p=root.join("external/iptables/libiptc/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/iptables/libiptc/Android.bp")).unwrap();
        let p=root.join("external/iptables/libxtables/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/iptables/libxtables/Android.bp")).unwrap();
        let p=root.join("external/iputils/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/iputils/Android.bp")).unwrap();
        let p=root.join("external/jackson-core/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/jackson-core/Android.bp")).unwrap();
        let p=root.join("external/jline/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/jline/Android.bp")).unwrap();
        let p=root.join("external/ksoap2/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/ksoap2/Android.bp")).unwrap();
        let p=root.join("external/libcups/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/libcups/Android.bp")).unwrap();
        let p=root.join("external/libcxx/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/libcxx/Android.bp")).unwrap();
        let p=root.join("external/libcxxabi/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/libcxxabi/Android.bp")).unwrap();
        let p=root.join("external/libffi/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/libffi/Android.bp")).unwrap();
        let p=root.join("external/liblc3/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/liblc3/Android.bp")).unwrap();
        let p=root.join("external/libldac/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/libldac/Android.bp")).unwrap();
        let p=root.join("external/lua/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/lua/Android.bp")).unwrap();
        let p=root.join("external/marisa-trie/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/marisa-trie/Android.bp")).unwrap();
        let p=root.join("external/mbedtls/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mbedtls/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/bin/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/bin/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/include/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/include/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/include/vulkan/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/include/vulkan/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/android_stub/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/android_stub/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/c11/impl/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/c11/impl/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/compiler/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/compiler/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/compiler/glsl/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/compiler/glsl/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/compiler/isaspec/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/compiler/isaspec/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/compiler/nir/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/compiler/nir/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/compiler/spirv/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/compiler/spirv/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/auxiliary/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/auxiliary/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/auxiliary/cso_cache/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/auxiliary/cso_cache/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/auxiliary/draw/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/auxiliary/draw/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/auxiliary/driver_ddebug/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/auxiliary/driver_ddebug/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/auxiliary/driver_noop/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/auxiliary/driver_noop/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/auxiliary/driver_trace/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/auxiliary/driver_trace/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/auxiliary/gallivm/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/auxiliary/gallivm/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/auxiliary/hud/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/auxiliary/hud/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/auxiliary/indices/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/auxiliary/indices/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/auxiliary/nir/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/auxiliary/nir/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/auxiliary/pipe-loader/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/auxiliary/pipe-loader/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/auxiliary/pipebuffer/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/auxiliary/pipebuffer/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/auxiliary/postprocess/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/auxiliary/postprocess/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/auxiliary/renderonly/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/auxiliary/renderonly/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/auxiliary/rtasm/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/auxiliary/rtasm/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/auxiliary/tessellator/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/auxiliary/tessellator/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/auxiliary/tgsi/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/auxiliary/tgsi/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/auxiliary/translate/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/auxiliary/translate/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/auxiliary/util/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/auxiliary/util/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/auxiliary/vl/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/auxiliary/vl/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/drivers/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/drivers/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/drivers/llvmpipe/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/drivers/llvmpipe/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/drivers/zink/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/drivers/zink/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/frontends/lavapipe/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/frontends/lavapipe/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/frontends/lavapipe/nir/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/frontends/lavapipe/nir/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/include/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/include/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/include/pipe/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/include/pipe/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/winsys/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/winsys/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/winsys/sw/null/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/winsys/sw/null/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gallium/winsys/sw/wrapper/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gallium/winsys/sw/wrapper/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gfxstream/aemu/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gfxstream/aemu/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gfxstream/aemu/include/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gfxstream/aemu/include/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gfxstream/codegen/scripts/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gfxstream/codegen/scripts/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gfxstream/codegen/xml/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gfxstream/codegen/xml/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gfxstream/guest/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gfxstream/guest/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gfxstream/guest/GoldfishAddressSpace/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gfxstream/guest/GoldfishAddressSpace/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gfxstream/guest/GoldfishAddressSpace/include/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gfxstream/guest/GoldfishAddressSpace/include/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gfxstream/guest/android/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gfxstream/guest/android/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gfxstream/guest/android/include/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gfxstream/guest/android/include/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gfxstream/guest/connection-manager/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gfxstream/guest/connection-manager/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gfxstream/guest/iostream/include/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gfxstream/guest/iostream/include/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gfxstream/guest/platform/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gfxstream/guest/platform/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gfxstream/guest/platform/drm/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gfxstream/guest/platform/drm/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gfxstream/guest/platform/include/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gfxstream/guest/platform/include/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gfxstream/guest/platform/kumquat/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gfxstream/guest/platform/kumquat/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gfxstream/guest/platform/kumquat/vulkan-mapper/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gfxstream/guest/platform/kumquat/vulkan-mapper/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gfxstream/guest/vulkan/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gfxstream/guest/vulkan/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gfxstream/guest/vulkan/stubs/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gfxstream/guest/vulkan/stubs/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gfxstream/guest/vulkan_enc/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gfxstream/guest/vulkan_enc/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gtest/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gtest/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gtest/include/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gtest/include/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/gtest/src/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/gtest/src/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/loader/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/loader/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/tool/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/tool/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/tool/pps/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/tool/pps/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/util/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/util/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/util/blake3/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/util/blake3/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/util/format/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/util/format/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/util/perf/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/util/perf/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/util/rust/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/util/rust/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/util/sha1/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/util/sha1/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/util/u_gralloc/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/util/u_gralloc/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/virtio/protocols/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/virtio/protocols/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/virtio/virtgpu_kumquat/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/virtio/virtgpu_kumquat/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/virtio/virtgpu_kumquat_ffi/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/virtio/virtgpu_kumquat_ffi/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/virtio/virtgpu_kumquat_ffi/include/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/virtio/virtgpu_kumquat_ffi/include/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/vulkan/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/vulkan/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/vulkan/registry/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/vulkan/registry/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/vulkan/runtime/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/vulkan/runtime/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/vulkan/runtime/bvh/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/vulkan/runtime/bvh/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/vulkan/runtime/radix_sort/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/vulkan/runtime/radix_sort/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/vulkan/runtime/radix_sort/common/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/vulkan/runtime/radix_sort/common/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/vulkan/runtime/radix_sort/common/vk/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/vulkan/runtime/radix_sort/common/vk/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/vulkan/runtime/radix_sort/shaders/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/vulkan/runtime/radix_sort/shaders/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/vulkan/runtime/rmv/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/vulkan/runtime/rmv/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/vulkan/util/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/vulkan/util/Android.bp")).unwrap();
        let p=root.join("external/mesa3d/src/vulkan/wsi/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/mesa3d/src/vulkan/wsi/Android.bp")).unwrap();
        let p=root.join("external/musl/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/musl/Android.bp")).unwrap();
        let p=root.join("external/musl/sources.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/musl/sources.bp")).unwrap();
        let p=root.join("external/neven/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/neven/Android.bp")).unwrap();
        let p=root.join("external/obex/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/obex/Android.bp")).unwrap();
        let p=root.join("external/openthread/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/openthread/Android.bp")).unwrap();
        let p=root.join("external/python/jinja/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/python/jinja/Android.bp")).unwrap();
        let p=root.join("external/python/jinja/src/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/python/jinja/src/Android.bp")).unwrap();
        let p=root.join("external/python/mako/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/python/mako/Android.bp")).unwrap();
        let p=root.join("external/python/markupsafe/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/python/markupsafe/Android.bp")).unwrap();
        let p=root.join("external/python/markupsafe/src/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/python/markupsafe/src/Android.bp")).unwrap();
        let p=root.join("external/rust/android-crates-io/crates/grpcio-sys/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/rust/android-crates-io/crates/grpcio-sys/Android.bp")).unwrap();
        let p=root.join("external/rust/crates/v4l2r/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/rust/crates/v4l2r/Android.bp")).unwrap();
        let p=root.join("external/rust/crates/v4l2r/android/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/rust/crates/v4l2r/android/Android.bp")).unwrap();
        let p=root.join("external/rust/crates/v4l2r/android/srcs.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/rust/crates/v4l2r/android/srcs.bp")).unwrap();
        let p=root.join("external/rust/crates/v4l2r/lib/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/rust/crates/v4l2r/lib/Android.bp")).unwrap();
        let p=root.join("external/rust/crates/v4l2r/utils/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/rust/crates/v4l2r/utils/Android.bp")).unwrap();
        let p=root.join("external/rust/rutabaga_gfx/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/rust/rutabaga_gfx/Android.bp")).unwrap();
        let p=root.join("external/rust/rutabaga_gfx/kumquat/server/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/rust/rutabaga_gfx/kumquat/server/Android.bp")).unwrap();
        let p=root.join("external/rust/rutabaga_gfx/third_party/mesa3d/src/magma/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/rust/rutabaga_gfx/third_party/mesa3d/src/magma/Android.bp")).unwrap();
        let p=root.join("external/rust/rutabaga_gfx/third_party/mesa3d/src/util/rust/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/rust/rutabaga_gfx/third_party/mesa3d/src/util/rust/Android.bp")).unwrap();
        let p=root.join("external/rust/rutabaga_gfx/third_party/mesa3d/src/virtio/protocols/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/rust/rutabaga_gfx/third_party/mesa3d/src/virtio/protocols/Android.bp")).unwrap();
        let p=root.join("external/rust/rutabaga_gfx/third_party/mesa3d/src/virtio/virtgpu_kumquat/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/rust/rutabaga_gfx/third_party/mesa3d/src/virtio/virtgpu_kumquat/Android.bp")).unwrap();
        let p=root.join("external/swiftshader/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/swiftshader/Android.bp")).unwrap();
        let p=root.join("external/swiftshader/src/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/swiftshader/src/Android.bp")).unwrap();
        let p=root.join("external/swiftshader/third_party/SPIRV-Headers/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/swiftshader/third_party/SPIRV-Headers/Android.bp")).unwrap();
        let p=root.join("external/swiftshader/third_party/SPIRV-Tools/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/swiftshader/third_party/SPIRV-Tools/Android.bp")).unwrap();
        let p=root.join("external/swiftshader/third_party/astc-encoder/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/swiftshader/third_party/astc-encoder/Android.bp")).unwrap();
        let p=root.join("external/swiftshader/third_party/llvm-10.0/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/swiftshader/third_party/llvm-10.0/Android.bp")).unwrap();
        let p=root.join("external/swiftshader/third_party/llvm-16.0/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/swiftshader/third_party/llvm-16.0/Android.bp")).unwrap();
        let p=root.join("external/swiftshader/third_party/llvm-16.0/scripts/template_Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/swiftshader/third_party/llvm-16.0/scripts/template_Android.bp")).unwrap();
        let p=root.join("external/swiftshader/third_party/llvm-subzero/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/swiftshader/third_party/llvm-subzero/Android.bp")).unwrap();
        let p=root.join("external/swiftshader/third_party/marl/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/swiftshader/third_party/marl/Android.bp")).unwrap();
        let p=root.join("external/virtio-media/device/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/virtio-media/device/Android.bp")).unwrap();
        let p=root.join("external/wayland-protocols/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/wayland-protocols/Android.bp")).unwrap();
        let p=root.join("external/wayland/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/wayland/Android.bp")).unwrap();
        let p=root.join("external/wpa_supplicant_8/wpa_supplicant/aidl/config/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/external/wpa_supplicant_8/wpa_supplicant/aidl/config/Android.bp")).unwrap();
        let p=root.join("frameworks/compile/libbcc/tools/bcc/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/compile/libbcc/tools/bcc/Android.bp")).unwrap();
        let p=root.join("frameworks/compile/mclinker/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/compile/mclinker/Android.bp")).unwrap();
        let p=root.join("frameworks/compile/mclinker/lib/ADT/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/compile/mclinker/lib/ADT/Android.bp")).unwrap();
        let p=root.join("frameworks/compile/mclinker/lib/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/compile/mclinker/lib/Android.bp")).unwrap();
        let p=root.join("frameworks/compile/mclinker/lib/Core/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/compile/mclinker/lib/Core/Android.bp")).unwrap();
        let p=root.join("frameworks/compile/mclinker/lib/Fragment/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/compile/mclinker/lib/Fragment/Android.bp")).unwrap();
        let p=root.join("frameworks/compile/mclinker/lib/LD/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/compile/mclinker/lib/LD/Android.bp")).unwrap();
        let p=root.join("frameworks/compile/mclinker/lib/MC/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/compile/mclinker/lib/MC/Android.bp")).unwrap();
        let p=root.join("frameworks/compile/mclinker/lib/Object/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/compile/mclinker/lib/Object/Android.bp")).unwrap();
        let p=root.join("frameworks/compile/mclinker/lib/Script/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/compile/mclinker/lib/Script/Android.bp")).unwrap();
        let p=root.join("frameworks/compile/mclinker/lib/Support/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/compile/mclinker/lib/Support/Android.bp")).unwrap();
        let p=root.join("frameworks/compile/mclinker/lib/Target/AArch64/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/compile/mclinker/lib/Target/AArch64/Android.bp")).unwrap();
        let p=root.join("frameworks/compile/mclinker/lib/Target/AArch64/TargetInfo/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/compile/mclinker/lib/Target/AArch64/TargetInfo/Android.bp")).unwrap();
        let p=root.join("frameworks/compile/mclinker/lib/Target/ARM/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/compile/mclinker/lib/Target/ARM/Android.bp")).unwrap();
        let p=root.join("frameworks/compile/mclinker/lib/Target/ARM/TargetInfo/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/compile/mclinker/lib/Target/ARM/TargetInfo/Android.bp")).unwrap();
        let p=root.join("frameworks/compile/mclinker/lib/Target/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/compile/mclinker/lib/Target/Android.bp")).unwrap();
        let p=root.join("frameworks/compile/mclinker/lib/Target/Mips/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/compile/mclinker/lib/Target/Mips/Android.bp")).unwrap();
        let p=root.join("frameworks/compile/mclinker/lib/Target/Mips/TargetInfo/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/compile/mclinker/lib/Target/Mips/TargetInfo/Android.bp")).unwrap();
        let p=root.join("frameworks/compile/mclinker/lib/Target/X86/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/compile/mclinker/lib/Target/X86/Android.bp")).unwrap();
        let p=root.join("frameworks/compile/mclinker/lib/Target/X86/TargetInfo/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/compile/mclinker/lib/Target/X86/TargetInfo/Android.bp")).unwrap();
        let p=root.join("frameworks/compile/mclinker/tools/mcld/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/compile/mclinker/tools/mcld/Android.bp")).unwrap();
        let p=root.join("frameworks/opt/vcard/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/opt/vcard/Android.bp")).unwrap();
        let p=root.join("frameworks/opt/vcard/tests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/frameworks/opt/vcard/tests/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/common/base/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/common/base/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/common/detector/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/common/detector/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/common/detector/shaders/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/common/detector/shaders/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/common/etc/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/common/etc/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/common/image/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/common/image/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/common/logging/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/common/logging/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/common/testenv/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/common/testenv/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/common/utils/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/common/utils/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/guest/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/guest/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/guest/GLESv1/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/guest/GLESv1/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/guest/GLESv1_enc/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/guest/GLESv1_enc/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/guest/GLESv2/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/guest/GLESv2/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/guest/GLESv2_enc/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/guest/GLESv2_enc/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/guest/OpenglCodecCommon/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/guest/OpenglCodecCommon/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/guest/OpenglSystemCommon/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/guest/OpenglSystemCommon/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/guest/android-emu/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/guest/android-emu/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/guest/egl/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/guest/egl/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/guest/gralloc_cb/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/guest/gralloc_cb/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/guest/include/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/guest/include/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/guest/qemupipe/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/guest/qemupipe/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/guest/renderControl_enc/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/guest/renderControl_enc/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/guest/rendercontrol/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/guest/rendercontrol/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/address_space/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/address_space/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/common/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/common/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/compressed_textures/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/compressed_textures/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/decoder_common/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/decoder_common/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/features/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/features/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/gl/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/gl/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/gl/OpenGLESDispatch/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/gl/OpenGLESDispatch/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/gl/gles1_dec/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/gl/gles1_dec/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/gl/gles2_dec/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/gl/gles2_dec/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/gl/glestranslator/common/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/gl/glestranslator/common/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/gl/glestranslator/egl/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/gl/glestranslator/egl/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/gl/glestranslator/gles_cm/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/gl/glestranslator/gles_cm/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/gl/glestranslator/gles_v2/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/gl/glestranslator/gles_v2/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/gl/glsnapshot/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/gl/glsnapshot/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/iostream/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/iostream/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/library/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/library/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/renderControl_dec/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/renderControl_dec/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/renderdoc/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/renderdoc/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/snapshot/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/snapshot/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/testlibs/oswindow/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/testlibs/oswindow/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/testlibs/support/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/testlibs/support/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/tracing/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/tracing/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/vulkan/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/vulkan/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/vulkan/cereal/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/vulkan/cereal/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/vulkan/cereal/common/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/vulkan/cereal/common/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/host/vulkan/emulated_textures/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/host/vulkan/emulated_textures/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/tests/end2end/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/tests/end2end/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/third_party/astc-encoder/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/third_party/astc-encoder/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/third_party/drm/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/third_party/drm/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/third_party/glm/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/third_party/glm/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/third_party/opengl/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/third_party/opengl/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/third_party/renderdoc/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/third_party/renderdoc/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/third_party/stb/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/third_party/stb/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/third_party/vulkan/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/third_party/vulkan/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/third_party/x11/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/third_party/x11/Android.bp")).unwrap();
        let p=root.join("hardware/google/gfxstream/third_party/xcb/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/google/gfxstream/third_party/xcb/Android.bp")).unwrap();
        let p=root.join("hardware/ril/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/ril/Android.bp")).unwrap();
        let p=root.join("hardware/ril/libril/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/ril/libril/Android.bp")).unwrap();
        let p=root.join("hardware/ril/librilutils/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/ril/librilutils/Android.bp")).unwrap();
        let p=root.join("hardware/ril/reference-ril/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/hardware/ril/reference-ril/Android.bp")).unwrap();
        let p=root.join("kernel/prebuilts/6.12/x86_64/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/kernel/prebuilts/6.12/x86_64/Android.bp")).unwrap();
        let p=root.join("kernel/prebuilts/6.6/x86_64/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/kernel/prebuilts/6.6/x86_64/Android.bp")).unwrap();
        let p=root.join("packages/apps/CellBroadcastReceiver/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/CellBroadcastReceiver/Android.bp")).unwrap();
        let p=root.join("packages/apps/CellBroadcastReceiver/apex/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/CellBroadcastReceiver/apex/Android.bp")).unwrap();
        let p=root.join("packages/apps/CellBroadcastReceiver/apex/permissions/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/CellBroadcastReceiver/apex/permissions/Android.bp")).unwrap();
        let p=root.join("packages/apps/CellBroadcastReceiver/apex/testing/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/CellBroadcastReceiver/apex/testing/Android.bp")).unwrap();
        let p=root.join("packages/apps/CellBroadcastReceiver/flags/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/CellBroadcastReceiver/flags/Android.bp")).unwrap();
        let p=root.join("packages/apps/CellBroadcastReceiver/legacy/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/CellBroadcastReceiver/legacy/Android.bp")).unwrap();
        let p=root.join("packages/apps/CellBroadcastReceiver/tests/testapp/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/CellBroadcastReceiver/tests/testapp/Android.bp")).unwrap();
        let p=root.join("packages/apps/CellBroadcastReceiver/tests/unit/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/CellBroadcastReceiver/tests/unit/Android.bp")).unwrap();
        let p=root.join("packages/apps/CertInstaller/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/CertInstaller/Android.bp")).unwrap();
        let p=root.join("packages/apps/CertInstaller/robotests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/CertInstaller/robotests/Android.bp")).unwrap();
        let p=root.join("packages/apps/ContactsPicker/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/ContactsPicker/Android.bp")).unwrap();
        let p=root.join("packages/apps/ContactsPicker/tests/componenttests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/ContactsPicker/tests/componenttests/Android.bp")).unwrap();
        let p=root.join("packages/apps/ContactsPicker/tests/democlientapps/lib/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/ContactsPicker/tests/democlientapps/lib/Android.bp")).unwrap();
        let p=root.join("packages/apps/ContactsPicker/tests/democlientapps/sdk36/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/ContactsPicker/tests/democlientapps/sdk36/Android.bp")).unwrap();
        let p=root.join("packages/apps/ContactsPicker/tests/democlientapps/sdk37/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/ContactsPicker/tests/democlientapps/sdk37/Android.bp")).unwrap();
        let p=root.join("packages/apps/ContactsPicker/tests/integration/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/ContactsPicker/tests/integration/Android.bp")).unwrap();
        let p=root.join("packages/apps/DeviceDiagnostics/DeviceDiagnosticsLib/src/androidTest/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/DeviceDiagnostics/DeviceDiagnosticsLib/src/androidTest/Android.bp")).unwrap();
        let p=root.join("packages/apps/DeviceDiagnostics/DeviceDiagnosticsLib/src/main/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/DeviceDiagnostics/DeviceDiagnosticsLib/src/main/Android.bp")).unwrap();
        let p=root.join("packages/apps/DeviceDiagnostics/app/src/main/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/DeviceDiagnostics/app/src/main/Android.bp")).unwrap();
        let p=root.join("packages/apps/DeviceDiagnostics/tradeinmode/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/DeviceDiagnostics/tradeinmode/Android.bp")).unwrap();
        let p=root.join("packages/apps/DeviceDiagnostics/tradeinmode/tests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/DeviceDiagnostics/tradeinmode/tests/Android.bp")).unwrap();
        let p=root.join("packages/apps/HTMLViewer/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/HTMLViewer/Android.bp")).unwrap();
        let p=root.join("packages/apps/KeyChain/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/KeyChain/Android.bp")).unwrap();
        let p=root.join("packages/apps/KeyChain/robotests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/KeyChain/robotests/Android.bp")).unwrap();
        let p=root.join("packages/apps/KeyChain/support/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/KeyChain/support/Android.bp")).unwrap();
        let p=root.join("packages/apps/KeyChain/tests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/KeyChain/tests/Android.bp")).unwrap();
        let p=root.join("packages/apps/MusicFX/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/MusicFX/Android.bp")).unwrap();
        let p=root.join("packages/apps/PrivateSpace/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/PrivateSpace/Android.bp")).unwrap();
        let p=root.join("packages/apps/PrivateSpace/tests/integration/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/PrivateSpace/tests/integration/Android.bp")).unwrap();
        let p=root.join("packages/apps/PrivateSpace/tests/unit/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/PrivateSpace/tests/unit/Android.bp")).unwrap();
        let p=root.join("packages/apps/SecureElement/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/SecureElement/Android.bp")).unwrap();
        let p=root.join("packages/apps/SecureElement/tests/unit/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/SecureElement/tests/unit/Android.bp")).unwrap();
        let p=root.join("packages/apps/Stk/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/Stk/Android.bp")).unwrap();
        let p=root.join("packages/apps/Tag/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/apps/Tag/Android.bp")).unwrap();
        let p=root.join("packages/modules/AppSearch/AppSearchAiSealConfig/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/AppSearch/AppSearchAiSealConfig/Android.bp")).unwrap();
        let p=root.join("packages/modules/AppSearch/AppSearchAiSealConfig/assets/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/AppSearch/AppSearchAiSealConfig/assets/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/android/app/change-ids/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/android/app/change-ids/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/apex/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/apex/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/apex/key/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/apex/key/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/apex/permissions/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/apex/permissions/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/common/kotlin_utils/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/common/kotlin_utils/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/sysprop/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/sysprop/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/audio/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/audio/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/audio/codecs/lhdcv5/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/audio/codecs/lhdcv5/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/audio_hal_interface/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/audio_hal_interface/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/audio_hal_interface/fuzzer/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/audio_hal_interface/fuzzer/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/bta/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/bta/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/bta/aics/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/bta/aics/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/btcore/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/btcore/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/btif/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/btif/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/common/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/common/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/conf/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/conf/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/device/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/device/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/device/fuzzer/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/device/fuzzer/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/embdrv/encoder_for_aptx/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/embdrv/encoder_for_aptx/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/embdrv/encoder_for_aptxhd/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/embdrv/encoder_for_aptxhd/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/embdrv/g722/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/embdrv/g722/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/embdrv/g722/fuzzer/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/embdrv/g722/fuzzer/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/embdrv/sbc/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/embdrv/sbc/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/embdrv/sbc/decoder/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/embdrv/sbc/decoder/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/embdrv/sbc/encoder/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/embdrv/sbc/encoder/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/gd/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/gd/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/gd/crypto_toolbox/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/gd/crypto_toolbox/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/gd/packet/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/gd/packet/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/gd/packet/parser/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/gd/packet/parser/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/gd/packet/parser/test/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/gd/packet/parser/test/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/gd/proto/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/gd/proto/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/hci/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/hci/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/include/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/include/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/internal_include/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/internal_include/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/log/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/log/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/main/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/main/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/metrics/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/metrics/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/osi/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/osi/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/osi/test/fuzzers/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/osi/test/fuzzers/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/osi/test/fuzzers/alarm/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/osi/test/fuzzers/alarm/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/osi/test/fuzzers/allocator/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/osi/test/fuzzers/allocator/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/osi/test/fuzzers/compat/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/osi/test/fuzzers/compat/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/osi/test/fuzzers/fixed_queue/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/osi/test/fuzzers/fixed_queue/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/osi/test/fuzzers/future/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/osi/test/fuzzers/future/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/osi/test/fuzzers/list/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/osi/test/fuzzers/list/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/packet/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/packet/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/packet/avrcp/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/packet/avrcp/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/packet/base/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/packet/base/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/packet/tests/fuzzers/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/packet/tests/fuzzers/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/pdl/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/pdl/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/pdl/ascs/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/pdl/ascs/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/pdl/hci/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/pdl/hci/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/pdl/l2cap/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/pdl/l2cap/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/pdl/pacs/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/pdl/pacs/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/pdl/ras/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/pdl/ras/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/pdl/security/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/pdl/security/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/profile/avrcp/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/profile/avrcp/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/rust/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/rust/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/rust/macros/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/rust/macros/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/rust/private_gatt/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/rust/private_gatt/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/rust/src/le_audio/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/rust/src/le_audio/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/stack/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/stack/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/stack/fuzzers/test/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/stack/fuzzers/test/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/stack/test/fuzzers/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/stack/test/fuzzers/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/types/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/types/Android.bp")).unwrap();
        let p=root.join("packages/modules/Bluetooth/system/udrv/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Bluetooth/system/udrv/Android.bp")).unwrap();
        let p=root.join("packages/modules/CaptivePortalLogin/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/CaptivePortalLogin/Android.bp")).unwrap();
        let p=root.join("packages/modules/CaptivePortalLogin/tests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/CaptivePortalLogin/tests/Android.bp")).unwrap();
        let p=root.join("packages/modules/ConfigInfrastructure/aflags/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/ConfigInfrastructure/aflags/Android.bp")).unwrap();
        let p=root.join("packages/modules/ConfigInfrastructure/aflags/proto/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/ConfigInfrastructure/aflags/proto/Android.bp")).unwrap();
        let p=root.join("packages/modules/ConfigInfrastructure/apex/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/ConfigInfrastructure/apex/Android.bp")).unwrap();
        let p=root.join("packages/modules/Connectivity/clatd/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Connectivity/clatd/Android.bp")).unwrap();
        let p=root.join("packages/modules/Connectivity/staticlibs/native/nettestutils/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Connectivity/staticlibs/native/nettestutils/Android.bp")).unwrap();
        let p=root.join("packages/modules/Connectivity/thread/apex/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Connectivity/thread/apex/Android.bp")).unwrap();
        let p=root.join("packages/modules/DnsResolver/apex/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/DnsResolver/apex/Android.bp")).unwrap();
        let p=root.join("packages/modules/DnsResolver/tests/dns_responder/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/DnsResolver/tests/dns_responder/Android.bp")).unwrap();
        let p=root.join("packages/modules/ExtServices/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/ExtServices/Android.bp")).unwrap();
        let p=root.join("packages/modules/ExtServices/apex/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/ExtServices/apex/Android.bp")).unwrap();
        let p=root.join("packages/modules/ExtServices/apex/permissions/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/ExtServices/apex/permissions/Android.bp")).unwrap();
        let p=root.join("packages/modules/ExtServices/apex/testing/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/ExtServices/apex/testing/Android.bp")).unwrap();
        let p=root.join("packages/modules/ExtServices/flags/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/ExtServices/flags/Android.bp")).unwrap();
        let p=root.join("packages/modules/ExtServices/java/tests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/ExtServices/java/tests/Android.bp")).unwrap();
        let p=root.join("packages/modules/ExtServices/jni/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/ExtServices/jni/Android.bp")).unwrap();
        let p=root.join("packages/modules/ExtServices/native/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/ExtServices/native/Android.bp")).unwrap();
        let p=root.join("packages/modules/IntentResolver/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/IntentResolver/Android.bp")).unwrap();
        let p=root.join("packages/modules/IntentResolver/aconfig/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/IntentResolver/aconfig/Android.bp")).unwrap();
        let p=root.join("packages/modules/IntentResolver/tests/activity/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/IntentResolver/tests/activity/Android.bp")).unwrap();
        let p=root.join("packages/modules/IntentResolver/tests/integration/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/IntentResolver/tests/integration/Android.bp")).unwrap();
        let p=root.join("packages/modules/IntentResolver/tests/shared/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/IntentResolver/tests/shared/Android.bp")).unwrap();
        let p=root.join("packages/modules/IntentResolver/tests/unit/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/IntentResolver/tests/unit/Android.bp")).unwrap();
        let p=root.join("packages/modules/NetworkStack/common/captiveportal/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/NetworkStack/common/captiveportal/Android.bp")).unwrap();
        let p=root.join("packages/modules/NeuralNetworks/apex/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/NeuralNetworks/apex/Android.bp")).unwrap();
        let p=root.join("packages/modules/NeuralNetworks/apex/testing/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/NeuralNetworks/apex/testing/Android.bp")).unwrap();
        let p=root.join("packages/modules/Permission/SafetyCenter/Resources/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Permission/SafetyCenter/Resources/Android.bp")).unwrap();
        let p=root.join("packages/modules/RuntimeI18n/apex/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/RuntimeI18n/apex/Android.bp")).unwrap();
        let p=root.join("packages/modules/StatsD/tests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/StatsD/tests/Android.bp")).unwrap();
        let p=root.join("packages/modules/StatsD/tests/apps/atomstormapp/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/StatsD/tests/apps/atomstormapp/Android.bp")).unwrap();
        let p=root.join("packages/modules/StatsD/tests/apps/statsdapp/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/StatsD/tests/apps/statsdapp/Android.bp")).unwrap();
        let p=root.join("packages/modules/StatsD/tests/utils/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/StatsD/tests/utils/Android.bp")).unwrap();
        let p=root.join("packages/modules/StatsD/tests/utils/tests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/StatsD/tests/utils/tests/Android.bp")).unwrap();
        let p=root.join("packages/modules/Uwb/apex/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Uwb/apex/Android.bp")).unwrap();
        let p=root.join("packages/modules/Uwb/libuwb-uci/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Uwb/libuwb-uci/Android.bp")).unwrap();
        let p=root.join("packages/modules/Uwb/libuwb-uci/src/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Uwb/libuwb-uci/src/Android.bp")).unwrap();
        let p=root.join("packages/modules/Uwb/ranging/rtt_backend/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Uwb/ranging/rtt_backend/Android.bp")).unwrap();
        let p=root.join("packages/modules/Uwb/ranging/rtt_backend/tests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Uwb/ranging/rtt_backend/tests/Android.bp")).unwrap();
        let p=root.join("packages/modules/Uwb/ranging/service/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Uwb/ranging/service/Android.bp")).unwrap();
        let p=root.join("packages/modules/Uwb/ranging/service/tests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Uwb/ranging/service/tests/Android.bp")).unwrap();
        let p=root.join("packages/modules/Uwb/ranging/uwb_backend/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Uwb/ranging/uwb_backend/Android.bp")).unwrap();
        let p=root.join("packages/modules/Uwb/ranging/uwb_backend/tests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Uwb/ranging/uwb_backend/tests/Android.bp")).unwrap();
        let p=root.join("packages/modules/Uwb/service/uci/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Uwb/service/uci/Android.bp")).unwrap();
        let p=root.join("packages/modules/Uwb/service/uci/jni/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Uwb/service/uci/jni/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/guest/pvmfw/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/guest/pvmfw/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/guest/pvmfw/avb/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/guest/pvmfw/avb/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/guest/pvmfw/avb/fuzz/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/guest/pvmfw/avb/fuzz/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/guest/trusty/test_vm/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/guest/trusty/test_vm/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/guest/trusty/test_vm/vm/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/guest/trusty/test_vm/vm/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/ComposBenchmarkApp/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/ComposBenchmarkApp/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/ComposHostTestCases/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/ComposHostTestCases/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/Terminal/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/Terminal/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/TrustyVmBenchmarks/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/TrustyVmBenchmarks/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/aidl/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/aidl/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/authfs/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/authfs/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/authfs/benchmarks/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/authfs/benchmarks/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/authfs/common/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/authfs/common/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/authfs/hosttests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/authfs/hosttests/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/backcompat_test/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/backcompat_test/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/benchmark/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/benchmark/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/benchmark/src/jni/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/benchmark/src/jni/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/benchmark_hostside/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/benchmark_hostside/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/com.android.microdroid.test.tenant0/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/com.android.microdroid.test.tenant0/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/dtcompare/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/dtcompare/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/early_vm_test/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/early_vm_test/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/encrypted_assets/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/encrypted_assets/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/hostside/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/hostside/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/hypervisor_neverallow_test/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/hypervisor_neverallow_test/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/libs/common/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/libs/common/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/libs/device/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/libs/device/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/libs/host/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/libs/host/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/libs/libdts/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/libs/libdts/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/libs/preparer/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/libs/preparer/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/no_avf/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/no_avf/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/old_images_avf_test/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/old_images_avf_test/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/pvmfw/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/pvmfw/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/pvmfw/assets/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/pvmfw/assets/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/pvmfw/libs/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/pvmfw/libs/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/pvmfw/tools/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/pvmfw/tools/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/testapk/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/testapk/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/testapk_no_perm/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/testapk_no_perm/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/vendor_images/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/vendor_images/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/vm_accessor/accessor/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/vm_accessor/accessor/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/vm_accessor/accessor_vm/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/vm_accessor/accessor_vm/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/vm_accessor/aidl/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/vm_accessor/aidl/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/vm_accessor/apex/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/vm_accessor/apex/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/vm_accessor/test/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/vm_accessor/test/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/vm_attestation/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/vm_attestation/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/vm_attestation/aidl/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/vm_attestation/aidl/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/vm_multitenancy/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/vm_multitenancy/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/vmbase_example/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/vmbase_example/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/vmbase_test_vm/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/vmbase_test_vm/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/vmbase_test_vm/messages/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/vmbase_test_vm/messages/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/vmshareapp/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/vmshareapp/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/vmshareapp/aidl/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/vmshareapp/aidl/Android.bp")).unwrap();
        let p=root.join("packages/modules/Virtualization/tests/vts/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Virtualization/tests/vts/Android.bp")).unwrap();
        let p=root.join("packages/modules/Wifi/OsuLogin/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Wifi/OsuLogin/Android.bp")).unwrap();
        let p=root.join("packages/modules/Wifi/WifiDialog/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Wifi/WifiDialog/Android.bp")).unwrap();
        let p=root.join("packages/modules/Wifi/aidl/mainline_supplicant/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Wifi/aidl/mainline_supplicant/Android.bp")).unwrap();
        let p=root.join("packages/modules/Wifi/apex/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Wifi/apex/Android.bp")).unwrap();
        let p=root.join("packages/modules/Wifi/jni/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Wifi/jni/Android.bp")).unwrap();
        let p=root.join("packages/modules/Wifi/service/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Wifi/service/Android.bp")).unwrap();
        let p=root.join("packages/modules/Wifi/service/ServiceWifiResources/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Wifi/service/ServiceWifiResources/Android.bp")).unwrap();
        let p=root.join("packages/modules/Wifi/service/coex-table-parser/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Wifi/service/coex-table-parser/Android.bp")).unwrap();
        let p=root.join("packages/modules/Wifi/service/proto/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Wifi/service/proto/Android.bp")).unwrap();
        let p=root.join("packages/modules/Wifi/service/tests/mts/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Wifi/service/tests/mts/Android.bp")).unwrap();
        let p=root.join("packages/modules/Wifi/service/tests/wifitests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Wifi/service/tests/wifitests/Android.bp")).unwrap();
        let p=root.join("packages/modules/Wifi/service/tests/wifitests/apex/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/Wifi/service/tests/wifitests/apex/Android.bp")).unwrap();
        let p=root.join("packages/modules/adb/apex/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/adb/apex/Android.bp")).unwrap();
        let p=root.join("packages/modules/common/build/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/common/build/Android.bp")).unwrap();
        let p=root.join("packages/modules/common/build/mainline_modules_sdks_test_data/google_wifi_for_r_Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/common/build/mainline_modules_sdks_test_data/google_wifi_for_r_Android.bp")).unwrap();
        let p=root.join("packages/modules/common/build/mainline_modules_sdks_test_data/ipsec_for_r_Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/common/build/mainline_modules_sdks_test_data/ipsec_for_r_Android.bp")).unwrap();
        let p=root.join("packages/modules/common/build/mainline_modules_sdks_test_data/tethering_for_r_Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/modules/common/build/mainline_modules_sdks_test_data/tethering_for_r_Android.bp")).unwrap();
        let p=root.join("packages/providers/BookmarkProvider/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/providers/BookmarkProvider/Android.bp")).unwrap();
        let p=root.join("packages/providers/CallLogProvider/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/providers/CallLogProvider/Android.bp")).unwrap();
        let p=root.join("packages/providers/CallLogProvider/tests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/providers/CallLogProvider/tests/Android.bp")).unwrap();
        let p=root.join("packages/providers/ContactsKeysProvider/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/providers/ContactsKeysProvider/Android.bp")).unwrap();
        let p=root.join("packages/providers/ContactsKeysProvider/tests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/providers/ContactsKeysProvider/tests/Android.bp")).unwrap();
        let p=root.join("packages/providers/ContactsProvider/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/providers/ContactsProvider/Android.bp")).unwrap();
        let p=root.join("packages/providers/ContactsProvider/test_common/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/providers/ContactsProvider/test_common/Android.bp")).unwrap();
        let p=root.join("packages/providers/ContactsProvider/tests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/providers/ContactsProvider/tests/Android.bp")).unwrap();
        let p=root.join("packages/providers/DownloadProvider/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/providers/DownloadProvider/Android.bp")).unwrap();
        let p=root.join("packages/providers/DownloadProvider/flags/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/providers/DownloadProvider/flags/Android.bp")).unwrap();
        let p=root.join("packages/providers/DownloadProvider/tests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/providers/DownloadProvider/tests/Android.bp")).unwrap();
        let p=root.join("packages/providers/DownloadProvider/ui/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/providers/DownloadProvider/ui/Android.bp")).unwrap();
        let p=root.join("packages/providers/PartnerBookmarksProvider/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/providers/PartnerBookmarksProvider/Android.bp")).unwrap();
        let p=root.join("packages/providers/PartnerBookmarksProvider/tests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/providers/PartnerBookmarksProvider/tests/Android.bp")).unwrap();
        let p=root.join("packages/providers/UserDictionaryProvider/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/providers/UserDictionaryProvider/Android.bp")).unwrap();
        let p=root.join("packages/screensavers/Basic/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/screensavers/Basic/Android.bp")).unwrap();
        let p=root.join("packages/services/AlternativeNetworkAccess/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/services/AlternativeNetworkAccess/Android.bp")).unwrap();
        let p=root.join("packages/services/AlternativeNetworkAccess/tests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/services/AlternativeNetworkAccess/tests/Android.bp")).unwrap();
        let p=root.join("packages/services/BuiltInPrintService/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/services/BuiltInPrintService/Android.bp")).unwrap();
        let p=root.join("packages/services/BuiltInPrintService/flags/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/services/BuiltInPrintService/flags/Android.bp")).unwrap();
        let p=root.join("packages/services/BuiltInPrintService/jni/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/services/BuiltInPrintService/jni/Android.bp")).unwrap();
        let p=root.join("packages/services/DeviceAsWebcam/impl/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/services/DeviceAsWebcam/impl/Android.bp")).unwrap();
        let p=root.join("packages/services/DeviceAsWebcam/interface/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/services/DeviceAsWebcam/interface/Android.bp")).unwrap();
        let p=root.join("packages/services/DeviceAsWebcam/interface/jni/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/services/DeviceAsWebcam/interface/jni/Android.bp")).unwrap();
        let p=root.join("packages/services/Mms/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/services/Mms/Android.bp")).unwrap();
        let p=root.join("packages/services/Mms/proto/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/services/Mms/proto/Android.bp")).unwrap();
        let p=root.join("packages/services/Mms/tests/robotests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/services/Mms/tests/robotests/Android.bp")).unwrap();
        let p=root.join("packages/services/Mms/tests/unittests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/services/Mms/tests/unittests/Android.bp")).unwrap();
        let p=root.join("packages/wallpapers/LivePicker/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/packages/wallpapers/LivePicker/Android.bp")).unwrap();
        let p=root.join("platform_testing/libraries/androidbuildinternal/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/platform_testing/libraries/androidbuildinternal/Android.bp")).unwrap();
        let p=root.join("prebuilts/android-emulator/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/prebuilts/android-emulator/Android.bp")).unwrap();
        let p=root.join("prebuilts/android-emulator/trusty-x86_64/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/prebuilts/android-emulator/trusty-x86_64/Android.bp")).unwrap();
        let p=root.join("prebuilts/misc/common/devtools-annotations/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/prebuilts/misc/common/devtools-annotations/Android.bp")).unwrap();
        let p=root.join("prebuilts/tools/common/google-api-services-compute/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/prebuilts/tools/common/google-api-services-compute/Android.bp")).unwrap();
        let p=root.join("prebuilts/tools/common/google-api-services-storage/1.24.1/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/prebuilts/tools/common/google-api-services-storage/1.24.1/Android.bp")).unwrap();
        let p=root.join("system/apex/patchlevel/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/apex/patchlevel/Android.bp")).unwrap();
        let p=root.join("system/ca-certificates/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/ca-certificates/Android.bp")).unwrap();
        let p=root.join("system/ca-certificates/wfa_certs/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/ca-certificates/wfa_certs/Android.bp")).unwrap();
        let p=root.join("system/dmesgd/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/dmesgd/Android.bp")).unwrap();
        let p=root.join("system/extras/cppreopts/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/cppreopts/Android.bp")).unwrap();
        let p=root.join("system/extras/kcmdlinectrl/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/kcmdlinectrl/Android.bp")).unwrap();
        let p=root.join("system/extras/kcmdlinemodprobe/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/kcmdlinemodprobe/Android.bp")).unwrap();
        let p=root.join("system/extras/mtectrl/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/mtectrl/Android.bp")).unwrap();
        let p=root.join("system/extras/pinner/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/pinner/Android.bp")).unwrap();
        let p=root.join("system/extras/pinner/tests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/pinner/tests/Android.bp")).unwrap();
        let p=root.join("system/extras/preopt2cachename/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/preopt2cachename/Android.bp")).unwrap();
        let p=root.join("system/extras/tests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/tests/Android.bp")).unwrap();
        let p=root.join("system/extras/tests/binder/benchmarks/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/tests/binder/benchmarks/Android.bp")).unwrap();
        let p=root.join("system/extras/tests/cpueater/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/tests/cpueater/Android.bp")).unwrap();
        let p=root.join("system/extras/tests/crypto/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/tests/crypto/Android.bp")).unwrap();
        let p=root.join("system/extras/tests/directiotest/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/tests/directiotest/Android.bp")).unwrap();
        let p=root.join("system/extras/tests/ext4/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/tests/ext4/Android.bp")).unwrap();
        let p=root.join("system/extras/tests/framebuffer/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/tests/framebuffer/Android.bp")).unwrap();
        let p=root.join("system/extras/tests/fstest/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/tests/fstest/Android.bp")).unwrap();
        let p=root.join("system/extras/tests/icachetest/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/tests/icachetest/Android.bp")).unwrap();
        let p=root.join("system/extras/tests/kernel.config/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/tests/kernel.config/Android.bp")).unwrap();
        let p=root.join("system/extras/tests/lib/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/tests/lib/Android.bp")).unwrap();
        let p=root.join("system/extras/tests/lib/testUtil/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/tests/lib/testUtil/Android.bp")).unwrap();
        let p=root.join("system/extras/tests/pagingtest/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/tests/pagingtest/Android.bp")).unwrap();
        let p=root.join("system/extras/tests/pftest/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/tests/pftest/Android.bp")).unwrap();
        let p=root.join("system/extras/tests/schedtest/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/tests/schedtest/Android.bp")).unwrap();
        let p=root.join("system/extras/tests/storage/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/tests/storage/Android.bp")).unwrap();
        let p=root.join("system/extras/tests/suspend_stress/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/tests/suspend_stress/Android.bp")).unwrap();
        let p=root.join("system/extras/tests/tcp_nuke_addr/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/tests/tcp_nuke_addr/Android.bp")).unwrap();
        let p=root.join("system/extras/tests/timetest/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/tests/timetest/Android.bp")).unwrap();
        let p=root.join("system/extras/tests/uevents/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/extras/tests/uevents/Android.bp")).unwrap();
        let p=root.join("system/hwservicemanager/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/hwservicemanager/Android.bp")).unwrap();
        let p=root.join("system/memory/guardian/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/memory/guardian/Android.bp")).unwrap();
        let p=root.join("system/netd/tests/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/netd/tests/Android.bp")).unwrap();
        let p=root.join("system/netd/tests/benchmarks/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/netd/tests/benchmarks/Android.bp")).unwrap();
        let p=root.join("system/security/keystore-engine/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/security/keystore-engine/Android.bp")).unwrap();
        let p=root.join("system/server_configurable_flags/disaster_recovery/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/server_configurable_flags/disaster_recovery/Android.bp")).unwrap();
        let p=root.join("system/zygote/zygote-core/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/zygote/zygote-core/Android.bp")).unwrap();
        let p=root.join("system/zygote/zygote/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/zygote/zygote/Android.bp")).unwrap();
        let p=root.join("system/zygote/zygote/libs/statslog/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/system/zygote/zygote/libs/statslog/Android.bp")).unwrap();
        let p=root.join("tools/security/remote_provisioning/hwtrust/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/tools/security/remote_provisioning/hwtrust/Android.bp")).unwrap();
        let p=root.join("tools/security/remote_provisioning/hwtrust/cxxbridge/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/tools/security/remote_provisioning/hwtrust/cxxbridge/Android.bp")).unwrap();
        let p=root.join("trusty/device/desktop/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/trusty/device/desktop/Android.bp")).unwrap();
        let p=root.join("trusty/host/common/scripts/metrics_atoms_protoc_plugin/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/trusty/host/common/scripts/metrics_atoms_protoc_plugin/Android.bp")).unwrap();
        let p=root.join("trusty/host/common/scripts/replace_ramdisk_modules/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/trusty/host/common/scripts/replace_ramdisk_modules/Android.bp")).unwrap();
        let p=root.join("trusty/user/desktop/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/trusty/user/desktop/Android.bp")).unwrap();
        let p=root.join("trusty/user/desktop/lib/desktop_trusty_build_params/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/trusty/user/desktop/lib/desktop_trusty_build_params/Android.bp")).unwrap();
        let p=root.join("trusty/vendor/google/aosp/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/trusty/vendor/google/aosp/Android.bp")).unwrap();
        let p=root.join("trusty/vendor/google/aosp/scripts/Android.bp");fs::create_dir_all(p.parent().unwrap()).unwrap();fs::write(p,include_bytes!("../tests/fixtures/audio-generic535-original/trusty/vendor/google/aosp/scripts/Android.bp")).unwrap();
    }
    #[test]
    fn audio_generic535_complete_original_blueprints_are_real_inputs_and_reject_drift_or_missing() {
        let d=tempfile::tempdir().unwrap();write_generic535_original_fixtures(d.path());
        validate_audio_generic535_original_inputs(d.path(),SoongDependencyMode::AudioApexTargetClosure).unwrap();
        let path=d.path().join(AUDIO_GENERIC535_ORIGINAL_BPS[0].0);let bytes=fs::read(&path).unwrap();fs::write(&path,b"changed").unwrap();
        assert!(validate_audio_generic535_original_inputs(d.path(),SoongDependencyMode::AudioApexTargetClosure).is_err());
        fs::write(&path,bytes).unwrap();fs::remove_file(&path).unwrap();assert!(validate_audio_generic535_original_inputs(d.path(),SoongDependencyMode::AudioApexTargetClosure).is_err());
        validate_audio_generic535_original_inputs(d.path(),SoongDependencyMode::Strict).unwrap();
    }
    #[test]
    fn audio_generic535_original_blueprints_reject_source_aliases() {
        use std::os::unix::fs::symlink;
        let d=tempfile::tempdir().unwrap();write_generic535_original_fixtures(d.path());
        let path=d.path().join(AUDIO_GENERIC535_ORIGINAL_BPS[0].0);let target=d.path().join("same-original");fs::rename(&path,&target).unwrap();symlink(&target,&path).unwrap();
        assert!(validate_audio_generic535_original_inputs(d.path(),SoongDependencyMode::AudioApexTargetClosure).is_err());
    }
    #[test]
    fn audio_generic535_exact_discovery_keeps_required_providers_and_rejects_foreign_markers() {
        let d=tempfile::tempdir().unwrap();write_generic535_original_fixtures(d.path());
        assert!(audio_keep_required_discovery(d.path(),"external/rust/android-crates-io/crates/grpcio-sys",SoongDependencyMode::AudioApexTargetClosure).unwrap());
        assert!(audio_keep_required_discovery(d.path(),"packages/modules/StatsD/tests",SoongDependencyMode::AudioApexTargetClosure).unwrap());
        assert!(audio_keep_required_discovery(d.path(),"packages/modules/Virtualization/tests",SoongDependencyMode::AudioApexTargetClosure).unwrap());
        assert!(audio_keep_required_discovery(d.path(),"packages/modules/Virtualization/guest/pvmfw",SoongDependencyMode::AudioApexTargetClosure).unwrap());
        assert!(audio_keep_required_discovery(d.path(),"packages/modules/Virtualization/guest/trusty/test_vm",SoongDependencyMode::AudioApexTargetClosure).unwrap());

        let marker=d.path().join("packages/modules/StatsD/tests/.find-ignore");fs::write(&marker,b"foreign").unwrap();
        assert!(audio_keep_required_discovery(d.path(),"packages/modules/StatsD/tests",SoongDependencyMode::AudioApexTargetClosure).is_err());
        assert_eq!(fs::read(marker).unwrap(),b"foreign");
    }
    use super::*;

    #[test]
    fn vendor_policy_typed_request_keeps_audio_lock_and_rejects_widening() {
        let request = FixedProductionRequest::VendorPolicyOnAudioSource;
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let lock = selected_source_lock(repo, request.source_mode()).unwrap();
        assert_eq!(lock, repo.join("android/manifest/audio-bridge-source-lock.json"));
        assert_eq!(hash(&lock).unwrap(), AUDIO_SOURCE_LOCK_SHA256);
        assert_eq!(request.projection_targets(), ["com.android.hardware.audio.droidloom"]);
        assert_eq!(request.requested_targets(), ["vendor_sepolicy.cil"]);
        assert!(request.validate("droidloom_arm64").is_err());
        for targets in [&["vendor_sepolicy.cil"][..],
                        &["com.android.hardware.audio.droidloom", "vendor_sepolicy.cil"][..]] {
            assert!(FixedProductionRequest::Existing(
                SoongDependencyMode::AudioApexTargetClosure, targets).validate("droidloom_x86_64").is_err());
        }
        let d = tempfile::tempdir().unwrap();
        fs::create_dir_all(d.path().join("android/manifest")).unwrap();
        fs::write(d.path().join("android/manifest/audio-bridge-source-lock.json"), b"{}\n").unwrap();
        assert!(selected_source_lock(d.path(), request.source_mode()).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn vendor_policy_real_command_overrides_inherited_debug_environment() {
        const PROBE: &str = "DROIDLOOM_TEST_VENDOR_POLICY_ENV_CHILD";
        if std::env::var_os(PROBE).is_none() {
            for inherited in ["userdebug", "eng"] {
                let child = Command::new(std::env::current_exe().unwrap())
                    .args(["--exact", "android::tests::vendor_policy_real_command_overrides_inherited_debug_environment", "--test-threads=1"])
                    .env(PROBE, "1").env("TARGET_BUILD_VARIANT", inherited)
                    .env("TARGET_RELEASE", "cp3a").env("TARGET_PRODUCT", "wrong-product")
                    .env("ALLOW_MISSING_DEPENDENCIES", "true")
                    .env("SELINUX_IGNORE_NEVERALLOWS", "true").output().unwrap();
                assert!(child.status.success(), "{}", String::from_utf8_lossy(&child.stderr));
                assert!(String::from_utf8_lossy(&child.stdout).contains("1 passed; 0 failed"));
            }
            return;
        }
        assert!(matches!(std::env::var("TARGET_BUILD_VARIANT").as_deref(), Ok("userdebug" | "eng")));
        use std::os::unix::fs::PermissionsExt;
        let d = tempfile::tempdir().unwrap();
        let executable = d.path().join("soong_ui");
        // Real child environment/argv observer; it is not a Soong substitute.
        fs::write(&executable, b"#!/bin/sh\nset -eu\nprintf '%s\\n' \"$TARGET_BUILD_VARIANT\" \"$TARGET_RELEASE\" \"$TARGET_PRODUCT\" \"$ALLOW_MISSING_DEPENDENCIES\" \"$SELINUX_IGNORE_NEVERALLOWS\" \"$@\"\n").unwrap();
        fs::set_permissions(&executable, fs::Permissions::from_mode(0o700)).unwrap();
        let request = FixedProductionRequest::VendorPolicyOnAudioSource;
        let selected = request.soong_targets(d.path(), "droidloom_x86_64").unwrap();
        let mut command = production_soong_command(d.path(), d.path(), d.path(), "droidloom_x86_64", 6, &selected).unwrap();
        request.configure_dependencies(&mut command, "droidloom_x86_64").unwrap();
        let observed = command.output().unwrap();
        assert!(observed.status.success()); assert!(observed.stderr.is_empty());
        assert_eq!(observed.stdout, b"user\ncp2a\ndroidloom_x86_64\nfalse\nfalse\n--make-mode\n-j6\nvendor_sepolicy.cil\n");
    }

    #[test]
    fn vendor_policy_origin_guard_and_receipt_cannot_claim_apex_or_qpr1() {
        let d = tempfile::tempdir().unwrap();
        assert!(validate_vendor_policy_original(d.path()).is_err());
        fs::create_dir_all(d.path().join("system/sepolicy")).unwrap();
        fs::write(d.path().join("system/sepolicy/Android.bp"), b"se_versioned_policy { name: \"vendor_sepolicy.cil\" }\n").unwrap();
        assert!(validate_vendor_policy_original(d.path()).is_err());
        let value = FixedProductionRequest::VendorPolicyOnAudioSource.description("droidloom_x86_64").unwrap();
        assert_eq!(value["requested_targets"], serde_json::json!(["vendor_sepolicy.cil"]));
        assert_eq!(value["projection_scope_targets"], serde_json::json!(["com.android.hardware.audio.droidloom"]));
        assert_eq!(value["source_release"], "cp2a"); assert_eq!(value["build_variant"], "user");
        for key in ["QPR1_source_identity_claim", "Audio_APEX_qualified", "selected_cohort_policy_qualified", "runtime_qualified"] {
            assert_eq!(value[key], false);
        }
    }

    #[test]
    fn vendor_policy_scope_uses_normal_and_interrupted_projection_restore() {
        let request = FixedProductionRequest::VendorPolicyOnAudioSource;
        request.validate("droidloom_x86_64").unwrap();
        assert_eq!(request.source_mode(), SoongDependencyMode::AudioApexTargetClosure);
        let d = tempfile::tempdir().unwrap(); let source = d.path().join("aosp-source");
        fs::create_dir_all(&source).unwrap(); let file = source.join("original");
        fs::write(&file, b"original upstream bytes").unwrap(); let journal = d.path().join("source-projection.json");
        {
            let mut projection = Projection::new(journal.clone()).unwrap();
            projection.put(&file, b"existing profile projection").unwrap();
            projection.restore().unwrap();
        }
        assert_eq!(fs::read(&file).unwrap(), b"original upstream bytes"); assert!(!journal.exists());
        use std::os::unix::fs::PermissionsExt;
        let raw = serde_json::to_vec(&serde_json::json!({"schema_version": PROJECTION_JOURNAL_SCHEMA, "originals": [{
            "path": file, "bytes": b"original upstream bytes".to_vec(),
            "modified": fs::metadata(&file).unwrap().modified().unwrap(),
            "permissions_mode": fs::metadata(&file).unwrap().permissions().mode()
        }]})).unwrap();
        fs::write(&file, b"interrupted existing profile projection").unwrap();
        fs::write(&journal, raw).unwrap(); recover(&journal, &source).unwrap();
        assert_eq!(fs::read(&file).unwrap(), b"original upstream bytes"); assert!(!journal.exists());
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

    fn audio_before_lint_fonttools_lock() -> String {
        use sha2::{Digest, Sha256};
        let current = include_str!("../../droidloom-source/tests/fixtures/audio-source431-before-vendor-test-tools.json").to_owned();
        let marker = ",\n    {\n      \"path\": \"external/fonttools\",";
        assert_eq!(current.matches(marker).count(), 1);
        let (prefix, _) = current.split_once(marker).unwrap();
        let mut previous = format!("{prefix}\n  ]\n}}\n");
        let added = ",\n        \"fix\"";
        assert_eq!(previous.matches(added).count(), 1);
        previous = previous.replacen(added, "", 1);
        assert_eq!(format!("{:x}", Sha256::digest(previous.as_bytes())),
            "9a68f55567b88f89face6dce6121a60ee27fae028285c3cc0cda4cbae1d43364");
        previous
    }

    fn audio_before_sdk33_zygote_lock() -> String {
        use sha2::{Digest, Sha256};
        let mut previous = audio_before_lint_fonttools_lock();
        for path in ["33/module-lib", "zygote-proc-macros", "zygote-sys"] {
            let added = format!(",\n        \"{path}\"");
            assert_eq!(previous.matches(&added).count(), 1);
            previous = previous.replacen(&added, "", 1);
        }
        assert_eq!(format!("{:x}", Sha256::digest(previous.as_bytes())),
            "db5187942e23ef535cfc53ebe47e98ef3e258a9f79d225a621f8fd20cded9a91");
        previous
    }

    fn audio_before_released_sdk_lock() -> String {
        use sha2::{Digest, Sha256};
        let mut previous = audio_before_sdk33_zygote_lock();
        for path in [
            "4/public/android.jar",
            "4/public/framework.aidl",
            "7/public/android.jar",
            "7/public/framework.aidl",
            "15/public/android.jar",
            "15/public/framework.aidl",
            "16/public/android.jar",
            "16/public/framework.aidl",
            "19/public/android.jar",
            "19/public/framework.aidl",
            "21/public/android.jar",
            "21/public/framework.aidl",
            "22/public/android.jar",
            "22/public/framework.aidl",
            "23/public/android.jar",
            "23/public/framework.aidl",
            "24/public/android.jar",
            "24/public/framework.aidl",
            "25/public/android.jar",
            "25/public/framework.aidl",
            "26/public/android.jar",
            "26/public/framework.aidl",
            "27/public/android.jar",
            "27/public/framework.aidl",
            "33/public/android.jar",
            "33/public/framework.aidl",
            "33/public/core-for-system-modules.jar",
            "37.0/public/android.jar",
            "37.0/public/framework.aidl",
            "37.0/public/core-for-system-modules.jar",
            "31/system/android.jar",
            "35/system/android.jar",
            "36/public/android.jar",
            "36/public/framework.aidl",
            "36/public/core-for-system-modules.jar",
        ] {
            let added = format!(",\n        \"{path}\"");
            assert_eq!(previous.matches(&added).count(), 1);
            previous = previous.replacen(&added, "", 1);
        }
        assert_eq!(format!("{:x}", Sha256::digest(previous.as_bytes())),
            "45496b24c055fca9aa1f3fae7bd5c7c3c99cb46721150690645bf5d059159de2");
        previous
    }

    #[test]
    fn audio_watchdog_rejects_failed453_missing_repinned_and_narrow_sources() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        let current = droidloom_source::load_lock(&repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        validate_audio_provider_source_paths(&current, audio).unwrap();
        let old = tempfile::tempdir().unwrap();
        let path = old.path().join("android/manifest/audio-bridge-source-lock.json");
        write(&path, include_bytes!("../../droidloom-source/tests/fixtures/audio-source453-before-watchdog.json")).unwrap();
        assert!(selected_source_lock(old.path(), audio).is_err());
        assert!(validate_audio_provider_source_paths(&droidloom_source::load_lock(&path).unwrap(), audio).is_err());
        let project = Path::new("external/python/watchdog");
        let mut missing = current.clone();
        missing.projects.retain(|p| p.path != project);
        assert!(validate_audio_provider_source_paths(&missing, audio).is_err());
        let mut narrow = current.clone();
        narrow.projects.iter_mut().find(|p| p.path == project).unwrap().sparse_paths = vec![PathBuf::from("Android.bp")];
        assert!(validate_audio_provider_source_paths(&narrow, audio).is_err());
        let mut repinned = current.clone();
        repinned.projects.iter_mut().find(|p| p.path == project).unwrap().commit = "0000000000000000000000000000000000000000".into();
        assert!(validate_audio_provider_source_paths(&repinned, audio).is_err());
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            validate_audio_provider_source_paths(&missing, mode).unwrap();
            validate_audio_provider_source_paths(&narrow, mode).unwrap();
            validate_audio_provider_source_paths(&repinned, mode).unwrap();
        }
    }


    #[test]
    fn audio_trusty_rejects_failed455_and_missing_wrong_or_bp_only_header_closure() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        let current = droidloom_source::load_lock(&repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        let previous: droidloom_source::SparseSourceLock = serde_json::from_str(include_str!("../../droidloom-source/tests/fixtures/audio-source455-before-trusty-storage.json")).unwrap();
        validate_audio_trusty_source_paths(&current, audio).unwrap();
        assert!(validate_audio_trusty_source_paths(&previous, audio).is_err());
        for (path,_name,_commit,cone) in [
        ("external/trusty/lk", "trusty/lk/common", "88b0dd09802a19f07869d45dcd9a87a291803201", "include/shared"),
        ("external/trusty/lk", "trusty/lk/common", "88b0dd09802a19f07869d45dcd9a87a291803201", "include/uapi"),
        ("trusty/kernel", "trusty/lk/trusty", "837ece72a3c50f454dfaf3bb86d5ac2e843c142b", "include/shared"),
        ("trusty/kernel", "trusty/lk/trusty", "837ece72a3c50f454dfaf3bb86d5ac2e843c142b", "include/uapi"),
        ("trusty/user/base", "trusty/lib", "165d46c463bd22524a7d33d177bf7f35dad46bf5", "interface/storage"),
        ("trusty/user/base", "trusty/lib", "165d46c463bd22524a7d33d177bf7f35dad46bf5", "include/user"),
        ] {
            let mut missing = current.clone(); missing.projects.retain(|p| p.path != Path::new(path));
            assert!(validate_audio_trusty_source_paths(&missing, audio).is_err());
            let mut wrong = current.clone(); wrong.projects.iter_mut().find(|p| p.path == Path::new(path)).unwrap().commit = "0000000000000000000000000000000000000000".into();
            assert!(validate_audio_trusty_source_paths(&wrong, audio).is_err());
            let mut named = current.clone(); named.projects.iter_mut().find(|p| p.path == Path::new(path)).unwrap().name = "trusty/user/base".into();
            assert!(validate_audio_trusty_source_paths(&named, audio).is_err());
            let mut narrow = current.clone(); let p = narrow.projects.iter_mut().find(|p| p.path == Path::new(path)).unwrap();
            p.sparse_paths.retain(|c| c != Path::new(cone)); p.sparse_paths.push(PathBuf::from(format!("{cone}/Android.bp")));
            assert!(validate_audio_trusty_source_paths(&narrow, audio).is_err());
        }
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure, SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            validate_audio_trusty_source_paths(&previous, mode).unwrap();
        }
    }
    #[cfg(unix)]
    #[test]
    fn audio_trusty_rejects_missing_modified_or_linked_originals_and_retains_storageproxyd_edge() {
        let fixtures: &[(&str,&[u8])] = &[
            ("external/trusty/lk/Android.bp", include_bytes!("../tests/fixtures/audio-trusty-storage-providers/external/trusty/lk/Android.bp")),
            ("trusty/kernel/Android.bp", include_bytes!("../tests/fixtures/audio-trusty-storage-providers/trusty/kernel/Android.bp")),
            ("trusty/user/base/Android.bp", include_bytes!("../tests/fixtures/audio-trusty-storage-providers/trusty/user/base/Android.bp")),
            ("trusty/user/base/interface/storage/Android.bp", include_bytes!("../tests/fixtures/audio-trusty-storage-providers/trusty/user/base/interface/storage/Android.bp")),
            ("trusty/user/base/interface/storage/LICENSE", include_bytes!("../tests/fixtures/audio-trusty-storage-providers/trusty/user/base/interface/storage/LICENSE")),
            ("trusty/user/base/interface/storage/include/interface/storage/storage.h", include_bytes!("../tests/fixtures/audio-trusty-storage-providers/trusty/user/base/interface/storage/include/interface/storage/storage.h")),
            ("trusty/user/base/interface/storage/rules.mk", include_bytes!("../tests/fixtures/audio-trusty-storage-providers/trusty/user/base/interface/storage/rules.mk")),
            ("system/core/trusty/storage/proxy/Android.bp", include_bytes!("../tests/fixtures/audio-trusty-storage-providers/system/core/trusty/storage/proxy/Android.bp")),
        ];
        let d = tempfile::tempdir().unwrap(); let audio = SoongDependencyMode::AudioApexTargetClosure;
        for (path,bytes) in fixtures { write(&d.path().join(path), bytes).unwrap(); }
        validate_audio_trusty_original_inputs(d.path(), audio).unwrap();
        for (path,bytes) in fixtures {
            let p = d.path().join(path); fs::remove_file(&p).unwrap(); assert!(validate_audio_trusty_original_inputs(d.path(), audio).is_err());
            let mut changed = bytes.to_vec(); changed[0] ^= 1; write(&p, changed).unwrap(); assert!(validate_audio_trusty_original_inputs(d.path(), audio).is_err());
            fs::remove_file(&p).unwrap(); let other = d.path().join("original.input"); write(&other, bytes).unwrap(); std::os::unix::fs::symlink(&other,&p).unwrap();
            assert!(validate_audio_trusty_original_inputs(d.path(), audio).is_err()); fs::remove_file(&p).unwrap(); write(&p, bytes).unwrap();
        }
        validate_audio_trusty_original_inputs(d.path(), audio).unwrap();
        let bp = std::str::from_utf8(fixtures.iter().find(|r|r.0=="trusty/user/base/interface/storage/Android.bp").unwrap().1).unwrap();
        assert!(bp.contains("name: \"libtrustystorageinterface\"")); assert!(bp.contains("host_supported: true"));
        let parent = std::str::from_utf8(fixtures.iter().find(|r|r.0=="trusty/user/base/Android.bp").unwrap().1).unwrap();
        for name in ["external_trusty_lk_headers_shared", "trusty_kernel_headers_shared", "trusty_kernel_headers_uapi"] { assert!(parent.contains(name)); }
        let consumer = include_str!("../tests/fixtures/audio-trusty-storage-providers/system/core/trusty/storage/proxy/Android.bp");
        assert!(consumer.contains("name: \"storageproxyd_host\"")); assert!(consumer.contains("\"libtrustystorageinterface\""));
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure, SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            validate_audio_trusty_original_inputs(tempfile::tempdir().unwrap().path(), mode).unwrap();
        }
    }

    #[test]
    fn audio_host_tools_rejects_failed454_missing_repinned_and_bp_only_cones() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        let current = droidloom_source::load_lock(&repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        validate_audio_provider_source_paths(&current, audio).unwrap();
        let previous: droidloom_source::SparseSourceLock = serde_json::from_str(include_str!("../../droidloom-source/tests/fixtures/audio-source454-before-host-tools.json")).unwrap();
        assert!(validate_audio_provider_source_paths(&previous, audio).is_err());
        for (project, cone) in [
            ("development", "tools/etc1tool"),
            ("development", "tools/emulator/skins"),
            ("development", "tools/templates"),
            ("dalvik", "tools/hprof-conv"),
            ("system/extras", "partition_tools"),
            ("external/f2fs-tools", "fsck"),
            ("external/f2fs-tools", "include"),
            ("external/f2fs-tools", "lib"),
            ("external/f2fs-tools", "mkfs"),
            ("external/f2fs-tools", "tools"),
            ("external/e2fsprogs", "contrib/android"),
        ] {
            let mut missing = current.clone(); missing.projects.retain(|p| p.path != Path::new(project));
            assert!(validate_audio_provider_source_paths(&missing, audio).is_err());
            let mut wrong = current.clone(); wrong.projects.iter_mut().find(|p| p.path == Path::new(project)).unwrap().commit = "0000000000000000000000000000000000000000".into();
            assert!(validate_audio_provider_source_paths(&wrong, audio).is_err());
            let mut narrow = current.clone();
            let p = narrow.projects.iter_mut().find(|p| p.path == Path::new(project)).unwrap();
            p.sparse_paths.retain(|path| path != Path::new(cone));
            p.sparse_paths.push(PathBuf::from(format!("{cone}/Android.bp")));
            assert!(validate_audio_provider_source_paths(&narrow, audio).is_err());
            for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                         SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
                validate_audio_provider_source_paths(&previous, mode).unwrap();
                validate_audio_provider_source_paths(&missing, mode).unwrap();
                validate_audio_provider_source_paths(&wrong, mode).unwrap();
                validate_audio_provider_source_paths(&narrow, mode).unwrap();
            }
        }
    }

    #[cfg(unix)]
    #[test]
    fn audio_host_tools_rejects_missing_modified_and_symlinked_original_inputs() {
        let fixtures: &[(&str, &[u8])] = &[
            ("dalvik/tools/hprof-conv/Android.bp", include_bytes!("../tests/fixtures/audio-host-tools-providers/dalvik/tools/hprof-conv/Android.bp")),
            ("development/tools/Android.bp", include_bytes!("../tests/fixtures/audio-host-tools-providers/development/tools/Android.bp")),
            ("development/tools/etc1tool/Android.bp", include_bytes!("../tests/fixtures/audio-host-tools-providers/development/tools/etc1tool/Android.bp")),
            ("external/e2fsprogs/contrib/Android.bp", include_bytes!("../tests/fixtures/audio-host-tools-providers/external/e2fsprogs/contrib/Android.bp")),
            ("external/e2fsprogs/contrib/android/Android.bp", include_bytes!("../tests/fixtures/audio-host-tools-providers/external/e2fsprogs/contrib/android/Android.bp")),
            ("external/f2fs-tools/Android.bp", include_bytes!("../tests/fixtures/audio-host-tools-providers/external/f2fs-tools/Android.bp")),
            ("external/f2fs-tools/tools/f2fs_io/Android.bp", include_bytes!("../tests/fixtures/audio-host-tools-providers/external/f2fs-tools/tools/f2fs_io/Android.bp")),
            ("system/extras/partition_tools/Android.bp", include_bytes!("../tests/fixtures/audio-host-tools-providers/system/extras/partition_tools/Android.bp")),
            ("system/extras/partition_tools/aidl/Android.bp", include_bytes!("../tests/fixtures/audio-host-tools-providers/system/extras/partition_tools/aidl/Android.bp")),
        ];
        let d = tempfile::tempdir().unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        for (path, bytes) in fixtures { write(&d.path().join(path), bytes).unwrap(); }
        validate_audio_host_tools_original_inputs(d.path(), audio).unwrap();
        for (path, bytes) in fixtures {
            let p = d.path().join(path);
            fs::remove_file(&p).unwrap(); assert!(validate_audio_host_tools_original_inputs(d.path(), audio).is_err());
            let mut changed = bytes.to_vec(); changed[0] ^= 1; write(&p, changed).unwrap();
            assert!(validate_audio_host_tools_original_inputs(d.path(), audio).is_err());
            fs::remove_file(&p).unwrap(); let other = d.path().join("original.input"); write(&other, bytes).unwrap();
            std::os::unix::fs::symlink(&other, &p).unwrap();
            assert!(validate_audio_host_tools_original_inputs(d.path(), audio).is_err());
            fs::remove_file(&p).unwrap(); write(&p, bytes).unwrap();
        }
        validate_audio_host_tools_original_inputs(d.path(), audio).unwrap();
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            validate_audio_host_tools_original_inputs(tempfile::tempdir().unwrap().path(), mode).unwrap();
        }
    }

    #[cfg(unix)]
    #[test]
    fn audio_watchdog_rejects_missing_modified_and_symlinked_original_inputs() {
        let fixtures: &[(&str, &[u8])] = &[
            ("external/python/watchdog/Android.bp", include_bytes!("../tests/fixtures/audio-watchdog-providers/external/python/watchdog/Android.bp")),
            ("external/python/watchdog/src/watchdog/Android.bp", include_bytes!("../tests/fixtures/audio-watchdog-providers/external/python/watchdog/src/watchdog/Android.bp")),
        ];
        let d = tempfile::tempdir().unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        for (path, bytes) in fixtures { write(&d.path().join(path), bytes).unwrap(); }
        validate_audio_watchdog_original_inputs(d.path(), audio).unwrap();
        for (path, bytes) in fixtures {
            let p = d.path().join(path);
            fs::remove_file(&p).unwrap();
            assert!(validate_audio_watchdog_original_inputs(d.path(), audio).is_err());
            let mut changed = bytes.to_vec(); changed[0] ^= 1;
            write(&p, &changed).unwrap();
            assert!(validate_audio_watchdog_original_inputs(d.path(), audio).is_err());
            fs::remove_file(&p).unwrap();
            let other = d.path().join("original.input"); write(&other, bytes).unwrap();
            std::os::unix::fs::symlink(&other, &p).unwrap();
            assert!(validate_audio_watchdog_original_inputs(d.path(), audio).is_err());
            fs::remove_file(&p).unwrap(); write(&p, bytes).unwrap();
        }
        validate_audio_watchdog_original_inputs(d.path(), audio).unwrap();
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            validate_audio_watchdog_original_inputs(tempfile::tempdir().unwrap().path(), mode).unwrap();
        }
    }

    #[test]
    fn audio_adb_webrtc_rejects_failed446_missing_repinned_and_narrow_sources() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        let current = droidloom_source::load_lock(&repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        validate_audio_provider_source_paths(&current, audio).unwrap();
        let old = tempfile::tempdir().unwrap();
        let path = old.path().join("android/manifest/audio-bridge-source-lock.json");
        write(&path, include_bytes!("../../droidloom-source/tests/fixtures/audio-source446-before-adb-webrtc.json")).unwrap();
        assert!(selected_source_lock(old.path(), audio).is_err());
        assert!(validate_audio_provider_source_paths(&droidloom_source::load_lock(&path).unwrap(), audio).is_err());
        for (project, cone) in [
            ("external/openscreen", "discovery"),
            ("external/openscreen", "platform"),
            ("external/openscreen", "third_party/abseil"),
            ("external/openscreen", "util"),
            ("external/libusb", "android/config.h"),
            ("external/libusb", "darwin"),
            ("external/libusb", "include"),
            ("external/libusb", "libusb"),
            ("external/libusb", "linux"),
            ("external/libusb", "windows"),
            ("external/webrtc", "api"),
            ("external/webrtc", "audio"),
            ("external/webrtc", "call"),
            ("external/webrtc", "common_audio"),
            ("external/webrtc", "common_video"),
            ("external/webrtc", "logging"),
            ("external/webrtc", "media"),
            ("external/webrtc", "modules"),
            ("external/webrtc", "net"),
            ("external/webrtc", "p2p"),
            ("external/webrtc", "pc"),
            ("external/webrtc", "rtc_base"),
            ("external/webrtc", "stats"),
            ("external/webrtc", "system_wrappers"),
            ("external/webrtc", "test"),
            ("external/webrtc", "third_party"),
            ("external/webrtc", "video"),
            ("external/webrtc", "webrtc"),
            ("external/webrtc", "sdk"),
            ("external/pffft", "simd"),
            ("external/rnnoise", "include"),
            ("external/rnnoise", "src"),
            ("external/libsrtp2", "crypto"),
            ("external/libsrtp2", "exported_include"),
            ("external/libsrtp2", "fuzzer"),
            ("external/libsrtp2", "include"),
            ("external/libsrtp2", "srtp"),
            ("tools/security", "fuzzing/libFuzzer_mte_crash_handler"),
            ("external/libevent", "compat"),
            ("external/libevent", "include"),
            ("packages/modules/adb", "client"),
            ("packages/modules/adb", "fdevent"),
            ("packages/modules/adb", "sysdeps"),
            ("packages/modules/adb", "daemon"),
            ("packages/modules/adb", "fastdeploy"),
            ("packages/modules/adb", "test_utils"),
        ] {
            let mut missing = current.clone();
            missing.projects.retain(|p| p.path != Path::new(project));
            assert!(validate_audio_provider_source_paths(&missing, audio).is_err(), "{project}");
            let mut narrow = current.clone();
            let p = narrow.projects.iter_mut().find(|p| p.path == Path::new(project)).unwrap();
            p.sparse_paths.retain(|selected| !Path::new(cone).starts_with(selected));
            // An empty list denotes a full project, so retain an unrelated original root file.
            if p.sparse_paths.is_empty() { p.sparse_paths.push(PathBuf::from("Android.bp")); }
            assert!(validate_audio_provider_source_paths(&narrow, audio).is_err(), "{project}/{cone}");
            let mut repinned = current.clone();
            repinned.projects.iter_mut().find(|p| p.path == Path::new(project)).unwrap()
                .commit = "0000000000000000000000000000000000000000".into();
            assert!(validate_audio_provider_source_paths(&repinned, audio).is_err(), "{project}");
            for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                         SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
                validate_audio_provider_source_paths(&missing, mode).unwrap();
                validate_audio_provider_source_paths(&narrow, mode).unwrap();
                validate_audio_provider_source_paths(&repinned, mode).unwrap();
            }
        }
    }

    #[cfg(unix)]
    #[test]
    fn audio_adb_webrtc_rejects_missing_modified_and_symlinked_original_inputs() {
        let fixtures: &[(&str, &[u8])] = &[
            ("build/soong/cc/fuzz.go", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/build/soong/cc/fuzz.go")),
            ("external/libevent/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/external/libevent/Android.bp")),
            ("external/libsrtp2/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/external/libsrtp2/Android.bp")),
            ("external/libusb/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/external/libusb/Android.bp")),
            ("external/openscreen/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/external/openscreen/Android.bp")),
            ("external/openscreen/third_party/abseil/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/external/openscreen/third_party/abseil/Android.bp")),
            ("external/pffft/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/external/pffft/Android.bp")),
            ("external/rnnoise/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/external/rnnoise/Android.bp")),
            ("external/webrtc/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/external/webrtc/Android.bp")),
            ("external/webrtc/sdk/objc/base/RTCMacros.h", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/external/webrtc/sdk/objc/base/RTCMacros.h")),
            ("external/webrtc/sdk/objc/native/src/audio/audio_device_ios.h", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/external/webrtc/sdk/objc/native/src/audio/audio_device_ios.h")),
            ("external/webrtc/sdk/objc/native/src/audio/audio_session_observer.h", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/external/webrtc/sdk/objc/native/src/audio/audio_session_observer.h")),
            ("external/webrtc/sdk/objc/native/src/audio/voice_processing_audio_unit.h", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/external/webrtc/sdk/objc/native/src/audio/voice_processing_audio_unit.h")),
            ("external/webrtc/third_party/crc32c/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/external/webrtc/third_party/crc32c/Android.bp")),
            ("frameworks/av/media/libeffects/preprocessing/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/frameworks/av/media/libeffects/preprocessing/Android.bp")),
            ("packages/modules/adb/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/packages/modules/adb/Android.bp")),
            ("packages/modules/adb/client/adbmdns/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/packages/modules/adb/client/adbmdns/Android.bp")),
            ("packages/modules/adb/crypto/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/packages/modules/adb/crypto/Android.bp")),
            ("packages/modules/adb/crypto/tests/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/packages/modules/adb/crypto/tests/Android.bp")),
            ("packages/modules/adb/fastdeploy/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/packages/modules/adb/fastdeploy/Android.bp")),
            ("packages/modules/adb/libs/adbconnection/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/packages/modules/adb/libs/adbconnection/Android.bp")),
            ("packages/modules/adb/libs/libadbd_fs/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/packages/modules/adb/libs/libadbd_fs/Android.bp")),
            ("packages/modules/adb/pairing_auth/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/packages/modules/adb/pairing_auth/Android.bp")),
            ("packages/modules/adb/pairing_auth/tests/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/packages/modules/adb/pairing_auth/tests/Android.bp")),
            ("packages/modules/adb/pairing_connection/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/packages/modules/adb/pairing_connection/Android.bp")),
            ("packages/modules/adb/pairing_connection/tests/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/packages/modules/adb/pairing_connection/tests/Android.bp")),
            ("packages/modules/adb/proto/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/packages/modules/adb/proto/Android.bp")),
            ("packages/modules/adb/tls/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/packages/modules/adb/tls/Android.bp")),
            ("packages/modules/adb/tls/tests/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/packages/modules/adb/tls/tests/Android.bp")),
            ("prebuilts/clang/host/linux-x86/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/prebuilts/clang/host/linux-x86/Android.bp")),
            ("tools/security/fuzzing/libFuzzer_mte_crash_handler/Android.bp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/tools/security/fuzzing/libFuzzer_mte_crash_handler/Android.bp")),
            ("tools/security/fuzzing/libFuzzer_mte_crash_handler/crash_handler.cpp", include_bytes!("../tests/fixtures/audio-adb-webrtc-providers/tools/security/fuzzing/libFuzzer_mte_crash_handler/crash_handler.cpp")),
        ];
        let d = tempfile::tempdir().unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        for (path, bytes) in fixtures { write(&d.path().join(path), bytes).unwrap(); }
        validate_audio_adb_webrtc_original_inputs(d.path(), audio).unwrap();
        for (path, bytes) in fixtures {
            let p = d.path().join(path);
            fs::remove_file(&p).unwrap();
            assert!(validate_audio_adb_webrtc_original_inputs(d.path(), audio).is_err());
            let mut changed = bytes.to_vec(); changed[0] ^= 1;
            write(&p, &changed).unwrap();
            assert!(validate_audio_adb_webrtc_original_inputs(d.path(), audio).is_err());
            fs::remove_file(&p).unwrap();
            let other = d.path().join("original.input"); write(&other, bytes).unwrap();
            std::os::unix::fs::symlink(&other, &p).unwrap();
            assert!(validate_audio_adb_webrtc_original_inputs(d.path(), audio).is_err());
            fs::remove_file(&p).unwrap(); write(&p, bytes).unwrap();
        }
        validate_audio_adb_webrtc_original_inputs(d.path(), audio).unwrap();
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            validate_audio_adb_webrtc_original_inputs(tempfile::tempdir().unwrap().path(), mode).unwrap();
        }
    }

    #[test]
    fn audio_vintf_vts_rejects_failed445_and_incomplete_or_repinned_provider() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        let current = droidloom_source::load_lock(&repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        validate_audio_provider_source_paths(&current, audio).unwrap();
        let old = tempfile::tempdir().unwrap();
        let path = old.path().join("android/manifest/audio-bridge-source-lock.json");
        write(&path, include_bytes!("../../droidloom-source/tests/fixtures/audio-source445-before-vintf-vts.json")).unwrap();
        assert!(selected_source_lock(old.path(), audio).is_err());
        assert!(validate_audio_provider_source_paths(&droidloom_source::load_lock(&path).unwrap(), audio).is_err());
        let mut missing = current.clone();
        missing.projects.retain(|p| p.path != Path::new("test/vts-testcase/hal"));
        assert!(validate_audio_provider_source_paths(&missing, audio).is_err());
        let mut narrow = current.clone();
        narrow.projects.iter_mut().find(|p| p.path == Path::new("test/vts-testcase/hal")).unwrap()
            .sparse_paths = vec![PathBuf::from("treble/vintf/libvts_vintf_test_common")];
        assert!(validate_audio_provider_source_paths(&narrow, audio).is_err());
        let mut repinned = current.clone();
        repinned.projects.iter_mut().find(|p| p.path == Path::new("test/vts-testcase/hal")).unwrap()
            .commit = "0000000000000000000000000000000000000000".into();
        assert!(validate_audio_provider_source_paths(&repinned, audio).is_err());
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            validate_audio_provider_source_paths(&missing, mode).unwrap();
            validate_audio_provider_source_paths(&narrow, mode).unwrap();
            validate_audio_provider_source_paths(&repinned, mode).unwrap();
        }
    }

    #[cfg(unix)]
    #[test]
    fn audio_vintf_vts_rejects_missing_modified_and_symlinked_originals() {
        let fixtures: &[(&str, &[u8])] = &[
            ("system/libbase/Android.bp", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/system/libbase/Android.bp")),
            ("system/libvintf/Android.bp", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/system/libvintf/Android.bp")),
            ("test/vts-testcase/hal/treble/Android.bp", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/Android.bp")),
            ("test/vts-testcase/hal/treble/vintf/Android.bp", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/Android.bp")),
            ("test/vts-testcase/hal/treble/vintf/DeviceManifestTest.cpp", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/DeviceManifestTest.cpp")),
            ("test/vts-testcase/hal/treble/vintf/DeviceManifestTest.h", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/DeviceManifestTest.h")),
            ("test/vts-testcase/hal/treble/vintf/DeviceMatrixTest.cpp", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/DeviceMatrixTest.cpp")),
            ("test/vts-testcase/hal/treble/vintf/DeviceMatrixTest.h", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/DeviceMatrixTest.h")),
            ("test/vts-testcase/hal/treble/vintf/OWNERS", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/OWNERS")),
            ("test/vts-testcase/hal/treble/vintf/SingleManifestTest.cpp", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/SingleManifestTest.cpp")),
            ("test/vts-testcase/hal/treble/vintf/SingleManifestTest.h", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/SingleManifestTest.h")),
            ("test/vts-testcase/hal/treble/vintf/SystemVendorTest.cpp", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/SystemVendorTest.cpp")),
            ("test/vts-testcase/hal/treble/vintf/SystemVendorTest.h", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/SystemVendorTest.h")),
            ("test/vts-testcase/hal/treble/vintf/TEST_MAPPING", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/TEST_MAPPING")),
            ("test/vts-testcase/hal/treble/vintf/VtsNoHidl.cpp", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/VtsNoHidl.cpp")),
            ("test/vts-testcase/hal/treble/vintf/VtsTrebleVintfTestBase.cpp", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/VtsTrebleVintfTestBase.cpp")),
            ("test/vts-testcase/hal/treble/vintf/VtsTrebleVintfTestBase.h", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/VtsTrebleVintfTestBase.h")),
            ("test/vts-testcase/hal/treble/vintf/aidl/Android.bp", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/aidl/Android.bp")),
            ("test/vts-testcase/hal/treble/vintf/aidl/android/vintf/IServiceInfoFetcher.aidl", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/aidl/android/vintf/IServiceInfoFetcher.aidl")),
            ("test/vts-testcase/hal/treble/vintf/aidl/android/vintf/ServiceInfo.aidl", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/aidl/android/vintf/ServiceInfo.aidl")),
            ("test/vts-testcase/hal/treble/vintf/aidl/android/vintf/StabilityLevel.aidl", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/aidl/android/vintf/StabilityLevel.aidl")),
            ("test/vts-testcase/hal/treble/vintf/libvts_vintf_test_common/Android.bp", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/libvts_vintf_test_common/Android.bp")),
            ("test/vts-testcase/hal/treble/vintf/libvts_vintf_test_common/common.cpp", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/libvts_vintf_test_common/common.cpp")),
            ("test/vts-testcase/hal/treble/vintf/libvts_vintf_test_common/include/libvts_vintf_test_common/common.h", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/libvts_vintf_test_common/include/libvts_vintf_test_common/common.h")),
            ("test/vts-testcase/hal/treble/vintf/main.cpp", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/main.cpp")),
            ("test/vts-testcase/hal/treble/vintf/utils.cpp", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/utils.cpp")),
            ("test/vts-testcase/hal/treble/vintf/utils.h", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/utils.h")),
            ("test/vts-testcase/hal/treble/vintf/vts_treble_vintf_framework_test.xml", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/vts_treble_vintf_framework_test.xml")),
            ("test/vts-testcase/hal/treble/vintf/vts_treble_vintf_trusted_hal_test.xml", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/vts_treble_vintf_trusted_hal_test.xml")),
            ("test/vts-testcase/hal/treble/vintf/vts_treble_vintf_vendor_test.xml", include_bytes!("../tests/fixtures/audio-vintf-vts-providers/test/vts-testcase/hal/treble/vintf/vts_treble_vintf_vendor_test.xml")),
        ];
        let d = tempfile::tempdir().unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        for (path, bytes) in fixtures { write(&d.path().join(path), bytes).unwrap(); }
        validate_audio_vintf_vts_original_providers(d.path(), audio).unwrap();
        for (path, bytes) in fixtures {
            let p = d.path().join(path);
            fs::remove_file(&p).unwrap();
            assert!(validate_audio_vintf_vts_original_providers(d.path(), audio).is_err());
            let mut drifted = bytes.to_vec(); drifted[0] ^= 1;
            write(&p, &drifted).unwrap();
            assert!(validate_audio_vintf_vts_original_providers(d.path(), audio).is_err());
            fs::remove_file(&p).unwrap();
            let other = d.path().join("original.input"); write(&other, bytes).unwrap();
            std::os::unix::fs::symlink(&other, &p).unwrap();
            assert!(validate_audio_vintf_vts_original_providers(d.path(), audio).is_err());
            fs::remove_file(&p).unwrap(); write(&p, bytes).unwrap();
        }
        validate_audio_vintf_vts_original_providers(d.path(), audio).unwrap();
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            validate_audio_vintf_vts_original_providers(tempfile::tempdir().unwrap().path(), mode).unwrap();
        }
    }

    #[test]
    fn audio_chre_rejects_failed444_and_incomplete_or_repinned_providers() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        let current = droidloom_source::load_lock(&repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        validate_audio_provider_source_paths(&current, audio).unwrap();
        let old = tempfile::tempdir().unwrap();
        let path = old.path().join("android/manifest/audio-bridge-source-lock.json");
        write(&path, include_bytes!("../../droidloom-source/tests/fixtures/audio-source444-before-chre-pigweed.json")).unwrap();
        assert!(selected_source_lock(old.path(), audio).is_err());
        assert!(validate_audio_provider_source_paths(&droidloom_source::load_lock(&path).unwrap(), audio).is_err());
        for (project, cone) in [
            ("external/pigweed", "pw_async2"),
            ("external/pigweed", "pw_bluetooth"),
            ("external/pigweed", "pw_bluetooth_proxy"),
            ("external/pigweed", "pw_checksum"),
            ("external/pigweed", "pw_intrusive_ptr"),
            ("external/pigweed", "pw_multibuf"),
            ("external/pigweed", "third_party/emboss"),
            ("external/emboss", "compiler"),
            ("external/emboss", "runtime"),
        ] {
            let mut missing = current.clone();
            missing.projects.iter_mut().find(|p| p.path == Path::new(project)).unwrap()
                .sparse_paths.retain(|p| p != Path::new(cone));
            assert!(validate_audio_provider_source_paths(&missing, audio).is_err(), "{project}/{cone}");
        }
        for project in ["external/pigweed", "external/emboss"] {
            let mut repinned = current.clone();
            repinned.projects.iter_mut().find(|p| p.path == Path::new(project)).unwrap()
                .commit = "0000000000000000000000000000000000000000".into();
            assert!(validate_audio_provider_source_paths(&repinned, audio).is_err());
        }
        let mut missing_project = current.clone();
        missing_project.projects.retain(|p| p.path != Path::new("external/emboss"));
        assert!(validate_audio_provider_source_paths(&missing_project, audio).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn audio_chre_rejects_missing_modified_and_symlinked_originals() {
        let fixtures: &[(&str, &[u8])] = &[
            ("external/emboss/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/emboss/Android.bp")),
            ("external/emboss/compiler/back_end/cpp/generated_code_templates", include_bytes!("../tests/fixtures/audio-chre-providers/external/emboss/compiler/back_end/cpp/generated_code_templates")),
            ("external/emboss/compiler/front_end/error_examples", include_bytes!("../tests/fixtures/audio-chre-providers/external/emboss/compiler/front_end/error_examples")),
            ("external/emboss/compiler/front_end/prelude.emb", include_bytes!("../tests/fixtures/audio-chre-providers/external/emboss/compiler/front_end/prelude.emb")),
            ("external/emboss/compiler/front_end/reserved_words", include_bytes!("../tests/fixtures/audio-chre-providers/external/emboss/compiler/front_end/reserved_words")),
            ("external/emboss/embossc", include_bytes!("../tests/fixtures/audio-chre-providers/external/emboss/embossc")),
            ("external/emboss/runtime/cpp/emboss_prelude.h", include_bytes!("../tests/fixtures/audio-chre-providers/external/emboss/runtime/cpp/emboss_prelude.h")),
            ("external/pigweed/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/Android.bp")),
            ("external/pigweed/pw_allocator/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_allocator/Android.bp")),
            ("external/pigweed/pw_assert/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_assert/Android.bp")),
            ("external/pigweed/pw_assert_log/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_assert_log/Android.bp")),
            ("external/pigweed/pw_async2/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_async2/Android.bp")),
            ("external/pigweed/pw_base64/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_base64/Android.bp")),
            ("external/pigweed/pw_bluetooth/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_bluetooth/Android.bp")),
            ("external/pigweed/pw_bluetooth_proxy/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_bluetooth_proxy/Android.bp")),
            ("external/pigweed/pw_bluetooth_proxy/gatt/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_bluetooth_proxy/gatt/Android.bp")),
            ("external/pigweed/pw_bluetooth_proxy/hci/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_bluetooth_proxy/hci/Android.bp")),
            ("external/pigweed/pw_bluetooth_proxy/rfcomm/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_bluetooth_proxy/rfcomm/Android.bp")),
            ("external/pigweed/pw_build_android/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_build_android/Android.bp")),
            ("external/pigweed/pw_bytes/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_bytes/Android.bp")),
            ("external/pigweed/pw_checksum/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_checksum/Android.bp")),
            ("external/pigweed/pw_chrono/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_chrono/Android.bp")),
            ("external/pigweed/pw_chrono_stl/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_chrono_stl/Android.bp")),
            ("external/pigweed/pw_containers/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_containers/Android.bp")),
            ("external/pigweed/pw_elf/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_elf/Android.bp")),
            ("external/pigweed/pw_function/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_function/Android.bp")),
            ("external/pigweed/pw_intrusive_ptr/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_intrusive_ptr/Android.bp")),
            ("external/pigweed/pw_log/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_log/Android.bp")),
            ("external/pigweed/pw_log_android/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_log_android/Android.bp")),
            ("external/pigweed/pw_log_tokenized/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_log_tokenized/Android.bp")),
            ("external/pigweed/pw_memory/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_memory/Android.bp")),
            ("external/pigweed/pw_metric/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_metric/Android.bp")),
            ("external/pigweed/pw_multibuf/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_multibuf/Android.bp")),
            ("external/pigweed/pw_numeric/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_numeric/Android.bp")),
            ("external/pigweed/pw_polyfill/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_polyfill/Android.bp")),
            ("external/pigweed/pw_preprocessor/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_preprocessor/Android.bp")),
            ("external/pigweed/pw_protobuf/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_protobuf/Android.bp")),
            ("external/pigweed/pw_protobuf/py/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_protobuf/py/Android.bp")),
            ("external/pigweed/pw_protobuf_compiler/py/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_protobuf_compiler/py/Android.bp")),
            ("external/pigweed/pw_result/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_result/Android.bp")),
            ("external/pigweed/pw_rpc/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_rpc/Android.bp")),
            ("external/pigweed/pw_rpc/nanopb/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_rpc/nanopb/Android.bp")),
            ("external/pigweed/pw_rpc/pwpb/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_rpc/pwpb/Android.bp")),
            ("external/pigweed/pw_rpc/py/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_rpc/py/Android.bp")),
            ("external/pigweed/pw_rpc/raw/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_rpc/raw/Android.bp")),
            ("external/pigweed/pw_span/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_span/Android.bp")),
            ("external/pigweed/pw_status/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_status/Android.bp")),
            ("external/pigweed/pw_status/py/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_status/py/Android.bp")),
            ("external/pigweed/pw_stream/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_stream/Android.bp")),
            ("external/pigweed/pw_string/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_string/Android.bp")),
            ("external/pigweed/pw_sync/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_sync/Android.bp")),
            ("external/pigweed/pw_sync_baremetal/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_sync_baremetal/Android.bp")),
            ("external/pigweed/pw_sync_stl/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_sync_stl/Android.bp")),
            ("external/pigweed/pw_thread/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_thread/Android.bp")),
            ("external/pigweed/pw_thread_stl/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_thread_stl/Android.bp")),
            ("external/pigweed/pw_tokenizer/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_tokenizer/Android.bp")),
            ("external/pigweed/pw_toolchain/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_toolchain/Android.bp")),
            ("external/pigweed/pw_varint/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/pw_varint/Android.bp")),
            ("external/pigweed/third_party/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/third_party/Android.bp")),
            ("external/pigweed/third_party/emboss/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/third_party/emboss/Android.bp")),
            ("external/pigweed/third_party/emboss/embossc_runner.py", include_bytes!("../tests/fixtures/audio-chre-providers/external/pigweed/third_party/emboss/embossc_runner.py")),
            ("system/chre/Android.bp", include_bytes!("../tests/fixtures/audio-chre-providers/system/chre/Android.bp")),
        ];
        let d = tempfile::tempdir().unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        for (path, bytes) in fixtures { write(&d.path().join(path), bytes).unwrap(); }
        validate_audio_chre_original_providers(d.path(), audio).unwrap();
        for (path, bytes) in fixtures {
            let p = d.path().join(path);
            fs::remove_file(&p).unwrap();
            assert!(validate_audio_chre_original_providers(d.path(), audio).is_err());
            let mut drifted = bytes.to_vec(); drifted[0] ^= 1;
            write(&p, &drifted).unwrap();
            assert!(validate_audio_chre_original_providers(d.path(), audio).is_err());
            fs::remove_file(&p).unwrap();
            let other = d.path().join("original.input"); write(&other, bytes).unwrap();
            std::os::unix::fs::symlink(&other, &p).unwrap();
            assert!(validate_audio_chre_original_providers(d.path(), audio).is_err());
            fs::remove_file(&p).unwrap(); write(&p, bytes).unwrap();
        }
        validate_audio_chre_original_providers(d.path(), audio).unwrap();
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            validate_audio_chre_original_providers(tempfile::tempdir().unwrap().path(), mode).unwrap();
        }
    }

    #[test]
    fn audio_bcc_rejects_failed444_and_missing_original_cone() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        let current = droidloom_source::load_lock(&repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        validate_audio_provider_source_paths(&current, audio).unwrap();
        let old = tempfile::tempdir().unwrap();
        let path = old.path().join("android/manifest/audio-bridge-source-lock.json");
        write(&path, include_bytes!("../../droidloom-source/tests/fixtures/audio-source444-before-bcc-tools.json")).unwrap();
        assert!(selected_source_lock(old.path(), audio).is_err());
        assert!(validate_audio_provider_source_paths(&droidloom_source::load_lock(&path).unwrap(), audio).is_err());
        let mut missing = current.clone();
        missing.projects.iter_mut().find(|p| p.path == Path::new("frameworks/compile/libbcc")).unwrap()
            .sparse_paths.retain(|p| p != Path::new("tools/bcc_compat"));
        assert!(validate_audio_provider_source_paths(&missing, audio).is_err());
        let mut repinned = current.clone();
        repinned.projects.iter_mut().find(|p| p.path == Path::new("frameworks/compile/libbcc")).unwrap()
            .commit = "0000000000000000000000000000000000000000".into();
        assert!(validate_audio_provider_source_paths(&repinned, audio).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn audio_bcc_rejects_missing_modified_and_symlinked_originals() {
        let fixtures: &[(&str, &[u8])] = &[
            ("frameworks/compile/libbcc/Android.bp", include_bytes!("../tests/fixtures/audio-bcc-providers/frameworks/compile/libbcc/Android.bp")),
            ("frameworks/compile/libbcc/tools/Android.bp", include_bytes!("../tests/fixtures/audio-bcc-providers/frameworks/compile/libbcc/tools/Android.bp")),
            ("frameworks/compile/libbcc/tools/bcc_compat/Android.bp", include_bytes!("../tests/fixtures/audio-bcc-providers/frameworks/compile/libbcc/tools/bcc_compat/Android.bp")),
            ("frameworks/compile/libbcc/tools/bcc_compat/Main.cpp", include_bytes!("../tests/fixtures/audio-bcc-providers/frameworks/compile/libbcc/tools/bcc_compat/Main.cpp")),
            ("frameworks/compile/libbcc/lib/Android.bp", include_bytes!("../tests/fixtures/audio-bcc-providers/frameworks/compile/libbcc/lib/Android.bp")),
            ("frameworks/compile/libbcc/bcinfo/Android.bp", include_bytes!("../tests/fixtures/audio-bcc-providers/frameworks/compile/libbcc/bcinfo/Android.bp")),
            ("frameworks/compile/slang/Android.bp", include_bytes!("../tests/fixtures/audio-bcc-providers/frameworks/compile/slang/Android.bp")),
            ("external/llvm/Android.bp", include_bytes!("../tests/fixtures/audio-bcc-providers/external/llvm/Android.bp")),
            ("external/llvm/lib/Android.bp", include_bytes!("../tests/fixtures/audio-bcc-providers/external/llvm/lib/Android.bp")),
            ("development/build/Android.bp", include_bytes!("../tests/fixtures/audio-bcc-providers/development/build/Android.bp")),
        ];
        let d = tempfile::tempdir().unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        for (path, bytes) in fixtures { write(&d.path().join(path), bytes).unwrap(); }
        validate_audio_bcc_original_providers(d.path(), audio).unwrap();
        for (path, bytes) in fixtures {
            let p = d.path().join(path);
            fs::remove_file(&p).unwrap();
            assert!(validate_audio_bcc_original_providers(d.path(), audio).is_err());
            let mut drifted = bytes.to_vec(); drifted[0] ^= 1;
            write(&p, &drifted).unwrap();
            assert!(validate_audio_bcc_original_providers(d.path(), audio).is_err());
            fs::remove_file(&p).unwrap();
            let other = d.path().join("original.input"); write(&other, bytes).unwrap();
            std::os::unix::fs::symlink(&other, &p).unwrap();
            assert!(validate_audio_bcc_original_providers(d.path(), audio).is_err());
            fs::remove_file(&p).unwrap(); write(&p, bytes).unwrap();
        }
        validate_audio_bcc_original_providers(d.path(), audio).unwrap();
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            validate_audio_bcc_original_providers(tempfile::tempdir().unwrap().path(), mode).unwrap();
        }
    }

    #[test]
    fn audio_vendor_test_tools_reject_failed431_and_incomplete_cones() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        let lock = droidloom_source::load_lock(&repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        validate_audio_provider_source_paths(&lock, audio).unwrap();
        let old = tempfile::tempdir().unwrap();
        let path = old.path().join("android/manifest/audio-bridge-source-lock.json");
        write(&path, include_bytes!("../../droidloom-source/tests/fixtures/audio-source431-before-vendor-test-tools.json")).unwrap();
        assert!(selected_source_lock(old.path(), audio).is_err());
        assert!(validate_audio_provider_source_paths(&droidloom_source::load_lock(&path).unwrap(), audio).is_err());
        for (project, cone) in [
            ("dalvik", "tools/dexdeps"),
            ("tools/asuite", "atest"),
            ("external/python/absl-py", "absl"),
            ("external/scapy", "scapy"),
            ("external/python/google-api-python-client", "apiclient"),
            ("external/python/google-api-python-client", "googleapiclient"),
            ("external/python/oauth2client", "oauth2client"),
            ("external/python/httplib2", "python3"),
            ("tools/test/mobly_extensions", "coverage"),
            ("tools/test/mobly_extensions", "mobly_sponge_converter"),
            ("tools/test/mobly_extensions", "resultdb_uploader"),
            ("tools/test/mobly_extensions", "tools"),
            ("external/python/uritemplates", "uritemplate"),
            ("external/python/python-api-core", "google"),
            ("external/python/google-auth-library-python", "google"),
            ("external/python/cachetools", "src"),
            ("external/python/rsa", "rsa"),
            ("external/python/pyasn1", "pyasn1"),
            ("external/python/pyasn1-modules", "pyasn1_modules"),
        ] {
            let mut changed = lock.clone();
            let item = changed.projects.iter_mut().find(|p| p.path == Path::new(project)).unwrap();
            item.sparse_paths.retain(|p| p != Path::new(cone));
            if item.sparse_paths.is_empty() { item.sparse_paths.push("Android.bp".into()); }
            assert!(validate_audio_provider_source_paths(&changed, audio).is_err(), "{project}/{cone}");
            let mut drifted = lock.clone();
            drifted.projects.iter_mut().find(|p| p.path == Path::new(project)).unwrap()
                .commit = "0000000000000000000000000000000000000000".into();
            assert!(validate_audio_provider_source_paths(&drifted, audio).is_err());
        }
    }

    #[test]
    fn audio_vendor_test_tools_reject_missing_modified_and_symlinked_originals() {
        let fixtures: &[(&str, &[u8])] = &[
            ("dalvik/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/dalvik/Android.bp")),
            ("dalvik/tools/dexdeps/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/dalvik/tools/dexdeps/Android.bp")),
            ("external/python/absl-py/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/external/python/absl-py/Android.bp")),
            ("external/python/cachetools/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/external/python/cachetools/Android.bp")),
            ("external/python/cachetools/src/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/external/python/cachetools/src/Android.bp")),
            ("external/python/google-api-python-client/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/external/python/google-api-python-client/Android.bp")),
            ("external/python/google-auth-library-python/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/external/python/google-auth-library-python/Android.bp")),
            ("external/python/httplib2/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/external/python/httplib2/Android.bp")),
            ("external/python/oauth2client/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/external/python/oauth2client/Android.bp")),
            ("external/python/oauth2client/oauth2client/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/external/python/oauth2client/oauth2client/Android.bp")),
            ("external/python/pyasn1-modules/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/external/python/pyasn1-modules/Android.bp")),
            ("external/python/pyasn1-modules/pyasn1_modules/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/external/python/pyasn1-modules/pyasn1_modules/Android.bp")),
            ("external/python/pyasn1/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/external/python/pyasn1/Android.bp")),
            ("external/python/pyasn1/pyasn1/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/external/python/pyasn1/pyasn1/Android.bp")),
            ("external/python/python-api-core/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/external/python/python-api-core/Android.bp")),
            ("external/python/rsa/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/external/python/rsa/Android.bp")),
            ("external/python/rsa/rsa/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/external/python/rsa/rsa/Android.bp")),
            ("external/python/uritemplates/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/external/python/uritemplates/Android.bp")),
            ("external/python/uritemplates/uritemplate/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/external/python/uritemplates/uritemplate/Android.bp")),
            ("external/scapy/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/external/scapy/Android.bp")),
            ("tools/asuite/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/tools/asuite/Android.bp")),
            ("tools/asuite/atest/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/tools/asuite/atest/Android.bp")),
            ("tools/asuite/atest/asuite_lib_test/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/tools/asuite/atest/asuite_lib_test/Android.bp")),
            ("tools/asuite/atest/coverage/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/tools/asuite/atest/coverage/Android.bp")),
            ("tools/asuite/atest/integration_tests/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/tools/asuite/atest/integration_tests/Android.bp")),
            ("tools/asuite/atest/integration_tests/device_android_test/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/tools/asuite/atest/integration_tests/device_android_test/Android.bp")),
            ("tools/asuite/atest/integration_tests/device_cc_test/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/tools/asuite/atest/integration_tests/device_cc_test/Android.bp")),
            ("tools/asuite/atest/integration_tests/deviceless_cc_test/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/tools/asuite/atest/integration_tests/deviceless_cc_test/Android.bp")),
            ("tools/asuite/atest/integration_tests/deviceless_cc_test_host/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/tools/asuite/atest/integration_tests/deviceless_cc_test_host/Android.bp")),
            ("tools/asuite/atest/integration_tests/deviceless_java_test_host/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/tools/asuite/atest/integration_tests/deviceless_java_test_host/Android.bp")),
            ("tools/asuite/atest/integration_tests/deviceless_python_test_host/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/tools/asuite/atest/integration_tests/deviceless_python_test_host/Android.bp")),
            ("tools/asuite/atest/integration_tests/deviceless_python_test_host_multiclass/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/tools/asuite/atest/integration_tests/deviceless_python_test_host_multiclass/Android.bp")),
            ("tools/asuite/atest/java/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/tools/asuite/atest/java/Android.bp")),
            ("tools/asuite/atest/logstorage/httplib2/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/tools/asuite/atest/logstorage/httplib2/Android.bp")),
            ("tools/test/mobly_extensions/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/tools/test/mobly_extensions/Android.bp")),
            ("tools/test/mobly_extensions/mobly_sponge_converter/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/tools/test/mobly_extensions/mobly_sponge_converter/Android.bp")),
            ("tools/test/mobly_extensions/resultdb_uploader/Android.bp", include_bytes!("../tests/fixtures/audio-test-tool-providers/tools/test/mobly_extensions/resultdb_uploader/Android.bp")),
        ];
        let d = tempfile::tempdir().unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        for (path, bytes) in fixtures { write(&d.path().join(path), bytes).unwrap(); }
        validate_audio_test_tools_original_providers(d.path(), audio).unwrap();
        for (path, bytes) in fixtures {
            let p = d.path().join(path);
            fs::remove_file(&p).unwrap();
            assert!(validate_audio_test_tools_original_providers(d.path(), audio).is_err());
            let mut drifted = bytes.to_vec(); drifted[0] ^= 1;
            write(&p, &drifted).unwrap();
            assert!(validate_audio_test_tools_original_providers(d.path(), audio).is_err());
            fs::remove_file(&p).unwrap();
            let other = d.path().join("original.bp"); write(&other, bytes).unwrap();
            std::os::unix::fs::symlink(&other, &p).unwrap();
            assert!(validate_audio_test_tools_original_providers(d.path(), audio).is_err());
            fs::remove_file(&p).unwrap(); write(&p, bytes).unwrap();
        }
        validate_audio_test_tools_original_providers(d.path(), audio).unwrap();
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            validate_audio_test_tools_original_providers(tempfile::tempdir().unwrap().path(), mode).unwrap();
        }
    }

    #[test]
    fn audio_lint_fonttools_rejects_the_actual_r13_lock() {
        let old = audio_before_lint_fonttools_lock();
        let d = tempfile::tempdir().unwrap();
        let path = d.path().join("android/manifest/audio-bridge-source-lock.json");
        write(&path, old.as_bytes()).unwrap();
        let lock = droidloom_source::load_lock(&path).unwrap();
        assert_eq!(lock.projects.len(), 430);
        let mode = SoongDependencyMode::AudioApexTargetClosure;
        assert!(selected_source_lock(d.path(), mode).is_err());
        assert!(validate_audio_provider_source_paths(&lock, mode).is_err());
    }

    #[test]
    fn audio_lint_fonttools_requires_complete_cones_and_original_commits() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let lock = droidloom_source::load_lock(&repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        validate_audio_provider_source_paths(&lock, audio).unwrap();
        for (project, cone, partial) in [
            ("tools/lint_checks", "fix", "fix/Android.bp"),
            ("tools/lint_checks", "fix", "fix/soong_lint_fix.py"),
            ("external/fonttools", "Lib", "Lib/fontTools/Android.bp"),
            ("external/fonttools", "Lib", "Lib/fontTools/__init__.py"),
        ] {
            let mut missing = lock.clone();
            let p = missing.projects.iter_mut().find(|p| p.path == Path::new(project)).unwrap();
            p.sparse_paths.retain(|p| p != Path::new(cone));
            // Empty sparse paths mean the complete project, not no files.
            // Keep this negative fixture an explicit root-BP-only selection.
            if p.sparse_paths.is_empty() { p.sparse_paths.push("Android.bp".into()); }
            assert!(validate_audio_provider_source_paths(&missing, audio).is_err());
            missing.projects.iter_mut().find(|p| p.path == Path::new(project)).unwrap()
                .sparse_paths.push(partial.into());
            assert!(validate_audio_provider_source_paths(&missing, audio).is_err());
            let mut wrong = lock.clone();
            wrong.projects.iter_mut().find(|p| p.path == Path::new(project)).unwrap()
                .commit = "0000000000000000000000000000000000000000".into();
            assert!(validate_audio_provider_source_paths(&wrong, audio).is_err());
            let mut widened = fs::read_to_string(repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
            let marker = format!("\"path\": \"{project}\",");
            assert_eq!(widened.matches(&marker).count(), 1);
            let start = widened.find(&marker).unwrap();
            let end = start + widened[start..].find("\n      ]").unwrap();
            widened.insert_str(end, ",\n        \"unreviewed-extra-input\"");
            let d = tempfile::tempdir().unwrap();
            write(&d.path().join("android/manifest/audio-bridge-source-lock.json"),
                  widened.as_bytes()).unwrap();
            droidloom_source::load_lock(&d.path().join("android/manifest/audio-bridge-source-lock.json")).unwrap();
            selected_source_lock(repo, audio).unwrap();
            assert!(selected_source_lock(d.path(), audio).is_err());
            for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                         SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
                validate_audio_provider_source_paths(&missing, mode).unwrap();
            }
        }
    }

    #[test]
    fn audio_lint_fonttools_original_provider_guard_rejects_missing_drift_and_links() {
        let fixtures = [
            ("tools/lint_checks/fix/Android.bp", include_bytes!("../tests/fixtures/audio-providers/lint-fix-original.bp").as_slice()),
            ("external/fonttools/Android.bp", include_bytes!("../tests/fixtures/audio-providers/fonttools-license-original.bp").as_slice()),
            ("external/fonttools/Lib/fontTools/Android.bp", include_bytes!("../tests/fixtures/audio-providers/fonttools-library-original.bp").as_slice()),
        ];
        let d = tempfile::tempdir().unwrap();
        for (path, bytes) in fixtures { write(&d.path().join(path), bytes).unwrap(); }
        let mode = SoongDependencyMode::AudioApexTargetClosure;
        validate_audio_lint_fonttools_original_providers(d.path(), mode).unwrap();
        for (path, bytes) in fixtures {
            let p = d.path().join(path);
            fs::remove_file(&p).unwrap();
            assert!(validate_audio_lint_fonttools_original_providers(d.path(), mode).is_err());
            let mut drifted = bytes.to_vec(); drifted[0] ^= 1;
            write(&p, &drifted).unwrap();
            assert!(validate_audio_lint_fonttools_original_providers(d.path(), mode).is_err());
            fs::remove_file(&p).unwrap();
            let other = d.path().join("original.bp"); write(&other, bytes).unwrap();
            std::os::unix::fs::symlink(&other, &p).unwrap();
            assert!(validate_audio_lint_fonttools_original_providers(d.path(), mode).is_err());
            fs::remove_file(&p).unwrap(); write(&p, bytes).unwrap();
        }
        validate_audio_lint_fonttools_original_providers(d.path(), mode).unwrap();
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            validate_audio_lint_fonttools_original_providers(tempfile::tempdir().unwrap().path(), mode).unwrap();
        }
    }

    #[test]
    fn audio_sdk33_zygote_rejects_the_actual_r12_lock() {
        let old = audio_before_sdk33_zygote_lock();
        let d = tempfile::tempdir().unwrap();
        let path = d.path().join("android/manifest/audio-bridge-source-lock.json");
        write(&path, old.as_bytes()).unwrap();
        let lock = droidloom_source::load_lock(&path).unwrap();
        assert_eq!(lock.projects.len(), 430);
        let mode = SoongDependencyMode::AudioApexTargetClosure;
        assert!(selected_source_lock(d.path(), mode).is_err());
        assert!(validate_audio_provider_source_paths(&lock, mode).is_err());
    }

    #[test]
    fn audio_sdk33_zygote_requires_full_original_cones_and_commits() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let lock = droidloom_source::load_lock(&repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        validate_audio_provider_source_paths(&lock, audio).unwrap();
        for (project, cone, partial) in [
            ("prebuilts/sdk", "33/module-lib", "33/module-lib/android.jar"),
            ("system/zygote", "zygote-proc-macros", "zygote-proc-macros/Android.bp"),
            ("system/zygote", "zygote-sys", "zygote-sys/src/lib.rs"),
        ] {
            let mut missing = lock.clone();
            let p = missing.projects.iter_mut().find(|p| p.path == Path::new(project)).unwrap();
            p.sparse_paths.retain(|p| p != Path::new(cone));
            assert!(validate_audio_provider_source_paths(&missing, audio).is_err());
            let p = missing.projects.iter_mut().find(|p| p.path == Path::new(project)).unwrap();
            p.sparse_paths.push(partial.into());
            assert!(validate_audio_provider_source_paths(&missing, audio).is_err());
            let mut wrong = lock.clone();
            wrong.projects.iter_mut().find(|p| p.path == Path::new(project)).unwrap().commit = "0000000000000000000000000000000000000000".into();
            assert!(validate_audio_provider_source_paths(&wrong, audio).is_err());
            for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                         SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
                validate_audio_provider_source_paths(&missing, mode).unwrap();
            }
        }
    }

    #[test]
    fn audio_zygote_original_provider_guard_rejects_missing_drift_and_links() {
        let fixtures = [
            ("system/zygote/zygote-proc-macros/Android.bp", include_bytes!("../tests/fixtures/audio-providers/zygote-proc-macros-original.bp").as_slice()),
            ("system/zygote/zygote-sys/Android.bp", include_bytes!("../tests/fixtures/audio-providers/zygote-sys-original.bp").as_slice()),
        ];
        let d = tempfile::tempdir().unwrap();
        for (path, bytes) in fixtures { write(&d.path().join(path), bytes).unwrap(); }
        let mode = SoongDependencyMode::AudioApexTargetClosure;
        validate_audio_zygote_original_providers(d.path(), mode).unwrap();
        for (path, bytes) in fixtures {
            let p = d.path().join(path);
            fs::remove_file(&p).unwrap();
            assert!(validate_audio_zygote_original_providers(d.path(), mode).is_err());
            write(&p, b"rust_library { name: \"libzygote_sys\" }\n").unwrap();
            assert!(validate_audio_zygote_original_providers(d.path(), mode).is_err());
            fs::remove_file(&p).unwrap();
            let other = d.path().join("original.bp"); write(&other, bytes).unwrap();
            std::os::unix::fs::symlink(&other, &p).unwrap();
            assert!(validate_audio_zygote_original_providers(d.path(), mode).is_err());
            fs::remove_file(&p).unwrap(); write(&p, bytes).unwrap();
        }
        validate_audio_zygote_original_providers(d.path(), mode).unwrap();
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            validate_audio_zygote_original_providers(tempfile::tempdir().unwrap().path(), mode).unwrap();
        }
    }

    #[test]
    fn audio_released_sdk_rejects_the_actual_r11_source_lock() {
        let old = audio_before_released_sdk_lock();
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("android/manifest/audio-bridge-source-lock.json");
        write(&path, old.as_bytes()).unwrap();
        let old_lock = droidloom_source::load_lock(&path).unwrap();
        assert_eq!(old_lock.projects.len(), 430);
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        assert!(selected_source_lock(directory.path(), audio).is_err());
        let error = validate_audio_provider_source_paths(&old_lock, audio).unwrap_err().to_string();
        assert!(error.contains("released SDK input"));
    }

    #[test]
    fn audio_released_sdk_requires_jar_aidl_and_system_module_inputs() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let lock = droidloom_source::load_lock(
            &repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        validate_audio_provider_source_paths(&lock, audio).unwrap();
        for required in AUDIO_RELEASED_SDK_INPUTS {
            let mut missing = lock.clone();
            let sdk = missing.projects.iter_mut().find(|p| p.path == Path::new("prebuilts/sdk")).unwrap();
            sdk.sparse_paths.retain(|cone| !Path::new(required).starts_with(cone));
            assert!(!sdk.sparse_paths.is_empty());
            assert!(validate_audio_provider_source_paths(&missing, audio).is_err(), "{required}");
            for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                         SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
                validate_audio_provider_source_paths(&missing, mode).unwrap();
            }
        }
        let mut parent_cone = lock.clone();
        let sdk = parent_cone.projects.iter_mut().find(|p| p.path == Path::new("prebuilts/sdk")).unwrap();
        sdk.sparse_paths.retain(|p| !p.starts_with("23/public"));
        sdk.sparse_paths.push(PathBuf::from("23/public"));
        validate_audio_provider_source_paths(&parent_cone, audio).unwrap();
    }

    fn audio_before_ondeviceintelligence_lock() -> String {
        use sha2::{Digest, Sha256};
        let mut previous = audio_before_released_sdk_lock();
        for path in [
            "36/public/api/service-ondeviceintelligence.txt",
            "36/public/api/service-ondeviceintelligence-removed.txt",
            "36/system-server/api/service-ondeviceintelligence.txt",
            "36/system-server/api/service-ondeviceintelligence-removed.txt",
        ] {
            let added = format!(",\n        \"{path}\"");
            assert_eq!(previous.matches(&added).count(), 1);
            previous = previous.replacen(&added, "", 1);
        }
        assert_eq!(format!("{:x}", Sha256::digest(previous.as_bytes())),
            "78cc10ee7459926ec151e6224e6341d1b33397801330499e5d7f1a13fadb997a");
        previous
    }

    #[test]
    fn audio_ondeviceintelligence_rejects_the_actual_r10_430_lock() {
        let old = audio_before_ondeviceintelligence_lock();
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("android/manifest/audio-bridge-source-lock.json");
        write(&path, old.as_bytes()).unwrap();
        let old_lock = droidloom_source::load_lock(&path).unwrap();
        assert_eq!(old_lock.projects.len(), 430);
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        assert!(selected_source_lock(directory.path(), audio).is_err());
        assert!(validate_audio_provider_source_paths(&old_lock, audio).is_err());
    }

    #[test]
    fn audio_ondeviceintelligence_requires_both_original_scopes_at_same_commit() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let lock = droidloom_source::load_lock(
            &repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        validate_audio_provider_source_paths(&lock, audio).unwrap();
        for missing in [
            "36/public/api/service-ondeviceintelligence.txt",
            "36/public/api/service-ondeviceintelligence-removed.txt",
            "36/system-server/api/service-ondeviceintelligence.txt",
            "36/system-server/api/service-ondeviceintelligence-removed.txt",
        ] {
            let mut incomplete = lock.clone();
            incomplete.projects.iter_mut().find(|project| project.path == Path::new("prebuilts/sdk")).unwrap()
                .sparse_paths.retain(|path| path != Path::new(missing));
            assert!(validate_audio_provider_source_paths(&incomplete, audio).is_err(), "{missing}");
        }
        let mut wrong = lock.clone();
        wrong.projects.iter_mut().find(|project| project.path == Path::new("prebuilts/sdk")).unwrap()
            .commit = "0000000000000000000000000000000000000000".into();
        assert!(validate_audio_provider_source_paths(&wrong, audio).is_err());
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
            SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            validate_audio_provider_source_paths(&wrong, mode).unwrap();
        }
    }

    #[test]
    fn audio_ondeviceintelligence_original_api_guard_rejects_drift_missing_and_links() {
        let directory = tempfile::tempdir().unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        for (relative, bytes) in [
            ("prebuilts/sdk/36/public/api/service-ondeviceintelligence.txt", include_bytes!("../tests/fixtures/audio-ondeviceintelligence-api/36/public/api/service-ondeviceintelligence.txt") as &[u8]),
            ("prebuilts/sdk/36/public/api/service-ondeviceintelligence-removed.txt", include_bytes!("../tests/fixtures/audio-ondeviceintelligence-api/36/public/api/service-ondeviceintelligence-removed.txt") as &[u8]),
            ("prebuilts/sdk/36/system-server/api/service-ondeviceintelligence.txt", include_bytes!("../tests/fixtures/audio-ondeviceintelligence-api/36/system-server/api/service-ondeviceintelligence.txt") as &[u8]),
            ("prebuilts/sdk/36/system-server/api/service-ondeviceintelligence-removed.txt", include_bytes!("../tests/fixtures/audio-ondeviceintelligence-api/36/system-server/api/service-ondeviceintelligence-removed.txt") as &[u8]),
        ] {
            write(&directory.path().join(relative), bytes).unwrap();
        }
        validate_audio_ondeviceintelligence_api_inputs(directory.path(), audio).unwrap();
        for (relative, _, _) in AUDIO_ONDEVICEINTELLIGENCE_API_INPUTS {
            let path = directory.path().join(relative);
            let original = fs::read(&path).unwrap();
            let mut changed = original.clone();
            changed[0] ^= 1;
            write(&path, &changed).unwrap();
            assert!(validate_audio_ondeviceintelligence_api_inputs(directory.path(), audio).is_err(), "{relative}");
            fs::remove_file(&path).unwrap();
            assert!(validate_audio_ondeviceintelligence_api_inputs(directory.path(), audio).is_err(), "{relative}");
            let referent = directory.path().join("original-api");
            write(&referent, &original).unwrap();
            std::os::unix::fs::symlink(&referent, &path).unwrap();
            assert!(validate_audio_ondeviceintelligence_api_inputs(directory.path(), audio).is_err(), "{relative}");
            fs::remove_file(&path).unwrap();
            fs::remove_file(&referent).unwrap();
            write(&path, &original).unwrap();
        }
        validate_audio_ondeviceintelligence_api_inputs(directory.path(), audio).unwrap();
        let empty = tempfile::tempdir().unwrap();
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
            SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            validate_audio_ondeviceintelligence_api_inputs(empty.path(), mode).unwrap();
        }
    }

    #[test]
    fn audio_pasit_old_425_lock_reproduces_missing_original_project() {
        use sha2::{Digest, Sha256};
        let current = audio_before_ondeviceintelligence_lock();
        let (prefix, _) = current.split_once(",\n    {\n      \"path\": \"tools/test/desktop/mobly\",").unwrap();
        let old = format!("{prefix}\n  ]\n}}\n");
        assert_eq!(format!("{:x}", Sha256::digest(old.as_bytes())),
            "1dd0671551fb3c07cac4bb9b587346421321a6e4809494299f7b6daa4c49371c");
        let d = tempfile::tempdir().unwrap();
        let path = d.path().join("android/manifest/audio-bridge-source-lock.json");
        write(&path, old.as_bytes()).unwrap();
        let old_lock = droidloom_source::load_lock(&path).unwrap();
        assert_eq!(old_lock.projects.len(), 425);
        assert!(validate_audio_provider_source_paths(&old_lock,
            SoongDependencyMode::AudioApexTargetClosure).is_err());
        assert!(selected_source_lock(d.path(), SoongDependencyMode::AudioApexTargetClosure).is_err());
        let old_value: serde_json::Value = serde_json::from_str(&old).unwrap();
        let new_value: serde_json::Value = serde_json::from_str(&current).unwrap();
        assert_eq!(new_value["projects"].as_array().unwrap().len(), 430);
        assert_eq!(&new_value["projects"].as_array().unwrap()[..425],
            old_value["projects"].as_array().unwrap().as_slice());
        for name in ["superproject", "links", "policy", "remote_base", "schema_version", "selected_at", "status"] {
            assert_eq!(new_value[name], old_value[name], "{name}");
        }
    }

    #[test]
    fn audio_pasit_requires_all_five_complete_same_commit_sources() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let lock = droidloom_source::load_lock(
            &repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        validate_audio_provider_source_paths(&lock, audio).unwrap();
        for path in [
            "tools/test/desktop/mobly",
            "external/grpc-grpc",
            "external/chromiumos-config",
            "external/python/snippet-uiautomator",
            "external/mobly-snippet-lib",
        ] {
            let mut absent = lock.clone();
            absent.projects.retain(|project| project.path != Path::new(path));
            assert!(validate_audio_provider_source_paths(&absent, audio).is_err(), "{path}");
            for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
                validate_audio_provider_source_paths(&absent, mode).unwrap();
            }
            let mut incomplete = lock.clone();
            incomplete.projects.iter_mut().find(|project| project.path == Path::new(path)).unwrap()
                .sparse_paths = vec![PathBuf::from("Android.bp")];
            assert!(validate_audio_provider_source_paths(&incomplete, audio).is_err(), "{path}");
            let mut wrong = lock.clone();
            wrong.projects.iter_mut().find(|project| project.path == Path::new(path)).unwrap()
                .commit = "0000000000000000000000000000000000000000".into();
            assert!(validate_audio_provider_source_paths(&wrong, audio).is_err(), "{path}");
        }
    }

    fn audio_pasit_fixture_tree(source: &Path) {
        for (relative, bytes) in [
            ("tools/test/desktop/mobly/lib/pasit/Android.bp", include_bytes!("../tests/fixtures/audio-pasit-original/tools__test__desktop__mobly__lib__pasit__Android.bp") as &[u8]),
            ("tools/test/desktop/mobly/lib/pasit/passport/Android.bp", include_bytes!("../tests/fixtures/audio-pasit-original/tools__test__desktop__mobly__lib__pasit__passport__Android.bp") as &[u8]),
            ("tools/test/desktop/mobly/lib/pasit/snippets/hid/Android.bp", include_bytes!("../tests/fixtures/audio-pasit-original/tools__test__desktop__mobly__lib__pasit__snippets__hid__Android.bp") as &[u8]),
            ("tools/test/desktop/mobly/lib/utils/Android.bp", include_bytes!("../tests/fixtures/audio-pasit-original/tools__test__desktop__mobly__lib__utils__Android.bp") as &[u8]),
            ("tools/test/desktop/mobly/tests/pasit/Android.bp", include_bytes!("../tests/fixtures/audio-pasit-original/tools__test__desktop__mobly__tests__pasit__Android.bp") as &[u8]),
            ("external/grpc-grpc/Android.bp", include_bytes!("../tests/fixtures/audio-pasit-original/external__grpc-grpc__Android.bp") as &[u8]),
            ("external/grpc-grpc/src/python/grpcio/Android.bp", include_bytes!("../tests/fixtures/audio-pasit-original/external__grpc-grpc__src__python__grpcio__Android.bp") as &[u8]),
            ("external/grpc-grpc/third_party/address_sorting/Android.bp", include_bytes!("../tests/fixtures/audio-pasit-original/external__grpc-grpc__third_party__address_sorting__Android.bp") as &[u8]),
            ("external/grpc-grpc/third_party/upb/Android.bp", include_bytes!("../tests/fixtures/audio-pasit-original/external__grpc-grpc__third_party__upb__Android.bp") as &[u8]),
            ("external/grpc-grpc/third_party/utf8_range/Android.bp", include_bytes!("../tests/fixtures/audio-pasit-original/external__grpc-grpc__third_party__utf8_range__Android.bp") as &[u8]),
            ("external/grpc-grpc/third_party/xxhash/Android.bp", include_bytes!("../tests/fixtures/audio-pasit-original/external__grpc-grpc__third_party__xxhash__Android.bp") as &[u8]),
            ("external/chromiumos-config/Android.bp", include_bytes!("../tests/fixtures/audio-pasit-original/external__chromiumos-config__Android.bp") as &[u8]),
            ("external/chromiumos-config/python/Android.bp", include_bytes!("../tests/fixtures/audio-pasit-original/external__chromiumos-config__python__Android.bp") as &[u8]),
            ("external/python/snippet-uiautomator/Android.bp", include_bytes!("../tests/fixtures/audio-pasit-original/external__python__snippet-uiautomator__Android.bp") as &[u8]),
            ("external/python/snippet-uiautomator/snippet_uiautomator/Android.bp", include_bytes!("../tests/fixtures/audio-pasit-original/external__python__snippet-uiautomator__snippet_uiautomator__Android.bp") as &[u8]),
            ("external/mobly-snippet-lib/Android.bp", include_bytes!("../tests/fixtures/audio-pasit-original/external__mobly-snippet-lib__Android.bp") as &[u8]),
        ] {
            write(&source.join(relative), bytes).unwrap();
        }
    }

    #[test]
    fn audio_pasit_original_provider_guard_rejects_drift_missing_and_links() {
        let d = tempfile::tempdir().unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        audio_pasit_fixture_tree(d.path());
        validate_audio_pasit_original_providers(d.path(), audio).unwrap();
        for (relative, _, _) in AUDIO_PASIT_ORIGINAL_PROVIDERS {
            let path = d.path().join(relative);
            let original = fs::read(&path).unwrap();
            let mut changed = original.clone();
            changed[0] ^= 1;
            write(&path, &changed).unwrap();
            assert!(validate_audio_pasit_original_providers(d.path(), audio).is_err(), "{relative}");
            fs::remove_file(&path).unwrap();
            assert!(validate_audio_pasit_original_providers(d.path(), audio).is_err(), "{relative}");
            let referent = d.path().join("original-provider");
            write(&referent, &original).unwrap();
            std::os::unix::fs::symlink(&referent, &path).unwrap();
            assert!(validate_audio_pasit_original_providers(d.path(), audio).is_err(), "{relative}");
            fs::remove_file(&path).unwrap();
            fs::remove_file(&referent).unwrap();
            write(&path, &original).unwrap();
        }
        validate_audio_pasit_original_providers(d.path(), audio).unwrap();
        let empty = tempfile::tempdir().unwrap();
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
            SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            validate_audio_pasit_original_providers(empty.path(), mode).unwrap();
        }
    }

    #[test]
    fn audio_pasit_retains_original_consumer_defaults_and_transitive_edges() {
        use sha2::{Digest, Sha256};
        let consumer = include_str!("../tests/fixtures/audio-pasit-original/desktop-test-lib-mobly-consumer.bp");
        assert_eq!(format!("{:x}", Sha256::digest(consumer.as_bytes())),
            "bf1647bf57fab65f5ff2fa7a82b434bb909880f1e258edebf163f8dea48672f0");
        assert!(consumer.contains("name: \"DesktopTestLibTestsMobly\""));
        assert!(consumer.contains("defaults: [\"PASIT-defaults\"]"));
        let defaults = include_str!("../tests/fixtures/audio-pasit-original/tools__test__desktop__mobly__tests__pasit__Android.bp");
        for retained in ["PASIT-defaults", "mobly", "py-pasit-test", "platform-test-py-annotations"] {
            assert!(defaults.contains(&format!("\"{retained}\"")), "{retained}");
        }
        let provider = include_str!("../tests/fixtures/audio-pasit-original/tools__test__desktop__mobly__lib__pasit__Android.bp");
        for retained in ["py-pasit-test", "py-pasit-device", "py-passport",
            "py-snippet-uiautomator", "py-grpcio", "libprotobuf-python",
            "py-chromiumos-config-passport", "py-desktop-utils"] {
            assert!(provider.contains(&format!("\"{retained}\"")), "{retained}");
        }
        let snippet = include_str!("../tests/fixtures/audio-pasit-original/external__python__snippet-uiautomator__snippet_uiautomator__Android.bp");
        assert!(snippet.contains("\"mobly-snippet-lib\""));
        assert!(include_str!("../tests/fixtures/audio-pasit-original/external__mobly-snippet-lib__Android.bp")
            .contains("\"androidx.test.runner\""));
    }


    #[test]
    fn audio_error_prone_restores_original_provider_and_retained_consumer_edge() {
        use sha2::{Digest, Sha256};
        let original = include_str!("../tests/fixtures/audio-providers/error-prone.bp");
        let consumer = include_str!("../tests/fixtures/audio-providers/systemfeatures.bp");
        let jimfs = include_str!("../tests/fixtures/audio-providers/jimfs.bp");
        for (bytes, expected) in [
            (original, "a8647e651304f9b1a6ff3740aade8723cd0628e711fdc9c18b17ec01790f959f"),
            (consumer, "1fb7036ce96dfc24f8ecbcb8db38af465de259132e85a07a674b58ab23869a3c"),
            (jimfs, "ba0aca424deb294572edec43cd2df0e269a82b87d6371a58ef876105f327e540"),
        ] {
            assert_eq!(format!("{:x}", Sha256::digest(bytes.as_bytes())), expected);
        }
        // This is the exact failed old transformation, with its real consumer.
        let old = private_without_named_java_module(original,
            "java_library_host", "error_prone_test_helpers").unwrap();
        assert!(!old.contains("name: \"error_prone_test_helpers\""));
        assert!(consumer.contains("name: \"systemfeatures-errorprone-tests\""));
        assert!(consumer.contains("\"error_prone_test_helpers\""));
        let current = native_leaf_error_prone(original,
            SoongDependencyMode::AudioApexTargetClosure).unwrap();
        assert_eq!(current.as_bytes(), original.as_bytes());
        for dependency in ["error_prone_check_api", "jimfs", "compile-testing-prebuilt",
            "error_prone_annotations", "google_java_format", "hamcrest", "hamcrest-library",
            "jspecify", "junit", "truth"] {
            assert!(current.contains(&format!("\"{dependency}\"")), "{dependency}");
        }
        for dependency in ["jimfs-annotation-stubs-srcjar", "auto_service_annotations",
            "guava", "icu4j", "auto_service_plugin", "gen_annotations.py", "soong_zip"] {
            assert!(jimfs.contains(dependency), "{dependency}");
        }
        for path in ["external/error_prone/Android.bp", "external/jimfs/jimfs/Android.bp",
                     "frameworks/base/tools/systemfeatures/Android.bp"] {
            assert!(!SOONG_EXCLUDED_TEST_FIXTURES.contains(&path));
        }
    }

    #[test]
    fn audio_error_prone_requires_pinned_complete_provider_and_keeps_other_scope() {
        let original = include_str!("../tests/fixtures/audio-providers/error-prone.bp");
        let old = private_without_named_java_module(original,
            "java_library_host", "error_prone_test_helpers").unwrap();
        assert!(native_leaf_error_prone(&old, SoongDependencyMode::AudioApexTargetClosure).is_err());
        assert!(native_leaf_error_prone(&(original.to_owned() + "\n"),
            SoongDependencyMode::AudioApexTargetClosure).is_err());
        assert_eq!(native_leaf_error_prone(original,
            SoongDependencyMode::MinigbmTargetClosure).unwrap(), old);
        assert!(PRIVATE_NATIVEBRIDGE_UNRELATED_JAVA_MODULES.iter().any(
            |(path, kind, names)| *path == "external/error_prone/Android.bp"
                && *kind == "java_library_host" && names == &["error_prone_test_helpers"]));
    }

    #[test]
    fn audio_error_prone_jimfs_requires_original_full_cone_and_commit() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let lock = droidloom_source::load_lock(
            &repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        validate_audio_provider_source_paths(&lock, audio).unwrap();
        let mut absent = lock.clone();
        absent.projects.retain(|project| project.path != Path::new("external/jimfs"));
        assert!(validate_audio_provider_source_paths(&absent, audio).is_err());
        let mut header_only = lock.clone();
        header_only.projects.iter_mut().find(|p| p.path == Path::new("external/jimfs")).unwrap()
            .sparse_paths = vec![PathBuf::from("jimfs/Android.bp")];
        assert!(validate_audio_provider_source_paths(&header_only, audio).is_err());
        let mut wrong = lock.clone();
        wrong.projects.iter_mut().find(|p| p.path == Path::new("external/jimfs")).unwrap()
            .commit = "0000000000000000000000000000000000000000".into();
        assert!(validate_audio_provider_source_paths(&wrong, audio).is_err());
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            validate_audio_provider_source_paths(&absent, mode).unwrap();
        }
    }

    #[test]
    fn audio_error_prone_projection_preserves_original_bytes_and_recovers_journal() {
        let fixture = tempfile::tempdir().unwrap();
        let original = include_bytes!("../tests/fixtures/audio-providers/error-prone.bp");
        let consumer = include_bytes!("../tests/fixtures/audio-providers/systemfeatures.bp");
        let provider_path = fixture.path().join("external/error_prone/Android.bp");
        let consumer_path = fixture.path().join("frameworks/base/tools/systemfeatures/Android.bp");
        write(&provider_path, original).unwrap();
        write(&consumer_path, consumer).unwrap();
        let old_time = fs::metadata(&provider_path).unwrap().modified().unwrap();
        let journal = fixture.path().join("source-projection.json");
        {
            let mut p = Projection::new(journal.clone()).unwrap();
            let projected = native_leaf_error_prone(std::str::from_utf8(original).unwrap(),
                SoongDependencyMode::AudioApexTargetClosure).unwrap();
            p.put(&provider_path, projected).unwrap();
            assert_eq!(fs::read(&provider_path).unwrap(), original);
            assert_eq!(fs::read(&consumer_path).unwrap(), consumer);
            assert!(journal.exists());
            p.restore().unwrap();
        }
        assert!(!journal.exists());
        assert_eq!(fs::read(&provider_path).unwrap(), original);
        assert_eq!(fs::read(&consumer_path).unwrap(), consumer);
        assert_eq!(fs::metadata(&provider_path).unwrap().modified().unwrap(), old_time);
    }

    #[test]
    fn audio_actual_three_defaults_regression_preserves_original_consumers_and_providers() {
        let mode = SoongDependencyMode::AudioApexTargetClosure;
        let systemui = include_str!("../tests/fixtures/audio-providers/systemui.bp");
        let shell = include_str!("../tests/fixtures/audio-providers/shell.bp");
        let tests = include_str!("../tests/fixtures/audio-providers/systemui-tests.bp");
        let perf = include_str!("../tests/fixtures/audio-providers/structured-concurrency-tests.bp");
        let automotive = include_str!("../tests/fixtures/audio-providers/automotive-audiocontrol.bp");
        let power = include_str!("../tests/fixtures/audio-providers/car-power-client.bp");
        // These are the unmodified consumers from the failed real Soong run,
        // not reduced fixtures or replacement defaults declarations.
        for (text, expected) in [
            (tests, "f1b2422c693a8f8c52034369ded585a3a93ac861f9dd6dd73f0801a77e6be4da"),
            (perf, "02923c7af8aea6162312ce2d846ddea19c9703a72aeb4ba8a5ccc69fb7440c9c"),
            (automotive, "9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6"),
            (power, "dff094a9867822aba3b96f236ca2092f1640ba2c40f0c063e0b8b19c10282c38"),
        ] {
            use sha2::{Digest, Sha256};
            assert_eq!(format!("{:x}", Sha256::digest(text.as_bytes())), expected);
        }
        assert!(tests.contains("defaults: [\"systemui-non-platform-apis-defaults\"]"));
        assert!(tests.contains("static_libs: [\"SystemUI-tests\"]"));
        assert!(tests.contains("\"SystemUI-application\""));
        assert!(perf.contains("\"SystemUI_optimized_defaults\""));
        assert!(perf.contains("included_proguard_flags_files: [\":sysui_proguard_common_and_kotlin\"]"));
        assert!(automotive.contains("\"powerpolicyclient_defaults\""));

        // Reproduce the real old failure: metadata_only deleted both defaults.
        let old_systemui = metadata_only(systemui).unwrap();
        for name in ["systemui-non-platform-apis-defaults", "SystemUI_optimized_defaults"] {
            assert!(!old_systemui.contains(&format!("name: \"{name}\"")));
        }
        let new_systemui = audio_original_shared_provider(
            "frameworks/base/packages/SystemUI/Android.bp", systemui, mode).unwrap().unwrap();
        let new_shell = audio_original_shared_provider(
            "frameworks/base/libs/WindowManager/Shell/Android.bp", shell, mode).unwrap().unwrap();
        assert_eq!(new_systemui.as_bytes(), systemui.as_bytes());
        assert_eq!(new_shell.as_bytes(), shell.as_bytes());
        for name in ["systemui-non-platform-apis-defaults", "systemui_optimized_java_defaults",
                     "SystemUI_optimized_defaults", "SystemUI-tests", "SystemUI-application",
                     "sysui_proguard_common_and_kotlin"] {
            assert!(new_systemui.contains(&format!("name: \"{name}\"")), "{name}");
        }
        assert!(new_shell.contains("name: \"wmshell_defaults\""));
        for name in ["powerpolicyclient_defaults", "powerpolicyclient_lib_build_defaults", "libpowerpolicyclient"] {
            assert!(power.contains(&format!("name: \"{name}\"")), "{name}");
        }
        for edge in ["android.frameworks.automotive.powerpolicy-V3-ndk", "libbase", "libbinder_ndk", "libutils",
                     "src/PowerPolicyClientBase.cpp", "export_include_dirs: [\"include\"]"] {
            assert!(power.contains(edge), "{edge}");
        }
    }

    #[test]
    fn audio_shared_provider_visibility_is_exact_and_scoped() {
        let original = include_str!("../tests/fixtures/audio-providers/systemui.bp");
        let relative = "frameworks/base/packages/SystemUI/Android.bp";
        assert!(audio_original_shared_provider(relative, &(original.to_owned() + "\n"),
            SoongDependencyMode::AudioApexTargetClosure).is_err());
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            assert!(audio_original_shared_provider(relative, original, mode).unwrap().is_none());
        }
        assert!(audio_original_shared_provider("packages/apps/Settings/Android.bp", "unmodified other route",
            SoongDependencyMode::AudioApexTargetClosure).unwrap().is_none());
    }

    #[test]
    fn audio_allgraph_required_discovery_preserves_sources_and_rejects_foreign_markers() {
        for (relative, probe, original) in [
            ("cts/common/device-side/nativetesthelper/jni", "cts/common/device-side/nativetesthelper/jni/Android.bp", include_bytes!("../tests/fixtures/audio-providers/allgraph-nativetesthelper-jni.bp").as_slice()),
            ("frameworks/base/core/tests", "frameworks/base/core/tests/coretests/Android.bp", include_bytes!("../tests/fixtures/audio-providers/allgraph-framework-coretests.bp").as_slice()),
            ("frameworks/base/services/tests", "frameworks/base/services/tests/servicestests/Android.bp", include_bytes!("../tests/fixtures/audio-providers/allgraph-framework-servicestests.bp").as_slice()),
        ] {
            let d = tempfile::tempdir().unwrap();
            let source = d.path().join("source");
            write(&source.join(probe), original).unwrap();
            let marker = source.join(relative).join(".find-ignore");
            let mut projection = Projection::new(d.path().join("projection.json")).unwrap();
            project_discovery_exclusion(&mut projection, &source, relative,
                SoongDependencyMode::AudioApexTargetClosure).unwrap();
            assert!(!marker.exists());
            assert_eq!(fs::read(source.join(probe)).unwrap(), original);
            for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                         SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
                project_discovery_exclusion(&mut projection, &source, relative, mode).unwrap();
                assert!(marker.is_file());
                projection.restore().unwrap();
                assert!(!marker.exists());
            }
            write(&marker, b"foreign marker").unwrap();
            assert!(project_discovery_exclusion(&mut projection, &source, relative,
                SoongDependencyMode::AudioApexTargetClosure).is_err());
            assert_eq!(fs::read(&marker).unwrap(), b"foreign marker");
            fs::remove_file(&marker).unwrap();
            std::os::unix::fs::symlink("absent-target", &marker).unwrap();
            assert!(audio_keep_required_discovery(&source, relative,
                SoongDependencyMode::AudioApexTargetClosure).is_err());
            assert!(fs::symlink_metadata(&marker).unwrap().file_type().is_symlink());
            fs::remove_file(&marker).unwrap();
            write(&source.join(probe), b"different original provider").unwrap();
            assert!(project_discovery_exclusion(&mut projection, &source, relative,
                SoongDependencyMode::AudioApexTargetClosure).is_err());
            assert!(!marker.exists());
        }
    }

    #[test]
    fn audio_required_settings_discovery_rejects_foreign_markers_without_removing_them() {
        let d = tempfile::tempdir().unwrap();
        let relative = "frameworks/base/packages/SettingsLib";
        let path = d.path().join(relative);
        write(&path.join("Android.bp"), include_bytes!("../tests/fixtures/audio-providers/settingslib.bp")).unwrap();
        assert!(audio_keep_required_discovery(d.path(), relative, SoongDependencyMode::AudioApexTargetClosure).unwrap());
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            assert!(!audio_keep_required_discovery(d.path(), relative, mode).unwrap());
        }
        assert!(!audio_keep_required_discovery(d.path(), "other/provider", SoongDependencyMode::AudioApexTargetClosure).unwrap());
        let marker = path.join(".find-ignore");
        write(&marker, b"foreign marker must remain").unwrap();
        assert!(audio_keep_required_discovery(d.path(), relative, SoongDependencyMode::AudioApexTargetClosure).is_err());
        assert_eq!(fs::read(&marker).unwrap(), b"foreign marker must remain");
        fs::remove_file(&marker).unwrap();
        write(&path.join("Android.bp"), b"different original").unwrap();
        assert!(audio_keep_required_discovery(d.path(), relative, SoongDependencyMode::AudioApexTargetClosure).is_err());
    }

    #[test]
    fn audio_room_processor_keeps_original_transitive_dependencies() {
        let original = include_str!("../tests/fixtures/audio-providers/java-plugins.bp");
        let audio = native_leaf_java_plugins(original, SoongDependencyMode::AudioApexTargetClosure).unwrap();
        let marker = "java_plugin {\n    name: \"androidx.room_room-compiler-plugin\",";
        let start = original.find(marker).unwrap();
        let end = start + original[start..].find("\n}\n").unwrap() + 3;
        assert!(audio.contains(&original[start..end]));
        assert!(audio.contains("\"androidx.room_room-compiler\""));
        assert!(audio.contains("\"kotlin-reflect\""));
        // The incoming MediaProvider/AdServices/Permission consumers also
        // need AppSearch; retain this complete pinned original provider BP.
        assert_eq!(audio, original);
        for name in ["androidx.appsearch_appsearch-compiler-plugin", "androidx.appfunctions_appfunctions-compiler-plugin"] {
            assert!(audio.contains(&format!("name: \"{name}\"")));
        }
        assert!(!native_leaf_java_plugins(original, SoongDependencyMode::MinigbmTargetClosure).unwrap().contains(marker));
        assert!(native_leaf_java_plugins(&(original.to_owned() + "\n"), SoongDependencyMode::AudioApexTargetClosure).is_err());
    }

    #[test]
    fn audio_launcher_tapl_preserves_original_generator_chain_and_dependency_bodies() {
        let original = include_str!("../tests/fixtures/audio-providers/launcher.bp");
        let shared = include_str!("../tests/fixtures/audio-providers/launcher-shared.bp");
        let relative = "packages/apps/Launcher3/Android.bp";
        let marker = "android_library {\n    name: \"launcher-aosp-tapl\",";
        assert!(!metadata_only(original).unwrap().contains(marker));
        let projected = audio_original_shared_provider(relative, original,
            SoongDependencyMode::AudioApexTargetClosure).unwrap().unwrap();
        for (kind, name) in [("android_library", "launcher-aosp-tapl"),
                             ("genrule", "launcher-tapl-build-config"),
                             ("sh_binary_host", "launcher-build-config-tool")] {
            let marker = format!("{kind} {{\n    name: \"{name}\",");
            let start = original.find(&marker).unwrap();
            let end = start + original[start..].find("\n}\n").unwrap() + 3;
            assert_eq!(projected.matches(&original[start..end]).count(), 1, "{name}");
        }
        for dependency in ["launcher-testing-shared", "SystemUISharedLib",
                           "//frameworks/libs/systemui:animationlib",
                           "//frameworks/libs/systemui:contextualeducationlib",
                           "com_android_launcher3_flags_lib", "tools/buildconfig.sh",
                           "tests/tapl/**/*.java", "tests/tapl/**/*.kt",
                           "tests/tapl/AndroidManifest.xml"] {
            assert!(projected.contains(dependency), "{dependency}");
        }
        assert!(!projected.contains("name: \"Launcher3\""));
        assert!(projected.starts_with(&metadata_only(original).unwrap()));
        assert!(shared.contains("min_sdk_version: min_launcher3_sdk_version"));
        let assignment = original.lines().find(|line| line.starts_with("min_launcher3_sdk_version = ")).unwrap();
        assert_eq!(assignment, "min_launcher3_sdk_version = \"31\"");
        assert_eq!(projected.matches(assignment).count(), 1);
        assert!(!metadata_only(original).unwrap().contains(assignment));
        assert!(audio_original_shared_provider(relative, &(original.to_owned() + "\n"),
            SoongDependencyMode::AudioApexTargetClosure).is_err());
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            assert!(audio_original_shared_provider(relative, original, mode).unwrap().is_none());
        }
    }

    #[test]
    fn audio_new_launcher_ancestor_tests_keep_only_the_unselected_root_scope() {
        let original = include_str!("../tests/fixtures/audio-providers/launcher-tests.bp");
        let root = include_str!("../tests/fixtures/audio-providers/launcher.bp");
        let shared = include_str!("../tests/fixtures/audio-providers/launcher-shared.bp");
        let relative = "packages/apps/Launcher3/tests/Android.bp";
        let projected = audio_new_source_root_scope(relative, original,
            SoongDependencyMode::AudioApexTargetClosure).unwrap().unwrap();
        assert_eq!(projected, metadata_only(original).unwrap());
        let retained = audio_original_launcher_tapl_provider(root).unwrap() + shared;
        for name in ["Launcher3TestLib", "Launcher3TestResources", "Launcher3Tests",
                     "launcher-non-quickstep-tests-src", "launcher-oop-tests-src",
                     "launcher-testing-helpers", "launcher-testing-helpers-robo",
                     "launcher-tests-src", "launcher3-robo-src"] {
            assert!(original.contains(&format!("name: \"{name}\"")), "{name}");
            assert!(!projected.contains(&format!("\"{name}\"")), "{name}");
            assert!(!retained.contains(&format!("\"{name}\"")), "{name}");
            assert!(!retained.contains(&format!("\":{name}\"")), "{name}");
        }
        assert!(projected.contains("default_applicable_licenses"));
        assert!(projected.contains("default_team: \"trendy_team_launcher\""));
        assert!(!original.contains("name: \"launcher-aosp-tapl\""));
        assert!(retained.contains("name: \"launcher-aosp-tapl\""));
        assert!(audio_new_source_root_scope(relative, &(original.to_owned() + "\n"),
            SoongDependencyMode::AudioApexTargetClosure).is_err());
        assert!(audio_new_source_root_scope("packages/apps/Launcher3/shared/Android.bp", shared,
            SoongDependencyMode::AudioApexTargetClosure).unwrap().is_none());
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            assert!(audio_new_source_root_scope(relative, original, mode).unwrap().is_none());
        }
    }

    #[test]
    fn audio_new_crossdevice_roots_preserve_license_and_independent_original_flags() {
        let root = include_str!("../tests/fixtures/audio-providers/crossdevice.bp");
        let testlib = include_str!("../tests/fixtures/audio-providers/crossdevice-testlib.bp");
        let flags = include_str!("../tests/fixtures/audio-providers/crossdevice-flags.bp");
        for (relative, original, names) in [
            ("packages/services/CrossDeviceSync/Android.bp", root,
             &["CrossDeviceSync-srcs", "CrossDeviceSync-res", "CrossDeviceSync", "CrossDeviceSyncTests"][..]),
            ("packages/services/CrossDeviceSync/lib/Android.bp", testlib,
             &["CrossDeviceSync-testlib", "CrossDeviceSync-testlib-tests"][..]),
        ] {
            let projected = audio_new_source_root_scope(relative, original,
                SoongDependencyMode::AudioApexTargetClosure).unwrap().unwrap();
            assert_eq!(projected, metadata_only(original).unwrap());
            assert!(projected.contains("packages_services_CrossDeviceSync_license"));
            for name in names {
                assert!(original.contains(&format!("name: \"{name}\"")), "{name}");
                assert!(!projected.contains(&format!("\"{name}\"")), "{name}");
                assert!(!flags.contains(&format!("\"{name}\"")), "{name}");
                assert!(!flags.contains(&format!("\":{name}\"")), "{name}");
            }
            assert!(audio_new_source_root_scope(relative, &(original.to_owned() + "\n"),
                SoongDependencyMode::AudioApexTargetClosure).is_err());
            for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                         SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
                assert!(audio_new_source_root_scope(relative, original, mode).unwrap().is_none());
            }
        }
        let projected = audio_new_source_root_scope("packages/services/CrossDeviceSync/Android.bp", root,
            SoongDependencyMode::AudioApexTargetClosure).unwrap().unwrap();
        assert!(projected.contains("name: \"packages_services_CrossDeviceSync_license\""));
        assert!(projected.contains("\"NOTICE\""));
        assert!(flags.contains("name: \"com_android_crossdevicesync_flags_lib\""));
        assert!(flags.contains("aconfig_declarations: \"com_android_crossdevicesync_flags\""));
        assert!(audio_new_source_root_scope(
            "packages/services/CrossDeviceSync/src/com/android/crossdevicesync/flags/Android.bp", flags,
            SoongDependencyMode::AudioApexTargetClosure).unwrap().is_none());
    }

    #[test]
    fn audio_power_provider_requires_complete_original_cone_without_changing_other_routes() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let path = selected_source_lock(repo, SoongDependencyMode::AudioApexTargetClosure).unwrap();
        let original = droidloom_source::load_lock(&path).unwrap();
        validate_audio_provider_source_paths(&original, SoongDependencyMode::AudioApexTargetClosure).unwrap();
        let mut old = original.clone();
        let car = old.projects.iter_mut().find(|p| p.path == Path::new("packages/services/Car")).unwrap();
        let retained = car.sparse_paths.len();
        car.sparse_paths.retain(|p| p != Path::new("cpp/power/client"));
        assert_eq!(car.sparse_paths.len() + 1, retained);
        assert!(!cone_covers_metadata(Path::new("cpp/power/client/Android.bp"), &car.sparse_paths));
        assert!(validate_audio_provider_source_paths(&old, SoongDependencyMode::AudioApexTargetClosure).is_err());
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            validate_audio_provider_source_paths(&old, mode).unwrap();
        }
        let mut headers_only = old.clone();
        headers_only.projects.iter_mut().find(|p| p.path == Path::new("packages/services/Car"))
            .unwrap().sparse_paths.push(PathBuf::from("cpp/power/client/include"));
        // Cone ancestry makes the BP visible, but source dependencies must
        // still materialize; a headers-only substitute cannot close this gate.
        assert!(validate_audio_provider_source_paths(&headers_only, SoongDependencyMode::AudioApexTargetClosure).is_err());
        let mut wrong_revision = original;
        wrong_revision.projects.iter_mut().find(|p| p.path == Path::new("packages/services/Car"))
            .unwrap().commit = "0000000000000000000000000000000000000000".into();
        assert!(validate_audio_provider_source_paths(&wrong_revision, SoongDependencyMode::AudioApexTargetClosure).is_err());
    }

    #[test]
    fn audio_gatekeeper_requires_the_complete_locked_rust_provider_cones() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let lock = droidloom_source::load_lock(
            &repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        assert!(validate_audio_provider_source_paths(&lock, audio).is_ok());
        for relative in ["system/gatekeeper", "system/security"] {
            let mut missing_project = lock.clone();
            missing_project.projects.retain(|p| p.path != Path::new(relative));
            assert!(validate_audio_provider_source_paths(&missing_project, audio).is_err());
            let mut changed = lock.clone();
            changed.projects.iter_mut().find(|p| p.path == Path::new(relative))
                .unwrap().commit = "0000000000000000000000000000000000000000".into();
            assert!(validate_audio_provider_source_paths(&changed, audio).is_err());
            for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                         SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
                assert!(validate_audio_provider_source_paths(&missing_project, mode).is_ok());
            }
        }
        for (relative, required) in [
            ("system/gatekeeper", "include"), ("system/gatekeeper", "rust"),
            ("system/security", "hals/Android.bp"), ("system/security", "hals/derive"),
            ("system/security", "hals/wire"),
        ] {
            let mut missing_cone = lock.clone();
            let provider = missing_cone.projects.iter_mut()
                .find(|p| p.path == Path::new(relative)).unwrap();
            provider.sparse_paths.retain(|p| p != Path::new(required));
            assert!(validate_audio_provider_source_paths(&missing_cone, audio).is_err());
        }
    }


    #[test]
    fn audio_cts_sts_recursive_closure_requires_all_original_source_cones() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let lock = droidloom_source::load_lock(
            &repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        validate_audio_provider_source_paths(&lock, audio).unwrap();
        for (relative, required) in [
            ("cts", "hostsidetests/appcompat/host/lib"),
            ("cts", "hostsidetests/appsecurity/certs"),
            ("cts", "hostsidetests/appsecurity/res"),
            ("cts", "hostsidetests/appsecurity/src"),
            ("cts", "hostsidetests/appsecurity/test-apps/AppAccessData"),
            ("cts", "hostsidetests/appsecurity/test-apps/AppDataIsolationTestApp"),
            ("cts", "hostsidetests/appsecurity/test-apps/AppWithData"),
            ("cts", "hostsidetests/appsecurity/test-apps/DeclarePermissionsWithSpacesApp"),
            ("cts", "hostsidetests/appsecurity/test-apps/DeviceIdentifiers"),
            ("cts", "hostsidetests/appsecurity/test-apps/DuplicatePermissionDeclareApp"),
            ("cts", "hostsidetests/appsecurity/test-apps/DuplicatePermissionSameGroup"),
            ("cts", "hostsidetests/appsecurity/test-apps/InstrumentationAppDiffCert"),
            ("cts", "hostsidetests/appsecurity/test-apps/KeyRotationTest"),
            ("cts", "hostsidetests/appsecurity/test-apps/KeyStoreManagerTest"),
            ("cts", "hostsidetests/appsecurity/test-apps/ListeningPortsApp"),
            ("cts", "hostsidetests/appsecurity/test-apps/MalformedDuplicatePermission"),
            ("cts", "hostsidetests/appsecurity/test-apps/PackageInstallerPermissionRequestApp"),
            ("cts", "hostsidetests/appsecurity/test-apps/PackageInstallerWhitelistApp"),
            ("cts", "hostsidetests/appsecurity/test-apps/PermissionDeclareApp"),
            ("cts", "hostsidetests/appsecurity/test-apps/PermissionDeclareAppCompat"),
            ("cts", "hostsidetests/appsecurity/test-apps/ReadSettingsFieldsApp"),
            ("cts", "hostsidetests/appsecurity/test-apps/RoleSecurityTestApp"),
            ("cts", "hostsidetests/appsecurity/test-apps/SimpleAppInstall"),
            ("cts", "hostsidetests/appsecurity/test-apps/SimpleAppInstallDiffCert"),
            ("cts", "hostsidetests/appsecurity/test-apps/StatsdSecurityApp"),
            ("cts", "hostsidetests/appsecurity/test-apps/TargetInstrumentationApp"),
            ("cts", "hostsidetests/appsecurity/test-apps/UsePermissionDiffCert"),
            ("cts", "hostsidetests/appsecurity/test-apps/UseProcessFailActivity"),
            ("cts", "hostsidetests/appsecurity/test-apps/V32HybridSigningScheme"),
            ("cts", "hostsidetests/appsecurity/test-apps/V3SigningSchemeRotation"),
            ("cts", "hostsidetests/appsecurity/test-apps/keysets/malBadKey"),
            ("cts", "hostsidetests/appsecurity/test-apps/keysets/malNoDef"),
            ("cts", "hostsidetests/appsecurity/test-apps/keysets/malOneDef"),
            ("cts", "hostsidetests/appsecurity/test-apps/keysets/permDef"),
            ("cts", "hostsidetests/appsecurity/test-apps/keysets/permUse"),
            ("cts", "hostsidetests/appsecurity/test-apps/keysets/testApp"),
            ("cts", "hostsidetests/appsecurity/test-apps/keysets/uA"),
            ("cts", "hostsidetests/appsecurity/test-apps/keysets/uAuB"),
            ("cts", "hostsidetests/appsecurity/test-apps/keysets/uB"),
            ("cts", "hostsidetests/appsecurity/test-apps/keysets/uBsharedUser"),
            ("cts", "hostsidetests/appsecurity/test-apps/keysets/uEcA"),
            ("cts", "hostsidetests/appsecurity/test-apps/keysets/uNone"),
            ("cts", "hostsidetests/appsecurity/test-apps/tinyapp"),
            ("cts", "hostsidetests/statsdatom/Android.bp"),
            ("cts", "hostsidetests/statsdatom/apps/adpfapp"),
            ("cts", "hostsidetests/statsdatom/apps/expressloghelperapp"),
            ("cts", "hostsidetests/statsdatom/apps/statsdapp"),
            ("cts", "hostsidetests/statsdatom/configs/AndroidTestTelecom.xml"),
            ("cts", "hostsidetests/statsdatom/express/src"),
            ("cts", "hostsidetests/statsdatom/lib/src"),
            ("cts", "hostsidetests/statsdatom/statsd/src"),
            ("cts", "hostsidetests/statsdatom/telecom/src"),
            ("cts", "hostsidetests/utils"),
            ("cts", "tests/tests/telecom"),
            ("cts", "tests/tests/telecom-apps/ConnectionServiceVoipAppClone"),
            ("cts", "tests/tests/telecom-apps/ConnectionServiceVoipAppMain"),
            ("cts", "tests/tests/telecom-apps/ManagedConnectionService"),
            ("cts", "tests/tests/telecom-apps/ManagedConnectionServiceClone"),
            ("cts", "tests/tests/telecom-apps/TransactionalVoipAppClone"),
            ("cts", "tests/tests/telecom-apps/TransactionalVoipAppMain"),
            ("cts", "tests/tests/telecom-apps/Utils"),
            ("cts", "tests/tests/telecom-cuj"),
            ("external/bouncycastle", "bcpkix/src/main/java"),
            ("external/bouncycastle", "bcprov/src/main/java"),
            ("external/bouncycastle", "repackaged_platform/bcpkix/src/main/java"),
            ("external/bouncycastle", "repackaged_platform/bcprov/src/main/java"),
            ("external/caliper", "caliper"),
            ("external/caliper", "examples"),
            ("external/caliper", "lib"),
            ("external/compiler-rt", "lib/builtins/comparedf2.c"),
            ("external/compiler-rt", "lib/builtins/mulodi4.c"),
            ("external/cronet", "android/java/src/android/net/http/BidirectionalStream.java"),
            ("external/cronet", "android/java/src/android/net/http/BidirectionalStreamBuilderWrapper.java"),
            ("external/cronet", "android/java/src/android/net/http/BidirectionalStreamCallbackWrapper.java"),
            ("external/cronet", "android/java/src/android/net/http/BidirectionalStreamWrapper.java"),
            ("external/cronet", "android/java/src/android/net/http/CallbackException.java"),
            ("external/cronet", "android/java/src/android/net/http/CallbackExceptionWrapper.java"),
            ("external/cronet", "android/java/src/android/net/http/ConnectionMigrationOptions.java"),
            ("external/cronet", "android/java/src/android/net/http/CronetEngineWrapper.java"),
            ("external/cronet", "android/java/src/android/net/http/CronetExceptionTranslationUtils.java"),
            ("external/cronet", "android/java/src/android/net/http/CronetExceptionWrapper.java"),
            ("external/cronet", "android/java/src/android/net/http/DnsOptions.java"),
            ("external/cronet", "android/java/src/android/net/http/HeaderBlock.java"),
            ("external/cronet", "android/java/src/android/net/http/HeaderBlockImpl.java"),
            ("external/cronet", "android/java/src/android/net/http/HeaderBlockWrapper.java"),
            ("external/cronet", "android/java/src/android/net/http/HttpEngine.java"),
            ("external/cronet", "android/java/src/android/net/http/HttpEngineJavaClasses.java"),
            ("external/cronet", "android/java/src/android/net/http/HttpException.java"),
            ("external/cronet", "android/java/src/android/net/http/InlineExecutionProhibitedException.java"),
            ("external/cronet", "android/java/src/android/net/http/NetworkException.java"),
            ("external/cronet", "android/java/src/android/net/http/NetworkExceptionWrapper.java"),
            ("external/cronet", "android/java/src/android/net/http/Proxy.java"),
            ("external/cronet", "android/java/src/android/net/http/ProxyOptions.java"),
            ("external/cronet", "android/java/src/android/net/http/QuicException.java"),
            ("external/cronet", "android/java/src/android/net/http/QuicExceptionWrapper.java"),
            ("external/cronet", "android/java/src/android/net/http/QuicOptions.java"),
            ("external/cronet", "android/java/src/android/net/http/UploadDataProvider.java"),
            ("external/cronet", "android/java/src/android/net/http/UploadDataProviderWrapper.java"),
            ("external/cronet", "android/java/src/android/net/http/UploadDataSink.java"),
            ("external/cronet", "android/java/src/android/net/http/UploadDataSinkWrapper.java"),
            ("external/cronet", "android/java/src/android/net/http/UrlRequest.java"),
            ("external/cronet", "android/java/src/android/net/http/UrlRequestBuilderWrapper.java"),
            ("external/cronet", "android/java/src/android/net/http/UrlRequestCallbackWrapper.java"),
            ("external/cronet", "android/java/src/android/net/http/UrlRequestStatusListenerWrapper.java"),
            ("external/cronet", "android/java/src/android/net/http/UrlRequestWrapper.java"),
            ("external/cronet", "android/java/src/android/net/http/UrlResponseInfo.java"),
            ("external/cronet", "android/java/src/android/net/http/UrlResponseInfoWrapper.java"),
            ("external/cronet", "stable/build/Android.bp"),
            ("external/cronet", "stable/build/util/LASTCHANGE"),
            ("external/cronet", "stable/build/util/android_chrome_version.py"),
            ("external/cronet", "stable/build/util/version.py"),
            ("external/cronet", "stable/chrome/VERSION"),
            ("external/escapevelocity", "src/main"),
            ("external/libbpf", "android/bpf_stub.c"),
            ("external/mime-support", "mime.types"),
            ("external/mime-support", "mime.types-alt"),
            ("external/protobuf", "java/lite/proguard.pgcfg"),
            ("external/protobuf", "javanano/src/device/main/java/com/google/protobuf/nano"),
            ("external/protobuf", "javanano/src/main/java/com/google/protobuf/nano"),
            ("packages/modules/Bluetooth", "framework/tests/util"),
            ("packages/modules/ConfigInfrastructure", "aconfigd/proto"),
            ("packages/modules/Connectivity", "Tethering/apex/hiddenapi"),
            ("packages/modules/Connectivity", "staticlibs/device"),
            ("packages/modules/Connectivity", "staticlibs/framework"),
            ("packages/modules/NpuManager", "flags"),
            ("packages/modules/NpuManager", "framework"),
            ("packages/modules/NpuManager", "ndk"),
            ("packages/modules/Telephony", "tests/mcts/Android.bp"),
            ("packages/modules/Telephony", "tests/mcts/AndroidTest.xml"),
            ("packages/modules/Telephony", "tests/mcts/telecom-cuj"),
            ("packages/modules/Wifi", "framework/aidl-export"),
            ("packages/modules/Wifi", "framework/java"),
            ("platform_testing", "libraries/sts-common-util/host-side/Android.bp"),
            ("platform_testing", "libraries/sts-common-util/host-side/res"),
            ("platform_testing", "libraries/sts-common-util/host-side/src"),
            ("platform_testing", "libraries/sts-common-util/util/Android.bp"),
            ("platform_testing", "libraries/sts-common-util/util/src"),
            ("prebuilts/sdk", "tools/darwin/bin/aapt2"),
            ("prebuilts/sdk", "tools/linux/bin/aapt2"),
            ("prebuilts/sdk", "tools/windows/bin/aapt2.exe"),
            ("system/gsid", "aidl/android/gsi/AvbPublicKey.aidl"),
            ("system/gsid", "aidl/android/gsi/GsiProgress.aidl"),
            ("system/gsid", "aidl/android/gsi/IGsiService.aidl"),
            ("system/gsid", "aidl/android/gsi/IGsiServiceCallback.aidl"),
            ("system/gsid", "aidl/android/gsi/IImageService.aidl"),
            ("system/gsid", "aidl/android/gsi/IProgressCallback.aidl"),
            ("system/gsid", "aidl/android/gsi/MappedImage.aidl"),
            ("system/liburingutils", "include"),
            ("system/liburingutils", "src"),
            ("system/logging", "logd/Android.bp"),
            ("system/logging", "logd/CommandListener.cpp"),
            ("system/logging", "logd/CompressionEngine.cpp"),
            ("system/logging", "logd/LogAudit.cpp"),
            ("system/logging", "logd/LogBufferElement.cpp"),
            ("system/logging", "logd/LogBufferTest.cpp"),
            ("system/logging", "logd/LogKlog.cpp"),
            ("system/logging", "logd/LogListener.cpp"),
            ("system/logging", "logd/LogPermissions.cpp"),
            ("system/logging", "logd/LogReader.cpp"),
            ("system/logging", "logd/LogReaderList.cpp"),
            ("system/logging", "logd/LogReaderThread.cpp"),
            ("system/logging", "logd/LogSize.cpp"),
            ("system/logging", "logd/LogStatistics.cpp"),
            ("system/logging", "logd/LogTags.cpp"),
            ("system/logging", "logd/LogdLock.cpp"),
            ("system/logging", "logd/LogdNativeService.cpp"),
            ("system/logging", "logd/PkgIds.cpp"),
            ("system/logging", "logd/PruneList.cpp"),
            ("system/logging", "logd/ReplayMessages.cpp"),
            ("system/logging", "logd/SerializedFlushToState.cpp"),
            ("system/logging", "logd/SerializedFlushToStateTest.cpp"),
            ("system/logging", "logd/SerializedLogBuffer.cpp"),
            ("system/logging", "logd/SerializedLogBufferTest.cpp"),
            ("system/logging", "logd/SerializedLogChunk.cpp"),
            ("system/logging", "logd/SerializedLogChunkTest.cpp"),
            ("system/logging", "logd/SimpleLogBuffer.cpp"),
            ("system/logging", "logd/TrustyLog.cpp"),
            ("system/logging", "logd/auditctl.cpp"),
            ("system/logging", "logd/binder"),
            ("system/logging", "logd/device_test_config.xml"),
            ("system/logging", "logd/flags"),
            ("system/logging", "logd/libaudit"),
            ("system/logging", "logd/logd_test.cpp"),
            ("system/logging", "logd/logtagd.rc"),
            ("system/logging", "logd/main.cpp"),
            ("system/update_engine", "binder_bindings/android/os/IUpdateEngine.aidl"),
            ("system/update_engine", "binder_bindings/android/os/IUpdateEngineCallback.aidl"),
            ("system/update_engine", "stable"),
            ("system/vold", "binder/android/os/IVold.aidl"),
            ("system/vold", "binder/android/os/IVoldListener.aidl"),
            ("system/vold", "binder/android/os/IVoldMountCallback.aidl"),
            ("system/vold", "binder/android/os/IVoldTaskListener.aidl"),
        ] {
            let mut missing = lock.clone();
            let project = missing.projects.iter_mut().find(|p| p.path == Path::new(relative)).unwrap();
            project.sparse_paths.retain(|cone| !Path::new(required).starts_with(cone));
            assert!(!project.sparse_paths.is_empty(), "test must not turn a sparse project into a full checkout");
            assert!(validate_audio_provider_source_paths(&missing, audio).is_err(), "{relative}/{required}");
        }
        for relative in ["external/caliper", "external/mime-support", "packages/modules/NpuManager", "system/liburingutils"] {
            let mut missing = lock.clone();
            missing.projects.retain(|p| p.path != Path::new(relative));
            assert!(validate_audio_provider_source_paths(&missing, audio).is_err());
            for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                         SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
                validate_audio_provider_source_paths(&missing, mode).unwrap();
            }
            let mut wrong = lock.clone();
            wrong.projects.iter_mut().find(|p| p.path == Path::new(relative)).unwrap()
                .commit = "0000000000000000000000000000000000000000".into();
            assert!(validate_audio_provider_source_paths(&wrong, audio).is_err());
        }
    }


    fn audio_connectivity_fixture_source(root: &Path) -> PathBuf {
        let source = root.join("source");
        for (relative, bytes) in [
            ("service/Android.bp", include_bytes!("../tests/fixtures/audio-providers/allgraph-connectivity-service.bp").as_slice()),
            ("bpf/loader/Android.bp", include_bytes!("../tests/fixtures/audio-providers/connectivity-bpf-loader-original.bp").as_slice()),
            ("bpf/loader/NetBpfLoad.cpp", include_bytes!("../tests/fixtures/audio-providers/connectivity-netbpfload-original.cpp").as_slice()),
            ("service/jni/com_android_server_connectivity_ClatCoordinator.cpp", include_bytes!("../tests/fixtures/audio-providers/connectivity-clatcoordinator-original.cpp").as_slice()),
            ("service/jni/com_android_server_connectivity_LocalNetEventListener.cpp", include_bytes!("../tests/fixtures/audio-providers/connectivity-localnetevent-original.cpp").as_slice()),
            ("bpf/headers/include/bpf/BpfUtils.h", include_bytes!("../tests/fixtures/audio-providers/connectivity-bpfutils-original.h").as_slice()),
            ("staticlibs/native/bpfmapjni/com_android_net_module_util_Bpf.cpp", include_bytes!("../tests/fixtures/audio-providers/connectivity-bpfjni-original.cpp").as_slice()),
        ] {
            write(&source.join("packages/modules/Connectivity").join(relative), bytes).unwrap();
        }
        source
    }

    fn audio_connectivity_apply_original_patches(p: &mut Projection, repo: &Path, source: &Path) {
        let selected: Vec<_> = PATCHES.iter().copied().filter(|(_, name)|
            AUDIO_CONNECTIVITY_PATCHES.iter().any(|(expected, _)| name == expected)).collect();
        assert_eq!(selected.len(), 2);
        for ((cwd, name), (expected, digest)) in selected.into_iter().zip(AUDIO_CONNECTIVITY_PATCHES.iter().copied()) {
            assert_eq!(cwd, "packages/modules/Connectivity");
            assert_eq!(name, expected);
            assert_eq!(hash(&repo.join(name)).unwrap(), digest);
            p.patch(source, cwd, &repo.join(name)).unwrap();
        }
    }

    #[test]
    fn audio_connectivity_normal_patch_chain_preserves_providers_and_recovers() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let mode = SoongDependencyMode::AudioApexTargetClosure;
        for interrupted in [false, true] {
            let temp = tempfile::tempdir().unwrap();
            let source = audio_connectivity_fixture_source(temp.path());
            let provider = source.join(AUDIO_CONNECTIVITY_BP);
            let original = fs::read(&provider).unwrap();
            let before_time = fs::metadata(&provider).unwrap().modified().unwrap();
            let unselected = source.join("packages/modules/Connectivity/tests/unselected.bp");
            write(&unselected, b"unchanged sibling\n").unwrap();
            assert!(audio_original_graph_provider(AUDIO_CONNECTIVITY_BP,
                std::str::from_utf8(&original).unwrap(), mode).unwrap().is_some());
            let journal = temp.path().join("projection.json");
            let mut p = Projection::new(journal.clone()).unwrap();
            audio_connectivity_apply_original_patches(&mut p, &repo, &source);
            let projected = fs::read_to_string(&provider).unwrap();
            // This reproduces the actual r8 failure after the genuine patches.
            assert!(audio_original_graph_provider(AUDIO_CONNECTIVITY_BP, &projected, mode).is_err());
            assert_eq!(audio_connectivity_provider_after_patch(
                &p, &repo, &source, &projected, mode).unwrap().unwrap(), projected);
            for name in ["service-connectivity-jarjar-gen", "service-nearby-jarjar-gen",
                         "service-remoteauth-jarjar-gen", "service-thread-jarjar-gen",
                         "service-networksecurity-jarjar-gen", "libservice-connectivity"] {
                assert!(projected.contains(&format!("name: \"{name}\"")));
            }
            let expected: Vec<_> = p.originals.iter().map(|o|
                (o.path.clone(), o.bytes.clone().unwrap(), o.modified)).collect();
            assert_eq!(expected.len(), 7);
            let inventory = p.effective_inventory(&repo, &source).unwrap();
            assert_eq!(inventory["files"][AUDIO_CONNECTIVITY_BP],
                "e5b482317718cea8ce2a8dbe5c339daaf7837e92b1fa58c735dd4f3f48c58c44");
            assert_eq!(inventory["patches"].as_object().unwrap().len(), 2);
            if interrupted {
                std::mem::forget(p);
                recover(&journal, &source).unwrap();
            } else {
                p.restore().unwrap();
            }
            for (path, bytes, modified) in expected {
                assert_eq!(fs::read(&path).unwrap(), bytes);
                assert_eq!(fs::metadata(&path).unwrap().modified().ok(), modified);
            }
            assert_eq!(fs::read(&provider).unwrap(), original);
            assert_eq!(fs::metadata(&provider).unwrap().modified().unwrap(), before_time);
            assert_eq!(fs::read(&unselected).unwrap(), b"unchanged sibling\n");
            assert!(!journal.exists());
        }
    }

    #[test]
    fn audio_connectivity_projection_guard_rejects_unbound_or_changed_inputs() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let temp = tempfile::tempdir().unwrap();
        let source = audio_connectivity_fixture_source(temp.path());
        let mode = SoongDependencyMode::AudioApexTargetClosure;
        let mut p = Projection::new(temp.path().join("projection.json")).unwrap();
        audio_connectivity_apply_original_patches(&mut p, &repo, &source);
        let current = fs::read_to_string(source.join(AUDIO_CONNECTIVITY_BP)).unwrap();
        assert!(audio_connectivity_provider_after_patch(&p, &repo, &source,
            &(current.clone() + "\n"), mode).is_err());
        let index = p.originals.iter().position(|o| o.path == source.join(AUDIO_CONNECTIVITY_BP)).unwrap();
        let saved = p.originals[index].bytes.clone();
        p.originals[index].bytes.as_mut().unwrap().push(b'\n');
        assert!(audio_connectivity_provider_after_patch(&p, &repo, &source, &current, mode).is_err());
        p.originals[index].bytes = None;
        assert!(audio_connectivity_provider_after_patch(&p, &repo, &source, &current, mode).is_err());
        p.originals[index].bytes = saved;
        for (name, _) in AUDIO_CONNECTIVITY_PATCHES {
            let path = repo.join(name);
            let digest = p.applied_patches.remove(&path).unwrap();
            assert!(audio_connectivity_provider_after_patch(&p, &repo, &source, &current, mode).is_err());
            p.applied_patches.insert(path.clone(), "0".repeat(64));
            assert!(audio_connectivity_provider_after_patch(&p, &repo, &source, &current, mode).is_err());
            p.applied_patches.insert(path, digest);
        }
        assert!(audio_connectivity_provider_after_patch(&p, &repo, &source, &current, mode).is_ok());
        p.restore().unwrap();
    }

    #[test]
    fn audio_connectivity_projection_guard_rejects_unapplied_and_partial_chain() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let mode = SoongDependencyMode::AudioApexTargetClosure;
        for selected in [None, Some(0usize), Some(1usize)] {
            let temp = tempfile::tempdir().unwrap();
            let source = audio_connectivity_fixture_source(temp.path());
            let mut p = Projection::new(temp.path().join("projection.json")).unwrap();
            if let Some(index) = selected {
                p.patch(&source, "packages/modules/Connectivity",
                    &repo.join(AUDIO_CONNECTIVITY_PATCHES[index].0)).unwrap();
            }
            let current = fs::read_to_string(source.join(AUDIO_CONNECTIVITY_BP)).unwrap();
            assert!(audio_connectivity_provider_after_patch(&p, &repo, &source, &current, mode).is_err());
            p.restore().unwrap();
            assert!(audio_original_graph_provider(AUDIO_CONNECTIVITY_BP,
                &fs::read_to_string(source.join(AUDIO_CONNECTIVITY_BP)).unwrap(), mode).is_ok());
        }
    }

    #[test]
    fn audio_connectivity_projection_guard_keeps_other_modes_unchanged() {
        let temp = tempfile::tempdir().unwrap();
        let p = Projection::new(temp.path().join("projection.json")).unwrap();
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::MinigbmTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::NativeBridgeTargetClosure] {
            assert!(audio_connectivity_provider_after_patch(&p, temp.path(), temp.path(),
                "other mode does not adopt this Audio qualification", mode).unwrap().is_none());
        }
        assert!(audio_apex_only_build(&["com.android.hardware.audio.droidloom"]));
        assert!(!audio_apex_only_build(&["com.android.hardware.audio.droidloom", "services"]));
    }

    #[test]
    fn audio_allgraph_preserves_exact_original_provider_bytes_and_scopes() {
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        for (relative, original) in [
            ("system/update_engine/Android.bp", include_str!("../tests/fixtures/audio-providers/allgraph-update-engine.bp")),
            ("packages/modules/Connectivity/service/Android.bp", include_str!("../tests/fixtures/audio-providers/allgraph-connectivity-service.bp")),
            ("frameworks/base/libs/hwui/Android.bp", include_str!("../tests/fixtures/audio-providers/allgraph-graphics-sdk.bp")),
            ("packages/modules/ConfigInfrastructure/aconfigd/Android.bp", include_str!("../tests/fixtures/audio-providers/allgraph-aconfigd-rust.bp")),
            ("prebuilts/sdk/current/androidx/JavaPlugins.bp", include_str!("../tests/fixtures/audio-providers/allgraph-androidx-plugins.bp")),
        ] {
            assert_eq!(audio_original_graph_provider(relative, original, audio).unwrap().unwrap(), original);
            assert!(audio_original_graph_provider(relative, &(original.to_owned() + "\n"), audio).is_err());
            for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                         SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
                assert!(audio_original_graph_provider(relative, original, mode).unwrap().is_none());
            }
        }
    }

    #[test]
    fn audio_allgraph_reproduces_old_provider_removal() {
        let update = include_str!("../tests/fixtures/audio-providers/allgraph-update-engine.bp");
        let old = private_nativebridge_update_engine_headers_only(update).unwrap();
        for name in ["update_metadata-protos", "libupdate_engine_aidl", "delta_generator"] {
            assert!(!old.contains(&format!("name: \"{name}\"")));
            assert!(update.contains(&format!("name: \"{name}\"")));
        }
        let rust = include_str!("../tests/fixtures/audio-providers/allgraph-aconfigd-rust.bp");
        assert!(!metadata_only(rust).unwrap().contains("libaconfigd_rust"));
        let graphics = include_str!("../tests/fixtures/audio-providers/allgraph-graphics-sdk.bp");
        assert!(!private_without_named_java_module(graphics, "java_sdk_library", "framework-graphics")
            .unwrap().contains("name: \"framework-graphics\""));
        let connectivity = include_str!("../tests/fixtures/audio-providers/allgraph-connectivity-service.bp");
        for name in ["service-connectivity-jarjar-gen", "service-nearby-jarjar-gen",
                     "service-networksecurity-jarjar-gen", "service-remoteauth-jarjar-gen", "service-thread-jarjar-gen"] {
            assert!(!private_without_named_java_module(connectivity, "java_genrule", name)
                .unwrap().contains(&format!("name: \"{name}\"")));
        }
    }

    #[test]
    fn audio_cts_sts_keeps_original_provider_and_sibling_modules() {
        use sha2::{Digest, Sha256};
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        for (relative, original, expected, module) in [
            ("cts/hostsidetests/appcompat/host/lib/Android.bp", include_str!("../tests/fixtures/audio-providers/cts-sts-appcompat.bp"),
             "4df3e911da926b7b631a266df50d3509e89f6760a91dbf88ae50982c05a0e9b1", "CompatChangeGatingTestBase"),
            ("cts/hostsidetests/appsecurity/test-apps/PackageInstallerPermissionRequestApp/Android.bp", include_str!("../tests/fixtures/audio-providers/cts-sts-package-installer.bp"),
             "74013068c04801d46e844e8de1750243b2f118f2a91569a842b389748b38b8a0", "CtsPkgInstallerConstants"),
            ("cts/hostsidetests/utils/Android.bp", include_str!("../tests/fixtures/audio-providers/cts-sts-host-utils.bp"),
             "9190769e983df09706e7e2af7d5cd437b1d03bf19e294d214d90454c28c8a36f", "cts-host-utils"),
            ("cts/hostsidetests/statsdatom/Android.bp", include_str!("../tests/fixtures/audio-providers/cts-sts-statsdatom.bp"),
             "d89ae82c69508bdae1d54e8a7b22008403d50c0ce80b65b60ac4d1fe5f79828f", "cts-statsd-atom-host-test-utils"),
            ("platform_testing/libraries/sts-common-util/host-side/Android.bp", include_str!("../tests/fixtures/audio-providers/cts-sts-host-side.bp"),
             "e39cdc7bd48cd5e969b3c2a244299ba92ce8ee8699863bff40f77f2cfa989276", "sts-host-util"),
            ("packages/modules/NpuManager/framework/Android.bp", include_str!("../tests/fixtures/audio-providers/cts-sts-npumanager.bp"),
             "199f86c7e2f5b7ccb49f4903e9adbd45039ac4966234e6184fecb0b7620fc081", "framework-npumanager-aidl"),
            ("external/caliper/Android.bp", include_str!("../tests/fixtures/audio-providers/cts-sts-caliper.bp"),
             "3840744aea249f527f097ed1b795cb7ed07b92e907719548de722d617d1e9db2", "caliper-prebuilts"),
            ("external/mime-support/Android.bp", include_str!("../tests/fixtures/audio-providers/cts-sts-mime.bp"),
             "f4d6975d744ddaacf84dba49d31515a2464b49c0a8f008698d0d0e060769f458", "debian.mime.types.minimized"),
            ("system/liburingutils/Android.bp", include_str!("../tests/fixtures/audio-providers/cts-sts-liburingutils.bp"),
             "af40346c200ec0e1cacb28aff74975cfea44f57921334926f1e630a2f77605e4", "liburingutils"),
            ("packages/modules/common/sdk/Android.bp", include_str!("../tests/fixtures/audio-providers/cts-sts-sdk-defaults.bp"),
             "f68716de589c8ab13e4aa46b00416144728ed61d488450659cb97265eae88e17", "framework-module-defaults"),
        ] {
            assert_eq!(format!("{:x}", Sha256::digest(original.as_bytes())), expected);
            assert!(original.contains(&format!("name: \"{module}\"")));
            assert!(audio_original_shared_provider(relative, original, audio).unwrap().is_none());
            assert!(audio_new_source_root_scope(relative, original, audio).unwrap().is_none());
        }
    }

    #[test]
    fn audio_npumanager_sdk_uses_exact_original_three_scopes() {
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        for scope in ["public", "system", "module-lib"] {
            assert!(!project_fallback_sdk_import_for_mode("framework-npumanager", scope, audio));
            for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                         SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
                assert!(project_fallback_sdk_import_for_mode("framework-npumanager", scope, mode));
            }
        }
        assert!(project_fallback_sdk_import_for_mode("framework-npumanager", "system-server", audio));
        assert!(project_fallback_sdk_import_for_mode("framework-media", "module-lib", audio));
        let d = tempfile::tempdir().unwrap();
        let provider = d.path().join("packages/modules/NpuManager/framework/Android.bp");
        let defaults = d.path().join("packages/modules/common/sdk/Android.bp");
        write(&provider, include_bytes!("../tests/fixtures/audio-providers/cts-sts-npumanager.bp")).unwrap();
        write(&defaults, include_bytes!("../tests/fixtures/audio-providers/cts-sts-sdk-defaults.bp")).unwrap();
        validate_audio_npumanager_sdk_provider(d.path(), audio).unwrap();
        write(&provider, b"different provider").unwrap();
        assert!(validate_audio_npumanager_sdk_provider(d.path(), audio).is_err());
        write(&provider, include_bytes!("../tests/fixtures/audio-providers/cts-sts-npumanager.bp")).unwrap();
        write(&defaults, b"different scopes").unwrap();
        assert!(validate_audio_npumanager_sdk_provider(d.path(), audio).is_err());
        validate_audio_npumanager_sdk_provider(d.path(), SoongDependencyMode::Strict).unwrap();
    }

    #[test]
    fn audio_cts_compilation_requires_original_defaults_without_deleting_consumers() {
        use sha2::{Digest, Sha256};
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let lock = droidloom_source::load_lock(
            &repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        let mode = SoongDependencyMode::AudioApexTargetClosure;
        validate_audio_provider_source_paths(&lock, mode).unwrap();
        let mut old = lock.clone();
        old.projects.iter_mut().find(|p| p.path == Path::new("cts")).unwrap()
            .sparse_paths.retain(|p| p != Path::new("hostsidetests/compilation"));
        assert!(validate_audio_provider_source_paths(&old, mode).is_err());
        let mut incomplete = old;
        incomplete.projects.iter_mut().find(|p| p.path == Path::new("cts")).unwrap()
            .sparse_paths.push(PathBuf::from("hostsidetests/compilation/Android.bp"));
        assert!(validate_audio_provider_source_paths(&incomplete, mode).is_err());
        let provider = include_str!("../tests/fixtures/audio-providers/cts-compilation.bp");
        let consumer = include_str!("../tests/fixtures/audio-providers/cts-appsecurity.bp");
        assert_eq!(format!("{:x}", Sha256::digest(provider.as_bytes())),
            "e9bbc37ad6e6e4b53f64e2746aed5892848f7d25f2eb692e846f2d9bdd5595d8");
        assert_eq!(format!("{:x}", Sha256::digest(consumer.as_bytes())),
            "d15a2400b5f11d874614bd5e00f2e2628f71c1d2bf95ac6f46c7389ee6d8b916");
        for name in ["profile_defaults", "dm_defaults"] {
            assert!(provider.contains(&format!("name: \"{name}\"")));
            assert!(consumer.contains(&format!("defaults: [\"{name}\"]")));
        }
        for expected in ["tools: [\"profman\"]", "name: \"generate_dm\"",
                         "src: \"scripts/generate_dm.sh\"", "\"soong_zip\""] {
            assert!(provider.contains(expected));
        }
        for (path, original) in [("cts/hostsidetests/compilation/Android.bp", provider),
                                 ("cts/hostsidetests/appsecurity/Android.bp", consumer)] {
            assert!(audio_original_shared_provider(path, original, mode).unwrap().is_none());
            assert!(audio_new_source_root_scope(path, original, mode).unwrap().is_none());
        }
    }

    #[test]
    fn audio_api35_cts_keeps_real_consumers_and_original_provider_modules() {
        use sha2::{Digest, Sha256};
        let perfetto = include_str!("../tests/fixtures/audio-providers/perfetto-sdk35-modules.bp");
        assert_eq!(perfetto.matches("sdk_version: \"35\"").count(), 2);
        assert!(perfetto.contains("name: \"perfetto_src_java_sdk_main_perfetto_lib\""));
        let consumer = include_str!("../tests/fixtures/audio-providers/framework-stagedinstall.bp");
        assert!(consumer.contains("name: \"StagedInstallInternalTest\""));
        for dependency in ["cts-shim-host-lib", "cts-install-lib-host"] {
            assert!(consumer.contains(&format!("\"{dependency}\"")));
        }
        let install = include_str!("../tests/fixtures/audio-providers/cts-install.bp");
        for name in ["cts-install-lib", "cts-install-lib-host", "cts-install-lib-java",
                     "StagedInstallTestApexV1", "StagedInstallTestApexV2", "StagedInstallTestApexV3"] {
            assert!(install.contains(name), "{name}");
        }
        let suite = include_str!("../tests/fixtures/audio-providers/cts-tradefed.bp");
        let ats = include_str!("../tests/fixtures/audio-providers/deviceinfra-prebuilts.bp");
        for name in ["ats_console_deploy", "ats_olc_server_local_mode_deploy"] {
            assert!(suite.contains(&format!("\"{name}\"")));
            assert!(ats.contains(&format!("name: \"{name}\"")));
            assert!(ats.contains(&format!("\"{name}.jar\"")));
        }
        let runner_tests = include_str!("../tests/fixtures/audio-providers/deqp-android-cts-runner-tests-original.bp");
        for dependency in ["CtsDeqpTestCases", "easymock"] {
            assert!(runner_tests.contains(&format!("\"{dependency}\"")));
        }
        let runner = include_str!("../tests/fixtures/audio-providers/deqp-android-cts-original.bp");
        for input in ["runner/src/**/*.java", "llvm-strip-tools", "com.drawelements.deqp", "deqp-binary"] {
            assert!(runner.contains(input), "{input}");
        }
        let deqp = include_str!("../tests/fixtures/audio-providers/deqp-original.bp");
        for provider in ["deqp_amber", "deqp_spirv-tools", "deqp_glslang_glslang",
                         "external/deqp-deps/SPIRV-Headers/include"] {
            assert!(deqp.contains(provider), "{provider}");
        }
        let easymock = include_str!("../tests/fixtures/audio-providers/easymock-original.bp");
        assert!(easymock.contains("name: \"easymock\""));
        assert_eq!(easymock.matches("sdk_version: \"9\"").count(), 2);
        // Keep complete upstream BPs, including sibling test modules and resources.
        for (relative, original, expected) in [
            ("external/deqp/android/cts/runner/tests/Android.bp", include_str!("../tests/fixtures/audio-providers/deqp-android-cts-runner-tests-original.bp"), "53e34061eaf71d2da1d036c16646a4327015a7c583f4df3d6397afb7e73a568c"),
            ("external/deqp/Android.bp", include_str!("../tests/fixtures/audio-providers/deqp-original.bp"), "b30ff8e5e19b5be1482c0f3fa254d9f87d090dd602ed5652d912f29c27a60c3f"),
            ("external/deqp/android/cts/Android.bp", include_str!("../tests/fixtures/audio-providers/deqp-android-cts-original.bp"), "e3fa268b76d5859389513f650a1d23caf7e7b33e3ec7712d7a55d94821c170c9"),
            ("external/deqp-deps/SPIRV-Headers/Android.bp", include_str!("../tests/fixtures/audio-providers/deqp-deps-SPIRV-Headers-original.bp"), "0fa6b9ebeed222d0fb4f290848a89d220e8ae7eca1776ad40b2613959c1fe70b"),
            ("external/deqp-deps/SPIRV-Tools/Android.bp", include_str!("../tests/fixtures/audio-providers/deqp-deps-SPIRV-Tools-original.bp"), "58f22ee12a282cb9dbf607a24451a6d258d7ad54b3e4976e6804a36beb473f2b"),
            ("external/deqp-deps/amber/Android.bp", include_str!("../tests/fixtures/audio-providers/deqp-deps-amber-original.bp"), "5481fc9068794994db28a51d3e80368641e82df2b50ca9693031d28f525f4eab"),
            ("external/deqp-deps/glslang/Android.bp", include_str!("../tests/fixtures/audio-providers/deqp-deps-glslang-original.bp"), "40bde4a1f43c1d1a59cbdcfbf7206f3ddf5412119d1bcdf4f3be1af10195ba1b"),
            ("external/easymock/Android.bp", include_str!("../tests/fixtures/audio-providers/easymock-original.bp"), "d4f9a44c826f62d5c3a47dfea6241b030bc28aaf693352572c7eaf86aaa40fe4"),
            ("frameworks/base/tests/StagedInstallTest/Android.bp", include_str!("../tests/fixtures/audio-providers/framework-stagedinstall.bp"), "50226d00f53449f2a4e9aefc381442d8abfba778793028e61bdc6a0c412fd9b3"),
            ("cts/libs/shim/Android.bp", include_str!("../tests/fixtures/audio-providers/cts-shim.bp"), "c9ccd47197e6bdf106c24efd80ab3f4278ad2572ee170ec8480e30cde5864afd"),
            ("cts/libs/install/Android.bp", include_str!("../tests/fixtures/audio-providers/cts-install.bp"), "d45d89054e58c9f915f047038f7be99fe68f47fe9321a0e7ae60bbc8407ec2cf"),
            ("cts/hostsidetests/stagedinstall/Android.bp", include_str!("../tests/fixtures/audio-providers/cts-stagedinstall.bp"), "d6472b9904aa6ff5ca7a4b054b8762f4fd90adc5d202d5999767a39a41a7d348"),
            ("cts/hostsidetests/appsecurity/test-apps/PrivilegedUpdateApp/Android.bp", include_str!("../tests/fixtures/audio-providers/cts-privileged-update.bp"), "3eb2869132b8043971bdfdf2b6da5aa41a776f3ae8f0015644873b69d2b17612"),
            ("cts/tools/cts-tradefed/Android.bp", include_str!("../tests/fixtures/audio-providers/cts-tradefed.bp"), "78456ae08c26a0dbba7a859dc7860c57332ab198009dbccbb86f3793c392ea42"),
            ("cts/libs/runner/Android.bp", include_str!("../tests/fixtures/audio-providers/cts-runner.bp"), "3dfdbba783609e6b4c19fe4d355fb3a2d1f3a44a553f8bfce1b70de94261cc16"),
            ("cts/tests/core/runner-axt/Android.bp", include_str!("../tests/fixtures/audio-providers/cts-core-runner.bp"), "df2551b27025f35c3474b7b341058d8884bfd91ee9216462aa4bb2508f322ab1"),
            ("cts/libs/vogar-expect/Android.bp", include_str!("../tests/fixtures/audio-providers/cts-vogar-expect.bp"), "60317351f2eeac4aa1010b52f9c6d9c60bb38a25655d8bccd9505c9bd9cda86b"),
            ("tools/deviceinfra/prebuilts/Android.bp", include_str!("../tests/fixtures/audio-providers/deviceinfra-prebuilts.bp"), "5c1d4fcbdf68b1e01affd6012db6dcf2f3835a10e3d1d51ab5f05d8b21450d82"),
            ("external/e2fsprogs/debugfs/Android.bp", include_str!("../tests/fixtures/audio-providers/e2fsprogs-debugfs.bp"), "9c53b1b7be61444930c241815554df9b0dc4f85cf1ed13e1f73e52a034e6e78d"),
        ] {
            assert_eq!(format!("{:x}", Sha256::digest(original.as_bytes())), expected);
            assert!(audio_original_shared_provider(relative, original,
                SoongDependencyMode::AudioApexTargetClosure).unwrap().is_none(), "{relative}");
            assert!(audio_new_source_root_scope(relative, original,
                SoongDependencyMode::AudioApexTargetClosure).unwrap().is_none(), "{relative}");
        }
    }

    #[test]
    fn audio_api35_cts_rejects_the_observed_missing_original_inputs() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let lock = droidloom_source::load_lock(
            &repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        validate_audio_provider_source_paths(&lock, audio).unwrap();
        for (relative, required) in [
            ("external/deqp", "android/cts/main"),
            ("external/deqp", "android/openglcts/AndroidManifest.xml"),
            ("external/deqp", "android/openglcts/src"),
            ("external/deqp", "android/package"),
            ("external/deqp", "data"),
            ("external/deqp", "execserver"),
            ("external/deqp", "executor"),
            ("external/deqp", "external"),
            ("external/deqp", "framework"),
            ("external/deqp", "modules"),
            ("external/deqp", "android/cts/runner"),
            ("external/deqp", "android/cts/angle"),
            ("external/deqp-deps/SPIRV-Headers", "include"),
            ("external/deqp-deps/SPIRV-Tools", "include"),
            ("external/deqp-deps/SPIRV-Tools", "source"),
            ("external/deqp-deps/SPIRV-Tools", "test"),
            ("external/deqp-deps/SPIRV-Tools", "tools"),
            ("external/deqp-deps/SPIRV-Tools", "utils"),
            ("external/deqp-deps/amber", "android_sample"),
            ("external/deqp-deps/amber", "include"),
            ("external/deqp-deps/amber", "samples/config_helper.h"),
            ("external/deqp-deps/amber", "samples/config_helper_dawn.h"),
            ("external/deqp-deps/amber", "samples/config_helper_vulkan.h"),
            ("external/deqp-deps/amber", "samples/log.h"),
            ("external/deqp-deps/amber", "samples/png.h"),
            ("external/deqp-deps/amber", "samples/ppm.h"),
            ("external/deqp-deps/amber", "samples/timestamp.h"),
            ("external/deqp-deps/amber", "src"),
            ("external/deqp-deps/amber", "tools"),
            ("external/deqp-deps/glslang", "SPIRV"),
            ("external/deqp-deps/glslang", "StandAlone"),
            ("external/deqp-deps/glslang", "Test"),
            ("external/deqp-deps/glslang", "glslang"),
            ("external/deqp-deps/glslang", "gtests"),
            ("external/easymock", "src"),
            ("prebuilts/sdk", "9/public"),
            ("prebuilts/clang/host/linux-x86", "clang-r584948b"),
            ("prebuilts/sdk", "35/public/android.jar"),
            ("prebuilts/sdk", "35/public/framework.aidl"),
            ("prebuilts/sdk", "35/public/core-for-system-modules.jar"),
            ("cts", "libs/shim"),
            ("cts", "libs/install"),
            ("cts", "hostsidetests/stagedinstall"),
            ("cts", "hostsidetests/appsecurity/test-apps/PrivilegedUpdateApp"),
            ("cts", "tools/cts-tradefed"),
            ("cts", "libs/runner"),
            ("cts", "tests/core/runner-axt"),
            ("cts", "libs/vogar-expect"),
            ("external/e2fsprogs", "debugfs"),
            ("external/e2fsprogs", "lib"),
            ("external/e2fsprogs", "misc"),
            ("external/e2fsprogs", "e2fsck"),
            ("platform_testing", "scripts"),
            ("tools/deviceinfra/prebuilts", "Android.bp"),
            ("tools/deviceinfra/prebuilts", "ats_console_deploy.jar"),
            ("tools/deviceinfra/prebuilts", "ats_olc_server_local_mode_deploy.jar"),
            ("tools/deviceinfra/prebuilts", "ats_olc_server_deploy.jar"),
        ] {
            let mut missing = lock.clone();
            let provider = missing.projects.iter_mut()
                .find(|p| p.path == Path::new(relative)).unwrap();
            provider.sparse_paths.retain(|p| p != Path::new(required));
            // An empty sparse list means a complete checkout, so model a missing cone explicitly.
            if provider.sparse_paths.is_empty() {
                provider.sparse_paths.push(std::path::PathBuf::from("Android.bp"));
            }
            assert!(validate_audio_provider_source_paths(&missing, audio).is_err(),
                "{relative}/{required}");
            for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                         SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
                validate_audio_provider_source_paths(&missing, mode).unwrap();
            }
        }
        for relative in ["prebuilts/sdk", "cts", "external/e2fsprogs",
                         "platform_testing", "tools/deviceinfra/prebuilts", "prebuilts/clang/host/linux-x86",
                         "external/deqp", "external/deqp-deps/SPIRV-Headers", "external/deqp-deps/SPIRV-Tools", "external/deqp-deps/amber", "external/deqp-deps/glslang", "external/easymock"] {
            let mut substituted = lock.clone();
            substituted.projects.iter_mut().find(|p| p.path == Path::new(relative))
                .unwrap().commit = "0000000000000000000000000000000000000000".into();
            assert!(validate_audio_provider_source_paths(&substituted, audio).is_err());
        }
    }

    #[test]
    fn audio_junit_provider_keeps_the_real_icu_consumer_and_all_original_dependencies() {
        use sha2::{Digest, Sha256};
        let consumer = include_str!("../tests/fixtures/audio-providers/icu4j.bp");
        let provider = include_str!("../tests/fixtures/audio-providers/junit-params.bp");
        for (text, expected) in [
            (consumer, "e5a8137f19dbb133bdfa451c42493dbb481b1745a390817876b4636028a6014b"),
            (provider, "85348fe51555dfca2a488dcefa8911acd4e8773ac312bc51cd7407156f9597e8"),
        ] {
            assert_eq!(format!("{:x}", Sha256::digest(text.as_bytes())), expected);
        }
        assert!(consumer.contains("name: \"icu4j-tests\""));
        assert!(consumer.contains("\"junit-params\""));
        for dependency in ["gson", "icu4j", "icu4j-testdata"] {
            assert!(consumer.contains(&format!("\"{dependency}\"")));
        }
        for name in ["junit-params", "junit-params-host", "junit-params-test", "junit-params-assertj-core"] {
            assert!(provider.contains(&format!("name: \"{name}\"")));
        }
        for input in ["src/main/java/**/*.java", "src/test/java/**/*.java",
                      "src/test/resources", "lib/assertj-core-1.7.1.jar", "LICENSE.txt"] {
            assert!(provider.contains(input));
        }
        assert!(provider.contains("static_libs: [\"junit\"]"));
        for (relative, original) in [
            ("external/icu/icu4j/Android.bp", consumer),
            ("external/junit-params/Android.bp", provider),
        ] {
            assert!(audio_original_shared_provider(relative, original,
                SoongDependencyMode::AudioApexTargetClosure).unwrap().is_none());
            assert!(audio_new_source_root_scope(relative, original,
                SoongDependencyMode::AudioApexTargetClosure).unwrap().is_none());
        }
    }

    #[test]
    fn audio_junit_provider_requires_complete_original_sources_and_prebuilt_jar() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let lock = droidloom_source::load_lock(
            &repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        validate_audio_provider_source_paths(&lock, audio).unwrap();
        let mut old = lock.clone();
        old.projects.retain(|project| project.path != Path::new("external/junit-params"));
        assert_eq!(old.projects.len() + 1, lock.projects.len());
        assert!(validate_audio_provider_source_paths(&old, audio).is_err());
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            validate_audio_provider_source_paths(&old, mode).unwrap();
        }
        for missing in ["lib", "src"] {
            let mut incomplete = lock.clone();
            let provider = incomplete.projects.iter_mut()
                .find(|project| project.path == Path::new("external/junit-params")).unwrap();
            provider.sparse_paths.retain(|path| path != Path::new(missing));
            if missing == "src" {
                // Keeping only production Java hides source still required by the original sibling test.
                provider.sparse_paths.push(PathBuf::from("src/main/java"));
            }
            assert!(validate_audio_provider_source_paths(&incomplete, audio).is_err());
        }
        let mut substituted = lock;
        substituted.projects.iter_mut().find(|project| project.path == Path::new("external/junit-params"))
            .unwrap().commit = "0000000000000000000000000000000000000000".into();
        assert!(validate_audio_provider_source_paths(&substituted, audio).is_err());
    }


    #[test]
    fn audio_rkpd_sdk_requires_the_complete_original_apex_provider() {
        use sha2::{Digest, Sha256};
        let original = include_str!("../tests/fixtures/audio-providers/rkpd-apex-original.bp");
        assert_eq!(format!("{:x}", Sha256::digest(original.as_bytes())),
            "684c033d9ee70db48c8b2a7d0ee11eb156aa56abca0c0826271d9176696784b1");
        for definition in ["name: \"com.android.rkpd\"", "name: \"com.android.rkpd.key\"",
                           "name: \"com.android.rkpd.certificate\"",
                           "\"com.android.rkpd-systemserverclasspath-fragment\"",
                           "apps: [\"rkpdapp\"]", "file_contexts: \":com.android.rkpd-file_contexts\""] {
            assert!(original.contains(definition), "{definition}");
        }
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let lock = droidloom_source::load_lock(
            &repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        validate_audio_provider_source_paths(&lock, audio).unwrap();
        let project = Path::new("packages/modules/RemoteKeyProvisioning");
        let mut old = lock.clone();
        old.projects.iter_mut().find(|p| p.path == project).unwrap()
            .sparse_paths.retain(|p| p.as_path() != Path::new("apex"));
        assert!(validate_audio_provider_source_paths(&old, audio).is_err());
        let mut bp_only = old.clone();
        bp_only.projects.iter_mut().find(|p| p.path == project).unwrap()
            .sparse_paths.push(PathBuf::from("apex/Android.bp"));
        assert!(validate_audio_provider_source_paths(&bp_only, audio).is_err());
        let mut wrong_commit = lock.clone();
        wrong_commit.projects.iter_mut().find(|p| p.path == project).unwrap()
            .commit = "0000000000000000000000000000000000000000".into();
        assert!(validate_audio_provider_source_paths(&wrong_commit, audio).is_err());
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            validate_audio_provider_source_paths(&old, mode).unwrap();
        }
    }

    #[test]
    fn audio_build_source_lock_is_scoped_and_exact() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let lock = selected_source_lock(repo, SoongDependencyMode::AudioApexTargetClosure).unwrap();
        let parsed = droidloom_source::load_lock(&lock).unwrap();
        assert_eq!(parsed.projects.len(), 537);
        assert!(droidloom_source::build_plan(&parsed).is_ok());
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            assert_eq!(selected_source_lock(repo, mode).unwrap(), repo.join("android/manifest/m2-sparse-source-lock.json"));
        }
        let changed = tempfile::tempdir().unwrap();
        write(&changed.path().join("android/manifest/audio-bridge-source-lock.json"), b"{}").unwrap();
        assert!(selected_source_lock(changed.path(), SoongDependencyMode::AudioApexTargetClosure).is_err());
    }

    #[test]
    fn audio_sdk_fallback_preserves_original_scopes_and_other_modes() {
        let audio = SoongDependencyMode::AudioApexTargetClosure;
        for scope in ["public", "system", "module-lib"] {
            assert!(!project_fallback_sdk_import_for_mode("framework-sdkextensions", scope, audio));
            for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                         SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
                assert!(project_fallback_sdk_import_for_mode("framework-sdkextensions", scope, mode));
            }
        }
        assert!(project_fallback_sdk_import_for_mode("framework-sdkextensions", "system-server", audio));
        assert!(project_fallback_sdk_import_for_mode("framework-media", "module-lib", audio));
        assert!(!project_fallback_sdk_import_for_mode("framework-permission-s", "module-lib", audio));
        let d = tempfile::tempdir().unwrap();
        let path = d.path().join("prebuilts/module_sdk/SdkExtensions/current/Android.bp");
        write(&path, include_bytes!("../tests/fixtures/audio-resources/sdkextensions.bp")).unwrap();
        validate_audio_sdk_import_provider(d.path(), audio).unwrap();
        write(&path, b"missing or different provider").unwrap();
        assert!(validate_audio_sdk_import_provider(d.path(), audio).is_err());
    }

    #[test]
    fn audio_resource_projection_preserves_all_original_bytes_and_mtimes_on_restore() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let d = tempfile::tempdir().unwrap();
        let source = d.path().join("source");
        let context = source.join("build/blueprint/context.go");
        let soong = source.join("build/soong/ui/build/soong.go");
        let bootstrap = source.join("build/blueprint/bootstrap/command.go");
        let originals: [(&Path, &[u8]); 3] = [
            (&context, include_bytes!("../tests/fixtures/audio-resources/context.go")),
            (&soong, include_bytes!("../tests/fixtures/audio-resources/soong.go")),
            (&bootstrap, include_bytes!("../tests/fixtures/audio-resources/bootstrap-command.go")),
        ];
        let mtime = std::time::UNIX_EPOCH + std::time::Duration::new(1_700_000_000, 123_456_789);
        for (path, bytes) in originals {
            write(path, bytes).unwrap(); fs::File::open(path).unwrap().set_modified(mtime).unwrap();
        }
        let journal = d.path().join("source-projection.json");
        let mut p = Projection::new(journal.clone()).unwrap();
        project_audio_resources(&mut p, repo, &source, SoongDependencyMode::AudioApexTargetClosure).unwrap();
        assert_eq!(hash(&context).unwrap(), "38f6ae2fa339f04834241b20d4185bc091aa9e16cb894030927bdc58a8f67182");
        let actual = fs::read_to_string(&soong).unwrap();
        for line in ["invocationEnv[\"GOMEMLIMIT\"] = \"5GiB\"", "invocationEnv[\"GOMAXPROCS\"] = \"2\"",
                     "invocationEnv[\"GOGC\"] = \"50\"", "invocationEnv[\"GODEBUG\"] = \"gctrace=1\""] {
            assert!(actual.contains(line), "{line}");
        }
        let runtime = fs::read_to_string(&bootstrap).unwrap();
        assert!(runtime.contains("if configured := os.Getenv(\"GOMAXPROCS\"); configured == \"\""));
        assert!(runtime.contains("runtime.GOMAXPROCS(0) != requested"));
        assert!(runtime.contains("/sched/gomaxprocs:threads"));
        assert!(runtime.contains("/gc/gomemlimit:bytes"));
        assert!(runtime.contains("/gc/gogc:percent"));
        assert!(runtime.contains("defer reportGoBudget(\"leave\")"));
        assert_eq!(p.originals.len(), 3); assert_eq!(p.applied_patches.len(), 4);
        assert!(journal.exists()); p.restore().unwrap(); assert!(!journal.exists());
        for (path, bytes) in originals {
            assert_eq!(fs::read(path).unwrap(), bytes); assert_eq!(fs::metadata(path).unwrap().modified().unwrap(), mtime);
        }
    }

    #[test]
    fn audio_resource_projection_rejects_changed_inputs_and_does_not_touch_other_modes() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let d = tempfile::tempdir().unwrap(); let source = d.path().join("source");
        let journal = d.path().join("source-projection.json");
        let mut p = Projection::new(journal.clone()).unwrap();
        for mode in [SoongDependencyMode::Strict, SoongDependencyMode::NativeBridgeTargetClosure,
                     SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::MinigbmTargetClosure] {
            project_audio_resources(&mut p, repo, &source, mode).unwrap();
            assert!(p.originals.is_empty()); assert!(!journal.exists()); assert!(!source.exists());
        }
        write(&source.join("build/blueprint/context.go"), b"changed input").unwrap();
        assert!(project_audio_resources(&mut p, repo, &source, SoongDependencyMode::AudioApexTargetClosure).is_err());
        assert!(p.originals.is_empty()); assert!(!journal.exists());
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

    #[test]
    fn original_connectivity_module_sdk_stubs_are_not_shadowed() {
        for module in [
            "framework-connectivity-b",
            "framework-connectivity-t",
            "framework-tethering",
        ] {
            assert!(!project_fallback_sdk_import(module), "{module}");
        }
        assert!(project_fallback_sdk_import("framework-media"));
    }

    #[test]
    fn original_permission_sdk_stubs_are_not_shadowed() {
        assert!(!project_fallback_sdk_import("framework-permission-s"));
        assert!(project_fallback_sdk_import("framework-media"));
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
                ("", "android/aosp-patches/0017-droidloom-real-pcm-input.patch"),
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
