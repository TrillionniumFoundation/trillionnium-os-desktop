#![no_std]
//! Experimental HOS2 2.0 wire codec. Explicit little-endian bytes only.
//! No I/O, permissions, delivery state, OS clock, or kernel implementation.

use core::convert::TryInto;

pub const HEADER_LEN: usize = 64;
pub const TRANSPORT_LEN: usize = 32;
pub const MAX_PAYLOAD: usize = 65_536;
pub const MAX_FRAME: usize = HEADER_LEN + MAX_PAYLOAD;
pub const PERIOD_NS: u64 = 100_000_000;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Error {
    Length,
    Magic,
    Version,
    Opcode,
    Reserved,
    Identifier,
    Payload,
    Status,
    Semantic,
    Overflow,
    Capacity,
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
impl TryFrom<u16> for Opcode {
    type Error = Error;
    fn try_from(value: u16) -> Result<Self, Error> {
        match value {
            1 => Ok(Self::QueryAbi),
            2 => Ok(Self::ReadUsage),
            3 => Ok(Self::InstallBudget),
            4 => Ok(Self::QueryDelivery),
            5 => Ok(Self::RetireThrough),
            _ => Err(Error::Opcode),
        }
    }
}
impl Opcode {
    pub const fn request_len(self) -> usize {
        match self {
            Self::QueryAbi | Self::ReadUsage => 0,
            Self::InstallBudget => 32,
            Self::QueryDelivery | Self::RetireThrough => 40,
        }
    }
    pub const fn response_len(self) -> usize {
        match self {
            Self::QueryAbi => 48,
            Self::ReadUsage | Self::QueryDelivery => 64,
            Self::InstallBudget => 24,
            Self::RetireThrough => 16,
        }
    }
}

fn le16(a: &[u8], i: usize) -> u16 {
    u16::from_le_bytes(a[i..i + 2].try_into().unwrap())
}
fn le32(a: &[u8], i: usize) -> u32 {
    u32::from_le_bytes(a[i..i + 4].try_into().unwrap())
}
fn le64(a: &[u8], i: usize) -> u64 {
    u64::from_le_bytes(a[i..i + 8].try_into().unwrap())
}
fn id(a: &[u8], i: usize) -> [u8; 16] {
    a[i..i + 16].try_into().unwrap()
}
fn nonzero(a: &[u8]) -> bool {
    a.iter().any(|&v| v != 0)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Transport {
    pub request_addr: u64,
    pub response_addr: u64,
    pub request_bytes: u32,
    pub response_capacity: u32,
}
pub fn decode_transport(a: &[u8]) -> Result<Transport, Error> {
    if a.len() != TRANSPORT_LEN {
        return Err(Error::Length);
    }
    if le64(a, 24) != 0 {
        return Err(Error::Reserved);
    }
    let r = Transport {
        request_addr: le64(a, 0),
        response_addr: le64(a, 8),
        request_bytes: le32(a, 16),
        response_capacity: le32(a, 20),
    };
    if r.request_bytes as usize > MAX_FRAME
        || r.request_addr.checked_add(r.request_bytes as u64).is_none()
        || r.response_addr
            .checked_add(r.response_capacity as u64)
            .is_none()
    {
        return Err(Error::Overflow);
    }
    Ok(r)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Request<'a> {
    pub opcode: Opcode,
    pub request_id: [u8; 16],
    pub slot: u64,
    pub generation: u64,
    pub payload: &'a [u8],
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Response<'a> {
    pub opcode: Opcode,
    pub status: u16,
    pub request_id: [u8; 16],
    pub boot_id: [u8; 16],
    pub revision: u64,
    pub payload: &'a [u8],
}
impl Response<'_> {
    pub fn echoes(&self, request: &Request<'_>) -> bool {
        self.opcode == request.opcode && self.request_id == request.request_id
    }
}

fn header(a: &[u8], magic: &[u8; 4]) -> Result<(Opcode, u16), Error> {
    if a.len() < HEADER_LEN || a.len() > MAX_FRAME {
        return Err(Error::Length);
    }
    if &a[..4] != magic {
        return Err(Error::Magic);
    }
    if (le16(a, 4), le16(a, 6)) != (2, 0) {
        return Err(Error::Version);
    }
    let opcode = Opcode::try_from(le16(a, 8))?;
    if le32(a, 12) != HEADER_LEN as u32
        || le32(a, 20) != 0
        || le32(a, 16) as usize != a.len() - HEADER_LEN
    {
        return Err(Error::Length);
    }
    if !nonzero(&a[24..40]) {
        return Err(Error::Identifier);
    }
    if opcode == Opcode::InstallBudget
        && (!a[32..40].iter().all(|&b| b == 0) || le64(a, 24) == 0 || le64(a, 24) == u64::MAX)
    {
        return Err(Error::Identifier);
    }
    Ok((opcode, le16(a, 10)))
}

pub fn decode_request(a: &[u8]) -> Result<Request<'_>, Error> {
    let (op, flags) = header(a, b"HOS2")?;
    if flags != 0 || le64(a, 56) != 0 {
        return Err(Error::Reserved);
    }
    let slot = le64(a, 40);
    let generation = le64(a, 48);
    if (op == Opcode::QueryAbi && (slot != 0 || generation != 0))
        || (op != Opcode::QueryAbi && (slot == 0 || generation == 0))
    {
        return Err(Error::Identifier);
    }
    let payload = &a[HEADER_LEN..];
    if payload.len() != op.request_len() {
        return Err(Error::Payload);
    }
    match op {
        Opcode::InstallBudget => {
            let revision = le64(payload, 0);
            if revision == 0
                || revision == u64::MAX
                || le64(payload, 8) != PERIOD_NS
                || le64(payload, 16) > PERIOD_NS
                || le64(payload, 24) != 0
            {
                return Err(Error::Semantic);
            }
        }
        Opcode::QueryDelivery | Opcode::RetireThrough
            if !nonzero(&payload[..16]) || !nonzero(&payload[16..32]) || le64(payload, 32) == 0 =>
        {
            return Err(Error::Identifier);
        }
        _ => {}
    }
    Ok(Request {
        opcode: op,
        request_id: id(a, 24),
        slot,
        generation,
        payload,
    })
}

