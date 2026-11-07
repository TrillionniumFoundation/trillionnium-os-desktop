#!/usr/bin/python3 -I
"""Read only the exact retained Gallery03 route and fixture; default inert.

No helper invocation, native observation, input, task removal, provider mutation,
package change or image rewrite is available in this controller.
"""
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
import argparse, gzip, hashlib, json, os, re, signal, types, xml.etree.ElementTree as ET

OUT=Path('/home/alex/work/pocket4-gallery-rotation-live-route03-20261105-r12-01')
SOURCE=Path('/home/alex/work/pocket4-gallery-rotation-flow-20261105-r12-03')
TOOLS=Path('/home/alex/work/pocket4-gallery-rotation-tools-20261105-r12-03')
EXPORT=Path('/home/alex/work/pocket4-gallery-rotation-saved-route03-20261105-r12-01/result.json')
EXPORT_SHA='027d94508fbd039b6e3b95481428774ec433a3f7276d1b2c755fa7c46ea361d8'
RESULT_SHA='41a2a9c45ab1e04fc70774f711384b701b7e495b8a46011f97cd18f0c0f0fb66'
TRANSPORT=Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
TRANSPORT_SHA='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
PINS={'rotation_ui.py':'ac885a393ff6b3e6cc477bb9c0acf55284fe3e4c92474fb82571884d07d9b650',
      'rotation_package.py':'44abbfe0193905a7b3a6137b4bb95dafc8d6cec4d795e8b258b97508cdd83dd4',
      'owned_media.py':'95b6c90fbc9ac22c41ca2c35d9ba3a13ce140de9cc52f710f2b5fd080506ae9b',
      'bounded_diagnostics.py':'c0eaf47627b31793b3c90d875ce74761ae9c98e749fc437a422e73c2da66a947'}
PATCHED_UI_SHA='2ad57b62514cd0cc45056c34d5c30a3df0240d800394701f408b02f212be4ccf'
RUN='d24b61ed8f7c9a03'
PACKAGE='org.droidloom.qa.galleryrotation.r12.n'+RUN
GALLERY='com.android.gallery3d'
TASK=1005
ALBUM_URI='content://media/external/images/media?bucketId=-1681480384'
GALLERY_TOKEN='24212890'
HELPER_TOKEN='243553609'
WINDOW_TOKEN='c4ad8a1'
REPLACEMENTS=(
    (r"r'(?=^\s*\* Hist #\d+: ActivityRecord\{)'",r"r'(?=^[ \t]*\* Hist[ \t]+#\d+: ActivityRecord\{)'"),
    (r"r'^\s*\* Hist #\d+: ActivityRecord\{[^\n]*\bu0 '",r"r'^[ \t]*\* Hist[ \t]+#\d+: ActivityRecord\{[^\n]*\bu0 '"))

def need(value,reason):
    if not value:raise RuntimeError(reason)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def stamp():return datetime.now(timezone.utc).isoformat()

def load(path,pin,patch=False):
    raw=Path(path).read_bytes();need(sha(raw)==pin,'SOURCE_PIN_CHANGED:'+Path(path).name)
    if patch:
        text=raw.decode()
        for old,new in REPLACEMENTS:
            need(text.count(old)==1,'TWO_EXACT_HIST_REPLACEMENTS_REQUIRED');text=text.replace(old,new)
        raw=text.encode();need(sha(raw)==PATCHED_UI_SHA,'PATCHED_UI_PIN_CHANGED')
    module=types.ModuleType('readonly_'+Path(path).stem);module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__);return module

