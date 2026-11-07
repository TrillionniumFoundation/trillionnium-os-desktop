#!/usr/bin/python3 -I
"""Read Clock's declared shared-library closure and existing ART metadata only."""
from pathlib import Path
import argparse, contextlib, datetime, gzip, hashlib, io, json, os, re, resource
import time, types, xml.etree.ElementTree as ET, zipfile

ROOT=Path('/home/alex/work/pocket4-clock-art-context-20261105-r12-04')
STORAGE=Path('/home/alex/work/pocket4-storage-session-candidate-20261105-r12')
TX=Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
TX_SHA='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
ACTIVATION_SHA='7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
ART_SHA='e5de57780be072ced10a5beba049fe89e89e381d6a66a974a8f298ef34cf2742'
DISCOVERY_SHA='614f0c61ec4956a626edb06950bb6b7494ed856dc1dc2c45ac8bfd748421bab9'
PACKAGE='com.android.deskclock'
APK='/data/app/~~IbaHjOhSap41lASiYb4RDQ==/com.android.deskclock-WSxg1z5KSAFk5lJv8t51zw==/base.apk'
APK_SHA='e4ff4b46a651ff3ac77397705b7b749c7fbaaeb94fe1d00818debb31dea34172'
LIBRARIES=['androidx.window.extensions','androidx.window.sidecar']
LIBRARY_FILES=['/system_ext/framework/'+n+'.jar' for n in LIBRARIES]
UNIT='p4-clock-art-context-20261105-r12-04.service'

def need(value, reason):
    if not value: raise RuntimeError(reason)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def stamp(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def load(path, pin, name):
    raw=path.read_bytes(); need(sha(raw)==pin,'SOURCE_CHANGED:'+name)
    m=types.ModuleType(name); m.__file__=str(path); exec(compile(raw,str(path),'exec'),m.__dict__); return m

def limits():
    line=Path('/proc/self/cgroup').read_text().strip()
    need(line=='0::/system.slice/'+UNIT,'WRONG_OWN_UNIT')
    cg=Path('/sys/fs/cgroup')/line[3:].lstrip('/')
    values={n:(cg/n).read_text().strip() for n in ('cpu.max','memory.max','memory.swap.max','pids.max')}
    q,p=map(int,values['cpu.max'].split())
    need(q==p and values['memory.max']=='536870912' and values['memory.swap.max']=='0'
         and values['pids.max']=='48' and os.sched_getaffinity(0)=={20},'OWN_LIMITS_CHANGED')
    need(resource.getrlimit(resource.RLIMIT_CORE)==(0,0),'CORE_NOT_DISABLED')
    events={k:int(v) for k,v in (x.split() for x in (cg/'memory.events').read_text().splitlines())}
    need(events.get('max',0)==events.get('oom',0)==events.get('oom_kill',0)==0,'MEMORY_LIMIT_HIT')
    return {'limits':values,'memory_peak_bytes':int((cg/'memory.peak').read_text()),'memory_events':events}

def names(s,path):
    fd=s.target.open_root(path,os.O_RDONLY|os.O_DIRECTORY)
    try: value=sorted(os.listdir(fd))
    finally: os.close(fd)
    need(len(value)<=256 and all(re.fullmatch(r'[A-Za-z0-9_.+-]+',n) for n in value),'DIRECTORY_NOT_BOUNDED')
    return value

def package(s,tx,label):
    paths=s.android(['/system/bin/pm','path',PACKAGE],12).decode('utf-8','strict').splitlines()
    need(paths==['package:'+APK],'CLOCK_PATH_CHANGED')
    raw=s.android(['/system/bin/dumpsys','package',PACKAGE],12)
    need(len(raw)<=256*1024,'PACKAGE_DUMP_TOO_LARGE')
    tx.write_new(ROOT/(label+'-package.txt'),raw,alex_readable=False)
    text=raw.decode('utf-8','strict')
    blocks=re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)',text,re.M|re.S)
    need(len(blocks)==1,'PACKAGE_BLOCK_REQUIRED'); text=blocks[0]
    need(re.findall(r'^    appId=(\d+)$',text,re.M)==['10063']
         and re.findall(r'^    versionCode=(\d+)\b',text,re.M)==['37'],'CLOCK_ID_CHANGED')
    def rows(key):
        found=re.findall(r'^    '+key+r':\n((?:^      \S.*\n)+)',text,re.M)
        need(len(found)<=1,'DUPLICATE_PACKAGE_SECTION:'+key)
        return [x.strip() for x in found[0].splitlines()] if found else []
    result={key:rows(key) for key in ('usesLibraries','usesOptionalLibraries','usesLibraryFiles','usesStaticLibraries')}
    need(result=={'usesLibraries':[],'usesOptionalLibraries':LIBRARIES,
                  'usesLibraryFiles':LIBRARY_FILES,'usesStaticLibraries':[]},'DECLARED_LIBRARY_CLOSURE_CHANGED')
    need(re.findall(r'^    splits=(.*)$',text,re.M)==['[base]'],'CLOCK_SPLITS_CHANGED')
    return {'uid':10063,'version_code':37,'apk_path':APK,**result}

