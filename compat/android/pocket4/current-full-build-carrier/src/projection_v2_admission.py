"""Strict observation of the current typed v2 source journal; history remains unchanged."""
import json
from pathlib import Path
def need(v,m):
 if not v:raise RuntimeError(m)
def pairs(rows):
 result={}
 for key,value in rows:
  need(key not in result,'duplicate projection journal JSON field');result[key]=value
 return result
def invalid_constant(value):raise RuntimeError('nonfinite projection journal JSON')
def validate(raw,source,projected_files=None):
 root=json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid_constant)
 need(type(root)is dict and set(root)=={'schema_version','originals'}and type(root['schema_version'])is int and root['schema_version']==2 and type(root['originals'])is list,'exact current v2 journal root required')
 paths=set();relative=set();files=absences=0;source=Path(source)
 for row in root['originals']:
  need(type(row)is dict and set(row)=={'path','bytes','modified','permissions_mode'},'exact four original fields required')
  name=row['path'];need(type(name)is str,'original path string required');p=Path(name);need(p.is_absolute()and'..'not in p.parts and p!=source and p.is_relative_to(source)and name not in paths,'duplicate or unconfined original path');paths.add(name);relative.add(p.relative_to(source).as_posix())
  if row['bytes']is None:
   need(row['modified']is row['permissions_mode']is None,'exact original absence required');absences+=1
  else:
   need(type(row['bytes'])is list and all(type(b)is int and 0<=b<=255 for b in row['bytes']),'original bytes must be exact u8 values')
   mode=row['permissions_mode'];need(type(mode)is int and mode&~0o177777==0 and mode&0o170000==0o100000,'complete original regular-file mode required')
   modified=row['modified'];need(type(modified)is dict and set(modified)=={'secs_since_epoch','nanos_since_epoch'}and type(modified['secs_since_epoch'])is int and 0<=modified['secs_since_epoch']<2**64 and type(modified['nanos_since_epoch'])is int and 0<=modified['nanos_since_epoch']<1000000000,'exact original SystemTime required');files+=1
 if projected_files is not None:need(type(projected_files)is dict and relative==set(projected_files),'journal original paths differ from actual normal projection inventory')
 return{'schema_version':2,'original_rows':len(paths),'regular_originals':files,'original_absences':absences,'all_original_paths_confined_and_unique':True,'all_complete_mode_mtime_and_absence_verified':True,'actual_projection_inventory_joined':projected_files is not None,'source_writes':0}
def selftest():
 source=Path('/not-executed/source');row={'path':str(source/'a'),'bytes':[1,2],'modified':{'secs_since_epoch':1,'nanos_since_epoch':2},'permissions_mode':0o100600};good={'schema_version':2,'originals':[row,{'path':str(source/'b'),'bytes':None,'modified':None,'permissions_mode':None}]}
 need(validate(json.dumps(good),source,{'a':'x','b':None})['original_rows']==2,'valid exact v2 observation failed')
 cases=[[],{'schema_version':1,'originals':[row]},{'schema_version':True,'originals':[row]},{'schema_version':2,'originals':[{k:v for k,v in row.items()if k!='permissions_mode'}]},{'schema_version':2,'originals':[{**row,'path':'/outside'}]},{'schema_version':2,'originals':[row,row]},{'schema_version':2,'originals':[{**row,'permissions_mode':0o120777}]},{'schema_version':2,'originals':[{**row,'bytes':[True]}]},{'schema_version':2,'originals':[{**row,'modified':{'secs_since_epoch':1,'nanos_since_epoch':1000000000}}]}]
 for bad in cases:
  try:validate(json.dumps(bad),source)
  except (RuntimeError,ValueError):pass
  else:raise RuntimeError('invalid journal admitted by current v2 observer')
 for raw in ['{"schema_version":2,"schema_version":2,"originals":[]}','{"schema_version":2,"originals":[],"unknown":1}']:
  try:validate(raw,source)
  except (RuntimeError,ValueError):pass
  else:raise RuntimeError('duplicate or unknown journal fields admitted')
 try:validate(json.dumps(good),source,{'a':'x'})
 except RuntimeError:pass
 else:raise RuntimeError('mismatched actual normal inventory admitted')
 return{'positive_complete_v2':1,'negative_contract_cases':12,'source_writes':0,'full_starts':0}
