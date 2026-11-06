import hashlib,json,os,re,stat,sys,time
from pathlib import Path
ROOT=Path('/home/alex/work/pocket4-owned-bili-qa-r9-install-state-01')
BASE={'worker-command.json':ROOT/'evidence/02-install-state.result.json'}
PINS={}
def require(value,reason):
    if not value:raise RuntimeError(reason)
def sha(raw):return hashlib.sha256(raw).hexdigest()
class Reader:
    def __init__(self):
        self.started = time.monotonic()
        self.total = 0
        self.records = {}

    def read(self, path, optional=False):
        require(time.monotonic()-self.started < 8, 'READ_DEADLINE')
        require(path in BASE.values(), 'EXACT_THREE_FILE_ALLOWLIST_REQUIRED')
        directory = os.open('/', os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
        fd = None
        try:
            for name in path.parts[1:-1]:
                next_fd = os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=directory)
                os.close(directory); directory=next_fd
            try:
                fd=os.open(path.name,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=directory)
            except FileNotFoundError:
                if optional:
                    return None
                raise
            first=os.fstat(fd)
            require(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and first.st_uid==0 and
                    0<=first.st_size<=65536,'ROOT_SINGLE_REGULAR_BOUNDED_RECEIPT_REQUIRED')
            chunks=[];count=0
            while True:
                require(time.monotonic()-self.started<8,'READ_DEADLINE')
                part=os.read(fd,min(16384,65537-count))
                if not part:
                    break
                chunks.append(part);count+=len(part);self.total+=len(part)
                require(count<=65536 and self.total<=524288,'TOTAL_OR_FILE_BOUND')
            last=os.fstat(fd)
            fields=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
            require(count==first.st_size and all(getattr(first,k)==getattr(last,k) for k in fields),'RECEIPT_CHANGED')
            return b''.join(chunks)
        finally:
            if fd is not None:
                os.close(fd)
            os.close(directory)

    def add(self, name, path, raw=None):
        require(name not in self.records,'DUPLICATE_EXPORT_NAME')
        if raw is None:
            raw=self.read(path)
        text=raw.decode('utf-8','strict')
        if name in PINS:
            require((len(raw),sha(raw))==PINS[name],'EXTERNAL_TERMINAL_RECEIPT_PIN_CHANGED:'+name)
        self.records[name]={'path':str(path),'bytes':len(raw),'sha256':sha(raw),'text':text}
        return raw


def no_raw_ui(value):
    if isinstance(value,dict):
        require(not ({'nodes','text','content_desc','inspection','raw_tree','raw_ui_tree','screenshot','pixels'} & set(value)),
                'RAW_UI_FIELD_FORBIDDEN_IN_STATE_EXPORT')
        for item in value.values():no_raw_ui(item)
    elif isinstance(value,list):
        for item in value:no_raw_ui(item)


require(os.getuid()==os.geteuid()==0,'ROOT_FIXED_READ_ONLY')
wire=sys.stdin.buffer.read(16385)
require(0<len(wire)<=16384,'EXACT_INPUT_BOUND')
p=json.loads(wire);worker_raw=p['worker_raw'].encode('utf-8')
require(len(worker_raw)==7589 and sha(worker_raw)=='e9310a73a567d7207e55b8fede9a68f7a305d72e5cdb9042a6b7455ef4e02ad3','ROOT_ACTUAL_WORKER_PIN')
worker=json.loads(worker_raw)
require(worker['owned_package_uid']==10152 and worker['state']['helper']['ui_automation_connected'] is False,'ROOT_ACTUAL_WORKER_SCOPE')
r=Reader();raw=r.add('worker-command.json',BASE['worker-command.json'])
value=json.loads(raw);no_raw_ui(value)
require(value['name']=='02-install-state' and value['argv']==['/usr/bin/python3','-I',str(ROOT/'source/install_state.py'),'--worker-once','--source-manifest-sha256','399cebc279ac8653b943b5c433b248c94dec32062b85b45e9cb6c22fce379a66'],'EXACT_OWNED_WORKER_COMMAND')
require(value['spawned'] is True and value['joined'] is True and value['returncode']==0 and value['timed_out'] is False and value['secondary_errors']==[] and 'primary_error' not in value,'WORKER_JOIN_NOT_QUALIFIED')
require(value['Main_before'] is True and value['Main_after']==p['Main_after'],'WORKER_MAIN_FENCES')
printed=(json.dumps(worker,ensure_ascii=False)+'\n').encode('utf-8')
require(value['stdout']=={'bytes':len(printed),'sha256':sha(printed)} and value['stderr']=={'bytes':0,'sha256':sha(b'')},'EXACT_WORKER_STDOUT_AND_EMPTY_STDERR')
print(json.dumps({'schema':'pocket4-bili-r9-fixed-worker-command-read-v1','files':r.records,'direct_child_join_verified':True,'worker_stdout_reconstructed_from_exact_original_and_frozen_serializer':True,'worker_raw_sha256':sha(worker_raw),'state_command_sha256':worker['state']['recorder_command_result_sha256'],'total_read_bytes':r.total,'elapsed_seconds':time.monotonic()-r.started,'Android_commands':0,'UI_actions':0,'independent_runtime_qualification':False},sort_keys=True,separators=(',',':')),flush=True)
