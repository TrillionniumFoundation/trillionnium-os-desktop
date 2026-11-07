#!/usr/bin/python3 -I
"""Offline one-method DEX candidate; no Android entry or installation commands."""
from pathlib import Path
import datetime,hashlib,json,os,re,shutil,signal,struct,subprocess,sys,types,zipfile,zlib

ROOT=Path('/home/alex/work/pocket4-storage-session-candidate-20261105-r12')
OUT=ROOT/'build13'
FROZEN=ROOT/'frozen13'
TOOL_SHA='9f269253784471fb1cc0cc0f9f554032410ac25c1ca4b28071d21e4264128e4a'
JAR_SHA='f33987e633e476f47ea043af3f7fb94907fd2431fa2b5b49df84cb586bce5c50'
DEX_SHA='bbbeed4aeb197113710fd084ebe7fc30d42c8ea0baf60c36e12fa62c238cd172'
OLD_CLASS='e0ddf859ff6c243681256b2100baab7bbb4228b10e77ad65812b301fd9bd1523'
NEW_CLASS='9c7070a802038cb1eaa4a18ebb3db12785aad1d7e96d37c50d5c62e92abe6e61'
IR_SHA='a895a4e3963f958ea6a6ff45b9d0c51f6239118b3a10fddff6d0f17e22e25f9f'
REL='com/android/server/storage/StorageSessionController.smali'
METHOD='public onVolumeUnmount(Lcom/android/server/storage/ImmutableVolumeInfo;)V'
ENV={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'}


def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def write(path,value):
    with path.open('x') as f:
        json.dump(value,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())


def run(result,label,argv,timeout=90):
    with (OUT/(label+'.stdout')).open('xb') as out,(OUT/(label+'.stderr')).open('xb') as err:
        p=subprocess.Popen(argv,stdout=out,stderr=err,env=ENV,start_new_session=True)
        timed_out=False
        try:p.wait(timeout)
        except subprocess.TimeoutExpired:
            timed_out=True
            os.killpg(p.pid,signal.SIGKILL);p.wait(10)
    record=dict(argv=argv,rc=p.returncode,timed_out=timed_out,joined=True,
        stdout_sha256=digest(OUT/(label+'.stdout')),stderr_sha256=digest(OUT/(label+'.stderr')))
    result['commands'][label]=record
    write(OUT/(label+'.json'),record)
    return record


def good(record):
    assert record['rc']==0 and not record['timed_out'] and record['joined'],record


def tree(root):
    files={}
    for p in root.rglob('*'):
        assert not p.is_symlink(),p
        if p.is_file():
            assert p.suffix=='.smali',p
            files[str(p.relative_to(root))]=p
    assert len(files)==7582,len(files)
    return files


def zip_proof(original,candidate,candidate_dex):
    rows={}
    with zipfile.ZipFile(original) as a,zipfile.ZipFile(candidate) as b:
        assert a.namelist()==b.namelist() and a.comment==b.comment
        assert b.testzip() is None
        for name in a.namelist():
            x,y=a.read(name),b.read(name)
            if name=='classes3.dex':assert y==candidate_dex
            else:assert x==y,name
            ai,bi=a.getinfo(name),b.getinfo(name)
            for key in ('date_time','compress_type','comment','extra','create_system',
                        'external_attr','internal_attr','flag_bits'):
                assert getattr(ai,key)==getattr(bi,key),(name,key)
            rows[name]=dict(bytes_before=len(x),bytes_after=len(y),
                sha256_before=hashlib.sha256(x).hexdigest(),sha256_after=hashlib.sha256(y).hexdigest(),
                payload_equal=x==y)
    assert [k for k,v in rows.items() if not v['payload_equal']]==['classes3.dex']
    return rows


def build(result):
    assert os.getuid()==1000
    result['effective_uid']=os.getuid();result['cpu_affinity']=sorted(os.sched_getaffinity(0))
    assert set(result['cpu_affinity']) and set(result['cpu_affinity']) <= {20,21}
    assert digest(ROOT/'toolchain11.json')==TOOL_SHA
    pins=json.loads((ROOT/'toolchain11.json').read_text())
    checked=[*pins['jars'].values(),*pins['jre'].values()]
    for pin in checked:assert pin['exists'] and digest(Path(pin['canonical']))==pin['sha256'],pin
    original=ROOT/'input/services-installed.jar';dex=ROOT/'input/classes3.dex'
    assert digest(original)==JAR_SHA and digest(dex)==DEX_SHA
    candidate=FROZEN/'StorageSessionController.smali';assert digest(candidate)==NEW_CLASS
    ir_source=FROZEN/'smali_equivalence.py';assert digest(ir_source)==IR_SHA
    ir=types.ModuleType('checked_smali_ir');ir.__file__=str(ir_source)
    exec(compile(ir_source.read_bytes(),str(ir_source),'exec'),ir.__dict__)
    reference=ROOT/'preimage12/original-smali'
    tree(reference);assert digest(reference/REL)==OLD_CLASS
    shutil.copytree(reference,OUT/'source')
    shutil.copyfile(candidate,OUT/'source'/REL)
    java=pins['jre']['bin/java']['canonical']
    common=['antlr3-runtime','dexlib2','guava','jcommander','smali-util']
    def command(tool):
        cp=':'.join(pins['jars'][n]['canonical'] for n in [common[0],tool,*common[1:]])
        return [java,'-Xmx1024m','-XX:ActiveProcessorCount=2','-cp',cp,'org.jf.'+tool+'.Main']
    good(run(result,'smali-version',command('smali')+['--version'],10))
    candidate_dex=OUT/'classes3.single-removal.dex'
    good(run(result,'assemble',command('smali')+['assemble','--jobs','2','--api','35',
        '--output',str(candidate_dex),str(OUT/'source')]))
    data=candidate_dex.read_bytes()
    assert data[:8]==b'dex\n039\0' and struct.unpack_from('<I',data,32)[0]==len(data)
    assert hashlib.sha1(data[32:]).digest()==data[12:32]
    assert (zlib.adler32(data[12:])&0xffffffff)==struct.unpack_from('<I',data,8)[0]
    assert struct.unpack_from('<I',data,96)[0]==7582
    for label,source in [('fresh-original',dex),('roundtrip',candidate_dex)]:
        good(run(result,label,command('baksmali')+['disassemble','--jobs','2','--api','35',
            '--output',str(OUT/label),str(source)]))
    before,after=tree(OUT/'fresh-original'),tree(OUT/'roundtrip');assert set(before)==set(after)
    expected_method=ir.class_ir(candidate.read_text())['methods'][METHOD]
    differences=[];class_records={};method_count=0
    for rel in sorted(before):
        a=ir.class_ir(before[rel].read_text());b=ir.class_ir(after[rel].read_text())
        assert a['header']==b['header'],('class_metadata_changed',rel)
        assert set(a['methods'])==set(b['methods']),('method_set_changed',rel)
        for name in a['methods']:
            method_count+=1
            if a['methods'][name] != b['methods'][name]:
                differences.append(dict(file=rel,method=name))
                assert rel==REL and name==METHOD,('non_target_method_changed',rel,name)
        if rel==REL:
            assert b['methods'][METHOD]==expected_method,'ASSEMBLED_TARGET_DIFFERS_FROM_REVIEWED_IR'
        class_records[rel]=dict(before_sha256=digest(before[rel]),after_sha256=digest(after[rel]),
            before_ir_sha256=ir.ir_sha256(a),after_ir_sha256=ir.ir_sha256(b),methods=len(a['methods']))
    assert differences==[dict(file=REL,method=METHOD)],differences
    write(OUT/'all-class-semantic-digests.json',class_records)
    result['semantic_verification']=dict(classes=len(before),methods=method_count,
        differences=differences,non_target_semantic_changes=0,reviewed_target_ir_equal=True,
        class_metadata_and_method_sets_equal=True,
        evidence_sha256=digest(OUT/'all-class-semantic-digests.json'))
    result['candidate_dex']=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
        format='039',checksum_and_signature_valid=True)
    unaligned=OUT/'services-storage-single-removal.unaligned.jar'
    with zipfile.ZipFile(original) as src,zipfile.ZipFile(unaligned,'x') as dst:
        dst.comment=src.comment
        for info in src.infolist():
            dst.writestr(info,data if info.filename=='classes3.dex' else src.read(info.filename))
    proof=zip_proof(original,unaligned,data);write(OUT/'zip-payload-proof.json',proof)
    result['zip_payloads']=dict(members=len(proof),only_changed_member='classes3.dex',
        evidence_sha256=digest(OUT/'zip-payload-proof.json'))
    result['unaligned_jar']=dict(path=str(unaligned),bytes=unaligned.stat().st_size,sha256=digest(unaligned))
    result['state']='DEX_VERIFIED_ALIGNMENT_PENDING'
    zip_pin=pins['zipalign'];assert zip_pin['exists'] and digest(Path(zip_pin['canonical']))==zip_pin['sha256']
    probe=run(result,'zipalign-check-input',[zip_pin['canonical'],'-c','4',str(original)],10)
    if probe['rc']==0 and not probe['timed_out']:
        aligned=OUT/'services-storage-single-removal.jar'
        good(run(result,'zipalign',[zip_pin['canonical'],'4',str(unaligned),str(aligned)],15))
        good(run(result,'zipalign-check-output',[zip_pin['canonical'],'-c','4',str(aligned)],10))
        final=zip_proof(original,aligned,data);assert final==proof
        result['aligned_jar']=dict(path=str(aligned),bytes=aligned.stat().st_size,sha256=digest(aligned))
        result['state']='ALIGNED_OFFLINE_CANDIDATE'
    else:
        run(result,'zipalign-libraries',['/usr/bin/ldd',zip_pin['canonical']],10)
        toolroot=Path(zip_pin['path']).parents[2]
        libs={}
        for relative in ('lib/x86_64-linux-gnu','usr/lib/x86_64-linux-gnu','lib','usr/lib'):
            for p in sorted((toolroot/relative).glob('*zopfli*')):
                if p.is_file():libs[str(p)]=dict(canonical=str(p.resolve()),sha256=digest(p),bytes=p.stat().st_size)
        result['zipalign_library_candidates']=libs
    for pin in checked:assert digest(Path(pin['canonical']))==pin['sha256'],'tool changed during build'
    assert digest(original)==JAR_SHA and digest(dex)==DEX_SHA
    result['inputs_and_tools_unchanged']=True


def main():
    result=dict(started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        state='STARTED',scope='offline DEX assembly and semantic preservation only',commands={},
        complete_java_or_aosp_build=False,android_art_verifier_run=False,
        android_lifecycle_test_run=False,deployed=False,UI_actions=0,runtime_writes=0)
    rc=0
    try:build(result)
    except BaseException as error:
        result['state']='FAILED';result['error']=type(error).__name__+':'+str(error);rc=2
    result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    write(OUT/'result.json',result);print(json.dumps(result,sort_keys=True));return rc


if __name__=='__main__':sys.exit(main())
