package org.droidloom.qa.galleryrotation.r12.nd24b61ed8f7c9a03;

import android.app.Activity;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Only an explicit button opens the sole verified owned JPEG album. */
public final class RotationActivity extends Activity {
    RotationStore store;
    TextView status;
    Button open;
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        LinearLayout body=new LinearLayout(this);body.setOrientation(LinearLayout.VERTICAL);body.setPadding(24,24,24,24);
        status=new TextView(this);status.setId(R.id.status);body.addView(status);
        open=new Button(this);open.setId(R.id.open_owned_album);open.setText("Open owned JPEG album");body.addView(open);
        setContentView(body);open.setEnabled(false);
        try {
            store=new RotationStore(this);store.live();status.setText(store.status().toString());
            boolean first="SEEDED".equals(store.phase()) && store.prefs.getInt("gallery_launches",0)==0;
            boolean second="ROTATED_VERIFIED".equals(store.phase()) && store.prefs.getInt("gallery_launches",0)==1;
            open.setEnabled(store.pending().isEmpty() && (first || second));
        } catch(Exception error) { status.setText("Owned fixture unavailable: "+error.getClass().getSimpleName()); }
        open.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View view) {
            open.setEnabled(false);
            try { startActivity(store.prepareAlbumLaunch());status.setText(store.status().toString()); }
            catch(Exception error) {
                // A launch failure may be post-dispatch; retain its durable
                // pending record and never enable a second button decision.
                status.setText("Owned album request unconfirmed: "+error.getClass().getSimpleName());
            }
            }
        });
    }
}
