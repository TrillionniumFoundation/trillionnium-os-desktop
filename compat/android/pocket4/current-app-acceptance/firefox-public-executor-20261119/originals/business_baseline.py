#!/usr/bin/python3 -I
"""New read-only business baseline. A final Main capture is an input, never a legacy-schema alias."""
import argparse,grp,hashlib,json,os,re,stat,time,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
FINAL=Path('/home/alex/work/pocket4-android-final')
DATA_SHA='2f86b90b1ca0a3993387163ce2169d17b67841a6c3e65f5a59dd9c8557a7a25a'
ANCESTRY=Path('/home/alex/work/pocket4-main-current-baseline-02/source/cell_ancestry.py')
ANCESTRY_SHA='824492a2e9068aa30c3d5dc148402802843a3aaa574c41c290819a9f3d65d201'
POLICY=ANCESTRY.with_name('baseline_policy.py')
POLICY_SHA='c42514e346a5d61efe59c438ae64e4e90a0c37dfcd539552661f2fc87c64516d'
CAPTURE=FINAL/'qualification/capture_main.py'
CAPTURE_SHA='1a1a9122744eb83b047da9562daf9930883684a4f11d0de76e3e4154a91e9e69'
SCHEMA='pocket4-final-business-baseline-v1'
QUAL_SCHEMA='pocket4-final-business-qualification-v1'
ROLES=('daemon','launcher','owner_intermediary','presenter','init','zygote64','system_server','surfaceflinger')
ANDROID=('init','zygote64','system_server','surfaceflinger')
NS=('user','mnt','pid','uts','ipc','net','cgroup')
LIMITS={'cpu.max':'200000 100000','memory.high':'5368709120','memory.max':'6442450944','memory.swap.max':'max','pids.max':'12288'}
SOURCE_FILES={'business_commands.py','business_data.py','business_baseline.py','business_scope.py','business_ui_entry.py','business_image_capture.py'}
ENGINE='/system/lib64/libberberis_arm64.so'
HOST_PREREQUISITE_BINDING={'path':'/home/alex/work/pocket4-android-final/qualification/business-host-retention-integration-20261108-r1/host-prerequisite-binding.json',
    'bytes':3182,'sha256':'e7a9693d3ebc9f9fe669bd4a12b5c4af77c482ff806c3333151695a68e04958d'}
RETAINED_FIXED_TARGETS={'/etc/droidloom/cell.json',
    '/etc/systemd/system/droidloomd.service.d/90-digitalis-validation-resources.conf',
    '/home/alex/.config/systemd/user/droidloom.service.d/95-presenter-guard.conf'}
ACCOUNT_DATABASE_TARGETS={'/etc/group','/etc/gshadow','/etc/group-','/etc/gshadow-',
    '/etc/.pwd.lock','/etc/passwd','/etc/shadow','/etc/nsswitch.conf'}

