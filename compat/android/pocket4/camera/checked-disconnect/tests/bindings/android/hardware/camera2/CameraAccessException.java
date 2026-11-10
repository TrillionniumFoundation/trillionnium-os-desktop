package android.hardware.camera2;

/** Host fixture only; these public reasons and constructors match the Android API. */
public class CameraAccessException extends Exception {
    public static final int CAMERA_DISABLED = 1;
    public static final int CAMERA_DISCONNECTED = 2;
    public static final int CAMERA_ERROR = 3;
    public static final int CAMERA_IN_USE = 4;
    public static final int MAX_CAMERAS_IN_USE = 5;

    private final int reason;

    public CameraAccessException(int problem, String message) {
        super(message);
        reason = problem;
    }

    // Retain the original host suite's fixture-only constructor without treating
    // an unspecified failure as a device disconnect.
    public CameraAccessException(String message) {
        this(CAMERA_ERROR, message);
    }

    public final int getReason() {
        return reason;
    }
}
