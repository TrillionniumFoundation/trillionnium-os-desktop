"""Original standard Notify observation, bound to this actual new presenter.

Only bus metadata and the existing notification state are read. No service is
activated, no Notify is sent, and unknown monitor grammar remains unqualified.
"""
from datetime import datetime,timezone
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat

NAME='org.freedesktop.Notifications'
OBJECT='/org/freedesktop/Notifications'
KEY='0|com.android.deskclock|2147483644|null|10063'
STATE=Path('/run/user/1000/droidloom/notifications.state')
BUSCTL={'path':'/usr/bin/busctl','bytes':92776,'sha256':'df6999b51c9f774e871065ff8e7884cd1c72a3ff6b85418fe4269734f93fd60a'}
MAX_BYTES=1048576
MAX_SECONDS=240
UNIQUE=re.compile(r':[0-9]+\.[0-9]+')
PREFIX=['/usr/sbin/runuser','-u','alex','--',BUSCTL['path'],
    '--address=unix:path=/run/user/1000/bus','--no-pager','--auto-start=no',
    '--allow-interactive-authorization=no','--timeout=3']
BUS_CALL=['call','org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus']


def need(value,why):
    if not value:raise RuntimeError(why)


def stamp():return datetime.now(timezone.utc).isoformat()


def tool_identity():
    path=Path(BUSCTL['path']);need(path.resolve(strict=True)==path,'EXACT_ORIGINAL_BUSCTL_PATH')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid==0 and before.st_nlink>=1
            and not before.st_mode&0o022 and before.st_size==BUSCTL['bytes'],'ORIGINAL_BUSCTL_FILE_SCOPE')
        h=hashlib.sha256();size=0
        while True:
            block=os.read(fd,65536)
            if not block:break
            size+=len(block);need(size<=BUSCTL['bytes'],'ORIGINAL_BUSCTL_GREW');h.update(block)
        keys=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
        after=os.fstat(fd);named=path.lstat()
        need(size==BUSCTL['bytes'] and h.hexdigest()==BUSCTL['sha256'] and
            all(getattr(before,k)==getattr(after,k)==getattr(named,k) for k in keys),'ORIGINAL_BUSCTL_CHANGED')
        return {'source':BUSCTL,'held_file':{k:getattr(before,k) for k in keys}}
    finally:os.close(fd)


def presenter_sender(raw,pid):
    rows=json.loads(raw)
    need(type(rows) is list and len(rows)<=4096,'BOUNDED_ACTUAL_BUSCTL_LIST')
    names=[]
    for row in rows:
        need(type(row) is dict and set(row)=={'name','pid','process','user','connection','unit','session','description'},
            'ACTUAL_BUSCTL_LIST_SCHEMA')
        if type(row['name']) is str and UNIQUE.fullmatch(row['name']) and row['pid']==pid:
            need(type(row['pid']) is int and row['user']=='alex' and row['connection']==row['name'],
                'FRESH_PRESENTER_BUS_CONNECTION_IDENTITY')
            names.append(row['name'])
    need(len(names)==1,'ONE_ACTUAL_NEW_PRESENTER_UNIQUE_BUS_NAME')
    return names[0]


def monitor_match(binding):
    need(UNIQUE.fullmatch(binding['sender']) and UNIQUE.fullmatch(binding['owner'])
        and re.fullmatch('[0-9a-f]{32}',binding['bus_id']),'ACTUAL_NOTIFY_BINDING_GRAMMAR')
    return "type='method_call',sender='%s',path='%s',interface='%s',member='Notify',arg0='Clock'"%(binding['sender'],OBJECT,NAME)


def monitor_argv(binding):
    return [BUSCTL['path'],'--address=unix:path=/run/user/1000/bus','--no-pager',
        '--auto-start=no','--allow-interactive-authorization=no','--json=short',
        '--match='+monitor_match(binding),'-N','32','monitor']