def need(ok,code):
    if not ok:raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def metadata(fd):
    st=os.fstat(fd);return {k:getattr(st,k) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')}
def read_ref(ref,maximum=16*1024*1024):
    path=Path(ref['path']);need(path.is_absolute() and path.resolve()==path,'EXACT_PINNED_PATH_REQUIRED')
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        before=metadata(fd);need(stat.S_ISREG(before['st_mode']) and before['st_nlink']==1 and 0<before['st_size']<=maximum,'PINNED_FILE_BOUND')
        raw=bytearray();deadline=time.monotonic()+10
        while True:
            need(time.monotonic()<deadline,'PINNED_READ_DEADLINE')
            part=os.read(fd,min(65536,maximum+1-len(raw)))
            if not part:break
            raw.extend(part);need(len(raw)<=maximum,'PINNED_FILE_GREW')
        need(metadata(fd)==before and len(raw)==before['st_size'] and sha(raw)==ref['sha256'] and
             ('bytes' not in ref or ref['bytes']==len(raw)),'PINNED_FILE_CHANGED')
        return bytes(raw)
    finally:os.close(fd)
def load(path,pin,name):
    raw=read_ref({'path':str(path),'sha256':pin},1024*1024)
    module=types.ModuleType(name);module.__file__=str(path);exec(compile(raw,str(path),'exec'),module.__dict__);return module
def data_module():return load(HERE/'business_data.py',DATA_SHA,'new_business_data_binding')

def host_group_ready():
    """The separately prepared empty group is observed, never changed here."""
    expected=('droidloom-audio-hal',1041,())
    try:rows=(grp.getgrgid(1041),grp.getgrnam(expected[0]))
    except KeyError:raise RuntimeError('ACTUAL_PREPARED_HOST_GROUP_REQUIRED')
    need(all((row.gr_name,row.gr_gid,tuple(row.gr_mem))==expected for row in rows),
         'ACTUAL_HOST_GROUP_NAME_GID_OR_MEMBERS_CHANGED')
    return {'name':expected[0],'gid':1041,'members':[],'managed_by_file_transaction':False}

def verify_host_prerequisite_records(data):
    """Recheck the actual host proof and four retained prerequisite archives.

    Archive identities describe immutable private archive files, not current
    account databases. No account lock, account write or rollback is performed.
    Host source qualification supplies no Android runtime or business credit.
    """
    binding=data.parse(read_ref(HOST_PREREQUISITE_BINDING,65536))
    need(binding.get('schema')=='pocket4-business-host-prerequisite-binding-v1' and
         binding.get('state')=='ACTUAL_HOST_PREREQUISITE_OBSERVED_RUNTIME_PENDING' and
         binding.get('group')=={'name':'droidloom-audio-hal','gid':1041,'members':[]} and
         binding.get('group_managed_by_file_transaction') is False and
         binding.get('Main_actions')==0 and binding.get('runtime_qualified') is False and
         binding.get('whole_app_business_accepted') is False,'EXACT_SEPARATE_HOST_PREREQUISITE_BINDING')
    group=host_group_ready()
    host_raw=read_ref(binding['host_qualification'],65536);host=data.parse(host_raw)
    need(host.get('schema')=='pocket4-audio-host-qualification-source-binding-v1' and
         host.get('state')=='ACTUAL_HOST_QUALIFIED_RUNTIME_PENDING' and
         host.get('group')==binding['group'] and host.get('runtime_qualified') is False and
         host.get('candidate_deployed') is False and
         host.get('evidence',{}).get('group_preparation')==binding['group_preparation'],
         'ACTUAL_HOST_PROOF_AND_SAME_GROUP_PREPARATION_REQUIRED')
    prepared=data.parse(read_ref(binding['group_preparation'],65536))
    archives=binding.get('retained_archives')
    need(type(archives) is list and len(archives)==4 and
         all(type(row) is dict and set(row)=={'source','identity'} for row in archives),
         'EXACT_FOUR_ORIGINAL_GROUP_ARCHIVES_REQUIRED')
    expected_names={'preimage-group','preimage-gshadow','preimage-group-','preimage-gshadow-'}
    archive_root=Path(binding['group_preparation']['path']).parent
    info=archive_root.lstat()
    need(archive_root.is_absolute() and archive_root.resolve()==archive_root and
         stat.S_ISDIR(info.st_mode) and info.st_uid==info.st_gid==0 and
         stat.S_IMODE(info.st_mode)==0o700,'PRIVATE_ORIGINAL_GROUP_ARCHIVE_DIRECTORY_REQUIRED')
    need(prepared.get('schema')=='pocket4-audio-host-group-preparation-v1' and
         prepared.get('ready') is True and prepared.get('created') is True and
         prepared.get('resolved_group')==binding['group'] and
         prepared.get('unrelated_group_entries_unchanged') is True and
         prepared.get('retained_for_final_audio_socket_contract') is True and
         prepared.get('canonical_installation') is False and prepared.get('Main_actions')==0 and
         prepared.get('preimages')==[row['source'] for row in archives] and
         {Path(row['source']['path']).name for row in archives}==expected_names,
         'ACTUAL_GROUP_PREPARATION_AND_ORIGINAL_ARCHIVE_SET_REQUIRED')
    total=0
    for row in archives:
        ref=row['source'];path=Path(ref['path']);identity=row['identity']
        need(set(ref)=={'path','bytes','sha256'} and path.parent==archive_root and
             path.resolve()==path and type(ref['bytes']) is int and 0<ref['bytes']<=2*1024*1024 and
             type(identity) is dict and set(identity)=={'device','inode','mode','uid','gid',
                 'nlink','bytes','mtime_ns','ctime_ns'} and all(type(v) is int for v in identity.values()) and
             identity['bytes']==ref['bytes'] and identity['inode']>0 and
             (identity['uid'],identity['gid'],identity['mode'],identity['nlink'])==(0,0,0o400,1),
             'EXACT_PRIVATE_ORIGINAL_ARCHIVE_IDENTITY_REQUIRED')
        def observed():
            st=path.lstat()
            need(stat.S_ISREG(st.st_mode),'ORIGINAL_GROUP_ARCHIVE_MUST_BE_REGULAR')
            return dict(device=st.st_dev,inode=st.st_ino,mode=stat.S_IMODE(st.st_mode),
                uid=st.st_uid,gid=st.st_gid,nlink=st.st_nlink,bytes=st.st_size,
                mtime_ns=st.st_mtime_ns,ctime_ns=st.st_ctime_ns)
        need(observed()==identity,'ORIGINAL_GROUP_ARCHIVE_IDENTITY_CHANGED')
        read_ref(ref,2*1024*1024)
        need(observed()==identity,'ORIGINAL_GROUP_ARCHIVE_CHANGED_DURING_READ')
        total+=ref['bytes']
    need(host_group_ready()==group,'HOST_GROUP_CHANGED_DURING_ARCHIVE_CHECK')
    read_ref(HOST_PREREQUISITE_BINDING,65536)
    return {'binding':binding,'host_raw':host_raw,'group':group,'archive_count':4,
            'archive_bytes':total,'runtime_qualified':False,'whole_app_business_accepted':False}

def verify_host_prerequisite(manifest,transaction,data):
    observed=verify_host_prerequisite_records(data);binding=observed['binding']
    need('audio_account_contract' not in manifest and 'audio_account_prerequisite' not in manifest and
         'audio_account' not in transaction,'SEPARATE_GROUP_PREREQUISITE_IS_NOT_AN_ACCOUNT_TRANSACTION')
    payload=manifest.get('payload')
    need(type(payload) is list and 0<len(payload)<=61 and
         all(type(row) is dict and type(row.get('install_target')) is str for row in payload),
         'BOUNDED_EXACT_DEPLOYED_PAYLOAD_REQUIRED')
    targets=[row['install_target'] for row in payload]
    archive_paths={row['source']['path'] for row in binding['retained_archives']}
    need(all(Path(p).is_absolute() and str(Path(p))==p and '..' not in Path(p).parts for p in targets) and
         len(set(targets))==len(targets) and not set(targets)&(RETAINED_FIXED_TARGETS|ACCOUNT_DATABASE_TARGETS|archive_paths) and
         set(transaction['preimages'])==set(targets)|RETAINED_FIXED_TARGETS,
         'EXACT_FILE_TRANSACTION_TARGETS_WITH_SEPARATE_ARCHIVES_REQUIRED')
    need(transaction.get('startup',{}).get('audio_host_group_before_daemon_restart')==observed['group'],
         'ACTUAL_STARTUP_GROUP_CHECK_MUST_MATCH_SEPARATE_PREREQUISITE')
    audio_ref=manifest.get('actual_component_source_qualification',{}).get('audio')
    need(type(audio_ref) is dict and set(audio_ref)=={'path','bytes','sha256'} and
         type(audio_ref['path']) is str and audio_ref['path'].startswith(str(FINAL)+'/qualification/') and
         manifest.get('audio_lifecycle',{}).get('source_qualification')==audio_ref and
         manifest['audio_lifecycle'].get('socket_uid')==1000 and manifest['audio_lifecycle'].get('socket_gid')==1041,
         'DEPLOYED_AUDIO_SOURCE_AND_SOCKET_CONTRACT_REQUIRED')
    audio=data.parse(read_ref(audio_ref,262144))
    need(audio.get('schema')=='pocket4-audio-complete-source-qualification-v1' and
         audio.get('state')=='ACTUAL_SOURCE_QUALIFIED_RUNTIME_PENDING' and
         audio.get('runtime_qualified') is False and audio.get('candidate_deployed') is False and
         audio.get('original45_whole_app_accepted')==0,
         'REAL_COMPLETE_SOURCE_PACKET_REQUIRED_WITHOUT_RUNTIME_CREDIT')
    host_ref=audio.get('host_qualification_binding');expected=binding['host_qualification']
    need(type(host_ref) is dict and set(host_ref)=={'path','bytes','sha256'} and
         type(host_ref['path']) is str and host_ref['path'].startswith(str(FINAL)+'/qualification/') and
         (host_ref['bytes'],host_ref['sha256'])==(expected['bytes'],expected['sha256']) and
         read_ref(host_ref,65536)==observed['host_raw'],
         'DEPLOYED_AUDIO_PACKET_MUST_BIND_THE_ACTUAL_HOST_PROOF')
    return {k:observed[k] for k in ('group','archive_count','archive_bytes','runtime_qualified','whole_app_business_accepted')}

def verify_sources(ref,data):
    manifest=data.parse(read_ref(ref,131072))
    need(manifest.get('schema')=='pocket4-final-business-support-v1' and set(manifest.get('files',{}))==SOURCE_FILES,
         'EXACT_NEW_BUSINESS_SOURCE_SET_REQUIRED')
    for name,row in manifest['files'].items():
        need(set(row)=={'bytes','sha256'},'EXACT_SOURCE_REFERENCE_REQUIRED')
        read_ref({'path':str(HERE/name),**row},1024*1024)
    need(manifest['files']['business_data.py']['sha256']==DATA_SHA,'DATA_SUPPORT_PIN_CHANGED')
    need(manifest.get('historical_runtime_authority_transferred') is False and manifest.get('business_accepted') is False,
         'NEW_SOURCE_IS_NOT_LEGACY_RUNTIME_ADMISSION')
    for path,pin in ((ANCESTRY,ANCESTRY_SHA),(POLICY,POLICY_SHA),(CAPTURE,CAPTURE_SHA)):
        read_ref({'path':str(path),'sha256':pin},1024*1024)
    return manifest

def validate_inputs(plan,base,manifest,transaction,post):
    need(plan.get('schema')=='pocket4-final-business-capture-plan-v1' and
         set(plan)=={'schema','target','final_baseline','deployment_manifest','transaction','post_start_receipt','source_manifest'},
         'EXACT_NEW_CAPTURE_PLAN_REQUIRED')
    need(plan['target']=='pocket4-local-droidloom-x86_64','LOCAL_MAIN_ONLY')
    for name in ('final_baseline','deployment_manifest','transaction','post_start_receipt','source_manifest'):
        ref=plan[name]
        need(set(ref)=={'path','bytes','sha256'} and ref['path'].startswith(str(FINAL)+'/') and
             type(ref['bytes']) is int and 0<ref['bytes']<=16*1024*1024 and
             re.fullmatch('[0-9a-f]{64}',ref['sha256']),'EXTERNALLY_PINNED_FINAL_REFERENCE_REQUIRED')
    need(base.get('schema')=='pocket4-final-main-baseline-v1' and base.get('historical_PIDs_reused') is False,
         'FRESH_FINAL_CAPTURE_REQUIRED')
    epoch=base['main_epoch']
    need(epoch['schema']=='pocket4-framework-epoch-v1' and epoch['sha256']==sha(canonical(epoch['binding'])) and
         set(epoch['binding']['processes'])==set(ANDROID),'FULL_FINAL_FRAMEWORK_EPOCH_REQUIRED')
    need(set(base['host_processes'])=={'daemon','launcher','owner_intermediary','presenter'},'FINAL_HOST_ROLE_SET_CHANGED')
    rows={**base['host_processes'],**epoch['binding']['processes']}
    need(set(rows)==set(ROLES) and len({r['host_pid'] for r in rows.values()})==len(ROLES),'SEVEN_MAIN_ROLES_AND_ORIGINAL_OWNER_INTERMEDIARY_REQUIRED')
    need(base['init_host_pid']==rows['init']['host_pid'] and base['daemon_status']['host_pid']==rows['launcher']['host_pid'],
         'FINAL_OWNER_DISCOVERY_CHANGED')
    for child,parent in (('launcher','daemon'),('owner_intermediary','launcher'),('init','owner_intermediary'),
                         ('zygote64','init'),('system_server','zygote64'),('surfaceflinger','init')):
        need(rows[child]['parent_host_pid']==rows[parent]['host_pid'],'FINAL_PARENT_CHAIN_CHANGED')
    need(base['resources']['cgroup']=='/system.slice/droidloomd.service' and
         base['resources']['values']=={k:v for k,v in LIMITS.items() if k!='memory.swap.max'},'FINAL_RESOURCE_CONTRACT_CHANGED')
    for role in ('daemon','launcher','owner_intermediary'):
        need(rows[role]['uids']==[0]*4 and rows[role]['cgroup']==['0::'+base['resources']['cgroup']],'ROOT_OWNER_CGROUP_CHANGED')
    for role,program in (('daemon','/usr/bin/droidloomd'),('presenter','/usr/bin/droidloom-wayland')):
        need(rows[role]['executable']==program and rows[role]['uids']==[0 if role=='daemon' else 1000]*4,'HOST_ROLE_PROGRAM_CHANGED')
        unit=base['systemd_units'][role]
        need(unit['MainPID']==str(rows[role]['host_pid']) and unit['ControlPID']=='0' and
             unit['ActiveState']=='active' and unit['SubState']=='running' and
             rows[role]['cgroup']==['0::'+unit['ControlGroup']] and re.fullmatch('[0-9a-f]{32}',unit['InvocationID']),
             'FINAL_SERVICE_GENERATION_CHANGED')
    need(len(base['three_double_samples'])==3,'FINAL_DOUBLE_SAMPLES_MISSING')
    for sample in base['three_double_samples']:
        need(sample['first']['binding']==sample['second']['binding']==epoch['binding'] and
             sample['host_epoch']['binding']=={'boot_id':epoch['binding']['boot_id'],'processes':base['host_processes']},
             'FINAL_CAPTURE_SAMPLE_DRIFT')
    fds=base['observation_authorities']
    need(type(fds['acquired']) is int and fds['acquired']>0 and fds['acquired']==fds['closed'] and fds['remaining']==0,
         'FINAL_CAPTURE_FDS_UNCLOSED')
    mref=plan['deployment_manifest']
    need(base['deployment_manifest']=={'path':mref['path'],'sha256':mref['sha256']} and manifest.get('ready_for_apply') is True and
         base['cell_spec']['sha256']==manifest['candidate_cell']['sha256'],'COMMITTED_CANDIDATE_BINDING_REQUIRED')
    need(transaction.get('schema')=='pocket4-final-deployment-result-v1' and transaction.get('status')=='committed' and
         transaction.get('outcome_unknown') is False and transaction.get('production_mutated') is True and
         transaction.get('temporary_preimages_removed') is False and
         transaction.get('preimages_retention')=='retained until original45 whole-app final acceptance' and
         type(transaction.get('retained_preimages')) is dict and
         transaction.get('deployment_manifest_sha256')==mref['sha256'],
         'KNOWN_COMMITTED_FINAL_TRANSACTION_REQUIRED')
    need(post.get('schema')=='pocket4-final-deployment-adapter-result-v1' and post.get('phase')=='post' and post.get('status')=='pass' and
         post.get('transaction_id')==transaction['transaction_id'] and post.get('deployment_manifest_sha256')==mref['sha256'] and
         post.get('automatic_retry') is False and set(post['checks'])=={'main','storage','native','framework','applications','camera'} and
         all(value is True for value in post['checks'].values()),'BASE_PLATFORM_QUALIFICATION_REQUIRED')
    link=transaction['post_start_qualification']
    need(link['receipt']==plan['post_start_receipt']['path'] and link['sha256']==plan['post_start_receipt']['sha256'] and
         link['checks']==post['checks'] and link['proofs']==post['proofs'],'QUALIFICATION_REFERENCE_CHANGED')
    bref={k:plan['final_baseline'][k] for k in ('path','sha256')}
    need(sum(item==bref for item in post['proofs'])==1 and post['started_unix_ns']<=base['captured_unix_ns']<=post['finished_unix_ns'],
         'BASELINE_NOT_CAPTURED_IN_THIS_FINAL_QUALIFICATION')
    return rows

def verify_retained_preimages(plan,transaction,data):
    """Bind a committed transaction to its still-held, unchanged rollback files.

    The exact deployment runner hashes each file before sealing this immutable
    index. Every business guard rechecks the index seal, full held-file identity,
    file set and original preimage mapping without repeatedly hashing large APKs.
    """
    txid=transaction['transaction_id']
    need(isinstance(txid,str) and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}',txid),
         'EXACT_RETAINED_TRANSACTION_ID_REQUIRED')
    tx=FINAL/'deployment/transactions'/txid
    need(plan['transaction']['path']==str(tx/'result.json'),'EXACT_COMMITTED_TRANSACTION_PATH_REQUIRED')
    reference=transaction['retained_preimages'];index=tx/'retained-preimages.json';pre=tx/'preimages'
    need(set(reference)=={'path','bytes','sha256'} and reference['path']==str(index) and
         type(reference['bytes']) is int and 0<reference['bytes']<=16*1024*1024 and
         isinstance(reference['sha256'],str) and re.fullmatch('[0-9a-f]{64}',reference['sha256']),
         'EXACT_SEALED_RETENTION_INDEX_REQUIRED')
    for directory in (FINAL/'deployment',tx.parent,tx,pre):
        info=directory.lstat()
        need(directory.resolve()==directory and stat.S_ISDIR(info.st_mode) and info.st_uid==0 and
             stat.S_IMODE(info.st_mode)==0o700,'ROOT_PRIVATE_RETENTION_DIRECTORY_REQUIRED')
    info=index.lstat()
    need(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==info.st_gid==0 and
         stat.S_IMODE(info.st_mode)==0o400,'IMMUTABLE_SINGLE_LINK_RETENTION_INDEX_REQUIRED')
    value=data.parse(read_ref(reference))
    need(set(value)=={'schema','state','transaction_id','deployment_manifest_sha256','original_application_count',
         'business_acceptance_complete','directory','preimages','files','total_file_bytes'} and
         value['schema']=='pocket4-retained-deployment-preimages-v1' and
         value['state']=='RETAINED_PENDING_ORIGINAL45_ACCEPTANCE' and value['transaction_id']==txid and
         value['deployment_manifest_sha256']==transaction['deployment_manifest_sha256']==plan['deployment_manifest']['sha256'] and
         type(value['original_application_count']) is int and value['original_application_count']==45 and
         value['business_acceptance_complete'] is False and value['directory']==str(pre) and
         value['preimages']==transaction['preimages'],'RETENTION_MUST_BIND_THIS_COMMITTED_ORIGINAL45_TRANSACTION')
    originals=value['preimages'];files=value['files'];expected={};total=0
    need(type(originals) is dict and 0<len(originals)<=64 and type(files) is dict,'BOUNDED_COMPLETE_RETENTION_SET_REQUIRED')
    for target,original in originals.items():
        need(type(original) is dict and original['path']==target,'ORIGINAL_RETENTION_TARGET_CHANGED')
        if original.get('absent'):
            need(set(original)=={'path','absent'} and original['absent'] is True,'ABSENT_TARGET_HAS_NO_PREIMAGE_FILE')
            continue
        name=original['preimage']
        need(isinstance(name,str) and re.fullmatch('0|[1-9][0-9]?',name) and int(name)<64 and name not in expected,
             'UNIQUE_FINITE_RETAINED_PREIMAGE_NAME_REQUIRED')
        expected[name]=target
    need(set(files)==set(expected)==set(os.listdir(pre)),'EXACT_RETAINED_FILE_SET_REQUIRED')
    end=time.monotonic()+10
    for name,target in expected.items():
        need(time.monotonic()<end,'RETAINED_IDENTITY_CHECK_DEADLINE')
        row=files[name];path=pre/name;original=originals[target]
        need(set(row)=={'path','target','bytes','sha256','identity'} and row['path']==str(path) and row['target']==target and
             row['bytes']==original['bytes'] and row['sha256']==original['sha256'],
             'EXACT_ORIGINAL_CONTENT_RETENTION_BINDING_REQUIRED')
        fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|os.O_NOATIME)
        try:
            held=metadata(fd);named=path.lstat()
            need(held==row['identity'] and all(getattr(named,key)==val for key,val in held.items()) and
                 stat.S_ISREG(held['st_mode']) and held['st_nlink']==1 and held['st_uid']==held['st_gid']==0 and
                 stat.S_IMODE(held['st_mode'])==0o600 and type(row['bytes']) is int and
                 held['st_size']==row['bytes'] and metadata(fd)==held,'HELD_RETAINED_PREIMAGE_CHANGED')
            total+=held['st_size']
        finally:os.close(fd)
    need(type(value['total_file_bytes']) is int and total==value['total_file_bytes'] and total<=2*1024**3,
         'RETAINED_TOTAL_BYTES_CHANGED')
    read_ref(reference)
    return {'files':len(files),'total_bytes':total,'preimages_retained':True,'business_acceptance_complete':False}

