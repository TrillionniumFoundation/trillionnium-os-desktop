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
    # Worktree/index/ref and transport operations which can alter the
    # checkout or invoke a user-controlled helper.  Keep the set explicit so
    # a newly introduced verb is not silently treated as read-only.
    "restore",
    "rm",
    "mv",
    "stash",
    "apply",
    "am",
    "worktree",
    "switch",
    "submodule",
    "remote",
    "notes",
    "reflog",
    "update-index",
    "filter-branch",
    "filter-repo",
    "fast-import",
    "maintenance",
    "gc",
    "replace",
    "repack",
    "prune",
    "init",
    "bisect",
    "format-patch",
    "bundle",
    "pack-refs",
    "index-pack",
    "mktag",
    "checkout-index",
    "read-tree",
    "write-tree",
    "symbolic-ref",
    "update-server-info",
}
# Git verbs which are intentionally used by the qualification workflows and
# do not update refs in the checked-out repository.  The source gate is not a
# shell interpreter, so an unknown verb must never be treated as read-only:
# callers can extend this allow-list only with a reviewed policy change.
# ``clone``, ``checkout`` and ``archive`` are retained because the permanent
# qualification jobs use them for disposable /tmp trees or tar streams; they
# are not an allowance to mutate the source checkout.
GIT_READ_ONLY_SUBCOMMANDS = frozenset(
    {
        "archive",
        "cat-file",
        "check-attr",
        "check-ignore",
        "check-mailmap",
        "check-ref-format",
        "describe",
        "diff",
        "diff-files",
        "diff-index",
        "diff-tree",
        "for-each-ref",
        "help",
        "hash-object",
        "log",
        "ls-files",
        "ls-tree",
        "merge-base",
        "name-rev",
        "rev-list",
        "rev-parse",
        "show",
        "show-ref",
        "status",
        "verify-commit",
        "verify-pack",
        "verify-tag",
        "whatchanged",
        # These are used by the exact-pin and D2I qualification jobs.  They
        # operate on disposable external trees or ephemeral fetch metadata,
        # not protected source/promotion refs. ``repository_write: false`` in
        # the D2I contract is scoped to that remote/protected boundary; a
        # local fetch is intentionally the only checkout-state exception.
        "clone",
        "checkout",
        "fetch",
    }
)
# Options which can write files or invoke an external pager/helper even when
# the Git verb itself is normally read-only. Dynamic option names are also
# rejected by the invocation checker below.
GIT_SIDE_EFFECT_OPTIONS = frozenset({"--output", "-o", "--ext-diff", "--textconv", "--paginate"})
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
        "--upload-pack",
        "--receive-pack",
    }
)
GIT_EXECUTABLES = frozenset({"git", "git.exe"})
GIT_MUTATING_HELPERS = frozenset(
    {
        "git-branch",
        "git-branch.exe",
        "git-checkout",
        "git-checkout.exe",
        "git-clean",
        "git-clean.exe",
        "git-commit",
        "git-commit.exe",
        "git-config",
        "git-config.exe",
        "git-merge",
        "git-merge.exe",
        "git-mv",
        "git-mv.exe",
        "git-rebase",
        "git-rebase.exe",
        "git-push",
        "git-push.exe",
        "git-receive-pack",
        "git-receive-pack.exe",
        "git-reset",
        "git-reset.exe",
        "git-restore",
        "git-restore.exe",
        "git-rm",
        "git-rm.exe",
        "git-send-pack",
        "git-send-pack.exe",
        "git-stash",
        "git-stash.exe",
        "git-tag",
        "git-tag.exe",
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
PYTHON_HTTP_REQUEST = re.compile(
    r"(?<![A-Za-z0-9_.])(?:requests|httpx)\.request\s*\(", re.I
)
PYTHON_HTTP_MUTATION_METHOD = re.compile(
    r"(?i)\b(?:post|put|patch|delete)\b"
)
PYTHON_URLREQUEST_CALL = re.compile(
    r"(?<![A-Za-z0-9_.])urllib\.request\.(?:urlopen|Request)\s*\(", re.I
)
PYTHON_HTTP_MUTATING_CALL = re.compile(
    r"(?<![A-Za-z0-9_.])(?:requests|httpx)\.(?:post|put|patch|delete)\s*\(",
    re.I,
)
PYTHON_HTTP_ALIAS_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:requests|httpx)\.request\b"
)
PYTHON_HTTP_ALIAS_IMPORT = re.compile(
    r"(?i)\bfrom\s+(?:requests|httpx)\s+import\s+request(?:\s+as\s+([A-Za-z_][A-Za-z0-9_]*))?"
)
PYTHON_SESSION_REQUEST = re.compile(
    r"(?i)\b(?:(?:requests|httpx)\.)?(?:Session|Client)\s*\([^\n]{0,512}\)\s*\.request\s*\("
)
PYTHON_SESSION_MUTATING_CALL = re.compile(
    r"(?i)\b(?:(?:requests|httpx)\.)?(?:Session|Client)\s*\([^\n]{0,512}\)\s*\."
    r"(?:post|put|patch|delete)\s*\("
)
PYTHON_SESSION_ALIAS_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:(?:requests|httpx)\.)?(?:Session|Client)\s*\("
)
PYTHON_SESSION_ALIAS_IMPORT = re.compile(
    r"(?i)\bfrom\s+(?:requests|httpx)\s+import\s+(Session|Client)"
    r"(?:\s+as\s+([A-Za-z_][A-Za-z0-9_]*))?"
)
PYTHON_HTTP_MUTATING_ALIAS_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
    r"(?:(?:requests|httpx)\.(?:post|put|patch|delete)|urllib\.request\.urlopen)\b"
)
PYTHON_HTTP_MUTATING_ALIAS_IMPORT = re.compile(
    r"(?i)\bfrom\s+(?:requests|httpx)\s+import\s+"
    r"(post|put|patch|delete)(?:\s+as\s+([A-Za-z_][A-Za-z0-9_]*))?"
)
PYTHON_URLOPEN_ALIAS_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*urllib\.request\.urlopen\b"
)
PYTHON_URLOPEN_ALIAS_IMPORT = re.compile(
    r"(?i)\bfrom\s+urllib\.request\s+import\s+urlopen"
    r"(?:\s+as\s+([A-Za-z_][A-Za-z0-9_]*))?"
)
PYTHON_REQUEST_CLASS_ALIAS_IMPORT = re.compile(
    r"(?i)\bfrom\s+urllib\.request\s+import\s+Request"
    r"(?:\s+as\s+([A-Za-z_][A-Za-z0-9_]*))?"
)
PYTHON_GETATTR_PROCESS = re.compile(
    r"(?i)\bgetattr\s*\(\s*(?:os|subprocess)\s*,\s*['\"](?:system|popen|run|call|Popen|check_call|check_output|getoutput|getstatusoutput|exec[a-z0-9_]*|spawn[a-z0-9_]*|fork|forkpty)['\"]\s*\)\s*\("
)
PYTHON_PROCESS_ALIAS_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*((?:subprocess\.(?:run|call|Popen|check_call|check_output|getoutput|getstatusoutput|exec[a-z0-9_]*))|(?:os\.(?:system|popen|exec[a-z0-9_]*|spawn[a-z0-9_]*|posix_spawn[a-z0-9_]*|startfile|fork|forkpty)))\b"
)
PYTHON_PROCESS_ALIAS_IMPORT = re.compile(
    r"(?i)\bfrom\s+(subprocess|os)\s+import\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+as\s+([A-Za-z_][A-Za-z0-9_]*))?"
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
    r"subprocess\.(?:run|call|Popen|check_call|check_output|getoutput|getstatusoutput|exec[a-z0-9_]*)|"
    r"os\.(?:system|popen|exec[a-z0-9_]*|spawn[a-z0-9_]*|posix_spawn[a-z0-9_]*|startfile|fork|forkpty)|system"
    r")\s*\("
)
# Shell expansion can hide an otherwise tokenized Git executable from the
# bounded command scanner.  Keep these recognizers deliberately narrow and
# fail closed: a workflow that constructs a Git command dynamically is not a
# source-level proof that the command is read-only.
SHELL_VARIABLE = re.compile(r"^\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?$")
SHELL_ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)
# Match both braced and unbraced IFS forms even when punctuation follows
# (``${IFS}-X`` is a common field-splitting spelling).  The negative
# lookahead prevents a prefix match inside a longer variable name.
SHELL_IFS_EXPANSION = re.compile(r"(?:\$\{IFS\}|\$IFS(?![A-Za-z0-9_]))")
# A command-position expansion cannot be proven to be a read-only executable
# without evaluating the shell.  Keep this separate from ordinary argument
# expansion: the workflows intentionally interpolate SHA/path arguments.
SHELL_PARAMETER_EXPANSION = re.compile(
    r"(?:\$\{[^}\n]*\}|\$\([^)\n]*\)|\$[A-Za-z_][A-Za-z0-9_]*|`[^`\n]*`)",
)
SHELL_ARRAY_EXPANSION = re.compile(
    r"\$\{?[A-Za-z_][A-Za-z0-9_]*\[(?:@|\*)\](?:[^}]*)?\}?",
)
SHELL_FUNCTION_DEFINITION = re.compile(
    r"(?m)(?:^|[;&|\n])\s*(?:function\s+)?[A-Za-z_][A-Za-z0-9_]*\s*\(\s*\)\s*\{",
)
SHELL_CONFIG_ASSIGNMENT = re.compile(
    r"(?im)(?:^|[;&|]\s*)"
    r"(?:(?:env|export|declare|local|readonly|typeset)\b[^\n;&|]*\s+)?"
    # PATH can redirect a literal ``git`` to a runner-controlled helper;
    # every GIT_* variable can alter config, transports, object stores, or
    # hooks. Treat both classes as unsafe environment authority.
    r"(?:PATH|GIT_[A-Za-z0-9_]*)\s*=",
)
SHELL_SOURCE_COMMAND = re.compile(
    # ``{ ...; }`` opens a command list but is not one of the ordinary
    # punctuation separators handled by the first-generation recognizer.
    # Include braces here so a sourced script inside a function or brace
    # group cannot hide behind the group opener.
    r"(?m)(?:^|[;&|{}\n]\s*)(?:source|\.)\s+(?![=])(?P<path>[^\s;&|]+)"
)
SHELL_ALIAS_COMMAND = re.compile(
    r"(?m)(?:^|[;&|\n]\s*)alias(?:\s+|$)"
)
SHELL_FUNCTION_WITH_GIT = re.compile(
    r"(?is)(?:^|[;&|\n{}])\s*"
    r"(?:function\s+[A-Za-z_][A-Za-z0-9_]*(?:\s*\(\s*\))?|"
    r"[A-Za-z_][A-Za-z0-9_]*\s*\(\s*\))\s*\{"
    r"[^}]{0,4096}\bgit(?:\.exe)?\b"
)
SHELL_DYNAMIC_HTTP_METHOD = re.compile(
    r"(?i)\b(?:curl|wget)\b[^\n]*?(?:--request|--method|-X)"
    r"(?:\s+|=\s*)['\"]?\$(?:\{?[A-Za-z_][A-Za-z0-9_]*\}?|\{)"
)
SHELL_COMMAND_SUBSTITUTION = re.compile(r"\$\(([^\n]{0,8192})\)|`([^`\n]{0,8192})`")
SHELL_COMMAND_SUBSTITUTION_EXECUTABLE = re.compile(
    # A substitution can occupy command position at the start of a segment,
    # after a pipeline/list separator, or after a compound-command keyword.
    # Include ``then``/``do``/``else``/``elif`` and shell negation so forms
    # such as ``if true; then $(printf git) push; fi`` cannot hide a dynamic
    # executable behind the control-flow token.  Whitespace after a segment
    # boundary is permitted because process-substitution payloads are often
    # extracted with a leading space.
    r"(?im)(?:^|[;&|]\s*|(?:if|while|until|then|do|else|elif)\s+)\s*"
    r"(?:!\s+)?(?:\$\([^()\n]{0,8192}\)|`[^`\n]{0,8192}`)(?:\s|$)"
)
GH_EXECUTABLES = frozenset({"gh", "gh.exe"})
HTTP_EXECUTABLES = frozenset({"curl", "curl.exe", "wget", "wget.exe"})
PYTHON_EXEC_METHODS = frozenset(
    {
        "execl",
        "execle",
        "execlp",
        "execlpe",
        "execv",
        "execve",
        "execvp",
        "execvpe",
        "fexecve",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
        "posix_spawn",
        "posix_spawnp",
        "startfile",
        # Process creation APIs do not carry a command argv themselves, but
        # they still transfer execution to a child (or fork the runner).  A
        # source-level policy cannot prove that the child cannot mutate the
        # checkout, so keep them in the fail-closed process set.
        "fork",
        "forkpty",
    }
)
PYTHON_PROCESS_METHODS = frozenset(
    {
        "run",
        "call",
        "popen",
        "check_call",
        "check_output",
        "getoutput",
        "getstatusoutput",
        *PYTHON_EXEC_METHODS,
    }
)
PYTHON_SUBPROCESS_METHODS = frozenset(
    {
        "run",
        "call",
        "Popen",
        "check_call",
        "check_output",
        "getoutput",
        "getstatusoutput",
    }
)
PYTHON_OS_METHODS = frozenset(
    {
        "system",
        "popen",
        *PYTHON_EXEC_METHODS,
        "fork",
        "forkpty",
    }
)
# ``subprocess`` exposes a large keyword surface.  Keep only the options whose
# values do not install a second executable, mutate the inherited environment,
# or run arbitrary Python before ``exec``.  In particular, ``preexec_fn`` and
# unknown/``**kwargs`` forms are not a source-level read-only proof.
PYTHON_SAFE_PROCESS_KEYWORDS = frozenset(
    {
        "args",
        "argv",
        "cmd",
        "command",
        "shell",
        "env",
        "executable",
        "cwd",
        "stdin",
        "stdout",
        "stderr",
        "capture_output",
        "timeout",
        "input",
        "check",
        "encoding",
        "errors",
        "text",
        "universal_newlines",
        "bufsize",
        "close_fds",
        "restore_signals",
        "start_new_session",
        "pass_fds",
        "creationflags",
        "startupinfo",
    }
)
HTTP_METHOD_FLAGS = frozenset({"-X", "--request", "--method"})
HTTP_DATA_FLAGS = frozenset(
    {
        "-d",
        "--data",
        "--data-raw",
        "--data-binary",
        "--data-urlencode",
        "--json",
        "--form",
        "-F",
        "--form-string",
        "--upload-file",
        "--config",
        "--config-file",
        "-K",
        "--post-data",
        "--post-file",
        "--body-data",
        "--body-file",
        "-t",
        "-T",
    }
)
SHELL_WRAPPERS = frozenset(
    {
        "env",
        "command",
        "builtin",
        "exec",
        "sudo",
        "timeout",
        "nice",
        "nohup",
        "time",
    }
)
# Command-graph wrappers which can execute a second command without looking
# like a conventional ``env``/``sudo`` prefix.  They stay out of
# ``SHELL_WRAPPERS`` because their argument grammars are different (for
# example ``flock`` consumes a lock path before the command and ``find`` uses
# ``-exec``).  ``_shell_graph_wrapper_mutates`` handles those grammars below.
SHELL_GRAPH_WRAPPERS = frozenset(
    {
        "xargs",
        "find",
        "parallel",
        "busybox",
        "setsid",
        "flock",
        "chroot",
        "nsenter",
        "unshare",
        "systemd-run",
        "daemonize",
        "trap",
        "at",
        "batch",
        "watch",
        "crontab",
        # Bash's ``coproc [NAME] COMMAND`` creates a second asynchronous
        # command graph.  Keep it in the graph-wrapper set so both the
        # unnamed and named forms are audited recursively.
        "coproc",
    }
)
SHELL_INTERPRETERS = frozenset({"bash", "sh", "dash", "zsh", "ksh", "git-shell"})
PYTHON_INTERPRETERS = frozenset(
    {"python", "python2", "python3", "python3.12", "pypy", "pypy3"}
)
SHELL_WRAPPER_OPTIONS_WITH_ARGS = {
    "sudo": frozenset(
        {
            "-u",
            "--user",
            "-g",
            "--group",
            "-h",
            "--host",
            "-p",
            "--prompt",
            "-C",
            "--chdir",
            "-R",
            "--chroot",
            "-r",
            "--role",
            "-t",
            "--type",
            "--close-from",
        }
    ),
    "timeout": frozenset({"-k", "--kill-after", "-s", "--signal"}),
    "nice": frozenset({"-n", "--adjustment"}),
    "env": frozenset({"-u", "--unset", "-C", "--chdir"}),
    # ``exec -a NAME CMD`` consumes NAME before the command.  Without this
    # entry the scanner mistakes NAME for the executable and never reaches a
    # following ``git push``.
    "exec": frozenset({"-a", "--argv0"}),
    # GNU ``time`` consumes a format/output path for these options before the
    # wrapped command. Without the entries, the value (for example ``%e``)
    # is mistaken for the executable and a following ``git`` is skipped.
    "time": frozenset({"-f", "--format", "-o", "--output"}),
}
# Dynamic-path commands are accepted only for these fixed basenames used by
# the reviewed qualification workflows.  A variable prefix may name a
# runner-owned directory, but an arbitrary script basename could hide a
# repository mutation and must remain fail-closed.
DYNAMIC_PATH_ALLOWED_BASENAMES = frozenset(
    {"configure", "mke2fs", "e2fsck", "dumpe2fs", "debugfs"}
)
# A reviewed workflow may materialize a source checkout or an isolated tool
# prefix under a runner-owned directory.  Do not infer trust from an
# arbitrary path merely because its basename/suffix looks familiar: an
# attacker-controlled ``/tmp/evil/tools/validate_repository.py`` (or
# ``$evil/configure``) must stay outside the source-level allow-list.  These
# are the only shell roots currently used by the committed workflow graph;
# keeping the set explicit also makes adding a new root an auditable policy
# change.
REVIEWED_PATH_ROOT_VARIABLES = frozenset(
    {"validation_root", "GITHUB_WORKSPACE", "PWD"}
)
# ``prefix`` is assigned by the D2I build to the isolated e2fsprogs install
# directory.  It is intentionally separate from script roots: only the
# exact ``$prefix/sbin/<tool>`` shape below is accepted for dynamic tool
# probes, never an arbitrary variable/basename combination.
DYNAMIC_TOOL_ROOT_VARIABLES = frozenset({"GITHUB_WORKSPACE", "prefix"})
# Absolute binaries under these runner-provided system directories are not
# treated as repository-local scripts.  They still flow through the ordinary
# Git/shell/HTTP executable checks by basename.  Any other path-qualified
# executable (for example ``/tmp/evil/helper`` or ``$RUNNER_TEMP/helper``) is
# an unreviewed code boundary and fails closed.
SYSTEM_EXECUTABLE_PATH_PREFIXES = (
    "/bin/",
    "/sbin/",
    "/usr/bin/",
    "/usr/sbin/",
    "/lib/",
    "/lib64/",
    "/usr/lib/",
    "/usr/lib64/",
    "/usr/libexec/",
    "/usr/local/bin/",
    "/usr/local/sbin/",
    "/usr/local/libexec/",
)
# Runner-managed roots may be assigned in the two qualification workflows.
# Keep their accepted assignment spellings narrow enough that a command such
# as ``validation_root=/tmp/evil; python3 "$validation_root/tools/..."`` does
# not regain the suffix bypass through a trusted variable name.  The values
# are matched lexically; no environment is evaluated by this source gate.
REVIEWED_ROOT_ASSIGNMENT_PATTERNS = {
    "validation_root": re.compile(
        r"^\$(?:\{RUNNER_TEMP\}|RUNNER_TEMP)/trillionnium-repository-validation$"
    ),
    "prefix": re.compile(
        r"^\$(?:\{RUNNER_TEMP\}|RUNNER_TEMP)/e2fsprogs-"
        r"\$(?:\{E2FSPROGS_VERSION\}|E2FSPROGS_VERSION)$"
    ),
}
# Local scripts are executable policy inputs.  A workflow may invoke only
# this reviewed set by path; an unregistered ``./evil.sh``/``python3
# tools/evil.py`` is rejected before any command body can hide a Git, HTTP,
# or GitHub mutation.  Keep this inventory synchronized with the committed
# workflow graph when intentionally adding a new gate script.
REVIEWED_LOCAL_SCRIPTS = frozenset(
    {
        "packaging/debian/image/build-d1-image.sh",
        "tests/qemu/prepare-d2i-image.sh",
        "tests/qemu/run-d1-boot-test.sh",
        "tests/qemu/run-d1-pipeline.sh",
        "tests/qemu/run-d2i-boot-test.sh",
        "tests/test_systemd_custody_validator.py",
        "tests/test_validate_rust_browser_codec.py",
        "tests/test_verify_receipt_journal.py",
        "tests/transport/test_agent_transport_reference.py",
        "tools/agent_transport_reference.py",
        "tools/browser_codec_reference.py",
        "tools/build_pinned_e2fsprogs.sh",
        "tools/gate_evidence_envelope.py",
        "tools/inject_servo_content_process.py",
        "tools/qualify_servo_exact_pin.py",
        "tools/qualify_servo_exact_pin_evidence.py",
        "tools/qualify_servo_exact_pin_identity.py",
        "tools/qualify_servo_exact_pin_v3.py",
        "tools/reject_symlink_path.sh",
        "tools/run_d1_final_qualification.sh",
        "tools/run_d1_product_image_qualification.sh",
        "tools/run_servo_headed_runtime_gate.sh",
        "tools/validate_d0c04_rust_product.py",
        "tools/validate_d0t03_source.py",
        "tools/validate_d3_development_profile.py",
        "tools/validate_governance_integrity.py",
        "tools/validate_project_truth.py",
        "tools/validate_repository.py",
        "tools/validate_rust_browser_codec.py",
        "tools/verify_receipt_journal.py",
        "tools/verify_systemd_socket_custody.py",
        "packaging/debian/image/rootfs-overlay/usr/local/libexec/trillionnium-d1-agent-port-path-custody",
        "tests/d4/test_collaboration_reference.py",
        "tests/d5/test_trusted_app_bundle.py",
        "tests/d6/test_capability_egress_reference.py",
        "tests/d7/test_ab_update_reference.py",
        "tests/d7/test_effect_reconciliation_reference.py",
        "tests/d8/test_hardware_evidence_verifier.py",
        "tests/d8/test_hardware_promotion_gate.py",
        "tests/d8/test_hardware_verification_receipt.py",
        "tests/d9/test_release_promotion_verifier.py",
        "tools/ab_update_reference.py",
        "tools/capability_egress_reference.py",
        "tools/d4_collaboration_reference.py",
        "tools/effect_reconciliation_reference.py",
        "tools/hardware_evidence_verifier.py",
        "tools/hardware_promotion_gate.py",
        "tools/hardware_verification_receipt.py",
        "tools/release_promotion_verifier.py",
        "tools/trusted_app_bundle.py",
        "tools/trusted_app_indicator.py",
        "tools/validate_agent_port_path_custody.py",
        "tools/validate_late_stage_source_packages.py",
    }
)
SCRIPT_SUFFIXES = frozenset(
    {
        ".bash",
        ".cmd",
        ".js",
        ".ksh",
        ".pl",
        ".py",
        ".py3",
        ".rb",
        ".sh",
        ".zsh",
    }
)
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
    ".github/workflows/agent-port-path-custody.yml",
    ".github/workflows/d4-collaboration.yml",
    ".github/workflows/d4-d9-source-suite.yml",
    ".github/workflows/d5-trusted-app.yml",
    ".github/workflows/d6-capability-egress.yml",
    ".github/workflows/d7-recovery-update.yml",
    ".github/workflows/d8-hardware-promotion-policy.yml",
    ".github/workflows/d8-hardware-qualification.yml",
    ".github/workflows/d9-release-promotion.yml",
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


