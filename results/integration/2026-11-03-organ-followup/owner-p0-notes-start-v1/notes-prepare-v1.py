import ctypes, hashlib, importlib.util, json, os, stat, subprocess, sys, time
from pathlib import Path

assert os.getuid() == os.geteuid() == 0
os.umask(0o077)
release = Path('/opt/trill-organ-20261103/releases/fd8d56c52b97-053cc1957b40')
private = Path('/root/trill-organ-owner-20261103')
prefix = Path('/var/lib/trill/o1103n1')
output = Path('/data/trill-organ-owner-20261103/root-fd-v5-tests-package-01/notes-prepare-v1.json')
allowed = ('DISPLAY','WAYLAND_DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS','XAUTHORITY','XMODIFIERS','LANG','LC_ALL')
environment = json.loads(sys.argv[1])
assert set(environment).issubset(allowed)
assert not private.exists() and not prefix.exists() and not output.exists()
receipt = {'schema':'trill.audit.original-notes-prepare.v1', 'scope':'New private administrator inputs and actual graphical prerequisites only',
           'initialization_started':False, 'authority_created':False, 'model_turn_sent':False, 'effect_requested':False,
           'release':str(release), 'prefix':str(prefix), 'started_unix_ms':int(time.time()*1000)}

def regular(path, uid, executable=False):
    path = Path(path); s = path.lstat()
    assert path.is_absolute() and path.resolve(strict=True) == path
    assert stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_uid == uid and not s.st_mode & 0o022
    if executable: assert s.st_mode & 0o111
    return {'path':str(path),'uid':s.st_uid,'gid':s.st_gid,'mode':oct(stat.S_IMODE(s.st_mode)),'bytes':s.st_size,'nlink':s.st_nlink}

