//! Whole-App release scope is the last per-App join, before whole-run acceptance.
//! Only the retained source-owned case histories below supply prerequisites.
//! Neither a serialized report nor CompletePhysicalApplicationRun is an input.
use super::*;

const ACCOUNT_PREREQUISITE: &str = "Authenticated or transactional coverage needs an authorized test account/environment; guest search alone is scoped progress.";
const COMMUNICATION_PREREQUISITE: &str = "No outbound message or call until an explicit authorized test recipient/endpoint is available.";
const REVIEWED_REGISTRY: &[u8] = include_bytes!("../tests/fixtures/physical-gates39-registry.json");

#[derive(Debug, Clone, PartialEq, Serialize)]
struct DependencyReview {
    description: String,
    required_gates: Vec<&'static str>,
}
#[derive(Debug, Clone, PartialEq, Serialize)]
struct Checklist {
    package: &'static str,
    profile: &'static str,
    common: BTreeMap<String, String>,
    business: BTreeMap<String, String>,
    release_scope: String,
    dependencies: Vec<DependencyReview>,
}

fn dependency_gates(
    fixed: &'static roster::PackageGates,
    prerequisites: &[String],
) -> Result<Vec<DependencyReview>, String> {
    if fixed.profile == "browser" {
        require(fixed.package == "org.mozilla.firefox" && prerequisites.len() == 5,
            "browser release review lost its five exact source prerequisites")?;
        let gates: [&[&str]; 5] = [
            &["identity", "data_permissions", "lifecycle", "stability", "ui_observation"],
            &["browser.document", "browser.media", "data_permissions"],
            &["browser.external_https", "browser.recovery"],
            &["browser.return", "browser.recovery", "data_permissions"],
            &["identity", "ui_observation", "stability"],
        ];
        return Ok(prerequisites.iter().zip(gates).map(|(description, required)|
            DependencyReview { description:description.clone(), required_gates:required.to_vec() }
        ).collect());
    }
    prerequisites.iter().map(|description| {
        let required: &[&str] = match description.as_str() {
            ACCOUNT_PREREQUISITE => match fixed.profile {
                "hotel" => &["hotel.account"],
                "train" => &["train.account"],
                "retail" => &["retail.account"],
                "rental" => &["rental.account"],
                "flight" => &["flight.account"],
                "services" => &["services.account"],
                "travel" => &["travel.account"],
                "delivery" => &["delivery.order_scope"],
                "ride" => &["ride.location", "ride.lifecycle"],
                _ => return Err("account prerequisite has no source-owned typed business contract".into()),
            },
            COMMUNICATION_PREREQUISITE => match fixed.profile {
                "dialer" => &["dialer.call", "dialer.history"],
                "messaging" => &["messaging.compose", "messaging.delivery", "messaging.persist"],
                _ => return Err("communication prerequisite has no exact authorized endpoint contract".into()),
            },
            _ => return Err("release scope encountered an unreviewed prerequisite".into()),
        };
        require(required.iter().all(|gate| fixed.business.contains(gate)),
            "release dependency names a gate outside the exact package contract")?;
        Ok(DependencyReview { description:description.clone(), required_gates:required.to_vec() })
    }).collect()
}