def _shell_heredoc_markers(line: str) -> list[tuple[str, bool, bool]]:
    """Extract simple shell heredoc delimiters outside quoted text.

    The third tuple member records whether the delimiter was quoted.  An
    unquoted delimiter is significant even when the body is fed to a
    seemingly inert consumer: parameter/command substitutions in that body
    are expanded by the *outer* shell while constructing the heredoc.
    """

    markers: list[tuple[str, bool, bool]] = []
    index = 0
    quote: str | None = None
    escaped = False
    while index < len(line):
        character = line[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if quote == "'":
            if character == "'":
                quote = None
            index += 1
            continue
        if quote == '"':
            if character == "\\":
                escaped = True
            elif character == '"':
                quote = None
            index += 1
            continue
        if character == "\\":
            escaped = True
            index += 1
            continue
        if character in {"'", '"'}:
            quote = character
            index += 1
            continue
        if line.startswith("<<", index):
            cursor = index + 2
            strip_tabs = cursor < len(line) and line[cursor] == "-"
            if strip_tabs:
                cursor += 1
            while cursor < len(line) and line[cursor] in " \t":
                cursor += 1
            if cursor >= len(line):
                break
            delimiter_quote: str | None = None
            if line[cursor] in {"'", '"'}:
                delimiter_quote = line[cursor]
                cursor += 1
            start = cursor
            while cursor < len(line):
                current = line[cursor]
                if delimiter_quote is not None:
                    if current == delimiter_quote:
                        break
                elif current.isspace() or current in ";|&()":
                    break
                cursor += 1
            delimiter = line[start:cursor]
            if delimiter:
                markers.append((delimiter, strip_tabs, delimiter_quote is not None))
            index = cursor + (1 if delimiter_quote and cursor < len(line) else 0)
            continue
        index += 1
    return markers


def _heredoc_kind(line: str) -> str:
    """Classify a heredoc as Python, shell, or inert data.

    A workflow ``run`` block can contain several unrelated heredocs.  Scanning
    every body as Python or shell would make a fixture/documentation payload
    look executable, while dropping every body would hide a real ``bash`` or
    ``python3`` script.  Inspect only the command text before the first
    delimiter; a pipe to an interpreter is covered because all command
    segments on that line are considered.
    """

    marker = line.find("<<")
    prefix = line if marker < 0 else line[:marker]
    suffix = "" if marker < 0 else line[marker + 2 :]
    python_names = {"python", "python3", "python3.12", "pypy", "pypy3"}
    # ``at``/``batch`` execute shell source read from stdin, so their
    # heredoc bodies are executable command graphs just like ``bash`` input.
    shell_names = {"bash", "sh", "dash", "zsh", "ksh", "at", "batch"}
    for tokens in _shell_command_tokens(prefix, strip_comments=True):
        index = _shell_executable_index(tokens, 0)
        if index >= len(tokens):
            continue
        executable = _executable_basename(tokens[index])
        if executable in python_names:
            return "python"
        if executable in shell_names:
            return "shell"
        # Do not scan arbitrary arguments for interpreter-looking words:
        # ``echo python3 <<EOF`` is an inert data producer, not a Python
        # heredoc.  A real interpreter on the right side of a pipe is handled
        # by the explicit pipe checks below.
    # ``cat <<EOF | python3``/``| bash`` feeds the body to the interpreter on
    # the right side of a pipe. Restrict this check to an actual pipe so a
    # delimiter or redirection target named ``python3`` cannot reclassify an
    # inert data heredoc.
    if re.search(r"\|\s*(?:env\s+)?(?:python(?:3(?:\.[0-9]+)?)?|pypy3?)\b", suffix):
        return "python"
    if re.search(r"\|\s*(?:env\s+)?(?:bash|sh|dash|zsh|ksh)\b", suffix):
        return "shell"
    return "data"


def _mask_heredoc_bodies(command: str, *, keep_kinds: set[str]) -> str:
    """Mask non-executable heredoc bodies while preserving line offsets."""

    lines = command.splitlines(keepends=True)
    output: list[str] = []
    pending: list[tuple[str, bool, bool, str]] = []
    active: tuple[str, bool, bool, str] | None = None
    for line in lines:
        if active is None and pending:
            active = pending.pop(0)
        if active is not None:
            delimiter, strip_tabs, quoted, kind = active
            candidate = line.rstrip("\r\n")
            if strip_tabs:
                candidate = candidate.lstrip("\t")
            if candidate == delimiter:
                # Keep the delimiter itself: it is shell syntax and retaining
                # it avoids changing diagnostics/line-oriented offsets.
                output.append(line)
                active = None
            elif kind in keep_kinds:
                output.append(line)
            else:
                # Preserve only the physical newline; body bytes are data for
                # another process and must not be reinterpreted by this scan.
                output.append("\n" if line.endswith("\n") else "")
            continue
        output.append(line)
        for delimiter, strip_tabs, quoted in _shell_heredoc_markers(line):
            pending.append((delimiter, strip_tabs, quoted, _heredoc_kind(line)))
    return "".join(output)


_HEREDOC_EXPANSION = re.compile(
    # Any of these constructs is expanded in an unquoted here-document.  We
    # reject the whole source fragment rather than attempting to emulate
    # shell expansion/field splitting; this keeps a command substitution such
    # as ``$(git push)`` from hiding behind a data heredoc.  Include the
    # positional/special parameter spellings (``$@``, ``$?``, ``$1``, ``$$``
    # and friends) as well: when the body is fed to a shell interpreter those
    # values can inject an otherwise invisible command graph just like a
    # named variable can.
    r"(?:\$\(|`|\$\{|\$[A-Za-z_][A-Za-z0-9_]*|\$(?:[0-9]+|[#$?!@*_-])|\$\(?\()"
)


def _unquoted_heredoc_expansion_mutates(command: str) -> bool:
    """Fail closed for executable expansions in unquoted heredoc bodies."""

    lines = command.splitlines(keepends=True)
    pending: list[tuple[str, bool, bool]] = []
    active: tuple[str, bool, bool] | None = None
    body_chunks: list[str] = []
    for line in lines:
        if active is None and pending:
            active = pending.pop(0)
            body_chunks = []
        if active is not None:
            delimiter, strip_tabs, quoted = active
            candidate = line.rstrip("\r\n")
            if strip_tabs:
                candidate = candidate.lstrip("\t")
            if candidate == delimiter:
                if not quoted:
                    # A backslash-newline pair is removed while an unquoted
                    # heredoc is expanded.  Inspect the whole body after that
                    # removal so an expansion split across physical lines
                    # (for example ``$\\\n(git push)``) cannot evade the
                    # marker regex below.
                    body = "".join(body_chunks)
                    normalized = re.sub(r"\\[ \t]*\r?\n", "", body)
                    if _HEREDOC_EXPANSION.search(normalized):
                        return True
                active = None
            else:
                body_chunks.append(line)
            continue
        for delimiter, strip_tabs, quoted in _shell_heredoc_markers(line):
            pending.append((delimiter, strip_tabs, quoted))
    # An unterminated unquoted heredoc is malformed shell and cannot be
    # treated as a read-only source proof.  The YAML parser preserves the run
    # scalar, so reject it here rather than silently masking its tail.
    if active is not None and not active[2]:
        body = "".join(body_chunks)
        normalized = re.sub(r"\\[ \t]*\r?\n", "", body)
        if _HEREDOC_EXPANSION.search(normalized):
            return True
    return active is not None and not active[2]


def _strip_shell_heredoc_bodies(command: str) -> str:
    """Replace Python/data heredoc bodies before shell command scanning."""

    return _mask_heredoc_bodies(command, keep_kinds={"shell"})


def _python_scan_source(command: str) -> str:
    """Return direct/Python heredoc source while masking shell/data bodies."""

    return _mask_heredoc_bodies(command, keep_kinds={"python"})


_SHELL_BRACE_OPEN_SENTINEL = "\x1e"
_SHELL_BRACE_CLOSE_SENTINEL = "\x1f"
_SHELL_EXPANSION_SPACE_SENTINEL = "\x1d"


def _shield_shell_parameter_braces(command: str) -> str:
    """Shield braces inside ``${...}`` while tokenizing shell punctuation.

    Braces are useful punctuation for compact function bodies (``f(){git;}``),
    but adding them to :mod:`shlex`'s punctuation set would split ordinary
    parameter expansions such as ``${IFS}`` and ``${GIT_VERB:-push}``. Replace
    only expansion braces with private sentinels; the token stream is restored
    immediately after lexing. Nested braces in GitHub expressions are handled
    with a small depth counter and no evaluation.
    """

    chars = list(command)
    index = 0
    while index + 1 < len(chars):
        if chars[index] != "$" or chars[index + 1] != "{":
            index += 1
            continue
        chars[index + 1] = _SHELL_BRACE_OPEN_SENTINEL
        depth = 1
        cursor = index + 2
        quote: str | None = None
        escaped = False
        while cursor < len(chars):
            character = chars[cursor]
            if escaped:
                escaped = False
                cursor += 1
                continue
            if quote is not None:
                if character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
                cursor += 1
                continue
            if character in {"'", '"'}:
                quote = character
            elif character == "{":
                depth += 1
                chars[cursor] = _SHELL_BRACE_OPEN_SENTINEL
            elif character == "}":
                depth -= 1
                chars[cursor] = _SHELL_BRACE_CLOSE_SENTINEL
                if depth == 0:
                    index = cursor + 1
                    break
            elif character in " \t\r\n":
                # Keep a GitHub expression such as ``${{ github.sha }}`` in
                # one lexical token.  Restore the original whitespace after
                # shlex has split command words.
                chars[cursor] = _SHELL_EXPANSION_SPACE_SENTINEL
            cursor += 1
        else:
            # Unterminated expansions are intentionally left partially
            # shielded; the fallback token scanner will fail closed.
            index = cursor
    return "".join(chars)


def _restore_shell_parameter_braces(value: str) -> str:
    return value.replace(
        _SHELL_BRACE_OPEN_SENTINEL, "{"
    ).replace(_SHELL_BRACE_CLOSE_SENTINEL, "}").replace(
        _SHELL_EXPANSION_SPACE_SENTINEL, " "
    )


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
    normalized = _shield_shell_parameter_braces(normalized)
    commands: list[list[str]] = []
    current: list[str] = []
    try:
        lexer = shlex.shlex(
            normalized,
            posix=True,
            # Braces are shell command-list delimiters.  Keeping them as
            # punctuation lets function/brace-group bodies such as
            # ``f(){git push;}`` be scanned at the real command boundary;
            # quoted braces remain part of their quoted token.
            punctuation_chars=";&|(){}\n",
        )
        lexer.wordchars += (
            _SHELL_BRACE_OPEN_SENTINEL
            + _SHELL_BRACE_CLOSE_SENTINEL
            + _SHELL_EXPANSION_SPACE_SENTINEL
        )
        lexer.whitespace_split = True
        # Keep newline out of ``whitespace`` so punctuation handling emits it
        # as a command boundary (newlines inside quoted strings remain part of
        # that token).
        lexer.whitespace = " \t\r"
        lexer.commenters = "#" if strip_comments else ""
        # ``shlex`` may emit a punctuation run one character at a time when
        # ``punctuation_chars`` is enabled (notably ``&&`` and background
        # ``&``).  Treat a single ampersand as a command boundary too; if a
        # run is split into two ampersands, both still safely terminate the
        # preceding command and expose the command after it.
        separators = {";", "&", "&&", "||", "|", "(", ")", "\n"}
        brace_depth = 0

        def emit_punctuation(character: str) -> None:
            """Apply one shell punctuation character to the current segment."""

            nonlocal brace_depth, current
            if character == "{":
                # A brace is a command-list opener only at a command
                # boundary, after a function declarator, or immediately after
                # a compound-control keyword.  Keeping ``echo { ...`` in the
                # same segment prevents prose/data from becoming an executed
                # command, while compact ``f(){git;}`` remains parseable.
                opens_group = (
                    not current
                    or current[-1]
                    in {")", "()", "then", "do", "else", "elif", "coproc"}
                    or (current and current[0].lower() == "function")
                    or (current and current[0].lower() == "coproc")
                )
                if opens_group:
                    if current:
                        commands.append(current)
                        current = []
                    brace_depth += 1
                else:
                    current.append(character)
                return
            if character == "}":
                if brace_depth:
                    if current:
                        commands.append(current)
                        current = []
                    brace_depth -= 1
                else:
                    current.append(character)
                return
            if character in separators:
                if current:
                    commands.append(current)
                    current = []
                return
            current.append(character)

        for word in lexer:
            word = _restore_shell_parameter_braces(word)
            # ``shlex`` can return a run such as ``);`` as one punctuation
            # token. Split runs explicitly so a command following a closing
            # subshell/function delimiter is still recognized as a new
            # command (and array expansions at that position fail closed).
            punctuation_run = bool(word) and all(
                character in ";&|(){}\n" for character in word
            )
            if word in separators or punctuation_run:
                if punctuation_run:
                    for character in word:
                        emit_punctuation(character)
                else:
                    emit_punctuation(word)
            else:
                current.append(word)
    except ValueError:
        for segment in re.split(r"(?:\r?\n|&&|\|\||[;|])", normalized):
            if strip_comments:
                segment = re.split(r"(?<!\\)#", segment, maxsplit=1)[0]
            words = [
                _restore_shell_parameter_braces(word)
                for word in re.findall(r"[^\s]+", segment)
            ]
            if words:
                commands.append(words)
        return commands
    if current:
        commands.append(current)
    return commands


def _executable_basename(value: str) -> str:
    """Normalize Unix/Windows path-qualified executable names."""

    return value.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()


def _is_git_executable_or_helper(value: str) -> bool:
    """Return whether *value* can dispatch Git or a Git helper.

    Git installs a large family of ``git-*`` helper executables.  Maintaining
    a finite mutation list is unsound: a newly added helper (for example
    ``git-revert`` or ``git-filter-repo``) would otherwise disappear from the
    command graph.  Treat every path-qualified ``git-*`` basename as an
    effectful/ambiguous helper, with the one restricted ``git-shell`` spelling
    left to the shell-interpreter payload auditor below.
    """

    executable = _executable_basename(value)
    return (
        executable in GIT_EXECUTABLES
        or executable in GIT_MUTATING_HELPERS
        or (executable.startswith("git-") and executable != "git-shell")
    )


def _shell_token_has_expansion(value: str) -> bool:
    """Return whether *value* contains an unresolved shell expansion."""

    return SHELL_PARAMETER_EXPANSION.search(value) is not None


def _shell_brace_expansion_mutates(command: str) -> bool:
    """Detect unquoted shell brace expansion which can rewrite a path.

    ``shlex`` exposes braces as command-list punctuation, so a form such as
    ``python3 {tools,evil}/validate_repository.py`` can otherwise lose the
    executable path before the script allow-list sees it.  Skip quoted text,
    comments, and ``${...}``/``${{...}}`` parameter/GitHub expressions; reject
    only the shell brace-expansion signatures (comma lists and ``{n..m}``
    ranges).  The source gate is intentionally conservative for these forms.
    """

    index = 0
    quote: str | None = None
    escaped = False
    comment = False
    while index < len(command):
        character = command[index]
        if comment:
            if character in "\r\n":
                comment = False
            index += 1
            continue
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            index += 1
            continue
        if character == "\\":
            index += 2
            continue
        if character in {"'", '"'}:
            quote = character
            index += 1
            continue
        if character == "#" and (
            index == 0 or command[index - 1].isspace() or command[index - 1] in ";|&(){}"
        ):
            comment = True
            index += 1
            continue
        if character == "$" and index + 1 < len(command) and command[index + 1] == "{":
            # Parameter/GitHub expressions are not shell brace expansion.
            depth = 1
            cursor = index + 2
            nested_quote: str | None = None
            nested_escaped = False
            while cursor < len(command) and depth:
                current = command[cursor]
                if nested_quote is not None:
                    if nested_escaped:
                        nested_escaped = False
                    elif current == "\\":
                        nested_escaped = True
                    elif current == nested_quote:
                        nested_quote = None
                elif current in {"'", '"'}:
                    nested_quote = current
                elif current == "{":
                    depth += 1
                elif current == "}":
                    depth -= 1
                cursor += 1
            index = cursor
            continue
        if character == "{":
            depth = 1
            cursor = index + 1
            nested_quote: str | None = None
            nested_escaped = False
            while cursor < len(command) and depth:
                current = command[cursor]
                if nested_quote is not None:
                    if nested_escaped:
                        nested_escaped = False
                    elif current == "\\":
                        nested_escaped = True
                    elif current == nested_quote:
                        nested_quote = None
                elif current in {"'", '"'}:
                    nested_quote = current
                elif current == "{":
                    depth += 1
                elif current == "}":
                    depth -= 1
                cursor += 1
            if depth == 0:
                body = command[index + 1 : cursor - 1]
                if "," in body or ".." in body:
                    return True
                index = cursor
                continue
        index += 1
    return False


def _shell_static_prefix(value: str) -> str | None:
    """Return the literal prefix before a shell expansion, when present."""

    if not _shell_token_has_expansion(value):
        return value
    match = re.match(r"^([A-Za-z0-9_.-]+)", value)
    return match.group(1) if match else None


def _git_ref_expansion_is_reviewed(value: str) -> bool:
    """Return whether a dynamic Git ref has reviewed provenance."""
    value = value.strip()
    if not _shell_token_has_expansion(value):
        return True
    if value.startswith("${") and value.endswith("}"):
        name = value[2:-1]
    elif value.startswith("$"):
        name = value[1:]
    else:
        return False
    if not name or not (name[0].isalpha() or name[0] == "_"):
        return False
    if not all(character.isalnum() or character == "_" for character in name):
        return False
    return name.upper().endswith(("REVISION", "SHA", "COMMIT", "REF", "OID", "HEAD"))


def _git_fetch_is_read_only(tokens: list[str], verb_index: int) -> bool:
    """Allow only the exact bounded fetch shape used by qualification."""
    tail = tokens[verb_index + 1:]
    if not tail:
        return False
    positional: list[str] = []
    index = 0
    while index < len(tail):
        argument = tail[index]
        if argument in {"--no-tags", "--quiet", "-q", "--verbose", "-v"}:
            index += 1
            continue
        if argument == "--depth":
            if index + 1 >= len(tail) or not tail[index + 1].isdigit() or int(tail[index + 1]) < 1:
                return False
            index += 2
            continue
        if argument.startswith("--depth="):
            value = argument.split("=", 1)[1]
            if not value.isdigit() or int(value) < 1:
                return False
            index += 1
            continue
        if argument.startswith("-"):
            return False
        positional.append(argument)
        index += 1
    if len(positional) != 2:
        return False
    remote, revision = positional
    if _shell_token_has_expansion(remote):
        return False
    if not remote or not all(character.isalnum() or character in "._-" for character in remote):
        return False
    return _git_ref_expansion_is_reviewed(revision)


def _git_checkout_is_read_only(tokens: list[str], verb_index: int) -> bool:
    """Allow only a detached checkout of one reviewed revision."""
    tail = tokens[verb_index + 1:]
    detached = False
    revision: str | None = None
    for argument in tail:
        if argument == "--detach":
            detached = True
            continue
        if argument in {"--quiet", "-q", "--progress", "--no-progress"}:
            continue
        if argument.startswith("-"):
            return False
        if revision is not None:
            return False
        revision = argument
    return detached and revision is not None and _git_ref_expansion_is_reviewed(revision)


def _git_option_is_side_effectful(argument: str) -> bool:
    """Reject write/pager options, including attached dynamic spellings."""
    lowered = argument.lower()
    for option in GIT_SIDE_EFFECT_OPTIONS:
        normalized = option.lower()
        if lowered == normalized or lowered.startswith(normalized + "="):
            return True
        if normalized.startswith("--") and lowered.startswith(normalized):
            suffix = argument[len(option):]
            if suffix and _shell_token_has_expansion(suffix):
                return True
    return argument.startswith("--") and _shell_token_has_expansion(argument)

def _git_invocation_mutates(tokens: list[str], executable_index: int) -> bool:
    """Return whether a Git invocation is not statically read-only.

    The caller must pass the index of an actual command-position executable;
    arbitrary ``git`` words in prose, comments, or Python string arguments are
    intentionally not interpreted as commands.  Once a Git executable is at
    that position, unknown verbs and dynamic subcommands fail closed.  Dynamic
    commit/path arguments after an approved verb remain allowed because the
    qualification workflows bind those values through the environment.
    """

    if executable_index < 0 or executable_index >= len(tokens):
        return False
    executable = _executable_basename(tokens[executable_index])
    if executable in GIT_MUTATING_HELPERS or (
        executable.startswith("git-") and executable != "git-shell"
    ):
        return True
    if executable not in GIT_EXECUTABLES:
        return False

    # File-output, external-diff, text-conversion, and pager options can
    # mutate the workspace or execute helpers even for a read-only verb.
    if any(_git_option_is_side_effectful(argument) for argument in tokens[executable_index + 1 :]):
        return True

    # Configuration/helper options are dangerous wherever they occur. Git's
    # option parser accepts several of them both before and after a verb, and
    # compact ``-cname=value`` spelling otherwise evades the separate-argument
    # check below. A configured alias or custom transport helper can turn a
    # seemingly read-only verb into a repository/network mutation.
    for argument in tokens[executable_index + 1 :]:
        option = argument.split("=", 1)[0]
        option_lower = option.lower()
        if (
            option == "-c"
            or option.startswith("-c")
            or option_lower in {
                "--config-env",
                "--exec-path",
                "--upload-pack",
                "--receive-pack",
            }
        ):
            return True
    # Git treats ``--help``/``--version`` as informational even when a topic
    # follows (for example ``git --help push``). They do not dispatch the
    # topic as a mutating subcommand.
    if any(
        argument.lower().split("=", 1)[0] in {"--help", "-h", "--version", "-v"}
        for argument in tokens[executable_index + 1 :]
    ):
        return False

    cursor = executable_index + 1
    while cursor < len(tokens):
        argument = tokens[cursor]
        lowered = argument.lower()
        if lowered == "--":
            cursor += 1
            continue

        if not argument.startswith("-"):
            # A token such as ``fetch${IFS}origin`` has a statically visible
            # verb and a dynamic argument separator.  Evaluate only that
            # prefix; a wholly dynamic token (``${GIT_VERB:-push}``) is not a
            # source-level read-only proof.
            verb = _shell_static_prefix(argument)
            if verb is None or "[" in argument:
                return True
            verb = verb.lower()
            if verb in MUTATING_GIT_SUBCOMMANDS:
                return True
            if verb == "hash-object" and any(
                item.lower() in {"-w", "--write"}
                for item in tokens[cursor + 1 :]
            ):
                return True
            if verb == "checkout":
                return not _git_checkout_is_read_only(tokens, cursor)
            if verb == "fetch":
                return not _git_fetch_is_read_only(tokens, cursor)
            if verb == "switch":
                return True
            return verb not in GIT_READ_ONLY_SUBCOMMANDS

        # Preserve the case-sensitive short ``-C`` path option.  Lowercasing
        # it would alias it to ``-c`` and falsely reject every read-only
        # command that changes to a disposable directory.
        option = argument.split("=", 1)[0]
        option_lower = option.lower()
        if option == "-c" or option.startswith("-c") or option_lower in {
            "--config-env",
            "--exec-path",
            "--upload-pack",
            "--receive-pack",
        }:
            return True
        option_with_arg = option == "-C" or option_lower in {
            item.lower()
            for item in MUTATING_GIT_OPTIONS_WITH_ARGS
            if item != "-C"
        }
        if "=" not in argument and option_with_arg:
            cursor += 2
        else:
            cursor += 1

    # ``git --version`` and ``git --help`` have no subcommand and are
    # informational.  Any other incomplete invocation is ambiguous.
    options = {
        token.lower().split("=", 1)[0]
        for token in tokens[executable_index + 1 :]
    }
    return not bool(options & {"--version", "-v", "--help", "-h"})


def _shell_command_start_indices(tokens: list[str]) -> list[int]:
    """Return likely command positions in one tokenized shell segment."""

    # ``shlex`` already splits punctuation operators (``;``, ``&&``, ``||``,
    # ``|`` and newlines) into separate command segments.  Reserved words
    # such as ``then``/``do`` are therefore command prefixes only when they
    # begin a segment; treating every occurrence as a boundary would classify
    # harmless data like ``echo then git push`` as an executed Git command.
    starts: set[int] = {0} if tokens else set()
    prefix_words = {"then", "do", "else", "elif", "!", "(", "coproc"}
    for index, token in enumerate(tokens[:-1]):
        lowered = token.lower()
        if index == 0 and lowered in prefix_words:
            starts.add(index + 1)
        # ``then ! git ...``/``do ! git ...`` and a leading ``!`` put the
        # executable after the negation operator.  Preserve the segment-start
        # requirement so an arbitrary ``echo ! git push`` remains data.
        if token == "!" and index in starts:
            starts.add(index + 1)
        # A brace following a function declarator opens a command body.  Do
        # not treat ``echo { ...`` as a second command, but retain compound
        # blocks written as ``{ git ...; }``.
        if token == "{" and (
            index == 0
            or index in starts
            or (index > 0 and tokens[index - 1] in {")", "()"})
            or (index >= 2 and tokens[index - 2].lower() == "function")
        ):
            starts.add(index + 1)
    # ``if git ...`` and ``while git ...`` put the command after a shell
    # control keyword without a punctuation separator.  Test expressions are
    # data, not commands, so leave ``if [[ ... ]]``/``while [ ... ]`` alone.
    for index, token in enumerate(tokens[:-1]):
        if token.lower() not in {"if", "while", "until"}:
            continue
        candidate = index + 1
        if tokens[candidate] not in {"[", "[["}:
            starts.add(candidate)
            if tokens[candidate] == "!" and candidate + 1 < len(tokens):
                starts.add(candidate + 1)
    # The control-keyword pass above can add a leading ``{``/``!`` after the
    # first brace/negation pass (for example ``if { git push; }``).  Close
    # this tiny boundary expansion without treating braces in ordinary data
    # as command starts.
    for index in sorted(starts):
        if index + 1 >= len(tokens):
            continue
        if tokens[index] == "!":
            starts.add(index + 1)
        elif tokens[index] == "{":
            starts.add(index + 1)
    return sorted(set(starts))


def _shell_executable_index(tokens: list[str], start: int) -> int:
    """Skip assignments and common wrappers before a command executable."""

    index = start
    while index < len(tokens):
        token = tokens[index]
        if SHELL_ASSIGNMENT.fullmatch(token):
            index += 1
            continue
        executable = _executable_basename(token)
        if executable not in SHELL_WRAPPERS:
            break
        index += 1
        option_args = SHELL_WRAPPER_OPTIONS_WITH_ARGS.get(executable, frozenset())
        if executable == "timeout":
            # timeout's first non-option is a duration, not the command.
            while index < len(tokens) and tokens[index].startswith("-"):
                option = tokens[index].split("=", 1)[0]
                index += 2 if option in option_args and "=" not in tokens[index] else 1
            if index < len(tokens) and tokens[index] != "--":
                index += 1
            elif index < len(tokens):
                index += 1
            # ``--`` terminates timeout's options and is not the wrapped
            # executable.  Advance past it so a command such as
            # ``timeout --signal=KILL 5 -- git push`` is audited at ``git``.
            if index < len(tokens) and tokens[index] == "--":
                index += 1
        elif executable == "nice":
            while index < len(tokens) and tokens[index].startswith("-"):
                option = tokens[index].split("=", 1)[0]
                index += 2 if option in option_args and "=" not in tokens[index] else 1
        else:
            while index < len(tokens):
                candidate = tokens[index]
                if SHELL_ASSIGNMENT.fullmatch(candidate):
                    index += 1
                    continue
                if candidate == "--":
                    index += 1
                    break
                if not candidate.startswith("-"):
                    break
                option = candidate.split("=", 1)[0]
                index += 2 if option in option_args and "=" not in candidate else 1
    return index


SHELL_INTERPRETER_OPTIONS_WITH_ARGS = frozenset(
    {
        "-o",
        "-O",
        "--rcfile",
        "--init-file",
        "--startup-file",
    }
)
SHELL_INTERPRETER_OPTIONS_NO_ARGS = frozenset(
    {
        "--login",
        "--noprofile",
        "--norc",
        "--posix",
        "--verbose",
        "--debugger",
        "--restricted",
        "--noediting",
        "--noexec",
        "--version",
        "--help",
    }
)
PYTHON_INTERPRETER_OPTIONS_WITH_ARGS = frozenset(
    {
        "-c",
        "-m",
        "-W",
        "-X",
    }
)


def _script_path_key(token: str) -> str | None:
    """Return a reviewed repository-relative script name for *token*.

    The old implementation accepted any path ending in a reviewed suffix.
    That made an unrelated checkout such as
    ``/tmp/attacker/tools/validate_repository.py`` indistinguishable from the
    repository copy.  Keep the accepted forms deliberately small:

    * an exact repository-relative path (optionally ``./``-prefixed), or
    * an exact path rooted at one of the explicitly reviewed workflow
      variables (``$validation_root``, ``$GITHUB_WORKSPACE`` or ``$PWD``).

    No canonicalisation is attempted here.  Traversal, duplicate separators,
    URL/absolute prefixes, and unknown variable roots must fail closed rather
    than being normalised into an apparently safe suffix.
    """

    value = token.strip("'\"").replace("\\", "/")
    if not value or any(part == ".." for part in value.split("/")):
        return None

    for path in REVIEWED_LOCAL_SCRIPTS:
        if value == path or value == f"./{path}":
            return path

        # Shell variable roots used by the reviewed workflows.  Match the
        # complete root/path shape, not a suffix, so ``$evil/foo/$root/...``
        # and ``/tmp/evil/<reviewed suffix>`` are not accepted.
        for variable in REVIEWED_PATH_ROOT_VARIABLES:
            if value == f"${variable}/{path}" or value == f"${{{variable}}}/{path}":
                return path

        # GitHub expressions are emitted literally in workflow source before
        # the runner interpolates them.  Accept only the canonical workspace
        # expression, in both spacing styles produced by common YAML forms.
        if value in {
            f"${{{{ github.workspace }}}}/{path}",
            f"${{{{github.workspace}}}}/{path}",
        }:
            return path
    return None


def _reviewed_root_assignment_safe(token: str) -> bool:
    """Return whether a trusted path-root assignment is source-safe.

    Trusted variable *names* alone are not sufficient: a workflow can shadow
    ``validation_root``/``prefix`` with an arbitrary external directory before
    invoking a reviewed-looking suffix.  Only the exact runner-owned values
    used by the committed qualification jobs are accepted.  Unrecognised
    root assignments are rejected by the caller.
    """

    match = SHELL_ASSIGNMENT.fullmatch(token)
    if match is None:
        return True
    name, value = match.groups()
    if name not in REVIEWED_PATH_ROOT_VARIABLES | DYNAMIC_TOOL_ROOT_VARIABLES:
        return True
    value = value.strip("'\"")
    pattern = REVIEWED_ROOT_ASSIGNMENT_PATTERNS.get(name)
    if pattern is None:
        # GITHUB_WORKSPACE and PWD are runner/shell-provided roots.  Assigning
        # either in a workflow would make their provenance ambiguous, so do
        # not permit a source-side override.
        return False
    return pattern.fullmatch(value) is not None


def _shell_root_assignment_tokens(tokens: list[str]) -> Iterable[str]:
    """Yield root assignments which are syntactically executable.

    A raw token scan would mistake data such as ``echo "prefix=/tmp"`` for a
    shell assignment because :mod:`shlex` intentionally discards quote
    provenance.  Restrict checks to leading assignment words, declaration
    builtins, and ``env``'s assignment prefix—the positions where a shell can
    actually alter a command's root environment.
    """

    declaration_builtins = {
        "declare",
        "export",
        "local",
        "readonly",
        "typeset",
    }
    for start in _shell_command_start_indices(tokens):
        index = start
        while index < len(tokens) and SHELL_ASSIGNMENT.fullmatch(tokens[index]):
            yield tokens[index]
            index += 1
        if index >= len(tokens):
            continue
        executable = _executable_basename(tokens[index])
        if executable in declaration_builtins:
            for token in tokens[index + 1 :]:
                if SHELL_ASSIGNMENT.fullmatch(token):
                    yield token
            continue
        if executable != "env":
            continue
        # ``env`` accepts options before NAME=VALUE assignments.  Stop at the
        # first command token; later words are command arguments/data.
        index += 1
        while index < len(tokens):
            token = tokens[index]
            if token == "--":
                index += 1
                break
            if token.startswith("-"):
                option = token.split("=", 1)[0]
                if option in {"-C", "--chdir", "-u", "--unset"} and "=" not in token:
                    index += 2
                else:
                    index += 1
                continue
            if SHELL_ASSIGNMENT.fullmatch(token):
                yield token
                index += 1
                continue
            break


def _looks_like_script_path(token: str) -> bool:
    """Return whether a command token plausibly names an executable script."""

    value = token.strip("'\"")
    normalized = value.replace("\\", "/")
    if not value:
        return False
    basename = normalized.rsplit("/", 1)[-1]
    if any(basename.lower().endswith(suffix) for suffix in SCRIPT_SUFFIXES):
        return True
    # Extensionless repository scripts conventionally use an explicit
    # relative/repository path.  Do not classify ordinary absolute binaries
    # such as ``/usr/bin/git`` as scripts merely because they contain '/'.
    if normalized.startswith(("./", "tools/", "tests/", "packaging/")):
        return True
    # The D2I contract permits a small set of dynamically rooted tool
    # basenames (notably ``.../configure``).  Include path-qualified forms
    # even without a shell expansion so a static ``/tmp/evil/configure`` is
    # not invisible to the script-path gate.
    if "/" not in normalized:
        return False
    if _executable_basename(normalized) in DYNAMIC_PATH_ALLOWED_BASENAMES:
        return True
    # Keep canonical system binaries out of the local-script policy; their
    # basenames are still audited by the Git/HTTP/interpreter recognizers.
    if normalized.startswith(SYSTEM_EXECUTABLE_PATH_PREFIXES):
        return False
    # An extensionless executable outside the runner's fixed system roots is
    # still an executable code boundary.  Do not let a helper such as
    # ``/tmp/evil/helper --version`` pass merely because it has no familiar
    # script suffix: the source gate cannot inspect that helper's contents.
    # Variable-root forms are treated the same way (``$RUNNER_TEMP/helper``),
    # while URL/ordinary argument tokens never reach this predicate unless
    # they occupy a command or interpreter executable slot.
    if normalized.startswith("/") or normalized.startswith("$"):
        return True
    return False


def _script_path_invocation_mutates(token: str) -> bool:
    """Fail closed for an unregistered local/external script invocation."""

    if not _looks_like_script_path(token):
        return False
    value = token.strip("'\"").replace("\\", "/")
    basename = value.rsplit("/", 1)[-1]
    # The ordinary executable recognizers need to see canonical system paths
    # such as ``/usr/bin/git`` and ``/bin/bash``.  They are not repository
    # script inputs, so leave them for those recognizers after the explicit
    # dynamic-tool check below.
    if (
        value.startswith(SYSTEM_EXECUTABLE_PATH_PREFIXES)
        and basename not in DYNAMIC_PATH_ALLOWED_BASENAMES
    ):
        return False
    # The D2I build intentionally invokes a pinned external ``configure`` or
    # freshly built e2fsprogs binary through a runner path.  Those five
    # basenames are independently constrained by the D2I contract.  Every
    # other dynamic path is too ambiguous to prove read-only.
    if _shell_token_has_expansion(value):
        if _dynamic_path_executable_is_allowed(value):
            return False
        return _script_path_key(value) is None
    if basename in DYNAMIC_PATH_ALLOWED_BASENAMES:
        # Static paths to the tool basenames are not provenance-bound to the
        # pinned source/prefix and therefore cannot be admitted.
        return True
    return _script_path_key(value) is None


def _python_path_invocation_mutates(token: str) -> bool:
    """Apply path provenance rules to a literal Python process path.

    A Python string containing ``$prefix/...`` is not shell-expanded, so the
    shell-path helper's dynamic-tool allowance must not be reused blindly.
    Conversely, extensionless external paths (``/tmp/evil/helper``) need an
    explicit fail-closed check because they have no script suffix for the
    lexical shell classifier to recognise.
    """

    value = token.strip("'\"").replace("\\", "/")
    if not value:
        return True
    if _shell_token_has_expansion(value):
        return True
    if _is_git_executable_or_helper(value):
        # Git paths are audited by the Git verb checker below.
        return False
    if value.startswith(SYSTEM_EXECUTABLE_PATH_PREFIXES):
        return False
    if _script_path_key(value) is not None:
        return False
    if _script_path_invocation_mutates(value):
        return True
    # Any remaining path-qualified literal is an unreviewed executable
    # boundary. Bare command names (``echo``, ``python3``) remain eligible for
    # the ordinary executable recognizers.
    return "/" in value


def _interpreter_script_argument(
    tokens: list[str], executable_index: int
) -> str | None:
    """Find a literal script argument after a shell/Python interpreter.

    ``-c``/``-m`` forms carry code/module names rather than filesystem script
    paths and are audited by their dedicated recursive scanners.  A missing
    argument is left to those scanners; this helper only returns a candidate
    when a non-option token unambiguously occupies the script slot.
    """

    executable = _executable_basename(tokens[executable_index])
    arguments = tokens[executable_index + 1 :]
    option_args = (
        SHELL_INTERPRETER_OPTIONS_WITH_ARGS
        if executable in SHELL_INTERPRETERS
        else PYTHON_INTERPRETER_OPTIONS_WITH_ARGS
    )
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            index += 1
            continue
        if argument in {"-c", "--command", "-m", "--module"}:
            return None
        if argument.startswith("--command=") or argument.startswith("--module="):
            return None
        if executable in SHELL_INTERPRETERS and argument in SHELL_INTERPRETER_OPTIONS_NO_ARGS:
            index += 1
            continue
        if argument.startswith("-"):
            option = argument.split("=", 1)[0]
            if option in option_args and "=" not in argument:
                index += 2
            else:
                index += 1
            continue
        # ``python3 -`` reads stdin (usually a heredoc), not a filesystem
        # script.  The heredoc classifier handles its body separately.
        return None if argument == "-" else argument
    return None


XARGS_OPTIONS_WITH_ARGS = frozenset(
    {
        "-a",
        "--arg-file",
        "-E",
        "--eof",
        "-I",
        "--replace",
        "-L",
        "--max-lines",
        "-n",
        "--max-args",
        "-P",
        "--max-procs",
        "--process-slot-var",
        "-d",
        "--delimiter",
        "-s",
        "--max-chars",
    }
)
XARGS_OPTIONS_NO_ARGS = frozenset(
    {
        "-0",
        "--null",
        "-r",
        "--no-run-if-empty",
        "-t",
        "--verbose",
        "-p",
        "--interactive",
        "--show-limits",
        "--version",
        "--help",
    }
)
# ``flock`` consumes a value for these options before its lock operand.  If
# the value is not skipped, a command such as ``flock -E 1 /tmp/lock git
# push`` is mis-parsed with ``1`` as the lock path and the Git command hidden
# from the nested scan.
FLOCK_OPTIONS_WITH_ARGS = frozenset(
    {
        "-w",
        "--wait",
        "-E",
        "--conflict-exit-code",
    }
)
FLOCK_OPTIONS_NO_ARGS = frozenset(
    {
        "-n",
        "--nonblock",
        "-s",
        "--shared",
        "-o",
        "--close",
        "-F",
        "--fcntl",
        "--verbose",
        "--help",
        "--version",
    }
)
# GNU ``chroot`` accepts both ``--option=value`` and separated option values
# for these options.  Keep the latter explicit so the NEWROOT operand is not
# mistaken for an option value and the command following it remains visible.
CHROOT_OPTIONS_WITH_ARGS = frozenset(
    {
        "-u",
        "-g",
        "--userspec",
        "--groups",
        "--chdir",
        "--directory",
    }
)
CHROOT_OPTIONS_NO_ARGS = frozenset({"--skip-chdir", "--help", "--version"})
# Common GNU parallel options which consume one argument.  Unknown options
# are rejected by the caller; keeping this grammar explicit prevents an
# option value from being mistaken for the nested command executable.
PARALLEL_OPTIONS_WITH_ARGS = frozenset(
    {
        "-j",
        "--jobs",
        "--max-procs",
        "--halt",
        "--load",
        "--memfree",
        "--delay",
        "--timeout",
        "--joblog",
        "--results",
        "--sshlogin",
        "--sshdelay",
        "--transferfile",
        "--return",
        "--cleanup",
        "--trc",
        "--basefile",
        "--arg-file",
        "--arg-sep",
        "--arg-sep-str",
        "--colsep",
        "--header",
        "--replace",
        "--rpl",
        "--shell",
        "--shellquote",
        "--tmpdir",
        "--workdir",
        "--env",
        "--block",
        "--blocksize",
        "--recend",
        "--recstart",
        "--filter",
        "--tagstring",
        "--group-by",
        "--process-slot-var",
        "--semaphoretimeout",
    }
)
PARALLEL_OPTIONS_NO_ARGS = frozenset(
    {
        "--will-cite",
        "--pipe",
        "--pipe-part",
        "--pipepart",
        "--round-robin",
        "--ungroup",
        "--group",
        "--keep-order",
        "--line-buffer",
        "--tag",
        "--dry-run",
        "--verbose",
        "--plain",
        "--semaphore",
        "--fg",
        "--nonall",
        "--onall",
        "--all",
        "--citation",
        "--help",
        "--version",
    }
)
# ``watch`` accepts an interval value before the command.  Keep this small
# grammar explicit so ``watch -n 1 git push`` cannot be mistaken for a probe
# of the literal token ``1``.
WATCH_OPTIONS_WITH_ARGS = frozenset({"-n", "--interval"})
WATCH_OPTIONS_NO_ARGS = frozenset(
    {
        "-b",
        "--beep",
        "-c",
        "--color",
        "-d",
        "--differences",
        "-e",
        "--errexit",
        "-g",
        "--chgexit",
        "-p",
        "--precise",
        "-t",
        "--no-title",
        "-x",
        "--exec",
        "--no-linewrap",
        "--help",
        "--version",
    }
)
WRAPPER_OPTIONS_WITH_ARGS = {
    "setsid": frozenset(),
    "busybox": frozenset(),
    "daemonize": frozenset({"-p", "--pidfile", "-o", "--stdout", "-e", "--stderr"}),
    "nsenter": frozenset(
        {
            "-t",
            "--target",
            "-C",
            "--cgroup",
            "-S",
            "--setuid",
            "-G",
            "--setgid",
        }
    ),
    "unshare": frozenset(
        {
            "--setgroups",
            "--map-users",
            "--map-groups",
            "--setuid",
            "--setgid",
            "--propagation",
            "--monotonic",
            "--boottime",
        }
    ),
    "systemd-run": frozenset(
        {
            "--unit",
            "--description",
            "--slice",
            "--property",
            "-p",
            "--service-type",
            "--working-directory",
            "-E",
            "--setenv",
            "--uid",
            "--gid",
            "--nice",
            "--signal",
            "--kill-mode",
            "--timeout-start-sec",
            "--timeout-stop-sec",
        }
    ),
}
WRAPPER_OPTIONS_NO_ARGS = {
    "setsid": frozenset({"-f", "--fork", "--wait", "-w"}),
    "busybox": frozenset({"--install", "--list", "--help", "--version"}),
    "nsenter": frozenset(
        {
            "-m",
            "--mount",
            "-u",
            "--uts",
            "-i",
            "--ipc",
            "-n",
            "--net",
            "-p",
            "--pid",
            "-U",
            "--user",
            "-C",
            "--cgroup",
            "--fork",
            "--preserve-credentials",
        }
    ),
    "unshare": frozenset(
        {
            "-m",
            "--mount",
            "-u",
            "--uts",
            "-i",
            "--ipc",
            "-n",
            "--net",
            "-p",
            "--pid",
            "-U",
            "--user",
            "-f",
            "--fork",
            "--kill-child",
            "--mount-proc",
            "--keep-caps",
            "--map-root-user",
            "--map-current-user",
            "--map-auto",
        }
    ),
    "daemonize": frozenset({"-c", "--core", "-z", "--zeros"}),
    "systemd-run": frozenset(
        {
            "--wait",
            "--pipe",
            "--pty",
            "--quiet",
            "--collect",
            "--service-type=oneshot",
            "--shell",
            "--user",
            "--system",
        }
    ),
}


def _first_non_option_command(
    arguments: list[str],
    *,
    option_args: frozenset[str] = frozenset(),
    option_no_args: frozenset[str] = frozenset(),
    reject_unknown: bool = False,
) -> int | None:
    """Return an index of the first command token after wrapper options."""

    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            return index + 1 if index + 1 < len(arguments) else None
        if not argument.startswith("-"):
            return index
        option = argument.split("=", 1)[0]
        if option in option_args and "=" not in argument:
            index += 2
        elif option in option_no_args:
            index += 1
        elif reject_unknown:
            # Returning -1 distinguishes an unrecognised option from a
            # wrapper invocation with no command.  Callers treat this as an
            # ambiguous executable graph and fail closed.
            return -1
        else:
            index += 1
    return None


def _shell_graph_wrapper_mutates(
    tokens: list[str], executable_index: int, *, depth: int
) -> bool:
    """Audit wrappers which execute a nested command or delayed trap body."""

    if executable_index < 0 or executable_index >= len(tokens):
        return False
    executable = _executable_basename(tokens[executable_index])
    if executable not in SHELL_GRAPH_WRAPPERS:
        return False
    if depth >= 2:
        # Nested wrappers are executable command graphs; do not recurse
        # indefinitely while preserving the fail-closed boundary.
        return True
    arguments = tokens[executable_index + 1 :]

    def scan_nested(values: list[str]) -> bool:
        if not values:
            return False
        first = values[0]
        if _shell_token_has_expansion(first):
            return True
        # ``trap``/``flock -c`` expose one already-parsed shell program as a
        # single token (for example ``"git push"``).  Joining that token with
        # :func:`shlex.join` would quote the whole program and turn an actual
        # command into inert data; preserve it verbatim in the one-token case.
        nested = values[0] if len(values) == 1 else shlex.join(values)
        return _contains_mutation(nested, _depth=depth + 1)

    if executable == "trap":
        # ``trap -p``/``trap -l`` print definitions.  Other forms carry a
        # shell program as their first non-option argument; inspect it as a
        # nested command so ``trap 'git push' EXIT`` cannot hide a mutation.
        if arguments and arguments[0] in {"-p", "-l", "--list"}:
            return False
        for argument in arguments:
            if argument.startswith("-") or argument.upper() in {
                "EXIT",
                "ERR",
                "DEBUG",
                "RETURN",
                "SIGINT",
                "SIGTERM",
                "SIGHUP",
                "SIGQUIT",
            }:
                continue
            if scan_nested([argument]):
                return True
            # The first non-option is the command body; trailing signal names
            # are not executable.  A literal harmless body is allowed.
            break
        return False

    if executable == "find":
        # ``-delete`` mutates the searched tree directly.  ``-exec``/``-ok``
        # forms execute an arbitrary command after the expression.
        exec_markers = {"-exec", "-execdir", "-ok", "-okdir"}
        for index, argument in enumerate(arguments):
            if argument == "-delete":
                return True
            if argument not in exec_markers:
                continue
            payload = arguments[index + 1 :]
            if not payload:
                return True
            # ``find -execdir -- COMMAND ...`` uses ``--`` as an end-of
            # options marker for the nested utility.  It is not itself an
            # executable; skipping it keeps the following command graph
            # visible to the recursive scanner.
            if payload and payload[0] == "--":
                payload = payload[1:]
            if not payload:
                return True
            if payload and payload[0] in {";", "+"}:
                return True
            if scan_nested(payload):
                return True
        return False

    if executable == "xargs":
        # xargs defaults to ``echo`` when no command is supplied.  Locate an
        # explicit command after its bounded option grammar; a dynamic or
        # incomplete command is not a source-level proof.
        index = _first_non_option_command(
            arguments,
            option_args=XARGS_OPTIONS_WITH_ARGS,
            option_no_args=XARGS_OPTIONS_NO_ARGS,
            reject_unknown=True,
        )
        if index == -1:
            return True
        # The shell tokenizer keeps braces as punctuation so compact
        # replacement options (``-I{} ``) arrive as ``-I { }``.  They are
        # option payload syntax, not the command; skip those punctuation
        # fragments before selecting the nested executable.
        while index is not None and index < len(arguments) and arguments[index] in {
            "{",
            "}",
        }:
            index += 1
        if index is None:
            return False
        command = arguments[index:]
        if command and command[0] == "--":
            command = command[1:]
        return scan_nested(command)

    if executable == "parallel":
        index = _first_non_option_command(
            arguments,
            option_args=PARALLEL_OPTIONS_WITH_ARGS,
            option_no_args=PARALLEL_OPTIONS_NO_ARGS,
            reject_unknown=True,
        )
        if index == -1:
            return True
        if index is None:
            return False
        command = arguments[index:]
        if ":::" in command:
            marker = command.index(":::")
            # With no command before ``:::`` GNU parallel derives commands
            # from the input words.  That command graph is not statically
            # attributable (``parallel ::: git push`` is a classic hiding
            # shape), so reject it rather than treating the trailing words as
            # inert data.  A literal command before the marker is scanned
            # normally; its input arguments remain data.
            if marker == 0:
                return True
            command = command[:marker]
        return scan_nested(command)

    if executable == "flock":
        # ``flock -c 'git push'`` carries a shell string; otherwise the first
        # non-option token is the lock path and the following token starts the
        # command (fd forms such as ``flock 9 git push`` are covered too).
        for index, argument in enumerate(arguments):
            if argument in {"-c", "--command"}:
                if index + 1 >= len(arguments):
                    return True
                return scan_nested([arguments[index + 1]])
            if argument.startswith("--command="):
                return scan_nested([argument.split("=", 1)[1]])
        lock_index = _first_non_option_command(
            arguments,
            option_args=FLOCK_OPTIONS_WITH_ARGS,
            option_no_args=FLOCK_OPTIONS_NO_ARGS,
            reject_unknown=True,
        )
        if lock_index == -1:
            return True
        if lock_index is None or lock_index + 1 >= len(arguments):
            return False
        command = arguments[lock_index + 1 :]
        # The optional ``--`` after the lock operand terminates flock's
        # options; it belongs to flock rather than to the wrapped command.
        if command and command[0] == "--":
            command = command[1:]
        if not command:
            return True
        return scan_nested(command)

    if executable == "chroot":
        root_index = _first_non_option_command(
            arguments,
            option_args=CHROOT_OPTIONS_WITH_ARGS,
            option_no_args=CHROOT_OPTIONS_NO_ARGS,
            reject_unknown=True,
        )
        if root_index == -1:
            return True
        if root_index is None:
            return True
        if root_index + 1 >= len(arguments):
            # chroot with no command launches the target's default shell.
            return True
        command = arguments[root_index + 1 :]
        if command and command[0] == "--":
            command = command[1:]
        if not command:
            # A terminator without a command is malformed/ambiguous; keep the
            # source gate fail-closed rather than silently accepting it.
            return True
        return scan_nested(command)

    if executable == "coproc":
        # Bash accepts both ``coproc COMMAND`` and ``coproc NAME COMMAND``.
        # Scan the complete tail first (covering the unnamed form), then scan
        # past a plausible identifier so a named form such as
        # ``coproc worker git push`` cannot hide the nested Git executable.
        if not arguments:
            return True
        command = arguments
        if command and command[0] == "--":
            command = command[1:]
        if not command:
            return True
        if scan_nested(command):
            return True
        if len(arguments) > 1 and re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*", arguments[0]
        ):
            command = arguments[1:]
            if command and command[0] == "--":
                command = command[1:]
            if not command:
                return True
            return scan_nested(command)
        return False

    if executable in {"at", "batch"}:
        # These commands schedule shell source for later execution.  ``at``
        # list/show modes are observational; every other form either reads a
        # command from stdin (often an unmarked heredoc) or executes a file.
        if executable == "at" and any(
            argument in {"-l", "--list", "-q", "--queue"} for argument in arguments
        ) and not any(
            argument in {"-f", "--file"} for argument in arguments
        ):
            return False
        for index, argument in enumerate(arguments):
            if argument in {"-f", "--file"}:
                if index + 1 >= len(arguments):
                    return True
                return _script_path_invocation_mutates(arguments[index + 1])
            if argument.startswith("--file="):
                return _script_path_invocation_mutates(argument.split("=", 1)[1])
        # ``batch`` and ordinary ``at TIME`` consume stdin; without a static
        # body proof the scheduled command graph is inherently ambiguous.
        return True

    if executable == "crontab":
        # Installing/replacing a crontab is an external authority boundary.
        # Listing is read-only; all other forms fail closed, including a
        # dynamically selected file whose contents could contain Git/HTTP.
        if arguments and arguments[0] in {"-l", "--list"}:
            return False
        return True

    if executable == "watch":
        # Keep watch's option grammar explicit.  An unknown option may alter
        # how the command is interpreted (or select a future execution mode),
        # so fail closed instead of skipping one token and potentially
        # mistaking an option value for the command.
        index = 0
        while index < len(arguments):
            argument = arguments[index]
            if argument == "--":
                index += 1
                break
            if not argument.startswith("-") or argument == "-":
                break
            option = argument.split("=", 1)[0]
            if option in WATCH_OPTIONS_WITH_ARGS:
                # GNU watch also accepts the compact ``-n1`` spelling.
                if option == "-n" and len(argument) > 2 and "=" not in argument:
                    index += 1
                    continue
                if "=" not in argument:
                    if index + 1 >= len(arguments):
                        return True
                    interval = arguments[index + 1]
                    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", interval):
                        return True
                    index += 2
                else:
                    interval = argument.split("=", 1)[1]
                    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", interval):
                        return True
                    index += 1
                continue
            if option in WATCH_OPTIONS_NO_ARGS:
                index += 1
                continue
            return True
        if index >= len(arguments):
            return False
        return scan_nested(arguments[index:])

    # ``setsid``, ``busybox``, ``nsenter``, ``unshare``, ``systemd-run`` and
    # ``daemonize`` all execute the first non-option command.  Their options
    # are bounded above; unknown options are rejected so an option value
    # cannot hide a dynamic command token from ``scan_nested``.
    option_args = WRAPPER_OPTIONS_WITH_ARGS.get(executable, frozenset())
    option_no_args = WRAPPER_OPTIONS_NO_ARGS.get(executable, frozenset())
    index = _first_non_option_command(
        arguments,
        option_args=option_args,
        option_no_args=option_no_args,
        reject_unknown=True,
    )
    if index == -1:
        return True
    if index is None:
        return False
    return scan_nested(arguments[index:])
