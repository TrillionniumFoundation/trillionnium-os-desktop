package org.droidloom.qa.documents.r12.n98116f3fbefcfc95;

import android.app.Activity;
import android.content.ComponentName;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.UriPermission;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Bundle;
import android.os.Process;
import android.os.SystemClock;
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
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import org.json.JSONArray;
import org.json.JSONObject;

/** Exact generated tree fixture. No broad storage permission or provider delete API. */
public final class FeaturesActivity extends Activity {
    static final String RUN="98116f3fbefcfc95";
    static final String AUTHORITY="com.android.externalstorage.documents";
    static final String FOLDER="Pocket4_DocFeatures_r12_"+RUN;
    static final String SOURCE="source-"+RUN, COPIES="copies-"+RUN;
    static final String ALPHA="alpha-"+RUN+".txt", BETA="beta-"+RUN+".txt";
    static final byte[] A=("Pocket4 Documents "+RUN+" alpha\n中文 café 😀\n").getBytes(StandardCharsets.UTF_8);
    static final byte[] B=("Pocket4 Documents "+RUN+" beta\n中文 café 😀\nTwo generated payloads distinguish a correct copy and move.\n").getBytes(StandardCharsets.UTF_8);
    static final int RW=Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION;
    static final int GET_CANCEL=51,TREE_CANCEL=52,TREE_GRANT=53,GET_ACCEPT=54;
    static final long LEASE_MS=1200000L;
    SharedPreferences prefs;TextView status;final ArrayList<Button> buttons=new ArrayList<>();
    interface Checked {void run() throws Exception;}
    static void need(boolean ok,String message){if(!ok)throw new IllegalStateException(message);}
    static String id(String relative){return "primary:"+FOLDER+(relative.isEmpty()?"":"/"+relative);}
    static Uri plain(String relative){return DocumentsContract.buildDocumentUri(AUTHORITY,id(relative));}
    static Uri tree(){return DocumentsContract.buildTreeDocumentUri(AUTHORITY,id(""));}
    static boolean allowed(String relative){return Arrays.asList("",SOURCE,COPIES,ALPHA,BETA,
        SOURCE+"/"+ALPHA,SOURCE+"/"+BETA,COPIES+"/"+ALPHA,COPIES+"/"+BETA).contains(relative);}
    static Uri document(String relative){need(allowed(relative),"NON_FIXTURE_RELATIVE_PATH");return DocumentsContract.buildDocumentUriUsingTree(tree(),id(relative));}
    static void exactTree(Uri value){need(value!=null&&value.equals(tree())&&value.getQuery()==null&&value.getFragment()==null,
        "ONLY_EXACT_OWNED_TREE_ROOT_ALLOWED");}
    static void exactDocument(Uri value,String relative){need(allowed(relative)&&value!=null&&value.equals(document(relative))
        &&value.getQuery()==null&&value.getFragment()==null,"ONLY_EXACT_OWNED_TREE_DOCUMENT_ALLOWED");}
    static void singleResult(Intent data,Uri value){
        need(data!=null&&value!=null&&value.equals(data.getData()),"ONE_RESULT_URI_REQUIRED");
        if(data.getClipData()!=null){need(data.getClipData().getItemCount()==1,"ONE_RESULT_CLIP_REQUIRED");
            android.content.ClipData.Item item=data.getClipData().getItemAt(0);
            need(value.equals(item.getUri())&&item.getIntent()==null&&item.getText()==null&&item.getHtmlText()==null,
                "ONE_URI_ONLY_CLIP_REQUIRED");}
    }
    static String sha(byte[] raw)throws Exception{StringBuilder out=new StringBuilder();for(byte x:MessageDigest.getInstance("SHA-256").digest(raw))out.append(String.format(java.util.Locale.ROOT,"%02x",x&255));return out.toString();}
    String phase(){return prefs.getString("phase","NEW");}
    void commit(SharedPreferences.Editor editor){need(editor.commit(),"DURABLE_STATE_COMMIT_FAILED");}
    void count(String key){commit(prefs.edit().putInt(key,prefs.getInt(key,0)+1));}
    void lease(){long start=prefs.getLong("started_elapsed_ms",-1),now=SystemClock.elapsedRealtime();
        need(start>=0&&now>=start&&now-start<LEASE_MS,"OWNED_LEASE_EXPIRED_OR_BOOT_CHANGED");}
    void begin(String expected,String pending,String counter){lease();need(phase().equals(expected),"EXPECTED_PHASE:"+expected);
        need(prefs.getString("pending","").isEmpty()&&prefs.getString("step_pending","").isEmpty(),"UNKNOWN_EFFECT_CANNOT_REPLAY");
        commit(prefs.edit().putString("phase",pending).putString("pending",pending).putInt(counter,prefs.getInt(counter,0)+1));}
    void step(String label,String counter){need(prefs.getString("step_pending","").isEmpty(),"PROVIDER_STEP_PENDING_NO_REPLAY");
        commit(prefs.edit().putString("step_pending",label).putInt(counter,prefs.getInt(counter,0)+1));}
    void stepDone(){commit(prefs.edit().putString("step_pending",""));}
    void complete(String next){commit(prefs.edit().putString("phase",next).putString("pending","").putString("step_pending","").putString("error",""));}
    void action(Checked work){try{work.run();}catch(Exception error){commit(prefs.edit().putString("phase","FAILED").putString("error",error.getClass().getSimpleName()+":"+error.getMessage()));}render();}
    Button button(LinearLayout layout,int rid,String label,String expected,Checked work){Button b=new Button(this);b.setId(rid);b.setText(label);b.setAllCaps(false);b.setTag(expected);b.setOnClickListener(new View.OnClickListener(){@Override public void onClick(View v){action(work);}});layout.addView(b,new LinearLayout.LayoutParams(-1,-2));buttons.add(b);return b;}
    @Override public void onCreate(Bundle saved){super.onCreate(saved);prefs=getSharedPreferences("owned-features-"+RUN,MODE_PRIVATE);
        if(!prefs.contains("run")){need(prefs.getAll().isEmpty(),"INITIAL_STATE_NOT_EMPTY");need(getContentResolver().getPersistedUriPermissions().isEmpty(),"INITIAL_URI_GRANTS_NOT_EMPTY");
            commit(prefs.edit().putString("run",RUN).putString("phase","NEW").putLong("started_elapsed_ms",SystemClock.elapsedRealtime()));}
        need(RUN.equals(prefs.getString("run","")),"RUN_CHANGED");count("activity_creations");
        ScrollView scroll=new ScrollView(this);LinearLayout layout=new LinearLayout(this);layout.setOrientation(LinearLayout.VERTICAL);layout.setPadding(18,12,18,12);scroll.addView(layout);setContentView(scroll);
        status=new TextView(this);status.setId(R.id.status);status.setTextSize(13);status.setTypeface(Typeface.MONOSPACE);layout.addView(status);
        button(layout,R.id.cancel_get,"Cancel a GET_CONTENT picker","NEW",new Checked(){public void run() throws Exception {requestPicker(GET_CANCEL);}});
        button(layout,R.id.cancel_tree,"Cancel a tree picker","GET_CANCELLED",new Checked(){public void run() throws Exception {requestPicker(TREE_CANCEL);}});
        button(layout,R.id.grant_tree,"Select only the owned tree","TREE_CANCELLED",new Checked(){public void run() throws Exception {requestPicker(TREE_GRANT);}});
        button(layout,R.id.seed,"Create two fixture files through tree grant","TREE_GRANTED",new Checked(){public void run() throws Exception {seed();}});
        button(layout,R.id.files,"Open the owned Files scope","SEEDED",new Checked(){public void run() throws Exception {openFiles(false);}});
        button(layout,R.id.verify_files,"Verify copy move and UI delete results","FILES_OPENED",new Checked(){public void run() throws Exception {verifyFiles();}});
        button(layout,R.id.release_tree,"Release the owned persisted tree grant","FILES_VERIFIED",new Checked(){public void run() throws Exception {release();}});
        button(layout,R.id.probe_revoked,"Verify revoked owned-file access is denied","TREE_RELEASED",new Checked(){public void run() throws Exception {probeRevoked();}});
        button(layout,R.id.get_content,"Select the generated alpha through GET_CONTENT","DENIED_OBSERVED",new Checked(){public void run() throws Exception {requestPicker(GET_ACCEPT);}});
        button(layout,R.id.cleanup_files,"Open Files for exact UI cleanup","GET_CONTENT_OK",new Checked(){public void run() throws Exception {openFiles(true);}});
        render();}
    @Override public void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);render();}
    Intent picker(boolean wantTree){Intent i=new Intent(wantTree?Intent.ACTION_OPEN_DOCUMENT_TREE:Intent.ACTION_GET_CONTENT)
        .setComponent(new ComponentName("com.android.documentsui","com.android.documentsui.picker.PickActivity"));
        if(wantTree)i.addFlags(RW|Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION|Intent.FLAG_GRANT_PREFIX_URI_PERMISSION);
        else i.addCategory(Intent.CATEGORY_OPENABLE).setType("text/plain").putExtra(Intent.EXTRA_ALLOW_MULTIPLE,false).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        i.putExtra(DocumentsContract.EXTRA_INITIAL_URI,plain(""));return i;}
    void requestPicker(int request){String expected=request==GET_CANCEL?"NEW":request==TREE_CANCEL?"GET_CANCELLED":request==TREE_GRANT?"TREE_CANCELLED":"DENIED_OBSERVED";
        String pending=request==GET_CANCEL?"GET_CANCEL_PENDING":request==TREE_CANCEL?"TREE_CANCEL_PENDING":request==TREE_GRANT?"TREE_GRANT_PENDING":"GET_ACCEPT_PENDING";
        begin(expected,pending,"picker_calls");commit(prefs.edit().putInt("pending_request",request));startActivityForResult(picker(request==TREE_CANCEL||request==TREE_GRANT),request);}
    void onlyTreeGrant(){List<UriPermission> grants=getContentResolver().getPersistedUriPermissions();need(grants.size()==1,"EXACTLY_ONE_PERSISTED_GRANT_REQUIRED");UriPermission g=grants.get(0);exactTree(g.getUri());need(g.isReadPermission()&&g.isWritePermission(),"TREE_READ_WRITE_GRANT_REQUIRED");}
    @Override protected void onActivityResult(int request,int result,Intent data){super.onActivityResult(request,result,data);action(new Checked(){public void run() throws Exception {
        lease();need(prefs.getInt("pending_request",-1)==request&&!prefs.getString("pending","").isEmpty(),"UNEXPECTED_PICKER_RESULT");
        if(request==GET_CANCEL||request==TREE_CANCEL){need(result==RESULT_CANCELED&&(data==null||(data.getData()==null&&data.getClipData()==null)),"CANCEL_MUST_RETURN_NO_URI");
            need(getContentResolver().getPersistedUriPermissions().isEmpty(),"CANCEL_CREATED_PERSISTED_GRANT");count(request==GET_CANCEL?"get_cancel_results":"tree_cancel_results");complete(request==GET_CANCEL?"GET_CANCELLED":"TREE_CANCELLED");return;}
        need(result==RESULT_OK&&data!=null,"SUCCESSFUL_SINGLE_PICKER_RESULT_REQUIRED");Uri value=data.getData();singleResult(data,value);
        if(request==TREE_GRANT){need(phase().equals("TREE_GRANT_PENDING"),"TREE_RESULT_PHASE");exactTree(value);need((data.getFlags()&RW)==RW&&(data.getFlags()&Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)!=0,"TREE_RETURNED_FLAGS_REQUIRED");
            step("take-exact-tree-grant","persist_calls");getContentResolver().takePersistableUriPermission(value,RW);onlyTreeGrant();stepDone();need(children("").isEmpty(),"OWNED_TREE_NOT_EMPTY");count("tree_grant_results");complete("TREE_GRANTED");}
        else {need(request==GET_ACCEPT&&phase().equals("GET_ACCEPT_PENDING"),"GET_RESULT_PHASE");need(value.equals(plain(ALPHA)),"GET_CONTENT_EXACT_ALPHA_URI_REQUIRED");
            need((data.getFlags()&Intent.FLAG_GRANT_READ_URI_PERMISSION)!=0,"GET_CONTENT_READ_FLAG_REQUIRED");need(getContentResolver().getPersistedUriPermissions().isEmpty(),"GET_CONTENT_MUST_NOT_PERSIST_GRANT");
            verify(value,ALPHA,A,false);count("get_content_results");complete("GET_CONTENT_OK");}
    }});}
    List<String> children(String relative){need(Arrays.asList("",SOURCE,COPIES).contains(relative),"ONLY_THREE_OWNED_DIRECTORIES");onlyTreeGrant();
        Uri uri=DocumentsContract.buildChildDocumentsUriUsingTree(tree(),id(relative));ArrayList<String> result=new ArrayList<>();
        String[] projection={Document.COLUMN_DOCUMENT_ID,Document.COLUMN_DISPLAY_NAME,Document.COLUMN_MIME_TYPE,Document.COLUMN_SIZE};
        try(Cursor c=getContentResolver().query(uri,projection,null,null,null)){need(c!=null&&c.getCount()<=4,"CHILD_QUERY_BOUND");while(c.moveToNext()){
            String name=c.getString(1),child=relative.isEmpty()?name:relative+"/"+name;need(allowed(child)&&id(child).equals(c.getString(0)),"UNEXPECTED_CHILD_PRESERVE_SCOPE");
            boolean directory=child.equals(SOURCE)||child.equals(COPIES);need((directory?Document.MIME_TYPE_DIR:"text/plain").equals(c.getString(2)),"OWNED_CHILD_TYPE_CHANGED");
            need(!result.contains(name),"DUPLICATE_CHILD_NAME");result.add(name);}}
        Collections.sort(result);return result;}
    void metadata(Uri value,String relative,int expectedSize,boolean asTree){if(asTree)exactDocument(value,relative);else need(value.equals(plain(relative)),"EXACT_PLAIN_URI_REQUIRED");
        try(Cursor c=getContentResolver().query(value,new String[]{Document.COLUMN_DOCUMENT_ID,Document.COLUMN_DISPLAY_NAME,Document.COLUMN_MIME_TYPE,Document.COLUMN_SIZE},null,null,null)){
            need(c!=null&&c.getCount()==1&&c.moveToFirst(),"ONE_OWNED_FILE_ROW_REQUIRED");String name=relative.substring(relative.lastIndexOf('/')+1);
            need(id(relative).equals(c.getString(0))&&name.equals(c.getString(1))&&"text/plain".equals(c.getString(2))&&!c.isNull(3)&&c.getLong(3)==expectedSize,"OWNED_METADATA_CHANGED");}}
    void verify(Uri value,String relative,byte[] expected,boolean asTree)throws Exception{metadata(value,relative,expected.length,asTree);ByteArrayOutputStream all=new ByteArrayOutputStream();
        try(InputStream in=getContentResolver().openInputStream(value)){need(in!=null,"OWNED_STREAM_MISSING");byte[] buffer=new byte[256];int n;while((n=in.read(buffer))!=-1){need(all.size()+n<=1024,"OWNED_READ_BOUND");all.write(buffer,0,n);}}
        need(Arrays.equals(all.toByteArray(),expected),"OWNED_PAYLOAD_MISMATCH");commit(prefs.edit().putString("last_read_sha256",sha(all.toByteArray())).putInt("last_read_bytes",all.size()));count("content_readbacks");}
    void seedOne(String name,byte[] payload)throws Exception{String rel=SOURCE+"/"+name;step("create:"+rel,"provider_create_calls");
        Uri created=DocumentsContract.createDocument(getContentResolver(),document(SOURCE),"text/plain",name);exactDocument(created,rel);metadata(created,rel,0,true);stepDone();
        step("write:"+rel,"content_writes");try(OutputStream out=getContentResolver().openOutputStream(created,"w")){need(out!=null,"OWNED_OUTPUT_MISSING");out.write(payload);out.flush();}
        verify(created,rel,payload,true);stepDone();}
    void seed()throws Exception{onlyTreeGrant();need(children("").isEmpty()&&prefs.getInt("provider_create_calls",0)==0&&prefs.getInt("content_writes",0)==0,"SEED_ONCE_IN_EMPTY_OWNED_TREE_ONLY");
        begin("TREE_GRANTED","SEED_PENDING","seed_calls");step("create:"+SOURCE,"provider_create_calls");
        Uri created=DocumentsContract.createDocument(getContentResolver(),document(""),Document.MIME_TYPE_DIR,SOURCE);exactDocument(created,SOURCE);need(children(SOURCE).isEmpty(),"NEW_SOURCE_DIRECTORY_NOT_EMPTY");stepDone();
        seedOne(ALPHA,A);seedOne(BETA,B);need(children("").equals(Collections.singletonList(SOURCE)),"SEED_ROOT_CHANGED");
        ArrayList<String> expected=new ArrayList<>(Arrays.asList(ALPHA,BETA));Collections.sort(expected);need(children(SOURCE).equals(expected),"SEED_CHILDREN_CHANGED");complete("SEEDED");}
    void openFiles(boolean cleanup){begin(cleanup?"GET_CONTENT_OK":"SEEDED",cleanup?"FILES_CLEANUP_PENDING":"FILES_OPEN_PENDING","files_launch_calls");
        Intent i=new Intent(Intent.ACTION_VIEW).setDataAndType(plain(""),Document.MIME_TYPE_DIR).setComponent(new ComponentName("com.android.documentsui","com.android.documentsui.files.FilesActivity"));
        startActivity(i);complete(cleanup?"FILES_CLEANUP_OPENED":"FILES_OPENED");}
    void verifyFiles()throws Exception{begin("FILES_OPENED","VERIFY_FILES_PENDING","files_verify_calls");onlyTreeGrant();
        ArrayList<String> expected=new ArrayList<>(Arrays.asList(SOURCE,COPIES,ALPHA,BETA));Collections.sort(expected);need(children("").equals(expected),"FILES_FINAL_LAYOUT_CHANGED");
        need(children(SOURCE).isEmpty()&&children(COPIES).isEmpty(),"MOVED_SOURCE_OR_UI_DELETED_COPIES_NOT_EMPTY");
        verify(document(ALPHA),ALPHA,A,true);verify(document(BETA),BETA,B,true);complete("FILES_VERIFIED");}
    void release(){onlyTreeGrant();begin("FILES_VERIFIED","RELEASE_PENDING","release_calls");step("release-exact-tree","release_mutations");
        getContentResolver().releasePersistableUriPermission(tree(),RW);need(getContentResolver().getPersistedUriPermissions().isEmpty(),"TREE_RELEASE_NOT_OBSERVED");stepDone();
        commit(prefs.edit().putInt("release_activity_creation",prefs.getInt("activity_creations",0)));complete("TREE_RELEASED");}
    void probeRevoked()throws Exception{need(prefs.getInt("activity_creations",0)>prefs.getInt("release_activity_creation",Integer.MAX_VALUE),"NORMAL_CLOSE_REOPEN_REQUIRED_AFTER_RELEASE");
        need(getContentResolver().getPersistedUriPermissions().isEmpty(),"PERSISTED_GRANT_RETURNED");begin("TREE_RELEASED","DENIAL_PENDING","denial_probes");
        Uri value=document(BETA);need(checkUriPermission(value,Process.myPid(),Process.myUid(),Intent.FLAG_GRANT_READ_URI_PERMISSION)==PackageManager.PERMISSION_DENIED,"OWNED_BETA_READ_GRANT_STILL_ACTIVE");
        boolean denied=false;try(InputStream in=getContentResolver().openInputStream(value)){need(in!=null,"UNEXPECTED_NULL_READ_RESULT");}catch(SecurityException expected){denied=true;}
        need(denied,"REVOKED_OWNED_URI_UNEXPECTEDLY_OPENED");count("security_denials_observed");complete("DENIED_OBSERVED");}
    void render(){if(status==null)return;try{JSONObject o=new JSONObject().put("run",RUN).put("phase",phase()).put("pending",prefs.getString("pending",""))
        .put("step_pending",prefs.getString("step_pending","")).put("error",prefs.getString("error","")).put("last_read_sha256",prefs.getString("last_read_sha256",""))
        .put("last_read_bytes",prefs.getInt("last_read_bytes",0)).put("persisted_grant_count",getContentResolver().getPersistedUriPermissions().size());
        for(String key:new String[]{"activity_creations","picker_calls","get_cancel_results","tree_cancel_results","tree_grant_results","persist_calls","seed_calls","provider_create_calls","content_writes","content_readbacks","files_launch_calls","files_verify_calls","release_calls","release_mutations","denial_probes","security_denials_observed","get_content_results"})o.put(key,prefs.getInt(key,0));
        status.setText(o.toString());for(Button b:buttons){boolean next=phase().equals((String)b.getTag());b.setEnabled(next);b.setVisibility(next?View.VISIBLE:View.GONE);}
    }catch(Exception error){throw new IllegalStateException(error);}}
}
