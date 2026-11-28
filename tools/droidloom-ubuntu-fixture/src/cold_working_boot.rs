//! Normal working-qualification boot material from the live cold successor.
//! It owns the same Returned custody and calls the normal initramfs producer;
//! its serialized report never grants a data exchange, label write, or boot.
use super::{
    materials::Guard, owner::SealedInput, working_materials::WorkingQualificationMaterials,
};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    cold_working_recovery::contract::{
        self as c, WorkingBootSpec, WorkingEarlyConfiguration, WorkingSchedule,
    },
    ensure, fs,
};
use serde::Serialize;
use serde_json::{Value, json};
use std::{fs::File, path::Path};

fn pin(value: &Value) -> Result<FilePin> {
    let p: FilePin = serde_json::from_value(value.clone())?;
    ensure(
        p.bytes > 0 && fs::valid_digest(&p.sha256),
        "normal working source file commitment missing",
    )?;
    Ok(p)
}
fn read(pin: &FilePin) -> Result<Value> {
    Ok(serde_json::from_slice(&files::read_pin(
        pin,
        16 * 1024 * 1024,
    )?)?)
}
fn source(path: &Path, value: &impl Serialize) -> Result<SealedInput> {
    let mut raw = serde_json::to_vec_pretty(value)?;
    raw.push(b'\n');
    ensure(
        raw.len() <= 16 * 1024 * 1024,
        "normal working boot source bound exceeded",
    )?;
    files::write_new(path, &raw, 0o400)?;
    File::open(path.parent().ok_or("normal working source parent absent")?)?.sync_all()?;
    SealedInput::open(&files::pin_file(path)?)
}

fn derive_normal_plan(base: &Value, directory: &Path, recipe: &FilePin) -> Result<Value> {
    ensure(
        base["schema"] == "droidloom.original-host-initramfs-plan.v1"
            && base["recovery_recipe"].is_null(),
        "working recovery requires the actual normal base plan without another boot kind",
    )?;
    let mut plan = base.clone();
    plan["work_directory"] = serde_json::to_value(directory)?;
    plan["recovery_recipe"] = serde_json::to_value(recipe)?;
    Ok(plan)
}