pub fn decode_response(a: &[u8]) -> Result<Response<'_>, Error> {
    let (op, status) = header(a, b"HOSR")?;
    if status > 11 {
        return Err(Error::Status);
    }
    let boot_id = id(a, 40);
    if !nonzero(&boot_id) {
        return Err(Error::Identifier);
    }
    let revision = le64(a, 56);
    let payload = &a[HEADER_LEN..];
    if status != 0 {
        if !payload.is_empty() || revision != 0 {
            return Err(Error::Payload);
        }
    } else {
        if payload.len() != op.response_len() {
            return Err(Error::Payload);
        }
        if (op == Opcode::ReadUsage || op == Opcode::InstallBudget) != (revision != 0) {
            return Err(Error::Semantic);
        }
        match op {
            Opcode::QueryAbi => {
                let page = le32(payload, 16);
                let max_req = le32(payload, 20);
                let max_resp = le32(payload, 24);
                let operations = le64(payload, 32);
                if !nonzero(&payload[..16])
                    || !page.is_power_of_two()
                    || le32(payload, 28) != 0
                    || le64(payload, 40) != 0
                    || operations & !62 != 0
                    || operations & 2 == 0
                    || (operations & 8 != 0 && operations & (4 | 16 | 32) != (4 | 16 | 32))
                    || (operations & 32 != 0 && operations & 16 == 0)
                    || max_req < 40 && (operations & (8 | 16 | 32) != 0)
                    || max_req as usize > MAX_PAYLOAD
                    || max_resp as usize > MAX_PAYLOAD
                    || max_resp < 48
                    || (operations & (4 | 16) != 0 && max_resp < 64)
                {
                    return Err(Error::Semantic);
                }
            }
            Opcode::ReadUsage => {
                let sample = le64(payload, 0);
                let used = le64(payload, 24);
                if le64(payload, 40) != PERIOD_NS
                    || le64(payload, 16) != sample / PERIOD_NS * PERIOD_NS
                    || used > sample % PERIOD_NS
                    || used > le64(payload, 8)
                    || le64(payload, 32) > PERIOD_NS
                    || le64(payload, 56) > le64(payload, 48)
                {
                    return Err(Error::Semantic);
                }
            }
            Opcode::InstallBudget => {
                let previous = le64(payload, 0);
                let effective = le64(payload, 8);
                if previous == 0
                    || previous == u64::MAX
                    || previous + 1 != revision
                    || le64(payload, 16) > effective % PERIOD_NS
                {
                    return Err(Error::Semantic);
                }
            }
            Opcode::QueryDelivery => {
                let state = le16(payload, 0);
                let saved = le16(payload, 2);
                let seq = le64(payload, 8);
                if state > 4 || saved > 11 || le32(payload, 4) != 0 || seq == 0 {
                    return Err(Error::Semantic);
                }
                let object = &payload[16..32];
                let sr = le64(payload, 32);
                let prev = le64(payload, 40);
                let eff = le64(payload, 48);
                let used = le64(payload, 56);
                if state != 1 || saved != 0 {
                    if (state != 1 && saved != 0)
                        || nonzero(object)
                        || sr != 0
                        || prev != 0
                        || eff != 0
                        || used != 0
                    {
                        return Err(Error::Semantic);
                    }
                } else if !nonzero(object)
                    || prev == 0
                    || prev == u64::MAX
                    || sr != prev + 1
                    || used > eff % PERIOD_NS
                {
                    return Err(Error::Semantic);
                }
            }
            Opcode::RetireThrough => {
                if le64(payload, 8) <= le64(payload, 0) {
                    return Err(Error::Semantic);
                }
            }
        }
    }
    Ok(Response {
        opcode: op,
        status,
        request_id: id(a, 24),
        boot_id,
        revision,
        payload,
    })
}