def inputs(plan_ref):
    data=data_module();plan=data.parse(read_ref(plan_ref,131072))
    docs={key:data.parse(read_ref(plan[key])) for key in ('final_baseline','deployment_manifest','transaction','post_start_receipt')}
    validate_inputs(plan,docs['final_baseline'],docs['deployment_manifest'],docs['transaction'],docs['post_start_receipt'])
    verify_retained_preimages(plan,docs['transaction'],data)
    verify_host_prerequisite(docs['deployment_manifest'],docs['transaction'],data)
    verify_sources(plan['source_manifest'],data)
    for reference in docs['post_start_receipt']['proofs']:
        need(reference['path'].startswith(str(FINAL)+'/'),'FINAL_PROOF_OUTSIDE_PROJECT')
        read_ref(reference)
    return data,plan,docs

class Observation:
    def __init__(self,data,plan,docs,seconds=120):
        self.data,self.plan,self.docs=data,plan,docs
        self.base,self.manifest=docs['final_baseline'],docs['deployment_manifest']
        self.rows=validate_inputs(plan,self.base,self.manifest,docs['transaction'],docs['post_start_receipt'])
        self.epoch=load(data.EPOCH_PATH,data.EPOCH_SHA,'business_exact_epoch')
        self.reader=load(data.READER_PATH,data.READER_SHA,'business_exact_root_reader')
        self.ancestry=load(ANCESTRY,ANCESTRY_SHA,'business_exact_ancestry')
        self.policy=load(POLICY,POLICY_SHA,'business_legacy_pure_validators')
        self.pool=self.ancestry.ManagedFDs();self.handles={};self.deadline=time.monotonic()+seconds
        self.preimage=data.load_preimage()
    def check(self):need(time.monotonic()<self.deadline,'BUSINESS_OBSERVATION_DEADLINE')
    def identities(self):
        self.check()
        actual=self.epoch.capture_processes({k:v['host_pid'] for k,v in self.rows.items()})
        need(actual['binding']=={'boot_id':self.base['main_epoch']['binding']['boot_id'],'processes':self.rows},'FINAL_MAIN_GENERATION_CHANGED')
        for role,row in actual['binding']['processes'].items():
            fixed=self.rows[role]
            expected={'pid':fixed['host_pid'],'ppid':fixed['parent_host_pid'],'start_ticks':fixed['start_ticks'],
                      'uids':fixed['uids'],'namespace_pids':fixed['namespace_pids'],'namespaces':fixed['namespaces'],
                      'cgroup':'\n'.join(fixed['cgroup'])+'\n'}
            # Only this pure, explicitly parameterized function is reused.
            # No legacy current-binding/global PID policy is invoked or mutated.
            self.policy.validate_identity('android_init' if role=='init' else role,row,expected)
        self.check();return actual['binding']['processes']
    def acquire(self):
        self.identities()
        for role,row in self.rows.items():
            pid=row['host_pid'];self.check()
            pidfd=self.pool.own(os.pidfd_open(pid,0),role+'_pidfd')
            proc=self.pool.own(os.open('/proc/'+str(pid),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC),role+'_proc')
            self.ancestry.require_pidfd_live(pidfd)
            root=self.pool.own(os.open('root',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC,dir_fd=proc),role+'_root')
            exe=self.pool.own(os.open('exe',os.O_RDONLY|os.O_CLOEXEC,dir_fd=proc),role+'_exe')
            ns={k:self.pool.own(os.open('ns/'+k,os.O_RDONLY|os.O_CLOEXEC,dir_fd=proc),role+'_ns_'+k) for k in NS}
            self.handles[role]={'pidfd':pidfd,'proc':proc,'root':root,'exe':exe,'namespaces':ns}
        self.identities()
    def artifact(self,fd,limit=268435456):
        before=metadata(fd);need(stat.S_ISREG(before['st_mode']) and before['st_nlink']==1 and 0<before['st_size']<=limit,'ARTIFACT_BOUND')
        os.lseek(fd,0,os.SEEK_SET);h=hashlib.sha256();count=0
        while True:
            self.check();part=os.read(fd,min(131072,before['st_size']+1-count))
            if not part:break
            count+=len(part);need(count<=before['st_size'],'ARTIFACT_GREW');h.update(part)
        need(count==before['st_size'] and metadata(fd)==before,'ARTIFACT_CHANGED')
        value={'bytes':count,'sha256':h.hexdigest(),'file':before};self.policy.validate_artifact(value);return value
    def host_artifact(self,path):
        need(Path(path).resolve()==Path(path),'HOST_ARTIFACT_SYMLINK_REFUSED')
        fd=self.pool.own(os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC),'host_artifact')
        try:return self.artifact(fd)
        finally:self.pool.close(fd)
    def guest(self,role,path,flags=os.O_RDONLY):
        self.check();return self.pool.own(self.reader.open_in_root(self.handles[role]['root'],path,flags),'guest_file')
    def engine(self,hash_bytes=True):
        fd=self.guest('init',ENGINE)
        try:return self.artifact(fd) if hash_bytes else metadata(fd)
        finally:self.pool.close(fd)
    def observe(self):
        value={'roles':self.identities(),'roots':{},'namespaces':{},'executables':{},'child_tables':{},
               'host_user_namespace':os.readlink('/proc/self/ns/user'),'limits':{}}
        for role,h in self.handles.items():
            self.check();self.ancestry.require_pidfd_live(h['pidfd'])
            for leaf,flags,label in (('root',os.O_PATH|os.O_DIRECTORY,'roots'),('exe',os.O_RDONLY,'executables')):
                fd=self.pool.own(os.open(leaf,flags|os.O_CLOEXEC,dir_fd=h['proc']),'reopened_'+leaf)
                try:
                    st=os.fstat(fd);held=os.fstat(h['root' if leaf=='root' else 'exe'])
                    need((st.st_dev,st.st_ino)==(held.st_dev,held.st_ino),'HELD_ROLE_BACKING_CHANGED')
                    value[label][role]={'device':st.st_dev,'inode':st.st_ino} if leaf=='root' else metadata(fd)
                    if leaf=='exe':need(metadata(fd)==metadata(h['exe']),'HELD_EXECUTABLE_METADATA_CHANGED')
                finally:self.pool.close(fd)
            value['namespaces'][role]={}
            for name,held in h['namespaces'].items():
                link=os.readlink('ns/'+name,dir_fd=h['proc'])
                fd=self.pool.own(os.open('ns/'+name,os.O_RDONLY|os.O_CLOEXEC,dir_fd=h['proc']),'reopened_namespace')
                try:
                    a,b=os.fstat(fd),os.fstat(held)
                    need((a.st_dev,a.st_ino)==(b.st_dev,b.st_ino) and
                         link==name+':['+str(a.st_ino)+']','HELD_NAMESPACE_CHANGED')
                    value['namespaces'][role][name]={'link':link,'device':a.st_dev,'inode':a.st_ino}
                finally:self.pool.close(fd)
            need(value['namespaces'][role]['user']['link']==value['host_user_namespace'],'USER_NAMESPACE_MAPPING_CHANGED')
            need(all(value['namespaces'][role][name]['link']==self.rows[role]['namespaces'][name] for name in ('pid','mnt')),
                 'FINAL_EPOCH_NAMESPACE_CHANGED')
        for parent,child in (('daemon','launcher'),('launcher','owner_intermediary'),('owner_intermediary','init')):
            first=self.ancestry.children_sample(self.pool,self.handles[parent]['proc'],self.rows[parent]['host_pid'],self.check)
            second=self.ancestry.children_sample(self.pool,self.handles[parent]['proc'],self.rows[parent]['host_pid'],self.check)
            need(first==second,'OWNER_CHILD_TABLE_CHANGED')
            self.policy.validate_child_table(second,self.rows[parent]['host_pid'],self.rows[child]['host_pid'])
            value['child_tables'][parent]=second
        for name in LIMITS:
            path='/sys/fs/cgroup'+self.base['resources']['cgroup']+'/'+name
            fd=self.pool.own(os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC),'runtime_limit')
            try:value['limits'][name]=self.reader.read_fd(fd,8192,self.deadline).decode('ascii').strip()
            finally:self.pool.close(fd)
        need(value['limits']==LIMITS,'RUNTIME_RESOURCE_LIMITS_CHANGED')
        need(all(value['roots'][role]==value['roots']['init'] for role in ANDROID),'ANDROID_ROOT_BACKING_DIFFERS')
        self.identities();return value
    def classpaths(self,expected=None):
        raw=self.ancestry.read_proc_leaf(self.pool,self.handles['zygote64']['proc'],'environ',self.reader.ENV_LIMIT,self.check)
        values=self.reader.selected_classpaths(raw);del raw
        need(values==self.base['classpath_values'],'FINAL_CLASSPATH_VALUES_CHANGED')
        paths=list(dict.fromkeys(path for key in self.reader.REQUIRED_CLASSPATHS for path in values[key].split(':')))
        need(0<len(paths)<=self.reader.PATH_COUNT_LIMIT,'CLASSPATH_PATH_BOUND')
        files=[];total=0
        for i,path in enumerate(paths):
            left=self.guest('init',path);right=None
            try:
                right=self.guest('zygote64',path);a,b=metadata(left),metadata(right)
                need(all(a[k]==b[k] for k in ('st_dev','st_ino','st_size')),'TWO_ROOT_CLASSPATH_BACKING_DIFFERS')
                if expected is None:proof=self.artifact(left,self.reader.FILE_LIMIT)
                else:
                    old=expected['files'][i];need(path==old['path'] and a==old['init_view'] and b==old['zygote_view'],'CLASSPATH_BACKING_CHANGED')
                    proof={'sha256':old['sha256'],'bytes':old['bytes']}
                need(metadata(left)==a and metadata(right)==b,'CLASSPATH_READ_DRIFT')
                final=self.base['classpath_files'][i]
                names={'st_dev':'device','st_ino':'inode','st_mode':'mode','st_uid':'uid','st_gid':'gid','st_nlink':'nlink','st_size':'bytes','st_mtime_ns':'mtime_ns'}
                need(path==final['path'] and proof['sha256']==final['sha256'] and
                     all(a[k]==b[k]==final[v] for k,v in names.items()),'CLASSPATH_NOT_SAME_FINAL_BACKING')
                files.append({'path':path,'sha256':proof['sha256'],'bytes':proof['bytes'],'init_view':a,'zygote_view':b})
                total+=proof['bytes'];need(total<=self.reader.TOTAL_FILE_LIMIT,'CLASSPATH_BYTE_BOUND')
            finally:
                if right is not None:self.pool.close(right)
                self.pool.close(left)
        need(len(files)==len(self.base['classpath_files']) and total==self.base['classpath_bytes'],'FINAL_CLASSPATH_SET_CHANGED')
        return {'values':values,'files':files,'total_bytes':total}
    def data_proof(self):
        h=self.handles['init']
        return self.data.measure(self.rows['init'],self.preimage,self.pool,h['proc'],h['root'],self.deadline)
    def payloads(self,expected=None):
        result={}
        payload={row['install_target']:row for row in self.manifest['payload']}
        need(set(payload)==set(self.base['installed_payloads']),'FINAL_PAYLOAD_SET_CHANGED')
        for path,item in payload.items():
            fd=self.pool.own(os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC),'installed_payload')
            try:
                if expected is None:
                    artifact=self.artifact(fd);need(artifact['sha256']==item['sha256'] and artifact['bytes']==item['bytes'],'INSTALLED_PAYLOAD_BYTES_CHANGED')
                else:
                    need(metadata(fd)==expected[path]['file'],'INSTALLED_PAYLOAD_IDENTITY_CHANGED');artifact=expected[path]
                st=artifact['file'];need(st['st_uid']==item['install_owner']['uid'] and st['st_gid']==item['install_owner']['gid'] and
                    stat.S_IMODE(st['st_mode'])==item['install_mode'],'INSTALLED_PAYLOAD_METADATA_CHANGED')
                result[path]=artifact
            finally:self.pool.close(fd)
        return result
    def close(self):
        self.pool.close_all();self.pool.require_clean();return self.pool.summary()

