"""Fixed create-only source staging and build-only entry. Default: PLAN_ONLY."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import types

ROOT = Path('/home/alex/work/pocket4-owned-bestbuy-qa-r4-source-01')
OUTPUT = Path('/home/alex/work/pocket4-owned-bestbuy-qa-r4-build-01')
MEMORY = 536870912


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_new(path, raw):
    if not isinstance(raw, bytes):
        raw = (json.dumps(raw, indent=2)+'\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno()); os.fchmod(stream.fileno(),0o444)


def validate_packet(packet):
    require(isinstance(packet, dict) and set(packet) == {'schema','stage_source','source_manifest_sha256','files'} and
            packet['schema'] == 1 and isinstance(packet['files'], dict), 'EXACT_BUILD_PACKET_REQUIRED')
    files = packet['files']
    require(10 <= len(files) <= 33 and 'SOURCE_PINS.json' in files and
            files.get('stage_build.py') == packet['stage_source'], 'COMPLETE_SOURCE_PACKET_REQUIRED')
    raw = {name:value.encode('utf-8') for name,value in files.items() if isinstance(value,str)}
    require(set(raw) == set(files) and sum(len(value) for value in raw.values()) <= 524288,
            'UTF8_SOURCE_PACKET_BOUND')
    manifest = json.loads(raw['SOURCE_PINS.json'])
    require(sha(raw['SOURCE_PINS.json']) == packet['source_manifest_sha256'] and
            set(manifest['files']) | {'SOURCE_PINS.json'} == set(files), 'EXTERNAL_SOURCE_MANIFEST_CHANGED')
    for name, value in raw.items():
        path = PurePosixPath(name)
        require(not path.is_absolute() and '..' not in path.parts and str(path) == name and
                name not in ('','.','..') and '\0' not in name and len(value) <= 262144,
                'RELATIVE_BOUNDED_TEXT_SOURCE_REQUIRED')
        if name != 'SOURCE_PINS.json':
            require(manifest['files'][name] == {'bytes':len(value),'sha256':sha(value)}, 'SOURCE_PAYLOAD_CHANGED')
    return raw


def resources(cgroup):
    record = {'cgroup':str(cgroup), 'device':cgroup.stat().st_dev,'inode':cgroup.stat().st_ino}
    for name in ('memory.max','memory.swap.max','cpu.max','pids.max','memory.events','memory.current',
                 'memory.peak','memory.swap.current','memory.swap.peak','cgroup.procs'):
        text = (cgroup/name).read_text();require(len(text) <= 16384,'OWNED_RESOURCE_BOUND')
        record[name] = text.strip()
    require(str(os.getpid()) in record['cgroup.procs'].split() and record['memory.max'] == str(MEMORY) and
            record['cpu.max'] == '100000 100000' and record['memory.swap.max'] == '0' and
            record['pids.max'] == '128', 'OWNED_BUILD_RESOURCE_IDENTITY_DIFFERS')
    return record


def execute(packet):
    payload = validate_packet(packet)
    require(os.getuid() == os.geteuid() == 1000 and ROOT.parent.resolve() == ROOT.parent,
            'EXACT_UNPRIVILEGED_BUILD_OPERATOR_REQUIRED')
    require(not os.path.lexists(ROOT) and not os.path.lexists(OUTPUT), 'NEW_SOURCE_AND_BUILD_ROOT_REQUIRED')
    raw = Path('/proc/self/cgroup').read_text().strip()
    require(raw.startswith('0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-') and
            '\n' not in raw, 'OWNED_MANAGED_BUILD_UNIT_REQUIRED')
    cgroup = Path('/sys/fs/cgroup') / raw[3:].lstrip('/')
    require(cgroup.name.startswith('hepta-runtime-job-') and cgroup.name.endswith('.service') and
            (cgroup/'memory.max').read_text().strip() == str(MEMORY) and
            (cgroup/'cpu.max').read_text().strip() == '100000 100000', 'EXACT_BUILD_UNIT_LIMITS_REQUIRED')
    # Only this current exact owned unit; never the Main service or a parent.
    subprocess.run(['/usr/bin/systemctl','--user','set-property','--runtime',cgroup.name,
                    'MemorySwapMax=0','TasksMax=128'],check=True,capture_output=True,timeout=10)
    before = resources(cgroup)
    os.umask(0o077); ROOT.mkdir(mode=0o700); source = ROOT/'source';source.mkdir(mode=0o700)
    result = {'schema':1,'state':'BUILD_STAGE_FAILED','source_manifest_sha256':packet['source_manifest_sha256'],
              'root':str(ROOT),'source':str(source),'output':str(OUTPUT),'owned_before':before,
              'build_returncode':None,'error':None,'secondary_errors':[],
              'Main_actions':0,'Android_install_or_UI_actions':0,'automatic_retry':False,
              'whole_app_production_ready':False}
    try:
        write_new(ROOT/'once.claim.json', {'source_manifest_sha256':packet['source_manifest_sha256'],
                  'unit':cgroup.name,'unit_device':before['device'],'unit_inode':before['inode'],'automatic_retry':False})
        for name, data in payload.items():
            target=source/name;target.parent.mkdir(mode=0o700,parents=True,exist_ok=True);write_new(target,data)
        builder=types.ModuleType('owned_bestbuy_qa_build');builder.__file__=str(source/'build_candidate.py')
        exec(compile(payload['build_candidate.py'],builder.__file__,'exec'),builder.__dict__)
        code=builder.build_once(packet['source_manifest_sha256']);result['build_returncode']=code
        if (OUTPUT/'build-result.json').is_file():
            data=(OUTPUT/'build-result.json').read_bytes();require(len(data)<=1048576,'BUILD_RECEIPT_BOUND')
            result['build_result']={'path':str(OUTPUT/'build-result.json'),'bytes':len(data),'sha256':sha(data)}
        require(code==0 and 'build_result' in result,'ACTUAL_BUILD_DID_NOT_COMPLETE')
        result['state']='OWNED_QA_APK_STATIC_BUILD_PASS_ANDROID_UNRUN'
    except BaseException as error:
        result['error']={'type':type(error).__name__,'message':str(error),'notes':getattr(error,'__notes__',[])}
    finally:
        try:
            after=resources(cgroup);result['owned_after']=after
            require((after['device'],after['inode'])==(before['device'],before['inode']),'OWNED_BUILD_CGROUP_CHANGED')
            rows=[line.split() for line in after['memory.events'].splitlines()]
            require(rows and all(len(row)==2 and row[1].isdigit() for row in rows),'OWNED_MEMORY_EVENTS_MALFORMED')
            events={key:int(value) for key,value in rows}
            require(len(events)==len(rows) and all(key in events and events[key]==0
                    for key in ('oom','oom_kill','oom_group_kill')),'OWNED_BUILD_OOM_OBSERVED_OR_MISSING')
        except BaseException as error:
            value={'type':type(error).__name__,'message':str(error)}
            if result['error'] is None:result['error']=value
            else:result['secondary_errors'].append(value)
            result['state']='BUILD_STAGE_FAILED'
        write_new(ROOT/'stage-result.json',result)
    print(json.dumps({'state':result['state'],'result':str(ROOT/'stage-result.json'),
          'result_sha256':sha((ROOT/'stage-result.json').read_bytes()),'Android_actions':0}))
    return 0 if result['state']=='OWNED_QA_APK_STATIC_BUILD_PASS_ANDROID_UNRUN' else 1


if __name__ == '__main__':
    if 'PACKET' not in globals():
        print(json.dumps({'state':'PLAN_ONLY','source_root':str(ROOT),'output':str(OUTPUT),
              'cpu_percent':100,'memory_max':MEMORY,'swap_max':0,'tasks_max':128,
              'install_or_UI_actions':0}))
    else:
        raise SystemExit(execute(PACKET))
