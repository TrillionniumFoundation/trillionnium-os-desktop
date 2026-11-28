/*
 * Copyright 2026 Droidloom
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
package com.android.droidloom.calendar;

import android.database.AbstractWindowedCursor;
import android.database.Cursor;
import android.database.CursorWindow;
import android.database.DatabaseErrorHandler;
import android.database.sqlite.SQLiteDatabase;
import android.os.ParcelFileDescriptor;
import android.system.Os;
import android.system.OsConstants;
import android.system.StructStat;

import java.io.FileDescriptor;
import java.nio.charset.StandardCharsets;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Fixed readonly Calendar database comparison for the factory-owned observer.
 *
 * The normal InputBridge target supplies this class. Its factory role fixes
 * user 0, provider UID/GID, the original Main, deadline and selected JAR.
 * No command line argument selects a path, statement, package or identity.
 * Counts are comparison data; this class cannot award an acceptance gate.
 */
public final class CalendarCounts {
    private static final int UID = 10017;
    private static final String PROVIDER = "com.android.providers.calendar";
    private static final String DATABASE =
            "/data/user/0/com.android.providers.calendar/databases/calendar.db";
    private static final String DATABASE_CONTEXT =
            "u:object_r:privapp_data_file:s0:c512,c768";
    private static final String SCHEMA = "droidloom.native-calendar-counts.android.v1";
    private static final String QUERY = "eight-table-counts-one-sqlite-statement.v1";
    private static final String[] TABLES = {
        "Calendars", "Events", "Reminders", "Attendees", "Instances",
        "CalendarAlerts", "EventsRawTimes", "ExtendedProperties"
    };
    // A single statement has one SQLite read snapshot, including existing WAL.
    // Android's execSQL("BEGIN") has separate session transaction semantics, so
    // this observer never issues a transaction command, PRAGMA, or other SQL.
    private static final String SQL =
            "SELECT 'Calendars' AS name,COUNT(*) AS count FROM Calendars UNION ALL "
            + "SELECT 'Events' AS name,COUNT(*) AS count FROM Events UNION ALL "
            + "SELECT 'Reminders' AS name,COUNT(*) AS count FROM Reminders UNION ALL "
            + "SELECT 'Attendees' AS name,COUNT(*) AS count FROM Attendees UNION ALL "
            + "SELECT 'Instances' AS name,COUNT(*) AS count FROM Instances UNION ALL "
            + "SELECT 'CalendarAlerts' AS name,COUNT(*) AS count FROM CalendarAlerts UNION ALL "
            + "SELECT 'EventsRawTimes' AS name,COUNT(*) AS count FROM EventsRawTimes UNION ALL "
            + "SELECT 'ExtendedProperties' AS name,COUNT(*) AS count FROM ExtendedProperties";

    private CalendarCounts() {}

    private static void need(boolean value, String reason) {
        if (!value) throw new IllegalStateException(reason);
    }

    private static void requireFile(StructStat value) {
        need(OsConstants.S_ISREG(value.st_mode) && value.st_uid == UID
                && value.st_nlink == 1
                && value.st_dev > 0 && value.st_ino > 0
                && (value.st_mode & 0400) != 0 && (value.st_mode & 0002) == 0
                && value.st_size >= 0, "Calendar database identity differs");
    }

    private static void sameFile(StructStat left, StructStat right) {
        requireFile(left);
        requireFile(right);
        // Preserve the original leaf's six-field inode identity. A legitimate
        // SQLite checkpoint can alter size/mtime/ctime; they are reported as
        // observations, never mislabeled as unchanged database contents.
        need(left.st_dev == right.st_dev && left.st_ino == right.st_ino
                && left.st_uid == right.st_uid && left.st_gid == right.st_gid
                && left.st_mode == right.st_mode && left.st_nlink == right.st_nlink,
                "Calendar database inode was replaced");
    }

    private static String context(FileDescriptor held, ParcelFileDescriptor duplicate,
            StructStat expected) throws Exception {
        sameFile(expected, Os.fstat(held));
        sameFile(expected, Os.fstat(duplicate.getFileDescriptor()));
        need(duplicate.getFd() >= 0, "Calendar database descriptor is closed");
        // The only pathname here is generated from our own still-owned dup of
        // the original database FD. It cannot select another application's file.
        final String descriptorPath = "/proc/self/fd/" + duplicate.getFd();
        sameFile(expected, Os.stat(descriptorPath));
        final byte[] label = Os.getxattr(descriptorPath, "security.selinux");
        final byte[] selected = DATABASE_CONTEXT.getBytes(StandardCharsets.US_ASCII);
        need(label.length == selected.length
                || (label.length == selected.length + 1 && label[label.length - 1] == 0),
                "Calendar database security context differs");
        for (int i = 0; i < selected.length; i++) {
            need(label[i] == selected[i], "Calendar database security context differs");
        }
        sameFile(expected, Os.fstat(held));
        sameFile(expected, Os.fstat(duplicate.getFileDescriptor()));
        sameFile(expected, Os.stat(descriptorPath));
        // Report actual xattr bytes after checking the fixed object context.
        return new String(label, 0, selected.length, StandardCharsets.US_ASCII);
    }

