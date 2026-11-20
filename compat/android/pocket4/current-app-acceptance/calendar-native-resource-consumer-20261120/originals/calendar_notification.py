"""Exact Calendar-only NMS evidence. Android delivery is separate from desktop/sound/action evidence."""
import hashlib,re
PACKAGE='com.android.calendar'
UID=10061
CHANNEL='calendar-events-restored-v1'
def need(v,reason):
    if not v:raise RuntimeError(reason)
def blocks(text):
    lines=text.splitlines()
    need(lines and lines[0]=="Current Notification Manager state (filtered to 'com.android.calendar'):",
         'EXACT_CALENDAR_NOTIFICATION_FILTER_UNKNOWN')
    starts=[i for i,line in enumerate(lines) if line=='  Notification List:']
    need(len(starts)==1,'ACTIVE_NOTIFICATION_SECTION_UNKNOWN')
    active=[]
    for line in lines[starts[0]+1:]:
        if line.strip() and not line.startswith('    '):break
        active.append(line)
    chunks=re.split(r'(?=^    NotificationRecord\()', '\n'.join(active),flags=re.M)
    need(not chunks[0].strip(),'ACTIVE_NOTIFICATION_RECORD_FORMAT_UNKNOWN')
    need(len(chunks)<=33,'CALENDAR_NOTIFICATION_BOUND')
    return chunks[1:]
def project(text,marker,alert_id=None):
    rows=blocks(text);result={'active_calendar_count':len(rows),'present':False,
        'Android_notification_manager_only':True,'desktop_visible_inferred':False,
        'sound_inferred':False,'host_action_inferred':False}
    if alert_id is None:return result
    need(type(alert_id) is int and alert_id>0,'OWNED_ALERT_ID_REQUIRED')
    tag='calendar-alert-'+str(alert_id);key='0|'+PACKAGE+'|0|'+tag+'|'+str(UID)
    selected=[row for row in rows if re.search(r'\bkey='+re.escape(key)+r'(?:\s|$)',row)]
    need(len(selected)<=1,'OWNED_CALENDAR_NOTIFICATION_DUPLICATE')
    result.update(key=key,tag=tag,notification_id=0)
    if not selected:return result
    row=selected[0]
    valid=(re.search(r'\buid=10061\b',row) is not None and 'user=UserHandle{0}' in row and
        re.search(r'\bchannel='+re.escape(CHANNEL)+r'(?:\s|$)',row) is not None and
        re.search(r'android\.title=String \('+re.escape(marker)+r'\)',row) is not None)
    result.update(present=True,source_bound_uid_channel_title=bool(valid),
        record_sha256=hashlib.sha256(row.encode()).hexdigest(),
        observed_action_label_strings=[s for s in ('Snooze 10 min','Dismiss') if s in row])
    return result
class Evidence:
    def __init__(self,session,tx,root,marker):
        self.s,self.tx,self.root,self.marker=session,tx,root,marker;self.sequence=0
    def read(self,label,alert_id=None):
        self.s.guard()
        raw=self.s.android(['/system/bin/dumpsys','notification','--noredact','--package',PACKAGE],12)
        need(len(raw)<=4*1024*1024,'CALENDAR_NMS_BYTE_BOUND')
        self.sequence+=1
        proof=self.tx.write_new(self.root/('%03d-'%self.sequence+label+'-nms-private.txt'),raw)
        result=project(raw.decode('utf-8','strict'),self.marker,alert_id)
        result['raw_private_receipt']=proof;self.s.guard();return result
