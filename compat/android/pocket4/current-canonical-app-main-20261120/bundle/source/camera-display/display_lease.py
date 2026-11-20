#!/usr/bin/env python3
"""One bounded normal desktop display lease for the fixed built-in UVC device.

The caller owns this process. This module never opens a video node, changes a
power preference, unlocks the desktop, resets USB, or starts an Android unit.
"""
import os
from pathlib import Path
import stat
import time

BUS = 'unix:path=/run/user/1000/bus'
DEVICE = Path('/dev/v4l/by-id/usb-SunplusIT_Inc_Integrated_Camera_JX20250923V2-video-index0')
USB = Path('/sys/bus/usb/devices/3-4')
SERVICES = {
    'session': ('org.gnome.SessionManager', '/org/gnome/SessionManager'),
    'display': ('org.gnome.Mutter.DisplayConfig', '/org/gnome/Mutter/DisplayConfig'),
    'screen': ('org.gnome.ScreenSaver', '/org/gnome/ScreenSaver'),
    'idle': ('org.gnome.Mutter.IdleMonitor', '/org/gnome/Mutter/IdleMonitor/Core'),
}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def physical_identity():
    named = DEVICE.lstat()
    require(stat.S_ISLNK(named.st_mode), 'fixed camera by-id is not a symlink')
    target = DEVICE.resolve(strict=True)
    require(target.parent == Path('/dev') and target.name.startswith('video') and
            target.name[5:].isdecimal(), 'fixed camera target is not a video node')
    node = target.stat()
    require(stat.S_ISCHR(node.st_mode), 'fixed camera target is not a character device')
    usb = USB.resolve(strict=True)
    sys_video = (Path('/sys/class/video4linux') / target.name / 'device').resolve(strict=True)
    require(sys_video.is_relative_to(usb), 'video node is not on built-in USB port 3-4')
    attributes = {key: (USB / key).read_text().strip()
                  for key in ('idVendor', 'idProduct', 'serial', 'devnum')}
    require((attributes['idVendor'], attributes['idProduct'], attributes['serial']) ==
            ('1e08', '5520', 'JX20250923V2'), 'built-in Sunplus USB identity differs')
    return {'by_id': str(DEVICE), 'target': str(target), 'device': node.st_dev,
            'inode': node.st_ino, 'rdev': node.st_rdev, 'symlink_inode': named.st_ino,
            'usb_path': str(usb), 'video_sysfs': str(sys_video), 'usb': attributes}


class DesktopBus:
    def __init__(self):
        require(os.geteuid() == os.getuid() == 1000, 'display lease requires normal alex')
        from gi.repository import Gio, GLib
        self.Gio, self.GLib = Gio, GLib
        self.connection = Gio.DBusConnection.new_for_address_sync(
            BUS, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT |
            Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)
        self.connection.set_exit_on_close(False)
        self.unique_name = self.connection.get_unique_name()
        self.owners = {}
        try:
            for key, (name, path) in SERVICES.items():
                owner = self.call_raw('org.freedesktop.DBus', '/org/freedesktop/DBus',
                                      'org.freedesktop.DBus', 'GetNameOwner', '(s)', (name,))[0]
                uid = self.call_raw('org.freedesktop.DBus', '/org/freedesktop/DBus',
                                    'org.freedesktop.DBus', 'GetConnectionUnixUser', '(s)', (owner,))[0]
                require(uid == 1000, 'desktop service owner UID differs')
                self.owners[key] = owner
        except BaseException:
            self.close()
            raise

    def call_raw(self, destination, path, interface, method, signature=None, values=()):
        require(not self.connection.is_closed(), 'private desktop connection closed')
        args = self.GLib.Variant(signature, values) if signature else None
        return self.connection.call_sync(destination, path, interface, method, args,
            None, self.Gio.DBusCallFlags.NONE, 2000, None).unpack()

    def call(self, key, method, signature=None, values=(), interface=None):
        name, path = SERVICES[key]
        return self.call_raw(self.owners[key], path, interface or name, method, signature, values)

    def mode(self):
        return self.call('display', 'Get', '(ss)',
            ('org.gnome.Mutter.DisplayConfig', 'PowerSaveMode'), 'org.freedesktop.DBus.Properties')[0]

    def set_mode(self, value):
        self.call('display', 'Set', '(ssv)',
            ('org.gnome.Mutter.DisplayConfig', 'PowerSaveMode', self.GLib.Variant('i', value)),
            'org.freedesktop.DBus.Properties')

    def inhibitors(self):
        return self.call('session', 'GetInhibitors')[0]

    def snapshot(self):
        for key, (name, path) in SERVICES.items():
            owner = self.call_raw('org.freedesktop.DBus', '/org/freedesktop/DBus',
                                  'org.freedesktop.DBus', 'GetNameOwner', '(s)', (name,))[0]
            require(owner == self.owners[key], 'desktop service owner changed: ' + key)
        return {'monotonic_ns': time.monotonic_ns(), 'power_save_mode': self.mode(),
                'locked': self.call('screen', 'GetActive')[0],
                'idle_ms': self.call('idle', 'GetIdletime')[0]}

    def close(self):
        if not self.connection.is_closed():
            self.connection.close_sync(None)
        require(self.connection.is_closed(), 'private desktop connection did not close')


