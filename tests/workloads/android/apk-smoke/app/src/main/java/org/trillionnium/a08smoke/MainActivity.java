package org.trillionnium.a08smoke;

import android.app.Activity;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

public final class MainActivity extends Activity {
    private static final String PREFS = "a08smoke";
    private TextView saved;

    private void refresh() {
        String value = getSharedPreferences(PREFS, MODE_PRIVATE).getString("value", "EMPTY");
        saved.setText("SAVED:" + value);
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        if (Build.VERSION.SDK_INT >= 30) {
            getWindow().setDecorFitsSystemWindows(false);
        } else {
            getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
        }
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        final int padding = Math.round(16 * getResources().getDisplayMetrics().density);
        root.setPadding(padding, padding, padding, padding);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            int left, top, right, bottom;
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets bars = insets.getInsets(
                    WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                left = bars.left; top = bars.top; right = bars.right; bottom = bars.bottom;
            } else {
                left = insets.getSystemWindowInsetLeft(); top = insets.getSystemWindowInsetTop();
                right = insets.getSystemWindowInsetRight(); bottom = insets.getSystemWindowInsetBottom();
            }
            view.setPadding(padding + left, padding + top, padding + right, padding + bottom);
            return insets;
        });
        saved = new TextView(this);
        saved.setId(R.id.saved_value);
        root.addView(saved);
        EditText input = new EditText(this);
        input.setId(R.id.input_value);
        input.setSingleLine(true);
        input.setHint("Type persisted text");
        root.addView(input);
        Button button = new Button(this);
        button.setId(R.id.save_button);
        button.setText("SAVE");
        button.setOnClickListener((View v) -> {
            boolean committed = getSharedPreferences(PREFS, MODE_PRIVATE)
                .edit().putString("value", input.getText().toString()).commit();
            if (!committed) throw new IllegalStateException("SharedPreferences commit failed");
            refresh();
        });
        root.addView(button);
        setContentView(root);
        root.requestApplyInsets();
        refresh();
    }
}
