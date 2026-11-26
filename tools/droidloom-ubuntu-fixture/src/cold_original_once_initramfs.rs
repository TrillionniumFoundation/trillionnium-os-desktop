//! Source-bound recovery additions to the existing normal private initramfs
//! producer. A recipe describes bytes; it never grants physical boot authority.
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    cold_original_once_recovery::contract::{
        self, EARLY_CONFIG, EARLY_EXECUTABLE, EarlyConfiguration, KERNEL, KERNEL_SHA, MODULE_BYTES,
        MODULE_REL, MODULE_SHA, RecoveryBootSpec,
    },
    ensure, fs,
    model::Identity,
};
use rustix::fs::{FileType, Mode};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    fs::File,
    io::Seek,
    path::{Path, PathBuf},
};

const INPUT_SCHEMA: &str = "droidloom.original-once-initramfs-recipe.v1";
const STAGE_SCHEMA: &str = "droidloom.original-once-staged-recovery.v1";
const HOOK: &str = "/etc/initramfs-tools/hooks/droidloom-original-once-recovery";
const SCRIPT: &str = "/etc/initramfs-tools/scripts/init-top/00-droidloom-original-once-recovery";
const IMAGE_SCRIPT: &str = "/scripts/init-top/00-droidloom-original-once-recovery";
const STOCK_INIT_BYTES: u64 = 7827;
const STOCK_INIT_SHA: &str = "eca0482dafc96e4221ecc67b0c65cb3f7a86e4ed142419b90df741017221570c";
const STOCK_FUNCTIONS_BYTES: u64 = 24836;
const STOCK_FUNCTIONS_SHA: &str =
    "2e5b29a8a2ea6cc6429f2353fb2f1166b693f50c30b6a3394d1bf450c804eb88";
const STOCK_HOOKS_BYTES: u64 = 33365;
const STOCK_HOOKS_SHA: &str = "5ff086ed0cf512be3e56c2d60d02c4c0f50550940020ff9cdf156f6b313aa62b";

// manual_add_modules copies the already admitted signed module. It does not add
// a load_modules entry: the early Rust helper is its sole arming owner.
const HOOK_BYTES: &[u8] = b"#!/bin/sh\nset -eu\ncase \"${1:-}\" in prereqs) exit 0 ;; esac\n. /usr/share/initramfs-tools/hook-functions\ncopy_exec /usr/lib/droidloom/qualification/once-recovery\ncopy_file config /etc/droidloom/qualification/early.json\nmanual_add_modules softdog\n";
// The unchanged upstream panic() handles panic=10 by sleeping ten seconds and
// reboot -f, without offering an interactive shell. The normal /init parses that
// same required command-line argument. An identified early owner also reboots
// directly on a failed arming/readback operation, before returning to this script.
const SCRIPT_BYTES: &[u8] = b"#!/bin/sh\nset -eu\ncase \"${1:-}\" in prereqs) exit 0 ;; esac\n. /scripts/functions\npanic=10\nexport panic\nif ! /usr/lib/droidloom/qualification/once-recovery original-once-early-recovery; then\n    panic 'Droidloom once recovery did not arm and verify the admitted watchdog'\n    exit 1\nfi\n";

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct RecipeInput {
    schema: String,
    normal_producer: FilePin,
    base_intent: FilePin,
    early_configuration: FilePin,
}

/// This serializable source description is not an installation authority. Only
/// the existing producer's real private-build owner may install its fixed files.
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct RecoveryRecipe {
    schema: String,
    source_input: FilePin,
    source_producer: FilePin,
    helper: FilePin,
    base_intent: FilePin,
    early_configuration: FilePin,
    normal_public_release_id: String,
    normal_native_release_id: String,
    recovery: RecoveryBootSpec,
}

