"""Exact installed identities and finite current Camera video scope.

These profiles define future collection; no historical PID, task, nonce, audio
receipt or whole-application acceptance is carried into a fresh Main.
"""
import copy

CAMERA = {'package': 'com.android.camera2', 'uid': 10062, 'version_code': 20002000,
    'component': 'com.android.camera2/com.android.camera.CameraLauncher',
    'apks': [{'sha256': '0218041bc46f49c0c9622196e2a3610c641e0cc8f12386f23cdd88dc3a3ce18e', 'bytes': 11892407}],
    'certificate_sha256': 'a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc',
    'require_v3': True}
PLAYER = {'package': 'com.android.gallery3d', 'uid': 10064, 'version_code': 40030,
    'component': 'com.android.gallery3d/com.android.gallery3d.app.GalleryActivity',
    'apks': [{'sha256': '052e448c94aae064490539b23b32e130071ce80285d55d7e99654e1335749a5c', 'bytes': 7488378}],
    'certificate_sha256': 'a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc',
    'require_v3': True}
HELPER = {'package': 'local.pocket4.actions.v2', 'uid': 10125, 'version_code': 2,
    'component': None,
    'apks': [{'sha256': 'a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058', 'bytes': 20847}], 'certificate_sha256': None, 'require_v3': False}
LIMITS = {'business_seconds': 420, 'cleanup_seconds': 60, 'supervisor_seconds': 510,
    'actor_seconds': 24, 'recording_seconds': 20, 'capture_seconds': 21,
    'maximum_ui_actions': 9, 'video_bytes': 134217728}
AUDIO_ACTOR = {'path': '/home/alex/work/pocket4-android-final/qualification/'
    'camera-video-audio-client-build-20261108-r2/build-01/artifacts/camera-audio-client',
    'bytes': 3995920, 'sha256': '7e91ea8731fdac2b29951782fdac0caa94a8343d488fe6792e60f7c286908487'}
AUDIO_BUILD = {'path': '/home/alex/work/pocket4-android-final/qualification/'
    'camera-video-audio-client-build-20261108-r2/build-01/result.json',
    'bytes': 23538, 'sha256': 'a1005943e50c752b71653220bfe287a1412481e26ed4a831793019778d1ac9bf'}
MEDIA_PROVIDER_APK = '/apex/com.android.mediaprovider/priv-app/MediaProvider@CP2A.260605.016/MediaProvider.apk'
MEDIA_PROVIDER_BYTES = 15447727
MEDIA_PROVIDER_SHA = 'b98258475c14043fe1f7e0d5a61caa13aa22dea426ffc589e83012f0377ce0f4'
PROVIDER_UNIT = 'pocket4-live-camera.service'
DEVICE = '/dev/v4l/by-id/usb-SunplusIT_Inc_Integrated_Camera_JX20250923V2-video-index0'
PERMISSIONS = frozenset({'android.permission.POST_NOTIFICATIONS', 'android.permission.CAMERA',
    'android.permission.RECORD_AUDIO', 'android.permission.ACCESS_FINE_LOCATION',
    'android.permission.ACCESS_COARSE_LOCATION'})
VIDEO_COMPONENT = 'com.android.gallery3d/com.android.gallery3d.app.MovieActivity'
VIDEO_URI = 'content://media/external_primary/video/media'
HAL_EXE = '/apex/com.android.hardware.audio.droidloom/bin/hw/android.hardware.audio.service-aidl.droidloom'

def profiles(kind):
    if kind != 'camera_video':
        raise RuntimeError('ONLY_CURRENT_CAMERA_VIDEO_SCOPE')
    return tuple(copy.deepcopy(v) for v in (CAMERA, PLAYER, HELPER, LIMITS))
