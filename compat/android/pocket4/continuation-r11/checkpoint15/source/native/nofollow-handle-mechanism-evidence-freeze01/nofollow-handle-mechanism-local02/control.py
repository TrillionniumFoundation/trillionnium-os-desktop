import ctypes,os,fcntl,json,platform
class Handle(ctypes.Structure):
    _fields_=[('handle_bytes',ctypes.c_uint),('handle_type',ctypes.c_int),('f_handle',ctypes.c_ubyte*128)]
libc=ctypes.CDLL(None,use_errno=True)
libc.name_to_handle_at.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.POINTER(Handle),ctypes.POINTER(ctypes.c_int),ctypes.c_int]
libc.name_to_handle_at.restype=ctypes.c_int
libc.open_by_handle_at.argtypes=[ctypes.c_int,ctypes.POINTER(Handle),ctypes.c_int]
libc.open_by_handle_at.restype=ctypes.c_int
fd=os.memfd_create('owned-nofollow-handle-mechanism',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
opened=-1
try:
    os.write(fd,b'owned mechanism only\n');os.fchmod(fd,0o444);fcntl.fcntl(fd,1033,15)
    h=Handle();h.handle_bytes=128;mount=ctypes.c_int()
    ctypes.set_errno(0);rc=libc.name_to_handle_at(fd,b'',ctypes.byref(h),ctypes.byref(mount),0x1000);en=ctypes.get_errno()
    r={'scope':'local own memfd only; no factory entry or namespace/policy operation','uname':platform.release(),'uid':os.getuid(),'name_to_handle':{'returncode':rc,'errno':en,'handle_bytes':h.handle_bytes,'handle_type':h.handle_type,'mount_id':mount.value},'Main_actions':0}
    status={}
    for line in open('/proc/self/status'):
        if line.startswith(('CapEff:','Seccomp:','NoNewPrivs:')):
            k,v=line.strip().split(':',1);status[k]=v.strip()
    r['self_status']=status
    if rc==0:
        ctypes.set_errno(0);opened=libc.open_by_handle_at(fd,ctypes.byref(h),os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW);en=ctypes.get_errno()
        r['open_by_handle']={'returncode':opened if opened<0 else 0,'errno':en}
        if opened>=0:
            a=os.fstat(fd);b=os.fstat(opened)
            r['open_by_handle'].update({'same_inode':(a.st_dev,a.st_ino)==(b.st_dev,b.st_ino),'status_flags':fcntl.fcntl(opened,fcntl.F_GETFL),'nofollow_present':bool(fcntl.fcntl(opened,fcntl.F_GETFL)&os.O_NOFOLLOW),'fd_flags':fcntl.fcntl(opened,fcntl.F_GETFD),'seals':fcntl.fcntl(opened,1034),'offset':os.lseek(opened,0,os.SEEK_CUR),'payload_ok':os.pread(opened,100,0)==b'owned mechanism only\n'})
    print(json.dumps(r,sort_keys=True))
finally:
    if opened>=0:os.close(opened)
    os.close(fd)
