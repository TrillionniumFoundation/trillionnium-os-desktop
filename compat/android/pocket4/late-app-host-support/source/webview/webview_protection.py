"""Original WebView APK/provider/library/data readers with fresh held identity.

The 333,998,538-byte provider is hashed in 1 MiB reads on one retained FD,
under the original 25-second bound. It never passes through command stdout.
Only historical device/inode numbers are replaced by the current qualified
Main receipt; permissions, package versions, modes and every byte pin remain.
"""
import os,re,stat,time,hashlib,types,signal
from pathlib import Path
PACKAGE = 'org.chromium.webview_shell'
OLD_PATH = '/product/app/Browser2/Browser2.apk'
OLD_SHA = '0f9dbb8ef3af284a08eb86f9558cd6c21a35dbeca2482b4b6e4b85ea49c183df'
NEW_SHA = '45e7be6309d8675cce6e2281f00d887c2e297b770fa19378b34350971dc8a06b'
OLD_BYTES, NEW_BYTES = 70877, 75170
PROVIDER = 'com.android.webview'
PROVIDER_PATH = '/product/app/webview/webview.apk'
PROVIDER_VERSION = '145.0.7632.218'
PROVIDER_CODE = 763221807
PROVIDER_SHA = 'e6b6c8e7e5d1e597c51003ca9e6dbdb4e52650ab04567e9aee535d546a2bee31'
PROVIDER_BYTES = 333998538
SHARED_LIBRARIES = {'/system/framework/android.test.base.jar': (33874, 'a31fbbc82db44e3bf9ca7e542c3aca7327ee571150b095c7b084782276a62649'), '/system/framework/android.test.mock.jar': (65214, '0b222fbae2d9499a883bdff8568e91bfb8abeaa0fc80e3e7891b14e29017dab3'), '/system/framework/android.test.runner.jar': (108162, 'b5813e64f5f95abb29f61d2cdf434da3b6759c4c1fe65dc0662cb66ec7c02d42')}
EXPECTED_LIBRARY_ORDER = list(SHARED_LIBRARIES)
EXPECTED_FLATTENED = [EXPECTED_LIBRARY_ORDER[i] for i in (2, 1, 0, 1, 0)]
def require(value,reason):
    if not value:raise RuntimeError(reason)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def meta(info):
    return {k:getattr(info,k) for k in ('st_dev','st_ino','st_uid','st_gid','st_mode',
                                      'st_nlink','st_size','st_mtime_ns','st_ctime_ns')}

def package_identity(dump, package, uid, version):
    active = re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)',dump,re.M|re.S)
    require(len(active)==1 and re.findall(r'^  Package \[([^]]+)\]',active[0],re.M)==[package] and
            re.findall(r'^    appId=(\d+)$',active[0],re.M)==[str(uid)] and
            re.findall(r'^    versionCode=(\d+)\b',active[0],re.M)==[str(version)], 'PACKAGE_UID_OR_VERSION_CHANGED')
    users = re.findall(r'^    User 0: (.*)$',active[0],re.M)
    require(len(users)==1 and all(re.search(r'\b'+key+'='+value+r'\b',users[0]) for key,value in
            (('installed','true'),('hidden','false'),('suspended','false'),('enabled','[01]'))),
            'PACKAGE_USER_STATE_CHANGED')

def provider_ready(raw):
    lines = [' '.join(line.split()) for line in raw.splitlines()]
    def single(prefix):
        matches = [line[len(prefix):] for line in lines if line.startswith(prefix)]
        require(len(matches)==1,'PROVIDER_STATE_FIELD_NOT_UNIQUE:'+prefix)
        return matches[0]
    expected = '('+PROVIDER+', '+PROVIDER_VERSION+')'
    require(single('Current WebView package (name, version): ')==expected and
            single('Preferred WebView package (name, version): ')==expected and
            single('WebView package dirty: ')=='false' and single('Any WebView package installed: ')=='true',
            'PROVIDER_SELECTION_OR_READY_STATE_CHANGED')
    started,finished = single('Number of relros started: '),single('Number of relros finished: ')
    require(started.isdecimal() and finished.isdecimal() and int(started)>0 and started==finished,
            'PROVIDER_RELRO_NOT_READY')
    valid = [line for line in lines if line.startswith('Valid package '+PROVIDER+' ')]
    require(valid==['Valid package '+PROVIDER+' (versionName: '+PROVIDER_VERSION+', versionCode: '+
        str(PROVIDER_CODE)+', targetSdkVersion: 36) is installed/enabled for all users'], 'PROVIDER_PACKAGE_NOT_VALID')
    return {'package':PROVIDER,'version_name':PROVIDER_VERSION,'version_code':PROVIDER_CODE,
            'relros_started':int(started),'relros_finished':int(finished),'ready':True}

