package org.droidloom.frontend;

import android.os.ParcelFileDescriptor;

/**
 * Attached only to the selected Composer IComposer/default Binder.
 * Each silent unnamed proof socketpair is bound to the synchronous Binder caller
 * by kernel credentials, security context and a retained peer PIDFD.
 * Each descriptor carries the existing bounded, versioned seqpacket protocol.
 * No pathname, PID, credentials, executable, or protocol record is supplied here.
 */
@VintfStability
interface IFrontendChannels {
    /** The selected core input adapter receives routed input records. */
    ParcelFileDescriptor openInputChannel(in ParcelFileDescriptor caller);
    /** The selected core task helper receives one independent task channel. */
    ParcelFileDescriptor openTaskControlChannel(in ParcelFileDescriptor caller);
}
