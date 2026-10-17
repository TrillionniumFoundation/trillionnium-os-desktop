// SPDX-License-Identifier: Apache-2.0
// A08 first-party Android JNI binary; deliberately x86_64-only.
#include <jni.h>
#include <unistd.h>

#if !defined(__x86_64__)
#error A08 x86_64 JNI fixture compiled for unexpected target architecture
#endif

JNIEXPORT jstring JNICALL
Java_org_trillionnium_a08native_MainActivity_nativeIsa(JNIEnv *env, jclass clazz) {
    (void)clazz;
    return (*env)->NewStringUTF(env, "x86_64");
}

JNIEXPORT jlong JNICALL
Java_org_trillionnium_a08native_MainActivity_nativePid(JNIEnv *env, jclass clazz) {
    (void)env;
    (void)clazz;
    return (jlong)getpid();
}
