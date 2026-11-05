/*
 * Copyright 2026 The Droidloom Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package com.android.calendar.event;

import java.net.URI;

/** Input-only Calendar URI contract. Provider write receipts remain stricter. */
public final class EventReference {
    public final long id,begin,end;
    public final boolean hasOccurrence;

    private EventReference(long id,long begin,long end,boolean hasOccurrence) {
        this.id=id; this.begin=begin; this.end=end; this.hasOccurrence=hasOccurrence;
    }
    private static long number(String value) {
        if(value==null || !value.matches("[0-9]+"))
            throw new IllegalArgumentException("The Calendar event reference is invalid.");
        return Long.parseLong(value);
    }
    public static EventReference parse(String input) {
        try {
            URI uri=new URI(input);
            if(!"content".equals(uri.getScheme()) ||
               !"com.android.calendar".equals(uri.getRawAuthority()) ||
               uri.getRawQuery()!=null || uri.getRawFragment()!=null ||
               uri.getRawPath()==null || !uri.getRawPath().equals(uri.getPath()))
                throw new IllegalArgumentException("This is not a Calendar event.");
            String[] parts=uri.getRawPath().split("/",-1);
            if((parts.length!=3 && parts.length!=6) || !parts[0].isEmpty() || !"events".equals(parts[1]))
                throw new IllegalArgumentException("This is not a Calendar event.");
            long id=number(parts[2]);
            if(parts.length==3) return new EventReference(id,-1,-1,false);
            if(!"EventTime".equals(parts[3]))
                throw new IllegalArgumentException("The Calendar event reference is invalid.");
            long begin=number(parts[4]),end=number(parts[5]);
            if(end<=begin) throw new IllegalArgumentException("The event occurrence has no valid duration.");
            return new EventReference(id,begin,end,true);
        } catch(java.net.URISyntaxException | NullPointerException failure) {
            throw new IllegalArgumentException("This is not a Calendar event.",failure);
        }
    }
}
