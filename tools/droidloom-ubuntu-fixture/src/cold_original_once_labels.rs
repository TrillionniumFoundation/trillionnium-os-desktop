//! Qualification binding of the large, immutable, actual complete label plan.
//! No JSON field grants label authority: mutations arrive as the label writer's
//! non-constructible held-inode derivation, with actual xattr/generation syncfs.
use super::{OriginalQualificationAuthority, RetirementSource, owner, same_pin};
use crate::{Result, boot_files as files, ensure, fs, model::Identity};
use files::FilePin;
use std::{fs::File, io::Seek};

pub(super) struct LabelPlanBinding {
    pin: FilePin,
    held: File,
    identity: Identity,
}
impl LabelPlanBinding {
    pub(super) fn open(a: &OriginalQualificationAuthority, pin: &FilePin) -> Result<Self> {
        ensure(
            pin.path == a.work().join("labels/LABEL-PLAN.json")
                && pin.bytes > 0
                && pin.bytes <= 512 * 1024 * 1024,
            "complete label plan is outside its exact bounded work",
        )?;
        let (held, identity) = files::open_pin(pin)?;
        ensure(
            identity.uid == 0
                && identity.gid == 0
                && identity.nlink == 1
                && identity.mode == 0o100400,
            "complete label plan custody differs",
        )?;
        let value: serde_json::Value =
            serde_json::from_slice(&files::read_pin(pin, 512 * 1024 * 1024)?)?;
        ensure(
            value["schema"] == "droidloom.original-label-transaction-plan.v1"
                && value["candidate_id"] == a.candidate_id()
                && value["work_directory"] == a.work().join("labels").to_string_lossy().as_ref()
                && value["root_uuid"] == owner::ROOT_UUID,
            "complete label plan belongs to another original transaction",
        )?;
        let pair: FilePin = serde_json::from_value(value["pair_intent"].clone())?;
        match &*a.retirement.borrow() {
            RetirementSource::Prepared(actual) => ensure(
                same_pin(&pair, actual.pin()),
                "label plan is not bound to the actual held pair intent",
            )?,
            RetirementSource::Initial => {
                return Err("label plan precedes actual pair intent".into());
            }
        }
        let sources: FilePin = serde_json::from_value(value["normal_sources"].clone())?;
        ensure(
            a.admitted_inputs
                .iter()
                .any(|p| same_pin(&sources, p.pin())),
            "label plan normal source is not one of the freshly admitted immutable inputs",
        )?;
        let result = Self {
            pin: pin.clone(),
            held,
            identity,
        };
        result.full_readback()?;
        Ok(result)
    }
    pub(super) fn verify_pin(&self, pin: &FilePin) -> Result<()> {
        ensure(
            same_pin(&self.pin, pin),
            "label derivation changed its complete source plan",
        )?;
        self.revalidate()
    }
    pub(super) fn revalidate(&self) -> Result<()> {
        ensure(
            fs::stat(&self.held)? == self.identity
                && fs::Tree::open("/", 0)?.identity(&fs::absolute_string(&self.pin.path)?)?
                    == self.identity,
            "complete label plan held/named identity changed",
        )
    }
    pub(super) fn full_readback(&self) -> Result<()> {
        self.revalidate()?;
        let mut file = &self.held;
        file.rewind()?;
        ensure(
            fs::hash(file)? == self.pin.sha256,
            "complete label plan original bytes changed",
        )?;
        self.revalidate()
    }
}
