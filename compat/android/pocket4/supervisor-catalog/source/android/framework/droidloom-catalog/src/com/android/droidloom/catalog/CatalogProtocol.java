/*
 * Copyright 2026 Droidloom
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
package com.android.droidloom.catalog;

import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

/** Bounded, single-request protocol for the root-only catalog socket. */
final class CatalogProtocol {
    static final byte[] MAGIC = "DLCAT001".getBytes(StandardCharsets.US_ASCII);
    static final int LIST = 1;
    static final int ICON = 2;
    static final int OK = 0;
    static final int INVALID = 1;
    static final int UNAVAILABLE = 2;
    static final int BUSY = 3;
    static final int OUTPUT_LIMIT = 4;
    static final int MAX_COMPONENT_BYTES = 511;
    static final int MAX_RESPONSE_BYTES = 2 * 1024 * 1024;
    static final int MAX_USER = Integer.MAX_VALUE / 100000;
    static final int REQUEST_TIMEOUT_MILLIS = 5000;

    private CatalogProtocol() {}

    static final class Request {
        final int operation;
        final int user;
        final int size;
        final String component;

        Request(int operation, int user, int size, String component) throws IOException {
            this.operation = operation;
            this.user = user;
            this.size = size;
            this.component = component;
            validate();
        }

        private void validate() throws IOException {
            if (user < 0 || user > MAX_USER || component == null) {
                throw new IOException("INVALID_REQUEST");
            }
            if (operation == LIST) {
                if (size != 0 || !component.isEmpty()) {
                    throw new IOException("INVALID_REQUEST");
                }
            } else if (operation == ICON) {
                if (size < 16 || size > 512 || !validComponent(component)) {
                    throw new IOException("INVALID_REQUEST");
                }
            } else {
                throw new IOException("INVALID_REQUEST");
            }
        }
    }

    static boolean validComponent(String value) {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        int slash = value.indexOf('/');
        if (bytes.length > MAX_COMPONENT_BYTES || slash <= 0
                || slash != value.lastIndexOf('/') || slash == value.length() - 1) {
            return false;
        }
        String owner = value.substring(0, slash);
        if (owner.length() > 255 || owner.indexOf('.') < 0) return false;
        for (int i = 0; i < owner.length(); i++) {
            char c = owner.charAt(i);
            if (!asciiAlphanumeric(c) && c != '.' && c != '_') return false;
        }
        for (int i = slash + 1; i < value.length(); i++) {
            char c = value.charAt(i);
            if (!asciiAlphanumeric(c) && c != '.' && c != '_' && c != '$') return false;
        }
        return true;
    }

    private static boolean asciiAlphanumeric(char c) {
        return c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9';
    }

    static Request readRequest(InputStream input) throws IOException {
        DataInputStream stream = new DataInputStream(input);
        byte[] magic = new byte[MAGIC.length];
        stream.readFully(magic);
        if (!Arrays.equals(magic, MAGIC)) throw new IOException("INVALID_REQUEST");
        int operation = stream.readUnsignedByte();
        int user = stream.readInt();
        int size = stream.readInt();
        int length = stream.readUnsignedShort();
        if (length > MAX_COMPONENT_BYTES) throw new IOException("INVALID_REQUEST");
        byte[] component = new byte[length];
        stream.readFully(component);
        String decoded = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(component)).toString();
        // A request is complete only after the client half-closes. No second
        // command, trailing bytes, or ambiguous line framing can be accepted.
        if (stream.read() != -1) throw new IOException("INVALID_REQUEST");
        return new Request(operation, user, size, decoded);
    }

    static void writeResponse(OutputStream output, int status, String payload) throws IOException {
        if (payload == null || payload.length() > MAX_RESPONSE_BYTES) {
            throw new IOException("INVALID_RESPONSE");
        }
        byte[] bytes = payload.getBytes(StandardCharsets.UTF_8);
        if (status < OK || status > OUTPUT_LIMIT || bytes.length == 0
                || bytes.length > MAX_RESPONSE_BYTES
                || status != OK && !errorText(status).equals(payload)) {
            throw new IOException("INVALID_RESPONSE");
        }
        DataOutputStream stream = new DataOutputStream(output);
        stream.write(MAGIC);
        stream.writeByte(status);
        stream.writeInt(bytes.length);
        stream.write(bytes);
        stream.flush();
    }

    static String errorText(int status) throws IOException {
        switch (status) {
            case INVALID: return "INVALID_REQUEST";
            case UNAVAILABLE: return "CATALOG_UNAVAILABLE";
            case BUSY: return "CATALOG_BUSY";
            case OUTPUT_LIMIT: return "CATALOG_OUTPUT_LIMIT";
            default: throw new IOException("INVALID_STATUS");
        }
    }

    static void writeError(OutputStream output, int status) throws IOException {
        writeResponse(output, status, errorText(status));
    }
}
