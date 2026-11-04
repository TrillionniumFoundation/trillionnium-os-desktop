#!/usr/bin/env python3
# Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
"""Compare actual Reader + actual critical-consume/guard source across r4/r5.

Only descriptor/clock I/O is substituted. The r4 executable must compile and
fail the concrete intermediate-wakeup assertion; r5 must pass the same arms.
"""
import argparse, hashlib, json, pathlib, subprocess

p = argparse.ArgumentParser()
p.add_argument('--source-dir', type=pathlib.Path, required=True)
p.add_argument('--baseline-dir', type=pathlib.Path, required=True)
p.add_argument('--reader-fixture', type=pathlib.Path, required=True)
p.add_argument('--out-dir', type=pathlib.Path, required=True)
a = p.parse_args()
a.out_dir.mkdir(parents=True, exist_ok=False)
reader = a.reader_fixture.read_text().split('int main() {', 1)[0]
prefix = r'''
#include <cinttypes>
#include <time.h>
#define ALOGI(...) ((void)0)
enum {PSI=0,VENDOR=1,VMPRESS_LEVEL_MEDIUM=1,VMPRESS_LEVEL_CRITICAL=2};
enum {NO_RECLAIM,DIRECT_RECLAIM,KSWAPD_RECLAIM};
static int64_t fake_ms=1000;
extern "C" int __wrap_clock_gettime(clockid_t clock,timespec* out) {
 if(clock!=CLOCK_MONOTONIC){errno=EIO;return -1;}
 *out={fake_ms/1000,(fake_ms%1000)*1000000};return 0;
}
static long get_time_diff_ms(const int*,const int*) {return 0;}
static bool read_snapshot(Reader& r,Snapshot& s) {
#ifdef PENDING_API
 return r.Read(&s,1000);
#else
 return r.Read(&s);
#endif
}
static bool reaches_policy(Reader& cell_memory_reader,const Snapshot& cell_memory_snapshot,
                           int level,int events,int source=PSI,bool in_direct_reclaim=false,
                           bool in_kswapd_reclaim=false,bool refault=false,
                           bool cell_memory_enabled=true) {
 const int psi_window_size_ms=1000;
 bool cell_high_evidence=false;
 struct {struct {int pgscan_direct,pgscan_kswapd,pgrefill;} field;} vs{{0,0,0}};
 int init_pgscan_direct=0,init_pgscan_kswapd=0,init_pgrefill=0;
 int direct_reclaim_start_tm=0,curr_tm=0,reclaim=NO_RECLAIM;
 long direct_reclaim_duration_ms=0;
 int workingset_refault_file=refault?1:0,prev_workingset_refault=0;
'''
suffix = r'''
 (void)init_pgscan_direct;(void)init_pgscan_kswapd;(void)init_pgrefill;
 (void)direct_reclaim_duration_ms;(void)reclaim;(void)cell_memory_reader;
 (void)cell_memory_snapshot;(void)psi_window_size_ms;(void)cell_high_evidence;
 return true;
no_kill:
 return false;
}
int main(int argc,char** argv) {
 require(argc==2,"sequence argument");
 bool polling=std::string(argv[1])=="poll";
 reset();Reader r;Snapshot s{};
 require(r.Open("/owned-cell")&&read_snapshot(r,s),"real reader cold baseline");
 require(!s.high_throttling_progressed&&!reaches_policy(r,s,VMPRESS_LEVEL_CRITICAL,1),
         "old cumulative high count cannot activate critical decision");
 events(51);fake_ms=1100;
 require(read_snapshot(r,s)&&s.high_throttling_progressed&&s.current>s.high,
         "new high observation above unchanged finite limit");
 require(!reaches_policy(r,s,polling?VMPRESS_LEVEL_CRITICAL:VMPRESS_LEVEL_MEDIUM,polling?0:1),
         "intermediate wakeup preserves true critical notification gate");
 fake_ms=1200;
 require(read_snapshot(r,s)&&s.high_events==51&&s.current>s.high,
         "critical notification reads same current count and unchanged budget");
 require(reaches_policy(r,s,VMPRESS_LEVEL_CRITICAL,1),
         "fresh high observation survives intermediate wakeup until critical decision");
 require(!reaches_policy(r,s,VMPRESS_LEVEL_CRITICAL,1),"production critical block consumes token exactly once");
 require(read_snapshot(r,s)&&!reaches_policy(r,s,VMPRESS_LEVEL_CRITICAL,1),
         "later unchanged counter cannot replay consumed evidence");
 events(52);fake_ms=1300;
 require(read_snapshot(r,s)&&reaches_policy(r,s,VMPRESS_LEVEL_CRITICAL,1,PSI,true),
         "ordinary direct reclaim retains its policy path");
 require(read_snapshot(r,s)&&!reaches_policy(r,s,VMPRESS_LEVEL_CRITICAL,1),
         "critical direct-reclaim decision also consumes pending high token");
 events(53);
 require(read_snapshot(r,s)&&!reaches_policy(r,s,VMPRESS_LEVEL_MEDIUM,1),
         "medium event does not turn a fresh token into kill permission");
 require(reaches_policy(r,s,VMPRESS_LEVEL_MEDIUM,1,VENDOR),"vendor path remains unchanged");
 require(reaches_policy(r,s,VMPRESS_LEVEL_CRITICAL,1),"medium and vendor cannot consume a future critical token");
 events(54);
 require(read_snapshot(r,s)&&!reaches_policy(r,s,VMPRESS_LEVEL_CRITICAL,1,PSI,false,false,false,false),
         "host mode receives no cell exception");
 require(reaches_policy(r,s,VMPRESS_LEVEL_CRITICAL,1),"host mode did not consume the cell token");
 require(reaches_policy(r,s,VMPRESS_LEVEL_MEDIUM,1,PSI,false,true),"ordinary kswapd reclaim remains on original path");
 require(reaches_policy(r,s,VMPRESS_LEVEL_MEDIUM,1,PSI,false,false,true),"ordinary refault remains on original path");
 std::printf("RESULT %d passed\n",checks);
}
'''
sha = lambda data: hashlib.sha256(data).hexdigest()
report = {'scope': 'compiled actual Reader and actual decision gate; descriptor/clock substitutes; no live pressure',
          'production_ready': False, 'arms': {}}
