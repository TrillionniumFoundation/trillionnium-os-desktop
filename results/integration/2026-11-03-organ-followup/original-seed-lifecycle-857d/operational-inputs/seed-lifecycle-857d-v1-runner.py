import base64, hashlib, json, os, pathlib, re, subprocess, sys, time

BASE = pathlib.Path('/data/trill-organ-owner-20261103')
BUILD = BASE/'appserver-signal-component-v1/result.json'
OUTPUT = BASE/'seed-lifecycle-857d-v1'
OUTPUT.mkdir(mode=0o700)
expected_sha, payload = sys.argv[1], json.loads(sys.argv[2])
TEST = 'product_root::seed::tests::actual_seed_start_resume_closes_client_and_reaps_first_signal_child'
result = {'schema':'trill.original-root.seed-lifecycle-execution.v1','status':'running',
          'scope':'actual original seed component only; mixed component sources, no product acceptance',
          'commands':[],'production_qualified':False,'exact_test':TEST,'build_receipt_sha256':expected_sha}

def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def save():
    tmp=OUTPUT/'result.tmp';tmp.write_text(json.dumps(result,indent=2)+'\n');os.replace(tmp,OUTPUT/'result.json')

def run(name,command,limit):
    result['running']=name;save()
    out,err=OUTPUT/(name+'.stdout.log'),OUTPUT/(name+'.stderr.log')
    started=time.monotonic()
    with out.open('xb') as stdout,err.open('xb') as stderr:
        done=subprocess.run(command,stdout=stdout,stderr=stderr,timeout=limit)
    result['commands'].append({'name':name,'argv':command,'exit_code':done.returncode,
        'seconds':round(time.monotonic()-started,3),'stdout':str(out),'stderr':str(err),
        'stdout_sha256':sha(out),'stderr_sha256':sha(err)})
    result.pop('running',None);save()
    return done.returncode,out,err

attempted=False
try:
    assert os.getuid()==1000 and os.geteuid()==1000
    assert sha(BUILD)==expected_sha
    built=json.loads(BUILD.read_text())
    assert built['status']=='components_built_seed_not_run' and built['production_qualified'] is False
    assert built['sources']['hepta']['head']=='857d8f61b96453c06a7f93dfba79dcdebca31bf8'
    assert built['sources']['desktop']['head']=='92a06c4b4b041a9e94d83480bc2c4cdcd6afa3d2'
    assert built['seed_test_binary']['exact_test_listed_count']==1
    assert all(not v['status'] for v in built['sources_after'].values())
    result['components']={key:built[key] for key in ('appserver_binary','seed_test_binary')}
    result['host_before']={'io_pressure':pathlib.Path('/proc/pressure/io').read_text(),
        'memory_pressure':pathlib.Path('/proc/pressure/memory').read_text(),'at_unix_ms':time.time_ns()//1000000}
    code,out,err=run('root-component-stage',['/usr/bin/sudo','-n','--','/usr/bin/python3','-I','-c',
        payload['root_stage'],json.dumps(result['components'])],90)
    assert code==0,'explicit component staging failed'
    staged=json.loads(out.read_text());result['staging']=staged;save()
    command=['/usr/bin/sudo','-n','--','/usr/bin/env','-i','PATH=/usr/bin:/bin','LANG=C.UTF-8',
        'TRILL_ROOT_SEED_TEST_CONFIG='+staged['config'],'/usr/bin/unshare','--mount','--propagation','private','--',
        staged['copied']['seed_test_binary']['path'],'--exact',TEST,'--ignored','--nocapture','--test-threads=1']
    attempted=True
    code,out,err=run('actual-original-seed-test',command,180)
    result['test_exit_code']=code
    text=out.read_text()+err.read_text()
    summary=re.findall(r'test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out',text)
    result['libtest_summaries']=summary
    observed,obsout,obserr=run('new-prefix-read-only-postmortem',['/usr/bin/sudo','-n','--',
        '/usr/bin/python3','-I','-c',payload['postmortem']],30)
    assert observed==0,'own-prefix postmortem failed'
    postmortem=json.loads(obsout.read_text())
    saved=[]
    for item in postmortem['files']:
        data=base64.b64decode(item['base64'],validate=True)
        assert len(data)==item['size'] and hashlib.sha256(data).hexdigest()==item['sha256']
        relative=pathlib.PurePosixPath(item['path'])
        assert not relative.is_absolute() and '..' not in relative.parts
        destination=OUTPUT/'prefix-evidence'/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        with destination.open('xb') as f:f.write(data)
        saved.append({k:v for k,v in item.items() if k!='base64'})
    result['prefix_evidence']=saved
    result['authority_state_exists']=postmortem['authority_state_exists']
    assert code==0,'actual original seed test failed; preserve original fixed-bound error'
    assert len(summary)==1 and tuple(summary[0][:5])==('ok','1','0','0','0'),summary
    assert TEST in text
    observation_path=OUTPUT/'prefix-evidence/admin/seed-lifecycle-observation.json'
    observation=json.loads(observation_path.read_text())
    assert observation['app_server_sha256']==built['appserver_binary']['sha256']
    assert observation['app_server']==staged['copied']['appserver_binary']['path']
    assert observation['production_qualified'] is False and observation['original_child_termination_deadline_ms']==10000
    for key in ('original_seed_create_returned','seed_socket_retired','authority_state_absent','no_session_or_turn_submitted_by_fixture','fresh_mount_detached'):
        assert observation[key] is True,key
    assert postmortem['authority_state_exists'] is False
    result['observation']={'path':str(observation_path),'sha256':sha(observation_path),'value':observation}
    result['status']='original_seed_component_passed'
except BaseException as error:
    result['status']='failed'
    result['error']=repr(error)
    raise
finally:
    result['test_attempted']=attempted
    result['finished_unix_ms']=time.time_ns()//1000000
    save()
    print(json.dumps({'status':result['status'],'result':str(OUTPUT/'result.json')}),flush=True)
