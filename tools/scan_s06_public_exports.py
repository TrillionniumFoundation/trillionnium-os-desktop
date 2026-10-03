#!/usr/bin/env python3
"""Emit explicit Rust public use/type statements for the S06 absence guard.

Comments and literals never supply public syntax. This bounded lexical inventory
does not expand macros or replace Rust compilation and the closed product API
tests. CI rejects wildcard public imports as well as the forbidden named types.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys

MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_FILES = 256
MAX_ENTRIES = 1024
MAX_DEPTH = 32
MAX_ROOT_COMPONENTS = 64
MAX_TOTAL_BYTES = 8 * 1024 * 1024
MAX_STATEMENTS = 1024
RAW_STRING = re.compile(r'(?:br|cr|r)(#*)"')


PRODUCT_ROOT = Path(__file__).absolute().parents[1]
PRODUCT_DIRECTORY = PRODUCT_ROOT / "crates/hepta-browser-actor/src"
PRODUCT_CONTRACT = PRODUCT_ROOT / "contracts/browser-actor.v1.json"
CLOSED_PRODUCT_EXPORTS = ['pub use servo_runtime : : { ServoBrowserActor , ServoCompletionDelivery , ServoEventLoopWaker , ServoPumpResult , ServoRuntimeCommand , ServoRuntimeCompletion , ServoRuntimeEndpoint , ServoRuntimeError , ServoRuntimeOperation , ServoRuntimeOwner , closed_immutable_servo_runtime_pair , servo_runtime_pair , } ;', 'pub use servo_runtime : : { ServiceServoBrowserActor , ServiceServoRuntimeBridge , ServiceServoRuntimeCommand , ServiceServoRuntimeCompletion , ServiceServoRuntimeEndpoint , closed_immutable_service_runtime_pair , } ;', 'pub use hepta_agent_port : : { AgentPortError , DispatchContext , HandlerOutcome } ;', 'pub use hepta_agent_transport : : PeerIdentity ;', 'pub use hepta_browser_codec : : { BrowserRequest , BrowserResponse , ElementReference , JsonObject , JsonValue , NavigationTarget , ObservationField , PageAction , ProfilePersistence , ProfileSpec , WaitCondition , } ;', 'pub use hepta_peer_attestation : : { AttestedPeer , ProcfsPeerAttestor } ;', 'pub use hepta_session_core : : ReceiptJournal ;', 'pub use simulation : : { CancellationToken , PageOwnerSnapshot , ReceiptLifecycleObserver , TaskFlowPrincipal , executable_sha256 , scoped_frame_id , } ;', 'pub use service_runtime : : { ServiceServoBrowserActor , ServiceServoRuntimeBridge , ServiceServoRuntimeCommand , ServiceServoRuntimeCompletion , ServiceServoRuntimeEndpoint , closed_immutable_service_runtime_pair , } ;', 'pub use service_actor : : ServiceServoBrowserActor ;']
CLOSED_PRODUCT_CONTRACT = {'schema': 'hepta.browser-actor.closed-public-export-ledger.v1', 'scope': 'SOURCE_ONLY_LEXICAL_PUBLIC_USE_AND_TYPE_DECLARATIONS', 'lexical_declaration_count': 10, 'lexical_declarations': ['pub use servo_runtime : : { ServoBrowserActor , ServoCompletionDelivery , ServoEventLoopWaker , ServoPumpResult , ServoRuntimeCommand , ServoRuntimeCompletion , ServoRuntimeEndpoint , ServoRuntimeError , ServoRuntimeOperation , ServoRuntimeOwner , closed_immutable_servo_runtime_pair , servo_runtime_pair , } ;', 'pub use servo_runtime : : { ServiceServoBrowserActor , ServiceServoRuntimeBridge , ServiceServoRuntimeCommand , ServiceServoRuntimeCompletion , ServiceServoRuntimeEndpoint , closed_immutable_service_runtime_pair , } ;', 'pub use hepta_agent_port : : { AgentPortError , DispatchContext , HandlerOutcome } ;', 'pub use hepta_agent_transport : : PeerIdentity ;', 'pub use hepta_browser_codec : : { BrowserRequest , BrowserResponse , ElementReference , JsonObject , JsonValue , NavigationTarget , ObservationField , PageAction , ProfilePersistence , ProfileSpec , WaitCondition , } ;', 'pub use hepta_peer_attestation : : { AttestedPeer , ProcfsPeerAttestor } ;', 'pub use hepta_session_core : : ReceiptJournal ;', 'pub use simulation : : { CancellationToken , PageOwnerSnapshot , ReceiptLifecycleObserver , TaskFlowPrincipal , executable_sha256 , scoped_frame_id , } ;', 'pub use service_runtime : : { ServiceServoBrowserActor , ServiceServoRuntimeBridge , ServiceServoRuntimeCommand , ServiceServoRuntimeCompletion , ServiceServoRuntimeEndpoint , closed_immutable_service_runtime_pair , } ;', 'pub use service_actor : : ServiceServoBrowserActor ;'], 'retained_declaration_count': 7, 'Service_added_declaration_count': 3, 'Service_unique_names': ['ServiceServoBrowserActor', 'ServiceServoRuntimeBridge', 'ServiceServoRuntimeCommand', 'ServiceServoRuntimeCompletion', 'ServiceServoRuntimeEndpoint', 'closed_immutable_service_runtime_pair'], 'Service_public_structs_private_state': 5, 'Service_declaration_paths': ['crates/hepta-browser-actor/src/lib.rs', 'crates/hepta-browser-actor/src/servo_runtime.rs', 'crates/hepta-browser-actor/src/servo_runtime/service_runtime.rs'], 'separate_typed_API_contracts': ['contracts/approved-service-runtime.v2.json', 'contracts/approved-service-actor.v2.json', 'contracts/service-dispatch-denial-cutoff.v1.json'], 'scanner_does_not_expand_macros_or_compile_Rust': True, 'genuine_session_verifier_and_original_binding_required_for_actor': True, 'unbound_pair_mints_request_authority': False, 'raw_handler_exposed': False, 'native_consumer_connected': False, 'default_product_enabled': False, 'installed_image_qualified': False, 'Native_qualified': False, 'production_release': False}


def tokens(source: str) -> list[str]:
    """Discard Rust comments/literals while retaining identifier boundaries."""
    result: list[str] = []
    position = 0
    while position < len(source):
        if source[position].isspace():
            position += 1
            continue
        if source.startswith("//", position):
            newline = source.find("\n", position + 2)
            position = len(source) if newline < 0 else newline + 1
            continue
        if source.startswith("/*", position):
            depth = 1
            position += 2
            while depth:
                if position >= len(source):
                    raise ValueError("unterminated Rust block comment")
                if source.startswith("/*", position):
                    depth += 1
                    position += 2
                elif source.startswith("*/", position):
                    depth -= 1
                    position += 2
                else:
                    position += 1
            continue
        raw = RAW_STRING.match(source, position)
        if raw:
            delimiter = '"' + raw.group(1)
            end = source.find(delimiter, raw.end())
            if end < 0:
                raise ValueError("unterminated Rust raw string")
            position = end + len(delimiter)
            continue
        quote = position
        if source[position:position + 2] in {'b"', 'c"', "b'"}:
            quote += 1
        if source[quote] == '"':
            position = quote + 1
            while True:
                if position >= len(source):
                    raise ValueError("unterminated Rust string")
                if source[position] == "\\":
                    position += 2
                elif source[position] == '"':
                    position += 1
                    break
                else:
                    position += 1
            continue
        # A lifetime is not a character literal. A character has one literal
        # scalar or one escape immediately followed by its terminating quote.
        if source[quote] == "'":
            end = quote + 1
            if end < len(source) and source[end] == "\\":
                end += 2
                if source[quote + 2:quote + 4] == "u{":
                    brace = source.find("}", quote + 4)
                    if brace < 0:
                        raise ValueError("unterminated Rust character escape")
                    end = brace + 1
                elif source[quote + 2:quote + 3] == "x":
                    end += 2
            else:
                end += 1
            if end < len(source) and source[end] == "'":
                position = end + 1
                continue
        start = position
        if source.startswith("r#", position):
            position += 2
            start = position
            if position >= len(source) or not (source[position].isalpha() or source[position] == "_"):
                raise ValueError("invalid Rust raw identifier")
        if position < len(source) and (source[position].isalpha() or source[position] == "_"):
            position += 1
            while position < len(source) and (source[position].isalnum() or source[position] == "_"):
                position += 1
            result.append(source[start:position])
        else:
            result.append(source[position])
            position += 1
    return result


def public_exports(source: str) -> list[str]:
    items = tokens(source)
    statements: list[str] = []
    for index, item in enumerate(items[:-1]):
        if item != "pub" or items[index + 1] not in {"use", "type"}:
            # pub(crate), pub(super), pub(self), and pub(in ...) are private
            # crate/module authority, not an externally exported declaration.
            continue
        end = index + 2
        while end < len(items) and items[end] != ";":
            end += 1
        if end == len(items):
            raise ValueError("unterminated public use/type declaration")
        statements.append(" ".join(items[index:end + 1]))
        if len(statements) > MAX_STATEMENTS:
            raise ValueError("public export count exceeds its bound")
    return statements


class _Descriptor:
    """One descriptor owner; cleanup never retries an attempted raw close."""
    def __init__(self):
        self.fd = None

    def close(self):
        descriptor = None
        attempted = False
        try:
            descriptor, self.fd = self.fd, None
            if descriptor is not None:
                attempted = True; os.close(descriptor)
        except BaseException:
            if descriptor is not None and not attempted:
                self.fd = descriptor
            raise

    def __del__(self):
        try:
            self.close()
        except BaseException:
            pass


def _close_all(owners):
    failure = None
    for owner in reversed(owners):
        try:
            owner.close()
        except BaseException as error:
            if failure is None:
                failure = error
    if failure is not None:
        raise failure


def _directory(path):
    parts = path.parts
    if not path.is_absolute() or len(parts) > MAX_ROOT_COMPONENTS or ".." in parts:
        raise ValueError("Rust source root exceeds its canonical component bound")
    owners = []
    current = _Descriptor()
    owners.append(current)
    try:
        current.fd = os.open(parts[0], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        for name in parts[1:]:
            following = _Descriptor()
            owners.append(following)
            following.fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                   dir_fd=current.fd)
            current.close()
            current = following
        return current
    except BaseException:
        _close_all(owners)
        raise


def _identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def _source(path):
    # Hold an empty owner before every native open. Both the returned leaf and
    # intermediate directories remain owned if an ordinary Python line fails.
    leaf = _Descriptor()
    parent = None
    try:
        parent = _directory(path.parent)
        leaf.fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                          dir_fd=parent.fd)
        metadata = os.fstat(leaf.fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError("Rust source must be regular and have exactly one hard link")
        return leaf
    except BaseException:
        leaf.close()
        raise
    finally:
        if parent is not None:
            parent.close()


class _Frame:
    def __init__(self, path):
        self.path = path
        self.directory = _Descriptor()
        self.iterator = None
        self.identity = None

    def begin(self):
        self.identity = _identity(os.fstat(self.directory.fd))
        self.iterator = os.scandir(self.directory.fd)

    def check(self):
        if _identity(os.fstat(self.directory.fd)) != self.identity:
            raise ValueError("Rust source directory changed while scanning")

    def close(self):
        iterator, self.iterator = self.iterator, None
        try:
            if iterator is not None:
                iterator.close()
        finally:
            self.directory.close()

    def __del__(self):
        try:
            self.close()
        except BaseException:
            pass


def inventory(directory: Path) -> list[str]:
    # Each next() consumes one actual DirEntry; neither pathlib.rglob nor a
    # directory-wide list is used. Only a fixed-depth DFS frontier is retained.
    directory = directory.absolute()
    creator = os.getpid()
    def current():
        if creator != os.getpid():
            raise ValueError("Rust source scanner creating process changed")
    statements = []
    paths = []
    directories = []
    total = 0
    entries = 0
    stack = []
    try:
        root = _Frame(directory)
        stack.append(root)
        root.directory = _directory(directory)
        root.begin()
        directories.append((directory, root.identity))
        while stack:
            current()
            frame = stack[-1]
            frame.check()
            try:
                entry = next(frame.iterator)
            except StopIteration:
                frame.check()
                retired = stack.pop()
                retired.close()
                continue
            current()
            entries += 1
            if entries > MAX_ENTRIES:
                raise ValueError("Rust source inventory exceeds its entry bound")
            observed = os.stat(entry.name, dir_fd=frame.directory.fd, follow_symlinks=False)
            current()
            path = frame.path / entry.name
            if stat.S_ISLNK(observed.st_mode):
                raise ValueError("Rust source inventory contains a symlink")
            if path.suffix == ".rs":
                if not stat.S_ISREG(observed.st_mode):
                    raise ValueError("Rust source entry is not a regular file")
                if len(paths) >= MAX_FILES:
                    raise ValueError("Rust source inventory exceeds its file bound")
                paths.append((path, _identity(observed)))
            elif stat.S_ISDIR(observed.st_mode):
                if len(stack) >= MAX_DEPTH:
                    raise ValueError("Rust source inventory exceeds its depth bound")
                child = _Frame(path)
                stack.append(child)
                child.directory.fd = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                             dir_fd=frame.directory.fd)
                child.begin()
                if child.identity != _identity(observed):
                    raise ValueError("Rust source directory name changed while opening")
                directories.append((path, child.identity))
        for path, expected in sorted(paths):
            current()
            retained_source = _source(path)
            try:
                before = os.fstat(retained_source.fd)
                if _identity(before) != expected:
                    raise ValueError("Rust source entry changed after enumeration")
                if before.st_size > MAX_SOURCE_BYTES:
                    raise ValueError("Rust source exceeds its byte bound")
                if before.st_size > MAX_TOTAL_BYTES - total:
                    raise ValueError("Rust source inventory exceeds its total byte bound")
                data = bytearray()
                while len(data) <= before.st_size:
                    current()
                    chunk = os.read(retained_source.fd, min(64 * 1024, before.st_size + 1 - len(data)))
                    current()
                    if not chunk:
                        break
                    data.extend(chunk)
                after = os.fstat(retained_source.fd)
                named = path.lstat()
                if len(data) != before.st_size or _identity(before) != _identity(after) or _identity(named) != _identity(after):
                    raise ValueError("Rust source changed while scanning")
            finally:
                retained_source.close()
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise ValueError("Rust source inventory exceeds its total byte bound")
            statements.extend(public_exports(data.decode("utf-8")))
            if len(statements) > MAX_STATEMENTS:
                raise ValueError("public export inventory exceeds its count bound")
        if not paths:
            raise ValueError("Rust source inventory is empty")
        # Reopen every bounded observed directory without following any parent;
        # late pathname/metadata drift never yields a partial successful list.
        for path, expected in directories:
            current()
            retained = _directory(path)
            try:
                if _identity(os.fstat(retained.fd)) != expected:
                    raise ValueError("Rust source directory changed after enumeration")
                current()
            finally:
                retained.close()
        current()
        return statements
    finally:
        owned, stack = stack, []
        _close_all(owned)



def _closed_contract_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("closed product contract has duplicate JSON keys")
        result[key] = value
    return result


def _closed_contract_constant(value):
    raise ValueError("closed product contract has a non-JSON numeric constant")


def _closed_contract():
    """Read the fixed Source contract through the existing no-link FD owner."""
    path = PRODUCT_CONTRACT
    creator = os.getpid()
    def current():
        if creator != os.getpid():
            raise ValueError("product contract scanner creating process changed")
    current()
    retained = _source(path)
    try:
        current()
        before = os.fstat(retained.fd)
        if before.st_size > MAX_SOURCE_BYTES:
            raise ValueError("closed product contract exceeds its byte bound")
        data = bytearray()
        while len(data) <= before.st_size:
            current()
            chunk = os.read(retained.fd, min(64 * 1024, before.st_size + 1 - len(data)))
            current()
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(retained.fd)
        named = path.lstat()
        current()
        if (len(data) != before.st_size or _identity(before) != _identity(after)
                or _identity(named) != _identity(after)):
            raise ValueError("closed product contract changed while scanning")
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_closed_contract_pairs,
                           parse_constant=_closed_contract_constant)
        if type(value) is not dict:
            raise ValueError("closed product contract must be an object")
        return value
    finally:
        retained.close()


def closed_product_inventory(directory: Path) -> list[str]:
    """The ten reviewed lexical declarations; no Rust/runtime qualification."""
    actual = _closed_contract().get("public_export_inventory")
    # Canonical JSON preserves boolean/integer/list/object distinctions. The
    # independent literal is not replaced by hashes or caller-supplied metadata.
    if (type(actual) is not dict
            or json.dumps(actual, sort_keys=True, separators=(",", ":"))
            != json.dumps(CLOSED_PRODUCT_CONTRACT, sort_keys=True, separators=(",", ":"))):
        raise ValueError("closed product export contract differs")
    statements = inventory(directory)
    if statements != CLOSED_PRODUCT_EXPORTS:
        raise ValueError("closed product export inventory differs")
    return statements


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--closed-product", action="store_true",
                        help="require the fixed reviewed product Source export contract")
    arguments = parser.parse_args()
    try:
        directory = arguments.directory.absolute()
        # The unchanged actual workflow supplies this exact product directory.
        # Temporary lexical fixtures retain their generic absence-guard mode;
        # this Source policy selection grants no runtime or installed authority.
        if arguments.closed_product or directory == PRODUCT_DIRECTORY:
            statements = closed_product_inventory(directory)
        else:
            statements = inventory(directory)
    except (OSError, ValueError, UnicodeError) as error:
        print(f"public export source scan failed: {error}", file=sys.stderr)
        return 2
    for statement in statements:
        print(statement)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