class DisplayLease:
    def __init__(self, transaction, record):
        require(transaction.isascii() and transaction.replace('-', '').replace('_', '').isalnum()
                and 1 <= len(transaction) <= 96, 'unsafe lease transaction')
        self.record = record
        self.bus = DesktopBus()
        self.cookie = None
        self.inhibitor = None
        self.identity = None
        self.wake_attempted = False
        self.owns_mode = False
        self.subscription = None
        self.events = []
        try:
            self.before = self.bus.snapshot()
            require(self.before['locked'] is True, 'desktop is not locked')
            require(self.before['power_save_mode'] in (0, 3), 'unexpected initial display power state')
            self.record.update({'before': self.before, 'owners': dict(self.bus.owners),
                               'private_bus_name': self.bus.unique_name, 'events': self.events,
                               'normal_alex_uid': os.geteuid(), 'explicit_wake_count': 0})
            self.app_id = 'local.hepta.pocket4.camera-lease.' + transaction
            self.before_inhibitors = self.bus.inhibitors()
        except BaseException:
            self.bus.close()
            raise

    def pump(self):
        context = self.bus.GLib.MainContext.default()
        count = 0
        while context.pending():
            require(count < 1024, 'unexpected desktop signal flood')
            context.iteration(False)
            count += 1

    def changed(self, connection, sender, path, interface, signal, parameters, user_data):
        iface, changed, invalidated = parameters.unpack()
        if iface == 'org.gnome.Mutter.DisplayConfig' and 'PowerSaveMode' in changed:
            mode = changed['PowerSaveMode']
            self.events.append({'monotonic_ns': time.monotonic_ns(), 'mode': mode, 'sender': sender})
            if self.wake_attempted and mode != 0:
                self.owns_mode = False

    def check(self, require_device=True):
        self.pump()
        current = self.bus.snapshot()
        predicted_idle = self.before['idle_ms'] + (current['monotonic_ns'] - self.before['monotonic_ns']) / 1_000_000
        if current['locked'] is not True or current['idle_ms'] + 1000 < predicted_idle:
            self.owns_mode = False
            raise RuntimeError('desktop lock or real user-idle authority changed')
        require(current['power_save_mode'] == 0, 'display power left normal mode during lease')
        require(self.inhibitor in self.bus.inhibitors(), 'owned desktop inhibitor disappeared')
        if require_device:
            identity = physical_identity()
            require(identity == self.identity, 'physical built-in camera identity changed during lease')
        return current

    def acquire(self):
        self.subscription = self.bus.connection.signal_subscribe(
            self.bus.owners['display'], 'org.freedesktop.DBus.Properties', 'PropertiesChanged',
            SERVICES['display'][1], 'org.gnome.Mutter.DisplayConfig',
            self.bus.Gio.DBusSignalFlags.NONE, self.changed, None)
        self.cookie = self.bus.call('session', 'Inhibit', '(susu)',
            (self.app_id, 0, 'Bounded built-in camera qualification ' + self.app_id, 8))[0]
        require(type(self.cookie) is int and 0 < self.cookie < 2**32, 'invalid inhibitor cookie')
        added = set(self.bus.inhibitors()) - set(self.before_inhibitors)
        require(len(added) == 1, 'owned inhibitor identity is ambiguous')
        self.inhibitor = added.pop()
        iface = 'org.gnome.SessionManager.Inhibitor'
        app = self.bus.call_raw(self.bus.owners['session'], self.inhibitor, iface, 'GetAppId')[0]
        flags = self.bus.call_raw(self.bus.owners['session'], self.inhibitor, iface, 'GetFlags')[0]
        require(app == self.app_id and flags == 8, 'owned inhibitor app/flags differ')
        self.record['inhibitor'] = {'path': self.inhibitor, 'cookie': self.cookie, 'app_id': app, 'flags': flags}
        if self.before['power_save_mode'] == 3:
            self.wake_attempted = True
            self.owns_mode = True
            self.record['explicit_wake_count'] = 1
            self.bus.set_mode(0)
        deadline = time.monotonic() + 15
        while True:
            self.check(require_device=False)
            try:
                self.identity = physical_identity()
                break
            except FileNotFoundError:
                require(time.monotonic() < deadline, 'built-in Sunplus did not enumerate after one display wake')
                time.sleep(0.2)
        self.record['physical_device'] = self.identity
        self.record['ready_monotonic_ns'] = time.monotonic_ns()
        self.record['ready'] = self.check()
        return self.record['ready']

    def finish(self):
        cleanup = {'connection_closed': False, 'inhibitor_removed': False,
                   'entry_mode_restored': False, 'restore_attempted': False, 'errors': []}
        self.record['cleanup'] = cleanup
        try:
            if not self.bus.connection.is_closed():
                self.pump()
                current = self.bus.snapshot()
                predicted = self.before['idle_ms'] + (current['monotonic_ns'] - self.before['monotonic_ns']) / 1_000_000
                may_restore = (self.wake_attempted and self.owns_mode and
                    current['power_save_mode'] == 0 and current['locked'] is True and
                    current['idle_ms'] + 1000 >= predicted and self.inhibitor in self.bus.inhibitors())
                cleanup['restore_authority_observation'] = current
                cleanup['owned_state_continuity'] = may_restore
                if may_restore:
                    cleanup['restore_attempted'] = True
                    self.owns_mode = False
                    self.bus.set_mode(self.before['power_save_mode'])
                if self.cookie is not None:
                    self.bus.call('session', 'Uninhibit', '(u)', (self.cookie,))
        except BaseException as exc:
            cleanup['errors'].append({'stage': 'normal_release', 'type': type(exc).__name__, 'message': str(exc)})
        finally:
            try:
                if self.subscription is not None:
                    self.bus.connection.signal_unsubscribe(self.subscription)
                self.bus.close()
                cleanup['connection_closed'] = True
            except BaseException as exc:
                cleanup['errors'].append({'stage': 'connection_close', 'message': str(exc)})
        observer = None
        try:
            observer = DesktopBus()
            require(observer.owners == self.bus.owners, 'desktop owner changed before release observation')
            cleanup['inhibitor_removed'] = self.inhibitor is None or self.inhibitor not in observer.inhibitors()
            cleanup['after'] = observer.snapshot()
            cleanup['entry_mode_restored'] = cleanup['after']['power_save_mode'] == self.before['power_save_mode']
            require(cleanup['after']['locked'] is True, 'desktop lock changed at release')
        except BaseException as exc:
            cleanup['errors'].append({'stage': 'release_observation', 'type': type(exc).__name__, 'message': str(exc)})
        finally:
            if observer is not None:
                observer.close()
        return cleanup
