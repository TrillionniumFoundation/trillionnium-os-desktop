package org.droidloom.qa.galleryrotation.r12.nd24b61ed8f7c9a03;

import android.content.ContentResolver;
import android.content.ContentUris;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.media.ExifInterface;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.os.SystemClock;
import android.provider.MediaStore;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.security.MessageDigest;
import java.util.Locale;
import org.json.JSONArray;
import org.json.JSONObject;

/** Fixed owned media only; route/rotation qualification belongs to the controller. */
final class RotationStore {
    static final String RUN="d24b61ed8f7c9a03";
    static final String PACKAGE="org.droidloom.qa.galleryrotation.r12.nd24b61ed8f7c9a03";
    static final String GALLERY="com.android.gallery3d";
    static final String CONTROL_ALBUM="Pocket4_Rotate_Control_r12_"+RUN;
    static final String COPY_ALBUM="Pocket4_Rotate_Copy_r12_"+RUN;
    static final String[] KEYS={"control","copy"};
    static final String[] NAMES={"pocket4-control-"+RUN+".png","pocket4-copy-"+RUN+".jpg"};
    static final String[] RELATIVE={"DCIM/"+CONTROL_ALBUM+"/","DCIM/"+COPY_ALBUM+"/"};
    static final String[] MIME={"image/png","image/jpeg"};
    static final String ORIGINAL_PNG_SHA="c27368348393b4063097c6ab18993dfc91e5c71e7fd1ac6978c191e1740fc7db";
    static final int WIDTH=640,HEIGHT=480,MAX_BYTES=4*1024*1024;
    static final long LEASE_MS=1200000L;
    static final Uri COLLECTION=MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY);
    final ContentResolver resolver;
    final SharedPreferences prefs;

    RotationStore(Context context) {
        need(PACKAGE.equals(context.getPackageName()),"EXACT_PACKAGE_REQUIRED");
        resolver=context.getContentResolver();
        prefs=context.getSharedPreferences("owned-rotation-"+RUN,Context.MODE_PRIVATE);
    }
    static void need(boolean ok,String why) { if(!ok)throw new IllegalStateException(why); }
    static String digest(byte[] data) throws Exception {
        return hex(MessageDigest.getInstance("SHA-256").digest(data));
    }
    static String hex(byte[] data) {
        StringBuilder value=new StringBuilder();
        for(byte b:data)value.append(String.format(Locale.ROOT,"%02x",b&255));
        return value.toString();
    }
    void commit(SharedPreferences.Editor value) { need(value.commit(),"OWNED_RECORD_COMMIT_FAILED"); }
    String phase() { return prefs.getString("phase","EMPTY"); }
    String pending() { return prefs.getString("pending",""); }
    void live() {
        need(RUN.equals(prefs.getString("run","")),"RUN_IDENTITY_CHANGED");
        long age=SystemClock.elapsedRealtime()-prefs.getLong("started_elapsed_ms",-1);
        need(age>=0 && age<LEASE_MS,"OWNED_FIXTURE_LEASE_EXPIRED");
    }
    Uri uri(int index) {
        need(index==0 || index==1,"FIXED_MEDIA_INDEX");
        Uri value=Uri.parse(prefs.getString(KEYS[index]+"_uri",""));
        need("content".equals(value.getScheme()) && "media".equals(value.getAuthority())
            && value.getQuery()==null && value.getFragment()==null,"OWNED_URI_REQUIRED");
        long id=ContentUris.parseId(value);
        need(id>0 && value.equals(ContentUris.withAppendedId(COLLECTION,id)),"EXACT_IMAGE_COLLECTION_REQUIRED");
        return value;
    }
    int count(Uri value,String selection,String[] args) {
        try(Cursor c=resolver.query(value,new String[]{"_id"},selection,args,null)) {
            need(c!=null,"MEDIA_QUERY_CURSOR_REQUIRED");
            int n=c.getCount();need(n<=8,"OWNED_QUERY_COUNT_BOUND");return n;
        }
    }
    byte[] read(Uri value) throws Exception {
        try(InputStream stream=resolver.openInputStream(value)) {
            need(stream!=null,"OWNED_IMAGE_STREAM_REQUIRED");
            ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] buffer=new byte[8192];int n;
            while((n=stream.read(buffer))!=-1) { need(out.size()+n<=MAX_BYTES,"OWNED_READ_BOUND");out.write(buffer,0,n); }
            return out.toByteArray();
        }
    }

    // Exactly the original immutable PNG generator; the JPEG is a derivative.
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

    static byte[] jpeg(byte[] png) throws Exception {
        Bitmap bitmap=BitmapFactory.decodeByteArray(png,0,png.length);
        need(bitmap!=null && bitmap.getWidth()==WIDTH && bitmap.getHeight()==HEIGHT,"SOURCE_PNG_DECODE");
        try {
            ByteArrayOutputStream out=new ByteArrayOutputStream();
            need(bitmap.compress(Bitmap.CompressFormat.JPEG,95,out),"JPEG_ENCODING_FAILED");
            byte[] bytes=out.toByteArray();need(bytes.length>100 && bytes.length<MAX_BYTES,"JPEG_SIZE_BOUND");
            return bytes;
        } finally { bitmap.recycle(); }
    }
    static JSONObject pixels(byte[] raw) throws Exception {
        BitmapFactory.Options options=new BitmapFactory.Options();
        options.inPreferredConfig=Bitmap.Config.ARGB_8888;options.inScaled=false;
        Bitmap bitmap=BitmapFactory.decodeByteArray(raw,0,raw.length,options);
        need(bitmap!=null,"OWNED_IMAGE_DECODE_FAILED");
        try {
            need(bitmap.getWidth()==WIDTH && bitmap.getHeight()==HEIGHT,"RAW_PIXEL_DIMENSIONS_CHANGED");
            MessageDigest md=MessageDigest.getInstance("SHA-256");
            for(int v:new int[]{WIDTH,HEIGHT})for(int shift=24;shift>=0;shift-=8)md.update((byte)(v>>>shift));
            int[] row=new int[WIDTH];byte[] bytes=new byte[WIDTH*4];
            for(int y=0;y<HEIGHT;y++) {
                bitmap.getPixels(row,0,WIDTH,0,y,WIDTH,1);
                for(int x=0;x<WIDTH;x++)for(int n=0;n<4;n++)bytes[x*4+n]=(byte)(row[x]>>>(24-8*n));
                md.update(bytes);
            }
            JSONArray samples=new JSONArray();
            for(int[] point:new int[][]{{100,100},{540,100},{100,380},{540,380}}) {
                int rgb=bitmap.getPixel(point[0],point[1]);
                samples.put(new JSONArray().put((rgb>>>16)&255).put((rgb>>>8)&255).put(rgb&255));
            }
            return new JSONObject().put("width",WIDTH).put("height",HEIGHT)
                .put("argb_pixels_sha256",hex(md.digest())).put("quadrant_RGB_samples",samples)
                .put("EXIF_applied_to_pixel_digest",false);
        } finally { bitmap.recycle(); }
    }
    static int orientation(byte[] raw) throws Exception {
        ExifInterface exif=new ExifInterface(new ByteArrayInputStream(raw));
        return exif.getAttributeInt(ExifInterface.TAG_ORIENTATION,ExifInterface.ORIENTATION_UNDEFINED);
    }
    JSONObject metadata(int index,boolean pendingAllowed) throws Exception {
        Uri value=uri(index);
        String[] columns={"_id","_display_name","relative_path","mime_type","_size","width","height",
            "is_pending","owner_package_name","orientation","bucket_id","bucket_display_name","_data"};
        JSONObject out=new JSONObject();
        try(Cursor c=resolver.query(value,columns,null,null,null)) {
            need(c!=null && c.getCount()==1 && c.moveToFirst(),"ONE_EXACT_MEDIA_ROW_REQUIRED");
            need(c.getLong(0)==ContentUris.parseId(value) && NAMES[index].equals(c.getString(1))
                && RELATIVE[index].equals(c.getString(2)) && MIME[index].equals(c.getString(3))
                && PACKAGE.equals(c.getString(8)),"OWNED_MEDIA_IDENTITY_CHANGED");
            need(c.getInt(7)==(pendingAllowed?1:0),"OWNED_MEDIA_PUBLICATION_STATE_CHANGED");
            if(!pendingAllowed)need(("/storage/emulated/0/"+RELATIVE[index]+NAMES[index]).equals(c.getString(12)),"OWNED_MEDIA_PATH_CHANGED");
            for(int i=0;i<columns.length;i++) {
                if(c.isNull(i))out.put(columns[i],JSONObject.NULL);
                else if(c.getType(i)==Cursor.FIELD_TYPE_INTEGER)out.put(columns[i],c.getLong(i));
                else out.put(columns[i],c.getString(i));
            }
        }
        return out;
    }
    JSONObject verifyImage(int index,boolean rotated,boolean pendingAllowed) throws Exception {
        JSONObject before=metadata(index,pendingAllowed);byte[] raw=read(uri(index));
        JSONObject after=metadata(index,pendingAllowed);
        if(!pendingAllowed)need(before.toString().equals(after.toString()),"MEDIA_ROW_CHANGED_DURING_READ");
        String key=KEYS[index],hash=digest(raw);JSONObject decoded=pixels(raw);
        need(decoded.getString("argb_pixels_sha256").equals(prefs.getString(key+"_pixels_sha256","")),
            "SOURCE_PIXEL_DIGEST_CHANGED");
        if(index==0 || !rotated)need(hash.equals(prefs.getString(key+"_sha256",""))
            && raw.length==prefs.getInt(key+"_bytes",-1),"ORIGINAL_IMAGE_BYTES_CHANGED");
        int exif=index==1?orientation(raw):0;
        if(index==1)need(rotated?exif==ExifInterface.ORIENTATION_ROTATE_90:
            exif==prefs.getInt("copy_initial_exif",-1),"COPY_EXIF_ORIENTATION_NOT_EXPECTED");
        if(!pendingAllowed) {
            need(after.getLong("_size")==raw.length && after.getInt("width")==WIDTH
                && after.getInt("height")==HEIGHT,"PUBLISHED_MEDIA_SIZE_OR_DIMENSIONS_NOT_READY");
            if(index==1)need(rotated?after.getInt("orientation")==90:
                after.isNull("orientation") || after.getInt("orientation")==0,"MEDIASTORE_ORIENTATION_NOT_EXPECTED");
            need((index==0?CONTROL_ALBUM:COPY_ALBUM).equals(after.getString("bucket_display_name")),"OWNED_BUCKET_LABEL_CHANGED");
            long bucket=after.getLong("bucket_id");need(bucket>=Integer.MIN_VALUE && bucket<=Integer.MAX_VALUE,"BUCKET_ID_RANGE");
            if(prefs.contains(key+"_bucket"))need(bucket==prefs.getLong(key+"_bucket",Long.MAX_VALUE),"BUCKET_ID_CHANGED");
            if(index==0 && prefs.contains("control_metadata"))
                need(after.toString().equals(prefs.getString("control_metadata","")),"CONTROL_METADATA_CHANGED");
        }
        if(index==1 && rotated && prefs.contains("copy_rotated_sha256"))
            need(hash.equals(prefs.getString("copy_rotated_sha256",""))
                && raw.length==prefs.getInt("copy_rotated_bytes",-1),"ROTATED_COPY_BYTES_CHANGED");
        return new JSONObject().put("uri",uri(index).toString()).put("sha256",hash).put("bytes",raw.length)
            .put("exif_orientation",exif).put("decoded",decoded).put("metadata",after);
    }
    JSONObject verify(boolean rotated) throws Exception {
        live();JSONObject control=verifyImage(0,false,false),copy=verifyImage(1,rotated,false);
        for(int i=0;i<2;i++)need(count(COLLECTION,"relative_path=?",new String[]{RELATIVE[i]})==1,"ONLY_OWNED_IMAGE_IN_BUCKET");
        return new JSONObject().put("control",control).put("copy",copy).put("rotated",rotated);
    }
    JSONObject seed() throws Exception {
        need(prefs.getAll().isEmpty(),"FRESH_PACKAGE_STATE_REQUIRED");
        for(int i=0;i<2;i++)need(count(COLLECTION,"relative_path=?",new String[]{RELATIVE[i]})==0,"OWNED_NAMESPACE_PRESENT");
        byte[] png=pattern();need(ORIGINAL_PNG_SHA.equals(digest(png)),"ORIGINAL_PNG_GENERATOR_BYTES_CHANGED");
        byte[][] payload={png,jpeg(png)};int initialExif=orientation(payload[1]);
        need(initialExif==ExifInterface.ORIENTATION_UNDEFINED || initialExif==ExifInterface.ORIENTATION_NORMAL,"JPEG_INITIAL_ORIENTATION");
        SharedPreferences.Editor initial=prefs.edit().putString("run",RUN)
            .putLong("started_elapsed_ms",SystemClock.elapsedRealtime()).putLong("started_wall_ms",System.currentTimeMillis())
            .putString("phase","SEED_PENDING").putString("pending","prepare-two-owned-images").putInt("copy_initial_exif",initialExif);
        for(int i=0;i<2;i++)initial.putString(KEYS[i]+"_sha256",digest(payload[i])).putInt(KEYS[i]+"_bytes",payload[i].length)
            .putString(KEYS[i]+"_pixels_sha256",pixels(payload[i]).getString("argb_pixels_sha256"));
        commit(initial);
        for(int i=0;i<2;i++) {
            live();commit(prefs.edit().putString("pending","insert-"+KEYS[i]).putInt("insert_calls",i+1));
            ContentValues values=new ContentValues();values.put("_display_name",NAMES[i]);values.put("mime_type",MIME[i]);
            values.put("relative_path",RELATIVE[i]);values.put("is_pending",1);values.put("width",WIDTH);values.put("height",HEIGHT);
            Uri created=resolver.insert(COLLECTION,values);need(created!=null,"MEDIA_INSERT_RETURNED_NULL");
            commit(prefs.edit().putString(KEYS[i]+"_uri",created.toString()).putString("pending","write-"+KEYS[i]).putInt("write_calls",i+1));
            Uri exact=uri(i);
            try(ParcelFileDescriptor descriptor=resolver.openFileDescriptor(exact,"w")) {
                need(descriptor!=null,"OWNED_WRITE_DESCRIPTOR_REQUIRED");
                try(ParcelFileDescriptor.AutoCloseOutputStream stream=new ParcelFileDescriptor.AutoCloseOutputStream(descriptor)) {
                    stream.write(payload[i]);stream.flush();stream.getFD().sync();
                }
            }
            verifyImage(i,false,true);live();
            commit(prefs.edit().putString("pending","publish-"+KEYS[i]).putInt("publish_calls",i+1));
            values.clear();values.put("is_pending",0);
            need(resolver.update(exact,values,null,null)==1,"ONE_OWNED_PUBLICATION_REQUIRED");
            JSONObject proof=verifyImage(i,false,false);
            SharedPreferences.Editor indexed=prefs.edit().putLong(KEYS[i]+"_bucket",proof.getJSONObject("metadata").getLong("bucket_id"));
            if(i==0)indexed.putString("control_metadata",proof.getJSONObject("metadata").toString());
            commit(indexed);
        }
        JSONObject proof=verify(false);commit(prefs.edit().putString("phase","SEEDED").putString("pending",""));return proof;
    }
    Intent prepareAlbumLaunch() throws Exception {
        synchronized(RotationStore.class) {
            live();need(pending().isEmpty(),"PREVIOUS_HELPER_EFFECT_PENDING");
            int round=prefs.getInt("gallery_launches",0);
            need((round==0 && "SEEDED".equals(phase())) ||
                (round==1 && "ROTATED_VERIFIED".equals(phase())),"ONE_LAUNCH_PER_VERIFIED_ROUND");
            JSONObject proof=verify(round==1);long bucket=proof.getJSONObject("copy").getJSONObject("metadata").getLong("bucket_id");
            Uri album=MediaStore.Images.Media.EXTERNAL_CONTENT_URI.buildUpon()
                .appendQueryParameter("bucketId",Long.toString(bucket)).build();
            need("content://media/external/images/media".equals(album.buildUpon().clearQuery().build().toString()),"ACTUAL_GALLERY_EXTERNAL_ROUTE_REQUIRED");
            Intent intent=new Intent(Intent.ACTION_VIEW).setClassName(GALLERY,GALLERY+".app.GalleryActivity")
                .setDataAndType(album,"vnd.android.cursor.dir/image");
            commit(prefs.edit().putInt("gallery_launches",round+1).putString("phase","ALBUM_OPEN_"+(round+1))
                .putString("pending","gallery-open-"+(round+1)).putString("album_uri",album.toString()));
            return intent;
        }
    }
    JSONObject seal(int round,boolean rotated) throws Exception {
        live();need((round==1 || round==2) && (round!=2 || rotated),"FIXED_ROUND_AND_ORIENTATION");
        need(("ALBUM_OPEN_"+round).equals(phase()) && ("gallery-open-"+round).equals(pending())
            && prefs.getInt("gallery_launches",0)==round,"EXACT_OPEN_ROUND_REQUIRED");
        JSONObject proof=verify(rotated);
        SharedPreferences.Editor editor=prefs.edit().putString("pending","");
        if(round==1 && rotated)editor.putString("copy_rotated_sha256",proof.getJSONObject("copy").getString("sha256"))
            .putInt("copy_rotated_bytes",proof.getJSONObject("copy").getInt("bytes")).putString("phase","ROTATED_VERIFIED");
        else editor.putString("phase",round==2?"REOPENED_VERIFIED":"FIRST_CLOSED_UNCHANGED");
        commit(editor);
        return proof.put("external_owned_task_close_required",true).put("Gallery_UI_success_claimed",false);
    }
    JSONObject delete() throws Exception {
        live();need(pending().isEmpty(),"UNKNOWN_EFFECT_PRESERVE_MEDIA");
        boolean rotated="ROTATED_VERIFIED".equals(phase()) || "REOPENED_VERIFIED".equals(phase());
        need(rotated || "SEEDED".equals(phase()) || "FIRST_CLOSED_UNCHANGED".equals(phase()),"KNOWN_MEDIA_STATE_REQUIRED");
        JSONObject proof=verify(rotated);
        for(int i=1;i>=0;i--) {
            live();verifyImage(i,i==1 && rotated,false);Uri exact=uri(i);
            commit(prefs.edit().putString("phase","DELETE_PENDING").putString("pending","delete-"+KEYS[i])
                .putInt("delete_calls",2-i));
            need(resolver.delete(exact,null,null)==1,"ONE_EXACT_IMAGE_DELETE_REQUIRED");
            need(count(exact,null,null)==0 && count(COLLECTION,"relative_path=?",new String[]{RELATIVE[i]})==0,
                "OWNED_IMAGE_ROW_STILL_PRESENT");
        }
        commit(prefs.edit().putString("phase","DELETED").putString("pending",""));
        return proof.put("owned_image_rows_absent",true).put("physical_and_directory_index_absence_verified_by_controller",false);
    }
    JSONObject status() throws Exception {
        JSONObject out=new JSONObject().put("run",RUN).put("phase",phase()).put("pending",pending())
            .put("gallery_launches",prefs.getInt("gallery_launches",0)).put("album_uri",prefs.getString("album_uri",""));
        for(String counter:new String[]{"insert_calls","write_calls","publish_calls","delete_calls"})out.put(counter,prefs.getInt(counter,0));
        for(int i=0;i<2;i++)if(prefs.contains(KEYS[i]+"_uri"))out.put(KEYS[i]+"_uri",uri(i).toString());
        return out;
    }
}