SHELL_INTERPRETER_LONG_OPTIONS = frozenset(
    {
        # Bash/sh boolean options which may precede ``-c``.  They do not
        # consume the following token, so the payload parser must continue
        # past them instead of mistaking the option for a script path.
        "--debug",
        "--debugger",
        "--dump-po-strings",
        "--help",
        "--login",
        "--noediting",
        "--noprofile",
        "--norc",
        "--posix",
        "--pretty-print",
        "--privileged",
        "--rcfile",
        "--restricted",
        "--verbose",
        "--version",
        "--wordexp",
    }
)


def _shell_interpreter_payload(
    tokens: list[str], executable_index: int
) -> tuple[str | None, bool]:
    """Return a shell ``-c`` payload and whether it is dynamically formed.

    Short option clusters (``bash -lc``/``sh -ec``), long command options,
    and option arguments are handled explicitly.  An absent payload is an
    ambiguity, not evidence of a harmless invocation.
    """

    arguments = tokens[executable_index + 1 :]
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        # Startup files and interactive/login modes execute code outside this
        # payload and are controlled by the runner environment.
        if argument in {"--rcfile", "--init-file", "--startup-file", "--login", "-i"}:
            return "", True
        if argument.startswith(("--rcfile=", "--init-file=", "--startup-file=")):
            return "", True
        if argument.startswith("-") and not argument.startswith("--") and "i" in argument[1:]:
            return "", True
        if argument == "--":
            # Everything after ``--`` is a script name/argument, not an
            # interpreter option.  In particular, do not mistake a script
            # argument named ``-c`` for a shell command payload.
            if (
                index + 1 < len(arguments)
                and arguments[index + 1] != "-"
                and arguments[index + 1].startswith("-")
            ):
                # An option-looking first script name (for example
                # ``bash -- -c ...``) is still a filesystem script operand,
                # not a command string.  Its provenance cannot be proven
                # read-only; mark the interpreter form ambiguous instead of
                # silently skipping it.
                return "", True
            return None, False
        if argument in {"-c", "--command"}:
            if index + 1 >= len(arguments):
                return "", True
            payload = arguments[index + 1]
            return payload, _shell_token_has_expansion(payload)
        if argument.startswith("--command="):
            payload = argument.split("=", 1)[1]
            return payload, _shell_token_has_expansion(payload)
        if argument in SHELL_INTERPRETER_OPTIONS_NO_ARGS:
            index += 1
            continue
        if argument.startswith("--"):
            option = argument.split("=", 1)[0]
            if option in SHELL_INTERPRETER_OPTIONS_WITH_ARGS or option in {
                "--rcfile",
                "--init-file",
                "--startup-file",
            }:
                # ``--rcfile FILE`` (and its aliases) consume one argument;
                # an absent argument is ambiguous and must fail closed.
                if "=" not in argument:
                    if index + 1 >= len(arguments):
                        return "", True
                    index += 2
                else:
                    index += 1
                continue
            # Known boolean options and unknown long options are skipped one
            # token at a time.  Unknown options are intentionally not treated
            # as proof of safety; if they are followed by a non-option script
            # path the function returns ``None`` below and the caller applies
            # the external-script/ambiguity policy.
            if option in SHELL_INTERPRETER_LONG_OPTIONS or option.startswith("--"):
                index += 1
                continue
        if argument.startswith("-") and not argument.startswith("--"):
            short_options = argument[1:]
            if "c" in short_options:
                position = short_options.index("c")
                suffix = short_options[position + 1 :]
                if suffix:
                    return suffix, _shell_token_has_expansion(suffix)
                if index + 1 >= len(arguments):
                    return "", True
                payload = arguments[index + 1]
                return payload, _shell_token_has_expansion(payload)
            if argument in SHELL_INTERPRETER_OPTIONS_WITH_ARGS:
                index += 2
                continue
            index += 1
            continue
        # The first non-option is a script/command argument, not an option
        # payload.  Leave it to the external-script policy below.
        break
    return None, False


