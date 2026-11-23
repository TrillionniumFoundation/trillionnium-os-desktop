# Complete normal product projection. The selected source/release gate is
# enforced by the producer before this journaled configuration is installed.
# These are the observed normal AOSP provider includes, not copied images.
ZYGOTE_FORCE_64 := true
MODULE_BUILD_FROM_SOURCE := true
$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/generic_system.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/handheld_system_ext.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/telephony_system_ext.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/aosp_product.mk)

# One source/product owns all four normal partition images on this path.
PRODUCT_NAME := droidloom_x86_64
PRODUCT_DEVICE := droidloom_x86_64
PRODUCT_BRAND := Droidloom
PRODUCT_MODEL := Droidloom x86_64 cell
PRODUCT_MANUFACTURER := Droidloom

PRODUCT_SOONG_NAMESPACES += vendor/droidloom

$(call inherit-product, vendor/droidloom/android/native-bridge/product.mk)

PRODUCT_BUILD_SYSTEM_IMAGE := true
PRODUCT_BUILD_SYSTEM_OTHER_IMAGE := false
PRODUCT_BUILD_SYSTEM_EXT_IMAGE := true
PRODUCT_BUILD_PRODUCT_IMAGE := true
PRODUCT_BUILD_ODM_IMAGE := false
PRODUCT_BUILD_VENDOR_IMAGE := true
PRODUCT_BUILD_VENDOR_DLKM_IMAGE := false
PRODUCT_BUILD_ODM_DLKM_IMAGE := false
PRODUCT_BUILD_SYSTEM_DLKM_IMAGE := false
PRODUCT_BUILD_CACHE_IMAGE := false
PRODUCT_BUILD_RAMDISK_IMAGE := false
PRODUCT_BUILD_USERDATA_IMAGE := false
PRODUCT_BUILD_RECOVERY_IMAGE := false
PRODUCT_BUILD_BOOT_IMAGE := false
PRODUCT_BUILD_INIT_BOOT_IMAGE := false
PRODUCT_BUILD_DEBUG_BOOT_IMAGE := false
PRODUCT_BUILD_VENDOR_BOOT_IMAGE := false
PRODUCT_BUILD_VENDOR_KERNEL_BOOT_IMAGE := false
PRODUCT_BUILD_DEBUG_VENDOR_BOOT_IMAGE := false
PRODUCT_BUILD_VBMETA_IMAGE := false
PRODUCT_BUILD_SUPER_EMPTY_IMAGE := false

PRODUCT_SHIPPING_API_LEVEL := $(PLATFORM_SDK_VERSION)

PRODUCT_PACKAGES += \
    vendor_compatibility_matrix.xml \
    selinux_policy_vendor \
    libdroidloom_selinux_compat \
    droidloom-readiness \
    android.hardware.security.keymint-service.nonsecure \
    android.hardware.health-service.example \
    android.hardware.power-service.example \
    com.android.hardware.audio.droidloom \
    DroidloomFrameworkDisplayOverlay \
    DroidloomConnectivityOverlay \
    android.hardware.ethernet.prebuilt.xml \
    android.hardware.graphics.composer3-service.droidloom \
    droidloom-task-launcher \
    droidloom-input-bridge \
    droidloom-lmkd-compat \
    droidloom-classpath-wrapper \
    android.hardware.graphics.allocator-service.minigbm \
    mapper.minigbm \
    libgbm_mesa \
    dri_gbm \
    radeonsi_dri \
    libgallium_dri \
    libEGL_mesa \
    libGLESv1_CM_mesa \
    libGLESv2_mesa \
    vulkan.radeon

PRODUCT_COPY_FILES += \
    vendor/droidloom/android/device/droidloom_x86_64/cgroups.json:$(TARGET_COPY_OUT_VENDOR)/etc/cgroups.json \
    vendor/droidloom/android/device/droidloom_x86_64/task_profiles.json:$(TARGET_COPY_OUT_VENDOR)/etc/task_profiles.json \
    vendor/droidloom/android/device/droidloom_arm64/android.hardware.droidloom_input.xml:$(TARGET_COPY_OUT_VENDOR)/etc/permissions/android.hardware.droidloom_input.xml \
    vendor/droidloom/android/device/droidloom_arm64/android.software.activities_on_secondary_displays.xml:$(TARGET_COPY_OUT_VENDOR)/etc/permissions/android.software.activities_on_secondary_displays.xml \
    vendor/droidloom/android/device/droidloom_arm64/android.software.app_widgets.xml:$(TARGET_COPY_OUT_VENDOR)/etc/permissions/android.software.app_widgets.xml \
    vendor/droidloom/android/device/droidloom_arm64/audio_policy_configuration.xml:$(TARGET_COPY_OUT_VENDOR)/etc/audio_policy_configuration.xml \
    vendor/droidloom/android/device/droidloom_arm64/droidloom_primary_audio_policy_configuration.xml:$(TARGET_COPY_OUT_VENDOR)/etc/droidloom_primary_audio_policy_configuration.xml \
    frameworks/av/services/audiopolicy/config/audio_policy_volumes.xml:$(TARGET_COPY_OUT_VENDOR)/etc/audio_policy_volumes.xml \
    frameworks/av/services/audiopolicy/config/default_volume_tables.xml:$(TARGET_COPY_OUT_VENDOR)/etc/default_volume_tables.xml \
    frameworks/av/services/audiopolicy/config/surround_sound_configuration_5_0.xml:$(TARGET_COPY_OUT_VENDOR)/etc/surround_sound_configuration_5_0.xml

PRODUCT_VENDOR_PROPERTIES += \
    ro.zygote=zygote64 \
    ro.vendor.droidloom.surfaceflinger_direct=true \
    ro.vendor.droidloom.surfaceflinger_tasks=true \
    ro.opengles.version=196610 \
    ro.hardware.egl=mesa \
    ro.hardware.vulkan=radeon \
    dalvik.vm.heapstartsize=16m \
    dalvik.vm.heapgrowthlimit=256m \
    dalvik.vm.heapsize=512m \
    dalvik.vm.heaptargetutilization=0.75 \
    dalvik.vm.heapminfree=512k \
    dalvik.vm.heapmaxfree=8m

# Image sizing is performed by the normal build_image producer; each delivered
# image is independently bounded and read back by coherent_images.
PRODUCT_USE_DYNAMIC_PARTITION_SIZE := true
PRODUCT_ENFORCE_VINTF_MANIFEST := true
PRODUCT_PACKAGES += \
    services \
    framework-minus-apex \
    framework-res \
    IntentResolver \
    Settings \
    DroidloomSystemUI \
    DroidloomIME \
    DroidloomHome \
    com.android.art \
    com.android.virt \
    com.android.media.swcodec \
    com.android.tethering \
    com.android.profiling \
    libfs_mgr \
    apexd \
    ExternalStorageProvider \
    libandroidfw \
    libhwui \
    framework_compatibility_matrix.device.xml
