/*
 * Copyright 2026 Droidloom
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
package com.android.droidloom.catalog;

import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.os.IBinder;
import android.os.Process;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.FileDescriptor;
import java.io.FileOutputStream;
import java.io.PrintStream;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

/**
 * Complete selected user-zero AppOps comparison, using the actual scoped Binder
 * API rather than the shell rendering that omits UID/package row boundaries.
 * No mutation, historical access data, account data or caller-selected UID.
 * Installed normal JAR bytes and the query's retirement are verified by its
 * original host owner. This JSON is comparison data, never runtime authority.
 */
public final class ApplicationAppOpsState {
    private static final int OP_COUNT = 181;
    private static final int OUTPUT_BYTES = 131072;
    private static final String SCHEMA = "droidloom.application-appops-android.v1";
    // This exact roster is checked against the source-owned Rust selection.
    private static final Set<String> PACKAGES = new HashSet<>(Arrays.asList(
            "com.Hyatt.hyt",
            "com.MobileTicket",
            "com.amazon.mShop.android.shopping",
            "com.android.calendar",
            "com.android.camera2",
            "com.android.contacts",
            "com.android.deskclock",
            "com.android.dialer",
            "com.android.documentsui",
            "com.android.gallery3d",
            "com.android.messaging",
            "com.android.quicksearchbox",
            "com.android.settings",
            "com.bestbuy.android",
            "com.ehi.national.mobile",
            "com.google.android.gms",
            "com.hertz.android.digital",
            "com.hilton.android.hhonors",
            "com.ihg.apps.android",
            "com.jingdong.app.mall",
            "com.lianjia.beike",
            "com.marriott.mrt",
            "com.rytong.airchina",
            "com.rytong.ceair",
            "com.sankuai.meituan.takeoutnew",
            "com.sdu.didi.psnger",
            "com.ss.android.ugc.aweme",
            "com.szzc",
            "com.taobao.taobao",
            "com.tencent.mm",
            "com.united.mobile.android",
            "com.xunmeng.pinduoduo",
            "com.zhubajie.client",
            "com.zillow.android.streeteasy",
            "ctrip.android.view",
            "jp.co.ana.android.tabidachi",
            "org.fcitx.fcitx5.android",
            "org.mozilla.firefox",
            "tv.danmaku.bili"
    ));

    private ApplicationAppOpsState() {}

    public static void main(String[] arguments) {
        try {
            require(arguments.length == 1 && PACKAGES.contains(arguments[0]),
                    "one source-selected package is required");
            require(Process.myUid() == 2000, "the normal observer must remain Android shell");
            String result = observe(arguments[0]).toString();
            require(result.getBytes(StandardCharsets.UTF_8).length + 1 <= OUTPUT_BYTES,
                    "complete AppOps output exceeds its bound");
            PrintStream output = new PrintStream(new FileOutputStream(FileDescriptor.out), true);
            output.println(result);
            output.flush();
            require(!output.checkError(), "complete AppOps output could not be written");
            System.exit(0);
        } catch (Throwable error) {
            PrintStream errors = new PrintStream(new FileOutputStream(FileDescriptor.err), true);
            error.printStackTrace(errors);
            errors.flush();
            System.exit(1);
        }
    }

    private static void require(boolean value, String reason) {
        if (!value) throw new IllegalStateException(reason);
    }

