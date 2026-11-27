//! Source-owned public-material boundary for the separate returned-copy stage.
//! This does not change the first-once r6 contract. The four commitments come
//! from the same compiled applications source table; neither a caller batch name
//! nor an input report can add an admission.
use crate::{
    Result,
    boot_files::FilePin,
    boot_public_apks::{self, VerifiedInputs, VerifiedSourceDocument},
    ensure, fs,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

const ADMISSIONS: &str =
    include_str!("../../../runtime/droidloom-applications/src/runtime_identity_admissions.json");
const CURRENT_BATCH: &str = "p4-public-apk-candidate-4b91-r7";
const MAX_DOCUMENT: u64 = 16 * 1024 * 1024;

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct PublicMaterialInputs {
    pub(super) selection: FilePin,
    pub(super) signature_receipt: FilePin,
    pub(super) normal_import: FilePin,
    pub(super) normal_input_verification: FilePin,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct BytesPin {
    bytes: u64,
    sha256: String,
}
impl BytesPin {
    fn valid(&self) -> bool {
        self.bytes > 0 && self.bytes <= MAX_DOCUMENT && fs::valid_digest(&self.sha256)
    }
    fn matches(&self, pin: &FilePin) -> bool {
        self.bytes == pin.bytes && self.sha256 == pin.sha256
    }
}
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Admission {
    id: String,
    selection: BytesPin,
    signature_receipt: BytesPin,
    normal_import: BytesPin,
    normal_input_verification: BytesPin,
    package_count: usize,
    apk_file_count: usize,
    apk_total_bytes: u64,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Admissions {
    schema: String,
    batches: Vec<Admission>,
}

fn current_admission(source: &str) -> Result<Admission> {
    let values: Admissions = serde_json::from_str(source)?;
    ensure(
        values.schema == "droidloom.application-material-admissions.v1"
            && !values.batches.is_empty()
            && values.batches.len() <= 32,
        "compiled application material table schema or bound differs",
    )?;
    let mut ids = BTreeSet::new();
    let mut selections = BTreeSet::new();
    for a in &values.batches {
        ensure(
            !a.id.is_empty()
                && ids.insert(a.id.as_str())
                && selections.insert((a.selection.bytes, a.selection.sha256.as_str()))
                && a.package_count == 39
                && a.apk_file_count >= a.package_count
                && a.apk_file_count <= 39 * 32
                && a.apk_total_bytes > 0
                && [
                    &a.selection,
                    &a.signature_receipt,
                    &a.normal_import,
                    &a.normal_input_verification,
                ]
                .into_iter()
                .all(BytesPin::valid),
            "compiled application admission is malformed or ambiguous",
        )?;
    }
    values.batches.into_iter().find(|a| a.id == CURRENT_BATCH)
        .ok_or_else(|| "new working qualification requires its source-reviewed r7 admission; r6 is only first once".into())
}

fn source_rows(value: &Value) -> Result<BTreeMap<String, (u64, String, bool)>> {
    let rows = value["sources"]
        .as_array()
        .ok_or("normal public source roster absent")?;
    ensure(
        !rows.is_empty() && rows.len() <= 39 * 32 + 16,
        "normal public source bound",
    )?;
    let mut result = BTreeMap::new();
    for row in rows {
        let pin: FilePin = serde_json::from_value(row["source"].clone())?;
        let path = fs::absolute_string(&pin.path)?;
        let apk = row["apk"]
            .as_bool()
            .ok_or("normal public source kind absent")?;
        ensure(
            pin.bytes > 0
                && fs::valid_digest(&pin.sha256)
                && row["complete_sha256_verified"] == true
                && result.insert(path, (pin.bytes, pin.sha256, apk)).is_none(),
            "normal public source is malformed or duplicated",
        )?;
    }
    Ok(result)
}
fn normal_report(value: &Value, admission: &Admission) -> Result<()> {
    ensure(
        value["schema"] == "droidloom.public-apk-inputs-verified.v1"
            && value["scope"] == "source_materials_only"
            && value["package_count"].as_u64() == Some(admission.package_count as u64)
            && value["apk_file_count"].as_u64() == Some(admission.apk_file_count as u64)
            && value["applications_installed"] == 0
            && value["application_business_accepted"] == false
            && value["guest_qualified"] == false
            && value["production_ready"] == false,
        "working material input is not the exact normal source-only contract",
    )?;
    let rows = source_rows(value)?;
    let apks: Vec<_> = rows.values().filter(|row| row.2).collect();
    let bytes = apks
        .iter()
        .try_fold(0_u64, |sum, row| sum.checked_add(row.0))
        .ok_or("public APK total overflow")?;
    ensure(
        apks.len() == admission.apk_file_count && bytes == admission.apk_total_bytes,
        "actual normal public APK closure differs from the compiled current admission",
    )
}

/// Only the actual normal verifier and compiled source table construct this.
/// All four documents and all actual normal material descriptors remain held.
pub(super) struct CurrentPublicMaterials {
    documents: Vec<VerifiedSourceDocument>,
    actual: VerifiedInputs,
    admission: Admission,
}
impl CurrentPublicMaterials {
    pub(super) fn admit(inputs: &PublicMaterialInputs) -> Result<Self> {
        let admission = current_admission(ADMISSIONS)?;
        let pairs = [
            (&inputs.selection, &admission.selection),
            (&inputs.signature_receipt, &admission.signature_receipt),
            (&inputs.normal_import, &admission.normal_import),
            (
                &inputs.normal_input_verification,
                &admission.normal_input_verification,
            ),
        ];
        let mut documents = Vec::new();
        for (pin, expected) in pairs {
            ensure(
                expected.matches(pin),
                "H2 document differs from its compiled r7 commitment",
            )?;
            documents.push(VerifiedSourceDocument::observe(pin, MAX_DOCUMENT)?);
        }
        let import = documents[2].json(MAX_DOCUMENT)?;
        let selected: FilePin = serde_json::from_value(import["selection"].clone())?;
        let signature: FilePin = serde_json::from_value(import["source_receipt"].clone())?;
        ensure(
            super::same_pin(&selected, &inputs.selection)
                && super::same_pin(&signature, &inputs.signature_receipt),
            "normal import did not consume these exact selected and signature documents",
        )?;
        let original_report = documents[3].json(MAX_DOCUMENT)?;
        normal_report(&original_report, &admission)?;
        let old_import: FilePin = serde_json::from_value(original_report["import"].clone())?;
        ensure(
            super::same_pin(&old_import, &inputs.normal_import),
            "normal source receipt has another import",
        )?;

        let actual = boot_public_apks::observe_inputs(
            &inputs.normal_import.path,
            &inputs.normal_import.sha256,
        )?;
        normal_report(actual.report(), &admission)?;
        ensure(
            source_rows(actual.report())? == source_rows(&original_report)?,
            "fresh actual public input roster differs from the admitted normal source receipt",
        )?;
        let result = Self {
            documents,
            actual,
            admission,
        };
        result.revalidate()?;
        Ok(result)
    }
    pub(super) fn revalidate(&self) -> Result<()> {
        for document in &self.documents {
            document.revalidate()?;
        }
        self.actual.revalidate()
    }
    pub(super) fn report(&self) -> Value {
        json!({
            "schema":"droidloom.working-qualification-public-materials.v1",
            "compiled_admission":self.admission,
            "compiled_table_sha256":fs::digest(ADMISSIONS.as_bytes()),
            "documents":self.documents.iter().map(|v| json!({
                "source":v.pin(),"identity":v.identity()
            })).collect::<Vec<_>>(),
            "actual_normal_input_verification":self.actual.report(),
            "first_once_r6_history_changed":false,
            "runtime_or_business_authority":false
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn table(id: &str) -> Value {
        let pin = |letter: &str| json!({"bytes":1,"sha256":letter.repeat(64)});
        json!({"schema":"droidloom.application-material-admissions.v1","batches":[{
            "id":id,"selection":pin("a"),"signature_receipt":pin("b"),
            "normal_import":pin("c"),"normal_input_verification":pin("d"),
            "package_count":39,"apk_file_count":39,"apk_total_bytes":39
        }]})
    }
    #[test]
    fn compiled_working_material_policy_has_current_r7_and_distinct_first_once_history() {
        // Synthetic tables cannot catch an omitted source integration. Exercise
        // the exact table embedded in the normal fixture executable.
        let current = current_admission(ADMISSIONS).unwrap();
        assert_eq!(current.package_count, 39);
        assert_eq!(current.apk_file_count, 65);
        assert_eq!(current.apk_total_bytes, 4_591_853_985);
        let compiled: Admissions = serde_json::from_str(ADMISSIONS).unwrap();
        let first_once = compiled
            .batches
            .iter()
            .find(|row| row.id == "p4-public-apk-candidate-4b91-r6")
            .unwrap();
        for (working, historical) in [
            (&current.selection, &first_once.selection),
            (&current.signature_receipt, &first_once.signature_receipt),
            (&current.normal_import, &first_once.normal_import),
            (
                &current.normal_input_verification,
                &first_once.normal_input_verification,
            ),
        ] {
            assert_ne!(working.sha256, historical.sha256);
        }
    }

    #[test]
    fn working_material_policy_has_no_legacy_or_caller_batch_fallback() {
        let admitted = table(CURRENT_BATCH);
        let parsed = current_admission(&admitted.to_string()).unwrap();
        assert_eq!(parsed.id, CURRENT_BATCH);
        for id in [
            "p4-public-apk-candidate-4b91-r6",
            "p4-public-apk-candidate-4b91-r8",
        ] {
            assert!(current_admission(&table(id).to_string()).is_err());
        }
        let mut duplicate = admitted.clone();
        let row = duplicate["batches"][0].clone();
        duplicate["batches"].as_array_mut().unwrap().push(row);
        assert!(current_admission(&duplicate.to_string()).is_err());
        let mut supplied = admitted.clone();
        supplied["passed"] = json!(true);
        assert!(current_admission(&supplied.to_string()).is_err());
        supplied = admitted;
        supplied["batches"][0]
            .as_object_mut()
            .unwrap()
            .remove("normal_input_verification");
        assert!(current_admission(&supplied.to_string()).is_err());
    }
    #[test]
    fn working_material_policy_requires_all_four_full_commitments() {
        let admitted = current_admission(&table(CURRENT_BATCH).to_string()).unwrap();
        for expected in [
            &admitted.selection,
            &admitted.signature_receipt,
            &admitted.normal_import,
            &admitted.normal_input_verification,
        ] {
            let mut actual = FilePin {
                path: "/public/source".into(),
                bytes: expected.bytes,
                sha256: expected.sha256.clone(),
            };
            assert!(expected.matches(&actual));
            actual.bytes += 1;
            assert!(!expected.matches(&actual));
            actual.bytes = expected.bytes;
            actual.sha256 = "0".repeat(64);
            assert!(!expected.matches(&actual));
        }
    }
    #[test]
    fn working_material_policy_rejects_partial_duplicate_or_runtime_credit_report() {
        let admitted = current_admission(&table(CURRENT_BATCH).to_string()).unwrap();
        let sources=(0..39).map(|index|json!({
            "source":{"path":format!("/public/{index}.apk"),"bytes":1,"sha256":"a".repeat(64)},
            "apk":true,"complete_sha256_verified":true
        })).collect::<Vec<_>>();
        let valid = json!({"schema":"droidloom.public-apk-inputs-verified.v1",
            "scope":"source_materials_only","package_count":39,"apk_file_count":39,
            "applications_installed":0,"application_business_accepted":false,
            "guest_qualified":false,"production_ready":false,"sources":sources});
        normal_report(&valid, &admitted).unwrap();
        let mut changed = valid.clone();
        changed["sources"].as_array_mut().unwrap().pop();
        assert!(normal_report(&changed, &admitted).is_err());
        changed = valid.clone();
        changed["sources"][38] = changed["sources"][0].clone();
        assert!(normal_report(&changed, &admitted).is_err());
        changed = valid.clone();
        changed["production_ready"] = json!(true);
        assert!(normal_report(&changed, &admitted).is_err());
        changed = valid.clone();
        changed["sources"][0]["source"]["sha256"] = json!("b".repeat(64));
        assert_ne!(source_rows(&changed).unwrap(), source_rows(&valid).unwrap());
    }
}
