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
NONCES = [['eaf888515143dc62a02c4b6b5b03fe06', 'e98427b65a90a511d3965b90c5a01ed8', '06b31c9d57b0d8ed2c456e5cb180cf4e'], ['6f43b881c5a2ec181b86927d8af14502', 'd9da08dad2f53b0f9162cf01cc2756be', 'e862bf0e9530fbd78e09072020866a02'], ['3dee279917ccb207fbd72e7aa37dbf8a', 'f6d39264e292996da5532b9794badc78', '144e53d6be71eb8a91a0b0a53f9c4148'], ['bc911b96a364727e7e30d281acf06cc1', 'be091cada3f8dacb7d527a772af48138', 'c8bae27878bdecf91f0477d4152e751c'], ['a32e6093a11aa28c3fc0d2f5876236be', '902909a50130402aadc120c0a1864d81', 'e69c65543353752b0ebed9e434043f35'], ['5e972a9bb1cefe8fdd8331b9aca8078c', 'd309e9a4edda234a22ab532a1caee674', '4e734f1471d30a9de7c635f2b9a560ef'], ['4b2d54d913532be62fa93bde1834a657', '91c5d34151a4f1273bc7edbd90b911ed', '0713e762c12f987e2a513fd6ae2c5d60'], ['d8f4e94f6b91497b18f36c3702f4a358', 'a25724749114b30f19d092dae3993f32', '75efcbd73662ce3372f4d53c4cb41672'], ['7c61e14680e12c51e6ba88e6bee7e818', '69c77c9154d047255cefde66888acb5e', '5b974770107be64372233ed63f39bfab'], ['25e2b239b813e7ceb26152ddc7757404', '565d111d14375f33f4081ca427459adb', 'e822c348ff5f9aaa552aae67bf23e743'], ['0e59f34ff18ee1663b8aaf47155dd43a', 'a69cf4dc046dcb28c523f8a8e9f82c1e', 'aa4117e81be4a03261315485238a6360'], ['1a0ac2c49ae03616ba626af7e0446a36', '2b098f6dd7360feb9d5483a2f275af90', '2dbb8196ebe09c168ccc03a2112d2627'], ['cb05efe3578391daa5692a350bf80914', 'c3aa42c04200c0de14f79489bc9e22c2', '498a7a9ed1da750df60745f3f4b876b4'], ['1d540482109bb59a3ba5cbd3bb474b8f', '7f8182ec5eab68eb2925402e55b2f936', '417b97f95cad87ef410734325645c7b9'], ['9c7ae1c70cf22051ab34c3125ba02746', '1137f065244c218a7fd74d0c10fedc1b', '16a0aa38d1d5450713eaee435d11ca36']]
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
    surfaces=[n for n in nodes if n['class']=='android.view.SurfaceView' and
        n['class_truncated'] is False and n['visible'] is True and n['enabled'] is True and
        n['password'] is False and n['path'].startswith(container['path']+'/')]
    base.require(len(surfaces)==1 and container['path'].startswith(area['path']+'/') and
        overlay['path'].startswith(area['path']+'/'),'UNIQUE_CURRENT_PLAYER_STRUCTURE_REQUIRED')
    def inside(a,b):
        return (all(type(v)is int for v in a+b) and len(a)==len(b)==4 and
            b[0]<=a[0]<a[2]<=b[2] and b[1]<=a[1]<a[3]<=b[3])
    crop=overlay['bounds']
    base.require(crop==toolbar['bounds'] and inside(crop,surfaces[0]['bounds']) and
        inside(surfaces[0]['bounds'],window['bounds']) and window['focused'] is True and
        window['package']==base.BILI and window['display']==0 and window['type']==1,
        'CURRENT_OVERLAY_CROP_MUST_BE_INSIDE_OBSERVED_WINDOW')
    descendants=[n for n in nodes if n['path'].startswith(container['path']+'/') and n['visible'] is True]
    texts=[n for n in descendants if n['text']]
    base.require(all(n['text_truncated'] is False for n in texts),'PLAYER_TEXT_COMPLETENESS_REQUIRED')
    buffering=[n for n in texts if n['text'].startswith('Buffering...')]
    base.require(len(buffering)<=1,'AMBIGUOUS_BUFFERING_OBSERVATION')
    return {'scope':scope,'window':window,'window_sha256':inspection['window_sha256'],
        'crop':crop,'surface_bounds':surfaces[0]['bounds'],'title_text_sha256':TITLE,
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
    keys=('scope','window','window_sha256','crop','surface_bounds','title_text_sha256','author_text_sha256')
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
