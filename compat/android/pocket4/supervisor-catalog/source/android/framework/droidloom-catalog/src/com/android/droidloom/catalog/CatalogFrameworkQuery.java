/*
 * Copyright 2026 Droidloom
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
package com.android.droidloom.catalog;

import android.content.ComponentName;
import android.content.Context;
import android.content.res.Configuration;
import android.os.IBinder;

import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/** Runs only on the catalog Looper; never returns a previous query result. */
final class CatalogFrameworkQuery implements CatalogSession.Query {
    private Context systemContext;

    @Override
    public String execute(CatalogProtocol.Request request) throws Exception {
        if (systemContext == null) systemContext = ApplicationCatalog.systemContext();
        Configuration before = configuration();
        applyConfiguration(before);
        Context context = systemContext.createConfigurationContext(before);
        if (request.user != 0) {
            Class<?> userHandle = Class.forName("android.os.UserHandle");
            Object user = userHandle.getMethod("of", int.class).invoke(null, request.user);
            context = (Context) Context.class.getMethod("createContextAsUser", userHandle, int.class)
                    .invoke(context, user, 0);
        }
        final String result;
        if (request.operation == CatalogProtocol.LIST) {
            result = ApplicationCatalog.listApplicationsBounded(
                    context, request.user, configurationKey(before));
        } else {
            ComponentName component = ComponentName.unflattenFromString(request.component);
            if (component == null) throw new IllegalArgumentException("INVALID_COMPONENT");
            result = ApplicationCatalog.renderIconBounded(context, request.user, component, request.size);
        }
        if (!before.equals(configuration())) {
            // Do not publish a result spanning a locale, density, overlay, or
            // other global configuration change. A later caller may ask again.
            throw new IllegalStateException("CATALOG_CONFIGURATION_CHANGED");
        }
        return result;
    }

    private static Configuration configuration() throws Exception {
        Class<?> serviceManager = Class.forName("android.os.ServiceManager");
        IBinder binder = (IBinder) serviceManager.getMethod("getService", String.class)
                .invoke(null, "activity");
        if (binder == null || !binder.isBinderAlive()) {
            throw new IllegalStateException("CATALOG_CONFIGURATION_UNAVAILABLE");
        }
        Class<?> stub = Class.forName("android.app.IActivityManager$Stub");
        Object service = stub.getMethod("asInterface", IBinder.class).invoke(null, binder);
        Object result = Class.forName("android.app.IActivityManager")
                .getMethod("getConfiguration").invoke(service);
        if (!(result instanceof Configuration)) {
            throw new IllegalStateException("CATALOG_CONFIGURATION_UNAVAILABLE");
        }
        return new Configuration((Configuration) result);
    }

    private static void applyConfiguration(Configuration configuration) throws Exception {
        // These are process-local resource/cache operations, not a change to
        // Android's global configuration. A missing platform method rejects the
        // query; there is no stale-label/icon fallback.
        Class<?> resources = Class.forName("android.app.ResourcesManager");
        Object manager = resources.getMethod("getInstance").invoke(null);
        Class<?> compatibility = Class.forName("android.content.res.CompatibilityInfo");
        Method apply = resources.getDeclaredMethod(
                "applyConfigurationToResources", Configuration.class, compatibility);
        apply.setAccessible(true);
        apply.invoke(manager, configuration, null);
        Method clear = Class.forName("android.app.ApplicationPackageManager")
                .getDeclaredMethod("configurationChanged");
        clear.setAccessible(true);
        clear.invoke(null);
    }

    private static String configurationKey(Configuration configuration) throws Exception {
        byte[] input = configuration.toString().getBytes(StandardCharsets.UTF_8);
        if (input.length > 16384) throw new IllegalStateException("CONFIGURATION_LIMIT");
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(input);
        char[] digits = "0123456789abcdef".toCharArray();
        char[] encoded = new char[digest.length * 2];
        for (int i = 0; i < digest.length; i++) {
            encoded[i * 2] = digits[(digest[i] >>> 4) & 15];
            encoded[i * 2 + 1] = digits[digest[i] & 15];
        }
        return new String(encoded);
    }
}
