// SPDX-License-Identifier: GPL-3.0-or-later
package com.droidloom.camera;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.util.Arrays;

/** Bounded real byte-stream checks, run by the normal host compiler preflight. */
public final class CameraProtocolTest {
    private static int checked;
    private interface Operation { void run() throws Exception; }
    private static void rejected(Operation operation) throws Exception {
        try {
            operation.run();
        } catch (IOException expected) {
            checked++;
            return;
        }
        throw new AssertionError("malformed input accepted");
    }
    private static byte[] response(int status, int width, int height, int fps, int limit, int reserved)
            throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        out.write(new byte[] {'D','L','C','A','M','0','1',0});
        for (int value : new int[] {status,width,height,fps,limit,reserved}) out.writeInt(value);
        return bytes.toByteArray();
    }
    private static boolean reply(byte[] bytes) throws IOException {
        return CameraProtocol.reply(new DataInputStream(new ByteArrayInputStream(bytes)));
    }
    public static void main(String[] args) throws Exception {
        byte[] available = response(0,640,480,30,4194304,0);
        if (!reply(available) || reply(response(1,0,0,0,0,0))) throw new AssertionError();
        checked += 2;
        for (int size = 0; size < 32; size++) {
            byte[] truncated = Arrays.copyOf(available,size);
            rejected(() -> reply(truncated));
        }
        for (int field : new int[] {8,12,16,20,24,28}) {
            byte[] changed = available.clone();
            changed[field + 3] ^= 1;
            rejected(() -> reply(changed));
        }
        byte[] magic = available.clone(); magic[0] = 'X';
        rejected(() -> reply(magic));
        rejected(() -> reply(response(1,640,0,0,0,0)));
        rejected(() -> reply(response(2,0,0,0,0,0)));
        for (int op : new int[] {1,2}) {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            CameraProtocol.request(bytes,op);
            byte[] expected = new byte[] {'D','L','C','A','M','0','1',0,0,0,0,(byte)op};
            if (!Arrays.equals(bytes.toByteArray(),expected)) throw new AssertionError();
            checked++;
        }
        rejected(() -> CameraProtocol.request(new ByteArrayOutputStream(),0));
        CameraProtocol.validateHeader(4,1,1,0,0,1_000_000_001L);
        CameraProtocol.validateHeader(4194304,2,2,1,1,2);
        checked += 2;
        rejected(() -> CameraProtocol.validateHeader(3,1,1,0,0,1));
        rejected(() -> CameraProtocol.validateHeader(4194305,1,1,0,0,1));
        rejected(() -> CameraProtocol.validateHeader(4,1,2,1,1,2));
        rejected(() -> CameraProtocol.validateHeader(4,-1,2,0,1,2));
        rejected(() -> CameraProtocol.validateHeader(4,2,1,1,1,2));
        rejected(() -> CameraProtocol.validateHeader(4,2,3,1,1,2));
        rejected(() -> CameraProtocol.validateHeader(4,2,1,1,0,1_000_000_002L));
        System.out.println("CameraProtocolTest passed=" + checked + " hardware_qualified=false");
    }
}
