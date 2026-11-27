//! Complete native business assertions from an actual, retained leaf invocation.
//!
//! This module is deliberately not a receipt importer. The only production
//! constructor borrows LeafObservation, rechecks its live source/Main/result
//! custody, and reads the original held result descriptor. The private parsers
//! below describe what those exact admitted programs actually executed.
//! Image/video and create/open-provider fragments have no public gate name.
//! They acquire a complete gate only in the fixed same-subject join.
use super::FilePin;
use super::leaf_routes::{self, LeafObservation, Route};
use droidloom_supervisor::control::application_probe::ApplicationInspection;
use droidloom_supervisor::main_custody::RuntimeMainCustody;
use serde::Serialize;
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;

type Result<T> = std::result::Result<T, String>;

#[derive(Clone, PartialEq)]
struct Subject {
    application: ApplicationInspection,
    main: Value,
    selection: FilePin,
    catalog_sha256: String,
}
impl Subject {
    fn require(
        &self,
        package: &str,
        main: &RuntimeMainCustody,
        actual: &ApplicationInspection,
    ) -> Result<()> {
        need(
            self.application.package == package
                && actual.package == package
                && &self.application == actual
                && main.epoch == actual.epoch
                && self.main == serde_json::to_value(main).map_err(|e| e.to_string())?,
            "native cases differ in package/user/UID/version/full APKs or actual Main/epoch",
        )
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd)]
enum Gate {
    ContactsEdit,
    ContactsPersist,
    ContactsCleanup,
    CalendarEdit,
    CalendarPersist,
    CalendarReminder,
    CameraPreview,
    CameraPersist,
    ClockAlarm,
    ClockPersist,
    DocumentsIo,
    DocumentsPersist,
    DocumentsProvider,
    GalleryEnumeration,
    GalleryOpen,
    GalleryPersist,
}
impl Gate {
    fn name(self) -> &'static str {
        match self {
            Self::ContactsEdit => "contacts.edit",
            Self::ContactsPersist => "contacts.persist",
            Self::ContactsCleanup => "contacts.cleanup",
            Self::CalendarEdit => "calendar.edit",
            Self::CalendarPersist => "calendar.persist",
            Self::CalendarReminder => "calendar.reminder",
            Self::CameraPreview => "camera.preview",
            Self::CameraPersist => "camera.persist",
            Self::ClockAlarm => "clock.alarm",
            Self::ClockPersist => "clock.persist",
            Self::DocumentsIo => "documents.io",
            Self::DocumentsPersist => "documents.persist",
            Self::DocumentsProvider => "documents.provider",
            Self::GalleryEnumeration => "gallery.enumeration",
            Self::GalleryOpen => "gallery.open",
            Self::GalleryPersist => "gallery.persist",
        }
    }
}
#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd)]
enum Fragment {
    DocumentsCreateOpen,
    DocumentsNavigation,
    GalleryImage,
    GalleryVideo,
}
#[derive(Default)]
struct CheckedCase {
    gates: BTreeSet<Gate>,
    fragments: BTreeSet<Fragment>,
}

/// No Deserialize, Clone, public fields or caller-supplied result constructor.
/// The history owner retains this alongside the invocation's immutable guards.
pub(super) struct NativeCaseEvidence {
    subject: Subject,
    route: Route,
    request: FilePin,
    result: FilePin,
    preparation: FilePin,
    entry: FilePin,
    checked: CheckedCase,
}
impl NativeCaseEvidence {
    pub(super) fn require_subject(
        &self,
        package: &str,
        main: &RuntimeMainCustody,
        actual: &ApplicationInspection,
    ) -> Result<()> {
        self.subject.require(package, main, actual)
    }
}

/// A named complete registry assertion, never a generic "passed" map.
pub(super) struct NativeBusinessFact {
    subject: Subject,
    gate: Gate,
    basis: Vec<CaseBasis>,
}
#[derive(Serialize)]
struct CaseBasis {
    route: Route,
    request: FilePin,
    result: FilePin,
    preparation: FilePin,
    entry: FilePin,
}
impl NativeBusinessFact {
    pub(super) fn gate(&self) -> &'static str {
        self.gate.name()
    }
    pub(super) fn require_subject(
        &self,
        package: &str,
        main: &RuntimeMainCustody,
        actual: &ApplicationInspection,
    ) -> Result<()> {
        self.subject.require(package, main, actual)
    }
    /// Exact typed case origins; this cannot construct a fact or accept result JSON.
    pub(super) fn contributing_routes(&self) -> impl Iterator<Item = Route> + '_ {
        self.basis.iter().map(|value| value.route)
    }
    /// A small comparison summary; the typed fact, not this JSON, is authority.
    pub(super) fn comparison(&self) -> Result<Value> {
        Ok(serde_json::json!({
            "schema":"droidloom.native-business-fact.v1",
            "package":self.subject.application.package,
            "gate":self.gate.name(),
            "source_selection":self.subject.selection,
            "source_catalog_sha256":self.subject.catalog_sha256,
            "cases":self.basis,
            "comparison_only":true,
            "whole_app_business_accepted":false,
        }))
    }
}

pub(super) fn from_leaf(leaf: &LeafObservation) -> Result<NativeCaseEvidence> {
    leaf.retained_bookends()?;
    need(
        leaf.original_entry_result_verified
            && leaf.main_epoch_unchanged
            && leaf.owned_host_tree_retired
            && !leaf.automatic_retry
            && !leaf.whole_app_business_accepted
            && !leaf.production_ready,
        "native business input is not a completed, scoped original leaf",
    )?;
    let actual = leaf.actual_application()?;
    let main = leaf
        .main_observation()
        .ok_or("native leaf has no opaque Main")?;
    need(
        actual.package == leaf.route.package()
            && actual.user == 0
            && main.facts().epoch == actual.epoch,
        "native business subject is not the actual selected user-zero application",
    )?;
    let (selection, catalog) = leaf_routes::compiled_release_sources();
    let rows: Value = serde_json::from_str(catalog).map_err(|e| e.to_string())?;
    let source_index = source_index(leaf.route);
    let row = array(&rows, "")?
        .iter()
        .find(|row| row["index"].as_u64() == Some(source_index))
        .ok_or("native case is absent from the compiled source catalog")?;
    let preparation: FilePin =
        serde_json::from_value(row["preparation"].clone()).map_err(|e| e.to_string())?;
    let entry: FilePin = serde_json::from_value(row["entry"].clone()).map_err(|e| e.to_string())?;
    need(
        preparation == leaf.preparation && entry == leaf.entry_source,
        "native case does not use the compiled complete preparation and entry",
    )?;
    let subject = Subject {
        application: actual.clone(),
        main: serde_json::to_value(main.facts()).map_err(|e| e.to_string())?,
        selection,
        catalog_sha256: hex::encode(Sha256::digest(catalog.as_bytes())),
    };
    subject.require(leaf.route.package(), main.facts(), actual)?;
    // Exactly one same-FD result read; never open a named child result here.
    let result = leaf.retained_result_value()?;
    let checked = match expected_engine_points(leaf.route) {
        Some(points) => {
            need(
                leaf.original_business_success_reported && !leaf.business_outcome_unknown,
                "partial or unknown native business result cannot mint a gate",
            )?;
            let engines = leaf
                .engine_observations
                .as_ref()
                .ok_or("native business case lacks actual running-engine observations")?;
            engines.require_identity(main, actual)?;
            need(
                engines.observation_count() == points,
                "native case lacks its fixed actual target activation observations",
            )?;
            validate_case(leaf.route, &result)?
        }
        // Settings' two complete gates and the Clock timer pair have their own
        // existing typed factories. IHG's London text observation is incomplete.
        None => CheckedCase::default(),
    };
    leaf.retained_bookends()?;
    Ok(NativeCaseEvidence {
        subject,
        route: leaf.route,
        request: leaf.request.clone(),
        result: leaf.result.clone(),
        preparation: leaf.preparation.clone(),
        entry: leaf.entry_source.clone(),
        checked,
    })
}

fn source_index(route: Route) -> u64 {
    match route {
        Route::ContactsSearch | Route::CalendarCore => 0,
        Route::CalendarReminder => 1,
        Route::CameraPhoto => 3,
        Route::ClockTimerPair
        | Route::ClockTimerRemaining
        | Route::ClockExpiry
        | Route::ClockAlarm => 4,
        Route::ClockTimer | Route::IhgLondon => 5,
        Route::DocumentsSaf => 6,
        Route::DocumentsSearchSort => 7,
        Route::GalleryRotation => 9,
        Route::GalleryVideo => 10,
        Route::GallerySeek => 11,
        Route::GalleryAlbum => 12,
        Route::SettingsSupportedPages => 13,
    }
}
fn expected_engine_points(route: Route) -> Option<usize> {
    match route {
        Route::ContactsSearch
        | Route::CalendarCore
        | Route::CalendarReminder
        | Route::CameraPhoto
        | Route::ClockAlarm
        | Route::GalleryRotation
        | Route::GalleryVideo
        | Route::GallerySeek
        | Route::GalleryAlbum => Some(2),
        Route::DocumentsSaf => Some(3),
        Route::DocumentsSearchSort => Some(6),
        _ => None,
    }
}

pub(super) fn join_cases(cases: &[&NativeCaseEvidence]) -> Result<Vec<NativeBusinessFact>> {
    need(
        !cases.is_empty() && cases.len() <= 14,
        "native case join is empty or unbounded",
    )?;
    let subject = &cases[0].subject;
    let mut routes = BTreeSet::new();
    let mut paths = BTreeSet::new();
    let mut contents = BTreeSet::new();
    for case in cases {
        need(
            &case.subject == subject && case.route.package() == subject.application.package,
            "native case join mixed actual Main/package/epoch/APKs or source selection",
        )?;
        need(
            routes.insert(format!("{:?}", case.route))
                && paths.insert(case.result.path.clone())
                && contents.insert((case.result.bytes, case.result.sha256.clone())),
            "native case join repeats a route or actual result",
        )?;
    }
    let mut gates = BTreeSet::new();
    let mut fragments = BTreeSet::new();
    for case in cases {
        gates.extend(case.checked.gates.iter().copied());
        fragments.extend(case.checked.fragments.iter().copied());
    }
    if fragments.contains(&Fragment::DocumentsCreateOpen)
        && fragments.contains(&Fragment::DocumentsNavigation)
    {
        gates.insert(Gate::DocumentsProvider);
    }
    if fragments.contains(&Fragment::GalleryImage) && fragments.contains(&Fragment::GalleryVideo) {
        gates.extend([
            Gate::GalleryEnumeration,
            Gate::GalleryOpen,
            Gate::GalleryPersist,
        ]);
    }
    Ok(gates
        .into_iter()
        .map(|gate| NativeBusinessFact {
            subject: subject.clone(),
            gate,
            basis: cases
                .iter()
                .filter(|case| supplies(case, gate))
                .map(|case| CaseBasis {
                    route: case.route,
                    request: case.request.clone(),
                    result: case.result.clone(),
                    preparation: case.preparation.clone(),
                    entry: case.entry.clone(),
                })
                .collect(),
        })
        .collect())
}
fn supplies(case: &NativeCaseEvidence, gate: Gate) -> bool {
    case.checked.gates.contains(&gate)
        || match gate {
            Gate::DocumentsProvider => !case.checked.fragments.is_disjoint(&BTreeSet::from([
                Fragment::DocumentsCreateOpen,
                Fragment::DocumentsNavigation,
            ])),
            Gate::GalleryEnumeration | Gate::GalleryOpen | Gate::GalleryPersist => {
                !case.checked.fragments.is_disjoint(&BTreeSet::from([
                    Fragment::GalleryImage,
                    Fragment::GalleryVideo,
                ]))
            }
            _ => false,
        }
}

