#!/usr/bin/env python3
"""Fixed baseline02 three-parent diagnostic; no relaxation or runtime admission.

The original generated guard, policy and ancestry sources remain immutable.
Only complete bounded kernel child tables from three already fixed parents are
projected. An original uniqueness rejection is reported as an observation;
it never authorizes Main, an App action, a new process, or task retirement.
"""
import hashlib,json,os,re,signal,stat,time,types
from pathlib import Path

GUARD_PATH=Path('/home/alex/work/pocket4-current-host-r6-source-01/current_baseline_guard.py')
GUARD_BYTES=11541
GUARD_SHA='96dbdaf7673d5298e6fe17cb1b7ebae29b37110ee59f31b0c927e2cb0ef4b150'
BASELINE_SHA='633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364'
QUALIFICATION_SHA='ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e'
SOURCE_SHA='68379ffa989e90c72faa7574df5f1541582f302f730864c4818a976446f727ab'
EPOCH_SHA='7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c'
PARENTS=({'role':'daemon','pid':3588022,'child':3268774},
         {'role':'launcher','pid':3268774,'child':3268775},
         {'role':'intermediary','pid':3268775,'child':3268779})
IDENTITY_KEYS={'host_pid','parent_host_pid','start_ticks','namespace_pids','uids',
               'cmdline','executable','namespaces','cgroup'}

def need(value,code):
    if not value:raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def safe_error(error):
    result={'type':type(error).__name__}
    if isinstance(error,OSError):result['errno']=error.errno
    elif isinstance(error,(RuntimeError,TimeoutError)) and re.fullmatch('[A-Z0-9_]{1,96}',str(error)):
        result['code']=str(error)
    else:result['code']='UNEXPECTED_DIAGNOSTIC_ERROR'
    return result

def read_guard(check,report):
    fds=[];primary=None;errors=[]
    report.update(acquired=0,close_attempts=0,closed=0,remaining=0,errors=[])
    def own(fd):
        if fd<3:
            try:os.close(fd)
            finally:raise RuntimeError('INPUT_FD_ALIASED_STANDARD_STREAM')
        fds.append(fd);report['acquired']+=1;return fd
    try:
        check();directory=own(os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC))
        for part in GUARD_PATH.parts[1:-1]:
            check();directory=own(os.open(part,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory))
        fd=own(os.open(GUARD_PATH.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory))
        first=os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and first.st_uid==0 and
             first.st_size==GUARD_BYTES,'EXACT_CURRENT_GUARD_REGULAR_FILE_REQUIRED')
        raw=b''
        while True:
            check();part=os.read(fd,min(16384,GUARD_BYTES+1-len(raw)))
            if not part:break
            raw+=part;need(len(raw)<=GUARD_BYTES,'CURRENT_GUARD_BYTE_BOUND')
        last=os.fstat(fd)
        fields=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
        need(all(getattr(first,k)==getattr(last,k) for k in fields) and
             len(raw)==GUARD_BYTES and sha(raw)==GUARD_SHA,'EXACT_CURRENT_GUARD_BYTES_CHANGED')
        return raw
    except BaseException as error:primary=error;raise
    finally:
        for fd in reversed(fds):
            report['close_attempts']+=1
            try:os.close(fd);report['closed']+=1
            except BaseException as error:errors.append(safe_error(error))
        report['remaining']=report['acquired']-report['closed'];report['errors']=errors
        if errors:
            if primary is None:raise RuntimeError('DIAGNOSTIC_INPUT_FD_CLOSE_FAILED')
            primary.add_note('DIAGNOSTIC_INPUT_FD_CLOSE_FAILED')

def table_verdict(policy,table,parent,child):
    need(type(parent) is int and type(child) is int and parent!=child,
         'FIXED_DISTINCT_PARENT_CHILD_REQUIRED')
    try:
        policy.validate_child_table(table,parent,child)
    except RuntimeError as error:
        if str(error)!='OWNER_SINGLE_DIRECT_CHILD_REQUIRED':raise
        children=table['child_host_pids']
        classification=('no_children' if not children else
                        'expected_and_additional_children' if child in children else
                        'expected_child_absent')
        return {'original_unique_gate_passed':False,'original_error':safe_error(error),
                'classification':classification}
    return {'original_unique_gate_passed':True,'original_error':None,
            'classification':'exact_expected_single_child'}

