#!/usr/bin/python3 -I
"""Gallery18 package/metadata preservation only; no UI, account or media reads."""
import hashlib, io, os, re, stat, struct, zipfile
from pathlib import Path

PACKAGE='com.android.gallery3d'
OLD_PATH='/product/app/Gallery2/Gallery2.apk'
OLD_SHA='835fe119745324276457b4434fc39f25b633e752c822d2fc9be40eb4b2d45439'
NEW_SHA='6677d382076f10f0502c813c7614c32127ccf3cd8f02756b75a8c3574980e87e'
OLD_BYTES,NEW_BYTES=7390425,7493022
MANIFEST_SHA='2d4399372058787b9a9986a797ddc8f2d3722e4cee85a055721da4dc546890ee'
DEX_SHA='6a994fabd3494dcbf071d727922351f72ff8fdbee0d3d3c1a46b6ed30ca034ee'
EXPECTED = __import__('json').loads("{\"package\":\"com.android.gallery3d\",\"uid\":10064,\"version_code\":40030,\"min_sdk\":37,\"target_sdk\":28,\"version_name\":\"1.1.40030\",\"first_install_time\":\"2026-10-07 03:30:59\",\"directories\":{\"ce\":{\"st_dev\":1811,\"st_gid\":10064,\"st_ino\":131655,\"st_mode\":16832,\"st_uid\":10064},\"de\":{\"st_dev\":1811,\"st_gid\":10064,\"st_ino\":131658,\"st_mode\":16832,\"st_uid\":10064}},\"all_permission_rows\":[\"android.permission.ACCESS_BACKGROUND_LOCATION: granted=false, flags=[ REVOKE_WHEN_REQUESTED|USER_SENSITIVE_WHEN_GRANTED|USER_SENSITIVE_WHEN_DENIED|RESTRICTION_UPGRADE_EXEMPT]\",\"android.permission.ACCESS_COARSE_LOCATION: granted=false, flags=[ USER_SENSITIVE_WHEN_GRANTED|USER_SENSITIVE_WHEN_DENIED]\",\"android.permission.ACCESS_FINE_LOCATION: granted=false, flags=[ USER_SENSITIVE_WHEN_GRANTED|USER_SENSITIVE_WHEN_DENIED]\",\"android.permission.ACCESS_LOCAL_NETWORK: granted=true, flags=[ REVOKE_WHEN_REQUESTED|USER_SENSITIVE_WHEN_GRANTED|USER_SENSITIVE_WHEN_DENIED]\",\"android.permission.ACCESS_MEDIA_LOCATION: granted=true, flags=[ USER_SENSITIVE_WHEN_GRANTED|USER_SENSITIVE_WHEN_DENIED|RESTRICTION_UPGRADE_EXEMPT|GRANTED_BY_ROLE]\",\"android.permission.ACCESS_NETWORK_STATE: granted=true\",\"android.permission.CAMERA: granted=false, flags=[ USER_SENSITIVE_WHEN_GRANTED|USER_SENSITIVE_WHEN_DENIED]\",\"android.permission.GET_ACCOUNTS: granted=false, flags=[ USER_SENSITIVE_WHEN_GRANTED|USER_SENSITIVE_WHEN_DENIED]\",\"android.permission.INTERNET: granted=true\",\"android.permission.MANAGE_ACCOUNTS: granted=true\",\"android.permission.NFC: granted=true\",\"android.permission.POST_NOTIFICATIONS: granted=false, flags=[ USER_SENSITIVE_WHEN_GRANTED|USER_SENSITIVE_WHEN_DENIED]\",\"android.permission.READ_EXTERNAL_STORAGE: granted=true, flags=[ REVOKE_WHEN_REQUESTED|USER_SENSITIVE_WHEN_GRANTED|USER_SENSITIVE_WHEN_DENIED|RESTRICTION_SYSTEM_EXEMPT|RESTRICTION_UPGRADE_EXEMPT|GRANTED_BY_ROLE]\",\"android.permission.READ_MEDIA_AUDIO: granted=true, flags=[ USER_SENSITIVE_WHEN_GRANTED|USER_SENSITIVE_WHEN_DENIED|RESTRICTION_UPGRADE_EXEMPT|GRANTED_BY_ROLE]\",\"android.permission.READ_MEDIA_IMAGES: granted=true, flags=[ USER_SENSITIVE_WHEN_GRANTED|USER_SENSITIVE_WHEN_DENIED|RESTRICTION_UPGRADE_EXEMPT|GRANTED_BY_ROLE]\",\"android.permission.READ_MEDIA_VIDEO: granted=true, flags=[ USER_SENSITIVE_WHEN_GRANTED|USER_SENSITIVE_WHEN_DENIED|RESTRICTION_UPGRADE_EXEMPT|GRANTED_BY_ROLE]\",\"android.permission.READ_MEDIA_VISUAL_USER_SELECTED: granted=true, flags=[ USER_SENSITIVE_WHEN_GRANTED|USER_SENSITIVE_WHEN_DENIED|RESTRICTION_UPGRADE_EXEMPT|GRANTED_BY_ROLE]\",\"android.permission.READ_SYNC_SETTINGS: granted=true\",\"android.permission.RECEIVE_BOOT_COMPLETED: granted=true\",\"android.permission.RECORD_AUDIO: granted=false, flags=[ USER_SENSITIVE_WHEN_GRANTED|USER_SENSITIVE_WHEN_DENIED]\",\"android.permission.SET_WALLPAPER: granted=true\",\"android.permission.USE_CREDENTIALS: granted=true\",\"android.permission.VIBRATE: granted=true\",\"android.permission.WAKE_LOCK: granted=true\",\"android.permission.WRITE_EXTERNAL_STORAGE: granted=true, flags=[ USER_SENSITIVE_WHEN_GRANTED|USER_SENSITIVE_WHEN_DENIED|RESTRICTION_SYSTEM_EXEMPT|RESTRICTION_UPGRADE_EXEMPT|GRANTED_BY_ROLE]\",\"android.permission.WRITE_SETTINGS: granted=true\",\"android.permission.WRITE_SYNC_SETTINGS: granted=true\",\"com.android.gallery3d.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION: granted=true\",\"com.android.gallery3d.permission.GALLERY_PROVIDER: granted=true\"],\"disabled_components\":[\"com.android.camera.CameraLauncher\",\"com.android.camera.DisableCameraReceiver\"],\"enabled_components\":[],\"shared_library_configuration\":{\"usesLibraries\":[\"android.test.base\",\"android.hidl.manager-V1.0-java\",\"android.hidl.base-V1.0-java\"],\"usesOptionalLibraries\":[\"com.google.android.media.effects\",\"org.apache.http.legacy\"],\"usesLibraryFiles\":[\"/system/framework/android.test.base.jar\",\"/system/framework/android.hidl.manager-V1.0-java.jar\",\"/system/framework/android.hidl.base-V1.0-java.jar\",\"/system/framework/org.apache.http.legacy.jar\"],\"usesStaticLibraries\":[],\"usesSdkLibraries\":[]},\"user0_state\":\"ceDataInode=131655 deDataInode=131658 pccCeDataInode=0 pccDeDataInode=0 installed=true hidden=false suspended=false appLockEnabled=false distractionFlags=0 stopped=false notLaunched=false enabled=0 instant=false virtual=false quarantined=false\",\"install_reason\":\"0\",\"uninstall_reason\":\"0\",\"gids\":\"[3003]\",\"data_dir\":\"/data/user/0/com.android.gallery3d\",\"native_configuration\":{\"extract_native_libs\":\"true\",\"primary_cpu_abi\":\"x86_64\",\"secondary_cpu_abi\":\"null\",\"cpu_abi_override\":\"null\"},\"hidden_api_policy\":\"2\",\"uses_non_sdk_api\":\"false\",\"splits\":\"[base]\",\"signing_version\":\"3\"}")

