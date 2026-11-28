#!/usr/bin/python3 -I
"""Owned silent video: real pixels, native pause/resume, normal reopen, exact cleanup."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, io, json, os, re, signal, stat, sys, time, types
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
ROOT=None  # Bound once to the new create-only result directory.
BASE=HERE/'gallery_base.py'
BASE_SHA='06a182dae066e4d1c9d0387371711145754378747e561f16543e5315051aefb2'
CODE = Path('/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/inputs/current-movie-source.json')
CODE_SHA = 'ac4dee6dda805bd163fc0a4274e5c15a173b9fb2224e65113852aa51676d670f'
RUN='c92c3d79180955ef';PACKAGE='org.droidloom.qa.media.r12.n'+RUN
FOLDER='Pocket4_Gallery_r12_'+RUN;NAME='pocket4-pattern-'+RUN+'.mp4'
RELATIVE='DCIM/'+FOLDER+'/';GUEST_FOLDER='/storage/emulated/0/DCIM/'+FOLDER;GUEST_FILE=GUEST_FOLDER+'/'+NAME
GALLERY='com.android.gallery3d';MAIN=GALLERY+'.app.GalleryActivity';MOVIE=GALLERY+'.app.MovieActivity'
VIDEO_SHA='eaeb797bff8f610373204451f5885dcba2fb1ffa2530410468b7dc480d5588da'
PINS={'package_fixture.py': '5cb30798c5ce70e5dd56175e7a7d4382908086f30c3cbeda16b6dc10c18ab068', 'runtime_evidence.py': '670af6f9a2ecd16591babc3e40387dc6f25474d27f73fc93f42b881d3d60d5df', 'verify_pattern.py': '80cd758ca6da90fa404368907fc645adb9524b86be96966dc328599c2e8f7e7f', 'verify_video.py': '2b52f1514fff4507a9618ac5695d0dd64820f2e34f9c242cb5d640f6c79fe93d'}
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
            self.last_video_proof=None;self.seek_attempts=0
            self.result.update(schema='pocket4-gallery-current-video-flow-v1',run=RUN,temporary_package=PACKAGE,
                max_seconds=WORK_SECONDS,cleanup_seconds=CLEANUP_SECONDS,media_kind='video',audio_track_count=0,
                audio_output_qualified=False,seek_qualified=False,album_enumeration_qualified=False,
                movie_source_receipt_sha256=CODE_SHA,inputs=[],pixel_rounds=[])

        def setup(self):
            self.result['prior_cleanup']=self.s.prior_cleanup()
            self.result['guard_before']=self.s.guard();self.result['gallery_before']=self.gallery_identity()
            need(any(line.startswith('android.permission.READ_MEDIA_VIDEO: granted=true,')
                for line in self.result['gallery_before']['permissions']),'GALLERY_VIDEO_PERMISSION_NOT_GRANTED')
            self.result['native_actions_before']=self.doc.identity(self.s,'local.pocket4.actions.v2','a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058',10125,2)
            self.original_rows=self.original_media('original-before')
            need(self.namespace('namespace-before')==[],'GLOBAL_MEDIA_NAMESPACE_NOT_ABSENT')
            self.folder_parent=self.s.target.open_root('/storage/emulated/0/DCIM',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:os.stat(FOLDER,dir_fd=self.folder_parent,follow_symlinks=False)
            except FileNotFoundError:pass
            else:raise RuntimeError('OWNED_FOLDER_ALREADY_EXISTS')
            self.before_diag=self.diagnostics.diagnostics('before',self.s.gallery_uid)
            self.fixture.install();self.installed=self.fixture.installed
            self.record('global-owned-namespace-absent',{'global_media_rows':0,'physical_directory_absent':True})
            self.runtime=self.runtime_module.RuntimeEvidence(self.s.runtime_observer_session(),self.tx,ROOT/'runtime-private',FOLDER)
            self.runtime.start()

        def prefs(self):
            value,comparison=self.s.baseline.live.fixture().prefs()
            self.record('actual-owned-helper-state',comparison)
            return value

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

        def native_controls(self,label):
            # The exact installed runner revalidates the complete native tree,
            # selected application window and unique node inside its own request.
            focus=self.movie_focus();self.s.guard()
            value=self.s.helper.ui({'op':'dump','expected_package':GALLERY,'display':0,'accessibility_mode':'none'})
            self.s.guard();current=self.ui.focus(label+'-wm-after-native')
            need(current==focus and self.ui.focus_allowed(current,False),'NATIVE_CONTROL_WINDOW_CHANGED')
            context=value.get('window_context',{});window=context.get('selected_window',{});root=context.get('root',{})
            need(value.get('ok') is True and value.get('accessibility_mode_restoration_verified') is True
                and context.get('snapshot_complete') is True and context.get('truncated') is False
                and context.get('display_id')==0 and window.get('display_id')==0
                and window.get('active') is True and window.get('focused') is True and window.get('type')==1
                and root.get('package')==GALLERY and root.get('visible') is True
                and window.get('root',{}).get('package')==GALLERY
                and root.get('window_id')==window.get('window_id'),'NATIVE_CONTROL_SCOPE_INCOMPLETE')
            self.record(label,{'focus':focus,'native':value,'no_pixel_equality_required_for_semantic_selection':True})
            return focus,[n for n in value.get('nodes',[]) if n.get('package')==GALLERY and n.get('visible') is True],window['bounds']

        def ensure_controls(self):
            focus,nodes,scope=self.native_controls('show-controls-native-before')
            button=self.control(nodes,PAUSE_LABELS)
            if button:return focus,button
            need(self.control(nodes,PLAY_LABELS) is None,'VIDEO_ALREADY_PAUSED_BEFORE_PAUSE_TEST')
            views=[n for n in nodes if n.get('class')=='android.widget.VideoView'
                and n.get('resource-id')==GALLERY+':id/surface_view' and n.get('enabled') is True
                and n.get('focused') is True and n.get('clickable') is False]
            need(len(views)==1,'UNIQUE_OBSERVED_NATIVE_VIDEO_VIEW_REQUIRED')
            node=views[0];bounds=node.get('bounds_array')
            need(isinstance(bounds,list) and len(bounds)==4 and all(type(v) is int for v in bounds)
                and scope[0]<=bounds[0]<bounds[2]<=scope[2] and scope[1]<=bounds[1]<bounds[3]<=scope[3],
                'NATIVE_VIDEO_VIEW_OUTSIDE_OWNED_WINDOW')
            selector={'package':GALLERY,'id':GALLERY+':id/surface_view','class':'android.widget.VideoView',
                'enabled':True,'focused':True,'clickable':False}
            request={'op':'click','expected_package':GALLERY,'display':0,'accessibility_mode':'none','method':'mouse','selector':selector}
            need(self.pending is None and self.inputs<MAX_INPUTS and self.movie_focus()==focus,'INPUT_SCOPE_OR_BUDGET')
            self.record('show-controls-native-intent',{'request':request,'observed_video_view':node,'focus':focus,
                'source_bound_to':'Actual v2 native bounds mouse; installed MoviePlayer$3.onTouch calls controller.show',
                'automatic_retry':False})
            self.pending='show-controls-native';self.inputs+=1
            try:reply=self.s.helper.ui(request)
            except BaseException as exc:
                details=getattr(exc,'details',{})
                if details.get('outcome_unknown') is False:
                    self.record('show-controls-native-explicit-no-effect',{'error':str(exc),'details':details});self.pending=None
                raise
            self.record('show-controls-native-receipt',reply);target=reply.get('actual_target',{})
            need(reply.get('ok') is True and reply.get('performed')=='click' and reply.get('method')=='mouse'
                and reply.get('source')=='native_bounds_mouse' and reply.get('accessibility_mode_restoration_verified') is True
                and target.get('package')==GALLERY and target.get('class')=='android.widget.VideoView'
                and target.get('resource-id')==selector['id'] and target.get('bounds_array')==bounds
                and reply.get('coordinates')==[(bounds[0]+bounds[2])//2,(bounds[1]+bounds[3])//2],
                'NATIVE_MOUSE_RECEIPT_NOT_JOINED')
            current,fresh,_=self.native_controls('show-controls-native-after')
            button=self.control(fresh,PAUSE_LABELS)
            need(current==focus and button is not None,'PLAYING_CONTROL_NOT_OBSERVED_AFTER_NATIVE_SHOW')
            self.pending=None;self.result['inputs'].append({'label':'show-controls','method':'native_bounds_mouse',
                'actual_target':target,'own_task':focus['task'],'Pause_control_observed':True})
            return current,button

        def click_control(self,label,focus,button,expected_labels):
            need(self.pending is None and self.inputs<MAX_INPUTS and self.movie_focus()==focus,'PLAYBACK_CLICK_SCOPE')
            selector={'package':GALLERY,'class':'android.widget.ImageView','desc':button['content-desc'],'clickable':True,'enabled':True}
            request={'op':'click','expected_package':GALLERY,'display':0,'accessibility_mode':'none',
                'method':'accessibility','selector':selector}
            self.record(label+'-intent',{'request':request,'observed_control':button,'focus':focus,'automatic_retry':False})
            self.pending=label;self.inputs+=1
            try:reply=self.s.helper.ui(request)
            except BaseException as exc:
                details=getattr(exc,'details',{})
                if details.get('outcome_unknown') is False:
                    self.record(label+'-explicit-no-effect',{'error':str(exc),'details':details});self.pending=None
                raise
            self.record(label+'-receipt',reply);target=reply.get('actual_target',{})
            need(reply.get('ok') is True and reply.get('performed')=='click'
                and reply.get('accessibility_mode_restoration_verified') is True
                and target.get('package')==GALLERY and target.get('class')=='android.widget.ImageView'
                and target.get('content-desc')==button['content-desc'],'PLAYBACK_CLICK_NOT_JOINED')
            current,nodes,_=self.native_controls(label+'-post');next_control=self.control(nodes,expected_labels)
            need(current==focus and next_control is not None,'PLAYBACK_STATE_CONTROL_NOT_CHANGED')
            self.pending=None;self.result['inputs'].append({'label':label,'before':button['content-desc'],
                'after':next_control['content-desc'],'actual_target':target,'owned_task':focus['task']})
            return current,next_control

        def video_round(self,index):
            need(self.pending is None,'PENDING_VIDEO_ROUND');self.runtime.phase_changed('round-'+str(index)+'-launch')
            self.pending='native-launch-'+str(index);self.ui.launch();task=self.ui.owned[0]
            self.native_launches.append(task);self.pending=None
            self.ui.s.commands.native_channel_module().ComparisonChannel().observe_running_engine()
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
            if index==1:
                self.s.components['video_seek.py'].seek_midpoint(self,entry)
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
                need(stage.get('guest_staging_used') is False and stage.get('staged_apk_created') is False,
                     'NORMAL_HELPER_MUST_USE_NO_GUEST_APK_STAGING')
                out['guest_staging_used']=False;out['staged_apk_created']=False;out['staged_apk_removed']=False
            except BaseException as e:out['errors'].append('stage:'+type(e).__name__+':'+str(e))
            finally:
                self.pkg_module.close_handles(self,('folder_fd','folder_parent'))
            return out
    return VideoFlow