def fp(info):return {k:getattr(info,k) for k in ('st_dev','st_ino','st_uid','st_gid','st_mode')}

def identity(session,package,expected_sha,expected_uid=None,expected_code=1):
    raw=session.android(['/system/bin/dumpsys','package',package]).decode()
    blocks=re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)',raw,re.M|re.S)
    need(len(blocks)==1 and re.findall(r'^  Package \[([^]]+)\]',blocks[0],re.M)==[package],'PACKAGE_SECTION_CHANGED')
    block=blocks[0]
    def one(pattern):
        values=re.findall(pattern,block,re.M);need(len(values)==1,'PACKAGE_FIELD_AMBIGUOUS:'+pattern);return values[0]
    uid=int(one(r'^    appId=(\d+)$'));code=int(one(r'^    versionCode=(\d+)\b'))
    need((expected_uid is None or uid==expected_uid) and code==expected_code,'PACKAGE_UID_OR_VERSION_CHANGED')
    state=one(r'^    User 0: (.*)$')
    need(all(re.search(r'\b'+k+'='+v+r'\b',state) for k,v in
        (('installed','true'),('hidden','false'),('suspended','false'),('enabled','[01]'))),'PACKAGE_USER_STATE')
    paths=session.android(['/system/bin/pm','path','--user','0',package]).decode().splitlines()
    need(len(paths)==1 and paths[0].startswith('package:/') and paths[0].endswith('.apk'),'SINGLE_APK_PATH_REQUIRED')
    data,metadata=session.target.read_file(paths[0][8:],16*1024*1024,single_link=True)
    need(sha(data)==expected_sha,'INSTALLED_APK_HASH_CHANGED')
    directories={}
    for label,path in [('ce','/data/user/0/'+package),('de','/data/user_de/0/'+package)]:
        fd=session.target.open_root(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:info=os.fstat(fd);directories[label]=fp(info)
        finally:os.close(fd)
        inode=int(re.search(r'\b'+label+r'DataInode=(\d+)\b',state)[1])
        need(info.st_uid==info.st_gid==uid and info.st_ino==inode,'PACKAGE_DATA_IDENTITY_CHANGED')
    session.guard()
    return {'package':package,'uid':uid,'version_code':code,'apk_path':paths[0][8:],
        'apk_sha256':sha(data),'apk_bytes':len(data),'directories':directories}

def permission_rows(raw, package):
    sections = re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)', raw, re.M | re.S)
    need(len(sections) == 1 and re.findall(r'^  Package \[([^]]+)\]', sections[0], re.M) == [package],
         'PERMISSION_PACKAGE_SECTION')
    rows = sorted(line.strip() for line in sections[0].splitlines()
                  if re.search(r'android\.permission\.[A-Z_]+: granted=', line))
    need(rows, 'NO_PERMISSION_ROWS')
    return rows

def shared_library_rows(raw):
    sections=re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)',raw,re.M|re.S)
    require(len(sections)==1,'ACTIVE_PACKAGE_SECTION')
    block=sections[0]
    result={}
    for key in ('usesLibraries','usesOptionalLibraries','usesLibraryFiles','usesStaticLibraries','usesSdkLibraries'):
        values=re.findall(r'^    '+key+r':\n((?:^      \S.*\n)+)',block,re.M)
        require(len(values)<=1,'DUPLICATE_LIBRARY_FIELD')
        result[key]=[line.strip() for line in values[0].splitlines()] if values else []
    require(result=={'usesLibraries':['android.test.base','android.test.mock','android.test.runner'],
        'usesOptionalLibraries':[],'usesLibraryFiles':EXPECTED_LIBRARY_ORDER,
        'usesStaticLibraries':[],'usesSdkLibraries':[]},'ART07_RESOLVED_LIBRARIES_CHANGED')
    return result

