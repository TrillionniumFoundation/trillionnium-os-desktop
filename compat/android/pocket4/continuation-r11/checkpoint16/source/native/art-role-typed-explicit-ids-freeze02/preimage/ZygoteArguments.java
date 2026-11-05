/*
 * Copyright (C) 2007 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package com.android.internal.os;

import android.net.Credentials;
import android.os.Process;

import java.io.EOFException;
import java.util.ArrayList;
import java.util.Arrays;

import android.ravenwood.annotation.RavenwoodKeep;
import android.ravenwood.annotation.RavenwoodKeepPartialClass;

import com.android.internal.annotations.VisibleForTesting;

/**
 * Handles argument parsing for args related to the zygote spawner.
 *
 * Current recognized args:
 * <ul>
 *   <li> --setuid=<i>uid of child process, defaults to 0</i>
 *   <li> --setgid=<i>gid of child process, defaults to 0</i>
 *   <li> --setgroups=<i>comma-separated list of supplementary gid's</i>
 *   <li> --capabilities=<i>a pair of comma-separated integer strings
 * indicating Linux capabilities(2) set for child. The first string
 * represents the <code>permitted</code> set, and the second the
 * <code>effective</code> set. Precede each with 0 or
 * 0x for octal or hexidecimal value. If unspecified, both default to 0.
 * This parameter is only applied if the uid of the new process will
 * be non-0. </i>
 *   <li> --rlimit=r,c,m<i>tuple of values for setrlimit() call.
 *    <code>r</code> is the resource, <code>c</code> and <code>m</code>
 *    are the settings for current and max value.</i>
 *   <li> --instruction-set=<i>instruction-set-string</i> which instruction set to use/emulate.
 *   <li> --nice-name=<i>nice name to appear in ps</i>
 *   <li> --package-name=<i>package name this process belongs to</i>
 *   <li> --runtime-args indicates that the remaining arg list should
 * be handed off to com.android.internal.os.RuntimeInit, rather than
 * processed directly.
 * Android runtime startup (eg, Binder initialization) is also eschewed.
 *   <li> [--] &lt;args for RuntimeInit &gt;
 * </ul>
 * @hide
 */
@RavenwoodKeepPartialClass
public class ZygoteArguments {

    /**
     * from --setuid
     */
    int mUid = 0;
    boolean mUidSpecified;

    /**
     * from --setgid
     */
    int mGid = 0;
    boolean mGidSpecified;

    /**
     * from --setgroups
     */
    int[] mGids;

    /**
     * From --runtime-flags.
     */
    int mRuntimeFlags;

    /**
     * From --mount-external
     */
    int mMountExternal = Zygote.MOUNT_EXTERNAL_NONE;

    /**
     * from --target-sdk-version.
     */
    private boolean mTargetSdkVersionSpecified;
    int mTargetSdkVersion;

    /**
     * from --nice-name
     */
    String mNiceName;

    /**
     * from --capabilities
     */
    private boolean mCapabilitiesSpecified;
    long mPermittedCapabilities;
    long mEffectiveCapabilities;

    /**
     * from --seinfo
     */
    private boolean mSeInfoSpecified;
    String mSeInfo;

    /**
     *
     */
    boolean mUsapPoolEnabled;
    boolean mUsapPoolStatusSpecified = false;

    /**
     * from all --rlimit=r,c,m
     */
    ArrayList<int[]> mRLimits;

    /**
     * from --invoke-with
     */
    String mInvokeWith;

    /** from --package-name */
    String mPackageName;

    /**
     * Any args after and including the first non-option arg (or after a '--')
     */
    String[] mRemainingArgs;

    /**
     * Whether the current arguments constitute an ABI list query.
     */
    boolean mAbiListQuery;

    /**
     * The instruction set to use, or null when not important.
     */
    String mInstructionSet;

    /**
     * The app data directory. May be null, e.g., for the system server. Note that this might not be
     * reliable in the case of process-sharing apps.
     */
    String mAppDataDir;

    /**
     * A Base64 string representing a serialize ApplicationInfo Parcel,
     when using --preload-app.
     */
    String mPreloadApp;

