//! Source-owned, reversible native Family UI and separate-reopen facts.
//!
//! The only constructor below borrows the normal Main/complete-PM/data context.
//! A compiled control plan chooses comparison vocabulary, never PID, command,
//! live authority, or a pass. Every Android operation uses the original UI
//! owner, actual task, held entry/program inputs and original absolute end.
use super::*;
use crate::control::application_probe::ApplicationInspection;
use serde_json::{json, Value};
#[path = "native_application_ui_family_controls.rs"]
mod controls;
use controls::{Control, Locator, Mode, Plan};

const OPEN_SECONDS: u64 = 250 + 3 * 15 + 250 + 250 + 2 * 15 + 70;
const FINISH_SECONDS: u64 = 250 + 70 + 250 + 70 + 60;
const UI_QUERY_SECONDS: u64 = 2 * 15 + 70;
const PIXEL_SECONDS: u64 = 2 * 15 + 2 * 15 + 2 * 15 + 20;
const DISCOVERY_SECONDS: u64 =
    UI_QUERY_SECONDS + controls::MAX_NAVIGATIONS as u64 * 2 * UI_QUERY_SECONDS;
const FIRST_LOCAL_SECONDS: u64 = 120;
const SECOND_LOCAL_SECONDS: u64 = 60;
const FIRST_MAX_COMMANDS: u32 = 111;
const SECOND_MAX_COMMANDS: u32 = 64;

/// Existing stability, two normal opens/closes, four scoped pixel observations,
/// two source-fixed text replacements, their exact native readbacks, and at
/// most two non-submitting navigations per session. No timeout is renewed.
pub fn family_ui_window_seconds() -> u64 {
    2 * OPEN_SECONDS + 2 * FINISH_SECONDS + stability_additional_window_seconds()
        + 2 * DISCOVERY_SECONDS
        + 2 * (2 * UI_QUERY_SECONDS) // compare-before + one set-text per replacement
        + 2 * UI_QUERY_SECONDS       // actual readback after both replacements
        + 4 * UI_QUERY_SECONDS       // native control after each scoped capture
        + 4 * PIXEL_SECONDS
        + FIRST_LOCAL_SECONDS + SECOND_LOCAL_SECONDS
}
fn second_window_seconds() -> u64 {
    OPEN_SECONDS
        + DISCOVERY_SECONDS
        + UI_QUERY_SECONDS
        + PIXEL_SECONDS
        + FINISH_SECONDS
        + SECOND_LOCAL_SECONDS
}
/// Finite source upper bound on both immutable UI journals and retained image
/// descriptors. The separate normal permission/account window adds its own.
pub fn family_ui_retained_members_bound() -> usize {
    4 * (FIRST_MAX_COMMANDS + SECOND_MAX_COMMANDS) as usize + 64 + 4
}
fn require_window(now: Instant, end: Instant, baseline_end: Instant) -> Result<Instant, String> {
    need(
        now < end
            && end <= baseline_end
            && end.duration_since(now) <= Duration::from_secs(family_ui_window_seconds()),
        "Family UI needs the existing bounded original case end",
    )?;
    end.checked_sub(Duration::from_secs(second_window_seconds()))
        .filter(|v| *v > now)
        .ok_or_else(|| {
            "Family original window cannot reserve its separate reopen and normal close".into()
        })
}
fn same_reopen(
    first: &NativeUiTranscript,
    second: &NativeUiTranscript,
    end: Instant,
) -> Result<(), String> {
    need(
        first.engine().application() == second.engine().application()
            && first.engine().facts().main == second.engine().facts().main
            && first.task() != second.task()
            && first.journal() != second.journal()
            && first.journal_custody.identity[..2] != second.journal_custody.identity[..2]
            && first.opened_at < first.finished_at
            && first.finished_at < second.opened_at
            && second.opened_at < second.finished_at
            && first.finished_at < first.original_end
            && second.finished_at < second.original_end
            && first.original_end <= end
            && second.original_end == end,
        "Family reopening must be a later distinct actual task/journal of the same complete Main/PM",
    )?;
    Ok(())
}

