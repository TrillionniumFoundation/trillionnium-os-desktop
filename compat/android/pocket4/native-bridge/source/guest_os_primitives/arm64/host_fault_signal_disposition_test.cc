// Copyright (C) 2026 The Android Open Source Project
// SPDX-License-Identifier: Apache-2.0

#include <gtest/gtest.h>

#include <sys/time.h>
#include <sys/wait.h>
#include <unistd.h>

#include <cerrno>
#include <csignal>
#include <cstdint>

#include "berberis/guest_os_primitives/guest_signal.h"

namespace berberis {
namespace {
volatile sig_atomic_t g_count = 0;
volatile sig_atomic_t g_signo = 0;
volatile sig_atomic_t g_code = 0;
volatile sig_atomic_t g_sender = 0;

void Handler(int signo) {
  g_signo = signo;
  g_count = g_count + 1;
}

void InfoHandler(int signo, siginfo_t* info, void*) {
  g_signo = signo;
  g_code = info->si_code;
  g_sender = info->si_pid;
  g_count = g_count + 1;
}

void ResetAlarm() {
  struct itimerval timer {};
  if (setitimer(ITIMER_REAL, &timer, nullptr) != 0) _exit(80);
  struct sigaction action {};
  action.sa_handler = SIG_DFL;
  sigemptyset(&action.sa_mask);
  if (sigaction(SIGALRM, &action, nullptr) != 0) _exit(81);
  sigset_t clear;
  sigemptyset(&clear);
  if (sigprocmask(SIG_SETMASK, &clear, nullptr) != 0) _exit(82);
  g_count = 0;
  g_signo = 0;
  g_code = 0;
  g_sender = 0;
}

int ChildStatus(void (*body)()) {
  const pid_t pid = fork();
  if (pid == 0) {
    ResetAlarm();
    body();
    _exit(0);
  }
  if (pid < 0) return -1;
  int status;
  while (waitpid(pid, &status, 0) < 0) {
    if (errno != EINTR) return -1;
  }
  return status;
}

void ExpectExitZero(int status) {
  ASSERT_NE(status, -1);
  ASSERT_TRUE(WIFEXITED(status)) << status;
  EXPECT_EQ(WEXITSTATUS(status), 0);
}

void ExpectAlarmDeath(int status) {
  ASSERT_NE(status, -1);
  ASSERT_TRUE(WIFSIGNALED(status)) << status;
  EXPECT_EQ(WTERMSIG(status), SIGALRM);
}

TEST(HostFaultSignalDisposition, DefaultAlarmStillTerminates) {
  ExpectAlarmDeath(ChildStatus([] {
    ClaimHostFaultSignals();
    raise(SIGALRM);
    _exit(91);
  }));
}

TEST(HostFaultSignalDisposition, ArmedDeadlineStillTerminates) {
  ExpectAlarmDeath(ChildStatus([] {
    struct itimerval timer {};
    timer.it_value.tv_usec = 20000;
    if (setitimer(ITIMER_REAL, &timer, nullptr) != 0) _exit(83);
    ClaimHostFaultSignals();
    usleep(100000);
    _exit(92);
  }));
}

TEST(HostFaultSignalDisposition, BlockedPendingAlarmIsNotDiscarded) {
  ExpectAlarmDeath(ChildStatus([] {
    sigset_t block, pending;
    sigemptyset(&block);
    sigaddset(&block, SIGALRM);
    if (sigprocmask(SIG_BLOCK, &block, nullptr) != 0) _exit(84);
    raise(SIGALRM);
    if (sigpending(&pending) != 0 || sigismember(&pending, SIGALRM) != 1) _exit(85);
    ClaimHostFaultSignals();
    if (sigpending(&pending) != 0 || sigismember(&pending, SIGALRM) != 1) _exit(93);
    if (sigprocmask(SIG_UNBLOCK, &block, nullptr) != 0) _exit(86);
    _exit(94);
  }));
}

TEST(HostFaultSignalDisposition, ExistingPlainHandlerIsPreserved) {
  ExpectExitZero(ChildStatus([] {
    struct sigaction action {}, actual {};
    action.sa_handler = Handler;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGALRM, &action, nullptr) != 0) _exit(87);
    ClaimHostFaultSignals();
    if (sigaction(SIGALRM, nullptr, &actual) != 0 || actual.sa_handler != Handler) _exit(95);
    raise(SIGALRM);
    if (g_count != 1 || g_signo != SIGALRM) _exit(96);
  }));
}

TEST(HostFaultSignalDisposition, UserSignalCauseAndSenderArePreserved) {
  ExpectExitZero(ChildStatus([] {
    struct sigaction action {}, actual {};
    action.sa_sigaction = InfoHandler;
    action.sa_flags = SA_SIGINFO;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGALRM, &action, nullptr) != 0) _exit(87);
    ClaimHostFaultSignals();
    if (sigaction(SIGALRM, nullptr, &actual) != 0 ||
        !(actual.sa_flags & SA_SIGINFO) || actual.sa_sigaction != InfoHandler) _exit(97);
    if (kill(getpid(), SIGALRM) != 0) _exit(88);
    if (g_count != 1 || g_signo != SIGALRM || g_code != SI_USER || g_sender != getpid()) _exit(98);
  }));
}

TEST(HostFaultSignalDisposition, ExplicitIgnoreIsPreserved) {
  ExpectExitZero(ChildStatus([] {
    struct sigaction action {}, actual {};
    action.sa_handler = SIG_IGN;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGALRM, &action, nullptr) != 0) _exit(87);
    ClaimHostFaultSignals();
    if (sigaction(SIGALRM, nullptr, &actual) != 0 || actual.sa_handler != SIG_IGN) _exit(99);
    if (raise(SIGALRM) != 0) _exit(88);
  }));
}

TEST(HostFaultSignalDisposition, ExistingMaskIsPreserved) {
  ExpectExitZero(ChildStatus([] {
    sigset_t block, actual;
    sigemptyset(&block);
    sigaddset(&block, SIGALRM);
    sigaddset(&block, SIGUSR2);
    if (sigprocmask(SIG_SETMASK, &block, nullptr) != 0) _exit(84);
    ClaimHostFaultSignals();
    if (sigprocmask(SIG_SETMASK, nullptr, &actual) != 0) _exit(86);
    for (int signo = 1; signo < NSIG; ++signo) {
      if (sigismember(&block, signo) != sigismember(&actual, signo)) _exit(100);
    }
  }));
}

TEST(HostFaultSignalDisposition, OtherSignalDispositionsArePreserved) {
  ExpectExitZero(ChildStatus([] {
    struct sigaction dfl {}, custom {}, actual {};
    dfl.sa_handler = SIG_DFL; custom.sa_handler = Handler;
    sigemptyset(&dfl.sa_mask); sigemptyset(&custom.sa_mask);
    if (sigaction(SIGUSR1, &dfl, nullptr) != 0 ||
        sigaction(SIGUSR2, &custom, nullptr) != 0) _exit(87);
    ClaimHostFaultSignals();
    if (sigaction(SIGUSR1, nullptr, &actual) != 0 || actual.sa_handler != SIG_DFL) _exit(101);
    if (sigaction(SIGUSR2, nullptr, &actual) != 0 || actual.sa_handler != Handler) _exit(102);
    raise(SIGUSR2);
    if (g_count != 1 || g_signo != SIGUSR2) _exit(103);
  }));
}
}  // namespace
}  // namespace berberis