fn checklists(registry: &GateRegistry) -> Result<Vec<Checklist>, String> {
    require(REVIEWED_REGISTRY.len() as u64 == roster::REGISTRY_BYTES
        && format!("{:x}", Sha256::digest(REVIEWED_REGISTRY)) == roster::REGISTRY_SHA256,
        "compiled release review differs from the exact normal registry bytes")?;
    let reviewed: GateRegistry = serde_json::from_slice(REVIEWED_REGISTRY).map_err(|e|e.to_string())?;
    require(serde_json::to_value(registry).map_err(|e|e.to_string())?
        == serde_json::to_value(&reviewed).map_err(|e|e.to_string())?,
        "release checklist changed descriptions, dependencies, failure paths or package scope")?;
    roster::PACKAGES.iter().map(|fixed| {
        let registered = registry.packages.get(fixed.package).ok_or("release package absent")?;
        let profile = registry.profiles.get(fixed.profile).ok_or("release profile absent")?;
        require(registered.profile == fixed.profile
            && profile.checks.keys().map(String::as_str).collect::<BTreeSet<_>>()
                == fixed.business.iter().copied().collect(),
            "release profile substituted a required feature or failure path")?;
        let mut common = registry.common_gates.clone();
        let release_scope = common.remove("release_scope").ok_or("release scope description absent")?;
        require(common.keys().map(String::as_str).collect::<BTreeSet<_>>()
            == roster::COMMON.into_iter().filter(|gate| *gate != "release_scope").collect(),
            "release review requires the other five complete common contracts")?;
        Ok(Checklist {
            package:fixed.package, profile:fixed.profile, common,
            business:profile.checks.clone(), release_scope,
            dependencies:dependency_gates(fixed, &registered.prerequisites)?,
        })
    }).collect()
}

/// Frozen semantics from the actual originally retained registry input.
/// This review alone supplies no completed gate.
pub(super) struct ReleaseScopeReview {
    registry: FilePin,
    checklists: Vec<Checklist>,
}
impl ReleaseScopeReview {
    pub(super) fn capture(
        registry: &GateRegistry, pin: &FilePin, inputs: &PlanInputs,
    ) -> Result<Self, String> {
        require(pin.bytes == roster::REGISTRY_BYTES && pin.sha256 == roster::REGISTRY_SHA256,
            "release review requires the original complete registry commitment")?;
        let value = Self { registry:pin.clone(), checklists:checklists(registry)? };
        value.guard(inputs)?;
        Ok(value)
    }
    pub(super) fn guard(&self, inputs: &PlanInputs) -> Result<(), String> {
        let held = inputs.documents.iter().find(|doc| doc.reference() == &self.registry)
            .ok_or("release scope lost its original retained registry descriptor")?;
        let current: GateRegistry = serde_json::from_value(held.read()?).map_err(|e|e.to_string())?;
        require(checklists(&current)? == self.checklists,
            "retained release checklist differs from its original semantics")
    }
    pub(super) fn reconcile(
        &self, inputs: &PlanInputs, evidence: &ScopeEvidence<'_>,
    ) -> Result<Vec<ReleaseScopeFact>, String> {
        self.guard(inputs)?;
        evidence.guard_histories()?;
        let mut result = Vec::new();
        for checklist in &self.checklists {
            if let Some(fact) = collect(checklist, evidence)? { result.push(fact); }
        }
        self.guard(inputs)?;
        Ok(result)
    }
}

/// Borrowed only from this invocation's real, non-deserializable custody.
/// The fields never accept a saved passed-map or a caller's success boolean.
pub(super) struct ScopeEvidence<'a> {
    pub(super) original_main: &'a control::MainCustodyObservation,
    pub(super) final_main: Option<&'a control::MainCustodyObservation>,
    pub(super) histories: &'a [HistoricalCompletedCase],
    pub(super) native_facts: &'a [HistoricalNativeBusinessFact],
    pub(super) families: &'a [HistoricalFamilyCase],
    pub(super) photo: Option<&'a HistoricalCameraPhotoCase>,
    pub(super) settings: Option<&'a HistoricalSettingsPermissionCase>,
    pub(super) errors: &'a BTreeMap<String, String>,
    pub(super) retained_failure: Option<&'a str>,
}
impl ScopeEvidence<'_> {
    fn guard_histories(&self) -> Result<(), String> {
        if let Some(final_main) = self.final_main {
            require_same_main(self.original_main.facts(), final_main.facts())?;
        }
        for case in self.histories {
            case.guard()?;
            require_same_main(case.binding(), self.original_main.facts())?;
        }
        for family in self.families {
            family.guard()?;
            require_same_main(family.binding(), self.original_main.facts())?;
        }
        for fact in self.native_facts { fact.require_retained_binding(self.histories)?; }
        if let Some(photo) = self.photo {
            photo.guard()?;
            photo.require_original_case(self.histories)?;
            require_same_main(photo.binding(), self.original_main.facts())?;
        }
        if let Some(settings) = self.settings {
            settings.guard()?;
            settings.require_original_case(self.histories)?;
            require_same_main(settings.binding(), self.original_main.facts())?;
        }
        Ok(())
    }
}

