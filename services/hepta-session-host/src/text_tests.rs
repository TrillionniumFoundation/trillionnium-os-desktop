//! Presentation fixtures only; synthetic receipts do not qualify a Root lane.
use super::*;
use hepta_control_core::chat_timeline::{Message, MessagePhase, Role};
use serde_json::json;

fn owner() -> TextOwnerReceipt {
    TextOwnerReceipt {
        schema_version: 1,
        protocol: "hepta.ui-chat-owner.v1".into(),
        principal_id: "human".into(),
        session_id: "session".into(),
        permission_revision: 1,
        expires_at_ms: 500_000,
        route: codex_hepta_agentd::text_session::AgentdTextSessionConfig {
            control_socket: "/fixture/original.sock".into(),
            agent_id: codex_hepta_contracts::AgentId::parse("018f4f72-5f8f-7cc1-8f55-df9fb3aa2c12")
                .unwrap(),
            spawn_generation: 2,
            thread_id: "thread-one".into(),
            app_server_session_id: "original-session".into(),
            codex_home: "/fixture/home".into(),
        },
        can_interrupt: true,
        can_resolve_approvals: false,
        intent_namespace: "text:fixture".into(),
        next_intent_sequence: 2,
    }
}

fn reference() -> TextPrepared {
    let payload = br#"{"spawn_generation":1,"thread_id":"thread-one","text":"same local text"}"#;
    TextPrepared {
        host_reference: "text:fixture:1".into(),
        issuer_id: "issuer".into(),
        key_epoch: 1,
        message_id: "issuer:original:1".into(),
        sequence: 1,
        expires_at_ms: 1,
        payload_sha256: *codex_hepta_types::Digest32::of_bytes(payload).as_array(),
        envelope_sha256: [2; 32],
        text: "same local text".into(),
        delivery_id: codex_hepta_types::Digest32::from_array([3; 32]).to_string(),
        spawn_generation: 1,
        lookup_only: true,
    }
}

#[test]
fn approval_scope_is_not_derived_from_text_or_interrupt_permission() {
    let original = owner();
    let mut workspace = ChatWorkspace::default();
    workspace
        .install_owner(owner_session(original.clone(), 7), 10)
        .unwrap();
    assert!(
        workspace
            .authenticated_chat_scope(ChatCapability::SubmitSignedText, 10)
            .is_ok()
    );
    assert!(
        workspace
            .authenticated_chat_scope(ChatCapability::InterruptTurn, 10)
            .is_ok()
    );
    assert!(
        workspace
            .authenticated_chat_scope(ChatCapability::ResolveApproval, 10)
            .is_err()
    );
    let mut explicitly_permitted = original;
    explicitly_permitted.can_resolve_approvals = true;
    workspace
        .install_owner(owner_session(explicitly_permitted, 8), 11)
        .unwrap();
    assert!(
        workspace
            .authenticated_chat_scope(ChatCapability::ResolveApproval, 11)
            .is_ok()
    );
    assert!(
        workspace
            .authenticated_chat_scope(ChatCapability::ResolveApproval, 500_000)
            .is_err()
    );
}

