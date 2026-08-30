#!/usr/bin/env python3
"""Validate the source-side D0T-03 governance contract.

The validator intentionally does not depend on PyYAML.  GitHub workflow files
are policy inputs, so silently falling back to a lossy line-oriented parser is
unsafe: YAML aliases, duplicate keys, flow collections, and quoted keys can
change the meaning of a workflow without changing a simple text match.  The
small parser below implements the YAML subset used by GitHub Actions and
rejects unsupported/ambiguous constructs (anchors, aliases, tags, malformed
flow syntax, duplicate mapping keys, and indentation errors).

This is a source-only check.  It proves neither repository settings nor human
review, signing custody, nor release readiness.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = ROOT / ".github" / "workflows"
CONTRACT_PATH = ROOT / "contracts" / "repository-governance.v1.json"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
ACTION_REF = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})?/"
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})?@[0-9a-f]{40}$"
)
LOCAL_ACTION = re.compile(r"^\./[A-Za-z0-9._/-]+$")
LOCAL_WORKFLOW = re.compile(r"^\./\.github/workflows/[A-Za-z0-9._-]+\.(?:yml|yaml)$")
OWNER_TOKEN = re.compile(r"^@[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)?$")

MUTATING_GIT_SUBCOMMANDS = {
    "push",
    "commit",
    "tag",
    "update-ref",
    "receive-pack",
    "upload-pack",
    "send-pack",
    "reset",
    "clean",
    "rebase",
    "merge",
    "cherry-pick",
    "revert",
    "branch",
    "config",
}
# Git accepts global options before the subcommand.  Options in this set take
# a separate argument; ``--git-dir=/path``/friends are handled by the ``=``
# branch in ``_git_invocation_mutates``.  Keeping this list explicit prevents
# a path argument such as ``-C push`` from being mistaken for the mutating
# subcommand.
MUTATING_GIT_OPTIONS_WITH_ARGS = frozenset(
    {
        "-C",
        "-c",
        "--config-env",
        "--exec-path",
        "--git-dir",
        "--namespace",
        "--super-prefix",
        "--work-tree",
    }
)
GIT_EXECUTABLES = frozenset({"git", "git.exe"})
GIT_MUTATING_HELPERS = frozenset(
    {
        "git-push",
        "git-push.exe",
        "git-receive-pack",
        "git-receive-pack.exe",
        "git-send-pack",
        "git-send-pack.exe",
        "git-update-ref",
        "git-update-ref.exe",
        "git-upload-pack",
        "git-upload-pack.exe",
    }
)
# Keep mutation recognizers line-oriented.  A ``[^\n]*`` expression over a
# multi-thousand-line ``run: |`` block can exhibit quadratic backtracking and
# make the policy gate hang; token scanning below is both stricter and linear.
GH_MUTATION = re.compile(
    r"(?<![A-Za-z0-9_])gh\s+(?:api|workflow\s+run|pr\s+(?:merge|review)|release\s+create)(?![A-Za-z0-9_-])",
    re.I,
)
REST_MUTATION = re.compile(
    r"(?<![A-Za-z0-9_])(?:curl|wget)\b[^\n]*?(?:--request|-X)(?:\s+|=\s*)?(?:POST|PUT|PATCH|DELETE)(?![A-Za-z0-9_-])",
    re.I,
)
DIRECT_GITHUB_MUTATION = re.compile(
    r"(?<![A-Za-z0-9_])(?:POST|PUT|PATCH|DELETE)\s+https?://api\.github\.com\b",
    re.I,
)
PYTHON_GITHUB_MUTATION = re.compile(
    r"(?<![A-Za-z0-9_])(?:requests|httpx)\.(?:post|put|patch|delete)\s*\([^\n]*api\.github\.com",
    re.I,
)
PYTHON_GIT_MUTATION = re.compile(
    r"[\"']git[\"']\s*,\s*[\"'](?:push|commit|tag|update-ref|receive-pack|send-pack|reset|clean|rebase|merge|cherry-pick|revert|branch|config)[\"']",
    re.I,
)
# Calls whose argument list may contain a tokenized Git command.  The body is
# parsed conservatively below rather than trying to model Python syntax with a
# single regular expression; this catches subprocess.run/call/Popen and
# os.system/system forms, including multiline calls and path-qualified
# executables.
PYTHON_COMMAND_CALL = re.compile(
    r"(?ix)(?<![A-Za-z0-9_.])(?:"
    r"subprocess\.(?:run|call|Popen|check_call|check_output)|"
    r"os\.(?:system|popen)|system"
    r")\s*\("
)
# Shell expansion can hide an otherwise tokenized Git executable from the
# bounded command scanner.  Keep these recognizers deliberately narrow and
# fail closed: a workflow that constructs a Git command dynamically is not a
# source-level proof that the command is read-only.
SHELL_VARIABLE = re.compile(r"^\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?$")
SHELL_ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)
SHELL_IFS_EXPANSION = re.compile(r"\$\{?IFS\}?\b")
GIT_NEWLINE_MUTATION = re.compile(
    r"(?is)(?<![A-Za-z0-9_-])"
    r"(?:[^\s;&|]+[/\\])?git(?:\.exe)?"
    r"[^;&|\n]{0,512}\n"
    r"(?:[ \t]*[^;&|\n]*\n){0,2}"
    r"[ \t]*(?:push|commit|tag|update-ref|receive-pack|send-pack|reset|clean|"
    r"rebase|merge|cherry-pick|revert|branch|config)\b"
)
EXPECTED_REQUIRED_CONTEXTS = frozenset(
    {
        "desktop-ci / repository-contracts",
        "desktop-ci / rust",
        "governance-integrity / governance-integrity",
    }
)
EXPECTED_REQUIRED_WORKFLOWS = (
    ".github/workflows/d0t03-source-contract.yml",
    ".github/workflows/governance-integrity.yml",
    ".github/workflows/ci.yml",
    ".github/workflows/agent-port-custody.yml",
    ".github/workflows/agent-transport-reference.yml",
    ".github/workflows/browser-codec-reference.yml",
    ".github/workflows/receipt-journal.yml",
    ".github/workflows/servo-exact-pin.yml",
    ".github/workflows/servo-headed-runtime.yml",
    ".github/workflows/d1-final-qualification.yml",
    ".github/workflows/d2i-integrated-image.yml",
)
EXPECTED_ROOT_FILES = frozenset(
    {
        ".editorconfig",
        ".gitignore",
        "CONTRIBUTING.md",
        "Cargo.lock",
        "Cargo.toml",
        "LICENSE",
        "Makefile",
        "README.md",
        "SECURITY.md",
        "rust-toolchain.toml",
    }
)
EXPECTED_CODEOWNER_PATTERNS = frozenset(
    {
        "*",
        "/.github/",
        "/contracts/",
        "/manifests/",
        "/docs/adr/",
        "/docs/security/",
        "/docs/release/",
    }
)
KNOWN_PERMISSION_KEYS = frozenset(
    {
        "actions",
        "attestations",
        "checks",
        "contents",
        "deployments",
        "discussions",
        "id-token",
        "issues",
        "models",
        "packages",
        "pages",
        "pull-requests",
        "repository-projects",
        "security-events",
        "statuses",
    }
)
KNOWN_WORKFLOW_KEYS = frozenset(
    {"name", "on", "permissions", "env", "defaults", "concurrency", "jobs"}
)
EXPECTED_DYNAMIC_ACCEPTANCE = frozenset(
    {
        "direct_push_rejected",
        "force_push_rejected",
        "branch_delete_rejected",
        "author_self_approval_not_counted",
        "failing_required_workflow_blocks_merge",
        "approval_dismissed_after_new_push",
        "unresolved_conversation_blocks_merge",
        "independently_approved_green_pull_request_can_merge",
        "production_environment_requires_independent_approval",
    }
)


class YamlParseError(ValueError):
    """A strict workflow YAML syntax/semantic error."""


@dataclass(frozen=True)
class _Line:
    number: int
    indent: int
    content: str
    raw: str


def _error(source: str, line: int, message: str) -> YamlParseError:
    return YamlParseError(f"{source}:{line}: {message}")


def _strip_comment(value: str) -> str:
    """Strip a YAML comment outside quoted scalars."""

    quote: str | None = None
    escaped = False
    index = 0
    while index < len(value):
        character = value[index]
        if quote == '"':
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quote = None
            index += 1
            continue
        if quote == "'":
            if character == "'":
                if index + 1 < len(value) and value[index + 1] == "'":
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if character in ("'", '"'):
            quote = character
        elif character == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
        index += 1
    return value.rstrip()


def _find_mapping_colon(value: str) -> int | None:
    """Find a block/flow mapping colon outside quotes.

    A colon is a YAML mapping delimiter only when followed by whitespace, a
    collection delimiter, or end-of-input.  This keeps ``https://`` and
    expression text in plain scalars intact.
    """

    quote: str | None = None
    escaped = False
    depth = 0
    index = 0
    while index < len(value):
        character = value[index]
        if quote == '"':
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quote = None
            index += 1
            continue
        if quote == "'":
            if character == "'":
                if index + 1 < len(value) and value[index + 1] == "'":
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if character in ("'", '"'):
            quote = character
            index += 1
            continue
        if character in "[{":
            depth += 1
            index += 1
            continue
        if character in "]}" and depth:
            depth -= 1
            index += 1
            continue
        if character == ":" and depth == 0:
            next_character = value[index + 1] if index + 1 < len(value) else ""
            if not next_character or next_character.isspace() or next_character in "[{]}":
                return index
        index += 1
    return None


def _contains_tag_or_anchor(value: str) -> bool:
    """Return whether syntax contains an unsupported YAML tag/anchor."""

    quote: str | None = None
    escaped = False
    index = 0
    expression = False
    while index < len(value):
        character = value[index]
        if quote == '"':
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quote = None
            index += 1
            continue
        if quote == "'":
            if character == "'":
                if index + 1 < len(value) and value[index + 1] == "'":
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if character in ("'", '"'):
            quote = character
            index += 1
            continue
        if value.startswith("{{", index):
            expression = True
            index += 2
            continue
        if expression and value.startswith("}}", index):
            expression = False
            index += 2
            continue
        if expression:
            index += 1
            continue
        # ``&`` is also the shell/YAML-expression operator (``&&``), ``!``
        # occurs in expressions, and ``*`` is legal punctuation in a plain
        # scalar.  Only reject the actual YAML indicator forms: an indicator
        # followed by an anchor/tag name (or the merge alias ``*``).  This
        # keeps expressions such as ``${{ a && b }}`` intact while refusing
        # ``&anchor``, ``*alias``, ``!tag`` and ``!!str``.
        if character in "&*!" and (
            index == 0 or value[index - 1].isspace() or value[index - 1] in "[{,:"
        ):
            next_character = value[index + 1] if index + 1 < len(value) else ""
            if character == "&" and next_character == "&":
                index += 2
                continue
            if character == "*" and (
                not next_character or next_character.isspace() or next_character in "[{,]}"
            ):
                return True
            if character in "&*!" and (
                next_character == "!"
                or next_character.isalpha()
                or next_character.isdigit()
                or next_character in "_-"
                or not next_character
            ):
                return True
        index += 1
    return False


def _scalar(value: str, source: str, line: int) -> Any:
    value = _strip_comment(value).strip()
    if not value:
        return None
    if _contains_tag_or_anchor(value):
        raise _error(source, line, "YAML tags, anchors, aliases, and merge syntax are forbidden")
    if value.startswith("'"):
        if not re.fullmatch(r"'(?:[^']|'')*'", value):
            raise _error(source, line, "malformed single-quoted scalar")
        return value[1:-1].replace("''", "'")
    if value.startswith('"'):
        if not re.fullmatch(r'"(?:[^"\\]|\\.)*"', value):
            raise _error(source, line, "malformed double-quoted scalar")
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise _error(source, line, f"malformed double-quoted scalar: {exc}") from exc
    if any(character in value for character in "\n\r"):
        raise _error(source, line, "newline in plain scalar")
    if value in {"null", "Null", "NULL", "~"}:
        return None
    if value in {"true", "True", "TRUE"}:
        return True
    if value in {"false", "False", "FALSE"}:
        return False
    if re.fullmatch(r"[-+]?(?:0|[1-9][0-9]*)", value):
        try:
            return int(value, 10)
        except ValueError:
            raise _error(source, line, "integer scalar is out of range")
    if re.fullmatch(r"[-+]?(?:[0-9]+\.[0-9]*|[0-9]*\.[0-9]+)", value):
        try:
            return float(value)
        except ValueError:
            raise _error(source, line, "invalid numeric scalar")
    # YAML plain scalars may contain punctuation, expressions, URLs, and
    # shell fragments.  Keep them as strings after the strict syntax checks.
    return value


class _FlowParser:
    def __init__(self, text: str, source: str, line: int):
        self.text = text
        self.source = source
        self.line = line
        self.position = 0

    def parse(self) -> Any:
        value = self._value()
        self._space()
        if self.position != len(self.text):
            raise _error(self.source, self.line, "trailing flow YAML content")
        return value

    def _space(self) -> None:
        while self.position < len(self.text):
            character = self.text[self.position]
            if character.isspace():
                self.position += 1
                continue
            if character == "#":
                # Flow comments consume the remainder of the logical value.
                self.position = len(self.text)
            break

    def _value(self, *, allow_empty: bool = False) -> Any:
        self._space()
        if self.position >= len(self.text):
            raise _error(self.source, self.line, "missing flow value")
        character = self.text[self.position]
        if allow_empty and character in ",]}":
            return None
        if character == "[":
            return self._sequence()
        if character == "{":
            return self._mapping()
        if character in ("'", '"'):
            return self._quoted()
        start = self.position
        # A plain flow scalar may contain spaces (for example an expression
        # or a command fragment).  It ends only at a collection delimiter;
        # nested collections and quoted values are handled recursively above.
        while self.position < len(self.text):
            character = self.text[self.position]
            if character in ",]}" :
                break
            self.position += 1
        token = self.text[start:self.position].strip()
        if not token:
            raise _error(self.source, self.line, "empty flow scalar")
        return _scalar(token, self.source, self.line)

    def _quoted(self) -> str:
        quote = self.text[self.position]
        start = self.position
        self.position += 1
        escaped = False
        while self.position < len(self.text):
            character = self.text[self.position]
            self.position += 1
            if quote == '"' and escaped:
                escaped = False
            elif quote == '"' and character == "\\":
                escaped = True
            elif character == quote:
                if quote == "'" and self.position < len(self.text) and self.text[self.position] == "'":
                    self.position += 1
                    continue
                raw = self.text[start:self.position]
                return _scalar(raw, self.source, self.line)
        raise _error(self.source, self.line, "unterminated flow quote")

    def _sequence(self) -> list[Any]:
        self.position += 1
        result: list[Any] = []
        self._space()
        if self.position < len(self.text) and self.text[self.position] == "]":
            self.position += 1
            return result
        while True:
            result.append(self._value())
            self._space()
            if self.position >= len(self.text):
                raise _error(self.source, self.line, "unterminated flow sequence")
            if self.text[self.position] == "]":
                self.position += 1
                return result
            if self.text[self.position] != ",":
                raise _error(self.source, self.line, "flow sequence requires commas")
            self.position += 1
            self._space()
            if self.position < len(self.text) and self.text[self.position] == "]":
                raise _error(self.source, self.line, "trailing flow comma")

    def _mapping(self) -> dict[str, Any]:
        self.position += 1
        result: dict[str, Any] = {}
        self._space()
        if self.position < len(self.text) and self.text[self.position] == "}":
            self.position += 1
            return result
        while True:
            key = self._key()
            self._space()
            if self.position >= len(self.text) or self.text[self.position] != ":":
                raise _error(self.source, self.line, "flow mapping key lacks colon")
            self.position += 1
            value = self._value(allow_empty=True)
            if key in result:
                raise _error(self.source, self.line, f"duplicate YAML mapping key: {key!r}")
            result[key] = value
            self._space()
            if self.position >= len(self.text):
                raise _error(self.source, self.line, "unterminated flow mapping")
            if self.text[self.position] == "}":
                self.position += 1
                return result
            if self.text[self.position] != ",":
                raise _error(self.source, self.line, "flow mapping requires commas")
            self.position += 1
            self._space()
            if self.position < len(self.text) and self.text[self.position] == "}":
                raise _error(self.source, self.line, "trailing flow comma")

    def _key(self) -> str:
        self._space()
        if self.position >= len(self.text):
            raise _error(self.source, self.line, "missing flow mapping key")
        if self.text[self.position] in ("'", '"'):
            value = self._quoted()
            if not isinstance(value, str):
                raise _error(self.source, self.line, "flow mapping key must be a string")
            return value
        start = self.position
        while self.position < len(self.text):
            character = self.text[self.position]
            if character == ":":
                break
            if character in ",]}" or character.isspace():
                # Whitespace before a colon is legal; leave it for _space.
                if character.isspace():
                    self.position += 1
                    continue
                break
            self.position += 1
        key = self.text[start:self.position].strip()
        if not key or key == "<<":
            raise _error(self.source, self.line, "invalid or merge flow mapping key")
        if _contains_tag_or_anchor(key):
            raise _error(self.source, self.line, "flow mapping key uses an anchor/tag")
        return str(_scalar(key, self.source, self.line))


class StrictYamlParser:
    """Parse the workflow YAML subset while rejecting ambiguous constructs."""

    def __init__(self, text: str, *, source: str = "<workflow>"):
        self.source = source
        self.lines: list[_Line] = []
        for number, raw in enumerate(text.splitlines(), 1):
            if "\t" in raw[: len(raw) - len(raw.lstrip(" ")) + 1]:
                raise _error(source, number, "tabs are forbidden in YAML indentation")
            if any(ord(character) < 0x20 and character not in "\t" for character in raw):
                raise _error(source, number, "control character in YAML source")
            indent = len(raw) - len(raw.lstrip(" "))
            content = _strip_comment(raw[indent:])
            if content:
                self.lines.append(_Line(number, indent, content, raw))

    def parse(self) -> Any:
        if not self.lines:
            raise YamlParseError(f"{self.source}: empty YAML document")
        if self.lines[0].content in {"---", "..."}:
            raise _error(self.source, self.lines[0].number, "YAML document markers are unsupported")
        value, index = self._block(0, self.lines[0].indent)
        if index != len(self.lines):
            line = self.lines[index]
            raise _error(self.source, line.number, "unexpected YAML content after document")
        return value

    def _block(self, index: int, indent: int) -> tuple[Any, int]:
        if index >= len(self.lines):
            return None, index
        line = self.lines[index]
        if line.indent < indent:
            return None, index
        if line.indent != indent:
            raise _error(self.source, line.number, "unexpected indentation")
        if line.content == "-" or line.content.startswith("- "):
            return self._sequence(index, indent)
        return self._mapping(index, indent)

    def _mapping(self, index: int, indent: int) -> tuple[dict[str, Any], int]:
        result: dict[str, Any] = {}
        while index < len(self.lines):
            line = self.lines[index]
            if line.indent < indent:
                break
            if line.indent > indent:
                raise _error(self.source, line.number, "mapping indentation is not aligned")
            if line.content == "-" or line.content.startswith("- "):
                break
            if line.content.startswith("?"):
                raise _error(self.source, line.number, "explicit YAML keys are unsupported")
            colon = _find_mapping_colon(line.content)
            if colon is None:
                raise _error(self.source, line.number, "mapping entry lacks colon")
            key_raw = line.content[:colon].strip()
            if not key_raw or key_raw == "<<":
                raise _error(self.source, line.number, "invalid or merge mapping key")
            key = _scalar(key_raw, self.source, line.number)
            if not isinstance(key, str):
                raise _error(self.source, line.number, "mapping keys must be strings")
            if key in result:
                raise _error(self.source, line.number, f"duplicate YAML mapping key: {key!r}")
            value_raw = line.content[colon + 1 :].strip()
            if value_raw.startswith(("|", ">")):
                value, index = self._block_scalar(index, indent, value_raw)
            elif value_raw.startswith(("[", "{")):
                value, index = self._flow_value(index, value_raw)
            elif value_raw:
                value = _scalar(value_raw, self.source, line.number)
                index += 1
                if index < len(self.lines) and self.lines[index].indent > indent:
                    raise _error(self.source, self.lines[index].number, "scalar mapping has unexpected child")
            else:
                index += 1
                if index < len(self.lines) and self.lines[index].indent > indent:
                    value, index = self._block(index, self.lines[index].indent)
                else:
                    value = None
            result[key] = value
        return result, index

    def _sequence(self, index: int, indent: int) -> tuple[list[Any], int]:
        result: list[Any] = []
        while index < len(self.lines):
            line = self.lines[index]
            if line.indent < indent:
                break
            if line.indent != indent:
                raise _error(self.source, line.number, "sequence indentation is not aligned")
            if not (line.content == "-" or line.content.startswith("- ")):
                break
            remainder = line.content[1:].strip()
            if not remainder:
                index += 1
                if index < len(self.lines) and self.lines[index].indent > indent:
                    value, index = self._block(index, self.lines[index].indent)
                else:
                    value = None
                result.append(value)
                continue
            if remainder.startswith(("[", "{")):
                value, index = self._flow_value(index, remainder)
                result.append(value)
                continue
            colon = _find_mapping_colon(remainder)
            if colon is not None:
                # Sequence mapping item (``- name: value``), followed by
                # zero or more aligned mapping continuation lines.
                key_raw = remainder[:colon].strip()
                key = _scalar(key_raw, self.source, line.number)
                if not isinstance(key, str) or key == "<<":
                    raise _error(self.source, line.number, "invalid sequence mapping key")
                item: dict[str, Any] = {key: None}
                value_raw = remainder[colon + 1 :].strip()
                index += 1
                if value_raw.startswith(("|", ">")):
                    value, index = self._block_scalar(index - 1, indent, value_raw)
                elif value_raw.startswith(("[", "{")):
                    # Reparse the inline value through the flow collector.
                    value, index = self._flow_value(index - 1, value_raw)
                elif value_raw:
                    value = _scalar(value_raw, self.source, line.number)
                elif index < len(self.lines) and self.lines[index].indent > indent:
                    value, index = self._block(index, self.lines[index].indent)
                else:
                    value = None
                item[key] = value
                if index < len(self.lines) and self.lines[index].indent > indent:
                    child_indent = self.lines[index].indent
                    continuation, index = self._mapping(index, child_indent)
                    for continuation_key, continuation_value in continuation.items():
                        if continuation_key in item:
                            raise _error(self.source, line.number, f"duplicate YAML mapping key: {continuation_key!r}")
                        item[continuation_key] = continuation_value
                result.append(item)
                continue
            value = _scalar(remainder, self.source, line.number)
            index += 1
            if index < len(self.lines) and self.lines[index].indent > indent:
                raise _error(self.source, self.lines[index].number, "scalar sequence item has unexpected child")
            result.append(value)
        return result, index

    def _flow_value(self, index: int, value_raw: str) -> tuple[Any, int]:
        start_line = self.lines[index]
        chunks = [value_raw]
        depth = self._flow_depth(value_raw)
        index += 1
        while depth > 0 and index < len(self.lines):
            chunk = self.lines[index].content
            chunks.append(chunk)
            depth += self._flow_depth(chunk)
            index += 1
        if depth != 0:
            raise _error(self.source, start_line.number, "unterminated flow collection")
        return _FlowParser(" ".join(chunks), self.source, start_line.number).parse(), index

    @staticmethod
    def _flow_depth(value: str) -> int:
        depth = 0
        quote: str | None = None
        escaped = False
        index = 0
        while index < len(value):
            character = value[index]
            if quote == '"':
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    quote = None
                index += 1
                continue
            if quote == "'":
                if character == "'":
                    if index + 1 < len(value) and value[index + 1] == "'":
                        index += 2
                        continue
                    quote = None
                index += 1
                continue
            if character in ("'", '"'):
                quote = character
            elif character in "[{":
                depth += 1
            elif character in "]}":
                depth -= 1
            index += 1
        return depth

    def _block_scalar(self, index: int, parent_indent: int, indicator: str) -> tuple[str, int]:
        line = self.lines[index]
        match = re.fullmatch(r"([|>])([1-9]?)([+-]?)", indicator)
        if match is None:
            raise _error(self.source, line.number, "unsupported block scalar indicator")
        style, explicit_indent, chomping = match.groups()
        index += 1
        raw_lines: list[str] = []
        while index < len(self.lines):
            child = self.lines[index]
            if child.indent <= parent_indent:
                break
            raw_lines.append(child.raw)
            index += 1
        if raw_lines:
            nonempty = [len(raw) - len(raw.lstrip(" ")) for raw in raw_lines if raw.strip()]
            content_indent = parent_indent + int(explicit_indent) if explicit_indent else min(nonempty or [parent_indent + 1])
            values = [raw[content_indent:] if len(raw) >= content_indent else "" for raw in raw_lines]
        else:
            values = []
        if style == "|":
            text = "\n".join(values)
        else:
            folded: list[str] = []
            for value in values:
                if not value:
                    folded.append("\n")
                elif folded and folded[-1] != "\n":
                    folded.append(" ")
                    folded.append(value)
                else:
                    folded.append(value)
            text = "".join(folded)
        if values:
            text += "\n"
        if chomping == "-":
            text = text.rstrip("\n")
        elif chomping != "+":
            text = text.rstrip("\n") + ("\n" if text else "")
        return text, index


def parse_yaml_strict(text: str, *, source: str = "<workflow>") -> Any:
    """Public strict parser used by tests and the governance gate."""

    return StrictYamlParser(text, source=source).parse()


def _read_text(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise OSError(f"unsafe or missing governance input: {path}")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError(f"governance input is not regular: {path}")
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=True) as stream:
            descriptor = -1
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _fail(message: str) -> None:
    raise SystemExit(f"governance-integrity: {message}")


def _strict_shape_equal(actual: Any, expected: Any) -> bool:
    """Compare JSON policy values without bool/int coercion.

    Python considers ``True == 1`` and ``False == 0``.  Ordinary dictionary
    equality would therefore accept a malformed JSON policy that replaces a
    boolean with an integer.  Policy validation needs exact JSON scalar types
    in addition to equal values, recursively through mappings and arrays.
    """

    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual) == set(expected) and all(
            _strict_shape_equal(actual[key], expected[key]) for key in expected
        )
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _strict_shape_equal(actual_value, expected_value)
            for actual_value, expected_value in zip(actual, expected)
        )
    return actual == expected


def _json_pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _load_json(path: Path) -> Any:
    return json.loads(
        _read_text(path), object_pairs_hook=_json_pairs_no_duplicates
    )


def assert_source_inventory() -> None:
    """Reject unregistered root files and symlinked authority inputs."""

    probe = ROOT / "__probe__"
    if probe.exists() or probe.is_symlink():
        _fail("root __probe__ residue is forbidden")
    # A source-only gate must not silently validate a generated/attacker-added
    # root file.  Keep the allow-list explicit; adding a root file requires a
    # reviewed policy update.  ``.git`` is a worktree implementation detail,
    # not a source input.
    try:
        entries = list(ROOT.iterdir())
    except OSError as error:
        _fail(f"cannot enumerate repository root: {error}")
        return
    for entry in entries:
        if entry.name == ".git":
            if entry.is_symlink():
                _fail("repository metadata .git must not be a symlink")
            continue
        if entry.is_symlink():
            _fail(f"repository root contains a symlinked entry: {entry.name}")
            continue
        if not entry.is_dir() and entry.name not in EXPECTED_ROOT_FILES:
            _fail(f"repository root contains an unregistered file: {entry.name}")
    actual_files = {
        entry.name
        for entry in entries
        if entry.name != ".git" and not entry.is_dir() and not entry.is_symlink()
    }
    if actual_files != EXPECTED_ROOT_FILES:
        missing = sorted(EXPECTED_ROOT_FILES - actual_files)
        extra = sorted(actual_files - EXPECTED_ROOT_FILES)
        _fail(f"root file inventory mismatch (missing={missing}, extra={extra})")

    # Cross-check against the tracked index so an ignored/untracked file cannot
    # masquerade as one of the allow-listed inputs.  Worktree archives without
    # a Git directory are rejected rather than weakening the check.
    try:
        result = subprocess.run(
            ["git", "ls-files", "--stage", "-z", "--"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        _fail(f"cannot inspect tracked root inventory: {error}")
        return
    tracked_files: set[str] = set()
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        try:
            header, raw_path = record.split(b"\t", 1)
            mode, _object_id, _stage = header.split(b" ", 2)
            path = raw_path.decode("utf-8")
        except (UnicodeDecodeError, ValueError) as error:
            _fail(f"tracked root inventory contains malformed Git data: {error}")
            continue
        if "/" not in path:
            if mode not in {b"100644", b"100755"}:
                _fail(f"tracked root entry is not a regular file: {path!r}")
            tracked_files.add(path)
    if tracked_files != EXPECTED_ROOT_FILES:
        missing = sorted(EXPECTED_ROOT_FILES - tracked_files)
        extra = sorted(tracked_files - EXPECTED_ROOT_FILES)
        _fail(f"tracked root file inventory mismatch (missing={missing}, extra={extra})")


def _parse_codeowners(text: str) -> list[tuple[str, tuple[str, ...]]]:
    rules: list[tuple[str, tuple[str, ...]]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if any(
            (ord(character) < 0x20 and character not in "\t\r")
            or ord(character) == 0x7F
            for character in line
        ):
            _fail(f"CODEOWNERS line {line_number} contains a control character")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tokens: list[str] = []
        for token in stripped.split():
            if token.startswith("#"):
                break
            tokens.append(token)
        if len(tokens) < 3:
            _fail(
                f"CODEOWNERS line {line_number} must contain a path and two owners"
            )
        pattern, owners = tokens[0], tuple(tokens[1:])
        if not pattern or pattern.startswith(("!", "@")):
            _fail(f"CODEOWNERS line {line_number} has an invalid path pattern")
        if len(set(owners)) != len(owners) or any(
            OWNER_TOKEN.fullmatch(owner) is None for owner in owners
        ):
            _fail(f"CODEOWNERS line {line_number} has duplicate or invalid owners")
        rules.append((pattern, owners))
    if not rules:
        _fail("CODEOWNERS has no active rules")
    return rules


def _validate_codeowners_source() -> None:
    """Require every protected source area to route to both interim owners."""

    path = ROOT / ".github" / "CODEOWNERS"
    try:
        rules = _parse_codeowners(_read_text(path))
    except (OSError, UnicodeError, ValueError) as error:
        _fail(f"CODEOWNERS is unreadable: {error}")
        return
    patterns = {pattern for pattern, _owners in rules}
    missing_patterns = sorted(EXPECTED_CODEOWNER_PATTERNS - patterns)
    if missing_patterns:
        _fail(f"CODEOWNERS omits required protected paths: {missing_patterns}")
    try:
        manifest = _load_json(ROOT / "manifests" / "repository-governance.v1.json")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        _fail(f"cannot load CODEOWNERS owner registry: {error}")
        return
    review = manifest.get("source_review") if isinstance(manifest, dict) else None
    owners = review.get("interim_codeowners") if isinstance(review, dict) else None
    if (
        not isinstance(owners, list)
        or len(owners) < 2
        or any(not isinstance(owner, str) or not owner for owner in owners)
        or len(set(owners)) != len(owners)
    ):
        _fail("governance manifest has no distinct interim CODEOWNER identities")
    required = {f"@{owner}" for owner in owners}
    for pattern, rule_owners in rules:
        missing = sorted(required - set(rule_owners))
        if missing:
            _fail(f"CODEOWNERS rule {pattern!r} omits required owners: {missing}")


def _validate_permissions(value: Any, location: str) -> None:
    if isinstance(value, str):
        if value != "read-all":
            _fail(f"{location} must be read-all or an explicit read-only map")
        return
    if not isinstance(value, dict):
        _fail(f"{location} must be a mapping or read-all")
    for key, permission in value.items():
        if not isinstance(key, str) or not isinstance(permission, str):
            _fail(f"{location} has a non-string permission")
        if key not in KNOWN_PERMISSION_KEYS:
            _fail(f"{location} contains an unknown permission key: {key!r}")
        if permission != "read" and permission != "none":
            _fail(f"{location}.{key} grants {permission!r}; write authority is forbidden")


def _trigger_names(value: Any, location: str) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        if not all(isinstance(item, str) for item in value):
            _fail(f"{location} list must contain event names")
        return set(value)
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            _fail(f"{location} has a non-string event name")
        return set(value)
    _fail(f"{location} must be a mapping, list, or event name")
    return set()


def _validate_triggers(workflow_path: Path, workflow: dict[str, Any]) -> None:
    if "on" not in workflow:
        _fail(f"{workflow_path}: top-level on trigger is required")
    triggers = _trigger_names(workflow["on"], f"{workflow_path}: on")
    if "pull_request_target" in triggers:
        _fail(f"{workflow_path}: pull_request_target is forbidden")
    if workflow_path.name == "governance-integrity.yml":
        required = {"pull_request", "push", "workflow_dispatch"}
        if triggers != required:
            _fail(
                f"{workflow_path}: governance workflow triggers must be exactly "
                "pull_request, push, and workflow_dispatch"
            )
        raw = workflow["on"]
        if not isinstance(raw, dict):
            _fail(f"{workflow_path}: governance triggers must use a mapping")
        for event in ("pull_request", "push"):
            config = raw.get(event)
            if not isinstance(config, dict):
                _fail(f"{workflow_path}: {event} must explicitly configure branches")
            branches = config.get("branches")
            if branches != ["main"] and branches != "main":
                _fail(f"{workflow_path}: {event} must target only main")
            if "paths" in config or "paths-ignore" in config:
                _fail(f"{workflow_path}: governance trigger may not use path filters")


def _safe_local_reference(
    value: str, *, workflow_path: Path, reusable: bool
) -> Path:
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value) or "\\" in value:
        _fail(f"{workflow_path}: local action/workflow path is unsafe: {value!r}")
    pattern = LOCAL_WORKFLOW if reusable else LOCAL_ACTION
    if pattern.fullmatch(value) is None:
        _fail(f"{workflow_path}: local reference is malformed: {value!r}")
    # Reject empty and dot components as well as traversal.  They are
    # semantically redundant to GitHub's path resolver, but accepting them
    # would make the reviewed lexical reference differ from the path that is
    # actually opened (for example ``./actions//action.yml`` or
    # ``./actions/./action.yml``).  Keep the source spelling canonical and
    # make inventory/path comparisons unambiguous.
    components = value[2:].split("/")
    if any(component in {"", ".", ".."} for component in components):
        _fail(f"{workflow_path}: local reference contains traversal: {value!r}")
    target = ROOT / value[2:]
    try:
        target.relative_to(ROOT)
    except ValueError:
        _fail(f"{workflow_path}: local reference escapes repository")
    # Inspect every lexical component before resolving, so a symlink cannot
    # redirect a supposedly local action/workflow outside the source tree.
    current = ROOT
    for component in target.relative_to(ROOT).parts:
        current /= component
        try:
            if current.is_symlink():
                _fail(f"{workflow_path}: local reference contains a symlink: {value!r}")
        except OSError as error:
            _fail(f"{workflow_path}: local reference cannot be inspected: {error}")
    if reusable:
        if not target.is_file():
            _fail(
                f"{workflow_path}: local reusable workflow is missing or unsafe: {value!r}"
            )
    elif not target.is_dir():
        _fail(f"{workflow_path}: local action directory is missing or unsafe: {value!r}")
    return target


def _validate_uses(
    value: Any,
    *,
    workflow_path: Path,
    reusable: bool,
    location: str,
    seen_local: set[Path] | None = None,
) -> None:
    if not isinstance(value, str) or not value or any(character.isspace() for character in value):
        _fail(f"{workflow_path}:{location}: uses must be one immutable scalar")
    if value.startswith("./"):
        target = _safe_local_reference(
            value, workflow_path=workflow_path, reusable=reusable
        )
        _audit_local_reference(
            target,
            workflow_path=workflow_path,
            reusable=reusable,
            seen_local=seen_local if seen_local is not None else set(),
        )
        return
    if ACTION_REF.fullmatch(value) is None:
        # Reusable remote workflows contain a path before @.  Validate the
        # owner/repository prefix and immutable SHA without permitting refs.
        if reusable and "@" in value and FULL_SHA.fullmatch(value.rsplit("@", 1)[1]):
            prefix = value.rsplit("@", 1)[0]
            parts = prefix.split("/")
            if (
                len(parts) == 5
                and REPOSITORY_COMPONENT.fullmatch(parts[0])
                and REPOSITORY_COMPONENT.fullmatch(parts[1])
                and parts[2] == ".github"
                and parts[3] == "workflows"
                and re.fullmatch(r"[A-Za-z0-9_.-]+\.(?:yml|yaml)", parts[4])
                and all(parts)
            ):
                return
        _fail(f"{workflow_path}:{location}: mutable or malformed action reference: {value!r}")


def _audit_local_reference(
    target: Path,
    *,
    workflow_path: Path,
    reusable: bool,
    seen_local: set[Path],
) -> None:
    """Follow local action/workflow references and audit their executable graph."""

    target = target.absolute()
    if target in seen_local:
        return
    seen_local.add(target)
    if reusable:
        try:
            nested = parse_yaml_strict(
                _read_text(target), source=str(target.relative_to(ROOT))
            )
        except (OSError, UnicodeError, YamlParseError) as error:
            _fail(f"{workflow_path}: local reusable workflow is invalid: {error}")
        validate_workflow(target, nested, seen_local=seen_local, nested=True)
        return

    metadata = [target / "action.yml", target / "action.yaml"]
    present = [path for path in metadata if path.exists()]
    if len(present) != 1 or present[0].is_symlink():
        _fail(
            f"{workflow_path}: local action must contain exactly one regular "
            f"action.yml/action.yaml: {target}"
        )
    try:
        model = parse_yaml_strict(
            _read_text(present[0]), source=str(present[0].relative_to(ROOT))
        )
    except (OSError, UnicodeError, YamlParseError) as error:
        _fail(f"{workflow_path}: local action metadata is invalid: {error}")
    if not isinstance(model, dict) or not isinstance(model.get("runs"), dict):
        _fail(f"{workflow_path}: local action metadata has no runs mapping")
    runs = model["runs"]
    using = runs.get("using")
    if not isinstance(using, str) or using not in {
        "composite",
        "node12",
        "node16",
        "node20",
        "docker",
    }:
        _fail(f"{workflow_path}: local action has unsupported runs.using: {using!r}")
    if using != "composite":
        # Node and Docker local actions execute repository-controlled code in
        # a separate runtime.  Without a language/runtime-aware mutation
        # proof, an entrypoint or image could perform a hidden GitHub/source
        # mutation while the workflow YAML appears read-only.  Composite
        # actions are recursively audited through their shell steps below;
        # fail closed for the other action kinds until an equivalent scanner
        # exists.
        _fail(
            f"{workflow_path}: local {using} actions are unsupported by the "
            "source mutation gate; use an audited composite action"
        )
    if using == "composite":
        steps = runs.get("steps")
        if not isinstance(steps, list) or not steps:
            _fail(f"{workflow_path}: composite local action has no steps")
        _validate_step_list(
            workflow_path,
            f"local action {target}",
            steps,
            seen_local=seen_local,
        )
    elif using.startswith("node"):
        main = runs.get("main")
        if not isinstance(main, str) or not main or main.startswith(("/", "\\")):
            _fail(f"{workflow_path}: node local action has unsafe runs.main")
        if ".." in Path(main).parts:
            _fail(f"{workflow_path}: node local action runs.main traverses directories")
        entrypoint = target / main
        if entrypoint.is_symlink() or not entrypoint.is_file():
            _fail(f"{workflow_path}: node local action entrypoint is missing or unsafe")
    elif using == "docker":
        image = runs.get("image")
        if not isinstance(image, str) or not image:
            _fail(f"{workflow_path}: docker local action has no image")


def _command_tokens(command: str) -> Iterable[list[str]]:
    """Yield shell token lists for simple command segments.

    We intentionally split on shell control operators before ``shlex``.  A
    malformed shell fragment is still scanned textually by the caller, so a
    parser failure cannot hide a mutation command.
    """

    for segment in re.split(r"[;&|\n]", command):
        try:
            tokens = shlex.split(segment, comments=False, posix=True)
        except ValueError:
            continue
        if tokens:
            yield tokens


def _shell_command_tokens(
    command: str, *, strip_comments: bool = False
) -> list[list[str]]:
    """Tokenize shell fragments while retaining command boundaries.

    Workflow ``run`` blocks are not executed by this validator, so a full
    shell interpreter would be both unsafe and unnecessarily permissive.  A
    small ``shlex`` scanner is enough to recognize executable names and Git
    options, while preserving quoted ``bash -c '...'``/``os.system`` payloads
    as tokens for the bounded recursive scan below.  Malformed quoting falls
    back to conservative whitespace splitting; it must not hide a mutation.
    """

    normalized = re.sub(r"\\[ \t]*\r?\n", " ", command)
    commands: list[list[str]] = []
    current: list[str] = []
    try:
        lexer = shlex.shlex(
            normalized,
            posix=True,
            punctuation_chars=";&|()\n",
        )
        lexer.whitespace_split = True
        # Keep newline out of ``whitespace`` so punctuation handling emits it
        # as a command boundary (newlines inside quoted strings remain part of
        # that token).
        lexer.whitespace = " \t\r"
        lexer.commenters = "#" if strip_comments else ""
        separators = {";", "&&", "||", "|", "(", ")", "\n"}
        for word in lexer:
            if word in separators:
                if current:
                    commands.append(current)
                    current = []
            else:
                current.append(word)
    except ValueError:
        for segment in re.split(r"(?:\r?\n|&&|\|\||[;|])", normalized):
            if strip_comments:
                segment = re.split(r"(?<!\\)#", segment, maxsplit=1)[0]
            words = re.findall(r"[^\s]+", segment)
            if words:
                commands.append(words)
        return commands
    if current:
        commands.append(current)
    return commands


def _executable_basename(value: str) -> str:
    """Normalize Unix/Windows path-qualified executable names."""

    return value.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()


def _git_invocation_mutates(tokens: list[str], executable_index: int) -> bool:
    """Return whether a tokenized Git invocation has a mutating verb."""

    executable = _executable_basename(tokens[executable_index])
    if executable in GIT_MUTATING_HELPERS:
        return True
    if executable not in GIT_EXECUTABLES:
        return False
    cursor = executable_index + 1
    while cursor < len(tokens):
        argument = tokens[cursor]
        lowered = argument.lower()
        if lowered == "--":
            cursor += 1
            continue
        if lowered in MUTATING_GIT_SUBCOMMANDS:
            return True
        if not argument.startswith("-"):
            # The first non-option is Git's subcommand.  It is either a
            # read-only verb or an unknown extension; do not inspect ordinary
            # positional arguments for a second command.
            return False
        option = lowered.split("=", 1)[0]
        if "=" not in argument and option in MUTATING_GIT_OPTIONS_WITH_ARGS:
            cursor += 2
        else:
            cursor += 1
    return False


def _shell_dynamic_mutates(command: str, *, depth: int) -> bool:
    """Reject dynamic shell forms that can conceal a mutating Git command.

    ``shlex`` intentionally treats variable expansions as opaque words.  That
    is useful for ordinary lexical matching, but it would let constructs such
    as ``x=git; $x push`` or ``git push${IFS}origin`` evade the mutation gate.
    Track simple literal executable assignments across command segments,
    expand the shell's standard ``IFS`` separator for a bounded re-scan, and
    inspect a short newline-spanning window.  Unknown dynamic executables are
    also rejected when followed by a mutating verb: the source cannot prove
    which binary the expansion resolves to.
    """

    if depth > 2:
        return False

    # Field-splitting can concatenate a mutating verb and its arguments into a
    # single token.  Replacing only the exact IFS forms keeps GitHub expression
    # syntax (``${{ ... }}``) untouched.
    if SHELL_IFS_EXPANSION.search(command) and re.search(r"(?i)\bgit(?:\.exe)?\b", command):
        expanded = SHELL_IFS_EXPANSION.sub(" ", command)
        if expanded != command and _contains_mutation(expanded, _depth=depth + 1):
            return True

    # A line break can separate the executable and verb in the token stream,
    # while shell wrappers or continuation-heavy input may still execute it
    # as one command.  Keep the window bounded and never cross shell command
    # separators so this remains deterministic on large run blocks.
    if GIT_NEWLINE_MUTATION.search(command):
        return True

    known_git_variables: dict[str, str] = {}
    for tokens in _shell_command_tokens(command):
        # Track simple literal assignments (including ``export x=git``).  An
        # overwrite with another literal removes the previous executable
        # binding rather than allowing stale state to satisfy a later use.
        for token in tokens:
            assignment = SHELL_ASSIGNMENT.fullmatch(token)
            if assignment is None:
                continue
            name, value = assignment.groups()
            basename = _executable_basename(value)
            if basename in GIT_EXECUTABLES or basename in GIT_MUTATING_HELPERS:
                known_git_variables[name] = value
            else:
                known_git_variables.pop(name, None)
            if any(character.isspace() for character in value) and _contains_mutation(
                value, _depth=depth + 1
            ):
                return True

        for index, token in enumerate(tokens):
            variable = SHELL_VARIABLE.fullmatch(token)
            if variable is None:
                continue
            name = variable.group(1)
            value = known_git_variables.get(name)
            if value is not None:
                if _git_invocation_mutates([value, *tokens[index + 1 :]], 0):
                    return True
                continue

            # Even without a visible assignment, ``$tool push`` is an
            # unresolved executable.  Treat a mutating verb after it as a
            # potential repository mutation rather than guessing the value.
            if _git_invocation_mutates(["git", *tokens[index + 1 :]], 0):
                return True
    return False


def _python_call_end(command: str, start: int, limit: int = 8192) -> int:
    """Find a bounded closing parenthesis for a Python call payload."""

    end = min(len(command), start + limit)
    depth = 1
    quote: str | None = None
    escaped = False
    index = start
    while index < end:
        character = command[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            index += 1
            continue
        if character in ("'", '"'):
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return end


_PYTHON_STRING_LITERAL = re.compile(
    r'''(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')'''
)


def _python_literal_values(payload: str) -> list[str]:
    """Decode bounded Python string literals from a call argument payload."""

    values: list[str] = []
    for match in _PYTHON_STRING_LITERAL.finditer(payload):
        raw = match.group(0)
        try:
            value = ast.literal_eval(raw)
        except (SyntaxError, ValueError, TypeError, MemoryError, RecursionError):
            continue
        if isinstance(value, str):
            values.append(value)
    return values


def _python_call_mutates(command: str, *, depth: int) -> bool:
    """Inspect subprocess/os.system calls for tokenized Git mutations."""

    if depth > 2:
        return False
    for match in PYTHON_COMMAND_CALL.finditer(command):
        end = _python_call_end(command, match.end())
        values = _python_literal_values(command[match.end() : end])
        for index, value in enumerate(values):
            if _git_invocation_mutates(values, index):
                return True
            if any(character.isspace() for character in value) and _contains_mutation(
                value, _depth=depth + 1
            ):
                return True
    return False


def _has_command_invocation(
    commands: Iterable[str], command: str, *, _depth: int = 0
) -> bool:
    """Return whether a shell token stream executes *command*.

    Shell comments are removed before matching, and the expected command must
    begin a command segment (apart from harmless ``NAME=value`` assignments).
    Requiring an invocation boundary prevents a quoted string, ``echo``
    argument, or comment from satisfying a governance gate's required command.
    """

    try:
        expected = shlex.split(command, comments=False, posix=True)
    except ValueError:
        return False
    if not expected:
        return False
    for source in commands:
        for tokens in _shell_command_tokens(source, strip_comments=True):
            width = len(expected)
            # Permit shell variable assignments before the executable, but do
            # not treat arbitrary command arguments such as ``echo python3``
            # as proof that the required validator actually ran.
            start = 0
            while start < len(tokens) and re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[start]
            ):
                start += 1
            if len(tokens) >= start + width and tokens[start : start + width] == expected:
                return True
            # A direct shell wrapper still executes the command, whereas an
            # arbitrary command such as ``echo`` merely prints its spelling.
            # Recognize the bounded, unambiguous ``sh -c``/``bash -c`` form so
            # wrappers cannot become a way to hide a required gate.  The
            # recursive call is depth-limited and receives the already
            # comment-stripped payload.
            if (
                _depth < 2
                and start < len(tokens)
                and _executable_basename(tokens[start]) in {
                    "sh",
                    "bash",
                    "dash",
                    "zsh",
                    "ksh",
                }
            ):
                try:
                    command_index = tokens.index("-c", start + 1)
                except ValueError:
                    command_index = -1
                if (
                    command_index >= 0
                    and command_index + 1 < len(tokens)
                    and _has_command_invocation(
                        [tokens[command_index + 1]],
                        command,
                        _depth=_depth + 1,
                    )
                ):
                    return True
    return False


def _contains_mutation(command: str, *, _depth: int = 0) -> bool:
    # Inspect each physical line first so the common case is O(n) even for
    # large qualification scripts.  The text patterns deliberately cover
    # quoted/Python forms that shell tokenization cannot reliably understand.
    for line in command.splitlines():
        if (
            GH_MUTATION.search(line)
            or REST_MUTATION.search(line)
            or DIRECT_GITHUB_MUTATION.search(line)
            or PYTHON_GITHUB_MUTATION.search(line)
            or PYTHON_GIT_MUTATION.search(line)
        ):
            return True
    if _python_call_mutates(command, depth=_depth):
        return True
    if _shell_dynamic_mutates(command, depth=_depth):
        return True

    # Normalize shell line continuations, then inspect each command segment.
    for tokens in _shell_command_tokens(command):
        for index, token in enumerate(tokens):
            if _git_invocation_mutates(tokens, index):
                return True
        # A workflow may pass a shell fragment through ``bash -c``/``sh -c``;
        # ``shlex`` preserves that quoted fragment as one token.  Recurse only
        # into bounded whitespace-bearing tokens so this remains linear on
        # ordinary command text and cannot recurse indefinitely.
        if _depth < 2:
            for token in tokens:
                if (
                    any(character.isspace() for character in token)
                    and "git" in token.lower()
                    and _contains_mutation(token, _depth=_depth + 1)
                ):
                    return True
    return False


def _reject_continue_on_error(value: Any, location: str) -> None:
    # Do not let a quoted scalar or expression re-enable failure masking.
    if (
        value is True
        or (type(value) is str and value == "true")
        or (type(value) is str and value.startswith("${{"))
    ):
        _fail(f"{location} masks failures with continue-on-error")


ALLOWED_GATE_CONDITIONS = frozenset({"always()", "failure()"})


def _validate_condition(value: Any, location: str) -> None:
    """Allow only explicit diagnostic/cleanup conditions.

    Arbitrary job/step expressions (especially ``false`` or event-dependent
    predicates) can silently skip a required status context while GitHub still
    reports the skipped job as successful.  ``always()`` and ``failure()`` are
    the two narrow forms used by this repository for unconditional artifact
    collection/diagnostics and are therefore the only permitted conditions.
    """

    if not isinstance(value, str) or value not in ALLOWED_GATE_CONDITIONS:
        _fail(f"{location} has a conditional skip; only always()/failure() are allowed")


def _validate_step_condition(value: Any, step: dict[str, Any], location: str) -> None:
    """Validate a step condition and require a diagnostic/cleanup shape."""

    _validate_condition(value, location)
    name = step.get("name", "")
    name = name.lower() if isinstance(name, str) else ""
    uses = step.get("uses")
    artifact_upload = (
        isinstance(uses, str)
        and uses.lower().startswith("actions/upload-artifact@")
    )
    diagnostic_name = any(
        marker in name
        for marker in ("artifact", "diagnostic", "restore", "cleanup", "collect")
    )
    if value == "failure()":
        if not artifact_upload or "diagnostic" not in name:
            _fail(
                f"{location} failure() is reserved for diagnostic artifact collection"
            )
    elif not artifact_upload and not diagnostic_name:
        _fail(
            f"{location} always() is reserved for cleanup or diagnostic artifact collection"
        )


def _validate_step_list(
    workflow_path: Path,
    job_id: str,
    steps: Any,
    *,
    seen_local: set[Path] | None = None,
) -> None:
    if not isinstance(steps, list) or not steps:
        _fail(f"{workflow_path}: {job_id} has no steps")
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            _fail(f"{workflow_path}: job {job_id} step {index} is not a mapping")
        if "uses" in step and "run" in step:
            _fail(f"{workflow_path}: job {job_id} step {index} has both uses and run")
        if "continue-on-error" in step:
            _reject_continue_on_error(
                step["continue-on-error"], f"{workflow_path}: job {job_id} step {index}"
            )
        if "if" in step:
            _validate_step_condition(
                step["if"],
                step,
                f"{workflow_path}: job {job_id} step {index}",
            )
        if "permissions" in step:
            _validate_permissions(step["permissions"], f"{workflow_path}: job {job_id} step {index} permissions")
        if "uses" in step:
            _validate_uses(
                step["uses"],
                workflow_path=workflow_path,
                reusable=False,
                location=f"job {job_id} step {index}",
                seen_local=seen_local,
            )
            if step["uses"].lower().startswith("actions/checkout@"):
                with_map = step.get("with", {})
                persist_credentials = (
                    with_map.get("persist-credentials")
                    if isinstance(with_map, dict)
                    else None
                )
                if not (
                    persist_credentials is False
                    or (
                        type(persist_credentials) is str
                        and persist_credentials == "false"
                    )
                ):
                    _fail(f"{workflow_path}: checkout step {index} must set persist-credentials: false")
        if "run" in step:
            if not isinstance(step["run"], str):
                _fail(f"{workflow_path}: job {job_id} step {index} run must be a string")
            if _contains_mutation(step["run"]):
                _fail(f"{workflow_path}: job {job_id} step {index} contains a repository mutation command")
        # A step with neither uses nor run has no executable semantics and is
        # usually a malformed/ambiguous source declaration.
        if "uses" not in step and "run" not in step:
            _fail(f"{workflow_path}: job {job_id} step {index} has neither uses nor run")


def _validate_steps(
    workflow_path: Path,
    job_id: str,
    job: dict[str, Any],
    *,
    seen_local: set[Path] | None = None,
) -> None:
    if "permissions" in job:
        _validate_permissions(
            job["permissions"], f"{workflow_path}: job {job_id} permissions"
        )
    if "continue-on-error" in job:
        _reject_continue_on_error(
            job["continue-on-error"], f"{workflow_path}: job {job_id}"
        )
    if "uses" in job:
        if "steps" in job:
            _fail(f"{workflow_path}: reusable job {job_id} cannot also define steps")
        _validate_uses(
            job["uses"],
            workflow_path=workflow_path,
            reusable=True,
            location=f"job {job_id}",
            seen_local=seen_local,
        )
        if job.get("secrets") == "inherit":
            _fail(f"{workflow_path}: reusable job {job_id} may not inherit secrets")
        return
    _validate_step_list(
        workflow_path, f"job {job_id}", job.get("steps"), seen_local=seen_local
    )


def validate_workflow(
    path: Path,
    model: Any,
    *,
    seen_local: set[Path] | None = None,
    nested: bool = False,
) -> list[str]:
    """Validate one parsed workflow; return its check contexts."""

    if seen_local is None:
        seen_local = set()
    if not isinstance(model, dict):
        _fail(f"{path}: workflow root must be a mapping")
    unknown_keys = sorted(set(model) - KNOWN_WORKFLOW_KEYS)
    if unknown_keys:
        _fail(f"{path}: workflow has unknown top-level key(s): {unknown_keys}")
    name = model.get("name")
    if not isinstance(name, str) or not name.strip():
        _fail(f"{path}: workflow name is required")
    if path.name == "governance-integrity.yml":
        if name != "governance-integrity":
            _fail(f"{path}: governance workflow name is not canonical")
    _validate_triggers(path, model)
    if "permissions" not in model:
        _fail(f"{path}: explicit top-level permissions are required")
    _validate_permissions(model["permissions"], f"{path}: top-level permissions")
    if path.name == "governance-integrity.yml" and model["permissions"] != {
        "contents": "read"
    }:
        _fail(f"{path}: governance workflow permissions must be exactly contents: read")
    jobs = model.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        _fail(f"{path}: jobs must be a non-empty mapping")
    if path.name == "governance-integrity.yml" and set(jobs) != {
        "governance_integrity"
    }:
        _fail(f"{path}: governance workflow must have exactly one canonical job")
    contexts: list[str] = []
    for job_id, job in jobs.items():
        if not isinstance(job_id, str) or not isinstance(job, dict):
            _fail(f"{path}: jobs must map string IDs to mappings")
        if "if" in job:
            _fail(f"{path}: job {job_id} may not be conditional")
        _validate_steps(path, job_id, job, seen_local=seen_local)
        job_name = job.get("name", job_id)
        if not isinstance(job_name, str) or not job_name.strip():
            _fail(f"{path}: job {job_id} has an invalid name")
        contexts.append(f"{name} / {job_name}")
    if path.name == "governance-integrity.yml":
        runs = [
            step.get("run", "")
            for step in jobs["governance_integrity"].get("steps", [])
            if isinstance(step, dict) and "if" not in step
        ]
        required_commands = (
            "python3 tools/validate_governance_integrity.py",
            "python3 tools/validate_repository.py",
            "python3 tools/validate_project_truth.py",
            "cargo fmt --all --check",
            "cargo check --workspace --all-targets --locked",
            "cargo clippy --workspace --all-targets --locked -- -D warnings",
            "cargo test --workspace --all-targets --locked",
        )
        executable_runs = [value for value in runs if isinstance(value, str)]
        missing_commands = [
            command
            for command in required_commands
            if not _has_command_invocation(executable_runs, command)
        ]
        if missing_commands:
            _fail(f"{path}: governance workflow omits required gate commands: {missing_commands}")
    return contexts


def _validate_contract(contract: Any) -> list[str]:
    if not isinstance(contract, dict):
        _fail("governance contract must be a mapping")
    if contract.get("schema") != "trillionnium.desktop.repository-governance.v1":
        _fail("unexpected governance contract schema")
    if contract.get("work_package") != "D0T-03":
        _fail("governance contract must bind D0T-03")
    if contract.get("status") != "SOURCE_BOOTSTRAP_READY_REPOSITORY_SETTINGS_REQUIRED":
        _fail("governance contract must remain source-only")
    main_branch = contract.get("main_branch")
    if not isinstance(main_branch, dict):
        _fail("governance main_branch policy must be a mapping")
    expected_main_branch = {
        "name": "main",
        "pull_request_required": True,
        "strict_required_checks": True,
        "force_push_allowed": False,
        "deletion_allowed": False,
        "linear_history_required": True,
        "administrator_bypass_allowed": False,
    }
    if not _strict_shape_equal(main_branch, expected_main_branch):
        _fail("governance main_branch policy is incomplete or weakened")
    review = contract.get("review")
    expected_review = {
        "minimum_distinct_approver_identities": 2,
        "dismiss_stale_approvals": True,
        "approval_after_latest_push": True,
        "code_owner_review_required": True,
        "all_conversations_resolved": True,
        "author_self_approval_counts": False,
        "author_self_merge_allowed": False,
        "organization_team_codeowners_required": True,
    }
    if not _strict_shape_equal(review, expected_review):
        _fail("governance review policy is incomplete or weakened")
    actions = contract.get("actions")
    expected_actions = {
        "default_workflow_permissions": "read",
        "actions_may_approve_pull_requests": False,
        "source_mutating_workflows_allowed": False,
        "mutable_external_action_refs_allowed": False,
        "pull_request_target_allowed": False,
    }
    if not _strict_shape_equal(actions, expected_actions):
        _fail("governance Actions policy is incomplete or weakened")
    release = contract.get("release")
    expected_release = {
        "protected_environment": "production",
        "minimum_independent_approvers": 2,
        "source_author_may_approve_release": False,
        "signing_key_available_to_pull_request_workflows": False,
        "signing_and_source_authority_separated": True,
    }
    if not _strict_shape_equal(release, expected_release):
        _fail("governance release policy is incomplete or weakened")
    required_workflows = contract.get("required_workflows")
    if (
        not isinstance(required_workflows, list)
        or required_workflows != list(EXPECTED_REQUIRED_WORKFLOWS)
    ):
        _fail("required_workflows must match the committed workflow registry")
    ceiling = contract.get("claim_ceiling")
    if not isinstance(ceiling, dict) or set(ceiling) != {
        "source_contract_proves_live_repository_settings",
        "source_contract_proves_independent_human_review",
        "source_contract_proves_signing_key_custody",
        "source_contract_proves_release_readiness",
    } or any(type(value) is not bool or value for value in ceiling.values()):
        _fail("governance claim ceiling must explicitly contain only false claims")
    required = contract.get("required_status_contexts")
    if (
        not isinstance(required, list)
        or not required
        or not all(isinstance(item, str) for item in required)
    ):
        _fail("required_status_contexts must be a non-empty string list")
    if len(set(required)) != len(required) or set(required) != EXPECTED_REQUIRED_CONTEXTS:
        _fail("required_status_contexts must match the committed check registry")
    dynamic = contract.get("dynamic_acceptance_required")
    if (
        not isinstance(dynamic, list)
        or len(dynamic) != len(set(dynamic))
        or set(dynamic) != EXPECTED_DYNAMIC_ACCEPTANCE
    ):
        _fail("dynamic_acceptance_required must match the bounded acceptance corpus")
    return required


def _validate_manifest_parity(contract: dict[str, Any]) -> None:
    """Bind the legacy source manifest to the reviewed governance contract."""

    manifest_path = ROOT / "manifests" / "repository-governance.v1.json"
    try:
        manifest = _load_json(manifest_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        _fail(f"legacy governance manifest is unreadable: {error}")
    if not isinstance(manifest, dict):
        _fail("legacy governance manifest must be a mapping")
    for key in ("schema", "work_package", "status"):
        if not _strict_shape_equal(manifest.get(key), contract.get(key)):
            _fail(f"legacy manifest and governance contract {key} diverge")
    branch = manifest.get("main_branch")
    if not isinstance(branch, dict):
        _fail("legacy governance manifest main_branch is missing")
    contract_branch = contract.get("main_branch")
    if not isinstance(contract_branch, dict):
        _fail("governance contract main_branch is missing")
    branch_policy_keys = {
        "name",
        "pull_request_required",
        "strict_required_checks",
        "force_push_allowed",
        "deletion_allowed",
        "linear_history_required",
        "administrator_bypass_allowed",
    }
    if set(branch) != branch_policy_keys | {"required_workflows"}:
        _fail("legacy manifest main_branch policy has unknown or missing keys")
    if any(
        not _strict_shape_equal(branch.get(key), contract_branch.get(key))
        for key in branch_policy_keys
    ):
        _fail("legacy manifest and governance contract main_branch policy diverge")
    manifest_workflows = branch.get("required_workflows")
    if not _strict_shape_equal(manifest_workflows, contract.get("required_workflows")):
        _fail("legacy manifest and governance contract required_workflows diverge")
    manifest_dynamic = manifest.get("dynamic_acceptance_required")
    if not _strict_shape_equal(manifest_dynamic, contract.get("dynamic_acceptance_required")):
        _fail("legacy manifest and governance contract dynamic acceptance diverge")

    contract_review = contract.get("review")
    manifest_review = manifest.get("source_review")
    if not isinstance(contract_review, dict) or not isinstance(manifest_review, dict):
        _fail("legacy manifest and governance contract review policy is missing")
    review_mapping = {
        "minimum_distinct_approver_identities": "minimum_distinct_approver_identities",
        "stale_approvals_dismissed_required": "dismiss_stale_approvals",
        "approval_after_latest_push_required": "approval_after_latest_push",
        "code_owner_review_required": "code_owner_review_required",
        "all_conversations_resolved_required": "all_conversations_resolved",
        "author_self_approval_counts": "author_self_approval_counts",
        "author_self_merge_allowed": "author_self_merge_allowed",
        "organization_team_codeowners_required_for_closure": "organization_team_codeowners_required",
    }
    if any(
        not _strict_shape_equal(
            manifest_review.get(manifest_key), contract_review.get(contract_key)
        )
        for manifest_key, contract_key in review_mapping.items()
    ):
        _fail("legacy manifest and governance contract review policy diverge")
    if set(manifest_review) != set(review_mapping) | {"interim_codeowners"}:
        _fail("legacy manifest review policy has unknown or missing keys")

    for section in ("actions", "release"):
        if not _strict_shape_equal(manifest.get(section), contract.get(section)):
            _fail(f"legacy manifest and governance contract {section} policy diverge")


def _workflow_inventory() -> list[Path]:
    """Return the exact, symlink-free workflow inventory.

    ``Path.glob('*.yml')`` only inspects one directory level and silently
    ignores nested workflow files.  A nested or newly-added workflow can
    therefore bypass the reviewed registry.  Walk the complete tree, reject
    symlink/non-regular entries, and require an exact path set against the
    contract's registry.
    """

    if WORKFLOW_ROOT.is_symlink() or not WORKFLOW_ROOT.is_dir():
        _fail(f"workflow root is missing or symlinked: {WORKFLOW_ROOT}")
    files: list[Path] = []
    for current, directory_names, file_names in os.walk(
        WORKFLOW_ROOT, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        safe_directories: list[str] = []
        for name in directory_names:
            path = current_path / name
            if path.is_symlink() or not path.is_dir():
                _fail(f"workflow inventory contains an unsafe directory: {path}")
            safe_directories.append(name)
        directory_names[:] = safe_directories
        for name in file_names:
            path = current_path / name
            if path.is_symlink() or not path.is_file():
                _fail(f"workflow inventory contains an unsafe file: {path}")
            if path.suffix.lower() not in {".yml", ".yaml"}:
                _fail(f"workflow directory contains an unregistered file: {path}")
            files.append(path)
    actual = {
        path.relative_to(ROOT).as_posix()
        for path in files
    }
    expected = set(EXPECTED_REQUIRED_WORKFLOWS)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        _fail(f"workflow inventory mismatch (missing={missing}, extra={extra})")
    return sorted(files)


def main() -> int:
    try:
        contract = _load_json(CONTRACT_PATH)
        required_contexts = _validate_contract(contract)
        _validate_manifest_parity(contract)
        assert_source_inventory()
        _validate_codeowners_source()
        files = _workflow_inventory()
        contexts: list[str] = []
        for path in files:
            text = _read_text(path)
            model = parse_yaml_strict(text, source=str(path.relative_to(ROOT)))
            contexts.extend(validate_workflow(path, model))
        duplicates = sorted({context for context in contexts if contexts.count(context) > 1})
        if duplicates:
            _fail(f"ambiguous duplicate check contexts: {duplicates}")
        missing = sorted(set(required_contexts) - set(contexts))
        if missing:
            _fail(f"required status contexts are not implemented: {missing}")
        print(
            json.dumps(
                {
                    "schema": "trillionnium.desktop.governance-integrity-result.v1",
                    "status": "PASS_SOURCE_POLICY_ONLY",
                    "workflow_count": len(files),
                    "check_context_count": len(contexts),
                    "required_status_contexts": required_contexts,
                    "audited_workflows": [str(path.relative_to(ROOT)) for path in files],
                    "live_repository_settings_proven": False,
                    "independent_human_review_proven": False,
                    "signing_key_custody_proven": False,
                    "release_readiness_proven": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, YamlParseError, ValueError) as error:
        _fail(str(error))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
