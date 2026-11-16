import os, sys, json, hashlib, stat, subprocess, select, signal, time, traceback, re, shutil, importlib.util
from pathlib import Path

R = Path('/data/pocket4-runtime-d7-unified538-20261113-e2a3-r1')
OLD = Path('/data/pocket4-intentresolver-security-normal-20261113-e2a3-r3')
E = Path('/data/pocket4-erofs194-official-builder-20261113-e2a3-r1')
repo = R/'source'
Q = R/'tools-normal334-r1'
HEAD = '273d1a2b554923b7b53e645560ddbe5999cbde9b'
TREE = 'cde7467f68d2de89f688431cafd494fed147e247'
UNIT = 'p4-runtime-d7-tools334-normal-e2a3-r1.service'
os.umask(0o077)
assert os.getuid() == 1000
cg = next(x.split(':',2)[2] for x in Path('/proc/self/cgroup').read_text().splitlines() if x.startswith('0::'))
cgp = Path('/sys/fs/cgroup')/cg.lstrip('/')
assert cg.endswith('/'+UNIT)
assert (cgp/'memory.max').read_text().strip() == '4294967296'
assert (cgp/'memory.swap.max').read_text().strip() == '0'
assert os.sched_getaffinity(0) == {8,9}
assert (cgp/'cpu.max').read_text().split() == ['200000','100000']
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == '14f92beb-43c6-4786-839e-b57307ae8048'
Q.mkdir(); (Q/'tmp').mkdir()
report = {'schema':'runtime-d7-exact1595-tools334-actual-harness-qualification-v1','state':'RUNNING','recipe_commit':HEAD,'recipe_tree':TREE,
          'base_commit':'fbb235628023f5fb5d9e47064a6d2884d23534bc','runtime_tests_repeated':0,'release_binaries_rebuilt':0,'reader_pid':os.getpid(),'commands':[],'test_runs':{},'errors':[],
          'runtime_qualified':False,'production_ready':False,'Android_builds':0,'APK_installs':0,'shared_AOSP_writes':0,
          'started_ns':time.time_ns(),'cgroup':str(cgp),'invocation_id':os.environ.get('INVOCATION_ID')}