def app_identity(s,expected_sha):
    require(expected_sha in (OLD_SHA,NEW_SHA),'REVIEWED_APK_REQUIRED')
    value=identity(s,PACKAGE,expected_sha,10060,1)
    expected_bytes=OLD_BYTES if expected_sha==OLD_SHA else NEW_BYTES
    require(value['apk_bytes']==expected_bytes,'APPLIED_APK_LENGTH_CHANGED')
    if expected_sha==OLD_SHA:
        require(value['apk_path']==OLD_PATH,'ORIGINAL_PRODUCT_APK_REQUIRED')
    else:
        require(re.fullmatch(r'/data/app/~~[^/]+/org\.chromium\.webview_shell-[^/]+/base\.apk',
                            value['apk_path']) is not None,'UPDATED_APP_BASE_APK_PATH_REQUIRED')
    raw=s.android(['/system/bin/dumpsys','package',PACKAGE],12).decode('utf-8','strict')
    package_identity(raw,PACKAGE,10060,1)
    active=re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)',raw,re.M|re.S)
    require(len(active)==1 and re.findall(r'^    versionCode=(\d+) minSdk=(\d+) targetSdk=(\d+)$',
        active[0],re.M)==[('1','37','29')],'WEBVIEW_SDK_CHANGED')
    require(re.findall(r'^    splits=(.*)$',active[0],re.M)==['[base]'],'SINGLE_BASE_SPLIT_REQUIRED')
    first=re.findall(r'^      firstInstallTime=(.*)$',active[0],re.M)
    require(len(first)==1,'FIRST_INSTALL_TIME_AMBIGUOUS')
    value['first_install_time']=first[0]
    value['permissions']=permission_rows(raw,PACKAGE)
    value['shared_library_configuration']=shared_library_rows(raw)
    value['shared_library_files']={}
    for path,(size,pin) in SHARED_LIBRARIES.items():
        data,info=s.target.read_file(path,131072,single_link=True)
        require(len(data)==size and sha(data)==pin,'ART07_SHARED_LIBRARY_BYTES_CHANGED')
        value['shared_library_files'][path]={'bytes':size,'sha256':pin}
    s.guard();return value

def provider_identity(s):
    paths=s.android(['/system/bin/pm','path','--user','0',PROVIDER],12).decode().splitlines()
    require(paths==['package:'+PROVIDER_PATH],'PROVIDER_PATH_CHANGED')
    dump=s.android(['/system/bin/dumpsys','package',PROVIDER],12).decode('utf-8','strict')
    package_identity(dump,PROVIDER,10071,PROVIDER_CODE)
    permissions=permission_rows(dump,PROVIDER)
    fd=s.target.open_root(PROVIDER_PATH,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd);fingerprint=meta(before)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink==1
            and (before.st_size,before.st_uid,before.st_gid,stat.S_IMODE(before.st_mode))
                ==(PROVIDER_BYTES,0,0,0o644),'PROVIDER_FILE_METADATA_CHANGED')
        expected=getattr(s,'protection_provider_expected',None)
        require(expected is None or fingerprint==expected,'FRESH_PROVIDER_HELD_IDENTITY_CHANGED')
        digest=hashlib.sha256();count=0;end=min(time.monotonic()+25,getattr(s,'deadline',float('inf')))
        while count<PROVIDER_BYTES:
            require(time.monotonic()<end,'PROVIDER_HASH_DEADLINE')
            chunk=os.pread(fd,min(1048576,PROVIDER_BYTES-count),count)
            require(chunk,'PROVIDER_SHORT_READ');digest.update(chunk);count+=len(chunk)
        require(count==PROVIDER_BYTES and digest.hexdigest()==PROVIDER_SHA
                and meta(os.fstat(fd))==fingerprint,'PROVIDER_WHOLE_BYTES_CHANGED')
        again=s.target.open_root(PROVIDER_PATH,os.O_RDONLY|os.O_NOFOLLOW)
        try:require(meta(os.fstat(again))==fingerprint,'PROVIDER_CURRENT_PATH_CHANGED')
        finally:os.close(again)
    finally:os.close(fd)
    state=provider_ready(s.android(['/system/bin/dumpsys','webviewupdate'],12).decode('utf-8','strict'))
    s.guard()
    return {'package':PROVIDER,'uid':10071,'version_code':PROVIDER_CODE,'version_name':PROVIDER_VERSION,
        'apk_path':PROVIDER_PATH,'apk_bytes':PROVIDER_BYTES,'apk_sha256':PROVIDER_SHA,
        'file_metadata':fingerprint,'permissions':permissions,'service':state,'whole_file_hashed':True}

