"""Main-only binding for the existing business recorder; no UI operations here.

The qualified R5 primitives hold the init namespaces/root and both real roots
used for classpath resolution. The original recorder still owns epoch checks,
the action lock, task claims, command evidence, and explicit task removal.
"""
import os
import stat
import time


def require(value, code):
    if not value:
        raise RuntimeError(code)


def same_epoch_identity(raw, expected):
    return (raw["pid"] == expected["host_pid"] and
            int(raw["start"]) == expected["start_ticks"] and
            raw["uid"] == [str(value) for value in expected["uids"]] and
            raw["ppid"] == expected["parent_host_pid"] and
            [int(value) for value in raw["nspid"]] == expected["namespace_pids"] and
            raw["exe"] == expected["executable"] and
            raw["cgroup"].splitlines() == expected["cgroup"] and
            all(raw["ns"][key] == value for key, value in expected["namespaces"].items()
                if key in raw["ns"]))


def main_classpaths(held, target, framework_epoch, epoch, guard):
    """R5's two-root proof, labelled accurately for this fixed Main target."""
    guard()
    expected = framework_epoch["binding"]["processes"]["zygote64"]
    require(expected["namespaces"]["pid"] == target.expected["ns"]["pid"],
            "MAIN_ZYGOTE_PID_NAMESPACE_CHANGED")
    require(epoch.process_identity(expected["host_pid"]) == expected,
            "MAIN_ZYGOTE_CHANGED_BEFORE_ENVIRONMENT_READ")
    deadline = time.monotonic() + held.CLASSPATH_SECONDS
    view = held.HeldZygoteRoot(expected, deadline)
    primary = None
    try:
        raw = held.read_at(view.proc_fd, "environ", held.ENV_LIMIT, deadline)
        values = held.selected_classpaths(raw)
        environment = selected_environment(raw)
        del raw
        files, total = held.hash_classpaths_paired(target, view, values, deadline)
        again_raw = held.read_at(view.proc_fd, 'environ', held.ENV_LIMIT, deadline)
        again = held.selected_classpaths(again_raw)
        require(selected_environment(again_raw) == environment, 'HELD_ENVIRONMENT_CHANGED')
        del again_raw
        require(again == values, "MAIN_ZYGOTE_CLASSPATH_CHANGED_DURING_ADMISSION")
        view.verify()
        require(epoch.process_identity(expected["host_pid"]) == expected,
                "MAIN_ZYGOTE_GENERATION_CHANGED_AFTER_ENVIRONMENT_READ")
        target.verify()
        guard()
        return values, {"schema": 2, "source": "fixed Main zygote held procdir only",
            "zygote": expected, "required_keys": list(held.REQUIRED_CLASSPATHS),
            "values": values, "files": files, "total_bytes": total,
            "limits": {"environ_bytes": held.ENV_LIMIT, "path_count": held.PATH_COUNT_LIMIT,
                       "per_file_bytes": held.FILE_LIMIT, "total_file_bytes": held.TOTAL_FILE_LIMIT,
                       "deadline_seconds": held.CLASSPATH_SECONDS},
            "root": target.root_record, "zygote_root": view.root_record,
            "zygote_mount_namespace": held.fd_record(view.mnt_fd),
            "command_mount_namespace": held.fd_record(target.namespaces["mnt"]),
            "resolution_contract": "same dev/inode/size from simultaneously held init-root and zygote-root file descriptors; metadata stable around streaming hash",
            "different_mount_namespaces_permitted": True,
            "different_backing_files_permitted": False,
            "main_classpath_read": True}, environment
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            view.close()
        except BaseException as cleanup:
            if primary is None:
                raise
            primary.add_note("Main zygote root cleanup: " + type(cleanup).__name__ + ": " + str(cleanup))


def package_uids(raw, packages):
    """Retain only the requested package metadata, never the complete UID list."""
    found = {}
    for line in raw.decode("utf-8", "strict").splitlines():
        fields = line.split()
        if not fields or fields[0] not in packages:
            continue
        require(len(fields) >= 2 and fields[1].isdecimal() and fields[0] not in found,
                "PACKAGE_UID_ROW_INVALID_OR_DUPLICATED")
        found[fields[0]] = int(fields[1])
    require(found == packages, "FIXED_BILIBILI_OR_ACTION_RUNNER_UID_CHANGED")
    return found



