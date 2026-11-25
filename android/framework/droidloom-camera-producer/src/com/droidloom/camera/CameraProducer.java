// SPDX-License-Identifier: GPL-3.0-or-later
package com.droidloom.camera;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Rect;
import android.net.LocalSocket;
import android.net.LocalSocketAddress;
import android.os.Binder;
import android.os.IBinder;
import android.os.RemoteException;
import android.os.SELinux;
import android.os.ServiceManager;
import android.companion.virtualcamera.Format;
import android.companion.virtualcamera.LensFacing;
import android.companion.virtualcamera.SensorOrientation;
import android.companion.virtualcamera.IVirtualCameraService;
import android.companion.virtualcamera.IVirtualCameraCallback;
import android.companion.virtualcamera.ICaptureResultConsumer;
import android.companion.virtualcamera.SupportedStreamConfiguration;
import android.companion.virtualcamera.VirtualCameraConfiguration;
import android.companion.virtualcamera.VirtualCameraMetadata;
import android.view.Surface;

import java.io.BufferedInputStream;
import java.io.DataInputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Presents only newly captured physical UVC JPEG frames through the stock camera
 * service. The service and callback ABI are generated from the locked AOSP AIDL.
 * No file, recording, network source or synthetic frame is accepted.
 */
public final class CameraProducer extends IVirtualCameraCallback.Stub {
    private static final String SERVICE_NAME = "virtual_camera";
    private static final String SERVICE_DESCRIPTOR =
            "android.companion.virtualcamera.IVirtualCameraService";
    private static final String SOCKET_PATH = "/dev/socket/droidloom-frontend/camera";
    private static final String CAMERA_LABEL = "Pocket4 Integrated Front Camera";
    private static final int WIDTH = 640;
    private static final int HEIGHT = 480;
    private static final int RGBA_8888 = Format.RGBA_8888;
    private static final int MAX_FPS = 30;
    private static final int FRONT = LensFacing.FRONT;
    private static final int SENSOR_ORIENTATION = SensorOrientation.ORIENTATION_0;
    private static final int DEVICE_ID = 0;
    private static final int MAX_STREAMS = 4;
    private static final int MAX_JPEG_BYTES = 4 * 1024 * 1024;
    private static final int SOCKET_TIMEOUT_MS = 2000;
    private static final long MAX_FRAME_AGE_NS = 1_000_000_000L;
    private static final long FIRST_FRAME_TIMEOUT_NS = 2_000_000_000L;

    private final Object stateLock = new Object();
    private final LinkedHashMap<Integer, Stream> streams = new LinkedHashMap<>();
    private final IBinder token = new Binder();
    private final AtomicBoolean stopping = new AtomicBoolean(false);
    private final AtomicBoolean failed = new AtomicBoolean(false);
    private final CountDownLatch termination = new CountDownLatch(1);
    private volatile IVirtualCameraService service;
    private volatile boolean registered;
    private Session activeSession;
    private long nextSessionId;

    private static final class Session {
        final long id;
        final long startedNs = System.nanoTime();
        volatile boolean cancelled;
        volatile LocalSocket socket;
        volatile long lastPresentedCaptureNs;
        volatile long presentedFrames;

        Session(long id) {
            this.id = id;
        }

        void cancel() {
            cancelled = true;
            closeSocket(socket);
        }
    }

    private final class Stream {
        final int id;
        final Surface surface;
        final Rect destination;
        final Paint paint = new Paint(Paint.FILTER_BITMAP_FLAG);
        volatile boolean active = true;

        Stream(int id, Surface surface, int width, int height) {
            this.id = id;
            this.surface = surface;
            destination = new Rect(0, 0, width, height);
        }

        synchronized boolean present(Bitmap frame, long captureNs) throws IOException {
            if (!active || stopping.get() || failed.get()) {
                return false;
            }
            CameraProtocol.validateFreshness(captureNs, System.nanoTime());
            // Fixed software canvas only; no alternate renderer or replay.
            Canvas canvas = surface.lockCanvas(null);

            // Never post an expired image even if acquiring a BufferQueue slot
            // stalled. On failure the camera is unregistered and this process exits.
            CameraProtocol.validateFreshness(captureNs, System.nanoTime());
            if (!active || stopping.get() || failed.get()) {
                throw new IOException("stream closed while acquiring Surface");
            }
            canvas.drawBitmap(frame, null, destination, paint);
            CameraProtocol.validateFreshness(captureNs, System.nanoTime());
            surface.unlockCanvasAndPost(canvas);
            return true;
        }

