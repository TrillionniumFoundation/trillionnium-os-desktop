#!/usr/bin/env python3
"""Verify one complete S41 APK with the actual ordinary-owner S38 tools."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time

ROOT = Path('/home/alex/work/pocket4-zbj-operator-full-verification-20261106-s42')
FIELDS = ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "TZ": "UTC"}
MAX_TOOL_OUTPUT = 4 * 1024 * 1024
SAVED_PM_SIGNER = '556246aaaf05f61c8bbb9587dfc0660e01f6c3c6813ec038d18684d3ab378bbe'
TOOL_BINDINGS = {'aapt': {'observed': {'bytes': 30680, 'file': {'st_ctime_ns': 1791415705179294996, 'st_dev': 66306, 'st_gid': 0, 'st_ino': 108138269, 'st_mode': 33261, 'st_mtime_ns': 1757926427000000000, 'st_nlink': 1, 'st_size': 30680, 'st_uid': 0}, 'sha256': 'd9c0d90fc4bcf03d57cbf4fe19ca66c80280ac760c53245c8678b9837844b972'}, 'pin': {'bytes': 30680, 'declared_path': '/usr/lib/android-sdk/build-tools/debian/aapt', 'resolved_path': '/usr/lib/android-sdk/build-tools/debian/aapt', 'sha256': 'd9c0d90fc4bcf03d57cbf4fe19ca66c80280ac760c53245c8678b9837844b972'}}, 'apksigner_jar': {'observed': {'bytes': 521108, 'file': {'st_ctime_ns': 1791415705147294650, 'st_dev': 66306, 'st_gid': 0, 'st_ino': 108005159, 'st_mode': 33188, 'st_mtime_ns': 1741954421000000000, 'st_nlink': 1, 'st_size': 521108, 'st_uid': 0}, 'sha256': '98346a3200d6030e247ccba0e47b354b6113ec2068dcea6c43558b01fe5885c2'}, 'pin': {'bytes': 521108, 'declared_path': '/usr/share/java/apksigner.jar', 'resolved_path': '/usr/share/java/apksigner-35.0.2.jar', 'sha256': '98346a3200d6030e247ccba0e47b354b6113ec2068dcea6c43558b01fe5885c2'}}, 'java': {'observed': {'bytes': 8528, 'file': {'st_ctime_ns': 1792770278197673619, 'st_dev': 66306, 'st_gid': 1000, 'st_ino': 40663514, 'st_mode': 33277, 'st_mtime_ns': 1792770278197673619, 'st_nlink': 1, 'st_size': 8528, 'st_uid': 1000}, 'sha256': 'cfa21aeadd00925925c9e1287f5c08f3e04ee7f26a9e23d9dbfb16149153d842'}, 'pin': {'bytes': 8528, 'declared_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/bin/java', 'resolved_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/bin/java', 'sha256': 'cfa21aeadd00925925c9e1287f5c08f3e04ee7f26a9e23d9dbfb16149153d842'}}, 'java_security': {'observed': {'bytes': 64249, 'file': {'st_ctime_ns': 1792770278199673482, 'st_dev': 66306, 'st_gid': 1000, 'st_ino': 40663555, 'st_mode': 33204, 'st_mtime_ns': 1792770278199673482, 'st_nlink': 1, 'st_size': 64249, 'st_uid': 1000}, 'sha256': '78f06ea1ce6fe10c188c99f6e4ca5631060e6e1b193ae598c0dfc6f3c3b6ac75'}, 'pin': {'bytes': 64249, 'declared_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/conf/security/java.security', 'resolved_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/conf/security/java.security', 'sha256': '78f06ea1ce6fe10c188c99f6e4ca5631060e6e1b193ae598c0dfc6f3c3b6ac75'}}, 'jdk_modules': {'observed': {'bytes': 141608978, 'file': {'st_ctime_ns': 1792770278872627336, 'st_dev': 66306, 'st_gid': 1000, 'st_ino': 40664004, 'st_mode': 33204, 'st_mtime_ns': 1792770278872627336, 'st_nlink': 1, 'st_size': 141608978, 'st_uid': 1000}, 'sha256': '4bddbec43a2fbf497528b9b0227a285e80c015c825921dc7a4181bdb4176ad36'}, 'pin': {'bytes': 141608978, 'declared_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/modules', 'resolved_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/modules', 'sha256': '4bddbec43a2fbf497528b9b0227a285e80c015c825921dc7a4181bdb4176ad36'}}, 'jdk_release': {'observed': {'bytes': 1246, 'file': {'st_ctime_ns': 1792770279240602138, 'st_dev': 66306, 'st_gid': 1000, 'st_ino': 40664019, 'st_mode': 33204, 'st_mtime_ns': 1792770279240602138, 'st_nlink': 1, 'st_size': 1246, 'st_uid': 1000}, 'sha256': 'd6854c41e3ef131089538dc4362452517b16061ebabb1931f2d287bf7ea78c3c'}, 'pin': {'bytes': 1246, 'declared_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/release', 'resolved_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/release', 'sha256': 'd6854c41e3ef131089538dc4362452517b16061ebabb1931f2d287bf7ea78c3c'}}, 'jvm_cfg': {'observed': {'bytes': 29, 'file': {'st_ctime_ns': 1792770278329664568, 'st_dev': 66306, 'st_gid': 1000, 'st_ino': 40663966, 'st_mode': 33204, 'st_mtime_ns': 1792770278329664568, 'st_nlink': 1, 'st_size': 29, 'st_uid': 1000}, 'sha256': 'aa9efb969444c1484e29adecab55a122458090616e766b2f1230ef05bc3867e0'}, 'pin': {'bytes': 29, 'declared_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/jvm.cfg', 'resolved_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/jvm.cfg', 'sha256': 'aa9efb969444c1484e29adecab55a122458090616e766b2f1230ef05bc3867e0'}}, 'libjava': {'observed': {'bytes': 163840, 'file': {'st_ctime_ns': 1792770278348663265, 'st_dev': 66306, 'st_gid': 1000, 'st_ino': 40663979, 'st_mode': 33204, 'st_mtime_ns': 1792770278348663265, 'st_nlink': 1, 'st_size': 163840, 'st_uid': 1000}, 'sha256': '39638b30e207d063cfe2c5bd19d36707f80843fe30481c8723f68e427ee4b331'}, 'pin': {'bytes': 163840, 'declared_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/libjava.so', 'resolved_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/libjava.so', 'sha256': '39638b30e207d063cfe2c5bd19d36707f80843fe30481c8723f68e427ee4b331'}}, 'libjimage': {'observed': {'bytes': 142408, 'file': {'st_ctime_ns': 1792770278352916149, 'st_dev': 66306, 'st_gid': 1000, 'st_ino': 40663983, 'st_mode': 33204, 'st_mtime_ns': 1792770278352916149, 'st_nlink': 1, 'st_size': 142408, 'st_uid': 1000}, 'sha256': 'acbf04054075e886aa29fe24fb26e35c857ce5c7fc6b48ef2ffe7683c229e87e'}, 'pin': {'bytes': 142408, 'declared_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/libjimage.so', 'resolved_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/libjimage.so', 'sha256': 'acbf04054075e886aa29fe24fb26e35c857ce5c7fc6b48ef2ffe7683c229e87e'}}, 'libjli': {'observed': {'bytes': 93096, 'file': {'st_ctime_ns': 1792770278353662922, 'st_dev': 66306, 'st_gid': 1000, 'st_ino': 40663984, 'st_mode': 33204, 'st_mtime_ns': 1792770278353662922, 'st_nlink': 1, 'st_size': 93096, 'st_uid': 1000}, 'sha256': '0c59fc8823cf5c8d25f12516b8ca38cab8e83b9695715775fcfdd5fea1df75f1'}, 'pin': {'bytes': 93096, 'declared_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/libjli.so', 'resolved_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/libjli.so', 'sha256': '0c59fc8823cf5c8d25f12516b8ca38cab8e83b9695715775fcfdd5fea1df75f1'}}, 'libjvm': {'observed': {'bytes': 26010448, 'file': {'st_ctime_ns': 1792770279072613632, 'st_dev': 66306, 'st_gid': 1000, 'st_ino': 40664016, 'st_mode': 33204, 'st_mtime_ns': 1792770279072613632, 'st_nlink': 1, 'st_size': 26010448, 'st_uid': 1000}, 'sha256': '53aebc862cb667bae382a429af95e06bd269b27ce3ddb0d7e39b922049156f16'}, 'pin': {'bytes': 26010448, 'declared_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/server/libjvm.so', 'resolved_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/server/libjvm.so', 'sha256': '53aebc862cb667bae382a429af95e06bd269b27ce3ddb0d7e39b922049156f16'}}, 'signer_companion_apksig-0.9.jar': {'observed': {'bytes': 489902, 'file': {'st_ctime_ns': 1791415705113294282, 'st_dev': 66306, 'st_gid': 0, 'st_ino': 108005156, 'st_mode': 33188, 'st_mtime_ns': 1741954421000000000, 'st_nlink': 1, 'st_size': 489902, 'st_uid': 0}, 'sha256': '61186f715a98cf2473544a4bbb1fae06ab84600cf2cd6adfa7ad50f4b0e2375e'}, 'pin': {'bytes': 489902, 'declared_path': '/usr/share/java/apksig.jar', 'resolved_path': '/usr/share/java/apksig-0.9.jar', 'sha256': '61186f715a98cf2473544a4bbb1fae06ab84600cf2cd6adfa7ad50f4b0e2375e'}}}
EXPECTED_TOOL_NAMES = {'aapt', 'apksigner_jar', 'java', 'java_security', 'jdk_modules', 'jdk_release', 'jvm_cfg', 'libjava', 'libjimage', 'libjli', 'libjvm', 'signer_companion_apksig-0.9.jar'}
TOOL_EVIDENCE = {'bytes': 132796, 'sha256': 'd2df2ac82742d7cbc69b43df878af8372e2df617113492e2e8ab25c69bbc0605', 'schema': 'pocket4-successor-installed-apk-audit-v1', 'kind': 'prior actual successful batch04 tool bindings; full current identity recheck required'}
RUNNER_EVIDENCE = {'bytes': 29242, 'sha256': 'faff199c1f6218b3c01d87e44be610d6fa211de396b5e8c862c188dec59d284a', 'copied_functions_unchanged': ['now', 'run_tool']}
APK_PIN = {'declared_path': '/home/alex/work/pocket4-launcher-official-candidates-20261106-zbj-tail-s41-r2/com.zhubajie.client.apk', 'resolved_path': '/home/alex/work/pocket4-launcher-official-candidates-20261106-zbj-tail-s41-r2/com.zhubajie.client.apk', 'bytes': 166873622, 'sha256': '1822af13f666fea9814a7e571d50cc7def3aad72426d2e3eaa9101dcd6eaefa0'}
APK_IDENTITY = {'st_dev': '66306', 'st_ino': '35915593', 'st_size': '166873622', 'st_mtime_ns': '1793999334433116177', 'st_ctime_ns': '1793999335020137411', 'st_uid': '1000', 'st_gid': '1000', 'st_nlink': '1', 'st_mode': '33152'}

PACKAGE = 'com.zhubajie.client'
EXPECTED_VERSION_NAME = '9.5.20'
EXPECTED_VERSION_CODE = 370
ARCHIVED_INSTALLED = {'kind': 'latest saved successful batch12 actual APK audit; fresh current observation still required before install', 'artifact': {'path': 'successor_audit_requests/actual/batches-final-r1/batch-12/artifact.original.json', 'bytes': 167063, 'sha256': '29b47ba3639c5964a6b7ee0ac802706ed6dfe4a2aa87dcfcb7e2a20bb1233709'}, 'observed_utc': '2026-11-06T20:59:54.356617+00:00', 'job_id': '1a1b2a90ea8-fc05-7f31', 'package': 'com.zhubajie.client', 'uid': 10144, 'bytes': 166858796, 'sha256': '41c143d933240c0e1482b41873991def8e769fd9bcbe414e6e6bdbbe66bfea13', 'manifest': {'long_version_code': 369, 'max_sdk': None, 'min_sdk': '26', 'native_abi_source': 'aapt2_dump_badging_current_APK', 'native_abis': ['arm64-v8a', 'armeabi-v7a'], 'package': 'com.zhubajie.client', 'package_line_raw': "package: name='com.zhubajie.client' versionCode='369' versionName='9.5.11' platformBuildVersionName='11' platformBuildVersionCode='30' compileSdkVersion='30' compileSdkVersionCodename='11'", 'split_name': None, 'target_sdk': '30', 'version_code': 369, 'version_code_major': 0, 'version_name': '9.5.11'}, 'signer_certificate_sha256': ['556246aaaf05f61c8bbb9587dfc0660e01f6c3c6813ec038d18684d3ab378bbe'], 'permission_tag_names': [{'tag': 'permission', 'name': 'com.zhubajie.client.permission.KW_SDK_BROADCAST'}, {'tag': 'uses-permission', 'name': 'com.zhubajie.client.permission.KW_SDK_BROADCAST'}, {'tag': 'uses-permission', 'name': 'android.permission.WRITE_EXTERNAL_STORAGE'}, {'tag': 'uses-permission', 'name': 'android.permission.INTERNET'}, {'tag': 'uses-permission', 'name': 'android.permission.CAMERA'}, {'tag': 'uses-permission', 'name': 'android.permission.READ_EXTERNAL_STORAGE'}, {'tag': 'uses-permission', 'name': 'android.permission.BROADCAST_STICKY'}, {'tag': 'uses-permission', 'name': 'android.permission.MODIFY_AUDIO_SETTINGS'}, {'tag': 'uses-permission', 'name': 'android.permission.VIBRATE'}, {'tag': 'uses-permission', 'name': 'android.permission.EXPAND_STATUS_BAR'}, {'tag': 'uses-permission', 'name': 'android.permission.WAKE_LOCK'}, {'tag': 'uses-permission', 'name': 'android.permission.DOWNLOAD_WITHOUT_NOTIFICATION'}, {'tag': 'uses-permission', 'name': 'android.permission.ACCESS_DOWNLOAD_MANAGER'}, {'tag': 'uses-permission', 'name': 'android.permission.REQUEST_INSTALL_PACKAGES'}, {'tag': 'uses-permission', 'name': 'android.permission.FOREGROUND_SERVICE'}, {'tag': 'uses-permission', 'name': 'com.coloros.mcs.permission.RECIEVE_MCS_MESSAGE'}, {'tag': 'uses-permission', 'name': 'com.heytap.mcs.permission.RECIEVE_MCS_MESSAGE'}, {'tag': 'uses-permission', 'name': 'com.meizu.flyme.push.permission.RECEIVE'}, {'tag': 'uses-permission', 'name': 'com.zhubajie.client.push.permission.MESSAGE'}, {'tag': 'uses-permission', 'name': 'com.meizu.c2dm.permission.RECEIVE'}, {'tag': 'uses-permission', 'name': 'com.zhubajie.client.permission.C2D_MESSAGE'}, {'tag': 'uses-permission', 'name': 'com.huawei.android.launcher.permission.CHANGE_BADGE'}, {'tag': 'uses-permission', 'name': 'android.permission.FLASHLIGHT'}, {'tag': 'uses-permission', 'name': 'android.permission.RECORD_VIDEO'}, {'tag': 'uses-permission', 'name': 'android.permission.RECORD_AUDIO'}, {'tag': 'uses-permission', 'name': 'android.permission.ACCESS_NETWORK_STATE'}, {'tag': 'permission', 'name': 'com.zhubajie.client.openadsdk.permission.TT_PANGOLIN'}, {'tag': 'uses-permission', 'name': 'com.zhubajie.client.openadsdk.permission.TT_PANGOLIN'}, {'tag': 'uses-permission', 'name': 'android.permission.INTERNET'}, {'tag': 'uses-permission', 'name': 'android.permission.SYSTEM_ALERT_WINDOW'}, {'tag': 'uses-permission', 'name': 'android.permission.ACCESS_COARSE_LOCATION'}, {'tag': 'uses-permission', 'name': 'android.permission.ACCESS_FINE_LOCATION'}, {'tag': 'uses-permission', 'name': 'com.asus.msa.SupplementaryDID.ACCESS'}, {'tag': 'uses-permission', 'name': 'android.permission.CHANGE_NETWORK_STATE'}, {'tag': 'uses-permission', 'name': 'android.permission.POST_NOTIFICATIONS'}, {'tag': 'uses-permission', 'name': 'android.permission.REORDER_TASKS'}, {'tag': 'permission', 'name': 'com.zhubajie.client.permission.MIPUSH_RECEIVE'}, {'tag': 'uses-permission', 'name': 'com.zhubajie.client.permission.MIPUSH_RECEIVE'}, {'tag': 'uses-permission', 'name': 'android.permission.MOUNT_UNMOUNT_FILESYSTEMS'}, {'tag': 'permission', 'name': 'com.zhubajie.client.permission.PROCESS_PUSH_MSG'}, {'tag': 'uses-permission', 'name': 'com.zhubajie.client.permission.PROCESS_PUSH_MSG'}, {'tag': 'uses-permission', 'name': 'android.permission.READ_MEDIA_IMAGES'}, {'tag': 'uses-permission', 'name': 'android.permission.READ_MEDIA_AUDIO'}, {'tag': 'uses-permission', 'name': 'android.permission.READ_MEDIA_VIDEO'}, {'tag': 'uses-permission', 'name': 'android.permission.SCHEDULE_EXACT_ALARM'}, {'tag': 'uses-permission', 'name': 'getui.permission.GetuiService.com.zhubajie.client'}, {'tag': 'uses-permission', 'name': 'com.vivo.notification.permission.BADGE_ICON'}, {'tag': 'permission', 'name': 'getui.permission.GetuiService.com.zhubajie.client'}, {'tag': 'uses-permission', 'name': 'com.meizu.flyme.permission.PUSH'}, {'tag': 'uses-permission', 'name': 'com.google.android.gms.permission.AD_ID'}, {'tag': 'permission', 'name': 'com.zhubajie.client.permission.PUSH_PROVIDER'}, {'tag': 'permission', 'name': 'com.zhubajie.client.permission.PUSH_WRITE_PROVIDER'}, {'tag': 'uses-permission', 'name': 'com.zhubajie.client.permission.PUSH_PROVIDER'}, {'tag': 'uses-permission', 'name': 'com.hihonor.push.permission.READ_PUSH_NOTIFICATION_INFO'}, {'tag': 'uses-permission', 'name': 'android.permission.WRITE_SETTINGS'}, {'tag': 'uses-permission', 'name': 'freemme.permission.msa'}, {'tag': 'uses-permission', 'name': 'android.permission.INTERNET'}, {'tag': 'uses-permission', 'name': 'android.permission.INTERNET'}]}
DOWNLOAD_REFERENCE = {'job_id': '1a1b2aad530-fc05-7f38', 'stdout': {'path': 'official_source_scripts/s41_zbj_finite_tail/candidate-r2/actual/stdout.original.jsonl', 'bytes': 90411, 'sha256': '87ff7fb49fe8ce2570dbba9c777fd1944c7fcc8fbdf09dc49ecd4a61e7e9cea8'}, 'terminal': {'path': 'official_source_scripts/s41_zbj_finite_tail/candidate-r2/actual/terminal.original.json', 'bytes': 733, 'sha256': '8474c03fc5a09313f1d4dfd84a2d680753d6592681562c80f2953fccad5ebf6c'}, 'source': {'path': 'official_source_scripts/s41_zbj_finite_tail/candidate-r2/continue_zbj_s41_once.py', 'bytes': 50714, 'sha256': '9b79c319611295e10d00f141b072a79d39f828549d78f9300572345375fbb2e4'}, 'actual_complete_APK': {'declared_path': '/home/alex/work/pocket4-launcher-official-candidates-20261106-zbj-tail-s41-r2/com.zhubajie.client.apk', 'resolved_path': '/home/alex/work/pocket4-launcher-official-candidates-20261106-zbj-tail-s41-r2/com.zhubajie.client.apk', 'bytes': 166873622, 'sha256': '1822af13f666fea9814a7e571d50cc7def3aad72426d2e3eaa9101dcd6eaefa0'}, 'official_url': 'https://s.shouji.qihucdn.com/261009/9b8bc092373e8f09d56861322b8ce1c9/com.zhubajie.client_370.apk?en=curpage%3Dopenbox_wap_detail%26exp%3D1794571897%26from%3Dopenbox_mintf_getAppInfoByIds%26m2%3D%26ts%3D1793967097%26tok%3Db64e944d9e3de8d16861a770d758bee5%26v%3D%26f%3Dz.apk', 'public_version_metadata': '9.5.20', 'computed_MD5': '9b8bc092373e8f09d56861322b8ce1c9', 'metadata_MD5': None, 'complete_segments': 38, 'owned_curl_joined': 38, 'old_source_FDs_closed': 46, 'signature_and_manifest_not_previously_verified': True, 'all_prior_failures_preserved': True}
FILE_INFO_REFERENCE = {'path': 'official_source_scripts/s41_zbj_finite_tail/candidate-r2/actual/candidate-file_info.original.txt', 'bytes': 497, 'sha256': '402326c44bdc61524cb5e3e9774e04cdfe903ba349c28e3a3b3523fa80a01dd0', 'original_version': '66306:35915593:166873622:1793999334433116177:1793999335020137411', 'regular_file_type_required_on_actual_FD': True, 'file_info_mode_is_permission_bits_not_independent_file_type_observation': True}
TOOL_EXECUTION_EVIDENCE = {'actual_result': {'path': 'official_source_scripts/s38_szzc_operator_signature/actual/stdout.original.json', 'bytes': 25448, 'sha256': '3ba6894d1d084f8d95b4ebfb342a3710990ce3b0aadf0e17710e9f608f8228a6'}, 'actual_terminal': {'path': 'official_source_scripts/s38_szzc_operator_signature/actual/status-1.original.txt', 'bytes': 733, 'sha256': '2974cb7304f993a0120ed8052cc6ff99837ad01e690d2c0f61f21c4d710ca904'}, 'same_12_tool_complete_identities_rechecked_before_after': True}

def need(value, code):
    if not value:
        raise RuntimeError(code)

def ident(fd):
    s = os.fstat(fd)
    return {k: str(getattr(s,k)) for k in FIELDS}

def digest_fd(fd, limit, deadline):
    size = os.fstat(fd).st_size
    need(0 < size <= limit, 'BOUNDED_FILE_SIZE')
    offset, digest = 0, hashlib.sha256()
    while offset < size:
        need(time.monotonic() < deadline, 'FULL_FILE_HASH_DEADLINE')
        block = os.pread(fd, min(1024*1024,size-offset),offset)
        need(bool(block), 'FULL_FILE_HASH_PROGRESS')
        offset += len(block); digest.update(block)
    return digest.hexdigest()

def census():
    result={}
    for name in os.listdir('/proc/self/fd'):
        try:
            fd=int(name);s=os.fstat(fd)
            result[name]=[os.readlink('/proc/self/fd/'+name),s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,
                          fcntl.fcntl(fd,fcntl.F_GETFD),fcntl.fcntl(fd,fcntl.F_GETFL)]
        except OSError as e:
            if e.errno not in (2,9):raise
    return result

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def run_tool(argv, pass_fds, receipt, end):
    """Bounded host child; retire only its own process group and keep raw output."""
    receipt.update(argv=argv, started_utc=now(), spawned=False, joined=False, timed_out=False,
                   output_capture_complete=False, automatic_retry=False, pipes_closed=False)
    proc, sel = None, selectors.DefaultSelector()
    streams, output = [], {"stdout": bytearray(), "stderr": bytearray()}
    deadline, killed = min(end, time.monotonic() + 90), False
    failure = None
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                pass_fds=tuple(pass_fds), close_fds=True, start_new_session=True, env=ENV)
        receipt.update(spawned=True, pid=proc.pid)
        streams = [proc.stdout, proc.stderr]
        for name, stream in zip(("stdout", "stderr"), streams):
            os.set_blocking(stream.fileno(), False); sel.register(stream, selectors.EVENT_READ, name)
        while sel.get_map():
            if time.monotonic() >= deadline:
                receipt["timed_out"] = True
                break
            for key, unused in sel.select(min(.2, max(0, deadline - time.monotonic()))):
                part = os.read(key.fileobj.fileno(), 65536)
                if not part:
                    sel.unregister(key.fileobj)
                    continue
                room = MAX_TOOL_OUTPUT - len(output[key.data])
                output[key.data].extend(part[:room])
                if len(part) > room:
                    receipt["output_truncated"] = True
                    raise RuntimeError("TOOL_OUTPUT_BOUND")
        if receipt["timed_out"]:
            os.killpg(proc.pid, signal.SIGKILL); killed = True
        proc.wait(timeout=5)
        receipt.update(joined=True, returncode=proc.returncode, output_capture_complete=not bool(sel.get_map()))
    except BaseException as error:
        failure = error
        receipt["error"] = {"type": type(error).__name__, "reason": str(error)[:160]}
    finally:
        try:
            if proc is not None and (proc.poll() is None or failure is not None):
                try:
                    os.killpg(proc.pid, signal.SIGKILL); killed = True
                except ProcessLookupError:
                    pass
                proc.wait(timeout=5)
            if proc is not None:
                receipt.update(joined=proc.poll() is not None, returncode=proc.returncode)
        except BaseException as error:
            receipt["retirement_error"] = {"type": type(error).__name__, "reason": str(error)[:160]}
        finally:
            for stream in streams:
                stream.close()
            sel.close()
            receipt.update(ended_utc=now(), own_group_kill_requested=killed, pipes_closed=all(x.closed for x in streams))
    return {key: bytes(value) for key, value in output.items()}

def hold_exact(name, pin, expected, held, deadline):
    path = pin['resolved_path']
    need(Path(path).is_absolute() and Path(path).resolve(strict=True).as_posix() == path,
         'EXACT_NONALIAS_INPUT_PATH:' + name)
    need(Path(pin['declared_path']).resolve(strict=True).as_posix() == path,
         'DECLARED_INPUT_ALIAS_CHANGED:' + name)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        s = os.fstat(fd); observed = ident(fd)
        need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and
             observed == {k: str(expected[k]) for k in FIELDS} and s.st_size == pin['bytes'],
             'EXACT_PREVIOUSLY_OBSERVED_FILE_IDENTITY_REQUIRED:' + name)
        need(digest_fd(fd, pin['bytes'], deadline) == pin['sha256'] and ident(fd) == observed,
             'FULL_PINNED_FILE_BYTES_CHANGED:' + name)
    except BaseException:
        os.close(fd); raise
    held.append({'name': name, 'fd': fd, 'path': path, 'declared_path': pin['declared_path'],
                 'bytes': pin['bytes'], 'sha256': pin['sha256'], 'identity': observed})
    return fd

def recheck_exact(held, deadline):
    for row in held:
        need(ident(row['fd']) == row['identity'] and
             digest_fd(row['fd'], row['bytes'], deadline) == row['sha256'],
             'HELD_INPUT_CHANGED:' + row['name'])
        fresh = os.open(row['path'], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            need(ident(fresh) == row['identity'] and
                 Path(row['path']).resolve(strict=True).as_posix() == row['path'] and
                 Path(row['declared_path']).resolve(strict=True).as_posix() == row['path'],
                 'INPUT_PATH_REPLACED:' + row['name'])
        finally:
            os.close(fresh)

def badging_manifest(raw):
    text = raw.decode("utf-8", "strict")
    lines = [line for line in text.splitlines() if line.startswith("package: ")]
    need(len(lines) == 1, "UNIQUE_AAPT_PACKAGE_LINE")
    attrs, at = {}, len("package:")
    while at < len(lines[0]):
        match = re.match(r"\s+([A-Za-z][A-Za-z0-9_-]*)='([^']*)'", lines[0][at:])
        need(match is not None and match[1] not in attrs, "BADGING_ATTRIBUTE_UNPARSED_OR_DUPLICATE")
        attrs[match[1]] = match[2]
        at += match.end()
    need("name" in attrs and attrs.get("versionCode", "").isdigit(), "AAPT_PACKAGE_VERSION_REQUIRED")
    value = {"package": attrs["name"], "version_code": int(attrs["versionCode"]), "version_name": attrs.get("versionName"),
             "split_name": attrs.get("split"), "package_line_raw": lines[0]}
    for name, prefix in (("min_sdk", "sdkVersion:"), ("target_sdk", "targetSdkVersion:"), ("max_sdk", "maxSdkVersion:")):
        found = [line for line in text.splitlines() if line.startswith(prefix)]
        need(len(found) <= 1, "AMBIGUOUS_AAPT_SDK")
        value[name] = re.findall(r"'([^']*)'", found[0])[0] if found and re.findall(r"'([^']*)'", found[0]) else None
    native = [line for line in text.splitlines() if line.startswith("native-code:")]
    need(len(native) <= 1, "AMBIGUOUS_AAPT_ABI")
    value["native_abis"] = re.findall(r"'([^']*)'", native[0]) if native else []
    value["native_abi_source"] = "aapt_dump_badging_current_APK"
    value["version_code_major"] = int(attrs.get("versionCodeMajor", "0"))
    value["long_version_code"] = value["version_code"] | (value["version_code_major"] << 32)
    return value

def parse_signature(raw, command):
    text = raw.decode("utf-8", "strict")
    certs = re.findall(r"^Signer #\d+ certificate SHA-256 digest: ([0-9a-fA-F]{64})$", text, re.M)
    certs = sorted(value.lower() for value in certs)
    verified = bool(command.get("returncode") == 0 and command.get("joined") and command.get("output_capture_complete") and not command.get("timed_out") and certs and len(certs) == len(set(certs)))
    schemes = {match[1]: match[2] == "true" for match in re.finditer(r"^Verified using (.*): (true|false)$", text, re.M)}
    return {"cryptographic_verification_performed": True, "verified": verified,
            "signer_certificate_sha256": certs, "schemes": schemes,
            "API_minimum_override_used": False, "integrity_check_bypassed": False}

def quoted_attributes(value):
    attributes, at = {}, 0
    while at < len(value):
        match = re.match(r"\s*([A-Za-z][A-Za-z0-9_:-]*)='([^']*)'(?:\s+|$)", value[at:])
        need(match is not None and match[1] not in attributes, 'UNPARSED_OR_DUPLICATE_PERMISSION_ATTRIBUTE')
        attributes[match[1]] = match[2]
        at += match.end()
    return attributes

def permissions_dump(raw):
    """Decode recognized aapt permission rows without discarding duplicates or raw attributes."""
    text = raw.decode('utf-8', 'strict')
    lines = text.splitlines()
    need(len(lines) <= 4096, 'PERMISSIONS_LINE_COUNT_BOUND')
    packages, entries, unparsed = [], [], []
    tags = {'uses-permission', 'uses-permission-sdk-23', 'uses-permission-sdk-m',
            'permission', 'permission-group', 'permission-tree'}
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        if line.startswith('package: '):
            value = line[len('package: '):]
            if value.startswith("name='"):
                attributes = quoted_attributes(value)
                packages.append({'name': attributes.get('name'), 'attributes': attributes, 'raw': line})
            else:
                need(value and not any(character.isspace() for character in value) and
                     "'" not in value and '"' not in value, 'UNPARSED_PERMISSION_PACKAGE')
                packages.append({'name': value, 'attributes': {}, 'raw': line})
            continue
        tag, separator, value = line.partition(': ')
        if separator and tag in tags:
            entry = {'tag': tag, 'name': None, 'attributes': {}, 'raw_line': line, 'line_number': number}
            try:
                if value.startswith("name='"):
                    entry['attributes'] = quoted_attributes(value)
                    entry['name'] = entry['attributes'].get('name')
                else:
                    need(value and not any(character.isspace() for character in value) and
                         "'" not in value and '"' not in value, 'UNPARSED_BARE_PERMISSION_NAME')
                    entry['name'] = value
                    entry['name_form'] = 'bare_aapt_name'
                need(isinstance(entry['name'], str) and 0 < len(entry['name']) <= 1024,
                     'EMPTY_OR_UNBOUNDED_PERMISSION_NAME')
            except (RuntimeError, UnicodeError, ValueError) as error:
                entry['decode_error'] = {'type': type(error).__name__, 'reason': str(error)}
            entries.append(entry)
            need(len(entries) <= 2048, 'PERMISSION_ENTRY_BOUND')
        else:
            unparsed.append({'line_number': number, 'raw_line': line})
    need(len(packages) == 1 and packages[0]['name'] == PACKAGE, 'UNIQUE_CANDIDATE_PERMISSION_PACKAGE')
    return {'package': packages[0]['name'], 'package_row': packages[0], 'entries': entries,
        'entry_count': len(entries), 'duplicates_preserved': True, 'unparsed_lines': unparsed,
        'all_names_decoded': all(row['name'] is not None and 'decode_error' not in row for row in entries),
        'declared_manifest_only': True, 'effective_permission_grants': 'UNKNOWN_NOT_QUERIED',
        'permission_coverage': 'aapt_dump_permissions_recognized_rows; raw output is authoritative'}

def aapt_diagnostics(kind, raw, stderr):
    """Nonempty stderr or an unrecognized stdout line prevents a healthy-parser claim."""
    text = raw.decode('utf-8', 'strict')
    diagnostic = []
    for number, line in enumerate(text.splitlines(), 1):
        if re.match(r'^\s*(?:[EWFDI]/|(?:warning|warn|error|fatal|exception|note)\b|ResourceType\b)', line, re.I):
            diagnostic.append({'line_number': number, 'raw_line': line})
    unexpected = []
    if kind == 'badging':
        allowed = {
            'package', 'sdkVersion', 'targetSdkVersion', 'maxSdkVersion', 'application',
            'application-debuggable', 'application-testOnly', 'launchable-activity', 'leanback-launchable-activity',
            'uses-permission', 'uses-permission-sdk-23', 'uses-permission-sdk-m', 'uses-implied-permission',
            'permission', 'permission-group', 'permission-tree', 'uses-feature', 'uses-feature-not-required',
            'uses-implied-feature', 'uses-gl-es', 'uses-library', 'uses-library-not-required',
            'uses-static-library', 'uses-sdk-library', 'provides-library', 'uses-package',
            'feature-group', 'uses-configuration', 'supports-screens', 'compatible-screens',
            'supports-any-density', 'supports-input', 'locales', 'densities', 'native-code',
            'alt-native-code', 'other-activities', 'other-receivers', 'other-services',
        }
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            key = line.split(':', 1)[0]
            if key not in allowed and not re.fullmatch(r'application-(?:label|icon)(?:-[A-Za-z0-9_-]+)?', key):
                unexpected.append({'line_number': number, 'raw_line': line})
    return {'stderr_nonempty': bool(stderr), 'stdout_diagnostic_lines': diagnostic,
            'unrecognized_badging_lines': unexpected,
            'healthy_output_shape': not stderr and not diagnostic and not unexpected,
            'stderr_and_diagnostic_rows_never_removed': True}

def normal_child_retired(command):
    return (type(command.get('returncode')) is int and command.get('joined') is True and
        command.get('pipes_closed') is True and command.get('output_capture_complete') is True and
        command.get('timed_out') is False and command.get('own_group_kill_requested') is False and
        not command.get('error') and not command.get('retirement_error') and not command.get('output_truncated'))

def feature_group_diagnostics(original, kind, raw, stderr):
    result = original(kind, raw, stderr)
    accepted = []
    if kind == 'badging':
        lines = raw.decode('utf-8', 'strict').splitlines()
        group_line = None
        group_has_feature = False
        main_seen = False
        for number, line in enumerate(lines, 1):
            if re.fullmatch(r"feature-group: label='[^'\r\n]*'", line):
                group_line = number
                group_has_feature = False
                continue
            feature = re.fullmatch(
                r"  (uses-feature|uses-feature-not-required): name='([A-Za-z_][A-Za-z0-9_.]*)'", line)
            implied = re.fullmatch(
                r"  uses-implied-feature: name='([A-Za-z_][A-Za-z0-9_.]*)' reason='([^'\r\n]+)'", line)
            if group_line is not None and (feature or implied):
                row = {'line_number': number, 'raw_line': line, 'feature_group_line': group_line}
                if feature:
                    row.update(tag=feature[1], name=feature[2])
                else:
                    row.update(tag='uses-implied-feature', name=implied[1], reason=implied[2])
                accepted.append(row)
                group_has_feature = True
                continue
            if line == 'main' and group_line is not None and group_has_feature and not main_seen:
                accepted.append({'line_number': number, 'raw_line': line,
                    'tag': 'legacy_bare_main_marker', 'feature_group_line': group_line,
                    'launchable_component_inferred': False})
                main_seen = True
            # Whitespace, malformed rows and any other token end this contiguous
            # block. Their original unrecognized/diagnostic entries remain.
            group_line = None
            group_has_feature = False
        accepted_keys = {(row['line_number'], row['raw_line']) for row in accepted}
        result['unrecognized_badging_lines'] = [row for row in result['unrecognized_badging_lines']
            if (row['line_number'], row['raw_line']) not in accepted_keys]
    result['recognized_feature_group_extension_rows'] = accepted
    result['healthy_output_shape'] = (not result['stderr_nonempty'] and
        not result['stdout_diagnostic_lines'] and not result['unrecognized_badging_lines'])
    result['raw_lines_preserved'] = True
    result['parser_itself_executes_no_commands'] = True
    return result

def save(name, body):
    need(name in ('apksigner.stdout', 'apksigner.stderr', 'badging.stdout', 'badging.stderr',
                  'permissions.stdout', 'permissions.stderr', 'result.json'), 'CLOSED_EVIDENCE_NAME')
    with (ROOT / name).open('xb') as stream:
        stream.write(body); stream.flush(); os.fsync(stream.fileno())
    return {'path': str(ROOT / name), 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}


def qualify_vendor_signature(signature):
    need(signature['cryptographic_verification_performed'] is True and
         signature['verified'] is True and signature['API_minimum_override_used'] is False and
         signature['integrity_check_bypassed'] is False, 'NORMAL_FULL_SIGNATURE_REQUIRED')
    need(signature['signer_certificate_sha256'] == [SAVED_PM_SIGNER],
         'VALID_SIGNATURE_WITH_DIFFERENT_VENDOR_IS_NOT_AN_UPDATE')
    schemes = signature['schemes']
    need(schemes.get('v2 scheme (APK Signature Scheme v2)') is True or
         schemes.get('v3 scheme (APK Signature Scheme v3)') is True,
         'WHOLE_APK_V2_OR_V3_VERIFICATION_REQUIRED')


def observe_command(kind, argv, af, result, deadline):
    command = {'name': kind, 'purpose': 'read only the exact held complete S41 APK',
               'execution_uid': 1000}
    result['commands'].append(command)
    remaining = deadline - time.monotonic()
    command['remaining_budget_before_spawn_seconds'] = remaining
    command['minimum_budget_before_spawn_seconds'] = 5
    need(remaining > 5, 'VERIFICATION_DEADLINE_BEFORE_SPAWN:' + kind)
    outputs = run_tool(argv, (af,), command, deadline)
    for stream, raw in outputs.items():
        command[stream] = save(kind + '.' + stream, raw)
        if len(raw) <= 32768:
            try:
                command[stream + '_original_utf8'] = raw.decode('utf-8', 'strict')
            except UnicodeError as error:
                command[stream + '_decode_error'] = str(error)
        else:
            command[stream + '_original_inline_state'] = 'FULL_RAW_FILE_SAVED; exceeds_inline_32768B'
    need(normal_child_retired(command), 'COMPLETE_NORMAL_CHILD_RETIREMENT_REQUIRED:' + kind)
    return command, outputs


def main():
    need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 1000 and
         sys.argv[1:] == ['--verify-complete-zbj-as-existing-owner-once'],
         'EXACT_UNPRIVILEGED_EXISTING_TOOL_OWNER_ENTRY')
    need(ROOT.parent.resolve() == ROOT.parent, 'FIXED_PRIVATE_PARENT')
    os.umask(0o077); before = census(); ROOT.mkdir(mode=0o700)
    held, deadline = [], time.monotonic() + 170
    result = {'schema': 'pocket4-zbj-complete-operator-verification-v1', 'ok': False, 'errors': [],
        'actual_uid': os.getuid(), 'actual_euid': os.geteuid(), 'root_execution': False,
        'Android_commands': 0, 'Main_actions': 0, 'installs': 0, 'UI_actions': 0, 'permission_changes': 0,
        'automatic_retry': False, 'production_ready': False, 'cleanup_eligible': False,
        'root_private_dependency_files_opened': False, 'old_files_modified_or_deleted': False,
        'candidate_signature_verified': False, 'candidate_manifest_verified': False,
        'candidate_permission_dump_verified': False, 'vendor_signer_matches_archived_installed_APK': False,
        'candidate_qualified_for_fresh_install_review': False, 'installable_without_fresh_scope': False,
        'commands': [], 'tool_identity_basis': TOOL_EVIDENCE,
        'prior_actual_tool_execution_basis': TOOL_EXECUTION_EVIDENCE,
        'runner_source_basis': RUNNER_EVIDENCE, 'download_reference': DOWNLOAD_REFERENCE,
        'candidate_file_info_reference': FILE_INFO_REFERENCE,
        'latest_archived_installed_APK_reference': ARCHIVED_INSTALLED,
        'archived_installed_reference_is_fresh_at_this_verification': False,
        'signature_integrity_checks_changed': False, 'API_minimum_override_used': False,
        'effective_permission_grants': 'UNKNOWN_NOT_QUERIED',
        'candidate_runtime_compatibility': 'UNKNOWN_NOT_EXECUTED',
        'original_S39_failure_reclassified': False, 'earlier_download_failures_reclassified': False,
        'update_eligibility': 'PENDING_THIS_VERIFICATION_AND_FRESH_CURRENT_SCOPE_RUNTIME_COMPATIBILITY'}
    try:
        need(len(TOOL_BINDINGS) == 12 and set(TOOL_BINDINGS) == EXPECTED_TOOL_NAMES,
             'EXACT_PRIOR_TWELVE_TOOL_INPUTS')
        for name, row in TOOL_BINDINGS.items():
            hold_exact(name, row['pin'], row['observed']['file'], held, deadline)
        af = hold_exact('complete_s41_APK', APK_PIN, APK_IDENTITY, held, deadline)
        result['candidate'] = {key: value for key, value in held[-1].items() if key != 'fd'}
        recheck_exact(held, deadline)
        argv = [TOOL_BINDINGS['java']['pin']['resolved_path'], '-Xmx256m', '-jar',
                TOOL_BINDINGS['apksigner_jar']['pin']['resolved_path'], 'verify', '--verbose',
                '--print-certs', '/proc/self/fd/' + str(af)]
        command, outputs = observe_command('apksigner', argv, af, result, deadline)
        signature = parse_signature(outputs['stdout'], command)
        result['candidate_signature_observation'] = signature
        result['signature_stderr_nonempty'] = bool(outputs['stderr'])
        result['signature_warning_lines'] = [line for line in outputs['stdout'].decode('utf-8', 'strict').splitlines()
                                             if re.match(r'^\s*(?:WARNING|WARN)\b', line, re.I)]
        result['signature_warning_and_stderr_bytes_preserved'] = True
        qualify_vendor_signature(signature)
        result['candidate_signature_verified'] = True
        result['vendor_signer_matches_archived_installed_APK'] = True
        command_health = []
        for kind in ('badging', 'permissions'):
            recheck_exact(held, deadline)
            argv = [TOOL_BINDINGS['aapt']['pin']['resolved_path'], 'dump', kind, '/proc/self/fd/' + str(af)]
            command, outputs = observe_command(kind, argv, af, result, deadline)
            health = {'name': kind, 'normal_exit_zero': command['returncode'] == 0,
                      'parsed': False, 'healthy': False, 'parse_errors': []}
            try:
                health['diagnostics'] = feature_group_diagnostics(
                    aapt_diagnostics, kind, outputs['stdout'], outputs['stderr'])
                if kind == 'badging':
                    manifest = badging_manifest(outputs['stdout'])
                    manifest['native_abi_source'] = 'aapt_dump_badging_exact_complete_S41_candidate_APK'
                    result['candidate_manifest_observation'] = manifest
                    need(manifest['package'] == PACKAGE and manifest['split_name'] is None and
                         manifest['version_name'] == EXPECTED_VERSION_NAME and
                         manifest['long_version_code'] == EXPECTED_VERSION_CODE and
                         manifest['long_version_code'] > ARCHIVED_INSTALLED['manifest']['long_version_code'] and
                         all(isinstance(manifest[key], str) and manifest[key].isdigit() and int(manifest[key]) > 0
                             for key in ('min_sdk', 'target_sdk')), 'EXACT_CANDIDATE_PACKAGE_VERSION_SDK_FIELDS')
                    need(manifest['max_sdk'] is None or (manifest['max_sdk'].isdigit() and
                         int(manifest['max_sdk']) >= int(manifest['min_sdk'])), 'CANDIDATE_MAX_SDK_INCONSISTENT')
                    need(len(manifest['native_abis']) == len(set(manifest['native_abis'])),
                         'CANDIDATE_ABI_ROWS_DUPLICATED')
                    health['parsed'] = True
                else:
                    permissions = permissions_dump(outputs['stdout'])
                    result['candidate_declared_permissions_observation'] = permissions
                    need(permissions['all_names_decoded'] is True and not permissions['unparsed_lines'],
                         'COMPLETE_RECOGNIZED_DECLARED_PERMISSION_ROWS_REQUIRED')
                    health['parsed'] = True
                health['healthy'] = health['normal_exit_zero'] and health['parsed'] and health['diagnostics']['healthy_output_shape']
            except (RuntimeError, UnicodeError, ValueError, IndexError) as error:
                health['parse_errors'].append({'type': type(error).__name__, 'reason': str(error)[:512]})
            command_health.append(health)
        result['command_parser_health'] = command_health
        result['all_raw_command_observations_complete'] = len(result['commands']) == 3
        if 'candidate_manifest_observation' in result:
            candidate = result['candidate_manifest_observation']
            fields = ('package', 'version_code', 'version_code_major', 'long_version_code', 'version_name',
                      'min_sdk', 'target_sdk', 'max_sdk', 'native_abis')
            result['archived_installed_comparison'] = {
                'scope': 'latest saved batch12 actual APK audit; no new Android observation',
                'candidate_bytes_equal_archived_APK': APK_PIN['bytes'] == ARCHIVED_INSTALLED['bytes'],
                'candidate_sha256_equal_archived_APK': APK_PIN['sha256'] == ARCHIVED_INSTALLED['sha256'],
                'field_equality': {key: candidate.get(key) == ARCHIVED_INSTALLED['manifest'].get(key) for key in fields},
                'candidate_minus_archived_long_version_code': candidate['long_version_code'] - ARCHIVED_INSTALLED['manifest']['long_version_code'],
                'SDK_and_ABI_equality_does_not_prove_runtime_compatibility': True}
            if 'candidate_declared_permissions_observation' in result:
                entries = result['candidate_declared_permissions_observation']['entries']
                result['archived_installed_comparison']['permission_tag_and_name_sequence_equal'] = (
                    [{'tag': row['tag'], 'name': row['name']} for row in entries] == ARCHIVED_INSTALLED['permission_tag_names'])
                result['archived_installed_comparison']['permission_attribute_equivalence'] = 'NOT_CLAIMED_DIFFERENT_DUMP_FORMATS'
        recheck_exact(held, deadline)
        result['all_held_files_full_identity_and_hash_unchanged'] = True
        result['held_input_bindings'] = [{key: value for key, value in row.items() if key != 'fd'} for row in held]
        result['candidate_manifest_verified'] = command_health[0]['healthy']
        result['candidate_permission_dump_verified'] = command_health[1]['healthy']
        result['ok'] = all(row['healthy'] for row in command_health)
        if not result['ok']:
            result['errors'].append({'type': 'AaptObservationIncomplete',
                                    'reason': 'nonzero return, diagnostic bytes, unrecognized output or parse failure; raw evidence preserved'})
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:512]})
    finally:
        close_errors = []
        for row in reversed(held):
            try:
                os.close(row['fd'])
            except OSError as error:
                close_errors.append({'name': row['name'], 'errno': error.errno})
        result['held_files'] = {'acquired': len(held), 'closed': len(held) - len(close_errors), 'errors': close_errors}
        if close_errors:
            result['ok'] = False
    result['original_descriptor_identities_restored'] = census() == before
    result['ok'] = (result['ok'] and not result['errors'] and result['original_descriptor_identities_restored'] and
                    result['held_files'] == {'acquired': 13, 'closed': 13, 'errors': []} and
                    len(result['commands']) == 3 and all(normal_child_retired(x) for x in result['commands']) and
                    result['candidate_signature_verified'] and result['candidate_manifest_verified'] and
                    result['candidate_permission_dump_verified'] and result['vendor_signer_matches_archived_installed_APK'])
    result['candidate_qualified_for_fresh_install_review'] = result['ok']
    result['status'] = 'COMPLETE_CANDIDATE_VERIFIED_PENDING_FRESH_INSTALL_REVIEW' if result['ok'] else 'COMPLETE_CANDIDATE_VERIFICATION_FAILED'
    if result['ok']:
        result['update_eligibility'] = 'HOST_CANDIDATE_QUALIFIED; FRESH_CURRENT_SCOPE_AND_RUNTIME_COMPATIBILITY_STILL_REQUIRED'
    raw = (json.dumps(result, sort_keys=True) + '\n').encode()
    save('result.json', raw)
    need(census() == before, 'FINAL_OUTPUT_PUBLICATION_DESCRIPTOR_SET_CHANGED')
    print(raw.decode(), end='', flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
