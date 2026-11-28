package org.droidloom.qa.state;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.net.Uri;
import android.os.Binder;
import android.os.Bundle;
import android.os.CancellationSignal;
import android.os.ParcelFileDescriptor;
import android.os.Process;
import android.os.SystemClock;
import android.system.ErrnoException;
import android.system.Os;
import android.system.OsConstants;
import android.system.StructStat;
import android.util.Base64;
import java.io.FileDescriptor;
import java.io.FileNotFoundException;
import java.security.MessageDigest;
import java.util.Arrays;
import org.json.JSONArray;
import org.json.JSONObject;

/** A fixed read of this owned fixture's state, without restarting its Activity.
 * No path, preference name, package, operation or output flag comes from IPC.
 * This provider has no network, file export or mutation interface. */
public final class FixedStateProvider extends ContentProvider {
    private static final String SCHEMA = "droidloom.owned-fixture-state.v1";
    private static final int MAX_PREFS = 65536;
    // Linux UAPI value; public SDK 31 omits the O_DIRECTORY constant.
    private static final int O_DIRECTORY = 0x10000;
    private static final String[][] KINDS = {
        {"org.droidloom.qa.saf.r12.na7f1de49e707c7a9", "a7f1de49e707c7a9", "owned-saf-a7f1de49e707c7a9.xml"},
        {"org.droidloom.qa.documents.r12.n98116f3fbefcfc95", "98116f3fbefcfc95", "owned-features-98116f3fbefcfc95.xml"},
        {"org.droidloom.qa.galleryrotation.r12.nd24b61ed8f7c9a03", "d24b61ed8f7c9a03", "owned-rotation-d24b61ed8f7c9a03.xml"},
        {"org.droidloom.qa.media.r12.nc92c3d79180955ef", "c92c3d79180955ef", "owned-media-c92c3d79180955ef-video.xml"}
    };

    private static void need(boolean value) {
        if (!value) throw new SecurityException("fixed owned-state contract rejected");
    }
    private String[] kind() {
        String name = getContext().getPackageName();
        need(Process.myUid() >= 10000 && Process.myUid() < 100000
            && getContext().getApplicationInfo().uid == Process.myUid());
        for (String[] row : KINDS) if (row[0].equals(name)) return row;
        throw new SecurityException("fixed owned-state package rejected");
    }
    @Override public boolean onCreate() { kind(); return true; }

    /** Android call has no URI path parameter. The normal factory fixes the
     * sole authority; this provider does not claim to inspect a path. */
    @Override public Bundle call(String method, String arg, Bundle extras) {
        kind();
        need(Binder.getCallingUid() == 2000 && "state".equals(method)
            && arg == null && (extras == null || extras.isEmpty()));
        try {
            String value = Base64.encodeToString(observe().toString().getBytes("UTF-8"), Base64.NO_WRAP);
            need(value.length() <= 196608);
            Bundle result = new Bundle(); result.putString("reply", value); return result;
        } catch (SecurityException error) { throw error; }
        catch (Exception error) { throw new IllegalStateException("fixed owned-state read failed", error); }
    }
    @Override public Cursor query(Uri uri, String[] projection, String selection,
                                  String[] arguments, String sort) { throw new SecurityException("no query interface"); }
    @Override public Cursor query(Uri uri, String[] projection, Bundle args,
                                  CancellationSignal cancellation) { throw new SecurityException("no query interface"); }

