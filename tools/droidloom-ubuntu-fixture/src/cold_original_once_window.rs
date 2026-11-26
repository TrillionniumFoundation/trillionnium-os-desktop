//! Actual, borrowed label window. The constructor needs the independently
//! guarded freezer and the already journalled complete label plan. It cannot
//! be deserialized or retained after that freezer is retired.
use super::{
    OriginalQualificationAuthority, RetirementSource, owner::SealedInput, quiescence::Quiescence,
    same_pin, state::Phase,
};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    cold_original_data::labels::OriginalLabelDerivation,
    ensure, fs,
    model::Identity,
};
use std::{cell::RefCell, collections::BTreeMap, fs::File};

struct CellCustody {
    held: File,
    identity: RefCell<Identity>,
    attrs: RefCell<BTreeMap<String, String>>,
    pin: FilePin,
}
impl CellCustody {
    fn open(a: &OriginalQualificationAuthority) -> Result<Self> {
        let (held, identity) = files::open_pin(a.expected_cell())?;
        ensure(
            identity.uid == 0
                && identity.gid == 0
                && identity.nlink == 1
                && identity.mode == 0o100644
                && fs::hash(&held)? == a.expected_cell().sha256,
            "window actual cell differs",
        )?;
        let attrs = fs::xattrs(&held)?;
        let result = Self {
            held,
            identity: RefCell::new(identity),
            attrs: RefCell::new(attrs),
            pin: a.expected_cell().clone(),
        };
        result.verify()?;
        Ok(result)
    }
    fn verify(&self) -> Result<()> {
        let (named, id) = files::open_pin(&self.pin)?;
        ensure(
            id == *self.identity.borrow()
                && fs::stat(&self.held)? == id
                && fs::xattrs(&self.held)? == *self.attrs.borrow()
                && fs::xattrs(&named)? == *self.attrs.borrow()
                && fs::stat(&named)? == id
                && fs::stat(&self.held)? == id,
            "window current cell inode/attributes changed",
        )
    }
    fn accept(&self, actual: &OriginalLabelDerivation) -> Result<()> {
        if actual.path() != self.pin.path {
            return Ok(());
        }
        let before = actual.before_identity();
        let after = actual.after_identity();
        let mut same = after.clone();
        same.ctime_sec = before.ctime_sec;
        same.ctime_nsec = before.ctime_nsec;
        ensure(
            same == *before
                && (*self.identity.borrow() == *before || *self.identity.borrow() == *after)
                && fs::stat(&self.held)? == *after,
            "actual cell label derivation changed body or inode",
        )?;
        let attrs = fs::xattrs(&self.held)?;
        let old = self.attrs.borrow();
        ensure(
            attrs
                .iter()
                .filter(|(k, _)| k.as_str() != "security.selinux")
                .eq(old.iter().filter(|(k, _)| k.as_str() != "security.selinux")),
            "cell label changed unrelated attributes",
        )?;
        drop(old);
        *self.identity.borrow_mut() = after.clone();
        *self.attrs.borrow_mut() = attrs;
        self.verify()
    }
}

pub(crate) struct OriginalLabelWindow<'a> {
    authority: &'a OriginalQualificationAuthority,
    frozen: &'a Quiescence,
    plan: FilePin,
    cell: CellCustody,
}
impl<'a> OriginalLabelWindow<'a> {
    pub(super) fn open(
        authority: &'a OriginalQualificationAuthority,
        frozen: &'a Quiescence,
    ) -> Result<Self> {
        authority.verify_current_owner()?;
        frozen.verify()?;
        ensure(
            frozen.candidate_id() == authority.candidate_id()
                && authority.journal.borrow().phase() == Some(Phase::LabelsIntent),
            "label window identity/phase differs",
        )?;
        let event = authority
            .journal
            .borrow()
            .observation(Phase::LabelsIntent)?
            .ok_or("durable label plan absent")?;
        let plan: FilePin = serde_json::from_value(event["label_plan"].clone())?;
        authority.verify_label_plan(&plan)?;
        authority
            .label_plan
            .borrow()
            .as_ref()
            .ok_or("held label plan absent")?
            .full_readback()?;
        let cell = CellCustody::open(authority)?;
        let result = Self {
            authority,
            frozen,
            plan,
            cell,
        };
        result.verify_step()?;
        Ok(result)
    }
    pub(crate) fn candidate_id(&self) -> &str {
        self.authority.candidate_id()
    }
    pub(crate) fn source_plan(&self) -> &FilePin {
        &self.plan
    }
    /// No source/archive body is re-read here. Every fixed open/named inode,
    /// all of its F9/attributes, actual locks/namespaces, selected cell, exact
    /// journal/plan and actual frozen cgroups are checked each time.
    pub(crate) fn verify_step(&self) -> Result<()> {
        self.frozen.verify()?;
        let a = self.authority;
        a.owner.borrow().revalidate()?;
        a.materials.revalidate_custody()?;
        for v in [
            &a.intent,
            &a.original_cell,
            &a.new_cell,
            &a.selection,
            &a.cold_clone,
        ] {
            v.revalidate_custody()?;
        }
        for v in &a.admitted_inputs {
            v.revalidate_custody()?;
        }
        a.journal.borrow().revalidate_custody()?;
        ensure(
            a.journal.borrow().phase() == Some(Phase::LabelsIntent),
            "label window phase advanced",
        )?;
        let named = fs::Tree::open(&fs::absolute_string(a.work())?, 0)?;
        for id in [fs::stat(&named.root)?, fs::stat(&a.work_fd)?] {
            ensure(
                (id.dev, id.ino, id.mode, id.uid, id.gid)
                    == (
                        a.work_identity.dev,
                        a.work_identity.ino,
                        a.work_identity.mode,
                        a.work_identity.uid,
                        a.work_identity.gid,
                    ),
                "label window work identity changed",
            )?;
        }
        match &*a.retirement.borrow() {
            RetirementSource::Prepared(v) => v.revalidate_custody()?,
            RetirementSource::Initial => return Err("label window lacks actual pair intent".into()),
        }
        a.label_plan
            .borrow()
            .as_ref()
            .ok_or("label window plan lost")?
            .verify_pin(&self.plan)?;
        self.cell.verify()?;
        self.frozen.verify()
    }
    /// This is the only fast rebind path. The opaque writer proof still fully
    /// validates held inode, generation, source-plan pin, actual label/xattrs,
    /// before/after metadata and durable xattr completion before updating locks.
    pub(crate) fn accept_derivation(&self, derivation: &OriginalLabelDerivation) -> Result<()> {
        self.frozen.verify()?;
        derivation.revalidate()?;
        ensure(
            derivation.candidate_id() == self.candidate_id()
                && same_pin(derivation.source_plan(), &self.plan),
            "window derivation belongs to another actual source/target",
        )?;
        self.authority.journal.borrow().revalidate_custody()?;
        ensure(
            self.authority.journal.borrow().phase() == Some(Phase::LabelsIntent),
            "label derivation phase advanced",
        )?;
        self.authority.owner.borrow_mut().accept_lock_label(
            derivation.path(),
            derivation.before_identity(),
            derivation.after_identity(),
        )?;
        self.cell.accept(derivation)?;
        self.verify_step()?;
        derivation.revalidate()
    }
    pub(crate) fn finish(self) -> Result<()> {
        self.verify_step()?;
        self.authority
            .label_plan
            .borrow()
            .as_ref()
            .ok_or("label plan absent")?
            .full_readback()?;
        self.authority.verify_current_owner()?;
        self.frozen.verify()
    }
}