def artifact_consistency(value,base,manifest):
    payload={row['install_target']:row for row in manifest['payload']}
    need(set(value['artifacts'])==set(ROLES)|{'engine'},'ORIGINAL_MAIN_AND_OWNER_CHAIN_ARTIFACTS_REQUIRED')
    for role in ROLES:need(value['artifacts'][role]['file']==value['observation']['executables'][role],'EXECUTABLE_HASH_IDENTITY_DRIFT')
    for role in ('daemon','presenter'):
        path=value['observation']['roles'][role]['executable']
        need(value['artifacts'][role]['sha256']==payload[path]['sha256'],'HOST_EXECUTABLE_NOT_FINAL_CANDIDATE')
    matches=[row for row in manifest['android_file_overrides'] if row['guest_target']==ENGINE]
    need(len(matches)==1 and matches[0]['candidate_source'] in payload and
         value['artifacts']['engine']['sha256']==payload[matches[0]['candidate_source']]['sha256'],'ENGINE_NOT_FINAL_CANDIDATE')
    for role in ANDROID:
        matches=[row for row in manifest['android_file_overrides'] if row['guest_target']==value['observation']['roles'][role]['executable']]
        if matches:
            need(len(matches)==1,'DUPLICATE_EXECUTABLE_OVERRIDE')
            source=matches[0]['candidate_source']
            pin=payload[source]['sha256'] if source in payload else matches[0]['current_source']['sha256']
            need(value['artifacts'][role]['sha256']==pin,'ANDROID_EXECUTABLE_NOT_FINAL_OVERRIDE')

