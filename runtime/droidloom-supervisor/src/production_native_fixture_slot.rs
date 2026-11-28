//! One source-owned late-born fixture at a time. The real accepted physical
//! peer, its PIDFD, and opaque factory lease survive between bounded requests.
//! This slot cannot be reconstructed from a receipt or an operator document.
use super::*;
use crate::native_leaf_fixture::{FixtureAction, NativeFixtureRequest};
use crate::production_application::{NativeFixtureLease, apk_scope::NativeLeafApkRoute};
use crate::production_selection::early_generation::EarlyApplicationAuthority;
use std::cell::RefCell;

struct Active { peer: crate::control::package::NativeUiPeer, lease: NativeFixtureLease }
#[derive(Default)]
pub(super) struct Slot {
    busy: bool,
    failure: Option<String>,
    active: Option<Active>,
    completed: Vec<NativeLeafApkRoute>,
}
impl Slot {
    pub(super) fn require_retired(&self) -> Result<(), ControlError> {
        if self.busy || self.active.is_some() || self.failure.is_some() {
            return Err(ControlError::Invalid("late-born fixture lease is incomplete; working data and original failure must be retained".into()));
        }
        Ok(())
    }
    pub(super) fn execute(cell:&RefCell<Self>,owner:&EarlyApplicationAuthority<'_>,stream:&UnixStream,
        caller:crate::control::package::NativeUiPeer,request:NativeFixtureRequest,end:Instant)
        ->std::result::Result<serde_json::Value,crate::production_application::ApplicationError>
    {
        use crate::production_application::{ApplicationError,begin_native_fixture};
        let reject=|s:&str|ApplicationError::Rejected(s.into());
        request.validate().map_err(|e|reject(&e))?;
        caller.revalidate(stream,end).map_err(ApplicationError::Io)?;
        let mut active={
            let mut slot=cell.borrow_mut();
            if slot.busy || slot.failure.is_some() || slot.completed.contains(&request.route()) {
                return Err(reject("fixed fixture slot is busy, failed, or this source case was already completed"));
            }
            if (request.action()==FixtureAction::Begin)!=slot.active.is_none() {
                return Err(reject("fixture request does not match the actual live slot"));
            }
            slot.busy=true;
            slot.active.take()
        };
        // No RefCell borrow remains across a factory progress callback. A
        // reentrant request sees busy and cannot replace this actual owner.
        let result:std::result::Result<serde_json::Value,ApplicationError>=(|| {
            let value=match request.action() {
                FixtureAction::Begin=>{
                    let lease=begin_native_fixture(owner,request.clone(),end)?;
                    let comparison=lease.begin_reply().comparison().map_err(|e|reject(&e))?;
                    active=Some(Active{peer:caller,lease});
                    comparison
                }
                FixtureAction::Guard|FixtureAction::State|FixtureAction::Retire=>{
                    let live=active.as_mut().ok_or_else(||reject("fixture has no original active lease"))?;
                    live.peer.revalidate(stream,end).map_err(ApplicationError::Io)?;
                    let reply=live.lease.continue_with(owner,request.clone(),end)?;
                    live.peer.revalidate(stream,end).map_err(ApplicationError::Io)?;
                    reply.comparison().map_err(|e|reject(&e))?
                }
            };
            if let Some(live)=&active {live.peer.revalidate(stream,end).map_err(ApplicationError::Io)?;}
            Ok(value)
        })();
        let mut slot=cell.borrow_mut();
        if !slot.busy || slot.active.is_some() {
            slot.failure.get_or_insert_with(||"fixture original slot was replaced during its factory callback".into());
            return Err(reject("fixture slot custody changed"));
        }
        slot.busy=false;
        match &result {
            Ok(_) if request.action()==FixtureAction::Retire => {slot.completed.push(request.route());}
            Ok(_) => {slot.active=active;}
            Err(error) => {slot.failure=Some(error.to_string());slot.active=active;}
        }
        result
    }
}
