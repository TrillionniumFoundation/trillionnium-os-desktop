#!/usr/bin/env python3
"""Read-only CP3A provider APK source verification. No Android execution."""
import os, sys, stat, json, hashlib, time, subprocess, signal, resource, re, zipfile, struct, traceback, datetime, selectors, threading
from pathlib import Path
ROOT=Path('/home/qq/work/p4-cp3a-provider-source-5cd1-20261119-r2')
OUT=ROOT/'work'
APP=Path('/home/qq/work/p4-remaining-app-inputs-20261118-162b-r1')
GSI=Path('/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/official-gsi')
IMAGE=GSI/'images/system.img'
ORIGINAL=APP/'gsi-system-apks-source-20261119-r2/source'
SOURCE_PINS={
 'axml_metadata.py':(13457,'3759ae23233d6909060d591795281e565b447de2ab74e245d244be17a30a8813'),
 'verify_apk.py':(43119,'cd83cd9beb2479ab01c27f5a1422d2ceb2b4703f3e2632b036f3f0fc4633ce20'),
 'verify_apk_set.py':(22828,'2f7f862a368fcf1e53f6618b2de21f082afd18a8b42aa09282b85a7026c7738f')}
TOOLS={
 'debugfs':('/usr/sbin/debugfs',231368,'864e1d7b445e7b5bfc831da78330dbcafc590fa82b89ea9de60b7527f989954f'),
 'aapt2':(str(APP/'sdk37/aapt2'),6274200,'0f1c0e560f99db510a76ebc99ad5c3e68438f62e8e8617018a716ca4a589a699'),
 'apksigner':(str(APP/'sdk37/lib/apksigner.jar'),1181416,'2defad215d7ff52968a409cde528cdaef7918b115e276b8e3378ca7a178e4180'),
 'java':('/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/work/aosp-source/prebuilts/jdk/jdk21/linux-x86/bin/java',8528,'cfa21aeadd00925925c9e1287f5c08f3e04ee7f26a9e23d9dbfb16149153d842')}
EXPECTED=[
 ('com.android.providers.calendar','/system/priv-app/CalendarProvider/CalendarProvider.apk',3208,336615),
 ('com.android.providers.contacts','/system/priv-app/ContactsProvider/ContactsProvider.apk',3232,942497),
 ('com.android.externalstorage','/system/priv-app/ExternalStorageProvider/ExternalStorageProvider.apk',3291,57567)]
MEDIA='com.android.providers.media.module'
IMAGE_BYTES=2294853632
IMAGE_SHA='dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4'
CAPEX_PATH='/system/apex/com.android.mediaprovider.capex'
CAPEX_BYTES=17256448
CAPEX_SHA='a15084a3dcf7eca1fa0344625226b4600c3020cce3bdda9749bcb77d76c7ad95'
CAPEX_INODE=71
LIMIT=256*1024*1024
DEADLINE=None
BOOKENDS=[]
COMMANDS=[]
APP_RESULTS=[]
R={'schema':'pocket4-cp3a-four-provider-source-run-v1','success':False,'source_identity_verified':False,
   'installed':False,'runtime_qualified':False,'business_qualified':False,'production_ready':False,
   'semantic_cleanup_qualified':False,'individual_provider_install_authorized':False,
   'Android_starts':0,'Android_actions':0,'new_downloads':0,'C_or_Rust_compilations':0,
   'privileged_mounts':0,'image_written':False,'user_data_reads':0,
   'commands':COMMANDS,'providers':APP_RESULTS}


def need(v,msg):
 if not v: raise ValueError(msg)

def f9(s):
 return [str(v) for v in (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)]

def fdsha(fd):
 h=hashlib.sha256(); pos=0
 while True:
  b=os.pread(fd,1024*1024,pos)
  if not b: break
  h.update(b);pos+=len(b)
 return h.hexdigest()

