use hepta_os_observer::cpu_delivery::{
    BindingError, CpuDeliveryId, CpuDeliveryIdentity, CpuHistoryObservation, CpuHistoryTransport,
    HistoryError, HistoryView, RecordedCpuDelivery, UnknownReason, HISTORY_REQUEST_BYTES,
    HISTORY_RESPONSE_BYTES, INSTALL_FRAME_BYTES,
};
use hos2_os_abi::{
    install_budget_request_id, DeliveryState, InstallBudgetRequest, Opcode, QueryDeliveryResponse,
    Request, RequestPayload, Response, ResponsePayload, Status, CPU_PERIOD_NS,
};

fn identity() -> CpuDeliveryIdentity {
    let fixture: serde_json::Value =
        serde_json::from_str(include_str!("fixtures/hos2_production_owner.json")).unwrap();
    CpuDeliveryIdentity {
        operation_id: "operation-a".into(),
        subject_id: "subject-a".into(),
        payload_digest: serde_json::from_value(fixture["payload_digest"].clone()).unwrap(),
        scope_digest: serde_json::from_value(fixture["scope_digest"].clone()).unwrap(),
        semantic_digest: serde_json::from_value(fixture["semantic_digest"].clone()).unwrap(),
        policy_generation: 7,
        owner_generation: 3,
    }
}

fn fixture_field(field: &str) -> String {
    let fixture: serde_json::Value =
        serde_json::from_str(include_str!("fixtures/hos2_production_owner.json")).unwrap();
    fixture[field].as_str().unwrap().to_owned()
}

fn fixture_bytes(field: &str) -> Vec<u8> {
    fixture_field(field)
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
        .collect()
}

fn delivery() -> CpuDeliveryId {
    CpuDeliveryId {
        boot_id: [1; 16],
        capspace_id: [2; 16],
        sequence: 1,
    }
}

fn request_id() -> [u8; 16] {
    install_budget_request_id(1).unwrap()
}

fn install() -> [u8; INSTALL_FRAME_BYTES] {
    let request = Request {
        opcode: Opcode::InstallBudget,
        request_id: request_id(),
        target_slot: 2,
        target_generation: 1,
        payload: RequestPayload::InstallBudget(InstallBudgetRequest {
            expected_revision: 1,
            period_ns: CPU_PERIOD_NS,
            cap_ns: 25_000_000,
            reserved: 0,
        }),
    };
    let mut bytes = [0; INSTALL_FRAME_BYTES];
    assert_eq!(request.encode(&mut bytes).unwrap(), bytes.len());
    bytes
}

fn retained() -> RecordedCpuDelivery {
    RecordedCpuDelivery::from_owner_record(identity(), &fixture_field("payload_json")).unwrap()
}

#[test]
fn pinned_agentd_frames_pass_the_original_a02_request_and_response_decoders() {
    for (request_field, response_field) in [
        ("abi_request_hex", "abi_response_hex"),
        ("install_frame_hex", "install_response_hex"),
        ("history_request_hex", "history_response_hex"),
    ] {
        let request_bytes = fixture_bytes(request_field);
        let response_bytes = fixture_bytes(response_field);
        let request = Request::decode(&request_bytes).unwrap();
        let response = Response::decode(&response_bytes).unwrap();
        response.validate_for(&request).unwrap();
        let mut encoded = vec![0; request_bytes.len()];
        assert_eq!(request.encode(&mut encoded).unwrap(), encoded.len());
        assert_eq!(encoded, request_bytes);
        let mut encoded = vec![0; response_bytes.len()];
        assert_eq!(response.encode(&mut encoded).unwrap(), encoded.len());
        assert_eq!(encoded, response_bytes);
    }
}

fn view() -> HistoryView {
    HistoryView {
        slot: 3,
        generation: 1,
    }
}

