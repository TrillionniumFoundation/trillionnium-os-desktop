#![no_std]

//! Explicit byte codec for the experimental HOS2 control ABI.
//!
//! The codec deliberately never casts a wire buffer to a Rust structure.  All
//! fields are read and written at their documented little-endian offsets.

pub const HOS2_MAGIC: [u8; 4] = *b"HOS2";
pub const HOSR_MAGIC: [u8; 4] = *b"HOSR";
pub const HOS2_MAJOR: u16 = 2;
pub const HOS2_MINOR: u16 = 0;
pub const HEADER_LEN: usize = 64;
pub const TRANSPORT_LEN: usize = 32;
pub const MAX_PAYLOAD: usize = 65_536;
pub const MAX_FRAME: usize = HEADER_LEN + MAX_PAYLOAD;
pub const CPU_PERIOD_NS: u64 = 100_000_000;

const REQUEST_RESERVED_OFFSET: usize = 20;
const RESPONSE_RESERVED_OFFSET: usize = 20;

/// Wire/parser failure.  Variants are intentionally structural; permission,
/// CAS and resource decisions belong to the kernel and are encoded as status.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Error {
    Truncated,
    InvalidMagic,
    UnknownVersion,
    UnknownOpcode,
    InvalidFlags,
    ReservedNonZero,
    InvalidHeaderLength,
    PayloadTooLarge,
    PayloadLengthMismatch,
    TrailingBytes,
    InvalidRequestId,
    InvalidTarget,
    InvalidGeneration,
    InvalidSequence,
    SequenceHighBytesNonZero,
    InvalidField,
    IntegerOverflow,
    InvalidStatus,
    MalformedErrorResponse,
    InsufficientCapacity,
    InvalidTransport,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u16)]
pub enum Opcode {
    QueryAbi = 1,
    ReadUsage = 2,
    InstallBudget = 3,
    QueryDelivery = 4,
    RetireThrough = 5,
}

impl Opcode {
    pub const fn as_u16(self) -> u16 {
        self as u16
    }

    pub const fn from_u16(value: u16) -> Result<Self, Error> {
        match value {
            1 => Ok(Self::QueryAbi),
            2 => Ok(Self::ReadUsage),
            3 => Ok(Self::InstallBudget),
            4 => Ok(Self::QueryDelivery),
            5 => Ok(Self::RetireThrough),
            _ => Err(Error::UnknownOpcode),
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u16)]
pub enum Status {
    Ok = 0,
    InvalidInput = 1,
    PermissionDenied = 2,
    StaleHandle = 3,
    Revoked = 4,
    Conflict = 5,
    ResourceExhausted = 6,
    Unsupported = 7,
    Indeterminate = 8,
    Busy = 9,
    OutOfOrder = 10,
    Retired = 11,
}

impl Status {
    pub const fn as_u16(self) -> u16 {
        self as u16
    }

