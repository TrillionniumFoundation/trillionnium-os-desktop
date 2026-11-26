//! Isolated complete public-root scale measurement. Never a physical authority.
use super::*;
use std::{collections::BTreeMap, os::unix::fs::MetadataExt, time::Instant};
const BASE: &str = "/var/lib/droidloom-qualification/original-label-scale-4b91-r4";
const SOURCE: &str = "/var/lib/droidloom-qualification/p4-complete-native-credentials-4b91-r2/root";

#[test]
#[ignore = "root only; exact independent public shadow root; records real SELinux xattr and syncfs costs"]
fn complete_public_shadow_root_split_label_cost() -> Result<()> {
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
    // The actual producer has two separate bounded freezes: initial label
    // publication and later original-boot label restoration. Measure those
    // independently. A batch owns its FDs only until its durable commit;
    // the return phase reopens every target from the real retained WAL.
    let forward_started = Instant::now();
    let members = all.values().cloned().collect::<Vec<_>>();
    let mut originals = Vec::with_capacity(members.len());
    for aliases in &members {
        let held = held_path(&aliases[0])?;
        let before = snapshot(&held)?;
        for alias in aliases {
            ensure(
                snapshot(&held_path(alias)?)? == before,
                "initial complete alias snapshot differs",
            )?;
            let md = std::fs::symlink_metadata(Path::new(SOURCE).join(alias.strip_prefix(&root)?))?;
            ensure(
                (md.dev(), md.ino()) != (before.identity.dev, before.identity.ino),
                "shadow alias shares the original source inode",
            )?;
        }
        originals.push(before);
    }
    let initial_readback_seconds = forward_started.elapsed().as_secs_f64();
    let mut pins = vec![None; members.len()];
    let mut applied = vec![None; members.len()];
    let mut restored = vec![None; members.len()];
    let mut forward_error = None;
    let (mut prepared_s, mut applied_s, mut done) = (0.0, 0.0, 0usize);
    batch::BARRIERS.with(|v| v.set(0));
    for start in (0..members.len()).step_by(BATCH_LIMIT) {
        if forward_started.elapsed().as_secs() >= 600 {
            break;
        }
        let end = (start + BATCH_LIMIT).min(members.len());
        let t = Instant::now();
        let result = (|| -> Result<()> {
            let mut staged = Vec::new();
            let mut batch = RecordBatch::new();
            for ordinal in start..end {
                let held = held_path(&members[ordinal][0])?;
                ensure(
                    snapshot(&held)? == originals[ordinal],
                    "pre-write shadow inode changed",
                )?;
                let dir = records.join(format!("{ordinal:06}"));
                crate::boot_files::private_dir(&dir)?;
                let logical = Path::new("/").join(members[ordinal][0].strip_prefix(&root)?);
                staged.push(DurableAttempt::stage(
                    Records::open(&dir)?,
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
            let attempts = DurableAttempt::seal_preparations(staged, batch)?;
            for (ordinal, attempt) in (start..end).zip(&attempts) {
                pins[ordinal] = Some(attempt.pin.clone());
            }
            prepared_s += t.elapsed().as_secs_f64();
            let t = Instant::now();
            let cores = attempts
                .iter()
                .map(DurableAttempt::apply_uncommitted)
                .collect::<Result<Vec<_>>>()?;
            DurableAttempt::complete_applications(&attempts.iter().collect::<Vec<_>>(), &cores)?;
            for (ordinal, attempt) in (start..end).zip(&attempts) {
                let actual = attempt.readback_uncommitted()?;
                actual.revalidate()?;
                let after = snapshot(&held_path(&members[ordinal][0])?)?;
                for alias in &members[ordinal] {
                    ensure(
                        snapshot(&held_path(alias)?)? == after,
                        "forward complete alias differs",
                    )?;
                }
                applied[ordinal] = Some(after);
                done += 1;
            }
            applied_s += t.elapsed().as_secs_f64();
            Ok(())
        })();
        if let Err(e) = result {
            forward_error = Some(e.to_string());
            break;
        }
        if done / 1000 != start / 1000 || done == members.len() {
            eprintln!(
                "LABEL_SPLIT_FORWARD completed={done} total={} wall_seconds={:.3} prepare={prepared_s:.3} apply={applied_s:.3}",
                members.len(),
                forward_started.elapsed().as_secs_f64()
            );
        }
    }
    let final_forward = Instant::now();
    for (ordinal, aliases) in members.iter().enumerate() {
        if forward_error.is_some() && pins[ordinal].is_some() && applied[ordinal].is_none() {
            continue;
        }
        let expected = applied[ordinal].as_ref().unwrap_or(&originals[ordinal]);
        for alias in aliases {
            match held_path(alias).and_then(|fd| snapshot(&fd)) {
                Ok(actual) if actual == *expected => {}
                Ok(_) => {
                    forward_error
                        .get_or_insert_with(|| "forward final complete snapshot differs".into());
                }
                Err(e) => {
                    forward_error.get_or_insert_with(|| e.to_string());
                }
            }
        }
    }
    let forward_final_seconds = final_forward.elapsed().as_secs_f64();
    let forward_seconds = forward_started.elapsed().as_secs_f64();
    let forward_barriers = batch::BARRIERS.with(|v| v.get());
    let forward = json!({"completed_inodes":done,"total_inodes":members.len(),
        "complete":done==members.len() && forward_error.is_none(),
        "error":forward_error,"wall_seconds":forward_seconds,
        "initial_full_readback_seconds":initial_readback_seconds,
        "final_full_readback_seconds":forward_final_seconds,
        "prepare_seconds":prepared_s,"apply_seconds":applied_s,
        "fits_fixed_window":done==members.len() && forward_error.is_none() && forward_seconds<600.0,
        "actual_same_fs_barriers":forward_barriers});
    crate::boot_files::write_new(
        &base.join("FORWARD-RESULT.json"),
        &serde_json::to_vec_pretty(&forward)?,
        0o400,
    )?;
    File::open(base)?.sync_all()?;
    eprintln!(
        "LABEL_SPLIT_FORWARD_RESULT {}",
        serde_json::to_string(&forward)?
    );

    // No target descriptors survive from forward batches. Current preimages,
    // generation handles and the original PREIMAGE/APPLIED bytes are reopened
    // independently, as in a returned original boot. Test-only retirement is
    // explicitly not a production authority or a claim of runtime execution.
    let return_started = Instant::now();
    let mut return_errors = Vec::new();
    for (ordinal, aliases) in members.iter().enumerate() {
        if let Some(expected) = &applied[ordinal] {
            for alias in aliases {
                match held_path(alias).and_then(|fd|snapshot(&fd)) {
                    Ok(actual) if actual==*expected=>{},
                    Ok(_) => return_errors.push(json!({"ordinal":ordinal,"error":"return initial complete readback differs"})),
                    Err(e) => return_errors.push(json!({"ordinal":ordinal,"error":e.to_string()})),
                }
            }
        }
    }
    let return_initial_seconds = return_started.elapsed().as_secs_f64();
    let mut returned = 0usize;
    let mut exceeded_at = None;
    let mut restore_s = 0.0;
    batch::BARRIERS.with(|v| v.set(0));
    for start in (0..members.len()).step_by(BATCH_LIMIT) {
        let end = (start + BATCH_LIMIT).min(members.len());
        if !(start..end).any(|i| pins[i].is_some()) {
            continue;
        }
        if return_started.elapsed().as_secs() >= 600 && exceeded_at.is_none() {
            exceeded_at = Some(returned);
        }
        // If the isolated test exceeds its budget, keep the failure and finish
        // real recovery of every attempted target. This cleanup cannot turn an
        // over-budget result into a passing production window.
        let t = Instant::now();
        let result = (|| -> Result<()> {
            let mut batch = RecordBatch::new();
            let mut pending = Vec::new();
            let mut ordinals = Vec::new();
            for ordinal in start..end {
                let Some(pin) = &pins[ordinal] else {
                    continue;
                };
                let item = records.join(format!("{ordinal:06}"));
                let original = DurableAttempt::load_unclassified(
                    Records::open(&item)?,
                    pin,
                    held_path(&members[ordinal][0])?,
                )?;
                if applied[ordinal].is_none() {
                    original.restore()?;
                    restored[ordinal] = Some(snapshot(&held_path(&members[ordinal][0])?)?);
                    returned += 1;
                    continue;
                }
                original.applied_readback()?.revalidate()?;
                let return_dir = item.join("return");
                crate::boot_files::private_dir(&return_dir)?;
                pending.push(RuntimeRestoreAttempt::stage_exact(
                    original,
                    Records::open(&return_dir)?,
                    &retirement,
                    None,
                    &mut batch,
                )?);
                ordinals.push(ordinal);
            }
            let attempts = RuntimeRestoreAttempt::seal_preparations(pending, batch)?;
            let values = attempts
                .iter()
                .map(RuntimeRestoreAttempt::restore_uncommitted)
                .collect::<Result<Vec<_>>>()?;
            RuntimeRestoreAttempt::complete_restorations(
                &attempts.iter().collect::<Vec<_>>(),
                &values,
            )?;
            for (ordinal, value) in ordinals.into_iter().zip(values) {
                restored[ordinal] = Some(value.core.after);
                returned += 1;
            }
            Ok(())
        })();
        if let Err(e) = result {
            return_errors.push(json!({"first_ordinal":start,"error":e.to_string()}));
            for ordinal in start..end {
                let Some(pin) = &pins[ordinal] else {
                    continue;
                };
                if restored[ordinal].is_some() {
                    continue;
                }
                let cleanup = (|| -> Result<()> {
                    let item = records.join(format!("{ordinal:06}"));
                    let original = DurableAttempt::load_unclassified(
                        Records::open(&item)?,
                        pin,
                        held_path(&members[ordinal][0])?,
                    )?;
                    let ret = item.join("return");
                    if ret.join("CURRENT-PREIMAGE.json").exists() {
                        let r = Records::open(&ret)?;
                        let (_, _, body) = r.read("CURRENT-PREIMAGE.json")?;
                        let pin = FilePin {
                            path: ret.join("CURRENT-PREIMAGE.json"),
                            bytes: body.len() as u64,
                            sha256: fs::digest(&body),
                        };
                        RuntimeRestoreAttempt::reopen(original, r, &pin)?.restore()?;
                    } else {
                        original.restore()?;
                    }
                    restored[ordinal] = Some(snapshot(&held_path(&members[ordinal][0])?)?);
                    returned += 1;
                    Ok(())
                })();
                if let Err(e) = cleanup {
                    return_errors.push(json!({"ordinal":ordinal,"cleanup_error":e.to_string()}));
                }
            }
        }
        restore_s += t.elapsed().as_secs_f64();
        if returned / 1000 != start / 1000 || returned == done {
            eprintln!(
                "LABEL_SPLIT_RETURN restored={returned} attempted={done} wall_seconds={:.3}",
                return_started.elapsed().as_secs_f64()
            );
        }
    }
    let final_return = Instant::now();
    let mut final_errors = Vec::new();
    let mut classes = BTreeMap::<String, usize>::new();
    for (ordinal, aliases) in members.iter().enumerate() {
        let expected = restored[ordinal].as_ref().unwrap_or(&originals[ordinal]);
        let original = &originals[ordinal];
        if expected.attributes != original.attributes
            || expected.handle != original.handle
            || !only_ctime_changed(&original.identity, &expected.identity)
        {
            final_errors.push(json!({"ordinal":ordinal,"error":"restoration changed original unrelated metadata"}));
        }
        for alias in aliases {
            match held_path(alias).and_then(|fd| snapshot(&fd)) {
                Ok(actual) if actual == *expected => {}
                Ok(_) => final_errors.push(
                    json!({"ordinal":ordinal,"path":alias,"error":"complete final alias differs"}),
                ),
                Err(e) => {
                    final_errors.push(json!({"ordinal":ordinal,"path":alias,"error":e.to_string()}))
                }
            }
        }
        *classes
            .entry(format!(
                "{:?}",
                FileType::from_raw_mode(original.identity.mode)
            ))
            .or_default() += 1;
    }
    let final_return_seconds = final_return.elapsed().as_secs_f64();
    let return_seconds = return_started.elapsed().as_secs_f64();
    let attempted = pins.iter().filter(|p| p.is_some()).count();
    let all_restored = returned == attempted && final_errors.is_empty();
    let result = json!({"schema":"droidloom.isolated-public-root-label-split-scale-result.v1",
        "source_manifest":manifest,"shadow":root,"source_plan":plan,"inventory_seconds":inventory_seconds,
        "unique_inodes":members.len(),"logical_paths":members.iter().map(Vec::len).sum::<usize>(),
        "forward":forward,"return":{"restored_inodes":returned,"attempted_inodes":attempted,
            "wall_seconds":return_seconds,"initial_full_readback_seconds":return_initial_seconds,
            "restore_seconds":restore_s,"final_full_readback_seconds":final_return_seconds,
            "deadline_exceeded_after_inodes":exceeded_at,"errors":return_errors,"final_errors":final_errors,
            "actual_same_fs_barriers":batch::BARRIERS.with(|v|v.get()),
            "fits_fixed_window":all_restored && return_errors.is_empty() && return_seconds<600.0},
        "complete":done==members.len() && all_restored && forward_error.is_none() && return_errors.is_empty(),
        "every_attempt_restored":all_restored,"batch_limit":BATCH_LIMIT,"classes":classes,
        "actual_attribute":"security.selinux","forward_fds_released_before_independent_return":true,
        "return_reopens_actual_durable_preimages":true,"includes_actual_durable_preimage_syncfs_readback":true,
        "includes_normal_matcher_or_authority_freeze":false,"production_qualified":false});
    crate::boot_files::write_new(
        &base.join("SCALE-RESULT.json"),
        &serde_json::to_vec_pretty(&result)?,
        0o400,
    )?;
    File::open(base)?.sync_all()?;
    eprintln!("{}", serde_json::to_string(&result)?);
    ensure(
        all_restored,
        "isolated test cleanup left a real restoration error",
    )?;
    Ok(())
}
fn held_path(path: &Path) -> Result<File> {
    Ok(File::from(rustix::fs::open(
        path,
        OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    )?))
}