pub fn require_success_capacity(opcode: Opcode, capacity: usize) -> Result<(), Error> {
    if capacity < HEADER_LEN + opcode.response_len() {
        Err(Error::Capacity)
    } else {
        Ok(())
    }
}

pub fn encode_request(
    op: Opcode,
    request_id: [u8; 16],
    slot: u64,
    generation: u64,
    payload: &[u8],
    out: &mut [u8],
) -> Result<usize, Error> {
    let len = HEADER_LEN
        .checked_add(payload.len())
        .ok_or(Error::Overflow)?;
    if len > MAX_FRAME || out.len() < len {
        return Err(Error::Capacity);
    }
    out[..len].fill(0);
    out[..4].copy_from_slice(b"HOS2");
    out[4..6].copy_from_slice(&2u16.to_le_bytes());
    out[8..10].copy_from_slice(&(op as u16).to_le_bytes());
    out[12..16].copy_from_slice(&(HEADER_LEN as u32).to_le_bytes());
    out[16..20].copy_from_slice(&(payload.len() as u32).to_le_bytes());
    out[24..40].copy_from_slice(&request_id);
    out[40..48].copy_from_slice(&slot.to_le_bytes());
    out[48..56].copy_from_slice(&generation.to_le_bytes());
    out[64..len].copy_from_slice(payload);
    decode_request(&out[..len])?;
    Ok(len)
}

pub fn encode_response(
    op: Opcode,
    status: u16,
    request_id: [u8; 16],
    boot_id: [u8; 16],
    revision: u64,
    payload: &[u8],
    out: &mut [u8],
) -> Result<usize, Error> {
    let len = HEADER_LEN
        .checked_add(payload.len())
        .ok_or(Error::Overflow)?;
    if len > MAX_FRAME || out.len() < len {
        return Err(Error::Capacity);
    }
    out[..len].fill(0);
    out[..4].copy_from_slice(b"HOSR");
    out[4..6].copy_from_slice(&2u16.to_le_bytes());
    out[8..10].copy_from_slice(&(op as u16).to_le_bytes());
    out[10..12].copy_from_slice(&status.to_le_bytes());
    out[12..16].copy_from_slice(&(HEADER_LEN as u32).to_le_bytes());
    out[16..20].copy_from_slice(&(payload.len() as u32).to_le_bytes());
    out[24..40].copy_from_slice(&request_id);
    out[40..56].copy_from_slice(&boot_id);
    out[56..64].copy_from_slice(&revision.to_le_bytes());
    out[64..len].copy_from_slice(payload);
    decode_response(&out[..len])?;
    Ok(len)
}

#[cfg(test)]
mod tests {
    extern crate std;
    use super::*;
    use std::{format, vec::Vec};

    fn golden(name: &str) -> Vec<u8> {
        // Independent Python struct fixture, not a codec round-trip.
        let data = include_str!("../../../tests/golden/hos2.json");
        let marker = format!("\"name\": \"{name}\"");
        let found = data.find(&marker).expect("golden name");
        let next = &data[found + marker.len()..];
        let prefix = "\"hex\": \"";
        let start = next.find(prefix).expect("golden hex") + prefix.len();
        let hex = next[start..].split('"').next().unwrap();
        hex.as_bytes()
            .chunks_exact(2)
            .map(|pair| u8::from_str_radix(core::str::from_utf8(pair).unwrap(), 16).unwrap())
            .collect()
    }

