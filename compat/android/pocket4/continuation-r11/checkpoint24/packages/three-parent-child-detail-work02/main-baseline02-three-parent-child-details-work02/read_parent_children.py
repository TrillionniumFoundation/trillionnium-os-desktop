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

PUBLIC_EXECUTABLE_ROLES={
    '/usr/bin/timeout':'host_timeout',
    '/usr/bin/nsenter':'host_namespace_enter',
    '/usr/sbin/ip':'host_ip',
    '/usr/bin/ip':'host_ip',
    '/system/bin/getprop':'Android_property_reader',
    '/vendor/bin/droidloom-task-launcher':'Android_task_launcher',
}
MAX_CHILD_DETAILS=64
MAX_FD_LINKS=256
MAX_ONE_CHILD_FDS=128

def public_child_identity(value,expected_identities):
    need(type(value) is dict and set(value)==IDENTITY_KEYS,'CHILD_COMPLETE_IDENTITY_SCHEMA')
    need(type(value['host_pid']) is int and 0<value['host_pid']<=2147483647 and
         type(value['parent_host_pid']) is int and 0<=value['parent_host_pid']<=2147483647 and
         type(value['start_ticks']) is int and 0<value['start_ticks']<2**64 and
         type(value['namespace_pids']) is list and 1<=len(value['namespace_pids'])<=8 and
         all(type(x) is int and 0<x<=2147483647 for x in value['namespace_pids']) and
         type(value['uids']) is list and len(value['uids'])==4 and
         all(type(x) is int and 0<=x<2**32 for x in value['uids']),'CHILD_IDENTITY_NUMBERS')
    need(type(value['namespaces']) is dict and set(value['namespaces'])=={'pid','mnt'} and
         all(type(value['namespaces'][k]) is str and
             re.fullmatch(k+r':\[[0-9]{1,20}\]',value['namespaces'][k])
             for k in ('pid','mnt')),'CHILD_IDENTITY_NAMESPACES')
    need(type(value['cmdline']) is list and len(value['cmdline'])<=256 and
         all(type(x) is str for x in value['cmdline']) and
         len(canonical(value['cmdline']))<=65536 and
         type(value['cgroup']) is list and len(value['cgroup'])<=32 and
         all(type(x) is str for x in value['cgroup']) and
         len(canonical(value['cgroup']))<=65536 and
         type(value['executable']) is str and len(value['executable'].encode())<=4096,
         'CHILD_PRIVATE_FIELD_BOUND')
    matches=[role for role,identity in expected_identities.items() if identity==value]
    need(len(matches)<=1,'CHILD_ROLE_IDENTITY_AMBIGUOUS')
    return {'host_pid':value['host_pid'],'parent_host_pid':value['parent_host_pid'],
            'start_ticks':value['start_ticks'],'namespace_pids':value['namespace_pids'],
            'uids':value['uids'],'namespaces':value['namespaces'],
            'full_identity_sha256':sha(canonical(value)),
            'fixed_baseline_role':matches[0] if matches else None,
            'exact_expected_role_identity':bool(matches),
            'public_executable_shape':PUBLIC_EXECUTABLE_ROLES.get(value['executable']),
            'public_executable_shape_is_installed_source_authority':False,
            'cmdline_json_bytes':len(canonical(value['cmdline'])),
            'cmdline_sha256':sha(canonical(value['cmdline'])),
            'executable_utf8_bytes':len(value['executable'].encode()),
            'executable_sha256':sha(value['executable'].encode()),
            'cgroup_json_bytes':len(canonical(value['cgroup'])),
            'cgroup_sha256':sha(canonical(value['cgroup'])),
            'raw_cmdline_executable_cgroup_exported':False}

def fd_name_list(names):
    need(type(names) is list and len(names)<=MAX_ONE_CHILD_FDS and
         all(type(name) is str and re.fullmatch('0|[1-9][0-9]{0,9}',name) and int(name)<=2147483647
             for name in names),'OBSERVED_CHILD_FD_LIST_BOUND_OR_SHAPE')
    values=sorted(int(name) for name in names)
    need(len(set(values))==len(values),'OBSERVED_CHILD_FD_DUPLICATE')
    return values

