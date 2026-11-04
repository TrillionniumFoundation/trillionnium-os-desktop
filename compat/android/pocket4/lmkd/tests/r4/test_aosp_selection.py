#!/usr/bin/env python3
"""Compile selected, byte-identical AOSP functions with owned fake process I/O.
No OS process is registered, signalled, or assigned an oom_score_adj by this test.
"""
import argparse,pathlib,re,subprocess,json,hashlib
parser=argparse.ArgumentParser()
parser.add_argument('--source',type=pathlib.Path,required=True)
parser.add_argument('--upstream',type=pathlib.Path,required=True)
parser.add_argument('--out-dir',type=pathlib.Path,required=True)
args=parser.parse_args()
p=args.out_dir.resolve();p.mkdir(parents=True,exist_ok=False)
old=args.upstream.read_text()
new=args.source.read_text()
def function(text,name):
 m=re.search(r'(?:static )?(?:int|bool|void|char \*|struct proc\s*\*)\s+'+name+r'\s*\(',text)
 assert m,name
 start=m.start(); brace=text.index('{',m.end());depth=1;i=brace+1
 while depth:
  if text[i]=='{':depth+=1
  elif text[i]=='}':depth-=1
  i+=1
 return text[start:i]
names=['find_and_kill_process','apply_proc_prio','register_oom_adj_proc','kill_one_process','watchdog_callback','claim_record']
identity={}
for name in names:
 a,b=function(old,name),function(new,name)
 assert a==b, name+' drifted'
 identity[name]=hashlib.sha256(a.encode()).hexdigest()