    private static final class Identity {
        final String packageName;
        final int uid;
        final long version;
        final TreeSet<String> paths;
        Identity(String packageName, PackageManager manager) throws Exception {
            PackageInfo info = manager.getPackageInfo(packageName, 0);
            ApplicationInfo app = info.applicationInfo;
            require(info.packageName.equals(packageName) && app != null
                    && app.packageName.equals(packageName) && app.uid > 0 && app.uid < 100000,
                    "selected actual user-zero package identity differs");
            this.packageName = packageName;
            uid = app.uid;
            version = info.getLongVersionCode();
            require(version >= 0, "negative package version");
            paths = new TreeSet<>();
            addPath(app.sourceDir);
            if (app.splitSourceDirs != null) {
                require(app.splitSourceDirs.length < 128, "too many installed split paths");
                for (String path : app.splitSourceDirs) addPath(path);
            }
        }
        private void addPath(String path) {
            require(path != null && path.startsWith("/") && !path.endsWith("/")
                    && path.length() <= 4096 && !path.contains("//")
                    && !path.contains("/../") && !path.contains("/./")
                    && path.chars().noneMatch(c -> c < 32 || c == 127)
                    && paths.add(path), "installed code path is incomplete or duplicated");
        }
        boolean same(Identity other) {
            return packageName.equals(other.packageName) && uid == other.uid
                    && version == other.version && paths.equals(other.paths);
        }
    }

    private static final class Snapshot {
        final Identity identity;
        final TreeMap<Integer, Integer> defaults = new TreeMap<>();
        final TreeMap<Integer, String> names = new TreeMap<>();
        final TreeMap<Integer, Integer> uidModes;
        final TreeMap<Integer, Integer> packageModes;
        Snapshot(String packageName, PackageManager packages, Object service,
                Method uidQuery, Method packageQuery, Class<?> manager,
                Class<?> packageOps, Class<?> opEntry) throws Exception {
            identity = new Identity(packageName, packages);
            Method defaultMode = manager.getDeclaredMethod("opToDefaultMode", int.class);
            Method opName = manager.getDeclaredMethod("opToName", int.class);
            defaultMode.setAccessible(true);
            opName.setAccessible(true);
            Set<String> distinct = new HashSet<>();
            for (int op = 0; op < OP_COUNT; op++) {
                int mode = (Integer) defaultMode.invoke(null, op);
                String name = (String) opName.invoke(null, op);
                require(validMode(mode) && name != null
                        && name.matches("[A-Z][A-Z0-9_]{0,127}") && distinct.add(name),
                        "actual complete AppOps default table differs");
                defaults.put(op, mode);
                names.put(op, name);
            }
            uidModes = modes(uidQuery.invoke(service, identity.uid, (Object) null),
                    null, identity.uid, packageOps, opEntry);
            packageModes = modes(packageQuery.invoke(service, identity.uid,
                    packageName, (Object) null), packageName, identity.uid, packageOps, opEntry);
            require(identity.same(new Identity(packageName, packages)),
                    "actual package identity changed during AppOps reads");
        }

        TreeMap<Integer, Integer> packageOverrides() {
            TreeMap<Integer, Integer> result = new TreeMap<>(packageModes);
            result.entrySet().removeIf(e -> Objects.equals(defaults.get(e.getKey()), e.getValue()));
            return result;
        }

        boolean same(Snapshot other) {
            // The service may add default-mode OpEntry records for normal access.
            // Keep every actual UID override; normalize only package records
            // equal to the complete defaults read in this same actual framework.
            return identity.same(other.identity) && defaults.equals(other.defaults)
                    && names.equals(other.names) && uidModes.equals(other.uidModes)
                    && packageOverrides().equals(other.packageOverrides());
        }

        JSONObject json() throws Exception {
            JSONObject value = new JSONObject();
            value.put("schema", SCHEMA);
            value.put("observer_uid", Process.myUid());
            value.put("user", 0);
            value.put("package", identity.packageName);
            value.put("uid", identity.uid);
            value.put("version_code", identity.version);
            value.put("source_paths", new JSONArray(identity.paths));
            JSONArray defaultRows = new JSONArray();
            for (Map.Entry<Integer, Integer> row : defaults.entrySet()) {
                JSONObject item = new JSONObject();
                item.put("op", row.getKey());
                item.put("name", names.get(row.getKey()));
                item.put("mode", row.getValue());
                defaultRows.put(item);
            }
            value.put("defaults", defaultRows);
            value.put("uid_modes", rows(uidModes));
            // Preserve actual package rows on the wire; Rust independently
            // validates and normalizes them. No timestamps are read or hidden.
            value.put("package_modes", rows(packageModes));
            value.put("samples", 2);
            return value;
        }
    }

