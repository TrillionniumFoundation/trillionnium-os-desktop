//! Closed source release schemas. V1 keeps the original CI contract and
//! one-field CURRENT relation. V2 can only retain the actual H2 child witness;
//! detached JSON comparison fields cannot replace that constructor.
use super::*;
use droidloom_supervisor::working_qualification::{
    WorkingLeafManifest, WorkingSourceFilePin, WorkingSourceWitness,
};
#[derive(Serialize)]
#[serde(untagged)]
pub(super) enum ReleaseManifest {
    Legacy(Manifest),
    Working(WorkingLeafManifest),
}
fn pin_from(value: &WorkingSourceFilePin) -> FilePin {
    FilePin {
        path: value.path.clone(),
        bytes: value.bytes,
        sha256: value.sha256.clone(),
    }
}
impl ReleaseManifest {
    pub(super) fn parse(raw: &[u8]) -> Result<Self, String> {
        let value = json(raw)?;
        let result = match value.get("schema").and_then(Value::as_str) {
            Some("pocket4-native-application-leaf-release-v1") => {
                Self::Legacy(serde_json::from_value(value).map_err(|e| e.to_string())?)
            }
            Some("pocket4-native-application-leaf-release-v2") => {
                Self::Working(serde_json::from_value(value).map_err(|e| e.to_string())?)
            }
            _ => return Err("unknown native source release schema".into()),
        };
        match &result {
            Self::Legacy(v) => v.validate()?,
            Self::Working(v) => v.validate()?,
        }
        Ok(result)
    }
    pub(super) fn binary(&self) -> FilePin {
        match self {
            Self::Legacy(v) => v.binary.clone(),
            Self::Working(v) => pin_from(&v.binary),
        }
    }
    pub(super) fn selection(&self) -> FilePin {
        match self {
            Self::Legacy(v) => v.selection.clone(),
            Self::Working(v) => pin_from(&v.selection),
        }
    }
    pub(super) fn catalog(&self) -> FilePin {
        match self {
            Self::Legacy(v) => v.catalog.clone(),
            Self::Working(v) => pin_from(&v.catalog),
        }
    }
    pub(super) fn before_copy(&self) -> FilePin {
        match self {
            Self::Legacy(v) => v.before_current_copy.clone(),
            Self::Working(v) => pin_from(&v.before_current_copy),
        }
    }
    pub(super) fn expiry(&self) -> u64 {
        match self {
            Self::Legacy(v) => v.owner_expires_unix_seconds,
            Self::Working(v) => v.owner_expires_unix_seconds,
        }
    }
    pub(super) fn owner(&self) -> Result<Value, String> {
        match self {
            Self::Legacy(v) => serde_json::to_value(&v.foreground_owner).map_err(|e| e.to_string()),
            Self::Working(v) => {
                serde_json::to_value(&v.foreground_owner).map_err(|e| e.to_string())
            }
        }
    }
    pub(super) fn relation(
        &self,
        before: &Value,
        current: &Value,
        reference: &FilePin,
    ) -> Result<(), String> {
        match self {
            Self::Legacy(_) => {
                require(
                    before.get("foreground_owner") == Some(&self.owner()?),
                    "preserved original CURRENT owner differs",
                )?;
                forward_relation(before, current, reference)
            }
            Self::Working(v) => {
                let mut permitted = before.clone();
                let map = permitted
                    .as_object_mut()
                    .ok_or("whole CURRENT preimage required")?;
                map.insert("foreground_owner".into(), self.owner()?);
                map.insert(
                    "application_qualification_preparations".into(),
                    serde_json::to_value(&v.selection).map_err(|e| e.to_string())?,
                );
                map.insert(
                    "native_application_leaf_release".into(),
                    serde_json::to_value(reference).map_err(|e| e.to_string())?,
                );
                require(
                    &permitted == current,
                    "working CURRENT must be the exact original three-field successor",
                )
            }
        }
    }
    pub(super) fn working_witness(&self) -> Result<Option<WorkingSourceWitness>, String> {
        match self {
            Self::Legacy(_) => Ok(None),
            Self::Working(v) => WorkingSourceWitness::capture(&v.working_owner).map(Some),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn closed_release_schema_never_infers_working_authority_from_unrecognized_json() {
        for raw in [br#"{}"#.as_slice(),
            br#"{"schema":"pocket4-native-application-leaf-release-v3"}"#.as_slice(),
            br#"{"schema":"pocket4-native-application-leaf-release-v1","working_owner":{"passed":true}}"#.as_slice(),
            br#"{"schema":"pocket4-native-application-leaf-release-v2","ci_run_id":1}"#.as_slice(),
            br#"{"schema":"pocket4-native-application-leaf-release-v1","schema":"pocket4-native-application-leaf-release-v2"}"#.as_slice()] {
            assert!(ReleaseManifest::parse(raw).is_err());
        }
    }
}