def _shell_payload_expansion_is_reviewed(payload: str) -> bool:
    """Return whether command-position expansions in *payload* are trusted.

    ``_shell_interpreter_payload`` conservatively marks any expansion in a
    ``bash -c`` string as dynamic.  Argument-only expansions (for example
    ``echo "$PWD/log"``) are harmless, while an exact reviewed script/tool
    path (``$PWD/tools/reject_symlink_path.sh``) is also statically bounded.
    This helper narrows the dynamic rejection to executable positions without
    weakening the fail-closed rule for unknown roots.
    """

    for tokens in _shell_command_tokens(payload, strip_comments=True):
        for start in _shell_command_start_indices(tokens):
            index = _shell_executable_index(tokens, start)
            if index >= len(tokens):
                continue
            token = tokens[index]
            if not _shell_token_has_expansion(token):
                continue
            if _script_path_key(token) is None and not _dynamic_path_executable_is_allowed(
                token
            ):
                return False
    return True


def _shell_unescape_legacy_backticks(value: str) -> str:
    """Unescape odd backslash runs before legacy nested backticks."""
    output: list[str] = []
    index = 0
    while index < len(value):
        if value[index] != "\\":
            output.append(value[index])
            index += 1
            continue
        end = index
        while end < len(value) and value[end] == "\\":
            end += 1
        run = value[index:end]
        if end < len(value) and value[end] == "`" and len(run) % 2 == 1:
            output.append(run[:-1])
            output.append("`")
            index = end + 1
        else:
            output.append(run)
            index = end
    return "".join(output)

def _shell_substitution_payloads(command: str) -> tuple[list[str], bool]:
    """Extract shell ``$(...)``/backtick payloads outside single quotes.

    Tokenization with ``shlex`` can split a parameter expansion such as
    ``${name:-$(git push)}`` at the nested parentheses.  A small raw lexer
    preserves that execution edge while still ignoring quoted prose and
    comments.  The boolean result marks an unterminated substitution, which
    is treated as ambiguous by the caller.
    """

    payloads: list[str] = []
    malformed = False
    index = 0
    quote: str | None = None
    comment = False
    escaped = False
    while index < len(command):
        character = command[index]
        if comment:
            if character in "\r\n":
                comment = False
            index += 1
            continue
        if quote == "'":
            if character == "'":
                quote = None
            index += 1
            continue
        if quote == '"':
            if escaped:
                escaped = False
                index += 1
                continue
            if character == "\\":
                escaped = True
                index += 1
                continue
            if character == '"':
                quote = None
                index += 1
                continue
        else:
            if character == "\\":
                index += 2
                continue
            if character in {"'", '"'}:
                quote = character
                index += 1
                continue
            if character == "#" and (
                index == 0
                or command[index - 1].isspace()
                or command[index - 1] in ";|&(){}<>"
            ):
                comment = True
                index += 1
                continue
        if character == "$" and index + 1 < len(command) and command[index + 1] == "(":
            start = index + 2
            cursor = start
            depth = 1
            nested_quote: str | None = None
            nested_escaped = False
            while cursor < len(command):
                current = command[cursor]
                if nested_quote is not None:
                    if nested_escaped:
                        nested_escaped = False
                    elif current == "\\":
                        nested_escaped = True
                    elif current == nested_quote:
                        nested_quote = None
                    cursor += 1
                    continue
                if current in {"'", '"'}:
                    nested_quote = current
                elif current == "(" :
                    depth += 1
                elif current == ")":
                    depth -= 1
                    if depth == 0:
                        payloads.append(command[start:cursor])
                        index = cursor + 1
                        break
                cursor += 1
            else:
                payloads.append(command[start:])
                malformed = True
                break
            continue
        if character == "`":
            cursor = index + 1
            nested_escaped = False
            while cursor < len(command):
                current = command[cursor]
                if nested_escaped:
                    nested_escaped = False
                elif current == "\\":
                    nested_escaped = True
                elif current == "`":
                    payload = command[index + 1 : cursor]
                    payloads.append(payload)
                    normalized = _shell_unescape_legacy_backticks(payload)
                    if normalized != payload:
                        payloads.append(normalized)
                    index = cursor + 1
                    break
                cursor += 1
            else:
                payloads.append(command[index + 1 :])
                malformed = True
                break
            continue
        index += 1
    return payloads, malformed


def _shell_process_substitution_payloads(command: str) -> tuple[list[str], bool]:
    """Extract Bash process-substitution payloads outside quoted text.

    ``<(...)`` and ``>(...)`` start a second command graph even when they are
    used as an argument to an otherwise harmless command (for example,
    ``diff <(git status) <(git push)``).  The shell tokeniser intentionally
    treats ``<``/``>`` as ordinary words, so relying on the incidental
    punctuation split for the inner command is fragile: quoting, nested
    parentheses, and malformed input can make the payload disappear.  Keep a
    small raw lexer here, analogous to :func:`_shell_substitution_payloads`,
    and let the normal bounded mutation scanner audit each extracted body.

    The lexer is deliberately conservative.  An unterminated or empty
    process substitution is reported as malformed and therefore rejected by
    the caller.  Shell comments, escapes, and quoted text are skipped in the
    outer command; the same rules are applied while balancing parentheses in
    the payload.  ``<<(...)``/``>>``-style redirections are not process
    substitution operators, so a second adjacent redirection character is
    excluded from the opener check.
    """

    payloads: list[str] = []
    malformed = False
    index = 0
    quote: str | None = None
    comment = False
    escaped = False

    while index < len(command):
        character = command[index]

        if comment:
            if character in "\r\n":
                comment = False
            index += 1
            continue

        if quote == "'":
            if character == "'":
                quote = None
            index += 1
            continue

        if quote == '"':
            if escaped:
                escaped = False
                index += 1
                continue
            if character == "\\":
                escaped = True
                index += 1
                continue
            if character == '"':
                quote = None
            index += 1
            continue

        if character == "\\":
            # An escaped ``<``/``>`` is data, not a process-substitution
            # operator.  Skip the escaped byte (and its following byte) as a
            # single lexical unit; a trailing backslash is simply consumed.
            index += 2
            continue
        if character in {"'", '"'}:
            quote = character
            index += 1
            continue
        if character == "#" and (
            index == 0
            or command[index - 1].isspace()
            or command[index - 1] in ";|&(){}<>"
        ):
            comment = True
            index += 1
            continue

        if (
            character in "<>"
            and index + 1 < len(command)
            and command[index + 1] == "("
            and (index == 0 or command[index - 1] not in "<>")
        ):
            start = index + 2
            cursor = start
            depth = 1
            nested_quote: str | None = None
            nested_comment = False
            nested_escaped = False

            while cursor < len(command):
                current = command[cursor]

                if nested_comment:
                    if current in "\r\n":
                        nested_comment = False
                    cursor += 1
                    continue

                if nested_quote == "'":
                    if current == "'":
                        nested_quote = None
                    cursor += 1
                    continue

                if nested_quote == '"':
                    if nested_escaped:
                        nested_escaped = False
                        cursor += 1
                        continue
                    if current == "\\":
                        nested_escaped = True
                        cursor += 1
                        continue
                    if current == '"':
                        nested_quote = None
                    cursor += 1
                    continue

                if current == "\\":
                    cursor += 2
                    continue
                if current in {"'", '"'}:
                    nested_quote = current
                    cursor += 1
                    continue
                if current == "#" and (
                    cursor == start
                    or command[cursor - 1].isspace()
                    or command[cursor - 1] in ";|&(){}<>"
                ):
                    nested_comment = True
                    cursor += 1
                    continue
                if current == "(":
                    depth += 1
                elif current == ")":
                    depth -= 1
                    if depth == 0:
                        payload = command[start:cursor]
                        if not payload.strip():
                            malformed = True
                        else:
                            payloads.append(payload)
                        index = cursor + 1
                        break
                cursor += 1
            else:
                # A process-substitution opener without a matching close is
                # malformed shell. Preserve the tail for diagnostics and fail
                # closed in the caller.
                payloads.append(command[start:])
                malformed = True
                break
            continue

        index += 1

    return payloads, malformed


def _dynamic_path_executable_is_allowed(token: str) -> bool:
    """Allow the small, reviewed set of dynamic tool paths used by D2I.

    D2I invokes the pinned external ``configure`` script and probes freshly
    built e2fsprogs binaries through runner paths.  Other dynamic command
    paths remain ambiguous and are rejected by the source gate.
    """

    value = token.strip("'\"").replace("\\", "/")
    if "/" not in value:
        return False
    basename = value.rsplit("/", 1)[-1]
    if not basename or _shell_token_has_expansion(basename):
        return False
    # Basenames are case-sensitive on the Linux runners used by every
    # qualifying workflow.  Do not let a look-alike such as ``MKE2FS`` inherit
    # the pinned-tool allowance.
    if basename not in DYNAMIC_PATH_ALLOWED_BASENAMES:
        return False

    # The configure script is the checked-out e2fsprogs source entry point;
    # permit only that exact workspace-relative shape.  The installed tools
    # are addressed through the D2I ``prefix/sbin`` directory.  Restricting
    # both forms prevents ``$evil/configure`` and ``$evil/mke2fs`` from being
    # mistaken for the pinned toolchain merely because their basenames match.
    if basename == "configure":
        return value in {
            "$GITHUB_WORKSPACE/e2fsprogs-source/configure",
            "${GITHUB_WORKSPACE}/e2fsprogs-source/configure",
            "${{ github.workspace }}/e2fsprogs-source/configure",
            "${{github.workspace}}/e2fsprogs-source/configure",
        }

    prefix = value.rsplit("/", 1)[0]
    if not prefix.endswith("/sbin"):
        return False
    # Keep the root exact.  ``$prefix`` is the reviewed D2I install prefix;
    # the workspace expression is accepted for explicit absolute probes in
    # future workflow revisions, but arbitrary variables are not.
    return prefix in {"$prefix/sbin", "${prefix}/sbin"}


def _shell_is_executable_probe(prefix: list[str]) -> bool:
    """Return whether a wrapper is only probing an executable name."""

    # ``command -p`` is *not* a probe: POSIX ``command`` uses ``-p`` to alter
    # PATH lookup and then executes the following command.  The old generic
    # flag test treated it like ``type -P`` and skipped a real ``command -p
    # git push`` invocation.  Keep probe flags scoped to each utility.
    for index, item in enumerate(prefix):
        executable = _executable_basename(item)
        tail = [value.lower() for value in prefix[index + 1 :]]
        if executable == "command":
            if any(value in {"-v", "-V", "--verbose"} for value in tail):
                return True
        elif executable in {"type", "which", "where"}:
            if any(
                value in {"-v", "-p", "-a", "-ap", "--version", "--path"}
                for value in tail
            ):
                return True
    return False


