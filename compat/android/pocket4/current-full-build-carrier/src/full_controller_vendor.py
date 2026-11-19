from pathlib import Path
import sys
entry=sys.modules.get('p4_storage_entry')
assert entry is not None and entry.proof['role']=='vendor_inner'
p=Path(__file__).with_name('full_controller.py')
exec(compile(p.read_bytes(),str(p),'exec'),globals())
