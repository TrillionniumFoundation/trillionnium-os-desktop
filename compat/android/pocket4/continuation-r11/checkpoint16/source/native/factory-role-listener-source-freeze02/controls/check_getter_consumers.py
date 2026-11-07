#!/usr/bin/env python3
"""Local exact-source callsite error controls; authority/getters are explicit seams."""
from pathlib import Path
import hashlib,json,subprocess,time
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'local-getter-errors01'

def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def segment(text,start,end):
    if text.count(start)!=1:raise RuntimeError('non-unique function start')
    a=text.index(start);b=text.index(end,a)
    return text[a:b],{'start_byte':a,'end_byte':b,**pin(text[a:b].encode())}

OUT.mkdir(mode=0o700)
inputs={};blocks={};segments={}
for arm in ['preimage','candidate']:
    ss=(ROOT/arm/'source/role_session.cc').read_bytes();ad=(ROOT/arm/'source/role_admission.cc').read_bytes()
    inputs[arm]={'role_session.cc':pin(ss),'role_admission.cc':pin(ad)}
    sw,swpin=segment(ss.decode(),'int Wait(Registry&','int Send(')
    dp,dppin=segment(ss.decode(),'int DispatchOne(Registry&','  Received received;')
    check,chpin=segment(ad.decode(),'int Check(Registry&','int Wait(Registry&')
    aw,awpin=segment(ad.decode(),'int Wait(Registry&','int CloseError(')
    segments[arm]={'session_Wait_full':swpin,'DispatchOne_prefix_before_Received':dppin,'admission_Check_full':chpin,'admission_Wait_full':awpin}
    blocks[arm]=(f'namespace {arm}_session {{\nusing namespace fixture;\n'+sw+dp+
                 '  (void)deadline; (void)previous; return 777;\n}\n}\n'+
                 f'namespace {arm}_admission {{\nusing namespace fixture;\n'+check+aw+'}\n')