struct Guard {
    pin: FilePin,
    file: File,
    identity: Identity,
}
impl Guard {
    fn open(pin: &FilePin, mode: Option<u32>) -> Result<Self> {
        fs::Tree::open("/", 0)?.parent(&fs::absolute_string(&pin.path)?)?;
        let (file, identity) = files::open_pin(pin)?;
        ensure(
            identity.uid == 0
                && identity.gid == 0
                && identity.nlink == 1
                && identity.mode & 0o7022 == 0
                && mode.is_none_or(|v| identity.mode & 0o7777 == v)
                && fs::xattrs(&file)?.is_empty(),
            "recovery material is not an ordinary root-controlled source",
        )?;
        let result = Self {
            pin: pin.clone(),
            file,
            identity,
        };
        result.revalidate()?;
        Ok(result)
    }
    fn revalidate(&self) -> Result<()> {
        (&self.file).rewind()?;
        ensure(
            fs::stat(&self.file)? == self.identity
                && fs::hash(&self.file)? == self.pin.sha256
                && fs::stat(&self.file)? == self.identity
                && fs::Tree::open("/", 0)?.identity(&fs::absolute_string(&self.pin.path)?)?
                    == self.identity,
            "recovery source changed or was replaced during verification",
        )
    }
}
fn same_bytes(a: &FilePin, b: &FilePin) -> bool {
    a.bytes == b.bytes && a.sha256 == b.sha256
}
fn configuration(recipe: &RecoveryRecipe) -> Result<EarlyConfiguration> {
    let guard = Guard::open(&recipe.early_configuration, Some(0o400))?;
    let config: EarlyConfiguration =
        serde_json::from_slice(&files::read_pin(&recipe.early_configuration, 65536)?)?;
    config.recovery.validate()?;
    ensure(
        config.schema == "droidloom.original-once-early.v1"
            && config.intent_sha256 == recipe.base_intent.sha256
            && serde_json::to_value(&config.recovery)? == serde_json::to_value(&recipe.recovery)?,
        "recovery configuration does not bind its exact intent and schedule",
    )?;
    guard.revalidate()?;
    Ok(config)
}
fn material_binding(recipe: &RecoveryRecipe, materials: &Value) -> Result<()> {
    recipe.recovery.validate()?;
    ensure(
        matches!(recipe.schema.as_str(), INPUT_SCHEMA | STAGE_SCHEMA)
            && same_bytes(&recipe.source_producer, &recipe.helper)
            && recipe.recovery.helper_bytes == recipe.helper.bytes
            && recipe.recovery.helper_sha256 == recipe.helper.sha256
            && materials["deployment_id"] == recipe.recovery.candidate_id
            && materials["public_release_id"] == recipe.normal_public_release_id
            && materials["native_release_id"] == recipe.normal_native_release_id
            && materials["root_uuid"] == contract::ROOT_UUID
            && materials["original_kernel"] == contract::ORIGINAL_KERNEL
            && materials["kernel_release"] == KERNEL
            && materials["kernel_sha256"] == KERNEL_SHA
            && contract::digest(&recipe.normal_public_release_id)
            && contract::digest(&recipe.normal_native_release_id),
        "recovery recipe differs from the actually admitted normal candidate",
    )
}

pub(crate) fn admit_recovery_recipe(
    input: &FilePin,
    producer: &FilePin,
    normal_materials: &Value,
) -> Result<RecoveryRecipe> {
    let input_guard = Guard::open(input, Some(0o400))?;
    let source: RecipeInput = serde_json::from_slice(&files::read_pin(input, 65536)?)?;
    ensure(
        source.schema == INPUT_SCHEMA
            && source.normal_producer.path == producer.path
            && same_bytes(&source.normal_producer, producer),
        "recovery helper is not this normal initramfs producer",
    )?;
    let producer_guard = Guard::open(producer, None)?;
    let intent_guard = Guard::open(&source.base_intent, Some(0o400))?;
    let config_guard = Guard::open(&source.early_configuration, Some(0o400))?;
    let intent: Value =
        serde_json::from_slice(&files::read_pin(&source.base_intent, 16 * 1024 * 1024)?)?;
    let config: EarlyConfiguration =
        serde_json::from_slice(&files::read_pin(&source.early_configuration, 65536)?)?;
    let recipe = RecoveryRecipe {
        schema: INPUT_SCHEMA.into(),
        source_input: input.clone(),
        source_producer: producer.clone(),
        helper: producer.clone(),
        base_intent: source.base_intent,
        early_configuration: source.early_configuration,
        normal_public_release_id: normal_materials["public_release_id"]
            .as_str()
            .ok_or("normal public release ID missing")?
            .into(),
        normal_native_release_id: normal_materials["native_release_id"]
            .as_str()
            .ok_or("normal native release ID missing")?
            .into(),
        recovery: config.recovery,
    };
    material_binding(&recipe, normal_materials)?;
    configuration(&recipe)?;
    ensure(
        intent["schema"] == "droidloom.original-once-intent.v1"
            && intent["candidate_id"] == recipe.recovery.candidate_id
            && intent["root_uuid"] == contract::ROOT_UUID
            && intent["original_kernel"] == contract::ORIGINAL_KERNEL
            && intent["original_entry"] == contract::ORIGINAL_ENTRY
            && intent["normal_public_release_id"] == recipe.normal_public_release_id
            && intent["normal_native_release_id"] == recipe.normal_native_release_id,
        "recovery source intent belongs to another original host or candidate",
    )?;
    for guard in [input_guard, producer_guard, intent_guard, config_guard] {
        guard.revalidate()?;
    }
    Ok(recipe)
}

