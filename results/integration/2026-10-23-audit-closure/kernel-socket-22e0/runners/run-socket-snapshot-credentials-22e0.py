from pathlib import Path
import hashlib, json, os, subprocess, time, sys
kind=sys.argv[1]
assert kind in ('lifetime','groups')
SUITE='credentials59' if kind=='lifetime' else 'groups16'
ROOT=Path(__file__).resolve().parents[1]
DATA=Path('/data/asterinas-audit-build.8tdrjboi')
SOURCE=DATA/'socket-credential-snapshot'
OUT=DATA/'socket-credential-native-22e0-01'
HEAD='22e0a19f8ab95f730e0fedd85462157ed3d9a10e'
TREE='9cbd2a0762b42a63cb2c718746773d6555c46460'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def snapshot():
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()==HEAD
    assert subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=SOURCE,text=True).strip()==TREE
    assert not subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=all'],cwd=SOURCE)
    entries=[]
    for item in subprocess.check_output(['git','ls-files','-s','-z'],cwd=SOURCE).split(b'\0'):
        if not item:continue
        attrs,name=item.split(b'\t',1);mode,blob,stage=attrs.decode().split();assert stage=='0'
        path=SOURCE/os.fsdecode(name)
        value=os.readlink(path).encode() if mode=='120000' else path.read_bytes()
        assert hashlib.sha1(b'blob '+str(len(value)).encode()+b'\0'+value).hexdigest()==blob,str(path)
        entries.append({'path':os.fsdecode(name),'mode':mode,'blob':blob,'sha256':hashlib.sha256(value).hexdigest()})
    return {'head':HEAD,'tree':TREE,'tracked_files':entries}
base=json.loads((OUT/'full/source-before.json').read_text())
before=snapshot();assert before==base
ordinary=json.loads((OUT/'ordinary/result.json').read_text())
assert ordinary['passed'] and ordinary['source_inputs_unchanged']
assert ordinary['source_head']==HEAD and ordinary['source_tree']==TREE
kernel=OUT/'ordinary/product-kernel.elf'
assert sha(kernel)==ordinary['kernel_elf_sha256']
report={'schema':'trillionnium.native-socket-credentials-source-bound.v1','source_head':HEAD,'source_tree':TREE,'source_before_sha256':sha(OUT/'full/source-before.json'),'ordinary_receipt_sha256':sha(OUT/'ordinary/result.json'),'kernel_sha256':sha(kernel),'passed':False,'complete':False,'production_authority':False,'g2_complete':False}
file=OUT/(SUITE+'-source-bound.json')
assert not file.exists()
def save():file.write_text(json.dumps(report,indent=2)+'\n')
argv=['python3','-I','-B','tests/workloads/linux/socket_credentials/run_guest.py','--suite',kind,'--probe',str(DATA/'socket-credential-lifetime-audit-01'/('socket-credential-probe' if kind=='lifetime' else 'socket-group-probe')),'--kernel',str(kernel),'--initramfs',str(SOURCE/'support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz'),'--output',str(OUT/SUITE)]
report['argv']=argv;save();start=time.monotonic()
try:
    with (OUT/(SUITE+'-console.log')).open('xb') as log:
        code=subprocess.run(argv,cwd=SOURCE,stdout=log,stderr=subprocess.STDOUT,timeout=240).returncode
    report['exit_code']=code
    result=OUT/SUITE/'result.json'
    if result.is_file():report['guest_receipt_sha256']=sha(result)
    after=snapshot();report['source_unchanged']=before==after
    (OUT/(SUITE+'-source-after.json')).write_text(json.dumps(after,indent=2)+'\n')
    report['source_after_sha256']=sha(OUT/(SUITE+'-source-after.json'))
    report['passed']=code==0 and report['source_unchanged'] and json.loads(result.read_text())['passed']
finally:
    report['elapsed_seconds']=round(time.monotonic()-start,3);report['complete']=True;save()
raise SystemExit(0 if report['passed'] else 1)
