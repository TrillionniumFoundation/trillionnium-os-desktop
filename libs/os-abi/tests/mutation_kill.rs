//! Host-only adversarial checks against the actual HOS2 Rust request parser.
//!
//! This is deliberately NOT another production delivery ledger or state
//! machine. The test uses one fixed Python-generated golden frame and the
//! production Rust decoder. The tiny classifier describes only the canonical
//! retry predicate; A03 owns reservation ordering, locks and durable results.

use hos2_os_abi::{decode_request, encode_request, Opcode, Request, RequestPayload};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Replay {
    NewId,
    Identical,
    Conflict,
}

fn hex(bytes: &str) -> Vec<u8> {
    assert_eq!(bytes.len() % 2, 0);
    let (pairs, remainder) = bytes.as_bytes().as_chunks::<2>();
    assert!(remainder.is_empty());
    pairs
        .iter()
        .map(|pair| {
            let hi = (pair[0] as char).to_digit(16).unwrap() as u8;
            let lo = (pair[1] as char).to_digit(16).unwrap() as u8;
            (hi << 4) | lo
        })
        .collect()
}

fn fixed_install() -> Vec<u8> {
    // Independent generator: tests/golden/generate_hos2.py, vector install_budget.
    hex("484f53320200000003000000400000002000000000000000010000000000000000000000000000000700000000000000090000000000000000000000000000000a0000000000000000e1f50500000000005a6202000000000000000000000000")
}

fn changed_u64(offset: usize, new_value: u64) -> Request {
    let mut bytes = fixed_install();
    bytes[offset..offset + 8].copy_from_slice(&new_value.to_le_bytes());
    decode_request(&bytes).unwrap()
}

fn canonical_retry(prior: &Request, next: &Request) -> Replay {
    if prior.request_id != next.request_id {
        Replay::NewId
    } else if prior == next {
        Replay::Identical
    } else {
        Replay::Conflict
    }
}

fn must_conflict(
    prior: &Request,
    next: &Request,
    predicate: fn(&Request, &Request) -> Replay,
) -> Result<(), &'static str> {
    match predicate(prior, next) {
        Replay::Conflict => Ok(()),
        Replay::Identical => Err("mutant treated distinct canonical writes as a retry"),
        Replay::NewId => Err("mutant lost the shared delivery sequence identity"),
    }
}

fn ignoring_cap(prior: &Request, next: &Request) -> Replay {
    if prior.request_id != next.request_id {
        return Replay::NewId;
    }
    match (prior.payload, next.payload) {
        (RequestPayload::InstallBudget(a), RequestPayload::InstallBudget(b))
            if prior.target_slot == next.target_slot
                && prior.target_generation == next.target_generation
                && a.expected_revision == b.expected_revision
                && a.period_ns == b.period_ns
                && a.reserved == b.reserved =>
        {
            Replay::Identical // BUG: the cap is deliberately omitted.
        }
        _ => Replay::Conflict,
    }
}

fn ignoring_expected_revision(prior: &Request, next: &Request) -> Replay {
    if prior.request_id != next.request_id {
        return Replay::NewId;
    }
    match (prior.payload, next.payload) {
        (RequestPayload::InstallBudget(a), RequestPayload::InstallBudget(b))
            if prior.target_slot == next.target_slot
                && prior.target_generation == next.target_generation
                && a.cap_ns == b.cap_ns
                && a.period_ns == b.period_ns
                && a.reserved == b.reserved =>
        {
            Replay::Identical // BUG: expected_revision is deliberately omitted.
        }
        _ => Replay::Conflict,
    }
}

fn ignoring_target(prior: &Request, next: &Request) -> Replay {
    if prior.request_id != next.request_id {
        return Replay::NewId;
    }
    if prior.payload == next.payload {
        Replay::Identical // BUG: different slots can never reuse a CapSpace D.
    } else {
        Replay::Conflict
    }
}

#[test]
fn fixed_golden_is_a_real_valid_rust_request() {
    let fixed = fixed_install();
    let parsed = decode_request(&fixed).unwrap();
    assert_eq!(parsed.opcode, Opcode::InstallBudget);
    assert_eq!(parsed.target_slot, 7);
    assert_eq!(parsed.target_generation, 9);
    assert_eq!(canonical_retry(&parsed, &parsed), Replay::Identical);

    let mut encoded = [0u8; 96];
    assert_eq!(encode_request(&parsed, &mut encoded), Ok(96));
    assert_eq!(encoded.as_slice(), fixed.as_slice());
}