def table_pair(policy,first,second):
    roles=[row['role'] for row in PARENTS]
    need(type(first) is dict and type(second) is dict and set(first)==set(second)==set(roles),
         'EXACT_THREE_FIXED_PARENT_TABLES_REQUIRED')
    result={}
    for row in PARENTS:
        role=row['role'];a=table_verdict(policy,first[role],row['pid'],row['child'])
        b=table_verdict(policy,second[role],row['pid'],row['child'])
        result[role]={'fixed_parent_host_pid':row['pid'],'expected_child_host_pid':row['child'],
                      'first':first[role],'second':second[role],
                      'first_original_gate':a,'second_original_gate':b,
                      'complete_tables_equal':first[role]==second[role]}
    return {'parents':result,'all_complete_tables_equal':first==second,
            'original_unique_requirement_met_both_samples':all(
                v['first_original_gate']['original_unique_gate_passed'] and
                v['second_original_gate']['original_unique_gate_passed'] for v in result.values()),
            'runtime_admitted':False,'cleanup_authority':False}

def controls(policy):
    rows=[]
    def table(parent,children):return {'thread_ids':[parent],'per_thread':{str(parent):children},
                                      'child_host_pids':children}
    def case(name,fn):
        fn();rows.append({'name':name,'passed':True})
    def reject(code,fn):
        try:fn()
        except RuntimeError as error:need(str(error)==code,'CONTROL_WRONG_REJECTION')
        else:raise RuntimeError('CONTROL_EXPECTED_REJECTION')
    def exact():
        v=table_verdict(policy,table(11,[12]),11,12)
        need(v=={'original_unique_gate_passed':True,'original_error':None,
                 'classification':'exact_expected_single_child'},'EXACT_CONTROL_FAILED')
    def mismatch(children,label):
        v=table_verdict(policy,table(11,children),11,12)
        need(v['original_unique_gate_passed'] is False and v['classification']==label and
             v['original_error']=={'type':'RuntimeError','code':'OWNER_SINGLE_DIRECT_CHILD_REQUIRED'},
             'MISMATCH_CONTROL_FAILED')
    case('original_exact_single_child_passes',exact)
    case('original_empty_child_gate_stays_failed',lambda:mismatch([],'no_children'))
    case('original_extra_child_gate_stays_failed',lambda:mismatch([12,13],'expected_and_additional_children'))
    case('original_replaced_child_gate_stays_failed',lambda:mismatch([13],'expected_child_absent'))
    case('original_duplicate_child_remains_shape_failure',lambda:reject(
        'COMPLETE_OWNER_PER_THREAD_CHILDREN_REQUIRED',
        lambda:table_verdict(policy,table(11,[12,12]),11,12)))
    case('original_union_mismatch_remains_failure',lambda:reject(
        'COMPLETE_OWNER_CHILD_UNION_REQUIRED',
        lambda:table_verdict(policy,{'thread_ids':[11],'per_thread':{'11':[12]},
                                    'child_host_pids':[13]},11,12)))
    case('original_missing_parent_thread_remains_failure',lambda:reject(
        'COMPLETE_OWNER_THREAD_SET_REQUIRED',
        lambda:table_verdict(policy,{'thread_ids':[10],'per_thread':{'10':[12]},
                                    'child_host_pids':[12]},11,12)))
    def pair(changed=False):
        a={x['role']:table(x['pid'],[x['child']]) for x in PARENTS}
        b=json.loads(json.dumps(a))
        if changed:
            r=PARENTS[0];b[r['role']]=table(r['pid'],sorted([r['child'],1]))
        v=table_pair(policy,a,b)
        need(v['runtime_admitted'] is False and v['cleanup_authority'] is False,
             'DIAGNOSTIC_MUST_NOT_ADMIT_RUNTIME')
        need(v['all_complete_tables_equal']==(not changed) and
             v['original_unique_requirement_met_both_samples']==(not changed),
             'PAIR_COMPARISON_CONTROL_FAILED')
    case('two_complete_equal_tables_still_no_runtime',lambda:pair(False))
    case('second_changed_table_not_hidden_or_retried',lambda:pair(True))
    case('distinct_parent_child_mandatory',lambda:reject('FIXED_DISTINCT_PARENT_CHILD_REQUIRED',
         lambda:table_verdict(policy,table(11,[11]),11,11)))
    need(len(rows)==10 and len({x['name'] for x in rows})==10,'EXACT_TEN_CONTROLS_REQUIRED')
    return {'count':10,'all_passed':True,'cases':rows,'synthetic_data_only':True,
            'actual_production_policy_called':True}

