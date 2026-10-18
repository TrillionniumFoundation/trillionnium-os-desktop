import importlib.util
import json
import os
from pathlib import Path
import tempfile
from unittest import mock

spec = importlib.util.spec_from_file_location('candidate', Path(__file__).with_name('archive.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
results = {}
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    source = root / 'source'
    source.mkdir()
    (source / 'archive.json').write_text('original selected evidence')
    destination = root / 'bundle'
    module.archive(source, destination)
    manifest = json.loads((destination / 'archive.json').read_text())
    results['reserved_output_overwrite'] = {'accepted': True, 'records': manifest['files'], 'overwritten': (destination / 'archive.json').read_text() != 'original selected evidence'}
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    source = root / 'source'
    source.mkdir()
    (source / 'normal.txt').write_text('stand-in data')
    destination = root / 'bundle'
    original_open = os.open
    def racing_open(name, flags, *args, **kwargs):
        if name == 'normal.txt':
            os.link(source / name, root / 'external-link.txt')
        return original_open(name, flags, *args, **kwargs)
    with mock.patch.object(module.os, 'open', racing_open):
        module.archive(source, destination)
    results['hardlink_between_lstat_and_open'] = {'accepted': True, 'source_links': (source / 'normal.txt').stat().st_nlink}
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    source = root / 'source'
    source.mkdir()
    (source / 'normal.txt').write_text('original root')
    destination = root / 'bundle'
    original_fwalk = os.fwalk
    def racing_fwalk(*args, **kwargs):
        source.rename(root / 'held-original')
        source.mkdir()
        (source / 'foreign.txt').write_text('replacement root')
        yield from original_fwalk(*args, **kwargs)
    with mock.patch.object(module.os, 'fwalk', racing_fwalk):
        module.archive(source, destination)
    results['source_path_replaced_after_open'] = {'accepted': True, 'archived_files': sorted(p.name for p in destination.iterdir())}
print(json.dumps(results, indent=2))
