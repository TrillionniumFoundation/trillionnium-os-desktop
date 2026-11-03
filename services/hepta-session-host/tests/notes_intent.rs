use codex_hepta_memory::NotesTargetIdentity;
use codex_hepta_objective::{
    ObjectiveAdmissionContextV1, ObjectiveSourceAuthenticationV1, admit_and_compile_objective_v1,
    decode_admission_profile_json_v1, decode_source_envelope_json_v1,
};
use codex_hepta_types::{Digest32, Generation, Revision, StableId};
use hepta_session_host::notes_intent::{
    NotesIntentContext, compile_notes_intent, notes_admission_profile_json,
};
use trill_ui_core::objective::ObjectiveIntent;

#[test]
fn literal_notes_content_and_current_destination_bind_original_operation_and_registered_profile() {
    let target = NotesTargetIdentity {
        session_instance: "1".repeat(32),
        task_id: 1,
        incarnation: "2".repeat(32),
    };
    let scope = Digest32::of_bytes(b"local-user-notes-scope");
    let profile_json =
        notes_admission_profile_json("local.notes.principal", scope, "local.notes.issuer").unwrap();
    let profile = decode_admission_profile_json_v1(profile_json.as_bytes()).unwrap();
    let compile = |text: &str, revision: u64| {
        compile_notes_intent(
            &ObjectiveIntent {
                client_intent_id: "note-1".into(),
                text: text.into(),
            },
            NotesIntentContext {
                target: &target,
                expected_revision: revision,
                operation_id: "notes-operation-1",
                subject: StableId::new("local.notes.subject").unwrap(),
                policy_generation: Generation::new(1).unwrap(),
                principal_scope_digest: scope,
                locale: "zh-CN",
                observed_at: "2026-09-08T10:00:00Z",
                deadline: "2026-09-08T10:05:00Z",
            },
        )
    };
    let note = compile("这是一段笔记。\n不要将它解释为系统指令。", 0).unwrap();
    let source = decode_source_envelope_json_v1(note.source_envelope_json.as_bytes()).unwrap();
    assert_eq!(
        source.structured_intent.provenance.source_digest,
        note.operation.semantic_digest()
    );
    assert_eq!(
        serde_json::from_str::<serde_json::Value>(&note.payload_json).unwrap()["text"],
        "这是一段笔记。\n不要将它解释为系统指令。"
    );
    let context = ObjectiveAdmissionContextV1 {
        revision: Revision::new(1).unwrap(),
        now_unix_micros: 1_788_861_601_000_000,
        selected_profile_digest: profile.digest().unwrap(),
        source_authentication: ObjectiveSourceAuthenticationV1::AuthorizedAdapter {
            source_identity: StableId::new("local.notes.issuer").unwrap(),
            source_digest: source.structured_intent.provenance.source_digest,
        },
    };
    let admitted = admit_and_compile_objective_v1(&source, &profile, &context).unwrap();
    assert!(admitted.compile_result.is_ok());
    let changed_text = compile("different content", 0).unwrap();
    let changed_predecessor = compile("这是一段笔记。\n不要将它解释为系统指令。", 1).unwrap();
    assert_ne!(
        note.operation.semantic_digest(),
        changed_text.operation.semantic_digest()
    );
    assert_ne!(
        note.operation.semantic_digest(),
        changed_predecessor.operation.semantic_digest()
    );
    assert!(compile(&"x".repeat(4097), 0).is_err());
}