def held(path,expected=None,limit=4*1024*1024*1024,allow_root=False):
 path=Path(path)
 fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
 try:
  s=os.fstat(fd); old=f9(s)
  need(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and 0<s.st_size<=limit,'regular single-link file bound: '+str(path))
  need(s.st_uid in ({0,os.getuid()} if allow_root else {os.getuid()}),'input owner: '+str(path))
  sha=fdsha(fd)
  if expected is not None: need((s.st_size,sha)==expected,'pin mismatch: '+str(path))
  need(f9(os.fstat(fd))==old and f9(os.stat(path,follow_symlinks=False))==old,'input changed while hashing')
  pin={'path':str(path),'bytes':s.st_size,'sha256':sha,'identity':old}
  BOOKENDS.append((path,fd,dict(pin)))
  return fd,pin
 except BaseException:
  os.close(fd);raise

def save(path,data):
 if not isinstance(data,bytes): data=(json.dumps(data,sort_keys=True,indent=2)+'\n').encode('ascii')
 need(len(data)<=16*1024*1024,'evidence size bound')
 space(len(data),final=Path(path).name=='RESULT.json')
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
 try:
  view=memoryview(data)
  while view: n=os.write(fd,view);need(n>0,'short evidence write');view=view[n:]
  os.fsync(fd)
 finally: os.close(fd)
 os.chmod(path,0o444,follow_symlinks=False)
 return {'path':str(path),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}

def verify_identity(expected,raw,badging,manifest_output,signature,block,selected):
 attrs=dict(re.findall(r"(\w+)='([^']*)'",next((line for line in badging.splitlines() if line.startswith('package:')),'')))
 need(attrs.get('name')==expected and raw['package']==expected,'expected package differs')
 match=re.search(r'\bA: package="([^"]+)"',manifest_output)
 need(match is not None and match.group(1)==expected,'SDK XML package differs')
 need(attrs.get('versionCode','').isdigit(),'missing numeric SDK version')
 need(int(attrs['versionCode'])==raw['version_code'] and int(attrs.get('versionCodeMajor','0'))==raw['version_code_major'],'AXML/SDK version mismatch')
 need((attrs.get('split') or None)==raw['split_name'],'AXML/SDK split mismatch')
 need(raw['split_name'] is None and not raw['is_feature_split'] and not raw['is_split_required']
      and raw['uses_split'] is None and raw['config_for_split'] is None
      and not raw['required_split_types'] and not raw['split_types'],'incomplete split APK')
 certs=single.application_signer_certificates(signature)
 need(bool(certs) and certs==selected['certificate_sha256'],'SDK/signed-block cert mismatch')
 need(all(re.fullmatch('[0-9a-f]{64}',x) for x in certs),'invalid certificate')
 for key,label in [('min_sdk_version','minSdkVersion'),('target_sdk_version','targetSdkVersion')]:
  value=raw.get(key)
  if value is not None:
   match=re.search(r"^"+label+r":'([^']+)'$",badging,re.M)
   need(match is not None and match.group(1)==value,'SDK/AXML SDK bound mismatch')
 return attrs,certs

def native_header(name,header):
 parts=name.split('/')
 need(len(parts)==3 and parts[2].endswith('.so') and parts[1] in single._ABI_ELF,'native path ABI unsupported')
 cls,machine=single._ABI_ELF[parts[1]]
 need(len(header)>=64 and header[:4]==b'\x7fELF','native ELF header missing')
 need(header[4]==cls and header[5]==1 and header[6]==1,'native ELF class/encoding/version')
 actual=struct.unpack_from('<H',header,18)[0]
 need(actual==machine,'native ELF machine mismatches directory ABI')
 need(struct.unpack_from('<H',header,16)[0] in (2,3),'native ELF type')
 return {'abi':parts[1],'elf_class':cls,'elf_machine':actual}

