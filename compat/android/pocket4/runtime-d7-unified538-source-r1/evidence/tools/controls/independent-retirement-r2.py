"""Read-only qualification of D7's exact actual 334 tool tests and original bins."""
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import signal
import stat
import subprocess
import time
import traceback

R = Path('/data/pocket4-runtime-d7-unified538-20261113-e2a3-r1')
REPO = R/'source'
Q = R/'tools334-independent-retirement-r2'
HEAD = '273d1a2b554923b7b53e645560ddbe5999cbde9b'
TREE = 'cde7467f68d2de89f688431cafd494fed147e247'
BOOT = '14f92beb-43c6-4786-839e-b57307ae8048'
CG = Path('/sys/fs/cgroup')/Path('/proc/self/cgroup').read_text().strip().removeprefix('0::/')
os.umask(0o077)
assert os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 1000
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
assert CG.name.startswith('hepta-runtime-job-') and CG.name.endswith('.service')
os.sched_setaffinity(0, {8,9})
cap = subprocess.Popen(['/usr/bin/systemctl','--user','set-property','--runtime',CG.name,'MemorySwapMax=0'],
    stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'HOME':'/home/qian-qi','PATH':'/usr/bin:/bin',
    'XDG_RUNTIME_DIR':'/run/user/1000','DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/1000/bus'},start_new_session=True)
capfd = os.pidfd_open(cap.pid)
try:
    try: cap_out,cap_err = cap.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        signal.pidfd_send_signal(capfd,signal.SIGKILL);cap.communicate(timeout=5);raise
    poll=select.poll();poll.register(capfd,select.POLLIN)
    assert cap.returncode==0 and poll.poll(0)
finally:
    if cap.poll() is None: signal.pidfd_send_signal(capfd,signal.SIGKILL);cap.wait(timeout=5)
    os.close(capfd)
assert (CG/'memory.max').read_text().strip()=='2147483648' and (CG/'memory.swap.max').read_text().strip()=='0'
assert (CG/'cpu.max').read_text().split()==['200000','100000']
Q.mkdir()
report={'schema':'runtime-d7-exact1595-tools334-independent-retirement-v1','state':'RUNNING','errors':[],
        'head':HEAD,'tree':TREE,'boot_id':BOOT,'reader_pid':os.getpid(),'reader_cgroup':str(CG),
        'started_ns':time.time_ns(),'Cargo_or_tests_repeated':False,'release_binaries_rebuilt':0,
        'runtime289_tests_repeated':0,'Android_builds':0,'shared_AOSP_reads_or_writes':0,
        'runtime_qualified':False,'production_ready':False,'fixture_published_with_producer':False}
packet={};refs={}