    private static long[] stable(StructStat s) {
        return new long[]{s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid};
    }
    private static long[] file(StructStat s) {
        return new long[]{s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid,
            s.st_nlink, s.st_size, s.st_mtim.tv_sec, s.st_mtim.tv_nsec,
            s.st_ctim.tv_sec, s.st_ctim.tv_nsec};
    }
    private static JSONArray numbers(long[] values) {
        JSONArray result = new JSONArray();
        for (long value : values) result.put(value);
        return result;
    }
    private static FileDescriptor directory(String path) throws Exception {
        FileDescriptor fd = Os.open(path, OsConstants.O_RDONLY | O_DIRECTORY
            | OsConstants.O_NOFOLLOW | OsConstants.O_CLOEXEC, 0);
        try {
            StructStat s = Os.fstat(fd);
            need(OsConstants.S_ISDIR(s.st_mode) && s.st_uid == Process.myUid()
                && s.st_gid == Process.myUid() && (s.st_mode & 0022) == 0
                && Arrays.equals(stable(s), stable(Os.lstat(path))));
            return fd;
        } catch (Exception error) { Os.close(fd); throw error; }
    }
    private static void absent(String path) throws Exception {
        try { Os.lstat(path); }
        catch (ErrnoException error) { if (error.errno == OsConstants.ENOENT) return; throw error; }
        throw new SecurityException("fixed preference absence changed");
    }
    private static String sha(byte[] raw) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(raw);
        StringBuilder out = new StringBuilder();
        for (byte b : digest) out.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
        return out.toString();
    }
    private static JSONObject selinux() throws Exception {
        // Selected 6.18 procattr returns the kernel SID string including its
        // single terminating NUL. Preserve that raw shape in the comparison.
        FileDescriptor fd = Os.open("/proc/self/attr/selinux/current",
            OsConstants.O_RDONLY | OsConstants.O_NOFOLLOW | OsConstants.O_CLOEXEC, 0);
        byte[] raw = new byte[256]; int count = 0;
        try {
            while (count < raw.length) {
                int n = Os.read(fd, raw, count, raw.length - count);
                if (n == 0) break;
                need(n > 0); count += n;
            }
            need(count > 0 && Os.read(fd, new byte[1], 0, 1) == 0);
        } finally { Os.close(fd); }
        boolean nul = raw[count-1] == 0; int length = count - (nul ? 1 : 0);
        need(length > 0);
        for (int i = 0; i < length; ++i) {
            int b = raw[i] & 255;
            need((b >= 'A' && b <= 'Z') || (b >= 'a' && b <= 'z')
                || (b >= '0' && b <= '9') || b == '_' || b == ':'
                || b == ',' || b == '.' || b == '-');
        }
        return new JSONObject().put("value", new String(raw, 0, length, "US-ASCII"))
            .put("bytes", count).put("sha256", sha(Arrays.copyOf(raw, count)))
            .put("terminal_nul", nul);
    }
    private JSONObject observe() throws Exception {
        String[] row = kind();
        long started = SystemClock.elapsedRealtimeNanos();
        JSONObject label = selinux();
        String ce = "/data/user/0/" + row[0], de = "/data/user_de/0/" + row[0];
        FileDescriptor ceFd = directory(ce);
        try {
            FileDescriptor deFd = directory(de);
            try {
                long[] ceIdentity = stable(Os.fstat(ceFd)), deIdentity = stable(Os.fstat(deFd));
                need(ceIdentity[0] == deIdentity[0] && ceIdentity[1] != deIdentity[1]);
                String parent = ce + "/shared_prefs", path = parent + "/" + row[2];
                JSONObject prefs = null;
                FileDescriptor parentFd = null;
                try { parentFd = directory(parent); }
                catch (ErrnoException error) {
                    if (error.errno != OsConstants.ENOENT) throw error;
                    absent(parent); absent(path);
                }
                if (parentFd != null) {
                    try {
                        long[] parentIdentity = stable(Os.fstat(parentFd));
                        FileDescriptor fd = null;
                        try { fd = Os.open(path, OsConstants.O_RDONLY | OsConstants.O_NOFOLLOW
                            | OsConstants.O_CLOEXEC | OsConstants.O_NONBLOCK, 0); }
                        catch (ErrnoException error) {
                            if (error.errno != OsConstants.ENOENT) throw error;
                            absent(path);
                        }
                        if (fd != null) {
                            try {
                                StructStat s = Os.fstat(fd);
                                need(OsConstants.S_ISREG(s.st_mode) && s.st_nlink == 1
                                    && s.st_uid == Process.myUid() && s.st_gid == Process.myUid()
                                    && (s.st_mode & 0022) == 0 && s.st_size > 0 && s.st_size <= MAX_PREFS);
                                byte[] raw = new byte[(int)s.st_size];
                                int count = 0;
                                while (count < raw.length) {
                                    int n = Os.read(fd, raw, count, raw.length - count);
                                    need(n > 0); count += n;
                                }
                                need(Os.read(fd, new byte[1], 0, 1) == 0
                                    && Arrays.equals(file(s), file(Os.fstat(fd)))
                                    && Arrays.equals(file(s), file(Os.lstat(path))));
                                prefs = new JSONObject().put("name", row[2]).put("metadata", numbers(file(s)))
                                    .put("bytes", raw.length).put("sha256", sha(raw))
                                    .put("base64", Base64.encodeToString(raw, Base64.NO_WRAP));
                            } finally { Os.close(fd); }
                        }
                        need(Arrays.equals(parentIdentity, stable(Os.fstat(parentFd)))
                            && Arrays.equals(parentIdentity, stable(Os.lstat(parent))));
                    } finally { Os.close(parentFd); }
                }
                need(Arrays.equals(ceIdentity, stable(Os.fstat(ceFd)))
                    && Arrays.equals(ceIdentity, stable(Os.lstat(ce)))
                    && Arrays.equals(deIdentity, stable(Os.fstat(deFd)))
                    && Arrays.equals(deIdentity, stable(Os.lstat(de))));
                JSONObject afterLabel = selinux();
                need(label.toString().equals(afterLabel.toString()));
                return new JSONObject().put("schema", SCHEMA).put("package", row[0]).put("run", row[1])
                    .put("uid", Process.myUid()).put("pid", Process.myPid()).put("caller_uid", Binder.getCallingUid())
                    .put("ce", numbers(ceIdentity)).put("de", numbers(deIdentity)).put("process_selinux", label)
                    .put("prefs", prefs == null ? JSONObject.NULL : prefs)
                    .put("started_elapsed_ns", started).put("finished_elapsed_ns", SystemClock.elapsedRealtimeNanos())
                    .put("state_mutated", false).put("activity_started", false);
            } finally { Os.close(deFd); }
        } finally { Os.close(ceFd); }
    }
    @Override public String getType(Uri uri) { throw new SecurityException("no MIME interface"); }
    @Override public Uri insert(Uri uri, ContentValues values) { throw new SecurityException("no insert interface"); }
    @Override public int update(Uri uri, ContentValues values, String selection, String[] args) { throw new SecurityException("no update interface"); }
    @Override public int delete(Uri uri, String selection, String[] args) { throw new SecurityException("no delete interface"); }
    @Override public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException { throw new SecurityException("no file interface"); }
}
