"""Freeze only the actual R22 inputs; never launch a build or take source locks.

The final artifact-custody and completed-client pins must be filled from actual
observations. All original R21 inputs and source identities remain immutable.
"""
from pathlib import Path
import ast
import hashlib
import json
import os
import resource
import signal
import stat
import sys
import types

sys.dont_write_bytecode = True
ROOT = Path('/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1')
PREP = Path('/home/qq/work/current2367-cli-preparation-20261120-3b9d-r1')
STAGE = Path('/home/qq/work/p4-r22-controller-preparation-20261120-3b9d-r1')
DEST = ROOT / 'control/vendor-build-20261120-9907-r22'
R21 = ROOT / 'control/vendor-build-20261120-9907-r21'
FIXTURE = Path('/home/qq/work/p4-r22-apex-provider-fixture-20261120-3b9d-r2')
ADM = Path('/home/qq/work/p4-r22-admission-controls-20261120-3b9d-r2')
HEAD = 'e69efd552c1732e8bb3bf92d191f95648b59e7d5'
RUN = 44732433154
CURRENT = {'tree':'fd0ef624e436d1eb5c8d2c4083335088811a6a42','files':2367,'bytes':45262277}
CI_CUSTODY_PIN = None
CURRENT_CLIENTS_PIN = None

def need(value, message):
    if not value:
        raise RuntimeError(message)

def f9(s):
    return [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]

def read(path, cap=16*1024**2):
    path=Path(path)
    need(path.is_absolute() and path.resolve()==path,'canonical whole input')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=f9(os.fstat(fd))
        need(stat.S_ISREG(before[2]) and before[5]==1 and 0<=before[6]<=cap,'bounded regular input')
        with os.fdopen(os.dup(fd),'rb') as stream: body=stream.read(cap+1)
        need(len(body)==before[6] and f9(os.fstat(fd))==f9(path.lstat())==before,'whole original input bookend')
        return {'path':str(path),'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'identity':before},body
    finally:
        os.close(fd)

def pinned(path, expected):
    reference,raw=read(path)
    need(type(expected) is tuple and (reference['bytes'],reference['sha256'])==expected,'exact frozen input: '+str(path))
    return reference,raw

def check(reference):
    actual,_=read(reference['path'])
    need(actual==reference,'original complete identity changed: '+reference['path'])
    return actual

def decode(raw):
    def pairs(items):
        result={}
        for key,value in items:
            need(key not in result,'duplicate JSON key');result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))

def document(path):
    reference,raw=read(path)
    return reference,decode(raw)

def same_source_snapshot(actual, persisted):
    """Compare every native F9 integer across the original JSON tuple encoding."""
    need(set(actual)==set(persisted)=={'tree','files','directories'},'complete original source snapshot shape')
    need(actual['tree']==persisted['tree']==CURRENT['tree'],'exact complete source tree')
    for group in ('files','directories'):
        need(type(actual[group]) is dict and type(persisted[group]) is dict
             and actual[group].keys()==persisted[group].keys(),'exact original snapshot membership')
        for name,vector in actual[group].items():
            stored=persisted[group][name]
            need(type(vector) is tuple and type(stored) is list and len(vector)==len(stored)==9
                 and all(type(x) is int for x in (*vector,*stored)), 'nine native integer F9 fields')
            need(list(vector)==stored,'original source identity changed: '+name)
    return True

def module(path, expected):
    reference,raw=pinned(path,expected)
    value=types.ModuleType('r22_'+Path(path).stem);value.__file__=str(path)
    exec(compile(raw,str(path),'exec'),value.__dict__)
    check(reference)
    return value,reference

def write(path, raw):
    need(path.parent.resolve()==path.parent,'canonical new parent')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return read(path)[0]

def save(path, value):
    return write(path,(json.dumps(value,indent=2,sort_keys=True)+'\n').encode())

def observed_clients(path, expected=None):
    reference,raw=read(path) if expected is None else pinned(path,expected)
    result=[]
    for item in decode(raw):
        observed=item['observation'];status=observed['status'];code=item['expected_exit_code']
        need(type(code) is int and type(status['exit_code']) is int and status['exit_code']==code
             and status['state']=='exited' and status['output_complete'] is True
             and status['capture_error'] is None and observed['output_complete'] is True
             and observed['offset']==0 and observed['next_offset']==observed['available_end'],
             'actual complete original preparation client')
        stdout,body=read(observed['archive_path'])
        need(stdout['bytes']==status['bytes_seen']==status['bytes_stored']==observed['available_end']
             and stdout['sha256']==observed['chunk_sha256'], 'complete original terminal archive')
        result.append({'name':item['name'],'session_id':observed['session_id'],
                       'actual_status':status,'stdout':stdout,'expected_exit_code':code})
    return reference,result

