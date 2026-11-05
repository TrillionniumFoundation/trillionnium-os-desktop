#!/usr/bin/python3 -I
"""Owned silent video: real pixels, native pause/resume, normal reopen, exact cleanup."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, io, json, os, re, signal, stat, sys, time, types
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
ROOT=Path('/home/alex/work/pocket4-gallery-video-flow-20261105-r12-01')
BASE=Path('/home/alex/work/pocket4-gallery-tools-20261105-r12-01/run_gallery01.py')
BASE_SHA='1373820f8c1a39203bb764d3b5f5859b1ef91387cc4b04fb564d4d4d3cd7f40e'
CODE=Path('/home/alex/work/pocket4-gallery-movie-source-20261105-r12-01/result.json')
CODE_SHA='9d655713eb1201f3d4accbe295d8f47b80cc6eaca14e202f53d5b1b29cb05cf2'
RUN='c92c3d79180955ef';PACKAGE='org.droidloom.qa.media.r12.n'+RUN
FOLDER='Pocket4_Gallery_r12_'+RUN;NAME='pocket4-pattern-'+RUN+'.mp4'
RELATIVE='DCIM/'+FOLDER+'/';GUEST_FOLDER='/storage/emulated/0/DCIM/'+FOLDER;GUEST_FILE=GUEST_FOLDER+'/'+NAME
GALLERY='com.android.gallery3d';MAIN=GALLERY+'.app.GalleryActivity';MOVIE=GALLERY+'.app.MovieActivity'
VIDEO_SHA='eaeb797bff8f610373204451f5885dcba2fb1ffa2530410468b7dc480d5588da'
PINS={'package_fixture.py':'5cb30798c5ce70e5dd56175e7a7d4382908086f30c3cbeda16b6dc10c18ab068',
      'runtime_evidence.py':'3b68854c19037f50eef9f0fc5e462372c2f1e05914382c9d752776fc8e027629',
      'verify_pattern.py':'0206850626989ddd3a52693252d211dbd5e03addfe86332190da8ca1cb6951e9',
      'verify_video.py':'2b52f1514fff4507a9618ac5695d0dd64820f2e34f9c242cb5d640f6c79fe93d'}
WORK_SECONDS=600;CLEANUP_SECONDS=120;MAX_INPUTS=12
PLAY_LABELS={'Play','Play video','播放','播放视频'}
PAUSE_LABELS={'Pause','Pause video','暂停','暂停视频'}

def need(ok, why):
    if not ok: raise RuntimeError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def stamp():return datetime.now(timezone.utc).isoformat()
def load(path,pin,name):
    raw=path.read_bytes();need(sha(raw)==pin,'SOURCE_CHANGED:'+name)
    module=types.ModuleType(name);module.__file__=str(path);exec(compile(raw,str(path),'exec'),module.__dict__);return module
def expand(activity):return GALLERY+activity if activity.startswith('.') else activity
def expired(*unused):raise TimeoutError('GALLERY_VIDEO_DEADLINE_NO_REPLAY')

class PackageUI:
    def __init__(self,flow):self.flow=flow
    def record(self,label,value):self.flow.record(label,value)
    @property
    def owned(self):return self.flow.ui.owned
    @property
    def pending(self):
        return {'effect':self.flow.pending,'close':self.flow.close_pending} if self.flow.pending or self.flow.close_pending else {}

def make_class(base):
    class VideoFlow(base.Gallery):
        def __init__(self,s,tx,ui,doc,diag,pattern,video,pkg,runtime):
            super().__init__(s,tx,ui,doc,diag,pattern)
            self.video=video;self.pkg_module=pkg;self.fixture=pkg.PackageFixture(s,tx,PackageUI(self),self.result)
            self.runtime_module=runtime;self.runtime=None;self.inputs=0;self.directory_row=None
            self.last_video_proof=None
            self.result.update(schema='pocket4-gallery-video-flow-v1',run=RUN,temporary_package=PACKAGE,
                max_seconds=WORK_SECONDS,cleanup_seconds=CLEANUP_SECONDS,media_kind='video',audio_track_count=0,
                audio_output_qualified=False,seek_qualified=False,album_enumeration_qualified=False,
                movie_source_receipt_sha256=CODE_SHA,inputs=[],pixel_rounds=[])

        def setup(self):
            self.result['guard_before']=self.s.guard();self.result['gallery_before']=self.gallery_identity()
            need(any(line.startswith('android.permission.READ_MEDIA_VIDEO: granted=true,')
                for line in self.result['gallery_before']['permissions']),'GALLERY_VIDEO_PERMISSION_NOT_GRANTED')
            self.original_rows=self.original_media('original-before')
            need(self.namespace('namespace-before')==[],'GLOBAL_MEDIA_NAMESPACE_NOT_ABSENT')
            self.folder_parent=self.s.target.open_root('/storage/emulated/0/DCIM',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:os.stat(FOLDER,dir_fd=self.folder_parent,follow_symlinks=False)
            except FileNotFoundError:pass
            else:raise RuntimeError('OWNED_FOLDER_ALREADY_EXISTS')
            self.before_diag=self.diagnostics.diagnostics('before',10064)
            self.fixture.install();self.installed=self.fixture.installed
            self.record('global-owned-namespace-absent',{'global_media_rows':0,'physical_directory_absent':True})
            self.runtime=self.runtime_module.RuntimeEvidence(self.s,self.tx,ROOT/'runtime-private',FOLDER)
            self.runtime.start()

        def prefs(self):
            path='/data/user/0/'+PACKAGE+'/shared_prefs/owned-media-'+RUN+'-video.xml'
            try:raw,_=self.s.target.read_file(path,16384,single_link=True)
            except FileNotFoundError:return None
            root=ET.fromstring(raw);need(root.tag=='map','OWNED_PREFS_SCHEMA');value={}
            for item in root:
                key=item.get('name');need(key and key not in value,'OWNED_PREFS_DUPLICATE')
                if item.tag=='string':value[key]=item.text or ''
                elif item.tag in ('int','long'):value[key]=int(item.get('value'))
                else:raise RuntimeError('OWNED_PREFS_TYPE')
            need(value.get('run')==RUN,'OWNED_PREFS_RUN');return value

        def instrument(self,op):
            need(op in ('seed','verify','delete') and self.pending is None,'INSTRUMENT_SCOPE_OR_PENDING')
            need(len(self.instrument_calls)<5,'INSTRUMENT_CALL_LIMIT')
            need(self.pkg_module.identity(self.s,PACKAGE,self.pkg_module.APK_SHA)==self.installed,'HELPER_IDENTITY_CHANGED')
            token='video-'+op+'-'+str(len(self.instrument_calls))
            argv=['/system/bin/am','instrument','-w','-r','-e','run',RUN,'-e','media','video','-e','op',op,PACKAGE+'/.MediaFixture']
            self.record(token+'-intent',{'argv':argv,'automatic_retry':False,'mutating':op in ('seed','delete')})
            self.pending=token;self.instrument_calls.append(op)
            raw=self.s.android(argv,55).decode();self.record(token+'-receipt',{'stdout':raw})
            values=re.findall(r'^INSTRUMENTATION_RESULT: result_json=(.+)$',raw,re.M)
            codes=re.findall(r'^INSTRUMENTATION_CODE: (-?\d+)\s*$',raw,re.M)
            need(len(values)==1 and codes==['0'],'INSTRUMENT_TERMINAL_NOT_SUCCESS')
            value=json.loads(values[0]);phase='DELETED' if op=='delete' else 'SEEDED'
            need(value.get('ok') is True and value.get('package')==PACKAGE and value.get('run')==RUN
                and value.get('uid')==self.installed['uid'] and value.get('operation')==op and value.get('media_kind')=='video',
                'INSTRUMENT_RESULT_IDENTITY')
            need(value.get('phase')==phase and value.get('pending')=='' and value.get('insert_calls')==1
                and value.get('write_calls')==1 and value.get('publish_calls')==1
                and value.get('delete_calls')==(1 if op=='delete' else 0),'INSTRUMENT_EFFECT_NOT_JOINED')
            saved=self.prefs();need(saved and saved.get('phase')==phase and saved.get('pending')=='','OWNED_PREFS_READBACK')
            media=value['media'];need(media['sha256']==VIDEO_SHA and media['bytes']==123394
                and media['media_kind']=='video' and media['duration_ms']==60000
                and media['video_frame_samples_verified'] is True,'VIDEO_FIXTURE_PROVENANCE_CHANGED')
            self.pending=None;self.result['media_operations'].append(value);return value

        def verify_media(self,label):
            need(self.media is not None,'OWNED_MEDIA_REQUIRED')
            match=re.fullmatch(r'content://media/external_primary/video/media/(\d+)',self.media['uri'])
            need(match and int(match[1])>0,'EXACT_VIDEO_URI')
            rows=self.namespace(label);videos=[r for r in rows if r['_id']==int(match[1])]
            need(len(videos)==1,'EXACT_GLOBAL_VIDEO_ROW');row=videos[0]
            need(row['_data']==GUEST_FILE and row['_display_name']==NAME and row['relative_path']==RELATIVE
                and row['owner_package_name']==PACKAGE and row['media_type']==3 and row['mime_type']=='video/mp4'
                and row['_size']==123394 and row['width']==640 and row['height']==480 and row['is_pending']==0,
                'GLOBAL_VIDEO_INDEX_FIELDS_DIFFER')
            others=[r for r in rows if r is not row];need(len(others)<=1,'EXTRA_NAMESPACE_ROWS')
            if others:
                directory=others[0]
                need(directory['_id']>0 and directory['_data']==GUEST_FOLDER and directory['_display_name']==FOLDER
                    and directory['relative_path']=='DCIM/' and directory['media_type']==0
                    and directory['is_pending']==0 and directory['owner_package_name'] is None,'DIRECTORY_ROW_SCOPE')
                if self.directory_row is None:self.directory_row=directory
                else:need(directory==self.directory_row,'OWNED_DIRECTORY_INDEX_CHANGED')
            need(self.held_folder()==[NAME],'EXACT_PHYSICAL_VIDEO_REQUIRED')
            fd=os.open(NAME,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=self.folder_fd)
            try:
                before=os.fstat(fd);need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size==123394,'VIDEO_FILE_SCOPE')
                data=b''
                while len(data)<123395:
                    chunk=os.read(fd,123395-len(data))
                    if not chunk:break
                    data+=chunk
                after=os.fstat(fd)
                need(len(data)==123394 and sha(data)==VIDEO_SHA and base.fp(before)==base.fp(after)
                    and before.st_mtime_ns==after.st_mtime_ns and before.st_ctime_ns==after.st_ctime_ns,'VIDEO_BYTES_CHANGED')
            finally:os.close(fd)
            need(self.original_media(label+'-original')==self.original_rows,'PREEXISTING_MEDIA_CHANGED')
            self.record(label+'-joined-proof',{'uri':self.media['uri'],'file_sha256':sha(data),'file_bytes':len(data),
                'file_identity':base.fp(before),'folder_identity':self.folder_birth,'global_index':row,
                'original_image_video_metadata_preserved':True});return row

        def movie_focus(self):
            focus=self.ui.ready_focus(False)
            need(focus['package']==GALLERY and expand(focus['activity'])==MOVIE
                and expand(focus['focused_activity'])==MOVIE,'EXACT_MOVIE_FOCUS_REQUIRED')
            return focus

        def capture_frame(self,label,pattern=True):
            focus=self.movie_focus();start=time.monotonic()
            capture=self.s.helper.capture({'package':GALLERY,'display':0,'accessibility_mode':'none','window_token':focus['window_token']})
            end=time.monotonic();need(self.movie_focus()==focus,'MOVIE_FOCUS_CHANGED_DURING_CAPTURE')
            buffer=io.BytesIO();capture['image'].save(buffer,format='PNG');raw=buffer.getvalue()
            self.tx.write_new(ROOT/(label+'.png'),raw)
            value={'monotonic_sample_midpoint':(start+end)/2,'capture_seconds':end-start,
                'png_sha256':sha(raw),'pixel_sha256':sha(capture['image'].convert('RGB').tobytes()),
                'image_size':list(capture['image'].size),'snapshot':capture['meta']}
            if pattern:value['pattern']=self.video.verify_video_frame(capture['image']);self.last_video_proof=value
            self.record(label,value);return value

        def advancing(self,label):
            # Controls auto-hide after playback starts. This is a bounded wait,
            # not an input retry or an inference that playback succeeded.
            time.sleep(3.3)
            before=self.capture_frame(label+'-a');time.sleep(3)
            after=self.capture_frame(label+'-b')
            proof=self.video.verify_advancing(before['pattern'],after['pattern'],
                after['monotonic_sample_midpoint']-before['monotonic_sample_midpoint'])
            self.record(label+'-advance',proof);return {'before':before,'after':after,**proof}

        def observe_movie(self,label):
            focus=self.movie_focus();nodes=self.ui.observe(label,focus)
            return focus,[n for n in nodes if n.get('package')==GALLERY and n.get('visible') is True],self.ui.last_observation['screenshot']

        @staticmethod
        def control(nodes,labels):
            matches=[n for n in nodes if n.get('package')==GALLERY and n.get('visible') is True
                and n.get('class')=='android.widget.ImageView' and n.get('content-desc') in labels
                and n.get('enabled') is True and n.get('clickable') is True]
            need(len(matches)<=1,'PLAYBACK_CONTROL_AMBIGUOUS');return matches[0] if matches else None

        def ensure_controls(self):
            for decision in range(3):
                focus,nodes,shot=self.observe_movie('pause-control-observation-'+str(decision))
                button=self.control(nodes,PAUSE_LABELS)
                if button:return focus,button
                need(self.control(nodes,PLAY_LABELS) is None,'VIDEO_ALREADY_PAUSED_BEFORE_PAUSE_TEST')
                views=[n for n in nodes if n.get('class')=='android.widget.VideoView' and n.get('enabled') is True]
                need(len(views)==1,'OBSERVED_VIDEO_VIEW_REQUIRED_TO_SHOW_CONTROLS')
                bounds=views[0].get('bounds_array');scope=shot['scope_bounds']
                need(isinstance(bounds,list) and len(bounds)==4 and all(type(v) is int for v in bounds)
                    and scope[0]<=bounds[0]<bounds[2]<=scope[2] and scope[1]<=bounds[1]<bounds[3]<=scope[3],
                    'VIDEO_VIEW_NOT_FULLY_WITHIN_OWNED_WINDOW')
                point=[(3*bounds[0]+bounds[2])//4,(3*bounds[1]+bounds[3])//4]
                request={'op':'snapshot-tap','package':GALLERY,'display':0,'accessibility_mode':'none',
                    'window_token':focus['window_token'],'coords':point,'input_source':'touch',
                    **{key:shot[key] for key in ('frame_sha256','scope_sha256','context_token')}}
                need(self.pending is None and self.inputs<MAX_INPUTS and self.movie_focus()==focus,'INPUT_SCOPE_OR_BUDGET')
                token='show-controls-'+str(decision);self.record(token+'-intent',{'request':request,'observed_video_view':views[0],
                    'source_bound_to':'MovieControllerOverlay.onTouchEvent hidden -> show','automatic_retry':False})
                self.pending=token;self.inputs+=1
                try:reply=self.s.helper.dispatch(request)
                except BaseException as exc:
                    details=getattr(exc,'details',{})
                    if str(exc)=='STALE_FRAME' and details.get('action_taken') is False and details.get('outcome_unknown') is not True:
                        self.record(token+'-explicit-no-effect',{'error':str(exc),'details':details});self.pending=None;continue
                    raise
                self.record(token+'-receipt',reply)
                need(reply.get('ok') is True and reply.get('input_command_completed') is True,'SHOW_CONTROLS_INPUT_UNKNOWN')
                current,fresh,_=self.observe_movie(token+'-post')
                button=self.control(fresh,PAUSE_LABELS);need(current==focus and button is not None,'PLAYING_CONTROL_NOT_OBSERVED_AFTER_SHOW')
                self.pending=None;return current,button
            raise RuntimeError('SHOW_CONTROLS_FRESH_DECISION_LIMIT')

        def click_control(self,label,focus,button,expected_labels):
            need(self.pending is None and self.inputs<MAX_INPUTS and self.movie_focus()==focus,'PLAYBACK_CLICK_SCOPE')
            selector={'package':GALLERY,'class':'android.widget.ImageView','desc':button['content-desc'],'clickable':True,'enabled':True}
            request={'op':'click','package':GALLERY,'display':0,'window_token':focus['window_token'],
                'accessibility_mode':'none','method':'accessibility','selector':selector}
            self.record(label+'-intent',{'request':request,'observed_control':button,'automatic_retry':False})
            self.pending=label;self.inputs+=1
            try:reply=self.s.helper.dispatch(request)
            except BaseException as exc:
                details=getattr(exc,'details',{})
                if details.get('outcome_unknown') is not True and (details.get('action_taken') is False
                    or details.get('outcome_unknown') is False):
                    self.record(label+'-explicit-no-effect',{'error':str(exc),'details':details});self.pending=None
                raise
            self.record(label+'-receipt',reply)
            target=reply.get('actual_target',{})
            need(reply.get('ok') is True and reply.get('performed')=='click'
                and reply.get('accessibility_mode_restoration_verified') is True
                and target.get('package')==GALLERY and target.get('class')=='android.widget.ImageView'
                and target.get('content-desc')==button['content-desc'],'PLAYBACK_CLICK_NOT_JOINED')
            current,nodes,_=self.observe_movie(label+'-post');next_control=self.control(nodes,expected_labels)
            need(current==focus and next_control is not None,'PLAYBACK_STATE_CONTROL_NOT_CHANGED')
            self.pending=None;self.result['inputs'].append({'label':label,'before':button['content-desc'],
                'after':next_control['content-desc'],'actual_target':target,'owned_task':focus['task']})
            return current,next_control

        def video_round(self,index):
            need(self.pending is None,'PENDING_VIDEO_ROUND');self.runtime.phase_changed('round-'+str(index)+'-launch')
            self.pending='native-launch-'+str(index);self.ui.launch();task=self.ui.owned[0]
            self.native_launches.append(task);self.pending=None
            focus=self.ui.ready_focus(False);need(expand(focus['activity'])==MAIN,'GALLERY_MAIN_FOCUS')
            self.verify_media('round-'+str(index)+'-before-view')
            argv=['/system/bin/am','start-activity','-W','--user','0','--display','0','--task',str(task),
                '--activity-clear-top','-a','android.intent.action.VIEW','-d',self.media['uri'],'-t','video/mp4',
                '--ez','android.intent.extra.finishOnCompletion','false','-n',GALLERY+'/.app.MovieActivity']
            self.record('movie-view-'+str(index)+'-intent',{'argv':argv,'task':task,'automatic_retry':False,
                'intent_extra_source_receipt_sha256':CODE_SHA,'task_option_proof_sha256':base.TASK_PROOF_SHA})
            self.pending='movie-view-'+str(index);self.intent_calls+=1
            raw=self.s.android(argv,35).decode();self.record('movie-view-'+str(index)+'-receipt',{'stdout':raw})
            need(re.findall(r'^Status:\s*(\S+)',raw,re.M)==['ok'] and 'Error:' not in raw and 'Exception' not in raw,'MOVIE_VIEW_OUTCOME_UNKNOWN')
            need(self.movie_focus()['task']==task,'MOVIE_TASK_CHANGED');self.pending=None
            self.runtime.phase_changed('round-'+str(index)+'-playback')
            entry={'task':task,'index':index,'initial_playback':self.advancing('round-'+str(index)+'-playing')}
            if index==0:
                need(entry['initial_playback']['after']['pattern']['visual_second_code']<40,'TOO_CLOSE_TO_CLIP_END_FOR_PAUSE')
                focus,button=self.ensure_controls();focus,button=self.click_control('pause',focus,button,PLAY_LABELS)
                self.runtime.phase_changed('paused');time.sleep(.6)
                first=self.capture_frame('paused-a',False);time.sleep(3);second=self.capture_frame('paused-b',False)
                elapsed=second['monotonic_sample_midpoint']-first['monotonic_sample_midpoint']
                need(2.5<=elapsed<=12 and first['image_size']==second['image_size']
                    and first['pixel_sha256']==second['pixel_sha256'],'PAUSED_APPLICATION_PIXELS_NOT_STABLE')
                focus,nodes,_=self.observe_movie('paused-state-after-interval');button=self.control(nodes,PLAY_LABELS)
                need(button is not None,'PAUSED_CONTROL_NOT_PRESERVED')
                entry['pause']={'before':first,'after':second,'elapsed_seconds':elapsed,
                    'exact_application_pixels_stable':True,'playing_to_paused_control_verified':True,
                    'last_moving_second':entry['initial_playback']['after']['pattern']['visual_second_code'],
                    'paused_timecode_decode_claimed':False}
                self.click_control('resume',focus,button,PAUSE_LABELS);self.runtime.phase_changed('resumed')
                entry['resume']=self.advancing('resumed')
            self.verify_media('round-'+str(index)+'-after-view');self.close()
            checked=self.instrument('verify');need(checked['media']['sha256']==self.media['sha256'],'REOPEN_MEDIA_CHANGED')
            entry['normal_close_verified']=True;self.result['pixel_rounds'].append(entry)

        def clean_folder(self):
            need(self.pending is None and self.held_folder()==[],'OWNED_DIRECTORY_NOT_EMPTY_OR_PENDING')
            rows=self.namespace('after-video-delete')
            if rows:
                need(self.directory_row is not None and rows==[self.directory_row],'ONLY_OWNED_DIRECTORY_INDEX_MAY_REMAIN')
                row=self.directory_row;identity=row['_id']
                need(self.query('directory-children','SELECT _id FROM files WHERE parent='+str(identity)+
                    " OR _data GLOB '"+GUEST_FOLDER+"/*' ORDER BY _id")==[],'DIRECTORY_CHILD_ROW_PRESENT')
                predicate='_id='+str(identity)+" AND _data='"+GUEST_FOLDER+"' AND _display_name='"+FOLDER+"' AND relative_path='DCIM/' AND media_type=0 AND is_pending=0 AND owner_package_name IS NULL"
                argv=['/system/bin/content','delete','--user','0','--uri','content://media/external_primary/file/'+str(identity),'--where',predicate]
                self.record('owned-directory-delete-intent',{'argv':argv,'exact_row':row,'physical_entries':[],
                    'directory_identity':self.folder_birth,'automatic_retry':False,'App_delete_qualification':False})
                self.pending='delete-owned-directory-index';self.result['directory_provider_delete_calls']=1
                raw=self.s.android(argv,25).decode();self.record('directory-delete-receipt',{'stdout':raw})
                # Actual prior Gallery cleanup03 returned rc0 with an empty
                # stdout. Independent provider/physical readback resolved it.
                need(raw.strip()=='' or re.fullmatch(r'Deleted 1 rows\.?',raw.strip()),'DIRECTORY_DELETE_OUTPUT_UNKNOWN')
                need(self.namespace('after-directory-delete')==[],'OWNED_DIRECTORY_INDEX_NOT_ABSENT')
                self.pending=None
            try:os.stat(FOLDER,dir_fd=self.folder_parent,follow_symlinks=False)
            except FileNotFoundError:pass
            else:
                need(self.held_folder()==[],'PHYSICAL_DIRECTORY_CHANGED_AFTER_DELETE')
                self.record('owned-empty-rmdir-intent',{'name':FOLDER,'birth':self.folder_birth,'automatic_retry':False})
                self.pending='remove-owned-empty-directory';os.rmdir(FOLDER,dir_fd=self.folder_parent)
                try:os.stat(FOLDER,dir_fd=self.folder_parent,follow_symlinks=False)
                except FileNotFoundError:self.pending=None
                else:raise RuntimeError('OWNED_DIRECTORY_REMOVAL_UNKNOWN')
            need(self.namespace('namespace-clean')==[],'OWNED_MEDIA_NAMESPACE_NOT_EMPTY')
            self.result['owned_directory_removed']=True

        def cleanup(self):
            out={'errors':[],'video_deleted':False,'package_absent':False,'staged_apk_removed':False}
            if self.runtime is not None:
                try:self.result['runtime_evidence']=self.runtime.stop()
                except BaseException as e:out['errors'].append('runtime:'+type(e).__name__+':'+str(e))
            try:
                need(self.pending is None and self.close_pending is None,'UNKNOWN_UI_OR_MEDIA_EFFECT_NO_CLEANUP')
                self.close()
                need(not self.fixture.install_pending and not self.fixture.uninstall_pending,'UNKNOWN_PACKAGE_EFFECT')
                if self.installed is not None:
                    saved=self.prefs()
                    if saved:
                        need(saved.get('phase') in ('SEEDED','DELETED') and saved.get('pending')=='','OWNED_MEDIA_EFFECT_PENDING')
                        if saved['phase']=='SEEDED':
                            self.verify_media('before-delete');self.instrument('delete')
                        need(self.prefs().get('phase')=='DELETED' and self.prefs().get('pending')=='','DELETE_NOT_VERIFIED')
                        out['video_deleted']=True;self.clean_folder()
                    else:
                        need(self.namespace('no-seed-cleanup')==[],'MEDIA_WITHOUT_OWNED_RECORD')
                        try:os.stat(FOLDER,dir_fd=self.folder_parent,follow_symlinks=False)
                        except FileNotFoundError:pass
                        else:raise RuntimeError('PHYSICAL_MEDIA_WITHOUT_OWNED_RECORD')
                package=self.fixture.uninstall(no_pending_effects=self.pending is None and self.close_pending is None)
                out['package_absent']=package['package_absent_verified'];out['package_cleanup']=package
            except BaseException as e:out['errors'].append('fixture:'+type(e).__name__+':'+str(e))
            try:
                stage=self.fixture.cleanup_staged();out['staging_cleanup']=stage
                out['staged_apk_removed']=stage.get('staged_apk_removed',stage.get('staged_apk_created') is False)
            except BaseException as e:out['errors'].append('stage:'+type(e).__name__+':'+str(e))
            finally:
                for fd in (self.folder_fd,self.folder_parent):
                    if fd is not None:os.close(fd)
                self.folder_fd=self.folder_parent=None
            return out
    return VideoFlow

def execute():
    base=load(BASE,BASE_SHA,'gallery_video_previous_image_controller')
    tx,ui,doc,diag=[load(Path(path),pin,'gallery_video_dependency_'+str(i)) for i,(path,pin) in enumerate(base.PINS.items())]
    pattern=load(HERE/'verify_pattern.py',PINS['verify_pattern.py'],'verify_pattern');sys.modules['verify_pattern']=pattern
    video=load(HERE/'verify_video.py',PINS['verify_video.py'],'video_validator')
    pkg=load(HERE/'package_fixture.py',PINS['package_fixture.py'],'gallery_video_package')
    runtime=load(HERE/'runtime_evidence.py',PINS['runtime_evidence.py'],'gallery_video_runtime')
    source=json.loads(tx.read_regular(CODE,CODE_SHA,262144))
    need(source['state']=='INSTALLED_MOVIE_CODE_INSPECTED' and source['apk']['sha256']==base.GALLERY_SHA,'MOVIE_SOURCE_BINDING_CHANGED')
    need(sha(base.TASK_PROOF.read_bytes())==base.TASK_PROOF_SHA,'TASK_ROUTING_PROOF_CHANGED')
    for key,value in {'ROOT':ROOT,'RUN':RUN,'PACKAGE':PACKAGE,'FOLDER':FOLDER,'NAME':NAME,'RELATIVE':RELATIVE,
        'GUEST_FOLDER':GUEST_FOLDER,'GUEST_FILE':GUEST_FILE,'APK':pkg.APK,'APK_SHA':pkg.APK_SHA,'CERT_SHA':pkg.CERT_SHA}.items():setattr(base,key,value)
    ui.ROOT=ROOT/'ui';ui.PACKAGE=GALLERY;ui.COMPONENT=GALLERY+'/.app.GalleryActivity';diag.PACKAGE=GALLERY
    result={'state':'FAILED','whole_app_production_ready':False};flow=None;previous=signal.signal(signal.SIGALRM,expired)
    try:
        with tx.ui_lock():
            ROOT.mkdir(mode=0o750);os.chown(ROOT,0,1000);os.chmod(ROOT,0o750);(ROOT/'ui').mkdir(mode=0o700)
            signal.setitimer(signal.ITIMER_REAL,WORK_SECONDS)
            with tx.CameraSession(ROOT/'commands') as session:
                flow=make_class(base)(session,tx,ui,doc,diag,pattern,video,pkg,runtime);result=flow.result
                try:
                    flow.setup();flow.media=flow.instrument('seed')['media'];flow.verify_media('after-seed')
                    for index in range(2):flow.video_round(index)
                    after=flow.diagnostics.diagnostics('after',10064)
                    result['diagnostics']=diag.fresh_crashes(flow.before_diag,after,10064,flow.before_diag['guest_seconds'])
                    need(result['diagnostics']['clear'],'FRESH_GALLERY_CRASH_OR_ANR')
                    result['gallery_after']=flow.gallery_identity();need(result['gallery_after']==result['gallery_before'],'GALLERY_IDENTITY_CHANGED')
                    result['business_scope_completed']=True
                except BaseException as e:result['error']=type(e).__name__+':'+str(e)
                finally:
                    signal.setitimer(signal.ITIMER_REAL,CLEANUP_SECONDS);result['cleanup']=flow.cleanup()
                    try:
                        result['guard_after']=session.guard()
                        if hasattr(flow,'original_rows'):result['original_media_preserved']=flow.original_media('original-final')==flow.original_rows
                        session.caller_status('gallery-video-final')
                    except BaseException as e:result['final_check_error']=type(e).__name__+':'+str(e)
                    result.update(owned_tasks=flow.native_launches,normal_closed_tasks=flow.closed,pending_effect=flow.pending,
                        close_pending=flow.close_pending,install_pending=flow.fixture.install_pending,
                        uninstall_pending=flow.fixture.uninstall_pending,instrument_calls=flow.instrument_calls,
                        view_intent_calls=flow.intent_calls,ui_input_decisions=flow.inputs)
                    if (result.get('business_scope_completed') and not result['cleanup']['errors']
                        and result.get('guard_before')==result.get('guard_after') and result.get('original_media_preserved')
                        and not result.get('final_check_error') and result['cleanup']['video_deleted']
                        and result['cleanup']['package_absent'] and result['cleanup']['staged_apk_removed']
                        and result.get('owned_directory_removed') and flow.native_launches==flow.closed and len(flow.closed)==2
                        and flow.pending is None and flow.close_pending is None
                        and not flow.fixture.install_pending and not flow.fixture.uninstall_pending):
                        result['state']='VIDEO_PLAY_PAUSE_RESUME_REOPEN_CLEANUP_VERIFIED'
    except BaseException as e:result['outer_error']=type(e).__name__+':'+str(e)
    finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
    result['finished_utc']=stamp()
    if ROOT.is_dir():tx.write_new(ROOT/'result.json',result,alex_readable=True)
    print(json.dumps({'state':result['state'],'result_path':str(ROOT/'result.json'),'error':result.get('error'),
        'outer_error':result.get('outer_error'),'cleanup':result.get('cleanup'),'pending_effect':result.get('pending_effect')}))
    return 0 if result['state']=='VIDEO_PLAY_PAUSE_RESUME_REOPEN_CLEANUP_VERIFIED' else 1

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--execute',action='store_true')
    if ap.parse_args().execute:raise SystemExit(execute())
    print('INERT')
