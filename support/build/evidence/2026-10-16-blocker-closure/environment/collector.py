import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

root=Path('/workspace/scratch/ae1a8cf05419')
repo=root/'trillionnium-os-desktop'
out=repo/'support/build/evidence/2026-10-16-blocker-closure/environment'
out.mkdir(exist_ok=False)
toolbin=root/'toolchains/rustup/toolchains/nightly-2026-07-21-x86_64-unknown-linux-gnu/bin'
commands=[('dpkg-packages',['dpkg-query','-W','-f=${binary:Package}\t${Version}\t${Architecture}\n']),
          ('kernel',['uname','-a']),('rustc',[str(toolbin/'rustc'),'-Vv']),
          ('cargo',[str(toolbin/'cargo'),'-Vv']),('qemu',['qemu-system-x86_64','--version']),
          ('make',['make','--version']),('source-check',['python3','-I','support/build/verify-source.py'])]
records=[]
for name,argv in commands:
    result=subprocess.run(argv,cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    path=out/(name+'.log');path.write_bytes(result.stdout)
    records.append({'argv':argv,'cwd':str(repo),'returncode':result.returncode,'log':path.name,
                    'sha256':hashlib.sha256(result.stdout).hexdigest()})
paths=[toolbin/'rustc',toolbin/'cargo',Path('/usr/bin/qemu-system-x86_64'),Path('/usr/bin/make'),
       Path('/usr/bin/x86_64-linux-gnu-nm'),Path('/usr/share/seabios/bios-256k.bin'),
       Path('/usr/bin/busybox'),root/'a01-host-tools-next-e5ae/root/usr/bin/gdb',
       root/'toolchains/cargo/bin/rust-strip']
files=[]
for path in paths:
    actual=path.resolve(strict=True); digest=hashlib.sha256()
    with actual.open('rb') as source:
        for data in iter(lambda:source.read(1024*1024),b''):digest.update(data)
    files.append({'requested_path':str(path),'actual_path':str(actual),'bytes':actual.stat().st_size,
                  'sha256':digest.hexdigest()})
report={'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'host':os.uname().nodename,'commands':records,'tool_files':files,
        'scope':'Observed installed environment inventory; does not supply an immutable container/image or an independent second host',
        'secrets_or_complete_environment_saved':False}
out.joinpath('inventory.json').write_text(json.dumps(report,indent=2)+'\n')
out.joinpath('collector.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps({'commands':[(r['log'],r['returncode']) for r in records],'tools':len(files)}))