def f9(s):
    return [getattr(s,k) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')]

def pinned(p, expected=None, independent=True):
    p=Path(p)
    assert p.resolve() == p, ('alias',str(p))
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        s=os.fstat(fd)
        assert stat.S_ISREG(s.st_mode) and (not independent or s.st_nlink == 1)
        h=hashlib.sha256(); chunks=[]; off=0
        while off<s.st_size:
            b=os.pread(fd,min(1048576,s.st_size-off),off); assert b
            h.update(b);chunks.append(b);off+=len(b)
        assert f9(s)==f9(os.fstat(fd))==f9(p.lstat())
        value={'path':str(p),'bytes':off,'sha256':h.hexdigest(),'identity':f9(s)}
        if expected:
            assert all(value[k]==expected[k] for k in ('bytes','sha256')),str(p)
        return b''.join(chunks),value
    finally: os.close(fd)

def ref(p, independent=False): return pinned(p,independent=independent)[1]

def write_json(p,value):
    with Path(p).open('x') as f:
        json.dump(value,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    return ref(p)

env=dict(os.environ,PATH=str(E/'install/bin')+':'+str(Q/'host-tools/usr/bin')+':/home/qian-qi/.cargo/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
         LD_LIBRARY_PATH=str(E/'dependency-root/usr/lib/x86_64-linux-gnu'),CARGO_HOME=str(R/'cargo-home'),CARGO_TARGET_DIR=str(R/'target'),
         CARGO_BUILD_JOBS='2',CARGO_TERM_COLOR='never',TMPDIR=str(Q/'tmp'),GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',GIT_TERMINAL_PROMPT='0',LC_ALL='C')

def run(name,args,limit=600,extra_env=None):
    op=Q/(name+'.stdout');ep=Q/(name+'.stderr');started=time.time_ns();timed_out=False
    with op.open('xb') as out,ep.open('xb') as err:
        child=subprocess.Popen(args,cwd=repo,env=env if not extra_env else dict(env,**extra_env),stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
        fd=os.pidfd_open(child.pid)
        try:
            try: code=child.wait(timeout=limit)
            except subprocess.TimeoutExpired:
                timed_out=True;os.killpg(child.pid,signal.SIGTERM)
                try:code=child.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);code=child.wait(timeout=5)
            poll=select.poll();poll.register(fd,select.POLLIN);retired=bool(poll.poll(0));assert retired
        finally:os.close(fd)
    row={'name':name,'argv':args,'pid':child.pid,'exit_code':code,'timed_out':timed_out,'original_pidfd_retired':retired,
         'started_ns':started,'ended_ns':time.time_ns(),'stdout':ref(op),'stderr':ref(ep)}
    report['commands'].append(row)
    print(json.dumps({'event':'command_complete','name':name,'exit_code':code,'stdout_bytes':row['stdout']['bytes'],'stderr_bytes':row['stderr']['bytes']}),flush=True)
    assert code==0 and not timed_out,(name,code,timed_out)
    return op.read_text()

def snapshot(name):
    raw=run(name,['git','ls-tree','-rz','HEAD'])
    rows=[]
    for entry in raw.split('\0'):
        if not entry:continue
        meta,relative=entry.split('\t',1);mode,kind,blob=meta.split()
        assert kind=='blob' and mode in ('100644','100755')
        path=Path(relative);assert not path.is_absolute() and '..' not in path.parts and '.git' not in path.parts
        b,r=pinned(repo/path)
        assert stat.S_IMODE(r['identity'][2])==int(mode,8)&0o777
        assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==blob,relative
        rows.append(dict(r,relative=relative,git_blob=blob,git_mode=mode))
    assert len(rows)==1595 and len({x['relative'] for x in rows})==1595
    actual=set()
    for path in repo.rglob('*'):
        relative=path.relative_to(repo)
        if relative.parts[0]=='.git':continue
        st=path.lstat();assert not stat.S_ISLNK(st.st_mode) and (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode))
        if stat.S_ISREG(st.st_mode):actual.add(relative.as_posix())
    assert actual=={x['relative'] for x in rows},'only the complete original1595 producer may exist before DMA fixture staging'
    return rows

def catalog(name,binary,expected):
    text=run(name,[str(binary),'--list','--format=terse'])
    names=[]
    for line in text.splitlines():
        assert line.endswith(': test'),(name,line)
        names.append(line[:-6])
    assert len(names)==len(set(names)) and set(names)==set(expected),(name,len(names),set(names)^set(expected))
    return names

before=None; release_before=None; erofs_before=[]
try:
    retired,retired_ref=pinned(R/'independent-retirement-r1/RESULT.json',{'bytes':7360,'sha256':'f64c29579d3c4b60a52201a8c8b6e9768119ce29f08e4b16cbdf9df24991ecdd'})
    previous=json.loads(retired)
    assert previous['state']=='ALL289_ACTUAL_ORDINARY_TESTS_FOUR_FRESH_RELEASES_AND_ALL3152_SOURCE_FILES_INDEPENDENTLY_RETIRED' and not previous['errors']
    assert previous['head']==HEAD and previous['tree']==TREE and previous['actual_ordinary_tests_passed']==289
    assert previous['all1595_candidate_F9_Gitblobs_modes_preserved'] and previous['all1557_parent_F9_Gitblobs_modes_preserved']
    assert all(not os.path.lexists(p) for p in previous['cgroups_absent'])
    for pid in previous['original_PIDs_fresh_ESRCH']:
        try:fd=os.pidfd_open(pid)
        except ProcessLookupError:continue
        else:os.close(fd);raise RuntimeError('prior runtime PID is still allocated')
    normal_raw,prior_normal_ref=pinned(R/'qualification-normal-r1/RESULT.json',previous['normal_result'])
    prior_normal=json.loads(normal_raw)
    original_source,original_source_ref=pinned(prior_normal['source_before']['path'],prior_normal['source_before'])
    original_source=json.loads(original_source);assert len(original_source)==1595
    release_before=previous['independent_single_link_0555_release_binaries']
    assert set(release_before)=={'droidloom-source','droidloom-update','droidloomd','droidloom-supervisor'}
    for name,row in release_before.items():
        raw,now=pinned(R/'bin'/name,row);assert now==row and stat.S_IMODE(now['identity'][2])==0o555
    report['prior289_and_four_fresh_release_proof']=retired_ref
    report['release_binaries_before']=release_before
    report['prior_runtime_normal']=prior_normal_ref
    report['prior_source_baseline']=original_source_ref
    catalog_raw,catalog_ref=pinned(R/'tools334-catalog.json',{'bytes':31149,'sha256':'f0cef31c0597ddb9c1f0f42361b8b7014df76a4284412a744136e02e71e02abb'})
    expected=json.loads(catalog_raw);report['test_catalog']=catalog_ref
    assert expected['main_source_total']==331 and expected['all_harness_total']==334
    assert len(expected['updater'])==288 and len(expected['source'])==43
    helper=R/'tools334-test-terminal.py'
    assert hashlib.sha256(helper.read_bytes()).hexdigest()=='5839760e1804f5d4c8f345da8b71b9fc2d48a02e6efd9205535ed3f36787a69b'
    spec=importlib.util.spec_from_file_location('audio_terminal',helper);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    terminal=module.test_terminal
    assert run('initial-head',['git','rev-parse','HEAD']).strip()==HEAD
    assert run('initial-tree',['git','rev-parse','HEAD^{tree}']).strip()==TREE
    assert not run('initial-status',['git','status','--porcelain'])
    run('composite-diff-check',['git','diff','fbb235628023f5fb5d9e47064a6d2884d23534bc','HEAD','--check'])
    before=snapshot('initial-source-tree')
    assert {x['relative']:{k:x[k] for k in ('path','bytes','sha256','identity')} for x in before}==original_source
    report['source_before']=write_json(Q/'SOURCE-BEFORE.json',before)
    assert next(x for x in before if x['relative']=='Cargo.lock')['sha256']=='ca5300907a8e609ac0340d016ecfe7b4292bf45fe5ab3cbe8dd0c013f12a2285'
    available=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
    assert available>=12*1024**3 and shutil.disk_usage(R).free>=6*1024**3
    cache_raw,cache_ref=pinned(prior_normal['public_registry_cache_copy']['path'],prior_normal['public_registry_cache_copy'])
    cache=json.loads(cache_raw);assert len(cache['copied'])==240 and cache['credential_files_read_or_copied']==0
    for row in cache['copied']:
        dest=Path(row['destination']['path']);relative=dest.relative_to(R/'cargo-home')
        assert relative.parts[0]=='registry' and not any('credential' in x.lower() for x in relative.parts)
        _,actual=pinned(dest,row['destination']);assert actual==row['destination']
    assert (R/'target').is_dir() and (R/'cargo-home').is_dir()
    report['existing_private_public_registry_cache']=cache_ref
    pkg,pkgref=pinned(OLD/'official-attr.deb',{'bytes':25318,'sha256':'9242ea4780a656226ce000e0d78cbdda8dc376f9ca3bff2436aaa89b2a48aaf0'})
    with (Q/'official-attr.deb').open('xb') as f:f.write(pkg)
    run('private-attr-extract',['dpkg-deb','--extract',str(Q/'official-attr.deb'),str(Q/'host-tools')])
    assert ref(OLD/'official-attr.deb',True)==pkgref
    erofs,erofs_ref=pinned(E/'qualification-r2/RESULT.json',{'bytes':2176,'sha256':'851cdfe08c053f37a7e86f89aa6f84f589dec09595e5a80afae9606c8e192cb8'})
    assert json.loads(erofs)['state']=='OFFICIAL_EROFSTOOLS_ACTUAL_METADATA_REPACK_TEST_PASSED'
    report['actual_erofs_tool_qualification']=erofs_ref
    for wanted in json.loads(erofs)['tools'].values():
        _,er=pinned(wanted['path'],wanted);erofs_before.append(er)
    report['official_erofs_tools']=erofs_before
    cargo='/home/qian-qi/.cargo/bin/cargo'
    built=run('compile-all-harnesses',[cargo,'test','--locked','--offline','-j','2','-p','droidloom-update','-p','droidloom-source','--no-run','--message-format=json'],1200)
    messages=[json.loads(line) for line in built.splitlines() if line]
    assert messages[-1]=={'reason':'build-finished','success':True}
    artifacts={}
    for line in built.splitlines():
        row=json.loads(line)
        if row.get('reason')=='compiler-artifact' and row.get('profile',{}).get('test') and row.get('executable'):
            assert row['fresh'] is False, 'all five D7 tool test harnesses must be freshly compiled'
            key=(row['target']['name'],tuple(row['target']['kind']))
            assert key not in artifacts
            p=Path(row['executable']);assert p.parent==R/'target/debug/deps'
            artifacts[key]=p
    wanted={('droidloom-update',('bin',)),('droidloom_source',('lib',)),('droidloom-source',('bin',)),('dma_heap_layout',('test',)),('release_queue',('test',))}
    assert set(artifacts)==wanted,set(artifacts)
    report['compiled_harnesses']=[{'name':k[0],'kind':list(k[1]),'artifact':ref(v)} for k,v in artifacts.items()]
    update=artifacts[('droidloom-update',('bin',))];source=artifacts[('droidloom_source',('lib',))]
    sourcebin=artifacts[('droidloom-source',('bin',))];release=artifacts[('release_queue',('test',))];dma=artifacts[('dma_heap_layout',('test',))]
    catalog('updater-catalog',update,expected['updater']);catalog('source-catalog',source,expected['source'])
    catalog('source-bin-catalog',sourcebin,[]);catalog('release-queue-catalog',release,expected['release_queue'])
    catalog('dma-heap-catalog',dma,expected['dma_heap_layout'])
    image_test='image_policy::tests::repack_preserves_android_metadata_and_adbd'
    network_test='native_bridge::tests::published_source_pin_fetches_and_verifies'
    ignored=run('updater-ignored-catalog',[str(update),'--list','--ignored','--format=terse'])
    assert ignored==network_test+': test\n'
    main_expected=set(expected['updater'])-{image_test}
    text=run('updater-main-287-including-network',[str(update),'--include-ignored','--skip',image_test,'--test-threads=1','--color','never'],600)
    report['test_runs']['updater_main_287']=terminal(text,main_expected);assert report['test_runs']['updater_main_287']['filtered']==1
    assert network_test in report['test_runs']['updater_main_287']['names']
    # Invoke the original test's documented fakeroot branch directly. This
    # avoids conflating its recursive harness with a second distinct test.
    text=run('original-erofs-metadata-repack',['fakeroot','--',str(update),'--exact',image_test,'--test-threads=2','--color','never'],90,{'DROIDLOOM_IMAGE_POLICY_TEST':'1'})
    report['test_runs']['original_erofs_repack']=terminal(text,{image_test});assert report['test_runs']['original_erofs_repack']['filtered']==287
    text=run('source-library-43',[str(source),'--test-threads=1','--color','never'],300)
    report['test_runs']['source_43']=terminal(text,expected['source'])
    text=run('source-bin-no-tests',[str(sourcebin),'--test-threads=1','--color','never'],60)
    report['test_runs']['source_bin_zero']=terminal(text,[])
    text=run('release-queue-original-cpp-2',[str(release),'--test-threads=2','--color','never'],90)
    report['test_runs']['release_queue_2']=terminal(text,expected['release_queue'])
    text=run('source-doc-tests',[cargo,'test','--locked','--offline','-j','2','-p','droidloom-source','--doc','--','--test-threads=1','--color','never'],90)
    report['test_runs']['source_doc_zero']=terminal(text,[])
    report['qualified_existing_release_updater']=release_before['droidloom-update']
    report['qualified_existing_release_source']=release_before['droidloom-source']
    run('security-entry-help',[str(R/'bin/droidloom-update'),'intentresolver-security-build','--help'])
    run('aac-security-entry-help',[str(R/'bin/droidloom-update'),'aac-security-build','--help'])
    run('vendor-bundle-entry-help',[str(R/'bin/droidloom-update'),'vendor-policy-bundle-build','--help'])
    after=snapshot('final-source-tree');assert before==after
    assert run('final-head',['git','rev-parse','HEAD']).strip()==HEAD
    assert not run('final-status',['git','status','--porcelain'])
    report['all_1595_producer_files_preserved']=True
    report['actual_distinct_tests_passed']=333
    report['remaining_harness']={'name':'dma_heap_layout','registered':expected['dma_heap_layout'],'executed':False,
         'reason':'Run separately with a complete original pinned minigbm checkout; never counted as passed or hidden as nested output.'}
    report['state']='D7_333_ACTUAL_TOOL_TESTS_AND_EXISTING_FOUR_RELEASES_PRESERVED_DMA_PENDING'
except BaseException as error:
    report['state']='FAILED';report['errors'].append({'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()})
finally:
    try:
        if before is not None:
            for row in before:
                _,now=pinned(row['path'],row)
                assert now=={k:row[k] for k in now}, row['relative']
            report['whole1595_F9_preserved_including_failure_boundary']=True
        if release_before is not None:
            for row in release_before.values():assert pinned(row['path'],row)[1]==row
            report['all_four_original_release_F9_preserved']=True
        for row in erofs_before:assert pinned(row['path'],row)[1]==row
    except BaseException as error:
        report['state']='FAILED';report['errors'].append({'stage':'final_original_boundary','type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()})
    report['finished_ns']=time.time_ns();report['memory_events']=(cgp/'memory.events').read_text();report['memory_peak_bytes']=int((cgp/'memory.peak').read_text())
    result=write_json(Q/'RESULT.json',report)
    print(json.dumps({'state':report['state'],'result':result,'actual_distinct_tests_passed':report.get('actual_distinct_tests_passed'),'errors':report['errors']}),flush=True)
raise SystemExit(0 if report['state']=='D7_333_ACTUAL_TOOL_TESTS_AND_EXISTING_FOUR_RELEASES_PRESERVED_DMA_PENDING' else 1)