need=require

HOME_RESOLVE=['/system/bin/cmd','package','resolve-activity','--brief','--user','0',
    '-a','android.intent.action.MAIN','-c','android.intent.category.HOME']

def home_only(session):
    """The original one pre-existing home task, freshly resolved in this Main."""
    raw=session.android(HOME_RESOLVE,12).decode('utf-8','strict').strip()
    require(re.fullmatch(r'[A-Za-z][A-Za-z0-9_.]*/[A-Za-z0-9_.$]+',raw), 'ONE_ACTUAL_DEFAULT_HOME_COMPONENT')
    roots,tasks=session.components['webview_trial10.py'].parse_stacks(
        session.android(['/system/bin/cmd','activity','stack','list'],15).decode('utf-8','strict'))
    children=[(root,child) for root in roots.values() for child in root['children']]
    def expanded(component):
        package,activity=component.split('/',1)
        return package+'/'+(package+activity if activity.startswith('.') else activity)
    require(len(tasks)==len(children)==1 and expanded(children[0][1]['component'])==expanded(raw)
        and children[0][0]['display']==children[0][0]['user']==children[0][1]['user']==0
        and raw.split('/')[0] not in (PACKAGE,PROVIDER), 'ONLY_THIS_FRESH_MAIN_EXISTING_HOME_TASK')
    return {'component':raw,'task':next(iter(tasks)),'roots':roots,'tasks':sorted(tasks)}


def stable_shell(c,current,profile):
    expected=profile.SHELL_ORIGINAL_STATE
    c.need({k:v for k,v in current.items() if k not in ('directories','apk_path')}==expected,
        'ORIGINAL_WEBVIEW_UID_VERSION_ALL_PERMISSIONS_FIRST_INSTALL_AND_LIBRARIES')
    c.need(re.fullmatch(r'/data/app/~~[^/]+/org\.chromium\.webview_shell-[^/]+/base\.apk',current['apk_path']),
        'ORIGINAL_INSTALLED_SINGLE_BASE_APK_SCOPE')
    c.need(set(current['directories'])=={'ce','de'} and all(
        row['st_uid']==row['st_gid']==profile.TARGET['uid'] and stat.S_ISDIR(row['st_mode'])
        and row['st_ino']>0 for row in current['directories'].values()), 'ACTUAL_CE_DE_DIRECTORY_IDENTITIES')


def stable_provider(c,current,profile):
    c.need({k:current[k] for k in profile.PROVIDER}==profile.PROVIDER
        and set(current)==set(profile.PROVIDER)|{'file_metadata','service','whole_file_hashed'}
        and current['whole_file_hashed'] is True, 'ORIGINAL_PROVIDER_IDENTITY_AND_WHOLE_FILE_BYTES')
    f=current['file_metadata'];c.need(set(f)=={'st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns'}
        and all(type(v) is int for v in f.values()) and stat.S_ISREG(f['st_mode'])
        and f['st_uid']==f['st_gid']==0 and f['st_nlink']==1 and f['st_size']==PROVIDER_BYTES
        and stat.S_IMODE(f['st_mode'])==profile.PROVIDER_MODE, 'FRESH_ACTUAL_PROVIDER_FILE_METADATA')
    ready=current['service'];c.need(ready=={'package':PROVIDER,'version_name':PROVIDER_VERSION,
        'version_code':PROVIDER_CODE,'relros_started':ready.get('relros_started'),
        'relros_finished':ready.get('relros_started'),'ready':True}
        and type(ready['relros_started']) is int and ready['relros_started']>0, 'ACTUAL_READY_PROVIDER_RELRO')


def identity_reads():
    return [(['/system/bin/dumpsys','package',PACKAGE],20),
        (['/system/bin/pm','path','--user','0',PACKAGE],20),
        (['/system/bin/dumpsys','package',PACKAGE],12),
        (['/system/bin/pm','path','--user','0',PROVIDER],12),
        (['/system/bin/dumpsys','package',PROVIDER],12),
        (['/system/bin/dumpsys','webviewupdate'],12)]


