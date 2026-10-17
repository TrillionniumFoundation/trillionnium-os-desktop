package org.trillionnium.a08native;

import android.app.Activity;
import android.os.Build;
import android.os.Bundle;
import android.os.Process;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

public final class MainActivity extends Activity {
    static { System.loadLibrary("a08jni"); }
    private static native String nativeIsa();
    private static native long nativePid();
    private static final String PREFS = "a08-native-smoke";
    private TextView saved;

    private void refresh() {
        String value = getSharedPreferences(PREFS, MODE_PRIVATE).getString("value", "EMPTY");
        saved.setText("SAVED:" + value);
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        // Do not print success unless the actual x86_64 .so was loaded and JNI
        // executed in this process. A missing/wrong ISA .so must fail launch.
        if (!"x86_64".equals(nativeIsa()) || nativePid() != Process.myPid() ||
            Build.SUPPORTED_64_BIT_ABIS.length == 0 ||
            !"x86_64".equals(Build.SUPPORTED_64_BIT_ABIS[0])) {
            throw new IllegalStateException("JNI native ABI/process verification failed");
        }
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(32, 64, 32, 32);
        TextView nativeStatus = new TextView(this);
        nativeStatus.setId(R.id.native_status);
        nativeStatus.setText("JNI:x86_64:PID_MATCH");
        root.addView(nativeStatus);
        saved = new TextView(this);
        saved.setId(R.id.saved_value);
        root.addView(saved);
        EditText input = new EditText(this);
        input.setId(R.id.input_value);
        input.setSingleLine(true);
        input.setHint("Native APK persistent text");
        root.addView(input);
        Button button = new Button(this);
        button.setId(R.id.save_button);
        button.setText("SAVE");
        button.setOnClickListener((View v) -> {
            boolean written = getSharedPreferences(PREFS, MODE_PRIVATE).edit()
                .putString("value", input.getText().toString()).commit();
            if (!written) throw new IllegalStateException("Native APK storage commit failed");
            refresh();
        });
        root.addView(button);
        setContentView(root);
        refresh();
    }
}
