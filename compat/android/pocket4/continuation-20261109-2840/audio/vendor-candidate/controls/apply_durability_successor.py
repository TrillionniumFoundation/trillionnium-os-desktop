from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path('/data/pocket4-audio-qpr1-vendor-candidate-20261109-2840-r1')
SOURCE = ROOT / 'source'
frozen = json.loads((ROOT / 'SOURCE_FROZEN.json').read_text())
assert subprocess.check_output(['/usr/bin/git', '-C', str(SOURCE), 'rev-parse', 'HEAD']).decode().strip() == frozen['commit']
assert frozen['commit'] == '287595503314c610355bcce85a1ff148d0569ac9'
for relative, reference in frozen['source_files'].items():
    raw = (SOURCE / relative).read_bytes()
    assert len(raw) == reference['bytes'] and hashlib.sha256(raw).hexdigest() == reference['sha256']

def replace(path, before, after):
    text = path.read_text()
    assert text.count(before) == 1, (str(path), text.count(before))
    path.write_text(text.replace(before, after))

source = SOURCE / 'tools/droidloom-update/src/audio_vendor_candidate.rs'
replace(source,
        '    output.set_permissions(Permissions::from_mode(0o400))?;\n',
        '    output.set_permissions(Permissions::from_mode(0o400))?;\n    output.sync_all()?;\n')
replace(source,
        '    manifest.set_permissions(Permissions::from_mode(0o400))?;\n',
        '    manifest.set_permissions(Permissions::from_mode(0o400))?;\n    manifest.sync_all()?;\n')
replace(source, '''    chain.0[stage_dir].file.sync_all()?;
    chain.0[parent].file.sync_all()?;
    Ok(report)
''', '''    // Persist each newly created directory entry before its containing entry.
    for held in chain.0[stage_dir..].iter().rev() {
        held.file.sync_all()?;
    }
    chain.0[parent].file.sync_all()?;
    chain.verify()?;
    need(
        file_identity(&output.metadata()?)? == target_identity
            && named_identity(&stat_at(chain.fd(artifact_dir), OsStr::new(&target_name))?)?
                == target_identity
            && file_identity(&manifest.metadata()?)? == manifest_identity
            && named_identity(&stat_at(chain.fd(stage_dir), OsStr::new("CANDIDATE.json"))?)?
                == manifest_identity,
        "staged files changed during durable publication",
    )?;
    Ok(report)
''')
readme = SOURCE / 'tools/droidloom-update/README.md'
replace(readme, '''staging can leave a partial private directory without a successful receipt;
inspect that attempt before choosing another new destination.
''', '''staging can leave a partial private directory, including a manifest written
before a final synchronization or identity check failed. Consume a candidate
only after the command exits successfully; inspect a failed attempt before
choosing another new destination.

The staged files are synchronized again after their final permissions are set.
New directories are synchronized from deepest child through the stage root,
then the existing parent. Final descriptor and pathname identity checks precede
successful return.
''')
subprocess.run(['/usr/bin/git', '-C', str(SOURCE), 'diff', '--check'], check=True)
print(json.dumps({'state': 'DURABILITY_SUCCESSOR_APPLIED_NOT_YET_RETESTED', 'parent': frozen['commit'],
                  'changed': subprocess.check_output(['/usr/bin/git', '-C', str(SOURCE), 'diff', '--name-only']).decode().splitlines()}))
