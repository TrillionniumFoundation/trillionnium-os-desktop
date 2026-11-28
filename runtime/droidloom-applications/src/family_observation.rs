//! Actual native UI and stability custody for the thirty-three non-leaf families.
//! A completed observation can retain blocked business gates after a proven
//! normal close. It cannot manufacture a business pass from a launch, text,
//! screenshot, elapsed duration, or a saved comparison report.
use super::physical_gate_roster as roster;
#[path = "family_retail.rs"]
mod family_retail;
#[path = "family_retail_case.rs"]
mod retail_case;
#[path = "family_news.rs"]
mod family_news;
#[path = "family_news_case.rs"]
mod news_case;
#[path = "family_collaboration.rs"]
mod family_collaboration;
#[path = "family_collaboration_case.rs"]
mod collaboration_case;
#[path = "family_travel.rs"]
mod family_travel;
#[path = "family_travel_case.rs"]
mod travel_case;
#[path = "family_housing.rs"]
mod family_housing;
#[path = "family_housing_case.rs"]
mod housing_case;
use droidloom_supervisor::control::application_probe::ApplicationInspection;
use droidloom_supervisor::control::{
    NativeApplicationInspector, NativeFamilyUiEvidence, NativeUiStabilityEvidence,
    observe_native_family_ui, family_ui_window_seconds, family_ui_retained_members_bound,
    NativeUiPermissionWindow, NativeUiPermissionPreservation,
    NativeGmsIdentityEvidence, observe_native_gms_identity,
    permission_preservation_additional_window_seconds,
};
use droidloom_supervisor::main_custody::RuntimeMainCustody;
use droidloom_supervisor::native_leaf_baseline::NativeLeafBaselineObservation;
use serde::Serialize;
use serde_json::{Value, json};
use std::time::{Duration, Instant};

const FAMILY_COUNT: usize = 33;
const FAMILY_BUSINESS_GATE_COUNT: usize = 126;
pub(super) fn retained_journal_members_bound() -> usize {
    // Root's normal preservation factory owns its separate fixed journal.
    // Eight records cover the same PM/AppOps/account interval around both sessions.
    family_ui_retained_members_bound() + 8
}
fn ui_window_seconds() -> u64 { family_ui_window_seconds() }
pub(super) fn window_seconds() -> u64 {
    ui_window_seconds() + permission_preservation_additional_window_seconds()
}
pub(super) fn window_seconds_for(package: &str) -> u64 {
    window_seconds() + business_window_seconds(package)
}
fn business_window_seconds(package: &str) -> u64 {
    if retail_case::supports(package) { retail_case::window_seconds() }
    else if news_case::supports(package) { news_case::window_seconds() }
    else if collaboration_case::supports(package) { collaboration_case::window_seconds() }
    else if travel_case::supports(package) { travel_case::window_seconds(package) }
    else if housing_case::supports(package) { housing_case::window_seconds() } else { 0 }
}
fn retained_journal_members_bound_for(package: &str) -> usize {
    retained_journal_members_bound()
        + if retail_case::supports(package) { retail_case::retained_journal_members_bound() } else { 0 }
        + if news_case::supports(package) { news_case::retained_journal_members_bound() } else { 0 }
        + if collaboration_case::supports(package) { collaboration_case::retained_journal_members_bound() } else { 0 }
        + if travel_case::supports(package) { travel_case::retained_journal_members_bound(package) } else { 0 }
        + if housing_case::supports(package) { housing_case::retained_journal_members_bound() } else { 0 }
}
fn ordered_completed(
    row: &'static roster::PackageGates, complete: &[&'static str],
) -> Result<Vec<&'static str>, String> {
    let unique = complete.iter().copied().collect::<std::collections::BTreeSet<_>>();
    require(unique.len() == complete.len()
        && complete.iter().all(|gate| row.business.contains(gate)),
        "actual family business IDs repeat or leave the compiled gate set")?;
    Ok(row.business.iter().copied().filter(|gate| unique.contains(gate)).collect())
}
fn remaining(
    row: &'static roster::PackageGates, complete: &[&'static str],
) -> Vec<FamilyBlockedGate> {
    blocked(row).into_iter().filter(|gate| !complete.contains(&gate.id)).collect()
}