    private static boolean validMode(int value) {
        return value >= 0 && value <= 4;
    }

    private static TreeMap<Integer, Integer> modes(Object result, String packageName,
            int uid, Class<?> packageOps, Class<?> opEntry) throws Exception {
        TreeMap<Integer, Integer> modes = new TreeMap<>();
        // These two selected service methods return null for no stored modes;
        // Binder failures and permission failures throw and are never caught
        // as an empty set by this adapter.
        if (result == null) return modes;
        require(result instanceof List<?>, "AppOps response is not a complete list");
        List<?> packages = (List<?>) result;
        require(packages.size() <= 1, "foreign or duplicate AppOps package scope");
        for (Object item : packages) {
            require(packageOps.isInstance(item), "unknown AppOps package row");
            int actualUid = (Integer) packageOps.getMethod("getUid").invoke(item);
            String actualPackage = (String) packageOps.getMethod("getPackageName").invoke(item);
            require(actualUid == uid && Objects.equals(actualPackage, packageName),
                    "actual AppOps UID/package boundary differs");
            Object raw = packageOps.getMethod("getOps").invoke(item);
            require(raw instanceof List<?>, "AppOps entries are incomplete");
            List<?> entries = (List<?>) raw;
            require(entries.size() <= OP_COUNT, "AppOps entry count exceeds selected framework");
            for (Object entry : entries) {
                require(opEntry.isInstance(entry), "unknown AppOps operation row");
                int op = (Integer) opEntry.getMethod("getOp").invoke(entry);
                int mode = (Integer) opEntry.getMethod("getMode").invoke(entry);
                require(op >= 0 && op < OP_COUNT && validMode(mode)
                        && modes.put(op, mode) == null, "duplicate or invalid actual AppOps mode");
            }
        }
        return modes;
    }

    private static JSONArray rows(TreeMap<Integer, Integer> values) throws Exception {
        JSONArray result = new JSONArray();
        for (Map.Entry<Integer, Integer> row : values.entrySet()) {
            JSONObject value = new JSONObject();
            value.put("op", row.getKey());
            value.put("mode", row.getValue());
            result.put(value);
        }
        return result;
    }

    private static JSONObject observe(String packageName) throws Exception {
        PackageManager packages = ApplicationCatalog.systemContext().getPackageManager();
        Class<?> manager = Class.forName("android.app.AppOpsManager");
        Field opCount = manager.getDeclaredField("_NUM_OP");
        opCount.setAccessible(true);
        require(opCount.getInt(null) == OP_COUNT, "selected framework AppOps roster changed");
        Class<?> services = Class.forName("android.os.ServiceManager");
        IBinder binder = (IBinder) services.getDeclaredMethod("getService", String.class)
                .invoke(null, "appops");
        require(binder != null && binder.isBinderAlive() && binder.pingBinder(),
                "actual AppOps service is not live");
        Class<?> stub = Class.forName("com.android.internal.app.IAppOpsService$Stub");
        Object service = stub.getMethod("asInterface", IBinder.class).invoke(null, binder);
        Class<?> api = Class.forName("com.android.internal.app.IAppOpsService");
        require(service != null && api.isInstance(service), "actual AppOps interface is absent");
        Method uidQuery = api.getMethod("getUidOps", int.class, int[].class);
        Method packageQuery = api.getMethod("getOpsForPackage", int.class, String.class, int[].class);
        Class<?> packageOps = Class.forName("android.app.AppOpsManager$PackageOps");
        Class<?> opEntry = Class.forName("android.app.AppOpsManager$OpEntry");
        Snapshot before = new Snapshot(packageName, packages, service, uidQuery,
                packageQuery, manager, packageOps, opEntry);
        Snapshot after = new Snapshot(packageName, packages, service, uidQuery,
                packageQuery, manager, packageOps, opEntry);
        require(before.same(after) && binder.isBinderAlive() && binder.pingBinder(),
                "complete AppOps modes/defaults or actual service changed during observation");
        return after.json();
    }
}