struct PixelRecord {
    held: RetainedScopedWindowPixels,
    native_readback_sha256: String,
    control_region_sha256: Option<String>,
}
impl PixelRecord {
    fn comparison(&self) -> Result<Value, String> {
        Ok(json!({"pixels":self.held.comparison()?,
            "native_readback_sha256":self.native_readback_sha256,
            "control_region_sha256":self.control_region_sha256}))
    }
}
struct ControlSnapshot {
    control: Control,
    pixels: PixelRecord,
}
struct TextFirst {
    before: ControlSnapshot,
    edited: ControlSnapshot,
    restored: ControlSnapshot,
    apply_delta: Value,
    restore_delta: Value,
}
struct PanelFirst {
    before: PixelRecord,
    after: PixelRecord,
    panel: Value,
}
enum FirstProof {
    Text(TextFirst),
    Panel(PanelFirst),
}
enum ReopenedProof {
    Text(ControlSnapshot),
    Panel { pixels: PixelRecord, panel: Value },
}
struct Discovery {
    navigations: Vec<Locator>,
    initial_native_sha256: String,
}
fn native_hash(body: &Value) -> Result<String, String> {
    Ok(controls::hash(
        &serde_json::to_vec(body).map_err(|e| e.to_string())?,
    ))
}
fn describe_control(c: &Control) -> Value {
    json!({"selector":c.locator.comparison(),"resource_id":c.resource_id,
        "class":c.class,"hint":c.hint,"bounds":c.bounds,"window_id":c.window_id,
        "value_bytes":c.value.len(),"value_sha256":controls::hash(c.value.as_bytes()),
        "value_is_original_non_password_input":true})
}
fn discover(
    session: &mut NativeUiSession<'_, '_>,
    inspector: &NativeApplicationInspector,
    p: &Plan,
) -> Result<(Control, Discovery), String> {
    let mut dump = session.dump(inspector)?;
    let initial = native_hash(dump.body())?;
    let mut navigations = Vec::new();
    loop {
        if let Some(control) = controls::editor(dump.body(), p)? {
            return Ok((
                control,
                Discovery {
                    navigations,
                    initial_native_sha256: initial,
                },
            ));
        }
        need(
            navigations.len() < controls::MAX_NAVIGATIONS,
            "selected Family source editor was not reached within its fixed navigation bound",
        )?;
        let target=controls::opener(dump.body(),p,&navigations)?
            .ok_or("selected Family source has no unique non-submitting navigation control in this actual tree")?;
        let result = session.click(inspector, target.selector()?)?;
        session.journal.json(
            &format!("FAMILY-NAVIGATION-{}.json", navigations.len() + 1),
            &json!({"source_plan_sha256":controls::plan_digest(),"selector":target.comparison(),
                "actual_reply_sha256":native_hash(result.body())?,
                "submitted_query":false,"account_or_transaction_action":false}),
        )?;
        navigations.push(target);
        dump = session.dump(inspector)?;
    }
}
fn capture_control(
    session: &mut NativeUiSession<'_, '_>,
    inspector: &NativeApplicationInspector,
    p: &Plan,
    prior: &Control,
    label: &str,
) -> Result<(ControlSnapshot, Vec<u8>), String> {
    session.guard(inspector, session.work_end)?;
    let pixels = session.scoped_window_pixels(inspector)?;
    let comparison = pixels.comparison()?;
    need(
        comparison["window"]["package"] == p.package,
        "Family scoped pixels belong to a different actual package window",
    )?;
    let crop = controls::region_pixels(
        pixels.rgb(),
        pixels.width(),
        pixels.height(),
        &comparison["window"],
        prior.bounds,
    )?;
    let region = controls::hash(&crop);
    let pixels = pixels.into_retained()?;
    // The new native observation closes the pixel interval. Its actual window
    // id and bounds must still equal the native control sampled before capture.
    let reply = session.find(inspector, prior.locator.selector()?)?;
    let now = controls::readback(reply.body(), p, prior, &prior.value, true)?;
    need(
        now.bounds == prior.bounds,
        "actual Family editor moved during the scoped pixel observation",
    )?;
    let native = native_hash(reply.body())?;
    session.journal.json(
        label,
        &json!({"control":describe_control(&now),
        "actual_native_sha256":native,"region_sha256":region,
        "actual_scoped_pixels":pixels.comparison()?,"comparison_only":true}),
    )?;
    session.guard(inspector, session.work_end)?;
    Ok((
        ControlSnapshot {
            control: now,
            pixels: PixelRecord {
                held: pixels,
                native_readback_sha256: native,
                control_region_sha256: Some(region),
            },
        },
        crop,
    ))
}
fn replace_exact(
    session: &mut NativeUiSession<'_, '_>,
    inspector: &NativeApplicationInspector,
    p: &Plan,
    prior: &Control,
    expected: &str,
    replacement: &str,
) -> Result<(), String> {
    need(
        !session.poisoned && !session.cleanup_started,
        "Family refuses another input after an uncertain operation or cleanup",
    )?;
    let selector = prior.locator.selector()?;
    let before = session.find(inspector, selector.clone())?;
    let actual = controls::readback(before.body(), p, prior, expected, true)?;
    need(
        actual.bounds == prior.bounds,
        "Family refuses to overwrite a moved or concurrently changed editor",
    )?;
    // No arbitrary string/selector enters this factory: replacement is either
    // the fixed canary or the exact bounded original value read from this app.
    session.ui(
        inspector,
        wire::Operation::SetText {
            selector,
            value: replacement.into(),
        },
    )?;
    Ok(())
}
fn post_replace(
    session: &mut NativeUiSession<'_, '_>,
    inspector: &NativeApplicationInspector,
    p: &Plan,
    prior: &Control,
    expected: &str,
    label: &str,
) -> Result<(ControlSnapshot, Vec<u8>), String> {
    let actual = session.find(inspector, prior.locator.selector()?)?;
    let control = controls::readback(actual.body(), p, prior, expected, true)?;
    need(
        control.bounds == prior.bounds,
        "Family input control moved after its actual replacement",
    )?;
    capture_control(session, inspector, p, &control, label)
}
/// Preserve the earliest actual input/readback error even when the diagnostic
/// record also fails. This combines completed results; it performs no operation
/// and never retries the original replacement or its one restoration branch.
fn ordered_input_readbacks<T>(
    edited: Result<T, String>,
    restored: Result<T, String>,
    recorded: Result<(), String>,
) -> Result<(T, T), String> {
    match (edited, restored, recorded) {
        (Err(first), restored, recorded) => Err(format!(
            "{first}; original restore completed={}; restore error={:?}; input record error={:?}",
            restored.is_ok(),
            restored.err(),
            recorded.err(),
        )),
        (Ok(_), Err(first), recorded) => {
            Err(format!("{first}; input record error={:?}", recorded.err(),))
        }
        (Ok(_), Ok(_), Err(record)) => Err(record),
        (Ok(edited), Ok(restored), Ok(())) => Ok((edited, restored)),
    }
}
fn first_text(
    session: &mut NativeUiSession<'_, '_>,
    inspector: &NativeApplicationInspector,
    p: &Plan,
) -> Result<(FirstProof, Discovery), String> {
    let (control, discovery) = discover(session, inspector, p)?;
    let (original, original_crop) =
        capture_control(session, inspector, p, &control, "FAMILY-ORIGINAL.json")?;
    let canary = controls::canary(p, &original.control.value);
    replace_exact(
        session,
        inspector,
        p,
        &original.control,
        &original.control.value,
        canary,
    )?;
    let edited = post_replace(
        session,
        inspector,
        p,
        &original.control,
        canary,
        "FAMILY-EDITED.json",
    );
    // One restoration attempt belongs to the original actual replacement.
    // If a read/pixel check fails after the known successful mutation, retain
    // that first error and try only this exact restore while original custody
    // remains certain. Unknown mutation outcomes are never retried or hidden.
    let mut restore_replacement_completed = false;
    let restored = (|| {
        replace_exact(
            session,
            inspector,
            p,
            &original.control,
            canary,
            &original.control.value,
        )?;
        restore_replacement_completed = true;
        post_replace(
            session,
            inspector,
            p,
            &original.control,
            &original.control.value,
            "FAMILY-RESTORED.json",
        )
    })();
    let recorded = session.journal.json(
        "FAMILY-INPUT-RESULT.json",
        &json!({
        "canary_replacement_completed":true,"restore_source_branch_entered":true,
        "restore_replacement_completed":restore_replacement_completed,
        "canary_readback_and_pixels":edited.is_ok(),
        "original_restored_and_reobserved":restored.is_ok(),
        "first_error":edited.as_ref().err(),"restore_error":restored.as_ref().err(),
        "automatic_retry":false,"form_submission_performed":false,
        "business_or_account_action":false}),
    );
    let ((edited, edited_crop), (restored, restored_crop)) =
        ordered_input_readbacks(edited, restored, recorded)?;
    let apply = controls::rendered_change(&original_crop, &edited_crop, original.control.bounds)?;
    let restore = controls::rendered_change(&edited_crop, &restored_crop, original.control.bounds)?;
    Ok((
        FirstProof::Text(TextFirst {
            before: original,
            edited,
            restored,
            apply_delta: apply,
            restore_delta: restore,
        }),
        discovery,
    ))
}
fn panel_pixels(
    session: &mut NativeUiSession<'_, '_>,
    inspector: &NativeApplicationInspector,
    p: &Plan,
    expected: Option<&Value>,
    label: &str,
) -> Result<(PixelRecord, Option<Value>), String> {
    let pixels = session.scoped_window_pixels(inspector)?.into_retained()?;
    let reply = session.dump(inspector)?;
    let observed = controls::panel(reply.body(), p)?;
    if let Some(wanted) = expected {
        need(
            observed.as_ref() == Some(wanted),
            "source-fixed read-only panel changed during actual scoped pixels",
        )?;
    }
    let native = native_hash(reply.body())?;
    session.journal.json(
        label,
        &json!({"native_sha256":native,
        "actual_panel":observed,"actual_scoped_pixels":pixels.comparison()?,
        "comparison_only":true}),
    )?;
    Ok((
        PixelRecord {
            held: pixels,
            native_readback_sha256: native,
            control_region_sha256: None,
        },
        observed,
    ))
}
fn first_panel(
    session: &mut NativeUiSession<'_, '_>,
    inspector: &NativeApplicationInspector,
    p: &Plan,
) -> Result<(FirstProof, Discovery), String> {
    let home = session.dump(inspector)?;
    let initial = native_hash(home.body())?;
    let target = controls::opener(home.body(), p, &[])?
        .ok_or("source-fixed self-check navigation control is unavailable or ambiguous")?;
    let (before, _) = panel_pixels(session, inspector, p, None, "FAMILY-PANEL-BEFORE.json")?;
    session.click(inspector, target.selector()?)?;
    let after = session.dump(inspector)?;
    let panel = controls::panel(after.body(), p)?
        .ok_or("actual source-fixed self-check panel did not appear after its own navigation")?;
    let (after, _) = panel_pixels(
        session,
        inspector,
        p,
        Some(&panel),
        "FAMILY-PANEL-AFTER.json",
    )?;
    need(
        before.held.pixels_sha256() != after.held.pixels_sha256(),
        "source-fixed self-check input had no actual rendered effect",
    )?;
    Ok((
        FirstProof::Panel(PanelFirst {
            before,
            after,
            panel,
        }),
        Discovery {
            navigations: vec![target],
            initial_native_sha256: initial,
        },
    ))
}
fn reopen_text(
    session: &mut NativeUiSession<'_, '_>,
    inspector: &NativeApplicationInspector,
    p: &Plan,
    first: &TextFirst,
) -> Result<(ReopenedProof, Discovery), String> {
    let (control, discovery) = discover(session, inspector, p)?;
    need(
        control.value == first.before.control.value
            && control.resource_id == first.before.control.resource_id
            && control.class == first.before.control.class
            && control.hint == first.before.control.hint
            && control.locator == first.before.control.locator,
        "separate normal reopen did not preserve the exact restored source control/value",
    )?;
    let (observed, _) = capture_control(session, inspector, p, &control, "FAMILY-REOPENED.json")?;
    Ok((ReopenedProof::Text(observed), discovery))
}
fn reopen_panel(
    session: &mut NativeUiSession<'_, '_>,
    inspector: &NativeApplicationInspector,
    p: &Plan,
    first: &PanelFirst,
) -> Result<(ReopenedProof, Discovery), String> {
    let mut dump = session.dump(inspector)?;
    let initial = native_hash(dump.body())?;
    let mut navigations = Vec::new();
    loop {
        if let Some(panel) = controls::panel(dump.body(), p)? {
            need(
                panel == first.panel,
                "separate normal reopen changed the exact read-only self-check state",
            )?;
            let (pixels, _) = panel_pixels(
                session,
                inspector,
                p,
                Some(&panel),
                "FAMILY-PANEL-REOPENED.json",
            )?;
            return Ok((
                ReopenedProof::Panel { pixels, panel },
                Discovery {
                    navigations,
                    initial_native_sha256: initial,
                },
            ));
        }
        need(
            navigations.len() < controls::MAX_NAVIGATIONS,
            "source-fixed self-check reopen exceeded its navigation bound",
        )?;
        let target = controls::opener(dump.body(), p, &navigations)?
            .ok_or("source-fixed self-check control is unavailable on separate reopen")?;
        session.click(inspector, target.selector()?)?;
        navigations.push(target);
        dump = session.dump(inspector)?;
    }
}