def validate_observation(value,rows,policy):
    need(type(value) is dict and set(value)=={'roles','roots','namespaces','executables','child_tables',
         'host_user_namespace','limits'},'EXACT_NEW_OBSERVATION_REQUIRED')
    need(value['roles']==rows and value['limits']==LIMITS,'ACTUAL_ROLE_AND_RESOURCE_FACTS_REQUIRED')
    need(type(value['host_user_namespace']) is str and re.fullmatch(r'user:\[[1-9][0-9]*\]',value['host_user_namespace']),
         'ACTUAL_HOST_USER_NAMESPACE_REQUIRED')
    for name in ('roots','namespaces','executables'):
        need(type(value[name]) is dict and set(value[name])==set(ROLES),'ORIGINAL_MAIN_AND_OWNER_CHAIN_FACTS_REQUIRED')
    for role,row in rows.items():
        expected={'pid':row['host_pid'],'ppid':row['parent_host_pid'],'start_ticks':row['start_ticks'],
            'uids':row['uids'],'namespace_pids':row['namespace_pids'],'namespaces':row['namespaces'],
            'cgroup':'\n'.join(row['cgroup'])+'\n'}
        policy.validate_identity('android_init' if role=='init' else role,row,expected)
        root=value['roots'][role]
        need(type(root) is dict and set(root)=={'device','inode'} and
             all(type(x) is int and x>0 for x in root.values()),'REAL_ROLE_ROOT_IDENTITY_REQUIRED')
        namespaces=value['namespaces'][role]
        need(type(namespaces) is dict and set(namespaces)==set(NS),'SEVEN_NAMESPACES_FOR_EVERY_ROLE_REQUIRED')
        for name,item in namespaces.items():
            need(type(item) is dict and set(item)=={'link','device','inode'} and
                 type(item['device']) is int and item['device']>0 and type(item['inode']) is int and item['inode']>0 and
                 item['link']==name+':['+str(item['inode'])+']','NAMESPACE_LINK_AND_HELD_INODE_REQUIRED')
        need(namespaces['user']['link']==value['host_user_namespace'] and
             all(namespaces[name]['link']==row['namespaces'][name] for name in ('pid','mnt')),
             'ACTUAL_USER_AND_FINAL_PID_MNT_NAMESPACES_REQUIRED')
    need(all(value['roots'][role]==value['roots']['init'] for role in ANDROID),'ANDROID_ROOT_BACKING_DIFFERS')
    need(type(value['child_tables']) is dict and set(value['child_tables'])=={'daemon','launcher','owner_intermediary'},
         'ALL_THREE_COMPLETE_OWNER_TABLES_REQUIRED')
    for parent,child in (('daemon','launcher'),('launcher','owner_intermediary'),('owner_intermediary','init')):
        policy.validate_child_table(value['child_tables'][parent],rows[parent]['host_pid'],rows[child]['host_pid'])