    #[test]
    fn twelve_independent_golden_frames() {
        for name in [
            "query_abi",
            "read_usage",
            "install_budget",
            "query_delivery_with_new_view",
            "retire_through",
        ] {
            let data = golden(name);
            let req = decode_request(&data).unwrap();
            let mut result = [0u8; 112];
            let n = encode_request(
                req.opcode,
                req.request_id,
                req.slot,
                req.generation,
                req.payload,
                &mut result,
            )
            .unwrap();
            assert_eq!(&result[..n], data.as_slice(), "{name}");
        }
        for name in [
            "query_abi_ok",
            "read_usage_lowered_cap",
            "install_budget_ok",
            "query_delivery_terminal",
            "query_delivery_retired",
            "retire_through_ok",
            "install_cas_rejection",
        ] {
            let data = golden(name);
            let resp = decode_response(&data).unwrap();
            let mut result = [0u8; 128];
            let n = encode_response(
                resp.opcode,
                resp.status,
                resp.request_id,
                resp.boot_id,
                resp.revision,
                resp.payload,
                &mut result,
            )
            .unwrap();
            assert_eq!(&result[..n], data.as_slice(), "{name}");
        }
    }

    #[test]
    fn cap_and_revision_change_canonical_request() {
        let original = golden("install_budget");
        let parsed = decode_request(&original).unwrap();
        for (offset, replacement) in [(64, 9u64), (80, 39_000_000)] {
            let mut changed = original.clone();
            changed[offset..offset + 8].copy_from_slice(&replacement.to_le_bytes());
            assert_eq!(&changed[24..56], &original[24..56]);
            let mutant = decode_request(&changed).unwrap();
            assert_ne!(parsed, mutant, "same D must not suppress changed intent");
            assert_ne!(original, changed);
        }
    }

    #[test]
    fn bad_header_and_response_are_rejected() {
        let original = golden("install_budget");
        for offset in [0, 6, 10, 12, 20, 32, 56] {
            let mut changed = original.clone();
            changed[offset] ^= 1;
            assert!(decode_request(&changed).is_err(), "offset={offset}");
        }
        assert_eq!(decode_request(&original[..95]), Err(Error::Length));
        let mut altered = original.clone();
        altered.push(0);
        assert_eq!(decode_request(&altered), Err(Error::Length));
        let mut error = golden("install_cas_rejection");
        error[10] = 12;
        assert_eq!(decode_response(&error), Err(Error::Status));
        error[10] = 5;
        error[56] = 1;
        assert_eq!(decode_response(&error), Err(Error::Payload));
    }

    #[test]
    fn time_invariants_detect_old_goldens() {
        let mut usage = golden("read_usage_lowered_cap");
        usage[88..96].copy_from_slice(&35_000_000u64.to_le_bytes());
        assert_eq!(decode_response(&usage), Err(Error::Semantic));
        let mut install = golden("install_budget_ok");
        install[80..88].copy_from_slice(&33_000_000u64.to_le_bytes());
        assert_eq!(decode_response(&install), Err(Error::Semantic));
        let mut history = golden("query_delivery_terminal");
        history[120..128].copy_from_slice(&33_000_000u64.to_le_bytes());
        assert_eq!(decode_response(&history), Err(Error::Semantic));
    }

    #[test]
    fn transport_overflow_and_capacity() {
        let mut desc = [0u8; 32];
        desc[..8].copy_from_slice(&u64::MAX.to_le_bytes());
        desc[16..20].copy_from_slice(&64u32.to_le_bytes());
        assert_eq!(decode_transport(&desc), Err(Error::Overflow));
        desc[..8].fill(0);
        assert_eq!(decode_transport(&desc).unwrap().request_bytes, 64);
        assert_eq!(
            require_success_capacity(Opcode::QueryDelivery, 127),
            Err(Error::Capacity)
        );
        assert!(require_success_capacity(Opcode::QueryDelivery, 128).is_ok());
    }
    #[test]
    fn last_legal_revision_request_and_response_agree() {
        let mut request = golden("install_budget");
        request[64..72].copy_from_slice(&(u64::MAX - 1).to_le_bytes());
        assert!(decode_request(&request).is_ok());
        let mut response = golden("install_budget_ok");
        response[56..64].copy_from_slice(&u64::MAX.to_le_bytes());
        response[64..72].copy_from_slice(&(u64::MAX - 1).to_le_bytes());
        assert!(
            decode_response(&response).is_ok(),
            "last legal CAS result must decode"
        );
        response[64..72].copy_from_slice(&u64::MAX.to_le_bytes());
        assert_eq!(decode_response(&response), Err(Error::Semantic));
    }

    #[test]
    fn last_legal_revision_history_is_queryable() {
        let mut response = golden("query_delivery_terminal");
        response[96..104].copy_from_slice(&u64::MAX.to_le_bytes());
        response[104..112].copy_from_slice(&(u64::MAX - 1).to_le_bytes());
        assert!(
            decode_response(&response).is_ok(),
            "last legal result must remain observable"
        );
        response[104..112].copy_from_slice(&u64::MAX.to_le_bytes());
        assert_eq!(decode_response(&response), Err(Error::Semantic));
    }
}