prefix=r'''
#define _GNU_SOURCE 1
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <sys/socket.h>
#include <ctime>
#include <vector>
#define OOM_SCORE_ADJ_MAX 1000
#define OOM_SCORE_ADJ_MIN -1000
#define PERCEPTIBLE_APP_ADJ 200
#define PROCFS_PATH_MAX 128
#define PROC_STATUS_TGID_FIELD "Tgid:"
#define ALOGE(...) ((void)0)
#define ALOGW(...) ((void)0)
struct proc {int pid, oomadj, rss; bool stale=false;};
struct kill_info {}; union meminfo {int unused;};
struct wakeup_info {}; struct psi_data {};
static bool kill_heaviest_task=false, use_inkernel_interface=false;
static std::vector<proc> fixtures;
static int killed=-1;
static proc* proc_adj_tail(int score) {
 for (auto& p:fixtures) if(p.oomadj==score)return &p;
 return nullptr;
}
static proc* proc_get_heaviest(int score) {
 proc* selected=nullptr;
 for (auto& p:fixtures)if(p.oomadj==score&&(!selected||p.rss>selected->rss))selected=&p;
 return selected;
}
static int kill_one_process(proc* p,int,kill_info*,meminfo*,wakeup_info*,timespec*,psi_data*) {
 if(p->stale){p->oomadj=-1001;return -1;}
 killed=p->pid;return p->rss;
}
enum {PROC_TYPE_FIRST=0,PROC_TYPE_APP=0,PROC_TYPE_SERVICE=1,PROC_TYPE_COUNT=2};
struct lmk_procprio {int pid,uid,oomadj,ptype;bool for_lmkd_only;};
static int pagesize=4096,writes=0,registrations=0;
static int64_t fixture_tgid=123;
static bool writable=true;
static std::string score;
static bool read_proc_status(int,char*,size_t){return true;}
static bool parse_status_tag(char*,const char*,int64_t* out){*out=fixture_tgid;return true;}
static bool writefilestring(const char*,const char* value,bool){++writes;score=value;return writable;}
static void stats_store_taskname(int,char*){}
static char* proc_get_name(int,char* out,size_t){return out;}
static void register_oom_adj_proc(const lmk_procprio&,ucred*){++registrations;}
'''
main=r'''
static int tests;
static void require(bool ok,const char* name){
 if(!ok){std::fprintf(stderr,"FAIL %s\n",name);std::exit(2);}
 ++tests;std::printf("PASS %s\n",name);
}
static int choose(int min_score){
 killed=-1;find_and_kill_process(min_score,nullptr,nullptr,nullptr,nullptr,nullptr);return killed;
}
int main(){
 fixtures={{1,0,2000},{2,100,1000},{3,900,10},{4,-1000,8000}};
 require(choose(0)==3,"small cached process chosen before large foreground/protected");
 fixtures={{1,0,2000},{2,100,1000},{4,-1000,8000}};
 require(choose(701)==-1,"no eligible cached process causes no action");
 fixtures={{4,-1000,8000},{5,-100,1000}};
 require(choose(0)==-1,"negative-adj protected processes excluded");
 fixtures={{1,900,5,true},{2,900,7}};
 require(choose(0)==2,"stale record skipped");
 fixtures={{1,900,5},{2,900,7}};kill_heaviest_task=true;
 require(choose(0)==2,"heaviest selection confined to equal adj");
 fixtures={{1,100,2000},{2,900,7}};kill_heaviest_task=true;
 require(choose(0)==2,"heaviest flag still respects importance");
 lmk_procprio params{123,10001,900,PROC_TYPE_APP,false};ucred cred{};
 writes=registrations=0;apply_proc_prio(params,&cred);
 require(writes==1&&registrations==1&&score=="900","valid score written and registered");
 for(int adj:{-1001,1001}){
  params.oomadj=adj;writes=registrations=0;apply_proc_prio(params,&cred);
  require(writes==0&&registrations==0,"out-of-range score rejected");
 }
 params.oomadj=-1000;writes=registrations=0;apply_proc_prio(params,&cred);
 require(writes==1&&registrations==1&&score=="-1000","valid protected score retained");
 params.oomadj=1000;writes=registrations=0;apply_proc_prio(params,&cred);
 require(writes==1&&registrations==1&&score=="1000","valid upper score retained");
 params.ptype=PROC_TYPE_COUNT;writes=registrations=0;apply_proc_prio(params,&cred);
 require(writes==0&&registrations==0,"invalid process type rejected");
 params.ptype=PROC_TYPE_APP;fixture_tgid=124;writes=registrations=0;apply_proc_prio(params,&cred);
 require(writes==0&&registrations==0,"nonleader pid rejected");
 fixture_tgid=123;writable=false;writes=registrations=0;apply_proc_prio(params,&cred);
 require(writes==1&&registrations==0,"failed kernel score write cannot register success");
 writable=true;params.for_lmkd_only=true;writes=registrations=0;apply_proc_prio(params,&cred);
 require(writes==0&&registrations==1,"AOSP lmkd-only priority contract retained");
 std::printf("RESULT %d passed\n",tests);
}
'''
extract=function(new,'find_and_kill_process')+'\n'+function(new,'apply_proc_prio')
path=p/'owned_selection_fixture.cpp'
path.write_text(prefix+extract+main)
cmd=['c++','-std=gnu++17','-Wall','-Wextra','-Werror','-O2',str(path),'-o',str(p/'owned_selection_fixture')]
build=subprocess.run(cmd,capture_output=True,text=True)
if build.returncode: print(build.stderr);raise SystemExit(build.returncode)
test=subprocess.run([str(p/'owned_selection_fixture')],capture_output=True,text=True)
print(test.stdout,end='')
print(test.stderr,end='')
report={'scope':'host unit fixture only; I/O fakes; no real process effects','upstream_commit':'c3601e823bd07c9c190f67e2f9bc7486e4978328','unchanged_function_sha256':identity,'build_rc':build.returncode,'test_rc':test.returncode,'stdout':test.stdout}
(p/'selection-tests-result.json').write_text(json.dumps(report,indent=2)+'\n')
raise SystemExit(test.returncode)