def fd_target_projection(target):
    need(type(target) is str and len(target.encode('utf-8'))<=4096,'OBSERVED_CHILD_FD_TARGET_BOUND')
    raw=target.encode('utf-8')
    value={'target_utf8_bytes':len(raw),'target_sha256':sha(raw),'kind':'other',
           'known_public_target':None,'kernel_object_number':None,'raw_target_exported':False}
    match=re.fullmatch(r'(socket|pipe):\[([0-9]{1,20})\]',target)
    if match:
        value['kind']=match.group(1);value['kernel_object_number']=match.group(2)
    elif target in ('/dev/null','/dev/zero'):
        value['kind']='known_device';value['known_public_target']=target
    elif target in ('anon_inode:[eventpoll]','anon_inode:[eventfd]','anon_inode:[timerfd]',
                     'anon_inode:inotify','anon_inode:[pidfd]','anon_inode:[signalfd]'):
        value['kind']='known_anon_inode'
    return value

def detail_own(pool,fd,label):
    value=pool.own(fd,label)
    need(pool.acquired<=512,'CHILD_DIAGNOSTIC_DESCRIPTOR_BOUND')
    return value

def held_stat_values(raw):
    need(type(raw) is bytes and 0<len(raw)<=16384,'HELD_CHILD_STAT_BYTE_BOUND')
    text=raw.decode('utf-8','strict')
    # Same field positions as the exact original framework_epoch._stat.
    fields=text[text.rindex(')')+2:].split()
    return int(text.split('(',1)[0]),int(fields[1]),int(fields[19]),fields[0]

def require_held_child_stat(raw,expected):
    value=held_stat_values(raw)
    need(value[:3]==(expected['host_pid'],expected['parent_host_pid'],expected['start_ticks']) and
         value[3] not in 'ZX','HELD_CHILD_PROCESS_IDENTITY_CHANGED')
    return value

def check_held_child_stat(pool,proc,expected,check):
    fd=None
    try:
        check();fd=detail_own(pool,os.open('stat',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=proc),
                              'observed_child_held_stat')
        raw=b''
        while True:
            check();part=os.read(fd,min(4096,16385-len(raw)))
            if not part:break
            raw+=part;need(len(raw)<=16384,'HELD_CHILD_STAT_BYTE_BOUND')
        require_held_child_stat(raw,expected)
    finally:
        if fd is not None:pool.close(fd)

def child_fd_observation(pool,proc,check,budget):
    directory=None
    value={'complete':False,'before_numbers':None,'after_numbers':None,'links':[],
           'same_fd_number_set':False,'error':None}
    try:
        check();directory=detail_own(pool,os.open('fd',os.O_RDONLY|os.O_DIRECTORY|
                                      os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=proc),'observed_child_fd_directory')
        numbers=fd_name_list(os.listdir(directory));value['before_numbers']=numbers
        need(budget['fd_links']+len(numbers)<=MAX_FD_LINKS,'TOTAL_CHILD_FD_LINK_BOUND')
        for number in numbers:
            check();target=os.readlink(str(number),dir_fd=directory);budget['fd_links']+=1
            value['links'].append({'fd_number':number,**fd_target_projection(target)})
        value['after_numbers']=fd_name_list(os.listdir(directory))
        value['same_fd_number_set']=value['after_numbers']==numbers
        need(value['same_fd_number_set'],'OBSERVED_CHILD_FD_NUMBER_SET_CHANGED')
        value['complete']=True
    except BaseException as error:value['error']=safe_error(error)
    finally:
        if directory is not None:pool.close(directory)
    return value

