"""Restricted same-process APIs for the original Editor03/Probe03 cases.

The exact final consumer backend is a private module instance. All actual host
children pass through the caller's fresh ScopeBinding, RecorderBridge and
PhaseCommands. The case retains its one action-lock OFD. No Android/UI call is
made by import, and no historical activation, Session, Flow or scope is loaded.
"""
import base64
import hashlib
import json
import re
import subprocess
import types
import weakref
from pathlib import Path

APP = {'path': '/usr/local/bin/android-app', 'bytes': 37467,
       'sha256': '4823c1a6d2434a9d102b2b6dbc369dd0cf192e7fc0a31384a68dddb370d0a340'}
BACKEND = {'path': '/usr/local/libexec/android-digitalis-observe-helper', 'bytes': 36404,
           'sha256': '76e9875d141f69976cbbafe469aa13439cf99c3214bc479a0c80cda740c8dcfa'}
RUNNER = 'local.pocket4.actions.v2/.ActionRunner'
PNG_BOUND = 33554432
METADATA_BOUND = 16777216
BASE64_BOUND = ((PNG_BOUND + 2) // 3) * 4
IMAGE_ENVELOPE_BOUND = BASE64_BOUND + METADATA_BOUND


def mutation(request):
    return request.get('op') in ('click', 'set-text', 'snapshot-tap', 'scroll-forward', 'scroll-backward')


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


class ReadinessCalls:
    def __init__(self, facade):
        self.facade = facade
    def __getattr__(self, name):
        return getattr(subprocess, name)
    def run(self, argv, **options):
        f = self.facade
        f.need(f.active is not None and argv == ['/usr/bin/droidloomctl', 'readiness', '--json']
            and options == {'stdout': subprocess.PIPE, 'stderr': subprocess.PIPE, 'timeout': 8,
                            'env': f.runtime.scope_module.HOST_ENV, 'check': True},
            'ONLY_ORIGINAL_READONLY_BACKEND_DISCOVERY')
        return f.runtime.ui_readiness(argv, options, f.active)


class OriginalAPIs:
    def __init__(self, runtime):
        self.runtime = runtime; self.c = runtime.c; self.need = self.c.need
        self.active = None; self.action_used = False; self.frames = {}; self.closed = False
        self.ui_stack = []; self.foreground_callback = None; self.package_callback = None
        runtime.verify_final_consumers(APP, BACKEND)
        self.module = self.c.module(BACKEND, 'final_system_case_private_consumer_backend')
        self.real_ui = self.module.ui; self.real_capture = self.module.capture
        self.real_dispatch = self.module.dispatch; self.real_foreground = self.module.foreground
        self.real_package_name = self.module.package_name
        self.real_discover = self.module.discover
        self.module.arun = self._android
        self.module.subprocess = ReadinessCalls(self)
        self.module.ui = self._native_ui
        self.module.capture = self._capture
        self.module.foreground = self._foreground
        self.module.package_name = self._package_name
        self.module.discover = self._discover
        self.need(self.module.MAX_PNG == PNG_BOUND, 'ORIGINAL_BACKEND_PNG_LIMIT_CHANGED')

    def _guard(self, attempted=False):
        self.runtime.ui_guard(action_attempted=attempted)

    def _call(self, api, request, invoke):
        self.need(not self.closed and self.active is None and type(request) is dict, 'NO_REENTRANT_CLOSED_OR_UNTYPED_ORIGINAL_API')
        request_copy = self.c.parse(json_bytes(request))
        self.need(len(json_bytes(request_copy)) <= 65536, 'ORIGINAL_UI_REQUEST_BOUND')
        context = self.runtime.begin_ui_api(api, request_copy)
        self.active = context; self.action_used = False
        value = None; first = None
        try:
            self._guard()
            value = invoke(request_copy)
            self._guard(attempted=self.action_used)
            if api != 'capture':
                self._validate_return(api, value)
            return value
        except BaseException as error:
            first = error
            raise
        finally:
            try:
                self.runtime.finish_ui_api(context, api, request_copy, value, first,
                                           action_attempted=self.action_used)
            except BaseException as evidence_error:
                if first is not None:
                    first.add_note('SYSTEM_UI_RESULT_EVIDENCE:' + type(evidence_error).__name__)
                else:
                    raise
            finally:
                self.active = None; self.action_used = False

    def _validate_return(self, api, value):
        self.need(type(value) is dict, 'ORIGINAL_API_OBJECT_REQUIRED')
        if api == 'capture':
            self.need(set(value) == {'meta', 'image'} and type(value['meta']) is dict,
                      'EXACT_ORIGINAL_CAPTURE_API_REQUIRED')
            image = value['image']; meta = value['meta']
            self.need(image.mode == 'RGB' and 0 < image.width <= 8192 and 0 < image.height <= 8192
                and image.width * image.height <= 32000000
                and meta['scope_sha256'] == self.module.image_sha(image)
                and len(json_bytes(meta)) <= METADATA_BOUND, 'ORIGINAL_CAPTURE_PIXEL_AND_METADATA_BOUNDS')
            self.frames = {key: row for key, row in self.frames.items() if row['image']() is not None}
            self.frames[id(value)] = {'image': weakref.ref(image), 'meta_sha256': self.c.sha(json_bytes(meta))}
            return
        encoded = value.get('screenshot_png_base64')
        if encoded is not None:
            self.need(api == 'dispatch' and self.active['request']['op'] == 'observe'
                and type(encoded) is str and 0 < len(encoded) <= BASE64_BOUND and encoded.isascii(),
                'ONLY_ORIGINAL_OBSERVE_HAS_BOUNDED_PNG')
            data = base64.b64decode(encoded, validate=True)
            self.need(0 < len(data) <= PNG_BOUND and data.startswith(b'\x89PNG\r\n\x1a\n'),
                      'ORIGINAL_OBSERVATION_PNG_BOUND')
            body = dict(value); body.pop('screenshot_png_base64')
            # The wire metadata includes the original field name, colon and
            # quotes; compute it from the exact canonical encoding with an empty
            # base64 value, independently of the PNG payload budget.
            body['screenshot_png_base64'] = ''
            metadata = len(json_bytes(body))
            self.need(metadata <= METADATA_BOUND and metadata + len(encoded) <= IMAGE_ENVELOPE_BOUND,
                      'ORIGINAL_OBSERVATION_METADATA_AND_ENCODED_BOUNDS')
        else:
            self.need(len(json_bytes(value)) <= METADATA_BOUND, 'ORIGINAL_NATIVE_JSON_BOUND')

    def capture(self, request):
        return self._call('capture', request, self._capture)

    def dispatch(self, request):
        return self._call('dispatch', request, self.real_dispatch)

    @property
    def ui(self):
        return self.module.ui

    @ui.setter
    def ui(self, callback):
        previous = self.module.ui
        if self.ui_stack and callback is self.ui_stack[-1]:
            self.ui_stack.pop(); self.module.ui = callback
            return
        self.need(callable(callback) and self.active is None, 'NATIVE_OBSERVER_MUST_BE_BOUND_BEFORE_DISPATCH')
        self.runtime.verify_original_callback('native_observer', callback, previous)
        self.ui_stack.append(previous); self.module.ui = callback

    @property
    def foreground(self):
        return self._foreground

    @foreground.setter
    def foreground(self, callback):
        self.need(self.foreground_callback is None and callable(callback), 'ONE_ORIGINAL_OWNED_FOREGROUND_BINDING')
        self.runtime.verify_original_callback('foreground', callback, None)
        self.foreground_callback = callback

    @property
    def package_name(self):
        return self.real_package_name

    @package_name.setter
    def package_name(self, callback):
        self.need(self.package_callback is None and callable(callback), 'ONE_ORIGINAL_PACKAGE_VALIDATOR_BINDING')
        self.runtime.verify_original_callback('package_name', callback, None)
        self.package_callback = callback

    def _package_name(self, package):
        self.need(package in self.runtime.allowed_ui_packages, 'ORIGINAL_CASE_PACKAGE_ALLOWLIST')
        return self.package_callback(package) if self.package_callback else self.real_package_name(package)

    def _foreground(self):
        self.need(self.active is not None and self.foreground_callback is not None,
                  'ORIGINAL_API_NEEDS_OWNED_FOREGROUND_CALLBACK')
        value = self.foreground_callback()
        self.runtime.validate_ui_foreground(value, self.active)
        return value

    def _discover(self):
        self._guard(); init, env, status = self.real_discover()
        actual = self.runtime.baseline.docs['final_baseline']
        self.need(init == actual['init_host_pid'] and status['host_pid'] == actual['daemon_status']['host_pid']
            and env == actual['android_env'], 'ACTUAL_DISCOVERY_NOT_THIS_FRESH_MAIN')
        self._guard()
        return init, env, status

    def _capture(self, request):
        self.need(self.active is not None, 'CAPTURE_REQUIRES_CURRENT_TYPED_API')
        self.runtime.validate_internal_capture(request, self.active)
        value = self.real_capture(request)
        self._validate_return('capture', value)
        return value

    def _native_ui(self, request):
        if self.active is None:
            return self._call('ui', request, self._native_ui)
        self.runtime.validate_native_request(request, self.active, self.action_used)
        if mutation(request):
            self._foreground()
        self._guard()
        value = self.real_ui(request)
        # Record the untouched native return before the original dispatch can
        # attach a later screenshot result. Original observer callbacks receive
        # this same Python value; no ACK is reconstructed from final output.
        self.runtime.record_native_return(request, value, self.active)
        return value

    def _android(self, argv, timeout=30):
        self.need(self.active is not None, 'NO_ANDROID_CALL_OUTSIDE_TYPED_ORIGINAL_API')
        is_mutation, image = self.runtime.admit_ui_android(list(argv), timeout, self.active, self.action_used)
        if is_mutation:
            self._foreground()
            self.need(not self.action_used, 'ONE_ORIGINAL_API_MUTATION_NO_REPLAY')
            self.action_used = True
        return self.runtime.ui_android(list(argv), timeout, self.active,
                                       mutation=is_mutation, image=image)

    def validate_snapshot(self, request, frame):
        self.need(not self.closed, 'ORIGINAL_SNAPSHOT_API_CLOSED')
        self._guard()
        known = self.frames.get(id(frame))
        self.need(known is not None and known['image']() is frame.get('image')
            and known['meta_sha256'] == self.c.sha(json_bytes(frame.get('meta'))),
            'SNAPSHOT_VALIDATION_REQUIRES_THIS_REAL_CAPTURE')
        self.runtime.validate_snapshot_request(request, frame)
        return self.module.validate_snapshot(request, frame)

    def window_state(self, package, token, display, mode):
        request = {'package': package, 'window_token': token, 'display': display, 'accessibility_mode': mode}
        return self._call('window_state', request,
            lambda r: self.module.window_state(r['package'], r['window_token'], r['display'], r['accessibility_mode']))

    def stable_window(self, value):
        self.runtime.original_caller(['search_driver.py'], {'back'})
        self.need(not self.closed and type(value) is dict, 'ORIGINAL_EDITOR_WINDOW_SHAPE_REQUIRED')
        return self.module.stable_window(value)

    def close(self):
        self.need(self.active is None and not self.ui_stack, 'NATIVE_API_OR_OBSERVER_STILL_ACTIVE')
        self.frames.clear()
        try:
            self.runtime.verify_final_consumers(APP, BACKEND)
        finally:
            self.closed = True
