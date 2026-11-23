// SPDX-License-Identifier: GPL-3.0-or-later
#include <binder/IActivityManager.h>
#include <binder/IBinder.h>
#include <binder/IServiceManager.h>
#include <binder/ProcessState.h>
#include <linux/capability.h>
#include <private/android_filesystem_config.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/system_properties.h>
#include <sys/un.h>
#include <unistd.h>
#include <utils/String16.h>

#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdint>
#include <cstring>

namespace {
constexpr char kChannel[] = "/dev/socket/droidloom/droidloom_readiness";
constexpr std::array<uint8_t, 8> kRequest = {'D', 'L', 'R', 'D', 'R', 'E', 'Q', '1'};
constexpr std::array<uint8_t, 8> kResponse = {'D', 'L', 'R', 'D', 'R', 'S', 'P', '1'};
constexpr size_t kNonceBytes = 32;
constexpr uint8_t kBinder = 1, kBoot = 2, kActivity = 4;

bool original_identity() {
    uid_t ruid, euid, suid;
    gid_t rgid, egid, sgid;
    if (getppid() != 1 || getresuid(&ruid, &euid, &suid) != 0 ||
        getresgid(&rgid, &egid, &sgid) != 0 || ruid != AID_NOBODY || euid != ruid || suid != ruid ||
        rgid != AID_NOBODY || egid != rgid || sgid != rgid)
        return false;
    gid_t group;
    const int groups = getgroups(1, &group);
    if (groups < 0 || (groups == 1 && group != AID_NOBODY)) return false;
    __user_cap_header_struct head{_LINUX_CAPABILITY_VERSION_3, 0};
    __user_cap_data_struct caps[2]{};
    if (syscall(__NR_capget, &head, caps) != 0) return false;
    for (const auto& cap : caps) {
        if (cap.effective || cap.permitted || cap.inheritable) return false;
    }
    return prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0;
}

bool property_is(const char* key, const char* expected) {
    char value[PROP_VALUE_MAX]{};
    return __system_property_get(key, value) > 0 && strcmp(value, expected) == 0;
}

uint8_t observe() {
    if (!property_is("servicemanager.ready", "true")) return 0;
    auto manager = android::ProcessState::self()->getContextObject(nullptr);
    if (!manager || !manager->remoteBinder() || manager->pingBinder() != android::OK) return 0;
    if (!property_is("sys.boot_completed", "1")) return kBinder;
    auto services = android::defaultServiceManager();
    if (!services) return kBinder | kBoot;
    auto binder = services->checkService(android::String16("activity"));
    if (!binder) return kBinder | kBoot;
    auto activity = android::interface_cast<android::IActivityManager>(binder);
    int32_t answer = 0;
    // The platform client checks both transport and remote exceptions. Querying
    // our own identity never grants the signature-only permission being read.
    if (activity &&
        activity->checkPermission(android::String16("android.permission.REBOOT"), getpid(),
                                  getuid(), &answer) == android::OK &&
        answer == -1) {
        return kBinder | kBoot | kActivity;
    }
    return kBinder | kBoot;
}

int connect_owner() {
    sockaddr_un addr{};
    addr.sun_family = AF_UNIX;
    static_assert(sizeof(kChannel) <= sizeof(addr.sun_path));
    memcpy(addr.sun_path, kChannel, sizeof(kChannel));
    for (;;) {
        const int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
        if (fd == -1) return -1;
        if (connect(fd, reinterpret_cast<const sockaddr*>(&addr), sizeof(addr)) == 0) return fd;
        const int err = errno;
        close(fd);
        if (err != ENOENT && err != ECONNREFUSED && err != EINTR) return -1;
        if (err != EINTR) sleep(1);
    }
}
}  // namespace

int main() {
    if (!original_identity()) return 1;
    const int fd = connect_owner();
    if (fd == -1) return 1;
    for (;;) {
        std::array<uint8_t, kRequest.size() + kNonceBytes> request{};
        const ssize_t n = recv(fd, request.data(), request.size(), MSG_TRUNC);
        if (n < 0 && errno == EINTR) continue;
        if (n != static_cast<ssize_t>(request.size()) ||
            !std::equal(kRequest.begin(), kRequest.end(), request.begin()))
            break;
        std::array<uint8_t, kResponse.size() + kNonceBytes + 1> response{};
        std::copy(kResponse.begin(), kResponse.end(), response.begin());
        std::copy(request.begin() + kRequest.size(), request.end(),
                  response.begin() + kResponse.size());
        // A wedged Binder service must retire this observer. Android init can
        // restart it, and the host loses the kernel-bound peer immediately.
        alarm(4);
        response.back() = observe();
        const ssize_t sent = send(fd, response.data(), response.size(), MSG_NOSIGNAL);
        alarm(0);
        if (sent != static_cast<ssize_t>(response.size())) break;
    }
    close(fd);
    return 1;
}