def selected_message(value,binding):
    need(isinstance(value,dict) and value.get('type')=='method_call'
        and value.get('sender')==binding['sender'] and value.get('path')==OBJECT
        and value.get('interface')==NAME and value.get('member')=='Notify'
        and value.get('destination') in (NAME,binding['owner']),'NOT_EXACT_CLOCK_NOTIFY')
    body=value.get('payload',{})
    need(isinstance(body,dict) and body.get('type')=='susssasa{sv}i','NOTIFY_PAYLOAD_GRAMMAR')
    args=body.get('data')
    need(isinstance(args,list) and len(args)==8 and args[0]=='Clock'
        and type(args[1]) is int and 0<=args[1]<=0xffffffff
        and all(isinstance(args[i],str) for i in (2,3,4))
        and len(args[3])<=8192 and len(args[4])<=65536,'NOTIFY_ARGUMENT_GRAMMAR')
    return {'sender':binding['sender'],'destination':value['destination'],'app':'Clock',
        'replaces_id':args[1],'title':args[3],'body':args[4],
        'cookie':value.get('cookie'),'timestamp_realtime':value.get('timestamp-realtime'),
        'desktop_popup_observed':False}


def read_state(binding):
    fd=os.open(STATE,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid==1000 and before.st_nlink==1
            and 0<before.st_size<=MAX_BYTES,'NOTIFY_STATE_FILE_SCOPE')
        with os.fdopen(os.dup(fd),'rb') as stream:raw=stream.read(MAX_BYTES+1)
        after=os.fstat(fd);named=STATE.lstat()
        keys=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
        need(len(raw)==before.st_size and all(getattr(before,k)==getattr(after,k)==getattr(named,k) for k in keys),
            'NOTIFY_STATE_CHANGED_WHILE_READ')
    finally:os.close(fd)
    value=json.loads(raw)
    need(value.get('owner')==binding['owner'] and value.get('bus_id')==binding['bus_id']
        and isinstance(value.get('records'),dict),'NOTIFY_STATE_BUS_CHANGED')
    record=value['records'].get(KEY)
    if record is not None:
        need(isinstance(record,dict) and set(record)=={'id','version','hidden'}
            and (record['id'] is None or type(record['id']) is int and 0<record['id']<=0xffffffff)
            and isinstance(record['version'],str) and len(record['version'])<=96
            and type(record['hidden']) is bool,'CLOCK_STATE_RECORD_GRAMMAR')
    return {'utc':stamp(),'path':str(STATE),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),
        'owner':binding['owner'],'bus_id':binding['bus_id'],'key':KEY,'record':record,
        'other_record_count':len(value['records'])-(record is not None),
        'file_identity':{k:getattr(before,k) for k in keys}}


def decode_capture(raw,receipts,binding):
    need(type(raw) is bytes and len(raw)<=MAX_BYTES and type(receipts) is list,'BOUNDED_RAW_NOTIFY_CAPTURE')
    previous=0
    for receipt in receipts:
        need(set(receipt)=={'end_byte_offset','monotonic_ns','realtime_ns'}
            and type(receipt['end_byte_offset']) is int and previous<receipt['end_byte_offset']<=len(raw)
            and all(type(receipt[k]) is int and receipt[k]>0 for k in ('monotonic_ns','realtime_ns')),
            'ACTUAL_NOTIFY_LOCAL_READ_RECEIPTS')
        previous=receipt['end_byte_offset']
    need(previous==len(raw),'EVERY_NOTIFY_BYTE_HAS_LOCAL_READ_COMPLETION')
    messages=[];unparsed=[];end=0
    for index,line in enumerate(raw.splitlines(keepends=True)):
        begin=end;end+=len(line)
        if not line.endswith(b'\n') or not line.strip():continue
        receipt=next(row for row in receipts if row['end_byte_offset']>=end)
        timing={'source':'local_read_completion_not_sender_or_delivery_timestamp',
            'chunk_end_byte_offset':receipt['end_byte_offset'],'monotonic_ns':str(receipt['monotonic_ns']),
            'realtime_ns':str(receipt['realtime_ns']),'receive_time_is_upper_bound':True,'line_byte_range':[begin,end]}
        try:
            message=selected_message(json.loads(line),binding);message['local_receive']=timing;messages.append(message)
        except Exception:unparsed.append({'line':index+1,'bytes':len(line),
            'sha256':hashlib.sha256(line).hexdigest(),'local_receive':timing})
    return messages,unparsed