def validate(c,receipt,request,profile,source_ref):
    fields={'schema','state','baseline','qualification','target_identity','source','framework_epoch_sha256',
        'after','provider_after','reads','before_guard','after_guard','held_binding_closed','source_unchanged',
        'Android_mutations','UI_actions','old_runtime_authority_transferred','whole_app_business_accepted'}
    c.need(set(receipt)==fields and receipt['schema']=='pocket4-final-webview-current-protection-v1'
        and receipt['state']=='OBSERVED' and receipt['source']==source_ref
        and all(receipt[k]==request[k] for k in ('baseline','qualification','target_identity'))
        and receipt['held_binding_closed'] is receipt['source_unchanged'] is True
        and receipt['Android_mutations']==receipt['UI_actions']==0
        and receipt['old_runtime_authority_transferred'] is False
        and receipt['whole_app_business_accepted'] is False, 'COMPLETE_FRESH_WEBVIEW_PROTECTION_RECEIPT')
    c.read_ref(source_ref)
    identity=c.parse(c.read_ref(request['target_identity']))
    c.validate_identity(identity,profile.TARGET,request['baseline'],request['qualification'])
    c.need(receipt['framework_epoch_sha256']==identity['epoch_sha256'], 'PROTECTION_IS_SAME_QUALIFIED_MAIN')
    stable_shell(c,receipt['after'],profile);stable_provider(c,receipt['provider_after'],profile)
    c.need(len(identity['artifacts'])==1 and identity['artifacts'][0]['guest_path']==receipt['after']['apk_path'],
        'PROTECTION_MATCHES_FRESH_SIGNED_SHELL_APK')
    expected=identity_reads();c.need(len(receipt['reads'])==len(expected),'COMPLETE_ORIGINAL_IDENTITY_READ_SET')
    for row,(argv,timeout) in zip(receipt['reads'],expected):
        c.need(set(row)=={'argv','timeout','stdout','logical','transport','command_observation','result'}
            and row['argv']==argv and row['timeout']==timeout, 'EXACT_ORIGINAL_IDENTITY_READ_ORDER')
        actual=c.parse(c.read_ref(row['result']));transport=c.parse(c.read_ref(row['transport']))
        c.need(actual['argv'][-len(argv):]==argv and actual['returncode']==0 and actual['timed_out'] is False
            and actual['host_retirement_proved'] is True and actual['evidence_complete'] is True
            and not actual['errors'] and actual['stdout']==row['stdout']
            and actual==row['command_observation']
            and transport['logical']==row['logical'] and row['logical']['argv']==argv
            and row['logical']['epoch_sha256']==receipt['framework_epoch_sha256']
            and row['logical']['Android_mutation'] is False and row['logical']['root_read'] is False
            and transport['lease_entered'] is transport['lease_released'] is transport['host_retirement_proved'] is True
            and transport['error_type'] is None and transport['post_guard'], 'ACTUAL_HELD_READ_AND_CHILD_RETIREMENT')
        text=c.read_ref(row['stdout']).decode('utf-8','strict')
        if argv[:2]==['/system/bin/dumpsys','package']:
            pkg=argv[-1];package_identity(text,pkg,10060 if pkg==PACKAGE else 10071,1 if pkg==PACKAGE else PROVIDER_CODE)
            c.need(permission_rows(text,pkg)==receipt['after' if pkg==PACKAGE else 'provider_after']['permissions'],
                'RECORDED_PACKAGE_PERMISSION_ROWS_ARE_ORIGINAL')
        elif argv[:3]==['/system/bin/pm','path','--user']:
            c.need(text.splitlines()==['package:'+receipt['after' if argv[-1]==PACKAGE else 'provider_after']['apk_path']],
                'RECORDED_EXACT_APK_PATH')
        else:c.need(provider_ready(text)==receipt['provider_after']['service'],'RECORDED_READY_PROVIDER_STATE')
    c.need(receipt['before_guard'] and receipt['after_guard'],'INDEPENDENT_PROTECTION_MAIN_GUARDS')
    return receipt


