"""Explicit current profile data for unchanged proven Linux custody/resource helpers."""
import copy,hashlib,json,os,resource,time
ORIGINAL_PROFILE={'name': 'ai395-native-source600-high22g-memory24g-cpu8-jobs6-go5g2-combined58g-work96g-peer120g-sharedreserve32g-v2', 'build_memory_max_bytes': 25769803776, 'build_memory_high_bytes': 23622320128, 'memory_swap_max_bytes': 0, 'cpu_quota_percent': 800, 'cpu_affinity': [8, 9, 10, 11, 12, 13, 14, 15], 'normal_requested_jobs': 6, 'go_memory_limit_bytes': 5368709120, 'go_max_procs': 2, 'go_gc_percent': 50, 'host_reserve_bytes': 8589934592, 'fresh_memavailable_minimum_bytes': 62277025792, 'initial_build_work_budget_bytes': 103079215104, 'shared_disk_reserve_bytes': 34359738368, 'fresh_disk_minimum_bytes': 266287972352, 'reserved_peer_kernel_growth_bytes': 128849018880, 'normal_build_timeout_seconds': 21600, 'inner_runtime_max_seconds': 22800, 'outer_timeout_seconds': 28800, 'outer_memory_max_bytes': 2147483648, 'outer_cpu_quota_percent': 200}
CURRENT_PROFILE={'name': 'ai395-native643-high10g-memory12g-cpu2-jobs2-go5g2-fresh24g-host12g-work96g-peer120g-shared32g-r1', 'build_memory_max_bytes': 12884901888, 'build_memory_high_bytes': 10737418240, 'memory_swap_max_bytes': 0, 'cpu_quota_percent': 200, 'cpu_affinity': [8, 9], 'normal_requested_jobs': 2, 'go_memory_limit_bytes': 5368709120, 'go_max_procs': 2, 'go_gc_percent': 50, 'host_reserve_bytes': 12884901888, 'fresh_memavailable_minimum_bytes': 25769803776, 'initial_build_work_budget_bytes': 103079215104, 'shared_disk_reserve_bytes': 34359738368, 'fresh_disk_minimum_bytes': 266287972352, 'reserved_peer_kernel_growth_bytes': 128849018880, 'normal_build_timeout_seconds': 21600, 'inner_runtime_max_seconds': 22800, 'outer_timeout_seconds': 28800, 'outer_memory_max_bytes': 2147483648, 'outer_cpu_quota_percent': 200}
PLAN_SHA='f6d0437be4ea9e2f2022de46006e370e92a6b39a5255917e7af27299f3af68b3'
def need(v,m):
    if not v:raise RuntimeError(m)
def exact(left,right,message):
    need(json.dumps(left,sort_keys=True,separators=(',',':'),allow_nan=False)==json.dumps(right,sort_keys=True,separators=(',',':'),allow_nan=False),message)
def validate_historical_profile(profile):
    exact(profile,ORIGINAL_PROFILE,'original historical24GiB profile differs')
def budget_snapshot(support,cgroup,*,inner):
    exact(support.PROFILE,CURRENT_PROFILE,'current profile changed before actual resource observation')
    row={name:(cgroup/name).read_text().strip()for name in('memory.max','memory.swap.max','memory.swap.current',
         'cpu.max','memory.current','memory.peak','memory.events','memory.high','memory.stat')}
    row.update(affinity=sorted(os.sched_getaffinity(0)),nice=os.getpriority(os.PRIO_PROCESS,0),
               file_size_rlimit=list(resource.getrlimit(resource.RLIMIT_FSIZE)))
    maximum=CURRENT_PROFILE['build_memory_max_bytes'if inner else'outer_memory_max_bytes']
    need(row['memory.max']==str(maximum)and row['memory.swap.max']==row['memory.swap.current']=='0',
         'actual current memory cap/no-swap differs')
    need(row['cpu.max']=='200000 100000','actual current CPU200 quota differs')
    if inner:
        need(row['memory.high']==str(CURRENT_PROFILE['build_memory_high_bytes']),
             'actual current10GiB early reclaim boundary differs')
        row['memory_stat_summary']=support.memory_stat_summary(row['memory.stat'])
        need(row['affinity']==CURRENT_PROFILE['cpu_affinity'],'actual current affinity differs')
    need(row['nice']>=10 and row['file_size_rlimit'][0]==resource.RLIM_INFINITY,
         'actual nice/unlimited-file boundary differs')
    return row


def admission(support,root):
    exact(support.PROFILE,CURRENT_PROFILE,'current profile changed before actual admission')
    row={'observed_ns':time.time_ns(),'memavailable_bytes':support.memavailable(),'disk_free_bytes':support.disk_free(root)}
    need(row['memavailable_bytes']>=CURRENT_PROFILE['fresh_memavailable_minimum_bytes'],
         'fresh current12GiB full plus12GiB host reserve unavailable')
    need(row['disk_free_bytes']>=CURRENT_PROFILE['fresh_disk_minimum_bytes'],
         'original96GiB work plus120GiB peer and32GiB shared disk reserve unavailable')
    return row


def configure(support,plan_reference):
    actual,raw=support.pinned(plan_reference,1024**2,contents=True)
    need(actual['bytes']==3481 and actual['sha256']==PLAN_SHA and hashlib.sha256(raw).hexdigest()==PLAN_SHA,
         'exact root-reviewed explicit low-memory full plan changed')
    plan=json.loads(raw);wanted={'memory_max_bytes':12*1024**3,'memory_high_bytes':10*1024**3,
       'memory_swap_max_bytes':0,'cpu_quota_percent':200,'cpu_affinity':[8,9],'jobs':2,
       'fresh_memavailable_minimum_bytes':24*1024**3,'monitor_memavailable_minimum_bytes':12*1024**3,
       'go_runtime_limit_bytes':5*1024**3,'go_max_procs':2,'go_gc_percent':50,'go_observed_num_cpu':2}
    need(plan['schema']=='p4-native643-full-low-memory-resource-plan-v1'
         and plan['full_build_authorized_by_this_document']is False,'the plan is not full dispatch authorization')
    exact(plan['required_profile'],wanted,'precise approved low-memory profile required')
    need(set(support.PROFILE)==set(ORIGINAL_PROFILE),'complete original profile key set required')
    encoded=json.dumps(support.PROFILE,sort_keys=True,separators=(',',':'),allow_nan=False)
    need(encoded in(json.dumps(p,sort_keys=True,separators=(',',':'),allow_nan=False)for p in(ORIGINAL_PROFILE,CURRENT_PROFILE)),
         'foreign or partially changed runtime profile')
    support.PROFILE=copy.deepcopy(CURRENT_PROFILE);support.validate_profile(support.PROFILE)
    support.budget_snapshot=lambda cgroup,inner:budget_snapshot(support,cgroup,inner=inner)
    support.admission=lambda root:admission(support,root)
    return {'resource_plan':actual,'resource_profile':copy.deepcopy(CURRENT_PROFILE),
            'producer_Go_budget_unchanged':True,'actual_Go_NumCPU_must_equal':2,
            'full_builds_started':0,'actual_execution_authorized_by_plan':False}