pub(crate) fn stage_recovery_recipe(
    recipe: &RecoveryRecipe,
    build: &Path,
) -> Result<RecoveryRecipe> {
    ensure(
        recipe.schema == INPUT_SCHEMA
            && build.file_name().is_some_and(|v| v == "build")
            && build.parent().and_then(Path::parent)
                == Some(Path::new("/var/lib/droidloom-qualification")),
        "recovery staging is outside the existing private initramfs build",
    )?;
    let tree = fs::Tree::open(&fs::absolute_string(build)?, 0)?;
    ensure(
        fs::stat(&tree.root)?.mode & 0o7777 == 0o700,
        "private recovery build mode",
    )?;
    let helper = FilePin {
        path: build.join("producer"),
        ..recipe.source_producer.clone()
    };
    Guard::open(&helper, Some(0o555))?.revalidate()?;
    configuration(recipe)?;
    let destination = build.join("recovery");
    files::private_dir(&destination)?;
    let mut staged = recipe.clone();
    for (source, name) in [
        (&recipe.base_intent, "INTENT.json"),
        (&recipe.early_configuration, "EARLY.json"),
    ] {
        Guard::open(source, Some(0o400))?.revalidate()?;
        files::copy_pin(source, &destination.join(name), 0o400)?;
    }
    staged.schema = STAGE_SCHEMA.into();
    staged.helper.path = PathBuf::from("/build/producer");
    staged.base_intent.path = PathBuf::from("/build/recovery/INTENT.json");
    staged.early_configuration.path = PathBuf::from("/build/recovery/EARLY.json");
    File::open(&destination)?.sync_all()?;
    Ok(staged)
}

fn private_owner(recipe: &RecoveryRecipe, producer: &FilePin, original: &Value) -> Result<()> {
    ensure(
        recipe.schema == STAGE_SCHEMA
            && recipe.helper.path == Path::new("/build/producer")
            && recipe.base_intent.path == Path::new("/build/recovery/INTENT.json")
            && recipe.early_configuration.path == Path::new("/build/recovery/EARLY.json")
            && same_bytes(producer, &recipe.source_producer)
            && producer.path == recipe.source_producer.path
            && std::process::id() == 1
            && rustix::process::geteuid().as_raw() == 0,
        "recovery installation requires the normal private producer PID1",
    )?;
    let root = fs::Tree::open("/", 0)?;
    let root_id = fs::stat(&root.root)?;
    ensure(
        rustix::fs::fstatfs(&root.root)?.f_type as u64 == 0x794c7630
            && json!([root_id.dev, root_id.ino]) != original["root_identity"],
        "recovery additions may only enter the actual private overlay",
    )?;
    let own = std::fs::metadata("/proc/self/root")?;
    let pid1 = std::fs::metadata("/proc/1/root")?;
    use std::os::unix::fs::MetadataExt;
    ensure(
        (own.dev(), own.ino()) == (root_id.dev, root_id.ino)
            && (pid1.dev(), pid1.ino()) == (root_id.dev, root_id.ino),
        "private recovery process root is not its private PID1 root",
    )?;
    for ns in ["user", "mnt", "pid", "net"] {
        let observed = std::fs::read_link(format!("/proc/self/ns/{ns}"))?;
        ensure(
            observed == std::fs::read_link(format!("/proc/1/ns/{ns}"))?
                && original["namespaces"][ns]
                    .as_str()
                    .is_some_and(|v| observed != Path::new(v)),
            "recovery additions are outside the producer's independent namespaces",
        )?;
    }
    let helper = Guard::open(&recipe.helper, Some(0o555))?;
    ensure(
        fs::stat(&File::open("/proc/self/exe")?)? == helper.identity,
        "recovery installer is not the held normal producer inode",
    )?;
    helper.revalidate()?;
    Ok(())
}