def need(ok,reason):
    if not ok:raise RuntimeError(reason)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def fp(info):
    return {k:getattr(info,k) for k in ('st_dev','st_ino','st_uid','st_gid','st_mode')}

def active_block(raw):
    found=re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)',raw,re.M|re.S)
    need(len(found)==1,'ONE_ACTIVE_PACKAGES_SECTION_REQUIRED')
    need(re.findall(r'^  Package \[([^]]+)\]',found[0],re.M)==[PACKAGE],
         'EXACT_GALLERY_ACTIVE_PACKAGE_REQUIRED')
    return found[0]

def parse_package(raw):
    block=active_block(raw)
    def one(pattern):
        found=re.findall(pattern,block,re.M)
        need(len(found)==1,'PACKAGE_FIELD_NOT_UNIQUE:'+pattern)
        return found[0]
    def field(name,indent=4):
        return one('^'+' '*indent+re.escape(name)+r'=(.*)$')
    uid=int(field('appId'))
    version=one(r'^    versionCode=(\d+) minSdk=(\d+) targetSdk=(\d+)$')
    need(uid==10064 and version==('40030','37','28'),'GALLERY_PACKAGE_IDENTITY_CHANGED')
    userlines=re.findall(r'^    User (\d+): (.*)$',block,re.M)
    need(len(userlines)==1 and userlines[0][0]=='0','EXACT_USER0_ONLY_REQUIRED')
    state=userlines[0][1]
    tokens=state.split()
    need(all(re.fullmatch(r'[A-Za-z][A-Za-z0-9]*=\S+',s) for s in tokens) and
         len(tokens)==len({s.split('=',1)[0] for s in tokens}),'USER_STATE_GRAMMAR')
    need(state==EXPECTED['user0_state'],'GALLERY_USER0_STATE_CHANGED')
    permissions=[]
    for line in block.splitlines():
        if ': granted=' not in line:continue
        item=line.strip()
        need(re.fullmatch(r'[A-Za-z][A-Za-z0-9_.]+: granted=(true|false)(?:, flags=\[[A-Z_ |]*\])?',item)
             is not None,'UNPARSED_PERMISSION_ROW')
        permissions.append(item)
    names=[row.split(':',1)[0] for row in permissions]
    need(len(names)==len(set(names))==29,'ALL_29_PERMISSION_ROWS_REQUIRED')
    need(set(names)=={r.split(':',1)[0] for r in EXPECTED['all_permission_rows']},
         'PERMISSION_NAMES_CHANGED')
    libraries={}
    for key in ('usesLibraries','usesOptionalLibraries','usesLibraryFiles',
                'usesStaticLibraries','usesSdkLibraries'):
        heads=re.findall(r'^    '+key+r':\n',block,re.M)
        found=re.findall(r'^    '+key+r':\n((?:^      \S.*\n)+)',block,re.M)
        need(len(heads)<=1 and len(found)==len(heads),'LIBRARY_LIST_GRAMMAR:'+key)
        libraries[key]=[line.strip() for line in found[0].splitlines()] if found else []
    components={}
    for key in ('enabledComponents','disabledComponents'):
        heads=re.findall(r'^      '+key+r':\n',block,re.M)
        found=re.findall(r'^      '+key+r':\n((?:^        [A-Za-z0-9_.$]+\n)+)',block,re.M)
        need(len(heads)<=1 and len(found)==len(heads),'COMPONENT_LIST_GRAMMAR:'+key)
        names=[line.strip() for line in found[0].splitlines()] if found else []
        need(len(names)==len(set(names)),'DUPLICATE_COMPONENT')
        components[key]=sorted(names)
    protected={
        'package':PACKAGE,'uid':uid,'version_code':int(version[0]),
        'min_sdk':int(version[1]),'target_sdk':int(version[2]),
        'version_name':field('versionName'),'user0_state':state,
        'first_install_time':field('firstInstallTime',6),
        'install_reason':field('installReason',6),'uninstall_reason':field('uninstallReason',6),
        'gids':field('gids',6),'data_dir':field('dataDir',6),
        'native_configuration':{'extract_native_libs':field('extractNativeLibs'),
            'primary_cpu_abi':field('primaryCpuAbi'),'secondary_cpu_abi':field('secondaryCpuAbi'),
            'cpu_abi_override':field('cpuAbiOverride')},
        'hidden_api_policy':field('hiddenApiEnforcementPolicy'),
        'uses_non_sdk_api':field('usesNonSdkApi'),
        'splits':field('splits'),'signing_version':field('apkSigningVersion'),
        'all_permission_rows':sorted(permissions),
        'shared_library_configuration':libraries,
        'enabled_components':components['enabledComponents'],
        'disabled_components':components['disabledComponents']}
    mutable_code_metadata={name:field(name) for name in
        ('codePath','resourcePath','legacyNativeLibraryDir','timeStamp','lastUpdateTime',
         'installerPackageName','installerPackageUid','initiatingPackageName',
         'originatingPackageName','packageSource','flags','privateFlags','pkgFlags',
         'privatePkgFlags')}
    need(mutable_code_metadata['codePath']==mutable_code_metadata['resourcePath'],
         'CODE_RESOURCE_ROOTS_DIFFER')
    return {'protected':protected,'code_and_install_metadata':mutable_code_metadata,
            'selected_block_sha256':sha(block.encode()),'dump_sha256':sha(raw.encode())}