def inspect_direct_children(pool,c,e,g,table,row,expected_identities,check,budget):
    results=[]
    for pid in table['child_host_pids']:
        item={'host_pid':pid,'started_monotonic_ns':time.monotonic_ns(),'started_realtime_ns':time.time_ns(),
              'identity':None,'complete_stable_identity_observed':False,
              'executable_file':None,'executable_content_read':False,'fd_observation':None,
              'error':None,'new_process_adopted':False}
        results.append(item);pidfd=None;proc=None;exe=None
        try:
            need(budget['children']<MAX_CHILD_DETAILS,'TOTAL_CHILD_DETAIL_BOUND')
            budget['children']+=1;check()
            pidfd=detail_own(pool,os.pidfd_open(pid,0),'observed_direct_child_pidfd')
            first=e.process_identity(pid)
            item['identity']=public_child_identity(first,expected_identities)
            need(first['host_pid']==pid and first['parent_host_pid']==row['pid'],'OBSERVED_CHILD_PARENT_DIFFERS')
            c.require_pidfd_live(pidfd)
            proc=detail_own(pool,os.open('/proc/'+str(pid),os.O_RDONLY|os.O_DIRECTORY|
                                       os.O_NOFOLLOW|os.O_CLOEXEC),'observed_direct_child_proc')
            check_held_child_stat(pool,proc,first,check)
            exe=detail_own(pool,os.open('exe',os.O_PATH|os.O_CLOEXEC,dir_fd=proc),'observed_direct_child_executable')
            file=g.meta(exe);item['executable_file']=file
            item['executable_matches_fixed_role_executables']=[
                role for role,value in expected_identities.items() if first['executable']==value['executable']]
            item['cgroup_equals_fixed_roles']=[
                role for role,value in expected_identities.items() if first['cgroup']==value['cgroup']]
            item['cmdline_equals_fixed_roles']=[
                role for role,value in expected_identities.items() if first['cmdline']==value['cmdline']]
            item['fd_observation']=child_fd_observation(pool,proc,check,budget)
            check();check_held_child_stat(pool,proc,first,check)
            last=e.process_identity(pid)
            need(last==first,'OBSERVED_CHILD_IDENTITY_CHANGED')
            need(g.meta(exe)==file,'OBSERVED_CHILD_EXECUTABLE_FILE_CHANGED')
            c.require_pidfd_live(pidfd)
            item['complete_stable_identity_observed']=True
        except BaseException as error:item['error']=safe_error(error)
        finally:
            for fd in (exe,proc,pidfd):
                if fd is not None:pool.close(fd)
            item['ended_monotonic_ns']=time.monotonic_ns();item['ended_realtime_ns']=time.time_ns()
    return results

def child_detail_controls():
    rows=[]
    def same(actual,expected):need(actual==expected,'CHILD_DETAIL_CONTROL_ASSERTION')
    def case(name,fn):fn();rows.append({'name':name,'passed':True})
    def reject(code,fn):
        try:fn()
        except RuntimeError as error:same(str(error),code);return
        raise RuntimeError('CHILD_DETAIL_CONTROL_FALSE_ACCEPT')
    sample={'host_pid':11,'parent_host_pid':1,'start_ticks':22,'namespace_pids':[11],
            'uids':[0,0,0,0],'namespaces':{'pid':'pid:[123]','mnt':'mnt:[456]'},
            'cmdline':['/synthetic/private','value'],'executable':'/synthetic/private',
            'cgroup':['0::/synthetic/private']}
    def known():
        value=public_child_identity(sample,{'daemon':sample})
        same(value['fixed_baseline_role'],'daemon');same(value['exact_expected_role_identity'],True)
        need('/synthetic/private' not in json.dumps(value),'PRIVATE_CHILD_VALUE_EXPORTED')
    case('only_full_identity_assigns_fixed_role',known)
    def changed():
        value=public_child_identity({**sample,'host_pid':12,'start_ticks':23},{'daemon':sample})
        same(value['fixed_baseline_role'],None);same(value['exact_expected_role_identity'],False)
    case('same_program_different_process_not_adopted',changed)
    def fd_public():
        value=fd_target_projection('socket:[123456]')
        same((value['kind'],value['kernel_object_number']),('socket','123456'))
        unknown=fd_target_projection('/private/unknown/filename')
        need('/private' not in json.dumps(unknown) and unknown['raw_target_exported'] is False,
             'PRIVATE_FD_TARGET_EXPORTED')
    case('FD_closed_kernel_shape_unknown_path_hash_only',fd_public)
    case('oversize_FD_link_stays_failure',lambda:reject(
        'OBSERVED_CHILD_FD_TARGET_BOUND',lambda:fd_target_projection('x'*4097)))
    case('FD_numbers_preserve_standard_streams',lambda:same(fd_name_list(['2','0','17','1']),[0,1,2,17]))
    case('duplicate_FD_number_not_partial_success',lambda:reject(
        'OBSERVED_CHILD_FD_DUPLICATE',lambda:fd_name_list(['0','0'])))
    fields=['S','1']+['0']*17+['22']
    raw=('11 (synthetic ) comm) '+' '.join(fields)).encode()
    case('held_stat_uses_final_comm_parenthesis',lambda:same(require_held_child_stat(raw,sample),(11,1,22,'S')))
    case('held_proc_start_drift_not_admitted',lambda:reject(
        'HELD_CHILD_PROCESS_IDENTITY_CHANGED',lambda:require_held_child_stat(raw,{**sample,'start_ticks':23})))
    need(len(rows)==8 and len({x['name'] for x in rows})==8,'EXACT_EIGHT_CHILD_DETAIL_CONTROLS_REQUIRED')
    return rows