    private static JSONObject time(long seconds, long nanos) throws Exception {
        need(seconds >= 0 && nanos >= 0 && nanos < 1_000_000_000L,
                "Calendar database timestamp differs");
        return new JSONObject().put("seconds", seconds).put("nanos", nanos);
    }

    private static JSONObject state(StructStat value, String context) throws Exception {
        requireFile(value);
        return new JSONObject()
                .put("device", value.st_dev).put("inode", value.st_ino)
                .put("uid", value.st_uid).put("gid", value.st_gid)
                .put("mode", value.st_mode).put("links", value.st_nlink)
                .put("size", value.st_size).put("selinux", context)
                .put("mtime", time(value.st_mtim.tv_sec, value.st_mtim.tv_nsec))
                .put("ctime", time(value.st_ctim.tv_sec, value.st_ctim.tv_nsec));
    }

    private static JSONObject observe() throws Exception {
        need(Os.getuid() == UID && Os.geteuid() == UID
                && Os.getgid() == UID && Os.getegid() == UID,
                "Calendar observer identity differs");
        final FileDescriptor held = Os.open(DATABASE,
                OsConstants.O_RDONLY | OsConstants.O_CLOEXEC | OsConstants.O_NOFOLLOW, 0);
        try (ParcelFileDescriptor duplicate = ParcelFileDescriptor.dup(held)) {
            final StructStat before = Os.fstat(held);
            sameFile(before, Os.lstat(DATABASE));
            final String beforeContext = context(held, duplicate, before);
            final JSONArray rows = new JSONArray();
            final int windowRows;
            final int rowCount;
            // The default Android corruption handler may delete corrupt files.
            // Always fail without invoking that handler, recovery or recreation.
            final DatabaseErrorHandler rejectCorruption = database -> {
                throw new IllegalStateException("Calendar database corruption; no recovery");
            };
            final int flags = SQLiteDatabase.OPEN_READONLY
                    | SQLiteDatabase.NO_LOCALIZED_COLLATORS;
            try (SQLiteDatabase database = SQLiteDatabase.openDatabase(
                        DATABASE, null, flags, rejectCorruption);
                    Cursor cursor = database.rawQuery(SQL, null)) {
                need(database.isReadOnly(), "Calendar database is writable");
                sameFile(before, Os.fstat(held));
                sameFile(before, Os.lstat(DATABASE));
                need(cursor instanceof AbstractWindowedCursor,
                        "Calendar count cursor differs");
                need(cursor.getColumnCount() == 2
                        && "name".equals(cursor.getColumnName(0))
                        && "count".equals(cursor.getColumnName(1)),
                        "Calendar count columns differ");
                rowCount = cursor.getCount();
                final CursorWindow window = ((AbstractWindowedCursor) cursor).getWindow();
                need(window != null, "Calendar count window is absent");
                windowRows = window.getNumRows();
                need(rowCount == TABLES.length && window.getStartPosition() == 0
                        && windowRows == TABLES.length,
                        "Calendar counts are not one complete cursor window");
                for (int i = 0; i < TABLES.length; i++) {
                    need(cursor.moveToNext()
                            && cursor.getType(0) == Cursor.FIELD_TYPE_STRING
                            && cursor.getType(1) == Cursor.FIELD_TYPE_INTEGER
                            && TABLES[i].equals(cursor.getString(0)),
                            "Calendar count row differs");
                    final long count = cursor.getLong(1);
                    need(count >= 0, "Calendar count is negative");
                    rows.put(new JSONObject().put("name", TABLES[i]).put("count", count));
                }
                need(!cursor.moveToNext(), "Calendar count has extra rows");
                need(((AbstractWindowedCursor) cursor).getWindow() == window
                        && window.getStartPosition() == 0
                        && window.getNumRows() == TABLES.length,
                        "Calendar count cursor was refilled");
            }
            final StructStat after = Os.fstat(held);
            sameFile(before, after);
            sameFile(after, Os.lstat(DATABASE));
            final String afterContext = context(held, duplicate, after);
            need(beforeContext.equals(afterContext), "Calendar database was relabeled");
            return new JSONObject()
                    .put("schema", SCHEMA).put("provider", PROVIDER)
                    .put("user", 0).put("observer_uid", UID).put("observer_gid", UID)
                    .put("database", DATABASE).put("read_only", true).put("query", QUERY)
                    .put("cursor_rows", rowCount).put("window_rows", windowRows)
                    .put("before", state(before, beforeContext)).put("after", state(after, afterContext))
                    .put("tables", rows);
        } finally {
            Os.close(held);
        }
    }

    public static void main(String[] args) {
        try {
            need(args.length == 0, "Calendar count observer takes no arguments");
            final byte[] output = (observe().toString() + "\n").getBytes(StandardCharsets.UTF_8);
            need(output.length > 0 && output.length <= 8192,
                    "Calendar count output exceeds its fixed bound");
            System.out.write(output);
            System.out.flush();
            need(!System.out.checkError(), "Calendar count output failed");
        } catch (Throwable failure) {
            // Do not print database contents, SQL values or exception messages.
            System.err.println("Calendar count observer failed: "
                    + failure.getClass().getSimpleName());
            System.exit(1);
        }
    }
}
