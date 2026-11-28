//! Actual preparation peer transport for the one static IHG helper.
//! Kept separate from NativeUi and the three readonly preparation diagnostics.
use super::*;
use crate::native_ihg_helper::{MainBinding,IhgInstallRequest,IhgInstallReply,IhgStateRequest,IhgStateReply};
use crate::native_leaf_baseline::NativeLeafBaselineObservation;
use crate::prebuilt_native_helpers::PrebuiltIhgMaterial;
use std::{fs::File,process::Output};

pub(crate) struct IhgInstallObservation {reply:IhgInstallReply,_peer_pidfd:File,uid:u32}
pub(crate) struct IhgStateObservation {reply:IhgStateReply,_peer_pidfd:File,output:Output}
fn historical_peer(file:&File,main:&MainCustodyObservation,application:&ActualApplicationObservation)->Result<(),ControlError> {
    let id=|f:&File|->Result<(u64,u64),ControlError>{live(f).map_err(|e|io_error("IHG actual peer live",e))?;
        let m=f.metadata().map_err(|e|io_error("IHG actual peer identity",e))?;Ok((m.dev(),m.ino()))};
    if id(file)?!=id(&main.pidfd)?||id(file)?!=id(&application.pidfd)?||main.peer!=application.peer {
        return Err(ControlError::Invalid("IHG history belongs to another actual Main peer".into()))
    }Ok(())
}
impl IhgInstallObservation {
    pub(crate) fn uid(&self)->u32 {self.uid}
    pub(crate) fn comparison(&self)->Result<serde_json::Value,String>{self.reply.comparison()}
    pub(crate) fn require_main(&self,main:&MainCustodyObservation,target:&ActualApplicationObservation)->Result<(),ControlError>{
        historical_peer(&self._peer_pidfd,main,target)?;
        if !self.reply.matches(main.facts(),target.facts()){return Err(ControlError::Invalid("IHG install Main/target changed".into()))}Ok(())
    }
}
impl IhgStateObservation {
    pub(crate) fn output(&self)->&Output {&self.output}
    pub(crate) fn comparison(&self)->Result<serde_json::Value,String>{self.reply.comparison()}
    pub(crate) fn require_main(&self,main:&MainCustodyObservation,target:&ActualApplicationObservation)->Result<(),ControlError>{
        historical_peer(&self._peer_pidfd,main,target)?;
        if !self.reply.matches(main.facts(),target.facts()){return Err(ControlError::Invalid("IHG state Main/target changed".into()))}Ok(())
    }
}
impl NativeApplicationInspector {
    fn ihg_request(&self,baseline:&NativeLeafBaselineObservation<'_>,request:&ControlRequest,end:Instant)
        ->Result<(ControlResponse,File),ControlError>
    {
        baseline.verify_local(self,end)?;
        let stream=progress::connect(Path::new(DEFAULT_CONTROL_SOCKET)).map_err(|e|io_error("connect original IHG owner",e))?;
        let peer=peer_credentials_checked(&stream)?;
        let fd=peer_pidfd(&stream).map_err(|e|io_error("capture original IHG owner",e))?;
        let current=fd.metadata().map_err(|e|io_error("stat IHG peer",e))?;
        let original=self.pidfd.metadata().map_err(|e|io_error("stat original IHG peer",e))?;
        if peer.pid as u32!=self.peer_pid||(current.dev(),current.ino())!=(original.dev(),original.ino()){
            return Err(ControlError::Invalid("IHG socket changed actual owner".into()))
        }
        baseline.verify_local(self,end)?;
        let result=progress::request_on_until(stream,request,end);
        let after=(|| {live(&fd).map_err(|e|io_error("IHG peer final bookend",e))?;baseline.verify_local(self,end)})();
        let response=match (result,after) {
            (Ok(v),Ok(()))=>v,(Err(e),Ok(()))=>return Err(e),(Ok(_),Err(e))=>return Err(e),
            (Err(e),Err(post))=>return Err(ControlError::Invalid(format!("{e}; IHG custody postcheck also failed: {post}"))),
        };
        if !response.ok||response.state!=CellState::Running||response.host_pid!=Some(baseline.main().facts().epoch.cell_host_pid) {
            return Err(ControlError::Invalid(format!("actual IHG request failed; no automatic retry: {}",response.message)))
        }
        Ok((response,fd))
    }
    pub(crate) fn install_ihg_helper_until(&self,baseline:&NativeLeafBaselineObservation<'_>,binding:MainBinding,
        material:&PrebuiltIhgMaterial,end:Instant)->Result<IhgInstallObservation,ControlError>
    {
        let end=end.min(baseline.deadline());
        baseline.verify_local(self,end)?;material.guard(end).map_err(|e|io_error("guard normal IHG material",e))?;
        let request=IhgInstallRequest::from_owned(baseline,binding,end).map_err(ControlError::Invalid)?;
        let command=ControlRequest::InstallIhgHelper{request:request.clone()};
        let (response,fd)=self.ihg_request(baseline,&command,end)?;
        material.guard(end).map_err(|e|io_error("guard normal IHG material",e))?;
        let reply:IhgInstallReply=serde_json::from_str(response.diagnostics.as_deref().ok_or_else(||ControlError::Invalid("IHG actual install reply absent".into()))?)?;
        let uid=reply.validate(&request).map_err(ControlError::Invalid)?;
        baseline.verify_local(self,end)?;
        Ok(IhgInstallObservation{reply,_peer_pidfd:fd,uid})
    }
    pub(crate) fn observe_ihg_helper_state_until(&self,baseline:&NativeLeafBaselineObservation<'_>,helper:&ActualApplicationObservation,
        binding:MainBinding,nonce:String,end:Instant)->Result<IhgStateObservation,ControlError>
    {
        self.require_observations_local(baseline.main(),helper,end)?;
        let request=IhgStateRequest::from_owned(baseline,helper,binding,nonce,end).map_err(ControlError::Invalid)?;
        let (response,fd)=self.ihg_request(baseline,&ControlRequest::ObserveIhgHelperState{request:request.clone()},end)?;
        let reply:IhgStateReply=serde_json::from_str(response.diagnostics.as_deref().ok_or_else(||ControlError::Invalid("IHG actual state reply absent".into()))?)?;
        let output=reply.output_for(&request).map_err(ControlError::Invalid)?;
        self.require_observations_local(baseline.main(),helper,end)?;
        Ok(IhgStateObservation{reply,_peer_pidfd:fd,output})
    }
}
