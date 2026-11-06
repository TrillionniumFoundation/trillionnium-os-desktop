#!/usr/bin/env python3
"""Freeze a fresh builder466 compile using the observed direct Rust 1.93 tools."""
import ast
import base64
import difflib
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zlib

BASE = Path('/workspace/scratch/94990735b266/native-recovery-20261105-02')
OLD = BASE / 'typed-ingress-builder466-go5-compile01'
DEST = BASE / 'typed-ingress-builder466-go5-compile02'
EVIDENCE = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence')
OBSERVED = EVIDENCE / 'rust193-tools-recheck-read03/result.json'
FAILED = EVIDENCE / 'typed-ingress-builder466-go5-compile01/result.json'
OLD_REMOTE = '/home/alex/work/pocket4-native-typed-ingress-builder466-go5-compile-01-20261105'
REMOTE = '/home/alex/work/pocket4-native-typed-ingress-builder466-go5-compile-02-20261105'
KEY = 'pocket4-native-typed-ingress-builder466-go5-matching-compile-02-20261105'


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def exact(source, before, after):
    assert source.count(before) == 1, before[:200]
    return source.replace(before, after)


def definitions(source):
    return {node.name: ast.dump(node, include_attributes=False)
            for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)}


def assignment(source, name, replacement):
    nodes = [node for node in ast.parse(source).body
             if isinstance(node, ast.Assign) and len(node.targets) == 1
             and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name]
    assert len(nodes) == 1, name
    return exact(source, ast.get_source_segment(source, nodes[0]), name + ' = ' + repr(replacement))


def diff(before, after, name):
    return ''.join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                                      fromfile='a/' + name, tofile='b/' + name)).encode()


