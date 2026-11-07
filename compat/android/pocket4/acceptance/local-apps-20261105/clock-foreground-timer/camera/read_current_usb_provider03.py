#!/usr/bin/python3 -I
"""Current exact UVC presence and live provider process birth; host metadata reads only."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, os, stat, subprocess

OUT = Path('/home/alex/work/pocket4-camera-usb-current-20261105-r12-03.json')
TARGET = Path('/sys/devices/pci0000:00/0000:00:08.3/0000:c7:00.0/usb3/3-4')
ALIAS = Path('/sys/bus/usb/devices/3-4')
IDENTITY = {'idVendor':'1e08','idProduct':'5520','serial':'JX20250923V2',
            'bcdDevice':'0923','busnum':'3','devpath':'4'}


def utc():
    return datetime.now(timezone.utc).isoformat()


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def small(path):
    with open(path,'rb') as source:
        raw = source.read(8193)
    require(len(raw) <= 8192,'BOUNDED_METADATA_REQUIRED')
    return raw


def proc(pid):
    root = Path('/proc')/str(pid)
    before = small(root/'stat')
    fields = before.decode()[before.decode().rfind(')')+2:].split()
    require(fields[0] not in ('Z','X'),'PROVIDER_NOT_LIVE')
    value = {'pid':pid,'birth_ticks':int(fields[19]),'state':fields[0],
        'executable':os.readlink(root/'exe'),'mount_namespace':os.readlink(root/'ns/mnt'),
        'pid_namespace':os.readlink(root/'ns/pid'),
        'commandline_sha256':hashlib.sha256(small(root/'cmdline')).hexdigest(),
        'cgroup':small(root/'cgroup').decode().strip()}
    after = small(root/'stat').decode()
    require(int(after[after.rfind(')')+2:].split()[19]) == value['birth_ticks'],'PROVIDER_GENERATION_CHANGED')
    require(value['cgroup'].endswith('/system.slice/pocket4-live-camera.service'),'PROVIDER_CGROUP_CHANGED')
    return value


def main():
    p = argparse.ArgumentParser(); p.add_argument('--execute-read-only',action='store_true')
    if not p.parse_args().execute_read_only:
        print(json.dumps({'state':'INERT','UI_actions':0,'sysfs_writes':0,'service_changes':0})); return 0
    require(os.geteuid() == 0,'ROOT_METADATA_READER_REQUIRED')
    require(os.uname().nodename == 'alex-G1628-04' and os.uname().release == '7.0.0-38-generic','HOST_CHANGED')
    boot = small('/proc/sys/kernel/random/boot_id').decode().strip()
    require(boot == '981ff371-cd72-4f81-9be3-a862111afdb1','BOOT_CHANGED')
    require(os.readlink('/proc/self/ns/mnt') == 'mnt:[4026531832]','HOST_NAMESPACE_CHANGED')
    result = {'started_utc':utc(),'boot_id':boot,'read_only':True,'UI_actions':0,
        'sysfs_writes':0,'service_changes':0,'device_open_calls':0,'owner_lock_acquisitions':0,
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    code = 0
    try:
        if ALIAS.exists():
            require(ALIAS.resolve(strict=True) == TARGET,'USB_TOPOLOGY_CHANGED')
            descriptor = os.open(TARGET,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:
                initial = os.fstat(descriptor)
                values = {}
                for key in (*IDENTITY,'devnum','power/control','power/runtime_status'):
                    fd = os.open(key,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=descriptor)
                    try:
                        raw = os.read(fd,4097);require(len(raw)<=4096,'USB_ATTRIBUTE_TOO_LARGE')
                        values[key] = raw.decode('ascii').strip()
                    finally: os.close(fd)
                require({key:values[key] for key in IDENTITY} == IDENTITY,'USB_IDENTITY_CHANGED')
                after = os.stat(TARGET,follow_symlinks=False)
                require((initial.st_dev,initial.st_ino) == (after.st_dev,after.st_ino),'USB_GENERATION_CHANGED')
                result['camera'] = {'present':True,'target':str(TARGET),'observed_utc':utc(),
                    'device':initial.st_dev,'inode':initial.st_ino,'attributes':values}
            finally: os.close(descriptor)
        else:
            result['camera'] = {'present':False,'target':str(TARGET),'observed_utc':utc()}
        result['matching_video_nodes'] = []
        nodes = Path('/sys/class/video4linux')
        if nodes.exists():
            for item in sorted(nodes.iterdir()):
                actual = item.resolve(strict=True)
                if str(actual).startswith(str(TARGET)+'/'):
                    result['matching_video_nodes'].append({'name':item.name,'sysfs_target':str(actual),
                        'device_number':small(item/'dev').decode().strip()})
        call = subprocess.run(['/usr/bin/systemctl','show','pocket4-live-camera.service',
            '--property=Id,MainPID,ActiveState,SubState,ControlGroup'],stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,check=True)
        properties = dict(line.split('=',1) for line in call.stdout.decode().splitlines())
        require(properties['Id'] == 'pocket4-live-camera.service','PROVIDER_UNIT_CHANGED')
        result['provider_unit'] = properties
        pid = int(properties['MainPID'])
        result['provider_process'] = proc(pid) if pid else None
        result['state'] = 'CURRENT_METADATA_OBSERVED'
    except BaseException as error:
        code = 1; result['state'] = 'READ_FAILED';result['error'] = type(error).__name__+': '+str(error)
    result['finished_utc'] = utc()
    data = (json.dumps(result,sort_keys=True,indent=2)+'\n').encode()
    fd = os.open(OUT,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o640)
    try:
        os.fchown(fd,0,1000);os.fchmod(fd,0o640)
        with os.fdopen(os.dup(fd),'wb') as f: f.write(data);f.flush();os.fsync(f.fileno())
    finally: os.close(fd)
    print(json.dumps({'result':result,'path':str(OUT),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()},sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