def validate_files(value,base,manifest,policy):
    artifact_consistency(value,base,manifest)
    for row in value['artifacts'].values():policy.validate_artifact(row)
    policy.validate_artifact(value['cell_artifact'],base['cell_spec']['sha256'])
    need(value['cell_artifact']['bytes']==base['cell_spec']['bytes'],'FINAL_CELL_BYTE_COUNT_CHANGED')
    payload={row['install_target']:row for row in manifest['payload']}
    need(len(payload)==len(manifest['payload']) and set(value['installed_payloads'])==set(payload)==set(base['installed_payloads']),
         'EXACT_FINAL_PAYLOAD_SET_REQUIRED')
    names={'st_dev':'device','st_ino':'inode','st_mode':'mode','st_uid':'uid','st_gid':'gid',
           'st_nlink':'nlink','st_size':'bytes','st_mtime_ns':'mtime_ns'}
    for path,row in value['installed_payloads'].items():
        policy.validate_artifact(row,payload[path]['sha256']);info=row['file'];final=base['installed_payloads'][path]
        need(row['bytes']==payload[path]['bytes'] and info['st_uid']==payload[path]['install_owner']['uid'] and
             info['st_gid']==payload[path]['install_owner']['gid'] and stat.S_IMODE(info['st_mode'])==payload[path]['install_mode'],
             'EXACT_FINAL_PAYLOAD_BYTES_AND_OWNER_REQUIRED')
        # file_ref's mode is permission bits; classpath files below use full st_mode.
        for key,destination in names.items():
            if key=='st_mtime_ns':continue  # final capture did not record payload timestamps
            actual=stat.S_IMODE(info[key]) if key=='st_mode' else info[key]
            need(actual==final[destination],'PAYLOAD_NOT_SAME_FINAL_CAPTURE_BACKING')
    cp=value['classpath']
    need(type(cp) is dict and set(cp)=={'values','files','total_bytes'} and cp['values']==base['classpath_values'] and
         type(cp['files']) is list and 0<len(cp['files'])<=256 and len(cp['files'])==len(base['classpath_files']),
         'COMPLETE_FINAL_CLASSPATH_PROOF_REQUIRED')
    paths=list(dict.fromkeys(path for key in ('BOOTCLASSPATH','DEX2OATBOOTCLASSPATH') for path in cp['values'][key].split(':')))
    need([row['path'] for row in cp['files']]==paths,'EXACT_CLASSPATH_ORDER_REQUIRED')
    total=0
    for row,final in zip(cp['files'],base['classpath_files']):
        need(set(row)=={'path','bytes','sha256','init_view','zygote_view'} and row['path']==final['path'] and
             row['sha256']==final['sha256'] and type(row['bytes']) is int and 0<row['bytes']<=128*1024*1024,
             'EXACT_FINAL_CLASSPATH_ARTIFACT_REQUIRED')
        for role in ('init_view','zygote_view'):
            policy.validate_artifact({'sha256':row['sha256'],'bytes':row['bytes'],'file':row[role]})
            need(all(row[role][k]==final[v] for k,v in names.items()),'CLASSPATH_NOT_SAME_FINAL_BACKING')
        need(row['init_view']==row['zygote_view'],'BOTH_ACTUAL_CLASSPATH_VIEWS_REQUIRED');total+=row['bytes']
    need(type(cp['total_bytes']) is int and cp['total_bytes']==total==base['classpath_bytes'] and total<=768*1024*1024,
         'FINAL_CLASSPATH_TOTAL_CHANGED')