fn public_parent(path: &Path) -> Result<()> {
    let tree = fs::Tree::open("/", 0)?;
    let parent = path.parent().ok_or("recovery destination parent missing")?;
    let mut current = String::new();
    for name in crate::paths::parts(&fs::absolute_string(parent)?)? {
        current.push('/');
        current.push_str(name);
        match tree.identity(&current) {
            Ok(id) => ensure(
                FileType::from_raw_mode(id.mode) == FileType::Directory
                    && id.uid == 0
                    && id.gid == 0
                    && id.mode & 0o7022 == 0,
                "recovery parent is not a normal root-controlled directory",
            )?,
            Err(e) if e.downcast_ref::<rustix::io::Errno>() == Some(&rustix::io::Errno::NOENT) => {
                tree.mkdir(&current)?;
                rustix::fs::fchmod(&tree.dir(&current)?, Mode::from_raw_mode(0o755))?;
            }
            Err(e) => return Err(e),
        }
    }
    Ok(())
}
fn check_stock(path: &str, bytes: u64, sha: &str) -> Result<()> {
    Guard::open(
        &FilePin {
            path: path.into(),
            bytes,
            sha256: sha.into(),
        },
        None,
    )?
    .revalidate()
}
pub(crate) fn install_private_recipe(
    recipe: &RecoveryRecipe,
    producer: &FilePin,
    original: &Value,
) -> Result<Value> {
    private_owner(recipe, producer, original)?;
    configuration(recipe)?;
    let intent = Guard::open(&recipe.base_intent, Some(0o400))?;
    check_stock(
        "/usr/share/initramfs-tools/init",
        STOCK_INIT_BYTES,
        STOCK_INIT_SHA,
    )?;
    check_stock(
        "/usr/share/initramfs-tools/scripts/functions",
        STOCK_FUNCTIONS_BYTES,
        STOCK_FUNCTIONS_SHA,
    )?;
    check_stock(
        "/usr/share/initramfs-tools/hook-functions",
        STOCK_HOOKS_BYTES,
        STOCK_HOOKS_SHA,
    )?;
    for path in [HOOK, SCRIPT, EARLY_CONFIG, EARLY_EXECUTABLE] {
        ensure(
            !Path::new(path).try_exists()?,
            "recovery destination already exists",
        )?;
        public_parent(Path::new(path))?;
    }
    files::copy_pin(&recipe.helper, Path::new(EARLY_EXECUTABLE), 0o555)?;
    files::copy_pin(&recipe.early_configuration, Path::new(EARLY_CONFIG), 0o444)?;
    files::write_new(Path::new(HOOK), HOOK_BYTES, 0o755)?;
    files::write_new(Path::new(SCRIPT), SCRIPT_BYTES, 0o755)?;
    let mut installed = Vec::new();
    for (path, mode) in [
        (HOOK, 0o755),
        (SCRIPT, 0o755),
        (EARLY_CONFIG, 0o444),
        (EARLY_EXECUTABLE, 0o555),
    ] {
        let pin = files::pin_file(Path::new(path))?;
        let guard = Guard::open(&pin, Some(mode))?;
        File::open(Path::new(path).parent().unwrap())?.sync_all()?;
        installed.push(json!({"pin":pin,"identity":guard.identity}));
        guard.revalidate()?;
    }
    private_owner(recipe, producer, original)?;
    intent.revalidate()?;
    Ok(
        json!({"schema":"droidloom.original-once-private-recovery-installed.v1",
        "recipe":recipe,"installed":installed,"module_load_owner":"source-bound early Rust helper",
        "physical_install":false,"watchdog_armed":false,"qualification_boot_authorized":false}),
    )
}