    /**
     * Whether this is a request to start preloading the default resources and classes. This
     * argument only makes sense when the zygote is in lazy preload mode (i.e, when it's started
     * with --enable-lazy-preload).
     */
    boolean mPreloadDefault;

    /**
     * Whether this is a request to start a zygote process as a child of this zygote. Set with
     * --start-child-zygote. The remaining arguments must include the CHILD_ZYGOTE_SOCKET_NAME_ARG
     * flag to indicate the abstract socket name that should be used for communication.
     */
    boolean mStartChildZygote;

    // An explicit request for a stronger private path, never an authorization
    // label. No existing AppZygote producer supplies this option. Without it,
    // the ordinary child-zygote parser and fork path remain unchanged.
    boolean mRequireDroidloomAppZygoteRoleV1;

    /**
     * Whether the current arguments constitute a request for the zygote's PID.
     */
    boolean mPidQuery;

    /**
     * Whether the current arguments constitute a notification that boot completed.
     */
    boolean mBootCompleted;

    /**
     * Exemptions from API deny-listing. These are sent to the pre-forked zygote at boot time, or
     * when they change, via --set-api-denylist-exemptions.
     */
    String[] mApiDenylistExemptions;

    /**
     * Sampling rate for logging hidden API accesses to the event log. This is sent to the
     * pre-forked zygote at boot time, or when it changes, via --hidden-api-log-sampling-rate.
     */
    int mHiddenApiAccessLogSampleRate = -1;

    /**
     * Sampling rate for logging hidden API accesses to statslog. This is sent to the
     * pre-forked zygote at boot time, or when it changes, via --hidden-api-statslog-sampling-rate.
     */
    int mHiddenApiAccessStatslogSampleRate = -1;

    /**
     * @see Zygote#START_AS_TOP_APP_ARG
     */
    boolean mIsTopApp;

    /**
     * A set of disabled app compatibility changes for the running app. From
     * --disabled-compat-changes.
     */
    long[] mDisabledCompatChanges = null;

    /**
     * A set of enabled app compatibility changes for the running app. From
     * --enabled-compat-changes.
     */
    long[] mEnabledCompatChanges = null;

    /**
     * A list that stores all related packages and its data info: volume uuid and inode.
     * Null if it does need to do app data isolation.
     */
    String[] mPkgDataInfoList;

    /**
     * A list that stores all allowlisted app data info: volume uuid and inode.
     * Null if it does need to do app data isolation.
     */
    String[] mAllowlistedDataInfoList;

    /**
     * @see Zygote#BIND_MOUNT_APP_STORAGE_DIRS
     */
    boolean mBindMountAppStorageDirs;

    /**
     * @see Zygote#BIND_MOUNT_APP_DATA_DIRS
     */
    boolean mBindMountAppDataDirs;

    /**
     * @see Zygote#BIND_MOUNT_SYSPROP_OVERRIDES
     */
    boolean mBindMountSyspropOverrides;

    /**
     * @see Zygote#APP_DATA_ISOLATION_ENABLED
     */
    boolean mAppDataIsolationEnabled;

    /**
     * from --preload-package
     */
    String mPreloadPackage;

    /**
     * Constructs instance and parses args
     *
     * @param args zygote command-line args as ZygoteCommandBuffer, positioned after argument count.
     */
    private ZygoteArguments(ZygoteCommandBuffer args, int argCount)
            throws IllegalArgumentException, EOFException {
        parseArgs(args, argCount);
    }

    /**
     * Return a new ZygoteArguments reflecting the contents of the given ZygoteCommandBuffer. Return
     * null if the ZygoteCommandBuffer was positioned at EOF. Assumes the buffer is initially
     * positioned at the beginning of the command.
     */
    public static ZygoteArguments getInstance(ZygoteCommandBuffer args)
            throws IllegalArgumentException, EOFException {
        int argCount = args.getCount();
        return argCount == 0 ? null : new ZygoteArguments(args, argCount);
    }