fn need(value: bool, message: &str) -> Result<()> {
    if value {
        Ok(())
    } else {
        Err(format!("native business: {message}"))
    }
}
fn at<'a>(root: &'a Value, path: &str) -> Result<&'a Value> {
    let mut value = root;
    for key in path.split('.').filter(|s| !s.is_empty()) {
        value = value
            .get(key)
            .ok_or_else(|| format!("native business missing {path}"))?;
    }
    Ok(value)
}
fn object<'a>(root: &'a Value, path: &str) -> Result<&'a Map<String, Value>> {
    at(root, path)?
        .as_object()
        .ok_or_else(|| format!("native business expected object {path}"))
}
fn array<'a>(root: &'a Value, path: &str) -> Result<&'a Vec<Value>> {
    at(root, path)?
        .as_array()
        .ok_or_else(|| format!("native business expected array {path}"))
}
fn text<'a>(root: &'a Value, path: &str) -> Result<&'a str> {
    at(root, path)?
        .as_str()
        .ok_or_else(|| format!("native business expected text {path}"))
}
fn number(root: &Value, path: &str) -> Result<u64> {
    at(root, path)?
        .as_u64()
        .ok_or_else(|| format!("native business expected integer {path}"))
}
fn yes(root: &Value, paths: &[&str]) -> Result<()> {
    for p in paths {
        need(at(root, p)? == true, &format!("{p} is not verified"))?;
    }
    Ok(())
}
fn no(root: &Value, paths: &[&str]) -> Result<()> {
    for p in paths {
        need(at(root, p)? == false, &format!("{p} was not false"))?;
    }
    Ok(())
}
fn empty(root: &Value, paths: &[&str]) -> Result<()> {
    for p in paths {
        need(
            match at(root, p)? {
                Value::Array(x) => x.is_empty(),
                Value::Object(x) => x.is_empty(),
                _ => false,
            },
            &format!("{p} was not an empty collection"),
        )?;
    }
    Ok(())
}
fn null(root: &Value, paths: &[&str]) -> Result<()> {
    for p in paths {
        need(at(root, p)?.is_null(), &format!("{p} remained pending"))?;
    }
    Ok(())
}
fn equal(root: &Value, a: &str, b: &str) -> Result<()> {
    let x = at(root, a)?;
    let y = at(root, b)?;
    need(!x.is_null() && x == y, &format!("{a}/{b} changed"))
}
fn exact(root: &Value, path: &str, expected: &str) -> Result<()> {
    need(
        text(root, path)? == expected,
        &format!("{path} differs from the fixed source contract"),
    )
}
fn zero_map(root: &Value, path: &str) -> Result<()> {
    let m = object(root, path)?;
    need(
        !m.is_empty() && m.values().all(|v| v.as_u64() == Some(0)),
        &format!("{path} is not all zero"),
    )
}
fn keys(root: &Value, path: &str, expected: &[&str]) -> Result<()> {
    need(
        object(root, path)?
            .keys()
            .map(String::as_str)
            .collect::<BTreeSet<_>>()
            == expected.iter().copied().collect(),
        &format!("{path} incomplete source step set"),
    )
}
fn sha(value: &Value, path: &str) -> Result<()> {
    let s = text(value, path)?;
    need(
        s.len() == 64
            && s.bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "invalid full content SHA256",
    )
}
fn positive_id(value: &Value) -> bool {
    value.as_u64().is_some_and(|x| x > 0)
        || value.as_str().is_some_and(|s| {
            !s.is_empty() && !s.starts_with('0') && s.bytes().all(|b| b.is_ascii_digit())
        })
}
fn tasks(root: &Value, opened: &str, closed: &str, count: usize) -> Result<()> {
    let a = array(root, opened)?;
    let b = array(root, closed)?;
    need(
        a.len() == count
            && a.iter().all(positive_id)
            && a.iter()
                .map(Value::to_string)
                .collect::<BTreeSet<_>>()
                .len()
                == count
            && a == b,
        "actual tasks were not distinctly launched and normally closed",
    )
}
fn terminal(root: &Value, schema: &str, state: &str) -> Result<()> {
    exact(root, "schema", schema)?;
    exact(root, "state", state)?;
    no(root, &["whole_app_business_accepted", "automatic_retry"])?;
    for key in [
        "error",
        "outer_error",
        "entry_error",
        "final_check_error",
        "post_context_error",
    ] {
        need(
            root.get(key).is_none_or(Value::is_null),
            "native result retained an error",
        )?;
    }
    for key in [
        "secondary_errors",
        "received_signals",
        "cancelled_signals",
        "entry_cancellation_signals",
    ] {
        if root.get(key).is_some() {
            empty(root, &[key])?;
        }
    }
    for key in [
        "outcome_unknown",
        "host_cancellation_observed",
        "production_ready",
        "whole_app_production_ready",
    ] {
        if root.get(key).is_some() {
            no(root, &[key])?;
        }
    }
    if root.get("cancellation_commit").is_some() {
        empty(
            root,
            &[
                "cancellation_commit.observed_before_commit",
                "cancellation_commit.pending_at_commit",
            ],
        )?;
        yes(
            root,
            &["cancellation_commit.decision_frozen_after_context_exit"],
        )?;
    }
    Ok(())
}
fn original_closed(root: &Value) -> Result<()> {
    yes(
        root,
        &[
            "case_business_success_verified",
            "final_source_and_identity_chain_unchanged",
            "actual_Main_and_original_APIs_closed",
            "whole_case_OFD_closed",
            "evidence_witness_closed",
        ],
    )?;
    empty(root, &["received_signals", "secondary_errors"])
}
fn validate_case(route: Route, result: &Value) -> Result<CheckedCase> {
    let mut out = CheckedCase::default();
    match route {
        Route::ContactsSearch => {
            contacts(result)?;
            out.gates.extend([
                Gate::ContactsEdit,
                Gate::ContactsPersist,
                Gate::ContactsCleanup,
            ]);
        }
        Route::CalendarCore => {
            calendar(result)?;
            out.gates
                .extend([Gate::CalendarEdit, Gate::CalendarPersist]);
        }
        Route::CalendarReminder => {
            reminder(result)?;
            out.gates.insert(Gate::CalendarReminder);
        }
        Route::CameraPhoto => {
            camera(result)?;
            out.gates.extend([Gate::CameraPreview, Gate::CameraPersist]);
        }
        Route::ClockAlarm => {
            alarm(result)?;
            out.gates.extend([Gate::ClockAlarm, Gate::ClockPersist]);
        }
        Route::DocumentsSaf => {
            documents_saf(result)?;
            out.gates
                .extend([Gate::DocumentsIo, Gate::DocumentsPersist]);
            out.fragments.insert(Fragment::DocumentsCreateOpen);
        }
        Route::DocumentsSearchSort => {
            documents_search(result)?;
            out.fragments.insert(Fragment::DocumentsNavigation);
        }
        Route::GalleryRotation => {
            gallery_outer(result)?;
            gallery_image(at(result, "business")?)?;
            out.fragments.insert(Fragment::GalleryImage);
        }
        Route::GalleryAlbum => {
            gallery_outer(result)?;
            gallery_album(at(result, "business")?)?;
            out.fragments.insert(Fragment::GalleryVideo);
        }
        // The album successor includes the original play/pause/resume/reopen
        // and seek predicates. These separate runs do not fill an image gap.
        Route::GalleryVideo | Route::GallerySeek => {
            gallery_outer(result)?;
        }
        _ => {}
    }
    Ok(out)
}

const CONTACT_NAME: &str = "Pocket4 Search QA r12 f4a76c9d";
const CONTACT_EDITED: &str = "Pocket4 Search QA r12 f4a76c9d Edited";
fn contact_proof<'a>(v: &'a Value, name: &str) -> Result<&'a Value> {
    exact(v, "name", name)?;
    yes(v, &["local_null_account"])?;
    for id in ["raw_contact_id", "contact_id", "name_data_id"] {
        need(
            positive_id(at(v, id)?),
            "contact has no exact positive owned row identity",
        )?;
    }
    Ok(v)
}
fn contact_identity(a: &Value, b: &Value) -> Result<()> {
    for key in ["raw_contact_id", "contact_id", "name_data_id"] {
        need(
            at(a, key)? == at(b, key)?,
            "contact name edit changed its owned database identity",
        )?;
    }
    Ok(())
}
fn contacts(v: &Value) -> Result<()> {
    terminal(
        v,
        "pocket4-final-original-system-case-result-v1",
        "ORIGINAL_CASE_VERIFIED_CLEAN",
    )?;
    original_closed(v)?;
    exact(v, "kind", "contacts_search")?;
    yes(
        v,
        &[
            "business_scope_completed",
            "cleanup_verified",
            "empty_baseline_verified",
            "edited_contact_found_by_search_and_reopened",
            "UI_delete_verified",
            "durable_contact_ownership",
        ],
    )?;
    null(
        v,
        &[
            "pending_input",
            "pending_close",
            "pending_database_effect",
            "owned_task_remaining",
        ],
    )?;
    tasks(v, "native_launched_tasks", "normally_closed_tasks", 2)?;
    equal(v, "guard_before", "guard_after")?;
    equal(v, "native_actions_before", "native_actions_after")?;
    equal(v, "account_topology_before", "account_topology_after")?;
    empty(
        v,
        &[
            "contacts_before.raw_rows",
            "contacts_before.marker_rows",
            "contacts_after.marker_rows",
        ],
    )?;
    null(v, &["contacts_before.owned", "contacts_after.owned"])?;
    let created = contact_proof(at(v, "phases.save-created-committed.proof")?, CONTACT_NAME)?;
    for tag in [
        "save-edited-committed",
        "persisted-after-normal-close",
        "persisted-after-reopen",
        "search-result-identity",
        "searched-detail-same-record",
        "before-delete-confirm",
    ] {
        let row = at(v, &format!("phases.{tag}"))?;
        let proof = contact_proof(at(row, "proof")?, CONTACT_EDITED)?;
        contact_identity(created, proof)?;
        let state = at(row, "state")?;
        let names = array(state, "marker_rows")?;
        need(
            names.len() == 1,
            "contact proof lacks its one actual name row",
        )?;
        exact(&names[0], "data1", CONTACT_EDITED)?;
        let owned = at(state, "owned")?;
        need(
            at(owned, "name_row")? == &names[0],
            "contact marker does not match the actual owned row",
        )?;
        null(
            owned,
            &[
                "raw_contact.account_name",
                "raw_contact.account_type",
                "raw_contact.data_set",
            ],
        )?;
        need(
            at(owned, "raw_contact._id")? == at(proof, "raw_contact_id")?
                && at(owned, "raw_contact.contact_id")? == at(proof, "contact_id")?
                && at(owned, "name_row._id")? == at(proof, "name_data_id")?,
            "contact proof is not bound to the exact provider rows",
        )?;
    }
    exact(v, "search_result.query", CONTACT_EDITED)?;
    contact_identity(
        created,
        contact_proof(at(v, "search_result.same_contact")?, CONTACT_EDITED)?,
    )?;
    exact(v, "search_result.observed_node.text", CONTACT_EDITED)?;
    exact(
        v,
        "search_result.observed_node.content-desc",
        CONTACT_EDITED,
    )?;
    yes(v, &["deleted_final_proof.active_owned_contact_absent"])?;
    let after = array(v, "contacts_after.raw_rows")?;
    need(
        after.len() <= 1
            && number(v, "deleted_final_proof.owned_tombstone_count")? == after.len() as u64
            && at(v, "deleted_final_proof.database_returned_to_empty")?
                == &Value::Bool(after.is_empty()),
        "contact cleanup omitted a row or reported a false empty database",
    )?;
    for row in after {
        need(
            at(row, "_id")? == at(created, "raw_contact_id")? && row["deleted"] == "1",
            "contact cleanup retained an active or unrelated row",
        )?;
    }
    // The successful UI-delete path cannot receive credit from provider fallback.
    need(
        v.get("fixture_cleanup").is_none()
            || v.get("fixture_cleanup")
                .and_then(|x| x.get("method"))
                .and_then(Value::as_str)
                == Some("read-only"),
        "provider fallback does not prove contact UI delete",
    )?;
    need(
        number(v, "provider_cleanup_calls")? == 0,
        "provider fallback cannot grant contact UI cleanup",
    )?;
    Ok(())
}