def original_scope(tx):
    raw=tx.read_regular(SOURCE/'result.json',RESULT_SHA,32768);old=json.loads(raw)
    need(old['state']=='FAILED' and old['error']=='RuntimeError:EXACT_TOP_GALLERY_ACTIVITY_RECORD_REQUIRED'
         and old['temporary_package']==PACKAGE and old['run']==RUN
         and old['native_launches']==1 and old['normal_closed_tasks']==[]
         and old['rotation_input_calls']==0 and old['instrument_calls']==['seed']
         and old['client_pending']=='open-owned-album-1'
         and set(old['owned_tasks'])=={str(TASK)} and old['installed_identity']['uid']==10197,
         'EXACT_ORIGINAL_FAILED_GALLERY03_REQUIRED')
    need(old['native_pending']=={'open-owned-album-1':{'input_acknowledged':True,'kind':'tap',
         'post_capture_outcome_unknown':True}}
         and all(old[k] is None for k in ('helper_pending','rotation_pending','album_pending',
             'close_pending','directory_pending'))
         and old['install_pending'] is False and old['uninstall_pending'] is False,
         'ORIGINAL_PENDING_SCOPE_CHANGED')
    export=json.loads(tx.read_regular(EXPORT,EXPORT_SHA,524288))
    need(export['source_result_sha256']==RESULT_SHA and export['source_query_stems']==['060-android']
         and export['artifacts']['commands/060-android.stdout']['sha256']==
             'd0f40e33cd80274075545744b5f728c2674ed9f1ec444a2cfa9b5c1206bb538c',
         'FIXED_SAVED_ROUTE_EXPORT_REQUIRED')
    saved={};pins={}
    for name in ('004-original-media-before.json','015-owned-two-images-seeded-namespace.json',
                 '019-owned-two-images-seeded.json'):
        need(name in export['ui_file_inventory'],'SAVED_RECORD_NOT_IN_FIXED_INVENTORY')
        raw=tx.read_regular(SOURCE/'ui'/name,maximum=131072)
        saved[name]=json.loads(raw);pins[name]={'bytes':len(raw),'sha256':sha(raw)}
    need(len(old['instrumentations'])==1 and old['instrumentations'][0]['uid']==10197
         and old['instrumentations'][0]['operation']=='seed','ORIGINAL_SEED_IDENTITY')
    for role,identity in (('control',98),('copy',100)):
        seed=old['instrumentations'][0]['media'][role]
        proof=saved['019-owned-two-images-seeded.json']['media'][role]
        need(seed['uri']=='content://media/external_primary/images/media/'+str(identity)
             and proof['metadata']['_id']==identity and proof['file']['sha256']==seed['sha256']
             and proof['file']['bytes']==seed['bytes'],'ORIGINAL_SAVED_FILE_PROOF_DIFFERS_FROM_SEED')
    return old,saved,pins