def _shell_git_command_indices(tokens: list[str]) -> list[int]:
    """Return Git executable indexes that begin actual shell commands."""

    indexes: list[int] = []
    for start in _shell_command_start_indices(tokens):
        index = _shell_executable_index(tokens, start)
        if index < len(tokens) and _is_git_executable_or_helper(tokens[index]):
            # ``command -v git``/``type -P git`` are executable discovery
            # probes, not invocations of the Git binary. Do not interpret the
            # probed name as a subcommand.
            if _shell_is_executable_probe(tokens[start:index]):
                continue
            indexes.append(index)
    return indexes


def _github_invocation_mutates(tokens: list[str], executable_index: int) -> bool:
    """Return whether a GitHub CLI invocation is not statically harmless.

    GitHub CLI has a broad and extensible command surface.  The governance
    workflow does not need it, so the source gate permits only version/help
    probes and rejects every other command (including a dynamic subcommand or
    an alias-expanded invocation) rather than maintaining an incomplete
    mutation allow-list.
    """

    if executable_index < 0 or executable_index >= len(tokens):
        return False
    if _executable_basename(tokens[executable_index]) not in GH_EXECUTABLES:
        return False
    arguments = tokens[executable_index + 1 :]
    if not arguments:
        return True
    # Keep the harmless surface deliberately exact.  ``gh --help`` and
    # ``gh version`` are probes; adding another argument can select an alias,
    # endpoint, or extension and therefore is not a proof of read-only
    # behavior.
    if len(arguments) == 1 and arguments[0].lower() in {
        "--version",
        "-v",
        "--help",
        "-h",
        "help",
        "version",
    }:
        return False
    # Unknown/all-option invocations can select a mutating default through
    # environment/configuration; fail closed.
    return True


def _http_invocation_mutates(tokens: list[str], executable_index: int) -> bool:
    """Reject curl/wget requests whose method or body is not read-only."""

    if executable_index < 0 or executable_index >= len(tokens):
        return False
    if _executable_basename(tokens[executable_index]) not in HTTP_EXECUTABLES:
        return False
    arguments = tokens[executable_index + 1 :]
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        lowered = argument.lower()
        method: str | None = None
        # ``-X`` is case-sensitive in curl; lower-case ``-x`` is the proxy
        # option and must not be mistaken for a method selector.
        if argument == "-X" or lowered in {"--request", "--method"}:
            if "=" in argument:
                method = argument.split("=", 1)[1].strip("'\"")
            elif index + 1 < len(arguments):
                index += 1
                method = arguments[index].strip("'\"")
            else:
                return True
        elif argument.startswith("-X") and len(argument) > 2:
            # curl accepts compact ``-XPOST``/``-X$METHOD`` forms.
            method = argument[2:]
        else:
            for flag in ("--request", "--method"):
                if lowered.startswith(flag) and len(argument) > len(flag):
                    suffix = argument[len(flag) :]
                    method = suffix[1:] if suffix.startswith("=") else suffix
                    break
        if method is not None:
            if _shell_token_has_expansion(method):
                return True
            if method.upper() not in {"GET", "HEAD", "OPTIONS"}:
                return True
        elif (
            # Attached long forms such as `--header${HEADER}` are either
            # dynamic or malformed.  A source-only scan cannot prove their
            # value is a harmless header, so reject every non-`=` attached
            # spelling before it can consume the following URL as its value.
            lowered.startswith("--header")
            and len(argument) > len("--header")
            and not lowered.startswith("--header=")
        ):
            return True
        elif argument in {"-H", "--header"} or lowered.startswith("--header="):
            header = ""
            if "=" in argument:
                header = argument.split("=", 1)[1].strip("'\"")
            elif index + 1 < len(arguments):
                index += 1
                header = arguments[index].strip("'\"")
            # An unresolved header can inject ``X-HTTP-Method-Override`` (or
            # another transport-specific write control) even when no literal
            # ``-X`` flag is present.  Static source cannot prove its value,
            # so reject dynamic header payloads just like dynamic methods.
            if (
                _shell_token_has_expansion(header)
                or header.startswith("@")
                or header.startswith("$")
                or "{" in header
                or "}" in header
            ):
                return True
            if re.search(r"(?i)(?:method-override|^:method\s*:)", header):
                if _shell_token_has_expansion(header) or re.search(
                    r"(?i)\b(?:post|put|patch|delete)\b", header
                ):
                    return True
        elif (
            argument in {"-d", "-F", "-K", "-T", "-t"}
            or any(
                argument.startswith(prefix)
                for prefix in ("-d", "-F", "-K", "-T", "-t")
            )
            # Long curl/wget body/config options accept both a separate
            # value and an ``--option=value`` spelling.  Comparing only the
            # bare option (the old check) let forms such as
            # ``--body-data=...``/``--config-file=...`` bypass the mutation
            # gate and potentially select a POST/configured write.
            or any(
                lowered == item.lower()
                or lowered.startswith(f"{item.lower()}=")
                or (
                    lowered.startswith(item.lower())
                    and len(argument) > len(item)
                    and _shell_token_has_expansion(argument[len(item) :])
                )
                for item in HTTP_DATA_FLAGS
                if item.startswith("--")
            )
        ):
            return True
        index += 1
    return False


def _direct_http_invocation_mutates(tokens: list[str], executable_index: int) -> bool:
    """Reject a bare HTTP method command targeting a URL.

    A few workflow tools use tiny wrappers that expose ``POST URL`` (rather
    than ``curl -X POST URL``).  Keep the historical direct-method guard, but
    evaluate it only at an actual command position so prose, comments, and
    heredoc payloads cannot trigger the policy.
    """

    if executable_index < 0 or executable_index >= len(tokens):
        return False
    method = tokens[executable_index].upper()
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False
    return (
        executable_index + 1 < len(tokens)
        and re.match(r"(?i)^https?://", tokens[executable_index + 1]) is not None
    )


def _shell_variable_name(token: str) -> str | None:
    """Return a simple variable name for an exact shell expansion."""

    match = re.fullmatch(r"\$([A-Za-z_][A-Za-z0-9_]*)|\$\{([A-Za-z_][A-Za-z0-9_]*)\}", token)
    if match is None:
        return None
    return match.group(1) or match.group(2)


def _shell_literal_assignments(command: str) -> dict[str, str]:
    """Collect simple literal shell assignments in source order.

    This is deliberately bounded and lexical.  It is used only to prove that
    ``x=git; $x status`` is equivalent to a known read-only invocation; an
    unresolved or compound assignment is never treated as safe.
    """

    values: dict[str, str] = {}
    for tokens in _shell_command_tokens(command, strip_comments=True):
        for token in tokens:
            match = SHELL_ASSIGNMENT.fullmatch(token)
            if match is None:
                continue
            name, value = match.groups()
            value = value.strip("'\"")
            if (
                not value
                or _shell_token_has_expansion(value)
                or any(character.isspace() for character in value)
                or value.startswith("(")
            ):
                values.pop(name, None)
            else:
                values[name] = value
    return values


def _shell_record_assignment(values: dict[str, str], token: str) -> None:
    """Apply one simple assignment to a shell variable environment model."""

    match = SHELL_ASSIGNMENT.fullmatch(token)
    if match is None:
        return
    name, value = match.groups()
    value = value.strip("'\"")
    if (
        not value
        or _shell_token_has_expansion(value)
        or any(character.isspace() for character in value)
        or value.startswith("(")
    ):
        values.pop(name, None)
    else:
        values[name] = value


def _shell_update_assignments(tokens: list[str], values: dict[str, str]) -> None:
    """Update literal variable bindings in one shell command segment.

    The update is intentionally limited to shell assignments and declaration
    builtins. Environment assignments consumed by ``env`` are not shell
    bindings and therefore are left untouched. Handling ``unset`` prevents a
    stale earlier literal from making a later dynamic executable appear safe.
    """

    index = 0
    while index < len(tokens) and SHELL_ASSIGNMENT.fullmatch(tokens[index]):
        _shell_record_assignment(values, tokens[index])
        index += 1

    if index < len(tokens) and tokens[index].lower() in {
        "export",
        "declare",
        "local",
        "readonly",
        "typeset",
    }:
        index += 1
        while index < len(tokens):
            token = tokens[index]
            if token.startswith("-"):
                index += 1
                continue
            if SHELL_ASSIGNMENT.fullmatch(token):
                _shell_record_assignment(values, token)
            else:
                values.pop(token, None)
            index += 1
        return

    if index < len(tokens) and tokens[index].lower() == "unset":
        for token in tokens[index + 1 :]:
            if not token.startswith("-"):
                values.pop(token, None)


def _shell_is_test_command(tokens: list[str], index: int) -> bool:
    """Return whether a token position is a ``[``/``[[`` test expression."""

    if index >= len(tokens):
        return False
    if _executable_basename(tokens[index]) in {"[", "[[", "test"}:
        return True
    # Some malformed/complex shell fragments lose the opening bracket during
    # conservative tokenization.  Require a closing bracket before treating a
    # comparison operator as test data; looking only for ``-n``/``-z`` would
    # misclassify perfectly valid wrapper options such as ``flock -n``.
    if index == 0 and any(token in {"]", "]]"} for token in tokens[1:]):
        return True
    return False