def xml_config(s,art,peer):
    root='/system_ext/etc/permissions'; directory=names(s,root)
    files=[n for n in directory if 'window' in n and n.endswith('.xml')]
    need(0<len(files)<=8,'WINDOW_LIBRARY_CONFIG_COUNT')
    result={}; declarations={}
    for name in files:
        path=root+'/'+name; raw,meta=s.target.read_file(path,128*1024)
        pin=art.pin_guest(s,peer,path); need(pin['sha256']==sha(raw),'XML_READ_CHANGED')
        tree=ET.fromstring(raw); libs=[dict(e.attrib) for e in tree.iter('library')]
        result[path]={'pin':pin,'xml_utf8':raw.decode('utf-8','strict'),'library_declarations':libs}
        for lib in libs:
            n=lib.get('name')
            if n in LIBRARIES:
                need(n not in declarations,'DUPLICATE_LIBRARY_DECLARATION'); declarations[n]=lib
    need(set(declarations)==set(LIBRARIES),'TWO_EXACT_LIBRARY_DECLARATIONS_REQUIRED')
    for n,p in zip(LIBRARIES,LIBRARY_FILES):
        need(declarations[n].get('file')==p,'LIBRARY_CONFIG_PATH_CHANGED')
    return {'directory':root,'selected_files':files,'files':result,'declarations':declarations}

def collect(s,tx,art,discovery,result):
    with contextlib.ExitStack() as stack:
        identity=s.activation['framework_epoch']['binding']['processes']['system_server']
        need(identity==discovery['system_server_identity'],'SYSTEM_SERVER_CHANGED')
        peer=s.held.HeldZygoteRoot(identity,art.DEADLINE); stack.callback(peer.close)
        result['package_before']=package(s,tx,'before')
        result['apk_before']=art.pin_guest(s,peer,APK)
        need(result['apk_before']['sha256']==APK_SHA,'INSTALLED_CLOCK_CHANGED')
        raw,_=s.target.read_file(APK,12*1024*1024)
        need(sha(raw)==APK_SHA,'APK_READ_CHANGED')
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            result['manifest_sha256']=sha(z.read('AndroidManifest.xml'))
        result['library_config_before']=xml_config(s,art,peer)
        result['library_files_before']={p:art.pin_guest(s,peer,p) for p in LIBRARY_FILES}
        need(sum(x['bytes'] for x in result['library_files_before'].values())<=32*1024*1024,'LIBRARY_BYTES')
        result['art_bin_names']=names(s,'/apex/com.android.art/bin')
        tools={}
        for name in ('dex2oat64','oatdump'):
            old=discovery['tools'][name]; current=art.pin_guest(s,peer,old['path'])
            need(all(current[k]==old[k] for k in ('device','inode','bytes','sha256')),'ART_TOOL_CHANGED:'+name)
            tools[old['path']]=current
        result['artifact_commands']=[]
        oat=str(Path(APK).parent/'oat/x86_64/base.odex')
        try: fd=s.target.open_root(oat,os.O_RDONLY)
        except FileNotFoundError: result['existing_oat']={'path':oat,'present':False}
        else:
            stack.callback(os.close,fd); pin=art.pin_fd(fd,64*1024*1024)
            result['existing_oat']={'path':oat,'present':True,'pin':pin}
            reply=art.command(s,'clock-current-oat-header',[art.OATDUMP,'--oat-file=/proc/self/fd/'+str(fd),'--header-only'],(fd,),15)
            receipt=art.record_command(tx,'clock-current-oat-header',reply)
            result['artifact_commands'].append(receipt)
            need(len(reply['stdout'])<=128*1024,'OAT_HEADER_OUTPUT_LIMIT')
            result['existing_oat']['header_rc']=reply['rc']
            result['existing_oat']['header_utf8']=reply['stdout'].decode('utf-8','strict')
            need(art.pin_fd(fd,64*1024*1024)==pin,'EXISTING_OAT_CHANGED')
        deps={n:v.get('dependency','') for n,v in result['library_config_before']['declarations'].items()}
        result['declared_dependencies']=deps
        result['declared_candidate_context']=None
        result['context_basis']='Package optional-library order plus exact installed XML/JAR bytes; not a running Java ClassLoader capture. Any dependencies or after-app policy still require explicit review.'
        if not any(deps.values()):
            context='PCL[]{'+'#'.join('PCL['+p+']' for p in LIBRARY_FILES)+'}'
            result['declared_candidate_context']=context
            analyzer='/apex/com.android.art/bin/dexoptanalyzer64'
            if 'dexoptanalyzer64' in result['art_bin_names']:
                tools[analyzer]=art.pin_guest(s,peer,analyzer)
                reply=art.command(s,'clock-flatten-context',[analyzer,'--class-loader-context='+context,
                    '--flatten-class-loader-context','--image=/system/framework/boot.art'],(),12)
                result['artifact_commands'].append(art.record_command(tx,'clock-flatten-context',reply))
                need(len(reply['stdout'])<=4096,'FLATTEN_OUTPUT_LIMIT')
                result['flatten_observation']={'rc':reply['rc'],'stdout':reply['stdout'].decode('utf-8','strict'),
                    'verified':False,'interpretation':'Actual installed parser output; return code and path grammar require independent review before FD order is used.'}
            else: result['flatten_observation']={'present':False,'verified':False,'path':analyzer}
        result['tools_before']=tools
        need(xml_config(s,art,peer)==result['library_config_before'],'XML_CONFIG_CHANGED')
        need({p:art.pin_guest(s,peer,p) for p in LIBRARY_FILES}==result['library_files_before'],'LIBRARY_JARS_CHANGED')
        need({p:art.pin_guest(s,peer,p) for p in tools}==tools,'ART_TOOLS_CHANGED')
        need(art.pin_guest(s,peer,APK)==result['apk_before'],'CURRENT_APK_CHANGED')
        result['package_after']=package(s,tx,'after')
        need(result['package_after']==result['package_before'],'PACKAGE_CONTEXT_CHANGED')
        result['closure_unchanged']=True; peer.verify(); result['guard_after']=s.guard()