const CALENDAR_GATES: &[&str] = &[
    "explicit_first_use_local_calendar",
    "cancel_unsaved_without_event_write",
    "created_in_calendar_ui",
    "edited_same_event",
    "normal_close_reopen_detail",
    "deleted_in_calendar_ui",
    "edited_dates_timezone_recurrence",
    "later_occurrence_detail_does_not_change_series",
    "series_editor_uses_original_start",
];
fn calendar_closed(v: &Value) -> Result<()> {
    original_closed(v)?;
    yes(
        v,
        &[
            "business_scope_completed",
            "task_set_restored",
            "cleanup.calendar_removed",
            "cleanup.provider_baseline_restored",
            "diagnostics.clear",
        ],
    )?;
    empty(v, &["cleanup.errors", "ui_pending", "owned_tasks"])?;
    null(v, &["business_pending"])?;
    no(v, &["empty_calendar_cleanup_pending"])?;
    need(
        number(v, "native_launches")? == 2 && number(v, "normal_close_calls")? == 2,
        "Calendar must complete two original normal task lifecycles",
    )?;
    let closed = array(v, "normally_closed_tasks")?;
    need(
        closed.len() == 2 && closed.iter().all(positive_id) && closed[0] != closed[1],
        "Calendar normal close identities are incomplete",
    )?;
    zero_map(v, "final_counts")?;
    for (a, b) in [
        ("guard_before", "guard_after"),
        ("calendar_before", "calendar_after"),
        ("provider_before", "provider_after"),
        ("native_actions_before", "native_actions_after"),
    ] {
        equal(v, a, b)?;
    }
    Ok(())
}
fn one_event(v: &Value) -> Result<&Value> {
    let rows = array(v, "events")?;
    need(rows.len() == 1, "Calendar event readback is not unique")?;
    need(
        positive_id(at(&rows[0], "_id")?) && positive_id(at(&rows[0], "calendar_id")?),
        "Calendar event lacks actual provider identity",
    )?;
    Ok(&rows[0])
}
fn calendar(v: &Value) -> Result<()> {
    terminal(
        v,
        "pocket4-final-original-system-case-result-v1",
        "ORIGINAL_CASE_VERIFIED_CLEAN",
    )?;
    exact(v, "kind", "calendar_core")?;
    calendar_closed(v)?;
    keys(v, "gates", CALENDAR_GATES)?;
    let g = at(v, "gates")?;
    empty(
        g,
        &[
            "explicit_first_use_local_calendar.events",
            "cancel_unsaved_without_event_write.events",
            "deleted_in_calendar_ui.events",
        ],
    )?;
    let created = one_event(at(g, "created_in_calendar_ui")?)?;
    let edited = one_event(at(g, "edited_same_event")?)?;
    need(
        at(created, "_id")? == at(edited, "_id")?
            && at(created, "calendar_id")? == at(edited, "calendar_id")?
            && at(edited, "_id")? == at(v, "owned_event_id")?,
        "Calendar edit did not preserve the exact owned event",
    )?;
    exact(
        created,
        "title",
        "Pocket4 event calendar-recurrence21-6c978e4da120b35f",
    )?;
    exact(
        edited,
        "title",
        "Pocket4 event calendar-recurrence21-6c978e4da120b35f Edited",
    )?;
    exact(edited, "eventTimezone", "Hongkong")?;
    exact(edited, "rrule", "FREQ=DAILY")?;
    exact(edited, "duration", "PT2700S")?;
    null(edited, &["dtend", "_sync_id", "original_id"])?;
    need(
        number(edited, "allDay")? == 0
            && number(edited, "deleted")? == 0
            && number(edited, "hasAlarm")? == 0,
        "Calendar event scope changed",
    )?;
    let plan = at(v, "intended_series")?;
    need(
        at(plan, "dtstart")? == at(edited, "dtstart")?
            && at(plan, "duration")? == at(edited, "duration")?
            && at(plan, "rrule")? == at(edited, "rrule")?
            && at(plan, "timezone")? == at(edited, "eventTimezone")?
            && number(plan, "first_end")?.checked_sub(number(plan, "dtstart")?) == Some(2_700_000),
        "Calendar date/timezone/recurrence differs from its source-owned plan",
    )?;
    yes(
        v,
        &[
            "host_series_preflight.verified",
            "host_preflight_before_first_UI_launch",
        ],
    )?;
    need(
        at(v, "host_series_preflight.plan")? == plan
            && at(g, "edited_dates_timezone_recurrence.expected")? == plan
            && one_event(at(g, "edited_dates_timezone_recurrence.provider")?)? == edited
            && one_event(at(g, "normal_close_reopen_detail.provider")?)? == edited
            && one_event(at(
                g,
                "later_occurrence_detail_does_not_change_series.provider_after_view",
            )?)? == edited
            && one_event(at(
                g,
                "series_editor_uses_original_start.after_cancel_provider",
            )?)? == edited,
        "Calendar reopen, occurrence view or editor changed the exact edited series",
    )?;
    need(
        number(
            g,
            "later_occurrence_detail_does_not_change_series.selected_occurrence_begin",
        )? > number(edited, "dtstart")?,
        "Calendar did not inspect a later occurrence",
    )?;
    yes(
        g,
        &[
            "series_editor_uses_original_start.series_row_unchanged",
            "series_editor_uses_original_start.no_series_probe_save",
        ],
    )?;
    Ok(())
}
fn reminder(v: &Value) -> Result<()> {
    terminal(
        v,
        "pocket4-final-calendar-reminder22-current-result-v1",
        "OWNED_NATURAL_CALENDAR_REMINDER_AND_UI_DELETE_VERIFIED",
    )?;
    exact(v, "kind", "calendar_reminder")?;
    calendar_closed(v)?;
    keys(
        v,
        "gates",
        &[
            "reminder_set_in_calendar_ui",
            "ordinary_provider_reminder_fired_while_task_closed",
            "exact_android_notification_delivered",
            "deleted_in_calendar_ui",
            "owned_notification_removed_after_ui_delete",
        ],
    )?;
    let g = at(v, "gates")?;
    let created = one_event(at(g, "reminder_set_in_calendar_ui")?)?;
    need(
        one_event(at(v, "closed_event_persistence")?)? == created
            && one_event(at(g, "ordinary_provider_reminder_fired_while_task_closed")?)? == created,
        "Calendar reminder did not fire for the same normally closed event",
    )?;
    let alerts = array(
        g,
        "ordinary_provider_reminder_fired_while_task_closed.owned_alerts",
    )?;
    need(
        alerts.len() == 1 && alerts[0]["state"] == 1 && alerts[0]["event_id"] == created["_id"],
        "Calendar reminder provider state did not record the exact fired event",
    )?;
    yes(
        g,
        &[
            "exact_android_notification_delivered.present",
            "exact_android_notification_delivered.source_bound_uid_channel_title",
        ],
    )?;
    empty(g, &["deleted_in_calendar_ui.events"])?;
    need(
        number(
            g,
            "owned_notification_removed_after_ui_delete.active_calendar_count",
        )? == 0
            && number(v, "notifications_after.active_calendar_count")? == 0,
        "owned Calendar notification remained after UI delete",
    )?;
    equal(v, "system_timezone_before", "system_timezone_after")?;
    equal(
        v,
        "calendar_uid_census_before.same_uid_packages",
        "calendar_uid_census_after.same_uid_packages",
    )?;
    yes(
        v,
        &[
            "runtime_evidence.synchronous_observer_closed",
            "local_synchronous_observer_closed",
        ],
    )?;
    need(
        !array(v, "delivery_observations")?.is_empty(),
        "natural reminder samples absent",
    )?;
    Ok(())
}

