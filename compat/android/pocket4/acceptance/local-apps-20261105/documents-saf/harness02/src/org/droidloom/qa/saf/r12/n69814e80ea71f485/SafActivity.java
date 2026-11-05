package org.droidloom.qa.saf.r12.n69814e80ea71f485;

import android.app.Activity;
import android.content.ComponentName;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.UriPermission;
import android.database.Cursor;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Bundle;
import android.provider.DocumentsContract;
import android.provider.DocumentsContract.Document;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import org.json.JSONObject;

/** A single-run SAF client. No storage/network permissions, broad grants, or reset. */
public final class SafActivity extends Activity {
    static final String RUN = "69814e80ea71f485";
    static final String AUTHORITY = "com.android.externalstorage.documents";
    static final String FOLDER = "Pocket4_SAF_r12_" + RUN;
    static final String CREATED = "created-" + RUN + ".txt";
    static final String PROVIDER = "provider-" + RUN + ".txt";
    static final String FILES = "files-ui-" + RUN + ".txt";
    static final byte[] PAYLOAD = ("Pocket4 SAF fixture " + RUN
            + "\n中文 café 😀 — ContentResolver round trip.\n").getBytes(StandardCharsets.UTF_8);
    static final String SHA = "5e8ee8b6e154ade076e1f62e1ff0bc206ae69ba41982ac1c7a048c303f0503e7";
    static final int CREATE = 41, OPEN = 42, RW = Intent.FLAG_GRANT_READ_URI_PERMISSION
            | Intent.FLAG_GRANT_WRITE_URI_PERMISSION;
    SharedPreferences prefs;
    TextView status;
    Button create, rename, files, open, delete;

    interface Checked { void run() throws Exception; }

    static void need(boolean value, String reason) {
        if (!value) throw new IllegalStateException(reason);
    }

    static Uri uri(String name) {
        return DocumentsContract.buildDocumentUri(AUTHORITY,
                "primary:" + FOLDER + (name.isEmpty() ? "" : "/" + name));
    }

    static void exact(Uri value, String name) {
        need(value != null && value.equals(uri(name)) && value.getQuery() == null
                && value.getFragment() == null && !DocumentsContract.isTreeUri(value),
                "OWNED_EXACT_DOCUMENT_URI_REQUIRED");
    }

    static void singleDocument(Intent intent, String name) {
        exact(intent.getData(), name);
        if (intent.getClipData() != null) {
            need(intent.getClipData().getItemCount() == 1, "SINGLE_DOCUMENT_CLIP_REQUIRED");
            android.content.ClipData.Item item = intent.getClipData().getItemAt(0);
            exact(item.getUri(), name);
            need(item.getIntent() == null && item.getText() == null && item.getHtmlText() == null,
                    "URI_ONLY_CLIP_REQUIRED");
        }
    }

    static String digest(byte[] raw) throws Exception {
        StringBuilder out = new StringBuilder();
        for (byte b : MessageDigest.getInstance("SHA-256").digest(raw))
            out.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
        return out.toString();
    }

    String phase() { return prefs.getString("phase", "NEW"); }

    void commit(SharedPreferences.Editor editor) {
        need(editor.commit(), "DURABLE_OWNED_STATE_WRITE_FAILED");
    }

    void count(String name) {
        commit(prefs.edit().putInt(name, prefs.getInt(name, 0) + 1));
    }

    void begin(String expected, String pending, String counter) {
        need(phase().equals(expected), "PHASE_REQUIRED:" + expected);
        need(prefs.getString("pending", "").isEmpty(), "PENDING_EFFECT_NOT_REPLAYABLE");
        need(System.currentTimeMillis() - prefs.getLong("started_ms", 0) < 1200000,
                "OWNED_RUN_LEASE_EXPIRED");
        commit(prefs.edit().putString("phase", pending).putString("pending", pending)
                .putInt(counter, prefs.getInt(counter, 0) + 1));
    }

    void complete(String value, Uri document) {
        SharedPreferences.Editor editor = prefs.edit().putString("phase", value)
                .putString("pending", "").putString("error", "");
        if (document != null) editor.putString("uri", document.toString());
        commit(editor);
    }

