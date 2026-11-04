/* Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0 */
// Exercises the real Reader with descriptor I/O replacements. No host cgroup
// is opened, modified, or interpreted as test data by this binary.
#include "memory_cgroup.h"
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
#include <sys/vfs.h>
#include <linux/magic.h>
#include <unistd.h>

using namespace droidloom::lmkd;
static std::map<std::string,std::string> files;
static std::map<int,std::string> descriptors;
static std::string failed_file;
static bool race_high;
static int high_reads, checks;
extern "C" int __wrap_open(const char* path,int,...) {
    if (!std::strcmp(path,"/owned-cell")) return 100;
    if (!std::strcmp(path,"/proc/meminfo")) {descriptors[199]="host";return 199;}
    errno=ENOENT;return -1;
}
extern "C" int __wrap_openat(int fd,const char* path,int,...) {
    if(fd!=100||!files.count(path)){errno=ENOENT;return -1;}
    int result=200+static_cast<int>(descriptors.size());descriptors[result]=path;return result;
}
extern "C" int __wrap_fstatfs(int fd,struct statfs* out) {
    if(fd!=100){errno=EBADF;return -1;}*out={};out->f_type=CGROUP2_SUPER_MAGIC;return 0;
}
extern "C" int __wrap_close(int) {return 0;}
extern "C" ssize_t __wrap_pread(int fd,void* buffer,size_t size,off_t offset) {
    if(!descriptors.count(fd)||offset){errno=EBADF;return -1;}
    const auto& name=descriptors[fd];
    if(name==failed_file){errno=EIO;return -1;}
    auto value=files.at(name);
    if(name=="memory.high"&&race_high&&++high_reads==2)value="419434496\n";
    if(value.size()>size){errno=EOVERFLOW;return -1;}
    std::memcpy(buffer,value.data(),value.size());return static_cast<ssize_t>(value.size());
}
static void require(bool value,const char* name) {
    if(!value){std::fprintf(stderr,"FAIL %s\n",name);std::exit(2);}
    ++checks;std::printf("PASS %s\n",name);
}
static void reset() {
    descriptors.clear();failed_file.clear();race_high=false;high_reads=0;
    files={{"memory.current","442388480\n"},{"memory.max","536870912\n"},
      {"memory.high","402653184\n"},{"memory.swap.current","0\n"},{"memory.swap.max","0\n"},
      {"memory.events","low 0\nhigh 50\nmax 0\noom 0\noom_kill 0\n"},
      {"host","MemTotal: 26214400 kB\nMemFree: 10485760 kB\nSwapTotal: 16777216 kB\nSwapFree: 5242880 kB\n"},
      {"memory.stat","anon 440401920\nfile 0\nshmem 0\nswapcached 0\nactive_anon 440401920\ninactive_anon 0\nactive_file 0\ninactive_file 0\nunevictable 0\nslab_reclaimable 0\nslab_unreclaimable 0\nkernel_stack 0\npagetables 0\nfile_dirty 0\nworkingset_refault_file 0\npgscan_kswapd 0\npgscan_direct 0\npgrefill 0\n"}};
}
static void events(unsigned count) {files["memory.events"]="low 0\nhigh "+std::to_string(count)+"\nmax 0\noom 0\noom_kill 0\n";}
int main() {
    reset();
    {
        Reader r;Snapshot s{};
        require(r.Open("/owned-cell"),"reader pins event descriptor in owned cgroup");
        require(r.Read(&s)&&s.high_events==50&&!s.high_throttling_progressed,"first cumulative count is only baseline");
        events(51);
        require(r.Read(&s)&&s.high_throttling_progressed&&s.stat.pgscan_direct==0,"real throttle progresses without any page scans");
        require(r.Read(&s)&&!s.high_throttling_progressed,"same cumulative event is consumed once");
        files["memory.current"]=files["memory.high"];events(52);
        require(r.Read(&s)&&!s.high_throttling_progressed,"event increment cannot act after usage reaches high");
        files["memory.current"]="442388480\n";files["memory.high"]="419430400\n";events(53);
        require(r.Read(&s)&&!s.high_throttling_progressed,"changed boundary restarts interval");
        events(54);
        require(r.Read(&s)&&s.high_throttling_progressed,"new event after stable changed boundary is valid");
        failed_file="memory.events";
        require(!r.Read(&s)&&r.error()==EIO&&s.high_events==54,"event I/O failure publishes no partial snapshot");
        failed_file.clear();events(55);
        require(r.Read(&s)&&!s.high_throttling_progressed,"successful read after failure cannot reuse old interval");
        events(56);
        require(r.Read(&s)&&s.high_throttling_progressed,"subsequent coherent increment restores evidence");
        race_high=true;high_reads=0;events(57);
        require(!r.Read(&s)&&r.error()==EAGAIN&&s.high_events==56,"budget race rejects whole sample");
        race_high=false;events(58);
        require(r.Read(&s)&&!s.high_throttling_progressed,"budget race also invalidates event interval");
        events(59);
        require(r.Read(&s)&&s.high_throttling_progressed,"new stable interval after race works");
        files["memory.events"]="low 0\nmax 0\n";
        require(!r.Read(&s)&&s.high_events==59,"missing high refuses snapshot");
        events(60);
        require(r.Read(&s)&&!s.high_throttling_progressed,"malformed input cannot leave pending high evidence");
        files["memory.high"]="max\n";events(61);
        require(r.Read(&s)&&s.high_unlimited&&!s.high_throttling_progressed,"unlimited high has no throttle evidence");
    }
    reset();
    {
        Reader r;Snapshot s{};require(r.Open("/owned-cell")&&r.Read(&s),"new reader baseline");
        failed_file="memory.events";require(!r.Read(&s),"injected failed sample");
        failed_file.clear();events(49);
        require(!r.Read(&s)&&r.error()==EUCLEAN,"read failure does not erase counter rollback protection");
        events(51);
        require(!r.Read(&s)&&r.error()==EUCLEAN,"counter rollback permanently fails reader closed");
    }
    std::printf("RESULT %d passed\n",checks);
}
