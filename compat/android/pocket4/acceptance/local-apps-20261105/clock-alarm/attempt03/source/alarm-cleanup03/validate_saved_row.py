from pathlib import Path
import copy,hashlib,json,types

HERE=Path(__file__).parent
SOURCE=HERE/'cleanup_alarm03.py'
OLD=HERE.parent/'alarm-accept03'/'alarm_accept03.py'
RAW=HERE.parent/'alarm-accept03'/'result03-original.json'
TREE=HERE.parent/'alarm-accept03'/'saved03-112-cleanup-current-owned-window.json'

def module(path,name):
    m=types.ModuleType(name);m.__file__=str(path);exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m

old=module(OLD,'alarm_old');new=module(SOURCE,'alarm_cleanup')
prior=json.loads(RAW.read_text());tree=json.loads(TREE.read_text())
claim,text=new.bind_prior(prior,tree)
klass=new.make_flow(old)

def sample(cls,nodes=None,value=None):
    obj=cls.__new__(cls);obj.nodes=copy.deepcopy(nodes or tree['native']['nodes'])
    obj.ids=prior['actual_resource_contract']['ids'];obj.clock_text=text
    obj.m=types.SimpleNamespace(MARKER='Pocket4 QA alarm 19d75a2c')
    obj.reader=types.SimpleNamespace(read=lambda:copy.deepcopy(value or claim),target=prior['target'])
    return obj

cases=[]
def rejected(name,fn,expected):
    try:fn()
    except RuntimeError as e:
        assert str(e)==expected,(name,str(e));cases.append({'name':name,'passed':True,'error':str(e)});return
    raise AssertionError(name+' unexpectedly accepted')

rejected('actual03_old_expanded_assumption',lambda:sample(old.Flow).row(False),'OWNED_ALARM_ROW_CONTAINER_AMBIGUOUS')
row=sample(klass).row(False)
assert row['container']['bounds_array']==[0,506,1200,752] and row['switch']['checked'] is True
assert row['container']['content-desc']==text+' Alarm' and 16 in row['container']['supported_actions']
assert not [n for n in row['children'] if n.get('resource-id')==prior['actual_resource_contract']['ids']['delete']]
cases.append({'name':'actual_saved_unique_collapsed_owned_row','passed':True})
bad=copy.deepcopy(claim);bad['alarm']['_id']=4
rejected('foreign_id',lambda:sample(klass,value=bad).row(False),'EXACT_UNLABELLED_FIXTURE_REQUIRED')
bad=copy.deepcopy(claim);bad['alarm']['enabled']=0
rejected('switch_db_mismatch',lambda:sample(klass,value=bad).row(False),'OWNED_ROW_DB_STATE_DIFFERS')
nodes=copy.deepcopy(tree['native']['nodes']);nodes.append(copy.deepcopy(row['clock']))
rejected('duplicate_time',lambda:sample(klass,nodes=nodes).row(False),'OWNED_TIME_NODE_NOT_UNIQUE')
report={'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    'old_source_sha256':hashlib.sha256(OLD.read_bytes()).hexdigest(),
    'actual_tree_sha256':hashlib.sha256(TREE.read_bytes()).hexdigest(),
    'cases':cases,'passed':len(cases),'total':len(cases),'UI_actions':0,'RPC_calls':0,
    'scope':'actual saved-tree selection only; no delete, launch or live behavior qualification'}
(HERE/'LOCAL_VALIDATION.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps({'passed':len(cases),'total':len(cases),'UI_actions':0}))
