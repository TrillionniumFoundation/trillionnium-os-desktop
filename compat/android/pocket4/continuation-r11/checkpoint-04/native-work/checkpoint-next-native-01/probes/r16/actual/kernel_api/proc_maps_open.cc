/* Copyright 2026. SPDX-License-Identifier: Apache-2.0 */
#include "berberis/kernel_api/proc_maps_open.h"
#include "berberis/kernel_api/proc_maps_fd_owner.h"
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

namespace berberis::proc_maps_provenance {
namespace {
constexpr const char* kSelfMaps = "/proc/self/maps";
int Error(int error) { errno = error; return -1; }
class Fd {
 public:
  explicit Fd(int value) : value_(value) {}
  ~Fd() { const int saved=errno; if(value_>=0)syscall(SYS_close,value_);errno=saved; }
  Fd(const Fd&)=delete;
  Fd& operator=(const Fd&)=delete;
  int get() const {return value_;}
  int release(){const int result=value_;value_=-1;return result;}
 private:
  int value_;
};
bool SameInode(const struct stat& a,const struct stat& b) {
  return a.st_dev==b.st_dev && a.st_ino==b.st_ino;
}
struct Request {
  int flags;
  mode_t mode;
  const struct stat* observed;
  SnapshotOperation snapshot;
  void* context;
  int publication_flags=0;
};
int Prepare(int,void* opaque) {
  auto* request=static_cast<Request*>(opaque);
  // Successful fstatat selected this process's actual maps object. Its inode
  // lifetime is the still-live current task, so a later alias rename cannot
  // change which object this positive operation opens. Canonical open applies
  // the caller's full flags before transformation (EXCL, DIRECTORY, etc.).
  Fd source(open(kSelfMaps,request->flags|O_CLOEXEC,request->mode));
  if(source.get()<0)return -1;
  struct stat actual{};
  if(fstat(source.get(),&actual)<0)return -1;
  if(!SameInode(actual,*request->observed))return Error(ESTALE);
  int prepared;
  if((request->flags&O_PATH)!=0 || (request->flags&O_ACCMODE)!=O_RDONLY) {
    prepared=source.release();
  } else {
    prepared=request->snapshot(source.get(),request->flags,request->context);
  }
  Fd output(prepared);
  if(output.get()<0)return -1;
  const int status=fcntl(output.get(),F_GETFL);
  if(status<0)return -1;
  request->publication_flags=(status & ~(O_CREAT|O_EXCL|O_NOCTTY|O_TRUNC|O_NOFOLLOW)) |
                              (request->flags&O_CLOEXEC);
  return output.release();
}
int Publish(const char* private_path,void* opaque) {
  auto* request=static_cast<Request*>(opaque);
  // This is the first and only allocation in the guest/caller table. Never
  // inspect, overwrite or close the resulting public slot after this syscall.
  return open(private_path,request->publication_flags);
}
}  // namespace

bool TryOpenSelfMaps(int dirfd,const char* path,int flags,mode_t mode,
                     SnapshotOperation snapshot,void* context,int* result) {
  const int incoming_errno=errno;
  struct stat requested{},canonical{};
  if(fstatat(dirfd,path,&requested,(flags&O_NOFOLLOW)?AT_SYMLINK_NOFOLLOW:0)<0){
    errno=incoming_errno;
    return false;
  }
  if(stat(kSelfMaps,&canonical)<0){*result=-1;return true;}
  if(!SameInode(requested,canonical)){errno=incoming_errno;return false;}
  if(snapshot==nullptr){*result=Error(EINVAL);return true;}
  Request request{flags,mode,&canonical,snapshot,context};
  *result=fd_owner::WithPreparedFile(Prepare,Publish,&request);
  if(*result>=0)errno=incoming_errno;
  return true;
}

}  // namespace berberis::proc_maps_provenance