def execute():
    began=time.monotonic();began_ns=time.monotonic_ns();deadline=began+8;pool=None;phase='input_guard'
    result={'schema':'pocket4-baseline02-three-parent-child-detail-diagnostic-v1','ok':False,
            'error':None,'secondary_errors':[],'baseline_sha256':BASELINE_SHA,
            'qualification_sha256':QUALIFICATION_SHA,'expected_epoch_sha256':EPOCH_SHA,
            'original_Main_guard_source_unchanged':True,'original_unique_child_gate_unchanged':True,
            'Android_actions':0,'process_children_created':0,'external_signals':0,
            'namespace_entries':0,'App_or_task_actions':0,'files_written':0,
            'Main_runtime_requalified':False,'old_tasks_reauthorized':False,
            'cleanup_authority':False,'raw_private_baseline_or_cmdline_exported':False,
            'input_FDs':{},'observations':[], 'source_sha256':SOURCE_SHA256,
            'Status_or_Readiness_RPC':0,'action_lock_operations':0,
            'current_Main_runtime_admitted':False,'past_failure_parent_attributed':False,
            'child_fd_contents_read':False,'child_executable_contents_read':False}
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
        extra=child_detail_controls();result['controls']['cases']+=extra
        result['controls']['count']+=len(extra)
        need(result['controls']['count']==18,'EXACT_EIGHTEEN_DIAGNOSTIC_CONTROLS_REQUIRED')
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
        expected_identities={**b['all_seven_processes']['binding']['processes'],
                             'owner_intermediary':b['owner_lineage']['intermediary_process']}
        detail_budget={'children':0,'fd_links':0}
        for index in (1,2):
            phase='complete_fixed_parent_tables_'+str(index);tables={};details={};gates={};table_times={}
            record={'index':index,'started_monotonic_ns':time.monotonic_ns(),
                    'started_realtime_ns':time.time_ns(),'complete':False,
                    'tables':tables,'children':details,'original_gates':gates,'table_sample_times':table_times}
            result['observations'].append(record)
            for row in PARENTS:
                check();role=row['role'];identity_role='owner_intermediary' if role=='intermediary' else role
                expected=expected_identities[identity_role]
                need(e.process_identity(row['pid'])==expected,'FIXED_PARENT_CHANGED_BEFORE_TABLE')
                table_times[role]={'started_monotonic_ns':time.monotonic_ns(),'started_realtime_ns':time.time_ns()}
                tables[role]=c.children_sample(pool,parent_fds[role],row['pid'],check)
                table_times[role].update(ended_monotonic_ns=time.monotonic_ns(),ended_realtime_ns=time.time_ns())
                # The unchanged production policy still rejects every extra,
                # missing or substituted child. This is diagnostic observation.
                gates[role]=table_verdict(p,tables[role],row['pid'],row['child'])
                details[role]=inspect_direct_children(pool,c,e,g,tables[role],row,
                                                      expected_identities,check,detail_budget)
                need(e.process_identity(row['pid'])==expected,'FIXED_PARENT_CHANGED_AFTER_CHILD_DETAILS')
            record.update(complete=True,elapsed_ns=time.monotonic_ns()-began_ns,
                          ended_monotonic_ns=time.monotonic_ns(),ended_realtime_ns=time.time_ns())
        result['child_detail_budget_used']=detail_budget
        result['all_child_details_complete']=all(
            item['complete_stable_identity_observed'] and item['fd_observation'] is not None and
            item['fd_observation']['complete']
            for record in result['observations'] for items in record['children'].values() for item in items)
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
        need(len(raw)<=262144,'DIAGNOSTIC_PUBLIC_OUTPUT_BOUND')
        print(raw.decode('utf-8'),end='',flush=True)
    return 0 if result['ok'] else 1

def main():return execute()
