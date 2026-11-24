//! Fixed first Pocket4 activation. Input documents select bytes; only the live
//! original-owner transaction can authorize installation and one-shot boot.
use super::{
    Result,
    activation_android::{self, AndroidInputs},
    activation_boot,
    activation_commit::ProductInstaller,
    activation_files::{self as files, FileIdentity, FilePin, HeldFile},
    activation_host::{self, HostInputs},
    activation_labels::{self, LabelInputs, Labeler},
    activation_native::NativeInstaller,
    activation_owner::InstallationPermit,
    activation_platform::{self, PlatformInputs},
    activation_query,
    activation_userdata::{OriginalData, OriginalInputs},
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    fs,
    os::unix::fs::MetadataExt,
    path::{Path, PathBuf},
};

const BASE: &str = "/var/lib/droidloom/activation-staging";
const MAX_PLAN: u64 = 4 * 1024 * 1024;
const MAX_RECEIPT: u64 = 32 * 1024 * 1024;
fn require(ok: bool, message: &str) -> Result<()> {
    if ok { Ok(()) } else { Err(message.into()) }
}
fn git_id(s: &str) -> bool {
    s.len() == 40
        && s.bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Plan {
    schema: String,
    source_commit: String,
    source_tree: String,
    host: HostInputs,
    platform: PlatformInputs,
    android: AndroidInputs,
    original: OriginalInputs,
    labels: LabelInputs,
}
impl Plan {
    fn validate(&self) -> Result<()> {
        require(
            self.schema == "droidloom-pocket4-first-activation-v1"
                && git_id(&self.source_commit)
                && git_id(&self.source_tree),
            "first activation requires this exact Pocket4 source-bound plan",
        )?;
        require(
            self.original.cell.path == Path::new("/etc/droidloom/cell.json"),
            "first activation cannot select another desktop user's data",
        )?;
        activation_android::install_paths(&self.android)?;
        Ok(())
    }
}
#[derive(Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct TreeEntry {
    path: String,
    kind: String,
    mode: u32,
    uid: u32,
    gid: u32,
    device: u64,
    inode: u64,
    bytes: u64,
    sha256: Option<String>,
    target: Option<String>,
    modified_sec: i64,
    modified_nsec: i64,
    changed_sec: i64,
    changed_nsec: i64,
}
fn protected_directory(path: &Path, private: bool) -> Result<()> {
    let m = fs::symlink_metadata(path)?;
    require(
        m.is_dir()
            && m.uid() == 0
            && m.gid() == 0
            && m.mode() & 0o7022 == 0
            && (!private || m.mode() & 0o7777 == 0o700),
        "activation generation is not a protected original root directory",
    )
}
fn tree(root: &Path) -> Result<Vec<TreeEntry>> {
    protected_directory(root, true)?;
    let root_meta = fs::symlink_metadata(root)?;
    let device = root_meta.dev();
    let mut pending = vec![root.to_owned()];
    let mut result = Vec::new();
    let mut inodes = BTreeSet::from([(device, root_meta.ino())]);
    let mut total = 0u64;
    while let Some(directory) = pending.pop() {
        for row in fs::read_dir(&directory)? {
            let path = row?.path();
            let relative = path
                .strip_prefix(root)?
                .to_str()
                .ok_or("non-UTF8 stage member")?
                .to_owned();
            require(
                !relative.is_empty()
                    && !relative
                        .split('/')
                        .any(|p| p.is_empty() || p == "." || p == ".."),
                "unsafe staged member path",
            )?;
            let m = fs::symlink_metadata(&path)?;
            require(
                m.uid() == 0
                    && m.gid() == 0
                    && m.dev() == device
                    && inodes.insert((m.dev(), m.ino())),
                "staged member escapes root custody or aliases another original object",
            )?;
            let (kind, bytes, sha256, target) = if m.is_dir() {
                protected_directory(&path, false)?;
                pending.push(path.clone());
                ("directory", 0, None, None)
            } else if m.is_file() {
                let before = FileIdentity::read(m.clone())?;
                let pin = files::pin_file(&path)?;
                require(
                    pin.bytes <= 8 * 1024 * 1024 * 1024
                        && FileIdentity::read(fs::symlink_metadata(&path)?)? == before,
                    "staged ordinary file changed during inventory",
                )?;
                total = total
                    .checked_add(pin.bytes)
                    .ok_or("stage inventory size overflow")?;
                require(
                    total <= 64 * 1024 * 1024 * 1024,
                    "stage exceeds the fixed complete release bound",
                )?;
                files::no_privilege_xattrs(&files::open_regular(&path)?)?;
                ("file", pin.bytes, Some(pin.sha256), None)
            } else if m.file_type().is_symlink() {
                require(
                    relative == "usr/lib/x86_64-linux-gnu/libapparmor.so.1"
                        && m.nlink() == 1
                        && fs::read_link(&path)? == Path::new("libapparmor.so.1.30.7"),
                    "stage contains an unrelated or escaping symlink",
                )?;
                ("symlink", 0, None, Some("libapparmor.so.1.30.7".into()))
            } else {
                return Err("stage contains a device, socket or other unexpected node".into());
            };
            result.push(TreeEntry {
                path: relative,
                kind: kind.into(),
                mode: m.mode(),
                uid: m.uid(),
                gid: m.gid(),
                device: m.dev(),
                inode: m.ino(),
                bytes,
                sha256,
                target,
                modified_sec: m.mtime(),
                modified_nsec: m.mtime_nsec(),
                changed_sec: m.ctime(),
                changed_nsec: m.ctime_nsec(),
            });
            require(
                result.len() <= 20000,
                "stage namespace exceeds its fixed bound",
            )?;
        }
    }
    result.sort_by(|a, b| a.path.cmp(&b.path));
    Ok(result)
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct StageReceipt {
    schema: String,
    plan: FilePin,
    source_commit: String,
    source_tree: String,
    platform: Value,
    host: Value,
    android: Value,
    labels: Value,
    preflight: Value,
    tree: Vec<TreeEntry>,
    live_system_modified: bool,
    production_ready: bool,
}
fn generation(value: &str) -> Result<(PathBuf, PathBuf, PathBuf)> {
    require(
        files::valid_digest(value),
        "activation generation must be the exact plan SHA256",
    )?;
    let parent = Path::new(BASE).join(value);
    Ok((parent.join("root"), parent.join("work"), parent))
}
fn private_child(parent: &Path, name: &str) -> Result<PathBuf> {
    let path = parent.join(name);
    files::private_dir(&path)?;
    Ok(path)
}
fn load_plan(path: &Path) -> Result<(Plan, HeldFile)> {
    let pin = files::pin_file(path)?;
    let held = HeldFile::open(&pin, MAX_PLAN)?;
    let plan: Plan = serde_json::from_slice(&held.read_all(MAX_PLAN)?)?;
    plan.validate()?;
    Ok((plan, held))
}
fn compare_boot_preview(old: &Value, new: &Value) -> Result<()> {
    for key in ["entry", "root_filesystem_uuid", "retained_fallback"] {
        require(
            old.get(key).is_some() && old[key] == new[key],
            "physical GRUB preview changed since staging",
        )?;
    }
    for key in ["script", "kernel", "initrd"] {
        require(
            old[key]["bytes"] == new[key]["bytes"] && old[key]["sha256"] == new[key]["sha256"],
            "physical one-shot bytes differ from the reviewed stage preview",
        )?;
    }
    Ok(())
}
pub(super) fn stage(plan_path: &Path) -> Result<Value> {
    super::require_root()?;
    super::require_legacy()?;
    let (plan, plan_file) = load_plan(plan_path)?;
    let original = OriginalData::open(&plan.original)?;
    let identity = super::activation_identity::preflight(&original, false)?;
    let owner_preflight = super::activation_owner::preflight(&original)?;
    let generation_sha = plan_file.pin().sha256.clone();
    let (root, work, parent) = generation(&generation_sha)?;
    files::ensure_dir(Path::new("/"), "var/lib/droidloom")?;
    match fs::symlink_metadata(BASE) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => files::private_dir(Path::new(BASE))?,
        Err(e) => return Err(e.into()),
        Ok(_) => protected_directory(Path::new(BASE), true)?,
    }
    files::private_dir(&parent)?;
    files::private_dir(&root)?;
    files::private_dir(&work)?;
    let copied_plan = plan_file.copy_new(&work.join("PLAN.json"), 0o400)?;
    let host = activation_host::stage(
        &root,
        &work,
        &plan.host,
        &plan.source_commit,
        &plan.source_tree,
    )?;
    activation_host::executing_helper_matches(&host)?;
    let platform = activation_platform::stage(&plan.platform, &root, &work)?;
    let label_stage = activation_labels::stage(&root, &work, &plan.labels)?;
    let (_, android) = activation_android::stage(&root, &plan.android, &original)?;
    let labels = Labeler::from_stage(&root)?;
    let label_preflight = labels.preflight()?;
    let native = NativeInstaller::from_stage(&root, &work, &platform)?;
    let native_preflight = native.preflight()?;
    let products = ProductInstaller::from_stage(
        &root,
        &work,
        &host,
        &plan.android,
        &plan.platform,
        &platform,
    )?;
    let product_preflight = products.preflight()?;
    let boot = activation_boot::prepare(
        &root,
        &private_child(&work, "boot-preview")?,
        &generation_sha,
        &plan.platform,
    )?;
    let boot_preview = boot.receipt();
    original.revalidate()?;
    plan_file.revalidate()?;
    let inventory = tree(&root)?;
    let receipt = StageReceipt {
        schema: "droidloom-pocket4-first-activation-staged-v1".into(),
        plan: copied_plan,
        source_commit: plan.source_commit.clone(),
        source_tree: plan.source_tree.clone(),
        platform,
        host: activation_host::receipt(&host, &plan.host),
        android,
        labels: label_stage,
        preflight: json!({"labels":label_preflight,"native":native_preflight,"products":product_preflight,
            "one_shot_boot":boot_preview,"original_data":original.receipt(),"identity_transition":identity,"owner":owner_preflight}),
        tree: inventory,
        live_system_modified: false,
        production_ready: false,
    };
    let receipt_pin = files::write_new(
        &work.join("STAGED.json"),
        &serde_json::to_vec_pretty(&receipt)?,
        0o400,
    )?;
    files::sync_parent(&receipt_pin.path)?;
    Ok(
        json!({"generation":generation_sha,"stage":parent,"receipt":receipt_pin,
        "live_system_modified":false,"production_ready":false}),
    )
}
pub(super) fn activate(value: &str) -> Result<Value> {
    super::require_root()?;
    super::require_legacy()?;
    let (root, work, parent) = generation(value)?;
    for p in [
        Path::new(BASE),
        parent.as_path(),
        root.as_path(),
        work.as_path(),
    ] {
        protected_directory(p, true)?;
    }
    let staged_pin = files::pin_file(&work.join("STAGED.json"))?;
    let staged = HeldFile::open(&staged_pin, MAX_RECEIPT)?;
    require(
        staged.identity().uid == 0
            && staged.identity().gid == 0
            && staged.identity().mode & 0o7777 == 0o400,
        "staging receipt is not sealed by its normal root producer",
    )?;
    let receipt: StageReceipt = serde_json::from_slice(&staged.read_all(MAX_RECEIPT)?)?;
    require(
        receipt.schema == "droidloom-pocket4-first-activation-staged-v1"
            && receipt.plan.path == work.join("PLAN.json")
            && receipt.plan.sha256 == value
            && !receipt.live_system_modified
            && !receipt.production_ready,
        "activation cannot adopt a foreign, partial or claimed-runtime stage",
    )?;
    let (plan, plan_file) = load_plan(&receipt.plan.path)?;
    require(
        plan_file.pin().bytes == receipt.plan.bytes
            && plan_file.pin().sha256 == value
            && plan_file.identity().uid == 0
            && plan_file.identity().gid == 0
            && plan_file.identity().mode & 0o7777 == 0o400
            && receipt.source_commit == plan.source_commit
            && receipt.source_tree == plan.source_tree,
        "original sealed plan changed",
    )?;
    require(
        tree(&root)? == receipt.tree,
        "actual staged namespace or complete bytes changed",
    )?;
    let original = OriginalData::open(&plan.original)?;
    let identity = super::activation_identity::preflight(&original, false)?;
    let owner_preflight = super::activation_owner::preflight(&original)?;
    let host =
        activation_host::verify_staged(&root, &plan.host, &plan.source_commit, &plan.source_tree)?;
    activation_host::executing_helper_matches(&host)?;
    let selected = activation_android::verify_staged(&root, &plan.android, &original)?;
    let labels = Labeler::from_stage(&root)?;
    let native = NativeInstaller::from_stage(&root, &work, &receipt.platform)?;
    let products = ProductInstaller::from_stage(
        &root,
        &work,
        &host,
        &plan.android,
        &plan.platform,
        &receipt.platform,
    )?;
    // All routine materials, filesystem primitives, ordinary native dependencies
    // and existing boot configuration are checked before the first live fence.
    let label_preflight = labels.preflight()?;
    let native_preflight = native.preflight()?;
    let product_preflight = products.preflight()?;
    let preview = activation_boot::prepare(
        &root,
        &private_child(&work, "boot-recheck")?,
        value,
        &plan.platform,
    )?;
    compare_boot_preview(&receipt.preflight["one_shot_boot"], &preview.receipt())?;
    original.revalidate()?;
    plan_file.revalidate()?;
    staged.revalidate()?;
    let preflight = files::write_new(
        &work.join("ACTIVATION-PREFLIGHT.json"),
        &serde_json::to_vec_pretty(
            &json!({"labels":label_preflight,"native":native_preflight,"products":product_preflight,
            "boot":preview.receipt(),"original_data":original.receipt(),"identity_transition":identity,"owner":owner_preflight}),
        )?,
        0o400,
    )?;
    drop(preview);
    let mut permit = InstallationPermit::retire(original, value, &labels)?;
    super::activation_identity::preflight(permit.original(), false)?;
    let ordinary = products.install(&permit)?;
    let native_install = native.install(&permit)?;
    permit.revalidate()?;
    let userdata_labels = permit.label_userdata(&labels)?;
    let bulk_labels = labels.apply_live_tree(&permit)?;
    let identity_readback = super::activation_identity::preflight(permit.original(), true)?;
    let query_labels = activation_query::label_installed(&plan.android.runtime.sha256, &permit)?;
    let backup = private_child(&work, "configuration-backup")?;
    let committed_selection = permit.publish_configuration(&selected, &backup, &labels)?;
    let native_readback = native.observe_installed(&permit)?;
    let product_readback = products.observe_installed(&permit)?;
    // All live labels are now complete. Capture fresh original GRUB identities;
    // the earlier preview cannot survive a legitimate label's ctime change.
    let prepared = activation_boot::prepare(
        &root,
        &private_child(&work, "boot-commit")?,
        value,
        &plan.platform,
    )?;
    compare_boot_preview(&receipt.preflight["one_shot_boot"], &prepared.receipt())?;
    permit.revalidate()?;
    native_readback.revalidate()?;
    product_readback.revalidate()?;
    committed_selection.revalidate()?;
    query_labels.revalidate()?;
    let boot = activation_boot::commit(prepared, &permit, &labels)?;
    permit.revalidate()?;
    native_readback.revalidate()?;
    product_readback.revalidate()?;
    committed_selection.revalidate()?;
    query_labels.revalidate()?;
    boot.revalidate()?;
    let result = json!({"schema":"droidloom-pocket4-first-activation-committed-v1","generation":value,
        "source_commit":plan.source_commit,"source_tree":plan.source_tree,"preflight":preflight,
        "original_owner":permit.receipt(),"ordinary_install":ordinary,"native_install":native_install,
        "userdata_labels":userdata_labels,"identity_transition":identity_readback,"normal_labels":bulk_labels,"query_inputs":query_labels.receipt(),
        "native_readback":native_readback.receipt(),"ordinary_readback":product_readback.receipt(),
        "selection":committed_selection.receipt(),"one_shot_boot":boot.receipt(),
        "original_userdata_preserved":true,"old_kernel_retained":true,"reboot_requested":false,
        "runtime_qualified":false,"production_ready":false});
    let commit_pin = files::write_new(
        &work.join("COMMITTED.json"),
        &serde_json::to_vec_pretty(&result)?,
        0o400,
    )?;
    files::sync_parent(&commit_pin.path)?;
    permit.finish(&boot, &committed_selection)?;
    let completion = files::write_new(
        &work.join("ACTIVATED.json"),
        &serde_json::to_vec_pretty(
            &json!({"committed":commit_pin,"original_fence_consumed":true,"one_shot_boot_armed":true,
            "runtime_qualified":false,"production_ready":false}),
        )?,
        0o400,
    )?;
    files::sync_parent(&completion.path)?;
    Ok(
        json!({"generation":value,"committed":commit_pin,"activation":completion,
        "one_shot_boot_armed":true,"old_kernel_retained":true,"original_userdata_preserved":true,
        "reboot_requested":false,"runtime_qualified":false,"production_ready":false}),
    )
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_canonical_first_generation_can_select_the_fixed_stage() {
        for bad in [
            "",
            "a/../b",
            &"A".repeat(64),
            &"g".repeat(64),
            &"a".repeat(63),
        ] {
            assert!(generation(bad).is_err());
        }
        let (root, work, parent) = generation(&"a".repeat(64)).unwrap();
        assert_eq!(root.parent(), Some(parent.as_path()));
        assert_eq!(work.parent(), Some(parent.as_path()));
        assert_eq!(root.file_name().unwrap(), "root");
    }
    #[test]
    fn boot_recheck_compares_content_and_identity_not_changed_observation_paths() {
        let pin = json!({"path":"/old/preview","bytes":5,"sha256":"a".repeat(64)});
        let old = json!({"entry":"selected","root_filesystem_uuid":"uuid","retained_fallback":"old",
            "script":pin,"kernel":pin,"initrd":pin});
        let mut now = old.clone();
        now["script"]["path"] = json!("/new/preview");
        compare_boot_preview(&old, &now).unwrap();
        now["script"]["sha256"] = json!("b".repeat(64));
        assert!(compare_boot_preview(&old, &now).is_err());
        let mut now = old.clone();
        now["retained_fallback"] = json!("new");
        assert!(compare_boot_preview(&old, &now).is_err());
    }
}