    /**
     * Parses the commandline arguments intended for the Zygote spawner (such as "--setuid=" and
     * "--setgid=") and creates an array containing the remaining args. Return false if we were
     * at EOF.
     *
     * Per security review bug #1112214, duplicate args are disallowed in critical cases to make
     * injection harder.
     */
    private void parseArgs(ZygoteCommandBuffer args, int argCount)
            throws IllegalArgumentException, EOFException {
        /*
         * See android.os.ZygoteProcess.zygoteSendArgsAndGetResult()
         * Presently the wire format to the zygote process is:
         * a) a count of arguments (argc, in essence)
         * b) a number of newline-separated argument strings equal to count
         *
         * After the zygote process reads these it will write the pid of
         * the child or -1 on failure.
         */

        String unprocessedArg = null;
        int curArg = 0;  // Index of arg
        boolean seenRuntimeArgs = false;
        boolean expectRuntimeArgs = true;

        for ( /* curArg */ ; curArg < argCount; ++curArg) {
            String arg = args.nextArg();

            if (arg.equals("--")) {
                curArg++;
                break;
            } else if (arg.startsWith("--setuid=")) {
                if (mUidSpecified) {
                    throw new IllegalArgumentException(
                        "Duplicate arg specified");
                }
                mUidSpecified = true;
                mUid = Integer.parseInt(getAssignmentValue(arg));
            } else if (arg.startsWith("--setgid=")) {
                if (mGidSpecified) {
                    throw new IllegalArgumentException(
                        "Duplicate arg specified");
                }
                mGidSpecified = true;
                mGid = Integer.parseInt(getAssignmentValue(arg));
            } else if (arg.startsWith("--target-sdk-version=")) {
                if (mTargetSdkVersionSpecified) {
                    throw new IllegalArgumentException(
                        "Duplicate target-sdk-version specified");
                }
                mTargetSdkVersionSpecified = true;
                mTargetSdkVersion = Integer.parseInt(getAssignmentValue(arg));
            } else if (arg.equals("--runtime-args")) {
                seenRuntimeArgs = true;
            } else if (arg.startsWith("--runtime-flags=")) {
                mRuntimeFlags = Integer.parseInt(getAssignmentValue(arg));
            } else if (arg.startsWith("--seinfo=")) {
                if (mSeInfoSpecified) {
                    throw new IllegalArgumentException(
                        "Duplicate arg specified");
                }
                mSeInfoSpecified = true;
                mSeInfo = getAssignmentValue(arg);
            } else if (arg.startsWith("--capabilities=")) {
                if (mCapabilitiesSpecified) {
                    throw new IllegalArgumentException(
                        "Duplicate arg specified");
                }
                mCapabilitiesSpecified = true;
                String capString = getAssignmentValue(arg);

                String[] capStrings = capString.split(",", 2);

                if (capStrings.length == 1) {
                    mEffectiveCapabilities = Long.decode(capStrings[0]);
                    mPermittedCapabilities = mEffectiveCapabilities;
                } else {
                    mPermittedCapabilities = Long.decode(capStrings[0]);
                    mEffectiveCapabilities = Long.decode(capStrings[1]);
                }
            } else if (arg.startsWith("--rlimit=")) {
                // Duplicate --rlimit arguments are specifically allowed.
                String[] limitStrings = getAssignmentList(arg);

                if (limitStrings.length != 3) {
                    throw new IllegalArgumentException(
                        "--rlimit= should have 3 comma-delimited ints");
                }
                int[] rlimitTuple = new int[limitStrings.length];

                for (int i = 0; i < limitStrings.length; i++) {
                    rlimitTuple[i] = Integer.parseInt(limitStrings[i]);
                }

                if (mRLimits == null) {
                    mRLimits = new ArrayList<>();
                }

                mRLimits.add(rlimitTuple);
            } else if (arg.startsWith("--setgroups=")) {
                if (mGids != null) {
                    throw new IllegalArgumentException(
                        "Duplicate arg specified");
                }

                String[] params = getAssignmentList(arg);

                mGids = new int[params.length];

                for (int i = params.length - 1; i >= 0; i--) {
                    mGids[i] = Integer.parseInt(params[i]);
                }
            } else if (arg.equals("--invoke-with")) {
                if (mInvokeWith != null) {
                    throw new IllegalArgumentException(
                        "Duplicate arg specified");
                }
                try {
                    ++curArg;
                    mInvokeWith = args.nextArg();
                } catch (IndexOutOfBoundsException ex) {
                    throw new IllegalArgumentException(
                        "--invoke-with requires argument");
                }
            } else if (arg.startsWith("--nice-name=")) {
                if (mNiceName != null) {
                    throw new IllegalArgumentException(
                        "Duplicate arg specified");
                }
                mNiceName = getAssignmentValue(arg);
            } else if (arg.equals("--mount-external-default")) {
                mMountExternal = Zygote.MOUNT_EXTERNAL_DEFAULT;
            } else if (arg.equals("--mount-external-installer")) {
                mMountExternal = Zygote.MOUNT_EXTERNAL_INSTALLER;
            } else if (arg.equals("--mount-external-pass-through")) {
                mMountExternal = Zygote.MOUNT_EXTERNAL_PASS_THROUGH;
            } else if (arg.equals("--mount-external-android-writable")) {
                mMountExternal = Zygote.MOUNT_EXTERNAL_ANDROID_WRITABLE;
            } else if (arg.equals("--query-abi-list")) {
                mAbiListQuery = true;
            } else if (arg.equals("--get-pid")) {
                mPidQuery = true;
            } else if (arg.equals("--boot-completed")) {
                mBootCompleted = true;
            } else if (arg.startsWith("--instruction-set=")) {
                mInstructionSet = getAssignmentValue(arg);
            } else if (arg.startsWith("--app-data-dir=")) {
                mAppDataDir = getAssignmentValue(arg);
            } else if (arg.equals("--preload-app")) {
                ++curArg;
                mPreloadApp = args.nextArg();
            } else if (arg.equals("--preload-default")) {
                mPreloadDefault = true;
                expectRuntimeArgs = false;
            } else if (arg.equals("--start-child-zygote")) {
                mStartChildZygote = true;
            } else if (arg.equals("--require-droidloom-app-zygote-role-v1")) {
                if (mRequireDroidloomAppZygoteRoleV1) {
                    throw new IllegalArgumentException("Duplicate private AppZygote request");
                }
                mRequireDroidloomAppZygoteRoleV1 = true;
            } else if (arg.equals("--set-api-denylist-exemptions")) {
                // consume all remaining args; this is a stand-alone command, never included
                // with the regular fork command.
                mApiDenylistExemptions = new String[argCount - curArg - 1];
                ++curArg;
                for (int i = 0; curArg < argCount; ++curArg, ++i) {
                    mApiDenylistExemptions[i] = args.nextArg();
                }
                expectRuntimeArgs = false;
            } else if (arg.startsWith("--hidden-api-log-sampling-rate=")) {
                String rateStr = getAssignmentValue(arg);
                try {
                    mHiddenApiAccessLogSampleRate = Integer.parseInt(rateStr);
                } catch (NumberFormatException nfe) {
                    throw new IllegalArgumentException(
                        "Invalid log sampling rate: " + rateStr, nfe);
                }
                expectRuntimeArgs = false;
            } else if (arg.startsWith("--hidden-api-statslog-sampling-rate=")) {
                String rateStr = getAssignmentValue(arg);
                try {
                    mHiddenApiAccessStatslogSampleRate = Integer.parseInt(rateStr);
                } catch (NumberFormatException nfe) {
                    throw new IllegalArgumentException(
                        "Invalid statslog sampling rate: " + rateStr, nfe);
                }
                expectRuntimeArgs = false;
            } else if (arg.startsWith("--package-name=")) {
                if (mPackageName != null) {
                    throw new IllegalArgumentException("Duplicate arg specified");
                }
                mPackageName = getAssignmentValue(arg);
            } else if (arg.startsWith("--usap-pool-enabled=")) {
                mUsapPoolStatusSpecified = true;
                mUsapPoolEnabled = Boolean.parseBoolean(getAssignmentValue(arg));
                expectRuntimeArgs = false;
            } else if (arg.startsWith(Zygote.START_AS_TOP_APP_ARG)) {
                mIsTopApp = true;
            } else if (arg.startsWith("--disabled-compat-changes=")) {
                mDisabledCompatChanges = parseAndMergeCompatChanges(arg, mDisabledCompatChanges);
            } else if (arg.startsWith("--enabled-compat-changes=")) {
                mEnabledCompatChanges = parseAndMergeCompatChanges(arg, mEnabledCompatChanges);
            } else if (arg.startsWith(Zygote.PKG_DATA_INFO_MAP)) {
                mPkgDataInfoList = getAssignmentList(arg);
            } else if (arg.startsWith(Zygote.ALLOWLISTED_DATA_INFO_MAP)) {
                mAllowlistedDataInfoList = getAssignmentList(arg);
            } else if (arg.equals(Zygote.BIND_MOUNT_APP_STORAGE_DIRS)) {
                mBindMountAppStorageDirs = true;
            } else if (arg.equals(Zygote.BIND_MOUNT_APP_DATA_DIRS)) {
                mBindMountAppDataDirs = true;
            } else if (arg.equals(Zygote.BIND_MOUNT_SYSPROP_OVERRIDES)) {
                mBindMountSyspropOverrides = true;
            } else {
                unprocessedArg = arg;
                break;
            }
        }
        // curArg is the index of the first unprocessed argument. That argument is either referenced
        // by unprocessedArg or not read yet.

        if (mBootCompleted) {
            if (argCount > curArg) {
                throw new IllegalArgumentException("Unexpected arguments after --boot-completed");
            }
        } else if (mAbiListQuery || mPidQuery) {
            if (argCount > curArg) {
                throw new IllegalArgumentException("Unexpected arguments after --query-abi-list.");
            }
        } else if (mPreloadApp != null) {
            if (argCount > curArg) {
                throw new IllegalArgumentException(
                    "Unexpected arguments after --preload-app.");
            }
        } else if (expectRuntimeArgs) {
            if (!seenRuntimeArgs) {
                throw new IllegalArgumentException("Unexpected argument : "
                    + (unprocessedArg == null ? args.nextArg() : unprocessedArg));
            }

            mRemainingArgs = new String[argCount - curArg];
            int i = 0;
            if (unprocessedArg != null) {
                mRemainingArgs[0] = unprocessedArg;
                ++i;
            }
            for (; i < argCount - curArg; ++i) {
                mRemainingArgs[i] = args.nextArg();
            }
        }

        if (mRequireDroidloomAppZygoteRoleV1
                && (!mStartChildZygote || mRemainingArgs == null || mRemainingArgs.length == 0
                    || !AppZygoteForkSpec.ENTRY_CLASS.equals(mRemainingArgs[0]))) {
            throw new IllegalArgumentException("Private role request requires AppZygoteInit");
        }

        if (mStartChildZygote) {
            boolean seenChildSocketArg = false;
            for (String arg : mRemainingArgs) {
                if (arg.startsWith(Zygote.CHILD_ZYGOTE_SOCKET_NAME_ARG)) {
                    seenChildSocketArg = true;
                    break;
                }
            }
            if (!seenChildSocketArg) {
                throw new IllegalArgumentException("--start-child-zygote specified "
                        + "without " + Zygote.CHILD_ZYGOTE_SOCKET_NAME_ARG);
            }
        }
    }

