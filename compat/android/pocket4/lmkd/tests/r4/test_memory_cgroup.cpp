/* Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0 */
#include "memory_cgroup.h"
#include <cassert>
#include <cerrno>
#include <climits>
#include <cstdio>
#include <string>
#include <unistd.h>

using namespace droidloom::lmkd;
constexpr uint64_t GiB = 1024ULL*1024*1024;
static int count;
static void check(bool condition, const char* name) {
    if (!condition) { std::fprintf(stderr, "FAIL %s\n", name); std::abort(); }
    ++count;
    std::printf("PASS %s\n", name);
}
static Snapshot sample() {
    Snapshot s{};
    s.max=6*GiB; s.high=5*GiB; s.current=2*GiB;
    s.swap_unlimited=true; s.swap_current=4*GiB;
    s.host={25*GiB, 10*GiB, 16*GiB, 5*GiB};
    s.stat.file=GiB; s.stat.shmem=GiB/4;
    s.stat.inactive_file=GiB/2;
    return s;
}
int main() {
    uint64_t n=123; bool unlimited=false;
    check(ParseNumber(" 6442450944\n",&n)&&n==6*GiB,"bytes preserve 64-bit precision");
    check(!ParseNumber("-1",&n)&&!ParseNumber("+1",&n),"signed values rejected");
    check(!ParseNumber("7 8",&n)&&!ParseNumber("9junk",&n),"trailing data rejected");
    check(!ParseNumber("18446744073709551615",&n),"signed arithmetic overflow rejected");
    check(ParseLimit("max\n",&n,&unlimited)&&unlimited&&n==0,"unlimited explicit");
    check(!ParseLimit("maximum",&n,&unlimited),"unknown limit rejected");
    std::string stat=
      "anon 10\nfile 20\nshmem 3\nswapcached 4\nactive_anon 1\ninactive_anon 2\n"
      "active_file 5\ninactive_file 6\nunevictable 0\nslab_reclaimable 7\n"
      "slab_unreclaimable 8\nkernel_stack 9\npagetables 10\nfile_dirty 11\n"
      "workingset_refault_file 12\npgscan_kswapd 13\npgscan_direct 14\npgrefill 15\n";
    MemoryStat st{};
    check(ParseStat(stat,&st)&&st.file==20&&st.pgscan_direct==14,"all required stat fields");
    check(ParseStat(stat+"future_kernel_field 9\n",&st),"future fields permitted");
    check(!ParseStat(stat+"file 21\n",&st),"duplicate field rejected");
    check(!ParseStat(stat.substr(stat.find('\n')+1),&st),"missing required stat rejected");
    check(!ParseStat(stat+"file -1\n",&st),"negative accounting rejected");
    uint64_t high_events=99;
    check(ParseHighEvents("low 0\nhigh 153\nmax 0\noom 0\noom_kill 0\n",&high_events)&&high_events==153,"real high counter parsed");
    check(ParseHighEvents("future_event 7\nhigh 0\n",&high_events)&&high_events==0,"zero high and future events accepted");
    check(!ParseHighEvents("low 1\nmax 0\n",&high_events),"missing high rejected");
    check(!ParseHighEvents("high 1\nhigh 2\n",&high_events),"duplicate high rejected");
    check(!ParseHighEvents("high -1\n",&high_events)&&!ParseHighEvents("high +1\n",&high_events),"signed high rejected");
    check(!ParseHighEvents("high 18446744073709551615\n",&high_events),"high overflow rejected");
    check(!ParseHighEvents("high 1 junk\n",&high_events),"trailing high data rejected");
    check(!ParseHighEvents("high\n",&high_events),"truncated event rejected");
    HostMemory host{};
    std::string hm="MemTotal: 26214400 kB\nMemFree: 10485760 kB\nSwapTotal: 16777216 kB\nSwapFree: 5242880 kB\n";
    check(ParseHostMemory(hm,&host)&&host.total==25*GiB,"host values converted once");
    check(!ParseHostMemory(hm+"SwapFree: 1 kB\n",&host),"duplicate host field rejected");
    check(!ParseHostMemory("MemTotal: 5 MB\n",&host),"units and missing host values rejected");
    auto s=sample();
    check(Validate(s,4096)&&FreeBytes(s)==4*GiB,"cell hard cap bounds free capacity");
    s.current=5*GiB;
    check(FreeBytes(s)==GiB,"no host25GiB credit at 5GiB cell use");
    s.current=7*GiB;
    check(Validate(s,4096)&&FreeBytes(s)==0,"limit lowered below current saturates");
    s=sample();s.host.free=GiB/8;
    check(FreeBytes(s)==GiB/8,"host shortage further limits headroom");
    s=sample();s.max=0;
    check(!Validate(s,4096),"zero hard limit rejected");
    s=sample();s.high=7*GiB;
    check(!Validate(s,4096),"high above max rejected");
    s=sample();s.max=26*GiB;
    check(!Validate(s,4096),"capacity exceeding physical backing rejected");
    s=sample();s.high_unlimited=true;
    check(Validate(s,4096),"unlimited high is not unlimited hard budget");
    s=sample();
    check(SwapTotalBytes(s)==16*GiB&&SwapFreeBytes(s)==5*GiB,"unlimited swap bounded by shared backing");
    s.swap_unlimited=false;s.swap_max=6*GiB;
    check(SwapTotalBytes(s)==6*GiB&&SwapFreeBytes(s)==2*GiB,"finite swap counts only remaining quota");
    s.swap_current=7*GiB;
    check(SwapFreeBytes(s)==0,"lowered swap quota saturates");
    s=sample();s.host.swap_total=s.host.swap_free=0;
    check(SwapTotalBytes(s)==0&&SwapFreeBytes(s)==0,"swapless host truthful");
    s=sample();s.current=5*GiB;s.stat.file=3*GiB;s.stat.shmem=GiB;
    check(FreeBytes(s)==GiB,"file and shmem not credited twice");
    Watermarks w{};
    check(ScaleWatermarks(s,{100,150,200},4096,&w)&&w.high==GiB/4096&&w.low==3*GiB/4/4096&&w.min==GiB/2/4096,"soft-high reserve preserves kernel proportions");
    auto w0=w;s.high=11*GiB/2;
    check(ScaleWatermarks(s,{100,150,200},4096,&w)&&w.high==w0.high/2,"dynamic high reflected immediately");
    s.high_unlimited=true;
    check(ScaleWatermarks(s,{100,150,200},4096,&w)&&w.high==48,"unlimited high still scales to 6GiB");
    check(!ScaleWatermarks(s,{0,0,0},4096,&w)&&!ScaleWatermarks(s,{200,150,100},4096,&w),"unknown watermark rejected");
    auto a=sample(),b=a;a.stat.pgscan_direct=10;b.stat.pgscan_direct=11;
    check(CountersMonotonic(a,b),"reclaim counter increment valid");
    b.stat.pgscan_direct=9;
    check(!CountersMonotonic(a,b),"counter reset rejected");
    a=sample();b=a;a.high_events=10;b.high_events=9;
    check(!CountersMonotonic(a,b),"high counter rollback rejected");
    b=a;b.current=11*GiB/2;b.high_events=11;
    check(HighThrottlingProgressed(a,b),"new high throttle above finite unchanged boundary");
    b.high_events=10;
    check(!HighThrottlingProgressed(a,b),"historical high counter not current evidence");
    b.high_events=9;
    check(!HighThrottlingProgressed(a,b),"counter rollback not current evidence");
    b.high_events=11;b.current=b.high;
    check(!HighThrottlingProgressed(a,b),"equal high without current excess is quiet");
    b.current=b.high-1;
    check(!HighThrottlingProgressed(a,b),"usage below high is quiet despite event increment");
    b=a;b.current=11*GiB/2;b.high_events=11;b.high_unlimited=true;
    check(!HighThrottlingProgressed(a,b),"unlimited high cannot throttle");
    b.high_unlimited=false;a.high_unlimited=true;
    check(!HighThrottlingProgressed(a,b),"new finite high establishes a fresh baseline");
    a=sample();b=a;b.current=11*GiB/2;b.high_events=1;b.high-=4096;
    check(!HighThrottlingProgressed(a,b),"changed high cannot reuse old events");
    b.high=a.high;b.max+=4096;
    check(!HighThrottlingProgressed(a,b),"changed hard budget cannot reuse old events");
    b.max=a.max;b.swap_max+=4096;
    check(!HighThrottlingProgressed(a,b),"changed swap budget cannot reuse old events");
    b.swap_max=a.swap_max;b.swap_unlimited=!a.swap_unlimited;
    check(!HighThrottlingProgressed(a,b),"changed swap mode cannot reuse old events");
    Reader reader;Snapshot untouched=sample();
    check(!reader.Read(&untouched)&&reader.error()==EBADF&&untouched.max==6*GiB,"unopened reader cannot publish success");
    check(reader.OpenPressureMonitor(false,70000,1000000)==-1,"unopened reader cannot create PSI trigger");
    Reader regular;
    check(!regular.Open("/tmp")&&regular.error()==ENODEV,"regular fixture directory cannot masquerade as cgroup");
    check(!regular.Read(&untouched)&&regular.OpenPressureMonitor(false,1,1000000)==-1,"failed open cannot become monitor");
    std::printf("RESULT %d passed\n",count);
}