/// Only collect() constructs this complete, same-subject per-App join. Its
/// contributing original histories remain owned by RunCustody through ACK.
#[derive(PartialEq)]
pub(super) struct ReleaseScopeFact {
    checklist: Checklist,
    actual: ApplicationInspection,
    main: RuntimeMainCustody,
    basis: BTreeMap<&'static str, Vec<usize>>,
    completed_cases: Vec<usize>,
}
impl ReleaseScopeFact {
    pub(super) fn package(&self) -> &'static str { self.checklist.package }
    pub(super) fn completed_cases(&self) -> &[usize] { &self.completed_cases }
    pub(super) fn guard(
        &self, review: &ReleaseScopeReview, evidence: &ScopeEvidence<'_>,
    ) -> Result<(), String> {
        // RunCustody has just guarded all original source/result journals.
        // This recomputes the relation from those typed objects, never from
        // comparison JSON, without renewing their historical execution leases.
        let checklist = review.checklists.iter().find(|row| row.package == self.package())
            .ok_or("release fact lost its exact source checklist")?;
        let recomputed = collect(checklist, evidence)?
            .ok_or("release fact lost a complete prerequisite or retained a failure")?;
        require(&recomputed == self,
            "release fact no longer joins the same Main, full PM identity and case basis")
    }
    pub(super) fn comparison(&self) -> Result<Value, String> {
        Ok(serde_json::json!({
            "schema":"droidloom.physical-application-release-scope.v1",
            "package":self.package(), "profile":self.checklist.profile,
            "application":self.actual,
            "main_sha256":format!("{:x}",Sha256::digest(
                serde_json::to_vec(&self.main).map_err(|e|e.to_string())?)),
            "source_checklist":self.checklist,
            "typed_prerequisite_cases":self.basis,
            "completed_cases":self.completed_cases,
            "retained_failures":[],
            "unsupported_or_unavailable_prerequisites":[],
            "whole_application_release_accepted":true,
            "whole_run_acceptance_used_as_input":false,
            "saved_reports_used_as_authority":false,
            "historical_leases_renewed":false
        }))
    }
}

fn insert_basis(
    fixed: &'static roster::PackageGates,
    basis: &mut BTreeMap<&'static str, Vec<usize>>,
    gate: &'static str, index: usize,
) -> Result<(), String> {
    require(gate != "release_scope" && roster::required(fixed).contains(gate)
        && index < owned_channel::CASE_COUNT,
        "release prerequisite is foreign, circular or outside actual case ordinals")?;
    let indices = basis.entry(gate).or_default();
    if !indices.contains(&index) { indices.push(index); indices.sort_unstable(); }
    Ok(())
}

/// Pure completeness comparison. It cannot construct a ReleaseScopeFact.
fn complete_basis(
    checklist: &Checklist, basis: &BTreeMap<&'static str, Vec<usize>>,
) -> Result<bool, String> {
    let required = checklist.common.keys().chain(checklist.business.keys())
        .map(String::as_str).collect::<BTreeSet<_>>();
    require(!required.contains("release_scope")
        && basis.keys().all(|gate| required.contains(gate)),
        "release scope cannot depend on itself or substitute an undeclared feature")?;
    for indices in basis.values() {
        require(!indices.is_empty() && indices.iter().all(|index| *index < owned_channel::CASE_COUNT)
            && indices.windows(2).all(|pair| pair[0] < pair[1]),
            "release prerequisite lost its distinct real contributing case ordinals")?;
    }
    for dependency in &checklist.dependencies {
        require(!dependency.required_gates.is_empty()
            && dependency.required_gates.iter().all(|gate| required.contains(gate)),
            "release dependency has no exact complete typed prerequisite")?;
    }
    Ok(basis.keys().copied().collect::<BTreeSet<_>>() == required
        && checklist.dependencies.iter().all(|dependency|
            dependency.required_gates.iter().all(|gate| basis.contains_key(gate))))
}