/// This object can only be made by consuming the actual admitted cold materials.
/// It does not reconstruct the first once's live authority or release its locks.
pub(super) struct PreparedWorkingBoot {
    materials: WorkingQualificationMaterials,
    contract: WorkingBootSpec,
    intent: SealedInput,
    early: SealedInput,
    recipe: SealedInput,
    producer_plan: SealedInput,
    normal_prepared: SealedInput,
    initrd: Guard,
    ordinary_initrd: Guard,
    retained_sources: Vec<Guard>,
    report: SealedInput,
}
impl PreparedWorkingBoot {
    pub(super) fn prepare(mut materials: WorkingQualificationMaterials) -> Result<Self> {
        materials.revalidate()?;
        let admitted = read(materials.report())?;
        let material_intent = read(materials.intent())?;
        let producer = pin(&material_intent["normal_producer"])?;
        let mut retained_sources = vec![Guard::open(&producer)?];
        let recovery = WorkingBootSpec {
            schema: "droidloom.working-qualification-boot.v1".into(),
            kind: c::KIND.into(),
            candidate_id: materials.candidate().into(),
            first_once_candidate: material_intent["first_once_candidate"]
                .as_str()
                .ok_or("actual first once candidate absent")?
                .into(),
            helper_bytes: producer.bytes,
            helper_sha256: producer.sha256.clone(),
            kernel_release: c::KERNEL.into(),
            kernel_sha256: c::KERNEL_SHA.into(),
            kernel_config_sha256: c::CONFIG_SHA.into(),
            module_relative: c::MODULE_REL.into(),
            module_bytes: c::MODULE_BYTES,
            module_sha256: c::MODULE_SHA.into(),
            panic_seconds: c::PANIC_SECONDS,
            schedule: WorkingSchedule::selected(),
        };
        recovery.validate()?;
        let intent = source(
            &materials.work().join("BOOT-INTENT.json"),
            &json!({
                "schema":"droidloom.working-qualification-boot-intent.v1","kind":c::KIND,
                "candidate_id":materials.candidate(),"first_once_candidate":recovery.first_once_candidate,
                "material_intent":materials.intent(),"admitted_materials":materials.report(),
                "original_boot_id":material_intent["original_boot_id"],
                "root_uuid":c::ROOT_UUID,"original_kernel":c::ORIGINAL_KERNEL,"original_entry":c::ORIGINAL_ENTRY,
                "host_source_commit":material_intent["host_source_commit"],
                "host_source_tree":material_intent["host_source_tree"],
                "normal_public_release_id":material_intent["normal_public_release_id"],
                "normal_native_release_id":material_intent["normal_native_release_id"],
                "normal_sources":material_intent["normal_sources"],"normal_producer":producer,
                "original_cell":material_intent["original_cell"],"candidate_cell":material_intent["candidate_cell"],
                "selection":material_intent["selection"],"current_original_grub":material_intent["current_original_grub"],
                "recovery":recovery,"same_four_backing_ofds_retained":true,
                "old_live_retirement_reconstructed":false,"boot_armed":false,"production_ready":false
            }),
        )?;
        let early_value = WorkingEarlyConfiguration {
            schema: "droidloom.working-qualification-early.v1".into(),
            intent_sha256: intent.pin().sha256.clone(),
            recovery: recovery.clone(),
        };
        early_value.validate()?;
        let early = source(&materials.work().join("WORKING-EARLY.json"), &early_value)?;
        let recipe = source(
            &materials.work().join("WORKING-RECOVERY-RECIPE.json"),
            &json!({
                "schema":"droidloom.working-qualification-initramfs-recipe.v1",
                "normal_producer":producer,"base_intent":intent.pin(),"early_configuration":early.pin()
            }),
        )?;
        // The plan descends from the actually admitted normal H2 preparation.
        // Only its new create-only output directory and closed recipe input are
        // substituted. Public/native packages, kernel, toolchain and source
        // identity remain under the existing normal producer's complete gates.
        let material_input = pin(&admitted["input"])?;
        retained_sources.push(Guard::open(&material_input)?);
        let original_prepared = pin(&read(&material_input)?["prepared_initramfs"])?;
        retained_sources.push(Guard::open(&original_prepared)?);
        let original_value = read(&original_prepared)?;
        ensure(
            original_value["schema"] == "droidloom.original-host-initramfs-prepared.v1"
                && original_value["recovery_recipe_input"].is_null()
                && original_value["kernel_release"] == c::KERNEL
                && original_value["kernel_sha256"] == c::KERNEL_SHA,
            "ordinary production initrd must be the actual normal base without recovery",
        )?;
        let ordinary_initrd = Guard::open(&pin(&original_value["initrd"])?)?;
        let ordinary_materials = pin(&original_value["normal_materials"])?;
        retained_sources.push(Guard::open(&ordinary_materials)?);
        ensure(
            read(&ordinary_materials)? == admitted["normal_initramfs"]["normal_materials"],
            "ordinary initrd changed the actual normal material family",
        )?;
        let initial = pin(&original_value["input"])?;
        retained_sources.push(Guard::open(&initial)?);
        let base_plan = read(&initial)?;
        let directory = materials.recovery_directory()?;
        let plan = derive_normal_plan(&base_plan, &directory, recipe.pin())?;
        let producer_plan = source(&materials.work().join("RECOVERY-PRODUCER.json"), &plan)?;
        materials.revalidate()?;
        for guard in &retained_sources {
            guard.revalidate()?;
        }
        let normal = materials.prepare_boot_recovery(producer_plan.pin())?;
        let normal_prepared = SealedInput::open(&normal)?;
        let actual: Value = serde_json::from_slice(&normal_prepared.read()?)?;
        ensure(
            actual["input"] == serde_json::to_value(producer_plan.pin())?
                && actual["recovery_recipe_input"] == serde_json::to_value(recipe.pin())?
                && actual["recovery_image_readback"]["schema"]
                    == "droidloom.working-qualification-recovery-image-readback.v1",
            "actual normal working image lost its exact input or kind",
        )?;
        let actual_materials_pin = pin(&actual["normal_materials"])?;
        let actual_materials = read(&actual_materials_pin)?;
        ensure(
            actual_materials == admitted["normal_initramfs"]["normal_materials"],
            "normal recovery rebuild changed the actually admitted H2 material family",
        )?;
        retained_sources.push(Guard::open(&actual_materials_pin)?);
        let initrd_pin = pin(&actual["initrd"])?;
        ensure(
            initrd_pin.path == directory.join("build/initrd.img"),
            "normal working recovery output left its one owned private build",
        )?;
        let initrd = Guard::open(&initrd_pin)?;
        materials.revalidate()?;
        for guard in &retained_sources {
            guard.revalidate()?;
        }
        let report = source(
            &materials.work().join("WORKING-RECOVERY-PREPARED.json"),
            &json!({
                "schema":"droidloom.working-qualification-recovery-prepared.v1","kind":c::KIND,
                "candidate_id":materials.candidate(),"first_once_candidate":recovery.first_once_candidate,
                "material_intent":materials.intent(),"admitted_materials":materials.report(),
                "boot_intent":intent.pin(),"early_configuration":early.pin(),"recovery_recipe":recipe.pin(),
                "normal_base_plan":initial,"normal_producer_plan":producer_plan.pin(),
                "normal_prepared":normal,"initrd":initrd_pin,"recovery":recovery,
                "ordinary_normal_prepared":original_prepared,"ordinary_initrd":ordinary_initrd.pin(),
                "same_four_backing_ofds_retained":true,"cold_parent_stage_completed":true,
                "runtime_parent_freeze":false,"data_exchanged":false,"labels_applied":false,
                "boot_armed":false,"application_business_accepted":false,"production_ready":false
            }),
        )?;
        let value = Self {
            materials,
            contract: recovery,
            intent,
            early,
            recipe,
            producer_plan,
            normal_prepared,
            initrd,
            ordinary_initrd,
            retained_sources,
            report,
        };
        value.revalidate()?;
        Ok(value)
    }
    pub(super) fn revalidate(&self) -> Result<()> {
        self.materials.revalidate()?;
        self.contract.validate()?;
        for value in [
            &self.intent,
            &self.early,
            &self.recipe,
            &self.producer_plan,
            &self.normal_prepared,
            &self.report,
        ] {
            value.revalidate()?;
        }
        self.initrd.revalidate()?;
        self.ordinary_initrd.revalidate()?;
        for guard in &self.retained_sources {
            guard.revalidate()?;
        }
        self.materials.revalidate()
    }
    pub(super) fn materials(&self) -> &WorkingQualificationMaterials {
        &self.materials
    }
    pub(super) fn report(&self) -> &FilePin {
        self.report.pin()
    }
    pub(super) fn intent(&self) -> &FilePin {
        self.intent.pin()
    }
    pub(super) fn early(&self) -> &FilePin {
        self.early.pin()
    }
    pub(super) fn ordinary_initrd(&self) -> &FilePin {
        self.ordinary_initrd.pin()
    }
    pub(super) fn recovery(&self) -> &WorkingBootSpec {
        &self.contract
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn working_normal_plan_preserves_packages_and_rejects_prior_recovery() -> Result<()> {
        let pin = FilePin {
            path: "/root/normal-source".into(),
            bytes: 1000,
            sha256: "a".repeat(64),
        };
        let base = json!({"schema":"droidloom.original-host-initramfs-plan.v1",
            "work_directory":"/var/lib/droidloom-qualification/original-initramfs-base",
            "public_release":pin,"native_release":pin,"native_release_id":"b".repeat(64),
            "target_preflight":pin});
        let expected =
            Path::new("/var/lib/droidloom-qualification/original-initramfs-working-example");
        let output = derive_normal_plan(&base, expected, &pin)?;
        assert_eq!(output["work_directory"], serde_json::to_value(expected)?);
        assert_eq!(output["recovery_recipe"], serde_json::to_value(&pin)?);
        let mut reduced = output;
        reduced.as_object_mut().unwrap().remove("recovery_recipe");
        reduced["work_directory"] = base["work_directory"].clone();
        assert_eq!(reduced, base);
        let mut other = base.clone();
        other["recovery_recipe"] = serde_json::to_value(&pin)?;
        assert!(derive_normal_plan(&other, expected, &pin).is_err());
        other = base;
        other["schema"] = json!("caller-initramfs");
        assert!(derive_normal_plan(&other, expected, &pin).is_err());
        Ok(())
    }
}

/// Actual normal recovery sources after the mutable targets are separated.
pub(super) struct WorkingBootSources {
    contract: WorkingBootSpec,
    intent: SealedInput,
    early: SealedInput,
    recipe: SealedInput,
    producer_plan: SealedInput,
    normal_prepared: SealedInput,
    initrd: Guard,
    ordinary_initrd: Guard,
    retained_sources: Vec<Guard>,
    report: SealedInput,
}
impl WorkingBootSources {
    pub(super) fn revalidate_label_custody(&self) -> Result<()> {
        self.contract.validate()?;
        for value in [
            &self.intent,
            &self.early,
            &self.recipe,
            &self.producer_plan,
            &self.normal_prepared,
            &self.report,
        ] {
            value.revalidate_custody()?;
        }
        self.initrd.revalidate_custody()?;
        self.ordinary_initrd.revalidate_custody()?;
        for guard in &self.retained_sources {
            guard.revalidate_custody()?;
        }
        Ok(())
    }