fn require(value: bool, reason: &str) -> Result<(), String> {
    if value { Ok(()) } else { Err(reason.into()) }
}
fn family(package: &str) -> Result<&'static roster::PackageGates, String> {
    let row = roster::package(package)?;
    require(
        row.cases.is_empty(),
        "native leaf packages cannot select the family observation factory",
    )?;
    Ok(row)
}
fn require_window(
    package: &str,
    now: Instant,
    original_end: Instant,
    baseline_end: Instant,
) -> Result<(), String> {
    family(package)?;
    require(
        now < original_end
            && original_end <= baseline_end
            && original_end.duration_since(now) <= Duration::from_secs(window_seconds_for(package)),
        "family observation needs its original source-bounded case and baseline deadline",
    )
}

#[derive(Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub(super) enum FamilyBlockCode {
    BusinessFlowNotObserved,
    OwnedCommunicationPeerCasePending,
    DependentServiceConsumerCasePending,
    RenderedAudioVideoCasePending,
    BrowserFixtureCasePending,
    InputMethodConsumerCasePending,
    AuthenticatedWorkspaceCasePending,
    DeclaredReadonlyDocumentCasePending,
    OwnedUnsentDraftCasePending,
    ScopedCollaborationRecoveryCasePending,
    AuthenticatedHousingRouteCasePending,
}

/// Source-owned missing assertion, never a success or a claim about whether an
/// account, service, payment method or third-party endpoint is available.
#[derive(Debug, PartialEq, Eq, Serialize)]
pub(super) struct FamilyBlockedGate {
    id: &'static str,
    code: FamilyBlockCode,
}
impl FamilyBlockedGate {
    pub(super) fn id(&self) -> &'static str {
        self.id
    }
    pub(super) fn code(&self) -> &FamilyBlockCode {
        &self.code
    }
}
fn blocked(row: &'static roster::PackageGates) -> Vec<FamilyBlockedGate> {
    row.business
        .iter()
        .copied()
        .map(|id| {
            let code = match row.profile {
                "dialer" | "messaging" => FamilyBlockCode::OwnedCommunicationPeerCasePending,
                "gms" => FamilyBlockCode::DependentServiceConsumerCasePending,
                "video" => FamilyBlockCode::RenderedAudioVideoCasePending,
                "browser" => FamilyBlockCode::BrowserFixtureCasePending,
                "ime" => FamilyBlockCode::InputMethodConsumerCasePending,
                "collaboration" => match id {
                    "collaboration.account" | "collaboration.navigation" => FamilyBlockCode::AuthenticatedWorkspaceCasePending,
                    "collaboration.search" | "collaboration.documents" => FamilyBlockCode::DeclaredReadonlyDocumentCasePending,
                    "collaboration.compose" => FamilyBlockCode::OwnedUnsentDraftCasePending,
                    _ => FamilyBlockCode::ScopedCollaborationRecoveryCasePending,
                },
                "housing" if id == "housing.navigation" => FamilyBlockCode::AuthenticatedHousingRouteCasePending,
                _ => FamilyBlockCode::BusinessFlowNotObserved,
            };
            FamilyBlockedGate { id, code }
        })
        .collect()
}

/// No public constructor or deserializer exists. Only the genuine retained
/// source-owned execution/retained observation may add its completed business assertions.
#[derive(Debug, Serialize)]
pub(super) struct FamilyBusinessFact {
    id: &'static str,
    package: String,
    main: RuntimeMainCustody,
    application: ApplicationInspection,
    basis: Value,
}
impl FamilyBusinessFact {
    pub(super) fn id(&self) -> &'static str {
        self.id
    }
    pub(super) fn require_subject(
        &self,
        main: &RuntimeMainCustody,
        application: &ApplicationInspection,
    ) -> Result<(), String> {
        require(
            self.package == application.package
                && &self.main == main
                && &self.application == application
                && family(&self.package)?.business.contains(&self.id),
            "family business assertion belongs to a different actual subject or source gate",
        )
    }
}

