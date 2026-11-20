"""Current-image Gallery metadata conservation, without historic data credit."""
import hashlib, io, os, re, stat, struct, zipfile
from pathlib import Path
PACKAGE = 'com.android.gallery3d'
APK_SHA = '835fe119745324276457b4434fc39f25b633e752c822d2fc9be40eb4b2d45439'
APK_BYTES = 7390425
APK_PATHS = ('/system/product/app/Gallery2/Gallery2.apk', '/product/app/Gallery2/Gallery2.apk')
MANIFEST_SHA = '2d4399372058787b9a9986a797ddc8f2d3722e4cee85a055721da4dc546890ee'
PERMISSION_NAMES = ['android.permission.ACCESS_BACKGROUND_LOCATION', 'android.permission.ACCESS_COARSE_LOCATION', 'android.permission.ACCESS_FINE_LOCATION', 'android.permission.ACCESS_LOCAL_NETWORK', 'android.permission.ACCESS_MEDIA_LOCATION', 'android.permission.ACCESS_NETWORK_STATE', 'android.permission.CAMERA', 'android.permission.GET_ACCOUNTS', 'android.permission.INTERNET', 'android.permission.MANAGE_ACCOUNTS', 'android.permission.NFC', 'android.permission.POST_NOTIFICATIONS', 'android.permission.READ_EXTERNAL_STORAGE', 'android.permission.READ_MEDIA_AUDIO', 'android.permission.READ_MEDIA_IMAGES', 'android.permission.READ_MEDIA_VIDEO', 'android.permission.READ_MEDIA_VISUAL_USER_SELECTED', 'android.permission.READ_SYNC_SETTINGS', 'android.permission.RECEIVE_BOOT_COMPLETED', 'android.permission.RECORD_AUDIO', 'android.permission.SET_WALLPAPER', 'android.permission.USE_CREDENTIALS', 'android.permission.VIBRATE', 'android.permission.WAKE_LOCK', 'android.permission.WRITE_EXTERNAL_STORAGE', 'android.permission.WRITE_SETTINGS', 'android.permission.WRITE_SYNC_SETTINGS', 'com.android.gallery3d.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION', 'com.android.gallery3d.permission.GALLERY_PROVIDER']

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


def parse_package(raw, expected_uid):
    block=active_block(raw)
    def one(pattern):
        found=re.findall(pattern,block,re.M)
        need(len(found)==1,'PACKAGE_FIELD_NOT_UNIQUE:'+pattern)
        return found[0]
    def field(name,indent=4):
        return one('^'+' '*indent+re.escape(name)+r'=(.*)$')
    uid=int(field('appId'))
    version=one(r'^    versionCode=(\d+) minSdk=(\d+) targetSdk=(\d+)$')
    need(type(expected_uid) is int and 0 < expected_uid < 100000 and uid==expected_uid and version==('40030','37','28'),'GALLERY_PACKAGE_IDENTITY_CHANGED')
    userlines=re.findall(r'^    User (\d+): (.*)$',block,re.M)
    need(len(userlines)==1 and userlines[0][0]=='0','EXACT_USER0_ONLY_REQUIRED')
    state=userlines[0][1]
    tokens=state.split()
    need(all(re.fullmatch(r'[A-Za-z][A-Za-z0-9]*=\S+',s) for s in tokens) and
         len(tokens)==len({s.split('=',1)[0] for s in tokens}),'USER_STATE_GRAMMAR')
    user_state=dict(item.split('=',1) for item in tokens)
    need(user_state.get('installed')=='true' and user_state.get('hidden')=='false'
         and user_state.get('suspended')=='false' and user_state.get('enabled')=='0',
         'CURRENT_GALLERY_MUST_BE_INSTALLED_AND_ENABLED')
    permissions=[]
    for line in block.splitlines():
        if ': granted=' not in line:continue
        item=line.strip()
        need(re.fullmatch(r'[A-Za-z][A-Za-z0-9_.]+: granted=(true|false)(?:, flags=\[[A-Z_ |]*\])?',item)
             is not None,'UNPARSED_PERMISSION_ROW')
        permissions.append(item)
    names=[row.split(':',1)[0] for row in permissions]
    need(len(names)==len(set(names))==29,'ALL_29_PERMISSION_ROWS_REQUIRED')
    need(set(names)==set(PERMISSION_NAMES),
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
        # The exact official image member contains no embedded native namespace.
        # This does not establish absence of JNI or preservation of external native files.
        need(not any(n.startswith('lib/') or n.endswith('.so') for n in names),
             'ACTUAL_EMPTY_APK_NATIVE_NAMESPACE_REQUIRED')
        need(all(v['elf_class']==2 and v['elf_machine']==62 for n,v in out.items()
                 if n.startswith('lib/x86_64/')),'X86_64_ELF_IDENTITY')
        return out


def snapshot(session,observation):
    need(observation==session.image_capture.bind(session.view), 'CURRENT_CAPTURE_OBSERVATION_REQUIRED')
    expected_uid=observation['uid']
    session.guard()
    dump=session.android(['/system/bin/dumpsys','package',PACKAGE],15).decode('utf-8','strict')
    parsed=parse_package(dump,expected_uid)
    paths=session.android(['/system/bin/pm','path','--user','0',PACKAGE],12).decode('utf-8','strict').splitlines()
    need(len(paths)==1 and paths[0].startswith('package:'),'SINGLE_GALLERY_APK_PATH_REQUIRED')
    path=paths[0][8:]
    need(path in APK_PATHS and path==observation['apks'][0]['path'], 'CURRENT_ORIGINAL_SYSTEM_GALLERY_PATH_REQUIRED')
    code_root=str(Path(path).parent)
    need(parsed['code_and_install_metadata']['codePath']==code_root and
         parsed['code_and_install_metadata']['legacyNativeLibraryDir']==code_root+'/lib',
         'GALLERY_NATIVE_CODE_ROOT_NOT_OWNED')
    apk,apk_meta=session.target.read_file(path,16*1024*1024,single_link=True)
    observed={'path':path,'bytes':len(apk),'sha256':sha(apk),'metadata':apk_meta}
    need(observed['sha256']==APK_SHA and len(apk)==APK_BYTES,
         'INSTALLED_GALLERY_WHOLE_APK_DIFFERS')
    native=native_payload(apk)
    dirs={}
    for label,guest in (('ce','/data/user/0/'+PACKAGE),('de','/data/user_de/0/'+PACKAGE)):
        fd=session.target.open_root(guest,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            info=os.fstat(fd);dirs[label]=fp(info)
            need(stat.S_ISDIR(info.st_mode) and (info.st_uid,info.st_gid)==session.mapped_owner(expected_uid),
                 'GALLERY_DATA_DIRECTORY_OWNER')
            match=re.search(r'\b'+label+r'DataInode=(\d+)\b',parsed['protected']['user0_state'])
            need(match is not None and int(match[1])==info.st_ino,'GALLERY_DATA_INODE_PM_MISMATCH')
        finally:os.close(fd)
    parsed['protected']['directories']=dirs
    parsed['native_apk_payload']=native
    parsed['apk']=observed
    session.guard()
    return parsed