        void close() {
            // Set before waiting for a draw so a concurrent reader cannot enqueue
            // another frame while the callback is retiring this stream.
            active = false;
            synchronized (this) {
                surface.release();
            }
        }
    }

    private CameraProducer() {}

    @Override
    public void onOpenCamera() {
        // Capture remains off until a valid Surface is supplied.
        log("camera_open");
    }

    @Override
    public void onConfigureSession(VirtualCameraMetadata parameters,
            ICaptureResultConsumer consumer) {
        if (parameters == null || consumer != null) {
            failClosed("unexpected_metadata_injection", null);
            return;
        }
        log("session_configured metadata_injection=false");
    }

    @Override
    public void onStreamConfigured(int streamId, Surface surface, int width,
            int height, int format) {
        try {
            configureStream(streamId, surface, width, height, format);
        } catch (Throwable problem) {
            failClosed("stream_configuration_failure", problem);
        }
    }

    @Override
    public void onProcessCaptureRequest(int streamId, int frameId,
            VirtualCameraMetadata settings) {
        // A request is a hint. Only the next physical frame may be presented.
    }

    @Override
    public void onStreamClosed(int streamId) {
        try {
            closeStream(streamId);
        } catch (Throwable problem) {
            failClosed("stream_retirement_failure", problem);
        }
    }

    private static LocalSocket sourceSocket() throws IOException {
        LocalSocket socket = new LocalSocket(LocalSocket.SOCKET_STREAM);
        try {
            socket.connect(new LocalSocketAddress(SOCKET_PATH,
                    LocalSocketAddress.Namespace.FILESYSTEM));
            socket.setSoTimeout(SOCKET_TIMEOUT_MS);
            String context = SELinux.getPeerContext(socket.getFileDescriptor());
            if (!"u:r:droidloom_broker:s0".equals(context)) {
                throw new IOException("physical capture peer has the wrong SELinux context");
            }
            return socket;
        } catch (Throwable problem) {
            closeSocket(socket);
            throw problem;
        }
    }

    private static boolean probeAvailable() throws IOException {
        try (LocalSocket socket = sourceSocket()) {
            CameraProtocol.request(socket.getOutputStream(), CameraProtocol.PROBE);
            DataInputStream input = new DataInputStream(socket.getInputStream());
            boolean available = CameraProtocol.reply(input);
            if (input.read() != -1) {
                throw new IOException("PROBE must close without frame bytes");
            }
            return available;
        }
    }

    private void configureStream(int streamId, Surface surface, int width,
            int height, int format) throws IOException {
        if (surface == null || !surface.isValid() || width != WIDTH
                || height != HEIGHT || format != RGBA_8888) {
            if (surface != null) {
                surface.release();
            }
            throw new IOException("unsupported input Surface configuration");
        }

        Stream replaced;
        Session sessionToStart = null;
        synchronized (stateLock) {
            if (stopping.get()) {
                surface.release();
                return;
            }
            if (!streams.containsKey(streamId) && streams.size() >= MAX_STREAMS) {
                surface.release();
                throw new IOException("too many input streams");
            }
            replaced = streams.put(streamId, new Stream(streamId, surface, width, height));
            if (activeSession == null) {
                activeSession = new Session(++nextSessionId);
                sessionToStart = activeSession;
            }
        }
        if (replaced != null) {
            replaced.close();
        }
        log("stream_configured id=" + streamId + " size=" + width + "x" + height
                + " format=" + format);
        if (sessionToStart != null) {
            final Session session = sessionToStart;
            Thread reader = new Thread(() -> readLiveFrames(session), "Droidloom-camera-frames");
            reader.setDaemon(true);
            reader.start();
        }
    }

    private void closeStream(int streamId) {
        Stream removed;
        Session cancelled = null;
        synchronized (stateLock) {
            removed = streams.remove(streamId);
            if (streams.isEmpty() && activeSession != null) {
                cancelled = activeSession;
                activeSession = null;
            }
        }
        if (cancelled != null) {
            cancelled.cancel();
        }
        if (removed != null) {
            removed.close();
        }
        log("stream_closed id=" + streamId);
    }

