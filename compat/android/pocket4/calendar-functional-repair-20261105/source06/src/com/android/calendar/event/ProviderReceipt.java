/* Copyright 2026 The Droidloom Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package com.android.calendar.event;

import java.net.URI;

/** A malformed response after a write is an unknown outcome, never a retryable input error. */
public final class ProviderReceipt {
    private ProviderReceipt() {}
    public static long id(String value,String collection) {
        try {
            URI uri=new URI(value);
            String prefix="/"+collection+"/";
            String path=uri.getRawPath();
            if(!"content".equals(uri.getScheme()) ||
               !"com.android.calendar".equals(uri.getRawAuthority()) ||
               uri.getRawQuery()!=null || uri.getRawFragment()!=null ||
               path==null || !path.startsWith(prefix)) throw new IllegalArgumentException();
            String suffix=path.substring(prefix.length());
            if(!suffix.matches("[0-9]+")) throw new IllegalArgumentException();
            long id=Long.parseLong(suffix);
            if(id<0) throw new IllegalArgumentException();
            return id;
        } catch(Exception invalidReceipt) {
            throw new IllegalStateException(
                "The change may have completed, but the saved item could not be confirmed. Check Calendar before trying again.",
                invalidReceipt);
        }
    }
}
