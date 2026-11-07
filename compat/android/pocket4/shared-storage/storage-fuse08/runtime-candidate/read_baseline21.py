"""Read retained ART20 outputs; do not invoke ART or enter Android."""
from pathlib import Path
import hashlib,json,os,re,stat
ROOT=Path('/home/alex/work/pocket4-storage-session-candidate-20261105-r12')
SRC=ROOT/'art-pair20'
OUT=ROOT/'art-baseline-review21'
RESULT_SHA='1138ea24880808e639112691c5e224497705a82b289aa646d1687c0117583292'

def sha(b):return hashlib.sha256(b).hexdigest()
def read(path,limit,expected=None):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as f:
        a=os.fstat(f.fileno());assert stat.S_ISREG(a.st_mode) and a.st_nlink==1 and a.st_size<=limit
        b=f.read(limit+1);z=os.fstat(f.fileno())
        assert len(b)==a.st_size and (a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(z.st_dev,z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns)
    if expected:assert sha(b)==expected
    return b
def write(name,b):
    fd=os.open(OUT/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o640)
    with os.fdopen(fd,'wb') as f:
        f.write(b);f.flush();os.fsync(f.fileno());os.fchown(f.fileno(),0,1000);os.fchmod(f.fileno(),0o640)
    return dict(file=name,bytes=len(b),sha256=sha(b))
def main():
    assert os.geteuid()==0
    raw=read(SRC/'result.json',1024*1024,RESULT_SHA);r=json.loads(raw);v=r['phases']['original']
    assert r['runner_sha256']=='e2dfabd5a0b01316c05181c5c06e35ab980c108c8c40d51746a0f79a38ddf80b'
    assert r['error']=='RuntimeError:TARGET_DUMP_NOT_BOUNDED' and list(r['phases'])==['original']
    for key in ('compiler','target_dump','android_log'):
        assert v[key]['rc']==0 and v[key]['joined'] and not v[key]['timed_out']
    assert v['fd_proof']['all_descriptor_identities_exact'] and r['input_boot_apex_classpaths_unchanged']
    for flag in ('--compiler-filter=verify','--abort-on-hard-verifier-error','--abort-on-soft-verifier-error'):
        assert v['argv'].count(flag)==1
    output=read(SRC/'original-target-dump.stdout',8*1024*1024,v['target_dump']['stdout']['sha256'])
    text=output.decode()
    pattern=re.compile(r'^\d+: Lcom/android/server/storage/StorageSessionController; \(offset=0x[0-9a-f]+\) \(type_idx=\d+\) \(([^)]+)\) \(([^)]+)\)$',re.M)
    hits=list(pattern.finditer(text));assert len(hits)==1
    h=hits[0];assert h[1]=='Verified'
    allheaders=re.compile(r'^\d+: L[^;]+; \(offset=',re.M)
    next_header=allheaders.search(text,h.end());end=next_header.start() if next_header else len(text)
    method=re.compile(r'^\s*\d+: void com\.android\.server\.storage\.StorageSessionController\.onVolumeUnmount\(com\.android\.server\.storage\.ImmutableVolumeInfo\) \(dex_method_idx=\d+\)$',re.M)
    methods=list(method.finditer(text,h.end(),end));assert len(methods)==1
    before=read(SRC/'before.json',1024*1024);after=read(SRC/'after.json',1024*1024)
    assert json.loads(before)==json.loads(after)
    b=json.loads(before)
    for name,file in (('oat','original.odex'),('vdex','original.vdex')):
        data=read(SRC/'original'/file,64*1024*1024,v['outputs'][name]['sha256'])
        assert len(data)==v['outputs'][name]['bytes']
    read(SRC/'original/original.jar',40*1024*1024,v['input_after']['sha256'])
    OUT.mkdir(mode=0o750);os.chown(OUT,0,1000);os.chmod(OUT,0o750)
    window=text[h.start():min(end,h.start()+24000)].encode()
    summary=dict(state='RETAINED_ORIGINAL_TARGET_VERIFIED_CANDIDATE_NOT_EXECUTED',
        original_result_sha256=RESULT_SHA,original_result_preserved=True,
        original_run_error=r['error'],compiler=v['compiler'],target_dump=v['target_dump'],
        output_file_sha256=sha(output),target_class_header=h[0],target_status=h[1],
        target_compilation_kind=h[2],target_method_header=methods[0][0].strip(),
        exact_class_header_matches=1,method_in_exact_class=True,
        target_window=write('target-window.txt',window),
        target_window_starts_at_utf8_byte=len(text[:h.start()].encode()),
        target_window_reaches_next_class_or_eof=min(end,h.start()+24000)==end,
        closure=dict(before_sha256=sha(before),after_sha256=sha(after),values_equal=True,
            bcp_files=len(b['classpath_files']),guest_dependencies=len(b['guest_files']),
            host_inputs={k:{f:x[f] for f in ('bytes','sha256')} for k,x in b['host_inputs'].items()}),
        outputs={k:{f:x[f] for f in ('bytes','sha256')} for k,x in v['outputs'].items()},
        guard_after=r['guard_after'],resource_usage=r['resource_usage'],
        candidate_attempted=False,ART_invocations=0,Main_reads=0,UI_actions=0,deployed=False,
        scope='Existing original target class verification only; full ART20 pair remains unqualified and its exit2 is not rewritten.')
    log=read(SRC/'original-compiler-log.stdout',1024*1024,v['android_log']['stdout']['sha256'])
    summary['compiler_log']=write('original-compiler.log',log)
    encoded=(json.dumps(summary,indent=2,sort_keys=True)+'\n').encode()
    item=write('result.json',encoded)
    print(json.dumps(dict(summary=summary,result_file=item),sort_keys=True))
if __name__=='__main__':main()
