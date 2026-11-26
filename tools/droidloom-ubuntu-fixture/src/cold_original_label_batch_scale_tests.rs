//! Isolated complete public-root scale measurement. Never a physical authority.
use super::*;
use std::{collections::BTreeMap, os::unix::fs::MetadataExt, time::Instant};
const BASE: &str = "/var/lib/droidloom-qualification/original-label-scale-4b91-r2";
const SOURCE: &str = "/var/lib/droidloom-qualification/p4-complete-native-credentials-4b91-r2/root";

#[test]
#[ignore = "root only; exact independent public shadow root; records real SELinux xattr and syncfs costs"]
fn complete_public_shadow_root_batch_label_cost() -> Result<()> {
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
    let retirement_path = base.join("SCALE-RETIREMENT.json");
    crate::boot_files::write_new(
        &retirement_path,
        &serde_json::to_vec(&json!({
        "schema":"droidloom.isolated-public-root-label-scale-retirement.v1",
        "source_plan":plan,"production_authority":false,"actual_runtime_occurred":false}))?,
        0o400,
    )?;
    let retirement = crate::boot_files::pin_file(&retirement_path)?;
    let started = Instant::now();
    let (mut prepare_s, mut apply_s, mut restore_s, mut done) = (0.0, 0.0, 0.0, 0usize);
    let mut classes: BTreeMap<String, usize> = BTreeMap::new();
    let members = all.iter().collect::<Vec<_>>();
    let mut restored_snapshots = Vec::new();
    batch::BARRIERS.with(|value| value.set(0));
    for group in members.chunks(BATCH_LIMIT) {
        if started.elapsed().as_secs() >= 600 {
            break;
        }
        let first = done;
        let mut pending = Vec::new();
        let mut batch = RecordBatch::new();
        let mut originals = Vec::new();
        let mut held_recovery = Vec::new();
        let t = Instant::now();
        for (offset, ((dev, ino), aliases)) in group.iter().enumerate() {
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
            for alias in *aliases {
                let fd = File::from(rustix::fs::open(
                    alias,
                    OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                    Mode::empty(),
                )?);
                ensure(
                    snapshot(&fd)? == before,
                    "shadow hardlink alias differs from complete actual before snapshot",
                )?;
            }
            let source_path = Path::new(SOURCE).join(path.strip_prefix(&root)?);
            let source_inode = std::fs::symlink_metadata(&source_path)?;
            ensure(
                (source_inode.dev(), source_inode.ino())
                    != (before.identity.dev, before.identity.ino),
                "shadow target is hardlinked to its original normal source inode",
            )?;
            let ordinal = first + offset;
            let item = records.join(format!("{ordinal:06}"));
            crate::boot_files::private_dir(&item)?;
            let logical = Path::new("/").join(path.strip_prefix(&root)?);
            held_recovery.push(held.try_clone()?);
            originals.push(before);
            pending.push(DurableAttempt::stage(
                Records::open(&item)?,
                held,
                &candidate,
                &plan,
                ordinal.try_into()?,
                &logical,
                b"u:object_r:p4_linux_native_config_t:s0",
                LABEL,
                &mut batch,
            )?);
        }
        let attempts = DurableAttempt::seal_preparations(pending, batch)?;
        prepare_s += t.elapsed().as_secs_f64();
        let source_pins = attempts.iter().map(|a| a.pin.clone()).collect::<Vec<_>>();
        let work = || -> Result<Vec<Snapshot>> {
            let t = Instant::now();
            let cores = attempts
                .iter()
                .map(DurableAttempt::apply_uncommitted)
                .collect::<Result<Vec<_>>>()?;
            let refs = attempts.iter().collect::<Vec<_>>();
            DurableAttempt::complete_applications(&refs, &cores)?;
            for attempt in &attempts {
                attempt.readback_uncommitted()?.revalidate()?;
            }
            apply_s += t.elapsed().as_secs_f64();
            let t = Instant::now();
            let mut pending = Vec::new();
            let mut batch = RecordBatch::new();
            for (offset, attempt) in attempts.into_iter().enumerate() {
                let item = records
                    .join(format!("{:06}", first + offset))
                    .join("return");
                crate::boot_files::private_dir(&item)?;
                pending.push(RuntimeRestoreAttempt::stage_exact(
                    attempt,
                    Records::open(&item)?,
                    &retirement,
                    None,
                    &mut batch,
                )?);
            }
            let attempts = RuntimeRestoreAttempt::seal_preparations(pending, batch)?;
            let provisional = attempts
                .iter()
                .map(RuntimeRestoreAttempt::restore_uncommitted)
                .collect::<Result<Vec<_>>>()?;
            let refs = attempts.iter().collect::<Vec<_>>();
            RuntimeRestoreAttempt::complete_restorations(&refs, &provisional)?;
            restore_s += t.elapsed().as_secs_f64();
            Ok(provisional
                .into_iter()
                .map(|value| value.core.after)
                .collect())
        };
        let after = match work() {
            Ok(after) => after,
            Err(error) => {
                // Even a partial kernel write retains its independent FD and
                // exact original/current WAL. Attempt actual bounded cleanup
                // of every group member before reporting this failed test.
                let mut cleanup = Vec::new();
                for (offset, (held, pin)) in held_recovery.iter().zip(&source_pins).enumerate() {
                    let item = records.join(format!("{:06}", first + offset));
                    let result = (|| -> Result<()> {
                        let original = DurableAttempt::load_unclassified(
                            Records::open(&item)?,
                            pin,
                            held.try_clone()?,
                        )?;
                        let return_path = item.join("return");
                        if return_path.join("CURRENT-PREIMAGE.json").exists() {
                            let now = Records::open(&return_path)?;
                            let (_, _, body) = now.read("CURRENT-PREIMAGE.json")?;
                            let current = FilePin {
                                path: return_path.join("CURRENT-PREIMAGE.json"),
                                bytes: body.len() as u64,
                                sha256: fs::digest(&body),
                            };
                            RuntimeRestoreAttempt::reopen(original, now, &current)?.restore()?;
                        } else {
                            original.restore()?;
                        }
                        Ok(())
                    })();
                    cleanup.push(json!({"ordinal":first+offset,"cleanup_error":result.err().map(|e|e.to_string())}));
                }
                crate::boot_files::write_new(
                    &base.join("SCALE-FAILED.json"),
                    &serde_json::to_vec_pretty(&json!({
                    "schema":"droidloom.isolated-public-root-label-scale-failure.v1","error":error.to_string(),
                    "cleanup":cleanup,"production_qualified":false}))?,
                    0o400,
                )?;
                return Err(error);
            }
        };
        for (offset, (restored, before)) in after.into_iter().zip(originals).enumerate() {
            ensure(
                restored.attributes == before.attributes
                    && restored.handle == before.handle
                    && only_ctime_changed(&before.identity, &restored.identity),
                "shadow restoration changed original unrelated metadata",
            )?;
            for alias in group[offset].1 {
                let fd = File::from(rustix::fs::open(
                    alias,
                    OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                    Mode::empty(),
                )?);
                ensure(
                    snapshot(&fd)? == restored,
                    "complete shadow alias readback differs after group restoration",
                )?;
            }
            *classes
                .entry(format!(
                    "{:?}",
                    FileType::from_raw_mode(before.identity.mode)
                ))
                .or_default() += 1;
            restored_snapshots.push(restored);
            done += 1;
        }
        if done / 1000 != first / 1000 || done == all.len() {
            eprintln!(
                "LABEL_BATCH_SCALE completed={done} total={} wall_seconds={:.3} prepare={prepare_s:.3} apply={apply_s:.3} restore={restore_s:.3}",
                all.len(),
                started.elapsed().as_secs_f64()
            );
        }
        // The next group is never started after the fixed deadline. Every
        // attempted member of this group is already actually restored.
    }
    let final_readback_started = Instant::now();
    for ((_, aliases), expected) in all.iter().take(done).zip(&restored_snapshots) {
        for alias in aliases {
            let held = File::from(rustix::fs::open(
                alias,
                OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                Mode::empty(),
            )?);
            ensure(
                snapshot(&held)? == *expected,
                "complete final shadow root readback changed an earlier restored target",
            )?;
        }
    }
    let final_readback_seconds = final_readback_started.elapsed().as_secs_f64();
    let wall_seconds = started.elapsed().as_secs_f64();
    let result = json!({"schema":"droidloom.isolated-public-root-label-batch-scale-result.v1","source_manifest":manifest,"shadow":root,"source_plan":plan,"inventory_seconds":inventory_seconds,"unique_inodes":all.len(),"logical_paths":all.values().map(Vec::len).sum::<usize>(),"completed_inodes":done,"complete":done==all.len(),"prepare_seconds":prepare_s,"apply_seconds":apply_s,"restore_seconds":restore_s,"wall_seconds":wall_seconds,"final_readback_seconds":final_readback_seconds,"fits_fixed_window":done==all.len() && wall_seconds<600.0,"batch_limit":BATCH_LIMIT,"actual_same_fs_barriers":batch::BARRIERS.with(|v|v.get()),"classes":classes,"actual_attribute":"security.selinux","every_attempt_restored":true,"includes_actual_durable_preimage_syncfs_readback":true,"includes_normal_matcher_or_authority_freeze":false,"production_qualified":false});
    crate::boot_files::write_new(
        &base.join("SCALE-RESULT.json"),
        &serde_json::to_vec_pretty(&result)?,
        0o400,
    )?;
    File::open(base)?.sync_all()?;
    eprintln!("{}", serde_json::to_string(&result)?);
    Ok(())
}
