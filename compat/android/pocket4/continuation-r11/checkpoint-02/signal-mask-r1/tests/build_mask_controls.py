#!/usr/bin/env python3
"""Compile actual ProcessGuestSignal and ARM64 GuestContext against declared
CPU/GuestCall fixture providers; use real Linux signals, masks and sigreturn.
This is a bounded source control, not a full translator or Android execution.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / (sys.argv[1] if len(sys.argv) > 1 else 'local-mask-controls-r1')
OUT.mkdir(exist_ok=False)
FIXTURE = OUT / 'fixture'


def write(name, content):
    path = FIXTURE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


write('berberis/base/checks.h', r'''
#pragma once
#include <cstdlib>
#define CHECK(x) do { if (!(x)) std::abort(); } while (0)
#define CHECK_NE(x,y) CHECK((x)!=(y))
''')
write('berberis/base/tracing.h', r'''
#pragma once
namespace berberis { template<class... T> inline void FixtureTrace(T...) {} }
#define TRACE(...) ::berberis::FixtureTrace(__VA_ARGS__)
''')
write('berberis/base/gettid.h', r'''
#pragma once
#include <sys/syscall.h>
#include <unistd.h>
namespace berberis {
inline pid_t GetpidSyscall() { return syscall(SYS_getpid); }
inline pid_t GettidSyscall() { return syscall(SYS_gettid); }
}
''')
write('berberis/guest_state/guest_state.h', r'''
#pragma once
#include <cstdint>
namespace berberis {
using GuestAddr = uintptr_t;
template<class T> inline T* ToHostAddr(GuestAddr p) { return reinterpret_cast<T*>(p); }
template<class T> inline GuestAddr ToGuestAddr(T* p) { return reinterpret_cast<GuestAddr>(p); }
// Fixture storage only. No translator, assembly or real CPUState ABI is claimed.
struct CPUState {
  uint64_t x[31]{}, sp = 0, insn_addr = 0;
  uint16_t flags = 0;
  uint32_t emulated_fpsr = 0, cached_fpcr = 0;
  __uint128_t v[32]{};
  static constexpr uint16_t kFlagNegative=0x8000, kFlagZero=0x4000;
  static constexpr uint16_t kFlagCarry=0x0100, kFlagOverflow=0x0001;
};
constexpr uint16_t kFlagsNZCVMask = 0xc101;
struct ThreadState { CPUState cpu; };
inline CPUState& GetCPUState(ThreadState& state) { return state.cpu; }
inline GuestAddr GetStackRegister(const CPUState& cpu) { return cpu.sp; }
inline GuestAddr GetInsnAddr(const CPUState& cpu) { return cpu.insn_addr; }
}
''')
write('berberis/guest_os_primitives/guest_thread.h', r'''
#pragma once
#include "berberis/guest_state/guest_state.h"
namespace berberis {
class GuestThread {
 public:
  ThreadState* state() { return &state_; }
  void SwitchToSigAltStack() {}
 private:
  ThreadState state_;
};
}
''')
write('berberis/guest_os_primitives/guest_signal.h', r'''
#pragma once
#include <csignal>
#include <cstring>
#include "berberis/base/host_signal.h"
#include "berberis/base/struct_check.h"
#include "berberis/guest_os_primitives/guest_thread.h"
namespace berberis {
using Guest_siginfo_t = siginfo_t;
struct Guest_sigset_t { uint64_t bits[1]; };
constexpr GuestAddr Guest_SIG_DFL=0, Guest_SIG_IGN=1, Guest_SIG_ERR=~GuestAddr{0};
template<class S, class B> void ConvertToBigSigset(const S& small, B* big) {
  static_assert(sizeof(S)<=sizeof(B)); std::memset(big,0,sizeof(B)); std::memcpy(big,&small,sizeof(S));
}
struct Guest_sigaction;
#if CANDIDATE
void ProcessGuestSignal(GuestThread*, const Guest_sigaction*, Guest_siginfo_t*);
void ProcessGuestSignal(GuestThread*, const Guest_sigaction*, Guest_siginfo_t*, HostSigset*);
#else
void ProcessGuestSignal(GuestThread*, const Guest_sigaction*, Guest_siginfo_t*);
#endif
}
''')
write('berberis/guest_abi/guest_call.h', r'''
#pragma once
#include <cstdint>
#include <signal.h>
#include "berberis/guest_state/guest_state.h"
namespace berberis {
void FixtureGuestHandler(GuestAddr, int, siginfo_t*, void*);
class GuestCall {
 public:
  void AddArgInt32(int signal) { signal_=signal; }
  void AddArgGuestAddr(GuestAddr address) { args_[count_++]=address; }
  void RunVoid(GuestAddr handler) {
    FixtureGuestHandler(handler,signal_,reinterpret_cast<siginfo_t*>(args_[0]),reinterpret_cast<void*>(args_[1]));
  }
 private:
  int signal_=0, count_=0;
  GuestAddr args_[2]{};
};
}
''')

results = []
for candidate, dirname in [(0, 'device-r16-preimage'), (1, 'source-candidate-r1')]:
    source = ROOT / dirname
    name = 'fixed' if candidate else 'baseline'
    executable = OUT / name
    command = ['g++', '-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
               '-pthread', '-DNATIVE_BRIDGE_GUEST_ARCH_ARM64=1', '-DBERBERIS_GUEST_LP64=1',
               f'-DCANDIDATE={candidate}', '-I', str(FIXTURE),
               '-I', str(source/'base/include'), '-I', str(source/'guest_os_primitives/arm64/include'),
               '-I', str(source/'guest_os_primitives/arm64'), '-I', str(source/'guest_os_primitives'),
               str(source/'guest_os_primitives/guest_signal_handling_arch.cc'),
               str(ROOT/'tests/mask_control.cc'), '-o', str(executable)]
    built = subprocess.run(command, capture_output=True, text=True, timeout=30)
    (OUT/(name+'.build.stderr')).write_text(built.stderr)
    entry = {'candidate':name, 'build_command':command, 'build_exit':built.returncode,
             'source_sha256':{str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in source.rglob('*') if p.is_file() and p.suffix in ['.h','.cc']}}
    if built.returncode:
        results.append(entry)
        (OUT/'report.json').write_text(json.dumps({'results':results},indent=2)+'\n')
        print(built.stderr)
        raise SystemExit(built.returncode)
    run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=15)
    (OUT/(name+'.stdout.jsonl')).write_text(run.stdout)
    (OUT/(name+'.stderr.txt')).write_text(run.stderr)
    entry.update(run_exit=run.returncode, stdout_sha256=hashlib.sha256(run.stdout.encode()).hexdigest(),
                 records=[json.loads(line) for line in run.stdout.splitlines()])
    results.append(entry)
    print(name,run.returncode,run.stdout,run.stderr,flush=True)
report = {'schema':1, 'scope':'Actual ProcessGuestSignal + ARM64 GuestContext with declared CPU/GuestCall fixture providers; real own-process Linux signal and sigreturn; not full translator/Android',
          'results':results, 'fixture_files':{str(p.relative_to(FIXTURE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in FIXTURE.rglob('*') if p.is_file()},
          'mask_control_sha256':hashlib.sha256((ROOT/'tests/mask_control.cc').read_bytes()).hexdigest()}
(OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
raise SystemExit(0 if results[0]['run_exit']==1 and results[1]['run_exit']==0 else 1)
