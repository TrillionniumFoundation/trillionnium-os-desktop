/*
 * Copyright 2026 Droidloom
 * SPDX-License-Identifier: GPL-3.0-or-later
 * See LICENSE and LICENSES/GPL-3.0-or-later.txt for the license terms.
 */

package com.android.droidloom.catalog;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.PorterDuff;
import android.graphics.drawable.Drawable;
import android.os.Looper;
import android.util.Base64;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.FileDescriptor;
import java.io.FileOutputStream;
import java.io.PrintStream;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * One-shot framework adapter for Droidloom's unprivileged host catalog.
 *
 * <p>Android remains authoritative for intent resolution, localized labels,
 * adaptive icons, and per-user package state. The host receives only a bounded
 * JSON snapshot or one rendered PNG and never parses APK resources itself.</p>
 */
public final class ApplicationCatalog {
    private static final int MIN_ICON_SIZE = 16;
    private static final int MAX_ICON_SIZE = 512;
    private static final Set<String> HIDDEN_PACKAGES = new HashSet<>(Arrays.asList(
            "android.droidloom.bootstrap",
            "com.android.launcher3",
            "com.android.systemui"
    ));

    private ApplicationCatalog() {}

    public static void main(String[] arguments) {
        try {
            // RuntimeInit redirects System.out and System.err to logcat before
            // invoking app_process entry points. Droidloom uses this class as
            // a one-shot pipe adapter, so preserve the inherited Unix streams.
            PrintStream output = new PrintStream(new FileOutputStream(FileDescriptor.out), true);
            output.println(execute(arguments));
            output.flush();
            System.exit(0);
        } catch (Throwable error) {
            PrintStream errors = new PrintStream(new FileOutputStream(FileDescriptor.err), true);
            error.printStackTrace(errors);
            errors.flush();
            System.exit(1);
        }
    }

    private static String execute(String[] arguments) throws Exception {
        if (arguments.length == 3 && "list".equals(arguments[0])
                && "--user".equals(arguments[1])) {
            return listApplications(parseUser(arguments[2])).toString();
        }
        if (arguments.length == 7 && "icon".equals(arguments[0])
                && "--user".equals(arguments[1])
                && "--component".equals(arguments[3])
                && "--size".equals(arguments[5])) {
            int user = parseUser(arguments[2]);
            ComponentName component = ComponentName.unflattenFromString(arguments[4]);
            if (component == null) {
                throw new IllegalArgumentException("invalid flattened component");
            }
            int size = Integer.parseInt(arguments[6]);
            if (size < MIN_ICON_SIZE || size > MAX_ICON_SIZE) {
                throw new IllegalArgumentException("icon size is outside the supported range");
            }
            return renderIcon(user, component, size);
        }
        throw new IllegalArgumentException(
                "usage: ApplicationCatalog list --user ID | "
                        + "icon --user ID --component PACKAGE/ACTIVITY --size PIXELS");
    }

    private static int parseUser(String value) {
        int user = Integer.parseInt(value);
        if (user < 0) {
            throw new IllegalArgumentException("Android user must be non-negative");
        }
        return user;
    }

    private static JSONArray listApplications(int userId) throws Exception {
        Context context = systemContext();
        PackageManager packageManager = context.getPackageManager();
        List<ResolveInfo> activities = new ArrayList<>(
                queryLauncherActivities(packageManager, userId, null));
        activities.removeIf(new java.util.function.Predicate<ResolveInfo>() {
            @Override public boolean test(ResolveInfo activity) {
                return HIDDEN_PACKAGES.contains(activity.activityInfo.packageName);
            }
        });
        activities.sort(new Comparator<ResolveInfo>() {
            @Override public int compare(ResolveInfo first, ResolveInfo second) {
                return component(first).flattenToString().compareTo(
                        component(second).flattenToString());
            }
        });

        JSONArray result = new JSONArray();
        for (ResolveInfo activity : activities) {
            ComponentName component = component(activity);
            CharSequence loadedLabel = activity.loadLabel(packageManager);
            String label = loadedLabel == null ? component.getPackageName()
                    : loadedLabel.toString();
            if (label.isEmpty()) {
                label = component.getPackageName();
            }
            JSONObject entry = new JSONObject();
            entry.put("name", label);
            entry.put("package", component.getPackageName());
            entry.put("component", component.flattenToString());
            entry.put("icon_key", iconKey(packageManager, component));
            result.put(entry);
        }
        return result;
    }