def selected_environment(raw):
    keys = {'PATH', 'BOOTCLASSPATH', 'DEX2OATBOOTCLASSPATH', 'ANDROID_ART_ROOT', 'ANDROID_ASSETS',
        'ANDROID_BOOTLOGO', 'ANDROID_DATA', 'ANDROID_I18N_ROOT', 'ANDROID_ROOT', 'ANDROID_STORAGE',
        'ANDROID_TZDATA_ROOT', 'ASEC_MOUNTPOINT', 'DOWNLOAD_CACHE', 'EXTERNAL_STORAGE',
        'LOOP_MOUNTPOINT', 'STANDALONE_SYSTEMSERVER_JARS', 'SYSTEMSERVERCLASSPATH', 'LANG'}
    found = {}
    for row in raw.split(b'\0'):
        if b'=' not in row:
            continue
        key, value = row.split(b'=', 1)
        name = key.decode('utf-8', 'strict')
        if name not in keys:
            continue
        require(name not in found and len(value) <= 65536, 'ENV_DUPLICATE_OR_BOUND')
        found[name] = value.decode('utf-8', 'strict')
    return found

class MainBinding:
    def __init__(self, *, contract, source, scope, activation, epoch, app, guard):
        source.verify_scope(scope, activation, contract)
        self.target = None
        self.contract, self.scope, self.activation, self.guard = contract, scope, activation, guard
        self.held = contract.load('references/held_runtime_r5.py', 'successor_held_runtime_r5')
        self.transport_module = contract.load('bound_android_transport.py', 'successor_transport')
        self.helper_qualification = source.verify_shared_helper()
        guard()
        expected = activation['framework_epoch']['binding']['processes']['init']
        init = expected['host_pid']
        require(epoch.process_identity(init) == expected, 'EXACT_SUCCESSOR_INIT_CHANGED')
        proc = os.open('/proc/' + str(init), os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            raw_identity = self.held.proc_identity_at(proc, init, time.monotonic() + 3)
            require(same_epoch_identity(raw_identity, expected) and raw_identity == activation['held_init_identity'],
                    'HELD_INIT_DIFFERS_FROM_ACTUAL_SUCCESSOR_INPUT')
        finally:
            os.close(proc)
        try:
            self.target = self.held.HeldTarget(raw_identity, source.HELPER_PATH, source.HELPER_SHA)
            require(epoch.process_identity(init) == expected, 'INIT_CHANGED_WHILE_ACQUIRING_FDS')
            values, classpath, environment = main_classpaths(self.held, self.target,
                    activation['framework_epoch'], epoch, guard)
            require(values == activation['classpath_values'], 'FIXED_SUCCESSOR_CLASSPATH_DIFFERS')
            self.environment = self.transport_module.environment_values(environment)
            self.packages = dict(activation['packages'])
            self.directories = dict(activation['app_directories'])
            self.verify()
            guard()
            self.record = {'schema':'pocket4-successor-held-binding-r5-v1',
                'runtime_epoch_sha256':activation['runtime_epoch_sha256'],
                'framework_epoch_sha256':source.MAIN_EPOCH,
                'app_scope_sha256':activation['app_scope']['sha256'], 'package':source.PACKAGE, 'uid':source.UID,
                'held_runtime_r5_sha256':source.REFERENCE_PINS['references/held_runtime_r5.py'][1],
                'target':self.target.record, 'classpath':classpath, 'helper_qualification':self.helper_qualification,
                'package_uids':self.packages, 'app_directories':self.directories,
                'ui_actions_performed_by_binding':False, 'owned_QA_helper_qualification_inherited':False,
                'production_ready':False}
        except BaseException as original:
            if self.target is not None:
                try:
                    self.target.close()
                except BaseException as cleanup:
                    original.add_note('held binding cleanup: ' + type(cleanup).__name__)
            raise

    def verify(self):
        self.target.verify()
        raw, _ = self.target.read_file('/data/system/packages.list', 1024 * 1024)
        package_uids(raw, self.packages)
        del raw
        for path, expected in self.directories.items():
            fd = self.target.open_root(path, os.O_PATH | os.O_DIRECTORY)
            try:
                info = os.fstat(fd)
                require(stat.S_ISDIR(info.st_mode) and
                        (info.st_dev, info.st_ino, info.st_uid, info.st_gid) ==
                        (expected['device'], expected['inode'], expected['uid'], expected['gid']),
                        'BOUND_APP_DATA_DIRECTORY_CHANGED')
            finally:
                os.close(fd)
        self.target.verify()

    def transport(self, *, record, runner, guard):
        return self.transport_module.BoundArun(target=self.target, environment=self.environment,
            guard=guard, record=record, epoch_sha256=self.scope['epoch_sha256'],
            init_pid=self.target.expected['pid'], package=self.scope['package'], uid=self.scope['uid'],
            interactive_production=True, runner=runner)

    def close(self):
        if self.target is not None:
            self.target.close()