/// Opaque history from the actual two-session source-owned normal executor.
/// There is no Deserialize, Clone, caller receipt, passed map or public ctor.
pub struct NativeFamilyUiEvidence {
    stability: NativeUiStabilityEvidence,
    reopened: RetainedNativeUiTranscript,
    first: FirstProof,
    second: ReopenedProof,
    first_discovery: Discovery,
    second_discovery: Discovery,
    original_end: Instant,
}
impl NativeFamilyUiEvidence {
    pub fn stability(&self) -> &NativeUiStabilityEvidence {
        &self.stability
    }
    pub fn reopened(&self) -> &RetainedNativeUiTranscript {
        &self.reopened
    }
    pub fn require_subject(
        &self,
        main: &RuntimeMainCustody,
        app: &ApplicationInspection,
    ) -> Result<(), String> {
        self.stability.require_subject(main, app)?;
        self.reopened.require_subject(main, app)?;
        self.guard_immutable()
    }
    pub fn guard_immutable(&self) -> Result<(), String> {
        self.stability.guard_immutable()?;
        self.reopened.guard_immutable()?;
        let a = self.stability.transcript();
        let b = self.reopened.transcript();
        same_reopen(a, b, self.original_end)?;
        let p = controls::plan(a.engine().application())?;
        need(
            self.first_discovery.navigations.len() <= controls::MAX_NAVIGATIONS
                && self.second_discovery.navigations.len() <= controls::MAX_NAVIGATIONS
                && a.operations() <= FIRST_MAX_COMMANDS
                && b.operations() <= SECOND_MAX_COMMANDS,
            "Family retained operation sequence exceeds its fixed source bound",
        )?;
        let writes = match (&self.first, &self.second) {
            (FirstProof::Text(first), ReopenedProof::Text(second)) => {
                need(
                    p.mode != Mode::ReadOnlyPanel
                        && first.before.control.value == first.restored.control.value
                        && first.before.control.hint == first.restored.control.hint
                        && first.before.control.value == second.control.value
                        && first.edited.control.value
                            == controls::canary(&p, &first.before.control.value)
                        && first.edited.control.value != first.before.control.value,
                    "Family exact input/restore/reopen chain is incomplete",
                )?;
                for v in [&first.before, &first.edited, &first.restored] {
                    v.pixels.held.require_transcript(a)?;
                    need(
                        v.control.resource_id == first.before.control.resource_id
                            && v.control.locator == first.before.control.locator
                            && v.control.class == first.before.control.class
                            && v.control.window_id == first.before.control.window_id
                            && v.control.bounds == first.before.control.bounds,
                        "Family first-session control/window identity changed",
                    )?;
                }
                need(
                    second.control.resource_id == first.before.control.resource_id
                        && second.control.locator == first.before.control.locator
                        && second.control.class == first.before.control.class
                        && second.control.hint == first.before.control.hint,
                    "Family reopened source control is different",
                )?;
                second.pixels.held.require_transcript(b)?;
                need(
                    first.apply_delta["before_region_sha256"].as_str()
                        == first.before.pixels.control_region_sha256.as_deref()
                        && first.apply_delta["after_region_sha256"].as_str()
                            == first.edited.pixels.control_region_sha256.as_deref()
                        && first.restore_delta["before_region_sha256"].as_str()
                            == first.edited.pixels.control_region_sha256.as_deref()
                        && first.restore_delta["after_region_sha256"].as_str()
                            == first.restored.pixels.control_region_sha256.as_deref(),
                    "Family rendered deltas are not the actual retained native control regions",
                )?;
                for d in [&first.apply_delta, &first.restore_delta] {
                    need(
                        d["changed_pixels"].as_u64().is_some_and(|v| v >= 24)
                            && d["changed_columns"].as_u64().is_some_and(|v| v >= 6)
                            && d["changed_rows"].as_u64().is_some_and(|v| v >= 3),
                        "Family actual input lacks its retained rendered change",
                    )?;
                }
                2
            }
            (FirstProof::Panel(first), ReopenedProof::Panel { pixels, panel }) => {
                need(
                    p.mode == Mode::ReadOnlyPanel
                        && first.panel == *panel
                        && !first.panel.as_array().is_none_or(Vec::is_empty)
                        && self.first_discovery.navigations.len() == 1
                        && first.before.held.pixels_sha256() != first.after.held.pixels_sha256(),
                    "Family read-only self-check lacks actual navigation/effect/reopen readback",
                )?;
                first.before.held.require_transcript(a)?;
                first.after.held.require_transcript(a)?;
                pixels.held.require_transcript(b)?;
                0
            }
            _ => return Err("Family source mode was mixed between sessions".into()),
        };
        need(
            a.actions() == self.first_discovery.navigations.len() as u32 + writes + 1
                && b.actions() == self.second_discovery.navigations.len() as u32 + 1,
            "Family needs exactly its source inputs and one normal owned removal per session",
        )?;
        Ok(())
    }
    pub fn comparison(&self) -> Result<Value, String> {
        self.guard_immutable()?;
        let first = self.stability.transcript();
        let second = self.reopened.transcript();
        let p = controls::plan(first.engine().application())?;
        let proof = match (&self.first, &self.second) {
            (FirstProof::Text(a), ReopenedProof::Text(b)) => json!({
                "kind":"exact_reversible_source_input","writes":2,"original":describe_control(&a.before.control),
                "canary":describe_control(&a.edited.control),"restored":describe_control(&a.restored.control),
                "reopened":describe_control(&b.control),"apply_pixels":a.apply_delta,
                "restore_pixels":a.restore_delta,"observations":[a.before.pixels.comparison()?,
                    a.edited.pixels.comparison()?,a.restored.pixels.comparison()?,b.pixels.comparison()?]}),
            (FirstProof::Panel(a), ReopenedProof::Panel { pixels, panel }) => json!({
                "kind":"source_fixed_readonly_self_check","writes":0,"panel":a.panel,
                "reopened_panel":panel,"observations":[a.before.comparison()?,a.after.comparison()?,pixels.comparison()?]}),
            _ => return Err("Family history mode mismatch".into()),
        };
        let first_record = json!({"task":first.task(),"journal":first.journal(),
            "journal_identity":first.journal_custody.identity,
            "operations":first.operations(),"actions":first.actions(),
            "initial_native_sha256":self.first_discovery.initial_native_sha256,
            "navigations":self.first_discovery.navigations.iter().map(Locator::comparison).collect::<Vec<_>>()});
        let reopened_record = json!({"task":second.task(),"journal":second.journal(),
            "journal_identity":second.journal_custody.identity,
            "operations":second.operations(),"actions":second.actions(),
            "initial_native_sha256":self.second_discovery.initial_native_sha256,
            "navigations":self.second_discovery.navigations.iter().map(Locator::comparison).collect::<Vec<_>>()});
        Ok(json!({"schema":"droidloom.native-family-ui-lifecycle.v1",
            "package":p.package,"application":first.engine().application(),"main":first.engine().facts().main,
            "source_plan_sha256":controls::plan_digest(),"selected_resource_sha256":p.source_resource_sha256,
            "selected_literal_sha256":p.source_literal_sha256,
            "first":first_record,"reopened":reopened_record,
            "proof":proof,"two_normal_owned_closes_and_complete_pm_main_bookends":true,
            "original_query_value_restored_before_close":matches!(&self.first,FirstProof::Text(_)),
            "form_submission_performed":false,"messages_calls_purchases_or_account_changes":false,
            "family_business_gates_supplied":false,"complete_data_account_scope_inferred":false,
            "comparison_only":true,"production_ready":false}))
    }
}

