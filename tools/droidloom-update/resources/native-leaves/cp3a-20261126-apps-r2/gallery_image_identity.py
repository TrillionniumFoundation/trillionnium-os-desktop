"""Current-image Gallery metadata conservation, without historic data credit."""
import hashlib, re, stat
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


# Observed from the actual 7,390,425-byte official image APK held read-only on
# 2026-11-28. The source receipt records complete SHA/EOF and unchanged F9,
# 944 unique ZIP members, the complete manifest, and no lib/ or .so member.
# A business invocation reuses these static facts only after its normal Reader
# rehashes the same complete original APK. It does not claim a second ZIP parse.
STATIC_SOURCE = {
    'method':'complete-original-sha256-bound-static-source',
    'source_receipt_bytes':1152,
    'source_receipt_sha256':'54cae905689545c67fb7012c6af79863ecc5f5e9ea8d480ed82963974d4ccd8c',
    'apk_bytes':APK_BYTES,'apk_sha256':APK_SHA,
    'manifest_bytes':29248,'manifest_sha256':MANIFEST_SHA,
    'zip_member_count':944,
    'zip_member_names_sha256':'d499e1dc10fd8f261b36a94537a87e85506eb6fc44c450f8f39accb6d982e8a6',
    'native_namespace_members':[],
    'complete_original_sha256_checked_this_case':True,
    'zip_reparsed_this_case':False,
}


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
    channel=session.baseline.live
    actual=channel.original_identity(PACKAGE,APK_SHA,expected_uid,40030)
    need(actual['apk_path']==path and actual['apk_bytes']==APK_BYTES,
         'SAME_COMPLETE_ORIGINAL_GALLERY_APK_REQUIRED')
    owner=channel.apk_custody();ordinal=owner.role(PACKAGE)
    original=owner.value['packages'][ordinal]['originals'][0]
    need(original['apk']['path']==path and original['apk']['bytes']==APK_BYTES
         and original['apk']['sha256']==APK_SHA,'ACTUAL_ORIGINAL_DESCRIPTOR_SOURCE_REQUIRED')
    observed={'path':path,'bytes':APK_BYTES,'sha256':APK_SHA,
              'metadata':original['identity'],'selinux':original['selinux']}
    dirs=actual['directories']
    for label,info in dirs.items():
        need(stat.S_ISDIR(info['st_mode'])
             and (info['st_uid'],info['st_gid'])==session.mapped_owner(expected_uid),
             'GALLERY_DATA_DIRECTORY_OWNER')
        match=re.search(r'\b'+label+r'DataInode=(\d+)\b',parsed['protected']['user0_state'])
        need(match is not None and int(match[1])==info['st_ino'],'GALLERY_DATA_INODE_PM_MISMATCH')
    parsed['protected']['directories']=dirs
    parsed['native_apk_payload']={}
    parsed['native_apk_source_proof']=dict(STATIC_SOURCE)
    parsed['apk']=observed
    session.guard()
    return parsed


