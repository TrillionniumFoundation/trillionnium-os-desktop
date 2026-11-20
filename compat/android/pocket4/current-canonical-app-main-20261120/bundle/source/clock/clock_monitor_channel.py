"""Typed one-parent/one-child channel for passive Notify observation only."""
import os
from pathlib import Path
import select
import socket
import stat
import struct
import time

MAX_PACKET=32768
REQUEST_KEYS={'schema','sequence','kind','parent','plan','value'}
RESPONSE_KEYS={'schema','sequence','kind','ok','value','error'}
SCHEMA='pocket4-clock-notify-channel-v1'


def need(value,why):
    if not value:raise RuntimeError(why)


def socket_identity(fd):
    info=os.fstat(fd);need(stat.S_ISSOCK(info.st_mode),'ACTUAL_MONITOR_CONTROL_SOCKET_REQUIRED')
    return {'device':info.st_dev,'inode':info.st_ino,'mode':info.st_mode,'uid':info.st_uid,'gid':info.st_gid}


def receive(sock,credentials,parse):
    raw,ancillary,flags,_=sock.recvmsg(MAX_PACKET+1,socket.CMSG_SPACE(struct.calcsize('3i')))
    need(raw and len(raw)<=MAX_PACKET and flags==0,'NOTIFY_CONTROL_EOF_OVERFLOW_OR_TRUNCATION')
    need(len(ancillary)==1 and ancillary[0][:2]==(socket.SOL_SOCKET,socket.SCM_CREDENTIALS)
        and len(ancillary[0][2])==struct.calcsize('3i')
        and struct.unpack('3i',ancillary[0][2])==credentials,'ACTUAL_NOTIFY_CONTROL_PEER_CREDENTIALS')
    return parse(raw)


