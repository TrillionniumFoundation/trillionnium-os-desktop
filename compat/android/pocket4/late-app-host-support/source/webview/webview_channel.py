"""One authenticated worker controls one owned fixed localhost fixture sibling."""
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
SCHEMA='pocket4-current-webview-fixture-channel-v1'

def need(value,why):
    if not value:raise RuntimeError(why)

def socket_identity(fd):
    s=os.fstat(fd);need(stat.S_ISSOCK(s.st_mode),'ACTUAL_FIXTURE_CHANNEL_SOCKET')
    return {'device':s.st_dev,'inode':s.st_ino,'mode':s.st_mode,'uid':s.st_uid,'gid':s.st_gid}

def receive(sock,credentials,parse):
    raw,ancillary,flags,_=sock.recvmsg(MAX_PACKET+1,socket.CMSG_SPACE(struct.calcsize('3i')))
    need(raw and len(raw)<=MAX_PACKET and flags==0,'FIXTURE_CHANNEL_EOF_OVERFLOW_OR_TRUNCATION')
    need(len(ancillary)==1 and ancillary[0][:2]==(socket.SOL_SOCKET,socket.SCM_CREDENTIALS)
        and len(ancillary[0][2])==struct.calcsize('3i')
        and struct.unpack('3i',ancillary[0][2])==credentials,'ACTUAL_FIXTURE_CHANNEL_SENDER')
    return parse(raw)

def exited(pidfd):
    poller=select.poll();poller.register(pidfd,select.POLLIN)
    return bool(poller.poll(0))

def child_identity(pid):
    """Read only stable public fields; pidfd separately pins this child generation."""
    proc=Path('/proc')/str(pid)
    def generation():
        raw=(proc/'stat').read_text();fields=raw.rsplit(')',1)[1].split()
        need(int(raw.split(' ',1)[0])==pid and len(fields)>=20,'ACTUAL_FIXTURE_PROCESS_STAT')
        return {'pid':pid,'parent':int(fields[1]),'start_ticks':int(fields[19])}
    before=generation();status=(proc/'status').read_text().splitlines()
    selected={line.split(':',1)[0]:line.split(':',1)[1].split() for line in status
        if line.split(':',1)[0] in ('Uid','Gid','Groups','CapEff','CapPrm','CapAmb','NoNewPrivs')}
    need(set(selected)=={'Uid','Gid','Groups','CapEff','CapPrm','CapAmb','NoNewPrivs'}
        and generation()==before,'STABLE_FIXTURE_IDENTITY')
    return {**before,'status':selected,'net_namespace':os.readlink(proc/'ns/net'),
        'other_namespaces':{name:os.readlink(proc/'ns'/name) for name in ('mnt','pid','uts','ipc','user','cgroup')},
        'cgroup':(proc/'cgroup').read_text().splitlines()}

