"""Original Camera release08 inputs and explicit new finite case limits.

The photo checks preserve the original business state machine. Its original
controller had no whole-case deadline. The bounds below are NEW execution
bounds, not a historical pass or a replacement for any of the five app gates.
"""

CAMERA = {'package': 'com.android.camera2', 'uid': 10062, 'version_code': 20002000,
    'component': 'com.android.camera2/com.android.camera.CameraLauncher',
    'apks': [{'bytes': 7709134,
        'sha256': '24632b0e1a1c22741177583b0dfd4a3fa71ff9b1d1b72af60a3d7cf373c7e61f'}],
    'certificate_sha256': 'a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc',
    'require_v3': True}
NATIVE_HELPER = {'package': 'local.pocket4.actions.v2', 'uid': 10125, 'version_code': 2,
    'component': None, 'apks': [{'bytes': 20847,
        'sha256': 'a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058'}],
    'certificate_sha256': None, 'require_v3': False}
PHOTO_LIMITS = {'business_seconds': 360, 'cleanup_seconds': 40,
    'maximum_UI_actions': 1, 'maximum_native_launches': 2,
    'native_launch_timeout': 45, 'maximum_new_images': 1,
    'shutter_dispatches': 1, 'new_image_readback_seconds': 25,
    'normal_close_readback_seconds': 8, 'provider_close_readback_seconds': 5,
    'account_mutations': 0, 'permission_writes': 0, 'package_mutations': 0,
    'media_delete_calls': 0, 'original_photos_read_or_modified': 0}
APP_GATES = ('camera.preview', 'camera.photo', 'camera.persist', 'camera.video', 'camera.recovery')
PHOTO_SCOPE = ('camera.preview', 'camera.photo', 'camera.persist')
PERMISSIONS = frozenset({'android.permission.POST_NOTIFICATIONS', 'android.permission.CAMERA',
    'android.permission.RECORD_AUDIO', 'android.permission.ACCESS_FINE_LOCATION',
    'android.permission.ACCESS_COARSE_LOCATION'})
DEVICE = '/dev/v4l/by-id/usb-SunplusIT_Inc_Integrated_Camera_JX20250923V2-video-index0'
PROVIDER_UNIT = 'pocket4-live-camera.service'
MEDIA_PROVIDER_APK = '/apex/com.android.mediaprovider/priv-app/MediaProvider@CP2A.260605.016/MediaProvider.apk'
MEDIA_PROVIDER_BYTES = 15447727
MEDIA_PROVIDER_SHA = 'b98258475c14043fe1f7e0d5a61caa13aa22dea426ffc589e83012f0377ce0f4'


def profiles(kind):
    if kind != 'camera_photo':
        raise RuntimeError('ONLY_THE_COMPLETE_ORIGINAL_SINGLE_PHOTO_CASE')
    return CAMERA, NATIVE_HELPER, PHOTO_LIMITS