def main():
    need(type(CI_CUSTODY_PIN) is tuple and type(CURRENT_CLIENTS_PIN) is tuple,
         'actual final artifact custody and completed ABI/plan clients are not frozen')
    need(os.getuid()==os.geteuid()==os.getgid()==1000,'ordinary ai395 owner')
    cpus=os.sched_getaffinity(0);need(18 in cpus and len(cpus)>=3,'reserved preparation CPU')
    os.sched_setaffinity(0,{18})
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
    resource.setrlimit(resource.RLIMIT_CPU,(60,60))
    resource.setrlimit(resource.RLIMIT_FSIZE,(8*1024**2,8*1024**2))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));signal.alarm(120)
    need(not os.path.lexists(DEST),'create-only complete R22 controller destination')

    admission,admission_ref=module(ADM/'admission_r22.py',(20971,'e8f407bae7c56f9f0b0c6147bc0150f5dd6dfdf7f3894554a1cf8c57d17f7097'))
    control_ref,control=document(ADM/'RESULT.json')
    need((control_ref['bytes'],control_ref['sha256'])==(6903,'976cd8f1aa3557e34b5f099bf73481e38536c31d3f13b23e9d03ce3dfbeffe5c')
         and control['passed'] is True and control['module']==admission_ref,'actual final admission controls')
    predecessor=control['predecessor_refs']
    for reference in predecessor.values(): check(reference)
    values={name:document(predecessor[name]['path'])[1] for name in ('contract','bundle','terminal','build','recovery')}
    old=values['contract'];baseline={'manifest':admission.MANIFEST,'locks':admission.LOCKS}
    previous=admission.validate_r21_predecessor(values,predecessor,baseline)
    check(baseline['manifest'])
    for reference in baseline['locks']:
        actual,raw=read(reference['path'])
        need(actual==admission.reference(reference) and raw.hex()==reference['body_hex'],'actual original source lock body and inode')

    ci_ref,ci_raw=pinned(PREP/'current-ci.json',(546621,'fe8dd7b37639d247fffa7760ea53a3220e333ca090d9ca81a7f06bc3faf8d851'))
    ci=decode(ci_raw)
    custody_ref,custody_raw=pinned(PREP/'CI-ARTIFACT-REVIEW.json',CI_CUSTODY_PIN)
    custody=decode(custody_raw)
    need(custody['passed'] is True and custody['head']==HEAD and custody['run_id']==RUN,
         'actual same-head complete downloaded artifact review')
    provenance={key:ci[key] for key in ('github_commit','github_run_id','source_chain')}
    need(provenance['github_commit']==HEAD and provenance['github_run_id']==RUN,'complete original final GitHub provenance')
    binaries={name:read(PREP/'bin'/name)[0] for name in admission.BINARIES}
    release=admission.validate_current_release(ci,binaries,provenance)

    source_ref,source=document(PREP/'SOURCE_FREEZE.json')
    need((source_ref['bytes'],source_ref['sha256'])==(2243323,'2663841a3ff4d3b646bfbb67e4a54189ce23e47b364f08b32abb4efbf9dacba8')
         and source['source']==CURRENT and source['whole_new_source_verified'] is True,
         'actual independently prepared whole producer')
    rows_ref,rows=document(PREP/'SOURCE-ROWS.json')
    helper,helper_ref=module(PREP/'source_helpers.py',(27232,'e6a14326b1aa1ccc17d606c60bfc9bdf525f47bb2ccafffc86a054c55dd06219'))
    need(same_source_snapshot(helper.source_snapshot(PREP/'producer',rows,CURRENT['tree']),source['source_snapshot']),
         'actual complete producer still matches original preparation identities')
    current={'path':str(PREP/'producer'),**CURRENT,'rows':rows_ref,'freeze':source_ref}

    abi_ref,abi=document(PREP/'abi/HOST-DIRECT-SYMBOL-REVIEW.json')
    need(abi['head']==HEAD and abi['source']==CURRENT and abi['passed_direct_symbols_only'] is True
         and abi['errors']==[] and abi['all_original_children_reaped'] is True,'actual same-cohort host symbol review')
    need(abi['schema']=='p4-current19-static-direct-import-compatibility-v1'
         and abi['host']=='ai395' and abi['binary_count']==19
         and abi['dynamic_transitive_loading_tested'] is False
         and abi['runtime_qualified'] is False and abi['production_ready'] is False
         and len(abi['binaries'])==19 and len({x['binary'] for x in abi['binaries']})==19
         and {x['binary']:x['sha256'] for x in abi['binaries']}
             == {name:x['sha256'] for name,x in binaries.items()}
         and all(x['missing_strong']==[] for x in abi['binaries']),
         'same complete nineteen actual binaries in the direct host ABI review')
    host_inputs=admission.validate_host_abi_custody(abi,abi['host_abi_inputs'])
    for reference in host_inputs:check(reference)
    plans_ref,plans=document(PREP/'plans/PLAN-EVIDENCE.json')
    need(plans['passed'] is True and plans['source']==CURRENT and plans['errors']==[]
         and plans['all_original_children_reaped'] is True and len(plans['commands'])==2,
         'actual two normal read-only source plans')
    profiles={}
    for i,(key,profile) in enumerate((('old','production-full-lint'),('new','production-full-apex-tests'))):
        command=plans['commands'][i];admission.command_reaped(command)
        lock=read(PREP/'producer/android/manifest'/(profile+'-source-lock.json'))[0]
        need(command['argv']==[binaries['droidloom-source']['path'],'--profile',profile,'plan','--lock',lock['path']],
             'original read-only source plan argv')
        profiles[key]={'lock':lock,'plan':check(command['stdout'])};check(command['stderr'])

    transition_ref,_=pinned(FIXTURE/'apex_test_transition.py',(18207,'40d6c8f957f96cea2329296729de940f7c22cdfd9ae1116b8d2809ac9c1ded3a'))
    partial_ref,_=pinned(FIXTURE/'apex_test_partial.py',(33714,'69aaa8f009979722a2fe29fa6b3e56c05bd2c2002b90cc551e86b36c1df5942e'))
    book_ref=check(old['support']['bookends'])
    real_git_ref,real_git=document(FIXTURE/'RESULT.json');admission.validate_original_git_fixture(real_git)
    transition_control_ref,_=pinned(STAGE/'TRANSITION-TESTS.json',(1340,'b4812ac6d7516a1cd2c2af55823bc5e17fdb6867a231816d9b05b3c86d331064'))
    original_clients_ref,clients=observed_clients(STAGE/'PREPARATION-CLIENTS.json')
    current_clients_ref,current_clients=observed_clients(STAGE/'CURRENT-PREPARATION-CLIENTS-R2.json',CURRENT_CLIENTS_PIN)
    clients+=current_clients
    need(len({row['session_id'] for row in clients})==len(clients),'unique original preparation clients')
    targets=list(old['live_retirement_targets'])
    for unit in ('p4-cp3a-vendor-supervisor-20261120-9907-r21.service',
                 'p4-cp3a-vendor-20261120-9907-r21.service',
                 'p4-cp3a-vendor-20261120-9907-r21-recovery.service',
                 'p4-r22-apex-providers-git-fixture-20261120-3b9d-r1.service',
                 'p4-r22-apex-providers-git-fixture-20261120-3b9d-r2.service'):
        need(not any(row['scope']=='user' and row['unit']==unit for row in targets),'no substituted live retirement')
        targets.append({'scope':'user','unit':unit,'pids':[]})
    source_inputs=[read(p)[0] for p in sorted(STAGE.iterdir()) if p.is_file()]
    source_inputs+=[custody_ref,helper_ref,read(PREP/'BINARY-IMPORTS.json')[0],read(PREP/'inspect_binaries.py')[0],
                    read(PREP/'inspect_host_abi.py')[0],read(PREP/'run_plans.py')[0]]
    contract={'schema':'p4-vendor-r22-operational-input-contract-v1','operational_inputs_frozen':True,
        'runtime_qualified':False,'production_ready':False,'git_conversion_admission':old['git_conversion_admission'],
        'support':{'admission':admission_ref,'transition':transition_ref,'partial':partial_ref,'bookends':book_ref},
        'current_source':current,'baseline':baseline,'current_binaries':binaries,
        'release_ci':ci_ref,'ci_provenance':provenance,'profiles':profiles,'plan_evidence':plans_ref,
        'host_direct_abi':abi_ref,'host_abi_inputs':host_inputs,'predecessor':predecessor,
        'controls':{'transition':transition_control_ref,'admission':control_ref,'real_git':real_git_ref,
                    'source_inputs':source_inputs},'live_retirement_targets':targets,'preparation_clients':clients}
    template_ref,template=pinned(STAGE/'source-r22-template.py',(315291,'ae3aec36d96c2a04932d5b08fd5eff855d066eaffb364238cd12ce45b4dc6396'))
    outer_ref,outer=pinned(STAGE/'outer-r22-template.py',(35188,'98949e4db26ed64d7716292f418aed3e8d3b7b2fc015df449f3ace60405d35d8'))
    final_refs=[*source_inputs,original_clients_ref,current_clients_ref,ci_ref,custody_ref,
        *binaries.values(),source_ref,rows_ref,abi_ref,*host_inputs,plans_ref,
        *[row[key] for row in profiles.values() for key in ('lock','plan')],
        *predecessor.values(),admission_ref,transition_ref,partial_ref,book_ref,
        real_git_ref,control_ref,transition_control_ref,template_ref,outer_ref,
        *[row['stdout'] for row in clients],baseline['manifest'],
        *[admission.reference(row) for row in baseline['locks']]]
    by_path={}
    for reference in final_refs:
        need(reference['path'] not in by_path or by_path[reference['path']]==reference,
             'one immutable identity per declared input path')
        by_path[reference['path']]=reference
    for reference in by_path.values():check(reference)
    need(same_source_snapshot(helper.source_snapshot(PREP/'producer',rows,CURRENT['tree']),source['source_snapshot']),
         'whole original producer remains unchanged immediately before creating the frozen packet')
    DEST.mkdir(mode=0o700);(DEST/'inputs').mkdir(mode=0o700)
    contract_ref=save(DEST/'inputs/CONTRACT.json',contract)
    anchor=b'R22_CONTRACT_PIN = None'
    need(template.count(anchor)==1,'single fixed reviewed contract anchor')
    frozen=template.replace(anchor,('R22_CONTRACT_PIN = '+repr((contract_ref['bytes'],contract_ref['sha256']))).encode())
    worker_ref=write(DEST/'source.py',frozen)
    worker=types.ModuleType('r22_frozen_worker');worker.__file__=worker_ref['path']
    exec(compile(frozen,worker.__file__,'exec'),worker.__dict__)
    need(worker.R22==contract and worker.TREE==CURRENT['tree'] and str(worker.CONTROL)==str(DEST/'actual'),
         'actual complete frozen worker imports only the reviewed current inputs')
    worker.r22_current_baseline();controls=worker.r22_validate_controls();worker.source_contracts()
    need(all(worker.PINS[path]==pin for path,pin in worker.R22_PRESERVED_PINS.items()),'all historical pins retained')
    bundle={'schema':'pocket4-vendor-r22-launch-bundle-v1','dispatch_inputs_frozen':True,
            'source_tree':CURRENT['tree'],'current_runtime_source':CURRENT,'worker':worker_ref,
            'operational_contract':contract_ref,'actual_current_CI':ci_ref,'actual_R21_predecessor':predecessor,
            'original_budgets_unchanged':True,'new_vendor_build_not_yet_dispatched':True,
            'only_four_original_APEX_provider_files_materialize':True,
            'previous_failed_build_replaced':False,'runtime_qualified':False,'production_ready':False}
    bundle_ref=save(DEST/'inputs/BUNDLE.json',bundle)
    anchor=b"BUNDLE_SHA = 'UNFROZEN_SOURCE_ONLY'";need(outer.count(anchor)==1,'single reviewed bundle anchor')
    frozen_outer=outer.replace(anchor,("BUNDLE_SHA = '"+bundle_ref['sha256']+"'").encode())
    compile(frozen_outer,str(DEST/'outer.py'),'exec')
    final_outer=write(DEST/'outer.py',frozen_outer)
    receipt={'schema':'p4-r22-actual-complete-input-freeze-v1','contract':contract_ref,'worker':worker_ref,
        'bundle':bundle_ref,'outer':final_outer,'actual_release':release,'actual_predecessor':previous,
        'actual_controls':controls,'source_snapshot_unchanged':True,'all_historical_pins_unchanged':True,
        'all_preparation_clients_complete':True,'build_started':False,'source_mutations':False,
        'source_locks_acquired':False,'runtime_qualified':False,'production_ready':False}
    receipt_ref=save(DEST/'PREPARATION.json',receipt)
    print(json.dumps({'passed':True,'preparation':receipt_ref,'worker':worker_ref,'outer':final_outer,
                      'build_started':False,'runtime_qualified':False,'production_ready':False}),flush=True)

if __name__=='__main__':
    main()
