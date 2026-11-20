"""Read-only original expiry05 delivery observers around unchanged expiry06.

Every business method remains in the current original expiry state machine.
Only its existing observation points add the original Notify/audio evidence.
"""
import copy
import hashlib
import time

PACKAGE='com.android.deskclock'


class Delivery:
    def __init__(self,session,monitor,result):
        self.s=session;self.client=monitor;self.r=result;self.started=False;self.stopped=False
        self.final=None;self.sequence=0;self.baseline=None;self.running_text=None;self.basis=None
        self.after_delete=False;self.expired_observed=False
        self.binding=session.components['clock_notify_binding.py'].Binding(session)
        self.proof=session.components['clock_notify_proof.py'];monitor.attach(session)
        self.audio=session.components['clock_audio_observe.py'].Observe(session,session.tx,session.root/'audio-private')

    def start(self):
        c=self.s.c;c.need(not self.started,'ONCE_ORIGINAL_EXPIRY_DELIVERY_OBSERVATION')
        value,self.baseline,ref=self.binding.discover()
        result=self.client.start(ref)
        c.need(type(result) is dict and result.get('state')=='MONITOR_STARTED'
            and result.get('binding')==ref and result.get('match')==self.s.components['clock_notify_binding.py'].monitor_match(value)
            and result.get('child_started') is True,'ACTUAL_CONTINUOUS_NOTIFY_CHILD_START')
        self.started=True;self.r['notify_watch_start']=result;self.r['notify_watch_child_started']=True
        self.audio.start()

    def snapshot(self):
        s=self.s;c=s.c;mod=s.components['clock_notify_binding.py'];self.sequence+=1
        binding=self.binding.guard();current=mod.read_state(binding);capture=self.client.snapshot()
        c.need(type(capture) is dict and set(capture)=={'stdout','receipts','errors','binding','running','bounded',
                'pipe_eof','terminal_observation','started_monotonic','monitor_deadline_monotonic'}
            and capture['binding']==self.binding.ref and capture['bounded'] is True and type(capture['running']) is bool,
            'ACTUAL_BOUNDED_NOTIFY_CAPTURE_SNAPSHOT')
        raw=c.read_ref(capture['stdout'],mod.MAX_BYTES);receipts=c.parse(c.read_ref(capture['receipts'],2097152))
        messages,unparsed=mod.decode_capture(raw,receipts,binding)
        c.need(self.binding.guard()==binding,'NOTIFY_BUS_CHANGED_DURING_SNAPSHOT')
        result={'utc':mod.stamp(),'binding':binding,'baseline':self.baseline,'state':current,'own_state':current,
            'filter':mod.monitor_match(binding),'local_receive_timing_proves_sender_time':False,
            'state_record_changed':current['record']!=self.baseline['record'],
            'id_changed':(current['record'] or {}).get('id')!=(self.baseline['record'] or {}).get('id'),
            'version_changed':(current['record'] or {}).get('version')!=(self.baseline['record'] or {}).get('version'),
            'notify_messages':messages,'raw_calls':messages,'unparsed_complete_lines':unparsed,
            'raw_stdout_bytes':len(raw),'raw_stdout_sha256':hashlib.sha256(raw).hexdigest(),
            'errors':capture['errors'],'desktop_popup_observed':False,'notification_visual_delivery_qualified':False,
            'absence_proves_delivery_failure':False,'continuous_capture':capture}
        c.write_new(s.root/('notify-snapshot-%02d.json'%self.sequence),result);return result

    def running(self,flow):
        self.s.c.need(self.started and self.basis is None,'ONCE_RUNNING_DELIVERY_BASELINE')
        before=time.monotonic_ns();uptime=flow.uptime();after=time.monotonic_ns()
        self.basis={'before_ns':before,'after_ns':after,'uptime_ms':uptime}
        raw=self.s.android(['/system/bin/dumpsys','notification','--noredact','--package',PACKAGE],12)
        self.s.tx.write_new(self.s.root/'running-text-private.txt',raw)
        self.running_text=self.proof.parse_nms(raw)
        self.r['host_notify_running']=self.snapshot();self.r['running_notification_text']=self.running_text

    def expired(self,flow,posted):
        s=self.s;c=s.c;c.need(not self.expired_observed and self.basis is not None,'ONCE_ACTUAL_EXPIRED_DELIVERY_OBSERVATION')
        self.expired_observed=True
        def verify_owned():
            current=s.components['clock_expiry_flow.py'].owned_timer(flow.m.read(s),flow.timer_id,60000)
            c.need(current['state']==3,'AUDIO_REQUIRES_THIS_SOLE_EXPIRED_TIMER')
        verify_owned()
        due=flow.r['expiry_timing']['expected_due_ms']
        self.r['expiry_audio_evidence']=self.audio.expired(verify_owned,due,flow.uptime);verify_owned()
        observed=self.snapshot();self.r['host_notify_expired']=observed
        raw=s.android(['/system/bin/dumpsys','notification','--noredact','--package',PACKAGE],12)
        s.tx.write_new(s.root/'expired-text-private.txt',raw);text=self.proof.parse_nms(raw)
        self.r['expired_notification_text']=text
        scope=self.proof.associate(text,self.running_text,observed,self.r['host_notify_running'],self.basis,due)
        own=[row for row in posted['records'] if row['key']==s.components['clock_expiry_flow.py'].KEY and row['timer_channel']]
        self.r['standard_title_body_to_host_Notify_observed']=bool(len(own)==1 and scope['verified'])
        scope.update(owned_timer_id=flow.timer_id,duration_ms=60000,snapshot_utc=observed['utc'],expiry_timing=flow.r['expiry_timing'])
        self.r['Notify_scope']=scope
        self.r['Notify_scope_context']={'owned_timer_id':flow.timer_id,'duration_ms':60000,
            'expired_key':observed['own_state']['key'],'snapshot_utc':observed['utc'],
            'expiry_timing':copy.deepcopy(flow.r['expiry_timing']),
            'actual_desktop_popup_observed':False,'absence_is_not_App_failure':True}

    def deleted(self):
        self.s.c.need(not self.after_delete,'ONCE_POST_DELETE_NOTIFY_STATE');self.after_delete=True
        self.r['host_notify_after_delete']=self.snapshot()
        self.r['expired_desktop_state_removed']=self.r['host_notify_after_delete']['own_state']['record'] is None

    def stop(self):
        if self.stopped:return self.final
        self.stopped=True;self.final=self.client.stop();return self.final


def make_delivery_flow(original,delivery):
    class DeliveryFlow(original):
        def notifications(self,label):
            result=super().notifications(label)
            if label=='before' and result['records']==[]:delivery.start()
            elif label=='actual-expired':delivery.expired(self,result)
            elif label in ('deleted','deleted-readback-0','deleted-readback-1') and result['records']==[]:
                delivery.deleted()
            return result

        def service(self,label):
            result=super().service(label)
            if label=='after-normal-close':delivery.running(self)
            return result
    return DeliveryFlow