    private static String renderIcon(int userId, ComponentName requested, int size)
            throws Exception {
        if (HIDDEN_PACKAGES.contains(requested.getPackageName())) {
            throw new IllegalArgumentException("component is hidden from the host launcher");
        }
        Context context = systemContext();
        PackageManager packageManager = context.getPackageManager();
        ResolveInfo selected = null;
        for (ResolveInfo activity
                : queryLauncherActivities(packageManager, userId, requested.getPackageName())) {
            if (requested.equals(component(activity))) {
                selected = activity;
                break;
            }
        }
        if (selected == null) {
            throw new IllegalArgumentException("component is not an enabled launcher activity");
        }

        Drawable drawable = selected.loadIcon(packageManager);
        if (drawable == null) {
            drawable = packageManager.getDefaultActivityIcon();
        }
        Bitmap bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(bitmap);
        canvas.drawColor(Color.TRANSPARENT, PorterDuff.Mode.CLEAR);
        setCenteredBounds(drawable, size);
        drawable.draw(canvas);
        ByteArrayOutputStream encoded = new ByteArrayOutputStream();
        if (!bitmap.compress(Bitmap.CompressFormat.PNG, 100, encoded)) {
            bitmap.recycle();
            throw new IllegalStateException("failed to encode launcher icon");
        }
        bitmap.recycle();
        return Base64.encodeToString(encoded.toByteArray(), Base64.NO_WRAP);
    }

    /** Resident path: fresh PM data with bounds before copying or encoding. */
    static String listApplicationsBounded(Context context, int userId, String configurationKey)
            throws Exception {
        if (configurationKey == null || !configurationKey.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("INVALID_CONFIGURATION_KEY");
        }
        PackageManager packageManager = context.getPackageManager();
        List<ResolveInfo> activities = boundedActivities(packageManager, userId, null);
        activities.sort(new Comparator<ResolveInfo>() {
            @Override public int compare(ResolveInfo first, ResolveInfo second) {
                return component(first).flattenToString().compareTo(
                        component(second).flattenToString());
            }
        });
        CatalogBudget result = new CatalogBudget();
        for (ResolveInfo activity : activities) {
            ComponentName component = component(activity);
            String label = CatalogBudget.label(
                    activity.loadLabel(packageManager), component.getPackageName());
            result.add(label, component.getPackageName(), component.flattenToString(),
                    iconKey(packageManager, component) + ":" + configurationKey);
        }
        return result.finish();
    }

    static String renderIconBounded(Context context, int userId, ComponentName requested, int size)
            throws Exception {
        if (size < MIN_ICON_SIZE || size > MAX_ICON_SIZE
                || HIDDEN_PACKAGES.contains(requested.getPackageName())) {
            throw new IllegalArgumentException("INVALID_ICON_REQUEST");
        }
        PackageManager packageManager = context.getPackageManager();
        ResolveInfo selected = null;
        for (ResolveInfo activity : boundedActivities(
                packageManager, userId, requested.getPackageName())) {
            if (requested.equals(component(activity))) {
                selected = activity;
                break;
            }
        }
        if (selected == null) {
            throw new IllegalArgumentException("COMPONENT_NOT_ENABLED");
        }
        Drawable drawable = selected.loadIcon(packageManager);
        if (drawable == null) drawable = packageManager.getDefaultActivityIcon();
        Bitmap bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
        try {
            Canvas canvas = new Canvas(bitmap);
            canvas.drawColor(Color.TRANSPARENT, PorterDuff.Mode.CLEAR);
            setCenteredBounds(drawable, size);
            drawable.draw(canvas);
            CatalogBudget.PngBytes encoded = new CatalogBudget.PngBytes();
            if (!bitmap.compress(Bitmap.CompressFormat.PNG, 100, encoded)) {
                throw new IllegalStateException("ICON_ENCODING_UNAVAILABLE");
            }
            return Base64.encodeToString(encoded.toByteArray(), Base64.NO_WRAP);
        } finally {
            bitmap.recycle();
        }
    }

