package android.hardware.camera2;
public class CameraCharacteristics {
 public static final int LENS_FACING_FRONT=0,LENS_FACING_BACK=1,LENS_FACING_EXTERNAL=2;
 public static final Key<Integer> LENS_FACING=new Key<Integer>();
 public static final class Key<T>{}
 public Integer facing;
 public CameraCharacteristics(Integer facing){this.facing=facing;}
 @SuppressWarnings("unchecked") public <T>T get(Key<T> key){return (T)facing;}
}