fn camera(v: &Value) -> Result<()> {
    terminal(
        v,
        "pocket4-final-camera-photo-display-result-v1",
        "PHOTO_AND_DISPLAY_VERIFIED_VISUAL_AND_OTHER_APP_GATES_PENDING",
    )?;
    yes(
        v,
        &[
            "success",
            "photo_capture_persistence_verified",
            "display_lease_qualified",
            "one_new_image",
            "photo_persisted_after_close",
            "photo_persisted_after_reopen",
            "other_tasks_preserved",
            "installed_apk_and_data_identity_preserved",
            "provider_owner_preserved",
            "original_photo_state_machine_completed",
            "own_task_cleanup_verified",
            "current_Main_APIs_closed",
            "whole_case_OFD_closed",
            "evidence_witness_closed",
            "final_source_and_identity_chain_unchanged",
            "crash_observation.clear",
        ],
    )?;
    no(v, &["prior_photos_modified_or_deleted", "outcome_unknown"])?;
    empty(
        v,
        &["pending_effects", "received_signals", "secondary_errors"],
    )?;
    null(v, &["owned_task_remaining"])?;
    need(
        number(v, "native_launch_calls")? == 2
            && number(v, "own_task_remove_calls")? == 2
            && number(v, "shutter_calls")? == 1,
        "Camera did not execute exactly one shutter and two normal closes",
    )?;
    equal(v, "provider_before", "provider_after")?;
    equal(v, "guard_before", "guard_after")?;
    let row = at(v, "new_media_row")?;
    let photo = at(v, "photo")?;
    exact(row, "owner_package_name", "com.android.camera2")?;
    exact(row, "mime_type", "image/jpeg")?;
    need(
        positive_id(at(row, "_id")?)
            && number(row, "is_pending")? == 0
            && number(photo, "bytes")? == number(row, "_size")?
            && number(photo, "bytes")? > 0,
        "Camera JPEG does not match the exact completed MediaStore row",
    )?;
    yes(photo, &["fully_decoded"])?;
    sha(photo, "sha256")?;
    let dims = array(photo, "dimensions")?;
    need(
        dims.len() == 2
            && dims
                .iter()
                .all(|v| v.as_u64().is_some_and(|n| n > 0 && n <= 8192)),
        "Camera decoded dimensions absent",
    )?;
    let expected = vec![
        Value::from(number(row, "width")?),
        Value::from(number(row, "height")?),
    ];
    let mut swapped = expected.clone();
    swapped.reverse();
    need(
        dims == &expected || (matches!(number(row, "orientation")?, 90 | 270) && dims == &swapped),
        "Camera decoded pixels differ from MediaStore dimensions",
    )?;
    for path in ["first_provider", "reopened_provider"] {
        let p = at(v, path)?;
        no(p, &["historical_frames_used"])?;
        need(
            array(p, "actual_fixed_device_cycles")?.len() == 1
                && at(p, "invocation")? == at(v, "provider_before.InvocationID")?
                && number(p, "manager_pid")? == number(v, "provider_owner.pid")?
                && number(p, "end_monotonic_us")? > number(p, "start_monotonic_us")?,
            "Camera preview is not tied to this actual provider session",
        )?;
        let basic = at(p, "original_provider_proof")?;
        need(
            number(basic, "physical_frames")? >= 2
                && number(basic, "producer_frames")? >= 2
                && number(basic, "physical_open_close_pairs")? == 1
                && number(basic, "producer_open_close_pairs")? == 1
                && number(basic, "capture_exit")? == 0,
            "Camera provider did not deliver a live frame sequence",
        )?;
    }
    for path in ["first_preview", "reopened_preview"] {
        let p = at(v, path)?;
        yes(p, &["shutter_ready"])?;
        sha(p, "screenshot_scope_sha256")?;
    }
    // The source expressly leaves visual correspondence, video/audio and
    // recovery unqualified. No camera.photo/video/recovery Gate exists here.
    Ok(())
}
fn alarm(v: &Value) -> Result<()> {
    terminal(
        v,
        "pocket4-current-clock-original-case-result-v1",
        "ORIGINAL_CLOCK_SCOPE_VERIFIED_CLEAN",
    )?;
    exact(v, "kind", "alarm04")?;
    basic_case_closed(v)?;
    yes(
        v,
        &[
            "business_scope_completed",
            "task_set_restored",
            "protected_business_and_sound_state_preserved",
            "actual_firing_verified",
            "actual_alarm_notification_posted",
            "actual_alarm_window_observed",
            "actual_dismiss_effect_verified",
            "normal_close_reopen_time_and_timezone_preserved",
            "exact_owned_alarm_deleted",
            "owned_alarm_cleanup_verified",
            "empty_alarm_state_at_final_read",
        ],
    )?;
    keys(v, "pending", &["input", "effect", "close"])?;
    null(v, &["pending.input", "pending.effect", "pending.close"])?;
    equal(v, "identity_before", "identity_after")?;
    equal(v, "guard_before", "guard_after")?;
    let launched = array(v, "native_launched_tasks")?;
    let closed = array(v, "normally_closed_tasks")?;
    need(
        launched.len() == 2
            && launched[0] != launched[1]
            && launched.iter().all(positive_id)
            && launched.iter().all(|t| closed.contains(t)),
        "Clock alarm lacks both normal task closes",
    )?;
    let id = at(v, "owned_alarm_id")?;
    need(positive_id(id), "Clock alarm lacks its exact owned ID")?;
    for label in [
        "frozen-created",
        "after-normal-close",
        "fired",
        "dismissed",
        "reopened",
    ] {
        need(
            at(v, &format!("phases.{label}.alarm._id"))? == id,
            "Clock alarm state changed its owned identity",
        )?;
    }
    need(
        at(v, "phases.dismissed.alarm")? == at(v, "phases.reopened.alarm")?
            && number(v, "phases.reopened.alarm.enabled")? == 0,
        "Clock reopen did not preserve the dismissed alarm",
    )?;
    empty(
        v,
        &["phases.dismissed.instances", "phases.reopened.instances"],
    )?;
    let fired = array(v, "phases.fired.instances")?;
    need(
        fired.len() == 1
            && fired[0]["_id"] == *at(v, "owned_instance_id")?
            && fired[0]["alarm_state"] == 5,
        "Clock alarm delivery lacks its actual fired instance",
    )?;
    need(
        number(
            v,
            "runtime_evidence.final.commands.scheduler.clock_uid_current_pending_alarm_count",
        )? == 0,
        "Clock scheduler still retains an owned alarm",
    )?;
    no(
        v,
        &["runtime_evidence.final.commands.notifications.alarm_record.present"],
    )?;
    // The reader's pristine/deleted projections include all original template
    // identities and exact unchanged originals, not only the new alarm's ID.
    need(
        at(v, "phases.deleted")? == at(v, "final_alarm_readback")?,
        "Clock final owned alarm cleanup differs from its deletion proof",
    )?;
    need(
        at(v, "phases.before")? == at(v, "final_alarm_readback")?,
        "Clock deletion did not restore the exact original alarm summary",
    )?;
    let pristine = serde_json::json!({"template_count":2,"instance_count":0,"enabled_count":0,
        "original_enabled":0,"marker_count":0,"template_ids":[1,2],"instance_ids":[]});
    need(
        at(v, "final_alarm_readback")? == &pristine,
        "Clock original two disabled templates changed",
    )?;
    yes(
        v,
        &[
            "creation_native_ACK",
            "label_native_ACK",
            "dismiss_native_ACK",
            "delete_native_ACK",
        ],
    )?;
    null(v, &["owned_task_remaining"])?;
    need(
        number(v, "native_launch_calls")? == 2,
        "Clock alarm launch count changed",
    )?;
    Ok(())
}
fn basic_case_closed(v: &Value) -> Result<()> {
    yes(
        v,
        &[
            "case_business_success_verified",
            "final_source_and_identity_chain_unchanged",
            "actual_Main_and_APIs_closed",
            "whole_case_OFD_closed",
            "source_and_receipt_witness_closed",
        ],
    )?;
    empty(v, &["received_signals", "secondary_errors"])
}

const SAF_GATES: &[&str] = &[
    "NEW",
    "CREATE_WRITE_READ_OK",
    "PROVIDER_RENAME_OK",
    "FILES_UI_RENAME",
    "FILES_VIEW_OK",
    "OPEN_OK",
    "REOPEN_OK",
    "DELETE_PROVIDER_ACK",
    "PROVIDER_DELETE_AND_ABSENCE",
];
const SEARCH_GATES: &[&str] = &[
    "GET_CONTENT_CANCEL",
    "TREE_CANCEL",
    "EXACT_TREE_GRANT",
    "FILES_NEW_FOLDER",
    "FILES_MULTIPLE_COPY",
    "FILES_MULTIPLE_MOVE",
    "FILES_MULTIPLE_DELETE_COPIES",
    "NORMAL_CLOSE_REOPEN_APP_READBACK",
    "REVOKED_EXISTING_URI_SECURITY_DENIAL",
    "GET_CONTENT_EXACT_FILE_READ",
    "FILES_UI_FINAL_DELETE",
    "FINAL_GRANTS_EMPTY",
    "FILES_VISIBLE_SORT",
    "FILES_OWNED_SEARCH",
];
fn all_steps(v: &Value, names: &[&str]) -> Result<()> {
    keys(v, "gates", names)?;
    for name in names {
        yes(at(v, &format!("gates.{name}"))?, &["passed"])?;
    }
    Ok(())
}
fn fixture_run(v: &Value) -> Result<&str> {
    let run = text(v, "run")?;
    need(
        run.len() == 16
            && run
                .bytes()
                .all(|x| x.is_ascii_digit() || (b'a'..=b'f').contains(&x))
            && !["69814e80ea71f485", "eeff7aa90e47139a"].contains(&run),
        "Documents fixture does not have its original fresh run identity",
    )?;
    Ok(run)
}
fn documents_closed(v: &Value, launches: usize, max_actions: u64) -> Result<()> {
    basic_case_closed(v)?;
    yes(v, &["task_set_restored"])?;
    no(
        v,
        &[
            "install_pending",
            "uninstall_pending",
            "outcome_unknown",
            "host_cancellation_observed",
        ],
    )?;
    empty(v, &["cleanup.errors", "owned_tasks"])?;
    equal(v, "initial_guard", "final_guard")?;
    need(
        !object(v, "actual_final_caller")?.is_empty(),
        "Documents final actual caller absent",
    )?;
    let closed = array(v, "owned_task_ids_closed")?;
    let adopted = array(v, "source_bound_adopted_tasks")?;
    need(
        number(v, "native_launch_calls")? == launches as u64
            && number(v, "owned_remove_calls")? == closed.len() as u64
            && closed.len() == launches + adopted.len()
            && closed.iter().all(positive_id)
            && closed
                .iter()
                .map(Value::to_string)
                .collect::<BTreeSet<_>>()
                .len()
                == closed.len()
            && number(v, "ui_actions")? <= max_actions,
        "Documents did not close exactly its real native and adopted tasks",
    )?;
    Ok(())
}
fn documents_saf(v: &Value) -> Result<()> {
    terminal(
        v,
        "pocket4-final-documents-saf-original-case-result-v1",
        "ORIGINAL_SAF11_VERIFIED_CLEAN",
    )?;
    documents_closed(v, 2, 36)?;
    all_steps(v, SAF_GATES)?;
    yes(v, &["all_original_local_FDs_closed"])?;
    yes(
        v,
        &[
            "business_flow_completed",
            "cleanup.package_uninstalled_verified",
            "cleanup.package_absent_verified",
            "cleanup.staged_apk_removed",
            "cleanup.file_cleanup.directory_removed_verified",
        ],
    )?;
    no(v, &["cleanup.file_cleanup.fallback_file_unlink"])?;
    empty(v, &["pending_effects"])?;
    let run = fixture_run(v)?;
    let payload =
        format!("Pocket4 SAF fixture {run}\n中文 café 😀 — ContentResolver round trip.\n");
    need(payload.len() == 87, "fixed SAF content length changed")?;
    let digest = format!("{:x}", Sha256::digest(payload.as_bytes()));
    for name in [
        "NEW",
        "CREATE_WRITE_READ_OK",
        "PROVIDER_RENAME_OK",
        "FILES_VIEW_OK",
        "OPEN_OK",
        "REOPEN_OK",
        "DELETE_PROVIDER_ACK",
    ] {
        let status = at(v, &format!("gates.{name}.client_status"))?;
        exact(status, "run", run)?;
        exact(status, "phase", name)?;
        exact(status, "pending", "")?;
        exact(status, "error", "")?;
        if name != "NEW" {
            need(
                number(status, "bytes")? == 87 && text(status, "sha256")? == digest,
                "SAF callback did not read the fixed complete UTF-8 payload",
            )?;
        }
    }
    let rename = at(v, "gates.FILES_UI_RENAME")?;
    yes(rename, &["old_name_absent"])?;
    exact(rename, "new_name", &format!("files-ui-{run}.txt"))?;
    exact(rename, "sha256", &digest)?;
    yes(
        v,
        &[
            "gates.PROVIDER_DELETE_AND_ABSENCE.all_exact_paths_errno_ENOENT",
            "gates.PROVIDER_DELETE_AND_ABSENCE.grants_empty",
        ],
    )?;
    Ok(())
}
fn documents_search(v: &Value) -> Result<()> {
    terminal(
        v,
        "pocket4-final-documents-original-case-result-v1",
        "ORIGINAL_FEATURES_SEARCH_SORT_VERIFIED_CLEAN",
    )?;
    documents_closed(v, 3, 80)?;
    all_steps(v, SEARCH_GATES)?;
    yes(v, &["owned_tree_FDs_closed", "helper_stage_FDs_closed"])?;
    yes(
        v,
        &[
            "business_scope_completed",
            "cleanup.package.package_absent_verified",
            "cleanup.package.data_directories_absent",
            "cleanup.file_cleanup.removed",
            "cleanup.stage.staged_apk_removed",
        ],
    )?;
    need(
        number(v, "cleanup.file_cleanup.fallback_files_unlinked")? == 0,
        "Documents UI deletion was replaced by fallback unlink",
    )?;
    empty(v, &["ui_pending", "deferred_supported_features"])?;
    yes(
        v,
        &[
            "original_search_sort_state.sort_started",
            "original_search_sort_state.sort_completed",
            "original_search_sort_state.query_attempted",
            "original_search_sort_state.query_acknowledged",
            "original_search_sort_state.result_selected",
            "original_search_sort_state.search_completed",
        ],
    )?;
    no(
        v,
        &[
            "original_search_sort_state.sort_setting_may_differ",
            "original_search_sort_state.automatic_retry",
            "original_search_sort_state.cleanup_replays_search_or_sort",
        ],
    )?;
    null(v, &["file_operation_pending", "helper_pending"])?;
    let run = fixture_run(v)?;
    let alpha = format!("Pocket4 Documents {run} alpha\n中文 café 😀\n");
    let beta = format!(
        "Pocket4 Documents {run} beta\n中文 café 😀\nTwo generated payloads distinguish a correct copy and move.\n"
    );
    need(
        alpha.len() == 59 && beta.len() == 118,
        "fixed Documents source payload changed",
    )?;
    let digest = format!("{:x}", Sha256::digest(alpha.as_bytes()));
    for name in ["GET_CONTENT_CANCEL", "TREE_CANCEL"] {
        let g = at(v, &format!("gates.{name}"))?;
        yes(g, &["RESULT_CANCELED", "grants_empty"])?;
        no(g, &["URI_returned"])?;
    }
    let g = at(v, "gates.EXACT_TREE_GRANT")?;
    exact(g, "tree", &format!("primary:Pocket4_DocFeatures_r12_{run}"))?;
    no(g, &["broader_root_granted"])?;
    need(
        number(g, "persisted_read_write_grants")? == 1,
        "Documents tree grant is not exact",
    )?;
    let setup = at(v, "fixture_setup")?;
    need(
        number(setup, "provider_directory_creates")? == 1
            && number(setup, "provider_file_creates")? == 2
            && number(setup, "content_writes")? == 2
            && at(setup, "file_bytes")? == &serde_json::json!([59, 118]),
        "Documents fixture scope changed",
    )?;
    no(setup, &["App_UI_creation_credit"])?;
    let reopen = at(v, "gates.NORMAL_CLOSE_REOPEN_APP_READBACK")?;
    yes(reopen, &["same_generated_tree"])?;
    need(
        number(reopen, "expected_payloads_verified_by_app")? == 2
            && number(reopen, "content_readbacks_total")? == 4,
        "Documents reopen lacks both complete content reads",
    )?;
    let denied = at(v, "gates.REVOKED_EXISTING_URI_SECURITY_DENIAL")?;
    exact(denied, "existing_file", &format!("beta-{run}.txt"))?;
    exact(denied, "exception", "SecurityException")?;
    yes(
        denied,
        &[
            "persisted_grants_empty",
            "checked_before_any_GET_CONTENT_grant",
        ],
    )?;
    let read = at(v, "gates.GET_CONTENT_EXACT_FILE_READ")?;
    exact(read, "file", &format!("alpha-{run}.txt"))?;
    exact(read, "sha256", &digest)?;
    need(
        number(read, "bytes")? == 59 && number(read, "persisted_grants")? == 0,
        "GET_CONTENT did not read exactly the selected source payload",
    )?;
    yes(read, &["previous_tree_grant_absent"])?;
    yes(
        v,
        &[
            "gates.FINAL_GRANTS_EMPTY.all_owned_tasks_normally_closed",
            "gates.FINAL_GRANTS_EMPTY.URI_permission_section_empty",
        ],
    )?;
    let counters = [
        ("picker_calls", 4),
        ("get_cancel_results", 1),
        ("tree_cancel_results", 1),
        ("tree_grant_results", 1),
        ("persist_calls", 1),
        ("seed_calls", 1),
        ("provider_create_calls", 3),
        ("content_writes", 2),
        ("content_readbacks", 5),
        ("files_launch_calls", 2),
        ("files_verify_calls", 1),
        ("release_calls", 1),
        ("release_mutations", 1),
        ("denial_probes", 1),
        ("security_denials_observed", 1),
        ("get_content_results", 1),
    ];
    keys(
        v,
        "final_helper_counters",
        &counters.iter().map(|(k, _)| *k).collect::<Vec<_>>(),
    )?;
    for (key, value) in counters {
        need(
            number(v, &format!("final_helper_counters.{key}"))? == value,
            "Documents source-owned provider protocol is incomplete",
        )?;
    }
    // This fragment supplies navigation and grant-denial evidence. It cannot
    // grant documents.provider until the same-subject SAF create/open case joins.
    Ok(())
}