def native_payload(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names=archive.namelist()
        need(len(names)==len(set(names)),'DUPLICATE_ZIP_ENTRY')
        need(sha(archive.read('AndroidManifest.xml'))==MANIFEST_SHA,'MANIFEST_CHANGED')
        out={}
        for name in sorted(names):
            if not name.startswith('lib/') or not name.endswith('.so'):continue
            need(re.fullmatch(r'lib/[A-Za-z0-9_-]+/[A-Za-z0-9_.+-]+\.so',name)
                 is not None,'NATIVE_PAYLOAD_NAME')
            body=archive.read(name)
            need(len(body)>=64 and body[:4]==b'\x7fELF' and body[5] in (1,2),
                 'NATIVE_ELF_HEADER_REQUIRED')
            machine=struct.unpack('<H' if body[5]==1 else '>H',body[18:20])[0]
            out[name]={'bytes':len(body),'sha256':sha(body),'elf_class':body[4],
                       'elf_machine':machine}
        # Actual cached original and candidate contain no embedded native namespace.
        # This does not establish absence of JNI or preservation of external native files.
        need(not any(n.startswith('lib/') or n.endswith('.so') for n in names),
             'ACTUAL_EMPTY_APK_NATIVE_NAMESPACE_REQUIRED')
        need(all(v['elf_class']==2 and v['elf_machine']==62 for n,v in out.items()
                 if n.startswith('lib/x86_64/')),'X86_64_ELF_IDENTITY')
        return out

def snapshot(session,expected_sha):
    need(expected_sha in (OLD_SHA,NEW_SHA),'UNREVIEWED_GALLERY_TARGET_HASH')
    session.guard()
    dump=session.android(['/system/bin/dumpsys','package',PACKAGE],15).decode('utf-8','strict')
    parsed=parse_package(dump)
    paths=session.android(['/system/bin/pm','path','--user','0',PACKAGE],12).decode('utf-8','strict').splitlines()
    need(len(paths)==1 and paths[0].startswith('package:'),'SINGLE_GALLERY_APK_PATH_REQUIRED')
    path=paths[0][8:]
    if expected_sha==OLD_SHA:need(path==OLD_PATH,'ORIGINAL_PRODUCT_GALLERY_REQUIRED')
    else:need(re.fullmatch(r'/data/app/~~[^/]+/com\.android\.gallery3d-[^/]+/base\.apk',path)
              is not None,'UPDATED_GALLERY_PATH_REQUIRED')
    code_root=str(Path(path).parent)
    need(parsed['code_and_install_metadata']['codePath']==code_root and
         parsed['code_and_install_metadata']['legacyNativeLibraryDir']==code_root+'/lib',
         'GALLERY_NATIVE_CODE_ROOT_NOT_OWNED')
    apk,apk_meta=session.target.read_file(path,16*1024*1024,single_link=True)
    observed={'path':path,'bytes':len(apk),'sha256':sha(apk),'metadata':apk_meta}
    need(observed['sha256']==expected_sha and len(apk)==(OLD_BYTES if expected_sha==OLD_SHA else NEW_BYTES),
         'INSTALLED_GALLERY_WHOLE_APK_DIFFERS')
    native=native_payload(apk)
    dirs={}
    for label,guest in (('ce','/data/user/0/'+PACKAGE),('de','/data/user_de/0/'+PACKAGE)):
        fd=session.target.open_root(guest,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            info=os.fstat(fd);dirs[label]=fp(info)
            need(stat.S_ISDIR(info.st_mode) and info.st_uid==info.st_gid==10064,
                 'GALLERY_DATA_DIRECTORY_OWNER')
            match=re.search(r'\b'+label+r'DataInode=(\d+)\b',parsed['protected']['user0_state'])
            need(match is not None and int(match[1])==info.st_ino,'GALLERY_DATA_INODE_PM_MISMATCH')
        finally:os.close(fd)
    parsed['protected']['directories']=dirs
    parsed['native_apk_payload']=native
    parsed['apk']=observed
    session.guard()
    return parsed

def require_historical_baseline(value):
    need(value['protected']==EXPECTED,'EXACT_SAVED_GALLERY_BASELINE_REQUIRED')
    return True

def require_preserved(before,after):
    need(before['protected']==after['protected'],'GALLERY_PROTECTED_IDENTITY_CHANGED')
    need(before['native_apk_payload']==after['native_apk_payload'],'NATIVE_APK_PAYLOAD_CHANGED')
    need(after['apk']['sha256']==NEW_SHA and after['apk']['bytes']==NEW_BYTES,'NEW_APK_NOT_READ_BACK')
    return {'all_29_permission_rows_identical':True,'uid_unchanged':True,
            'ce_de_directory_identity_identical':True,'component_overrides_identical':True,
            'user0_state_identical':True,'first_install_time_identical':True,
            'abi_and_all_native_apk_payloads_identical':True,
            'native_loaded_maps_or_business_execution_proved':False,
            'private_app_file_contents_read':False,
            'code_path_and_install_metadata_recorded_separately':True}

def home_snapshot(session,expected):
    raw=session.android(['/system/bin/cmd','activity','stack','list'],12).decode('utf-8','strict')
    roots={};tasks=[]
    for block in re.split(r'(?=^RootTask id=)',raw,flags=re.M):
        if not block.startswith('RootTask id='):continue
        h=re.fullmatch(r'RootTask id=(\d+)\b.*',block.splitlines()[0])
        need(h is not None,'ROOT_TASK_HEADER')
        rid=int(h[1]);need(rid not in roots,'DUPLICATE_ROOT_TASK')
        heads=block.splitlines()[0]
        display=re.search(r'\bdisplayId=(\d+)\b',heads)
        user=re.search(r'\buserId=(\d+)\b',heads)
        need(display and user,'ROOT_TASK_IDENTITY')
        children=[]
        for line in block.splitlines()[1:]:
            if not re.match(r'\s*taskId=',line):continue
            m=re.fullmatch(r'\s*taskId=(\d+):\s+(\S+)\s+.*?\buserId=(\d+)\b.*',line)
            need(m is not None,'UNPARSED_TASK')
            tid=int(m[1]);need(tid not in tasks,'DUPLICATE_TASK')
            tasks.append(tid);children.append({'id':tid,'component':m[2],'user':int(m[3])})
        roots[str(rid)]={'display':int(display[1]),'user':int(user[1]),'children':children}
    need(roots==expected and len(tasks)==1,'ONLY_ROOT_ADOPTED_HOME_TASK_REQUIRED')
    return {'roots':roots,'tasks':tasks,'raw_sha256':sha(raw.encode())}
