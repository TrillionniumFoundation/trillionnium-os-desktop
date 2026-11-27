//! Install the admitted third-party material through the actual normal PM
//! session before producing the physical plan. GSI packages are observed only;
//! Meituan's separate signer/data migration cannot borrow this update route.
use super::{
    FilePin, physical_gate_roster as roster,
    runtime_identity::{self, VerifiedMaterialBatch},
};
use droidloom_supervisor::{
    control::{
        ActualApplicationObservation, MainCustodyObservation, NativeApplicationInspector,
        WorkingApkPin, install_working_public_apks, working_system_package,
    },
    physical_qualification_channel::WorkingQualificationOwner,
};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Component, Path},
};

const MEITUAN: &str = "com.sankuai.meituan.takeoutnew";
type Result<T> = std::result::Result<T, String>;
pub(super) struct PreparedInstallation {
    pub(super) observations: Vec<ActualApplicationObservation>,
    pub(super) report: Value,
    pub(super) blockers: Vec<String>,
}
fn image_path(path: &str) -> bool {
    let p = Path::new(path);
    p.is_absolute()
        && !p
            .components()
            .any(|c| matches!(c, Component::ParentDir | Component::CurDir))
        && ["/system", "/system_ext", "/product", "/vendor", "/odm"]
            .iter()
            .any(|root| p.starts_with(root))
}
fn observe(
    owner: &WorkingQualificationOwner,
    inspector: &mut NativeApplicationInspector,
    main: &MainCustodyObservation,
    package: &str,
) -> Result<ActualApplicationObservation> {
    owner.compare_preparation_main(main)?;
    let actual = inspector
        .inspect_observed_until(package, 0, owner.preparation_deadline())
        .map_err(|e| e.to_string())?;
    owner.compare_preparation_main(main)?;
    if actual.facts().epoch != main.facts().epoch {
        return Err("working installation PM observation belongs to another Main epoch".into());
    }
    Ok(actual)
}
fn exact_row(
    batch: &VerifiedMaterialBatch,
    actual: &ActualApplicationObservation,
    kind: &str,
) -> Result<Value> {
    let facts = actual.facts();
    let source = batch.source(&facts.package)?;
    Ok(json!({"package":facts.package,"mode":kind,"uid":facts.uid,
        "version_code":facts.version_code,"version_name_from_verified_apk":source.version_name,
        "complete_installed_apks":facts.apks,
        "signers_from_identical_sdk_verified_apks":source.signers,
        "installed_target_identity_verified":true,"application_accepted":false}))
}
fn emit(row: &Value) {
    eprintln!("droidloom-working-install-readback {row}");
}
pub(super) fn prepare(
    owner: &WorkingQualificationOwner,
    inspector: &mut NativeApplicationInspector,
    main: &MainCustodyObservation,
    selection: &FilePin,
    signature: &FilePin,
) -> Result<PreparedInstallation> {
    owner.compare_preparation_main(main)?;
    if selection.bytes != roster::CURRENT_SELECTION_BYTES
        || selection.sha256 != roster::CURRENT_SELECTION_SHA256
    {
        return Err("working installer requires the exact current compiled material batch".into());
    }
    let batch = runtime_identity::admit_source_materials(selection, signature)?
        .ok_or("current installation materials lack source admission")?;
    let expected: BTreeSet<_> = roster::PACKAGES.iter().map(|p| p.package).collect();
    if batch.packages() != expected {
        return Err("working installer requires the complete current 39-package roster".into());
    }
    let mut system_count = 0;
    let mut third_party_count = 0;
    for package in &expected {
        let source = batch.source(package)?;
        if working_system_package(package) {
            if source.role != "system" {
                return Err("GSI package role differs from compiled policy".into());
            }
            system_count += 1;
        } else {
            if source.role != "third_party" {
                return Err("third-party package role differs from compiled policy".into());
            }
            third_party_count += 1;
        }
    }
    if system_count != 10 || third_party_count != 29 {
        return Err("working GSI/third-party material split differs".into());
    }
    let mut observations = BTreeMap::new();
    let mut rows = Vec::new();
    // Validate the complete ten-package GSI set before authorizing any update.
    for fixed in roster::PACKAGES
        .iter()
        .filter(|p| working_system_package(p.package))
    {
        batch.revalidate()?;
        let actual = observe(owner, inspector, main, fixed.package)?;
        if !batch.is_current(fixed.package, &main.facts().epoch, actual.facts())?
            || actual.facts().apks.iter().any(|a| !image_path(&a.path))
        {
            return Err(format!(
                "{} differs from the complete admitted GSI; individual PM replacement is forbidden",
                fixed.package
            ));
        }
        let row = exact_row(&batch, &actual, "same_actual_main_gsi")?;
        emit(&row);
        rows.push(row);
        observations.insert(fixed.package.to_owned(), actual);
    }
    let anchor = observations
        .get("com.android.calendar")
        .ok_or("actual GSI inventory anchor absent")?;
    let inventory = inspector
        .observe_user_zero_package_inventory_until(main, anchor, owner.preparation_deadline())
        .map_err(|e| e.to_string())?;
    owner.compare_preparation_main(main)?;
    let initial_uids: BTreeMap<_, _> = inventory
        .facts()
        .records
        .iter()
        .map(|r| (r.package.clone(), r.uid))
        .collect();
    let mut committed = 0usize;
    let mut blockers = Vec::new();
    for fixed in roster::PACKAGES
        .iter()
        .filter(|p| !working_system_package(p.package))
    {
        batch.revalidate()?;
        owner.compare_preparation_main(main)?;
        let prior_uid = initial_uids.get(fixed.package).copied();
        let prior = match prior_uid {
            Some(uid) => {
                let actual = observe(owner, inspector, main, fixed.package)?;
                if actual.facts().uid != uid {
                    return Err(
                        "actual package UID changed after the complete initial inventory".into(),
                    );
                }
                Some(actual)
            }
            None => None,
        };
        let current = prior
            .as_ref()
            .map(|a| batch.is_current(fixed.package, &main.facts().epoch, a.facts()))
            .transpose()?
            .unwrap_or(false);
        if current {
            let actual = prior.ok_or("actual current observation absent")?;
            let row = exact_row(&batch, &actual, "already_current")?;
            emit(&row);
            rows.push(row);
            observations.insert(fixed.package.to_owned(), actual);
            continue;
        }
        if fixed.package == MEITUAN {
            let anchor=observations.get("com.android.calendar").ok_or("actual GSI inventory anchor absent")?;
            let operation=droidloom_supervisor::control::reinstall_retained_meituan(
                owner,inspector,main,anchor,prior.as_ref()).map_err(|e|e.to_string())?;
            batch.revalidate()?;
            let actual=observe(owner,inspector,main,fixed.package)?;
            if !batch.is_current(fixed.package,&main.facts().epoch,actual.facts())?{
                return Err("Meituan mechanical replacement did not yield the complete SDK-admitted current APK identity".into());
            }
            let mut row=exact_row(&batch,&actual,"retained_original_standard_reinstall")?;
            row["initial_uid"]=json!(prior_uid);
            row["retained_mechanical_operation"]=operation;
            row["original_data_migration_accepted"]=json!(false);
            row["account_login_accepted"]=json!(false);
            emit(&row);rows.push(row);observations.insert(fixed.package.to_owned(),actual);committed+=1;
            continue;
        }
        let source = batch.source(fixed.package)?;
        let mut pins = source
            .apks
            .iter()
            .map(|a| WorkingApkPin {
                bytes: a.bytes,
                sha256: a.sha256.clone(),
                manifest_split: a.manifest_split.clone(),
            })
            .collect::<Vec<_>>();
        pins.sort_by(|a, b| a.manifest_split.cmp(&b.manifest_split));
        let session = install_working_public_apks(owner, inspector, main, fixed.package, &pins)
            .map_err(|e| e.to_string())?;
        committed += 1;
        batch.revalidate()?;
        if owner.preparation_deadline().saturating_duration_since(std::time::Instant::now())
            < std::time::Duration::from_secs(
                droidloom_supervisor::physical_qualification_channel::budget::APPLICATION_INSTALL_INSPECT_SECONDS,
            ) {
            return Err("atomic session completed but the original complete-readback window expired; no automatic retry".into());
        }
        let actual = observe(owner, inspector, main, fixed.package)?;
        if prior_uid.is_some_and(|uid| uid != actual.facts().uid)
            || !batch.is_current(fixed.package, &main.facts().epoch, actual.facts())?
        {
            return Err(format!(
                "{} atomic session completed but its original UID or complete target APK readback differs; no automatic retry",
                fixed.package
            ));
        }
        let mut row = exact_row(&batch, &actual, "atomic_session_and_complete_readback")?;
        row["initial_uid"] = json!(prior_uid);
        row["session"] = session;
        emit(&row);
        rows.push(row);
        observations.insert(fixed.package.to_owned(), actual);
    }
    batch.revalidate()?;
    owner.compare_preparation_main(main)?;
    let observations = roster::PACKAGES
        .iter()
        .filter_map(|p| observations.remove(p.package))
        .collect::<Vec<_>>();
    Ok(PreparedInstallation {
        report: json!({"schema":"droidloom.working-current-application-preparation.v1",
            "selection":selection,"signature_receipt":signature,"epoch":main.facts().epoch,
            "same_complete_actual_main_required":true,"system_packages_from_gsi_verified":system_count,
            "third_party_packages":third_party_count,"atomic_sessions_confirmed":committed,
            "current_packages_verified":rows.iter().filter(|r|r["installed_target_identity_verified"]==true).count(),
            "applications":rows,"blockers":blockers,"original_data_migration_accepted":false,
            "application_accepted":false,"production_ready":false}),
        observations,
        blockers,
    })
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn system_readback_requires_an_image_path_not_a_data_update_or_traversal() {
        for good in [
            "/system/priv-app/Calendar/Calendar.apk",
            "/system_ext/priv-app/Settings/Settings.apk",
            "/product/app/Native/base.apk",
        ] {
            assert!(image_path(good));
        }
        for bad in [
            "/data/app/native/base.apk",
            "/system-other/base.apk",
            "/system/../data/app/base.apk",
            "system/app/base.apk",
        ] {
            assert!(!image_path(bad));
        }
    }
}
