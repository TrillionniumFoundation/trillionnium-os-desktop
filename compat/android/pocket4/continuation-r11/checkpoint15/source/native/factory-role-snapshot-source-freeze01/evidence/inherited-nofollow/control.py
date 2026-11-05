import os,fcntl,json,errno
out={};fds=[]
try:
 src=os.open('/proc/self/maps',os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW);fds.append(src)
 flags=fcntl.fcntl(src,fcntl.F_GETFL);out={'source_flags':flags,'O_NOFOLLOW':os.O_NOFOLLOW,'nofollow_retained':bool(flags&os.O_NOFOLLOW)}
 fd=os.memfd_create('owned-role-reopen-control',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING);fds.append(fd)
 try:
  reopened=os.open('/proc/thread-self/fd/'+str(fd),flags|os.O_CLOEXEC);fds.append(reopened)
  out['reopen']={'returncode':0,'flags':fcntl.fcntl(reopened,fcntl.F_GETFL)}
 except OSError as error:out['reopen']={'returncode':-1,'errno':error.errno}
finally:
 for fd in reversed(fds):os.close(fd)
print(json.dumps(out))