/// The only constructor. A normal caller supplies only its already-owned
/// baseline and original absolute end; package/control choice is source-fixed.
pub fn observe_native_family_ui(
    inspector: &mut NativeApplicationInspector,
    baseline: &mut NativeLeafBaselineObservation<'_>,
    original_end: Instant,
) -> Result<NativeFamilyUiEvidence, String> {
    let first_end = require_window(Instant::now(), original_end, baseline.deadline())?;
    let p = controls::plan(baseline.application())?;
    let application = baseline.application().clone();
    let main = baseline.main().facts().clone();
    let mut first = NativeUiSession::open(inspector, baseline, first_end)?;
    let mut stable = first.begin_stability(inspector)?;
    stable.sample(&mut first, inspector)?;
    let result = match p.mode {
        Mode::Text | Mode::Number => first_text(&mut first, inspector, &p),
        Mode::ReadOnlyPanel => first_panel(&mut first, inspector, &p),
    };
    let (proof, first_discovery) = match result {
        Ok(v) => v,
        Err(e) => return Err(first.observation_failure(inspector, e)),
    };
    stable.sample(&mut first, inspector)?;
    stable.sample(&mut first, inspector)?;
    let stability = stable.finish(first, inspector)?;
    stability.require_subject(&main, &application)?;
    let mut second = NativeUiSession::open(inspector, baseline, original_end)?;
    let result = match &proof {
        FirstProof::Text(v) => reopen_text(&mut second, inspector, &p, v),
        FirstProof::Panel(v) => reopen_panel(&mut second, inspector, &p, v),
    };
    let (reopened_proof, second_discovery) = match result {
        Ok(v) => v,
        Err(e) => return Err(second.observation_failure(inspector, e)),
    };
    let reopened = second.finish(inspector)?.into_retained()?;
    let evidence = NativeFamilyUiEvidence {
        stability,
        reopened,
        first: proof,
        second: reopened_proof,
        first_discovery,
        second_discovery,
        original_end,
    };
    evidence.require_subject(&main, &application)?;
    before(original_end)?;
    Ok(evidence)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn family_ui_input_result_preserves_first_failure_before_journal_diagnostics() {
        // Pure result ordering, never an executed UI observation or a gate.
        let both = ordered_input_readbacks::<u8>(
            Err("actual readback failure".into()),
            Err("actual restore failure".into()),
            Err("journal failure".into()),
        )
        .unwrap_err();
        assert!(both.starts_with("actual readback failure;"));
        assert!(both.contains("actual restore failure"));
        assert!(both.contains("journal failure"));
        assert!(both.contains("restore completed=false"));

        let restored = ordered_input_readbacks(
            Ok(1_u8),
            Err("actual restore failure".into()),
            Err("journal failure".into()),
        )
        .unwrap_err();
        assert!(restored.starts_with("actual restore failure;"));
        assert!(restored.contains("journal failure"));

        assert_eq!(
            ordered_input_readbacks(Ok(1_u8), Ok(2_u8), Err("journal failure".into()),)
                .unwrap_err(),
            "journal failure"
        );
        assert_eq!(
            ordered_input_readbacks(Ok(1_u8), Ok(2_u8), Ok(())).unwrap(),
            (1, 2)
        );
    }
    #[test]
    fn family_ui_pair_deadline_preserves_original_elapsed_time_and_reopen_reserve() {
        assert_eq!(family_ui_window_seconds(), 6_490);
        assert_eq!(second_window_seconds(), 2_365);
        let now = Instant::now();
        let end = now + Duration::from_secs(family_ui_window_seconds());
        let first = require_window(now, end, end).unwrap();
        assert_eq!(first, end - Duration::from_secs(2_365));
        assert_eq!(
            require_window(now + Duration::from_millis(1), end, end).unwrap(),
            first
        );
        assert!(require_window(
            now,
            end + Duration::from_nanos(1),
            end + Duration::from_nanos(1)
        )
        .is_err());
        assert!(require_window(now, end, end - Duration::from_nanos(1)).is_err());
        assert!(require_window(now, now + Duration::from_secs(2_365), end).is_err());
        assert!(require_window(end, end, end).is_err());
    }
}
