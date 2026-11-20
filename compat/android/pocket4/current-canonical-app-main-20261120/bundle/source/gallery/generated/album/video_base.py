#!/usr/bin/python3 -I
"""One synthetic image, actual Gallery render/reopen, exact MediaStore cleanup."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,io,json,os,re,signal,stat,time,types
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
ROOT=None  # Bound once by the current video case.
TX=Path('/home/alex/work/pocket4-runtime-profile-20261105-r12-6144-01/camera_transaction.py')
BASE=Path('/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/custody/d02821d751736a9e-ui_preflight04.py')
DOC=Path('/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/custody/d1426a5d52e80d40-run_saf10.py')
DIAG=Path('/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/custody/93cf4567c19f6033-diagnostics_source.py')
PINS={str(TX):'e65a47bea8b3800d0b1a89247bd8c356dd291523c2d248d401d05d1d3b55fb83',
    str(BASE):'d02821d751736a9e3cf275ec0b27383852e24362928fd4257ebb6d3dee7f6a58',
    str(DOC):'d1426a5d52e80d4064430070193e5b4c083f69ae7b7a44a733e6cbb413edaae4',
    str(DIAG):'93cf4567c19f6033dce0b120d068a7120a2b27952a4a1d0d4cfdd8b988ebfbcb'}
PATTERN_SHA='0206850626989ddd3a52693252d211dbd5e03addfe86332190da8ca1cb6951e9'
TASK_PROOF=Path('/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/fixtures/9cb008b7050d3bb0-task-option-proof.json')
TASK_PROOF_SHA='9cb008b7050d3bb0b8da2221140c02b39ebde973833b5ee24039932e266e90a5'
RUN='a1d407c85b3e6f92';PACKAGE='org.droidloom.qa.media.r12.n'+RUN
FOLDER='Pocket4_Gallery_r12_'+RUN;NAME='pocket4-pattern-'+RUN+'.png'
RELATIVE='DCIM/'+FOLDER+'/';GUEST_FOLDER='/storage/emulated/0/DCIM/'+FOLDER
GUEST_FILE=GUEST_FOLDER+'/'+NAME
GALLERY='com.android.gallery3d';COMPONENT=GALLERY+'/.app.GalleryActivity'
GALLERY_SHA='835fe119745324276457b4434fc39f25b633e752c822d2fc9be40eb4b2d45439'
APK=Path('/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/inputs/7fc4dadcc33c94cd41d0425473622df38138d60801c2e5585c4d28cf7db68933/owned-media.apk')
APK_SHA = '7fc4dadcc33c94cd41d0425473622df38138d60801c2e5585c4d28cf7db68933'
CERT_SHA = 'b152def48096bab1000175a762244910f2c4aa9b5b6b080813515a1a38a0b403'
BUILD_SHA = '632e5c0aa13a758f7245939b227577c1b8416a3c950e55eddbc5e0bb61d735b9'
DB='/data/user/0/com.android.providers.media.module/databases/external.db'
LEASE=540;RESERVE=90

def need(value,reason):
    if not value:raise RuntimeError(reason)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def stamp():return datetime.now(timezone.utc).isoformat()
def load(path,pin,name):
    raw=Path(path).read_bytes();need(sha(raw)==pin,'SOURCE_CHANGED:'+name)
    module=types.ModuleType(name);module.__file__=str(path);exec(compile(raw,str(path),'exec'),module.__dict__)
    return module
def fp(s):return {k:getattr(s,k) for k in ('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink')}
def expired(signum,frame):raise TimeoutError('GALLERY_DEADLINE_NO_REPLAY')

class Gallery:
    def __init__(self,s,tx,base,doc,diag,pattern):
        self.s,self.tx,self.doc,self.pattern=s,tx,doc,pattern
        self.ui=base.Trial(s,tx);self.diagnostics=diag.Trial(s,tx,ROOT)
        self.staged=self.installed=None;self.install_pending=self.uninstall_pending=False
        self.close_pending=None
        self.pending=None;self.media=None;self.folder_fd=self.folder_parent=None;self.folder_birth=None
        self.native_launches=[];self.closed=[];self.intent_calls=0;self.instrument_calls=[]
        self.result={'schema':'pocket4-gallery-image-flow-v1','state':'FAILED','whole_app_production_ready':False,
            'run':RUN,'package':GALLERY,'temporary_package':PACKAGE,'automatic_retry':False,
            'started_utc':stamp(),'source_pins':PINS,'rounds':[],'media_operations':[],
            'fixture_is_not_launcher':True,'no_existing_media_bytes_read':True,'max_seconds':LEASE,'cleanup_seconds':RESERVE}

    def record(self,label,value):self.ui.record(label,value)

    def query(self,label,sql):
        need(sql.startswith('SELECT ') and not re.search(r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|ATTACH)\b',sql,re.I),'READ_ONLY_SQL')
        cmd=['/system/bin/env','-i']+[k+'='+self.s.environment[k] for k in sorted(self.s.environment)]
        cmd+=['/system/bin/timeout','-k','2','10','/system/bin/sqlite3','-readonly','-json',DB,'PRAGMA query_only=ON;BEGIN;'+sql+';ROLLBACK;']
        r=self.s.root_query(label,cmd,14)
        need(r['rc']==0 and r['joined'] and not r['timed_out'],'MEDIA_QUERY_FAILED')
        need(len(r['stdout'])<262144,'MEDIA_QUERY_BOUND')
        rows=json.loads(r['stdout']) if r['stdout'].strip() else []
        self.record('media-'+label,{'rows':rows,'read_only':True});return rows

    def namespace(self,label):
        fields='_id,_data,_display_name,relative_path,owner_package_name,media_type,mime_type,_size,width,height,is_pending'
        return self.query(label,'SELECT '+fields+" FROM files WHERE relative_path='"+RELATIVE+"' OR _data IN ('"+
            GUEST_FOLDER+"','"+GUEST_FILE+"') OR _display_name IN ('"+FOLDER+"','"+NAME+"') OR owner_package_name='"+PACKAGE+"' ORDER BY _id")

    def original_media(self,label):
        return self.query(label,"SELECT _id,media_type,mime_type,_size,width,height,is_pending FROM files WHERE media_type IN (1,3) AND (owner_package_name IS NULL OR owner_package_name!='"+PACKAGE+"') ORDER BY _id")

    def gallery_identity(self):
        value=self.doc.identity(self.s,GALLERY,GALLERY_SHA,self.s.gallery_uid,40030)
        raw=self.s.android(['/system/bin/dumpsys','package',GALLERY],12).decode()
        blocks=re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)',raw,re.M|re.S)
        need(len(blocks)==1,'GALLERY_PACKAGE_SECTION')
        permissions=sorted(l.strip() for l in blocks[0].splitlines() if re.search(r'android\.permission\.[A-Z_]+: granted=',l))
        need(any(l.startswith('android.permission.READ_MEDIA_IMAGES: granted=true,') for l in permissions),'GALLERY_MEDIA_PERMISSION_NOT_GRANTED')
        value['permissions']=permissions;value['epoch_sha256']=self.s.epoch_sha256
        return value

    def setup(self):
        self.result['guard_before']=self.s.guard();self.result['gallery_before']=self.gallery_identity()
        self.original_rows=self.original_media('original-before');need(self.namespace('namespace-before')==[],'GLOBAL_MEDIA_NAMESPACE_NOT_ABSENT')
        self.folder_parent=self.s.target.open_root('/storage/emulated/0/DCIM',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.stat(FOLDER,dir_fd=self.folder_parent,follow_symlinks=False)
        except FileNotFoundError:pass
        else:raise RuntimeError('OWNED_FOLDER_ALREADY_EXISTS')
        self.doc.Flow.install(self)
        self.before_diag=self.diagnostics.diagnostics('before',self.s.gallery_uid)
        self.record('global-owned-namespace-absent',{'global_media_rows':0,'physical_directory_absent':True,'parent_preexisting':True})

    def prefs(self):
        path='/data/user/0/'+PACKAGE+'/shared_prefs/owned-media-'+RUN+'.xml'
        try:raw,_=self.s.target.read_file(path,16384,single_link=True)
        except FileNotFoundError:return None
        root=ET.fromstring(raw);need(root.tag=='map','PREFS_SCHEMA');value={}
        for item in root:
            name=item.get('name');need(name and name not in value,'PREFS_DUPLICATE')
            if item.tag=='string':value[name]=item.text or ''
            elif item.tag in ('int','long'):value[name]=int(item.get('value'))
            else:raise RuntimeError('PREFS_TYPE')
        need(value.get('run')==RUN,'PREFS_RUN');return value

    def instrument(self,operation):
        need(operation in ('seed','verify','delete') and self.pending is None,'INSTRUMENT_SCOPE_OR_PENDING')
        need(len(self.instrument_calls)<5,'INSTRUMENT_BOUND')
        need(self.doc.identity(self.s,PACKAGE,APK_SHA)==self.installed,'FIXTURE_IDENTITY_CHANGED')
        label='media-'+operation+'-'+str(len(self.instrument_calls))
        argv=['/system/bin/am','instrument','-w','-r','-e','run',RUN,'-e','op',operation,PACKAGE+'/.MediaFixture']
        self.record(label+'-intent',{'argv':argv,'automatic_retry':False,'mutating':operation in ('seed','delete')})
        self.pending=label;self.instrument_calls.append(operation)
        raw=self.s.android(argv,55).decode();self.record(label+'-output',{'stdout':raw})
        values=re.findall(r'^INSTRUMENTATION_RESULT: result_json=(.+)$',raw,re.M)
        codes=re.findall(r'^INSTRUMENTATION_CODE: (-?\d+)\s*$',raw,re.M)
        need(len(values)==1 and codes==['0'],'INSTRUMENT_TERMINAL_NOT_SUCCESS')
        value=json.loads(values[0]);need(value.get('ok') is True and value.get('package')==PACKAGE and value.get('run')==RUN
            and value.get('uid')==self.installed['uid'] and value.get('operation')==operation,'INSTRUMENT_RESULT_IDENTITY')
        expected='DELETED' if operation=='delete' else 'SEEDED'
        need(value.get('phase')==expected and value.get('pending')=='','INSTRUMENT_EFFECT_PENDING')
        need(value.get('insert_calls')==1 and value.get('write_calls')==1 and value.get('publish_calls')==1
            and value.get('delete_calls')==(1 if operation=='delete' else 0),'FIXTURE_EFFECT_COUNTS')
        saved=self.prefs();need(saved is not None and saved.get('phase')==expected and saved.get('pending')=='','INSTRUMENT_PREFS_READBACK')
        self.pending=None;self.result['media_operations'].append(value);return value

    def held_folder(self):
        if self.folder_fd is None:
            self.folder_fd=os.open(FOLDER,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=self.folder_parent)
            self.folder_birth=fp(os.fstat(self.folder_fd))
        need(fp(os.stat(FOLDER,dir_fd=self.folder_parent,follow_symlinks=False))==self.folder_birth
            and fp(os.fstat(self.folder_fd))==self.folder_birth,'OWNED_FOLDER_REPLACED')
        fresh=os.open('.',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=self.folder_fd)
        try:names=os.listdir(fresh);need(fp(os.fstat(fresh))==self.folder_birth,'FRESH_DIRECTORY_IDENTITY_CHANGED')
        finally:os.close(fresh)
        need(fp(os.stat(FOLDER,dir_fd=self.folder_parent,follow_symlinks=False))==self.folder_birth
            and fp(os.fstat(self.folder_fd))==self.folder_birth,'OWNED_DIRECTORY_CHANGED_AFTER_ENUMERATION')
        need(set(names)<={NAME},'FOREIGN_FILE_IN_OWNED_DIRECTORY');return names

    def verify_media(self,label):
        need(self.media is not None,'OWNED_MEDIA_REQUIRED');uri=self.media['uri']
        match=re.fullmatch(r'content://media/external_primary/images/media/(\d+)',uri)
        need(match and int(match[1])>0,'EXACT_MEDIA_URI')
        rows=self.namespace(label);image=[r for r in rows if r['_id']==int(match[1])]
        need(len(image)==1,'EXACT_GLOBAL_MEDIA_ROW');row=image[0]
        need(row['_data']==GUEST_FILE and row['_display_name']==NAME and row['relative_path']==RELATIVE
            and row['owner_package_name']==PACKAGE and row['media_type']==1 and row['mime_type']=='image/png'
            and row['_size']==self.media['bytes'] and row['width']==640 and row['height']==480
            and row['is_pending']==0,'GLOBAL_MEDIA_INDEX_FIELDS_DIFFER')
        for other in rows:
            if other is row:continue
            need(other['_data']==GUEST_FOLDER and other['_display_name']==FOLDER and other['media_type']==0,
                'UNEXPECTED_OWNED_NAMESPACE_ROW')
        need(self.held_folder()==[NAME],'EXACT_PHYSICAL_MEDIA_REQUIRED')
        fd=os.open(NAME,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=self.folder_fd)
        try:
            before=os.fstat(fd);need(stat.S_ISREG(before.st_mode) and before.st_nlink==1
                and before.st_size==self.media['bytes']<4*1024*1024,'OWNED_FILE_TYPE_SIZE')
            data=b''
            while True:
                chunk=os.read(fd,65536)
                if not chunk:break
                data+=chunk;need(len(data)<=4*1024*1024,'FILE_READ_BOUND')
            after=os.fstat(fd);need(fp(before)==fp(after) and before.st_mtime_ns==after.st_mtime_ns
                and before.st_ctime_ns==after.st_ctime_ns and sha(data)==self.media['sha256'],'OWNED_FILE_BYTES_CHANGED')
        finally:os.close(fd)
        need(self.original_media(label+'-original')==self.original_rows,'PREEXISTING_MEDIA_METADATA_CHANGED')
        self.record(label+'-joined-proof',{'uri':uri,'file_sha256':sha(data),'file_bytes':len(data),
            'file_identity':fp(before),'folder_identity':self.folder_birth,'global_index':row,
            'original_image_video_metadata_preserved':True})
        return row

    def launch_image(self,index):
        need(self.pending is None,'PENDING_EFFECT');self.pending='native-launch-'+str(index)
        self.ui.launch();task=self.ui.owned[0];self.native_launches.append(task);self.pending=None
        focus=self.ui.ready_focus(False)
        need(focus['package']==GALLERY and focus['activity']==GALLERY+'.app.GalleryActivity','GALLERY_FOCUS_ROUTE')
        self.verify_media('before-view-'+str(index));self.ui.ready_focus(False)
        argv=['/system/bin/am','start-activity','-W','--user','0','--display','0','--task',str(task),
            '--activity-clear-top','-a','android.intent.action.VIEW','-d',self.media['uri'],'-t','image/png','-n',COMPONENT]
        self.record('view-intent-'+str(index),{'argv':argv,'owned_task':task,'automatic_retry':False,
            'exact_media_row_verified':True,'task_option_proof_sha256':TASK_PROOF_SHA})
        self.pending='view-image-'+str(index);self.intent_calls+=1
        raw=self.s.android(argv,35).decode();self.record('view-result-'+str(index),{'stdout':raw})
        need(re.findall(r'^Status:\s*(\S+)',raw,re.M)==['ok'] and 'Error:' not in raw and 'Exception' not in raw,'VIEW_INTENT_UNKNOWN')
        focus=self.ui.ready_focus(False);need(self.ui.owned[0]==task and focus['activity']==GALLERY+'.app.GalleryActivity','VIEW_TASK_OR_ACTIVITY_CHANGED')
        self.pending=None
        self.ui.observe('image-native-'+str(index),focus)
        proofs=[]
        for sample in range(2):
            focus=self.ui.ready_focus(False)
            capture=self.s.helper.capture({'package':GALLERY,'display':0,'accessibility_mode':'none','window_token':focus['window_token']})
            proof=self.pattern.verify_pattern(capture['image'])
            buffer=io.BytesIO();capture['image'].save(buffer,format='PNG');png=buffer.getvalue()
            self.tx.write_new(ROOT/('owned-image-%d-%d.png'%(index,sample)),png)
            proof.update(snapshot=capture['meta'],png_sha256=sha(png));self.record('pattern-%d-%d'%(index,sample),proof);proofs.append(proof)
            if sample==0:time.sleep(.3)
        self.verify_media('after-view-'+str(index))
        self.close()
        value=self.instrument('verify');need(value['image']['sha256']==self.media['sha256'],'REOPEN_BYTES_CHANGED')
        self.result['rounds'].append({'task':task,'normal_close_verified':True,'pattern_frames':proofs,
            'media_sha256':self.media['sha256'],'index_fields_verified':True})

    def close(self):
        need(self.close_pending is None,'OWNED_CLOSE_OUTCOME_PENDING_NO_REPLAY')
        if self.ui.owned is None:return
        task=self.ui.owned[0];before=self.ui.removals
        self.close_pending={'task':task,'automatic_retry':False}
        self.ui.close()
        need(self.ui.removals==before+1 and self.ui.result.get('other_tasks_preserved') is True,'NORMAL_CLOSE_UNVERIFIED')
        self.closed.append(task);self.close_pending=None

    def clean_folder(self):
        need(self.pending is None and self.media is not None,'NO_UNKNOWN_MEDIA_CLEANUP')
        need(self.held_folder()==[],'IMAGE_FILE_NOT_ABSENT')
        rows=self.namespace('after-image-delete')
        if rows:
            need(len(rows)==1 and rows[0]['_data']==GUEST_FOLDER and rows[0]['_display_name']==FOLDER
                and rows[0]['media_type']==0,'UNEXPECTED_REMAINING_MEDIA_ROW')
            # No guessed directory-provider operation: retain a precise indexed
            # directory if this platform requires an additional public-API step.
            self.result['owned_directory_index_retained']=rows[0]
            raise RuntimeError('OWNED_EMPTY_DIRECTORY_INDEX_REQUIRES_RECONCILIATION')
        os.rmdir(FOLDER,dir_fd=self.folder_parent)
        try:os.stat(FOLDER,dir_fd=self.folder_parent,follow_symlinks=False)
        except FileNotFoundError:pass
        else:raise RuntimeError('DIRECTORY_REMOVAL_NOT_VERIFIED')
        need(self.namespace('namespace-clean')==[],'OWNED_MEDIA_INDEX_NOT_EMPTY')
        self.result['owned_directory_removed']=True

    def cleanup(self):
        result={'errors':[],'package_absent':False,'staged_apk_removed':False,'image_deleted':False}
        try:self.close()
        except BaseException as e:result['errors'].append('close:'+type(e).__name__+':'+str(e))
        try:
            need(self.pending is None and self.close_pending is None and not self.install_pending
                and not self.uninstall_pending,'UNKNOWN_EFFECT_PRESERVE_FIXTURE')
            if self.installed is not None:
                saved=self.prefs()
                if saved and saved.get('phase')=='SEEDED' and saved.get('pending')=='':
                    need(self.media is not None,'SEED_OUTCOME_NOT_JOINED');self.verify_media('before-delete')
                    self.instrument('delete');saved=self.prefs()
                if saved:
                    need(saved.get('phase')=='DELETED' and saved.get('pending')=='','MEDIA_EFFECT_NOT_RESOLVED')
                    result['image_deleted']=True;self.clean_folder()
                else:need(self.namespace('no-seed-cleanup')==[],'UNEXPECTED_MEDIA_WITHOUT_RECORD')
                need(self.ui.owned is None and self.doc.identity(self.s,PACKAGE,APK_SHA)==self.installed,'UNINSTALL_IDENTITY_OR_TASK_CHANGED')
                self.record('exact-fixture-uninstall-intent',{'package':PACKAGE,'identity':self.installed,'automatic_retry':False})
                self.uninstall_pending=True
                raw=self.s.android(['/system/bin/pm','uninstall',PACKAGE],60).decode();need(raw.strip()=='Success','UNINSTALL_UNKNOWN')
                self.doc.absent(self.s);self.uninstall_pending=False;result['package_absent']=True
            else:self.doc.absent(self.s);result['package_absent']=True
        except BaseException as e:result['errors'].append('fixture:'+type(e).__name__+':'+str(e))
        try:
            if self.staged is not None and not self.install_pending:
                x=self.staged;name=Path(x['guest']).name
                need(name=='owned-saf.apk' and self.doc.fp(os.fstat(x['directory']))==x['birth'],'STAGE_DIRECTORY_SCOPE')
                need(self.doc.fp(os.stat(x['name'],dir_fd=x['parent'],follow_symlinks=False))==x['birth'],'STAGE_DIRECTORY_REPLACED')
                need(os.listdir(x['directory'])==[name] and self.doc.fp(os.stat(name,dir_fd=x['directory'],follow_symlinks=False))==x['file_identity'],'STAGE_FILE_SCOPE')
                raw,_=self.s.target.read_file(x['guest'],1048576,single_link=True);need(sha(raw)==APK_SHA,'STAGED_APK_CHANGED')
                os.unlink(name,dir_fd=x['directory']);os.rmdir(x['name'],dir_fd=x['parent']);result['staged_apk_removed']=True
        except BaseException as e:result['errors'].append('stage:'+type(e).__name__+':'+str(e))
        finally:
            if self.staged is not None:os.close(self.staged['directory']);os.close(self.staged['parent'])
            if self.folder_fd is not None:os.close(self.folder_fd)
            if self.folder_parent is not None:os.close(self.folder_parent)
        return result

