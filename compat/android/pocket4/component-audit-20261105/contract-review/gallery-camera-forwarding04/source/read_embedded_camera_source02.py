#!/usr/bin/python3 -I
"""Inspect installed Gallery embedded-camera classes; no Android/UI/package changes."""
from pathlib import Path
from datetime import datetime, timezone
import gzip, hashlib, io, json, os, re, stat, struct, types, zipfile, zlib

OUT=Path('/home/alex/work/pocket4-gallery-embedded-camera-source-20261105-r12-02')
TX=Path('/home/alex/work/pocket4-runtime-profile-20261105-r12-6144-01/camera_transaction.py')
TX_SHA='e65a47bea8b3800d0b1a89247bd8c356dd291523c2d248d401d05d1d3b55fb83'
TOOLS=Path('/home/alex/work/pocket4-clock-session-tools-20261105-r12-01')
INSPECT_SHA='4fe7333255ccbcd6df22a4c89d40c669603f7817eae3d0071c7e5f930a6b424f'
PINS_SHA='20b2752edb6c820577c3467bd38b8386f88825fc18ae66f3394302ae3a630b24'
APK='/product/app/Gallery2/Gallery2.apk'
APK_SHA='347c376f07a4365fa3828ddf9f011994fe527a53fd2f5bd059997ffd3904d46e'
PACKAGE='com.android.gallery3d'
EPOCH='48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'

def need(ok, reason):
    if not ok: raise RuntimeError(reason)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def load(path, pin):
    raw=path.read_bytes();need(sha(raw)==pin,'PIN_CHANGED:'+path.name)
    mod=types.ModuleType('gallery_source_'+path.stem);mod.__file__=str(path)
    exec(compile(raw,str(path),'exec'),mod.__dict__);return mod
def classes(raw):
    need(len(raw)>=112 and re.fullmatch(rb'dex\n0[34][0-9]\x00',raw[:8]),'DEX_MAGIC')
    def u32(off):
        need(0<=off<=len(raw)-4,'DEX_U32_BOUND');return struct.unpack_from('<I',raw,off)[0]
    need(u32(32)==len(raw) and u32(36)==112 and u32(40)==0x12345678,'DEX_HEADER')
    need(u32(8)==zlib.adler32(raw[12:])&0xffffffff and raw[12:32]==hashlib.sha1(raw[32:]).digest(),'DEX_CHECKSUM')
    sc,so,tc,to,cc,co=(u32(x) for x in (56,60,64,68,96,100))
    need(so+4*sc<=len(raw) and to+4*tc<=len(raw) and co+32*cc<=len(raw),'DEX_TABLE_BOUNDS')
    names=[]
    for off in range(co,co+cc*32,32):
        typ=u32(off);need(typ<tc,'DEX_TYPE_INDEX');idx=u32(to+typ*4);need(idx<sc,'DEX_STRING_INDEX');pos=u32(so+idx*4)
        for _ in range(5):
            need(pos<len(raw),'DEX_ULEB_BOUND');v=raw[pos];pos+=1
            if v<128:break
        else:raise RuntimeError('DEX_ULEB_OVERFLOW')
        end=raw.find(b'\0',pos,min(len(raw),pos+4096));need(end>=pos,'DEX_DESCRIPTOR_TERMINATION')
        name=raw[pos:end].decode('ascii');need(re.fullmatch(r'L[^;\s]+;',name),'DEX_DESCRIPTOR')
        names.append(name)
    need(len(names)==len(set(names)),'DUPLICATE_CLASS');return names

