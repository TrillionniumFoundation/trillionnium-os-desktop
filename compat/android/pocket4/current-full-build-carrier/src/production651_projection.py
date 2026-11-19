"""Independent current original inputs and strict observed/restored v2 projections."""
import os,json,re,time,hashlib,stat,importlib.util
from pathlib import Path
_spec=importlib.util.spec_from_file_location('projection_candidate_checks',Path(__file__).with_name('carrier_checks.py'))
checks=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(checks)
producer=checks.sibling('producer_contract')
def need(v,m):
 if not v:raise RuntimeError(m)
def paths_for_recipe(recipe,source,old_scope):
 old_root=Path('/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/work/aosp-source')
 paths=set()
 for value in json.loads(Path(old_scope).read_bytes())['paths']:
  prior=Path(value)
  need(prior.is_absolute() and prior.is_relative_to(old_root) and prior!=old_root and '..' not in prior.parts,
       'historical path scope must stay within the authenticated original source root')
  paths.add(str(Path(source)/prior.relative_to(old_root)))
 text=(Path(recipe)/'tools/droidloom-update/src/android.rs').read_text()
 block=text[text.index('const PATCHES:'):text.index('// Keep the upstream missing-dependency')]
 pairs=re.findall(r'\(\s*"([^"]*)"\s*,\s*"([^"]+\.patch)"\s*,?\s*\)',block)
 need(len(pairs)>10,'normal checked platform patch list was not decoded')
 pairs += [('',p) for p in ('android/aosp-patches/0015-droidloom-pcm-output.patch','android/aosp-patches/0016-droidloom-pcm-cancellation-lifecycle.patch','android/aosp-patches/0017-droidloom-real-pcm-input.patch')]
 current=producer.spec()
 for lane,directory,cwd in [('libpng','android/security/libpng-ownership','external/libpng'),('wm','android/security/wm','frameworks/base'),('framework','android/security/framework-asb','frameworks/base'),('avb','android/security/avb-rsa','external/avb')]:
  expected={row[0]:(row[1],row[2]) for row in current['lanes'][lane]['patches']}
  actual={str(p.relative_to(recipe)) for p in (Path(recipe)/directory).rglob('*.patch')}
  need(actual==set(expected),'complete current official patch membership differs: '+lane)
  for name,(size,digest) in expected.items():
   checks.exact_file({'path':str(Path(recipe)/name),'bytes':size,'sha256':digest},Path(recipe)/name)
   pairs.append((cwd,name))
 for cwd,name in pairs:
  raw=(Path(recipe)/name).read_text()
  names=re.findall(r'^(?:--- a/|\+\+\+ b/)([^\t\r\n]+)',raw,re.M)
  need(names,'normal patch path header missing: '+name)
  for relative in names:
   p=Path(source)/cwd/relative
   need('..' not in p.parts and p.is_relative_to(source) and '.git' not in p.parts,'patch path escapes fixed source')
   paths.add(str(p))
 need(0<len(paths)<512,'bounded current normal projection path set required')
 return sorted(paths),pairs
def capture(recipe,source,old_scope,physical):
 paths,patches=paths_for_recipe(recipe,source,old_scope)
 rows={p:physical(p) for p in paths}
 for p,row in rows.items():need(physical(p)==row,'original input changed across complete capture')
 return {'schema':'p4-production651-independent-originals-v1','source':str(source),'captured_ns':time.time_ns(),'paths':paths,'originals':rows,'normal_patch_inputs':patches,'historical_scope_values_inherited':False,'historical_paths_rebased_only':True,'source_writes':0}
def compare(raw,baseline,parse_v2,original):
 rows=parse_v2(raw);known=baseline['originals']
 need(set(rows)<=set(known),'normal journal has a path absent from the independent pre-normal baseline: '+str(sorted(set(rows)-set(known))))
 for p,row in rows.items():
  expected=None if known[p] is None else original(known[p])
  need(row==expected,'normal journal original differs from independent bytes/mode/nsmtime/absence: '+p)
 return rows
def verify_restored(baseline,projected,physical,original):
 changed=[];unattributed=[];current={}
 for p,before in baseline['originals'].items():
  after=physical(p);current[p]=after
  if before is None:need(after is None,'original absence did not restore: '+p);continue
  need(after is not None and original(after)==original(before),'whole original bytes/mode/nsmtime did not restore: '+p)
  if after['identity']!=before['identity']:
   if p not in projected:unattributed.append(p)
   else:need(projected[p]==original(before),'restoration original differs from actual owned journal')
   need(all(after['identity'][i]==before['identity'][i] for i in (0,2,3,4,5,6,7)),'restoration changed original identity beyond inode/ctime: '+p)
   changed.append({'path':p,'before':before['identity'],'after':after['identity']})
 for p,row in current.items():need(physical(p)==row,'restored originals changed during independent boundary')
 need(not unattributed,'original F9 changed without observed owned journal: '+str(unattributed))
 return {'source':baseline['source'],'roles':len(current),'observed_originals':len(projected),'whole_bytes_mode_nsmtime_absence_restored':True,'only_owned_projected_inode_ctime_changed':True,'changed_F9':changed,'source_writes':0}