def identity_projection(role,row,expected):
    need(type(row) is dict and set(row)==IDENTITY_KEYS,'FULL_PROCESS_IDENTITY_SCHEMA')
    need(row==expected,'FIXED_FULL_PROCESS_IDENTITY_DIFFERS')
    return {'role':role,'host_pid':row['host_pid'],'parent_host_pid':row['parent_host_pid'],
            'start_ticks':row['start_ticks'],'namespace_pids':row['namespace_pids'],
            'uids':row['uids'],'namespaces':row['namespaces'],
            'full_identity_sha256':sha(canonical(row)),
            'cmdline_json_bytes':len(canonical(row['cmdline'])),
            'cmdline_sha256':sha(canonical(row['cmdline'])),
            'executable_sha256':sha(canonical(row['executable'])),
            'cgroup_sha256':sha(canonical(row['cgroup'])),
            'complete_identity_equal_baseline':True}

def execute():
    began=time.monotonic();began_ns=time.monotonic_ns();deadline=began+8;pool=None;phase='input_guard'
    result={'schema':'pocket4-baseline02-three-parent-diagnostic-v1','ok':False,
            'error':None,'secondary_errors':[],'baseline_sha256':BASELINE_SHA,
            'qualification_sha256':QUALIFICATION_SHA,'expected_epoch_sha256':EPOCH_SHA,
            'original_Main_guard_source_unchanged':True,'original_unique_child_gate_unchanged':True,
            'Android_actions':0,'process_children_created':0,'external_signals':0,
            'namespace_entries':0,'App_or_task_actions':0,'files_written':0,
            'Main_runtime_requalified':False,'old_tasks_reauthorized':False,
            'cleanup_authority':False,'raw_private_baseline_or_cmdline_exported':False,
            'input_FDs':{},'observations':[]}
    def check():need(time.monotonic()<deadline,'DIAGNOSTIC_EIGHT_SECOND_READ_DEADLINE')
    try:
        need(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
        raw=read_guard(check,result['input_FDs'])
        g=types.ModuleType('fixed_original_baseline02_guard');g.__file__=str(GUARD_PATH)
        exec(compile(raw,str(GUARD_PATH),'exec'),g.__dict__)
        need(g.BASELINE_SHA==BASELINE_SHA and g.QUALIFICATION_SHA==QUALIFICATION_SHA and
             g.MAIN_EPOCH==EPOCH_SHA and g.SOURCE_MANIFEST_SHA==SOURCE_SHA,
             'EXACT_BASELINE02_GUARD_BINDING_REQUIRED')
        phase='full_baseline_and_original_source'
        check();b,q,p,e,h,c=g.load_current()
        need(tuple(p.CHAIN_PARENTS)==PARENTS,'EXACT_FIXED_THREE_PARENT_CHAIN_REQUIRED')
        result['controls']=controls(p)
        # Identical historical and executable-lineage gates used by current_guard.
        old=p.parse(g.raw_file(p.ACTIVATION_PATH,131072,p.ACTIVATION_SHA,p.ACTIVATION_BYTES))
        verified=p.parse(g.raw_file(p.VERIFIED_PATH,131072,p.VERIFIED_SHA))
        p.historical(old,verified)
        previous=p.parse(g.raw_file(p.PREVIOUS_BASELINE['path'],131072,
                                   p.PREVIOUS_BASELINE['sha256'],p.PREVIOUS_BASELINE['bytes']))
        p.validate_previous_baseline(previous,old)
        p.validate_executable_content(b['current_process_executables'],
                                      p.executable_content(previous['current_process_executables']))
        g.raw_file(p.CELL_PATH,131072,p.CELL_SHA)
        check();e.require_unchanged(b['framework_epoch'],action_attempted=False)
        fixed=e.capture_processes({k:v['pid'] for k,v in p.EXPECTED.items()})
        need(fixed['binding']==b['all_seven_processes']['binding'],'CURRENT_SEVEN_ROLE_BINDING_CHANGED')
        phase='held_fixed_role_identity_namespace_executable'
        pool=c.ManagedFDs();procs={};roots={};pidfds={};exes={}
        for role,row in p.EXPECTED.items():
            check();pidfds[role]=pool.own(os.pidfd_open(row['pid'],0),'diagnostic_fixed_role_pidfd')
            c.require_pidfd_live(pidfds[role])
            procs[role]=pool.own(os.open('/proc/'+str(row['pid']),os.O_RDONLY|os.O_DIRECTORY|
                                       os.O_CLOEXEC|os.O_NOFOLLOW),'diagnostic_fixed_role_proc')
            roots[role]=pool.own(os.open('root',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC,
                                        dir_fd=procs[role]),'diagnostic_fixed_role_root')
            st=os.fstat(roots[role])
            need({'device':st.st_dev,'inode':st.st_ino}==b['process_roots'][role],'CURRENT_ROOT_CHANGED')
            need(os.readlink('ns/user',dir_fd=procs[role])==b['owner_lineage']['role_user_namespaces'][role],
                 'CURRENT_USER_NAMESPACE_CHANGED')
            exes[role]=pool.own(os.open('exe',os.O_RDONLY|os.O_CLOEXEC,dir_fd=procs[role]),
                               'diagnostic_fixed_role_executable')
            need(g.meta(exes[role])==b['current_process_executables'][role]['file'],
                 'CURRENT_EXECUTABLE_FILE_IDENTITY_CHANGED')
        mid=c.hold_intermediary(pool,p);before_mid=e.process_identity(p.EXPECTED_INTERMEDIARY['pid'])
        need(before_mid==b['owner_lineage']['intermediary_process'],'CURRENT_INTERMEDIARY_IDENTITY_DIFFERS')
        before_ns=c.namespace_sample(pool,procs,mid,check)
        expected_ns={'host':b['owner_lineage']['host_user_namespace'],
                     'roles':b['owner_lineage']['role_user_namespaces'],
                     'intermediary':b['owner_lineage']['intermediary_user_namespace'],
                     'intermediary_root':b['owner_lineage']['intermediary_root']}
        need(before_ns==expected_ns,'CURRENT_NAMESPACES_OR_INTERMEDIARY_ROOT_CHANGED')
        result['fixed_identities_before']={k:identity_projection(k,v,b['all_seven_processes']['binding']['processes'][k])
                                          for k,v in fixed['binding']['processes'].items()}
        result['intermediary_before']=identity_projection('owner_intermediary',before_mid,
                                                         b['owner_lineage']['intermediary_process'])
        parent_fds={'daemon':procs['daemon'],'launcher':procs['launcher'],'intermediary':mid['proc']}
        for index in (1,2):
            phase='complete_fixed_parent_tables_'+str(index);tables={}
            for row in PARENTS:
                check();role=row['role']
                tables[role]=c.children_sample(pool,parent_fds[role],row['pid'],check)
                # Run the unchanged original validator for each complete table.
                # Only its exact uniqueness rejection is recorded as diagnostic.
                table_verdict(p,tables[role],row['pid'],row['child'])
            result['observations'].append({'index':index,'elapsed_ns':time.monotonic_ns()-began_ns,
                                           'tables':tables})
        result['table_comparison']=table_pair(p,result['observations'][0]['tables'],result['observations'][1]['tables'])
        phase='independent_fixed_identity_namespace_executable_after'
        check();again=e.capture_processes({k:v['pid'] for k,v in p.EXPECTED.items()})
        need(again['binding']==fixed['binding'],'CURRENT_FULL_IDENTITIES_CHANGED_DURING_DIAGNOSTIC')
        after_mid=e.process_identity(p.EXPECTED_INTERMEDIARY['pid'])
        need(after_mid==before_mid,'CURRENT_INTERMEDIARY_CHANGED_DURING_DIAGNOSTIC')
        need(c.namespace_sample(pool,procs,mid,check)==before_ns,'CURRENT_NAMESPACES_CHANGED_DURING_DIAGNOSTIC')
        c.require_pidfd_live(mid['pidfd'])
        for role in p.ROLES:
            check();c.require_pidfd_live(pidfds[role]);st=os.fstat(roots[role])
            need({'device':st.st_dev,'inode':st.st_ino}==b['process_roots'][role],'CURRENT_ROOT_CHANGED')
            need(g.meta(exes[role])==b['current_process_executables'][role]['file'],
                 'CURRENT_EXECUTABLE_FILE_IDENTITY_CHANGED')
            fresh=pool.own(os.open('exe',os.O_RDONLY|os.O_CLOEXEC,dir_fd=procs[role]),
                           'diagnostic_final_named_executable')
            try:need(g.meta(fresh)==b['current_process_executables'][role]['file'],
                     'CURRENT_NAMED_EXECUTABLE_CHANGED')
            finally:pool.close(fresh)
        p.validate_snapshot(again,old,b['process_roots'])
        engine=pool.own(h.open_in_root(roots['android_init'],'/system/lib64/libberberis_arm64.so',os.O_RDONLY),
                        'diagnostic_current_engine')
        need(g.meta(engine)==b['engine_artifact']['file'],'CURRENT_ENGINE_FILE_IDENTITY_CHANGED')
        limits={}
        for name in p.LIMITS:
            check();fd=pool.own(os.open('/sys/fs/cgroup/system.slice/droidloomd.service/'+name,
                                       os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW),'diagnostic_cgroup_limit')
            try:
                value=os.read(fd,8193);need(len(value)<=8192,'CGROUP_LIMIT_BOUND')
                limits[name]=value.decode('ascii','strict').strip()
            finally:pool.close(fd)
        need(limits==p.LIMITS==b['limits'],'MAIN_RESOURCE_LIMITS_CHANGED')
        check();e.require_unchanged(b['framework_epoch'],action_attempted=False)
        phase='independent_pinned_source_and_baseline_after'
        b2,q2,_,_,_,_=g.load_current()
        need(b2==b and q2==q,'PINNED_FULL_BASELINE_OR_QUALIFICATION_CHANGED')
        result['final_input_FDs']={}
        need(read_guard(check,result['final_input_FDs'])==raw,'PINNED_ORIGINAL_GUARD_SOURCE_CHANGED')
        check()
        result.update(ok=True,full_private_baseline_and_qualification_revalidated=True,
                      all_seven_full_identities_equal_before_after=True,
                      intermediary_full_identity_equal_before_after=True,
                      all_roots_namespaces_and_executable_files_equal=True,
                      resource_limits_equal=True,source_set_unchanged=True,
                      original_unique_requirement_met_both_samples=
                          result['table_comparison']['original_unique_requirement_met_both_samples'])
    except BaseException as error:result['error']={'phase':phase,**safe_error(error)}
    finally:
        if pool is not None:
            pool.close_all();result['managed_FDs']=pool.summary()
            try:pool.require_clean()
            except BaseException as error:
                result['ok']=False;result['secondary_errors'].append({'phase':'owned_FD_retirement',**safe_error(error)})
        result['elapsed_ns']=time.monotonic_ns()-began_ns
        raw=(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
        need(len(raw)<=131072,'DIAGNOSTIC_PUBLIC_OUTPUT_BOUND')
        print(raw.decode('utf-8'),end='',flush=True)
    return 0 if result['ok'] else 1

def main():return execute()