#[test]
fn recovered_original_input_never_dispatches_or_clears_an_identical_new_draft() {
    let directory = tempfile::tempdir().unwrap();
    let mut adapter = TextChatAdapter::start(
        directory.path().join("absent-root.sock"),
        std::process::id(),
        Arc::new(|| {}),
    )
    .unwrap();
    let mut workspace = ChatWorkspace::default();
    adapter
        .observe(
            &mut workspace,
            TextWorkerEvent::Connected { connection_id: 7 },
            10,
        )
        .unwrap();
    adapter
        .observe(
            &mut workspace,
            TextWorkerEvent::Authenticated {
                connection_id: 7,
                owner: owner(),
            },
            10,
        )
        .unwrap();
    workspace.edit("same local text".into());
    adapter
        .observe(
            &mut workspace,
            TextWorkerEvent::Recovered {
                connection_id: 7,
                reference: reference(),
            },
            11,
        )
        .unwrap();
    assert!(adapter.recovering);
    assert!(adapter.tickets.is_empty());
    adapter
        .observe(
            &mut workspace,
            TextWorkerEvent::History {
                connection_id: 7,
                viewing_earlier: false,
                page: codex_hepta_agentd::text_session::TextHistorySnapshot {
                    turns: Vec::new(),
                    earlier_cursor: None,
                    notice: None,
                },
            },
            11,
        )
        .unwrap();
    adapter
        .observe(
            &mut workspace,
            TextWorkerEvent::RecoveryComplete { connection_id: 7 },
            11,
        )
        .unwrap();
    assert!(!adapter.recovering);
    adapter
        .observe(
            &mut workspace,
            TextWorkerEvent::Admission {
                connection_id: 7,
                request_id: "text:fixture:1".into(),
                message_id: "issuer:original:1".into(),
                status: AuthBusTextStatus {
                    delivery_id: reference().delivery_id,
                    state: AuthBusTextState::QueueAccepted,
                    delivery_attempts: 1,
                    queue_receipt_digest: Some(
                        codex_hepta_types::Digest32::from_array([4; 32]).to_string(),
                    ),
                },
            },
            12,
        )
        .unwrap();
    assert_eq!(workspace.draft().text, "same local text");
    assert!(adapter.tickets.is_empty());
    let before = workspace.draft().clone();
    assert!(
        adapter
            .observe(
                &mut workspace,
                TextWorkerEvent::Recovered {
                    connection_id: 6,
                    reference: reference()
                },
                12
            )
            .is_err()
    );
    assert_eq!(workspace.draft(), &before);
    adapter
        .observe(
            &mut workspace,
            TextWorkerEvent::Retired {
                connection_id: 7,
                request_id: "text:fixture:1".into(),
                message_id: "issuer:original:1".into(),
            },
            13,
        )
        .unwrap();
    assert!(adapter.intents.is_empty());
    assert!(adapter.releases.contains("issuer:original:1"));
    assert_eq!(workspace.draft(), &before);
}

#[test]
fn original_oversize_history_notice_does_not_block_reference_recovery() {
    let directory = tempfile::tempdir().unwrap();
    let mut adapter = TextChatAdapter::start(
        directory.path().join("absent-root.sock"),
        std::process::id(),
        Arc::new(|| {}),
    )
    .unwrap();
    let mut workspace = ChatWorkspace::default();
    adapter
        .observe(
            &mut workspace,
            TextWorkerEvent::Connected { connection_id: 7 },
            10,
        )
        .unwrap();
    adapter
        .observe(
            &mut workspace,
            TextWorkerEvent::Authenticated {
                connection_id: 7,
                owner: owner(),
            },
            10,
        )
        .unwrap();
    workspace.edit("a new original input remains possible".into());
    adapter
        .observe(
            &mut workspace,
            TextWorkerEvent::History {
                connection_id: 7,
                viewing_earlier: false,
                page: codex_hepta_agentd::text_session::TextHistorySnapshot {
                    turns: Vec::new(),
                    earlier_cursor: Some("original-cursor".into()),
                    notice: Some("Original large item preview is unavailable".into()),
                },
            },
            11,
        )
        .unwrap();
    adapter
        .observe(
            &mut workspace,
            TextWorkerEvent::RecoveryComplete { connection_id: 7 },
            11,
        )
        .unwrap();
    assert!(!adapter.recovering && adapter.history_ready && adapter.can_load_earlier);
    assert!(
        workspace
            .authenticated_chat_scope(ChatCapability::SubmitSignedText, 11)
            .is_ok()
    );
    assert_eq!(
        workspace.draft().text,
        "a new original input remains possible"
    );
    assert_eq!(
        workspace.presentation_note.as_deref(),
        Some("Original large item preview is unavailable")
    );
}

