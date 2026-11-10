# Alarm03: observed scheduler failure and exact fixture cleanup

The original Alarm03 controller exited with failure after it created one alarm. Its row selector incorrectly required expanded controls while the actual new row was collapsed. That original failure, five input count and first task close remain unchanged.

A separately reviewed cleanup used the exact saved DB claim (alarm 3, instance 1, 2026-11-05 18:54 GMT), then performed two real native inputs: expand its unique whole row, then Delete within that row. It verified the original two disabled templates and their full content hash, zero instances, zero current Clock scheduler entries, no active firing notification, unchanged protected state and restoration of the original Home task. The cleanup is a separate success and does not convert Alarm03 into a complete alarm business pass.

## Independent firing failure evidence

At 18:50:36, AlarmManager held two Clock RTC_WAKEUP operations for 18:54:00: the indicator broadcast and change_state service PendingIntent. The state-change entry used startService. At 19:02:51, each had one recorded wakeup at the due time and neither remained pending. Events independently show that the existing AlarmStateManager receiver started the Clock process at 18:54. However, the exact AlarmService record for instance 1 was unattached (app=null; startForegroundCount=0) and the DB remained in state 3, whose actual installed implementation is the high-priority upcoming-notification state. The firing notification was absent. The fixture was then removed.

This identifies the failure between attempted timed delivery and an attached AlarmService/state transition. It does not uniquely identify a particular ActivityManager policy branch. The current system/main log buffer no longer covers the due time; its missing lines and an empty UID log are not treated as evidence of no execution.

## Source contract and next correction

The installed AlarmService starts an alarm and its foreground notification only for requested state 5. Other state transitions cannot all be changed to foreground-service PendingIntents. The existing manifest-declared AlarmStateManager receiver already has an asynchronous state-handler route. Any new product candidate must preserve all state transitions, generation/instance checks and complete PendingIntent cancellation identity. No new APK or repaired alarm-delivery result is claimed here.

This package contains selected evidence, exact source hashes, controller sources and actual saved-tree regression results. Original full private service, notification, audio and other-app scheduler dumps are not included. Existing Timer or Clock reviews are not transferred to a future APK automatically.
