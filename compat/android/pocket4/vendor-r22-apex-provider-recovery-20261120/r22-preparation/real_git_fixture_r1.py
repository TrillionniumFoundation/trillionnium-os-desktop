from pathlib import Path
import importlib.util, json, hashlib, os, shutil, signal, stat, subprocess, time

ROOT = Path(__file__).resolve().parent
ORIGINAL = Path('/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/work/aosp-source')
CONTRACT = Path('/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor-build-20261120-9907-r21/inputs/CONTRACT.json')
BOOKENDS = Path('/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor-build-20261120-9907-r20/inputs/vendor_source_bookends_text_auto_9907.py')
UNIT = 'p4-r22-apex-providers-git-fixture-20261120-3b9d-r1.service'
deadline = time.monotonic()+270

def load(name, path, size, sha):
    raw = path.read_bytes()
    assert len(raw) == size and hashlib.sha256(raw).hexdigest() == sha
    spec = importlib.util.spec_from_file_location(name,path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

core = load('r22_core',ROOT/'apex_test_transition.py',18207,'40d6c8f957f96cea2329296729de940f7c22cdfd9ae1116b8d2809ac9c1ded3a')
partial = load('r22_partial',ROOT/'apex_test_partial.py',33714,'69aaa8f009979722a2fe29fa6b3e56c05bd2c2002b90cc551e86b36c1df5942e')
book = load('bookends',BOOKENDS,29338,'bab5c377bf642d4aaa7b50a416319cebad31537022e5179a77e6e8d63827fa88')
assert os.getuid() == os.geteuid() == 1000 and os.sched_getaffinity(0) == {18}
cgroup = Path('/sys/fs/cgroup')/Path('/proc/self/cgroup').read_text().strip()[4:]
assert cgroup.name == UNIT
limits = {n:(cgroup/n).read_text().strip() for n in ['memory.max','memory.swap.max','cpu.max','pids.max']}
assert limits['memory.max'] == '2147483648' and limits['memory.swap.max'] == '0' and limits['pids.max'] == '64'
q,p = map(int,limits['cpu.max'].split());assert q == p
raw = CONTRACT.read_bytes();assert len(raw)==83652 and hashlib.sha256(raw).hexdigest()=='f88235f91532045e2037a42ce2a44623dc549075e93e041fb955c945d4876d3d'
contract = json.loads(raw);admission=contract['git_conversion_admission']
partial._production_admission(admission);partial._scope(admission)
old_raw = Path(contract['profiles']['new']['lock']['path']).read_bytes()
assert hashlib.sha256(old_raw).hexdigest() == core.OLD_LOCK_SHA
old_lock = json.loads(old_raw)
projects=[]
for project in old_lock['projects']:
    if project['path'] in core.PROVIDERS:
        projects.append({'path':project['path'],'url':old_lock['remote_base']+project['name'],
                         'commit':project['commit'],'purpose':project['purpose'],
                         'sparse_paths':project['sparse_paths']})
assert len(projects)==2
new_projects = [{**p,'sparse_paths':p['sparse_paths']+[core.PROVIDERS[p['path']]['cone']]} for p in projects]
source = ROOT/'fixture-source';source.mkdir(mode=0o700)
source_inode = partial.f9(source.lstat())
original_metadata = {p['path']:partial._metadata(ORIGINAL/p['path'],[]) for p in projects}
commands=[];snapshots=[];errors=[];retired=False;removed=False

def guard():
    assert time.monotonic()<deadline
    events=dict(line.split() for line in (cgroup/'memory.events').read_text().splitlines())
    assert int(events['oom'])==int(events['oom_kill'])==0
    assert (cgroup/'memory.swap.current').read_text().strip()=='0'
    partial._scope(admission)

def run(args, cwd=None):
    guard()
    child=subprocess.Popen(['/usr/bin/git','-c','core.fsmonitor=false',*args],cwd=cwd,
                           stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           env={**os.environ,'GIT_OPTIONAL_LOCKS':'0'},start_new_session=True)
    pidfd=None
    started=time.time_ns();timed_out=False
    try:
        pidfd=os.pidfd_open(child.pid)
        try: out,err=child.communicate(timeout=min(90,max(1,deadline-time.monotonic())))
        except subprocess.TimeoutExpired:
            timed_out=True;os.killpg(child.pid,signal.SIGKILL);out,err=child.communicate(timeout=10)
        try:os.killpg(child.pid,0)
        except ProcessLookupError:group_empty=True
        else:group_empty=False
        row={'argv':['/usr/bin/git','-c','core.fsmonitor=false',*args],'pid':child.pid,
             'exit_code':child.returncode,'actual_reaped':child.returncode is not None,
             'pidfd_held_until_reaped':True,'owned_process_group_absent':group_empty,'timed_out':timed_out,
             'started_ns':started,'finished_ns':time.time_ns(),
             'stdout_bytes':len(out),'stdout_sha256':hashlib.sha256(out).hexdigest(),
             'stderr_bytes':len(err),'stderr_sha256':hashlib.sha256(err).hexdigest()}
        commands.append(row)
        assert row['exit_code']==0 and group_empty and not timed_out, (row,err.decode(errors='replace')[:2000])
        guard();return out
    finally:
        if child.poll() is None:
            os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=10)
        if pidfd is not None:os.close(pidfd)