def f9(s):
    return [getattr(s,k) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')]

def pinned(path, expected=None, links=1, maximum=32*1024**2):
    path=Path(path);assert path.resolve()==path
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        st=os.fstat(fd)
        assert stat.S_ISREG(st.st_mode) and st.st_uid==st.st_gid==1000 and st.st_size<=maximum
        assert links is None or st.st_nlink==links
        with os.fdopen(os.dup(fd),'rb') as stream:body=stream.read()
        assert len(body)==st.st_size and f9(st)==f9(os.fstat(fd))==f9(path.lstat())
        row={'path':str(path),'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'identity':f9(st)}
        if expected:
            assert all(row[k]==expected[k] for k in ('path','bytes','sha256','identity') if k in expected),str(path)
        return body,row
    finally:os.close(fd)

def include(name,path,expected=None):
    assert name not in packet and not Path(name).is_absolute() and '..' not in Path(name).parts
    body,row=pinned(path,expected)
    refs[str(path)]=row;packet[name]=dict(row,body_base64=__import__('base64').b64encode(body).decode())
    return body,row

def get_json(name,path,expected=None):
    body,row=include(name,path,expected);return json.loads(body),row

def save(path,value):
    with Path(path).open('x') as stream:
        json.dump(value,stream,sort_keys=True,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    return pinned(path)[1]

def no_pid(pid):
    assert type(pid) is int and pid>1 and pid!=os.getpid()
    try:fd=os.pidfd_open(pid)
    except ProcessLookupError:return
    else:os.close(fd);raise RuntimeError('an original PID remains allocated: '+str(pid))

def no_oom(text):
    events=dict((k,int(v)) for k,v in map(str.split,text.splitlines()))
    assert {'oom','oom_kill','oom_group_kill'}<=set(events)
    assert all(events[k]==0 for k in ('oom','oom_kill','oom_group_kill'))
    return events

try:
    failed,failed_ref=get_json('history/independent-r1-FAILED.json',R/'tools334-independent-retirement-r1/RESULT.json',
        {'bytes':1579,'sha256':'75d36de126429ce19adbab77ae97b09b50d52b88b7692c1577403d71592d7e64'})
    assert failed['state']=='FAILED' and len(failed['errors'])==1 and 'line 150' in failed['errors'][0]['traceback']
    previous_h=Path('/home/qian-qi/.local/state/hepta-runtime-mac-worker/jobs/1a1d75718a0-392-a53')
    old_docs={}
    for name in ('request','started','exit'):
        old_docs[name],_=get_json('history/independent-r1-'+name+'.json',previous_h/(name+'.json'))
        assert old_docs[name]['job_id']=='1a1d75718a0-392-a53' and old_docs[name]['launch_nonce']=='9149f4d0308333a2fc16c1077159b00e'
    assert old_docs['request']['request_digest']=='8021a32ec7238fd3704497c5254db9b2477f9f563722d2a5224e512091894ecb'
    assert old_docs['exit']['exit_code']==1 and old_docs['exit']['at_unix_ms']==1794614173670 and old_docs['exit']['output_complete'] is old_docs['exit']['output_durable'] is True
    for side,size in [('stdout',1026),('stderr',0)]:
        assert old_docs['exit']['log_bytes'][side]=={'seen':size,'stored':size}
        assert old_docs['exit']['log_errors'][side] is None and old_docs['exit']['log_synced'][side] is True and old_docs['exit']['log_truncated'][side] is False
    no_pid(failed['reader_pid']);no_pid(old_docs['started']['supervisor_pid'])
    assert not os.path.lexists(failed['reader_cgroup'])
    report['prior_read_size_failure_preserved']=failed_ref
    report['scoped_actual_harness_read_limit']='exact five recorded artifact sizes only; metadata32MiB unchanged'
    prior,prior_ref=get_json('prior-runtime/independent.json',R/'independent-retirement-r1/RESULT.json',
        {'bytes':7360,'sha256':'f64c29579d3c4b60a52201a8c8b6e9768119ce29f08e4b16cbdf9df24991ecdd'})
    assert prior['head']==HEAD and prior['tree']==TREE and prior['actual_ordinary_tests_passed']==289 and not prior['errors']
    normal,nref=get_json('normal/RESULT.json',R/'tools-normal334-r1/RESULT.json',
        {'bytes':75557,'sha256':'9b0c06c141bfbf4cee4ec765e6a3f437a2bfa7396c6b0276b90b8be4888bd0db'})
    dma,dref=get_json('dma/RESULT.json',R/'tools-dma334-r1/RESULT.json',
        {'bytes':122995,'sha256':'cb7147de2ad8a376f2136f241a63bd68af25bc51c56cac806eacdfa43553bac8'})
    assert normal['state']=='D7_333_ACTUAL_TOOL_TESTS_AND_EXISTING_FOUR_RELEASES_PRESERVED_DMA_PENDING' and not normal['errors']
    assert normal['recipe_commit']==HEAD and normal['recipe_tree']==TREE and normal['actual_distinct_tests_passed']==333
    assert normal['all_1595_producer_files_preserved'] and normal['whole1595_F9_preserved_including_failure_boundary'] and normal['all_four_original_release_F9_preserved']
    assert dma['state']=='ALL334_REGISTERED_SOURCE_UPDATER_AND_INTEGRATION_TESTS_ACTUALLY_PASSED' and dma['actual_distinct_tests_passed']==334 and not dma['errors']
    assert dma['prior333_actual_proof']==nref and dma['source_commit']=='ce79bbee67b3e2ea7abb110e1415e9ceceaa6471' and dma['source_tree']=='95c2eb6837a39a6ef62ae454c5d9767cf2066c53'
    assert dma['private_original_file_count']==103 and dma['private_original_files_unchanged'] and dma['final_original1595_and_four_bins_F9_boundary_passed']
    assert normal['release_binaries_rebuilt']==normal['runtime_tests_repeated']==dma['release_binaries_rebuilt']==dma['runtime_tests_repeated']==0
    assert normal['Android_builds']==dma['Android_builds']==0 and normal['production_ready'] is dma['production_ready'] is False
    normal_events=no_oom(normal['memory_events']);dma_events=no_oom(dma['memory_events'])
    assert 0<normal['memory_peak_bytes']<=4*1024**3 and 0<dma['memory_peak_bytes']<=4*1024**3
    catalog,catalog_ref=get_json('catalog.json',R/'tools334-catalog.json',
        {'bytes':31149,'sha256':'f0cef31c0597ddb9c1f0f42361b8b7014df76a4284412a744136e02e71e02abb'})
    helper=R/'tools334-test-terminal.py'
    include('controls/test-terminal.py',helper,{'bytes':10892,'sha256':'5839760e1804f5d4c8f345da8b71b9fc2d48a02e6efd9205535ed3f36787a69b'})
    spec=importlib.util.spec_from_file_location('d7_tools_terminal',helper);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert len(catalog['updater'])==288 and len(catalog['source'])==43 and catalog['all_harness_total']==334
    pids={normal['reader_pid'],dma['reader_pid']};commands={}
    for label,value in [('normal',normal),('dma',dma)]:
        commands[label]={}
        for row in value['commands']:
            assert row['name'] not in commands[label] and row['exit_code']==0 and row['timed_out'] is False and row['original_pidfd_retired'] is True
            commands[label][row['name']]=row;pids.add(row['pid'])
            for side in ('stdout','stderr'):
                include(label+'/'+row['name']+'.'+side,row[side]['path'],row[side])
    for name,expected,record_key,filtered in [
        ('updater-main-287-including-network',set(catalog['updater'])-{'image_policy::tests::repack_preserves_android_metadata_and_adbd'},'updater_main_287',1),
        ('original-erofs-metadata-repack',{'image_policy::tests::repack_preserves_android_metadata_and_adbd'},'original_erofs_repack',287),
        ('source-library-43',set(catalog['source']),'source_43',0),
        ('source-bin-no-tests',set(),'source_bin_zero',0),
        ('release-queue-original-cpp-2',set(catalog['release_queue']),'release_queue_2',0),
        ('source-doc-tests',set(),'source_doc_zero',0)]:
        cmd=commands['normal'][name];text=pinned(cmd['stdout']['path'],cmd['stdout'])[0].decode()
        actual=module.test_terminal(text,expected)
        assert actual==normal['test_runs'][record_key] and actual['filtered']==filtered
    assert 'native_bridge::tests::published_source_pin_fetches_and_verifies' in normal['test_runs']['updater_main_287']['names']
    cmd=commands['dma']['actual-original-dma-layout']
    assert module.test_terminal(pinned(cmd['stdout']['path'],cmd['stdout'])[0].decode(),set(catalog['dma_heap_layout']))==dma['actual_dma_layout']
    assert dma['actual_dma_layout']['filtered']==0
    cmd=commands['normal']['compile-all-harnesses'];messages=[json.loads(x) for x in pinned(cmd['stdout']['path'],cmd['stdout'])[0].decode().splitlines() if x]
    assert [x for x in messages if x.get('reason')=='build-finished']==[{'reason':'build-finished','success':True}] and messages[-1]=={'reason':'build-finished','success':True}
    assert not any(x.get('reason')=='compiler-message' and x.get('message',{}).get('level')=='error' for x in messages)
    artifacts=[x for x in messages if x.get('reason')=='compiler-artifact' and x.get('profile',{}).get('test') and x.get('executable')]
    assert len(artifacts)==5 and all(x['fresh'] is False for x in artifacts)
    wanted={('droidloom-update',('bin',)),('droidloom_source',('lib',)),('droidloom-source',('bin',)),('dma_heap_layout',('test',)),('release_queue',('test',))}
    assert {(x['target']['name'],tuple(x['target']['kind'])) for x in artifacts}==wanted
    harnesses=normal['compiled_harnesses'];assert len(harnesses)==5
    for row in harnesses:
        assert Path(row['artifact']['path']).parent==R/'target/debug/deps'
        pinned(row['artifact']['path'],row['artifact'],links=row['artifact']['identity'][5],maximum=row['artifact']['bytes'])
    assert {x['artifact']['path'] for x in harnesses}=={x['executable'] for x in artifacts}
    expected_runs=[('intentresolver-security-build','security-entry-help'),('aac-security-build','aac-security-entry-help'),('vendor-policy-bundle-build','vendor-bundle-entry-help')]
    for target,name in expected_runs:
        cmd=commands['normal'][name];assert cmd['argv']==[str(R/'bin/droidloom-update'),target,'--help']
        assert target in pinned(cmd['stdout']['path'],cmd['stdout'])[0].decode()
    source,sref=get_json('source/SOURCE-BEFORE.json',normal['source_before']['path'],normal['source_before'])
    assert len(source)==1595 and len({x['relative'] for x in source})==1595
    for row in source:
        assert Path(row['path'])==REPO/row['relative']
        body,current=pinned(row['path'],row)
        assert stat.S_IMODE(current['identity'][2])==int(row['git_mode'],8)&0o777
        assert hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()==row['git_blob']
    fixture=REPO/'.work/aosp-m2-source/external/minigbm'
    assert dma['only_fixture_outside1595']==str(fixture) and dma['fixture_published_with_producer'] is False
    originals=dma['private_original_files'];assert len(originals)==103
    for row in originals:
        assert Path(row['path'])==fixture/row['relative']
        body,current=pinned(row['path'],row)
        assert stat.S_IMODE(current['identity'][2])==int(row['git_mode'],8)&0o777
        assert hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()==row['git_blob']
    actual=set()
    for path in REPO.rglob('*'):
        if path.is_relative_to(REPO/'.git') or path.is_relative_to(fixture/'.git'):continue
        node=path.lstat();assert not stat.S_ISLNK(node.st_mode) and (stat.S_ISREG(node.st_mode) or stat.S_ISDIR(node.st_mode))
        if stat.S_ISREG(node.st_mode):actual.add(str(path))
    assert actual=={x['path'] for x in source}|{x['path'] for x in originals}
    bins=normal['release_binaries_before'];assert bins==prior['independent_single_link_0555_release_binaries']==dma['all_four_existing_release_binaries'] and len(bins)==4
    for name,row in bins.items():
        body,current=pinned(R/'bin'/name,row);assert stat.S_IMODE(current['identity'][2])==0o555
        assert body[:6]==b'\x7fELF\x02\x01' and int.from_bytes(body[18:20],'little')==62
    for row in normal['official_erofs_tools']:pinned(row['path'],row)
    for row in dma['parent_private_originals_preserved']:pinned(row['path'],row)
    h_records={};groups=[]
    for label,jobid,nonce,digest,finished,streams,unit,owned_path in [
        ('normal','1a1d751a90e-392-a4e','668fe30dfe5a4c175ca0a29aed20d8fc','ba20755aecbfc7e85b7cef2503432db9b26867a39ab05ad0e80b9325841c1edc',1794613883510,{'stdout':3729,'stderr':297},'p4-runtime-d7-tools334-normal-e2a3-r1.service',R/'TOOLS334-NORMAL-r1-RETIREMENT.json'),
        ('dma','1a1d75411a8-392-a50','0bda6933aa8d5fae3bc36353e930b3ea','c1119cca3abb581bdd64b039e57fd33553e8a8bc7b17877c7516ab7f69718011',1794613978051,{'stdout':1568,'stderr':290},'p4-runtime-d7-tools334-dma-layout-e2a3-r1.service',R/'TOOLS334-DMA-RETIREMENT.json')]:
        owned,owned_ref=get_json(label+'/OWNED-RETIREMENT.json',owned_path)
        assert owned['exit_code']==0 and owned['original_pidfd_retired'] is owned['cgroup_absent'] is True
        assert set(owned['unit_show'].splitlines())=={'MainPID=0','ControlGroup=','LoadState=not-found','ActiveState=inactive'}
        assert owned['boot_id']==BOOT;pids.update({owned['reader_pid'],owned['systemd_run_pid']})
        base=Path('/home/qian-qi/.local/state/hepta-runtime-mac-worker/jobs')/jobid;docs={};h_records[label]={}
        for name in ('request','started','exit'):
            docs[name],h_records[label][name]=get_json('durable/'+label+'-'+name+'.json',base/(name+'.json'))
            assert docs[name]['job_id']==jobid and docs[name]['launch_nonce']==nonce
        assert docs['request']['request_digest']==digest
        final=docs['exit'];assert final['exit_code']==0 and final['at_unix_ms']==finished
        assert final['output_complete'] is final['output_durable'] is True and final['timed_out'] is final['cancelled'] is False
        for side,size in streams.items():
            assert final['log_bytes'][side]=={'seen':size,'stored':size} and final['log_errors'][side] is None and final['log_synced'][side] is True and final['log_truncated'][side] is False
        pids.add(docs['started']['supervisor_pid'])
        groups.append('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/'+unit)
        groups.extend('/sys/fs/cgroup/'+prefix+'/hepta-runtime-job-'+jobid+'.service' for prefix in ('user.slice/user-1000.slice/user@1000.service/app.slice','system.slice'))
    assert len(groups)==6 and all(not os.path.lexists(x) for x in groups)
    for pid in sorted(pids):no_pid(pid)
    for name in ('tools334-normal-worker-r1.py','tools334-normal-launch-r1.py','tools334-dma-worker-r1.py','tools334-dma-launch-r1.py'):
        include('controls/'+name,R/name)
    include('controls/independent-retirement-r2.py',__file__)
    for name,row in refs.items():pinned(name,row)
    for row in source+originals:pinned(row['path'],row)
    for row in bins.values():pinned(row['path'],row)
    report.update(state='ALL334_D7_TOOL_TESTS_AND_1595_SOURCE_FOUR_RELEASES_INDEPENDENTLY_VERIFIED_AND_RETIRED',
        normal=nref,dma=dref,prior289_runtime_retirement=prior_ref,test_catalog=catalog_ref,
        actual_distinct_tool_tests_passed=334,actual_normal_commands=len(normal['commands']),actual_DMA_commands=len(dma['commands']),
        five_fresh_harnesses=normal['compiled_harnesses'],compiled_harness_terminal_exactly_one_success=True,
        complete_source=sref,all1595_source_Git_blobs_modes_and_F9_preserved=True,
        complete_original_fixture_files=103,fixture_commit=dma['source_commit'],fixture_tree=dma['source_tree'],fixture_root=str(fixture),
        original103_fixture_Git_blobs_modes_and_F9_preserved=True,producer_membership_only1595_plus_exact103_fixture=True,
        four_original_0555_release_binaries=bins,all_four_release_F9_preserved=True,
        fresh_original_PIDFD_ESRCH=sorted(pids),original_cgroups_absent=groups,
        all_original_command_logs_whole_SHA_and_F9_verified=True,all_original_OOM_events_zero=True,
        normal_memory_events=normal_events,DMA_memory_events=dma_events,durable_H_envelopes=h_records,
        public_packet_members_before_report=len(packet))
except BaseException as error:
    report['state']='FAILED';report['errors'].append({'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()})
finally:
    report['finished_ns']=time.time_ns();report['memory_events']=(CG/'memory.events').read_text();report['memory_peak_bytes']=int((CG/'memory.peak').read_text())
    no_oom(report['memory_events'])
    result=save(Q/'RESULT.json',report)
    publication=None
    if report['state']!='FAILED':
        include('independent/RESULT.json',Q/'RESULT.json',result)
        raw=(json.dumps({'schema':'runtime-d7-tools334-public-evidence-v1','head':HEAD,'tree':TREE,'files':packet},sort_keys=True,separators=(',',':'))+'\n').encode()
        path=Q/'PUBLICATION-INPUTS-r1.json.gz'
        with path.open('xb') as stream:stream.write(gzip.compress(raw,mtime=0));stream.flush();os.fsync(stream.fileno())
        publication=pinned(path)[1]
    print(json.dumps({'state':report['state'],'result':result,'publication':publication,'PID_count':len(report.get('fresh_original_PIDFD_ESRCH',[])),'errors':report['errors']}),flush=True)
raise SystemExit(1 if report['state']=='FAILED' else 0)
