"""Regression coverage for both permitted Camera video restoration orders.

All inputs are synthetic public-API observations. These tests do not execute
Android, media decoding, physical audio, or whole-application qualification.
"""
from pathlib import Path
import copy
import hashlib
import unittest

source=Path(__file__).with_name('camera_video_state.py')

def namespace(text):
    result={'__name__':'camera_video_state_unit','__file__':str(source)}
    exec(compile(text,str(source),'exec'),result)
    return result
def run_cases(text):
    m=namespace(text); result={}
    def make_ref(label):
        return {'path':'/synthetic-regression/'+label,'bytes':1,'sha256':hashlib.sha256(label.encode()).hexdigest()}
    class Fixture:
        def __init__(self,initial='0'):
            self.now=1_000_000_000
            self.sequence=0; self.mode=initial
            self.scope,self.phase=make_ref('scope'),make_ref('phase')
            self.epoch='e'*64; self.nonce='1234567890abcdef'
            self.focus={'verified':True,'package':m['PACKAGE'],'task':42,'user':0,
                'activity':'com.android.camera.CameraActivity','focused_activity':'com.android.camera.CameraActivity',
                'window_token':'abc'}
            self.record=m['Recording'](nonce=self.nonce,scope=self.scope,phase=self.phase,
                epoch_sha256=self.epoch,task=42,emit=self.emit)
            self.observe(initial)
        def emit(self,event,value):
            self.sequence+=1
            return make_ref(str(self.sequence)+'-'+event)
        def node(self,ident=None,desc=None,text=None,clickable=True):
            n={'package':m['PACKAGE'],'visible':True,'enabled':True,'clickable':clickable,
               'window_id':7,'bounds':[1,1,20,20]}
            if ident:n['resource-id']=ident
            if desc:n['content-desc']=desc
            if text is not None:n['text']=text
            return n
        def observe(self,mode,seconds=None,menu=None,advance=100_000_000):
            self.now+=advance; self.mode=mode
            nodes=[self.node(ident=m['SHUTTER']),self.node(ident=m['MODE_TOGGLE'])]
            if menu:nodes.append(self.node(desc=menu))
            if seconds is not None:
                nodes.append(self.node(ident=m['TIMER'],text='00:'+str(seconds).zfill(2),clickable=False))
            self.native={'ok':True,'outcome_unknown':False,'accessibility_mode_restoration_verified':True,
                'nodes':nodes,'window_context':{'selected_window':{'window_id':7,'display_id':0,
                'focused':True,'type':1,'root':{'package':m['PACKAGE']}}}}
            self.record.observe(value=self.native,focus_value=self.focus,mode=mode,
                monotonic_ns=self.now,observation_ref=make_ref('observation-'+str(self.now)))
        def click(self,action,ident=None,desc=None,ack=True):
            control=m['one_control'](self.native,ident=ident,description=desc)
            request={'op':'click','package':m['PACKAGE'],'display':0,'method':'accessibility',
                'selector':control['selector']}
            self.now+=100_000_000
            self.record.claim(action=action,request=request,control=control,
                focus_value=self.focus,monotonic_ns=self.now)
            if not ack:return
            native_request=dict(request);native_request['expected_package']=native_request.pop('package')
            fields={}
            if ident:fields['resource-id']=ident
            if desc:fields['content-desc']=desc
            reply={'ok':True,'performed':'click','outcome_unknown':False,'automatic_retry':False,
                'accessibility_mode_restoration_verified':True,'target':fields,'actual_target':fields}
            self.now+=100_000_000
            self.record.native_return(request=native_request,reply=reply,monotonic_ns=self.now,
                boundary_ref=make_ref('native-'+action))
            self.record.dispatch_return({'ok':True,'outcome_unknown':False})
        def saved(self):
            if self.mode=='0':
                self.click('mode_menu',ident=m['MODE_TOGGLE'])
                self.observe('0',menu=m['VIDEO_DESCRIPTION'])
                self.click('select_video',desc=m['VIDEO_DESCRIPTION']);self.observe('1')
            self.click('start',ident=m['SHUTTER']);self.observe('1',seconds=0)
            self.observe('1',seconds=2,advance=2_000_000_000)
            self.click('stop',ident=m['SHUTTER']);self.observe('1')
            self.row={'is_pending':0,'owner_package_name':m['PACKAGE'],'file_sha256':'f'*64,
                '_size':16000,'uri':'content://media/external_primary/video/media/999'}
            decode={'full_video_decode':True,'full_audio_decode':True,'file_sha256':'f'*64,
                'file_bytes':16000,'uri':self.row['uri'],'nonce':self.nonce}
            self.record.saved(self.row,make_ref('row'),decode,make_ref('decode'))
        def playback(self):
            common={'nonce':self.nonce,'epoch_sha256':self.epoch,'uri':self.row['uri'],
                'file_sha256':'f'*64,'scope':self.scope,'phase':self.phase,'outcome_unknown':False}
            audio={**common,'decoded_own_audio_nonce_match':True,'CAMCORDER_uid':10062,
                'actual_HAL_input_session_bound':True,'actual_physical_source_bound':True,
                'baseline_negative_passed':True,'decoy_negative_passed':True}
            playback={**common,'actual_owned_uri_intent':True,'actual_video_frames_advanced':True,
                'actual_Android_output_session_bound':True,'physical_playback_nonce_match':True,
                'owned_player_closed':True,'foreign_tasks_unchanged':True}
            self.record.audio_and_playback(audio_ref=make_ref('audio'),audio=audio,
                playback_ref=make_ref('playback'),playback=playback)
        def restore(self):
            self.click('restore_menu',ident=m['MODE_TOGGLE'])
            self.observe('1',menu=m['PHOTO_DESCRIPTION'])
            self.click('restore_photo',desc=m['PHOTO_DESCRIPTION']);self.observe('0')
        def terminal(self,**changes):
            args={'final_mode':self.mode,'task_closed':True,'preserved_state':True,'host_retired':True}
            args.update(changes)
            return self.record.terminal(**args)
    f=Fixture();f.saved();f.playback();f.restore()
    t=f.terminal()
    result['playback_then_restore_photo']={'passed':t['camera_video_verified'] is True,
        'observed_state':f.record.state,'observed_terminal':t['state']}
    f=Fixture();f.saved();f.restore();f.playback()
    result['restore_photo_then_playback']={'passed':f.terminal()['camera_video_verified'] is True}
    f=Fixture('1');f.saved();f.playback()
    result['original_video_mode']={'passed':f.terminal()['camera_video_verified'] is True}
    f=Fixture();f.saved();f.restore()
    result['no_audio_playback_rejected']={'passed':f.terminal()['camera_video_verified'] is False}
    f=Fixture();f.saved();f.playback();f.restore()
    for key,changes in [('wrong_final_mode_rejected',{'final_mode':'1'}),
        ('unretired_host_rejected',{'host_retired':False}),
        ('unclosed_task_rejected',{'task_closed':False}),
        ('unpreserved_state_rejected',{'preserved_state':False})]:
        result[key]={'passed':f.terminal(**changes)['camera_video_verified'] is False}
    f=Fixture();f.saved();f.playback();f.click('restore_menu',ident=m['MODE_TOGGLE'],ack=False)
    t=f.terminal()
    result['unacknowledged_restore_rejected']={'passed':t['camera_video_verified'] is False and t['outcome_unknown'] is True}
    return result

class CameraVideoRestorationOrderTests(unittest.TestCase):
    def test_public_api_ordering_and_refusals(self):
        for name,result in run_cases(source.read_text()).items():
            with self.subTest(case=name):
                self.assertTrue(result['passed'], result)


if __name__ == '__main__':
    unittest.main()
