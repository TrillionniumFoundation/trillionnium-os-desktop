//! New normal software admission while the returned first-once pair stays held.
//! This never reconstructs OriginalQualificationAuthority/OriginalRetirement.
//! It does not copy, relabel, mount or open a private image for writing.
use super::{
    cell,
    materials::{self, Guard},
    owner::SealedInput,
    working_grub::WorkingGrubPreimage,
    working_material_policy::{CurrentPublicMaterials, PublicMaterialInputs},
    working_qualification::{PreparedWorkingCopyObservation, ReturnedWorkingCopyObservation},
};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    boot_owned_evidence::WorkingOwnedObservation,
    boot_runtime::LabelTools,
    cold_original_data::labels::OriginalLabelSources,
    cold_original_once_recovery::contract as c,
    ensure, fs,
    model::Identity,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    fs::File,
    path::{Path, PathBuf},
};

const BASE: &str = "/var/lib/droidloom-qualification";
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Plan {
    schema: String,
    first_once_candidate: String,
    candidate_id: String,
    original_boot_id: String,
    normal_producer: FilePin,
    prepared_initramfs: FilePin,
    owned_verification_input: FilePin,
    public_materials: PublicMaterialInputs,
    original_ext4_metadata: FilePin,
    label_tools: LabelTools,
}
fn validate_plan(plan: &Plan) -> Result<()> {
    ensure(
        plan.schema == "droidloom.working-qualification-material-plan.v1"
            && fs::valid_digest(&plan.first_once_candidate)
            && fs::valid_digest(&plan.candidate_id)
            && plan.first_once_candidate != plan.candidate_id
            && c::uuid(&plan.original_boot_id),
        "working qualification requires separate first-once and new normal candidate identities",
    )
}
fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value[key]
        .as_str()
        .ok_or_else(|| format!("new normal source lacks {key}").into())
}
fn save(path: &Path, value: &Value) -> Result<FilePin> {
    let mut body = serde_json::to_vec_pretty(value)?;
    body.push(b'\n');
    ensure(
        body.len() <= 128 * 1024 * 1024,
        "bounded working admission record required",
    )?;
    files::write_new(path, &body, 0o400)?;
    File::open(path.parent().ok_or("working record parent absent")?)?.sync_all()?;
    let pin = files::pin_file(path)?;
    SealedInput::open(&pin)?;
    Ok(pin)
}
fn same_work(before: &Identity, actual: &Identity) -> bool {
    (before.dev, before.ino, before.mode, before.uid, before.gid)
        == (actual.dev, actual.ino, actual.mode, actual.uid, actual.gid)
        && actual.mode == 0o40700
        && actual.uid == 0
        && actual.gid == 0
}

