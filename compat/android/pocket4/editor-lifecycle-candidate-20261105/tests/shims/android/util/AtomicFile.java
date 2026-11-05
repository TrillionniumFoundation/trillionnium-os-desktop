package android.util;

/** Host-only identity boundary: the production snapshot never calls file IO. */
public final class AtomicFile {
    public AtomicFile(java.io.File path) { }
}
