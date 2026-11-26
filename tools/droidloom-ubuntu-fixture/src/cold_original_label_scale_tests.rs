//! Isolated complete public-root scale measurement. Never a physical authority.
use super::*;
use std::{
    collections::BTreeMap,
    os::unix::fs::{MetadataExt, PermissionsExt},
    time::Instant,
};
const BASE: &str = "/var/lib/droidloom-qualification/original-label-scale-4b91-r1";
const SOURCE: &str = "/var/lib/droidloom-qualification/p4-complete-native-credentials-4b91-r2/root";

#[test]
#[ignore = "root only; exact independent public shadow root; records real SELinux xattr and syncfs costs"]
fn complete_public_shadow_root_durable_label_cost() -> Result<()> {
    ensure(
        rustix::process::geteuid().as_raw() == 0,
        "isolated scale test requires existing root",
    )?;
    let base = Path::new(BASE);
    let root = base.join("root");
    let source = std::fs::symlink_metadata(SOURCE)?;
    let target = std::fs::symlink_metadata(&root)?;
    ensure(
        source.is_dir()
            && target.is_dir()
            && (source.dev(), source.ino()) != (target.dev(), target.ino())
            && target.uid() == 0,
        "independent exact public clone required",
    )?;
    let manifest = FilePin {
        path: PathBuf::from(
            "/var/lib/droidloom-qualification/4b91-credentials-installed-r2/MANIFEST.json",
        ),
        bytes: 82414843,
        sha256: "b1035908144af716560d771e85eb526ba5a10500b6748c70dbad1825ef72f83e".into(),
    };
    let (_, id) = crate::boot_files::open_pin(&manifest)?;
    ensure(
        id.size == manifest.bytes,
        "actual full source manifest size",
    )?;
    let mf = File::open(&manifest.path)?;
    ensure(
        fs::hash(&mf)? == manifest.sha256,
        "actual full public source manifest hash",
    )?;
    let inventory_started = Instant::now();
    let mut todo = vec![root.clone()];
    let mut all: BTreeMap<(u64, u64), Vec<PathBuf>> = BTreeMap::new();
    while let Some(path) = todo.pop() {
        let md = std::fs::symlink_metadata(&path)?;
        ensure(
            md.dev() == target.dev(),
            "shadow traversal crossed filesystem",
        )?;
        ensure(all.len() < 500_000, "bounded complete root inventory")?;
        all.entry((md.dev(), md.ino()))
            .or_default()
            .push(path.clone());
        if md.is_dir() {
            for child in std::fs::read_dir(&path)? {
                todo.push(child?.path());
            }
        }
    }
    let inventory_seconds = inventory_started.elapsed().as_secs_f64();
    let records = base.join("records");
    crate::boot_files::private_dir(&records)?;
    let plan = base.join("SCALE-PLAN.json");
    crate::boot_files::write_new(
        &plan,
        &serde_json::to_vec(
            &json!({"schema":"droidloom.isolated-public-root-label-scale-plan.v1","source":SOURCE,"shadow":root,"source_manifest":manifest,"unique_inodes":all.len(),"logical_paths":all.values().map(Vec::len).sum::<usize>(),"production_authority":false}),
        )?,
        0o400,
    )?;
    let plan = crate::boot_files::pin_file(&plan)?;
    let candidate = fs::digest(b"isolated complete root scale measurement only");
    let started = Instant::now();
    let (mut prepare_s, mut apply_s, mut restore_s, mut done) = (0.0, 0.0, 0.0, 0usize);
    let mut classes: BTreeMap<String, usize> = BTreeMap::new();
    for (ordinal, ((dev, ino), aliases)) in all.iter().enumerate() {
        let path = &aliases[0];
        let held = File::from(rustix::fs::open(
            path,
            OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )?);
        let before = snapshot(&held)?;
        ensure(
            (before.identity.dev, before.identity.ino) == (*dev, *ino),
            "shadow inode changed after inventory",
        )?;
        for alias in aliases {
            let md = std::fs::symlink_metadata(alias)?;
            ensure((md.dev(), md.ino()) == (*dev, *ino), "shadow alias changed")?;
        }
        let item = records.join(format!("{ordinal:06}"));
        crate::boot_files::private_dir(&item)?;
        File::open(&records)?.sync_all()?;
        let logical = Path::new("/").join(path.strip_prefix(&root)?);
        let t = Instant::now();
        let attempt = DurableAttempt::prepare(
            Records::open(&item)?,
            held,
            &candidate,
            &plan,
            ordinal.try_into()?,
            &logical,
            b"u:object_r:p4_linux_native_config_t:s0",
            LABEL,
        )?;
        prepare_s += t.elapsed().as_secs_f64();
        let t = Instant::now();
        let actual = attempt.apply()?;
        actual.revalidate()?;
        let readback = attempt.applied_readback()?;
        readback.revalidate()?;
        apply_s += t.elapsed().as_secs_f64();
        let t = Instant::now();
        let restored = attempt.restore()?;
        restore_s += t.elapsed().as_secs_f64();
        ensure(
            restored.attributes == before.attributes
                && restored.handle == before.handle
                && only_ctime_changed(&before.identity, &restored.identity),
            "shadow restoration changed original unrelated metadata",
        )?;
        done += 1;
        *classes
            .entry(format!(
                "{:?}",
                FileType::from_raw_mode(before.identity.mode)
            ))
            .or_default() += 1;
        if done % 1000 == 0 {
            eprintln!(
                "LABEL_SCALE completed={done} total={} wall_seconds={:.3} prepare={prepare_s:.3} apply={apply_s:.3} restore={restore_s:.3}",
                all.len(),
                started.elapsed().as_secs_f64()
            );
        }
        // The experiment is safely bounded too. Every attempted inode has
        // already been restored; partial measurements remain explicit facts.
        if started.elapsed().as_secs() >= 600 {
            break;
        }
    }
    let result = json!({"schema":"droidloom.isolated-public-root-label-scale-result.v1","source_manifest":manifest,"shadow":root,"source_plan":plan,"inventory_seconds":inventory_seconds,"unique_inodes":all.len(),"logical_paths":all.values().map(Vec::len).sum::<usize>(),"completed_inodes":done,"complete":done==all.len(),"prepare_seconds":prepare_s,"apply_seconds":apply_s,"restore_seconds":restore_s,"wall_seconds":started.elapsed().as_secs_f64(),"classes":classes,"actual_attribute":"security.selinux","every_attempt_restored":true,"includes_actual_durable_preimage_syncfs_readback":true,"includes_normal_matcher_or_authority_freeze":false,"production_qualified":false});
    crate::boot_files::write_new(
        &base.join("SCALE-RESULT.json"),
        &serde_json::to_vec_pretty(&result)?,
        0o400,
    )?;
    File::open(base)?.sync_all()?;
    eprintln!("{}", serde_json::to_string(&result)?);
    Ok(())
}