    private static List<ResolveInfo> boundedActivities(
            PackageManager packageManager, int userId, String packageName) throws Exception {
        List<ResolveInfo> observed = queryLauncherActivities(packageManager, userId, packageName);
        if (observed == null || observed.size() > CatalogBudget.MAX_SCANNED_ACTIVITIES) {
            throw new CatalogBudget.OutputLimit();
        }
        List<ResolveInfo> activities = new ArrayList<>();
        for (ResolveInfo activity : observed) {
            if (activity == null || activity.activityInfo == null) {
                throw new IllegalArgumentException("INCOMPLETE_ACTIVITY");
            }
            ActivityInfo info = activity.activityInfo;
            if (info.packageName == null || info.name == null
                    || info.packageName.length() > 255
                    || info.name.length() > CatalogProtocol.MAX_COMPONENT_BYTES) {
                throw new CatalogBudget.OutputLimit();
            }
            if (HIDDEN_PACKAGES.contains(info.packageName)) continue;
            String flattened = component(activity).flattenToString();
            if (!CatalogProtocol.validComponent(flattened)
                    || activities.size() >= CatalogBudget.MAX_ACTIVITIES) {
                throw new CatalogBudget.OutputLimit();
            }
            activities.add(activity);
        }
        return activities;
    }

    @SuppressWarnings("deprecation")
    private static String iconKey(PackageManager packageManager, ComponentName component)
            throws PackageManager.NameNotFoundException {
        PackageInfo packageInfo = packageManager.getPackageInfo(component.getPackageName(), 0);
        ActivityInfo activityInfo = packageManager.getActivityInfo(component, 0);
        return Long.toUnsignedString(packageInfo.getLongVersionCode()) + ":"
                + Long.toUnsignedString(packageInfo.lastUpdateTime) + ":"
                + Integer.toUnsignedString(activityInfo.getIconResource());
    }

    private static void setCenteredBounds(Drawable drawable, int size) {
        int width = drawable.getIntrinsicWidth();
        int height = drawable.getIntrinsicHeight();
        if (width <= 0 || height <= 0) {
            drawable.setBounds(0, 0, size, size);
            return;
        }
        float scale = Math.min((float) size / width, (float) size / height);
        int renderedWidth = Math.max(1, Math.round(width * scale));
        int renderedHeight = Math.max(1, Math.round(height * scale));
        int left = (size - renderedWidth) / 2;
        int top = (size - renderedHeight) / 2;
        drawable.setBounds(left, top, left + renderedWidth, top + renderedHeight);
    }

    private static ComponentName component(ResolveInfo activity) {
        ActivityInfo info = activity.activityInfo;
        if (info == null || info.packageName == null || info.name == null) {
            throw new IllegalArgumentException("package manager returned an incomplete activity");
        }
        return new ComponentName(info.packageName, info.name);
    }

    @SuppressWarnings("unchecked")
    private static List<ResolveInfo> queryLauncherActivities(
            PackageManager packageManager, int userId, String packageName) throws Exception {
        Intent launcher = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
        if (packageName != null) {
            launcher.setPackage(packageName);
        }
        // Droidloom's current cell runs its framework tools in Android user 0.
        // Keep that hot path entirely on the public SDK; the reflected system
        // API is reserved for future explicitly requested secondary users.
        if (userId == 0) {
            return packageManager.queryIntentActivities(launcher, 0);
        }
        Method query = packageManager.getClass().getMethod(
                "queryIntentActivitiesAsUser", Intent.class, int.class, int.class);
        query.setAccessible(true);
        return (List<ResolveInfo>) query.invoke(packageManager, launcher, 0, userId);
    }

    static Context systemContext() throws Exception {
        // app_process does not create an Application. Obtain Android's system
        // context through its framework bootstrap without teaching Linux how
        // to parse Android packages or resources.
        if (Looper.myLooper() == null) {
            Looper.prepareMainLooper();
        }
        Class<?> activityThreadClass = Class.forName("android.app.ActivityThread");
        Method systemMain = activityThreadClass.getDeclaredMethod("systemMain");
        systemMain.setAccessible(true);
        Object activityThread = systemMain.invoke(null);
        Method getSystemContext = activityThreadClass.getDeclaredMethod("getSystemContext");
        getSystemContext.setAccessible(true);
        return (Context) getSystemContext.invoke(activityThread);
    }
}
