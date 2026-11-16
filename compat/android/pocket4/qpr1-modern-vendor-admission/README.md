# QPR1 modern vendor metadata admission

The official CP3A.260905.010 / 16176746 GSI's legacy no-VNDK action rejected
the current vendor even though its vendor, board and LLNDK APIs are 202604.
The first actual probe reached that reboot action. This adaptation changes
only the selected action, preserving the original import selector.

A synchronous script accepts one exact observed metadata tuple. It reads the
real Android properties, requires the obsolete VNDK property to be absent,
and checks board freezing, shipping SDK, vendor SDK and the exact official
QPR1 build. Missing, wrong or unreadable observations retain the original
bootloader reboot. It changes no property, library, APEX or official image.

The script is a new read-only leaf under the already existing `/vendor/etc`.
The rc override remains `/system/system_ext/etc/gsi/init.vndk-nodef.rc`.
The earlier absent-parent projection was rejected correctly; this correction
does not weaken the host's existing-parent requirement.

Nine controls run the actual shell logic with fixture getprop/reboot commands:

```sh
python3 -I -B test_modern_vendor_guard.py
```

The subsequent actual QPR1 execution observed this synchronous script exit
zero and progressed into normal init service startup. Its new blocker was
different: several guest directories inherited the private host umask, and
the critical hwservicemanager repeatedly aborted before boot completed.
The bound summary records those limits. A successful metadata admission
does not qualify VINTF, HALs, boot completion, applications or production
isolation. Original account data was not used.

The original GSI scripts and locked build source match byte for byte. See
the [VNDK deprecation documentation](https://source.android.com/docs/core/architecture/vndk)
and [AOSP GSI init selector](https://android.googlesource.com/platform/build/+/master/target/product/gsi/init.gsi.rc).
