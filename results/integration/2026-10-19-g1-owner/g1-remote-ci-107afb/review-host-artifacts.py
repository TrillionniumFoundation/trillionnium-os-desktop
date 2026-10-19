#!/usr/bin/env python3
"""Validate final ordinary CI host receipts without executing a build or fixture."""
from pathlib import Path
import ast, collections, datetime, hashlib, json, re, subprocess, tomllib, zipfile

BASE=Path('/workspace/scratch/499c7902de8e/r10-evidence/g1-remote-ci-107afb74')
REPO='/workspace/scratch/499c7902de8e/r10-g1-queryabi'
LOCAL='bccb817e0d3f1987f59c1b9e7d94e939d2e6d1d3'
HEAD='107afb7436ca17177262fdfef2e6b5dfee13597a'
TREE='65ddb50cd303f3c43a8226141c5298dca369db5d'
checks=[]
def need(v, label):
    if not v: raise ValueError(label)
    checks.append(label)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def gitfile(name): return subprocess.check_output(['git','--no-optional-locks','-C',REPO,'show',LOCAL+':'+name])
def ident(name):
    p=BASE/name
    return {'path':name,'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())}
def observation(name,key):
    return next(o['response_json'] for o in json.loads((BASE/name).read_text())['observations'] if o['key']==key)
def main():
    started=datetime.datetime.now(datetime.timezone.utc).isoformat()
    a03job=observation('observation-002-jobs.json','a03_jobs')['jobs'][0]
    g0job=observation('observation-003-host-terminal.json','g0_jobs')['jobs'][0]
    for job,count in [(a03job,10),(g0job,20)]:
        need(job['head_sha']==HEAD and job['conclusion']=='success' and len(job['steps'])==count and all(s['conclusion']=='success' for s in job['steps']), 'all actual API steps successful '+job['name'])
    merge=observation('observation-004-merge-and-a06.json','g0_merge_commit')
    need(merge['sha']=='1f6d2ea7d1ba1e0044d3d9dce8f36247b884be81' and merge['tree']['sha']==TREE and HEAD in [p['sha'] for p in merge['parents']], 'G0 actual merge checkout has exact final tree')
    g0text=(BASE/'g0-job-117877088393.log').read_text()
    a03text=(BASE/'a03-job-117877088641.log').read_text()
    need(merge['sha'] in g0text and HEAD in a03text and '##[error]' not in g0text and '##[error]' not in a03text, 'full G0 and A03 logs no error annotations and checkout binding')
    # These are host fixture runs; do not count them as QEMU cases.
    test_source=ast.parse(gitfile('tests/kernel/control/test_queryabi_candidate_runner.py').decode())
    tests=[n.name for c in test_source.body if isinstance(c,ast.ClassDef) for n in c.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')]
    need(len(tests)==8 and len(set(tests))==8, 'eight candidate host fixture names in frozen Git')
    host_hits={n:g0text.count(n+' (') for n in tests}
    need(all(v==2 for v in host_hits.values()), 'all eight candidate host fixtures ran in normal and optimized G0 passes')
    summaries=[{'line':i+1,'text':l} for i,l in enumerate(g0text.splitlines()) if ('Ran ' in l and ' test' in l) or 'test result: ok.' in l]
    path=BASE/'a03-native-models-39195437840.zip'
    need(path.stat().st_size==16548 and sha(path.read_bytes())=='2f5b5cb5252ab96871e64f49b4ab3a44c3b9309993ce7ff1a9512fd4ab5ebb17', 'actual A03 archive matches GitHub size/digest')
    with zipfile.ZipFile(path) as z:
        need(len(z.infolist())==17 and z.testzip() is None,'A03 actual seventeen members and CRC')
        loom=json.loads(z.read('a03-loom/results.json'))
        current=json.loads(z.read('a03-lock-alloc/current/execution.json'))
        total=json.loads(z.read('a03-lock-alloc/execution.json'))
        need(loom['exit_code']==0 and loom['requested_variant']=='all' and loom['source_unchanged'] and loom['source_inventory_unchanged'], 'all Loom variants complete and source unchanged')
        for name,digest in loom['source_hashes'].items():
            need(sha(gitfile(name))==digest, 'Loom source Git hash '+name)
        model_summaries={}
        for variant,count in [('default_shim',13),('public_backend',6)]:
            v=loom['variants'][variant]
            raw=z.read('a03-loom/'+variant+'.log')
            text=raw.decode()
            need('test result: ok. '+str(count)+' passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in ' in text, 'actual Loom raw summary '+variant)
            found={n:int(c) for n,c in re.findall(r'MODEL ([a-z_]+): schedules=([0-9]+)',text)}
            need(found==v['models'] and len(found)==count, 'actual model schedule observations match '+variant)
            need(v['source_overrides']==(['src/sync.rs'] if variant=='default_shim' else []),'exact source override boundary '+variant)
            for name,digest in v['copied_source_hashes'].items():
                source_path='tests/control/loom/sync.rs' if variant=='default_shim' and name=='sync.rs' else 'libs/os-control/src/'+name
                need(sha(gitfile(source_path))==digest,'copied Loom source '+variant+':'+name)
            commands=[c for c in loom['commands'] if c.get('variant')==variant]
            need(len(commands)==3 and all(c['exit_code']==0 for c in commands), 'fmt test strict clippy zero '+variant)
            need(any('clippy' in c['argv'] and c['argv'][-3:]==['--','-D','warnings'] for c in commands), 'strict warnings retained '+variant)
            model_summaries[variant]={'models':found,'raw_log_sha256':sha(raw),'commands':commands}
        need(total['passed'] and total['result']=='current_zero' and total['current_check_executed'] and set(total['probes'])=={'current'}, 'only actual current allocator probe accepted')
        need(total['probes']['current']==current,'allocator embedded and standalone receipt same')
        need(current['passed'] and current['mode']=='current_required_zero' and current['lock_selection']=='public_LockBackend_TrackingBackend', 'actual current probe mode')
        for field in ['production_sources_byte_identical','temporary_source_bytes_verified_after_execution','worktree_source_bytes_unchanged_during_execution']:
            need(current[field] is True,'allocator exact source bound '+field)
        need(current['only_source_substitution'] is None and current['replacement_sync_sha256'] is None,'no substituted production modules for current probe')
        for row in total['fixtures']:
            need(sha(gitfile('tests/control/lock_alloc/'+row['path']))==row['sha256'],'allocator fixture exact Git '+row['path'])
        for row in current['source_inventory']:
            data=gitfile('libs/os-control/src/'+row['path'])
            need(sha(data)==row['sha256'] and len(data)==row['bytes'],'allocator production source exact Git '+row['path'])
        need(current['source_inventory']==current['copied_source_inventory'],'allocator copies equal original six modules')
        need(total['all_probes_used_identical_harness_bytes'] and total['harness_fixtures_unchanged_during_execution'],'actual fixture bytes stable')
        for stage in ['build','format','clippy','run']:
            c=current[stage]
            need(c['returncode']==0 and not c['timed_out'],'actual allocator '+stage+' returned zero')
            for stream in ['stdout','stderr']:
                need(sha(z.read('a03-lock-alloc/current/'+c[stream]))==c[stream+'_sha256'],'allocator '+stage+' '+stream+' raw bytes bound')
        need(current['run']['argv'][1:]==['--allocation-failure-controls'],'actual bounded failure controls requested')
        need(current['clippy']['argv'][-3:]==['--','-D','warnings'],'allocator strict warnings retained')
        for n,v in current['generated_manifests'].items():
            need(sha(v['contents'].encode())==v['sha256'],'generated manifest exact recorded bytes '+n)
        generated=tomllib.loads(current['generated_manifests']['os-control/Cargo.toml']['contents'])
        need(generated['lints']['rust']['unsafe_code']=='forbid' and generated['lints']['rust']['unexpected_cfgs']=={'level':'warn','check-cfg':['cfg(ktest)']},'generated manifest registers known cfg without enabling it')
        need(total['toolchain_environment']['RUSTFLAGS'] is None and total['toolchain_environment']['CARGO_ENCODED_RUSTFLAGS'] is None,'no injected rustflags in actual host run')
        raw=z.read('a03-lock-alloc/current/run.stdout.log')
        events=[json.loads(line) for line in raw.decode().splitlines()]
        need(events==current['checks']['events'] and len(events)==26,'26 raw allocator events match receipt exactly')
        scenarios=[e for e in events if e['event']=='scenario']
        need(len(scenarios)==len({e['name'] for e in scenarios})==19,'19 unique allocator scenario events')
        fields=['alloc','realloc','dealloc','allocated_bytes','reallocated_bytes','deallocated_bytes']
        need(all(all(e[k]==0 for k in fields) for e in scenarios),'all six allocation counters zero in every scenario')
        summary=[e for e in events if e['event']=='summary']
        need(len(summary)==1 and summary[0]==current['checks']['summary'] and all(summary[0][k]==0 for k in fields),'actual aggregate excludes no scenario allocation')
        controls={e['name']:e for e in events if e['event']=='control'}
        positive=controls['allocator_positive']
        need(positive['alloc']==positive['realloc']==positive['dealloc']==1,'positive allocator instrumentation sees all three event kinds')
        need(controls['failed_allocator_call_under_lock']['alloc']==1 and controls['failed_allocator_call_under_lock']['allocated_bytes']==16,'failed allocation counted while locked')
        need(controls['depth_tls_poison_unwind']['passed'] is True,'depth TLS poison and unwind control passed')
        fail=[e for e in events if e['event']=='failure_control']
        need(fail==[{'event':'failure_control','injected_failures':2,'frontier_atomic':True,'history_usable':True}],'actual two bounded failure controls preserve frontier and history')
        need(events[-1]=={'event':'acceptance','scenario_count':19,'zero':True,'controls_ok':True},'actual final allocator acceptance event')
        stderr=z.read('a03-lock-alloc/current/run.stderr.log').decode()
        output={
            'schema':'r10.g1-pr197.final-host-artifact-review.v1','review_started_at_utc':started,'review_completed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'blocking_findings':[],
            'head':HEAD,'tree':TREE,'same_tree_local':LOCAL,
            'g0':{'job':g0job,'actual_checkout_commit':merge['sha'],'actual_checkout_tree':merge['tree']['sha'],'log':ident('g0-job-117877088393.log'),'candidate_host_fixture_occurrences':host_hits,'suite_summaries':summaries,'scope':'Host wire/spec/model/strict lint/cross-rlib gates; no QEMU or device-control execution in G0.'},
            'a03':{'job':a03job,'archive':ident(path.name),'manifest':'a03-artifact-members.json','log':ident('a03-job-117877088641.log'),'loom':model_summaries,'loom_checked_Git_inputs':len(loom['source_hashes']),'allocator_source_modules':current['source_inventory'],'allocator_fixture_inputs':total['fixtures'],'allocator_commands':{s:current[s] for s in ['build','format','clippy','run']},'generated_os_control_manifest':current['generated_manifests']['os-control/Cargo.toml'],'actual_event_count':len(events),'actual_scenario_count':len(scenarios),'scenario_names':[e['name'] for e in scenarios],'actual_summary':summary[0],'actual_controls':controls,'actual_failure_control':fail[0],'run_stderr_retained':stderr,'run_stdout_sha256':sha(raw)},
            'limits':['A03 tests are bounded host Loom and instrumented allocator models; they are not real kernel IRQ/allocator/OSTD proof.','The actual allocator command used only the current probe and two allocation-failure controls. Historical and callback negative source revisions were not requested in this CI execution.','The allocator positive and poison/unwind controls intentionally emit activity and a caught panic hook; raw stderr is preserved and runtime returned zero.','This A03 archive preserves actual commands, source-copy hashes and raw output, but does not contain the removed temporary allocator ELF; independent ELF identity verification belongs to the separate A06 artifact.','G0 uses the PR merge checkout, verified through GitHub Git API to have exactly the final-head tree. A03 uses the exact PR source head.','A06 was still running at the observation underlying this host review; its final artifact will be reviewed separately.'],
            'evidence_checks_completed':len(checks)
        }
    (BASE/'host-artifact-review.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({'blocking_findings':[],'g0_steps':20,'candidate_host_fixtures':len(tests),'occurrences_each':2,'loom_models':19,'allocator_events':26,'allocator_scenarios':19,'review':str(BASE/'host-artifact-review.json')},indent=2))
if __name__=='__main__':main()