def _shell_dynamic_mutates(command: str, *, depth: int) -> bool:
    """Reject shell forms whose executable/subcommand graph is dynamic.

    ``shlex`` intentionally treats variable expansions as opaque words.  That
    is useful for ordinary lexical matching, but it would let constructs such
    as ``x=git; $x push`` or ``git push${IFS}origin`` evade the mutation gate.
    Track simple literal executable assignments across command segments,
    expand the shell's standard ``IFS`` separator for a bounded re-scan, and
    inspect a short newline-spanning window.  Unknown dynamic executables are
    also rejected when followed by a mutating verb: the source cannot prove
    which binary the expansion resolves to.
    Ordinary argument expansions remain allowed (for example ``git rev-parse
    "$SHA"``).  Expansions at command or Git-subcommand positions, shell
    aliases/eval/configuration, and nested dynamic ``bash -c`` payloads are
    rejected because a source-only lexical scan cannot establish that they
    are read-only.
    """

    if depth > 2:
        return True

    # A command substitution assigned to a variable and then expanded as the
    # command word is an unresolved executable graph. Ordinary path
    # assignments remain allowed. Keep the pattern deliberately small and
    # inspect command segments without relying on shell quoting semantics.
    for assignment in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)=\$\(", command):
        if assignment.start() > 0 and command[assignment.start() - 1] not in " \t\r\n;&|":
            continue
        name = assignment.group(1)
        remainder = command[assignment.end() :]
        for segment in re.split(r"[;&|\r\n]", remainder):
            fields = segment.strip().split()
            if not fields:
                continue
            first = fields[0].strip("\"'")
            if first in {f"${name}", f"${{{name}}}"}:
                return True
    # Brace expansion can synthesize an otherwise unregistered executable or
    # script path before the shell tokenizer sees command boundaries.
    if _shell_brace_expansion_mutates(command):
        return True

    # A command substitution/backtick can emit ``git`` (or any other mutating
    # helper) without leaving a literal executable token for shlex to inspect.
    # Parse the raw shell text as well as the token stream so substitutions
    # nested inside ``${var:-$(...)}`` are not split away.  Single-quoted prose
    # and comments are ignored by the lexer.
    if SHELL_COMMAND_SUBSTITUTION_EXECUTABLE.search(command):
        return True
    substitutions, malformed_substitution = _shell_substitution_payloads(command)
    if malformed_substitution:
        return True
    if depth < 2:
        for payload in substitutions:
            if _contains_mutation(payload, _depth=depth + 1):
                return True

    # Bash process substitutions (``<(...)``/``>(...)``) launch their payload
    # asynchronously before the outer command runs.  They are an independent
    # command graph, not ordinary redirection data; audit each body with the
    # same bounded scanner used for ``$(...)``.  At the recursion ceiling an
    # otherwise uninspected process graph is ambiguous, so fail closed.
    process_substitutions, malformed_process_substitution = (
        _shell_process_substitution_payloads(command)
    )
    if malformed_process_substitution:
        return True
    if process_substitutions:
        if depth >= 2:
            return True
        for payload in process_substitutions:
            if _contains_mutation(payload, _depth=depth + 1):
                return True

    # Field-splitting can concatenate a mutating verb and its arguments into a
    # single token.  Replacing only the exact IFS forms keeps GitHub expression
    # syntax (``${{ ... }}``) untouched.
    # Field splitting can hide any effectful command, not only Git.  Expand
    # the exact IFS forms unconditionally; the recursive scanner is bounded
    # and harmless commands simply return false.  This also closes direct
    # HTTP forms such as ``POST${IFS}https://...`` and ``curl${IFS}-X...``.
    if SHELL_IFS_EXPANSION.search(command):
        expanded = SHELL_IFS_EXPANSION.sub(" ", command)
        if expanded != command and _contains_mutation(expanded, _depth=depth + 1):
            return True

    if SHELL_CONFIG_ASSIGNMENT.search(command):
        # GIT_CONFIG_COUNT/KEY/VALUE can install a ``!`` alias without an
        # explicit ``git -c`` argument; PATH/GIT_* can redirect helpers,
        # object stores, hooks, or transport commands.
        return True

    # Aliases, function bodies, and ``eval``/sourced scripts are executable
    # graphs outside this lexical proof.  Reject them unless the source is the
    # single reviewed helper that contains no Git command and is used by D2I.
    if SHELL_ALIAS_COMMAND.search(command):
        return True
    for match in SHELL_SOURCE_COMMAND.finditer(command):
        path = match.group("path").strip("'\"")
        if _script_path_key(path) != "tools/reject_symlink_path.sh":
            return True

    assignments: dict[str, str] = {}
    for tokens in _shell_command_tokens(command, strip_comments=True):
        # Validate assignments to any variable which may later serve as a
        # reviewed script/tool root before resolving command positions.  This
        # closes the provenance hole where an arbitrary directory is assigned
        # to ``validation_root`` or ``prefix`` and then combined with an
        # otherwise approved suffix.
        for assignment in _shell_root_assignment_tokens(tokens):
            if not _reviewed_root_assignment_safe(assignment):
                name_match = SHELL_ASSIGNMENT.fullmatch(assignment)
                name = name_match.group(1) if name_match is not None else ""
                if name in REVIEWED_PATH_ROOT_VARIABLES | DYNAMIC_TOOL_ROOT_VARIABLES:
                    return True
        _shell_update_assignments(tokens, assignments)
        for start in _shell_command_start_indices(tokens):
            # GNU ``env -S/--split-string`` executes a command encoded in the
            # following string.  Treat the string as an opaque shell payload:
            # attempting to tokenise it as an ordinary executable can hide a
            # mutation (for example ``env -S \"git push\"``).  No reviewed
            # workflow needs this form, so fail closed whenever it appears at
            # a command position.
            raw_index = start
            while raw_index < len(tokens) and SHELL_ASSIGNMENT.fullmatch(
                tokens[raw_index]
            ):
                raw_index += 1
            if raw_index < len(tokens) and _executable_basename(
                tokens[raw_index]
            ) == "env":
                if any(
                    argument == "-S"
                    or argument == "--split-string"
                    or argument.startswith("--split-string=")
                    for argument in tokens[raw_index + 1 :]
                ):
                    return True
            index = _shell_executable_index(tokens, start)
            if index >= len(tokens):
                continue
            if _shell_is_test_command(tokens, index):
                continue
            token = tokens[index]
            executable = _executable_basename(token)

            # A wrapper can execute a nested command or delay it until a
            # signal fires.  Audit these command-graph edges before the
            # ordinary Git/GH/HTTP checks, which only see the wrapper token.
            if _shell_graph_wrapper_mutates(tokens, index, depth=depth):
                return True

            # Direct script paths and interpreter script arguments are
            # executable policy inputs.  Permit only the reviewed workflow
            # inventory (or the narrow pinned-tool basename exception); an
            # unregistered path could hide a repository mutation in a file
            # that this lexical scanner never opens.
            if _script_path_invocation_mutates(token):
                return True
            if executable in SHELL_INTERPRETERS | PYTHON_INTERPRETERS:
                script_argument = _interpreter_script_argument(tokens, index)
                if script_argument is not None and _script_path_invocation_mutates(
                    script_argument
                ):
                    return True

            # An array expansion in command position can combine independently
            # assigned executable and subcommand elements (``cmd=(git);
            # "${cmd[@]}" push``). Array references inside ``[[ ... ]]`` are
            # excluded above because they are test data, not commands.
            if SHELL_ARRAY_EXPANSION.search(token):
                return True

            # ``alias`` and ``eval`` alter the command graph at runtime.
            if executable in {"alias", "eval"}:
                return True

            # A simple variable executable can be proven safe only when its
            # assignment is literal.  Resolve it before checking the Git verb
            # so a dynamic subcommand (``g=git; v=push; "$g" "$v"``) is not
            # missed while ``x=git; $x status`` remains allowed.
            resolved_executable = assignments.get(_shell_variable_name(token) or "")
            if resolved_executable is not None:
                resolved_tokens = [resolved_executable, *tokens[index + 1 :]]
                # A literal variable binding can point at an extensionless
                # external helper (``cmd=/tmp/evil/helper; $cmd``), which is
                # not identifiable by the ordinary script suffix test.  The
                # binding is unambiguously in command position here, so
                # reject every non-system path unless it is one of the
                # explicitly reviewed script/tool forms.
                normalized_resolved = resolved_executable.strip("'\"").replace(
                    "\\", "/"
                )
                if (
                    "/" in normalized_resolved
                    and not normalized_resolved.startswith(
                        SYSTEM_EXECUTABLE_PATH_PREFIXES
                    )
                    and not _is_git_executable_or_helper(resolved_executable)
                ):
                    if _script_path_invocation_mutates(resolved_executable):
                        return True
                    if _script_path_key(resolved_executable) is None and not (
                        _dynamic_path_executable_is_allowed(resolved_executable)
                    ):
                        return True
                if _is_git_executable_or_helper(resolved_executable):
                    # Replace a literal subcommand variable when available.
                    for offset, argument in enumerate(resolved_tokens[1:], start=1):
                        if argument.startswith("-"):
                            continue
                        name = _shell_variable_name(argument)
                        if name is not None and name in assignments:
                            resolved_tokens[offset] = assignments[name]
                        break
                    if _git_invocation_mutates(resolved_tokens, 0):
                        return True
                elif _executable_basename(resolved_executable) in GH_EXECUTABLES:
                    if _github_invocation_mutates(resolved_tokens, 0):
                        return True
                elif _executable_basename(resolved_executable) in HTTP_EXECUTABLES:
                    if _http_invocation_mutates(resolved_tokens, 0):
                        return True
                elif _executable_basename(resolved_executable) in {"alias", "eval"}:
                    return True
                elif _executable_basename(resolved_executable) in (
                    SHELL_INTERPRETERS | SHELL_WRAPPERS | SHELL_GRAPH_WRAPPERS
                ):
                    # Re-run the resolved wrapper/interpreter command so
                    # aliases such as ``w=env; $w -S 'git push'`` and
                    # ``w=bash; $w -lc 'git push'`` cannot bypass the normal
                    # command-graph checks.
                    if _contains_mutation(
                        shlex.join(resolved_tokens), _depth=depth + 1
                    ):
                        return True
                elif _executable_basename(resolved_executable) in {"source", "."}:
                    # A sourced path is executable shell code.  Preserve the
                    # one reviewed helper exception used by the D2I path;
                    # every dynamic/unreviewed path fails closed.
                    source_path = next(
                        (
                            value
                            for value in resolved_tokens[1:]
                            if not value.startswith("-")
                        ),
                        "",
                    )
                    if _script_path_key(source_path.strip("'\"")) != (
                        "tools/reject_symlink_path.sh"
                    ):
                        return True
                continue

            # A bare expansion/backtick/command substitution at a command
            # boundary is an unresolved executable.  Keep the narrow,
            # reviewed-path and literal-basename exceptions for current
            # qualification workflows; every other expansion is ambiguous.
            if _shell_token_has_expansion(token):
                if (
                    _script_path_key(token) is None
                    and not _dynamic_path_executable_is_allowed(token)
                ):
                    return True

            # ``bash -c``/``sh -c`` payloads are recursively audited.  A
            # payload containing an unresolved expansion is rejected even if
            # no literal Git token is visible to the outer shell scanner.
            if executable in SHELL_INTERPRETERS:
                payload, dynamic = _shell_interpreter_payload(tokens, index)
                if payload is not None:
                    if (
                        (dynamic and (not payload or not _shell_payload_expansion_is_reviewed(payload)))
                        or SHELL_ARRAY_EXPANSION.search(payload)
                        or re.search(r"(?m)\b(?:alias|eval)\b", payload)
                    ):
                        return True
                    if _contains_mutation(payload, _depth=depth + 1):
                        return True

        # Scan only Git tokens that begin an actual command.  Looking at every
        # token would mistake ``echo 'git push'`` or a Python argv literal for
        # an executed mutation.  Command substitutions are handled explicitly
        # below.
        for index in _shell_git_command_indices(tokens):
            if _git_invocation_mutates(tokens, index):
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


def _python_mask_literals(command: str) -> str:
    """Mask Python string/comment contents while preserving source offsets.

    Workflow ``run`` blocks often embed Python heredocs alongside shell text.
    Regex recognizers must not treat a diagnostic string such as
    ``print('requests.post(...)')`` as an actual network call, but the original
    source is still needed later to decode literal arguments.  This bounded
    lexer masks quoted/comment characters with spaces and keeps newlines and
    punctuation at their original offsets.
    """

    masked = list(command)
    index = 0
    quote: str | None = None
    triple = False
    comment = False
    while index < len(command):
        character = command[index]
        if comment:
            if character in "\r\n":
                comment = False
            else:
                masked[index] = " "
            index += 1
            continue
        if quote is not None:
            if triple:
                marker = quote * 3
                if command.startswith(marker, index):
                    for offset in range(3):
                        masked[index + offset] = " "
                    index += 3
                    quote = None
                    triple = False
                    continue
                if character not in "\r\n":
                    masked[index] = " "
                index += 1
                continue
            if character == "\\":
                masked[index] = " "
                if index + 1 < len(command) and command[index + 1] not in "\r\n":
                    masked[index + 1] = " "
                    index += 2
                else:
                    index += 1
                continue
            if character == quote:
                masked[index] = " "
                quote = None
            elif character not in "\r\n":
                masked[index] = " "
            index += 1
            continue
        if character == "#":
            masked[index] = " "
            comment = True
            index += 1
            continue
        if character in {"'", '"'}:
            quote = character
            triple = command.startswith(character * 3, index)
            width = 3 if triple else 1
            for offset in range(width):
                masked[index + offset] = " "
            index += width
            continue
        index += 1
    return "".join(masked)


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


def _python_static_string(node: ast.AST) -> str | None:
    """Evaluate a bounded string expression without executing Python."""

    try:
        value = ast.literal_eval(node)
    except (SyntaxError, ValueError, TypeError, MemoryError, RecursionError):
        value = None
    if isinstance(value, str):
        return value
    # ``ast.literal_eval`` intentionally rejects concatenation represented as
    # a BinOp on some supported Python versions.  Permit only literal string
    # addition; names, calls, formatting, and f-strings remain dynamic.
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _python_static_string(node.left)
        right = _python_static_string(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _python_static_argv(node: ast.AST) -> list[str | None] | None:
    """Return a bounded argv list, using ``None`` for dynamic elements."""

    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    values: list[str | None] = []
    for element in node.elts:
        values.append(_python_static_string(element))
    return values


def _python_call_name(node: ast.AST) -> str:
    """Render a small dotted call name for diagnostics/dispatch."""

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _python_call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _python_keyword_true(call: ast.Call, name: str) -> bool:
    return any(
        keyword.arg == name
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is True
        for keyword in call.keywords
    )


def _python_http_has_literal_safe_method(
    arguments: str, *, request_object: bool = False
) -> bool:
    """Return whether a bounded HTTP call has an explicit safe method.

    Parse a synthetic call expression instead of searching raw text: a URL or
    diagnostic string containing ``method='GET'`` must not make a dynamic
    method appear safe.  Only the target call's own method argument is
    considered.  ``urlopen(Request(...))`` is the one nested shape whose
    ``Request(method=...)`` controls the effective method, so callers opt into
    that narrowly with ``request_object=True``.
    """

    try:
        expression = ast.parse(f"__http_call({arguments})", mode="eval")
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return False
    call = expression.body
    if not isinstance(call, ast.Call):
        return False
    safe = {"GET", "HEAD", "OPTIONS"}
    body_keywords = {
        "data",
        "json",
        "content",
        "files",
        "body",
        "upload_file",
        "post_data",
    }
    method_override_names = {
        "x-http-method-override",
        "x-http-method",
        ":method",
        "http-method-override",
    }

    def static_safe(value: ast.AST | None) -> bool:
        method = _python_static_string(value) if value is not None else None
        return method is not None and method.upper() in safe

    def has_unsafe_body(call_node: ast.Call, *, request_node: bool = False) -> bool:
        # ``**kwargs`` can carry a body, method override, or transport helper
        # that is invisible to the AST keyword names.  It is never a bounded
        # read-only proof.
        if any(keyword.arg is None for keyword in call_node.keywords):
            return True
        if any(
            keyword.arg in body_keywords
            and not (
                isinstance(keyword.value, ast.Constant)
                and keyword.value.value is None
            )
            for keyword in call_node.keywords
        ):
            return True
        for keyword in call_node.keywords:
            if keyword.arg != "headers":
                continue
            value = keyword.value
            if isinstance(value, ast.Constant) and value.value is None:
                continue
            if isinstance(value, ast.Dict):
                pairs = zip(value.keys, value.values)
                for key, header_value in pairs:
                    key_text = _python_static_string(key) if key is not None else None
                    if key_text is None:
                        return True
                    normalized = key_text.strip().lower()
                    if normalized not in method_override_names and "method-override" not in normalized:
                        continue
                    if isinstance(header_value, ast.Constant) and header_value.value is None:
                        continue
                    method_text = _python_static_string(header_value)
                    if method_text is None or method_text.upper() not in safe:
                        return True
            elif isinstance(value, (ast.List, ast.Tuple)):
                for item in value.elts:
                    if not isinstance(item, (ast.List, ast.Tuple)) or len(item.elts) < 2:
                        return True
                    key_text = _python_static_string(item.elts[0])
                    if key_text is None:
                        return True
                    normalized = key_text.strip().lower()
                    if normalized not in method_override_names and "method-override" not in normalized:
                        continue
                    method_text = _python_static_string(item.elts[1])
                    if method_text is None or method_text.upper() not in safe:
                        return True
            else:
                # A mapping supplied by a variable/call may contain an
                # override header even when the method itself is GET.
                return True
        # urllib.request.Request(url, data) uses the second positional
        # argument as the request body; a non-None value changes the method.
        if request_node and len(call_node.args) >= 2:
            value = call_node.args[1]
            if not (isinstance(value, ast.Constant) and value.value is None):
                return True
        if request_node and len(call_node.args) >= 3:
            # Request's third positional argument is the headers mapping.
            headers = call_node.args[2]
            if not isinstance(headers, ast.Dict):
                return True
            for key, header_value in zip(headers.keys, headers.values):
                key_text = _python_static_string(key) if key is not None else None
                if key_text is None:
                    return True
                normalized = key_text.strip().lower()
                if normalized not in method_override_names and "method-override" not in normalized:
                    continue
                method_text = _python_static_string(header_value)
                if method_text is None or method_text.upper() not in safe:
                    return True
        literal_strings = [
            node.value
            for node in ast.walk(call_node)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        if any("method-override" in value.lower() for value in literal_strings) and any(
            re.search(r"\b(?:post|put|patch|delete)\b", value, re.I)
            for value in literal_strings
        ):
            return True
        return False

    # requests/httpx ``request`` and Session.request use the first positional
    # argument (or the explicit keyword) as the method.
    # ``request_object=True`` is reserved for ``urlopen(Request(...))``.
    # ``urlopen(url)`` has an implicit GET in today's urllib implementation,
    # but that is not a sufficiently stable source-level proof: a wrapper,
    # monkey-patch, or dynamically constructed request can change the
    # effective method.  Require the nested Request object and its explicit
    # safe method before accepting this special shape.  Keep this branch
    # before the ordinary positional-method logic so a URL string is never
    # mistaken for a method token.
    if request_object:
        if not call.args:
            return False
        nested = call.args[0]
        if not (
            isinstance(nested, ast.Call)
            and _python_call_name(nested.func).split(".")[-1].lower()
            == "request"
        ):
            return False
        if has_unsafe_body(call) or has_unsafe_body(nested, request_node=True):
            return False
        return any(
            keyword.arg == "method" and static_safe(keyword.value)
            for keyword in nested.keywords
        )

    if call.args and static_safe(call.args[0]) and not has_unsafe_body(call):
        return True
    if any(
        keyword.arg == "method"
        and static_safe(keyword.value)
        and not has_unsafe_body(call)
        for keyword in call.keywords
    ):
        return True
    return False


def _python_http_call_arguments(command: str, start: int) -> str:
    """Return a bounded argument payload beginning immediately after ``(``."""

    end = _python_call_end(command, start)
    return command[start:end]


def _python_module_aliases(command: str) -> dict[str, str]:
    """Collect common module aliases without executing Python imports."""

    aliases: dict[str, str] = {}
    masked = _python_mask_literals(command)
    for match in re.finditer(r"(?m)(?:^|;)\s*import\s+([^;\n]+)", masked):
        # A comma-separated import statement is still unambiguous after
        # literals/comments have been masked.  Ignore malformed fragments;
        # the call-site scanner will fail closed if an alias is actually used.
        for fragment in match.group(1).split(","):
            fields = fragment.strip().split()
            if not fields or fields[0] not in {
                "requests",
                "httpx",
                "subprocess",
                "os",
                "urllib.request",
                "importlib",
            }:
                continue
            module = fields[0]
            alias = fields[2] if len(fields) == 3 and fields[1] == "as" else module.rsplit(".", 1)[-1]
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", alias):
                aliases[alias] = module
    # A module can be rebound through a simple assignment before its effectful
    # method is called (``sp = subprocess; sp.run(...)``). Resolve only
    # literal module names/aliases; dynamic assignments remain unresolved and
    # are handled by the fail-closed call scanners.
    assignment_pattern = re.compile(
        r"(?m)(?:^|;)\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
        r"([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\b"
    )
    for _ in range(3):
        changed = False
        for match in assignment_pattern.finditer(masked):
            target, source = match.groups()
            canonical = aliases.get(source, source)
            if canonical in {
                "requests",
                "httpx",
                "subprocess",
                "os",
                "urllib.request",
                "importlib",
            } and aliases.get(target) != canonical:
                aliases[target] = canonical
                changed = True
        if not changed:
            break
    return aliases


def _python_from_import_bindings(
    command: str,
) -> list[tuple[str, str, str]]:
    """Collect bounded ``from module import name [as alias]`` bindings.

    The older regular-expression bindings intentionally handled only the
    one-line form. Python also permits parenthesized/multiline imports, which
    are common in embedded heredocs and can hide an effectful alias. Parse
    candidate statements independently so surrounding shell syntax does not
    make the complete workflow fragment a Python program. Malformed or
    unusually large candidates are ignored here; the call-site scanners still
    fail closed when they encounter unresolved dynamic calls.
    """

    lines = command.splitlines(keepends=True)
    masked_lines = _python_mask_literals(command).splitlines(keepends=True)
    bindings: list[tuple[str, str, str]] = []
    supported = {
        "requests",
        "httpx",
        "subprocess",
        "os",
        "urllib.request",
        "importlib",
    }
    index = 0
    while index < len(lines):
        masked_line = masked_lines[index] if index < len(masked_lines) else ""
        match = re.match(
            r"^[ \t]*from\s+([A-Za-z_][A-Za-z0-9_.]*)\s+import\b",
            masked_line,
            re.I,
        )
        if match is None or match.group(1) not in supported:
            index += 1
            continue
        end = index + 1
        # A parenthesized import may span lines. Keep a tight bound to avoid
        # turning arbitrary shell text into one giant parse candidate.
        remainder = masked_line[match.end() :]
        if "(" in remainder and ")" not in remainder:
            while end < len(lines) and end - index < 32:
                if ")" in (masked_lines[end] if end < len(masked_lines) else ""):
                    end += 1
                    break
                end += 1
        snippet = "".join(lines[index:end])
        try:
            tree = ast.parse(snippet, mode="exec")
        except (SyntaxError, ValueError, MemoryError, RecursionError):
            index = max(index + 1, end)
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.module not in supported:
                continue
            for alias in node.names:
                if alias.name == "*":
                    # Star imports are handled as an unconditional rejection
                    # by the callers; do not manufacture a binding here.
                    continue
                bindings.append((node.module, alias.name, alias.asname or alias.name))
        index = max(index + 1, end)
    return bindings


def _python_call_payload(command: str, match_end: int) -> str:
    """Return a bounded call argument payload for a masked-source match."""

    return command[match_end : _python_call_end(command, match_end)]


def _python_interpreter_payload(arguments: list[str]) -> tuple[str | None, bool]:
    """Return a Python ``-c`` payload, including clustered short flags."""

    for index, argument in enumerate(arguments):
        if argument in {"-m", "--module"}:
            if index + 1 >= len(arguments):
                return "", True
            module = arguments[index + 1]
            if _shell_token_has_expansion(module) or module not in {"unittest", "py_compile"}:
                return "", True
            return None, False
        if argument.startswith("-m") and len(argument) > 2:
            module = argument[2:]
            if _shell_token_has_expansion(module) or module not in {"unittest", "py_compile"}:
                return "", True
            return None, False
        if argument.startswith("--module="):
            module = argument.split("=", 1)[1]
            if _shell_token_has_expansion(module) or module not in {"unittest", "py_compile"}:
                return "", True
            return None, False
        if argument == "--":
            if (
                index + 1 < len(arguments)
                and arguments[index + 1] != "-"
                and arguments[index + 1].startswith("-")
            ):
                # After ``--`` the next token is a script path, even when it
                # happens to begin with a dash.  Treat an option-looking
                # operand as ambiguous rather than allowing it to hide a
                # command graph.
                return "", True
            return None, False
        if argument == "-c":
            if index + 1 >= len(arguments):
                return "", True
            payload = arguments[index + 1]
            return payload, _shell_token_has_expansion(payload)
        if argument.startswith("-c") and len(argument) > 2:
            payload = argument[2:]
            return payload, _shell_token_has_expansion(payload)
        if argument.startswith("-") and not argument.startswith("--"):
            flags = argument[1:]
            if "c" in flags:
                position = flags.index("c")
                suffix = flags[position + 1 :]
                if suffix:
                    return suffix, _shell_token_has_expansion(suffix)
                if index + 1 >= len(arguments):
                    return "", True
                payload = arguments[index + 1]
                return payload, _shell_token_has_expansion(payload)
    return None, False


def _python_interpreter_payload_mutates(command: str, *, depth: int) -> bool:
    """Audit static ``python -c`` command-position payloads.

    The main Python regex scanner intentionally masks quoted shell tokens, so
    ``python3 -c 'subprocess.run(...)'`` would otherwise look like harmless
    data.  Only a literal command-position interpreter and literal ``-c``
    payload are recursively inspected; an expansion is unknown and therefore
    rejected.
    """

    if depth > 2:
        return True
    python_names = {"python", "python3", "python3.12", "pypy", "pypy3"}
    for tokens in _shell_command_tokens(command, strip_comments=True):
        for start in _shell_command_start_indices(tokens):
            index = _shell_executable_index(tokens, start)
            if index >= len(tokens):
                continue
            if _executable_basename(tokens[index]) not in python_names:
                continue
            arguments = tokens[index + 1 :]
            payload, dynamic = _python_interpreter_payload(arguments)
            if payload is not None:
                if dynamic:
                    return True
                if _python_http_call_mutates(payload) or _python_call_mutates(
                    payload, depth=depth + 1
                ):
                    return True
    return False


def _python_import_function_aliases(command: str) -> set[str]:
    """Return aliases that dispatch ``importlib.import_module``/``__import__``."""

    aliases = {"__import__"}
    masked = _python_mask_literals(command)
    for match in re.finditer(
        r"(?m)(?:^|;)\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
        r"(?:importlib\s*\.\s*import_module|__import__)\b",
        masked,
    ):
        aliases.add(match.group(1))
    for module, symbol, alias in _python_from_import_bindings(command):
        if module == "importlib" and symbol == "import_module":
            aliases.add(alias)
    return aliases


def _python_module_http_mutates(command: str) -> bool:
    """Audit HTTP calls through ``import ... as`` module aliases."""

    masked = _python_mask_literals(command)
    if re.search(
        r"(?im)^\s*from\s+(?:requests|httpx|urllib\.request)\s+import\s+\*",
        masked,
    ):
        return True
    aliases = _python_module_aliases(command)
    for alias, module in aliases.items():
        if module in {"requests", "httpx"}:
            direct = re.compile(
                rf"(?<![A-Za-z0-9_]){re.escape(alias)}\s*\.\s*"
                r"(post|put|patch|delete)\s*\(",
                re.I,
            )
            if direct.search(masked):
                return True
            request = re.compile(
                rf"(?<![A-Za-z0-9_]){re.escape(alias)}\s*\.\s*request\s*\(",
                re.I,
            )
            for match in request.finditer(masked):
                arguments = _python_http_call_arguments(command, match.end())
                if not _python_http_has_literal_safe_method(arguments):
                    return True
            constructor = re.compile(
                rf"(?<![A-Za-z0-9_]){re.escape(alias)}\s*\.\s*"
                r"(Session|Client)\s*\([^\n]{0,512}\)\s*\.\s*"
                r"(get|head|options|post|put|patch|delete|request)\s*\(",
                re.I,
            )
            for match in constructor.finditer(masked):
                method = re.search(
                    r"\.\s*(get|head|options|post|put|patch|delete|request)\s*\($",
                    match.group(0),
                    re.I,
                )
                if method is not None and method.group(1).lower() in {
                    "post",
                    "put",
                    "patch",
                    "delete",
                }:
                    return True
                arguments = _python_http_call_arguments(command, match.end())
                if method is not None and method.group(1).lower() in {
                    "get",
                    "head",
                    "options",
                }:
                    arguments = f'"{method.group(1).upper()}",' + arguments
                if not _python_http_has_literal_safe_method(arguments):
                    return True
            object_aliases = {
                match.group(1)
                for match in re.finditer(
                    rf"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
                    rf"{re.escape(alias)}\s*\.\s*(?:Session|Client)\s*\(",
                    masked,
                    re.I,
                )
            }
            for object_alias in object_aliases:
                calls = re.compile(
                    rf"(?<![A-Za-z0-9_]){re.escape(object_alias)}\s*\.\s*"
                    r"(get|head|options|post|put|patch|delete|request)\s*\(",
                    re.I,
                )
                for match in calls.finditer(masked):
                    method = match.group(1).lower()
                    if method in {"post", "put", "patch", "delete"}:
                        return True
                    arguments = _python_http_call_arguments(command, match.end())
                    if method in {"get", "head", "options"}:
                        arguments = f'"{method.upper()}",' + arguments
                    if not _python_http_has_literal_safe_method(arguments):
                        return True
        elif module == "urllib.request":
            for method_name, request_object in (
                ("urlopen", True),
                ("Request", False),
            ):
                pattern = re.compile(
                    rf"(?<![A-Za-z0-9_]){re.escape(alias)}\s*\.\s*"
                    rf"{method_name}\s*\(",
                    re.I,
                )
                for match in pattern.finditer(masked):
                    arguments = _python_http_call_arguments(command, match.end())
                    if not _python_http_has_literal_safe_method(
                        arguments, request_object=request_object
                    ):
                        return True
    return False


def _python_dynamic_import_mutates(command: str, *, depth: int) -> bool:
    """Audit chained calls on ``__import__``/``import_module`` results."""

    if depth > 2:
        return True
    masked = _python_mask_literals(command)
    importlib_aliases = {
        alias
        for alias, module in _python_module_aliases(command).items()
        if module == "importlib"
    }
    importlib_roots = "|".join(
        ["importlib", *(re.escape(alias) for alias in sorted(importlib_aliases))]
    )
    import_function_aliases = _python_import_function_aliases(command)
    import_function_names = "|".join(
        re.escape(alias) for alias in sorted(import_function_aliases)
    )
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_.])(?:{import_function_names}|(?:{importlib_roots})\s*\.\s*import_module)\s*\(",
        re.I,
    )
    process_methods = PYTHON_PROCESS_METHODS | {"fork", "forkpty"}
    for match in pattern.finditer(masked):
        inner_end = _python_call_end(command, match.end())
        cursor = inner_end + 1
        while cursor < len(command) and command[cursor].isspace():
            cursor += 1
        if cursor >= len(command) or command[cursor] != ".":
            continue
        cursor += 1
        # Permit a bounded dotted attribute chain.  ``__import__(
        # "urllib.request").request.urlopen(...)`` has two attributes between
        # the dynamic importer and the effectful call; matching only one
        # attribute silently dropped that HTTP graph.
        name_match = re.match(
            r"\s*((?:[A-Za-z_][A-Za-z0-9_]*\s*\.)*[A-Za-z_][A-Za-z0-9_]*)\s*\(",
            command[cursor:],
        )
        if name_match is None:
            continue
        method = name_match.group(1).rsplit(".", 1)[-1].strip().lower()
        call_start = cursor + name_match.end() - 1
        outer_end = _python_call_end(command, call_start + 1)
        snippet = command[match.start() : min(len(command), outer_end + 1)]
        try:
            expression = ast.parse(snippet, mode="eval")
        except (SyntaxError, ValueError, MemoryError, RecursionError):
            return True
        outer = expression.body
        if not isinstance(outer, ast.Call) or not isinstance(outer.func, ast.Attribute):
            return True
        # Walk through any intermediate attributes to recover the dynamic
        # importer call at the root of the function chain.
        importer = outer.func.value
        while isinstance(importer, ast.Attribute):
            importer = importer.value
        if not isinstance(importer, ast.Call):
            return True
        module_name = (
            _python_static_string(importer.args[0]) if importer.args else None
        )
        if module_name is None:
            return True
        if module_name in {"subprocess", "os"} and method in process_methods:
            canonical = f"{module_name}.{method}"
            if _python_call_mutates(
                f"{canonical}({', '.join(ast.unparse(arg) for arg in outer.args)})",
                depth=depth + 1,
            ):
                return True
        elif module_name in {"requests", "httpx"} and method in {
            "post",
            "put",
            "patch",
            "delete",
        }:
            return True
        elif module_name in {"requests", "httpx"} and method == "request":
            arguments = command[call_start + 1 : outer_end]
            if not _python_http_has_literal_safe_method(arguments):
                return True
        elif module_name == "urllib.request" and method in {"urlopen", "request"}:
            arguments = command[call_start + 1 : outer_end]
            if not _python_http_has_literal_safe_method(
                arguments, request_object=method == "urlopen"
            ):
                return True
        elif method in process_methods or method in {
            "post",
            "put",
            "patch",
            "delete",
            "request",
            "urlopen",
        }:
            # A different module can expose an identically named effectful
            # API; without resolving imports, treating it as harmless would
            # be an unsound source-level proof.
            return True
    return False


def _python_http_call_mutates(command: str) -> bool:
    """Reject Python HTTP mutation graphs unless the method is literal-safe.

    Requests are intentionally audited independent of destination URL: a
    source-only workflow gate cannot prove that a variable or wrapper will not
    redirect a request to GitHub (or another promotion endpoint).  Explicit
    GET/HEAD/OPTIONS calls are the only accepted method proof.  Aliased
    ``request`` imports and Session/Client calls are conservatively rejected
    when their method is not a literal safe token.
    """

    scan_command = _python_mask_literals(command)

    if _python_dynamic_module_dispatch_mutates(command):
        return True
    if _python_bound_method_mutates(command, depth=0):
        return True
    if _python_module_http_mutates(command):
        return True
    if _python_getattr_http_mutates(command):
        return True
    if _python_dynamic_import_mutates(command, depth=0):
        return True

    # Direct requests/httpx mutation methods are effectful regardless of URL.
    if PYTHON_HTTP_MUTATING_CALL.search(scan_command):
        return True
    if PYTHON_SESSION_MUTATING_CALL.search(scan_command):
        return True

    # GET/HEAD/OPTIONS convenience methods are read-only only when no body or
    # method-override argument is supplied. Audit them as bounded calls too;
    # this closes the common ``requests.get(..., data=...)`` escape hatch
    # without rejecting ordinary timeout/params/header arguments.
    safe_method_call = re.compile(
        r"(?<![A-Za-z0-9_])(?:requests|httpx)\s*\.\s*"
        r"(get|head|options)\s*\(",
        re.I,
    )
    for match in safe_method_call.finditer(scan_command):
        method = re.search(r"\.\s*(get|head|options)\s*\($", match.group(0), re.I)
        if method is not None and not _python_http_has_literal_safe_method(
            f'"{method.group(1).upper()}",'
            f"{_python_http_call_arguments(command, match.end())}"
        ):
            return True

    for pattern in (PYTHON_HTTP_REQUEST, PYTHON_SESSION_REQUEST):
        for match in pattern.finditer(scan_command):
            arguments = _python_http_call_arguments(command, match.end())
            if _python_http_has_literal_safe_method(arguments):
                continue
            return True

    # ``urlopen(Request(...))`` is safe only when the nested Request object
    # carries an explicit read-only method.  The URLRequest regex also finds
    # the nested ``Request`` call itself; that inner call is checked below
    # with the ordinary (non-nested) rule.
    for match in PYTHON_URLREQUEST_CALL.finditer(scan_command):
        arguments = _python_http_call_arguments(command, match.end())
        call_name = match.group(0).split("(", 1)[0].rsplit(".", 1)[-1].lower()
        if call_name == "urlopen":
            if _python_http_has_literal_safe_method(
                arguments, request_object=True
            ):
                continue
            return True
        if _python_http_has_literal_safe_method(arguments):
            continue
        # ``urllib.request.Request`` and ``urlopen(Request(...))`` need an
        # explicit safe method because data/headers can otherwise alter the
        # effective request method at runtime.
        return True

    # Track the common requests.request alias/import forms without executing
    # Python. If an alias is rebound, an invocation with an unresolved method
    # remains an effectful graph.
    request_aliases = {
        match.group(1)
        for match in PYTHON_HTTP_ALIAS_ASSIGNMENT.finditer(command)
    }
    for module_alias, module in _python_module_aliases(command).items():
        if module in {"requests", "httpx"}:
            request_aliases.update(
                match.group(1)
                for match in re.finditer(
                    rf"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
                    rf"{re.escape(module_alias)}\s*\.\s*request\b",
                    scan_command,
                    re.I,
                )
            )
    request_aliases.update(
        (match.group(1) or "request")
        for match in PYTHON_HTTP_ALIAS_IMPORT.finditer(command)
    )
    for module, symbol, alias in _python_from_import_bindings(command):
        if module in {"requests", "httpx"} and symbol == "request":
            request_aliases.add(alias)
    for alias in request_aliases:
        for match in re.finditer(
            rf"(?<![A-Za-z0-9_]){re.escape(alias)}\s*\(", command
        ):
            arguments = _python_http_call_arguments(command, match.end())
            if not _python_http_has_literal_safe_method(arguments):
                return True

    # ``from requests import get as g`` (and the equivalent httpx import)
    # bypasses the dotted-module recognizers above.  Track those convenience
    # callables explicitly and propagate short rebinding chains (``f = g``)
    # before auditing body/method-override kwargs at the call site.
    imported_http_methods: dict[str, str] = {}
    for module, symbol, alias in _python_from_import_bindings(command):
        if module in {"requests", "httpx"} and symbol.lower() in {
            "get",
            "head",
            "options",
            "post",
            "put",
            "patch",
            "delete",
            "request",
        }:
            imported_http_methods[alias] = symbol.lower()
    for _ in range(3):
        changed = False
        for match in re.finditer(
            r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
            r"([A-Za-z_][A-Za-z0-9_]*)\b",
            scan_command,
        ):
            target, receiver = match.groups()
            if target in imported_http_methods or receiver not in imported_http_methods:
                continue
            imported_http_methods[target] = imported_http_methods[receiver]
            changed = True
        if not changed:
            break
    for alias, method in imported_http_methods.items():
        for match in re.finditer(
            rf"(?<![A-Za-z0-9_]){re.escape(alias)}\s*\(", scan_command
        ):
            before = command[max(0, match.start() - 3) : match.start()]
            if "=" in before:
                continue
            arguments = _python_http_call_arguments(command, match.end())
            if method in {"post", "put", "patch", "delete"}:
                return True
            if method in {"get", "head", "options"}:
                arguments = f'"{method.upper()}",' + arguments
            if not _python_http_has_literal_safe_method(arguments):
                return True

    # Track Session/Client constructor aliases (including ``from ... import
    # Session as S``) and audit their instance methods.
    session_class_aliases = {"Session", "Client"}
    session_class_aliases.update(
        (match.group(2) or match.group(1))
        for match in PYTHON_SESSION_ALIAS_IMPORT.finditer(scan_command)
    )
    session_class_aliases.update(
        alias
        for module, symbol, alias in _python_from_import_bindings(command)
        if module in {"requests", "httpx"} and symbol in {"Session", "Client"}
    )
    session_aliases = {
        match.group(1)
        for match in PYTHON_SESSION_ALIAS_ASSIGNMENT.finditer(scan_command)
    }
    for module_alias, module in _python_module_aliases(command).items():
        if module in {"requests", "httpx"}:
            session_aliases.update(
                match.group(1)
                for match in re.finditer(
                    rf"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
                    rf"{re.escape(module_alias)}\s*\.\s*(?:Session|Client)\s*\(",
                    scan_command,
                    re.I,
                )
            )
    for constructor in session_class_aliases:
        session_aliases.update(
            match.group(1)
            for match in re.finditer(
                rf"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*{re.escape(constructor)}\s*\(",
                scan_command,
                re.I,
            )
        )
        for match in re.finditer(
            rf"\b{re.escape(constructor)}\s*\([^\n]{{0,512}}\)\s*\.\s*"
            rf"(get|head|options|post|put|patch|delete|request)\s*\(",
            scan_command,
            re.I,
        ):
            method = re.search(
                r"\.\s*(get|head|options|post|put|patch|delete|request)\s*\($",
                match.group(0),
                re.I,
            )
            if method is not None and method.group(1).lower() in {
                "post",
                "put",
                "patch",
                "delete",
            }:
                return True
            arguments = _python_http_call_arguments(command, match.end())
            if method is not None and method.group(1).lower() in {
                "get",
                "head",
                "options",
            }:
                arguments = f'"{method.group(1).upper()}",' + arguments
            if not _python_http_has_literal_safe_method(arguments):
                return True

    for alias in session_aliases:
        for match in re.finditer(
            rf"(?<![A-Za-z0-9_]){re.escape(alias)}\s*\.\s*"
            rf"(get|head|options|post|put|patch|delete|request)\s*\(",
            scan_command,
            re.I,
        ):
            method = re.search(
                r"\.\s*(get|head|options|post|put|patch|delete|request)\s*\($",
                match.group(0),
                re.I,
            )
            if method is not None and method.group(1).lower() in {
                "post",
                "put",
                "patch",
                "delete",
            }:
                return True
            arguments = _python_http_call_arguments(command, match.end())
            if method is not None and method.group(1).lower() in {
                "get",
                "head",
                "options",
            }:
                arguments = f'"{method.group(1).upper()}",' + arguments
            if not _python_http_has_literal_safe_method(arguments):
                return True

    # Track direct mutation-method aliases and imports (for example
    # ``post = requests.post`` or ``from httpx import delete as remove``).
    mutating_aliases = {
        match.group(1)
        for match in PYTHON_HTTP_MUTATING_ALIAS_ASSIGNMENT.finditer(scan_command)
        if ".urlopen" not in match.group(0).lower()
    }
    for module_alias, module in _python_module_aliases(command).items():
        if module in {"requests", "httpx"}:
            mutating_aliases.update(
                match.group(1)
                for match in re.finditer(
                    rf"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
                    rf"{re.escape(module_alias)}\s*\.\s*"
                    r"(?:post|put|patch|delete)\b",
                    scan_command,
                    re.I,
                )
            )
    mutating_aliases.update(
        (match.group(2) or match.group(1))
        for match in PYTHON_HTTP_MUTATING_ALIAS_IMPORT.finditer(scan_command)
    )
    mutating_aliases.update(
        alias
        for module, symbol, alias in _python_from_import_bindings(command)
        if module in {"requests", "httpx"}
        and symbol in {"post", "put", "patch", "delete"}
    )
    for alias in mutating_aliases:
        if re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(alias)}\s*\(", scan_command, re.I
        ):
            return True

    # ``urllib.request.urlopen`` is frequently imported or rebound. Preserve
    # the same explicit-safe-method rule for those aliases.
    urlopen_aliases = {
        match.group(1)
        for match in PYTHON_URLOPEN_ALIAS_ASSIGNMENT.finditer(scan_command)
    }
    for module_alias, module in _python_module_aliases(command).items():
        if module == "urllib.request":
            urlopen_aliases.update(
                match.group(1)
                for match in re.finditer(
                    rf"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
                    rf"{re.escape(module_alias)}\s*\.\s*urlopen\b",
                    scan_command,
                    re.I,
                )
            )
    urlopen_aliases.update(
        (match.group(1) or "urlopen")
        for match in PYTHON_URLOPEN_ALIAS_IMPORT.finditer(scan_command)
    )
    urlopen_aliases.update(
        alias
        for module, symbol, alias in _python_from_import_bindings(command)
        if module == "urllib.request" and symbol == "urlopen"
    )
    # Preserve aliases copied from an imported ``urlopen`` binding.  A bare
    # URL remains conservatively rejected; only a nested Request with an
    # explicit GET/HEAD/OPTIONS method is accepted below.
    for _ in range(3):
        changed = False
        for match in re.finditer(
            r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
            r"([A-Za-z_][A-Za-z0-9_]*)\b",
            scan_command,
        ):
            target, receiver = match.groups()
            if target in urlopen_aliases or receiver not in urlopen_aliases:
                continue
            urlopen_aliases.add(target)
            changed = True
        if not changed:
            break
    for alias in urlopen_aliases:
        for match in re.finditer(
            rf"(?<![A-Za-z0-9_]){re.escape(alias)}\s*\(", scan_command
        ):
            arguments = _python_http_call_arguments(command, match.end())
            if not _python_http_has_literal_safe_method(
                arguments, request_object=True
            ):
                return True

    request_class_aliases = {
        match.group(1) or "Request"
        for match in PYTHON_REQUEST_CLASS_ALIAS_IMPORT.finditer(scan_command)
    }
    request_class_aliases.update(
        alias
        for module, symbol, alias in _python_from_import_bindings(command)
        if module == "urllib.request" and symbol == "Request"
    )
    for alias in request_class_aliases:
        for match in re.finditer(
            rf"(?<![A-Za-z0-9_]){re.escape(alias)}\s*\(", scan_command
        ):
            arguments = _python_http_call_arguments(command, match.end())
            if not _python_http_has_literal_safe_method(arguments):
                return True
    return False