/// Complete in-process custody. Ok does not mean that the application passed.
/// A caller may continue another independent case only after this object's
/// immutable checks and the original source lease have both been validated.
pub(super) struct FamilyObservation {
    ui: NativeFamilyUiEvidence,
    permissions: NativeUiPermissionPreservation,
    retail: Option<retail_case::RetailCaseObservation>,
    news: Option<news_case::NewsCaseObservation>,
    collaboration: Option<collaboration_case::CollaborationCaseObservation>,
    travel: Option<travel_case::TravelCaseObservation>,
    housing: Option<housing_case::HousingCaseObservation>,
    // Joins existing retained common owners; no additional query/FD/window.
    gms_identity: Option<NativeGmsIdentityEvidence>,
    business_facts: Vec<FamilyBusinessFact>,
    blocked: Vec<FamilyBlockedGate>,
}
impl FamilyObservation {
    pub(super) fn stability(&self) -> &NativeUiStabilityEvidence { self.ui.stability() }
    pub(super) fn ui(&self) -> &NativeFamilyUiEvidence { &self.ui }
    pub(super) fn business_facts(&self) -> &[FamilyBusinessFact] { &self.business_facts }
    pub(super) fn blocked(&self) -> &[FamilyBlockedGate] { &self.blocked }
    pub(super) fn require_subject(
        &self, main: &RuntimeMainCustody, application: &ApplicationInspection,
    ) -> Result<(), String> {
        self.ui.require_subject(main, application)?;
        self.guard_immutable()
    }
    pub(super) fn guard_immutable(&self) -> Result<(), String> {
        self.ui.guard_immutable()?;
        let first = self.ui.stability().transcript();
        let reopened = self.ui.reopened().transcript();
        // A single-session preservation receipt cannot cover this pair.
        // The normal window's actual before/after observations enclose both
        // closes and the strict first.finished < reopened.opened boundary.
        self.permissions.require_pair(first, reopened)?;
        let row = family(&first.engine().application().package)?;
        require(self.gms_identity.is_some() == NativeGmsIdentityEvidence::supports(row.package),
            "GMS identity cannot be omitted or borrowed by another application family")?;
        let (complete, basis) = match (&self.retail, &self.news, &self.collaboration, &self.travel, &self.housing) {
            (Some(value), None, None, None, None) => {
                require(retail_case::supports(row.package),
                    "retail history selected a different family contract")?;
                value.require_subject(&first.engine().facts().main, first.engine().application())?;
                self.permissions.require_continuation(value.permissions())?;
                (value.completed_gates().to_vec(), value.comparison()?)
            }
            (None, Some(value), None, None, None) => {
                require(news_case::supports(row.package), "news history selected another family contract")?;
                value.require_subject(&first.engine().facts().main, first.engine().application())?;
                self.permissions.require_continuation(value.permissions())?;
                (value.completed_gates(), value.comparison()?)
            }
            (None, None, Some(value), None, None) => {
                require(collaboration_case::supports(row.package), "collaboration history selected another family contract")?;
                value.require_subject(&first.engine().facts().main, first.engine().application())?;
                self.permissions.require_continuation(value.permissions())?;
                (value.completed_gates(), value.comparison()?)
            }
            (None, None, None, Some(value), None) => {
                require(travel_case::supports(row.package), "travel history selected another family contract")?;
                value.require_subject(&first.engine().facts().main, first.engine().application())?;
                self.permissions.require_continuation(value.permissions())?;
                (value.completed_gates(), value.comparison()?)
            }
            (None, None, None, None, Some(value)) => {
                require(housing_case::supports(row.package), "housing history selected another family contract")?;
                value.require_subject(&first.engine().facts().main, first.engine().application())?;
                self.permissions.require_continuation(value.permissions())?;
                (value.completed_gates(), value.comparison()?)
            }
            (None, None, None, None, None) => {
                require(!retail_case::supports(row.package) && !news_case::supports(row.package)
                    && !collaboration_case::supports(row.package) && !travel_case::supports(row.package)
                    && !housing_case::supports(row.package),
                    "a compiled business execution cannot be silently skipped")?;
                if let Some(identity) = &self.gms_identity {
                    identity.require_existing_evidence(&self.ui, &self.permissions)?;
                    (identity.completed_gates().to_vec(), identity.comparison(&self.ui, &self.permissions)?)
                } else { (Vec::new(), Value::Null) }
            }
            _ => return Err("one family cannot borrow two different business factories".into()),
        };
        let ordered = ordered_completed(row, &complete)?;
        require(self.business_facts.iter().map(|value| value.id()).collect::<Vec<_>>() == ordered
            && self.blocked == remaining(row, &complete),
            "family assertions or blocked remainder differ from the actual retained executor")?;
        for fact in &self.business_facts {
            fact.require_subject(&first.engine().facts().main, first.engine().application())?;
            require(fact.basis == basis,
                "family business assertion is detached from its retained actual execution")?;
        }
        Ok(())
    }
    pub(super) fn comparison(&self) -> Result<Value, String> {
        self.guard_immutable()?;
        let engine = self.ui.stability().transcript().engine();
        let row = family(&engine.application().package)?;
        Ok(json!({
            "schema":"droidloom.physical-family-observation.v4",
            "package":row.package,"profile":row.profile,
            "application":engine.application(),"main":engine.facts().main,
            "stability":self.ui.stability().summary(),
            "actual_ui_lifecycle":self.ui.comparison()?,
            "pm_permission_preservation":self.permissions.comparison()?,
            "retail_business":self.retail.as_ref().map(|value|value.comparison()).transpose()?,
            "news_business":self.news.as_ref().map(|value|value.comparison()).transpose()?,
            "collaboration_business":self.collaboration.as_ref().map(|value|value.comparison()).transpose()?,
            "travel_business":self.travel.as_ref().map(|value|value.comparison()).transpose()?,
            "housing_business":self.housing.as_ref().map(|value|value.comparison()).transpose()?,
            "gms_identity":self.gms_identity.as_ref().map(|value|value.comparison(&self.ui,&self.permissions)).transpose()?,
            "business_facts":self.business_facts,"blocked":self.blocked,
            "decoded_pixels_retained_in_history":false,
            "business_execution_attempted":self.retail.is_some() || self.news.is_some() || self.collaboration.is_some() || self.travel.is_some() || self.housing.is_some() || self.gms_identity.is_some(),
            "complete_data_permissions_or_account_acceptance_inferred":false,
            "source_window_seconds":window_seconds_for(row.package),
            "source_maximum_retained_journal_members":retained_journal_members_bound_for(row.package),
            "runtime_qualified":false,"production_ready":false,"comparison_only":true
        }))
    }
}