for label, directory in [('baseline', a.baseline_dir), ('candidate', a.source_dir)]:
    source = (directory/'lmkd.cpp').read_text()
    start = source.index('    /* Identify reclaim state */')
    stop = source.index('    prev_workingset_refault = workingset_refault_file;', start)
    guard = source[start:stop]
    pending = 'ConsumeHighEvidence' in source
    consume = ''
    if pending:
        start = source.index('    // A critical decision consumes current evidence once,')
        stop = source.index('    if (vmstat_parse(&vs)', start)
        consume = source[start:stop]
    cpp = a.out_dir/(label+'.cpp')
    exe = a.out_dir/label
    cpp.write_text(reader + ('\n#define PENDING_API 1\n' if pending else '') + prefix + consume + guard + suffix)
    cmd = ['c++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-I', str(directory),
           str(directory/'memory_cgroup.cpp'), str(cpp),
           '-Wl,--wrap=open,--wrap=openat,--wrap=fstatfs,--wrap=pread,--wrap=close,--wrap=clock_gettime',
           '-o', str(exe)]
    build = subprocess.run(cmd, capture_output=True, text=True)
    assert build.returncode == 0, label + build.stderr
    result = {'compile_rc': 0, 'source_sha256': {n: sha((directory/n).read_bytes())
              for n in ['lmkd.cpp','memory_cgroup.cpp','memory_cgroup.h']},
              'guard_sha256': sha(guard.encode()), 'consume_sha256': sha(consume.encode()), 'sequences': {}}
    for sequence in ('medium', 'poll'):
        run = subprocess.run([str(exe), sequence], capture_output=True, text=True)
        result['sequences'][sequence] = {'rc': run.returncode, 'stdout': run.stdout, 'stderr': run.stderr}
        if label == 'baseline':
            assert run.returncode == 2, result
            assert run.stderr == 'FAIL fresh high observation survives intermediate wakeup until critical decision\n', result
        else:
            assert run.returncode == 0 and run.stderr == '', result
        print(label, sequence, 'rc', run.returncode, run.stdout.strip().splitlines()[-1], run.stderr.strip())
    report['arms'][label] = result
report['pass'] = True
(a.out_dir/'result.json').write_text(json.dumps(report, indent=2)+'\n')
