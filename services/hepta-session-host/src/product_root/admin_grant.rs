//! Finite original-artifact selectors/export. Files and DTOs grant no authority.
use super::*;
use codex_hepta_agentd::RootIssuedNotesGrantSelection;
use codex_hepta_contracts::{Sha256Digest, SignedFinalUseGrant};
use std::os::unix::fs::MetadataExt;
use std::path::PathBuf;

pub(super) struct Command {
    pub(super) action: RootAdminAction,
    pub(super) export: Option<PathBuf>,
}

pub(super) fn parse_command(args: impl Iterator<Item = OsString>) -> Result<Command> {
    let mut args = args.peekable();
    match args.peek().and_then(|value| value.to_str()) {
        Some("observe-grant") => observe(args),
        Some("revoke-grant") => revoke(args),
        _ => Ok(Command {
            action: parse_action(args)?,
            export: None,
        }),
    }
}

fn next_utf8(args: &mut impl Iterator<Item = OsString>) -> Result<String> {
    Ok(args
        .next()
        .ok_or("missing original admin argument")?
        .into_string()
        .map_err(|_| "original admin argument must be UTF8")?)
}
fn expected(args: &mut impl Iterator<Item = OsString>, flag: &str) -> Result<()> {
    if next_utf8(args)? != flag {
        return Err("unexpected or duplicate original admin argument".into());
    }
    Ok(())
}
fn nonzero(args: &mut impl Iterator<Item = OsString>) -> Result<u64> {
    let raw = next_utf8(args)?;
    let value: u64 = raw.parse()?;
    if value == 0 || raw != value.to_string() {
        return Err("expected canonical nonzero original revision".into());
    }
    Ok(value)
}
fn finish(args: &mut impl Iterator<Item = OsString>) -> Result<()> {
    if args.next().is_some() {
        return Err("unexpected or duplicate original admin argument".into());
    }
    Ok(())
}

fn observe(mut args: impl Iterator<Item = OsString>) -> Result<Command> {
    expected(&mut args, "observe-grant")?;
    let selection = match next_utf8(&mut args)?.as_str() {
        "--latest" => RootIssuedNotesGrantSelection::Latest {},
        "--grant-id" => {
            let grant_id = next_utf8(&mut args)?;
            if grant_id.is_empty()
                || grant_id.len() > 128
                || !grant_id
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"_-.:/".contains(&b))
            {
                return Err("invalid original grant ID selector".into());
            }
            RootIssuedNotesGrantSelection::Exact { grant_id }
        }
        _ => return Err("observe-grant needs exactly --latest or --grant-id".into()),
    };
    let export = match args.next() {
        None => None,
        Some(flag) if flag == "--export-grant" => {
            Some(PathBuf::from(args.next().ok_or("missing export path")?))
        }
        Some(_) => return Err("unexpected or duplicate grant observation argument".into()),
    };
    finish(&mut args)?;
    Ok(Command {
        action: RootAdminAction::ObserveIssuedNotesGrant { selection },
        export,
    })
}

fn revoke(mut args: impl Iterator<Item = OsString>) -> Result<Command> {
    expected(&mut args, "revoke-grant")?;
    expected(&mut args, "--signed-grant-file")?;
    let file = PathBuf::from(args.next().ok_or("missing original signed grant file")?);
    expected(&mut args, "--expected-effect-lease-revision")?;
    let expected_effect_lease_revision = nonzero(&mut args)?;
    expected(&mut args, "--expected-issuer-head-revision")?;
    let expected_issuer_head_revision = nonzero(&mut args)?;
    expected(&mut args, "--reason-sha256")?;
    let reason_sha256 = reason(&next_utf8(&mut args)?)?;
    finish(&mut args)?;
    // Artifact only: same issuer independently verifies signature/epoch/binding
    // and reads the exact EXISTING lease. No client-issued replacement exists.
    let signed_grant: SignedFinalUseGrant = fs::read_root_json(&file)?;
    signed_grant.grant.signing_bytes()?;
    if serde_json::to_vec(&signed_grant)?.len() > 8 * 1024 {
        return Err("original grant artifact bound".into());
    }
    Ok(Command {
        action: RootAdminAction::RevokeOriginalNotesGrant {
            signed_grant: Box::new(signed_grant),
            expected_effect_lease_revision,
            expected_issuer_head_revision,
            reason_sha256,
        },
        export: None,
    })
}

pub(super) fn finish_response(value: &serde_json::Value, export: Option<&Path>) -> Result<()> {
    match value["status"].as_str() {
        Some("observed" | "writer_revoked") if export.is_none() => Ok(()),
        Some("issued_notes_grant_observed") => {
            let observation = &value["observation"];
            if observation["status"] != "captured" {
                return Err("original issued grant observation unknown".into());
            }
            let raw = observation["signed_grant_json"]
                .as_str()
                .ok_or("original artifact absent")?;
            validate_artifact(raw, &observation["signed_grant_sha256"])?;
            if let Some(path) = export {
                let parent = path
                    .parent()
                    .ok_or("original artifact output has no parent")?;
                fs::root_directory(parent)?;
                if std::fs::metadata(parent)?.mode() & 0o7777 != 0o700 {
                    return Err("artifact output requires Root0700 parent".into());
                }
                fs::write_new(path, raw.as_bytes())?;
            }
            Ok(())
        }
        Some("original_notes_grant_revocation")
            if export.is_none()
                && !value["final_use_head"].is_null()
                && value["synchronization"]["state"] == "confirmed" =>
        {
            Ok(())
        }
        _ => Err("request refused, partial or outcome unknown; no mutation retry".into()),
    }
}

fn validate_artifact(raw: &str, expected_sha256: &serde_json::Value) -> Result<()> {
    if raw.is_empty()
        || raw.len() > 8 * 1024
        || expected_sha256.as_str() != Some(Sha256Digest::for_bytes(raw.as_bytes()).as_str())
    {
        return Err("original artifact bytes/digest mismatch".into());
    }
    let signed: SignedFinalUseGrant = serde_json::from_str(raw)?;
    signed.grant.signing_bytes()?;
    if signed.signature.len() != 64 {
        return Err("original signature length mismatch".into());
    }
    Ok(())
}

#[cfg(test)]
#[path = "admin_grant_tests.rs"]
mod tests;
