#!/usr/bin/env python3
# Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
"""Freeze the r4 high-evidence consumption defect using its real Reader.

The production Reader and actual LMKD no-scan block are compiled unchanged.
Descriptor I/O is supplied by the existing isolated Reader fixture; no live
cgroup or Android process is involved. Both intermediate wakeup sequences
must compile and reproduce the expected final assertion failure.
"""
import argparse,hashlib,json,pathlib,subprocess

p=argparse.ArgumentParser()
p.add_argument('--source-dir',type=pathlib.Path,required=True)
p.add_argument('--reader-fixture',type=pathlib.Path,required=True)
p.add_argument('--out-dir',type=pathlib.Path,required=True)
a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=False)
source=(a.source_dir/'lmkd.cpp').read_text()
begin=source.index('    /* Identify reclaim state */')
end=source.index('    prev_workingset_refault = workingset_refault_file;',begin)
guard=source[begin:end]
reader=a.reader_fixture.read_text().split('int main() {',1)[0]
prefix=r'''
#include <cinttypes>
#define ALOGI(...) ((void)0)
enum {PSI=0,VENDOR=1,VMPRESS_LEVEL_MEDIUM=1,VMPRESS_LEVEL_CRITICAL=2};
enum {NO_RECLAIM,DIRECT_RECLAIM,KSWAPD_RECLAIM};
static long get_time_diff_ms(const int*,const int*) {return 0;}
static bool reaches_policy(const Snapshot& cell_memory_snapshot,int level,int events) {
 bool cell_memory_enabled=true;int source=PSI;
 bool in_direct_reclaim=false,in_kswapd_reclaim=false;
 struct {struct {int pgscan_direct,pgscan_kswapd,pgrefill;} field;} vs{{0,0,0}};
 int init_pgscan_direct=0,init_pgscan_kswapd=0,init_pgrefill=0;
 int direct_reclaim_start_tm=0,curr_tm=0,reclaim=NO_RECLAIM;
 long direct_reclaim_duration_ms=0;
 int workingset_refault_file=0,prev_workingset_refault=0;
'''
suffix=r'''
 (void)init_pgscan_direct;(void)init_pgscan_kswapd;(void)init_pgrefill;
 (void)direct_reclaim_duration_ms;(void)reclaim;
 return true;
no_kill:
 return false;
}
int main(int argc,char** argv) {
 require(argc==2,"sequence argument");
 bool polling=std::string(argv[1])=="poll";
 reset();Reader r;Snapshot s{};
 require(r.Open("/owned-cell")&&r.Read(&s),"real reader cold baseline");
 require(!s.high_throttling_progressed&&!reaches_policy(s,VMPRESS_LEVEL_CRITICAL,1),
         "old cumulative high count cannot activate critical decision");
 events(51);
 require(r.Read(&s)&&s.high_throttling_progressed&&s.current>s.high,
         "new high observation above unchanged finite limit");
 require(!reaches_policy(s,polling?VMPRESS_LEVEL_CRITICAL:VMPRESS_LEVEL_MEDIUM,polling?0:1),
         "intermediate wakeup preserves true critical notification gate");
 require(r.Read(&s)&&s.high_events==51&&s.current>s.high,
         "critical notification reads same current count and unchanged budget");
 require(reaches_policy(s,VMPRESS_LEVEL_CRITICAL,1),
         "fresh high observation survives intermediate wakeup until critical decision");
 std::printf("RESULT sequence passed\n");
}
'''
cpp=a.out_dir/'actual_reader_sequence.cpp';exe=a.out_dir/'actual-reader-sequence'
cpp.write_text(reader+prefix+guard+suffix)
cmd=['c++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I',str(a.source_dir),
     str(a.source_dir/'memory_cgroup.cpp'),str(cpp),
     '-Wl,--wrap=open,--wrap=openat,--wrap=fstatfs,--wrap=pread,--wrap=close','-o',str(exe)]
build=subprocess.run(cmd,capture_output=True,text=True)
assert build.returncode==0,build.stderr
results={}
for label in ('medium','poll'):
    r=subprocess.run([str(exe),label],capture_output=True,text=True)
    results[label]={'rc':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
    assert r.returncode==2,results
    assert r.stderr=='FAIL fresh high observation survives intermediate wakeup until critical decision\n',results
    print(label+': '+r.stdout+r.stderr,end='')
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
report={'scope':'actual Reader and actual no-scan block; descriptor I/O substitutes; no live pressure',
        'compile_rc':build.returncode,'source_sha256':{n:sha(a.source_dir/n) for n in ['lmkd.cpp','memory_cgroup.cpp','memory_cgroup.h']},
        'reader_fixture_sha256':sha(a.reader_fixture),'guard_sha256':hashlib.sha256(guard.encode()).hexdigest(),
        'sequences':results,'r4_regression_confirmed':True,'production_ready':False}
(a.out_dir/'result.json').write_text(json.dumps(report,indent=2)+'\n')
