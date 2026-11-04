package local.pocket4.nativeoraclev8;
import android.app.Activity;
import android.os.Bundle;
import android.os.Process;
import android.system.ErrnoException;
import android.system.Os;
import android.system.OsConstants;
import android.system.StructStat;
import android.util.Log;
import android.widget.TextView;
import java.io.File;
import java.io.FileDescriptor;
import java.nio.charset.StandardCharsets;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
public final class MainActivity extends Activity {
 private static final String TAG="NativeOracleV8";
 private static native long runCase(int c);
 private static native long readField(int i);
 private static native long queryAlarm();
 private static String readBounded(String path,int limit,boolean checkClaim) throws Exception {
  FileDescriptor fd=Os.open(path,OsConstants.O_RDONLY|OsConstants.O_CLOEXEC|OsConstants.O_NOFOLLOW,0);
  try {
   if(checkClaim) {
    StructStat st=Os.fstat(fd);
    if(!OsConstants.S_ISREG(st.st_mode)||st.st_uid!=Process.myUid()||st.st_nlink!=1||(st.st_mode&0777)!=0600||st.st_size<=0||st.st_size>=limit)throw new IllegalStateException("claim metadata");
   }
   byte[] bytes=new byte[limit];int length=0,n;
   while((n=Os.read(fd,bytes,length,bytes.length-length))>0) {
    length+=n;
    if(length==bytes.length)throw new IllegalStateException("bounded record exceeded");
   }
   return new String(bytes,0,length,StandardCharsets.UTF_8);
  } finally {Os.close(fd);}
 }
 private static long startTicks() throws Exception {
  String stat=readBounded("/proc/self/stat",4096,false);
  int end=stat.lastIndexOf(')');
  if(end<1)throw new IllegalStateException("process stat");
  String[] fields=stat.substring(end+1).trim().split(" +");
  long value=Long.parseLong(fields[19]);
  if(value<=0)throw new IllegalStateException("process start");
  return value;
 }
 private boolean claimDefault(String nonce,String prefix,long start) throws Exception {
  File directory=getFilesDir(),claim=new File(directory,"default-alarm-"+nonce+".claim");
  FileDescriptor fd;
  try {
   fd=Os.open(claim.getAbsolutePath(),OsConstants.O_WRONLY|OsConstants.O_CREAT|OsConstants.O_EXCL|OsConstants.O_CLOEXEC|OsConstants.O_NOFOLLOW,0600);
  } catch(ErrnoException e) {
   if(e.errno!=OsConstants.EEXIST)throw e;
   String previous=readBounded(claim.getAbsolutePath(),512,true);
   Matcher m=Pattern.compile("v=1 run_id=([0-9a-f]{32}) mode=default-alarm pid=([1-9][0-9]*) uid=([0-9]+) start_ticks=([1-9][0-9]*)\\n").matcher(previous);
   if(!m.matches()||!m.group(1).equals(nonce)||Long.parseLong(m.group(3))!=Process.myUid())throw new IllegalStateException("claim identity");
   Log.i(TAG,prefix+"phase=relaunch-refused owner_pid="+m.group(2)+" owner_uid="+m.group(3)+" owner_start_ticks="+m.group(4));
   finishAndRemoveTask();
   return false;
  }
  try {
   byte[] record=("v=1 run_id="+nonce+" mode=default-alarm pid="+Process.myPid()+" uid="+Process.myUid()+" start_ticks="+start+"\n").getBytes(StandardCharsets.UTF_8);
   int offset=0;
   while(offset<record.length) {
    int n=Os.write(fd,record,offset,record.length-offset);
    if(n<=0)throw new IllegalStateException("claim write");
    offset+=n;
   }
   Os.fsync(fd);
  } finally {Os.close(fd);}
  FileDescriptor directoryFd=Os.open(directory.getAbsolutePath(),OsConstants.O_RDONLY|OsConstants.O_CLOEXEC|OsConstants.O_NOFOLLOW,0);
  try {
   StructStat directoryStat=Os.fstat(directoryFd);
   if(!OsConstants.S_ISDIR(directoryStat.st_mode)||directoryStat.st_uid!=Process.myUid())throw new IllegalStateException("claim directory");
   Os.fsync(directoryFd);
  } finally {Os.close(directoryFd);}
  Log.i(TAG,prefix+"phase=claim-acquired owner_pid="+Process.myPid()+" owner_uid="+Process.myUid()+" owner_start_ticks="+start);
  return true;
 }
 @Override public void onCreate(Bundle state) {
  super.onCreate(state);TextView view=new TextView(this);setContentView(view);
  String nonce=getIntent().getStringExtra("run_id"),mode=getIntent().getStringExtra("mode");
  if(nonce==null||!nonce.matches("[0-9a-f]{32}")||(!"controls".equals(mode)&&!"default-alarm".equals(mode))||(state!=null&&!"default-alarm".equals(mode))){view.setText("Owned V8 diagnostic: fresh explicit intent required");return;}
  String prefix="run_id="+nonce+" mode="+mode+" pid="+Process.myPid()+" uid="+Process.myUid()+" ";
  try {
   long start=startTicks();prefix+="start_ticks="+start+" ";
   if("default-alarm".equals(mode)&&!claimDefault(nonce,prefix,start))return;
   Log.i(TAG,prefix+"phase=before-load");System.loadLibrary("nativeoraclev8");
   Log.i(TAG,prefix+"phase=loaded initial_alarm="+queryAlarm());
   int first="controls".equals(mode)?0:5,last="controls".equals(mode)?4:5;
   boolean all=true;
   for(int c=first;c<=last;c++){
    Log.i(TAG,prefix+"phase=before-native case="+c);
    long returned=runCase(c);StringBuilder line=new StringBuilder(prefix+"phase=result case="+c+" returned="+returned);
    for(int i=0;i<40;i++)line.append(" f").append(i).append("=").append(readField(i));
    Log.i(TAG,line.toString());all&=returned==0;
   }
   Log.i(TAG,prefix+"phase=complete cases="+(last-first+1)+" own_status_zero="+(all?1:0));
   view.setText("Owned V8 diagnostic: observations recorded");
  }catch(Throwable failure){Log.i(TAG,prefix+"phase=exception type="+failure.getClass().getName());view.setText("Owned V8 diagnostic failed: "+failure.getClass().getName());}
 }
}
