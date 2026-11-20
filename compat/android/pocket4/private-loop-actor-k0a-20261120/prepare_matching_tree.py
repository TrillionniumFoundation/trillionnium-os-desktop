#!/usr/bin/python3
"""Prepare a matching source/header tree only; do not compile or operate devices."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import resource
import shutil
import signal
import stat
import subprocess
import tarfile
import time

ROOT = Path('/home/alex/work/p4-private-loop-k0a-compile-20261120-3b9d-r1')
INPUT = ROOT / 'inputs'
SOURCE = ROOT / 'source/linux-6.18.64'
OUT = ROOT / 'out'
PINS = {
  "target.config": {
    "bytes": 304072,
    "sha256": "bccb147083a909408e25dc63f1dd58cf465ee19bcabc660916a1fa28cc67a3e1"
  },
  "target-autoconf.h": {
    "bytes": 375632,
    "sha256": "bbee841212e4d2dc83fcb54a32e8b6080013e67877137d01c3f60f8597993275"
  },
  "candidate-final.patch": {
    "bytes": 84316,
    "sha256": "b9e77cdc6683b1a7eeb193fda35d8ac6945a24cb3e1a9f9f8cd804a0de20fdd2"
  },
  "SOURCE_FREEZE.json": {
    "bytes": 66444,
    "sha256": "3ea7961b7fd103c506604658426a25669054f259533dae9e5ec312001a276140"
  },
  "candidate-source-pins.json": {
    "bytes": 17673,
    "sha256": "4b5b19d3cbcd3caa5eb48ec65bc0e5dc3f0e1651f5f41a26a434019ece8686e7"
  },
  "linux-6.18.64.tar.sign": {
    "bytes": 991,
    "sha256": "dd1c4390eead8acece7acf1f4eeda4c0f2db4876545d0c8f6c284d68f6d910af"
  },
  "gregkh-wkd-public-key.gpg": {
    "bytes": 3576,
    "sha256": "61b758f0d4a386fc83565b92cfd6c05879573df0e96d44b71a5a3e19e1a8581a"
  },
  "GENERATED-SMALL-HEADERS.json": {
    "bytes": 116832,
    "sha256": "5333b13acdaff182b995666acf19db1d3f91126730ba23191288a6ec09be0614"
  },
  "GENERATED-HEADER-PINS.json": {
    "bytes": 7095,
    "sha256": "2736cd27249da883e295a7bcdc619b0408fa61d4804d608a32b35b158e4570e5"
  },
  "COMPILE-COMMAND-SOURCE.json": {
    "bytes": 4328,
    "sha256": "f5fb2841adfa02c8e2f89bba0c96071ff8fe51809f52b2965037d99c6676db43"
  },
  "K0a.patch": {
    "bytes": 9758,
    "sha256": "1e75b6fb1e3f65b581df35f54122845acc4a7eb835f10d5e8231992635df1e86"
  },
  "K0A-MANIFEST.json": {
    "bytes": 1923,
    "sha256": "37f6e6f410a340b15a1eedfb558b7d82dc35c97c760b4e58151ebd0678be4464"
  },
  "K0A-INPUTS.json": {
    "bytes": 4842,
    "sha256": "5d1bca7225853e312d0a7b2b4720fd4b0587a78143e67ee4ed0461ca23f4c799"
  }
}
ARCHIVE_SIZE = 155382076
ARCHIVE_SHA = '020d45510c539972e6f14c5c71566878d3b7ef56fb082b3e09134f2ebaade562'
SIGNER = '647F28654894E3BD457199BE38DBBDC86092693E'
DEADLINE = None
OBS = {'schema':'p4-k0a-exact-matching-source-preparation-v1','state':'PENDING',
       'compiler_executed':False,'kernel_loaded':False,'Android_started':False,
       'VM_started':False,'runtime_qualified':False,'production_ready':False,
       'commands':[]}

def need(value, reason):
    if not value: raise RuntimeError(reason)

def f9(s):
    return [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]

def reference(path, expected=None):
    need(path.resolve()==path, 'canonical input')
    with path.open('rb') as stream:
        before=f9(os.fstat(stream.fileno()))
        need(stat.S_ISREG(before[2]) and before[5]==1, 'regular single-link input')
        h=hashlib.sha256()
        for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
        need(f9(os.fstat(stream.fileno()))==f9(path.lstat())==before, 'complete input bookend')
    row={'path':str(path),'bytes':before[6],'sha256':h.hexdigest(),'identity':before}
    if expected is not None:
        need(row['bytes']==expected['bytes'] and row['sha256']==expected['sha256'], 'exact content pin: '+str(path))
    return row

def write_new(path, body):
    need(path.parent.resolve()==path.parent, 'canonical new parent')
    with path.open('xb') as stream:
        stream.write(body);stream.flush();os.fsync(stream.fileno())
    return reference(path)

def remaining(maximum=300):
    need(DEADLINE is not None and time.monotonic()<DEADLINE, 'preparation deadline')
    return min(maximum, DEADLINE-time.monotonic())

def retire(process):
    if process.poll() is None:
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
    else:process.wait()

def run(name, argv, cwd):
    stdout=ROOT/'logs'/(name+'.stdout');stderr=ROOT/'logs'/(name+'.stderr')
    started=time.monotonic_ns()
    with stdout.open('xb') as out,stderr.open('xb') as err:
        child=subprocess.Popen(argv,cwd=cwd,stdout=out,stderr=err,
            env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
        pid=child.pid
        try:code=child.wait(timeout=remaining())
        finally:retire(child)
    row={'name':name,'argv':argv,'pid':pid,'exit_code':code,'actual_child_reaped':True,
         'started_monotonic_ns':started,'finished_monotonic_ns':time.monotonic_ns(),
         'stdout':reference(stdout),'stderr':reference(stderr)}
    OBS['commands'].append(row)
    need(code==0,'command failed: '+name)
    return row

def signature(archive):
    home=ROOT/'public-gpg-home';home.mkdir(mode=0o700)
    paths={k:ROOT/'logs'/('signature.'+k) for k in ('status','stderr','xz-stderr')}
    with paths['status'].open('xb') as out,paths['stderr'].open('xb') as err,paths['xz-stderr'].open('xb') as xerr:
        xz=subprocess.Popen(['/usr/bin/xz','-cd',str(archive)],stdout=subprocess.PIPE,stderr=xerr)
        gpg=None
        try:
            gpg=subprocess.Popen(['/usr/bin/gpgv','--homedir',str(home),'--status-fd','1',
                '--keyring',str(INPUT/'gregkh-wkd-public-key.gpg'),str(INPUT/'linux-6.18.64.tar.sign'),'-'],
                stdin=xz.stdout,stdout=out,stderr=err)
            xz.stdout.close()
            gcode=gpg.wait(timeout=remaining());xcode=xz.wait(timeout=remaining())
        finally:
            if gpg is not None:retire(gpg)
            retire(xz)
    refs={k:reference(v) for k,v in paths.items()}
    need(gcode==xcode==0,'actual upstream signature children failed')
    need('[GNUPG:] VALIDSIG '+SIGNER+' ' in paths['status'].read_text(),'actual upstream signer')
    OBS['signature']={'gpgv_exit':gcode,'xz_exit':xcode,'all_actual_children_reaped':True,
                      'signer':SIGNER,'outputs':refs}

def pin_rows(rows, prefix, side):
    for row in rows:
        p=prefix/row['path']
        if row[side+'_sha256'] is None:need(not os.path.lexists(p),'new path already exists')
        else:reference(p,{'bytes':row[side+'_bytes'],'sha256':row[side+'_sha256']})

def main():
    global DEADLINE
    need(os.getuid()==os.geteuid()==os.getgid()==1000,'ordinary Pocket4 owner')
    need(ROOT.resolve()==ROOT and ROOT.stat().st_uid==1000,'own canonical compile root')
    need(not SOURCE.exists() and not (ROOT/'TREE-PREPARATION.json').exists(),'create-only source and receipt')
    need(23 in os.sched_getaffinity(0),'reserved CPU23')
    os.sched_setaffinity(0,{23});os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
    resource.setrlimit(resource.RLIMIT_CPU,(540,540))
    resource.setrlimit(resource.RLIMIT_FSIZE,(2*1024**3,2*1024**3))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));signal.alarm(600)
    DEADLINE=time.monotonic()+570
    OBS.update(state='INPUT_ADMISSION',affinity=[23],memory_address_space_limit=2*1024**3)
    original={name:reference(INPUT/name,pin) for name,pin in PINS.items()}
    download=json.loads((ROOT/'DOWNLOAD-R2.json').read_bytes())
    need(download['state']=='EXACT_OFFICIAL_ARCHIVE_DOWNLOADED_SIGNATURE_PENDING'
         and download['bytes']==ARCHIVE_SIZE and download['sha256']==ARCHIVE_SHA,'actual completed download')
    archive=Path(download['path'])
    need(archive==INPUT/'linux-6.18.64-r2.tar.xz','exact downloaded artifact path')
    archive_ref=reference(archive,{'bytes':ARCHIVE_SIZE,'sha256':ARCHIVE_SHA})
    signature(archive)
    need(reference(archive)==archive_ref,'original signed archive identity')
    OBS['state']='EXTRACTING_VERIFIED_OFFICIAL_SOURCE'
    free=shutil.disk_usage(ROOT).free;need(free>=8*1024**3,'actual disk reserve before extraction')
    need(not any((ROOT/'source').iterdir()),'fresh empty source parent')
    with tarfile.open(archive,'r:xz') as tar:
        members=tar.getmembers()
        need(len(members)==97306 and sum(m.size for m in members if m.isfile())==1547150736,
             'exact original complete upstream member count and bytes')
        need(len({m.name for m in members})==len(members),'no duplicate archive paths')
        for m in members:
            p=PurePosixPath(m.name)
            need(not p.is_absolute() and '..' not in p.parts and p.parts[0]=='linux-6.18.64'
                 and not m.isdev() and not m.isfifo(),'bounded upstream extraction member')
        tar.extractall(ROOT/'source',filter='data')
    need(reference(archive)==archive_ref,'archive unchanged after extraction')
    rows=json.loads((INPUT/'candidate-source-pins.json').read_bytes())
    need(len(rows)==66,'formal sixty-six-path kernel candidate')
    pin_rows(rows,SOURCE,'before')
    run('formal-patch-check',['/usr/bin/patch','--dry-run','--forward','--batch','--fuzz=0','-p1','-i',str(INPUT/'candidate-final.patch')],SOURCE)
    run('formal-patch-apply',['/usr/bin/patch','--forward','--batch','--fuzz=0','-p1','-i',str(INPUT/'candidate-final.patch')],SOURCE)
    pin_rows(rows,SOURCE,'after')
    freeze=json.loads((INPUT/'SOURCE_FREEZE.json').read_bytes())
    released=[row for row in freeze['files'] if row['path'].startswith('source/')]
    need(len(released)==66,'formal release source set')
    for row in released:reference(SOURCE/row['path'][7:],row)
    inputs=json.loads((INPUT/'K0A-INPUTS.json').read_bytes())
    for row in inputs['files']:
        name=row['path'].removeprefix(inputs['kernel_root']+'/')
        need(name!=row['path'],'exact original kernel input prefix')
        reference(SOURCE/name,{'bytes':row['size'],'sha256':row['sha256']})
    run('k0a-patch-check',['/usr/bin/patch','--dry-run','--forward','--batch','--fuzz=0','-p1','-i',str(INPUT/'K0a.patch')],SOURCE)
    run('k0a-patch-apply',['/usr/bin/patch','--forward','--batch','--fuzz=0','-p1','-i',str(INPUT/'K0a.patch')],SOURCE)
    manifest=json.loads((INPUT/'K0A-MANIFEST.json').read_bytes())
    for row in manifest['files']:reference(SOURCE/row['path'],row['after'])
    pin_rows(rows,SOURCE,'after')
    headers=json.loads((INPUT/'GENERATED-HEADER-PINS.json').read_bytes())
    small=json.loads((INPUT/'GENERATED-SMALL-HEADERS.json').read_bytes())
    need(len(headers)==43 and len(small['files'])==42,'exact generated C header set')
    expected={row['path']:row for row in headers}
    need(len(expected)==43 and 'include/generated/rustc_cfg' not in expected,'C-only generated inputs')
    for row in small['files']:
        need(row['path'] in expected and row['sha256']==expected[row['path']]['sha256']
             and row['bytes']==expected[row['path']]['bytes'],'same complete generated header pin')
        body=row['body'].encode()
        need(len(body)==row['bytes'] and hashlib.sha256(body).hexdigest()==row['sha256'],'complete real header body')
        target=OUT/row['path']
        need(target.parent.resolve()==target.parent,'exact generated-header parent')
        if target.exists():
            need(row['path']=='include/generated/asm-offsets.h','only the one prior exact header may exist')
            reference(target,row)
        else:write_new(target,body)
    write_new(OUT/'include/generated/autoconf.h',(INPUT/'target-autoconf.h').read_bytes())
    write_new(OUT/'.config',(INPUT/'target.config').read_bytes())
    for row in headers:reference(OUT/row['path'],row)
    config=reference(OUT/'.config',PINS['target.config'])
    for name,ref in original.items():need(reference(INPUT/name)==ref,'immutable preparation input changed')
    need(reference(archive)==archive_ref,'signed archive final bookend')
    OBS.update(state='EXACT_MATCHING_SOURCE_AND_C_HEADERS_PREPARED',source=str(SOURCE),output=str(OUT),
        source_archive=archive_ref,source_formal_changed_paths=66,k0a_preimages=12,
        k0a_postimages=manifest['files'],generated_C_headers=headers,configuration=config,
        configuration_changed=False,new_option_enabled_in_configuration=False,
        build_scope='direct single C object with actual target config/generated headers; Kbuild selection not executed',
        input_refs=original,disk_free_before_extraction=free,disk_free_after_preparation=shutil.disk_usage(ROOT).free)

if __name__=='__main__':
    try:main()
    except BaseException as error:
        OBS.update(state='FAILED',error=type(error).__name__+': '+str(error))
        raise
    finally:
        raw=(json.dumps(OBS,indent=2,sort_keys=True)+'\n').encode()
        path=ROOT/'TREE-PREPARATION.json'
        write_new(path,raw)
        print(json.dumps({'state':OBS['state'],'receipt':str(path),'bytes':len(raw),
                          'sha256':hashlib.sha256(raw).hexdigest(),'compiler_executed':False}),flush=True)
