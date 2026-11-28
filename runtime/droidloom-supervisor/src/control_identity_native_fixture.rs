//! Actual physical caller transport for the fixed late-born fixture lease.
//! The original peer PIDFD and source material stay held across the business
//! interval. Comparison replies never reconstruct the broker's lease.
use super::*;
use crate::native_leaf_baseline::NativeLeafBaselineObservation;
use crate::native_leaf_fixture::{FixtureAction,NativeFixtureReply,NativeFixtureRequest};
use crate::native_leaf_fixture_material::NativeLeafFixtureMaterial;
use std::fs::File;

pub(crate) struct NativeFixtureObservation {
    begin: NativeFixtureReply,
    peer: File,
    material: NativeLeafFixtureMaterial,
    retired: Option<NativeFixtureReply>,
    failure: Option<String>,
    original_absence:serde_json::Value,
    data:crate::native_leaf_baseline_data::HeldLeafData,
}
impl NativeFixtureObservation {
    fn require_live(&self,inspector:&NativeApplicationInspector,baseline:&NativeLeafBaselineObservation<'_>,end:Instant)->Result<(),ControlError> {
        if self.failure.is_some() || self.retired.is_some() {
            return Err(ControlError::Invalid("fixture observation already retired or has an unresolved failure".into()));
        }
        baseline.verify_local(inspector,end)?;
        live(&self.peer).map_err(|e|io_error("fixture original broker live",e))?;
        let a=self.peer.metadata().map_err(|e|io_error("fixture held broker identity",e))?;
        let b=inspector.pidfd.metadata().map_err(|e|io_error("fixture current broker identity",e))?;
        if (a.dev(),a.ino())!=(b.dev(),b.ino()) || self.begin.request().main()!=baseline.main().facts()
            || self.begin.request().primary()!=baseline.application()
            || baseline.owned_fixture_route()?!=Some(self.begin.request().route()) {
            return Err(ControlError::Invalid("fixture live peer/Main/source route changed".into()));
        }
        self.material.guard(end).map_err(|e|io_error("fixture held complete source guard",e))
    }
    pub(crate) fn begin_comparison(&self)->Result<serde_json::Value,ControlError> {
        self.comparison(&self.begin,None)
    }
    fn comparison(&self,reply:&NativeFixtureReply,retirement_absence:Option<serde_json::Value>)
        ->Result<serde_json::Value,ControlError>
    {
        Ok(serde_json::json!({"schema":"droidloom.native-fixture-observation.v1",
            "transaction":reply.comparison().map_err(ControlError::Invalid)?,"original_absence":self.original_absence,
            "actual_data":self.data.facts(),"retirement_absence":retirement_absence,
            "comparison_only":true,"business_accepted":false}))
    }
    pub(crate) fn continue_until(&mut self,inspector:&NativeApplicationInspector,baseline:&NativeLeafBaselineObservation<'_>,
        action:FixtureAction,end:Instant)->Result<serde_json::Value,ControlError>
    {
        let result:Result<serde_json::Value,ControlError>=(|| {
            self.require_live(inspector,baseline,end)?;
            self.data.verify().map_err(|e|io_error("fixture actual helper CE/DE guard",e))?;
            let request=self.begin.request().continuation(action,end).map_err(ControlError::Invalid)?;
            let (reply,_peer)=inspector.fixture_request(baseline,&request,end)?;
            reply.validate(&request,Some(&self.begin)).map_err(ControlError::Invalid)?;
            self.require_live(inspector,baseline,end)?;
            let absent=if action==FixtureAction::Retire {Some(baseline.fixture_absent(request.kind().map_err(ControlError::Invalid)?)?)}
                else {self.data.verify().map_err(|e|io_error("fixture actual helper final CE/DE guard",e))?;None};
            if let Some(state)=reply.state_value().map_err(ControlError::Invalid)? {
                for (name,actual) in ["ce","de"].into_iter().zip(&self.data.facts().directories[2..]) {
                    if state[name][0]!=actual.device || state[name][1]!=actual.inode || state[name][2]!=actual.mode {
                        return Err(ControlError::Invalid("provider did not read the actually held late-born CE/DE inode".into()));
                    }
                }
            }
            let value=self.comparison(&reply,absent)?;
            if action==FixtureAction::Retire {self.retired=Some(reply);}
            Ok(value)
        })();
        if let Err(error)=&result {if self.failure.is_none(){self.failure=Some(error.to_string());}}
        result
    }
    pub(crate) fn require_retired(&self)->Result<(),String> {
        if let Some(error)=&self.failure {return Err(format!("fixture actual transaction failed: {error}"));}
        self.retired.as_ref().ok_or("fixture was installed without its actual complete retirement")?;
        // The reply was validated while the actual request end was live. This
        // immutable historical fact does not renew or re-open that operation.
        Ok(())
    }
}
impl NativeApplicationInspector {
    fn fixture_request(&self,baseline:&NativeLeafBaselineObservation<'_>,request:&NativeFixtureRequest,end:Instant)
        ->Result<(NativeFixtureReply,File),ControlError>
    {
        baseline.verify_local(self,end)?;
        let stream=progress::connect(Path::new(DEFAULT_CONTROL_SOCKET)).map_err(|e|io_error("connect original fixed fixture owner",e))?;
        let peer=peer_credentials_checked(&stream)?;
        let fd=peer_pidfd(&stream).map_err(|e|io_error("capture actual fixture owner",e))?;
        let now=fd.metadata().map_err(|e|io_error("stat fixture owner",e))?;
        let original=self.pidfd.metadata().map_err(|e|io_error("stat original fixture owner",e))?;
        if peer.pid as u32!=self.peer_pid || (now.dev(),now.ino())!=(original.dev(),original.ino()) {
            return Err(ControlError::Invalid("fixture socket was replaced by another actual owner".into()));
        }
        baseline.verify_local(self,end)?;
        let result=progress::request_on_until(stream,&ControlRequest::NativeFixture{request:request.clone()},end);
        let after=(||{live(&fd).map_err(|e|io_error("fixture broker final bookend",e))?;baseline.verify_local(self,end)})();
        let response=match (result,after) {
            (Ok(v),Ok(()))=>v,(Err(e),Ok(()))=>return Err(e),(Ok(_),Err(e))=>return Err(e),
            (Err(e),Err(post))=>return Err(ControlError::Invalid(format!("{e}; fixture original custody postcheck also failed: {post}"))),
        };
        if !response.ok || response.state!=CellState::Running || response.host_pid!=Some(baseline.main().facts().epoch.cell_host_pid) {
            return Err(ControlError::Invalid(format!("actual fixture transaction failed; no automatic retry: {}",response.message)));
        }
        let body=response.diagnostics.ok_or_else(||ControlError::Invalid("actual fixture comparison is absent".into()))?;
        if body.len()>crate::native_leaf_fixture::MAX_RESPONSE_BYTES {
            return Err(ControlError::Invalid("complete fixture reply exceeds its source bound".into()));
        }
        Ok((serde_json::from_str(&body)?,fd))
    }
    pub(crate) fn begin_native_fixture_until(&self,baseline:&NativeLeafBaselineObservation<'_>,end:Instant)->Result<NativeFixtureObservation,ControlError> {
        baseline.verify_local(self,end)?;
        let route=baseline.owned_fixture_route()?.ok_or_else(||ControlError::Invalid("this actual business scope has no fixed fixture".into()))?;
        let request=NativeFixtureRequest::begin(baseline,route,end).map_err(ControlError::Invalid)?;
        let material=NativeLeafFixtureMaterial::capture_before(request.kind().map_err(ControlError::Invalid)?,baseline.deadline(),end)
            .map_err(|e|io_error("capture fixed normal fixture source",e))?;
        let original_absence=baseline.fixture_absent(request.kind().map_err(ControlError::Invalid)?)?;
        let (begin,peer)=self.fixture_request(baseline,&request,end)?;
        begin.validate(&request,None).map_err(ControlError::Invalid)?;
        material.guard(end).map_err(|e|io_error("fixture source final installation guard",e))?;
        baseline.verify_local(self,end)?;
        let data=crate::native_leaf_baseline_data::HeldLeafData::capture(baseline.main().facts(),begin.helper())
            .map_err(|e|io_error("capture actual newly installed helper CE/DE",e))?;
        Ok(NativeFixtureObservation{begin,peer,material,retired:None,failure:None,original_absence,data})
    }
}