    /**
     * Immutable launch data for the private AppZygote JNI entry. This is not a
     * factory grant or proof that an early policy has been installed.
     */
    static final class AppZygoteForkSpec {
        static final int VERSION = 1;
        static final int KIND_APP_ZYGOTE = 1;
        static final String ENTRY_CLASS = "com.android.internal.os.AppZygoteInit";

        final int version = VERSION;
        final int kind = KIND_APP_ZYGOTE;
        final int initialUid;
        final int initialGid;
        final int uidMin;
        final int uidMax;
        final int gidMin;
        final int gidMax;
        private final String socketName;
        private final String abiList;

        private AppZygoteForkSpec(int uid, int gid, int minimum, int maximum,
                String socket, String abis) {
            initialUid = uid;
            initialGid = gid;
            uidMin = gidMin = minimum;
            uidMax = gidMax = maximum;
            socketName = socket;
            abiList = abis;
        }

        void requireMatches(int uid, int gid, boolean childZygote) {
            if (!childZygote || uid <= 0 || gid <= 0
                    || uid != initialUid || gid != initialGid
                    || uidMin < Process.FIRST_APP_ZYGOTE_ISOLATED_UID
                    || uidMin > uidMax || gidMin != uidMin || gidMax != uidMax) {
                throw new IllegalArgumentException("AppZygote fork specification changed");
            }
        }