/// Actual cold resources, current public inputs, fresh H2 normal sources and the
/// freshly rerun ended-guest verifier stay owned by this one preparation.
/// Serialized receipts describe these facts but cannot construct this type.
pub(super) struct WorkingQualificationMaterials {
    returned: PreparedWorkingCopyObservation,
    public_materials: CurrentPublicMaterials,
    sources: OriginalLabelSources,
    fresh_owned: WorkingOwnedObservation,
    guards: Vec<Guard>,
    input: SealedInput,
    original_cell: Guard,
    grub: WorkingGrubPreimage,
    work: PathBuf,
    work_fd: File,
    work_identity: Identity,
    candidate: String,
    report: SealedInput,
    intent: SealedInput,
    records: Vec<SealedInput>,
}
impl WorkingQualificationMaterials {
    pub(super) fn admit(input: &FilePin) -> Result<Self> {
        let input_guard = SealedInput::open(input)?;
        let plan: Plan = serde_json::from_slice(&input_guard.read()?)?;
        validate_plan(&plan)?;
        // The historical factory obtains the actual original owner and its four
        // locks. No second lock open and no old live authority is attempted.
        let returned = ReturnedWorkingCopyObservation::observe(&plan.first_once_candidate)?;
        ensure(
            returned.history().current_boot_id() == plan.original_boot_id,
            "working plan does not name this actual returned original boot",
        )?;
        let public_materials = CurrentPublicMaterials::admit(&plan.public_materials)?;
        let mut guards = Vec::new();
        for pin in [
            &plan.normal_producer,
            &plan.prepared_initramfs,
            &plan.owned_verification_input,
            &plan.original_ext4_metadata,
        ] {
            guards.push(Guard::open(pin)?);
        }
        let actual_exe = File::open("/proc/self/exe")?;
        ensure(
            fs::stat(&actual_exe)? == *guards[0].identity()
                && fs::hash(&actual_exe)? == plan.normal_producer.sha256,
            "working preparation is not executing its admitted normal producer",
        )?;
        returned.guard()?;
        let cold_clone = returned.history().retained_cold_clone()?;
        let cold_guard = Guard::open(&cold_clone)?;
        let (returned, sources) = returned.prepare_normal_sources(
            &plan.candidate_id,
            &plan.prepared_initramfs,
            &plan.label_tools,
        )?;
        let work = returned.work().to_owned();
        let work_fd = returned.work_file().try_clone()?;
        let work_identity = fs::stat(&work_fd)?;
        returned.guard()?;
        let fresh_owned = crate::boot_owned_evidence::verify_for_working_qualification(
            &plan.owned_verification_input,
            &work.join("OWNED-VERIFY-INPUTS.json"),
            &work_fd,
        )?;
        materials::compare_working_candidates(
            &plan.candidate_id,
            &sources,
            &fresh_owned,
            &plan.normal_producer,
        )?;
        let normal = sources.fresh_initramfs_report();
        let historical = returned.history().summary();
        ensure(
            normal["host_source_commit"] != historical["historical_host_source_commit"],
            "the new qualification cannot claim the first once's source as H2",
        )?;
        let (mac_receipt, mac_files) =
            materials::normal_mac(&sources, fresh_owned.report(), &work, &mut guards)?;
        let (persistent, ext4_readback) = materials::original_ext4_from_sources(
            &plan.original_ext4_metadata,
            &cold_clone,
            &work,
        )?;
        let actual_cell = files::pin_file(Path::new("/etc/droidloom/cell.json"))?;
        let original_cell = Guard::open(&actual_cell)?;
        let cell_copy = work.join("ORIGINAL-CELL.json");
        files::copy_pin(&actual_cell, &cell_copy, 0o400)?;
        let cell_copy_pin = files::pin_file(&cell_copy)?;
        ensure(
            cell_copy_pin.bytes == actual_cell.bytes && cell_copy_pin.sha256 == actual_cell.sha256,
            "new working preparation did not preserve the current original cell",
        )?;
        let normal_host_release =
            materials::selected_host_release(sources.source_pin(), normal, fresh_owned.report())?;
        let normal_materials = &normal["normal_materials"];
        let derived = cell::derive_original(
            &files::read_pin(&cell_copy_pin, 1024 * 1024)?,
            text(normal_materials, "cohort_sha256")?,
            text(normal_materials, "runtime_sha256")?,
            &persistent,
            &normal_host_release,
        )?;
        files::write_new(&work.join("CANDIDATE-CELL.json"), &derived.cell, 0o400)?;
        files::write_new(&work.join("SELECTION.json"), &derived.selection, 0o400)?;
        let new_cell = files::pin_file(&work.join("CANDIDATE-CELL.json"))?;
        let selection = files::pin_file(&work.join("SELECTION.json"))?;
        let grub =
            WorkingGrubPreimage::capture(&returned, &sources, &plan.candidate_id, input, &work)?;
        returned.guard()?;
        sources.revalidate()?;
        fresh_owned.revalidate()?;
        public_materials.revalidate()?;
        cold_guard.revalidate()?;
        original_cell.revalidate()?;
        input_guard.revalidate()?;
        for guard in &guards {
            guard.revalidate()?;
        }
        let actual_pair = returned.summary()?;
        let report = save(
            &work.join("ADMITTED-MATERIALS.json"),
            &json!({
                "schema":"droidloom.working-qualification-admitted-materials.v1",
                "input":input,"candidate_id":plan.candidate_id,
                "first_once_candidate":plan.first_once_candidate,
                "first_once_returned_observation":actual_pair,
                "actual_original_owner":returned.history().current_owner_evidence(),
                "normal_sources":sources.source_pin(),"normal_initramfs":normal,
                "fresh_owned":fresh_owned.report(),"public_materials":public_materials.report(),
                "five_mac_files":mac_receipt,"original_ext4":ext4_readback,
                "historical_cold_clone":cold_clone,"historical_cold_clone_identity":cold_guard.identity(),
                "original_cell":cell_copy_pin,"actual_original_cell":actual_cell,
                "actual_original_cell_identity":original_cell.identity(),
                "candidate_cell":new_cell,"selection":selection,
                "normal_host_release":normal_host_release,"current_original_grub":grub.pin(),
                "preserved_cell_fields":derived.preserved_fields,"changed_cell_fields":derived.changed_fields,
                "retained_sources":guards.iter().map(|g| json!({
                    "source":g.pin(),"identity":g.identity()
                })).collect::<Vec<_>>(),
                "old_retirement_reconstructed":false,"private_images_copied":false,
                "private_images_opened_for_write":false,"labels_applied":false,
                "boot_armed":false,"application_business_accepted":false,"production_ready":false
            }),
        )?;
        let intent = save(
            &work.join("MATERIALS-INTENT.json"),
            &json!({
                "schema":"droidloom.working-qualification-material-intent.v1",
                "candidate_id":plan.candidate_id,"work_directory":work,
                "first_once_candidate":plan.first_once_candidate,
                "first_once_returned_source":historical,
                "original_boot_id":plan.original_boot_id,
                "root_uuid":c::ROOT_UUID,"original_kernel":c::ORIGINAL_KERNEL,"original_entry":c::ORIGINAL_ENTRY,
                "admitted_materials":report,"normal_producer":plan.normal_producer,
                "normal_sources":sources.source_pin(),
                "host_source_commit":normal["host_source_commit"],"host_source_tree":normal["host_source_tree"],
                "original_cell":cell_copy_pin,"candidate_cell":new_cell,"selection":selection,
                "normal_public_release_id":normal_materials["public_release_id"],
                "normal_native_release_id":normal_materials["native_release_id"],
                "current_original_grub":grub.pin(),
                "stage":"normal_software_and_returned_pair_admitted",
                "new_boot_epoch_predeclared":false
            }),
        )?;
        let mut records = mac_files;
        for pin in [
            &cell_copy_pin,
            &new_cell,
            &selection,
            &mac_receipt,
            &ext4_readback,
        ] {
            records.push(SealedInput::open(pin)?);
        }
        guards.push(cold_guard);
        let value = Self {
            returned,
            public_materials,
            sources,
            fresh_owned,
            guards,
            input: input_guard,
            original_cell,
            grub,
            work,
            work_fd,
            work_identity,
            candidate: plan.candidate_id,
            report: SealedInput::open(&report)?,
            intent: SealedInput::open(&intent)?,
            records,
        };
        value.revalidate()?;
        Ok(value)
    }
    pub(super) fn revalidate(&self) -> Result<()> {
        self.returned.guard()?;
        let named = fs::Tree::open(&fs::absolute_string(&self.work)?, 0)?;
        let actual = fs::stat(&self.work_fd)?;
        ensure(
            actual == fs::stat(&named.root)?
                && same_work(&self.work_identity, &actual)
                && self.work
                    == Path::new(BASE).join(format!("working-qualification-{}", self.candidate)),
            "working qualification lost its actual private work inode",
        )?;
        self.input.revalidate()?;
        self.sources.revalidate_custody()?;
        self.fresh_owned.revalidate()?;
        self.public_materials.revalidate()?;
        self.original_cell.revalidate()?;
        self.grub.revalidate()?;
        for guard in &self.guards {
            guard.revalidate()?;
        }
        for record in &self.records {
            record.revalidate()?;
        }
        self.report.revalidate()?;
        self.intent.revalidate()?;
        self.returned.guard()
    }
    pub(super) fn recovery_directory(&self) -> Result<PathBuf> {
        self.revalidate()?;
        self.returned.recovery_directory(&self.candidate)
    }
    pub(super) fn prepare_boot_recovery(&mut self, input: &FilePin) -> Result<FilePin> {
        self.revalidate()?;
        let receipt = self.returned.prepare_recovery(&self.candidate, input)?;
        self.revalidate()?;
        Ok(receipt)
    }
    pub(super) fn candidate(&self) -> &str {
        &self.candidate
    }
    pub(super) fn work(&self) -> &Path {
        &self.work
    }
    pub(super) fn intent(&self) -> &FilePin {
        self.intent.pin()
    }
    pub(super) fn report(&self) -> &FilePin {
        self.report.pin()
    }
}
