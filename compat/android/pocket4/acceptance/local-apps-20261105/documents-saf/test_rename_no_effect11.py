"""Actual retained Rename form + real bounded method, with UI/FS boundaries shimmed."""
import copy,importlib.util,json,types,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
def module(name):
    s=importlib.util.spec_from_file_location(name,HERE/(name+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
F=module('run_saf11');A=module('ui_adapter03')
OBS=json.loads((HERE/'fixtures/rename-confirm10.json').read_text())['observed_own_form']
class ControlError(RuntimeError):
    def __init__(self,**details):super().__init__('STALE_FRAME');self.details=details
def exercise(errors,fresh=None):
    flow=F.Flow.__new__(F.Flow);flow.result={};calls=[];observations=[];effects=[]
    ui=types.SimpleNamespace(one=A.Adapter.one,pending={},record=lambda *a:None)
    def act(obs,label,node):
        calls.append(label)
        if errors:
            error=errors.pop(0)
            if error is not None:
                if error.details.get('outcome_unknown'):ui.pending[label]={'input_acknowledged':False}
                raise error
        effects.append(label)
    def observe(*args):observations.append(args);return copy.deepcopy(fresh if fresh is not None else OBS)
    ui.input=act;ui.observe=observe;flow.ui=ui
    flow.s=types.SimpleNamespace(helper=types.SimpleNamespace(ControlError=ControlError))
    flow.folder=types.SimpleNamespace(verify=lambda *args:None)
    failure=None
    try:flow.confirm_owned_rename(copy.deepcopy(OBS))
    except RuntimeError as exc:failure=str(exc)
    return calls,observations,effects,failure,ui.pending
class NoEffectRename(unittest.TestCase):
    def test_explicit_no_effect_allows_fresh_same_form_once(self):
        c,o,e,f,p=exercise([ControlError(action_taken=False),None])
        self.assertEqual((len(c),len(o),len(e),f,p),(2,1,1,None,{}))
    def test_unknown_or_missing_no_effect_never_redecides(self):
        for error in [ControlError(outcome_unknown=True),ControlError(),ControlError(action_taken=False,outcome_unknown=True)]:
            c,o,e,f,p=exercise([error]);self.assertEqual((len(c),len(o),len(e)),(1,0,0));self.assertEqual(f,'STALE_FRAME')
    def test_context_or_focus_change_stops_without_next_input(self):
        for kind in ['context','focus']:
            obs=copy.deepcopy(OBS)
            if kind=='context':obs['screenshot']['context_token']='changed'
            else:obs['focus']['window_token']='changed'
            c,o,e,f,p=exercise([ControlError(action_taken=False)],obs)
            self.assertEqual((len(c),len(e)),(1,0));self.assertEqual(f,'RENAME_CONFIRM_FOCUS_OR_CONTEXT_CHANGED')
    def test_full_field_or_button_change_stops_without_next_input(self):
        for index in [0,1]:
            obs=copy.deepcopy(OBS);obs['nodes'][index]['bounds_array'][0]+=1
            c,o,e,f,p=exercise([ControlError(action_taken=False)],obs)
            self.assertEqual((len(c),len(e)),(1,0));self.assertEqual(f,'RENAME_CONFIRM_FORM_CHANGED')
    def test_at_most_three_decisions_all_stale_no_fourth(self):
        c,o,e,f,p=exercise([ControlError(action_taken=False) for _ in range(4)])
        self.assertEqual((len(c),len(o),len(e)),(3,2,0));self.assertEqual(f,'STALE_FRAME')
    def test_cross_connection_number_only_does_not_change_target(self):
        obs=copy.deepcopy(OBS)
        for n in obs['nodes']:n['window_id']+=1
        c,o,e,f,p=exercise([ControlError(action_taken=False),None],obs)
        self.assertEqual((len(c),len(o),len(e),f),(2,1,1,None))
if __name__=='__main__':unittest.main(verbosity=2)