def validate_baseline(value,plan,docs,data):
    need(value.get('schema')==SCHEMA and value.get('kind')=='new-readonly-business-observation' and
         'deployment_performed' not in value and 'historical_deployment' not in value,'DISTINCT_NEW_BUSINESS_SCHEMA_REQUIRED')
    need(set(value)=={'schema','kind','plan','framework_epoch','observation','samples','artifacts','classpath','data_continuity',
        'installed_payloads','cell_artifact','started_unix_ns','finished_unix_ns','observation_fds','scope',
        'auxiliary_final_observations'},'EXACT_BUSINESS_BASELINE_FIELDS_REQUIRED')
    need(value['plan']==plan and value['framework_epoch']==docs['final_baseline']['main_epoch'],'BUSINESS_PLAN_OR_MAIN_BINDING_CHANGED')
    need(value['auxiliary_final_observations']=={'applications':docs['final_baseline']['catalog_process'],
         'source':plan['final_baseline'],'live_business_gate':False},'CATALOG_AUXILIARY_PROVENANCE_REQUIRED')
    rows=validate_inputs(plan,docs['final_baseline'],docs['deployment_manifest'],docs['transaction'],docs['post_start_receipt'])
    policy=load(POLICY,POLICY_SHA,'business_readonly_pure_validation')
    validate_observation(value['observation'],rows,policy)
    need(len(value['samples'])==3,'THREE_BUSINESS_DOUBLE_SAMPLES_REQUIRED')
    times=[]
    for sample in value['samples']:
        need(set(sample)=={'first','second','monotonic_ns'} and sample['first']==sample['second']==value['observation'],
             'BUSINESS_DOUBLE_SAMPLE_DRIFT')
        need(type(sample['monotonic_ns']) is int and sample['monotonic_ns']>0,'NEW_SAMPLE_CLOCK_REQUIRED');times.append(sample['monotonic_ns'])
    need(times==sorted(set(times)) and 10_000_000_000<=times[-1]-times[0]<=90_000_000_000,'ACTUAL_TEN_TO_NINETY_SECOND_OBSERVATION_REQUIRED')
    preimage=data.load_preimage();data.validate_live(preimage,value['data_continuity'])
    validate_files(value,docs['final_baseline'],docs['deployment_manifest'],policy)
    need(type(value['started_unix_ns']) is int and type(value['finished_unix_ns']) is int and
         0<docs['post_start_receipt']['finished_unix_ns']<=value['started_unix_ns']<value['finished_unix_ns'] and
         value['finished_unix_ns']-value['started_unix_ns']>=times[-1]-times[0],
         'BUSINESS_BASELINE_MUST_FOLLOW_THIS_COMMITTED_RUNTIME_QUALIFICATION')
    fds=value['observation_fds']
    need(all(type(fds[k]) is int for k in ('acquired','closed','close_attempts','remaining')) and
         fds['acquired']==fds['closed']==fds['close_attempts'] and fds['remaining']==0 and fds['errors']==[] and fds['acquired']>0,
         'BUSINESS_OBSERVATION_AUTHORITIES_NOT_CLOSED')
    need(value['scope']=={'namespace_entry':False,'Android_commands':0,'UI_actions':0,'App_launches':0,'helper_installs':0,
        'deployment_changes':0,'old_helpers_or_tasks_reauthorized':False,'business_actions_admitted':False,
        'whole_app_business_accepted':False,'per_app_APK_signer_version_verified':False,'per_app_engine_mapping_verified':False,
        'Binder_task_cleanup_verified':False,'Binder_UID_cleanup_verified':False},'READONLY_BASELINE_IS_NOT_BUSINESS_ACCEPTANCE')

def write_new(path,value):
    raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o400)
    try:
        view=memoryview(raw)
        while view:
            count=os.write(fd,view);need(count>0,'OUTPUT_NO_PROGRESS');view=view[count:]
        os.fsync(fd)
    finally:os.close(fd)
    fd=os.open(Path(path).parent,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)
    return {'path':str(path),'bytes':len(raw),'sha256':sha(raw)}

