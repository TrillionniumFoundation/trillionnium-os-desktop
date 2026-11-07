#!/usr/bin/env python3
# Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
"""Compile actual event dispatch and guarded Reaper source with owned I/O controls.

These controls never execute a signal/cgroup write. The effect syscalls are
replaced explicitly, while Session and SCM_RIGHTS run as compiled production
components. This is not Android integration or real PSI evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--source-dir', required=True, type=Path)
p.add_argument('--baseline-dir', required=True, type=Path)
p.add_argument('--out-dir', required=True, type=Path)
a = p.parse_args()
a.out_dir.mkdir(parents=True, exist_ok=False)
here = Path(__file__).resolve().parent
source = (a.source_dir / 'lmkd.cpp').read_text()
baseline = (a.baseline_dir / 'lmkd.cpp').read_text()


def block(text, start):
    brace = text.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        if text[end] == '{': depth += 1
        if text[end] == '}': depth -= 1
        end += 1
    return text[start:end]


def function(text, marker):
    return block(text, text.index(marker))


unchanged = {}
for marker in ['static int find_and_kill_process(', 'static void apply_proc_prio(',
               'static void register_oom_adj_proc(', 'static bool claim_record(',
               'static void __mp_event_psi(', 'static bool update_props() {']:
    old, new = function(baseline, marker), function(source, marker)
    assert old == new, marker + ' policy drift'
    unchanged[marker] = hashlib.sha256(new.encode()).hexdigest()

first = source.index('        for (i = 0, evt = &events[0]; i < nevents; ++i, evt++) {',
                     source.index('static void mainloop(void)'))
first_body = block(source, first)
second = source.index('        for (i = 0, evt = &events[0]; i < nevents; ++i, evt++) {',
                      first + len(first_body))
second_body = block(source, second)
router = r'''
#include <sys/epoll.h>
#include <cstdio>
#include <cstdlib>
#define ALOGI(...) ((void)0)
#define ALOGD(...) ((void)0)
struct polling_params {};
struct event_handler_info { int data; void (*handler)(int, uint32_t, polling_params*); };
static bool cell_relay_required = true, active = true;
static unsigned effects = 0, closes = 0, done = 0, checks = 0;
static int last_closed = -1;
static struct { void start() {} void stop() {} } watchdog;
static void cell_relay_event(int, uint32_t events, polling_params*) {
    if (events & (EPOLLHUP | EPOLLRDHUP | EPOLLERR)) active = false;
    else if (active) ++effects;
}
static void cell_relay_control_event(int, uint32_t, polling_params*) { active = false; }
static void kill_done_handler(int, uint32_t, polling_params*) { ++done; }
static void ordinary_handler(int, uint32_t, polling_params*) {}
static void ctrl_data_close(int index) { ++closes; last_closed = index; }
static void call_handler(event_handler_info* info, polling_params* params, uint32_t events) {
    info->handler(info->data, events, params);
}
'''
router += function(source, 'static bool is_cell_relay_handler(')
router += '\nstatic void Run(epoll_event* events, int nevents) {\n'
router += ' event_handler_info* handler_info; polling_params poll_params; epoll_event* evt; int i;\n'
router += first_body + '\n' + second_body + '\n}\n'
router += r'''
static void Check(bool value, const char* label) {
    if (!value) { std::fprintf(stderr, "FAIL %s\n", label); std::exit(2); }
    ++checks; std::printf("PASS %s\n", label);
}
int main() {
    event_handler_info medium{1, cell_relay_event}, critical{2, cell_relay_event};
    event_handler_info control{0, cell_relay_control_event}, ordinary{2, ordinary_handler};
    event_handler_info killed{0, kill_done_handler};
    for (uint32_t fault : {uint32_t(EPOLLHUP), uint32_t(EPOLLRDHUP), uint32_t(EPOLLERR)}) {
        active = true; effects = closes = 0;
        epoll_event batch[2]{};
        batch[0].events = EPOLLIN; batch[0].data.ptr = &critical;
        batch[1].events = fault; batch[1].data.ptr = &medium;
        Run(batch, 2);
        Check(!active && !effects && !closes, "relay failure preempts earlier queued event without ctrl_data_close");
    }
    active = true; effects = closes = 0;
    epoll_event control_batch[2]{};
    control_batch[0].events = EPOLLIN; control_batch[0].data.ptr = &critical;
    control_batch[1].events = EPOLLIN; control_batch[1].data.ptr = &control;
    Run(control_batch, 2);
    Check(!active && !effects && !closes, "unexpected control IN retires old batch before pressure dispatch");
    epoll_event original{}; original.events = EPOLLHUP; original.data.ptr = &ordinary;
    Run(&original, 1);
    Check(closes == 1 && last_closed == 2, "ordinary framework connection keeps original close index");
    original.data.ptr = &killed; Run(&original, 1);
    Check(done == 1 && closes == 1, "process-death HUP keeps original completion handler");
    active = true; effects = closes = 0;
    original.events = EPOLLIN; original.data.ptr = &critical; Run(&original, 1);
    Check(effects == 1 && !closes, "healthy pressure dispatch remains reachable");
    std::printf("RESULT %u source router assertions passed; no Android event loop\n", checks);
}
'''
router = '#include <cstdint>\n#include <initializer_list>\n' + router

header = (a.source_dir / 'reaper.h').read_text()
types = header[header.index('struct CgroupKillFD'):header.index('class Reaper')]
api = header[header.index('    struct target_proc'):header.index('private:')]
guarded = '#include <optional>\n#include <variant>\nextern "C" {\n#include <sys/pidfd.h>\n}\n#include <unistd.h>\n#include <signal.h>\n'
guarded += types + '\nclass Reaper { public:\n' + api
guarded += 'GuardedResult kill_guarded(const target_proc&, const EffectGate&);\n};\n'
guarded += function((a.source_dir/'reaper.cpp').read_text(), 'Reaper::GuardedResult Reaper::kill_guarded(')
guarded += '\n#define main uncalled_session_control_main\n#include "' + str(here/'test_session.cpp') + '"\n#undef main\n'
guarded += r'''
static unsigned writes = 0, signals = 0, validations = 0;
static bool write_ok = true, group_ok = true;
static uint64_t advance_after_write = 0;
extern "C" ssize_t __wrap_write(int fd, const void* data, size_t length) {
    Need(fd == 51 && length == 1 && *static_cast<const char*>(data) == '1', "single cgroup effect shape");
    ++writes;
    if (advance_after_write) test_clock = advance_after_write;
    if (!write_ok) { errno = EACCES; return -1; }
    return 1;
}
extern "C" int __wrap_pidfd_send_signal(int fd, int signal, siginfo_t*, unsigned flags) {
    Need(fd == 61 && signal == SIGKILL && flags == 0, "held pidfd effect shape");
    ++signals; return 0;
}
static Reaper::GuardedResult Gate(void* context, Reaper::Effect effect, void* argument) {
    const auto result = static_cast<Session*>(context)->Perform([&]() { return effect(argument); });
    if (result == Dispatch::Denied) return Reaper::GuardedResult::Denied;
    if (result == Dispatch::Failed) return Reaper::GuardedResult::Failed;
    return Reaper::GuardedResult::Sent;
}
static bool Group(void*, int fd, uid_t uid, pid_t pid) {
    ++validations;
    Need(fd == 51 && uid == 10001 && pid == 123, "exact expected group check");
    return group_ok;
}
int main() {
    Fixture f;
    Reaper reaper;
    const Reaper::EffectGate gate{&f.session, Gate, Group};
    Reaper::target_proc target{61, {}, 123, 10001};
    Check(reaper.kill_guarded(target, gate) == Reaper::GuardedResult::Denied && !signals,
          "real Reaper entry cannot signal from lease-only authority");
    f.FreezeClock(); const uint64_t observed = f.Fresh();
    Check(reaper.kill_guarded(target, gate) == Reaper::GuardedResult::Sent && signals == 1 && !writes,
          "pidfd-only effect is synchronous and finally gated");
    target.cgroupfd = CgroupKillFD{51}; signals = 0;
    Check(reaper.kill_guarded(target, gate) == Reaper::GuardedResult::Sent && writes == 1 && !signals && validations == 1,
          "verified exact group uses one actual write without queued work");
    group_ok = false;
    Check(reaper.kill_guarded(target, gate) == Reaper::GuardedResult::Denied && writes == 1 && !signals,
          "unbound broad group is refused without fallback");
    group_ok = true; target.cgroupfd = CgroupProcsFD{51};
    Check(reaper.kill_guarded(target, gate) == Reaper::GuardedResult::Denied && writes == 1 && !signals,
          "legacy numeric-PID cgroup loop is explicitly unsupported");
    target.cgroupfd = CgroupKillFD{51}; write_ok = false;
    Check(reaper.kill_guarded(target, gate) == Reaper::GuardedResult::Sent && writes == 2 && signals == 1,
          "failed group write requires a separately gated held-pidfd fallback");
    signals = 0; advance_after_write = observed + 1000000000;
    Check(reaper.kill_guarded(target, gate) == Reaper::GuardedResult::Denied && writes == 3 && !signals,
          "window expiry during failed group write prevents fallback syscall");
    f.session.Stop(); writes = signals = 0;
    Check(reaper.kill_guarded(target, gate) == Reaper::GuardedResult::Denied && !writes && !signals,
          "revoked generation leaves no deferred worker effect");
    std::printf("RESULT %u actual Reaper source assertions passed; syscall I/O replaced\n", passed);
}
'''

report = {'scope': 'source-extracted router and Reaper effect body; local real Session sockets; effect syscall I/O replaced; no Android/real PSI/cgroup/signal/deployment',
          'unchanged_r5_policy_sha256': unchanged, 'tests': {}, 'source_sha256': {}}
for name, text in [('router', router), ('guarded_reaper', guarded)]:
    cpp, exe = a.out_dir/(name+'.cpp'), a.out_dir/name
    cpp.write_text(text)
    command = ['g++', '-std=c++17', '-O2', '-g0', '-Wall', '-Wextra', '-Werror', '-pthread', '-I', str(a.source_dir), str(cpp)]
    if name == 'guarded_reaper':
        command += [str(a.source_dir/n) for n in ['pressure_relay.cpp', 'enrollment.cpp', 'relay_session.cpp']]
        command += ['-Wl,--wrap=clock_gettime,--wrap=write,--wrap=pidfd_send_signal']
    command += ['-o', str(exe)]
    built = subprocess.run(command, capture_output=True, text=True, timeout=30)
    run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15) if built.returncode == 0 else None
    report['tests'][name] = {'command': command, 'compile_rc': built.returncode, 'compile_stderr': built.stderr,
                           'test_rc': None if run is None else run.returncode,
                           'stdout': None if run is None else run.stdout, 'stderr': None if run is None else run.stderr}
    (a.out_dir/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    assert built.returncode == 0, built.stderr
    assert run.returncode == 0, run.stderr
    print(run.stdout)
for path in sorted(a.source_dir.iterdir()):
    if path.suffix in ('.cpp', '.h', '.bp'):
        report['source_sha256'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
report['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
report['pass'] = True
(a.out_dir/'result.json').write_text(json.dumps(report, indent=2)+'\n')
