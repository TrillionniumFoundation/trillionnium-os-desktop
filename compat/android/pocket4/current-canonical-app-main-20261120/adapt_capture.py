"""Build the immutable new Main factory from pinned utilities plus explicit body."""
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
COHORT='/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/source/main'
raw=(ROOT/'inputs/main/capture_main.py').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='1a1a9122744eb83b047da9562daf9930883684a4f11d0de76e3e4154a91e9e69'
s=raw.decode();start=s.index('def capture(');end=s.index('def main():')
s=s[:start]+(ROOT/'new_capture_body.py.txt').read_text()+'\n'+s[end:]
head=s.index("ROOT = Path(");tail=s.index('USER = [')
rows=["QUALIFICATION=Path('/var/lib/droidloom/qualification/pocket4')","SOURCE=Path("+repr(COHORT)+")"]
for constant,name in (('EPOCH','framework_epoch.py'),('READER','held_runtime.py'),('USERNS','main_user_namespace.py'),
                      ('NATIVE','native_main_observation.py'),('IMAGE','native_image_observation.py'),
                      ('HELPER_CONTRACT','helper_contract.py'),('READONLY_ENTRY','main_readonly_entry.py'),
                      ('COMMANDS','business_commands.py')):
    source=ROOT/'source'/name
    if not source.exists():source=ROOT/'inputs/main'/name
    raw=source.read_bytes()
    location='SOURCE.parent/\'support\'/'+repr(name) if name=='business_commands.py' else 'SOURCE/'+repr(name)
    rows.extend([constant+'='+location,constant+'_SHA='+repr(hashlib.sha256(raw).hexdigest())])
s=s[:head]+'\n'.join(rows)+'\n'+s[tail:]
s=s.replace('def show(base, unit):','def show(base, unit, seconds=15):')
s=s.replace("raw=host_command(base+['show',unit,'--property='+PROPERTIES])","raw=host_command(base+['show',unit,'--property='+PROPERTIES],seconds=seconds)")
compile(s,'capture_main.py','exec')
(ROOT/'source/capture_main.py').write_text(s)
print('capture_main',len(s.encode()),hashlib.sha256(s.encode()).hexdigest())