fn image_member(root: &Path, name: &str, bytes: u64, sha: &str, mode: u32) -> Result<Value> {
    let (pin, aliases) = files::resolve_public_file(root, name)?;
    let (held, before) = files::open_pin(&pin)?;
    ensure(
        pin.bytes == bytes
            && pin.sha256 == sha
            && before.uid == 0
            && before.gid == 0
            && before.nlink == 1
            && before.mode & 0o7777 == mode
            && fs::xattrs(&held)?.is_empty()
            && fs::stat(&held)? == before,
        "normal recovery image member differs from its exact source bytes or metadata",
    )?;
    Ok(json!({"name":name,"actual":pin,"identity":before,"aliases":aliases}))
}
fn verify_order(raw: &[u8]) -> Result<()> {
    ensure(raw.len() <= 65536, "init-top order exceeds bound")?;
    let text = std::str::from_utf8(raw)?;
    let lines = text.lines().collect::<Vec<_>>();
    ensure(
        !lines.is_empty() && lines.len() % 2 == 0 && lines[0] == format!("{IMAGE_SCRIPT} \"$@\""),
        "recovery must be the first actual normal init-top operation",
    )?;
    let mut count = 0;
    for pair in lines.chunks_exact(2) {
        ensure(
            pair[1] == "[ -e /conf/param.conf ] && . /conf/param.conf"
                && pair[0].starts_with("/scripts/init-top/")
                && pair[0].ends_with(" \"$@\""),
            "normal init-top order syntax changed",
        )?;
        let name = pair[0]
            .strip_prefix("/scripts/init-top/")
            .unwrap()
            .strip_suffix(" \"$@\"")
            .unwrap();
        ensure(
            !name.is_empty()
                && name
                    .bytes()
                    .all(|v| v.is_ascii_alphanumeric() || b"-_.".contains(&v)),
            "unexpected operation in init-top order",
        )?;
        if pair[0] == lines[0] {
            count += 1;
        }
    }
    ensure(count == 1, "recovery entry is duplicated in init-top order")
}
pub(crate) fn verify_recovery_image(recipe: &RecoveryRecipe, unpacked: &Path) -> Result<Value> {
    recipe.recovery.validate()?;
    ensure(
        same_bytes(&recipe.source_producer, &recipe.helper)
            && recipe.helper.bytes == recipe.recovery.helper_bytes
            && recipe.helper.sha256 == recipe.recovery.helper_sha256,
        "recovery image recipe has a different normal helper",
    )?;
    let roots = [unpacked.to_owned(), unpacked.join("main")]
        .into_iter()
        .filter(|r| r.join("init").is_file())
        .collect::<Vec<_>>();
    ensure(
        roots.len() == 1,
        "normal unpack must have one initial recovery root",
    )?;
    let root = &roots[0];
    let mut members = Vec::new();
    for (path, bytes, sha, mode) in [
        (
            EARLY_EXECUTABLE.to_owned(),
            recipe.helper.bytes,
            recipe.helper.sha256.clone(),
            0o555,
        ),
        (
            EARLY_CONFIG.to_owned(),
            recipe.early_configuration.bytes,
            recipe.early_configuration.sha256.clone(),
            0o444,
        ),
        (
            IMAGE_SCRIPT.to_owned(),
            SCRIPT_BYTES.len() as u64,
            fs::digest(SCRIPT_BYTES),
            0o755,
        ),
        (
            format!("/usr/lib/modules/{KERNEL}/{MODULE_REL}"),
            MODULE_BYTES,
            MODULE_SHA.to_owned(),
            0o644,
        ),
        (
            "/init".to_owned(),
            STOCK_INIT_BYTES,
            STOCK_INIT_SHA.to_owned(),
            0o755,
        ),
        (
            "/scripts/functions".to_owned(),
            STOCK_FUNCTIONS_BYTES,
            STOCK_FUNCTIONS_SHA.to_owned(),
            0o644,
        ),
    ] {
        members.push(image_member(root, &path, bytes, &sha, mode)?);
    }
    let (order_pin, _) = files::resolve_public_file(root, "/scripts/init-top/ORDER")?;
    let order = files::read_pin(&order_pin, 65536)?;
    verify_order(&order)?;
    let (configuration_pin, _) = files::resolve_public_file(root, EARLY_CONFIG)?;
    let config: EarlyConfiguration =
        serde_json::from_slice(&files::read_pin(&configuration_pin, 65536)?)?;
    ensure(
        config.schema == "droidloom.original-once-early.v1"
            && config.intent_sha256 == recipe.base_intent.sha256
            && serde_json::to_value(config.recovery)? == serde_json::to_value(&recipe.recovery)?,
        "unpacked early configuration no longer binds the immutable recovery intent",
    )?;
    let (modules_pin, _) = files::resolve_public_file(root, "/conf/modules")?;
    let modules = String::from_utf8(files::read_pin(&modules_pin, 65536)?)?;
    ensure(
        !modules.lines().any(|l| {
            l.split('#').next().unwrap_or("").split_whitespace().next() == Some("softdog")
        }),
        "normal module configuration tries to arm softdog before its sole owner",
    )?;
    Ok(
        json!({"schema":"droidloom.original-once-recovery-image-readback.v1",
        "recipe":recipe,"members":members,"actual_init_top_order":order_pin,
        "normal_module_configuration":modules_pin,"stock_panic_seconds":10,
        "watchdog_armed":false,"selected_kernel_runtime_verified":false,
        "hardware_hang_coverage":false,"qualification_boot_authorized":false}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn normal_order_requires_recovery_first_once_without_shell_injection() -> Result<()> {
        let first =
            format!("{IMAGE_SCRIPT} \"$@\"\n[ -e /conf/param.conf ] && . /conf/param.conf\n");
        let stock =
            "/scripts/init-top/udev \"$@\"\n[ -e /conf/param.conf ] && . /conf/param.conf\n";
        verify_order(format!("{first}{stock}").as_bytes())?;
        for bad in [
            format!("{stock}{first}"),
            format!("{first}{first}"),
            format!("{first}reboot -f\n"),
            first.replace("$@", "$(reboot)"),
        ] {
            assert!(verify_order(bad.as_bytes()).is_err());
        }
        Ok(())
    }
    #[test]
    fn recipe_keeps_normal_helper_identity_and_exact_material_family() -> Result<()> {
        let helper = FilePin {
            path: "/fixed/producer".into(),
            bytes: 10000,
            sha256: "a".repeat(64),
        };
        let recipe = RecoveryRecipe {
            schema: INPUT_SCHEMA.into(),
            source_input: helper.clone(),
            source_producer: helper.clone(),
            helper: helper.clone(),
            base_intent: helper.clone(),
            early_configuration: helper.clone(),
            normal_public_release_id: "b".repeat(64),
            normal_native_release_id: "c".repeat(64),
            recovery: RecoveryBootSpec {
                schema: "droidloom.original-once-recovery-boot.v1".into(),
                candidate_id: "d".repeat(64),
                helper_bytes: helper.bytes,
                helper_sha256: helper.sha256,
                kernel_release: KERNEL.into(),
                kernel_sha256: KERNEL_SHA.into(),
                kernel_config_sha256: contract::CONFIG_SHA.into(),
                module_relative: MODULE_REL.into(),
                module_bytes: MODULE_BYTES,
                module_sha256: MODULE_SHA.into(),
                watchdog_seconds: 1200,
                collect_at_boot_seconds: 600,
                return_at_boot_seconds: 900,
                panic_seconds: 10,
            },
        };
        let materials = json!({"deployment_id":"d".repeat(64),"public_release_id":"b".repeat(64),
            "native_release_id":"c".repeat(64),"root_uuid":contract::ROOT_UUID,
            "original_kernel":contract::ORIGINAL_KERNEL,"kernel_release":KERNEL,"kernel_sha256":KERNEL_SHA});
        material_binding(&recipe, &materials)?;
        for key in [
            "deployment_id",
            "public_release_id",
            "native_release_id",
            "root_uuid",
            "kernel_sha256",
        ] {
            let mut changed = materials.clone();
            changed[key] = json!("e".repeat(64));
            assert!(material_binding(&recipe, &changed).is_err());
        }
        let mut changed = recipe;
        changed.helper.sha256 = "f".repeat(64);
        assert!(material_binding(&changed, &materials).is_err());
        Ok(())
    }
    #[test]
    fn fixed_recipe_uses_normal_module_copy_and_stock_panic_not_force_load() {
        let hook = std::str::from_utf8(HOOK_BYTES).unwrap();
        assert!(hook.ends_with("manual_add_modules softdog\n"));
        assert!(!hook.contains("force_load") && !hook.contains("modprobe"));
        let script = std::str::from_utf8(SCRIPT_BYTES).unwrap();
        assert!(script.contains(". /scripts/functions\npanic=10\n"));
        assert!(script.contains("original-once-early-recovery; then\n    panic "));
        assert!(!script.contains("/proc/sysrq") && !script.contains("while "));
    }
}
