#!/usr/bin/python3 -I
"""Single create-only stage and exec of the reviewed Documents/SAF flow."""
from pathlib import Path
import ast, base64, hashlib, json, os, sys, zlib

TOOLS=Path('/home/alex/work/pocket4-documents-flow-20261105-r12-tools-09')
RUN=Path('/home/alex/work/pocket4-documents-flow-20261105-r12-09')
PINS={'ui_adapter02.py':'74234c0a3db0659e4632ce3e76510d80fe8b015514c6a72dc9e34bca31a83a54',
      'run_saf09.py':'93ce75cffa2ac2dadf70d5f10647f4ec0c9ef597baed7d06f96cbe0d5719056d'}


def need(value,reason):
    if not value:raise RuntimeError(reason)


def main():
    need(os.geteuid()==0 and len(sys.argv)==3,'ROOT_AND_EXACT_BUNDLE_ARGUMENTS_REQUIRED')
    compressed=base64.b64decode(sys.argv[1],validate=True)
    need(len(compressed)<=65536 and hashlib.sha256(compressed).hexdigest()==sys.argv[2],'BUNDLE_PIN_CHANGED')
    decoder=zlib.decompressobj();raw=decoder.decompress(compressed,131072)
    need(decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data,'BUNDLE_ENCODING_OR_BOUND')
    bundle=json.loads(raw);need(set(bundle)==set(PINS),'EXACT_TWO_REVIEWED_SOURCES_REQUIRED')
    files={name:base64.b64decode(value,validate=True) for name,value in bundle.items()}
    for name,data in files.items():
        need(hashlib.sha256(data).hexdigest()==PINS[name],'REVIEWED_SOURCE_CHANGED:'+name)
        ast.parse(data,filename=name)
    need(TOOLS.parent.resolve()==TOOLS.parent and not os.path.lexists(TOOLS) and not os.path.lexists(RUN),
        'FRESH_EXACT_STAGE_AND_RESULT_ROOTS_REQUIRED')
    os.umask(0o077);TOOLS.mkdir(mode=0o700)
    for name,data in files.items():
        fd=os.open(TOOLS/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as out:out.write(data);out.flush();os.fsync(out.fileno())
    manifest={'sources':PINS,'compressed_bundle_sha256':sys.argv[2],'automatic_retry':False,
        'temporary_package':'org.droidloom.qa.saf.r12.n69814e80ea71f485','max_seconds':720,'max_ui_actions':36}
    fd=os.open(TOOLS/'stage-manifest.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as out:json.dump(manifest,out,indent=2);out.write('\n');out.flush();os.fsync(out.fileno())
    os.execve('/usr/bin/python3',['/usr/bin/python3','-I',str(TOOLS/'run_saf09.py'),'--execute'],
        {'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})


if __name__=='__main__':main()
