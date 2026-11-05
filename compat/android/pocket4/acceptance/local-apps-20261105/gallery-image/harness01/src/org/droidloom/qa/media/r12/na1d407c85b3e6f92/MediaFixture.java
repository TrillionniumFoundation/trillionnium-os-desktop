package org.droidloom.qa.media.r12.na1d407c85b3e6f92;

import android.app.Instrumentation;
import android.content.ContentResolver;
import android.content.ContentUris;
import android.content.ContentValues;
import android.content.Context;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.net.Uri;
import android.os.Bundle;
import android.os.Process;
import android.provider.MediaStore;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.MessageDigest;
import java.util.Locale;
import org.json.JSONObject;

/** Own one synthetic PNG through public MediaStore APIs; no activity or permission. */
public final class MediaFixture extends Instrumentation {
    static final String RUN = "a1d407c85b3e6f92";
    static final String PACKAGE = "org.droidloom.qa.media.r12.na1d407c85b3e6f92";
    static final String RELATIVE = "DCIM/Pocket4_Gallery_r12_" + RUN + "/";
    static final String NAME = "pocket4-pattern-" + RUN + ".png";
    static final int WIDTH = 640, HEIGHT = 480, MAX_BYTES = 4 * 1024 * 1024;
    static final long LEASE_MS = 1200000L;
    static final Uri COLLECTION = MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY);
    Bundle arguments;
    Context context;
    ContentResolver resolver;
    SharedPreferences prefs;

    static void need(boolean value, String reason) {
        if (!value) throw new IllegalStateException(reason);
    }

    @Override public void onCreate(Bundle values) {
        super.onCreate(values);
        arguments = values == null ? new Bundle() : values;
        start();
    }

    static String digest(byte[] bytes) throws Exception {
        StringBuilder out = new StringBuilder();
        for (byte value : MessageDigest.getInstance("SHA-256").digest(bytes))
            out.append(String.format(Locale.ROOT, "%02x", value & 255));
        return out.toString();
    }

    void commit(SharedPreferences.Editor editor) {
        need(editor.commit(), "OWNED_RECORD_COMMIT_FAILED");
    }

    String phase() { return prefs.getString("phase", "EMPTY"); }

    void live() {
        need(RUN.equals(prefs.getString("run", "")), "RUN_IDENTITY_CHANGED");
        long age = System.currentTimeMillis() - prefs.getLong("started_ms", 0);
        need(age >= 0 && age < LEASE_MS, "OWNED_FIXTURE_LEASE_EXPIRED");
    }

    Uri ownedUri() {
        String value = prefs.getString("uri", "");
        Uri uri = Uri.parse(value);
        need("content".equals(uri.getScheme()) && "media".equals(uri.getAuthority())
                && uri.getQuery() == null && uri.getFragment() == null, "OWNED_URI_REQUIRED");
        long id = ContentUris.parseId(uri);
        need(id > 0 && uri.equals(ContentUris.withAppendedId(COLLECTION, id)), "EXACT_IMAGE_COLLECTION_REQUIRED");
        return uri;
    }

    int rowCount(Uri uri, String selection, String[] selectionArgs) {
        try (Cursor c = resolver.query(uri, new String[] {"_id"}, selection, selectionArgs, null)) {
            need(c != null, "QUERY_CURSOR_REQUIRED");
            int count = c.getCount();
            need(count <= 16, "OWNED_QUERY_COUNT_BOUND");
            return count;
        }
    }

    static int color(int x, int y) {
        if (x < 8 || x >= WIDTH - 8 || y < 8 || y >= HEIGHT - 8) return 0xff000000;
        if (Math.abs(x - WIDTH / 2) < 8 || Math.abs(y - HEIGHT / 2) < 8) return 0xffffffff;
        if (y < HEIGHT / 2) return x < WIDTH / 2 ? 0xffff3b30 : 0xff34c759;
        return x < WIDTH / 2 ? 0xff007aff : 0xffffcc00;
    }

    static byte[] pattern() throws Exception {
        int[] pixels = new int[WIDTH * HEIGHT];
        for (int y = 0; y < HEIGHT; y++) for (int x = 0; x < WIDTH; x++)
            pixels[y * WIDTH + x] = color(x, y);
        Bitmap bitmap = Bitmap.createBitmap(pixels, WIDTH, HEIGHT, Bitmap.Config.ARGB_8888);
        try {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            need(bitmap.compress(Bitmap.CompressFormat.PNG, 100, out), "PNG_ENCODING_FAILED");
            byte[] bytes = out.toByteArray();
            need(bytes.length > 100 && bytes.length < MAX_BYTES, "PNG_SIZE_BOUND");
            return bytes;
        } finally { bitmap.recycle(); }
    }

    byte[] read(Uri uri) throws Exception {
        try (InputStream input = resolver.openInputStream(uri)) {
            need(input != null, "OWNED_IMAGE_STREAM_REQUIRED");
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buffer = new byte[8192]; int count;
            while ((count = input.read(buffer)) != -1) {
                need(out.size() + count <= MAX_BYTES, "OWNED_READ_BOUND");
                out.write(buffer, 0, count);
            }
            return out.toByteArray();
        }
    }

    JSONObject verify(boolean pendingAllowed) throws Exception {
        Uri uri = ownedUri();
        String[] fields = {"_id", "_display_name", "relative_path", "mime_type", "_size",
                "width", "height", "is_pending", "owner_package_name"};
        JSONObject metadata = new JSONObject();
        try (Cursor c = resolver.query(uri, fields, null, null, null)) {
            need(c != null && c.getCount() == 1 && c.moveToFirst(), "ONE_EXACT_MEDIA_ROW_REQUIRED");
            need(c.getLong(0) == ContentUris.parseId(uri) && NAME.equals(c.getString(1))
                    && RELATIVE.equals(c.getString(2)) && "image/png".equals(c.getString(3))
                    && PACKAGE.equals(c.getString(8)), "OWNED_MEDIA_METADATA_CHANGED");
            need(c.getInt(7) == (pendingAllowed ? 1 : 0), "MEDIA_PUBLICATION_STATE_CHANGED");
            for (int i = 0; i < fields.length; i++) metadata.put(fields[i], c.isNull(i) ? JSONObject.NULL : c.getString(i));
        }
        byte[] bytes = read(uri);
        String hash = digest(bytes);
        need(hash.equals(prefs.getString("sha256", ""))
                && bytes.length == prefs.getInt("bytes", -1), "OWNED_IMAGE_BYTES_CHANGED");
        Bitmap bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.length);
        need(bitmap != null, "OWNED_PNG_DECODE_FAILED");
        try {
            need(bitmap.getWidth() == WIDTH && bitmap.getHeight() == HEIGHT, "OWNED_IMAGE_DIMENSIONS_CHANGED");
            int[][] samples = {{1, 1}, {100, 100}, {540, 100}, {100, 380}, {540, 380}, {320, 240}};
            for (int[] sample : samples) need(bitmap.getPixel(sample[0], sample[1]) == color(sample[0], sample[1]),
                    "OWNED_PIXEL_PATTERN_CHANGED");
        } finally { bitmap.recycle(); }
        return new JSONObject().put("uri", uri.toString()).put("sha256", hash).put("bytes", bytes.length)
                .put("width", WIDTH).put("height", HEIGHT).put("pixel_samples_exact", true).put("metadata", metadata);
    }

    JSONObject seed() throws Exception {
        need(prefs.getAll().isEmpty() && "EMPTY".equals(phase()), "FRESH_PACKAGE_STATE_REQUIRED");
        need(rowCount(COLLECTION, "relative_path=?", new String[] {RELATIVE}) == 0, "OWNED_MEDIA_NAMESPACE_PRESENT");
        byte[] payload = pattern();
        commit(prefs.edit().putString("run", RUN).putLong("started_ms", System.currentTimeMillis())
                .putString("phase", "SEED_PENDING").putString("pending", "insert-owned-image")
                .putString("sha256", digest(payload)).putInt("bytes", payload.length).putInt("insert_calls", 1));
        ContentValues values = new ContentValues();
        values.put(MediaStore.MediaColumns.DISPLAY_NAME, NAME);
        values.put(MediaStore.MediaColumns.MIME_TYPE, "image/png");
        values.put(MediaStore.MediaColumns.RELATIVE_PATH, RELATIVE);
        values.put(MediaStore.MediaColumns.IS_PENDING, 1);
        values.put(MediaStore.MediaColumns.WIDTH, WIDTH); values.put(MediaStore.MediaColumns.HEIGHT, HEIGHT);
        Uri uri = resolver.insert(COLLECTION, values);
        need(uri != null, "MEDIA_INSERT_RETURNED_NULL");
        commit(prefs.edit().putString("uri", uri.toString()).putString("pending", "write-owned-image")
                .putInt("write_calls", 1));
        ownedUri();
        try (OutputStream out = resolver.openOutputStream(uri, "w")) {
            need(out != null, "OWNED_OUTPUT_STREAM_REQUIRED"); out.write(payload); out.flush();
        }
        verify(true);
        live();
        commit(prefs.edit().putString("pending", "publish-owned-image").putInt("publish_calls", 1));
        values.clear(); values.put(MediaStore.MediaColumns.IS_PENDING, 0);
        need(resolver.update(uri, values, null, null) == 1, "ONE_OWNED_PUBLICATION_REQUIRED");
        JSONObject result = verify(false);
        commit(prefs.edit().putString("phase", "SEEDED").putString("pending", ""));
        return result;
    }

    JSONObject delete() throws Exception {
        live(); need("SEEDED".equals(phase()) && prefs.getString("pending", "").isEmpty(), "SEEDED_NO_PENDING_REQUIRED");
        JSONObject checked = verify(false); Uri uri = ownedUri();
        commit(prefs.edit().putString("phase", "DELETE_PENDING").putString("pending", "delete-owned-image")
                .putInt("delete_calls", 1));
        need(resolver.delete(uri, null, null) == 1, "ONE_EXACT_DELETE_REQUIRED");
        need(rowCount(uri, null, null) == 0
                && rowCount(COLLECTION, "relative_path=?", new String[] {RELATIVE}) == 0, "OWNED_MEDIA_NOT_ABSENT");
        commit(prefs.edit().putString("phase", "DELETED").putString("pending", ""));
        return checked.put("row_absence_verified", true);
    }

    @Override public void onStart() {
        JSONObject result = new JSONObject(); int code = 1;
        try {
            context = getTargetContext(); resolver = context.getContentResolver();
            need(PACKAGE.equals(context.getPackageName()) && RUN.equals(arguments.getString("run")), "EXACT_RUN_ARGUMENT_REQUIRED");
            prefs = context.getSharedPreferences("owned-media-" + RUN, Context.MODE_PRIVATE);
            String operation = arguments.getString("op", "");
            result.put("schema", "p4-owned-media-fixture-v1").put("run", RUN).put("package", PACKAGE)
                    .put("uid", Process.myUid()).put("pid", Process.myPid()).put("operation", operation);
            if ("seed".equals(operation)) result.put("image", seed());
            else if ("verify".equals(operation)) {
                live(); need("SEEDED".equals(phase()) && prefs.getString("pending", "").isEmpty(), "SEEDED_NO_PENDING_REQUIRED");
                result.put("image", verify(false));
            } else if ("delete".equals(operation)) result.put("image", delete());
            else if ("inspect".equals(operation)) {
                // This operation does not initialize or clear a record and never changes a pending effect.
                if (!prefs.getString("uri", "").isEmpty()) result.put("owned_row_count", rowCount(ownedUri(), null, null));
            } else throw new IllegalArgumentException("OPERATION_NOT_ALLOWED");
            result.put("ok", true); code = 0;
        } catch (Throwable error) {
            try { result.put("ok", false).put("error", error.getClass().getSimpleName() + ":" + error.getMessage()); }
            catch (Exception ignored) { }
        } finally {
            try {
                if (prefs != null) result.put("phase", phase()).put("pending", prefs.getString("pending", ""))
                        .put("uri", prefs.getString("uri", "")).put("insert_calls", prefs.getInt("insert_calls", 0))
                        .put("write_calls", prefs.getInt("write_calls", 0)).put("publish_calls", prefs.getInt("publish_calls", 0))
                        .put("delete_calls", prefs.getInt("delete_calls", 0));
            } catch (Exception ignored) { }
            Bundle output = new Bundle(); output.putString("result_json", result.toString()); finish(code, output);
        }
    }
}
