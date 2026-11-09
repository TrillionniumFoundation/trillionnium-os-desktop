"""Verify a replacement against the exact public helper, without executing it.

Usage: python3 -I -B verify_reference_patch.py [--baseline /path/to/executor.py]
Reads source and emits a scope receipt to stdout. Does not apply the patch.
"""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE_SHA256 = '22e7e85962c52a5cf44759dd99610d16293a0f8573ee68b8b9da4c89b1c7911a'
TARGET = 'cleanup/apps-old-root-retirement-20261108-8b88-r1/executor.py'


def replacement(base, observer):
    if hashlib.sha256(base).hexdigest() != BASE_SHA256:
        raise ValueError('baseline SHA-256 mismatch; reconcile the actual helper before changing it')
    old_text, new_text = base.decode('utf-8'), observer.decode('utf-8')
    old_tree, new_tree = ast.parse(old_text), ast.parse(new_text)
    def function(tree):
        matches = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'live_references']
        if len(matches) != 1:
            raise ValueError('exactly one top-level live_references is required')
        return matches[0]
    old, new = function(old_tree), function(new_tree)
    lines = old_text.splitlines(keepends=True)
    prefix, suffix = ''.join(lines[:old.lineno - 1]), ''.join(lines[old.end_lineno:])
    body = ast.get_source_segment(new_text, new)
    revised = prefix + body + '\n' + suffix
    checked = ast.parse(revised)
    checked.body = [n for n in checked.body if not isinstance(n, ast.FunctionDef) or n.name != 'live_references']
    old_tree.body = [n for n in old_tree.body if not isinstance(n, ast.FunctionDef) or n.name != 'live_references']
    if ast.dump(checked) != ast.dump(old_tree):
        raise ValueError('code outside live_references changed')
    compile(revised, TARGET, 'exec')  # Syntax check only; code object is never executed.
    patch = ''.join(difflib.unified_diff(old_text.splitlines(keepends=True),
                                       revised.splitlines(keepends=True),
                                       fromfile='a/' + TARGET, tofile='b/' + TARGET))
    receipt = {
        'baseline_sha256': BASE_SHA256,
        'revised_helper_bytes': len(revised.encode()),
        'revised_helper_sha256': hashlib.sha256(revised.encode()).hexdigest(),
        'prefix_sha256': hashlib.sha256(prefix.encode()).hexdigest(),
        'suffix_sha256': hashlib.sha256(suffix.encode()).hexdigest(),
        'all_code_outside_live_references_unchanged': True,
        'source_executed': False,
        'patch_applied': False,
        'deletion_authorized': False,
    }
    return patch, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path,
                        default=Path(__file__).resolve().parent / 'fixtures/executor-baseline.py')
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    generated, receipt = replacement(args.baseline.read_bytes(), (here / 'reference_observer.py').read_bytes())
    if generated != (here / 'reference_observer.patch').read_text():
        raise ValueError('published patch differs from the pinned single-function replacement')
    print(json.dumps(receipt, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