fn response() -> Response {
    Response {
        opcode: Opcode::QueryDelivery,
        status: Status::Ok,
        request_id: request_id(),
        boot_id: delivery().boot_id,
        revision: 0,
        payload: ResponsePayload::QueryDelivery(QueryDeliveryResponse {
            state: DeliveryState::Terminal,
            saved_status: Status::Ok,
            sequence: 1,
            stable_object_id: [9; 16],
            saved_revision: 2,
            previous_revision: 1,
            effective_ns: CPU_PERIOD_NS + 1_001,
            consumed_ns: 999,
        }),
    }
}

struct Transport {
    bytes: Vec<u8>,
    requests: Vec<Request>,
    fail: bool,
    claimed_length: Option<usize>,
}

impl Transport {
    fn with_response(response: Response) -> Self {
        let mut bytes = vec![0; HISTORY_RESPONSE_BYTES];
        let length = response.encode(&mut bytes).unwrap();
        bytes.truncate(length);
        Self {
            bytes,
            requests: Vec::new(),
            fail: false,
            claimed_length: None,
        }
    }
}

impl CpuHistoryTransport for Transport {
    type Error = &'static str;

    fn query_delivery(
        &mut self,
        request: &[u8; HISTORY_REQUEST_BYTES],
        response: &mut [u8; HISTORY_RESPONSE_BYTES],
    ) -> Result<usize, Self::Error> {
        let request = Request::decode(request).unwrap();
        assert_eq!(request.opcode, Opcode::QueryDelivery);
        assert!(matches!(request.payload, RequestPayload::QueryDelivery(_)));
        self.requests.push(request);
        if self.fail {
            return Err("lost reply");
        }
        response[..self.bytes.len()].copy_from_slice(&self.bytes);
        Ok(self.claimed_length.unwrap_or(self.bytes.len()))
    }
}

#[test]
fn original_k_d_and_install_bytes_remain_separate_and_immutable() {
    let original = identity();
    let mut supplied = fixture_field("payload_json");
    let retained = RecordedCpuDelivery::from_owner_record(original.clone(), &supplied).unwrap();
    supplied.clear();
    assert_eq!(retained.identity(), &original);
    assert_eq!(retained.delivery_id(), delivery());
    assert_eq!(
        retained.recorded_payload_json(),
        fixture_field("payload_json")
    );
    assert_eq!(retained.recorded_install_bytes(), &install());
    assert_eq!(
        retained.recorded_install_bytes().as_slice(),
        fixture_bytes("install_frame_hex")
    );
    let mut transport = Transport::with_response(response());
    assert_eq!(
        retained.query_once(&mut transport, view(), request_id()),
        Ok(CpuHistoryObservation::Installed {
            stable_object_id: [9; 16],
            revision: 2,
            previous_revision: 1,
            effective_ns: CPU_PERIOD_NS + 1_001,
            consumed_ns: 999,
        })
    );
    assert_eq!(transport.requests.len(), 1);
    let query = transport.requests[0];
    assert_eq!((query.target_slot, query.target_generation), (3, 1));
    let mut bytes = [0; HISTORY_REQUEST_BYTES];
    query.encode(&mut bytes).unwrap();
    assert_eq!(bytes.as_slice(), fixture_bytes("history_request_hex"));
    assert_eq!(transport.bytes, fixture_bytes("history_response_hex"));
    assert_ne!(
        query.target_slot,
        Request::decode(&install()).unwrap().target_slot
    );
    let RequestPayload::QueryDelivery(delivery) = query.payload else {
        panic!("adapter emitted a mutation");
    };
    assert_eq!(delivery.history_boot, retained.delivery_id().boot_id);
    assert_eq!(delivery.history_space, retained.delivery_id().capspace_id);
    assert_eq!(delivery.sequence, retained.delivery_id().sequence);
    assert_eq!(retained.identity(), &original);
}

