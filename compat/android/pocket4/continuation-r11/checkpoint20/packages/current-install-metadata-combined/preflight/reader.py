import hashlib,json,os,stat,time
from pathlib import Path
IHG_ROOT=Path('/home/alex/work/pocket4-owned-ihg-qa-r2-install-state-01')
BASE={'ihg-stage.json':IHG_ROOT/'stage-result.json','bili-state-command.json':Path('/home/alex/work/pocket4-bilibili-owned-qa-r9-flow-d327cfd21d7b59df0c45a68efdd74c98/steps/install-state-r9-01/command-006.result.json')}
PINS={'ihg-stage.json':(6006,'77a412e42d3881f388b5308544a5b118a40fdb8acaf081ec337dedbf5018bff8')}
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


require(os.getuid()==os.geteuid()==0,'ROOT_FIXED_RESULT_READ_ONLY')
r=Reader()
for name,path in BASE.items():
    raw=r.add(name,path);value=json.loads(raw);no_raw_ui(value)
    if name=='bili-state-command.json':
        require(sha(raw)=='1f5569b2f71cecb4d9991f0b6946033fde60be392f19d0f2bf9061ed4121eb15','EXACT_ACTUAL_STATE_COMMAND_PIN')
        require(value['returncode']==0 and value['owned_command_joined'] is True and value['timed_out'] is False and value['error'] is None and value['errors']==[] and value['action_attempted'] is False,'EXACT_STATE_COMMAND_OBSERVATION')
        require(value['stdout_sha256']=='d46f1cd04fc8ce3dd62cf291cc1ddb4a40f17afe9bfa4105b15e1dde5e909b61' and value['stderr_sha256']==sha(b''),'STATE_STREAM_PINS')
    else:
        require(value['ok'] is False and value['error']=={'phase':'stage_or_coordinator','type':'KeyError','message':"'references/readonly_r3_coordinator.py'"} and value['secondary_errors']==[],'EXACT_IHG_FAILED_STAGE')
current=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
absent={}
try:
    for name in IHG_ROOT.parts[1:]:
        require(time.monotonic()-r.started<8,'ABSENCE_DEADLINE')
        child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=current)
        try:os.close(current)
        except BaseException:
            os.close(child);raise
        current=child
    before=os.fstat(current)
    require(stat.S_ISDIR(before.st_mode) and before.st_uid==before.st_gid==0,'OWNED_IHG_ROOT')
    for name in ('result.json','worker'):
        try:st=os.stat(name,dir_fd=current,follow_symlinks=False)
        except FileNotFoundError:absent[name]=True
        else:absent[name]=False
    after=os.fstat(current)
    require((before.st_dev,before.st_ino,before.st_mode,before.st_uid,before.st_gid)==(after.st_dev,after.st_ino,after.st_mode,after.st_uid,after.st_gid),'HELD_ROOT_CHANGED')
finally:os.close(current)
print(json.dumps({'schema':'pocket4-fixed-ihg-failure-bili-state-metadata-read-v1','files':r.records,'ihg_exact_absence':absent,'bili_state_index_actual_digest_bound':6,'all_owned_directory_fds_closed':True,'Android_commands':0,'UI_actions':0,'service_or_process_actions':0,'total_read_bytes':r.total,'elapsed_seconds':time.monotonic()-r.started},sort_keys=True,separators=(',',':')),flush=True)
