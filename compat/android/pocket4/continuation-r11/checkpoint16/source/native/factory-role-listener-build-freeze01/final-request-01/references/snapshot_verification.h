// Exact existing snapshot oracle function; source range pinned in HELPER_BINDING.json.
provenance::Origin VerifySnapshot(int descriptor, uint32_t expected_pid, int expected_status) {
  struct stat metadata{};
  provenance::KernelStatfs fs{};
  Require(fstat(descriptor, &metadata) == 0 &&
          syscall(SYS_fstatfs, static_cast<long>(descriptor), &fs) == 0,
          "actual snapshot inode and raw filesystem");
  Require(metadata.st_mode == (S_IFREG | 0444) && metadata.st_uid == 0 && metadata.st_gid == 0 &&
          metadata.st_nlink == 0 && metadata.st_size == sizeof(kPayload) - 1 &&
          fs.f_type == TMPFS_MAGIC, "snapshot is a real root-owned anonymous readonly inode");
  const int seals = fcntl(descriptor, F_GET_SEALS), flags = fcntl(descriptor, F_GETFD);
  Require(seals >= 0 && (static_cast<uint32_t>(seals) & provenance::kRequiredSeals) == provenance::kRequiredSeals &&
          flags == FD_CLOEXEC && lseek(descriptor, 0, SEEK_CUR) == 0,
          "snapshot sealed CLOEXEC and initial offset");
  Require(fcntl(descriptor, F_GETFL) == expected_status,
          "receiver observes exact kernel file-status flags");
  char descriptor_path[80];
  const int descriptor_path_size = snprintf(descriptor_path, sizeof(descriptor_path),
                                            "/proc/thread-self/fd/%d", descriptor);
  Require(descriptor_path_size > 0 && static_cast<size_t>(descriptor_path_size) < sizeof(descriptor_path),
          "owned output descriptor path fits");
  char kernel_path[sizeof(provenance::kSnapshotKernelPath)];
  const ssize_t kernel_path_size = readlink(descriptor_path, kernel_path, sizeof(kernel_path));
  Require(kernel_path_size == sizeof(provenance::kSnapshotKernelPath) - 1 &&
          !memcmp(kernel_path, provenance::kSnapshotKernelPath, sizeof(provenance::kSnapshotKernelPath) - 1),
          "reopened snapshot retains exact V2 kernel-path contract");
  char content[sizeof(kPayload)]{};
  Require(pread(descriptor, content, sizeof(content), 0) == sizeof(kPayload) - 1 &&
          memcmp(content, kPayload, sizeof(kPayload) - 1) == 0,
          "snapshot fixed payload bytes and EOF");
  unsigned char tag[provenance::kMaxTagBytes];
  const ssize_t count = fgetxattr(descriptor, provenance::kTagName, tag, sizeof(tag));
  provenance::Origin origin{};
  Require(count > 0 && provenance::DecodeOrigin(tag, static_cast<size_t>(count), &origin),
          "complete ordinary V2 origin tag decodes");
  Require(origin.words[provenance::kFactoryUsernsDevice] == provenance::kTrustedUserNamespaceDevice &&
          origin.words[provenance::kFactoryUsernsInode] == provenance::kTrustedUserNamespaceInode &&
          origin.words[provenance::kBackingDevice] == metadata.st_dev &&
          origin.words[provenance::kBackingInode] == metadata.st_ino &&
          origin.words[provenance::kBackingSize] == sizeof(kPayload) - 1 &&
          origin.words[provenance::kOriginTgid] == expected_pid &&
          origin.words[provenance::kOriginStartTicks] > 0,
          "tag binds actual backing inode and approved subject");
  char path[80]; const int length = snprintf(path, sizeof(path), "/proc/%u/maps", expected_pid);
  Require(length > 0 && static_cast<size_t>(length) < sizeof(path) &&
          origin.path_size == static_cast<size_t>(length) && !memcmp(path, origin.path, origin.path_size),
          "tag canonical tgid maps path");
  return origin;
}

