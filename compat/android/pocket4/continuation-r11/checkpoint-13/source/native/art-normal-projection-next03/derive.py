#!/usr/bin/env python3
"""Prepare an isolated normal-updater ART build route. No build is run."""
import difflib
import hashlib
import json
from pathlib import Path

WORK = Path(__file__).resolve().parent
OUT = WORK / 'art-normal-projection-next03'
PAIR = WORK / 'paired-generation-v2-next01'
PREFORK = WORK / 'art-prefork-quiesce-next02'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def exact(text, old, new):
    assert text.count(old) == 1, old[:120]
    return text.replace(old, new)


def put(name, data):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        assert stream.write(data) == len(data)


def main():
    OUT.mkdir(mode=0o700)
    parent_bytes = (PAIR / 'expected-builder451-source-manifest.json').read_bytes()
    assert sha(parent_bytes) == 'a5052accd9bb36231a3c59271f8bc35e464e5cf14d702787735feed0d86b7a13'
    parent = json.loads(parent_bytes)
    old_main = (PAIR / 'delta/updater/tools/droidloom-update/src/main.rs').read_bytes()
    old_android = (WORK / 'blueprint-streaming-r1/builder-delta/tools/droidloom-update/src/android.rs').read_bytes()
    for relative, data in [('main.rs', old_main), ('android.rs', old_android)]:
        assert sha(data) == parent['tools/droidloom-update/src/' + relative]['sha256']
        put('preimage/tools/droidloom-update/src/' + relative, data)
    current = PAIR / 'references/current/platform'
    files = {
        'art/runtime/runtime.cc': PREFORK / 'delta/platform/art/runtime/runtime.cc',
        'art/runtime/native_bridge_art_interface.cc': PAIR / 'delta/platform/art/runtime/native_bridge_art_interface.cc',
        'art/runtime/Android.bp': PREFORK / 'build-only-enabled-flavor/art/runtime/Android.bp',
        'art/libnativebridge/Android.bp': PREFORK / 'build-only-enabled-flavor/art/libnativebridge/Android.bp',
    }
    for name in ['native_bridge.cc', 'droidloom_generation.cc', 'droidloom_generation.h',
                 'include/nativebridge/droidloom_generation_protocol.h',
                 'include/nativebridge/native_bridge.h', 'libnativebridge.map.txt']:
        files['art/libnativebridge/' + name] = current / 'art/libnativebridge' / name
    assert len(files) == 10
    inputs = []
    for path, source in sorted(files.items()):
        raw = source.read_bytes()
        put('delta/android/native-generation-art/source/' + path, raw)
        inputs.append({'path': path, 'bytes': len(raw), 'sha256': sha(raw),
                       'origin': str(source),
                       'kind': 'enabled_build_only_blueprint' if path.endswith('/Android.bp') else 'source'})
    module = (WORK / 'native-generation-art.template.rs').read_text()
    rows = '\n'.join('    Input { path: ' + json.dumps(row['path']) + ', bytes: ' + str(row['bytes']) +
                     ', sha256: ' + json.dumps(row['sha256']) + ' },' for row in inputs)
    assert module.count('/* FROZEN_INPUT_TABLE */') == 1
    module = module.replace('/* FROZEN_INPUT_TABLE */', rows)
    put('delta/tools/droidloom-update/src/native_generation_art.rs', module.encode())

    main_text = exact(old_main.decode(), 'mod native_generation;\n',
                      'mod native_generation;\nmod native_generation_art;\n')
    main_text = exact(main_text, 'enum Action {\n', '''enum Action {
    /// Build only the paired ART libraries through the normal strict source projection.
    /// Builds no image and does not install, activate, or enable a running component.
    NativeGenerationArtBuild {
        /// Existing package workspace containing aosp-source.
        #[arg(long)]
        work: PathBuf,
        /// Required fresh absolute output directory, separate from aosp-source.
        #[arg(long)]
        out: PathBuf,
        /// Compile the enabled ABI flavor only; runtime qualification remains separate.
        #[arg(long)]
        enabled_build_only: bool,
    },
''')
    main_text = exact(main_text,
        'fn selected_build_out(command: Option<&Action>, work: &std::path::Path) -> Result<PathBuf> {\n',
        '''fn selected_build_out(command: Option<&Action>, work: &std::path::Path) -> Result<PathBuf> {
    if let Some(Action::NativeGenerationArtBuild { out, .. }) = command {
        return native_generation_art::validated_output(work, out);
    }
''')
    main_text = exact(main_text, '        | Some(Action::NativeEngineBuild { work, .. })\n',
                      '        | Some(Action::NativeEngineBuild { work, .. })\n        | Some(Action::NativeGenerationArtBuild { work, .. })\n')
    main_text = exact(main_text, '    if let Some(Action::TargetClosureBuild { tests, .. }) = args.command {\n',
        '''    if let Some(Action::NativeGenerationArtBuild { enabled_build_only, .. }) = args.command {
        return android::build_native_generation_art(
            &repo, &source, &out, &work, product, jobs,
            native_generation_art::Flavor::from_build_only_flag(enabled_build_only),
        );
    }
    if let Some(Action::TargetClosureBuild { tests, .. }) = args.command {
''')
    put('delta/tools/droidloom-update/src/main.rs', main_text.encode())

    android = old_android.decode()
    signature = '''fn build_targets_with_dependency_mode(
    repo: &Path,
    source: &Path,
    out: &Path,
    work: &Path,
    product: &str,
    jobs: usize,
    targets: &[&str],
    dependency_mode: SoongDependencyMode,
) -> Result<()> {
'''
    replacement = signature + '''    build_targets_with_art_projection(
        repo, source, out, work, product, jobs, targets, dependency_mode, None,
    )
}

/// Fixed ART-only build entry. Normal callers retain the exact previous wrapper.
pub fn build_native_generation_art(
    repo: &Path,
    source: &Path,
    out: &Path,
    work: &Path,
    product: &str,
    jobs: usize,
    flavor: crate::native_generation_art::Flavor,
) -> Result<()> {
    build_targets_with_art_projection(
        repo, source, out, work, product, jobs,
        crate::native_generation_art::TARGETS, SoongDependencyMode::Strict, Some(flavor),
    )
}

fn build_targets_with_art_projection(
    repo: &Path,
    source: &Path,
    out: &Path,
    work: &Path,
    product: &str,
    jobs: usize,
    targets: &[&str],
    dependency_mode: SoongDependencyMode,
    art_flavor: Option<crate::native_generation_art::Flavor>,
) -> Result<()> {
'''
    android = exact(android, signature, replacement)
    android = exact(android,
        '    validate_soong_dependency_mode(dependency_mode, targets)?;\n    if dependency_mode == SoongDependencyMode::NativeEngineTargetClosure {\n',
        '''    validate_soong_dependency_mode(dependency_mode, targets)?;
    if let Some(flavor) = art_flavor {
        if dependency_mode != SoongDependencyMode::Strict
            || targets != crate::native_generation_art::TARGETS
        {
            return fail("paired ART projection requires only its fixed targets and strict dependencies");
        }
        crate::native_generation_art::begin_attempt(work, out, flavor)?;
    }
    if dependency_mode == SoongDependencyMode::NativeEngineTargetClosure {
''')
    android = exact(android,
        '    let mut p = Projection::new(work.join("source-projection.json"))?;\n',
        '''    let mut p = Projection::new(work.join("source-projection.json"))?;
    if let Some(flavor) = art_flavor {
        crate::native_generation_art::project(repo, source, &mut p, flavor)?;
    }
''')
    android = exact(android, '    if leaf_go_memory_mode(dependency_mode) {\n',
                      '    if leaf_go_memory_mode(dependency_mode) || art_flavor.is_some() {\n')
    android = exact(android,
        '    let selected_targets = selected_soong_targets(dependency_mode, targets, out, product)?;\n',
        '''    let selected_targets = selected_soong_targets(dependency_mode, targets, out, product)?;
    if let Some(flavor) = art_flavor {
        crate::native_generation_art::write_inputs(
            out, flavor, &selected_targets,
            serde_json::to_value(p.effective_inventory(repo, source)?)?,
        )?;
    }
''')
    android = exact(android, '    result?;\n    if let Some(inputs) = engine_inputs {\n',
        '''    result?;
    if let Some(flavor) = art_flavor {
        crate::native_generation_art::write_command_completion(out, flavor)?;
    }
    if let Some(inputs) = engine_inputs {
''')
    put('delta/tools/droidloom-update/src/android.rs', android.encode())
    expected = dict(parent)
    changes = {}
    for path in sorted((OUT / 'delta').rglob('*')):
        if not path.is_file():
            continue
        relative = str(path.relative_to(OUT / 'delta'))
        raw = path.read_bytes()
        row = {'kind': 'file', 'sha256': sha(raw), 'bytes': len(raw),
               'mode': parent[relative]['mode'] if relative in parent else 0o644}
        expected[relative] = row
        changes[relative] = {'before': parent.get(relative), 'after': row}
    assert len(expected) == 462 and len(changes) == 13
    put('references/parent451-source-manifest.json', parent_bytes)
    put('expected-builder462-source-manifest.json', (json.dumps(expected, indent=2) + '\n').encode())
    patch = ''
    for relative in changes:
        before = OUT / 'preimage' / relative
        old = before.read_text() if before.exists() else ''
        new = (OUT / 'delta' / relative).read_text()
        patch += ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
            fromfile='a/' + relative if before.exists() else '/dev/null', tofile='b/' + relative))
    put('normal-art-projection.patch', patch.encode())
    put('SOURCE_DELTA.json', (json.dumps({'parent_files':451,'candidate_files':462,
        'changed_existing':2,'added':11,'unchanged_existing':449,'changes':changes,
        'platform_inputs':inputs,'actual_compile':False,'full_TU_gate_executed':False},indent=2)+'\n').encode())
    put('derive.py', Path(__file__).read_bytes())
    print(json.dumps({'files':462,'source_changes':13,'actual_compile':False,
                     'expected_manifest_sha256':sha((OUT/'expected-builder462-source-manifest.json').read_bytes()),
                     'patch_bytes':len(patch.encode())}))


if __name__ == '__main__':
    main()
