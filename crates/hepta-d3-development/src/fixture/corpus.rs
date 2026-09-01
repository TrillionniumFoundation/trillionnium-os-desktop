use crate::client;
use crate::model::Coordinates;
use crate::{AnyError, escape_json};
use hepta_browser_codec::{
    BrowserErrorCode, BrowserOperation, BrowserRequest, ElementReference, NavigationTarget,
    ObservationField, PageAction, ProfilePersistence, ProfileSpec, WaitCondition,
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
    coordinates.update(client::success(&observed, "page_observe")?)?;

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

    let acted = client::invoke(coordinates.request(
        "d3-page-act-unsupported",
        BrowserOperation::PageAct {
            target: ElementReference {
                session_generation: coordinates.session_generation,
                document_generation: coordinates.document_generation,
                semantic_snapshot_revision: coordinates.semantic_snapshot_revision,
                frame_id: "frame-main".to_owned(),
                backend_node_key: Some("submit-primary".to_owned()),
                role: Some("button".to_owned()),
                accessible_name_sha256: None,
                structural_fingerprint: "11".repeat(32),
            },
            action: PageAction::Click,
        },
    ))?;
    client::error(
        &acted,
        BrowserErrorCode::Unsupported,
        "semantic resolver ceiling",
    )?;

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
            "\"page_act_without_servo_resolver_rejected\":true,",
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