        String[] copyRuntimeArguments() {
            // Do not retain or return the mutable command argument array. The
            // child receives exactly the range which was validated pre-fork.
            return new String[] {ENTRY_CLASS,
                    Zygote.CHILD_ZYGOTE_SOCKET_NAME_ARG + socketName,
                    Zygote.CHILD_ZYGOTE_ABI_LIST_ARG + abiList,
                    Zygote.CHILD_ZYGOTE_UID_RANGE_START + uidMin,
                    Zygote.CHILD_ZYGOTE_UID_RANGE_END + uidMax};
        }
    }

    /**
     * Called by ZygoteConnection after its kernel peer authentication and the
     * existing UID/invoke-with policies. An absent explicit requirement keeps
     * the old AppZygote path. A present but invalid request never falls back.
     */
    AppZygoteForkSpec appZygoteForkSpec(Credentials peer) {
        if (!mRequireDroidloomAppZygoteRoleV1) {
            return null;
        }
        if (!mStartChildZygote) {
            throw new IllegalArgumentException("Private role request is not AppZygoteInit");
        }
        if (peer == null || peer.getUid() != Process.SYSTEM_UID) {
            throw new ZygoteSecurityException("AppZygote specification requires the system peer");
        }
        if (!mUidSpecified || !mGidSpecified || mUid <= 0 || mGid <= 0 || mInvokeWith != null
                || mPermittedCapabilities != 0 || mEffectiveCapabilities != 0) {
            throw new ZygoteSecurityException("Unsupported AppZygote launch authority");
        }
        // startChildZygote supplies precisely these four extra arguments.
        // Reject duplicate, missing and unknown fields before any fork.
        final String[] requested = mRemainingArgs;
        if (requested == null || requested.length != 5) {
            throw new IllegalArgumentException("AppZygote requires four unique launch arguments");
        }
        final String[] arguments = requested.clone();
        if (!AppZygoteForkSpec.ENTRY_CLASS.equals(arguments[0])) {
            throw new IllegalArgumentException("Private role request is not AppZygoteInit");
        }
        String socket = null;
        String abis = null;
        Integer minimum = null;
        Integer maximum = null;
        for (int i = 1; i < arguments.length; ++i) {
            final String arg = arguments[i];
            if (arg == null) {
                throw new IllegalArgumentException("Null AppZygote launch argument");
            }
            if (arg.startsWith(Zygote.CHILD_ZYGOTE_SOCKET_NAME_ARG)) {
                if (socket != null) throw new IllegalArgumentException("Duplicate AppZygote socket");
                socket = nonemptyAppZygoteValue(arg, Zygote.CHILD_ZYGOTE_SOCKET_NAME_ARG);
            } else if (arg.startsWith(Zygote.CHILD_ZYGOTE_ABI_LIST_ARG)) {
                if (abis != null) throw new IllegalArgumentException("Duplicate AppZygote ABI list");
                abis = nonemptyAppZygoteValue(arg, Zygote.CHILD_ZYGOTE_ABI_LIST_ARG);
            } else if (arg.startsWith(Zygote.CHILD_ZYGOTE_UID_RANGE_START)) {
                if (minimum != null) throw new IllegalArgumentException("Duplicate AppZygote minimum");
                minimum = canonicalAppZygoteId(arg, Zygote.CHILD_ZYGOTE_UID_RANGE_START);
            } else if (arg.startsWith(Zygote.CHILD_ZYGOTE_UID_RANGE_END)) {
                if (maximum != null) throw new IllegalArgumentException("Duplicate AppZygote maximum");
                maximum = canonicalAppZygoteId(arg, Zygote.CHILD_ZYGOTE_UID_RANGE_END);
            } else {
                throw new IllegalArgumentException("Unknown AppZygote launch argument");
            }
        }
        if (socket == null || abis == null || minimum == null || maximum == null
                || minimum < Process.FIRST_APP_ZYGOTE_ISOLATED_UID || minimum > maximum) {
            throw new IllegalArgumentException("Incomplete or invalid AppZygote range");
        }
        final AppZygoteForkSpec result =
                new AppZygoteForkSpec(mUid, mGid, minimum, maximum, socket, abis);
        result.requireMatches(mUid, mGid, mStartChildZygote);
        return result;
    }