#[test]
fn original_typed_attachment_history_preserves_chinese_draft_and_next_thread_stream() {
    let directory = tempfile::tempdir().unwrap();
    let mut adapter = TextChatAdapter::start(
        directory.path().join("absent-root.sock"),
        std::process::id(),
        Arc::new(|| {}),
    )
    .unwrap();
    let mut workspace = ChatWorkspace::default();
    adapter
        .observe(
            &mut workspace,
            TextWorkerEvent::Connected { connection_id: 7 },
            10,
        )
        .unwrap();
    adapter
        .observe(
            &mut workspace,
            TextWorkerEvent::Authenticated {
                connection_id: 7,
                owner: owner(),
            },
            10,
        )
        .unwrap();
    workspace.edit("  下一条中文\n保留原文。  ".into());
    let draft = workspace.draft().clone();
    // Deserialize actual original Turn/UserInput protocol types before the
    // adapter serializes them for its existing ChatWorkspace projection.
    let turn = serde_json::from_value(json!({
        "id":"attachment-turn","itemsView":"full","status":"completed","items":[
            {"type":"userMessage","id":"attachment-input","clientId":"another-client","content":[
                {"type":"text","text":"  原始中文\n请看附件。  ","text_elements":[]},
                {"type":"image","url":"data:image/png;base64,DO_NOT_EXPAND"},
                {"type":"localImage","path":"/private/do-not-open.png"},
                {"type":"audio","url":"https://example.invalid/do-not-fetch.wav"},
                {"type":"localAudio","path":"/private/do-not-open.wav"},
                {"type":"skill","name":"do-not-invoke","path":"/private/skill.md"},
                {"type":"mention","name":"do-not-resolve","path":"connector://private"}
            ]}
        ]
    }))
    .unwrap();
    adapter
        .observe(
            &mut workspace,
            TextWorkerEvent::History {
                connection_id: 7,
                viewing_earlier: false,
                page: codex_hepta_agentd::text_session::TextHistorySnapshot {
                    turns: vec![turn],
                    earlier_cursor: Some("original-earlier-page".into()),
                    notice: None,
                },
            },
            11,
        )
        .unwrap();
    adapter
        .observe(
            &mut workspace,
            TextWorkerEvent::RecoveryComplete { connection_id: 7 },
            11,
        )
        .unwrap();
    assert!(adapter.history_ready && !adapter.history_pending && !adapter.recovering);
    assert!(adapter.can_load_earlier && !adapter.viewing_earlier);
    assert!(
        workspace
            .authenticated_chat_scope(ChatCapability::SubmitSignedText, 11)
            .is_ok()
    );
    for notification in [
        json!({"method":"item/started","params":{
            "threadId":"thread-one","turnId":"following-turn","startedAtMs":12,
            "item":{"type":"agentMessage","id":"following-reply","text":""}
        }}),
        json!({"method":"item/agentMessage/delta","params":{
            "threadId":"thread-one","turnId":"following-turn","itemId":"following-reply","delta":"继续处理中文。"
        }}),
        json!({"method":"turn/completed","params":{
            "threadId":"thread-one","turn":{"id":"following-turn","status":"completed","items":[]}
        }}),
    ] {
        adapter
            .observe(
                &mut workspace,
                TextWorkerEvent::Notification(codex_hepta_agentd::text_session::AgentdTextEvent {
                    connection_id: 7,
                    thread_id: "thread-one".into(),
                    message_id: String::new(),
                    delivery_id: String::new(),
                    turn_id: "following-turn".into(),
                    notification: serde_json::from_value(notification).unwrap(),
                }),
                12,
            )
            .unwrap();
    }
    let history = workspace.timeline().unwrap().history().unwrap();
    assert_eq!(history.thread_id, "thread-one");
    assert_eq!(
        history.messages,
        vec![
            Message {
                id: "attachment-input".into(),
                turn_id: "attachment-turn".into(),
                role: Role::User,
                text: concat!(
                    "  原始中文\n请看附件。  \n",
                    "[Original image attachment; preview unavailable]\n",
                    "[Original local image attachment; preview unavailable]\n",
                    "[Original audio attachment; preview unavailable]\n",
                    "[Original local audio attachment; preview unavailable]\n",
                    "[Original skill reference; details remain in App Server]\n",
                    "[Original mention reference; details remain in App Server]"
                )
                .into(),
                phase: MessagePhase::Observed,
            },
            Message {
                id: "following-reply".into(),
                turn_id: "following-turn".into(),
                role: Role::Assistant,
                text: "继续处理中文。".into(),
                phase: MessagePhase::Completed,
            },
        ]
    );
    assert_eq!(workspace.draft(), &draft);
    assert!(adapter.intents.is_empty() && adapter.tickets.is_empty());
}

