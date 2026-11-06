"""Create one local exact build request. Never submit it or install an APK."""
import argparse
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
KEY='pocket4-owned-bili-qa-r7-static-build-01-20261106'


def encode(value):
    return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def make(expected):
    raw=(HERE/'SOURCE_PINS.json').read_bytes()
    assert sha(raw)==expected and len(raw)<=131072
    manifest=json.loads(raw);files={'SOURCE_PINS.json':raw.decode()}
    for name,row in manifest['files'].items():
        path=Path(name);assert not path.is_absolute() and '..' not in path.parts and str(path)==name
        data=(HERE/name).read_bytes();assert len(data)==row['bytes'] and sha(data)==row['sha256']
        files[name]=data.decode('utf-8')
    packet={'schema':1,'stage_source':files['stage_build.py'],'source_manifest_sha256':expected,'files':files}
    wire=encode(packet);assert len(wire)<=524288
    stage_sha=sha(files['stage_build.py'].encode())
    wrapper=("import sys,json,hashlib;raw=sys.stdin.buffer.read(524289);"
        "assert len(raw)<=524288 and hashlib.sha256(raw).hexdigest()=="+repr(sha(wire))+";"
        "packet=json.loads(raw);source=packet['stage_source'];"
        "assert hashlib.sha256(source.encode()).hexdigest()=="+repr(stage_sha)+";"
        "scope={'__name__':'__main__','__file__':'<verified-owned-bili-qa-build-stage>','PACKET':packet};"
        "exec(compile(source,'stage_build.py','exec'),scope,scope)")
    return {'host':'pocket4','executable':'/usr/bin/python3','args':['-I','-c',wrapper],
        'cwd':'/home/alex/work','env':{'PYTHONDONTWRITEBYTECODE':'1'},'stdin':wire.decode(),
        'idempotency_key':KEY,'timeout_seconds':300,'cpu_quota_percent':100,
        'memory_max_bytes':536870912,'nice':10}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-manifest-sha256')
    parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args()
    if args.output_dir is None:
        print(json.dumps({'state':'PLAN_ONLY','key':KEY,'remote_actions':0,'install_or_UI_actions':0}));return
    assert args.source_manifest_sha256 is not None
    request=make(args.source_manifest_sha256);raw=encode(request)
    args.output_dir.mkdir(mode=0o700)
    (args.output_dir/'exact-request.json').open('xb').write(raw)
    pins={'schema':1,'state':'BUILD_ONLY_REQUEST_NOT_SUBMITTED','request_sha256':sha(raw),'request_bytes':len(raw),
          'stdin_sha256':sha(request['stdin'].encode()),'stdin_bytes':len(request['stdin'].encode()),
          'source_manifest_sha256':args.source_manifest_sha256,'stable_key':KEY,
          'remote_actions':0,'install_or_UI_actions':0}
    (args.output_dir/'REQUEST_PINS.json').open('xb').write(encode(pins))
    print(json.dumps(pins))


if __name__=='__main__':
    main()