def _python_getattr_process_mutates(command: str) -> bool:
    """Recognize ``getattr(os/subprocess, 'mutator')(...)`` call graphs.

    The general Python literal masker intentionally hides quoted strings.  A
    ``getattr`` dispatch, however, needs its literal attribute name to identify
    the process API.  Locate the call in masked source (so prose/comments are
    ignored), then parse the bounded original expression structurally.
    """

    masked = _python_mask_literals(command)
    head = re.compile(r"(?i)\bgetattr\s*\(")
    methods = {
        value.lower()
        for value in (PYTHON_PROCESS_METHODS | PYTHON_OS_METHODS | {"fork", "forkpty"})
    }
    module_aliases = _python_module_aliases(command)
    module_aliases.update({"os": "os", "subprocess": "subprocess"})
    for match in head.finditer(masked):
        inner_end = _python_call_end(command, match.end())
        cursor = inner_end + 1
        while cursor < len(command) and command[cursor].isspace():
            cursor += 1
        if cursor >= len(command) or command[cursor] != "(":
            continue
        outer_end = _python_call_end(command, cursor + 1)
        snippet = command[match.start() : min(len(command), outer_end + 1)]
        try:
            expression = ast.parse(snippet, mode="eval")
        except (SyntaxError, ValueError, MemoryError, RecursionError):
            continue
        outer = expression.body
        if not isinstance(outer, ast.Call) or not isinstance(outer.func, ast.Call):
            continue
        inner = outer.func
        if _python_call_name(inner.func).lower() != "getattr":
            continue
        if len(inner.args) < 2:
            continue
        module_name: str | None = None
        if isinstance(inner.args[0], ast.Name):
            module_name = module_aliases.get(inner.args[0].id)
        elif isinstance(inner.args[0], ast.Call) and _python_call_name(
            inner.args[0].func
        ).lower() == "__import__" and inner.args[0].args:
            module_name = _python_static_string(inner.args[0].args[0])
        attribute = _python_static_string(inner.args[1])
        if attribute is None:
            return True
        attribute_lower = attribute.lower()
        if attribute_lower not in methods:
            continue
        if module_name in {"os", "subprocess"}:
            return True
        # An unresolved object can still be a process-module alias assigned
        # dynamically.  Rebuild a bounded canonical call when the attribute
        # is a known process API; this catches ``getattr(proc, "run")(... )``
        # without rejecting an unrelated object's harmless ``run`` method
        # whose statically decoded argv is clearly non-Git.
        arguments = command[cursor + 1 : outer_end]
        synthetic = f"subprocess.{attribute}({arguments})"
        if _python_call_mutates(synthetic, depth=1):
            return True
    return False


def _python_dynamic_module_dispatch_mutates(command: str) -> bool:
    """Reject dictionary/dunder dispatch on effectful Python modules.

    Calls such as ``subprocess.__dict__["run"](...)`` and
    ``vars(os)["system"](...)`` hide the API name from the ordinary dotted
    call recognizers.  Resolving arbitrary dictionaries is outside a
    source-only proof, so any dispatch-looking use of the known process/HTTP
    modules is rejected.  The scan runs on a literal-masked source to avoid
    matching prose or comments.
    """

    masked = _python_mask_literals(command)
    modules = r"(?:subprocess|os|requests|httpx|urllib(?:\.request)?)"
    # Attribute dictionaries and __getattribute__ are both dynamic dispatch
    # surfaces.  Require a following index/call so harmless module metadata
    # mentions remain allowed.
    if re.search(
        rf"(?i)\b{modules}\s*\.\s*(?:__dict__|__getattribute__)\b"
        r"\s*(?:\[|\.|\()",
        masked,
    ):
        return True
    if re.search(
        rf"(?i)\bvars\s*\(\s*{modules}\s*\)\s*(?:\[|\.|\()",
        masked,
    ):
        return True
    # ``object.__getattribute__(subprocess, "run")`` and equivalent helper
    # calls have the same semantics even though the module is an argument.
    if re.search(
        rf"(?i)\b__getattribute__\s*\([^\n]{{0,512}}\b{modules}\b",
        masked,
    ):
        return True
    return False


def _python_dynamic_import_bound_aliases(
    command: str,
) -> dict[str, tuple[str, str]]:
    """Collect aliases bound to methods returned by dynamic imports.

    The direct dynamic-import recognizer handles an expression such as
    ``__import__("subprocess").run([...])``.  A small but equivalent command
    graph can split that expression across an assignment (``f =
    __import__("subprocess").run; f([...])``), which is otherwise invisible
    to the dotted-call regexes.  Parse only bounded assignment expressions and
    return the same ``(kind, method)`` shape used by
    :func:`_python_bound_method_mutates`; unresolved/imported modules are not
    treated as safe.
    """

    masked = _python_mask_literals(command)
    importlib_modules = {
        "importlib",
        *(
            alias
            for alias, module in _python_module_aliases(command).items()
            if module == "importlib"
        ),
    }
    importlib_roots = "|".join(
        re.escape(value) for value in sorted(importlib_modules)
    )
    import_function_aliases = _python_import_function_aliases(command)
    import_function_roots = "|".join(
        re.escape(value) for value in sorted(import_function_aliases)
    )
    # Match the assignment and the opening parenthesis only.  The balanced
    # call-end scan below handles nested arguments/quotes without attempting
    # to parse the surrounding shell fragment as Python.
    pattern = re.compile(
        rf"(?m)(?<![A-Za-z0-9_])"
        rf"(?P<target>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
        rf"(?P<root>__import__|(?:{import_function_roots})|"
        rf"(?:{importlib_roots})\s*\.\s*import_module)\s*\("
    )
    aliases: dict[str, tuple[str, str]] = {}
    process_methods = PYTHON_PROCESS_METHODS | PYTHON_OS_METHODS | {
        "fork",
        "forkpty",
    }
    http_methods = {
        "get",
        "head",
        "options",
        "post",
        "put",
        "patch",
        "delete",
        "request",
    }
    for match in pattern.finditer(masked):
        open_index = masked.find("(", match.start("root"), match.end())
        if open_index < 0:
            continue
        close_index = _python_call_end(command, open_index + 1)
        cursor = close_index + 1
        while cursor < len(command) and command[cursor].isspace():
            cursor += 1
        if cursor >= len(command) or command[cursor] != ".":
            continue
        method_match = re.match(
            r"\.\s*([A-Za-z_][A-Za-z0-9_]*)",
            command[cursor:],
        )
        if method_match is None:
            continue
        method = method_match.group(1).lower()
        expression_end = cursor + method_match.end()
        snippet = command[match.start() : expression_end]
        try:
            tree = ast.parse(snippet, mode="exec")
        except (SyntaxError, ValueError, MemoryError, RecursionError):
            continue
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.Assign):
            continue
        assignment = tree.body[0]
        if len(assignment.targets) != 1 or not isinstance(
            assignment.targets[0], ast.Name
        ):
            continue
        target = assignment.targets[0].id
        value = assignment.value
        if not isinstance(value, ast.Attribute) or not isinstance(
            value.value, ast.Call
        ):
            continue
        importer = value.value
        importer_name = _python_call_name(importer.func).lower()
        if importer_name != "__import__" and importer_name not in import_function_aliases and not (
            importer_name.rsplit(".", 1)[-1] == "import_module"
            and importer_name.split(".", 1)[0] in importlib_modules
        ):
            continue
        if not importer.args:
            continue
        module_name = _python_static_string(importer.args[0])
        if module_name in {"subprocess", "os"} and method in {
            value.lower() for value in process_methods
        }:
            aliases[target] = (module_name, method)
        elif module_name in {"requests", "httpx"} and method in http_methods:
            aliases[target] = ("http", method)
        elif module_name == "urllib.request" and method in {"urlopen", "request"}:
            aliases[target] = ("urllib", method)
    return aliases


