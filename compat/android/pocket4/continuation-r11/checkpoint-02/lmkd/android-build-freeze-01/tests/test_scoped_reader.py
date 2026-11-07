#!/usr/bin/env python3
# Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
"""Exercise actual new fixed-root Reader methods with explicit descriptor I/O substitutes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--source-dir', type=Path, required=True)
p.add_argument('--reader-fixture', type=Path, required=True)
p.add_argument('--out-dir', type=Path, required=True)
a = p.parse_args()
a.out_dir.mkdir(parents=True, exist_ok=False)
fixture = a.reader_fixture.read_text().split('int main() {', 1)[0]
old = '''extern "C" int __wrap_fstatfs(int fd,struct statfs* out) {
    if(fd!=100){errno=EBADF;return -1;}*out={};out->f_type=CGROUP2_SUPER_MAGIC;return 0;
}'''
assert old in fixture
fixture = fixture.replace(old, '''static bool bad_filesystem;
extern "C" int __wrap_fstatfs(int fd,struct statfs* out) {
    if(fd!=100&&fd!=301){errno=EBADF;return -1;}
    *out={};out->f_type=bad_filesystem?0:CGROUP2_SUPER_MAGIC;return 0;
}''')
fixture += r'''
#include <cstdarg>
#include <fcntl.h>
#include <linux/openat2.h>
#include <sys/stat.h>
#include <sys/syscall.h>
static bool identity_drift, fail_stat;
static int root_reads, opens, open_error;
extern "C" int __wrap_fstat(int fd, struct stat* st) {
    if(fail_stat){errno=EIO;return -1;}
    *st={};st->st_dev=13;
    if(fd==100){st->st_mode=S_IFDIR|0755;st->st_ino=identity_drift&&++root_reads==2?18:17;return 0;}
    st->st_mode=S_IFREG|0600;
    if(fd==301||fd==501){st->st_ino=31;return 0;}
    if(fd==502){st->st_ino=32;return 0;}
    errno=EBADF;return -1;
}
extern "C" long __wrap_syscall(long number, ...) {
    require(number==SYS_openat2,"only openat2 is used for bound target traversal");
    va_list arguments;va_start(arguments,number);
    int root=va_arg(arguments,int);
    const char* relative=va_arg(arguments,const char*);
    const open_how* how=va_arg(arguments,const open_how*);
    size_t length=va_arg(arguments,size_t);va_end(arguments);
    ++opens;
    require(root==100&&!std::strcmp(relative,"uid_10001/pid_123/cgroup.kill"),"target path uses exact uid and pid under pinned root fd");
    require(length==sizeof(open_how)&&how->flags==(O_PATH|O_CLOEXEC)&&
            how->resolve==(RESOLVE_BENEATH|RESOLVE_NO_SYMLINKS|RESOLVE_NO_XDEV),
            "openat2 forbids symlink traversal and mount escape without path fallback");
    if(open_error){errno=open_error;return -1;}
    return 301;
}
int main() {
    reset();Reader reader;Snapshot snapshot{};ScopeIdentity identity{};
    require(!reader.ReadScoped(&snapshot,&identity),"unopened Reader cannot publish scope");
    require(reader.Open("/owned-cell")&&reader.ReadScoped(&snapshot,&identity,1000)&&identity.device==13&&identity.inode==17,
            "scope identity and coherent accounting come from same retained Reader root");
    events(51);root_reads=0;identity_drift=true;
    snapshot.max=42;identity={99,98};
    require(!reader.ReadScoped(&snapshot,&identity,1000)&&snapshot.max==42&&identity.device==99&&identity.inode==98,
            "identity race publishes neither snapshot nor scope");
    require(!reader.ConsumeHighEvidence(1000),"identity failure retires pending high evidence");
    identity_drift=false;fail_stat=true;
    require(!reader.ReadScoped(&snapshot,&identity)&&snapshot.max==42&&identity.inode==98,
            "failed root stat preserves outputs and refuses authority");
    fail_stat=false;
    require(reader.IsProcessKillFd(501,10001,123),"matching exact per-process cgroup.kill inode is accepted");
    require(!reader.IsProcessKillFd(502,10001,123),"root or sibling cgroup.kill inode cannot match process subtree");
    bad_filesystem=true;
    require(!reader.IsProcessKillFd(501,10001,123),"non-cgroup2 target file cannot authorize group effect");
    bad_filesystem=false;
    for(int error:{EXDEV,ELOOP,ENOENT,ENOSYS}) {
        open_error=error;int before=opens;
        require(!reader.IsProcessKillFd(501,10001,123)&&opens==before+1,
                "mount symlink absent path or missing openat2 support fails without fallback");
    }
    int before=opens;
    require(!reader.IsProcessKillFd(501,10001,0)&&!reader.IsProcessKillFd(-1,10001,123)&&opens==before,
            "invalid target cannot construct a broad group lookup");
    std::printf("RESULT %d actual Reader scoped assertions passed; descriptor/syscall I/O replaced\n",checks);
    return 0;
}
'''
cpp, exe = a.out_dir/'scoped_reader.cpp', a.out_dir/'scoped_reader'
cpp.write_text(fixture)
command = ['g++', '-std=c++17', '-O2', '-g0', '-Wall', '-Wextra', '-Werror', '-I', str(a.source_dir),
           str(a.source_dir/'memory_cgroup.cpp'), str(cpp),
           '-Wl,--wrap=open,--wrap=openat,--wrap=fstatfs,--wrap=pread,--wrap=close,--wrap=fstat,--wrap=syscall',
           '-o', str(exe)]
built = subprocess.run(command, capture_output=True, text=True, timeout=30)
run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10) if built.returncode == 0 else None
report = {'scope': 'actual Reader methods with explicit descriptor/syscall substitutes; no live cgroup or pressure',
          'command': command, 'compile_rc': built.returncode, 'compile_stderr': built.stderr,
          'run_rc': None if run is None else run.returncode, 'stdout': None if run is None else run.stdout,
          'stderr': None if run is None else run.stderr,
          'source_sha256': {n: hashlib.sha256((a.source_dir/n).read_bytes()).hexdigest() for n in ['memory_cgroup.cpp','memory_cgroup.h']},
          'fixture_sha256': hashlib.sha256(a.reader_fixture.read_bytes()).hexdigest(),
          'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(a.out_dir/'result.json').write_text(json.dumps(report, indent=2)+'\n')
assert built.returncode == 0, built.stderr
assert run.returncode == 0, run.stderr
print(run.stdout)
