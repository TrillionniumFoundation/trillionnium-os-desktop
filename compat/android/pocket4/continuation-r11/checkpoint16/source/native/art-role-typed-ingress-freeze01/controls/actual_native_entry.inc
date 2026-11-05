static void com_android_internal_os_Zygote_nativeRequireDroidloomAppZygoteRoleV1(
        JNIEnv* env, jclass, jint uid, jint gid, jboolean child_zygote, jint version, jint kind,
        jint initial_uid, jint initial_gid, jint uid_min, jint uid_max,
        jint gid_min, jint gid_max) {
    using android::zygote::droidloom::AppZygoteSpecV1;
    static_assert(sizeof(jint) == sizeof(int32_t));
    static_assert(!android::zygote::droidloom::kAppZygoteRoleAuthorizationEnabled,
                  "Implement early policy and actual parent approval before enabling this path");
    const AppZygoteSpecV1 spec{version, kind, initial_uid, initial_gid,
                             uid_min, uid_max, gid_min, gid_max};
    if (!spec.Matches(uid, gid, child_zygote == JNI_TRUE)) {
        jniThrowException(env, "java/lang/IllegalArgumentException",
                          "Invalid private AppZygote specification V1");
        return;
    }
    if (getuid() != 0 || geteuid() != 0 || getgid() != 0 || getegid() != 0) {
        jniThrowException(env, "java/lang/SecurityException",
                          "Private AppZygote path requires root credentials");
        return;
    }
    // This is the exact remaining interface, not a permissive callback seam.
    // Do not fork, load a guest, set NNP/caps, contact a factory or fall back.
    jniThrowException(env, "java/lang/UnsupportedOperationException",
                      "AppZygote early policy and root-parent approval are unavailable");
}