#[test]
fn missing_retired_reserved_or_lost_history_never_means_no_effect() {
    for (state, reason) in [
        (DeliveryState::Reserved, UnknownReason::Reserved),
        (DeliveryState::Retired, UnknownReason::Retired),
        (DeliveryState::NotSeen, UnknownReason::NotSeen),
        (DeliveryState::HistoryLost, UnknownReason::HistoryLost),
    ] {
        let mut reply = response();
        reply.payload = ResponsePayload::QueryDelivery(QueryDeliveryResponse {
            state,
            saved_status: Status::Ok,
            sequence: 1,
            stable_object_id: [0; 16],
            saved_revision: 0,
            previous_revision: 0,
            effective_ns: 0,
            consumed_ns: 0,
        });
        let mut transport = Transport::with_response(reply);
        assert_eq!(
            retained().query_once(&mut transport, view(), request_id()),
            Ok(CpuHistoryObservation::Unknown(reason))
        );
        assert_eq!(transport.requests.len(), 1);
    }
}

#[test]
fn outer_refusal_is_not_a_saved_terminal_result() {
    for status in [
        Status::PermissionDenied,
        Status::Revoked,
        Status::Unsupported,
    ] {
        let mut reply = response();
        reply.status = status;
        reply.payload = ResponsePayload::Empty;
        let mut transport = Transport::with_response(reply);
        assert_eq!(
            retained().query_once(&mut transport, view(), request_id()),
            Ok(CpuHistoryObservation::Unknown(UnknownReason::OuterStatus(
                status
            )))
        );
    }
}

#[test]
fn saved_semantic_rejection_is_distinct_from_indeterminate_or_busy() {
    for status in [
        Status::PermissionDenied,
        Status::Indeterminate,
        Status::Busy,
    ] {
        let mut reply = response();
        reply.payload = ResponsePayload::QueryDelivery(QueryDeliveryResponse {
            state: DeliveryState::Terminal,
            saved_status: status,
            sequence: 1,
            stable_object_id: [0; 16],
            saved_revision: 0,
            previous_revision: 0,
            effective_ns: 0,
            consumed_ns: 0,
        });
        let mut transport = Transport::with_response(reply);
        let expected = if status == Status::PermissionDenied {
            CpuHistoryObservation::TerminalRejection(status)
        } else {
            CpuHistoryObservation::Unknown(UnknownReason::SavedStatus(status))
        };
        assert_eq!(
            retained().query_once(&mut transport, view(), request_id()),
            Ok(expected)
        );
    }
}

#[test]
fn boot_revision_sequence_and_read_id_are_all_bound() {
    for case in 0..4 {
        let mut reply = response();
        let expected = match case {
            0 => {
                reply.boot_id = [55; 16];
                HistoryError::BootChanged
            }
            1 => {
                let ResponsePayload::QueryDelivery(ref mut value) = reply.payload else {
                    unreachable!()
                };
                value.previous_revision += 1;
                value.saved_revision += 1;
                HistoryError::RevisionChanged
            }
            2 => {
                let ResponsePayload::QueryDelivery(ref mut value) = reply.payload else {
                    unreachable!()
                };
                value.sequence += 1;
                HistoryError::MalformedResponse
            }
            _ => {
                reply.request_id = [77; 16];
                HistoryError::MalformedResponse
            }
        };
        let mut transport = Transport::with_response(reply);
        assert_eq!(
            retained().query_once(&mut transport, view(), request_id()),
            Err(expected)
        );
        assert_eq!(transport.requests.len(), 1);
    }
}

#[test]
fn stable_object_comes_from_native_history_and_is_not_fabricated_in_source_payload() {
    let mut reply = response();
    let ResponsePayload::QueryDelivery(ref mut value) = reply.payload else {
        unreachable!()
    };
    value.stable_object_id = [66; 16];
    let mut transport = Transport::with_response(reply);
    assert_eq!(
        retained().query_once(&mut transport, view(), request_id()),
        Ok(CpuHistoryObservation::Installed {
            stable_object_id: [66; 16],
            revision: 2,
            previous_revision: 1,
            effective_ns: CPU_PERIOD_NS + 1_001,
            consumed_ns: 999,
        })
    );
}

