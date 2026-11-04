#!/usr/bin/env python3
"""Run the actual LMKD no-scan guard from candidate and baseline source.

Only the guard is extracted. OS I/O and process selection are not performed;
selection has a separate unchanged-AOSP test and the owned Android trial.
The baseline must reproduce the guarded-off true-pressure defect at runtime,
not fail to compile. Inputs have the same names/types used by the source block.
"""
import argparse,hashlib,json,pathlib,subprocess

parser=argparse.ArgumentParser()
parser.add_argument('--source',type=pathlib.Path,required=True)
parser.add_argument('--baseline',type=pathlib.Path,required=True)
parser.add_argument('--out-dir',type=pathlib.Path,required=True)
args=parser.parse_args()
args.out_dir.mkdir(parents=True,exist_ok=False)

prefix=r'''
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#define ALOGI(...) ((void)0)
enum {PSI=0,VENDOR=1,VMPRESS_LEVEL_MEDIUM=1,VMPRESS_LEVEL_CRITICAL=2};
enum {NO_RECLAIM,DIRECT_RECLAIM,KSWAPD_RECLAIM};
struct Snapshot {bool high_throttling_progressed;uint64_t current,high,high_events;};
static long get_time_diff_ms(const int*,const int*) {return 0;}
static bool passed(bool cell_memory_enabled,bool progressed,int source,int level,int events,
                   bool in_direct_reclaim=false,bool in_kswapd_reclaim=false,bool refault=false) {
 Snapshot cell_memory_snapshot{progressed,442388480,402653184,153};
 struct {struct {int pgscan_direct,pgscan_kswapd,pgrefill;} field;} vs{{0,0,0}};
 int init_pgscan_direct=0,init_pgscan_kswapd=0,init_pgrefill=0;
 int direct_reclaim_start_tm=0,curr_tm=0,reclaim=NO_RECLAIM;
 long direct_reclaim_duration_ms=0;
 int workingset_refault_file=refault?1:0,prev_workingset_refault=0;
'''
suffix=r'''
 (void)init_pgscan_direct;(void)init_pgscan_kswapd;(void)init_pgrefill;
 (void)direct_reclaim_duration_ms;(void)reclaim;(void)cell_memory_enabled;
 (void)cell_memory_snapshot;(void)level;(void)events;
 return true;
no_kill:
 return false;
}
static int tests;
static void require(bool ok,const char* label) {
 if(!ok){std::fprintf(stderr,"FAIL %s\n",label);std::exit(2);}
 ++tests;std::printf("PASS %s\n",label);
}
int main(){
 require(!passed(false,true,PSI,VMPRESS_LEVEL_CRITICAL,1),"host mode gets no cell exception");
 require(!passed(true,false,PSI,VMPRESS_LEVEL_CRITICAL,1),"historical or absent high event cannot bypass guard");
 require(!passed(true,true,PSI,VMPRESS_LEVEL_CRITICAL,0),"polling cannot turn old PSI into critical notification");
 require(!passed(true,true,PSI,VMPRESS_LEVEL_MEDIUM,1),"partial PSI retains original no-scan guard");
 require(!passed(true,true,PSI,0,1),"low PSI retains original no-scan guard");
 require(passed(true,false,PSI,VMPRESS_LEVEL_MEDIUM,1,true),"real direct reclaim remains on original path");
 require(passed(true,false,PSI,VMPRESS_LEVEL_MEDIUM,1,false,true),"real kswapd reclaim remains on original path");
 require(passed(true,false,PSI,VMPRESS_LEVEL_MEDIUM,1,false,false,true),"real refault remains on original path");
 require(passed(false,false,VENDOR,VMPRESS_LEVEL_MEDIUM,1),"vendor path unchanged");
 require(passed(true,true,PSI,VMPRESS_LEVEL_CRITICAL,1),"current high throttling and actual critical PSI reach existing policy");
 std::printf("RESULT %d passed\n",tests);
}
'''

results={}
for label,path in [('baseline',args.baseline),('candidate',args.source)]:
    source=path.read_text()
    begin=source.index('    /* Identify reclaim state */')
    end=source.index('    prev_workingset_refault = workingset_refault_file;',begin)
    block=source[begin:end]
    cpp=args.out_dir/(label+'.cpp');exe=args.out_dir/label
    cpp.write_text(prefix+block+suffix)
    command=['c++','-std=c++17','-O2','-Wall','-Wextra','-Werror',str(cpp),'-o',str(exe)]
    compile_result=subprocess.run(command,capture_output=True,text=True)
    if compile_result.returncode:
        raise RuntimeError(label+' compile failed: '+compile_result.stderr)
    run=subprocess.run([str(exe)],capture_output=True,text=True)
    results[label]={'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
      'guard_sha256':hashlib.sha256(block.encode()).hexdigest(),
      'compile_rc':compile_result.returncode,'run_rc':run.returncode,
      'stdout':run.stdout,'stderr':run.stderr}
    print(label+': '+run.stdout+run.stderr,end='')
assert results['baseline']['run_rc']==2,results
assert results['baseline']['stderr']=='FAIL current high throttling and actual critical PSI reach existing policy\n',results
assert results['candidate']['run_rc']==0,results
results['scope']='compiled actual source guard; fake inputs; no real process effects'
results['pass']=True
(args.out_dir/'result.json').write_text(json.dumps(results,indent=2)+'\n')