class Binding:
    def __init__(self,session):
        self.s=session;self.value=None;self.pending=None;self.sequence=0;self.queries=[]
        self.presenter=copy.deepcopy(session.baseline.docs['final_baseline']['host_processes']['presenter'])

    def verify_presenter(self):
        self.s.guard();pid=self.presenter['host_pid']
        need(type(pid) is int and pid>1 and self.s.epoch.process_identity(pid)==self.presenter,
            'ACTUAL_FRESH_MAIN_PRESENTER_CHANGED')

    def _query(self,kind,tail):
        need(self.pending is None,'NO_CONCURRENT_NOTIFY_BUS_QUERY');self.sequence+=1
        label='clock-notify-%03d-%s'%(self.sequence,kind);argv=PREFIX+tail
        self.pending=(label,argv,5)
        try:
            result=self.s.run_host(label,argv,5)
            need(result['joined'] is True and result['timed_out'] is False and result['rc']==0,'NOTIFY_BUS_QUERY_UNKNOWN')
            raw=result['stdout'];self.queries.append(self.s.records[-1]);return raw.decode('utf-8','strict')
        finally:self.pending=None

    def run_host(self,label,argv,timeout):
        self.s.original_caller(('clock_notify_binding.py',),{'_query'},skip=('run_host',))
        need(self.pending==(label,argv,timeout),'ONLY_CURRENT_EXACT_READONLY_NOTIFY_BUS_QUERY')
        return self.s._host(label,argv,timeout)

    def discover(self):
        need(self.value is None,'ONCE_NEW_NOTIFY_BINDING');self.verify_presenter();tool=tool_identity()
        sender=presenter_sender(self._query('list',['--json=short','list']),self.presenter['host_pid'])
        bus=re.fullmatch(r's "([0-9a-f]{32})"\s*',self._query('id',BUS_CALL+['GetId']))
        owner=re.fullmatch(r's "(:[0-9]+\.[0-9]+)"\s*',self._query('owner',BUS_CALL+['GetNameOwner','s',NAME]))
        need(bus and owner,'ACTUAL_SESSION_BUS_OWNER_AND_ID')
        self.value={'presenter':self.presenter,'sender':sender,'owner':owner[1],'bus_id':bus[1]}
        self.guard();baseline=read_state(self.value)
        need(baseline['record'] is None,'OLD_EXPIRED_DESKTOP_RECORD_PRESENT')
        record={'schema':'pocket4-clock-current-notify-binding-v1','baseline':self.s.request['baseline'],
            'qualification':self.s.request['qualification'],'phase':self.s.phase_ref,'binding':self.value,
            'tool':tool,'baseline_state':baseline,'queries':copy.deepcopy(self.queries),
            'service_activation_requests':0,'notification_method_calls':0,'Android_UI_actions':0}
        self.ref=self.s.c.write_new(self.s.root/'notify-binding.json',record)
        return self.value,baseline,self.ref

    def guard(self):
        need(self.value is not None,'ACTUAL_NOTIFY_BINDING_REQUIRED');self.verify_presenter()
        checks=[('id',['GetId'],'s "'+self.value['bus_id']+'"'),
            ('owner',['GetNameOwner','s',NAME],'s "'+self.value['owner']+'"'),
            ('sender',['GetConnectionUnixProcessID','s',self.value['sender']],'u '+str(self.presenter['host_pid']))]
        for kind,tail,expected in checks:
            need(self._query(kind,BUS_CALL+tail).strip()==expected,'NOTIFY_BUS_BINDING_CHANGED:'+kind)
        self.verify_presenter();return copy.deepcopy(self.value)
