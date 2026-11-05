"""Bounded successful reads and private crops of the observed player overlay.

No click, input injection, audio capture or playback-success inference. Source
is publishable; PNG files and full helper assessments remain private.
"""
import io
import json
import os
import struct
import time

DETAILS='tv.danmaku.bili/com.bilibili.ship.theseus.detail.UnitedBizDetailsActivity'
TITLE='7ff99f77d6b59f394c4c6c0ca167aded470663d4cef66215fcce841ed549afba'
AUTHOR='3355707b07511199c7d280b9a77510b5e9b8698c7c7e4aedcf938805a3822d64'
NONCES = [['a17d8eaace047ba4f552486225d57727', '0b5a977103ddc2cc454d545020b3f6fc', 'cee745fc466496a97fe1c9d64b5404f8'], ['8752e7ac524a37e5490d8fdd8bd323d3', '55434fbc05d21b45efca09dcec39027c', '4b4dd14bff878690cee20f187bcfc4d4'], ['90bd4cefc75f4284b319f07a5676c6f4', '0ce7877c11152a3904cd2f2bd51498ea', '4f44f03350884a5246ebbee56059a91a'], ['babbf00d4a979b77934cb3a6c1f456a3', 'da701d4ac79b93bba55eab41a5a2d4c7', '86019a396b87210ad6e1f82e5f8d0af0'], ['838933ced9c6eef5e88a7a0fd822b4e5', '26fdf1be0bba8ec32f212c6a7ba0e745', 'ae87bcb856e0ee8bff9a623daa8c7468'], ['31d6e3e27dd3b6690be4cf6dbd152d2a', 'cf1f045e93bcb1d991453f00975c9775', '55720ea3fabccdbc76528a6d4434a29d'], ['ce8bcc7087bbfd779116a38eba15dae5', 'cebbe8ab0a71733f3004f7a474dbef81', '4f802aa2f68e9eded7f3b35517bb8a63'], ['f77721b5cd90655d693bd0b81fc54d0c', '23c0a3d24125b4dcf00e7671df4970cf', '939724b29ac0a34b0faf0d31dcb67655'], ['cea2b345589d819052f9eacf3cdef32b', 'f9bddd387341f6c36f79e061dd2b70d7', '5718bf5d49a11ede0f4b73a7cacfca97'], ['5c007bf64da0ef9e35fa583e8be11067', '3301f1b4ff96647a779aa3e78753748e', '397164ba7768f81e03f8839434a00187'], ['1e78b002f0068f16922ff79ddd4b22d3', 'd0ef7c74eb0e11b419874a2eead9d574', '1da80d7874c9e0df25fe2cd1071246ec'], ['3fc386ef1ffb0f94ee59e58485ed7a4b', '4db1d3d2d5d7623acfd3c795c2fed8e1', '0818079f012597fbc6cc8cf32aab1107'], ['c611f4e986acdf0f34a7ab28e9d3d420', '318455c0b0e553e1929f99f9a54d6a7a', '574e61a6d16b96ad05bb09bb8ef03988'], ['7eddb4ab616d84c67de43f64d6de679d', '34fa3177e2acc4b90e6de0861078d42d', '36303b3d2e334452ecfe7a363c4cfcba'], ['734540d3033fd9e229db437c8912abd6', '358d57a1f9025d5c8c6791a6e8e3d397', 'e9306051f9624d78489a31ed7985a3b5']]
PLANS=[{'schema':1,'operation':'inspect','nonces':dict(zip(('before','inspect','after'),row))}for row in NONCES]


def validate(adapter,qa,used):
    values=[x for row in NONCES for x in row]
    qa.require(len(NONCES)==15 and all(len(row)==3 for row in NONCES) and
        len(values)==len(set(values))==45 and not set(values)&set(used),'FIXED_FRESH_VIEWPORT_NONCES')
    for plan in PLANS:adapter.validate_plan(plan,qa)


