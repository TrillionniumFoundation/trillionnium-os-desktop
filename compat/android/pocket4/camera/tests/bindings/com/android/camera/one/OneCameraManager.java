package com.android.camera.one;
import com.android.camera.device.CameraId;import com.android.camera.one.OneCamera.Facing;import android.os.Handler;
public interface OneCameraManager {
 boolean hasCamera();boolean hasCameraFacing(Facing f);CameraId findFirstCamera();CameraId findFirstCameraFacing(Facing f);
 OneCameraCharacteristics getOneCameraCharacteristics(CameraId id)throws OneCameraAccessException;
 void setAvailabilityCallback(AvailabilityCallback callback,Handler h);
 interface AvailabilityCallback{void onCameraAccessPrioritiesChanged();}
}