#[test]
fn thirty_two_proven_unsigned_closures_release_capacity_without_changing_drafts_or_signed_refs() {
    let directory = tempfile::tempdir().unwrap();
    let mut adapter = TextChatAdapter::start(
        directory.path().join("absent-root.sock"),
        std::process::id(),
        Arc::new(|| {}),
    )
    .unwrap();
    let mut workspace = ChatWorkspace::default();
    adapter
        .observe(
            &mut workspace,
            TextWorkerEvent::Connected { connection_id: 7 },
            10,
        )
        .unwrap();
    adapter
        .observe(
            &mut workspace,
            TextWorkerEvent::Authenticated {
                connection_id: 7,
                owner: owner(),
            },
            10,
        )
        .unwrap();
    workspace.edit("preserve the entire local draft".into());
    let before = workspace.draft().clone();
    let text_sha256 = *codex_hepta_types::Digest32::of_bytes(before.text.as_bytes()).as_array();
    for number in 1..=32 {
        let request_id = format!("text:fixture:{number}");
        adapter.intents.insert(
            request_id.clone(),
            Intent {
                room: workspace.active_id(),
                text: before.text.clone(),
                message_id: None,
                clear_draft: true,
            },
        );
        adapter.signing = Some(request_id.clone());
        adapter
            .observe(
                &mut workspace,
                TextWorkerEvent::PreparationClosed {
                    connection_id: 7,
                    request_id,
                    text_sha256,
                    original_watermark: Some(number),
                    message: "Original Root closure fixture".into(),
                },
                11,
            )
            .unwrap();
        assert!(adapter.intents.is_empty() && adapter.signing.is_none());
        assert_eq!(workspace.draft(), &before);
    }
    adapter
        .observe(
            &mut workspace,
            TextWorkerEvent::Recovered {
                connection_id: 7,
                reference: reference(),
            },
            12,
        )
        .unwrap();
    let retained = adapter
        .intents
        .get("text:fixture:1")
        .unwrap()
        .message_id
        .clone();
    assert!(
        adapter
            .observe(
                &mut workspace,
                TextWorkerEvent::PreparationClosed {
                    connection_id: 7,
                    request_id: "text:fixture:1".into(),
                    text_sha256,
                    original_watermark: Some(32),
                    message: "Must not clear signed reference".into(),
                },
                13
            )
            .is_err()
    );
    assert_eq!(
        adapter.intents.get("text:fixture:1").unwrap().message_id,
        retained
    );
    assert_eq!(workspace.draft(), &before);
    assert!(adapter.tickets.is_empty());
}

#[test]
fn unsigned_closure_rejects_stale_or_different_text_but_can_finish_after_disconnect() {
    let directory = tempfile::tempdir().unwrap();
    let mut adapter = TextChatAdapter::start(
        directory.path().join("absent-root.sock"),
        std::process::id(),
        Arc::new(|| {}),
    )
    .unwrap();
    let mut workspace = ChatWorkspace::default();
    adapter
        .observe(
            &mut workspace,
            TextWorkerEvent::Connected { connection_id: 7 },
            10,
        )
        .unwrap();
    adapter
        .observe(
            &mut workspace,
            TextWorkerEvent::Authenticated {
                connection_id: 7,
                owner: owner(),
            },
            10,
        )
        .unwrap();
    workspace.edit("newer local text".into());
    adapter.intents.insert(
        "text:fixture:3".into(),
        Intent {
            room: workspace.active_id(),
            text: "attempted input".into(),
            message_id: None,
            clear_draft: true,
        },
    );
    let text_sha256 = *codex_hepta_types::Digest32::of_bytes(b"attempted input").as_array();
    for (connection_id, digest) in [(6, text_sha256), (7, [0; 32])] {
        assert!(
            adapter
                .observe(
                    &mut workspace,
                    TextWorkerEvent::PreparationClosed {
                        connection_id,
                        request_id: "text:fixture:3".into(),
                        text_sha256: digest,
                        original_watermark: None,
                        message: "invalid fixture".into(),
                    },
                    11
                )
                .is_err()
        );
        assert_eq!(adapter.intents.len(), 1);
    }
    adapter.disconnect(&mut workspace, "transport was disconnected".into());
    let disconnected = workspace.draft().clone();
    adapter
        .observe(
            &mut workspace,
            TextWorkerEvent::PreparationClosed {
                connection_id: 7,
                request_id: "text:fixture:3".into(),
                text_sha256,
                original_watermark: None,
                message: "Original exact preparation closed".into(),
            },
            12,
        )
        .unwrap();
    assert!(adapter.intents.is_empty() && adapter.unavailable && adapter.owner.is_none());
    assert_eq!(workspace.draft(), &disconnected);
    workspace
        .install_owner(owner_session(owner(), 8), 13)
        .unwrap();
    assert_eq!(workspace.draft().text, "newer local text");
}
