#include <android/content/pm/IPackageManagerNative.h>
#include <binder/IServiceManager.h>
#include <utils/String16.h>

#include <cstdio>
#include <string>
#include <string_view>
#include <sys/stat.h>
#include <unistd.h>

static bool validPackageName(std::string_view name) {
    if (name.empty() || name.size() > 255) return false;
    bool first = true;
    for (char c : name) {
        const bool letter = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');
        if (c == '.') {
            if (first) return false;
            first = true;
        } else if (letter || (!first && ((c >= '0' && c <= '9') || c == '_'))) {
            first = false;
        } else {
            return false;
        }
    }
    return !first;
}

int main(int argc, char** argv) {
    using android::content::pm::IPackageManagerNative;
    if (argc != 2 || !validPackageName(argv[1])) {
        std::fprintf(stderr, "Usage: droidloom-package-inspect PACKAGE\n");
        return 2;
    }

    if (getuid() >= 100000) {
        std::fprintf(stderr, "A user-0 Android caller is required for the version query\n");
        return 1;
    }
    struct stat node {};
    if (stat("/dev/binder", &node) < 0) {
        std::perror("/dev/binder");
        return 1;
    }
    if (!S_ISCHR(node.st_mode)) {
        std::fprintf(stderr, "/dev/binder is not a character device\n");
        return 1;
    }
    // The framework can disappear between service lookup and either query.
    // Each invocation is bounded and publishes output only after both replies.
    alarm(10);
    const auto manager = android::defaultServiceManager();
    if (!manager) {
        std::fprintf(stderr, "Service manager unavailable\n");
        return 1;
    }
    const auto binder = manager->checkService(android::String16("package_native"));
    if (!binder || !binder->remoteBinder() || binder->pingBinder() != android::OK ||
        binder->getInterfaceDescriptor() != IPackageManagerNative::descriptor) {
        std::fprintf(stderr, "Android package_native service unavailable\n");
        return 1;
    }
    const auto packages = android::interface_cast<IPackageManagerNative>(binder);
    if (!packages) return 1;
    const std::string name(argv[1]);
    int32_t uid = -1;
    int64_t version = 0;
    const auto uidStatus = packages->getPackageUid(name, 0, 0, &uid);
    if (!uidStatus.isOk()) {
        std::fprintf(stderr, "getPackageUid: %s\n", uidStatus.toString8().c_str());
        return 1;
    }
    if (uid < 0) {
        std::fprintf(stderr, "Package unavailable to the caller for Android user 0\n");
        return 1;
    }
    const auto versionStatus = packages->getVersionCodeForPackage(android::String16(name.c_str()), &version);
    if (!versionStatus.isOk()) {
        std::fprintf(stderr, "getVersionCodeForPackage: %s\n", versionStatus.toString8().c_str());
        return 1;
    }
    if (version <= 0) {
        std::fprintf(stderr, "Package version unavailable to the caller\n");
        return 1;
    }
    std::printf("{\"package\":\"%s\",\"user\":0,\"uid\":%d,\"version_code\":%lld}\n",
                name.c_str(), uid, static_cast<long long>(version));
    return 0;
}