fn gallery_outer(v: &Value) -> Result<()> {
    terminal(
        v,
        "pocket4-gallery-image-scope-v1",
        "CURRENT_IMAGE_SCOPE_AND_CLEANUP_VERIFIED",
    )?;
    yes(
        v,
        &[
            "business_scope_completed",
            "current_image_owner_and_complete_bytes_preserved",
        ],
    )?;
    no(v, &["outcome_unknown"])?;
    empty(v, &["entry_cancellation_signals"])?;
    object(v, "business")?;
    Ok(())
}
fn gallery_contexts(v: &Value, owned: &str) -> Result<()> {
    yes(
        v,
        &[
            "business_scope_completed",
            "original_media_preserved",
            "held_session_closed",
            owned,
            "global_action_lock_exited",
            "source_unchanged",
            "all_case_acquired_FDs_closed",
        ],
    )?;
    no(
        v,
        &[
            "outcome_unknown",
            "host_cancellation_observed",
            "install_pending",
            "uninstall_pending",
        ],
    )?;
    empty(v, &["cleanup.errors", "cancelled_signals"])?;
    for (a, b) in [
        ("guard_before", "guard_after"),
        ("main_before", "main_after"),
        ("descriptor_table_before", "descriptor_table_after"),
    ] {
        equal(v, a, b)?;
    }
    for field in [
        "protected",
        "apk",
        "native_apk_payload",
        "code_and_install_metadata",
    ] {
        equal(
            v,
            &format!("identity_before.{field}"),
            &format!("identity_after.{field}"),
        )?;
    }
    Ok(())
}
fn image_proof(v: &Value, kind: &str, rotation: u64) -> Result<()> {
    exact(v, "render_scope", kind)?;
    need(
        number(v, "clockwise_degrees")? == rotation,
        "Gallery displayed the wrong rotation",
    )?;
    exact(v, "palette_source", "generated_owned_JPEG_before_UI")?;
    need(
        number(v, "color_tolerance")? == 6,
        "Gallery pixel reference was changed",
    )?;
    no(
        v,
        &[
            "thumbnail_crop_algorithm_qualified",
            "EXIF_or_MediaStore_qualified_by_this_function",
        ],
    )?;
    need(
        at(v, "full_image_verified")? == &Value::Bool(kind == "full")
            && at(v, "thumbnail_verified")? == &Value::Bool(kind == "thumbnail"),
        "Gallery confused a thumbnail with the full image",
    )?;
    let counts = array(v, "quadrant_counts")?;
    need(
        counts.len() == 4 && counts.iter().all(|n| n.as_u64().is_some_and(|n| n >= 40)),
        "Gallery did not observe all four owned color quadrants",
    )?;
    let expected = if rotation == 0 {
        ["red", "green", "blue", "yellow"]
    } else {
        ["blue", "red", "yellow", "green"]
    };
    need(
        at(v, "quadrant_order")? == &serde_json::json!(expected),
        "Gallery rendered a different quadrant order",
    )?;
    sha(v, "scope_sha256")?;
    sha(v, "png_sha256")?;
    need(
        !text(v, "context_token")?.is_empty(),
        "Gallery image lacks actual capture context",
    )?;
    Ok(())
}
fn gallery_image(v: &Value) -> Result<()> {
    terminal(
        v,
        "pocket4-current-owned-gallery-jpeg-rotation-v1",
        "OWNED_GALLERY_JPEG_ROTATION_REOPEN_AND_CLEANUP_VERIFIED",
    )?;
    gallery_contexts(v, "owned_media_FDs_closed")?;
    all_steps(
        v,
        &[
            "OWNED_ALBUM_ENUMERATION",
            "OWNED_JPEG_THUMBNAIL",
            "ORIGINAL_JPEG_FULL_DISPLAY",
            "UI_ROTATE_RIGHT_EXIF_INDEX_PIXELS",
            "ROTATED_JPEG_FULL_DISPLAY",
            "NORMAL_REOPEN_ROTATED_THUMBNAIL",
            "NORMAL_REOPEN_ROTATED_FULL_DISPLAY",
            "ORIGINAL_PNG_UNCHANGED",
        ],
    )?;
    empty(v, &["native_pending", "owned_tasks"])?;
    null(
        v,
        &[
            "helper_pending",
            "client_pending",
            "rotation_pending",
            "album_pending",
            "close_pending",
            "directory_pending",
        ],
    )?;
    yes(
        v,
        &[
            "cleanup.task_set_restored",
            "cleanup.package_cleanup.package_absent_verified",
            "cleanup.stage_cleanup.staged_apk_removed",
            "cleanup.media_cleanup.physical_and_indexed_owned_directories_absent",
        ],
    )?;
    need(
        number(v, "native_launches")? == 2 && number(v, "rotation_input_calls")? == 1,
        "Gallery image did not perform the fixed rotation and normal reopen sequence",
    )?;
    equal(v, "gallery_before", "gallery_after")?;
    equal(v, "native_actions_before", "native_actions_after")?;
    let enumeration = at(v, "gates.OWNED_ALBUM_ENUMERATION")?;
    yes(
        enumeration,
        &[
            "control_in_distinct_owned_bucket",
            "default_album_was_not_opened",
            "album_identity.album_name_derived_from_exact_description",
        ],
    )?;
    no(enumeration, &["album_identity.navigation_control_pressed"])?;
    need(
        positive_id(at(enumeration, "global_sole_copy_row._id")?),
        "Gallery image does not have its one actual owned MediaStore row",
    )?;
    let mut uri = None;
    for (key, kind, degrees) in [
        ("OWNED_JPEG_THUMBNAIL", "thumbnail", 0),
        ("ORIGINAL_JPEG_FULL_DISPLAY", "full", 0),
        ("ROTATED_JPEG_FULL_DISPLAY", "full", 90),
        ("NORMAL_REOPEN_ROTATED_THUMBNAIL", "thumbnail", 90),
        ("NORMAL_REOPEN_ROTATED_FULL_DISPLAY", "full", 90),
    ] {
        let proof = at(v, &format!("gates.{key}"))?;
        image_proof(proof, kind, degrees)?;
        let current = text(proof, "owned_uri")?;
        if let Some(old) = uri {
            need(
                old == current,
                "Gallery reopen selected a different owned image",
            )?;
        }
        uri = Some(current);
        need(
            text(proof, "album")? == text(enumeration, "album_identity.album_name")?,
            "Gallery pixels are not from the exact enumerated owned album",
        )?;
    }
    let rotation = at(v, "gates.UI_ROTATE_RIGHT_EXIF_INDEX_PIXELS")?;
    yes(
        rotation,
        &["raw_pixel_digest_unchanged", "ACK_alone_would_not_pass"],
    )?;
    need(
        number(rotation, "single_rotation_input")? == 1
            && number(rotation, "EXIF_orientation")? == 6
            && number(rotation, "MediaStore_orientation")? == 90,
        "Gallery edit lacks matching EXIF/provider effects",
    )?;
    object(rotation, "actual_media")?;
    let original = at(v, "gates.ORIGINAL_PNG_UNCHANGED")?;
    equal(original, "initial", "final")?;
    yes(original, &["full_png_bytes_sha256_identical"])?;
    need(
        number(original, "actual_bytes")? == 2416,
        "Gallery original control content changed",
    )?;
    Ok(())
}
fn f64_at(v: &Value, path: &str) -> Result<f64> {
    let x = at(v, path)?
        .as_f64()
        .ok_or_else(|| format!("native business expected number {path}"))?;
    need(x.is_finite(), "non-finite native observation")?;
    Ok(x)
}
fn advancing(v: &Value) -> Result<()> {
    yes(
        v,
        &[
            "pixel_timecode_advanced",
            "before.pattern.full_pattern_verified",
            "after.pattern.full_pattern_verified",
            "before.pattern.thumbnail_excluded",
            "after.pattern.thumbnail_excluded",
        ],
    )?;
    let before = number(v, "before.pattern.visual_second_code")?;
    let after = number(v, "after.pattern.visual_second_code")?;
    let elapsed = f64_at(v, "elapsed_seconds")?;
    need(
        before < 60
            && after < 60
            && after >= before + 2
            && (2.5..=12.0).contains(&elapsed)
            && (after as f64 - before as f64 - elapsed).abs() <= 2.0
            && number(v, "decoded_seconds_advanced")? == after - before,
        "Gallery video pixels did not advance with the actual observed interval",
    )?;
    for p in ["before.pixel_sha256", "after.pixel_sha256"] {
        sha(v, p)?;
    }
    Ok(())
}
fn proof_pin(v: &Value) -> Result<()> {
    need(
        number(v, "bytes")? > 0 && !text(v, "path")?.is_empty(),
        "empty original source evidence reference",
    )?;
    sha(v, "sha256")
}
fn gallery_album(v: &Value) -> Result<()> {
    terminal(
        v,
        "pocket4-gallery-current-owned-video-album-v1",
        "CURRENT_MAIN_VIDEO_ALBUM_THUMBNAIL_PLAY_PAUSE_RESUME_REOPEN_SEEK_CLEANUP_VERIFIED",
    )?;
    gallery_contexts(v, "owned_local_contexts_closed")?;
    yes(
        v,
        &[
            "cleanup.video_deleted",
            "cleanup.package_absent",
            "cleanup.staged_apk_removed",
            "owned_directory_removed",
            "seek_qualified",
            "album_enumeration_qualified",
            "diagnostics.clear",
        ],
    )?;
    no(v, &["audio_output_qualified"])?;
    null(v, &["pending_effect", "close_pending"])?;
    empty(v, &["outstanding_owned_tasks"])?;
    tasks(v, "owned_tasks", "normal_closed_tasks", 2)?;
    equal(v, "gallery_before", "gallery_after")?;
    equal(v, "native_actions_before", "native_actions_after")?;
    let rounds = array(v, "pixel_rounds")?;
    let albums = array(v, "album_checks")?;
    need(
        rounds.len() == 2 && albums.len() == 2,
        "Gallery video lacks both original normal rounds",
    )?;
    for (index, (round, album)) in rounds.iter().zip(albums).enumerate() {
        need(
            number(round, "index")? == index as u64
                && at(round, "task")? == &array(v, "owned_tasks")?[index]
                && number(album, "round")? == index as u64,
            "Gallery video round identity differs",
        )?;
        yes(round, &["normal_close_verified"])?;
        advancing(at(round, "initial_playback")?)?;
        yes(album, &["verified", "thumbnail.thumbnail_verified"])?;
        no(
            album,
            &["thumbnail_pressed", "default_album_pixels_captured"],
        )?;
        need(
            number(album, "new_UI_inputs")? == 0
                && number(album, "album_VIEW_intents")? == 1
                && positive_id(at(album, "actual_sole_bucket._id")?),
            "Gallery album fixture is not uniquely bound",
        )?;
        for pin in [
            "route",
            "route_after_pixels",
            "title",
            "title_after_pixels",
            "actual_owned_window_png",
        ] {
            proof_pin(at(album, pin)?)?;
        }
        sha(album, "owned_media_sha256")?;
        sha(album, "actual_scope_sha256")?;
        need(
            !text(album, "actual_context_token")?.is_empty(),
            "Gallery thumbnail lacks an actual context",
        )?;
        if index > 0 {
            for key in [
                "owned_media_uri",
                "owned_media_sha256",
                "actual_sole_bucket",
            ] {
                need(
                    at(album, key)? == at(&albums[0], key)?,
                    "Gallery normal reopen changed the owned clip",
                )?;
            }
        }
    }
    let pause = at(&rounds[0], "pause")?;
    yes(
        pause,
        &[
            "exact_application_pixels_stable",
            "playing_to_paused_control_verified",
        ],
    )?;
    no(pause, &["paused_timecode_decode_claimed"])?;
    equal(pause, "before.image_size", "after.image_size")?;
    equal(pause, "before.pixel_sha256", "after.pixel_sha256")?;
    sha(pause, "before.pixel_sha256")?;
    need(
        (2.5..=12.0).contains(&f64_at(pause, "elapsed_seconds")?),
        "Gallery pause lacks its actual bounded stable-pixel interval",
    )?;
    advancing(at(&rounds[0], "resume")?)?;
    let seek = at(v, "seek_observation")?;
    yes(
        seek,
        &["verified", "native_ack_alone_is_not_business_success"],
    )?;
    no(seek, &["audio_output_qualified"])?;
    need(
        at(&rounds[1], "seek")? == seek
            && number(seek, "minimum_discontinuity_margin_seconds")? == 5
            && f64_at(seek, "actual_discontinuity_margin_seconds")? >= 5.0,
        "Gallery seek did not change actual pixels beyond ordinary playback",
    )?;
    // This is only the video fragment. Image enumeration/full rendering/edit
    // remains mandatory in a distinct actual rotation case for all three gates.
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    // Synthetic parser and join fixtures are deliberately not LeafObservation,
    // PM/Main opaque tokens or runtime qualification. They exercise rejection
    // of incomplete/contradictory original result projections only.
    fn pin(name: &str) -> FilePin {
        FilePin {
            path: format!("/test/{name}").into(),
            bytes: 17,
            sha256: format!("{:x}", Sha256::digest(name.as_bytes())),
        }
    }
    fn mark(v: &mut Value, fields: &[&str], flag: bool) {
        for key in fields {
            v[*key] = Value::Bool(flag);
        }
    }
    fn result(schema: &str, state: &str, original: bool) -> Value {
        let mut v = json!({"schema":schema,"state":state,"whole_app_business_accepted":false,
            "automatic_retry":false,"secondary_errors":[],"received_signals":[],
            "guard_before":{"same":1},"guard_after":{"same":1}});
        mark(
            &mut v,
            &[
                "case_business_success_verified",
                "final_source_and_identity_chain_unchanged",
                "whole_case_OFD_closed",
            ],
            true,
        );
        if original {
            mark(
                &mut v,
                &[
                    "actual_Main_and_original_APIs_closed",
                    "evidence_witness_closed",
                ],
                true,
            );
        } else {
            mark(
                &mut v,
                &[
                    "actual_Main_and_APIs_closed",
                    "source_and_receipt_witness_closed",
                ],
                true,
            );
        }
        v
    }
    fn contact_row(name: &str) -> Value {
        let proof = json!({"raw_contact_id":"5","contact_id":"6","name_data_id":"7","name":name,"local_null_account":true});
        let name_row = json!({"_id":"7","raw_contact_id":"5","contact_id":"6","data1":name});
        json!({"proof":proof,"state":{"marker_rows":[name_row.clone()],
            "owned":{"name_row":name_row,"raw_contact":{"_id":"5","contact_id":"6",
                "account_name":null,"account_type":null,"data_set":null}}}})
    }
    fn contacts_fixture() -> Value {
        let mut v = result(
            "pocket4-final-original-system-case-result-v1",
            "ORIGINAL_CASE_VERIFIED_CLEAN",
            true,
        );
        v["kind"] = json!("contacts_search");
        mark(
            &mut v,
            &[
                "business_scope_completed",
                "cleanup_verified",
                "empty_baseline_verified",
                "edited_contact_found_by_search_and_reopened",
                "UI_delete_verified",
                "durable_contact_ownership",
            ],
            true,
        );
        for k in [
            "pending_input",
            "pending_close",
            "pending_database_effect",
            "owned_task_remaining",
        ] {
            v[k] = Value::Null;
        }
        v["native_launched_tasks"] = json!([10, 11]);
        v["normally_closed_tasks"] = json!([10, 11]);
        for prefix in ["native_actions", "account_topology"] {
            v[format!("{prefix}_before")] = json!({"same":1});
            v[format!("{prefix}_after")] = json!({"same":1});
        }
        let empty = json!({"raw_rows":[],"marker_rows":[],"owned":null});
        v["contacts_before"] = empty.clone();
        v["contacts_after"] = empty;
        let mut phases = json!({"save-created-committed":contact_row(CONTACT_NAME)});
        for tag in [
            "save-edited-committed",
            "persisted-after-normal-close",
            "persisted-after-reopen",
            "search-result-identity",
            "searched-detail-same-record",
            "before-delete-confirm",
        ] {
            phases[tag] = contact_row(CONTACT_EDITED);
        }
        v["phases"] = phases;
        v["search_result"] = json!({"query":CONTACT_EDITED,"same_contact":contact_row(CONTACT_EDITED)["proof"],
            "observed_node":{"text":CONTACT_EDITED,"content-desc":CONTACT_EDITED}});
        v["deleted_final_proof"] = json!({"active_owned_contact_absent":true,"owned_tombstone_count":0,
            "database_returned_to_empty":true});
        v["provider_cleanup_calls"] = json!(0);
        v
    }
    #[test]
    fn native_business_contacts_requires_same_provider_record_and_ui_cleanup() {
        let v = contacts_fixture();
        contacts(&v).unwrap();
        let mut changed = v.clone();
        changed["phases"]["persisted-after-reopen"]["proof"]["contact_id"] = json!("8");
        assert!(contacts(&changed).is_err());
        let mut fallback = v.clone();
        fallback["provider_cleanup_calls"] = json!(1);
        assert!(contacts(&fallback).is_err());
        let mut original = v;
        original["contacts_after"]["raw_rows"] = json!([{"_id":"99","deleted":"1"}]);
        assert!(contacts(&original).is_err());
    }

    fn calendar_fixture() -> Value {
        let mut v = result(
            "pocket4-final-original-system-case-result-v1",
            "ORIGINAL_CASE_VERIFIED_CLEAN",
            true,
        );
        v["kind"] = json!("calendar_core");
        mark(
            &mut v,
            &[
                "business_scope_completed",
                "task_set_restored",
                "host_preflight_before_first_UI_launch",
            ],
            true,
        );
        v["cleanup"] =
            json!({"calendar_removed":true,"provider_baseline_restored":true,"errors":[]});
        v["diagnostics"] = json!({"clear":true});
        v["ui_pending"] = json!({});
        v["owned_tasks"] = json!({});
        v["business_pending"] = Value::Null;
        v["empty_calendar_cleanup_pending"] = json!(false);
        v["native_launches"] = json!(2);
        v["normal_close_calls"] = json!(2);
        v["normally_closed_tasks"] = json!([20, 21]);
        v["final_counts"] = json!({"Events":0,"Reminders":0});
        for prefix in ["calendar", "provider", "native_actions"] {
            v[format!("{prefix}_before")] = json!({"same":1});
            v[format!("{prefix}_after")] = json!({"same":1});
        }
        let created = json!({"_id":7,"calendar_id":8,"title":"Pocket4 event calendar-recurrence21-6c978e4da120b35f"});
        let edited = json!({"_id":7,"calendar_id":8,"title":"Pocket4 event calendar-recurrence21-6c978e4da120b35f Edited",
            "eventTimezone":"Hongkong","rrule":"FREQ=DAILY","duration":"PT2700S","dtstart":100000000,
            "dtend":null,"_sync_id":null,"original_id":null,"allDay":0,"deleted":0,"hasAlarm":0});
        let provider = json!({"events":[edited]});
        let plan = json!({"dtstart":100000000,"first_end":102700000,"duration":"PT2700S",
            "rrule":"FREQ=DAILY","timezone":"Hongkong"});
        v["owned_event_id"] = json!(7);
        v["intended_series"] = plan.clone();
        v["host_series_preflight"] = json!({"verified":true,"plan":plan.clone()});
        v["gates"] = json!({
            "explicit_first_use_local_calendar":{"events":[]},"cancel_unsaved_without_event_write":{"events":[]},
            "created_in_calendar_ui":{"events":[created]},"edited_same_event":provider.clone(),
            "deleted_in_calendar_ui":{"events":[]},"edited_dates_timezone_recurrence":{"expected":plan,"provider":provider.clone()},
            "normal_close_reopen_detail":{"provider":provider.clone()},
            "later_occurrence_detail_does_not_change_series":{"provider_after_view":provider.clone(),"selected_occurrence_begin":186400000},
            "series_editor_uses_original_start":{"after_cancel_provider":provider,"series_row_unchanged":true,"no_series_probe_save":true}
        });
        v
    }
    fn reminder_fixture() -> Value {
        let mut v = calendar_fixture();
        v["schema"] = json!("pocket4-final-calendar-reminder22-current-result-v1");
        v["state"] = json!("OWNED_NATURAL_CALENDAR_REMINDER_AND_UI_DELETE_VERIFIED");
        v["kind"] = json!("calendar_reminder");
        let event = json!({"_id":9,"calendar_id":8});
        let normal = json!({"events":[event.clone()]});
        v["closed_event_persistence"] = normal.clone();
        v["gates"] = json!({"reminder_set_in_calendar_ui":normal,
            "ordinary_provider_reminder_fired_while_task_closed":{"events":[event],"owned_alerts":[{"event_id":9,"state":1}]},
            "exact_android_notification_delivered":{"present":true,"source_bound_uid_channel_title":true},
            "deleted_in_calendar_ui":{"events":[]},
            "owned_notification_removed_after_ui_delete":{"active_calendar_count":0}});
        v["notifications_after"] = json!({"active_calendar_count":0});
        v["system_timezone_before"] = json!("GMT");
        v["system_timezone_after"] = json!("GMT");
        v["calendar_uid_census_before"] = json!({"same_uid_packages":["com.android.calendar"]});
        v["calendar_uid_census_after"] = v["calendar_uid_census_before"].clone();
        v["runtime_evidence"] = json!({"synchronous_observer_closed":true});
        v["local_synchronous_observer_closed"] = json!(true);
        v["delivery_observations"] = json!([{"actual":1}]);
        v
    }
    #[test]
    fn native_business_calendar_requires_owned_recurrence_and_natural_delivery() {
        let v = calendar_fixture();
        calendar(&v).unwrap();
        let mut wrong = v;
        wrong["gates"]["edited_same_event"]["events"][0]["eventTimezone"] = json!("UTC");
        assert!(calendar(&wrong).is_err());
        let v = reminder_fixture();
        reminder(&v).unwrap();
        let mut wrong = v;
        wrong["gates"]["ordinary_provider_reminder_fired_while_task_closed"]["owned_alerts"][0]["event_id"] =
            json!(10);
        assert!(reminder(&wrong).is_err());
    }

    fn camera_fixture() -> Value {
        let mut v = result(
            "pocket4-final-camera-photo-display-result-v1",
            "PHOTO_AND_DISPLAY_VERIFIED_VISUAL_AND_OTHER_APP_GATES_PENDING",
            false,
        );
        mark(
            &mut v,
            &[
                "success",
                "photo_capture_persistence_verified",
                "display_lease_qualified",
                "one_new_image",
                "photo_persisted_after_close",
                "photo_persisted_after_reopen",
                "other_tasks_preserved",
                "installed_apk_and_data_identity_preserved",
                "provider_owner_preserved",
                "original_photo_state_machine_completed",
                "own_task_cleanup_verified",
                "current_Main_APIs_closed",
                "evidence_witness_closed",
            ],
            true,
        );
        mark(
            &mut v,
            &["prior_photos_modified_or_deleted", "outcome_unknown"],
            false,
        );
        v["pending_effects"] = json!({});
        v["owned_task_remaining"] = Value::Null;
        v["native_launch_calls"] = json!(2);
        v["own_task_remove_calls"] = json!(2);
        v["shutter_calls"] = json!(1);
        v["crash_observation"] = json!({"clear":true});
        v["provider_before"] = json!({"InvocationID":"session"});
        v["provider_after"] = v["provider_before"].clone();
        v["provider_owner"] = json!({"pid":123});
        v["new_media_row"] = json!({"_id":12,"owner_package_name":"com.android.camera2","mime_type":"image/jpeg",
            "is_pending":0,"_size":2000,"width":640,"height":480,"orientation":0});
        v["photo"] = json!({"bytes":2000,"fully_decoded":true,"sha256":"a".repeat(64),"dimensions":[640,480]});
        let proof = json!({"historical_frames_used":false,"actual_fixed_device_cycles":[{"current":1}],
            "invocation":"session","manager_pid":123,"start_monotonic_us":10,"end_monotonic_us":20,
            "original_provider_proof":{"physical_frames":3,"producer_frames":3,"physical_open_close_pairs":1,
                "producer_open_close_pairs":1,"capture_exit":0}});
        for key in ["first_provider", "reopened_provider"] {
            v[key] = proof.clone();
        }
        for key in ["first_preview", "reopened_preview"] {
            v[key] = json!({"shutter_ready":true,"screenshot_scope_sha256":"b".repeat(64)});
        }
        v
    }
    fn alarm_fixture() -> Value {
        let mut v = result(
            "pocket4-current-clock-original-case-result-v1",
            "ORIGINAL_CLOCK_SCOPE_VERIFIED_CLEAN",
            false,
        );
        v["kind"] = json!("alarm04");
        mark(
            &mut v,
            &[
                "business_scope_completed",
                "task_set_restored",
                "protected_business_and_sound_state_preserved",
                "actual_firing_verified",
                "actual_alarm_notification_posted",
                "actual_alarm_window_observed",
                "actual_dismiss_effect_verified",
                "normal_close_reopen_time_and_timezone_preserved",
                "exact_owned_alarm_deleted",
                "owned_alarm_cleanup_verified",
                "empty_alarm_state_at_final_read",
                "creation_native_ACK",
                "label_native_ACK",
                "dismiss_native_ACK",
                "delete_native_ACK",
            ],
            true,
        );
        v["pending"] = json!({"input":null,"effect":null,"close":null});
        v["owned_task_remaining"] = Value::Null;
        v["identity_before"] = json!({"same":1});
        v["identity_after"] = v["identity_before"].clone();
        v["native_launched_tasks"] = json!([31, 32]);
        v["normally_closed_tasks"] = json!([31, 33, 32]);
        v["native_launch_calls"] = json!(2);
        v["owned_alarm_id"] = json!(3);
        v["owned_instance_id"] = json!(5);
        let pristine = json!({"template_count":2,"instance_count":0,"enabled_count":0,"original_enabled":0,
            "marker_count":0,"template_ids":[1,2],"instance_ids":[]});
        let mut phases = json!({"before":pristine.clone(),"deleted":pristine.clone()});
        for tag in ["frozen-created", "after-normal-close"] {
            phases[tag] =
                json!({"alarm":{"_id":3,"enabled":1},"instances":[{"_id":5,"alarm_state":0}]});
        }
        phases["fired"] =
            json!({"alarm":{"_id":3,"enabled":1},"instances":[{"_id":5,"alarm_state":5}]});
        for tag in ["dismissed", "reopened"] {
            phases[tag] = json!({"alarm":{"_id":3,"enabled":0},"instances":[]});
        }
        v["phases"] = phases;
        v["final_alarm_readback"] = pristine;
        v["runtime_evidence"] = json!({"final":{"commands":{"scheduler":{"clock_uid_current_pending_alarm_count":0},
            "notifications":{"alarm_record":{"present":false}}}}});
        v
    }
    #[test]
    fn native_business_camera_and_alarm_require_actual_effect_and_preserved_originals() {
        let v = camera_fixture();
        camera(&v).unwrap();
        let mut wrong = v;
        wrong["reopened_provider"]["invocation"] = json!("other-session");
        assert!(camera(&wrong).is_err());
        let v = alarm_fixture();
        alarm(&v).unwrap();
        let mut wrong = v;
        wrong["final_alarm_readback"]["template_ids"] = json!([1, 3]);
        assert!(alarm(&wrong).is_err());
    }

    fn documents_fixture(search: bool) -> Value {
        let (schema, state) = if search {
            (
                "pocket4-final-documents-original-case-result-v1",
                "ORIGINAL_FEATURES_SEARCH_SORT_VERIFIED_CLEAN",
            )
        } else {
            (
                "pocket4-final-documents-saf-original-case-result-v1",
                "ORIGINAL_SAF11_VERIFIED_CLEAN",
            )
        };
        let mut v = result(schema, state, false);
        v["run"] = json!("1234567890abcdef");
        v["task_set_restored"] = json!(true);
        v["all_original_local_FDs_closed"] = json!(true);
        mark(
            &mut v,
            &[
                "install_pending",
                "uninstall_pending",
                "outcome_unknown",
                "host_cancellation_observed",
            ],
            false,
        );
        v["owned_tasks"] = json!({});
        v["initial_guard"] = json!({"same":1});
        v["final_guard"] = v["initial_guard"].clone();
        v["actual_final_caller"] = json!({"pid":100});
        v["source_bound_adopted_tasks"] = json!([]);
        let count = if search { 3 } else { 2 };
        v["native_launch_calls"] = json!(count);
        v["owned_remove_calls"] = json!(count);
        v["owned_task_ids_closed"] = if search {
            json!([41, 42, 43])
        } else {
            json!([41, 42])
        };
        v["ui_actions"] = json!(20);
        let mut gates = json!({});
        for key in if search { SEARCH_GATES } else { SAF_GATES } {
            gates[*key] = json!({"passed":true});
        }
        v["gates"] = gates;
        if !search {
            v["business_flow_completed"] = json!(true);
            v["cleanup"] = json!({"errors":[],"package_uninstalled_verified":true,"package_absent_verified":true,
                "staged_apk_removed":true,"file_cleanup":{"directory_removed_verified":true,"fallback_file_unlink":false}});
            v["pending_effects"] = json!({});
            let digest=format!("{:x}",Sha256::digest("Pocket4 SAF fixture 1234567890abcdef\n中文 café 😀 — ContentResolver round trip.\n".as_bytes()));
            for name in [
                "NEW",
                "CREATE_WRITE_READ_OK",
                "PROVIDER_RENAME_OK",
                "FILES_VIEW_OK",
                "OPEN_OK",
                "REOPEN_OK",
                "DELETE_PROVIDER_ACK",
            ] {
                v["gates"][name]["client_status"] = json!({"run":"1234567890abcdef","phase":name,
                    "pending":"","error":"","bytes":87,"sha256":digest});
            }
            v["gates"]["FILES_UI_RENAME"] = json!({"passed":true,"old_name_absent":true,
                "new_name":"files-ui-1234567890abcdef.txt","sha256":digest});
            v["gates"]["PROVIDER_DELETE_AND_ABSENCE"] =
                json!({"passed":true,"all_exact_paths_errno_ENOENT":true,"grants_empty":true});
        } else {
            mark(
                &mut v,
                &[
                    "business_scope_completed",
                    "owned_tree_FDs_closed",
                    "helper_stage_FDs_closed",
                ],
                true,
            );
            v["cleanup"] = json!({"errors":[],"package":{"package_absent_verified":true,"data_directories_absent":true},
                "file_cleanup":{"removed":true,"fallback_files_unlinked":0},"stage":{"staged_apk_removed":true}});
            v["ui_pending"] = json!({});
            v["deferred_supported_features"] = json!([]);
            v["file_operation_pending"] = Value::Null;
            v["helper_pending"] = Value::Null;
            v["original_search_sort_state"] = json!({"sort_started":true,"sort_completed":true,
                "query_attempted":true,"query_acknowledged":true,"result_selected":true,"search_completed":true,
                "sort_setting_may_differ":false,"automatic_retry":false,"cleanup_replays_search_or_sort":false});
            for key in ["GET_CONTENT_CANCEL", "TREE_CANCEL"] {
                v["gates"][key] = json!({"passed":true,"RESULT_CANCELED":true,
                "grants_empty":true,"URI_returned":false});
            }
            v["gates"]["EXACT_TREE_GRANT"] = json!({"passed":true,"tree":"primary:Pocket4_DocFeatures_r12_1234567890abcdef",
                "persisted_read_write_grants":1,"broader_root_granted":false});
            v["fixture_setup"] = json!({"provider_directory_creates":1,"provider_file_creates":2,
                "content_writes":2,"file_bytes":[59,118],"App_UI_creation_credit":false});
            v["gates"]["NORMAL_CLOSE_REOPEN_APP_READBACK"] = json!({"passed":true,"same_generated_tree":true,
                "expected_payloads_verified_by_app":2,"content_readbacks_total":4});
            v["gates"]["REVOKED_EXISTING_URI_SECURITY_DENIAL"] = json!({"passed":true,"existing_file":"beta-1234567890abcdef.txt",
                "exception":"SecurityException","persisted_grants_empty":true,"checked_before_any_GET_CONTENT_grant":true});
            let digest = format!(
                "{:x}",
                Sha256::digest(
                    "Pocket4 Documents 1234567890abcdef alpha\n中文 café 😀\n".as_bytes()
                )
            );
            v["gates"]["GET_CONTENT_EXACT_FILE_READ"] = json!({"passed":true,"file":"alpha-1234567890abcdef.txt",
                "sha256":digest,"bytes":59,"persisted_grants":0,"previous_tree_grant_absent":true});
            v["gates"]["FINAL_GRANTS_EMPTY"] = json!({"passed":true,"all_owned_tasks_normally_closed":true,"URI_permission_section_empty":true});
            v["final_helper_counters"] = json!({"picker_calls":4,"get_cancel_results":1,"tree_cancel_results":1,
                "tree_grant_results":1,"persist_calls":1,"seed_calls":1,"provider_create_calls":3,"content_writes":2,
                "content_readbacks":5,"files_launch_calls":2,"files_verify_calls":1,"release_calls":1,
                "release_mutations":1,"denial_probes":1,"security_denials_observed":1,"get_content_results":1});
        }
        v
    }
    #[test]
    fn native_business_documents_rejects_content_grant_or_cleanup_substitution() {
        let v = documents_fixture(false);
        documents_saf(&v).unwrap();
        let mut wrong = v;
        wrong["gates"]["REOPEN_OK"]["client_status"]["sha256"] = json!("0".repeat(64));
        assert!(documents_saf(&wrong).is_err());
        let v = documents_fixture(true);
        documents_search(&v).unwrap();
        let mut wrong = v;
        wrong["gates"]["EXACT_TREE_GRANT"]["broader_root_granted"] = json!(true);
        assert!(documents_search(&wrong).is_err());
        let mut wrong = documents_fixture(true);
        wrong["cleanup"]["file_cleanup"]["fallback_files_unlinked"] = json!(1);
        assert!(documents_search(&wrong).is_err());
    }

    fn image_fixture(kind: &str, degrees: u64) -> Value {
        json!({"render_scope":kind,"clockwise_degrees":degrees,"palette_source":"generated_owned_JPEG_before_UI",
            "color_tolerance":6,"thumbnail_crop_algorithm_qualified":false,
            "EXIF_or_MediaStore_qualified_by_this_function":false,"full_image_verified":kind=="full",
            "thumbnail_verified":kind=="thumbnail","quadrant_counts":[50,50,50,50],
            "quadrant_order":if degrees==0 {vec!["red","green","blue","yellow"]}else{vec!["blue","red","yellow","green"]},
            "scope_sha256":"a".repeat(64),"png_sha256":"b".repeat(64),"context_token":"actual-context"})
    }
    fn advancing_fixture() -> Value {
        let pattern = |second| json!({"full_pattern_verified":true,"thumbnail_excluded":true,"visual_second_code":second});
        json!({"pixel_timecode_advanced":true,"elapsed_seconds":3.0,"decoded_seconds_advanced":3,
            "before":{"pattern":pattern(10),"pixel_sha256":"a".repeat(64)},
            "after":{"pattern":pattern(13),"pixel_sha256":"b".repeat(64)}})
    }
    #[test]
    fn native_business_gallery_pixels_require_full_scope_rotation_and_time_advance() {
        image_proof(&image_fixture("full", 90), "full", 90).unwrap();
        let mut thumb = image_fixture("thumbnail", 90);
        assert!(image_proof(&thumb, "full", 90).is_err());
        thumb["quadrant_order"] = json!(["red", "green", "blue", "yellow"]);
        assert!(image_proof(&thumb, "thumbnail", 90).is_err());
        let v = advancing_fixture();
        advancing(&v).unwrap();
        let mut still = v;
        still["after"]["pattern"]["visual_second_code"] = json!(10);
        assert!(advancing(&still).is_err());
    }

    fn subject(package: &str) -> Subject {
        Subject {application:serde_json::from_value(json!({"package":package,"user":0,"uid":10101,"version_code":37,
            "epoch":{"boot_id":"00000000-0000-0000-0000-000000000001","cell_host_pid":10,
                "framework_host_pid":11,"framework_start_ticks":1234},
            "apks":[{"name":"base.apk","path":"/system/app/test/base.apk","bytes":100,"sha256":"a".repeat(64)}]})).unwrap(),
            main:json!({"actual_comparison_fixture":1}),selection:pin("selection"),catalog_sha256:"b".repeat(64)}
    }
    fn case(route: Route, fragment: Fragment, name: &str) -> NativeCaseEvidence {
        NativeCaseEvidence {
            subject: subject(route.package()),
            route,
            request: pin(&format!("{name}-request")),
            result: pin(name),
            preparation: pin(&format!("{name}-prep")),
            entry: pin(&format!("{name}-entry")),
            checked: CheckedCase {
                gates: BTreeSet::new(),
                fragments: BTreeSet::from([fragment]),
            },
        }
    }
    #[test]
    fn native_business_fragments_cannot_grant_a_whole_gate_or_cross_subjects() {
        let a = case(Route::GalleryRotation, Fragment::GalleryImage, "image");
        let mut b = case(Route::GalleryAlbum, Fragment::GalleryVideo, "video");
        assert!(join_cases(&[&a]).unwrap().is_empty());
        assert!(join_cases(&[&b]).unwrap().is_empty());
        let gates = join_cases(&[&a, &b]).unwrap();
        assert_eq!(
            gates
                .iter()
                .map(NativeBusinessFact::gate)
                .collect::<BTreeSet<_>>(),
            BTreeSet::from(["gallery.enumeration", "gallery.open", "gallery.persist"])
        );
        b.subject.application.epoch.framework_start_ticks += 1;
        assert!(join_cases(&[&a, &b]).is_err());
        b.subject = a.subject.clone();
        b.subject
            .application
            .apks
            .push(b.subject.application.apks[0].clone());
        assert!(join_cases(&[&a, &b]).is_err());
        assert!(join_cases(&[&a, &a]).is_err());
        let a = case(Route::DocumentsSaf, Fragment::DocumentsCreateOpen, "saf");
        let b = case(
            Route::DocumentsSearchSort,
            Fragment::DocumentsNavigation,
            "search",
        );
        assert!(join_cases(&[&a]).unwrap().is_empty());
        assert_eq!(
            join_cases(&[&a, &b]).unwrap()[0].gate(),
            "documents.provider"
        );
        let wrong = case(Route::GalleryAlbum, Fragment::GalleryVideo, "foreign");
        assert!(join_cases(&[&a, &wrong]).is_err());
    }
    #[test]
    fn native_business_compiled_sources_and_partial_profiles_remain_closed() {
        let (_, catalog) = leaf_routes::compiled_release_sources();
        let rows: Vec<Value> = serde_json::from_str(catalog).unwrap();
        assert_eq!(rows.len(), 14);
        for route in [
            Route::ContactsSearch,
            Route::CalendarCore,
            Route::CalendarReminder,
            Route::CameraPhoto,
            Route::ClockAlarm,
            Route::DocumentsSaf,
            Route::DocumentsSearchSort,
            Route::GalleryRotation,
            Route::GalleryVideo,
            Route::GallerySeek,
            Route::GalleryAlbum,
        ] {
            let row = rows
                .iter()
                .find(|r| r["index"] == source_index(route))
                .unwrap();
            let _: FilePin = serde_json::from_value(row["preparation"].clone()).unwrap();
            let _: FilePin = serde_json::from_value(row["entry"].clone()).unwrap();
            assert!(expected_engine_points(route).unwrap() > 0);
            assert!(
                validate_case(
                    route,
                    &json!({"passed":true,"whole_app_business_accepted":true})
                )
                .is_err()
            );
        }
        for route in [
            Route::ClockTimer,
            Route::ClockTimerPair,
            Route::ClockTimerRemaining,
            Route::ClockExpiry,
            Route::SettingsSupportedPages,
            Route::IhgLondon,
        ] {
            assert!(expected_engine_points(route).is_none());
            let parsed = validate_case(route, &json!({"passed":true})).unwrap();
            assert!(parsed.gates.is_empty() && parsed.fragments.is_empty());
        }
    }
}
