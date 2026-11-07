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
    /** Accept only this store's exact submitted LOCAL sync-adapter collection query.
     * The installed provider appends the new ID while retaining that query. */
    public static long calendarId(String value,String expectedInsertUri) {
        try {
            URI expected=new URI(expectedInsertUri);
            if(!"content".equals(expected.getScheme()) ||
               !"com.android.calendar".equals(expected.getRawAuthority()) ||
               !"/calendars".equals(expected.getRawPath()) ||
               expected.getRawFragment()!=null || expected.getRawQuery()==null)
                throw new IllegalArgumentException();
            String[] query=expected.getRawQuery().split("&",-1);
            if(query.length!=3 || !"caller_is_syncadapter=true".equals(query[0]) ||
               !query[1].startsWith("account_name=") || query[1].length()==13 ||
               !"account_type=LOCAL".equals(query[2])) throw new IllegalArgumentException();
            URI returned=new URI(value);
            if(returned.getRawFragment()!=null ||
               !expected.getRawQuery().equals(returned.getRawQuery()))
                throw new IllegalArgumentException();
            // Preserve the existing exact authority/path/numeric-ID checks. No
            // percent decoding or normalization can turn an invalid ID into a valid one.
            return id(value.substring(0,value.indexOf('?')),"calendars");
        } catch(Exception invalidReceipt) {
            throw new IllegalStateException(
                "The change may have completed, but the saved item could not be confirmed. Check Calendar before trying again.",
                invalidReceipt);
        }
    }
}
