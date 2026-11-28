#!/usr/bin/python3 -I
"""One bounded owned JPEG album/rotation/reopen session; default inert."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,io,json,os,re,signal,time,types,xml.etree.ElementTree as ET
from PIL import Image

ROOT=None  # Set once to the create-only output by the trusted new entry.
TOOLS = Path('/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/custody/rotation-original')
TRANSPORT=Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
TRANSPORT_SHA='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
PREVIOUS_CLEANUP = Path('/home/alex/work/pocket4-android-final/qualification/gallery-rotation-prior-reconciliation-20261107-r2/result.json')
PREVIOUS_CLEANUP_SHA = 'ebd4ce9a89d80ddd8d33a93d9561e826b97d09c97d5ba94c37223dcc1ebe9357'
PINS={'rotation_ui.py': 'd290900f48d3c1f27b8d13b5efee0978bd5ebba365023d440f354c8a8ffdc7f4', 'rotation_package.py': '44abbfe0193905a7b3a6137b4bb95dafc8d6cec4d795e8b258b97508cdd83dd4', 'owned_media.py': '95b6c90fbc9ac22c41ca2c35d9ba3a13ce140de9cc52f710f2b5fd080506ae9b', 'verify_rotation.py': '934c70dd3e3f9c4174aaafbbb47b5ee8b2eb195d15c4fa18d2891ec995973093', 'bounded_diagnostics.py': 'c0eaf47627b31793b3c90d875ce74761ae9c98e749fc437a422e73c2da66a947'}
RUN='d24b61ed8f7c9a03';PACKAGE='org.droidloom.qa.galleryrotation.r12.n'+RUN
GALLERY='com.android.gallery3d'
GALLERY_SHA='835fe119745324276457b4434fc39f25b633e752c822d2fc9be40eb4b2d45439'
NATIVE_SHA='a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058'
CLIENT=(PACKAGE,PACKAGE+'.RotationActivity');PHOTO=(GALLERY,GALLERY+'.app.GalleryActivity')
COPY_ALBUM='Pocket4_Rotate_Copy_r12_'+RUN
MAX_SECONDS=600;CLEANUP_SECONDS=120
REQUIRED={'OWNED_ALBUM_ENUMERATION','OWNED_JPEG_THUMBNAIL','ORIGINAL_JPEG_FULL_DISPLAY',
    'UI_ROTATE_RIGHT_EXIF_INDEX_PIXELS','ROTATED_JPEG_FULL_DISPLAY',
    'NORMAL_REOPEN_ROTATED_THUMBNAIL','NORMAL_REOPEN_ROTATED_FULL_DISPLAY','ORIGINAL_PNG_UNCHANGED'}

def need(value,why):
    if not value:raise RuntimeError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def stamp():return datetime.now(timezone.utc).isoformat()
def load(path,pin):
    raw=Path(path).read_bytes();need(sha(raw)==pin,'SOURCE_PIN_CHANGED:'+Path(path).name)
    value=types.ModuleType('rotation_'+Path(path).stem);value.__file__=str(path)
    exec(compile(raw,str(path),'exec'),value.__dict__);return value

def completed_previous_cleanup(tx,session):
    return session.prior_cleanup()


class Flow:
    def __init__(self,s,tx,ui,pkg,media,pattern,diag):
        self.s,self.tx,self.ui_type,self.pkg_type,self.pattern,self.diag=s,tx,ui,pkg,pattern,diag
        self.ui=ui.Adapter(s,tx,ROOT/'ui')
        self.result={'schema':'pocket4-current-owned-gallery-jpeg-rotation-v1','state':'FAILED',
            'run':RUN,'temporary_package':PACKAGE,'started_utc':stamp(),'gates':{},
            'business_scope_completed':False,'whole_app_production_ready':False,'automatic_retry':False,
            'user_media_file_contents_read':False,'default_gallery_album_opened':False,
            'fixture_provider_creation_is_Gallery_UI_creation':False,'instrumentations':[],
            'temporary_package_excluded_from_launcher_denominator':True}
        self.pkg=pkg.PackageFixture(s,tx,self.ui,self.result)
        self.media=media.OwnedMedia(s,self.ui.record)
        self.helper_pending=None;self.client_pending=None;self.rotation_pending=None
        self.album_pending=None;self.close_pending=None
        self.instrument_calls=[];self.seed_attempted=False;self.rotation_input_calls=0
        self.before_diag=None;self.lease_expired=False

    def gate(self,name,proof):
        need(name in REQUIRED and name not in self.result['gates'],'UNDECLARED_OR_DUPLICATE_GATE')
        self.result['gates'][name]={'passed':True,**proof};self.ui.record('gate-'+name.lower(),proof)

    def gallery_identity(self):
        value=self.pkg_type.identity(self.s,GALLERY,GALLERY_SHA,self.s.gallery_uid,40030)
        permissions=self.diag.permissions(self.s,self.ui.record,'gallery-permissions')[GALLERY]
        need(any(line.startswith('android.permission.READ_MEDIA_IMAGES: granted=true,')
            for line in permissions['permission_rows']),'GALLERY_IMAGES_PERMISSION_REQUIRED')
        value['permissions']=permissions;return value

    def prefs(self):
        value,comparison=self.s.baseline.live.fixture().prefs()
        self.ui.record('actual-owned-helper-state',comparison)
        return value

    def status(self,value,private,phase,pending,rounds):
        need(isinstance(value,dict) and private is not None and value.get('run')==RUN
            and value.get('phase')==private.get('phase')==phase
            and value.get('pending')==private.get('pending')==pending
            and value.get('gallery_launches')==private.get('gallery_launches',0)==rounds,
            'PRIVATE_AND_RETURNED_PHASE_DIFFER')
        for counter in ('insert_calls','write_calls','publish_calls'):
            need(value.get(counter)==private.get(counter)==2,'TWO_FIXED_FIXTURE_EFFECTS_REQUIRED')
        deletes=2 if phase=='DELETED' else 0
        need(value.get('delete_calls')==private.get('delete_calls',0)==deletes,'EXACT_HELPER_DELETE_COUNT')
        for key in ('control_uri','copy_uri'):
            need(value.get(key)==private.get(key) and re.fullmatch(
                r'content://media/external_primary/images/media/[1-9][0-9]*',value.get(key,'')),
                'EXACT_PRIVATE_IMAGE_URI_REQUIRED')

    def no_unknown(self):
        need(not self.ui.pending and self.helper_pending is None and self.client_pending is None
            and self.rotation_pending is None and self.close_pending is None
            and self.media.directory_pending is None and not self.pkg.install_pending
            and not self.pkg.uninstall_pending,'UNKNOWN_EFFECT_PRESERVE_FIXTURE')

    def setup(self):
        self.result['guard_before']=self.s.guard()
        previous=completed_previous_cleanup(self.tx,self.s)
        self.result['previous_cleanup']=previous
        self.result['current_verified_image_custody']=self.s.image_custody_ref
        roots,tasks=self.ui.stacks('original-task-baseline')
        need(not any(child['component'].split('/')[0] in (PACKAGE,GALLERY)
            for root in roots.values() for child in root['children']),'PREEXISTING_GALLERY_OR_HELPER_TASK')
        self.ui.baseline=tasks
        self.result['gallery_before']=self.gallery_identity()
        self.s.match_image_identity(self.result['gallery_before'])
        self.result['native_actions_before']=self.pkg_type.identity(self.s,'local.pocket4.actions.v2',NATIVE_SHA,10125,2)
        self.diag.uid_census(self.s,self.ui.record,'gallery-uid-census')
        self.media.setup()
        self.pkg.install();self.pkg.grants_empty('initial-helper-grants')
        need(self.prefs() is None,'NEW_HELPER_PRIVATE_RECORD_PRESENT')
        self.before_diag=self.diag.capture(self.s,self.ui.record,'gallery-diagnostics-before')

    def instrument(self,operation):
        phases={'seed':('SEEDED',0),'seal-first-unchanged':('FIRST_CLOSED_UNCHANGED',1),
            'seal-first-clockwise':('ROTATED_VERIFIED',1),'seal-reopen-clockwise':('REOPENED_VERIFIED',2),
            'delete':('DELETED',None)}
        need(operation in phases and operation not in self.instrument_calls and len(self.instrument_calls)<5,
            'FIXED_INSTRUMENTATION_ONCE_ONLY')
        self.no_unknown()
        need(not self.ui.owned,'INSTRUMENTATION_MUST_NOT_TERMINATE_OWNED_ACTIVITY')
        self.ui.check_tasks('before-instrument-'+operation)
        need(self.pkg_type.identity(self.s,PACKAGE,self.pkg_type.APK_SHA)==self.pkg.installed,
            'HELPER_IDENTITY_CHANGED')
        if operation=='seed':need(not self.seed_attempted and self.album_pending is None,'SEED_NOT_REPEATABLE')
        elif operation.startswith('seal-'):
            need(self.album_pending is not None and self.album_pending.get('route_verified') is True,
                'UNVERIFIED_ALBUM_LAUNCH_CANNOT_BE_SEALED')
        else:need(self.album_pending is None,'OPEN_ALBUM_PRIVATE_EFFECT_NOT_SEALED')
        previous=self.prefs()
        rounds=0 if previous is None else previous.get('gallery_launches',0)
        argv=['/system/bin/am','instrument','-w','-r','-e','run',RUN,'-e','op',operation,PACKAGE+'/.MediaFixture']
        self.helper_pending=operation;self.instrument_calls.append(operation)
        if operation=='seed':self.seed_attempted=True
        self.ui.record('helper-'+operation+'-intent',{'argv':argv,'automatic_retry':False,
            'all_owned_tasks_already_normally_closed':True,'Gallery_UI_success_claimed':False})
        raw=self.s.android(argv,55).decode();self.ui.record('helper-'+operation+'-response',{'stdout':raw})
        values=re.findall(r'^INSTRUMENTATION_RESULT: result_json=(.+)$',raw,re.M)
        codes=re.findall(r'^INSTRUMENTATION_CODE: (-?\d+)\s*$',raw,re.M)
        need(len(values)==1 and codes==['0'],'HELPER_INSTRUMENTATION_NOT_TERMINAL_SUCCESS')
        value=json.loads(values[0])
        need(value.get('ok') is True and value.get('schema')=='owned-gallery-rotation-fixture-v1'
            and value.get('operation')==operation and value.get('run')==RUN
            and value.get('package')==PACKAGE and value.get('uid')==self.pkg.installed['uid']
            and value.get('Gallery_UI_success_claimed') is False,'HELPER_RECEIPT_IDENTITY')
        phase,expected_rounds=phases[operation]
        self.status(value.get('status'),self.prefs(),phase,'',rounds if expected_rounds is None else expected_rounds)
        self.helper_pending=None
        if operation.startswith('seal-'):self.album_pending=None
        if operation=='seed':
            need(value.get('media',{}).get('rotated') is False,'SEEDED_ORIENTATION_REQUIRED')
            self.media.media=value['media']
        self.result['instrumentations'].append(value);return value

    def no_dispatch(self,exc,before_actions):
        details=getattr(exc,'details',{})
        return (not self.ui.pending and (self.ui.actions==before_actions or
            (details.get('action_taken') is False and details.get('outcome_unknown') is not True)))

    def open_album(self,round_number):
        self.no_unknown();need(self.album_pending is None,'PRIOR_ALBUM_ROUND_NOT_SEALED')
        phase='SEEDED' if round_number==1 else 'ROTATED_VERIFIED'
        self.ui.launch();obs=self.ui.observe('client-round-'+str(round_number),[CLIENT])
        node=self.ui.one(obs,lambda n:n.get('resource-id')==PACKAGE+':id/status','ONE_HELPER_STATUS')
        private=self.prefs();self.status(json.loads(node.get('text','')),private,phase,'',round_number-1)
        button=self.ui.one(obs,lambda n:n.get('resource-id')==PACKAGE+':id/open_owned_album'
            and n.get('class')=='android.widget.Button' and n.get('text')=='OPEN OWNED JPEG ALBUM'
            and n.get('enabled') is True and n.get('clickable') is True and 16 in n.get('supported_actions',[]),
            'ONE_EXPLICIT_OWNED_ALBUM_BUTTON')
        label='open-owned-album-'+str(round_number)
        self.client_pending=label;before_actions=self.ui.actions
        self.ui.record('album-client-action-intent',{'round':round_number,'previous_phase':phase,
            'automatic_retry':False,'expected_single_owned_bucket':self.media.media['copy']['metadata']['bucket_id']})
        try:self.ui.input(obs,label,button,transition=PHOTO)
        except BaseException as exc:
            if self.no_dispatch(exc,before_actions) and self.prefs()==private:self.client_pending=None
            raise
        current=self.prefs()
        uri='content://media/external/images/media?bucketId='+str(self.media.media['copy']['metadata']['bucket_id'])
        need(current is not None and current.get('phase')=='ALBUM_OPEN_'+str(round_number)
            and current.get('pending')=='gallery-open-'+str(round_number)
            and current.get('gallery_launches')==round_number and current.get('album_uri')==uri,
            'PRIVATE_ALBUM_DISPATCH_NOT_VERIFIED')
        self.ui.bind_gallery_route(label,uri,self.pkg.installed['uid'])
        obs=self.ui.observe('owned-album-'+str(round_number),[PHOTO])
        need(not self.ui.pending,'ALBUM_NATIVE_PENDING')
        self.album_pending={'round':round_number,'album_uri':uri,'route_verified':True,
            'gallery_focus':obs['focus']}
        self.client_pending=None
        self.ui.s.commands.native_channel_module().ComparisonChannel().observe_running_engine()
        return obs

    def album_title(self,obs):
        need((obs['focus']['package'],obs['focus']['activity'])==PHOTO and not obs['focus'].get('popup'),
            'OWNED_GALLERY_ALBUM_WINDOW_REQUIRED')
        bar=self.ui.one(obs,lambda n:n.get('package')==GALLERY
            and n.get('resource-id')=='android:id/action_bar' and n.get('class')=='android.view.ViewGroup'
            and n.get('visible') is True and n.get('enabled') is True,
            'ONE_ACTUAL_GALLERY_ACTION_BAR_REQUIRED')
        node=self.ui.one(obs,lambda n:n.get('package')==GALLERY and n.get('class')=='android.widget.LinearLayout'
            and n.get('text')=='' and n.get('content-desc')==COPY_ALBUM+', Navigate up'
            and n.get('visible') is True and n.get('enabled') is True and n.get('clickable') is True
            and n.get('editable') is False and n.get('password') is False
            and 16 in n.get('supported_actions',[]),'EXACT_OWNED_ALBUM_NAVIGATION_TITLE_REQUIRED')
        children=[self.ui.one(obs,lambda n:n.get('package')==GALLERY
            and n.get('class')=='android.widget.ImageView' and n.get('resource-id')==resource
            and n.get('visible') is True and n.get('enabled') is True,
            'ONE_ACTUAL_GALLERY_NAVIGATION_ICON_REQUIRED') for resource in ('android:id/up','android:id/home')]
        window=node.get('window_id')
        need(type(window) is int and window>=0 and all(n.get('window_id')==window for n in [bar,*children]),
            'ALBUM_TITLE_CONTEXT_CROSS_WINDOW')
        for value in [bar,node,*children]:self.ui.box(obs,value)
        def inside(outer,inner):
            return outer[0]<=inner[0]<inner[2]<=outer[2] and outer[1]<=inner[1]<inner[3]<=outer[3]
        need(inside(bar['bounds_array'],node['bounds_array'])
            and all(inside(node['bounds_array'],child['bounds_array']) for child in children),
            'ALBUM_TITLE_NOT_INSIDE_ACTUAL_NAVIGATION_CONTAINER')
        # Preserve the real node: its text is empty; the label is derived only
        # from the exact observed description. This control is never pressed.
        return {'album_name':COPY_ALBUM,'album_name_derived_from_exact_description':True,
            'observed_content_description':node['content-desc'],'navigation_node':node,
            'action_bar_node':bar,'navigation_icon_nodes':children,
            'same_native_window_id':window,'navigation_control_pressed':False}

    def visual(self,obs,label,degrees,kind):
        need(self.album_pending is not None and self.album_pending.get('route_verified') is True
            and obs['focus']==self.album_pending['gallery_focus'],'PHOTO_OUTSIDE_BOUND_OWNED_ALBUM_WINDOW')
        if kind=='thumbnail':self.album_title(obs)
        matches=list((ROOT/'ui').glob('*-'+label+'.png'));need(len(matches)==1,'ONE_SAVED_SCOPED_FRAME_REQUIRED')
        raw=matches[0].read_bytes();shot=obs['screenshot']
        with Image.open(io.BytesIO(raw)) as image:
            image=image.convert('RGB')
            need(image.size==(shot['scope_width'],shot['scope_height'])
                and self.s.helper.image_sha(image)==shot['scope_sha256'],'SAVED_PIXELS_NOT_BOUND_TO_OBSERVATION')
            proof=self.pattern.verify_display(image,self.media.media['copy']['decoded'],degrees,kind)
        proof.update(scope_sha256=shot['scope_sha256'],context_token=shot['context_token'],
            png_sha256=sha(raw),album=COPY_ALBUM,owned_uri=self.media.media['copy']['uri'])
        self.ui.record(label+'-pattern-proof',proof);return proof

    def rotation(self,photo):
        self.no_unknown();need(self.rotation_input_calls==0 and self.album_pending is not None
            and self.album_pending['round']==1,'ONE_ROTATION_IN_FIRST_OWNED_ROUND')
        self.media.verify('immediately-before-menu',False)
        photo=self.ui.observe('before-rotation-menu',[PHOTO])
        shown_reply=None
        if not any(n.get('content-desc')=='More options' for n in photo['nodes']):
            # Actual PhotoPage.refreshHidingMessage schedules hideBars after
            # 3500 ms. LocalImage's supported-op masks exclude video/camera
            # special taps; onSingleTapUp reaches toggleBars for this JPEG.
            proof=self.visual(photo,'before-rotation-menu',0,'full')
            shown_reply=self.ui.tap_pattern(photo,proof,'show-owned-photo-bars',purpose='show-photo-bars')
        # Use a fresh native observation for this semantic control. The actual
        # post-show capture is retained as context; no extra screenshot round
        # trip is inserted into PhotoPage's 3500 ms toolbar visibility window.
        self.ui.open_more_options(photo,shown_reply)
        menu=self.ui.observe('rotation-menu',[PHOTO])
        rotate=self.ui.one(menu,lambda n:n.get('text')=='Rotate right'
            and n.get('editable') is False and n.get('enabled') is True
            and n.get('class') in ('android.widget.TextView','android.widget.Button'),
            'ACTUAL_SUPPORTED_ROTATE_RIGHT_MENU_REQUIRED')
        self.media.verify('immediately-before-rotate-right',False)
        self.rotation_pending={'operation':'rotate-right','original':self.media.baseline['copy']}
        before_actions=self.ui.actions
        self.ui.record('rotation-effect-intent',{'pending':self.rotation_pending,'degrees':90,
            'source_menu_id':'com.android.gallery3d:id/action_rotate_cw','automatic_retry':False})
        try:self.ui.input(menu,'rotate-right',rotate)
        except BaseException as exc:
            if self.no_dispatch(exc,before_actions):
                self.media.verify('rotation-explicit-no-input-original-file',False)
                self.rotation_pending=None
            raise
        self.rotation_input_calls+=1
        self.rotation_pending['input_acknowledged']=True
        errors=[];proof=None;end=time.monotonic()+12
        for attempt in range(4):
            try:
                proof=self.media.verify('rotate-right-readback-'+str(attempt),True,admit_rotation=True);break
            except Exception as exc:
                errors.append(type(exc).__name__+':'+str(exc))
                if time.monotonic()>=end:break
                time.sleep(.3)
        need(proof is not None,'ROTATION_EFFECT_UNRESOLVED:'+json.dumps(errors))
        self.rotation_pending=None
        self.gate('UI_ROTATE_RIGHT_EXIF_INDEX_PIXELS',{'single_rotation_input':1,'actual_media':proof,
            'EXIF_orientation':6,'MediaStore_orientation':90,'raw_pixel_digest_unchanged':True,
            'ACK_alone_would_not_pass':True})
        return self.ui.observe('rotated-full',[PHOTO])

    def close(self):
        self.no_unknown()
        if not self.ui.owned:
            self.ui.check_tasks('already-closed-task-baseline');return
        self.close_pending={'tasks':list(self.ui.owned),'normal_remove_only':True}
        self.ui.record('owned-close-batch-intent',self.close_pending)
        self.ui.close_all()
        self.ui.check_tasks('normal-close-batch-completed')
        need(not self.ui.pending and not self.ui.owned,'OWNED_CLOSE_UNRESOLVED')
        self.close_pending=None

    def run(self):
        self.setup();self.instrument('seed')
        original=self.media.verify('owned-two-images-seeded',False)
        album=self.open_album(1)
        title=self.album_title(album)
        self.gate('OWNED_ALBUM_ENUMERATION',{'album_identity':title,
            'global_sole_copy_row':original['copy']['metadata'],
            'control_in_distinct_owned_bucket':True,'default_album_was_not_opened':True})
        thumb=self.visual(album,'owned-album-1',0,'thumbnail')
        self.gate('OWNED_JPEG_THUMBNAIL',thumb)
        self.ui.tap_pattern(album,thumb,'open-owned-thumbnail-1')
        photo=self.ui.observe('original-full',[PHOTO])
        self.gate('ORIGINAL_JPEG_FULL_DISPLAY',self.visual(photo,'original-full',0,'full'))
        rotated=self.rotation(photo)
        self.gate('ROTATED_JPEG_FULL_DISPLAY',self.visual(rotated,'rotated-full',90,'full'))
        self.close();self.instrument('seal-first-clockwise')
        self.open_album(2);self.media.verify('normal-reopen-physical',True)
        album=self.ui.observe('owned-album-reopened-ready',[PHOTO])
        thumb=self.visual(album,'owned-album-reopened-ready',90,'thumbnail')
        self.gate('NORMAL_REOPEN_ROTATED_THUMBNAIL',thumb)
        self.ui.tap_pattern(album,thumb,'open-owned-thumbnail-2')
        photo=self.ui.observe('reopened-full',[PHOTO])
        self.gate('NORMAL_REOPEN_ROTATED_FULL_DISPLAY',self.visual(photo,'reopened-full',90,'full'))
        self.close();self.instrument('seal-reopen-clockwise')
        final=self.media.verify('final-media-before-cleanup',True)
        self.gate('ORIGINAL_PNG_UNCHANGED',{'initial':self.media.baseline['control'],'final':final['control'],
            'full_png_bytes_sha256_identical':True,'actual_bytes':2416})
        need(set(self.result['gates'])==REQUIRED and self.ui.launches==2 and self.rotation_input_calls==1,
            'COMPLETE_DECLARED_SCOPE_REQUIRED')
        self.result['business_scope_completed']=True

    def cleanup(self):
        result={'errors':[],'provider_fixture_creation_is_UI_creation':False,'UI_delete_credit':False}
        try:
            self.no_unknown()
            self.close()
            if self.pkg.installed is not None:
                current=self.prefs()
                if self.seed_attempted:
                    need(current is not None and self.media.media is not None,'SEED_RESULT_UNKNOWN_KEEP_FIXTURE')
                    if self.album_pending is not None:
                        round_number=self.album_pending['round']
                        rotated=self.media.rotated is not None
                        need(round_number==1 or rotated,'SECOND_ROUND_ORIENTATION_UNKNOWN')
                        self.media.verify('known-closed-album-before-seal',rotated)
                        operation=('seal-reopen-clockwise' if round_number==2 else
                            'seal-first-clockwise' if rotated else 'seal-first-unchanged')
                        self.instrument(operation);current=self.prefs()
                    need(current.get('pending')=='' and current.get('phase') in
                        ('SEEDED','ROTATED_VERIFIED','REOPENED_VERIFIED','FIRST_CLOSED_UNCHANGED'),
                        'PRIVATE_PROVIDER_EFFECT_UNKNOWN_KEEP_FIXTURE')
                    self.media.verify('owned-images-before-exact-delete',self.media.rotated is not None)
                    self.instrument('delete')
                    result['media_cleanup']=self.media.cleanup_directories()
                else:
                    need(current is None and self.media.namespace('never-seeded-namespace')==[],
                        'UNEXPECTED_MEDIA_BEFORE_SEED')
                    result['media_cleanup']={'no_seed_dispatched':True,'owned_namespace_empty':True}
                self.pkg.grants_empty('final-helper-grants')
                result['package_cleanup']=self.pkg.uninstall(True)
                self.pkg.grants_empty('after-uninstall-helper-grants')
            else:
                need(not self.pkg.install_pending,'UNKNOWN_INSTALL_PRESERVE_PACKAGE')
                result['package_cleanup']=self.pkg.uninstall(True)
            self.ui.check_tasks('final-task-set')
            result['task_set_restored']=not self.ui.owned and not self.ui.pending
        except BaseException as exc:
            result['errors'].append(type(exc).__name__+':'+str(exc))
        try:result['stage_cleanup']=self.pkg.cleanup_staged()
        except BaseException as exc:result['errors'].append('stage:'+type(exc).__name__+':'+str(exc))
        return result

    def finish(self):
        result=self.result
        if self.before_diag is not None:
            after=self.diag.capture(self.s,self.ui.record,'gallery-diagnostics-after')
            result['diagnostics']=self.diag.compare(self.before_diag,after)
            need(result['diagnostics']['no_new_crash_or_anr_observed'],'NEW_GALLERY_CRASH_OR_ANR')
        if 'gallery_before' in result:
            result['gallery_after']=self.gallery_identity()
            need(result['gallery_after']==result['gallery_before'],'GALLERY_IDENTITY_OR_PERMISSION_CHANGED')
        if 'native_actions_before' in result:
            result['native_actions_after']=self.pkg_type.identity(self.s,'local.pocket4.actions.v2',NATIVE_SHA,10125,2)
            need(result['native_actions_after']==result['native_actions_before'],'NATIVE_ACTIONS_IDENTITY_CHANGED')
        if self.media.before is not None:
            result['original_media_preserved']=self.media.original('original-media-final')==self.media.before
            need(result['original_media_preserved'],'ORIGINAL_MEDIA_METADATA_CHANGED')
        result['guard_after']=self.s.guard()
        need(result['guard_after']==result.get('guard_before'),'FINAL_GUARD_CHANGED')
        self.s.caller_status('rotation-final-caller')

    def terminal(self):
        self.result.update(ui_actions=self.ui.actions,native_launches=self.ui.launches,
            owned_tasks=self.ui.owned,normal_closed_tasks=self.ui.closed,
            native_pending=self.ui.pending,helper_pending=self.helper_pending,client_pending=self.client_pending,
            rotation_pending=self.rotation_pending,album_pending=self.album_pending,close_pending=self.close_pending,
            directory_pending=self.media.directory_pending,install_pending=self.pkg.install_pending,
            uninstall_pending=self.pkg.uninstall_pending,instrument_calls=self.instrument_calls,
            rotation_input_calls=self.rotation_input_calls,source_pins=PINS)
