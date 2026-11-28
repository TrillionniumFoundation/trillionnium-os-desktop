//! Complete source-admitted runtime preparation in the actual working child.
//! Installed comparison documents never supply Main or application authority.
use super::*;
use std::time::Instant;
use droidloom_supervisor::control::{
    ActualApplicationObservation, ActualImageApplicationObservation,
    NativeApplicationInspector, MainCustodyObservation,
    physical_qualification_channel::{WorkingPreparationChannel, WorkingPreparationDocument},
};
use droidloom_update::working_preparation_materials::{
    PreparationMaterial as Material, WorkingPreparationMaterials,
};

struct ActualPreparationClient<'a> {
    inspector: &'a mut NativeApplicationInspector,
    main: &'a MainCustodyObservation,
    end: Instant,
    observations: Vec<(ActualApplicationObservation, Option<ActualImageApplicationObservation>)>,
}
impl PreparationClient for ActualPreparationClient<'_> {
    fn catalog(&mut self, user: u32, epoch: &RuntimeEpoch) -> Result<Vec<AndroidApplication>, String> {
        if user != 0 || epoch != &self.main.facts().epoch {
            return Err("normal preparation catalog must borrow this actual user-zero Main".into());
        }
        self.inspector.list_applications_for_main_until(self.main, self.end)
            .map_err(|e| e.to_string())
    }
    fn inspect(&mut self, package: &str, user: u32) -> Result<ApplicationInspection, String> {
        if user != 0 || !super::super::physical_gate_roster::PACKAGES.iter().any(|r| r.package == package) {
            return Err("normal preparation PM request is outside the exact compiled roster".into());
        }
        let (application, image) = if package == "com.android.gallery3d" {
            let (application, image) = self.inspector.inspect_gallery_observed_until(self.end)
                .map_err(|e| e.to_string())?;
            self.inspector.require_image_application_local(self.main, &application, &image, self.end)
                .map_err(|e| e.to_string())?;
            (application, Some(image))
        } else {
            (self.inspector.inspect_observed_until(package, user, self.end)
                .map_err(|e| e.to_string())?, None)
        };
        self.inspector.require_application_local(self.main, &application, self.end)
            .map_err(|e| e.to_string())?;
        let facts = application.facts().clone();
        self.observations.push((application, image));
        Ok(facts)
    }
}

pub(crate) struct WorkingRuntimePreparation {
    report: PreparationReport,
    observations: Vec<(ActualApplicationObservation, Option<ActualImageApplicationObservation>)>,
}
impl WorkingRuntimePreparation {
    pub(crate) fn guard(&self, channel: &mut WorkingPreparationChannel) -> Result<(), String> {
        channel.guard()?;
        let end = channel.deadline();
        let (inspector, main) = channel.observations();
        for (application, image) in &self.observations {
            inspector.require_application_local(main, application, end).map_err(|e| e.to_string())?;
            if let Some(image) = image {
                inspector.require_image_application_local(main, application, image, end)
                    .map_err(|e| e.to_string())?;
            }
        }
        Ok(())
    }
    pub(crate) fn report_bytes(&self) -> Result<Vec<u8>, String> {
        json_bytes(&serde_json::json!({
            "schema":"droidloom.working-runtime-preparation.v1",
            "preparation":self.report,
            "actual_image_observations":self.observations.iter().filter_map(|(_,i)|i.as_ref())
                .map(|i|i.facts()).collect::<Vec<_>>(),
            "image_observation_semantics":"completed normal whole-image byte bookends; original image owner stays in the broker",
            "application_gate_credit":false,"production_ready":false
        }))
    }
    pub(crate) fn runtime_plan(&self) -> Result<RuntimePlan, String> {
        if !self.report.bindings_complete || self.report.blocked_applications != 0
            || self.report.selected_applications != super::super::physical_gate_roster::PACKAGE_COUNT
            || self.report.app_launches != 0 || self.report.app_installs != 0
            || self.report.accepted_applications != 0 || self.report.runtime_qualified
            || self.report.production_ready
        {
            return Err("actual normal source/PM preparation retains blocked rows; no complete PLAN emitted".into());
        }
        let mut runtime = self.report.runtime_plan.clone();
        let (selection, _) = leaf_routes::compiled_release_sources();
        leaf_routes::validate_selection(&selection)?;
        runtime.preparation_selection = Some(selection);
        let _held_materials = runtime_identity::admit_plan(&runtime)?
            .ok_or("normal prepared roster is absent from the compiled material admission table")?;
        Ok(runtime)
    }
}

