"""Read only the exact retained flow09 package/file and saved open transition."""
import base64,hashlib,json,os,re,stat,time,types,zlib
from pathlib import Path
OUT=Path('/home/alex/work/pocket4-documents-reconcile09-20261105-r12-01')
BASE=Path('/home/alex/work/pocket4-documents-flow-20261105-r12-09')
TOOLS=Path('/home/alex/work/pocket4-documents-flow-20261105-r12-tools-09')
SOURCE=Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
def need(ok,why):
    if not ok:raise RuntimeError(why)
def sha(b):return hashlib.sha256(b).hexdigest()
def load(path,pin,name):
    b=path.read_bytes();need(sha(b)==pin,'SOURCE_PIN_CHANGED');m=types.ModuleType(name);m.__file__=str(path)
    exec(compile(b,str(path),'exec'),m.__dict__);return m
tx=load(SOURCE,'b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470','read09_tx')
f=load(TOOLS/'run_saf09.py','93ce75cffa2ac2dadf70d5f10647f4ec0c9ef597baed7d06f96cbe0d5719056d','read09_flow')
ui=load(TOOLS/'ui_adapter02.py','74234c0a3db0659e4632ce3e76510d80fe8b015514c6a72dc9e34bca31a83a54','read09_ui')
need(os.geteuid()==0 and BASE.resolve()==BASE and OUT.parent.resolve()==OUT.parent,'CANONICAL_ROOTS_REQUIRED')
prior=json.loads(tx.read_regular(BASE/'result.json','6048be3b22be228dc6f1a845ab8c7d94afa4ceddd185900e402e93f004e62e15',65536))
need(prior['owned_task_ids_closed']==[938,937] and prior['pending_effects']=={'files-open-owned-file':{
    'input_acknowledged':True,'kind':'tap','post_capture_outcome_unknown':True}},'ORIGINAL_PENDING_CHANGED')
os.umask(0o077);OUT.mkdir(mode=0o700)
result={'read_only':True,'ui_actions':0,'installs':0,'content_writes':0,'prior_result_sha256':'6048be3b22be228dc6f1a845ab8c7d94afa4ceddd185900e402e93f004e62e15'}
d=os.open(BASE,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
def saved(name,limit=262144):
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=d)
    try:
        a=os.fstat(fd);need(stat.S_ISREG(a.st_mode) and a.st_nlink==1 and a.st_uid==0 and a.st_size<=limit,'SAVED_RECEIPT_SCOPE')
        b=os.read(fd,limit+1);c=os.fstat(fd)
        need(len(b)==a.st_size and (a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(c.st_dev,c.st_ino,c.st_size,c.st_mtime_ns,c.st_ctime_ns),'SAVED_RECEIPT_CHANGED')
        return b
    finally:os.close(fd)
try:
    names=os.listdir(d)
    intent=[n for n in names if n.endswith('-files-open-owned-file-intent.json')]
    birth=[n for n in names if n.endswith('-fixture-directory-created.json')]
    need(len(intent)==len(birth)==1,'ORIGINAL_INTENT_OR_BIRTH_AMBIGUOUS')
    first=int(intent[0].split('-')[0]);chosen=sorted(n for n in names if n.endswith('.json') and (
        re.fullmatch(r'\d{3}-(?:files-open-owned-file-(?:intent|response)|actual-files-ui-rename-readback|fixture-directory-created|close-(?:938|937)-(?:intent|readback))\.json',n)
        or (n.endswith('-focus.json') and int(n.split('-')[0])>first)))
    need(5<=len(chosen)<=18,'SAVED_TRANSITION_BOUND')
    records={n:{'sha256':sha(saved(n)),'data_base64':base64.b64encode(saved(n)).decode()} for n in chosen}
    original_birth=json.loads(saved(birth[0]))['identity'];result['saved_records']=records
finally:os.close(d)
with tx.CameraSession(OUT/'commands') as session:
    result['guard_before']=session.guard();need(result['guard_before']==prior['final_guard'],'ORIGINAL_EPOCH_CHANGED')
    result['installed_identity']=f.identity(session,f.PACKAGE,f.APK_SHA)
    need(result['installed_identity']==prior['installed_identity'],'RETAINED_PACKAGE_IDENTITY_CHANGED')
    obj=f.Flow.__new__(f.Flow);obj.s=session;obj.ui=types.SimpleNamespace(record=lambda label,value:None)
    prefs=obj.pref_state();need(prefs is not None,'OWNED_PREFS_MISSING');result['owned_preferences']=prefs
    now=time.time_ns()//1000000;result['observed_unix_ms']=now
    result['original_lease_remaining_ms']=1200000-(now-prefs['started_ms'])
    raw=session.android(['/system/bin/cmd','activity','stack','list'],15).decode();roots,tasks=ui.parse_stacks(raw)
    result['current_tasks']={'raw':raw,'task_ids':sorted(tasks),'old_owned_ids_absent':not ({937,938}&(set(roots)|tasks)),
        'no_temporary_client_or_files_task':not any(c['component'].split('/')[0] in (f.PACKAGE,f.DOCS) for r in roots.values() for c in r['children'])}
    android_uid=session.android(['/system/bin/pm','list','packages','-U','--user','0','android'],15).decode()
    rows=[line for line in android_uid.splitlines() if line.startswith('package:android ')]
    result['system_resolver_uid_lines']=rows;result['system_uid_query_sha256']=sha(android_uid.encode())
    need(rows==['package:android uid:1000'],'SYSTEM_RESOLVER_UID_CHANGED')
    folder=session.target.open_root('/storage/emulated/0/'+f.FOLDER,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        need(f.fp(os.fstat(folder))==original_birth,'ORIGINAL_DIRECTORY_BIRTH_CHANGED')
        fresh=os.open('.',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=folder)
        try:need(f.fp(os.fstat(fresh))==original_birth,'FRESH_DIRECTORY_BIRTH_CHANGED');entries=os.listdir(fresh)
        finally:os.close(fresh)
        need(entries==[f.FILES],'RETAINED_EXACT_FILE_NAMES_CHANGED')
        fd=os.open(f.FILES,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=folder)
        try:
            a=os.fstat(fd);need(stat.S_ISREG(a.st_mode) and a.st_nlink==1 and a.st_size==87,'OWNED_FILE_TYPE_OR_SIZE_CHANGED')
            data=os.read(fd,1025);c=os.fstat(fd)
            need(len(data)==87 and sha(data)==f.PAYLOAD_SHA and (a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(c.st_dev,c.st_ino,c.st_size,c.st_mtime_ns,c.st_ctime_ns),'OWNED_FILE_CONTENT_CHANGED')
            result['retained_file']={'name':f.FILES,'bytes':len(data),'sha256':sha(data),'identity':f.fp(a),'mtime_ns':str(a.st_mtime_ns),'ctime_ns':str(a.st_ctime_ns)}
        finally:os.close(fd)
        need(f.fp(os.fstat(folder))==original_birth,'ORIGINAL_DIRECTORY_CHANGED_AFTER_READ')
        result['directory']={'birth':original_birth,'fresh_entries':entries}
    finally:os.close(folder)
    result['guard_after']=session.guard();need(result['guard_after']==result['guard_before'],'GUARD_CHANGED')
tx.write_new(OUT/'result.json',result)
raw=json.dumps(result,sort_keys=True,separators=(',',':')).encode();comp=zlib.compress(raw,9)
print(json.dumps({'encoding':'zlib-json-base64','archive_bytes':len(raw),'compressed_sha256':sha(comp),'archive_base64':base64.b64encode(comp).decode()}))
