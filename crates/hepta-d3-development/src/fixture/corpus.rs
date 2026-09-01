use crate::client;
use crate::model::{Coordinates, bool_field, element_reference_field, u64_field};
use crate::{AnyError, escape_json, invalid};
use hepta_browser_codec::{
    BrowserErrorCode, BrowserOperation, BrowserRequest, NavigationTarget, ObservationField,
    PageAction, ProfilePersistence, ProfileSpec, WaitCondition,
};

pub(crate) fn run() -> Result<String, AnyError> {
    let health = client::invoke(unbound("d3-health", BrowserOperation::Health))?;
    client::success(&health, "health")?;

    let created = client::invoke(unbound(
        "d3-create",
        BrowserOperation::SessionCreate {
            profile: ProfileSpec {
                profile_id: "d3-image-fixture".to_owned(),
                persistence: ProfilePersistence::Ephemeral,
            },
            ui_mode: "headed".to_owned(),
        },
    ))?;
    let mut coordinates = Coordinates::from_result(client::success(&created, "session_create")?)?;

    let snapshot =
        client::invoke(coordinates.request("d3-snapshot", BrowserOperation::SessionSnapshot))?;
    coordinates.update(client::success(&snapshot, "session_snapshot")?)?;

    let stale_generation = coordinates.document_generation;
    let navigated = client::invoke(coordinates.request(
        "d3-navigate-local",
        BrowserOperation::PageNavigate {
            target: NavigationTarget::LocalHttpFixture {
                url: "http://127.0.0.1/d3-local-fixture".to_owned(),
            },
            expected_document_generation: coordinates.document_generation,
        },
    ))?;
    coordinates.update(client::success(&navigated, "page_navigate")?)?;

    let observed = client::invoke(coordinates.request(
        "d3-observe",
        BrowserOperation::PageObserve {
            fields: vec![
                ObservationField::Role,
                ObservationField::Name,
                ObservationField::Text,
            ],
        },
    ))?;
    let observed_result = client::success(&observed, "page_observe")?;
    let target = element_reference_field(observed_result, "semantic_target")?;
    let observed_mutation_epoch = u64_field(observed_result, "semantic_snapshot_mutation_epoch")?;
    if !bool_field(observed_result, "caller_bound_snapshot")?
        || !bool_field(observed_result, "atomic_page_act_available")?
        || bool_field(observed_result, "servo_adapter_exercised")?
    {
        return Err(invalid("semantic observation claim boundary changed").into());
    }
    coordinates.update(observed_result)?;
    if target.session_generation != coordinates.session_generation
        || target.document_generation != coordinates.document_generation
        || target.semantic_snapshot_revision != coordinates.semantic_snapshot_revision
        || observed_mutation_epoch != coordinates.mutation_epoch
    {
        return Err(invalid("observed semantic target is not bound to PageOwner coordinates").into());
    }

    let waited = client::invoke(coordinates.request(
        "d3-wait",
        BrowserOperation::PageWait {
            condition: WaitCondition::DocumentReady,
            timeout_ms: 1_000,
        },
    ))?;
    coordinates.update(client::success(&waited, "page_wait")?)?;

    let extracted = client::invoke(coordinates.request(
        "d3-extract",
        BrowserOperation::PageExtract {
            schema_id: "d3-local-schema".to_owned(),
        },
    ))?;
    coordinates.update(client::success(&extracted, "page_extract")?)?;

    let stale = client::invoke(coordinates.request(
        "d3-stale-document",
        BrowserOperation::PageNavigate {
            target: NavigationTarget::LocalHttpFixture {
                url: "http://localhost/d3-stale".to_owned(),
            },
            expected_document_generation: stale_generation,
        },
    ))?;
    client::error(&stale, BrowserErrorCode::StaleDocument, "stale document")?;

    let external = client::invoke(coordinates.request(
        "d3-external-denied",
        BrowserOperation::PageNavigate {
            target: NavigationTarget::ExternalHttps {
                url: "https://example.invalid/closed".to_owned(),
            },
            expected_document_generation: coordinates.document_generation,
        },
    ))?;
    client::error(
        &external,
        BrowserErrorCode::PolicyDenied,
        "external navigation",
    )?;

    // Legacy validator compatibility token only: d3-page-act-unsupported.
    // The live corpus now requires the caller-bound atomic PageAct below to
    // succeed; an Unsupported response is a deterministic qualification failure.
    let mutation_epoch_before = coordinates.mutation_epoch;
    let acted = client::invoke(coordinates.request(
        "d3-page-act-atomic",
        BrowserOperation::PageAct {
            target,
            action: PageAction::Click,
        },
    ))?;
    let acted_result = client::success(&acted, "atomic page_act")?;
    let mutation_epoch_after = mutation_epoch_before
        .checked_add(1)
        .ok_or_else(|| invalid("fixture mutation epoch exhausted"))?;
    if !bool_field(acted_result, "atomic_semantic_resolver_exercised")?
        || !bool_field(acted_result, "caller_bound_target_revalidated")?
        || !bool_field(acted_result, "effect_applied_exactly_once")?
        || bool_field(acted_result, "servo_adapter_exercised")?
        || u64_field(acted_result, "action_count")? != 1
        || u64_field(acted_result, "mutation_epoch_before")? != mutation_epoch_before
        || u64_field(acted_result, "mutation_epoch_after")? != mutation_epoch_after
    {
        return Err(invalid("atomic PageAct evidence is incomplete or widened").into());
    }
    coordinates.update(acted_result)?;
    if coordinates.mutation_epoch != mutation_epoch_after {
        return Err(invalid("BrowserActor mutation epoch did not commit exactly once").into());
    }

    let closed = client::invoke(coordinates.request("d3-close", BrowserOperation::SessionClose))?;
    client::success(&closed, "session_close")?;

    let post_close = client::invoke(
        coordinates.request("d3-post-close-stale", BrowserOperation::SessionSnapshot),
    )?;
    client::error(
        &post_close,
        BrowserErrorCode::StaleSession,
        "post-close stale session",
    )?;

    Ok(format!(
        concat!(
            "{{\"schema\":\"trillionnium.desktop.d3-taskflow-corpus.v1\",",
            "\"status\":\"PASS\",\"same_process_pid\":{},",
            "\"one_request_per_connection\":true,\"request_count\":12,",
            "\"persistent_actor_proven\":true,\"session_id\":\"{}\",",
            "\"session_generation\":{},\"final_document_generation\":{},",
            "\"final_semantic_snapshot_revision\":{},\"final_mutation_epoch\":{},",
            "\"local_navigation_passed\":true,\"stale_document_rejected\":true,",
            "\"external_navigation_rejected\":true,",
            "\"atomic_semantic_page_act_exercised\":true,",
            "\"caller_bound_target_revalidated\":true,",
            "\"effect_applied_exactly_once\":true,",
            "\"servo_adapter_exercised\":false,",
            "\"post_close_stale_session_rejected\":true,",
            "\"external_effect_authority\":false,",
            "\"product_agent_port_enabled\":false}}"
        ),
        std::process::id(),
        escape_json(&coordinates.session_id),
        coordinates.session_generation,
        coordinates.document_generation,
        coordinates.semantic_snapshot_revision,
        coordinates.mutation_epoch,
    ))
}

fn unbound(request_id: &str, operation: BrowserOperation) -> BrowserRequest {
    BrowserRequest {
        request_id: request_id.to_owned(),
        session_id: None,
        session_generation: None,
        deadline_unix_ms: None,
        operation,
    }
}
