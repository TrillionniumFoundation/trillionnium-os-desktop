from __future__ import annotations

from contextlib import redirect_stderr
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_governance_integrity_under_test",
    ROOT / "tools/validate_governance_integrity.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VALIDATOR
SPEC.loader.exec_module(VALIDATOR)


class StrictYamlParserTests(unittest.TestCase):
    def assert_rejected(self, source: str) -> None:
        with self.assertRaises(VALIDATOR.YamlParseError):
            VALIDATOR.parse_yaml_strict(source, source="fixture.yml")

    def test_duplicate_block_and_flow_keys_are_rejected(self) -> None:
        self.assert_rejected("permissions:\n  contents: read\n  contents: none\n")
        self.assert_rejected("permissions: {contents: read, contents: none}\n")
        self.assert_rejected("'permissions': read\npermissions: none\n")

    def test_alias_merge_anchor_and_tag_syntax_is_rejected(self) -> None:
        for source in (
            "defaults: &defaults\n  run: echo ok\n",
            "defaults: *defaults\n",
            "defaults:\n  <<: *defaults\n",
            "value: !!str read\n",
        ):
            with self.subTest(source=source):
                self.assert_rejected(source)

    def test_flow_style_and_quoted_keys_are_normalized(self) -> None:
        model = VALIDATOR.parse_yaml_strict(
            "'on': [pull_request, push]\n"
            "permissions: { 'contents': read }\n"
            "jobs: {build: {steps: [{uses: 'actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'}]}}\n",
            source="fixture.yml",
        )
        self.assertEqual(model["on"], ["pull_request", "push"])
        self.assertEqual(model["permissions"], {"contents": "read"})
        self.assertEqual(model["jobs"]["build"]["steps"][0]["uses"], "actions/checkout@" + "a" * 40)

    def test_expression_operators_are_not_mistaken_for_anchors(self) -> None:
        model = VALIDATOR.parse_yaml_strict(
            "env:\n  ROLE: ${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}\n",
            source="fixture.yml",
        )
        self.assertIn("&&", model["env"]["ROLE"])


