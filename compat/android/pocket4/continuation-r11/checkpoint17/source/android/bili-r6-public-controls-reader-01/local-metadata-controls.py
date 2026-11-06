#!/usr/bin/env python3
"""Two pure output-scope controls. No collect, private files, Android or remote calls."""
from pathlib import Path
import json,types
HERE=Path(__file__).resolve().parent
m=types.ModuleType('candidate');exec(compile((HERE/'read_controls.py').read_bytes(),'read_controls.py','exec'),m.__dict__)
qa={'canonical':lambda v:json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()}

def node(path, resource='', kind='android.widget.FrameLayout', label='', description='', **kwargs):
    value = {'path': path, 'package': 'tv.danmaku.bili', 'enabled': True, 'clickable': False,
             'visible': True, 'focused': False, 'selected': False, 'checked': False,
             'password': False, 'child_count': 0, 'editable': False, 'supports_set_text': False,
             'bounds': [0, 0, 100, 100]}
    for key, text in (('resource_id', resource), ('class', kind), ('text', label), ('content_desc', description)):
        value[key] = text; value[key + '_sha256'] = m.sha(text.encode()); value[key + '_truncated'] = False
    value.update(kwargs)
    if value['password'] or not value['visible']:
        value['content_redacted'] = True
        for key in ('text', 'content_desc'):
            for suffix in ('', '_sha256', '_truncated'):
                value.pop(key + suffix)
    value['node_sha256'] = m.sha(qa['canonical'](value))
    return value

rows=[]
def base():
    return [node('0'),node('0/1',m.ROLE_IDS['area']),node('0/1/0',m.ROLE_IDS['container']),
            node('0/1/1',m.ROLE_IDS['overlay']),node('0/1/2',m.ROLE_IDS['toolbar']),
            node('0/1/0/0',m.ROLE_IDS['controls'])]
values=base()+[node('0/1/0/0/0',kind='android.widget.ImageButton',description='Pause',clickable=True),
    node('0/1/0/0/1',kind='android.widget.TextView',label='synthetic-private-inside-not-exported'),
    node('0/1/0/5',kind='android.widget.ImageButton',description='synthetic-outside-private-not-exported',clickable=True)]
x=m.controls_metadata({'nodes':values},{'crop':[0,0,100,100]});m.no_raw_ui(x);raw=json.dumps(x)
assert x['row_count']==3 and x['clickable_visible_enabled_count']==1 and x['seekbar_class_count']==0
assert 'synthetic-private-inside-not-exported' not in raw and 'synthetic-outside-private-not-exported' not in raw
assert m.sha(b'synthetic-private-inside-not-exported') in raw and m.sha(b'synthetic-outside-private-not-exported') not in raw
assert x['rows'][1]['public_description_label']=='Pause'
rows.append({'name':'only_control_subtree_outputs_public_label_and_unknown_inside_hash_outside_omitted','passed':True})
for mutation in ('missing','duplicate'):
    values=base()
    if mutation=='missing':values.pop()
    else:values.append(node('0/1/0/7',m.ROLE_IDS['controls']))
    try:m.controls_metadata({'nodes':values},{'crop':[0,0,100,100]})
    except RuntimeError as e:assert str(e)=='VERIFIED_PLAYER_ROLE_MUST_REMAIN_UNIQUE'
    else:raise AssertionError(mutation)
rows.append({'name':'missing_or_duplicate_control_container_rejected','passed':True})
print(json.dumps({'schema':1,'passed':True,'controls':rows,'actual_private_data_read':False,'collector_or_Android_executed':False},sort_keys=True))
