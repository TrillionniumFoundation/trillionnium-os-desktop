"""Finish only ZIP alignment for the previously verified offline DEX build."""
from pathlib import Path
import datetime,hashlib,json,os,re,shutil,stat,sys,types

ROOT=Path('/home/alex/work/pocket4-storage-session-candidate-20261105-r12')
OUT=ROOT/'alignment15'
RESULT_SHA='15947f9c0831e1419988dba12e2cf9a4dfa3bea66fdd229a857200fca2f76bd1'
BUILDER_SHA='757dc7cd0c04ee1d7ddb6f4fa05457867b410e6f4c4ce30f5656eb590b25c5a8'
LIBRARY=Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/wifi-disabled-candidate/zip-aligned-v2/tools/root/usr/lib/libzopfli.so.1.0.3')
LIBRARY_SHA='0ba6435437effc8b2593418d37067698c1bbac4baadfaa259bc917a035042b35'

def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def write(path,value):
    with path.open('x') as f:
        json.dump(value,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())

def align(result):
    assert os.getuid()==1000 and set(os.sched_getaffinity(0)) and set(os.sched_getaffinity(0)) <= {20,21}
    base_result=ROOT/'build13/result.json'
    assert digest(base_result)==RESULT_SHA
    base=json.loads(base_result.read_text())
    assert base['state']=='DEX_VERIFIED_ALIGNMENT_PENDING'
    assert base['semantic_verification']['non_target_semantic_changes']==0
    builder=ROOT/'frozen13/build_runtime13.py';assert digest(builder)==BUILDER_SHA
    module=types.ModuleType('verified_zip_helpers');module.__file__=str(builder)
    exec(compile(builder.read_bytes(),str(builder),'exec'),module.__dict__)
    module.OUT=OUT
    assert digest(ROOT/'toolchain11.json')==module.TOOL_SHA
    pins=json.loads((ROOT/'toolchain11.json').read_text())
    zipalign=Path(pins['zipalign']['canonical']);assert digest(zipalign)==pins['zipalign']['sha256']
    assert LIBRARY.is_file() and digest(LIBRARY)==LIBRARY_SHA
    libdir=OUT/'lib';libdir.mkdir(mode=0o700)
    copied=libdir/'libzopfli.so.1'
    with copied.open('xb') as f:f.write(LIBRARY.read_bytes());f.flush();os.fsync(f.fileno())
    copied.chmod(0o400);assert digest(copied)==LIBRARY_SHA
    module.ENV={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LD_LIBRARY_PATH':str(libdir)}
    module.good(module.run(result,'ldd',['/usr/bin/ldd',str(zipalign)],10))
    ldd=(OUT/'ldd.stdout').read_text();assert 'not found' not in ldd
    linked={}
    for line in ldd.splitlines():
        match=re.search(r'(?:=>\s*)?(/[^\s]+)\s+\(0x[0-9a-f]+\)',line)
        if match:
            p=Path(match[1]);c=p.resolve(strict=True)
            assert c.is_file()
            linked[str(p)]=dict(canonical=str(c),sha256=digest(c),bytes=c.stat().st_size)
    assert str(copied) in linked and linked[str(copied)]['sha256']==LIBRARY_SHA
    assert len(linked)>=10
    result['dynamic_dependencies']=linked
    original=ROOT/'input/services-installed.jar'
    unaligned=Path(base['unaligned_jar']['path'])
    dex=ROOT/'build13/classes3.single-removal.dex'
    assert digest(original)==module.JAR_SHA
    assert digest(unaligned)==base['unaligned_jar']['sha256']
    assert digest(dex)==base['candidate_dex']['sha256']
    module.good(module.run(result,'check-original',[str(zipalign),'-c','4',str(original)],10))
    aligned=OUT/'services-storage-single-removal.jar'
    module.good(module.run(result,'align',[str(zipalign),'4',str(unaligned),str(aligned)],20))
    module.good(module.run(result,'check-candidate',[str(zipalign),'-c','4',str(aligned)],10))
    proof=module.zip_proof(original,aligned,dex.read_bytes())
    prior_proof=ROOT/'build13/zip-payload-proof.json'
    assert digest(prior_proof)==base['zip_payloads']['evidence_sha256']
    assert proof==json.loads(prior_proof.read_text())
    write(OUT/'zip-payload-proof.json',proof)
    for p,record in linked.items():assert digest(Path(p).resolve(strict=True))==record['sha256']
    assert digest(zipalign)==pins['zipalign']['sha256'] and digest(LIBRARY)==LIBRARY_SHA
    assert digest(base_result)==RESULT_SHA and digest(original)==module.JAR_SHA
    assert digest(unaligned)==base['unaligned_jar']['sha256']
    assert digest(dex)==base['candidate_dex']['sha256']
    result.update(state='ALIGNED_OFFLINE_CANDIDATE',aligned_jar=dict(path=str(aligned),
        sha256=digest(aligned),bytes=aligned.stat().st_size),alignment=4,
        zip_members=len(proof),only_changed_member='classes3.dex',
        zip_payload_proof_sha256=digest(OUT/'zip-payload-proof.json'),
        source_build_result_sha256=RESULT_SHA,candidate_dex=base['candidate_dex'],
        semantic_verification=base['semantic_verification'],
        input_jar_sha256=module.JAR_SHA,inputs_and_tools_unchanged=True,
        zipalign_sha256=pins['zipalign']['sha256'],local_dependency_sha256=LIBRARY_SHA)

def main():
    result=dict(started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        state='STARTED',commands={},scope='offline ZIP alignment only',
        complete_java_or_aosp_build=False,android_art_verifier_run=False,
        android_lifecycle_test_run=False,deployed=False,UI_actions=0,runtime_writes=0)
    rc=0
    try:align(result)
    except BaseException as error:
        result['state']='FAILED';result['error']=type(error).__name__+':'+str(error);rc=2
    result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    write(OUT/'result.json',result);print(json.dumps(result,sort_keys=True));return rc

if __name__=='__main__':sys.exit(main())
