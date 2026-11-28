//! The parent's one normal preparation child, inside its original working end.
//! Reuse the physical owner's held ELF, credentialed socket, output custodian
//! and PIDFD retirement. Completion here prepares inputs; it grants no gate.
use super::*;
use super::super::preparation::{
    PREPARATION_CASE, PREPARATION_SUMMARY_LIMIT, PreparationReady, PreparationStart,
};
use crate::working_qualification::WorkingQualificationOwner;

pub(crate) struct PreparationHistory {
    stdout: SealedOutput,
    stderr: SealedOutput,
    plan: File,
    plan_identity: [u64; 9],
    plan_path: PathBuf,
    plan_sha256: String,
    child_pid: u32,
    child_pidfd: OwnedFd,
    child_start: u64,
    original_end_ns: u64,
    preparation_end_ns: u64,
}
impl PreparationHistory {
    pub(crate) fn guard(&self)->Result<(),String> {
        if !crate::development::owned_process::pidfd_exited(&self.child_pidfd).map_err(|e|e.to_string())? {
            return Err("retained preparation direct child is not retired".into());
        }
        self.stdout.guard().map_err(|e|e.to_string())?;
        self.stderr.guard().map_err(|e|e.to_string())?;
        let named=Plan::open(&self.plan_sha256).map_err(|e|e.to_string())?;
        if named.path!=self.plan_path || named.pin!=self.plan_identity
            || f9(&self.plan).map_err(|e|e.to_string())?!=self.plan_identity {
            return Err("retained preparation PLAN changed".into());
        }
        Ok(())
    }
    pub(crate) fn observation(&self)->Value {
        json!({"schema":"droidloom.working-preparation-history.v1",
            "actual_child_pid":self.child_pid,"actual_child_start_ticks":self.child_start,
            "actual_exit":0,"direct_child_reaped":true,"owned_descendants_absent":true,
            "original_end_monotonic_ns":self.original_end_ns,
            "preparation_end_monotonic_ns":self.preparation_end_ns,
            "stdout":self.stdout.observation(),"stderr":self.stderr.observation(),
            "plan":{"path":self.plan_path,"bytes":self.plan_identity[6],"sha256":self.plan_sha256},
            "restores_live_preparation_authority":false,"application_gate_credit":false})
    }
}
fn output(owner:&WorkingQualificationOwner,name:&str,limit:u64)->Result<Output,String> {
    let (file,path)=owner.preparation_output(name)?;
    Ok(Output{file,path,bytes:0,hash:Sha256::new(),limit,eof:false})
}
/// Parent API accepts only its actual opaque working owner, already published
/// by the normal applications source producer. No path/command/report selector.
pub fn capture_prepared_working_run(
    mut owner:WorkingQualificationOwner,
)->Result<CapturedCompleteApplicationRun,String> {
    let (end,wire_end)=owner.begin_preparation()?;
    let whole_end_ns=owner.source_origin().original_end_monotonic_ns;
    let mut stdout=output(&owner,"PREPARATION.stdout",PREPARATION_SUMMARY_LIMIT)?;
    let mut stderr=output(&owner,"PREPARATION.stderr",1024*1024)?;
    let (socket,child_socket)=socket::Socket::pair().map_err(|e|e.to_string())?;
    let inherited=unsafe{libc::fcntl(child_socket.file.as_raw_fd(),libc::F_DUPFD_CLOEXEC,64)};
    if inherited<0 {return Err(io::Error::last_os_error().to_string());}
    let inherited=unsafe{OwnedFd::from_raw_fd(inherited)};
    let parent_pid=std::process::id();
    let channel_fd=inherited.as_raw_fd();
    let watchdog=owner.close_in_child();
    let mut command=Command::new(format!("/proc/self/fd/{}",owner.unit().executable().as_raw_fd()));
    command.arg0(EXE).arg("--working-qualification-prepare")
        .stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped())
        .env_clear().env("PATH","/usr/sbin:/usr/bin:/sbin:/bin").env("LANG","C.UTF-8")
        .current_dir("/");
    // SAFETY: only fixed descriptor, prctl and LSM attribute operations before exec.
    unsafe {
        command.pre_exec(move||{
            if libc::prctl(libc::PR_SET_PDEATHSIG,libc::SIGKILL)!=0 {
                return Err(io::Error::last_os_error());
            }
            if libc::getppid() as u32!=parent_pid {return Err(error("working parent died before preparation exec"));}
            crate::working_qualification::child_exec::prepare(
                crate::working_qualification::child_exec::Kind::Preparation,watchdog)?;
            if libc::dup2(channel_fd,3)<0 || libc::fcntl(3,libc::F_SETFD,0)<0 {
                return Err(io::Error::last_os_error());
            }
            Ok(())
        });
    }
    let cleanup_end=owner.preparation_retirement_end()?;
    owner.guard_until(end)?;
    owner.unit().boundary(None,end)?;
    let mut spawned=command.spawn().map_err(|e|e.to_string())?;
    drop(inherited);drop(child_socket);
    let pid=spawned.id();
    let pidfd=match open_pidfd(pid) {
        Ok(v)=>v,
        Err(e)=>{
            let _=spawned.kill();
            let _=spawned.wait();
            return Err(format!("preparation direct child PIDFD: {e}"));
        }
    };
    let mut child=ChildOwner{child:spawned,pidfd,pid,reaped:None};
    let mut out_pipe=child.child.stdout.take();
    let mut err_pipe=child.child.stderr.take();
    let operation=(||->Result<(Plan,u64),String>{
        let mut out_pipe=out_pipe.as_mut().ok_or("preparation stdout pipe absent")?;
        let mut err_pipe=err_pipe.as_mut().ok_or("preparation stderr pipe absent")?;
        socket::nonblocking(out_pipe.as_raw_fd()).map_err(|e|e.to_string())?;
        socket::nonblocking(err_pipe.as_raw_fd()).map_err(|e|e.to_string())?;
        let bound=BoundProcess::capture(pid).map_err(|e|e.to_string())?;
        let mut sequence=0;
        let mut ready:Option<(PreparationReady,Plan)>=None;
        let mut acknowledged=false;
        loop {
            if Instant::now()>=end {return Err("preparation exhausted its one original phase end".into());}
            stdout.drain(&mut out_pipe).map_err(|e|e.to_string())?;
            stderr.drain(&mut err_pipe).map_err(|e|e.to_string())?;
            let status=child.try_wait().map_err(|e|e.to_string())?;
            if status.is_none() && !acknowledged {owner.pump(Some(&bound),end)?;}
            if status.is_none() && ready.is_none() && !acknowledged {
                if let Some(packet)=socket.try_receive(pid).map_err(|e|e.to_string())? {
                    packet.require_sequence(sequence).map_err(|e|e.to_string())?;
                    owner.unit().child_guard(&bound)?;
                    if packet.case!=PREPARATION_CASE {return Err("preparation request is not its fixed private stage".into());}
                    match (sequence,packet.kind) {
                        (0,1) if packet.end_ns==0 && packet.payload.is_empty()=>{
                            owner.unit().boundary(Some(&bound),end)?;
                            let start=PreparationStart{schema:"droidloom.working-preparation-start.v1".into(),
                                origin:owner.source_origin().clone(),
                                publication:owner.published_source().ok_or("initial source publication absent")?,
                                preparation_end_ns:wire_end};
                            socket.send(&socket::Packet{sequence:0,kind:5,case:PREPARATION_CASE,
                                end_ns:wire_end,payload:serde_json::to_vec(&start).map_err(|e|e.to_string())?},
                                end).map_err(|e|e.to_string())?;
                            sequence=1;
                        }
                        (1,4) if packet.end_ns==wire_end=>{
                            let value:PreparationReady=serde_json::from_slice(&packet.payload).map_err(|e|e.to_string())?;
                            if value.schema!="droidloom.working-preparation-ready.v1"
                                || value.plan_bytes==0 || value.plan_bytes>4*1024*1024
                                || !digest_ok(&value.plan_sha256)
                                || value.summary_bytes==0 || value.summary_bytes>PREPARATION_SUMMARY_LIMIT
                                || !digest_ok(&value.summary_sha256) {
                                return Err("preparation complete file commitment differs".into());
                            }
                            value.binding.validate(&owner.main().facts().epoch)?;
                            owner.compare_physical_binding(&value.binding)?;
                            let plan=Plan::open(&value.plan_sha256).map_err(|e|e.to_string())?;
                            if plan.pin[6]!=value.plan_bytes {return Err("preparation PLAN size differs".into());}
                            ready=Some((value,plan));
                        }
                        _=>return Err("preparation requested a reordered, replayed or foreign operation".into()),
                    }
                }
            }
            if let Some((value,plan))=ready.as_ref() {
                if stdout.bytes>value.summary_bytes {return Err("preparation stdout has an uncommitted suffix".into());}
                if stdout.bytes==value.summary_bytes && !acknowledged {
                    if stdout.digest()!=value.summary_sha256 || stderr.bytes!=0 {
                        return Err("preparation complete stdout or stderr differs".into());
                    }
                    let mut bytes=vec![0;stdout.bytes as usize];
                    stdout.file.read_exact_at(&mut bytes,0).map_err(|e|e.to_string())?;
                    let summary:Value=serde_json::from_slice(&bytes).map_err(|e|e.to_string())?;
                    let expected=json!({"schema":"droidloom.working-preparation-produced.v1",
                        "plan":{"path":plan.path,"bytes":plan.pin[6],"sha256":plan.digest},
                        "source_publication":owner.published_source(),
                        "actual_epoch":owner.main().facts().epoch,
                        "original_end_monotonic_ns":whole_end_ns,"preparation_end_monotonic_ns":wire_end,
                        "stage_directory":format!("/var/lib/droidloom-qualification/working-preparation-{}",
                            owner.source_origin().unit.invocation),
                        "application_gate_credit":false,"production_ready":false});
                    if summary!=expected || !bytes.ends_with(b"\n") {
                        return Err("preparation stdout is not this original source/Main/PLAN comparison".into());
                    }
                    owner.guard_local(Some(&bound),end)?;
                    owner.unit().boundary(Some(&bound),end)?;
                    plan.guard().map_err(|e|e.to_string())?;
                    socket.send(&socket::Packet{sequence:1,kind:5,case:PREPARATION_CASE,
                        end_ns:wire_end,payload:Vec::new()},end).map_err(|e|e.to_string())?;
                    acknowledged=true;
                }
            }
            if let Some(status)=status {
                stdout.drain(&mut out_pipe).map_err(|e|e.to_string())?;
                stderr.drain(&mut err_pipe).map_err(|e|e.to_string())?;
                if !status.success() || !acknowledged || !stdout.eof || !stderr.eof || stderr.bytes!=0 {
                    return Err(format!("actual preparation producer incomplete: exit={status}, acknowledged={acknowledged}"));
                }
                let (value,plan)=ready.take().ok_or("normal preparation completion absent")?;
                if stdout.bytes!=value.summary_bytes || stdout.digest()!=value.summary_sha256 {
                    return Err("preparation stdout changed after acknowledgement".into());
                }
                owner.unit().boundary(None,end)?;
                plan.guard().map_err(|e|e.to_string())?;
                return Ok((plan,bound.identity.start_ticks));
            }
            std::thread::sleep(Duration::from_millis(5));
        }
    })();
    let (plan,child_start)=match operation {
        Ok(v)=>v,
        Err(reason)=>{
            let retirement=child.stop(cleanup_end);
            if let Some(pipe)=out_pipe.as_mut() {let _=stdout.drain(pipe);}
            if let Some(pipe)=err_pipe.as_mut() {let _=stderr.drain(pipe);}
            let nested=if retirement.is_ok(){owner.unit().boundary(None,cleanup_end)}else{Err("direct preparation child retirement failed".into())};
            let sealed_out=stdout.seal();
            let sealed_err=stderr.seal();
            let actual_exit=child.reaped.and_then(|s|s.code());
            let record=json!({"schema":"droidloom.working-preparation-failed.v1",
                "reason":reason,"actual_exit":actual_exit,"direct_child_reaped":child.reaped.is_some(),
                "direct_retirement_error":retirement.as_ref().err().map(ToString::to_string),
                "descendant_retirement_error":nested.as_ref().err(),
                "stdout":sealed_out.as_ref().ok().map(SealedOutput::observation),
                "stderr":sealed_err.as_ref().ok().map(SealedOutput::observation),
                "stdout_seal_error":sealed_out.as_ref().err().map(ToString::to_string),
                "stderr_seal_error":sealed_err.as_ref().err().map(ToString::to_string),
                "source_publication_already_committed":true,"automatic_retry":false,
                "application_gate_credit":false,"production_ready":false});
            let result=owner.record_preparation(&record);
            let failed=owner.record_failure(&reason);
            return Err(format!("{reason}; preparation retirement={retirement:?}; descendants={nested:?}; record={result:?}; owner={failed:?}"));
        }
    };
    let history=PreparationHistory{
        stdout:stdout.seal().map_err(|e|e.to_string())?,
        stderr:stderr.seal().map_err(|e|e.to_string())?,
        plan:plan.file.try_clone().map_err(|e|e.to_string())?,
        plan_identity:plan.pin,plan_path:plan.path.clone(),plan_sha256:plan.digest.clone(),
        child_pid:pid,child_pidfd:child.pidfd.try_clone().map_err(|e|e.to_string())?,
        child_start,original_end_ns:whole_end_ns,preparation_end_ns:wire_end};
    history.guard()?;
    owner.record_preparation(&history.observation())?;
    owner.finish_preparation(history,end)?;
    capture_working_physical_run(plan,owner)
}