/// Both UI sessions use the one normal context and original absolute end.
/// A failure remains a failure after any certain, source-owned cleanup. Saved
/// comparison JSON and a partial visual result cannot enter this constructor.
pub(super) fn run_family_case(
    inspector: &mut NativeApplicationInspector,
    baseline: &mut NativeLeafBaselineObservation<'_>,
    feishu_fixture: Option<&droidloom_supervisor::working_qualification::FeishuReadonlyFixture>,
    original_end: Instant,
) -> Result<FamilyObservation, String> {
    let application = baseline.application().clone();
    require_window(&application.package, Instant::now(), original_end, baseline.deadline())?;
    let main = baseline.main().facts().clone();
    let row = family(&application.package)?;
    baseline.verify_local(inspector, original_end).map_err(|e|e.to_string())?;
    let additional = business_window_seconds(&application.package);
    let common_end = if additional != 0 {
        original_end.checked_sub(Duration::from_secs(additional))
            .filter(|end| Instant::now() < *end)
            .ok_or("family original end cannot reserve its separate business window")?
    } else { original_end };
    let permission_window = NativeUiPermissionWindow::begin(inspector, baseline, common_end)?;
    let ui_end = (Instant::now() + Duration::from_secs(ui_window_seconds()))
        .min(permission_window.ui_deadline());
    let ui = match observe_native_family_ui(inspector, baseline, ui_end) {
        Ok(value) => value,
        Err(error) => return Err(permission_window.fail(error)),
    };
    ui.require_subject(&main, &application)?;
    let permissions = permission_window.finish_pair(
        inspector, baseline, ui.stability().transcript(), ui.reopened().transcript(),
    )?;
    let gms_identity = if NativeGmsIdentityEvidence::supports(&application.package) {
        Some(observe_native_gms_identity(&ui, &permissions)?)
    } else { None };
    let retail = if retail_case::supports(&application.package) {
        let retail_end = (Instant::now() + Duration::from_secs(retail_case::window_seconds()))
            .min(original_end);
        Some(retail_case::run(inspector, baseline, retail_end)?)
    } else { None };
    let news = if news_case::supports(&application.package) {
        let end = (Instant::now() + Duration::from_secs(news_case::window_seconds())).min(original_end);
        Some(news_case::run(inspector, baseline, end)?)
    } else { None };
    let collaboration = if collaboration_case::supports(&application.package) {
        let end=(Instant::now()+Duration::from_secs(collaboration_case::window_seconds())).min(original_end);
        Some(collaboration_case::run(inspector,baseline,feishu_fixture,end)?)
    } else {None};
    let travel = if travel_case::supports(&application.package) {
        let end = (Instant::now() + Duration::from_secs(travel_case::window_seconds(&application.package))).min(original_end);
        Some(travel_case::run(inspector, baseline, end)?)
    } else { None };
    let housing = if housing_case::supports(&application.package) {
        let end=(Instant::now()+Duration::from_secs(housing_case::window_seconds())).min(original_end);
        Some(housing_case::run(inspector,baseline,end)?)
    } else {None};
    let (complete, basis) = if let Some(value) = &retail {
        (value.completed_gates().to_vec(), Some(value.comparison()?))
    } else if let Some(value) = &news {
        (value.completed_gates(), Some(value.comparison()?))
    } else if let Some(value)=&collaboration {
        (value.completed_gates(),Some(value.comparison()?))
    } else if let Some(value) = &travel {
        (value.completed_gates(), Some(value.comparison()?))
    } else if let Some(value)=&housing {
        (value.completed_gates(),Some(value.comparison()?))
    } else if let Some(value) = &gms_identity {
        (value.completed_gates().to_vec(), Some(value.comparison(&ui, &permissions)?))
    } else { (Vec::new(), None) };
    let ordered = ordered_completed(row, &complete)?;
    let business_facts = ordered.into_iter().map(|id| FamilyBusinessFact {
        id, package:application.package.clone(), main:main.clone(),
        application:application.clone(), basis:basis.clone().unwrap_or(Value::Null),
    }).collect();
    let blocked = remaining(row, &complete);
    let observation = FamilyObservation { ui, permissions, retail, news, collaboration, travel, housing, gms_identity, business_facts, blocked };
    observation.guard_immutable()?;
    require(Instant::now() < original_end,
        "Family custody sealing exceeded the original case deadline")?;
    Ok(observation)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn family_observation_source_scope_rejects_native_leaves_and_excluded_apps() {
        let rows: Vec<_> = roster::PACKAGES
            .iter()
            .filter(|row| row.cases.is_empty())
            .collect();
        assert_eq!(rows.len(), FAMILY_COUNT);
        assert_eq!(
            rows.iter().map(|row| row.business.len()).sum::<usize>(),
            FAMILY_BUSINESS_GATE_COUNT
        );
        for row in roster::PACKAGES {
            assert_eq!(family(row.package).is_ok(), row.cases.is_empty());
        }
        for package in [
            "com.enflick.android.TextNow",
            "com.pinger.textfree",
            "com.ubercab",
            "com.android.settings.other",
            "",
        ] {
            assert!(family(package).is_err());
        }
    }

    #[test]
    fn family_observation_blocked_history_cannot_omit_or_duplicate_business_gates() {
        let mut seen = std::collections::BTreeSet::new();
        for row in roster::PACKAGES.iter().filter(|row| row.cases.is_empty()) {
            let pending = blocked(row);
            assert_eq!(pending.len(), row.business.len());
            for (observed, expected) in pending.iter().zip(row.business) {
                assert_eq!(observed.id(), *expected);
                assert!(seen.insert((row.package, observed.id())));
                let serialized = serde_json::to_value(observed).unwrap();
                assert!(serialized.get("passed").is_none());
                assert!(serialized.get("safe_to_continue").is_none());
            }
        }
        assert_eq!(seen.len(), FAMILY_BUSINESS_GATE_COUNT);
    }

    #[test]
    fn family_observation_budget_rejects_renewal_and_outliving_original_baseline() {
        assert_eq!(ui_window_seconds(), 6490);
        assert_eq!(permission_preservation_additional_window_seconds(), 420);
        assert_eq!(window_seconds(), 6910);
        let now = Instant::now();
        let end = now + Duration::from_secs(window_seconds());
        require_window("com.android.quicksearchbox", now, end, end).unwrap();
        require_window("com.android.quicksearchbox", now, end - Duration::from_secs(1), end).unwrap();
        assert!(require_window("com.android.quicksearchbox", now, end + Duration::from_nanos(1), end).is_err());
        assert!(require_window("com.android.quicksearchbox", now, end, end - Duration::from_nanos(1)).is_err());
        assert!(require_window("com.android.quicksearchbox", now, now, end).is_err());
        assert!(require_window("com.android.quicksearchbox", now, now - Duration::from_nanos(1), end).is_err());
        assert!(
            require_window(
                "com.android.quicksearchbox", now,
                end + Duration::from_secs(1),
                end + Duration::from_secs(1)
            )
            .is_err()
        );
    }

    #[test]
    fn family_observation_pair_has_finite_retained_inputs_without_rgb_history() {
        assert_eq!(family_ui_retained_members_bound(), 768);
        assert_eq!(retained_journal_members_bound(), 776);
        assert!(33 * retained_journal_members_bound() < 32_768);
    }

    #[test]
    fn family_retail_partition_never_promotes_common_input_or_account_success() {
        let row = family("com.amazon.mShop.android.shopping").unwrap();
        assert_eq!(ordered_completed(row, &[]).unwrap(), Vec::<&str>::new());
        assert_eq!(ordered_completed(row, &["retail.search", "retail.detail"]).unwrap(),
            vec!["retail.detail", "retail.search"]);
        assert!(ordered_completed(row, &["retail.search", "retail.search"]).is_err());
        assert!(ordered_completed(row, &["search.query"]).is_err());
        assert_eq!(remaining(row, &["retail.search", "retail.detail", "retail.navigation"])
            .iter().map(|gate| gate.id()).collect::<Vec<_>>(), vec!["retail.account"]);
        let rows: Vec<_> = roster::PACKAGES.iter().filter(|row| row.cases.is_empty()).collect();
        assert_eq!(rows.iter().filter(|row| retail_case::supports(row.package)).count(), 5);
        assert_eq!(window_seconds_for("com.amazon.mShop.android.shopping"), 15_000);
        assert_eq!(window_seconds_for("com.android.quicksearchbox"), 6_910);
        assert_eq!(retained_journal_members_bound_for("com.amazon.mShop.android.shopping"), 1_704);
        let retained = rows.iter().map(|row|retained_journal_members_bound_for(row.package)).sum::<usize>();
        assert_eq!(retained, FAMILY_COUNT * retained_journal_members_bound()
            + 5 * retail_case::retained_journal_members_bound()
            + news_case::retained_journal_members_bound()
            + collaboration_case::retained_journal_members_bound()
            + rows.iter().filter(|row|travel_case::supports(row.package)).map(|row|travel_case::retained_journal_members_bound(row.package)).sum::<usize>()

            + 2 * housing_case::retained_journal_members_bound());
        assert_eq!(retained, droidloom_supervisor::control::physical_qualification_channel::budget::resources::FAMILY_JOURNAL_DESCRIPTORS);
        assert!(retained > 32_768); // the old family-only limit was insufficient
        let now = Instant::now();
        let end = now + Duration::from_secs(15_000);
        require_window("com.amazon.mShop.android.shopping", now, end, end).unwrap();
        assert!(require_window("com.android.quicksearchbox", now, end, end).is_err());
        assert!(require_window("com.amazon.mShop.android.shopping", now,
            end + Duration::from_nanos(1), end + Duration::from_nanos(1)).is_err());
        assert!(require_window("com.ubercab", now, end, end).is_err());
    }

    #[test]
    fn news_partial_business_keeps_private_navigation_media_and_recovery_pending() {
        let row=family("com.ss.android.article.news").unwrap();
        let complete=["news.feed","news.article","news.search"];
        let pending=remaining(row,&complete).into_iter().map(|g|g.id).collect::<std::collections::BTreeSet<_>>();
        assert_eq!(pending,std::collections::BTreeSet::from(["news.navigation","news.media","news.recovery"]));
        assert_eq!(window_seconds_for(row.package),17_450);
        assert_eq!(retained_journal_members_bound_for(row.package),2_046);
        assert!(!news_case::supports("com.ss.android.lark"));
        let now=Instant::now();let end=now+Duration::from_secs(17_450);
        require_window(row.package,now,end,end).unwrap();
        assert!(require_window(row.package,now,end+Duration::from_nanos(1),end+Duration::from_nanos(1)).is_err());
    }
    #[test]
    fn collaboration_contract_never_relabels_login_as_document_draft_or_recovery_success() {
        let row=family("com.ss.android.lark").unwrap();
        assert_eq!(window_seconds_for(row.package),17_230);
        assert_eq!(retained_journal_members_bound_for(row.package),2_058);
        assert!(ordered_completed(row,&["news.search"]).is_err());
        assert_eq!(remaining(row,&["collaboration.account","collaboration.navigation"])
            .iter().map(|g|g.id).collect::<std::collections::BTreeSet<_>>(),
            std::collections::BTreeSet::from(["collaboration.compose","collaboration.documents","collaboration.recovery","collaboration.search"]));
        assert_eq!(blocked(row).iter().filter(|g|matches!(g.code,FamilyBlockCode::DeclaredReadonlyDocumentCasePending)).count(),2);
    }

    #[test]
    fn travel_public_business_keeps_account_paths_blocked_and_reserves_full_route_budget() {
        let rows:Vec<_>=roster::PACKAGES.iter().filter(|r|travel_case::supports(r.package)).collect();
        assert_eq!(rows.len(),12);
        assert_eq!(rows.iter().map(|r|business_window_seconds(r.package)).sum::<u64>(),243_240);
        assert_eq!(rows.iter().map(|r|travel_case::retained_journal_members_bound(r.package)).sum::<usize>(),30_288);
        for row in rows {
            let allowed:Vec<_>=row.business.iter().copied().filter(|id|!id.ends_with(".account")).collect();
            let pending=remaining(row,&allowed);
            assert_eq!(pending.len(),1);assert!(pending[0].id.ends_with(".account"));
            assert_eq!(window_seconds_for(row.package),window_seconds()+travel_case::window_seconds(row.package));
        }
        assert_eq!(window_seconds_for("ctrip.android.view"),48_520);
        assert_eq!(retained_journal_members_bound_for("ctrip.android.view"),6_072);
        let budget=droidloom_supervisor::control::physical_qualification_channel::budget::TRAVEL_ADDITIONAL_SECONDS;
        assert_eq!(budget,travel_case::window_seconds("com.united.mobile.android"));
        assert_eq!(droidloom_supervisor::control::physical_qualification_channel::budget::CTRIP_ADDITIONAL_SECONDS,
            travel_case::window_seconds("ctrip.android.view"));
    }

    #[test]
    fn housing_public_query_detail_partition_preserves_authenticated_navigation_gate() {
        for package in ["com.lianjia.beike","com.zillow.android.streeteasy"]{
            let row=family(package).unwrap();
            let pending=remaining(row,&["housing.query","housing.details"]);
            assert_eq!(pending.len(),1);
            assert_eq!(pending[0].id(),"housing.navigation");
            assert_eq!(pending[0].code(),&FamilyBlockCode::AuthenticatedHousingRouteCasePending);
            assert_eq!(window_seconds_for(package),19_080);
            assert_eq!(retained_journal_members_bound_for(package),2_232);
            assert!(ordered_completed(row,&["retail.navigation"]).is_err());
            let now=Instant::now();let end=now+Duration::from_secs(19_080);
            require_window(package,now,end,end).unwrap();
            assert!(require_window(package,now,end+Duration::from_nanos(1),end+Duration::from_nanos(1)).is_err());
        }
        assert_eq!(roster::PACKAGES.iter().filter(|r|housing_case::supports(r.package)).count(),2);
    }

    #[test]
    fn gms_identity_partition_keeps_consumer_failure_and_all_original_budgets() {
        let row=family("com.google.android.gms").unwrap();
        assert_eq!(ordered_completed(row,&["gms.identity"]).unwrap(),vec!["gms.identity"]);
        assert_eq!(remaining(row,&["gms.identity"]).iter().map(|gate|gate.id()).collect::<Vec<_>>(),
            vec!["gms.consumer","gms.failure"]);
        assert!(remaining(row,&["gms.identity"]).iter()
            .all(|gate|gate.code()==&FamilyBlockCode::DependentServiceConsumerCasePending));
        assert_eq!(window_seconds_for(row.package),6_910);
        assert_eq!(retained_journal_members_bound_for(row.package),776);
        assert_eq!(business_window_seconds(row.package),0);
        assert_eq!(roster::PACKAGES.iter()
            .filter(|row|NativeGmsIdentityEvidence::supports(row.package)).count(),1);
        assert!(ordered_completed(row,&["gms.identity","gms.identity"]).is_err());
        assert!(ordered_completed(row,&["retail.search"]).is_err());
    }

}