class FixtureClient:
    def __init__(self,c,runtime,fd,parent_ref,plan_ref,prep_ref,base):
        self.c=c;self.runtime=runtime;self.parent_ref=parent_ref;self.plan_ref=plan_ref;self.base=base
        self.sock=self.pidfd=self.server_pidfd=None;self.session=None;self.closed=False
        self.sequence=0;self.started=self.stopped=False;self.ready=self.final=self.server_identity=None
        self.run=base['run_id'];self.pages=();self.base_url=None
        value=c.parse(c.read_ref(parent_ref,131072));self.parent=value
        try:
            need(set(value)=={'schema','plan','preparation','case_root','parent','boot_id','client_socket','limits','automatic_retry'}
                and value['schema']=='pocket4-current-webview-supervisor-parent-v1'
                and value['plan']==plan_ref and value['preparation']==prep_ref
                and value['case_root']==base['case_root'] and value['limits']==base['limits']
                and value['automatic_retry'] is False
                and Path(parent_ref['path'])==Path(base['case_root'])/'fixture-supervisor/parent.json',
                'EXACT_NEW_WEBVIEW_PARENT_BINDING')
            need(type(fd) is int and fd>2 and socket_identity(fd)==value['client_socket'],'ACTUAL_INHERITED_CHANNEL_FD')
            self.sock=socket.socket(fileno=fd);self.sock.setblocking(False);os.set_inheritable(fd,False)
            need(self.sock.family==socket.AF_UNIX and self.sock.type==socket.SOCK_SEQPACKET,'EXACT_FIXTURE_SOCKET_PROTOCOL')
            self.sock.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)
            self.pid=value['parent']['pid'];self.pidfd=os.pidfd_open(self.pid,0)
            need(struct.unpack('3i',self.sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))==(self.pid,0,0),
                'ACTUAL_ROOT_PARENT_PEER');self.verify_parent_and_server()
        except BaseException:self.close();raise
    def verify_parent_and_server(self):
        need(not self.closed and self.sock is not None and self.pidfd is not None,'FIXTURE_PARENT_AUTHORITY_CLOSED')
        self.c.read_ref(self.parent_ref)
        need(not exited(self.pidfd) and os.getppid()==self.pid and self.runtime.boot()==self.parent['boot_id']
            and self.runtime.process(self.c,self.pid)==self.parent['parent'],'SAME_LIVE_FIXTURE_PARENT_GENERATION')
        need(socket_identity(self.sock.fileno())==self.parent['client_socket'] and not os.get_inheritable(self.sock.fileno()),
            'UNCHANGED_PRIVATE_FIXTURE_CHANNEL')
        if self.ready is not None and not self.stopped:
            need(self.server_pidfd is not None and not exited(self.server_pidfd)
                and child_identity(self.ready['pid'])==self.server_identity,'SAME_LIVE_FIXTURE_SIBLING')
    def attach(self,session):
        need(self.session is None and session.active['base_plan']==self.plan_ref
            and session.kind==self.base['kind'] and session.root==Path(self.base['case_root']),
            'ONE_EXACT_FRESH_WEBVIEW_SESSION')
        self.session=session;self.verify_parent_and_server()
    def request(self,kind,value):
        need(kind in ('start','stop') and self.session is not None,'FINITE_FIXTURE_LIFECYCLE_REQUEST')
        self.verify_parent_and_server()
        if kind=='start':self.session.guard()
        deadline=min(time.monotonic()+10,self.session.deadline) if kind=='start' else time.monotonic()+12
        need(time.monotonic()<deadline,'NO_START_AFTER_ORIGINAL_PHASE')
        self.sequence+=1;need(self.sequence<=2,'ONE_START_AND_ONE_STOP_NO_REPLAY')
        row={'schema':SCHEMA,'sequence':self.sequence,'kind':kind,'parent':self.parent_ref,'plan':self.plan_ref,'value':value}
        raw=self.c.canonical(row);need(len(raw)<=MAX_PACKET,'BOUNDED_FIXTURE_REQUEST')
        sent=False;poller=select.poll();poller.register(self.pidfd,select.POLLIN)
        poller.register(self.sock,select.POLLOUT|select.POLLIN|select.POLLERR|select.POLLHUP)
        while time.monotonic()<deadline:
            self.verify_parent_and_server()
            if not sent:
                try:
                    need(self.sock.send(raw,socket.MSG_NOSIGNAL)==len(raw),'ATOMIC_FIXTURE_REQUEST');sent=True
                    poller.modify(self.sock,select.POLLIN|select.POLLERR|select.POLLHUP)
                except BlockingIOError:pass
            if sent:
                try:
                    reply=receive(self.sock,(self.pid,0,0),self.c.parse)
                    need(type(reply) is dict and set(reply)==RESPONSE_KEYS and reply['schema']==SCHEMA
                        and reply['sequence']==self.sequence and reply['kind']==kind and reply['ok'] is True
                        and reply['error'] is None,'EXACT_CURRENT_FIXTURE_REPLY')
                    self.verify_parent_and_server();return reply['value']
                except BlockingIOError:pass
            poller.poll(max(1,min(100,int((deadline-time.monotonic())*1000))))
        raise TimeoutError('FIXTURE_REQUEST_OUTCOME_UNKNOWN_NO_REPLAY')
    def start(self):
        need(not self.started and not self.stopped,'ONCE_FIXTURE_START');self.started=True
        value=self.request('start',{'active_plan':self.session.active_ref,'phase':self.session.phase_ref})
        need(set(value)=={'ready','server_identity','pages','base_url','ready_ref'},'EXACT_FIXTURE_START_REPLY')
        ready=value['ready'];self.c.read_ref(value['ready_ref'])
        need(self.c.parse(self.c.read_ref(value['ready_ref']))=={k:v for k,v in value.items() if k!='ready_ref'},
            'READY_REF_MUST_BIND_FULL_START_REPLY')
        # ready_ref cannot recursively contain itself. The reference contains
        # the full start payload except this reference.
        self.ready=ready;self.server_identity=value['server_identity'];self.pages=tuple(value['pages']);self.base_url=value['base_url']
        self.server_pidfd=os.pidfd_open(ready['pid'],0)
        need(ready['run']==self.run and self.base_url=='http://127.0.0.1:%d/p4/%s/'%(ready['port'],self.run)
            and self.server_identity['pid']==ready['pid'] and self.server_identity['parent']==self.pid
            and self.server_identity['start_ticks']==ready['start_ticks'],'SAME_ORIGINAL_RUN_AND_SERVER_GENERATION')
        self.verify_parent_and_server();self.session.guard();return self
    def ensure_alive(self):
        need(self.started and not self.stopped and self.ready is not None,'ACTUAL_STARTED_OWNED_WEBVIEW_FIXTURE')
        self.session.guard();self.verify_parent_and_server()
    def url(self,name):
        need(name in self.pages,'ONLY_ORIGINAL_FIXED_FIXTURE_PAGE');self.ensure_alive();return self.base_url+name
    def stop(self):
        if self.stopped:return self.final
        self.stopped=True
        self.final=self.request('stop',{'started_request_sent':self.started})
        return self.final
    def close(self):
        first=None
        for name in ('sock','server_pidfd','pidfd'):
            value=getattr(self,name,None);setattr(self,name,None)
            if value is not None:
                try:value.close() if name=='sock' else os.close(value)
                except BaseException as error:
                    if first is None:first=error
                    else:first.add_note('OTHER_FIXTURE_FD_CLOSE:'+str(error))
        self.closed=True
        if first is not None:raise first
