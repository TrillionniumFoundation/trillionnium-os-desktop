/*
 * Copyright 2026 Droidloom
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
package com.android.droidloom.catalog;

import java.io.ByteArrayOutputStream;

/** Bounds resident-query construction before copying labels or appending JSON. */
final class CatalogBudget {
    static final int MAX_ACTIVITIES = 1024;
    static final int MAX_SCANNED_ACTIVITIES = 4096;
    static final int MAX_LABEL_BYTES = 1024;
    static final int MAX_ICON_KEY_BYTES = 128;
    static final int MAX_PNG_BYTES = CatalogProtocol.MAX_RESPONSE_BYTES / 4 * 3;
    private static final String NAME = "{\"name\":";
    private static final String PACKAGE = ",\"package\":";
    private static final String COMPONENT = ",\"component\":";
    private static final String ICON_KEY = ",\"icon_key\":";
    private static final char[] HEX = "0123456789abcdef".toCharArray();

    static final class OutputLimit extends RuntimeException {
        OutputLimit() { super("CATALOG_OUTPUT_LIMIT"); }
    }

    private final StringBuilder result = new StringBuilder("[");
    private int bytes = 2; // Include the closing bracket before admitting entries.
    private int entries;
    private boolean finished;

    static String label(CharSequence loaded, String fallback) {
        if (loaded == null || loaded.length() == 0) return fallback;
        if (loaded.length() > MAX_LABEL_BYTES) throw new OutputLimit();
        String value = loaded.toString();
        utf8Size(value, MAX_LABEL_BYTES);
        return value.isEmpty() ? fallback : value;
    }

    static int utf8Size(CharSequence value, int limit) {
        if (value == null || value.length() > limit) throw new OutputLimit();
        int bytes = 0;
        for (int index = 0; index < value.length(); index++) {
            char c = value.charAt(index);
            if (Character.isHighSurrogate(c)) {
                if (++index >= value.length()
                        || !Character.isLowSurrogate(value.charAt(index))) {
                    throw new OutputLimit();
                }
                bytes += 4;
            } else if (Character.isLowSurrogate(c)) {
                throw new OutputLimit();
            } else {
                bytes += c < 0x80 ? 1 : c < 0x800 ? 2 : 3;
            }
            if (bytes > limit) throw new OutputLimit();
        }
        return bytes;
    }

    void add(String name, String owner, String component, String iconKey) {
        if (finished || entries >= MAX_ACTIVITIES || name == null || name.isEmpty()
                || name.indexOf('\0') >= 0 || owner == null || owner.length() > 255
                || component == null || component.length() > CatalogProtocol.MAX_COMPONENT_BYTES
                || !CatalogProtocol.validComponent(component)
                || !component.startsWith(owner + "/")
                || iconKey == null || iconKey.isEmpty()
                || iconKey.length() > MAX_ICON_KEY_BYTES) {
            throw new OutputLimit();
        }
        utf8Size(name, MAX_LABEL_BYTES);
        for (int index = 0; index < iconKey.length(); index++) {
            char c = iconKey.charAt(index);
            if (!(c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z'
                    || c >= '0' && c <= '9' || c == '.' || c == '_'
                    || c == '-' || c == ':')) throw new OutputLimit();
        }
        int added = NAME.length() + PACKAGE.length() + COMPONENT.length() + ICON_KEY.length()
                + 1 + (entries == 0 ? 0 : 1)
                + quotedBytes(name) + quotedBytes(owner)
                + quotedBytes(component) + quotedBytes(iconKey);
        if (added > CatalogProtocol.MAX_RESPONSE_BYTES - bytes) throw new OutputLimit();
        if (entries != 0) result.append(',');
        result.append(NAME); appendQuoted(name);
        result.append(PACKAGE); appendQuoted(owner);
        result.append(COMPONENT); appendQuoted(component);
        result.append(ICON_KEY); appendQuoted(iconKey);
        result.append('}');
        bytes += added;
        entries++;
    }

    String finish() {
        if (finished) throw new OutputLimit();
        finished = true;
        return result.append(']').toString();
    }

    private static int quotedBytes(String value) {
        int bytes = 2;
        for (int index = 0; index < value.length(); index++) {
            char c = value.charAt(index);
            if (c == '"' || c == '\\') bytes += 2;
            else if (c < 0x20) bytes += 6;
            else if (Character.isHighSurrogate(c)) { index++; bytes += 4; }
            else bytes += c < 0x80 ? 1 : c < 0x800 ? 2 : 3;
        }
        return bytes;
    }

    private void appendQuoted(String value) {
        result.append('"');
        for (int index = 0; index < value.length(); index++) {
            char c = value.charAt(index);
            if (c == '"' || c == '\\') result.append('\\').append(c);
            else if (c < 0x20) {
                result.append('\\').append('u').append('0').append('0')
                        .append(HEX[c >>> 4]).append(HEX[c & 15]);
            } else result.append(c);
        }
        result.append('"');
    }

    /** Bitmap compression cannot grow an unbounded intermediate byte array. */
    static final class PngBytes extends ByteArrayOutputStream {
        PngBytes() { super(4096); }

        private void admit(int length) {
            if (length < 0 || length > MAX_PNG_BYTES - count) throw new OutputLimit();
        }

        @Override
        public synchronized void write(int value) {
            admit(1);
            super.write(value);
        }

        @Override
        public synchronized void write(byte[] bytes, int offset, int length) {
            if (offset < 0 || length < 0 || offset > bytes.length - length) {
                throw new IndexOutOfBoundsException();
            }
            admit(length);
            super.write(bytes, offset, length);
        }
    }
}