def viewport(base,qa,inspection,scope):
    qa.inspect_record(inspection);qa.scope(scope)
    base.require(scope['activity']==DETAILS,'CURRENT_COURSE_DETAILS_REQUIRED')
    nodes=inspection['nodes'];window=inspection['window']
    def one(resource,kind,digest=None):
        rows=[n for n in nodes if n['resource_id']==resource and n['class']==kind and
            n['resource_id_truncated'] is False and n['class_truncated'] is False and
            n['visible'] is True and n['enabled'] is True and n['password'] is False and
            (digest is None or (n['text_truncated'] is False and isinstance(n['text'],str) and
             base.sha(n['text'].encode())==n['text_sha256']==digest))]
        base.require(len(rows)==1,'EXACT_CURRENT_VIEWPORT_NODE_REQUIRED:'+resource)
        return rows[0]
    one('tv.danmaku.bili:id/title','android.widget.TextView',TITLE)
    one('tv.danmaku.bili:id/author_name','android.widget.TextView',AUTHOR)
    area=one('tv.danmaku.bili:id/video_area','android.widget.FrameLayout')
    container=one('tv.danmaku.bili:id/video_container','android.widget.FrameLayout')
    overlay=one('tv.danmaku.bili:id/video_area_float_layer_container','android.widget.FrameLayout')
    toolbar=one('tv.danmaku.bili:id/collapsing_toolbar','android.widget.FrameLayout')
    surfaces=[n for n in nodes if n['class'] in ('android.view.SurfaceView','android.view.TextureView')]
    base.require(len(surfaces)==2 and all(n['class']=='android.view.SurfaceView' and
        n['class_truncated'] is False and n['resource_id']=='' and n['resource_id_truncated'] is False and
        n['visible'] is True and n['enabled'] is True and n['password'] is False and
        n['path'].startswith(container['path']+'/') and
        not n['path'].startswith(overlay['path']+'/') and
        not n['path'].startswith(toolbar['path']+'/') for n in surfaces) and
        container['path'].startswith(area['path']+'/') and
        overlay['path'].startswith(area['path']+'/'),'EXACT_TWO_CURRENT_PLAYER_SURFACES_REQUIRED')
    def inside(a,b):
        return (all(type(v)is int for v in a+b) and len(a)==len(b)==4 and
            b[0]<=a[0]<a[2]<=b[2] and b[1]<=a[1]<a[3]<=b[3])
    crop=overlay['bounds']
    full=area['bounds']
    base.require(full==container['bounds'] and crop==toolbar['bounds'] and crop!=full and
        inside(crop,full) and inside(full,window['bounds']) and window['focused'] is True and
        window['package']==base.BILI and window['display']==0 and window['type']==1,
        'CURRENT_OVERLAY_CROP_MUST_BE_INSIDE_OBSERVED_WINDOW')
    # Geometry assigns two unique observed roles. No traversal-order choice or
    # claim about which renderer produces video/audio is made.
    area_surfaces=[n for n in surfaces if n['bounds']==full]
    crop_surfaces=[n for n in surfaces if n['bounds']==crop]
    base.require(len(area_surfaces)==len(crop_surfaces)==1,
        'UNIQUE_AREA_AND_CROP_SURFACE_GEOMETRY_REQUIRED')
    by_path={n['path']:n for n in nodes};render_rows=[];parent_paths=[]
    for role,rows in (('area-sized',area_surfaces),('crop-sized',crop_surfaces)):
        node,=rows
        parent_path=node['path'].rsplit('/',1)[0]
        parent=by_path.get(parent_path)
        base.require(parent is not None and parent_path.startswith(container['path']+'/') and
            parent['class']=='android.widget.FrameLayout' and parent['class_truncated'] is False and
            parent['resource_id']=='' and parent['resource_id_truncated'] is False and
            parent['bounds']==node['bounds'],'EXACT_SURFACE_PARENT_STRUCTURE_REQUIRED')
        parent_paths.append(parent_path)
        render_rows.append({'role':role,'path_sha256':base.sha(node['path'].encode()),
            'node_sha256':node['node_sha256'],'bounds':node['bounds'],
            'parent_path_sha256':base.sha(parent_path.encode()),'parent_node_sha256':parent['node_sha256']})
    base.require(len(set(parent_paths))==2,'DISTINCT_CURRENT_SURFACE_PARENTS_REQUIRED')
    fixed_rows=[{'role':role,'path_sha256':base.sha(node['path'].encode()),
                 'bounds':node['bounds'],'class':node['class'],'resource_id':node['resource_id']}
        for role,node in (('area',area),('container',container),('overlay',overlay),('toolbar',toolbar))]
    render_structure={'fixed_roles':fixed_rows,'surfaces':render_rows}
    render_structure_sha256=base.sha(qa.canonical(render_structure))
    descendants=[n for n in nodes if n['path'].startswith(container['path']+'/') and n['visible'] is True]
    texts=[n for n in descendants if n['text']]
    base.require(all(n['text_truncated'] is False for n in texts),'PLAYER_TEXT_COMPLETENESS_REQUIRED')
    buffering=[n for n in texts if n['text'].startswith('Buffering...')]
    base.require(len(buffering)<=1,'AMBIGUOUS_BUFFERING_OBSERVATION')
    return {'scope':scope,'window':window,'window_sha256':inspection['window_sha256'],
        'crop':crop,'surface_bounds':crop,'full_area_surface_bounds':full,
        'render_structure':render_structure,'render_structure_sha256':render_structure_sha256,
        'renderer_content_identity_proven':False,'title_text_sha256':TITLE,
        'author_text_sha256':AUTHOR,'buffering_label_present':bool(buffering),
        'buffering_label_sha256':buffering[0]['text_sha256'] if buffering else None,
        'nonempty_player_text_count':len(texts),'video_only_pixels_proven':False}