def main():
    need(os.geteuid()==0 and not os.path.lexists(OUT),'NEW_ROOT_REQUIRED')
    tx=load(TX,TX_SHA);inspector=load(TOOLS/'inspect_clock_dex01.py',INSPECT_SHA)
    raw=(TOOLS/'baksmali-pins.json').read_bytes();need(sha(raw)==PINS_SHA,'TOOL_MANIFEST_CHANGED');pins=json.loads(raw)
    for group in ('jre','jars'):
        for entry in pins[group].values():inspector.check_tool(entry)
    os.umask(0o077);OUT.mkdir(mode=0o750);os.chown(OUT,0,1000);os.chmod(OUT,0o750)
    os.sched_setaffinity(0,{20})
    result={'schema':'gallery-embedded-camera-code-inspection-v1','state':'FAILED','ui_actions':0,
        'package_changes':0,'apk_code_executed':False,'tool_pins_sha256':PINS_SHA,
        'started_utc':datetime.now(timezone.utc).isoformat(),'sources':{}}
    try:
        with tx.CameraSession(OUT/'commands') as s:
            result['guard_before']=s.guard();need(s.epoch_sha256==EPOCH,'MAIN_CHANGED')
            need(s.android(['/system/bin/pm','path','--user','0',PACKAGE]).decode().splitlines()==['package:'+APK],'ACTIVE_APK_CHANGED')
            listed=s.android(['/system/bin/pm','list','packages','-U','--user','0',PACKAGE]).decode().splitlines()
            need(listed==['package:'+PACKAGE+' uid:10064'],'GALLERY_UID_CHANGED')
            raw,meta=s.target.read_file(APK,16*1024*1024,single_link=True);need(sha(raw)==APK_SHA,'INSTALLED_APK_CHANGED')
            result['apk']={'path':APK,'sha256':sha(raw),'bytes':len(raw),'metadata':meta}
            cp=':'.join(pins['jars'][name]['canonical'] for name in sorted(pins['jars']))
            cmd=[pins['jre']['bin/java']['canonical'],'-Xmx192m','-cp',cp,'org.jf.baksmali.Main']
            help_result=s.run_host('gallery-baksmali-help',cmd+['disassemble','--help'],15)
            need(help_result['rc']==0 and help_result['joined'] and not help_result['timed_out']
                and b'--classes' in help_result['stdout']+help_result['stderr'],'BAKSMALI_CLASS_FILTER_UNVERIFIED')
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                members=archive.namelist();need(len(members)==len(set(members)) and archive.testzip() is None,'APK_ZIP_INTEGRITY')
                dex_names=sorted(n for n in members if re.fullmatch(r'classes(?:[2-9][0-9]*)?\.dex',n))
                need(1<=len(dex_names)<=4,'DEX_COUNT_BOUND');result['dex']=[]
                for name in dex_names:
                    need(archive.getinfo(name).file_size<=32*1024*1024,'DEX_SIZE_BOUND')
                    data=archive.read(name);names=classes(data)
                    selected=sorted(n for n in names if any(n==prefix+';' or n.startswith(prefix+'$')
                        for prefix in ('Lcom/android/camera/CameraActivity','Lcom/android/camera/PhotoModule',
                            'Lcom/android/camera/VideoModule','Lcom/android/camera/CameraModule',
                            'Lcom/android/camera/app/CameraApp','Lcom/android/gallery3d/app/GalleryAppImpl')))
                    need(len(selected)<=96,'SELECTED_CLASS_BOUND')
                    camera_classes=sorted(n for n in names if n.startswith('Lcom/android/camera/'))
                    result['dex'].append({'name':name,'bytes':len(data),'sha256':sha(data),'class_count':len(names),
                        'selected':selected,'all_camera_defined_descriptors':camera_classes,
                        'MediaSaveService_descriptor_defined':'Lcom/android/camera/MediaSaveService;' in names,
                        'MediaSaveService_slash_utf8_occurrences':data.count(b'com/android/camera/MediaSaveService'),
                        'MediaSaveService_dot_utf8_occurrences':data.count(b'com.android.camera.MediaSaveService'),
                        'string_occurrences_do_not_prove_reachability_or_reflection_absence':True})
                    if not selected:continue
                    path=OUT/name;tx.write_new(path,data);dest=OUT/(name+'-selected')
                    run=s.run_host('gallery-'+name.replace('.','-'),cmd+['disassemble','--jobs','1','--classes',','.join(selected),'--output',str(dest),str(path)],60)
                    need(run['rc']==0 and run['joined'] and not run['timed_out'],'DISASSEMBLY_FAILED')
                    for descriptor in selected:
                        code=(dest/(descriptor[1:-1]+'.smali')).read_bytes();need(len(code)<=512*1024,'CLASS_SIZE_BOUND')
                        need(descriptor not in result['sources'],'MULTIPLE_CLASS_DEFINITIONS')
                        result['sources'][descriptor]={'dex':name,'sha256':sha(code),'bytes':len(code),'smali':code.decode()}
            need('Lcom/android/camera/CameraActivity;' in result['sources'],'EMBEDDED_CAMERA_ACTIVITY_MISSING')
            again,after=s.target.read_file(APK,16*1024*1024,single_link=True)
            need(sha(again)==APK_SHA and meta==after,'APK_CHANGED_DURING_INSPECTION')
            result['guard_after']=s.guard();need(result['guard_after']==result['guard_before'],'MAIN_CHANGED_AFTER')
            s.caller_status('gallery-embedded-camera-code-final');result['state']='INSTALLED_EMBEDDED_CAMERA_CODE_INSPECTED'
    except BaseException as e:result['error']=type(e).__name__+':'+str(e)
    result['finished_utc']=datetime.now(timezone.utc).isoformat()
    encoded=(json.dumps(result,indent=2,sort_keys=True)+'\n').encode();packed=gzip.compress(encoded,mtime=0)
    need(len(packed)<=512*1024,'EXPORT_SIZE_BOUND')
    tx.write_new(OUT/'result.json',encoded,alex_readable=True);tx.write_new(OUT/'result.json.gz',packed,alex_readable=True)
    print(json.dumps({'state':result['state'],'error':result.get('error'),'ui_actions':0,
        'gzip_path':str(OUT/'result.json.gz'),'gzip_bytes':len(packed),'gzip_sha256':sha(packed),
        'result_bytes':len(encoded),'result_sha256':sha(encoded),'selected_classes':len(result['sources'])}))
    return 0 if result['state']=='INSTALLED_EMBEDDED_CAMERA_CODE_INSPECTED' else 1
if __name__=='__main__':raise SystemExit(main())
