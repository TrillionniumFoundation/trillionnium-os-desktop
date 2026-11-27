/*
 * Copyright 2026 Droidloom
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
package com.android.droidloom.catalog;

import android.accounts.Account;
import android.accounts.AuthenticatorDescription;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.os.IBinder;
import android.os.Process;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.FileDescriptor;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.lang.reflect.Method;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/**
 * Registered user-zero account identities and target visibility only.
 * The fixed AccountRead role is independently admitted as uid 1000; no denied
 * shell operation is retried here. The actual selected AccountManager method
 * includes every account belonging to its complete registered authenticator
 * roster. This is not an orphan-database, credential or login-state inventory.
 *
 * Names and types never cross this process boundary. A fresh creator-origin
 * stdin supplies the live original host owner's private key, never argv,
 * environment, a path, an APK input or a caller-provided descriptor.
 */
public final class AccountState {
    private static final int OUTPUT_BYTES = 131072;
    private static final int MAX_TYPES = 128;
    private static final int MAX_ACCOUNTS = 512;
    private static final String SCHEMA = "droidloom.application-account-android.v1";
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
    private AccountState() {}

    public static void main(String[] arguments) {
        byte[] key = new byte[32];
        int status = 1;
        // Do not print Throwable, its message, cause, account or authenticator
        // objects. Reflection/Binder errors may contain private strings.
        Thread.setDefaultUncaughtExceptionHandler((thread, failure) -> {
            emitFailure();
            Runtime.getRuntime().halt(1);
        });
        try {
            require(arguments.length == 1 && PACKAGES.contains(arguments[0]));
            require(Process.myUid() == 1000);
            try (FileInputStream input = new FileInputStream(FileDescriptor.in)) {
                int at = 0;
                while (at < key.length) {
                    int count = input.read(key, at, key.length - at);
                    require(count > 0);
                    at += count;
                }
                require(input.read() == -1);
            }
            String result = observe(arguments[0], key).toString();
            byte[] output = (result + "\n").getBytes(StandardCharsets.UTF_8);
            require(output.length <= OUTPUT_BYTES);
            try (FileOutputStream stream = new FileOutputStream(FileDescriptor.out)) {
                stream.write(output);
                stream.flush();
            }
            status = 0;
        } catch (Throwable failure) {
            emitFailure();
        } finally {
            Arrays.fill(key, (byte) 0);
        }
        System.exit(status);
    }