def main():
    p=argparse.ArgumentParser(); p.add_argument('--execute',action='store_true'); args=p.parse_args()
    if not args.execute:
        print(json.dumps({'state':'INERT','UI_actions':0,'compiler_run':False,'installed':False})); return 0
    need(os.geteuid()==0 and not os.path.lexists(ROOT),'NEW_OWNED_OUTPUT_REQUIRED')
    tx=load(TX,TX_SHA,'clock_context_tx'); need(tx.ACTIVATION_SHA==ACTIVATION_SHA,'ACTIVATION_CHANGED')
    art=tx.load_module(STORAGE/'verify_candidate22.py',ART_SHA,'clock_context_art')
    discovery=json.loads(tx.read_regular(STORAGE/'art-discovery16/result.json',DISCOVERY_SHA,maximum=1048576))
    art.OUT=ROOT; art.DEADLINE=time.monotonic()+85
    os.umask(0o077); ROOT.mkdir(mode=0o750); os.chown(ROOT,0,1000); os.chmod(ROOT,0o750)
    result={'schema':'clock-art-declared-context04-v1','state':'FAILED','started_utc':stamp(),
        'reader_sha256':sha(Path(__file__).read_bytes()),'transport_sha256':TX_SHA,
        'activation_sha256':ACTIVATION_SHA,'read_only':True,'planned_read_only_PM_queries':4,
        'UI_actions':0,'compiler_run':False,'installed':False,'app_code_executed':False,
        'classloader_heap_capture':False,'ART_verified':False,'automatic_retry':False}
    rc=2
    try:
        result['resource_before']=limits()
        with tx.CameraSession(ROOT/'journal') as s:
            result['guard_before']=s.guard(); collect(s,tx,art,discovery,result)
        result['resource_after']=limits()
        result['state']='DECLARED_CONTEXT_METADATA_COLLECTED_NOT_ART_VERIFIED'; rc=0
    except BaseException as exc:
        result['state']='FAILED'; result['error']=type(exc).__name__+':'+str(exc); rc=2
    result['finished_utc']=stamp(); tx.write_new(ROOT/'result.json',result,alex_readable=True)
    raw=(ROOT/'result.json').read_bytes(); compressed=gzip.compress(raw,mtime=0)
    tx.write_new(ROOT/'result.json.gz',compressed,alex_readable=True)
    print(json.dumps({'state':result['state'],'error':result.get('error'),'result_path':str(ROOT/'result.json'),
        'result_bytes':len(raw),'result_sha256':sha(raw),'gzip_bytes':len(compressed),'gzip_sha256':sha(compressed)}))
    return rc
if __name__=='__main__': raise SystemExit(main())