    private void readLiveFrames(Session session) {
        try {
            // Reached only after configureStream retains a valid Surface.
            if (session.cancelled || stopping.get()) {
                return;
            }
            LocalSocket socket = sourceSocket();
            session.socket = socket;
            if (session.cancelled || stopping.get()) {
                return;
            }
            CameraProtocol.request(socket.getOutputStream(), CameraProtocol.STREAM);
            DataInputStream input = new DataInputStream(
                    new BufferedInputStream(socket.getInputStream(), 64 * 1024));
            if (!CameraProtocol.reply(input)) {
                throw new IOException("physical camera is unavailable");
            }
            log("source_connected session=" + session.id + " authenticated=true");
            long lastSequence = 0;
            long lastCaptureNs = 0;
            while (!session.cancelled && !stopping.get() && !failed.get()) {
                long length = Integer.toUnsignedLong(input.readInt());
                long sequence = input.readLong();
                long capturedNs = input.readLong();
                CameraProtocol.validateHeader(length, sequence, capturedNs, lastSequence,
                        lastCaptureNs, System.nanoTime());
                byte[] jpeg = new byte[(int) length];
                input.readFully(jpeg);
                CameraProtocol.validateFreshness(capturedNs, System.nanoTime());
                if (session.cancelled || stopping.get()) {
                    break;
                }
                if ((jpeg[0] & 255) != 0xff || (jpeg[1] & 255) != 0xd8
                        || (jpeg[jpeg.length - 2] & 255) != 0xff
                        || (jpeg[jpeg.length - 1] & 255) != 0xd9) {
                    throw new IOException("invalid JPEG boundaries");
                }
                BitmapFactory.Options bounds = new BitmapFactory.Options();
                bounds.inJustDecodeBounds = true;
                BitmapFactory.decodeByteArray(jpeg, 0, jpeg.length, bounds);
                if (bounds.outWidth != WIDTH || bounds.outHeight != HEIGHT
                        || !"image/jpeg".equals(bounds.outMimeType)) {
                    throw new IOException("unexpected capture dimensions or image type");
                }
                BitmapFactory.Options options = new BitmapFactory.Options();
                options.inPreferredConfig = Bitmap.Config.ARGB_8888;
                Bitmap bitmap = BitmapFactory.decodeByteArray(jpeg, 0, jpeg.length, options);
                if (bitmap == null || bitmap.getWidth() != WIDTH || bitmap.getHeight() != HEIGHT) {
                    if (bitmap != null) {
                        bitmap.recycle();
                    }
                    throw new IOException("live JPEG could not be decoded");
                }

                int presented = 0;
                try {
                    List<Stream> currentStreams;
                    synchronized (stateLock) {
                        if (activeSession != session || session.cancelled) {
                            break;
                        }
                        currentStreams = new ArrayList<>(streams.values());
                    }
                    for (Stream stream : currentStreams) {
                        if (stream.present(bitmap, capturedNs)) {
                            presented++;
                        }
                    }
                } finally {
                    bitmap.recycle();
                }
                lastSequence = sequence;
                lastCaptureNs = capturedNs;
                if (presented > 0) {
                    session.lastPresentedCaptureNs = capturedNs;
                    session.presentedFrames++;
                    if (session.presentedFrames == 1 || session.presentedFrames % 300 == 0) {
                        log("live_frame session=" + session.id + " frames="
                                + session.presentedFrames + " seq=" + sequence
                                + " age_ms=" + (System.nanoTime() - capturedNs) / 1_000_000
                                + " surfaces=" + presented);
                    }
                }
            }
        } catch (Throwable problem) {
            if (!session.cancelled && !stopping.get()) {
                failClosed("live_source_or_surface_failure", problem);
            }
        } finally {
            closeSocket(session.socket);
            log("source_closed session=" + session.id + " frames=" + session.presentedFrames);
        }
    }