class Client:
    def __init__(self,c,runtime,fd,parent_ref,plan_ref,prep_ref,case_root):
        self.c=c;self.runtime=runtime;self.parent_ref=parent_ref;self.plan_ref=plan_ref
        self.closed=False;self.sequence=0;self.started=False;self.stopped=False;self.final=None
        self.sock=None;self.pidfd=None;self.session=None
        value=c.parse(c.read_ref(parent_ref,131072));self.parent=value
        try:
            need(set(value)=={'schema','plan','preparation','case_root','parent','boot_id','client_socket','limits','automatic_retry'}
                and value['schema']=='pocket4-clock-notify-supervisor-parent-v1' and value['plan']==plan_ref
                and value['preparation']==prep_ref and value['case_root']==str(case_root)
                and value['automatic_retry'] is False
                and Path(parent_ref['path'])==Path(case_root)/'notify-supervisor/parent.json',
                'CURRENT_EXPLICIT_NOTIFY_PARENT_BINDING')
            need(type(fd) is int and fd>2 and socket_identity(fd)==value['client_socket'],
                'ORIGINAL_PASSED_NOTIFY_SOCKET_IDENTITY')
            self.sock=socket.socket(fileno=fd);self.sock.setblocking(False);os.set_inheritable(fd,False)
            need(self.sock.family==socket.AF_UNIX and self.sock.type==socket.SOCK_SEQPACKET,
                'EXACT_NOTIFY_CONTROL_PROTOCOL')
            self.sock.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)
            self.pid=value['parent']['pid'];self.pidfd=os.pidfd_open(self.pid,0)
            actual=struct.unpack('3i',self.sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            need(actual==(self.pid,0,0),'ACTUAL_ROOT_PARENT_SOCKET_PEER')
            self.verify()
        except BaseException:self.close();raise

    def verify(self):
        need(not self.closed and self.sock is not None and self.pidfd is not None,'NOTIFY_CONTROL_CLOSED')
        self.c.read_ref(self.parent_ref)
        poller=select.poll();poller.register(self.pidfd,select.POLLIN)
        need(not poller.poll(0) and self.runtime.boot()==self.parent['boot_id']
            and os.getppid()==self.pid and self.runtime.process(self.c,self.pid)==self.parent['parent'],
            'ORIGINAL_LIVE_NOTIFY_PARENT_REQUIRED')
        need(socket_identity(self.sock.fileno())==self.parent['client_socket']
            and not os.get_inheritable(self.sock.fileno()),'NOTIFY_CHANNEL_FD_CHANGED')

    def attach(self,session):
        need(self.session is None and session.kind=='expiry06' and session.root==Path(self.parent['case_root']),
            'ONE_ACTUAL_EXPIRY_SESSION_ON_NOTIFY_CHANNEL')
        self.session=session;self.verify()

    def request(self,kind,value):
        need(kind in ('start','snapshot','stop') and self.session is not None,'FINITE_PASSIVE_NOTIFY_REQUEST')
        self.verify()
        # A stop must retire our already-owned passive child even if Main guard
        # failed. It cannot grant Android actions or reset a business UNKNOWN.
        if kind!='stop':self.session.guard()
        deadline=min(time.monotonic()+10,self.session.deadline) if kind!='stop' else time.monotonic()+10
        need(time.monotonic()<deadline,'NO_NOTIFY_REQUEST_AFTER_PHASE_DEADLINE')
        self.sequence+=1
        row={'schema':SCHEMA,'sequence':self.sequence,'kind':kind,'parent':self.parent_ref,
            'plan':self.plan_ref,'value':value};raw=self.c.canonical(row)
        need(len(raw)<=MAX_PACKET,'BOUNDED_TYPED_NOTIFY_REQUEST')
        sent=False;poller=select.poll();poller.register(self.pidfd,select.POLLIN)
        poller.register(self.sock,select.POLLOUT|select.POLLIN|select.POLLERR|select.POLLHUP)
        while time.monotonic()<deadline:
            self.verify()
            if not sent:
                try:
                    count=self.sock.send(raw,socket.MSG_NOSIGNAL)
                    need(count==len(raw),'ATOMIC_NOTIFY_REQUEST_SEND');sent=True
                    poller.modify(self.sock,select.POLLIN|select.POLLERR|select.POLLHUP)
                except BlockingIOError:pass
            if sent:
                try:
                    reply=receive(self.sock,(self.pid,0,0),self.c.parse)
                    need(type(reply) is dict and set(reply)==RESPONSE_KEYS and reply['schema']==SCHEMA
                        and reply['sequence']==self.sequence and reply['kind']==kind and type(reply['ok']) is bool,
                        'EXACT_CURRENT_NOTIFY_REPLY')
                    self.verify()
                    need(reply['ok'] is True and reply['error'] is None,'NOTIFY_SUPERVISOR_REJECTED:'+str(reply['error']))
                    if kind!='stop':self.session.guard()
                    return reply['value']
                except BlockingIOError:pass
            poller.poll(max(1,min(100,int((deadline-time.monotonic())*1000))))
        raise TimeoutError('NOTIFY_REQUEST_OUTCOME_UNKNOWN_NO_REPLAY')

    def start(self,binding_ref):
        need(not self.started and not self.stopped,'ONCE_NOTIFY_START')
        self.started=True
        return self.request('start',{'binding':binding_ref,'phase':self.session.phase_ref})

    def snapshot(self):
        need(self.started and not self.stopped,'ACTIVE_NOTIFY_MONITOR_REQUIRED')
        return self.request('snapshot',{'phase':self.session.phase_ref})

    def stop(self):
        if self.stopped:return self.final
        self.stopped=True
        self.final=self.request('stop',{'started_request_sent':self.started})
        return self.final

    def close(self):
        # No request replay or Android cleanup is attempted from FD teardown.
        first=None
        for name in ('sock','pidfd'):
            value=getattr(self,name,None);setattr(self,name,None)
            if value is not None:
                try:value.close() if name=='sock' else os.close(value)
                except BaseException as error:
                    if first is None:first=error
                    else:first.add_note('NOTIFY_OTHER_FD_CLOSE:'+type(error).__name__)
        self.closed=True
        if first is not None:raise first