def inspect(base,prior,qa,flow,session,installed,plan):
    sequence=session.sequence(json.loads(json.dumps(plan)))
    base.require(sequence['installed_before']==sequence['installed_after']==installed and
        sequence['restoration_qualified'] is True and sequence['after_state_completed'] is True and
        sequence['foreground_before']==sequence['foreground_after'],'VIEWPORT_READ_RESTORATION_AND_SCOPE_REQUIRED')
    summaries=base.assessment_summary(prior,qa,flow.step,sequence,plan);row=summaries['inspect']
    raw=base.read(flow.step/(row['nonce']+'.assessment.json'),1048576,row['assessment_sha256'],row['assessment_bytes'])
    assessed=json.loads(raw);helper=assessed['helper'];scope=sequence['foreground_after']
    base.require(assessed['held_transport_returned_after_post_guard'] is True and
        assessed['actual_command_returncode']==0 and assessed['actual_instrumentation_finish_code']==-1 and
        helper['ok'] is True and helper['error'] is None and helper['secondary_errors']==[] and
        helper['self_uid']==base.UID and helper['host_scope_attestation']==scope and
        helper['nonce']==row['nonce'] and helper['op']=='inspect' and
        assessed['wire_sha256']==row['wire_sha256']==base.sha(qa.canonical(helper)),
        'CURRENT_VIEWPORT_ASSESSMENT_REQUIRED')
    proof=viewport(base,qa,helper['inspection'],scope)
    return proof,{'assessments':summaries,'proof':proof,'after_state_completed':True,'restoration_qualified':True}


def same_scope(a,b):
    keys=('scope','window','window_sha256','crop','surface_bounds','title_text_sha256','author_text_sha256',
          'full_area_surface_bounds','render_structure_sha256')
    return all(a[k]==b[k]for k in keys)


def write_private(path,data):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    error=None
    try:
        remaining=memoryview(data)
        while remaining:
            count=os.write(fd,remaining)
            if count<=0:raise OSError('PRIVATE_CROP_SHORT_WRITE')
            remaining=remaining[count:]
        os.fsync(fd)
    except BaseException as exc:
        error=exc;raise
    finally:
        try:os.close(fd)
        except BaseException as close_error:
            if error is None:raise
            error.add_note('private crop close: '+type(close_error).__name__)