def private_state(session):
    path='/data/user/0/'+PACKAGE+'/shared_prefs/owned-rotation-'+RUN+'.xml'
    raw,metadata=session.target.read_file(path,65536,single_link=True)
    root=ET.fromstring(raw);need(root.tag=='map','PRIVATE_RECORD_SCHEMA');value={}
    for item in root:
        key=item.get('name');need(key and key not in value,'PRIVATE_RECORD_DUPLICATE')
        if item.tag=='string':v=item.text or ''
        elif item.tag in ('int','long'):v=int(item.get('value'))
        else:raise RuntimeError('PRIVATE_RECORD_TYPE')
        value[key]=v
    expected={'run':RUN,'phase':'ALBUM_OPEN_1','pending':'gallery-open-1',
              'gallery_launches':1,'album_uri':ALBUM_URI,'insert_calls':2,'write_calls':2,
              'publish_calls':2,'control_uri':'content://media/external_primary/images/media/98',
              'copy_uri':'content://media/external_primary/images/media/100'}
    need(all(value.get(k)==v for k,v in expected.items()) and value.get('delete_calls',0)==0,
         'PRIVATE_EXACT_SINGLE_ALBUM_DISPATCH_STATE_CHANGED')
    need(type(value.get('started_elapsed_ms')) is int and value['started_elapsed_ms']>0,
         'ORIGINAL_ELAPSED_LEASE_REQUIRED')
    return {'values':value,'raw_sha256':sha(raw),'bytes':len(raw),'file_metadata':metadata}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    if not args.execute:
        print(json.dumps({'state':'INERT','task':TASK,'helper_uid':10197,'image_ids':[98,100],
                          'UI_actions':0,'mutations':0,'would_replay_open':False}));return 0
    tx=load(TRANSPORT,TRANSPORT_SHA)
    need(os.geteuid()==0 and not os.path.lexists(OUT),'NEW_READONLY_OUTPUT_REQUIRED')
    old,saved,saved_pins=original_scope(tx)
    ui=load(TOOLS/'rotation_ui.py',PINS['rotation_ui.py'],True)
    pkg=load(TOOLS/'rotation_package.py',PINS['rotation_package.py'])
    media_mod=load(TOOLS/'owned_media.py',PINS['owned_media.py'])
    diag=load(TOOLS/'bounded_diagnostics.py',PINS['bounded_diagnostics.py'])
    os.umask(0o077);OUT.mkdir(mode=0o750);os.chown(OUT,0,1000);os.chmod(OUT,0o750)
    (OUT/'records').mkdir(mode=0o700)
    result={'schema':'gallery03-exact-retained-route-readonly-v1','state':'FAILED','started_utc':stamp(),
            'source_result_sha256':RESULT_SHA,'saved_export_sha256':EXPORT_SHA,
            'original_pending_preserved':old['native_pending'],'original_client_pending':old['client_pending'],
            'original_result_modified':False,'UI_actions':0,'native_observations':0,
            'provider_package_or_physical_mutations':0,'task_removals':0,'helper_invocations':0,
            'explicit_read_only_android_queries':0,'provider_sql_read_queries':0,
            'saved_record_pins':saved_pins,'whole_app_production_ready':False,'business_scope_pass':False}
    sequence=0
    def record(label,value):
        nonlocal sequence
        sequence+=1;tx.write_new(OUT/'records'/('%03d-'%sequence+label+'.json'),value)
        if isinstance(value,dict) and value.get('read_only') is True and 'rows' in value:
            result['provider_sql_read_queries']+=1
    def expired(signum,frame):raise TimeoutError('READ_ONLY_RECONCILIATION_DEADLINE')
    previous_handler=signal.signal(signal.SIGALRM,expired);signal.alarm(160)
    try:
        with tx.ui_lock(),tx.CameraSession(OUT/'commands') as session:
            result['guard_before']=session.guard();need(result['guard_before']==old['guard_after'],'MAIN_DIFFERS')
            original_android=session.android;last_activity={}
            permitted=[['/system/bin/cmd','activity','stack','list'],
                       ['/system/bin/dumpsys','window','displays'],
                       ['/system/bin/dumpsys','activity','activities',GALLERY],
                       ['/system/bin/cat','/proc/uptime']]
            for package in (PACKAGE,GALLERY):
                permitted.extend([['/system/bin/dumpsys','package',package],
                                  ['/system/bin/pm','path','--user','0',package]])
            def readonly_android(argv,timeout=20):
                need(argv in permitted and result['explicit_read_only_android_queries']<24,
                     'ONLY_FIXED_READ_ONLY_ANDROID_QUERY_ALLOWED')
                result['explicit_read_only_android_queries']+=1
                value=original_android(argv,timeout)
                if argv==['/system/bin/dumpsys','activity','activities',GALLERY]:last_activity['raw']=value.decode()
                return value
            session.android=readonly_android
            media=media_mod.OwnedMedia(session,record)
            try:
                media.media=old['instrumentations'][0]['media']
                rows=saved['004-original-media-before.json']['rows']
                media.before={'rows':len(rows),'sha256':sha(json.dumps(rows,sort_keys=True,separators=(',',':')).encode())}
                media.baseline=saved['019-owned-two-images-seeded.json']['media']
                media.parent=session.target.open_root('/storage/emulated/0/DCIM',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                media.parent_birth=media_mod.birth(os.fstat(media.parent))
                media.backing_parent=session.target.open_root('/data/media/0/DCIM',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                media.backing_parent_birth=media_mod.birth(os.fstat(media.backing_parent))
                result['rounds']=[]
                for turn in ('before','after'):
                    identity=pkg.identity(session,PACKAGE,pkg.APK_SHA,10197)
                    need(identity==old['installed_identity'],'RETAINED_HELPER_IDENTITY_CHANGED')
                    gallery=pkg.identity(session,GALLERY,old['gallery_before']['apk_sha256'],10064,40030)
                    gallery['permissions']=diag.permissions(session,record,'gallery-permissions-'+turn)[GALLERY]
                    need(gallery==old['gallery_before'],'GALLERY_IDENTITY_OR_PERMISSIONS_CHANGED')
                    private=private_state(session)
                    uptime=readonly_android(['/system/bin/cat','/proc/uptime'],6).decode().strip()
                    need(re.fullmatch(r'[0-9]+\.[0-9]+ [0-9]+\.[0-9]+',uptime),'UPTIME_GRAMMAR')
                    elapsed_ms=int(Decimal(uptime.split()[0])*1000)
                    age=elapsed_ms-private['values']['started_elapsed_ms'];need(age>=0,'NEGATIVE_ORIGINAL_LEASE_AGE')
                    adapter=ui.Adapter(session,tx,OUT/'records')
                    bound={}
                    def route_record(label,value):
                        record(turn+'-'+label,value)
                        if label=='actual-owned-album-route':bound.update(value)
                    adapter.record=route_record;adapter.baseline={851}
                    adapter.owned={TASK:old['owned_tasks'][str(TASK)]}
                    adapter.pending={k:dict(v) for k,v in old['native_pending'].items()}
                    adapter.allow_new={'source':'open-owned-album-1','component':(GALLERY,ui.FILES)}
                    need(adapter.bind_gallery_route('open-owned-album-1',ALBUM_URI,10197)==TASK,
                         'SAME_RETAINED_TASK_REQUIRED')
                    need(bound['foreground']['window_token']==WINDOW_TOKEN and bound['new_task'] is False,
                         'ORIGINAL_RETAINED_WINDOW_REQUIRED')
                    raw=last_activity['raw']
                    tops=re.findall(r'^[ \t]*topResumedActivity=ActivityRecord\{([^\n]+)\}',raw,re.M)
                    need(tops.count(GALLERY_TOKEN+' u0 '+GALLERY+'/.app.GalleryActivity t1005')==1,
                         'ORIGINAL_GALLERY_ACTIVITY_TOKEN_NOT_TOP')
                    headers=re.findall(r'^[ \t]*\* Hist[ \t]+#\d+: ActivityRecord\{([^\n]+)\}',raw,re.M)
                    need([h for h in headers if h.endswith(' t1005')]==[
                             GALLERY_TOKEN+' u0 '+GALLERY+'/.app.GalleryActivity t1005',
                             HELPER_TOKEN+' u0 '+PACKAGE+'/.RotationActivity t1005'],
                         'ORIGINAL_HELPER_AND_GALLERY_ACTIVITY_TOKENS_REQUIRED')
                    provider=media.provider_pin('reviewed-provider-'+turn)
                    need(media.namespace('exact-original-namespace-'+turn)==saved['015-owned-two-images-seeded-namespace.json']['rows'],
                         'ORIGINAL_FULL_NAMESPACE_TUPLES_CHANGED')
                    files=media.verify('exact-original-images-'+turn,False)
                    result['rounds'].append({'phase':turn,'helper_identity':identity,'gallery_identity':gallery,
                        'private_state':private,'route':bound,'activity_dump_sha256':sha(raw.encode()),
                        'fixture_age_elapsed_ms':age,'lease_ms':1200000,'lease_expired':age>=1200000,
                        'elapsed_clock_source':'held /proc/uptime, millisecond truncation',
                        'provider':provider,'media':files,'directory_rows':dict(media.directory_rows),
                        'fuse_parent_birth':media.parent_birth,'backing_parent_birth':media.backing_parent_birth,
                        'backing_folder_birth':dict(media.backing_folder_birth)})
                a,b=result['rounds']
                need(all(a[k]==b[k] for k in ('helper_identity','gallery_identity','private_state','route',
                     'provider','media','directory_rows','fuse_parent_birth','backing_parent_birth','backing_folder_birth')),
                     'RETAINED_STATE_CHANGED_DURING_READ_ONLY_RECONCILIATION')
                for name,pin in saved_pins.items():tx.read_regular(SOURCE/'ui'/name,pin['sha256'],131072)
                tx.read_regular(SOURCE/'result.json',RESULT_SHA,32768)
                result['guard_after']=session.guard();need(result['guard_after']==result['guard_before'],'MAIN_CHANGED')
            finally:media.close()
        result['state']='EXACT_ORIGINAL_SINGLE_ALBUM_ROUTE_AND_UNCHANGED_FIXTURE_OBSERVED'
        result['route_effect_independently_observed']=True
        result['original_pending_rewritten']=False
        result['cleanup_executed']=False
    except BaseException as exc:
        result['state']='FAILED';result['error']=type(exc).__name__+':'+str(exc)
        result['route_effect_independently_observed']=False
    finally:
        signal.alarm(0);signal.signal(signal.SIGALRM,previous_handler)
    result['finished_utc']=stamp()
    raw=(json.dumps(result,indent=2,sort_keys=True)+'\n').encode()
    need(len(raw)<=131072,'READONLY_RESULT_BOUND')
    packed=gzip.compress(raw,mtime=0);need(len(packed)<=65536,'READONLY_GZIP_BOUND')
    tx.write_new(OUT/'result.json',raw,alex_readable=True)
    tx.write_new(OUT/'result.json.gz',packed,alex_readable=True)
    print(json.dumps({'state':result['state'],'error':result.get('error'),
        'result_path':str(OUT/'result.json'),'result_bytes':len(raw),'result_sha256':sha(raw),
        'gzip_path':str(OUT/'result.json.gz'),'gzip_bytes':len(packed),'gzip_sha256':sha(packed),
        'explicit_read_only_android_queries':result['explicit_read_only_android_queries'],
        'provider_sql_read_queries':result['provider_sql_read_queries'],
        'UI_actions':0,'mutations':0,'original_pending_rewritten':False},sort_keys=True))
    return 0 if result['state']=='EXACT_ORIGINAL_SINGLE_ALBUM_ROUTE_AND_UNCHANGED_FIXTURE_OBSERVED' else 1

if __name__=='__main__':raise SystemExit(main())
