/*
 * Copyright 2026 The Droidloom Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package com.android.calendar.alerts;

/** Small recovery policy; Android provider reads supply the observed states. */
public final class SnoozeState {
    public static final int REQUESTED=0, CONFIRMED=1, CANCELLED=2;
    public static final int ABSENT=-1, SCHEDULED=0, FIRED=1, DISMISSED=2;
    public enum Decision { INITIAL_WRITE, RESTORE, ADOPT, PUBLISH, CANCEL_TARGET, FORGET, NO_EFFECT, UNKNOWN }
    private SnoozeState() {}

    /**
     * A fresh user action alone may start the initial write. After interruption,
     * REQUESTED never invents confirmation from an absent target. A confirmed
     * request may rebuild its missing target, guarded by the original dismissed
     * alert and unchanged event/occurrence. Existing target rows are adopted,
     * never duplicated.
     */
    public static Decision decide(int phase,boolean eventMatches,boolean sourceMatches,
                                  int sourceState,int targetCount,int targetState,boolean freshUserAction) {
        if(phase<REQUESTED || phase>CANCELLED || targetCount<0 || targetState<ABSENT || targetState>DISMISSED)
            throw new IllegalArgumentException("Invalid snooze recovery state.");
        if(!sourceMatches) return Decision.FORGET;
        if(sourceState!=FIRED && sourceState!=DISMISSED) return Decision.UNKNOWN;
        if(targetCount>1) return Decision.UNKNOWN;
        if((targetCount==0)!=(targetState==ABSENT))
            throw new IllegalArgumentException("Snooze target count disagrees with state.");
        if(!eventMatches || phase==CANCELLED) return Decision.CANCEL_TARGET;
        if(targetState==DISMISSED) return Decision.FORGET;
        if(sourceState==FIRED) {
            if(phase==REQUESTED && targetCount==0)
                return freshUserAction?Decision.INITIAL_WRITE:Decision.NO_EFFECT;
            return Decision.UNKNOWN;
        }
        if(targetCount==0)
            return phase==CONFIRMED?Decision.RESTORE:Decision.UNKNOWN;
        if(targetState==FIRED) return Decision.PUBLISH;
        return Decision.ADOPT;
    }

    /** FIRED alone cannot retire the retry capability; NMS must contain this notification. */
    public static boolean canForgetPublished(int phase,boolean sourceMatches,int sourceState,
            boolean eventMatches,int targetState,boolean targetIdMatches,boolean activeNotification) {
        return phase==CONFIRMED && sourceMatches && sourceState==DISMISSED && eventMatches &&
            targetState==FIRED && targetIdMatches && activeNotification;
    }
}
