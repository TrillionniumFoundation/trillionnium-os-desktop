import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraManager;
import com.android.camera.device.CameraId;
import com.android.camera.one.OneCamera.Facing;
import com.android.camera.one.OneCameraAccessException;
import com.android.camera.one.v2.Camera2OneCameraManagerImpl;
import java.util.Arrays;

/** Differential host controls using the complete production manager. */
public final class CheckedDisconnectRegression {
    interface Check { void run() throws Exception; }
    private static int passed;
    private static int failed;

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    private static void run(String name, Check check) throws Exception {
        try {
            check.run();
            passed++;
            System.out.println("PASS " + name);
        } catch (AssertionError error) {
            failed++;
            System.out.println("FAIL " + name + ": " + error.getMessage());
        }
    }

    private static CameraAccessException failure(int reason) {
        return new CameraAccessException(reason, "metadata lookup failure");
    }

    private static void add(CameraManager manager, String id, int facing) {
        manager.devices.put(id, new CameraCharacteristics(facing));
    }

    private static void survivor(Facing facing, int lensFacing) {
        CameraManager service = new CameraManager();
        Camera2OneCameraManagerImpl manager = new Camera2OneCameraManagerImpl(service);
        service.ids = new String[] {"gone", "healthy"};
        service.perDeviceFailure.put("gone", failure(CameraAccessException.CAMERA_DISCONNECTED));
        add(service, "healthy", lensFacing);
        CameraId selected = manager.findFirstCameraFacing(facing);
        require(selected != null && "healthy".equals(selected.getValue()),
                "connected camera following a checked disconnect was not selected");
        require(service.metadataQueries.equals(Arrays.asList("gone", "healthy")),
                "selection retried a device or skipped the healthy metadata lookup");
    }

    private static void nonDisconnectStops(int reason) {
        CameraManager service = new CameraManager();
        Camera2OneCameraManagerImpl manager = new Camera2OneCameraManagerImpl(service);
        service.ids = new String[] {"blocked", "healthy"};
        service.perDeviceFailure.put("blocked", failure(reason));
        add(service, "healthy", CameraCharacteristics.LENS_FACING_BACK);
        require(manager.findFirstCameraFacing(Facing.BACK) == null,
                "non-disconnection error was incorrectly skipped");
        require(service.metadataQueries.equals(Arrays.asList("blocked", "blocked")),
                "existing back/external failure behavior changed");
    }

    public static void main(String[] args) throws Exception {
        run("checked disconnect retains following back camera", () ->
                survivor(Facing.BACK, CameraCharacteristics.LENS_FACING_BACK));
        run("checked disconnect retains following front camera", () ->
                survivor(Facing.FRONT, CameraCharacteristics.LENS_FACING_FRONT));
        run("checked disconnect retains external fallback", () -> {
            CameraManager service = new CameraManager();
            Camera2OneCameraManagerImpl manager = new Camera2OneCameraManagerImpl(service);
            service.ids = new String[] {"gone", "usb"};
            service.perDeviceFailure.put("gone", failure(CameraAccessException.CAMERA_DISCONNECTED));
            add(service, "usb", CameraCharacteristics.LENS_FACING_EXTERNAL);
            CameraId selected = manager.findFirstCameraFacing(Facing.BACK);
            require(selected != null && "usb".equals(selected.getValue()),
                    "connected external fallback was not selected");
            require(service.metadataQueries.equals(Arrays.asList("gone", "usb", "gone", "usb")),
                    "existing back/external passes changed or a device was retried within a pass");
        });
        run("all checked disconnects terminate within existing passes", () -> {
            CameraManager service = new CameraManager();
            Camera2OneCameraManagerImpl manager = new Camera2OneCameraManagerImpl(service);
            service.ids = new String[] {"gone-a", "gone-b"};
            service.perDeviceFailure.put("gone-a", failure(CameraAccessException.CAMERA_DISCONNECTED));
            service.perDeviceFailure.put("gone-b", failure(CameraAccessException.CAMERA_DISCONNECTED));
            require(manager.findFirstCameraFacing(Facing.BACK) == null,
                    "a disconnected camera was selected");
            require(service.metadataQueries.size() <= 4,
                    "enumeration exceeded two existing passes over two devices");
        });
        run("list service disconnect does not query metadata", () -> {
            CameraManager service = new CameraManager();
            Camera2OneCameraManagerImpl manager = new Camera2OneCameraManagerImpl(service);
            service.ids = new String[] {"healthy"};
            add(service, "healthy", CameraCharacteristics.LENS_FACING_BACK);
            service.listFailure = failure(CameraAccessException.CAMERA_DISCONNECTED);
            require(manager.findFirstCameraFacing(Facing.BACK) == null,
                    "unavailable camera list was ignored");
            require(service.metadataQueries.isEmpty(), "metadata queried after list failure");
        });
        run("camera disabled preserves failure behavior", () ->
                nonDisconnectStops(CameraAccessException.CAMERA_DISABLED));
        run("camera error preserves failure behavior", () ->
                nonDisconnectStops(CameraAccessException.CAMERA_ERROR));
        run("camera in use preserves failure behavior", () ->
                nonDisconnectStops(CameraAccessException.CAMERA_IN_USE));
        run("maximum cameras preserves failure behavior", () ->
                nonDisconnectStops(CameraAccessException.MAX_CAMERAS_IN_USE));
        run("direct selected disconnect retains checked cause", () -> {
            CameraManager service = new CameraManager();
            Camera2OneCameraManagerImpl manager = new Camera2OneCameraManagerImpl(service);
            CameraAccessException error = failure(CameraAccessException.CAMERA_DISCONNECTED);
            service.perDeviceFailure.put("gone", error);
            try {
                manager.getCameraCharacteristics(CameraId.from("gone"));
                throw new AssertionError("selected-device disconnect was swallowed");
            } catch (OneCameraAccessException expected) {
                require(expected.getCause() == error, "selected-device cause changed");
            }
        });
        run("enumeration security exception is not swallowed", () -> {
            CameraManager service = new CameraManager();
            Camera2OneCameraManagerImpl manager = new Camera2OneCameraManagerImpl(service);
            service.ids = new String[] {"blocked"};
            SecurityException error = new SecurityException("permission denied");
            service.queryRuntime = error;
            try {
                manager.findFirstCameraFacing(Facing.BACK);
                throw new AssertionError("security exception was swallowed");
            } catch (SecurityException expected) {
                require(expected == error, "security exception changed");
            }
        });
        System.out.println("TOTAL_PASS=" + passed + " TOTAL_FAIL=" + failed);
        if (failed != 0) System.exit(1);
    }
}