def collect(c,request,output,profile,source_ref):
    c.need(set(request)=={'baseline','qualification','target_identity'} and os.geteuid()==0,
        'NEW_MAIN_SIGNED_SHELL_IDENTITY_BEFORE_PROTECTION')
    target=c.parse(c.read_ref(request['target_identity']))
    c.validate_identity(target,profile.TARGET,request['baseline'],request['qualification'])
    root=c.private_dir(output,create=True);journal=c.private_dir(root/'commands',create=True)
    result={'schema':'pocket4-final-webview-current-protection-v1','state':'STARTING',**request,'source':source_ref,
        'framework_epoch_sha256':target['epoch_sha256'],'reads':[],'held_binding_closed':False,
        'source_unchanged':False,'Android_mutations':0,'UI_actions':0,'old_runtime_authority_transferred':False,
        'whole_app_business_accepted':False}
    calls=identity_reads();view=None;first=None
    def admit(argv,timeout,root_read,private):
        index=len(result['reads']);c.need(index<len(calls) and (argv,timeout)==calls[index]
            and not root_read and not private,'ONLY_ORIGINAL_READONLY_WEBVIEW_PROTECTION_COMMAND')
    try:
        c.read_ref(source_ref)
        view=c.MainView(request['baseline'],request['qualification'],journal,admit,support_ref=c.SUPPORT_REF)
        result['before_guard']=view.guard()
        c.need(view.baseline.value['data_continuity']['package_uids'][PACKAGE]==10060,
            'ACTUAL_PREDEPLOYMENT_SHELL_DATA_CONTINUITY')
        def android(argv,timeout=20):
            raw,proof=view.command(argv,timeout)
            name='read-%03d'%view.index
            ref=c.regular(journal/(name+'.result.json'),contents=False)
            actual=c.parse(c.read_ref(ref))
            result['reads'].append({'argv':list(argv),'timeout':timeout,'stdout':actual['stdout'],
                'logical':proof['logical'],'transport':proof['transport'],
                'command_observation':proof['command_observation'],'result':ref})
            return raw
        adapter=types.SimpleNamespace(android=android,target=view.target,guard=view.guard,protection_provider_expected=None)
        result['after']=app_identity(adapter,NEW_SHA);result['provider_after']=provider_identity(adapter)
        result['after_guard']=view.guard();result['state']='OBSERVED'
    except BaseException as error:
        first=error;result['state']='FAILED_OR_UNKNOWN';result['error']={'type':type(error).__name__,'message':str(error)}
    finally:
        if view is not None:
            try:view.close();result['held_binding_closed']=True
            except BaseException as error:
                first=first or error;result['state']='FAILED_OR_UNKNOWN';result['close_error']=str(error)
        try:c.read_ref(source_ref);result['source_unchanged']=True
        except BaseException as error:first=first or error;result['state']='FAILED_OR_UNKNOWN';result['source_error']=str(error)
        if first is None:
            try:validate(c,result,request,profile,source_ref)
            except BaseException as error:first=error;result['state']='FAILED_OR_UNKNOWN';result['validation_error']=str(error)
        ref=c.write_new(root/'result.json',result)
    if first is not None:raise first
    return ref


class HeldProvider:
    """One immutable provider FD; metadata guards and exact before/after hashes."""
    def __init__(self,c,target,expected):
        self.c=c;self.expected=expected;self.fd=None;self.closed=False
        try:
            self.fd=target.open_root(PROVIDER_PATH,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
            self.verify(target);self.rehash(target)
        except BaseException:self.close();raise
    def verify(self,target):
        self.c.need(not self.closed and self.fd is not None and meta(os.fstat(self.fd))==self.expected,
            'SAME_RETAINED_PROVIDER_FD_FULL_IDENTITY')
        fd=target.open_root(PROVIDER_PATH,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:self.c.need(meta(os.fstat(fd))==self.expected,'SAME_CURRENT_PROVIDER_NAMED_PATH')
        finally:os.close(fd)
    def rehash(self,target):
        self.verify(target);deadline=time.monotonic()+25;digest=hashlib.sha256();count=0
        while count<PROVIDER_BYTES:
            self.c.need(time.monotonic()<deadline,'ORIGINAL_PROVIDER_25_SECOND_HASH_BOUND')
            raw=os.pread(self.fd,min(1048576,PROVIDER_BYTES-count),count)
            self.c.need(raw,'ORIGINAL_PROVIDER_COMPLETE_BYTES_REQUIRED');digest.update(raw);count+=len(raw)
        self.c.need(count==PROVIDER_BYTES and not os.pread(self.fd,1,count) and digest.hexdigest()==PROVIDER_SHA,
            'ORIGINAL_COMPLETE_PROVIDER_BYTES_AND_EOF')
        self.verify(target)
    def close(self):
        fd=self.fd;self.fd=None;self.closed=True
        if fd is not None:os.close(fd)