    private static String nonemptyAppZygoteValue(String arg, String prefix) {
        final String value = arg.substring(prefix.length());
        if (value.isEmpty() || value.indexOf('\0') >= 0) {
            throw new IllegalArgumentException("Empty or invalid AppZygote argument");
        }
        return value;
    }

    private static int canonicalAppZygoteId(String arg, String prefix) {
        final String value = nonemptyAppZygoteValue(arg, prefix);
        final int id;
        try {
            id = Integer.parseInt(value);
        } catch (NumberFormatException error) {
            throw new IllegalArgumentException("AppZygote ID is not an int32 value", error);
        }
        if (id <= 0 || !Integer.toString(id).equals(value)) {
            throw new IllegalArgumentException("AppZygote ID is not canonical positive decimal");
        }
        return id;
    }

    @RavenwoodKeep
    private static String getAssignmentValue(String arg) {
        return arg.substring(arg.indexOf('=') + 1);
    }

    private static String[] getAssignmentList(String arg) {
        return getAssignmentValue(arg).split(",");
    }

    /**
     * Parse and merge compatibility changes from a zygote argument.
     * The resulting array is sorted to allow O(log n) lookup via Arrays.binarySearch.
     *
     * @hide
     */
    @VisibleForTesting
    @RavenwoodKeep
    static long[] parseAndMergeCompatChanges(String arg, long[] existingChanges) {
        final String value = getAssignmentValue(arg);
        final int oldLen = (existingChanges == null) ? 0 : existingChanges.length;

        if (value.isEmpty()) {
            return existingChanges == null ? new long[0] : existingChanges;
        }

        // Count commas to determine the maximum possible number of new changes.
        int commaCount = 0;
        for (int i = 0; i < value.length(); i++) {
            if (value.charAt(i) == ',') {
                commaCount++;
            }
        }
        final int maxNewChanges = commaCount + 1;

        // Pre-allocate the merged array to avoid multiple intermediate allocations.
        long[] merged = new long[oldLen + maxNewChanges];
        if (oldLen > 0) {
            System.arraycopy(existingChanges, 0, merged, 0, oldLen);
        }

        int actualCount = oldLen;
        int start = 0;
        final int length = value.length();
        while (start < length) {
            int end = value.indexOf(',', start);
            if (end == -1) {
                end = length;
            }
            if (start < end) {
                merged[actualCount++] = Long.parseLong(value.substring(start, end));
            }
            start = end + 1;
        }

        // Shrink if there were empty parameters (e.g. "1,,2")
        if (actualCount < merged.length) {
            merged = Arrays.copyOf(merged, actualCount);
        }

        Arrays.sort(merged);

        // In-place deduplication to avoid Set allocations on the critical path
        if (merged.length > 1) {
            int uniqueIndex = 0;
            for (int i = 1; i < merged.length; i++) {
                if (merged[uniqueIndex] != merged[i]) {
                    uniqueIndex++;
                    merged[uniqueIndex] = merged[i];
                }
            }
            int uniqueCount = uniqueIndex + 1;
            if (uniqueCount < merged.length) {
                merged = Arrays.copyOf(merged, uniqueCount);
            }
        }
        return merged;
    }
}