def _python_bound_method_mutates(command: str, *, depth: int) -> bool:
    """Audit aliases bound to Session/Client or process-module methods."""

    if depth > 2:
        return True
    scan = _python_mask_literals(command)
    module_aliases = _python_module_aliases(command)
    http_modules = {
        alias
        for alias, module in module_aliases.items()
        if module in {"requests", "httpx"}
    }
    http_modules.update({"requests", "httpx"})
    process_modules = {
        alias
        for alias, module in module_aliases.items()
        if module in {"subprocess", "os"}
    }
    process_modules.update({"subprocess", "os"})

    http_objects: set[str] = set()
    constructor_aliases = {"Session", "Client"}
    constructor_aliases.update(
        (match.group(2) or match.group(1))
        for match in PYTHON_SESSION_ALIAS_IMPORT.finditer(scan)
    )
    constructor_aliases.update(
        alias
        for module, symbol, alias in _python_from_import_bindings(command)
        if module in {"requests", "httpx"} and symbol in {"Session", "Client"}
    )
    # Constructor aliases and direct canonical constructors.
    ctor_module_pattern = "|".join(re.escape(value) for value in sorted(http_modules))
    for match in re.finditer(
        rf"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:{ctor_module_pattern})\s*\.\s*(?:Session|Client)\s*\(",
        scan,
        re.I,
    ):
        http_objects.add(match.group(1))
    constructor_pattern = "|".join(
        re.escape(value) for value in sorted(constructor_aliases)
    )
    for match in re.finditer(
        rf"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:{constructor_pattern})\s*\(",
        scan,
        re.I,
    ):
        http_objects.add(match.group(1))
    # Preserve one level of object rebinding (``client2 = client``).
    for _ in range(2):
        changed = False
        for match in re.finditer(
            r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\b",
            scan,
        ):
            if match.group(2) in http_objects and match.group(1) not in http_objects:
                http_objects.add(match.group(1))
                changed = True
        if not changed:
            break

    aliases: dict[str, tuple[str, str]] = {}
    # Dynamic-import bound methods (for example
    # ``f = __import__(\"subprocess\").run``) have the same callable
    # semantics as a direct module-method alias.  Seed them before the
    # ordinary alias pass so they also participate in transitive rebinding.
    aliases.update(_python_dynamic_import_bound_aliases(command))
    # ``f = requests.Session().request`` / ``f = session.post``.
    method_names = (
        "get|head|options|post|put|patch|delete|request"
    )
    for match in re.finditer(
        rf"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
        rf"(?:([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*)?"
        rf"(?:Session|Client)\s*\([^\n]{{0,512}}\)\s*\.\s*({method_names})\b(?!\s*\.)",
        scan,
        re.I,
    ):
        aliases[match.group(1)] = ("http", match.group(3).lower())
    for match in re.finditer(
        rf"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
        rf"([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*({method_names})\b(?!\s*\.)",
        scan,
        re.I,
    ):
        target, receiver, method = match.groups()
        if receiver in http_objects:
            aliases[target] = ("http", method.lower())
        elif receiver in http_modules:
            # Direct convenience-method aliases (``get = requests.get``)
            # still need the body/override checks applied at their call site.
            aliases[target] = ("http", method.lower())

    # A callable alias can be copied through one or more simple assignments
    # (``f = requests.post; g = f; g(url)``).  Resolve a short, bounded chain;
    # unresolved/dynamic assignments remain covered by ``unknown_aliases``
    # below and therefore fail closed when called.
    for _ in range(3):
        changed = False
        for match in re.finditer(
            r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
            r"([A-Za-z_][A-Za-z0-9_]*)\b",
            scan,
        ):
            target, receiver = match.groups()
            if target in aliases or receiver not in aliases:
                continue
            aliases[target] = aliases[receiver]
            changed = True
        if not changed:
            break

    # A method copied from an unresolved object can be a wrapper around either
    # process or HTTP I/O.  If it is subsequently called, resolving that
    # receiver would require executing Python state; fail closed instead of
    # assuming that a name such as ``post``/``run`` is harmless.
    unknown_aliases: set[str] = set()
    dynamic_method_names = {
        value.lower()
        for value in (
            PYTHON_PROCESS_METHODS
            | PYTHON_OS_METHODS
            | {"get", "head", "options", "post", "put", "patch", "delete", "request"}
        )
    }
    for match in re.finditer(
        rf"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
        rf"([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\b(?!\s*\.)",
        scan,
        re.I,
    ):
        target, receiver, method = match.groups()
        if (
            target not in aliases
            and receiver not in http_objects
            and receiver not in http_modules
            and receiver not in process_modules
            and method.lower() in dynamic_method_names
        ):
            unknown_aliases.add(target)

    process_method_pattern = "|".join(
        re.escape(value) for value in sorted(PYTHON_PROCESS_METHODS | PYTHON_OS_METHODS)
    )
    for match in re.finditer(
        rf"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
        rf"([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*({process_method_pattern})\b(?!\s*\.)",
        scan,
        re.I,
    ):
        target, receiver, method = match.groups()
        if receiver in process_modules:
            canonical_module = module_aliases.get(receiver, receiver)
            aliases[target] = (canonical_module, method.lower())

    # Process-method aliases are discovered in the pass above, so repeat the
    # bounded rebinding step after both HTTP and process maps are populated.
    # This closes chains such as ``m = subprocess.run; f = m; f(argv)`` while
    # retaining a finite, source-only resolution bound.
    for _ in range(3):
        changed = False
        for match in re.finditer(
            r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
            r"([A-Za-z_][A-Za-z0-9_]*)\b",
            scan,
        ):
            target, receiver = match.groups()
            if target in aliases or receiver not in aliases:
                continue
            aliases[target] = aliases[receiver]
            changed = True
        if not changed:
            break

    for alias, (kind, method) in aliases.items():
        for match in re.finditer(
            rf"(?<![A-Za-z0-9_]){re.escape(alias)}\s*\(", scan, re.I
        ):
            # Skip the alias assignment's right-hand constructor/reference.
            before = command[max(0, match.start() - 3) : match.start()]
            if "=" in before:
                continue
            end = _python_call_end(command, match.end())
            arguments = command[match.end() : end]
            if kind == "http":
                if method in {"post", "put", "patch", "delete"}:
                    return True
                if method in {"get", "head", "options"}:
                    arguments = f'"{method.upper()}",' + arguments
                if method != "request" and method not in {"get", "head", "options"}:
                    return True
                if not _python_http_has_literal_safe_method(arguments):
                    return True
            elif kind == "urllib":
                # ``urlopen`` aliases require a nested Request object with an
                # explicit read-only method; a bare URL or dynamic Request is
                # not a source-level proof.  Keep ``request`` as the regular
                # requests-like method form for completeness.
                if method == "urlopen":
                    if not _python_http_has_literal_safe_method(
                        arguments, request_object=True
                    ):
                        return True
                elif method == "request":
                    if not _python_http_has_literal_safe_method(arguments):
                        return True
                else:
                    return True
            else:
                synthetic = f"{kind}.{method}({arguments})"
                if _python_call_mutates(synthetic, depth=depth + 1):
                    return True
    for alias in unknown_aliases:
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(alias)}\s*\(", scan, re.I):
            return True
    return False


def _python_getattr_http_mutates(command: str) -> bool:
    """Recognize dynamic HTTP dispatch through ``getattr``."""

    masked = _python_mask_literals(command)
    modules = _python_module_aliases(command)
    modules.update(
        {
            "requests": "requests",
            "httpx": "httpx",
            "urllib": "urllib.request",
        }
    )
    head = re.compile(r"(?i)\bgetattr\s*\(")
    for match in head.finditer(masked):
        inner_end = _python_call_end(command, match.end())
        cursor = inner_end + 1
        while cursor < len(command) and command[cursor].isspace():
            cursor += 1
        if cursor >= len(command) or command[cursor] != "(":
            continue
        outer_end = _python_call_end(command, cursor + 1)
        snippet = command[match.start() : min(len(command), outer_end + 1)]
        try:
            expression = ast.parse(snippet, mode="eval")
        except (SyntaxError, ValueError, MemoryError, RecursionError):
            return True
        outer = expression.body
        if not isinstance(outer, ast.Call) or not isinstance(outer.func, ast.Call):
            continue
        inner = outer.func
        if _python_call_name(inner.func).lower() != "getattr" or len(inner.args) < 2:
            continue
        module_name: str | None = None
        target = inner.args[0]
        # Resolve both a simple alias (``getattr(rq, ...)``) and a
        # qualified module expression (``getattr(urllib.request, ...)``).
        # The latter is an ``ast.Attribute`` rather than ``ast.Name`` and was
        # previously skipped, allowing ``getattr(urllib.request,
        # "urlopen")(url)`` to evade the explicit-method guard.
        target_name = _python_call_name(target).lower()
        if isinstance(target, ast.Name):
            module_name = modules.get(target.id)
        elif target_name in {"requests", "httpx", "urllib.request"}:
            module_name = target_name
        elif isinstance(target, ast.Attribute):
            # ``_python_call_name`` also preserves aliases for dotted names;
            # consult the alias table for the root when available.
            parts = target_name.split(".")
            if parts and parts[0] in modules:
                suffix = ".".join(parts[1:])
                candidate = modules[parts[0]]
                module_name = f"{candidate}.{suffix}" if suffix else candidate
        elif isinstance(target, ast.Call) and _python_call_name(
            target.func
        ).lower() == "__import__" and target.args:
            module_name = _python_static_string(target.args[0])
        if module_name not in {"requests", "httpx", "urllib.request"}:
            continue
        method = _python_static_string(inner.args[1])
        if method is None:
            return True
        method = method.lower()
        arguments = command[cursor + 1 : outer_end]
        if module_name in {"requests", "httpx"}:
            if method in {"post", "put", "patch", "delete"}:
                return True
            if method in {"get", "head", "options"}:
                arguments = f'"{method.upper()}",' + arguments
            if method not in {
                "get",
                "head",
                "options",
                "request",
            } or not _python_http_has_literal_safe_method(arguments):
                return True
        elif method in {"urlopen", "request"}:
            if not _python_http_has_literal_safe_method(
                arguments, request_object=method == "urlopen"
            ):
                return True
        else:
            return True
    return False


def _python_process_alias_mutates(command: str, *, depth: int) -> bool:
    """Audit aliases and ``getattr`` wrappers around process APIs."""

    scan_command = _python_mask_literals(command)
    if re.search(
        r"(?im)^\s*from\s+(?:subprocess|os)\s+import\s+\*", scan_command
    ):
        return True
    if _python_getattr_process_mutates(command):
        return True

    # Module aliases (``import subprocess as sp`` / ``import os as posix``)
    # are as effectful as their canonical names.  Rebuild a synthetic
    # canonical call from each bounded argument payload and pass it through
    # the structural process scanner below.
    for module_alias, module in _python_module_aliases(command).items():
        if module not in {"subprocess", "os"}:
            continue
        methods = (
            PYTHON_SUBPROCESS_METHODS if module == "subprocess" else PYTHON_OS_METHODS
        )
        for method in methods:
            pattern = re.compile(
                rf"(?<![A-Za-z0-9_]){re.escape(module_alias)}\s*\.\s*"
                rf"{re.escape(method)}\s*\(",
                re.I if method.islower() else 0,
            )
            for match in pattern.finditer(scan_command):
                arguments = _python_http_call_arguments(command, match.end())
                synthetic = f"{module}.{method}({arguments})"
                if _python_call_mutates(synthetic, depth=depth + 1):
                    return True

    aliases: dict[str, str] = {
        match.group(1): match.group(2)
        for match in PYTHON_PROCESS_ALIAS_ASSIGNMENT.finditer(scan_command)
    }
    for module_alias, module in _python_module_aliases(command).items():
        methods = (
            PYTHON_SUBPROCESS_METHODS
            if module == "subprocess"
            else PYTHON_OS_METHODS
            if module == "os"
            else ()
        )
        for method in methods:
            for match in re.finditer(
                rf"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
                rf"{re.escape(module_alias)}\s*\.\s*{re.escape(method)}\b",
                scan_command,
                re.I if method.islower() else 0,
            ):
                aliases[match.group(1)] = f"{module}.{method}"
    for match in PYTHON_PROCESS_ALIAS_IMPORT.finditer(scan_command):
        module, symbol, alias = match.groups()
        aliases[alias or symbol] = f"{module}.{symbol}"
    # Parenthesized/multiline ``from`` imports are not matched by the compact
    # regex above. Reuse the bounded AST bindings so ``from subprocess import
    # (run as r); r([\"git\", \"push\"])`` cannot evade the process gate.
    for module, symbol, alias in _python_from_import_bindings(command):
        if module in {"subprocess", "os"} and any(
            symbol.lower() == candidate.lower()
            for candidate in (PYTHON_SUBPROCESS_METHODS | PYTHON_OS_METHODS)
        ):
            aliases[alias] = f"{module}.{symbol}"

    # Imported process callables can be rebound before invocation (``r`` to
    # ``g`` in ``from subprocess import run as r; g = r; g(argv)``).  Resolve a
    # short chain so the same fail-closed policy applies to direct and copied
    # aliases alike.
    for _ in range(3):
        changed = False
        for match in re.finditer(
            r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
            r"([A-Za-z_][A-Za-z0-9_]*)\b",
            scan_command,
        ):
            target, receiver = match.groups()
            if target in aliases or receiver not in aliases:
                continue
            aliases[target] = aliases[receiver]
            changed = True
        if not changed:
            break

    for alias, target in aliases.items():
        for match in re.finditer(
            rf"(?<![A-Za-z0-9_]){re.escape(alias)}\s*\(", scan_command
        ):
            # Skip the right-hand side of an alias assignment itself.
            if match.start() > 0 and command[max(0, match.start() - 2) : match.start()].strip().endswith("="):
                continue
            end = _python_call_end(command, match.end())
            arguments = command[match.end() : end]
            synthetic = f"{target}({arguments})"
            if _python_call_mutates(synthetic, depth=depth + 1):
                return True
    return False


def _python_env_mapping_is_safe(node: ast.AST) -> bool:
    """Return whether a literal subprocess environment is non-redirecting."""

    if not isinstance(node, ast.Dict):
        return False
    dangerous_prefixes = (
        "GIT_",
        "PATH",
    )
    for key in node.keys:
        key_value = _python_static_string(key) if key is not None else None
        if key_value is None:
            return False
        upper = key_value.upper()
        if upper == "PATH" or any(upper.startswith(prefix) for prefix in dangerous_prefixes if prefix != "PATH"):
            return False
    return True


def _python_exec_call_mutates(call: ast.Call, name: str) -> bool:
    """Audit ``os.exec*``/``os.spawn*`` calls and nested shell wrappers.

    These APIs do not use the ``subprocess.run(argv)`` signature: ``exec*``
    takes ``(path, argv)`` while ``spawn*`` prefixes those with a mode.  Keep
    the small signature distinction explicit so a static ``echo`` invocation
    remains harmless but ``os.execvp('git', ['git', 'push'])`` (or a static
    ``flock``/``parallel`` wrapper carrying that command) cannot bypass the
    process scanner.
    """

    method = name.rsplit(".", 1)[-1].lower()
    if method in {"fork", "forkpty", "fexecve"}:
        # The child/file-descriptor target is not statically attributable to a
        # harmless executable.  A source-only workflow gate cannot establish
        # that the fork/descriptor path will not mutate the checkout.
        return True
    if method == "startfile":
        if not call.args:
            return True
        target = _python_static_string(call.args[0])
        if target is None:
            return True
        # ``startfile`` delegates to a platform handler; even a non-Git path
        # can launch a repository-mutating script.  Keep only an explicitly
        # boring executable/document suffix as an allow case.
        return _is_git_executable_or_helper(target) or target.lower().endswith(
            ('.sh', '.py', '.exe', '.com', '.bat', '.cmd')
        )

    is_spawn = method.startswith("spawn")
    is_l_family = method.startswith("exec") and method.startswith("execl")
    if is_spawn:
        path_index = 1
        argv_index = None if method.startswith("spawnl") else 2
    else:
        path_index = 0
        argv_index = None if is_l_family else 1
    if len(call.args) <= path_index:
        return True
    path = _python_static_string(call.args[path_index])
    if path is None:
        return True
    if _python_path_invocation_mutates(path):
        return True

    # ``*e`` variants carry an environment mapping as their final argument.
    # Dynamic or helper-related environment values can redirect even a
    # read-only-looking Git invocation.
    if method.endswith("e") and call.args:
        if not _python_env_mapping_is_safe(call.args[-1]):
            return True

    if argv_index is None:
        # execl*/spawnl* pass argv[0], argv[1], ... as individual positional
        # strings.  The environment (for *e) was removed above.
        end = len(call.args) - (1 if method.endswith("e") else 0)
        argv_values = [_python_static_string(value) for value in call.args[path_index + 1 : end]]
        if any(value is None for value in argv_values):
            return True
        argv = [value for value in argv_values if value is not None]
    else:
        if len(call.args) <= argv_index:
            return True
        argv_node = call.args[argv_index]
        argv = _python_static_argv(argv_node)
        if argv is None or any(value is None for value in argv):
            return True
        argv = [value for value in argv if value is not None]

    path_base = _executable_basename(path)
    if _is_git_executable_or_helper(path):
        # argv[0] is the display name for exec*/spawn*; the actual executable
        # is the statically decoded path supplied above.
        concrete = [path, *argv[1:]] if argv else [path]
        return _git_invocation_mutates(concrete, 0)

    # Shell/interpreter launchers can execute a Git command encoded in an
    # argument even when their path is not itself named ``git``.
    if path_base in {"sh", "bash", "dash", "zsh", "ksh", "git-shell"}:
        if any(_contains_mutation(value, _depth=1) for value in argv):
            return True
    elif path_base in SHELL_WRAPPERS | SHELL_GRAPH_WRAPPERS:
        # ``os.exec*``/``os.spawn*`` can launch the same command-graph
        # wrappers as ``subprocess.run``.  The argv is fully static at this
        # point (dynamic values returned above), so rebuild the concrete
        # command with the executable path and recursively apply the shell
        # wrapper policy.  As with the Git branch, argv[0] is only the
        # display name and must not be retained as a second command argument.
        concrete = [path, *argv[1:]] if argv else [path]
        if _contains_mutation(shlex.join(concrete), _depth=1):
            return True
    return False


def _python_primary_argument(call: ast.Call, *, shell_string: bool = False) -> ast.AST | None:
    """Return the command argument from positional or keyword call forms."""

    if call.args:
        return call.args[0]
    names = ("command", "cmd") if shell_string else ("args", "argv", "command", "cmd")
    for keyword in call.keywords:
        if keyword.arg in names:
            return keyword.value
    return None


def _python_formatted_value_mutates(command: str) -> bool:
    """Reject process or HTTP calls evaluated inside f-string expressions."""
    try:
        tree = ast.parse(command, mode="exec")
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return False
    effectful = {
        value.lower()
        for value in (
            *(PYTHON_PROCESS_METHODS),
            "system", "post", "put", "patch", "delete", "request", "urlopen",
        )
    }
    for formatted in ast.walk(tree):
        if not isinstance(formatted, ast.FormattedValue):
            continue
        for node in ast.walk(formatted.value):
            if isinstance(node, ast.Call):
                terminal = _python_call_name(node.func).rsplit(".", 1)[-1].lower()
                if terminal in effectful:
                    return True
    return False

def _python_call_mutates(command: str, *, depth: int) -> bool:
    """Inspect Python process/network calls without executing their payloads.

    Only a statically decoded argv executable and Git subcommand are accepted
    as read-only proof. Dynamic argv construction, ``shell=True``, eval/exec,
    and dynamic HTTP methods fail closed. Ordinary calls such as
    ``subprocess.run(["echo", ...])`` are not rejected merely because their
    arguments contain the word ``git``.
    """

    if depth > 2:
        return True

    if _python_formatted_value_mutates(command):
        return True

    if _python_dynamic_module_dispatch_mutates(command):
        return True

    if _python_bound_method_mutates(command, depth=depth):
        return True

    if _python_interpreter_payload_mutates(command, depth=depth):
        return True

    if _python_dynamic_import_mutates(command, depth=depth):
        return True

    if _python_process_alias_mutates(command, depth=depth):
        return True

    scan_command = _python_mask_literals(command)
    # Dynamic code evaluation can construct a mutating process/network call
    # entirely from strings, so it is never a source-level read-only proof.
    if re.search(r"(?i)\b(?:eval|exec)\s*\(", scan_command):
        return True

    for match in PYTHON_COMMAND_CALL.finditer(scan_command):
        end = _python_call_end(command, match.end())
        payload = command[match.end() : end]
        try:
            # Parse the complete matched call, including its function name.
            # Wrapping only the argument payload (``__call__(...)``) loses
            # the distinction between subprocess and shell APIs and makes a
            # list such as ``['git', 'push']`` look like an arbitrary call.
            expression = ast.parse(command[match.start() : min(len(command), end + 1)], mode="eval")
            call = expression.body
        except (SyntaxError, ValueError, MemoryError, RecursionError):
            # Malformed/partial Python in a shell heredoc cannot be proven
            # safe if it visibly references a Git command.
            if re.search(r"(?i)\bgit(?:\.exe)?\b", payload):
                return True
            continue
        if not isinstance(call, ast.Call):
            continue

        name = _python_call_name(call.func).lower()
        is_process = name.startswith("subprocess.")
        is_shell = name in {"os.system", "os.popen", "system"}
        if name.startswith("os.") and name.rsplit(".", 1)[-1] in PYTHON_EXEC_METHODS:
            if _python_exec_call_mutates(call, name):
                return True
            continue
        first = _python_primary_argument(call, shell_string=is_shell)
        if first is None:
            # A process/shell API without a statically attributable command
            # argument is malformed or dynamically supplied; neither is a
            # read-only proof.
            if is_process or is_shell:
                return True
            continue
        if not (is_process or is_shell):
            continue

        static_string = _python_static_string(first)
        argv = _python_static_argv(first)
        if is_process:
            # A keyword expansion can turn a literal argv into a shell
            # command or inject a helper/environment mapping.  Permit only an
            # explicit boolean ``False`` for ``shell``; unknown ``**kwargs``
            # and dynamic shell values fail closed.
            for keyword in call.keywords:
                if keyword.arg is None:
                    return True
                if keyword.arg not in PYTHON_SAFE_PROCESS_KEYWORDS:
                    return True
                if keyword.arg == "shell":
                    if not (
                        isinstance(keyword.value, ast.Constant)
                        and type(keyword.value.value) is bool
                        and keyword.value.value is False
                    ):
                        return True
                elif keyword.arg == "executable":
                    executable_value = _python_static_string(keyword.value)
                    if executable_value is None or _python_path_invocation_mutates(
                        executable_value
                    ):
                        return True
                elif keyword.arg == "env":
                    if not _python_env_mapping_is_safe(keyword.value):
                        # An inherited/dynamic environment can install a Git
                        # alias, path, or transport helper that is not visible
                        # in the argv literal.
                        return True
            if argv is not None:
                if not argv:
                    continue
                executable = argv[0]
                if executable is None:
                    # A dynamic executable can be ``git`` (or a mutating
                    # helper) after shell/Python evaluation; there is no
                    # source-level proof that it is harmless.
                    return True
                executable_base = _executable_basename(executable)
                concrete = [value for value in argv if value is not None]
                if _python_path_invocation_mutates(executable):
                    return True
                if _is_git_executable_or_helper(executable):
                    # Dynamic values are acceptable only after a statically
                    # approved read-only verb (for example pathspecs after
                    # ``git ls-files --``). Truncate at the first unresolved
                    # element: if the known prefix is incomplete or mutating,
                    # _git_invocation_mutates fails closed; if it is a
                    # read-only verb, the unresolved value is merely an
                    # argument and does not change the command graph.
                    if any(value is None for value in argv):
                        first_dynamic = next(
                            index for index, value in enumerate(argv) if value is None
                        )
                        known_prefix = [
                            value for value in argv[:first_dynamic] if value is not None
                        ]
                        if _git_invocation_mutates(known_prefix, 0):
                            return True
                    elif _git_invocation_mutates(
                        [value for value in argv if value is not None], 0
                    ):
                        return True
                elif executable_base in GH_EXECUTABLES | HTTP_EXECUTABLES:
                    # A static Python argv is still an actual command. Apply
                    # the same strict GitHub CLI/HTTP method policy used for
                    # shell tokens; unresolved elements cannot establish a
                    # read-only request.
                    if any(value is None for value in argv):
                        return True
                    concrete = [value for value in argv if value is not None]
                    if executable_base in GH_EXECUTABLES:
                        if _github_invocation_mutates(concrete, 0):
                            return True
                    elif _http_invocation_mutates(concrete, 0):
                        return True
                elif executable_base in SHELL_INTERPRETERS | PYTHON_INTERPRETERS:
                    # A process argv can launch a nested shell/Python script
                    # just as directly written workflow text can. Reuse the
                    # reviewed path inventory and interpreter payload parser
                    # so ``run(["bash", "-c", "git push"])`` and
                    # ``run(["python3", "tools/evil.py"])`` fail closed.
                    script_argument = _interpreter_script_argument(concrete, 0)
                    if script_argument is not None and _python_path_invocation_mutates(
                        script_argument
                    ):
                        return True
                    if executable_base in SHELL_INTERPRETERS:
                        payload, dynamic = _shell_interpreter_payload(concrete, 0)
                        if payload is not None and (
                            dynamic or _contains_mutation(payload, _depth=depth + 1)
                        ):
                            return True
                    else:
                        payload, dynamic = _python_interpreter_payload(concrete)
                        if payload is not None and (
                            dynamic
                            or _python_http_call_mutates(payload)
                            or _python_call_mutates(payload, depth=depth + 1)
                        ):
                            return True
                elif executable_base in SHELL_WRAPPERS | SHELL_GRAPH_WRAPPERS:
                    # Static Python argv can also launch a shell command
                    # through a wrapper such as ``flock``/``parallel`` or a
                    # prefix wrapper such as ``env``/``timeout``. Reuse the
                    # shell command-graph scanner so wrapper option values,
                    # ``--`` terminators, and nested interpreters receive the
                    # same fail-closed treatment as literal workflow shell.
                    if _contains_mutation(
                        shlex.join(concrete), _depth=depth + 1
                    ):
                        return True
                elif any(value is not None and re.search(r"(?i)\bgit(?:\.exe)?\b", value) for value in argv[1:]):
                    # ``echo 'git push'`` is data, not an invocation.
                    continue
                continue
            if static_string is not None:
                try:
                    tokens = shlex.split(static_string, comments=False, posix=True)
                except ValueError:
                    return True if re.search(r"(?i)\bgit(?:\.exe)?\b", static_string) else False
                if tokens:
                    if _git_invocation_mutates(tokens, 0):
                        return True
                    if any(character.isspace() for character in static_string) and _contains_mutation(
                        static_string, _depth=depth + 1
                    ):
                        return True
                continue
            if re.search(r"(?i)\bgit(?:\.exe)?\b", payload):
                return True
            # An unresolved argv/string can invoke an arbitrary executable;
            # without a statically decoded read-only Git prefix there is no
            # source-level proof that it cannot mutate the checkout.
            return True

        # os.system/popen/system take a shell string.  A literal read-only
        # command can be checked recursively; dynamic concatenation is not a
        # proof when Git appears in the expression.
        if static_string is not None:
            if _contains_mutation(static_string, _depth=depth + 1):
                return True
        else:
            # os.system/popen/system execute a shell string. Dynamic string
            # construction is never a bounded read-only proof, even when the
            # word ``git`` happens to be held in another variable.
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
                and _executable_basename(tokens[start]) in SHELL_INTERPRETERS
            ):
                payload, dynamic = _shell_interpreter_payload(tokens, start)
                if (
                    payload is not None
                    and not dynamic
                    and _has_command_invocation(
                        [payload], command, _depth=_depth + 1
                    )
                ):
                    return True
    return False


def _contains_mutation(command: str, *, _depth: int = 0) -> bool:
    # An unquoted heredoc body is expanded by the invoking shell before it is
    # delivered to ``cat``/Python/etc.  Masking that body as inert data would
    # otherwise hide ``$(git push)`` and backtick substitutions.  Quoted
    # delimiters remain eligible for the ordinary body-kind handling below.
    if _unquoted_heredoc_expansion_mutates(command):
        return True
    # Keep Python source intact for the AST recognizers, but remove shell
    # heredoc bodies before lexical shell scanning.  A heredoc is data for the
    # command that consumes it; words such as ``gh api``/``curl -X POST`` in a
    # fixture payload are not executed by the workflow shell.
    shell_command = _strip_shell_heredoc_bodies(command)
    # Expand only the exact IFS separator forms before token-level Git
    # dispatch.  Without this normalization, `fetch${IFS}origin${IFS}main`
    # is seen as a one-token incomplete fetch and is rejected even though its
    # bounded expansion is the reviewed read-only `git fetch origin main`
    # shape.  Other parameter expansions remain opaque and fail closed.
    if SHELL_IFS_EXPANSION.search(shell_command):
        shell_command = SHELL_IFS_EXPANSION.sub(" ", shell_command)
    python_command = _python_scan_source(command)
    if _python_http_call_mutates(python_command):
        return True
    if _python_call_mutates(python_command, depth=_depth):
        return True
    if _shell_dynamic_mutates(shell_command, depth=_depth):
        return True

    # Normalize shell line continuations, then inspect only command-position
    # Git/GitHub CLI tokens. Quoted prose/argv literals are not executed;
    # nested shell substitutions are handled by ``_shell_dynamic_mutates``.
    for tokens in _shell_command_tokens(shell_command, strip_comments=True):
        for index in _shell_git_command_indices(tokens):
            if _git_invocation_mutates(tokens, index):
                return True
        for start in _shell_command_start_indices(tokens):
            index = _shell_executable_index(tokens, start)
            if index < len(tokens):
                if _shell_is_executable_probe(tokens[start:index]):
                    continue
                if _direct_http_invocation_mutates(tokens, index):
                    return True
                if _github_invocation_mutates(tokens, index):
                    return True
                if _http_invocation_mutates(tokens, index):
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
