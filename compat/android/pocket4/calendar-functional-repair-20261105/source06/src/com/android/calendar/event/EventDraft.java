/*
 * Copyright 2026 The Droidloom Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package com.android.calendar.event;

import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Objects;

/** Form state with explicit UTC all-day and local wall-clock semantics. */
public final class EventDraft {
    public long id = -1;
    public long calendarId = -1;
    public String title = "";
    public String location = "";
    public String description = "";
    public LocalDate startDate;
    public LocalDate endDate;
    public LocalTime startTime;
    public LocalTime endTime;
    public String timezone;
    public ZoneOffset preferredStartOffset;
    public ZoneOffset preferredEndOffset;
    public boolean allDay;
    public String recurrence;
    public boolean recurrenceChanged;
    public boolean timingChanged;
    public boolean remindersChanged;
    public int reminderMinutes = -1;

    public EventDraft copy() {
        EventDraft d = new EventDraft();
        d.id=id; d.calendarId=calendarId; d.title=title; d.location=location;
        d.description=description; d.startDate=startDate; d.endDate=endDate;
        d.startTime=startTime; d.endTime=endTime; d.timezone=timezone;
        d.preferredStartOffset=preferredStartOffset; d.preferredEndOffset=preferredEndOffset;
        d.allDay=allDay; d.recurrence=recurrence; d.recurrenceChanged=recurrenceChanged;
        d.timingChanged=timingChanged; d.remindersChanged=remindersChanged;
        d.reminderMinutes=reminderMinutes;
        return d;
    }

    /** Read-only occurrence presentation; the series form remains the save target. */
    public EventDraft displayOccurrence(long begin,long end) {
        EventDraft display=copy();
        display.setTimes(begin,end,timezone,allDay);
        return display;
    }

    public void setTimes(long begin, long end, String zone, boolean day) {
        if (end <= begin) throw new IllegalArgumentException("The end must be after the start.");
        ZoneId z = ZoneId.of(day ? "UTC" : zone);
        java.time.ZonedDateTime s = Instant.ofEpochMilli(begin).atZone(z);
        java.time.ZonedDateTime e = Instant.ofEpochMilli(end).atZone(z);
        startDate=s.toLocalDate(); startTime=s.toLocalTime();
        endDate=e.toLocalDate(); endTime=e.toLocalTime();
        if (day) endDate=endDate.minusDays(1); // The provider end is exclusive.
        timezone=day ? ZoneId.systemDefault().getId() : z.getId();
        preferredStartOffset=s.getOffset(); preferredEndOffset=e.getOffset(); allDay=day;
        timingChanged=false;
    }

    private static long wallTime(LocalDate date, LocalTime time, String zone,
                                 ZoneOffset preferred) {
        LocalDateTime local = LocalDateTime.of(date, time);
        ZoneId z = ZoneId.of(zone);
        List<ZoneOffset> offsets = z.getRules().getValidOffsets(local);
        if (offsets.isEmpty()) {
            throw new IllegalArgumentException("This time does not exist because the clocks change. Choose another time.");
        }
        // Retain the original occurrence of an ambiguous local time when possible.
        ZoneOffset offset = offsets.contains(preferred) ? preferred : offsets.get(0);
        return local.toInstant(offset).toEpochMilli();
    }

    public long beginMillis() {
        if (allDay) return startDate.atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli();
        return wallTime(startDate, startTime, timezone, preferredStartOffset);
    }

    public long endMillis() {
        if (allDay) return endDate.plusDays(1).atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli();
        return wallTime(endDate, endTime, timezone, preferredEndOffset);
    }

    public String providerTimezone() { return allDay ? "UTC" : ZoneId.of(timezone).getId(); }

    public void chooseRecurrence(String rule, boolean keepOriginal, EventDraft original) {
        recurrence=keepOriginal ? original.recurrence : rule;
        recurrenceChanged=!keepOriginal;
    }

    public void chooseReminder(int minutes, boolean keepOriginal, EventDraft original) {
        reminderMinutes=keepOriginal ? original.reminderMinutes : minutes;
        remindersChanged=!keepOriginal;
    }

    public String duration() {
        long millis = Math.subtractExact(endMillis(), beginMillis());
        if (millis <= 0) throw new IllegalArgumentException("The end must be after the start.");
        if (allDay) return "P" + (millis / 86_400_000L) + "D";
        return "PT" + ((millis + 999L) / 1000L) + "S";
    }

    public void validate() {
        if (calendarId < 0) throw new IllegalArgumentException("Choose a writable calendar.");
        if (startDate==null || endDate==null || startTime==null || endTime==null)
            throw new IllegalArgumentException("Choose the event dates and times.");
        if (endMillis() <= beginMillis()) throw new IllegalArgumentException("The end must be after the start.");
        if (recurrenceChanged && recurrence!=null &&
            !recurrence.matches("FREQ=(DAILY|WEEKLY|MONTHLY|YEARLY)"))
            throw new IllegalArgumentException("Choose a supported repeat interval.");
        if (remindersChanged && reminderMinutes < -1)
            throw new IllegalArgumentException("Choose a valid reminder.");
    }

    public boolean sameForm(EventDraft d) {
        return id==d.id && calendarId==d.calendarId && allDay==d.allDay
            && reminderMinutes==d.reminderMinutes && remindersChanged==d.remindersChanged
            && Objects.equals(title,d.title) && Objects.equals(location,d.location)
            && Objects.equals(description,d.description) && Objects.equals(startDate,d.startDate)
            && Objects.equals(endDate,d.endDate) && Objects.equals(startTime,d.startTime)
            && Objects.equals(endTime,d.endTime) && Objects.equals(timezone,d.timezone)
            && Objects.equals(recurrence,d.recurrence) && recurrenceChanged==d.recurrenceChanged;
    }
}
