// SPDX-License-Identifier: GPL-3.0-or-later
package com.droidloom.camera;

import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.util.Arrays;

/** Closed physical-camera transport; no Java/Android object deserialization. */
final class CameraProtocol {
    static final int PROBE = 1;
    static final int STREAM = 2;
    static final int WIDTH = 640;
    static final int HEIGHT = 480;
    static final int FPS = 30;
    static final int MAX_JPEG = 4 * 1024 * 1024;
    static final long MAX_AGE_NS = 1_000_000_000L;
    private static final byte[] MAGIC = {'D', 'L', 'C', 'A', 'M', '0', '1', 0};

    private CameraProtocol() {}

    static void request(OutputStream stream, int operation) throws IOException {
        if (operation != PROBE && operation != STREAM) {
            throw new IOException("unknown physical camera operation");
        }
        DataOutputStream output = new DataOutputStream(stream);
        output.write(MAGIC);
        output.writeInt(operation);
        output.flush();
    }

    static boolean reply(DataInputStream input) throws IOException {
        byte[] magic = new byte[MAGIC.length];
        input.readFully(magic);
        int status = input.readInt();
        int width = input.readInt();
        int height = input.readInt();
        int fps = input.readInt();
        int limit = input.readInt();
        int reserved = input.readInt();
        if (!Arrays.equals(magic, MAGIC) || reserved != 0) {
            throw new IOException("different physical camera protocol");
        }
        if (status == 1 && width == 0 && height == 0 && fps == 0 && limit == 0) {
            return false;
        }
        if (status != 0 || width != WIDTH || height != HEIGHT || fps != FPS || limit != MAX_JPEG) {
            throw new IOException("unexpected physical camera configuration");
        }
        return true;
    }

    static void validateHeader(long length, long sequence, long captureNs,
            long previousSequence, long previousCaptureNs, long nowNs) throws IOException {
        if (length < 4 || length > MAX_JPEG || sequence <= 0 || sequence <= previousSequence
                || captureNs <= 0 || captureNs <= previousCaptureNs) {
            throw new IOException("invalid or repeated physical frame");
        }
        validateFreshness(captureNs, nowNs);
    }

    static void validateFreshness(long captureNs, long nowNs) throws IOException {
        if (captureNs <= 0 || nowNs < captureNs || nowNs - captureNs > MAX_AGE_NS) {
            throw new IOException("physical capture timestamp is stale or in the future");
        }
    }
}
