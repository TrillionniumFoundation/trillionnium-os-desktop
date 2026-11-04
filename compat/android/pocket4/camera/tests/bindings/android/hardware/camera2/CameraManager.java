package android.hardware.camera2;
import android.os.Handler; import java.util.*;
public class CameraManager {
 public String[] ids=new String[0]; public Map<String,CameraCharacteristics> devices=new HashMap<String,CameraCharacteristics>();
 public CameraAccessException listFailure,queryFailure; public RuntimeException queryRuntime; public Set<String> removed=new HashSet<String>();
 public int registered,unregistered; public boolean returnNull;
 public String[] getCameraIdList() throws CameraAccessException {if(listFailure!=null)throw listFailure;return ids;}
 public CameraCharacteristics getCameraCharacteristics(String id) throws CameraAccessException {
  if(queryFailure!=null)throw queryFailure;if(queryRuntime!=null)throw queryRuntime;
  if(returnNull)return null;
  if(removed.contains(id)||!devices.containsKey(id))throw new IllegalArgumentException("unknown device "+id);
  return devices.get(id);
 }
 public void registerAvailabilityCallback(AvailabilityCallback callback,Handler handler){registered++;}
 public void unregisterAvailabilityCallback(AvailabilityCallback callback){unregistered++;}
 public static class AvailabilityCallback{
  public void onCameraAvailable(String id){} public void onCameraUnavailable(String id){}
  public void onCameraAccessPrioritiesChanged(){}
 }
}