    pub const fn from_u16(value: u16) -> Result<Self, Error> {
        match value {
            0 => Ok(Self::Ok),
            1 => Ok(Self::InvalidInput),
            2 => Ok(Self::PermissionDenied),
            3 => Ok(Self::StaleHandle),
            4 => Ok(Self::Revoked),
            5 => Ok(Self::Conflict),
            6 => Ok(Self::ResourceExhausted),
            7 => Ok(Self::Unsupported),
            8 => Ok(Self::Indeterminate),
            9 => Ok(Self::Busy),
            10 => Ok(Self::OutOfOrder),
            11 => Ok(Self::Retired),
            _ => Err(Error::InvalidStatus),
        }
    }
}

/// Wire size of a successful response payload for an opcode.
pub const fn response_payload_len(opcode: Opcode) -> usize {
    match opcode {
        Opcode::QueryAbi => 48,
        Opcode::ReadUsage => 64,
        Opcode::InstallBudget => 24,
        Opcode::QueryDelivery => 64,
        Opcode::RetireThrough => 16,
    }
}

/// Required response frame capacity for an opcode and outer status.
///
/// Error responses have no payload and therefore require only the 64-byte
/// response header.  This helper does not perform any user-address checks.
pub const fn response_frame_len(opcode: Opcode, status: Status) -> usize {
    HEADER_LEN
        + if matches!(status, Status::Ok) {
            response_payload_len(opcode)
        } else {
            0
        }
}

/// Alias with an explicit name for callers sizing a copyout buffer.
pub const fn required_response_frame_len(opcode: Opcode, status: Status) -> usize {
    response_frame_len(opcode, status)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Transport {
    pub request_addr: u64,
    pub response_addr: u64,
    pub request_bytes: u32,
    pub response_capacity: u32,
    pub reserved: u64,
}

impl Transport {
    pub const fn new(
        request_addr: u64,
        response_addr: u64,
        request_bytes: u32,
        response_capacity: u32,
    ) -> Self {
        Self {
            request_addr,
            response_addr,
            request_bytes,
            response_capacity,
            reserved: 0,
        }
    }

    pub fn decode(bytes: &[u8]) -> Result<Self, Error> {
        if bytes.len() < TRANSPORT_LEN {
            return Err(Error::Truncated);
        }
        if bytes.len() != TRANSPORT_LEN {
            return Err(Error::TrailingBytes);
        }
        let out = Self {
            request_addr: get_u64(bytes, 0),
            response_addr: get_u64(bytes, 8),
            request_bytes: get_u32(bytes, 16),
            response_capacity: get_u32(bytes, 20),
            reserved: get_u64(bytes, 24),
        };
        if out.reserved != 0 {
            return Err(Error::ReservedNonZero);
        }
        out.validate_lengths()?;
        Ok(out)
    }

    pub fn encode(&self, out: &mut [u8]) -> Result<usize, Error> {
        if out.len() < TRANSPORT_LEN {
            return Err(Error::InsufficientCapacity);
        }
        if self.reserved != 0 {
            return Err(Error::ReservedNonZero);
        }
        self.validate_lengths()?;
        put_u64(out, 0, self.request_addr);
        put_u64(out, 8, self.response_addr);
        put_u32(out, 16, self.request_bytes);
        put_u32(out, 20, self.response_capacity);
        put_u64(out, 24, self.reserved);
        Ok(TRANSPORT_LEN)
    }

    /// Check capacity before authorization or semantic processing.
    ///
    /// HOS2 requires capacity for the opcode's successful response even when
    /// the eventual status is an error; this check therefore runs first.
    pub fn ensure_response_capacity(&self, opcode: Opcode, _status: Status) -> Result<(), Error> {
        self.ensure_success_response_capacity(opcode)
    }

    /// Check the maximum response size required by an opcode.
    pub fn ensure_success_response_capacity(&self, opcode: Opcode) -> Result<(), Error> {
        if u64::from(self.response_capacity) < response_frame_len(opcode, Status::Ok) as u64 {
            return Err(Error::InsufficientCapacity);
        }
        Ok(())
    }

    fn validate_lengths(&self) -> Result<(), Error> {
        if u64::from(self.request_bytes) < HEADER_LEN as u64
            || u64::from(self.request_bytes) > MAX_FRAME as u64
        {
            return Err(Error::InvalidTransport);
        }
        // Guard arithmetic only. Canonical user pointers, access rights and
        // copy faults remain the kernel ioctl handler's responsibility.
        self.request_addr
            .checked_add(u64::from(self.request_bytes))
            .ok_or(Error::IntegerOverflow)?;
        self.response_addr
            .checked_add(u64::from(self.response_capacity))
            .ok_or(Error::IntegerOverflow)?;
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct InstallBudgetRequest {
    pub expected_revision: u64,
    pub period_ns: u64,
    pub cap_ns: u64,
    pub reserved: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct DeliveryRequest {
    pub history_boot: [u8; 16],
    pub history_space: [u8; 16],
    pub sequence: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RequestPayload {
    QueryAbi,
    ReadUsage,
    InstallBudget(InstallBudgetRequest),
    QueryDelivery(DeliveryRequest),
    RetireThrough(DeliveryRequest),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Request {
    pub opcode: Opcode,
    pub request_id: [u8; 16],
    pub target_slot: u64,
    pub target_generation: u64,
    pub payload: RequestPayload,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct QueryAbiResponse {
    pub space_id: [u8; 16],
    pub page_size: u32,
    pub max_request_payload: u32,
    pub max_response_payload: u32,
    pub supported_ops: u64,
    pub features: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ReadUsageResponse {
    pub sample_boottime_ns: u64,
    pub cumulative_cpu_ns: u64,
    pub window_start_ns: u64,
    pub window_consumed_ns: u64,
    pub active_cap_ns: u64,
    pub active_period_ns: u64,
    pub event_sequence: u64,
    pub dropped_events: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct InstallBudgetResponse {
    pub previous_revision: u64,
    pub effective_boottime_ns: u64,
    pub consumed_at_apply_ns: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u16)]
pub enum DeliveryState {
    Reserved = 0,
    Terminal = 1,
    Retired = 2,
    NotSeen = 3,
    HistoryLost = 4,
}

impl DeliveryState {
    pub const fn as_u16(self) -> u16 {
        self as u16
    }
    pub const fn from_u16(v: u16) -> Result<Self, Error> {
        match v {
            0 => Ok(Self::Reserved),
            1 => Ok(Self::Terminal),
            2 => Ok(Self::Retired),
            3 => Ok(Self::NotSeen),
            4 => Ok(Self::HistoryLost),
            _ => Err(Error::InvalidField),
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct QueryDeliveryResponse {
    pub state: DeliveryState,
    pub saved_status: Status,
    pub sequence: u64,
    pub stable_object_id: [u8; 16],
    pub saved_revision: u64,
    pub previous_revision: u64,
    pub effective_ns: u64,
    pub consumed_ns: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct RetireThroughResponse {
    pub retired_through: u64,
    pub next_sequence: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ResponsePayload {
    /// Error responses carry no payload on the wire.
    Empty,
    QueryAbi(QueryAbiResponse),
    ReadUsage(ReadUsageResponse),
    InstallBudget(InstallBudgetResponse),
    QueryDelivery(QueryDeliveryResponse),
    RetireThrough(RetireThroughResponse),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Response {
    pub opcode: Opcode,
    pub status: Status,
    pub request_id: [u8; 16],
    pub boot_id: [u8; 16],
    pub revision: u64,
    pub payload: ResponsePayload,
}

pub fn decode_request(bytes: &[u8]) -> Result<Request, Error> {
    if bytes.len() < HEADER_LEN {
        return Err(Error::Truncated);
    }
    check_magic(bytes, HOS2_MAGIC)?;
    check_version(bytes)?;
    if get_u16(bytes, 10) != 0 {
        return Err(Error::InvalidFlags);
    }
    check_common_header(bytes, true)?;
    let payload_len = checked_payload_len(bytes)?;
    let opcode = Opcode::from_u16(get_u16(bytes, 8))?;
    let request_id = copy16(bytes, 24);
    if is_zero(&request_id) {
        return Err(Error::InvalidRequestId);
    }
    let target_slot = get_u64(bytes, 40);
    let target_generation = get_u64(bytes, 48);
    let payload = &bytes[HEADER_LEN..HEADER_LEN + payload_len];
    let parsed = match opcode {
        Opcode::QueryAbi => {
            if target_slot != 0 || target_generation != 0 {
                return Err(Error::InvalidTarget);
            }
            if payload_len != 0 {
                return Err(Error::PayloadLengthMismatch);
            }
            RequestPayload::QueryAbi
        }
        Opcode::ReadUsage => {
            check_target(target_slot, target_generation)?;
            if payload_len != 0 {
                return Err(Error::PayloadLengthMismatch);
            }
            RequestPayload::ReadUsage
        }
        Opcode::InstallBudget => {
            check_target(target_slot, target_generation)?;
            if payload_len != 32 {
                return Err(Error::PayloadLengthMismatch);
            }
            validate_install_sequence_id(&request_id)?;
            let req = InstallBudgetRequest {
                expected_revision: get_u64(payload, 0),
                period_ns: get_u64(payload, 8),
                cap_ns: get_u64(payload, 16),
                reserved: get_u64(payload, 24),
            };
            validate_install_request(&req)?;
            RequestPayload::InstallBudget(req)
        }
        Opcode::QueryDelivery => {
            check_target(target_slot, target_generation)?;
            RequestPayload::QueryDelivery(parse_delivery_request(payload)?)
        }
        Opcode::RetireThrough => {
            check_target(target_slot, target_generation)?;
            RequestPayload::RetireThrough(parse_delivery_request(payload)?)
        }
    };
    Ok(Request {
        opcode,
        request_id,
        target_slot,
        target_generation,
        payload: parsed,
    })
}

/// Alias retained for callers that use parser terminology.
pub fn parse_request(bytes: &[u8]) -> Result<Request, Error> {
    decode_request(bytes)
}

pub fn encode_request(request: &Request, out: &mut [u8]) -> Result<usize, Error> {
    validate_request(request)?;
    let payload_len = request_payload_len(&request.payload);
    let frame_len = HEADER_LEN
        .checked_add(payload_len)
        .ok_or(Error::IntegerOverflow)?;
    if frame_len > MAX_FRAME {
        return Err(Error::PayloadTooLarge);
    }
    if out.len() < frame_len {
        return Err(Error::InsufficientCapacity);
    }
    out[..frame_len].fill(0);
    out[0..4].copy_from_slice(&HOS2_MAGIC);
    put_u16(out, 4, HOS2_MAJOR);
    put_u16(out, 6, HOS2_MINOR);
    put_u16(out, 8, request.opcode.as_u16());
    put_u16(out, 10, 0);
    put_u32(out, 12, HEADER_LEN as u32);
    put_u32(out, 16, payload_len as u32);
    out[24..40].copy_from_slice(&request.request_id);
    put_u64(out, 40, request.target_slot);
    put_u64(out, 48, request.target_generation);
    encode_request_payload(&request.payload, &mut out[HEADER_LEN..frame_len]);
    Ok(frame_len)
}

pub fn decode_response(bytes: &[u8]) -> Result<Response, Error> {
    if bytes.len() < HEADER_LEN {
        return Err(Error::Truncated);
    }
    check_magic(bytes, HOSR_MAGIC)?;
    check_version(bytes)?;
    check_common_header(bytes, false)?;
    let payload_len = checked_payload_len(bytes)?;
    let opcode = Opcode::from_u16(get_u16(bytes, 8))?;
    let status = Status::from_u16(get_u16(bytes, 10))?;
    let request_id = copy16(bytes, 24);
    let boot_id = copy16(bytes, 40);
    if is_zero(&request_id) {
        return Err(Error::InvalidRequestId);
    }
    if is_zero(&boot_id) {
        return Err(Error::InvalidField);
    }
    // Even a failed InstallBudget echoes its ordered sequence identity.
    // Validate standalone responses as well as correlated ones.
    if opcode == Opcode::InstallBudget {
        validate_install_sequence_id(&request_id)?;
    }
    let revision = get_u64(bytes, 56);
    if status != Status::Ok {
        if payload_len != 0 || revision != 0 {
            return Err(Error::MalformedErrorResponse);
        }
        return Ok(Response {
            opcode,
            status,
            request_id,
            boot_id,
            revision,
            payload: ResponsePayload::Empty,
        });
    }
    let expected = response_payload_len(opcode);
    if payload_len != expected {
        return Err(Error::PayloadLengthMismatch);
    }
    let payload = &bytes[HEADER_LEN..HEADER_LEN + payload_len];
    let parsed = match opcode {
        Opcode::QueryAbi => {
            if revision != 0 {
                return Err(Error::InvalidField);
            }
            ResponsePayload::QueryAbi(parse_query_abi_response(payload)?)
        }
        Opcode::ReadUsage => {
            if revision == 0 {
                return Err(Error::InvalidField);
            }
            ResponsePayload::ReadUsage(parse_read_usage_response(payload)?)
        }
        Opcode::InstallBudget => {
            if revision == 0 {
                return Err(Error::InvalidField);
            }
            let p = parse_install_response(payload)?;
            validate_install_response_revision(p.previous_revision, revision)?;
            validate_apply_times(p.effective_boottime_ns, p.consumed_at_apply_ns)?;
            ResponsePayload::InstallBudget(p)
        }
        Opcode::QueryDelivery => {
            if revision != 0 {
                return Err(Error::InvalidField);
            }
            ResponsePayload::QueryDelivery(parse_query_delivery_response(payload)?)
        }
        Opcode::RetireThrough => {
            if revision != 0 {
                return Err(Error::InvalidField);
            }
            ResponsePayload::RetireThrough(parse_retire_response(payload)?)
        }
    };
    Ok(Response {
        opcode,
        status,
        request_id,
        boot_id,
        revision,
        payload: parsed,
    })
}

/// Read the exact response frame length declared by an HOSR header.
///
/// A transport buffer may be larger than the returned frame.  Callers should
/// slice to this length before passing the bytes to `decode_response`, which
/// intentionally rejects trailing capacity as malformed input.
pub fn declared_response_len(bytes: &[u8]) -> Result<usize, Error> {
    if bytes.len() < HEADER_LEN {
        return Err(Error::Truncated);
    }
    check_magic(bytes, HOSR_MAGIC)?;
    check_version(bytes)?;
    check_common_header(bytes, false)?;
    let payload_len = get_u32(bytes, 16) as usize;
    if payload_len > MAX_PAYLOAD {
        return Err(Error::PayloadTooLarge);
    }
    let expected = HEADER_LEN
        .checked_add(payload_len)
        .ok_or(Error::IntegerOverflow)?;
    if bytes.len() < expected {
        return Err(Error::Truncated);
    }
    Ok(expected)
}

/// Decode a response from a transport buffer that may include unused capacity.
pub fn decode_response_prefix(bytes: &[u8]) -> Result<(Response, usize), Error> {
    let frame_len = declared_response_len(bytes)?;
    let response = decode_response(&bytes[..frame_len])?;
    Ok((response, frame_len))
}

/// Prefix variant of `decode_response_for` with request correlation.
pub fn decode_response_prefix_for(
    bytes: &[u8],
    request: &Request,
) -> Result<(Response, usize), Error> {
    let frame_len = declared_response_len(bytes)?;
    let response = decode_response_for(&bytes[..frame_len], request)?;
    Ok((response, frame_len))
}

/// Decode a response and verify that it belongs to a specific request.
pub fn decode_response_for(bytes: &[u8], request: &Request) -> Result<Response, Error> {
    let response = decode_response(bytes)?;
    response.validate_for(request)?;
    Ok(response)
}

/// Alias retained for callers that use parser terminology.
pub fn parse_response(bytes: &[u8]) -> Result<Response, Error> {
    decode_response(bytes)
}

pub fn encode_response(response: &Response, out: &mut [u8]) -> Result<usize, Error> {
    validate_response(response)?;
    let payload_len = if response.status == Status::Ok {
        response_payload_len(response.opcode)
    } else {
        0
    };
    let frame_len = HEADER_LEN
        .checked_add(payload_len)
        .ok_or(Error::IntegerOverflow)?;
    if out.len() < frame_len {
        return Err(Error::InsufficientCapacity);
    }
    out[..frame_len].fill(0);
    out[0..4].copy_from_slice(&HOSR_MAGIC);
    put_u16(out, 4, HOS2_MAJOR);
    put_u16(out, 6, HOS2_MINOR);
    put_u16(out, 8, response.opcode.as_u16());
    put_u16(out, 10, response.status.as_u16());
    put_u32(out, 12, HEADER_LEN as u32);
    put_u32(
        out,
        16,
        if response.status == Status::Ok {
            payload_len as u32
        } else {
            0
        },
    );
    out[24..40].copy_from_slice(&response.request_id);
    out[40..56].copy_from_slice(&response.boot_id);
    put_u64(out, 56, response.revision);
    if response.status == Status::Ok {
        encode_response_payload(&response.payload, &mut out[HEADER_LEN..frame_len]);
        Ok(frame_len)
    } else {
        Ok(HEADER_LEN)
    }
}

impl Request {
    pub fn decode(bytes: &[u8]) -> Result<Self, Error> {
        decode_request(bytes)
    }
    pub fn encode(&self, out: &mut [u8]) -> Result<usize, Error> {
        encode_request(self, out)
    }
}

impl Response {
    pub fn decode(bytes: &[u8]) -> Result<Self, Error> {
        decode_response(bytes)
    }
    pub fn encode(&self, out: &mut [u8]) -> Result<usize, Error> {
        encode_response(self, out)
    }

    /// Return whether this response is correlated to the request's opcode and ID.
    pub fn matches_request(&self, request: &Request) -> bool {
        self.opcode == request.opcode && self.request_id == request.request_id
    }

    /// Validate both the response wire semantics and request correlation.
    pub fn validate_for(&self, request: &Request) -> Result<(), Error> {
        validate_request(request)?;
        if !self.matches_request(request) {
            return Err(Error::InvalidField);
        }
        validate_response(self)?;
        if self.status != Status::Ok {
            return Ok(());
        }
        match (&request.payload, &self.payload) {
            (
                RequestPayload::InstallBudget(request_payload),
                ResponsePayload::InstallBudget(response_payload),
            ) if request_payload.expected_revision != response_payload.previous_revision => {
                Err(Error::InvalidField)
            }
            (
                RequestPayload::QueryDelivery(request_payload),
                ResponsePayload::QueryDelivery(response_payload),
            ) if request_payload.sequence != response_payload.sequence => Err(Error::InvalidField),
            (
                RequestPayload::RetireThrough(request_payload),
                ResponsePayload::RetireThrough(response_payload),
            ) if response_payload.retired_through < request_payload.sequence => {
                Err(Error::InvalidField)
            }
            _ => Ok(()),
        }
    }
}

fn check_magic(bytes: &[u8], expected: [u8; 4]) -> Result<(), Error> {
    if bytes.get(0..4) != Some(expected.as_slice()) {
        Err(Error::InvalidMagic)
    } else {
        Ok(())
    }
}

fn check_version(bytes: &[u8]) -> Result<(), Error> {
    if get_u16(bytes, 4) != HOS2_MAJOR || get_u16(bytes, 6) != HOS2_MINOR {
        Err(Error::UnknownVersion)
    } else {
        Ok(())
    }
}

fn check_common_header(bytes: &[u8], request: bool) -> Result<(), Error> {
    if get_u32(bytes, 12) != HEADER_LEN as u32 {
        return Err(Error::InvalidHeaderLength);
    }
    if get_u32(bytes, REQUEST_RESERVED_OFFSET) != 0 {
        return Err(Error::ReservedNonZero);
    }
    if request {
        if get_u64(bytes, 56) != 0 {
            return Err(Error::ReservedNonZero);
        }
    } else if get_u32(bytes, RESPONSE_RESERVED_OFFSET) != 0 {
        return Err(Error::ReservedNonZero);
    }
    Ok(())
}

fn checked_payload_len(bytes: &[u8]) -> Result<usize, Error> {
    let payload_len = get_u32(bytes, 16) as usize;
    if payload_len > MAX_PAYLOAD {
        return Err(Error::PayloadTooLarge);
    }
    let expected = HEADER_LEN
        .checked_add(payload_len)
        .ok_or(Error::IntegerOverflow)?;
    if bytes.len() < expected {
        return Err(Error::Truncated);
    }
    if bytes.len() > expected {
        return Err(Error::TrailingBytes);
    }
    Ok(payload_len)
}

fn check_target(slot: u64, generation: u64) -> Result<(), Error> {
    if slot == 0 {
        return Err(Error::InvalidTarget);
    }
    if generation == 0 {
        return Err(Error::InvalidGeneration);
    }
    Ok(())
}

/// Construct the canonical InstallBudget request_id from a CapSpace sequence.
///
/// This is a wire-format helper only. Sequence allocation, reservation and
/// replay detection remain the responsibility of the A03/A05 control layer.
pub fn install_budget_request_id(sequence: u64) -> Result<[u8; 16], Error> {
    if sequence == 0 || sequence == u64::MAX {
        return Err(Error::InvalidSequence);
    }
    let mut id = [0u8; 16];
    id[..8].copy_from_slice(&sequence.to_le_bytes());
    Ok(id)
}

/// Decode an InstallBudget request_id without accepting nonzero high bytes.
pub fn install_budget_sequence(id: &[u8; 16]) -> Result<u64, Error> {
    if is_zero(id) {
        return Err(Error::InvalidRequestId);
    }
    validate_install_sequence_id(id)?;
    Ok(get_u64(id, 0))
}

/// The low half is a little-endian sequence; the high half is zero.
fn validate_install_sequence_id(id: &[u8; 16]) -> Result<(), Error> {
    if !all_zero(&id[8..]) {
        return Err(Error::SequenceHighBytesNonZero);
    }
    let sequence = get_u64(id, 0);
    if sequence == 0 || sequence == u64::MAX {
        return Err(Error::InvalidSequence);
    }
    Ok(())
}

fn validate_request(request: &Request) -> Result<(), Error> {
    if is_zero(&request.request_id) {
        return Err(Error::InvalidRequestId);
    }
    match request.opcode {
        Opcode::QueryAbi => {
            if request.target_slot != 0 || request.target_generation != 0 {
                return Err(Error::InvalidTarget);
            }
            if !matches!(request.payload, RequestPayload::QueryAbi) {
                return Err(Error::InvalidField);
            }
        }
        Opcode::ReadUsage => {
            check_target(request.target_slot, request.target_generation)?;
            if !matches!(request.payload, RequestPayload::ReadUsage) {
                return Err(Error::InvalidField);
            }
        }
        Opcode::InstallBudget => {
            check_target(request.target_slot, request.target_generation)?;
            validate_install_sequence_id(&request.request_id)?;
            match request.payload {
                RequestPayload::InstallBudget(v) => validate_install_request(&v)?,
                _ => return Err(Error::InvalidField),
            }
        }
        Opcode::QueryDelivery => {
            check_target(request.target_slot, request.target_generation)?;
            match request.payload {
                RequestPayload::QueryDelivery(v) => validate_delivery_request(&v)?,
                _ => return Err(Error::InvalidField),
            }
        }
        Opcode::RetireThrough => {
            check_target(request.target_slot, request.target_generation)?;
            match request.payload {
                RequestPayload::RetireThrough(v) => validate_delivery_request(&v)?,
                _ => return Err(Error::InvalidField),
            }
        }
    }
    Ok(())
}

fn request_payload_len(payload: &RequestPayload) -> usize {
    match payload {
        RequestPayload::QueryAbi | RequestPayload::ReadUsage => 0,
        RequestPayload::InstallBudget(_) => 32,
        RequestPayload::QueryDelivery(_) | RequestPayload::RetireThrough(_) => 40,
    }
}

fn encode_request_payload(payload: &RequestPayload, out: &mut [u8]) {
    match payload {
        RequestPayload::QueryAbi | RequestPayload::ReadUsage => {}
        RequestPayload::InstallBudget(v) => {
            put_u64(out, 0, v.expected_revision);
            put_u64(out, 8, v.period_ns);
            put_u64(out, 16, v.cap_ns);
            put_u64(out, 24, v.reserved);
        }
        RequestPayload::QueryDelivery(v) | RequestPayload::RetireThrough(v) => {
            out[0..16].copy_from_slice(&v.history_boot);
            out[16..32].copy_from_slice(&v.history_space);
            put_u64(out, 32, v.sequence);
        }
    }
}

fn validate_install_request(v: &InstallBudgetRequest) -> Result<(), Error> {
    if v.expected_revision == 0 || v.expected_revision == u64::MAX {
        return Err(Error::InvalidField);
    }
    if v.period_ns != CPU_PERIOD_NS || v.cap_ns > v.period_ns || v.reserved != 0 {
        return Err(Error::InvalidField);
    }
    Ok(())
}

fn parse_delivery_request(payload: &[u8]) -> Result<DeliveryRequest, Error> {
    if payload.len() != 40 {
        return Err(Error::PayloadLengthMismatch);
    }
    let out = DeliveryRequest {
        history_boot: copy16(payload, 0),
        history_space: copy16(payload, 16),
        sequence: get_u64(payload, 32),
    };
    validate_delivery_request(&out)?;
    Ok(out)
}

fn validate_delivery_request(v: &DeliveryRequest) -> Result<(), Error> {
    if is_zero(&v.history_boot) || is_zero(&v.history_space) || v.sequence == 0 {
        return Err(Error::InvalidField);
    }
    Ok(())
}

fn parse_query_abi_response(p: &[u8]) -> Result<QueryAbiResponse, Error> {
    if p.len() != 48 {
        return Err(Error::PayloadLengthMismatch);
    }
    let out = QueryAbiResponse {
        space_id: copy16(p, 0),
        page_size: get_u32(p, 16),
        max_request_payload: get_u32(p, 20),
        max_response_payload: get_u32(p, 24),
        supported_ops: get_u64(p, 32),
        features: get_u64(p, 40),
    };
    if is_zero(&out.space_id)
        || out.page_size == 0
        || (out.page_size & (out.page_size - 1)) != 0
        || get_u32(p, 28) != 0
        || out.features != 0
    {
        return Err(Error::InvalidField);
    }
    if out.max_request_payload as usize > MAX_PAYLOAD
        || out.max_response_payload as usize > MAX_PAYLOAD
    {
        return Err(Error::PayloadTooLarge);
    }
    if out.supported_ops & !0x3e != 0 || out.supported_ops & 0x02 == 0 {
        return Err(Error::InvalidField);
    }
    // InstallBudget (opcode 3, bit 3) requires all observation/history
    // operations (bits 2, 4 and 5) to be advertised as well.
    if out.supported_ops & 0x08 != 0 && out.supported_ops & 0x34 != 0x34 {
        return Err(Error::InvalidField);
    }
    if out.supported_ops & 0x20 != 0 && out.supported_ops & 0x10 == 0 {
        return Err(Error::InvalidField);
    }
    let mut min_request = 0u32;
    let mut min_response = 0u32;
    if out.supported_ops & 0x02 != 0 {
        min_response = 48;
    }
    if out.supported_ops & 0x04 != 0 {
        min_response = max_u32(min_response, 64);
    }
    if out.supported_ops & 0x08 != 0 {
        min_request = max_u32(min_request, 32);
        min_response = max_u32(min_response, 24);
    }
    if out.supported_ops & 0x10 != 0 {
        min_request = max_u32(min_request, 40);
        min_response = max_u32(min_response, 64);
    }
    if out.supported_ops & 0x20 != 0 {
        min_request = max_u32(min_request, 40);
        min_response = max_u32(min_response, 16);
    }
    if out.max_request_payload < min_request || out.max_response_payload < min_response {
        return Err(Error::InvalidField);
    }
    Ok(out)
}

fn parse_read_usage_response(p: &[u8]) -> Result<ReadUsageResponse, Error> {
    if p.len() != 64 {
        return Err(Error::PayloadLengthMismatch);
    }
    let out = ReadUsageResponse {
        sample_boottime_ns: get_u64(p, 0),
        cumulative_cpu_ns: get_u64(p, 8),
        window_start_ns: get_u64(p, 16),
        window_consumed_ns: get_u64(p, 24),
        active_cap_ns: get_u64(p, 32),
        active_period_ns: get_u64(p, 40),
        event_sequence: get_u64(p, 48),
        dropped_events: get_u64(p, 56),
    };
    let elapsed = out
        .sample_boottime_ns
        .checked_sub(out.window_start_ns)
        .ok_or(Error::IntegerOverflow)?;
    let expected_start = (out.sample_boottime_ns / CPU_PERIOD_NS)
        .checked_mul(CPU_PERIOD_NS)
        .ok_or(Error::IntegerOverflow)?;
    if out.active_period_ns != CPU_PERIOD_NS
        || out.window_start_ns != expected_start
        || out.window_consumed_ns > elapsed
        || out.cumulative_cpu_ns < out.window_consumed_ns
        || out.active_cap_ns > out.active_period_ns
        || out.dropped_events > out.event_sequence
    {
        return Err(Error::InvalidField);
    }
    Ok(out)
}

fn parse_install_response(p: &[u8]) -> Result<InstallBudgetResponse, Error> {
    if p.len() != 24 {
        return Err(Error::PayloadLengthMismatch);
    }
    Ok(InstallBudgetResponse {
        previous_revision: get_u64(p, 0),
        effective_boottime_ns: get_u64(p, 8),
        consumed_at_apply_ns: get_u64(p, 16),
    })
}

fn parse_query_delivery_response(p: &[u8]) -> Result<QueryDeliveryResponse, Error> {
    if p.len() != 64 {
        return Err(Error::PayloadLengthMismatch);
    }
    if get_u32(p, 4) != 0 {
        return Err(Error::ReservedNonZero);
    }
    let state = DeliveryState::from_u16(get_u16(p, 0))?;
    let saved_status = Status::from_u16(get_u16(p, 2))?;
    let out = QueryDeliveryResponse {
        state,
        saved_status,
        sequence: get_u64(p, 8),
        stable_object_id: copy16(p, 16),
        saved_revision: get_u64(p, 32),
        previous_revision: get_u64(p, 40),
        effective_ns: get_u64(p, 48),
        consumed_ns: get_u64(p, 56),
    };
    validate_query_delivery_response(&out)?;
    Ok(out)
}

fn validate_query_delivery_response(v: &QueryDeliveryResponse) -> Result<(), Error> {
    if v.sequence == 0 {
        return Err(Error::InvalidSequence);
    }
    match v.state {
        DeliveryState::Terminal => {
            if v.saved_status == Status::Ok {
                if is_zero(&v.stable_object_id)
                    || v.previous_revision == 0
                    || v.previous_revision == u64::MAX
                    || v.saved_revision != v.previous_revision + 1
                {
                    return Err(Error::InvalidField);
                }
                validate_apply_times(v.effective_ns, v.consumed_ns)?;
            } else if !is_zero(&v.stable_object_id)
                || v.saved_revision != 0
                || v.previous_revision != 0
                || v.effective_ns != 0
                || v.consumed_ns != 0
            {
                return Err(Error::MalformedErrorResponse);
            }
        }
        DeliveryState::Reserved
        | DeliveryState::Retired
        | DeliveryState::NotSeen
        | DeliveryState::HistoryLost => {
            if v.saved_status != Status::Ok
                || !is_zero(&v.stable_object_id)
                || v.saved_revision != 0
                || v.previous_revision != 0
                || v.effective_ns != 0
                || v.consumed_ns != 0
            {
                return Err(Error::InvalidField);
            }
        }
    }
    Ok(())
}

fn parse_retire_response(p: &[u8]) -> Result<RetireThroughResponse, Error> {
    if p.len() != 16 {
        return Err(Error::PayloadLengthMismatch);
    }
    let out = RetireThroughResponse {
        retired_through: get_u64(p, 0),
        next_sequence: get_u64(p, 8),
    };
    if out.next_sequence == 0 || out.next_sequence <= out.retired_through {
        return Err(Error::InvalidField);
    }
    Ok(out)
}

fn validate_response(response: &Response) -> Result<(), Error> {
    if is_zero(&response.request_id) {
        return Err(Error::InvalidRequestId);
    }
    if is_zero(&response.boot_id) {
        return Err(Error::InvalidField);
    }
    if response.opcode == Opcode::InstallBudget {
        validate_install_sequence_id(&response.request_id)?;
    }
    if response.status != Status::Ok {
        if response.revision != 0 || !matches!(response.payload, ResponsePayload::Empty) {
            return Err(Error::MalformedErrorResponse);
        }
        return Ok(());
    }
    match (&response.opcode, &response.payload) {
        (Opcode::QueryAbi, ResponsePayload::QueryAbi(v)) => {
            if response.revision != 0 {
                return Err(Error::InvalidField);
            }
            validate_query_abi(v)
        }
        (Opcode::ReadUsage, ResponsePayload::ReadUsage(v)) => {
            if response.revision == 0 {
                return Err(Error::InvalidField);
            }
            validate_read_usage(v)
        }
        (Opcode::InstallBudget, ResponsePayload::InstallBudget(v)) => {
            validate_install_response_revision(v.previous_revision, response.revision)?;
            validate_apply_times(v.effective_boottime_ns, v.consumed_at_apply_ns)
        }
        (Opcode::QueryDelivery, ResponsePayload::QueryDelivery(v)) => {
            if response.revision != 0 {
                return Err(Error::InvalidField);
            }
            validate_query_delivery_response(v)
        }
        (Opcode::RetireThrough, ResponsePayload::RetireThrough(v)) => {
            if response.revision != 0 {
                return Err(Error::InvalidField);
            }
            if v.next_sequence == 0 || v.next_sequence <= v.retired_through {
                return Err(Error::InvalidField);
            }
            Ok(())
        }
        (_, ResponsePayload::Empty) => Err(Error::InvalidField),
        _ => Err(Error::InvalidField),
    }
}

fn validate_query_abi(v: &QueryAbiResponse) -> Result<(), Error> {
    let mut b = [0u8; 48];
    b[0..16].copy_from_slice(&v.space_id);
    put_u32(&mut b, 16, v.page_size);
    put_u32(&mut b, 20, v.max_request_payload);
    put_u32(&mut b, 24, v.max_response_payload);
    put_u64(&mut b, 32, v.supported_ops);
    put_u64(&mut b, 40, v.features);
    put_u32(&mut b, 28, 0);
    parse_query_abi_response(&b).map(|_| ())
}

fn validate_read_usage(v: &ReadUsageResponse) -> Result<(), Error> {
    let elapsed = v
        .sample_boottime_ns
        .checked_sub(v.window_start_ns)
        .ok_or(Error::IntegerOverflow)?;
    let expected_start = (v.sample_boottime_ns / CPU_PERIOD_NS)
        .checked_mul(CPU_PERIOD_NS)
        .ok_or(Error::IntegerOverflow)?;
    if v.active_period_ns != CPU_PERIOD_NS
        || v.window_start_ns != expected_start
        || v.window_consumed_ns > elapsed
        || v.cumulative_cpu_ns < v.window_consumed_ns
        || v.active_cap_ns > v.active_period_ns
        || v.dropped_events > v.event_sequence
    {
        return Err(Error::InvalidField);
    }
    Ok(())
}

fn encode_response_payload(payload: &ResponsePayload, out: &mut [u8]) {
    match payload {
        ResponsePayload::QueryAbi(v) => {
            out[0..16].copy_from_slice(&v.space_id);
            put_u32(out, 16, v.page_size);
            put_u32(out, 20, v.max_request_payload);
            put_u32(out, 24, v.max_response_payload);
            put_u32(out, 28, 0);
            put_u64(out, 32, v.supported_ops);
            put_u64(out, 40, v.features);
        }
        ResponsePayload::ReadUsage(v) => {
            put_u64(out, 0, v.sample_boottime_ns);
            put_u64(out, 8, v.cumulative_cpu_ns);
            put_u64(out, 16, v.window_start_ns);
            put_u64(out, 24, v.window_consumed_ns);
            put_u64(out, 32, v.active_cap_ns);
            put_u64(out, 40, v.active_period_ns);
            put_u64(out, 48, v.event_sequence);
            put_u64(out, 56, v.dropped_events);
        }
        ResponsePayload::InstallBudget(v) => {
            put_u64(out, 0, v.previous_revision);
            put_u64(out, 8, v.effective_boottime_ns);
            put_u64(out, 16, v.consumed_at_apply_ns);
        }
        ResponsePayload::QueryDelivery(v) => {
            put_u16(out, 0, v.state.as_u16());
            put_u16(out, 2, v.saved_status.as_u16());
            put_u32(out, 4, 0);
            put_u64(out, 8, v.sequence);
            out[16..32].copy_from_slice(&v.stable_object_id);
            put_u64(out, 32, v.saved_revision);
            put_u64(out, 40, v.previous_revision);
            put_u64(out, 48, v.effective_ns);
            put_u64(out, 56, v.consumed_ns);
        }
        ResponsePayload::RetireThrough(v) => {
            put_u64(out, 0, v.retired_through);
            put_u64(out, 8, v.next_sequence);
        }
        ResponsePayload::Empty => {}
    }
}

#[inline]
fn get_u16(b: &[u8], o: usize) -> u16 {
    u16::from_le_bytes([b[o], b[o + 1]])
}
#[inline]
fn get_u32(b: &[u8], o: usize) -> u32 {
    u32::from_le_bytes([b[o], b[o + 1], b[o + 2], b[o + 3]])
}
#[inline]
fn get_u64(b: &[u8], o: usize) -> u64 {
    u64::from_le_bytes([
        b[o],
        b[o + 1],
        b[o + 2],
        b[o + 3],
        b[o + 4],
        b[o + 5],
        b[o + 6],
        b[o + 7],
    ])
}
#[inline]
fn put_u16(b: &mut [u8], o: usize, v: u16) {
    b[o..o + 2].copy_from_slice(&v.to_le_bytes());
}
#[inline]
fn put_u32(b: &mut [u8], o: usize, v: u32) {
    b[o..o + 4].copy_from_slice(&v.to_le_bytes());
}
#[inline]
fn put_u64(b: &mut [u8], o: usize, v: u64) {
    b[o..o + 8].copy_from_slice(&v.to_le_bytes());
}
#[inline]
fn copy16(b: &[u8], o: usize) -> [u8; 16] {
    let mut x = [0u8; 16];
    x.copy_from_slice(&b[o..o + 16]);
    x
}
#[inline]
fn is_zero(v: &[u8]) -> bool {
    all_zero(v)
}
#[inline]
fn all_zero(v: &[u8]) -> bool {
    v.iter().all(|x| *x == 0)
}
#[inline]
fn max_u32(a: u32, b: u32) -> u32 {
    if a > b {
        a
    } else {
        b
    }
}

/// A prior revision must exist, must be incrementable, and must match HOSR.
fn validate_install_response_revision(previous: u64, reported: u64) -> Result<(), Error> {
    if previous == 0 || reported == 0 {
        return Err(Error::InvalidField);
    }
    let expected = previous.checked_add(1).ok_or(Error::IntegerOverflow)?;
    if reported != expected {
        return Err(Error::InvalidField);
    }
    Ok(())
}

fn validate_apply_times(effective_ns: u64, consumed_ns: u64) -> Result<(), Error> {
    let window_start = (effective_ns / CPU_PERIOD_NS)
        .checked_mul(CPU_PERIOD_NS)
        .ok_or(Error::IntegerOverflow)?;
    let elapsed = effective_ns
        .checked_sub(window_start)
        .ok_or(Error::IntegerOverflow)?;
    if consumed_ns > elapsed {
        return Err(Error::InvalidField);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn id(x: u8) -> [u8; 16] {
        [x; 16]
    }

    #[test]
    fn transport_explicit_little_endian() {
        let t = Transport::new(1, 2, 64, 128);
        let mut b = [0u8; 32];
        assert_eq!(t.encode(&mut b), Ok(32));
        assert_eq!(Transport::decode(&b), Ok(t));
        assert_eq!(&b[0..8], &[1, 0, 0, 0, 0, 0, 0, 0]);
    }

    #[test]
    fn request_header_and_payload_round_trip() {
        let r = Request {
            opcode: Opcode::InstallBudget,
            request_id: [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            target_slot: 1,
            target_generation: 2,
            payload: RequestPayload::InstallBudget(InstallBudgetRequest {
                expected_revision: 10,
                period_ns: CPU_PERIOD_NS,
                cap_ns: 40_000_000,
                reserved: 0,
            }),
        };
        let mut b = [0u8; 96];
        let n = r.encode(&mut b).unwrap();
        assert_eq!(n, 96);
        assert_eq!(Request::decode(&b[..n]), Ok(r));
    }

    #[test]
    fn malformed_usage_is_rejected() {
        let p = ReadUsageResponse {
            sample_boottime_ns: 10,
            cumulative_cpu_ns: 1,
            window_start_ns: 10,
            window_consumed_ns: 1,
            active_cap_ns: 1,
            active_period_ns: 2,
            event_sequence: 1,
            dropped_events: 0,
        };
        let r = Response {
            opcode: Opcode::ReadUsage,
            status: Status::Ok,
            request_id: id(1),
            boot_id: id(2),
            revision: 1,
            payload: ResponsePayload::ReadUsage(p),
        };
        let mut b = [0u8; 128];
        assert!(r.encode(&mut b).is_err());
    }
}