    void fail(Exception error) {
        commit(prefs.edit().putString("phase", "FAILED")
                .putString("error", error.getClass().getSimpleName() + ":" + error.getMessage()));
        render();
    }

    void action(Checked operation) {
        try { operation.run(); render(); } catch (Exception error) { fail(error); }
    }

    Button button(LinearLayout layout, int id, String title, Checked operation) {
        Button button = new Button(this);
        button.setId(id); button.setText(title); button.setAllCaps(false);
        button.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View view) { action(operation); }
        });
        layout.addView(button, new LinearLayout.LayoutParams(-1, -2));
        return button;
    }

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        prefs = getSharedPreferences("owned-saf-" + RUN, MODE_PRIVATE);
        if (!prefs.contains("run")) {
            need(prefs.getAll().isEmpty(), "NEW_PACKAGE_OWNED_STATE_NOT_EMPTY");
            commit(prefs.edit().putString("run", RUN).putString("phase", "NEW")
                    .putLong("started_ms", System.currentTimeMillis()));
        }
        need(RUN.equals(prefs.getString("run", "")), "OWNED_RUN_CHANGED");
        ScrollView scroll = new ScrollView(this);
        LinearLayout layout = new LinearLayout(this); layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(18, 12, 18, 12); scroll.addView(layout); setContentView(scroll);
        status = new TextView(this); status.setId(R.id.status); status.setTextSize(13);
        status.setTypeface(Typeface.MONOSPACE); layout.addView(status);
        create = button(layout, R.id.create_document, "Create owned document", new Checked() { public void run() throws Exception { createDocument(); } });
        rename = button(layout, R.id.provider_rename, "Rename through provider", new Checked() { public void run() throws Exception { providerRename(); } });
        files = button(layout, R.id.open_files, "Open owned folder in Files", new Checked() { public void run() throws Exception { openFiles(); } });
        open = button(layout, R.id.open_document, "Select owned document", new Checked() { public void run() throws Exception { openDocument(); } });
        delete = button(layout, R.id.provider_delete, "Delete owned document", new Checked() { public void run() throws Exception { providerDelete(); } });
        if (Intent.ACTION_VIEW.equals(getIntent().getAction())) {
            action(new Checked() { public void run() throws Exception { acceptFilesView(getIntent()); } });
        } else if (phase().equals("OPEN_OK")) {
            action(new Checked() { public void run() throws Exception {
                Uri document = Uri.parse(prefs.getString("uri", "")); exact(document, FILES);
                need(hasPersisted(document), "PERSISTED_EXACT_READ_WRITE_GRANT_REQUIRED");
                verify(document, FILES); count("reopen_reads"); complete("REOPEN_OK", document);
            } });
        }
        render();
    }

    @Override public void onNewIntent(Intent intent) {
        super.onNewIntent(intent); setIntent(intent);
        if (Intent.ACTION_VIEW.equals(intent.getAction())) action(new Checked() { public void run() throws Exception { acceptFilesView(intent); } });
        else render();
    }

    Intent picker(String action) {
        Intent intent = new Intent(action).addCategory(Intent.CATEGORY_OPENABLE)
                .setType("text/plain").setComponent(new ComponentName("com.android.documentsui",
                        "com.android.documentsui.picker.PickActivity"));
        intent.addFlags(RW | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        intent.putExtra(DocumentsContract.EXTRA_INITIAL_URI, uri(""));
        return intent;
    }

    void createDocument() {
        begin("NEW", "CREATE_REQUESTED", "create_picker_calls");
        Intent intent = picker(Intent.ACTION_CREATE_DOCUMENT);
        intent.putExtra(Intent.EXTRA_TITLE, CREATED);
        startActivityForResult(intent, CREATE);
    }

    void openDocument() {
        begin("FILES_VIEW_OK", "OPEN_REQUESTED", "open_picker_calls");
        startActivityForResult(picker(Intent.ACTION_OPEN_DOCUMENT), OPEN);
    }

    void persist(Uri value, int returnedFlags) {
        need((returnedFlags & RW) == RW
                && (returnedFlags & Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION) != 0,
                "RETURNED_PERSISTABLE_READ_WRITE_FLAGS_REQUIRED");
        getContentResolver().takePersistableUriPermission(value, RW);
        need(hasPersisted(value), "EXACT_GRANT_NOT_PERSISTED");
    }

    boolean hasPersisted(Uri value) {
        int count = 0;
        for (UriPermission grant : getContentResolver().getPersistedUriPermissions()) {
            if (grant.getUri().equals(value) && grant.isReadPermission() && grant.isWritePermission()) count++;
        }
        return count == 1;
    }

    long metadata(Uri value, String name) {
        exact(value, name);
        String[] projection = {Document.COLUMN_DOCUMENT_ID, Document.COLUMN_DISPLAY_NAME,
                Document.COLUMN_MIME_TYPE, Document.COLUMN_SIZE, Document.COLUMN_FLAGS};
        try (Cursor cursor = getContentResolver().query(value, projection, null, null, null)) {
            need(cursor != null && cursor.moveToFirst() && cursor.getCount() == 1,
                    "ONE_OWNED_DOCUMENT_ROW_REQUIRED");
            need(("primary:" + FOLDER + "/" + name).equals(cursor.getString(0))
                    && name.equals(cursor.getString(1)) && "text/plain".equals(cursor.getString(2))
                    && !cursor.isNull(3), "EXACT_OWNED_DOCUMENT_METADATA_REQUIRED");
            long size = cursor.getLong(3);
            need(size >= 0 && size <= 1024, "OWNED_DOCUMENT_SIZE_BOUND");
            commit(prefs.edit().putInt("document_flags", cursor.getInt(4)));
            return size;
        }
    }

    void verify(Uri value, String name) throws Exception {
        need(metadata(value, name) == PAYLOAD.length, "EXACT_PAYLOAD_LENGTH_REQUIRED");
        ByteArrayOutputStream data = new ByteArrayOutputStream();
        try (InputStream stream = getContentResolver().openInputStream(value)) {
            need(stream != null, "OWNED_DOCUMENT_INPUT_REQUIRED");
            byte[] buffer = new byte[256]; int read;
            while ((read = stream.read(buffer)) != -1) {
                need(data.size() + read <= 1024, "OWNED_READ_BOUND"); data.write(buffer, 0, read);
            }
        }
        byte[] actual = data.toByteArray();
        need(Arrays.equals(actual, PAYLOAD) && digest(actual).equals(SHA), "OWNED_CONTENT_HASH_MISMATCH");
        commit(prefs.edit().putString("readback_sha256", digest(actual)).putInt("readback_bytes", actual.length));
        count("content_readbacks");
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        action(new Checked() { public void run() throws Exception {
            need((request == CREATE && phase().equals("CREATE_REQUESTED"))
                    || (request == OPEN && phase().equals("OPEN_REQUESTED")), "UNEXPECTED_PICKER_RESULT");
            need(result == RESULT_OK && data != null,
                    "ONE_SUCCESSFUL_PICKER_RESULT_REQUIRED");
            Uri value = data.getData();
            String name = request == CREATE ? CREATED : FILES;
            singleDocument(data, name); // Validate before ANY provider query, read, write, or grant.
            commit(prefs.edit().putString("uri", value.toString()).putInt("returned_flags", data.getFlags()));
            persist(value, data.getFlags());
            if (request == CREATE) {
                need(metadata(value, CREATED) == 0, "NEW_EMPTY_CREATED_DOCUMENT_REQUIRED");
                need(prefs.getInt("content_writes", 0) == 0, "CONTENT_WRITE_NOT_REPLAYABLE");
                count("content_writes");
                try (OutputStream stream = getContentResolver().openOutputStream(value, "w")) {
                    need(stream != null, "OWNED_DOCUMENT_OUTPUT_REQUIRED");
                    stream.write(PAYLOAD); stream.flush();
                }
                verify(value, CREATED); complete("CREATE_WRITE_READ_OK", value);
            } else {
                verify(value, FILES); complete("OPEN_OK", value);
            }
        } });
    }

    void providerRename() throws Exception {
        Uri before = Uri.parse(prefs.getString("uri", "")); exact(before, CREATED);
        verify(before, CREATED);
        need((prefs.getInt("document_flags", 0) & Document.FLAG_SUPPORTS_RENAME) != 0,
                "PROVIDER_RENAME_CAPABILITY_REQUIRED");
        begin("CREATE_WRITE_READ_OK", "PROVIDER_RENAME_PENDING", "provider_rename_calls");
        Uri after = DocumentsContract.renameDocument(getContentResolver(), before, PROVIDER);
        exact(after, PROVIDER);
        commit(prefs.edit().putString("uri", after.toString()));
        verify(after, PROVIDER); complete("PROVIDER_RENAME_OK", after);
    }

    void openFiles() {
        begin("PROVIDER_RENAME_OK", "FILES_REQUESTED", "files_launch_calls");
        Intent intent = new Intent(Intent.ACTION_VIEW).setDataAndType(uri(""), Document.MIME_TYPE_DIR)
                .setComponent(new ComponentName("com.android.documentsui",
                        "com.android.documentsui.files.FilesActivity"));
        // Files already has MANAGE_DOCUMENTS; do not invent a broad URI grant.
        startActivity(intent);
    }

    void acceptFilesView(Intent intent) throws Exception {
        need(phase().equals("FILES_REQUESTED") && Intent.ACTION_VIEW.equals(intent.getAction()),
                "FILES_OPEN_PHASE_REQUIRED");
        need("text/plain".equals(intent.getType()),
                "ONE_PLAIN_TEXT_VIEW_REQUIRED");
        Uri value = intent.getData(); singleDocument(intent, FILES);
        need((intent.getFlags() & Intent.FLAG_GRANT_READ_URI_PERMISSION) != 0,
                "FILES_VIEW_READ_GRANT_REQUIRED");
        verify(value, FILES); count("files_view_results"); complete("FILES_VIEW_OK", value);
    }

    void providerDelete() throws Exception {
        Uri value = Uri.parse(prefs.getString("uri", "")); exact(value, FILES);
        need(hasPersisted(value), "EXACT_PERSISTED_GRANT_BEFORE_DELETE_REQUIRED");
        verify(value, FILES);
        need((prefs.getInt("document_flags", 0) & Document.FLAG_SUPPORTS_DELETE) != 0,
                "PROVIDER_DELETE_CAPABILITY_REQUIRED");
        begin("REOPEN_OK", "PROVIDER_DELETE_PENDING", "provider_delete_calls");
        need(DocumentsContract.deleteDocument(getContentResolver(), value), "PROVIDER_DELETE_NOT_ACKNOWLEDGED");
        // Revoked access is not evidence of absence. Runner must verify exact filesystem ENOENT.
        complete("DELETE_PROVIDER_ACK", value);
    }

    void render() {
        if (status == null) return;
        try {
            JSONObject value = new JSONObject(); value.put("run", RUN); value.put("phase", phase());
            value.put("pending", prefs.getString("pending", ""));
            value.put("uri", prefs.getString("uri", ""));
            value.put("sha256", prefs.getString("readback_sha256", ""));
            value.put("bytes", prefs.getInt("readback_bytes", 0));
            for (String key : new String[]{"create_picker_calls", "content_writes", "provider_rename_calls",
                    "files_launch_calls", "files_view_results", "open_picker_calls", "reopen_reads",
                    "provider_delete_calls", "content_readbacks"}) value.put(key, prefs.getInt(key, 0));
            value.put("error", prefs.getString("error", ""));
            status.setText(value.toString());
            create.setEnabled(phase().equals("NEW"));
            rename.setEnabled(phase().equals("CREATE_WRITE_READ_OK"));
            files.setEnabled(phase().equals("PROVIDER_RENAME_OK"));
            open.setEnabled(phase().equals("FILES_VIEW_OK"));
            delete.setEnabled(phase().equals("REOPEN_OK"));
        } catch (Exception error) { throw new IllegalStateException(error); }
    }
}
