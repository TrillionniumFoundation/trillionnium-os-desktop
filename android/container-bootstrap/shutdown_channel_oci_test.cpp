// SPDX-License-Identifier: Apache-2.0
#include "shutdown_channel.h"
#include <fcntl.h>
#include <sys/mount.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>

#include <array>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <string_view>

namespace {
constexpr char request[] = "DROIDLOOM_SHUTDOWN_V1";
constexpr char complete[] = "DROIDLOOM_DATA_UNMOUNTED_V1";

bool Wait(pid_t pid) {
    int status;
    return waitpid(pid, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == 0;
}

int Bootstrap(std::string_view mode) {
    using namespace droidloom::bootstrap;
    if (!OpenShutdownChannel() || ShutdownFd() != 3 || !(fcntl(3, F_GETFD) & FD_CLOEXEC) ||
        AcknowledgeUnmount()) return 11;
    if (ReceiveShutdownRequest() || ReceiveShutdownRequest()) return 12;
    if (!ReceiveShutdownRequest() || AcknowledgeUnmount() || ShutdownFd() != -1) return 13;
    if (mode == "mounted") return 0;
    if (mode == "moved") {
        if (mount("/data", "/elsewhere", nullptr, MS_MOVE, nullptr) < 0 ||
            umount("/metadata") < 0) return 18;
        if (AcknowledgeUnmount()) return 19;
        if (umount("/elsewhere") < 0) return 20;
        if (!AcknowledgeUnmount() || AcknowledgeUnmount()) return 17;
        return 0;
    }
    if (umount("/data") < 0) { perror("umount /data"); return 14; }
    if (AcknowledgeUnmount()) return 15;
    if (umount("/metadata") < 0) { perror("umount /metadata"); return 16; }
    if (!AcknowledgeUnmount() || AcknowledgeUnmount()) return 17;
    return 0;
}
}  // namespace

int main(int argc, char** argv) {
    std::string_view mode = argc > 1 ? argv[1] : "";
    bool unmount = mode == "unmount" || mode == "moved";
    if (argc == 3 && std::string_view(argv[2]) == "bootstrap") return Bootstrap(mode);
    if (getpid() != 1 || (argc != 2) ||
        (!unmount && std::string_view(argv[1]) != "mounted")) return 21;
    int pair[2];
    if (socketpair(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0, pair) < 0) return 22;
    int yes = 1;
    for (int fd : pair) if (setsockopt(fd, SOL_SOCKET, SO_PASSCRED, &yes, sizeof(yes)) < 0) return 23;

    // Queue three datagrams. The genuine request from a sibling is rejected by its sender PID.
    pid_t sibling = fork();
    if (sibling == 0) _exit(send(pair[0], request, sizeof(request)-1, 0) == sizeof(request)-1 ? 0 : 1);
    if (sibling < 0 || !Wait(sibling)) return 24;
    if (send(pair[0], "bad", 3, 0) != 3 ||
        send(pair[0], request, sizeof(request)-1, 0) != sizeof(request)-1) return 25;
    pid_t bootstrap = fork();
    if (bootstrap == 0) {
        close(pair[0]);
        if (pair[1] != 3) {
            if (dup2(pair[1], 3) != 3) _exit(26);
            close(pair[1]);
        } else if (fcntl(3, F_SETFD, 0) < 0) {
            _exit(27);
        }
        execl("/test", "/test", argv[1], "bootstrap", nullptr);
        _exit(28);
    }
    close(pair[1]);
    if (bootstrap < 0 || !Wait(bootstrap)) return 29;
    std::array<char, 64> bytes {};
    iovec iov {bytes.data(), bytes.size()};
    alignas(cmsghdr) char ancillary[CMSG_SPACE(sizeof(ucred))] {};
    msghdr msg {};
    msg.msg_iov = &iov; msg.msg_iovlen = 1;
    msg.msg_control = ancillary; msg.msg_controllen = sizeof(ancillary);
    ssize_t n = recvmsg(pair[0], &msg, MSG_DONTWAIT);
    if (!unmount) {
        if (n != -1 || errno != EAGAIN) return 30;
        puts("PASS real PID1 sender, sibling rejected, FD_CLOEXEC, mounted data prevents ACK");
        return 0;
    }
    if (n != sizeof(complete)-1 || memcmp(bytes.data(), complete, sizeof(complete)-1)) return 31;
    auto* cred = CMSG_FIRSTHDR(&msg);
    if (!cred || msg.msg_flags & (MSG_TRUNC | MSG_CTRUNC) || cred->cmsg_level != SOL_SOCKET ||
        cred->cmsg_type != SCM_CREDENTIALS || cred->cmsg_len != CMSG_LEN(sizeof(ucred))) return 32;
    ucred sender {};
    memcpy(&sender, CMSG_DATA(cred), sizeof(sender));
    if (sender.pid != bootstrap || sender.uid != 0 || sender.gid != 0) return 33;
    puts("PASS original PID1 request, wrong sender rejected, two disposable mounts removed, exact bootstrap ACK");
    return 0;
}