def capture(plan_ref,output):
    need(os.getuid()==os.geteuid()==0,'EXISTING_ROOT_OPERATOR_REQUIRED')
    data,plan,docs=inputs(plan_ref);output=Path(output)
    need(output.is_absolute() and output.parent==FINAL/'qualification' and output.name.startswith('business-baseline-') and
         not output.exists(),'FRESH_FINAL_BUSINESS_OUTPUT_REQUIRED')
    output.mkdir(mode=0o700);observer=Observation(data,plan,docs);value=None;primary=None
    started=time.time_ns()
    try:
        observer.acquire()
        artifacts={role:observer.artifact(h['exe']) for role,h in observer.handles.items()}
        artifacts['engine']=observer.engine()
        classpath=observer.classpaths();data_proof=observer.data_proof()
        payloads=observer.payloads();cell=observer.host_artifact('/etc/droidloom/cell.json')
        samples=[]
        for index in range(3):
            first,second=observer.observe(),observer.observe()
            need(first==second and (not samples or first==samples[0]['first']),'BUSINESS_OBSERVATION_DRIFT')
            samples.append({'first':first,'second':second,'monotonic_ns':time.monotonic_ns()})
            if index<2:time.sleep(5.05)
        need(observer.observe()==samples[-1]['second'],'FINAL_IDENTITY_RECHECK_FAILED')
        need(observer.classpaths(classpath)==classpath and observer.engine(False)==artifacts['engine']['file'],'FINAL_RUNTIME_BACKING_DRIFT')
        need(data.identity_projection(observer.data_proof())==data.identity_projection(data_proof),'DATA_CONTINUITY_CHANGED_DURING_CAPTURE')
        need(observer.payloads(payloads)==payloads and observer.host_artifact('/etc/droidloom/cell.json')==cell,'FINAL_PAYLOAD_OR_CELL_DRIFT')
        inputs(plan_ref)
        value={'schema':SCHEMA,'kind':'new-readonly-business-observation','plan':plan,'framework_epoch':docs['final_baseline']['main_epoch'],
            'auxiliary_final_observations':{'applications':docs['final_baseline']['catalog_process'],
                'source':plan['final_baseline'],'live_business_gate':False},
            'observation':samples[-1]['second'],'samples':samples,'artifacts':artifacts,'classpath':classpath,
            'data_continuity':data_proof,'installed_payloads':payloads,'cell_artifact':cell,
            'started_unix_ns':started,'finished_unix_ns':time.time_ns(),
            'scope':{'namespace_entry':False,'Android_commands':0,'UI_actions':0,'App_launches':0,'helper_installs':0,
                'deployment_changes':0,'old_helpers_or_tasks_reauthorized':False,'business_actions_admitted':False,
                'whole_app_business_accepted':False,'per_app_APK_signer_version_verified':False,'per_app_engine_mapping_verified':False,
                'Binder_task_cleanup_verified':False,'Binder_UID_cleanup_verified':False}}
    except BaseException as error:primary=error
    finally:
        try:closed=observer.close()
        except BaseException as error:
            closed=observer.pool.summary()
            if primary is None:primary=error
            else:primary.add_note('OBSERVATION_FD_CLOSE_FAILED:'+type(error).__name__)
    if primary is not None:
        write_new(output/'failure.json',{'schema':'pocket4-business-baseline-failure-v1','plan':plan_ref,
            'error':{'type':type(primary).__name__,'message':str(primary)},'observation_fds':closed,
            'business_actions_admitted':False,'whole_app_business_accepted':False})
        raise primary
    value['observation_fds']=closed;validate_baseline(value,plan,docs,data)
    baseline_ref=write_new(output/'baseline.private.json',value)
    q={'schema':QUAL_SCHEMA,'baseline':baseline_ref,'plan':plan_ref,'source_manifest':plan['source_manifest'],
       'main_epoch_sha256':value['framework_epoch']['sha256'],'main_identity_qualified':True,
       'predeployment_data_directory_identity_preserved':True,'business_actions_admitted':False,
       'whole_app_business_accepted':False,'observation_fds':closed}
    qref=write_new(output/'qualification.json',q)
    return {'baseline':baseline_ref,'qualification':qref,'main_epoch_sha256':q['main_epoch_sha256'],
            'business_actions_admitted':False,'whole_app_business_accepted':False}

class BusinessBaseline:
    def __init__(self,baseline_ref,qualification_ref):
        self.data=data_module();self.baseline_ref=baseline_ref;self.qualification_ref=qualification_ref
        self.value=self.data.parse(read_ref(baseline_ref));self.qualification=self.data.parse(read_ref(qualification_ref,131072))
        q=self.qualification
        need(set(q)=={'schema','baseline','plan','source_manifest','main_epoch_sha256','main_identity_qualified',
             'predeployment_data_directory_identity_preserved','business_actions_admitted','whole_app_business_accepted','observation_fds'},
             'EXACT_NEW_BUSINESS_QUALIFICATION_REQUIRED')
        self.data,self.plan,self.docs=inputs(q['plan']);validate_baseline(self.value,self.plan,self.docs,self.data)
        need(q['schema']==QUAL_SCHEMA and q['baseline']==baseline_ref and q['source_manifest']==self.plan['source_manifest'] and
             q['main_epoch_sha256']==self.value['framework_epoch']['sha256'] and q['main_identity_qualified'] is True and
             q['predeployment_data_directory_identity_preserved'] is True and q['business_actions_admitted'] is False and
             q['whole_app_business_accepted'] is False and q['observation_fds']==self.value['observation_fds'],
             'ACTUAL_NEW_IDENTITY_QUALIFICATION_REQUIRED')
    @property
    def protected_pids(self):return tuple(row['host_pid'] for row in self.value['observation']['roles'].values())
    def guard(self,*,action_attempted=False):
        observer=None;primary=None
        try:
            read_ref(self.baseline_ref);read_ref(self.qualification_ref);inputs(self.qualification['plan'])
            observer=Observation(self.data,self.plan,self.docs,seconds=15)
            observer.acquire();need(observer.observe()==self.value['observation'],'BUSINESS_MAIN_CHANGED')
            need(observer.classpaths(self.value['classpath'])==self.value['classpath'] and
                 observer.engine(False)==self.value['artifacts']['engine']['file'],'BUSINESS_RUNTIME_BACKING_CHANGED')
            current=observer.data_proof()
            need(self.data.identity_projection(current)==self.data.identity_projection(self.value['data_continuity']),
                 'BUSINESS_DATA_DIRECTORY_OR_UID_IDENTITY_CHANGED')
            observer.payloads(self.value['installed_payloads'])
            need(observer.host_artifact('/etc/droidloom/cell.json')==self.value['cell_artifact'],'BUSINESS_CELL_CHANGED')
            need(observer.observe()==self.value['observation'],'BUSINESS_MAIN_CHANGED_DURING_GUARD')
            observer.check()
        except BaseException as error:
            primary=error;error.action_attempted=action_attempted;error.outcome_unknown=action_attempted;error.automatic_retry=False
            raise
        finally:
            try:closed=observer.close() if observer is not None else None
            except BaseException as error:
                if primary is None:
                    error.action_attempted=action_attempted;error.outcome_unknown=action_attempted;error.automatic_retry=False
                    raise
                primary.add_note('BUSINESS_GUARD_FD_CLOSE_FAILED:'+type(error).__name__)
        return {'schema':'pocket4-final-business-main-guard-v1','main_epoch_sha256':self.value['framework_epoch']['sha256'],
            'business_baseline_sha256':self.baseline_ref['sha256'],'business_qualification_sha256':self.qualification_ref['sha256'],
            'exact_identity_roots_executables_namespaces_owner_chain':True,'predeployment_data_identity_preserved':True,
            'observation_fds':closed,'Binder_task_cleanup_verified':False,'Binder_UID_cleanup_verified':False,'whole_app_business_accepted':False}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan',required=True);parser.add_argument('--expect-plan-sha256',required=True)
    parser.add_argument('--output',required=True);args=parser.parse_args()
    reference={'path':args.plan,'sha256':args.expect_plan_sha256}
    raw=read_ref(reference,131072);reference['bytes']=len(raw)
    print(json.dumps(capture(reference,args.output),sort_keys=True))
if __name__=='__main__':main()
