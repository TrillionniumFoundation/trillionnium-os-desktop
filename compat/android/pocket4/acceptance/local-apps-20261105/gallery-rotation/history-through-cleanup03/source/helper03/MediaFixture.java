package org.droidloom.qa.galleryrotation.r12.nd24b61ed8f7c9a03;

import android.app.Instrumentation;
import android.os.Bundle;
import android.os.Process;
import org.json.JSONObject;

/** Run only with all owned helper/Gallery tasks closed; controller enforces that boundary. */
public final class MediaFixture extends Instrumentation {
    Bundle arguments;
    @Override public void onCreate(Bundle values) {
        super.onCreate(values);arguments=values==null?new Bundle():values;start();
    }
    @Override public void onStart() {
        JSONObject result=new JSONObject();RotationStore store=null;int code=1;
        try {
            RotationStore.need(RotationStore.RUN.equals(arguments.getString("run")),"EXACT_RUN_REQUIRED");
            store=new RotationStore(getTargetContext());String operation=arguments.getString("op","");
            result.put("schema","owned-gallery-rotation-fixture-v1").put("run",RotationStore.RUN)
                .put("package",RotationStore.PACKAGE).put("uid",Process.myUid()).put("pid",Process.myPid())
                .put("operation",operation).put("Gallery_UI_success_claimed",false);
            if("seed".equals(operation))result.put("media",store.seed());
            else if("verify-original".equals(operation))result.put("media",store.verify(false));
            else if("verify-clockwise".equals(operation))result.put("media",store.verify(true));
            else if("seal-first-unchanged".equals(operation))result.put("media",store.seal(1,false));
            else if("seal-first-clockwise".equals(operation))result.put("media",store.seal(1,true));
            else if("seal-reopen-clockwise".equals(operation))result.put("media",store.seal(2,true));
            else if("delete".equals(operation))result.put("media",store.delete());
            else RotationStore.need("inspect".equals(operation),"OPERATION_NOT_ALLOWED");
            result.put("ok",true);code=0;
        } catch(Throwable error) {
            try { result.put("ok",false).put("error_type",error.getClass().getSimpleName()).put("error",error.getMessage()); }
            catch(Exception ignored) { }
        } finally {
            try { if(store!=null)result.put("status",store.status()); }catch(Exception ignored) { }
            Bundle out=new Bundle();out.putString("result_json",result.toString());finish(code,out);
        }
    }
}
