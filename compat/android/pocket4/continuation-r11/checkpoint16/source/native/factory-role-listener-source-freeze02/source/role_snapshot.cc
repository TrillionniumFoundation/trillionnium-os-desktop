// SPDX-License-Identifier: Apache-2.0
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "role_snapshot.h"
#include "berberis/kernel_api/proc_maps_factory_protocol.h"
#include "berberis/kernel_api/proc_maps_linux_compat.h"
#include "berberis/kernel_api/proc_maps_snapshot_reopen.h"

#include <errno.h>
#include <fcntl.h>
#include <linux/magic.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <sys/xattr.h>
#include <time.h>
#include <unistd.h>

namespace droidloom::proc_maps_factory::role_v1 {
namespace {
namespace p = berberis::proc_maps_provenance;
using Fd = Descriptor;
constexpr uint64_t kCreationNanos = 2000000000ULL;
int Error(int value) { errno = value; return -1; }
bool SameInode(const struct stat& a, const struct stat& b) {
  return a.st_dev == b.st_dev && a.st_ino == b.st_ino;
}
uint64_t Now() {
  timespec value{};
  if (clock_gettime(CLOCK_MONOTONIC, &value) < 0 || value.tv_sec < 0 ||
      value.tv_nsec < 0 || value.tv_nsec >= 1000000000 ||
      static_cast<uint64_t>(value.tv_sec) > (UINT64_MAX - 999999999) / 1000000000) return 0;
  return static_cast<uint64_t>(value.tv_sec) * 1000000000 + value.tv_nsec;
}
int Path(char* path, size_t size, const char* leaf, uint32_t pid) {
  const int count = snprintf(path, size, "%u/%s", pid, leaf);
  return count > 0 && static_cast<size_t>(count) < size ? 0 : Error(EOVERFLOW);
}

// This complete field mapping is byte-identical to the existing V2 factory.
// In particular the statfs words preserve the raw kernel ABI and ST_VALID.
void StoreMetadata(const struct stat& source,const p::KernelStatfs& fs,p::Origin* origin) {
  auto* w=origin->words;
  w[p::kStatDevice]=source.st_dev;w[p::kStatInode]=source.st_ino;
  w[p::kStatMode]=source.st_mode;w[p::kStatNlink]=source.st_nlink;
  w[p::kStatUid]=source.st_uid;w[p::kStatGid]=source.st_gid;w[p::kStatRdev]=source.st_rdev;
  w[p::kStatSize]=static_cast<uint64_t>(source.st_size);
  w[p::kStatBlockSize]=static_cast<uint64_t>(source.st_blksize);
  w[p::kStatBlocks]=static_cast<uint64_t>(source.st_blocks);
  w[p::kStatAtimeSeconds]=static_cast<uint64_t>(source.st_atim.tv_sec);
  w[p::kStatAtimeNanoseconds]=static_cast<uint64_t>(source.st_atim.tv_nsec);
  w[p::kStatMtimeSeconds]=static_cast<uint64_t>(source.st_mtim.tv_sec);
  w[p::kStatMtimeNanoseconds]=static_cast<uint64_t>(source.st_mtim.tv_nsec);
  w[p::kStatCtimeSeconds]=static_cast<uint64_t>(source.st_ctim.tv_sec);
  w[p::kStatCtimeNanoseconds]=static_cast<uint64_t>(source.st_ctim.tv_nsec);
  w[p::kFsType]=fs.f_type;w[p::kFsBlockSize]=fs.f_bsize;
  w[p::kFsBlocks]=fs.f_blocks;w[p::kFsBlocksFree]=fs.f_bfree;
  w[p::kFsBlocksAvailable]=fs.f_bavail;w[p::kFsFiles]=fs.f_files;w[p::kFsFilesFree]=fs.f_ffree;
  w[p::kFsId0]=fs.f_fsid[0];w[p::kFsId1]=fs.f_fsid[1];
  w[p::kFsNameLength]=fs.f_namelen;w[p::kFsFragmentSize]=fs.f_frsize;w[p::kFsFlags]=fs.f_flags;
  for(unsigned i=0;i<4;++i)w[p::kFsSpare0+i]=fs.f_spare[i];
}
int MakeSnapshot(Registry& registry, GrantHandle handle, const SnapshotAuthority& authority,
                 const Request& request, int source_fd, int input_fd, uint64_t deadline) {
  struct stat source{},canonical{},input{};
  p::KernelStatfs source_fs{},input_fs{};
  if(fstat(source_fd,&source)<0||syscall(SYS_fstatfs,static_cast<long>(source_fd),&source_fs)<0||
     fstat(input_fd,&input)<0||syscall(SYS_fstatfs,static_cast<long>(input_fd),&input_fs)<0)return -1;
  const int source_flags=fcntl(source_fd,F_GETFL),input_flags=fcntl(input_fd,F_GETFL);
  if(source_flags<0||input_flags<0)return -1;
  if(static_cast<uint32_t>(source_flags)!=request.source_flags||
     (source_flags&(O_ACCMODE|O_PATH))!=O_RDONLY||source.st_mode!=(S_IFREG|0444)||
     source_fs.f_type!=PROC_SUPER_MAGIC)return Error(EINVAL);
  char path[80];
  if(Path(path,sizeof(path),"maps",authority.visible_tgid)<0)return -1;
  Fd canonical_fd(openat(authority.proc_fd,path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW));
  if(canonical_fd.get()<0||fstat(canonical_fd.get(),&canonical)<0)return -1;
  if(!SameInode(source,canonical)||source.st_mode!=canonical.st_mode||
     source.st_uid!=canonical.st_uid||source.st_gid!=canonical.st_gid)return Error(ESTALE);
  const int seals=fcntl(input_fd,F_GET_SEALS);
  if(seals<0)return -1;
  if(!S_ISREG(input.st_mode)||input_fs.f_type!=TMPFS_MAGIC||input.st_nlink!=0||
     input.st_uid!=authority.uid||input.st_gid!=authority.gid||
     input.st_size<=0||static_cast<uint64_t>(input.st_size)!=request.payload_size||
     (input_flags&O_PATH)||(input_flags&O_ACCMODE)==O_WRONLY||
     (seals&p::kRequiredSeals)!=p::kRequiredSeals)return Error(EINVAL);
  Fd output(static_cast<int>(syscall(SYS_memfd_create,p::kSnapshotName,
                                    static_cast<unsigned long>(MFD_CLOEXEC|MFD_ALLOW_SEALING))));
  if(output.get()<0)return -1;
  char buffer[65536];uint64_t offset=0;
  while(offset<request.payload_size) {
    const uint64_t now=Now();
    if(now==0||now>=deadline)return Error(ETIMEDOUT);
    if(registry.IsActive(handle)<0)return -1;
    size_t wanted=sizeof(buffer);
    if(request.payload_size-offset<wanted)wanted=static_cast<size_t>(request.payload_size-offset);
    const ssize_t count=pread(input_fd,buffer,wanted,static_cast<off_t>(offset));
    if(count<0){if(errno==EINTR)continue;return -1;}
    if(count==0)return Error(EIO);
    size_t written=0;
    while(written<static_cast<size_t>(count)) {
      const ssize_t amount=write(output.get(),buffer+written,static_cast<size_t>(count)-written);
      if(amount<0){if(errno==EINTR)continue;return -1;}
      if(amount==0)return Error(EIO);
      written+=static_cast<size_t>(amount);
    }
    offset+=static_cast<uint64_t>(count);
  }
  struct stat backing{};struct statfs backing_fs{};
  if(fstat(output.get(),&backing)<0||fstatfs(output.get(),&backing_fs)<0)return -1;
  if(backing.st_uid||backing.st_gid||backing.st_nlink||
     static_cast<uint64_t>(backing.st_size)!=request.payload_size||
     static_cast<uint64_t>(backing_fs.f_type)!=TMPFS_MAGIC)return Error(EPROTO);
  p::Origin origin{};
  origin.words[p::kFactoryUsernsDevice]=p::kTrustedUserNamespaceDevice;
  origin.words[p::kFactoryUsernsInode]=p::kTrustedUserNamespaceInode;
  origin.words[p::kBackingDevice]=backing.st_dev;origin.words[p::kBackingInode]=backing.st_ino;
  origin.words[p::kBackingSize]=request.payload_size;
  origin.words[p::kOriginTgid]=authority.visible_tgid;origin.words[p::kOriginStartTicks]=authority.start_ticks;
  StoreMetadata(source,source_fs,&origin);
  const int path_size=snprintf(origin.path,sizeof(origin.path),"/proc/%u/maps",authority.visible_tgid);
  if(path_size<=0||static_cast<size_t>(path_size)>=sizeof(origin.path))return Error(EOVERFLOW);
  origin.path_size=static_cast<size_t>(path_size);
  unsigned char tag[p::kMaxTagBytes];
  const size_t tag_size=p::EncodeOrigin(origin,tag,sizeof(tag));
  if(!tag_size)return Error(EBADMSG);
  if(fsetxattr(output.get(),p::kTagName,tag,tag_size,XATTR_CREATE)<0||
     fchmod(output.get(),0444)<0||fcntl(output.get(),F_ADD_SEALS,p::kRequiredSeals)<0)return -1;
  Fd readable;
  if (source_flags & O_NOFOLLOW) {
    readable.reset(ReopenOwnSnapshotByHandle(output.get(), source_flags));
  } else {
    // This is the factory's own held fdtable. Reopen through thread-self and
    // verify the resulting object, not /proc/self/fd of a different owner.
    Fd directory(open("/proc/thread-self/fd",O_PATH|O_DIRECTORY|O_CLOEXEC));
    struct statfs directory_fs{};
    if(directory.get()<0||fstatfs(directory.get(),&directory_fs)<0)return -1;
    if(static_cast<uint64_t>(directory_fs.f_type)!=PROC_SUPER_MAGIC)return Error(EXDEV);
    char number[32];const int n=snprintf(number,sizeof(number),"%d",output.get());
    if(n<=0||static_cast<size_t>(n)>=sizeof(number))return Error(EOVERFLOW);
    readable.reset(openat(directory.get(),number,source_flags|O_CLOEXEC));
  }
  struct stat final_info{};
  if(readable.get()<0||fstat(readable.get(),&final_info)<0)return -1;
  const int final_seals=fcntl(readable.get(),F_GET_SEALS);
  const int final_status=fcntl(readable.get(),F_GETFL);
  const int final_fd_flags=fcntl(readable.get(),F_GETFD);
  const off_t final_offset=lseek(readable.get(),0,SEEK_CUR);
  if(final_seals<0||final_status<0||final_fd_flags<0||final_offset<0)return -1;
  if(!SameInode(backing,final_info)||final_info.st_mode!=(S_IFREG|0444)||final_info.st_uid||final_info.st_gid||
     final_info.st_nlink||final_info.st_size!=backing.st_size||
     (final_seals&p::kRequiredSeals)!=p::kRequiredSeals||
     final_status!=source_flags||final_fd_flags!=FD_CLOEXEC||final_offset!=0)return Error(EPROTO);
  unsigned char observed[p::kMaxTagBytes];
  const ssize_t tag_read=fgetxattr(readable.get(),p::kTagName,observed,sizeof(observed));
  if(tag_read<0)return -1;
  if(static_cast<size_t>(tag_read)!=tag_size||memcmp(observed,tag,tag_size))return Error(ESTALE);
  if(registry.IsActive(handle)<0)return -1;
  return readable.release();
}
int CreateBefore(Registry& registry, GrantHandle handle, const Received& message,
                 uint64_t deadline) {
  SnapshotAuthority authority{};
  if (registry.AuthorizeCreate(handle, message, &authority) < 0) {
    const int authorization_error = errno;
    if (deadline) registry.Close(handle);
    errno = authorization_error;
    return -1;
  }
  const uint64_t now = Now();
  int output = -1;
  if (!now || now > UINT64_MAX - kCreationNanos) {
    Error(EIO);
  } else if (deadline && deadline <= now) {
    Error(ETIMEDOUT);
  } else if (deadline && deadline > now + kCreationNanos) {
    Error(EINVAL);
  } else {
    output = MakeSnapshot(registry, handle, authority, message.request(),
                          message.source_fd(), message.payload_fd(),
                          deadline ? deadline : now + kCreationNanos);
    if (output >= 0 && deadline) {
      const uint64_t after = Now();
      if (!after || after < now || after >= deadline) {
        close(output);
        output = Error(after && after >= now ? ETIMEDOUT : EIO);
      }
    }
  }
  const int creation_error = errno;
  // Complete on both paths. An invalid/dead caller must never receive the
  // newly created root inode, even if all file operations already succeeded.
  if (registry.FinishCreate(handle) < 0) {
    const int finish_error = errno;
    if (output >= 0) close(output);
    // A poisoned owner can fail FinishCreate before it reaches the slot.
    // Close still permits this same owner to revoke; foreign callers cannot.
    registry.Close(handle);
    errno = output < 0 ? creation_error : finish_error;
    return -1;
  }
  if (output < 0) errno = creation_error;
  return output;
}
}  // namespace

int CreateAuthorizedSnapshot(Registry& registry, GrantHandle handle,
                             const Received& message) {
  return CreateBefore(registry, handle, message, 0);
}

int CreateAuthorizedSnapshotBefore(Registry& registry, GrantHandle handle,
                                   const Received& message, uint64_t deadline) {
  if (!deadline) return Error(EINVAL);
  return CreateBefore(registry, handle, message, deadline);
}

}  // namespace droidloom::proc_maps_factory::role_v1