def space(max_growth,final=False):
    total=OUT.stat().st_blocks*512
    for root,dirs,files in os.walk(OUT,followlinks=False):
        for name in dirs:
            need(not os.path.islink(Path(root)/name),'output symlink directory')
            total+=os.stat(Path(root)/name,follow_symlinks=False).st_blocks*512
        for name in files:
            s=os.stat(Path(root)/name,follow_symlinks=False)
            need(stat.S_ISREG(s.st_mode) and s.st_nlink==1,'output file type')
            total+=s.st_blocks*512
    reserve=0 if final else 16*1024*1024
    need(total+((max_growth+4095)//4096)*4096+65536+reserve<=LIMIT,'output allocated reservation bound 256MiB')
    return total

def budget():
    need(DEADLINE is not None and time.monotonic()<DEADLINE,'overall deadline')
    v=os.statvfs(OUT)
    need(v.f_bavail*v.f_frsize>=24*1024**3,'host disk floor 24GiB')
    return space(0)

def verify_process_observation_preconditions():
    need(signal.getsignal(signal.SIGCHLD)==signal.SIG_DFL,'default SIGCHLD required')
    need(threading.get_native_id()==os.getpid(),'main thread required')
    need(os.listdir('/proc/self/task')==[str(os.getpid())],'single-threaded parent required')

def run(name,argv,pass_fds=(),timeout=120,output_bytes=0):
    budget()
    verify_process_observation_preconditions()
    max_log=8*1024*1024
    space(2*max_log+output_bytes)
    need(re.fullmatch(r'[A-Za-z0-9_.-]+',name),'command label')
    op=OUT/'logs'/(name+'.stdout');ep=OUT/'logs'/(name+'.stderr')
    of=os.open(op,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC,0o600)
    ef=os.open(ep,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC,0o600)
    row={'name':name,'argv':argv,'started_ns':time.time_ns(),
         'original_pidfd_held_until_reaped':False,'actual_child_reaped':False}
    COMMANDS.append(row);p=None;pidfd=None
    selector=selectors.DefaultSelector()
    sizes={'stdout':0,'stderr':0};handles={'stdout':of,'stderr':ef}
    stopped_at=None
    started=time.monotonic()
    try:
        env={'PATH':'/usr/bin:/usr/sbin:/bin','LC_ALL':'C',
             'PYTHONDONTWRITEBYTECODE':'1','TMPDIR':str(OUT/'tmp'),
             'LD_LIBRARY_PATH':str(APP/'sdk37/lib64')}
        def child_limits():
            cap=output_bytes if output_bytes else max_log
            resource.setrlimit(resource.RLIMIT_FSIZE,(cap,cap))
        p=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           pass_fds=pass_fds,env=env,start_new_session=True,preexec_fn=child_limits)
        row['pid']=p.pid;pidfd=os.pidfd_open(p.pid,0)
        row['original_pidfd_held_until_reaped']=True
        for stream,key in [(p.stdout,'stdout'),(p.stderr,'stderr')]:
            os.set_blocking(stream.fileno(),False)
            selector.register(stream,selectors.EVENT_READ,key)
        def child_terminal():
            return os.waitid(os.P_PIDFD,pidfd,os.WEXITED|os.WNOHANG|os.WNOWAIT) is not None
        def stop(reason):
            nonlocal stopped_at
            if stopped_at is None:
                stopped_at=time.monotonic();row['termination']=reason
                try: signal.pidfd_send_signal(pidfd,signal.SIGKILL)
                except ProcessLookupError: pass
        while selector.get_map() or not child_terminal():
            now=time.monotonic()
            if now-started>timeout or now>=DEADLINE: stop('command_deadline')
            for key,_ in selector.select(0.1):
                block=os.read(key.fileobj.fileno(),65536)
                if not block:
                    selector.unregister(key.fileobj);key.fileobj.close();continue
                namekey=key.data
                remaining=max_log-sizes[namekey]
                if len(block)>remaining:
                    block=block[:remaining];stop('log_byte_bound')
                view=memoryview(block)
                while view:
                    n=os.write(handles[namekey],view);need(n>0,'log short write');view=view[n:]
                sizes[namekey]+=len(block)
            if stopped_at is not None and time.monotonic()-stopped_at>5:
                row['output_complete']=False;break
        row.setdefault('output_complete',True)
        rc=p.wait(timeout=5)
        row['exit']=rc;row['actual_child_reaped']=True
        try:
            os.waitid(os.P_PIDFD,pidfd,os.WEXITED|os.WNOHANG)
            row['after_reap_echild']=False
        except ChildProcessError:
            row['after_reap_echild']=True
    finally:
        if p is not None and p.poll() is None:
            if pidfd is not None: signal.pidfd_send_signal(pidfd,signal.SIGKILL)
            else: p.kill()
            p.wait(timeout=5);row['actual_child_reaped']=True
        if pidfd is not None: os.close(pidfd)
        for key in list(selector.get_map().values()): key.fileobj.close()
        selector.close()
        os.fsync(of);os.fsync(ef);os.close(of);os.close(ef)
    row['ended_ns']=time.time_ns()
    data=[]
    for path,key in [(op,'stdout'),(ep,'stderr')]:
        need(path.stat().st_size<=8*1024*1024,'command output bound')
        b=path.read_bytes();row[key]={'path':str(path),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
        data.append(b.decode('utf-8'))
    need(row.get('exit')==0 and not row.get('termination') and row.get('output_complete'),'command failed: '+name)
    return data[0],data[1],row

def list_image(label,image_fd,directory):
    need(directory.startswith('/') and '..' not in directory.split('/'),'image directory')
    text,err,cmd=run(label,[TOOLS['debugfs'][0],'-R','ls -p '+directory,
                    f'/proc/self/fd/{image_fd}'],(image_fd,),30)
    rows=[]
    for line in text.splitlines():
        if not line: continue
        parts=line.split('/')
        need(len(parts)==8 and parts[0]==parts[-1]=='','debugfs directory record')
        ino,mode,uid,gid,name,size=parts[1:-1]
        need(ino.isdigit() and re.fullmatch('[0-7]{6}',mode),'debugfs inode/mode')
        need(name not in ('','/') and '\\' not in name,'debugfs basename')
        rows.append({'inode':int(ino),'mode':int(mode,8),'uid':int(uid),'gid':int(gid),
                     'name':name,'bytes':int(size) if size else None})
    need(rows,'nonempty image directory required')
    return rows,cmd

def dump_image(label,image_fd,path,out,expected_inode,expected_size,expected_sha=None,expected_uid=0,expected_gid=0):
    need(re.fullmatch(r'/[A-Za-z0-9_./@-]+',path) and '..' not in path.split('/'),'fixed image file path')
    rows,ls= list_image(label+'-ls',image_fd,str(Path(path).parent))
    matching=[r for r in rows if r['name']==Path(path).name]
    need(len(matching)==1,'exact image member')
    row=matching[0]
    need(row=={'inode':expected_inode,'mode':0o100644,'uid':expected_uid,'gid':expected_gid,
               'name':Path(path).name,'bytes':expected_size},'image member changed')
    fd=os.open(out,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
    try:
        identity=(os.fstat(fd).st_dev,os.fstat(fd).st_ino)
        _,_,cmd=run(label+'-dump',[TOOLS['debugfs'][0],'-R',
            f'dump {path} /proc/self/fd/{fd}',f'/proc/self/fd/{image_fd}'],(image_fd,fd),60,output_bytes=expected_size)
        s=os.fstat(fd)
        need((s.st_dev,s.st_ino)==identity and s.st_size==expected_size,'extraction output identity')
        os.fsync(fd)
    finally: os.close(fd)
    os.chmod(out,0o444,follow_symlinks=False)
    fd,pin=held(out,(expected_size,expected_sha) if expected_sha else None,128*1024*1024)
    return fd,pin,[ls,cmd]

def zip_member(parent_fd,parent_pin,target,out,label):
    members=[];chosen=None
    with os.fdopen(os.dup(parent_fd),'rb') as stream,zipfile.ZipFile(stream) as archive:
        entries=safe_members(archive,count_limit=1000,expansion_limit=128*1024*1024)
        need(target in entries and not entries[target].is_dir(),'required exact archive member')
        need(entries[target].file_size<=128*1024*1024,'selected archive member size')
        space(entries[target].file_size)
        of=os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
        try:
            for item in archive.infolist():
                h=hashlib.sha256();size=0
                with archive.open(item) as source:
                    while True:
                        b=source.read(1024*1024)
                        if not b: break
                        h.update(b);size+=len(b)
                        need(size<=item.file_size,'archive member expansion bound')
                        if item.filename==target:
                            view=memoryview(b)
                            while view:
                                n=os.write(of,view);need(n>0,'archive extraction short write');view=view[n:]
                need(size==item.file_size,'archive member EOF')
                rec={'name':item.filename,'bytes':size,'sha256':h.hexdigest(),
                     'crc32':f'{item.CRC:08x}','compressed_bytes':item.compress_size,
                     'compression':item.compress_type,'complete_eof_crc_verified':True}
                members.append(rec)
                if item.filename==target: chosen=rec
            os.fsync(of)
        finally: os.close(of)
    os.chmod(out,0o444,follow_symlinks=False)
    fd,pin=held(out,(chosen['bytes'],chosen['sha256']),128*1024*1024)
    evidence={'schema':'pocket4-cp3a-exact-archive-member-chain-v1','parent':parent_pin,
              'selected_member':chosen,'extracted':pin,'complete_members':members,
              'container_signature_or_AVB_qualified':False,'runtime_qualified':False}
    proof=save(OUT/'evidence'/(label+'.json'),evidence)
    budget()
    return fd,pin,proof

def verify_apk_source(package,apk_fd,apk_pin,path,image_pin,chain,extraction_commands):
    prefix=package
    apkarg=f'/proc/self/fd/{apk_fd}'
    members=[];native=[];manifest_bytes=None
    with os.fdopen(os.dup(apk_fd),'rb') as stream,zipfile.ZipFile(stream) as archive:
        entries=safe_members(archive,count_limit=100000,expansion_limit=512*1024*1024)
        need('AndroidManifest.xml' in entries,'manifest missing')
        for item in archive.infolist():
            h=hashlib.sha256();size=0;header=b'';parts=[] if item.filename=='AndroidManifest.xml' else None
            with archive.open(item) as source:
                while True:
                    b=source.read(1024*1024)
                    if not b: break
                    h.update(b);size+=len(b)
                    if len(header)<64: header=(header+b)[:64]
                    if parts is not None:
                        need(size<=1024*1024,'manifest bound');parts.append(b)
            need(size==item.file_size,'APK member EOF')
            rec={'name':item.filename,'bytes':size,'sha256':h.hexdigest(),
                 'crc32':f'{item.CRC:08x}','compressed_bytes':item.compress_size,
                 'compression':item.compress_type,'directory':item.is_dir(),
                 'complete_eof_crc_verified':True}
            members.append(rec)
            if parts is not None: manifest_bytes=b''.join(parts)
            if not item.is_dir() and item.filename.startswith('lib/'):
                native.append({**rec,**native_header(item.filename,header),'execution_qualified':False})
    raw=manifest_observation(manifest_bytes)
    block=signing_block_certificates(apkarg)
    badging,be,bc=run(prefix+'-badging',[TOOLS['aapt2'][0],'dump','badging',apkarg],(apk_fd,),60)
    manifest,me,mc=run(prefix+'-manifest',[TOOLS['aapt2'][0],'dump','xmltree',apkarg,
                         '--file','AndroidManifest.xml'],(apk_fd,),60)
    java=[TOOLS['java'][0],'-XX:ActiveProcessorCount=1','-Xmx128m','-XX:+UseSerialGC',
          '-XX:CompressedClassSpaceSize=32m','-XX:ReservedCodeCacheSize=32m',
          '-XX:MaxMetaspaceSize=64m','-Xss256k','-Duser.home='+str(OUT/'home'),
          '-Djava.io.tmpdir='+str(OUT/'tmp'),'-jar',TOOLS['apksigner'][0],
          'verify','--min-sdk-version','37','--max-sdk-version','37',
          '--verbose','--print-certs',apkarg]
    signature,se,sc=run(prefix+'-signature',java,(apk_fd,),120)
    selected=verified_scheme_certificates(signature+se,block)
    attrs,certs=verify_identity(package,raw,badging,manifest,signature+se,block,selected)
    if not APP_RESULTS:
        controls=[]
        def rejected(name,fn):
            try: fn()
            except (ValueError,KeyError) as ex:
                controls.append({'name':name,'rejected':True,'reason':str(ex)})
            else: raise ValueError('source negative accepted: '+name)
        rejected('different-scope-package',lambda:verify_identity('com.invalid.other',raw,badging,manifest,signature+se,block,selected))
        changed=dict(raw);changed['version_code']+=1
        rejected('different-AXML-version',lambda:verify_identity(package,changed,badging,manifest,signature+se,block,selected))
        rejected('different-signer',lambda:verify_identity(package,raw,badging,manifest,signature+se,block,{'certificate_sha256':['0'*64]}))
        altered=dict(raw);altered['is_split_required']=True
        rejected('incomplete-required-split',lambda:verify_identity(package,altered,badging,manifest,signature+se,block,selected))
        malformed=dict(raw);malformed['min_sdk_version']='999'
        rejected('different-min-SDK',lambda:verify_identity(package,malformed,badging,manifest,signature+se,block,selected))
        elf=bytearray(64);elf[:7]=b'\x7fELF\x02\x01\x01';struct.pack_into('<HH',elf,16,3,183)
        rejected('wrong-native-ELF-machine',lambda:native_header('lib/x86_64/libwrong.so',bytes(elf)))
        R['actual_evidence_negative_controls']=controls
    need(fdsha(apk_fd)==apk_pin['sha256'] and f9(os.fstat(apk_fd))==apk_pin['identity'],'APK changed during verification')
    receipt={'schema':'pocket4-verified-cp3a-provider-apk-source-v1',
             'observed_ns':time.time_ns(),'package':package,'apk':apk_pin,
             'version_code':raw['version_code'],'version_code_major':raw['version_code_major'],
             'version_name_axml':raw['version_name'],'version_name':attrs.get('versionName'),
             'original_image_path':path,'full_system_image':image_pin,
             'container_chain':chain,'GSI_manifest':R['GSI_manifest'],
             'SDK_preparation':R['SDK_preparation'],'signer_certificate_sha256':certs,
             'selected_signing_scheme':selected,'signature_verified_for_api':37,
             'public_signing_block':block,'manifest':raw,'native_members':native,
             'complete_zip_members':members,'commands':extraction_commands+[bc,mc,sc],
             'tool_pins':R['tool_pins'],'original_parser_source_pins':R['parser_pins'],
             'source_identity_verified':True,'full_CRC_and_SHA_verified':True,
             'signer_reference_kind':'certificate in APK extracted through the fully SHA-pinned official GSI chain',
             'install_mode':'coherent_full_GSI_only','individual_APK_install_authorized':False,
             'actual_UID':None,'framework_epoch':None,'installed':False,
             'semantic_cleanup_qualified':False,'native_compatibility_qualified':False,
             'runtime_qualified':False,'business_qualified':False,'production_ready':False}
    proof=save(OUT/'receipts'/(package+'.json'),receipt)
    row={'package':package,'version_code':raw['version_code'],'version_name':attrs.get('versionName'),
         'apk':apk_pin,'image_path':path,'signer_certificate_sha256':certs,'source_receipt':proof,
         'native_ABIs':sorted({n['abi'] for n in native}),'zip_members':len(members),
         'source_identity_verified':True,'actual_UID':None,'runtime_qualified':False,
         'semantic_cleanup_qualified':False,'business_qualified':False,'production_ready':False}
    APP_RESULTS.append(row)
    print(json.dumps({'provider_source_verified':package,'bytes':apk_pin['bytes'],
                      'sha256':apk_pin['sha256'],'signer':certs}),flush=True)
    budget()

def main():
    global DEADLINE,single,safe_members,manifest_observation,signing_block_certificates,verified_scheme_certificates
    need(os.getuid()==1000,'ordinary uid1000 required')
    verify_process_observation_preconditions()
    need(Path(__file__).resolve()==ROOT/'verify_providers.py','reviewed worker location')
    need(not OUT.exists(),'one-shot output already exists')
    OUT.mkdir(mode=0o700)
    for name in ('source','evidence','logs','apks','containers','receipts','tmp','home'):
        (OUT/name).mkdir(mode=0o700)
    R['started_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    DEADLINE=time.monotonic()+540
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_FSIZE,(128*1024*1024,128*1024*1024))
    need(sorted(os.sched_getaffinity(0))==[31],'actual CPU31 affinity required')
    cg=[l.split(':',2)[2] for l in Path('/proc/self/cgroup').read_text().splitlines() if l.startswith('0::')]
    need(len(cg)==1,'unified cgroup')
    cgp=Path('/sys/fs/cgroup')/cg[0].lstrip('/')
    limits={n:(cgp/n).read_text().strip() for n in ('memory.max','memory.high','memory.swap.max','cpu.max','pids.max')}
    need(limits=={'memory.max':'805306368','memory.high':'671088640','memory.swap.max':'0',
                  'cpu.max':'100000 100000','pids.max':'64'},'actual resource bounds')
    events_before=(cgp/'memory.events').read_text()
    R['resource_limits']={'observed':limits,'affinity':[31],'cgroup':str(cgp),
                          'output_max_allocated_bytes':LIMIT,'deadline_seconds':540}
    R['memory_events_before']=events_before
    self_fd,R['worker_source']=held(Path(__file__),limit=65536)
    save(OUT/'source/verify_providers.py',os.pread(self_fd,R['worker_source']['bytes'],0))
    parser={}
    for name,expected in SOURCE_PINS.items():
        fd,pin=held(ORIGINAL/name,expected,65536)
        save(OUT/'source'/name,os.pread(fd,expected[0],0));parser[name]=pin
    R['parser_pins']=parser
    sys.path.insert(0,str(OUT/'source'))
    import verify_apk as single
    from verify_apk_set import safe_members,manifest_observation
    from axml_metadata import signing_block_certificates,verified_scheme_certificates
    R['tool_pins']={name:held(path,(size,sha),8*1024*1024,True)[1] for name,(path,size,sha) in TOOLS.items()}
    mf,mp=held(GSI/'official-gsi-manifest.json',(12184,'8dff52f9abc8bd219266e1e85ba8cd3063677443aafc3efd90c4df9c8f04bfde'),16384)
    mb=os.pread(mf,mp['bytes'],0);manifest=json.loads(mb)
    save(OUT/'evidence/official-gsi-manifest.json',mb);R['GSI_manifest']=mp
    profile=manifest['profile'];R['build_identity']=profile['build_identity']
    need(profile['build_identity']['id']=='CP3A.260905.010' and profile['build_identity']['sdk']==37,'coherent GSI build')
    members=profile['archive_members']
    need(len([m for m in members if m['name']=='system.img' and m['bytes']==IMAGE_BYTES and m['sha256']==IMAGE_SHA])==1,'manifest system chain')
    need([x for x in profile['apex_containers'] if x['path']==CAPEX_PATH]==
         [{'path':CAPEX_PATH,'bytes':CAPEX_BYTES,'sha256':CAPEX_SHA}],'manifest CAPEX chain')
    sf,sp=held(APP/'metadata/sdk37-preparation-receipt.json',(7636,'c9b2003dfeec0d0dc72263ff63723f9b4fe5f77ca4ad0b6ac77224ca80a78bb5'),16384)
    sb=os.pread(sf,sp['bytes'],0);sdk=json.loads(sb)
    save(OUT/'evidence/sdk37-preparation-receipt.json',sb);R['SDK_preparation']=sp
    need(sdk['ready'] and sdk['archive']['official_sha1_matched'],'SDK preparation unqualified')
    R['SDK_full_tool_bookends']=[]
    for pin in sdk['extracted']+[sdk['java'],sdk['jdk_release']]:
        R['SDK_full_tool_bookends'].append(held(pin['path'],(pin['bytes'],pin['sha256']),8*1024*1024)[1])
    image_fd,image_pin=held(IMAGE,(IMAGE_BYTES,IMAGE_SHA))
    need(os.pread(image_fd,2,1080)==b'\x53\xef','source ext4 required')
    R['full_system_image']=image_pin
    for package,path,inode,size in EXPECTED:
        fd,pin,cmds=dump_image(package,image_fd,path,OUT/'apks'/(package+'.apk'),inode,size)
        verify_apk_source(package,fd,pin,path,image_pin,[],cmds)
    capfd,cappin,capcmds=dump_image('mediaprovider-capex',image_fd,CAPEX_PATH,
        OUT/'containers/com.android.mediaprovider.capex',CAPEX_INODE,CAPEX_BYTES,CAPEX_SHA)
    apexfd,apexpin,capchain=zip_member(capfd,cappin,'original_apex',OUT/'containers/original.apex','CAPEX-MEMBER-CHAIN')
    payloadfd,payloadpin,apexchain=zip_member(apexfd,apexpin,'apex_payload.img',
        OUT/'containers/apex_payload.img','APEX-PAYLOAD-CHAIN')
    need((apexpin['bytes'],apexpin['sha256'])==(38428672,'a7a5eae92c563e9b26c552de818af4cecda768213a3c57895d5a76cdd56b4670'),'current MediaProvider original APEX identity')
    need((payloadpin['bytes'],payloadpin['sha256'])==(38154240,'a1018f008013e8363534e4effc2d70d36ac471af18bccea205dad1bf3ab6ef23'),'current MediaProvider inner payload identity')
    need(os.pread(payloadfd,2,1080)==b'\x53\xef','current media payload requires ext4')
    rows,dircmd=list_image('mediaprovider-apex-privapp',payloadfd,'/priv-app')
    dirs=[r for r in rows if r['name'] not in ('.','..')]
    selected=[r for r in dirs if r['name'].startswith('MediaProvider@')]
    need(len(selected)==1 and selected[0]['mode']==0o40755,'single original MediaProvider directory')
    need(selected[0]['name']=='MediaProvider@CP3A.260905.010','current MediaProvider build-specific path')
    image_path='/priv-app/'+selected[0]['name']+'/MediaProvider.apk'
    leaves,leafcmd=list_image('mediaprovider-apex-apkdir',payloadfd,str(Path(image_path).parent))
    matches=[r for r in leaves if r['name']=='MediaProvider.apk']
    need(len(matches)==1 and matches[0]['mode']==0o100644 and 0<matches[0]['bytes']<64*1024*1024,'one current provider APK')
    leaf=matches[0]
    need(leaf=={'inode':51,'mode':0o100644,'uid':1000,'gid':1000,'name':'MediaProvider.apk','bytes':13826854},'current exact MediaProvider leaf record')
    mediafd,mediapin,mediacmds=dump_image('mediaprovider-apk',payloadfd,image_path,
        OUT/'apks'/(MEDIA+'.apk'),leaf['inode'],leaf['bytes'],expected_uid=1000,expected_gid=1000)
    R['media_source_chain']={'capex':cappin,'original_apex':apexpin,'payload':payloadpin,
                            'capex_member_proof':capchain,'apex_payload_proof':apexchain,
                            'image_member_path':image_path,'container_signature_or_AVB_qualified':False}
    verify_apk_source(MEDIA,mediafd,mediapin,'/apex/com.android.mediaprovider'+image_path,
        image_pin,R['media_source_chain'],capcmds+[dircmd,leafcmd]+mediacmds)
    need({x['package'] for x in APP_RESULTS}=={x[0] for x in EXPECTED}|{MEDIA},'exact four provider set')
    need(len(R['actual_evidence_negative_controls'])==6,'all actual source negatives')
    R['bookends']=[]
    for path,fd,pin in BOOKENDS:
        need(f9(os.fstat(fd))==pin['identity'] and f9(os.stat(path,follow_symlinks=False))==pin['identity'],'input identity changed: '+str(path))
        need(fdsha(fd)==pin['sha256'],'input content changed: '+str(path))
        R['bookends'].append({'path':str(path),'bytes':pin['bytes'],'sha256':pin['sha256'],'F9_and_SHA_equal':True})
    need(all(c.get('exit')==0 and c['actual_child_reaped'] and c.get('after_reap_echild') and
             c['original_pidfd_held_until_reaped'] for c in COMMANDS),'original child retirement')
    children=Path('/proc/self/task/'+str(os.getpid())+'/children').read_text().strip()
    need(children=='','remaining child process')
    R['remaining_children']=children
    events_after=(cgp/'memory.events').read_text();R['memory_events_after']=events_after
    before=dict(x.split() for x in events_before.splitlines());after=dict(x.split() for x in events_after.splitlines())
    need(all(int(after[x])==int(before[x]) for x in ('oom','oom_kill','oom_group_kill')),'cgroup OOM changed')
    R['actual_output_allocated_bytes_before_RESULT']=budget()
    R['source_APK_pass_count']=4
    R['total_APK_bytes']=sum(x['apk']['bytes'] for x in APP_RESULTS)
    R['source_identity_verified']=True;R['success']=True

if __name__=='__main__':
    try:
        main()
    except BaseException as error:
        R['error']=repr(error);R['traceback']=traceback.format_exc()
    finally:
        R['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        if OUT.exists():
            try:
                result=save(OUT/'RESULT.json',R)
                print(json.dumps({'success':R['success'],'providers_completed':len(APP_RESULTS),
                                  'result':result,'runtime_qualified':False,'production_ready':False}),flush=True)
            except BaseException: traceback.print_exc()
        for path,fd,pin in BOOKENDS:
            try: os.close(fd)
            except OSError: pass
    sys.exit(0 if R['success'] else 1)
