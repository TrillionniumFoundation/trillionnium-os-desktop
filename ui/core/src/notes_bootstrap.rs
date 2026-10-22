//! One-time private Session-to-original-owner descriptor handoff. These
//! messages carry no grant and are never accepted by public Session IPC.

use serde::{Deserialize, Serialize};

use crate::notes::NotesTargetIdentity;

pub const NOTES_BOOTSTRAP_MAX_BYTES: usize = 1024;
pub const NOTES_BOOTSTRAP_SCHEMA_VERSION: u16 = 1;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NotesBootstrapOfferAction {
    OfferNotesTarget,
}

/// One datagram, accompanied by exactly one SCM_RIGHTS descriptor for the
/// Notes effect UnixStream. Version 1 bootstraps only initial task 1.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NotesBootstrapOffer {
    pub schema_version: u16,
    pub action: NotesBootstrapOfferAction,
    pub target: NotesTargetIdentity,
    pub destination_id: String,
}

impl NotesBootstrapOffer {
    pub fn new(target: NotesTargetIdentity) -> Result<Self, &'static str> {
        let value = Self {
            schema_version: NOTES_BOOTSTRAP_SCHEMA_VERSION,
            action: NotesBootstrapOfferAction::OfferNotesTarget,
            destination_id: target.destination_id(),
            target,
        };
        value.validate()?;
        Ok(value)
    }

    pub fn parse_exact(raw: &[u8]) -> Result<Self, &'static str> {
        frame(raw)?;
        let value: Self = serde_json::from_slice(raw).map_err(|_| "bootstrap offer schema")?;
        value.validate()?;
        Ok(value)
    }

    fn validate(&self) -> Result<(), &'static str> {
        identity(self.schema_version, &self.target, &self.destination_id)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NotesBootstrapAckAction {
    NotesTargetRegistration,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NotesBootstrapStatus {
    Attached,
    Rejected,
}

/// No ancillary descriptor may accompany the ACK. Attached means only that
/// the original host acknowledged explicit target composition. It says
/// nothing about FinalUse issuance, an effect, pixels or durable terminality.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NotesBootstrapAck {
    pub schema_version: u16,
    pub action: NotesBootstrapAckAction,
    pub target: NotesTargetIdentity,
    pub destination_id: String,
    pub status: NotesBootstrapStatus,
}

impl NotesBootstrapAck {
    pub fn parse_exact(raw: &[u8]) -> Result<Self, &'static str> {
        frame(raw)?;
        let value: Self = serde_json::from_slice(raw).map_err(|_| "bootstrap ACK schema")?;
        identity(value.schema_version, &value.target, &value.destination_id)?;
        Ok(value)
    }

    pub fn matches(&self, offer: &NotesBootstrapOffer) -> bool {
        self.target == offer.target && self.destination_id == offer.destination_id
    }
}

fn identity(
    version: u16,
    target: &NotesTargetIdentity,
    destination: &str,
) -> Result<(), &'static str> {
    target.validate().map_err(|_| "bootstrap identity")?;
    if version != NOTES_BOOTSTRAP_SCHEMA_VERSION
        || target.task_id != 1
        || destination != target.destination_id()
    {
        return Err("bootstrap version, initial task or destination");
    }
    Ok(())
}

fn frame(raw: &[u8]) -> Result<(), &'static str> {
    if raw.is_empty() || raw.len() > NOTES_BOOTSTRAP_MAX_BYTES {
        return Err("bootstrap frame bound");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fixed_bootstrap_fixture_pins_the_initial_target_and_ack() {
        let fixture: serde_json::Value =
            serde_json::from_str(include_str!("../../../tests/ui/notes-bootstrap-v1.json"))
                .unwrap();
        let offer =
            NotesBootstrapOffer::parse_exact(fixture["offer_utf8"].as_str().unwrap().as_bytes())
                .unwrap();
        let ack = NotesBootstrapAck::parse_exact(
            fixture["attached_ack_utf8"].as_str().unwrap().as_bytes(),
        )
        .unwrap();
        assert!(ack.matches(&offer));
        assert_eq!(ack.status, NotesBootstrapStatus::Attached);
        let refused = NotesBootstrapAck::parse_exact(
            fixture["rejected_ack_utf8"].as_str().unwrap().as_bytes(),
        )
        .unwrap();
        assert!(refused.matches(&offer));
        assert_eq!(refused.status, NotesBootstrapStatus::Rejected);
    }

    #[test]
    fn bootstrap_rejects_duplicates_unknown_fields_and_noninitial_identity() {
        let target = NotesTargetIdentity {
            session_instance: "1".repeat(32),
            task_id: 1,
            incarnation: "2".repeat(32),
        };
        let raw =
            serde_json::to_string(&NotesBootstrapOffer::new(target.clone()).unwrap()).unwrap();
        for invalid in [
            raw.replacen('{', "{\"schema_version\":1,", 1),
            raw.replacen('{', "{\"grant\":true,", 1),
            raw.replace("\"task_id\":1", "\"task_id\":2"),
            raw.replace("offer_notes_target", "replace_note"),
        ] {
            assert!(NotesBootstrapOffer::parse_exact(invalid.as_bytes()).is_err());
        }
        let mut noninitial = target;
        noninitial.task_id = 2;
        assert!(NotesBootstrapOffer::new(noninitial).is_err());
        assert!(
            NotesBootstrapAck::parse_exact(&vec![b' '; NOTES_BOOTSTRAP_MAX_BYTES + 1]).is_err()
        );
    }
}
