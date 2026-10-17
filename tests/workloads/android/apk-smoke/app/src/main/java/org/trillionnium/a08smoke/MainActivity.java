package org.trillionnium.a08smoke;

import android.app.Activity;
import android.os.Bundle;
import android.view.View;
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
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(32, 64, 32, 32);
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
        refresh();
    }
}