fn from_reference(value: Value) -> Result<FilePin, String> {
    serde_json::from_value(value).map_err(|e| e.to_string())
}
fn json_bytes<T: Serialize>(value: &T) -> Result<Vec<u8>, String> {
    let mut raw = serde_json::to_vec_pretty(value).map_err(|e| e.to_string())?;
    raw.push(b'\n');
    Ok(raw)
}
fn fixed_material(materials: &WorkingPreparationMaterials, kind: Material) -> Result<FilePin, String> {
    from_reference(materials.reference(kind).map_err(|e| e.to_string())?)
}

/// The installed source documents, actual private child and held Main determine
/// every input. Failures retain the unchanged original complete blocked roster.
pub(crate) fn prepare_working(
    channel: &mut WorkingPreparationChannel,
    materials: &WorkingPreparationMaterials,
) -> Result<WorkingRuntimePreparation, String> {
    channel.guard()?;
    materials.guard().map_err(|e| e.to_string())?;
    let selection: StaticSelection = serde_json::from_slice(
        materials.bytes(Material::Selection).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    validate_selection(&selection, super::super::physical_gate_roster::PACKAGE_COUNT)?;
    let requested = selection.applications.iter().map(|r|r.package.as_str()).collect::<BTreeSet<_>>();
    let compiled = super::super::physical_gate_roster::PACKAGES.iter().map(|r|r.package).collect::<BTreeSet<_>>();
    if requested != compiled { return Err("normal preparation source roster differs".into()); }
    let gates: GateRegistry = serde_json::from_slice(
        materials.bytes(Material::GateRegistry).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    for application in &selection.applications {
        if !gates.packages.contains_key(&application.package) {
            return Err(format!("normal gate registry omits {}", application.package));
        }
    }
    let main_body = json_bytes(&serde_json::json!({
        "schema":"droidloom.working-main-preparation-comparison.v1",
        "actual_main":channel.main().facts(),"source_publication":channel.source_publication(),
        "comparison_only":true,"application_gate_credit":false,"production_ready":false
    }))?;
    let main = from_reference(channel.write_document(WorkingPreparationDocument::Main, &main_body)?)?;
    let intent = PreparationIntent {
        schema:1, selection:fixed_material(materials, Material::Selection)?,
        source_receipt:fixed_material(materials, Material::SignatureReceipt)?,
        main_qualification:main, expected_epoch:channel.main().facts().epoch.clone(),
        gate_registry:fixed_material(materials, Material::GateRegistry)?,
        specification:from_reference(channel.cell_specification()?)?, android_user:0,
    };
    let intent_pin = from_reference(channel.write_document(
        WorkingPreparationDocument::Intent, &json_bytes(&intent)?)?)?;
    let end = channel.deadline();
    let (report, observations) = {
        let (inspector, main) = channel.observations();
        let mut client = ActualPreparationClient { inspector, main, end, observations:Vec::new() };
        let report = prepare(&intent, intent_pin, &selection, &gates, &mut client)?;
        client.inspector.revalidate_main_until(client.main, end).map_err(|e| e.to_string())?;
        (report, client.observations)
    };
    materials.guard().map_err(|e| e.to_string())?;
    let value = WorkingRuntimePreparation { report, observations };
    value.guard(channel)?;
    Ok(value)
}