    pub(super) fn revalidate(&self) -> Result<()> {
        self.contract.validate()?;
        for value in [
            &self.intent,
            &self.early,
            &self.recipe,
            &self.producer_plan,
            &self.normal_prepared,
            &self.report,
        ] {
            value.revalidate()?;
        }
        self.initrd.revalidate()?;
        self.ordinary_initrd.revalidate()?;
        for guard in &self.retained_sources {
            guard.revalidate()?;
        }
        Ok(())
    }
    pub(super) fn ordinary_initrd(&self) -> &FilePin {
        self.ordinary_initrd.pin()
    }
    pub(super) fn recovery(&self) -> &WorkingBootSpec {
        &self.contract
    }
    pub(super) fn intent(&self) -> &FilePin {
        self.intent.pin()
    }
    pub(super) fn initrd(&self) -> &FilePin {
        self.initrd.pin()
    }
}
impl PreparedWorkingBoot {
    pub(super) fn into_sources(
        self,
    ) -> Result<(WorkingBootSources, WorkingQualificationMaterials)> {
        self.revalidate()?;
        let Self {
            materials,
            contract,
            intent,
            early,
            recipe,
            producer_plan,
            normal_prepared,
            initrd,
            ordinary_initrd,
            retained_sources,
            report,
        } = self;
        Ok((
            WorkingBootSources {
                contract,
                intent,
                early,
                recipe,
                producer_plan,
                normal_prepared,
                initrd,
                ordinary_initrd,
                retained_sources,
                report,
            },
            materials,
        ))
    }
}