def capture(base,prior,qa,flow,session,installed,before,after_plan,index):
    """Never save the full screen or emit a crop before the independent check."""
    record={'index':index,'capture_attempted':False,'private_crop_published':False,
        'atomic_frame_attribution':False,'default_display_uses_original_screencap_convention':True,
        'playback_verified':False,'audio_captured':False}
    primary=None;raw=None;after=None
    try:
        base.require(not flow._private_backend_transport,'NO_NESTED_PRIVATE_VIEWPORT_CAPTURE')
        flow._private_backend_transport=True;began=time.monotonic()
        try:
            record['capture_attempted']=True
            raw=flow.android(['/system/bin/screencap','-p'],20,mutation=False)
        finally:flow._private_backend_transport=False
        record['capture_ms']=int((time.monotonic()-began)*1000)
        base.require(isinstance(raw,bytes) and 33<=len(raw)<=16777216 and
            raw[:16]==b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR','BOUNDED_ORIGINAL_SCREENSHOT_REQUIRED')
        width,height=struct.unpack('>II',raw[16:24])
        base.require(0<width<=4096 and 0<height<=4096 and width*height<=8388608,'SCREENSHOT_PIXEL_BOUND')
        record.update(raw_screen_sha256=base.sha(raw),raw_screen_bytes=len(raw),screen_size=[width,height])
    except BaseException as exc:primary=exc
    finally:
        # A capture failure never skips the independent original state/read
        # sequence. Its failure is secondary and can never authorize pixels.
        try:
            after,observation=inspect(base,prior,qa,flow,session,installed,after_plan)
            record['after_observation']=observation
        except BaseException as exc:
            if primary is None:primary=exc
            else:primary.add_note('independent viewport after: '+type(exc).__name__+': '+str(exc))
    if primary is not None:
        primary.viewport_observation=record
        raise primary
    image=crop_image=None;render_error=None
    try:
        base.require(same_scope(before,after),'VIEWPORT_SCOPE_CHANGED_DURING_CAPTURE')
        backend=flow.contract.load('references/android_backend.py','owned_viewport_png_codec')
        image=backend.png_image(raw);del raw
        rect=backend.valid_rect(before['crop'],image.width,image.height)
        crop_image=image.crop(tuple(rect));png=io.BytesIO();crop_image.save(png,format='PNG');data=png.getvalue()
        base.require(0<len(data)<=1048576,'PRIVATE_CROP_PNG_BOUND')
        path=flow.step/('player-viewport-%02d.png'%index)
        write_private(path,data)
        record.update(private_crop_published=True,private_crop={'path':str(path),'bytes':len(data),
            'sha256':base.sha(data),'pixel_sha256':backend.image_sha(crop_image),'bounds':rect,
            'width':crop_image.width,'height':crop_image.height,'must_not_enter_Git':True},
            scope_checked_before_and_after=True,video_only_pixels_proven=False)
    except BaseException as exc:
        render_error=exc;exc.viewport_observation=record;raise
    finally:
        for value in (crop_image,image):
            if value is not None:
                try:value.close()
                except BaseException as close_error:
                    if render_error is None:render_error=close_error
                    else:render_error.add_note('viewport image close: '+type(close_error).__name__)
        if render_error is not None:
            render_error.viewport_observation=record
            raise render_error
    return after,record


def run(base,prior,qa,flow,session,installed,result):
    record={'maximum_successful_reads':12,'read_deadline_seconds':25,'reads':[],
        'buffering_label_absent_observed':False,'viewport_samples':[],
        'action_replayed':False,'failed_read_retried':False,'audio_captured':False,
        'playback_verified':False,'whole_app_ready':False}
    result['buffer_viewport_observation']=record;result['buffer_viewport_observation_completed']=False
    try:
        base.require(result.get('video_click_and_observations_completed') is True and result['error'] is None,
            'ORIGINAL_COURSE_OPEN_MUST_COMPLETE_BEFORE_VIEWPORT_READS')
        began=time.monotonic();proof=None
        for index,plan in enumerate(PLANS[:12],1):
            if time.monotonic()-began>=25:break
            proof,observation=inspect(base,prior,qa,flow,session,installed,plan)
            observation.update(index=index,elapsed_ms=int((time.monotonic()-began)*1000))
            record['reads'].append(observation)
            base.require(time.monotonic()-began<=25,'BUFFER_OBSERVATION_DEADLINE')
            if not proof['buffering_label_present']:
                record['buffering_label_absent_observed']=True;break
        base.require(proof is not None,'NO_COMPLETE_BUFFER_OBSERVATION')
        # A still-buffering run gets one diagnostic crop but keeps its failure.
        count=3 if record['buffering_label_absent_observed'] else 1
        for index,plan in enumerate(PLANS[12:12+count],1):
            proof,sample=capture(base,prior,qa,flow,session,installed,proof,plan,index)
            record['viewport_samples'].append(sample)
            base.require(not record['buffering_label_absent_observed'] or not proof['buffering_label_present'],
                'BUFFERING_REAPPEARED_DURING_VIEWPORT_OBSERVATION')
        base.require(record['buffering_label_absent_observed'],'BUFFERING_REMAINED_IN_BOUNDED_READS')
        record['final_scope']=proof['scope']
        result['buffer_viewport_observation_completed']=True
    except BaseException as error:
        if hasattr(error,'viewport_observation'):record['failed_capture']=error.viewport_observation
        if hasattr(session,'sequence_observation'):record['last_sequence']=session.sequence_observation
        prior.remember(result,'buffer_viewport_observation',error)
    result['playback_or_audio_success_inferred']=False