    private static void emitFailure() {
        try {
            FileOutputStream errors = new FileOutputStream(FileDescriptor.err);
            errors.write("account observation unavailable\n".getBytes(StandardCharsets.US_ASCII));
            errors.flush();
        } catch (Throwable ignored) {
            // No secondary diagnostic is allowed to expose a private cause.
        }
    }
    private static void require(boolean value) {
        if (!value) throw new IllegalStateException("account observation unavailable");
    }
    private static void privateText(String value, int maximumBytes) {
        require(value != null && !value.isEmpty()
                && value.getBytes(StandardCharsets.UTF_8).length <= maximumBytes);
    }
    private static String token(byte[] key, String packageName, String kind, String... values)
            throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        for (String value : concat(packageName, kind, values)) {
            byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
            mac.update(ByteBuffer.allocate(4).putInt(bytes.length).array());
            mac.update(bytes);
        }
        byte[] bytes = mac.doFinal();
        StringBuilder result = new StringBuilder(64);
        for (byte value : bytes) result.append("0123456789abcdef".charAt((value >>> 4) & 15))
                .append("0123456789abcdef".charAt(value & 15));
        Arrays.fill(bytes, (byte) 0);
        return result.toString();
    }
    private static String[] concat(String packageName, String kind, String[] values) {
        String[] all = new String[values.length + 3];
        all[0] = "droidloom.account-comparison.v1";
        all[1] = packageName;
        all[2] = kind;
        System.arraycopy(values, 0, all, 3, values.length);
        return all;
    }

    private static final class Identity {
        final String packageName;
        final int uid;
        final long version;
        final TreeSet<String> paths = new TreeSet<>();
        Identity(String packageName, PackageManager manager) throws Exception {
            require(packageName != null && packageName.length() <= 255
                    && packageName.matches("[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z0-9_]+)*"));
            PackageInfo info = manager.getPackageInfo(packageName, 0);
            ApplicationInfo app = info.applicationInfo;
            require(info.packageName.equals(packageName) && app != null
                    && app.packageName.equals(packageName) && app.uid > 0 && app.uid < 100000);
            this.packageName = packageName;
            uid = app.uid;
            version = info.getLongVersionCode();
            require(version >= 0);
            path(app.sourceDir);
            if (app.splitSourceDirs != null) {
                require(app.splitSourceDirs.length < 128);
                for (String value : app.splitSourceDirs) path(value);
            }
        }
        private void path(String path) {
            require(path != null && path.startsWith("/") && !path.endsWith("/")
                    && path.length() <= 4096 && !path.contains("//")
                    && !path.contains("/../") && !path.contains("/./")
                    && path.chars().noneMatch(c -> c < 32 || c == 127) && paths.add(path));
        }
        boolean same(Identity other) {
            return packageName.equals(other.packageName) && uid == other.uid
                    && version == other.version && paths.equals(other.paths);
        }
        JSONObject json() throws Exception {
            JSONObject result = new JSONObject();
            result.put("package", packageName);
            result.put("uid", uid);
            result.put("version_code", version);
            result.put("source_paths", new JSONArray(paths));
            return result;
        }
    }

    private static final class Authenticator {
        final String token;
        final Identity identity;
        final int label;
        final int icon;
        final int smallIcon;
        final int preferences;
        final boolean customTokens;
        Authenticator(AuthenticatorDescription value, String target, byte[] key,
                PackageManager packages) throws Exception {
            privateText(value.type, 1024);
            token = token(key, target, "type", value.type);
            identity = new Identity(value.packageName, packages);
            label = value.labelId;
            icon = value.iconId;
            smallIcon = value.smallIconId;
            preferences = value.accountPreferencesId;
            customTokens = value.customTokens;
            require(label >= 0 && icon >= 0 && smallIcon >= 0 && preferences >= 0);
        }
        boolean same(Authenticator other) {
            return token.equals(other.token) && identity.same(other.identity)
                    && label == other.label && icon == other.icon && smallIcon == other.smallIcon
                    && preferences == other.preferences && customTokens == other.customTokens;
        }
        JSONObject json() throws Exception {
            JSONObject result = new JSONObject();
            result.put("type_token", token);
            result.put("provider", identity.json());
            result.put("label_id", label);
            result.put("icon_id", icon);
            result.put("small_icon_id", smallIcon);
            result.put("preferences_id", preferences);
            result.put("custom_tokens", customTokens);
            return result;
        }
    }

    private static TreeMap<String, Authenticator> authenticators(String target, byte[] key,
            PackageManager packages, Object service, Method types) throws Exception {
        Object raw = types.invoke(service, 0);
        require(raw instanceof AuthenticatorDescription[]);
        AuthenticatorDescription[] values = (AuthenticatorDescription[]) raw;
        // An uninitialized/unknown empty registry is not evidence of no accounts.
        require(values.length > 0 && values.length <= MAX_TYPES);
        TreeMap<String, Authenticator> result = new TreeMap<>();
        for (AuthenticatorDescription value : values) {
            require(value != null);
            Authenticator item = new Authenticator(value, target, key, packages);
            require(result.put(item.token, item) == null);
        }
        return result;
    }
    private static boolean sameAuthenticators(TreeMap<String, Authenticator> a,
            TreeMap<String, Authenticator> b) {
        if (!a.keySet().equals(b.keySet())) return false;
        for (String type : a.keySet()) if (!a.get(type).same(b.get(type))) return false;
        return true;
    }

    private static final class AccountRow {
        final String id;
        final String type;
        final int visibility;
        AccountRow(Account account, Integer visibility, String target, byte[] key)
                throws Exception {
            privateText(account.name, 4096);
            privateText(account.type, 1024);
            require(visibility != null && visibility >= 1 && visibility <= 4);
            id = token(key, target, "account", account.type, account.name);
            type = token(key, target, "type", account.type);
            this.visibility = visibility;
        }
        boolean same(AccountRow other) {
            return id.equals(other.id) && type.equals(other.type) && visibility == other.visibility;
        }
        JSONObject json() throws Exception {
            JSONObject result = new JSONObject();
            result.put("account_token", id);
            result.put("type_token", type);
            result.put("visibility", visibility);
            return result;
        }
    }

    private static final class Snapshot {
        final Identity target;
        final TreeMap<String, Authenticator> types;
        final TreeMap<String, AccountRow> accounts = new TreeMap<>();
        Snapshot(String packageName, byte[] key, PackageManager packages, Object service,
                Method typeQuery, Method accountQuery) throws Exception {
            target = new Identity(packageName, packages);
            types = authenticators(packageName, key, packages, service, typeQuery);
            // Selected CP3A getAccountsAndVisibilityForPackage(type=null) uses
            // all registered types only for actual uid 1000. Its null rejection
            // and exceptions are not converted into an empty successful map.
            Object raw = accountQuery.invoke(service, packageName, null);
            require(raw instanceof Map<?, ?>);
            Map<?, ?> values = (Map<?, ?>) raw;
            require(values.size() <= MAX_ACCOUNTS);
            for (Map.Entry<?, ?> value : values.entrySet()) {
                require(value.getKey() instanceof Account && value.getValue() instanceof Integer);
                AccountRow row = new AccountRow((Account) value.getKey(),
                        (Integer) value.getValue(), packageName, key);
                require(types.containsKey(row.type) && accounts.put(row.id, row) == null);
            }
            require(target.same(new Identity(packageName, packages)));
            require(sameAuthenticators(types,
                    authenticators(packageName, key, packages, service, typeQuery)));
        }
        boolean same(Snapshot other) {
            if (!target.same(other.target) || !sameAuthenticators(types, other.types)
                    || !accounts.keySet().equals(other.accounts.keySet())) return false;
            for (String id : accounts.keySet()) if (!accounts.get(id).same(other.accounts.get(id)))
                return false;
            return true;
        }
        JSONObject json() throws Exception {
            JSONObject result = new JSONObject();
            result.put("schema", SCHEMA);
            result.put("observer_uid", Process.myUid());
            result.put("user", 0);
            result.put("target", target.json());
            JSONArray auth = new JSONArray();
            for (Authenticator value : types.values()) auth.put(value.json());
            result.put("authenticators", auth);
            JSONArray rows = new JSONArray();
            for (AccountRow value : accounts.values()) rows.put(value.json());
            result.put("accounts", rows);
            result.put("samples", 2);
            result.put("scope", "all_registered_authenticator_accounts_and_target_visibility");
            return result;
        }
    }

    private static JSONObject observe(String packageName, byte[] key) throws Exception {
        PackageManager packages = ApplicationCatalog.systemContext().getPackageManager();
        Class<?> services = Class.forName("android.os.ServiceManager");
        IBinder binder = (IBinder) services.getDeclaredMethod("getService", String.class)
                .invoke(null, "account");
        require(binder != null && binder.isBinderAlive() && binder.pingBinder());
        Class<?> stub = Class.forName("android.accounts.IAccountManager$Stub");
        Object service = stub.getMethod("asInterface", IBinder.class).invoke(null, binder);
        Class<?> api = Class.forName("android.accounts.IAccountManager");
        require(service != null && api.isInstance(service));
        Method types = api.getMethod("getAuthenticatorTypes", int.class);
        Method accounts = api.getMethod("getAccountsAndVisibilityForPackage",
                String.class, String.class);
        Snapshot before = new Snapshot(packageName, key, packages, service, types, accounts);
        Snapshot after = new Snapshot(packageName, key, packages, service, types, accounts);
        require(before.same(after) && binder.isBinderAlive() && binder.pingBinder()
                && Process.myUid() == 1000);
        return after.json();
    }
}
