//! Read only the Android attestation OID and two public security-level declarations.
//! No signature trust, identity, private key, or current HAL capability is inferred.
//! Schema: https://source.android.com/docs/security/features/keystore/attestation
use crate::{Result, database::DEFAULT_UUID};
use rusqlite::{Connection, types::ValueRef};
use serde::Serialize;
use std::collections::BTreeMap;

const ATTESTATION_OID: &[u8] = &[0x2b, 0x06, 0x01, 0x04, 0x01, 0xd6, 0x79, 0x02, 0x01, 0x11];
#[derive(Default, Serialize)]
pub(crate) struct Summary {
    all_stored_certificate_blobs: Scope,
    live_default_route_client_certificate_blobs: Scope,
    signature_validation_performed: bool,
    historical_declarations_are_current_hardware_evidence: bool,
}
#[derive(Default, Serialize)]
struct Scope {
    blobs: u64,
    der_certificates: u64,
    malformed_or_unsupported_blobs: u64,
    android_attestation_oid_certificates: u64,
    malformed_attestation_extensions: u64,
    declared_security_level_pairs: BTreeMap<String, u64>,
}
enum Attestation {
    Absent,
    Levels(u8, u8),
    Malformed,
}
fn tlv<'a>(input: &mut &'a [u8]) -> std::result::Result<(u8, &'a [u8]), ()> {
    if input.len() < 2 {
        return Err(());
    }
    let tag = input[0];
    if tag & 0x1f == 0x1f {
        return Err(());
    }
    let first = input[1];
    let (header, length) = if first < 128 {
        (2, usize::from(first))
    } else {
        let n = usize::from(first & 0x7f);
        if n == 0 || n > 4 || input.len() < 2 + n || input[2] == 0 {
            return Err(());
        }
        let mut length = 0_usize;
        for byte in &input[2..2 + n] {
            length = length
                .checked_mul(256)
                .and_then(|x| x.checked_add(usize::from(*byte)))
                .ok_or(())?;
        }
        if length < 128 {
            return Err(());
        }
        (2 + n, length)
    };
    let end = header.checked_add(length).ok_or(())?;
    if end > input.len() {
        return Err(());
    }
    let value = &input[header..end];
    *input = &input[end..];
    Ok((tag, value))
}
fn take<'a>(input: &mut &'a [u8], wanted: u8) -> std::result::Result<&'a [u8], ()> {
    let (tag, value) = tlv(input)?;
    if tag != wanted {
        return Err(());
    }
    Ok(value)
}
fn levels(data: &[u8]) -> std::result::Result<(u8, u8), ()> {
    let mut outer = data;
    let mut seq = take(&mut outer, 0x30)?;
    if !outer.is_empty() {
        return Err(());
    }
    let version = take(&mut seq, 0x02)?;
    let att = take(&mut seq, 0x0a)?;
    let km_version = take(&mut seq, 0x02)?;
    let km = take(&mut seq, 0x0a)?;
    if version.is_empty()
        || version[0] & 0x80 != 0
        || km_version.is_empty()
        || km_version[0] & 0x80 != 0
        || att.len() != 1
        || km.len() != 1
        || att[0] > 2
        || km[0] > 2
    {
        return Err(());
    }
    take(&mut seq, 0x04)?; // challenge: never emitted
    take(&mut seq, 0x04)?; // unique ID: never emitted
    take(&mut seq, 0x30)?; // software authorizations: never emitted
    take(&mut seq, 0x30)?; // hardware authorizations: never emitted
    if !seq.is_empty() {
        return Err(());
    }
    Ok((att[0], km[0]))
}
fn certificate(seq: &[u8]) -> std::result::Result<Attestation, ()> {
    let mut body = seq;
    let mut tbs = take(&mut body, 0x30)?;
    take(&mut body, 0x30)?;
    let signature = take(&mut body, 0x03)?;
    if !body.is_empty() || signature.is_empty() {
        return Err(());
    }
    if tbs.first() == Some(&0xa0) {
        let mut version = take(&mut tbs, 0xa0)?;
        take(&mut version, 0x02)?;
        if !version.is_empty() {
            return Err(());
        }
    }
    take(&mut tbs, 0x02)?;
    for _ in 0..5 {
        take(&mut tbs, 0x30)?;
    } // algorithm, issuer, validity, subject, SPKI
    for optional in [0x81, 0x82] {
        if tbs.first() == Some(&optional) {
            take(&mut tbs, optional)?;
        }
    }
    if tbs.is_empty() {
        return Ok(Attestation::Absent);
    }
    let mut extension_outer = take(&mut tbs, 0xa3)?;
    if !tbs.is_empty() {
        return Err(());
    }
    let mut extensions = take(&mut extension_outer, 0x30)?;
    if !extension_outer.is_empty() {
        return Err(());
    }
    let mut result = Attestation::Absent;
    let mut found = false;
    while !extensions.is_empty() {
        let mut extension = take(&mut extensions, 0x30)?;
        let oid = take(&mut extension, 0x06)?;
        if extension.first() == Some(&0x01) {
            let critical = take(&mut extension, 0x01)?;
            if critical.len() != 1 || ![0, 255].contains(&critical[0]) {
                return Err(());
            }
        }
        let content = take(&mut extension, 0x04)?;
        if !extension.is_empty() {
            return Err(());
        }
        if oid == ATTESTATION_OID {
            if found {
                result = Attestation::Malformed;
            } else {
                result = match levels(content) {
                    Ok((a, k)) => Attestation::Levels(a, k),
                    Err(()) => Attestation::Malformed,
                };
            }
            found = true;
        }
    }
    Ok(result)
}
fn record(scope: &mut Scope, value: &Attestation) {
    scope.der_certificates += 1;
    match value {
        Attestation::Absent => {}
        Attestation::Levels(a, k) => {
            scope.android_attestation_oid_certificates += 1;
            *scope
                .declared_security_level_pairs
                .entry(format!("attestation_{a}_keymint_{k}"))
                .or_default() += 1;
        }
        Attestation::Malformed => {
            scope.android_attestation_oid_certificates += 1;
            scope.malformed_attestation_extensions += 1;
        }
    }
}
fn inspect(data: &[u8], all: &mut Scope, scoped: Option<&mut Scope>) {
    let mut scoped = scoped;
    all.blobs += 1;
    if let Some(s) = scoped.as_deref_mut() {
        s.blobs += 1;
    }
    let mut rest = data;
    let mut malformed = rest.is_empty();
    while !rest.is_empty() {
        match take(&mut rest, 0x30).and_then(certificate) {
            Ok(value) => {
                record(all, &value);
                if let Some(s) = scoped.as_deref_mut() {
                    record(s, &value);
                }
            }
            Err(()) => {
                malformed = true;
                break;
            }
        }
    }
    if malformed {
        all.malformed_or_unsupported_blobs += 1;
        if let Some(s) = scoped {
            s.malformed_or_unsupported_blobs += 1;
        }
    }
}
pub(crate) fn summarize(db: &Connection) -> Result<Summary> {
    let mut result = Summary::default();
    let mut statement = db
        .prepare(
            "SELECT b.blob, (e.key_type=0 AND e.state=1 AND e.km_uuid=?1 AND b.state=0)
         FROM blobentry b LEFT JOIN keyentry e ON e.id=b.keyentryid
         WHERE b.subcomponent_type IN (1,2) ORDER BY b.id",
        )
        .map_err(|_| "certificate_aggregate_query_failed")?;
    let mut rows = statement
        .query([DEFAULT_UUID])
        .map_err(|_| "certificate_aggregate_query_failed")?;
    while let Some(row) = rows
        .next()
        .map_err(|_| "certificate_aggregate_row_failed")?
    {
        let active = row
            .get::<_, Option<bool>>(1)
            .map_err(|_| "certificate_scope_decode_failed")?
            .unwrap_or(false);
        let data = match row
            .get_ref(0)
            .map_err(|_| "certificate_blob_decode_failed")?
        {
            ValueRef::Blob(bytes) => bytes,
            _ => &[],
        };
        let scoped = if active {
            Some(&mut result.live_default_route_client_certificate_blobs)
        } else {
            None
        };
        inspect(data, &mut result.all_stored_certificate_blobs, scoped);
    }
    Ok(result)
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    pub(crate) fn der(tag: u8, bytes: &[u8]) -> Vec<u8> {
        let mut out = vec![tag];
        if bytes.len() < 128 {
            out.push(bytes.len() as u8);
        } else if bytes.len() < 256 {
            out.extend_from_slice(&[0x81, bytes.len() as u8]);
        } else {
            out.extend_from_slice(&[0x82, (bytes.len() >> 8) as u8, bytes.len() as u8]);
        }
        out.extend_from_slice(bytes);
        out
    }
    pub(crate) fn fixture(a: Option<(u8, u8)>) -> Vec<u8> {
        let mut tbs = der(0xa0, &der(2, &[2]));
        tbs.extend(der(2, &[1]));
        for _ in 0..5 {
            tbs.extend(der(0x30, &[]));
        }
        if let Some((a, k)) = a {
            let mut description = der(2, &[100]);
            description.extend(der(0x0a, &[a]));
            description.extend(der(2, &[100]));
            description.extend(der(0x0a, &[k]));
            description.extend(der(4, b"synthetic challenge"));
            description.extend(der(4, b"synthetic ID never logged"));
            description.extend(der(0x30, &[]));
            description.extend(der(0x30, &[]));
            let mut extension = der(6, ATTESTATION_OID);
            extension.extend(der(4, &der(0x30, &description)));
            tbs.extend(der(0xa3, &der(0x30, &der(0x30, &extension))));
        }
        let mut cert = der(0x30, &tbs);
        cert.extend(der(0x30, &[]));
        cert.extend(der(3, &[0, 1, 2, 3]));
        der(0x30, &cert)
    }
    #[test]
    fn certificate_chain_counts_historical_levels_without_trust_claims() {
        let mut bytes = fixture(Some((1, 1)));
        bytes.extend(fixture(Some((0, 0))));
        bytes.extend(fixture(None));
        let mut summary = Scope::default();
        inspect(&bytes, &mut summary, None);
        assert_eq!(summary.der_certificates, 3);
        assert_eq!(summary.android_attestation_oid_certificates, 2);
        assert_eq!(
            summary.declared_security_level_pairs["attestation_1_keymint_1"],
            1
        );
        assert_eq!(summary.malformed_or_unsupported_blobs, 0);
    }
    #[test]
    fn truncated_and_unknown_level_are_reported_not_treated_as_absent() {
        let bytes = fixture(Some((7, 1)));
        let mut summary = Scope::default();
        inspect(&bytes, &mut summary, None);
        assert_eq!(summary.android_attestation_oid_certificates, 1);
        assert_eq!(summary.malformed_attestation_extensions, 1);
        let mut summary = Scope::default();
        inspect(&bytes[..bytes.len() - 1], &mut summary, None);
        assert_eq!(summary.malformed_or_unsupported_blobs, 1);
        for length in 0..bytes.len() {
            let mut summary = Scope::default();
            inspect(&bytes[..length], &mut summary, None);
        }
    }
    #[test]
    fn oid_outside_extensions_does_not_count() {
        let mut cert = fixture(None);
        // An OID embedded in signature bytes must not be mistaken for an extension.
        cert = {
            let mut outer = cert.as_slice();
            let body = take(&mut outer, 0x30).unwrap();
            let mut body = body;
            let tbs = take(&mut body, 0x30).unwrap();
            let mut new = der(0x30, tbs);
            new.extend(der(0x30, &[]));
            let mut sig = vec![0];
            sig.extend(ATTESTATION_OID);
            new.extend(der(3, &sig));
            der(0x30, &new)
        };
        let mut summary = Scope::default();
        inspect(&cert, &mut summary, None);
        assert_eq!(summary.der_certificates, 1);
        assert_eq!(summary.android_attestation_oid_certificates, 0);
    }
}