try:
    spec = importlib.util.spec_from_file_location('native_human_original', release/'libexec/native_human.py')
    native = importlib.util.module_from_spec(spec); spec.loader.exec_module(native)
    session = native.local_session(1000)
    receipt['original_logind_session'] = session
    leader = int(session['Leader']); pinned = os.pidfd_open(leader)
    try:
        before = Path('/proc/'+str(leader)+'/stat').read_text().rsplit(')',1)[1].split()[19]
        raw = Path('/proc/'+str(leader)+'/environ').read_bytes()
        selected = {}
        for pair in raw.split(b'\0'):
            if b'=' not in pair: continue
            k,v = pair.split(b'=',1)
            if k.decode(errors='replace') in allowed: selected[k.decode()] = v.decode()
        after = Path('/proc/'+str(leader)+'/stat').read_text().rsplit(')',1)[1].split()[19]
        assert before == after
        receipt['leader_graphical_environment'] = selected
        receipt['leader_start_ticks'] = int(before)
    finally:
        os.close(pinned)
    # Keep the actual operator's display choices; do not read any credential bytes.
    assert environment['XDG_RUNTIME_DIR'] == '/run/user/1000'
    assert environment['DBUS_SESSION_BUS_ADDRESS'] == 'unix:path=/run/user/1000/bus'
    assert environment.get('XMODIFIERS') == '@im=ibus'
    assert environment.get('DISPLAY') and environment.get('WAYLAND_DISPLAY')
    runtime = Path(environment['XDG_RUNTIME_DIR']); rs = runtime.lstat()
    assert runtime.resolve(strict=True) == runtime and stat.S_ISDIR(rs.st_mode) and rs.st_uid == 1000 and stat.S_IMODE(rs.st_mode) == 0o700
    for socket in (runtime/'bus', runtime/environment['WAYLAND_DISPLAY']):
        ss = socket.lstat(); assert stat.S_ISSOCK(ss.st_mode) and ss.st_uid == 1000
    assert not (runtime/'trillionnium-ui/session.sock').exists()
    receipt['xauthority_metadata'] = regular(environment['XAUTHORITY'],1000)
    receipt['selected_environment'] = environment
    programs = {name:str(release/'bin'/file) for name,file in [('agentd','codex-hepta-agentd'),('app_server','codex-app-server'),('authority_host','hepta-authority-host')]}
    programs.update({name:str(release/'desktop/bin'/file) for name,file in [('session','trill-session'),('shell','trill-shell'),('app_window','trill-app-window')]})
    programs.update(python='/usr/bin/python3.12',human_provider=str(release/'libexec/native_human.py'))
    receipt['program_metadata'] = {name:regular(path,0,name!='human_provider') for name,path in programs.items()}
    probe = '''import ctypes,json,gi,os
gi.require_version("Atspi","2.0")
from gi.repository import Atspi
x=ctypes.CDLL("libX11.so.6");x.XOpenDisplay.argtypes=[ctypes.c_char_p];x.XOpenDisplay.restype=ctypes.c_void_p;x.XCloseDisplay.argtypes=[ctypes.c_void_p]
d=x.XOpenDisplay(os.environ["DISPLAY"].encode());assert d;x.XCloseDisplay(d)
Atspi.init();root=Atspi.get_desktop(0);assert root is not None
print(json.dumps({"actual_display_opened":True,"atspi_bus_available":True,"editable_text_api":hasattr(Atspi.EditableText,"set_text_contents"),"existing_app_content_read":False}))
'''
    public_env = {'PATH':'/usr/bin:/bin', **environment}
    p = subprocess.run(['/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups','/usr/bin/python3.12','-B','-c',probe],env=public_env,capture_output=True,text=True,timeout=12)
    receipt['graphical_probe']={'exit_code':p.returncode,'stdout':p.stdout[:4096],'stderr':p.stderr[:4096]}
    assert p.returncode == 0
    private.mkdir(mode=0o700)
    mount_probe = '''import json,os,subprocess,sys,tempfile
from pathlib import Path
base=Path(tempfile.mkdtemp(prefix="mount-check-",dir=sys.argv[1]));a=base/"source";b=base/"target";a.mkdir();b.mkdir();mounted=False
try:
 subprocess.run(["/usr/bin/mount","--bind",str(a),str(b)],check=True,timeout=5);mounted=True
 assert os.stat(a).st_ino==os.stat(b).st_ino
 subprocess.run(["/usr/bin/umount",str(b)],check=True,timeout=5);mounted=False
 print(json.dumps({"private_bind_mount":True,"ordinary_unmount":True}))
finally:
 if not mounted:b.rmdir();a.rmdir();base.rmdir()
'''
    p = subprocess.run(['/usr/bin/unshare','--mount','--propagation','private','/usr/bin/python3.12','-B','-c',mount_probe,str(private)],capture_output=True,text=True,timeout=15)
    receipt['private_mount_probe']={'exit_code':p.returncode,'stdout':p.stdout[:4096],'stderr':p.stderr[:4096]}
    assert p.returncode == 0
    preferences={'schema':'trill.original-notes-preferences.v1','locale':'zh-CN','model':'qwen38-flash-next-uc','model_provider':'hepta_local'}
    prompts={'schema':'trill.original-notes-prompts.v1','developer_instructions':'Use only the original Notes tools. For a requested replacement, read hepta_notes_state first, make at most one hepta_notes_replace call using that revision, then read hepta_notes_status and hepta_notes_state. Preserve returned operation identity. An unknown or lost effect reply permits only read-only reconciliation, never another replace call. Do not claim success without both the original writer result and independent current document readback. Respond in Chinese.'}
    assert len(prompts['developer_instructions'].encode())<=512
    config={'schema':'trill.original-desktop-root.initialize.v1','prefix':str(prefix),'uid':1000,'gid':1000,'programs':programs,
            'sources':{'runtime_body':programs['agentd'],'preferences':str(private/'preferences.json'),'prompt_registry':str(private/'prompts.json'),
                       'sdk':str(release/'desktop/resources/NATIVE-SDK-SOURCE.json'),'source_freeze':str(release/'desktop/source-profile.json')},
            'makepad_resources':str(release/'desktop/resources'),'environment':environment,'locale':'zh-CN','lifetime_ms':300000,'grant_lifetime_ms':30000}
    receipt['inputs']={}
    for name,value in [('preferences.json',preferences),('prompts.json',prompts),('initialize.json',config)]:
        raw=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode();path=private/name
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        receipt['inputs'][name]={'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    directory=os.open(private,os.O_RDONLY|os.O_DIRECTORY);os.fsync(directory);os.close(directory)
    receipt['status']='prepared'
except Exception as e:
    receipt['status']='blocked';receipt['error']=repr(e)
finally:
    receipt['finished_unix_ms']=int(time.time()*1000)
    raw=(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n').encode()
    fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.chmod(output,0o644)
    print(json.dumps({'path':str(output),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'receipt':receipt},ensure_ascii=False))
if receipt['status']!='prepared':sys.exit(1)