#[test]
fn transport_loss_and_invalid_lengths_never_retry_or_allocate_delivery() {
    let retained = retained();
    let original = retained.identity().clone();
    let mut transport = Transport::with_response(response());
    transport.fail = true;
    assert_eq!(
        retained.query_once(&mut transport, view(), request_id()),
        Err(HistoryError::Transport("lost reply"))
    );
    assert_eq!(transport.requests.len(), 1);
    assert_eq!(retained.identity(), &original);
    for length in [0, 63, 127, HISTORY_RESPONSE_BYTES + 1, usize::MAX] {
        let mut transport = Transport::with_response(response());
        transport.claimed_length = Some(length);
        assert_eq!(
            retained.query_once(&mut transport, view(), request_id()),
            Err(HistoryError::MalformedResponse)
        );
        assert_eq!(transport.requests.len(), 1);
    }
}

#[test]
fn invalid_view_or_read_id_fails_before_transport_entry() {
    for (handle, request_id) in [
        (
            HistoryView {
                slot: 0,
                generation: 1,
            },
            request_id(),
        ),
        (
            HistoryView {
                slot: 1,
                generation: 0,
            },
            request_id(),
        ),
        (view(), [0; 16]),
    ] {
        let mut transport = Transport::with_response(response());
        assert_eq!(
            retained().query_once(&mut transport, handle, request_id),
            Err(HistoryError::InvalidQuery)
        );
        assert!(transport.requests.is_empty());
    }
}

#[test]
fn invalid_owner_or_digest_binding_cannot_create_a_snapshot() {
    for case in 0..9 {
        let mut id = identity();
        let expected = match case {
            0 => {
                id.operation_id.clear();
                BindingError::InvalidOwnerIdentity
            }
            1 => {
                id.subject_id = "x".repeat(129);
                BindingError::InvalidOwnerIdentity
            }
            2 => {
                id.owner_generation = 0;
                BindingError::InvalidOwnerIdentity
            }
            3 => {
                id.payload_digest.fill(0);
                BindingError::PayloadDigestMismatch
            }
            4 => {
                id.scope_digest.fill(0);
                BindingError::ScopeDigestMismatch
            }
            5 => {
                id.semantic_digest.fill(0);
                BindingError::SemanticDigestMismatch
            }
            6 => {
                id.operation_id.push('x');
                BindingError::SemanticDigestMismatch
            }
            7 => {
                id.subject_id.push('x');
                BindingError::SemanticDigestMismatch
            }
            _ => {
                id.policy_generation += 1;
                BindingError::SemanticDigestMismatch
            }
        };
        assert_eq!(
            RecordedCpuDelivery::from_owner_record(id, &fixture_field("payload_json")).unwrap_err(),
            expected
        );
    }
}

#[test]
fn canonical_owner_payload_rejects_ambiguity_truncation_and_invalid_d() {
    let original = fixture_field("payload_json");
    for payload in [
        String::new(),
        original[..original.len() - 1].to_owned(),
        format!("{original} "),
        " ".repeat(1025),
        original.replacen(
            "\"schema_version\":1",
            "\"schema_version\":1,\"schema_version\":1",
            1,
        ),
        original.replacen("\"schema_version\":1", "\"schema_version\":2", 1),
        original.replacen(
            "\"schema_version\":1",
            "\"extra\":0,\"schema_version\":1",
            1,
        ),
    ] {
        assert_eq!(
            RecordedCpuDelivery::from_owner_record(identity(), &payload).unwrap_err(),
            BindingError::InvalidOwnerPayload
        );
    }
    for sequence in [
        "0",
        "0000000000000000",
        "ffffffffffffffff",
        "000000000000000A",
    ] {
        let payload = original.replace("0000000000000001", sequence);
        assert_eq!(
            RecordedCpuDelivery::from_owner_record(identity(), &payload).unwrap_err(),
            BindingError::InvalidDeliveryIdentity
        );
    }
    for (before, after) in [
        ("\"cap_ns\":25000000", "\"cap_ns\":25000001"),
        ("\"manage_slot\":2", "\"manage_slot\":3"),
        ("\"expected_revision\":1", "\"expected_revision\":2"),
    ] {
        let payload = original.replace(before, after);
        assert_eq!(
            RecordedCpuDelivery::from_owner_record(identity(), &payload).unwrap_err(),
            BindingError::PayloadDigestMismatch
        );
    }
}
