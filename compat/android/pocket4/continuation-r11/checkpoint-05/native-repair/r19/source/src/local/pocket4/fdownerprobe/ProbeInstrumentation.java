package local.pocket4.fdownerprobe;
import android.app.Instrumentation;
import android.app.Activity;
import android.os.Bundle;
import android.os.Process;
import android.os.Build;
import android.content.pm.ApplicationInfo;
import java.io.*;
public final class ProbeInstrumentation extends Instrumentation {
 private static native String runProbe();
 @Override public void onCreate(Bundle args) {
  super.onCreate(args);
  Bundle out=new Bundle();
  out.putInt("pid",Process.myPid()); out.putInt("uid",Process.myUid());
  out.putInt("sdk",Build.VERSION.SDK_INT);
  try {
   String nonce=args==null?null:args.getString("nonce");
   if(nonce==null || !nonce.matches("[a-zA-Z0-9_-]{12,80}")) throw new IllegalArgumentException("explicit nonce required");
   File claim=new File(getTargetContext().getFilesDir(),nonce+".claim");
   if(!claim.createNewFile()) throw new IllegalStateException("nonce already claimed; no replay");
   try(FileOutputStream file=new FileOutputStream(claim)) {
    file.write(("pid="+Process.myPid()+" uid="+Process.myUid()+"\n").getBytes("UTF-8")); file.getFD().sync();
   }
   out.putString("nonce",nonce);
   out.putBoolean("debuggable",(getTargetContext().getApplicationInfo().flags&ApplicationInfo.FLAG_DEBUGGABLE)!=0);
   StringBuilder policy=new StringBuilder();
   try(BufferedReader br=new BufferedReader(new FileReader("/proc/self/status"))) {
    String line;while((line=br.readLine())!=null) if(line.startsWith("Seccomp:")||line.startsWith("NoNewPrivs:")||line.startsWith("Seccomp_filters:")) policy.append(line).append('\n');
   }
   out.putString("policy",policy.toString());
   System.loadLibrary("fdownerprobe");
   out.putString("probe_result",runProbe());
   finish(Activity.RESULT_OK,out);
  } catch(Throwable e) {
   out.putString("error",e.getClass().getName()+": "+e.getMessage());
   finish(Activity.RESULT_CANCELED,out);
  }
 }
}
