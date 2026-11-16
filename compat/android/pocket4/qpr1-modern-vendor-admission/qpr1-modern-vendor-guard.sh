#!/system/bin/sh
# Metadata admission for the CP3A.260905.010 / 16176746 x86 boot candidate.
# Android 15+ removed ro.vndk.version; vendor and LLNDK API levels replace that
# legacy presence test.  This exact tuple is the one observed from both pinned
# images and all eleven property snapshots in the preceding isolated boot.
# This guard does not establish VINTF, HAL, ART, application, or production
# qualification.  It changes no property and does not accept arbitrary APIs.

reject()
{
    printf '%s\n' "Droidloom QPR1 vendor metadata rejected: $1" >&2
    /system/bin/reboot bootloader
    exit 1
}

require_property()
{
    observed=$(/system/bin/getprop "$1") || reject "property-read:$1"
    [ "$observed" = "$2" ] || reject "property-value:$1"
}

require_property ro.vndk.version ''
require_property ro.board.api_level 202604
require_property ro.board.api_frozen true
require_property ro.vendor.api_level 202604
require_property ro.product.first_api_level 37
require_property ro.vendor.build.version.sdk 37
require_property ro.vendor.build.version.sdk_full 37.0
require_property ro.build.version.sdk 37
require_property ro.build.version.sdk_full 37.1
require_property ro.llndk.api_level 202604
require_property ro.build.id CP3A.260905.010
require_property ro.build.version.incremental 16176746

printf '%s\n' 'Droidloom QPR1 modern vendor metadata accepted: API 202604 / SDK 37'
exit 0