def sparse(project):
    path=source/project['path']
    run(['sparse-checkout','set','--cone','--skip-checks','--',*book.canonical_sparse_cones(project['sparse_paths'])],path)

def snapshot(label, expected_present):
    output=ROOT/(label+'.ndjson')
    result=partial._snapshot_projects(book,core,source,projects,new_projects,output,deadline,guard,admission)
    assert result['project_count']==2 and result['profile_contract_validated'] is False
    assert result['source_mutations'] is False and result['source_recovery_complete'] is False
    actual=[]
    for line in output.open('rb'):
        row=json.loads(line)
        if (row['project'],row['path']) in core.CANDIDATES:actual.append(row)
    assert len(actual)==4 and sum(r['present'] for r in actual)==expected_present
    summary=ROOT/(label+'.json');summary.write_text(json.dumps(result,indent=2)+'\n')
    snapshots.append({'label':label,'actual_candidates':actual,
                      'actual_provider_cone_profiles':result['actual_provider_cone_profiles'],
                      'summary':partial.fingerprint(summary),'inventory':result['inventory']})
    print(json.dumps({'case':label,'provider_present':expected_present}),flush=True)

try:
    for project in projects:
        destination=source/project['path'];destination.parent.mkdir(parents=True,exist_ok=True)
        run(['clone','--shared','--no-checkout','--',str(ORIGINAL/project['path']),str(destination)])
        run(['remote','set-url','origin',project['url']],destination)
        sparse(project)
        run(['checkout','--detach',project['commit']],destination)
    rules=partial.candidate_checkout_rules(book,core,source,ROOT/'candidate-rule-queries',deadline,guard,admission)
    assert rules['candidate_count']==4 and rules['all_five_attributes_unspecified'] is True
    (ROOT/'CANDIDATE-RULES.json').write_text(json.dumps(rules,indent=2)+'\n')
    snapshot('both-old',0)
    sparse(new_projects[0])
    snapshot('first-new-second-old',2)
    sparse(new_projects[1])
    snapshot('both-new',4)
    key=next(k for k in core.CANDIDATES if k[0]==new_projects[0]['path'])
    checkout=source/key[0]
    run(['update-index','--skip-worktree','--',key[1]],checkout)
    (checkout/key[1]).unlink()
    snapshot('both-new-one-original-skip-absent',3)
    run(['update-index','--no-skip-worktree','--',key[1]],checkout)
    try:
        partial._snapshot_projects(book,core,source,projects,new_projects,ROOT/'missing-H-rejected.ndjson',
                                   deadline,guard,admission)
    except RuntimeError as e:
        assert str(e) == 'missing required source body: ' + key[1], str(e)
        rejected_missing_H=True
    else:
        raise AssertionError('missing H provider was accepted')
    assert rejected_missing_H
    retired=all(c['actual_reaped'] and c['pidfd_held_until_reaped'] and c['owned_process_group_absent'] for c in commands)
    assert retired
finally:
    try:
        assert {p['path']:partial._metadata(ORIGINAL/p['path'],[]) for p in projects}==original_metadata
        assert shutil.rmtree.avoids_symlink_attacks
        assert source.lstat().st_ino==source_inode[1] and source.lstat().st_dev==source_inode[0]
        shutil.rmtree(source);removed=not os.path.lexists(source)
    except BaseException as e:
        errors.append({'cleanup':repr(e)})
    result={'schema':'p4-r22-real-original-git-object-partial-fixture-v1',
            'limits':limits,'commands':commands,'snapshots':snapshots,
            'only_two_isolated_clone_projects':True,'complete_652_production_source_qualification':False,
            'original_git_metadata_unchanged':not errors,'all_created_git_commands_retired':retired,
            'fixture_source_removed':removed,'errors':errors,
            'source_mutations_on_original_workspace':False,'Android_builds':0,'Android_starts':0,
            'runtime_qualified':False,'production_ready':False}
    (ROOT/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'cases':len(snapshots),'created_git_commands':len(commands),
                      'all_retired':retired,'fixture_removed':removed,'errors':errors}),flush=True)
assert not errors and retired and removed