def main():
    assert not DEST.exists()
    old_pins = json.loads((OLD / 'SOURCE_PINS.json').read_bytes())['files']
    for name, row in old_pins.items():
        assert pin((OLD / name).read_bytes()) == row, name
    original = (OLD / 'compile_builder.py').read_bytes()
    assert pin(original) == {'bytes': 66979, 'sha256': 'f219dd4504ad8abe41589eeabd46b595e7f43abdabfeca1a9ffc46c6eb953d82'}
    observed_raw = OBSERVED.read_bytes()
    assert pin(observed_raw) == {'bytes': 31452, 'sha256': '60f543d7a5fc552add6824160794c2c2e8b1a5f908401aab9b176a0a737789fb'}
    observed = json.loads(observed_raw)
    assert observed['state'] == 'PASS_FIXED_TOOL_OBSERVATION_NOT_EXECUTION_APPROVAL'
    assert observed['complete'] and observed['first_error'] is None and not observed['secondary_errors']
    assert observed['owned_resource_gate']['pass'] and not observed['commands_executed']
    assert observed['changed_tools'] == [{'changed_admission_fields': ['sha256', 'bytes'],
        'original_object_metadata_equal': False, 'path': '/home/alex/.cargo/bin/rustup'}]
    for row in observed['tools'] + [observed['repository_toolchain']]:
        assert row['error'] is None and row['content_read'] and not row['resolution_changed']
        assert row['held_before'] == row['held_after'] == row['resolved_named_after']
        assert row['requested_named_before'] == row['requested_named_after']
        assert row['requested_link_text_before'] == row['requested_link_text_after']
        if row['requested_path'] != '/home/alex/.cargo/bin/rustup':
            assert row['compilation_admission_fields_equal'] and row['original_object_metadata_equal']
    failed_raw = FAILED.read_bytes()
    assert pin(failed_raw) == {'bytes': 7681, 'sha256': '44da2c2f9f2df67bc1c32fe25f003442378b19e341da4add8869b77488e7fee3'}
    failed = json.loads(failed_raw)
    assert failed['state'] == 'FAIL' and failed['commands'] == []
    assert failed['error'] == "RuntimeError('observed tool changed before compilation: /home/alex/.cargo/bin/rustup')"
    assert observed['actual_build_failure'] == pin(failed_raw)
    assert not failed['cleanup']['errors'] and not failed['cleanup']['remaining'] and not failed['cleanup']['forced_cleanup']

    function_body = (BASE / 'builder466-direct-toolchain-body.py').read_text()
    assert list(definitions(function_body)) == ['toolchain']
    source = original.decode()
    source = exact(source, 'ROOT = Path(' + repr(OLD_REMOTE) + ')', 'ROOT = Path(' + repr(REMOTE) + ')')
    source = exact(source, "RUSTUP = Path('/home/alex/.cargo/bin/rustup')\nRUSTUP_HOME = Path('/home/alex/.rustup')",
        "RUST_SYSROOT = Path('/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu')")
    source = assignment(source, 'OBSERVATION', pin(observed_raw)['sha256'])
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'toolchain')
    source = exact(source, ast.get_source_segment(source, node), function_body.rstrip())
    source = exact(source,
        "        env={'PATH':'/usr/bin:/bin','HOME':'/home/alex','CARGO_HOME':str(CARGO_HOME),'RUSTUP_HOME':str(RUSTUP_HOME),\n"
        "             'RUSTUP_SKIP_UPDATE_CHECK':'1','RUSTUP_TOOLCHAIN':TOOLCHAIN,'CARGO_NET_OFFLINE':'true','LC_ALL':'C','LANG':'C',",
        "        env={'PATH':'/usr/bin:/bin','HOME':'/home/alex','CARGO_HOME':str(CARGO_HOME),\n"
        "             'RUSTC':str(RUST_SYSROOT/'bin/rustc'),'RUSTDOC':str(RUST_SYSROOT/'bin/rustdoc'),\n"
        "             'CARGO_NET_OFFLINE':'true','LC_ALL':'C','LANG':'C',")
    source = exact(source,
        "        env.update({'PATH':str(tools['cargo'].parent)+':/usr/bin:/bin','RUSTC':str(tools['rustc']),\n"
        "                    'RUSTC_WRAPPER':'','RUSTC_WORKSPACE_WRAPPER':'','RUSTFLAGS':'','CARGO_ENCODED_RUSTFLAGS':'',",
        "        env.update({'PATH':str(tools['cargo'].parent)+':/usr/bin:/bin','RUSTC':str(tools['rustc']),\n"
        "                    'RUSTDOC':str(tools['rustdoc']),'RUSTDOCFLAGS':'','CARGO_ENCODED_RUSTDOCFLAGS':'',\n"
        "                    'RUSTC_WRAPPER':'','RUSTC_WORKSPACE_WRAPPER':'','RUSTFLAGS':'','CARGO_ENCODED_RUSTFLAGS':'',")
    source = exact(source, "        config_paths=[CARGO_HOME/'config',CARGO_HOME/'config.toml']",
        "        require('/home/alex/.cargo/bin' not in env['PATH'].split(':') and\n"
        "                all(shutil.which(name,path=env['PATH'])==str(tools[name]) for name in ['cargo','rustc','rustdoc']) and\n"
        "                not any(name.startswith('RUSTUP') for name in env) and\n"
        "                all(name not in env for name in ('LD_PRELOAD','LD_LIBRARY_PATH','RUSTC_BOOTSTRAP')),\n"
        "                'fixed direct compiler tools are shadowed or proxy environment was reintroduced')\n"
        "        config_paths=[CARGO_HOME/'config',CARGO_HOME/'config.toml']")
    old_defs, new_defs = definitions(original.decode()), definitions(source)
    assert set(old_defs) == set(new_defs)
    assert sorted(n for n in old_defs if old_defs[n] != new_defs[n]) == ['execute', 'toolchain']
    assert not any(isinstance(n, ast.Name) and n.id in ('RUSTUP', 'RUSTUP_HOME') for n in ast.walk(ast.parse(source)))
    assert not any(isinstance(n, ast.Constant) and n.value in ('resolve-cargo', 'resolve-rustc') for n in ast.walk(ast.parse(source)))

    old_packet = json.loads((OLD / 'verified-source-packet.json').read_bytes())
    old_stage = (OLD / 'stage.py').read_text()
    expected_node = next(n for n in ast.parse(old_stage).body if isinstance(n, ast.Assign) and n.targets[0].id == 'EXPECTED')
    old_expected = ast.literal_eval(expected_node.value)
    assert set(old_packet) == set(old_expected) and len(old_packet) == 13
    for name, content in old_packet.items():
        assert pin(content.encode()) == old_expected[name]
    data = {name: content.encode() for name, content in old_packet.items()
            if name not in ('compile_builder.py', 'rust193-tools-read02-result.json')}
    unchanged_packets = {name: pin(raw) for name, raw in data.items()}
    data.update({'compile_builder.py': source.encode(),
                 'rust193-tools-recheck-read03-result.json': observed_raw,
                 'prior-compile01-failure.json': failed_raw})
    assert len(data) == 14
    assert data['compiled-parent465-manifest.json'] == (OLD / 'compiled-parent465-manifest.json').read_bytes()
    assert data['expected-builder466-manifest.json'] == (OLD / 'expected-builder466-manifest.json').read_bytes()
    stage = old_stage.replace(OLD_REMOTE, REMOTE)
    stage = assignment(stage, 'EXPECTED', {name: pin(raw) for name, raw in data.items()})
    assert definitions(stage) == definitions(old_stage)
    packet = json.dumps({name: raw.decode() for name, raw in data.items()}, ensure_ascii=True, sort_keys=True)
    uncompressed = (stage + '\nPACKET=json.loads(' + repr(packet) + ')\nmain(PACKET)\n').encode()
    ast.parse(uncompressed)
    compressed = gzip.compress(uncompressed, compresslevel=9, mtime=0)
    envelope = (json.dumps({'schema': 1, 'encoding': 'gzip+base64', 'compressed': pin(compressed),
                           'uncompressed': pin(uncompressed), 'payload': base64.b64encode(compressed).decode()},
                          sort_keys=True, separators=(',', ':')) + '\n').encode()
    assert len(envelope) < 1024 * 1024
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    restored = decoder.decompress(compressed, len(uncompressed) + 1)
    assert restored == uncompressed and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail
    old_boundary = (OLD / 'transport-boundary.py').read_text()
    boundary = old_boundary
    for name, raw in [('ENVELOPE', envelope), ('COMPRESSED', compressed), ('UNCOMPRESSED', uncompressed)]:
        boundary = assignment(boundary, name, pin(raw))
    normalized = boundary
    for node in ast.parse(old_boundary).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('ENVELOPE', 'COMPRESSED', 'UNCOMPRESSED'):
            normalized = assignment(normalized, node.targets[0].id, ast.literal_eval(node.value))
    assert ast.dump(ast.parse(normalized), include_attributes=False) == ast.dump(ast.parse(old_boundary), include_attributes=False)
    request = json.loads((OLD / 'exact-request.json').read_bytes())
    request['args'] = ['-I', '-B', '-c', boundary]
    request['stdin'] = envelope.decode()
    request['idempotency_key'] = KEY
    assert request['host'] == 'pocket4' and request['executable'] == '/usr/bin/python3'
    assert request['cpu_quota_percent'] == 100 and request['memory_max_bytes'] == 1073741824 and request['timeout_seconds'] == 600
    assert 'env' not in request
    artifacts = dict(data)
    artifacts.update({'stage.py': stage.encode(), 'transport-boundary.py': boundary.encode(),
                      'verified-source-packet.json': (packet + '\n').encode(),
                      'exact-request.json': (json.dumps(request, indent=2) + '\n').encode(),
                      'compiler01-to02.patch': diff(original, source.encode(), 'compile_builder.py'),
                      'stage01-to02.patch': diff(old_stage.encode(), stage.encode(), 'stage.py'),
                      'transport01-to02.patch': diff(old_boundary.encode(), boundary.encode(), 'transport-boundary.py'),
                      'direct-toolchain-function.py': function_body.encode(),
                      'make_request.py': Path(__file__).read_bytes()})
    checks = {'schema': 1, 'state': 'FROZEN_DIRECT_RUST193_BUILD_REQUEST_NOT_SUBMITTED',
        'prior_failed_compile': pin(failed_raw), 'actual_tool_reobservation': pin(observed_raw),
        'old_compile01_source_and_root_preserved': True,
        'actual_source_file_count': 465, 'revision_name': '466-go5',
        'source_manifest_unchanged_from_compile01': pin(data['expected-builder466-manifest.json']),
        'changed_existing_functions': ['execute', 'toolchain'],
        'unchanged_functions': sorted(n for n in old_defs if old_defs[n] == new_defs[n]),
        'stage_main_AST_unchanged': True, 'transport_AST_unchanged_except_three_pins': True,
        'unchanged_authority_packets': unchanged_packets, 'packet_files': len(data),
        'uncompressed_stage': pin(uncompressed), 'compressed_stage': pin(compressed),
        'stdin_envelope': pin(envelope), 'controller': pin(source.encode()),
        'direct_compiler_paths': {name: '/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu/bin/' + name
                                  for name in ['cargo', 'rustc', 'rustdoc']},
        'rustup_proxy_removed_from_execution_and_compilation_closure': True,
        'rustup_changed_binary_approved_for_execution': False,
        'RUSTDOC_absolute_and_observed_with_sysroot_closure_at_compile_admission': True,
        'RUSTDOC_old_SHA_prequalified': False, 'doctests_requested': False,
        'fresh_environment_no_RUSTUP_or_loader_override_inheritance': True,
        'expected_registered': 199, 'expected_targeted_this_attempt': 9,
        'image_and_ART_targeted_tests_rerun': False, 'local_Rust_execution': False,
        'decoded_stage_executed_locally': False, 'remote_request_submitted': False,
        'runtime_authorization_enabled': False, 'Main_actions': 0}
    artifacts['LOCAL_SOURCE_CHECKS.json'] = (json.dumps(checks, indent=2) + '\n').encode()
    artifacts['README.md'] = b'''# Builder466 compile02: direct installed Rust 1.93 tools

The source revision and its complete 465-file manifest are unchanged from compile01: one ASCII byte in the normal Soong Go heap patch selects 5GiB, and all 464 other files retain their actual builder465 bytes. The old compile01 failed before any command because the rustup proxy's content changed. Its failure and partially created private source copy remain untouched.

The complete read03 observation proves that all eleven directly used tool paths still have their original content, sizes and resolved targets. Rustup alone changed. This attempt does not approve or execute that changed binary: it removes the two rustup which commands and directly selects the already observed installed Rust 1.93 cargo and rustc. The fresh environment has no inherited RUSTUP, wrapper or loader overrides. PATH excludes the user proxy directory, and the explicit sysroot cargo/rustc/rustdoc resolution is checked before Cargo runs. RUSTC and RUSTDOC are absolute. The exact rustdoc file and its runtime libraries are observed alongside the existing sysroot closure in this attempt and rechecked afterward; no old rustdoc SHA or doctest execution is claimed. The Cargo test command remains bin-only and no-run, followed by the existing direct test executable controls.

All offline/locked selected-package, archive/source, compiler-input, ELF, source/config/tool, exact independent libtest-result, owned-child and resource gates remain. This attempt compiles the complete builder and test executable, lists 199 registrations, and runs the same seven projection/CLI plus two typed-lock tests. The historical parent 26 tests and image/ART tests are not relabeled as new executions.

The compile budget remains one CPU, 1GiB and 600 seconds; swap.max is observed rather than newly constrained. It does not materialize framework source, run Soong, install or enable anything, or act on Main. A separate normal framework build must bind this attempt's actual successful ELF and the independent work-preparation receipt and meet its own fresh resource and input gates.
'''
    DEST.mkdir(mode=0o700)
    for name, raw in artifacts.items():
        path = DEST / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(raw)
    plan = subprocess.run([sys.executable, '-I', '-B', str(DEST / 'compile_builder.py')], capture_output=True, check=True)
    assert plan.stderr == b'' and json.loads(plan.stdout)['mode'] == 'PLAN'
    assert not Path(REMOTE).exists()
    with (DEST / 'PLAN.json').open('xb') as stream:
        stream.write(plan.stdout)
    pins = {str(p.relative_to(DEST)): pin(p.read_bytes()) for p in sorted(DEST.rglob('*')) if p.is_file()}
    with (DEST / 'SOURCE_PINS.json').open('xb') as stream:
        stream.write((json.dumps({'schema': 1, 'files': pins}, indent=2, sort_keys=True) + '\n').encode())
    for path in DEST.rglob('*'):
        if path.is_file():
            path.chmod(0o444)
    print(json.dumps({'root': str(DEST), 'files': len(pins) + 1, 'controller': pin(source.encode()),
        'manifest': pin(data['expected-builder466-manifest.json']),
        'request': pin((DEST / 'exact-request.json').read_bytes()), 'stdin': pin(envelope),
        'packet_files': len(data), 'patch': pin(artifacts['compiler01-to02.patch']),
        'PLAN_exit_code': plan.returncode, 'remote_submitted': False}))


if __name__ == '__main__':
    main()