fn collect(
    checklist: &Checklist, evidence: &ScopeEvidence<'_>,
) -> Result<Option<ReleaseScopeFact>, String> {
    let fixed = roster::package(checklist.package)?;
    let cases = evidence.histories.iter().enumerate()
        .filter(|(_, case)| case.summary.actual.package == fixed.package).collect::<Vec<_>>();
    let families = evidence.families.iter().enumerate()
        .filter(|(_, case)| case.summary.actual.package == fixed.package).collect::<Vec<_>>();
    require(cases.len() <= fixed.cases.len()
        && cases.iter().zip(fixed.cases).all(|((_, case), route)| case.summary.route == *route)
        && families.len() <= usize::from(fixed.cases.is_empty()),
        "release scope has duplicate, reordered or cross-family case histories")?;
    if evidence.final_main.is_none() || evidence.retained_failure.is_some()
        || !evidence.errors.is_empty()
        || cases.len() != fixed.cases.len()
        || families.len() != usize::from(fixed.cases.is_empty())
        || (fixed.package == "com.android.camera2" && evidence.photo.is_none())
        || (fixed.package == "com.android.settings" && evidence.settings.is_none())
    { return Ok(None); }
    let actual = cases.first().map(|(_, case)| &case.summary.actual)
        .or_else(|| families.first().map(|(_, case)| &case.summary.actual))
        .ok_or("release scope has no actual full PM subject")?;
    let main = evidence.original_main.facts();
    require(actual.package == fixed.package && actual.user == 0 && actual.epoch == main.epoch,
        "release scope differs from the actual package/user/Main epoch")?;
    let mut basis = BTreeMap::new();
    for (index, case) in &cases {
        require(&case.summary.actual == actual, "release cases changed the full installed PM subject")?;
        require_same_main(case.binding(), main)?;
        for fact in &case.summary.common {
            fact.require_subject(fixed.package, &actual.epoch)?;
            insert_basis(fixed, &mut basis, fact.id(), *index)?;
        }
        for gate in &case.summary.business_gates { insert_basis(fixed, &mut basis, *gate, *index)?; }
    }
    for fact in evidence.native_facts {
        let first = evidence.histories.get(*fact.case_indices.first()
            .ok_or("native release fact has no history basis")?).ok_or("native release index absent")?;
        if first.summary.actual.package != fixed.package { continue; }
        fact.fact.require_subject(fixed.package, main, actual)?;
        for index in &fact.case_indices { insert_basis(fixed, &mut basis, fact.fact.gate(), *index)?; }
    }
    for (index, family) in families {
        require(evidence.histories.len() == owned_channel::NATIVE_CASE_COUNT
            && &family.summary.actual == actual,
            "family release scope has the wrong preceding native cases or full PM subject")?;
        require_same_main(family.binding(), main)?;
        if !family.custody.blocked().is_empty() { return Ok(None); }
        for fact in &family.summary.common {
            fact.require_subject(fixed.package, &actual.epoch)?;
            insert_basis(fixed, &mut basis, fact.id(), evidence.histories.len() + index)?;
        }
        for fact in family.custody.business_facts() {
            fact.require_subject(main, actual)?;
            insert_basis(fixed, &mut basis, fact.id(), evidence.histories.len() + index)?;
        }
    }
    if let Some(photo) = evidence.photo.filter(|photo| photo.summary.actual.package == fixed.package) {
        photo.fact.require_subject(main, actual)?;
        insert_basis(fixed, &mut basis, photo.fact.gate(), QualificationCase::CameraPhotoCaptureReopen as usize)?;
    }
    if let Some(settings) = evidence.settings.filter(|case| case.summary.actual.package == fixed.package) {
        settings.fact.require_subject(main, actual)?;
        insert_basis(fixed, &mut basis, settings.fact.gate(), QualificationCase::SettingsPermissionInterfaces as usize)?;
    }
    if !complete_basis(checklist, &basis)? { return Ok(None); }
    let completed_cases = basis.values().flatten().copied().collect::<BTreeSet<_>>().into_iter().collect();
    Ok(Some(ReleaseScopeFact { checklist:checklist.clone(), actual:actual.clone(),
        main:main.clone(), basis, completed_cases }))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn reviewed() -> GateRegistry { serde_json::from_slice(REVIEWED_REGISTRY).unwrap() }
    #[test]
    fn release_scope_checklist_preserves_all_338_prior_contracts_and_dependencies() {
        let rows = checklists(&reviewed()).unwrap();
        assert_eq!(rows.len(), 39);
        assert_eq!(rows.iter().map(|row| row.common.len() + row.business.len()).sum::<usize>(), 338);
        for row in rows {
            assert_eq!(row.common.len(), 5);
            assert!(!row.common.contains_key("release_scope"));
            for dependency in row.dependencies {
                assert!(!dependency.required_gates.is_empty());
                assert!(dependency.required_gates.iter()
                    .all(|gate| row.common.contains_key(*gate) || row.business.contains_key(*gate)));
            }
        }
    }
    #[test]
    fn release_scope_rejects_same_id_description_dependency_or_scope_substitution() {
        let mut gates = reviewed();
        gates.common_gates.insert("data_permissions".into(), "directory inode unchanged".into());
        assert!(checklists(&gates).is_err());
        let mut gates = reviewed();
        gates.packages.get_mut("com.android.dialer").unwrap().prerequisites.clear();
        assert!(checklists(&gates).is_err());
        let mut gates = reviewed();
        gates.profiles.get_mut("hotel").unwrap().checks.insert("hotel.account".into(), "guest search".into());
        assert!(checklists(&gates).is_err());
        let mut gates = reviewed();
        gates.packages.remove("org.mozilla.firefox");
        assert!(checklists(&gates).is_err());
    }
    #[test]
    fn release_scope_requires_real_account_communication_and_browser_contracts() {
        let rows = checklists(&reviewed()).unwrap();
        let find = |package| rows.iter().find(|row| row.package == package).unwrap();
        assert_eq!(find("com.Hyatt.hyt").dependencies[0].required_gates, ["hotel.account"]);
        assert_eq!(find("com.android.dialer").dependencies[0].required_gates, ["dialer.call", "dialer.history"]);
        assert_eq!(find("com.tencent.mm").dependencies[0].required_gates,
            ["messaging.compose", "messaging.delivery", "messaging.persist"]);
        assert_eq!(find("org.mozilla.firefox").dependencies.len(), 5);
        assert!(dependency_gates(roster::package("com.android.settings").unwrap(),
            &[ACCOUNT_PREREQUISITE.into()]).is_err());
        assert!(dependency_gates(roster::package("com.Hyatt.hyt").unwrap(),
            &["assume account access".into()]).is_err());
    }
    #[test]
    fn release_scope_coverage_rejects_missing_data_circular_or_invalid_case_basis() {
        // Pure set/index comparisons cannot mint histories or release facts.
        let rows = checklists(&reviewed()).unwrap();
        let row = rows.iter().find(|row| row.package == "com.android.settings").unwrap();
        let fixed = roster::package(row.package).unwrap();
        let mut basis = BTreeMap::new();
        for gate in roster::required(fixed).into_iter().filter(|gate| *gate != "release_scope") {
            insert_basis(fixed, &mut basis, gate, 12).unwrap();
        }
        assert!(complete_basis(row, &basis).unwrap());
        let mut missing = basis.clone();
        missing.remove("data_permissions");
        assert!(!complete_basis(row, &missing).unwrap());
        let mut circular = basis.clone();
        circular.insert("release_scope", vec![12]);
        assert!(complete_basis(row, &circular).is_err());
        for invalid in [vec![], vec![12,12], vec![13,12], vec![owned_channel::CASE_COUNT]] {
            let mut changed = basis.clone();
            changed.insert("identity", invalid);
            assert!(complete_basis(row, &changed).is_err());
        }
        assert!(insert_basis(fixed, &mut basis, "camera.photo", 12).is_err());
        assert!(insert_basis(fixed, &mut basis, "release_scope", 12).is_err());
    }
}