source=r'''#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>
#include <sys/eventfd.h>
#include <sys/syscall.h>
#include <stdexcept>
#include <string>
namespace fixture {
constexpr uint64_t kSessionRequestNanos=2000000000ULL;
constexpr short kDead=POLLERR|POLLHUP|POLLNVAL|POLLRDHUP;
struct GrantHandle{unsigned slot=0;uint64_t serial=1;};
struct DispatchResult{};
int Error(int error){errno=error;return -1;}
uint64_t Now(){timespec t{};if(clock_gettime(CLOCK_MONOTONIC,&t)<0)return 0;return uint64_t(t.tv_sec)*1000000000ULL+uint64_t(t.tv_nsec);}
int TimeRemaining(uint64_t deadline,uint64_t* previous){const uint64_t n=Now();if(!n||n<*previous)return Error(EIO);*previous=n;return n<deadline?0:Error(ETIMEDOUT);}
// Explicit authority and getter seams. poll uses real owned kernel descriptors.
struct OwnerLease {
 int control,pidfd,fail_control,fail_pidfd;
 mutable unsigned control_calls=0,pidfd_calls=0,verifies=0;
 int Verify()const{++verifies;errno=0;return 0;}
 int control_fd()const{++control_calls;if(fail_control)return Error(fail_control);errno=EUCLEAN;return control;}
 int owner_pidfd()const{++pidfd_calls;if(fail_pidfd)return Error(fail_pidfd);errno=EUCLEAN;return pidfd;}
};
struct Registry {
 int connection;unsigned closes=0;
 int Sweep(){return 0;}int IsActive(GrantHandle){return 0;}
 int Connection(GrantHandle){return connection;}
 void Close(GrantHandle){++closes;errno=EBUSY;}
};
int CloseError(Registry& registry,GrantHandle handle,int error){registry.Close(handle);return Error(error>0&&error<=4095?error:EIO);}
void Need(bool value,const char* reason){if(!value)throw std::runtime_error(reason);}
}
'''+blocks['preimage']+blocks['candidate']+r'''
int main(){
 using namespace fixture;
 int pipes[2];Need(pipe2(pipes,O_NONBLOCK|O_CLOEXEC)==0,"own readiness pipe");
 const int control=eventfd(0,EFD_CLOEXEC|EFD_NONBLOCK),pidfd=static_cast<int>(syscall(SYS_pidfd_open,getpid(),0));
 Need(control>=0&&pidfd>=0,"own quiet event and live PIDFD");
 Need(write(pipes[1],"x",1)==1,"real readiness");
 unsigned comparisons=0,original_defects=0;
 for(int site=0;site<3;++site)for(int fail=0;fail<3;++fail){
  int observed_rc[2]{},observed_error[2]{};unsigned calls[2][3]{};
  for(int arm=0;arm<2;++arm){
   Registry registry{pipes[0]};OwnerLease owner{control,pidfd,fail==1?EMFILE:0,fail==2?EINTR:0};
   GrantHandle handle{};DispatchResult output{};uint64_t previous=Now(),deadline=previous+kSessionRequestNanos;
   errno=0;int rc;
   if(site==0)rc=arm?candidate_session::Wait(registry,handle,owner,pipes[0],POLLIN,deadline,&previous,true):preimage_session::Wait(registry,handle,owner,pipes[0],POLLIN,deadline,&previous,true);
   else if(site==1)rc=arm?candidate_session::DispatchOne(registry,handle,owner,&output):preimage_session::DispatchOne(registry,handle,owner,&output);
   else rc=arm?candidate_admission::Wait(registry,owner,pipes[0],POLLIN,deadline,&previous):preimage_admission::Wait(registry,owner,pipes[0],POLLIN,deadline,&previous);
   observed_rc[arm]=rc;observed_error[arm]=errno;calls[arm][0]=owner.control_calls;calls[arm][1]=owner.pidfd_calls;calls[arm][2]=registry.closes;
   if(!fail){Need(rc==(site==1?777:0),"positive reaches original next point");Need(owner.control_calls==1&&owner.pidfd_calls==1&&!registry.closes,"positive exact getter count");}
   else if(arm){
    Need(rc==-1&&errno==(fail==1?EMFILE:EINTR),"candidate retains first getter error");
    Need(owner.control_calls==1&&owner.pidfd_calls==(fail==1?0U:1U),"candidate never evaluates later getter after failure");
    Need(registry.closes==(site==1?1U:0U),"candidate Dispatch closes before receive");
   }else{
    Need(owner.control_calls==1&&owner.pidfd_calls==1&&!registry.closes,"original consumes both getters and does not close");
    if(site<2){Need(rc==(site==1?777:0),"original failure swallowed before continuation");++original_defects;}
    else if(fail==1){Need(rc==-1&&errno==EUCLEAN,"original first error overwritten by later successful getter");++original_defects;}
    else Need(rc==-1&&errno==EINTR,"unchanged original second getter rejection");
   }
  }
  printf("{\"site\":%d,\"fault\":%d,\"original_rc\":%d,\"original_errno\":%d,\"candidate_rc\":%d,\"candidate_errno\":%d,\"original_getters_and_close\":[%u,%u,%u],\"candidate_getters_and_close\":[%u,%u,%u]}\n",site,fail,observed_rc[0],observed_error[0],observed_rc[1],observed_error[1],calls[0][0],calls[0][1],calls[0][2],calls[1][0],calls[1][1],calls[1][2]);
  ++comparisons;
 }
 Need(comparisons==9&&original_defects==5,"exact five original error-path defects observed");
 Need(close(pipes[0])==0&&close(pipes[1])==0&&close(control)==0&&close(pidfd)==0,"close exact owned controls");
 printf("{\"state\":\"PASS_BOUND_CALLSITE_ERROR_CONTROLS\",\"comparisons\":9,\"original_defects\":5,\"authority_and_getters\":\"explicit_seam\",\"poll\":\"actual_owned_kernel_descriptors\",\"production_authorization_executed\":false}\n");
}
'''
(OUT/'bound_callsites.cc').write_text(source)
compiler=Path('/usr/bin/x86_64-linux-gnu-g++-13');compiler_before=pin(compiler.read_bytes());records=[]
report={'schema':1,'state':'FAIL','inputs':inputs,'source_segments':segments,'compiler':{'path':str(compiler),**compiler_before},'commands':records,'authority_and_getter_calls_are_explicit_seams':True,'actual_poll_and_own_descriptors':True,'DispatchOne_scope':'exact prefix until before Received; continuation sentinel 777 is test-only','root_execution':False,'Android_execution':False,'Main_actions':0}
try:
 for name,argv in [('compile',[str(compiler),'-std=c++17','-O2','-Wall','-Wextra','-Werror',str(OUT/'bound_callsites.cc'),'-o',str(OUT/'bound_callsites')]),('run',[str(OUT/'bound_callsites')])]:
  start=time.monotonic();r=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
  (OUT/(name+'.stdout')).write_bytes(r.stdout);(OUT/(name+'.stderr')).write_bytes(r.stderr)
  records.append({'name':name,'argv':argv,'returncode':r.returncode,'seconds':time.monotonic()-start,'stdout':pin(r.stdout),'stderr':pin(r.stderr)})
  if r.returncode:raise RuntimeError(name+' failed')
 report['state']='PASS_BOUND_CALLSITE_ERROR_CONTROLS';report['error']=None
except BaseException as error:report['error']=repr(error)
finally:
 report['compiler_unchanged']=pin(compiler.read_bytes())==compiler_before
 report['source_unchanged']=all(pin((ROOT/arm/'source'/name).read_bytes())==meta for arm,rows in inputs.items()for name,meta in rows.items())
 if not report['compiler_unchanged']or not report['source_unchanged']:report['state']='FAIL'
 report['bound_source']=pin((OUT/'bound_callsites.cc').read_bytes())
 (OUT/'result.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
 print(json.dumps({'state':report['state'],'result':str(OUT/'result.json'),**pin((OUT/'result.json').read_bytes())}))
 if report['state']=='FAIL':
  print((OUT/'compile.stderr').read_text())
  if (OUT/'run.stderr').exists():print((OUT/'run.stderr').read_text())
  raise SystemExit(1)