#[test]
fn same_sequence_and_target_different_cap_is_conflict() {
    let previous = decode_request(&fixed_install()).unwrap();
    let updated = changed_u64(80, 39_000_000);
    assert_eq!(previous.request_id, updated.request_id);
    assert_eq!(previous.target_slot, updated.target_slot);
    assert_eq!(previous.target_generation, updated.target_generation);
    assert_ne!(previous, updated);
    assert_eq!(canonical_retry(&previous, &updated), Replay::Conflict);
    assert_eq!(must_conflict(&previous, &updated, canonical_retry), Ok(()));
}

#[test]
fn same_sequence_and_target_different_revision_is_conflict() {
    let previous = decode_request(&fixed_install()).unwrap();
    let updated = changed_u64(64, 9);
    assert_eq!(previous.request_id, updated.request_id);
    assert_eq!(previous.target_slot, updated.target_slot);
    assert_eq!(previous.target_generation, updated.target_generation);
    assert_ne!(previous, updated);
    assert_eq!(canonical_retry(&previous, &updated), Replay::Conflict);
    assert_eq!(must_conflict(&previous, &updated, canonical_retry), Ok(()));
}

#[test]
fn cap_ignoring_mutant_is_killed_by_same_delivery_oracle() {
    let prior = decode_request(&fixed_install()).unwrap();
    let next = changed_u64(80, 39_000_000);
    assert_eq!(ignoring_cap(&prior, &next), Replay::Identical);
    assert!(must_conflict(&prior, &next, ignoring_cap).is_err());
    assert!(must_conflict(&prior, &next, canonical_retry).is_ok());
}

#[test]
fn revision_ignoring_mutant_is_killed_by_same_delivery_oracle() {
    let prior = decode_request(&fixed_install()).unwrap();
    let next = changed_u64(64, 9);
    assert_eq!(ignoring_expected_revision(&prior, &next), Replay::Identical);
    assert!(must_conflict(&prior, &next, ignoring_expected_revision).is_err());
    assert!(must_conflict(&prior, &next, canonical_retry).is_ok());
}

#[test]
fn same_sequence_across_targets_is_also_conflict() {
    let prior = decode_request(&fixed_install()).unwrap();
    let mut next = prior;
    next.target_slot += 1;
    assert_eq!(prior.request_id, next.request_id);
    assert_ne!(prior, next);
    assert_eq!(canonical_retry(&prior, &next), Replay::Conflict);
    assert_eq!(ignoring_target(&prior, &next), Replay::Identical);
    assert!(must_conflict(&prior, &next, ignoring_target).is_err());
}

#[test]
fn same_sequence_and_slot_different_generation_is_conflict() {
    let prior = decode_request(&fixed_install()).unwrap();
    // Slot reuse changes the capability identity, even when its index and all
    // budget fields stay the same. Mutate only the fixed wire generation.
    let next = changed_u64(48, prior.target_generation + 1);
    assert_eq!(prior.request_id, next.request_id);
    assert_eq!(prior.target_slot, next.target_slot);
    assert_eq!(prior.payload, next.payload);
    assert_ne!(prior.target_generation, next.target_generation);
    assert_ne!(prior, next);
    assert_eq!(canonical_retry(&prior, &next), Replay::Conflict);
    assert_eq!(must_conflict(&prior, &next, canonical_retry), Ok(()));
    assert_eq!(ignoring_target(&prior, &next), Replay::Identical);
    assert!(must_conflict(&prior, &next, ignoring_target).is_err());
}

#[test]
fn full_low_eight_byte_sequence_is_little_endian_and_high_half_zero() {
    let mut req = decode_request(&fixed_install()).unwrap();
    req.request_id = [1, 2, 3, 4, 5, 6, 7, 8, 0, 0, 0, 0, 0, 0, 0, 0];
    let mut encoded = [0u8; 96];
    assert_eq!(encode_request(&req, &mut encoded), Ok(96));
    assert_eq!(&encoded[24..40], &req.request_id);
    let decoded = decode_request(&encoded).unwrap();
    assert_eq!(decoded, req);
    assert_eq!(
        canonical_retry(&decoded, &decode_request(&fixed_install()).unwrap()),
        Replay::NewId
    );
}
