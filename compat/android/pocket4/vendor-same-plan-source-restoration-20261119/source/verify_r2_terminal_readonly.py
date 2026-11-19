#!/usr/bin/python3
"""Read-only independent check after the exact R2 unit has retired."""
import hashlib, json, os, stat, subprocess, sys, time
from pathlib import Path

ROOT = Path('/home/qq/work/p4-sameplan-source-repair-5cd1-20261119-r2')
SOURCE = Path('/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/work/aosp-source')
UNIT = 'p4-sameplan-source-repair-5cd1-20261119-r2.service'
START = time.monotonic()
def need(x, message):
    if not x: raise RuntimeError(message)
def f9(s):
    return [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
def read(path, wanted=None, retain_body=True):
    path = Path(path)
    need(path.resolve() == path, 'canonical read path')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        first = f9(os.fstat(fd)); need(stat.S_ISREG(first[2]) and first[5] == 1 and first[6] <= 64*1024**2, 'bounded ordinary read')
        sha = hashlib.sha256(); body = bytearray()
        while True:
            need(time.monotonic()-START < 180, 'bounded terminal observation')
            b = os.read(fd, 1024**2)
            if not b: break
            sha.update(b)
            if retain_body: body.extend(b)
        need(first == f9(os.fstat(fd)) == f9(path.lstat()), 'unchanged held artifact')
        pin = {'path':str(path),'bytes':first[6],'sha256':sha.hexdigest(),'f9':first}
        if wanted is not None:
            need(all(pin[k] == wanted[k] for k in ('path','bytes','sha256','f9')), 'actual artifact pin matches receipt')
        return bytes(body), pin
    finally: os.close(fd)

need(os.getuid() == 1000, 'ordinary qq metadata reader')
cmd = ['/usr/bin/systemctl','--user','show',UNIT,'--property=LoadState,ActiveState,SubState,MainPID,ControlGroup']
p = subprocess.run(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
fields = dict(line.split('=',1) for line in p.stdout.decode().splitlines() if '=' in line)
need(p.returncode == 0 and not p.stderr and fields == {'LoadState':'not-found','ActiveState':'inactive','SubState':'dead','MainPID':'0','ControlGroup':''}, 'exact original unit retired')
cg = Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice')/UNIT
need(not os.path.lexists(cg), 'exact original cgroup gone')
raw, result_pin = read(ROOT/'actual/RESULT.json')
need(result_pin['sha256'] == sys.argv[1], 'actual terminal result matches original client output hash')
r = json.loads(raw)
need(r['schema']=='pocket4-normal-same-plan-source-repair-v2' and r['state']=='PASSED' and r['errors']==[], 'actual successful complete repair')
need(r['source_reconcile_dispatched'] is True and r['source_reconcile_returned_success'] is True, 'actual normal repair dispatched and returned')
need(r['all_original_children_reaped'] is True and r['original_locks_held_through_child_retirement'] is True and r['adopted_child_retirement']==[], 'complete original child and lock custody')
need(r['actual_worker_source']['sha256']=='7a86286830d5ba83db799bfa2911eaa3f919d12fdfac07a5e5fc8dc8acf2a6a3', 'reviewed worker actually used')
need(r['complete_original_canonical_producer_unchanged'] is True and r['production_ready'] is False and r['runtime_qualified'] is False, 'exact source-only qualification scope')
need(all(r[k]==0 for k in ('Android_starts','compilations','installations','external_CURRENT_mutations','owner_or_lease_changes','historical_tests_counted_as_fresh')), 'no out-of-scope operations credited')
commands=r['commands']
need(all(c['actual_child_reaped'] is True and c['original_pidfd_held_until_reaped'] is True and c['after_reap_echild'] is True and c['exit_code']==0 and c['waitid']=={'pid':c['pid'],'code':os.CLD_EXITED,'status':0} and not c.get('forced') for c in commands), 'every original child genuinely successful and reaped')
normal=[c for c in commands if c['name'] in ('normal-same-plan-reconcile','normal-verify-materialized')]
need([c['name'] for c in normal]==['normal-same-plan-reconcile','normal-verify-materialized'], 'exact two actual normal commands')
tool='/home/qq/work/p4-integrated-continuation-20261118-162b-r1/unified-native-capex-asb-20261119-r2/release-tools-r1/bin/droidloom-source'
lock='/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/producer-build-r6/android/manifest/production-full-source-lock.json'
for command,verb in zip(normal,('reconcile','verify-materialized')):
    need(command['argv']==[tool,'--profile','production-full',verb,'--lock',lock,'--output',str(SOURCE)], 'exact normal tool/profile/lock/output command')
lock_rows=r['actual_original_locks']
need(len(lock_rows)==3 and [x['f9'][1] for x in lock_rows]==[60857531,60857480,60857481], 'three original source lock identities')
actual_lock_lines=Path('/proc/locks').read_text().splitlines()
for row in lock_rows:
    p=Path(row['path']);s=p.lstat();need(f9(s)==row['f9'], 'original lock F9 unchanged after retirement')
    key=f'{os.major(s.st_dev):02x}:{os.minor(s.st_dev):02x}:{s.st_ino}'
    need(not any(key in line.split() for line in actual_lock_lines), 'original source lock actually free after unit retirement')
verified_pins=[]
for c in normal:
    for key in ('saved_stdout','saved_stderr'):
        _, pin=read(c[key]['path'],c[key],False);verified_pins.append(pin)
artifacts={}
for key in ('manifest_before','manifest_after'):
    body,pin=read(r[key]['copy']['path'],r[key]['copy']);artifacts[key]=json.loads(body);verified_pins.append(pin)
need(artifacts['manifest_before']==artifacts['manifest_after'], 'same complete normal manifest semantics')
need(len(artifacts['manifest_after']['plan']['projects'])==651, 'original full651 plan retained')
_, live_manifest=read(SOURCE/'.droidloom-source-manifest.json',r['manifest_after']['original'])
for key in ('projects_before','projects_after','canonical_producer_before','canonical_producer_after'):
    body,pin=read(r[key]['path'],r[key]);artifacts[key]=json.loads(body);verified_pins.append(pin)
need(artifacts['canonical_producer_before']==artifacts['canonical_producer_after'] and len(artifacts['canonical_producer_after']['files'])==2336 and artifacts['canonical_producer_after']['tree']=='fa0382574f4fc18f59b2b5dd67a30939167d8c3a', 'actual complete original2336 source snapshot equality')
need(artifacts['projects_before']['project_count']==artifacts['projects_after']['project_count']==651 and artifacts['projects_before']['sparse_count']==artifacts['projects_after']['sparse_count']==446 and artifacts['projects_after']['missing_cones']=={}, 'all651 metadata and446 sparse checks completed')
for a,b in zip(artifacts['projects_before']['projects'],artifacts['projects_after']['projects']):
    need(all(a[k]==b[k] for k in ('project','commit','origin','tree_entries','tree_sha256','index_sha256','clean')), 'original complete project tuples/index retained')
body,pin=read(r['selected_tree_before']['path'],r['selected_tree_before']);selected=json.loads(body);verified_pins.append(pin)
body,pin=read(ROOT/'FULL_PROJECT_MISSING.json');need(pin['sha256']=='8e7973d893ecc73dab52037cc96817423a099e30df5cbc0214142866568ceda2', 'exact additional988 input');full=json.loads(body);verified_pins.append(pin)
expected={}
for item in selected.values():
    for path,row in item['rows'].items(): expected[(item['project'],path)]={'git_mode':row['mode'],'git_blob':row['git_blob'],'bytes':row['bytes']}
for item in full['rows']:
    for row in item['missing_rows']:
        key=(item['project'],row['path']);need(key not in expected, 'disjoint original missing scopes');expected[key]={k:row[k] for k in ('git_mode','git_blob','bytes')}
need(len(expected)==26047 and sum(x['bytes'] for x in expected.values())==13818632037, 'exact merged originally absent source inventory')
seen=set();total=symlinks=0
for name in ('restored_body_inventory','restored_full_project_body_inventory'):
    receipt=r[name];body,pin=read(receipt['path'],receipt);verified_pins.append(pin)
    need(receipt['every_actual_body_Git_blob_and_SHA256_verified'] is True, 'actual body verification reported')
    for line in body.splitlines():
        need(time.monotonic()-START < 180, 'bounded live metadata bookend')
        row=json.loads(line);key=(row['project'],row['path'])
        need(key in expected and key not in seen and row['present'] is True, 'exact complete unique actual restored member')
        need(all(row[k]==expected[key][k] for k in ('git_mode','git_blob','bytes')), 'restored member matches exact original committed blob')
        need(len(row['sha256'])==64 and all(x in '0123456789abcdef' for x in row['sha256']), 'actual SHA256 supplied')
        path=SOURCE/row['project']/row['path'];need(path.parent.resolve()==path.parent, 'current restored parent is not an alias')
        need(f9(path.lstat())==row['f9'], 'actual restored source member unchanged after worker retirement')
        seen.add(key);total+=row['bytes'];symlinks+=row['git_mode']=='120000'
need(seen==set(expected) and total==13818632037 and symlinks==776, 'all26047 live F9 identities and776 symlinks match complete body receipts')
resource=r['resources'];need(resource['minimum_free_bavail']>=144*1024**3 and resource['maximum_observed_growth']<=16*1024**3, 'actual recorded source and disk budgets passed')
need(r['allocation_after']['scan_started_ns']>r['restored_full_project_body_inventory']['f9'][7], 'final allocation scan actually follows body proof')
du=subprocess.run(['/usr/lib/cargo/bin/coreutils/du','--one-file-system','--summarize','--block-size=1','--',str(ROOT)],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
need(du.returncode==0 and not du.stderr, 'complete actual owned allocation')
owned=int(du.stdout.split(b'\t',1)[0]);need(owned<=64*1024**2, 'actual entire owned root including RESULT within64MiB')
growth=r['allocation_after']['allocations'][str(SOURCE)]+owned-sum(r['allocation_before']['allocations'].values());need(growth<=16*1024**3, 'actual quiescent source plus final owned output within16GiB')
fs=os.statvfs(SOURCE);free=fs.f_bavail*fs.f_frsize;need(free>=144*1024**3, 'actual post-retirement disk floor')
need(not os.path.lexists(SOURCE.parent/'source-projection.json'), 'actual source projection absent')
print(json.dumps({'schema':'pocket4-r2-source-repair-independent-terminal-observation-v1','passed':True,'observed_ns':time.time_ns(),'elapsed_seconds':time.monotonic()-START,'result':result_pin,'exact_unit':{'unit':UNIT,'fields':fields,'cgroup_absent':True},'commands_verified':len(commands),'normal_commands':normal,'actual_manifest_after':live_manifest,'manifest_body_identical':r['manifest_body_identical'],'manifest_F9_identical':r['manifest_F9_identical'],'projects_verified':651,'canonical_producer_files_verified':2336,'body_inventory_members':len(seen),'body_inventory_logical_bytes':total,'symlink_bodies':symlinks,'all_restored_live_F9_match':True,'owned_root_allocation_bytes':owned,'source_plus_final_owned_growth_bytes':growth,'disk_free_bavail':free,'recorded_resources':resource,'verified_artifacts':verified_pins,'source_mutations':False,'whole651_body_equality_claimed':False,'production_ready':False,'runtime_qualified':False},sort_keys=True))