class GovernanceModelTests(unittest.TestCase):
    SHA = "a" * 40

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.old_root = VALIDATOR.ROOT
        VALIDATOR.ROOT = self.root

    def tearDown(self) -> None:
        VALIDATOR.ROOT = self.old_root
        self.temporary.cleanup()

    def workflow(self, **changes):
        model = {
            "name": "fixture",
            "on": {"pull_request": {"branches": ["main"]}},
            "permissions": {"contents": "read"},
            "jobs": {
                "build": {
                    "name": "build",
                    "steps": [
                        {
                            "name": "checkout",
                            "uses": f"actions/checkout@{self.SHA}",
                            "with": {"persist-credentials": False},
                        },
                        {"run": "printf 'ok\\n'"},
                    ],
                }
            },
        }
        model.update(changes)
        return model

    def reject(self, model, name="fixture.yml"):
        path = self.root / name
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            VALIDATOR.validate_workflow(path, model)

    def test_flow_write_permission_is_rejected(self) -> None:
        model = self.workflow(permissions={"contents": "write"})
        self.reject(model)

    def test_pull_request_target_is_rejected_even_in_flow_form(self) -> None:
        model = self.workflow(**{"on": ["pull_request_target"]})
        self.reject(model)

    def test_mutable_and_compact_action_references_are_rejected(self) -> None:
        for value in (
            "actions/checkout@main",
            "actions/checkout@v4",
            "actions/checkout@" + "A" * 40,
        ):
            with self.subTest(value=value):
                model = self.workflow(
                    jobs={
                        "build": {
                            "steps": [
                                {
                                    "uses": value,
                                    "with": {"persist-credentials": False},
                                }
                            ]
                        }
                    }
                )
                self.reject(model)

    def test_checkout_must_explicitly_drop_credentials(self) -> None:
        model = self.workflow(
            jobs={
                "build": {
                    "steps": [
                        {"uses": f"actions/checkout@{self.SHA}", "with": {}}
                    ]
                }
            }
        )
        self.reject(model)
        for value in (0, 1, "False", "TRUE"):
            with self.subTest(value=value):
                model = self.workflow(
                    jobs={
                        "build": {
                            "steps": [
                                {
                                    "uses": f"actions/checkout@{self.SHA}",
                                    "with": {"persist-credentials": value},
                                }
                            ]
                        }
                    }
                )
                self.reject(model)

    def test_checkout_owner_case_cannot_bypass_credential_guard(self) -> None:
        model = self.workflow(
            jobs={
                "build": {
                    "steps": [
                        {
                            "uses": f"Actions/Checkout@{self.SHA}",
                            "with": {},
                        }
                    ]
                }
            }
        )
        self.reject(model)

    def test_conditional_jobs_and_steps_are_limited_to_diagnostics(self) -> None:
        for condition in (
            False,
            True,
            "false",
            "always()",
            "failure()",
            "${{ github.event_name == 'push' }}",
        ):
            with self.subTest(condition=condition):
                model = self.workflow(
                    jobs={
                        "build": {
                            "if": condition,
                            "steps": [{"run": "printf 'ok\\n'"}],
                        }
                    }
                )
                self.reject(model)
        for condition in ("always()", "failure()"):
            with self.subTest(condition=condition):
                model = self.workflow(
                    jobs={
                        "build": {
                            "steps": [
                                {
                                    "if": condition,
                                    "name": "Upload bounded diagnostic artifact",
                                    "uses": f"actions/upload-artifact@{self.SHA}",
                                }
                            ],
                        }
                    }
                )
                VALIDATOR.validate_workflow(self.root / "fixture.yml", model)
        self.reject(
            self.workflow(
                jobs={
                    "build": {
                        "steps": [
                            {
                                "if": "always()",
                                "name": "Run required gate",
                                "run": "printf 'gate\\n'",
                            }
                        ]
                    }
                }
            )
        )

    def test_local_node_and_docker_actions_are_rejected_without_runtime_scanner(
        self,
    ) -> None:
        for using, metadata in (
            ("node20", "  main: index.js\n"),
            ("docker", "  image: Dockerfile\n"),
        ):
            with self.subTest(using=using):
                action = self.root / ".github/actions/local"
                action.mkdir(parents=True)
                (action / "action.yml").write_text(
                    "name: local\n"
                    "runs:\n"
                    f"  using: {using}\n"
                    + metadata,
                    encoding="utf-8",
                )
                if using.startswith("node"):
                    (action / "index.js").write_text(
                        "require('child_process').exec('git push')\n",
                        encoding="utf-8",
                    )
                model = self.workflow(
                    jobs={"build": {"steps": [{"uses": "./.github/actions/local"}]}}
                )
                self.reject(model)
                import shutil

                shutil.rmtree(action)

    def test_git_and_github_mutation_forms_are_rejected(self) -> None:
        commands = (
            "git -C . push origin main",
            "git update-ref refs/heads/main deadbeef",
            "gh api --method POST https://api.github.com/repos/example/repo",
            "curl --request POST https://api.github.com/repos/example/repo",
            "requests.post('https://api.github.com/repos/example/repo')",
            "subprocess.run(['git', 'push', 'origin', 'main'])",
        )
        for command in commands:
            with self.subTest(command=command):
                model = self.workflow(jobs={"build": {"steps": [{"run": command}]}})
                self.reject(model)

    def test_path_qualified_case_insensitive_git_and_helper_mutations_are_rejected(
        self,
    ) -> None:
        commands = (
            "/usr/bin/git push origin main",
            "GIT -C . PUSH origin main",
            "git.exe --git-dir /tmp/repo push origin main",
            "/usr/libexec/git-receive-pack repo.git",
            "git-upload-pack repo.git",
            "subprocess.run(['/usr/bin/git', '-C', '.', 'push', 'origin', 'main'])",
            "subprocess.call(['GIT.EXE', '--git-dir', '/tmp/repo', 'PUSH'])",
            "subprocess.Popen(['git-receive-pack', 'repo.git'])",
            "os.system('git -C . push origin main')",
            'system("/usr/bin/git --git-dir /tmp/repo update-ref refs/heads/main deadbeef")',
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(VALIDATOR._contains_mutation(command))
                model = self.workflow(jobs={"build": {"steps": [{"run": command}]}})
                self.reject(model)

    def test_dynamic_shell_git_mutation_forms_are_rejected(self) -> None:
        commands = (
            "x=git; $x push origin main",
            "g=/usr/bin/git; ${g} --git-dir /tmp/repo push origin main",
            "git push${IFS}origin${IFS}main",
            "git\n push origin main",
            "git -C .\n push origin main",
            "bash -c 'x=git; $x push origin main'",
            "bash -c 'git\n push origin main'",
            'bash --login -c "git push origin main"',
            'bash --noprofile --norc -c "git push origin main"',
            'sh --login -c "git push origin main"',
            "sudo -u builder git push origin main",
            "timeout 30 git push origin main",
            "if git push origin main; then :; fi",
            "while git push origin main; do :; done",
            "if true; then ! git push origin main; fi",
            "if true; then { git push origin main; }; fi",
            "coproc git push origin main",
            "coproc worker { git push origin main; }",
            'env -S "git push origin main"',
            'env --split-string="git push origin main"',
            "command -p git push origin main",
            "exec -a harmless-name git push origin main",
            "timeout --signal KILL 30 git push origin main",
            "timeout --signal=KILL 30 -- git push origin main",
            "f(){git push origin main;};f",
            "f(){ source /tmp/unreviewed.sh; };f",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(VALIDATOR._contains_mutation(command))
                model = self.workflow(jobs={"build": {"steps": [{"run": command}]}})
                self.reject(model)
        for command in (
            "x=git; $x status --short",
            "git fetch${IFS}origin${IFS}main",
        ):
            with self.subTest(command=command):
                self.assertFalse(VALIDATOR._contains_mutation(command))

    def test_dynamic_git_command_graph_forms_are_rejected(self) -> None:
        """Reject Git mutations hidden behind shell command-graph features.

        These forms are intentionally conservative: resolving a subcommand
        variable, array expansion, alias, function, Git config alias, or an
        unreviewed sourced script would require executing shell state.  The
        source gate must fail closed rather than treating the visible
        ``git status`` tail as proof of read-only behavior.
        """

        commands = (
            'verb="${GIT_VERB:-push}"; git "$verb" origin main',
            'git "$GIT_VERB" origin main',
            'cmd=(git push origin main); "${cmd[@]}"',
            'cmd=(git); sub=(push); "${cmd[@]}" "${sub[@]}" origin main',
            '$(printf git) push origin main',
            '`printf git` push origin main',
            "alias g='git push'; g origin main",
            "g() { git push origin main; }; g",
            "function g { git push origin main; }; g",
            "w=flock; $w /tmp/lock git push",
            "w=parallel; $w --jobs 2 git push ::: x",
            "w=coproc; $w worker git push",
            (
                "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.g "
                "GIT_CONFIG_VALUE_0='!git push'; git status"
            ),
            "source ./unreviewed.sh; git status",
            'source "$UNREVIEWED_SCRIPT"; git status',
            "git init /tmp/repo",
            "git worktree add /tmp/repo",
            "git hash-object -w payload",
            "git --upload-pack=custom-helper status",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(VALIDATOR._contains_mutation(command))
                model = self.workflow(jobs={"build": {"steps": [{"run": command}]}})
                self.reject(model)

        # The one sourced helper explicitly reviewed by the policy and a
        # literal read-only command remain valid allow cases.
        for command in (
            "x=git; $x status --short",
            "source ./tools/reject_symlink_path.sh",
            'source "$PWD/tools/reject_symlink_path.sh"',
            'source "$GITHUB_WORKSPACE/tools/reject_symlink_path.sh"',
            "git -C . fetch --no-tags origin main",
        ):
            with self.subTest(allow_command=command):
                self.assertFalse(VALIDATOR._contains_mutation(command))
                model = self.workflow(jobs={"build": {"steps": [{"run": command}]}})
                VALIDATOR.validate_workflow(self.root / "fixture.yml", model)

    def test_dynamic_github_cli_forms_are_rejected(self) -> None:
        """Reject dynamic gh executable/subcommand and alias paths.

        ``gh`` is extensible and its aliases/configuration can introduce a
        write operation without a literal ``gh api`` token.  Only explicit
        help/version probes are retained as harmless allow cases.
        """

        commands = (
            'gh "$GH_VERB" 1',
            'gh ${GH_VERB:-api} --method POST https://api.github.com/repos/example/repo',
            '${GH_BIN:-gh} api --method POST https://api.github.com/repos/example/repo',
            # Use a read-only-looking ``api`` request so the case exercises
            # dynamic executable resolution itself, rather than the separate
            # literal POST recognizer.
            'GH_BIN=gh; $GH_BIN api --method GET https://api.github.com/repos/example/repo',
            'GH_BIN=gh; "$GH_BIN" api --method GET https://api.github.com/repos/example/repo',
            '`printf gh` api https://api.github.com/repos/example/repo',
            "gh alias set p 'pr merge'; gh p 1",
            'gh --hostname "$GH_HOST" "$GH_VERB"',
            'gh api --method "$METHOD" https://api.github.com/repos/example/repo',
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(VALIDATOR._contains_mutation(command))
                model = self.workflow(jobs={"build": {"steps": [{"run": command}]}})
                self.reject(model)

        for command in ("gh --version", "gh --help", "gh help", "gh version"):
            with self.subTest(allow_command=command):
                self.assertFalse(VALIDATOR._contains_mutation(command))
                model = self.workflow(jobs={"build": {"steps": [{"run": command}]}})
                VALIDATOR.validate_workflow(self.root / "fixture.yml", model)
        for command in (
            "gh --help api",
            "gh help api",
            "gh --version api",
            "gh -h --hostname example.com",
        ):
            with self.subTest(reject_command=command):
                self.assertTrue(VALIDATOR._contains_mutation(command))
                model = self.workflow(jobs={"build": {"steps": [{"run": command}]}})
                self.reject(model)

    def test_dynamic_rest_methods_are_rejected(self) -> None:
        """Reject curl/wget methods that are not statically read-only."""

        commands = (
            'curl -X "$METHOD" https://api.github.com/repos/example/repo',
            'curl --request=${METHOD:-POST} https://api.github.com/repos/example/repo',
            'curl -X"$METHOD" https://api.github.com/repos/example/repo',
            'curl -X$METHOD https://api.github.com/repos/example/repo',
            'curl -X${METHOD:-POST} https://api.github.com/repos/example/repo',
            'curl --request${METHOD:-POST} https://api.github.com/repos/example/repo',
            'wget --method="$METHOD" https://api.github.com/repos/example/repo',
            'wget --method ${METHOD} https://api.github.com/repos/example/repo',
            'wget --method${METHOD} https://api.github.com/repos/example/repo',
            'CURL_BIN=curl; $CURL_BIN -X$METHOD https://api.github.com/repos/example/repo',
            'CURL_BIN=curl; "$CURL_BIN" -X$METHOD https://api.github.com/repos/example/repo',
            'curl --post-data="$DATA" https://api.github.com/repos/example/repo',
            'wget --post-file="$FILE" https://api.github.com/repos/example/repo',
            'wget --body-data="$DATA" https://api.github.com/repos/example/repo',
            'wget --body-file="$FILE" https://api.github.com/repos/example/repo',
            'curl --config-file="$CFG" https://api.github.com/repos/example/repo',
            'curl --json "$DATA" https://api.github.com/repos/example/repo',
            'curl --config "$CFG" https://api.github.com/repos/example/repo',
            'curl -H "$HEADER" https://api.github.com/repos/example/repo',
            'curl --header="$(cat header.txt)" https://api.github.com/repos/example/repo',
            'curl -H @headers.txt https://api.github.com/repos/example/repo',
            # The destination can be non-GitHub: an unresolved HTTP method is
            # still not a source-level proof that no external effect occurs.
            'curl --request "$METHOD" https://example.test/resource',
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(VALIDATOR._contains_mutation(command))
                model = self.workflow(jobs={"build": {"steps": [{"run": command}]}})
                self.reject(model)

        for command in (
            "curl -X GET https://api.github.com/repos/example/repo",
            "curl --request HEAD https://example.test/resource",
            "wget --method=GET https://api.github.com/repos/example/repo",
            "curl https://api.github.com/repos/example/repo",
        ):
            with self.subTest(allow_command=command):
                self.assertFalse(VALIDATOR._contains_mutation(command))
                model = self.workflow(jobs={"build": {"steps": [{"run": command}]}})
                VALIDATOR.validate_workflow(self.root / "fixture.yml", model)

    def test_dynamic_python_http_methods_are_rejected(self) -> None:
        """Reject requests/httpx/urllib calls with unresolved methods."""

        commands = (
            'requests.request(method, "https://api.github.com/repos/example/repo")',
            'requests.request(method=method, url="https://api.github.com/repos/example/repo")',
            'httpx.request(method, "https://api.github.com/repos/example/repo")',
            'httpx.request(method=method, url="https://api.github.com/repos/example/repo")',
            (
                'urllib.request.urlopen(urllib.request.Request('
                '"https://api.github.com/repos/example/repo", method=method))'
            ),
            'req = requests.request; req(method, url)',
            'from requests import request as req; req(method, url)',
            'requests.Session().request(method, url)',
            'requests.Session().post(url)',
            'httpx.Client().delete(url)',
            'session = requests.Session(); session.put(url)',
            'client = httpx.Client(); client.patch(url)',
            'from requests import post; post(url)',
            'from httpx import delete as remove; remove(url)',
            'post = requests.post; post(url)',
            'from urllib.request import urlopen as open_url; open_url(req)',
            'u = urllib.request.urlopen; u(req)',
            'getattr(urllib.request, "urlopen")(url)',
            '__import__("urllib.request").request.urlopen(__import__("urllib.request").request.Request(url, method="POST"))',
            'import urllib.request as ur; getattr(ur, "urlopen")(url)',
            'from requests import Session as S; session = S(); session.post(url)',
            'from httpx import Client as C; client = C(); client.request(method, url)',
            'from requests import Session; session = Session(); session.delete(url)',
            'from httpx import Client; client = Client(); client.put(url)',
            'from subprocess import (run as invoke)\ninvoke(["git", "push"])',
            'from requests import (request as req)\nreq(method, url)',
            'import importlib as il\nil.import_module("subprocess").run(["git", "push"])',
            'import importlib as il\nil.import_module("requests").post(url)',
            'import subprocess\nsp = subprocess\nsp.run(["git", "push"])',
            'import requests\nrq = requests\nrq.post(url)',
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(VALIDATOR._contains_mutation(command))
                model = self.workflow(jobs={"build": {"steps": [{"run": command}]}})
                self.reject(model)

        for command in (
            'requests.request("GET", "https://api.github.com/repos/example/repo")',
            'httpx.request("HEAD", "https://api.github.com/repos/example/repo")',
            (
                'urllib.request.urlopen(urllib.request.Request('
                '"https://api.github.com/repos/example/repo", method="GET"))'
            ),
            'requests.get("https://api.github.com/repos/example/repo")',
            'requests.Session().get(url)',
            'httpx.Client().get(url)',
            'session = requests.Session(); session.request("GET", url)',
            'from requests import Session as S; session = S(); session.request("HEAD", url)',
            'u = urllib.request.urlopen; u(urllib.request.Request(url, method="GET"))',
            'from urllib.request import urlopen as open_url; open_url(urllib.request.Request(url, method="HEAD"))',
            'getattr(urllib.request, "urlopen")(urllib.request.Request(url, method="GET"))',
            '__import__("urllib.request").request.urlopen(__import__("urllib.request").request.Request(url, method="GET"))',
            'import urllib.request as ur; getattr(ur, "urlopen")(ur.Request(url, method="HEAD"))',
            'from requests import Session; session = Session(); session.request("GET", url)',
            'from httpx import Client; client = Client(); client.request("OPTIONS", url)',
            'from subprocess import (run as invoke)\ninvoke(["git", "status"])',
            'import importlib as il\nil.import_module("subprocess").run(["git", "status"])',
            'import subprocess\nsp = subprocess\nsp.run(["git", "status"])',
        ):
            with self.subTest(allow_command=command):
                self.assertFalse(VALIDATOR._contains_mutation(command))
                model = self.workflow(jobs={"build": {"steps": [{"run": command}]}})
                VALIDATOR.validate_workflow(self.root / "fixture.yml", model)

    def test_dynamic_python_process_and_shell_calls_are_rejected(self) -> None:
        """Reject unresolved subprocess/shell command graphs."""

        commands = (
            'subprocess.run(["git", os.environ["GIT_VERB"]])',
            'argv = ["git"]; argv += ["push"]; subprocess.run(argv)',
            'argv = ["git"]; argv.extend([verb]); subprocess.run(argv)',
            'subprocess.run(command)',
            'subprocess.run(command, shell=True)',
            'os.system(command)',
            'os.popen(command)',
            'os.system("git " + verb)',
            'popen = os.popen; popen("git push")',
            'from subprocess import run as invoke; invoke(command)',
            'getattr(os, "system")("git push")',
            'os.fork()',
            'os.forkpty()',
            '__import__("os").fork()',
            'importlib.import_module("os").fork()',
            'subprocess.run(args=["git", "push"])',
            'subprocess.run(args=["git", "status"], **kwargs)',
            'os.system(command="git push")',
            'os.execl("/usr/bin/git", "git", "push")',
            'os.execv("/usr/bin/git", ["git", "push"])',
            'os.spawnl(os.P_WAIT, "/usr/bin/git", "git", "push")',
            'os.execv("/usr/bin/flock", ["flock", "/tmp/lock", "git", "push"])',
            'os.spawnv(os.P_WAIT, "/usr/bin/parallel", ["parallel", "--jobs", "2", "git", "push", ":::", "x"])',
            'subprocess.run(["/tmp/unreviewed.sh"])',
            'subprocess.run(args=["tools/unreviewed.py"])',
            'subprocess.Popen(["bash", "tools/unreviewed.sh"])',
            'subprocess.run(["bash", "-c", "git push"])',
            'subprocess.run(["python3", "-c", "subprocess.run([\'git\', \'push\'])"])',
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(VALIDATOR._contains_mutation(command))
                model = self.workflow(jobs={"build": {"steps": [{"run": command}]}})
                self.reject(model)

        for command in (
            'subprocess.run(["git", "status"])',
            'subprocess.check_call(["git", "log", "--oneline"])',
            'os.system("git status")',
            'subprocess.run(["echo", "git push"])',
            'os.execle("/usr/bin/git", "git", "status", {})',
            'os.spawnle(os.P_WAIT, "/usr/bin/git", "git", "status", {})',
            'os.execv("/usr/bin/flock", ["flock", "/tmp/lock", "echo", "git", "push"])',
            'os.spawnv(os.P_WAIT, "/usr/bin/parallel", ["parallel", "--jobs", "2", "echo", "git", "push", ":::", "x"])',
            'os.system(command="git status")',
        ):
            with self.subTest(allow_command=command):
                self.assertFalse(VALIDATOR._contains_mutation(command))
                model = self.workflow(jobs={"build": {"steps": [{"run": command}]}})
                VALIDATOR.validate_workflow(self.root / "fixture.yml", model)

    def test_shell_data_comments_and_heredocs_are_not_commands(self) -> None:
        """Do not classify prose/data as an executed mutation command.

        The source gate still fails closed for command substitutions and real
        control-flow invocations, but shell quoting, comments, and heredoc
        bodies must not let raw ``gh``/HTTP/Python text create a false block.
        """

        safe_commands = (
            "echo 'gh api --method POST https://api.github.com/x'",
            "echo gh api --method POST https://api.github.com/x",
            'printf "%s\\n" "curl -X POST https://api.github.com/x"',
            "# gh api --method POST https://api.github.com/x",
            "gh --version # gh api --method POST https://api.github.com/x",
            "curl -X GET https://api.github.com/x # curl -X POST https://api.github.com/x",
            "wget --method=GET https://example.test # wget --method POST https://example.test",
            "cat <<'EOF'\ngh api --method POST https://api.github.com/x\nEOF",
            "cat <<EOF\ncurl -X POST https://api.github.com/x\nEOF",
            "cat <<'EOF'\n# git push\nEOF",
            (
                "python3 - <<'PY'\n"
                "print(\"requests.post('https://api.github.com/x')\")\n"
                "PY"
            ),
            'print("subprocess.run([\\"git\\", \\"push\\"])" )',
            '# subprocess.run(["git", "push"])',
            'echo "g() { git push; }"',
            'echo "function g { git status; }"',
            'echo "export GIT_CONFIG_COUNT=1"',
            'if [[ "$x" == "git push" ]]; then echo ok; fi',
            'while [ "$x" = "git push" ]; do echo ok; done',
            'case "$x" in git) echo ok;; esac',
            'test "$x" = "git push"',
            'printf "git\\n push origin main\\n"',
            'printf "git\n push origin main\n"',
            'echo python3 <<EOF\nrequests.post("https://api.github.com/x")\nEOF',
            'echo "$(printf git)"',
        )
        for command in safe_commands:
            with self.subTest(safe_command=command):
                self.assertFalse(VALIDATOR._contains_mutation(command))
                model = self.workflow(jobs={"build": {"steps": [{"run": command}]}})
                VALIDATOR.validate_workflow(self.root / "fixture.yml", model)

        for command in (
            "POST https://api.github.com/x",
            'echo "$(git push)"',
            'if git push origin main; then :; fi',
            'while git push origin main; do :; done',
            'cat <<EOF\n$(git push origin main)\nEOF',
            'cat <<EOF\n$GIT_COMMAND\nEOF',
        ):
            with self.subTest(actual_command=command):
                self.assertTrue(VALIDATOR._contains_mutation(command))
                model = self.workflow(jobs={"build": {"steps": [{"run": command}]}})
                self.reject(model)

    def test_tokenized_read_only_git_and_python_calls_remain_allowed(self) -> None:
        commands = (
            "/usr/bin/git -C . fetch --no-tags origin main",
            "GIT.EXE --git-dir /tmp/repo STATUS --short",
            "subprocess.run(['/usr/bin/git', '--git-dir', '/tmp/repo', 'status'])",
            "subprocess.check_call(['git', 'log', '--oneline'])",
            "os.system('git log --oneline')",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertFalse(VALIDATOR._contains_mutation(command))

        # Quote-discarding in the shell lexer must not turn ordinary output
        # data that happens to contain ``prefix=...`` into a root assignment.
        for command in (
            'echo "prefix=/tmp/evil"',
            'printf "%s" "validation_root=/tmp/evil"',
        ):
            with self.subTest(data_command=command):
                self.assertFalse(VALIDATOR._contains_mutation(command))
                model = self.workflow(jobs={"build": {"steps": [{"run": command}]}})
                VALIDATOR.validate_workflow(self.root / "fixture.yml", model)

    def test_required_gate_commands_must_not_be_comments_or_echo_arguments(self) -> None:
        source = (ROOT / ".github/workflows/governance-integrity.yml").read_text(
            encoding="utf-8"
        )
        model = VALIDATOR.parse_yaml_strict(source, source="governance-integrity.yml")
        run = "\n".join(
            [
                "# python3 tools/validate_governance_integrity.py",
                "# python3 tools/validate_repository.py",
                "# python3 tools/validate_project_truth.py",
                "# cargo fmt --all --check",
                "# cargo check --workspace --all-targets --locked",
                "# cargo clippy --workspace --all-targets --locked -- -D warnings",
                "# cargo test --workspace --all-targets --locked",
            ]
        )
        model["jobs"]["governance_integrity"]["steps"] = [{"run": run}]
        self.reject(model, name="governance-integrity.yml")
        model["jobs"]["governance_integrity"]["steps"] = [
            {"run": "echo python3 tools/validate_governance_integrity.py"}
        ]
        self.reject(model, name="governance-integrity.yml")
        model["jobs"]["governance_integrity"]["steps"] = [
            {
                "if": "always()",
                "name": "Collect diagnostic output",
                "run": "python3 tools/validate_governance_integrity.py",
            }
        ]
        self.reject(model, name="governance-integrity.yml")

    def test_required_gate_shell_wrapper_handles_long_command_tokens(self) -> None:
        command = "cargo clippy --workspace --all-targets --locked -- -D warnings"
        wrapped = "bash -c '" + command + "'"
        self.assertTrue(VALIDATOR._has_command_invocation([wrapped], command))
        self.assertFalse(
            VALIDATOR._has_command_invocation(["echo '" + command + "'"], command)
        )

    def test_read_only_git_commands_remain_allowed(self) -> None:
        model = self.workflow(
            jobs={"build": {"steps": [{"run": "git -C . fetch --no-tags origin main"}]}}
        )
        VALIDATOR.validate_workflow(self.root / "fixture.yml", model)

    def test_local_reusable_workflow_is_path_checked(self) -> None:
        workflows = self.root / ".github/workflows"
        workflows.mkdir(parents=True)
        local = workflows / "safe.yml"
        local.write_text(
            "name: safe\n"
            "on: {workflow_call: {}}\n"
            "permissions: {contents: read}\n"
            "jobs: {safe: {steps: [{run: echo ok}]}}\n",
            encoding="utf-8",
        )
        model = self.workflow(
            jobs={"call": {"uses": "./.github/workflows/safe.yml"}}
        )
        # The reference is accepted only after lexical/path validation.  The
        # caller's job still has no executable steps because it is reusable.
        VALIDATOR.validate_workflow(self.root / "fixture.yml", model)
        self.reject(
            self.workflow(jobs={"call": {"uses": "./.github/workflows/../evil.yml"}})
        )
        for unsafe in (
            "./.github/workflows//safe.yml",
            "./.github/workflows/./safe.yml",
            "./.github/workflows/safe.yml/",
        ):
            with self.subTest(unsafe=unsafe):
                self.reject(self.workflow(jobs={"call": {"uses": unsafe}}))

    def test_remote_reusable_workflow_reference_has_exact_path_shape(self) -> None:
        valid = f"owner/repository/.github/workflows/gate.yml@{self.SHA}"
        VALIDATOR._validate_uses(
            valid,
            workflow_path=self.root / "fixture.yml",
            reusable=True,
            location="job call",
        )
        for value in (
            f"owner/repository/.github/workflows/nested/gate.yml@{self.SHA}",
            f"owner/repository/.github/workflows/gate.yml/extra@{self.SHA}",
        ):
            with self.subTest(value=value), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                VALIDATOR._validate_uses(
                    value,
                    workflow_path=self.root / "fixture.yml",
                    reusable=True,
                    location="job call",
                )

    def test_local_composite_action_is_followed_for_mutations(self) -> None:
        action = self.root / ".github/actions/local"
        action.mkdir(parents=True)
        (action / "action.yml").write_text(
            "name: local\n"
            "runs:\n"
            "  using: composite\n"
            "  steps:\n"
            "    - run: git -C . push origin main\n",
            encoding="utf-8",
        )
        model = self.workflow(
            jobs={
                "build": {
                    "steps": [
                        {"uses": "./.github/actions/local"},
                    ]
                }
            }
        )
        self.reject(model)

    def test_governance_workflow_is_unconditional_and_runs_all_gates(self) -> None:
        source = (ROOT / ".github/workflows/governance-integrity.yml").read_text(
            encoding="utf-8"
        )
        model = VALIDATOR.parse_yaml_strict(source, source="governance-integrity.yml")
        path = self.root / "governance-integrity.yml"
        VALIDATOR.validate_workflow(path, model)

        missing = {
            **model,
            "jobs": {
                "governance_integrity": {
                    **model["jobs"]["governance_integrity"],
                    "steps": [{"run": "true"}],
                }
            },
        }
        self.reject(missing, name="governance-integrity.yml")

        target = {**model, "on": ["pull_request_target"]}
        self.reject(target, name="governance-integrity.yml")

        write = {**model, "permissions": {"contents": "write"}}
        self.reject(write, name="governance-integrity.yml")

    def test_root_probe_is_a_hard_failure(self) -> None:
        probe = self.root / "__probe__"
        probe.write_text("residue", encoding="utf-8")
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            VALIDATOR.assert_source_inventory()

    def test_root_inventory_rejects_unregistered_files(self) -> None:
        for name in VALIDATOR.EXPECTED_ROOT_FILES:
            (self.root / name).write_text("fixture", encoding="utf-8")
        (self.root / "unexpected.txt").write_text("residue", encoding="utf-8")
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            VALIDATOR.assert_source_inventory()

    def test_codeowners_required_paths_and_identities_are_fail_closed(self) -> None:
        (self.root / ".github").mkdir()
        (self.root / "manifests").mkdir()
        (self.root / ".github/CODEOWNERS").write_text(
            "* @Tomasrgbsf @ProfHepta\n", encoding="utf-8"
        )
        manifest = json.loads(
            (ROOT / "manifests/repository-governance.v1.json").read_text(
                encoding="utf-8"
            )
        )
        (self.root / "manifests/repository-governance.v1.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            VALIDATOR._validate_codeowners_source()

    def test_manifest_contract_parity_is_fail_closed(self) -> None:
        manifests = self.root / "manifests"
        manifests.mkdir()
        manifest = json.loads(
            (ROOT / "manifests/repository-governance.v1.json").read_text(
                encoding="utf-8"
            )
        )
        contract = json.loads(
            (ROOT / "contracts/repository-governance.v1.json").read_text(
                encoding="utf-8"
            )
        )
        contract["dynamic_acceptance_required"] = contract[
            "dynamic_acceptance_required"
        ][:-1]
        (manifests / "repository-governance.v1.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        old_root = VALIDATOR.ROOT
        VALIDATOR.ROOT = self.root
        try:
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                VALIDATOR._validate_manifest_parity(contract)
        finally:
            VALIDATOR.ROOT = old_root

    def test_manifest_policy_sections_must_match_contract(self) -> None:
        manifests = self.root / "manifests"
        manifests.mkdir()
        manifest = json.loads(
            (ROOT / "manifests/repository-governance.v1.json").read_text(
                encoding="utf-8"
            )
        )
        contract = json.loads(
            (ROOT / "contracts/repository-governance.v1.json").read_text(
                encoding="utf-8"
            )
        )
        (manifests / "repository-governance.v1.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        old_root = VALIDATOR.ROOT
        VALIDATOR.ROOT = self.root
        try:
            for section in ("actions", "release"):
                mutated = json.loads(json.dumps(contract))
                key = next(iter(mutated[section]))
                value = mutated[section][key]
                mutated[section][key] = not value if isinstance(value, bool) else "mutated"
                with self.subTest(section=section), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    VALIDATOR._validate_manifest_parity(mutated)
            mutated = json.loads(json.dumps(contract))
            mutated["main_branch"]["linear_history_required"] = False
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                VALIDATOR._validate_manifest_parity(mutated)
        finally:
            VALIDATOR.ROOT = old_root

    def test_contract_policy_booleans_require_json_boolean_types(self) -> None:
        contract = json.loads(
            (ROOT / "contracts/repository-governance.v1.json").read_text(
                encoding="utf-8"
            )
        )
        contract["main_branch"]["pull_request_required"] = 1
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            VALIDATOR._validate_contract(contract)

    def test_manifest_main_branch_rejects_extra_policy_keys(self) -> None:
        manifests = self.root / "manifests"
        manifests.mkdir()
        manifest = json.loads(
            (ROOT / "manifests/repository-governance.v1.json").read_text(
                encoding="utf-8"
            )
        )
        manifest["main_branch"]["unexpected_bypass"] = True
        (manifests / "repository-governance.v1.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        contract = json.loads(
            (ROOT / "contracts/repository-governance.v1.json").read_text(
                encoding="utf-8"
            )
        )
        old_root = VALIDATOR.ROOT
        VALIDATOR.ROOT = self.root
        try:
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                VALIDATOR._validate_manifest_parity(contract)
        finally:
            VALIDATOR.ROOT = old_root

    def test_workflow_inventory_rejects_nested_or_unregistered_workflows(self) -> None:
        workflows = self.root / ".github/workflows"
        workflows.mkdir(parents=True)
        workflow = workflows / "only.yml"
        workflow.write_text("name: only\n", encoding="utf-8")
        old_root = VALIDATOR.ROOT
        old_workflow_root = VALIDATOR.WORKFLOW_ROOT
        old_registry = VALIDATOR.EXPECTED_REQUIRED_WORKFLOWS
        VALIDATOR.ROOT = self.root
        VALIDATOR.WORKFLOW_ROOT = workflows
        VALIDATOR.EXPECTED_REQUIRED_WORKFLOWS = (".github/workflows/only.yml",)
        try:
            self.assertEqual(VALIDATOR._workflow_inventory(), [workflow])
            nested = workflows / "nested"
            nested.mkdir()
            (nested / "extra.yml").write_text("name: extra\n", encoding="utf-8")
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                VALIDATOR._workflow_inventory()
        finally:
            VALIDATOR.ROOT = old_root
            VALIDATOR.WORKFLOW_ROOT = old_workflow_root
            VALIDATOR.EXPECTED_REQUIRED_WORKFLOWS = old_registry


class WrapperAndScriptGraphTests(unittest.TestCase):
    """Exercise command-graph wrappers which can hide a second executable."""

    def test_process_substitution_command_graphs_are_scanned(self) -> None:
        """Audit Bash ``<(...)``/``>(...)`` payloads independently.

        Process substitutions are asynchronous command graphs.  They must not
        become an accidental blind spot merely because the outer command is a
        read-only consumer such as ``cat``/``diff``.  The committed D2I
        workflows use the safe ``find``/``git show`` forms below, which remain
        accepted after the explicit raw-lexer pass.
        """

        rejected = (
            "cat <(git push origin main)",
            "cat >(git update-ref refs/heads/main HEAD)",
            "cat <(bash -c 'git push origin main')",
            "cat <(echo \"$(git push origin main)\")",
            "cat <(git${IFS}push)",
            "cat <(xargs git push)",
            "cat >(curl -X POST https://example.test/api)",
            "cat <(gh api --method POST https://api.github.com/repos/x)",
            "cat <(git push",
            "cat >(echo ok",
        )
        for command in rejected:
            with self.subTest(rejected_command=command):
                self.assertTrue(VALIDATOR._contains_mutation(command))

        allowed = (
            "cat <(git status --short)",
            "diff <(git show -s --format=%P HEAD) <(git rev-parse HEAD)",
            "mapfile -t files < <(find -P \"$source_root\" -type f -print0)",
            "cat <(printf '%s\\n' ok)",
            "echo \"<(git push origin main)\"",
            "echo '<(git push origin main)'",
            "cat <(git status) # <(git push origin main)",
            "cat <<'EOF'\n<(git push origin main)\nEOF",
        )
        for command in allowed:
            with self.subTest(allowed_command=command):
                self.assertFalse(VALIDATOR._contains_mutation(command))

    def test_unquoted_heredoc_special_parameters_fail_closed(self) -> None:
        """Do not let special/positional parameters hide heredoc commands."""

        for parameter in ("$@", "$*", "$?", "$0", "$1", "$$", "$#", "$!", "$-"):
            command = f"cat <<EOF\n{parameter}\nEOF"
            with self.subTest(parameter=parameter):
                self.assertTrue(VALIDATOR._contains_mutation(command))

        # Quoted delimiters suppress all heredoc expansion, so the same bytes
        # are inert data and must remain an allow case.
        for parameter in ("$@", "$?", "$1", "$$"):
            command = f"cat <<'EOF'\n{parameter}\nEOF"
            with self.subTest(quoted_parameter=parameter):
                self.assertFalse(VALIDATOR._contains_mutation(command))

        # Heredoc expansion removes backslash-newline pairs before evaluating
        # ``$(``, backticks, or variable names.  Keep the physical split from
        # becoming a lexical blind spot.
        for body in (
            "$\\\n(git push origin main)",
            "`\\\ngit push origin main`",
            "$\\\nGIT_COMMAND",
        ):
            command = f"cat <<EOF\n{body}\nEOF"
            with self.subTest(split_expansion=body):
                self.assertTrue(VALIDATOR._contains_mutation(command))

    def test_nested_wrapper_git_mutations_are_rejected(self) -> None:
        commands = (
            "xargs -n1 git push",
            "printf x | xargs -0 git push",
            "find . -exec git push {} \\;",
            "find . -execdir sh -c 'git push' \\;",
            "find . -delete",
            "setsid git push",
            "flock /tmp/lock git push",
            "flock -c 'git push' /tmp/lock",
            "chroot /tmp/root git push",
            "busybox git push",
            "nsenter -t 1 -m git push",
            "unshare -m git push",
            "systemd-run --unit probe git push",
            "watch -n 1 git push",
            "parallel git push ::: origin main",
            "parallel ::: git push",
            "trap 'git push origin main' EXIT",
            "trap \"$(git push origin main)\" EXIT",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(VALIDATOR._contains_mutation(command))

    def test_wrapper_option_terminators_and_named_coproc_are_rejected(self) -> None:
        """Keep option-value/``--`` forms on the nested command graph."""

        commands = (
            # ``find`` permits an end-of-options marker before the utility.
            "find . -execdir -- git push {} \\;",
            # flock's lock operand may be a path or an already-open fd, and
            # ``-E`` consumes a value before that operand.
            "flock -n /tmp/lock -- git push",
            "flock 9 -- git push",
            "flock -E 1 /tmp/lock git push",
            # chroot options can consume separated values; ``--`` after the
            # NEWROOT belongs to the wrapper, not to the command.
            "chroot --userspec=0:0 /tmp/root -- git push",
            "chroot --userspec 0:0 /tmp/root -- git push",
            # GNU parallel's jobs value must not be mistaken for the command.
            "parallel --jobs 2 git push ::: x",
            "parallel -j 2 git push ::: x",
            "parallel --jobs 2 --halt soon,fail=1 git push ::: x",
            # Bash allows an optional coprocess name.
            "coproc worker git push",
            "coproc worker -- git push",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(VALIDATOR._contains_mutation(command))

        # The same wrapper spellings remain harmless when the nested command
        # is a literal data/probe command rather than Git mutation.
        for command in (
            "find . -execdir -- echo git push {} \\;",
            "flock -n /tmp/lock -- echo git push",
            "flock -E 1 /tmp/lock echo ok",
            "chroot --userspec 0:0 /tmp/root -- echo git push",
            "parallel --jobs 2 echo git push ::: x",
            "coproc worker echo git push",
        ):
            with self.subTest(allow_command=command):
                self.assertFalse(VALIDATOR._contains_mutation(command))

    def test_wrapper_data_forms_remain_allowed(self) -> None:
        commands = (
            "xargs -r sudo apt-get install -y foo",
            "find . -type f -print0",
            "find . -exec echo git push {} \\;",
            "setsid echo ok",
            "flock /tmp/lock echo ok",
            "flock -c 'echo git push' /tmp/lock",
            "busybox echo ok",
            "nsenter -t 1 -m echo ok",
            "unshare -m echo ok",
            "systemd-run --unit probe echo ok",
            "parallel echo git push ::: origin main",
            "trap 'rm -rf /tmp/work' EXIT",
            "trap -p EXIT",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertFalse(VALIDATOR._contains_mutation(command))

    def test_unregistered_script_paths_fail_closed(self) -> None:
        commands = (
            "./unreviewed.sh",
            "bash tools/unreviewed.sh",
            "python3 tools/unreviewed.py",
            'subprocess.run(["/tmp/unreviewed.sh"])',
            'subprocess.run(args=["tools/unreviewed.py"])',
            'subprocess.Popen(["bash", "tools/unreviewed.sh"])',
            "python3 /tmp/runner-owned.py",
            'bash "$RUNNER_TEMP/generated.sh"',
            "$(./unreviewed.sh)",
            "xargs ./unreviewed.sh",
            # A reviewed suffix must not make an unrelated external checkout
            # look trusted. The path gate accepts only exact repository
            # relative forms or explicitly reviewed roots.
            "python3 /tmp/evil/tools/validate_repository.py",
            "python3 /workspace/other/tools/validate_project_truth.py",
            "python3 foo/bar/tools/validate_repository.py",
            "python3 ./foo/tools/validate_repository.py",
            "python3 https://evil.example/tools/validate_repository.py",
            'python3 "$evil/tools/validate_repository.py"',
            'validation_root=/tmp/evil; python3 "$validation_root/tools/validate_repository.py"',
            'prefix=/tmp/evil; "$prefix/sbin/mke2fs" -V',
            'cmd=/tmp/evil/helper; $cmd --version',
            'env validation_root=/tmp/evil python3 "$validation_root/tools/validate_repository.py"',
            'export validation_root=/tmp/evil; python3 "$validation_root/tools/validate_repository.py"',
            # Extensionless dynamic tool paths need the same provenance check
            # as ordinary scripts; a static attacker path must not be missed.
            "/tmp/evil/configure --prefix=/tmp/prefix",
            '"$evil/configure" --prefix=/tmp/prefix',
            '"$RUNNER_TEMP/evil/configure" --prefix=/tmp/prefix',
            '"$RUNNER_TEMP/evil/sbin/mke2fs" -V',
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(VALIDATOR._contains_mutation(command))

    def test_reviewed_script_paths_and_interpreter_options_remain_allowed(self) -> None:
        commands = (
            "tools/run_d1_final_qualification.sh identities",
            "./tools/run_servo_headed_runtime_gate.sh identities",
            "bash --login tools/run_servo_headed_runtime_gate.sh identities",
            "bash --noprofile --norc -c 'printf ok'",
            "python3 tools/validate_repository.py",
            'python3 "$validation_root/tools/validate_repository.py"',
            'python3 "${validation_root}/tools/validate_repository.py"',
            'python3 "$GITHUB_WORKSPACE/tools/validate_repository.py"',
            'python3 "${GITHUB_WORKSPACE}/tools/validate_repository.py"',
            'python3 "$PWD/tools/validate_repository.py"',
            'python3 "${PWD}/tools/validate_repository.py"',
            'python3 "${{ github.workspace }}/tools/validate_repository.py"',
            'bash -c "$PWD/tools/reject_symlink_path.sh"',
            'bash -c "$GITHUB_WORKSPACE/tools/reject_symlink_path.sh"',
            'subprocess.run(["python3", "tools/validate_repository.py"])',
            'subprocess.run(["bash", "tools/run_servo_headed_runtime_gate.sh"])',
            'subprocess.run(["bash", "-c", "echo git push"])',
            '"$GITHUB_WORKSPACE/e2fsprogs-source/configure" --prefix=/tmp/prefix',
            '"${GITHUB_WORKSPACE}/e2fsprogs-source/configure" --prefix=/tmp/prefix',
            '"${{ github.workspace }}/e2fsprogs-source/configure" --prefix=/tmp/prefix',
            '"$prefix/sbin/mke2fs" -V',
            '"${prefix}/sbin/e2fsck" -V',
            "/usr/bin/echo ok",
            "/bin/bash -c 'printf ok'",
            "/usr/bin/git -C . fetch --no-tags origin main",
            "python3 - <<'PY'\nprint('git push')\nPY",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertFalse(VALIDATOR._contains_mutation(command))

    def test_python_bound_and_dynamic_import_aliases_fail_closed(self) -> None:
        """Do not lose process/HTTP effects when callables are rebound."""

        commands = (
            'import subprocess as s; m=s.run; f=m; f(["git", "push"])',
            'f=__import__("subprocess").run; f(["git", "push"])',
            'import importlib as il; f=il.import_module("subprocess").run; f(["git", "push"])',
            'from importlib import import_module as im; f=im("subprocess").run; f(["git", "push"])',
            'import requests as rq; f=rq.post; g=f; g(url)',
            'f=__import__("requests").post; f(url)',
            'from requests import get as g; f=g; f(url, data=x)',
            'from requests import request as r; f=r; f("GET", url, **kwargs)',
            'from httpx import Client as C; c=C(); f=c.get; g=f; g(url, **kwargs)',
            'python3 -c \'import subprocess as s; m=s.run; f=m; f(["git", "push"])\'',
            'python3 -c \'f=__import__("subprocess").run; f(["git", "push"])\'',
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(VALIDATOR._contains_mutation(command))

        for command in (
            'import subprocess as s; m=s.run; f=m; f(["git", "status"])',
            'from importlib import import_module as im; f=im("subprocess").run; f(["git", "status"])',
            'import requests as rq; f=rq.get; g=f; g(url)',
            'f=__import__("requests").get; f(url)',
            'from requests import get as g; f=g; f(url)',
            'from requests import request as r; f=r; f("GET", url)',
            'from httpx import Client as C; c=C(); f=c.get; g=f; g(url)',
            'python3 -c \'import subprocess as s; m=s.run; f=m; f(["git", "status"])\'',
        ):
            with self.subTest(allow_command=command):
                self.assertFalse(VALIDATOR._contains_mutation(command))

    def test_python_process_argv_wrappers_are_scanned_recursively(self) -> None:
        """Static subprocess argv must not hide shell command graphs."""

        commands = (
            'subprocess.run(["flock", "/tmp/lock", "git", "push"])',
            'subprocess.run(["flock", "-E", "1", "/tmp/lock", "--", "git", "push"])',
            'subprocess.run(["parallel", "--jobs", "2", "git", "push", ":::", "x"])',
            'subprocess.run(["find", ".", "-execdir", "--", "git", "push", "{}", ";"])',
            'subprocess.run(["env", "-S", "git push"])',
            'subprocess.run(["timeout", "30", "git", "push"])',
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(VALIDATOR._contains_mutation(command))

        for command in (
            'subprocess.run(["flock", "/tmp/lock", "echo", "git", "push"])',
            'subprocess.run(["parallel", "--jobs", "2", "echo", "git", "push", ":::", "x"])',
            'subprocess.run(["find", ".", "-execdir", "--", "echo", "git", "push", "{}", ";"])',
            'subprocess.run(["env", "FOO=bar", "echo", "git", "push"])',
            'subprocess.run(["timeout", "30", "echo", "git", "push"])',
        ):
            with self.subTest(allow_command=command):
                self.assertFalse(VALIDATOR._contains_mutation(command))


class RealTreeRegressionTests(unittest.TestCase):
    def test_real_tree_governance_gate_passes(self) -> None:
        self.assertEqual(VALIDATOR.main(), 0)


if __name__ == "__main__":
    unittest.main()