    private void startWatchdog() {
        Thread watchdog = new Thread(() -> {
            while (!stopping.get()) {
                Session session;
                synchronized (stateLock) {
                    session = activeSession;
                }
                if (session != null && !session.cancelled) {
                    long now = System.nanoTime();
                    long last = session.lastPresentedCaptureNs;
                    if ((last == 0 && now - session.startedNs > FIRST_FRAME_TIMEOUT_NS)
                            || (last != 0 && now - last > MAX_FRAME_AGE_NS)) {
                        failClosed("fresh_frame_watchdog_expired", null);
                        return;
                    }
                }
                try {
                    Thread.sleep(100);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }, "Droidloom-frame-watchdog");
        watchdog.setDaemon(true);
        watchdog.start();
    }

    private void register() throws Exception {
        IBinder binder = ServiceManager.getService(SERVICE_NAME);
        if (binder == null || !SERVICE_DESCRIPTOR.equals(binder.getInterfaceDescriptor())) {
            throw new IOException("stock virtual_camera service is unavailable");
        }
        binder.linkToDeath(() -> failClosed("virtual_camera_service_died", null), 0);
        service = IVirtualCameraService.Stub.asInterface(binder);
        SupportedStreamConfiguration stream = new SupportedStreamConfiguration();
        stream.width = WIDTH;
        stream.height = HEIGHT;
        stream.imageFormat = RGBA_8888;
        stream.maxFps = MAX_FPS;
        stream.index = 0;
        VirtualCameraConfiguration configuration = new VirtualCameraConfiguration();
        configuration.supportedStreamConfigs = new SupportedStreamConfiguration[] { stream };
        configuration.virtualCameraCallback = this;
        configuration.sensorOrientation = SENSOR_ORIENTATION;
        configuration.lensFacing = FRONT;
        configuration.perFrameCameraMetadataEnabled = false;
        configuration.cameraCharacteristics = null;
        configuration.isMultiInputStreamEnabled = false;
        if (!service.registerCamera(token, configuration, DEVICE_ID)) {
            throw new IOException("stock virtual camera registration rejected");
        }
        registered = true;
        String id = service.getCameraId(token);
        if (id == null || !id.matches("[A-Za-z0-9_.:-]{1,128}")) {
            throw new IOException("stock virtual camera returned an invalid identifier");
        }
        log("registered label=" + CAMERA_LABEL + " camera_id=" + id
                + " source=physical_uvc size=" + WIDTH + "x" + HEIGHT
                + " facing=front orientation=" + SENSOR_ORIENTATION
                + " max_fps=" + MAX_FPS + " idle=no_capture");
    }

    private void unregister() throws RemoteException {
        if (!registered || service == null) {
            return;
        }
        try {
            service.closeSession(token);
        } finally {
            service.unregisterCamera(token);
        }
        registered = false;
        log("unregistered");
    }

    private void failClosed(String reason, Throwable cause) {
        if (stopping.get() || !failed.compareAndSet(false, true)) {
            return;
        }
        log("fatal reason=" + reason + (cause == null ? ""
                : " type=" + cause.getClass().getSimpleName() + " detail=" + cause.getMessage()));
        // Run outside a Binder callback or Surface monitor so unregister callbacks
        // cannot deadlock cleanup. The selected source-rebuilt provider owns
        // token death cleanup; this process never signals that service.
        Thread exit = new Thread(() -> {
            shutdown();
            System.exit(1);
        }, "Droidloom-camera-camera-exit");
        exit.setDaemon(false);
        exit.start();
    }

    private void shutdown() {
        if (!stopping.compareAndSet(false, true)) {
            return;
        }
        Session session;
        List<Stream> retiring;
        synchronized (stateLock) {
            session = activeSession;
            activeSession = null;
            retiring = new ArrayList<>(streams.values());
            streams.clear();
        }
        if (session != null) {
            session.cancel();
        }
        for (Stream stream : retiring) {
            stream.active = false;
        }
        // Bound shutdown if a broken Binder service or stalled Surface blocks. A
        // normal graceful exit always attempts the exact registered token first.
        Thread hardExit = new Thread(() -> {
            try {
                Thread.sleep(2500);
            } catch (InterruptedException ignored) {
                return;
            }
            log("cleanup_timeout normal_exit=false");
            Runtime.getRuntime().halt(2);
        }, "Droidloom-camera-camera-shutdown-deadline");
        hardExit.setDaemon(true);
        hardExit.start();
        try {
            unregister();
        } catch (Throwable problem) {
            log("unregister_failed type=" + problem.getClass().getSimpleName());
        }
        for (Stream stream : retiring) {
            try {
                stream.close();
            } catch (Throwable ignored) {
                // Camera registration is already removed; process exit closes FDs.
            }
        }
        termination.countDown();
    }

    private static void closeSocket(LocalSocket socket) {
        if (socket != null) {
            try {
                socket.close();
            } catch (IOException ignored) {
                // Closing the same session from reader/callback/watchdog is safe.
            }
        }
    }

    private static void log(String message) {
        System.out.println("DroidloomCamera " + message);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 0 || android.os.Process.myUid() != 0
                || !"u:r:droidloom_camera_producer:s0".equals(SELinux.getContext())) {
            throw new SecurityException("fixed init-owned camera role required");
        }
        CameraProducer producer = new CameraProducer();
        Runtime.getRuntime().addShutdownHook(new Thread(producer::shutdown,
                "Droidloom-camera-shutdown"));
        try {
            while (!probeAvailable()) {
                log("physical_unavailable registered=false capture=false");
                Thread.sleep(2000);
            }
            producer.register();
            producer.startWatchdog();
            producer.termination.await();
        } catch (Throwable problem) {
            producer.shutdown();
            throw problem;
        }
    }
}
