/*
 * Copyright 2026 The Droidloom Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package com.android.calendar.event;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.DatePickerDialog;
import android.app.Fragment;
import android.app.NotificationManager;
import android.app.TimePickerDialog;
import android.content.ContentUris;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.OperationApplicationException;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Bundle;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.os.RemoteException;
import android.provider.CalendarContract;
import android.provider.CalendarContract.Events;
import android.provider.CalendarContract.Calendars;
import android.provider.Settings;
import android.text.InputType;
import android.text.format.DateFormat;
import android.view.View;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import com.android.calendar.alerts.RestoredAlerts;

import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Restored Calendar editor and detail screen. Uses the existing component, permissions
 * and provider. Writes require Save, Delete, or explicit local-calendar confirmation.
 * No AccountManager account or online sync adapter is created.
 */
public class EditEventActivity extends Activity {
    private static final String WORKER_TAG="calendar-restored-editor-worker";
    private static final int CALENDAR_PERMISSION=402;
    private static final int NOTIFICATION_PERMISSION=403;
    private static final String FORM="calendar.editor.form";
    private static final String PENDING="calendar.editor.pending";
    private static final String VIEWING="calendar.editor.viewing";
    private static final String SNAPSHOT="calendar.editor.original";
    private static final String[] REPEAT_LABELS={"Does not repeat","Daily","Weekly","Monthly","Yearly"};
    private static final String[] REPEAT_RULES={null,"FREQ=DAILY","FREQ=WEEKLY","FREQ=MONTHLY","FREQ=YEARLY"};
    private static final int[] REMINDER_MINUTES={-1,0,5,10,15,30,60,1440};
    private static final String[] REMINDER_LABELS={
        "No reminder","At start time","5 minutes before","10 minutes before","15 minutes before",
        "30 minutes before","1 hour before","1 day before"
    };
    private Worker worker;
    private EventEditorStore.Loaded rendered;
    private EventDraft draft;
    private EventDraft originalForm;
    private Bundle restoreForm;
    private ContentValues restoreOriginal;
    private boolean viewing;
    private boolean interruptedWrite;
    private boolean resumed;
    private EditText title,location,description;
    private LinearLayout body;
    private TextView status;
    private Button blockedClose;
    private final List<View> controls=new ArrayList<>();

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        RestoredAlerts.acknowledgeOpen(this,getIntent());
        viewing=Intent.ACTION_VIEW.equals(getIntent().getAction());
        if(state!=null) {
            viewing=state.getBoolean(VIEWING,viewing);
            restoreForm=state.getBundle(FORM);
            restoreOriginal=state.getParcelable(SNAPSHOT);
            interruptedWrite=state.getBoolean(PENDING,false);
        }
        worker=(Worker)getFragmentManager().findFragmentByTag(WORKER_TAG);
        if(worker==null) {
            worker=new Worker();
            getFragmentManager().beginTransaction().add(worker,WORKER_TAG).commit();
            getFragmentManager().executePendingTransactions();
            worker.blocked=interruptedWrite;
        } else interruptedWrite=false; // The same retained worker is still authoritative.
        worker.owner=this;
        if(worker.loaded!=null || worker.busy || worker.completed!=null || worker.error!=null) render();
        else beginLoad();
    }

    @Override protected void onResume() {
        super.onResume();
        if(worker!=null) {
            worker.owner=this;
            // Returning from the separate editor must re-read the saved event.
            if(resumed && viewing && !worker.busy && worker.completed==null && !worker.blocked) {
                rendered=null; draft=null; originalForm=null; restoreForm=null;
                beginLoad();
            } else render();
        }
        resumed=true;
    }

    @Override protected void onPause() {
        readFields();
        super.onPause();
    }

    @Override protected void onDestroy() {
        if(worker!=null && worker.owner==this) worker.owner=null;
        super.onDestroy();
    }

    @Override protected void onNewIntent(Intent incoming) {
        super.onNewIntent(incoming);
        if(worker!=null && worker.busy && !"load".equals(worker.action)) {
            Toast.makeText(this,"Wait for the current change to finish.",Toast.LENGTH_LONG).show();
            return;
        }
        discardThen(() -> {
            setIntent(new Intent(incoming)); viewing=Intent.ACTION_VIEW.equals(incoming.getAction());
            rendered=null; draft=null; originalForm=null; restoreForm=null; restoreOriginal=null;
            interruptedWrite=false;
            worker.clearResult(); beginLoad();
        });
    }

    private boolean granted(String name) {
        return checkSelfPermission(name)==PackageManager.PERMISSION_GRANTED;
    }

    private void beginLoad() {
        if(!granted(Manifest.permission.READ_CALENDAR) ||
            (!viewing && !granted(Manifest.permission.WRITE_CALENDAR))) {
            simpleMessage("Calendar permission is needed to display and edit events.",false);
            button("Allow Calendar access",() -> requestPermissions(
                new String[]{Manifest.permission.READ_CALENDAR,Manifest.permission.WRITE_CALENDAR},
                CALENDAR_PERMISSION));
            return;
        }
        try {
            final Intent intent=getIntent();
            final String action=intent.getAction();
            final boolean insert=Intent.ACTION_INSERT.equals(action) ||
                (Intent.ACTION_INSERT_OR_EDIT.equals(action) &&
                 (intent.getData()==null || intent.getData().getPathSegments().size()<2));
            final long id;
            if(insert) {
                Uri data=intent.getData();
                if(data!=null && (!"content".equals(data.getScheme()) ||
                    !CalendarContract.AUTHORITY.equals(data.getAuthority()) ||
                    !"/events".equals(data.getPath()) || data.getQuery()!=null || data.getFragment()!=null))
                    throw new IllegalArgumentException("This is not a Calendar event request.");
                id=-1;
            } else if(Intent.ACTION_VIEW.equals(action) || Intent.ACTION_EDIT.equals(action) ||
                      Intent.ACTION_INSERT_OR_EDIT.equals(action)) {
                id=EventEditorStore.eventId(intent.getData());
            } else throw new IllegalArgumentException("This Calendar action is not supported.");
            ZonedDateTime now=ZonedDateTime.now().withSecond(0).withNano(0);
            now=now.plusMinutes((15-now.getMinute()%15)%15);
            long begin=intent.getLongExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME,now.toInstant().toEpochMilli());
            boolean allDay=intent.getBooleanExtra(CalendarContract.EXTRA_EVENT_ALL_DAY,false);
            long end=intent.getLongExtra(CalendarContract.EXTRA_EVENT_END_TIME,
                Math.addExact(begin,allDay?86_400_000L:3_600_000L));
            if(allDay && id<0) {
                begin=Instant.ofEpochMilli(begin).atZone(ZoneOffset.UTC).toLocalDate()
                    .atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli();
                end=Instant.ofEpochMilli(end).atZone(ZoneOffset.UTC).toLocalDate()
                    .atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli();
            }
            worker.load(getApplicationContext(),id,intent.getLongExtra(Events.CALENDAR_ID,-1),
                begin,end,allDay,intent.getStringExtra(Events.TITLE),
                intent.getStringExtra(Events.EVENT_LOCATION),intent.getStringExtra(Events.DESCRIPTION));
            render();
        } catch(RuntimeException failure) {
            worker.error=failure.getMessage()==null?"This event cannot be opened.":failure.getMessage();
            render();
        }
    }

    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] results) {
        super.onRequestPermissionsResult(request,permissions,results);
        if(request==NOTIFICATION_PERMISSION) {
            if(draft!=null) { readFields(); buildForm(); render(); }
            return;
        }
        if(request!=CALENDAR_PERMISSION) return;
        if(granted(Manifest.permission.READ_CALENDAR) &&
           (viewing || granted(Manifest.permission.WRITE_CALENDAR))) beginLoad();
        else simpleMessage("Calendar permission was not granted. No event was changed.",false);
    }

    private int dp(int value) {
        return Math.round(value*getResources().getDisplayMetrics().density);
    }

    private void newLayout() {
        title=location=description=null; blockedClose=null; controls.clear();
        ScrollView scroll=new ScrollView(this); scroll.setFillViewport(true);
        body=new LinearLayout(this); body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(dp(20),dp(16),dp(20),dp(24));
        scroll.addView(body,new ScrollView.LayoutParams(-1,-2));
        setContentView(scroll);
        status=text("",16); status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
    }

    private TextView text(String value,int size) {
        TextView view=new TextView(this); view.setText(value); view.setTextSize(size);
        view.setPadding(0,dp(5),0,dp(5));
        body.addView(view,new LinearLayout.LayoutParams(-1,-2));
        return view;
    }

    private Button button(String label,Runnable action) {
        Button b=new Button(this); b.setText(label); b.setAllCaps(false);
        b.setOnClickListener(v -> action.run());
        body.addView(b,new LinearLayout.LayoutParams(-1,-2)); controls.add(b); return b;
    }

    private EditText field(String label,String value,boolean multi) {
        TextView caption=text(label,14);
        EditText edit=new EditText(this); edit.setId(View.generateViewId());
        caption.setLabelFor(edit.getId()); edit.setHint(label); edit.setText(value);
        edit.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_CAP_SENTENCES|
            (multi?InputType.TYPE_TEXT_FLAG_MULTI_LINE:0));
        edit.setSingleLine(!multi); edit.setMinLines(multi?3:1);
        body.addView(edit,new LinearLayout.LayoutParams(-1,-2)); controls.add(edit); return edit;
    }

    private void simpleMessage(String message,boolean loading) {
        newLayout(); setTitle("Calendar"); status.setText(message);
        if(!loading) button("Close",this::finish);
    }

    private void render() {
        if(isFinishing() || worker==null) return;
        if("create-calendar".equals(worker.completed)) {
            long id=ContentUris.parseId(worker.result);
            getIntent().putExtra(Events.CALENDAR_ID,id);
            worker.clearResult(); rendered=null; draft=null; originalForm=null;
            restoreForm=null; restoreOriginal=null;
            Toast.makeText(this,"Local calendar created.",Toast.LENGTH_SHORT).show();
            beginLoad(); return;
        }
        if(worker.completed!=null) {
            String done=worker.completed;
            RestoredAlerts.refresh(this);
            setResult(RESULT_OK,new Intent().setData(worker.result));
            Toast.makeText(this,"delete".equals(done)?"Event deleted.":"Event saved.",Toast.LENGTH_SHORT).show();
            finish(); return;
        }
        if(worker.loaded==null) {
            simpleMessage(worker.error!=null?worker.error:"Loading event…",worker.busy);
            return;
        }
        if(worker.loaded.calendars.isEmpty()) {
            newLayout(); setTitle("New event");
            text("No writable calendar",24);
            text("Create a calendar on this device to save events. No account sign-in is needed.",16);
            if(worker.error!=null) status.setText(worker.error);
            if(worker.blocked) {
                text("Creation could not be confirmed. Close this screen and check the calendar list before trying again.",16);
            } else if(worker.busy) status.setText("Creating local calendar…");
            else button("Create local calendar",this::confirmLocalCalendar);
            Button close=button("Close",this::finish); close.setEnabled(!worker.busy);
            return;
        }
        if(rendered!=worker.loaded) {
            title=location=description=null;
            rendered=worker.loaded; draft=rendered.draft.copy(); originalForm=draft.copy();
            if(restoreForm!=null) {
                try {
                    if(draft.id>=0 && !java.util.Objects.equals(restoreOriginal,rendered.original)) {
                        worker.blocked=true;
                        worker.error="This event changed while the editor was closed. Reopen it before editing.";
                    } else restore(draft,restoreForm);
                }
                catch(RuntimeException ignored) { draft=rendered.draft.copy(); }
                restoreForm=null; restoreOriginal=null;
            }
            if(!rendered.canWrite) viewing=true;
            buildForm();
        }
        boolean writing=worker.busy && !"load".equals(worker.action);
        for(View v:controls) v.setEnabled(!writing);
        if(worker.blocked) {
            status.setText(worker.error!=null?worker.error:
                "A change may have completed. Close this screen and check the calendar before trying again.");
            for(View v:controls) v.setEnabled(false);
            // Closing does not submit or repeat an operation.
            if(blockedClose==null) blockedClose=button("Close",this::finish);
            blockedClose.setEnabled(true);
        } else if(worker.error!=null) status.setText(worker.error);
        else status.setText(writing?("delete".equals(worker.action)?"Deleting event…":"Saving event…"):"");
    }

    private void buildForm() {
        readFields(); newLayout();
        setTitle(viewing?"Event details":(draft.id>=0?"Edit event":"New event"));
        if(viewing) {
            text(draft.title.isEmpty()?"(No title)":draft.title,24).setTextIsSelectable(true);
            text(dateSummary(),18);
            if(!draft.location.isEmpty()) text(draft.location,16).setTextIsSelectable(true);
            if(!draft.description.isEmpty()) text(draft.description,16).setTextIsSelectable(true);
            text("Calendar: "+selectedCalendar().toString(),14);
            if(rendered.recurring) text(rendered.exception?"This occurrence of a repeating event.":"Repeating event.",14);
            if(rendered.originalReminderCount>0) text("Reminders: "+rendered.originalReminderCount,14);
            if(rendered.canWrite) {
                button("Edit",() -> {
                    Intent edit=new Intent(Intent.ACTION_EDIT,ContentUris.withAppendedId(Events.CONTENT_URI,draft.id));
                    edit.setClass(this,EditEventActivity.class); startActivity(edit);
                });
                if(granted(Manifest.permission.WRITE_CALENDAR)) button("Delete",this::confirmDelete);
            } else text("This event is read-only.",14);
            button("Close",this::finish);
            return;
        }
        title=field("Title",draft.title,false);
        location=field("Location",draft.location,false);
        description=field("Description",draft.description,true);
        text("Calendar",14);
        Spinner calendars=new Spinner(this);
        calendars.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,rendered.calendars));
        int selected=0;
        for(int i=0;i<rendered.calendars.size();i++) if(rendered.calendars.get(i).id==draft.calendarId) selected=i;
        calendars.setSelection(selected);
        calendars.setEnabled(draft.id<0);
        body.addView(calendars,new LinearLayout.LayoutParams(-1,-2));
        if(draft.id<0) controls.add(calendars);
        calendars.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override public void onNothingSelected(AdapterView<?> parent) {}
            @Override public void onItemSelected(AdapterView<?> parent,View v,int position,long id) {
                draft.calendarId=rendered.calendars.get(position).id;
            }
        });
        CheckBox day=new CheckBox(this); day.setText("All day"); day.setChecked(draft.allDay);
        body.addView(day); controls.add(day);
        day.setOnCheckedChangeListener((v,checked) -> {
            readFields(); draft.allDay=checked; draft.timingChanged=true; buildForm();
        });
        button("Starts: "+displayDate(draft.startDate),() -> pickDate(true));
        if(!draft.allDay) button("Start time: "+displayTime(draft.startTime),() -> pickTime(true));
        button("Ends: "+displayDate(draft.endDate),() -> pickDate(false));
        if(!draft.allDay) {
            button("End time: "+displayTime(draft.endTime),() -> pickTime(false));
            button("Time zone: "+draft.timezone,this::pickTimezone);
        }
        if(rendered.recurring && draft.id>=0 && !rendered.exception)
            text("Edits apply to the entire repeating series.",14);
        repeatControl(); reminderControl();
        button("Save",this::save);
        button("Cancel",() -> discardThen(this::finish));
        if(draft.id>=0) button("Delete event",this::confirmDelete);
    }

    private EventEditorStore.CalendarChoice selectedCalendar() {
        for(EventEditorStore.CalendarChoice value:rendered.calendars)
            if(value.id==draft.calendarId) return value;
        return rendered.calendars.get(0);
    }

    private String displayDate(LocalDate date) {
        return date.format(DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM));
    }
    private String displayTime(LocalTime time) {
        return time.format(DateTimeFormatter.ofPattern(DateFormat.is24HourFormat(this)?"HH:mm":"h:mm a"));
    }
    private String dateSummary() {
        if(draft.allDay) return displayDate(draft.startDate)+" – "+displayDate(draft.endDate)+" · All day";
        return displayDate(draft.startDate)+" "+displayTime(draft.startTime)+" – "+
            displayDate(draft.endDate)+" "+displayTime(draft.endTime)+" · "+draft.timezone;
    }

    private void pickDate(boolean start) {
        readFields(); LocalDate old=start?draft.startDate:draft.endDate;
        new DatePickerDialog(this,(view,year,month,day) -> {
            LocalDate value=LocalDate.of(year,month+1,day);
            if(start) draft.startDate=value; else draft.endDate=value;
            draft.timingChanged=true; buildForm();
        },old.getYear(),old.getMonthValue()-1,old.getDayOfMonth()).show();
    }
    private void pickTime(boolean start) {
        readFields(); LocalTime old=start?draft.startTime:draft.endTime;
        new TimePickerDialog(this,(view,hour,minute) -> {
            if(start) draft.startTime=LocalTime.of(hour,minute); else draft.endTime=LocalTime.of(hour,minute);
            draft.timingChanged=true; buildForm();
        },old.getHour(),old.getMinute(),DateFormat.is24HourFormat(this)).show();
    }
    private void pickTimezone() {
        readFields(); String[] zones=ZoneId.getAvailableZoneIds().toArray(new String[0]); Arrays.sort(zones);
        new AlertDialog.Builder(this).setTitle("Time zone")
            .setSingleChoiceItems(zones,Arrays.binarySearch(zones,draft.timezone),(dialog,which) -> {
                draft.timezone=zones[which]; draft.preferredStartOffset=draft.preferredEndOffset=null;
                draft.timingChanged=true; dialog.dismiss(); buildForm();
            }).setNegativeButton("Cancel",null).show();
    }
    private void repeatControl() {
        text("Repeats",14);
        List<String> labels=new ArrayList<>(Arrays.asList(REPEAT_LABELS));
        final int keepOriginalIndex=rendered.recurring ? labels.size() : -1;
        if(keepOriginalIndex>=0) labels.add("Existing repeat pattern (unchanged)");
        int initial=-1;
        for(int i=0;i<REPEAT_RULES.length;i++)
            if(java.util.Objects.equals(REPEAT_RULES[i],draft.recurrence)) initial=i;
        if(keepOriginalIndex>=0 && !draft.recurrenceChanged) initial=keepOriginalIndex;
        if(initial<0) initial=0;
        final int unchangedIndex=initial;
        Spinner repeat=new Spinner(this);
        repeat.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,labels));
        repeat.setSelection(initial); repeat.setEnabled(!rendered.exception);
        body.addView(repeat,new LinearLayout.LayoutParams(-1,-2)); if(!rendered.exception) controls.add(repeat);
        repeat.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            private boolean first=true;
            @Override public void onNothingSelected(AdapterView<?> parent) {}
            @Override public void onItemSelected(AdapterView<?> parent,View v,int position,long id) {
                if(first) { first=false; if(position==unchangedIndex) return; }
                if(position==keepOriginalIndex)
                    draft.chooseRecurrence(null,true,rendered.draft);
                else if(position<REPEAT_RULES.length)
                    draft.chooseRecurrence(REPEAT_RULES[position],false,rendered.draft);
            }
        });
    }
    private void reminderControl() {
        text("Reminder",14);
        NotificationManager notifications=getSystemService(NotificationManager.class);
        if(notifications!=null && !notifications.areNotificationsEnabled()) {
            text("Calendar notifications are disabled. Events can be saved, but reminders will not be displayed.",14);
            button("Enable reminder notifications",() -> {
                if(Build.VERSION.SDK_INT>=33 && !granted("android.permission.POST_NOTIFICATIONS"))
                    requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"},NOTIFICATION_PERMISSION);
                else startActivity(new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                    .putExtra(Settings.EXTRA_APP_PACKAGE,getPackageName()));
            });
        }
        List<String> labels=new ArrayList<>(Arrays.asList(REMINDER_LABELS));
        final int keepOriginalIndex=rendered.originalReminderCount>0 ? labels.size() : -1;
        if(keepOriginalIndex>=0) labels.add("Existing reminders (unchanged)");
        int initial=-1;
        if(!rendered.customReminders || draft.remindersChanged) {
            for(int i=0;i<REMINDER_MINUTES.length;i++) if(REMINDER_MINUTES[i]==draft.reminderMinutes) initial=i;
        }
        if(keepOriginalIndex>=0 && !draft.remindersChanged) initial=keepOriginalIndex;
        if(initial<0) initial=0;
        final int unchangedIndex=initial;
        Spinner reminder=new Spinner(this);
        reminder.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,labels));
        reminder.setSelection(initial); body.addView(reminder,new LinearLayout.LayoutParams(-1,-2)); controls.add(reminder);
        reminder.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            private boolean first=true;
            @Override public void onNothingSelected(AdapterView<?> parent) {}
            @Override public void onItemSelected(AdapterView<?> parent,View v,int position,long id) {
                if(first) { first=false; if(position==unchangedIndex) return; }
                if(position==keepOriginalIndex)
                    draft.chooseReminder(-1,true,rendered.draft);
                else if(position<REMINDER_MINUTES.length)
                    draft.chooseReminder(REMINDER_MINUTES[position],false,rendered.draft);
            }
        });
    }

    private void readFields() {
        if(draft==null || viewing) return;
        if(title!=null) draft.title=title.getText().toString();
        if(location!=null) draft.location=location.getText().toString();
        if(description!=null) draft.description=description.getText().toString();
    }
    private void save() {
        if(worker.busy || worker.blocked) return;
        readFields();
        try {
            draft.validate();
            worker.save(getApplicationContext(),draft.copy()); render();
        } catch(RuntimeException e) { status.setText(e.getMessage()); }
    }
    private void confirmDelete() {
        if(worker.busy || worker.blocked || draft.id<0) return;
        new AlertDialog.Builder(this).setTitle(rendered.recurring && !rendered.exception
            ?"Delete the entire repeating series?":"Delete this event?")
            .setMessage("This removes the saved event and its reminders.")
            .setNegativeButton("Cancel",null)
            .setPositiveButton("Delete",(dialog,which) -> {
                if(!worker.busy && !worker.blocked) { worker.delete(getApplicationContext()); render(); }
            }).show();
    }
    private void confirmLocalCalendar() {
        if(worker.busy || worker.blocked || worker.loaded==null ||
            !worker.loaded.calendars.isEmpty()) return;
        EditText name=new EditText(this); name.setHint("Calendar name"); name.setSingleLine(true);
        name.setText("On this device");
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("Create local calendar")
            .setMessage("Events stay in this device's Calendar database. This does not add an online account.")
            .setView(name).setNegativeButton("Cancel",null).setPositiveButton("Create",null).create();
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            String label=name.getText().toString().trim();
            if(label.isEmpty() || label.length()>255) {
                name.setError("Enter a name of 1 to 255 characters."); return;
            }
            if(worker.busy || worker.blocked) return;
            dialog.dismiss(); worker.createCalendar(getApplicationContext(),label); render();
        }));
        dialog.show();
    }
    private void discardThen(Runnable next) {
        readFields();
        if(!viewing && draft!=null && originalForm!=null && !draft.sameForm(originalForm)) {
            new AlertDialog.Builder(this).setTitle("Discard changes?")
                .setMessage("Your changes have not been saved.")
                .setNegativeButton("Keep editing",null)
                .setPositiveButton("Discard",(dialog,which) -> next.run()).show();
        } else next.run();
    }
    @Override public void onBackPressed() {
        if(worker!=null && worker.busy && !"load".equals(worker.action)) {
            Toast.makeText(this,"Wait for the current change to finish.",Toast.LENGTH_SHORT).show(); return;
        }
        discardThen(this::finish);
    }

    @Override protected void onSaveInstanceState(Bundle state) {
        readFields();
        if(draft!=null) state.putBundle(FORM,bundle(draft));
        if(worker!=null && worker.loaded!=null && worker.loaded.original!=null)
            state.putParcelable(SNAPSHOT,new ContentValues(worker.loaded.original));
        state.putBoolean(VIEWING,viewing);
        state.putBoolean(PENDING,worker!=null && (worker.blocked ||
            (worker.busy && !"load".equals(worker.action))));
        super.onSaveInstanceState(state);
    }
    private static Bundle bundle(EventDraft d) {
        Bundle b=new Bundle();
        b.putLong("id",d.id); b.putLong("calendar",d.calendarId);
        b.putString("title",d.title); b.putString("location",d.location); b.putString("description",d.description);
        b.putString("startDate",d.startDate.toString()); b.putString("endDate",d.endDate.toString());
        b.putString("startTime",d.startTime.toString()); b.putString("endTime",d.endTime.toString());
        b.putString("timezone",d.timezone); b.putBoolean("allDay",d.allDay);
        b.putString("recurrence",d.recurrence); b.putBoolean("recurrenceChanged",d.recurrenceChanged);
        b.putBoolean("timingChanged",d.timingChanged); b.putBoolean("remindersChanged",d.remindersChanged);
        b.putInt("reminder",d.reminderMinutes);
        b.putString("startOffset",d.preferredStartOffset==null?null:d.preferredStartOffset.toString());
        b.putString("endOffset",d.preferredEndOffset==null?null:d.preferredEndOffset.toString());
        return b;
    }
    private static void restore(EventDraft d,Bundle b) {
        if(b.getLong("id",-2)!=d.id) throw new IllegalArgumentException("Different restored event.");
        d.calendarId=b.getLong("calendar",d.calendarId); d.title=b.getString("title","");
        d.location=b.getString("location",""); d.description=b.getString("description","");
        d.startDate=LocalDate.parse(b.getString("startDate")); d.endDate=LocalDate.parse(b.getString("endDate"));
        d.startTime=LocalTime.parse(b.getString("startTime")); d.endTime=LocalTime.parse(b.getString("endTime"));
        d.timezone=b.getString("timezone"); d.allDay=b.getBoolean("allDay");
        d.recurrence=b.getString("recurrence"); d.recurrenceChanged=b.getBoolean("recurrenceChanged");
        d.timingChanged=b.getBoolean("timingChanged"); d.remindersChanged=b.getBoolean("remindersChanged");
        d.reminderMinutes=b.getInt("reminder",-1);
        String offset=b.getString("startOffset"); d.preferredStartOffset=offset==null?null:ZoneOffset.of(offset);
        offset=b.getString("endOffset"); d.preferredEndOffset=offset==null?null:ZoneOffset.of(offset);
    }

    /** One retained writer, with no retries or replay after configuration changes. */
    public static class Worker extends Fragment {
        private final ExecutorService executor=Executors.newSingleThreadExecutor();
        private final Handler main=new Handler(Looper.getMainLooper());
        private int generation;
        private EditEventActivity owner;
        private EventEditorStore.Loaded loaded;
        private boolean busy,blocked;
        private String action="idle",error,completed;
        private Uri result;
        @Override public void onCreate(Bundle state) { super.onCreate(state); setRetainInstance(true); }
        @Override public void onDetach() { owner=null; super.onDetach(); }
        @Override public void onDestroy() { executor.shutdown(); super.onDestroy(); }
        private void notifyOwner() { if(owner!=null) owner.render(); }
        private void clearResult() { error=completed=null; result=null; loaded=null; }
        private void load(Context context,long id,long calendar,long begin,long end,boolean day,
                          String title,String location,String description) {
            if(busy && !"load".equals(action)) return;
            final int request=++generation;
            busy=true; action="load"; loaded=null; error=null;
            executor.execute(() -> {
                EventEditorStore.Loaded value=null; String failure=null;
                try { value=new EventEditorStore(context.getContentResolver()).load(
                    id,calendar,begin,end,day,title,location,description); }
                catch(Exception e) { failure=message(e,false); }
                final EventEditorStore.Loaded answer=value; final String problem=failure;
                main.post(() -> {
                    if(request!=generation) return;
                    loaded=answer; error=problem; busy=false; action="idle"; notifyOwner();
                });
            });
        }
        private void save(Context context,EventDraft draft) {
            if(busy || blocked || loaded==null) return;
            busy=true; action="save"; error=null;
            executor.execute(() -> {
                Uri answer=null; Exception failure=null;
                try { answer=new EventEditorStore(context.getContentResolver()).save(loaded,draft); }
                catch(Exception e) { failure=e; }
                final Uri saved=answer; final Exception problem=failure;
                main.post(() -> finishWrite("save",saved,problem));
            });
        }
        private void delete(Context context) {
            if(busy || blocked || loaded==null) return;
            busy=true; action="delete"; error=null;
            executor.execute(() -> {
                Exception failure=null;
                try { new EventEditorStore(context.getContentResolver()).delete(loaded); }
                catch(Exception e) { failure=e; }
                final Exception problem=failure;
                main.post(() -> finishWrite("delete",null,problem));
            });
        }
        private void createCalendar(Context context,String label) {
            if(busy || blocked || loaded==null || !loaded.calendars.isEmpty()) return;
            busy=true; action="create-calendar"; error=null;
            executor.execute(() -> {
                Uri answer=null; Exception failure=null;
                try {
                    long id=new EventEditorStore(context.getContentResolver()).createLocalCalendar(label);
                    answer=ContentUris.withAppendedId(Calendars.CONTENT_URI,id);
                } catch(Exception e) { failure=e; }
                final Uri saved=answer; final Exception problem=failure;
                main.post(() -> finishWrite("create-calendar",saved,problem));
            });
        }
        private void finishWrite(String kind,Uri uri,Exception failure) {
            busy=false; action="idle";
            if(failure==null) { completed=kind; result=uri; }
            else {
                // An interrupted remote call can have committed. Never submit it again here.
                blocked=!(failure instanceof OperationApplicationException) &&
                        !(failure instanceof SecurityException) &&
                        !(failure instanceof IllegalArgumentException);
                error=message(failure,true);
            }
            notifyOwner();
        }
        private static String message(Exception e,boolean writing) {
            if(e instanceof OperationApplicationException)
                return "The event or calendar changed. Close and reopen it before saving.";
            if(e instanceof SecurityException)
                return "Calendar permission is unavailable. No further change was submitted.";
            if(e instanceof RemoteException)
                return "The calendar service was interrupted. Check the calendar before trying again.";
            if(e instanceof IllegalArgumentException || e instanceof IllegalStateException)
                return e.getMessage()==null?"This event cannot be changed.":e.getMessage();
            return writing?"The change could not be confirmed. Check the calendar before trying again.":
                "The event could not be loaded. Close this screen and try again.";
        }
    }
}
