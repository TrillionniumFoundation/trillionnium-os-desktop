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
NONCES = [['02b04f657feed970a70f3e322ac44661', '8bd5dfb156ab5490655209298ef7c848', 'dd9c4470e57f739f8e57fcd1e7661f92'], ['5c1ea01cf66b0a47f82fd928925fdc34', '8fe8c5d795e3713d22d1630d8bf523da', 'd9eb3d41a3988a6e5a3d7e3f6212cbc5'], ['6796e67a6ba22a719e8dfca8a09eb27a', '5847315401be2251439057948d65fd8b', '60f1cbfeaf46d78668b832a99dfb3ebe'], ['d4d87bd90a0e523006074d8b41abf8ba', '44f70c5b17adc9bddeaf02128098b1be', 'c114249050bf113e0851b9bf59f7e41f'], ['08dce0aa4ed95b7efcffb1211799a24d', 'ac9c05a63772adf590e125cf3e768123', '5b7e09fa8427e9ace7d44596c20ab164'], ['4ed18df9369b4fa0cf0419730d1160a5', 'bcd6aeba50f384901e263e1f72306978', 'c84b0df7a61e259700cd837461a982a3'], ['a929697436f945580757937477d2731c', '8b9b62c323efa48fedf2eb1b4571d4f0', 'c33d4c2a7bea19fcde38af45c918837b'], ['0d06e5da259178153d71f8a2df2257a2', '03c540f478a6f76cdf6e2210611fccc0', '4ec5b09913fe1ec6608348d7669f96bb'], ['2fe555eaa5ccdaba5443f091a7094cbe', 'd46c9cd8c33f59aa03b4eadf25ce21e5', '410a2005384bec3b91db5c0a4320f29d'], ['1e57f000f9abfdd4fe8af7b1551aef3c', 'e2be7dc1a09e44a7ac64476354624fd0', 'af65ef5f4ac3ee087098830e7055415b'], ['e89f69e74082ea9a1701f9cba9151bf9', '6d4b7bb54fd445fa55da3f701fc12d3b', 'a4779c1a953263c5139f82621480b5fd'], ['4fa4669626dd43a7dc272dd6a7aa34f3', '5011d5c9d2dfc50239e7d321a9f8d0c8', '68eee4337cd0d7066655b57872536941'], ['95508c1dc30fa77664c766612a0c6dc4', '9d992eb0f7504e856d7c9002f3f1476f', '303ca2425a78f2fab0d578ff661e88e9'], ['9a3cc12cae59986247d21c34320c5392', '38b51d70be5b3cfb9b0fc5169059bcec', '2b8c080cda45004c1124944daf51beb7'], ['930892e678d4bb88d6b59070ee97bdb6', '087b9c657c9de6d82b0c01fa9d565bc3', 'ea33708a235a6ee928bd7bafc951eb53'], ['65639b2af171a5d93b93da7d5782f7ce', '33c2a7c94c848821471a41ab58351b6f', '9b19466a3ce9921c42d49302244b3bde'], ['2a77e81cce50c52da9bfcf3ca1f9d72a', '6dc4166396c10395929c7dd557b07953', 'aaf7b43fb6b2ce1c000ea6a16f0d67b9'], ['f81c934bf260e10e4db3b61bc5930279', 'a519199d1d99892d6d0616dd85e1277a', '42e0a4b532e284a5e24222fd606c0375']]
PLANS=[{'schema':1,'operation':'inspect','nonces':dict(zip(('before','inspect','after'),row))}for row in NONCES]


def validate(adapter,qa,used):
    values=[x for row in NONCES for x in row]
    qa.require(len(NONCES)==18 and all(len(row)==3 for row in NONCES) and
        len(values)==len(set(values))==54 and not set(values)&set(used),'FIXED_FRESH_VIEWPORT_NONCES')
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


def capture(base,prior,qa,flow,session,installed,before_plan,after_plan,index,*,allow_buffering=False):
    """Never save the full screen or emit a crop before the independent check."""
    record={'index':index,'capture_attempted':False,'private_crop_published':False,
        'atomic_frame_attribution':False,'default_display_uses_original_screencap_convention':True,
        'playback_verified':False,'audio_captured':False,'fresh_before_read_completed':False}
    # Every capture obtains new authority. The previous transaction's after
    # observation is evidence only, never the next screenshot's coordinate proof.
    try:
        before,before_observation=inspect(base,prior,qa,flow,session,installed,before_plan)
        record['before_observation']=before_observation
        record['fresh_before_read_completed']=True
        base.require(allow_buffering or not before['buffering_label_present'],
            'BUFFERING_REAPPEARED_BEFORE_CAPTURE')
    except BaseException as error:
        error.viewport_observation=record
        raise
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
        'fresh_before_read_per_capture':True,'maximum_capture_transactions':3,
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
        for index in range(1,count+1):
            before_plan,after_plan=PLANS[12+2*(index-1):14+2*(index-1)]
            proof,sample=capture(base,prior,qa,flow,session,installed,before_plan,after_plan,index,
                allow_buffering=not record['buffering_label_absent_observed'])
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
