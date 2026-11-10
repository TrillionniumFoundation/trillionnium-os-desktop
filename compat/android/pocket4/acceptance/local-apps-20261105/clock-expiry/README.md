# Clock timer expiry01

A new 60-second timer was created through the real Clock UI after notification04 had successfully enabled Clock notifications. Its persisted state remained RUNNING through 28.245 seconds beyond the expected due time. The bounded trial failed. It was not converted to a pass by extending the wait.

The controller reopened Clock, paused this exact timer (the real stored remaining time was -42,145 ms), and deleted it through the UI. Both newly owned tasks were normally removed. No timer, stopwatch state, pending action, or owned task remained. Original alarm templates 1 and 2 remained disabled and byte-for-byte unchanged.

This preserves two independent facts: the notification permission/AppOps repair passed; background timer expiry did not pass. The root cause remains under read-only investigation. No audible output or alarm delivery is qualified by this trial.
