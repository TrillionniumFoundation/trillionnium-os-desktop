#!/usr/bin/env python3
"""Patch the temporary S05 repair generator before its one-shot execution."""
from pathlib import Path

path = Path("tools/s05_authoritative_export_autofix.py")
text = path.read_text(encoding="utf-8")

start = text.index("    parent_pattern = re.compile(")
end = text.index("    parent_replacement = r'''", start)
text = text[:start] + text[end:]

start = text.index("    text, count = parent_pattern.subn")
end = text.index("\n\n    snapshot_impl = r'''", start)
replacement = '''    function_start = text.index("fn validate_parent_components(")
    function_end = text.index("\\nfn ", function_start + 1) + 1
    text = text[:function_start] + parent_replacement + text[function_end:]
'''
text = text[:start] + replacement + text[end:]

old = '''    #[cfg(test)]
    persistence_tests::point("export.after_stage_create")?;
'''
new = '''    #[cfg(test)]
    if let Err(error) = persistence_tests::point("export.after_stage_create") {
        drop(file);
        remove_unpublished_stage(&stage);
        return Err(error);
    }
'''
if text.count(old) != 1:
    raise SystemExit("expected one export.after_stage_create cutpoint")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
