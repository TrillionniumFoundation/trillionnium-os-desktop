package org.trillionnium.a08native;
public final class MainActivity {
    static { System.loadLibrary("a08jni"); }
    private static native String nativeIsa();
    private static native long nativePid();
    public static void main(String[] args) {
        if (!"x86_64".equals(nativeIsa()) || nativePid() != ProcessHandle.current().pid()) {
            throw new AssertionError("actual host JNI identity/PID mismatch");
        }
        System.out.println("HOST_JNI_INTEGRATION_PASS isa="+nativeIsa()+" pid_equal=true");
    }
}
