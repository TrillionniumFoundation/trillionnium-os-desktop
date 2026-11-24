//! Reassemble bounded copied pixels from the same held presenter and window.
//! No returned JSON token may replace the live Session retained by the broker.
use super::*;
use base64::Engine;
use sha2::Digest;

pub(super) fn collect(
    first: window::CapturePart,
    initial: &window::Observation,
    lease: &Lease,
    call: &WindowCall<'_>,
    until: Instant,
) -> Result<window::Image, ControlError> {
    let meta = first.original.clone();
    if Some(meta.object) != initial.object
        || initial.phase != window::Phase::Bound
        || !initial.mapped
        || first.offset != 0
    {
        return Err(ControlError::Invalid(
            "capture does not identify the original bound mapped window".into(),
        ));
    }
    let mut bytes = first
        .decode()
        .map_err(|e| ControlError::Invalid(e.to_string()))?;
    while (bytes.len() as u64) < meta.total_png_bytes {
        let (mut reply, _) = invoke(
            call,
            &window::Command::CaptureChunk {
                lease: lease.token,
                capture: meta.capture,
                offset: bytes.len() as u64,
            },
            Some(&lease.session),
            until,
        )?;
        let state = reply
            .result()
            .map_err(|e| ControlError::Invalid(e.to_string()))?;
        if state.lease != initial.lease
            || state.object != initial.object
            || state.android_task != initial.android_task
            || state.creation_serial != initial.creation_serial
            || state.phase != window::Phase::Bound
            || !state.mapped
        {
            return Err(ControlError::Invalid(
                "original window changed while reading captured pixels".into(),
            ));
        }
        let part = reply
            .capture
            .take()
            .ok_or_else(|| ControlError::Invalid("original capture part missing".into()))?;
        if part.original != meta || part.offset != bytes.len() as u64 {
            return Err(ControlError::Invalid(
                "capture parts came from different original frames or offsets".into(),
            ));
        }
        let part = part
            .decode()
            .map_err(|e| ControlError::Invalid(e.to_string()))?;
        bytes.extend_from_slice(&part);
        if bytes.len() > window::MAX_PNG_BYTES {
            return Err(ControlError::Invalid(
                "captured pixels exceeded the fixed byte budget".into(),
            ));
        }
    }
    if Instant::now() >= until
        || bytes.len() as u64 != meta.total_png_bytes
        || bytes.len() < 24
        || &bytes[..8] != b"\x89PNG\r\n\x1a\n"
        || &bytes[12..16] != b"IHDR"
        || u32::from_be_bytes(bytes[16..20].try_into().unwrap()) != meta.width
        || u32::from_be_bytes(bytes[20..24].try_into().unwrap()) != meta.height
    {
        return Err(ControlError::Invalid(
            "original capture PNG shape or deadline differs".into(),
        ));
    }
    let sha256 = format!("{:x}", sha2::Sha256::digest(&bytes));
    let png_base64 = base64::engine::general_purpose::STANDARD.encode(&bytes);
    if Instant::now() >= until {
        return Err(ControlError::Invalid(
            "capture encoding exceeded its original deadline".into(),
        ));
    }
    Ok(window::Image {
        original: meta,
        sha256,
        png_base64,
    })
}
