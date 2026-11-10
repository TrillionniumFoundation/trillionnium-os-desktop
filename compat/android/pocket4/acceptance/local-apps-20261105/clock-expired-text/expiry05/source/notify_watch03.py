"""Bounded, read-only Clock Notify capture on the already-running host session bus.

No Android commands, service activation, notification method calls, or UI input.
Unknown monitor grammar is retained privately and never counted as delivery proof.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, os, re, select, signal, stat, subprocess, threading, time

SENDER=':1.808414'
PRESENTER_PID=3588024
OWNER=':1.311419'
BUS_ID='f93731a024b4e445a5dd308b6ade9dda'
NAME='org.freedesktop.Notifications'
OBJECT='/org/freedesktop/Notifications'
STATE=Path('/run/user/1000/droidloom/notifications.state')
KEY='0|com.android.deskclock|2147483644|null|10063'
MATCH="type='method_call',sender='%s',path='%s',interface='%s',member='Notify',arg0='Clock'"%(SENDER,OBJECT,NAME)
MAX_BYTES=1024*1024
MAX_SECONDS=240
SYSTEM_TOOL_PINS = {'/usr/bin/busctl': {'canonical': '/usr/bin/busctl', 'bytes': 92776, 'sha256': 'df6999b51c9f774e871065ff8e7884cd1c72a3ff6b85418fe4269734f93fd60a'}, '/usr/bin/timeout': {'canonical': '/usr/lib/cargo/bin/coreutils/timeout', 'bytes': 11807104, 'sha256': 'f84e76ea4da1e0c4e92254bd0d7dccdabe2c8b3098e734f27997dae3ee5d8e02'}}


def need(ok, reason):
    if not ok: raise RuntimeError(reason)


def stamp(): return datetime.now(timezone.utc).isoformat()


def digest(raw): return hashlib.sha256(raw).hexdigest()


def selected_message(value):
    """Only a positively decoded exact Notify is evidence; raw capture is separate."""
    need(isinstance(value,dict) and value.get('type')=='method_call'
        and value.get('sender')==SENDER and value.get('path')==OBJECT
        and value.get('interface')==NAME and value.get('member')=='Notify'
        and value.get('destination') in (NAME,OWNER),'NOT_EXACT_CLOCK_NOTIFY')
    body=value.get('payload',{})
    need(isinstance(body,dict) and body.get('type')=='susssasa{sv}i','NOTIFY_PAYLOAD_GRAMMAR')
    args=body.get('data')
    need(isinstance(args,list) and len(args)==8 and args[0]=='Clock'
        and type(args[1]) is int and 0<=args[1]<=0xffffffff
        and all(isinstance(args[i],str) for i in (2,3,4))
        and len(args[3])<=8192 and len(args[4])<=65536,'NOTIFY_ARGUMENT_GRAMMAR')
    return {'sender':SENDER,'destination':value['destination'],'app':'Clock',
        'replaces_id':args[1],'title':args[3],'body':args[4],
        'cookie':value.get('cookie'),'timestamp_realtime':value.get('timestamp-realtime'),
        'desktop_popup_observed':False}


def system_tool(path):
    """Resolve the reviewed root-owned tool; hard links are valid system inputs."""
    expected=SYSTEM_TOOL_PINS[path]
    entry=Path(path);entry_stat=entry.lstat();canonical=entry.resolve(strict=True)
    need(entry_stat.st_uid==0 and str(canonical)==expected['canonical'],'MONITOR_TOOL_ENTRY_CHANGED')
    fd=os.open(canonical,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid==0 and before.st_nlink>=1
            and not before.st_mode&0o022 and before.st_size==expected['bytes']
            and before.st_size<=64*1024*1024,'MONITOR_CANONICAL_TOOL_SCOPE')
        h=hashlib.sha256()
        while True:
            chunk=os.read(fd,65536)
            if not chunk:break
            h.update(chunk)
        after=os.fstat(fd)
        attrs=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_nlink','st_mode','st_uid')
        need(all(getattr(before,k)==getattr(after,k) for k in attrs)
            and h.hexdigest()==expected['sha256'],'MONITOR_CANONICAL_TOOL_CHANGED')
    finally:os.close(fd)
    return {'entry':path,'canonical':str(canonical),'bytes':before.st_size,
        'sha256':h.hexdigest(),'nlink':before.st_nlink,'mode':stat.S_IMODE(before.st_mode)}


class Watch:
    def __init__(self,session,tx,out):
        self.s,self.tx,self.out=session,tx,Path(out)
        self.process=None; self.pidfd=-1; self.thread=None; self.started=False; self.stopped=False
        self.lock=threading.Lock(); self.sequence=0; self.errors=[]; self.counts={'stdout':0,'stderr':0}
        self.eof={'stdout':False,'stderr':False}; self.baseline=None; self.final=None
        self.stdout=bytearray(); self.stderr=bytearray(); self.started_at=None; self.stdout_receipts=[]

    def _guard_bus(self,label):
        self.s.guard()
        presenter=self.s.activation['presenter_process']
        need(presenter['host_pid']==PRESENTER_PID,'PINNED_PRESENTER_PID_CHANGED')
        need(self.s.epoch.process_identity(PRESENTER_PID)==presenter,'PINNED_PRESENTER_IDENTITY_CHANGED')
        prefix=[self.tx.RUNUSER,'-u','alex','--','/usr/bin/busctl',
            '--address=unix:path=/run/user/1000/bus','--no-pager','--auto-start=no',
            '--allow-interactive-authorization=no','--timeout=3','call','org.freedesktop.DBus',
            '/org/freedesktop/DBus','org.freedesktop.DBus']
        checks=[('id',['GetId'],'s "'+BUS_ID+'"'),
            ('owner',['GetNameOwner','s',NAME],'s "'+OWNER+'"'),
            ('sender',['GetConnectionUnixProcessID','s',SENDER],'u '+str(PRESENTER_PID))]
        for suffix,argv,expected in checks:
            r=self.s.run_host('clock-notify-'+label+'-'+suffix,prefix+argv,5)
            need(r['joined'] and not r['timed_out'] and r['rc']==0,'NOTIFY_BUS_QUERY_UNKNOWN')
            raw=r['stdout']; raw=raw.decode('utf-8','strict') if isinstance(raw,bytes) else raw
            need(raw.strip()==expected,'NOTIFY_BUS_BINDING_CHANGED:'+suffix)
        self.s.guard()
        return {'presenter':presenter,'sender':SENDER,'owner':OWNER,'bus_id':BUS_ID}

    def _state(self):
        fd=os.open(STATE,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
        try:
            before=os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and before.st_uid==1000 and before.st_nlink==1
                and 0<before.st_size<=1024*1024,'NOTIFY_STATE_FILE_SCOPE')
            raw=b''
            while len(raw)<before.st_size:
                part=os.read(fd,min(65536,before.st_size-len(raw)));need(part,'NOTIFY_STATE_TRUNCATED');raw+=part
            after=os.fstat(fd)
            attrs=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
            need(all(getattr(before,k)==getattr(after,k) for k in attrs),'NOTIFY_STATE_CHANGED_WHILE_READ')
        finally:os.close(fd)
        value=json.loads(raw)
        need(value.get('owner')==OWNER and value.get('bus_id')==BUS_ID
            and isinstance(value.get('records'),dict),'NOTIFY_STATE_BUS_CHANGED')
        record=value['records'].get(KEY)
        if record is not None:
            need(isinstance(record,dict) and set(record)=={'id','version','hidden'}
                and (record['id'] is None or type(record['id']) is int and 0<record['id']<=0xffffffff)
                and isinstance(record['version'],str) and len(record['version'])<=96
                and type(record['hidden']) is bool,'CLOCK_STATE_RECORD_GRAMMAR')
        return {'utc':stamp(),'path':str(STATE),'sha256':digest(raw),'bytes':len(raw),
            'owner':OWNER,'bus_id':BUS_ID,'key':KEY,'record':record,
            'other_record_count':len(value['records'])-(record is not None)}

    def _signal_owned(self,number):
        with self.lock:
            if self.process is None:return
            if self.pidfd>=0:
                poller=select.poll();poller.register(self.pidfd,select.POLLIN)
                if poller.poll(0): return
            else:
                # Only the immediate Popen startup path can lack pidfd. The
                # unreaped child PID is still reserved; do not poll/reap first.
                need(self.process.returncode is None,'MONITOR_CHILD_ALREADY_REAPED')
            need(os.getpgid(self.process.pid)==self.process.pid,'MONITOR_PRIVATE_GROUP_CHANGED')
            os.killpg(self.process.pid,number)

    def _drain(self):
        pipes={self.process.stdout.fileno():'stdout',self.process.stderr.fileno():'stderr'}
        files={name:open(self.out/('monitor.'+name),'xb') for name in ('stdout','stderr')}
        deadline=time.monotonic()+MAX_SECONDS
        try:
            while pipes:
                if time.monotonic()>=deadline:
                    self.errors.append('MONITOR_LEASE_EXPIRED');self._signal_owned(signal.SIGKILL);break
                ready,_,_=select.select(list(pipes),[],[],.2)
                for fd in ready:
                    name=pipes[fd];data=os.read(fd,65536)
                    if not data:self.eof[name]=True;del pipes[fd];continue
                    remain=MAX_BYTES-self.counts[name]
                    chunk=data[:remain]
                    files[name].write(chunk);files[name].flush()
                    with self.lock:
                        getattr(self,name).extend(chunk);self.counts[name]+=len(chunk)
                        if name=='stdout' and chunk:
                            self.stdout_receipts.append({'end_byte_offset':self.counts[name],
                                'monotonic_ns':time.monotonic_ns(),'realtime_ns':time.time_ns()})
                    if len(data)>remain:
                        self.errors.append('MONITOR_OUTPUT_LIMIT:'+name)
                        self._signal_owned(signal.SIGKILL);return
        except BaseException as exc:self.errors.append(type(exc).__name__+': '+str(exc))
        finally:
            for stream in files.values():stream.flush();os.fsync(stream.fileno());stream.close()

    def start(self):
        need(not self.started,'NOTIFY_WATCH_ALREADY_STARTED')
        self.started=True
        self.out.mkdir(mode=0o700)
        try:
            binding=self._guard_bus('before');self.baseline=self._state()
            tool_pins={path:system_tool(path) for path in ('/usr/bin/timeout','/usr/bin/busctl')}
            # timeout is only our child lease; its private process group contains busctl.
            argv=['/usr/bin/timeout','--signal=TERM','--kill-after=1',str(MAX_SECONDS),
                tool_pins['/usr/bin/busctl']['canonical'],'--address=unix:path=/run/user/1000/bus','--no-pager',
                '--auto-start=no','--allow-interactive-authorization=no','--json=short',
                '--match='+MATCH,'-N','32','monitor']
            self.tx.write_new(self.out/'start-intent.json',{'argv':argv,'binding':binding,
                'match':MATCH,'user':1000,'group':1000,'max_bytes_per_stream':MAX_BYTES,
                'max_seconds':MAX_SECONDS,'tool_pins':tool_pins,'automatic_retry':False})
            self.started_at=stamp()
            self.process=subprocess.Popen(argv,executable=tool_pins['/usr/bin/timeout']['canonical'],
                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,start_new_session=True,close_fds=True,user=1000,group=1000,
                extra_groups=[],env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8',
                    'XDG_RUNTIME_DIR':'/run/user/1000','DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/1000/bus'})
            self.pidfd=os.pidfd_open(self.process.pid,0)
            need(os.getpgid(self.process.pid)==self.process.pid,'MONITOR_NOT_PRIVATE_GROUP')
            self.thread=threading.Thread(target=self._drain,name='owned-clock-notify-watch',daemon=False)
            self.thread.start()
            self.s.guard()
            return {'state':'MONITOR_STARTED','pid':self.process.pid,'match':MATCH,'baseline':self.baseline,
                'subscription_ready_verified':False,'absence_proves_delivery_failure':False,
                'service_activation_requests':0,'UI_actions':0,'notification_method_calls':0}
        except BaseException:
            self.stop();raise

    def snapshot(self):
        need(self.started and not self.stopped,'NOTIFY_WATCH_NOT_ACTIVE')
        self.sequence+=1;binding=self._guard_bus('snapshot-'+str(self.sequence));current=self._state()
        with self.lock:
            raw=bytes(self.stdout);errors=list(self.errors);receipts=list(self.stdout_receipts)
        complete=raw.splitlines(keepends=True);messages=[];unparsed=[];end_byte_offset=0
        for index,line in enumerate(complete):
            begin_byte_offset=end_byte_offset;end_byte_offset+=len(line)
            if not line.endswith(b'\n'):continue
            if not line.strip():continue
            receipt=next((r for r in receipts if r['end_byte_offset']>=end_byte_offset),None)
            need(receipt is not None,'COMPLETE_NOTIFY_LINE_HAS_NO_LOCAL_RECEIPT')
            timing={'source':'local_read_completion_not_sender_or_delivery_timestamp',
                'chunk_end_byte_offset':receipt['end_byte_offset'],
                'monotonic_ns':str(receipt['monotonic_ns']),'realtime_ns':str(receipt['realtime_ns']),
                'receive_time_is_upper_bound':True,'line_byte_range':[begin_byte_offset,end_byte_offset]}
            try:
                message=selected_message(json.loads(line));message['local_receive']=timing;messages.append(message)
            except Exception:
                unparsed.append({'line':index+1,'bytes':len(line),'sha256':digest(line),'local_receive':timing})
        need(self._guard_bus('snapshot-'+str(self.sequence)+'-after')==binding,
            'NOTIFY_BUS_CHANGED_DURING_SNAPSHOT')
        result={'utc':stamp(),'binding':binding,'baseline':self.baseline,'state':current,
            'own_state':current,'filter':MATCH,'local_receive_timing_proves_sender_time':False,
            'state_record_changed':current['record']!=self.baseline['record'],
            'id_changed':(current['record'] or {}).get('id')!=(self.baseline['record'] or {}).get('id'),
            'version_changed':(current['record'] or {}).get('version')!=(self.baseline['record'] or {}).get('version'),
            'notify_messages':messages,'raw_calls':messages,'unparsed_complete_lines':unparsed,'raw_stdout_bytes':len(raw),
            'raw_stdout_sha256':digest(raw),'errors':errors,'desktop_popup_observed':False,
            'notification_visual_delivery_qualified':False,'absence_proves_delivery_failure':False}
        self.tx.write_new(self.out/('snapshot-%02d.json'%self.sequence),result)
        return result

    def stop(self):
        if self.stopped:return self.final
        joined=False;error=None
        try:
            if self.process is not None:
                self._signal_owned(signal.SIGTERM)
                try:self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._signal_owned(signal.SIGKILL);self.process.wait(timeout=3)
                joined=True
            if self.thread is not None:self.thread.join(timeout=3)
            need(self.thread is None or not self.thread.is_alive(),'MONITOR_READER_NOT_JOINED')
        except BaseException as exc:error=type(exc).__name__+': '+str(exc)
        finally:
            if self.pidfd>=0:os.close(self.pidfd);self.pidfd=-1
            if self.process is not None and (self.thread is None or not self.thread.is_alive()):
                self.process.stdout.close();self.process.stderr.close()
            self.stopped=True
        self.final={'stopped_utc':stamp(),'started_utc':self.started_at,
            'owned_process_joined':joined,'reader_joined':self.thread is None or not self.thread.is_alive(),
            'child_joined':joined,'filter':MATCH,
            'pipe_eof':dict(self.eof),'returncode':None if self.process is None else self.process.returncode,
            'bytes':dict(self.counts),'errors':list(self.errors),'cleanup_error':error,
            'all_owned_monitor_writers_closed':joined and all(self.eof.values()) and error is None,
            'notification_method_calls':0,'UI_actions':0,'service_activation_requests':0}
        if self.out.is_dir():self.tx.write_new(self.out/'stop.json',self.final)
        return self.final
